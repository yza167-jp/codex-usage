"""Independent project/session rendering without changing accounting or exports."""
import json
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from test_codex_usage import load_module


class ProjectColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def fixture(self, duplicate=False, child=False):
        m = self.m
        now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        ids = ["019ffabc-1234-7000-8000-123456789111",
               "019ffabc-1234-7000-8000-123456789222"]
        projects = ["atomic-cross-modal-transfer", "rl_steer_sae"]
        titles = ["实现Qwen3字典内OMP并进行对照实验", "读取 AGENTS.md 后继续推进"]
        if duplicate:
            projects[1], titles[1] = projects[0], titles[0]
        sessions, index = {}, {}
        for i, sid in enumerate(ids):
            session = m.RawSession(sid, Path(f"synthetic-{i}.jsonl"),
                                   cwd=f"/tmp/{projects[i]}", model_provider="openai")
            session.usage_events = [m.UsageEvent(
                now - timedelta(minutes=i + 1),
                m.Usage(1_000_000, 900_000, 10_000, 2_000, 1_010_000),
                "gpt-6-astra" if i == 0 else "gpt-5.6-sol", "standard")]
            if child and i == 1:
                session.source, session.parent_id = "subagent", ids[0]
                session.usage_events.append(m.UsageEvent(
                    now - timedelta(seconds=30),
                    m.Usage(2_000_000, 1_800_000, 20_000, 4_000, 2_020_000),
                    "gpt-5.6-sol", "standard"))
            sessions[sid] = session
            index[sid] = {"name": titles[i], "title": "模板化指令", "project_name": projects[i]}
        buckets = m.make_buckets(sessions, index, now - timedelta(days=1), now,
                                 timezone.utc, False, now - timedelta(hours=1))
        return buckets, sessions, now, m.QuotaCalibration(100.0, "LOW")

    def render(self, buckets=None, width=144, wide=False, details=False, color="never", **kw):
        bs, sessions, now, cal = self.fixture(**kw)
        if buckets is not None:
            bs = buckets
        with patch.object(self.m.shutil, "get_terminal_size", return_value=os.terminal_size((width, 40))):
            return self.m.render_table(bs, sessions, "last 24h", timezone.utc, False,
                                       details, now, True, self.m.Colorizer(color),
                                       wide=wide, quota_calibration=cal)

    def cells(self, line, width=144, wide=False):
        """Split by terminal cells, not code points, to catch CJK misalignment."""
        _, widths, _, _ = self.m.summary_table_layout(width, wide)
        gap = self.m.summary_column_gap(min(width, 144))
        cells, offset = [], 0
        for w in widths:
            used, text = 0, ""
            for ch in line:
                n = self.m._terminal_char_width(ch)
                if offset <= used < offset + w:
                    text += ch
                used += n
            cells.append(text.strip())
            offset += w + gap
        return cells

    def test_summary_project_and_session_are_separate(self):
        text = self.render()
        header = next(x for x in text.splitlines() if x.startswith("PROJECT"))
        self.assertEqual(self.cells(header)[:3], ["PROJECT", "SESSION", "MODEL(S)"])
        row = next(x for x in text.splitlines() if x.startswith("atomic"))
        cells = self.cells(row)
        self.assertTrue(cells[0].startswith("atomic"))
        self.assertTrue(cells[1].startswith("实现Qwen3字典内OMP"))
        self.assertNotIn("atomic", cells[1])
        self.assertEqual(cells[2], "6 Astra")
        self.assertEqual(self.m.display_width(row), 144)

    def test_wide_keeps_names_and_uses_token_continuations(self):
        normal, wide = self.render(), self.render(wide=True)
        normal_rows = [x for x in normal.splitlines() if x.startswith(("PROJECT", "atomic", "rl_", "TOTAL"))]
        wide_rows = [x for x in wide.splitlines() if x.startswith(("PROJECT", "atomic", "rl_", "TOTAL"))]
        self.assertEqual(normal_rows, wide_rows)
        self.assertEqual(sum(x.startswith("  TOKENS I/C/O  ") for x in wide.splitlines()), 3)
        self.assertIn("1M/900K/10K", wide)

    def test_layouts_fit_narrow_normal_and_fullscreen(self):
        for width in (80, 90, 99, 100, 116, 120, 143, 144, 240):
            for wide in (False, True):
                with self.subTest(width=width, wide=wide):
                    headers, widths, right, inline = self.m.summary_table_layout(width, wide)
                    target = min(width, 144)
                    self.assertEqual(sum(widths) + self.m.summary_column_gap(target) * (len(widths)-1), target)
                    self.assertEqual(headers[:2], ["PROJECT", "SESSION"])
                    self.assertFalse(inline)
                    self.assertEqual(right, {4, 5, 6, 7, 8})
                    text = self.render(width=width, wide=wide)
                    for line in text.splitlines():
                        if line.startswith(("PROJECT", "atomic", "rl_", "TOTAL", "  TOKENS")):
                            self.assertLessEqual(self.m.display_width(line), target)
        self.assertEqual(self.render(width=240, wide=True), self.render(width=144, wide=True))

    def test_natural_bracket_task_tag_is_not_project(self):
        m = self.m
        b = m.Bucket("sid", title="[Review] 检查数据", project_name="research")
        self.assertEqual(m.bucket_identity(b), ("research", "[Review] 检查数据"))
        b.project_name = ""
        self.assertEqual(m.bucket_identity(b), ("", "[Review] 检查数据"))

    def test_exact_project_prefixes_and_internal_mentions(self):
        m = self.m
        for title in ("[demo] 实验", "DEMO: 实验", "demo · 实验"):
            self.assertEqual(m.session_without_project(title, "demo"), "实验")
        self.assertEqual(m.session_without_project("检查 [demo] 和数据", "demo"), "检查 [demo] 和数据")
        self.assertEqual(m.session_without_project("[demo-long] 实验", "demo"), "[demo-long] 实验")

    def test_missing_project_uses_placeholder_not_task_tag(self):
        m = self.m
        b = m.Bucket("unknown-sid", title="[Review] 检查", project_name="")
        b.add("gpt-6-astra", m.Usage(100, 50, 10, 0, 110), b.session_id)
        text = self.render(buckets={b.session_id: b})
        row = next(x for x in text.splitlines() if "[Review] 检查" in x)
        self.assertEqual(self.cells(row)[:2], ["—", "[Review] 检查"])

    def test_unnamed_session_keeps_project_and_uses_short_id(self):
        m = self.m
        sid = "019ffabc-1234-7000-8000-123456789111"
        session = m.RawSession(sid, Path("synthetic.jsonl"), cwd="/tmp/project")
        meta = m.session_label_metadata(session, {})
        self.assertEqual(meta["project_name"], "project")
        b = m.Bucket(sid, title=meta["display_title"], project_name=meta["project_name"])
        self.assertEqual(m.bucket_identity(b), ("project", m.short_sid(sid)))

    def test_windows_cwd_fallback_is_independent_of_host(self):
        m = self.m
        b = m.Bucket("sid", title="[win-project] Task", cwd=r"C:\Users\sample\proj\win-project")
        self.assertEqual(m.bucket_identity(b), ("win-project", "Task"))

    def test_remote_fallback_is_retained_for_unnamed_session(self):
        m = self.m
        s = m.RawSession("sid", Path("synthetic.jsonl"))
        meta = m.session_label_metadata(s, {"sid": {"git_origin_url": "git@example.invalid:team/demo.git"}})
        self.assertEqual(meta["project_name"], "demo")
        b = m.Bucket("sid", title=meta["display_title"], project_name=meta["project_name"])
        self.assertEqual(m.bucket_identity(b), ("demo", "sid"))

    def test_duplicate_markers_survive_project_removal(self):
        buckets, _, _, _ = self.fixture(duplicate=True)
        names = [self.m.bucket_identity(b)[1] for b in buckets.values()]
        self.assertEqual(len(set(names)), 2)
        self.assertTrue(all(name.startswith("#") for name in names))
        self.assertTrue(all("atomic" not in name for name in names))

    def test_orphan_marker_is_not_mistaken_for_project(self):
        m = self.m
        b = m.Bucket("sid", title="[ORPHAN SUB] [demo] #123456 检查", project_name="demo")
        self.assertEqual(m.bucket_identity(b), ("demo", "[ORPHAN SUB] #123456 检查"))

    def test_details_and_agents_separate_actual_source_projects(self):
        text = self.render(details=True, child=True)
        heading = next(x for x in text.splitlines() if x.startswith("DETAILS"))
        self.assertNotIn("atomic", heading)
        self.assertIn("project: atomic-cross-modal-transfer", text)
        agent = text.split("\nAgent breakdown\n", 1)[1]
        self.assertTrue(agent.splitlines()[0].startswith("PROJECT"))
        self.assertIn("rl_steer_sae", agent)
        self.assertNotIn("[rl_steer_sae]", agent)
        self.assertNotIn("[atomic-cross-modal-transfer]", agent)
        for line in agent.splitlines():
            if line.strip():
                self.assertLessEqual(self.m.display_width(line), 144)
        detail_headers = [x for x in text.splitlines() if x.rstrip().endswith("SESSION%")]
        self.assertGreaterEqual(len(detail_headers), 5)
        self.assertTrue(all(self.m.display_width(x) == 144 for x in detail_headers))

    def test_compact_agent_table_preserves_tokens(self):
        for width in (80, 100, 120):
            text = self.render(width=width, details=True, child=True)
            agent = text.split("\nAgent breakdown\n", 1)[1]
            self.assertIn("PROJECT", agent)
            self.assertIn("TOKENS I/C/O", agent)
            for line in agent.splitlines():
                self.assertLessEqual(self.m.display_width(line), width)

    def test_cjk_combining_project_and_color_alignment(self):
        m = self.m
        b = m.Bucket("sid", title="[实验e\u0301] 检查结果", project_name="实验e\u0301")
        b.add("gpt-6-astra", m.Usage(100, 50, 10, 0, 110), "sid")
        args = {"buckets": {"sid": b}, "details": True, "wide": True}
        plain, color = self.render(**args), self.render(color="always", **args)
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", color), plain)
        row = next(x for x in plain.splitlines() if x.startswith("实验"))
        self.assertEqual(self.cells(row)[:2], ["实验e\u0301", "检查结果"])
        self.assertEqual(m.display_width(row), 144)

    def test_existing_exports_and_credits_not_mutated_by_render(self):
        m = self.m
        buckets, sessions, now, cal = self.fixture(child=True)
        args = (buckets, sessions, "last 24h", timezone.utc, False, now, True)
        before = (m.render_json(*args, quota_calibration=cal), m.render_csv(buckets, sessions, False, now, True, quota_calibration=cal))
        amounts = [m.bucket_credits(b, sessions, False) for b in buckets.values()]
        with patch.object(m.shutil, "get_terminal_size", return_value=os.terminal_size((144, 40))):
            m.render_table(buckets, sessions, "last 24h", timezone.utc, False, True, now, True,
                           m.Colorizer("never"), wide=True, quota_calibration=cal)
        after = (m.render_json(*args, quota_calibration=cal), m.render_csv(buckets, sessions, False, now, True, quota_calibration=cal))
        self.assertEqual(before, after)
        self.assertEqual(amounts, [m.bucket_credits(b, sessions, False) for b in buckets.values()])
        data = json.loads(after[0])
        self.assertIn("project_name", data["sessions"][0])
        self.assertEqual(m.CACHE_SCHEMA_VERSION, 3)
        self.assertEqual(m.RATE_CARD_CALIBRATION_KEY, "2026-08-12-r3-tier-aware")

    def test_total_metrics_still_align_to_correct_headers(self):
        m = self.m
        text = self.render(wide=True)
        buckets, sessions, _, _ = self.fixture()
        total_credits = sum(m.bucket_credits(b, sessions, False)[0] for b in buckets.values())
        row = next(x for x in text.splitlines() if x.startswith("TOTAL"))
        cells = self.cells(row)
        self.assertEqual(cells[:4], ["TOTAL", "", "", ""])
        self.assertEqual(cells[6], f"{total_credits:.1f}")
        self.assertEqual(cells[8], "100%")


if __name__ == "__main__":
    unittest.main()
