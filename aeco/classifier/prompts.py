"""Prompt builders for the LLM classifier."""
import json
import random


SYSTEM_PROMPT = """Você é um assistente de contabilidade gerencial da AECO Capital.
Sua tarefa é classificar lançamentos financeiros em 4 dimensões para a contadora:
descricao, observacoes, fluxo_caixa, empresa.

REGRAS:
1. fluxo_caixa DEVE ser exatamente uma das opções do enum (não invente categorias).
2. empresa DEVE ser exatamente uma de: AECO, Bravo, Cons, Igor, Matriz, PS, Sec, Tech.
3. descricao e observacoes preferem reusar valores que já apareceram (lista quase fechada);
   só crie novo se o lançamento for genuinamente único.
4. Se valor é positivo (entrada), fluxo costuma ser Receita_*/Aporte/Recebimento.
   Se negativo (saída), fluxo é Despesas/Custos/Impostos.
5. Quando incerto, escolha a opção mais plausível e marque confidence=red com explicação.

CASOS RECORRENTES (heurísticas):
- AECO Securitizadora 350,00 -> Reembolso PS / Contabilidade
- AECO Securitizadora 12.113,27 -> Receita Emissões / Taxa Adm CRI 5ª (empresa=Sec)
- Receita Federal Pix Enviado -> Impostos e Taxas / DARF (empresa varia, confira valor)
- Tarifa OPERAÇÕES PIX -> Despesas Bancárias / Despesas Adm / empresa=Tech
- Pix Enviado para nome de pessoa -> usualmente Salário (verifique histórico do beneficiário)
- Compra/IOF Conta Simples -> Software/Marketing/Servidor (usar Categoria do raw_row)
"""


def build_examples_block(dictionary: dict, n_per_fluxo: int = 2) -> str:
    """Sample 1-2 examples per fluxo_caixa, balanced. Cached per session."""
    rng = random.Random(42)
    examples_by_fluxo: dict[str, list[dict]] = {}
    for key, entry in dictionary["entries"].items():
        if entry["mode"] == "exact":
            cls = entry["classification"]
        elif entry["mode"] == "value_brackets":
            cls = entry["buckets"][0]["classification"]
        else:
            continue
        fluxo = cls.get("fluxo_caixa") or "_unknown"
        examples_by_fluxo.setdefault(fluxo, []).append({
            "key": key,
            "n": entry["n"],
            "classification": cls,
        })

    sampled = []
    for fluxo, items in sorted(examples_by_fluxo.items()):
        items.sort(key=lambda x: -x["n"])
        sampled.extend(items[:n_per_fluxo])

    text = "EXEMPLOS DE LANÇAMENTOS JÁ CLASSIFICADOS NO HISTÓRICO\n"
    text += "(formato: [tipo||beneficiario] (n=ocorrencias) -> classificacao)\n\n"
    for ex in sampled:
        text += f"[{ex['key']}] (n={ex['n']}) -> {json.dumps(ex['classification'], ensure_ascii=False)}\n"
    return text


def build_user_message(tx, key_alts: list[dict] | None = None) -> str:
    alts_text = json.dumps(key_alts or [], ensure_ascii=False, indent=2)
    return f"""Lançamento a classificar:
- Data: {tx.data:%d/%m/%Y}
- Tipo: {tx.tipo}
- Beneficiário: {tx.beneficiario}
- Valor: {tx.valor:.2f}
- Fonte: {tx.source}
- Contexto bruto: {json.dumps(tx.raw_row, ensure_ascii=False, default=str)}

Alternativas históricas para a chave (Tipo+Beneficiário), se houver:
{alts_text}

Decida com base no histórico, no valor e no contexto. Se nenhuma alternativa
bater bem, escolha a opção mais provável e marque confidence=red explicando
o porquê em reasoning.
"""
