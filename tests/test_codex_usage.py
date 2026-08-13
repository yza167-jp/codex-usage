import base64
import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "codex-usage"


def load_module():
    loader = importlib.machinery.SourceFileLoader("codex_usage_module", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


class CodexUsageSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_version(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("1.5.5", proc.stdout)

    def test_terminal_display_width_handles_cjk_and_combining(self):
        self.assertEqual(self.mod.display_width("ASCII"), 5)
        self.assertEqual(self.mod.display_width("中文"), 4)
        self.assertEqual(self.mod.display_width("A中B"), 4)
        self.assertEqual(self.mod.display_width("e\u0301"), 1)
        self.assertEqual(self.mod.display_width("\u200d"), 0)

    def test_terminal_truncate_and_padding_are_cell_aware(self):
        sample = "请先阅读 AGENTS.md、README.md"
        for width in (1, 2, 5, 10, 20, 30):
            clipped = self.mod.truncate(sample, width)
            self.assertLessEqual(self.mod.display_width(clipped), width)

        left = self.mod.pad_display("中文 session", 18)
        right = self.mod.pad_display("中文 session", 18, right=True)
        self.assertEqual(self.mod.display_width(left), 18)
        self.assertEqual(self.mod.display_width(right), 18)
        self.assertTrue(left.startswith("中文"))
        self.assertTrue(right.endswith("session"))

    def test_terminal_rows_do_not_underpad_cjk(self):
        # This is the regression seen in a wide terminal: len("中文") == 2,
        # but it occupies four terminal cells. Padding must use display width.
        cell = self.mod.pad_display("请先阅读 AGENTS.md", 32)
        self.assertEqual(self.mod.display_width(cell), 32)

    def test_report_width_cap_and_detail_right_edges(self):
        self.assertEqual(self.mod.REPORT_MAX_WIDTH, self.mod.display_width(self.mod.STATUS_NOTE))
        self.assertEqual(self.mod.REPORT_MAX_WIDTH, 144)
        cases = (
            ([30, 14, 10], (0,)),
            ([12, 11, 11, 11, 12, 12, 10], (0,)),
            ([20, 10, 10, 10, 10, 11, 11, 9], (0,)),
            ([37, 19, 9, 9, 9, 10, 10, 9], (0, 1)),
        )
        for base, flex in cases:
            widths = self.mod.fit_widths_to_target(base, self.mod.REPORT_MAX_WIDTH, flex)
            rendered = sum(widths) + 2 * (len(widths) - 1)
            self.assertEqual(rendered, self.mod.REPORT_MAX_WIDTH)

        # On a narrower terminal, preserve readable base widths rather than
        # squeezing numeric columns merely to force the wide-screen alignment.
        narrow_base = [37, 19, 9, 9, 9, 10, 10, 9]
        self.assertEqual(
            self.mod.fit_widths_to_target(narrow_base, 100, (0, 1)),
            narrow_base,
        )

    def test_local_auth_plan_decodes_prolite(self):
        claims = {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "prolite",
                "chatgpt_user_id": "test-user",
            }
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        token = f"eyJhbGciOiJub25lIn0.{payload}.sig"
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "auth.json").write_text(json.dumps({
                "auth_mode": "chatgpt",
                "tokens": {
                    "id_token": token,
                    "access_token": "secret",
                    "refresh_token": "secret",
                    "account_id": "acct",
                },
            }), encoding="utf-8")
            ctx = self.mod.read_local_auth_context(home)
            self.assertEqual(ctx.plan_type, "prolite")
            self.assertEqual(self.mod.plan_display_name(ctx.plan_type), "Pro 5x")
            self.assertNotEqual(ctx.account_key, "local")

    def test_v155_plan_seed_keeps_weekly_available_after_reset(self):
        snap = self.mod.QuotaSnapshot(
            datetime.now(timezone.utc), 0.0, 10080, 9999999999, plan_type="prolite"
        )
        auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
        cal = self.mod.bootstrap_quota_calibration(auth, snap)
        self.assertEqual(cal.credits_per_percent, 175.0)
        self.assertEqual(cal.confidence, "SEED")
        self.assertEqual(cal.source, "plan_seed")
        self.assertEqual(self.mod.weekly_percent_text(350.0, cal, True), "2.00%")

    def test_v155_interval_calibration_ignores_dirty_spark_interval(self):
        now = datetime.now(timezone.utc)
        reset = int((now + self.mod.timedelta(days=5)).timestamp())
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            try:
                conn.execute(
                    """
                    INSERT INTO quota_intervals(
                        account_key,plan_type,reset_at,start_ts,end_ts,start_used_percent,
                        end_used_percent,local_credits,complete,rate_card,credit_mode,source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    ("acct", "prolite", reset, now.isoformat(), (now+self.mod.timedelta(seconds=1)).isoformat(),
                     0.0, 1.0, 50.0, 0, self.mod.RATE_CARD_CALIBRATION_KEY, "standard", "snapshot_delta"),
                )
                conn.execute(
                    """
                    INSERT INTO quota_intervals(
                        account_key,plan_type,reset_at,start_ts,end_ts,start_used_percent,
                        end_used_percent,local_credits,complete,rate_card,credit_mode,source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    ("acct", "prolite", reset, (now+self.mod.timedelta(seconds=2)).isoformat(),
                     (now+self.mod.timedelta(seconds=3)).isoformat(), 1.0, 3.0, 360.0, 1,
                     self.mod.RATE_CARD_CALIBRATION_KEY, "standard", "snapshot_delta"),
                )
                conn.commit()
                snap = self.mod.QuotaSnapshot(now+self.mod.timedelta(seconds=4), 3.0, 10080, reset, plan_type="prolite")
                cal = self.mod.load_quota_calibration(conn, auth, snap, None, False)
                self.assertAlmostEqual(cal.credits_per_percent, 180.0, delta=0.01)
                self.assertEqual(cal.source, "delta")
                self.assertEqual(cal.clean_intervals, 1)
            finally:
                conn.close()

    def test_v155_interval_anchor_uses_earliest_previous_plateau(self):
        now = datetime.now(timezone.utc)
        reset = int((now + self.mod.timedelta(days=6)).timestamp())
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            try:
                for offset in (0, 10, 20):
                    snap0 = self.mod.QuotaSnapshot(now+self.mod.timedelta(seconds=offset), 0.0, 10080, reset, plan_type="prolite")
                    self.mod._record_quota_snapshot(conn, auth, snap0, False)
                snap1 = self.mod.QuotaSnapshot(now+self.mod.timedelta(seconds=30), 1.0, 10080, reset, plan_type="prolite")
                anchor = self.mod._quota_interval_anchor(conn, auth, snap1, False)
                self.assertIsNotNone(anchor)
                self.assertEqual(anchor.used_percent, 0.0)
                self.assertEqual(anchor.ts, now)
            finally:
                conn.close()

    def test_v151_official_rate_card_and_spark_unpriced(self):
        self.assertEqual(self.mod.RATE_CARD["gpt-5.6-terra"], (62.5, 6.25, 375.0))
        self.assertEqual(self.mod.RATE_CARD["gpt-5.6-luna"], (25.0, 2.5, 150.0))
        self.assertEqual(self.mod.RATE_CARD["gpt-5.3-codex"], (43.75, 4.375, 350.0))
        self.assertEqual(self.mod.RATE_CARD["gpt-5.2"], (43.75, 4.375, 350.0))
        self.assertNotIn("gpt-5.3-codex-spark", self.mod.RATE_CARD)

    def test_partial_weekly_estimate_is_lower_bound(self):
        cal = self.mod.QuotaCalibration(credits_per_percent=172.3, confidence="LOW")
        exact = self.mod.weekly_percent_text(543.1, cal, True)
        partial = self.mod.weekly_percent_text(543.1, cal, False)
        self.assertFalse(exact.startswith("≥"))
        self.assertTrue(partial.startswith("≥"))
        self.assertEqual(partial[1:], exact)

    def test_legacy_rate_totals_are_not_used_directly(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            reset = int(now.timestamp()) + 3 * 86400
            try:
                conn.execute(
                    """
                    INSERT INTO quota_observations(
                        account_key,plan_type,reset_at,window_minutes,snapshot_ts,
                        used_percent,local_credits,rate_card,credit_mode,source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    ("acct", "prolite", reset, 10080, now.isoformat(), 92.0, 15851.6, "2026-08-12", "standard", "rollout"),
                )
                conn.commit()
                snap = self.mod.QuotaSnapshot(now, 97.0, 10080, reset, plan_type="prolite")
                cal = self.mod.load_quota_calibration(conn, auth, snap, None, False)
                self.assertIsNone(cal.credits_per_percent)
                self.assertEqual(cal.confidence, "LEARNING")
            finally:
                conn.close()

    def test_legacy_anchor_rebases_under_current_rate_card(self):
        now = datetime.now(timezone.utc)
        reset = int((now + self.mod.timedelta(days=5)).timestamp())
        window_start = datetime.fromtimestamp(reset, tz=timezone.utc) - self.mod.timedelta(minutes=10080)
        anchor_ts = now - self.mod.timedelta(hours=1)
        sid = "019ffabc-1234-7000-8000-123456789abc"
        session = self.mod.RawSession(
            session_id=sid,
            path=Path("synthetic.jsonl"),
            created_at=window_start,
            model_provider="openai",
            usage_events=[
                self.mod.UsageEvent(
                    ts=anchor_ts - self.mod.timedelta(minutes=1),
                    model="gpt-5.6-luna",
                    cumulative=self.mod.Usage(
                        input_tokens=1_000_000,
                        cached_input_tokens=800_000,
                        output_tokens=100_000,
                        reasoning_output_tokens=0,
                        total_tokens=1_100_000,
                    ),
                )
            ],
        )
        sessions = {sid: session}
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            try:
                # Old Luna card would have valued this at 4.4 credits; current
                # v1.5.1+ card values the same token history at 22 credits.
                conn.execute(
                    """
                    INSERT INTO quota_observations(
                        account_key,plan_type,reset_at,window_minutes,snapshot_ts,
                        used_percent,local_credits,rate_card,credit_mode,source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    ("acct", "prolite", reset, 10080, anchor_ts.isoformat(), 10.0, 4.4, "2026-08-12", "standard", "rollout"),
                )
                conn.commit()
                snap = self.mod.QuotaSnapshot(now, 20.0, 10080, reset, plan_type="prolite")
                rebased = self.mod._try_rebase_legacy_observation(
                    conn, auth, snap, sessions, {}, timezone.utc, False
                )
                self.assertIsNotNone(rebased)
                cal = self.mod.load_quota_calibration(conn, auth, snap, None, False)
                self.assertAlmostEqual(cal.credits_per_percent, 2.2, delta=0.01)
                self.assertEqual(cal.source, "rebased_baseline")
                self.assertEqual(cal.confidence, "LOW")
                stored = conn.execute(
                    "SELECT local_credits,source,rate_card FROM quota_observations WHERE rate_card=?",
                    (self.mod.RATE_CARD_CALIBRATION_KEY,),
                ).fetchone()
                self.assertIsNotNone(stored)
                self.assertAlmostEqual(float(stored["local_credits"]), 22.0, delta=0.01)
                self.assertEqual(stored["source"], "rebased")
            finally:
                conn.close()

    def test_rebase_skips_anchor_with_unpriced_history(self):
        now = datetime.now(timezone.utc)
        reset = int((now + self.mod.timedelta(days=5)).timestamp())
        window_start = datetime.fromtimestamp(reset, tz=timezone.utc) - self.mod.timedelta(minutes=10080)
        anchor_ts = now - self.mod.timedelta(hours=1)
        sid = "019ffabc-1234-7000-8000-123456789abd"
        session = self.mod.RawSession(
            session_id=sid,
            path=Path("synthetic-spark.jsonl"),
            created_at=window_start,
            model_provider="openai",
            usage_events=[
                self.mod.UsageEvent(
                    ts=anchor_ts - self.mod.timedelta(minutes=1),
                    model="gpt-5.3-codex-spark",
                    cumulative=self.mod.Usage(input_tokens=1000, total_tokens=1000),
                )
            ],
        )
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            try:
                conn.execute(
                    """
                    INSERT INTO quota_observations(
                        account_key,plan_type,reset_at,window_minutes,snapshot_ts,
                        used_percent,local_credits,rate_card,credit_mode,source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    ("acct", "prolite", reset, 10080, anchor_ts.isoformat(), 10.0, 100.0, "2026-08-12", "standard", "rollout"),
                )
                conn.commit()
                snap = self.mod.QuotaSnapshot(now, 20.0, 10080, reset, plan_type="prolite")
                rebased = self.mod._try_rebase_legacy_observation(
                    conn, auth, snap, {sid: session}, {}, timezone.utc, False
                )
                self.assertIsNone(rebased)
                cal = self.mod.load_quota_calibration(conn, auth, snap, None, False)
                self.assertIsNone(cal.credits_per_percent)
                self.assertEqual(cal.confidence, "LEARNING")
            finally:
                conn.close()

    def test_weekly_rate_limit_snapshot_prefers_seven_day_window(self):
        now = datetime.now(timezone.utc)
        rec = {
            "timestamp": now.isoformat(),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "plan_type": "prolite",
                    "primary": {"used_percent": 12.0, "window_minutes": 300, "resets_at": int(now.timestamp()) + 1000},
                    "secondary": {"used_percent": 37.5, "window_minutes": 10080, "resets_at": int(now.timestamp()) + 3 * 86400},
                },
            },
        }
        snap = self.mod._quota_snapshot_from_record(rec, "plus")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.plan_type, "prolite")
        self.assertEqual(snap.window_minutes, 10080)
        self.assertEqual(snap.used_percent, 37.5)

    def test_quota_calibration_learns_delta_ratio(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            conn = self.mod._cache_connect(Path(td) / "index.sqlite3")
            auth = self.mod.LocalAuthContext(plan_type="prolite", account_key="acct")
            reset = int(now.timestamp()) + 3 * 86400
            try:
                samples = [
                    (now, 20.0, 8000.0),
                    (now + self.mod.timedelta(seconds=1), 22.0, 8800.0),
                    (now + self.mod.timedelta(seconds=2), 25.0, 10000.0),
                ]
                for ts, used, credits in samples:
                    snap = self.mod.QuotaSnapshot(ts, used, 10080, reset, plan_type="prolite")
                    self.mod._record_quota_observation(conn, auth, snap, credits, False)
                latest = self.mod.QuotaSnapshot(samples[-1][0], 25.0, 10080, reset, plan_type="prolite")
                cal = self.mod.load_quota_calibration(conn, auth, latest, 10000.0, False)
                self.assertAlmostEqual(cal.credits_per_percent, 400.0, delta=1.0)
                self.assertGreaterEqual(cal.clean_intervals, 2)
                self.assertIn(cal.confidence, ("MEDIUM", "HIGH"))
            finally:
                conn.close()

    def test_sqlite_i64_handles_unsigned_windows_file_ids(self):
        self.assertEqual(self.mod._sqlite_i64(0), 0)
        self.assertEqual(self.mod._sqlite_i64((1 << 63) - 1), (1 << 63) - 1)
        self.assertEqual(self.mod._sqlite_i64(1 << 63), -(1 << 63))
        self.assertEqual(self.mod._sqlite_i64((1 << 64) - 1), -1)

    def test_sqlite_read_only_uri(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "state with spaces.sqlite"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE t(x INTEGER)")
            conn.execute("INSERT INTO t VALUES(7)")
            conn.commit()
            conn.close()

            uri = self.mod._sqlite_ro_uri(db)
            ro = sqlite3.connect(uri, uri=True)
            try:
                self.assertEqual(ro.execute("SELECT x FROM t").fetchone()[0], 7)
            finally:
                ro.close()

    def test_default_cache_path_matches_platform(self):
        cache = self.mod.default_cache_path()
        self.assertEqual(cache.name, "index-v2.sqlite3")
        if os.name == "nt":
            expected_base = os.environ.get("LOCALAPPDATA")
            if expected_base:
                self.assertTrue(str(cache).lower().startswith(str(Path(expected_base)).lower()))
        elif sys.platform == "darwin":
            self.assertIn("Library", cache.parts)
            self.assertIn("Caches", cache.parts)
        else:
            self.assertIn("codex-usage", cache.parts)

    def test_synthetic_rollout_no_cache_and_cached(self):
        sid = "019ffabc-1234-7000-8000-123456789abc"
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".codex"
            day = datetime.now(timezone.utc)
            session_dir = home / "sessions" / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
            session_dir.mkdir(parents=True)
            rollout = session_dir / f"rollout-{sid}.jsonl"
            records = [
                {
                    "timestamp": ts,
                    "type": "session_meta",
                    "payload": {
                        "id": sid,
                        "cwd": str(Path(td) / "demo-project"),
                        "source": "cli",
                        "model_provider": "openai",
                        "created_at": ts,
                    },
                },
                {
                    "timestamp": ts,
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.6-sol"},
                },
                {
                    "timestamp": ts,
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 10000,
                                "cached_input_tokens": 8000,
                                "output_tokens": 500,
                                "reasoning_output_tokens": 100,
                                "total_tokens": 10500,
                            }
                        },
                        "rate_limits": {
                            "limit_id": "codex",
                            "plan_type": "prolite",
                            "primary": {
                                "used_percent": 5.0,
                                "window_minutes": 300,
                                "resets_at": int(datetime.now(timezone.utc).timestamp()) + 3600,
                            },
                            "secondary": {
                                "used_percent": 25.0,
                                "window_minutes": 10080,
                                "resets_at": int(datetime.now(timezone.utc).timestamp()) + 3 * 86400,
                            },
                        },
                    },
                },
            ]
            rollout.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            claims = {"https://api.openai.com/auth": {"chatgpt_plan_type": "prolite", "chatgpt_user_id": "integration-user"}}
            payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            id_token = f"eyJhbGciOiJub25lIn0.{payload}.sig"
            (home / "auth.json").write_text(json.dumps({
                "auth_mode": "chatgpt",
                "tokens": {"id_token": id_token, "access_token": "secret", "refresh_token": "secret", "account_id": "acct"},
            }), encoding="utf-8")

            base_cmd = [
                sys.executable,
                str(SCRIPT),
                "24h",
                "--codex-home",
                str(home),
                "--color",
                "never",
            ]
            legacy_env = os.environ.copy()
            legacy_env["PYTHONIOENCODING"] = "cp1252"
            no_cache = subprocess.run(
                base_cmd + ["--no-cache"],
                check=True,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=legacy_env,
            )
            self.assertIn("demo-project", no_cache.stdout)
            self.assertIn("5.6 Sol", no_cache.stdout)

            cache_db = Path(td) / "cache" / "index.sqlite3"
            cached = subprocess.run(
                base_cmd + ["--cache-path", str(cache_db)],
                check=True,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=legacy_env,
            )
            self.assertIn("demo-project", cached.stdout)
            self.assertIn("Subscription", cached.stdout)
            self.assertIn("WEEKLY", cached.stdout)
            self.assertTrue(cache_db.exists())


if __name__ == "__main__":
    unittest.main()
