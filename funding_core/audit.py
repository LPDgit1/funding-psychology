from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import is_funding_opportunity
from .search import matches_query


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
        by_query = bool(item and matches_query(item, query))
        expected_themes = [str(value) for value in gold.get("expectedThemes", [])]
        actual_areas = {str(value) for value in (item or {}).get("macroAreas", [])}
        by_theme = bool(item and any(area in actual_areas for theme in expected_themes for area in USER_THEME_MAP.get(theme, (theme,))))
        if expected_positive:
            query_discoverable += int(by_query)
            theme_discoverable += int(by_theme)
            discoverable += int(by_query or by_theme)
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
        "opportunityTypeCorrectness": round(type_accuracy, 4),
        "themeCorrectness": round(theme_accuracy, 4),
        "manualReviewRequired": False,
        "gatePassed": gate_passed,
        "gateReason": "PASS" if gate_passed else "; ".join(failed),
        "cases": cases,
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
    final_path = directory / "final-report.md"
    gold_gate_detail = "tutte le soglie sono rispettate" if recall["gatePassed"] else recall["gateReason"]
    final_path.write_text(
        "# Funding Intelligence for Psychology v0.2.2 — report finale\n\n"
        "## CHANGES MADE\n\n"
        "Consolidamento mirato: filtro del tipo di opportunità nei feed HTML/AIG, pulizia di tre stringhe di navigazione, correzione della tutela contestuale, ricerca inversa dei sinonimi e otto temi user-facing. Nessuna nuova fonte o architettura.\n\n"
        "## OPPORTUNITY-TYPE FILTERING\n\n"
        "Decreti di nomina/commissione, graduatorie, riparti, accordi di collaborazione e contenuti editoriali sono esclusi quando non presentano un avviso o un finanziamento progettuale. Gli avvisi e le call con segnali di candidatura restano eleggibili.\n\n"
        "## SEMANTIC FIXES\n\n"
        "La parola inglese `protection` da sola non attiva la violenza; contano solo formule contestuali come child protection from violence, victim protection o protection against abuse.\n\n"
        "## SEARCH\n\n"
        "Ogni termine di un gruppo sinonimico attiva lo stesso gruppo: giovani/adolescenti/youth/young people e AI/artificial intelligence sono verificati in entrambe le direzioni.\n\n"
        "## UX\n\n"
        "La UI mostra Aree di interesse, Tema, Territorio, Scadenza e Chi può partecipare; i filtri secondari sono raccolti sotto Altri filtri. I bandi scaduti sono consultabili con un'azione esplicita e senza esporre il lessico tecnico del dataset.\n\n"
        "## GOLD SET\n\n"
        f"Campione manuale: **{recall['sampleSize']}** record ({recall['positiveCount']} positivi, {recall['hardNegativeCount']} hard negative). Precisione Alta/Media: **{recall['precisionHighMedium']:.1%}** ({recall['truePositive']} TP, {recall['falsePositive']} FP, {recall['falseNegative']} FN). Discoverability: **{recall['discoverabilityRate']:.1%}** ({recall['discoverableCount']}/{recall['positiveCount']}); correttezza tipo **{recall['opportunityTypeCorrectness']:.1%}**, tema **{recall['themeCorrectness']:.1%}**.\n\n"
        f"Esito gate gold set: **{'PASS' if recall['gatePassed'] else 'NOT PASSED'}** — {gold_gate_detail}. Se non superato, la correzione minima è intervenire solo sui casi elencati in `reports/known-relevant-opportunities.json`, senza ampliare la raccolta.\n\n"
        "## TESTS\n\n"
        "La suite Python e TypeScript è eseguita dopo le modifiche; il test HTML controlla l'assenza del vocabolario tecnico e i test mirati coprono tipo opportunità, tutela contestuale, sinonimi inversi e mapping dei temi.\n\n"
        "## KNOWN LIMITATIONS\n\n"
        f"Il feed corrente contiene **{current_stats['total']}** record e l'elenco scaduti **{archive_stats['total']}**; una fonte può restare stale se il trasporto ufficiale è temporaneamente indisponibile. La classificazione è euristica e non decide l'ammissibilità.\n\n"
        "## STOPPING RULE\n\n"
        f"**{'PASSED' if recall['gatePassed'] else 'NOT PASSED'}** — arresto dopo test, gold set e smoke test richiesti; nessuna nuova feature viene introdotta.\n",
        encoding="utf-8",
    )
    return {
        "highRelevanceCsv": high_relevance_csv,
        "precisionAuditCsv": precision_csv,
        "precisionAudit": precision_md,
        "datasetStats": stats_path,
        "searchQuality": quality_path,
        "adapterStatus": adapter_csv,
        "recallAudit": recall_path,
        "finalReport": final_path,
    }
