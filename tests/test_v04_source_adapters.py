from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from adapters import (
    AicsAdapter,
    ErasmusInappAdapter,
    EuropeanYouthFoundationAdapter,
    FondazioneCariparmaAdapter,
    FondazioneCarisboAdapter,
    FondazioneCrtAdapter,
    FondazioneModenaAdapter,
    MinisteroLavoroTerzoSettoreAdapter,
)


ROOT = Path(__file__).parents[1] / "adapters" / "fixtures"


def fixture(name: str) -> bytes:
    return (ROOT / name).read_bytes()


class Response:
    def __init__(self, payload: bytes, content_type: str = "text/html"):
        self.payload = payload
        self.headers = type("Headers", (), {"get_content_type": lambda self: content_type})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.payload


def test_mlps_annual_windows_and_ets_evidence():
    records = MinisteroLavoroTerzoSettoreAdapter().parse(fixture("ministero_lavoro_terzo_settore.html"))
    assert len(records) == 2
    current = next(record for record in records if record.external_id == "avviso-2026-1")
    assert current.opening_date == date(2026, 2, 20)
    assert current.deadline == date(2026, 4, 2)
    assert current.total_budget == 5_000_000
    assert current.eligible_entities
    assert current.source_status == "CLOSED"


def test_mlps_record_urls_are_official_and_year_scoped():
    records = MinisteroLavoroTerzoSettoreAdapter().parse(fixture("ministero_lavoro_terzo_settore.html"))
    assert all(record.official_url.startswith("https://www.lavoro.gov.it/") for record in records)
    assert {record.external_id for record in records} == {"avviso-2026-1", "avviso-2025-1"}


def test_aics_table_keeps_calls_and_excludes_procurement():
    records = AicsAdapter().parse(fixture("aics.html"))
    assert len(records) == 3
    assert any("Partenariato" in record.title and record.source_status == "OPEN" for record in records)
    assert any(record.deadline == date(2024, 6, 30) and record.source_status == "CLOSED" for record in records)
    assert not any("Gara" in record.title for record in records)


def test_aics_status_is_authoritative_and_entities_are_retained():
    records = AicsAdapter().parse(fixture("aics.html"))
    assert all(record.status_authoritative for record in records)
    assert any("OSC" in record.eligible_entities for record in records)
    assert len({record.external_id for record in records}) == len(records)


def test_eyf_codes_deadlines_and_status_sections():
    records = EuropeanYouthFoundationAdapter().parse(fixture("european_youth_foundation.html"))
    by_id = {record.external_id: record for record in records}
    assert set(by_id) == {"2026.c3.c", "2026.c4.a", "2027.c5.a", "2025.c2.b"}
    assert by_id["2026.c3.c"].deadline == date(2026, 9, 1)
    assert by_id["2026.c3.c"].source_status == "OPEN"
    assert by_id["2027.c5.a"].source_status == "UPCOMING"
    assert by_id["2025.c2.b"].source_status == "CLOSED"


def test_eyf_eligibility_and_official_url_are_fixed():
    records = EuropeanYouthFoundationAdapter().parse(fixture("european_youth_foundation.html"))
    assert all("Youth organisations" in record.eligible_entities[0] for record in records)
    assert all(record.official_url == EuropeanYouthFoundationAdapter.page_url for record in records)
    assert all(record.status_authoritative for record in records)


def test_inapp_keeps_only_inapp_vet_deadlines():
    records = ErasmusInappAdapter().parse(fixture("erasmus_inapp.html"))
    assert len(records) == 5
    assert all("Formazione professionale" in record.title for record in records)
    assert all("INDIRE" not in record.description for record in records)
    assert any(record.deadline == date(2026, 10, 1) for record in records)


def test_inapp_external_ids_separate_same_action_rounds():
    records = ErasmusInappAdapter().parse(fixture("erasmus_inapp.html"))
    assert len({record.external_id for record in records}) == 5
    assert {record.deadline for record in records} >= {date(2026, 2, 19), date(2026, 9, 29), date(2026, 10, 1)}


def test_cariparma_listing_is_dedicated_and_detail_fields_are_enriched():
    adapter = FondazioneCariparmaAdapter()
    records = adapter.parse(fixture("fondazione_cariparma.html"))
    assert [record.title for record in records] == ["Generare conoscenza", "Welfare connesso"]
    response = Response(fixture("fondazione_cariparma_detail.html"))
    with patch("funding_core.adapters.urlopen", return_value=response):
        enriched = adapter.enrich([records[0]], max_details=1)
    assert enriched[0].opening_date == date(2025, 12, 1)
    assert enriched[0].deadline == date(2026, 2, 28)
    assert enriched[0].total_budget == 500_000
    assert enriched[0].source_status == "CLOSED"


def test_cariparma_detail_keeps_eligible_entities_and_official_url():
    adapter = FondazioneCariparmaAdapter()
    record = adapter.parse(fixture("fondazione_cariparma.html"))[0]
    with patch("funding_core.adapters.urlopen", return_value=Response(fixture("fondazione_cariparma_detail.html"))):
        enriched = adapter.enrich([record], max_details=1)
    assert enriched[0].official_url.startswith("https://www.fondazionecrp.it/")
    assert enriched[0].eligible_entities


def test_modena_current_archive_cards_dates_amounts_and_status():
    records = FondazioneModenaAdapter().parse(fixture("fondazione_modena.html"))
    assert len(records) == 4
    current = [record for record in records if record.source_status == "OPEN"]
    archive = [record for record in records if record.source_status == "CLOSED"]
    assert len(current) == 2 and len(archive) == 2
    ricerca = next(record for record in current if "Ricerca Competitiva" in record.title)
    assert ricerca.opening_date == date(2026, 7, 2)
    assert ricerca.deadline == date(2026, 9, 15)
    assert ricerca.total_budget == 2_530_000


def test_modena_titles_are_clean_and_status_is_authoritative():
    records = FondazioneModenaAdapter().parse(fixture("fondazione_modena.html"))
    assert all("Approfondisci" not in record.title and "Data di pubblicazione" not in record.title for record in records)
    assert all(record.status_authoritative for record in records)
    assert len({record.external_id for record in records}) == len(records)


def test_carisbo_rest_filters_external_posts_and_parses_budget_deadline():
    records = FondazioneCarisboAdapter().parse(fixture("fondazione_carisbo.json"))
    assert len(records) == 3
    target = next(record for record in records if "Ricerca medica" in record.title)
    assert target.deadline == date(2026, 10, 9)
    assert target.total_budget == 500_000
    assert all(record.official_url.startswith("https://fondazionecarisbo.it/") for record in records)


def test_carisbo_detail_status_territory_and_entities_are_retained():
    adapter = FondazioneCarisboAdapter()
    target = next(record for record in adapter.parse(fixture("fondazione_carisbo.json")) if "Welfare" in record.title)
    with patch("funding_core.adapters.urlopen", return_value=Response(fixture("fondazione_carisbo_detail.html"))):
        enriched = adapter.enrich([target], max_details=1)
    assert enriched[0].source_status == "CLOSED"
    assert enriched[0].status_authoritative is True
    assert enriched[0].total_budget == 1_250_000
    assert enriched[0].territory == "Città metropolitana di Bologna"
    assert enriched[0].eligible_entities


def test_carisbo_parser_excludes_results_and_dev_urls():
    records = FondazioneCarisboAdapter().parse(fixture("fondazione_carisbo.json"))
    assert not any("Fondo esterno" in record.title for record in records)
    assert not any("Esiti" in record.title for record in records)
    assert not any("Dev test" in record.title for record in records)


def test_crt_v04_badges_and_opening_dates_drive_authoritative_status():
    adapter = FondazioneCrtAdapter()
    records = adapter.parse(fixture("fondazione_crt_v04_listing.html"))
    details = {
        "/note-sipari/": fixture("fondazione_crt_v04_notesipari.html"),
        "/welfare-ordinarie/": fixture("fondazione_crt_v04_ordinarie.html"),
        "/piccoli-comuni-cantieri-ambiente-territorio/": fixture("fondazione_crt_v04_piccoli.html"),
        "/legami-in-comune/": fixture("fondazione_crt_v04_legami.html"),
        "/missione-soccorso/": fixture("fondazione_crt_v04_missione.html"),
        "/culture-of-solidarity-fund/": fixture("fondazione_crt_v04_culture.html"),
        "/mezzi-protezione-civile/": fixture("fondazione_crt_v04_mezzi.html"),
        "/progetto-donoscuola/": fixture("fondazione_crt_v04_donoscuola.html"),
        "/progetto-lagrange/": fixture("fondazione_crt_v04_lagrange.html"),
    }

    def fake_urlopen(request, timeout):
        return Response(next(payload for path, payload in details.items() if path in request.full_url))

    with patch("funding_core.adapters.urlopen", side_effect=fake_urlopen):
        enriched = adapter.enrich(records, max_details=40)
    by_title = {record.title: record for record in enriched}
    assert by_title["NoteSipari"].source_status == "OPEN"
    assert by_title["Ordinarie: Welfare e Territorio"].source_status == "OPEN"
    assert by_title["Ordinarie: Welfare e Territorio"].deadline == date(2026, 10, 15)
    assert by_title["Piccoli comuni - cantieri per l'ambiente e il territorio"].source_status == "UPCOMING"
    assert by_title["Piccoli comuni - cantieri per l'ambiente e il territorio"].opening_date == date(2026, 9, 1)
    assert by_title["Legàmi in Comune"].source_status == "UPCOMING"
    assert by_title["Missione Soccorso"].source_status == "CLOSED"
    assert by_title["Culture of solidarity fund"].source_status == "CLOSED"
    assert "Mezzi Protezione Civile" not in by_title
    assert "Progetto Donoscuola" not in by_title
    assert "Progetto Lagrange" not in by_title


def test_crt_badges_are_read_from_page_chrome_fixtures():
    adapter = FondazioneCrtAdapter()
    expected = {
        "fondazione_crt_v04_notesipari.html": "OPEN",
        "fondazione_crt_v04_ordinarie.html": "OPEN",
        "fondazione_crt_v04_piccoli.html": "UPCOMING",
        "fondazione_crt_v04_legami.html": "UPCOMING",
        "fondazione_crt_v04_missione.html": "CLOSED",
        "fondazione_crt_v04_culture.html": "CLOSED",
    }
    titles = {
        "fondazione_crt_v04_notesipari.html": "NoteSipari",
        "fondazione_crt_v04_ordinarie.html": "Ordinarie: Welfare e Territorio",
        "fondazione_crt_v04_piccoli.html": "Piccoli comuni",
        "fondazione_crt_v04_legami.html": "Legàmi in Comune",
        "fondazione_crt_v04_missione.html": "Missione Soccorso",
        "fondazione_crt_v04_culture.html": "Culture of solidarity fund",
    }
    assert {adapter._official_badge(titles[name], fixture(name)) for name in expected} == set(expected.values())


def load_tests(loader, tests, pattern):
    functions = [
        test_mlps_annual_windows_and_ets_evidence,
        test_mlps_record_urls_are_official_and_year_scoped,
        test_aics_table_keeps_calls_and_excludes_procurement,
        test_aics_status_is_authoritative_and_entities_are_retained,
        test_eyf_codes_deadlines_and_status_sections,
        test_eyf_eligibility_and_official_url_are_fixed,
        test_inapp_keeps_only_inapp_vet_deadlines,
        test_inapp_external_ids_separate_same_action_rounds,
        test_cariparma_listing_is_dedicated_and_detail_fields_are_enriched,
        test_cariparma_detail_keeps_eligible_entities_and_official_url,
        test_modena_current_archive_cards_dates_amounts_and_status,
        test_modena_titles_are_clean_and_status_is_authoritative,
        test_carisbo_rest_filters_external_posts_and_parses_budget_deadline,
        test_carisbo_detail_status_territory_and_entities_are_retained,
        test_carisbo_parser_excludes_results_and_dev_urls,
        test_crt_v04_badges_and_opening_dates_drive_authoritative_status,
        test_crt_badges_are_read_from_page_chrome_fixtures,
    ]
    for function in functions:
        tests.addTest(unittest.FunctionTestCase(function))
    return tests
