from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _DetailTextParser
from funding_core.models import SourceRecord

from ._common import _context, compact, decode_html, extract_entities, extract_money
from ._v04_common import clean, dates_in, fetch_bytes, page_text


class _MpsPostContentParser(HTMLParser):
    """Extract the Divi ``et_pb_post_content`` container, not site chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "")
        if self._depth == 0 and "et_pb_post_content" in classes.split():
            self._depth = 1
            return
        if self._depth:
            self._depth += 1
            if tag in {"script", "style", "noscript", "template"}:
                self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth and not self._skip:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


class FondazioneMpsAdapter:
    """Official Fondazione MPS contribution/call cards and detail pages."""

    source_id = "fondazione_mps"
    page_url = "https://www.fondazionemps.it/icontributi/"
    source_label = "Fondazione MPS"
    funder = "Fondazione MPS"
    programme = "Contributi e bandi della Fondazione MPS"
    max_bytes = 16_000_000
    _contributi = re.compile(r"^https://www\.fondazionemps\.it/contributi/", re.IGNORECASE)
    _reject = re.compile(r"rendicont|esiti|graduator|news|comunicat|trasparenza", re.IGNORECASE)
    _signal = re.compile(r"bando|avviso|call|contribut|ra\s*e\s*rsa|siena\s+plurale|social\s+gym|consiglio\s+dei\s+giovani", re.IGNORECASE)

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            official_url = urljoin(self.page_url, href)
            if not self._contributi.match(official_url) or self._reject.search(official_url):
                continue
            title = clean(raw_title)
            if not title or not self._signal.search(title) or self._reject.search(title):
                continue
            # Avoid navigation links that simply repeat the archive heading.
            if title.casefold() in {"contributi", "scopri", "leggi tutto", "vai al bando"}:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(official_url).path.casefold()).strip("-")
            external_id = slug or f"mps-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            context = _context(text, href, raw_title, 1300)
            listing_status = "OPEN" if re.search(r"#bandiaperti|bando\s+aperto", context, re.IGNORECASE) else "UNKNOWN"
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                description=compact(f"{self.source_label}: {context}"),
                source_status=listing_status,
            ))
        return records

    @staticmethod
    def _labelled_date(text: str, labels: str) -> date | None:
        match = re.search(rf"(?:{labels})[^.;]{{0,100}}", text, re.IGNORECASE)
        values = dates_in(match.group(0), default_year=date.today().year) if match else []
        return values[0] if values else None

    @staticmethod
    def _detail_text(raw: bytes) -> str:
        decoded = decode_html(raw)
        content = _MpsPostContentParser()
        content.feed(decoded)
        if content.text:
            return content.text
        parser = _DetailTextParser()
        parser.feed(decoded)
        return parser.text or page_text(raw)

    def enrich(self, records: list[SourceRecord], policy: FetchPolicy | None = None, *, max_details: int = 30) -> list[SourceRecord]:
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = fetch_bytes(record.official_url, policy, label=f"{self.source_label} dettaglio")
                text = self._detail_text(payload)
                if not text:
                    enriched.append(record)
                    continue
                # MPS renders the lifecycle hashtag in the page chrome, just
                # outside ``et_pb_post_content``.  Read it from the full
                # bounded page text while keeping description/entities scoped
                # to the post-content parser above.
                chrome = page_text(payload)
                closed = bool(re.search(r"#(?:bando|avviso)chius[oa]|\b(?:bando|avviso)\s+chius[oa]|scadut\w*", chrome, re.IGNORECASE))
                open_tag = bool(re.search(r"#bandiaperti|\b(?:bando|avviso)\s+apert[oi]\b", chrome, re.IGNORECASE))
                deadline = self._labelled_date(text, r"scadenza|termine|entro il|chiusura") or record.deadline
                opening = self._labelled_date(text, r"apertura|dal giorno|pubblicazione") or record.opening_date
                if closed:
                    status = "CLOSED"
                elif open_tag:
                    status = "OPEN"
                elif deadline:
                    status = "OPEN" if deadline >= date.today() else "CLOSED"
                else:
                    status = record.source_status
                enriched.append(replace(
                    record,
                    opening_date=opening,
                    deadline=deadline,
                    total_budget=extract_money(text) or record.total_budget,
                    eligible_entities=extract_entities(text) or record.eligible_entities,
                    description=compact(text),
                    source_status=status,
                    status_authoritative=closed or open_tag,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
