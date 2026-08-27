from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _DetailTextParser
from funding_core.models import SourceRecord

from ._common import compact, derive_title
from ._v04_common import amount, clean, dates_in, fetch_bytes


class FondazioneCariparmaAdapter:
    source_id = "fondazione_cariparma"
    page_url = "https://www.fondazionecrp.it/contributi/richiedere-un-contributo/bandi-2026/"
    source_label = "Fondazione Cariparma"
    funder = "Fondazione Cariparma"
    programme = "Bandi 2026 Fondazione Cariparma"
    max_bytes = 4_000_000
    detail_enrichment = True

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    def _include(self, url: str, title: str) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "www.fondazionecrp.it":
            return False
        path = parsed.path.rstrip("/").lower()
        prefix = "/contributi/richiedere-un-contributo/bandi-2026"
        if not path.startswith(prefix) or path == prefix:
            return False
        if any(token in path for token in ("/esiti", "/rendicont", "/monitoraggio")):
            return False
        return len(title) >= 8

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = clean(derive_title(text, href, raw_title))
            official_url = urljoin(self.page_url, href)
            if not self._include(official_url, title):
                continue
            # The menu repeats each link several times; path slug is stable.
            slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(official_url).path.rstrip("/").split("/")[-1].lower()).strip("-")
            external_id = slug or f"cariparma-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                description=f"{self.source_label}: bando 2026; dettagli e tempistiche nella scheda ufficiale.",
                source_status="UNKNOWN",
                territory="Provincia di Parma",
            ))
        return records

    @staticmethod
    def _detail_text(raw: bytes) -> str:
        parser = _DetailTextParser()
        parser.feed(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
        if parser.text:
            return parser.text
        from ._v04_common import page_text
        return page_text(raw)

    @staticmethod
    def _window(text: str) -> tuple[date | None, date | None]:
        matches = list(re.finditer(r"Tempistiche(?:\s+Fase\s*\d+)?\s*:?", text, re.IGNORECASE))
        if not matches:
            return None, None
        opening: date | None = None
        deadline: date | None = None
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 380)
            values = dates_in(text[match.end():end], default_year=2026)
            if values:
                opening = min([value for value in (opening, values[0]) if value is not None])
                future_or_latest = values[-1]
                deadline = max([value for value in (deadline, future_or_latest) if value is not None])
        return opening, deadline

    @staticmethod
    def _entities(text: str) -> tuple[str, ...]:
        match = re.search(r"(?:Possono partecipare|Destinatari|Enti ammissibili|rivolt[oa] a)\s*:?\s*([^.;]{1,260})", text, re.IGNORECASE)
        return (clean(match.group(1)),) if match else ()

    def enrich(self, records: list[SourceRecord], policy: FetchPolicy | None = None, *, max_details: int = 40) -> list[SourceRecord]:
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = fetch_bytes(record.official_url, policy, label=f"{self.source_label} detail")
                text = self._detail_text(payload)
                opening, deadline = self._window(text)
                # “Richieste libere” is a rolling channel; the official page
                # intentionally exposes no closing date.
                status = "OPEN" if "richieste libere" in record.title.casefold() else "OPEN" if deadline and deadline >= date.today() else "CLOSED" if deadline else "UNKNOWN"
                entities = self._entities(text) or record.eligible_entities
                enriched.append(replace(
                    record,
                    opening_date=opening or record.opening_date,
                    deadline=deadline or record.deadline,
                    total_budget=amount(text) or record.total_budget,
                    eligible_entities=entities,
                    description=compact(text or record.description),
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
