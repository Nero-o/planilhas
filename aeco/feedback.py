"""Feedback loop: persist contadora corrections to feedback.jsonl."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


CLASS_COLS = ("descricao", "observacoes", "fluxo_caixa", "empresa")


def append_corrections(
    before: pd.DataFrame,
    after: pd.DataFrame,
    path: str | Path = "data/feedback.jsonl",
) -> int:
    """Append rows where any of the 4 classification fields changed.

    Returns the count of corrections written.
    """
    if before.empty or after.empty:
        return 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    merged = after.merge(
        before[["_id", *CLASS_COLS]],
        on="_id", suffixes=("_after", "_before"),
        how="inner",
    )
    n = 0
    with open(path, "a", encoding="utf-8") as f:
        for r in merged.itertuples():
            changed = {}
            for c in CLASS_COLS:
                a = getattr(r, f"{c}_after")
                b = getattr(r, f"{c}_before")
                if (a or "") != (b or ""):
                    changed[c] = {"before": b, "after": a}
            if not changed:
                continue
            f.write(json.dumps({
                "ts": datetime.utcnow().isoformat(),
                "tipo": r.tipo,
                "beneficiario": r.beneficiario,
                "valor": float(r.valor),
                "source": r.source,
                "classifier": r.classifier,
                "changes": changed,
            }, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n
