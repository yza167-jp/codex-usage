"""Sanitized, synthetic quota regression fixtures; no real account/transcript data."""
import csv
import importlib.machinery
import importlib.util
import io
import json
import math
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
loader = importlib.machinery.SourceFileLoader("quota_v180_test_module", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
loader.exec_module(m)


class QuotaReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.conn = m._cache_connect(self.home / "index.sqlite3")
        self.start = datetime(2026, 9, 10, 14, 25, 18, tzinfo=timezone.utc)
        self.reset = int((self.start + timedelta(days=7)).timestamp())
        self.auth = m.LocalAuthContext(plan_type="pro", account_key="synthetic-account")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def snap(self, hours, used, **kwargs):
        values = dict(ts=self.start + timedelta(hours=hours), used_percent=used,
                      window_minutes=10080, resets_at=self.reset, plan_type="pro")
        values.update(kwargs)
        return m.QuotaSnapshot(**values)

    def session(self, costs, tier="unknown", model="gpt-5.6-luna", sid="synthetic"):
        cumulative = 0
        events = []
        # Synthetic usage is uncached input only, to set exact reference costs.
        rate = m.RATE_CARD.get(model, (25, 2.5, 150))[0]
        for hours, cost in costs:
            cumulative += round(cost / rate * 1e6)
            events.append(m.UsageEvent(self.start + timedelta(hours=hours),
                                      m.Usage(input_tokens=cumulative, total_tokens=cumulative), model, tier))
        return m.RawSession(sid, Path(sid + ".jsonl"), created_at=self.start,
                            model_provider="openai", usage_events=events)

    def fit(self, sessions, points):
        end = points[-1]
        timeline = m.QuotaTimeline(sessions, self.start, end.ts, False)
        samples, warnings = m.build_quota_samples(points, timeline)
        quality = timeline.between(self.start, end.ts, include_start=True)
        cal = m.load_quota_calibration(self.conn, self.auth, end, None, False,
                                      samples=samples, current_quality=quality,
                                      regime_changed=bool(warnings))
        return cal, samples, quality

    def seed_old_intervals(self):
        old_reset = int((self.start - timedelta(days=3)).timestamp())
        for day, cost in ((11, 264.253), (6, 339.477)):
            a = self.snap(-24 * day, 9, resets_at=old_reset)
            b = self.snap(-24 * day + 1, 10, resets_at=old_reset)
            m._record_quota_interval(self.conn, self.auth, a, b, cost, True, False)

    def test_audit_regression_new_assumed_evidence_replaces_two_old_one_pp_samples(self):
        self.seed_old_intervals()
        # The aggregate magnitudes reproduce the reported failure, with
        # independently generated timestamps and token histories.
        costs = [(1, 3050), (3, 33987.1 - 3050 - 6065.692 - 4273.683),
                 (10, 6065.692), (14, 4273.683), (19, 1200.835)]
        s = self.session(costs)
        points = [self.snap(8, 43), self.snap(12, 54), self.snap(12.1, 54),
                  self.snap(16, 62), self.snap(16.01, 62), self.snap(16.02, 62),
                  self.snap(16.03, 62), self.snap(20, 64)]
        cal, samples, quality = self.fit({s.session_id: s}, points)
        expected = (6065.692 + 4273.683 + 1200.835) / 21
        self.assertAlmostEqual(cal.credits_per_percent, expected, places=4)
        self.assertGreater(cal.credits_per_percent, 500)
        self.assertLess(cal.credits_per_percent, 620)
        self.assertEqual((cal.clean_intervals, cal.assumed_intervals), (0, 3))
        self.assertEqual(cal.observed_percent_points, 21)
        self.assertEqual((cal.source, cal.confidence), ("current_assumed", "LOW"))
        self.assertEqual(len(samples), 3)
        self.assertLess(30937.1 / cal.credits_per_percent, 62)
        # Critically NOT forced equal to the backend by renormalizing the total.
        self.assertNotAlmostEqual(quality.credits / cal.credits_per_percent, 64, places=3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quota_intervals").fetchone()[0], 2)

    def test_repeated_plateaus_do_not_increase_sample_count_or_movement(self):
        s = self.session([(0.5, 1000), (2, 1000)])
        sparse = [self.snap(0, 0), self.snap(1, 2), self.snap(3, 4)]
        dense = sparse[:2] + [self.snap(1 + n / 100, 2) for n in range(1, 80)] + sparse[2:]
        a, sa, _ = self.fit({s.session_id: s}, sparse)
        b, sb, _ = self.fit({s.session_id: s}, dense)
        self.assertEqual(len(sa), len(sb))
        self.assertEqual(a.credits_per_percent, b.credits_per_percent)
        self.assertEqual(a.observed_percent_points, b.observed_percent_points)

    def test_endpoint_tokens_belong_to_one_interval_only(self):
        s = self.session([(0, 5), (1, 1000), (2, 1200)], tier="standard")
        t = m.QuotaTimeline({s.session_id: s}, self.start, self.snap(2, 4).ts, False)
        first = t.between(self.start, self.snap(1, 2).ts)
        second = t.between(self.snap(1, 2).ts, self.snap(2, 4).ts)
        self.assertEqual((first.credits, second.credits), (1000, 1200))
        self.assertEqual(t.between(self.start, self.snap(2, 4).ts, True).credits, 2205)

    def test_one_point_jumps_wait_until_two_pp(self):
        s = self.session([(0.5, 500), (1.5, 500)])
        cal, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(1, 1), self.snap(2, 2)])
        self.assertEqual(len(samples), 1)
        self.assertEqual(cal.observed_percent_points, 2)
        self.assertEqual(cal.confidence, "LOW")

    def test_spark_blocks_only_its_interval(self):
        s = self.session([(0.5, 50)], model="gpt-5.3-codex-spark", sid="spark")
        a = self.session([(2, 1100)], tier="standard", sid="known")
        cal, samples, _ = self.fit({s.session_id: s, a.session_id: a},
                                  [self.snap(0, 0), self.snap(1, 2), self.snap(3, 4)])
        self.assertEqual([s.usage.quality for s in samples], ["excluded", "complete"])
        self.assertEqual(cal.credits_per_percent, 550)
        self.assertEqual(cal.excluded_intervals, 1)

    def test_flex_is_excluded_not_assumed_standard_for_learning(self):
        s = self.session([(1, 1100)], tier="flex")
        cal, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(2, 2)])
        self.assertEqual(samples[0].usage.quality, "excluded")
        self.assertIsNone(cal.credits_per_percent)

    def test_unknown_tier_can_teach_without_becoming_complete(self):
        s = self.session([(1, 1100)])
        cal, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(2, 2)])
        self.assertEqual(samples[0].usage.quality, "assumed_tier")
        self.assertEqual(cal.credits_per_percent, 550)
        self.assertEqual(cal.clean_intervals, 0)

    def test_unknown_fast_uses_same_assumption_in_cost_and_calibration(self):
        s = self.session([(1, 1100)])
        t = m.QuotaTimeline({s.session_id: s}, self.start, self.snap(2, 2).ts, True)
        samples, _ = m.build_quota_samples([self.snap(0, 0), self.snap(2, 2)], t)
        cal = m.load_quota_calibration(self.conn, self.auth, self.snap(2, 2), None, True, samples=samples)
        self.assertEqual(cal.credits_per_percent, 550 * 2.5)
        self.assertEqual(cal.confidence, "LOW")
        self.assertEqual(samples[0].usage.quality, "assumed_tier")

    def test_unsupported_fast_model_is_not_complete(self):
        s = self.session([(1, 1100)], tier="fast", model="gpt-5.3-codex")
        _, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(2, 2)])
        self.assertEqual(samples[0].usage.quality, "excluded")

    def test_non_openai_provider_does_not_calibrate_subscription(self):
        s = self.session([(1, 1100)], tier="standard")
        s.model_provider = "third_party"
        _, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(2, 2)])
        self.assertEqual(samples[0].usage.quality, "excluded")

    def test_malformed_history_is_not_independently_validated(self):
        s = self.session([(1, 1100)], tier="standard")
        s.malformed_lines = 1
        _, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 0), self.snap(2, 2)])
        self.assertEqual(samples[0].usage.quality, "excluded")

    def test_zero_local_usage_cannot_teach_scale(self):
        cal, _, _ = self.fit({}, [self.snap(0, 0), self.snap(2, 10)])
        self.assertIsNone(cal.credits_per_percent)
        self.assertEqual(cal.excluded_intervals, 1)

    def test_used_percent_drop_discards_previous_regime(self):
        s = self.session([(1, 1000), (5, 3000)])
        cal, samples, _ = self.fit({s.session_id: s},
                                  [self.snap(0, 0), self.snap(2, 2), self.snap(4, 0), self.snap(6, 5)])
        self.assertEqual(len(samples), 1)
        self.assertEqual(cal.credits_per_percent, 600)
        self.assertIn("QUOTA_REGIME_CHANGED", cal.warnings)
        self.assertNotIn("CALIBRATION_MISMATCH", cal.warnings)

    def test_reset_boundary_never_creates_negative_or_cross_week_sample(self):
        s = self.session([(3, 1000)])
        points = [self.snap(0, 80, resets_at=self.reset - 3600), self.snap(1, 81, resets_at=self.reset - 3600),
                  self.snap(2, 0), self.snap(4, 2)]
        cal, samples, _ = self.fit({s.session_id: s}, points)
        self.assertEqual(len(samples), 1)
        self.assertEqual(cal.credits_per_percent, 500)

    def test_100_percent_endpoint_is_censored(self):
        s = self.session([(1, 1100), (3, 20000)])
        cal, samples, _ = self.fit({s.session_id: s}, [self.snap(0, 96), self.snap(2, 98), self.snap(4, 100)])
        self.assertEqual(len(samples), 1)
        self.assertEqual(cal.credits_per_percent, 550)

    def test_first_observation_baseline_is_labeled_reconciliation(self):
        s = self.session([(1, 33987.1)])
        cal, samples, quality = self.fit({s.session_id: s}, [self.snap(20, 62)])
        self.assertEqual(samples, [])
        self.assertAlmostEqual(cal.credits_per_percent, 33987.1 / 62, places=4)
        self.assertEqual(cal.source, "current_baseline_assumed")
        self.assertIsNone(cal.local_coverage_percent)
        self.assertEqual(cal.clean_intervals, 0)

    def test_seed_survives_fresh_zero_reset(self):
        cal, _, _ = self.fit({}, [self.snap(0, 0)])
        self.assertIsNone(cal.credits_per_percent)
        seed = m.bootstrap_quota_calibration(self.auth, self.snap(0, 0))
        self.assertEqual((seed.credits_per_percent, seed.confidence), (700, "SEED"))

    def test_mismatch_warning_does_not_clip_or_rewrite_estimates(self):
        s = self.session([(0.1, 10000), (2, 1000)], tier="standard")
        cal, samples, _ = self.fit({s.session_id: s}, [self.snap(1, 10), self.snap(3, 12)])
        self.assertEqual(cal.credits_per_percent, 500)
        self.assertIn("CALIBRATION_MISMATCH", cal.warnings)
        self.assertEqual(cal.comparison_local_percent, 22)
        self.assertEqual(m.weekly_percent_text(100000, cal), "200.0%")

    def test_assumed_samples_can_never_give_high_confidence(self):
        s = self.session([(i + 0.5, 2500) for i in range(6)])
        cal, _, _ = self.fit({s.session_id: s}, [self.snap(i, 5 * i) for i in range(7)])
        self.assertEqual(cal.assumed_intervals, 6)
        self.assertEqual(cal.confidence, "LOW")

    def test_well_spaced_complete_samples_can_gain_confidence(self):
        s = self.session([(i + 0.5, 2500) for i in range(6)], tier="standard")
        cal, _, _ = self.fit({s.session_id: s}, [self.snap(i, 5 * i) for i in range(7)])
        self.assertEqual(cal.clean_intervals, 6)
        self.assertEqual(cal.confidence, "HIGH")

    def test_one_large_outlier_is_explicitly_excluded(self):
        s = self.session([(0.5, 1000), (1.5, 1000), (2.5, 100000)], tier="standard")
        cal, _, _ = self.fit({s.session_id: s}, [self.snap(i, 2 * i) for i in range(4)])
        self.assertEqual(cal.credits_per_percent, 500)
        self.assertEqual(cal.excluded_intervals, 1)

    def test_legacy_snapshot_import_ignores_wrong_account_plan_mode_window_and_future(self):
        for snapshot, auth, fast in (
            (self.snap(1, 2), self.auth, False),
            (self.snap(2, 3), m.LocalAuthContext("pro", "other"), False),
            (self.snap(3, 4, plan_type="prolite"), self.auth, False),
            (self.snap(4, 5), self.auth, True),
            (self.snap(5, 6, window_minutes=300), self.auth, False),
            (self.snap(100, 50), self.auth, False),
        ):
            m._record_quota_snapshot(self.conn, auth, snapshot, fast)
        points = m.quota_snapshot_points(self.conn, self.auth, self.snap(6, 10), False)
        self.assertEqual([p.used_percent for p in points], [2, 10])

    def test_other_pool_is_not_merged_with_codex(self):
        m._record_quota_snapshot(self.conn, self.auth, self.snap(1, 40, limit_id="spark"), False)
        points = m.quota_snapshot_points(self.conn, self.auth, self.snap(2, 2), False)
        self.assertEqual([p.used_percent for p in points], [2])

    def test_derived_table_rebuild_preserves_all_legacy_records(self):
        self.seed_old_intervals()
        s = self.session([(1, 1000)])
        points = [self.snap(0, 0), self.snap(2, 2)]
        for p in points:
            m._record_quota_snapshot(self.conn, self.auth, p, False)
        _, samples, _ = self.fit({s.session_id: s}, points)
        for _ in range(2):
            m.save_quota_samples(self.conn, self.auth, points[-1], False, samples)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quota_samples_v180").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quota_intervals").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quota_snapshots").fetchone()[0], 2)
        self.assertEqual(m.CACHE_SCHEMA_VERSION, 3)

    def test_imported_overlapping_intervals_do_not_double_count(self):
        a = m.QuotaSample(self.snap(0, 0).ts, self.snap(2, 8).ts, 0, 8, m.QuotaUsage(4000))
        b = m.QuotaSample(a.start_ts, self.snap(2.1, 8).ts, 0, 8, m.QuotaUsage(4100))
        c = m.QuotaSample(a.end_ts, self.snap(3, 10).ts, 8, 10, m.QuotaUsage(1000))
        cal = m.load_quota_calibration(self.conn, self.auth, self.snap(3, 10), None, False, samples=[a, b, c])
        self.assertEqual(cal.observed_percent_points, 10)
        self.assertEqual(cal.clean_intervals, 2)

    def test_future_samples_are_not_accepted(self):
        sample = m.QuotaSample(self.snap(0, 0).ts, self.snap(10, 10).ts, 0, 10, m.QuotaUsage(5000))
        cal = m.load_quota_calibration(self.conn, self.auth, self.snap(2, 2), None, False, samples=[sample])
        self.assertIsNone(cal.credits_per_percent)

    def test_previous_policy_values_are_not_promoted_to_new_samples(self):
        self.seed_old_intervals()
        cal = m.load_quota_calibration(self.conn, self.auth, self.snap(20, 64), None, False, samples=[])
        self.assertIsNone(cal.credits_per_percent)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quota_samples_v180").fetchone()[0], 0)

    def test_recent_new_policy_prior_is_low_and_expires(self):
        s = self.session([(1, 1000)])
        points = [self.snap(0, 0), self.snap(2, 2)]
        _, samples, _ = self.fit({s.session_id: s}, points)
        m.save_quota_samples(self.conn, self.auth, points[-1], False, samples)
        end = self.snap(24, 0, resets_at=self.reset + 86400)
        cal = m.load_quota_calibration(self.conn, self.auth, end, None, False, samples=[])
        self.assertEqual(cal.source, "historical_prior")
        self.assertEqual((cal.credits_per_percent, cal.clean_intervals), (500, 0))
        later = self.snap(24 * 9, 0, resets_at=self.reset + 9 * 86400)
        expired = m.load_quota_calibration(self.conn, self.auth, later, None, False, samples=[])
        self.assertIsNone(expired.credits_per_percent)

    def test_historical_prior_does_not_reintroduce_rejected_outliers(self):
        s = self.session([(0.5, 1000), (1.5, 1000), (2.5, 100000)], tier="standard")
        points = [self.snap(i, 2 * i) for i in range(4)]
        cal, samples, _ = self.fit({s.session_id: s}, points)
        m.save_quota_samples(self.conn, self.auth, points[-1], False, samples)
        new_epoch = self.snap(24, 0, resets_at=self.reset + 86400)
        prior = m.load_quota_calibration(self.conn, self.auth, new_epoch, None, False, samples=[])
        self.assertEqual(prior.credits_per_percent, 500)
        self.assertEqual(prior.confidence, "LOW")

    def test_all_weekly_renderers_drop_mathematical_lower_bound_claim(self):
        s = self.session([(1, 1000)])
        buckets = m.make_buckets({s.session_id: s}, {}, self.start, self.snap(4, 3).ts,
                                 timezone.utc, False, trend_start=self.start)
        cal = m.QuotaCalibration(500, "LOW", source="current_assumed", assumed_intervals=1)
        document = json.loads(m.render_json(buckets, {s.session_id: s}, "test", timezone.utc,
                                          False, self.snap(4, 3).ts, True, quota_calibration=cal))
        row = document["sessions"][0]
        for child in [row] + row["model_breakdown"] + row["tier_breakdown"] + row["agent_breakdown"]:
            self.assertFalse(child["weekly_estimate_is_lower_bound"])
            self.assertTrue(child["weekly_estimate_is_partial"])
        text = m.render_table(buckets, {s.session_id: s}, "test", timezone.utc, False, True,
                              self.snap(4, 3).ts, True, m.Colorizer("never"), quota_calibration=cal)
        self.assertNotIn("≥", text)
        self.assertIn("~2.00%", text)
        rows = list(csv.DictReader(io.StringIO(m.render_csv(buckets, {s.session_id: s}, False,
                                                          self.snap(4, 3).ts, True, quota_calibration=cal))))
        self.assertEqual(rows[0]["weekly_estimate_is_lower_bound"], "0")
        self.assertEqual(rows[0]["weekly_estimate_is_partial"], "1")
        self.assertEqual(float(rows[0]["credit_estimate"]), 1000)

    def test_table_discloses_conflict_without_obscuring_numbers(self):
        cal = m.QuotaCalibration(264.253, "LOW", source="current_assumed", assumed_intervals=2,
                                comparison_local_percent=128.6, warnings=["CALIBRATION_MISMATCH"])
        s = self.session([(1, 33987.1)])
        buckets = m.make_buckets({s.session_id: s}, {}, self.start, self.snap(20, 62).ts, timezone.utc, False)
        with patch.object(m.shutil, "get_terminal_size", return_value=os.terminal_size((240, 40))):
            text = m.render_table(buckets, {s.session_id: s}, "18h", timezone.utc, False, False,
                                  self.snap(20, 62).ts, True, m.Colorizer("never"),
                                  quota_snapshot=self.snap(20, 62), quota_calibration=cal,
                                  quota_local_credits=33987.1, quota_local_complete=False)
        self.assertIn("CALIBRATION MISMATCH", text)
        self.assertIn("128.6%", text)
        self.assertIn("62.0%", text)
        self.assertIn("0 complete + 2 assumed", text)
        self.assertLessEqual(max(m.display_width(line) for line in text.splitlines()), 144)

class QuotaUpgradeIntegrationTests(unittest.TestCase):
    def make_fixture(self, home):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(hours=20)
        reset = int((start + timedelta(days=7)).timestamp())
        cache = home / "index.sqlite3"
        auth = m.LocalAuthContext("pro", "local")
        conn = m._cache_connect(cache)
        def snap(h, used, reset_at=reset):
            return m.QuotaSnapshot(start + timedelta(hours=h), used, 10080, reset_at, plan_type="pro")
        # These are old-format rows, not new-policy samples. Tier incomplete
        # flags cannot be promoted without replaying cached model/tier events.
        for h, used in [(8, 43), (12, 54), (12.1, 54), (16, 62), (16.01, 62), (16.02, 62)]:
            p = snap(h, used)
            conn.execute("INSERT INTO quota_snapshots VALUES(?,?,?,?,?,?,?,?)",
                         ("local", "pro", reset, 10080, p.ts.isoformat(), used, "tier_auto", "rollout"))
        for h, cost in [(-240, 264.253), (-120, 339.477)]:
            m._record_quota_interval(conn, auth, snap(h, 9, reset-7*86400), snap(h+1, 10, reset-7*86400), cost, True, False)
        for end_h in (16, 16.01, 16.02):
            m._record_quota_interval(conn, auth, snap(12, 54), snap(end_h, 62), 4273.683, False, False)
        conn.commit()
        conn.close()
        sid = "00000000-1111-7000-8000-000000000001"
        path = home / "sessions" / now.strftime("%Y/%m/%d") / ("rollout-" + sid + ".jsonl")
        path.parent.mkdir(parents=True)
        records = [
            {"timestamp": start.isoformat(), "type": "session_meta", "payload": {"id": sid, "model_provider": "openai", "cwd": "/synthetic/project"}},
            {"timestamp": start.isoformat(), "type": "turn_context", "payload": {"model": "gpt-5.6-luna"}},
        ]
        cumulative = 0
        for hour, cost in [(1, 3050), (3, 33987.1 - 3050 - 6065.692 - 4273.683),
                           (10, 6065.692), (14, 4273.683), (19, 1200.835)]:
            cumulative += round(cost / 25 * 1e6)
            records.append({"timestamp": (start + timedelta(hours=hour)).isoformat(),
                            "type": "event_msg", "payload": {"type": "token_count", "info": {
                                "total_token_usage": {"input_tokens": cumulative, "total_tokens": cumulative}}}})
        records.append({"timestamp": now.isoformat(), "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"input_tokens": cumulative, "total_tokens": cumulative}},
            "rate_limits": {"limit_id": "codex", "plan_type": "pro", "secondary": {
                "used_percent": 64, "window_minutes": 10080, "resets_at": reset}}}})
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return cache

    def run_cli(self, home, cache, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "18h", "--codex-home", str(home),
                               "--cache-path", str(cache), *extra], text=True, encoding="utf-8",
                              capture_output=True, check=True)

    def test_upgrade_replays_old_raw_snapshots_without_accepting_incomplete_interval_flags(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = self.make_fixture(home)
            doc = json.loads(self.run_cli(home, cache, "--json").stdout)
            sub = doc["subscription"]
            self.assertAlmostEqual(sub["credits_per_weekly_percent"], 549.5338095238095, places=5)
            self.assertEqual(sub["calibration_source"], "current_assumed")
            self.assertEqual(sub["calibration_clean_intervals"], 0)
            self.assertEqual(sub["calibration_assumed_intervals"], 3)
            self.assertEqual(sub["calibration_observed_percent_points"], 21)
            self.assertLess(doc["sessions"][0]["weekly_estimate_percent"], 64)
            with sqlite3.connect(cache) as con:
                # Three incomplete old rows plus two original complete rows.
                self.assertEqual(con.execute("SELECT COUNT(*) FROM quota_intervals").fetchone()[0], 5)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM quota_samples_v180").fetchone()[0], 3)

    def test_repeated_cli_queries_reuse_index_and_do_not_inflate_samples(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = self.make_fixture(home)
            first = json.loads(self.run_cli(home, cache, "--json").stdout)
            second_result = self.run_cli(home, cache, "--json", "--perf")
            second = json.loads(second_result.stdout)
            self.assertEqual(first["subscription"], second["subscription"])
            self.assertEqual(first["sessions"][0]["credit_estimate"], second["sessions"][0]["credit_estimate"])
            self.assertIn("cold=0", second_result.stderr)
            self.assertIn("tail=0", second_result.stderr)
            self.assertIn("read=0.0 MiB", second_result.stderr)

    def test_no_cache_path_matches_incremental_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = self.make_fixture(home)
            cached = json.loads(self.run_cli(home, cache, "--json").stdout)
            fresh = json.loads(self.run_cli(home, cache, "--json", "--no-cache").stdout)
            self.assertEqual(cached["subscription"], fresh["subscription"])
            self.assertEqual(cached["sessions"][0]["credit_estimate"], fresh["sessions"][0]["credit_estimate"])

    def test_normal_wide_details_and_csv_all_use_the_same_scale(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = self.make_fixture(home)
            doc = json.loads(self.run_cli(home, cache, "--json").stdout)
            expected = doc["sessions"][0]["weekly_estimate_percent"]
            csv_row = next(csv.DictReader(io.StringIO(self.run_cli(home, cache, "--csv").stdout)))
            self.assertAlmostEqual(float(csv_row["weekly_estimate_percent"]), expected, places=5)
            self.assertEqual(csv_row["weekly_estimate_is_lower_bound"], "0")
            text = self.run_cli(home, cache, "--wide", "--details", "--color", "never").stdout
            self.assertIn(f"~{expected:.1f}%", text)
            self.assertIn("current week", text)
            self.assertIn("0 complete + 3 assumed", text)
            self.assertNotIn("≥", text)
            self.assertNotIn("264.3", text)

    def test_no_quota_disables_calibration_without_changing_credit_estimate(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cache = self.make_fixture(home)
            standard = json.loads(self.run_cli(home, cache, "--json").stdout)
            off = json.loads(self.run_cli(home, cache, "--json", "--no-quota").stdout)
            self.assertIsNone(off["sessions"][0]["weekly_estimate_percent"])
            self.assertEqual(standard["sessions"][0]["credit_estimate"], off["sessions"][0]["credit_estimate"])


if __name__ == "__main__":
    unittest.main()
