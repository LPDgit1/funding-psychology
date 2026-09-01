"""Small, deterministic operational checks for the daily snapshot path.

The module deliberately stays file based: it provides source-health metadata,
snapshot validation, a simple last-known-good anomaly guard, and the latest
sync report.  It does not introduce a scheduler, database, or service.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SOURCE_STATUSES = frozenset({"LIVE", "STALE", "ERROR", "FIXTURE_ONLY"})


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value.astimezone(timezone.utc)
        return stamp.isoformat().replace("+00:00", "Z")
    return str(value)


def _rows(source_results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in source_results if isinstance(row, dict)]


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def source_health(source_results: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Return the public, non-ambiguous source-health counters.

    ``totalSourceCount`` includes fixture-only registrations.  A source is
    ``successful`` only when it is a live source with status ``LIVE``; fixture
    records are therefore never presented as a live refresh.
    """
    rows = _rows(source_results)
    return {
        "totalSourceCount": len(rows),
        "liveConfiguredSourceCount": sum(1 for row in rows if row.get("kind") == "live"),
        "successfulSourceCount": sum(1 for row in rows if row.get("kind") == "live" and row.get("status") == "LIVE"),
        "staleSourceCount": sum(1 for row in rows if row.get("status") == "STALE"),
        "errorSourceCount": sum(1 for row in rows if row.get("status") == "ERROR"),
        "fixtureOnlySourceCount": sum(1 for row in rows if row.get("status") == "FIXTURE_ONLY" or row.get("kind") == "fixture"),
    }


def snapshot_validation_errors(
    snapshot: dict[str, Any] | None,
    *,
    expected_dataset: str | None = None,
) -> list[str]:
    """Return concise structural/sanity errors for one snapshot envelope."""
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return ["snapshot is not an object"]
    if snapshot.get("schemaVersion") != 2:
        errors.append("schemaVersion must be 2")
    dataset = snapshot.get("dataset")
    if expected_dataset and dataset != expected_dataset:
        errors.append(f"dataset must be {expected_dataset}")
    generated_at = snapshot.get("generatedAt")
    if not isinstance(generated_at, str):
        errors.append("generatedAt is missing")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("generatedAt is not an ISO timestamp")
    opportunities = snapshot.get("opportunities")
    if not isinstance(opportunities, list):
        errors.append("opportunities must be a list")
        opportunities = []
    if snapshot.get("recordCount") != len(opportunities):
        errors.append("recordCount does not match opportunities")
    ids: list[str] = []
    for index, item in enumerate(opportunities):
        if not isinstance(item, dict):
            errors.append(f"opportunities[{index}] is not an object")
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"opportunities[{index}] has no id")
        ids.append(item_id)
        if not str(item.get("officialUrl") or "").startswith("https://"):
            errors.append(f"opportunities[{index}] has a non-HTTPS officialUrl")
    if len(ids) != len(set(ids)):
        errors.append("opportunity ids are not unique")

    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    source_ids: list[str] = []
    for index, row in enumerate(sources):
        if not isinstance(row, dict):
            errors.append(f"sources[{index}] is not an object")
            continue
        source_id = str(row.get("sourceId") or "")
        status = row.get("status")
        kind = row.get("kind")
        if not source_id:
            errors.append(f"sources[{index}] has no sourceId")
        source_ids.append(source_id)
        if status not in SOURCE_STATUSES:
            errors.append(f"sources[{index}] has invalid status")
        if kind not in {"live", "fixture"}:
            errors.append(f"sources[{index}] has invalid kind")
    if len(source_ids) != len(set(source_ids)):
        errors.append("source ids are not unique")
    if snapshot.get("sourceCount") != len(sources):
        errors.append("sourceCount does not match sources")

    expected_health = source_health(sources)
    if snapshot.get("liveSourceCount") != expected_health["successfulSourceCount"]:
        errors.append("liveSourceCount does not match sourceHealth.successfulSourceCount")
    actual_health = snapshot.get("sourceHealth")
    if not isinstance(actual_health, dict):
        errors.append("sourceHealth is missing")
    else:
        for key, value in expected_health.items():
            if actual_health.get(key) != value:
                errors.append(f"sourceHealth.{key} does not match sources")

    if dataset == "current" and any(isinstance(item, dict) and item.get("status") == "CLOSED" for item in opportunities):
        errors.append("current snapshot contains CLOSED opportunities")
    if dataset == "archive" and any(isinstance(item, dict) and item.get("status") != "CLOSED" for item in opportunities):
        errors.append("archive snapshot contains non-CLOSED opportunities")
    return errors


def assess_anomaly(
    candidate_current: dict[str, Any] | None,
    previous_current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply a small global last-known-good guard to a candidate snapshot."""
    candidate_count = _count((candidate_current or {}).get("recordCount"))
    previous_count = _count((previous_current or {}).get("recordCount"))
    candidate_rows = _rows((candidate_current or {}).get("sources", []))
    previous_rows = _rows((previous_current or {}).get("sources", []))
    candidate_health = source_health(candidate_rows)
    previous_health = source_health(previous_rows)
    reasons: list[str] = []

    # A dramatic current-data collapse is not a normal daily fluctuation.
    if previous_count >= 20 and candidate_count < max(5, int(previous_count * 0.20)):
        reasons.append(f"current records collapsed from {previous_count} to {candidate_count}")

    # A majority of live sources failing together is treated as catastrophic,
    # while a single stale/error source remains publishable with fallback data.
    configured = candidate_health["liveConfiguredSourceCount"]
    unavailable = sum(1 for row in candidate_rows if row.get("kind") == "live" and row.get("status") in {"STALE", "ERROR"})
    if configured >= 4 and unavailable >= (configured + 1) // 2:
        reasons.append(f"{unavailable}/{configured} live sources are STALE or ERROR")

    previous_live = previous_health["successfulSourceCount"]
    candidate_live = candidate_health["successfulSourceCount"]
    if previous_live >= 4 and candidate_live < max(1, int(previous_live * 0.50)):
        reasons.append(f"LIVE sources dropped from {previous_live} to {candidate_live}")

    return {
        "status": "BLOCKED" if reasons else "PASS",
        "reasons": reasons,
        "comparedToPrevious": bool(previous_current),
        "previousCurrentRecords": previous_count,
        "candidateCurrentRecords": candidate_count,
    }


def write_daily_sync_report(
    path: str | Path,
    *,
    started_at: datetime | str,
    completed_at: datetime | str,
    snapshot_generated_at: str | None,
    source_results: Iterable[dict[str, Any]],
    current_records: int,
    archive_records: int,
    anomaly: dict[str, Any],
    snapshot_valid: bool,
    deployment_status: str = "NOT_ATTEMPTED",
) -> Path:
    """Write the latest-only CI/manual run report atomically."""
    rows = _rows(source_results)
    health = source_health(rows)
    status_ids: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        status = str(row.get("status") or "ERROR")
        status_ids[status].append(str(row.get("sourceId") or ""))
    payload: dict[str, Any] = {
        "startedAt": _iso(started_at),
        "completedAt": _iso(completed_at),
        "snapshotGeneratedAt": snapshot_generated_at,
        "sourcesAttempted": health["liveConfiguredSourceCount"],
        "LIVE": sorted(status_ids.get("LIVE", [])),
        "STALE": sorted(status_ids.get("STALE", [])),
        "ERROR": sorted(status_ids.get("ERROR", [])),
        "FIXTURE_ONLY": sorted(status_ids.get("FIXTURE_ONLY", [])),
        "sourceCounts": health,
        "currentRecords": int(current_records),
        "archiveRecords": int(archive_records),
        "snapshotValid": bool(snapshot_valid),
        "anomaly": anomaly,
        "syncStatus": "DATA_SYNC_OK" if snapshot_valid and anomaly.get("status") != "BLOCKED" else "DATA_SYNC_FAILED",
        "deploymentStatus": deployment_status,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def update_daily_sync_deployment_status(path: str | Path, status: str) -> Path:
    """Record the post-build/publication outcome without changing sync data."""
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"daily sync report non leggibile: {target}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"daily sync report non valido: {target}")
    payload["deploymentStatus"] = status
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target
