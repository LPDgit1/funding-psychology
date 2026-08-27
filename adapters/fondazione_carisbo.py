from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date
from html import unescape
from urllib.parse import urljoin

from funding_core.adapters import AdapterError, FetchPolicy, _DetailTextParser
from funding_core.dates import parse_date
from funding_core.models import SourceRecord

from ._v04_common import amount, clean, dates_in, fetch_bytes, page_text


class FondazioneCarisboAdapter:
    """WordPress REST adapter for Carisbo's own bando announcements."""

    source_id = "fondazione_carisbo"
    page_url = "https://fondazionecarisbo.it/bandi-e-progetti/bandi/"
    api_url = "https://fondazionecarisbo.it/wp-json/wp/v2/posts?search=bando&per_page=100&_fields=id,link,title,content,date,modified"
    source_label = "Fondazione Carisbo"
    funder = "Fondazione Carisbo"
    programme = "Bandi Fondazione Carisbo"
    max_bytes = 4_000_000

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.api_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label, accept="application/json", content_types={"application/json"})

    @staticmethod
    def _title(value: object) -> str:
        if isinstance(value, dict):
            value = value.get("rendered", "")
        return clean(re.sub(r"<[^>]+>", " ", unescape(str(value or ""))))

    @staticmethod
    def _body(value: object) -> str:
        if isinstance(value, dict):
            value = value.get("rendered", "")
        return clean(re.sub(r"<[^>]+>", " ", unescape(str(value or ""))))

    @staticmethod
    def _deadline(body: str, year: int) -> date | None:
        match = re.search(r"accessibile\s+fino\s+all?'?\s*([^,.;]{1,50})", body, re.IGNORECASE)
        if match:
            values = dates_in(match.group(1), default_year=year)
            if values:
                return values[-1]
        values = dates_in(body, default_year=year)
        return values[-1] if values else None

    @staticmethod
    def _detail_url(body_html: str, post_link: str) -> str:
        match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>\s*Vai al bando", body_html, re.IGNORECASE | re.DOTALL)
        return unescape(match.group(1)) if match else post_link

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (ValueError, TypeError) as exc:
            raise AdapterError("Fondazione Carisbo REST response is not valid JSON") from exc
        if not isinstance(payload, list):
            raise AdapterError("Fondazione Carisbo REST response is not a list")
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = self._title(item.get("title"))
            # The REST search also returns external Fondo/Con i Bambini posts,
            # result announcements and projects.  Keep only Carisbo's own
            # “Aperto/Prorogato il bando” announcements.
            if not re.search(r"^(?:Aperto|Prorogat[oa])\b.*\bbando\b", title, re.IGNORECASE):
                continue
            body_html = str(item.get("content", {}).get("rendered", "") if isinstance(item.get("content"), dict) else item.get("content") or "")
            body = self._body(body_html)
            post_link = str(item.get("link") or self.page_url)
            official_url = urljoin(self.page_url, self._detail_url(body_html, post_link))
            if not official_url.startswith(("https://fondazionecarisbo.it/", "https://www.fondazionecarisbo.it/")):
                continue
            external_id = str(item.get("id") or re.sub(r"[^a-z0-9]+", "-", official_url.lower()).strip("-"))
            if external_id in seen:
                continue
            seen.add(external_id)
            year_match = re.search(r"\b(20\d{2})\b", title)
            post_date = parse_date(str(item.get("date") or ""))
            year = int(year_match.group(1)) if year_match else (post_date.year if post_date else 2026)
            deadline = self._deadline(body, year)
            records.append(SourceRecord(
                external_id=f"post-{external_id}",
                title=re.sub(r"^(?:Aperto|Prorogat[oa])\s+il\s+bando\s+", "", title, flags=re.IGNORECASE),
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                deadline=deadline,
                total_budget=amount(body),
                eligible_entities=("Soggetti senza scopo di lucro e Enti del Terzo Settore",),
                description=body[:1600],
                source_status="OPEN" if deadline is None or deadline >= date.today() else "CLOSED",
                territory="Città metropolitana di Bologna",
            ))
        return records

    @staticmethod
    def _detail_text(raw: bytes) -> str:
        parser = _DetailTextParser()
        parser.feed(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
        if parser.text:
            return parser.text
        return page_text(raw)

    @staticmethod
    def _entities(text: str) -> tuple[str, ...]:
        match = re.search(r"(?:soggetti\s+ammissibili|destinatari|rivolto\s+a|possono\s+partecipare)\s*:?\s*([^.;]{1,260})", text, re.IGNORECASE)
        return (clean(match.group(1)),) if match else ()

    def enrich(self, records: list[SourceRecord], policy: FetchPolicy | None = None, *, max_details: int = 12) -> list[SourceRecord]:
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = fetch_bytes(record.official_url, policy, label=f"{self.source_label} detail")
                text = self._detail_text(payload)
                explicit_status = "CLOSED" if re.search(r"\b(?:in\s+valutazione|chius[oa]|conclus[oa]|scadut[oa])\b", text, re.IGNORECASE) else "OPEN" if re.search(r"\b(?:aperto|aperta|in\s+corso)\b", text, re.IGNORECASE) else None
                detail_dates = dates_in(text, default_year=2026)
                deadline = detail_dates[-1] if detail_dates and re.search(r"(?:scadenza|fino\s+al|accessibile)", text, re.IGNORECASE) else record.deadline
                enriched.append(replace(
                    record,
                    deadline=deadline,
                    total_budget=amount(text) or record.total_budget,
                    eligible_entities=self._entities(text) or record.eligible_entities,
                    description=text[:1600] or record.description,
                    source_status=explicit_status or record.source_status,
                    status_authoritative=bool(explicit_status),
                    territory="Città metropolitana di Bologna" if "Città metropolitana di Bologna" in text else record.territory,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
