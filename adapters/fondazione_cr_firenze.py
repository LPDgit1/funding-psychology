from __future__ import annotations

from ._common import DedicatedHtmlAdapter, parse_listing_records


class FondazioneCrFirenzeAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_cr_firenze"
    page_url = "https://fondazionecrfirenze.it/cosa-facciamo/bandi/"
    source_label = "Fondazione CR Firenze"
    funder = "Fondazione CR Firenze"
    programme = "I nostri bandi — Fondazione CR Firenze"
    url_tokens = ("bando", "benessere", "welfare", "fragilit", "inclus", "salute", "disabilit", "caregiver")
    excluded_tokens = ("esit", "progett", "event", "news", "privacy", "cookie", "deliber")
    allow_status_context = True

    def parse(self, raw: bytes | str):
        records = parse_listing_records(self, raw, allow_status_context=True, context_window=850)
        updated = []
        for record in records:
            if "firenze" in record.description.lower() and not record.territory:
                record = record.__class__(**{**record.__dict__, "territory": "Città metropolitana di Firenze"})
            updated.append(record)
        return updated
