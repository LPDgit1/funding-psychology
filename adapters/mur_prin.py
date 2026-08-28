from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import FetchPolicy, _AnchorTextParser
from funding_core.models import SourceRecord

from ._common import _context, compact, decode_html, extract_entities, extract_money
from ._v04_common import clean, dates_in, fetch_bytes


class MurPrinAdapter:
    """Parser for the public MUR PRIN initiative catalogue."""

    source_id = "mur_prin"
    page_url = "https://prin.mur.gov.it/"
    source_label = "MUR – PRIN"
    funder = "Ministero dell'Università e della Ricerca"
    programme = "Progetti di Ricerca di Interesse Nazionale (PRIN)"
    max_bytes = 10_000_000
    _detail_path = re.compile(r"/iniziative/detail\?key=", re.IGNORECASE)

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    @staticmethod
    def _title(raw_title: str) -> tuple[str, int | None]:
        title = clean(raw_title)
        match = re.search(r"\b(20\d{2})\b", title)
        year = int(match.group(1)) if match else None
        upper = title.upper()
        if "HYBRID" in upper:
            return f"Bando PRIN {year or ''} HYBRID".replace("  ", " ").strip(), year
        if "AFAM" in upper:
            return f"Bando PRIN {year or ''} AFAM".replace("  ", " ").strip(), year
        if year:
            return f"Bando PRIN {year}", year
        return title or "Bando PRIN", year

    @staticmethod
    def _window(context: str, year: int | None) -> tuple:
        if not context:
            return None, None
        # Prefer the explicit presentation/application sentence; this avoids
        # using publication/decree dates exposed in the same initiative card.
        labelled = re.search(
            r"(?:presentazion\w*|apertura|domand\w*|candidatur\w*|termine|scadenza)[^.;]{0,360}",
            context,
            re.IGNORECASE,
        )
        values = dates_in(labelled.group(0) if labelled else context, default_year=year)
        if len(values) >= 2:
            return values[0], values[-1]
        return (values[0], None) if values else (None, None)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        links = [(index, href, raw_title, text.find(href)) for index, (href, raw_title) in enumerate(parser.links, 1)]
        initiative_positions = [(position, href) for _, href, _, position in links if self._detail_path.search(href) and position >= 0]
        for index, (link_index, href, raw_title, position) in enumerate(links, 1):
            if not self._detail_path.search(href):
                continue
            official_url = urljoin(self.page_url, href)
            if urlsplit(official_url).netloc.casefold() != "prin.mur.gov.it":
                continue
            title, year = self._title(raw_title)
            if not title or title.casefold() in {"bando prin", "detail"}:
                continue
            external_id = re.sub(r"[^a-z0-9]+", "-", href.casefold()).strip("-") or f"prin-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            # The portal repeats the initiative links in navigation and cards;
            # use the bounded segment around this occurrence so PRIN HYBRID
            # does not inherit the first PRIN window's dates.
            next_positions = [item for item in initiative_positions if item[0] > position]
            previous_positions = [item for item in initiative_positions if item[0] < position]
            if previous_positions:
                previous_position, previous_href = max(previous_positions, key=lambda item: item[0])
                start = previous_position + len(previous_href)
            else:
                start = max(0, position - 700)
            end = min(len(text), min(item[0] for item in next_positions) if next_positions else position + 1200)
            context = compact(text[start:end])
            if not context:
                context = _context(text, href, raw_title, 1800)
            opening, deadline = self._window(context, year)
            if deadline is None and year and year < date.today().year:
                status = "CLOSED"
            elif deadline and deadline < date.today():
                status = "CLOSED"
            elif opening and opening > date.today():
                status = "UPCOMING"
            elif deadline:
                status = "OPEN"
            else:
                status = "UNKNOWN"
            entities = extract_entities(context)
            if not entities:
                entities = ("Università e enti pubblici di ricerca", "Istituzioni AFAM" if "AFAM" in title else "")
                entities = tuple(value for value in entities if value)
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                opening_date=opening,
                deadline=deadline,
                total_budget=extract_money(context),
                eligible_entities=entities,
                description=compact(f"{self.source_label}: {context}"),
                source_status=status,
            ))
        return records
