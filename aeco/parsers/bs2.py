"""Parser for BS2 extrato CSV.

Layout:
- Header preamble with "Saldo Atual; R$ X" line
- Table header line: "Data;Tipo;Detalhe;Banco;Agencia;Conta;Identificador da transação;...;Valor;Observação"
- "Saldo;Saldo Inicial;...;R$ X" row marks initial balance
- BOM may appear mid-file at line starts.
"""
import csv
import re
from datetime import datetime
import pandas as pd

from ..normalize import parse_pt_money, normalize_text


# "Débito PIX - 00712125906 - ZILDA APARECIDA DE MATOS" -> "ZILDA APARECIDA DE MATOS"
# "CRÉDITO PIX CHAVE - 63010206000112 - AN S C FINANCEIROS S/A"
# "TARIFA OPERAÇÕES PIX" (no dashes -> use detalhe as-is)
_DETAIL_RE = re.compile(r"^[^-]+-\s*\d+\s*-\s*(.+?)\s*$")
_BOM = "﻿"


def _read_lines(path) -> list[str]:
    if hasattr(path, "read"):
        raw = path.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig")
        return [l.lstrip(_BOM) for l in raw.splitlines(keepends=False)]
    with open(path, encoding="utf-8-sig") as f:
        return [l.rstrip("\n").rstrip("\r").lstrip(_BOM) for l in f]


def _extract_benef(detalhe: str) -> str:
    m = _DETAIL_RE.match(detalhe or "")
    return normalize_text(m.group(1)) if m else normalize_text(detalhe)


def parse(path) -> tuple[pd.DataFrame, dict]:
    lines = _read_lines(path)
    saldo_ini = saldo_fim = None
    # Saldo Atual aparece no preâmbulo
    for l in lines[:15]:
        if l.startswith("Saldo Atual;"):
            saldo_fim = parse_pt_money(l.split(";", 1)[1])
    header_idx = next(
        i for i, l in enumerate(lines)
        if l.startswith("Data;") and "Tipo" in l and "Detalhe" in l
    )
    rows = []
    reader = csv.reader(lines[header_idx + 1:], delimiter=";")
    for parts in reader:
        if not parts or not parts[0].strip():
            continue
        if "sujeitos a alterações" in parts[0]:
            continue
        if len(parts) < 9:
            continue
        data_str, tipo, detalhe = parts[0], parts[1], parts[2]
        valor_str = parts[8]
        if tipo.strip() == "Saldo":
            v = parse_pt_money(valor_str)
            if "Inicial" in detalhe:
                saldo_ini = v
            elif "Final" in detalhe:
                saldo_fim = v
            continue
        d = datetime.strptime(data_str.strip(), "%d/%m/%Y")
        valor = parse_pt_money(valor_str)
        benef = _extract_benef(detalhe)
        rows.append({
            "source": "bs2",
            "data": d,
            "tipo": normalize_text(tipo).title(),
            "beneficiario": benef,
            "valor": valor,
            "raw_row": {"tipo": tipo, "detalhe": detalhe, "valor_str": valor_str},
        })
    return pd.DataFrame(rows), {"saldo_inicial": saldo_ini, "saldo_final": saldo_fim}
