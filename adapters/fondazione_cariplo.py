from __future__ import annotations

from ._common import DedicatedHtmlAdapter


class FondazioneCariploAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_cariplo"
    page_url = "https://www.fondazionecariplo.it/contributi/bandi/"
    source_label = "Fondazione Cariplo"
    funder = "Fondazione Cariplo"
    programme = "Bandi Fondazione Cariplo"
    url_prefix = "/bando/"
    url_tokens = ("/bando/",)
    excluded_tokens = ("delibere", "progetti", "news", "privacy", "contributi/bandi")
    allow_status_context = True
    detail_enrichment = False
