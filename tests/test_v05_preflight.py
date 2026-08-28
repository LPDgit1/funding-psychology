from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from adapters import AicsAdapter, FondazioneCrtAdapter, MinisteroLavoroTerzoSettoreAdapter


ROOT = Path(__file__).parents[1] / "adapters" / "fixtures"


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


def fixture(name: str) -> bytes:
    return (ROOT / name).read_bytes()


def test_crt_v05_application_window_precedence_regression():
    adapter = FondazioneCrtAdapter()
    listing = adapter.parse(fixture("fondazione_crt_v05_listing.html"))
    details = {
        "vivomeglio": fixture("fondazione_crt_v05_vivomeglio.html"),
        "best-beni-senza-tempo": fixture("fondazione_crt_v05_best.html"),
        "note-sipari": fixture("fondazione_crt_v05_notesipari.html"),
        "welfare-ordinarie": fixture("fondazione_crt_v05_ordinarie.html"),
        "legami-in-comune": fixture("fondazione_crt_v05_legami.html"),
    }

    def fake_urlopen(request, timeout):
        return Response(next(payload for path, payload in details.items() if path in request.full_url))

    with patch("funding_core.adapters.urlopen", side_effect=fake_urlopen):
        enriched = adapter.enrich(listing, max_details=20)
    by_title = {record.title: record for record in enriched}
    assert by_title["Vivomeglio"].source_status == "CLOSED"
    assert by_title["BeST – Beni Senza Tempo"].source_status == "CLOSED"
    assert by_title["NoteSipari"].source_status == "OPEN"
    assert by_title["Ordinarie: Welfare e Territorio"].source_status == "OPEN"
    assert by_title["Ordinarie: Welfare e Territorio"].deadline == date(2026, 10, 15)
    assert by_title["Legàmi in Comune"].source_status == "UPCOMING"


def test_mlps_combines_oncology_and_art72_entry_points_without_updates():
    adapter = MinisteroLavoroTerzoSettoreAdapter()
    raw = fixture("ministero_lavoro_terzo_settore.html") + adapter._combined_marker.encode() + fixture("ministero_lavoro_art72.html")
    records = adapter.parse(raw)
    assert {record.external_id for record in records} == {"avviso-2026-1", "avviso-2025-1", "art72-avviso-2-2025"}
    art72 = next(record for record in records if record.external_id == "art72-avviso-2-2025")
    assert art72.opening_date == date(2025, 9, 25)
    assert art72.deadline == date(2025, 10, 28)
    assert "art. 72-73" in art72.programme
    assert len(records) == 3


def test_aics_decodes_accented_entities_without_replacement_characters():
    adapter = AicsAdapter()
    raw = fixture("aics.html").decode("utf-8").encode("cp1252")
    records = adapter.parse(raw)
    assert records
    text = " ".join(entity for record in records for entity in record.eligible_entities)
    assert "Società" in text
    assert "Università" in text
    assert "\ufffd" not in text


def load_tests(loader, tests, pattern):
    for function in (
        test_crt_v05_application_window_precedence_regression,
        test_mlps_combines_oncology_and_art72_entry_points_without_updates,
        test_aics_decodes_accented_entities_without_replacement_characters,
    ):
        tests.addTest(__import__("unittest").FunctionTestCase(function))
    return tests
