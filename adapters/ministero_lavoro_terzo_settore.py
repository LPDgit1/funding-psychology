from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._common import compact, extract_entities, extract_money
from ._v04_common import clean, dates_in, fetch_bytes, page_text


class MinisteroLavoroTerzoSettoreAdapter:
    """Official MLPS annual Third Sector call page.

    The Ministry publishes the annual calls in a single server-rendered page;
    the adapter reads each labelled ``ANNUALITÀ`` block and never follows the
    linked PDF merely to invent fields that the HTML does not expose.
    """

    source_id = "ministero_lavoro_terzo_settore"
    page_url = "https://www.lavoro.gov.it/temi-e-priorita/terzo-settore-e-responsabilita-sociale-imprese/focus-on/volontariato/pagine/fondo-assistenza-bambini-affetti-da-malattia-oncologica"
    source_label = "Ministero del Lavoro – Terzo Settore"
    funder = "Ministero del Lavoro e delle Politiche Sociali"
    programme = "Fondo per l'assistenza dei bambini affetti da malattia oncologica"
    max_bytes = 3_000_000

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    @staticmethod
    def _annual_blocks(text: str) -> list[tuple[int, str]]:
        matches = list(re.finditer(r"ANNUALIT[ÀA]\s+(20\d{2})", text, re.IGNORECASE))
        blocks: list[tuple[int, str]] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            blocks.append((int(match.group(1)), text[match.end():end]))
        return blocks

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = page_text(raw)
        records: list[SourceRecord] = []
        for year, block in self._annual_blocks(text):
            call = re.search(r"\bAvviso\s+(\d+)\s*/\s*(20\d{2})\b", block, re.IGNORECASE)
            if not call:
                continue
            call_year = int(call.group(2))
            if call_year != year:
                continue
            dates = dates_in(block, default_year=year)
            opening = dates[0] if dates else None
            deadline = dates[-1] if dates else None
            # A section also contains approval/linee-operative dates. Keep
            # only the first application window after its submission label.
            window = re.search(r"(?:compilazione\s+della\s+domanda|potr[aà]\s+avvenire|presentat\w*|pervenire).*?(?=Di seguito|APPROVAZIONE|LINEE OPERATIVE|$)", block, re.IGNORECASE | re.DOTALL)
            if window:
                window_dates = dates_in(window.group(0), default_year=year)
                if len(window_dates) >= 2:
                    opening, deadline = window_dates[-2], window_dates[-1]
            # Prefer an explicit applicant label.  The annual page also
            # contains a later “graduatoria/enti assegnatari” paragraph; that
            # is an outcome, not an eligibility category, and must not leak
            # into the opportunity record.
            labelled = re.search(
                r"(?:destinatari|soggetti\s+ammissibili|chi\s+pu[oò]\s+partecipare)\s*[:\-]?\s*([^.;\n]{1,260})",
                block,
                re.IGNORECASE,
            )
            if labelled and "graduator" not in labelled.group(1).casefold():
                entities = (clean(labelled.group(1)),)
            elif re.search(r"\benti\s+del\s+terzo\s+settore\b", block, re.IGNORECASE):
                entities = ("Enti del Terzo Settore",)
            elif re.search(r"associazioni\s+che\s+svolgono\s+attivit[aà]\s+di\s+assistenza", block, re.IGNORECASE):
                entities = ("Associazioni che svolgono attività di assistenza",)
            else:
                entities = ("Associazioni e fondazioni ammissibili secondo l'Avviso",)
            records.append(SourceRecord(
                external_id=f"avviso-{call_year}-{call.group(1)}",
                title=f"Fondo assistenza bambini oncologici — Avviso {call.group(1)}/{call_year}",
                official_url=f"{self.page_url}#annualita-{call_year}",
                funder=self.funder,
                programme=self.programme,
                opening_date=opening,
                deadline=deadline,
                total_budget=extract_money(block),
                eligible_entities=tuple(entities),
                description=compact(f"{self.source_label}: Avviso {call.group(1)}/{call_year}. {block}"),
                source_status="OPEN" if deadline and deadline >= date.today() else "CLOSED" if deadline else "UNKNOWN",
            ))
        return records
