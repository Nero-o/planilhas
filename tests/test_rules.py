"""Rule classifier tests."""
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from aeco import classifier
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

    def test_review_field_bucket_is_yellow_with_base_obs(self):
        # AECO Sec reembolso: value recurs but the observação suffix (emission)
        # rotates. Fill the shared stem, leave the rest for the contadora.
        d = _dict({
            "pix recebido||aeco securitizadora": {
                "mode": "value_brackets", "n": 32,
                "buckets": [
                    {"valor_aprox": 350.0, "tolerance": 0.01, "n": 32,
                     "review_fields": ["observacoes"],
                     "observacoes_variants": [
                         {"observacoes": "Contabilidade - PS - 4ª Emissão", "n": 10},
                         {"observacoes": "Contabilidade - PS - 6ª Emissão", "n": 9},
                     ],
                     "classification": {"descricao": "Reembolso de Despesas",
                                        "observacoes": "Contabilidade - PS",
                                        "fluxo_caixa": "Reembolso de Despesas",
                                        "empresa": "PS"}},
                ],
            }
        })
        tx = _tx(tipo="Pix Recebido", benef="AECO Securitizadora", valor=350.0)
        classify_rule(tx, d)
        assert tx.confidence == "yellow"
        assert tx.observacoes == "Contabilidade - PS"
        assert tx.empresa == "PS"
        assert tx.classifier == "rule"
        assert "revisar" in tx.reasoning
        assert "['observacoes']" in tx.reasoning
        # Historical variants surfaced so the contadora can pick the emission.
        assert "Contabilidade - PS - 4ª Emissão(n=10)" in tx.reasoning

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
    def test_consensus_on_non_empresa_autofills_yellow(self):
        # Two empresas (Sec/Tech) share the same vendor with the same descricao/
        # observacoes/fluxo_caixa. Only empresa differs — rules can auto-fill
        # the three agreed fields and leave empresa as best guess (highest n).
        d = _dict({
            "pix enviado||microsoft": {
                "mode": "ambiguous", "n": 12,
                "top_alternatives": [
                    {"n": 8, "classification": {
                        "descricao": "Despesas com Vendas",
                        "observacoes": "Software Marketing",
                        "fluxo_caixa": "Despesas Gerais e Administrativas",
                        "empresa": "Sec",
                    }},
                    {"n": 4, "classification": {
                        "descricao": "Despesas com Vendas",
                        "observacoes": "Software Marketing",
                        "fluxo_caixa": "Despesas Gerais e Administrativas",
                        "empresa": "Tech",
                    }},
                ],
            }
        })
        tx = _tx(tipo="Pix Enviado", benef="Microsoft", valor=-1000)
        classify_rule(tx, d)
        assert tx.confidence == "yellow"
        assert tx.descricao == "Despesas com Vendas"
        assert tx.observacoes == "Software Marketing"
        assert tx.fluxo_caixa == "Despesas Gerais e Administrativas"
        assert tx.empresa == "Sec"  # highest-n alternative
        assert tx.classifier == "rule"
        assert tx.reasoning.startswith("ambiguous_auto_filled")

    def test_discord_on_fluxo_stays_red(self):
        # Alternatives disagree on fluxo_caixa — cannot auto-fill, stays red
        # so the LLM gets a chance to decide.
        d = _dict({
            "pix enviado||receita federal": {
                "mode": "ambiguous", "n": 40,
                "top_alternatives": [
                    {"n": 29, "classification": {
                        "descricao": "Impostos",
                        "observacoes": "PIS/COFINS",
                        "fluxo_caixa": "Impostos Sec",
                        "empresa": "Sec",
                    }},
                    {"n": 6, "classification": {
                        "descricao": "Impostos",
                        "observacoes": "DARF",
                        "fluxo_caixa": "Impostos Tech",
                        "empresa": "Tech",
                    }},
                ],
            }
        })
        tx = _tx(tipo="Pix Enviado", benef="Receita Federal", valor=-100)
        classify_rule(tx, d)
        assert tx.confidence == "red"
        assert tx.reasoning.startswith("ambiguous_partial")
        # Discordant fields stay blank so the LLM (or a human) can decide.
        assert tx.observacoes is None
        assert tx.fluxo_caixa is None


class TestNoMatch:
    def test_unknown_key_is_red(self):
        d = _dict({})
        tx = _tx(benef="Some Random New Vendor That Never Appeared")
        classify_rule(tx, d)
        assert tx.confidence == "red"
        assert "no_match" in tx.reasoning


class TestOrchestratorLLMInvocation:
    def _df_one(self, tipo="Pix Enviado", benef="Receita Federal", valor=-100.0):
        return pd.DataFrame([{
            "source": "bs2",
            "raw_row": {},
            "data": datetime(2026, 5, 15),
            "tipo": tipo,
            "beneficiario": benef,
            "valor": valor,
        }])

    def test_llm_called_on_ambiguous_discord(self):
        d = _dict({
            "pix enviado||receita federal": {
                "mode": "ambiguous", "n": 40,
                "top_alternatives": [
                    {"n": 29, "classification": {
                        "descricao": "Impostos", "observacoes": "PIS/COFINS",
                        "fluxo_caixa": "Impostos Sec", "empresa": "Sec",
                    }},
                    {"n": 6, "classification": {
                        "descricao": "Impostos", "observacoes": "DARF",
                        "fluxo_caixa": "Impostos Tech", "empresa": "Tech",
                    }},
                ],
            }
        })
        df = self._df_one()

        def fake_enrich(tx, dictionary, examples_cache):
            tx.descricao = "Impostos"
            tx.observacoes = "DARF"
            tx.fluxo_caixa = "Impostos Tech"
            tx.empresa = "Tech"
            tx.confidence = "yellow"
            tx.reasoning = "llm: fake"

        with patch.object(classifier, "_llm") as mock_llm:
            mock_llm.return_value.build_examples_block.return_value = ""
            mock_llm.return_value.enrich_with_llm.side_effect = fake_enrich
            out = classifier.classify(df, d, use_llm=True)

        assert mock_llm.return_value.enrich_with_llm.call_count == 1
        row = out.iloc[0]
        assert row["empresa"] == "Tech"
        assert row["classifier"] == "llm"

    def test_llm_skipped_when_consensus_autofilled(self):
        d = _dict({
            "pix enviado||microsoft": {
                "mode": "ambiguous", "n": 12,
                "top_alternatives": [
                    {"n": 8, "classification": {
                        "descricao": "Despesas com Vendas",
                        "observacoes": "Software Marketing",
                        "fluxo_caixa": "Despesas Gerais e Administrativas",
                        "empresa": "Sec",
                    }},
                    {"n": 4, "classification": {
                        "descricao": "Despesas com Vendas",
                        "observacoes": "Software Marketing",
                        "fluxo_caixa": "Despesas Gerais e Administrativas",
                        "empresa": "Tech",
                    }},
                ],
            }
        })
        df = self._df_one(benef="Microsoft", valor=-1000)

        with patch.object(classifier, "_llm") as mock_llm:
            out = classifier.classify(df, d, use_llm=True)

        mock_llm.return_value.enrich_with_llm.assert_not_called()
        row = out.iloc[0]
        assert row["confidence"] == "yellow"
        assert row["descricao"] == "Despesas com Vendas"
        assert row["classifier"] == "rule"


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
