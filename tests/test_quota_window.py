"""Window-local calibration regressions; synthetic receipts, no user identity.

The audit-shaped fixture uses published diagnostic aggregates to reproduce the
264.253-stale-prior bug. It is not a replay of the user's actual transcripts.
"""
import csv
import io
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from test_codex_usage import load_module

UTC = timezone.utc

def ts(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


class QuotaWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'index.sqlite3'
        self.conn = self.m._cache_connect(self.path)
        self.auth = self.m.LocalAuthContext(plan_type='pro', account_key='synthetic')
        self.start = ts('2026-09-10T14:25:18')
        self.reset = int((self.start + timedelta(days=7)).timestamp())
        self.now = ts('2026-09-11T13:23:57')

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def snap(self, when, used, *, reset=None, pool='codex', plan='pro'):
        return self.m.QuotaSnapshot(when, used, 10080, reset or self.reset, plan_type=plan, limit_id=pool)

    def record(self, *snapshots, fast=False):
        for snap in snapshots:
            self.m._record_quota_snapshot(self.conn, self.auth, snap, fast)

    def sessions(self, receipts, *, tier='unknown', model='gpt-5.6-luna', provider='openai'):
        events = []
        tokens = 0
        rate = self.m.RATE_CARD.get(model, (25, 0, 0))[0]
        for when, cost in receipts:
            tokens += round(cost / rate * 1_000_000)
            events.append(self.m.UsageEvent(ts=when, model=model,
                cumulative=self.m.Usage(input_tokens=tokens, total_tokens=tokens), service_tier=tier))
        s = self.m.RawSession(session_id='synthetic-main', path=Path('synthetic.jsonl'),
            created_at=self.start, model_provider=provider, usage_events=events)
        return {s.session_id: s}

    def calc(self, snap, sessions, fast=False):
        self.record(snap, fast=fast)
        return self.m.load_quota_calibration(self.conn, self.auth, snap, None, fast,
            ledger=self.m.QuotaCreditLedger(sessions, fast))

    def old_prior(self, account='synthetic', mode='tier_auto', plan='pro'):
        old_reset = int(ts('2026-09-07T02:59:26').timestamp())
        for a,b,x,y,cost in [
            ('2026-08-31T15:00:12','2026-08-31T15:32:16',9,10,264.253),
            ('2026-09-05T02:33:47','2026-09-05T05:22:09',82,83,339.477),
        ]:
            auth = self.m.LocalAuthContext(plan_type=plan, account_key=account)
            self.m._record_quota_interval(self.conn, auth,
                self.snap(ts(a),x,reset=old_reset,plan=plan), self.snap(ts(b),y,reset=old_reset,plan=plan),
                cost,True,mode=='tier_auto_assume_fast')

    def audit_fixture(self):
        self.old_prior()
        points = [('03:29:56',43),('07:15:00',54),('07:21:49',54),
                  ('09:56:14',62),('09:56:46',62),('09:57:14',62),('09:58:11',62),('13:23:57',64)]
        snaps = [self.snap(ts('2026-09-11T'+t),u) for t,u in points]
        self.record(*snaps)
        receipts = [(self.start+timedelta(minutes=5),23707.725),
                    (ts('2026-09-11T07:14:00'),6005.692),
                    (ts('2026-09-11T07:18:00'),60),
                    (ts('2026-09-11T09:55:00'),4213.683),
                    (ts('2026-09-11T13:22:00'),1200.835)]
        return snaps, self.sessions(receipts)

    def test_audit_current_assumed_beats_two_old_complete_intervals(self):
        snaps, sessions = self.audit_fixture()
        cal = self.calc(snaps[-1], sessions)
        self.assertEqual(cal.source,'current_delta_assumed')
        self.assertEqual(cal.scope,'current_window')
        self.assertEqual(cal.confidence,'LOW')
        self.assertAlmostEqual(cal.credits_per_percent,(6005.692+4273.683)/19,places=4)
        self.assertEqual((cal.qualified_intervals,cal.assumed_intervals,cal.clean_intervals),(2,2,0))
        self.assertEqual(cal.observed_percent_points,19)
        self.assertAlmostEqual(cal.prior_credits_per_percent,264.253)
        self.assertLess(30937.1/cal.credits_per_percent,62)
        self.assertTrue(any('Old scale' in w for w in cal.warnings))
        self.assertIsNone(cal.local_coverage_percent)

    def test_repeated_plateau_queries_add_neither_samples_nor_pp(self):
        snaps, sessions = self.audit_fixture()
        cal = self.calc(snaps[3],sessions)
        for snap in snaps[4:7]:
            newer = self.calc(snap,sessions)
            self.assertEqual(newer.qualified_intervals,cal.qualified_intervals)
            self.assertEqual(newer.observed_percent_points,cal.observed_percent_points)
            self.assertAlmostEqual(newer.credits_per_percent,cal.credits_per_percent)
        rows = self.conn.execute('SELECT * FROM quota_intervals_v2 ORDER BY start_ts').fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['end_ts'],rows[1]['start_ts'])
        self.assertEqual(rows[0]['end_used_percent'],rows[1]['start_used_percent'])

    def test_half_open_boundaries_bill_each_event_once(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1); c=b+timedelta(hours=1)
        sessions=self.sessions([(a,100),(b,200),(c,300)],tier='standard')
        ledger=self.m.QuotaCreditLedger(sessions,False)
        self.assertEqual(ledger.between(a,b).credits,200)
        self.assertEqual(ledger.between(b,c).credits,300)
        self.assertEqual(ledger.between(a,c).credits,500)

    def test_spark_blocks_only_its_interval_and_later_unknown_can_learn(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1); c=b+timedelta(hours=1)
        self.record(self.snap(a,0),self.snap(b,3))
        sessions=self.sessions([(c-timedelta(minutes=1),1650)])
        other=self.sessions([(b-timedelta(minutes=1),300)],model='gpt-5.3-codex-spark')
        s=next(iter(other.values()));s.session_id='spark';sessions['spark']=s
        cal=self.calc(self.snap(c,6),sessions)
        self.assertEqual(cal.excluded_intervals,1)
        self.assertEqual(cal.assumed_intervals,1)
        self.assertAlmostEqual(cal.credits_per_percent,550)
        raw=self.conn.execute('SELECT * FROM quota_intervals_v2 ORDER BY start_ts').fetchall()
        self.assertEqual(raw[0]['quality'],'excluded')
        self.assertEqual(raw[0]['unpriced_events'],1)
        self.assertEqual(raw[1]['quality'],'assumed_tier')

    def test_flex_and_foreign_and_broken_history_are_not_unknown_tier(self):
        a=self.start+timedelta(hours=1);b=a+timedelta(hours=1)
        for tier,provider,broken,reason in [('flex','openai',False,'flex_events'),
                ('standard','other',False,'unsupported_events'),('standard','openai',True,'history_events')]:
            with self.subTest(reason=reason):
                sessions=self.sessions([(b,100)],tier=tier,provider=provider)
                if broken: next(iter(sessions.values())).malformed_lines=1
                summary=self.m.QuotaCreditLedger(sessions,False).between(a,b)
                self.assertFalse(summary.eligible)
                self.assertEqual(getattr(summary,reason),1)
                self.assertEqual(summary.quality,'excluded')

    def test_unknown_and_assume_fast_use_same_basis_as_report(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1)
        sessions=self.sessions([(b,1650)],model='gpt-6-astra')
        for fast,expected in [(False,550),(True,1375)]:
            self.record(self.snap(a,0),fast=fast)
            cal=self.calc(self.snap(b,3),sessions,fast=fast)
            self.assertAlmostEqual(cal.credits_per_percent,expected)
            self.assertEqual(cal.confidence,'LOW')
            buckets=self.m.make_buckets(sessions,{},a,b+timedelta(microseconds=1),UTC,False)
            credits,_=self.m.bucket_collection_credits(buckets,sessions,fast)
            self.assertAlmostEqual(credits/cal.credits_per_percent,3)

    def test_known_standard_never_becomes_fast(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1)
        sessions=self.sessions([(b,1650)],tier='standard',model='gpt-6-astra')
        self.record(self.snap(a,0),fast=True)
        cal=self.calc(self.snap(b,3),sessions,fast=True)
        self.assertAlmostEqual(cal.credits_per_percent,550)
        self.assertEqual(cal.assumed_intervals,0)

    def test_clean_evidence_confidence_needs_independent_movement(self):
        a=self.start+timedelta(hours=1)
        snaps=[self.snap(a+timedelta(hours=i),4*i) for i in range(7)]
        self.record(*snaps)
        sessions=self.sessions([(s.ts,2200) for s in snaps[1:]],tier='standard')
        cal=self.calc(snaps[-1],sessions)
        self.assertEqual(cal.confidence,'HIGH')
        self.assertEqual(cal.clean_intervals,6)
        self.assertEqual(cal.observed_percent_points,24)

    def test_in_window_decrease_restarts_evidence_not_negative_or_bridging(self):
        a=self.start+timedelta(hours=1)
        snaps=[self.snap(a+timedelta(hours=i),u) for i,u in enumerate([0,10,2,6])]
        self.record(*snaps)
        sessions=self.sessions([(snaps[1].ts,5500),(snaps[3].ts,2200)],tier='standard')
        cal=self.calc(snaps[-1],sessions)
        self.assertEqual(cal.qualified_intervals,1)
        self.assertEqual(cal.observed_percent_points,4)
        self.assertAlmostEqual(cal.credits_per_percent,550)
        self.assertTrue(any('decreased' in w for w in cal.warnings))
        self.assertNotEqual(cal.source,'reconciled_baseline')

    def test_future_snapshot_never_affects_past_asof_replay(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1); c=b+timedelta(hours=1)
        self.record(self.snap(a,0),self.snap(b,3),self.snap(c,20))
        sessions=self.sessions([(b,1650),(c,10)],tier='standard')
        cal=self.calc(self.snap(b,3),sessions)
        self.assertAlmostEqual(cal.credits_per_percent,550)
        self.assertEqual(cal.observed_percent_points,3)

    def test_saturated_endpoint_and_after_exhaustion_do_not_teach(self):
        a=self.start+timedelta(hours=1); b=a+timedelta(hours=1)
        self.record(self.snap(a,97))
        sessions=self.sessions([(b,9000)])
        cal=self.calc(self.snap(b,100),sessions)
        self.assertEqual(cal.confidence,'SEED')
        self.assertEqual(cal.qualified_intervals,0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_intervals_v2').fetchone()[0],0)

    def test_reset_zero_uses_visible_prior_and_old_prior_expires(self):
        self.old_prior()
        cal=self.calc(self.snap(self.start+timedelta(minutes=1),0),{})
        self.assertEqual(cal.source,'historical_prior')
        self.assertEqual(cal.scope,'historical')
        self.assertIn('2026-09-05',cal.data_as_of)
        future=self.snap(self.now+timedelta(days=21),0,reset=self.reset+21*86400)
        later=self.calc(future,{})
        self.assertEqual(later.confidence,'SEED')
        self.assertEqual(later.credits_per_percent,700)

    def test_account_plan_mode_and_pool_are_isolated(self):
        self.old_prior(account='another');self.old_prior(plan='prolite');self.old_prior(mode='tier_auto_assume_fast')
        cal=self.calc(self.snap(self.now,0),{})
        self.assertEqual(cal.confidence,'SEED')
        self.old_prior()
        other=self.calc(self.snap(self.now,0,pool='spark'),{})
        self.assertEqual(other.confidence,'SEED')
        self.assertTrue(any('pool' in w for w in other.warnings))

    def test_partial_baseline_is_labeled_and_does_not_invent_clean_samples(self):
        snap=self.snap(self.now,62)
        cal=self.calc(snap,self.sessions([(self.now,33987.1)]))
        self.assertAlmostEqual(cal.credits_per_percent,33987.1/62)
        self.assertEqual(cal.source,'current_baseline_assumed')
        self.assertEqual(cal.qualified_intervals,0)
        self.assertTrue(any('construction' in w for w in cal.warnings))
        self.assertIsNone(cal.local_coverage_percent)

    def test_conflicting_complete_delta_uses_explicit_reconciled_baseline(self):
        a=self.start+timedelta(hours=1);b=a+timedelta(hours=1)
        self.record(self.snap(a,10))
        sessions=self.sessions([(a,10000),(b,900)],tier='standard')
        cal=self.calc(self.snap(b,13),sessions)
        self.assertTrue(cal.conflict)
        self.assertEqual(cal.source,'reconciled_baseline')
        self.assertAlmostEqual(cal.prior_credits_per_percent,300)
        self.assertAlmostEqual(cal.credits_per_percent,10900/13)
        self.assertEqual(cal.qualified_intervals,0)
        self.assertTrue(any('MISMATCH' in w for w in cal.warnings))

    def test_unpriced_conflict_is_warned_not_normalized_or_capped(self):
        self.old_prior()
        sessions=self.sessions([(self.now,33000)])
        other=next(iter(self.sessions([(self.now,1)],model='gpt-5.3-codex-spark').values()))
        other.session_id='spark';sessions['spark']=other
        cal=self.calc(self.snap(self.now,62),sessions)
        self.assertEqual(cal.confidence,'CONFLICT')
        self.assertAlmostEqual(cal.credits_per_percent,264.253)
        self.assertGreater(33000/cal.credits_per_percent,100)
        self.assertNotEqual(cal.source,'reconciled_baseline')

    def test_cache_migration_preserves_tokens_legacy_intervals_and_observations(self):
        self.old_prior()
        self.m._record_quota_observation(self.conn,self.auth,self.snap(self.now,20),5000,False)
        before={t:self.conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                ['events','files','quota_intervals','quota_observations']}
        self.conn.execute("INSERT OR REPLACE INTO meta VALUES('sentinel','kept')")
        self.conn.commit();self.conn.close();self.conn=self.m._cache_connect(self.path)
        self.calc(self.snap(self.now,0),{})
        after={t:self.conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
        self.assertEqual(before,after)
        self.assertEqual(self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],'3')
        self.assertEqual(self.conn.execute("SELECT value FROM meta WHERE key='sentinel'").fetchone()[0],'kept')

    def test_replay_is_idempotent_and_adds_no_fake_history(self):
        snaps,sessions=self.audit_fixture()
        cal=self.calc(snaps[-1],sessions)
        before=[tuple(r) for r in self.conn.execute('SELECT * FROM quota_intervals_v2 ORDER BY start_ts')]
        for _ in range(3):self.calc(snaps[-1],sessions)
        after=[tuple(r) for r in self.conn.execute('SELECT * FROM quota_intervals_v2 ORDER BY start_ts')]
        self.assertEqual(before,after)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_intervals').fetchone()[0],2)

    def test_invalid_snapshot_nan_negative_and_outside_window_rejected(self):
        for when,used in [(self.now,float('nan')),(self.now,float('inf')),(self.now,-1),
                          (self.now,101),(self.start-timedelta(seconds=1),1),
                          (datetime.fromtimestamp(self.reset,UTC),1)]:
            self.record(self.snap(when,used))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quota_snapshots').fetchone()[0],0)

    def test_current_data_and_historical_snapshot_have_same_time_alignment(self):
        a=self.start+timedelta(hours=1);b=a+timedelta(hours=1)
        cal=self.calc(self.snap(a,10),self.sessions([(a,5500),(b,20000)]))
        self.assertAlmostEqual(cal.credits_per_percent,550)

    def test_new_rate_revision_does_not_reuse_old_derived_scale(self):
        a=self.start+timedelta(hours=1);b=a+timedelta(hours=1)
        self.record(self.snap(a,0))
        self.calc(self.snap(b,3),self.sessions([(b,1650)],tier='standard'))
        with patch.object(self.m,'RATE_CARD_CALIBRATION_KEY','new-coordinate'):
            # Without replay, stored v2 rows from an old coordinate are unusable.
            cal=self.m.load_quota_calibration(self.conn,self.auth,self.snap(b,3),None,False)
            self.assertEqual(cal.confidence,'SEED')

    def test_weekly_partial_never_claims_mathematical_lower_bound(self):
        cal=self.m.QuotaCalibration(credits_per_percent=550,confidence='LOW')
        self.assertEqual(self.m.weekly_percent_text(550,cal,False),'1.00%?')
        self.assertEqual(self.m.weekly_percent_text(550,cal,True),'1.00%')
        self.assertNotIn('≥',self.m.weekly_percent_text(100000,cal,False))
        self.assertGreater(float(self.m.weekly_percent_text(100000,cal,True).rstrip('%')),100)

    def test_render_details_and_exports_share_scale_partial_semantics(self):
        snaps,sessions=self.audit_fixture();cal=self.calc(snaps[-1],sessions)
        buckets=self.m.make_buckets(sessions,{},self.start,self.now+timedelta(microseconds=1),UTC,False,
                                   trend_start=self.now-timedelta(hours=1))
        credits,complete=self.m.bucket_collection_credits(buckets,sessions,False)
        args=(buckets,sessions,'synthetic 18h',UTC,False,self.now,True,self.auth,snaps[-1],cal,credits)
        doc=json.loads(self.m.render_json(*args))
        self.assertFalse(doc['sessions'][0]['weekly_estimate_is_lower_bound'])
        self.assertTrue(doc['sessions'][0]['weekly_estimate_is_partial'])
        self.assertAlmostEqual(doc['sessions'][0]['weekly_estimate_percent'],credits/cal.credits_per_percent)
        self.assertEqual(doc['subscription']['calibration']['qualified_intervals'],2)
        output=self.m.render_csv(buckets,sessions,False,self.now,True,self.auth,snaps[-1],cal)
        row=list(csv.DictReader(io.StringIO(output)))[0]
        self.assertEqual(row['weekly_estimate_is_lower_bound'],'0')
        self.assertEqual(row['weekly_estimate_is_partial'],'1')
        self.assertEqual(row['calibration_scope'],'current_window')
        with patch.object(self.m.shutil,'get_terminal_size',return_value=os.terminal_size((240,40))):
            text=self.m.render_table(buckets,sessions,'synthetic 18h',UTC,False,True,self.now,True,
                    self.m.Colorizer('never'),wide=True,quota_snapshot=snaps[-1],quota_calibration=cal,
                    quota_local_credits=credits,quota_local_complete=complete)
        self.assertNotIn('≥',text)
        self.assertIn('current window',text)
        self.assertIn('assumed tier',text)
        for line in text.splitlines():
            if line.startswith(('Quota note','Old scale','Unknown tiers','Calibration evidence')):
                self.assertLessEqual(self.m.display_width(line),144)

    def test_latest_snapshot_prefers_codex_over_newer_model_specific_pool(self):
        m=self.m
        good=self.snap(self.now-timedelta(minutes=1),62)
        special=self.snap(self.now,10,pool='spark')
        p1=Path(self.tmp.name)/'a';p2=Path(self.tmp.name)/'b';p1.touch();p2.touch()
        with patch.object(m,'_recent_date_rollouts',return_value=[p1,p2]), \
             patch.object(m,'_recent_state_rollouts',return_value=[]), \
             patch.object(m,'_latest_quota_in_rollout',side_effect=lambda p,_:good if p==p1 else special):
            self.assertEqual(m.read_latest_quota_snapshot(Path(self.tmp.name),UTC).limit_id,'codex')

    def test_old_confidence_counts_not_relabelled_new_clean(self):
        self.old_prior()
        cal=self.calc(self.snap(self.now,0),{})
        self.assertEqual(cal.clean_intervals,0)
        self.assertEqual(cal.confidence,'LOW')
        self.assertEqual(cal.scope,'historical')

    def test_model_fork_accounting_ledger_and_buckets_agree(self):
        parent=self.sessions([(self.start+timedelta(hours=1),1000),(self.now,500)])
        p=next(iter(parent.values()))
        c=self.m.RawSession(session_id='child',path=Path('child.jsonl'),created_at=self.start+timedelta(hours=2),
            parent_id=p.session_id,model_provider='openai',source='subagent')
        c.usage_events=[self.m.UsageEvent(ts=self.now,model='gpt-5.6-luna',cumulative=self.m.Usage(input_tokens=48_000_000,total_tokens=48_000_000),service_tier='unknown')]
        parent['child']=c
        ledger=self.m.QuotaCreditLedger(parent,False)
        buckets=self.m.make_buckets(parent,{},self.start,self.now+timedelta(microseconds=1),UTC,False)
        cost,_=self.m.bucket_collection_credits(buckets,parent,False)
        self.assertAlmostEqual(cost,ledger.between(self.start,self.now).credits)

    def test_zero_read_repeated_cli_with_unknown_interval_and_current_reset(self):
        m=self.m;home=Path(self.tmp.name)/'home'
        now=datetime.now(UTC)
        logs=home/'sessions'/now.strftime('%Y/%m/%d');logs.mkdir(parents=True)
        reset=int((now+timedelta(days=6)).timestamp())
        a=now-timedelta(hours=2);b=now-timedelta(minutes=1)
        self.reset=reset
        self.record(self.snap(a,0))
        records=[
            {'timestamp':a.isoformat(),'type':'session_meta','payload':{'id':'test-cli','model_provider':'openai'}},
            {'timestamp':a.isoformat(),'type':'turn_context','payload':{'model':'gpt-6-astra'}},
            {'timestamp':b.isoformat(),'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':6_600_000,'total_tokens':6_600_000}},
                'rate_limits':{'limit_id':'codex','plan_type':'pro','secondary':{'used_percent':3,'window_minutes':10080,'resets_at':reset}}}},
        ]
        # No auth token; the CLI's fallback account key is local.
        self.conn.execute("UPDATE quota_snapshots SET account_key='local'");self.conn.commit()
        (logs/'rollout-test-cli.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
        script=Path(__file__).resolve().parents[1]/'codex-usage'
        cmd=[sys.executable,str(script),'24h','--codex-home',str(home),'--cache-path',str(self.path),'--json','--perf']
        one=subprocess.run(cmd,text=True,encoding='utf-8',capture_output=True,check=True)
        two=subprocess.run(cmd,text=True,encoding='utf-8',capture_output=True,check=True)
        doc=json.loads(two.stdout)
        self.assertEqual(doc['subscription']['calibration_source'],'current_delta_assumed')
        self.assertAlmostEqual(doc['subscription']['credits_per_weekly_percent'],550)
        self.assertIn('cold=0',two.stderr)
        self.assertIn('read=0.0 MiB',two.stderr)
        self.assertEqual(json.loads(one.stdout)['sessions'],doc['sessions'])

    def test_schema3_without_new_pool_column_migrates_without_token_rescan(self):
        m=self.m
        path=Path(self.tmp.name)/'rollout-019ffabc-1234-7000-8000-123456789abc.jsonl'
        records=[{'timestamp':self.start.isoformat(),'type':'session_meta',
                  'payload':{'id':'019ffabc-1234-7000-8000-123456789abc','model_provider':'openai'}},
                 {'timestamp':self.start.isoformat(),'type':'turn_context',
                  'payload':{'model':'gpt-6-astra','service_tier':'default'}},
                 {'timestamp':self.now.isoformat(),'type':'event_msg','payload':{'type':'token_count',
                  'info':{'total_token_usage':{'input_tokens':1000,'total_tokens':1000}}}}]
        path.write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
        m._scan_file_into_cache(self.conn,path,m.CacheStats())
        self.conn.commit()
        before=[tuple(r) for r in self.conn.execute('SELECT * FROM events')]
        self.assertTrue(before)
        # Recreate the pre-v1.7.4 raw snapshot table: legacy schema 3 lacks limit_id.
        self.conn.execute('DROP TABLE quota_snapshots')
        self.conn.execute('''CREATE TABLE quota_snapshots (
            account_key TEXT NOT NULL,plan_type TEXT NOT NULL,reset_at INTEGER NOT NULL,
            window_minutes INTEGER NOT NULL,snapshot_ts TEXT NOT NULL,used_percent REAL NOT NULL,
            credit_mode TEXT NOT NULL,source TEXT NOT NULL,
            PRIMARY KEY(account_key,plan_type,reset_at,snapshot_ts,credit_mode))''')
        self.conn.execute('DROP TABLE quota_intervals_v2');self.conn.commit()
        self.conn.close();self.conn=m._cache_connect(self.path)
        self.assertIn('limit_id',{r[1] for r in self.conn.execute('PRAGMA table_info(quota_snapshots)')})
        self.assertEqual(before,[tuple(r) for r in self.conn.execute('SELECT * FROM events')])
        stats=m.sync_incremental_cache(self.conn,[path],self.start,self.now+timedelta(seconds=1),False)
        self.assertEqual(stats.bytes_read,0)
        self.assertEqual(stats.cold_scans,0)

    def test_small_quantized_steps_accumulate_into_one_block(self):
        a=self.start+timedelta(hours=1)
        snaps=[self.snap(a+timedelta(minutes=10*i),u) for i,u in enumerate([0,0,1,1,2,2,3,3])]
        self.record(*snaps)
        sessions=self.sessions([(snaps[i].ts,550) for i in (2,4,6)],tier='standard')
        cal=self.calc(snaps[-1],sessions)
        self.assertEqual(cal.clean_intervals,1)
        self.assertEqual(cal.observed_percent_points,3)
        self.assertEqual(cal.confidence,'LOW')
        self.assertAlmostEqual(cal.credits_per_percent,550)

    def test_empty_events_do_not_produce_zero_scale(self):
        cal=self.calc(self.snap(self.now,62),{})
        self.assertEqual(cal.confidence,'SEED')
        self.assertGreater(cal.credits_per_percent,0)
