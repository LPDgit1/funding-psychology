from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from adapters import (
    FamiAdapter,
    FondazioneCariploAdapter,
    FondazioneConIlSudAdapter,
    FondazioneCrcAdapter,
    FondazioneCrFirenzeAdapter,
    FondazioneCrtAdapter,
    FondazioneSardegnaAdapter,
    FondazioneVeneziaAdapter,
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


def test_fami_published_entry_point_keeps_open_and_closed_sections():
    adapter = FamiAdapter()
    raw = fixture("fami_published.html") + adapter._combined_marker.encode() + fixture("fami.html")
    records = adapter.parse(raw)
    open_records = [record for record in records if record.source_status == "OPEN" and "www.interno.gov.it" in record.official_url]
    assert len(open_records) >= 1
    assert all(record.status_authoritative for record in open_records)
    assert any("interno.gov.it" in record.official_url for record in open_records)


def test_crc_reads_current_open_card_and_detail():
    adapter = FondazioneCrcAdapter()
    records = adapter.parse(fixture("fondazione_crc.html"))
    assert [record.title for record in records] == ["Manifesta Bellezza"]
    response = Response(fixture("fondazione_crc_detail.html"))
    with patch("funding_core.adapters.urlopen", return_value=response):
        enriched = adapter.enrich(records)
    assert enriched[0].deadline == date(2026, 9, 30)
    assert enriched[0].source_status == "OPEN"


def test_crt_keeps_application_call_and_rejects_project_cards():
    records = FondazioneCrtAdapter().parse(fixture("fondazione_crt.html"))
    assert [record.title for record in records] == ["Bando Unito"]


def test_venezia_detail_moves_old_2025_call_to_closed():
    adapter = FondazioneVeneziaAdapter()
    records = adapter.parse(fixture("fondazione_venezia.html"))
    assert len(records) == 1
    response = Response(fixture("fondazione_venezia_detail.html"))
    with patch("funding_core.adapters.urlopen", return_value=response):
        enriched = adapter.enrich(records)
    assert enriched[0].deadline == date(2025, 9, 30)
    assert enriched[0].source_status == "CLOSED"
    assert "/archivio-attivita/" in enriched[0].official_url


def test_sardegna_2026_title_uses_official_pdf_deadline():
    adapter = FondazioneSardegnaAdapter()
    record = adapter.parse(fixture("fondazione_sardegna.html"))[0]
    detail = b'<main><h1>Bando annuale 2026 Arte</h1><a href="/media/bando-annuale-2026-arte.pdf">Scarica Bando Annuale 2026 Arte.pdf</a></main>'

    def fake_urlopen(request, timeout):
        url = request.full_url
        return Response(detail if url.endswith("sacrica-bando-arte-2019") else b"%PDF-1.7 fake")

    with patch("adapters.fondazione_sardegna.urlopen", side_effect=fake_urlopen), patch(
        "adapters.fondazione_sardegna._extract_pdf_text",
        return_value="Le richieste devono essere presentate dalle ore 9 del 29 ottobre alle ore 15 del 5 dicembre 2025.",
    ):
        enriched = adapter.enrich([record], max_details=1)
    assert enriched[0].deadline == date(2025, 12, 5)
    assert enriched[0].source_status == "CLOSED"


def test_cariplo_pagination_and_next_future_phase_deadline():
    adapter = FondazioneCariploAdapter()
    raw = fixture("fondazione_cariplo.html") + adapter._combined_marker.encode() + fixture("fondazione_cariplo_page2.html")
    records = adapter.parse(raw)
    assert {record.title for record in records} >= {"Housing Sociale per Persone Fragili", "Luoghi plurali"}
    assert len({record.external_id for record in records}) == len(records)
    target = next(record for record in records if record.title == "Luoghi plurali")
    response = Response(fixture("fondazione_cariplo_detail.html"))
    with patch("funding_core.adapters.urlopen", return_value=response):
        enriched = adapter.enrich([target])
    assert enriched[0].deadline == date(2026, 12, 9)


def test_con_il_sud_parses_explicit_volontariato_deadline():
    records = FondazioneConIlSudAdapter().parse(fixture("fondazione_con_il_sud.html"))
    target = next(record for record in records if record.title == "Bando Volontariato 2026")
    assert target.deadline == date(2026, 9, 30)


def test_crfirenze_keeps_non_thematic_grandi_attrezzature_call():
    raw = b"""<main><article><a href=\"/bandi/grandi-attrezzature/\">Grandi Attrezzature</a><p>In corso. Bando per le attrezzature di ricerca. Scadenza: 18 Settembre 2026.</p></article></main>"""
    records = FondazioneCrFirenzeAdapter().parse(raw)
    assert [record.title for record in records] == ["Grandi Attrezzature"]
    assert records[0].deadline == date(2026, 9, 18)


def load_tests(loader, tests, pattern):
    functions = [
        test_fami_published_entry_point_keeps_open_and_closed_sections,
        test_crc_reads_current_open_card_and_detail,
        test_crt_keeps_application_call_and_rejects_project_cards,
        test_venezia_detail_moves_old_2025_call_to_closed,
        test_sardegna_2026_title_uses_official_pdf_deadline,
        test_cariplo_pagination_and_next_future_phase_deadline,
        test_con_il_sud_parses_explicit_volontariato_deadline,
        test_crfirenze_keeps_non_thematic_grandi_attrezzature_call,
    ]
    for function in functions:
        tests.addTest(unittest.FunctionTestCase(function))
    return tests
