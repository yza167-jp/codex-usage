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
        self.assertIn("1.4.3", proc.stdout)

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
            session_dir = home / "sessions" / "2099" / "01" / "01"
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
                    },
                },
            ]
            rollout.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

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
            self.assertTrue(cache_db.exists())


if __name__ == "__main__":
    unittest.main()
