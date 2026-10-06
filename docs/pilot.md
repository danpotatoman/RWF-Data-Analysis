# Pilot experiment: 48 hours, one whole guild

**Baseline experiment specification; runner completion audited offline on 2026-09-23.**
At that readiness review, the real experiment had not been started. Scope clarification
added 2026-10-06: [STATUS.md](../STATUS.md) supplies current execution state; this
document defines the protocol and acceptance criteria. Read [operations](pilot-operations.md) for exact launch,
restart, report and backup commands, software validation, and concrete scheduling/budget choices.
The September 17 roster and query-cost evidence justify a
small whole-guild Blizzard experiment. The highest-value question is whether repeated snapshots
of the roughly 1,000 returned characters yield useful gear/identity changes at manageable cost.
This is a coverage/freshness experiment, not an attempt to infer ownership, splits or loot allocation.

## Scope and cadence

Start from a fresh, complete Liquid US–Illidan Blizzard roster (guild ID 52374740), preserving all
returned characters and each member's own realm. Do not restrict by level, name pattern, activity
or progression participation. Keep departures tracked through the 48-hour window. New roster
members enter at discovery; additional resolved public-report players can be queued with a separate
discovery reason. Keep baseline-roster and later-added coverage denominators separate. If the
population grows beyond 1,200, retain every discovery and explicitly defer additional polling
until the budget is reviewed; do not silently remove characters or claim coverage for deferred ones.

| Work | Cadence and limit | Purpose |
|---|---|---|
| Blizzard full guild roster | Every 6 hours, eight rounds | New/absent members and realm distribution |
| Blizzard equipment, all targets | Every 30 minutes, stagger evenly, 96 rounds | Snapshot yield and missed/unchanged-state rates |
| Blizzard summary, all targets | Every 6 hours, eight rounds | IDs, affiliations, average/equipped levels, last-login context |
| Blizzard status, all targets | At start and hour 24; extra on identity/availability anomalies | Validity and ID discrepancy handling |
| Specializations and raids | Three sampled public characters, at start/end only | Small contextual before/after check; not all-member history |
| Item/set metadata | First unseen referenced ID/build/locale, cache; cap 500 calls total | Context for observed copies, never substitute static item level |
| WCL guild roster | Start and end, complete pages | Compare changing source coverage, not ownership |
| WCL guild report discovery | Every 30 minutes, fixed overlapping bounds | Detect public guild activity; archive empty results too |
| WCL character recent reports | Ten preselected public roster characters every 6 hours | Check activity missed by guild-only discovery; fixed panel avoids activity-based selection drift |
| WCL report metadata/actors/fights | Up to three discovered public reports, every 6 hours | Report revisions and actor identity checks |
| WCL player details + CombatantInfo | At most 20 selected fights across the pilot, bounded pagination | Historical equipment context and size/cost checks |
| WCL budget observation | Hourly and after unexpectedly costly batches | Confirm budget, without per-request observers |

If a discovery list needs multiple pages, save each page and checkpoint; stop at budget without
claiming completeness. Use explicit time bounds and preserve filters. Only retrieve discovered,
known public report codes. Do not probe private/unlisted codes. WCL is a small comparison arm;
whole-guild Blizzard repeated observation is the central experiment. A fixed ten-character WCL
panel should span multiple realms and activity levels, selected before seeing pilot outcomes.

Do not continuously poll the race feed in this first pilot. Its availability is already established
for the saved sample. During an actual relevant RWF, separately budget a controlled Heroic/Mythic
composition experiment with contemporaneous public controls to study update lag, selection and
private-source linkage. A quiet 48-hour window cannot answer those questions.

## Budget based on measured shapes

For exactly 1,000 targets and no retries:

- Equipment: `1,000 × 96 = 96,000` requests.
- Summary: `1,000 × 8 = 8,000`; status: `1,000 × 2 = 2,000`.
- Eight rosters plus 12 sample specialization/raid calls: 20.
- At most 500 metadata requests: **106,520 total**, about **2,219/hour** or **0.62/second**.

Use an initial local ceiling of **3,000 Blizzard requests/hour and two/second**, including retries
and additions. Stagger equipment rather than producing 1,000-request bursts. This leaves about
35% above the baseline average without approaching the documented provider ceilings. Actual
throttling headers and 429 responses take precedence; shared-client usage must be included.

Approximate WCL target-point plan, using September 17 shapes:

| Work | Estimated points over 48 hours |
|---|---:|
| Two full WCL rosters | 40.36 |
| 96 guild report pages, 1–1.98 points each | 96–190.08 |
| 80 character report pages at 1.02 | 81.60 |
| 24 report detail calls at 2 | 48 |
| 20 fight details + combatant pairs at 2 + 1 | 60 |
| 48 standalone rate observations | 48 |
| **Estimated total** | **473.96–568.04** |

This is roughly **10–12 points/hour**, not a guarantee: page count, fight size, cache state and
other client activity vary. Set a pilot allowance of **60 points/hour**, stagger initial roster
work and defer optional WCL detail before exhausting it. Reserve at least 20% of the provider's
remaining hourly budget; stop optional work if another application consumes it. Extra pages or
oversized CombatantInfo responses count against the same allowance. Save why work was deferred.
Do not extrapolate one-point small-fight gear cost to whole reports (848 events cost 3.8).

## Minimal state, storage and comparisons

Use a single-process runner and the existing append-only raw archive, plus a small checkpoint file
or sidecar table of target, operation, planned round, attempt ID and completion state. This is a
pilot-specific resumability layer, not a normalized production database or general scheduler.
Place its active SQLite database outside OneDrive synchronization, with consistent exported backups.
Keep existing evidence intact. Complete a restore/replay check before collection begins.

Retain every response and attempt, including unchanged bodies, 404s, errors and partial results.
Deduplicate body storage only; retain observation timestamps, source timestamps, request inputs,
safe headers, cursor/filter state and parse version. No OAuth response, token or credential enters
the archive. Use existing ignored data paths for exports and synthetic fixtures for tests.

Generate temporary, replayable tables/JSON for coverage per target/round, roster addresses and
provider IDs, equipment entries by source ordinal/slot, field presence, and adjacent snapshot
differences. Preserve full raw fields alongside these projections. Report changes in item ID,
observed level, bonus list, crafting fields, set state, enchants, sockets/gems and spec/summary
context separately. Distinguish cosmetic/order/text-only response changes from equipment changes;
do not discard either. Null/missing/empty are distinct. No unique item-instance ID is assumed.

Mark transitions as **detected API-state changes**, not acquisition times. Keep WCL comparisons
labelled with historical fight time and source identity confidence. Quarantine ID mismatches such
as the observed Thdlock example; do not merge on name/realm alone. Report time since last login
as context, not as a proven freshness bound.

## Questions and acceptance criteria

At 48 hours, report per-character and per-realm coverage, request/cost distributions, raw storage
growth, unchanged-response fraction, characters with equipment changes, newly discovered members,
source-only roster changes, and public activity missed by guild-only WCL discovery. Show denominators
for baseline targets, new targets and unavailable targets separately. Extrapolate storage/request
load to 10–20 guilds using measured bytes and populations, not an assumed alts-per-player multiplier.

Success criteria for the real pilot (software tests alone do not establish these):

1. At least **95% of scheduled baseline equipment attempts** completed, with every missed round
   accounted for; at least 95% successful observations among targets that were initially accessible.
   Separately report later provider-unavailable targets; do not silently exclude them to meet a metric.
2. Every attempted API request has a durable outcome/body or explicit transport failure; every
   normalized row/difference resolves to its observation and parser version. No secret material stored.
3. A deliberate restart around hour 24 resumes without losing completed observations, silently
   skipping pages or duplicating a normalized result. A raw replay reproduces summary counts.
4. No intentional quota exhaustion; any 429 honored and separately reported. Stay within local
   allowances, or record deferrals and treat the cadence as infeasible at that allowance.
5. Every sampled array mismatch, unknown scalar shape or identity discrepancy is retained and
   reported, with no fabricated empty snapshot or destructive identity merge.

Zero equipment changes is a valid finding, not software failure; it means yield under that window
was low. A quiet pilot cannot prove the cadence adequate during RWF. Absolute Blizzard publication
lag remains unidentifiable without a consenting character with independently timed changes/logout.
If such a control becomes available, add a small separately consented control experiment; do not
infer lag by treating old WCL gear and current Armory as simultaneous. Long-term retention policy
clarification and CN access remain prerequisites for their respective broader deployment scopes.

## Implemented instrument

`python -m rwf.pilot` provides `run`, `resume`, `stop`, `status`, `report`, `replay`, `backup` and
`dry-run`. One SQLite database combines the existing append-only raw archive with pilot-specific
planned slots, send intents, targets/discoveries, deferrals and checkpoints. No production scheduler,
analytical schema, inference engine or split classifier was added. Code/query signatures and parser
version accompany the run. Raw bodies remain authoritative; generated projections are disposable.

Status sweeps are spread across six hours from start/hour 24. The fixed ten-character WCL panel is
chosen from the fresh public Blizzard roster before looking at activity; WCL-hidden/unavailable
members are reported without substitution. Equipment snapshots expire after 120 seconds of lateness;
summary/status/spec/raid snapshots after 600 seconds, also bounded by their original windows.
Late resume records historical misses rather than backfilling current equipment. End WCL checks
get at most one hour after the 48-hour equipment window; end profile samples retain the 600-second
tolerance. There are 49 scheduled WCL budget observations including that end
boundary, plus observations needed after missing/expensive responses. These concrete choices are
explained in the runbook; actual durations and extra requests remain measurable.
Optional WCL details preserve ten of the local 60 points for core checks. See the
[implementation/offline-readiness audit](pilot-audit.md) for exact planned workload and verified limitations.
