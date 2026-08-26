from __future__ import annotations

import re

from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, parse_listing_records


class DipendenzeAdapter(DedicatedHtmlAdapter):
    source_id = "dipendenze"
    page_url = "https://www.politicheantidroga.gov.it/it/avvisi-e-accordi/avvisi/"
    source_label = "Dipartimento per le politiche antidroga"
    funder = "Dipartimento per le politiche antidroga"
    programme = "Avvisi e finanziamenti per prevenzione e contrasto delle dipendenze"
    url_tokens = ("avvis", "bando", "progett", "finanziament", "serviz")
    excluded_tokens = ("esperti", "incaric", "graduatori", "commission", "esit", "selezione-del-personale", "/news")
    allow_status_context = True

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        return not re.search(r"\b(?:esperti|incaric|commission|graduatori|esit)\b", title, re.I)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        return parse_listing_records(self, raw, allow_status_context=True)

