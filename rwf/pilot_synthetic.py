"""Deterministic synthetic provider/clock. This module never opens a network connection."""
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import unquote, urlsplit

from rwf.probe import Response
from rwf.pilot_state import State, exclusive
from rwf.pilot_runner import Runner
from rwf.pilot_report import summarize


class Clock:
    def __init__(self, value=1800000000.):
        self.value=value

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value+=max(0,seconds)

    def iso(self):
        return datetime.fromtimestamp(self.value,timezone.utc).isoformat()


class Synthetic:
    def __init__(self, state, clock):
        self.s,self.clock=state,clock

    def __call__(self, method, url, headers, body):
        if url.endswith('/token'):
            return Response(200,{},b'{"access_token":"synthetic-token-never-archive","expires_in":3600}')
        intent=self.s.db.execute('SELECT * FROM intent ORDER BY rowid DESC LIMIT 1').fetchone()
        job=self.s.db.execute('SELECT * FROM job WHERE id=?',(intent['job'],)).fetchone()
        tries=self.s.db.execute('SELECT count(*) FROM intent WHERE job=?',(job['id'],)).fetchone()[0]
        p=json.loads(job['params']); op=job['op']; round_=job['round']
        def response(payload,status=200,headers=None):
            return Response(status,headers or {},json.dumps(payload).encode())
        if job['provider']=='blizzard':
            if op=='roster':
                rows=[dict(character=dict(id=i,name=f'Example{i:02}',realm={'slug':'test-one' if i%2 else 'test-two'})) for i in range(1,13)]
                if round_>=1:
                    rows=rows[1:]+[dict(character=dict(id=13,name='Newmember',realm={'slug':'test-two'}))]
                return response(dict(guild={'id':52374740},members=rows))
            if op in ('item','item-set'):
                return response(dict(id=p['item_id'],level=20,items=[]))
            if op in ('specializations','raids'):
                if op=='raids' and round_==0 and tries==1:
                    return response(dict(code=429),429,{'Retry-After':'3'})
                return response(dict(character={'id':100},specializations=[],expansions=[]))
            target=self.s.db.execute('SELECT * FROM target WHERE id=?',(job['target'],)).fetchone()
            pid=target['provider_id']
            if op=='equipment' and pid==3 and round_==1 and tries==1:
                raise URLError('synthetic-sensitive-exception-must-not-persist')
            if op=='equipment' and pid==4 and round_==1 and tries==1:
                return response(dict(error='outage'),503)
            if pid==5 and round_>=4:
                return response(dict(code=404),404)
            observed=999 if pid==6 and round_>=4 else pid
            c=dict(id=observed,name=target['name'],realm={'slug':target['realm']})
            if op=='status':
                return response(dict(id=observed,is_valid=True))
            if op=='character':
                return response(dict(**c,average_item_level=100,equipped_item_level=100,last_login_timestamp=1799999000000))
            item=dict(item={'id':101,'key':{'href':'https://us.api.blizzard.com/data/wow/item/101?namespace=static-test-us'}},
                      slot={'type':'HEAD'},level={'value':101 if pid==2 and round_>=2 else 100},bonus_list=[1,2],
                      set={'item_set':{'id':201,'key':{'href':'https://us.api.blizzard.com/data/wow/item-set/201?namespace=static-test-us'}}})
            if pid==7 and round_>=2:
                item['name']='Cosmetic text'
                item['bonus_list']=[2,1]
            return response(dict(character=c,equipped_items=[item]))
        # Shared-client counter includes non-pilot traffic each hour, exercising conservative accounting.
        hour=int(self.clock()//3600)
        prior=self.s.db.execute("SELECT count(*) FROM intent WHERE provider='wcl' AND at>=?",(hour*3600,)).fetchone()[0]
        rate=dict(limitPerHour=3600,pointsSpentThisHour=10+prior,pointsResetIn=(hour+1)*3600-self.clock())
        data={'rateLimitData':rate}
        if op=='guild':
            page=p['page']
            data['guildData']={'guild':{'id':488971,'members':dict(current_page=page,has_more_pages=page<2,
                data=[dict(id=i,name=f'Example{i:02}',server={'slug':'test-one','region':{'name':'United States'}}) for i in range((page-1)*6+1,page*6+1)])}}
        elif op in ('reports','character-reports'):
            code='PUBLICSYNTHETIC1' if op=='reports' else 'PUBLICSYNTHETIC2'
            page=dict(current_page=p['page'],has_more_pages=False,data=[dict(code=code,visibility='public')])
            if op=='reports':
                data['reportData']={'reports':page}
            else:
                data['characterData']={'character':{'hidden':False,'recentReports':page}}
            if op=='reports' and round_==1:
                return response(dict(data=data,errors=[dict(message='synthetic partial failure',path=['other'])]))
        elif op=='report':
            data['reportData']={'report':dict(code=p['code'],visibility='public',startTime=1799999000000,endTime=1799999001000,
                masterData={'actors':[dict(id=1,gameID=99999,name='Example02',server='Test Two',type='Player')]},
                fights=[dict(id=i,encounterID=1,inProgress=False,startTime=0,endTime=1000,
                    friendlyPlayers=[1],friendlySpecs=[2],friendlyItemLevels=[100]) for i in (1,2)])}
        elif op=='player-details':
            data['reportData']={'report':{'playerDetails':{'data':{'playerDetails':{'dps':[]}}}}}
        elif op=='combatants':
            next_cursor=500 if p['start']==0 else None
            data['reportData']={'report':{'events':dict(data=[dict(timestamp=p['start'],type='combatantinfo',sourceID=1,gear=[])],nextPageTimestamp=next_cursor)}}
        return response(dict(data=data))


class SimulatedCrash(Exception):
    pass


def exercise(directory):
    directory=Path(directory)
    if (directory/'pilot.sqlite').exists():
        raise ValueError('Synthetic scenario needs a new empty data directory')
    directory.mkdir(parents=True,exist_ok=True)
    clock=Clock()
    env={k:'synthetic-credential-never-archive' for k in ('BLIZZARD_CLIENT_ID','BLIZZARD_CLIENT_SECRET','WCL_CLIENT_ID','WCL_CLIENT_SECRET')}
    with exclusive(directory),patch('rwf.probe.utcnow',clock.iso):
        state=State(directory,True,clock)
        runner=Runner(state,Synthetic(state,clock),clock.sleep,clock,env)
        runner.recover()
        runner.step()  # fresh complete baseline and all immutable planned slots
        start=state.get('start')
        def crash(attempt):
            raise SimulatedCrash()
        runner.after_archive=crash
        try:
            runner.step()  # response durable; logical completion deliberately absent
        except SimulatedCrash:
            pass
        before=state.db.execute('SELECT count(*) FROM attempt').fetchone()[0]
        state.close()
        state=State(directory,True,clock)
        runner=Runner(state,Synthetic(state,clock),clock.sleep,clock,env)
        runner.recover()
        assert state.db.execute('SELECT count(*) FROM attempt').fetchone()[0]==before
        # Deliberately pause after guild page 1 is committed and page 2 exists.
        for _ in range(1000):
            if state.db.execute("SELECT 1 FROM job WHERE op='guild' AND state='ok'").fetchone():
                break
            if not runner.step():
                clock.sleep(1)
        else:
            raise AssertionError('Pagination checkpoint was not exercised')
        state.close()
        state=State(directory,True,clock)
        runner=Runner(state,Synthetic(state,clock),clock.sleep,clock,env)
        runner.run(until=start+24*3600)
        state.close()
        # Same persistent archive/slots; tokens and clients are deliberately discarded.
        state=State(directory,True,clock)
        runner=Runner(state,Synthetic(state,clock),clock.sleep,clock,env)
        runner.run()
        asof=state.get('finished')
        state.close()
    report=summarize(directory,asof, directory/'replay-a')
    replay=summarize(directory,asof, directory/'replay-b')
    assert report==replay
    for name in ('equipment','differences','context','wcl','anomalies','timing'):
        assert (directory/'replay-a'/f'{name}.jsonl').read_bytes()==(directory/'replay-b'/f'{name}.jsonl').read_bytes()
    for path in directory.rglob('*'):
        if path.is_file():
            data=path.read_bytes()
            assert b'synthetic-credential-never-archive' not in data
            assert b'synthetic-token-never-archive' not in data
            assert b'synthetic-sensitive-exception-must-not-persist' not in data
    result=dict(synthetic=True,network_calls=0,raw_replay_equal=True,secret_exclusion=True,
        baseline=report['baseline_roster_size'],new_members=report['newly_discovered'],
        departures=report['baseline_departures'],attempts=report['requests']['raw_attempts'],
        restarts=report['restart'],changes=report['equipment']['characters_with_detected_changes'],
        deferrals=len(report['deferrals']),anomalies=report['anomalies'],criteria=report['criteria'])
    (directory/'scenario-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
