from __future__ import annotations

import re


REGIONS = (
    "Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna", "Friuli-Venezia Giulia",
    "Lazio", "Liguria", "Lombardia", "Marche", "Molise", "Piemonte", "Puglia", "Sardegna",
    "Sicilia", "Toscana", "Trentino-Alto Adige", "Umbria", "Valle d'Aosta", "Veneto",
)


def split_regions(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values or ():
        for part in re.split(r"[,;|]", str(raw)):
            value = re.sub(r"\s+", " ", part).strip()
            if not value:
                continue
            value = re.sub(r"^(regione|region|provincia autonoma di)\s+", "", value, flags=re.IGNORECASE).strip()
            match = next((region for region in REGIONS if region.lower() == value.lower()), None)
            normalized = match or value
            if normalized not in result:
                result.append(normalized)
    return tuple(result)


def normalize_territory(regions: tuple[str, ...] = (), scope: str | None = None, *, fallback: str | None = None) -> str | None:
    normalized = split_regions(regions)
    if len(normalized) == 1:
        return normalized[0]
    folded_scope = (scope or "").lower()
    if len(normalized) > 1 or any(token in folded_scope for token in ("multi", "nazionale", "tutta italia", "italia")):
        return "Multi-regione" if len(normalized) > 1 else "Italia"
    if fallback:
        return fallback
    return None
