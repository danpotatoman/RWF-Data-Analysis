# Experiment records

[STATUS.md](../../STATUS.md) is the authoritative current-state index. This directory
defines historical experiment records; existing dated findings/audits remain at
their established paths and are indexed below. Do not duplicate results to migrate
them. Design/spec/runbooks define methodology, README summarizes the project, and
local archives hold detailed evidence under [repository hygiene](../REPOSITORY_HYGIENE.md).

## Existing evidence records

| Record | Mode / scope | Execution and analysis dates |
| --- | --- | --- |
| [Feasibility findings](../feasibility-results.md) and [recovery runbook](../validation.md) | LIVE study; recovery/analysis was offline | Live 2026-09-17; analysis 2026-09-22 |
| [Pilot implementation and offline-readiness audit](../pilot-audit.md) | SYNTHETIC execution plus software verification; no live pilot | Simulation/results recorded 2026-09-23; virtual 48-hour duration |
| [Publication preparation audit](../PUBLICATION_AUDIT.md) | Repository preparation/validation snapshot, not a live experiment | 2026-10-06 before the initial commit; includes offline synthetic verification |

Legacy records predate this format. Keep their counts, dates and limitations. Mark
missing original run IDs or capture revisions UNKNOWN / NOT RECORDED; do not assign
the current Git revision to an earlier experiment. Future retrospective additions
must be dated and identify their evidence rather than implying contemporaneous capture.

## Lifecycle

1. For a meaningful live or synthetic experiment, create a record using
   `YYYY-MM-DD-short-name-run-id.md`. Fix the protocol/criteria before execution;
   mark the record PROVISIONAL while execution or analysis is incomplete.
2. Register the run in STATUS with mode, run ID, actual start, phase, last verification
   time and evidence link. On stop/pause/failure/completion, update execution state
   independently of analysis and scientific outcome. Do not infer liveness from a PID.
3. Finalize after execution and analysis have been reconciled with available evidence.
   Failed/aborted execution or inconclusive science can have a finalized record.
   Remove the active entry and link the finalized result from STATUS.
4. Treat finalized records as historical evidence. Correct substantive errors through
   dated errata or a superseding record stating what changed, why and which evidence
   supports it; preserve original conclusions. Scope/link clarifications must identify
   their date. This is a maintenance convention, not a technical immutability guarantee.

Routine unit-test reruns are validation, not separate experiments needing duplicate
records. Record their dated result in STATUS. A changed experimental protocol,
intentional new run, or materially new finding warrants a record.

## Compact record format

Use the fields below as applicable; mark unavailable information explicitly.

```text
Experiment: descriptive name
Record: PROVISIONAL or FINALIZED; record/review date
Mode: LIVE or SYNTHETIC
Run ID: stable identifier (distinct from filename/date)
Actual execution: start/end dates and timestamps, with timezone
Virtual execution: start/end and duration if SYNTHETIC; otherwise N/A
Code: capture Git revision and/or captured code/query/parser hashes
Protocol: version/revision and specification link; deviations
Questions/hypotheses: what was tested and the controls
Acceptance criteria: predeclared thresholds and denominators
Execution outcome: NOT STARTED / IN PROGRESS / PAUSED / COMPLETED / FAILED / ABORTED
Scientific outcome: each hypothesis CONFIRMED / REFUTED / INCONCLUSIVE / NOT TESTED
Criterion outcomes: PASSED / FAILED / NOT EVALUABLE, with evidence
Analysis: NOT STARTED / IN PROGRESS / RESULTS ANALYZED; date and analysis revision
Results: essential measurements, uncertainty and interpretation
Limitations: coverage, missingness, confounders, scope and departures from protocol
Evidence: sanitized references, observation IDs and hashes as appropriate
Local evidence: logical archive/run identifier, excluded artifacts and replay procedure
Corrections/supersession: dated links and reason, if applicable
```

Execution COMPLETED can coexist with a FAILED acceptance criterion or an INCONCLUSIVE
hypothesis. IMPLEMENTED and TESTED / SIMULATED are validation facts, not proof of LIVE
EXECUTED. For simulations, label virtual dates explicitly and record network-call
count; never present a virtual 48 hours as elapsed wall-clock collection.

Do not expose credentials, authenticated headers, personal absolute paths or unnecessary
identifying metadata. Link safe aggregate findings and provenance; keep raw provider
archives/databases/exports local. Use logical archive identifiers rather than machine
paths. Public readers may be unable to replay excluded evidence; state that boundary.
Sanitization and inclusion still require provider redistribution/retention review and
do not acquire permission from the repository's software license.
