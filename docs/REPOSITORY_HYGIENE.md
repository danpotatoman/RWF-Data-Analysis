# Repository hygiene

Git contains reproducibility code and reviewed research narrative. Provider archives
and local experiment state remain local. Preserve valuable evidence without publishing
it: ignore it, use nonsynced collection storage, and make consistent database backups.
Never destroy research data merely to obtain a clean Git status.

## Safe to commit

- Source, query documents, tests, schemas/migrations authored for this project.
- Documentation, dated aggregate findings with limitations, source URL/hash manifests,
  and reproducibility scripts.
- Dependency pins, CI, safe defaults, and examples with empty credential values.
- Small deterministic sanitized fixtures with provenance and a reason for inclusion.

## Never commit

- Credentials, `.env`, tokens, OAuth responses, authenticated headers, cookies,
  secrets in URLs, or secret/private/local configuration. Public environment variable
  names are fine; real values are not.
- Raw API archives, provider downloads, bulk data, active/backup databases, replay
  exports, local reports/evidence, logs, run locks/stop markers or PID state.
- Virtual environments, Python/tool caches, Java/Maven build output, editor/OS files,
  machine-specific paths/state or unnecessary personal information.

Local artifacts belong under ignored `data/`, `reports/`, `outputs/`, `artifacts/`,
`local/`, or `tmp/`. Live pilot data must also be outside the project and known sync
directories. Arbitrary `--archive`/`--output` paths are possible: deliberately choose
local storage. Ignore rules never untrack files and `git add -f` can bypass them.

## Review before committing

New datasets, provider-derived fixtures, generated reports, screenshots, binaries,
large files, third-party documentation/schemas/assets, character/report identifiers,
and user/machine metadata need review. Public API readability does not settle
redistribution status. Document purpose, provenance, sanitization, size, and
rights/retention questions before adding a category.

## Software license and third-party boundary

The owner selected the [MIT License](../LICENSE), SPDX identifier `MIT`, for
original software/code authored for this repository. The copyright notice is
`Copyright (c) 2026 Dan Temereanca`, using the current year and the unambiguous
configured Git author name. Preserve the standard license text and copyright notice;
changes to the licensing decision require the owner's authorization.

This grant supplies no rights to Blizzard, Warcraft Logs, World of Warcraft,
provider-derived data, third-party documentation or other third-party material.
Dependencies and third-party material retain their respective terms. A downloaded
response, copied schema, screenshot, provider documentation excerpt or derived
dataset does not acquire MIT redistribution permission merely by entering this
repository or being processed by MIT-licensed code. Continue the existing
redistribution, provenance, sanitization and retention review before including
provider material; raw archives remain local by default.

Existing research retains dated public game-character/report references when they
substantiate identity or coverage findings. They are not asserted to identify real
people or establish ownership. Review whether these references are necessary for
the intended audience before publication; do not expand them into raw roster dumps.

## Contributor and agent workflow

1. Read this policy and `AGENTS.md`. Classify new output as code, a reviewed
   fixture/document, or local evidence before generating it.
2. Put local evidence in ignored storage; update `.gitignore` for new local categories.
   Follow `tests/fixtures/README.md`; keep tests independent of credentials/archives.
3. Review committed defaults/examples for values and personal paths. Use process
   environment or a secret manager for live configuration. Dotenv is not auto-loaded.
4. Run `python tools/repository_hygiene.py` and `python -m unittest discover -s tests -v`.
5. Stage intended files only. Inspect `git status --short`, `git diff --cached --stat`,
   `git diff --cached --name-status`, and the actual diff privately. Never paste suspect
   values into reports/output. Run `python tools/repository_hygiene.py --staged`
   to check all index bytes, including ignored files added by force.
6. Before publication inspect reachable Git history as well as the current tree.
   Preparation began without history. Future reviews must inspect prior commits,
   tags and branches; this scanner checks candidates/index, not historical blobs.
7. Stop on real credentials in tracked content/history. Report location/category only.
   Revoke/rotate with authorization; repair affected history before publishing.
   Deleting a working file or adding an ignore rule is insufficient.
8. Do not push, add remotes, publish or upload research data without explicit approval.

## Automated checks

`tools/repository_hygiene.py` is standard-library-only, repository-owned and offline.
It reports locations/categories, never matching values. It checks:

- Known current process credentials and encoded OAuth Basic pairs, when available.
- Credential literals, authenticated headers, private keys and common token formats;
  authentication fields in saved fixtures.
- Personal absolute home-directory paths and email addresses needing privacy review.
- Local/generated categories, binary/unreviewed types, symlinks/submodules, and files
  over 1 MiB. `.env.example` must contain only the four empty assignments.

Exact existing in-memory synthetic markers have file-specific exemptions. Never
exempt a directory or add a real value to that list. For legitimate new artifact
types, document review and narrowly update the checker/tests. There is no bypass
flag. Scanners cannot prove arbitrary strings are nonsecret or certify redistribution.

`--staged` and `--tracked` both inspect the entire index via Git blob IDs, including
differences between staged and working content. CI uses `--tracked` on clean checkouts.
Default mode includes tracked working files and nonignored untracked candidates.
An empty candidate/index set fails. CI runs offline tests on Windows and Linux;
live schema/feasibility commands and the real pilot require separate authorization
and configuration. Dependency installation uses the package index; tests/checks
themselves require no network.

Optional hook (activate your virtual environment first):

```sh
git config --local core.hooksPath .githooks
```

The versioned pre-commit hook runs the staged checker. Git for Windows supplies its
shell. Ensure `python` resolves to Python 3.12+; remove the opt-in with `git config
--local --unset core.hooksPath`. Hooks can be bypassed, so CI and manual review remain
required. No pre-push hook, paid scanner or live API check is needed for development.
