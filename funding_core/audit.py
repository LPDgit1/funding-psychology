from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def dataset_stats(snapshot: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in snapshot.get("opportunities", []) if isinstance(item, dict)]
    statuses = Counter(str(item.get("status") or "UNKNOWN") for item in items)
    sources = Counter(str(item.get("sourceId") or "unknown") for item in items)
    relevance = Counter(str(item.get("relevance") or "Bassa") for item in items)
    macro_areas: Counter[str] = Counter()
    for item in items:
        macro_areas.update(str(area) for area in item.get("macroAreas", []) if area)
    return {
        "total": len(items),
        "status": dict(sorted(statuses.items())),
        "sources": dict(sorted(sources.items())),
        "relevance": dict(sorted(relevance.items())),
        "macroAreas": dict(sorted(macro_areas.items())),
        "missingDeadline": sum(1 for item in items if not item.get("deadline")),
        "missingTerritory": sum(1 for item in items if not item.get("territory")),
        "missingOfficialUrl": sum(1 for item in items if not str(item.get("officialUrl") or "").startswith("https://")),
    }


def write_audit_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    current_stats = dataset_stats(current)
    archive_stats = dataset_stats(archive)

    audit_csv = directory / "high-relevance-audit.csv"
    rows: list[dict[str, Any]] = []
    for label, limit in (("Alta", 50), ("Media", 30), ("Bassa", 20)):
        candidates = sorted(
            (item for item in current.get("opportunities", []) if item.get("relevance") == label),
            key=lambda item: (str(item.get("sourceId")), str(item.get("id"))),
        )
        for item in candidates[:limit]:
            rows.append({
                "title": item.get("title", ""),
                "source": item.get("sourceLabel") or item.get("sourceId", ""),
                "status": item.get("status", ""),
                "macro_areas": " | ".join(item.get("macroAreas", [])),
                "relevance_score": item.get("relevanceScore", ""),
                "relevance_label": item.get("relevance", ""),
                "positive_signals": " | ".join(item.get("positiveSignals", [])),
                "negative_signals": " | ".join(item.get("negativeSignals", [])),
                "official_url": item.get("officialUrl", ""),
            })
    with audit_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [
            "title", "source", "status", "macro_areas", "relevance_score", "relevance_label",
            "positive_signals", "negative_signals", "official_url",
        ])
        writer.writeheader()
        writer.writerows(rows)

    stats_path = directory / "dataset-audit.json"
    stats_path.write_text(json.dumps({"current": current_stats, "archive": archive_stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_path = directory / "search-quality.md"
    queries = (
        "salute mentale adolescenti", "caregiver demenza", "inclusione sociale disabilità",
        "bullismo scuola", "violenza di genere", "dipendenze giovani", "burnout lavoratori",
        "psicologia anziani", "migrazione trauma", "intelligenza artificiale salute mentale",
    )
    lines = ["# Search quality gate", "", "Conteggi deterministici sullo snapshot current (non sostituiscono la verifica umana).", ""]
    for query in queries:
        terms = query.casefold().split()
        matches = []
        for item in current.get("opportunities", []):
            haystack = " ".join([
                str(item.get("title", "")), str(item.get("summary", "")),
                " ".join(item.get("macroAreas", [])), " ".join(item.get("eligibleEntities", [])),
            ]).casefold()
            if all(term in haystack for term in terms):
                matches.append(item)
        lines.append(f"- `{query}`: {len(matches)} risultati; primi titoli: " + "; ".join(str(item.get("title", ""))[:90] for item in matches[:3]))
    quality_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"highRelevanceCsv": audit_csv, "datasetStats": stats_path, "searchQuality": quality_path}
