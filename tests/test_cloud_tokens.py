"""Synthetic backend fixtures only; no live login or Cloud tasks."""
import csv
import io
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from test_codex_usage import load_module


class CloudTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def group(self):
        return dict(model="gpt-6.1-sol", reasoning_effort="xhigh", speed="fast",
                    estimated_usage_credits_micros=2_500_001,
                    input_tokens=100, cached_input_tokens=20, output_tokens=40)

    def report(self, groups=None, credits=2_500_001, v2=None, error=None):
        v2 = v2 if v2 is not None else {"threads": [{"thread_id": "same", "data_status": "available",
            "weekly_limit_percent": 12.5, "balance_usage_credits": 0,
            "groups": [{"model": "gpt-6.1-sol", "reasoning_effort": "xhigh", "speed": "fast",
                        "weekly_limit_percent": 12.5}]}], "comparison_plan": "pro"}
        tokens = {"threads": [{"thread_id": "same", "estimated_usage_credits_micros": credits,
                              "groups": [self.group()] if groups is None else groups}]}
        def request(_home, path, _body):
            if path.endswith("query_v2"):
                return v2
            if error:
                raise error
            return tokens
        with patch.object(self.m, "_cloud_request", side_effect=request) as transport:
            report = self.m.read_cloud_usage(Path("unused"), [{"id": "same", "title": "中文任务"}])
        return report, transport

    def test_official_request_schema_cumulative_tokens_and_credit_micros(self):
        report, calls = self.report()
        row = report["sessions"][0]
        self.assertEqual(calls.call_args_list[1].args[2], {"thread_ids": ["same"]})
        self.assertEqual([row[k] for k in self.m.CLOUD_TOKEN_FIELDS], [100, 20, 80, 40, 140])
        self.assertEqual(row["estimated_usage_credits_micros"], 2_500_001)
        self.assertEqual(row["estimated_credits"], 2.500001)
        self.assertEqual(row["token_data_status"], "available")
        self.assertTrue(report["token_counts_available"])
        self.assertFalse(report["period_attribution_available"])
        self.assertEqual(row["groups"][0]["weekly_limit_percent"], 12.5)

    def test_missing_fields_preserve_known_partial_sums_and_provenance(self):
        a = self.group()
        b = {"model": "gpt-6-luna", "input_tokens": 5, "output_tokens": None}
        row = self.report(groups=[a, b])[0]["sessions"][0]
        self.assertEqual(row["input_tokens"], 105)
        self.assertEqual(row["output_tokens"], 40)
        self.assertTrue(row["token_fields_complete"]["input_tokens"])
        self.assertFalse(row["token_fields_complete"]["output_tokens"])
        self.assertEqual(row["token_data_status"], "partial")
        self.assertEqual(self.m.cloud_token_text(row, "output_tokens"), "40+?")
        self.assertIsNone(row["token_groups"][1]["cached_input_tokens"])
        self.assertIn("total_tokens", row["token_groups"][0]["derived_token_fields"])

    def test_uncached_and_cached_can_derive_input_without_guessing_other_fields(self):
        row = self.report(groups=[{"net_new_input_tokens": 80, "cached_input_tokens": 20}])[0]["sessions"][0]
        self.assertEqual(row["input_tokens"], 100)
        self.assertIsNone(row["total_tokens"])
        self.assertIsNone(row["output_tokens"])

    def test_real_zero_is_available_but_empty_groups_are_unknown(self):
        zero = {key: 0 for key in self.m.CLOUD_TOKEN_FIELDS if key != "uncached_input_tokens"}
        row = self.report(groups=[zero], credits=0)[0]["sessions"][0]
        self.assertEqual(row["token_data_status"], "available")
        self.assertEqual(row["total_tokens"], 0)
        self.assertEqual(row["estimated_credits"], 0)
        row = self.report(groups=[], credits=0)[0]["sessions"][0]
        self.assertIsNone(row["total_tokens"])
        self.assertEqual(row["token_unavailable_reason"], "fields_missing")
        self.assertEqual(row["estimated_credits"], 0)

    def test_invalid_numeric_types_never_become_tokens(self):
        for invalid in (True, -1, 1.5, "123", float("nan"), float("inf")):
            row = self.report(groups=[{"input_tokens": invalid}], credits=invalid)[0]["sessions"][0]
            self.assertIsNone(row["input_tokens"])
            self.assertIsNone(row["estimated_credits"])

    def test_large_token_counters_do_not_round_through_float(self):
        count = 2**53 + 1
        row = self.report(groups=[{"input_tokens": count, "cached_input_tokens": 0, "output_tokens": 0}])[0]["sessions"][0]
        self.assertEqual(row["total_tokens"], count)

    def test_inconsistent_server_counters_are_retained_but_not_complete(self):
        report, _ = self.report(groups=[{"input_tokens": 100, "cached_input_tokens": 120,
                                         "output_tokens": 20, "total_tokens": 10}])
        row = report["sessions"][0]
        self.assertEqual(row["cached_input_tokens"], 120)
        self.assertEqual(row["total_tokens"], 10)
        self.assertIsNone(row["uncached_input_tokens"])
        self.assertFalse(row["token_fields_complete"]["total_tokens"])
        self.assertEqual(row["token_data_status"], "partial")

    def test_access_denied_is_distinct_from_missing_and_zero(self):
        report, _ = self.report(error=self.m.CloudUsageError("denied", http_status=403))
        row = report["sessions"][0]
        self.assertEqual(report["endpoint_errors"]["query"],
                         {"status": "access_denied", "http_status": 403, "message": "denied"})
        self.assertEqual(row["token_unavailable_reason"], "access_denied")
        self.assertIsNone(row["estimated_credits"])
        self.assertEqual(row["weekly_limit_percent"], 12.5)
        self.assertEqual(self.m.cloud_tiers(row), "FAST")

    def test_unsupported_interface_is_classified(self):
        report, _ = self.report(error=self.m.CloudUsageError("unsupported", http_status=404))
        self.assertEqual(report["endpoint_errors"]["query"]["status"], "unsupported")

    def test_one_denial_is_not_retried_for_each_batch(self):
        def request(_home, path, body):
            if path.endswith("/query"):
                raise self.m.CloudUsageError("denied", http_status=403)
            return {"threads": [{"thread_id": t["thread_id"], "data_status": "available"} for t in body["threads"]]}
        with patch.object(self.m, "_cloud_request", side_effect=request) as request_mock:
            report = self.m.read_cloud_usage(Path("unused"), [{"id": str(i)} for i in range(101)])
        self.assertEqual(len(report["sessions"]), 101)
        self.assertEqual(sum(c.args[1].endswith("/query") for c in request_mock.call_args_list), 1)
        self.assertEqual(request_mock.call_count, 4)

    def test_query_metrics_survive_v2_permission_failure(self):
        def request(_home, path, body):
            if path.endswith("query_v2"):
                raise self.m.CloudUsageError("denied", http_status=403)
            return {"threads": [{"thread_id": "same", "estimated_usage_credits_micros": 1,
                                  "groups": [self.group()]}]}
        with patch.object(self.m, "_cloud_request", side_effect=request):
            report = self.m.read_cloud_usage(Path("unused"), [{"id": "same"}])
        row = report["sessions"][0]
        self.assertEqual(row["data_status"], "unavailable")
        self.assertEqual(row["token_data_status"], "available")
        self.assertEqual(self.m.cloud_value(row, "estimated_credits"), 0.000001)
        self.assertIsNone(self.m.cloud_value(row, "weekly_limit_percent"))

    def test_invalid_query_response_does_not_hide_v2_metrics(self):
        def request(_home, path, body):
            if path.endswith("/query"):
                return {"threads": [{"thread_id": "unexpected"}]}
            return {"threads": [{"thread_id": "same", "data_status": "available", "weekly_limit_percent": 3}]}
        with patch.object(self.m, "_cloud_request", side_effect=request):
            report = self.m.read_cloud_usage(Path("unused"), [{"id": "same"}])
        self.assertEqual(report["endpoint_errors"]["query"]["status"], "invalid_response")
        self.assertEqual(report["sessions"][0]["weekly_limit_percent"], 3)

    def test_later_failed_v2_batch_makes_report_freshness_unknown(self):
        batch = 0
        def request(_home, path, body):
            nonlocal batch
            if path.endswith("/query"):
                return {"threads": []}
            batch += 1
            if batch == 2:
                raise self.m.CloudUsageError("denied", http_status=403)
            return {"threads": [{"thread_id": t["thread_id"], "data_status": "available"} for t in body["threads"]],
                    "data_as_of": "2026-10-18T00:00:00Z"}
        with patch.object(self.m, "_cloud_request", side_effect=request):
            report = self.m.read_cloud_usage(Path("unused"), [{"id": str(i)} for i in range(51)])
        self.assertIsNone(report["data_as_of"])
        self.assertEqual(report["sessions"][0]["allowance_data_as_of"], "2026-10-18T00:00:00+00:00")

    def test_same_model_efforts_and_speeds_are_separate_groups(self):
        a = self.group()
        b = dict(a, reasoning_effort="max", speed="standard")
        report, _ = self.report(groups=[a, b])
        row = report["sessions"][0]
        self.assertEqual(row["total_tokens"], 280)
        self.assertEqual(len(row["token_groups"]), 2)
        self.assertEqual(self.m.cloud_tiers(row), "MIXED")

    def test_object_comparison_context_is_supported_without_persisting_raw_metadata(self):
        plan = {"plan_type": "pro", "basis": {"weekly": 100, "five_hour": 20}}
        def comparison_key(context):
            report, _ = self.report(v2={"comparison_plan": context, "threads": [{"thread_id": "same"}]})
            return report["sessions"][0]["comparison_plan"]
        key = comparison_key(plan)
        self.assertTrue(key)
        self.assertEqual(key, comparison_key(dict(reversed(list(plan.items())))))
        self.assertNotEqual(key, comparison_key({"plan_type": "plus"}))
        self.assertNotIn("plan_type", key)

    def test_omitted_rows_and_duplicate_or_unexpected_ids(self):
        with patch.object(self.m, "_cloud_request", return_value={"threads": []}):
            row = self.m.read_cloud_usage(Path("unused"), [{"id": "same"}])["sessions"][0]
        self.assertEqual(row["token_unavailable_reason"], "row_omitted")
        for rows in ([{"thread_id": "other"}], [{"thread_id": "same"}] * 2, [None]):
            with self.subTest(rows=rows), patch.object(self.m, "_cloud_request", return_value={"threads": rows}):
                with self.assertRaises(self.m.CloudUsageError):
                    self.m.read_cloud_usage(Path("unused"), [{"id": "same"}])

    def test_models_effort_fast_and_unknown_speed_render_at_144_cells(self):
        groups = [self.group(), {"model": "gpt-6-astra", "reasoning_effort": "max"}]
        report, _ = self.report(groups=groups)
        self.assertEqual(self.m.cloud_models(report["sessions"][0]), ["gpt-6-astra", "gpt-6.1-sol"])
        self.assertEqual(self.m.cloud_tiers({"groups": [{"model": "gpt-6-astra"}]}), "?")
        for width in (80, 100, 144, 240):
            with patch.object(self.m.shutil, "get_terminal_size", return_value=os.terminal_size((width, 40))):
                text = self.m.render_cloud_usage(report, details=True, wide=True)
            self.assertIn("effort max", text)
            self.assertIn("speed fast", text)
            self.assertIn("EST CREDITS", text)
            for line in text.splitlines():
                self.assertLessEqual(self.m.display_width(line), min(width, 144))

    def test_exports_keep_scope_and_raw_micro_units_separate_from_local(self):
        report, _ = self.report()
        raw = json.loads(self.m.render_cloud_usage(report, "json"))
        self.assertEqual(raw["sessions"][0]["estimated_usage_credits_micros"], 2_500_001)
        local = {"sessions": [{"session_id": "same", "title": "本地", "credit_estimate": 999}]}
        unified = self.m.unified_json_sessions(local, report)
        self.assertEqual(len(unified), 1)
        self.assertEqual(unified[0]["local_usage"]["credit_estimate"], 999)
        self.assertEqual(unified[0]["cloud_usage"]["total_tokens"], 140)
        local_csv = "session_id,title,credit_estimate\nsame,local,999\nother,中文任务,1\n"
        rows = list(csv.DictReader(io.StringIO(self.m.append_cloud_csv(local_csv, report))))
        shared = [r for r in rows if r["session_id"] == "same"]
        self.assertEqual([r["host"] for r in shared], ["local", "cloud"])
        self.assertEqual(shared[1]["credit_estimate"], "")
        self.assertEqual(shared[1]["estimated_usage_credits_micros"], "2500001")
        self.assertEqual(len(rows), 3)
        self.assertEqual(json.loads(shared[1]["token_groups_json"])[0]["speed"], "fast")

    def test_missing_csv_fields_are_blank_and_permission_reason_is_exported(self):
        report, _ = self.report(error=self.m.CloudUsageError("denied", http_status=403))
        row = list(csv.DictReader(io.StringIO(self.m.render_cloud_usage(report, "csv"))))[0]
        self.assertEqual(row["total_tokens"], "")
        self.assertEqual(row["estimated_credits"], "")
        self.assertEqual(row["token_unavailable_reason"], "access_denied")

    def test_http_error_does_not_expose_token_account_or_response(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://chatgpt.com", 403, "Denied", {}, io.BytesIO(b"private-response"))
        with patch.object(self.m, "_cloud_credentials", return_value=("secret-token", "secret-account")), \
             patch.object(self.m.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(self.m.CloudUsageError) as caught:
                self.m._cloud_request(Path("unused"), "/wham/usage/thread_usage/query", {"thread_ids": ["same"]})
        self.assertEqual(caught.exception.http_status, 403)
        for secret in ("secret-token", "secret-account", "private-response"):
            self.assertNotIn(secret, str(caught.exception))


class CloudSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "cloud.sqlite3"
        self.now = datetime(2026, 10, 18, 8, tzinfo=timezone.utc)

    def record(self, value, ts, account="account-a", plan="pro", partial=False, selected=None):
        report = {"sessions": [{"session_id": "same", "title": "must-not-persist",
            "data_status": "available", "weekly_limit_percent": value, "comparison_plan": plan,
            "estimated_usage_credits_micros": value * 1_000_000 if value is not None else None,
            **{key: value for key in self.m.CLOUD_TOKEN_FIELDS},
            "token_fields_complete": {key: not partial for key in self.m.CLOUD_TOKEN_FIELDS}}]}
        self.m.record_cloud_snapshots(report, self.path, account, ts, selected)
        return report

    def metric(self, report, key="total_tokens", window="1h"):
        return report["sessions"][0]["posting_windows"][window]["metrics"][key]

    def test_first_observation_never_turns_lifetime_into_recent_usage(self):
        report = self.record(100, self.now)
        self.assertEqual(report["snapshot_status"], "recorded")
        self.assertFalse(report["posting_deltas_available"])
        for label in ("1h", "12h", "24h", "7d"):
            self.assertIsNone(self.metric(report, window=label)["value"])

    def test_delta_uses_only_observed_coverage_and_all_windows(self):
        self.record(100, self.now - timedelta(minutes=30))
        report = self.record(120, self.now)
        for label in ("1h", "12h", "24h", "7d"):
            metric = self.metric(report, window=label)
            self.assertEqual(metric["value"], 20)
            self.assertEqual(metric["covered_seconds"], 1800)
            self.assertFalse(metric["complete_window"])
        self.assertEqual(self.metric(report, "estimated_usage_credits_micros")["value"], 20_000_000)

    def test_no_proration_of_boundary_crossing_intervals(self):
        self.record(100, self.now - timedelta(hours=2))
        report = self.record(120, self.now)
        self.assertIsNone(self.metric(report)["value"])
        self.assertEqual(self.metric(report, window="12h")["value"], 20)

    def test_exact_boundary_coverage_can_be_complete(self):
        self.record(100, self.now - timedelta(hours=1))
        self.assertTrue(self.metric(self.record(120, self.now))["complete_window"])

    def test_missing_and_partial_measurements_break_continuity(self):
        for missing in (True, False):
            with self.subTest(partial=missing):
                self.record(100, self.now - timedelta(minutes=40), account=str(missing))
                self.record(110 if missing else None, self.now - timedelta(minutes=20), account=str(missing), partial=missing)
                report = self.record(120, self.now, account=str(missing))
                self.assertIsNone(self.metric(report)["value"])
                self.assertTrue(self.metric(report)["discontinuity"])

    def test_decreases_are_unknown_not_zero_and_later_interval_is_retained(self):
        self.record(100, self.now - timedelta(minutes=40))
        report = self.record(80, self.now - timedelta(minutes=20))
        self.assertIsNone(self.metric(report)["value"])
        report = self.record(90, self.now)
        self.assertEqual(self.metric(report)["value"], 10)
        self.assertTrue(self.metric(report)["discontinuity"])
        self.assertEqual(self.metric(report)["covered_seconds"], 1200)

    def test_same_counter_is_known_zero_posting_delta(self):
        self.record(100, self.now - timedelta(minutes=20))
        self.assertEqual(self.metric(self.record(100, self.now))["value"], 0)

    def test_account_isolation_and_changed_plan_percentages(self):
        self.record(100, self.now - timedelta(minutes=20))
        report = self.record(120, self.now, account="account-b")
        self.assertIsNone(self.metric(report)["value"])
        report = self.record(120, self.now, plan="plus")
        self.assertIsNone(self.metric(report, "weekly_limit_percent")["value"])
        self.assertEqual(self.metric(report)["value"], 20)

    def test_historical_selected_window_does_not_use_future_observation(self):
        self.record(100, self.now - timedelta(hours=2))
        self.record(110, self.now - timedelta(hours=1))
        selected = (self.now - timedelta(hours=2), self.now - timedelta(minutes=30))
        report = self.record(150, self.now, selected=selected)
        self.assertEqual(self.metric(report, window="selected_period")["value"], 10)

    def test_selected_window_normalizes_non_utc_timezone_for_storage_lookup(self):
        self.record(100, self.now - timedelta(days=10))
        self.record(110, self.now - timedelta(days=9))
        china = timezone(timedelta(hours=8))
        selected = ((self.now - timedelta(days=10)).astimezone(china),
                    (self.now - timedelta(days=8)).astimezone(china))
        report = self.record(120, self.now, selected=selected)
        self.assertEqual(self.metric(report, window="selected_period")["value"], 10)

    def test_unknown_comparison_plan_does_not_teach_allowance_deltas(self):
        self.record(100, self.now - timedelta(minutes=20), plan=None)
        report = self.record(120, self.now, plan=None)
        self.assertIsNone(self.metric(report, "weekly_limit_percent")["value"])
        self.assertEqual(self.metric(report)["value"], 20)

    def test_minimal_storage_preserves_other_tables_and_history(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("CREATE TABLE unrelated (value TEXT)")
            conn.execute("INSERT INTO unrelated VALUES ('keep')")
            conn.commit()
        self.record(100, self.now - timedelta(days=10))
        self.record(120, self.now)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cloud_counter_snapshots").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT value FROM unrelated").fetchone()[0], "keep")
            for (counters,) in conn.execute("SELECT counters FROM cloud_counter_snapshots"):
                self.assertNotIn("must-not-persist", counters)
                self.assertNotIn("groups", counters)

    def test_repeated_observation_timestamp_is_not_overwritten_or_double_counted(self):
        self.record(100, self.now - timedelta(minutes=20))
        self.record(110, self.now)
        self.record(999, self.now)
        report = self.record(120, self.now + timedelta(minutes=20))
        self.assertEqual(self.metric(report)["value"], 20)
        self.assertEqual(self.metric(report)["intervals"], 2)

    def test_cli_records_scoped_snapshot_without_touching_local_index(self):
        report = {"sessions": [], "data_as_of": None}
        cache = Path(self.tmp.name) / "index.sqlite3"
        with patch.object(self.m, "read_cloud_usage", return_value=report), \
             patch.object(self.m, "_cloud_credentials", return_value=("fake-token", "fake-account")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.main(["cloud", "--cloud-thread", "same", "--json", "--cache-path", str(cache)]), 0)
        self.assertFalse(cache.exists())
        self.assertTrue(cache.with_name("index-cloud.sqlite3").exists())
        self.assertEqual(report["snapshot_status"], "recorded")

    def test_snapshot_storage_error_does_not_hide_lifetime_report(self):
        report = {"sessions": [], "data_as_of": None}
        output = io.StringIO()
        with patch.object(self.m, "read_cloud_usage", return_value=report), \
             patch.object(self.m, "_cloud_credentials", return_value=("fake-token", "fake-account")), \
             patch.object(self.m, "record_cloud_snapshots", side_effect=sqlite3.OperationalError("locked")), \
             redirect_stdout(output):
            self.assertEqual(self.m.main(["cloud", "--cloud-thread", "same", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["snapshot_status"], "storage_unavailable")

    def test_cli_no_cache_never_writes_cloud_snapshots(self):
        report = {"sessions": [], "data_as_of": None}
        with patch.object(self.m, "read_cloud_usage", return_value=report), \
             patch.object(self.m, "record_cloud_snapshots") as record, redirect_stdout(io.StringIO()):
            code = self.m.main(["cloud", "--cloud-thread", "same", "--no-cache", "--json", "--codex-home", self.tmp.name])
        self.assertEqual(code, 0)
        record.assert_not_called()
        self.assertEqual(report["snapshot_status"], "disabled")


if __name__ == "__main__":
    unittest.main()
