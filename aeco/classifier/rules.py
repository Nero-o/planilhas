"""Deterministic classification via the dictionary.

Mutates the Transaction in place with proposed classification + confidence.
"""
from rapidfuzz import fuzz

from ..normalize import make_key, normalize_key, normalize_tipo
from ..schema import Transaction


_FUZZY_THRESHOLD = 88  # token_set_ratio cutoff


def _apply_classification(tx: Transaction, classification: dict) -> None:
    tx.descricao = classification.get("descricao")
    tx.observacoes = classification.get("observacoes")
    tx.fluxo_caixa = classification.get("fluxo_caixa")
    tx.empresa = classification.get("empresa")


def _fuzzy_lookup(tx: Transaction, dictionary: dict) -> tuple[str, dict, str] | None:
    """If exact key missing, try prefix and fuzzy match within the same tipo.

    Returns (matched_key, entry, match_kind) or None.
    """
    tipo_norm = normalize_key(normalize_tipo(tx.tipo))
    benef_norm = normalize_key(tx.beneficiario)
    if not benef_norm:
        return None

    candidates = []
    for k, e in dictionary["entries"].items():
        k_tipo, _, k_benef = k.partition("||")
        if k_tipo != tipo_norm:
            continue
        # Prefix match in either direction (Sicoob truncates ~25 chars)
        if k_benef.startswith(benef_norm) or benef_norm.startswith(k_benef):
            return (k, e, f"prefix({k_benef})")
        score = fuzz.token_set_ratio(benef_norm, k_benef)
        if score >= _FUZZY_THRESHOLD:
            candidates.append((score, k, e))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        score, k, e = candidates[0]
        return (k, e, f"fuzzy({score})")
    return None


def classify_rule(tx: Transaction, dictionary: dict) -> Transaction:
    key = make_key(tx.tipo, tx.beneficiario)
    entry = dictionary["entries"].get(key)
    match_kind = "exact_key"

    if entry is None:
        found = _fuzzy_lookup(tx, dictionary)
        if found is not None:
            key, entry, match_kind = found

    if entry is None:
        tx.confidence = "red"
        tx.reasoning = f"no_match_in_dict({key})"
        return tx

    mode = entry["mode"]
    if mode == "exact":
        _apply_classification(tx, entry["classification"])
        consistency = entry.get("consistency", 1.0)
        # Fuzzy/prefix matches downgrade confidence one notch
        if match_kind == "exact_key" and consistency >= 0.95:
            tx.confidence = "green"
        else:
            tx.confidence = "yellow"
        tx.reasoning = f"rule:exact(n={entry['n']},c={consistency:.2f},{match_kind})"
        tx.classifier = "rule"
        return tx

    if mode == "value_brackets":
        for b in entry["buckets"]:
            tol = b.get("tolerance", 0.01)
            if abs(tx.valor - b["valor_aprox"]) <= tol * max(abs(b["valor_aprox"]), 1.0):
                _apply_classification(tx, b["classification"])
                tx.confidence = "green"
                tx.reasoning = f"rule:value_bucket({b['valor_aprox']:.2f}, n={b.get('n','?')})"
                tx.classifier = "rule"
                return tx
        # No bucket matched — open question, send to LLM
        tx.confidence = "red"
        tx.reasoning = f"value_bracket_miss(valor={tx.valor:.2f}; buckets={[b['valor_aprox'] for b in entry['buckets']]})"
        return tx

    # ambiguous: leave for human review with hint
    alts = entry.get("top_alternatives", [])[:3]
    summary = "; ".join(
        f"n={a['n']} -> {a['classification'].get('empresa','?')}/{a['classification'].get('observacoes','?')}"
        for a in alts
    )
    tx.confidence = "red"
    tx.reasoning = f"ambiguous: confira no DARF/e-mail. Hist: [{summary}]"
    return tx
