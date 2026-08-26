from __future__ import annotations

import re

from funding_core.adapters import _AnchorTextParser
from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, _context, compact, decode_html, extract_deadline, infer_status, opportunity_context_ok


class FondazioneCrcAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_crc"
    page_url = "https://fondazionecrc.it/categorie_cosafacciamo/bandi/"
    source_label = "Fondazione CRC"
    funder = "Fondazione CRC"
    programme = "Bandi Fondazione CRC"
    url_tokens = ("bando", "contribut", "scuola", "giovani", "welfare", "comunit")
    excluded_tokens = ("deliberat", "progett", "event", "news", "esit", "privacy", "cookie")
    allow_status_context = True
    detail_enrichment = False

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(raw_title)
            if not title or re.search(r"contributi? deliberati|progett[oi] sostenuti", title, re.I):
                continue
            official_url = self._absolute(href)
            if not self._include_link(official_url, title):
                continue
            context = _context(text, href, title, 900)
            if not opportunity_context_ok(title, context, allow_status_context=True):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            records.append(SourceRecord(
                external_id=external_id, title=title, official_url=official_url,
                funder=self.funder, programme=self.programme, deadline=extract_deadline(context),
                eligible_entities=("Enti e organizzazioni ammissibili indicati nel singolo bando",),
                description=compact(f"{self.source_label}: {context}"), source_status=infer_status(context),
                territory="Piemonte",
            ))
        return records

    def _absolute(self, href: str) -> str:
        from urllib.parse import urljoin
        return urljoin(self.page_url, href)
