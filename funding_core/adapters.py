from __future__ import annotations

import csv
import html
import io
import json
import re
import time
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .models import SourceRecord
from .dates import parse_date
from .territories import normalize_territory, split_regions


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


# These are deliberately narrow patterns.  A generic word such as
# ``decreto`` or ``accordo`` is not enough to reject a record: an official
# act can also approve a real call.  The helper is used only by the bounded
# HTML/AIG adapters where these editorial follow-ups were observed.
_FUNDING_TITLE_SIGNAL = re.compile(
    r"\b(?:bando|avviso\s+(?:pubblic\w*|per)|call\s+for\s+(?:proposal|project)|"
    r"finanziament\w*|grant|contribut\w*|presentazion\w*\s+(?:delle\s+)?(?:domande|candidatur\w*|progett\w*)|"
    r"candidatur\w*\s+aperte|progett\w*\s+finanziabil\w*)\b",
    re.IGNORECASE,
)
_NON_OPPORTUNITY_STRONG = re.compile(
    r"(?:\bdecreto\s+(?:di\s+)?nomina(?:zione)?\s+(?:della\s+)?commissione\b|"
    r"\bdecreto\s+commissione\s+valutazione\b|"
    r"\bdecreto\s+(?:di\s+)?(?:riconoscimento|approvazione|conferma)\b|"
    r"\bcommissione\s+(?:di\s+)?valutazione\b|"
    r"\b(?:graduatori\w*|esiti(?:\s+finali)?|approvazione\s+(?:della\s+)?graduatori\w*)\b|"
    r"\bdecreto[^.;]{0,80}\briparto\b|"
    r"\b(?:pubblicat\w*\s+)?accordo\s+di\s+collaborazione\b|"
    r"^\s*informativa\b)",
    re.IGNORECASE,
)
_NON_OPPORTUNITY_EDITORIAL = re.compile(
    r"\b(?:comunicat\w*|seminari\w*|webinar\w*|convegn\w*|focus\s+group|consultazion\w*)\b",
    re.IGNORECASE,
)


def is_funding_opportunity(title: str, content: str = "") -> bool:
    """Keep candidate calls and reject clearly non-candidable follow-ups."""
    title_text = re.sub(r"\s+", " ", html.unescape(str(title or ""))).strip()
    content_text = re.sub(r"\s+", " ", html.unescape(str(content or ""))).strip()
    if _NON_OPPORTUNITY_STRONG.search(title_text):
        return False
    # A real call remains valid even when its detail page mentions a
    # commission, an agreement, or a later administrative step.
    if not _FUNDING_TITLE_SIGNAL.search(title_text) and (
        _NON_OPPORTUNITY_STRONG.search(content_text) or _NON_OPPORTUNITY_EDITORIAL.search(content_text)
    ):
        return False
    return True


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

    # SEDIA status codes: 31094501 upcoming, 31094502 open, 31094503 closed.
    # Closed calls belong in the archive, never in the operational EU feed.
    open_statuses = {"31094502", "31094501"}
    page_size = 100
    max_pages = 50
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
                ],
            },
        }

    @staticmethod
    def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
        # The portal creates a fresh multipart boundary for each request.  A
        # fixed boundary can be cached as an invalid/replayed request by the
        # gateway and intermittently return HTTP 404 on subsequent pages.
        boundary = f"----FundingIntelligenceBoundary{uuid.uuid4().hex}"
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

    def _request_page(
        self,
        body: bytes,
        content_type: str,
        page_number: int,
        policy: FetchPolicy,
    ) -> dict:
        url = (
            # The current portal uses *** as its all-records sentinel; a
            # single * now returns HTTP 404 from the same public endpoint.
            f"{self.endpoint}?apiKey=SEDIA&text=***&pageSize={self.page_size}"
            f"&pageNumber={page_number}"
        )
        request = Request(url, data=body, method="POST", headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": policy.user_agent,
            "Referer": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
            "Origin": "https://ec.europa.eu",
        })
        for attempt in range(policy.retries + 1):
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() != "application/json":
                        raise AdapterError("unexpected content type from EU Funding & Tenders API")
                    payload = response.read(policy.max_bytes + 1)
                if len(payload) > policy.max_bytes:
                    raise AdapterError("EU Funding & Tenders page exceeds download size limit")
                parsed = json.loads(payload)
                if not isinstance(parsed, dict):
                    raise AdapterError("EU Funding & Tenders page is not a JSON object")
                return parsed
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
            except json.JSONDecodeError as exc:
                raise AdapterError("EU Funding & Tenders page is not valid JSON") from exc
        raise AdapterError("EU Funding & Tenders request exhausted retries")

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=25_000_000)) -> bytes:
        query = json.dumps(self.build_query(), ensure_ascii=False, separators=(",", ":"))
        languages = json.dumps(["en"])
        display_fields = json.dumps(list(self.display_fields))
        multipart_fields = {
            "sort": json.dumps({"order": "DESC", "field": "relevance"}),
            "query": query,
            "languages": languages,
            "displayFields": display_fields,
        }
        results: list[dict] = []
        total_results: int | None = None
        for page_number in range(1, self.max_pages + 1):
            # Use a fresh boundary on every paginated request, as the portal
            # does with FormData.
            body, content_type = self._multipart(multipart_fields)
            page = self._request_page(body, content_type, page_number, policy)
            page_results = page.get("results")
            if not isinstance(page_results, list):
                raise AdapterError("EU Funding & Tenders response has no results list")
            results.extend(item for item in page_results if isinstance(item, dict))
            raw_total = page.get("totalResults") or page.get("total")
            if isinstance(raw_total, int):
                total_results = raw_total
            if not page_results or len(page_results) < self.page_size:
                break
            if total_results is not None and len(results) >= total_results:
                break
        else:
            raise AdapterError(f"EU Funding & Tenders pagination exceeded {self.max_pages} pages")
        combined = json.dumps({
            "results": results,
            "totalResults": total_results if total_results is not None else len(results),
            "pagesFetched": min(self.max_pages, (len(results) + self.page_size - 1) // self.page_size),
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(combined) > policy.max_bytes:
            raise AdapterError("EU Funding & Tenders response exceeds download size limit")
        return combined

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
        return parse_date(value)

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

    @classmethod
    def _deadline(cls, values: list[str], *, source_status: str, today: date | None = None) -> date | None:
        """Select the meaningful cut-off from all values returned by SEDIA.

        A call can expose historical and future cut-offs together.  For an
        authoritative OPEN/UPCOMING status the first cut-off that is still
        usable is the only safe value to publish.  If an authoritative call
        has no future cut-off we leave the date empty rather than archiving it
        from a stale historical date; UNKNOWN records retain their latest
        parsed date so the normal local CLOSED inference remains available.
        """
        parsed = sorted({parsed for value in values if (parsed := cls._date(value))})
        if not parsed:
            return None
        reference = today or date.today()
        future = [value for value in parsed if value >= reference]
        if source_status in {"OPEN", "UPCOMING"}:
            return future[0] if future else None
        return parsed[-1]

    def parse(self, raw: bytes | str | dict, *, today: date | None = None) -> list[SourceRecord]:
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
            source_status = self._status(self._values(metadata, "status"))
            # The server-side query is current-only, but retain this guard for
            # cached/manual payloads that may contain a stale closed result.
            if source_status == "CLOSED":
                continue
            records.append(SourceRecord(
                external_id=identifier[0] if identifier else f"eu-result-{index}",
                title=title,
                official_url=official_url,
                funder="Unione Europea",
                programme=(self._values(metadata, "frameworkProgramme") or ["Funding & Tenders Portal"])[0],
                opening_date=self._date((self._values(metadata, "startDate") or [None])[0]),
                deadline=self._deadline(self._values(metadata, "deadlineDate"), source_status=source_status, today=today),
                total_budget=self._money(self._values(metadata, "budget", "grantAmount")),
                eligible_entities=tuple(self._values(metadata, "participantTypes")),
                description=description[0] if description else "",
                source_status=source_status,
                status_authoritative=True,
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
        return parse_date(value, default_year=2026)

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
        return parse_date(value, default_year=2026)

    @staticmethod
    def _is_fundable(title: str, content: str) -> bool:
        if not is_funding_opportunity(title, content):
            return False
        title_text = title.lower()
        text = f"{title} {content}".lower()
        # A generic mention of the EU budget or of funding policy is not a
        # funding opportunity.  Require a local project/grant context instead
        # of accepting every occurrence of ``finanziamento`` in the article.
        funding_signal = re.search(
            r"\b(?:grant(?:\s+opportunit\w*)?|funding\s+(?:application|opportunit\w*|call)|"
            r"bando|avviso\s+pubblic\w*|finanziament\w*\s+(?:di|per|a(?:\s+favore)?|destinat)|"
            r"contribut\w*\s+(?:per|a(?:\s+favore)?|destinat)|sovvenzion\w*|"
            r"opportunit\w*\s+di\s+finanziament\w*|sostegno\s+(?:a|per)\s+(?:progett|spaz|iniziativ))\b",
            text,
        ) is not None
        programme_signal = re.search(
            r"\b(?:erasmus\+?|european solidarity corps|esc|ka\s*1|ka\s*2|ka210|ka220)\b",
            text,
        ) is not None
        action_code = re.search(r"\bka\s*(?:1|2|210|220)\b|\b(?:ka210|ka220)\b", text) is not None
        deadline_signal = re.search(r"\b(?:scadenza|deadline|termine|entro il|entro)\b", text) is not None
        proposal_signal = re.search(
            r"(?:call\s+for\s+(?:proposal|project|projects)|project\s+call|candidatur\w*\s+(?:per|di)\s+(?:progett|grant|finanziament)|progett\w*\s+(?:finanziat|funding|grant))",
            text,
        ) is not None
        application_signal = re.search(r"\b(?:candidatur\w*|application\w*)\b", text) is not None
        event_only = re.search(
            r"\b(?:seminari\w*|webinar\w*|event\w*|festival\w*|consultazion\w*|focus\s+group|"
            r"training\s+course|cors\w*|conferenz\w*|presentazion\w*|contest\w*|"
            r"round\s+table|tavola\s+rotonda|iniziativ\w*|percorso\w*|viaggio\s+del\s+ricordo)\b",
            text,
        ) is not None
        participants_only = re.search(r"call\s+for\s+participants?|chiamata\s+per\s+partecipanti", text) is not None
        title_funding = re.search(
            r"\b(?:bando|avviso\s+pubblic\w*|grant|funding|finanziament\w*|contribut\w*|"
            r"sovvenzion\w*|ka\s*(?:1|2|210|220)|ka210|ka220|project\s+call|call\s+for\s+proposals?)\b",
            title_text,
        ) is not None
        activity_marker = re.search(
            r"\b(?:corso|seminari\w*|webinar\w*|event\w*|festival\w*|consultazion\w*|focus\s+group|"
            r"round\s+table|tavola\s+rotonda|workshop|contest\w*|concorso\w*|percorso\w*|"
            r"iniziativ\w*|call\s+for\s+participants?|tavola|appuntament\w*|storie)\b",
            text,
        ) is not None

        # Programme/action codes are meaningful only when they identify a
        # project opportunity; a bare mention in an event announcement is not
        # enough.  In all other cases require a funding word or a proposal /
        # application pattern with an explicit deadline or project signal.
        clear_funding = funding_signal or (programme_signal and (action_code or deadline_signal))
        clear_project_call = proposal_signal or (application_signal and deadline_signal and re.search(r"\bprogett\w*\b", text) is not None)
        project_funding = clear_funding or clear_project_call
        # AIG publishes many informational/editorial posts.  If the title or
        # body clearly describes an event/course/contest, a generic mention of
        # a programme or budget is not enough: retain it only with an explicit
        # funding title or project-call signal.
        if activity_marker and not title_funding:
            return False
        if participants_only and not project_funding:
            return False
        if event_only and not project_funding:
            return False
        return bool(project_funding)

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
            if not self._is_fundable(title, content):
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
        return parse_date(value)

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


class _VenetoBandiListParser(HTMLParser):
    """Extract detail links and their server-rendered result-row context."""

    _row_marker = re.compile(r"(?:^|[-_ ])(?:row|item|atto|risultat|scheda|elenco)(?:$|[-_ ])", re.IGNORECASE)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._row_depth: int | None = None
        self._row_text: list[str] | None = None
        self._row_href: str | None = None
        self._anchor_href: str | None = None
        self._anchor_text: list[str] | None = None
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        attributes = dict(attrs)
        identity = " ".join(filter(None, (attributes.get("id"), attributes.get("class"))))
        if self._row_depth is None and (tag in {"tr", "li"} or self._row_marker.search(identity or "")):
            self._row_depth = self._depth
            self._row_text = []
            self._row_href = None
        if self._row_depth is not None and tag == "a" and self._anchor_href is None:
            href = attributes.get("href") or ""
            if "dettaglio" in href.lower() and "idatto=" in href.lower():
                self._anchor_href = href
                self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._row_text is not None:
            self._row_text.append(data)
        if self._anchor_text is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            if self._row_href is None:
                self._row_href = self._anchor_href
            self._anchor_href = None
            self._anchor_text = None
            self._depth = max(0, self._depth - 1)
            return
        if self._row_depth is not None and self._depth == self._row_depth:
            if self._row_href:
                self.rows.append((self._row_href, "".join(self._row_text or [])))
            self._row_depth = None
            self._row_text = None
            self._row_href = None
        self._depth = max(0, self._depth - 1)


class VenetoBandiAdapter:
    """Server-rendered official Veneto Bandi list adapter.

    The home page only shows the ten ``IN SCADENZA`` cards.  The stable
    ``Public/Elenco?Tipo=1`` list is used instead; the parser accepts every
    detail row returned by that endpoint and does not impose a ten-item cap.
    """

    source_id = "veneto-bandi"
    page_url = "https://bandi.regione.veneto.it/Public/Elenco?Tipo=1"
    endpoint = "https://bandi.regione.veneto.it/Public/GetListaAttiJson"
    source_label = "Regione Veneto — Bandi, Avvisi e Concorsi"
    page_size = 100
    max_pages = 50

    def fetch(self, policy: FetchPolicy = FetchPolicy(max_bytes=30_000_000)) -> bytes:
        from urllib.parse import urlencode

        rows: list[object] = []
        total: int | None = None
        for page in range(self.max_pages):
            params = {
                "cig": "",
                "parolaChiave": "",
                "tipoAttoTmp": "1",
                # The portal's Select2 controls send these sentinel values
                # when no filter is selected (empty strings return zero rows).
                "destinatariTmp": "null",
                "struttureTmp": "0",
                "categorieTmp": "null",
                "statoTmp": "null",
                "materieTmp": "null",
                "paginaIniziale": "Elenco",
                "sEcho": str(page + 1),
                "iDisplayStart": str(page * self.page_size),
                "iDisplayLength": str(self.page_size),
                "iSortingCols": "0",
            }
            url = f"{self.endpoint}?{urlencode(params)}"
            request = Request(url, headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.page_url,
                "User-Agent": policy.user_agent,
            })
            for attempt in range(policy.retries + 1):
                try:
                    with urlopen(request, timeout=policy.timeout_seconds) as response:
                        if response.headers.get_content_type() != "application/json":
                            raise AdapterError("unexpected content type from Regione Veneto bandi JSON endpoint")
                        payload = response.read(policy.max_bytes + 1)
                    break
                except HTTPError as exc:
                    if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                        time.sleep(0.2 * (attempt + 1))
                        continue
                    raise AdapterError(f"HTTP {exc.code} from Regione Veneto bandi JSON endpoint", status_code=exc.code) from exc
                except URLError as exc:
                    if attempt < policy.retries:
                        time.sleep(0.2 * (attempt + 1))
                        continue
                    raise AdapterError(f"connection failed for Regione Veneto bandi JSON endpoint: {exc.reason}") from exc
            if len(payload) > policy.max_bytes:
                raise AdapterError("Regione Veneto bandi JSON page exceeds download size limit")
            try:
                page_payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise AdapterError("Regione Veneto bandi endpoint returned invalid JSON") from exc
            page_rows = page_payload.get("aaData") if isinstance(page_payload, dict) else None
            if not isinstance(page_rows, list):
                raise AdapterError("Regione Veneto bandi endpoint has no aaData list")
            rows.extend(page_rows)
            raw_total = page_payload.get("recordsTotal") if isinstance(page_payload, dict) else None
            if isinstance(raw_total, int):
                total = raw_total
            if not page_rows or len(page_rows) < self.page_size or (total is not None and len(rows) >= total):
                break
        else:
            raise AdapterError(f"Regione Veneto bandi pagination exceeded {self.max_pages} pages")
        combined = json.dumps({"recordsTotal": total if total is not None else len(rows), "aaData": rows}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(combined) > policy.max_bytes:
            raise AdapterError("Regione Veneto bandi response exceeds download size limit")
        return combined

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    @staticmethod
    def _date(value: str) -> date | None:
        return parse_date(value)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        if isinstance(raw, bytes):
            json_text = raw.decode("utf-8", errors="replace")
        else:
            json_text = raw
        try:
            payload = json.loads(json_text)
        except (TypeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("aaData"), list):
            fragments: list[str] = []
            for row in payload["aaData"]:
                if isinstance(row, list) and row and isinstance(row[0], str):
                    fragments.append(f'<div class="row-atto">{row[0]}</div>')
                elif isinstance(row, str):
                    fragments.append(f'<div class="row-atto">{row}</div>')
            text = "\n".join(fragments)
        elif isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                text = raw.decode("cp1252", errors="replace")
        else:
            text = raw
        parser = _VenetoBandiListParser()
        parser.feed(text)
        rows = parser.rows
        if not rows:
            # Keep the original homepage fixture contract as a regression
            # fallback; live collection itself uses the complete list URL.
            homepage_parser = _VenetoBandiRowsParser()
            homepage_parser.feed(text)
            rows = [(href, row_text) for href, _title, row_text in homepage_parser.rows]
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, row_text) in enumerate(rows, 1):
            cleaned_row = self._clean(row_text)
            # A detail link is the reliable title source.  The list parser
            # includes its anchor text in the row context, so remove common
            # labels and use the first meaningful sentence as a fallback.
            anchor_title = ""
            anchor_match = re.search(r"(?:Bando|Avviso|Concorso|Manifestazione|Contributi|Rilevazione)[^|]{8,240}", cleaned_row, re.IGNORECASE)
            if anchor_match:
                anchor_title = self._clean(anchor_match.group(0))
            title = anchor_title or cleaned_row[:240]
            if not title:
                continue
            official_url = urljoin("https://bandi.regione.veneto.it/Public/", href)
            if not official_url.startswith("https://bandi.regione.veneto.it/"):
                continue
            external_match = re.search(r"idAtto=(\d+)", official_url, re.IGNORECASE)
            external_id = external_match.group(1) if external_match else f"homepage-row-{index}"
            if external_id in seen:
                continue
            seen.add(external_id)
            category_match = re.search(r"\b([ABC])\b", cleaned_row)
            category_code = category_match.group(1) if category_match else ("B" if re.search(r"\bbando\b|\bcontribut", title, re.IGNORECASE) else "A" if re.search(r"\bavviso\b", title, re.IGNORECASE) else "C" if re.search(r"\bconcorso\b", title, re.IGNORECASE) else "B")
            category = {"A": "Avviso", "B": "Bando o finanziamento", "C": "Concorso"}[category_code]
            deadline_match = re.search(r"(?:scadenza|termine|entro|chiusura)[^.;]{0,80}(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)", cleaned_row, re.IGNORECASE)
            if not deadline_match:
                deadline_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?\b", cleaned_row)
            status = "CLOSED" if re.search(r"\b(?:scadut[oa]|chius[oa]|expired)\b", cleaned_row, re.IGNORECASE) else "OPEN" if re.search(r"\b(?:apert[oa]|in corso|attiv[oa])\b", cleaned_row, re.IGNORECASE) else "UNKNOWN"
            entities = re.search(r"(?:destinatari|beneficiari|soggetti ammissibili)\s*[:\-]?\s*([^.;]{1,220})", cleaned_row, re.IGNORECASE)
            records.append(SourceRecord(
                external_id=external_id,
                title=title,
                official_url=official_url,
                funder="Regione del Veneto",
                programme=f"Portale Bandi — {category}",
                deadline=self._date(deadline_match.group(1) if deadline_match and deadline_match.lastindex else deadline_match.group(0) if deadline_match else None),
                eligible_entities=(self._clean(entities.group(1)),) if entities else (),
                description=f"Voce estratta dall'elenco ufficiale del portale regionale ({category}). {cleaned_row[:900]}".strip(),
                source_status=status,
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


class _DetailTextParser(HTMLParser):
    """Extract the real detail content, excluding site chrome.

    The parser deliberately stays structural rather than trying to understand
    arbitrary page semantics: main > article > known content container > body.
    This is enough to prevent navigation/footer/cookie text from influencing
    classification while preserving a conservative body fallback.
    """

    _excluded_tags = {"header", "nav", "footer", "aside", "script", "style", "noscript", "template", "form"}
    _excluded_markers = re.compile(
        r"(?:cookie|consent|breadcrumb|bread-crumb|(?:^|[-_ ])menu(?:$|[-_ ])|navbar|navigation|(?:^|[-_ ])nav(?:$|[-_ ])|search|sidebar|footer|header|social|share|privacy|banner|modal|popup)",
        re.IGNORECASE,
    )
    _known_container = re.compile(
        r"(?:content|entry-content|page-content|post-content|detail|bando|avviso|opportunit|call-content|main-content)",
        re.IGNORECASE,
    )
    _noise_text = re.compile(
        r"\b(?:vai\s+al\s+contenuto(?:\s+principale)?|vai\s+alla\s+navigazione(?:\s+del\s+sito)?|menu\s+accessibilit[aà])\b",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool, int]] = []
        self._buffers: dict[int, list[str]] = {0: []}
        self._title_stack_depth: int | None = None
        self._title: list[str] = []

    @classmethod
    def _rank(cls, tag: str, attrs: list[tuple[str, str | None]]) -> int:
        if tag == "main":
            return 3
        if tag == "article":
            return 2
        attributes = dict(attrs)
        identity = " ".join(filter(None, (attributes.get("id"), attributes.get("class"))))
        return 1 if identity and cls._known_container.search(identity) else 0

    @classmethod
    def _excluded(cls, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in cls._excluded_tags:
            return True
        attributes = dict(attrs)
        identity = " ".join(filter(None, (attributes.get("id"), attributes.get("class"))))
        return bool(identity and cls._excluded_markers.search(identity))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent_excluded = self._stack[-1][1] if self._stack else False
        excluded = parent_excluded or self._excluded(tag, attrs)
        rank = max((entry[2] for entry in self._stack if not entry[1]), default=0)
        if not excluded:
            rank = max(rank, self._rank(tag, attrs))
            self._buffers.setdefault(rank, [])
            if tag in {"br", "p", "li", "div", "tr", "h1", "h2", "h3", "section"}:
                self._buffers[rank].append(" ")
            if self._title_stack_depth is None and tag in {"title", "h1"}:
                self._title_stack_depth = len(self._stack) + 1
        self._stack.append((tag, excluded, rank))

    def handle_data(self, data: str) -> None:
        if not self._stack or self._stack[-1][1]:
            return
        rank = max((entry[2] for entry in self._stack if not entry[1]), default=0)
        self._buffers.setdefault(rank, []).append(data)
        if self._title_stack_depth is not None:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        # HTML from public portals is occasionally imperfect.  Pop through a
        # matching tag without allowing a malformed footer/nav to leak into
        # later content.
        index = next((index for index in range(len(self._stack) - 1, -1, -1) if self._stack[index][0] == tag), None)
        if index is None:
            return
        popped = self._stack[index:]
        del self._stack[index:]
        if self._title_stack_depth is not None and index < self._title_stack_depth:
            self._title_stack_depth = None

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._title)).strip()

    @property
    def text(self) -> str:
        for rank in (3, 2, 1, 0):
            value = self._noise_text.sub(" ", "".join(self._buffers.get(rank, [])))
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                return value
        return ""


def _detail_fields(raw: bytes | str) -> dict[str, object]:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    if "\ufffd" in text and isinstance(raw, bytes):
        text = raw.decode("cp1252", errors="replace")
    parser = _DetailTextParser()
    parser.feed(text)
    plain = html.unescape(parser.text)
    lowered = plain.lower()

    def first_date(patterns: tuple[str, ...]) -> date | None:
        for pattern in patterns:
            match = re.search(pattern, plain, re.IGNORECASE)
            if match:
                window = match.group(1)
                for date_match in re.finditer(
                    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2}\s+[A-Za-zÀ-ÿ]+(?:\s+\d{4})?\b|\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b",
                    window,
                ):
                    parsed = parse_date(date_match.group(0))
                    if parsed:
                        return parsed
        return None

    deadline = first_date((
        r"(?:scadenza|scade|termine|chiusura|deadline|entro il)\s*[:\-]?\s*([^.;]{1,80})",
        r"(?:presentare[^.;]{0,35}|domande[^.;]{0,35})\s+entro\s+([^.;]{1,80})",
    ))
    opening = first_date((
        r"(?:apertura|apre|opening|dal)\s*[:\-]?\s*([^.;]{1,80})",
    ))
    amount: int | None = None
    amount_match = re.search(
        r"(?:budget|dotazione|stanziamento|finanziamento|importo)[^€$0-9]{0,40}(?:€|eur)?\s*([0-9][0-9. ,]{2,})",
        plain,
        re.IGNORECASE,
    )
    if amount_match:
        digits = re.sub(r"[^0-9]", "", amount_match.group(1))
        if digits:
            amount = int(digits)
    if amount is None:
        bare_amount = re.search(r"(?:€|eur)\s*([0-9][0-9. ,]{2,})", plain, re.IGNORECASE)
        if bare_amount:
            digits = re.sub(r"[^0-9]", "", bare_amount.group(1))
            if digits:
                amount = int(digits)
    eligible = ""
    eligible_match = re.search(
        r"(?:destinatari|beneficiari|soggetti ammissibili|chi può partecipare|a chi è rivolto)[^:]{0,20}:?\s*([^.;]{1,220})",
        plain,
        re.IGNORECASE,
    )
    if eligible_match:
        eligible = re.sub(r"\s+", " ", eligible_match.group(1)).strip(" -")
    status = "UNKNOWN"
    if re.search(r"\b(?:scadut[oa]|chius[oa]|closed|expired)\b", lowered):
        status = "CLOSED"
    elif re.search(r"\b(?:apert[oa]|in corso|open|active)\b", lowered):
        status = "OPEN"
    return {
        "title": parser.title,
        "description": plain[:1600],
        "deadline": deadline,
        "opening_date": opening,
        "total_budget": amount,
        "eligible_entities": (eligible,) if eligible else (),
        "source_status": status,
    }


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
            if not is_funding_opportunity(title):
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

    def enrich(
        self,
        records: list[SourceRecord],
        policy: FetchPolicy | None = None,
        *,
        max_details: int = 40,
    ) -> list[SourceRecord]:
        """Best-effort detail enrichment; listing records survive every error."""
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        enriched: list[SourceRecord] = []
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            request = Request(record.official_url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
            try:
                with urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError(f"unexpected detail content type from {self.source_label}")
                    payload = response.read(policy.max_bytes + 1)
                if len(payload) > policy.max_bytes:
                    raise AdapterError(f"detail page exceeds size limit for {self.source_label}")
                fields = _detail_fields(payload)
                description = str(fields["description"] or record.description)
                if not is_funding_opportunity(record.title, description):
                    continue
                if len(description) < 40:
                    description = record.description
                entities = tuple(fields["eligible_entities"] or record.eligible_entities)
                status = str(fields["source_status"])
                if status == "UNKNOWN":
                    status = record.source_status
                enriched.append(replace(
                    record,
                    opening_date=fields["opening_date"] or record.opening_date,
                    deadline=fields["deadline"] or record.deadline,
                    total_budget=fields["total_budget"] or record.total_budget,
                    eligible_entities=entities,
                    description=description,
                    source_status=status,
                ))
            except (AdapterError, OSError, ValueError):
                enriched.append(record)
        return enriched


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
                if not is_funding_opportunity(title):
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
        return parse_date(value)

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

    def _catalog_url(self, document: dict) -> str:
        candidate = (self._values(document, "URL", "url") or [""])[0]
        if candidate.startswith("/"):
            candidate = self.portal_base_url + candidate
        if candidate.startswith("https://"):
            return candidate
        return self.page_url

    def _official_url(self, document: dict) -> str:
        candidate = (self._values(document, "Link_istituzionale", "institutional_url") or [""])[0]
        if candidate.startswith("/"):
            candidate = self.portal_base_url + candidate
        if candidate.startswith("https://"):
            return candidate
        return self._catalog_url(document)

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
            regions = split_regions(self._values(document, "Regioni"))
            scope_values = self._values(document, "Ambito_territoriale")
            scope = "; ".join(self._clean(value) for value in scope_values)
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
                regions=regions,
                territory=normalize_territory(regions, scope),
                aggregator_url=self._catalog_url(document),
            ))
        return records


def _money(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None
