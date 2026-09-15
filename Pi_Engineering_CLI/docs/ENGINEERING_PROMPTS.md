# Pi Engineering — Engineering Prompts (Production Build Pack)

Use these prompts with coding agents **or** human engineers.  
**Global constraints for every prompt:**

- Do **not** delete existing code (`pi_legacy.py`, companion, archived UI modules).
- Do **not** change terminal UI/UX/design language (`CLI_DESIGN.md`).
- Prefer additive fixes; preserve authority model (propose → approve → execute → verify).
- Keep Pi brain-open: no model-id allowlists; `compat` endpoints remain usable.
- Add/extend tests; do not weaken regressions (especially schema isolation).
- Report evidence (commands, results); no marketing claims.

---

## Prompt A — Repository hygiene & release freeze

```
You are productionizing Pi Engineering CLI.

Goal: Make the git tree match the runnable product.

Tasks:
1. Inventory imports used by pi_app/pi_engine/pi_workflow/pi_terminal and ensure every runtime module is tracked.
2. Commit or intentionally exclude with rationale: pi_live.py, graph tests, GRAPH_*.md, benchmarks/.
3. Reconcile dirty pi_workflow.py / pi_engine.py / pi_terminal.py with tests/test_graph_scheduler.py and terminal suites.
4. Ensure pyproject py-modules + package-data include presets/*.json and workflows/*.json.
5. Run: python -m unittest discover -s tests -v
6. Run distribution check script if present.
7. Produce a RELEASE_TREE.md listing files that ship in the wheel.

Constraints: no UI redesign; no deletions of legacy modules.
Success: clean status for release paths; tests green or only documented waived P2 items.
```

---

## Prompt B — Fix terminal width/overflow contract (P0)

```
Pi has 3 failing tests about terminal line width / overflow:
- test_product.ProductTests.test_terminal_wrap_and_injection
- test_qualification.QualificationTests.test_qualification_and_schema_render_without_color_or_overflow
- test_terminal_experience.TerminalExperienceTests.test_live_projection_parallel_states_and_widths

Goal: Make them pass without changing the visual design language (colors, badges, scrollback, header rules).

Investigate pi_terminal.py, pi_live.py, and render helpers. Fix wrapping/truncation/sanitization.
Re-verify widths 32,40,80,120,180 and plain/NO_COLOR behavior per CLI_DESIGN.md.

Success: those tests pass; no new failures; no alternate-screen dashboard introduced.
```

---

## Prompt C — Schema isolation forever-regression

```
Historical bug: shared JSON Schema string dict caused workspace_check enums to poison workspace_read/write paths (OpsGraph 0/100).

Confirm pi_tools.local_schemas uses fresh dicts per field.
Extend tests beyond test_schema_isolation.py:
- ToolBroker with registered checks validates AGENTS.md read and missing-hash write.
- Knowledge/memory query fields also unpoisoned.

Do not remove check enums; fix sharing only.
Success: adversarial tests pass.
```

---

## Prompt D — Open brain production hardening

```
Pi must remain an open advanced agent: performance scales with the connected brain.

Hardening tasks:
1. Document and test auth precedence for OpenAICompatModel (token_env, XAI_API_KEY/OPENAI_API_KEY, ~/.grok/auth.json nested `key`).
2. Ensure provider `compat` accepts arbitrary HTTPS/loopback OpenAI-compatible base URLs and arbitrary model ids.
3. Cancellation/timeouts: hung HTTP and Codex subprocesses terminate cleanly.
4. `brain show/set/open` remain accurate vs ModelSettings ceilings.
5. Expose per-agent model overrides via CLI with tests if schema already supports AgentSettings.model.
6. Never log secrets.

UI must stay the same. Success: tests + manual smoke with grok-4.6 and a fake compat endpoint fixture.
```

---

## Prompt E — Workflow scheduler production seal

```
Seal completion-driven graph scheduling for v1.

Requirements from GRAPH_UPGRADE.md acceptance:
- Independent branch completion releases dependents without waiting on unrelated blocked peers; all-joins still require all success.
- Resource exclusivity + priority ordering.
- --validate/--explain never create tasks or call models/tools.
- Resume binding rejects stale workspace/schema/revision.

Re-run tests/test_graph_scheduler.py and tests/benchmark_workflow.py; update GRAPH_VERIFICATION.md date/evidence if still accurate.
Do not add distributed workers.
Success: suite green; verification doc matches code.
```

---

## Prompt F — Persona packs & recipe import

```
Productionize presets developer/hacker/cto and workflows.

Add preset schema version field; validate on load.
Implement recipe import (inverse of export) that:
- merges without deleting servers
- rejects embedded secret values
- is deterministic

Add examples/ docs for each persona without changing TUI.
Success: profile/recipe tests expanded; apply/import roundtrip works.
```

---

## Prompt G — CI & supply chain

```
Add CI (GitHub Actions or owner’s SCM) for Pi Engineering:

Matrix: macos-latest + ubuntu-latest; Python 3.11 and 3.12 (3.13 if feasible).
Jobs: unit tests, pip-audit, bandit on production modules, build wheel/sdist, install wheel in clean venv, run pi-engineering --version && doctor --json (doctor may fail model connectivity—assert structure).

Publish checksums for artifacts. No UI changes.
Success: CI config merged; badge/docs linked from README.
```

---

## Prompt H — Security review pack

```
Prepare an independent review pack without claiming the review is done:

1. Short threat model (single-user local CLI).
2. Data flows to hosted models.
3. Approval/allowlist invariants.
4. Explicit non-claims (no OS sandbox, no multi-tenant).
5. Reproduce commands for bandit/pip-audit/backup-restore.
6. Incident steps from SECURITY.md as a checklist form.

Do not weaken controls. Do not delete code.
Success: docs/SECURITY_REVIEW_PACK.md suitable to hand an external reviewer.
```

---

## Prompt I — Eval harness honesty (OpsGraph successor)

```
Rebuild or repair the OpsGraph benchmark runner to evaluate Pi fairly AFTER schema isolation fix.

Separate:
- Pi product defects
- Harness defects (nested sandbox-exec, Playwright readiness)

Produce a methodology doc and one controlled run report. No performance multiplier marketing.
Keep BeGuardit production tree untouched except isolated solver clones as before.
Success: report with environment confounds explicitly labeled.
```

---

## Prompt J — v1.0.0 release captain

```
You are release captain for pi-engineering v1.0.0 (local single-user production).

Checklist:
- All P0 items in PRODUCTION_ENGINEERING_SPEC.md DoD
- Changelog
- Tag v1.0.0
- Wheel install smoke on clean machine
- README accuracy (brain, profiles, security boundary)
- VERIFICATION.md updated honestly (what is still external)

Refuse to tag if terminal tests fail or runtime files are untracked.
Success: tagged release + release notes + evidence appendix.
```

---

## Prompt K — Meta orchestrator (use first)

```
You are the Pi Platform production orchestrator.

Read:
- Pi_Engineering_CLI/docs/PRODUCTION_ENGINEERING_SPEC.md
- Pi_Engineering_CLI/docs/ENGINEERING_PROMPTS.md
- CLI_DESIGN.md, SECURITY.md, BUILD_CONTRACT.md, VERIFICATION.md

Plan the minimum path to v1.0.0 respecting non-negotiables.
Execute Prompt B first if tests are red, then A, C, E, D, F, G, H, I, J as dependencies allow.
Work in the visible local checkout; do not redesign UI; do not delete legacy.
Keep the owner informed with concrete evidence after each prompt.
```

---

## Operator one-liners (human)

```bash
# Audit now
cd Pi_Engineering_CLI && .venv/bin/python -m unittest discover -s tests -v

# Brain
pi-engineering brain open
pi-engineering brain set grok-4.6 --provider grok
pi-engineering brain show

# Personas
pi-engineering profile list
pi-engineering profile apply developer
pi-engineering workflow workflows/implement-review.json --validate --json
```
