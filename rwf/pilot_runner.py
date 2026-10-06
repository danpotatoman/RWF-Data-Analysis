"""Single-process worker for fixed pilot slots. No production scheduling service."""
import json
import math
import time
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from rwf.probe import Client, ProbeError, blizzard_url, retry_delay
from rwf.pilot_state import DURATION, GRACE, VERSION, dumps, key, SNAPSHOT_LAG

WCL_URL = 'https://www.warcraftlogs.com/api/v2/client'


class Deferred(ProbeError):
    def __init__(self, reason, until):
        super().__init__(reason)
        self.reason, self.until = reason, until


class Runner:
    def __init__(self, state, transport=None, sleep=time.sleep, monotonic=time.monotonic, environ=None):
        self.s, self.db = state, state.db
        self.clock, self.sleep = state.clock, sleep
        self.clients = {}
        self.client_args = dict(sleep=sleep, clock=monotonic, environ=environ)
        if transport is not None:
            self.client_args['transport'] = transport
        self.after_archive = None  # Test-only crash injection boundary, before logical commit.

    def client(self, provider):
        if provider not in self.clients:
            self.clients[provider] = Client(provider,self.s.archive,**self.client_args)
        return self.clients[provider]

    def recover(self):
        """Reapply archived-but-uncommitted results before considering any new sends."""
        with self.db:
            sessions=self.db.execute("SELECT count(*) FROM event WHERE kind='session_start'").fetchone()[0]
            self.s.event('session_start',dict(restart=bool(sessions)))
            self.s.put('status','collecting' if self.s.get('start') is not None else 'awaiting_baseline')
        for intent in self.db.execute('SELECT * FROM intent WHERE applied=0 ORDER BY at,id').fetchall():
            raw=self.db.execute('SELECT id FROM attempt WHERE id=?',(intent['id'],)).fetchone()
            if raw:
                self.apply(intent['id'])
                with self.db:
                    self.s.event('recovered_observation',dict(attempt=intent['id'],job=intent['job']),key('recovered',intent['id']))
            else:
                with self.db:
                    self.s.event('indeterminate_send',dict(attempt=intent['id'],job=intent['job']),key('indeterminate',intent['id']))
                    self.db.execute('UPDATE intent SET applied=1 WHERE id=?',(intent['id'],))
                    self.db.execute("UPDATE job SET state='pending',ready=? WHERE id=?",(self.clock(),intent['job']))
        with self.db:
            self.db.execute("UPDATE job SET state='pending' WHERE state='running'")

    def reserve(self, job, attempt_id, descriptor):
        now=self.clock()
        provider=job['provider']
        # Called after OAuth AND the client's pacing sleep. Suspend/resume must not send an
        # expired snapshot even if it occurred while an already-selected request was waiting.
        if now>=job['deadline']:
            reason='snapshot_window_expired' if provider=='blizzard' and job['op'] in SNAPSHOT_LAG else 'deadline_elapsed'
            raise Deferred(reason,now)
        if (self.s.directory/'STOP').exists():
            raise Deferred('operator_stop',now+30)
        pause=self.s.get('pause_'+provider,0)
        if now < pause:
            raise Deferred('provider_cooldown',pause)
        if provider=='blizzard':
            count=self.db.execute("SELECT count(*) FROM intent WHERE provider='blizzard' AND at>?",(now-3600,)).fetchone()[0]
            if count>=self.s.get('config')['blizzard_hourly']:
                oldest=self.db.execute("SELECT min(at) FROM intent WHERE provider='blizzard' AND at>?",(now-3600,)).fetchone()[0]
                raise Deferred('blizzard_hourly_budget',oldest+3600.01)
            last=self.db.execute("SELECT max(at) FROM intent WHERE provider='blizzard'").fetchone()[0]
            if last is not None and now-last<.5:
                raise Deferred('blizzard_send_rate',last+.5)
            if job['op'] in ('item','item-set'):
                count=self.db.execute("SELECT count(*) FROM intent i JOIN job j ON i.job=j.id WHERE j.op IN ('item','item-set')").fetchone()[0]
                if count>=500:
                    raise Deferred('metadata_call_cap',job['deadline']+.01)
            reserved=0
        else:
            # Reserve pessimistically, then charge at least observed account deltas. Shared-client
            # activity is conservatively included; this is not exact per-query attribution.
            historical=self.db.execute('''SELECT max(i.charged) FROM intent i JOIN job j ON j.id=i.job
                                          WHERE j.provider='wcl' AND j.op=? AND i.at>?''',(job['op'],now-3600)).fetchone()[0]
            default={'rate-limit':1,'guild':3.1,'combatants':6,'report':4,'player-details':4}.get(job['op'],3)
            reserved=max(default,(historical or 0)+(.5 if job['op']=='rate-limit' else 1))
            used=self.db.execute("SELECT coalesce(sum(max(reserved,coalesce(charged,0))),0) FROM intent WHERE provider='wcl' AND at>?",(now-3600,)).fetchone()[0]
            if used+reserved>self.s.get('config')['wcl_hourly']:
                oldest=self.db.execute("SELECT min(at) FROM intent WHERE provider='wcl' AND at>?",(now-3600,)).fetchone()[0]
                raise Deferred('wcl_local_budget',(oldest or now)+3600.01)
            if job['op'] in ('report','player-details','combatants') and used+reserved>self.s.get('config')['wcl_hourly']-10:
                oldest=self.db.execute("SELECT min(at) FROM intent WHERE provider='wcl' AND at>?",(now-3600,)).fetchone()[0]
                raise Deferred('wcl_optional_reserve',(oldest or now)+3600.01)
            rate=self.db.execute('SELECT * FROM rate ORDER BY at DESC,rowid DESC LIMIT 1').fetchone()
            if job['op']!='rate-limit':
                if rate is None or now-rate['at']>3600 or now>=rate['reset_at']:
                    self.ensure_rate(now)
                    raise Deferred('wcl_rate_observation_required',now+5)
            if rate and now<rate['reset_at'] and rate['allowance']-rate['spent']-reserved<rate['allowance']*.2:
                raise Deferred('wcl_provider_headroom',rate['reset_at']+.1)
        # Each reservation survives a crash before/after the send. A missing response is explicitly
        # indeterminate, not silently invented as a failed HTTP response.
        with self.db:
            self.db.execute('INSERT INTO intent(id,job,provider,at,reserved) VALUES (?,?,?,?,?)',
                            (attempt_id,job['id'],provider,now,reserved))

    def ensure_rate(self, now):
        with self.db:
            self.s.job('wcl','rate-limit','extra',int(now//60),{},now,now+3600,1)

    def request(self, job):
        p=json.loads(job['params'])
        if job['provider']=='wcl':
            if job['op'] in ('report','combatants','player-details'):
                allowed=self.db.execute('SELECT active FROM public_report WHERE code=?',(p['code'],)).fetchone()
                if not allowed or not allowed['active']:
                    raise Deferred('report_not_known_public',job['deadline']+.01)
            if job['op']=='guild':
                p.update(name='Liquid',serverSlug='illidan',serverRegion='US')
            query=self.s.get('queries')[job['op']]
            return WCL_URL,dict(query=query,variables=p)
        if job['op']=='roster':
            kwargs=dict(realm='illidan',name='liquid')
        elif job['op'] in ('item','item-set'):
            kwargs=dict(item_id=p['item_id'])
        elif job['op'] in ('specializations','raids'):
            kwargs=p
        else:
            target=self.db.execute('SELECT * FROM target WHERE id=?',(job['target'],)).fetchone()
            if not target or not target['active']:
                raise Deferred(target['deferred'] if target else 'unresolved_target',job['deadline']+.01)
            kwargs=dict(realm=target['realm'],name=target['name'])
        url=blizzard_url(job['op'],**kwargs)
        if job['op'] in ('item','item-set') and p.get('namespace'):
            bits=urlsplit(url)
            url=urlunsplit((bits.scheme,bits.netloc,bits.path,urlencode(dict(namespace=p['namespace'],locale='en_US')),''))
        return url,None

    def step(self):
        now=self.clock()
        with self.db:
            self.db.execute("""UPDATE job SET state='missed',reason=CASE
              WHEN provider='blizzard' AND op IN ('equipment','character','status','specializations','raids')
                THEN 'snapshot_window_expired' ELSE coalesce(reason,'deadline_elapsed') END
              WHERE state='pending' AND deadline<=?""",(now,))
        # Bound selection to the small due set; choosing the expiry index scans every future
        # slot (over 100,000 for the baseline) on every worker iteration.
        job=self.db.execute("SELECT * FROM job INDEXED BY job_due WHERE state='pending' AND ready<=? AND deadline>? ORDER BY priority,planned,id LIMIT 1",(now,now)).fetchone()
        if job is None:
            return False
        with self.db:
            self.db.execute("UPDATE job SET state='running' WHERE id=?",(job['id'],))
        try:
            url,payload=self.request(job)
            self.client(job['provider']).request(url,payload,max_attempts=1,
                before_attempt=lambda aid,descriptor:self.reserve(job,aid,descriptor),
                context=dict(job=job['id'],version=VERSION))
        except Deferred as error:
            self.s.defer(job,error.reason,error.until)
            return True
        except ProbeError:
            # Only safe categorical diagnostics are persisted, never exception/server/token text.
            pass
        intent=self.db.execute('''SELECT i.* FROM intent i LEFT JOIN attempt a ON i.id=a.id
          WHERE i.job=? AND i.applied=0 AND a.id IS NOT NULL ORDER BY i.at DESC LIMIT 1''',(job['id'],)).fetchone()
        if intent:
            if self.after_archive:
                self.after_archive(intent['id'])
            self.apply(intent['id'])
        else:
            with self.db:
                self.s.event('authentication_or_pre_send_failure',dict(job=job['id']))
            self.s.defer(job,'authentication_or_pre_send_failure',now+300)
        return True

    def apply(self, attempt_id):
        row=self.db.execute('''SELECT a.*,b.content,i.at AS sent,i.job AS job_id FROM attempt a
          JOIN intent i ON a.id=i.id LEFT JOIN body b ON a.body_sha256=b.sha256 WHERE a.id=?''',(attempt_id,)).fetchone()
        job=self.db.execute('SELECT * FROM job WHERE id=?',(row['job_id'],)).fetchone()
        try:
            payload=json.loads(row['content']) if row['content'] else None
        except (ValueError,UnicodeError):
            payload=None
        headers=json.loads(row['response_headers'])
        with self.db:
            # Raw storage is already committed. Parse/plan/checkpoint is one separate transaction.
            self.observe_budget(job,row,payload,headers)
            state,reason='ok',None
            if row['status'] is None or row['status'] in (401,429,500,502,503,504):
                failures=job['failures']+1
                wait=max(self.s.get('pause_'+job['provider'],0),self.clock()+min(300,2**failures))
                if failures<4 and wait<job['deadline']:
                    self.db.execute("UPDATE job SET state='pending',failures=?,ready=?,result=?,reason='transient_retry' WHERE id=?",
                                    (failures,wait,attempt_id,job['id']))
                    self.db.execute('UPDATE intent SET applied=1 WHERE id=?',(attempt_id,))
                    return
                state,reason='failed','retry_allowance_or_deadline'
            elif row['status'] not in range(200,300):
                state,reason='failed','http_failure'
            elif not isinstance(payload,dict):
                state,reason='failed','unknown_shape'
            elif job['provider']=='wcl' and (payload.get('errors') or 'data' not in payload):
                state,reason='failed','graphql_partial_or_error'
            else:
                # Savepoint prevents a partially parsed page from advancing any logical state.
                self.db.execute('SAVEPOINT parse_page')
                try:
                    self.process(job,payload,attempt_id)
                except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):
                    self.db.execute('ROLLBACK TO parse_page')
                    state,reason='failed','unknown_shape'
                finally:
                    self.db.execute('RELEASE parse_page')
            if reason:
                self.s.event('response_anomaly',dict(job=job['id'],attempt=attempt_id,reason=reason),key(attempt_id,'anomaly'))
            self.db.execute('UPDATE job SET state=?,result=?,reason=? WHERE id=?',(state,attempt_id,reason,job['id']))
            self.db.execute('UPDATE intent SET applied=1 WHERE id=?',(attempt_id,))
            if job['provider']=='blizzard' and job['op'] in ('equipment','character') and row['status'] in (403,404):
                self.s.job('blizzard','status',job['target'],-2,{},self.clock()+30,min(self.clock()+1800,self.s.get('end',job['deadline'])),20,page=job['id'])

    def observe_budget(self, job, row, payload, headers):
        now=self.clock()
        if row['status'] in (429,503) or 'retry-after' in headers:
            delay=retry_delay(headers.get('retry-after'),0,now=now)
            # Without a provider duration, choose a deliberately conservative pause.
            if row['status']==429 and 'retry-after' not in headers:
                delay=max(delay,60)
            self.s.put('pause_'+job['provider'],max(self.s.get('pause_'+job['provider'],0),now+delay))
        if job['provider']=='blizzard':
            # Honor common explicit exhausted-quota headers when supplied; retain all safe variants.
            for k,v in headers.items():
                if k.startswith('x-ratelimit') and 'remaining' in k:
                    try:
                        if float(v)<=0:
                            self.s.put('pause_blizzard',max(self.s.get('pause_blizzard',0),now+3600))
                    except (TypeError,ValueError):
                        self.s.event('unknown_rate_header',dict(attempt=row['id']),key(row['id'],'header'))
            return
        rate=payload.get('data',{}).get('rateLimitData') if isinstance(payload,dict) and isinstance(payload.get('data'),dict) else None
        if not isinstance(rate,dict):
            self.ensure_rate(now)
            return
        try:
            spent,limit,reset=(float(rate[k]) for k in ('pointsSpentThisHour','limitPerHour','pointsResetIn'))
            if not all(math.isfinite(v) for v in (spent,limit,reset)) or spent<0 or limit<=0 or reset<=0:
                raise ValueError()
        except (ValueError,TypeError,KeyError):
            self.ensure_rate(now)
            return
        previous=self.db.execute('SELECT * FROM rate ORDER BY at DESC,rowid DESC LIMIT 1').fetchone()
        delta=None
        observed=row['sent']
        if previous and abs(previous['reset_at']-(observed+reset))<10 and spent>=previous['spent']:
            delta=round(spent-previous['spent'],6)
        else:
            delta=None
        self.db.execute('INSERT OR IGNORE INTO rate VALUES (?,?,?,?,?,?)',(row['id'],observed,spent,limit,observed+reset,delta))
        self.db.execute('UPDATE intent SET charged=? WHERE id=?',(delta,row['id']))
        if delta is not None:
            reserved=self.db.execute('SELECT reserved FROM intent WHERE id=?',(row['id'],)).fetchone()[0]
            if delta>reserved:
                self.s.event('unexpected_point_cost',dict(attempt=row['id'],observed_account_delta=delta,reserved=reserved),key(row['id'],'cost'))
                if job['op']!='rate-limit':
                    self.ensure_rate(now)

    def identity(self, job, payload, attempt):
        t=self.db.execute('SELECT * FROM target WHERE id=?',(job['target'],)).fetchone()
        if t is None:
            return True
        c=payload if job['op'] in ('character','status') else payload.get('character')
        if not isinstance(c,dict) or type(c.get('id')) is not int:
            raise ValueError('missing identity')
        if c['id']!=t['provider_id'] or (job['op']=='status' and payload.get('is_valid') is False):
            self.db.execute("UPDATE target SET active=0,deferred='identity_conflict' WHERE id=?",(t['id'],))
            self.s.event('identity_discrepancy',dict(target=t['id'],attempt=attempt,expected=t['provider_id'],observed=c['id']),key(attempt,'identity'))
            return False
        return True

    def process(self, job, payload, attempt):
        op=job['op']; p=json.loads(job['params']); now=self.clock()
        if job['provider']=='blizzard':
            if op=='roster':
                received=self.db.execute('SELECT received_at FROM attempt WHERE id=?',(attempt,)).fetchone()[0]
                self.s.apply_roster(payload,attempt,datetime.fromisoformat(received).timestamp())
            elif op in ('equipment','character','status'):
                valid=self.identity(job,payload,attempt)
                if not valid:
                    return
                if op=='equipment':
                    from rwf.pilot_report import equipment
                    equipment(payload)
                    self.metadata(payload,attempt)
                elif op=='status' and type(payload.get('is_valid')) is not bool:
                    raise ValueError('validity shape')
            return
        data=payload['data']
        if op=='rate-limit':
            if not isinstance(data.get('rateLimitData'),dict):
                raise ValueError('rate missing')
            return
        if op=='guild':
            guild=data['guildData']['guild']
            if guild['id']!=488971:
                raise ValueError('wrong WCL guild')
            page=guild['members']
        elif op=='character-reports':
            character=data['characterData']['character']
            if character.get('hidden') is not False:
                self.s.event('panel_unavailable',dict(target=job['target'],attempt=attempt),key(attempt,'panel'))
                return
            page=character['recentReports']
        elif op=='reports':
            page=data['reportData']['reports']
        else:
            report=data['reportData']['report']
            if not isinstance(report,dict):
                raise ValueError('report unavailable')
            if op=='report':
                if report.get('visibility')!='public':
                    self.db.execute('UPDATE public_report SET active=0 WHERE code=?',(p['code'],))
                    self.s.event('report_unavailable',dict(code=p['code'],attempt=attempt),key(attempt,'visibility'))
                    return
                self.select_fights(report,job,attempt)
                return
            if op=='player-details':
                if (not isinstance(report.get('playerDetails'),dict) or 'error' in report['playerDetails']
                        or not isinstance(report['playerDetails'].get('data',{}).get('playerDetails'),dict)):
                    raise ValueError('player details unavailable')
                return
            page=report['events']
            if not isinstance(page,dict) or not isinstance(page.get('data'),list) or 'nextPageTimestamp' not in page:
                raise ValueError('events envelope')
            cursor=page['nextPageTimestamp']
            if cursor is not None:
                if self.db.execute("SELECT count(*) FROM job WHERE op='combatants' AND target=?",(job['target'],)).fetchone()[0]>=20:
                    raise ValueError('event page allowance')
                if isinstance(cursor,bool) or not isinstance(cursor,(float,int)) or not math.isfinite(cursor) or not p['start']<cursor<=p['end']:
                    raise ValueError('event cursor')
                p['start']=cursor
                self.s.job('wcl',op,job['target'],job['round'],p,now,job['deadline'],job['priority'],page=cursor)
            return
        if not isinstance(page,dict) or page.get('current_page')!=p['page'] or type(page.get('has_more_pages')) is not bool or not isinstance(page.get('data'),list):
            raise ValueError('pagination envelope')
        if op in ('reports','character-reports'):
            for report in page['data']:
                if report.get('visibility')=='public':
                    self.discover_report(report['code'],op,attempt)
        if page['has_more_pages']:
            if p['page']>=100:
                raise ValueError('page allowance')
            p['page']+=1
            self.s.job('wcl',op,job['target'],job['round'],p,now,job['deadline'],job['priority'],page=p['page'])

    def metadata(self,payload,attempt):
        def walk(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k in ('item','item_set') and isinstance(v,dict) and isinstance(v.get('id'),int) and v['id']>0:
                        href=v.get('key',{}).get('href','')
                        ns=parse_qs(urlsplit(href).query).get('namespace',['static-us'])[0]
                        import re
                        if not re.fullmatch(r'static(?:-[A-Za-z0-9._]+)?-us',ns):
                            self.s.event('unknown_metadata_namespace',dict(attempt=attempt),key(attempt,'namespace'))
                            continue
                        op='item' if k=='item' else 'item-set'
                        self.s.job('blizzard',op,key(op,v['id'],ns,'en_US'),0,dict(item_id=v['id'],namespace=ns),
                                   self.clock(),self.s.get('end'),60)
                    walk(v)
            elif isinstance(value,list):
                for v in value:
                    walk(v)
        walk(payload)

    def discover_report(self,code,source,attempt):
        if not isinstance(code,str) or not code:
            raise ValueError('report code')
        # Every code passed to a report endpoint must have an explicit public discovery.
        exists=self.db.execute('SELECT code FROM public_report WHERE code=?',(code,)).fetchone()
        selected=self.db.execute('SELECT count(*) FROM public_report WHERE selected=1').fetchone()[0]<3
        if not exists:
            self.db.execute('INSERT INTO public_report(code,evidence,source,selected) VALUES (?,?,?,?)',(code,attempt,source,int(selected)))
            if selected:
                start=self.s.get('start')
                for round_ in range(8):
                    planned=max(self.clock(),start+round_*21600)
                    if start+(round_+1)*21600>self.clock():
                        self.s.job('wcl','report',code,round_,dict(code=code),planned,start+(round_+1)*21600,50)
        self.s.event('public_report_discovery',dict(code=code,source=source,attempt=attempt),key(attempt,code,'discovery'))

    def select_fights(self,report,job,attempt):
        actors=report['masterData']['actors']
        actor_ids={a['id'] for a in actors}
        for a in actors:
            if a.get('type')=='Player' and a.get('server'):
                matches=self.db.execute('SELECT * FROM target WHERE lower(name)=lower(?)',(a['name'],)).fetchall()
                for t in matches:
                    if folded_server(t['realm'])==folded_server(a['server']) and t['provider_id']!=a.get('gameID'):
                        # WCL historical discrepancies quarantine the link, not current Blizzard polling.
                        self.s.event('identity_discrepancy',dict(target=t['id'],attempt=attempt,actor=a['id'],scope='historical_wcl_link'),key(attempt,a['id'],t['id']))
        for f in report['fights']:
            arrays=[f.get(k) for k in ('friendlyPlayers','friendlySpecs','friendlyItemLevels')]
            if not all(isinstance(x,list) for x in arrays) or len({len(x) for x in arrays})!=1 or any(a not in actor_ids for a in arrays[0]):
                self.s.event('fight_shape_anomaly',dict(attempt=attempt,fight=f['id']),key(attempt,f['id'],'alignment'))
                continue
            if not f.get('encounterID') or f.get('inProgress') or not 0<=f['startTime']<=f['endTime']<=report['endTime']-report['startTime']:
                continue
            if self.db.execute('SELECT count(*) FROM selected_fight').fetchone()[0]>=20:
                break
            if self.db.execute('SELECT 1 FROM selected_fight WHERE code=? AND fight=?',(report['code'],f['id'])).fetchone():
                continue
            self.db.execute('INSERT INTO selected_fight VALUES (?,?,?)',(report['code'],f['id'],attempt))
            target=f"{report['code']}:{f['id']}"
            self.s.job('wcl','player-details',target,0,dict(code=report['code'],fightIDs=[f['id']]),self.clock(),self.s.get('end'),55)
            self.s.job('wcl','combatants',target,0,dict(code=report['code'],fightIDs=[f['id']],start=f['startTime'],end=f['endTime'],limit=1000),
                       self.clock(),self.s.get('end'),55,page=f['startTime'])

    def run(self, until=None):
        self.recover()
        while True:
            now=self.clock()
            if (self.s.directory/'STOP').exists() or (until is not None and now>=until):
                with self.db:
                    self.s.event('graceful_stop',dict(at=now))
                    self.s.put('status','paused')
                return
            end=self.s.get('end')
            if end and now>=end and self.s.get('status')!='finalizing':
                with self.db:
                    self.s.put('status','finalizing')
            if end and now>=end+GRACE:
                with self.db:
                    self.db.execute("UPDATE job SET state='missed',reason=coalesce(reason,'finalization_deadline') WHERE state IN ('pending','running')")
                    self.s.put('status','finished')
                    self.s.put('finished',now)
                    self.s.event('finished',dict(at=now))
                return
            if self.step():
                continue
            pending=self.db.execute("SELECT min(ready) FROM job WHERE state='pending'").fetchone()[0]
            if not end and pending is None:
                with self.db:
                    self.s.put('status','baseline_failed')
                return
            if end and now>=end and pending is None:
                with self.db:
                    self.s.put('status','finished'); self.s.put('finished',now)
                    self.s.event('finished',dict(at=now))
                return
            wake=min([x for x in (pending,until,end+GRACE if end else None,now+30) if x is not None])
            self.sleep(max(.01,wake-now))


def folded_server(value):
    # Only a candidate comparison for mismatch warnings, never an identity merge.
    return ''.join(c for c in value.casefold() if c.isalnum())
