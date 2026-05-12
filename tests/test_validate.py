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
            {"source": "sicoob", "data": datetime(2026, 3, 1), "tipo": "Pix",
             "beneficiario": "X", "valor": 100.0},
            {"source": "sicoob", "data": datetime(2026, 3, 2), "tipo": "Pix",
             "beneficiario": "Y", "valor": -50.0},
        ])
        saldos = {"sicoob": {"saldo_inicial": 1000.0, "saldo_final": 1050.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["sicoob"]["ok"] is True
        assert res["saldo"]["sicoob"]["diferenca"] == 0.0

    def test_imbalanced_returns_failure(self):
        df = _df([
            {"source": "bs2", "data": datetime(2026, 3, 1), "tipo": "Pix",
             "beneficiario": "X", "valor": 100.0},
        ])
        saldos = {"bs2": {"saldo_inicial": 1000.0, "saldo_final": 1500.0}}
        res = validate.run(df, saldos)
        assert res["saldo"]["bs2"]["ok"] is False
        assert res["saldo"]["bs2"]["diferenca"] == -400.0


class TestCounts:
    def test_counts_per_confidence(self):
        df = pd.DataFrame([
            {"_id": "a", "source": "sicoob", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "green"},
            {"_id": "b", "source": "sicoob", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "yellow"},
            {"_id": "c", "source": "sicoob", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "red"},
            {"_id": "d", "source": "sicoob", "data": datetime(2026, 3, 1),
             "tipo": "X", "beneficiario": "Y", "valor": 1.0, "confidence": "red"},
        ])
        res = validate.run(df, {})
        assert res["counts"]["total"] == 4
        assert res["counts"]["green"] == 1
        assert res["counts"]["yellow"] == 1
        assert res["counts"]["red"] == 2
