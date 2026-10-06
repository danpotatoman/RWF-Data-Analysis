# Local publication preparation — 2026-10-06

**Historical preparation snapshot, before the initial commit/remote setup.** The
staged-file counts, Git state, test results and readiness judgment below describe
that preparation and MIT follow-up, not the repository's current Git state. Scope
clarification added 2026-10-06; original results are preserved. See
[STATUS.md](../STATUS.md) for current project state. This is a repository audit with
offline verification, not evidence that the live 48-hour pilot ran.

Status: **PASS WITH WARNINGS** pending owner review of the dated public
game-character/report references and provider-material considerations in the research
narrative. The owner selected MIT for original repository software; that decision
is implemented in `LICENSE`. No remote, push, release, GitHub repository, upload of research
data, or live API collection was performed. Local Git was initialized on `main`;
the proposed initial public tree is staged for review without creating a commit.

## Scope and inventory

The pre-change inventory covered all project directories, including hidden files:

| Category | Finding and treatment |
| --- | --- |
| Source and queries | Python `rwf/`, authored GraphQL query documents, `tools/`; include |
| Tests | Synthetic inline responses, generated minimal schema; include |
| Research docs | Nine original technical docs/manifest; preserve and remove personal setup paths |
| Configuration | Pinned validation dependency; add empty environment example and safe Git/CI rules |
| Raw/downloaded data | Blizzard/WCL feasibility payloads, full introspection, public portal JSON; local only |
| Generated evidence | Synthetic pilot runs, projections, cost/index ledgers, reports and locks; local only |
| Databases | Seven SQLite files plus WAL/SHM sidecars; preserve locally |
| Environments/caches | Existing Python venv and bytecode caches; local only |
| Java/build/editor/OS | No Java project, screenshots or separate third-party asset tree found; ignore common future artifacts |

Before preparation, `data/` contained 190 files totaling 99,661,656 bytes, and
`.venv/` contained 1,268 files totaling 16,239,158 bytes. The largest raw response
was about 20.2 MB. Those originals were preserved. Publication-check artifacts
generated subsequently also remain under ignored `data/`.

## Secret and privacy audit

- Scanned nonenvironment project files, including local downloaded JSON/JSONL,
  for credential literals, authenticated headers/tokens, personal home paths and emails.
- All four current process credential values were available for exact byte matching;
  no occurrences were found in project files outside the ignored virtual environment.
  A final scan of 260 nonenvironment/non-Git project files also checked the encoded
  OAuth Basic pairs; no matches. Fresh-copy scratch artifacts were excluded from
  that original-project scan and remain ignored.
- Scanned text/blob cells in all seven local SQLite databases read-only for credential,
  authentication, personal-path and email patterns; no findings in those cells.
- Credential-shaped source matches were reviewed synthetic markers and environment
  lookups. Downloaded public OAuth guide examples matched authentication patterns;
  these provider downloads remain excluded. They were not treated as actual project tokens.
- Removed six personal absolute-path occurrences from README and two runbooks.
  Kept portable relative paths, runtime-selected local paths and dated source provenance.

The staged-tree scanner additionally checks known credentials/encoded OAuth Basic
pairs, suspicious filenames, fixture auth fields, personal paths, emails, binary
types, oversized files and local/generated categories. It emits locations/categories
only. These are targeted checks, not proof that unknown secrets cannot exist in
arbitrary provider payloads. Ignored archives are not intended for publication.

## Git history

There was no `.git` directory, parent Git repository, or existing project history
before preparation. The new local repository has no commits, branches with history,
tags or remotes. There is therefore no earlier committed secret/path history to
rewrite. Future publication reviews must inspect history separately; the repository
checker validates working candidates or the entire index, not past commits.

## Safeguards and exclusions

Added a tailored `.gitignore`, empty `.env.example`, portable setup README,
`AGENTS.md`, durable hygiene policy, fixture provenance, deterministic offline
checker/tests, optional pre-commit hook, LF normalization and credential-free CI.
The checker inspects staged blob bytes, so sanitized working files cannot mask a
previously staged value and force-adding ignored files does not evade checks.

Ignore rules cover raw/downloaded data, databases/sidecars, generated report/evidence
directories, logs/runtime state, archives, private config/key files, Python caches/
environments, Maven output, editor files and OS metadata. Reviewed fixtures have a
dedicated versioned directory; source, tests, docs, query documents and dependency
pins remain included. The hook is opt-in and not installed automatically.

## Reproduction boundaries and owner decisions

Fresh developers can install the one pinned dependency, run synthetic offline tests,
and exercise/replay the accelerated pilot without credentials or collected data.
Saved-real-schema checks and replay of the original feasibility study require local
archives and cannot be reproduced from a public clone alone. The dated aggregate
findings and URL/hash manifest preserve useful evidence without distributing payloads.
CI is configured for Windows/Linux; only locally executed platforms are claimed tested.

Owner review before the first push:

- Licensing decision resolved: the standard [MIT License](../LICENSE), SPDX `MIT`,
  applies to original software/code authored for this repository. Its notice is
  `Copyright (c) 2026 Dan Temereanca`, using the current year and the single effective
  Git author name; no conflicting project attribution was found.
- The MIT grant supplies no rights to Blizzard, Warcraft Logs, World of Warcraft,
  provider-derived data, third-party documentation or other third-party material.
  Dependencies and third-party content remain subject to their respective terms.
  README, hygiene policy and agent instructions record this boundary; provider
  redistribution and retention review requirements remain in effect.
- Review whether the public character names/IDs, report codes, guild references and
  small quoted API/error-field examples retained in research docs are necessary for
  the public audience. They support dated identity/coverage findings; they are not
  raw rosters, screenshots, full downloaded documentation or full copied schemas.
- Review Blizzard/WCL redistribution and retention questions before distributing
  provider material or starting long-term collection. No legal permission is asserted.
- Inspect the complete staged diff and status privately. Run the staged hygiene check
  again after any edits, and authorize publication separately.

## Verification and proposed public tree

| Check | Result |
| --- | --- |
| Original workspace offline suite | 85 tests passed, including seven new hygiene tests |
| Clean-copy offline suite | Same 85 tests passed; process credentials/Python path overrides removed, sockets blocked |
| Clean dependency installation | New isolated venv installed `graphql-core==3.2.6` from public PyPI with cache disabled |
| Working-candidate and index hygiene | Passed; 50 proposed public files, no known secret/privacy/local-artifact findings |
| Staged whitespace | `git diff --cached --check` passed |
| Ignore boundaries | Raw SQLite, venv, bytecode, `.env`, and generated outputs ignored; fixture README, empty example and query source included |
| Documentation links | All relative Markdown links resolve within the proposed tree |
| Windows operations snippets | All PowerShell blocks parsed with zero syntax errors; live launch was not executed |
| Clean-copy CLI | Synthetic `dry-run`, read-only `status`, and `replay` all exited 0 with network blocked |
| Synthetic result | 12 baseline targets, one addition, one departure, 1,644 archived attempts; finished, replay equality and synthetic-secret exclusion true |
| History/remotes | Zero existing commits/refs/tags and zero remotes; no publication action |

The dependency download initially failed under sandbox network restrictions; the
authorized network retry succeeded. The first clean-copy test attempt before the
dependency was installed failed its schema-test import; the final installed-environment
run passed all 85 tests. Git's ownership check in the restricted runner used a
process-scoped trust exception for this specific repository, not a global setting.
Windows was exercised locally; Linux CI is configured but has not been run here.

A real clone was unavailable because no commit was created. Instead, the check
exported the exact staged blob bytes into an ignored isolated tree, initialized its
local index, and created a separate venv without copying the original environment,
data, caches or IDE state. Dependency installation used only the declared pin;
tests and CLI simulation then ran offline. Verification scratch files remain under
ignored `data/publication-check/`. The final audit text records these results;
application code and tests are the same as the verified snapshot.

Final proposed initial commit: **50 staged additions**, about 0.34 MB total, with
no unstaged or nonignored untracked files. All are UTF-8 text; the largest is about
32 KB. The optional hook has executable mode in the index. No commit was created.

| Public category | Files |
| --- | ---: |
| Python source and GraphQL queries (`rwf/`) | 21 |
| Tests and fixture provenance (`tests/`) | 7 |
| Detailed docs, manifests and policies (`docs/`) | 11 |
| Research and hygiene tools (`tools/`) | 2 |
| CI and optional hook | 2 |
| Root README, agent instructions, dependency pin, ignore/attribute rules, empty environment example and MIT license | 7 |

Existing files edited: `.gitignore`, `README.md`, `docs/validation.md`,
`docs/pilot-operations.md`, and `tests/test_pilot.py` (rename invented auth markers
to make their synthetic purpose explicit; no live credential changes).
New files: `.env.example`, `.gitattributes`, `AGENTS.md`,
`.github/workflows/offline.yml`, `.githooks/pre-commit`, this audit,
`docs/REPOSITORY_HYGIENE.md`, `tests/fixtures/README.md`,
`tools/repository_hygiene.py`, and `tests/test_repository_hygiene.py`.

The MIT follow-up added `LICENSE` and updated `README.md`, `AGENTS.md`,
`docs/REPOSITORY_HYGIENE.md` and this audit. The complete offline suite and working,
staged/index hygiene checks were rerun after the licensing/documentation changes.
The earlier clean-copy verification remains applicable to unchanged application
code, tests and dependencies; it was not repeated for the documentation-only update.
