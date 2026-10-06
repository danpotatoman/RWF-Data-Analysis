# RWF research and probes

Research tooling for World of Warcraft's Race to World First (RWF): investigate what
Blizzard Profile/Game Data APIs and Warcraft Logs (WCL) can establish about guild
populations, observed equipment changes, and historical raid participation. The aim
is to measure coverage and uncertainty before building a broader collector.

Implemented: dependency-free authenticated probes, exact-byte SQLite archives,
bounded pagination and schema validation, saved-evidence replay, and a fixed Liquid
48-hour pilot runner with scheduling, budget controls, restart recovery, consistent
backup, and read-only projections. The pilot has been tested offline. **The real
48-hour experiment has not started; the production collector/data model remain
proposals.** The live feasibility study was performed on 2026-09-17 and analyzed on
2026-09-22; those dated observations are not guarantees of current API behavior.

The flow is provider request ? local raw body/attempt archive ? validation or pilot
state ? reproducible projections and coverage reports. OAuth responses stay in memory;
archive metadata excludes authenticated headers and cookies. Provider payloads remain
local and may still contain identifying data. Equipment receipt time is not loot
acquisition time; public reports cannot establish complete private raid activity or
character ownership. See [design and limitations](docs/design.md).

## Setup and offline tests

Python **3.12+** and Git are required. Run from the cloned repository root. Core
probes use only the standard library; full tests/schema validation need the pinned
[requirements-validation.txt](requirements-validation.txt).

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python tools/repository_hygiene.py
```

If activation is unavailable, use `.\.venv\Scripts\python.exe` in place of `python`.
On macOS/Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-validation.txt
python -m unittest discover -s tests -v
python tools/repository_hygiene.py
```

The test suite uses synthetic responses and a minimal generated test schema. It needs
no credentials, network, raw archives, or IDE state. Exercise the accelerated 48-hour
recovery scenario and replay its results entirely offline using a new directory:

```sh
python -m rwf.pilot dry-run --data-dir data/pilot-synthetic-example
python -m rwf.pilot status --data-dir data/pilot-synthetic-example
python -m rwf.pilot replay --data-dir data/pilot-synthetic-example --output data/pilot-synthetic-example/replay-check
```

The scenario injects unavailable/quarantined characters, so its two 95% scientific
coverage criteria deliberately fail while software/recovery assertions pass. This
is a simulation, not a real Liquid measurement. See [fixture policy](tests/fixtures/README.md).

## Credentials and live workflows

[.env.example](.env.example) lists the four required environment variable names with
empty values: `BLIZZARD_CLIENT_ID`, `BLIZZARD_CLIENT_SECRET`, `WCL_CLIENT_ID`, and
`WCL_CLIENT_SECRET`. Supply values securely in the process environment or through a
secret manager. **The application does not load `.env` files.** A single-provider
probe needs that provider's pair; the live pilot requires all four. Do not put values
in command arguments, variable JSON files, scripts, logs, or GitHub Actions.

```sh
python -m rwf.probe --help
python -m rwf.probe blizzard equipment --region eu --realm REALM-SLUG --name CHARACTER
python -m rwf.probe blizzard roster --region eu --realm REALM-SLUG --name GUILD-SLUG
python -m rwf.probe blizzard item --id 19019
python -m rwf.probe wcl rate-limit
python -m rwf.probe wcl report --variables data/report-variables.json
```

Create local `data/report-variables.json` with `{"code":"YOUR_PUBLIC_REPORT_CODE"}`.
Each probe retrieves one response/page with bounded retries. Raw bytes and request
metadata are saved transactionally to `data/probes.sqlite`; use `--archive PATH`
before the subcommand to change that path. Failures return exit code 2 and retain
API error/partial bodies. Unknown fields survive.

[Validation](docs/validation.md) explains query shapes and controlled live checks.
`python -m rwf.validation check-schema` and `python -m rwf.replay_validation` are
offline **saved-artifact** tools, but require the excluded local feasibility archive.
A fresh clone cannot reproduce the original live measurements without those archives
or a new authorized collection. The source manifest and aggregate findings preserve
provenance and conclusions without publishing raw data.

For the real pilot, follow [operations](docs/pilot-operations.md) for preflight, launch,
hour-24 stop/resume, recovery, final replay, and backup. Live `run`/`resume` require an
explicit absolute `--data-dir` outside the repository and known cloud-sync paths.
Keep active SQLite on a nonsynced local volume; export consistent backups. Use a
fresh run directory, freeze collector/query code during collection, and review
unresolved provider retention rules before long-term collection or redistribution.

## Layout and research documentation

| Location | Purpose |
| --- | --- |
| `rwf/` and `rwf/queries/` | Clients, archive schema, validation, pilot scheduler/replay, queries |
| `tests/` | Offline synthetic tests and fixture provenance |
| `tools/` | Public documentation downloader and publication hygiene checker |
| `docs/` | Detailed research, data model, runbooks, historical audit and source manifest |
| `data/` (ignored) | Local provider downloads, raw archives, synthetic runs and projections |
| `.github/workflows/offline.yml` | Credential-free tests and hygiene on Windows/Linux |
| `.githooks/` | Optional staged-content pre-commit check |

Read [API inventory](docs/api-inventory.md), [proposed model](docs/data-model.md),
[feasibility findings](docs/feasibility-results.md), [pilot specification](docs/pilot.md),
and [historical pilot audit](docs/pilot-audit.md). `python tools/research_docs.py`
downloads public Blizzard documentation to ignored `data/research/`; the committed
[source manifest](docs/blizzard-source-manifest.json) records URLs, hashes and timestamps
for the original research, rather than vendoring downloaded provider documentation.

## Safe contributions and publication

[Repository hygiene](docs/REPOSITORY_HYGIENE.md) defines what belongs in Git and how
to review new artifacts. `.gitignore` excludes credentials/private configuration,
raw data, databases, generated reports, environments, caches, build/editor/OS state.
Small reviewed fixtures belong under `tests/fixtures/`, with documented provenance.

Before proposing a commit:

```sh
python tools/repository_hygiene.py
python -m unittest discover -s tests -v
git diff --cached --stat
python tools/repository_hygiene.py --staged
```

Optional local hook installation, with the virtual environment active:

```sh
git config --local core.hooksPath .githooks
```

The hook checks the entire index using staged bytes, including force-added ignored
files. CI repeats checks without private credentials. These checks reduce mistakes
but cannot recognize every secret or certify redistribution rights; manual review
and history review remain necessary.

Original software/code authored for this repository is licensed under the
[MIT License](LICENSE), SPDX identifier `MIT`, copyright (c) 2026 Dan Temereanca.
This license grants no rights to Blizzard, Warcraft Logs, World of Warcraft,
provider-derived data, third-party documentation, or other third-party material.
Third-party dependencies and material remain subject to their respective terms.
Access to provider data/documentation does not itself establish permission to
redistribute it; the existing provider redistribution and retention cautions apply.
See [local publication audit](docs/PUBLICATION_AUDIT.md) for verified readiness and
remaining review items. Publication/push requires explicit owner authorization.
