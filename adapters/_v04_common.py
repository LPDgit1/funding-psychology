from __future__ import annotations

import html
import re
from datetime import date
from html.parser import HTMLParser
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy
from funding_core.dates import parse_date


class _PageTextParser(HTMLParser):
    """Small text extractor for source-local structured pages.

    It deliberately does not infer opportunities.  Each v0.4 adapter still
    owns its source-specific row/card contract; this helper only removes
    executable/page-chrome text before field extraction.
    """

    _excluded = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._excluded:
            self._skip += 1
        elif not self._skip and tag in {"p", "li", "br", "div", "tr", "section", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._excluded and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", html.unescape("".join(self._parts))).strip()


def page_text(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
        if "\ufffd" in text:
            text = raw.decode("cp1252", errors="replace")
    else:
        text = raw
    parser = _PageTextParser()
    parser.feed(text)
    return parser.text


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def parse_day_date(value: str | None, *, default_year: int | None = None) -> date | None:
    """Parse source labels such as ``16-11-2026`` and ``1° ottobre``."""

    if not value:
        return None
    candidate = clean(value).replace("°", "").replace("º", "")
    parsed = parse_date(candidate, default_year=default_year)
    if parsed:
        return parsed
    # The shared parser intentionally accepts only unambiguous formats.  This
    # bounded fallback covers an Italian date with a missing year in a source
    # calendar whose page heading supplies the year.
    match = re.search(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\b", candidate, re.IGNORECASE)
    if match and default_year:
        return parse_date(f"{match.group(1)} {match.group(2)} {default_year}")
    return None


_DATE_TOKEN = re.compile(
    r"\b\d{1,2}\s*[°º]?\s+[A-Za-zÀ-ÿ]+(?:\s+\d{4})?\b|"
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b[A-Za-zÀ-ÿ]+\s+\d{1,2},\s*\d{4}\b",
    re.IGNORECASE,
)


def dates_in(value: str, *, default_year: int | None = None) -> list[date]:
    found: list[date] = []
    for match in _DATE_TOKEN.finditer(value):
        parsed = parse_day_date(match.group(0), default_year=default_year)
        if parsed and parsed not in found:
            found.append(parsed)
    return found


def amount(value: str) -> int | None:
    # Supports both Italian grouping (1.250.000) and an explicit euro symbol.
    for match in re.finditer(r"(?:€|EUR|euro|stanziamento|dotazione|budget|importo|risorse)[^€$0-9]{0,40}(?:€|EUR|euro)?\s*([0-9][0-9. ,]{2,})", value, re.IGNORECASE):
        token = match.group(1).strip()
        # Italian amounts often carry decimal cents (``300.000,00``).
        token = re.sub(r",\s*\d{2}\b", "", token)
        digits = re.sub(r"[^0-9]", "", token)
        if digits:
            return int(digits)
    return None


def fetch_bytes(url: str, policy: FetchPolicy, *, label: str, accept: str = "text/html,application/xhtml+xml", content_types: set[str] | None = None) -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": policy.user_agent})
    accepted = content_types or {"text/html", "application/xhtml+xml"}
    for attempt in range(policy.retries + 1):
        try:
            with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
                if response.headers.get_content_type() not in accepted:
                    raise AdapterError(f"unexpected content type from {label}")
                payload = response.read(policy.max_bytes + 1)
            if len(payload) > policy.max_bytes:
                raise AdapterError(f"{label} exceeds download size limit")
            return payload
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                sleep(0.2 * (attempt + 1))
                continue
            raise AdapterError(f"HTTP {exc.code} from {label}", status_code=exc.code) from exc
        except URLError as exc:
            if attempt < policy.retries:
                sleep(0.2 * (attempt + 1))
                continue
            raise AdapterError(f"connection failed for {label}: {exc.reason}") from exc
    raise AdapterError(f"request exhausted retries for {label}")
