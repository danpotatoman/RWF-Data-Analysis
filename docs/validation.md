Validation runbook and results
==============================

Completed live **2026-09-17**, recovered and analyzed offline **2026-09-22**. All four credential
variables were present/nonempty at recovery. Both APIs authenticated in the saved run. Read
[feasibility results](feasibility-results.md) for evidence-labelled findings, roster counts,
field shapes, 42 controlled WCL cost measurements, error cases and unresolved questions.
No live API calls were repeated during recovery. The original documentation-only conclusions
are superseded where the empirical results establish behavior.

The probes retrieve one page per invocation. They archive the full JSON before examining errors,
and save status/error bodies before deciding whether to retry. Token exchange responses are the
intentional exception. The archive is persistent and attempt replay is idempotent, but the CLI
does not implement durable jobs, automatic restart/resume, normalized production equipment parsing,
cross-process rate accounting or retention deletion. The small `rwf.validation` wrapper adds
bounded page traversal, exact-cursor event traversal, a 50%-hourly-point safety stop before target
queries, cost observations and schema validation. Run live probes serially. This is not a scheduler.

Run offline unit tests after following the [fresh setup instructions](../README.md).
The saved-artifact commands below additionally require the private/local research archive:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m rwf.validation check-schema
.\.venv\Scripts\python.exe -m rwf.replay_validation > data/feasibility/replay-2026-09-22.json
```

Tests cover exact-byte retention and unknown fields; repeated observations vs body deduplication;
archive reopening/idempotence/conflicts; HTTP errors; malformed JSON; GraphQL partial data; token
reuse/expiry/one-time refresh; missing credentials; bounded retries; numeric/date Retry-After;
secret-free metadata/diagnostics; redirect protection; Unicode addressing/namespaces; input errors;
and the documentation downloader's success/failure manifest. Added tests cover schema argument/
enum/nullability validation, terminal/non-advancing pagination, oversized pages, roster address
matching, cost reset/observer handling, failed-auth evidence attribution and offline analysis.
Fixtures are synthetic. `check-schema` and `replay_validation` separately use the saved real
artifacts locally, with no network or authentication. The full suite passed **38 tests** after recovery.

Recovery commands and evidence replay
------------------------------------

The environment-only check used (prints booleans, never values):

```powershell
@('BLIZZARD_CLIENT_ID','BLIZZARD_CLIENT_SECRET','WCL_CLIENT_ID','WCL_CLIENT_SECRET') | ForEach-Object {
  $present = -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($_, 'Process'))
  Write-Output ("{0}: {1}" -f $_, $present)
}
git status --short
git diff --stat
```

Git commands reported that this folder is not a repository. No initialization/commit was performed.
README, every `docs/` document, modified probe/query/test files and ignored local artifacts were
inspected before changes. Small inline Python inspections loaded `rwf.validation.latest(label)`
to inspect saved response shapes; the repeatable aggregate computation is now `replay_validation`.
Its output includes roster comparison, 47 fight audits, equipment field counts, gear overlaps,
composition counts and all 42 adjusted costs. It refuses an unexpected WCL region for this US study.

Interrupted-run entry commands (already completed; **do not rerun merely for recovery**):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install graphql-core==3.2.6
python -m rwf.probe --archive data/feasibility.sqlite wcl rate-limit
python -m rwf.probe --archive data/feasibility.sqlite blizzard realms
.\.venv\Scripts\python.exe -m rwf.validation schema
.\.venv\Scripts\python.exe -m rwf.validation identity
.\.venv\Scripts\python.exe -m rwf.validation rosters
```

Other controlled calls were inline Python `Session.named`/`Session.wcl`/`Session.blizzard` batches,
not a persisted shell script. Exact shell text for those batches cannot be reconstructed solely
from artifacts. Exact API request documents and variables **are** persisted. To inspect/reproduce
the actual request shape without another API call, open the SQLite archive read-only and run:

```sql
SELECT a.id, a.started_at, a.received_at, a.source, a.status,
       a.request_json, a.body_sha256
FROM attempt a ORDER BY a.started_at;
```

For a measurement, use the `attempt`, `before_attempt`, `after_attempt` UUIDs in `costs.jsonl`
to retrieve precisely its three archived responses. `query_sha256` identifies the tested query
text. Do not rewrite the original ledger delta: it includes the after-observer cost. The replay
adds `estimated_target = delta - 1` based on the saved calibration; reset/underflow yields unknown.
Budget polling itself costs points. A standalone target with before/after observers costs target + 2.

Recovery integrity checks also recomputed SHA-256 for all 153 main-archive bodies and both initial
archive bodies, checked request metadata for authentication fields, and scanned the source/docs/
test files and saved response artifacts for exact current environment credential values. All
passed; only aggregate pass/fail results were displayed. This checks those known credential
values, not an independent proof that arbitrary unknown sensitive strings cannot occur in provider
payloads. OAuth responses remain excluded by the client and covered by synthetic tests.

Dependencies: core probes remain standard-library only; full schema validation/tests require
`graphql-core` from `requirements-validation.txt`. A clean environment can install that file
with `python -m pip install -r requirements-validation.txt`. Local real artifacts are deliberately
not fixtures and are unnecessary for the synthetic test suite.

Future credential-enabled validation sequence
---------------------------

1. Set process environment credentials securely, then run `wcl rate-limit` and Blizzard `realms`.
   Record successful authentication, provider quota, status/headers and artifact IDs. Never paste
   credentials into variables files. All outputs belong under ignored `data/`.
2. Prefer `python -m rwf.validation schema` for full introspection and all-document validation.
   Targeted inspection can use `wcl schema --variables data/schema.json`, with `{"name":"ReportEventPaginator"}`.
   Repeat for Query, ReportData, Report, ReportFight, ProgressRaceData, Guild, Character,
   RateLimitData, Difficulty and EventDataType. Save snapshots; adjust queries if needed.
   The supplied introspection query returns field/argument types and enum values, not a complete
   schema export; the validation wrapper obtains the complete schema. Validate every selected field
   and argument against it. Saved September 17 introspection already covers the current documents.
3. Run `wcl world`, choose actual zone/encounter/difficulty IDs, and record those decisions.
   Run `guild` using a known guild. Compare paginated member totals with a full Blizzard roster;
   investigate rather than assuming either population is complete.
4. Run Blizzard `character`, `equipment`, `status`, `raids`, `specializations`, then item/set/journal
   probes for returned IDs. Keep each response independently timestamped. Check all candidate
   fields in the inventory and note absent/null/unrecognized shapes. Repeat around a controlled
   equipment swap/logout on a consenting test character if one becomes available; measure publication lag without assuming
   the API updates every poll. Check crafted/enchanted/socketed/upgraded/tier variants.
5. Run WCL report discovery, then a public report, one fight's player-details, and combatant-info
   pages. Compare friendly IDs/spec arrays, report actor realm mappings and gear with the known
   fight. Validate absolute UTC time against a known report: report epoch plus fight offset.
   Do not use an active character's current Armory gear as historical fight ground truth.
6. For list queries increment `page` while `has_more_pages` is true. Save a fixed start/end window.
   For combatant pages use returned `nextPageTimestamp` as the next `start`; keep end/filters fixed.
   Verify terminal null behavior, equal-timestamp boundaries and non-advancing cursors. A single
   probe page never constitutes complete report collection.
7. Measure point cost with rate queries before/after each query shape. Exercise access-denied,
   nonexistent character and unknown report cases using known test inputs; never enumerate private
   codes. Simulate 429/5xx via tests rather than deliberately exhausting quotas.

Variables JSON shapes (replace illustrative IDs/times/codes with actual discovered values):

| Query | Example object |
|---|---|
| `schema` | `{"name":"ReportEventPaginator"}` |
| `guild`, `character-reports` | `{"name":"NAME","serverSlug":"REALM","serverRegion":"EU","page":1}` |
| `reports` | `{"guildID":123,"start":1789603200000,"end":1789689600000,"page":1}` |
| `report` | `{"code":"PUBLIC_CODE"}` |
| `player-details` | `{"code":"PUBLIC_CODE","fightIDs":[1]}` |
| `combatants` | `{"code":"PUBLIC_CODE","fightIDs":[1],"start":0,"end":600000,"limit":100}` |
| `events` | `{"code":"PUBLIC_CODE","fightIDs":[1],"start":0,"end":1000,"dataType":"All","limit":100}` |
| `race` | `{"zoneID":123,"difficulty":4,"guildID":123}` |
| `composition` | `{"guildID":123,"encounterID":123,"difficulty":4}` |

`start/end` in `reports` are epoch milliseconds; those in `combatants` are report-relative
milliseconds. The example difficulty value is illustrative, not a verified upcoming-tier setting.
Set `competitionID` and supported `size` where appropriate; do not assume Heroic is fixed-size.

Active-race experiment
----------------------

Sample multiple guilds/encounters with explicit Heroic and Mythic difficulty values and at least
one contemporaneous public-report positive control. Fetch race summary every 30–60 seconds;
rotate composition requests at 60–120 seconds subject to measured points. Save field presence,
response age, count/identity of returned participants, report links (if any), gear and timestamps,
alongside HTTP/GraphQL failures, nulls and empty JSON. Continue across boss transitions and after
the race ends to characterize availability boundaries.

Compare detailed composition to public fights and independently confirmed sessions. A match shows
usefulness for that sample; no match or an undiscoverable report does not prove private sourcing.
Only a controlled session with corroborated report visibility, or an explicit provider statement,
could substantiate that provenance. Keep the private-derived-data hypothesis unresolved otherwise.
September 17 race pulls explicitly labelled some summaries `reportIsPrivate: true` with null report
codes; this confirms public visibility of provider-labelled private-report summaries. Detailed
composition's precise private provenance remains unverified. Useful Heroic/Mythic composition is
already observed for two encounters; the next experiment concerns timeliness, selection and coverage.
Test helper/alt inclusion, historical-vs-current composition, competition/stealth mode differences,
and whether loot-related fields actually identify events rather than equipped items.

For each experiment record: hypothesis, input/query hash, observation UUIDs, authentication mode,
expected control, measured result, explanation alternatives, and status (`confirmed`, `refuted`,
`inconclusive`, `not tested`). This evidence ledger should drive the next parser/model revision.
