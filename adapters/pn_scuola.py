from __future__ import annotations

import html
import re

from funding_core.dates import parse_date
from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, _DATE_RE, compact, decode_html, infer_status


class PnScuolaAdapter(DedicatedHtmlAdapter):
    source_id = "pn_scuola"
    page_url = "https://pn20212027.istruzione.it/scuola-e-competenze-fse/"
    source_label = "Programma Nazionale Scuola e Competenze 2021-2027"
    funder = "Ministero dell'istruzione e del merito"
    programme = "PN Scuola e Competenze FSE+ 2021-2027"
    url_tokens = ("avvis", "scuola", "agenda", "piano", "orientamento", "formazione", "accoglienza")
    excluded_tokens = ("privacy", "cookie", "youtube", "manuale", "tutorial")
    allow_status_context = True
    detail_enrichment = False

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.IGNORECASE | re.DOTALL)
        for index, row in enumerate(rows, 1):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)
            if len(cells) < 4:
                continue
            anchor = re.search(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", cells[0], re.IGNORECASE | re.DOTALL)
            if not anchor:
                continue
            href, raw_title = anchor.group(1), anchor.group(2)
            title = self._clean(re.sub(r"<[^>]+>", " ", html.unescape(raw_title)))
            if len(title) < 5 or title.lower() in {"scopri", "leggi", "image"}:
                continue
            if not re.search(r"\b(?:avvis|scuole|agenda|piano|orientamento|formazione|accoglienza|percorsi)\b", title, re.I):
                continue
            official_url = self._absolute(href)
            row_text = compact(" ".join(re.sub(r"<[^>]+>", " ", html.unescape(cell)) for cell in cells), 1400)
            status = "CLOSED" if re.search(r"scadut", row_text, re.I) else "UPCOMING" if re.search(r"in programma|prossim", row_text, re.I) else infer_status(row_text)
            date_match = _DATE_RE.search(cells[2])
            deadline = parse_date(date_match.group(0)) if date_match else None
            if deadline is None:
                date_match = _DATE_RE.search(row_text)
                deadline = parse_date(date_match.group(0)) if date_match else None
            external_id_match = re.search(r"(\d{3,}/?\d{0,8})", cells[1])
            external_id = external_id_match.group(1) if external_id_match else self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            records.append(SourceRecord(
                external_id=external_id, title=title, official_url=official_url,
                funder=self.funder, programme=self.programme, deadline=deadline,
                eligible_entities=("Istituzioni scolastiche",),
                description=compact(f"{self.source_label}: {row_text}"), source_status=status,
                territory="Italia",
            ))
        return records

    def _absolute(self, href: str) -> str:
        from urllib.parse import urljoin
        return urljoin(self.page_url, href)
