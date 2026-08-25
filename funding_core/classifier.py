from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


MACRO_RULES = {
    "Salute mentale e benessere": ("salute mentale", "mental health", "benessere psicologico", "benessere", "psychological support", "supporto psicologico"),
    "Minori e adolescenti": ("minori", "adolescent", "youth", "children", "giovani"),
    "Scuola, università e formazione": ("scuola", "scolastic", "school", "student", "universit", "formazione"),
    "Famiglia e genitorialità": ("famiglia", "genitorial", "family", "parent"),
    "Inclusione sociale e vulnerabilità": ("inclusione sociale", "inclusione", "fragilit", "povert", "vulnerab", "social exclusion"),
    "Disabilità e neurodiversità": ("disabil", "neurodivers", "autism"),
    "Anziani, ageing e caregiver": ("anzian", "ageing", "elderly", "older people", "caregiver"),
    "Violenza, trauma e tutela": ("violenza", "trauma", "abuso", "protection"),
    "Dipendenze": ("dipendenz", "addiction", "substance use"),
    "Lavoro, organizzazioni e occupazione": ("lavor", "occupazione", "employment", "workplace", "burnout"),
    "Comunità, welfare e sviluppo territoriale": ("comunit", "welfare", "territori", "community"),
    "Salute pubblica e prevenzione": ("salute pubblica", "prevenzione", "public health", "prevention"),
    "Migrazione, integrazione e intercultura": ("migraz", "intercultur", "migrant", "refugee"),
    "Diritti, pari opportunità e contrasto alle discriminazioni": ("pari opportun", "discrimin", "gender equality", "violenza di genere", "diritti"),
    "Digitale, innovazione e AI": ("digitale", "digital", "artificial intelligence", "intelligenza artificiale", "innovazione"),
    "Ricerca e innovazione scientifica": ("ricerca", "research", "scientific"),
}

POSITIVE_SIGNALS: tuple[tuple[str, float], ...] = (
    ("supporto psicologico", 6), ("psychological support", 6), ("psicolog", 6), ("salute mentale", 6),
    ("mental health", 6), ("psychosocial", 5), ("psicoterapia", 5),
    ("benessere psicologico", 5), ("trauma", 4), ("dipendenz", 4),
    ("violenza", 3), ("adolescent", 3), ("disabil", 2), ("caregiver", 2),
    ("inclusione sociale", 2), ("prevenzione", 2), ("giovani", 1),
    ("formazione", 1), ("community", 1), ("innovazione", 0.5),
)
NEGATIVE_SIGNALS: tuple[tuple[str, float], ...] = (
    ("pmi", -4), ("impresa", -3), ("efficientamento energetico", -7),
    ("energia", -5), ("turismo", -4), ("internazionalizzazione", -4),
    ("macchinari", -5), ("commercio", -3), ("agricoltura", -3),
)
GENERIC_YOUTH_CONTEXTS = ("giovani imprese", "giovani imprenditori", "giovani aziende", "giovani startup")
# A small guard against recurring non-psychology sectors that otherwise score
# through broad words such as disabilita, inclusione or giovani.  It activates
# only when the record has no direct psychology/psychosocial signal.
NON_PSYCHOLOGY_CONTEXTS = (
    "sport", "autoveicol", "predazion", "lupo in malga", "irap", "aler ",
    "manutenzione programmata", "sponsorizzaz", "consultazion sulla futura politica",
    "premi di laurea",
)
DIRECT_PSYCHOLOGY_SIGNALS = (
    "supporto psicologico", "psychological support", "psicolog", "salute mentale",
    "mental health", "psychosocial", "psicoterapia", "benessere psicologico",
    "trauma", "dipendenz", "caregiver", "demenza",
)


@dataclass(frozen=True)
class Classification:
    macro_areas: tuple[str, ...]
    score: float
    label: str
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]


def _fold(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(char) != "Mn")


def _contains(text: str, pattern: str) -> bool:
    return _fold(pattern) in text


def classify_with_relevance(text: str) -> Classification:
    folded = _fold(re.sub(r"\s+", " ", text))
    positive: list[str] = []
    negative: list[str] = []
    score = 0.0
    for signal, weight in POSITIVE_SIGNALS:
        if signal == "giovani" and any(_contains(folded, context) for context in GENERIC_YOUTH_CONTEXTS):
            continue
        if _contains(folded, signal):
            positive.append(signal)
            score += weight
    for signal, weight in NEGATIVE_SIGNALS:
        if _contains(folded, signal):
            negative.append(signal)
            score += weight
    if any(_contains(folded, context) for context in NON_PSYCHOLOGY_CONTEXTS) and not any(_contains(folded, signal) for signal in DIRECT_PSYCHOLOGY_SIGNALS):
        negative.append("non-psychology context")
        score -= 6
    macro_areas = tuple(
        area for area, words in MACRO_RULES.items()
        if any(_contains(folded, word) for word in words)
    )
    score = round(score, 1)
    label = "Alta" if score >= 6 else "Media" if score >= 2 else "Bassa"
    return Classification(tuple(macro_areas), score, label, tuple(positive), tuple(negative))


def classify(text: str) -> tuple[str, ...]:
    """Backward-compatible macroarea-only API."""

    return classify_with_relevance(text).macro_areas
