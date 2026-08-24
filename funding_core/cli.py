from __future__ import annotations

import argparse
import sys
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
from .snapshot import ALL_SOURCE_IDS, FIXTURE_SOURCE_SPECS, LIVE_SOURCE_SPECS, build_snapshot_set, write_snapshot


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
}

FIXTURE_PATHS = {source_id: fixture_name for source_id, _, fixture_name in FIXTURE_SOURCE_SPECS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostica gli adapter Funding Intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-source")
    validate.add_argument("source", choices=ALL_SOURCE_IDS)
    sync = subparsers.add_parser("sync")
    sync.add_argument("source", choices=ALL_SOURCE_IDS)
    populate = subparsers.add_parser("populate-snapshot")
    populate.add_argument("--output", default="public/data/opportunities-current.json")
    populate.add_argument("--archive-output", default="public/data/opportunities-archive.json")
    populate.add_argument("--previous")
    populate.add_argument("--previous-archive")
    populate.add_argument("--audit-dir", default="reports")
    args = parser.parse_args(argv)

    if args.command == "populate-snapshot":
        def read_previous(path_value: str | None) -> dict | None:
            if not path_value:
                return None
            path = Path(path_value)
            if not path.exists():
                return None
            try:
                import json
                value = json.loads(path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else None
            except (OSError, ValueError):
                return None

        previous_path = args.previous or args.output
        previous_archive_path = args.previous_archive or args.archive_output
        snapshots = build_snapshot_set(
            previous_current=read_previous(previous_path),
            previous_archive=read_previous(previous_archive_path),
        )
        current = snapshots["current"]
        archive = snapshots["archive"]
        target = write_snapshot(args.output, current)
        archive_target = write_snapshot(args.archive_output, archive)
        # Keep the original route as a compatibility alias for old deployments.
        if Path(args.output).name != "opportunities.json":
            write_snapshot(Path(args.output).with_name("opportunities.json"), current)
        reports = write_audit_reports(current, archive, args.audit_dir)
        print(f"Snapshot current: {target}")
        print(f"Snapshot archive: {archive_target}")
        print(f"Published current records: {current['recordCount']}")
        print(f"Archived records: {archive['recordCount']}")
        print(f"Live sources: {current['liveSourceCount']}/{len(LIVE_SOURCE_SPECS)}")
        print(f"Audit: {reports['highRelevanceCsv']}")
        for warning in current["warnings"]:
            print(f"WARNING: {warning}")
        return 0 if current["recordCount"] else 1

    adapter = ADAPTERS[args.source]()
    if args.source in FIXTURE_PATHS:
        fixture = Path(__file__).with_name("fixtures") / FIXTURE_PATHS[args.source]
        try:
            raw = fixture.read_bytes()
            records = adapter.parse(raw)
        except (OSError, AdapterError, ValueError) as exc:
            print(f"FIXTURE: ERROR\nItems found: 0\nParsed: 0\nWarnings: {exc}", file=sys.stderr)
            return 1
        print(f"FIXTURE: OK\nItems found: {len(records)}\nParsed: {len(records)}\nTitles: {'OK' if records else 'WARNING'}")
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
            "veneto-bandi": 5_000_000,
            "dipartimento-famiglia": 8_000_000,
            "dipartimento-disabilita": 8_000_000,
            "fondazione-cariparo": 10_000_000,
            "fondazione-cariverona": 10_000_000,
            "con-i-bambini": 10_000_000,
            "fondo-repubblica-digitale": 10_000_000,
        }.get(args.source, 25_000_000)
        raw = adapter.fetch(FetchPolicy(timeout_seconds=20, max_bytes=max_bytes))
        records = adapter.parse(raw)
    except AdapterError as exc:
        print(f"HTTP: ERROR\nItems found: 0\nParsed: 0\nWarnings: {exc}", file=sys.stderr)
        return 1
    print(f"HTTP: OK\nItems found: {len(records)}\nParsed: {len(records)}\nTitles: {'OK' if records else 'WARNING'}")
    if args.command == "sync":
        opportunities = process(adapter.source_id, records)
        warnings = anomaly_warnings(len(opportunities), [], [item.title for item in records], [item.deadline for item in records])
        print(f"New: {len(opportunities)}\nUpdated: 0\nUnchanged: 0")
        for warning in warnings:
            print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
