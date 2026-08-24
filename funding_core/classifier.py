from __future__ import annotations

import unicodedata

RULES = {
    "Salute mentale e benessere": ("salute mentale", "benessere", "psychological", "mental health", "disagio"),
    "Minori e adolescenti": ("minori", "adolescent", "youth", "children", "giovani"),
    "Scuola, università e formazione": ("scuola", "scolastic", "school", "student", "formazione", "universit"),
    "Famiglia e genitorialità": ("famiglia", "genitorial", "family", "parent"),
    "Inclusione sociale e vulnerabilità": ("inclusione", "fragilit", "povert", "vulnerab", "social exclusion"),
    "Disabilità e neurodiversità": ("disabil", "neurodivers", "autism"),
    "Anziani, ageing e caregiver": ("anzian", "ageing", "elderly", "older people", "caregiver"),
    "Violenza, trauma e tutela": ("violenza", "trauma", "abuso", "protection"),
    "Dipendenze": ("dipenden", "addiction", "substance use"),
    "Lavoro, organizzazioni e occupazione": ("lavor", "occupazione", "employment", "workplace", "burnout"),
    "Comunità, welfare e sviluppo territoriale": ("comunit", "welfare", "territori", "community"),
    "Salute pubblica e prevenzione": ("salute pubblica", "prevenzione", "public health", "prevention"),
    "Migrazione, integrazione e intercultura": ("migraz", "intercultur", "migrant", "refugee"),
    "Diritti, pari opportunità e contrasto alle discriminazioni": ("pari opportun", "discrimin", "gender equality", "violenza di genere", "diritti"),
    "Digitale, innovazione e AI": ("digitale", "digital", "artificial intelligence", "intelligenza artificiale"),
    "Ricerca e innovazione scientifica": ("ricerca", "research", "scientific", "innovazione"),
}


def _fold(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(char) != "Mn")


def classify(text: str) -> tuple[str, ...]:
    folded = _fold(text)
    return tuple(area for area, words in RULES.items() if any(_fold(word) in folded for word in words))
