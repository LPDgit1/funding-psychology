from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Callable

from .adapters import (
    AdapterError,
    AigOpportunitiesAdapter,
    ConIBambiniAdapter,
    DipartimentoDisabilitaAdapter,
    DipartimentoFamigliaAdapter,
    ErasmusIndireAdapter,
    EuFundingTendersAdapter,
    FondoRepubblicaDigitaleAdapter,
    FondazioneCariparoAdapter,
    FondazioneCariveronaAdapter,
    IncentiviGovAdapter,
    InterregItalyCroatiaAdapter,
    FetchPolicy,
    VenetoBandiAdapter,
    VenetoFesrCalendarAdapter,
    VenetoFseCalendarAdapter,
)
from .models import Opportunity, SourceRecord
from .pipeline import anomaly_warnings, process


@dataclass(frozen=True)
class SnapshotSourceSpec:
    source_id: str
    adapter_factory: Callable[[], object]
    max_bytes: int


# These sources have a working live transport and are safe to include in the
# first public snapshot.  The two Veneto programme calendars stay explicitly
# fixture-only until their official download contracts are stable.
LIVE_SOURCE_SPECS: tuple[SnapshotSourceSpec, ...] = (
    SnapshotSourceSpec("eu-funding-tenders", EuFundingTendersAdapter, 25_000_000),
    SnapshotSourceSpec("incentivi-gov", IncentiviGovAdapter, 30_000_000),
    SnapshotSourceSpec("erasmus-indire", ErasmusIndireAdapter, 10_000_000),
    SnapshotSourceSpec("aig-opportunities", AigOpportunitiesAdapter, 8_000_000),
    SnapshotSourceSpec("interreg-italy-croatia", InterregItalyCroatiaAdapter, 15_000_000),
    SnapshotSourceSpec("veneto-bandi", VenetoBandiAdapter, 30_000_000),
    SnapshotSourceSpec("dipartimento-famiglia", DipartimentoFamigliaAdapter, 8_000_000),
    SnapshotSourceSpec("dipartimento-disabilita", DipartimentoDisabilitaAdapter, 8_000_000),
    SnapshotSourceSpec("fondazione-cariparo", FondazioneCariparoAdapter, 10_000_000),
    SnapshotSourceSpec("fondazione-cariverona", FondazioneCariveronaAdapter, 10_000_000),
    SnapshotSourceSpec("con-i-bambini", ConIBambiniAdapter, 10_000_000),
    SnapshotSourceSpec("fondo-repubblica-digitale", FondoRepubblicaDigitaleAdapter, 10_000_000),
)


FIXTURE_SOURCE_SPECS: tuple[tuple[str, type, str], ...] = (
    ("veneto-fse-calendar", VenetoFseCalendarAdapter, "veneto_fse_calendar.csv"),
    ("veneto-fesr-calendar", VenetoFesrCalendarAdapter, "veneto_fesr_calendar.csv"),
)


ALL_SOURCE_IDS = tuple(spec.source_id for spec in LIVE_SOURCE_SPECS) + tuple(item[0] for item in FIXTURE_SOURCE_SPECS)

_MONTHS = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
def _verified_label(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _shorten(value: str, limit: int = 360) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _amount(value: int | None) -> str | None:
    if value is None:
        return None
    return f"€{value:,.0f}".replace(",", ".")


def _territory(source_id: str, item_territory: str | None = None) -> str:
    if item_territory:
        return item_territory
    if source_id == "eu-funding-tenders":
        return "Unione Europea"
    if source_id.startswith("veneto-"):
        return "Veneto"
    return "Italia"


def public_opportunity(
    item: Opportunity,
    verified_on: date,
    *,
    now: datetime | None = None,
    previous: dict[str, Any] | None = None,
    source_label: str | None = None,
) -> dict[str, Any]:
    """Map an internal opportunity to a compact, traceable public record."""
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    stable_suffix = item.source_external_id or hashlib.sha1(item.official_url.encode("utf-8")).hexdigest()[:12]
    stable_id = f"{item.source_id}:{stable_suffix}"
    unchanged = bool(previous and previous.get("contentHash") == item.content_hash)
    first_seen = (previous or {}).get("firstSeen") or stamp
    last_changed = (previous or {}).get("lastChanged") if unchanged else stamp
    payload: dict[str, Any] = {
        "id": stable_id,
        "title": item.title,
        "funder": item.funder,
        "programme": item.programme,
        "status": item.status,
        "territory": _territory(item.source_id, item.territory),
        "regions": list(item.regions),
        "eligibleEntities": list(item.eligible_entities),
        "macroAreas": list(item.macro_areas),
        "summary": _shorten(item.short_description or "Descrizione non esposta dalla lista ufficiale."),
        "relevance": item.relevance_label,
        "relevanceScore": item.relevance_score,
        "positiveSignals": list(item.positive_signals),
        "negativeSignals": list(item.negative_signals),
        "relevanceWhy": (
            "La classificazione testuale intercetta segnali direttamente collegati a interventi psicologici o psicosociali."
            if item.relevance_label == "Alta" else
            "La classificazione testuale intercetta segnali adiacenti; verifica il testo ufficiale prima di candidare il progetto."
            if item.relevance_label == "Media" else
            "La scheda non contiene segnali sufficienti per una rilevanza psicologica automatica."
        ),
        "officialUrl": item.official_url,
        "aggregatorUrl": item.aggregator_url,
        "sourceLabel": source_label or item.source_id,
        "lastVerified": _verified_label(verified_on),
        "firstSeen": first_seen,
        "lastSeen": stamp,
        "lastChanged": last_changed or stamp,
        "contentHash": item.content_hash,
        "demo": False,
        "sourceId": item.source_id,
    }
    if item.deadline:
        payload["deadline"] = item.deadline.isoformat()
    if item.opening_date:
        payload["openingDate"] = item.opening_date.isoformat()
    amount = _amount(item.total_budget)
    if amount:
        payload["amount"] = amount
    return payload


def _source_label(adapter: object, source_id: str) -> str:
    return str(getattr(adapter, "source_label", source_id))


def _record_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "")


def _index_previous(*snapshots: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        for item in snapshot.get("opportunities", []):
            if isinstance(item, dict) and _record_id(item):
                indexed[_record_id(item)] = item
    return indexed


def _previous_source_items(*snapshots: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        for item in snapshot.get("opportunities", []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("sourceId") or "")
            if source_id:
                grouped.setdefault(source_id, []).append(item)
    return grouped


def _sort_public(items: list[dict[str, Any]]) -> None:
    rank = {"Alta": 0, "Media": 1, "Bassa": 2}
    items.sort(key=lambda item: (
        rank.get(str(item.get("relevance")), 3),
        item.get("deadline") or "9999-12-31",
        item.get("firstSeen") or "9999-12-31T00:00:00Z",
        str(item.get("title", "")).lower(),
    ))


def _envelope(
    *,
    dataset: str,
    now: datetime,
    today: date,
    opportunities: list[dict[str, Any]],
    source_results: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    _sort_public(opportunities)
    return {
        "schemaVersion": 2,
        "dataset": dataset,
        "generatedAt": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "asOfDate": today.isoformat(),
        "complete": not any(item.get("status") in {"ERROR", "STALE"} for item in source_results),
        "recordCount": len(opportunities),
        "recordCountCurrent": len(opportunities) if dataset == "current" else 0,
        "recordCountArchive": len(opportunities) if dataset == "archive" else 0,
        "liveSourceCount": sum(1 for item in source_results if item["kind"] == "live" and item["status"] == "LIVE"),
        "sourceCount": len(source_results),
        "sources": source_results,
        "warnings": warnings,
        "notImplemented": ["Pari Opportunità", "Dipendenze", "FAMI"],
        "opportunities": opportunities,
    }


def build_snapshot_set(
    *,
    today: date | None = None,
    now: datetime | None = None,
    previous_current: dict[str, Any] | None = None,
    previous_archive: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    previous_by_id = _index_previous(previous_current, previous_archive)
    previous_by_source = _previous_source_items(previous_current, previous_archive)
    current_opportunities: list[dict[str, Any]] = []
    archive_opportunities: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    warnings_all: list[str] = []

    for spec in LIVE_SOURCE_SPECS:
        adapter = spec.adapter_factory()
        previous_items = previous_by_source.get(spec.source_id, [])
        previous_count = len(previous_items)
        try:
            raw = adapter.fetch(FetchPolicy(timeout_seconds=25, max_bytes=spec.max_bytes, retries=2))
            records: list[SourceRecord] = adapter.parse(raw)
            enrich = getattr(adapter, "enrich", None)
            if callable(enrich):
                records = enrich(records, FetchPolicy(timeout_seconds=12, max_bytes=2_000_000, retries=1), max_details=40)
            normalized = process(spec.source_id, records, today)
            warnings = anomaly_warnings(
                len(normalized), [previous_count] if previous_count else [], [record.title for record in records], [record.deadline for record in records]
            )
            if spec.source_id == "aig-opportunities":
                # The strict v0.2.1 event filter intentionally removes most
                # editorial posts from the old feed; this is not a transport
                # anomaly when a non-empty parsed result remains.
                warnings = [warning for warning in warnings if "dropped by more than half" not in warning]
            # AIG's v0.2.1 parser deliberately removes editorial/event posts,
            # so a non-empty result can legitimately be much smaller than the
            # previous broad feed.  Keep the zero-result protection for that
            # source, while retaining the stronger drop guard everywhere else.
            suspicious = previous_count >= 10 and (
                len(normalized) == 0
                or (spec.source_id != "aig-opportunities" and len(normalized) < max(1, int(previous_count * 0.2)))
            )
            if suspicious:
                warning = f"{spec.source_id}: parser anomaly; preserved {previous_count} previous records"
                warnings = [*warnings, warning]
                warnings_all.append(warning)
                current_opportunities.extend(item for item in previous_items if item.get("status") != "CLOSED")
                archive_opportunities.extend(item for item in previous_items if item.get("status") == "CLOSED")
                source_status = "STALE"
                published_count = previous_count
                source_current_count = sum(1 for item in previous_items if item.get("status") != "CLOSED")
                source_archive_count = sum(1 for item in previous_items if item.get("status") == "CLOSED")
                new_count = updated_count = unchanged_count = 0
            else:
                mapped = [
                    public_opportunity(
                        item,
                        today,
                        now=now,
                        previous=previous_by_id.get(f"{item.source_id}:{item.source_external_id or hashlib.sha1(item.official_url.encode('utf-8')).hexdigest()[:12]}"),
                        source_label=_source_label(adapter, spec.source_id),
                    )
                    for item in normalized
                ]
                mapped_ids = {_record_id(item) for item in mapped}
                retained_archive = [
                    item for item in previous_items
                    if item.get("status") == "CLOSED" and _record_id(item) not in mapped_ids
                ]
                current_opportunities.extend(item for item in mapped if item.get("status") != "CLOSED")
                archive_opportunities.extend(item for item in mapped if item.get("status") == "CLOSED")
                archive_opportunities.extend(retained_archive)
                source_status = "LIVE"
                published_count = len(mapped) + len(retained_archive)
                source_current_count = sum(1 for item in mapped if item.get("status") != "CLOSED")
                source_archive_count = sum(1 for item in mapped if item.get("status") == "CLOSED") + len(retained_archive)
                old_ids = {_record_id(item) for item in previous_items}
                new_count = sum(1 for item in mapped if _record_id(item) not in old_ids)
                updated_count = sum(1 for item in mapped if _record_id(item) in old_ids and item.get("contentHash") != next((old.get("contentHash") for old in previous_items if _record_id(old) == _record_id(item)), None))
                unchanged_count = published_count - new_count - updated_count
            if warnings:
                warnings_all.extend(f"{spec.source_id}: {warning}" for warning in warnings)
            source_results.append({
                "sourceId": spec.source_id,
                "label": _source_label(adapter, spec.source_id),
                "kind": "live",
                "status": source_status,
                "fetchedRecords": len(records),
                "parsedRecords": len(normalized),
                "publishedRecords": published_count,
                "currentRecords": source_current_count,
                "archiveRecords": source_archive_count,
                "new": new_count,
                "updated": updated_count,
                "unchanged": unchanged_count,
                "warnings": warnings,
            })
        except (AdapterError, ValueError, OSError, IncompleteRead) as exc:
            message = str(exc)
            warning = f"{spec.source_id}: {message}; preserved {previous_count} previous records"
            warnings_all.append(warning)
            current_opportunities.extend(item for item in previous_items if item.get("status") != "CLOSED")
            archive_opportunities.extend(item for item in previous_items if item.get("status") == "CLOSED")
            source_results.append({
                "sourceId": spec.source_id,
                "label": _source_label(adapter, spec.source_id),
                "kind": "live",
                "status": "ERROR" if not previous_items else "STALE",
                "fetchedRecords": 0,
                "parsedRecords": 0,
                "publishedRecords": previous_count,
                "currentRecords": sum(1 for item in previous_items if item.get("status") != "CLOSED"),
                "archiveRecords": sum(1 for item in previous_items if item.get("status") == "CLOSED"),
                "new": 0,
                "updated": 0,
                "unchanged": previous_count,
                "warnings": [warning],
            })

    fixture_root = Path(__file__).with_name("fixtures")
    for source_id, adapter_factory, fixture_name in FIXTURE_SOURCE_SPECS:
        adapter = adapter_factory()
        try:
            records = adapter.parse((fixture_root / fixture_name).read_bytes())
            source_results.append({
                "sourceId": source_id,
                "label": _source_label(adapter, source_id),
                "kind": "fixture",
                "status": "FIXTURE_ONLY",
                "fetchedRecords": len(records),
                "parsedRecords": len(records),
                "publishedRecords": 0,
                "warnings": ["Fixture verificata; non pubblicata finché il contratto live non è stabile."],
            })
        except (OSError, ValueError, AdapterError) as exc:
            source_results.append({
                "sourceId": source_id,
                "label": _source_label(adapter, source_id),
                "kind": "fixture",
                "status": "ERROR",
                "fetchedRecords": 0,
                "parsedRecords": 0,
                "publishedRecords": 0,
                "warnings": [str(exc)],
            })

    return {
        "current": _envelope(
            dataset="current", now=now, today=today,
            opportunities=current_opportunities, source_results=source_results, warnings=warnings_all,
        ),
        "archive": _envelope(
            dataset="archive", now=now, today=today,
            opportunities=archive_opportunities, source_results=source_results, warnings=warnings_all,
        ),
    }


def build_snapshot(*, today: date | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Compatibility wrapper returning the operational/current envelope."""
    return build_snapshot_set(today=today, now=now)["current"]


def write_snapshot(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    return target
