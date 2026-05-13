from datetime import datetime

import pandas as pd

from aeco import validate


def _df(rows):
    df = pd.DataFrame(rows)
    if "_id" not in df:
        df["_id"] = [str(i) for i in range(len(df))]
    if "confidence" not in df:
        df["confidence"] = "green"
    return df


class TestSaldoCheck:
    def test_balanced_returns_ok(self):
        df = _df([
            {"source": "bb", "data": datetime(2026, 3, 1), "tipo": "Pix",
             "beneficiario": "X", "valor": 100.0},
            {"source": "bb", "data": datetime(2026, 3, 2), "tipo": "Pix",
             "beneficiario": "Y", "valor": -50.0},
        ])
        saldos = {"bb": {"saldo_inicial": 1000.0, "saldo_final": 1050.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["bb"]["ok"] is True
        assert res["saldo"]["bb"]["diferenca"] == 0.0

    def test_imbalanced_returns_failure(self):
        df = _df([
            {"source": "bs2", "data": datetime(2026, 3, 1), "tipo": "Pix",
             "beneficiario": "X", "valor": 100.0},
        ])
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 1500.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["bs2"]["ok"] is False
        assert res["saldo"]["bs2"]["diferenca"] == -400.0


class TestSaldoWarnings:
    def test_unpaired_pgto_flagged_when_saldo_fails(self):
        # Two PGTO -178.31 with only one EST +178.31 → 04/03 PGTO unpaired,
        # saldo expects an extra +178.31 of credit.
        df = _df([
            {"source": "bs2", "data": datetime(2026, 3, 4), "tipo": "Pgto Concess/Tributo",
             "beneficiario": "DARF", "valor": -178.31},
            {"source": "bs2", "data": datetime(2026, 3, 9), "tipo": "Pgto Concess/Tributo",
             "beneficiario": "DARF", "valor": -178.31},
            {"source": "bs2", "data": datetime(2026, 3, 9), "tipo": "Est Pagto Concess/Tributo",
             "beneficiario": "DARF", "valor": 178.31},
        ])
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 821.69}}
        # expected movement = -178.31, observed = -178.31; saldo would be OK here.
        # But to simulate the real BS2 case the bank's saldo implies *both* PGTOs were estornated.
        # Adjust saldo so diff = -178.31:
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 1000.0}}
        # expected = 0, observed = -178.31, diff = -178.31
        res = validate.run(df, saldos)
        assert res["saldo"]["bs2"]["ok"] is False
        assert res["saldo"]["bs2"]["diferenca"] == -178.31
        suspects = res["saldo_warnings"]["bs2"]
        assert len(suspects) == 1
        s = suspects[0]
        assert s["valor"] == -178.31
        assert s["data"] in ("2026-03-04", "2026-03-09")  # whichever is leftover
        assert "estorn" in s["hint"].lower()

    def test_no_warning_when_saldo_ok(self):
        df = _df([
            {"source": "bs2", "data": datetime(2026, 3, 4), "tipo": "Pgto",
             "beneficiario": "X", "valor": -100.0},
        ])
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 900.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["bs2"]["ok"] is True
        assert res["saldo_warnings"] == {}

    def test_no_warning_when_no_value_matches_diff(self):
        # Saldo fails but no transaction matches the diff magnitude.
        df = _df([
            {"source": "bs2", "data": datetime(2026, 3, 4), "tipo": "Pix",
             "beneficiario": "X", "valor": -50.0},
        ])
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 500.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["bs2"]["ok"] is False
        assert "bs2" not in res["saldo_warnings"]


class TestCounts:
    def test_counts_per_confidence(self):
        df = pd.DataFrame([
            {"_id": "a", "source": "bb", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "green"},
            {"_id": "b", "source": "bb", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "yellow"},
            {"_id": "c", "source": "bb", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "red"},
            {"_id": "d", "source": "bb", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "red"},
        ])
        res = validate.run(df, {})
        assert res["counts"]["total"] == 4
        assert res["counts"]["green"] == 1
        assert res["counts"]["yellow"] == 1
        assert res["counts"]["red"] == 2
