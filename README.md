# RWF Data Analysis

**Reproducible data-collection and analysis infrastructure for studying World of Warcraft's Race to World First (RWF).**

This project investigates what can be established about top RWF guilds from the **Blizzard Profile/Game Data APIs** and **Warcraft Logs (WCL)**. It combines resilient multi-provider API collection, exact-byte archival, schema validation, deterministic replay, and long-running experiment orchestration to measure guild populations, observed equipment changes, historical raid participation, and—most importantly—the **coverage and uncertainty** of those observations.

The project is currently built around a fixed **48-hour pilot experiment** designed to test whether this data can support a broader RWF collection and analysis system. The collection infrastructure and offline validation are implemented; **the real 48-hour experiment has not yet been run**, and the production collector/data model remain proposals.

## Engineering highlights

- **Resilient API collection** across Blizzard and Warcraft Logs with authenticated clients, bounded pagination, retries, and provider-aware handling.
- **Exact-byte SQLite archival** of provider responses and request metadata for reproducibility and later analysis.
- **Deterministic replay** of archived evidence without requiring live APIs or credentials.
- **Long-running experiment orchestration** with persistent scheduling, API-budget controls, provider cooldowns, restart recovery, and consistent backups.
- **Schema and response validation** designed to preserve unknown fields while detecting unexpected API behavior.
- **Crash-safe state recovery** so interrupted pilot runs can resume without blindly repeating completed work.
- **Offline synthetic validation** covering pilot execution, restart/recovery, replay, unavailable targets, roster changes, and other failure conditions.
- **85-test offline suite** that runs without credentials, network access, raw research archives, or IDE state.
- **Credential-free CI** configured for Windows and Linux.
- **Repository security/hygiene tooling** that checks staged Git blobs for secrets, authenticated data, personal paths, unintended generated artifacts, and other publication risks.

## System overview

```text
                 ┌─────────────────────┐
                 │    Blizzard APIs    │
                 └──────────┬──────────┘
                            │
                            │ authenticated requests
                            ▼
┌─────────────────────┐   Collection /   ┌─────────────────────┐
│    Warcraft Logs    │ ───────────────► │ Exact-byte archive  │
│       GraphQL       │   validation     │      (SQLite)       │
└─────────────────────┘                  └──────────┬──────────┘
                                                  │
                                      deterministic replay
                                                  │
                                                  ▼
                                       ┌─────────────────────┐
                                       │ Pilot state /       │
                                       │ validated evidence  │
                                       └──────────┬──────────┘
                                                  │
                                                  ▼
                                       ┌─────────────────────┐
                                       │ Coverage reports /  │
                                       │ projections         │
                                       └─────────────────────┘
```

OAuth responses remain in memory; archived request metadata excludes authenticated headers and cookies. Provider payloads remain local and may still contain identifying data.

The system deliberately distinguishes **observation from inference**. For example, an equipment snapshot establishes when an item was observed, not when it was acquired. Likewise, public reports cannot establish complete private raid activity or character ownership.

See [design and limitations](docs/design.md) for the detailed methodology and interpretation boundaries.

## Research status

The live feasibility study was performed on **2026-09-17** and analyzed on **2026-09-22**. These observations are dated research findings, not guarantees about current provider behavior.

Implemented:

- authenticated Blizzard and WCL probes
- exact-byte SQLite response archival
- bounded pagination
- schema validation
- saved-evidence replay
- fixed 48-hour pilot scheduling
- request/API-budget controls
- restart recovery
- consistent backup
- read-only status/projection tooling
- synthetic offline pilot simulation
- repository publication/security safeguards

The **real 48-hour pilot has not started**. Production-scale collection and the broader data model remain proposals pending the results of that experiment.

## Setup and offline tests

### Requirements

- Python **3.12+**
- Git

Core probes use only the Python standard library. Full tests and schema validation use the pinned dependencies in [requirements-validation.txt](requirements-validation.txt).

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python tools/repository_hygiene.py
```

If activation is unavailable, use `.\.venv\Scripts\python.exe` in place of `python`.

### macOS / Linux

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python tools/repository_hygiene.py
```

The test suite uses synthetic responses and a minimal generated test schema. It requires **no credentials, network access, raw archives, or IDE state**.

To exercise the accelerated 48-hour recovery scenario and replay its results entirely offline:

```sh
python -m rwf.pilot dry-run --data-dir data/pilot-synthetic-example
python -m rwf.pilot status --data-dir data/pilot-synthetic-example
python -m rwf.pilot replay --data-dir data/pilot-synthetic-example --output data/pilot-synthetic-example/replay-check
```

The synthetic scenario deliberately injects unavailable/quarantined characters, causing its two 95% scientific coverage criteria to fail while the software and recovery assertions pass.

This is a simulation, **not a real Liquid measurement**.

See the [fixture policy](tests/fixtures/README.md) for details.

## Credentials and live workflows

[`.env.example`](.env.example) documents the four required environment variables with empty values:

```text
BLIZZARD_CLIENT_ID
BLIZZARD_CLIENT_SECRET
WCL_CLIENT_ID
WCL_CLIENT_SECRET
```

Supply credentials securely through the process environment or a secret manager.

**The application does not load `.env` files.**

A single-provider probe requires that provider's credential pair; the live pilot requires all four. Credentials should never be placed in command arguments, JSON variable files, scripts, logs, or GitHub Actions.

Example probe commands:

```sh
python -m rwf.probe --help
python -m rwf.probe blizzard equipment --region eu --realm REALM-SLUG --name CHARACTER
python -m rwf.probe blizzard roster --region eu --realm REALM-SLUG --name GUILD-SLUG
python -m rwf.probe blizzard item --id 19019
python -m rwf.probe wcl rate-limit
python -m rwf.probe wcl report --variables data/report-variables.json
```

Create a local `data/report-variables.json` containing:

```json
{"code":"YOUR_PUBLIC_REPORT_CODE"}
```

Each probe retrieves one response/page with bounded retries. Raw bytes and request metadata are saved transactionally to `data/probes.sqlite`.

Use `--archive PATH` before the subcommand to select another archive location.

Failures return exit code `2` while retaining API error/partial bodies. Unknown response fields are preserved.

## Validation and reproducibility

[Validation](docs/validation.md) documents query shapes and controlled live checks.

These commands operate on saved artifacts:

```sh
python -m rwf.validation check-schema
python -m rwf.replay_validation
```

They are offline but require the excluded local feasibility archive.

A fresh public clone therefore **cannot reproduce the original live measurements** without those archives or a new authorized collection. Instead, the committed source manifest and aggregate findings preserve the provenance and conclusions of the original research without publishing the underlying raw provider data.

For the real pilot, follow [pilot operations](docs/pilot-operations.md), which covers:

- preflight
- launch
- hour-24 stop/resume
- recovery
- final replay
- backup

Live `run` and `resume` require an explicit absolute `--data-dir` outside the repository and known cloud-sync paths.

Active SQLite databases should remain on a nonsynced local volume with consistent backups. Each collection should use a fresh run directory, and collector/query code should remain frozen during the experiment.

Provider retention and redistribution requirements should be reviewed before long-term collection.

## Repository layout

| Location | Purpose |
| --- | --- |
| `rwf/` | API clients, archive schema, validation, pilot scheduler and replay |
| `rwf/queries/` | Authored provider query documents |
| `tests/` | Offline synthetic tests and fixture provenance |
| `tools/` | Research-document and repository-hygiene tooling |
| `docs/` | Design, methodology, findings, data model, runbooks and publication policies |
| `data/` | **Ignored:** local provider data, archives, synthetic runs and projections |
| `.github/workflows/offline.yml` | Credential-free Windows/Linux CI |
| `.githooks/` | Optional staged-content pre-commit validation |

Additional research documentation:

- [API inventory](docs/api-inventory.md)
- [Design and limitations](docs/design.md)
- [Feasibility findings](docs/feasibility-results.md)
- [Proposed data model](docs/data-model.md)
- [48-hour pilot specification](docs/pilot.md)
- [Historical pilot audit](docs/pilot-audit.md)

`python tools/research_docs.py` downloads public Blizzard documentation into ignored `data/research/`.

The committed [Blizzard source manifest](docs/blizzard-source-manifest.json) records URLs, hashes, and timestamps from the original research rather than vendoring downloaded provider documentation.

## Repository hygiene

[Repository hygiene](docs/REPOSITORY_HYGIENE.md) defines what belongs in Git and how new artifacts must be reviewed.

The repository intentionally excludes:

- credentials and private configuration
- raw provider/API data
- SQLite databases and sidecars
- generated reports/evidence
- virtual environments
- caches and build output
- editor/OS state
- machine-specific files

Small, reviewed, deterministic fixtures may be committed under `tests/fixtures/` with documented provenance.

Before proposing a commit:

```sh
python tools/repository_hygiene.py
python -m unittest discover -s tests -v
git diff --cached --stat
python tools/repository_hygiene.py --staged
```

To enable the optional local pre-commit check:

```sh
git config --local core.hooksPath .githooks
```

The hook inspects the entire staged index using Git blob contents, including force-added ignored files. CI repeats the checks without private credentials.

Automated checks reduce publication mistakes but cannot identify every possible secret or determine redistribution rights. Manual review and Git-history review remain part of the publication process.

## License and third-party material

Original software/code authored for this repository is licensed under the [MIT License](LICENSE).

That license does **not** grant rights to Blizzard Entertainment, Warcraft Logs, World of Warcraft, provider-derived data, third-party documentation, or other third-party material referenced by or used with this project.

Raw provider data and downloaded documentation are intentionally excluded from the repository. Redistribution and retention requirements for provider material should be evaluated independently of the repository's software license.