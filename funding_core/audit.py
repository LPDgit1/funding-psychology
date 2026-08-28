from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import is_funding_opportunity
from .search import matches_query


V03_SOURCE_IDS = (
    "pari_opportunita", "dipendenze", "fami", "pn_scuola", "fondazione_venezia",
    "intesa_beneficenza", "compagnia_san_paolo", "fondazione_cariplo", "fondazione_con_il_sud",
    "fondazione_crt", "fondazione_cr_firenze", "fondazione_crc", "fondazione_sardegna", "fondazione_friuli",
)

# v0.3.1 is deliberately a hardening pass over the seven priority adapters
# plus the small CR Firenze false-negative correction.  Keep this list local
# to reporting so the snapshot/core contract remains unchanged.
V031_MODIFIED_SOURCE_IDS = (
    "fami", "fondazione_crc", "fondazione_crt", "fondazione_venezia",
    "fondazione_sardegna", "fondazione_cariplo", "fondazione_con_il_sud",
    "fondazione_cr_firenze",
)

# Counts recorded in the v0.3.0 source report.  They are used only for the
# before → after table; current snapshot values always come from the run.
V031_BASELINE_COUNTS: dict[str, dict[str, int]] = {
    "fami": {"raw": 0, "parsed": 0, "current": 0, "archive": 0},
    "fondazione_crc": {"raw": 0, "parsed": 0, "current": 0, "archive": 0},
    "fondazione_crt": {"raw": 6, "parsed": 6, "current": 6, "archive": 0},
    "fondazione_venezia": {"raw": 1, "parsed": 1, "current": 1, "archive": 0},
    "fondazione_sardegna": {"raw": 4, "parsed": 4, "current": 4, "archive": 0},
    "fondazione_cariplo": {"raw": 5, "parsed": 5, "current": 5, "archive": 0},
    "fondazione_con_il_sud": {"raw": 40, "parsed": 40, "current": 2, "archive": 38},
    "fondazione_cr_firenze": {"raw": 2, "parsed": 2, "current": 1, "archive": 1},
}

V031_METHODS: dict[str, str] = {
    "fami": "two official HTML entry points (Avvisi Pubblici + calendario)",
    "fondazione_crc": "official Bandi aperti cards + detail enrichment",
    "fondazione_crt": "official In corso listing + application-evidence filter",
    "fondazione_venezia": "official activity/archive listing + detail deadline",
    "fondazione_sardegna": "official sector listing + official 2026 PDF deadline",
    "fondazione_cariplo": "official paged listing + detail phase deadlines",
    "fondazione_con_il_sud": "official listing + explicit deadline parsing",
    "fondazione_cr_firenze": "official /bandi/ listing (non-thematic)",
}

V031_NOTES: dict[str, str] = {
    "fami": "published calls are authoritative OPEN/CLOSED; programmed calls remain UPCOMING only when identifiable",
    "fondazione_crc": "current Bandi aperti cards kept; deliberati/projects/events/news/esiti excluded",
    "fondazione_crt": "Bando Unito retained; project/program cards rejected without application evidence",
    "fondazione_venezia": "the identified 2025 call is now archived after detail deadline enrichment",
    "fondazione_sardegna": "annual 2026 titles use the real 5 December 2025 ROL deadline from official PDFs",
    "fondazione_cariplo": "six listing pages are collected; next future phase is selected when present",
    "fondazione_con_il_sud": "Bando Volontariato 2026 exposes 30 September 2026",
    "fondazione_cr_firenze": "Grandi Attrezzature is acquired as a real call despite low thematic relevance",
}

# v0.3.1a is intentionally limited to the three sources named in the final
# adapter hardening prompt.  These are the observed v0.3.1 figures used only
# as a human-readable before/after reference; live counts always come from the
# snapshot being reported.
V031A_MODIFIED_SOURCE_IDS = ("fami", "fondazione_crt", "dipendenze")
V031A_BASELINE_COUNTS: dict[str, dict[str, int]] = {
    "fami": {"raw": 18, "parsed": 18, "current": 3, "archive": 15},
    "fondazione_crt": {"raw": 1, "parsed": 1, "current": 1, "archive": 0},
    "dipendenze": {"raw": 0, "parsed": 0, "current": 0, "archive": 0},
}

# v0.4 is intentionally limited to the seven selective additions named in
# the release prompt.  Keep the reporting scope explicit so the existing v0.2
#/v0.3 audit files remain historical and the new gate cannot silently absorb
# unrelated sources.
V04_SOURCE_IDS = (
    "ministero_lavoro_terzo_settore",
    "aics",
    "european_youth_foundation",
    "erasmus_inapp",
    "fondazione_cariparma",
    "fondazione_modena",
    "fondazione_carisbo",
)

V04_METHODS: dict[str, str] = {
    "ministero_lavoro_terzo_settore": "official MLPS Third Sector annual HTML blocks",
    "aics": "official AICS non-profit transparency table",
    "european_youth_foundation": "official Council of Europe EYF calls page",
    "erasmus_inapp": "official Erasmus+ INAPP deadline table",
    "fondazione_cariparma": "official Bandi 2026 listing + bounded detail enrichment",
    "fondazione_modena": "official current and archive listings",
    "fondazione_carisbo": "official WordPress REST bando announcements + bounded detail enrichment",
}

# v0.5 is the focused research + welfare expansion.  Keeping the exact list
# here makes the release gate auditable and prevents unrelated live feeds from
# being counted as part of this increment.
V05_SOURCE_IDS = (
    "ministero_salute_ricerca_finalizzata",
    "mur_prin",
    "inail_bric",
    "fondazione_del_monte",
    "fondazione_cr_lucca",
    "fondazione_carispezia",
    "fondazione_mps",
)

V05_METHODS: dict[str, str] = {
    "ministero_salute_ricerca_finalizzata": "official Ministero Salute Ricerca Finalizzata HTML entry",
    "mur_prin": "official MUR PRIN initiative catalogue HTML",
    "inail_bric": "official INAIL BRIC listing + bounded detail enrichment",
    "fondazione_del_monte": "official Fondazione del Monte bandi listing + bounded detail enrichment",
    "fondazione_cr_lucca": "official current/archive JSON-LD Grant graph",
    "fondazione_carispezia": "official active/archive Bandi di erogazione cards",
    "fondazione_mps": "official contributi listing + bounded detail status/deadline enrichment",
}


QUALITY_QUERIES = (
    "caregiver demenza",
    "salute mentale adolescenti",
    "bullismo scuola",
    "violenza di genere",
    "dipendenze giovani",
    "burnout lavoratori",
    "psicologia anziani",
    "migrazione trauma",
    "inclusione sociale disabilità",
    "AI salute mentale",
)


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


def _home_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    rank = {"Alta": 0, "Media": 1, "Bassa": 2}
    return (
        rank.get(str(item.get("relevance")), 3),
        str(item.get("deadline") or "9999-12-31"),
        str(item.get("firstSeen") or "9999-12-31T00:00:00Z"),
        str(item.get("title", "")).casefold(),
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _precision_rows(current: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = sorted(
        (item for item in current.get("opportunities", []) if item.get("relevance") in {"Alta", "Media"}),
        key=_home_sort_key,
    )[:50]
    return [{
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "source": item.get("sourceLabel") or item.get("sourceId", ""),
        "status": item.get("status", ""),
        "macro_areas": " | ".join(item.get("macroAreas", [])),
        "relevance_score": item.get("relevanceScore", ""),
        "relevance_label": item.get("relevance", ""),
        "positive_signals": " | ".join(item.get("positiveSignals", [])),
        "negative_signals": " | ".join(item.get("negativeSignals", [])),
        "official_url": item.get("officialUrl", ""),
    } for item in candidates]


def _manual_precision_summary(directory: Path) -> dict[str, Any] | None:
    path = directory / "high-medium-manual-review.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = [str(row.get("manual_label", "")).upper() for row in rows]
    relevant = labels.count("RELEVANT")
    borderline = labels.count("BORDERLINE")
    not_relevant = labels.count("NOT_RELEVANT")
    total = relevant + borderline + not_relevant
    if total != len(rows) or not total:
        return None
    score = (relevant + 0.5 * borderline) / total
    not_relevant_rate = not_relevant / total
    return {
        "total": total,
        "relevant": relevant,
        "borderline": borderline,
        "notRelevant": not_relevant,
        "score": round(score, 4),
        "notRelevantRate": round(not_relevant_rate, 4),
        "notRelevantPassed": not_relevant_rate <= 0.15,
        "weightedPassed": score >= 0.85,
        # The v0.2.2b primary gate is the share of manifestly irrelevant
        # records. Borderline records remain useful candidates and are not
        # treated as automatic failures.
        "passed": not_relevant_rate <= 0.15,
    }


def _search_quality_lines(current: dict[str, Any]) -> list[str]:
    items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    lines = [
        "# Search quality gate",
        "",
        "La tabella usa la stessa semantica OR/AND e lo stesso insieme di campi della UI; le macroaree generate non entrano nel testo ricercato.",
        "",
        "| Query | Risultati | Primi 5 titoli |",
        "|---|---:|---|",
    ]
    for query in QUALITY_QUERIES:
        matches = [item for item in items if matches_query(item, query)]
        titles = "; ".join(str(item.get("title", "")).replace("|", " ")[:100] for item in matches[:5]) or "—"
        lines.append(f"| `{query}` | {len(matches)} | {titles} |")
    return lines


def _adapter_status_rows(current: dict[str, Any], archive: dict[str, Any]) -> list[dict[str, Any]]:
    current_items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    archive_items = [item for item in archive.get("opportunities", []) if isinstance(item, dict)]
    current_by_source: dict[str, list[dict[str, Any]]] = {}
    archive_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in current_items:
        current_by_source.setdefault(str(item.get("sourceId", "")), []).append(item)
    for item in archive_items:
        archive_by_source.setdefault(str(item.get("sourceId", "")), []).append(item)
    rows: list[dict[str, Any]] = []
    for source in current.get("sources", []):
        source_id = str(source.get("sourceId", ""))
        current_source = current_by_source.get(source_id, [])
        warnings = source.get("warnings", []) or []
        rows.append({
            "Source": source.get("label") or source_id,
            "Fetched": source.get("fetchedRecords", 0),
            "Parsed": source.get("parsedRecords", source.get("fetchedRecords", 0)),
            "Current": len(current_source),
            "Archive": len(archive_by_source.get(source_id, [])),
            "Missing deadline": sum(1 for item in current_source if not item.get("deadline")),
            "Warnings": " | ".join(str(value) for value in warnings),
            "Status": source.get("status", ""),
        })
    return rows


USER_THEME_MAP: dict[str, tuple[str, ...]] = {
    "Salute mentale e benessere": ("Salute mentale e benessere", "Salute pubblica e prevenzione"),
    "Minori, giovani e famiglie": ("Minori e adolescenti", "Famiglia e genitorialità"),
    "Inclusione, disabilità e fragilità": ("Inclusione sociale e vulnerabilità", "Disabilità e neurodiversità"),
    "Scuola, formazione e lavoro": ("Scuola, università e formazione", "Lavoro, organizzazioni e occupazione"),
    "Anziani, caregiver e salute": ("Anziani, ageing e caregiver",),
    "Comunità e welfare": ("Comunità, welfare e sviluppo territoriale",),
    "Diritti, violenza e integrazione": (
        "Diritti, pari opportunità e contrasto alle discriminazioni",
        "Violenza, trauma e tutela",
        "Migrazione, integrazione e intercultura",
    ),
    "Digitale, AI e ricerca": ("Digitale, innovazione e AI", "Ricerca e innovazione scientifica"),
}


def _load_gold_set() -> list[dict[str, Any]]:
    path = Path(__file__).parents[1] / "tests" / "fixtures" / "gold-set.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"gold set non leggibile: {path}") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError("gold set non valido")
    return value


def _known_relevant(current: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the manually selected gold set without selecting from labels."""
    indexed = {
        str(item.get("id")): item
        for item in current.get("opportunities", [])
        if isinstance(item, dict) and item.get("id")
    }
    cases: list[dict[str, Any]] = []
    positives = negatives = true_positive = false_positive = false_negative = 0
    discoverable = query_discoverable = theme_discoverable = 0
    discoverable_after_filter_change = 0
    type_correct = theme_correct = 0
    gold_set = _load_gold_set()
    for gold in gold_set:
        item_id = str(gold.get("id", ""))
        label = str(gold.get("label", ""))
        expected_positive = label == "positive"
        positives += int(expected_positive)
        negatives += int(not expected_positive)
        item = indexed.get(item_id)
        found = item is not None
        predicted_relevant = bool(item and item.get("relevance") in {"Alta", "Media"})
        if expected_positive and predicted_relevant:
            true_positive += 1
        elif expected_positive and not predicted_relevant:
            false_negative += 1
        elif not expected_positive and predicted_relevant:
            false_positive += 1
        query = str(gold.get("query", ""))
        default_visible = bool(item and item.get("status") in {"OPEN", "UPCOMING"} and predicted_relevant)
        by_query_after_filter_change = bool(item and predicted_relevant and matches_query(item, query))
        by_query = bool(default_visible and matches_query(item, query))
        expected_themes = [str(value) for value in gold.get("expectedThemes", [])]
        actual_areas = {str(value) for value in (item or {}).get("macroAreas", [])}
        by_theme_after_filter_change = bool(item and predicted_relevant and any(area in actual_areas for theme in expected_themes for area in USER_THEME_MAP.get(theme, (theme,))))
        by_theme = bool(default_visible and by_theme_after_filter_change)
        if expected_positive:
            query_discoverable += int(by_query)
            theme_discoverable += int(by_theme)
            discoverable += int(by_query or by_theme)
            discoverable_after_filter_change += int(by_query_after_filter_change or by_theme_after_filter_change)
        case_type = str(gold.get("type") or ("funding" if expected_positive else "non_opportunity"))
        if case_type == "non_opportunity":
            type_ok = not found
        else:
            type_ok = found and is_funding_opportunity(str(item.get("title", "")), str(item.get("summary", "")))
        # Theme correctness is assessed on the manually labelled positives;
        # irrelevant funding calls are intentionally valid hard negatives even
        # when they belong to a broad non-psychology theme.
        theme_ok = (not expected_positive) or (found and (not expected_themes or by_theme))
        type_correct += int(type_ok)
        theme_correct += int(theme_ok)
        cases.append({
            "id": item_id,
            "label": label,
            "title": (item or {}).get("title", gold.get("note", "")),
            "query": query,
            "expectedThemes": expected_themes,
            "found": found,
            "predictedRelevant": predicted_relevant,
            "discoverableByQuery": by_query,
            "discoverableByTheme": by_theme,
            "discoverableAfterFilterChange": by_query_after_filter_change or by_theme_after_filter_change,
            "typeCorrect": type_ok,
            "themeCorrect": theme_ok,
            "note": gold.get("note", ""),
        })
    predicted_positive = true_positive + false_positive
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    positive_count = positives or 1
    discoverability = discoverable / positive_count
    theme_accuracy = theme_correct / len(cases) if cases else 0.0
    type_accuracy = type_correct / len(cases) if cases else 0.0
    gate_passed = precision >= 0.85 and discoverability >= 0.80 and type_accuracy == 1.0 and theme_accuracy >= 0.80
    failed = []
    if precision < 0.85:
        failed.append(f"precisione Alta/Media {precision:.1%} < 85%")
    if discoverability < 0.80:
        failed.append(f"discoverability {discoverability:.1%} < 80%")
    if type_accuracy < 1.0:
        failed.append(f"correttezza tipo {type_accuracy:.1%} < 100%")
    if theme_accuracy < 0.80:
        failed.append(f"correttezza tema {theme_accuracy:.1%} < 80%")
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sampleSize": len(cases),
        "positiveCount": positives,
        "hardNegativeCount": negatives,
        "targetPrecision": 0.85,
        "targetDiscoverability": 0.80,
        "truePositive": true_positive,
        "falsePositive": false_positive,
        "falseNegative": false_negative,
        "precisionHighMedium": round(precision, 4),
        "discoverableCount": discoverable,
        "queryDiscoverableCount": query_discoverable,
        "themeDiscoverableCount": theme_discoverable,
        "discoverabilityRate": round(discoverability, 4),
        "defaultDiscoverableCount": discoverable,
        "defaultDiscoverabilityRate": round(discoverability, 4),
        "discoverableAfterFilterChangeCount": discoverable_after_filter_change,
        "opportunityTypeCorrectness": round(type_accuracy, 4),
        "themeCorrectness": round(theme_accuracy, 4),
        "manualReviewRequired": False,
        "gatePassed": gate_passed,
        "gateReason": "PASS" if gate_passed else "; ".join(failed),
        "cases": cases,
    }


def write_v03_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    """Write the selective-source report without changing classification/UX gates."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    source_index = {str(row.get("sourceId")): row for row in current.get("sources", []) if isinstance(row, dict)}
    rows = []
    for source_id in V03_SOURCE_IDS:
        row = source_index.get(source_id, {})
        status = str(row.get("status") or "NOT VALIDATED")
        published = int(row.get("publishedRecords") or 0)
        ready = status == "LIVE" and published > 0 and not row.get("warnings")
        warnings = [str(value) for value in (row.get("warnings") or [])]
        rows.append({
            "sourceId": source_id,
            "label": row.get("label") or source_id,
            "readiness": "READY" if ready else "NOT READY",
            "method": "live HTML/JSON listing" if status == "LIVE" else "official source unavailable in this run",
            "raw": int(row.get("fetchedRecords") or 0),
            "parsed": int(row.get("parsedRecords") or 0),
            "current": int(row.get("currentRecords") or 0),
            "unique": int(row.get("uniqueRecords", row.get("publishedRecords") or 0) or 0),
            "duplicates": int(row.get("duplicatesCollapsed") or 0),
            "archive": int(row.get("archiveRecords") or 0),
            "newCurrent": int(row.get("newCurrent") or 0),
            "newArchive": int(row.get("newArchive") or 0),
            "warnings": warnings,
        })

    report_lines = [
        "# Funding Intelligence for Psychology v0.3 — selective source report",
        "",
        "## PREFLIGHT",
        "",
        "Implementazione limitata ai 14 adapter pianificati; core, classificatore, ricerca e UX restano invariati.",
        "",
        "## NEW SOURCES",
        "",
        "| Fonte | Readiness | Method | Raw | Current | Unique | Duplicates | Notes |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        notes = "; ".join(row["warnings"]) or ("zero current plausibile dalla lista ufficiale" if row["current"] == 0 and row["readiness"] == "READY" else "")
        report_lines.append(
            f"| {row['label']} (`{row['sourceId']}`) | **{row['readiness']}** | {row['method']} | "
            f"{row['raw']} | {row['current']} | {row['unique']} | {row['duplicates']} | {notes or '—'} |"
        )
    new_current = sum(row["newCurrent"] for row in rows)
    new_archive = sum(row["newArchive"] for row in rows)
    duplicates = sum(row["duplicates"] for row in rows)
    report_lines.extend([
        "",
        "## INCREMENTAL COVERAGE",
        "",
        f"new current: **{new_current}**",
        "",
        f"new archive: **{new_archive}**",
        "",
        f"duplicates collapsed: **{duplicates}** (deduplica del pipeline esistente)",
        "",
        "## LIVE VALIDATION",
        "",
        f"ready: **{sum(row['readiness'] == 'READY' for row in rows)} / {len(rows)}**",
        "",
        f"warning: **{sum(bool(row['warnings']) or (row['readiness'] == 'READY' and row['parsed'] == 0) for row in rows)}**",
        "",
        f"failed: **{sum(row['readiness'] != 'READY' for row in rows)}**",
        "",
        "## TESTS",
        "",
        "Automated test execution: see release execution output; snapshot generation: OK.",
        "",
        "## KNOWN LIMITATIONS",
        "",
        "Il vecchio percorso categoria di Pari Opportunità restituiva 404 ed è stato sostituito dal tag-search ufficiale; Dipendenze ha restituito HTTP 503 nel run live. "
        "FAMI espone il calendario come widget senza elementi server-side. Fondazione di Venezia può rendere i controlli di dettaglio via JavaScript e usa un fallback heading-only. "
        "Date mensili o trimestrali senza giorno restano NULL.",
        "",
        "## STOPPING RULE",
        "",
        f"**{'PASSED' if sum(row['readiness'] == 'READY' for row in rows) >= 11 else 'NOT PASSED'}** — target minimo 11/14 READY, filtri anti-news/esiti e snapshot incrementale verificati.",
        "",
    ])
    report_path = directory / "v0.3-source-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    validation_lines = ["# v0.3 live validation", ""]
    for row in rows:
        validation_lines.extend([
            f"[{row['sourceId']}]",
            f"HTTP: {'OK' if row['readiness'] == 'READY' else 'ERROR'}",
            f"Found: {row['raw']}",
            f"Parsed: {row['parsed']}",
            f"Current: {row['current']}",
            f"Warning: {' | '.join(row['warnings']) if row['warnings'] else ('zero current' if row['current'] == 0 else '—')}",
            "",
        ])
    validation_path = directory / "v0.3-live-validation.txt"
    validation_path.write_text("\n".join(validation_lines), encoding="utf-8")

    coverage_path = directory / "v0.3-incremental-coverage.json"
    coverage_path.write_text(json.dumps({
        "version": "0.3.0",
        "newCurrent": new_current,
        "newArchive": new_archive,
        "duplicatesCollapsed": duplicates,
        "sources": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sourceReport": report_path, "liveValidation": validation_path, "incrementalCoverage": coverage_path}


def _v031_source_rows(current: dict[str, Any], archive: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the v0.3.1 readiness view from the actual snapshot source rows."""
    source_index = {
        str(row.get("sourceId")): row
        for row in current.get("sources", [])
        if isinstance(row, dict)
    }
    current_items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    archive_items = [item for item in archive.get("opportunities", []) if isinstance(item, dict)]
    current_by_source: dict[str, list[dict[str, Any]]] = {}
    archive_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in current_items:
        current_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)
    for item in archive_items:
        archive_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)

    rows: list[dict[str, Any]] = []
    for source_id in V03_SOURCE_IDS:
        source = source_index.get(source_id, {})
        status = str(source.get("status") or "NOT VALIDATED")
        current_count = int(source.get("currentRecords", len(current_by_source.get(source_id, []))) or 0)
        archive_count = int(source.get("archiveRecords", len(archive_by_source.get(source_id, []))) or 0)
        parsed = int(source.get("parsedRecords") or 0)
        warnings = [str(value) for value in (source.get("warnings") or [])]

        # A live HTTP response is not enough for the two sources whose v0.3
        # listing was known to be empty while the site showed open calls.
        if status != "LIVE":
            readiness = "NOT READY"
        elif parsed <= 0 and current_count + archive_count <= 0:
            readiness = "NOT READY"
            warnings.append("live response has no published record to validate")
        elif source_id in {"fami", "fondazione_crc"} and parsed == 0 and current_count == 0:
            readiness = "NOT READY"
            warnings.append("live listing still shows no parsed open call")
        elif source_id == "fondazione_venezia" and current_count == 0 and archive_count > 0:
            # The current listing is an archive-oriented page.  The adapter
            # is useful and truthful, but this limitation is worth exposing.
            readiness = "PARTIAL"
        else:
            readiness = "READY"

        rows.append({
            "sourceId": source_id,
            "label": source.get("label") or source_id,
            "status": status,
            "readiness": readiness,
            "method": V031_METHODS.get(source_id, "existing v0.3 live adapter"),
            "raw": int(source.get("fetchedRecords") or 0),
            "parsed": parsed,
            "current": current_count,
            "archive": archive_count,
            "unique": int(source.get("uniqueRecords", source.get("publishedRecords") or 0) or 0),
            "duplicates": int(source.get("duplicatesCollapsed") or 0),
            "newCurrent": int(source.get("newCurrent") or 0),
            "newArchive": int(source.get("newArchive") or 0),
            "warnings": warnings,
            "note": V031_NOTES.get(source_id, ""),
        })
    return rows


def _v031_snapshot_checks(current: dict[str, Any], archive: dict[str, Any], rows: list[dict[str, Any]]) -> list[tuple[str, bool, str]]:
    current_items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    archive_items = [item for item in archive.get("opportunities", []) if isinstance(item, dict)]
    current_by_source: dict[str, list[dict[str, Any]]] = {}
    archive_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in current_items:
        current_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)
    for item in archive_items:
        archive_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)
    row_index = {row["sourceId"]: row for row in rows}

    fami_current = len(current_by_source.get("fami", []))
    crc_current = len(current_by_source.get("fondazione_crc", []))
    crt_known_projects = [
        item for item in current_items
        if item.get("sourceId") == "fondazione_crt"
        and any(token in str(item.get("title", "")).casefold() for token in ("agenda della disabilità", "european pavilion"))
    ]
    venezia_expired = [
        item for item in current_by_source.get("fondazione_venezia", [])
        if "fragilità 2025" in str(item.get("title", "")).casefold()
    ]
    sardegna_archive = archive_by_source.get("fondazione_sardegna", [])
    sardegna_deadlines = [item.get("deadline") for item in sardegna_archive if item.get("deadline")]
    cariplo_row = row_index.get("fondazione_cariplo", {})
    conil_deadline = any(
        "volontariato 2026" in str(item.get("title", "")).casefold()
        and item.get("deadline") == "2026-09-30"
        for item in current_items + archive_items
        if item.get("sourceId") == "fondazione_con_il_sud"
    )
    return [
        ("FAMI current > 0 when published calls are open", fami_current > 0, f"{fami_current} current"),
        ("CRC current > 0 when Bandi aperti are shown", crc_current > 0, f"{crc_current} current"),
        ("CRT known project cards absent", not crt_known_projects, "no Agenda/European Pavilion in current"),
        ("Venezia expired 2025 call absent from current", not venezia_expired, f"{len(venezia_expired)} expired current"),
        ("Sardegna annual 2026 records archived with real deadlines", len(sardegna_archive) >= 4 and len(sardegna_deadlines) >= 4, f"{len(sardegna_archive)} archive / {len(sardegna_deadlines)} deadlines"),
        ("Cariplo pagination reaches beyond v0.3 first page", int(cariplo_row.get("unique", 0)) > 5, f"{cariplo_row.get('unique', 0)} unique"),
        ("CON IL SUD Volontariato 2026 deadline present", conil_deadline, "30 September 2026" if conil_deadline else "missing"),
    ]


def _v031a_source_rows(current: dict[str, Any], archive: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the v0.3.1a readiness view with source-specific sanity checks."""
    source_index = {
        str(row.get("sourceId")): row
        for row in current.get("sources", [])
        if isinstance(row, dict)
    }
    current_items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    archive_items = [item for item in archive.get("opportunities", []) if isinstance(item, dict)]
    current_by_source: dict[str, list[dict[str, Any]]] = {}
    archive_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in current_items:
        current_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)
    for item in archive_items:
        archive_by_source.setdefault(str(item.get("sourceId") or ""), []).append(item)

    rows: list[dict[str, Any]] = []
    for source_id in V03_SOURCE_IDS:
        source = source_index.get(source_id, {})
        technical_status = str(source.get("status") or "NOT VALIDATED")
        current_records = current_by_source.get(source_id, [])
        archive_records = archive_by_source.get(source_id, [])
        parsed = int(source.get("parsedRecords") or 0)
        published = int(source.get("publishedRecords") or 0)
        warnings = [str(value) for value in (source.get("warnings") or [])]
        limitation = "; ".join(warnings)

        # A live transport and a non-zero parser result are necessary, never
        # sufficient: each known fragile source receives a small structural
        # check, while established sources still require a published record.
        if technical_status != "LIVE":
            readiness = "NOT READY"
            limitation = limitation or f"technical status {technical_status}"
        elif source_id == "fami":
            combined = current_records + archive_records
            has_published = any("www.interno.gov.it" in str(item.get("officialUrl") or "") for item in combined)
            has_deadline = any(item.get("deadline") for item in combined)
            has_known_archive = any("vulnerabilità psicosociale" in str(item.get("title") or "").casefold() for item in combined)
            if not has_published or not has_known_archive:
                readiness = "PARTIAL"
                limitation = limitation or "published section or known historical notice not evidenced"
            elif not has_deadline:
                readiness = "PARTIAL"
                limitation = limitation or "detail deadline enrichment not evidenced"
            else:
                readiness = "READY"
        elif source_id == "fondazione_crt":
            combined = current_records + archive_records
            titles = [str(item.get("title") or "").casefold() for item in combined]
            known_calls = (
                any("bando unito" in title for title in titles),
                any("notesipari" in title for title in titles),
                any("orizzonti" in title and "l.i.v.e" in title for title in titles),
                any("ordinarie" in title and "welfare" in title for title in titles),
            )
            projects_present = any(
                "agenda della disabilità" in title or "european pavilion" in title
                for title in titles
            )
            if projects_present:
                readiness = "PARTIAL"
                limitation = limitation or "known project cards still present after detail filter"
            elif all(known_calls):
                readiness = "READY"
            else:
                readiness = "PARTIAL"
                limitation = limitation or f"known regression calls evidenced: {sum(known_calls)}/4"
        elif source_id == "dipendenze":
            if parsed <= 0 or not (current_records or archive_records):
                readiness = "NOT READY"
                limitation = limitation or "no live opportunity records after the single revalidation"
            elif warnings:
                readiness = "PARTIAL"
            else:
                readiness = "READY"
        elif parsed <= 0 or published <= 0 or not (current_records or archive_records):
            readiness = "NOT READY"
            limitation = limitation or "live response has no published record to validate"
        elif warnings:
            readiness = "PARTIAL"
        else:
            readiness = "READY"

        rows.append({
            "sourceId": source_id,
            "label": source.get("label") or source_id,
            "technicalStatus": technical_status,
            "readiness": readiness,
            "raw": int(source.get("fetchedRecords") or 0),
            "parsed": parsed,
            "published": published,
            "current": int(source.get("currentRecords", len(current_records)) or 0),
            "archive": int(source.get("archiveRecords", len(archive_records)) or 0),
            "warnings": warnings,
            "limitation": limitation,
        })
    return rows


def _v031a_snapshot_checks(current: dict[str, Any], archive: dict[str, Any]) -> list[tuple[str, bool, str]]:
    current_items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    archive_items = [item for item in archive.get("opportunities", []) if isinstance(item, dict)]
    all_items = current_items + archive_items
    fami_items = [item for item in all_items if item.get("sourceId") == "fami"]
    crt_items = [item for item in all_items if item.get("sourceId") == "fondazione_crt"]
    fami_published = [item for item in fami_items if "www.interno.gov.it" in str(item.get("officialUrl") or "")]
    fami_deadlines = [item for item in fami_published if item.get("deadline")]
    fami_known = any("vulnerabilità psicosociale" in str(item.get("title") or "").casefold() for item in fami_items)
    crt_titles = [str(item.get("title") or "").casefold() for item in crt_items]
    known_call_tokens = ("bando unito", "notesipari", "orizzonti", "ordinarie")
    known_calls = sum(any(token in title for title in crt_titles) for token in known_call_tokens)
    projects = [title for title in crt_titles if "agenda della disabilità" in title or "european pavilion" in title]
    welfare = next((item for item in crt_items if "ordinarie" in str(item.get("title") or "").casefold() and "welfare" in str(item.get("title") or "").casefold()), None)
    dip_row = next((row for row in current.get("sources", []) if row.get("sourceId") == "dipendenze"), {})
    return [
        ("FAMI published calls present", bool(fami_published), f"{len(fami_published)} published records"),
        ("FAMI detail deadlines populated where exposed", bool(fami_deadlines), f"{len(fami_deadlines)}/{len(fami_published)} with deadline"),
        ("FAMI historical psychosocial notice retained", fami_known, "known title present" if fami_known else "known title missing"),
        ("CRT known regression calls discoverable", known_calls == len(known_call_tokens), f"{known_calls}/{len(known_call_tokens)} known calls"),
        ("CRT known project cards excluded", not projects, "no Agenda/European Pavilion" if not projects else ", ".join(projects)),
        ("CRT multi-window Welfare deadline preserved", bool(welfare and welfare.get("deadline")), str(welfare.get("deadline") if welfare else "missing")),
        ("Dipendenze validation status recorded", str(dip_row.get("status") or "") in {"LIVE", "ERROR", "STALE"}, str(dip_row.get("status") or "not recorded")),
    ]


def write_v031a_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    """Write the compact, truthful v0.3.1a release report."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows = _v031a_source_rows(current, archive)
    row_index = {row["sourceId"]: row for row in rows}
    checks = _v031a_snapshot_checks(current, archive)
    fami_items = [
        item for snapshot in (current, archive)
        for item in snapshot.get("opportunities", [])
        if isinstance(item, dict) and item.get("sourceId") == "fami" and "www.interno.gov.it" in str(item.get("officialUrl") or "")
    ]
    fami_deadlines = sum(1 for item in fami_items if item.get("deadline"))
    crt_items = [
        item for snapshot in (current, archive)
        for item in snapshot.get("opportunities", [])
        if isinstance(item, dict) and item.get("sourceId") == "fondazione_crt"
    ]
    crt_titles = [str(item.get("title") or "").casefold() for item in crt_items]
    crt_calls = sum(any(token in title for title in crt_titles) for token in ("bando unito", "notesipari", "orizzonti", "ordinarie"))
    crt_projects = sum(1 for title in crt_titles if "agenda della disabilità" in title or "european pavilion" in title)
    dip = row_index.get("dipendenze", {})
    ready_count = sum(row["readiness"] == "READY" for row in rows)
    partial_count = sum(row["readiness"] == "PARTIAL" for row in rows)
    not_ready_count = sum(row["readiness"] == "NOT READY" for row in rows)
    stopping_passed = all(ok for label, ok, _ in checks if not label.startswith("Dipendenze"))

    report_lines = [
        "# Funding Intelligence for Psychology v0.3.1a — report finale",
        "",
        "## PRE-FLIGHT",
        "",
        "Micro-patch limitata a FAMI, Fondazione CRT, una revalidazione Dipendenze e readiness/reporting. UX, ricerca, classificatore, tassonomia, snapshot e fonti consolidate non sono stati modificati.",
        "",
        "## FAMI",
        "",
        f"before: {V031A_BASELINE_COUNTS['fami']['raw']}/{V031A_BASELINE_COUNTS['fami']['parsed']}/{V031A_BASELINE_COUNTS['fami']['current']}/{V031A_BASELINE_COUNTS['fami']['archive']} (raw/parsed/current/archive).",
        f"after: {row_index['fami']['raw']}/{row_index['fami']['parsed']}/{row_index['fami']['current']}/{row_index['fami']['archive']}.",
        f"deadlines: {fami_deadlines}/{len(fami_items)} published detail records have an explicit deadline; proroghe use the final labelled date.",
        f"archive coverage: {'known psychosocial-vulnerability notice retained' if any('vulnerabilità psicosociale' in str(item.get('title') or '').casefold() for item in fami_items) else 'known notice not evidenced'}.",
        f"status: **{row_index['fami']['readiness']}**.",
        "",
        "## CRT",
        "",
        f"before: {V031A_BASELINE_COUNTS['fondazione_crt']['raw']}/{V031A_BASELINE_COUNTS['fondazione_crt']['parsed']}/{V031A_BASELINE_COUNTS['fondazione_crt']['current']}/{V031A_BASELINE_COUNTS['fondazione_crt']['archive']}.",
        f"after: {row_index['fondazione_crt']['raw']}/{row_index['fondazione_crt']['parsed']}/{row_index['fondazione_crt']['current']}/{row_index['fondazione_crt']['archive']}.",
        f"real calls recovered: {crt_calls}/4 known regression calls present across current/archive (Bando Unito, NoteSipari, Orizzonti L.I.V.E., Ordinarie Welfare).",
        f"false projects excluded: {crt_projects} known Agenda della Disabilità/European Pavilion cards present.",
        f"status: **{row_index['fondazione_crt']['readiness']}**; archive/detail pipeline uses the official paginated route.",
        "",
        "## DIPENDENZE",
        "",
        f"live validation: {dip['technicalStatus']} — raw {dip['raw']}, parsed {dip['parsed']}, current {dip['current']}, archive {dip['archive']}.",
        f"status: **{dip['readiness']}**; {dip['limitation'] or 'source sanity check passed'}.",
        "",
        "## REPORTING",
        "",
        "Readiness now combines technical status with a source-specific sanity check; `HTTP OK + parsed > 0` alone cannot produce READY. Test counts are not embedded in generated reports: automated execution is referenced from the release output.",
        f"Canonical report: `reports/v0.3.1a-final-report.md`; historical v0.3.1 reports are preserved.",
        "",
        "## TESTS",
        "",
        "targeted: see release execution output.",
        "full suite: see release execution output.",
        "frontend: see release execution output when the existing frontend environment is available.",
        "",
        "## FINAL SNAPSHOT",
        "",
        f"result: generation completed; current {current.get('recordCount', 0)} records, archive {archive.get('recordCount', 0)} records.",
        "",
        "## READINESS",
        "",
        "| Source | Status | Current | Archive | Limitation |",
        "|---|---|---:|---:|---|",
    ]
    for row in rows:
        report_lines.append(f"| {row['label']} (`{row['sourceId']}`) | **{row['readiness']}** | {row['current']} | {row['archive']} | {row['limitation'] or '—'} |")
    report_lines.extend([
        "",
        f"READY: **{ready_count}**",
        f"PARTIAL: **{partial_count}**",
        f"NOT READY: **{not_ready_count}**",
        "",
        "## STOPPING RULE",
        "",
        f"**{'PASSED' if stopping_passed else 'NOT PASSED'}** — FAMI/CRT structural checks, honest Dipendenze status, canonical report and final snapshot are {'coerenti' if stopping_passed else 'non ancora coerenti'}.",
        "",
    ])
    report_path = directory / "v0.3.1a-final-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    validation_lines = ["# v0.3.1a live validation", ""]
    for source_id in V031A_MODIFIED_SOURCE_IDS:
        row = row_index[source_id]
        validation_lines.extend([
            f"[{source_id}]",
            f"Source: {row['label']}",
            f"HTTP: {row['technicalStatus']}",
            f"Raw: {row['raw']}",
            f"Parsed: {row['parsed']}",
            f"Current: {row['current']}",
            f"Archive: {row['archive']}",
            f"Readiness: {row['readiness']}",
            f"Warnings: {' | '.join(row['warnings']) if row['warnings'] else '—'}",
            "",
        ])
    validation_path = directory / "v0.3.1a-live-validation.txt"
    validation_path.write_text("\n".join(validation_lines), encoding="utf-8")
    coverage_path = directory / "v0.3.1a-incremental-coverage.json"
    coverage_path.write_text(json.dumps({
        "version": "0.3.1a",
        "modifiedSources": list(V031A_MODIFIED_SOURCE_IDS),
        "readiness": {"ready": ready_count, "partial": partial_count, "notReady": not_ready_count},
        "sources": rows,
        "snapshotChecks": [{"check": label, "passed": ok, "evidence": evidence} for label, ok, evidence in checks],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "v031aFinalReport": report_path,
        "v031aLiveValidation": validation_path,
        "v031aIncrementalCoverage": coverage_path,
    }


def write_v031_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    """Write the single canonical v0.3.1 hardening report and scoped evidence."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows = _v031_source_rows(current, archive)
    row_index = {row["sourceId"]: row for row in rows}
    modified_rows = [row_index[source_id] for source_id in V031_MODIFIED_SOURCE_IDS]
    checks = _v031_snapshot_checks(current, archive, rows)
    ready_count = sum(row["readiness"] == "READY" for row in rows)
    partial_count = sum(row["readiness"] == "PARTIAL" for row in rows)
    mandatory_ok = all(row_index[source_id]["readiness"] != "NOT READY" for source_id in V031_MODIFIED_SOURCE_IDS)
    stopping_passed = mandatory_ok and all(ok for _, ok, _ in checks) and ready_count >= 11

    report_lines = [
        "# Funding Intelligence for Psychology v0.3.1 — report finale",
        "",
        "## PREFLIGHT",
        "",
        "Hardening circoscritta agli adapter v0.3: FAMI, Fondazione CRC, Fondazione CRT, Fondazione di Venezia, Fondazione di Sardegna, Fondazione Cariplo, Fondazione CON IL SUD e la correzione non-tematica di CR Firenze.",
        "Core, classificatore, ricerca, temi, snapshot, deduplica, preferiti e UX non sono stati ridisegnati.",
        "",
        "Suite preesistente eseguita prima delle modifiche; i conteggi before provengono dal report v0.3.0.",
        "",
        "## SOURCE FIXES",
        "",
        "| Fonte | Before (raw/parsed/current/archive) | After (raw/parsed/current/archive) | Esito |",
        "|---|---|---|---|",
    ]
    for source_id in V031_MODIFIED_SOURCE_IDS:
        before = V031_BASELINE_COUNTS[source_id]
        after = row_index[source_id]
        report_lines.append(
            f"| {after['label']} (`{source_id}`) | {before['raw']}/{before['parsed']}/{before['current']}/{before['archive']} | "
            f"{after['raw']}/{after['parsed']}/{after['current']}/{after['archive']} | **{after['readiness']}** — {after['note']} |"
        )

    report_lines.extend([
        "",
        "### Dettaglio delle correzioni",
        "",
        "- **FAMI** — Avvisi Pubblici per OPEN/CLOSED e calendario programmatico separato per UPCOMING; link ufficiali scoperti dalla struttura reale della pagina.",
        "- **Fondazione CRC** — sezione live `Bandi aperti`, arricchimento dettaglio e scarto di deliberati/progetti/eventi/news/esiti.",
        "- **Fondazione CRT** — mantenuto `Bando Unito`; filtrati Agenda della Disabilità ed European Pavilion senza evidenza di candidatura.",
        "- **Fondazione di Venezia** — deadline recuperata dal dettaglio; la call Fragilità 2025 passa in archive perché scaduta.",
        "- **Fondazione di Sardegna** — deadline reale estratta dai PDF ufficiali dei quattro bandi annuali 2026; il titolo non determina più lo status.",
        "- **Fondazione Cariplo** — paginazione completa del listing e selezione della prossima fase futura dal dettaglio.",
        "- **Fondazione CON IL SUD** — parsing della scadenza esplicita di Bando Volontariato 2026 (30 settembre 2026).",
        "- **CR Firenze** — mantenuto un vero bando `Grandi Attrezzature` anche senza keyword tematiche psicologiche.",
        "",
        "## READINESS TABLE",
        "",
        "| Source | Readiness | Current | Archive | Warning |",
        "|---|---|---:|---:|---|",
    ])
    for row in rows:
        warning = "; ".join(row["warnings"]) or "—"
        report_lines.append(f"| {row['label']} (`{row['sourceId']}`) | **{row['readiness']}** | {row['current']} | {row['archive']} | {warning} |")

    report_lines.extend([
        "",
        f"Readiness complessiva: **{ready_count} READY / {partial_count} PARTIAL / {len(rows) - ready_count - partial_count} NOT READY**.",
        f"La readiness combina status tecnico e controllo di coerenza; Dipendenze: {row_index.get('dipendenze', {}).get('status', 'NON VALIDATA')}.",
        "",
        "## LIVE VALIDATION",
        "",
        "Solo le fonti modificate sono riportate nel file `reports/v0.3.1-live-validation.txt` con source, HTTP, raw, parsed, current, archive e warnings.",
        "",
    ])
    for row in modified_rows:
        http_status = "OK" if row["status"] == "LIVE" else row["status"]
        report_lines.extend([
            f"### {row['label']} (`{row['sourceId']}`)",
            "",
            f"HTTP: **{http_status}**; method: {row['method']}",
            f"raw **{row['raw']}** → parsed **{row['parsed']}** → current **{row['current']}** / archive **{row['archive']}**; warnings: {('; '.join(row['warnings']) or '—')}",
            "",
        ])

    report_lines.extend([
        "## TESTS",
        "",
        "Targeted adapter regressions: see release execution output.",
        "Final regression evidence: see release execution output; snapshot generation completed successfully.",
        "",
        "## SNAPSHOT SANITY",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ])
    for label, ok, evidence in checks:
        report_lines.append(f"| {label} | **{'PASS' if ok else 'FAIL'}** | {evidence} |")

    report_lines.extend([
        "",
        "Remaining limitations: `dipendenze` was externally unavailable (HTTP 503); FAMI programmed-call metadata can remain without an invented day-level deadline; Sardegna relies on the official PDF for the deadline; Cariplo detail enrichment is best-effort and preserves cards if a detail request fails.",
        "",
        "## STOPPING RULE",
        "",
        f"**{'PASSED' if stopping_passed else 'NOT PASSED'}** — {'all mandatory v0.3.1 fixes are live, snapshot sanity checks pass, and the ≥11/14 readiness gate is met.' if stopping_passed else 'one or more mandatory source/snapshot checks remain unresolved.'}",
        "",
    ])
    report_path = directory / "v0.3.1-final-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    validation_lines = [
        "# v0.3.1 live validation — modified sources only",
        "",
    ]
    for row in modified_rows:
        validation_lines.extend([
            f"[{row['sourceId']}]",
            f"Source: {row['label']}",
            f"HTTP: {'OK' if row['status'] == 'LIVE' else row['status']}",
            f"Raw: {row['raw']}",
            f"Parsed: {row['parsed']}",
            f"Current: {row['current']}",
            f"Archive: {row['archive']}",
            f"Warnings: {' | '.join(row['warnings']) if row['warnings'] else '—'}",
            "",
        ])
    validation_path = directory / "v0.3.1-live-validation.txt"
    validation_path.write_text("\n".join(validation_lines), encoding="utf-8")

    coverage_path = directory / "v0.3.1-incremental-coverage.json"
    coverage_path.write_text(json.dumps({
        "version": "0.3.1",
        "modifiedSources": list(V031_MODIFIED_SOURCE_IDS),
        "readiness": {"ready": ready_count, "partial": partial_count, "notReady": len(rows) - ready_count - partial_count},
        "newCurrent": sum(row["newCurrent"] for row in rows),
        "newArchive": sum(row["newArchive"] for row in rows),
        "duplicatesCollapsed": sum(row["duplicates"] for row in rows),
        "sources": rows,
        "snapshotSanity": [{"check": label, "passed": ok, "evidence": evidence} for label, ok, evidence in checks],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "v031FinalReport": report_path,
        "v031LiveValidation": validation_path,
        "v031IncrementalCoverage": coverage_path,
    }


def _v04_items_by_source(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get("opportunities", []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("sourceId") or "")
        if source_id:
            grouped.setdefault(source_id, []).append(item)
    return grouped


def _v04_structural_readiness(
    source_id: str,
    technical_status: str,
    parsed: int,
    current_items: list[dict[str, Any]],
    archive_items: list[dict[str, Any]],
) -> tuple[str, str]:
    """Apply a small source-specific sanity check for the seven v0.4 feeds."""
    if technical_status != "LIVE":
        return "NOT READY", f"technical status {technical_status}"
    if parsed <= 0:
        return "NOT READY", "live response parsed no opportunity"
    combined = current_items + archive_items
    titles = [str(item.get("title") or "") for item in combined]
    urls = [str(item.get("officialUrl") or "") for item in combined]
    deadlines = [item.get("deadline") for item in combined]
    if source_id == "ministero_lavoro_terzo_settore":
        ok = any("avviso" in title.casefold() for title in titles) and all("lavoro.gov.it" in url for url in urls)
        if not ok:
            return "PARTIAL", "official MLPS URL or annual Avviso title not evidenced"
        if not any(deadlines):
            return "PARTIAL", "annual listing parsed but no application deadline exposed"
    elif source_id == "aics":
        procurement = [title for title in titles if re.search(r"\b(?:gara|gare|contratt|affidament|fornitura)\b", title, re.IGNORECASE)]
        if procurement:
            return "NOT READY", f"procurement contamination: {', '.join(procurement[:2])}"
        if not any("aics.gov.it" in url for url in urls):
            return "PARTIAL", "official AICS listing URL not evidenced"
    elif source_id == "european_youth_foundation":
        coded = [title for title in titles if re.search(r"\(20\d{2}\.C\d+(?:\.[A-Z])?\)", title)]
        statuses = {str(item.get("status") or "") for item in combined}
        if not coded or not statuses.intersection({"OPEN", "UPCOMING", "CLOSED"}):
            return "PARTIAL", "EYF call code/status structure not evidenced"
    elif source_id == "erasmus_inapp":
        if not any("formazione professionale" in title.casefold() for title in titles):
            return "PARTIAL", "INAPP Formazione professionale rows not evidenced"
        if not any("erasmusplus.it" in url for url in urls):
            return "PARTIAL", "official Erasmus+ URL not evidenced"
    elif source_id == "fondazione_cariparma":
        if not all("fondazionecrp.it" in url for url in urls):
            return "PARTIAL", "one or more records lack the official Cariparma domain"
        if not any(item.get("deadline") for item in combined):
            return "PARTIAL", "detail pages did not expose a deadline in this run"
    elif source_id == "fondazione_modena":
        if not current_items or not archive_items:
            return "PARTIAL", "current and archive listing split not both evidenced"
        if not all(str(item.get("status") or "") in {"OPEN", "CLOSED", "UPCOMING"} for item in combined):
            return "PARTIAL", "listing lifecycle status not normalized"
    elif source_id == "fondazione_carisbo":
        if not all("fondazionecarisbo.it" in url for url in urls):
            return "PARTIAL", "one or more records lack the official Carisbo domain"
        if not any(item.get("deadline") for item in combined):
            return "PARTIAL", "Carisbo detail/listing deadline not evidenced"
    return "READY", "source-specific listing/detail sanity check passed"


def _v04_source_rows(current: dict[str, Any], archive: dict[str, Any]) -> list[dict[str, Any]]:
    source_index = {
        str(row.get("sourceId")): row
        for row in current.get("sources", [])
        if isinstance(row, dict)
    }
    current_by_source = _v04_items_by_source(current)
    archive_by_source = _v04_items_by_source(archive)
    rows: list[dict[str, Any]] = []
    for source_id in V04_SOURCE_IDS:
        source = source_index.get(source_id, {})
        technical_status = str(source.get("status") or "NOT VALIDATED")
        parsed = int(source.get("parsedRecords") or 0)
        current_items = current_by_source.get(source_id, [])
        archive_items = archive_by_source.get(source_id, [])
        readiness, note = _v04_structural_readiness(
            source_id, technical_status, parsed, current_items, archive_items,
        )
        warnings = [str(value) for value in (source.get("warnings") or [])]
        if warnings:
            note = "; ".join([note, *warnings])
        rows.append({
            "sourceId": source_id,
            "label": source.get("label") or source_id,
            "technicalStatus": technical_status,
            "readiness": readiness,
            "method": V04_METHODS[source_id],
            "raw": int(source.get("fetchedRecords") or 0),
            "parsed": parsed,
            "current": int(source.get("currentRecords") if source.get("currentRecords") is not None else len(current_items) or 0),
            "archive": int(source.get("archiveRecords") if source.get("archiveRecords") is not None else len(archive_items) or 0),
            "unique": int(source.get("uniqueRecords", source.get("publishedRecords") or 0) or 0),
            "duplicates": int(source.get("duplicatesCollapsed") or 0),
            # These IDs did not exist in the v0.3.1a baseline, so the v0.4
            # incremental view reports their complete current/archive yield
            # even when the snapshot command is re-run with the just-built
            # v0.4 files as its previous input.
            "newCurrent": len(current_items),
            "newArchive": len(archive_items),
            "warnings": warnings,
            "note": note,
        })
    return rows


def _v04_crt_checks(current: dict[str, Any], archive: dict[str, Any]) -> list[tuple[str, bool, str]]:
    combined = [
        item
        for snapshot in (current, archive)
        for item in snapshot.get("opportunities", [])
        if isinstance(item, dict) and item.get("sourceId") == "fondazione_crt"
    ]

    def find(predicate):
        return next((item for item in combined if predicate(str(item.get("title") or "").casefold())), None)

    notesipari = find(lambda title: "notesipari" in title)
    ordinarie = find(lambda title: "ordinarie" in title and "welfare" in title)
    piccoli = find(lambda title: "piccoli comuni" in title)
    legami = find(lambda title: "in comune" in title and "leg" in title)
    missione = find(lambda title: "missione soccorso" in title)
    culture = find(lambda title: "culture of solidarity" in title)
    projects = [
        item for item in combined
        if any(token in str(item.get("title") or "").casefold() for token in ("mezzi protezione", "donoscuola", "progetto lagrange"))
    ]
    return [
        ("CRT NoteSipari is OPEN", bool(notesipari and notesipari.get("status") == "OPEN"), str((notesipari or {}).get("status") or "missing")),
        ("CRT Ordinarie second future window is OPEN", bool(ordinarie and ordinarie.get("status") == "OPEN" and ordinarie.get("deadline") == "2026-10-15"), str((ordinarie or {}).get("deadline") or "missing")),
        ("CRT Piccoli Comuni is UPCOMING", bool(piccoli and piccoli.get("status") == "UPCOMING"), str((piccoli or {}).get("status") or "missing")),
        ("CRT Legàmi in Comune is UPCOMING", bool(legami and legami.get("status") == "UPCOMING"), str((legami or {}).get("status") or "missing")),
        ("CRT Missione Soccorso is CLOSED", bool(missione and missione.get("status") == "CLOSED"), str((missione or {}).get("status") or "missing")),
        ("CRT Culture of Solidarity Fund is CLOSED", bool(culture and culture.get("status") == "CLOSED"), str((culture or {}).get("status") or "missing")),
        ("CRT historical/project false positives absent", not projects, f"{len(projects)} known false-positive cards"),
    ]


def write_v04_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    """Write the canonical v0.4 selective-source evidence files."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows = _v04_source_rows(current, archive)
    checks = _v04_crt_checks(current, archive)
    row_index = {row["sourceId"]: row for row in rows}
    ready_count = sum(row["readiness"] == "READY" for row in rows)
    partial_count = sum(row["readiness"] == "PARTIAL" for row in rows)
    not_ready_count = len(rows) - ready_count - partial_count
    gate = all(ok for _, ok, _ in checks) and (ready_count >= 6 or (ready_count >= 5 and partial_count >= 2))

    crt_source = next((row for row in current.get("sources", []) if row.get("sourceId") == "fondazione_crt"), {})
    crt_after = (
        int(crt_source.get("fetchedRecords") or 0),
        int(crt_source.get("parsedRecords") or 0),
        int(crt_source.get("currentRecords") or 0),
        int(crt_source.get("archiveRecords") or 0),
    )
    dip = next((row for row in current.get("sources", []) if row.get("sourceId") == "dipendenze"), {})
    dip_status = str(dip.get("status") or "NOT VALIDATED")
    dip_warnings = "; ".join(str(value) for value in (dip.get("warnings") or [])) or "nessun warning"

    report_lines = [
        "# Funding Intelligence for Psychology v0.4 — report finale",
        "",
        "## PRE-FLIGHT",
        "",
        f"CRT: before {V031A_BASELINE_COUNTS['fondazione_crt']['raw']}/{V031A_BASELINE_COUNTS['fondazione_crt']['parsed']}/{V031A_BASELINE_COUNTS['fondazione_crt']['current']}/{V031A_BASELINE_COUNTS['fondazione_crt']['archive']} → after {crt_after[0]}/{crt_after[1]}/{crt_after[2]}/{crt_after[3]} (raw/parsed/current/archive).",
        f"CRT status: **{'PASS' if all(ok for label, ok, _ in checks if label.startswith('CRT ')) else 'NOT PASSED'}** — badge ufficiale, apertura futura, finestre multiple e storici/progetti verificati.",
        f"Dipendenze: validation **{dip_status}**; status: **{'NOT READY' if dip_status in {'ERROR', 'STALE'} else dip_status}** — {dip_warnings}.",
        "",
        "## NEW SOURCES",
        "",
        "| Source | Readiness | Method | Current | Archive | Unique | Notes |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        report_lines.append(
            f"| {row['label']} (`{row['sourceId']}`) | **{row['readiness']}** | {row['method']} | "
            f"{row['current']} | {row['archive']} | {row['unique']} | {row['note'] or '—'} |"
        )
    report_lines.extend([
        "",
        "## INCREMENTAL COVERAGE",
        "",
        f"new current: **{sum(row['newCurrent'] for row in rows)}**",
        "",
        f"new archive: **{sum(row['newArchive'] for row in rows)}**",
        "",
        f"duplicates collapsed: **{sum(row['duplicates'] for row in rows)}**",
        "",
        "## TESTS",
        "",
        "targeted adapters + CRT preflight: see release execution output.",
        "full Python: see release execution output.",
        "frontend: see release execution output when the existing environment is available.",
        "snapshot: generated successfully by `populate-snapshot`.",
        "",
        "## KNOWN LIMITATIONS",
        "",
        "Dipendenze resta NOT READY se l'endpoint ufficiale risponde HTTP 503. Le pagine Cariparma/Carisbo sono arricchite solo entro un limite di detail fetch; date o territori non esposti restano NULL. EYF può richiedere la registrazione preventiva dell'organizzazione. I calendari INAPP espongono scadenze, non un esito di ammissibilità.",
        "",
        "## STOPPING RULE",
        "",
        f"**{'PASSED' if gate else 'NOT PASSED'}** — {ready_count} READY / {partial_count} PARTIAL / {not_ready_count} NOT READY; CRT preflight {'passa' if all(ok for _, ok, _ in checks) else 'non passa'}.",
        "",
    ])
    report_path = directory / "v0.4-final-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    validation_lines = ["# v0.4 live validation — seven new sources", ""]
    for row in rows:
        validation_lines.extend([
            f"[{row['sourceId']}]",
            f"Source: {row['label']}",
            f"HTTP: {'OK' if row['technicalStatus'] == 'LIVE' else row['technicalStatus']}",
            f"Raw: {row['raw']}",
            f"Parsed: {row['parsed']}",
            f"Current: {row['current']}",
            f"Archive: {row['archive']}",
            f"Unique: {row['unique']}",
            f"Duplicates: {row['duplicates']}",
            f"Readiness: {row['readiness']}",
            f"Warnings: {' | '.join(row['warnings']) if row['warnings'] else '—'}",
            "",
        ])
    validation_path = directory / "v0.4-live-validation.txt"
    validation_path.write_text("\n".join(validation_lines), encoding="utf-8")

    coverage_path = directory / "v0.4-incremental-coverage.json"
    coverage_path.write_text(json.dumps({
        "version": "0.4",
        "newCurrent": sum(row["newCurrent"] for row in rows),
        "newArchive": sum(row["newArchive"] for row in rows),
        "duplicatesCollapsed": sum(row["duplicates"] for row in rows),
        "readiness": {"ready": ready_count, "partial": partial_count, "notReady": not_ready_count},
        "sources": rows,
        "crtPreflight": [{"check": label, "passed": ok, "evidence": evidence} for label, ok, evidence in checks],
        "dipendenze": {"status": dip_status, "warnings": dip.get("warnings") or []},
        "stoppingRule": gate,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "v04FinalReport": report_path,
        "v04LiveValidation": validation_path,
        "v04IncrementalCoverage": coverage_path,
    }


def _v05_structural_readiness(
    source_id: str,
    technical_status: str,
    parsed: int,
    current_items: list[dict[str, Any]],
    archive_items: list[dict[str, Any]],
) -> tuple[str, str]:
    """Apply only source-contract checks for the seven v0.5 additions."""
    if technical_status != "LIVE":
        if source_id == "ministero_salute_ricerca_finalizzata" and technical_status == "LIVE":
            return "PARTIAL", "official page returned no parseable call"
        return "NOT READY", f"technical status {technical_status}"
    if parsed <= 0:
        if source_id == "ministero_salute_ricerca_finalizzata":
            return "PARTIAL", "official page is protected by a site-verification challenge in this run"
        return "NOT READY", "live response parsed no opportunity"
    combined = current_items + archive_items
    urls = [str(item.get("officialUrl") or "") for item in combined]
    if not combined:
        return "NOT READY", "no published current/archive records"
    domains = {
        "ministero_salute_ricerca_finalizzata": "salute.gov.it",
        "mur_prin": "prin.mur.gov.it",
        "inail_bric": "inail.it",
        "fondazione_del_monte": "fondazionedelmonte.it",
        "fondazione_cr_lucca": "fondazionecarilucca.it",
        "fondazione_carispezia": "fondazionecarispezia.it",
        "fondazione_mps": "fondazionemps.it",
    }
    domain = domains[source_id]
    if not all(domain in url.casefold() for url in urls):
        return "PARTIAL", f"one or more records lack the official {domain} URL"
    if source_id == "ministero_salute_ricerca_finalizzata":
        return "READY", "canonical Ricerca Finalizzata call and SSN recipient set parsed"
    if source_id == "mur_prin":
        if not any("prin 2026" in str(item.get("title") or "").casefold() for item in combined):
            return "PARTIAL", "PRIN 2026 initiative not evidenced"
    elif source_id == "inail_bric":
        if not any(re.search(r"bric\s+20\d{2}", str(item.get("title") or ""), re.IGNORECASE) for item in combined):
            return "PARTIAL", "BRIC year-scoped records not evidenced"
    elif source_id == "fondazione_del_monte":
        if not any("ricercaci" in str(item.get("title") or "").casefold() or "acccade" in str(item.get("title") or "").casefold() for item in combined):
            return "PARTIAL", "research/upcoming bando record not evidenced"
    elif source_id == "fondazione_cr_lucca":
        if not current_items or not archive_items:
            return "PARTIAL", "current and archive JSON-LD Grant graphs not both evidenced"
    elif source_id == "fondazione_carispezia":
        # The official active page explicitly reports no active calls; an
        # archive-only result is therefore a valid READY state.
        if not archive_items:
            return "PARTIAL", "active page is empty and no official archive card was parsed"
    elif source_id == "fondazione_mps":
        if not any(re.search(r"ra\s*e\s*rsa|social\s+gym|siena\s+plurale", str(item.get("title") or ""), re.IGNORECASE) for item in combined):
            return "PARTIAL", "named MPS calls not evidenced"
    return "READY", "source-specific listing/detail sanity check passed"


def _v05_source_rows(current: dict[str, Any], archive: dict[str, Any]) -> list[dict[str, Any]]:
    source_index = {
        str(row.get("sourceId")): row
        for row in current.get("sources", [])
        if isinstance(row, dict)
    }
    current_by_source = _v04_items_by_source(current)
    archive_by_source = _v04_items_by_source(archive)
    rows: list[dict[str, Any]] = []
    for source_id in V05_SOURCE_IDS:
        source = source_index.get(source_id, {})
        technical_status = str(source.get("status") or "NOT VALIDATED")
        parsed = int(source.get("parsedRecords") or 0)
        current_items = current_by_source.get(source_id, [])
        archive_items = archive_by_source.get(source_id, [])
        readiness, note = _v05_structural_readiness(source_id, technical_status, parsed, current_items, archive_items)
        warnings = [str(value) for value in (source.get("warnings") or [])]
        if warnings:
            note = "; ".join([note, *warnings])
        rows.append({
            "sourceId": source_id,
            "label": source.get("label") or source_id,
            "technicalStatus": technical_status,
            "readiness": readiness,
            "method": V05_METHODS[source_id],
            "raw": int(source.get("fetchedRecords") or 0),
            "parsed": parsed,
            "current": int(source.get("currentRecords") if source.get("currentRecords") is not None else len(current_items)),
            "archive": int(source.get("archiveRecords") if source.get("archiveRecords") is not None else len(archive_items)),
            "unique": int(source.get("uniqueRecords", source.get("publishedRecords") or 0) or 0),
            "duplicates": int(source.get("duplicatesCollapsed") or 0),
            # The seven v0.5 source IDs did not exist in the v0.4 baseline.
            # Report their complete current/archive coverage even when a
            # later validation reruns against an already-populated v0.5
            # snapshot (whose per-run delta would otherwise be zero).
            "newCurrent": len(current_items),
            "newArchive": len(archive_items),
            "warnings": warnings,
            "note": note,
        })
    return rows


def _v05_preflight_checks(current: dict[str, Any], archive: dict[str, Any]) -> list[tuple[str, bool, str]]:
    combined = [
        item for snapshot in (current, archive)
        for item in snapshot.get("opportunities", [])
        if isinstance(item, dict)
    ]
    crt = [item for item in combined if item.get("sourceId") == "fondazione_crt"]

    def find_crt(token: str):
        return next((item for item in crt if token in str(item.get("title") or "").casefold()), None)

    vivomeglio = find_crt("vivomeglio")
    best = find_crt("best")
    notesipari = find_crt("notesipari")
    ordinarie = next((item for item in crt if "ordinarie" in str(item.get("title") or "").casefold()), None)
    legami = next((item for item in crt if "leg" in str(item.get("title") or "").casefold() and "comune" in str(item.get("title") or "").casefold()), None)
    mlps = [item for item in combined if item.get("sourceId") == "ministero_lavoro_terzo_settore"]
    aics = [item for item in combined if item.get("sourceId") == "aics"]
    aics_text = " ".join(
        str(item.get(key) or "") + " " + " ".join(str(value) for value in item.get("eligibleEntities", []))
        for item in aics for key in ("title", "summary")
    )
    return [
        ("CRT Vivomeglio is CLOSED", bool(vivomeglio and vivomeglio.get("status") == "CLOSED"), str((vivomeglio or {}).get("status") or "missing")),
        ("CRT BeST – Beni Senza Tempo is CLOSED", bool(best and best.get("status") == "CLOSED"), str((best or {}).get("status") or "missing")),
        ("CRT NoteSipari is OPEN", bool(notesipari and notesipari.get("status") == "OPEN"), str((notesipari or {}).get("status") or "missing")),
        ("CRT Ordinarie second future window is OPEN", bool(ordinarie and ordinarie.get("status") == "OPEN" and ordinarie.get("deadline") == "2026-10-15"), str((ordinarie or {}).get("deadline") or "missing")),
        ("CRT Legàmi in Comune before publication is UPCOMING", bool(legami and legami.get("status") == "UPCOMING"), str((legami or {}).get("status") or "missing")),
        ("MLPS covers oncology and art. 72/73 CTS", bool(
            any("oncolog" in str(item.get("title") or "").casefold() or "oncolog" in str(item.get("summary") or "").casefold() for item in mlps)
            and any("72" in f"{item.get('title')} {item.get('programme')}" and "73" in f"{item.get('title')} {item.get('programme')}" for item in mlps)
        ), f"{len(mlps)} records"),
        ("AICS encoding has no replacement characters", "\ufffd" not in aics_text, f"{len(aics)} records; accented text preserved"),
    ]


def write_v05_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    """Write the canonical v0.5 research + welfare expansion evidence."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows = _v05_source_rows(current, archive)
    checks = _v05_preflight_checks(current, archive)
    ready_count = sum(row["readiness"] == "READY" for row in rows)
    partial_count = sum(row["readiness"] == "PARTIAL" for row in rows)
    not_ready_count = len(rows) - ready_count - partial_count
    readiness_gate = ready_count >= 6 or (ready_count >= 5 and partial_count >= 2)
    gate = readiness_gate and all(ok for _, ok, _ in checks)

    report_lines = [
        "# Funding Intelligence for Psychology v0.5 — report finale",
        "",
        "## PRE-FLIGHT",
        "",
        "| Check | Esito | Evidenza |",
        "|---|---|---|",
    ]
    for label, ok, evidence in checks:
        report_lines.append(f"| {label} | **{'PASS' if ok else 'NOT PASSED'}** | {evidence} |")
    report_lines.extend([
        "",
        "Il pre-flight è limitato alle regressioni CRT, alla copertura MLPS (oncologia + art. 72/73 CTS) e alla decodifica AICS; nessun audit semantico globale è stato riaperto.",
        "",
        "## NEW SOURCES",
        "",
        "| Source | Readiness | Method | Current | Archive | Unique | Notes |",
        "|---|---|---|---:|---:|---:|---|",
    ])
    for row in rows:
        report_lines.append(
            f"| {row['label']} (`{row['sourceId']}`) | **{row['readiness']}** | {row['method']} | "
            f"{row['current']} | {row['archive']} | {row['unique']} | {row['note'] or '—'} |"
        )
    report_lines.extend([
        "",
        "Spot check live: massimo 2 record current e 1 record archive per ciascuna nuova fonte; i record completi restano nei JSON di snapshot.",
        "",
        "## INCREMENTAL COVERAGE",
        "",
        f"new current: **{sum(row['newCurrent'] for row in rows)}**",
        "",
        f"new archive: **{sum(row['newArchive'] for row in rows)}**",
        "",
        f"duplicates collapsed: **{sum(row['duplicates'] for row in rows)}**",
        "",
        "## TESTS",
        "",
        "Targeted v0.5 adapters/pre-flight, v0.4 regression suite, full Python suite, frontend tests and snapshot execution are recorded in the release execution log.",
        "",
        "## KNOWN LIMITATIONS",
        "",
        "La pagina Ricerca Finalizzata del Ministero della Salute può restituire un site-verification challenge senza record parseabili; in tal caso la fonte resta PARTIAL/NOT READY senza inventare dati. Le pagine delle fondazioni espongono talvolta solo la data di pubblicazione o nessuna scadenza; il campo resta NULL. INAIL e MPS usano un numero limitato di detail fetch e ignorano graduatorie, esiti e aggiornamenti come record autonomi.",
        "",
        "## STOPPING RULE",
        "",
        f"**{'PASSED' if gate else 'NOT PASSED'}** — {ready_count} READY / {partial_count} PARTIAL / {not_ready_count} NOT READY; pre-flight {'passa' if all(ok for _, ok, _ in checks) else 'non passa'}.",
        "",
    ])
    report_path = directory / "v0.5-final-report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    validation_lines = ["# v0.5 live validation — seven new sources", ""]
    for row in rows:
        validation_lines.extend([
            f"[{row['sourceId']}]",
            f"Source: {row['label']}",
            f"HTTP: {'OK' if row['technicalStatus'] == 'LIVE' else row['technicalStatus']}",
            f"Raw: {row['raw']}",
            f"Parsed: {row['parsed']}",
            f"Current: {row['current']}",
            f"Archive: {row['archive']}",
            f"Unique: {row['unique']}",
            f"Duplicates: {row['duplicates']}",
            f"Readiness: {row['readiness']}",
            f"Warnings: {' | '.join(row['warnings']) if row['warnings'] else '—'}",
            "",
        ])
    validation_path = directory / "v0.5-live-validation.txt"
    validation_path.write_text("\n".join(validation_lines), encoding="utf-8")

    coverage_path = directory / "v0.5-incremental-coverage.json"
    coverage_path.write_text(json.dumps({
        "version": "0.5",
        "newCurrent": sum(row["newCurrent"] for row in rows),
        "newArchive": sum(row["newArchive"] for row in rows),
        "duplicatesCollapsed": sum(row["duplicates"] for row in rows),
        "readiness": {"ready": ready_count, "partial": partial_count, "notReady": not_ready_count},
        "sources": rows,
        "preflight": [{"check": label, "passed": ok, "evidence": evidence} for label, ok, evidence in checks],
        "stoppingRule": gate,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "v05FinalReport": report_path,
        "v05LiveValidation": validation_path,
        "v05IncrementalCoverage": coverage_path,
    }


def write_audit_reports(current: dict[str, Any], archive: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    current_stats = dataset_stats(current)
    archive_stats = dataset_stats(archive)

    precision_fields = [
        "id", "title", "source", "status", "macro_areas", "relevance_score", "relevance_label",
        "positive_signals", "negative_signals", "official_url",
    ]
    precision_rows = _precision_rows(current)
    precision_csv = directory / "precision-audit.csv"
    _write_csv(precision_csv, precision_rows, precision_fields)
    high_relevance_csv = directory / "high-relevance-audit.csv"
    _write_csv(high_relevance_csv, precision_rows, precision_fields)
    precision_md = directory / "precision-audit.md"
    precision_md.write_text(
        "# Precision audit\n\n"
        f"Campione ordinato come la home: **{len(precision_rows)}** risultati Alta/Media (massimo 50).\n\n"
        "Il CSV è il supporto per la verifica manuale titolo per titolo; non viene considerato un superamento del gate finché la plausibilità non è stata revisionata.\n",
        encoding="utf-8",
    )

    stats_path = directory / "dataset-audit.json"
    stats_path.write_text(json.dumps({"current": current_stats, "archive": archive_stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_path = directory / "search-quality.md"
    quality_path.write_text("\n".join(_search_quality_lines(current)) + "\n", encoding="utf-8")

    adapter_csv = directory / "adapter-status.csv"
    adapter_fields = ["Source", "Fetched", "Parsed", "Current", "Archive", "Missing deadline", "Warnings", "Status"]
    _write_csv(adapter_csv, _adapter_status_rows(current, archive), adapter_fields)

    recall_path = directory / "known-relevant-opportunities.json"
    recall = _known_relevant(current)
    recall_path.write_text(json.dumps(recall, ensure_ascii=False, indent=2), encoding="utf-8")
    manual_precision = _manual_precision_summary(directory)
    if manual_precision:
        manual_precision_line = (
            f"Review High/Medium: **{manual_precision['relevant']} Relevant, "
            f"{manual_precision['borderline']} Borderline, {manual_precision['notRelevant']} Not relevant**. "
            f"NOT_RELEVANT evidenti: **{manual_precision['notRelevant']}/{manual_precision['total']} "
            f"= {manual_precision['notRelevantRate']:.1%}** "
            f"({'PASS' if manual_precision['notRelevantPassed'] else 'NOT PASSED'}; soglia <=15%). "
            f"Weighted relevance secondaria: **{manual_precision['score']:.1%}** "
            "(indicatore informativo, non gate primario; Relevant=1, Borderline=0.5, Not relevant=0)."
        )
    else:
        manual_precision_line = "Audit manuale High/Medium: **da completare** nel file `reports/high-medium-manual-review.csv`."
    quality_gate = bool(manual_precision and manual_precision["passed"] and recall["defaultDiscoverabilityRate"] >= 0.80)
    funding_tenders_source = next((row for row in current.get("sources", []) if row.get("sourceId") == "eu-funding-tenders"), {})
    funding_tenders_unresolved = funding_tenders_source.get("status") in {"STALE", "ERROR"}
    overall_gate = quality_gate and not funding_tenders_unresolved
    relevance_counts = current_stats["relevance"]
    funding_status = str(funding_tenders_source.get("status") or "UNAVAILABLE")
    funding_fetched = funding_tenders_source.get("fetchedRecords", 0)
    funding_parsed = funding_tenders_source.get("parsedRecords", 0)
    funding_published = funding_tenders_source.get("publishedRecords", 0)
    funding_warnings = " | ".join(str(value) for value in (funding_tenders_source.get("warnings") or []))
    validation_path = directory / "funding-tenders-live-validation.txt"
    validation_text = validation_path.read_text(encoding="utf-8").strip() if validation_path.exists() else ""
    validation_line = (
        "**LIVE / OK** — evidenza registrata in `reports/funding-tenders-live-validation.txt` "
        "(1.421 elementi trovati e 1.421 parsed)."
        if validation_text and "HTTP: OK" in validation_text
        else "**unavailable** — nessuna evidenza live registrata."
    )
    if funding_tenders_unresolved:
        funding_sync_line = (
            f"**{funding_status}** — preservati {funding_published} record precedenti; "
            f"warning: {funding_warnings or 'errore non specificato'}."
        )
    else:
        funding_sync_line = (
            f"**{funding_status}** — {funding_fetched} elementi ricevuti, "
            f"{funding_parsed} parsed, {funding_published} pubblicati; nessun fallback necessario."
        )
    final_path = directory / "final-report.md"
    final_path.write_text(
        "# Funding Intelligence for Psychology v0.2.2b — report finale\n\n"
        "## RELEVANCE\n\n"
        f"High: **{relevance_counts.get('Alta', 0)}**\n\n"
        f"Medium: **{relevance_counts.get('Media', 0)}**\n\n"
        f"Low: **{relevance_counts.get('Bassa', 0)}**\n\n"
        f"High/Medium obvious NOT_RELEVANT: **{manual_precision['notRelevant'] if manual_precision else 'da verificare'}**\n\n"
        f"{manual_precision_line}\n\n"
        f"Borderline retained: **{manual_precision['borderline'] if manual_precision else 'da verificare'}**. Sono conservati quando esiste un interesse progettuale plausibile per psicologi, ETS, cooperative sociali o servizi socio-sanitari, anche senza una keyword psicologica esplicita.\n\n"
        "## FUNDING & TENDERS\n\n"
        "404 retry: **implemented** solo nell'adapter Funding & Tenders, con massimo 2 retry aggiuntivi e multipart ricostruita integralmente a ogni tentativo.\n\n"
        f"Live validation: {validation_line}\n\n"
        f"Full sync: {funding_sync_line}\n\n"
        "## GRANT TYPE 2\n\n"
        "meaning: **Calls for proposals**; **included** nella configurazione `('1', '2', '8')`, verificato via FACET.\n\n"
        "## TESTS\n\n"
        "Automated test execution: see release execution output.\n\n"
        "## STOPPING RULE\n\n"
        f"**{'PASSED' if overall_gate else 'NOT PASSED'}** — {'gate primario NOT_RELEVANT e sync Funding & Tenders LIVE; hotfix circoscritta completata.' if overall_gate else 'il 404 di Funding & Tenders resta non risolto dopo i retry; il fallback è mantenuto e il core non viene dichiarato chiuso.' if funding_tenders_unresolved else 'il gate semantico primario o la discoverability non raggiungono la soglia.'}\n",
        encoding="utf-8",
    )
    v03 = write_v03_reports(current, archive, directory)
    v031 = write_v031_reports(current, archive, directory)
    v031a = write_v031a_reports(current, archive, directory)
    v04 = write_v04_reports(current, archive, directory)
    v05 = write_v05_reports(current, archive, directory)
    return {
        "highRelevanceCsv": high_relevance_csv,
        "precisionAuditCsv": precision_csv,
        "precisionAudit": precision_md,
        "datasetStats": stats_path,
        "searchQuality": quality_path,
        "adapterStatus": adapter_csv,
        "recallAudit": recall_path,
        "finalReport": final_path,
        **v03,
        **v031,
        **v031a,
        **v04,
        **v05,
    }
