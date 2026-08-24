from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import SourceRecord


@dataclass(frozen=True)
class FetchPolicy:
    timeout_seconds: int = 20
    max_bytes: int = 8_000_000
    retries: int = 2
    user_agent: str = "FundingIntelligencePsychology/0.1 (+source-monitor)"


class AdapterError(RuntimeError):
    """A source failure that should leave the previous valid data untouched."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class VenetoFseCalendarAdapter:
    """Small deterministic parser for the official FSE+ calendar CSV.

    Live verification remains manual because the official CSV is currently
    distributed through Google Drive and may be blocked by local TLS policy.
    """

    source_id = "veneto-fse-calendar"
    page_url = "https://programmazione-ue-2021-2027.regione.veneto.it/fse/fse-calendario-inviti-a-presentare-proposte"

    def fetch(self, url: str, policy: FetchPolicy = FetchPolicy()) -> bytes:
        request = Request(url, headers={"User-Agent": policy.user_agent, "Accept": "text/csv,text/plain;q=0.9"})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    content_type = response.headers.get_content_type()
                    if content_type not in {"text/csv", "text/plain", "application/octet-stream", "application/vnd.ms-excel"}:
                        raise AdapterError(f"unexpected content type: {content_type}")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from Veneto FSE+ calendar", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for Veneto FSE+ calendar: {exc.reason}") from exc
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


class EuFundingTendersAdapter:
    """Official EU Funding & Tenders Portal SEDIA search adapter.

    The Portal documents a public POST search endpoint using multipart fields
    (`query`, `languages`, `displayFields`). No user credential is required.
    """

    source_id = "eu-funding-tenders"
    endpoint = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    portal_url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home"
    topic_url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/"

    open_statuses = {"31094502", "31094501", "31094503"}
    grant_types = ("1", "8")
    display_fields = (
        "identifier", "reference", "title", "status", "startDate", "deadlineDate",
        "description", "frameworkProgramme", "typesOfAction", "callIdentifier",
        "participantTypes", "budget", "grantAmount",
    )

    def build_query(self) -> dict:
        return {
            "bool": {
                "must": [
                    {"terms": {"type": list(self.grant_types)}},
                    {"terms": {"status": sorted(self.open_statuses)}},
                    {"term": {"programmePeriod": "2021 - 2027"}},
                ],
            },
        }

    @staticmethod
    def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
        boundary = "----FundingIntelligenceBoundary7d4a"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n'.encode(),
                b"Content-Type: application/json\r\n\r\n",
                value.encode("utf-8"), b"\r\n",
            ])
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=25_000_000)) -> bytes:
        query = json.dumps(self.build_query(), ensure_ascii=False, separators=(",", ":"))
        languages = json.dumps(["en"])
        display_fields = json.dumps(list(self.display_fields))
        body, content_type = self._multipart({
            "query": query,
            "languages": languages,
            "displayFields": display_fields,
        })
        url = f"{self.endpoint}?apiKey=SEDIA&text=*&pageSize=100&pageNumber=1"
        request = Request(url, data=body, method="POST", headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": policy.user_agent,
        })
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() != "application/json":
                        raise AdapterError("unexpected content type from EU Funding & Tenders API")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                hint = "retry later" if exc.code in {429, 500, 502, 503, 504} else "check source contract"
                raise AdapterError(f"HTTP {exc.code} from EU Funding & Tenders API ({hint})", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for EU Funding & Tenders API: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("EU Funding & Tenders response exceeds download size limit")
        return payload

    @staticmethod
    def _values(metadata: object, *keys: str) -> list[str]:
        if not isinstance(metadata, dict):
            return []
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if value is not None and str(value).strip():
                return [str(value).strip()]
        return []

    @staticmethod
    def _date(value: str | None) -> date | None:
        if not value:
            return None
        candidate = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            try:
                return parsedate_to_datetime(candidate).date()
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _money(values: list[str]) -> int | None:
        for value in values:
            digits = re.sub(r"[^0-9]", "", value)
            if digits:
                return int(digits)
        return None

    @staticmethod
    def _status(values: list[str]) -> str:
        code = values[0] if values else ""
        return {"31094501": "UPCOMING", "31094502": "OPEN", "31094503": "CLOSED"}.get(code, "UNKNOWN")

    def parse(self, raw: bytes | str | dict) -> list[SourceRecord]:
        try:
            payload = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AdapterError("EU Funding & Tenders response is not valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise AdapterError("EU Funding & Tenders response has no results list")

        records: list[SourceRecord] = []
        for index, result in enumerate(payload["results"], 1):
            if not isinstance(result, dict):
                continue
            metadata = result.get("metadata")
            identifier = self._values(metadata, "identifier", "callIdentifier")
            titles = self._values(metadata, "title") or self._values(result, "summary", "content")
            title = titles[0] if titles else ""
            if not title:
                continue
            urls = self._values(metadata, "url", "esST_URL") or self._values(result, "url")
            official_url = urls[0] if urls else (self.topic_url + identifier[0] if identifier else self.portal_url)
            if not official_url.startswith("https://"):
                official_url = self.portal_url
            description = (self._values(metadata, "description") or self._values(result, "summary", "content"))
            records.append(SourceRecord(
                external_id=identifier[0] if identifier else f"eu-result-{index}",
                title=title,
                official_url=official_url,
                funder="Unione Europea",
                programme=(self._values(metadata, "frameworkProgramme") or ["Funding & Tenders Portal"])[0],
                opening_date=self._date((self._values(metadata, "startDate") or [None])[0]),
                deadline=self._date((self._values(metadata, "deadlineDate") or [None])[0]),
                total_budget=self._money(self._values(metadata, "budget", "grantAmount")),
                eligible_entities=tuple(self._values(metadata, "participantTypes")),
                description=description[0] if description else "",
                source_status=self._status(self._values(metadata, "status")),
            ))
        return records


def _money(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None
