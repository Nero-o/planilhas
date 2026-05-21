"""Classifier orchestration: deterministic rules first, LLM for misses."""
import os
import pandas as pd

from ..schema import Transaction
from ..normalize import make_key
from . import rules


_LLM_MODULE = None


def _llm():
    """Lazy-load LLM module so the package works without anthropic installed."""
    global _LLM_MODULE
    if _LLM_MODULE is None:
        from . import llm
        _LLM_MODULE = llm
    return _LLM_MODULE


def _row_to_tx(row) -> Transaction:
    return Transaction(
        source=row["source"],
        raw_row=row["raw_row"],
        data=row["data"],
        tipo=row["tipo"],
        beneficiario=row["beneficiario"],
        valor=float(row["valor"]),
    )


def classify(df: pd.DataFrame, dictionary: dict, *, use_llm: bool = True) -> pd.DataFrame:
    """Classify a DataFrame of raw transactions against the dictionary.

    Returns a new DataFrame with all Transaction fields populated.
    """
    if df.empty:
        return df

    examples_cache = None
    out = []
    for _, row in df.iterrows():
        t = _row_to_tx(row)
        rules.classify_rule(t, dictionary)
        # LLM fills remaining red rows: true unknowns, value-bracket misses, and
        # ambiguous keys where alternatives disagreed on a non-empresa field.
        if use_llm and t.confidence == "red":
            if examples_cache is None:
                examples_cache = _llm().build_examples_block(dictionary)
            try:
                _llm().enrich_with_llm(t, dictionary, examples_cache)
                t.classifier = "llm"
            except Exception as exc:  # noqa: BLE001
                t.reasoning = f"{t.reasoning} | llm_error: {exc}"
        out.append(t.to_dict())
    return pd.DataFrame(out)
