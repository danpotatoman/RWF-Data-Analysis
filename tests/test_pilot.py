"""Pilot tests use only synthetic data, clocks, transports and temporary databases."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rwf.probe import Archive, Client, ProbeError, Response
from rwf.pilot import main
from rwf.pilot_state import State, safe_directory, exclusive, key, read_database, VERSION
from rwf.pilot_runner import Runner, Deferred
from rwf.pilot_report import equipment, difference, summarize
from rwf.pilot_synthetic import Clock, Synthetic, SimulatedCrash, exercise


def roster(n=12):
    return dict(guild={'id':52374740},members=[dict(character=dict(id=i,name=f'Character{i:04}',realm={'slug':'realm-'+str(i%2)})) for i in range(1,n+1)])


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.clock=Clock()
        self.s=State(self.root,True,self.clock)
        self.addCleanup(self.s.close)
        self.env={k:'never-store-this-credential' for k in ('BLIZZARD_CLIENT_ID','BLIZZARD_CLIENT_SECRET','WCL_CLIENT_ID','WCL_CLIENT_SECRET')}
        self.patch=patch('rwf.probe.utcnow',self.clock.iso)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.runner=Runner(self.s,Synthetic(self.s,self.clock),self.clock.sleep,self.clock,self.env)

    def baseline(self,n=12):
        with self.s.db:
            self.s.apply_roster(roster(n),'synthetic-baseline')

    def job(self,op='equipment',provider='blizzard',target='test',params=None):
        with self.s.db:
            ident=self.s.job(provider,op,target,0,params or {},self.clock(),self.clock()+3600,10)
        return self.s.db.execute('SELECT * FROM job WHERE id=?',(ident,)).fetchone()

    def test_staggering_thousand_targets_stable_rounds_and_status_window(self):
        self.baseline(1000)
        rows=self.s.db.execute("SELECT planned FROM job WHERE op='equipment' AND round=0 ORDER BY planned").fetchall()
        self.assertEqual(len(rows),1000)
        self.assertAlmostEqual(rows[1][0]-rows[0][0],1.8,places=5)
        self.assertLess(rows[-1][0],self.s.get('start')+1800)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM job WHERE op='equipment'").fetchone()[0],96000)
        status=self.s.db.execute("SELECT min(planned),max(planned) FROM job WHERE op='status' AND round=1").fetchone()
        self.assertEqual(status[0],self.s.get('start')+86400)
        self.assertLess(status[1],self.s.get('start')+108000)
        count=self.s.db.execute('SELECT count(*) FROM job').fetchone()[0]
        with self.s.db:self.s.plan_fixed(self.s.get('start'))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM job').fetchone()[0],count)
        counts={(r[0],r[1]):r[2] for r in self.s.db.execute('SELECT provider,op,count(*) FROM job GROUP BY provider,op')}
        self.assertEqual({k[1]:v for k,v in counts.items() if k[0]=='blizzard'},
            dict(roster=8,equipment=96000,character=8000,status=2000,specializations=6,raids=6))
        self.assertEqual({k[1]:v for k,v in counts.items() if k[0]=='wcl'},
            {'guild':2,'reports':96,'character-reports':80,'rate-limit':49})
        self.assertEqual(count,106247)
        self.assertEqual(self.s.db.execute("SELECT count(DISTINCT round) FROM job WHERE op='equipment'").fetchone()[0],96)

    def test_sleep_inside_real_client_pacing_rechecks_snapshot_deadline(self):
        job=self.job()
        def wake_after_sleep(seconds):self.clock.sleep(181)
        def forbidden(*args):self.fail('Expired request reached transport')
        client=Client('blizzard',self.s.archive,transport=forbidden,sleep=wake_after_sleep,clock=self.clock,environ=self.env)
        client.token='synthetic-credential-never-archive';client.expires=self.clock()+1000;client.last_sent=self.clock()
        with self.assertRaisesRegex(Deferred,'snapshot_window_expired'):
            client.request('https://us.api.blizzard.com/profile/wow/character/test/test/equipment',max_attempts=1,
                before_attempt=lambda aid,desc:self.runner.reserve(job,aid,desc))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM intent').fetchone()[0],0)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM attempt').fetchone()[0],0)

    def test_thousand_target_window_keeps_equipment_ahead_of_context(self):
        self.baseline(1000)
        with self.s.db:
            self.s.db.execute("UPDATE job SET state='ok' WHERE op='roster' AND round=0")
        self.runner.run(until=self.s.get('start')+1800)
        completed=self.s.db.execute("SELECT count(*) FROM job WHERE op='equipment' AND round=0 AND state='ok'").fetchone()[0]
        self.assertGreaterEqual(completed,950)
        sends=[r[0] for r in self.s.db.execute("SELECT i.at FROM intent i JOIN job j ON j.id=i.job WHERE j.op='equipment' ORDER BY i.at")]
        self.assertGreater(sends[-1]-sends[0],1700)
        self.assertTrue(all(b-a>=.5 for a,b in zip(sends,sends[1:])))

    def test_several_hours_late_resume_expires_old_snapshots_not_history(self):
        self.runner.step()
        self.clock.sleep(3*3600+900)
        resumed=self.clock();self.runner.recover()
        for _ in range(30):
            if not self.runner.step():self.clock.sleep(1)
        self.assertTrue(self.s.db.execute("SELECT 1 FROM job WHERE op='equipment' AND state='missed' AND reason='snapshot_window_expired'").fetchone())
        for row in self.s.db.execute("SELECT i.at,j.planned,j.deadline FROM intent i JOIN job j ON j.id=i.job WHERE j.op='equipment' AND i.at>=?",(resumed,)):
            self.assertLess(row['at']-row['planned'],120)
            self.assertLess(row['at'],row['deadline'])
        report=summarize(self.root,self.clock())
        self.assertGreater(report['timing_by_operation']['blizzard:equipment']['missed_expired_historical_snapshot'],0)

    def test_hour48_guard_rejects_selected_equipment_and_end_context_has_bound(self):
        self.baseline(1)
        end=self.s.get('end')
        with self.s.db:
            ident=self.s.job('blizzard','equipment','test-boundary',95,{},end-60,end,10)
        job=self.s.db.execute('SELECT * FROM job WHERE id=?',(ident,)).fetchone()
        self.clock.value=end
        with self.assertRaisesRegex(Deferred,'snapshot_window_expired'):self.runner.reserve(job,'expired',{})
        final=self.s.db.execute("SELECT * FROM job WHERE op='raids' AND round=1 LIMIT 1").fetchone()
        self.assertLessEqual(final['deadline'],end+3600)

    def test_optional_wcl_preserves_future_core_capacity(self):
        optional=self.job('report','wcl',target='optional')
        core=self.job('reports','wcl',target='core')
        with self.s.db:
            self.s.db.execute('INSERT INTO intent(id,job,provider,at,reserved,charged) VALUES (?,?,?,?,?,?)',
                ('spent',core['id'],'wcl',self.clock()-10,48,48))
            self.s.db.execute('INSERT INTO rate VALUES (?,?,?,?,?,?)',('r',self.clock(),50,3600,self.clock()+3600,1))
        with self.assertRaisesRegex(Deferred,'optional_reserve'):self.runner.reserve(optional,'optional-send',{})
        # The historical high account delta belongs to a different operation; fresh core observation
        # remains available from the ten-point reserve.
        monitor=self.job('rate-limit','wcl',target='core-monitor')
        self.runner.reserve(monitor,'monitor-send',{})

    def test_old_external_point_spike_does_not_permanently_disable_monitoring(self):
        monitor=self.job('rate-limit','wcl')
        with self.s.db:
            self.s.db.execute('INSERT INTO intent(id,job,provider,at,reserved,charged) VALUES (?,?,?,?,?,?)',
                ('old-spike',monitor['id'],'wcl',self.clock()-3601,1,1000))
        self.runner.reserve(monitor,'fresh-monitor',{})

    def test_archive_idempotence_with_pilot_row_factory(self):
        response=Response(200,{},b'{"synthetic":true}')
        for _ in range(2):self.s.archive.save('same','blizzard',{},'now',response)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM attempt').fetchone()[0],1)

    def test_live_cli_default_http_wiring_without_network(self):
        """Use actual Client/send/urllib Request path; replace only the HTTP opener."""
        fresh=self.root/'live-wiring'
        calls=[]
        class HTTPResponse:
            def __init__(self,value):
                self.status=200;self.headers={'Set-Cookie':'NEVER-SAVE-COOKIE'};self.value=value
            def read(self):return json.dumps(self.value).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Opener:
            def open(inner,request,timeout):
                calls.append((request.full_url,request.get_method()))
                if request.full_url.endswith('/token'):
                    return HTTPResponse({'access_token':'NEVER-SAVE-LIVE-WIRING-TOKEN','expires_in':3600})
                if '/roster?' in request.full_url:return HTTPResponse(roster(1))
                if '/equipment?' in request.full_url:
                    (fresh/'STOP').write_text('test complete')
                    return HTTPResponse(dict(character={'id':1},equipped_items=[dict(item={'id':1},slot={'type':'HEAD'},level={'value':10})]))
                self.fail('Unexpected wiring request')
        with patch.dict(os.environ,self.env),patch('rwf.probe.build_opener',return_value=Opener()),\
             patch('rwf.pilot.State',side_effect=lambda p:State(p,False,self.clock)),\
             patch('rwf.pilot.Runner',side_effect=lambda s:Runner(s,sleep=self.clock.sleep,monotonic=self.clock)),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['run','--data-dir',str(fresh)]),0)
        db=read_database(fresh)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM attempt').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM target').fetchone()[0],1)
            dump='\n'.join(db.iterdump())
            raw=b'\n'.join(r[0] for r in db.execute('SELECT content FROM body'))
            for secret in ('NEVER-SAVE-LIVE-WIRING-TOKEN','never-store-this-credential','NEVER-SAVE-COOKIE','Authorization'):
                self.assertNotIn(secret,dump)
                self.assertNotIn(secret.encode(),raw)
        finally:db.close()
        self.assertEqual(len(calls),3)

    def test_population_cap_preserves_all_targets_and_denominators(self):
        self.baseline(1201)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM target').fetchone()[0],1201)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM target WHERE active=0').fetchone()[0],1)
        t=self.s.db.execute('SELECT * FROM target WHERE active=0').fetchone()
        self.assertEqual(t['deferred'],'population_cap')
        j=self.s.db.execute("SELECT * FROM job WHERE target=? AND op='equipment' LIMIT 1",(t['id'],)).fetchone()
        with self.assertRaisesRegex(Deferred,'population_cap'):self.runner.request(j)

    def test_new_members_and_departures_do_not_rewrite_baseline(self):
        self.baseline(2); self.clock.sleep(21600)
        value=roster(3); value['members']=value['members'][1:]
        with self.s.db:self.s.apply_roster(value,'second')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM target WHERE baseline=1').fetchone()[0],2)
        gone=self.s.db.execute('SELECT * FROM target WHERE provider_id=1').fetchone()
        self.assertEqual((gone['present'],gone['active']),(0,1))
        new=self.s.db.execute('SELECT * FROM target WHERE provider_id=3').fetchone()
        self.assertEqual((new['baseline'],new['reason']),(0,'new_roster_member'))
        checks=self.s.db.execute("SELECT * FROM job WHERE target=? AND round=-1",(new['id'],)).fetchall()
        self.assertEqual(len(checks),2)
        self.assertTrue(all(j['planned']>self.clock() for j in checks))

    def test_roster_address_conflicts_preserved_and_quarantined(self):
        self.baseline(1)
        changed=roster(1); changed['members'][0]['character']['id']=99
        with self.s.db:self.s.apply_roster(changed,'changed')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM target').fetchone()[0],2)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM target WHERE active=0').fetchone()[0],2)

    def test_wrong_guild_and_empty_roster_rejected(self):
        for value in [dict(guild={'id':7},members=roster(1)['members']),dict(guild={'id':52374740},members=[])]:
            with self.assertRaises(ValueError):
                with self.s.db:self.s.apply_roster(value,'bad')
        self.assertIsNone(self.s.get('start'))

    def test_blizzard_retry_reservations_and_hourly_budget(self):
        job=self.job()
        with self.s.db:
            config=self.s.get('config'); config['blizzard_hourly']=2; self.s.put('config',config)
        self.runner.reserve(job,'a',{})
        with self.assertRaisesRegex(Deferred,'send_rate'):self.runner.reserve(job,'b',{})
        self.clock.sleep(1); self.runner.reserve(job,'b',{})
        self.clock.sleep(1)
        with self.assertRaisesRegex(Deferred,'hourly_budget'):self.runner.reserve(job,'c',{})
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM intent').fetchone()[0],2)

    def test_metadata_cap_counts_every_attempt(self):
        job=self.job('item',params={'item_id':1})
        with self.s.db:
            self.s.db.executemany('INSERT INTO intent(id,job,provider,at,reserved) VALUES (?,?,?,?,?)',
                [(str(i),job['id'],'blizzard',self.clock()-4000,0) for i in range(500)])
        with self.assertRaisesRegex(Deferred,'metadata_call_cap'):self.runner.reserve(job,'new',{})

    def test_wcl_unknown_budget_requires_observation(self):
        job=self.job('reports','wcl')
        with self.assertRaisesRegex(Deferred,'rate_observation_required'):self.runner.reserve(job,'first',{})
        self.assertTrue(self.s.db.execute("SELECT 1 FROM job WHERE op='rate-limit'").fetchone())

    def test_wcl_provider_headroom_and_other_client_activity(self):
        job=self.job('report','wcl')
        with self.s.db:self.s.db.execute('INSERT INTO rate VALUES (?,?,?,?,?,?)',('rate',self.clock(),2900,3600,self.clock()+100,1000))
        with self.assertRaisesRegex(Deferred,'provider_headroom'):self.runner.reserve(job,'new',{})

    def test_wcl_local_budget_includes_monitoring_and_reservations(self):
        job=self.job('rate-limit','wcl')
        with self.s.db:
            self.s.db.execute('INSERT INTO intent(id,job,provider,at,reserved,charged) VALUES (?,?,?,?,?,?)',('used',job['id'],'wcl',self.clock()-1,1,60))
        with self.assertRaisesRegex(Deferred,'local_budget'):self.runner.reserve(job,'new',{})

    def test_429_cooldown_blocks_all_blizzard_operations(self):
        job=self.job('character'); row={'id':'a','sent':self.clock(),'status':429}
        with self.s.db:self.runner.observe_budget(job,row,{}, {'retry-after':'120'})
        with self.assertRaisesRegex(Deferred,'provider_cooldown'):self.runner.reserve(job,'new',{})
        self.clock.sleep(121); self.runner.reserve(job,'new',{})

    def test_public_report_guard_rejects_undiscovered_code(self):
        job=self.job('report','wcl',params={'code':'NOTDISCOVERED'})
        with self.assertRaisesRegex(Deferred,'not_known_public'):self.runner.request(job)

    def test_report_selection_and_fight_limits(self):
        self.baseline(1)
        with self.s.db:
            for i in range(5):self.runner.discover_report('PUBLIC'+str(i),'reports','evidence')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM public_report WHERE selected=1').fetchone()[0],3)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM public_report').fetchone()[0],5)
        report=dict(code='PUBLIC0',startTime=0,endTime=1000,masterData={'actors':[]},
            fights=[dict(id=i,encounterID=1,startTime=0,endTime=1000,friendlyPlayers=[],friendlySpecs=[],friendlyItemLevels=[]) for i in range(30)])
        with self.s.db:self.runner.select_fights(report,{},'evidence')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM selected_fight').fetchone()[0],20)

    def test_crash_after_raw_reapplies_without_another_http_call(self):
        def crash(attempt):raise SimulatedCrash()
        self.runner.after_archive=crash
        with self.assertRaises(SimulatedCrash):self.runner.step()
        before=self.s.db.execute('SELECT count(*) FROM attempt').fetchone()[0]
        self.assertIsNone(self.s.get('start'))
        self.runner.recover()
        self.assertIsNotNone(self.s.get('start'))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM attempt').fetchone()[0],before)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM intent WHERE applied=0').fetchone()[0],0)
        self.assertTrue(self.s.db.execute("SELECT 1 FROM event WHERE kind='recovered_observation'").fetchone())

    def test_indeterminate_send_is_accounted_on_recovery(self):
        job=self.job()
        self.runner.reserve(job,'no-response',{})
        self.runner.recover()
        self.assertTrue(self.s.db.execute("SELECT 1 FROM event WHERE kind='indeterminate_send'").fetchone())
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM attempt').fetchone()[0],0)

    def test_pagination_checkpoint_and_invalid_cursor(self):
        self.baseline(1)
        job=self.s.db.execute("SELECT * FROM job WHERE op='guild' LIMIT 1").fetchone()
        payload={'data':{'guildData':{'guild':{'id':488971,'members':dict(current_page=1,has_more_pages=True,data=[])}}}}
        with self.s.db:self.runner.process(job,payload,'page1')
        nextpage=self.s.db.execute("SELECT * FROM job WHERE op='guild' AND round=0 AND id!=?",(job['id'],)).fetchone()
        self.assertEqual(json.loads(nextpage['params'])['page'],2)
        with self.s.db:self.runner.process(job,payload,'page1')
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM job WHERE op='guild' AND round=0").fetchone()[0],2)
        ev=self.job('combatants','wcl','public:1',dict(code='public',start=10,end=100))
        for cursor in [10,9,101,True,'20']:
            with self.assertRaises(ValueError):self.runner.process(ev,{'data':{'reportData':{'report':{'events':dict(data=[],nextPageTimestamp=cursor)}}}},'invalid')
        with self.s.db:self.runner.process(ev,{'data':{'reportData':{'report':{'events':dict(data=[{}]*848,nextPageTimestamp=None)}}}},'terminal')

    def test_metadata_build_scoped_and_not_arbitrary_href(self):
        self.baseline(1)
        with self.s.db:
            for build in ('static-a-us','static-b-us'):
                self.runner.metadata({'item':{'id':12,'key':{'href':'https://evil.invalid/data?namespace='+build}}},'equipment')
        rows=self.s.db.execute("SELECT * FROM job WHERE op='item'").fetchall()
        self.assertEqual(len(rows),2)
        for row in rows:
            url,_=self.runner.request(row)
            self.assertTrue(url.startswith('https://us.api.blizzard.com/'))

    def test_mode_mismatch_fails(self):
        with self.assertRaisesRegex(ProbeError,'mode mismatch'):State(self.root,False,self.clock)

    def test_lock_excludes_second_writer(self):
        with exclusive(self.root):
            with self.assertRaisesRegex(ProbeError,'lock'):
                with exclusive(self.root):pass

    def test_status_is_read_only_and_no_api_calls(self):
        before=list(self.s.db.iterdump())
        with patch('rwf.probe.send',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['status','--data-dir',str(self.root)]),0)
        self.assertEqual(list(self.s.db.iterdump()),before)
        db=read_database(self.root)
        try:
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM job')
        finally:db.close()

    def test_backup_is_consistent_and_refuses_overwrite(self):
        out=self.root/'backup.sqlite'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['backup','--data-dir',str(self.root),'--output',str(out)]),0)
            self.assertEqual(main(['backup','--data-dir',str(self.root),'--output',str(out)]),2)
        db=sqlite3.connect(out)
        try:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        finally:db.close()

    def test_backup_restore_recovers_archived_unapplied_baseline(self):
        def crash(attempt):raise SimulatedCrash()
        self.runner.after_archive=crash
        with self.assertRaises(SimulatedCrash):self.runner.step()
        restored=self.root/'restored';restored.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['backup','--data-dir',str(self.root),'--output',str(restored/'pilot.sqlite')]),0)
        state=State(restored,True,self.clock)
        try:
            runner=Runner(state,lambda *args:self.fail('Restore should use saved response'),self.clock.sleep,self.clock,self.env)
            runner.recover()
            self.assertEqual(state.db.execute('SELECT count(*) FROM target').fetchone()[0],12)
            self.assertEqual(state.db.execute('SELECT count(*) FROM attempt').fetchone()[0],1)
        finally:state.close()

    def test_deadlines_record_misses_and_stop_is_resumable(self):
        self.runner.step()
        (self.root/'STOP').write_text('stop')
        self.runner.run()
        self.assertEqual(self.s.get('status'),'paused')
        (self.root/'STOP').unlink()
        self.clock.sleep(4000)
        self.runner.recover();self.runner.step()
        self.assertTrue(self.s.db.execute("SELECT 1 FROM job WHERE state='missed' AND reason='deadline_elapsed'").fetchone())

    def test_code_change_blocks_resume_without_changing_original_evidence(self):
        with patch('rwf.pilot_state.code_signature',return_value='different'):
            with self.assertRaisesRegex(ProbeError,'code changed'):State(self.root,True,self.clock)

    def test_one_attempt_401_invalidates_cached_token(self):
        values=iter([Response(200,{},b'{"access_token":"once","expires_in":3600}'),Response(401,{},b'{}')])
        client=Client('wcl',self.s.archive,transport=lambda *args:next(values),sleep=lambda _:None,environ=self.env)
        with self.assertRaises(ProbeError):client.request('https://www.warcraftlogs.com/api/v2/client',{},max_attempts=1)
        self.assertIsNone(client.token)

    def test_failed_bootstrap_cli_returns_failure_without_a_fake_baseline(self):
        def transport(method,url,headers,body):
            if url.endswith('/token'):
                return Response(200,{},b'{"access_token":"temporary","expires_in":3600}')
            return Response(404,{},b'{"code":404}')
        fresh=self.root/'failed-bootstrap'
        with patch.dict(os.environ,self.env),patch('rwf.pilot.State',side_effect=lambda p:State(p,True,self.clock)),\
             patch('rwf.pilot.Runner',side_effect=lambda s:Runner(s,transport,self.clock.sleep,self.clock,self.env)),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['run','--data-dir',str(fresh)]),2)
        db=read_database(fresh)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM target').fetchone()[0],0)
            self.assertIsNone(db.execute("SELECT value FROM meta WHERE key='start'").fetchone())
        finally:db.close()


class ProjectionTests(unittest.TestCase):
    def sample(self):
        return dict(equipped_items=[dict(item={'id':1},slot={'type':'HEAD'},level={'value':10},bonus_list=[1,2])])

    def test_changes_are_categorized_and_order_text_ignored_semantically(self):
        original=self.sample(); _,a=equipment(original)
        cosmetic=self.sample(); cosmetic['equipped_items'][0].update(name='display',bonus_list=[2,1])
        _,b=equipment(cosmetic)
        self.assertEqual(difference(a,b),[])
        changed=self.sample(); changed['equipped_items'][0]['level']['value']=11
        _,c=equipment(changed)
        self.assertEqual([d['category'] for d in difference(a,c)],['item_level'])

    def test_missing_null_empty_and_duplicate_slots(self):
        sigs=[]
        for state in ('missing',None,[]):
            value=self.sample()
            if state!='missing':value['equipped_items'][0]['sockets']=state
            sigs.append(equipment(value)[1])
        self.assertTrue(difference(sigs[0],sigs[1])); self.assertTrue(difference(sigs[1],sigs[2]))
        value=self.sample(); value['equipped_items']*=2
        with self.assertRaises(ValueError):equipment(value)
        with self.assertRaises(ValueError):equipment({})

    def test_path_safety_live_vs_synthetic(self):
        project=Path(__file__).resolve().parents[1]
        with self.assertRaises(ProbeError):safe_directory(project/'data'/'live')
        with self.assertRaises(ProbeError):safe_directory(None)
        with self.assertRaises(ProbeError):safe_directory('relative')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaises(ProbeError):safe_directory(root/'OneDrive - Company'/'pilot')
            with patch.dict(os.environ,{'OneDriveCommercial':str(root/'sync-root')}):
                with self.assertRaises(ProbeError):safe_directory(root/'sync-root'/'pilot')
            self.assertEqual(safe_directory(root/'local'),(root/'local').resolve())
        self.assertEqual(safe_directory(project/'data'/'synthetic',True),(project/'data'/'synthetic').resolve())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['run','--data-dir',str(project/'data'/'live-forbidden')]),2)
        self.assertIn('outside project',output.getvalue())

    def test_complete_accelerated_recovery_scenario(self):
        with tempfile.TemporaryDirectory() as td,patch('rwf.probe.send',side_effect=AssertionError('network forbidden')):
            result=exercise(Path(td))
            self.assertTrue(result['raw_replay_equal']); self.assertTrue(result['secret_exclusion'])
            self.assertEqual((result['baseline'],result['new_members'],result['departures']),(12,1,1))
            self.assertGreater(result['changes'],0)
            self.assertGreater(result['restarts']['session_count'],2)
            self.assertGreater(result['restarts']['recovery_reapplications'],0)
            self.assertGreater(result['deferrals'],0)
            self.assertFalse(result['criteria']['provisional'])
            # The intentionally unavailable/quarantined targets must cause honest failures, not
            # disappear from denominators to make the 95% thresholds pass.
            self.assertFalse(result['criteria']['baseline_completion_95'])
            report=json.loads((Path(td)/'replay-a'/'report.json').read_text())
            self.assertGreater(report['equipment']['unchanged'],0)
            self.assertGreater(report['equipment']['cosmetic_text_or_order_only'],0)
            self.assertIn('wcl:200',report['requests']['status_distribution'])
            self.assertGreater(report['requests']['status_distribution']['blizzard:429'],0)
            self.assertGreater(report['requests']['retries_or_duplicate_sends'],0)
            self.assertLessEqual(report['requests']['peak_rolling_hour_api_attempts']['blizzard'],3000)
            self.assertTrue(any(c['complete'] and c['accepted_pages']==2 for c in report['pagination_chains'] if c['operation']=='guild'))
            self.assertTrue(any(not c['complete'] for c in report['pagination_chains'] if c['operation']=='reports'))
            self.assertTrue(any(c['complete'] and c['accepted_pages']==2 for c in report['pagination_chains'] if c['operation']=='combatants'))
            self.assertTrue(report['per_equipment_round'])
            comparisons=report['wcl']['roster_comparisons']
            self.assertEqual(len(comparisons),2)
            self.assertTrue(all(c['complete'] for c in comparisons))
            self.assertEqual([c['counts']['overlap'] for c in comparisons],[6,5])
            self.assertEqual([c['counts']['wcl_only'] for c in comparisons],[6,7])
            self.assertEqual([c['counts']['blizzard_only'] for c in comparisons],[6,7])
            self.assertLess(comparisons[1]['blizzard_observed_at'],comparisons[1]['wcl_observation_interval'][0])
            # Each output observation and adjacent-snapshot pointer resolves in the raw archive.
            db=sqlite3.connect(Path(td)/'pilot.sqlite')
            observations={r[0] for r in db.execute('SELECT id FROM attempt')};db.close()
            for name in ('equipment','differences','context','wcl'):
                for line in (Path(td)/'replay-a'/f'{name}.jsonl').read_text().splitlines():
                    row=json.loads(line)
                    self.assertIn(row['observation'],observations)
                    self.assertEqual(row['version'],VERSION)
                    if row.get('previous_observation'):self.assertIn(row['previous_observation'],observations)
            # Replay uses raw rate responses even if a disposable operational rate cache is absent.
            db=sqlite3.connect(Path(td)/'pilot.sqlite'); db.execute('DELETE FROM rate');db.commit();db.close()
            replay=summarize(Path(td),report['as_of'])
            self.assertEqual(replay['wcl'],report['wcl'])


class ClientHookTests(unittest.TestCase):
    def test_single_attempt_hook_and_context_do_not_archive_oauth(self):
        archive=Archive(':memory:')
        try:
            values=iter([Response(200,{},b'{"access_token":"TOKENEXCLUDED","expires_in":3600}'),Response(503,{},b'{}')])
            intents=[]
            c=Client('wcl',archive,transport=lambda *args:next(values),sleep=lambda _:None,
                     environ={'WCL_CLIENT_ID':'synthetic-credential-never-archive','WCL_CLIENT_SECRET':'synthetic-credential-never-archive'})
            with self.assertRaises(ProbeError):c.request('https://www.warcraftlogs.com/api/v2/client',{'query':'query{rateLimitData{limitPerHour}}'},
                max_attempts=1,before_attempt=lambda aid,desc:intents.append(aid),context={'job':'synthetic-job'})
            self.assertEqual(len(intents),1)
            row=archive.db.execute('SELECT id,request_json FROM attempt').fetchone()
            self.assertEqual(row[0],intents[0]);self.assertIn('synthetic-job',row[1])
            dump='\n'.join(archive.db.iterdump())
            for secret in ['TOKENEXCLUDED','IDEXCLUDED','SECRETEXCLUDED']:self.assertNotIn(secret,dump)
            with self.assertRaisesRegex(ProbeError,'retry allowance'):c.request('x',max_attempts=0)
        finally:archive.close()

    def test_hook_can_defer_without_an_api_send_or_fake_observation(self):
        archive=Archive(':memory:'); calls=[]
        try:
            def transport(*args):
                calls.append(args[1]);return Response(200,{},b'{"access_token":"temporary","expires_in":3600}')
            c=Client('wcl',archive,transport=transport,environ={'WCL_CLIENT_ID':'synthetic-credential-never-archive','WCL_CLIENT_SECRET':'synthetic-credential-never-archive'})
            def block(*args):raise Deferred('budget',100)
            with self.assertRaises(Deferred):c.request('https://www.warcraftlogs.com/api/v2/client',{},before_attempt=block)
            self.assertEqual(len(calls),1)
            self.assertEqual(archive.db.execute('SELECT count(*) FROM attempt').fetchone()[0],0)
        finally:archive.close()
