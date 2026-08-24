from __future__ import annotations

import csv
import html
import io
import json
import re
import time
from dataclasses import dataclass, replace
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
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
    source_label = "Veneto FSE+"

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
                raise AdapterError(f"HTTP {exc.code} from {self.source_label} calendar", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for {self.source_label} calendar: {exc.reason}") from exc
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


class VenetoFesrCalendarAdapter(VenetoFseCalendarAdapter):
    """Same CSV contract for the Veneto FESR+ calendar.

    The current FESR page points to the regional cronoprogramma HTML rather
    than exposing a stable CSV URL.  Keeping the parser available lets us
    validate an exported file immediately, while live discovery remains an
    explicit source-contract task.
    """

    source_id = "veneto-fesr-calendar"
    page_url = "https://programmazione-ue-2021-2027.regione.veneto.it/fesr/fesr-calendario-inviti-a-presentare-proposte"
    source_label = "Veneto FESR+"

    def parse(self, raw: bytes) -> list[SourceRecord]:
        return [
            replace(record, programme="PR Veneto FESR+ 2021-2027", official_url=self.page_url)
            for record in super().parse(raw)
        ]


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


class _ErasmusDeadlineRowsParser(HTMLParser):
    """Extract only the explicit deadline rows from the official page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._div_depth = 0
        self._row_depth: int | None = None
        self._column_depth: int | None = None
        self._row: list[str] | None = None
        self._column: list[str] | None = None
        self.rows: list[list[str]] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div":
            self._div_depth += 1
            classes = self._classes(attrs)
            if self._row is None and {"row", "riga"}.issubset(classes):
                self._row = []
                self._row_depth = self._div_depth
            elif self._row is not None and self._column is None and "col-lg" in classes:
                self._column = []
                self._column_depth = self._div_depth
        elif self._column is not None and tag in {"br", "p", "li"}:
            self._column.append(" ")

    def handle_data(self, data: str) -> None:
        if self._column is not None:
            self._column.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        if self._column is not None and self._div_depth == self._column_depth:
            self._row.append(re.sub(r"\s+", " ", "".join(self._column)).strip())
            self._column = None
            self._column_depth = None
        if self._row is not None and self._div_depth == self._row_depth:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._row_depth = None
        self._div_depth -= 1


class ErasmusIndireAdapter:
    """Official Erasmus+ national deadline table, limited to INDIRE rows."""

    source_id = "erasmus-indire"
    page_url = "https://www.erasmusplus.it/programma/scadenze/"
    source_label = "Erasmus+ INDIRE"

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=10_000_000)) -> bytes:
        request = Request(self.page_url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError("unexpected content type from Erasmus+ INDIRE page")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from Erasmus+ INDIRE page", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for Erasmus+ INDIRE page: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("Erasmus+ INDIRE page exceeds download size limit")
        return payload

    @staticmethod
    def _date(value: str) -> date | None:
        months = {
            "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
            "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
            "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        }
        match = re.search(r"(\d{1,2})\s+([A-Za-zàèéìòù]+)(?:\s+(\d{4}))?", value, re.IGNORECASE)
        if match:
            month = months.get(match.group(2).lower())
            if month:
                try:
                    return date(int(match.group(3) or "2026"), month, int(match.group(1)))
                except ValueError:
                    return None
        match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        parser = _ErasmusDeadlineRowsParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, columns in enumerate(parser.rows, 1):
            if len(columns) < 3:
                continue
            title = self._clean(columns[0])
            sector = self._clean(columns[1])
            deadline_text = self._clean(columns[2])
            agency = self._clean(columns[3]) if len(columns) > 3 else ""
            if not title or "INDIRE" not in agency.upper():
                continue
            deadline = self._date(deadline_text)
            key = f"{title}|{sector}|{deadline_text}"
            if key in seen:
                continue
            seen.add(key)
            identifier = re.sub(r"[^a-z0-9]+", "-", f"2026-{title}-{sector}".lower()).strip("-")
            records.append(SourceRecord(
                external_id=identifier or f"erasmus-indire-row-{index}",
                title=f"Erasmus+ — {title}",
                official_url=self.page_url,
                funder="Agenzia nazionale Erasmus+ INDIRE",
                programme="Erasmus+ 2026",
                deadline=deadline,
                eligible_entities=(sector,) if sector else (),
                description=f"Settore: {sector}. Scadenza indicata dalla pagina ufficiale: {deadline_text}.",
                source_status="UNKNOWN",
            ))
        return records


class AigOpportunitiesAdapter:
    """Official AIG opportunities archive via its public WordPress REST API."""

    source_id = "aig-opportunities"
    page_url = "https://agenziagioventu.gov.it/news/opportunita-aig/"
    endpoint = "https://agenziagioventu.gov.it/wp-json/wp/v2/posts"
    category_id = 551

    def build_query(self) -> dict[str, str]:
        return {
            "categories": str(self.category_id),
            "per_page": "100",
            "_fields": "id,date,modified,link,title,content",
        }

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=8_000_000)) -> bytes:
        from urllib.parse import urlencode

        request = Request(
            f"{self.endpoint}?{urlencode(self.build_query())}",
            headers={"Accept": "application/json", "User-Agent": policy.user_agent},
        )
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() != "application/json":
                        raise AdapterError("unexpected content type from AIG opportunities API")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from AIG opportunities API", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for AIG opportunities API: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("AIG opportunities response exceeds download size limit")
        return payload

    @staticmethod
    def _clean(value: str) -> str:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _date(value: str) -> date | None:
        months = {
            "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
            "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
            "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
        }
        match = re.search(r"(\d{1,2})\s+([A-Za-zàèéìòù]+)(?:\s+(\d{4}))?", value, re.IGNORECASE)
        if match:
            month = months.get(match.group(2).lower())
            if month:
                try:
                    return date(int(match.group(3) or "2026"), month, int(match.group(1)))
                except ValueError:
                    return None
        match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None
        return None

    def parse(self, raw: bytes | str | list[dict]) -> list[SourceRecord]:
        try:
            payload = raw if isinstance(raw, list) else json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AdapterError("AIG opportunities response is not valid JSON") from exc
        if not isinstance(payload, list):
            raise AdapterError("AIG opportunities response is not a list")
        records: list[SourceRecord] = []
        for index, item in enumerate(payload, 1):
            if not isinstance(item, dict):
                continue
            title = self._clean(str((item.get("title") or {}).get("rendered", "")))
            url = str(item.get("link") or self.page_url)
            content = self._clean(str((item.get("content") or {}).get("rendered", "")))
            if not title or not url.startswith("https://"):
                continue
            deadline_match = re.search(r"(?:scadenza|entro|termine)[^.!?]{0,160}", content, re.IGNORECASE)
            deadline = self._date(deadline_match.group(0)) if deadline_match else None
            records.append(SourceRecord(
                external_id=str(item.get("id") or f"aig-result-{index}"),
                title=title,
                official_url=url,
                funder="Agenzia Italiana per la Gioventù",
                programme="AIG — Opportunità",
                deadline=deadline,
                description=content[:1200],
                source_status="UNKNOWN",
            ))
        return records


class InterregItalyCroatiaAdapter:
    """The current Interreg Italy–Croatia call page has structured call text."""

    source_id = "interreg-italy-croatia"
    page_url = "https://www.italy-croatia.eu/4th-call-for-proposals"

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=15_000_000)) -> bytes:
        request = Request(self.page_url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError("unexpected content type from Interreg Italy–Croatia page")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from Interreg Italy–Croatia page", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for Interreg Italy–Croatia page: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("Interreg Italy–Croatia page exceeds download size limit")
        return payload

    @staticmethod
    def _clean(value: str) -> str:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _date(value: str) -> date | None:
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _money(value: str) -> int | None:
        digits = re.sub(r"[^0-9]", "", value)
        return int(digits) if digits else None

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        plain = self._clean(text)
        schedule = re.search(
            r"Call schedule.*?from\s+(\d{1,2}/\d{1,2}/\d{4})\s+to\s+(\d{1,2}/\d{1,2}/\d{4})",
            plain,
            re.IGNORECASE,
        )
        budget = re.search(r"Call budget\s+amounts\s+to\s+EUR\s*([0-9.]+)", plain, re.IGNORECASE)
        title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        title = self._clean(title_match.group(1)) if title_match else "4th Call for Proposals"
        if not schedule:
            raise AdapterError("Interreg Italy–Croatia page has no call schedule")
        description_start = plain.find("The proposals submitted under this Call")
        description = plain[description_start:description_start + 1800] if description_start >= 0 else plain[:1800]
        return [SourceRecord(
            external_id="4th-call-for-proposals",
            title=title,
            official_url=self.page_url,
            funder="Interreg Italy–Croatia",
            programme="Interreg VI-A Italy–Croatia 2021-2027",
            opening_date=self._date(schedule.group(1)),
            deadline=self._date(schedule.group(2)),
            total_budget=self._money(budget.group(1)) if budget else None,
            description=description,
            source_status="UNKNOWN",
        )]


class _VenetoBandiRowsParser(HTMLParser):
    """Read the compact ``IN SCADENZA`` cards from the public homepage."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._row_depth: int | None = None
        self._row_text: list[str] | None = None
        self._row_href: str | None = None
        self._row_title = ""
        self._anchor_href: str | None = None
        self._anchor_text: list[str] | None = None
        self.rows: list[tuple[str, str, str]] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div":
            self._depth += 1
            if self._row_depth is None and "row-inScadenza" in self._classes(attrs):
                self._row_depth = self._depth
                self._row_text = []
                self._row_href = None
                self._row_title = ""
        if self._row_depth is not None and tag == "a" and self._anchor_href is None:
            self._anchor_href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._row_text is not None:
            self._row_text.append(data)
        if self._anchor_text is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            href = self._anchor_href.strip()
            title = re.sub(r"\s+", " ", "".join(self._anchor_text or [])).strip()
            if self._row_href is None and href:
                self._row_href = href
                self._row_title = title
            self._anchor_text = None
            self._anchor_href = None
            return
        if tag != "div":
            return
        if self._row_depth is not None and self._depth == self._row_depth:
            if self._row_href:
                self.rows.append((self._row_href, self._row_title, "".join(self._row_text or [])))
            self._row_depth = None
            self._row_text = None
            self._row_href = None
            self._row_title = ""
            self._anchor_href = None
            self._anchor_text = None
        self._depth -= 1


class VenetoBandiAdapter:
    """Public homepage adapter for the Regione del Veneto opportunity cards.

    The homepage intentionally exposes only the ten items in its ``IN
    SCADENZA`` block.  This first contract preserves that bounded, static
    listing; detail pages can be added once their pagination contract is
    separately verified.
    """

    source_id = "veneto-bandi"
    page_url = "https://bandi.regione.veneto.it/Public/"

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=5_000_000)) -> bytes:
        request = Request(self.page_url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError("unexpected content type from Regione Veneto bandi homepage")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from Regione Veneto bandi homepage", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for Regione Veneto bandi homepage: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("Regione Veneto bandi homepage exceeds download size limit")
        return payload

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    @staticmethod
    def _date(value: str) -> date | None:
        for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                continue
        return None

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
            # The portal declares UTF-8 but a few legacy title fragments still
            # arrive as Windows-1252 bytes.  Retry only when UTF-8 decoding
            # produced replacement characters so accents are not lost.
            if "\ufffd" in text:
                text = raw.decode("cp1252", errors="replace")
        else:
            text = raw
        parser = _VenetoBandiRowsParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, title, row_text) in enumerate(parser.rows, 1):
            match = re.search(r"\b([ABC])\s+(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)", self._clean(row_text))
            if not match or not title:
                continue
            official_url = urljoin(self.page_url, href)
            if not official_url.startswith("https://bandi.regione.veneto.it/"):
                continue
            external_match = re.search(r"idAtto=(\d+)", official_url, re.IGNORECASE)
            external_id = external_match.group(1) if external_match else f"homepage-row-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            category = {"A": "Avviso", "B": "Bando o finanziamento", "C": "Concorso"}[match.group(1)]
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder="Regione del Veneto",
                programme=f"Portale Bandi — {category}",
                deadline=self._date(match.group(2)),
                description=f"Voce estratta dalla sezione IN SCADENZA del portale regionale ({category}).",
                source_status="OPEN",
            ))
        return records


class _AnchorTextParser(HTMLParser):
    """Collect anchor href/text pairs without depending on a CSS framework."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._label: str | None = None
        self._text: list[str] | None = None
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._href is None:
            href = dict(attrs).get("href")
            if href:
                self._href = href
                attributes = dict(attrs)
                self._label = attributes.get("aria-label") or attributes.get("title")
                self._text = []

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        title = re.sub(r"\s+", " ", "".join(self._text or [])).strip()
        if self._label and (not title or title.lower() in {"scopri di più", "scopri tutto", "leggi", "leggi tutto"}):
            title = self._label
        title = re.sub(r"^(?:vai alla pagina|vai al dettaglio)\s+", "", title, flags=re.IGNORECASE)
        self.links.append((self._href, title))
        self._href = None
        self._label = None
        self._text = None


class _HtmlOpportunityListAdapter:
    """Small shared transport/parser shell for bounded official link lists."""

    source_id = ""
    page_url = ""
    source_label = "official HTML list"
    funder = ""
    programme = ""
    url_prefix = ""
    url_tokens: tuple[str, ...] = ()
    excluded_tokens: tuple[str, ...] = ()
    max_bytes = 8_000_000

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        request = Request(self.page_url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError(f"unexpected content type from {self.source_label}")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from {self.source_label}", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for {self.source_label}: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} exceeds download size limit")
        return payload

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    def _include_link(self, official_url: str, title: str) -> bool:
        parsed = urlsplit(official_url)
        if parsed.scheme != "https" or not parsed.netloc:
            return False
        if self.url_prefix and not parsed.path.lower().startswith(self.url_prefix.lower()):
            return False
        if self.url_prefix and parsed.path.rstrip("/").lower() == self.url_prefix.rstrip("/").lower():
            return False
        query_suffix = f"?{parsed.query.lower()}" if parsed.query else ""
        path_and_title = f"{parsed.path.lower()}{query_suffix} {title.lower()}"
        if self.url_tokens and not any(token.lower() in path_and_title for token in self.url_tokens):
            return False
        if any(token.lower() in path_and_title for token in self.excluded_tokens):
            return False
        return len(title) >= 8

    @staticmethod
    def _external_id(official_url: str, index: int) -> str:
        path = urlsplit(official_url).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1] if path else ""
        slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
        return slug or f"html-opportunity-{index}"

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                text = raw.decode("cp1252", errors="replace")
        else:
            text = raw
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(raw_title)
            official_url = urljoin(self.page_url, html.unescape(href))
            if not self._include_link(official_url, title):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                description=f"Link estratto dall'elenco ufficiale {self.source_label}.",
                source_status="UNKNOWN",
            ))
        return records


class DipartimentoFamigliaAdapter(_HtmlOpportunityListAdapter):
    source_id = "dipartimento-famiglia"
    page_url = "https://www.famiglia.governo.it/it/politiche-e-attivita/finanziamenti-avvisi-e-bandi/"
    source_label = "Dipartimento per le politiche della famiglia"
    funder = "Dipartimento per le politiche della famiglia"
    programme = "Politiche della famiglia"
    url_prefix = "/it/politiche-e-attivita/finanziamenti-avvisi-e-bandi/"
    url_tokens = ("/avvisi-e-bandi/", "/avviso-")
    excluded_tokens = ("archivio-bandi", "/faq", "/media/")

    def _include_link(self, official_url: str, title: str) -> bool:
        if urlsplit(official_url).path.rstrip("/").lower().endswith("/avvisi-e-bandi"):
            return False
        return super()._include_link(official_url, title)


class DipartimentoDisabilitaAdapter(_HtmlOpportunityListAdapter):
    source_id = "dipartimento-disabilita"
    page_url = "https://www.disabilita.governo.it/it/avvisi-e-bandi/"
    source_label = "Dipartimento per le politiche in favore delle persone con disabilità"
    funder = "Dipartimento per le politiche in favore delle persone con disabilità"
    programme = "Fondo unico per l'inclusione e politiche per la disabilità"
    url_prefix = "/it/avvisi-e-bandi/"
    excluded_tokens = ("?", "/media/")


class FondazioneCariparoAdapter(_HtmlOpportunityListAdapter):
    source_id = "fondazione-cariparo"
    page_url = "https://fondazionecariparo.it/bandi/"
    source_label = "Fondazione Cariparo"
    funder = "Fondazione Cariparo"
    programme = "Bandi Fondazione Cariparo"
    url_tokens = ("/2026/", "/2025/")
    excluded_tokens = ("/wp-", "/bandi/", "/iniziative/")


class FondazioneCariveronaAdapter(_HtmlOpportunityListAdapter):
    source_id = "fondazione-cariverona"
    page_url = "https://www.fondazionecariverona.org/bandi/"
    source_label = "Fondazione Cariverona"
    funder = "Fondazione Cariverona"
    programme = "Bandi Fondazione Cariverona"
    url_prefix = "/iniziative/"


class ConIBambiniAdapter(_HtmlOpportunityListAdapter):
    source_id = "con-i-bambini"
    page_url = "https://www.conibambini.org/bandi-e-iniziative/"
    source_label = "Con i Bambini"
    funder = "Con i Bambini"
    programme = "Bandi e iniziative per il contrasto della povertà educativa minorile"
    url_prefix = "/bandi-e-iniziative/"
    excluded_tokens = ("/categoria/", "/tag/", "#", "/wp-content/")

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                text = raw.decode("cp1252", errors="replace")
        else:
            text = raw
        match = re.search(r"var\s+bandi\s*=\s*(\{.*?\});", text, re.DOTALL)
        if not match:
            return super().parse(text)
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise AdapterError("Con i Bambini embedded bandi data is not valid JSON") from exc
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for section in payload.get("list_bandi", []):
            if not isinstance(section, dict):
                continue
            status_text = str(section.get("text") or "").lower()
            source_status = "OPEN" if "corso" in status_text else "CLOSED" if "scadut" in status_text else "UNKNOWN"
            for item in section.get("children", []):
                if not isinstance(item, dict):
                    continue
                title = self._clean(str(item.get("text") or ""))
                official_url = urljoin(self.page_url, str(item.get("id") or ""))
                if not title or not self._include_link(official_url, title):
                    continue
                external_id = self._external_id(official_url, len(records) + 1)
                if external_id in seen:
                    continue
                seen.add(external_id)
                records.append(SourceRecord(
                    external_id=external_id,
                    title=title,
                    official_url=official_url,
                    funder=self.funder,
                    programme=self.programme,
                    description=f"Voce dell'elenco ufficiale Con i Bambini ({section.get('text', '')}).",
                    source_status=source_status,
                ))
        return records


class FondoRepubblicaDigitaleAdapter(_HtmlOpportunityListAdapter):
    source_id = "fondo-repubblica-digitale"
    page_url = "https://www.fondorepubblicadigitale.it/pagina-bandi/"
    source_label = "Fondo per la Repubblica Digitale"
    funder = "Fondo per la Repubblica Digitale"
    programme = "Bandi Fondo per la Repubblica Digitale"
    url_prefix = "/bandi/"
    excluded_tokens = ("/pagina-bandi/", "/wp-content/")


class IncentiviGovAdapter:
    """Adapter for the official Incentivi.gov.it open-data Solr export.

    The portal exposes the same dataset used by its public open-data download
    through a read-only Solr endpoint.  The field aliases below intentionally
    mirror the portal's own export contract instead of scraping rendered HTML.
    """

    source_id = "incentivi-gov"
    page_url = "https://www.incentivi.gov.it/it/open-data"
    endpoint = "https://www.incentivi.gov.it/solr/coredrupal/select"
    portal_base_url = "https://www.incentivi.gov.it"
    default_rows = 8_000
    export_fields = (
        ("ID_Incentivo", "zs_nid"),
        ("Titolo", "zs_title"),
        ("Descrizione", "zs_body"),
        ("Obiettivo_Finalita", "zm_field_scopes_value"),
        ("Data_apertura", "zs_field_open_date"),
        ("Data_chiusura", "zs_field_close_date"),
        ("Note_di_apertura_chiusura", "zs_field_close_date_descriptor"),
        ("Dimensioni", "zm_field_dimensions_value"),
        ("Tipologia_Soggetto", "zm_field_subject_type_value"),
        ("Forma_agevolazione", "zm_field_support_form_value"),
        ("Costi_Ammessi", "zm_field_granted_costs_value"),
        ("Spesa_Ammessa_min", "zs_field_cost_min"),
        ("Spesa_Ammessa_max", "zs_field_cost_max"),
        ("Agevolazione_Concedibile_min", "zs_field_support_grant_type_min"),
        ("Agevolazione_Concedibile_max", "zs_field_support_grant_type_max"),
        ("Settore_Attivita", "zm_field_activity_sector_value"),
        ("Codici_ATECO", "zs_field_ateco"),
        ("Regioni", "zm_field_regions_value"),
        ("Comuni", "zs_field_comuni"),
        ("Ambito_territoriale", "zm_field_special_territory_value"),
        ("Soggetto_Concedente", "zs_field_subject_grant"),
        ("Base_normativa_primaria", "zs_field_primary_ruleset"),
        ("Base_normativa_secondaria", "zs_field_secondary_ruleset"),
        ("Provvedimento_attuativo", "zs_field_implementation_ruleset"),
        ("Gazzetta_ufficiale", "zs_field_official_references"),
        ("Stanziamento_incentivo", "zs_field_budget_allocation"),
        ("Link_istituzionale", "zs_field_link"),
        ("Altre_caratteristiche", "zs_field_other_characteristic"),
        ("Data_ultimo_aggiornamento", "ds_last_update"),
        ("URL", "zs_url"),
    )

    def build_query(self, rows: int | None = None) -> dict[str, str]:
        limit = rows or self.default_rows
        fields = ",".join(f"{alias}:{field}" for alias, field in self.export_fields) + ",score"
        return {
            "q.op": "OR",
            "wt": "json",
            "rows": str(limit),
            "fl": fields,
            "q": "index_id:incentivi ",
        }

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=30_000_000)) -> bytes:
        from urllib.parse import urlencode

        query = urlencode(self.build_query())
        request = Request(
            f"{self.endpoint}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": policy.user_agent,
            },
        )
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() != "application/json":
                        raise AdapterError("unexpected content type from Incentivi.gov.it Solr export")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                hint = "retry later" if exc.code in {429, 500, 502, 503, 504} else "check source contract"
                raise AdapterError(f"HTTP {exc.code} from Incentivi.gov.it Solr export ({hint})", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for Incentivi.gov.it Solr export: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError("Incentivi.gov.it response exceeds download size limit")
        return payload

    @staticmethod
    def _values(document: dict, *keys: str) -> list[str]:
        for key in keys:
            value = document.get(key)
            if isinstance(value, list):
                values = [str(item).strip() for item in value if str(item).strip()]
                if values:
                    return values
            elif value is not None and str(value).strip():
                return [str(value).strip()]
        return []

    @staticmethod
    def _date(value: str | None) -> date | None:
        if not value:
            return None
        candidate = value.strip().replace("Z", "+00:00")
        for parser in (
            lambda item: datetime.fromisoformat(item).date(),
            lambda item: datetime.strptime(item, "%d/%m/%Y").date(),
            lambda item: datetime.strptime(item, "%Y-%m-%d").date(),
        ):
            try:
                return parser(candidate)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _clean(value: str) -> str:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _money(values: list[str]) -> int | None:
        for value in values:
            digits = re.sub(r"[^0-9]", "", value)
            if digits:
                return int(digits)
        return None

    def _official_url(self, document: dict) -> str:
        candidate = (self._values(document, "URL", "url") or [""])[0]
        if candidate.startswith("/"):
            candidate = self.portal_base_url + candidate
        if candidate.startswith("https://"):
            return candidate
        return self.page_url

    def parse(self, raw: bytes | str | dict) -> list[SourceRecord]:
        try:
            payload = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AdapterError("Incentivi.gov.it response is not valid JSON") from exc
        response = payload.get("response") if isinstance(payload, dict) else None
        documents = response.get("docs") if isinstance(response, dict) else None
        if not isinstance(documents, list):
            raise AdapterError("Incentivi.gov.it response has no response.docs list")

        records: list[SourceRecord] = []
        for index, document in enumerate(documents, 1):
            if not isinstance(document, dict):
                continue
            identifier_values = self._values(document, "ID_Incentivo", "nid")
            external_id = identifier_values[0] if identifier_values else f"incentivi-result-{index}"
            title_values = self._values(document, "Titolo", "title")
            if not title_values:
                continue
            objectives = self._values(document, "Obiettivo_Finalita")
            description_values = self._values(document, "Descrizione", "body")
            description = self._clean(description_values[0]) if description_values else ""
            if objectives:
                objective_text = "; ".join(self._clean(value) for value in objectives)
                description = f"Obiettivo: {objective_text}. {description}".strip()
            entities = self._values(document, "Tipologia_Soggetto", "Dimensioni")
            records.append(SourceRecord(
                external_id=external_id,
                title=self._clean(title_values[0]),
                official_url=self._official_url(document),
                funder=self._clean((self._values(document, "Soggetto_Concedente") or ["Incentivi.gov.it"])[0]),
                programme="Incentivi.gov.it",
                opening_date=self._date((self._values(document, "Data_apertura") or [None])[0]),
                deadline=self._date((self._values(document, "Data_chiusura") or [None])[0]),
                total_budget=self._money(self._values(document, "Stanziamento_incentivo")),
                eligible_entities=tuple(self._clean(value) for value in entities),
                description=description,
                source_status="UNKNOWN",
            ))
        return records


def _money(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None
