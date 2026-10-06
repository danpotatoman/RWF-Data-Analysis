# Repository instructions

Read [repository hygiene](docs/REPOSITORY_HYGIENE.md) before adding artifacts.

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
