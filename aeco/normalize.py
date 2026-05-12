import re
from unidecode import unidecode


_MONEY_RE = re.compile(r"^\s*(R\$\s*)?(-?)([\d\.]+),(\d{2})\s*([CD])?\s*$")


def parse_pt_money(s) -> float:
    """Parse PT-BR money strings.

    Examples:
        "1.234,56 C"  -> 1234.56
        "-188,80 D"   -> -188.80
        "R$ -3,56"    -> -3.56
        "R$ 5.300,00" -> 5300.00
    """
    if s is None:
        raise ValueError("empty money value")
    if isinstance(s, (int, float)):
        return round(float(s), 2)
    text = str(s).strip()
    m = _MONEY_RE.match(text)
    if not m:
        raise ValueError(f"unparseable money: {text!r}")
    _, sign, intp, dec, cd = m.groups()
    val = float(f"{intp.replace('.', '')}.{dec}")
    if sign == "-":
        val = -val
    if cd == "D" and val > 0:
        val = -val
    if cd == "C" and val < 0:
        val = abs(val)
    return round(val, 2)


def normalize_text(s) -> str:
    """Trim, collapse whitespace. Preserves case and accents."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip())


def normalize_key(s) -> str:
    """For dictionary key matching: lower + ASCII + collapsed whitespace."""
    return re.sub(r"\s+", " ", unidecode(normalize_text(s)).lower()).strip()


def normalize_tipo(s) -> str:
    """Collapse Sicoob hyphenated variants: 'Pix - Recebido' -> 'Pix Recebido'.

    Applied in BOTH parsers and dictionary builder so keys match.
    """
    return normalize_text(str(s or "").replace(" - ", " "))


def make_key(tipo: str, beneficiario: str) -> str:
    return f"{normalize_key(normalize_tipo(tipo))}||{normalize_key(beneficiario)}"
