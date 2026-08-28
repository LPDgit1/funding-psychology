from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._common import compact, decode_html, extract_entities, extract_money
from ._v04_common import clean, dates_in, fetch_bytes


class _CarispeziaCardParser(HTMLParser):
    """Capture only the source's archive card containers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._fragment: list[str] = []
        self.cards: list[str] = []
        self._void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "") or ""
        if self._depth == 0 and "bando-archivio-data" in classes.split():
            self._depth = 1
            self._fragment = [self.get_starttag_text() or ""]
            return
        if self._depth:
            self._fragment.append(self.get_starttag_text() or "")
            if tag not in self._void_tags:
                self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        self._fragment.append(f"</{tag}>")
        self._depth -= 1
        if self._depth == 0:
            self.cards.append("".join(self._fragment))
            self._fragment = []

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._fragment.append(data)


class FondazioneCarispeziaAdapter:
    """Official active/archive Bandi di erogazione pages."""

    source_id = "fondazione_carispezia"
    page_url = "https://www.fondazionecarispezia.it/bandi-di-erogazione/"
    archive_url = "https://www.fondazionecarispezia.it/bando/"
    source_label = "Fondazione Carispezia"
    funder = "Fondazione Carispezia"
    programme = "Bandi di erogazione della Fondazione Carispezia"
    max_bytes = 10_000_000
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-CARISPEZIA-ARCHIVE -->\n"

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        current = fetch_bytes(self.page_url, policy, label=self.source_label)
        archive = fetch_bytes(self.archive_url, policy, label=f"{self.source_label} archivio")
        combined = current + self._combined_marker.encode() + archive
        if len(combined) > policy.max_bytes:
            raise ValueError(f"{self.source_label} combined response exceeds size limit")
        return combined

    @staticmethod
    def _cards(raw: bytes | str) -> list[str]:
        parser = _CarispeziaCardParser()
        parser.feed(decode_html(raw))
        return parser.cards

    def _parse_cards(self, raw: bytes | str, *, archive: bool) -> list[SourceRecord]:
        text = decode_html(raw)
        if not archive and re.search(r"non\s+sono\s+presenti\s+bandi\s+attivi", text, re.IGNORECASE):
            return []
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, card in enumerate(self._cards(raw), 1):
            title_match = re.search(r'class=["\'][^"\']*bando-archivio-titolo[^"\']*["\'][^>]*>(.*?)</p>', card, re.IGNORECASE | re.DOTALL)
            protocol_match = re.search(r'class=["\'][^"\']*bando-archivio-protocollo[^"\']*["\'][^>]*>(.*?)</p>', card, re.IGNORECASE | re.DOTALL)
            if not title_match:
                continue
            title = clean(re.sub(r"<[^>]+>", " ", title_match.group(1)))
            protocol = clean(re.sub(r"<[^>]+>", " ", protocol_match.group(1))) if protocol_match else ""
            if not title or re.search(r"esiti|graduator|news|comunicat", title, re.IGNORECASE):
                continue
            publication_match = re.search(r"Pubblicazione\s*:\s*([^<]+)", card, re.IGNORECASE)
            dates = dates_in(publication_match.group(1), default_year=date.today().year) if publication_match else []
            deadline_match = re.search(r"(?:Scadenza|Chiusura)\s*:\s*([^<]+)", card, re.IGNORECASE)
            deadline_values = dates_in(deadline_match.group(1), default_year=date.today().year) if deadline_match else []
            slug = re.sub(r"[^a-z0-9]+", "-", f"{protocol}-{title}".casefold()).strip("-") or f"archive-{index}"
            if slug in seen:
                continue
            seen.add(slug)
            status = "CLOSED" if archive or re.search(r"scadut\w*|chius\w*", card, re.IGNORECASE) else "OPEN"
            records.append(SourceRecord(
                external_id=f"carispezia-{slug}",
                title=title,
                official_url=f"{self.archive_url if archive else self.page_url}#{slug}",
                funder=self.funder,
                programme=self.programme,
                opening_date=dates[0] if dates else None,
                deadline=deadline_values[0] if deadline_values else None,
                total_budget=extract_money(compact(card)),
                eligible_entities=extract_entities(compact(card)) or ("Enti e organizzazioni senza scopo di lucro secondo il bando",),
                description=compact(f"{self.source_label}: {protocol}; {card}"),
                source_status=status,
                status_authoritative=True,
            ))
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        parts = raw.split(self._combined_marker.encode()) if isinstance(raw, bytes) else raw.split(self._combined_marker)
        records: list[SourceRecord] = []
        for index, part in enumerate(parts[:2]):
            records.extend(self._parse_cards(part, archive=index == 1))
        return records
