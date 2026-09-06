"""Model presentation follows unit price, not chronology or accumulated spend."""
import csv
import io
import itertools
import json
import os
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from test_codex_usage import load_module


class ModelPriceOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def test_order_is_independent_of_insertion(self):
        expected = ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
        for order in itertools.permutations(expected):
            self.assertEqual(self.m.model_names(iter(order)), expected)

    def test_aliases_and_tiers_are_deduplicated_before_ordering(self):
        m = self.m
        keys = ["gpt-5.6-sol", "gpt6", "openai.gpt-6-astra", "gpt-6-astra-2026-09-03",
                m.usage_key("gpt-6", "fast"), m.usage_key("gpt-5.6-sol", "unknown")]
        self.assertEqual(m.model_names(keys), ["gpt-6-astra", "gpt-5.6-sol"])
        self.assertEqual(m.model_cell_layout(keys, 12, 144),
                         ("6 Astra +1", ["  Models: 6 Astra / 5.6 Sol"]))

    def test_empty_and_single_model(self):
        self.assertEqual(self.m.model_names([]), [])
        self.assertEqual(self.m.model_label([]), "?")
        self.assertEqual(self.m.model_cell_layout(["gpt-6-astra"], 12, 144), ("6 Astra", []))

    def test_equal_rates_have_deterministic_id_tiebreak(self):
        models = ["gpt-5.6-sol", "gpt-5.5", "gpt-5.6"]
        self.assertEqual(self.m.model_names(models), sorted(models))
        self.assertEqual(self.m.model_names(reversed(models)), sorted(models))

    def test_unit_price_key_uses_input_then_output_then_cache(self):
        rates = {"a": (100., 10., 500.), "b": (100., 11., 500.),
                 "c": (100., 1., 600.), "d": (101., 0., 0.)}
        with patch.dict(self.m.RATE_CARD, rates, clear=True):
            self.assertEqual(self.m.model_names(["a", "b", "c", "d"]), ["d", "c", "b", "a"])

    def test_price_is_not_model_generation_or_capability(self):
        self.assertEqual(self.m.model_names(["gpt-6-astra", "gpt-5.5-cyber"]),
                         ["gpt-5.5-cyber", "gpt-6-astra"])

    def test_unpriced_models_stay_visible_last_and_unpriced(self):
        m = self.m
        unknown = ["gpt-6-astra-wm", "gpt-99-preview", "gpt-5.3-codex-spark"]
        self.assertEqual(m.model_names(unknown + ["gpt-5.6-luna", "gpt-6-astra"]),
                         ["gpt-6-astra", "gpt-5.6-luna"] + sorted(unknown))
        for model in unknown:
            self.assertEqual(m.credit_for_usage(model, m.Usage(input_tokens=1_000_000), False), None)
        label = m.model_label(unknown + ["gpt-6-astra"])
        self.assertTrue(label.startswith("6 Astra / "))
        self.assertIn("6 Astra WM", label)
        self.assertIn("5.3 Spark", label)

    def test_fast_does_not_promote_cheaper_model(self):
        m = self.m
        keys = [m.usage_key("gpt-5.6-sol", "fast"), m.usage_key("gpt-6-astra", "standard")]
        self.assertEqual(m.model_names(keys), ["gpt-6-astra", "gpt-5.6-sol"])

    def test_tiers_grouped_per_model_with_fast_before_standard(self):
        m = self.m
        keys = [m.usage_key(model, tier) for model in ("gpt-5.6-sol", "gpt-6-astra")
                for tier in ("unknown", "standard", "flex", "fast")]
        expected = [(model, tier) for model in ("gpt-6-astra", "gpt-5.6-sol")
                    for tier in ("fast", "standard", "flex", "unknown")]
        self.assertEqual([m.split_usage_key(k) for k in sorted(keys, key=m.model_tier_display_sort_key)], expected)

    def fixture(self):
        m = self.m
        now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        sid, cid = "019ffabc-1234-7000-8000-123456789173", "019ffabc-1234-7000-8000-123456789174"
        b = m.Bucket(sid, "[demo] 中文模型排序", project_name="demo")
        entries = [("gpt-5.6-luna", "standard", 100_000_000),
                   ("gpt-5.6-sol", "fast", 20_000_000),
                   ("gpt-6-astra", "standard", 1_000_000),
                   ("gpt-6-astra", "unknown", 30_000),
                   ("gpt-6-astra", "flex", 50_000),
                   ("gpt-6-astra", "fast", 100_000)]
        for model, tier, amount in entries:
            source = cid if tier == "fast" and model == "gpt-6-astra" else sid
            b.add(model, m.Usage(input_tokens=amount, total_tokens=amount), source,
                  source_title="中文模型排序", activity_ts=now, recent=True,
                  service_tier=tier, is_subagent=(source == cid))
        root = m.RawSession(sid, Path("synthetic-root.jsonl"), cwd="/tmp/demo", model_provider="openai")
        child = m.RawSession(cid, Path("synthetic-child.jsonl"), cwd="/tmp/demo", model_provider="openai",
                             parent_id=sid, source="subagent")
        return {sid: b}, {sid: root, cid: child}, now, m.QuotaCalibration(100.0, "LOW")

    def render(self, wide=False, width=144, fast=False):
        m = self.m
        b, sessions, now, cal = self.fixture()
        with patch.object(m.shutil, "get_terminal_size", return_value=os.terminal_size((width, 40))):
            return m.render_table(b, sessions, "24h", timezone.utc, fast, True, now, True,
                                  m.Colorizer("never"), wide=wide, quota_calibration=cal)

    def test_summary_and_agent_models_prioritize_astra_despite_larger_sol_spend(self):
        for wide in (False, True):
            for width in (100, 144, 240):
                with self.subTest(wide=wide, width=width):
                    text = self.render(wide=wide, width=width)
                    self.assertIn("Models: 6 Astra / 5.6 Sol / 5.6 Luna", text)
                    if width >= 144:
                        self.assertIn("6 Astra +2", text)
                    agent = text.split("\nAgent breakdown\n")[1]
                    self.assertIn("Models: 6 Astra / 5.6 Sol / 5.6 Luna", agent)
                    self.assertLess(agent.index("MAIN"), agent.index("SUB"))

    def test_terminal_details_use_price_not_total_spend(self):
        for fast in (False, True):
            section = self.render(fast=fast).split("\nModel breakdown\n")[1].split("\nAgent breakdown\n")[0]
            actual = [re.split(r"\s{2,}", line.strip())[:2] for line in section.splitlines()
                      if line.startswith(("6 Astra", "5.6 Sol", "5.6 Luna"))]
            self.assertEqual(actual, [["6 Astra", "FAST"], ["6 Astra", "STD"],
                                      ["6 Astra", "FLEX"], ["6 Astra", "?"],
                                      ["5.6 Sol", "FAST"], ["5.6 Luna", "STD"]])

    def test_json_csv_order_matches_terminal(self):
        m = self.m
        b, sessions, now, cal = self.fixture()
        row = json.loads(m.render_json(b, sessions, "24h", timezone.utc, False, now, True,
                                       quota_calibration=cal))["sessions"][0]
        self.assertEqual(row["models"], ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna"])
        self.assertEqual([(r["model"], r["service_tier"]) for r in row["model_breakdown"]],
                         [("gpt-6-astra", t) for t in ("fast", "standard", "flex", "unknown")] +
                         [("gpt-5.6-sol", "fast"), ("gpt-5.6-luna", "standard")])
        self.assertEqual(row["agent_breakdown"][0]["models"], row["models"])
        csv_row = next(csv.DictReader(io.StringIO(m.render_csv(b, sessions, False, now, True,
                                      quota_calibration=cal))))
        self.assertEqual(csv_row["models"], ",".join(row["models"]))
        self.assertEqual(row["credit_estimate"], 9082.5)
        self.assertEqual(row["weekly_estimate_percent"], 90.825)

    def test_render_order_does_not_mutate_usage_or_change_export_values(self):
        m = self.m
        b, sessions, now, cal = self.fixture()
        def canonical(doc):
            for row in doc["sessions"]:
                row["models"].sort()
                row["model_breakdown"].sort(key=lambda r: (r["model"], r["service_tier"]))
                for agent in row["agent_breakdown"]:
                    agent["models"].sort()
            return doc
        for fast in (False, True):
            before_keys = list(next(iter(b.values())).usage_by_model)
            baseline = json.loads(m.render_json(b, sessions, "24h", timezone.utc, fast, now, True,
                                                quota_calibration=cal))
            with patch.object(m, "model_display_sort_key", return_value=()), \
                 patch.object(m, "model_tier_display_sort_key", return_value=()):
                unsorted = json.loads(m.render_json(b, sessions, "24h", timezone.utc, fast, now, True,
                                                    quota_calibration=cal))
            self.assertEqual(canonical(baseline), canonical(unsorted))
            self.assertEqual(before_keys, list(next(iter(b.values())).usage_by_model))


if __name__ == "__main__":
    unittest.main()
