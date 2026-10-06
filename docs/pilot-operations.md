# Liquid pilot operations

This is a launch-ready, single-process implementation of the [48-hour experiment](pilot.md).
The September 23 readiness review tested the implementation offline; the real
48-hour experiment had not started at that review. Scope clarification added
2026-10-06: this is an operator runbook, not an execution record. Read
[STATUS.md](../STATUS.md) for current state and active runs, and follow the
[experiment-record convention](experiments/README.md) for intentional experiments.
The coding-agent/VS Code session is not the scheduler. A detached Python process does the work.

## Before launch

Create/activate a Python 3.12+ virtual environment as described in [setup](../README.md), then securely populate the four documented
environment variables in the PowerShell process that launches the runner. They are inherited by
the child process. Do not put credentials in arguments, panel files, scripts or logs. The runner
does not load `.env`. Core live execution needs only the standard library; full tests/schema
checks additionally need `requirements-validation.txt`.

Choose a **new absolute nonsynced local directory**. `--data-dir` is mandatory. Live run/resume
reject the project tree, known OneDrive environment roots, common cloud-sync path names, relative
paths and UNC paths. Resolved paths are checked, including existing symlink/junction targets. A
custom syncing tool or mapped network drive cannot be reliably detected from its name: use local
`LOCALAPPDATA` as below, and do not configure synchronization for the active directory. Synthetic
data is explicitly marked and may be written under ignored project `data/`; it cannot become a live run.

Keep the machine awake and online. Closing VS Code/PowerShell does not stop the detached process;
sleep, reboot or lost networking still create real coverage gaps. The runner is not a Windows
service and does not install a boot task. Resume it after a reboot. Freeze the collector's source
and query files during the experiment: a stored code signature rejects changed-code resumes.

## Start the real run

Run these commands yourself in credential-enabled PowerShell. They **have not** been executed
as part of implementation. Run the preflight from the repository; stop if tests or credentials fail.

```powershell
$pilotRepo = (Get-Location).Path  # Start PowerShell in your cloned repository.
$pilotPython = Join-Path $pilotRepo '.venv\Scripts\python.exe'
Set-Location -LiteralPath $pilotRepo
foreach ($pilotKey in @('BLIZZARD_CLIENT_ID','BLIZZARD_CLIENT_SECRET','WCL_CLIENT_ID','WCL_CLIENT_SECRET')) {
  $pilotPresent = -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($pilotKey, 'Process'))
  Write-Output "$pilotKey present=$pilotPresent"
  if (-not $pilotPresent) { throw 'Required credential missing; populate securely before launch.' }
}
& $pilotPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Full test suite failed' }
& $pilotPython -m unittest discover -s tests -p test_pilot.py -v
if ($LASTEXITCODE -ne 0) { throw 'Pilot tests failed' }
$pilotRunName = 'liquid-48h-{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0,8))
$pilotData = Join-Path (Join-Path $env:LOCALAPPDATA 'RwfPilot') $pilotRunName
New-Item -ItemType Directory -Path $pilotData -ErrorAction Stop | Out-Null
$pilotData | Set-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'RwfPilot\last-run-path.txt')
Write-Output $pilotData
$pilotProcess = Start-Process -FilePath $pilotPython `
  -ArgumentList @('-m', 'rwf.pilot', 'run', '--data-dir', ('"{0}"' -f $pilotData)) `
  -WorkingDirectory $pilotRepo -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $pilotData 'runner.stdout.log') `
  -RedirectStandardError (Join-Path $pilotData 'runner.stderr.log')
$pilotProcess.Id | Set-Content -LiteralPath (Join-Path $pilotData 'runner-pid.txt')
```

The phase begins with a fresh Liquid US–Illidan Blizzard roster. A successful, valid, nonempty
returned roster establishes the baseline and the 48-hour observation clock. A wrong guild ID,
malformed/duplicate roster or failed baseline cannot create an empty baseline. Bootstrap retries
are bounded to one hour. `baseline_failed` requires diagnosis and a new run directory; do not
pretend it collected 48 hours. `run` refuses to overwrite an existing pilot.

Immediately check status and logs. The normal initial phase is `awaiting_baseline`, then
`collecting`. The PID file is a convenience, not proof that the process is still alive.

## Read-only status

The following command opens the SQLite database in read-only/query-only mode and does not create
clients, obtain tokens, schedule work or update collection state:

```powershell
& $pilotPython -m rwf.pilot status --data-dir $pilotData
$pilotStatus = (& $pilotPython -m rwf.pilot status --data-dir $pilotData | ConvertFrom-Json)
if (-not $pilotStatus.baseline_established) { Write-Output 'Baseline not established yet; inspect logs and repeat status.' }
$pilotStatus | Select-Object status,baseline_established,baseline_targets,start_utc,end_utc,equipment_window_complete
```

It reports the durable phase, planned times, target/job counts and last raw attempt time. Durable
phase is not process liveness: compare the last attempt time with the clock and inspect the PID/logs
when diagnosing a stalled run. `paused` records a graceful interruption; a crash may leave the
previous phase on disk until resume. `finalizing` means equipment collection has ended but bounded
end checks are outstanding. `finished` records an actual end time.

```powershell
Get-Content -LiteralPath (Join-Path $pilotData 'runner.stdout.log')
Get-Content -LiteralPath (Join-Path $pilotData 'runner.stderr.log')
Get-Process -Id ([int](Get-Content -LiteralPath (Join-Path $pilotData 'runner-pid.txt')))
```

## Deliberate hour-24 restart

Request a graceful stop. The current bounded request finishes; idle polling checks the marker
at most 30 seconds apart. Confirm that the process exited **before** starting the replacement.

```powershell
& $pilotPython -m rwf.pilot stop --data-dir $pilotData
$pilotPreviousPid = [int](Get-Content -LiteralPath (Join-Path $pilotData 'runner-pid.txt'))
Wait-Process -Id $pilotPreviousPid -Timeout 120 -ErrorAction SilentlyContinue
if (Get-Process -Id $pilotPreviousPid -ErrorAction SilentlyContinue) { throw 'Old PID still exists; inspect it before resuming. Do not kill an unrelated process.' }
& $pilotPython -m rwf.pilot status --data-dir $pilotData
$pilotProcess = Start-Process -FilePath $pilotPython `
  -ArgumentList @('-m', 'rwf.pilot', 'resume', '--data-dir', ('"{0}"' -f $pilotData)) `
  -WorkingDirectory $pilotRepo -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $pilotData 'resume.stdout.log') `
  -RedirectStandardError (Join-Path $pilotData 'resume.stderr.log')
$pilotProcess.Id | Set-Content -LiteralPath (Join-Path $pilotData 'runner-pid.txt')
```

`resume` requires an existing compatible live pilot, takes the OS-held exclusive lock, clears the
stop marker and reuses the original clock/slots. A second process cannot collect concurrently in
the same directory. OS process death releases the lock; do not delete the lock file to bypass it.
Do not run another application with the same Blizzard credential pair during the pilot: there is
no provider-wide Blizzard request counter available to this local runner. WCL's observed shared
account counter is incorporated conservatively.

Recovery applies an archived response whose logical checkpoint was not committed before making
another request. A send reservation without a response becomes an explicit `indeterminate_send`;
it counts against budgets, and a replacement request may occur. Exactly-once HTTP is not promised.
Completed logical slots are not sent again. Expired slots become accounted misses rather than a
large catch-up burst. Page/cursor successors are committed with successful page processing;
partial errors never advance a pagination chain.

### Accidental crash/reboot

In a new credential-enabled PowerShell window, restore these variables, inspect the saved PID's
command line, and run the **resume** launch block above (from `$pilotProcess = Start-Process` through
the PID write). Do not run `run` again or choose a new data directory. If the old collector is alive,
use the graceful-stop procedure first. PID reuse after reboot is possible; never kill by saved PID
alone. The OS-held directory lock is the final guard against two collectors.

```powershell
$pilotRepo = (Get-Location).Path  # Start PowerShell in your cloned repository.
$pilotPython = Join-Path $pilotRepo '.venv\Scripts\python.exe'
$pilotData = (Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'RwfPilot\last-run-path.txt') -Raw).Trim()
Set-Location -LiteralPath $pilotRepo
$pilotPreviousPid = [int](Get-Content -LiteralPath (Join-Path $pilotData 'runner-pid.txt'))
Get-CimInstance Win32_Process -Filter "ProcessId = $pilotPreviousPid" | Select-Object ProcessId,ExecutablePath,CommandLine
& $pilotPython -m rwf.pilot status --data-dir $pilotData
```

### Overdue work and early health checks

Equipment slots expire **120 seconds after their planned time**, or at the round/pilot boundary,
whichever comes first. Summary/status/specialization/raid snapshots expire after **600 seconds**
(also bounded by their original window). The guard runs immediately before the HTTP send, after
OAuth and client pacing, so waking from sleep cannot send an already-selected stale snapshot.
Network failures, sleep, crash, reboot and late resume all obey these same deadlines. Misses remain
in the denominator; current state cannot reconstruct missed historical equipment. Requests already
in flight retain their actual response time and any timeout/error outcome.

Roster discovery may run late within its six-hour window and establishes membership at the actual
observation time. Static metadata and historical WCL detail can run late within their bounded
deadlines; they do not claim to be past Armory observations. WCL discovery windows remain fixed.
The report's `timing_by_operation`/`timing.jsonl` distinguish on-time sends (within five seconds),
meaningfully late work, snapshots within the stated tolerance, expired historical slots, and any
send-after-deadline violation. Provider-unavailable and budget-deferred flags are independent:
a delayed slot may ultimately succeed, fail or expire. Timing completion means an archived attempt,
not necessarily a successful provider response; outcome/coverage metrics supply that distinction.

Count elapsed time from `start_utc`, not process launch. With exactly 1,000 targets and fast responses,
expect approximately 167 equipment successes after five minutes, 1,000 after 30 minutes, and 12,000
after six hours. Summaries and the initial status sweep should reach roughly 14, 84 and 1,000 each
at those checkpoints. Counts vary with request latency and boundary timing; these are health guides,
not acceptance thresholds. At six hours, the next roster/summary round starts. Check that the PID is
the expected Python process, last-attempt time advances, stderr is quiet, and misses/deferrals are
explainable. A zero baseline, stagnant last-attempt time or rapidly growing misses needs investigation.
Closing Astra, VS Code or the launching PowerShell window is not required to keep collection running.

## Reports, replay and consistent backup

At/after hour 48, check status. Equipment schedules stop at exactly the planned end. The three
sample characters' final specialization/raid calls and the final WCL roster start at the boundary;
profile samples expire after ten minutes from each planned sample time; WCL end checks get **up to
one additional hour** to finish within budgets. This does not add equipment rounds.
The report records planned end, actual end and actual duration separately. Reports before `finished`
are provisional. Delayed/offline resume can increase wall-clock duration and records missed slots.

```powershell
$pilotStatus = (& $pilotPython -m rwf.pilot status --data-dir $pilotData | ConvertFrom-Json)
$pilotStatus | Select-Object status,equipment_window_complete,end_utc,finished_utc
if ($pilotStatus.status -ne 'finished') { throw 'Still collecting/finalizing; repeat status later before producing a final report.' }
& $pilotPython -m rwf.pilot report --data-dir $pilotData --output (Join-Path $pilotData 'final-report')
& $pilotPython -m rwf.pilot replay --data-dir $pilotData --output (Join-Path $pilotData 'independent-replay')
& $pilotPython -m rwf.pilot backup --data-dir $pilotData --output (Join-Path $pilotData 'review-backup.sqlite')
```

`report` and `replay` use the same deterministic read-only projector. It reads raw provider bodies
plus captured instrument metadata (planned slots, discoveries, send intents and event/deferral
records), not previous generated projections or mutable job success flags. Without `--output`,
it prints the report JSON. Explicit output directories contain real character information and
must remain temporary local data. Reusing an output directory regenerates its disposable files;
it does not change the source archive. A consistent SQLite backup requires a new destination file
and refuses to overwrite the live file or any existing backup. Do not copy a live database file
alone while its WAL is active. After `backup` completes, the exported snapshot can be copied/synced.
To restore, copy that snapshot into a **new nonsynced directory** as `pilot.sqlite`, then use
`resume` with that directory and the same code. Never restore over a running collector.

Outputs:

- `report.json`: coverage by cohort, character, realm and equipment round; initially accessible,
  later-unavailable, identity-quarantined and population-deferred denominators; departures,
  attempts/status/retries, actual account point deltas, pagination completeness, deferrals,
  storage growth, restart events, anomalies and linear 10-/20-comparable-guild extrapolations.
  Complete WCL start/end roster walks are compared with the first/latest Blizzard roster, preserving
  both observation times; overlap/source-only counts are address-string matches, not identity merges.
- `equipment.jsonl`: observation/version/source ordinal/slot/field-presence projections. Current
  Profile observations retain their own receipt times, separate from source last-login timestamps.
- `differences.jsonl`: adjacent valid observations with both evidence pointers; item ID, level,
  bonuses, crafting, sets, enchants, sockets/gems and other-field changes. Cosmetic/text/order-only
  differences and identical observations are distinguished. Array sorting in semantic comparison
  does not discard original ordering from raw data; positional interpretation remains in raw evidence.
- `context.jsonl`: summaries/status/spec/raid context and previous-observation links. Independently
  fetched context is not represented as synchronized with equipment.
- `wcl.jsonl`: raw-referenced WCL activity and historical fight-context projections, separate from
  Profile equipment. No automatic temporal equivalence or loot attribution is made.
- `anomalies.jsonl`: unknown shapes, ID discrepancies and relevant instrument events.
- `timing.jsonl`: every planned slot, actual first archived attempt, lateness classification,
  evidence pointer and independent provider-unavailable/budget-deferred flags.

Zero detected equipment changes is a valid result. A failed response is never fabricated as empty
equipment. Initially accessible means a valid response in that target's first planned equipment
slot, including a successful bounded retry; unknown and initially unavailable cases are separate.
Completion counts scheduled logical slots with at least one archived attempt; success additionally
requires matching identity and a supported equipment shape. All planned misses remain visible.
Unknown in-flight send reservations are explicit and are not falsely counted as completed responses.

## Cadence/budget decisions

The baseline specification is preserved with these concrete choices:

1. Baseline equipment slots are evenly distributed by stable sorted roster position through each
   30-minute window (1.8 seconds apart for 1,000 targets). Summaries are distributed through six
   hours. The start/day-24 status sweeps are also spread over six hours, avoiding an equipment-blocking
   burst. New targets receive stable phases; initial context is staggered, and departures remain tracked.
2. The first ten realm-diverse addresses from the fresh **public Blizzard roster** are frozen before
   examining WCL activity. No name/activity/progression filtering or outcome-driven substitution occurs.
   WCL's `hidden`/unavailable result is recorded if a panel member lacks public WCL data; fewer than
   ten usable WCL responses are a measured coverage limitation, not a reason to query private data.
3. The first three explicitly public discovered report codes are selected; at most 20 valid completed
   fights are selected. This convenience comparison sample is not representative progression analysis.
   Discovery uses fixed 48-hour overlapping lookback windows. Lists have a 100-page safety bound;
   CombatantInfo chains have a 20-page bound. Nonterminal budget/shape failures remain incomplete.
4. The existing client still spaces sends at least one second apart per provider, below the maximum
   local Blizzard two/second. Pilot send reservations enforce 3,000 Blizzard API attempts/rolling hour,
   including retries and uncertain crash sends. Metadata has a hard **500 attempted-call** cap; retry
   attempts consume it. OAuth bodies/tokens are intentionally excluded from raw request accounting.
5. WCL embeds a rate observation in each pilot query (including the guild query) and also polls hourly,
   after a missing rate observation and after unexpectedly high cost. Admission reserves conservatively
   from observed costs plus a margin and measured initial estimates, under a local 60-point rolling
   allowance. Observed account deltas, including possible other-client activity, replace lower estimates.
   The gate preserves at least **20% of the provider's total allowance**, a stronger floor than 20% of
   remaining allowance. Unknown/reset intervals are explicit. Exact future query cost is unknowable:
   a single unexpectedly expensive response can exceed its reservation; record it and defer subsequent
   work. Do not mistake reservations for a fixed tariff or precisely attributable pilot consumption.
   Optional report/player-details/CombatantInfo work can spend at most 50 of the local 60 points,
   preserving ten points for later core discovery/monitoring. Historical cost estimates use the
   last hour; an external-account spike cannot permanently disable future monitoring.
6. The pilot makes one API attempt per worker execution; durable bounded retries replace in-client
   blocking retries for this runner. 429/Retry-After creates a provider-wide cooldown. Ordinary 404,
   GraphQL partial/error and unsupported-shape results remain evidence and do not advance failed pages.
   Authentication/pre-send failures get a categorical diagnostic and backoff, never a stale prior payload.

The actual runner budget includes 49 scheduled hourly WCL observations (the boundary observation
supports end checks), occasional additional checks, discovered targets and retries. The proposal's
106,520 Blizzard / roughly 474–568 WCL estimate is a baseline estimate, not a hard total. Scheduling
and point uncertainty are reported instead of silently redefining the experiment's coverage.
Exactly 1,000 targets create 106,020 fixed Blizzard slots (96,000 equipment, 8,000 summary, 2,000
status, eight rosters and 12 sample calls), plus at most 500 metadata attempts. WCL creates 227 root
slots: two rosters, 96 discovery windows, 80 character checks and 49 rate observations. Thus there
are 106,247 initial logical jobs including bootstrap. Additional pages, up to 24 selected-report
checks, up to 20 fight-detail/CombatantInfo pairs, new targets, anomaly checks and retries are extra.

## Storage and retention

Everything needed to locate/review this run is under the supplied directory: `pilot.sqlite`
(raw archive and minimal durable state), SQLite sidecars while active, a lock/stop marker and any
logs/exports you request. Body deduplication never removes observations. Every send has an intent;
every successful archive commit has an attempt/body pointer. Disk/archive failures stop the runner.
Generated projections can be regenerated. This is not the proposed final normalized database.

No new long-term retention permission is assumed. Review the unresolved provider retention rules
before keeping/redistributing real data beyond the temporary experiment. After stopping the process,
review the directory and any exported backups together when deciding retention/deletion; the runner
does not automatically delete historical evidence. Never put the live directory, payload exports or
credential material into source control.

## Validation commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pilot.py -v
$pilotSynthetic = 'data/pilot-synthetic-' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m rwf.pilot dry-run --data-dir $pilotSynthetic
.\.venv\Scripts\python.exe -m rwf.pilot status --data-dir $pilotSynthetic
.\.venv\Scripts\python.exe -m rwf.pilot replay --data-dir $pilotSynthetic --output (Join-Path $pilotSynthetic 'replay-check')
```

Use a fresh directory for every `dry-run`. The deterministic scenario has 12 baseline targets,
a new member and a departure; unchanged/cosmetic/meaningful gear transitions; 429/503/transport
failures; unavailable/conflicting identities; paginated WCL responses and a partial GraphQL error.
It deliberately crashes after raw storage, restarts between pages, and stops/resumes at hour 24.
It runs entirely offline, compares independent projection outputs byte-for-byte and checks synthetic
credential/token exclusion. The injected unavailable/quarantined targets correctly cause the
95% scientific coverage criteria to fail; the recovery/software assertions still must pass.

Tests additionally cover 1,000-target staggering, the 1,200 population threshold, metadata limits,
rate/point deferral, path/lock safety, immutable evidence attribution, backup/restore, query-only
status and raw replay after removal of the operational rate cache. Saved real equipment samples
and the saved schema can be inspected offline as compatibility checks; no live feasibility repeat
is necessary. No live pilot or 48-hour success is claimed by these synthetic tests.
See the [implementation/offline-readiness audit](pilot-audit.md) for the final checklist,
mocked HTTP-path verification and synthetic results.
State version 2 refuses to resume older version-1 synthetic runs; their raw archives remain readable.
