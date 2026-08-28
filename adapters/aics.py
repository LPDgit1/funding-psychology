from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin

from funding_core.adapters import FetchPolicy
from funding_core.dates import parse_date
from funding_core.models import SourceRecord

from ._common import decode_html
from ._v04_common import clean, fetch_bytes


class _AicsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._row_depth = 0
        self._cell_depth = 0
        self._cell_parts: list[str] = []
        self._cells: list[str] = []
        self._href: str | None = None
        self._rows: list[tuple[list[str], str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr" and not self._row_depth:
            self._row_depth = 1
            self._cells = []
            self._href = None
            return
        if self._row_depth:
            if tag == "tr":
                self._row_depth += 1
            if tag == "td" and self._cell_depth == 0:
                self._cell_depth = 1
                self._cell_parts = []
            elif self._cell_depth:
                self._cell_depth += 1
            if tag == "a" and attrs_dict.get("href"):
                self._href = attrs_dict["href"]

    def handle_data(self, data: str) -> None:
        if self._cell_depth:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._row_depth:
            return
        if self._cell_depth:
            if tag == "td" and self._cell_depth == 1:
                self._cells.append(clean("".join(self._cell_parts)))
                self._cell_parts = []
                self._cell_depth = 0
            else:
                self._cell_depth -= 1
        if tag == "tr":
            self._row_depth -= 1
            if self._row_depth == 0:
                self._rows.append((self._cells, self._href))

    @property
    def rows(self) -> list[tuple[list[str], str | None]]:
        return self._rows


class AicsAdapter:
    source_id = "aics"
    page_url = "https://trasparenza.aics.gov.it/pagina952_bandi/noprofit.html"
    source_label = "AICS – Bandi non profit"
    funder = "Agenzia Italiana per la Cooperazione allo Sviluppo"
    programme = "Bandi e contributi AICS per enti non profit"
    max_bytes = 2_000_000

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    @staticmethod
    def _date(value: str) -> date | None:
        candidate = value.replace("-", "/")
        return parse_date(candidate)

    @staticmethod
    def _is_procurement(title: str) -> bool:
        return bool(re.search(r"\b(?:gara|gare|contratt[io]|affidament[oi]|fornitura|servizi\s+di\s+acquisto)\b", title, re.IGNORECASE))

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        parser = _AicsTableParser()
        # The transparency host has historically served this table as
        # Windows-1252 despite an incomplete/incorrect charset declaration.
        # Use the shared bounded decoder so accented applicant names survive
        # unchanged instead of becoming U+FFFD replacement characters.
        parser.feed(decode_html(raw))
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for cells, href in parser.rows:
            if len(cells) < 5:
                continue
            year, title, deadline_text, status_text, entities = cells[:5]
            if not title or not re.search(r"\b(?:bando|avviso|call|procedura)\b", title, re.IGNORECASE) or self._is_procurement(title):
                continue
            official_url = urljoin(self.page_url, href or self.page_url)
            external_id = re.sub(r"[^a-z0-9]+", "-", (href or title).lower()).strip("-") or f"aics-{year}-{len(records)+1}"
            if external_id in seen:
                continue
            seen.add(external_id)
            status = "OPEN" if re.search(r"in\s+corso|apert", status_text, re.IGNORECASE) else "CLOSED" if re.search(r"conclus|chius|scadut", status_text, re.IGNORECASE) else "UNKNOWN"
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                deadline=self._date(deadline_text),
                eligible_entities=(entities,) if entities else (),
                description=f"{self.source_label}: anno {year}; stato procedura {status_text}; soggetti proponenti: {entities}.",
                source_status=status,
                status_authoritative=True,
                territory="Internazionale / Paesi partner",
            ))
        return records
