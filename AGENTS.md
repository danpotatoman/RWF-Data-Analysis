# Repository instructions

Read [STATUS.md](STATUS.md) near the start of project work. It is the authoritative
current-state index and takes precedence over stale summaries. Read
[repository hygiene](docs/REPOSITORY_HYGIENE.md) before adding artifacts.

## Project-state discipline

- Update STATUS when implementation, validation, live execution, analysis, active
  runs, blockers/deferments or the next milestone materially change. Update its review
  date; supporting historical records identify their own revisions where available.
  Do not require STATUS to name its containing commit or amend commits solely to
  refresh a status-review hash.
- Support changes with repository evidence and links. Keep implementation, validation,
  execution and analysis separate. IMPLEMENTED or TESTED / SIMULATED never proves
  LIVE EXECUTED; completed execution never proves scientific acceptance criteria passed.
- Register active experiments with LIVE/SYNTHETIC mode, run ID, dates, last verified
  state and sanitized evidence. Do not infer liveness from a PID or stale durable phase.
- Create/finalize a record for meaningful completed live or synthetic experiments using
  [the experiment convention](docs/experiments/README.md). Routine test reruns need
  a dated validation summary, not duplicate experiment records.
- Preserve historical findings/audits, their counts and dates. Use dated corrections,
  errata or superseding records for substantive changes; never silently rewrite results
  or assign current capture revisions to experiments with unknown original revisions.
- Keep STATUS short and link outward. README is a public summary; design/spec/runbooks
  describe methodology; raw evidence stays local under the hygiene policy.

## Repository hygiene and licensing

- Never commit credentials, tokens, authenticated headers, or secret/local configuration.
- Never expose secret values in output, logs, reports, patches, or test diagnostics.
- Treat provider responses, downloaded documentation/data, databases, and generated
  reports/evidence as local by default. Preserve valuable local data; ignore it rather
  than deleting it to prepare a commit.
- Use small deterministic synthetic fixtures. Sanitize and document provenance before
  versioning any provider-derived fixture; exclude authentication and identifying metadata.
- Review third-party redistribution, privacy and file size for every new artifact category.
  Do not commit large generated artifacts without an explicit documented justification.
- Avoid personal absolute paths and machine-specific state in committed files.
- Keep offline tests independent of credentials, caches and real provider archives.
  Preserve source URLs, timestamps, hashes and research limitations where useful.
- Run `python tools/repository_hygiene.py` and the offline tests before proposing a
  commit; after staging run `python tools/repository_hygiene.py --staged` as well.
  A clean ignore check does not establish that tracked files or history are safe.
- If a real credential is discovered in tracked content or history, stop and report
  only its location/category. Deleting the working file does not repair history.
- Do not push, add remotes, publish, upload research data or rotate credentials
  without explicit user authorization. Local preparation is not publication authorization.
- Original software/code authored for this repository uses the MIT License in
  `LICENSE`. Preserve this owner-approved decision; license changes require the
  owner's authorization. The grant supplies no rights to Blizzard, Warcraft Logs,
  World of Warcraft, provider-derived data, third-party documentation or other
  third-party material. Preserve redistribution and retention review requirements.
