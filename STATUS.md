# Current project state

**Authoritative current-state index.**
Last reviewed against repository state on **2026-10-06**. Supporting historical
records identify their own revisions where available.

Read this file near the start of work. It takes precedence over stale README or
runbook summaries; linked records supply the evidence. Resolve conflicting evidence
before changing a state. **IMPLEMENTED does not imply LIVE EXECUTED.** Execution
completion does not imply scientific acceptance criteria passed. The four dimensions
below are independent; experiment mode and hypothesis outcome are separate again.

## Work and evidence

| Work item | Implementation | Validation | Execution | Analysis / evidence |
| --- | --- | --- | --- | --- |
| Live feasibility study | IMPLEMENTED probes/validation | TESTED; saved-schema checks | LIVE EXECUTED / COMPLETED, 2026-09-17 | RESULTS ANALYZED, 2026-09-22; [findings](docs/feasibility-results.md), [recovery](docs/validation.md) |
| 48-hour pilot software | IMPLEMENTED fixed one-guild runner | TESTED / SIMULATED; readiness audited 2026-09-23 | Live experiment NOT STARTED; see separate row | RESULTS ANALYZED for software validation; [instrument](docs/pilot.md#implemented-instrument), [offline audit](docs/pilot-audit.md) |
| Accelerated 48-hour pilot | IMPLEMENTED synthetic scenario | TESTED / SIMULATED | SYNTHETIC / COMPLETED; virtual 48 hours, 1,644 simulated attempts, zero network calls | RESULTS ANALYZED, 2026-09-23; [simulation results](docs/pilot-audit.md#final-verification) |
| Actual wall-clock/live 48-hour pilot | IMPLEMENTED instrument; PLANNED experiment | TESTED / SIMULATED instrument; live criteria unmeasured | PLANNED / NOT STARTED according to repository evidence | NOT STARTED; [protocol and criteria](docs/pilot.md#questions-and-acceptance-criteria), [launch runbook](docs/pilot-operations.md) |
| Production collector / normalized model | PLANNED / DEFERRED; model not deployed | NOT STARTED for production scope | NOT STARTED | NOT STARTED; [proposed model](docs/data-model.md), [scope limits](docs/pilot-audit.md#requirement-checklist) |
| Broader RWF coverage, split/ownership/loot/DPS analysis | PLANNED / DEFERRED pending coverage evidence | NOT STARTED for broader scope | NOT STARTED | NOT STARTED; [next steps](docs/design.md#unresolved-work-and-next-steps) |

The synthetic scenario deliberately failed both 95% coverage thresholds because of
injected unavailable/quarantined targets; archival, recovery and replay checks passed.
These outcomes are software validation, not live Liquid measurements. Earlier
feasibility calls do not count as execution of the separate live 48-hour pilot.

## Active runs and validation

No active LIVE or SYNTHETIC experiment is registered in repository evidence at this
review. No other IN PROGRESS work item is recorded. This does not establish process
liveness or rule out an unrecorded external run: live storage is outside the project.
Register an active run here with mode, run ID, actual start, phase, last verified time
and a sanitized evidence reference. Confirm live/synthetic mode and fresh run-state
evidence before claiming a run is active; a PID or durable phase alone is insufficient.

Latest offline validation: **85 tests passed on 2026-10-06**, with credentials removed
and sockets blocked; working-candidate and staged/index hygiene and documentation
links passed. This documentation update performed no live API collection. Windows
has been checked locally; Linux CI is configured but not recorded as executed.
Historical 38-/78-/85-test records retain their original dates and scopes.

## Next milestone and scoped dependencies

**Run the real wall-clock 48-hour Liquid pilot after operator launch preflight, then
analyze coverage, snapshot yield, costs, hour-24 recovery and raw replay against the
protocol's acceptance criteria before expanding production scope.** This is a
recommendation, not authorization to launch. Follow the [operations guide](docs/pilot-operations.md).

- No recorded implementation blocker prevents the fixed temporary pilot as of its
  [readiness audit](docs/pilot-audit.md). Launch still needs fresh credential/bootstrap
  checks, suitable nonsynced storage, budget review and an operator launch decision.
- BLOCKED pending clarification for the corresponding broader scopes: historical
  Profile retention/deletion rules and CN access. These do not establish a blocker
  for every temporary pilot activity; [scope qualification](docs/pilot.md#questions-and-acceptance-criteria).
- DEFERRED: production expansion until pilot results; non-roster actor discovery;
  active-RWF composition timing/provenance experiments until suitable windows/controls;
  exact loot attribution may remain unidentifiable. [Design](docs/design.md#unresolved-work-and-next-steps).

## Maintenance and evidence hierarchy

Update this index and its review date when a dimension, active run, blocker,
deferment or next milestone materially changes. Link supporting evidence; do not
promote simulations to live execution. Preserve dated results and use corrections
or superseding records. [Experiment-record convention](docs/experiments/README.md)
defines the format and indexes existing records without duplicating their findings.

Hierarchy: **STATUS.md** (current state) → **dated experiment records/audits/findings**
(historical execution/results) → **README** (public summary). Design/spec/runbooks
describe intended behavior; local archives/databases hold detailed raw evidence and
remain excluded from Git under [repository hygiene](docs/REPOSITORY_HYGIENE.md).
