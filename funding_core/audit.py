from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


_RECALL_BUCKETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("salute mentale", "salute mentale", ("salute mentale", "benessere")),
    ("adolescenti", "salute mentale adolescenti", ("minori", "adolescenti")),
    ("caregiver/demenza", "caregiver demenza", ("anziani", "caregiver", "demenza")),
    ("disabilità", "disabilità", ("disabilita", "neurodiversita")),
    ("dipendenze", "dipendenze giovani", ("dipendenze",)),
    ("violenza", "violenza di genere", ("violenza",)),
    ("scuola", "bullismo scuola", ("scuola",)),
    ("inclusione sociale", "inclusione sociale disabilità", ("inclusione sociale",)),
    ("migrazione", "migrazione trauma", ("migrazione", "migranti")),
    ("lavoro/benessere", "burnout lavoratori", ("lavoro", "occupazione", "burnout")),
)


def _known_relevant(current: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in current.get("opportunities", []) if isinstance(item, dict)]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    ordered = sorted(items, key=_home_sort_key)
    for bucket, query, macro_tokens in _RECALL_BUCKETS:
        candidates = []
        for item in ordered:
            item_id = str(item.get("id", ""))
            if item_id in selected_ids:
                continue
            macro_text = " ".join(str(value) for value in item.get("macroAreas", [])).casefold()
            # The known-relevant pool is selected from the classifier's
            # explicit macroarea labels, not from the same query result we are
            # measuring.  This avoids circularly choosing only easy hits.
            if any(token in macro_text for token in macro_tokens):
                candidates.append(item)
        for item in candidates[:3]:
            item_id = str(item.get("id", ""))
            by_query = matches_query(item, query)
            by_macro = any(token in " ".join(str(value) for value in item.get("macroAreas", [])).casefold() for token in macro_tokens)
            selected.append({
                "bucket": bucket,
                "id": item_id,
                "title": item.get("title", ""),
                "query": query,
                "expectedMacroArea": bucket,
                "discoverableByQuery": by_query,
                "discoverableByMacro": by_macro,
            })
            selected_ids.add(item_id)
    query_discoverable = sum(1 for item in selected if item["discoverableByQuery"])
    macro_discoverable = sum(1 for item in selected if item["discoverableByMacro"])
    discoverable = sum(1 for item in selected if item["discoverableByQuery"] or item["discoverableByMacro"])
    sample_size = len(selected)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sampleSize": sample_size,
        "target": 0.80,
        "discoverableCount": discoverable,
        "queryDiscoverableCount": query_discoverable,
        "macroareaDiscoverableCount": macro_discoverable,
        "recallRate": round(discoverable / sample_size, 4) if sample_size else 0.0,
        "manualReviewRequired": True,
        "gatePassed": False,
        "gateReason": "Meccanica per macroarea/query; manca una revisione manuale delle opportunità note.",
        "cases": selected,
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
    final_path.write_text(
        "# Funding Intelligence for Psychology v0.2.1 — report finale\n\n"
        "## PRE-FLIGHT\n\n"
        "Repository e snapshot rigenerati; il report usa i dati del sync corrente e non conteggi statici nella documentazione.\n\n"
        "## P0 FIXES\n\n"
        "- Funding & Tenders: deadline multiple, paginazione e precedenza dello stato ufficiale.\n"
        "- HTML: contenuto principale selezionato prima della classificazione, con esclusione del chrome di navigazione.\n"
        "- Ricerca: sinonimi per concetto, OR interno e AND tra concetti; macroaree escluse dal testo.\n\n"
        "## FUNDING & TENDERS RESULT\n\n"
        "L'adapter conserva OPEN/UPCOMING ufficiali anche quando una deadline storica è presente; i test A/B/C sono nel suite Python.\n\n"
        "## HTML CLEANUP RESULT\n\n"
        "Fixture di dettaglio verificano titolo e contenuto reale senza menu, header, aside o footer.\n\n"
        "## SEARCH FIXES\n\n"
        "Il report `search-quality.md` è calcolato con la stessa semantica del frontend.\n\n"
        "## AIG FILTER RESULT\n\n"
        "Eventi, consultazioni, corsi, focus group e call for participants prive di finanziamento progettuale sono esclusi; avvisi e project/grant call restano eleggibili.\n\n"
        "## REGIONE VENETO RESULT\n\n"
        "L'elenco ufficiale JSON viene paginato senza il limite delle dieci card della homepage.\n\n"
        "## DETAIL PARSER IMPROVEMENTS\n\n"
        "Le date sono cercate vicino a etichette di scadenza/termine/deadline e restano nulle quando il contesto è ambiguo.\n\n"
        "## FILTER FIXES\n\n"
        "Categorie applicant multilabel e regioni multi-regione sono testate; ETS e Veneto non dipendono da una singola etichetta.\n\n"
        "## UX BUG FIXES\n\n"
        "La vista `current|archive` è separata dalla cache dell'archivio e il linguaggio residuo di prototipo è stato rimosso dall'interfaccia.\n\n"
        "## DATASET BEFORE / AFTER\n\n"
        f"- After (sync corrente): **{current_stats['total']}** record operativi, **{archive_stats['total']}** archiviati.\n"
        "- Before: il baseline v0.2 è conservato nella storia Git; il generatore non inserisce un conteggio statico nella documentazione.\n\n"
        "## PRECISION AUDIT\n\n"
        f"sample size: **{len(precision_rows)}** risultati Alta/Media in ordine home (massimo 50).\n\n"
        "result: **NON VERIFICATO** — il CSV è pronto per la revisione manuale titolo per titolo; nessun valore viene auto-promosso a precision pass.\n\n"
        "Failure pattern da controllare: misure amministrative su inclusione/disabilità, giovani o formazione che non finanziano un intervento psicologico diretto.\n\n"
        "## RECALL AUDIT\n\n"
        f"sample size: **{recall['sampleSize']}** opportunità selezionate dalle macroaree note.\n\n"
        f"result: **NON VERIFICATO** — discoverability meccanica query {recall['queryDiscoverableCount']}/{recall['sampleSize']} e macroarea {recall['macroareaDiscoverableCount']}/{recall['sampleSize']}; manca la conferma manuale richiesta dal gate.\n\n"
        "Failure pattern da controllare: termini pertinenti presenti solo nel dettaglio ufficiale o espressi con una combinazione linguistica diversa dalla query naturale.\n\n"
        "## SEARCH QUALITY\n\n"
        "Vedi `search-quality.md` per conteggi e primi cinque titoli delle dieci query obbligatorie.\n\n"
        "## TESTS\n\n"
        "Vedi la suite Python e TypeScript; i comandi di verifica sono nel README.\n\n"
        "## KNOWN LIMITATIONS\n\n"
        "Deadline assenti quando la fonte non identifica il contesto; due calendari Veneto restano fixture-only; la classificazione è euristica e non decide l'ammissibilità.\n\n"
        "## DEFERRED\n\n"
        "Nessuna nuova fonte o feature: FAMI, Pari Opportunità e Dipendenze restano fuori scope.\n\n"
        "## STOPPING RULE STATUS\n\n"
        "**NOT PASSED** — i gate tecnici A–G e i test sono predisposti, ma precisione e recall non sono dichiarabili superati senza revisione manuale verificata.\n",
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
