from __future__ import annotations

import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime


MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_date(value: str | None, *, default_year: int | None = None) -> date | None:
    """Parse only unambiguous common Italian/European date representations."""

    if not value:
        return None
    candidate = re.sub(r"\s+", " ", str(value).strip()).replace("Z", "+00:00")
    for parser in (
        lambda item: datetime.fromisoformat(item).date(),
        lambda item: parsedate_to_datetime(item).date(),
        lambda item: datetime.strptime(item, "%d/%m/%Y %H:%M").date(),
        lambda item: datetime.strptime(item, "%d/%m/%Y").date(),
        lambda item: datetime.strptime(item, "%Y-%m-%d").date(),
        lambda item: datetime.strptime(item, "%B %d, %Y").date(),
        lambda item: datetime.strptime(item, "%d %B %Y").date(),
    ):
        try:
            return parser(candidate)
        except (TypeError, ValueError, OverflowError):
            continue

    match = re.search(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]+)(?:\s+(\d{4}))?\b", candidate, re.IGNORECASE)
    if match:
        month = MONTHS.get(match.group(2).lower())
        year = int(match.group(3) or default_year or 0)
        if month and year:
            try:
                return date(year, month, int(match.group(1)))
            except ValueError:
                return None

    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", candidate)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    return None
