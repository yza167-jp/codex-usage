"""v1.8.0 consolidation: preserve v1.7.4 behavior and harden raw scope/migration."""
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_quota_window as legacy


class ScopedQuotaTests(unittest.TestCase):
    setUpClass = classmethod(lambda cls: setattr(cls, 'm', legacy.load_module()))
    setUp = legacy.QuotaWindowTests.setUp
    tearDown = legacy.QuotaWindowTests.tearDown
    snap = legacy.QuotaWindowTests.snap
    record = legacy.QuotaWindowTests.record
    sessions = legacy.QuotaWindowTests.sessions
    calc = legacy.QuotaWindowTests.calc

    def points(self, snap, fast=False):
        return self.m._quota_snapshot_points_v180(self.conn, self.auth, snap, fast)

    def test_simultaneous_codex_and_model_pools_do_not_overwrite(self):
        good, special = self.snap(self.now, 62), self.snap(self.now, 4, pool='spark')
        self.record(good, special)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots_v180').fetchone()[0], 2)
        self.assertEqual(self.points(good)[-1].used_percent, 62)
        self.assertEqual(self.points(special)[-1].used_percent, 4)
        raw = self.conn.execute('SELECT limit_id,used_percent FROM quota_snapshots').fetchone()
        self.assertEqual(tuple(raw), ('codex', 62))

    def test_new_codex_snapshot_does_not_destroy_legacy_foreign_collision(self):
        good = self.snap(self.now, 62)
        self.conn.execute('''INSERT INTO quota_snapshots VALUES(?,?,?,?,?,?,?,?,?)''',
            (self.auth.account_key, 'pro', self.reset, 10080, self.now.isoformat(), 7,
             'tier_auto', 'rollout', 'spark'))
        self.conn.commit()
        self.record(good)
        self.assertEqual(self.conn.execute('SELECT limit_id FROM quota_snapshots').fetchone()[0], 'spark')
        self.assertEqual(self.points(good)[-1].used_percent, 62)

    def test_duration_is_part_of_raw_primary_key(self):
        good = self.snap(self.now, 62)
        other = replace(good, window_minutes=10079, used_percent=12)
        self.record(good, other)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots_v180').fetchone()[0], 2)
        self.assertEqual(self.points(good)[-1].window_minutes, 10080)
        self.assertEqual(self.points(good)[-1].used_percent, 62)
        self.assertEqual(self.points(other)[-1].used_percent, 12)

    def test_same_time_mode_isolation(self):
        self.record(self.snap(self.now, 60), fast=False)
        self.record(self.snap(self.now, 63), fast=True)
        earlier = self.now - timedelta(minutes=10)
        self.record(self.snap(earlier, 50), fast=False)
        self.record(self.snap(earlier, 10), fast=True)
        self.assertEqual(self.points(self.snap(self.now, 60))[0].used_percent, 50)
        self.assertEqual(self.points(self.snap(self.now, 63), True)[0].used_percent, 10)

    def test_scoped_rows_override_older_shadow_without_mutating_it(self):
        a, b = self.now - timedelta(hours=2), self.now
        self.record(self.snap(a, 5))
        self.record(self.snap(a, 10))
        self.assertEqual(self.conn.execute('SELECT used_percent FROM quota_snapshots').fetchone()[0], 5)
        self.assertEqual(self.points(self.snap(b, 13))[0].used_percent, 10)

    def test_legacy_observation_is_replayed_not_its_stored_credit_scalar(self):
        a, b = self.start + timedelta(hours=1), self.start + timedelta(hours=2)
        self.m._record_quota_observation(self.conn, self.auth, self.snap(a, 10), 999999, False)
        self.conn.execute("UPDATE quota_observations SET rate_card='obsolete-rate'")
        self.conn.commit()
        sessions = self.sessions([(a, 5500), (b, 1650)], tier='standard')
        cal = self.calc(self.snap(b, 13), sessions)
        self.assertEqual(cal.source, 'current_delta')
        self.assertAlmostEqual(cal.credits_per_percent, 550)
        self.assertEqual(self.conn.execute('SELECT local_credits FROM quota_observations').fetchone()[0], 999999)

    def test_unscoped_legacy_observation_not_used_for_model_pool(self):
        a = self.now - timedelta(hours=1)
        self.m._record_quota_observation(self.conn, self.auth, self.snap(a, 2), 1100, False)
        self.assertEqual(len(self.points(self.snap(self.now, 5, pool='special'))), 1)

    def test_legacy_observation_account_plan_mode_are_filtered(self):
        a = self.now - timedelta(hours=1)
        for account, plan, fast in [('other', 'pro', False),
                                    ('synthetic', 'prolite', False), ('synthetic', 'pro', True)]:
            auth = self.m.LocalAuthContext(account_key=account, plan_type=plan)
            self.m._record_quota_observation(self.conn, auth, self.snap(a, 3, plan=plan), 1650, fast)
        self.assertEqual(len(self.points(self.snap(self.now, 6))), 1)

    def test_future_scoped_snapshot_not_used_by_asof_query(self):
        a = self.now - timedelta(hours=1)
        self.record(self.snap(a, 2), self.snap(self.now, 5), self.snap(self.now + timedelta(hours=1), 20))
        points = self.points(self.snap(self.now, 5))
        self.assertEqual([p.used_percent for p in points], [2, 5])

    def test_derived_duration_key_allows_two_windows_without_collision(self):
        a, b = self.start + timedelta(hours=1), self.start + timedelta(hours=2)
        ledger = self.m.QuotaCreditLedger(self.sessions([(b, 1650)], tier='standard'), False)
        for duration in [10080, 10079]:
            left = replace(self.snap(a, 0), window_minutes=duration)
            right = replace(self.snap(b, 3), window_minutes=duration)
            self.record(left, right)
            self.m._refresh_quota_intervals_v2(self.conn, self.auth, right, ledger, False)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_intervals_v3').fetchone()[0], 2)
        self.assertEqual(self.conn.execute('SELECT COUNT(DISTINCT window_minutes) FROM quota_intervals_v3').fetchone()[0], 2)

    def test_v174_derived_audit_rows_survive_open_and_replay(self):
        a, b = self.start + timedelta(hours=1), self.start + timedelta(hours=2)
        self.record(self.snap(a, 0))
        self.calc(self.snap(b, 3), self.sessions([(b, 1650)]))
        self.conn.execute('INSERT INTO quota_intervals_v2 SELECT * FROM quota_intervals_v3')
        self.conn.commit()
        before = [tuple(r) for r in self.conn.execute('SELECT * FROM quota_intervals_v2')]
        self.conn.close()
        self.conn = self.m._cache_connect(self.path)
        self.calc(self.snap(b, 3), self.sessions([(b, 1650)]))
        self.assertEqual(before, [tuple(r) for r in self.conn.execute('SELECT * FROM quota_intervals_v2')])
        self.assertEqual(self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], '3')

    def test_unknown_assume_fast_without_multiplier_is_excluded(self):
        a, b = self.start + timedelta(hours=1), self.start + timedelta(hours=2)
        sessions = self.sessions([(b, 1650)], model='gpt-5.3-codex')
        ledger = self.m.QuotaCreditLedger(sessions, True)
        summary = ledger.between(a, b)
        self.assertEqual(summary.quality, 'excluded')
        self.assertEqual(summary.unsupported_events, 1)
        # Regular unknown/Standard assumption remains usable for this known model.
        self.assertEqual(self.m.QuotaCreditLedger(sessions, False).between(a, b).quality, 'assumed_tier')

    def test_policy_revision_export_is_not_left_at_v174(self):
        cal = self.m.QuotaCalibration(credits_per_percent=550)
        meta = self.m.quota_calibration_metadata(cal)
        self.assertEqual(meta['revision'], self.m.QUOTA_CALIBRATION_REVISION)
        self.assertIn('v3', meta['revision'])
        self.assertIn('window-v3-scoped', self.m.cache_info(self.conn, self.path))

    def test_invalid_snapshot_also_leaves_scoped_store_empty(self):
        for used in [float('nan'), float('inf'), -1, 101]:
            self.record(self.snap(self.now, used))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots_v180').fetchone()[0], 0)

    def test_unknown_assumed_many_queries_never_promoted_to_high(self):
        a = self.start + timedelta(hours=1)
        snaps = [self.snap(a + timedelta(hours=i), 4*i) for i in range(7)]
        self.record(*snaps)
        cal = self.calc(snaps[-1], self.sessions([(s.ts, 2200) for s in snaps[1:]]))
        self.assertEqual((cal.confidence, cal.assumed_intervals, cal.clean_intervals), ('LOW', 6, 0))

    def test_raw_scope_repeated_queries_are_idempotent(self):
        snap = self.snap(self.now, 3)
        for _ in range(20):
            self.record(snap)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots_v180').fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots').fetchone()[0], 1)
