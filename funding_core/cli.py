from __future__ import annotations

import argparse
import json
import sys

from .adapters import AdapterError, EuFundingTendersAdapter, FetchPolicy, IncentiviGovAdapter
from .pipeline import anomaly_warnings, process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostica gli adapter Funding Intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-source")
    validate.add_argument("source", choices=["eu-funding-tenders", "incentivi-gov"])
    sync = subparsers.add_parser("sync")
    sync.add_argument("source", choices=["eu-funding-tenders", "incentivi-gov"])
    args = parser.parse_args(argv)
    adapter = {
        "eu-funding-tenders": EuFundingTendersAdapter,
        "incentivi-gov": IncentiviGovAdapter,
    }[args.source]()
    try:
        max_bytes = 30_000_000 if args.source == "incentivi-gov" else 25_000_000
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
