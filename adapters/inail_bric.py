from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser
from funding_core.models import SourceRecord

from ._common import compact, decode_html, extract_entities, extract_money
from ._v04_common import clean, dates_in, fetch_bytes, page_text


class InailBricAdapter:
    """Official INAIL Bandi di ricerca in collaborazione (BRIC) catalogue."""

    source_id = "inail_bric"
    page_url = "https://www.inail.it/portale/ricerca-e-tecnologia/it/come-fare-per/bandi-di-ricerca-in-collaborazione--bric-.html"
    source_label = "INAIL – Bandi BRIC"
    funder = "INAIL"
    programme = "Bandi di ricerca in collaborazione (BRIC)"
    max_bytes = 12_000_000
    _link = re.compile(r"/bando-bric-(20\d{2})\.html", re.IGNORECASE)

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            match = self._link.search(href)
            if not match:
                continue
            official_url = urljoin(self.page_url, href)
            if urlsplit(official_url).netloc.casefold() not in {"www.inail.it", "inail.it"}:
                continue
            year = int(match.group(1))
            external_id = f"bric-{year}"
            if external_id in seen:
                continue
            seen.add(external_id)
            context = compact(f"{raw_title} {_context_for(text, href)}")
            records.append(SourceRecord(
                external_id=external_id,
                title=f"Bando BRIC {year}",
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                description=compact(f"{self.source_label}: {context}"),
                source_status="UNKNOWN",
            ))
        return records

    @staticmethod
    def _dates(text: str, year: int) -> tuple[date | None, date | None]:
        # The official detail sentence normally contains both endpoints in a
        # single “dal … al/entro …” window.  Restrict extraction to that
        # sentence so result/FAQ dates cannot become deadlines.
        match = re.search(
            r"(?:presentat\w*|propost\w*|domand\w*)[^.]{0,100}(?:dal|dalle)\b[^.]{0,260}",
            text,
            re.IGNORECASE,
        )
        window = match.group(0) if match else text
        values = dates_in(window, default_year=year)
        if len(values) >= 2:
            return values[0], values[-1]
        labelled = re.search(r"(?:scadenza|entro|chiusura)[^.;]{0,180}", text, re.IGNORECASE)
        values = dates_in(labelled.group(0), default_year=year) if labelled else []
        return (None, values[0]) if values else (None, None)

    def enrich(self, records: list[SourceRecord], policy: FetchPolicy | None = None, *, max_details: int = 12) -> list[SourceRecord]:
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = fetch_bytes(record.official_url, policy, label=f"{self.source_label} dettaglio")
                text = page_text(payload)
                year_match = re.search(r"\b(20\d{2})\b", record.title)
                year = int(year_match.group(1)) if year_match else date.today().year
                opening, deadline = self._dates(text, year)
                status = "OPEN" if deadline and deadline >= date.today() else "CLOSED" if deadline else record.source_status
                entities = extract_entities(text) or (
                    "Enti pubblici di ricerca",
                    "Università e dipartimenti",
                    "IRCCS",
                )
                enriched.append(replace(
                    record,
                    opening_date=opening or record.opening_date,
                    deadline=deadline or record.deadline,
                    total_budget=extract_money(text) or record.total_budget,
                    eligible_entities=tuple(entities),
                    description=compact(text or record.description),
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched


def _context_for(text: str, href: str, window: int = 700) -> str:
    position = text.lower().find(href.lower())
    if position < 0:
        return ""
    return text[max(0, position - window): position + window]
