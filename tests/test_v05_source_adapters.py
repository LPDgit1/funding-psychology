from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from adapters import (
    FondazioneCarispeziaAdapter,
    FondazioneCrLuccaAdapter,
    FondazioneDelMonteAdapter,
    FondazioneMpsAdapter,
    InailBricAdapter,
    MinisteroSaluteRicercaFinalizzataAdapter,
    MurPrinAdapter,
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


def test_salute_finalizzata_is_one_canonical_call_with_ssn_entities():
    records = MinisteroSaluteRicercaFinalizzataAdapter().parse(fixture("ministero_salute_ricerca_finalizzata.html"))
    assert len(records) == 1
    record = records[0]
    assert record.external_id == "ricerca-finalizzata-2024"
    assert record.total_budget == 150_000_000
    assert record.deadline == date(2024, 11, 30)
    assert any("IRCCS" in value for value in record.eligible_entities)


def test_salute_challenge_page_yields_no_false_opportunities():
    records = MinisteroSaluteRicercaFinalizzataAdapter().parse(b"<title>Site verification - Please enable JavaScript</title>")
    assert records == []


def test_mur_prin_keeps_detail_initiatives_and_separate_windows():
    records = MurPrinAdapter().parse(fixture("mur_prin.html"))
    by_title = {record.title: record for record in records}
    assert set(by_title) == {"Bando PRIN 2026", "Bando PRIN 2026 HYBRID", "Bando PRIN 2024 AFAM"}
    assert by_title["Bando PRIN 2026"].deadline == date(2026, 6, 1)
    assert by_title["Bando PRIN 2026 HYBRID"].deadline == date(2026, 6, 4)
    assert by_title["Bando PRIN 2024 AFAM"].deadline is None


def test_mur_prin_urls_and_entities_are_official():
    records = MurPrinAdapter().parse(fixture("mur_prin.html"))
    assert all(record.official_url.startswith("https://prin.mur.gov.it/Iniziative/Detail") for record in records)
    assert any("AFAM" in entity for record in records for entity in record.eligible_entities)
    assert not any("FAQ" in record.title for record in records)


def test_inail_bric_listing_is_year_scoped_and_rejects_graduatoria():
    records = InailBricAdapter().parse(fixture("inail_bric.html"))
    assert {record.external_id for record in records} == {"bric-2025", "bric-2024", "bric-2022"}
    assert all(record.title.startswith("Bando BRIC") for record in records)
    assert not any("Graduatoria" in record.title for record in records)


def test_inail_bric_detail_enrichment_extracts_window_budget_and_entities():
    adapter = InailBricAdapter()
    record = next(item for item in adapter.parse(fixture("inail_bric.html")) if item.external_id == "bric-2025")
    with patch("funding_core.adapters.urlopen", return_value=Response(fixture("inail_bric_2025.html"))):
        enriched = adapter.enrich([record], max_details=1)
    assert enriched[0].opening_date == date(2025, 8, 4)
    assert enriched[0].deadline == date(2025, 10, 6)
    assert enriched[0].total_budget == 14_405_000
    assert enriched[0].source_status == "CLOSED"
    assert enriched[0].eligible_entities


def test_del_monte_normalizes_titles_and_excludes_editorial_cards():
    records = FondazioneDelMonteAdapter().parse(fixture("fondazione_del_monte.html"))
    assert any(record.title == "Ricercaci 2026" for record in records)
    assert {record.title for record in records if record.external_id.startswith("upcoming-")} == {
        "Bando ACCCADE – III Edizione", "Bando ECCCO – III Edizione"
    }
    assert not any("Call for papers" in record.title for record in records)
    assert not any("buona pratica" in record.title.casefold() for record in records)


def test_del_monte_future_windows_are_upcoming_and_detail_fields_are_enriched():
    adapter = FondazioneDelMonteAdapter()
    records = adapter.parse(fixture("fondazione_del_monte.html"))
    acccade = next(record for record in records if "ACCCADE" in record.title)
    assert acccade.source_status == "UPCOMING"
    assert acccade.opening_date == date(2026, 9, 30)
    assert acccade.deadline == date(2026, 10, 30)
    ricercaci = next(record for record in records if record.title == "Ricercaci 2026")
    with patch("funding_core.adapters.urlopen", return_value=Response(fixture("fondazione_del_monte_ricercaci_2026.html"))):
        enriched = adapter.enrich([ricercaci], max_details=1)
    assert enriched[0].deadline == date(2026, 4, 2)
    assert enriched[0].total_budget == 300_000
    assert enriched[0].source_status == "CLOSED"


def test_cr_lucca_jsonld_current_and_archive_grants_are_split_and_canonical():
    adapter = FondazioneCrLuccaAdapter()
    raw = fixture("fondazione_cr_lucca_current.html") + adapter._combined_marker.encode() + fixture("fondazione_cr_lucca_archive.html")
    records = adapter.parse(raw)
    assert len(records) == 4
    assert {record.title for record in records} >= {"Bando 2026 Progett-Azioni", "Welfare e Comunità 2025", "Bando Annuale 2024"}
    assert all(record.official_url.startswith("https://www.fondazionecarilucca.it/") for record in records)


def test_cr_lucca_jsonld_status_and_exhaustion_override_are_authoritative():
    adapter = FondazioneCrLuccaAdapter()
    current = b'<script type="application/ld+json">{"@type":"Grant","name":"Test","url":"/bandi/test","expires":"2099-01-01","description":"Scaduto per esaurimento fondi"}</script>'
    records = adapter.parse(current)
    assert records[0].source_status == "CLOSED"
    assert records[0].status_authoritative is True


def test_carispezia_empty_active_page_and_archive_cards_are_distinguished():
    adapter = FondazioneCarispeziaAdapter()
    raw = fixture("fondazione_carispezia_current.html") + adapter._combined_marker.encode() + fixture("fondazione_carispezia_archive.html")
    records = adapter.parse(raw)
    assert len(records) == 2
    assert all(record.source_status == "CLOSED" for record in records)
    assert all(record.official_url.startswith("https://www.fondazionecarispezia.it/") for record in records)


def test_carispezia_archive_parser_does_not_promote_news_or_pdfs_to_records():
    records = FondazioneCarispeziaAdapter().parse(fixture("fondazione_carispezia_archive.html"))
    assert all("news" not in record.title.casefold() for record in records)
    assert all(not record.official_url.lower().endswith(".pdf") for record in records)
    assert any("Inclusione" in record.title for record in records)


def test_mps_listing_keeps_named_calls_and_filters_project_and_news_links():
    records = FondazioneMpsAdapter().parse(fixture("fondazione_mps.html"))
    titles = {record.title for record in records}
    assert {"Bando RA e RSA", "Social Gym edizione 2026 – Bando Ets", "Siena Plurale"}.issubset(titles)
    assert not any(record.title == "sCOOLFOOD" for record in records)
    assert not any("Esiti" in record.title for record in records)


def test_mps_detail_status_overrides_listing_and_extracts_deadlines():
    adapter = FondazioneMpsAdapter()
    records = adapter.parse(fixture("fondazione_mps.html"))
    details = {
        "ra-rsa": fixture("fondazione_mps_ra_rsa.html"),
        "social-gym": fixture("fondazione_mps_social_gym.html"),
        "siena-plurale": fixture("fondazione_mps_siena_plurale.html"),
    }

    def fake_urlopen(request, timeout):
        return Response(next(payload for path, payload in details.items() if path in request.full_url))

    with patch("funding_core.adapters.urlopen", side_effect=fake_urlopen):
        enriched = adapter.enrich(records[:3], max_details=3)
    by_title = {record.title: record for record in enriched}
    assert by_title["Bando RA e RSA"].source_status == "OPEN"
    assert by_title["Bando RA e RSA"].deadline == date(2026, 7, 10)
    assert by_title["Social Gym edizione 2026 – Bando Ets"].source_status == "CLOSED"
    assert by_title["Siena Plurale"].deadline == date(2026, 5, 15)


def load_tests(loader, tests, pattern):
    functions = [
        test_salute_finalizzata_is_one_canonical_call_with_ssn_entities,
        test_salute_challenge_page_yields_no_false_opportunities,
        test_mur_prin_keeps_detail_initiatives_and_separate_windows,
        test_mur_prin_urls_and_entities_are_official,
        test_inail_bric_listing_is_year_scoped_and_rejects_graduatoria,
        test_inail_bric_detail_enrichment_extracts_window_budget_and_entities,
        test_del_monte_normalizes_titles_and_excludes_editorial_cards,
        test_del_monte_future_windows_are_upcoming_and_detail_fields_are_enriched,
        test_cr_lucca_jsonld_current_and_archive_grants_are_split_and_canonical,
        test_cr_lucca_jsonld_status_and_exhaustion_override_are_authoritative,
        test_carispezia_empty_active_page_and_archive_cards_are_distinguished,
        test_carispezia_archive_parser_does_not_promote_news_or_pdfs_to_records,
        test_mps_listing_keeps_named_calls_and_filters_project_and_news_links,
        test_mps_detail_status_overrides_listing_and_extracts_deadlines,
    ]
    for function in functions:
        tests.addTest(unittest.FunctionTestCase(function))
    return tests
