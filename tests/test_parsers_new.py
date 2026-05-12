"""Smoke tests for the BS2 XLSX and BB parsers using current fixtures."""
from datetime import datetime
from pathlib import Path

import pytest

from aeco.parsers import bb, bs2


FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"


class TestBS2Xlsx:
    @pytest.fixture(scope="class")
    def parsed(self):
        return bs2.parse(FIXTURES / "01. BS2 - Janeiro 2026.xlsx")

    def test_loads_rows(self, parsed):
        df, _ = parsed
        assert len(df) >= 20
        assert (df["source"] == "bs2").all()

    def test_saldo_atual_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_final"] is not None
        assert abs(s["saldo_final"] - 8463.80) < 0.01

    def test_saldo_inicial_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] is not None
        assert abs(s["saldo_inicial"] - 8296.36) < 0.01

    def test_dates_are_datetime(self, parsed):
        df, _ = parsed
        assert df["data"].apply(lambda x: isinstance(x, datetime)).all()

    def test_no_saldo_rows_in_output(self, parsed):
        df, _ = parsed
        # The "Saldo" row should not leak through
        assert not (df["tipo"].astype(str).str.lower() == "saldo").any()


class TestBBExtratoConta:
    """BB Janeiro: Sicoob-shaped layout (header on row 1, PT-BR money strings)."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return bb.parse(FIXTURES / "Extrato BB - Janeiro.xlsx")

    def test_loads_rows(self, parsed):
        df, _ = parsed
        assert len(df) > 0
        assert (df["source"] == "bb").all()

    def test_saldo_anterior(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] is not None
        assert abs(s["saldo_inicial"] - 10895.21) < 0.01

    def test_no_saldo_rows_in_output(self, parsed):
        df, _ = parsed
        for tipo in df["tipo"]:
            assert "saldo" not in str(tipo).lower()

    def test_pix_normalized_no_hyphen(self, parsed):
        df, _ = parsed
        pix_tipos = df[df["tipo"].str.contains("Pix", case=False)]
        assert not pix_tipos["tipo"].str.contains(" - ").any()


class TestBBLegacy:
    """BB Outubro: legacy 'Extrato' layout with positive values + Histórico sign."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return bb.parse(FIXTURES / "Extrato BB - Outubro.xlsx")

    def test_loads_rows(self, parsed):
        df, _ = parsed
        assert len(df) >= 30
        assert (df["source"] == "bb").all()

    def test_saldo_anterior_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] is not None
        assert abs(s["saldo_inicial"] - 6521.11) < 0.01

    def test_saldo_final_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_final"] is not None
        assert abs(s["saldo_final"] - 35849.61) < 0.01

    def test_saldo_balances(self, parsed):
        """Net of all transactions == saldo_final - saldo_inicial."""
        df, s = parsed
        soma = float(df["valor"].sum())
        expected = s["saldo_final"] - s["saldo_inicial"]
        assert abs(soma - expected) < 0.02

    def test_sign_from_historico(self, parsed):
        df, _ = parsed
        enviados = df[df["tipo"].str.contains("Enviado", case=False)]
        recebidos = df[df["tipo"].str.contains("Recebido", case=False)]
        assert (enviados["valor"] < 0).all()
        assert (recebidos["valor"] > 0).all()
