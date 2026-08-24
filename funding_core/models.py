from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SourceRecord:
    external_id: str | None
    title: str
    official_url: str
    funder: str
    programme: str = ""
    opening_date: date | None = None
    deadline: date | None = None
    total_budget: int | None = None
    eligible_entities: tuple[str, ...] = ()
    description: str = ""
    source_status: str = "UNKNOWN"


@dataclass(frozen=True)
class Opportunity:
    source_id: str
    source_external_id: str | None
    title: str
    official_url: str
    funder: str
    programme: str
    opening_date: date | None
    deadline: date | None
    total_budget: int | None
    eligible_entities: tuple[str, ...]
    short_description: str
    status: str
    macro_areas: tuple[str, ...] = field(default_factory=tuple)
    content_hash: str = ""
