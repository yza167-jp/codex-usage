"""One session inventory, without summing incompatible Cloud/local measurements."""
import copy
import csv
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from test_codex_usage import load_module


class UnifiedSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_module()

    def fixture(self):
        m = self.m
        now = datetime(2026, 10, 18, 8, tzinfo=timezone.utc)
        b = m.Bucket('local-id', title='B 本地任务', session_name='B 本地任务', project_name='demo')
        b.add('gpt-6.1-sol', m.Usage(1_000_000, 800_000, 10_000, 1000, 1_010_000),
              b.session_id, source_title=b.title, activity_ts=now-timedelta(minutes=5),
              recent=True, service_tier='standard')
        session = m.RawSession(b.session_id, Path('synthetic.jsonl'), cwd='/tmp/demo', model_provider='openai')
        report = {'data_as_of': now.isoformat(), 'scope': 'lifetime', 'sessions': [
            self.cloud('cloud-id', 'A 云端任务', 56.3304),
            self.cloud('missing-id', 'A 无数据任务', None, 'unavailable'),
        ]}
        return {b.session_id: b}, {session.session_id: session}, now, m.QuotaCalibration(100, 'LOW'), report

    def cloud(self, sid, title, weekly=10.0, status='available', **kw):
        return dict(session_id=sid, title=title, project_name='demo', host='cloud', scope='lifetime',
                    data_status=status, usage_source='backend', weekly_limit_percent=weekly,
                    five_hour_limit_percent=0.0, balance_usage_credits=0.0, groups=[], **kw)

    def render(self, width=144, details=False, wide=False, modify=None, color='never'):
        buckets, sessions, now, cal, report = self.fixture()
        if modify:
            modify(buckets, sessions, report)
        with patch.object(self.m.shutil, 'get_terminal_size', return_value=os.terminal_size((width, 40))):
            return self.m.render_table(buckets, sessions, 'last 12h', timezone.utc, False, details,
                                      now, True, self.m.Colorizer(color), wide=wide,
                                      quota_calibration=cal, cloud_report=report)

    def test_all_summaries_precede_any_details(self):
        text = self.render(details=True)
        first_detail = text.index('DETAILS')
        for title in ('A 云端任务', 'B 本地任务', 'A 无数据任务'):
            self.assertLess(text.index(title), first_detail)
        self.assertEqual(text.count('DETAILS'), 3)
        self.assertNotIn('CLOUD SESSION', text)
        self.assertNotIn('Codex Cloud usage — lifetime', text)

    def test_unified_inventory_sorts_by_project_name_not_cross_scope_amount(self):
        m = self.m
        report = {'sessions': [self.cloud('cheap', 'A 任务', 0.1), self.cloud('expensive', 'Z 任务', 90)]}
        joined = m.join_session_views([{'session_id':'local', 'title':'M 任务', 'project_name':'demo', 'local':{}}], report)
        self.assertEqual([x['session_id'] for x in joined], ['cheap', 'local', 'expensive'])

    def test_missing_data_goes_last_but_remains_visible(self):
        text = self.render()
        self.assertLess(text.index('B 本地任务'), text.index('A 无数据任务'))
        self.assertIn('unavailable', text)

    def test_exact_same_id_is_one_row_one_detail_two_scopes(self):
        def modify(bs, ss, report):
            report['sessions'] = [self.cloud('local-id', 'Remote name', 99.5)]
        text = self.render(details=True, modify=modify)
        self.assertEqual(text.count('DETAILS'), 1)
        self.assertIn('BOTH', text)
        self.assertIn('99.5000%', text)
        self.assertIn('Cloud title: Remote name', text)
        self.assertIn('Local selected-period', text)
        self.assertIn('Cloud lifetime usage', text)

    def test_equal_titles_never_merge_different_ids(self):
        local = [{'session_id':'a', 'title':'same', 'project_name':'demo', 'local':{}}]
        joined = self.m.join_session_views(local, {'sessions':[self.cloud('b','same')]})
        self.assertEqual(len(joined), 2)
        self.assertEqual([e['sources'] for e in joined], [['local'], ['cloud']])

    def test_cloud_subagent_not_folded_into_parent_lifetime(self):
        items = [{'session_id':'root', 'title':'parent', 'project_name':'demo', 'local':{}, 'source_ids':['root','child']}]
        joined = self.m.join_session_views(items, {'sessions':[self.cloud('child','child',100)]})
        child = next(e for e in joined if e['session_id']=='child')
        self.assertIsNone(child['local'])
        self.assertEqual(child['local_rollup_parent'], 'root')
        self.assertEqual(len(joined), 2)

    def test_local_total_is_unchanged_and_lifetime_never_added(self):
        text = self.render()
        line = next(l for l in text.splitlines() if l.startswith('LOCAL TOTAL'))
        self.assertIn('0.14%', line)  # 14.5 reference credits / 100.
        self.assertIn('14.5', line)
        self.assertNotIn('56.3304', line)
        self.assertNotIn('CLOUD TOTAL', text)
        self.assertIn('No combined TOTAL', text)

    def test_no_lifetime_to_period_1h_or_credits_inference(self):
        text = self.render()
        header = next(l for l in text.splitlines() if l.startswith('PROJECT'))
        row = next(l for l in text.splitlines() if 'A 云端任务' in l)
        self.assertIn('PERIOD≈', header)
        self.assertIn('LIFE %', header)
        self.assertIn('56.3304%', row)
        self.assertNotIn('6.1 Sol', row)
        self.assertGreaterEqual(row.count('—'), 5)

    def test_zero_remains_zero_and_unavailable_is_not_zero(self):
        zero = self.cloud('zero','Zero',0)
        unavailable = self.cloud('missing','Missing',0,'unavailable')
        self.assertEqual(self.m.cloud_value_text(zero,'weekly_limit_percent',True),'0.0000%')
        self.assertEqual(self.m.cloud_value_text(unavailable,'weekly_limit_percent',True),'—')
        self.assertEqual(self.m.cloud_value_text(self.cloud('tiny','tiny',0.0000001),'weekly_limit_percent',True),'<0.0001%')

    def test_partial_and_cloud_balance_stay_separate_from_reference(self):
        def modify(bs, ss, report):
            cloud = self.cloud('cloud','C task',8,'partial')
            cloud['balance_usage_credits'] = 777
            report['sessions'] = [cloud]
        text = self.render(details=True, modify=modify)
        self.assertIn('partial', text)
        self.assertIn('BALANCE CREDITS 777.0000', text)
        self.assertNotIn('777', next(l for l in text.splitlines() if l.startswith('LOCAL TOTAL')))

    def test_widths_and_cjk_on_narrow_and_fullscreen(self):
        for width in (80,90,100,115,116,120,132,143,144,240):
            for wide in (False, True):
                with self.subTest(width=width, wide=wide):
                    text = self.render(width=width, wide=wide)
                    for line in text.splitlines():
                        self.assertLessEqual(self.m.display_width(line), min(width,144))
        self.assertEqual(self.render(width=144), self.render(width=240))
        _, widths, gap = self.m._unified_layout(144)
        self.assertGreaterEqual(widths[1],33)
        self.assertEqual(sum(widths)+gap*(len(widths)-1),144)

    def test_wide_preserves_tokens_cache_share_and_cloud_diagnostics(self):
        text = self.render(wide=True)
        for part in ('TOKENS I/C/O', 'CACHE TAX', 'LOCAL SHARE', 'BALANCE CREDITS', 'Cloud lifetime 5H %'):
            self.assertIn(part,text)
        self.assertNotIn('TOKENS I/C/O',self.render())

    def test_color_auto_never_and_always_keep_cell_alignment(self):
        plain = self.render(color='never')
        colored = self.render(color='always')
        self.assertNotIn('\x1b',plain)
        self.assertIn('\x1b',colored)
        self.assertEqual(re.sub(r'\x1b\[[0-9;]*m','',colored),plain)

    def test_remote_metadata_control_sequences_cannot_reach_terminal(self):
        def modify(bs,ss,report):
            row = report['sessions'][0]
            row['title']='bad\x1b]52;c;payload\x07\x9b2J'
            row['project_name']='demo\x1b[2J'
            row['groups']=[{'model':'gpt-unpriced\x1b[2J'}]
            report['data_as_of']='date\x1b[2J'
        text = self.render(modify=modify, details=True)
        for control in ('\x1b','\x07','\x9b'):
            self.assertNotIn(control,text)

    def test_local_model_display_splits_tier_before_terminal_sanitization(self):
        text = self.render()
        self.assertIn('6.1 Sol', text)
        self.assertNotIn('gpt-6.1-solstandard', text)
        self.assertNotIn('1 model', text)

    def test_cloud_model_metadata_only_not_title_guess(self):
        row=self.cloud('x','6.1 Sol guessed in title')
        self.assertEqual(self.m.cloud_models(row),[])
        row['groups']=[{'model':'gpt-6.1-sol'}, {'model':'gpt-6-astra'}, {'model':{'slug':'unknown'}}]
        self.assertEqual(self.m.cloud_models(row),['gpt-6-astra','gpt-6.1-sol'])

    def test_cloud_metadata_missing_project_stays_missing(self):
        row = self.cloud('x','project-name in a title')
        row['project_name']=None
        entries=self.m.join_session_views([],{'sessions':[row]})
        self.assertEqual(entries[0]['project_name'],'')

    def test_json_compatibility_and_additive_join_preserve_raw_records(self):
        bs,ss,now,cal,report=self.fixture()
        local=json.loads(self.m.render_json(bs,ss,'last 12h',timezone.utc,False,now,True,quota_calibration=cal))
        original=copy.deepcopy((local,report))
        report['sessions'].append(self.cloud('local-id','Cloud label',95))
        expected=copy.deepcopy((local,report))
        joined=self.m.unified_json_sessions(local,report)
        e=next(e for e in joined if e['session_id']=='local-id')
        self.assertEqual(e['local_scope'],'selected_period')
        self.assertEqual(e['cloud_scope'],'lifetime')
        self.assertEqual(e['sources'],['local','cloud'])
        self.assertEqual(e['local_usage']['credit_estimate'],14.5)
        self.assertEqual(e['cloud_usage']['weekly_limit_percent'],95)
        self.assertEqual((local,report),expected)
        self.assertNotIn('combined_weekly',e)

    def test_csv_same_thread_two_adjacent_measurement_rows_no_sum(self):
        bs,ss,now,cal,report=self.fixture()
        report['sessions']=[self.cloud('local-id','Different name',50)]
        raw=self.m.render_csv(bs,ss,False,now,True,quota_calibration=cal)
        rows=list(csv.DictReader(io.StringIO(self.m.append_cloud_csv(raw,report))))
        self.assertEqual(len(rows),2)
        self.assertEqual([r['scope'] for r in rows],['selected_period','lifetime'])
        self.assertEqual([r['session_id'] for r in rows],['local-id','local-id'])
        self.assertEqual(rows[1]['credit_estimate'],'')
        self.assertEqual(rows[0]['weekly_limit_percent'],'')
        self.assertEqual(float(rows[1]['weekly_limit_percent']),50)

    def test_empty_local_combined_still_renders_cloud_and_unknown_local_total(self):
        def modify(bs,ss,report):
            bs.clear()
        text=self.render(modify=modify,details=True)
        self.assertIn('A 云端任务',text)
        self.assertIn('LOCAL TOTAL',text)
        self.assertNotIn('No token_count',text)

    def test_empty_cloud_combined_and_both_empty(self):
        def modify(bs,ss,report):
            report['sessions']=[]
        self.assertIn('B 本地任务',self.render(modify=modify))
        def empty(bs,ss,report):
            bs.clear(); report['sessions']=[]
        self.assertIn('No local or Cloud sessions found',self.render(modify=empty))

    def test_cloud_only_details_use_same_renderer_and_no_empty_token_tables(self):
        _,_,_,_,report=self.fixture()
        text=self.m.render_cloud_usage(report,details=True)
        self.assertIn('LIFE %',text)
        self.assertEqual(text.count('DETAILS'),2)
        self.assertNotIn('LOCAL TOTAL',text)
        self.assertNotIn('Model breakdown',text)
        self.assertNotIn('Service tier breakdown',text)

    def test_combined_cli_summary_before_details_no_extra_network_requests(self):
        m=self.m
        _,_,_,_,report=self.fixture()
        with tempfile.TemporaryDirectory() as td:
            out=io.StringIO()
            with patch.object(m,'discover_cloud_threads',return_value=[{'id':'cloud-id'}]) as discover, \
                 patch.object(m,'read_cloud_usage',return_value=report) as read, redirect_stdout(out):
                code=m.main(['12h','--cloud','--no-quota','--no-cache','--details','--codex-home',td,'--color','never'])
            self.assertEqual(code,0)
            self.assertEqual(discover.call_count,1)
            self.assertEqual(read.call_count,1)
            self.assertLess(out.getvalue().index('A 云端任务'),out.getvalue().index('DETAILS'))

    def test_combined_json_keeps_legacy_and_adds_unified_sessions(self):
        m=self.m
        _,_,_,_,report=self.fixture()
        with tempfile.TemporaryDirectory() as td:
            out=io.StringIO()
            with patch.object(m,'read_cloud_usage',return_value=report),redirect_stdout(out):
                self.assertEqual(m.main(['12h','--cloud','--cloud-thread','cloud-id','--no-quota','--no-cache','--json','--codex-home',td]),0)
            output=json.loads(out.getvalue())
            self.assertEqual(output['sessions'],[])
            self.assertEqual(output['cloud_usage'],report)
            self.assertEqual(len(output['unified_sessions']),2)

    def test_local_only_remains_offline_and_legacy_layout(self):
        m=self.m
        with tempfile.TemporaryDirectory() as td,patch.object(m,'read_cloud_usage') as read,patch.object(m,'discover_cloud_threads') as discover:
            out=io.StringIO()
            with redirect_stdout(out):
                m.main(['12h','--no-quota','--no-cache','--codex-home',td])
            read.assert_not_called(); discover.assert_not_called()
        bs,ss,now,cal,_=self.fixture()
        text=m.render_table(bs,ss,'last12h',timezone.utc,False,False,now,True,m.Colorizer('never'),quota_calibration=cal)
        self.assertIn('WEEKLY≈',text)
        self.assertNotIn('LIFE %',text)

    def test_explicit_cloud_project_and_cwd_metadata_survive_usage_read(self):
        m=self.m
        with patch.object(m, '_cloud_request', return_value={'threads':[{'thread_id':'cloud', 'data_status':'available', 'weekly_limit_percent':4}], 'data_as_of':None}):
            r=m.read_cloud_usage(Path('unused'),[{'id':'cloud','title':'task','project_name':'Named project','cwd':r'C:\\work\\repo'}])
        self.assertEqual(r['sessions'][0]['project_name'],'Named project')
        csv_rows=list(csv.DictReader(io.StringIO(m.render_cloud_usage(r,'csv'))))
        self.assertEqual(csv_rows[0]['project_name'],'Named project')
        self.assertEqual(csv_rows[0]['weekly_limit_percent'],'4.0')

    def test_multiple_models_keep_price_order_in_unified_summary(self):
        def modify(bs,ss,report):
            b=bs['local-id']
            b.add('gpt-6-astra', self.m.Usage(100,50,10,0,110), b.session_id, service_tier='standard')
        text=self.render(modify=modify)
        self.assertIn('6 Astra +1',text)
        self.assertIn('Models: 6 Astra / 6.1 Sol',text)

    def test_shared_cloud_unavailable_never_erases_local_usage(self):
        def modify(bs,ss,report):
            report['sessions']=[self.cloud('local-id','same',999,'unavailable')]
        text=self.render(modify=modify)
        self.assertIn('BOTH',text)
        self.assertIn('0.14%',text)
        self.assertNotIn('999',text)
        self.assertIn('Cloud lifetime data: unavailable',text)

    def test_rendering_does_not_mutate_credits_or_cloud_report(self):
        bs,ss,now,cal,report=self.fixture()
        before=(copy.deepcopy(report),self.m.bucket_collection_credits(bs,ss,False))
        self.m.render_table(bs,ss,'last12h',timezone.utc,False,True,now,True,self.m.Colorizer('never'),quota_calibration=cal,cloud_report=report)
        self.assertEqual((report,self.m.bucket_collection_credits(bs,ss,False)),before)


if __name__=='__main__':
    unittest.main()
