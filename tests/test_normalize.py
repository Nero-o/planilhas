import pytest

from aeco.normalize import (
    make_key, normalize_key, normalize_text, normalize_tipo, parse_pt_money,
)


class TestParseMoney:
    def test_bb_credit(self):
        assert parse_pt_money("1.234,56 C") == 1234.56

    def test_bb_debit_with_negative(self):
        assert parse_pt_money("-188,80 D") == -188.80

    def test_bb_credit_with_negative_defensive(self):
        # Defensive: if string has negative sign but C suffix, treat as positive
        assert parse_pt_money("-100,00 C") == 100.00

    def test_bs2_real(self):
        assert parse_pt_money("R$ -3,56") == -3.56
        assert parse_pt_money("R$ 5.300,00") == 5300.0

    def test_passthrough_float(self):
        assert parse_pt_money(1234.56) == 1234.56

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_pt_money("not a number")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            parse_pt_money(None)


class TestNormalize:
    def test_text_collapses_whitespace(self):
        assert normalize_text("  foo   bar  ") == "foo bar"

    def test_text_handles_none(self):
        assert normalize_text(None) == ""

    def test_key_lower_and_ascii(self):
        assert normalize_key("João  da Silva") == "joao da silva"

    def test_tipo_collapses_hyphen(self):
        assert normalize_tipo("Pix - Recebido") == "Pix Recebido"
        assert normalize_tipo("PIX - Enviado") == "PIX Enviado"
        # Already normalized stays the same
        assert normalize_tipo("Pix Recebido") == "Pix Recebido"

    def test_make_key_consistent_across_tipo_variants(self):
        # BB produces "Pix Recebido", master may have "Pix - Recebido"
        k1 = make_key("Pix Recebido", "AECO Securitizadora")
        k2 = make_key("Pix - Recebido", "AECO Securitizadora")
        assert k1 == k2 == "pix recebido||aeco securitizadora"
