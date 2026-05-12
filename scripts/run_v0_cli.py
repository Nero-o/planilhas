"""CLI v0: end-to-end consolidação de um mês.

Usage:
    python scripts/run_v0_cli.py \\
        --sicoob "Extrato conta corrente - 032026.xlsx" \\
        --bs2 "extratoBancoBS2_*.csv" \\
        --cs "Transações_cartões_*.xlsx" \\
        [--c6 "c6_032026.xlsx"] \\
        --dictionary data/dictionary.json \\
        --master "Extrato AECO - Anual.xlsx" \\
        --out out_032026.xlsx \\
        --report report.txt \\
        [--no-llm]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from aeco import classifier, dictionary as dictmod, exporter, validate
from aeco.parsers import bs2, conta_simples, sicoob, c6 as c6_parser


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sicoob")
    p.add_argument("--bs2")
    p.add_argument("--cs")
    p.add_argument("--c6")
    p.add_argument("--dictionary", default="data/dictionary.json")
    p.add_argument("--master", default="Extrato AECO - Anual.xlsx")
    p.add_argument("--out", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--no-llm", action="store_true")
    args = p.parse_args()

    dictionary = dictmod.load(args.dictionary)

    dfs, saldos = [], {}
    if args.sicoob:
        df, s = sicoob.parse(args.sicoob); dfs.append(df); saldos["sicoob"] = s
    if args.bs2:
        df, s = bs2.parse(args.bs2); dfs.append(df); saldos["bs2"] = s
    if args.cs:
        df, s = conta_simples.parse(args.cs); dfs.append(df); saldos["conta_simples"] = s
    if args.c6:
        df, s = c6_parser.parse(args.c6); dfs.append(df); saldos["c6"] = s
    if not dfs:
        print("nothing to process", file=sys.stderr); sys.exit(1)

    raw = pd.concat(dfs, ignore_index=True)
    print(f"Loaded {len(raw)} transactions across {len(dfs)} sources")

    out = classifier.classify(raw, dictionary, use_llm=not args.no_llm)
    val = validate.run(out, saldos, anual_path=args.master)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(exporter.to_xlsx(out, saldos))
    print(f"Wrote {args.out}")

    lines = []
    lines.append(f"Total: {val['counts']['total']}")
    lines.append(f"  green:  {val['counts']['green']}")
    lines.append(f"  yellow: {val['counts']['yellow']}")
    lines.append(f"  red:    {val['counts']['red']}")
    lines.append("")
    lines.append("Saldos:")
    for src, s in val["saldo"].items():
        ok = "OK" if s["ok"] else "FALHOU"
        lines.append(f"  {src}: soma={s['soma_observada']} esperado={s['esperado']} diff={s['diferenca']} [{ok}]")
    lines.append("")
    lines.append(f"Duplicatas vs master: {len(val['duplicates'])}")
    for d in val["duplicates"][:20]:
        lines.append(f"  - {d['data']} {d['valor']:>10.2f} {d['beneficiario']} (sheet={d['in_sheet']}, score={d['match_score']})")
    lines.append("")
    lines.append("Reds (precisam revisão):")
    red = out[out.confidence == "red"]
    for r in red.itertuples():
        lines.append(f"  {r.source[:6]:6} {str(r.data)[:10]} {r.tipo[:25]:25} {r.beneficiario[:35]:35} v={r.valor:>10.2f}")
        lines.append(f"    -> {r.reasoning[:120]}")
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.report}")
    print(f"  greens={val['counts']['green']} yellows={val['counts']['yellow']} reds={val['counts']['red']}")


if __name__ == "__main__":
    main()
