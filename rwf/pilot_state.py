"""Durable instrument state for the fixed, single-guild 48-hour experiment."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import unicodedata

from rwf.probe import Archive, ProbeError

VERSION = 2
DURATION = 48 * 3600
GRACE = 3600
CAP = 1200
SAMPLES = [('alexstrasza', 'Imfiredup'), ('illidan', 'Imfiredup'), ('illidan', 'Thdlock')]
SNAPSHOT_LAG = {'equipment':120, 'character':600, 'status':600, 'specializations':600, 'raids':600}
TERMINAL = ('ok', 'failed', 'missed', 'quarantined')


def dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def key(*parts):
    return hashlib.sha256(dumps(parts).encode()).hexdigest()


def folded(value):
    return unicodedata.normalize('NFC', value).casefold()


def code_signature():
    root=Path(__file__).parent
    paths=sorted([root/'probe.py',root/'validation.py',*root.glob('pilot*.py'),*root.joinpath('queries').glob('*.graphql')])
    return key([(str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])


def safe_directory(value, synthetic=False):
    if not value:
        raise ProbeError('An explicit --data-dir is required')
    path = Path(value).expanduser().resolve()
    if not synthetic:
        if not Path(value).expanduser().is_absolute() or str(path).startswith('\\\\'):
            raise ProbeError('Live data directory must be absolute and outside synchronized storage')
        roots = [Path(__file__).resolve().parents[1]]
        roots.extend(Path(v).resolve() for k, v in os.environ.items()
                     if k.casefold().startswith('onedrive') and v)
        if (any(path == r or path.is_relative_to(r) for r in roots)
                or any(any(tag in p.casefold() for tag in ('onedrive', 'dropbox', 'google drive', 'box sync'))
                       for p in path.parts)):
            raise ProbeError('Active live SQLite must be outside project and known sync directories')
    return path


@contextmanager
def exclusive(directory):
    """OS-held lock: process death releases it; never delete another process's lock."""
    path = directory / 'runner.lock'
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ProbeError('Another pilot runner holds this directory lock') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_database(directory):
    path = Path(directory).resolve() / 'pilot.sqlite'
    if not path.is_file():
        raise ProbeError('Pilot database does not exist')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


class State:
    def __init__(self, directory, synthetic=False, clock=time.time):
        self.directory, self.clock = Path(directory), clock
        self.directory.mkdir(parents=True, exist_ok=True)
        self.archive = Archive(self.directory / 'pilot.sqlite')
        self.db = self.archive.db
        self.db.row_factory = sqlite3.Row
        # A single database keeps raw evidence and pilot bookkeeping together for backup.
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS target (
          id TEXT PRIMARY KEY, realm TEXT NOT NULL, name TEXT NOT NULL, provider_id INTEGER NOT NULL,
          baseline INTEGER NOT NULL, discovered REAL NOT NULL, reason TEXT NOT NULL,
          ordinal INTEGER NOT NULL, active INTEGER NOT NULL, deferred TEXT, present INTEGER NOT NULL,
          evidence TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS job (
          id TEXT PRIMARY KEY, provider TEXT NOT NULL, op TEXT NOT NULL, target TEXT NOT NULL,
          round INTEGER NOT NULL, params TEXT NOT NULL, planned REAL NOT NULL, deadline REAL NOT NULL,
          priority INTEGER NOT NULL, ready REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
          result TEXT, failures INTEGER NOT NULL DEFAULT 0, reason TEXT, version INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS job_due ON job(state, ready, priority);
        CREATE INDEX IF NOT EXISTS job_expiry ON job(state, deadline);
        CREATE INDEX IF NOT EXISTS job_target ON job(target,op,round);
        CREATE TABLE IF NOT EXISTS intent (
          id TEXT PRIMARY KEY, job TEXT NOT NULL REFERENCES job(id), provider TEXT NOT NULL,
          at REAL NOT NULL, reserved REAL NOT NULL, charged REAL, applied INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS intent_time ON intent(provider,at);
        CREATE TABLE IF NOT EXISTS event (
          id TEXT PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deferral (
          id INTEGER PRIMARY KEY, job TEXT NOT NULL, at REAL NOT NULL, until REAL NOT NULL, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS public_report (
          code TEXT PRIMARY KEY, evidence TEXT NOT NULL, source TEXT NOT NULL, selected INTEGER NOT NULL,
          active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS selected_fight (
          code TEXT NOT NULL, fight INTEGER NOT NULL, evidence TEXT NOT NULL, PRIMARY KEY(code,fight));
        CREATE TABLE IF NOT EXISTS rate (
          attempt TEXT PRIMARY KEY, at REAL NOT NULL, spent REAL NOT NULL, allowance REAL NOT NULL,
          reset_at REAL NOT NULL, delta REAL);
        ''')
        if self.get('version') is None:
            with self.db:
                self.put('version', VERSION)
                self.put('synthetic', synthetic)
                self.put('created', clock())
                self.put('code_signature',code_signature())
                self.put('status', 'awaiting_baseline')
                self.put('config', dict(duration=DURATION, grace=GRACE, cap=CAP,
                    blizzard_hourly=3000, wcl_hourly=60, locale='en_US', guild=52374740,
                    wcl_guild=488971, region='us', realm='illidan', metadata_calls=500))
                # Capture query text at creation; a restart cannot silently switch query shapes.
                query_dir = Path(__file__).parent / 'queries'
                queries = {p.stem:p.read_text(encoding='utf-8') for p in query_dir.glob('*.graphql')}
                guild = queries['guild'].rstrip()
                queries['guild'] = guild[:-1] + '\nrateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }\n}'
                self.put('queries', queries)
                self.job('blizzard', 'roster', 'liquid', 0, {}, clock(), clock()+3600, 0)
        if self.get('version') != VERSION or self.get('synthetic') != synthetic:
            self.close()
            raise ProbeError('State version or live/synthetic mode mismatch')
        if self.get('code_signature') != code_signature():
            self.close()
            raise ProbeError('Collector code changed since this pilot began; preserve/review this run before resuming')

    def get(self, name, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, name, value):
        self.db.execute('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                        (name, dumps(value)))

    def event(self, kind, detail, identity=None):
        ident = identity or key(kind, self.clock(), self.db.execute('SELECT count(*) FROM event').fetchone()[0])
        self.db.execute('INSERT OR IGNORE INTO event VALUES (?,?,?,?)',
                        (ident, self.clock(), kind, dumps(detail)))

    def job(self, provider, op, target, round_, params, planned, deadline, priority, page=None):
        if provider=='blizzard' and op in SNAPSHOT_LAG:
            deadline=min(deadline,planned+SNAPSHOT_LAG[op])
        ident = key(provider, op, target, round_, page)
        self.db.execute('''INSERT OR IGNORE INTO job
          (id,provider,op,target,round,params,planned,deadline,priority,ready,version)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
          (ident, provider, op, target, round_, dumps(params), planned, deadline, priority, planned, VERSION))
        return ident

    def defer(self, job, reason, until):
        with self.db:
            self.db.execute('INSERT INTO deferral(job,at,until,reason) VALUES (?,?,?,?)',
                            (job['id'], self.clock(), until, reason))
            self.db.execute("UPDATE job SET state='pending',ready=?,reason=? WHERE id=?", (until, reason, job['id']))

    def plan_target(self, target, fraction, start, discovered):
        target_id = target['id']
        for op, period, rounds, priority in [('equipment',1800,96,10), ('character',21600,8,30), ('status',86400,2,20)]:
            # Status spreads across its initial six-hour window, not a 24-hour window.
            window = min(period,21600)
            for round_ in range(rounds):
                planned = start + round_*period + fraction*window
                if planned < discovered:
                    continue
                self.job('blizzard',op,target_id,round_,{},planned,min(start+DURATION, start+round_*period+window),priority)

    def apply_roster(self, payload, attempt, observed_at=None):
        members = payload.get('members')
        if payload.get('guild',{}).get('id') != 52374740 or not isinstance(members, list) or not members:
            raise ValueError('missing/empty roster')
        rows = []
        for member in members:
            c = member['character']
            if type(c['id']) is not int or c['id']<=0 or not isinstance(c['name'],str) or not c['realm']['slug']:
                raise ValueError('roster identity shape')
            rows.append((folded(c['realm']['slug']), c['name'], c['id']))
        if len(set((r,folded(n),i) for r,n,i in rows)) != len(rows):
            raise ValueError('duplicate roster members')
        first = self.get('start') is None
        now = self.clock() if observed_at is None else observed_at
        start = now if first else self.get('start')
        if first:
            self.put('start',start)
            self.put('end',start+DURATION)
            self.put('status','collecting')
            self.put('baseline_evidence',attempt)
        self.db.execute('UPDATE target SET present=0')
        known = self.db.execute('SELECT count(*) FROM target').fetchone()[0]
        for index,(realm,name,pid) in enumerate(sorted(rows, key=lambda r:(r[0],folded(r[1]),r[2]))):
            ident = key('us',realm,folded(name),pid)
            existing = self.db.execute('SELECT * FROM target WHERE id=?',(ident,)).fetchone()
            conflicts = [r for r in self.db.execute('SELECT id,name,provider_id FROM target WHERE realm=? AND provider_id!=?',
                                       (realm,pid)) if folded(r['name']) == folded(name)]
            if not existing:
                ordinal = known
                known += 1
                reason = 'identity_conflict' if conflicts else ('population_cap' if ordinal >= CAP else None)
                self.db.execute('INSERT INTO target VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ident,realm,name,pid,int(first),now,'baseline_roster' if first else 'new_roster_member',
                     ordinal,int(reason is None),reason,1,attempt))
                fraction = index/len(rows) if first else int(ident[:12],16)/16**12
                self.plan_target({'id':ident},fraction,start,start if first else now)
                if not first:
                    # Discovery activates tracking immediately; initial context is staggered too.
                    # The next regular equipment slot is within 30 minutes; avoid a duplicate burst.
                    checks=[('status',20),('character',30)]
                    if not self.db.execute("SELECT 1 FROM job WHERE target=? AND op='equipment'",(ident,)).fetchone():
                        checks.append(('equipment',10))
                    deadline=min(now+1800,start+DURATION)
                    for op,priority in checks:
                        self.job('blizzard',op,ident,-1,{},now+fraction*max(0,deadline-now),deadline,priority)
            self.db.execute('UPDATE target SET present=1 WHERE id=?',(ident,))
            if conflicts:
                for c in conflicts:
                    self.db.execute("UPDATE target SET active=0,deferred='identity_conflict' WHERE id=?",(c['id'],))
                self.event('identity_discrepancy',dict(evidence=attempt,target=ident,other_targets=[c['id'] for c in conflicts]),
                           key(attempt,ident,'identity'))
        if first:
            self.plan_fixed(start)

    def plan_fixed(self, start):
        end = start+DURATION
        for round_ in range(1,8):
            at=start+21600*round_
            self.job('blizzard','roster','liquid',round_,{},at,at+21600,0)
        for round_,at in [(0,start),(1,end)]:
            self.job('wcl','guild','liquid',round_,dict(page=1),at,at+(21600 if round_==0 else GRACE),40,page=1)
            for i,(realm,name) in enumerate(SAMPLES):
                for op in ['specializations','raids']:
                    self.job('blizzard',op,f'{realm}/{name}',round_,dict(realm=realm,name=name),at+i*15,at+GRACE,50)
        for round_ in range(96):
            at=start+round_*1800
            self.job('wcl','reports','liquid',round_,dict(guildID=488971,start=(at-172800)*1000,end=at*1000,page=1),
                     at,at+1800,35,page=1)
        for hour in range(49):
            at=start+hour*3600
            self.job('wcl','rate-limit','account',hour,{},at,min(at+3600,end+GRACE),15)
        # Freeze a deterministic, realm-diverse panel before consulting report activity.
        by_realm={}
        for row in self.db.execute('SELECT * FROM target WHERE baseline=1 ORDER BY realm,name,id'):
            by_realm.setdefault(row['realm'],[]).append(dict(row))
        panel=[]
        while len(panel)<10 and any(by_realm.values()):
            for realm in sorted(by_realm):
                if by_realm[realm] and len(panel)<10:
                    panel.append(by_realm[realm].pop(0))
        self.put('panel',[p['id'] for p in panel])
        for i,p in enumerate(panel):
            for round_ in range(8):
                at=start+round_*21600+i*60
                self.job('wcl','character-reports',p['id'],round_,dict(name=p['name'],serverSlug=p['realm'],serverRegion='US',page=1),
                         at,start+(round_+1)*21600,45,page=1)

    def close(self):
        self.archive.close()
