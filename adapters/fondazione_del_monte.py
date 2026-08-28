from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import date
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser
from funding_core.models import SourceRecord

from ._common import _context, compact, decode_html, extract_entities, extract_money, infer_status
from ._v04_common import clean, dates_in, fetch_bytes, page_text


class FondazioneDelMonteAdapter:
    """Official Fondazione del Monte di Bologna e Ravenna grant listing."""

    source_id = "fondazione_del_monte"
    page_url = "https://fondazionedelmonte.it/chiedi-un-contributo/"
    source_label = "Fondazione del Monte di Bologna e Ravenna"
    funder = "Fondazione del Monte di Bologna e Ravenna"
    programme = "Bandi e contributi della Fondazione del Monte"
    max_bytes = 8_000_000
    _detail = re.compile(r"^https://fondazionedelmonte\.it/bando/", re.IGNORECASE)
    _reject_title = re.compile(r"call\s+for\s+papers|candid[aà]\s+una\s+buona\s+pratica|premio|progetto\s+di", re.IGNORECASE)

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        return fetch_bytes(self.page_url, policy or FetchPolicy(max_bytes=self.max_bytes), label=self.source_label)

    @staticmethod
    def _normal_title(value: str) -> str:
        return clean(unicodedata.normalize("NFKC", value))

    @staticmethod
    def _dates(value: str, *, default_year: int | None = None) -> list[date]:
        # ``dates_in`` intentionally avoids comma-bearing Italian dates (for
        # example “22 Ottobre, 2025”); normalize that source spelling before
        # handing the tokens to the shared parser so an old card cannot be
        # silently assigned the current year.
        normalized = re.sub(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+),\s*(\d{4})", r"\1 \2 \3", value)
        return dates_in(normalized, default_year=default_year)

    def _listing_records(self, text: str) -> list[SourceRecord]:
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        grouped: dict[str, list[str]] = {}
        for href, raw_title in parser.links:
            grouped.setdefault(href, []).append(raw_title)
        for index, (href, raw_titles) in enumerate(grouped.items(), 1):
            official_url = urljoin(self.page_url, href)
            if not self._detail.match(official_url):
                continue
            # Cards repeat a status link (“Bando scaduto”) and a visible
            # heading for the same URL.  Prefer the informative heading.
            candidates = [self._normal_title(value) for value in raw_titles]
            title = max(
                candidates,
                key=lambda value: (0 if re.fullmatch(r"bando\s+scaduto|scaduto", value, re.IGNORECASE) else 1, len(value)),
                default="",
            )
            if not title or self._reject_title.search(title) or title.casefold() in {"scopri", "scopri di più", "leggi il bando"}:
                continue
            context = _context(text, href, title, 1300)
            # The listing contains cards for real bandi and a few editorial
            # project pages.  A bando URL plus a title is the source-local
            # discovery contract; detail enrichment performs the bounded
            # opportunity check when available.
            slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(official_url).path.casefold()).strip("-")
            external_id = slug or f"bando-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            dates = self._dates(context, default_year=date.today().year)
            deadline = dates[-1] if dates else None
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                opening_date=dates[0] if len(dates) >= 2 else None,
                deadline=deadline,
                total_budget=extract_money(context),
                eligible_entities=extract_entities(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status=infer_status(context, "UNKNOWN"),
            ))
        return records

    @staticmethod
    def _future_records(text: str) -> list[SourceRecord]:
        # The official page lists the next editions inline, without detail
        # links.  They are genuine upcoming application windows and therefore
        # need explicit canonical records rather than being dropped as prose.
        records: list[SourceRecord] = []
        pattern = re.compile(
            r"AREA\s+(CULTURA|SOCIALE)\s+BANDO\s+([A-ZÀ-ÖØ-Ý]+)\s*[-–]\s*([^|]+?)\s*\|\s*"
            r"Apertura:\s*([^\-]+?)\s*-\s*Chiusura:\s*([^|]+?)(?=AREA\s+|$)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            area, code, edition, opening_text, closing_text = match.groups()
            opening = FondazioneDelMonteAdapter._dates(opening_text, default_year=2026)
            closing = FondazioneDelMonteAdapter._dates(closing_text, default_year=2026)
            title = clean(f"Bando {code.upper()} – {edition}")
            slug = re.sub(r"[^a-z0-9]+", "-", f"{code}-{edition}".casefold()).strip("-")
            records.append(SourceRecord(
                external_id=f"upcoming-{slug}",
                title=title,
                official_url="https://fondazionedelmonte.it/chiedi-un-contributo/#prossimi-bandi",
                funder="Fondazione del Monte di Bologna e Ravenna",
                programme=f"Bandi area {area.title()}",
                opening_date=opening[0] if opening else None,
                deadline=closing[0] if closing else None,
                eligible_entities=(),
                description=compact(f"{title}; apertura e chiusura previste come riportate nella pagina ufficiale."),
                source_status="UPCOMING",
                status_authoritative=True,
            ))
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records = self._listing_records(text)
        records.extend(self._future_records(text))
        seen: set[str] = set()
        return [record for record in records if not (record.external_id in seen or seen.add(record.external_id))]

    def enrich(self, records: list[SourceRecord], policy: FetchPolicy | None = None, *, max_details: int = 20) -> list[SourceRecord]:
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details or not self._detail.match(record.official_url):
                enriched.append(record)
                continue
            try:
                payload = fetch_bytes(record.official_url, policy, label=f"{self.source_label} dettaglio")
                text = page_text(payload)
                if self._reject_title.search(record.title) or re.search(r"call\s+for\s+papers|candid[aà]\s+una\s+buona\s+pratica", text, re.IGNORECASE):
                    continue
                values = self._dates(text, default_year=date.today().year)
                labelled = re.search(r"(?:scadenza|chiusura|termine)[^.;]{0,100}", text, re.IGNORECASE)
                labelled_values = self._dates(text[labelled.end(): labelled.end() + 220], default_year=date.today().year) if labelled else []
                deadline = labelled_values[0] if labelled_values else record.deadline
                opening = record.opening_date
                if opening is None and len(values) >= 2:
                    opening = values[0]
                detail_status = infer_status(text, record.source_status)
                status = detail_status
                if detail_status != "CLOSED" and deadline:
                    status = "OPEN" if deadline >= date.today() else "CLOSED"
                enriched.append(replace(
                    record,
                    opening_date=opening,
                    deadline=deadline,
                    total_budget=extract_money(text) or record.total_budget,
                    eligible_entities=extract_entities(text) or record.eligible_entities,
                    description=compact(text or record.description),
                    source_status=status,
                    status_authoritative=bool(re.search(r"\b(?:scadut\w*|chius\w*|apert\w*)\b", text, re.IGNORECASE)) or record.status_authoritative,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched
