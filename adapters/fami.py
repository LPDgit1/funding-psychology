from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import AdapterError, _AnchorTextParser
from funding_core.dates import parse_date
from funding_core.models import SourceRecord
from funding_core.territories import normalize_territory, split_regions

from ._common import (
    DedicatedHtmlAdapter,
    compact,
    decode_html,
    extract_deadline,
    extract_entities,
    extract_money,
    extract_opening,
    extract_regions,
    infer_status,
    opportunity_context_ok,
    _context,
)


class FamiAdapter(DedicatedHtmlAdapter):
    source_id = "fami"
    page_url = "https://fami.dlci.interno.gov.it/accesso-al-fondo/calendario-programmatico-degli-avvisi"
    source_label = "Programma Nazionale FAMI 2021-2027"
    funder = "Ministero dell'Interno — Autorità di Gestione FAMI"
    programme = "PN FAMI 2021-2027"
    url_tokens = ("avvis", "fami", "call", "fondo")
    excluded_tokens = ("faq", "tutorial", "event", "news", "privacy")
    max_bytes = 12_000_000

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        path = urlsplit(official_url).path.rstrip("/").lower()
        # Navigation links such as “Avvisi pubblici” and the calendar page are
        # not individual records.  A candidate must point below an avvisi/bandi
        # collection path (or be supplied by the embedded calendar JSON).
        if path.endswith("/calendario-programmatico-degli-avvisi") or path.endswith("/avvisi-pubblici"):
            return False
        return bool(re.search(r"/(?:avvisi|bandi)/[^/]+$", path))

    def _json_records(self, text: str) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        # Keep support for the small JSON payload used by the current calendar
        # widget without emulating its client-side filters.
        for match in re.finditer(r"<script[^>]+type=[\"']application/json[\"'][^>]*>(.*?)</script>", text, re.I | re.S):
            try:
                payload = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                continue
            values = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
            for index, item in enumerate(values, 1):
                if not isinstance(item, dict):
                    continue
                title = compact(str(item.get("title") or item.get("name") or ""), 300)
                if not title or not opportunity_context_ok(title, str(item), allow_status_context=True):
                    continue
                official_url = urljoin(self.page_url, str(item.get("url") or item.get("link") or self.page_url))
                opening = parse_date(str(item.get("expectedPublication") or item.get("openingDate") or ""))
                deadline = parse_date(str(item.get("expectedDeadline") or item.get("deadline") or ""))
                status = "UPCOMING" if str(item.get("kind") or item.get("type") or "").upper() == "EARLY" else infer_status(str(item), "UNKNOWN")
                records.append(SourceRecord(
                    external_id=str(item.get("id") or f"fami-json-{index}"), title=title,
                    official_url=official_url, funder=self.funder, programme=str(item.get("programme") or self.programme),
                    opening_date=opening, deadline=deadline, total_budget=extract_money(str(item)),
                    eligible_entities=tuple(str(item.get("eligibleEntities") or "").split(";")) if item.get("eligibleEntities") else (),
                    description=compact(str(item.get("description") or item)), source_status=status,
                    regions=split_regions(item.get("regions") if isinstance(item.get("regions"), list) else []),
                    territory=str(item.get("territory") or "Italia"),
                ))
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        json_records = self._json_records(text)
        if json_records:
            return json_records
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(raw_title)
            official_url = urljoin(self.page_url, href)
            if not self._include_link(official_url, title):
                continue
            context = _context(text, href, title, 500)
            if not opportunity_context_ok(title, context, allow_status_context=True):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            early = bool(re.search(r"(?:prossimi avvisi|calendario|previst|expected|early)", f"{title} {context}", re.I))
            published = bool(re.search(r"(?:avviso|call)\s+pubblicat|in\s+corso|apert", context, re.I))
            records.append(SourceRecord(
                external_id=external_id, title=title, official_url=official_url,
                funder=self.funder, programme=self.programme,
                opening_date=extract_opening(context), deadline=extract_deadline(context),
                total_budget=extract_money(context), eligible_entities=extract_entities(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status="UPCOMING" if early else "OPEN" if published else infer_status(context),
                regions=extract_regions(context), territory=normalize_territory(extract_regions(context), context, fallback="Italia"),
            ))
        return records
