# Release verification: 0.3.2

Date: 2026-09-13. Verdict: PASS WITH EXTERNAL GATES.
Scope: single-OS-user macOS arm64 CLI, Python 3.11, isolated runtime.
Full customer production qualification remains incomplete. Automated checks are
not an independent security assessment or representative-user acceptance.

## Current evidence

| Claim | Executed evidence | Result |
| --- | --- | --- |
| Regression behavior | 56 tests: 46 product and 10 historical | PASS |
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
| Static security scan | Bandit 1.9.4, eleven production modules | No findings |
| Dependency advisories | pip-audit 2.10.1, exact 34-package runtime lock | No known vulnerabilities |

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
python3 -m pip_audit -r requirements.lock --no-deps --disable-pip
python3 -m bandit pi_app.py pi_workspace.py pi_engine.py pi_tools.py pi_models.py pi_operations.py pi_knowledge.py pi_workflow.py pi_server.py pi_terminal.py pi_qualification.py
```

Evidence files: reports/live.json, integration.json, dependency-audit.json,
security-static.json and load.json. Local MCP tests require listener permission.
Live cases require authenticated Codex and network access. CI defines macOS/Linux
Python 3.11/3.12 jobs; remote CI execution was not performed here.
The packaged source omits ten legacy teaching tests and their implementation;
its product-only suite contains 46 tests.

0.3.2 stages and fsyncs restore files before publication, and leaves a durable
recovery marker on failure. Configuration, databases and run access refuse an
unfinished restore. Recovery is into a new empty directory, preserving the failed
target for investigation. Tests inject publication and fsync errors; they do not
simulate physical power loss or certify filesystem/hardware durability.
Live-model results above were obtained on 0.3.1; the model adapter is unchanged.

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
