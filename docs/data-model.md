Proposed normalized model
=========================

This is a logical schema, not a deployed migration. Use surrogate UUID primary keys unless a
composite key is specified below. Foreign keys enforce provenance. Timestamps are UTC; retain
original provider numbers and units in raw evidence. Observation time, source publication time,
game event time and inferred validity intervals are separate columns. Unknown is NULL with a
reason, not zero, false, an empty roster, or an assumed acquisition timestamp.

| Relation | Key, references and purpose |
|---|---|
| `collection_run` | ID; code/config hash, start/end, environment, schema snapshot IDs. |
| `job` / `job_attempt` | Job unique on source/operation/target/slot/parameters; leased state and retry due time. Attempts retain request UUID, timestamps, outcome, cost and raw observation FK. Mutable execution state is separate from immutable observations. |
| `raw_body` | SHA-256 PK, byte length, bytes/blob URI, encoding. Deduplicates storage, not observations. |
| `raw_observation` | UUID, source, run/attempt FK, sanitized request method/path/query/variables, namespace/locale, start/receipt time, HTTP status, safe response headers, body FK, source freshness fields, transport error kind. GraphQL error envelope remains in body. |
| `parse_run` | Observation FK, parser version, outcome, diagnostics; unique observation/version. Unknown fields remain recoverable even after parse failures. |
| `race` / `race_region_schedule` | Race UUID, tier/zone provider references; region, release/reset times, evidence and revisions. |
| `cohort_entry` | Race/guild FK, selection version, prior tier/rank, inclusion time, reason, evidence. Captures cohort expansion without rewriting the original sample. |
| `guild` / `guild_identifier_observation` | Internal guild entity; provider, region, game flavor, external ID, name/realm/team relationship, observation FK. WCL teams/custom guilds need not equal Blizzard guilds. |
| `character` | Internal entity, created time. No permanent name or player ownership stored as an identity key. |
| `character_identifier_observation` | Character FK, provider, region, game flavor, realm ID, external character ID, name/slug, WCL canonical ID if present, observation FK. Provider keys scoped conservatively; do not assume Blizzard ID survives transfers. |
| `identity_link_claim` | Two identity records, relation (same-character, rename, transfer), evidence, method/version, status/confidence. Reversible adjudication; preserve conflicting links. |
| `player` / `player_character_claim` | Optional research entity and evidenced character ownership, validity bounds, method/confidence. Never populate by name similarity alone. |
| `discovery` | Candidate character/provider address, originating observation + JSON pointer, source method, discovered time, scope/relevance classification, resolution status. Multiple discoveries can resolve to one character. |
| `tracking_target` | Character or unresolved address, priority/reason, eligibility, next due time, last success/error and retention-review due time; membership is not an eligibility requirement. |
| `roster_snapshot` / `roster_member` | Snapshot FK to raw observation and guild; complete/partial/error status. Member PK `(snapshot, provider member identity)`, rank, level/class and reported realm. No inferred leave event from a failed/partial response. |
| `character_snapshot` | Character FK, observation FK, summary identity/guild/class/spec/level, average/equipped item level and source last-login/publication timestamp if supplied. Unique observation/character/parser. |
| `equipment_snapshot` | Character FK, observation FK, source kind (`blizzard_profile`, `wcl_combatant`, etc.), optional report/fight actor reference, source time/offset, parse completeness. Separate HTTP requests are not presumed synchronized. |
| `equipment_entry` | PK `(snapshot, source_entry_ordinal)`; slot code, item FK, observed item level, quality/context, source JSON pointer. Slot indexed but not unique until validated, preserving anomalies. Item ID is not an item-instance GUID. |
| `equipment_bonus` / `equipment_socket` / `equipment_enchant` / `equipment_stat` | Parent entry FK plus ordinal PK; bonus ID, socket type/gem item/context, enchant ID/type/text, stat ID/value/display respectively. Preserve order, repeated IDs and unknown values. |
| `equipment_effect` / `equipment_set_observation` | Entry FK, reported spell/effect/crafting/upgrade/set fields and raw pointer. Parse stable subfields; leave unsupported structure in raw JSON. Active set bonuses/counts are contextual observations. |
| `item` / `item_metadata_version` | Item identity `(provider, flavor, item_id)`; metadata version keyed by identity, namespace/build, region, locale and content hash, with observation FK. Static item level must not replace observed scaled item level. |
| `item_set` / `item_set_version` / `item_set_member` | Provider set identity; metadata versions and per-version item membership. Distinguish generic set membership from inferred tier classification. |
| `encounter` / `encounter_identifier` / `encounter_loot_candidate` | Internal encounter; provider/ID mapping with evidence; journal item associations with metadata-version FK. Possible source is not observed loot provenance. |
| `report` / `report_observation` | Report key `(provider, site/flavor, code)`; observations with revision, segments, visibility, guild, region, start/end, source observation. Revision alone is insufficient for live uploads, so retain every observation. |
| `report_actor_observation` | PK `(report observation, actor_id)`; actor type, class, name, normalized server, gameID, raw pointer. Character resolution is a separate evidenced link. |
| `fight_observation` | PK `(report observation, fight_id)`; encounter, difficulty, size, relative start/end, kill, completion flag, boss/fight percentage and phases as available. Absolute time derived with explicit units. |
| `fight_participant` | PK `(fight observation, actor_id)`; reported spec/item level and source array ordinal, actor link. Check parallel-array lengths; do not silently misalign them. |
| `event_page` / `event_observation` | Page FK to raw observation, report version/filter hash, requested bounds and next cursor; event PK `(page, ordinal)` with event time/type and raw pointer. Identical event JSON can represent distinct simultaneous events. |
| `race_observation` | Raw observation FK, competition/zone/guild/encounter/difficulty/size parameters, data availability and parse version. JSON has no assumed mandatory composition schema. |
| `derived_claim` / `claim_evidence` | Versioned claim type, subject, value, time bounds, confidence category/optional calibrated probability, assumptions, alternatives, status/supersedes link; evidence edges to observations and JSON pointers. |
| `coverage_interval` | Source/target/window, scheduled vs completed requests, stale/unknown status, known gaps and cause. Helps distinguish absence from lack of observation. |

Do not fabricate relational rows for failed responses. Append observations for unchanged successful
responses even when the blob is shared. Normalized replays are idempotent per parse version.
Corrections create new parse versions/claims; they do not edit the archived response. Subject
indexes must also support retention actions where required, including multi-character roster
and report payloads; deduplicated blobs may need redaction/replacement with an explicit audit
trail rather than silent mutation. A historical deletion rule remains unresolved, not waived.

Example evidence chain:

* `O1`: equipment endpoint returned item 123 in HEAD at receipt time T1; source freshness unknown.
* `O2`: public report R, fight F, lists actor A; resolved-to-character claim links A to that character.
* `O3`: later equipment response includes item 456; both complete slot records remain.
* `C1`: a versioned classifier labels a set of fights a possible Heroic split, citing O2 and
  composition overlaps. A single Heroic clear is not automatically a split.
* `C2`: candidate item-acquisition attribution cites O1/O3/C1 plus possible journal sources, with
  alternatives (other raids, crafting, earlier unequipped item). No drop time is written into O3.

Even `(T1, T3]` describes a **detected API-state transition**, not a defensible game acquisition
interval when either observation is stale. Preserve that distinction in every downstream view.
