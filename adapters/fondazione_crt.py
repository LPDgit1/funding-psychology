from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy, _AnchorTextParser, _DetailTextParser, _detail_fields
from funding_core.dates import parse_date
from funding_core.models import SourceRecord

from ._common import (
    DedicatedHtmlAdapter,
    _context,
    compact,
    decode_html,
    derive_title,
    extract_entities,
    extract_money,
    extract_regions,
    infer_status,
)


class _CrtDetailTextParser(HTMLParser):
    """Read the WordPress/Elementor post-content container used by CRT."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._skip = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        identity = " ".join(filter(None, (attributes.get("id"), attributes.get("class"))))
        if self._depth == 0 and re.search(r"elementor-widget-theme-post-content|entry-content|post-content", identity, re.IGNORECASE):
            self._depth = 1
            return
        if self._depth:
            self._depth += 1
            if tag in {"script", "style", "noscript", "template"}:
                self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth and not self._skip:
            self._buffer.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._buffer)).strip()


class FondazioneCrtAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_crt"
    # The public cards page is a partial “load more” view.  The archive is the
    # server-rendered, paginated contract used for complete candidate discovery.
    page_url = "https://www.fondazionecrt.it/cpt_bandi-progetti-archive/"
    source_label = "Fondazione CRT"
    funder = "Fondazione CRT"
    programme = "Progetti e bandi Fondazione CRT"
    url_tokens = ("bando", "progett", "disabilit", "welfare", "istruz", "ordinari", "richiest", "notesipari", "orizzonti")
    excluded_tokens = ("risultat", "news", "storie", "talent", "newsletter", "privacy", "cookie", "eventi")
    allow_status_context = True
    detail_enrichment = True
    _combined_marker = "\n<!-- FUNDING-INTELLIGENCE-CRT-ARCHIVE-PAGE -->\n"
    _detail_date_re = re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b|"
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|"
        r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b|"
        r"\b[A-Za-zÀ-ÿ]+\s+\d{1,2},\s*\d{4}\b",
        re.IGNORECASE,
    )
    _known_rejects = re.compile(r"\b(?:agenda\s+della\s+disabilit[aà]|european\s+pavilion)\b", re.IGNORECASE)
    _strong_application_evidence = re.compile(
        r"\b(?:bando|avviso|richiest\w*\s+di\s+contribut\w*|presentazion\w*\s+delle\s+domand\w*|"
        r"modalit[aà]\s+di\s+partecipazione|come\s+partecipare|soggetti\s+ammissibili|"
        r"servizio\s+online|scadenz\w*)\b",
        re.IGNORECASE,
    )
    _weak_application_evidence = re.compile(r"\b(?:candidatur\w*|beneficiar\w*|domand\w*)\b", re.IGNORECASE)
    _project_language = re.compile(
        r"\b(?:progetto|programma|iniziativ\w*\s+della\s+fondazione|attivit[aà]\s+gi[aà]\s+avviat\w*|edizione\s+storica)\b",
        re.IGNORECASE,
    )
    _official_status = {
        "in arrivo": "UPCOMING",
        "in corso": "OPEN",
        "risultati": "CLOSED",
    }
    _current_application_evidence = re.compile(
        r"\b(?:pubblicazione\s+(?:del\s+)?bando|presentazion\w*\s+delle\s+domand\w*|"
        r"servizio\s+on\s*line|servizio\s+online|scadenz\w*|domand\w*\s+si\s+[eè]\s+chius\w*)\b",
        re.IGNORECASE,
    )
    # Used only when the official badge says “In corso” but the detail does
    # not expose a parseable application deadline.  A generic mention of a
    # past deadline is not enough to keep a record OPEN; the page must expose
    # an actual current application channel or an explicit open-submission
    # statement.
    _explicit_current_application_evidence = re.compile(
        r"\b(?:servizio\s+on\s*line|servizio\s+online|presentazion\w*\s+(?:delle\s+)?domand\w*\s+(?:[eè]\s+)?(?:apert\w*|possibil\w*)|"
        r"domand\w*\s+(?:apert\w*|possibil\w*)|candidatur\w*\s+(?:apert\w*|possibil\w*)|"
        r"presentare\s+(?:la\s+)?domand\w*\s+entro)\b",
        re.IGNORECASE,
    )

    def _fetch_url(self, url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html", "User-Agent": policy.user_agent})
        for attempt in range(policy.retries + 1):
            try:
                with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
                    if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                        raise AdapterError(f"unexpected content type from {self.source_label}")
                    payload = response.read(policy.max_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < policy.retries:
                    sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"HTTP {exc.code} from {self.source_label}", status_code=exc.code) from exc
            except URLError as exc:
                if attempt < policy.retries:
                    sleep(0.2 * (attempt + 1))
                    continue
                raise AdapterError(f"connection failed for {self.source_label}: {exc.reason}") from exc
        if len(payload) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} exceeds download size limit")
        return payload

    @staticmethod
    def _next_page(text: str) -> str | None:
        parser = _AnchorTextParser()
        parser.feed(text)
        for href, raw_title in parser.links:
            title = re.sub(r"\s+", " ", raw_title).strip().casefold()
            if re.search(r"\b(?:successiv\w*|next)\b", title):
                return href
        return None

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        """Follow only the CRT archive's own next-page links."""
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        pages: list[bytes] = []
        seen_urls: set[str] = set()
        url = self.page_url
        for _ in range(10):
            if url in seen_urls:
                break
            seen_urls.add(url)
            page = self._fetch_url(url, policy)
            pages.append(page)
            next_href = self._next_page(decode_html(page))
            if not next_href:
                break
            next_url = urljoin(url, next_href)
            if not next_url.startswith("https://www.fondazionecrt.it/cpt_bandi-progetti-archive/"):
                break
            url = next_url
        combined = self._combined_marker.encode("utf-8").join(pages)
        if len(combined) > policy.max_bytes:
            raise AdapterError(f"{self.source_label} paginated response exceeds size limit")
        return combined

    def _include_link(self, official_url: str, title: str) -> bool:
        if not super()._include_link(official_url, title):
            return False
        parsed = urlsplit(official_url)
        path = parsed.path.rstrip("/").lower()
        if parsed.netloc.lower() != "www.fondazionecrt.it":
            return False
        if not path.startswith("/bandi-progetti/") or path == "/bandi-progetti":
            return False
        if path.endswith(".pdf") or "/page/" in path:
            return False
        if title.casefold() in {"scopri di più", "scopri di piu", "leggi", "dettagli", "torna su", "presenta una richiesta"}:
            return False
        return True

    def _parse_page(self, text: str) -> list[SourceRecord]:
        parser = _AnchorTextParser()
        parser.feed(text)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for index, (href, raw_title) in enumerate(parser.links, 1):
            title = self._clean(derive_title(text, href, raw_title))
            official_url = urljoin(self.page_url, href)
            if not self._include_link(official_url, title):
                continue
            context = _context(text, href, title, 1500)
            # Discovery deliberately does not require application words in the
            # short card.  The detail page decides opportunity vs project.
            if re.search(r"\b(?:risultat\w*|news|privacy|cookie|torna\s+su)\b", title, re.IGNORECASE):
                continue
            external_id = self._external_id(official_url, index)
            if external_id in seen:
                continue
            seen.add(external_id)
            clean_title = re.sub(r"^(?:in\s+corso|risultat\w*|in\s+arrivo)\s+", "", title, flags=re.IGNORECASE).strip()
            regions = extract_regions(context)
            records.append(SourceRecord(
                external_id=external_id,
                title=clean_title or title,
                official_url=official_url,
                funder=self.funder,
                programme=self.programme,
                deadline=None,
                total_budget=extract_money(context),
                eligible_entities=extract_entities(context),
                description=compact(f"{self.source_label}: {context}"),
                source_status=infer_status(context, "UNKNOWN"),
                regions=regions,
                territory="Piemonte e Valle d'Aosta" if regions else None,
            ))
        return records

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        pages = text.split(self._combined_marker)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for page in pages:
            for record in self._parse_page(page):
                if record.external_id in seen:
                    continue
                seen.add(record.external_id)
                records.append(record)
        return records

    @classmethod
    def _detail_is_opportunity(cls, title: str, text: str, badge_status: str | None = None) -> bool:
        if cls._known_rejects.search(title):
            return False
        # These pages are retained only when the official detail itself
        # documents a real call/result (rather than a project landing page).
        # The evidence is textual and source-local; it is not a global title
        # blacklist or a psychology-relevance filter.
        if re.search(r"\b(?:mezzi\s+protezione|donoscuola|progetto\s+lagrange)\b", title, re.IGNORECASE):
            if not cls._current_application_evidence.search(text):
                return False
        if re.search(r"ultima\s+edizione\s+(?:si\s+)?(?:[èe]\s+)?tenut\w*\s+nel\s+2021|bando\s+2021", text, re.IGNORECASE):
            if not cls._current_application_evidence.search(text):
                return False
        # Culture of Solidarity is a historical call with a results badge;
        # the page explicitly says that a call awarded projects, so keep it in
        # the archive even though no current window remains.
        historical_call = bool(
            re.search(r"culture\s+of\s+solidarity\s+fund", text, re.IGNORECASE)
            and re.search(r"ha\s+promosso\s+un\s+bando|ha\s+premiato", text, re.IGNORECASE)
        )
        if badge_status == "CLOSED" and historical_call:
            return True
        if badge_status == "CLOSED" and re.search(r"missione\s+soccorso", title, re.IGNORECASE) and cls._strong_application_evidence.search(text):
            return True
        strong = bool(cls._strong_application_evidence.search(text))
        weak = bool(cls._weak_application_evidence.search(text))
        project = bool(cls._project_language.search(text))
        if strong:
            return True
        if weak and not project:
            return True
        return False

    @classmethod
    def _detail_deadlines(cls, text: str) -> list[date]:
        plain = re.sub(r"\s+", " ", text).strip()
        candidates: list[date] = []
        # Keep extraction local to labelled windows; unrelated dates in the
        # CRT footer/related cards must not determine the call status.
        label = re.compile(
            r"(?:\b\d+\s*[°º.]?\s*(?:scadenza|finestra)|\b(?:prima|seconda|terza|unica)\s+scadenza|"
            r"\bscadenza|\btermine(?:\s+finale)?|\bentro\s+il|\bpresentare[^.;]{0,40}\s+entro|"
            r"\bdomand\w*\s+si\s+[eè]\s+chius\w*)",
            re.IGNORECASE,
        )
        for match in label.finditer(plain):
            window = plain[match.start():match.start() + 240]
            for date_match in cls._detail_date_re.finditer(window):
                parsed = parse_date(date_match.group(0))
                if parsed and parsed not in candidates:
                    candidates.append(parsed)
        return sorted(candidates)

    @classmethod
    def _official_badge(cls, title: str, payload: bytes) -> str | None:
        """Read CRT's lifecycle badge from the page chrome.

        The badge is rendered outside Elementor's post-content container, so
        `_detail_text` cannot see it.  CRT repeats the heading three times
        (document title, navigation and page heading); the status immediately
        after the third occurrence is the authoritative one.  The bounded
        token anchor also tolerates the occasional mojibake in accented
        headings returned by the site.
        """
        from ._v04_common import page_text

        plain = page_text(payload)
        if not plain:
            return None
        first = (title or "").split()[0]
        token_match = re.match(r"[a-z0-9]+", first.casefold())
        token = token_match.group(0) if token_match else ""
        if len(token) < 3:
            return None
        compact_plain = re.sub(r"[^a-z0-9]+", " ", plain.casefold())
        # Some lightweight fixture/page templates concatenate an h1 and a
        # sibling status span without a separating space; a substring anchor
        # keeps those valid badges discoverable while remaining bounded to the
        # first heading token.
        matches = list(re.finditer(re.escape(token), compact_plain))
        for occurrence in matches[:4]:
            window = compact_plain[occurrence.start():occurrence.start() + 260]
            match = re.search(r"(in\s+arrivo|in\s+corso|risultati)\b", window, re.IGNORECASE)
            if match:
                return cls._official_status.get(match.group(1).casefold())
        return None

    @staticmethod
    def _detail_opening(text: str) -> date | None:
        match = re.search(r"pubblicazione\s+(?:del\s+)?bando\s*:\s*([^.;]{1,80})", text, re.IGNORECASE)
        if not match:
            return None
        values = [parse_date(item) for item in FondazioneCrtAdapter._detail_date_re.findall(match.group(1))]
        return next((value for value in values if value), None)

    @staticmethod
    def _detail_text(payload: bytes) -> str:
        text = decode_html(payload)
        parser = _CrtDetailTextParser()
        parser.feed(text)
        if parser.text:
            return parser.text
        fallback = _DetailTextParser()
        fallback.feed(text)
        return fallback.text

    @staticmethod
    def _fetch_detail(url: str, policy: FetchPolicy) -> bytes:
        request = Request(url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": policy.user_agent})
        with _core_adapters.urlopen(request, timeout=policy.timeout_seconds) as response:
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise AdapterError("unexpected detail content type from Fondazione CRT")
            payload = response.read(policy.max_bytes + 1)
        if len(payload) > policy.max_bytes:
            raise AdapterError("detail page exceeds size limit for Fondazione CRT")
        return payload

    def enrich(self, records, policy=None, *, max_details: int = 40):
        policy = policy or FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1)
        today = date.today()
        enriched: list[SourceRecord] = []
        cache: dict[str, bytes] = {}
        for index, record in enumerate(records):
            if index >= max_details:
                enriched.append(record)
                continue
            try:
                payload = cache.get(record.official_url)
                if payload is None:
                    payload = self._fetch_detail(record.official_url, policy)
                    cache[record.official_url] = payload
                detail_text = self._detail_text(payload)
                badge_status = self._official_badge(record.title, payload)
                if not self._detail_is_opportunity(record.title, detail_text, badge_status):
                    continue
                fields = _detail_fields(payload)
                deadlines = self._detail_deadlines(detail_text)
                future = [value for value in deadlines if value >= today]
                deadline = (min(future) if future else max(deadlines)) if deadlines else fields.get("deadline") or record.deadline
                # CRT's badge is authoritative only after applying the
                # application-window precedence required by the source
                # contract.  In particular, an “In corso” card with every
                # application deadline in the past is CLOSED; an OPEN card
                # without a deadline stays OPEN only when the detail exposes
                # an explicit current application channel.
                if badge_status == "CLOSED":
                    status = "CLOSED"
                elif badge_status == "UPCOMING":
                    status = "UPCOMING"
                elif badge_status == "OPEN":
                    if future:
                        status = "OPEN"
                    elif deadlines:
                        status = "CLOSED"
                    elif self._explicit_current_application_evidence.search(detail_text):
                        status = "OPEN"
                    else:
                        status = "UNKNOWN"
                else:
                    status = "OPEN" if future else "CLOSED" if deadlines else str(fields.get("source_status") or record.source_status)
                if status == "UNKNOWN" and not badge_status:
                    status = record.source_status
                description = str(detail_text or fields.get("description") or record.description)
                enriched.append(replace(
                    record,
                    opening_date=self._detail_opening(detail_text) or fields.get("opening_date") or record.opening_date,
                    deadline=deadline,
                    total_budget=extract_money(detail_text) or fields.get("total_budget") or record.total_budget,
                    eligible_entities=tuple(extract_entities(detail_text) or fields.get("eligible_entities") or record.eligible_entities),
                    description=compact(description),
                    source_status=status,
                    status_authoritative=bool(badge_status) or record.status_authoritative,
                    territory=record.territory or "Piemonte e Valle d'Aosta",
                ))
            except (AdapterError, OSError, ValueError):
                # A transient detail error must not erase a discovered card;
                # successful detail responses still enforce project rejection.
                enriched.append(record)
        return enriched
