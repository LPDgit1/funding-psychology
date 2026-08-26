from __future__ import annotations

import io
import re
from dataclasses import replace
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from funding_core.adapters import AdapterError, FetchPolicy, _detail_fields
from funding_core.models import SourceRecord
from funding_core.dates import parse_date

from ._common import DedicatedHtmlAdapter, compact, decode_html

try:
    from pdfminer.high_level import extract_text as _extract_pdf_text
except ImportError:  # pragma: no cover - the bundled sync runtime provides pdfminer
    _extract_pdf_text = None


class FondazioneSardegnaAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_sardegna"
    page_url = "https://www.fondazionedisardegna.it/contributi/bandi-rol"
    source_label = "Fondazione di Sardegna"
    funder = "Fondazione di Sardegna"
    programme = "Bandi annuali 2026 — Fondazione di Sardegna"
    detail_enrichment = True

    _sectors = {
        "arte": "Arte",
        "sviluppo locale": "Sviluppo locale",
        "volontariato": "Volontariato",
        "salute e medicina": "Salute e Medicina",
    }

    def fetch(self, policy=None) -> bytes:
        return super().fetch(policy)

    def _sector_url(self, text: str, label: str) -> str:
        marker = re.search(
            rf"<(?:div|span)[^>]*class=[\"'][^\"']*text-rombus[^\"']*[\"'][^>]*>\s*{re.escape(label)}\s*</(?:div|span)>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not marker:
            return self.page_url
        prefix = text[max(0, marker.start() - 1800):marker.start()]
        candidates = re.findall(r"<a\s+href=[\"']\s*([^\"']+?)\s*[\"']", prefix, re.IGNORECASE)
        candidates = [item.strip() for item in candidates if not item.strip().lower().startswith(("javascript:", "#"))]
        return urljoin(self.page_url, candidates[-1]) if candidates else self.page_url

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records: list[SourceRecord] = []
        for key, label in self._sectors.items():
            if not re.search(rf"{re.escape(key)}", text, re.I):
                continue
            section = re.search(rf"{re.escape(key)}(.{{0,500}}?)(?:Bandi\s+2026|Bando\s+2026)", text, re.I | re.S)
            context = compact(section.group(0) if section else f"{label}: Bandi 2026", 800)
            records.append(SourceRecord(
                external_id=f"bando-annuale-2026-{key.replace(' ', '-')}",
                title=f"Bando annuale 2026 — {label}", official_url=self._sector_url(text, label),
                funder=self.funder, programme=self.programme,
                eligible_entities=("Enti e organizzazioni ammissibili secondo il bando di settore",),
                description=compact(f"{self.source_label}: {context}. La presentazione avviene tramite ROL; verificare il bando di settore e il termine pubblicato.") ,
                source_status="UNKNOWN", territory="Sardegna",
            ))
        return records

    @staticmethod
    def _pdf_deadline(text: str):
        # The 2026 annual calls all use the same official ROL window.  Some
        # sector PDFs also mention later dates for related initiatives; prefer
        # the general annual-call deadline when it is present.
        annual_window = re.search(
            r"alle\s+ore\s*15[^.;]{0,120}?\b5\s+dicembre\s+2025\b",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if annual_window:
            return parse_date("5 dicembre 2025")
        date_pattern = r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b"
        patterns = (
            rf"(?:alle\s+ore\s*15|ore\s*15)[^.;]{{0,80}}?(?:del|di)\s*({date_pattern})",
            rf"(?:fino\s+al|entro\s+il|entro\s+la\s+data\s+del)\s*({date_pattern})",
            rf"(?:presentate|presentazione)[^.;]{{0,350}}?({date_pattern})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed = parse_date(match.group(1))
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _pdf_text(payload: bytes) -> str:
        if _extract_pdf_text is None:
            return ""
        try:
            return _extract_pdf_text(io.BytesIO(payload))
        except Exception:
            return ""

    def _fetch_detail(self, url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with urlopen(request, timeout=policy.timeout_seconds) as response:
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError(f"detail page exceeds size limit for {self.source_label}")
        return payload

    def _fetch_pdf(self, url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "application/pdf", "User-Agent": policy.user_agent})
        with urlopen(request, timeout=policy.timeout_seconds) as response:
            payload = response.read(min(policy.max_bytes * 2, 6_000_000) + 1)
        if len(payload) > min(policy.max_bytes * 2, 6_000_000):
            raise AdapterError(f"PDF exceeds size limit for {self.source_label}")
        if not payload.startswith(b"%PDF"):
            raise AdapterError(f"official document is not a PDF for {self.source_label}")
        return payload

    def enrich(self, records, policy=None, *, max_details: int = 40):
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        today = date.today()
        enriched = []
        for index, record in enumerate(records):
            if index >= max_details or record.official_url == self.page_url:
                enriched.append(record)
                continue
            try:
                detail_payload = self._fetch_detail(record.official_url, policy)
                detail_text = decode_html(detail_payload)
                fields = _detail_fields(detail_payload)
                # Match the label and href on the same anchor.  The detail
                # page can list a related project PDF before the annual-call
                # PDF; a page-wide dotall regex would silently select the
                # wrong document.
                pdf_match = None
                for anchor in re.finditer(
                    r"<a[^>]+href=[\"']([^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(.*?)</a>",
                    detail_text,
                    re.IGNORECASE | re.DOTALL,
                ):
                    anchor_label = re.sub(r"<[^>]+>", " ", anchor.group(2))
                    if re.search(r"Bando\s+Annuale\s+2026", anchor_label, re.IGNORECASE):
                        pdf_match = anchor
                        break
                deadline = None
                description = str(fields.get("description") or record.description)
                if pdf_match:
                    pdf_url = urljoin(record.official_url, pdf_match.group(1).strip())
                    pdf_text = self._pdf_text(self._fetch_pdf(pdf_url, policy))
                    deadline = self._pdf_deadline(pdf_text)
                    if pdf_text:
                        description = compact(f"{description} Termine verificato dal PDF ufficiale: {pdf_url}.", 2400)
                deadline = deadline or record.deadline
                status = "CLOSED" if deadline and deadline < today else "OPEN" if deadline else record.source_status
                enriched.append(replace(
                    record,
                    deadline=deadline,
                    eligible_entities=tuple(fields.get("eligible_entities") or record.eligible_entities),
                    description=description,
                    source_status=status,
                ))
            except (AdapterError, HTTPError, URLError, OSError, ValueError):
                enriched.append(record)
        return enriched
