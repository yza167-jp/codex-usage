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
        self.assertIn("1.4.0", proc.stdout)

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
