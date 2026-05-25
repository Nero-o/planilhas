"""Classifier orchestration: deterministic rules first, LLM for misses."""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

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


def classify(
    df: pd.DataFrame,
    dictionary: dict,
    *,
    use_llm: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Classify a DataFrame of raw transactions against the dictionary.

    LLM enrichment for red rows runs in parallel (ThreadPoolExecutor) — concurrency
    via AECO_LLM_CONCURRENCY env var (default 8). `on_progress(done, total)` is
    invoked after each LLM call completes (called from worker threads).

    Returns a new DataFrame with all Transaction fields populated.
    """
    if df.empty:
        return df

    txs: list[Transaction] = []
    for _, row in df.iterrows():
        t = _row_to_tx(row)
        rules.classify_rule(t, dictionary)
        txs.append(t)

    if use_llm:
        red_idx = [i for i, t in enumerate(txs) if t.confidence == "red"]
        if red_idx:
            examples_cache = _llm().build_examples_block(dictionary)
            max_workers = int(os.getenv("AECO_LLM_CONCURRENCY", "8"))
            total = len(red_idx)
            done = 0

            def _enrich(i: int) -> int:
                try:
                    _llm().enrich_with_llm(txs[i], dictionary, examples_cache)
                    txs[i].classifier = "llm"
                except Exception as exc:  # noqa: BLE001
                    txs[i].reasoning = f"{txs[i].reasoning} | llm_error: {exc}"
                return i

            with ThreadPoolExecutor(max_workers=min(max_workers, total)) as pool:
                for _ in as_completed(pool.submit(_enrich, i) for i in red_idx):
                    done += 1
                    if on_progress is not None:
                        on_progress(done, total)

    return pd.DataFrame([t.to_dict() for t in txs])
