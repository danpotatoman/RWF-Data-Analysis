# Authenticated feasibility findings

Live observations: **2026-09-17**, main archive 21:56:49–22:03:56 UTC. Recovery and offline
analysis: **2026-09-22**. These are dated observations, not a claim about today's roster/schema.
No additional live calls were made during recovery. All four credential variables were present
and nonempty on recovery; both credential pairs authenticated successfully in the saved run.
Values and OAuth responses were not retained. No Git repository exists in this workspace.

Evidence labels below: **E** = persisted authenticated API observation; **D** = official
documentation/schema description; **I** = interpretation; **U** = unresolved. Synthetic tests
are software checks, not provider evidence. Artifact labels resolve through the append-only
local `data/feasibility/index.jsonl`. Full response bytes, request variables, timestamps and
HTTP outcomes are in `data/feasibility/raw.sqlite`. These paths are ignored and contain real data.

## Recovery audit

| Objective | Persisted before recovery | Completed during recovery |
|---|---|---|
| Authentication, schema, identities | Initial two auth probes; full introspection; original 11-query validation; identity responses | Rechecked presence only; validated all current 12 documents offline |
| Rosters | Ten WCL pages, full Blizzard response, comparison | Recomputed totals, realms and string matches |
| Blizzard sample | 15 character endpoint responses, three items, two sets | Missing-field counts and metadata interpretation |
| Public reports | Three reports, discovery, two-page bounded list, details, combatants, three general-event pages | All-fight alignment/time checks; two historical gear comparisons |
| Race surface | Heroic/Mythic race summaries, four successful compositions, two domain errors | Distinguished available summaries from uncertain provenance/coverage |
| Costs/errors | Calibration, 42 controlled query measurements, representative error bodies | Subtracted observer cost; documented error implications |
| Code/docs | Pagination/schema utilities and synthetic tests; obsolete initial docs | Offline replay, failure-path fix, tests and updated design/runbook/pilot recommendation |

The main archive contains 153 attempts: 130 WCL HTTP 200, 22 Blizzard HTTP 200 and one Blizzard
404. HTTP 200 includes GraphQL errors. The initial `data/feasibility.sqlite` holds two additional
successful auth-validation API responses. The cost ledger ends at **157.27 / 3,600 points/hour**;
no deliberate throttling, private-report access, or quota exhaustion was attempted.

## Schema

**E:** `full-schema` plus `schema-validation`: all original 11 query documents passed GraphQL
validation against the retrieved schema. All current 12 pass offline replay, including the new
general-events query and parameterized CombatantInfo limit. No original selected field required
a schema correction. Validation checks arguments, variable compatibility/nullability, enum
values and selections, not merely HTTP status. JSON scalar contents require separate inspection.

Key observed types (absence of `!` means nullable):

| Surface | Observed signature/shape |
|---|---|
| `Report.events` | Returns `ReportEventPaginator`; `dataType: EventDataType`, `fightIDs: [Int]`, `startTime/endTime: Float`, `limit: Int` |
| Event paginator | `data: JSON`, `nextPageTimestamp: Float` |
| Report paginator | `data: [Report]`, `current_page/total/last_page/per_page: Int!`, `has_more_pages: Boolean!`, `from/to: Int` |
| Character paginator | `data: [Character]`, `current_page: Int!`, `has_more_pages: Boolean!` |
| Player details | `JSON`; `fightIDs: [Int]`, `includeCombatantInfo: Boolean` |
| Race/composition | `JSON`; nullable `Int` IDs/difficulty/size and `String` region/name inputs; composition has **no `zoneID`** |

**E:** `EventDataType` values were `All, Buffs, Casts, CombatantInfo, DamageDone, DamageTaken,
Deaths, Debuffs, Dispels, Healing, Interrupts, Resources, Summons, Threat`. There is no `Loot`
enum value. This does not prove every JSON surface lacks loot-related information.

## Liquid identity and population

**E:** `liquid-identity`, `liquid-blizzard-guild`, roster pages and sampled summaries:

| Source | Observed identity |
|---|---|
| WCL guild | ID **488971**, Liquid, `type: 0`, `competitionMode: true`, `stealthMode: true` |
| WCL server | ID **123**, slug `illidan`, `blizzardID: 57`, region ID 1 / United States |
| Blizzard guild | ID **52374740**, Liquid, US–Illidan / realm **57**, Horde, `member_count: 1000` |
| Relationships | WCL `parentGuild: null`, `teams: []`; **Farm, Splits, Progression are tags**, not discovered child teams |

The corresponding Blizzard identity is supported by returned name/realm ID/region and the sampled
characters' guild references. WCL IDs are separate from Blizzard IDs. No sister guild was identified;
an empty teams field cannot establish that no sister/alt guild exists outside this container.

**E:** WCL returned nine pages of 100 and one of 88; page 10 had `has_more_pages: false`.
Blizzard returned one roster with 1,000 members, matching its summary count. Matching uses
Unicode-normalized, case-insensitive **region + realm slug + name**, not human identity.

| Measure | Count |
|---|---:|
| WCL rows / unique addresses | 988 / 988 |
| Blizzard rows / unique addresses | 1,000 / 1,000 |
| Overlap | **988** |
| WCL only | **0** |
| Blizzard only | **12** |
| WCL / Blizzard realms | 29 / 30 |
| Regions | US only in both |

These are complete **returned accessible** rosters at observation time, not a census of all
prepared characters or guild-controlled accounts. The reason for the 12-source discrepancy is unknown.

Realms and counts (WCL / Blizzard):

| Realm | Counts | Realm | Counts | Realm | Counts |
|---|---:|---|---:|---|---:|
| illidan | 842 / 852 | malganis | 51 / 51 | zuljin | 18 / 18 |
| sentinels | 16 / 16 | haomarush | 9 / 9 | alexstrasza | 7 / 7 |
| area-52 | 6 / 6 | misha | 4 / 4 | thrall | 4 / 4 |
| coilfang | 2 / 3 | tichondrius | 3 / 3 | thunderlord | 3 / 3 |
| the-scryers | 3 / 3 | scarlet-crusade | 2 / 2 | darkspear | 2 / 2 |
| lethon | 2 / 2 | arygos | 2 / 2 | garrosh | 0 / 1 |
| feathermoon | 1 / 1 | dragonblight | 1 / 1 | sargeras | 1 / 1 |
| dethecus | 1 / 1 | demon-soul | 1 / 1 | steamwheedle-cartel | 1 / 1 |
| stormreaver | 1 / 1 | llane | 1 / 1 | stormrage | 1 / 1 |
| duskwood | 1 / 1 | blood-furnace | 1 / 1 | azshara | 1 / 1 |

**E, string matches only:** case-insensitive substring `imfiredup` matches **two characters in
each source**, with one distinct name string: **Imfiredup–Alexstrasza (US)** and
**Imfiredup–Illidan (US)**. Union-of-addresses prefix counts are `thd: 24`, `trill: 29`,
`yipz: 10`, `scott: 13`, `sang: 8`, `jpc: 1`, `imfiredup: 2`.
These do not identify common human ownership. **I:** broad preseason roster tracking is worthwhile
for discovering a large candidate alt pool; neither the 1,000 members nor these families establish
the number of prepared alts per RWF player. Guests, inactive characters and non-racers remain possible.

## Blizzard observations

**E:** `sample-selection` and `sample-{0,1,2}-{character,status,equipment,specializations,raids}`:
all five endpoints succeeded for Imfiredup–Alexstrasza, Imfiredup–Illidan and Thdlock–Illidan.
All statuses were valid. Samples are convenience selections, not a representative guild sample.
Summary average/equipped item levels were **301/301, 300/299, 333/333**. Equipment contained
**16, 15, 16 entries**; do not require a fixed count or insert fabricated missing slots.

Across 47 entries:

| Field | Present | Explicit null | Implication |
|---|---:|---:|---|
| `item`, `slot`, `level` | 47 each | 0 | Use `item.id`, `slot.type`, `level.value` for observed copies |
| `bonus_list`, `context` | 45 each | 0 | Two omissions; preserve bonus IDs without speculative decoding |
| `modified_crafting_stat` | 6 | 0 | Contextual crafting/stat information |
| `set` | 12 | 0 | Keep contextual set membership and effects |
| `sockets` | 16 | 0 | Socket type, gem item and display information when supplied |
| `enchantments` | 25 | 0 | Multiple enchantment kinds/optional spell or source-item references |
| `spells` | 21 | 0 | Preserve effects; do not classify all effects as embellishments |
| `name_description` | 37 | 0 | Localized description, not a stable upgrade enum |

Remaining entries omit these optional fields; absence is distinct from null or an empty list.
Both per-entry `set` and root `equipped_item_sets` occur. Nested `is_equipped`/`is_active` can be
omitted for inactive members/effects rather than explicitly false. Observed crafted candidates
have context 13, crafting stats and localized `Unique-Equipped: Embellished (2)` text; some have
`Tidal Crafted` descriptions. No dedicated upgrade-track or embellishment boolean was found.
Descriptions such as `Mythic Sporefused: Myth` are preserved evidence; decoding their semantics
and bonus IDs remains a versioned interpretation, not a validated item-copy history.

**E:** `item-250060`, `item-239656`, `item-268205`, `item-set-1983`, `item-set-2066` succeeded.
Sets contain item lists/effects (five items each). Hrefs expose build namespace
`static-12.1.0_68914-us`. Generic item levels / preview levels / observed equipped levels differ:

| Item | Generic `level` | Preview `level.value` | Sample equipped level |
|---|---:|---:|---:|
| 250060 | 197 | 44 | 289 |
| 239656 | 197 | 246 | 331 |
| 268205 | 219 | 219 | 334 |

Static metadata must not overwrite observed item level. Specializations include
`specializations`, `active_specialization`, `active_hero_talent_tree`; raid responses contain
`expansions[].instances[].modes` completion context, not a pull or loot-event history. Summary
last-login times differ from fetch times. Publication lag was **not** measured by a controlled swap.

## Public WCL reports and historical equipment

**E:** `reports-30days` returned no guild reports, while `character-reports` returned **55** reports
on a terminal page. `reports-all-history` returned **100**, with more pages; this was a discovery
sample, not full historical enumeration. A separate fixed March 1–September 1 UTC window with
`limit: 1` returned two pages, one row each, second terminal (`report-pagination-result`).
Guild-only discovery demonstrably misses accessible character-associated reports in this sample.

Three discovered public reports were inspected:

| Report | Fights | Actors / Player actors |
|---|---:|---:|
| `AjJV74zaLcTkYNvK` | 8 | 147 / 39 |
| `PXm9nVyY6c2MHQCq` | 29 | 674 / 118 |
| `DZzR9jwYmQA6tbV7` | 10 | 258 / 59 |

All **47** fight rows had equal-length `friendlyPlayers`, `friendlySpecs`, `friendlyItemLevels`;
all player IDs resolved in that report's master actors. This validates structural alignment, not
independent correctness of every reported spec/item level. All offsets lie within report duration.
Report timestamps are epoch milliseconds; fight timestamps are relative milliseconds. Example:
`1787254470329 + 2847821 = 1787257318150`, **2026-08-20 20:21:58.150 UTC**; fight 2 ends at
20:28:52.619 UTC (414.469 seconds). No independent video/game-clock synchronization was performed.

The Illidan Imfiredup actor has report-local IDs **77** and **541** in two reports, with
`gameID: 236155535`, matching the sampled Blizzard ID. WCL character ID **106323331** is different.
Actor `server` is a display string; resolve it using provider server/realm data and report region,
not the guild's realm. A historical Thdlock–Illidan actor has `gameID: 224758017`, whereas sampled
Blizzard Thdlock has ID **237902701**. The cause is unresolved; name/realm agreement alone must not
merge these records. No common-human claim or cross-ID gear comparison was made.

**E:** `details-one-fight` returns 30 players grouped by role under
`playerDetails.data.playerDetails`; `combatants-one-fight` returns 30 combatant events. Gear in
details has explicit numeric `slot`; CombatantInfo gear arrays retain order but lack explicit slot
in the sampled event entries. Both include IDs, item levels, bonus IDs, gems, enchants and set IDs
where present. Gear arrays include zero-ID/zero-level placeholders; preserve them in raw data.
The sampled Imfiredup details/event gear agree on the multiset of nonzero `(item ID, item level)`.

Two **historical** Imfiredup contexts compared to September 17 Blizzard equipment (15 entries):

| WCL context | Nonzero gear entries | Shared item IDs | Shared item ID + level |
|---|---:|---:|---:|
| `AjJV…`, fight 2, August 20 | 15 | 13 | 13 |
| `PXm9…`, fight 20, August 19 | 16 | 12 | 11 |

Counts are multiset overlaps, not slot matching or acquisition evidence. Differences could reflect
time, equipment swaps, copy variants or source publication. Current Armory data is **not** historical
ground truth. The comparison is limited to one identity-supported character at two historical contexts.

## Event limits and cursors

**D:** the retrieved schema describes `limit` as how many events to retrieve, range 100–10,000,
default 300. **E:** the saved full-report CombatantInfo request (`combatants-page-0`) explicitly used
`start: 0, end: 46168706, limit: 100`, no fight filter, and returned **848 events** with a null cursor.
Timestamps span 8,985–45,811,553 across fights. This is not explained solely by preserving one
equal-timestamp boundary. It refutes treating `limit` as a hard event-count ceiling for this shape;
whether CombatantInfo bypasses ordinary pagination or uses another batching rule remains unknown.
Do not truncate to `limit`, and do not synthesize a cursor after a terminal response.

General `All` events were separately paginated for fight 2 of `AjJV…`, fixed relative range
2,847,821–2,848,821, `limit: 100`:

| Requested start | Rows | Min/max event timestamp | Next cursor |
|---:|---:|---|---:|
| 2847821 | 107 | 2847821–2848016 | 2848017 |
| 2848017 | 105 | 2848017–2848632 | 2848633 |
| 2848633 | 41 | 2848633–2848812 | null |

All 253 events were retained. These non-overlapping timestamp boundaries are consistent with
whole timestamp groups, but do not prove the provider's general batching algorithm. Use the exact
returned cursor, require progress, preserve duplicates, and stop on null. Timestamp alone is not
an event identity. Maximum-volume, live-upload and revision behavior remain untested.

## Race surface: useful evidence with limited provenance

**E:** `world` identified zone **53**, The Venomous Abyss, with difficulty IDs 4 Heroic / 5 Mythic
(also 3 Normal / 1 LFR). `race-confirm-4/5` returned Liquid summaries (9/8 killed encounters).
`composition-{3470,3492}-{4,5}` succeeded for both encounters: **30 Heroic and 20 Mythic players**
per response. The JSON includes role groups, name/server/guid/type/item level, talents and gear
subsets. `supportsCombatantInfo: true`; `gearItems` contains two trinket slots 12/13 per player,
with separate `setGearItems`/`effectGearItems`. This is not a full equipment snapshot.

Race pull summaries explicitly contain **`reportIsPrivate: true` and `reportCode: null`** along
with pull times/fight IDs. Thus the public race endpoint exposes summaries the provider labels as
associated with private reports. This is stronger evidence than merely failing to find public logs.
It does **not** grant access to underlying private reports or independently establish which private
report produced a particular detailed composition. No private/unlisted report was accessed.

Encounter 3379 returned `{"error":"No data found for the encounter with id of 3379."}` **inside
the JSON scalar**, with HTTP 200 and no top-level GraphQL errors. The same guild/difficulty can have
useful and unavailable encounters. Availability is confirmed on September 17, but race-active status,
freshness, historical selection rule, full split participation and cross-guild coverage were not
established. These require observation during the relevant preseason/RWF window and controls.

## Measured WCL point costs

**E:** four serial `rate-calibration` observations rose **48.18 → 49.18 → 50.18 → 51.18**.
The standalone rate query cost one point. For each controlled call, the ledger's `delta` is
`after - before` and includes the **after observer**. Estimated target cost is **delta − 1**;
the full before/target/after experiment costs target + 2. Embedded rate fields are part of the
tested query shapes; do not subtract another point speculatively. No reset was detected.
Concurrent activity on the same client, caching, report size and future schema changes can change
attribution/cost. These are observed estimates, not a tariff or guaranteed ceiling.

| Tested shape (ledger labels) | Delta | Estimated target points |
|---|---:|---:|
| Full introspection; type `schema`; identity | 2 each | 1 each |
| Standalone rate control | 2 | 1 |
| Guild roster page of 100 (nine pages) | 3.03 each | 2.03 each |
| Guild roster final 88 | 2.91 | 1.91 |
| World zones/encounters/difficulties | 3.21 | 2.21 |
| Empty 30-day guild report list | 2 | 1 |
| Character recent reports (55) | 2.02 | 1.02 |
| Guild history first page (100) | 2.98 | 1.98 |
| Bounded report pagination, one row/page | 2 each | 1 each |
| Full report metadata/actors/fights (three reports) | 3 each | 2 each |
| One-fight player details with combatant info | 3 | 2 |
| One-fight CombatantInfo (30) | 2 | 1 |
| Whole-report CombatantInfo (848) | 4.8 | 3.8 |
| General events first / next / terminal page | 3.08 / 2 / 2 | 2.08 / 1 / 1 |
| Race summaries, Heroic/Mythic | 2 each | 1 each |
| Detailed composition, successful and unavailable | 3 each | 2 each |
| Unknown report / partial error / invalid variable / unknown type | 2 each | 1 each |

A complete observed WCL roster traversal costs **20.18 target points**, or **40.18** with
before/after observers on every page. Future collectors should sample budget sparingly rather
than double small-query costs. Exact query hashes, variables and attempt links are retained in
`costs.jsonl` plus `attempt.request_json`; offline replay emits adjusted costs without rewriting
the original measurements.

## Ordinary failures and remaining limits

| Artifact | Observed behavior | Collector implication |
|---|---|---|
| `nonexistent-character` | Blizzard HTTP 404, saved error body | Availability observation; not an empty equipment snapshot |
| `unknown-report` | HTTP 200; GraphQL error, report null | Do not treat HTTP success as report success |
| `partial-error` | HTTP 200; valid report alias retained, failing alias null, errors path retained | Preserve partial data/errors; do not advance failed work |
| `invalid-variable` | HTTP 200; GraphQL type error for non-integer fight ID | Fix input; no ordinary retry |
| `unavailable-schema-type` | HTTP 200; internal GraphQL error with `__type: null` | Do not assume unknown type returns clean null |
| `composition-heroic/mythic` for 3379 | HTTP 200; JSON scalar domain error | Validate scalar shape/content, not only GraphQL envelope |

The original unknown-report control used one fixed nonexistent sentinel. It was not a private-code
search and was not repeated during recovery. HTTP 429/5xx, expired-token refresh and network
failures are covered synthetically; they were not provoked live. No real forbidden-report control
was attempted. Ordinary missing data is not proof of inactivity.

**Confirmed:** useful public equipment/context, full accessible roster traversal, schema-compatible
queries, public report gear, ordinary cursor termination, useful Heroic composition and
provider-labelled private-report race summaries.

**Refuted:** fixed gear-entry count; generic item level as equipped level; guild reports as complete
public activity discovery; event `limit` as a hard ceiling; HTTP 200/no GraphQL errors as sufficient
JSON-scalar success; all same-name/realm provider IDs being safely mergeable.

**Documented, not empirically measured:** Blizzard update/retention rules and request ceilings;
quota behavior under load; WCL archive restrictions; intended race feed cadence. Consult the linked
official sources in [inventory](api-inventory.md) and [design](design.md).

**Unresolved:** publication lag, coverage for the next race/top 10–20 guilds, sister/unguilded alts,
character transfers/renames/ID discrepancies, exact bonus/upgrade/embellishment interpretation,
full loot/trade provenance, completeness of CombatantInfo for very large/revised reports,
composition timing/private-source linkage, status-driven historical retention and CN access.
No credential blocker affected the saved study. There is no September 22 live-auth/schema refresh,
by design. See the proposed [48-hour pilot](pilot.md); it is **not implemented**.
