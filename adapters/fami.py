from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _DetailTextParser, _detail_fields
from funding_core.dates import parse_date
from funding_core.models import SourceRecord
from funding_core.territories import normalize_territory, split_regions

from ._common import (
    DedicatedHtmlAdapter,
    compact,
    decode_html,
    extract_deadline,
    extract_entities,
    extract_money,
    extract_opening,
    extract_regions,
    infer_status,
    opportunity_context_ok,
    _context,
)


class FamiAdapter(DedicatedHtmlAdapter):
    source_id = "fami"
    page_url = "https://fami.dlci.interno.gov.it/accesso-al-fondo/calendario-programmatico-degli-avvisi"
    published_url = "https://fami.dlci.interno.gov.it/accesso-al-fondo/avvisi-pubblici"
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-FAMI-CALENDAR -->\n"
    source_label = "Programma Nazionale FAMI 2021-2027"
    funder = "Ministero dell'Interno — Autorità di Gestione FAMI"
    programme = "PN FAMI 2021-2027"
    url_tokens = ("avvis", "fami", "call", "fondo")
    excluded_tokens = ("faq", "tutorial", "event", "news", "privacy")
    max_bytes = 12_000_000
    _detail_date_re = re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b|"
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|"
        r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b|"
        r"\b[A-Za-zÀ-ÿ]+\s+\d{1,2},\s*\d{4}\b",
        re.IGNORECASE,
    )

    class _DetailTextParser(HTMLParser):
        """Read Drupal's main bandi-gare node, excluding site chrome."""

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self._depth = 0
            self._skip = 0
            self._buffer: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attributes = dict(attrs)
            identity = " ".join(filter(None, (attributes.get("id"), attributes.get("class"))))
            if self._depth == 0 and re.search(r"main-content|node--type-bandi-gare|block-system-main-block", identity, re.IGNORECASE):
                self._depth = 1
                return
            if self._depth:
                self._depth += 1
                if tag in {"script", "style", "noscript", "template", "nav", "footer", "aside"}:
                    self._skip += 1

        def handle_endtag(self, tag: str) -> None:
            if not self._depth:
                return
            if tag in {"script", "style", "noscript", "template", "nav", "footer", "aside"} and self._skip:
                self._skip -= 1
            self._depth -= 1

        def handle_data(self, data: str) -> None:
            if self._depth and not self._skip:
                self._buffer.append(data)

        @property
        def text(self) -> str:
            return re.sub(r"\s+", " ", " ".join(self._buffer)).strip()

    def _fetch_html(self, url: str, policy: FetchPolicy) -> bytes:
        """Fetch one of the two official FAMI entry points."""
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
        """Combine the published-call listing and the programme calendar."""
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        published = self._fetch_html(self.published_url, policy)
        calendar = super().fetch(policy)
        combined = published + self._combined_marker.encode("utf-8") + calendar
        if len(combined) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} combined response exceeds download size limit")
        return combined

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        path = urlsplit(official_url).path.rstrip("/").lower()
        # Navigation links such as “Avvisi pubblici” and the calendar page are
        # not individual records.  A candidate must point below an avvisi/bandi
        # collection path (or be supplied by the embedded calendar JSON).
        if path.endswith("/calendario-programmatico-degli-avvisi") or path.endswith("/avvisi-pubblici"):
            return False
        return bool(re.search(r"/(?:avvisi|bandi)/[^/]+$", path))

    def _json_records(self, text: str) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        # Keep support for the small JSON payload used by the current calendar
        # widget without emulating its client-side filters.
        for match in re.finditer(r"<script[^>]+type=[\"']application/json[\"'][^>]*>(.*?)</script>", text, re.I | re.S):
            try:
                payload = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
            values = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
            for index, item in enumerate(values, 1):
                if not isinstance(item, dict):
                    continue
                title = compact(str(item.get("title") or item.get("name") or ""), 300)
                if not title or not opportunity_context_ok(title, str(item), allow_status_context=True):
                    continue
                official_url = urljoin(self.page_url, str(item.get("url") or item.get("link") or self.page_url))
                opening = parse_date(str(item.get("expectedPublication") or item.get("openingDate") or ""))
                deadline = parse_date(str(item.get("expectedDeadline") or item.get("deadline") or ""))
                status = "UPCOMING" if str(item.get("kind") or item.get("type") or "").upper() == "EARLY" else infer_status(str(item), "UNKNOWN")
                records.append(SourceRecord(
                    external_id=str(item.get("id") or f"fami-json-{index}"), title=title,
                    official_url=official_url, funder=self.funder, programme=str(item.get("programme") or self.programme),
                    opening_date=opening, deadline=deadline, total_budget=extract_money(str(item)),
                    eligible_entities=tuple(str(item.get("eligibleEntities") or "").split(";")) if item.get("eligibleEntities") else (),
                    description=compact(str(item.get("description") or item)), source_status=status,
                    regions=split_regions(item.get("regions") if isinstance(item.get("regions"), list) else []),
                    territory=str(item.get("territory") or "Italia"),
                ))
        return records

    def _published_records(self, text: str) -> list[SourceRecord]:
        """Parse the authoritative ``Bandi aperti`` and ``Bandi scaduti`` lists."""
        heading_pattern = re.compile(
            r"<(?:h[1-6]|p)\b[^>]*>(?:(?!<(?:h[1-6]|p)\b).)*?"
            r"\bBandi\s+(aperti|scaduti)\b.*?</(?:h[1-6]|p)>",
            re.IGNORECASE | re.DOTALL,
        )
        headings = list(heading_pattern.finditer(text))
        open_heading = next((match for match in headings if match.group(1).lower() == "aperti"), None)
        closed_heading = next((match for match in headings if match.group(1).lower() == "scaduti"), None)
        if open_heading is None:
            lowered = text.lower()
            open_position = lowered.find("bandi aperti")
            closed_position = lowered.find("bandi scaduti", max(0, open_position + 1))
            if open_position < 0:
                return []
            open_start = open_position
            closed_start = closed_position if closed_position >= 0 else len(text)
        else:
            open_start = open_heading.start()
            closed_start = closed_heading.start() if closed_heading else len(text)

        def section_span(start: int, end: int) -> str:
            # Keep every list between the section heading and the next
            # section boundary.  In particular, do not stop at the first
            # ``<ul>``: the official historical section can contain more than
            # one list and may repeat an URL for distinct notices.
            return text[start:end]

        if open_heading is None and open_start < 0:
            return []

        sections = (
            ("OPEN", section_span(open_start, closed_start)),
            ("CLOSED", section_span(closed_start, len(text))),
        )
        records: list[SourceRecord] = []
        seen: set[tuple[str, str]] = set()
        used_ids: set[str] = set()
        for section_status, section in sections:
            parser = _AnchorTextParser()
            parser.feed(section)
            for index, (href, raw_title) in enumerate(parser.links, 1):
                title = self._clean(raw_title)
                official_url = urljoin(self.published_url, href)
                if not title or len(title) < 8 or not official_url.startswith("https://www.interno.gov.it/"):
                    continue
                if re.search(
                    r"(?:privacy|cookie|accessibilit|home|menu|faq|linee\s+operative|"
                    r"graduator\w*|esiti|news|comunicat\w*)",
                    title,
                    re.IGNORECASE,
                ):
                    continue
                context = _context(section, href, title, 900)
                # The published page is itself the authoritative call list;
                # avoid applying the generic thematic predicate to titles such
                # as the historical psychosocial-vulnerability notice.
                key = (official_url.rstrip("/"), title.casefold())
                if key in seen:
                    continue
                seen.add(key)
                external_id = self._external_id(official_url, index)
                if external_id in used_ids:
                    suffix = 2
                    candidate = f"{external_id}-{suffix}"
                    while candidate in used_ids:
                        suffix += 1
                        candidate = f"{external_id}-{suffix}"
                    external_id = candidate
                used_ids.add(external_id)
                entity_match = re.search(
                    r"rivolt[oa]\s+(?:esclusivamente\s+)?(?:agli?|alle?)\s+([^.;]{1,260})",
                    context,
                    re.IGNORECASE,
                )
                entities = extract_entities(context)
                if not entities and entity_match:
                    entities = (compact(entity_match.group(1), 260),)
                regions = extract_regions(context)
                records.append(SourceRecord(
                    external_id=external_id,
                    title=title,
                    official_url=official_url,
                    funder=self.funder,
                    programme=self.programme,
                    opening_date=extract_opening(context),
                    deadline=extract_deadline(context),
                    total_budget=extract_money(context),
                    eligible_entities=entities,
                    description=compact(f"{self.source_label}: {context}"),
                    source_status=section_status,
                    status_authoritative=True,
                    regions=regions,
                    territory=normalize_territory(regions, context, fallback="Italia"),
                ))
        return records

    @classmethod
    def _detail_deadline(cls, text: str) -> date | None:
        """Extract the final labelled FAMI deadline, including proroghe."""
        plain = re.sub(r"\s+", " ", text).strip()
        candidates: list[tuple[int, date]] = []
        patterns = (
            (3, r"(?:prorogat\w*|termine\s+finale\s+prorogat\w*)[^.;]{0,100}\b(?:al|il|giorno)\b[^.;]{0,80}"),
            (2, r"(?:data\s+di\s+scadenza|scadenza|termine\s+perentorio|termine|entro\s+il)[^.;]{0,100}"),
        )
        for priority, label_pattern in patterns:
            for match in re.finditer(label_pattern, plain, re.IGNORECASE):
                for date_match in cls._detail_date_re.finditer(match.group(0)):
                    parsed = parse_date(date_match.group(0))
                    if parsed:
                        candidates.append((priority, parsed))
        if not candidates:
            return None
        best_priority = max(priority for priority, _ in candidates)
        return max(value for priority, value in candidates if priority == best_priority)

    @staticmethod
    def _detail_text(payload: bytes) -> str:
        text = decode_html(payload)
        parser = FamiAdapter._DetailTextParser()
        parser.feed(text)
        if parser.text:
            return parser.text
        fallback = _DetailTextParser()
        fallback.feed(text)
        return fallback.text

    @staticmethod
    def _fetch_detail(url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise AdapterError(f"unexpected detail content type from {FamiAdapter.source_label}")
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError(f"detail page exceeds size limit for {FamiAdapter.source_label}")
        return payload

    def enrich(self, records, policy=None, *, max_details: int = 40):
        """Enrich published FAMI notices without changing calendar semantics."""
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        cache: dict[str, bytes] = {}
        for index, record in enumerate(records):
            if index >= max_details or "www.interno.gov.it" not in record.official_url:
                enriched.append(record)
                continue
            try:
                payload = cache.get(record.official_url)
                if payload is None:
                    payload = self._fetch_detail(record.official_url, policy)
                    cache[record.official_url] = payload
                detail_text = self._detail_text(payload)
                fields = _detail_fields(payload)
                deadline = self._detail_deadline(detail_text) or fields.get("deadline") or record.deadline
                description = str(detail_text or fields.get("description") or record.description)
                status = record.source_status if record.status_authoritative else str(fields.get("source_status") or record.source_status)
                enriched.append(replace(
                    record,
                    opening_date=fields.get("opening_date") or record.opening_date,
                    deadline=deadline,
                    total_budget=extract_money(detail_text) or fields.get("total_budget") or record.total_budget,
                    eligible_entities=tuple(extract_entities(detail_text) or fields.get("eligible_entities") or record.eligible_entities),
                    description=compact(description),
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched

    def _calendar_records(self, text: str) -> list[SourceRecord]:
        json_records = self._json_records(text)
        if json_records:
            return json_records
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(raw_title)
            official_url = urljoin(self.page_url, href)
            if not self._include_link(official_url, title):
                continue
            context = _context(text, href, title, 500)
            if not opportunity_context_ok(title, context, allow_status_context=True):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            early = bool(re.search(r"(?:prossimi avvisi|calendario|previst|expected|early)", f"{title} {context}", re.I))
            published = bool(re.search(r"(?:avviso|call)\s+pubblicat|in\s+corso|apert", context, re.I))
            records.append(SourceRecord(
                external_id=external_id, title=title, official_url=official_url,
                funder=self.funder, programme=self.programme,
                opening_date=extract_opening(context), deadline=extract_deadline(context),
                total_budget=extract_money(context), eligible_entities=extract_entities(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status="UPCOMING" if early else "OPEN" if published else infer_status(context),
                regions=extract_regions(context), territory=normalize_territory(extract_regions(context), context, fallback="Italia"),
            ))
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        if self._combined_marker in text:
            published, calendar = text.split(self._combined_marker, 1)
            return self._published_records(published) + self._calendar_records(calendar)
        return self._calendar_records(text)
