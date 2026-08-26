from __future__ import annotations

import re
from dataclasses import replace

from funding_core.dates import parse_date

from ._common import DedicatedHtmlAdapter


class FondazioneConIlSudAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_con_il_sud"
    page_url = "https://fondazioneconilsud.it/bandi/"
    source_label = "Fondazione CON IL SUD"
    funder = "Fondazione CON IL SUD"
    programme = "Bandi e opportunità Fondazione CON IL SUD"
    url_tokens = ("bando", "avviso", "opportunit", "iniziativa", "cofinanziamento")
    excluded_tokens = ("progetti-sostenuti", "sostenuti", "esiti", "news", "event", "comunicat", "area-riservata")
    allow_status_context = True
    detail_enrichment = False

    def parse(self, raw: bytes | str):
        records = super().parse(raw)
        updated = []
        for record in records:
            if record.deadline is None:
                match = re.search(
                    r"(?:scadenza|scade|termine)\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
                    record.description,
                    re.IGNORECASE,
                )
                if match:
                    deadline = parse_date(match.group(1))
                    if deadline:
                        record = replace(record, deadline=deadline)
            updated.append(record)
        return updated
