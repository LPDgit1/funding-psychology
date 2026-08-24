from datetime import date
import json
from pathlib import Path
import unittest

from funding_core.adapters import (
    IncentiviGovAdapter,
    EuFundingTendersAdapter,
    VenetoFesrCalendarAdapter,
    VenetoFseCalendarAdapter,
)
from funding_core.classifier import classify
from funding_core.pipeline import anomaly_warnings, process


class FundingCoreTests(unittest.TestCase):
    def test_multilabel_school_case(self):
        areas = classify("supporto psicologico scolastico per adolescenti e prevenzione del disagio")
        self.assertIn("Minori e adolescenti", areas)
        self.assertIn("Scuola, università e formazione", areas)
        self.assertIn("Salute mentale e benessere", areas)

    def test_multilabel_disability_work_case(self):
        areas = classify("inclusione lavorativa e occupazione per persone con disabilità vulnerabili")
        self.assertIn("Disabilità e neurodiversità", areas)
        self.assertIn("Inclusione sociale e vulnerabilità", areas)
        self.assertIn("Lavoro, organizzazioni e occupazione", areas)

    def test_multilabel_violence_case(self):
        areas = classify("contrasto alla violenza di genere, tutela, trauma e benessere")
        self.assertIn("Violenza, trauma e tutela", areas)
        self.assertIn("Diritti, pari opportunità e contrasto alle discriminazioni", areas)
        self.assertIn("Salute mentale e benessere", areas)

    def test_fixture_parse_and_idempotent_dedupe(self):
        raw = (Path(__file__).parents[1] / "funding_core" / "fixtures" / "veneto_fse_calendar.csv").read_bytes()
        parsed = VenetoFseCalendarAdapter().parse(raw)
        first = process("veneto-fse-calendar", parsed, date(2026, 8, 24))
        second = process("veneto-fse-calendar", parsed, date(2026, 8, 24))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertEqual(first[0].status, "UPCOMING")
        self.assertEqual(first[0].total_budget, 1_500_000)

    def test_anomaly_protection(self):
        warnings = anomaly_warnings(0, [18], [], [])
        self.assertIn("zero records after a previously populated run", warnings)
        self.assertIn("record count dropped by more than half", warnings)

    def test_eu_fixture_parse_and_missing_fields(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "eu_funding_tenders.json"
        records = EuFundingTendersAdapter().parse(path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].external_id, "FIXTURE-PSY-2026")
        self.assertEqual(records[0].source_status, "UPCOMING")
        self.assertEqual(records[0].opening_date, date(2026, 10, 1))
        self.assertEqual(records[0].deadline, date(2027, 2, 18))
        self.assertEqual(records[0].total_budget, 1_500_000)
        self.assertEqual(records[1].deadline, None)
        self.assertTrue(records[1].official_url.startswith("https://"))

    def test_eu_query_contract(self):
        query = EuFundingTendersAdapter().build_query()
        encoded = json.dumps(query)
        self.assertIn("programmePeriod", encoded)
        self.assertIn("31094502", encoded)
        self.assertIn("2021 - 2027", encoded)

    def test_incentivi_fixture_parse_and_contract(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "incentivi_gov.json"
        adapter = IncentiviGovAdapter()
        records = adapter.parse(path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].external_id, "FIXTURE-1423")
        self.assertEqual(records[0].opening_date, date(2026, 9, 8))
        self.assertEqual(records[0].deadline, date(2026, 12, 23))
        self.assertEqual(records[0].total_budget, 1_500_000)
        self.assertTrue(records[0].official_url.startswith("https://www.incentivi.gov.it/"))
        self.assertIn("Contributo per servizi", records[0].description)
        self.assertEqual(records[1].deadline, None)
        query = adapter.build_query()
        self.assertEqual(query["rows"], "8000")
        self.assertIn("index_id:incentivi", query["q"])
        self.assertIn("Titolo:zs_title", query["fl"])

    def test_fesr_fixture_uses_programme_specific_identity(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "veneto_fesr_calendar.csv"
        records = VenetoFesrCalendarAdapter().parse(path.read_bytes())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].external_id, "FESR-2026-01")
        self.assertEqual(records[0].programme, "PR Veneto FESR+ 2021-2027")
        self.assertTrue(records[0].official_url.startswith("https://programmazione-ue-2021-2027.regione.veneto.it/fesr/"))


if __name__ == "__main__":
    unittest.main()
