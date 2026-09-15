# Graph Engineering Specifications — Pi Platform

**Document type:** Graph subsystem production specification + implementation prompt pack  
**Product:** `pi-engineering` workflow / DAG scheduler (`pi_workflow.py` + Engine bindings)  
**Audience:** Graph engineers, platform owners, coding agents executing production work  
**Baseline:** local `Pi_Engineering_CLI` on `feat/platform-0.6-presets` (2026-09-15)  
**Related:** `GRAPH_UPGRADE.md`, `GRAPH_VERIFICATION.md`, `docs/PRODUCTION_ENGINEERING_SPEC.md`, `CLI_DESIGN.md`, `SECURITY.md`

---

## 0. Non-negotiables (carry into every prompt)

1. **Do not delete** existing code (legacy modules, companion, prior workflow v1 paths).
2. **Do not change** terminal UI/UX/design language (`CLI_DESIGN.md`). Offline `--validate`/`--explain` rendering may only fix contract bugs (width/overflow), not redesign.
3. Graph work is **additive** on the completion-driven scheduler already selected in `GRAPH_UPGRADE.md`.
4. Models remain non-authoritative: workflow nodes launch Engine tasks; **approvals/allowlists/verification** stay operator-controlled.
5. Pi stays **brain-open**: graphs must not hardcode a single vendor model; node agents use workspace/agent model settings.
6. Honesty: do not claim distributed exactly-once, OS sandboxing, or multi-tenant isolation.

---

## 1. Purpose of the graph subsystem

The graph is Pi’s **multi-agent orchestration brain-stem**: a validated, finite DAG of agent tasks with:

- Completion-driven admission (not wave barriers)
- Optional v2 priority + exclusive resource names
- Offline validation and blocker explanation
- Durable flow checkpoints bound to workspace + plan revision
- Strict separation from MCP (transport) and from model inference (proposal only)

It is how developers, hackers, and CTOs compose powerful runs **without** a browser dashboard.

---

## 2. As-built architecture (minute detail)

### 2.1 Objects

| Object | Definition | Limits (current) |
| --- | --- | --- |
| `Workflow` | `version` 1\|2, `nodes` map, `concurrency` | 1–32 nodes; concurrency 1–8 |
| `Node` | `agent`, `task`, `depends_on`, `priority`, `resources` | task ≤24k chars; ≤16 resources; priority −100…100 |
| Flow id | `flow_` + fingerprint(path, plan identity) | path-resolved; v1 identity ignores priority/resources |
| Flow body | SQLite `workflows(id, body)` | symlink-rejected; WAL-aware recovery checks |
| Binding | `schema_version`, `workspace_hash`, `revision`, per-task `workflow_binding` | mismatch ⇒ refuse reuse |

### 2.2 Runtime algorithm (normative)

1. `load_plan` — unique JSON keys, Pydantic validate, agent enabled checks, cycle reject via `TopologicalSorter`.
2. Acquire flow lock.
3. Read/create flow; `check_binding` when resuming.
4. Admission loop:
   - Consider nodes whose dependencies are **all `completed`**
   - Exclude failed/rejected/unresolved/budget_exhausted ancestors from releasing dependents (all-success joins)
   - Respect `concurrency`
   - Order ready nodes by **priority desc**, then **name asc**
   - Acquire declared resource locks (task-level OS locks shared with manual resume)
   - Start/resume Engine task with `workflow_resources` + `workflow_binding`
5. Use completion-driven waiting (`FIRST_COMPLETED` style) so unrelated slow/blocked peers do not stall ready descendants.
6. Persist flow after state changes; expose `--explain` offline without Engine.advance.

### 2.3 Engine coupling points (`pi_engine.py`)

- Per-task state machine `GRAPH`: intake→context→propose→policy→review/execute→verify→complete|unresolved|rejected
- `workflow_binding.workspace_hash` must match current workspace
- `workflow_resources` taken under `workspace.lock("resource_" + fingerprint(resource))`
- `ResourceBusy` surfaces as bounded admission error (`resource_busy`), not infinite spin
- Unknown post-dispatch interruption ⇒ `unresolved`, **replay blocked**

### 2.4 CLI surface (stable)

```
pi-engineering workflow FILE                 # run/resume
pi-engineering workflow FILE --validate      # offline, no tasks/inference
pi-engineering workflow FILE --explain       # offline blockers from checkpoint
pi-engineering workflow FILE --json|--plain
```

Packed workflows (platform): `workflows/review.json`, `implement-review.json`, `security-pass.json`, `release-gate.json`.

### 2.5 Verification snapshot (this audit)

- `tests.test_graph_scheduler`: **21/21 PASS** (2026-09-15)
- Full suite still has **3 unrelated TUI width failures** (must not be ignored at product release, but graph suite itself is green)
- Hygiene risk: `pi_workflow.py` / `pi_engine.py` dirty vs git; `pi_live.py` + graph tests historically untracked — **release freeze required**

---

## 3. Production gaps specific to graph engineering

### P0 — Must fix before calling graph “production”
1. **Source-of-truth freeze:** commit the exact `pi_workflow.py`, `pi_engine.py`, graph tests, and GRAPH_* docs that the 21 tests exercise.
2. **Distribution:** ensure wheel install includes workflow JSON packs + modules importing `pi_live` for workflow display.
3. **Contract tests in CI:** graph scheduler suite mandatory on macOS + Linux.
4. **No-payload leakage:** keep guarantees that validate/explain/errors never dump task prompts/secrets (tests already cover — keep forever).

### P1 — Robustness upgrades (still single-process)
5. **Admission observability:** durable events for admit/wait/resource_busy/cancel with stable reason codes (for CTO metrics).
6. **Partial failure UX:** `--explain` machine schema versioning (`inspection_schema: 1`) for tools integrating JSON.
7. **Budget propagation:** document/test how node agent `max_steps`/`deadline` interact with workflow wall time (no silent infinite).
8. **Idempotent resume matrix:** table-driven tests for every terminal status × dependency edge.
9. **Resource taxonomy guide:** recommended namespaces (`repo:`, `net:`, `account:`) — names are not permissions; docs must say so.
10. **Workflow lint command:** static checks beyond schema (unreachable nodes, redundant edges, agent tool capability hints) — advisory, non-breaking.

### P2 — Power features (backlog; do not fake as done)
11. Typed node output contracts / goal→graph compiler
12. Conditional branch predicates & bounded loops
13. Versioned replan with descendant invalidation + fresh approvals
14. Nested sub-workflows
15. Distributed workers/leases
16. Effect compensation / sagas
17. Quorum/any-joins (explicitly rejected for v1 all-success model)

### P3 — Evaluation
18. Keep `tests/benchmark_workflow.py` as **synthetic scheduler** timing only; never as model IQ claim.
19. Persona workflow packs must be validated in CI (`load_plan` on all `workflows/*.json`).

---

## 4. Graph production definition of done (v1 graph)

Graph subsystem is production-ready when:

| # | Criterion |
| --- | --- |
| G1 | All `test_graph_scheduler` + workflow pack validation + distribution checks green in CI |
| G2 | Tagged commit contains workflow runtime + tests + docs bit-identical to CI |
| G3 | `--validate` / `--explain` proven side-effect free (no DB writes, no model, no MCP) |
| G4 | Completion-driven acceptance tests from GRAPH_UPGRADE still pass |
| G5 | Resource locks work cross-process; partial acquisition releases |
| G6 | Binding refuses cross-workspace approval/resume |
| G7 | Unresolved effects never auto-retry |
| G8 | SECURITY boundary text unchanged: resources ≠ authz; single-user local |
| G9 | CLI_DESIGN preserved for workflow status rendering |
| G10 | GRAPH_VERIFICATION.md updated with fresh date/evidence for the tagged code |

---

## 5. Worked threat model (graph-specific)

| Threat | Mitigation |
| --- | --- |
| Malicious workflow JSON (cycles, huge fanout) | size cap, node cap, cycle detect, unique keys |
| Prompt injection via node `task` text | untrusted content; tools still allowlisted; approvals on writes |
| Checkpoint swap / symlink DB | symlink reject; binding hashes |
| Cross-workspace approval replay | workspace_hash + binding checks |
| Resource name spoofing as permission | docs + non-interpretation as authz |
| Explain leaking payloads | redaction tests |
| Scheduler starvation | finite DAG + priority/name ordering |

---

## 6. File ownership map

| Path | Owner concern |
| --- | --- |
| `pi_workflow.py` | Scheduler + schema + inspect |
| `pi_engine.py` | Task graph + resource locks + binding |
| `pi_workspace.py` | locks, SQLite, ResourceBusy |
| `pi_app.py` | `workflow` command wiring |
| `pi_live.py` / `pi_terminal.py` | status rendering only |
| `workflows/*.json` | Product packs |
| `tests/test_graph_scheduler.py` | Normative acceptance |
| `tests/benchmark_workflow.py` | Synthetic timing harness |
| `GRAPH_UPGRADE.md` / `GRAPH_VERIFICATION.md` | Design + evidence |

---

## 7. Master prompt — Graph Engineering Specifications (copy/paste)

Use this as the **primary assignment prompt** for a graph production engineer or coding agent:

```
# ROLE
You are the Graph Engineer for Pi Engineering CLI — a terminal-native, single-user agent platform.
Your job is to make the workflow/DAG subsystem fully production-ready without redesigning the product.

# NON-NEGOTIABLES
- Do NOT delete existing code (including legacy/companion).
- Do NOT change terminal UI/UX/design language (CLI_DESIGN.md). Fix overflow/contract bugs only if required for workflow rendering.
- Preserve authority: models propose; operators approve; Pi dispatches/verifies.
- Preserve brain-open posture: workflows must not hardcode a vendor model.
- Keep all-success joins; do NOT add any/quorum joins or distributed workers in v1.
- Be evidence-driven: commands, tests, file paths; no marketing multipliers.

# READ FIRST (in order)
1. Pi_Engineering_CLI/docs/GRAPH_ENGINEERING_SPEC.md  (this spec)
2. GRAPH_UPGRADE.md
3. GRAPH_VERIFICATION.md
4. docs/PRODUCTION_ENGINEERING_SPEC.md (graph sections + hygiene)
5. SECURITY.md + BUILD_CONTRACT.md
6. pi_workflow.py, pi_engine.py (workflow_* + resource locks), tests/test_graph_scheduler.py

# OBJECTIVE
Deliver a production-sealed graph subsystem that meets Definition of Done G1–G10 in
docs/GRAPH_ENGINEERING_SPEC.md §4.

# MANDATORY EXECUTION PLAN
## Phase 0 — Reality check
- Run: `.venv/bin/python -m unittest tests.test_graph_scheduler -v`
- Run pack validation: load every workflows/*.json via load_plan in a temp workspace
- Report git hygiene: is pi_workflow/pi_engine/tests tracked? dirty diff summary?
- List any mismatches between GRAPH_VERIFICATION.md claims and current code.

## Phase 1 — Freeze the truth
- Make the runnable graph code and its tests/docs match git (commit-ready tree).
- Do not “clean” by deleting legacy modules.
- Ensure pyproject packages all modules needed for `pi-engineering workflow`.

## Phase 2 — Close P0 graph gaps
- CI-ready: graph tests must be deterministic, no network.
- Confirm --validate/--explain perform zero model/tool/task creation (add assertion tests if missing).
- Confirm unresolved/unknown dispatch cannot be auto-retried.
- Confirm cross-workspace binding refusal on approve/resume paths.

## Phase 3 — P1 robustness (if Phase 2 green)
Implement only items that stay single-process and UI-neutral, prioritized:
1) versioned inspection JSON (`inspection_schema`)
2) richer durable admit/resource_busy reasons already user-safe
3) table-driven resume matrix tests for terminal statuses
4) CI job running graph suite on linux+macos
Skip typed compilers, distributed leases, conditional DSL — those are P2 backlog.

## Phase 4 — Evidence pack
Update GRAPH_VERIFICATION.md with:
- date, commit/tag, platform, python
- commands reproduced
- pass/fail table for G1–G10
- explicit remaining backlog (P2 list)
Do NOT claim independent pen-test or customer qualification from graph tests alone.

# SUCCESS CRITERIA
- test_graph_scheduler 100% pass
- workflow packs validate
- hygiene: release paths tracked
- GRAPH_VERIFICATION.md refreshed honestly
- no UI redesign; no deletions; no new authority bypasses

# DELIVERABLES
1. Code/tests/docs changes on a branch
2. Short GRAPH_RELEASE_NOTES.md (what changed, what didn’t)
3. Exact commands a reviewer can re-run

# STOP CONDITIONS
Stop and report if asked to redesign TUI, add cloud multi-tenant orchestration, or weaken approval/binding checks.
```

---

## 8. Satellite prompts (graph-only)

### 8.1 Freeze & hygiene
```
Commit/track the graph runtime actually covered by tests/test_graph_scheduler.py
(pi_workflow.py, pi_engine workflow bindings, graph tests, GRAPH_*.md, workflows/*.json).
Do not delete legacy. Produce a file manifest of the graph ship set.
```

### 8.2 Side-effect proof
```
Add/extend tests proving `workflow --validate` and `--explain` create no tasks,
call no models/MCP, and write no SQLite rows. Fail the build if violated.
```

### 8.3 Resume matrix
```
Build a table-driven test matrix: for each dependency parent status in
{completed, awaiting_approval, unresolved, failed, rejected, budget_exhausted, interrupted},
assert child readiness and join behavior matches GRAPH_UPGRADE acceptance.
```

### 8.4 Pack CI
```
CI target: validate all workflows/*.json and presets’ default_workflow paths exist;
run unittest tests.test_graph_scheduler on ubuntu + macos, Python 3.11+.
```

### 8.5 Persona graphs
```
Without changing TUI, ensure developer/hacker/cto default workflows remain valid
against default agents after profile apply. Add tests.
```

---

## 9. Operator quick reference

```bash
cd Pi_Engineering_CLI
.venv/bin/python -m unittest tests.test_graph_scheduler -v
.venv/bin/pi-engineering workflow workflows/implement-review.json --validate --json
.venv/bin/pi-engineering workflow workflows/security-pass.json --explain --plain
.venv/bin/python tests/benchmark_workflow.py   # synthetic only
```

---

## 10. Revision history

| Date | Note |
| --- | --- |
| 2026-09-15 | Initial Graph Engineering Specifications + master prompt from full-system audit |

