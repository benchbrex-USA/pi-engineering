# Pi Engineering Platform

[![CLI qualification](https://github.com/benchbrex-USA/pi-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/benchbrex-USA/pi-engineering/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

A terminal-native platform for governed AI engineering — built for developers,
security engineers, and technical leaders.

Pi keeps proposals, authority, execution, and verification separate. Models
propose. Operators approve. MCP tools and workspace checks run under exact
allowlists. The UI stays in your terminal scrollback (Specify-style), not a
browser dashboard.

## Who it is for

| Persona | Start with | Workflow |
| --- | --- | --- |
| Developer | `pi-engineering profile apply developer` | `workflows/implement-review.json` |
| Hacker / security | `pi-engineering profile apply hacker` | `workflows/security-pass.json` |
| CTO / eng leader | `pi-engineering profile apply cto` | `workflows/release-gate.json` |

Profiles **merge** into your workspace. Existing MCP servers and agents are
preserved unless you pass `--replace-agents`.

## Open brain

Attach any powerful model — Grok, Codex, Ollama, or any OpenAI-compatible endpoint.
Pi does not gate model IDs. Approvals and tool allowlists stay under your control.

```sh
pi-engineering brain set grok-4.6 --provider grok
pi-engineering brain set YOUR_MODEL --provider compat --endpoint https://HOST/v1 --token-env KEY_ENV
```

## Quick start

```sh
cd Pi_Engineering_CLI
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/pi-engineering --workspace /path/to/project setup
.venv/bin/pi-engineering model set grok-4.6 --provider grok
.venv/bin/pi-engineering profile apply developer
.venv/bin/pi-engineering doctor
.venv/bin/pi-engineering
```

Auth for Grok: `grok login` **or** `export XAI_API_KEY=...`.
Codex and Ollama remain fully supported.

## Core capabilities

- Graph workflows with completion-driven scheduling and resource locks
- MCP stdio + HTTP tools with schema pins and qualification contracts
- Exact-hash approvals, receipts, traces, encrypted backup/restore
- Persona presets and shareable recipes (`profile`, `recipe export`)
- Knowledge/memory retrieval with citations
- Deterministic system-graph analysis (`system validate/inspect/check/trace/impact/sample`)

## Runtime model

Pi separates proposal, authority, execution, and verification. The runtime maps
each responsibility to a concrete module and guarantee:

| Responsibility | Where | Guarantee |
| --- | --- | --- |
| Contract | `pi_workspace` settings, `pi_workflow.Workflow` | Strict schemas, exact allowlists; agent DAGs of 1–32 nodes with cycles rejected |
| Context | `Engine.walk` (`pi_engine.py`) | Bounded context; tool results are untrusted evidence, never instructions |
| Node graph | `Engine.GRAPH` + `checkpoint()` | Explicit transition table; illegal transitions are refused, never silently taken |
| Loop | `Engine.walk` | Step, deadline and context budgets; identical no-progress calls are dropped, not looped |
| Evidence | `workspace.record`, call receipts | SQLite events; action/result hashes with an explicit verification scope |
| Verification | `completion_status`, file readback | Registered checks must pass; a remote response is not business verification |

Workflow-level scheduling (`run_workflow`) composes these: per-node task
records with workflow bindings, resource locks, config-change guards, and
completion only when every node's evidence supports it.

## Design rules (unchanged)

See `Pi_Engineering_CLI/CLI_DESIGN.md` and `SECURITY.md`. No browser product UI.
No deletion of the archived teaching companion or legacy modules.

## Layout

- `Pi_Engineering_CLI/` — product platform (`pi-engineering`)
- `Pi_Engineering_Companion/` — offline teaching lab
- `benchmarks/` — evaluation reports and harness assets

## Contributing

Read [`Pi_Engineering_CLI/AGENTS.md`](Pi_Engineering_CLI/AGENTS.md) first — it
holds the non-negotiables (additive builds, frozen terminal UI contracts,
preserved authority model), the test commands, and the release-hygiene
checklist. Every push runs the full qualification matrix (Ubuntu/macOS ×
Python 3.11/3.12: unit suite, wheel build, installed-package smoke test,
bandit, pip-audit) — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
