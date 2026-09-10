"""Conservative euro parsing; public budgets are expressed in whole euros."""
import re
from decimal import Decimal, InvalidOperation


def parse_money(value: str) -> int | None:
    token = re.sub(r"\s+", "", str(value)).strip()
    token = re.sub(r"(?i)EUR(?:O)?|€", "", token)
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", token):
        return None
    if "," in token and "." in token:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        token = token.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in token or "." in token:
        separator = "," if "," in token else "."
        parts = token.split(separator)
        if all(len(part) == 3 for part in parts[1:]):
            token = "".join(parts)
        elif len(parts) == 2 and len(parts[-1]) <= 2:
            token = token.replace(separator, ".")
        else:
            return None
    try:
        return int(Decimal(token))
    except InvalidOperation:
        return None


def extract_money(text: str) -> int | None:
    # Require currency evidence: a year after "finanziamento" is not money.
    number = r"(\d+(?:[.,]\d+)*(?:[ ]\d{3})*)"
    scale = r"(?:\s*(milioni?|miliardi?|mila))?"
    patterns = (r"(?:€|\beur\b|\beuro\b)\s*" + number + scale,
                number + scale + r"\s*(?:di\s+)?(?:euro\b|eur\b|€)")
    matches = sorted((match for pattern in patterns for match in re.finditer(pattern, text, re.IGNORECASE)), key=lambda match: match.start())
    # Prefer an explicit overall allocation over per-project thresholds.
    totals = [match for match in matches if re.search(r"(?:dotazione|budget|stanziamento|sostegno\s+fornito)[^.;]{0,80}$", text[max(0, match.start() - 100):match.start()], re.IGNORECASE)]
    if totals:
        matches = totals
    elif len(matches) > 1 and re.search(r"contributo\s+(?:minimo|massimo)|linea\s+[AB]\b", text, re.IGNORECASE):
        return None  # A grant range is not a total budget.
    for match in matches:
        if match:
            multiplier = {"milione": 1000000, "milioni": 1000000,
                          "miliardo": 1000000000, "miliardi": 1000000000, "mila": 1000}.get((match[2] or "").lower(), 1)
            if multiplier != 1:
                try:
                    return int(Decimal(match[1].replace(",", ".")) * multiplier)
                except InvalidOperation:
                    return None
            return parse_money(match[1])
    return None
