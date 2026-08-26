from __future__ import annotations

from urllib.parse import urlsplit

from ._common import DedicatedHtmlAdapter, parse_listing_records


class FondazioneCrFirenzeAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_cr_firenze"
    page_url = "https://fondazionecrfirenze.it/cosa-facciamo/bandi/"
    source_label = "Fondazione CR Firenze"
    funder = "Fondazione CR Firenze"
    programme = "I nostri bandi — Fondazione CR Firenze"
    # The official page is already a bounded collection of calls.  A
    # thematic URL allow-list dropped legitimate records such as
    # ``Grandi Attrezzature``; rely on the source path and anti-editorial
    # exclusions instead.
    url_tokens = ()
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

    def _include_link(self, official_url: str, title: str) -> bool:
        # Keep only individual call pages.  The listing page itself and the
        # navigation/archive links live below ``/cosa-facciamo/`` and must not
        # become opportunities after removing the old thematic allow-list.
        if not urlsplit(official_url).path.lower().startswith("/bandi/"):
            return False
        return super()._include_link(official_url, title)
