"""Dictionary builder tests — value-bracket review fields and common base."""
from aeco.dictionary import _common_base, _decide_mode


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
