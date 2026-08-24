from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
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
    SnapshotSourceSpec("veneto-bandi", VenetoBandiAdapter, 5_000_000),
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
_HIGH_RELEVANCE = {
    "Salute mentale e benessere",
    "Minori e adolescenti",
    "Famiglia e genitorialità",
    "Inclusione sociale e vulnerabilità",
    "Disabilità e neurodiversità",
    "Violenza, trauma e tutela",
    "Dipendenze",
    "Anziani, ageing e caregiver",
    "Migrazione, integrazione e intercultura",
}


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


def _territory(source_id: str) -> str:
    if source_id == "eu-funding-tenders":
        return "Unione Europea"
    if source_id.startswith("veneto-"):
        return "Veneto"
    return "Italia"


def _relevance(areas: tuple[str, ...]) -> tuple[str, str]:
    if any(area in _HIGH_RELEVANCE for area in areas):
        return "Alta", "La classificazione testuale intercetta almeno un'area direttamente collegata a interventi psicologici o psicosociali."
    if areas:
        return "Media", "La classificazione testuale intercetta un'area adiacente; verifica il testo ufficiale prima di candidare il progetto."
    return "Bassa", "La scheda non contiene parole chiave sufficienti per una rilevanza psicologica automatica."


def public_opportunity(item: Opportunity, verified_on: date) -> dict[str, Any]:
    relevance, relevance_why = _relevance(item.macro_areas)
    stable_suffix = item.source_external_id or hashlib.sha1(item.official_url.encode("utf-8")).hexdigest()[:12]
    payload: dict[str, Any] = {
        "id": f"{item.source_id}:{stable_suffix}",
        "title": item.title,
        "funder": item.funder,
        "programme": item.programme,
        "status": item.status,
        "territory": _territory(item.source_id),
        "eligibleEntities": list(item.eligible_entities),
        "macroAreas": list(item.macro_areas),
        "summary": _shorten(item.short_description or "Descrizione non esposta dalla lista ufficiale."),
        "relevance": relevance,
        "relevanceWhy": relevance_why,
        "officialUrl": item.official_url,
        "lastVerified": _verified_label(verified_on),
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


def build_snapshot(*, today: date | None = None, now: datetime | None = None) -> dict[str, Any]:
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    opportunities: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    failures: list[str] = []

    for spec in LIVE_SOURCE_SPECS:
        adapter = spec.adapter_factory()
        try:
            raw = adapter.fetch(FetchPolicy(timeout_seconds=25, max_bytes=spec.max_bytes, retries=2))
            records: list[SourceRecord] = adapter.parse(raw)
            normalized = process(spec.source_id, records, today)
            warnings = anomaly_warnings(
                len(normalized), [], [record.title for record in records], [record.deadline for record in records]
            )
            opportunities.extend(public_opportunity(item, today) for item in normalized)
            source_results.append({
                "sourceId": spec.source_id,
                "label": _source_label(adapter, spec.source_id),
                "kind": "live",
                "status": "LIVE",
                "fetchedRecords": len(records),
                "publishedRecords": len(normalized),
                "warnings": warnings,
            })
        except (AdapterError, ValueError, OSError) as exc:
            message = str(exc)
            failures.append(f"{spec.source_id}: {message}")
            source_results.append({
                "sourceId": spec.source_id,
                "label": _source_label(adapter, spec.source_id),
                "kind": "live",
                "status": "ERROR",
                "fetchedRecords": 0,
                "publishedRecords": 0,
                "warnings": [message],
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
                "publishedRecords": 0,
                "warnings": [str(exc)],
            })

    opportunities.sort(key=lambda item: (item.get("status") not in {"OPEN", "UPCOMING"}, item.get("deadline") or "9999-12-31", item["title"].lower()))
    return {
        "schemaVersion": 1,
        "generatedAt": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "asOfDate": today.isoformat(),
        "complete": not failures,
        "recordCount": len(opportunities),
        "liveSourceCount": sum(1 for item in source_results if item["kind"] == "live" and item["status"] == "LIVE"),
        "sourceCount": len(source_results),
        "sources": source_results,
        "warnings": failures,
        "notImplemented": ["Pari Opportunità", "Dipendenze", "FAMI"],
        "opportunities": opportunities,
    }


def write_snapshot(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return target
