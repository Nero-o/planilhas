"""Export classified transactions to a 5-sheet xlsx + Validação tab.

Routing:
    - source=conta_simples -> "Conta Simples"
    - source=c6           -> "C6"
    - else, by empresa:
        AECO/PS/Cons/Matriz/Bravo/Igor -> "AECO"
        Sec -> "SEC"
        Tech -> "TECH"

The C6 sheet uses header "Entrada" instead of "Valor" (matches the master).
"""
import io
from datetime import datetime

import openpyxl
import pandas as pd
from openpyxl.styles import Font, PatternFill


CONF_FILL = {
    "green": PatternFill("solid", start_color="D4F7D4", end_color="D4F7D4"),
    "yellow": PatternFill("solid", start_color="FFF3A3", end_color="FFF3A3"),
    "red": PatternFill("solid", start_color="FFBBBB", end_color="FFBBBB"),
}

EMPRESA_TO_SHEET = {
    "AECO": "AECO",
    "PS": "AECO",
    "Cons": "AECO",
    "Matriz": "AECO",
    "Bravo": "AECO",
    "Igor": "AECO",
    "Sec": "SEC",
    "Tech": "TECH",
}

SHEETS = ["AECO", "SEC", "TECH", "Conta Simples", "C6"]


def route_row(row) -> str:
    if row["source"] == "conta_simples":
        return "Conta Simples"
    if row["source"] == "c6":
        return "C6"
    return EMPRESA_TO_SHEET.get(row["empresa"], "AECO")


def _write_validation_sheet(wb, txs_df, saldos: dict | None):
    ws = wb.create_sheet("Validação", 0)
    ws.append(["Fonte", "Saldo inicial", "Saldo final", "Soma transações", "Diferença", "OK?"])
    for c in ws[1]:
        c.font = Font(bold=True)
    if not saldos:
        return
    for src, s in saldos.items():
        if not s or s.get("saldo_inicial") is None or s.get("saldo_final") is None:
            continue
        source_name = "conta_simples" if src == "cs" else src
        soma = float(txs_df.loc[txs_df.source == source_name, "valor"].sum())
        expected = s["saldo_final"] - s["saldo_inicial"]
        diff = soma - expected
        ws.append([
            src, s["saldo_inicial"], s["saldo_final"],
            round(soma, 2), round(diff, 2), "OK" if abs(diff) <= 0.02 else "FALHOU",
        ])
    ws.append([])
    ws.append(["Distribuição por aba"])
    counts = txs_df.apply(route_row, axis=1).value_counts().to_dict()
    for sheet, n in counts.items():
        ws.append([sheet, n])


def to_xlsx(txs_df: pd.DataFrame, saldos: dict | None = None) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _write_validation_sheet(wb, txs_df, saldos or {})

    routed = txs_df.copy()
    routed["_sheet"] = routed.apply(route_row, axis=1)

    for sheet_name in SHEETS:
        ws = wb.create_sheet(sheet_name)
        # Linha 3 = header (espelha o master)
        ws.append([])
        ws.append([])
        valor_label = "Entrada" if sheet_name == "C6" else "Valor"
        ws.append([
            "Data", "Tipo de Pagamento", "Beneficiário", "Descrição",
            "Observações", "Fluxo de Caixa", valor_label, "Empresa",
        ])
        for c in ws[3]:
            c.font = Font(bold=True)
        rows = routed[routed._sheet == sheet_name]
        for r in rows.itertuples():
            data_val = r.data
            if isinstance(data_val, str):
                try:
                    data_val = datetime.fromisoformat(data_val[:10])
                except ValueError:
                    pass
            ws.append([
                data_val,
                r.tipo,
                r.beneficiario,
                r.descricao or "",
                r.observacoes or "",
                r.fluxo_caixa or "",
                r.valor,
                r.empresa or "",
            ])
            fill = CONF_FILL.get(r.confidence)
            if fill is not None:
                for cell in ws[ws.max_row]:
                    cell.fill = fill

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
