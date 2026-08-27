from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import FetchPolicy
from funding_core.models import SourceRecord

from ._common import compact, extract_entities, extract_money, extract_regions, parse_listing_records
from ._v04_common import amount, clean, dates_in, fetch_bytes


class FondazioneModenaAdapter:
    source_id = "fondazione_modena"
    page_url = "https://www.fondazionedimodena.it/bandi/"
    archive_url = "https://www.fondazionedimodena.it/bandi-archiviati/"
    source_label = "Fondazione di Modena"
    funder = "Fondazione di Modena"
    programme = "Bandi Fondazione di Modena"
    max_bytes = 3_000_000
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-MODENA-ARCHIVE -->\n"

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        current = fetch_bytes(self.page_url, policy, label=self.source_label)
        archive = fetch_bytes(self.archive_url, policy, label=f"{self.source_label} archivio")
        combined = current + self._combined_marker.encode("utf-8") + archive
        if len(combined) > policy.max_bytes:
            raise ValueError(f"{self.source_label} paginated response exceeds size limit")
        return combined

    def _include_link(self, official_url: str, title: str) -> bool:
        parsed = urlsplit(official_url)
        path = parsed.path.rstrip("/").lower()
        if parsed.scheme != "https" or parsed.netloc.lower() != "www.fondazionedimodena.it":
            return False
        if not path.startswith("/bandi/") or path == "/bandi":
            return False
        return bool(title and ("bando" in title.casefold() or "contribut" in title.casefold()))

    def _parse_part(self, part: str, *, archived: bool) -> list[SourceRecord]:
        # The common bounded-card parser handles the nested WordPress cards;
        # source-specific post-processing supplies the publication label that
        # is not a generic “apertura” token.
        class _View:
            page_url = self.page_url
            funder = self.funder
            programme = self.programme
            source_label = self.source_label
            url_prefix = "/bandi/"
            url_tokens = ()
            excluded_tokens = ("/bandi-archiviati", "/news/")
            allow_status_context = True
            default_status = "CLOSED" if archived else "OPEN"

            def _clean(self, value: str) -> str:
                return clean(value)

            def _include_link(self, url: str, title: str) -> bool:
                return adapter._include_link(url, title)

            @staticmethod
            def _external_id(url: str, index: int) -> str:
                path = urlsplit(url).path.rstrip("/")
                return re.sub(r"[^a-z0-9]+", "-", path.rsplit("/", 1)[-1].lower()).strip("-") or f"modena-{index}"

        adapter = self
        view = _View()
        rows = parse_listing_records(view, part, allow_status_context=True, default_status="CLOSED" if archived else "OPEN", context_window=2400)
        result: list[SourceRecord] = []
        for record in rows:
            raw_card = record.title
            title = re.split(r"\s+Data di pubblicazione:", raw_card, maxsplit=1, flags=re.IGNORECASE)[0]
            title = re.sub(r"\s+Approfondisci$", "", title, flags=re.IGNORECASE).strip()
            # Locate the card text using the title and a bounded window.  The
            # publication/deadline labels are present in both active/archive
            # listings even when the generic extractor misses a degree symbol.
            context = f"{raw_card} {record.description}"
            dates = dates_in(context, default_year=2026)
            opening = dates[0] if dates else None
            deadline = dates[-1] if dates else record.deadline
            status = "CLOSED" if archived else "OPEN"
            result.append(replace(
                record,
                title=title,
                opening_date=opening or record.opening_date,
                deadline=deadline,
                total_budget=amount(context) or record.total_budget,
                eligible_entities=extract_entities(context) or record.eligible_entities,
                description=compact(context or record.description),
                source_status=status,
                status_authoritative=True,
                regions=extract_regions(context) or record.regions,
                territory="Provincia di Modena",
            ))
        return result

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        parts = text.split(self._combined_marker)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, part in enumerate(parts):
            for record in self._parse_part(part, archived=index > 0):
                if record.external_id in seen:
                    continue
                seen.add(record.external_id)
                records.append(record)
        return records
