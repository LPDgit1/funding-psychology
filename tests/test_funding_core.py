from datetime import date
from pathlib import Path
import unittest

from funding_core.adapters import VenetoFseCalendarAdapter
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


if __name__ == "__main__":
    unittest.main()
