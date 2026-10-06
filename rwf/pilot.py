"""CLI for the fixed Liquid pilot; no live collection begins without the run command."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone

from rwf.probe import ProbeError
from rwf.pilot_state import State, exclusive, safe_directory, read_database
from rwf.pilot_runner import Runner
from rwf.pilot_report import summarize


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','resume','stop','status','report','replay','backup','dry-run'])
    parser.add_argument('--data-dir',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    state=None
    try:
        if args.command=='dry-run':
            from rwf.pilot_synthetic import exercise
            print(json.dumps(exercise(safe_directory(args.data_dir,True)),indent=2))
            return 0
        if args.command in ('status','report','replay','backup'):
            # Read-only operations can inspect exported snapshots in the workspace too.
            if args.command in ('report','replay'):
                report=summarize(args.data_dir,output=args.output)
                if args.output:
                    print(json.dumps(dict(result='written',directory=str(args.output),status=report['status'],criteria=report['criteria'])))
                else:
                    print(json.dumps(report,indent=2))
            else:
                db=read_database(args.data_dir)
                try:
                    if args.command=='backup':
                        if not args.output or args.output.resolve()==(args.data_dir/'pilot.sqlite').resolve() or args.output.exists():
                            raise ProbeError('Backup needs a new --output SQLite file distinct from the active database')
                        args.output.parent.mkdir(parents=True,exist_ok=True)
                        dest=sqlite3.connect(args.output)
                        try:
                            db.backup(dest)
                        finally:
                            dest.close()
                        print('Consistent SQLite backup written')
                    else:
                        db.execute('BEGIN')
                        meta={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM meta')}
                        def utc(value):
                            return datetime.fromtimestamp(value,timezone.utc).isoformat() if value is not None else None
                        print(json.dumps(dict(status=meta['status'],start=meta.get('start'),end=meta.get('end'),finished=meta.get('finished'),
                            start_utc=utc(meta.get('start')),end_utc=utc(meta.get('end')),finished_utc=utc(meta.get('finished')),
                            baseline_established=meta.get('start') is not None,
                            equipment_window_complete=bool(meta.get('end') and meta.get('finished',time.time())>=meta['end']),
                            mode='synthetic' if meta['synthetic'] else 'live',
                            targets=db.execute('SELECT count(*) FROM target').fetchone()[0],
                            baseline_targets=db.execute('SELECT count(*) FROM target WHERE baseline=1').fetchone()[0],
                            added_targets=db.execute('SELECT count(*) FROM target WHERE baseline=0').fetchone()[0],
                            equipment_outcomes={r[0]:r[1] for r in db.execute("SELECT state,count(*) FROM job WHERE op='equipment' GROUP BY state")},
                            deferral_reasons={r[0]:r[1] for r in db.execute('SELECT reason,count(*) FROM deferral GROUP BY reason')},
                            outcomes={r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM job GROUP BY state')},
                            raw_attempts=db.execute('SELECT count(*) FROM attempt').fetchone()[0],
                            last_attempt=db.execute('SELECT max(received_at) FROM attempt').fetchone()[0]),indent=2))
                finally:
                    db.close()
            return 0
        directory=safe_directory(args.data_dir)
        if args.command=='stop':
            if not (directory/'pilot.sqlite').exists():
                raise ProbeError('Pilot database does not exist')
            (directory/'STOP').write_text('Operator requested graceful stop\n',encoding='utf-8')
            print('Stop requested; current bounded request completes before exit')
            return 0
        directory.mkdir(parents=True,exist_ok=True)
        if any(not os.environ.get(k) for k in ('BLIZZARD_CLIENT_ID','BLIZZARD_CLIENT_SECRET','WCL_CLIENT_ID','WCL_CLIENT_SECRET')):
            raise ProbeError('All four credential environment variables must be present and nonempty to run/resume')
        with exclusive(directory):
            exists=(directory/'pilot.sqlite').exists()
            if args.command=='run' and exists:
                raise ProbeError('Existing pilot found; use resume, or a different new directory')
            if args.command=='resume' and not exists:
                raise ProbeError('No pilot exists to resume')
            state=State(directory)
            if state.get('status')=='finished':
                raise ProbeError('This pilot is already finished; generate its report')
            if args.command=='resume':
                (directory/'STOP').unlink(missing_ok=True)
            print(json.dumps(dict(result='runner_started',data_directory=str(directory))),flush=True)
            Runner(state).run()
            print(json.dumps(dict(result='runner_stopped',status=state.get('status'))),flush=True)
        return 2 if state.get('status')=='baseline_failed' else 0
    except KeyboardInterrupt:
        if state:
            with state.db:
                state.put('status','paused')
                state.event('graceful_stop',dict(reason='keyboard_interrupt'))
        print('Interrupted; resume uses persisted attempts and slots')
        return 130
    except ProbeError as error:
        print(str(error))  # ProbeError diagnostics are deliberately secret-free.
        return 2
    except (OSError,ValueError,sqlite3.Error):
        # Never print arbitrary exception text; a provider or local input may contain secrets.
        print('Pilot command failed: check data directory safety, mode, lock, arguments, credentials and disk availability')
        return 2
    finally:
        if state:
            state.close()


if __name__=='__main__':
    raise SystemExit(main())
