from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch

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
    _detail_fields,
)
from funding_core.classifier import classify
from funding_core.classifier import classify_with_relevance
from funding_core.dates import parse_date
from funding_core.pipeline import anomaly_warnings, process
from funding_core.models import SourceRecord
from funding_core.snapshot import public_opportunity
from funding_core.search import matches_query
from funding_core.territories import normalize_territory, split_regions


class FundingCoreTests(unittest.TestCase):
    def test_eu_multiple_deadlines_and_official_status_precedence(self):
        payload = {
            "results": [
                {"metadata": {
                    "identifier": ["CASE-A"], "title": ["Open multi-cutoff"], "status": ["31094502"],
                    "deadlineDate": ["2023-02-01", "2025-02-01", "2026-12-15"],
                }},
                {"metadata": {
                    "identifier": ["CASE-B"], "title": ["Upcoming historical"], "status": ["31094501"],
                    "deadlineDate": ["2022-02-01", "2024-02-01"],
                }},
                {"metadata": {
                    "identifier": ["CASE-C"], "title": ["Unknown past"], "status": ["999"],
                    "deadlineDate": ["2022-02-01", "2024-02-01"],
                }},
            ],
        }
        records = EuFundingTendersAdapter().parse(payload, today=date(2026, 8, 24))
        self.assertEqual(records[0].deadline, date(2026, 12, 15))
        self.assertEqual(records[1].deadline, None)
        self.assertTrue(records[0].status_authoritative)
        items = process("eu-funding-tenders", records, date(2026, 8, 24))
        self.assertEqual({item.source_external_id: item.status for item in items}, {"CASE-A": "OPEN", "CASE-B": "UPCOMING", "CASE-C": "CLOSED"})

    def test_detail_cleanup_prefers_main_and_excludes_site_chrome(self):
        fields = _detail_fields("""
            <html><head><title>Vero bando</title></head>
            <header>MENU PRINCIPALE caregiver demenza</header>
            <nav>Home Archivio Ricerca</nav>
            <main><h1>Vero bando</h1><p>Scadenza: 24 agosto 2026.</p><p>Beneficiari: ETS e Comuni.</p></main>
            <aside>SIDEBAR giovani digitale</aside><footer>FOOTER Regione Veneto</footer>
        """)
        self.assertIn("Vero bando", str(fields["description"]))
        self.assertNotIn("MENU PRINCIPALE", str(fields["description"]))
        self.assertNotIn("FOOTER", str(fields["description"]))
        self.assertEqual(fields["deadline"], date(2026, 8, 24))
        self.assertIn("ETS", fields["eligible_entities"][0])

    def test_common_search_fixture_matches_report_semantics(self):
        fixture_path = Path(__file__).parent / "fixtures" / "search-cases.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        titles = {
            "fixture-dementia-caregiver": "Programma caregiver e demenza",
            "fixture-youth-mental-health": "Salute mentale degli adolescenti",
            "fixture-school-bullying": "Prevenzione bullismo a scuola",
            "fixture-gender-violence": "Violenza di genere",
            "fixture-youth-addictions": "Dipendenze e giovani",
            "fixture-worker-burnout": "Burnout dei lavoratori",
            "fixture-older-psychology": "Psicologia per anziani",
            "fixture-migration-trauma": "Migrazione e trauma",
            "fixture-disability-inclusion": "Inclusione sociale e disabilità",
            "fixture-ai-mental-health": "AI e salute mentale",
        }
        items = [{"id": item_id, "title": title, "summary": "", "programme": "", "funder": "", "eligibleEntities": [], "regions": []} for item_id, title in titles.items()]
        for case in cases:
            found = [item["id"] for item in items if matches_query(item, case["query"])]
            self.assertEqual(found, case["expected"], case["query"])
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
        self.assertIn("31094502", encoded)
        self.assertIn('"type": ["1", "8"]', encoded)

    def test_eu_fetch_paginates_current_pages(self):
        adapter = EuFundingTendersAdapter()
        adapter.page_size = 2
        pages = []
        for index in range(3):
            results = [{"metadata": {"identifier": f"ID-{index}-{row}", "title": [f"Call {index}-{row}"], "status": ["31094502"]}} for row in range(2 if index < 2 else 1)]
            pages.append({"results": results, "totalResults": 5})

        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()
                self.headers = type("Headers", (), {"get_content_type": lambda self: "application/json"})()
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, limit): return self.payload

        calls = []
        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            return Response(pages[len(calls) - 1])

        with patch("funding_core.adapters.urlopen", side_effect=fake_urlopen):
            payload = adapter.fetch()
        self.assertEqual(len(adapter.parse(payload)), 5)
        self.assertEqual(len(calls), 3)
        self.assertIn("pageNumber=2", calls[1])
        self.assertIn("text=***", calls[0])

    def test_incentivi_fixture_parse_and_contract(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "incentivi_gov.json"
        adapter = IncentiviGovAdapter()
        records = adapter.parse(path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].external_id, "FIXTURE-1423")
        self.assertEqual(records[0].opening_date, date(2026, 9, 8))
        self.assertEqual(records[0].deadline, date(2026, 12, 23))
        self.assertEqual(records[0].total_budget, 1_500_000)
        self.assertEqual(records[0].official_url, "https://example.gov.it/bando-psicologia")
        self.assertEqual(records[0].territory, None)
        self.assertEqual(records[0].aggregator_url, "https://www.incentivi.gov.it/it/catalogo/sostegno-servizi-psicologici")
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
        self.assertEqual(records, [])
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

    def test_veneto_bandi_elenco_is_not_limited_to_ten_home_cards(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "veneto_bandi_elenco.html"
        records = VenetoBandiAdapter().parse(path.read_bytes())
        self.assertEqual(len(records), 12)
        self.assertEqual(records[-1].external_id, "14012")
        self.assertEqual(records[0].deadline, date(2026, 9, 1))
        self.assertIn("Bando 01", records[0].title)

    def test_family_and_disability_lists_filter_detail_links(self):
        root = Path(__file__).parents[1] / "funding_core" / "fixtures"
        family = DipartimentoFamigliaAdapter().parse((root / "dipartimento_famiglia.html").read_bytes())
        disability = DipartimentoDisabilitaAdapter().parse((root / "dipartimento_disabilita.html").read_bytes())
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0].source_status, "UNKNOWN")
        self.assertEqual(len(disability), 1)
        self.assertEqual(disability[0].external_id, "avviso-vita-opportunita")

    def test_html_detail_enrichment_is_best_effort(self):
        root = Path(__file__).parents[1] / "funding_core" / "fixtures"
        record = DipartimentoFamigliaAdapter().parse((root / "dipartimento_famiglia.html").read_bytes())[0]

        class Response:
            headers = type("Headers", (), {"get_content_type": lambda self: "text/html"})()
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, limit):
                return b"<html><title>Dettaglio bando</title><h1>Dettaglio bando</h1><p>Scadenza: 24 agosto 2026.</p><p>Budget: EUR 150.000.</p><p>Beneficiari: ETS e Comuni.</p></html>"

        with patch("funding_core.adapters.urlopen", return_value=Response()):
            enriched = DipartimentoFamigliaAdapter().enrich([record])
        self.assertEqual(enriched[0].deadline, date(2026, 8, 24))
        self.assertEqual(enriched[0].total_budget, 150000)
        self.assertIn("ETS", enriched[0].eligible_entities[0])

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

    def test_public_snapshot_mapping_is_not_demo_data(self):
        path = Path(__file__).parents[1] / "funding_core" / "fixtures" / "eu_funding_tenders.json"
        item = process("eu-funding-tenders", EuFundingTendersAdapter().parse(path.read_text(encoding="utf-8")), date(2026, 8, 24))[0]
        public = public_opportunity(item, date(2026, 8, 24))
        self.assertFalse(public["demo"])
        self.assertEqual(public["territory"], "Unione Europea")
        self.assertEqual(public["deadline"], "2027-02-18")
        self.assertTrue(public["officialUrl"].startswith("https://"))

    def test_weighted_relevance_separates_topic_from_psychology(self):
        high = classify_with_relevance("supporto psicologico per adolescenti e salute mentale")
        low = classify_with_relevance("contributi per digitalizzazione delle PMI e macchinari")
        self.assertEqual(high.label, "Alta")
        self.assertGreater(high.score, low.score)
        self.assertIn("Digitale, innovazione e AI", low.macro_areas)
        self.assertEqual(low.label, "Bassa")

    def test_date_and_territory_normalization(self):
        self.assertEqual(parse_date("24 agosto 2026"), date(2026, 8, 24))
        self.assertEqual(parse_date("August 24, 2026"), date(2026, 8, 24))
        self.assertEqual(parse_date("2026-08-24T12:00:00Z"), date(2026, 8, 24))
        regions = split_regions(("Regione Marche; Regione Veneto",))
        self.assertEqual(regions, ("Marche", "Veneto"))
        self.assertEqual(normalize_territory(regions, "multi-regione"), "Multi-regione")

    def test_aig_filters_event_without_call_signal(self):
        payload = [{
            "id": 1, "link": "https://agenziagioventu.gov.it/evento/1/",
            "title": {"rendered": "Webinar informativo"},
            "content": {"rendered": "Presentazione di una consultazione pubblica."},
        }, {
            "id": 2, "link": "https://agenziagioventu.gov.it/bando/2/",
            "title": {"rendered": "Call per candidature"},
            "content": {"rendered": "Candidature entro il 24 agosto 2026."},
        }]
        records = AigOpportunitiesAdapter().parse(payload)
        self.assertEqual(records, [])

    def test_aig_filters_editorial_activities_without_project_funding(self):
        payload = [
            {"id": 3, "link": "https://agenziagioventu.gov.it/contest/3/",
             "title": {"rendered": "Contest creativo nazionale"},
             "content": {"rendered": "Un'iniziativa per giovani e partecipanti."}},
            {"id": 4, "link": "https://agenziagioventu.gov.it/evento/4/",
             "title": {"rendered": "Round table on social sport"},
             "content": {"rendered": "Tavola rotonda e confronto tra operatori."}},
            {"id": 5, "link": "https://agenziagioventu.gov.it/focus/5/",
             "title": {"rendered": "Focus group giovani"},
             "content": {"rendered": "Call for participants entro il 24 agosto 2026."}},
            {"id": 6, "link": "https://agenziagioventu.gov.it/corso/6/",
             "title": {"rendered": "Training course Erasmus+"},
             "content": {"rendered": "Corso di formazione per youth workers."}},
        ]
        self.assertEqual(AigOpportunitiesAdapter().parse(payload), [])

    def test_aig_keeps_project_calls_and_grants(self):
        payload = [
            {
                "id": 10, "link": "https://agenziagioventu.gov.it/bando/ka210/",
                "title": {"rendered": "KA210 project grant call"},
                "content": {"rendered": "Funding application per un progetto di cooperazione. Deadline: 24 agosto 2026."},
            },
            {
                "id": 11, "link": "https://agenziagioventu.gov.it/bando/ka220/",
                "title": {"rendered": "KA220"},
                "content": {"rendered": "Bando Erasmus+ per finanziamento di progetti. Scadenza 31 ottobre 2026."},
            },
            {
                "id": 12, "link": "https://agenziagioventu.gov.it/evento/festival/",
                "title": {"rendered": "Festival giovani"},
                "content": {"rendered": "Evento e call for participants."},
            },
        ]
        records = AigOpportunitiesAdapter().parse(payload)
        self.assertEqual([record.external_id for record in records], ["10", "11"])


if __name__ == "__main__":
    unittest.main()
