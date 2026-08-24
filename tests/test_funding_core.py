from datetime import date
import json
from pathlib import Path
import unittest

from funding_core.adapters import (
    AigOpportunitiesAdapter,
    ConIBambiniAdapter,
    DipartimentoDisabilitaAdapter,
    DipartimentoFamigliaAdapter,
    ErasmusIndireAdapter,
    FondoRepubblicaDigitaleAdapter,
    FondazioneCariparoAdapter,
    FondazioneCariveronaAdapter,
    IncentiviGovAdapter,
    InterregItalyCroatiaAdapter,
    EuFundingTendersAdapter,
    VenetoBandiAdapter,
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

    def test_erasmus_indire_fixture_filters_agency_and_dates(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "erasmus_indire_deadlines.html"
        records = ErasmusIndireAdapter().parse(path.read_bytes())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].deadline, date(2026, 3, 5))
        self.assertEqual(records[1].deadline, date(2026, 2, 19))
        self.assertEqual(records[0].funder, "Agenzia nazionale Erasmus+ INDIRE")
        self.assertTrue(all(record.official_url.startswith("https://") for record in records))

    def test_aig_fixture_parse_and_missing_deadline(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "aig_opportunities.json"
        records = AigOpportunitiesAdapter().parse(path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].external_id, "19807")
        self.assertEqual(records[0].deadline, date(2026, 10, 31))
        self.assertIn("inclusione sociale", records[0].description)
        self.assertIsNone(records[1].deadline)
        self.assertIn("categories", AigOpportunitiesAdapter().build_query())

    def test_interreg_fixture_extracts_schedule_and_budget(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "interreg_italy_croatia_call.html"
        records = InterregItalyCroatiaAdapter().parse(path.read_bytes())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].opening_date, date(2026, 6, 15))
        self.assertEqual(records[0].deadline, date(2026, 9, 15))
        self.assertEqual(records[0].total_budget, 5_859_000)
        self.assertTrue(records[0].official_url.startswith("https://www.italy-croatia.eu/"))

    def test_veneto_bandi_home_fixture_extracts_cards(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "veneto_bandi_home.html"
        records = VenetoBandiAdapter().parse(path.read_bytes())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].external_id, "13137")
        self.assertEqual(records[0].deadline, date(2026, 8, 26))
        self.assertEqual(records[0].programme, "Portale Bandi — Bando o finanziamento")
        self.assertTrue(records[1].official_url.endswith("idAtto=13237"))

    def test_family_and_disability_lists_filter_detail_links(self):
        root = Path(__file__).parents[1] / "funding_core" / "fixtures"
        family = DipartimentoFamigliaAdapter().parse((root / "dipartimento_famiglia.html").read_bytes())
        disability = DipartimentoDisabilitaAdapter().parse((root / "dipartimento_disabilita.html").read_bytes())
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0].source_status, "UNKNOWN")
        self.assertEqual(len(disability), 1)
        self.assertEqual(disability[0].external_id, "avviso-vita-opportunita")

    def test_foundation_and_child_digital_lists_filter_detail_links(self):
        root = Path(__file__).parents[1] / "funding_core" / "fixtures"
        cariparo = FondazioneCariparoAdapter().parse((root / "fondazione_cariparo.html").read_bytes())
        cariverona = FondazioneCariveronaAdapter().parse((root / "fondazione_cariverona.html").read_bytes())
        children = ConIBambiniAdapter().parse((root / "con_i_bambini.html").read_bytes())
        digital = FondoRepubblicaDigitaleAdapter().parse((root / "fondo_repubblica_digitale.html").read_bytes())
        self.assertEqual(len(cariparo), 1)
        self.assertEqual(len(cariverona), 1)
        self.assertEqual(len(children), 1)
        self.assertEqual(len(digital), 1)
        self.assertEqual(digital[0].funder, "Fondo per la Repubblica Digitale")


if __name__ == "__main__":
    unittest.main()
