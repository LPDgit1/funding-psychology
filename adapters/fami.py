from __future__ import annotations

import json
import re
from datetime import date
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser
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
        lowered = text.lower()
        open_position = lowered.find("bandi aperti")
        closed_position = lowered.find("bandi scaduti", max(0, open_position + 1))
        if open_position < 0:
            return []
        if closed_position < 0:
            closed_position = len(text)
        def list_section(start: int, end: int) -> str:
            list_start = text.find("<ul", start, end)
            if list_start < 0:
                return text[start:end]
            list_end = text.find("</ul>", list_start, end)
            return text[list_start:list_end + len("</ul>")] if list_end >= 0 else text[list_start:end]

        sections = (
            ("OPEN", list_section(open_position, closed_position)),
            ("CLOSED", list_section(closed_position, len(text))),
        )
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for section_status, section in sections:
            parser = _AnchorTextParser()
            parser.feed(section)
            for index, (href, raw_title) in enumerate(parser.links, 1):
                title = self._clean(raw_title)
                official_url = urljoin(self.published_url, href)
                if not title or len(title) < 8 or not official_url.startswith("https://"):
                    continue
                if re.search(r"(?:privacy|cookie|accessibilit|home|menu)", title, re.IGNORECASE):
                    continue
                context = _context(section, href, title, 900)
                if not opportunity_context_ok(title, context, allow_status_context=True):
                    continue
                external_id = self._external_id(official_url, index)
                if external_id in seen:
                    continue
                seen.add(external_id)
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
