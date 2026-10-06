RWF collection design — initial proposal, 2026-09-17
===================================================

Preserve what each source returned, when it returned it, and how it was requested.
Build analytical views from that evidence later. Keep equipment observations, report
participation, identity links, and inferred loot history separate. The initial code implements
probes, feasibility validation, a raw archive and the fixed one-guild pilot runner; the production
architecture below remains a proposal. Updated 2026-09-22. See
[empirical findings](feasibility-results.md) and the [48-hour pilot recommendation](pilot.md).

Evidence and limits
-------------------

Blizzard's official portal JSON was downloaded successfully. Its endpoint inventory confirms
equipment, character summaries/status, guild rosters, item/set metadata and encounter resources.
It documents character updates on logout and guild updates at an unspecified regular interval;
an API fetch is therefore **an observation of published state**, not proof of live equipment at
the fetch time. [Namespaces](https://community.developer.battle.net/documentation/world-of-warcraft/guides/namespaces)

WCL's official indexed schema documents fight membership, specs, item levels, combatant-info gear,
and race composition. Full authenticated introspection and gameplay probes subsequently succeeded.
The saved study confirms complete returned Liquid rosters (988 WCL, 1,000 Blizzard), current
equipment context, public historical report gear, schema compatibility and measured query costs.
These dated samples do not establish global completeness. See [API evidence](api-inventory.md).

The public client API does not allow arbitrary private-report access. Race JSON has no frozen
field schema. Documentation describes active-race availability and a 30-second publication cadence;
neither timing claim was measured. Heroic and Mythic compositions worked for two sampled encounters.
Race pull summaries explicitly included `reportIsPrivate: true` with null report codes. This
establishes provider-labelled private-report summaries, not private-report access or the precise
provenance of a detailed composition. Timeliness, selection rules and race coverage remain unknown.
[Authentication](https://www.warcraftlogs.com/api/docs),
[race fields](https://www.warcraftlogs.com/v2-api-docs/warcraft/progressracedata.doc.html),
[cadence](https://www.warcraftlogs.com/v2-api-docs/warcraft/query.doc.html)

There is a concrete retention issue to resolve before long-term collection. Blizzard's
`/status` documentation describes checking character validity after 30 days and removing
information on a status 404, `is_valid=false`, or ID mismatch. This conflicts with unconditional
indefinite retention. Obtain clarification about historical research records; design selective
removal across raw blobs, normalized rows, exports and backups. Do not implement automatic deletion
from a transient equipment 404. No deletion policy is implemented by these probes.
[Official status definition](https://community.developer.battle.net/api/pages/content/documentation/world-of-warcraft/profile-apis.json)

Population and identity
-----------------------

Seed a versioned race cohort with 10–20 prior-tier guilds, recording the prior tier, ranking
source/date, region and selection rationale. Do not freeze today's top guilds as the next race's
cohort. Include documented sister/alt guilds and WCL raid teams as separate affiliations.

Rescan entire Blizzard rosters; do not restrict discovery to max-level mains or progression
participants. Supplement with WCL guild members, character recent reports, all player actors in
relevant public reports, race compositions when readable, and manually supplied public character
references. Each discovery has source, timestamp, raw pointer and reason. All discovered characters
enter the registry immediately; unknown realm/region entries remain unresolved candidates until
an address can be established. Equipment polling does not require current guild membership.

Use internal UUIDs and observed provider identifiers. Never equate a WCL report actor ID,
`gameID`, WCL character ID, and Blizzard character ID. Actor IDs are local to a report.
Preserve name/realm/guild histories and WCL canonical-ID assertions; transfers and renames require
evidence links, not destructive merges. Region plus realm plus name is an address, not a permanent
identity. Reused names with a different Blizzard ID become distinct candidates. No public endpoint
reviewed enumerates all alts of an arbitrary person; player-to-character ownership stays unknown
unless supported by explicit evidence. [WCL character identity](https://tw.warcraftlogs.com/v2-api-docs/warcraft/character.doc.html)

Architecture and data model
---------------------------

```mermaid
flowchart LR
  Seeds[Guild seeds and discoveries] --> Registry[Character registry]
  Registry --> Jobs[Durable scheduler and leased jobs]
  Jobs --> Clients[Provider clients and shared budgets]
  Clients --> Raw[Raw bodies and request attempts]
  Raw --> Parse[Versioned parsers]
  Parse --> Facts[Normalized observations]
  Facts --> Registry
  Facts --> Analysis[Versioned inferences and metrics]
```

Start the pilot with one scheduler/worker and a transactional database. PostgreSQL plus
content-addressed blob storage is a reasonable production candidate, not a committed dependency.
SQLite is sufficient for these probes. Keep storage and transports replaceable.

The implemented pilot uses one process and one SQLite file outside synchronized storage. Raw
attempts and bodies retain the probe schema; small pilot tables record immutable planned slots,
send reservations, target discovery, page successors, budgets and outcomes. No analytical tables
from the proposed normalized model have been deployed. Raw receipt precedes atomic logical
processing/checkpoint updates; restart reapplies any archived-but-uncommitted response. A missing
response for a durable send reservation is explicitly indeterminate, not exactly-once HTTP.
Readonly replay recomputes observations/differences from raw bodies and the instrument's planned
slots/discovery ledger. See [operations](pilot-operations.md) for the tested failure boundaries.
The pilot expires equipment slots after 120 seconds of lateness and other profile snapshots after
600 seconds (or their original window boundary). It rechecks immediately before HTTP sends, so
sleep/restart cannot fabricate historical snapshots. Report timing classifications and independent
provider/budget flags preserve those gaps. The [completion audit](pilot-audit.md) records offline
live-client wiring, workload and recovery checks; no real 48-hour success is claimed.

The [logical model](data-model.md) covers raw requests/bodies; provider identities and aliases;
roster/character/equipment observations; versioned item metadata; report versions, fights,
actors and participation; race payloads; derived claims and evidence edges. Every parsed row
references its source observation and parser version. Unknown JSON fields survive in raw storage.

Durable jobs carry `(source, operation, target, scheduled_slot, parameter_hash)`, a unique key,
attempt count, lease expiry and next eligible time. Each actual HTTP attempt gets a separate UUID.
Persist the raw body and attempt before parsing; acknowledge the job only after durable storage.
Parsing is independently retryable and unique on `(observation, parser_version, logical_row_key)`.
Advance a pagination checkpoint only with the committed page, never on errors or partial results.
Crash after receipt but before persistence may require refetching; exactly-once HTTP observation
cannot be promised. Record the resulting coverage gap.

For report lists, fix an end-time boundary, paginate fully, and repeat an overlapping window.
Keep known live reports scheduled independently of discovery cursors. Rescan 48-hour windows
frequently and the entire race daily/after completion to catch delayed publication of older logs.
Do not filter discovery solely by default report zone: mixed-zone reports could be missed.
Event pages retain their exact filters/cursors. Resume from the returned cursor, and stop with a
diagnostic on non-advancing cursors. Preserve page-boundary duplicates until deduplication is
justified; timestamp alone is not an event identity. Archive report revisions and refetch changed
segments. Duplicate reports from different uploaders remain separate evidence of potentially
the same fight, with later probabilistic links.

Initial polling and budgets
---------------------------

The following intervals are long-term planning candidates, **not the recommended first pilot**
and not API guarantees. The smaller [48-hour recommendation](pilot.md) uses measured query costs
and whole-guild Blizzard coverage. Jitter schedules and reserve capacity for discovery.

| Work | Pre-race | During race |
|---|---|---|
| Complete guild rosters | Every 6 hours | Every 15 minutes |
| Equipment, broad population | Every 6–12 hours | Every 30 minutes |
| Equipment, recently active/promoted characters | Every hour | Every 5 minutes |
| Character summary | At discovery, then daily | Every 30–60 minutes; sooner after equipment change |
| Character status | At identity anomalies; scheduled validity review | Same, with per-record due dates |
| Guild/character report discovery | Every 6 hours | Guilds every 2–5 minutes; selected characters every 15–60 minutes |
| Known growing report metadata/fights | As needed | Every 1–2 minutes |
| Combatant info/player details | Pilot sample | On new or revised fight; budget permitting |
| Race feed | Occasional availability check | 30–60 seconds overall; composition 60–120 seconds per relevant pair |
| Item/set/journal metadata | On first reference | Cache by namespace/build/locale; revalidate after patches |

Illustrative budget: 20 guilds × 30 players × 15 characters = 9,000 characters (planning assumption,
not an observed roster count). With 600 hot characters at 5 minutes and 8,400 at 30 minutes,
equipment alone uses `600×12 + 8,400×2 = 24,000` requests/hour. Hourly summaries add 9,000,
so that configuration already exceeds a proposed 28,800/hour operational budget before retries.
Initially run broad summaries every two hours or slow cold equipment; preserve a coverage floor
and log every scheduling change. Polling everyone every five minutes would require 108,000/hour.

Blizzard documents 36,000 requests/hour and 100/second. Use shared per-client hourly accounting
plus a smooth bucket capped initially at 8/second (28,800/hour), including retries and all regions;
do not assume independent regional quotas. Leave headroom and honor throttling responses.
[Official throttling guide](https://community.developer.battle.net/documentation/guides/getting-started)

WCL uses points, not a fixed request count. Sample `limitPerHour`, `pointsSpentThisHour`,
`pointsResetIn`, measure cost per query shape, and reserve at least 20% headroom. Twenty composition
requests per minute already means 1,200 queries/hour before reports. The sampled composition shape
cost about 2 target points, so this alone would use about 2,400 points/hour of the observed 3,600
budget, before monitoring/report work. A full 988-character WCL roster scan cost 20.18 target points.
Budget all workers together; query aliases do not make expensive fields free. At exhaustion,
defer work until reset; retain the gap. [Rate fields](https://www.warcraftlogs.com/v2-api-docs/warcraft/ratelimitdata.doc.html)

Retry 429/transient 5xx/network failures with bounded exponential backoff and jitter; honor
`Retry-After` seconds or dates. Refresh expired credentials once on 401. Treat 403/404 as access
or availability observations, not empty data. Keep GraphQL `data` and `errors` together; failed
fields cannot establish absence. Isolate schema failures by query/endpoint, alert and quarantine
parsing while raw collection continues where possible. Log response age, latency, job lag,
failure rate, provider cost, parser version and coverage per guild. Stop advancing work if disk
writes fail. Back up consistently and test restore before race week.

Measurement limits
------------------

| Bias/failure | Consequence and mitigation |
|---|---|
| Logout publication, caches, equipment swaps | Fetch time is not acquisition time. Preserve source timestamps separately; compare report gear. Poll intervals bound detection, not necessarily the game-time change. |
| Private, hidden, unlisted or never-uploaded logs | Public pull/split counts are lower bounds. No report is not evidence of no raid. Report coverage alongside every guild comparison. |
| Broad roster still misses unguilded/hidden alts | Discovery counts are minimums, not total prepared characters. Preserve inclusion dates and source mix. |
| Helpers, buyers, guests and sister teams | Co-occurrence is participation, not employment, ownership, or guild-controlled loot. Keep affiliations distinct. |
| Unequipped drops, bank items, trades, crafting, upgrades and catalyst-like conversions | Equipment changes do not identify original looter, raid of origin or loot allocation. Keep competing explanations. |
| Multiple uploads/revisions, incomplete fights | Avoid inflated pull counts; store versions and inferred duplicate links. Exclude incomplete fights from finalized metrics explicitly. |
| Adaptive polling | Active guilds can appear to change gear more often simply because they are observed more. Retain cadence, stale age and missingness; compare matched coverage. |
| Regional release/reset times, hotfixes, fight phases | Compare both wall-clock and region-relative elapsed time. Preserve release/reset calendar and patch context; health percentage alone may misstate progress. |
| Static metadata changes and ID collisions | Version metadata and provider namespaces; do not join solely by a numeric ID or item name. |
| Report archival/deletion | Retrieve useful evidence promptly; later event availability may change. WCL documents archive-access restrictions. |

Unresolved work and next steps
------------------------------

1. The [validation matrix](validation.md) now has authenticated evidence for equipment fields,
   timestamps, pagination, costs and schema types. Run the proposed [48-hour pilot](pilot.md) next
   to measure repeated-snapshot yield and operational gaps before adding normalized production parsers.
   Treat localized crafting/upgrade text and bonus mappings as interpretations requiring validation.
2. Resolve historical Profile retention and CN-region access. The portal definitions mark the
   reviewed character/roster methods `cnRegion: false`; a CN namespace example is not access proof.
3. Keep the first pilot to one guild's roughly 1,000 returned characters, equipment plus sparse
   summaries/status, a handful of public reports, and replayable comparison outputs. The pilot is
   implemented and tested offline; the real experiment has not run. Deliberately restart midway and replay archives, then size
   for the full cohort. Preserve all failed and unchanged observations.
4. During an active RWF, test explicit Heroic/Mythic `detailedComposition` across guilds,
   encounters and times, with positive public-report controls. Keep empty/null/error responses.
   Saved provider flags already label some pull summaries private; detailed-composition provenance
   still needs controlled corroboration or provider confirmation. Missing public reports alone do
   **not** prove that provenance. Document competition-mode effects and
   whether returned characters include helpers/alts and carry gear/timestamps/report references.
5. Only after coverage is characterized, implement split classification, gear transitions and
   progression metrics with versioned evidence, alternatives and confidence. Exact drop/trade
   attribution may remain unidentifiable from these APIs.
