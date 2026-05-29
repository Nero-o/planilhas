"""Dictionary builder tests — value-bracket review fields, common base, and
the feedback-ingestion loop."""
import json
from datetime import datetime

import openpyxl

from aeco import dictionary as dictmod
from aeco.dictionary import _common_base, _decide_mode, _iter_feedback_rows


def _write_master(path, rows, sheet="SEC"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["Data", "Tipo de Pagamento", "Beneficiário", "Descrição",
               "Observações", "Fluxo de Caixa", "Valor", "Empresa"])
    for r in rows:
        ws.append(r)
    wb.save(path)


def _fb_line(tipo, benef, valor, final):
    return json.dumps({
        "ts": "x", "tipo": tipo, "beneficiario": benef, "valor": valor,
        "source": "bb", "classifier": "llm", "changes": {}, "final": final,
    }, ensure_ascii=False)


class TestCommonBase:
    def test_shared_stem_with_rotating_suffix(self):
        variants = [
            "Contabilidade - PS",
            "Contabilidade - PS - 4ª Emissão",
            "Contabilidade - PS - 6ª Emissão",
            "Contabilidade - PS - 2ª Emissão",
        ]
        assert _common_base(variants) == "Contabilidade - PS"

    def test_trailing_separator_is_trimmed(self):
        variants = [
            "Contabilidade - PS - 4ª Emissão",
            "Contabilidade - PS - 6ª Emissão",
        ]
        # LCP is "Contabilidade - PS - " — dangling separator gets trimmed.
        assert _common_base(variants) == "Contabilidade - PS"

    def test_no_common_prefix_returns_empty(self):
        assert _common_base(["Reembolso - Contabilidade", "Spread - Série 10"]) == ""

    def test_ignores_blanks_and_non_strings(self):
        assert _common_base(["Taxa", "Taxa - X", None, ""]) == "Taxa"


class TestDecideModeReview:
    def test_recurring_value_with_rotating_obs_flags_review(self):
        # descricao/fluxo/empresa stable; observação rotates by emission at the
        # same value → value_brackets bucket fills the stem and flags review.
        stem = "Reembolso de Despesas"
        by_cls = {
            (stem, "Contabilidade - PS - 4ª Emissão", stem, "PS"): [350.0] * 4,
            (stem, "Contabilidade - PS - 6ª Emissão", stem, "PS"): [350.0] * 3,
            (stem, "Reembolso - Custodiante", stem, "PS"): [2724.0, 2724.0],
        }
        out = _decide_mode(by_cls)
        assert out["mode"] == "value_brackets"
        b350 = next(b for b in out["buckets"] if abs(b["valor_aprox"] - 350.0) < 0.01)
        assert b350["review_fields"] == ["observacoes"]
        assert b350["classification"]["observacoes"] == "Contabilidade - PS"
        assert b350["classification"]["empresa"] == "PS"
        assert {v["observacoes"] for v in b350["observacoes_variants"]} == {
            "Contabilidade - PS - 4ª Emissão",
            "Contabilidade - PS - 6ª Emissão",
        }
        # A value that maps to a single observação stays confident (no review).
        b2724 = next(b for b in out["buckets"] if abs(b["valor_aprox"] - 2724.0) < 0.01)
        assert "review_fields" not in b2724
        assert b2724["classification"]["observacoes"] == "Reembolso - Custodiante"


class TestFeedbackIngestion:
    def test_iter_feedback_weight_and_skips(self, tmp_path):
        fb = tmp_path / "fb.jsonl"
        ok = {"descricao": "D", "observacoes": "O", "fluxo_caixa": "F", "empresa": "Tech"}
        lines = [
            _fb_line("Pix", "A", 10.0, ok),
            json.dumps({"tipo": "Pix", "beneficiario": "B", "changes": {}}),  # no 'final'
            _fb_line("Pix", "C", 5.0, {**ok, "empresa": ""}),  # empty empresa → skip
            "",                                                # blank line
            "{not valid json",                                 # malformed → skip
        ]
        fb.write_text("\n".join(lines) + "\n", encoding="utf-8")

        rows = list(_iter_feedback_rows(str(fb), weight=3))

        # only the first record qualifies, emitted 3× (the weight)
        assert len(rows) == 3
        key, valor, cls = rows[0]
        assert key == "pix||a"
        assert valor == 10.0
        assert cls == ("D", "O", "F", "Tech")

    def test_iter_feedback_missing_file_is_empty(self, tmp_path):
        assert list(_iter_feedback_rows(str(tmp_path / "nope.jsonl"))) == []

    def test_feedback_creates_rule_for_new_key(self, tmp_path):
        master = tmp_path / "m.xlsx"
        _write_master(master, [
            [datetime(2026, 1, 1), "Pix Enviado", "Existing", "D", "O", "F", 100.0, "Tech"],
        ])
        fb = tmp_path / "fb.jsonl"
        fb.write_text(_fb_line(
            "Pix Recebido", "NovoForn", 2724.0,
            {"descricao": "Reembolso de Despesas", "observacoes": "Reembolso - Custodiante",
             "fluxo_caixa": "Reembolso de Despesas", "empresa": "PS"},
        ) + "\n", encoding="utf-8")

        d = dictmod.build(str(master), feedback_path=str(fb))

        e = d["entries"]["pix recebido||novoforn"]
        assert e["mode"] == "exact"
        assert e["n"] == dictmod.FEEDBACK_WEIGHT  # correction counts as N rows
        assert e["classification"]["observacoes"] == "Reembolso - Custodiante"
        assert e["classification"]["empresa"] == "PS"
        # master-only key is still present and untouched
        assert "pix enviado||existing" in d["entries"]

    def test_build_without_feedback_excludes_corrections(self, tmp_path):
        master = tmp_path / "m.xlsx"
        _write_master(master, [
            [datetime(2026, 1, 1), "Pix Enviado", "Existing", "D", "O", "F", 100.0, "Tech"],
        ])
        # feedback file exists but is not passed → corrections must be ignored
        fb = tmp_path / "fb.jsonl"
        fb.write_text(_fb_line("Pix Recebido", "NovoForn", 1.0,
                               {"descricao": "X", "observacoes": "Y",
                                "fluxo_caixa": "Z", "empresa": "PS"}) + "\n", encoding="utf-8")

        d = dictmod.build(str(master))

        assert "pix recebido||novoforn" not in d["entries"]
