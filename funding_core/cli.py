from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    FetchPolicy,
    IncentiviGovAdapter,
    InterregItalyCroatiaAdapter,
    VenetoBandiAdapter,
    VenetoFesrCalendarAdapter,
    VenetoFseCalendarAdapter,
)
from .pipeline import anomaly_warnings, process
from .audit import write_audit_reports
from .operational import assess_anomaly, snapshot_validation_errors, update_daily_sync_deployment_status, write_daily_sync_report
from .snapshot import ALL_SOURCE_IDS, FIXTURE_SOURCE_SPECS, LIVE_SOURCE_SPECS, build_snapshot_set, write_snapshot
from adapters import (
    PariOpportunitaAdapter,
    DipendenzeAdapter,
    FamiAdapter,
    PnScuolaAdapter,
    FondazioneVeneziaAdapter,
    IntesaBeneficenzaAdapter,
    CompagniaSanPaoloAdapter,
    FondazioneCariploAdapter,
    FondazioneConIlSudAdapter,
    FondazioneCrtAdapter,
    FondazioneCrFirenzeAdapter,
    FondazioneCrcAdapter,
    FondazioneSardegnaAdapter,
    FondazioneFriuliAdapter,
    MinisteroLavoroTerzoSettoreAdapter,
    AicsAdapter,
    EuropeanYouthFoundationAdapter,
    ErasmusInappAdapter,
    FondazioneCariparmaAdapter,
    FondazioneModenaAdapter,
    FondazioneCarisboAdapter,
    MinisteroSaluteRicercaFinalizzataAdapter,
    MurPrinAdapter,
    InailBricAdapter,
    FondazioneDelMonteAdapter,
    FondazioneCrLuccaAdapter,
    FondazioneCarispeziaAdapter,
    FondazioneMpsAdapter,
)


ADAPTERS = {
    "eu-funding-tenders": EuFundingTendersAdapter,
    "incentivi-gov": IncentiviGovAdapter,
    "erasmus-indire": ErasmusIndireAdapter,
    "aig-opportunities": AigOpportunitiesAdapter,
    "interreg-italy-croatia": InterregItalyCroatiaAdapter,
    "veneto-bandi": VenetoBandiAdapter,
    "dipartimento-famiglia": DipartimentoFamigliaAdapter,
    "dipartimento-disabilita": DipartimentoDisabilitaAdapter,
    "fondazione-cariparo": FondazioneCariparoAdapter,
    "fondazione-cariverona": FondazioneCariveronaAdapter,
    "con-i-bambini": ConIBambiniAdapter,
    "fondo-repubblica-digitale": FondoRepubblicaDigitaleAdapter,
    "veneto-fse-calendar": VenetoFseCalendarAdapter,
    "veneto-fesr-calendar": VenetoFesrCalendarAdapter,
    "pari_opportunita": PariOpportunitaAdapter,
    "dipendenze": DipendenzeAdapter,
    "fami": FamiAdapter,
    "pn_scuola": PnScuolaAdapter,
    "fondazione_venezia": FondazioneVeneziaAdapter,
    "intesa_beneficenza": IntesaBeneficenzaAdapter,
    "compagnia_san_paolo": CompagniaSanPaoloAdapter,
    "fondazione_cariplo": FondazioneCariploAdapter,
    "fondazione_con_il_sud": FondazioneConIlSudAdapter,
    "fondazione_crt": FondazioneCrtAdapter,
    "fondazione_cr_firenze": FondazioneCrFirenzeAdapter,
    "fondazione_crc": FondazioneCrcAdapter,
    "fondazione_sardegna": FondazioneSardegnaAdapter,
    "fondazione_friuli": FondazioneFriuliAdapter,
    "ministero_lavoro_terzo_settore": MinisteroLavoroTerzoSettoreAdapter,
    "aics": AicsAdapter,
    "european_youth_foundation": EuropeanYouthFoundationAdapter,
    "erasmus_inapp": ErasmusInappAdapter,
    "fondazione_cariparma": FondazioneCariparmaAdapter,
    "fondazione_modena": FondazioneModenaAdapter,
    "fondazione_carisbo": FondazioneCarisboAdapter,
    "ministero_salute_ricerca_finalizzata": MinisteroSaluteRicercaFinalizzataAdapter,
    "mur_prin": MurPrinAdapter,
    "inail_bric": InailBricAdapter,
    "fondazione_del_monte": FondazioneDelMonteAdapter,
    "fondazione_cr_lucca": FondazioneCrLuccaAdapter,
    "fondazione_carispezia": FondazioneCarispeziaAdapter,
    "fondazione_mps": FondazioneMpsAdapter,
}

FIXTURE_PATHS = {source_id: fixture_name for source_id, _, fixture_name in FIXTURE_SOURCE_SPECS}


def _read_previous(path_value: str | None) -> dict | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", default="public/data/opportunities-current.json")
    parser.add_argument("--archive-output", default="public/data/opportunities-archive.json")
    parser.add_argument("--previous")
    parser.add_argument("--previous-archive")
    parser.add_argument("--audit-dir", default="reports")
    parser.add_argument("--daily-report", default="reports/daily-sync-latest.json")


def _run_snapshot_sync(args: argparse.Namespace) -> int:
    started_at = datetime.now(timezone.utc)
    previous_path = args.previous or args.output
    previous_archive_path = args.previous_archive or args.archive_output
    previous_current = _read_previous(previous_path)
    previous_archive = _read_previous(previous_archive_path)
    snapshots = build_snapshot_set(previous_current=previous_current, previous_archive=previous_archive)
    current = snapshots["current"]
    archive = snapshots["archive"]
    validation_errors = [
        *snapshot_validation_errors(current, expected_dataset="current"),
        *snapshot_validation_errors(archive, expected_dataset="archive"),
    ]
    anomaly = assess_anomaly(current, previous_current)
    if not current.get("recordCount"):
        validation_errors.append("current snapshot contains no opportunities")
    completed_at = datetime.now(timezone.utc)
    if validation_errors or anomaly["status"] == "BLOCKED":
        report = write_daily_sync_report(
            args.daily_report,
            started_at=started_at,
            completed_at=completed_at,
            snapshot_generated_at=current.get("generatedAt"),
            source_results=current.get("sources", []),
            current_records=current.get("recordCount", 0),
            archive_records=archive.get("recordCount", 0),
            anomaly={**anomaly, "status": "BLOCKED" if anomaly["status"] == "BLOCKED" else "INVALID", "validationErrors": validation_errors},
            snapshot_valid=False,
            deployment_status="NOT_ATTEMPTED",
        )
        print(f"Daily sync FAILED; last known good snapshot preserved. Report: {report}", file=sys.stderr)
        for error in [*validation_errors, *anomaly.get("reasons", [])]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    target = write_snapshot(args.output, current)
    archive_target = write_snapshot(args.archive_output, archive)
    # Keep the original route as a compatibility alias for old deployments.
    if Path(args.output).name != "opportunities.json":
        write_snapshot(Path(args.output).with_name("opportunities.json"), current)
    reports = write_audit_reports(current, archive, args.audit_dir)
    report = write_daily_sync_report(
        args.daily_report,
        started_at=started_at,
        completed_at=completed_at,
        snapshot_generated_at=current.get("generatedAt"),
        source_results=current.get("sources", []),
        current_records=current.get("recordCount", 0),
        archive_records=archive.get("recordCount", 0),
        anomaly=anomaly,
        snapshot_valid=True,
        deployment_status="NOT_ATTEMPTED",
    )
    health = current.get("sourceHealth", {})
    print(f"Snapshot current: {target}")
    print(f"Snapshot archive: {archive_target}")
    print(f"Published current records: {current['recordCount']}")
    print(f"Archived records: {archive['recordCount']}")
    print(f"Sources LIVE: {health.get('successfulSourceCount', current['liveSourceCount'])}/{health.get('liveConfiguredSourceCount', len(LIVE_SOURCE_SPECS))}")
    print(f"Source health report: {report}")
    print(f"Audit: {reports['highRelevanceCsv']}")
    print(f"v0.3 source report: {reports['sourceReport']}")
    print(f"v0.3.1 final report: {reports['v031FinalReport']}")
    print(f"v0.3.1a final report: {reports['v031aFinalReport']}")
    print(f"v0.4 final report: {reports['v04FinalReport']}")
    print(f"v0.5 final report: {reports['v05FinalReport']}")
    for warning in current["warnings"]:
        print(f"WARNING: {warning}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostica gli adapter Funding Intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-source")
    validate.add_argument("source", choices=ALL_SOURCE_IDS)
    sync = subparsers.add_parser("sync")
    sync.add_argument("source", choices=ALL_SOURCE_IDS)
    populate = subparsers.add_parser("populate-snapshot")
    _snapshot_arguments(populate)
    daily = subparsers.add_parser("daily-sync", help="Esegue la stessa sync di produzione usata dal job giornaliero")
    _snapshot_arguments(daily)
    validate_snapshot = subparsers.add_parser("validate-snapshot", help="Valida gli snapshot current/archive senza riscriverli")
    validate_snapshot.add_argument("--current", default="public/data/opportunities-current.json")
    validate_snapshot.add_argument("--archive", default="public/data/opportunities-archive.json")
    mark_deployment = subparsers.add_parser("mark-deployment", help="Registra l'esito post-build nel report latest")
    mark_deployment.add_argument("--report", default="reports/daily-sync-latest.json")
    mark_deployment.add_argument("--status", choices=("NOT_CONFIGURED", "DEPLOY_TRIGGERED", "DEPLOY_FAILED", "DEPLOY_VERIFIED"), required=True)
    args = parser.parse_args(argv)

    if args.command in {"populate-snapshot", "daily-sync"}:
        return _run_snapshot_sync(args)

    if args.command == "validate-snapshot":
        current = _read_previous(args.current)
        archive = _read_previous(args.archive)
        errors = [
            *snapshot_validation_errors(current, expected_dataset="current"),
            *snapshot_validation_errors(archive, expected_dataset="archive"),
        ]
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(f"Snapshot valid: current={current['recordCount']} archive={archive['recordCount']}")
        return 0

    if args.command == "mark-deployment":
        try:
            target = update_daily_sync_deployment_status(args.report, args.status)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Deployment status recorded: {args.status} ({target})")
        return 0

    adapter = ADAPTERS[args.source]()
    if args.source in FIXTURE_PATHS:
        fixture = Path(__file__).with_name("fixtures") / FIXTURE_PATHS[args.source]
        try:
            raw = fixture.read_bytes()
            records = adapter.parse(raw)
        except (OSError, AdapterError, ValueError) as exc:
            print(f"FIXTURE: ERROR\nItems found: 0\nParsed: 0\nWarnings: {exc}", file=sys.stderr)
            return 1
        print(f"FIXTURE: OK\nItems found: {len(records)}\nParsed: {len(records)}\nCurrent: {sum(1 for item in process(adapter.source_id, records) if item.status != 'CLOSED')}\nTitles: {'OK' if records else 'WARNING'}")
        if args.command == "sync":
            opportunities = process(adapter.source_id, records)
            warnings = anomaly_warnings(len(opportunities), [], [item.title for item in records], [item.deadline for item in records])
            print(f"New: {len(opportunities)}\nUpdated: 0\nUnchanged: 0")
            for warning in warnings:
                print(f"WARNING: {warning}")
        return 0

    try:
        max_bytes = {
            "incentivi-gov": 30_000_000,
            "erasmus-indire": 10_000_000,
            "aig-opportunities": 8_000_000,
            "interreg-italy-croatia": 15_000_000,
            "veneto-bandi": 30_000_000,
            "dipartimento-famiglia": 8_000_000,
            "dipartimento-disabilita": 8_000_000,
            "fondazione-cariparo": 10_000_000,
            "fondazione-cariverona": 10_000_000,
            "con-i-bambini": 10_000_000,
            "fondo-repubblica-digitale": 10_000_000,
            "ministero_lavoro_terzo_settore": 4_000_000,
            "aics": 4_000_000,
            "european_youth_foundation": 4_000_000,
            "erasmus_inapp": 4_000_000,
            "fondazione_cariparma": 6_000_000,
            "fondazione_modena": 6_000_000,
            "fondazione_carisbo": 6_000_000,
            "ministero_salute_ricerca_finalizzata": 8_000_000,
            "mur_prin": 10_000_000,
            "inail_bric": 12_000_000,
            "fondazione_del_monte": 8_000_000,
            "fondazione_cr_lucca": 12_000_000,
            "fondazione_carispezia": 10_000_000,
            "fondazione_mps": 16_000_000,
        }.get(args.source, 25_000_000)
        raw = adapter.fetch(FetchPolicy(timeout_seconds=20, max_bytes=max_bytes))
        records = adapter.parse(raw)
    except AdapterError as exc:
        print(f"HTTP: ERROR\nItems found: 0\nParsed: 0\nWarnings: {exc}", file=sys.stderr)
        return 1
    opportunities = process(adapter.source_id, records)
    warnings = anomaly_warnings(len(opportunities), [], [item.title for item in records], [item.deadline for item in records])
    print(f"HTTP: OK\nItems found: {len(records)}\nParsed: {len(records)}\nCurrent: {sum(1 for item in opportunities if item.status != 'CLOSED')}\nTitles: {'OK' if records else 'WARNING'}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if args.command == "sync":
        print(f"New: {len(opportunities)}\nUpdated: 0\nUnchanged: 0")
        for warning in warnings:
            print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
