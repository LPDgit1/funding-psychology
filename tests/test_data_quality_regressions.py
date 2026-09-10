import unittest
from datetime import date

from funding_core.money import parse_money, extract_money
from funding_core.adapters import _detail_fields, IncentiviGovAdapter
from funding_core.snapshot import _revalidate_previous_item
from adapters._common import extract_deadline


class DataQualityRegressions(unittest.TestCase):
    def test_decimal_budgets_are_not_multiplied_by_100(self):
        for token in ("1418293.57", "1.418.293,57", "1,418,293.57"):
            self.assertEqual(parse_money(token), 1418293)
            self.assertEqual(IncentiviGovAdapter._money([token]), 1418293)
        self.assertEqual(parse_money("1.250.000"), 1250000)
        self.assertIsNone(parse_money("2025 e 2026"))

    def test_scale_and_currency_evidence(self):
        self.assertEqual(extract_money("Dotazione complessiva di 10 milioni di euro"), 10000000)
        self.assertEqual(extract_money("1,5 milioni di euro"), 1500000)
        self.assertIsNone(extract_money("finanziamento nel 2025"))
        self.assertIsNone(extract_money("importo articolo 146"))
        self.assertIsNone(extract_money("Linea A: fino a 30.000 euro. Linea B: fino a 120.000 euro."))
        self.assertEqual(extract_money("Dotazione di 3 milioni di euro. Contributo minimo: € 50.000. Contributo massimo: € 200.000."), 3000000)

    def test_deadline_after_decimal_clock(self):
        text = "Domande entro le ore 13.00 del 21 maggio 2026."
        self.assertEqual(_detail_fields(f"<main>{text}</main>")["deadline"], date(2026, 5, 21))
        self.assertEqual(extract_deadline(text), date(2026, 5, 21))

    def test_expired_fallback_keeps_original_verification(self):
        item = dict(title="Bando per progetti di salute mentale", summary="Contributi per interventi psicologici",
                    status="OPEN", deadline="2026-09-01", lastSeen="2026-08-28")
        updated = _revalidate_previous_item(item, date(2026, 9, 7))
        self.assertEqual(updated["status"], "CLOSED")
        self.assertEqual(updated["lastSeen"], "2026-08-28")
        self.assertEqual(item["status"], "OPEN")
