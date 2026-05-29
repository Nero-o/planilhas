"""Feedback loop tests — corrections are persisted with the full final state."""
import json
from datetime import datetime

import pandas as pd

from aeco import feedback


def _row(_id="1", descricao="D", observacoes="O1", fluxo_caixa="F", empresa="Tech"):
    return {
        "_id": _id, "source": "bb", "data": datetime(2026, 3, 1),
        "tipo": "Pix Enviado", "beneficiario": "Acme", "valor": -10.0,
        "descricao": descricao, "observacoes": observacoes,
        "fluxo_caixa": fluxo_caixa, "empresa": empresa, "classifier": "rule",
    }


def test_records_full_final_classification(tmp_path):
    before = pd.DataFrame([_row(observacoes="O1")])
    after = pd.DataFrame([_row(observacoes="O2")])  # contadora fixed the obs
    path = tmp_path / "fb.jsonl"

    n = feedback.append_corrections(before, after, path)

    assert n == 1
    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert rec["changes"]["observacoes"] == {"before": "O1", "after": "O2"}
    # final carries all 4 fields, including the unchanged ones
    assert rec["final"] == {
        "descricao": "D", "observacoes": "O2",
        "fluxo_caixa": "F", "empresa": "Tech",
    }


def test_no_change_writes_nothing(tmp_path):
    before = pd.DataFrame([_row()])
    after = pd.DataFrame([_row()])
    path = tmp_path / "fb.jsonl"
    assert feedback.append_corrections(before, after, path) == 0
    assert not path.exists() or path.read_text(encoding="utf-8").strip() == ""
