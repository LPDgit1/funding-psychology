from __future__ import annotations

from ._common import DedicatedHtmlAdapter


class FondazioneConIlSudAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_con_il_sud"
    page_url = "https://fondazioneconilsud.it/bandi/"
    source_label = "Fondazione CON IL SUD"
    funder = "Fondazione CON IL SUD"
    programme = "Bandi e opportunità Fondazione CON IL SUD"
    url_tokens = ("bando", "avviso", "opportunit", "iniziativa", "cofinanziamento")
    excluded_tokens = ("progetti-sostenuti", "sostenuti", "esiti", "news", "event", "comunicat", "area-riservata")
    allow_status_context = True
    detail_enrichment = False
