"""Synthetic GPT-6.1 Sol fixtures; no private conversations or credentials."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from test_codex_usage import load_module

MODEL = 'gpt-6.1-sol'
UTC = timezone.utc
SCRIPT = Path(__file__).resolve().parents[1] / 'codex-usage'


class GPT61SolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def usage(self):
        return self.m.Usage(input_tokens=1_000_000, cached_input_tokens=800_000,
                            output_tokens=100_000, reasoning_output_tokens=40_000,
                            total_tokens=1_100_000)

    def write_rollout(self, home, now):
        folder = home / 'sessions' / now.strftime('%Y/%m/%d')
        folder.mkdir(parents=True, exist_ok=True)
        sid = '019fffff-3333-7000-8000-123456789abc'
        path = folder / ('rollout-' + sid + '.jsonl')
        def rec(minutes, kind, payload):
            return dict(timestamp=(now-timedelta(minutes=minutes)).isoformat(),
                        type=kind, payload=payload)
        records = [
            rec(10, 'session_meta', dict(id=sid, model_provider='openai', cwd='/demo')),
            rec(9, 'turn_context', dict(model=MODEL, service_tier='default')),
            rec(6, 'event_msg', dict(type='token_count', info=dict(
                total_token_usage=self.usage().__dict__))),
            rec(4, 'event_msg', dict(type='thread_settings_applied',
                thread_settings=dict(model=MODEL, service_tier='priority'))),
            rec(2, 'event_msg', dict(type='token_count', info=dict(
                total_token_usage=(self.usage()+self.usage()).__dict__))),
        ]
        path.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
        return path, sid

    def test_identity_and_dated_ids_are_distinct(self):
        for spelling in (MODEL, ' GPT-6.1-SOL ', MODEL+'-2026-09-29', 'openai.'+MODEL):
            with self.subTest(spelling=spelling):
                self.assertEqual(self.m.normalize_model(spelling), MODEL)
                self.assertEqual(self.m.pretty_model(spelling), '6.1 Sol')
                self.assertEqual(self.m.split_usage_key(self.m.usage_key(spelling, 'priority')),
                                 (MODEL, 'fast'))
        self.assertEqual(self.m.normalize_model('gpt-6'), 'gpt-6-astra')
        self.assertEqual(self.m.normalize_model('gpt-6-sol'), 'gpt-6-sol')
        self.assertEqual(self.m.model_names([MODEL, MODEL+'-2026-09-29']), [MODEL])

    def test_generic_and_unverified_variants_stay_unpriced(self):
        for name in ('gpt-6.1', 'gpt6.1', 'gpt-6.1-luna', MODEL+'-ultrafast',
                     MODEL+'-pro', MODEL+'-wm', MODEL+'-preview', MODEL+'-latest',
                     MODEL+'-2026-09-29-pro', 'gpt-6x1-sol-2026-09-29'):
            with self.subTest(name=name):
                self.assertEqual(self.m.normalize_model(name), name)
                self.assertEqual(self.m._credit_for_usage_with_completeness(
                    self.m.usage_key(name, 'standard'), self.usage(), False), (None, False))

    def test_standard_reference_tuple_and_existing_rates_preserved(self):
        self.assertEqual(self.m.RATE_CARD[MODEL], (50.0, 2.5, 250.0))
        self.assertEqual(self.m.RATE_CARD['gpt-6-sol'], (50.0, 5.0, 250.0))
        self.assertEqual(self.m.RATE_CARD['gpt-6-astra'], (250.0, 25.0, 1250.0))
        self.assertEqual(self.m.RATE_CARD['gpt-6-luna'], (2.5, .25, 12.5))
        self.assertEqual(self.m.FAST_MULTIPLIERS[MODEL], 2.5)
        self.assertEqual(self.m.CACHE_SCHEMA_VERSION, 3)
        self.assertEqual(self.m.RATE_CARD_CALIBRATION_KEY, '2026-08-12-r3-tier-aware')

    def test_cached_and_reasoning_are_not_double_charged(self):
        key = self.m.usage_key(MODEL, 'standard')
        self.assertEqual(self.m.credit_components_for_usage(key, self.usage(), False),
                         (10.0, 2.0, 25.0))
        self.assertEqual(self.m._credit_for_usage_with_completeness(key, self.usage(), False),
                         (37.0, True))

    def test_cache_is_halved_but_not_the_whole_bill(self):
        cached = self.m.Usage(input_tokens=1_000_000, cached_input_tokens=1_000_000)
        old = self.m.credit_for_usage('gpt-6-sol', cached, False)
        new = self.m.credit_for_usage(MODEL, cached, False)
        self.assertEqual((old, new), (5.0, 2.5))
        self.assertEqual(self.m.credit_for_usage('gpt-6-sol', self.usage(), False), 39.0)
        self.assertEqual(self.m.credit_for_usage(MODEL, self.usage(), False), 37.0)

    def test_detected_fast_is_subscription_reference_not_paid_credit_rate(self):
        for tier in ('fast', 'priority'):
            key = self.m.usage_key(MODEL, tier)
            self.assertEqual(self.m._credit_for_usage_with_completeness(key, self.usage(), False),
                             (92.5, True))
            self.assertEqual(self.m.credit_components_for_usage(key, self.usage(), False),
                             (25.0, 5.0, 62.5))
        # Fast reference 2.5x is intentionally not a purchased-credit invoice (2x).
        self.assertNotEqual(92.5, 37.0*2)

    def test_unknown_fallback_does_not_override_detected_tiers(self):
        for tier, fast, expected in [('unknown', False, (37.0, False)),
                                      ('unknown', True, (92.5, True)),
                                      ('standard', True, (37.0, True)),
                                      ('fast', True, (92.5, True))]:
            self.assertEqual(self.m._credit_for_usage_with_completeness(
                self.m.usage_key(MODEL, tier), self.usage(), fast), expected)
        self.assertFalse(self.m._credit_for_usage_with_completeness(
            self.m.usage_key(MODEL, 'flex'), self.usage(), False)[1])

    def test_price_sorting_keeps_original_sol_ahead_on_cached_rate_tiebreak(self):
        models = [MODEL, 'gpt-6-luna', 'gpt-6-sol', 'gpt-6-astra']
        self.assertEqual(self.m.model_names(models),
                         ['gpt-6-astra', 'gpt-6-sol', MODEL, 'gpt-6-luna'])
        head, lines = self.m.model_cell_layout([MODEL, 'gpt-6-luna'], 12, 144)
        self.assertEqual(head, '6.1 Sol +1')
        self.assertIn('6.1 Sol / 6 Luna', ' '.join(lines))

    def test_rollout_and_subagent_totals_exports_share_one_scale(self):
        m = self.m
        now = datetime.now(UTC)
        with tempfile.TemporaryDirectory() as td:
            path, sid = self.write_rollout(Path(td), now)
            root = m.parse_rollout(path)
            sessions = {sid: root}
            self.assertEqual([r[2] for r in m.compute_deltas(root, sessions)], ['standard', 'fast'])
            child = m.RawSession('child', Path('child.jsonl'), parent_id=sid, source='subagent',
                created_at=now-timedelta(minutes=1), usage_events=[m.UsageEvent(
                    now-timedelta(seconds=30), self.usage()+self.usage()+self.usage(),
                    'gpt-6-luna', 'fast')])
            sessions['child'] = child
            buckets = m.make_buckets(sessions, {}, now-timedelta(hours=1), now, UTC, False,
                                    now-timedelta(hours=1))
            cost, complete = m.bucket_collection_credits(buckets, sessions, False)
            self.assertEqual((cost, complete), (134.375, True))
            cal = m.QuotaCalibration(credits_per_percent=100.0, confidence='LOW')
            doc = json.loads(m.render_json(buckets, sessions, 'test', UTC, False, now, True,
                                          quota_calibration=cal))
            row = doc['sessions'][0]
            self.assertEqual(row['credit_estimate'], 134.375)
            self.assertEqual(row['subagent_credit_estimate'], 4.875)
            self.assertEqual(row['weekly_estimate_percent'], 1.34375)
            self.assertEqual(row['trailing_1h_weekly_estimate_percent'], 1.34375)
            self.assertEqual(sum(r['credit_estimate'] for r in row['model_breakdown']), cost)
            csv_row = next(csv.DictReader(io.StringIO(m.render_csv(buckets, sessions, False,
                                         now, True, quota_calibration=cal))))
            self.assertAlmostEqual(float(csv_row['credit_estimate']), cost)
            self.assertIn(MODEL, csv_row['models'])
            with patch.object(m.shutil, 'get_terminal_size', return_value=os.terminal_size((144, 40))):
                text = m.render_table(buckets, sessions, 'test', UTC, False, True, now, True,
                                      m.Colorizer('never'), wide=True, quota_calibration=cal)
            for expected in ('6.1 Sol', 'TOTAL', '1.34%', 'Model breakdown', 'Agent breakdown',
                             '2.5x included-allowance reference', 'purchased-credit Fast is 2x'):
                self.assertIn(expected, text)
            self.assertNotIn('Unpriced models', text)

    def test_fast_pricing_note_only_when_fast_is_applied(self):
        m = self.m
        for tier, fast, shown in [('standard', False, False), ('standard', True, False),
                                 ('unknown', False, False), ('unknown', True, True),
                                 ('fast', False, True), ('flex', False, False)]:
            bucket = m.Bucket('test', 'test')
            bucket.add(MODEL, self.usage(), 'test', service_tier=tier)
            notes = m.fast_reference_notes({'test': bucket}, fast)
            self.assertEqual(bool(notes), shown)
            for note in notes:
                for line in m.wrap_display_words(note, 80):
                    self.assertLessEqual(m.display_width(line), 80)

    def test_unknown_tier_and_flex_quota_eligibility(self):
        m = self.m
        now = datetime.now(UTC)
        for tier, eligible, quality in [('unknown', True, 'assumed_tier'),
                                        ('flex', False, 'excluded'),
                                        ('standard', True, 'complete'), ('fast', True, 'complete')]:
            session = m.RawSession('test', Path('test.jsonl'), usage_events=[
                m.UsageEvent(now, self.usage(), MODEL, tier)])
            result = m.QuotaCreditLedger({'test': session}, False).between(now-timedelta(seconds=1), now)
            self.assertEqual((result.eligible, result.quality), (eligible, quality))
            self.assertEqual(result.unpriced_events, 0)

    def test_warm_cache_upgrade_recovers_prices_and_quota_without_rescan(self):
        m = self.m
        now = datetime.now(UTC)
        start = now-timedelta(hours=1)
        auth = m.LocalAuthContext(plan_type='pro', account_key='synthetic-only')
        reset = int((now+timedelta(days=3)).timestamp())
        points = [m.QuotaSnapshot(now-timedelta(minutes=7), 30, 10080, reset, plan_type='pro'),
                  m.QuotaSnapshot(now-timedelta(minutes=1), 34, 10080, reset, plan_type='pro')]
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path, sid = self.write_rollout(home, now)
            cache = home/'index.sqlite3'
            conn = m._cache_connect(cache)
            try:
                old_rates = {k:v for k,v in m.RATE_CARD.items() if k != MODEL}
                with patch.dict(m.RATE_CARD, old_rates, clear=True):
                    m.sync_incremental_cache(conn, [path], start, now, False)
                    sessions = m._load_sessions_from_cache(conn, {str(path)})
                    for point in points:
                        m._record_quota_snapshot(conn, auth, point, False)
                    before = m.load_quota_calibration(conn, auth, points[-1], None, False,
                                                       ledger=m.QuotaCreditLedger(sessions, False))
                    self.assertEqual(before.excluded_intervals, 1)
                    buckets = m.make_buckets(sessions, {}, start, now, UTC, False)
                    self.assertEqual(m.bucket_collection_credits(buckets, sessions, False), (None, False))
                events = [tuple(r) for r in conn.execute('SELECT * FROM events')]
                raw = [tuple(r) for r in conn.execute('SELECT * FROM quota_snapshots_v180')]
                stats = m.sync_incremental_cache(conn, [path], start, now, False)
                self.assertEqual((stats.bytes_read, stats.cold_scans, stats.cache_hits), (0, 0, 1))
                sessions = m._load_sessions_from_cache(conn, {str(path)})
                after = m.load_quota_calibration(conn, auth, points[-1], None, False,
                                                 ledger=m.QuotaCreditLedger(sessions, False))
                self.assertEqual(after.source, 'current_delta')
                self.assertEqual(after.excluded_intervals, 0)
                self.assertEqual(after.credits_per_percent, 129.5/4)
                self.assertEqual(events, [tuple(r) for r in conn.execute('SELECT * FROM events')])
                self.assertEqual(raw, [tuple(r) for r in conn.execute('SELECT * FROM quota_snapshots_v180')])
            finally:
                conn.close()
            args = [sys.executable, str(SCRIPT), '1h', '--codex-home', str(home),
                    '--cache-path', str(cache), '--no-quota', '--json']
            cached = json.loads(subprocess.run(args, capture_output=True, encoding='utf-8', check=True).stdout)
            uncached = json.loads(subprocess.run(args+['--no-cache'], capture_output=True,
                                                 encoding='utf-8', check=True).stdout)
            self.assertEqual(cached['sessions'][0]['credit_estimate'], 129.5)
            self.assertEqual(cached['sessions'][0]['credit_estimate'], uncached['sessions'][0]['credit_estimate'])


if __name__ == '__main__':
    unittest.main()
