"""Regressions for full model labels without sacrificing the SESSION column."""
import json
import os
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from test_codex_usage import load_module


class ModelDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_single_model_stays_inline(self):
        for model, label in (("gpt-6-astra", "6 Astra"), ("gpt-5.6-sol", "5.6 Sol")):
            self.assertEqual(self.m.model_cell_layout([model], 12, 144), (label, []))

    def test_fitting_multiple_models_stay_inline(self):
        models = ["gpt-5.6-sol", "gpt-6-astra"]
        self.assertEqual(self.m.model_cell_layout(models, 19, 144),
                         ("5.6 Sol / 6 Astra", []))

    def test_overflow_lists_all_models_in_continuation(self):
        cell, notes = self.m.model_cell_layout(["gpt-5.6-sol", "gpt-6-astra"], 12, 144)
        self.assertEqual(cell, "5.6 Sol +1")
        self.assertEqual(notes, ["  Models: 5.6 Sol / 6 Astra"])
        self.assertNotIn("…", cell + "".join(notes))

    def test_count_is_models_not_service_tiers(self):
        keys = [self.m.usage_key("gpt-5.6-sol", t) for t in ("fast", "standard", "unknown")]
        keys += [self.m.usage_key("gpt-6-astra", "standard")]
        self.assertEqual(self.m.model_cell_layout(iter(keys), 12, 144),
                         ("5.6 Sol +1", ["  Models: 5.6 Sol / 6 Astra"]))

    def test_narrow_column_uses_count_not_half_a_model(self):
        cell, notes = self.m.model_cell_layout(
            ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-6-astra"], 8, 80)
        self.assertEqual(cell, "3 models")
        self.assertEqual(notes, ["  Models: 5.6 Sol / 5.6 Luna / 6 Astra"])

    def test_long_unknown_identifier_remains_complete(self):
        model = "unpriced-model-" + "x" * 200 + "-final-suffix"
        cell, notes = self.m.model_cell_layout([model], 12, 80)
        self.assertEqual(cell, "1 model")
        self.assertGreater(len(notes), 1)
        self.assertEqual("".join(line[10:] for line in notes), model)
        self.assertTrue(all(self.m.display_width(line) <= 80 for line in notes))

    def test_many_models_wrap_without_loss(self):
        models = ["gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-luna"]
        models += [f"unknown-model-{i:02d}" for i in range(24)]
        for width in (80, 100, 116, 144):
            with self.subTest(width=width):
                cell, notes = self.m.model_cell_layout(models, 12, width)
                self.assertEqual(cell, "5.6 Sol +26")
                actual = "".join("".join(line[10:].split()) for line in notes)
                self.assertEqual(actual, "".join(self.m.model_label(models).split()))
                self.assertTrue(all(self.m.display_width(line) <= width for line in notes))

    def test_cjk_and_combining_marks_wrap_in_cells(self):
        model = "未定价模型-" + "中e\u0301" * 60 + "-末尾"
        cell, notes = self.m.model_cell_layout([model], 12, 80)
        self.assertEqual(cell, "1 model")
        self.assertEqual("".join(line[10:] for line in notes), model)
        for line in notes:
            self.assertLessEqual(self.m.display_width(line), 80)
            self.assertNotEqual(line[10:11], "\u0301")

    def fixture(self, long_model=False):
        m = self.m
        now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        sid = "019ffabc-1234-7000-8000-123456789111"
        b = m.Bucket(sid, title="[sample-project] 中文多模型实验")
        models = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-6-astra"]
        if long_model:
            models.append("unknown-model-with-a-very-long-identifier-and-unique-suffix")
        for model in models:
            b.add(model, m.Usage(1_000_000, 900_000, 10_000, 2_000, 1_010_000),
                  sid, source_title=b.title, activity_ts=now, recent=True)
        s = m.RawSession(sid, Path("synthetic.jsonl"), model_provider="openai")
        return {sid: b}, {sid: s}, now, m.QuotaCalibration(100.0, "LOW")

    def render(self, width=144, wide=True, details=False, color="never", long_model=False):
        b, sessions, now, cal = self.fixture(long_model)
        with patch.object(self.m.shutil, "get_terminal_size", return_value=os.terminal_size((width, 40))):
            return self.m.render_table(b, sessions, "last 24h", timezone.utc, False,
                                       details, now, True, self.m.Colorizer(color),
                                       wide=wide, quota_calibration=cal)

    def test_wide_render_preserves_width_and_full_models(self):
        text = self.render()
        rows = text.splitlines()
        header = next(line for line in rows if line.startswith("SESSION"))
        self.assertEqual(self.m.display_width(header.split("MODEL(S)")[0]), 36)
        main = next(line for line in rows if line.startswith("[sample-project]"))
        self.assertEqual(self.m.display_width(main), 144)
        self.assertIn("5.6 Sol +2", main)
        self.assertIn("  Models: 5.6 Sol / 5.6 Luna / 6 Astra", rows)
        total = next(line for line in rows if line.startswith("TOTAL"))
        self.assertIn("100%", total)
        self.assertEqual(sum(line.startswith("TOTAL") for line in rows), 1)

    def test_default_and_narrow_wide_both_show_complete_models(self):
        for width, wide in ((100, False), (100, True), (116, True), (144, False)):
            with self.subTest(width=width, wide=wide):
                text = self.render(width=width, wide=wide)
                self.assertIn("  Models: 5.6 Sol / 5.6 Luna / 6 Astra", text)
                self.assertNotIn("5.6 Sol / 5…", text)
                if wide and width == 100:
                    self.assertIn("  TOKENS I/C/O", text)
                for line in text.splitlines():
                    if line.startswith("  Models:"):
                        self.assertLessEqual(self.m.display_width(line), width)

    def test_details_agent_and_long_model_are_not_ellipsized(self):
        text = self.render(details=True, long_model=True)
        model_section = text.split("\nModel breakdown\n", 1)[1].split("\nAgent breakdown\n", 1)[0]
        agent_section = text.split("\nAgent breakdown\n", 1)[1]
        long_id = "unknown-model-with-a-very-long-identifier-and-unique-suffix"
        self.assertIn("  Models: " + long_id, model_section)
        self.assertIn("  Models: 5.6 Sol / 5.6 Luna / 6 Astra / " + long_id, agent_section)
        for line in text.splitlines():
            self.assertLessEqual(self.m.display_width(line), 144)

    def test_color_does_not_change_wrapping(self):
        plain = self.render(details=True, long_model=True)
        colored = self.render(color="always", details=True, long_model=True)
        self.assertIn("\033[", colored)
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", colored), plain)

    def test_fullscreen_does_not_expand_report(self):
        self.assertEqual(self.render(width=240), self.render(width=144))

    def test_rendering_leaves_accounting_and_exports_unchanged(self):
        m = self.m
        buckets, sessions, now, cal = self.fixture()
        before = m.render_json(buckets, sessions, "24h", timezone.utc, False, now, True,
                               quota_calibration=cal)
        with patch.object(m.shutil, "get_terminal_size", return_value=os.terminal_size((144, 40))):
            text = m.render_table(buckets, sessions, "24h", timezone.utc, False, True,
                                  now, True, m.Colorizer("never"), wide=True, quota_calibration=cal)
        after = m.render_json(buckets, sessions, "24h", timezone.utc, False, now, True,
                              quota_calibration=cal)
        self.assertEqual(json.loads(before), json.loads(after))
        self.assertIn("Models:", text)
        self.assertEqual(m.model_label(["gpt-5.6-sol", "gpt-6-astra"]), "5.6 Sol / 6 Astra")


if __name__ == "__main__":
    unittest.main()
