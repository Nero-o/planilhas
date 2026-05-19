"""Shared helpers to let parsers consume CSV inputs through the same
row-iteration interface they already use for openpyxl worksheets.

Each parser keeps its own header detection / row processing — this module
only handles format detection and turns a CSV file into a worksheet-like
object that exposes ``iter_rows(min_row, values_only)``.
"""
from __future__ import annotations

import csv as _csv


_BOM = "﻿"
_XLSX_SIG = b"PK"           # ZIP container (plain xlsx)
_OLE2_SIG = b"\xd0\xcf\x11\xe0"  # encrypted xlsx (OLE2 compound)


def is_xlsx(path) -> bool:
    """Return True for xlsx (plain or encrypted), False for csv."""
    if hasattr(path, "name") and isinstance(path.name, str):
        return path.name.lower().endswith(".xlsx")
    if hasattr(path, "read"):
        pos = path.tell() if hasattr(path, "tell") else None
        head = path.read(4)
        if pos is not None and hasattr(path, "seek"):
            path.seek(pos)
        return head[:2] == _XLSX_SIG or head[:4] == _OLE2_SIG
    return str(path).lower().endswith(".xlsx")


def _read_text(path) -> str:
    if hasattr(path, "read"):
        if hasattr(path, "seek"):
            path.seek(0)
        raw = path.read()
    else:
        with open(path, "rb") as f:
            raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc) if isinstance(raw, bytes) else raw
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace") if isinstance(raw, bytes) else raw


def read_csv_rows(path) -> list[tuple]:
    """Read a CSV as a list of tuples (matching openpyxl iter_rows shape).

    Auto-detects the delimiter among ``; , \\t |``. Empty trailing cells are
    preserved; the BOM, if any, is stripped from the first cell of row 1.
    """
    text = _read_text(path).lstrip(_BOM)
    sample = text[:8192]
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except _csv.Error:
        delim = ";"
    reader = _csv.reader(text.splitlines(), delimiter=delim)
    rows: list[tuple] = []
    for row in reader:
        # Empty strings -> None so downstream "if r[0]" checks behave like
        # they do with openpyxl (which yields None for empty cells).
        rows.append(tuple(cell if cell != "" else None for cell in row))
    return rows


class RowSheet:
    """Tiny adapter exposing the subset of openpyxl's worksheet API used by
    the parsers: ``iter_rows(min_row, max_row, values_only)``.
    """

    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def iter_rows(
        self,
        min_row: int = 1,
        max_row: int | None = None,
        values_only: bool = True,
    ):
        start = max(0, min_row - 1)
        end = max_row if max_row is not None else len(self._rows)
        for r in self._rows[start:end]:
            yield r
