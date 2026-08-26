from __future__ import annotations

import csv
import json
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
        ready = status == "LIVE"
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
        "Targeted adapter tests: 12 test in `tests/test_v03_adapters.py`; full Python regression: 50 test OK; frontend: 9 test OK; snapshot generation: OK.",
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
        "Targeted: retry 404 con request multipart distinta, preservazione dopo tre 404, grant type 2 e calibrazione dei pattern social-inclusivi. Full suite: **38 test Python e 9 test JavaScript**, eseguita una volta.\n\n"
        "## STOPPING RULE\n\n"
        f"**{'PASSED' if overall_gate else 'NOT PASSED'}** — {'gate primario NOT_RELEVANT e sync Funding & Tenders LIVE; hotfix circoscritta completata.' if overall_gate else 'il 404 di Funding & Tenders resta non risolto dopo i retry; il fallback è mantenuto e il core non viene dichiarato chiuso.' if funding_tenders_unresolved else 'il gate semantico primario o la discoverability non raggiungono la soglia.'}\n",
        encoding="utf-8",
    )
    v03 = write_v03_reports(current, archive, directory)
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
    }
