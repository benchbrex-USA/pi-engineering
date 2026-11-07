# Release verification: 0.6.0

Date: 2026-09-28. Verdict: PASS WITH EXTERNAL GATES.
Scope: single-OS-user macOS arm64 CLI, Python 3.11, isolated runtime.
Full customer production qualification remains incomplete. Automated checks are
not an independent security assessment or representative-user acceptance.

## 0.6.0 evidence

The 0.6.0 release adds deterministic system-graph analysis (`system
validate/inspect/check/trace/impact/sample` over software, security and wiring
domains), a hardware reviewer persona preset, shareable example graphs and the
packaged wheel 0.6.0. The graph runtime is unchanged since the graph release;
see GRAPH_VERIFICATION.md for its acceptance matrix, synthetic baseline,
failure paths and packaging results.

| Claim | Executed evidence | Result |
| --- | --- | --- |
| Regression behavior | 119 tests in tests/ and 46 companion tests, each suite run twice | PASS |
| System-graph analysis | Real console-script acceptance: validate, inspect, check, trace, impact, sample including refusal paths | PASS |
| Failed write conflict | Changed-file write conflict marks the task unresolved and never overwrites | PASS |
| Workflow packs | All nine packs load, including hardware-review | PASS |
| Installed package acceptance | proposal, approval, write/readback, replay, retrieval, memory, checks, encrypted recovery | PASS |
| Static security scan | Bandit 1.9.4, fifteen production modules, no findings; two documented nosec suppressions for env-var-name literals | PASS |
| Dependency advisories | pip-audit 2.10.1, exact 36-package runtime lock | No known vulnerabilities |

## Post-release patch verification (2026-11-07)

Scope: same single-OS-user macOS arm64 local CLI. This updates the test counts
above for the current tree and does not re-open or close the external gates.

| Claim | Executed evidence | Result |
| --- | --- | --- |
| Regression behavior | 129 tests in tests/, consecutive `unittest discover` runs | PASS |
| Animated live operation | `Terminal.operation` renders non-nested and leaves an empty `_live_stack` on completion and KeyboardInterrupt | PASS |
| Provider diagnostics | Codex failure parses the last structured stdout/stderr event and reports credits/auth/rate-limit reasons instead of a generic error | PASS |
| Tool-grant guidance | Unknown or ungranted tools name the agent allowlist or the `mcp add` step in the error | PASS |
| Distribution | Rebuilt 0.6.0 wheel installs non-editably; `profile list` shows four presets; `tests/check_distribution.py` passes | PASS |
| Artifact identity | `build/lib` modules byte-identical to source; wheel and source zip digests recorded in `SHA256SUMS.txt` | PASS |

Patch fixes: stale-ticket approvals are invalidated when a ticket changes,
tenant-scoped state treats an empty tenant as no rows, p95 uses nearest rank,
component analysis builds adjacency once, the animated live stack renders and
cleans up correctly, Codex provider failures surface the real reason from the
last structured event, unknown/ungranted tools explain how to grant them, and
`doctor` names an unconfigured model. The declared 0.6.0 identity is unchanged;
the wheel was rebuilt locally and is not published. Live hosted-model
acceptance remains blocked: the available Codex account has no credits, and no
Ollama service or cloud API key is present.

## 0.5.0 graph release (retained evidence)

The graph release added completion-driven scheduling, resource ownership and
offline validation/explanations. See GRAPH_VERIFICATION.md for its
acceptance matrix, synthetic baseline, failure paths and packaging results.
Live-model and integration rows below are historical retained evidence, not
fresh external qualification of that graph release.

| Claim | Executed evidence | Result |
| --- | --- | --- |
| Regression behavior | 86 source tests: 76 product and 10 legacy tests | PASS |
| Interrupted restore | Injected failures before/after publication block state access | PASS |
| Recovery publication | Successful publication restores records; concurrent nonempty state preserved | PASS |
| Real model retrieval, memory, approved write | Three isolated trials, nine cases | 9/9 PASS |
| Public MCP contract qualification | DeepWiki public MCP SDK repository, schema pin and response assertion | PASS |
| HTTP bearer boundary | Real local SDK HTTP server accepts correct token and rejects wrong token | PASS |
| Qualification cannot dispatch effectful tools | Negative read-policy and schema-drift tests | PASS |
| Tenant-response contract | Wrong synthetic tenant fails response assertion | PASS |
| Report minimization | Raw fixture responses absent from reports and audit events | PASS |
| Resource hardening | Excessive Codex event output refused | PASS |
| State integrity boundary | Configuration, lock and SQLite journal symlinks refused | PASS |
| Terminal qualification views | Plain output at 32/80/120 columns | PASS |
| Static security scan | Bandit 1.9.4, thirteen production modules | No findings |
| Dependency advisories | pip-audit 2.10.1, exact 36-package runtime lock | No known vulnerabilities |

## 0.4.0 terminal evidence

Installed wheel acceptance passed proposal, exact approval, write/readback,
replay, retrieval, memory, checks and encrypted recovery. The installed
`~/.local/bin/pi-engineering --version` returns 0.4.0.

Nine new UI tests cover searchable completion, validation, approval-hash
noncompletion, parallel task identity, widths, failure status, workflow totals,
interruption cleanup, color fallback and real engine-event projection.
Manual PTY checks exercised Ctrl-P search, selection, review and clean exit.
An actual hosted-model run in an empty temporary workspace completed in two
steps with a workspace_files observation; no private documents were sent.
Animated frames and elapsed time were observed during that run.

Rich-rendered approval/write previews at 40 and 100 columns were visually
inspected. These are render fixtures from an actual local approval roundtrip,
not screenshots of a customer session. Progress percentages are only rendered
for known workflow node totals. Plain and JSON output do not animate.

Installed 0.3.1 console-script acceptance passed proposal, exact approval,
write/readback, replay, retrieval, memory, checks and encrypted backup/restore.
Manual PTY startup from the home directory, workspace display, empty checks,
error handling and clean exit were exercised in the isolated installed runtime.

Live acceptance used only generated public labels, never private playbook excerpts.
Each model case took two model steps. Nine cases are a repeatability smoke check,
not a broad accuracy benchmark. The real external contract run took 7.72 seconds
including discovery. It is a public read service, not a private customer account.

The dependency audit initially found advisories in cryptography 46.0.7.
The release now pins 50.0.1 and installs an isolated environment; the exact
runtime lock passed a fresh advisory check. System Python was not upgraded.
See SECURITY.md for applicability, boundaries and maintenance instructions.

Retained tested behaviors include parallel DAG joins, approval hashes/expiry,
unknown-effect replay blocking, cancellation, bounded loops, file readback,
versioned and stale-source-aware PDF/text retrieval, operator memory expiry,
encrypted backup/restore and no-overwrite recovery.

Earlier local persistence qualification exercised four processes, 200 tasks and
400 events, with intact SQLite state. It is not distributed load qualification
or an ADK comparison. No fourfold performance/intelligence claim is made.

## Reproduction

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/live_acceptance.py --trials 3
.venv/bin/python tests/live_integration.py
.venv/bin/python tests/check_distribution.py "$PWD/.venv/bin/pi-engineering"
.venv/bin/pi-engineering system validate examples/systems/software.json
python3 -m pip_audit -r requirements.lock --no-deps --disable-pip
python3 -m bandit pi_app.py pi_workspace.py pi_engine.py pi_tools.py pi_models.py pi_operations.py pi_knowledge.py pi_workflow.py pi_server.py pi_terminal.py pi_qualification.py pi_live.py pi_prompt.py pi_profile.py pi_system.py
```

Evidence files: reports/live.json, integration.json, dependency-audit.json,
security-static.json and load.json. Local MCP tests require listener permission.
Live cases require authenticated Codex and network access. CI defines macOS/Linux
Python 3.11/3.12 jobs; remote CI execution was not performed here.
The packaged source omits ten legacy teaching tests and their implementation;
its product-only suite excludes those ten legacy tests; current counts are in
GRAPH_VERIFICATION.md.

0.3.2 stages and fsyncs restore files before publication, and leaves a durable
recovery marker on failure. Configuration, databases and run access refuse an
unfinished restore. Recovery is into a new empty directory, preserving the failed
target for investigation. Tests inject publication and fsync errors; they do not
simulate physical power loss or certify filesystem/hardware durability.
The nine historical live-model cases above were obtained on 0.3.1. Version 0.4.0
also awaits subprocess stdin closure to consume broken-pipe cleanup errors;
the new two-step PTY smoke test exercised the updated adapter.

## 0.6.0 re-verification addendum (2026-11-08)

Re-ran the release gate after a dependency security update. Verdict: PASS WITH
EXTERNAL GATES (unchanged). Evidence, macOS arm64, Python 3.11:

- pip-audit previously reported 34 known vulnerabilities in 4 locked packages
  (certifi 2026.7.22, mcp 1.29.1, PyJWT 2.14.0, pypdf 6.16.1). Locked pins
  bumped in `requirements.lock` and `pyproject.toml` to certifi 2026.10.18,
  mcp 1.30.0, PyJWT 2.15.0, pypdf 6.21.4. Full suite: 129 tests OK.
- AutoForge verification gate (`autoforge.toml`, argv-only, mirrors
  `.github/workflows/ci.yml`): unittest discover suite, isolated wheel build,
  installed-package smoke (`tests/check_distribution.py`), profile presets
  (4), bandit on 15 production modules (0 findings), pip-audit on locked
  requirements (no known vulnerabilities). All six checks passed; evidence in
  `.autoforge/verification/20261107T204628Z-e99a46b9/result.json`.
- `build_release.py` regenerated `Pi_Engineering_CLI.zip` (68 files; no
  `.pi-engineering`, `.eval`, `.venv` or cache state inside); SHA256SUMS.txt
  regenerated. Clean-room check: fresh venv, `pip install
  dist/pi_engineering-0.6.0-py3-none-any.whl`, `--version` 0.6.0, presets
  present.
- `tests/check_distribution.py` per-call subprocess timeout raised 20s -> 120s
  for high-latency filesystems; no assertion changes.

## External gates

1. Customer account acceptance: no private customer endpoint, scoped test
   credentials or authorized tenant test cases are available. The new
   mcp schema / mcp qualify commands support that work, but protocol fixtures
   cannot establish a real customer's authorization or business semantics.
2. Independent assessment: no external assessor or representative user has
   provided findings/signoff. Bandit, advisory scans and implementation-agent
   tests must not be presented as independent penetration/usability testing.
3. Private document transfer: automatic approval review previously denied sending
   actual playbook excerpts to Codex's hosted model. The subsequent message
   repeated the authorization question, not an explicit approval. No excerpts
   were sent; no indirect bypass was attempted. Local PDF indexing remains usable.

## Operating limits

Use trusted local code and OS/device protection: Pi is not a process sandbox or
hosted multi-tenant service. Active SQLite is not application-encrypted; backups
are. Memory deletion does not erase historical observations or backup copies.
Retrieval is lexical BM25, not semantic vectors; scanned PDFs need external OCR.
Unknown remote effects stay unresolved until independently checked. Exact pixels
depend on terminal font/theme; automated width tests are not user research.

Confidence: medium for the tested local scope, insufficient for untested customer
deployments. The three external gates require real authorization/access/review;
they cannot be closed by relabeling another internal test.
