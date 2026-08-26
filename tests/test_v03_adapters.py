from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from adapters import (
    CompagniaSanPaoloAdapter,
    DipendenzeAdapter,
    FamiAdapter,
    FondazioneCariploAdapter,
    FondazioneConIlSudAdapter,
    FondazioneCrcAdapter,
    FondazioneCrFirenzeAdapter,
    FondazioneCrtAdapter,
    FondazioneFriuliAdapter,
    FondazioneSardegnaAdapter,
    FondazioneVeneziaAdapter,
    IntesaBeneficenzaAdapter,
    PariOpportunitaAdapter,
    PnScuolaAdapter,
)
from funding_core.pipeline import process


ROOT = Path(__file__).parents[1] / "adapters" / "fixtures"


ADAPTERS = (
    PariOpportunitaAdapter,
    DipendenzeAdapter,
    FamiAdapter,
    PnScuolaAdapter,
    FondazioneVeneziaAdapter,
    IntesaBeneficenzaAdapter,
    CompagniaSanPaoloAdapter,
    FondazioneCariploAdapter,
    FondazioneConIlSudAdapter,
    FondazioneCrtAdapter,
    FondazioneCrFirenzeAdapter,
    FondazioneCrcAdapter,
    FondazioneSardegnaAdapter,
    FondazioneFriuliAdapter,
)


class V03AdapterTests(unittest.TestCase):
    def fixture(self, adapter) -> bytes:
        return (ROOT / f"{adapter.source_id}.html").read_bytes()

    def test_every_planned_adapter_has_a_fixture_and_parses(self):
        for adapter_class in ADAPTERS:
            adapter = adapter_class()
            with self.subTest(source=adapter.source_id):
                records = adapter.parse(self.fixture(adapter))
                self.assertGreater(len(records), 0)
                self.assertTrue(all(item.official_url.startswith("https://") for item in records))
                self.assertTrue(all(item.title.strip() for item in records))

    def test_listing_filters_obvious_results_and_editorial_items(self):
        checks = (
            (PariOpportunitaAdapter, "graduatori"),
            (DipendenzeAdapter, "esperti"),
            (FondazioneVeneziaAdapter, "selezionati"),
            (FondazioneCariploAdapter, "assegnati"),
            (FondazioneConIlSudAdapter, "sostenuti"),
            (FondazioneCrcAdapter, "deliberati"),
            (CompagniaSanPaoloAdapter, "risultati"),
            (FondazioneCrFirenzeAdapter, "esiti"),
        )
        for adapter_class, forbidden in checks:
            adapter = adapter_class()
            titles = " ".join(item.title.lower() for item in adapter.parse(self.fixture(adapter)))
            with self.subTest(source=adapter.source_id):
                self.assertNotIn(forbidden, titles)

    def test_pari_opportunita_and_dipendenze_dates_and_status(self):
        pari = PariOpportunitaAdapter().parse(self.fixture(PariOpportunitaAdapter()))[0]
        dip = DipendenzeAdapter().parse(self.fixture(DipendenzeAdapter()))[0]
        self.assertEqual(pari.source_status, "OPEN")
        self.assertEqual(pari.deadline, date(2026, 9, 30))
        self.assertEqual(dip.source_status, "OPEN")
        self.assertEqual(dip.deadline, date(2026, 10, 15))

    def test_fami_separates_early_and_call(self):
        records = FamiAdapter().parse(self.fixture(FamiAdapter()))
        self.assertEqual([item.source_status for item in records], ["UPCOMING", "OPEN"])
        self.assertIsNone(records[0].opening_date)
        self.assertEqual(records[1].deadline, date(2026, 11, 20))
        self.assertEqual(records[1].total_budget, 2_500_000)

    def test_pn_scuola_keeps_applicant_as_school(self):
        records = PnScuolaAdapter().parse(self.fixture(PnScuolaAdapter()))
        self.assertEqual(records[0].source_status, "CLOSED")
        self.assertEqual(records[0].deadline, date(2026, 5, 26))
        self.assertIn("Istituzioni scolastiche", records[0].eligible_entities[0])
        self.assertEqual(records[1].source_status, "UPCOMING")
        self.assertIsNone(records[1].deadline)

    def test_intesa_is_a_single_rolling_record_without_deadline(self):
        records = IntesaBeneficenzaAdapter().parse(self.fixture(IntesaBeneficenzaAdapter()))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_status, "OPEN")
        self.assertTrue(records[0].status_authoritative)
        self.assertIsNone(records[0].deadline)
        self.assertIn("senza finalità di lucro", records[0].eligible_entities[0])

    def test_compagnia_card_context_keeps_each_status_and_deadline(self):
        records = CompagniaSanPaoloAdapter().parse(self.fixture(CompagniaSanPaoloAdapter()))
        by_title = {item.title: item for item in records}
        self.assertEqual(len(records), 2)
        self.assertEqual(by_title["Bando promozione salute mentale giovani"].source_status, "OPEN")
        self.assertEqual(by_title["Bando promozione salute mentale giovani"].deadline, date(2026, 11, 30))
        self.assertEqual(by_title["Bando educazione e comunità 2025"].source_status, "CLOSED")
        self.assertEqual(by_title["Bando educazione e comunità 2025"].deadline, date(2025, 6, 15))

    def test_foundations_preserve_territory_and_budget(self):
        cariplo = FondazioneCariploAdapter().parse(self.fixture(FondazioneCariploAdapter()))[0]
        sud = FondazioneConIlSudAdapter().parse(self.fixture(FondazioneConIlSudAdapter()))[0]
        self.assertEqual(cariplo.territory, "Lombardia")
        self.assertEqual(sud.total_budget, 4_000_000)
        self.assertEqual(set(sud.regions), {"Basilicata", "Calabria", "Campania", "Molise", "Puglia", "Sardegna", "Sicilia"})

    def test_crt_and_crfirenze_keep_local_scope(self):
        crt = FondazioneCrtAdapter().parse(self.fixture(FondazioneCrtAdapter()))[0]
        crf = FondazioneCrFirenzeAdapter().parse(self.fixture(FondazioneCrFirenzeAdapter()))[0]
        self.assertIn("Piemonte", crt.regions)
        self.assertEqual(crf.territory, "Città metropolitana di Firenze")
        self.assertEqual(crf.deadline, date(2026, 9, 30))

    def test_sardegna_uses_one_canonical_record_per_sector(self):
        records = FondazioneSardegnaAdapter().parse(self.fixture(FondazioneSardegnaAdapter()))
        self.assertEqual(len(records), 4)
        self.assertEqual(len({item.external_id for item in records}), 4)
        self.assertTrue(all(item.territory == "Sardegna" for item in records))
        self.assertTrue(all(item.deadline is None for item in records))

    def test_friuli_welfare_is_upcoming_without_invented_date(self):
        records = FondazioneFriuliAdapter().parse(self.fixture(FondazioneFriuliAdapter()))
        by_id = {item.external_id: item for item in records}
        self.assertEqual(by_id["istruzione-2026"].deadline, date(2026, 3, 20))
        self.assertEqual(by_id["restauro-2026"].total_budget, 500_000)
        self.assertEqual(by_id["welfare-2026"].source_status, "UPCOMING")
        self.assertIsNone(by_id["welfare-2026"].opening_date)
        self.assertIsNone(by_id["welfare-2026"].deadline)

    def test_process_deduplicates_repeated_fundation_links(self):
        adapter = FondazioneCariploAdapter()
        records = adapter.parse(self.fixture(adapter))
        repeated = records + records
        self.assertEqual(len(process(adapter.source_id, repeated, date(2026, 8, 26))), len(records))


if __name__ == "__main__":
    unittest.main()
