"""Parser for C6 extrato — STUB.

The C6 extract format has not been provided yet. This parser raises
NotImplementedError until a representative file is captured and the
parsing rules are filled in.

Expected output (matching the canonical schema):
    DataFrame columns: source="c6", data, tipo, beneficiario, valor, raw_row
    Saldos dict: {"saldo_inicial": float, "saldo_final": float}

When the C6 sample arrives:
- Inspect the file shape (xlsx vs csv, header row, columns)
- Implement parse() following the pattern of sicoob.py / bs2.py
- Add a fixture to data/fixtures/ and tests to tests/test_parsers.py
"""
import pandas as pd


def parse(path) -> tuple[pd.DataFrame, dict]:
    raise NotImplementedError(
        "C6 parser pending. The bank delivers a password-protected .xls (OLE2 "
        "EncryptedPackage). To enable this parser, open the file in Excel, "
        "remove the password (Arquivo → Informações → Proteger pasta de "
        "trabalho → Criptografar com senha → apagar), and save as .xlsx. "
        "Then provide the unprotected sample so the parsing rules can be filled in."
    )
