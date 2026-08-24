from datetime import date, datetime, timezone
from unittest.mock import patch
import unittest

from funding_core.adapters import AdapterError
from funding_core.models import SourceRecord
from funding_core.snapshot import SnapshotSourceSpec, build_snapshot_set


class SnapshotResilienceTests(unittest.TestCase):
    def test_tracking_and_failed_source_preservation(self):
        state = {"mode": "ok", "count": 1, "deadline": date(2026, 12, 31)}

        class FakeAdapter:
            source_label = "Fake source"
            def fetch(self, policy):
                if state["mode"] == "error":
                    raise AdapterError("temporary outage")
                return b"ok"
            def parse(self, raw):
                return [SourceRecord(
                    external_id=f"fake-{index}", title=f"Supporto psicologico {index}",
                    official_url=f"https://example.test/{index}", funder="Fake", deadline=state["deadline"],
                    source_status="OPEN",
                ) for index in range(state["count"])]

        spec = SnapshotSourceSpec("fake", FakeAdapter, 100_000)
        first_now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        second_now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        with patch("funding_core.snapshot.LIVE_SOURCE_SPECS", (spec,)), patch("funding_core.snapshot.FIXTURE_SOURCE_SPECS", ()):
            first = build_snapshot_set(today=date(2026, 8, 24), now=first_now)
            first_item = first["current"]["opportunities"][0]
            state["deadline"] = date(2027, 1, 31)
            second = build_snapshot_set(
                today=date(2026, 8, 25), now=second_now,
                previous_current=first["current"], previous_archive=first["archive"],
            )
            second_item = second["current"]["opportunities"][0]
            self.assertEqual(second_item["firstSeen"], first_item["firstSeen"])
            self.assertEqual(second_item["lastChanged"], second_item["lastSeen"])
            self.assertNotEqual(second_item["contentHash"], first_item["contentHash"])
            state["mode"] = "error"
            failed = build_snapshot_set(
                today=date(2026, 8, 26), now=datetime(2026, 8, 26, tzinfo=timezone.utc),
                previous_current=second["current"], previous_archive=second["archive"],
            )
        self.assertEqual(len(failed["current"]["opportunities"]), 1)
        self.assertEqual(failed["current"]["sources"][0]["status"], "STALE")
        self.assertIn("preserved", failed["current"]["warnings"][0])

    def test_zero_record_anomaly_preserves_previous_dataset(self):
        state = {"empty": False}

        class FakeAdapter:
            source_label = "Fake source"
            def fetch(self, policy): return b"ok"
            def parse(self, raw):
                if state["empty"]: return []
                return [SourceRecord(
                    external_id=str(index), title=f"Bando psicologico {index}",
                    official_url=f"https://example.test/{index}", funder="Fake", source_status="OPEN",
                ) for index in range(11)]

        spec = SnapshotSourceSpec("fake", FakeAdapter, 100_000)
        with patch("funding_core.snapshot.LIVE_SOURCE_SPECS", (spec,)), patch("funding_core.snapshot.FIXTURE_SOURCE_SPECS", ()):
            first = build_snapshot_set(today=date(2026, 8, 24), now=datetime(2026, 8, 24, tzinfo=timezone.utc))
            state["empty"] = True
            second = build_snapshot_set(
                today=date(2026, 8, 25), now=datetime(2026, 8, 25, tzinfo=timezone.utc),
                previous_current=first["current"], previous_archive=first["archive"],
            )
        self.assertEqual(len(second["current"]["opportunities"]), 11)
        self.assertEqual(second["current"]["sources"][0]["status"], "STALE")
        self.assertTrue(any("parser anomaly" in warning for warning in second["current"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
