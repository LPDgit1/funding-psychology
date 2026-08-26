from __future__ import annotations

from urllib.parse import urlsplit

from ._common import DedicatedHtmlAdapter


class CompagniaSanPaoloAdapter(DedicatedHtmlAdapter):
    source_id = "compagnia_san_paolo"
    page_url = "https://www.compagniadisanpaolo.it/it/cosa-facciamo/contributi/"
    source_label = "Fondazione Compagnia di San Paolo"
    funder = "Fondazione Compagnia di San Paolo"
    programme = "Contributi e opportunità della Fondazione Compagnia di San Paolo"
    url_tokens = ("bando", "contribut", "opportunit", "call", "progett")
    excluded_tokens = ("news", "event", "contatti", "chi-siamo", "privacy", "cookie", "testimon")
    allow_status_context = True
    detail_enrichment = False

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        path = urlsplit(official_url).path.rstrip("/").lower()
        return path.startswith("/it/contributi/") and path != "/it/contributi"
