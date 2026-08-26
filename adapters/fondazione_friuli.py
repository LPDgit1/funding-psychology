from __future__ import annotations

import re

from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, compact, decode_html
from funding_core.dates import parse_date


class FondazioneFriuliAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_friuli"
    page_url = "https://fondazionefriuli.it/contributi-e-bandi/bandi-online/"
    source_label = "Fondazione Friuli"
    funder = "Fondazione Friuli"
    programme = "Bandi e sessioni erogative Fondazione Friuli"

    def enrich(self, records, policy=None, *, max_details: int = 40):
        # The landing page contains the authoritative status/deadline/plafond
        # for each 2026 window.  Fetching the same archive page as a “detail”
        # would incorrectly apply its historical Scaduto label to Welfare.
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records: list[SourceRecord] = []
        # The landing page explicitly announces the three 2026 windows.  A
        # single record per thematic call avoids duplicating its attachments.
        specs = (
            ("istruzione", "Bando Istruzione 2026", "20 marzo 2026", "600 mila euro", "CLOSED"),
            ("restauro", "Bando Restauro 2026", "11 maggio 2026", "500 mila euro", "CLOSED"),
        )
        for key, title, date_text, budget_text, status in specs:
            if not re.search(rf"{key}", text, re.I):
                continue
            records.append(SourceRecord(
                external_id=key + "-2026", title=title,
                official_url=self.page_url, funder=self.funder, programme=self.programme,
                deadline=parse_date(date_text), total_budget=int(re.sub(r"[^0-9]", "", budget_text)) * 1000,
                eligible_entities=("Enti e organizzazioni secondo il regolamento del bando",),
                description=compact(f"{self.source_label}: {title}; scadenza {date_text}; plafond {budget_text}."),
                source_status=status, territory="Friuli-Venezia Giulia",
            ))
        if re.search(r"Bando\s+Welfare[^.]{0,80}(?:lancio\s+)?settembre\s+2026", text, re.I):
            records.append(SourceRecord(
                external_id="welfare-2026", title="Bando Welfare 2026",
                official_url=self.page_url, funder=self.funder, programme=self.programme,
                eligible_entities=("Enti e organizzazioni secondo il regolamento del bando",),
                description="La pagina ufficiale annuncia il lancio del Bando Welfare a settembre 2026; la data puntuale e la scadenza non sono ancora indicate.",
                source_status="UPCOMING", territory="Friuli-Venezia Giulia",
            ))
        return records
