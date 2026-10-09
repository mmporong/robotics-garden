import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import collect_views as cv


OLD = "research/2026-08-01_old"
NEW = "research/2026-10-02_new"


def row(at, views):
    return {"at": at, "views": views}


class MonthlyTest(unittest.TestCase):
    def monthly(self, views, rows, at="2026-10-09T09:00:00+09:00"):
        return cv.monthly(views, datetime.fromisoformat(at), rows)

    def test_old_lifetime_leader_does_not_beat_new_monthly_leader(self):
        result = self.monthly({OLD: 101, NEW: 8}, [
            row("2026-09-30T09:00:00+09:00", {OLD: 100}),
            row("2026-10-03T09:00:00+09:00", {OLD: 101, NEW: 3}),
        ])
        self.assertEqual(result["views"], {OLD: 1, NEW: 8})
        self.assertEqual(result["total"], 9)
        self.assertEqual(result["baseline_at"], "2026-09-30T09:00:00+09:00")

    def test_kst_boundary_resets_month_without_resetting_counter(self):
        result = self.monthly({OLD: 111}, [
            row("2026-09-30T14:59:59+00:00", {OLD: 110}),
        ], at="2026-09-30T15:00:00+00:00")
        self.assertEqual(result["period"], "2026-10")
        self.assertEqual(result["views"][OLD], 1)

    def test_year_boundary(self):
        result = self.monthly({OLD: 30}, [
            row("2026-12-31T23:59:59+09:00", {OLD: 25}),
        ], at="2027-01-01T00:00:00+09:00")
        self.assertEqual(result["period"], "2027-01")
        self.assertEqual(result["views"][OLD], 5)

    def test_missing_old_baseline_does_not_count_lifetime_as_monthly(self):
        result = self.monthly({OLD: 80, NEW: 4}, [])
        self.assertEqual(result["views"], {OLD: 0, NEW: 4})
        self.assertIsNone(result["baseline_at"])

    def test_missing_slug_in_an_intermediate_sample_keeps_its_baseline(self):
        result = self.monthly({OLD: 12}, [
            row("2026-09-30T09:00:00+09:00", {OLD: 10}),
            row("2026-10-03T09:00:00+09:00", {}),
        ])
        self.assertEqual(result["views"][OLD], 2)

    def test_duplicate_collection_and_counter_reset_do_not_remove_gains(self):
        result = self.monthly({OLD: 3}, [
            row("2026-09-30T09:00:00+09:00", {OLD: 10}),
            row("2026-10-02T09:00:00+09:00", {OLD: 15}),
            row("2026-10-02T09:01:00+09:00", {OLD: 15}),
            row("2026-10-03T09:00:00+09:00", {OLD: 0}),
            row("2026-10-09T09:00:00+09:00", {OLD: 3}),
        ])
        self.assertEqual(result["views"][OLD], 8)

    def test_unsorted_history_and_future_samples(self):
        result = self.monthly({OLD: 13}, [
            row("2026-10-10T09:00:00+09:00", {OLD: 100}),
            row("2026-10-03T09:00:00+09:00", {OLD: 11}),
            row("2026-09-30T09:00:00+09:00", {OLD: 10}),
        ])
        self.assertEqual(result["views"][OLD], 3)

    def test_invalid_history_counter_is_rejected(self):
        for value in (-1, "100", True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.monthly({OLD: 5}, [row("2026-10-01T09:00:00+09:00", {OLD: value})])


class CollectionTest(unittest.TestCase):
    def collect(self, responses, previous):
        with patch.object(cv, "load_slugs", return_value=list(responses)), \
             patch.object(cv, "last_snapshot", return_value=previous), \
             patch.object(cv, "fetch", side_effect=responses.values()), \
             patch.object(cv.time, "sleep"):
            return cv.collect()

    def test_http_error_and_disappeared_counter_keep_previous_values(self):
        for status in ("http500", "http403", "ratelimited", "new"):
            with self.subTest(status=status):
                views, stats = self.collect({OLD: (0, status), NEW: (3, "ok")}, {OLD: 100})
                self.assertEqual(views, {OLD: 100, NEW: 3})
                self.assertEqual(stats["kept"], 1)

    def test_empty_index_refuses_to_overwrite_snapshot(self):
        with self.assertRaises(RuntimeError):
            self.collect({}, {OLD: 100})

    def test_total_failure_refuses_to_refresh_timestamp(self):
        with self.assertRaises(RuntimeError):
            self.collect({OLD: (0, "http500")}, {OLD: 100})

    def test_first_visit_counter_can_still_be_zero(self):
        views, stats = self.collect({NEW: (0, "new")}, {})
        self.assertEqual(views[NEW], 0)
        self.assertEqual(stats["new"], 1)

    def test_invalid_api_payload_is_not_a_successful_zero(self):
        for value in (None, "3", -1, True):
            with self.subTest(value=value), \
                 patch.object(cv.urllib.request, "urlopen") as urlopen, \
                 patch.object(cv.time, "sleep"):
                urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({"value": value}).encode()
                _, status = cv.fetch(OLD)
                self.assertNotEqual(status, "ok")

    def test_damaged_snapshot_stops_before_partial_api_results_can_overwrite_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "views.json"
            for damaged in ('{"views":', '{"views": []}', '{"views":{"old":-1}}', '{}'):
                with self.subTest(damaged=damaged):
                    snapshot.write_text(damaged)
                    with patch.object(cv, "SNAPSHOT", snapshot), \
                         patch.object(cv, "load_slugs", return_value=[OLD, NEW]), \
                         patch.object(cv, "fetch", side_effect=[(0, "http500"), (2, "ok")]) as fetch:
                        with self.assertRaises(RuntimeError):
                            cv.collect()
                        fetch.assert_not_called()
                    self.assertEqual(snapshot.read_text(), damaged)

    def test_failed_atomic_replace_keeps_previous_snapshot_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "views.json"
            snapshot.write_text('{"views":{"old":100}}')
            before = snapshot.read_bytes()
            with patch.object(cv, "SNAPSHOT", snapshot), \
                 patch.object(cv.os, "replace", side_effect=OSError("교체 실패")):
                with self.assertRaises(OSError):
                    cv.save_snapshot({"views": {OLD: 200}})
            self.assertEqual(snapshot.read_bytes(), before)
            self.assertEqual(list(Path(tmp).iterdir()), [snapshot])

    def test_rebuild_preserves_collection_timestamp_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, history = Path(tmp) / "views.json", Path(tmp) / "history.jsonl"
            payload = {"updated": "2026-10-09T09:00:00+09:00", "total": 105, "views": {OLD: 100, NEW: 5}}
            snapshot.write_text(json.dumps(payload))
            history.write_text(json.dumps(row("2026-09-30T09:00:00+09:00", {OLD: 98})) + "\n")
            before = history.read_bytes()
            with patch.object(cv, "SNAPSHOT", snapshot), patch.object(cv, "HISTORY", history), \
                 patch.object(cv, "fetch", side_effect=AssertionError("API 호출 금지")):
                cv.rebuild(dry_run=True)
                self.assertEqual(json.loads(snapshot.read_text()), payload)
                cv.rebuild()
            result = json.loads(snapshot.read_text())
            self.assertEqual(result["updated"], payload["updated"])
            self.assertEqual(result["views"], payload["views"])
            self.assertEqual(result["monthly"]["views"], {OLD: 2, NEW: 5})
            self.assertEqual(history.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
