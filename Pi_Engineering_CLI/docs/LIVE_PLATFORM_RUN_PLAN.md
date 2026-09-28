# Live platform run plan (local 0.6 RC)

**Status:** executed 2026-09-28. Tests (119 CLI + 46 companion, each run twice), non-editable 0.6.0 wheel install, scanners, wheel/source byte identity, and git state were **executed and verified**. Git dirty/untracked (spec R2/R6) was observed and is sealed by the release-freeze commit.

**Honest local RC:** freeze identity, green TUI contract, installable 0.6 surface (presets + workflows), refreshed 0.6 verification. Does **not** authorize customer-production language. P0 (spec §4): green tests, freeze, wheel, TUI. External gates are **P2 claim blockers**, not P0 for a single-user local CLI.

## Executed verification (2026-09-28)

| Check | Command | Result |
| --- | --- | --- |
| Full suite, twice | `.venv/bin/python -m unittest discover -s tests` ×2 | 119 tests OK |
| Companion suite, twice | `unittest test_runtime` ×2 | 46 tests OK |
| Version identity | installed `pi-engineering --version` | 0.6.0 |
| Wheel/source identity | byte-compare wheel modules vs source | identical |
| Non-editable install | clean venv, `pip install` 0.6.0 wheel | presets load from `sys.prefix/share` |
| Installed surface smoke | `profile list/show`, `system sample/validate/impact`, `workflow --validate --json` | PASS |
| Installed package acceptance | `tests/check_distribution.py` on installed script | PASS |
| Dependency advisories | `pip_audit -r requirements.lock --no-deps` | No known vulnerabilities |
| Static security scan | `bandit` on 15 production modules | 0 issues |
| build/lib identity | byte-compare `build/lib` vs source | identical |

## Evidence (this tree)

| Fact | Source |
| --- | --- |
| Declared **0.6.0** | `pyproject.toml`, `pi_workspace.py` `VERSION`, `pi_engineering.egg-info/PKG-INFO` |
| Wheels stop at **0.5.0** | `dist/` has 0.2.0–0.5.0 only; **no 0.6.0 wheel** |
| Docs still 0.5.0 | `VERIFICATION.md` “Release verification: 0.5.0” (2026-09-13); `README.md` “Version 0.5.0 adds…” |
| Zip builder stale | `build_release.py` ships `dist/pi_engineering-0.5.0-py3-none-any.whl`, **omits** `pi_profile.py` |
| Presets not in egg | `SOURCES.txt` has `pi_profile.py` + tests; **no** `presets/*.json` or `workflows/*.json` |
| Presets load beside module | `pi_profile.py`: `PACKAGE_PRESETS = Path(__file__).parent / "presets"` |
| Flat packaging | `pyproject.toml`: `py-modules` + `package-data` `"*" = ["presets/*.json", "workflows/*.json"]` |
| TUI P0 recorded red | `docs/PRODUCTION_ENGINEERING_SPEC.md` §3.1 (2026-09-15); `GRAPH_VERIFICATION.md` addendum |
| Wrap 32–180 cols | `CLI_DESIGN.md` / `BUILD_CONTRACT.md` §7; `pi_terminal.py` `row()` is one `Text` line |
| Checkout tests can pass | `tests/test_profiles.py` inserts source root |
| Scan stale vs 0.6 | `reports/security-static.json` 2026-09-13, loc 2416, **no** `pi_profile.py` |
| Bandit omits 0.6 modules | `SECURITY.md` / `VERIFICATION.md` omit `pi_live.py`, `pi_prompt.py`, `pi_profile.py` |
| External gates open | `VERIFICATION.md` 1–3; `SECURITY.md` no assessor / no private customer account |
| No `.github/` in listing | listing not truncated; remote CI not evidenced here |
| Boundaries implemented | allowlists `pi_engine.py`; HTTPS/loopback + `trust_env=False` + `token_env` `pi_tools.py`; restore fsync `pi_operations.py`; symlink refusals `pi_workspace.py` / `pi_tools.py` |

## Ordered remediation

### 1. Critical — Release identity 0.6.0 vs artifacts 0.5.0

Do not ship this tree as 0.6.0 until identity matches.

1. Keep declared **0.6.0** (`pyproject.toml`, `VERSION`) unless the product is not 0.6.
2. Update `VERIFICATION.md` header/date/scope to 0.6.0 after a real re-run (do not relabel 0.5.0 rows).
3. Update `README.md` “Version 0.5.0 adds…” to 0.6 (brain, profile, recipes); no customer-production claims.
4. Fix `build_release.py`: 0.6.0 wheel path; include `pi_profile.py`, `presets/*.json`, `workflows/*.json`.
5. Build/install a **0.6.0** wheel; `pi-engineering --version` must print 0.6.0; `dist/` must contain it.

### 2. Critical — CLI width/overflow (P0 DoD)

Recorded failures (2026-09-15) are **resolved**: as of 2026-09-18 the full suite is green (104 passed, 19 subtests passed), including:

- `test_product.ProductTests.test_terminal_wrap_and_injection`
- `test_qualification.QualificationTests.test_qualification_and_schema_render_without_color_or_overflow`
- `test_terminal_experience.TerminalExperienceTests.test_live_projection_parallel_states_and_widths`

`row()` / live badges wrap at 32/40/80/120/180; untrusted Rich markup is never evaluated. Plain / `NO_COLOR` behavior is verified.

### 3. High — Installed 0.6 surface must ship persona presets

`profile list/apply` is empty if `pi_profile.py` lands in site-packages without JSON.

1. Make package-data install `presets/*.json` (and workflows if the installed CLI needs them). `SOURCES.txt` shows they are **not** in the egg.
2. Prove with **non-editable** `pip install` (clean venv, not `-e`). Checkout `sys.path` tests are insufficient.
3. Smoke: `profile list` / `profile show developer` on the installed console script.
4. Keep `tests/test_schema_isolation.py` in the forever regression set.

### 4. High — Refresh 0.6 verification artifacts

1. Full `unittest discover` after TUI + packaging fixes.
2. Bandit on **all** packaged modules including `pi_live.py`, `pi_prompt.py`, `pi_profile.py`; replace `reports/security-static.json`.
3. pip-audit on `requirements.lock`; date `reports/dependency-audit.json`.
4. `tests/check_distribution.py` against the **installed** 0.6 script.
5. Graph addendum PASS is **not** a full-product seal; run graph tests as part of the product suite.
6. Live/MCP rows in `VERIFICATION.md` are historical unless re-executed.

### 5. High (claim only) — Customer-production language stays forbidden

Do not close gates 1–3 by rewriting docs. Independent assessor, representative-user signoff, and private customer MCP qualification remain **open**. Honest local RC ≠ “production-ready for customers.”

## Test / verify commands

```sh
# Identity
.venv/bin/python -c "from pi_workspace import VERSION; print(VERSION)"
.venv/bin/pi-engineering --version

# TUI P0 (dated red 2026-09-15 — re-verify)
.venv/bin/python -m unittest \
  tests.test_product.ProductTests.test_terminal_wrap_and_injection \
  tests.test_qualification.QualificationTests.test_qualification_and_schema_render_without_color_or_overflow \
  tests.test_terminal_experience.TerminalExperienceTests.test_live_projection_parallel_states_and_widths -v

# Full suite + schema isolation + graph
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_schema_isolation tests.test_graph_scheduler tests.test_graph_production -v

# Non-editable 0.6 install (not checkout path)
python3 -m venv /tmp/pi-0.6-rc
/tmp/pi-0.6-rc/bin/python -m pip install dist/pi_engineering-0.6.0-py3-none-any.whl
/tmp/pi-0.6-rc/bin/pi-engineering --version
/tmp/pi-0.6-rc/bin/pi-engineering --json profile list
/tmp/pi-0.6-rc/bin/python tests/check_distribution.py /tmp/pi-0.6-rc/bin/pi-engineering

# Offline workflow + scanners (include 0.6 modules)
.venv/bin/pi-engineering workflow workflows/review.json --validate --json
.venv/bin/pi-engineering workflow workflows/implement-review.json --validate --json
python3 -m pip_audit -r requirements.lock --no-deps --disable-pip
python3 -m bandit pi_app.py pi_workspace.py pi_engine.py pi_tools.py pi_models.py \
  pi_operations.py pi_knowledge.py pi_workflow.py pi_server.py pi_terminal.py \
  pi_qualification.py pi_live.py pi_prompt.py pi_profile.py
```

Optional (network/credentials; not a 0.6 seal if skipped): `tests/live_acceptance.py --trials 3`, `tests/live_integration.py`.

## Non-goals

- **No UI redesign.** `CLI_DESIGN.md` stays authoritative; wrap/overflow only.
- **No deletions** (`pi_legacy.py`, companion lab, archived teaching UI, historical reports).
- Do not re-rank documented limits as ship defects: hosted-model exfil, unsandboxed MCP/checks, unencrypted active SQLite. Code matches `SECURITY.md`.
- Do not treat unverified git dirty/untracked as a blocker until a git observation exists.
- Do not invent CI, remote Linux, or pen-test evidence. Do not market hosted multi-tenant, OS-sandbox, or customer-production-ready.
- Resolved as of 2026-09-18: three TUI tests green; setuptools ships presets via `data-files` (verified in the 0.6.0 wheel). Resolved 2026-09-28: `build/lib/` vs source byte identity measured — identical.

**Exit for local 0.6 RC:** version/docs/wheel agree on 0.6.0; three TUI tests green; non-editable install lists presets; Bandit+audit+distribution reports dated for this tree; no customer-production claim.
