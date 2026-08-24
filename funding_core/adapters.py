from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from urllib.request import Request, urlopen

from .models import SourceRecord


@dataclass(frozen=True)
class FetchPolicy:
    timeout_seconds: int = 20
    max_bytes: int = 8_000_000
    user_agent: str = "FundingIntelligencePsychology/0.1 (+source-monitor)"


class VenetoFseCalendarAdapter:
    """Small deterministic parser for the official FSE+ calendar CSV.

    Live verification remains manual because the official CSV is currently
    distributed through Google Drive and may be blocked by local TLS policy.
    """

    source_id = "veneto-fse-calendar"
    page_url = "https://programmazione-ue-2021-2027.regione.veneto.it/fse/fse-calendario-inviti-a-presentare-proposte"

    def fetch(self, url: str, policy: FetchPolicy = FetchPolicy()) -> bytes:
        request = Request(url, headers={"User-Agent": policy.user_agent, "Accept": "text/csv,text/plain;q=0.9"})
        with urlopen(request, timeout=policy.timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/csv", "text/plain", "application/octet-stream", "application/vnd.ms-excel"}:
                raise ValueError(f"unexpected content type: {content_type}")
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise ValueError("download exceeds size limit")
        return payload

    @staticmethod
    def _date(value: str):
        value = value.strip()
        for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%m/%Y"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                continue
        return None

    def parse(self, raw: bytes) -> list[SourceRecord]:
        text = raw.decode("utf-8-sig", errors="strict")
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        records: list[SourceRecord] = []
        for index, row in enumerate(reader, 1):
            normalized = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
            title = normalized.get("titolo") or normalized.get("titolo dell'invito") or normalized.get("denominazione") or ""
            if not title:
                continue
            records.append(SourceRecord(
                external_id=normalized.get("id") or f"calendar-row-{index}", title=title,
                official_url=normalized.get("url") or self.page_url, funder="Regione del Veneto",
                programme="PR Veneto FSE+ 2021-2027",
                opening_date=self._date(normalized.get("data prevista di apertura", "") or normalized.get("apertura", "")),
                total_budget=_money(normalized.get("importo totale", "") or normalized.get("dotazione", "")),
                eligible_entities=tuple(filter(None, [normalized.get("soggetti ammissibili", "")])),
                description=normalized.get("obiettivo specifico", "") or normalized.get("descrizione", ""),
                source_status="UPCOMING",
            ))
        return records


def _money(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None
