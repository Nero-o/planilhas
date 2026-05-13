"""Rule classifier tests."""
from datetime import datetime

import pytest

from aeco.classifier.rules import classify_rule
from aeco.schema import Transaction


def _tx(tipo="Pix Enviado", benef="Joao Eduardo Felipin", valor=-2000.0):
    return Transaction(
        source="bb",
        raw_row={},
        data=datetime(2026, 3, 1),
        tipo=tipo,
        beneficiario=benef,
        valor=valor,
    )


def _dict(entries):
    return {
        "categories": {"fluxo_caixa": [], "empresa": []},
        "all_descricoes": [],
        "all_observacoes": [],
        "entries": entries,
    }


class TestExactMode:
    def test_high_consistency_is_green(self):
        d = _dict({
            "pix enviado||joao eduardo felipin": {
                "mode": "exact", "n": 24, "consistency": 1.0,
                "classification": {
                    "descricao": "Salários", "observacoes": "Salários Tech",
                    "fluxo_caixa": "Despesas com Pessoal Tech", "empresa": "Tech",
                },
            }
        })
        tx = _tx()
        classify_rule(tx, d)
        assert tx.confidence == "green"
        assert tx.empresa == "Tech"
        assert tx.fluxo_caixa == "Despesas com Pessoal Tech"

    def test_low_consistency_is_yellow(self):
        d = _dict({
            "pix enviado||joao eduardo felipin": {
                "mode": "exact", "n": 10, "consistency": 0.7,
                "classification": {
                    "descricao": "Salários", "observacoes": "Salários Tech",
                    "fluxo_caixa": "Despesas com Pessoal Tech", "empresa": "Tech",
                },
            }
        })
        tx = _tx()
        classify_rule(tx, d)
        assert tx.confidence == "yellow"


class TestValueBracketsMode:
    def test_match_bucket_is_green(self):
        d = _dict({
            "pix enviado||joao eduardo felipin": {
                "mode": "value_brackets", "n": 10,
                "buckets": [
                    {"valor_aprox": -2000.0, "tolerance": 0.01, "n": 8,
                     "classification": {"descricao": "Sal", "observacoes": "Tech",
                                        "fluxo_caixa": "F", "empresa": "Tech"}},
                    {"valor_aprox": -5818.18, "tolerance": 0.01, "n": 2,
                     "classification": {"descricao": "Aviso", "observacoes": "Aviso Previo",
                                        "fluxo_caixa": "F", "empresa": "Tech"}},
                ],
            }
        })
        tx = _tx(valor=-2000.0)
        classify_rule(tx, d)
        assert tx.confidence == "green"
        assert tx.descricao == "Sal"

        tx2 = _tx(valor=-5818.18)
        classify_rule(tx2, d)
        assert tx2.descricao == "Aviso"

    def test_no_bucket_match_is_red(self):
        d = _dict({
            "pix enviado||joao eduardo felipin": {
                "mode": "value_brackets", "n": 5,
                "buckets": [
                    {"valor_aprox": -2000.0, "tolerance": 0.01,
                     "classification": {"descricao": "X", "observacoes": "Y",
                                        "fluxo_caixa": "Z", "empresa": "Tech"}},
                ],
            }
        })
        tx = _tx(valor=-9999.0)
        classify_rule(tx, d)
        assert tx.confidence == "red"
        assert "value_bracket_miss" in tx.reasoning


class TestAmbiguousMode:
    def test_ambiguous_is_red_with_alternatives(self):
        d = _dict({
            "pix enviado||receita federal": {
                "mode": "ambiguous", "n": 40,
                "top_alternatives": [
                    {"n": 29, "classification": {"empresa": "Sec", "observacoes": "PIS/COFINS"}},
                    {"n": 6, "classification": {"empresa": "PS", "observacoes": "Outros"}},
                ],
            }
        })
        tx = _tx(tipo="Pix Enviado", benef="Receita Federal", valor=-100)
        classify_rule(tx, d)
        assert tx.confidence == "red"
        assert "ambiguous" in tx.reasoning
        assert "DARF" in tx.reasoning


class TestNoMatch:
    def test_unknown_key_is_red(self):
        d = _dict({})
        tx = _tx(benef="Some Random New Vendor That Never Appeared")
        classify_rule(tx, d)
        assert tx.confidence == "red"
        assert "no_match" in tx.reasoning


class TestFuzzyAndPrefix:
    def test_truncated_benef_matches_via_prefix(self):
        # Sicoob truncates "AECO Securitizadora" to "AECO SECURI"
        d = _dict({
            "pix recebido||aeco securitizadora": {
                "mode": "exact", "n": 10, "consistency": 1.0,
                "classification": {
                    "descricao": "Receita", "observacoes": "Taxa CRI 5",
                    "fluxo_caixa": "Receita de Emissões", "empresa": "Sec",
                },
            }
        })
        tx = _tx(tipo="Pix Recebido", benef="AECO SECURI", valor=12113.27)
        classify_rule(tx, d)
        assert tx.empresa == "Sec"
        # Prefix match downgrades to yellow
        assert tx.confidence == "yellow"
        assert "prefix" in tx.reasoning
