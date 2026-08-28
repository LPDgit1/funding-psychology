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
    # The Ministry maintains a separate official entry point for the annual
    # art. 72/73 CTS fund.  It is intentionally listed explicitly rather than
    # discovered through a broad site crawl.
    secondary_page_url = "https://lavoro.gov.it/temi-e-priorita/terzo-settore-e-responsabilita-sociale-delle-imprese/focus/riforma-terzo-settore/pagine/avviso-2-2025"
    source_label = "Ministero del Lavoro – Terzo Settore"
    funder = "Ministero del Lavoro e delle Politiche Sociali"
    programme = "Fondo per l'assistenza dei bambini affetti da malattia oncologica"
    max_bytes = 3_000_000
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-MLPS-ART72 -->\n"

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        oncology = fetch_bytes(self.page_url, policy, label=self.source_label)
        art72 = fetch_bytes(self.secondary_page_url, policy, label=f"{self.source_label} art.72/73")
        combined = oncology + self._combined_marker.encode("utf-8") + art72
        if len(combined) > policy.max_bytes:
            raise ValueError(f"{self.source_label} combined response exceeds size limit")
        return combined

    @staticmethod
    def _annual_blocks(text: str) -> list[tuple[int, str]]:
        matches = list(re.finditer(r"ANNUALIT[ÀA]\s+(20\d{2})", text, re.IGNORECASE))
        blocks: list[tuple[int, str]] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            blocks.append((int(match.group(1)), text[match.end():end]))
        return blocks

    def _parse_oncology(self, text: str) -> list[SourceRecord]:
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

    def _parse_art72(self, text: str) -> list[SourceRecord]:
        """Parse the canonical Avviso entry without turning its updates into records."""
        call = re.search(r"\bAvviso\s+n?\.??\s*(\d+)\s*/\s*(20\d{2})\b", text, re.IGNORECASE)
        if not call or not re.search(r"art(?:icolo|icoli|\.)\s*72|art(?:icolo|icoli|\.)\s*73", text, re.IGNORECASE):
            return []
        year = int(call.group(2))
        # Keep the first canonical submission window.  Later “riapertura”,
        # commission, graduatoria and rendicontazione paragraphs are updates,
        # not additional opportunities.
        window = re.search(
            r"(?:Periodo\s+di\s+apertura|Modalit[aà]\s+e\s+termini\s+domanda).*?(?=Data\s+di\s+scadenza|Focus\s+Modello|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        window_text = window.group(0) if window else text[:5000]
        dates = dates_in(window_text, default_year=year)
        opening = dates[0] if dates else None
        deadline = dates[1] if len(dates) > 1 else (dates[-1] if dates else None)
        amount = extract_money(text)
        entities = (
            "Organizzazioni di volontariato (ODV) iscritte al RUNTS",
            "Associazioni di promozione sociale (APS) iscritte al RUNTS",
            "Fondazioni del Terzo settore",
            "Reti associative ai sensi dell'art. 41 CTS",
        )
        return [SourceRecord(
            external_id=f"art72-avviso-{call.group(1)}-{year}",
            title=f"Fondo iniziative e progetti di interesse generale nel Terzo settore — Avviso {call.group(1)}/{year}",
            official_url=self.secondary_page_url,
            funder=self.funder,
            programme="Fondo art. 72-73 CTS per iniziative e progetti di interesse generale",
            opening_date=opening,
            deadline=deadline,
            total_budget=amount,
            eligible_entities=entities,
            description=compact(f"{self.source_label}: Avviso {call.group(1)}/{year} per il finanziamento di iniziative e progetti di rilevanza nazionale ai sensi degli artt. 72 e 73 CTS. {window_text}"),
            source_status="OPEN" if deadline and deadline >= date.today() else "CLOSED" if deadline else "UNKNOWN",
        )]

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        # Split the transport payload before extracting text: the combined
        # marker is an HTML comment and is intentionally omitted by
        # ``page_text``.
        if isinstance(raw, bytes):
            raw_parts = raw.split(self._combined_marker.encode("utf-8"))
        else:
            raw_parts = raw.split(self._combined_marker)
        parts = [page_text(part) for part in raw_parts]
        records = self._parse_oncology(parts[0])
        if len(parts) > 1:
            records.extend(self._parse_art72(parts[1]))
        return records
