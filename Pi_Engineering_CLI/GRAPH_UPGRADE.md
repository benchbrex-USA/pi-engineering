# Graph orchestration outcome contract

## Facts and baseline

The product is `pi-engineering`, Python >=3.11, setuptools/pip, SQLite/WAL,
Pydantic, asyncio, Rich and prompt-toolkit. macOS/Linux are the supported
local execution environments (fcntl locks); no distributed workers exist.
CLI input in pi_app calls Engine for bounded model/tool loops; pi_workflow
coordinates separate Engine tasks. ToolBroker enforces capabilities and exact
operator approval protects writes. MCP is a tool transport, not a scheduler.
The current workflow uses topological batches plus gather: dependents wait for
unrelated slow peers; any blocked peer ends scheduling. Checkpoints preserve
individual tasks but workflow records lack explicit workspace/schema binding.
Pre-existing 0.4.0 UI changes are preserved. No AGENTS.md was found by the
repository file inventory; host and user instructions apply.

## Selection and alternatives

| Improvement | Problem / mechanism | Expected benefit / measurement | Risk / dependency |
| --- | --- | --- | --- |
| Completion-driven readiness | Replace batch barrier with bounded FIRST_COMPLETED admission, all-success joins | Independent descendants start sooner; event-order tests and equivalent synthetic timing trials | Cancellation cleanup; existing Engine checkpoints |
| Resource-aware admission | v2 nodes declare exclusive resource names and priority; task-level OS locks also cover manual approval/resume | No overlap for declared resources; concurrency/conflict tests | Declarations cannot discover arbitrary remote conflicts; locks shared by participating tasks only |
| Blocker navigator | Offline validate and persisted explain views, readiness reasons and next actions | Operators can distinguish dependencies, review, failure and stale config without inference | Must not dispatch tools or leak payloads; shared validated graph contract |
| Resume binding | Version/workspace/plan and task configuration checks before scheduling | Refuse stale completed evidence; preserve successful branches without repeat calls | Legacy upgrade must validate before binding |

Chosen: retain the single-process engine, upgrade its scheduler and inspection
contract together. Alternative: retain waves and only add explanations (does
not fix observed scheduling waste). A separate distributed queue would add
ownership/lease/migration costs without a demonstrated deployment need.

## Acceptance

1. A finished branch releases its dependent without waiting for an unrelated
   running or approval-blocked branch; all joins still require every prerequisite
   to be completed successfully. No arbitrary cycles, any/quorum joins or skips.
2. Running tasks never exceed concurrency. v2 priorities have deterministic
   name tie-breaking; finite DAG admission means no infinite arrivals/starvation.
   Declared exclusive resources do not overlap, including direct task resume.
3. Cancellation drains children and persists interrupted/unknown task outcomes;
   failed/rejected/unknown nodes cannot release dependents. No automatic effect retry.
4. Completed work is reused only within compatible plan/workspace/configuration
   bindings. Legacy v1 identity remains stable. Config drift stops all admission.
5. `workflow FILE` remains supported. `--validate` and `--explain` invoke no
   models/tools, offer stable JSON and readable node/blocker output. Invalid
   plans create no tasks. No non-interactive approval is synthesized.
6. Regression suite, adversarial graph tests, wheel and installed-command checks
   pass. Synthetic timings state sample size/variation and are not model benchmarks.

## Boundaries and runtime semantics

v1 plans retain their fields and limits. v2 adds priority and exclusive resources;
both retain default concurrency 4, maximum 8 and maximum 32 nodes as explicit
local admission budgets in this release. Per-agent deadline and step budgets
remain authoritative. No new inference, hosted data transfer or paid calls.
Dependencies carry successful upstream answer text as untrusted context, not
typed bindings or authority. No claim of typed output validation is introduced.
Graph revision is a content hash, immutable per flow identity; changing a plan
creates a separate flow and fresh tasks/approvals, not a silent replan.
Resource keys are operator-declared names, not permission grants or inferred
file paths. Locks protect participating local tasks; unrelated programs and
remote services require their own concurrency/idempotency controls.
Task state remains authoritative. Task creation/linking precedes dispatch;
an orphan pre-dispatch task is harmless and is not executed automatically.
SQLite saves workflow snapshots; Engine journals effect intent before dispatch.
There is no universal exactly-once guarantee or compensation guarantee.

## Development task graph (not product runtime data)

See graph-development.json. Evidence is attached to each outcome, not inferred
from an upstream node. Execution is serial by this agent; no delegated workers.

## Backlog / non-goals

1. Typed goal-to-graph compilation and executable node acceptance schemas.
2. Explicit branch predicates and bounded-loop/subgraph contracts.
3. Versioned replanning with descendant invalidation and fresh approvals.
4. Effect-free fault simulation and trace-based optimization evaluation.
5. Distributed coordination only after a real multi-worker requirement.

No publication, Git push, deployments, permission changes, new customer
integrations or independent qualification claims are part of this slice.
