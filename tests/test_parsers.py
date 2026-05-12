"""Parser tests using fixtures captured from real 03/2026 extracts."""
from pathlib import Path

import pytest

from aeco.parsers import bs2, c6, conta_simples, sicoob


FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"


class TestSicoob:
    @pytest.fixture(scope="class")
    def parsed(self):
        return sicoob.parse(FIXTURES / "sicoob_032026.xlsx")

    def test_saldos_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] == 28155.41
        assert s["saldo_final"] == 48525.09

    def test_saldo_balances(self, parsed):
        df, s = parsed
        soma = df["valor"].sum()
        expected = s["saldo_final"] - s["saldo_inicial"]
        assert abs(soma - expected) < 0.01

    def test_row_count(self, parsed):
        df, _ = parsed
        # 49 transactions in the 03/2026 extract (excluding 1 saldo anterior + 18 saldos do dia + 1 final saldo = 19 saldo rows)
        assert len(df) == 49

    def test_no_saldo_rows_in_output(self, parsed):
        df, _ = parsed
        for tipo in df["tipo"]:
            assert "saldo" not in tipo.lower()
            assert "S A L D O" not in tipo

    def test_pix_normalized(self, parsed):
        df, _ = parsed
        # Sicoob writes "Pix - Recebido"; parser collapses to "Pix Recebido"
        assert "Pix Recebido" in df["tipo"].values
        assert "Pix - Recebido" not in df["tipo"].values

    def test_beneficiario_extracted_from_pix_detail(self, parsed):
        df, _ = parsed
        # Detail like "02/03 14:21 52875482000127 AECO SECURI"
        # -> beneficiario should be "AECO SECURI" (truncation by the bank)
        first = df[df["tipo"] == "Pix Recebido"].iloc[0]
        assert "AECO" in first["beneficiario"]
        # The leading datetime + CNPJ must be stripped
        assert not first["beneficiario"].startswith("02/03")
        assert "52875" not in first["beneficiario"]


class TestBs2:
    @pytest.fixture(scope="class")
    def parsed(self):
        return bs2.parse(FIXTURES / "bs2_032026.csv")

    def test_saldos_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] == 39019.56
        assert s["saldo_final"] == 49027.17

    def test_row_count(self, parsed):
        df, _ = parsed
        assert len(df) == 26

    def test_pix_beneficiario_extracted(self, parsed):
        df, _ = parsed
        # "Débito PIX - 00712125906 - ZILDA APARECIDA DE MATOS"
        zilda = df[df["beneficiario"].str.contains("ZILDA", na=False)]
        assert len(zilda) == 1
        assert zilda.iloc[0]["valor"] == -400.0


class TestContaSimples:
    @pytest.fixture(scope="class")
    def parsed(self):
        return conta_simples.parse(FIXTURES / "conta_simples_032026.xlsx")

    def test_finds_header_dynamically(self, parsed):
        df, _ = parsed
        assert len(df) > 0

    def test_no_saldos(self, parsed):
        _, s = parsed
        # Cards have no balance to reconcile
        assert s == {}

    def test_estabelecimento_trimmed(self, parsed):
        df, _ = parsed
        # "MICROSOFT-G148450515     SAO PAULO    BR" -> "MICROSOFT-G148450515"
        ms = df[df["beneficiario"].str.startswith("MICROSOFT")]
        assert len(ms) > 0
        for b in ms["beneficiario"]:
            assert "SAO PAULO" not in b
            assert "BR" not in b.split()[-1] if " " in b else True

    def test_all_transactions_have_value(self, parsed):
        df, _ = parsed
        assert (df["valor"] != 0).all()


class TestC6:
    @pytest.fixture(scope="class")
    def parsed(self):
        return c6.parse(FIXTURES / "extrato-c6.xlsx")

    def test_saldo_balances(self, parsed):
        df, s = parsed
        soma = df["valor"].sum()
        expected = s["saldo_final"] - s["saldo_inicial"]
        assert abs(soma - expected) < 0.01

    def test_saldos_extracted(self, parsed):
        _, s = parsed
        assert s["saldo_inicial"] == 10930.67
        assert s["saldo_final"] == 8932.67

    def test_row_count(self, parsed):
        df, _ = parsed
        assert len(df) == 44

    def test_pix_enviado_extracted(self, parsed):
        df, _ = parsed
        aeco = df[df["beneficiario"] == "AECO SECURITIZADORA S/A"]
        assert len(aeco) >= 1
        assert (aeco["tipo"] == "Pix enviado").all()
        assert (aeco["valor"] < 0).all()

    def test_pix_recebido_extracted(self, parsed):
        df, _ = parsed
        be = df[df["beneficiario"] == "BE T06 EMPREENDIMENTO IMOBILIARIO SPE LTDA"]
        assert len(be) >= 1
        assert (be["tipo"] == "Pix recebido").all()
        assert (be["valor"] > 0).all()

    def test_no_preamble_rows(self, parsed):
        df, _ = parsed
        # Header / title rows must not leak into the dataframe.
        for tipo in df["tipo"]:
            assert "EXTRATO DE CONTA" not in tipo
            assert "Extrato gerado" not in tipo
            assert tipo != "Data Lançamento"

    def test_source_label(self, parsed):
        df, _ = parsed
        assert (df["source"] == "c6").all()

    def test_encrypted_xlsx_decrypts_with_password(self, tmp_path):
        import subprocess
        import sys
        enc = tmp_path / "encrypted.xlsx"
        subprocess.run(
            [
                sys.executable, "-m", "msoffcrypto",
                "-e", "-p", "test-pw",
                str(FIXTURES / "extrato-c6.xlsx"),
                str(enc),
            ],
            check=True,
        )
        df, s = c6.parse(enc, password="test-pw")
        assert len(df) == 44
        assert s["saldo_inicial"] == 10930.67

    def test_encrypted_xlsx_without_password_raises(self, tmp_path):
        import subprocess
        import sys
        enc = tmp_path / "encrypted.xlsx"
        subprocess.run(
            [
                sys.executable, "-m", "msoffcrypto",
                "-e", "-p", "test-pw",
                str(FIXTURES / "extrato-c6.xlsx"),
                str(enc),
            ],
            check=True,
        )
        with pytest.raises(ValueError, match="protegido por senha"):
            c6.parse(enc)

    def test_encrypted_xlsx_wrong_password_raises(self, tmp_path):
        import subprocess
        import sys
        enc = tmp_path / "encrypted.xlsx"
        subprocess.run(
            [
                sys.executable, "-m", "msoffcrypto",
                "-e", "-p", "test-pw",
                str(FIXTURES / "extrato-c6.xlsx"),
                str(enc),
            ],
            check=True,
        )
        with pytest.raises(ValueError, match="senha informada"):
            c6.parse(enc, password="wrong")
