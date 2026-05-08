"""LLM classifier using Claude Sonnet 4.6 with prompt caching."""
import os
from typing import Any

from ..normalize import make_key
from ..schema import Transaction
from .prompts import SYSTEM_PROMPT, build_examples_block, build_user_message


MODEL = "claude-sonnet-4-6"


_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        import anthropic
        _CLIENT = anthropic.Anthropic()
    return _CLIENT


def _build_tool(dictionary: dict) -> dict:
    return {
        "name": "classify_transaction",
        "description": "Classifica um lançamento financeiro nas 4 dimensões gerenciais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "descricao": {"type": "string"},
                "observacoes": {"type": "string"},
                "fluxo_caixa": {
                    "type": "string",
                    "enum": dictionary["categories"]["fluxo_caixa"],
                },
                "empresa": {
                    "type": "string",
                    "enum": dictionary["categories"]["empresa"],
                },
                "confidence": {"type": "string", "enum": ["green", "yellow", "red"]},
                "reasoning": {"type": "string"},
            },
            "required": [
                "descricao", "observacoes", "fluxo_caixa", "empresa",
                "confidence", "reasoning",
            ],
        },
    }


def enrich_with_llm(tx: Transaction, dictionary: dict, examples_cache: str) -> None:
    """Call Claude to fill in classification for a hard-to-classify transaction.

    Mutates `tx` in place. Raises on API errors (caller wraps).
    """
    key = make_key(tx.tipo, tx.beneficiario)
    entry = dictionary["entries"].get(key, {})
    alts = entry.get("top_alternatives") if entry.get("mode") == "ambiguous" else None

    tool = _build_tool(dictionary)

    resp = _client().messages.create(
        model=MODEL,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": examples_cache,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        tools=[tool],
        tool_choice={"type": "tool", "name": "classify_transaction"},
        messages=[{"role": "user", "content": build_user_message(tx, alts)}],
    )

    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("LLM did not return a tool_use block")
    out = block.input
    tx.descricao = out["descricao"]
    tx.observacoes = out["observacoes"]
    tx.fluxo_caixa = out["fluxo_caixa"]
    tx.empresa = out["empresa"]
    tx.confidence = out["confidence"]
    tx.reasoning = f"llm: {out['reasoning']}"
