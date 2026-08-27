from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._v04_common import clean, parse_day_date, fetch_bytes


class _InappRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._row_depth = 0
        self._cell_depth = 0
        self._cell: list[str] = []
        self._cells: list[str] = []
        self._rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "") or ""
        if tag == "div" and "row" in classes.split() and "riga" in classes.split() and not self._row_depth:
            self._row_depth = 1
            self._cells = []
            return
        if not self._row_depth:
            return
        if tag == "div":
            classes = classes.split()
            if "col-lg" in classes and self._cell_depth == 0:
                self._cell_depth = 1
                self._cell = []
            elif self._cell_depth:
                self._cell_depth += 1
        elif self._cell_depth:
            self._cell_depth += 1

    def handle_data(self, data: str) -> None:
        if self._cell_depth:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._row_depth:
            return
        if self._cell_depth:
            if tag == "div" and self._cell_depth == 1:
                self._cells.append(clean("".join(self._cell)))
                self._cell = []
                self._cell_depth = 0
            else:
                self._cell_depth -= 1
        if tag == "div" and self._cell_depth == 0 and self._row_depth == 1:
            # A row's closing div is indistinguishable from a column closing
            # div after the cell has been appended; it is safe to close a row
            # only when at least four columns have been captured.
            if len(self._cells) >= 4:
                self._rows.append(self._cells)
                self._row_depth = 0
        elif tag == "div" and self._row_depth > 1:
            self._row_depth -= 1

    @property
    def rows(self) -> list[list[str]]:
        return self._rows


class ErasmusInappAdapter:
    source_id = "erasmus_inapp"
    page_url = "https://www.erasmusplus.it/programma/scadenze/"
    source_label = "Erasmus+ INAPP"
    funder = "INAPP – Agenzia nazionale Erasmus+"
    programme = "Erasmus+ 2026 – Formazione professionale"
    max_bytes = 2_000_000

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        parser = _InappRowParser()
        parser.feed(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for cells in parser.rows:
            if len(cells) < 4:
                continue
            action, sector, deadline_text, agency = cells[:4]
            if "INAPP" not in agency.upper() or "formazione professionale" not in sector.casefold():
                continue
            date_match = re.search(r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+(?:\s+20\d{2})?\b", deadline_text)
            deadline = parse_day_date(date_match.group(0), default_year=2026) if date_match else None
            if not action or not deadline:
                continue
            code = re.search(r"\bKA\d{3}\b", action, re.IGNORECASE)
            code_text = code.group(0).lower() if code else re.sub(r"[^a-z0-9]+", "-", action.casefold()).strip("-")
            external_id = f"{code_text}-{deadline.isoformat()}"
            if external_id in seen:
                continue
            seen.add(external_id)
            source_status = "OPEN" if deadline >= date.today() else "CLOSED"
            title = f"Erasmus+ 2026 — {action} — Formazione professionale"
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=self.page_url,
                funder=self.funder,
                programme=self.programme,
                deadline=deadline,
                eligible_entities=("Organizzazioni ammissibili Erasmus+ per la formazione professionale",),
                description=f"Scadenza ufficiale Erasmus+ 2026; settore {sector}; agenzia {agency}; azione {action}.",
                source_status=source_status,
                territory="Italia / programma Erasmus+",
            ))
        return records

