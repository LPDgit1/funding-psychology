from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _detail_fields
from funding_core.dates import parse_date
from funding_core.models import SourceRecord

from ._common import (
    DedicatedHtmlAdapter,
    _context,
    compact,
    decode_html,
    derive_title,
    extract_deadline,
    extract_entities,
    extract_money,
    extract_regions,
    infer_status,
    opportunity_context_ok,
)


class FondazioneCariploAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_cariplo"
    page_url = "https://www.fondazionecariplo.it/contributi/bandi/"
    source_label = "Fondazione Cariplo"
    funder = "Fondazione Cariplo"
    programme = "Bandi Fondazione Cariplo"
    url_prefix = "/bando/"
    url_tokens = ("/bando/",)
    excluded_tokens = ("delibere", "news", "privacy", "contributi/bandi")
    allow_status_context = True
    detail_enrichment = True
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-CARIPLO-PAGE -->\n"

    def _include_link(self, official_url: str, title: str) -> bool:
        # A few legitimate cards have a short one-word title (for example
        # ``Veicolo``).  Keep the shared URL/exclusion checks while relaxing
        # only the generic eight-character title floor for this collection.
        if len(title.strip()) < 5:
            return False
        return super()._include_link(official_url, title if len(title) >= 8 else f"{title} call")

    def _fetch_url(self, url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError(f"unexpected content type from {self.source_label}")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from {self.source_label}", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for {self.source_label}: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} exceeds download size limit")
        return payload

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        first = super().fetch(policy)
        first_text = decode_html(first)
        page_numbers = [int(value) for value in re.findall(r"data-page=[\"'](\d+)[\"']", first_text)]
        max_page = min(max(page_numbers or [1]), 10)
        pages = [first]
        for page in range(2, max_page + 1):
            pages.append(self._fetch_url(f"{self.page_url}?paged={page}", policy))
        combined = self._combined_marker.encode("utf-8").join(pages)
        if len(combined) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} paginated response exceeds download size limit")
        return combined

    def _parse_page(self, text: str) -> list[SourceRecord]:
        parser = _AnchorTextParser()
        parser.feed(text)
        records = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(derive_title(text, href, raw_title))
            official_url = urljoin(self.page_url, href)
            if not self._include_link(official_url, title):
                continue
            if title.casefold() in {"scopri di più", "scopri di piu", "leggi", "dettagli"}:
                continue
            context = _context(text, href, title, 1500)
            if re.search(r"(?:contributi?\s+assegnat|deliberat|progetti?\s+sostenuti|esiti|news|privacy)", f"{title} {context}", re.IGNORECASE):
                continue
            # The official /bando/ collection is already the source contract;
            # do not apply a thematic keyword filter to valid call cards.
            if not opportunity_context_ok(title, context, allow_status_context=True) and not re.search(r"/bando/", official_url, re.IGNORECASE):
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
                opening_date=None,
                deadline=extract_deadline(context),
                total_budget=extract_money(context),
                eligible_entities=extract_entities(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status=infer_status(context, "OPEN"),
                regions=regions,
                territory="Lombardia" if "lombardia" in context.lower() else None,
            ))
        return records

    def parse(self, raw: bytes | str):
        text = decode_html(raw)
        pages = text.split(self._combined_marker)
        records = []
        seen: set[str] = set()
        for page in pages:
            for record in self._parse_page(page):
                if record.external_id in seen:
                    continue
                seen.add(record.external_id)
                records.append(record)
        return records

    @staticmethod
    def _detail_deadlines(description: str) -> list[date]:
        date_pattern = r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b|\b[A-Za-zÀ-ÿ]+\s+\d{1,2},\s*\d{4}\b"
        plain = compact(description, max(10000, len(description) + 1))
        values = []
        for match in re.finditer(r"(?:scadenza(?:\s+fase\s*\d+)?|fase\s*\d+)", plain, re.IGNORECASE):
            window = plain[match.start():match.start() + 220]
            for date_match in re.finditer(date_pattern, window, re.IGNORECASE):
                parsed = parse_date(date_match.group(0))
                if parsed and parsed not in values:
                    values.append(parsed)
        return sorted(values)

    @staticmethod
    def _fetch_detail(url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError("detail page exceeds size limit for Fondazione Cariplo")
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
                deadlines = self._detail_deadlines(detail_text)
                if deadlines:
                    future = [value for value in deadlines if value >= today]
                    deadline = future[0] if future else deadlines[-1]
                else:
                    deadline = fields.get("deadline") or record.deadline
                status = str(fields.get("source_status") or record.source_status)
                if status == "UNKNOWN":
                    status = record.source_status
                if deadline and deadline < today:
                    status = "CLOSED"
                description = str(fields.get("description") or record.description)
                enriched.append(replace(
                    record,
                    opening_date=fields.get("opening_date") or record.opening_date,
                    deadline=deadline,
                    total_budget=fields.get("total_budget") or record.total_budget,
                    eligible_entities=tuple(fields.get("eligible_entities") or record.eligible_entities),
                    description=description,
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
