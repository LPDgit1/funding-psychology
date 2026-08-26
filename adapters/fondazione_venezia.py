from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.parse import urljoin, urlsplit

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy, _detail_fields
from funding_core.models import SourceRecord

from funding_core.dates import parse_date

from ._common import (
    DedicatedHtmlAdapter,
    _context,
    compact,
    decode_html,
    extract_deadline,
    extract_money,
    extract_regions,
    infer_status,
    opportunity_context_ok,
)


class FondazioneVeneziaAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_venezia"
    page_url = "https://www.fondazionedivenezia.org/attivita/bandi/"
    source_label = "Fondazione di Venezia"
    funder = "Fondazione di Venezia"
    programme = "Bandi culturali e sociali della Fondazione di Venezia"
    url_tokens = ("bando", "avviso", "fragilit", "cultura", "solidariet")
    excluded_tokens = ("selezionat", "beneficiar", "esiti", "progett", "iniziative-selezionate", "archivio")
    allow_status_context = True
    detail_enrichment = True

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        headings = list(re.finditer(
            r"<h[1-6][^>]*class=[\"'][^\"']*\btitolo-att\b[^\"']*[\"'][^>]*>(.*?)</h[1-6]>",
            text,
            re.IGNORECASE | re.DOTALL,
        ))
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, heading in enumerate(headings, 1):
            title = self._clean(heading.group(1))
            end = headings[index].start() if index < len(headings) else min(len(text), heading.end() + 5000)
            card = text[heading.start():end]
            href_match = re.search(r"href=[\"']([^\"']+)[\"']", card, re.IGNORECASE)
            if not href_match:
                continue
            official_url = urljoin(self.page_url, href_match.group(1).strip())
            path = urlsplit(official_url).path.lower()
            if not ("/archivio-attivita/" in path or "/attivita/" in path):
                continue
            context = compact(card, 2400)
            if re.search(r"selezionat|esit|beneficiar|comunicat|news|event", f"{title} {context}", re.IGNORECASE):
                continue
            if not opportunity_context_ok(title, context, allow_status_context=True):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            regions = extract_regions(context)
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                deadline=extract_deadline(context),
                total_budget=extract_money(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status=infer_status(context),
                regions=regions,
                territory="Veneto",
            ))
        return records

    @staticmethod
    def _detail_deadline(description: str):
        date_pattern = r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b"
        # Strip markup first and allow ordinary punctuation (for example
        # ``ore 12.00``) between the label and the date.
        # WordPress pages can put a large inline stylesheet before the body;
        # do not truncate before reaching the detail text.
        plain = compact(description, max(10000, len(description) + 1))
        for label_match in re.finditer(r"(?:scadenza|termine|entro)", plain, re.IGNORECASE):
            window = plain[label_match.start():label_match.start() + 500]
            for date_match in re.finditer(date_pattern, window, re.IGNORECASE):
                parsed = parse_date(date_match.group(0))
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _fetch_detail(url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError("detail page exceeds size limit for Fondazione di Venezia")
        return payload

    def enrich(self, records, policy=None, *, max_details: int = 40):
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        today = date.today()
        enriched = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                detail_payload = self._fetch_detail(record.official_url, policy)
                detail_text = decode_html(detail_payload)
                fields = _detail_fields(detail_payload)
                deadline = record.deadline or self._detail_deadline(detail_text) or self._detail_deadline(record.description)
                status = record.source_status
                if deadline and deadline < today:
                    status = "CLOSED"
                description = str(fields.get("description") or record.description)
                if deadline:
                    description = compact(f"{description} Termine verificato dalla pagina ufficiale: {deadline.isoformat()}.", 2400)
                enriched.append(replace(record, deadline=deadline, source_status=status, description=description))
            except (AdapterError, HTTPError, URLError, OSError, ValueError):
                enriched.append(record)
        return enriched
