# Graph upgrade verification: 0.5.0

Date: 2026-09-13. Scope: local macOS arm64 / Python 3.11.
Verdict: PASS WITH GAPS for the selected local release contract.

## Claims and evidence

| Acceptance | Evidence | Result |
| --- | --- | --- |
| Early dependent release | Event-gated test cannot finish under the old wave barrier | PASS |
| Independent work survives review pause | Real Engine proposal/write approval plus independent child and all-join | PASS |
| Bounded concurrency, stable priority | Seven-node bound test and equal-resource priority/name ordering | PASS |
| Resource ownership | Non-overlap, manual resume, cross-process owner, partial acquisition cleanup | PASS |
| Recovery | Cancel during model and after dispatch, unknown-effect replay denial, completed-node reuse | PASS |
| Validation/trust | Missing/duplicate references, cycles, invalid resource/priority, unknown agent/join and duplicate JSON keys rejected before tasks | PASS |
| Revision/configuration | v1 ID unchanged, legacy migration, config drift, workspace/schema/revision mismatch and fresh revision approvals | PASS |
| Offline experience | JSON validate/explain without Engine.advance or new state; no task payload in output | PASS |
| Visual experience | Real offline validation rendered and inspected at 40 and 100 columns; wraps without clipping | PASS |

The final direct-approval workspace-binding test passed. The tests use deterministic
model/broker fixtures, plus actual local file writes, SQLite and OS locks.
No live model or customer integration was invoked for this scheduler upgrade.

## Final release pass

- Full source suite: 86 tests passed (65 baseline plus 21 new graph tests).
- Extracted final source archive: all 76 packaged product tests passed.
- Bandit: all thirteen production modules scanned, no findings.
- Dependency set unchanged from the audited 0.4.0 lock; pip check passed.
- Wheel built and installed locally; public command returns 0.5.0.
- Installed proposal/approval/write/readback/replay/retrieval/memory/checks and
  encrypted recovery acceptance passed.
- Installed --validate JSON and --explain plain commands passed from /tmp.
- Installed changed graph modules match the verified source byte-for-byte.
- Development graph validator checks IDs, cycles, dependencies, states and
  evidence references; this is separate from runtime Workflow validation.
- Complete tracked diff and new runtime/test files reviewed; diff --check clean.

The source archive includes the product tests, contract, development graph and
this report. No Git commit, push, deployment or external publication was performed.

## Equivalent synthetic timing baseline

Harness: `.venv/bin/python tests/benchmark_workflow.py`.
Three-node graph, concurrency 2, model fixtures sleeping 30/200/200 ms, five
fresh temporary workspaces per version. Both versions use the same harness and
real Engine/SQLite overhead. This is not an inference or distributed benchmark.

| Version | Seconds per trial | Median | Min-max |
| --- | --- | --- | --- |
| Original 0.4.0 waves | .433871, .432954, .441971, .448754, .447298 | .441971 | .432954-.448754 |
| Final completion-driven scheduler | .249441, .254857, .259246, .256349, .249623 | .254857 | .249441-.259246 |

Observed median elapsed reduction: approximately 42.3%. This particular graph
has avoidable waiting; fully serial graphs cannot gain this overlap. No general
speed/intelligence/reliability multiplier is claimed from five synthetic samples.

## Reproduce

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/benchmark_workflow.py
.venv/bin/python tests/check_development_graph.py
.venv/bin/python tests/check_distribution.py "$PWD/.venv/bin/pi-engineering"
.venv/bin/pi-engineering workflow workflows/review.json --validate --json
.venv/bin/pi-engineering workflow workflows/review.json --explain --plain
```

## Limits and recovery

Finite single-process DAG, all-success joins, no dynamic replanning, typed output
bindings, new loop constructs, distributed leases, compensation or exactly-once
effects. These remain explicit backlog items, not hidden partial features.
Locks cover declared resources on participating tasks, not arbitrary programs
or remote side effects. Resource contention is bounded to one dispatch attempt
per node per invocation; operator can retry after the owner exits.
Per-agent inference/elapsed limits are unchanged. Waiting for approval consumes
no new inference. Cancellation cannot prove a remote effect was cancelled.

No schema/data deletion; legacy bindings are added only after validation. An
interruption before task-to-flow linking can leave an unused pre-dispatch task;
it has performed no effect and is not automatically executed. Old releases do
not understand the new resource contract, so rollback uses retained packages
with a fresh workspace/v1 plans, never downgrading active v2 runs.
See README.md for exact migration and rollback guidance.

Existing customer-account and independent security/usability qualification gaps
in VERIFICATION.md remain open. macOS tests here are not evidence of remote CI
or Linux execution. Security scan is static and performed by the implementation
agent, not an independent assessment.

---

## Production seal addendum (2026-09-15)

Executed against the frozen graph tree on branch `feat/platform-0.6-presets`.

### Commands
```sh
.venv/bin/python -m unittest tests.test_graph_scheduler tests.test_graph_production -v
.venv/bin/pi-engineering workflow workflows/implement-review.json --validate --json
```

### Results
| Gate | Result |
| --- | --- |
| test_graph_scheduler (21) | PASS |
| test_graph_production (6) | PASS |
| Workflow packs load | PASS |
| Persona default workflows load | PASS |
| inspection_schema=1 | PASS |
| validate/explain side-effect proof | PASS |
| Resume matrix (parent statuses) | PASS |
| All-success join on budget exhaustion | PASS |
| CI workflow added | `.github/workflows/pi-graph.yml` |

### DoD G1–G10 (graph spec)
| ID | Status |
| --- | --- |
| G1 graph tests + packs | PASS locally; CI file added (remote run depends on SCM) |
| G2 tagged commit hygiene | PASS for graph ship set (frozen + sealed commits) |
| G3 validate/explain side-effect free | PASS |
| G4 completion-driven acceptance | PASS (existing suite) |
| G5 resource locks | PASS (existing suite) |
| G6 cross-workspace binding | PASS (existing suite) |
| G7 unresolved no auto-retry | PASS (existing suite) |
| G8 security boundary unchanged | PASS (no boundary edits) |
| G9 CLI_DESIGN preserved | PASS (no design redesign) |
| G10 verification refreshed | PASS (this addendum) |

### Still out of graph scope / product-wide
- Full-suite TUI width failures (3) remain a **product** P0, not graph-scheduler logic.
- Remote CI execution requires GitHub remote access (previously unavailable from this machine).
- P2 backlog unchanged: typed compilers, distributed workers, conditional DSL.
