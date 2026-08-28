from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._common import compact, decode_html, extract_entities
from ._v04_common import amount, clean, fetch_bytes, parse_day_date


class FondazioneCrLuccaAdapter:
    """Structured JSON-LD Grant records from Fondazione CR Lucca."""

    source_id = "fondazione_cr_lucca"
    page_url = "https://www.fondazionecarilucca.it/bandi-in-corso"
    archive_url = "https://www.fondazionecarilucca.it/storico-bandi"
    source_label = "Fondazione Cassa di Risparmio di Lucca"
    funder = "Fondazione Cassa di Risparmio di Lucca"
    programme = "Bandi e contributi della Fondazione CR Lucca"
    max_bytes = 12_000_000
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-CRLUCCA-ARCHIVE -->\n"

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        current = fetch_bytes(self.page_url, policy, label=self.source_label)
        archive = fetch_bytes(self.archive_url, policy, label=f"{self.source_label} archivio")
        combined = current + self._combined_marker.encode() + archive
        if len(combined) > policy.max_bytes:
            raise ValueError(f"{self.source_label} combined response exceeds size limit")
        return combined

    @staticmethod
    def _walk_grants(value: object):
        if isinstance(value, dict):
            kind = value.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item).casefold() == "grant" for item in kinds):
                yield value
            for child in value.values():
                yield from FondazioneCrLuccaAdapter._walk_grants(child)
        elif isinstance(value, list):
            for child in value:
                yield from FondazioneCrLuccaAdapter._walk_grants(child)

    @classmethod
    def _jsonld_grants(cls, raw: bytes | str):
        text = decode_html(raw)
        scripts = re.findall(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", text, re.IGNORECASE | re.DOTALL)
        for script in scripts:
            try:
                payload = json.loads(script.strip())
            except (TypeError, json.JSONDecodeError):
                continue
            yield from cls._walk_grants(payload)

    @staticmethod
    def _date(value: object) -> date | None:
        if value is None:
            return None
        return parse_day_date(str(value))

    @staticmethod
    def _same_domain(url: str) -> bool:
        return urlsplit(url).netloc.casefold() in {"www.fondazionecarilucca.it", "fondazionecarilucca.it"}

    def _record(self, grant: dict, *, archive: bool, index: int) -> SourceRecord | None:
        title = clean(grant.get("name"))
        if not title:
            return None
        candidate = clean(grant.get("url"))
        official_url = urljoin(self.archive_url if archive else self.page_url, candidate) if candidate else (self.archive_url if archive else self.page_url)
        if not self._same_domain(official_url):
            official_url = self.archive_url if archive else self.page_url
        description = clean(grant.get("description"))
        published = self._date(grant.get("datePublished"))
        deadline = self._date(grant.get("expires"))
        exhausted = bool(re.search(r"scadut\w*\s+per\s+esaurimento\s+fondi", description, re.IGNORECASE))
        status = "CLOSED" if archive or exhausted or (deadline and deadline < date.today()) else "OPEN"
        external_id = re.sub(r"[^a-z0-9]+", "-", urlsplit(official_url).path.casefold()).strip("-") or f"grant-{index}"
        entities = extract_entities(description)
        if not entities:
            entities = ("Soggetti pubblici e privati secondo il bando",)
        return SourceRecord(
            external_id=external_id,
            title=title,
            official_url=official_url,
            funder=self.funder,
            programme=self.programme,
            opening_date=published,
            deadline=deadline,
            total_budget=amount(description),
            eligible_entities=entities,
            description=compact(f"{self.source_label}: {description}"),
            source_status=status,
            status_authoritative=True,
        )

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        parts = raw.split(self._combined_marker.encode()) if isinstance(raw, bytes) else raw.split(self._combined_marker)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for part_index, part in enumerate(parts[:2]):
            for index, grant in enumerate(self._jsonld_grants(part), 1):
                record = self._record(grant, archive=part_index == 1, index=index)
                if record is None or record.external_id in seen:
                    continue
                seen.add(record.external_id)
                records.append(record)
        return records
