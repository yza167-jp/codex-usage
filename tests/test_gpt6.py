"""GPT-6 accounting regressions. All transcripts/accounts below are synthetic."""
import csv
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "codex-usage"


class GPT6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("codex_usage_gpt6_tests", str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.m
        loader.exec_module(cls.m)

    def usage(self):
        return self.m.Usage(input_tokens=1_000_000, cached_input_tokens=800_000,
                            output_tokens=100_000, reasoning_output_tokens=40_000,
                            total_tokens=1_100_000)

    def test_canonical_shorthand_and_dated_ids(self):
        # Shorthands are tool aliases, not claims about API model availability.
        for model in ("gpt-6-astra", " GPT-6-ASTRA ", "gpt-6", "gpt6",
                      "gpt-6-astra-2026-09-03", "openai.gpt-6-astra"):
            with self.subTest(model=model):
                self.assertEqual(self.m.normalize_model(model), "gpt-6-astra")
                self.assertEqual(self.m.pretty_model(model), "6 Astra")
                key = self.m.usage_key(model, "priority")
                self.assertEqual(self.m.split_usage_key(key), ("gpt-6-astra", "fast"))
        self.assertEqual(self.m.model_label(["gpt-6", "gpt-6-astra"]), "6 Astra")

    def test_other_gpt6_variants_are_not_silently_priced_as_astra(self):
        for model in ("gpt-6-pro", "gpt-6-astra-pro", "gpt-6-mini", "gpt-6.1",
                      "gpt-6-astra-preview", "gpt-6-astra-wm", "gpt-60",
                      "gpt-6-astra-2026-09-03-pro"):
            with self.subTest(model=model):
                self.assertEqual(self.m.normalize_model(model), model)
                key = self.m.usage_key(model, "standard")
                self.assertEqual(self.m._credit_for_usage_with_completeness(
                    key, self.usage(), False), (None, False))
        self.assertEqual(self.m.pretty_model("gpt-6-astra-wm"), "6 Astra WM")

    def test_standard_cached_input_and_reasoning_not_double_counted(self):
        key = self.m.usage_key("gpt-6-astra", "standard")
        # 0.2M * 250 + 0.8M * 25 + 0.1M * 1250 = 195 credits.
        self.assertEqual(self.m._credit_for_usage_with_completeness(
            key, self.usage(), False), (195.0, True))
        self.assertEqual(self.m.credit_components_for_usage(key, self.usage(), False),
                         (50.0, 20.0, 125.0))
        self.assertEqual(self.m.credit_for_usage(key, self.usage(), True), 195.0)

    def test_fast_uses_codex_multiplier_not_api_multiplier(self):
        for tier in ("fast", "priority"):
            key = self.m.usage_key("gpt-6-astra", tier)
            self.assertEqual(self.m._credit_for_usage_with_completeness(
                key, self.usage(), False), (487.5, True))
            self.assertEqual(self.m.credit_components_for_usage(key, self.usage(), False),
                             (125.0, 50.0, 312.5))

    def test_unknown_tier_and_flex_remain_marked_incomplete(self):
        key = self.m.usage_key("gpt-6-astra", "unknown")
        self.assertEqual(self.m._credit_for_usage_with_completeness(
            key, self.usage(), False), (195.0, False))
        self.assertEqual(self.m._credit_for_usage_with_completeness(
            key, self.usage(), True), (487.5, True))
        self.assertFalse(self.m._credit_for_usage_with_completeness(
            self.m.usage_key("gpt-6-astra", "flex"), self.usage(), False)[1])

    def test_codex_does_not_apply_api_long_context_or_cache_write_fees(self):
        # Large input by itself must not activate the API's >272K surcharge.
        u = self.m.Usage.from_dict(dict(input_tokens=500_000, cached_input_tokens=300_000,
                                       output_tokens=20_000, cache_write_tokens=100_000))
        expected = 50.0 + 7.5 + 25.0
        key = self.m.usage_key("gpt-6-astra", "standard")
        self.assertEqual(self.m.credit_for_usage(key, u, False), expected)

    def write_rollout(self, home, now, model="gpt-6-astra", tier="default"):
        folder = home / "sessions" / now.strftime("%Y/%m/%d")
        folder.mkdir(parents=True, exist_ok=True)
        sid = "019ffabc-1234-7000-8000-123456789170"
        path = folder / ("rollout-" + sid + ".jsonl")
        def record(offset, kind, payload):
            return dict(timestamp=(now + timedelta(seconds=offset)).isoformat(),
                        type=kind, payload=payload)
        records = [
            record(-180, "session_meta", dict(id=sid, model_provider="openai", cwd="/tmp/demo-project")),
            record(-175, "turn_context", dict(model=model, service_tier=tier)),
            record(-170, "event_msg", dict(type="token_count", info=dict(total_token_usage=self.usage().__dict__))),
            record(-150, "event_msg", dict(type="thread_settings_applied", thread_settings=dict(model=model, service_tier="priority"))),
            record(-140, "event_msg", dict(type="token_count", info=dict(total_token_usage=(self.usage()+self.usage()).__dict__))),
        ]
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path, sid

    def test_rollout_switches_standard_to_fast_per_token_delta(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            path, sid = self.write_rollout(Path(td), now)
            session = self.m.parse_rollout(path)
            deltas = self.m.compute_deltas(session, {sid: session})
            self.assertEqual([row[2] for row in deltas], ["standard", "fast"])
            buckets = self.m.make_buckets({sid: session}, {}, now-timedelta(hours=1), now,
                                          timezone.utc, False, now-timedelta(hours=1))
            self.assertEqual(self.m.bucket_credits(buckets[sid], {sid: session}, False),
                             (682.5, True))

    def test_mixed_models_subagents_totals_json_csv_and_weekly(self):
        m = self.m
        now = datetime.now(timezone.utc)
        sid, child_id = "root-gpt6", "child-gpt5"
        root = m.RawSession(sid, Path("root.jsonl"), created_at=now-timedelta(minutes=6),
                            usage_events=[
                                m.UsageEvent(now-timedelta(minutes=5), self.usage(), "gpt-6-astra", "standard"),
                                m.UsageEvent(now-timedelta(minutes=4), self.usage()+self.usage(), "gpt-6-astra", "fast")])
        child_usage = self.usage()+self.usage()+m.Usage(input_tokens=1_000_000, total_tokens=1_000_000)
        child = m.RawSession(child_id, Path("child.jsonl"), created_at=now-timedelta(minutes=3),
                             parent_id=sid, source="subagent", usage_events=[
                                 m.UsageEvent(now-timedelta(minutes=2), child_usage, "gpt-5.6-sol", "standard")])
        sessions = {sid: root, child_id: child}
        index = {sid: {"name": "GPT6 integration test", "project_name": "demo-project"}}
        buckets = m.make_buckets(sessions, index, now-timedelta(hours=1), now, timezone.utc,
                                 False, now-timedelta(hours=1))
        self.assertEqual(len(buckets), 1)
        b = buckets[sid]
        self.assertEqual(m.bucket_collection_credits(buckets, sessions, False), (807.5, True))
        main, sub = m.main_sub_maps(b)
        self.assertEqual(m.model_map_credits(main, False), (682.5, True))
        self.assertEqual(m.model_map_credits(sub, False), (125.0, True))
        # Synthetic scale, not an official weekly quota size.
        cal = m.QuotaCalibration(credits_per_percent=100.0, confidence="LOW", source="baseline")
        doc = json.loads(m.render_json(buckets, sessions, "test", timezone.utc, False,
                                      now, True, quota_calibration=cal))
        row = doc["sessions"][0]
        self.assertEqual(row["weekly_estimate_percent"], 8.075)
        self.assertEqual(row["trailing_1h_weekly_estimate_percent"], 8.075)
        self.assertEqual(row["subagent_credit_estimate"], 125.0)
        self.assertFalse(row["weekly_estimate_is_lower_bound"])
        self.assertEqual({r["service_tier"] for r in row["model_breakdown"]
                          if r["model"] == "gpt-6-astra"}, {"standard", "fast"})
        csv_row = list(csv.DictReader(io.StringIO(m.render_csv(buckets, sessions, False,
                                 now, True, quota_calibration=cal))))[0]
        self.assertIn("gpt-6-astra", csv_row["models"])
        self.assertAlmostEqual(float(csv_row["weekly_estimate_percent"]), 8.075)
        with patch.object(m.shutil, "get_terminal_size", return_value=os.terminal_size((144, 40))):
            table = m.render_table(buckets, sessions, "test", timezone.utc, False, True,
                                  now, True, m.Colorizer("never"), wide=True, quota_calibration=cal)
        self.assertIn("6 Astra", table)
        self.assertIn("TOTAL", table)
        self.assertIn("8.07%", table)
        self.assertIn("TOKENS I/C/O", table)
        self.assertIn("Service tier breakdown", table)
        self.assertIn("GPT-6 2026-09-05", table)

    def test_cached_previously_unpriced_gpt6_needs_no_rebuild(self):
        m = self.m
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path, sid = self.write_rollout(home, now)
            cache = home / "cache.sqlite3"
            conn = m._cache_connect(cache)
            try:
                old_rates = {k: v for k, v in m.RATE_CARD.items() if k != "gpt-6-astra"}
                with patch.dict(m.RATE_CARD, old_rates, clear=True):
                    m.sync_incremental_cache(conn, [path], now-timedelta(hours=1), now, False)
                    old_sessions = m._load_sessions_from_cache(conn, {str(path)})
                    old = m.make_buckets(old_sessions, {}, now-timedelta(hours=1), now, timezone.utc, False)
                    self.assertEqual(m.bucket_collection_credits(old, old_sessions, False), (None, False))
                before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            finally:
                conn.close()
            conn = m._cache_connect(cache)
            try:
                stats = m.sync_incremental_cache(conn, [path], now-timedelta(hours=1), now, False)
                self.assertEqual(stats.bytes_read, 0)
                self.assertEqual(stats.cold_scans, 0)
                self.assertEqual(stats.cache_hits, 1)
                sessions = m._load_sessions_from_cache(conn, {str(path)})
                buckets = m.make_buckets(sessions, {}, now-timedelta(hours=1), now, timezone.utc, False)
                self.assertEqual(m.bucket_collection_credits(buckets, sessions, False), (682.5, True))
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)
            finally:
                conn.close()

    def test_existing_calibration_is_preserved_and_gpt6_can_teach_new_interval(self):
        m = self.m
        now = datetime.now(timezone.utc)
        auth = m.LocalAuthContext(plan_type="pro", account_key="synthetic-account")
        reset = int((now+timedelta(days=4)).timestamp())
        snapshots = [m.QuotaSnapshot(now+timedelta(seconds=i*60), 20.0+2*i, 10080, reset,
                                     plan_type="pro") for i in range(3)]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cache.sqlite3"
            conn = m._cache_connect(path)
            try:
                self.assertEqual(m.CACHE_SCHEMA_VERSION, 3)
                self.assertEqual(m.RATE_CARD_CALIBRATION_KEY, "2026-08-12-r3-tier-aware")
                m._record_quota_interval(conn, auth, snapshots[0], snapshots[1], 682.5, True, False)
                # Incomplete old intervals must never become clean merely because a rate is added.
                m._record_quota_interval(conn, auth, snapshots[0], snapshots[2], 1.0, False, False)
            finally:
                conn.close()
            conn = m._cache_connect(path)
            try:
                cal = m.load_quota_calibration(conn, auth, snapshots[1], None, False)
                self.assertEqual(cal.credits_per_percent, 341.25)
                new_credits = sum(m.credit_for_usage(m.usage_key("gpt-6-astra", tier), self.usage(), False)
                                  for tier in ("standard", "fast"))
                m._record_quota_interval(conn, auth, snapshots[1], snapshots[2], new_credits, True, False)
                cal = m.load_quota_calibration(conn, auth, snapshots[2], None, False)
                self.assertEqual(cal.credits_per_percent, 341.25)
                self.assertEqual(cal.clean_intervals, 2)
                self.assertEqual(cal.source, "delta")
                self.assertEqual(cal.confidence, "MEDIUM")
            finally:
                conn.close()

    def test_cli_exports_and_zero_quota_reset_seed(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path, _ = self.write_rollout(home, now)
            records = [json.loads(line) for line in path.read_text().splitlines()]
            records[-1]["payload"]["rate_limits"] = {
                "limit_id": "codex", "plan_type": "pro", "secondary": {
                    "used_percent": 0.0, "window_minutes": 10080,
                    "resets_at": int((now+timedelta(days=6)).timestamp())}}
            path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
            args = [sys.executable, str(SCRIPT), "24h", "--codex-home", str(home),
                    "--cache-path", str(home / "cli-cache.sqlite3"), "--timezone", "UTC"]
            for extra in ([], ["--no-cache"]):
                result = subprocess.run(args + ["--json"] + extra, text=True,
                                        capture_output=True, check=True, encoding="utf-8")
                doc = json.loads(result.stdout)
                self.assertEqual(doc["sessions"][0]["credit_estimate"], 682.5)
                self.assertEqual(doc["subscription"]["weekly_used_percent"], 0.0)
                self.assertEqual(doc["subscription"]["calibration_confidence"], "SEED")
                self.assertAlmostEqual(doc["sessions"][0]["weekly_estimate_percent"], 682.5/700)
            result = subprocess.run(args + ["--csv"], text=True, capture_output=True,
                                    check=True, encoding="utf-8")
            row = list(csv.DictReader(io.StringIO(result.stdout)))[0]
            self.assertEqual(float(row["credit_estimate"]), 682.5)


if __name__ == "__main__":
    unittest.main()
