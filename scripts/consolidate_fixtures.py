"""Standardised consolidator for every spreadsheet in ``data/fixtures``.

Scans the fixtures directory, dispatches each file to the appropriate parser
based on its filename, classifies the resulting transactions against the
master dictionary, then writes a single consolidated workbook that mirrors
``Extrato AECO - Anual.xlsx`` — keeping the master's existing rows locked
(read-only) and appending the new entries as editable rows.

Usage:
    python scripts/consolidate_fixtures.py \\
        [--fixtures data/fixtures] \\
        [--master "data/fixtures/Extrato AECO - Anual.xlsx"] \\
        [--dictionary data/dictionary.json] \\
        [--out data/consolidado.xlsx] \\
        [--report data/consolidado.report.txt] \\
        [--c6-password SENHA] \\
        [--no-llm] [--no-protect]

Dispatch rules (case-insensitive matching on the file basename):

    BS2*.xlsx                                  -> bs2.parse
    Extrato BB*.xlsx                           -> bb.parse
    Transações_cartões*.xlsx / Conta Simples*  -> conta_simples.parse
    extrato-c6*.xlsx / c6*.xlsx                -> c6.parse

The master file itself is always skipped, even if it sits in the same folder.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from aeco import classifier, dictionary as dictmod, exporter, validate
from aeco.parsers import bb, bs2, c6 as c6_parser, conta_simples


_MASTER_DEFAULT = "Extrato AECO - Anual.xlsx"


def _normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def _classify_file(path: Path) -> str:
    n = _normalize_name(path.name)
    if "extrato aeco" in n:
        return "master"
    if n.startswith("bs2") or " bs2" in n or "bs2 -" in n:
        return "bs2"
    if "extrato bb" in n or n.startswith("bb"):
        return "bb"
    if "transacoes_cartoes" in n or "conta simples" in n or n.startswith("cs"):
        return "conta_simples"
    if "extrato-c6" in n or n.startswith("c6") or n.startswith("extrato c6"):
        return "c6"
    return "unknown"


_PARSERS = {
    "bs2": bs2.parse,
    "bb": bb.parse,
    "conta_simples": conta_simples.parse,
    "c6": c6_parser.parse,
}


def collect(fixtures_dir: Path, master_name: str, c6_password: str | None):
    """Walk ``fixtures_dir`` and parse every recognized spreadsheet.

    Returns ``(concatenated_df, saldos_per_file, processed, skipped)``.
    ``saldos_per_file`` is a list of ``(filename, source, saldo_dict, df)``;
    each file's saldo is validated independently, because the fixtures span
    multiple non-contiguous months and concatenating them would invalidate
    saldo arithmetic.
    """
    dfs = []
    saldos_per_file: list[tuple[str, str, dict, pd.DataFrame]] = []
    processed: list[tuple[str, str, int]] = []
    skipped: list[tuple[str, str]] = []

    files = sorted(p for p in fixtures_dir.iterdir() if p.is_file())
    for p in files:
        if p.name == master_name:
            continue
        kind = _classify_file(p)
        if kind in ("master", "unknown"):
            if kind == "unknown":
                skipped.append((p.name, "padrão de nome não reconhecido"))
            continue
        parser = _PARSERS[kind]
        try:
            if kind == "c6":
                df, s = parser(p, password=c6_password) if c6_password else parser(p)
            else:
                df, s = parser(p)
        except Exception as e:  # noqa: BLE001
            skipped.append((p.name, f"erro de parse: {e}"))
            continue
        n = len(df)
        if n == 0:
            skipped.append((p.name, "0 linhas extraídas"))
            continue
        dfs.append(df)
        processed.append((p.name, kind, n))
        saldos_per_file.append((p.name, kind, s, df))

    if not dfs:
        return pd.DataFrame(), [], processed, skipped
    return pd.concat(dfs, ignore_index=True), saldos_per_file, processed, skipped


def _per_file_saldo_report(saldos_per_file) -> list[str]:
    lines = ["Saldos por arquivo:"]
    for name, src, s, df in saldos_per_file:
        ini = s.get("saldo_inicial")
        fim = s.get("saldo_final")
        if ini is None or fim is None:
            lines.append(f"  [{src}] {name}: saldo não disponível")
            continue
        soma = round(float(df["valor"].sum()), 2)
        expected = round(fim - ini, 2)
        diff = round(soma - expected, 2)
        flag = "OK" if abs(diff) <= 0.02 else "FALHOU"
        lines.append(
            f"  [{src}] {name}: ini={ini} fim={fim}"
            f" soma={soma} esperado={expected} diff={diff} [{flag}]"
        )
    return lines


def _format_counts(val: dict) -> list[str]:
    lines = [
        f"Total: {val['counts']['total']}",
        f"  verdes:    {val['counts']['green']}",
        f"  amarelas:  {val['counts']['yellow']}",
        f"  vermelhas: {val['counts']['red']}",
        "",
        "Saldos por fonte:",
    ]
    for src, s in val["saldo"].items():
        flag = "OK" if s["ok"] else "FALHOU"
        lines.append(
            f"  {src}: soma={s['soma_observada']} esperado={s['esperado']}"
            f" diff={s['diferenca']} [{flag}]"
        )
    if val.get("duplicates"):
        lines.append("")
        lines.append(f"Duplicatas vs master: {len(val['duplicates'])}")
    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixtures", default="data/fixtures")
    p.add_argument("--master", default=None,
                   help="caminho do master (default: <fixtures>/Extrato AECO - Anual.xlsx)")
    p.add_argument("--dictionary", default="data/dictionary.json")
    p.add_argument("--out", default="data/consolidado.xlsx")
    p.add_argument("--report", default="data/consolidado.report.txt")
    p.add_argument("--c6-password", default=None)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--no-protect", action="store_true",
                   help="não habilita proteção da planilha (debug)")
    args = p.parse_args()

    fixtures_dir = Path(args.fixtures)
    if not fixtures_dir.exists():
        print(f"diretório de fixtures não encontrado: {fixtures_dir}", file=sys.stderr)
        sys.exit(2)

    master_name = _MASTER_DEFAULT
    master_path = Path(args.master) if args.master else fixtures_dir / master_name
    if not master_path.exists():
        print(f"master não encontrado: {master_path}", file=sys.stderr)
        sys.exit(2)

    # Build dictionary if missing
    dict_path = Path(args.dictionary)
    if dict_path.exists():
        dictionary = dictmod.load(dict_path)
    else:
        print(f"construindo dicionário a partir de {master_path} ...")
        dictionary = dictmod.build(master_path)
        try:
            dictmod.save(dictionary, dict_path)
        except OSError:
            pass

    print(f"escaneando {fixtures_dir} ...")
    raw, saldos_per_file, processed, skipped = collect(
        fixtures_dir, master_path.name, args.c6_password
    )
    if raw.empty:
        print("nenhum extrato processável encontrado.", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(processed)} arquivos OK, {len(skipped)} ignorados, {len(raw)} transações")

    out = classifier.classify(raw, dictionary, use_llm=not args.no_llm)
    # validate.run wants saldos keyed by source; we report per-file separately
    # because the fixtures span multiple non-contiguous months.
    val = validate.run(out, {}, anual_path=str(master_path))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    # Collapse saldos to one per source for the Validação tab (uses last file
    # of each source as a sanity reference).
    saldos_for_export: dict[str, dict] = {}
    for name, src, s, _df in saldos_per_file:
        saldos_for_export.setdefault(src, s)
    payload = exporter.to_xlsx_overlay(
        out,
        master_path,
        saldos_for_export,
        protect_password=None if args.no_protect else "",
    )
    Path(args.out).write_bytes(payload)
    print(f"escrito: {args.out}")

    lines = [
        "=== Consolidação AECO ===",
        f"master: {master_path}",
        f"fixtures: {fixtures_dir}",
        "",
        "Arquivos processados:",
    ]
    for name, kind, n in processed:
        lines.append(f"  [{kind}] {name} ({n} linhas)")
    if skipped:
        lines.append("")
        lines.append("Arquivos ignorados:")
        for name, reason in skipped:
            lines.append(f"  {name}: {reason}")
    lines.append("")
    lines.extend(_format_counts(val))
    lines.append("")
    lines.extend(_per_file_saldo_report(saldos_per_file))

    red = out[out.confidence == "red"]
    if not red.empty:
        lines.append("")
        lines.append(f"Vermelhas ({len(red)}) — precisam revisão:")
        for r in red.head(50).itertuples():
            lines.append(
                f"  [{r.source}] {str(r.data)[:10]} {r.tipo[:25]:25}"
                f" {str(r.beneficiario)[:35]:35} v={r.valor:>10.2f}"
            )
            lines.append(f"      → {r.reasoning[:120]}")
        if len(red) > 50:
            lines.append(f"  ... (+{len(red) - 50} omitidos)")

    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"relatório: {args.report}")
    print(
        f"  greens={val['counts']['green']} "
        f"yellows={val['counts']['yellow']} "
        f"reds={val['counts']['red']}"
    )


if __name__ == "__main__":
    main()
