from __future__ import annotations

import html
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from funding_core.adapters import (
    _AnchorTextParser,
    _HtmlOpportunityListAdapter,
    is_funding_opportunity,
)
from funding_core.dates import parse_date
from funding_core.models import SourceRecord
from funding_core.territories import normalize_territory, split_regions


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b|"
    r"\b[A-Za-zÀ-ÿ]+\s+\d{1,2},\s*\d{4}\b",
    re.IGNORECASE,
)
_REGION_RE = re.compile(
    r"Abruzzo|Basilicata|Calabria|Campania|Emilia[- ]Romagna|Friuli[- ]Venezia Giulia|"
    r"Lazio|Liguria|Lombardia|Marche|Molise|Piemonte|Puglia|Sardegna|Sicilia|"
    r"Toscana|Trentino[- ]Alto Adige|Umbria|Valle d['’]Aosta|Veneto",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    r"(?:€|eur(?:o)?|euro|plafond|dotazione|risorse|budget|stanziamento|importo)"
    r"[^€$0-9]{0,30}(?:€|eur(?:o)?|euro)?\s*([0-9][0-9. ,]{2,})",
    re.IGNORECASE,
)
_DIV_TAG_RE = re.compile(r"</?div\b[^>]*>", re.IGNORECASE)
_CARD_DIV_RE = re.compile(
    r"<div\b[^>]*(?:class|id)\s*=\s*['\"][^'\"]*"
    r"(?:card|item|entry|opportun|bando|call|contribut|result|teaser)[^'\"]*['\"][^>]*>",
    re.IGNORECASE,
)


def decode_html(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
        if "\ufffd" in text:
            text = raw.decode("cp1252", errors="replace")
    else:
        text = raw
    return html.unescape(text)


def compact(value: str, limit: int = 1600) -> str:
    value = _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html.unescape(value))).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _matching_div_span(text: str, start: int, position: int) -> tuple[int, int] | None:
    """Return the smallest matching div that contains ``position``.

    Several official foundation sites render cards as nested ``div`` blocks
    rather than semantic ``article``/``li`` elements.  A bounded depth walk
    keeps metadata (status/deadline) inside the card that owns the link while
    avoiding the neighbouring card's values.
    """
    depth = 0
    for match in _DIV_TAG_RE.finditer(text, start):
        tag = match.group(0)
        if tag.startswith("</"):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            if match.start() >= position:
                return (start, match.end())
            return None
    return None


def _context(text: str, href: str, title: str, window: int = 900) -> str:
    candidates = [match.start() for match in re.finditer(re.escape(html.unescape(href)), text)]
    # The same href is often emitted once for an image overlay and once for
    # the visible card title.  The final occurrence is the visible card in
    # the official lists we support and avoids pairing a title with the
    # preceding row's metadata.
    title_position = text.find(title) if title else -1
    position = candidates[-1] if candidates else (title_position if title_position >= 0 else 0)
    # Prefer the smallest common card/row container.  This prevents a date or
    # status from the next card (or a global navigation block) leaking into
    # the current record while retaining a bounded fallback for irregular HTML.
    containers: list[tuple[int, int]] = []
    # Compagnia di San Paolo and several foundation portals use a classed
    # ``div`` for each card.  Match only clearly card-like class/id values and
    # perform a bounded depth walk so nested layout divs do not leak metadata.
    for match in _CARD_DIV_RE.finditer(text, max(0, position - 12000), position + 1):
        span = _matching_div_span(text, match.start(), position)
        if span:
            start, end = span
            if end - start <= 6000:
                containers.append((start, end))
    for tag in ("article", "tr", "li", "section"):
        start = text.rfind(f"<{tag}", 0, position)
        end_marker = f"</{tag}>"
        end = text.find(end_marker, position)
        if start >= 0 and end >= position:
            span = end + len(end_marker) - start
            if span <= 6000:
                containers.append((start, end + len(end_marker)))
    if containers:
        start, end = min(containers, key=lambda item: item[1] - item[0])
        return compact(text[start:end], 2400)
    start = max(0, position - window)
    end = min(len(text), position + max(window, len(href) + len(title) + 400))
    return compact(text[start:end], 2400)


def derive_title(text: str, href: str, title: str) -> str:
    """Recover a card heading when an official list labels links “Scopri di più”."""
    normalized = _SPACE_RE.sub(" ", html.unescape(title or "")).strip()
    if normalized.lower() not in {"scopri di più", "scopri di piu", "scopri tutto", "leggi", "leggi tutto", "vai", "dettagli"}:
        return normalized
    occurrences = [match.start() for match in re.finditer(re.escape(html.unescape(href)), text)]
    if not occurrences:
        return normalized
    position = occurrences[-1]
    before = text[max(0, position - 1400):position]
    headings = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", before, re.IGNORECASE | re.DOTALL)
    if headings:
        candidate = compact(headings[-1], 300)
        if len(candidate) >= 5:
            return candidate
    return normalized


def infer_status(value: str, default: str = "UNKNOWN") -> str:
    lowered = value.lower()
    if re.search(r"\b(?:scadut[oaie]?|chius[oaie]?|closed|expired|non\s+più\s+attiv[oa])\b", lowered):
        return "CLOSED"
    if re.search(r"\b(?:in\s+programma|prossim[oa]|lancio|previst[oa]|upcoming|calendar(?:io)?)\b", lowered):
        return "UPCOMING"
    if re.search(r"\b(?:apert[oaie]?|attiv[oaie]?|in\s+corso|open|active|invio\s+candidature)\b", lowered):
        return "OPEN"
    return default


def _date_after_label(context: str, labels: tuple[str, ...]) -> date | None:
    pattern = r"(?:" + "|".join(labels) + r")[^.;\n]{0,100}"
    match = re.search(pattern, context, re.IGNORECASE)
    if not match:
        return None
    date_match = _DATE_RE.search(match.group(0))
    return parse_date(date_match.group(0)) if date_match else None


def extract_deadline(context: str) -> date | None:
    return _date_after_label(context, ("scadenza", "scade", "termine", "deadline", "chiusura", "entro"))


def extract_opening(context: str) -> date | None:
    return _date_after_label(context, ("apertura", "apre", "opening", "dal", "pubblicat[oa]"))


def extract_money(context: str) -> int | None:
    for match in _MONEY_RE.finditer(context):
        digits = re.sub(r"[^0-9]", "", match.group(1))
        if digits:
            return int(digits)
    return None


def extract_entities(context: str) -> tuple[str, ...]:
    match = re.search(
        r"(?:destinatari|beneficiari|soggetti\s+ammissibili|chi\s+può\s+partecipare|applicant|proponenti)"
        r"\s*[:\-]?\s*([^.;\n]{1,260})",
        context,
        re.IGNORECASE,
    )
    return (compact(match.group(1), 260),) if match else ()


def extract_regions(context: str) -> tuple[str, ...]:
    return split_regions([match.group(0) for match in _REGION_RE.finditer(context)])


def opportunity_context_ok(title: str, context: str, *, allow_status_context: bool = False) -> bool:
    if not title or len(title) < 5:
        return False
    lowered_title = title.lower()
    lowered = f"{title} {context}".lower()
    # Apply contamination rules to the candidate title first.  Listing pages
    # commonly include a global “Eventi/News” navigation block in the same
    # HTML window as a real card; rejecting the whole context would discard
    # valid calls merely because of that site chrome.
    if re.search(r"\b(?:contributi?\s+(?:deliberati|assegnati)|progetti?\s+selezionati|iniziative?\s+selezionate|graduatori\w*|esiti|eventi?|news|comunicat\w*)\b", lowered_title):
        return False
    if is_funding_opportunity(title, context):
        return True
    if allow_status_context and infer_status(context) in {"OPEN", "UPCOMING", "CLOSED"}:
        if re.search(r"\b(?:eventi?|news|comunicat\w*)\b", lowered_title):
            return False
        return bool(re.search(r"\b(?:bando|avviso|call|contribut|opportunit|progett|iniziativ|agenda|percorsi|housing|welfare)\b", lowered))
    return False


def parse_listing_records(
    adapter: _HtmlOpportunityListAdapter,
    raw: bytes | str,
    *,
    allow_status_context: bool = False,
    default_status: str = "UNKNOWN",
    context_window: int = 900,
) -> list[SourceRecord]:
    """Parse bounded link cards while leaving inclusion rules to each adapter."""
    text = decode_html(raw)
    parser = _AnchorTextParser()
    parser.feed(text)
    records: list[SourceRecord] = []
    seen: set[str] = set()
    for index, (href, raw_title) in enumerate(parser.links, 1):
        title = adapter._clean(derive_title(text, href, raw_title))
        official_url = urljoin(adapter.page_url, href)
        if not adapter._include_link(official_url, title):
            continue
        context = _context(text, href, title, context_window)
        if not opportunity_context_ok(title, context, allow_status_context=allow_status_context):
            continue
        external_id = adapter._external_id(official_url, index)
        if external_id in seen:
            continue
        seen.add(external_id)
        regions = extract_regions(context)
        status = infer_status(context, default_status)
        records.append(SourceRecord(
            external_id=external_id,
            title=title,
            official_url=official_url,
            funder=adapter.funder,
            programme=adapter.programme,
            opening_date=extract_opening(context),
            deadline=extract_deadline(context),
            total_budget=extract_money(context),
            eligible_entities=extract_entities(context),
            description=compact(f"{adapter.source_label}: {context}"),
            source_status=status,
            regions=regions,
            territory=normalize_territory(regions, context),
        ))
    return records


class DedicatedHtmlAdapter(_HtmlOpportunityListAdapter):
    """Thin source-local shell; no cross-foundation policy is encoded here."""

    allow_status_context = False
    default_status = "UNKNOWN"
    detail_enrichment = True

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        return parse_listing_records(
            self,
            raw,
            allow_status_context=self.allow_status_context,
            default_status=self.default_status,
        )

    def enrich(self, records, policy=None, *, max_details: int = 40):
        if not self.detail_enrichment:
            return records
        return super().enrich(records, policy, max_details=max_details)
