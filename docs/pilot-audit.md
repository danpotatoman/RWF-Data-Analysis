# Liquid pilot implementation and offline-readiness audit — 2026-09-23

**Historical software and SYNTHETIC execution audit, not a completed live pilot.**
State-tracking clarification added 2026-10-06; historical results and counts below
are preserved. [STATUS.md](../STATUS.md) supplies current state. Checklist "Complete"
means implementation/offline verification unless otherwise qualified, not measured
live experiment success. See [experiment records](experiments/README.md).

**READY FOR REAL 48-HOUR PILOT** after the offline checks below. This is readiness to run the
experiment, not a claim that real collection met its scientific criteria. No live pilot or new
authenticated API call was made during this audit. All four credential variables were present and
nonempty; validity at launch is checked by OAuth/bootstrap. No credential values were reported.

The prior implementation request and `pilot.md` were compared with the actual runner, probe,
archive, projections and tests. The September 17 feasibility evidence remains unchanged. This
folder had no Git metadata at this September 23 audit; no repository, remote or
commit was created during that audit.

## Requirement checklist

| Requirement | State | Evidence / boundary |
|---|---|---|
| Fresh full Liquid Blizzard roster, member realms, no activity/name/level filtering | Complete | Bootstrap validates guild 52374740, nonempty roster, IDs and duplicates; no baseline from an error |
| Preserve baseline/departures, discover new roster members, separate denominators, 1,200 cap | Complete | Durable targets/discovery evidence; cap deferrals retain targets and planned coverage |
| 96 equipment rounds, eight summaries/rosters, two status sweeps, anomaly status, sample contexts | Complete | Exact 1,000-target schedule and first-window workload tests |
| Stable staggering, equipment priority, no historical backfill | Complete | Equipment slots 1.8 seconds apart for 1,000; 120-second expiry; pre-send guard after pacing |
| Metadata by referenced ID/build/locale, at most 500 attempts | Complete | Cache keys, approved URL reconstruction and cap tests; retries consume cap |
| WCL roster/discovery/panel/report/fight/context limits and pagination | Complete | Fixed windows, public-code registry, transactional next-page/cursor creation; failures retain incomplete chains |
| Blizzard 3,000/hour and maximum two/sec, retry/addition accounting | Complete | Durable send reservations; existing client uses a stricter one-second spacing |
| WCL 60 points/hour, optional work first to defer, monitor costs/shared usage | Complete | Optional detail ceiling 50, core reserve ten; account deltas plus conservative reservations; provider headroom |
| Append-only raw outcomes, identical bodies/distinct observations, provenance | Complete | Actual API responses/errors archived before parse; stable logical IDs and separate attempt UUIDs |
| Secrets/OAuth exclusion | Complete | Environment-only credentials, in-memory OAuth; allowlisted headers; mocked real HTTP path and byte scans |
| Null/missing/empty, shape anomalies, identity quarantine, temporal distinction | Complete | Projection and conflict tests; current Profile and historical WCL evidence remain separate |
| Stop/resume, raw-before-checkpoint recovery, uncertain sends, page recovery | Complete | Four-session accelerated scenario plus explicit indeterminate-send test |
| Safe nonsynced location, exclusive lock, read-only status, consistent backup/restore | Complete | Path/lock/status/restore tests; operator procedures in runbook |
| Final coverage/change/cost/activity/storage/restart report and raw replay | Complete | Raw-derived projections, timing categories, asynchronous start/end roster comparisons and extrapolations |
| Detached Windows lifecycle and reboot workflow | Complete implementation; offline verification | Commands parsed, not launched. Operator must keep machine awake and manually resume after reboot |
| Actual 48-hour coverage, latency, point costs and provider behavior | Not yet measured, intentionally | These are outputs of the real experiment; synthetic results do not establish them |
| Guaranteed ten usable public WCL characters | Intentionally different | Freeze ten realm-diverse public Blizzard roster addresses before activity lookup; hidden/unavailable WCL results remain measured gaps; no substitution |
| Status sweep at a single instant | Intentionally different | Spread start/hour-24 sweeps across six hours to protect equipment coverage |
| End checks / monitoring count | Intentionally different | 49 scheduled WCL rate observations including hour 48; WCL finalization at most one hour, profile samples within ten minutes of their planned times |
| Optional discovery of non-roster report actors | Deferred, not required for this pilot | Raw actors retained; no automatic ownership/link inference or extra Blizzard population expansion from uncertain historical identities |
| Production scheduler/database, split/ownership/loot/DPS modeling | Intentionally absent | Outside authorized scope |

No missing requirement blocks this fixed temporary pilot. Long-term retention, CN access and
active-RWF/private-source composition questions remain outside its verified scope. Arbitrary sync
software cannot be identified reliably by directory name; use an unsynced local `LOCALAPPDATA`
directory and do not synchronize it while collecting. Do not share Blizzard credentials with another
collector: the local budget cannot observe its requests. WCL deltas include other account activity
and cannot prove exact per-query attribution. Unexpected query costs can exceed their reservation;
the runner records them and defers subsequent work rather than promising an absolute cost bound.

## Implemented execution path and mocked/offline verification

The following describes the runner's implemented behavior, not a log of live
collection. The real HTTP wiring was exercised with a mocked opener; the accelerated
scenario used synthetic responses and a virtual clock.

1. `rwf.pilot run --data-dir ...` parses an explicit directory; `run` refuses an existing archive.
2. Resolved live paths reject project/known sync roots and UNC/relative paths.
3. Credentials are checked for presence before opening state; an OS-held lock excludes a second
   writer. (This ordering differs harmlessly from the audit's illustrative lock-before-credentials list.)
4. `State` creates raw and operational tables, captures query text/code signature/version, and
   schedules only the bootstrap initially. `Runner` creates the existing real `Client` lazily.
5. OAuth is obtained/refreshed in memory. The live-wiring test replaces only `build_opener`, exercising
   the actual CLI, client, URL construction, urllib requests, pacing and archive; no external calls.
6. The fresh Blizzard roster response is archived first. Validated guild/member identities establish
   baseline targets and start/end from its receipt time. Failure cannot create a fake empty baseline.
7. Stable target and job keys create all slots; roster rescans preserve departures and add discoveries.
8. Due-job selection prioritizes equipment over summaries/context. The audit fixed a query-plan issue
   that otherwise scanned over 100,000 future slots on each iteration.
9. Immediately before each API send, after OAuth/pacing, the runner rechecks deadline, STOP,
   cooldown and budgets and commits a unique intent. No stale selected snapshot can survive sleep.
10. WCL uses saved queries with embedded rate observations, fixed discovery bounds, known public
    codes, bounded report/fight selection and exact pagination cursors. The pilot's modified guild
    query also validates against the saved real schema.
11. Real API response bytes or categorical transport failure are committed to the raw archive.
    OAuth requests are deliberately excluded; crashes/disk failures before archival leave explicit
    indeterminate intents after recovery, not invented response bodies or exactly-once guarantees.
12. Separate transactional parsing/checkpoint updates create page successors only on accepted pages.
    Unknown shapes and GraphQL errors retain raw evidence. Up to four attempts share one logical job.
13. Retry-After/429 applies across the provider; authentication failures back off. Retries and uncertain
    sends consume local budgets. Optional WCL detail preserves capacity for later core work.
14. STOP finishes the bounded current request, then exits; idle stop checks are at most 30 seconds apart.
    OS process death releases the lock. Resume checks mode/version/signature and retains the clock.
15. Recovery reapplies an archived-but-unapplied response without resending; an intent lacking a
    response is recorded as indeterminate and may be retried if its slot still permits it.
16. Equipment is never newly sent at/after the hour-48 boundary. Profile final samples have a
    ten-minute tolerance; WCL end checks have at most one-hour grace. Late resume can finish later
    in wall-clock time but expires missed slots and records the actual finish time separately.
17. `status`, `report`, `replay` and `backup` create no API clients. Replay uses raw bodies plus
    instrument plans/discoveries/intents, not mutable success flags, rate cache or earlier projections.
    SQLite's backup API produces a consistent restorable copy; copying a live main file alone does not.

## Exact planned workload

For 1,000 baseline targets: **106,020 fixed Blizzard jobs** = 96,000 equipment + 8,000 summary +
2,000 status + eight rosters + six specializations + six raids. Up to 500 metadata **attempts** bring
the nominal no-retry total to **106,520**. The cap includes metadata retries.

WCL creates **227 root jobs** = two rosters + 96 guild report windows + 80 panel checks + 49 hourly
rate observations. Together there are **106,247 initial logical jobs**, including bootstrap.
Pagination, up to 24 selected-report checks, 20 fight-detail/CombatantInfo pairs, extra monitors,
anomaly checks, new targets and retries add work; they remain budgeted and visible.

## Overdue semantics and audit fixes

Equipment expires after 120 seconds; other profile snapshots after 600 seconds, bounded further by
the original round/end deadline. Five seconds defines the report's on-time category. Late snapshots
within tolerance retain their actual receipt time; they are never presented as exact historical
state. Static metadata, historical WCL context and roster discovery can run later within their
documented windows. Sleep, network loss, crash, reboot and hours-late resume use the same rules.
Timing records distinguish expiry, meaningful late execution and deadline violations, with independent
provider-unavailable and budget-deferral flags. A completed attempt may still be an HTTP failure.

Other corrections: idempotent archive replay now works with SQLite Row objects; WCL recent cost
estimates age out rather than allowing an old external-usage spike to block monitoring forever;
optional WCL work preserves ten local points. Status adds UTC times, baseline and equipment-window
flags. State version 2 prevents accidentally resuming the older synthetic semantics. Old raw
archives remain inspectable. Start/end WCL/Blizzard roster comparisons require complete WCL page
chains, preserve separate observation times and compare address strings without merging identities.

## Final verification

Final results: **78 full-suite tests passed in 32.077 seconds; 40 pilot-specific tests passed in
30.173 seconds**. The earlier 65-/70-test results are not used as the final result. Synthetic
artifacts stay under ignored `data/`; no real character payload was copied into fixtures.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pilot.py -v
.\.venv\Scripts\python.exe -m rwf.validation check-schema
.\.venv\Scripts\python.exe -m rwf.pilot dry-run --data-dir data/pilot-audit-final-20260923
.\.venv\Scripts\python.exe -m rwf.pilot status --data-dir data/pilot-audit-final-20260923
.\.venv\Scripts\python.exe -m rwf.pilot replay --data-dir data/pilot-audit-final-20260923 --output data/pilot-audit-final-20260923/replay-cli-a
.\.venv\Scripts\python.exe -m rwf.pilot replay --data-dir data/pilot-audit-final-20260923 --output data/pilot-audit-final-20260923/replay-cli-b
.\.venv\Scripts\python.exe -m rwf.pilot backup --data-dir data/pilot-audit-final-20260923 --output data/pilot-audit-final-20260923/consistent-backup.sqlite
```

The fresh accelerated scenario finished with 12 baseline targets, one addition, one departure,
1,644 archived API attempts, four sessions, one recovery reapplication without another send,
one character with a meaningful equipment change, 130 deferrals, and zero network calls. Read-only
status returned `finished`, baseline established and equipment window complete. The virtual clock
finished 31 seconds after its 48-hour boundary. The injected unavailable/quarantined targets correctly
failed the two 95% scientific coverage criteria; archival accounting and rate assertions passed.

Both CLI replays produced **seven byte-identical files**, checked directly with `Path.read_bytes`.
The synthetic start roster comparison was overlap six / source-only six each; the end comparison
was overlap five / source-only seven each. These are synthetic string comparisons, not new Liquid
measurements. The final backup passed `PRAGMA integrity_check` and had matching attempt counts;
automated tests also restore an unfinished copy and recover an unapplied baseline.

Additional offline checks, run via PowerShell here-strings piped to the existing Python interpreter:

- `build_client_schema(latest('full-schema')['data'])` plus `validate` on all 12 captured pilot
  query documents, including the guild query with embedded rate data: zero errors. This checks the
  saved real schema, not a claim that the provider schema was re-fetched today.
- `equipment(latest(label))` on three saved real equipment samples: 16, 15 and 16 entries parsed.
- Byte scans of 71 source/documentation/final-scenario files for all four current environment values
  and encoded Basic-auth pairs: absent. Synthetic credential/token/error markers were absent from
  scenario files; raw bodies contained no OAuth `access_token`, and archived metadata contained no
  Authorization headers. Only presence/result booleans were printed.
- PowerShell `Parser.ParseInput` on all seven runbook command blocks: zero syntax errors. Detached
  launch commands were not executed. The earlier slow test pass was interrupted after exposing
  the due-query index issue; final results above are from the corrected code.

See [operations](pilot-operations.md) for launch, health checks, hour-24 restart, reboot recovery,
final report/replay, backup and temporary retention review. Keep code/query files fixed during a run.
