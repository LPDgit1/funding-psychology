import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from funding_core.operational import (
    assess_anomaly,
    snapshot_validation_errors,
    source_health,
    update_daily_sync_deployment_status,
    write_daily_sync_report,
)


def _source(source_id, kind="live", status="LIVE"):
    return {"sourceId": source_id, "label": source_id, "kind": kind, "status": status, "warnings": []}


def _snapshot(dataset, sources, records):
    return {
        "schemaVersion": 2,
        "dataset": dataset,
        "generatedAt": "2026-09-01T04:17:00Z",
        "asOfDate": "2026-09-01",
        "complete": True,
        "recordCount": len(records),
        "recordCountCurrent": len(records) if dataset == "current" else 0,
        "recordCountArchive": len(records) if dataset == "archive" else 0,
        "liveSourceCount": sum(1 for row in sources if row["kind"] == "live" and row["status"] == "LIVE"),
        "sourceCount": len(sources),
        "sourceHealth": source_health(sources),
        "sources": sources,
        "warnings": [],
        "notImplemented": [],
        "opportunities": records,
    }


class OperationalPreflightTests(unittest.TestCase):
    def test_source_health_counts_fixture_and_unavailable_sources(self):
        sources = [_source("one"), _source("two", status="STALE"), _source("three", status="ERROR"), _source("calendar", "fixture", "FIXTURE_ONLY")]
        self.assertEqual(source_health(sources), {
            "totalSourceCount": 4,
            "liveConfiguredSourceCount": 3,
            "successfulSourceCount": 1,
            "staleSourceCount": 1,
            "errorSourceCount": 1,
            "fixtureOnlySourceCount": 1,
        })

    def test_snapshot_validation_accepts_explicit_health_and_rejects_duplicate_ids(self):
        sources = [_source("one"), _source("calendar", "fixture", "FIXTURE_ONLY")]
        record = {"id": "one:1", "officialUrl": "https://example.test/1", "status": "OPEN"}
        current = _snapshot("current", sources, [record])
        self.assertEqual(snapshot_validation_errors(current, expected_dataset="current"), [])
        current["opportunities"].append(dict(record))
        current["recordCount"] = 2
        self.assertIn("opportunity ids are not unique", snapshot_validation_errors(current, expected_dataset="current"))

    def test_global_guard_blocks_record_and_majority_source_collapse(self):
        previous_sources = [_source(f"s{index}") for index in range(4)]
        current_sources = [_source("s0", status="LIVE"), _source("s1", status="STALE"), _source("s2", status="ERROR"), _source("s3", status="STALE")]
        previous = _snapshot("current", previous_sources, [{"id": f"s0:{index}", "officialUrl": f"https://example.test/{index}", "status": "OPEN"} for index in range(100)])
        candidate = _snapshot("current", current_sources, [{"id": "s0:1", "officialUrl": "https://example.test/1", "status": "OPEN"}])
        result = assess_anomaly(candidate, previous)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertGreaterEqual(len(result["reasons"]), 2)

    def test_global_guard_allows_one_stale_source_with_fallback(self):
        previous_sources = [_source(f"s{index}") for index in range(4)]
        current_sources = [_source("s0"), _source("s1"), _source("s2"), _source("s3", status="STALE")]
        previous = _snapshot("current", previous_sources, [{"id": f"s0:{index}", "officialUrl": f"https://example.test/{index}", "status": "OPEN"} for index in range(100)])
        candidate = _snapshot("current", current_sources, [{"id": f"s0:{index}", "officialUrl": f"https://example.test/{index}", "status": "OPEN"} for index in range(95)])
        self.assertEqual(assess_anomaly(candidate, previous)["status"], "PASS")

    def test_latest_daily_report_contains_required_status_and_counts(self):
        sources = [_source("one"), _source("two", status="STALE"), _source("calendar", "fixture", "FIXTURE_ONLY")]
        anomaly = {"status": "PASS", "reasons": []}
        with tempfile.TemporaryDirectory() as directory:
            target = write_daily_sync_report(
                Path(directory) / "daily-sync-latest.json",
                started_at=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 9, 1, 4, 5, tzinfo=timezone.utc),
                snapshot_generated_at="2026-09-01T04:05:00Z",
                source_results=sources,
                current_records=12,
                archive_records=8,
                anomaly=anomaly,
                snapshot_valid=True,
            )
            report = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(report["sourcesAttempted"], 2)
        self.assertEqual(report["LIVE"], ["one"])
        self.assertEqual(report["STALE"], ["two"])
        self.assertEqual(report["FIXTURE_ONLY"], ["calendar"])
        self.assertEqual(report["currentRecords"], 12)
        self.assertEqual(report["syncStatus"], "DATA_SYNC_OK")
        self.assertEqual(report["deploymentStatus"], "NOT_ATTEMPTED")

    def test_deployment_failure_is_recorded_without_hiding_data_sync_success(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write_daily_sync_report(
                Path(directory) / "daily-sync-latest.json",
                started_at="2026-09-01T04:00:00Z",
                completed_at="2026-09-01T04:05:00Z",
                snapshot_generated_at="2026-09-01T04:05:00Z",
                source_results=[_source("one")],
                current_records=1,
                archive_records=0,
                anomaly={"status": "PASS", "reasons": []},
                snapshot_valid=True,
            )
            update_daily_sync_deployment_status(target, "DEPLOY_FAILED")
            report = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(report["syncStatus"], "DATA_SYNC_OK")
        self.assertEqual(report["deploymentStatus"], "DEPLOY_FAILED")


if __name__ == "__main__":
    unittest.main()
