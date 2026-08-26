from __future__ import annotations

import re

from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, compact, decode_html, extract_money, infer_status, parse_listing_records


class FondazioneVeneziaAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_venezia"
    page_url = "https://www.fondazionedivenezia.org/attivita/bandi/"
    source_label = "Fondazione di Venezia"
    funder = "Fondazione di Venezia"
    programme = "Bandi culturali e sociali della Fondazione di Venezia"
    url_tokens = ("bando", "avviso", "fragilit", "cultura", "solidariet")
    excluded_tokens = ("selezionat", "beneficiar", "esiti", "progett", "iniziative-selezionate", "archivio")
    allow_status_context = True
    detail_enrichment = False

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records = parse_listing_records(self, text, allow_status_context=True)
        known = {item.title.casefold() for item in records}
        # The current landing page renders some cards as headings with a
        # JavaScript “Scopri di più” control rather than a normal anchor.  A
        # heading-only fallback keeps the canonical listing usable without a
        # browser while still excluding selected projects/results.
        for match in re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", text, re.I | re.S):
            title = self._clean(re.sub(r"<[^>]+>", " ", match.group(1)))
            if title.casefold() in known or not re.search(r"\b(?:bando|avviso|fragilit|solidariet|cultura)\b", title, re.I):
                continue
            if re.search(r"selezionat|esit|beneficiar|progett[oi]", title, re.I):
                continue
            context = compact(text[match.start(): match.end() + 900])
            records.append(SourceRecord(
                external_id=self._external_id(self.page_url + "#" + title, len(records) + 1),
                title=title, official_url=self.page_url, funder=self.funder,
                programme=self.programme, deadline=None, total_budget=extract_money(context),
                description=compact(f"{self.source_label}: {context}"), source_status="UNKNOWN",
                territory="Veneto",
            ))
            known.add(title.casefold())
        return records
