from __future__ import annotations

import hashlib
import json
from datetime import date

from .classifier import classify
from .models import Opportunity, SourceRecord


def _status(record: SourceRecord, today: date) -> str:
    if record.deadline and record.deadline < today:
        return "CLOSED"
    if record.opening_date and record.opening_date > today:
        return "UPCOMING"
    if record.deadline:
        return "OPEN"
    return record.source_status if record.source_status in {"OPEN", "UPCOMING", "CLOSED"} else "UNKNOWN"


def normalize(source_id: str, record: SourceRecord, today: date | None = None) -> Opportunity:
    if not record.title.strip():
        raise ValueError("title is required")
    if not record.official_url.startswith("https://"):
        raise ValueError("official_url must use https")
    today = today or date.today()
    semantic = {
        "title": record.title.strip(), "deadline": record.deadline.isoformat() if record.deadline else None,
        "budget": record.total_budget, "entities": record.eligible_entities, "url": record.official_url,
    }
    content_hash = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    text = " ".join((record.title, record.description, record.programme, " ".join(record.eligible_entities)))
    return Opportunity(
        source_id=source_id, source_external_id=record.external_id, title=record.title.strip(),
        official_url=record.official_url, funder=record.funder, programme=record.programme,
        opening_date=record.opening_date, deadline=record.deadline, total_budget=record.total_budget,
        eligible_entities=record.eligible_entities, short_description=record.description.strip(),
        status=_status(record, today), macro_areas=classify(text), content_hash=content_hash,
    )


def dedupe_key(item: Opportunity) -> tuple[str, ...]:
    if item.source_external_id:
        return ("external", item.source_id, item.source_external_id)
    return ("url", item.official_url.rstrip("/").lower())


def process(source_id: str, records: list[SourceRecord], today: date | None = None) -> list[Opportunity]:
    unique: dict[tuple[str, ...], Opportunity] = {}
    for record in records:
        item = normalize(source_id, record, today)
        unique[dedupe_key(item)] = item
    return list(unique.values())


def anomaly_warnings(current_count: int, previous_counts: list[int], titles: list[str], deadlines: list[date | None]) -> list[str]:
    warnings: list[str] = []
    baseline = previous_counts[-1] if previous_counts else 0
    if current_count == 0 and baseline >= 5:
        warnings.append("zero records after a previously populated run")
    if titles and not any(title.strip() for title in titles):
        warnings.append("all titles are empty")
    if deadlines and not any(deadlines):
        warnings.append("all deadlines are missing")
    if baseline >= 10 and current_count < baseline // 2:
        warnings.append("record count dropped by more than half")
    return warnings
