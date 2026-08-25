from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


# Keep this table deliberately small and semantic.  Terms which are merely
# related (for example caregiver and elderly) belong to separate concepts.
SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "anziani": ("anziani", "ageing", "elderly", "older people", "older persons", "senior"),
    "adolescenti": ("adolescenti", "adolescent", "minori", "youth", "children", "young people", "giovani"),
    "scuola": ("scuola", "scolastico", "school", "studenti", "student"),
    "burnout": ("burnout", "stress lavoro", "benessere organizzativo", "workplace stress"),
    "caregiver": (
        "caregiver", "caregivers", "caregiving", "carer", "carers",
        "informal caregiver", "informal caregivers", "informal carer", "informal carers",
    ),
    "violenza": ("violenza", "abuso", "violenza di genere", "gender-based violence"),
    "dipendenze": ("dipendenze", "addiction", "substance use"),
    "salute mentale": ("salute mentale", "mental health", "benessere psicologico", "supporto psicologico", "psychological support"),
    "inclusione sociale": ("inclusione sociale", "inclusione", "vulnerabilità", "fragilità", "social exclusion"),
    "demenza": ("demenza", "dementia", "alzheimer", "alzheimers"),
    "disabilita": ("disabilità", "disabilita", "neurodiversità", "autismo", "autism"),
    "intelligenza artificiale": ("intelligenza artificiale", "artificial intelligence", "machine learning", "ai"),
    "migrazione": ("migrazione", "migranti", "migration", "migrant", "rifugiati", "refugees"),
    "lavoratori": ("lavoratori", "lavoro", "workers", "workplace", "occupazione", "employment"),
}


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text.casefold()).strip()


_NORMALIZED_SYNONYMS = {
    normalized(key): tuple(dict.fromkeys(normalized(value) for value in values))
    for key, values in SEARCH_SYNONYMS.items()
}


def term_groups(query: str) -> list[list[str]]:
    """Return OR groups for each concept, preserving AND between groups."""
    tokens = normalized(query).split()
    groups: list[list[str]] = []
    index = 0
    while index < len(tokens):
        pair = " ".join(tokens[index:index + 2])
        key = pair if pair in _NORMALIZED_SYNONYMS else tokens[index]
        groups.append(list(_NORMALIZED_SYNONYMS.get(key, (tokens[index],))))
        index += 2 if key == pair else 1
    return groups


def search_haystack(item: dict[str, Any]) -> str:
    """Fields exposed as original/source text to the user search.

    Generated macro areas are intentionally absent: the macro filter remains
    the explicit way to search classifier output.
    """
    values: list[str] = [
        str(item.get("title", "")), str(item.get("summary", "")),
        str(item.get("programme", "")), str(item.get("funder", "")),
        " ".join(str(value) for value in item.get("eligibleEntities", []) or []),
        " ".join(str(value) for value in item.get("regions", []) or []),
        " ".join(str(value) for value in item.get("sourceTags", []) or []),
        str(item.get("cleanSourceText", "")),
    ]
    return normalized(" ".join(values))


def matches_query(item: dict[str, Any], query: str) -> bool:
    haystack = search_haystack(item)
    def contains(term: str) -> bool:
        if term == "ai":
            return re.search(r"(^|[^a-z0-9])ai([^a-z0-9]|$)", haystack) is not None
        return term in haystack
    return not query.strip() or all(any(contains(term) for term in group) for group in term_groups(query))


def filter_items(items: Iterable[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return [item for item in items if matches_query(item, query)]
