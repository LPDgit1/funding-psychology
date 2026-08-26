from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urljoin, urlsplit

from datetime import date
from urllib.request import Request

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _detail_fields
from funding_core.models import SourceRecord

from ._common import (
    DedicatedHtmlAdapter,
    _context,
    compact,
    decode_html,
    extract_deadline,
    extract_entities,
    extract_money,
    extract_regions,
    infer_status,
    opportunity_context_ok,
)


class FondazioneCrcAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_crc"
    page_url = "https://fondazionecrc.it/"
    source_label = "Fondazione CRC"
    funder = "Fondazione CRC"
    programme = "Bandi Fondazione CRC"
    url_tokens = ("bando", "contribut", "scuola", "giovani", "welfare", "comunit")
    excluded_tokens = ("deliberat", "progett", "event", "news", "esit", "privacy", "cookie")
    allow_status_context = True
    detail_enrichment = True

    @staticmethod
    def _card_title(context: str, official_url: str) -> str:
        quoted = re.search(r"\bbando\s+[\"“'«]([^\"”'».!?]+)", context, re.IGNORECASE)
        if quoted:
            return compact(quoted.group(1), 180).strip(" -")
        unquoted = re.search(
            r"\bbando\s+([A-ZÀ-Ý][^.!?,;]{1,100}?)(?=\s+(?:è|e|volto|per|che|sempre|aperto|aperta)\b|[!?.;,]|$)",
            context,
            re.IGNORECASE,
        )
        if unquoted:
            return compact(unquoted.group(1), 180).strip(" -")
        slug = urlsplit(official_url).path.rstrip("/").rsplit("/", 1)[-1]
        return re.sub(r"[-_]", " ", slug).strip().title() or "Bando Fondazione CRC"

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        heading = re.search(r"<h2\b[^>]*>\s*Bandi\s+aperti\b", text, re.IGNORECASE)
        if heading:
            next_heading = re.search(r"<h2\b[^>]*>\s*(?:News|Eventi|Progetti)\b", text[heading.end():], re.IGNORECASE)
            end = heading.end() + next_heading.start() if next_heading else len(text)
            section = text[heading.start():end]
        else:
            section = text
        parser = _AnchorTextParser()
        parser.feed(section)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            official_url = urljoin(self.page_url, href)
            path = urlsplit(official_url).path.lower()
            if not path.startswith("/cosafacciamo/") or "/categorie_cosafacciamo/" in path or path.endswith(".pdf"):
                continue
            context = _context(section, href, raw_title, 1500)
            if re.search(r"contributi?\s+deliberati|progett[oi]\s+sostenuti|esiti|eventi?|news|comunicat", context, re.I):
                continue
            if not re.search(r"\bbando\b", context, re.IGNORECASE):
                continue
            title = self._card_title(context, official_url)
            if not opportunity_context_ok(title, context, allow_status_context=True):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            regions = extract_regions(context)
            records.append(SourceRecord(
                external_id=external_id, title=title, official_url=official_url,
                funder=self.funder, programme=self.programme, deadline=extract_deadline(context),
                total_budget=extract_money(context),
                eligible_entities=extract_entities(context) or ("Enti e organizzazioni ammissibili indicati nel singolo bando",),
                description=compact(f"{self.source_label}: {context}"), source_status=infer_status(context, "OPEN"),
                regions=regions, territory="Provincia di Cuneo",
            ))
        return records

    @staticmethod
    def _fetch_detail(url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError("detail page exceeds size limit for Fondazione CRC")
        return payload

    def enrich(self, records, policy=None, *, max_details: int = 40):
        """Enrich CRC cards without reapplying the generic editorial filter.

        CRC detail pages may mention a webinar or communication alongside a
        real call.  The listing parser has already established opportunity
        context, so dropping the card at this stage would create a live false
        negative.
        """
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        today = date.today()
        enriched = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = self._fetch_detail(record.official_url, policy)
                fields = _detail_fields(payload)
                deadline = fields.get("deadline") or record.deadline
                status = str(fields.get("source_status") or record.source_status)
                if status == "UNKNOWN":
                    status = record.source_status
                if deadline:
                    # The detail page status token can be polluted by
                    # editorial copy; an explicit deadline is the reliable
                    # current/closed discriminator for this listing.
                    status = "CLOSED" if deadline < today else "OPEN"
                enriched.append(replace(
                    record,
                    opening_date=fields.get("opening_date") or record.opening_date,
                    deadline=deadline,
                    total_budget=fields.get("total_budget") or record.total_budget,
                    eligible_entities=tuple(fields.get("eligible_entities") or record.eligible_entities),
                    description=str(fields.get("description") or record.description),
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
