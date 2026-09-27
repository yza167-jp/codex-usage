"""Sol/Luna regression fixtures are synthetic; no account or transcript secrets."""
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from test_codex_usage import load_module

SCRIPT = Path(__file__).resolve().parents[1] / 'codex-usage'
UTC = timezone.utc
NEW_MODELS = ('gpt-6-sol', 'gpt-6-luna')


class GPT6SolLunaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def usage(self):
        return self.m.Usage(input_tokens=1_000_000, cached_input_tokens=800_000,
                            output_tokens=100_000, reasoning_output_tokens=40_000,
                            total_tokens=1_100_000)

    def report(self, models, details=False, width=144, colored=False):
        m = self.m
        now = datetime.now(UTC)
        b = m.Bucket('sample', 'Synthetic model test', project_name='demo')
        for model, tier in models:
            b.add(model, self.usage(), 'sample', activity_ts=now,
                  recent=True, service_tier=tier)
        with patch.object(m.shutil, 'get_terminal_size',
                          return_value=os.terminal_size((width, 40))):
            return m.render_table({'sample': b}, {}, 'test', UTC, False, details,
                                  now, True, m.Colorizer('always' if colored else 'never'),
                                  wide=True, quota_calibration=m.QuotaCalibration(
                                      credits_per_percent=100, confidence='LOW'))

    def write_rollout(self, home, now, model):
        folder = home / 'sessions' / now.strftime('%Y/%m/%d')
        folder.mkdir(parents=True, exist_ok=True)
        sid = '019fffff-1111-7000-8000-123456789abc'
        path = folder / f'rollout-{sid}.jsonl'
        def rec(minutes, kind, payload):
            return dict(timestamp=(now-timedelta(minutes=minutes)).isoformat(),
                        type=kind, payload=payload)
        records = [
            rec(10, 'session_meta', dict(id=sid, model_provider='openai', cwd='/demo')),
            rec(9, 'turn_context', dict(model=model, service_tier='default')),
            rec(6, 'event_msg', dict(type='token_count', info=dict(
                total_token_usage=self.usage().__dict__))),
            rec(4, 'event_msg', dict(type='thread_settings_applied',
                thread_settings=dict(model=model, service_tier='priority'))),
            rec(2, 'event_msg', dict(type='token_count', info=dict(
                total_token_usage=(self.usage()+self.usage()).__dict__))),
        ]
        path.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
        return path, sid

    def test_independent_reference_rates_and_fast_multipliers(self):
        self.assertEqual(self.m.RATE_CARD['gpt-6-sol'], (50.0, 5.0, 250.0))
        self.assertEqual(self.m.RATE_CARD['gpt-6-luna'], (2.5, 0.25, 12.5))
        for model in NEW_MODELS:
            self.assertEqual(self.m.FAST_MULTIPLIERS[model], 2.5)
        self.assertEqual(self.m.RATE_CARD['gpt-6-astra'], (250.0, 25.0, 1250.0))
        self.assertEqual(self.m.RATE_CARD['gpt-5.6-sol'], (125.0, 12.5, 750.0))
        self.assertEqual(self.m.RATE_CARD['gpt-5.6-luna'], (25.0, 2.5, 150.0))

    def test_canonical_dated_and_provider_ids_keep_their_family(self):
        for model, label in (('gpt-6-sol', '6 Sol'), ('gpt-6-luna', '6 Luna')):
            for spelling in (model, ' '+model.upper()+' ', model+'-2026-09-22', 'openai.'+model):
                with self.subTest(spelling=spelling):
                    self.assertEqual(self.m.normalize_model(spelling), model)
                    self.assertEqual(self.m.pretty_model(spelling), label)
                    self.assertEqual(self.m.split_usage_key(self.m.usage_key(spelling, 'priority')),
                                     (model, 'fast'))
        self.assertEqual(self.m.normalize_model('gpt-6'), 'gpt-6-astra')
        self.assertEqual(self.m.normalize_model('gpt6'), 'gpt-6-astra')

    def test_unverified_suffixes_stay_unpriced(self):
        for model in NEW_MODELS:
            for suffix in ('-pro', '-preview', '-wm', '-2026-09-22-pro', '-latest'):
                name = model+suffix
                self.assertEqual(self.m.normalize_model(name), name)
                self.assertEqual(self.m._credit_for_usage_with_completeness(
                    self.m.usage_key(name, 'standard'), self.usage(), False), (None, False))

    def test_cached_and_reasoning_tokens_are_not_billed_twice(self):
        for model, expected in (('gpt-6-sol', 39), ('gpt-6-luna', 1.95)):
            key = self.m.usage_key(model, 'standard')
            cost, complete = self.m._credit_for_usage_with_completeness(key, self.usage(), False)
            self.assertAlmostEqual(cost, expected)
            self.assertTrue(complete)
            self.assertAlmostEqual(sum(self.m.credit_components_for_usage(key, self.usage(), False)), expected)
            self.assertAlmostEqual(self.m.credit_for_usage(key, self.usage(), True), expected)

    def test_fast_and_unknown_fallback_do_not_override_standard(self):
        for model, base in (('gpt-6-sol', 39), ('gpt-6-luna', 1.95)):
            for tier in ('fast', 'priority'):
                cost, complete = self.m._credit_for_usage_with_completeness(
                    self.m.usage_key(model, tier), self.usage(), False)
                self.assertAlmostEqual(cost, base*2.5)
                self.assertTrue(complete)
            unknown = self.m.usage_key(model, 'unknown')
            self.assertEqual(self.m._credit_for_usage_with_completeness(unknown, self.usage(), False), (base, False))
            cost, complete = self.m._credit_for_usage_with_completeness(unknown, self.usage(), True)
            self.assertAlmostEqual(cost, base*2.5)
            self.assertTrue(complete)
            self.assertFalse(self.m._credit_for_usage_with_completeness(
                self.m.usage_key(model, 'flex'), self.usage(), False)[1])

    def test_sorting_uses_unit_price_not_generation(self):
        names = ['gpt-6-luna', 'gpt-6-sol', 'gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-6-astra']
        self.assertEqual(self.m.model_names(names),
                         ['gpt-6-astra', 'gpt-5.6-sol', 'gpt-6-sol', 'gpt-5.6-luna', 'gpt-6-luna'])
        head, lines = self.m.model_cell_layout(NEW_MODELS, 12, 144)
        self.assertEqual(head, '6 Sol +1')
        self.assertIn('6 Sol / 6 Luna', ' '.join(lines))

    def test_each_rollout_segment_has_its_own_rate(self):
        m = self.m
        now = datetime.now(UTC)
        for model, expected in (('gpt-6-sol', 136.5), ('gpt-6-luna', 6.825)):
            with tempfile.TemporaryDirectory() as td:
                path, sid = self.write_rollout(Path(td), now, model)
                sessions = {sid: m.parse_rollout(path)}
                self.assertEqual([r[2] for r in m.compute_deltas(sessions[sid], sessions)], ['standard', 'fast'])
                buckets = m.make_buckets(sessions, {}, now-timedelta(hours=1), now, UTC, False,
                                         now-timedelta(hours=1))
                cost, complete = m.bucket_collection_credits(buckets, sessions, False)
                self.assertAlmostEqual(cost, expected)
                self.assertTrue(complete)

    def test_mixed_subagent_rollup_totals_details_and_exports(self):
        m = self.m
        now = datetime.now(UTC)
        root = m.RawSession('root', Path('root.jsonl'), created_at=now-timedelta(minutes=10),
                            usage_events=[m.UsageEvent(now-timedelta(minutes=9), self.usage(),
                                                       'gpt-6-sol', 'standard')])
        child = m.RawSession('child', Path('child.jsonl'), parent_id='root', source='subagent',
                             created_at=now-timedelta(minutes=8), usage_events=[
                                 m.UsageEvent(now-timedelta(minutes=7), self.usage()+self.usage(),
                                              'gpt-6-luna', 'fast')])
        sessions = {'root': root, 'child': child}
        buckets = m.make_buckets(sessions, {}, now-timedelta(hours=1), now, UTC, False,
                                 now-timedelta(hours=1))
        cal = m.QuotaCalibration(credits_per_percent=100, confidence='LOW')
        cost, complete = m.bucket_collection_credits(buckets, sessions, False)
        self.assertAlmostEqual(cost, 43.875)
        self.assertTrue(complete)
        doc = json.loads(m.render_json(buckets, sessions, 'test', UTC, False, now, True,
                                       quota_calibration=cal))
        row = doc['sessions'][0]
        for field in ('weekly_estimate_percent', 'trailing_1h_weekly_estimate_percent'):
            self.assertAlmostEqual(row[field], .43875)
        self.assertAlmostEqual(row['subagent_credit_estimate'], 4.875)
        self.assertEqual([x['model'] for x in row['model_breakdown']], list(NEW_MODELS))
        csv_row = next(csv.DictReader(io.StringIO(m.render_csv(buckets, sessions, False,
                                    now, True, quota_calibration=cal))))
        self.assertAlmostEqual(float(csv_row['credit_estimate']), cost)
        text = self.report([(name, 'standard') for name in NEW_MODELS], details=True)
        self.assertIn('6 Sol', text)
        self.assertIn('6 Luna', text)
        self.assertIn('Agent breakdown', text)
        self.assertNotIn('Unpriced models', text)

    def test_missing_model_warning_is_explicit_even_without_quota(self):
        m = self.m
        b = m.Bucket('test', 'test')
        b.add('gpt-unpriced-demo', self.usage(), 'test', service_tier='standard')
        text = m.render_table({'test': b}, {}, 'test', UTC, False, False,
                               datetime.now(UTC), True, m.Colorizer('never'))
        self.assertIn('Unpriced models (selected period): gpt-unpriced-demo', text)
        self.assertIn('Tokens retained', text)
        self.assertEqual(m.bucket_collection_credits({'test': b}, {}, False), (None, False))

    def test_unknown_tier_is_not_misreported_as_missing_model(self):
        text = self.report([('gpt-6-sol', 'unknown')])
        self.assertNotIn('Unpriced models', text)
        self.assertIn('39.0+', text)
        self.assertIn('0.39%?', text)

    def test_mixed_unknown_models_retain_known_cost(self):
        text = self.report([('gpt-6-sol', 'standard'), ('gpt-unpriced-demo', 'standard')])
        self.assertIn('Unpriced models (selected period): gpt-unpriced-demo', text)
        self.assertIn('39.0+', text)
        self.assertIn('0.39%?', text)

    def test_long_missing_ids_wrap_without_losing_characters(self):
        name = 'gpt-unpriced-' + 'example-'*30
        for width in (80, 120, 144):
            text = self.report([(name, 'standard')], width=width)
            block = text.split('Unpriced models (selected period):', 1)[1].split('Tokens retained', 1)[0]
            self.assertEqual(''.join(block.split()), name)
            for line in block.splitlines():
                self.assertLessEqual(self.m.display_width(line), min(width, 144))

    def test_warm_cache_upgrade_reprices_and_replays_excluded_quota(self):
        m = self.m
        now = datetime.now(UTC)
        start = now-timedelta(hours=1)
        auth = m.LocalAuthContext(plan_type='pro', account_key='synthetic-test')
        reset = int((now+timedelta(days=3)).timestamp())
        points = [m.QuotaSnapshot(now-timedelta(minutes=7), 30, 10080, reset, plan_type='pro'),
                  m.QuotaSnapshot(now-timedelta(minutes=1), 34, 10080, reset, plan_type='pro')]
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path, sid = self.write_rollout(home, now, 'gpt-6-sol')
            cache = home / 'index.sqlite3'
            conn = m._cache_connect(cache)
            try:
                old_rates = {k:v for k,v in m.RATE_CARD.items() if k not in NEW_MODELS}
                with patch.dict(m.RATE_CARD, old_rates, clear=True):
                    m.sync_incremental_cache(conn, [path], start, now, False)
                    sessions = m._load_sessions_from_cache(conn, {str(path)})
                    for point in points:
                        m._record_quota_snapshot(conn, auth, point, False)
                    before_cal = m.load_quota_calibration(conn, auth, points[-1], None, False,
                                                          ledger=m.QuotaCreditLedger(sessions, False))
                    self.assertEqual(before_cal.excluded_intervals, 1)
                    self.assertNotEqual(before_cal.source, 'current_delta')
                    old = m.make_buckets(sessions, {}, start, now, UTC, False)
                    self.assertEqual(m.bucket_collection_credits(old, sessions, False), (None, False))
                before_events = [tuple(r) for r in conn.execute('SELECT * FROM events')]
                before_raw = [tuple(r) for r in conn.execute('SELECT * FROM quota_snapshots_v180')]
            finally:
                conn.close()
            conn = m._cache_connect(cache)
            try:
                stats = m.sync_incremental_cache(conn, [path], start, now, False)
                self.assertEqual(stats.bytes_read, 0)
                self.assertEqual(stats.cold_scans, 0)
                self.assertEqual(stats.cache_hits, 1)
                sessions = m._load_sessions_from_cache(conn, {str(path)})
                new = m.make_buckets(sessions, {}, start, now, UTC, False)
                self.assertEqual(m.bucket_collection_credits(new, sessions, False), (136.5, True))
                after_cal = m.load_quota_calibration(conn, auth, points[-1], None, False,
                                                     ledger=m.QuotaCreditLedger(sessions, False))
                self.assertEqual(after_cal.source, 'current_delta')
                self.assertEqual(after_cal.excluded_intervals, 0)
                self.assertEqual(after_cal.clean_intervals, 1)
                self.assertAlmostEqual(after_cal.credits_per_percent, 136.5/4)
                self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM events')], before_events)
                self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM quota_snapshots_v180')], before_raw)
            finally:
                conn.close()
            args = [sys.executable, str(SCRIPT), '1h', '--codex-home', str(home),
                    '--cache-path', str(cache), '--no-quota', '--json']
            cached = json.loads(subprocess.run(args, capture_output=True, encoding='utf-8', check=True).stdout)
            uncached = json.loads(subprocess.run(args+['--no-cache'], capture_output=True,
                                                 encoding='utf-8', check=True).stdout)
            self.assertEqual(cached['sessions'][0]['credit_estimate'], 136.5)
            self.assertEqual(cached['sessions'][0]['credit_estimate'], uncached['sessions'][0]['credit_estimate'])

    def test_solluna_assumed_and_flex_quota_eligibility(self):
        m = self.m
        now = datetime.now(UTC)
        for model in NEW_MODELS:
            for tier, eligible, quality in (('unknown', True, 'assumed_tier'),
                                            ('flex', False, 'excluded'),
                                            ('standard', True, 'complete')):
                s = m.RawSession('sample', Path('sample.jsonl'), usage_events=[
                    m.UsageEvent(now, self.usage(), model, tier)])
                ledger = m.QuotaCreditLedger({'sample': s}, False)
                summary = ledger.between(now-timedelta(seconds=1), now)
                self.assertEqual(summary.eligible, eligible)
                self.assertEqual(summary.quality, quality)
                self.assertEqual(summary.unpriced_events, 0)


if __name__ == '__main__':
    unittest.main()
