from __future__ import annotations

import argparse
import json
import sys

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
)
from .pipeline import anomaly_warnings, process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostica gli adapter Funding Intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-source")
    choices = [
        "eu-funding-tenders", "incentivi-gov", "erasmus-indire", "aig-opportunities", "interreg-italy-croatia", "veneto-bandi",
        "dipartimento-famiglia", "dipartimento-disabilita", "fondazione-cariparo", "fondazione-cariverona", "con-i-bambini", "fondo-repubblica-digitale",
    ]
    validate.add_argument("source", choices=choices)
    sync = subparsers.add_parser("sync")
    sync.add_argument("source", choices=choices)
    args = parser.parse_args(argv)
    adapter = {
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
    }[args.source]()
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
