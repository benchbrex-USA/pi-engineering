# Agent Guidelines for Pi Engineering CLI

## Non-Negotiables (from PRODUCTION_ENGINEERING_SPEC.md)

1. **Do not delete existing code** — including `pi_legacy.py`, `Pi_Engineering_Companion/`, archived teaching UI.
2. **Do not change terminal UI/UX/design contracts** — `CLI_DESIGN.md` remains authoritative. Fix overflow/contract bugs only; no redesign.
3. **Build additively** on the existing foundation — no rewrites.
4. **Preserve authority model**: models propose → operators approve → Pi dispatches/verifies.
5. **Preserve brain-open posture**: workflows must not hardcode a vendor model; any Codex/Ollama/Grok/OpenAI-compatible endpoint must work.
6. **Be evidence-driven**: commands, tests, file paths; no marketing multipliers.

## Running Tests

```bash
# Full suite
.venv/bin/python -m unittest discover -s tests -v

# Graph subsystem (critical path)
.venv/bin/python -m unittest tests.test_graph_scheduler tests.test_graph_production tests.test_schema_isolation -v

# Specific width/overflow regression tests
.venv/bin/python -m unittest tests.test_product.ProductTests.test_terminal_wrap_and_injection tests.test_qualification.QualificationTests.test_qualification_and_schema_render_without_color_or_overflow tests.test_terminal_experience.TerminalExperienceTests.test_live_projection_parallel_states_and_widths -v
```

## Release Hygiene

Before any release commit:
- All tests pass on macOS arm64 (local) and Linux x86_64/arm64 (CI)
- Wheel installs cleanly: `pip install dist/pi_engineering-<version>-py3-none-any.whl`
- Installed `pi-engineering --version` matches `pyproject.toml`
- `pi-engineering profile list` shows presets (not empty)
- Bandit clean on all 15 production modules
- pip-audit clean on locked requirements
- `build_release.py` regenerates `Pi_Engineering_CLI.zip` with current FILES list
- SHA256SUMS.txt updated for release artifacts

## Key Architecture Files

| Module | Role | Do Not Touch Without Spec Review |
|--------|------|----------------------------------|
| `pi_app.py` | CLI entry, commands, dispatch | ❌ |
| `pi_workspace.py` | Config, SQLite, locks, VERSION | ❌ |
| `pi_engine.py` | Bounded agent loop, graph state machine | ❌ |
| `pi_tools.py` | Tools, MCP broker, schema isolation | ❌ |
| `pi_models.py` | Model adapters (Codex/Ollama/Grok/OpenAI-compat) | ❌ |
| `pi_workflow.py` | Graph scheduler (completion-driven) | ❌ |
| `pi_terminal.py` / `pi_live.py` / `pi_prompt.py` | TUI surfaces | ❌ (UI only per CLI_DESIGN.md) |
| `pi_knowledge.py` / `pi_operations.py` / `pi_qualification.py` | Platform services | |
| `pi_profile.py` + `presets/` + `workflows/` | Personas & packs | |
| `pi_system.py` | Deterministic system-graph analysis | |
| `pi_server.py` | MCP server exposure | |

## Security Boundary (from SECURITY.md)

- Single local OS user trust domain (not multi-tenant isolation)
- Exact tool allowlists; remote MCP annotations do NOT grant read authority
- Writes require exact-hash operator approval; MCP cannot self-approve
- Checkpoints before dispatch; unknown remote outcomes do not auto-retry
- Hosted models transmit only authorized task/tool observations
- No OS process sandbox claim; registered checks/MCP run as the user

## Contributing Workflow

1. Read `PRODUCTION_ENGINEERING_SPEC.md` and `CLI_DESIGN.md` first
2. Work on a feature branch
3. Run full test suite before committing
4. Update relevant docs (VERIFICATION.md, README.md, LIVE_PLATFORM_RUN_PLAN.md)
5. Ensure `build_release.py` FILES list includes any new shipped files
6. Commit with clear message; tag release versions