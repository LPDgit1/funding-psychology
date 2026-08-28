from __future__ import annotations

import re
from datetime import date

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._v04_common import amount, clean, dates_in, fetch_bytes, page_text


class MinisteroSaluteRicercaFinalizzataAdapter:
    """Official Ministero della Salute Ricerca Finalizzata call listing."""

    source_id = "ministero_salute_ricerca_finalizzata"
    page_url = "https://www.salute.gov.it/new/it/tema/sistema-ricerca-del-ssn-enti-e-finanziamenti/la-ricerca-finalizzata/"
    source_label = "Ministero della Salute – Ricerca Finalizzata"
    funder = "Ministero della Salute"
    programme = "Ricerca Finalizzata del Servizio Sanitario Nazionale"
    max_bytes = 8_000_000

    _challenge = re.compile(r"site verification|please enable javascript|cf-chl|checking your browser", re.IGNORECASE)
    _call = re.compile(
        r"(?:bando|avviso)[^\n.;]{0,140}?ricerca\s+finalizzata[^\n.;]{0,80}?(20\d{2})",
        re.IGNORECASE,
    )

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    @staticmethod
    def _window(text: str, start: int, end: int) -> str:
        return text[max(0, start - 260): min(len(text), end + 1400)]

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = page_text(raw)
        if not text or self._challenge.search(text):
            return []
        matches = list(self._call.finditer(text))
        records: list[SourceRecord] = []
        seen: set[int] = set()
        for match in matches:
            year = int(match.group(1))
            if year in seen:
                continue
            seen.add(year)
            context = self._window(text, match.start(), match.end())
            values = dates_in(context, default_year=year)
            opening = None
            opening_match = re.search(r"(?:apertura|aperto|inizio|dal)\D{0,80}", context, re.IGNORECASE)
            if opening_match:
                labelled = dates_in(context[opening_match.end(): opening_match.end() + 180], default_year=year)
                opening = labelled[0] if labelled else None
            deadline = None
            deadline_match = re.search(r"(?:scadenza|chiusura|entro|termine|presentat\w*\s+entro)\D{0,80}", context, re.IGNORECASE)
            if deadline_match:
                labelled = dates_in(context[deadline_match.end(): deadline_match.end() + 220], default_year=year)
                deadline = labelled[0] if labelled else None
            if opening is None and values:
                opening = values[0]
            if deadline is None and len(values) >= 2:
                deadline = values[-1]
            status = "OPEN" if deadline and deadline >= date.today() else "CLOSED" if deadline else "UNKNOWN"
            records.append(SourceRecord(
                external_id=f"ricerca-finalizzata-{year}",
                title=f"Bando Ricerca Finalizzata {year}",
                official_url=self.page_url,
                funder=self.funder,
                programme=self.programme,
                opening_date=opening,
                deadline=deadline,
                total_budget=amount(context),
                eligible_entities=(
                    "Regioni e Province autonome tramite aziende sanitarie",
                    "Istituto Superiore di Sanità (ISS)",
                    "INAIL",
                    "AGENAS",
                    "IRCCS",
                    "Istituti Zooprofilattici Sperimentali (IIZZSS)",
                ),
                description=clean(f"{self.source_label}: {context}"),
                source_status=status,
            ))
        return records
