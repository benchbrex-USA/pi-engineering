# Pi Engineering Platform — Production Engineering Specification

**Document status:** Draft for execution  
**Product:** `pi-engineering` (Pi Engineering CLI / platform)  
**Baseline analyzed:** local tree on branch `feat/platform-0.6-presets` (commits through `ac4023d`), 2026-09-15  
**Non-negotiables (product owner):**
1. Do **not** delete existing code (including `pi_legacy.py`, companion lab, archived teaching UI).
2. Do **not** change terminal UI/UX/design contracts (`CLI_DESIGN.md` remains authoritative).
3. Build on the existing foundation; additive evolution only.
4. Pi is an **open advanced agent**: performance scales with the connected model (“brain”); model IDs/endpoints are not artificially gated.
5. Authority model remains: **models propose → operators approve → Pi dispatches/verifies**.

---

## 1. Executive summary

Pi is already a serious single-user local agent platform: graph workflows, MCP governance, exact-hash approvals, SQLite durability, knowledge/memory, personas, and open-brain providers (Grok/OpenAI-compat/Codex/Ollama). It is **not yet production-ready** as a shippable product for “everyone” (hackers, CTOs, developers) because:

| Area | State |
| --- | --- |
| Core engine + MCP + approvals | Strong local foundation |
| Graph scheduler (completion-driven) | Implemented + tested, but **source still partially untracked / dirty vs release packaging** |
| Terminal design contract | Defined; **3 width/overflow tests currently FAIL** |
| Open brain | Landed (0.6 brain commands + high ceilings) |
| Personas / workflows / recipes | Landed |
| Schema isolation bug (OpsGraph 0/100 root cause) | Fixed + regression test |
| External qualification / pen-test / customer account | **Open gates** (`VERIFICATION.md`: PASS WITH EXTERNAL GATES) |
| OS sandbox / multi-tenant hosting | Explicitly **out of current security boundary** |
| Distribution (GitHub remote, signed release, CI) | Incomplete (remote push previously failed; no remote CI evidence) |
| Benchmarks | OpsGraph v1 scored 0/100 historically (environment-confounded); harness still separate |

**Production-ready** for this product means: a reproducible, supportable **local single-user** release that meets BUILD_CONTRACT + SECURITY + CLI_DESIGN, with green CI, clean packaging, fixed terminal regressions, documented brain/persona ops, and completed external gates — **without** pretending to be a hosted multi-tenant SaaS.

---

## 2. System map (as-built)

### 2.1 Runtime architecture

```
Operator / TUI (pi_terminal + pi_prompt + pi_live)
        │
        ▼
   pi_app (CLI commands)
        │
        ├─ Engine (pi_engine) ──► Model adapters (pi_models)
        │         │                    ollama | codex | grok | openai | compat
        │         ▼
        │   ToolBroker (pi_tools) ── local tools + MCP sessions
        │         │
        │         ▼
        │   Approvals / receipts / checkpoints (pi_workspace SQLite)
        │
        ├─ Workflow scheduler (pi_workflow) — DAG, resources, validate/explain
        ├─ Knowledge / memory (pi_knowledge)
        ├─ Qualification (pi_qualification)
        ├─ Profiles / recipes (pi_profile + presets/)
        └─ Backup / metrics (pi_operations)
```

### 2.2 Module inventory (~6k LOC `pi_*.py`)

| Module | Role | Ship? |
| --- | --- | --- |
| `pi_app.py` | CLI entry, doctor, brain/profile/recipe | Yes (packaged) |
| `pi_workspace.py` | Config, SQLite, locks, VERSION | Yes |
| `pi_engine.py` | Bounded agent loop | Yes (dirty local upgrades present) |
| `pi_tools.py` | Tools, MCP broker, schema isolation fix | Yes |
| `pi_models.py` | Codex / Ollama / OpenAI-compat / Grok | Yes |
| `pi_workflow.py` | Graph scheduler | Yes (large dirty upgrade vs HEAD packaging) |
| `pi_terminal.py` / `pi_live.py` / `pi_prompt.py` | TUI surfaces | Yes (`pi_live` often untracked in git status) |
| `pi_knowledge.py` / `pi_operations.py` / `pi_qualification.py` / `pi_server.py` | Platform services | Yes |
| `pi_profile.py` + `presets/` + `workflows/` | Personas & packs | Yes |
| `pi_legacy.py` / `pi_core.py` / `pi_ui.py` | Archived / teaching | Keep on disk; **not** product entry |
| Companion (`Pi_Engineering_Companion/`) | Offline lab | Keep; separate artifact |
| `benchmarks/` | Eval harness & reports | Keep; not runtime dependency |

### 2.3 Public CLI surface (must remain stable)

`setup, init, launch, home, doctor, runs, agents, tools, graph, mcp-server, model, brain, agent, mcp, run, call, show, trace, receipt, resume, reject, approve, reconcile, workflow, knowledge, memory, backup, restore, metrics, workspace, check, profile, recipe`

Global flags: `--workspace`, `--json`, `--plain`, `--no-animate`, `--version`.

### 2.4 Authority & trust boundary (immutable for v1 production)

From `SECURITY.md` / `BUILD_CONTRACT.md`:

- Single local OS user trust domain (not multi-tenant isolation).
- Exact tool allowlists; remote MCP annotations do **not** grant read authority.
- Writes require exact-hash operator approval; MCP cannot self-approve.
- Checkpoints before dispatch; unknown remote outcomes do not auto-retry.
- Hosted models transmit only authorized task/tool observations.
- No OS process sandbox claim; registered checks/MCP run as the user.

---

## 3. Audit findings (minute detail)

### 3.1 Correctness / quality gates **red now**

Full `unittest discover` on 2026-09-15: **95 tests, 3 failures** (all terminal width/overflow):

1. `test_product.ProductTests.test_terminal_wrap_and_injection`
2. `test_qualification.QualificationTests.test_qualification_and_schema_render_without_color_or_overflow`
3. `test_terminal_experience.TerminalExperienceTests.test_live_projection_parallel_states_and_widths`

**Production blocker:** CLI_DESIGN requires verified behavior at 32/40/80/120/180 columns. These failures mean the TUI contract is currently violated under test.

### 3.2 Packaging / source-of-truth drift

- Declared version **0.6.0** (`pyproject.toml`, `VERSION`).
- Graph upgrade docs claim 0.5.0 verification “PASS WITH GAPS”.
- Working tree still shows **untracked**: `pi_live.py`, graph tests, GRAPH_*.md, benchmarks/, etc.
- **Dirty** vs last commit: `pi_engine.py`, `pi_terminal.py`, `pi_workflow.py` (substantial workflow delta ~323 lines).
- Risk: “what runs locally” ≠ “what is committed/releasable”.

**Production blocker:** freeze a release commit that includes all runtime modules + tests actually used.

### 3.3 Known historical product defect (fixed in tree, must stay)

OpsGraph benchmark 0/100 root cause: shared `{"type":"string"}` schema dict mutated when registering checks → `workspace_read`/`workspace_write` rejected normal paths. Fixed via per-field string schemas + `tests/test_schema_isolation.py`. **Must remain in release regression suite forever.**

Secondary benchmark issues (harness): nested `sandbox-exec` exit 71; Playwright readiness timeout — track under Eval Harness, not as silent Pi “model failure”.

### 3.4 External / organizational gates still open (`VERIFICATION.md`)

Must complete for any claim of production/customer readiness:

1. Independent security assessment (not self-Bandit).
2. Representative-user UX acceptance (developers, hackers, CTO personas).
3. Private customer-account MCP qualification (positive + negative authz).
4. Remote CI on macOS + Linux (Python 3.11/3.12 at minimum).
5. Signed/reproducible release artifacts + install verification on clean machines.
6. Support/incident runbook rehearsal (compromise steps already sketched in SECURITY.md).

### 3.5 Capability backlog (explicit non-features today)

From GRAPH_UPGRADE / VERIFICATION — do not market as done:

- Typed goal→graph compilation & output schema bindings
- Branch predicates / bounded loops / subgraphs
- Versioned replanning with descendant invalidation
- Distributed workers / leases / exactly-once remote effects
- OS sandboxing of checks/MCP
- Hosted multi-tenant SaaS control plane
- Guaranteed cancellation of remote side effects

### 3.6 Open-brain posture (desired product DNA)

Already started; production must preserve:

- `brain set|show|open` and providers `grok|openai|compat|codex|ollama`
- No model-id allowlist
- High operator-configurable ceilings (steps/deadline/context/output/timeout)
- Clear messaging: **stronger brain ⇒ stronger Pi**, authority unchanged

### 3.7 Persona platform layer

Presets `developer|hacker|cto` + workflows `implement-review|security-pass|release-gate|review` + `recipe export`. Production needs: pack hashing, versioned preset schema, conflict policy docs, and sample projects per persona.

---

## 4. Production definition of done (v1.0.0 local platform)

A release may be called **production-ready v1.0.0** only when **all** are true:

### P0 — Ship blockers
1. All unit/integration tests green on macOS arm64 and Linux x86_64/arm64 (incl. 32–180 column TUI tests).
2. Single tagged git commit contains every runtime module used by `pi-engineering` (no “untracked but imported” files).
3. `pip install` from sdist/wheel on a clean venv; `check_distribution.py` PASS.
4. Schema isolation + recovery + approval replay + MCP stdio/http fixtures PASS.
5. `brain` + `profile` + `workflow --validate/--explain` documented and smoke-tested.
6. SECURITY.md boundary statement reviewed and unchanged in meaning.
7. CLI_DESIGN.md visual/behavior contract verified (fixtures/SVG or automated width tests).
8. Changelog + migration notes from 0.5/0.6 → 1.0.

### P1 — Hardening before wide distribution
9. GitHub Actions (or equivalent) CI matrix green; branch protection.
10. SBOM + pip-audit + bandit in CI; signed artifacts (at least checksums + provenance).
11. Installer path documented for Homebrew/npm-adjacent optional wrappers **without** replacing Python package as SoT.
12. Telemetry **off by default**; if any added later, explicit opt-in only (currently prefer none).
13. Support matrix: Python 3.11–3.13, macOS 13+, popular Linux distros.
14. Persona UX sessions completed; findings filed; no design redesign—only additive command ergonomics if needed.

### P2 — Trust & market readiness
15. Independent pen-test / security review letter.
16. At least one private customer MCP qualification pack (redacted template published).
17. Public evaluation protocol (OpsGraph or successor) re-run on fixed Pi with environment confounds documented; no inflated marketing claims.
18. Course/companion alignment: companion remains teaching; product README never confuses them.

---

## 5. Workstreams & detailed requirements

### WS0 — Release freeze & repository hygiene
- Commit/track: `pi_live.py`, graph tests, GRAPH docs, workflows/presets already intended for ship.
- Reconcile dirty `pi_workflow.py` / `pi_engine.py` / `pi_terminal.py` with tests; no silent behavior drift.
- Ensure `py-modules` and package-data include presets/workflows.
- Pin lockfile; regenerate audit reports dated for the release.
- Establish remote (`origin`) access; tags `v1.0.0`.

### WS1 — Terminal contract repair (P0)
- Fix overflow failures without changing design language (badges, rules, colors, scrollback model).
- Re-verify 32/40/80/120/180 columns, plain/NO_COLOR, injection sanitization.
- Keep Rich markup never evaluating untrusted text.

### WS2 — Engine/workflow productionization
- Stabilize completion-driven scheduler as the sole workflow runtime.
- Document resource lock semantics and failure modes.
- Guarantee `--validate` / `--explain` never call models/tools.
- Add migration tests for legacy workflow records.

### WS3 — Brain openness & reliability
- Keep `compat` provider fully open (any HTTPS/loopback OpenAI-compatible base URL).
- Harden auth resolution order: explicit `--token-env` → env vars → `~/.grok/auth.json` key (document precisely; never log secrets).
- Model timeout/cancellation: kill hung HTTP/Codex subprocesses; surface actionable errors.
- Optional: per-agent model override already in schema — expose cleanly in CLI (`agent set --model/--provider`) end-to-end tests.
- Cost/spend: no automatic cloud spend amplifiers; budgets remain operator-set.

### WS4 — Tools, checks, MCP
- Preserve schema isolation invariant with adversarial tests (shared-object mutation attempts).
- Checks: document that Pi does not OS-sandbox check processes; recommend least privilege.
- MCP: qualify templates for common servers; schema pin UX; pagination/cursor abuse tests already present—keep.
- Add regression for “checks registered ⇒ file tools still accept paths/`missing`”.

### WS5 — Personas, packs, recipes
- Version preset schema (`version: 1`).
- `profile apply` policies: default merge; `--replace-agents` explicit.
- Pack format for community packs (local directory first; no forced marketplace).
- Recipe import (additive) matching export, rejecting secrets.

### WS6 — Security & compliance
- Re-run bandit/pip-audit in CI; fail on new highs.
- Threat model doc one-pager for hackers/CTOs/devs (same boundary, different examples).
- Backup/restore drill scripted.
- Explicit “not a sandbox” warnings in doctor when checks/MCP configured.

### WS7 — Evaluation & benchmarks
- Separate **product** claims from **harness** failures.
- Rebuild OpsGraph (or successor) runner against fixed schemas; publish methodology.
- Forbid marketing multipliers without comparative protocol.

### WS8 — Docs & DX
- Root README platform story (audiences + brain-first) — keep accurate.
- Manpages or `pi-engineering help TOPIC` optional later; for v1, README + `/help` sufficient if complete.
- AGENTS.md for contributors (graph docs noted absence historically).

### WS9 — Distribution
- Wheel + sdist; optional `install.sh` remains recognized-symlink only.
- Smoke: `pi-engineering doctor` on clean machine with Grok login **or** API key.
- Windows: defer or experimental; do not block macOS/Linux v1 unless owner prioritizes.

---

## 6. Risks register

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| R1 | TUI width regressions ship | UX trust loss | P0 test gate |
| R2 | Untracked runtime files | Broken installs | Release freeze checklist |
| R3 | Hosted model data exfil via over-granted tools | Security incident | Allowlists + docs + qualify |
| R4 | Marketing overclaim on benchmarks | Credibility | Eval protocol + VERIFICATION honesty |
| R5 | Raising budgets ⇒ runaway agent loops | Operator cost/surprise | brain show budgets; confirmations optional later |
| R6 | Dirty workflow code diverges from verified 0.5 graph | Latent scheduler bugs | Re-run graph suite before tag |
| R7 | Git remote inaccessible | No upstream distribution | Fix SCM access before public launch |

---

## 7. Suggested release train

| Milestone | Exit criteria |
| --- | --- |
| **M0 Audit pack** (this doc) | Spec + prompts approved by owner |
| **M1 Green tree** | Tests 100% green; hygiene commit |
| **M2 v0.9 RC** | Wheel install + doctor + brain + profile smoke |
| **M3 External gates** | CI + security review + UX sessions |
| **M4 v1.0.0** | Tag, notes, eval report, support matrix |

---

## 8. Out of scope for v1 (explicit)

- Hosted multi-tenant Pi cloud
- Redesigning terminal visual language
- Deleting legacy/companion
- Claiming OS isolation
- Automatic unpaid model upgrades or hidden cloud calls

---

## 9. Traceability

| Requirement source | Consumed in |
| --- | --- |
| CLI_DESIGN.md | WS1 |
| BUILD_CONTRACT.md | DoD, WS2–WS4 |
| SECURITY.md | WS6, boundary |
| GRAPH_UPGRADE/VERIFICATION | WS2, WS7 |
| Owner brain-first mandate | WS3 |
| Owner persona platform mandate | WS5 |
| OpsGraph 0/100 postmortem | WS4 regression + WS7 |

---

*End of specification body. Implementation prompts are in `docs/ENGINEERING_PROMPTS.md`.*
