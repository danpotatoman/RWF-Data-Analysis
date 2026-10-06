API inventory and evidence — checked 2026-09-17
==============================================

Evidence labels: **D** = official documentation; **L** = authenticated live observation;
**P** = proposal/candidate requiring validation. Live evidence dates to **2026-09-17** and was
recovered/analyzed offline on **2026-09-22**. See [empirical results](feasibility-results.md) for
artifact labels, confirmed/refuted assumptions and limits. Blizzard documentation hashes are in
[the manifest](blizzard-source-manifest.json). WCL HTML initially returned challenges, but full
authenticated introspection subsequently succeeded. All current 12 query documents validate
against that saved schema. This does not establish no schema change since September 17.

Blizzard
--------

Base `https://{region}.api.blizzard.com`, with `region` = `us`, `eu`, `kr`, `tw` in the probes.
Use Bearer authentication and explicit `namespace`/`locale`. OAuth client credentials:
`POST https://oauth.battle.net/token`, Basic client ID/secret, form
`grant_type=client_credentials`; cache token until `expires_in` minus a margin.
This covers public character/guild resources. Account/protected profile endpoints require user
authorization and `wow.profile`; they cannot discover arbitrary players' account-wide alts.
[OAuth](https://community.developer.battle.net/documentation/guides/using-oauth/client-credentials-flow),
[Profile definitions](https://community.developer.battle.net/api/pages/content/documentation/world-of-warcraft/profile-apis.json)

All paths below are **D**, HTTP GET. **L** covers equipment, summary, status, specializations,
raids, guild, roster, realm index, selected item and item-set detail calls. Other listed paths
remain documented but untested. `{characterName}` is lowercase and URL-encoded;
guild/realm slugs should be resolved from source data, not guessed by removing punctuation.
For cross-realm rosters, use each member's realm rather than the guild's realm.

| Purpose | Exact path | Namespace |
|---|---|---|
| Equipment | `/profile/wow/character/{realmSlug}/{characterName}/equipment` | `profile-{region}` |
| Summary | `/profile/wow/character/{realmSlug}/{characterName}` | profile |
| Validity/identity check | `/profile/wow/character/{realmSlug}/{characterName}/status` | profile |
| Spec/talent context | `/profile/wow/character/{realmSlug}/{characterName}/specializations` | profile |
| Raid completion context | `/profile/wow/character/{realmSlug}/{characterName}/encounters/raids` | profile |
| Achievement context | `/profile/wow/character/{realmSlug}/{characterName}/achievements` | profile |
| Guild identity | `/data/wow/guild/{realmSlug}/{nameSlug}` | **profile** |
| Guild population | `/data/wow/guild/{realmSlug}/{nameSlug}/roster` | **profile** |
| Activity / achievements | `/data/wow/guild/{realmSlug}/{nameSlug}/activity`, `/achievements` appended to guild base | profile |
| Realm index / identity | `/data/wow/realm/index`, `/data/wow/realm/{realmSlug}` | `dynamic-{region}` |
| Connected realms | `/data/wow/connected-realm/index`, `/data/wow/connected-realm/{connectedRealmId}` | dynamic |
| Item metadata | `/data/wow/item/{itemId}` | `static-{region}` |
| Item-set metadata | `/data/wow/item-set/index`, `/data/wow/item-set/{itemSetId}` | static |
| Item classes/subclasses | `/data/wow/item-class/index`, `/data/wow/item-class/{itemClassId}`, `/data/wow/item-class/{itemClassId}/item-subclass/{itemSubclassId}` | static |
| Journal raid / encounter | `/data/wow/journal-instance/index`, `/data/wow/journal-instance/{journalInstanceId}`, `/data/wow/journal-encounter/{journalEncounterId}` | static |
| Optional search / media | `/data/wow/search/item`, `/data/wow/media/item/{itemId}` | static |

Sources: [Profile API](https://community.developer.battle.net/documentation/world-of-warcraft/profile-apis),
[Game Data API](https://community.developer.battle.net/documentation/world-of-warcraft/game-data-apis),
[machine-readable Game Data definitions](https://community.developer.battle.net/api/pages/content/documentation/world-of-warcraft/game-data-apis.json).
The linked JSON documents provide endpoint parameters, not a complete equipment response schema.
The roster definition has no pagination parameter; save the whole response and measure completeness.

**L — fields present in the three sampled equipment/summary responses.** Equipment contains
`equipped_items[]`, nested `item.id`, `slot.type`, `level.value`, `quality`, `context`, `bonus_list`,
`stats`, `sockets`, `enchantments`, `spells`, `set`, `name_description`, and any new crafting/upgrade
fields where supplied, including `modified_crafting_stat` and root `equipped_item_sets`.
Summary includes `id`, `realm`, `guild`, `average_item_level`, `equipped_item_level`,
`last_login_timestamp`. Optional fields are often omitted; these samples do not establish mandatory
fields for every character. Preserve everything, including unknown fields and missing-vs-null distinctions.
No dedicated reliable public upgrade-track/embellishment/loot-transfer endpoint was established.
Bonus-ID interpretation, crafted status and tier classification need versioned mappings and tests.
Neither generic item metadata nor journal associations identify a particular equipped copy's source.

WCL v2
------

**D:** `POST https://www.warcraftlogs.com/oauth/token` exchanges Basic credentials for a token;
GraphQL reads use `POST https://www.warcraftlogs.com/api/v2/client` with a Bearer header.
`/api/v2/user` requires user authorization; it is not a way to access arbitrary private reports.
No private API support is implemented here. [Official authentication](https://www.warcraftlogs.com/api/docs)

Exact query documents live in [rwf/queries](../rwf/queries). All original 11 were validated against
live introspection; the current 12 also pass schema validation. Authenticated calls exercised all
supplied query shapes. Extra candidate fields below that are not selected in those documents
(for example attendance, zoneRanking, exportedSegments and archiveStatus) remain **D**, not **L**.
The following fields cover the proposed collection surface:

| Root/field | Relevant arguments and selections | Use / limit |
|---|---|---|
| `guildData.guild` | `id` or `name, serverSlug, serverRegion`; `id name server competitionMode stealthMode type parentGuild teams tags` | Identify WCL guild/team containers; not automatically an in-game guild. |
| `Guild.members` | `limit, page`; pagination `data { id canonicalID name server } current_page has_more_pages` | Supplement Blizzard roster. |
| `Guild.attendance` | `guildTagID, limit, page, zoneID` | Additional report/attendance evidence; maximum page size 25. |
| `Guild.zoneRanking` | `zoneId` (lowercase d) | Prior-tier cohort cross-check; not an assumed global top-20 discovery endpoint. |
| `characterData.character` | `id` or `name, serverSlug, serverRegion`; `id canonicalID name server hidden guilds` | Provider identity links and visibility. |
| `Character.recentReports` | `limit, page`; `data { code startTime endTime }`, pagination fields | Find public reports outside guild report lists. |
| `reportData.reports` | `guildID` or `guildName, guildServerSlug, guildServerRegion`; also `guildTagID, userID, startTime, endTime, limit, page, zoneID, gameZoneID` | Time bounds are epoch milliseconds. Max page size 100. Default-zone filters can miss mixed reports. |
| `reportData.report` | `code` (and documented `allowUnlisted` option) | Retrieve known reports; handle null/access errors, retain visibility. No unlisted-code enumeration. |
| `Report` metadata | `code title startTime endTime revision segments exportedSegments visibility region guild zone archiveStatus` | Observe upload/re-export changes. |
| `Report.fights` | Optional `difficulty, encounterID, fightIDs, killType` | Pulls, kills and compositions; see fields below. |
| `Report.masterData.actors` | `id gameID name server type subType petOwner` | Report-local actors; filter Player when discovering characters. |
| `Report.playerDetails` | `fightIDs, startTime, endTime, difficulty, encounterID, includeCombatantInfo` | JSON including gear/spec/talents; retain whole response. |
| `Report.events` | `dataType: CombatantInfo` or `All`, `fightIDs, startTime, endTime, limit` | **L:** gear and null-terminal pagination observed; limit is not a hard event-count ceiling. |
| `worldData.zones` / `.zone` | `zones(expansion_id)` or `zone(id)`; `id name encounters {id name} difficulties {id name sizes}` | Explicit tier/boss/difficulty configuration; never conflate journal encounter IDs with WCL encounter IDs. |
| `rateLimitData` | `limitPerHour pointsSpentThisHour pointsResetIn` | Actual account point budget and reset seconds. |

Sources for the table: [Guild](https://www.warcraftlogs.com/v2-api-docs/warcraft/guild.doc.html),
[GuildData](https://tw.warcraftlogs.com/v2-api-docs/warcraft/guilddata.doc.html),
[CharacterData](https://www.warcraftlogs.com/v2-api-docs/warcraft/characterdata.doc.html),
[Character](https://tw.warcraftlogs.com/v2-api-docs/warcraft/character.doc.html),
[ReportData](https://www.warcraftlogs.com/v2-api-docs/warcraft/reportdata.doc.html),
[Report](https://www.warcraftlogs.com/v2-api-docs/warcraft/report.doc.html),
[Actor](https://www.warcraftlogs.com/v2-api-docs/warcraft/reportactor.doc.html),
[event types](https://www.warcraftlogs.com/v2-api-docs/warcraft/eventdatatype.doc.html),
[WorldData](https://www.warcraftlogs.com/v2-api-docs/warcraft/worlddata.doc.html),
[Zone](https://www.warcraftlogs.com/v2-api-docs/warcraft/zone.doc.html),
[RateLimitData](https://www.warcraftlogs.com/v2-api-docs/warcraft/ratelimitdata.doc.html).

`ReportFight`: retain `id, encounterID, name, difficulty, size, startTime, endTime, kill,
inProgress, bossPercentage, fightPercentage, averageItemLevel, friendlyPlayers, friendlySpecs,
friendlyItemLevels`. Specs/item levels align by array index with player actor IDs. Fight times
are millisecond offsets from the report start. **L:** all 47 sampled fights have equal array lengths,
resolved actors and offsets within report duration; absolute conversion examples are in the results.
Keep original values. `fightPercentage` and `bossPercentage` have
different meanings; multi-phase progress should not be replaced by raw health.
[Fight schema](https://www.warcraftlogs.com/v2-api-docs/warcraft/reportfight.doc.html)

`ReportPagination` and `CharacterPagination`: `data`, `current_page`, `has_more_pages`, plus
`total`, `last_page`, `per_page`, `from`, `to` are schema-confirmed. **L:** event paginator
`data: JSON` and `nextPageTimestamp: Float` are nullable. General-event pages returned exact
advancing cursors then null; a CombatantInfo `limit: 100` returned 848 events and null.
Do not interpret successful HTTP alone as a successful page or truncate oversized pages.
[Report pagination](https://tw.warcraftlogs.com/v2-api-docs/warcraft/reportpagination.doc.html),
[character pagination](https://ru.warcraftlogs.com/v2-api-docs/warcraft/characterpagination.doc.html),
[event paginator to verify](https://www.warcraftlogs.com/v2-api-docs/warcraft/reporteventpaginator.doc.html)

Race queries have these documented signatures, both returning untyped JSON:

```graphql
progressRace(serverRegion: String, serverSubregion: String, serverSlug: String,
             zoneID: Int, competitionID: Int, difficulty: Int, size: Int,
             guildID: Int, guildName: String): JSON
detailedComposition(competitionID: Int, guildID: Int, guildName: String,
                    serverSlug: String, serverRegion: String,
                    encounterID: Int, difficulty: Int, size: Int): JSON
```

Call them under `progressRaceData`. Supply explicit difficulty rather than accepting the
highest-difficulty default. `detailedComposition` has **no `zoneID` argument**. Pin an encounter
and competition where known. **L:** useful Heroic and Mythic compositions were returned for two
encounters each; Heroic had 30 players and Mythic 20. Other encounters returned domain errors
inside JSON. Role/player/gear-subset shapes are observations, not a GraphQL-enforced contract.
Race pulls include provider-labelled private-report summaries (`reportIsPrivate: true`, null code).
Precise private provenance of a particular composition and active-race coverage remain **P**.
Preserve the query and raw JSON rather than assuming a mandatory nested player/gear shape.
[Official race schema](https://www.warcraftlogs.com/v2-api-docs/warcraft/progressracedata.doc.html)

No `Loot` member appears in the **L** introspected `EventDataType` enum. That is evidence against assuming
a dedicated loot-events query, not proof that no JSON surface could ever expose loot-related data.
Gear in combatant info is equipment evidence, not a drop, recipient or trade record. Inspect
actual payloads and ask the provider before planning exact loot allocation analysis.
[EventDataType](https://www.warcraftlogs.com/v2-api-docs/warcraft/eventdatatype.doc.html)
