from __future__ import annotations

from dataclasses import replace

from ._common import DedicatedHtmlAdapter, parse_listing_records


class FondazioneCrtAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_crt"
    page_url = "https://www.fondazionecrt.it/progetti-e-bandi/"
    source_label = "Fondazione CRT"
    funder = "Fondazione CRT"
    programme = "Progetti e bandi Fondazione CRT"
    url_tokens = ("bando", "progett", "disabilit", "welfare", "istruz", "ordinari", "richiest")
    excluded_tokens = ("risultat", "news", "storie", "talent", "newsletter", "privacy", "cookie", "eventi")
    allow_status_context = True
    detail_enrichment = False

    def parse(self, raw: bytes | str):
        records = parse_listing_records(self, raw, allow_status_context=True, context_window=750)
        return [replace(
            record,
            title=record.title.removeprefix("In corso ").removeprefix("Risultati ").strip(),
            territory=record.territory or "Piemonte e Valle d'Aosta",
        ) for record in records]

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        path = official_url.lower()
        return not path.endswith("#content") and "/presenta-una-richiesta" not in path and "/progetti-e-bandi/" not in path and title.lower().strip() not in {"torna su", "presenta una richiesta"} and "risult" not in title.lower()
