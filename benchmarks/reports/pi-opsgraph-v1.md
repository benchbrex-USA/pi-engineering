# Pi Engineering CLI Benchmark - OpsGraph v1

Latest result: the explicitly authorized run executed and failed to deliver
OpsGraph. Artifact score **0/100**; important product and harness blockers apply.
See **Authorized Pi Run** below. The earlier blocked result is retained unchanged
as historical context, not presented as the current run outcome.

## Result

**BLOCKED BEFORE SOLVER EXECUTION. NOT SCORED.**

Prepared on 2026-09-13; status recorded at 02:45:26 UTC.
The host's automatic approval reviewer rejected the first solver launch because
Codex/default would send potentially sensitive BeGuardit repository prompts,
source excerpts and tool observations to Codex's hosted service. It requires
explicit authorization for that destination/data transfer. No workaround,
alternate credential, indirect invocation or hosted solver retry was attempted.
No Pi solver task was created; `pi-engineering runs --json` returned `[]`.
No solver is running in the background.

This is an authorization/environment blocker, not evidence that Pi failed the
engineering challenge. No autonomous-engineering score can fairly be assigned.

## Environment

- Source repository: `/Users/benchbrex/Documents/BeGuardit`.
- Production branch: `main`, commit `29e04934251401d3837f48ed45ff8d2674b4367f`.
- Production checkout contained extensive pre-existing uncommitted changes.
  These were preserved and deliberately excluded from the committed baseline.
- Isolation: independent local Git clone, not a shared-object/hardlinked checkout.
- Solver directory: `/private/tmp/pi-opsgraph-v1/solver`.
- Solver branch: `benchmark/pi-opsgraph-v1`; no Git remote remains configured.
- Public challenge baseline: `f975fc13c14879f36236c4eb0f315d4c5159d243`.
- Pi executable: `/Users/benchbrex/.local/bin/pi-engineering`, version `0.5.0`.
- Node `v26.7.0`; npm `11.19.0`; macOS local host.
- Locked packages: Next.js `16.3.4`, React `19.2.8`, Playwright `1.63.0`.
- Framework: Next.js App Router, TypeScript, static export, repository CSS/Motion.
- Checks: ESLint, TypeScript, Next build, Playwright and axe tooling available.
- Applicable instructions read: AGENTS.md, CLAUDE.md, README, package metadata,
  Next configuration, TypeScript, ESLint and Playwright configurations.

## Solver configuration and bounds

Pi's installed help/version/run help were inspected; no guessed invocation API.
Model provider is Codex, model selection `default`; underlying resolved model
name, token usage and cost are not exposed by a run because no run occurred.
Existing authentication would be used; no credentials were copied into Pi config.
No MCP servers are connected in the solver workspace.

The engineer agent has standard file/read/write/check/retrieval/memory tools,
100 model steps, the product's 900-second active-task deadline, a 64,000-character
context limit and 120-second individual model timeout. The outer benchmark bound
is 90 minutes with at most two infrastructure-only restarts. The tighter internal
budgets are material configuration limits, not equivalent to 90 minutes of
unrestricted engineering time. None of those solver budgets has been consumed.

Scope-only approval policy was frozen before launch: exact-hash approval of
in-workspace proposed file writes and pre-registered non-deployment checks;
no implementation hints, hidden-test feedback, or post-run fixes. Approval
continuations would be counted separately from restarts.

## Prepared challenge and leakage controls

Only public scaffolding was committed: the user task, a small topology sample,
three public tests, an empty route directory, isolated Playwright configuration,
and benchmark-state ignore rules. No graph algorithm, feature UI or solution
was implemented by the benchmark orchestrator.

The public specification defines a minimal independent test boundary in
`lib/opsgraph.ts` (`validateTopology` and `analyzeImpact`) without prescribing
an implementation. This is an additional documented benchmark constraint.
The original task was otherwise retained, including route, direction, cycles,
scenario, export, accessibility, performance and non-deployment requirements.

Hidden tests, reference results, rubric and orchestration evidence reside outside
the solver checkout at `/private/tmp/pi-opsgraph-v1/evaluator`.
The prepared hidden suite covers the requested algorithm edge cases and large
graph measurements. UI/state/export checks would be performed independently
against the frozen result. No hidden suite was passed to a solver or executed
against a nonexistent solution.

Process-scoped macOS sandbox policies deny solver/child access to the hidden
evaluator and original BeGuardit checkout. Registered checks additionally have
write confinement to the solver directory and local-network-only access.
An actual attempt to read the hidden rubric under the check policy returned
`Operation not permitted`, exit 1; a harmless command under that policy returned
exit 0. No global OS permissions were changed.

## Verification evidence

| Check actually performed | Result |
| --- | --- |
| Installed Pi --help, run --help, --version | Available; 0.5.0 |
| Locked dependency installation in independent clone | PASS; lifecycle scripts disabled |
| Baseline npm run lint | PASS |
| Baseline npm run typecheck | PASS |
| Baseline npm run build | PASS; static export generated |
| Sandboxed baseline lint/typecheck/build | PASS |
| Public feature tests on empty starter | Expected failure: solution module absent |
| Hidden evaluator read-denial probe | PASS: read refused |
| Solver baseline Git status before launch | Clean |
| Solver launch | Rejected by automatic approval review before execution |
| Pi task history after rejection | Empty |
| Production HEAD and porcelain status before/after | Identical |
| Production tracked diff SHA256 before/after | Identical |

Production diff digest:
`4b38b51e85fe18484420627faa39beb95f4fcb542e50397a618c577b5a419bd3`.
No production branch, working files, environment variables or deployment was changed.

Evidence logs are retained in the evaluator directory, including baseline command
outputs, configuration, frozen rubric, original production state, and controller.
The launch rejection is recorded in this report and the host tool conversation;
there is no fabricated solver transcript.

## Score

| Category | Score |
| --- | --- |
| Functional correctness | Not evaluated / 30 |
| Robustness and security | Not evaluated / 15 |
| UI/responsiveness | Not evaluated / 15 |
| Accessibility | Not evaluated / 10 |
| Performance | Not evaluated / 10 |
| Engineering quality | Not evaluated / 10 |
| Testing/documentation | Not evaluated / 10 |
| TOTAL | **Not scored / 100** |

Quality caps applied: none; an unrun challenge is not a failed implementation.

## Performance and responsive review

Planned dataset: 10,000 nodes and 30,000 edges, two warm-ups and five measurements.
Median/worst runtime: not measured; no implementation exists to evaluate.
390x844, 1280x720 and 1440x900: not evaluated for the same reason.
Accessibility findings, scenario reset, malformed URL state, export correctness
and regression attribution: not evaluated. Existing baseline build success is
not credited as solver success.

## Autonomy metrics

- Solver launch approval attempts: 1; executed solver invocations: 0.
- Restarts: 0; scope approvals: 0; solver clarification questions: 0.
- Solver start/end time and engineering wall time: not applicable; never started.
- Instruction inspection, solver-run tests/builds, self-recovery and limitation
  reporting: unobserved, not inferred from orchestrator preparation.
- Unrelated changed-line percentage: not applicable; no solver changes.
- Strongest/weakest implementation aspects: no observations available.
- Failures recovered/unrecovered by Pi: none observed; the host blocked launch.

## Final assessment

Would I trust this Pi configuration on a comparable multi-file engineering task
with limited supervision? **NO, not on the evidence of this benchmark: the run
has not happened, so trust is not established.** This is not a demonstrated
capability failure, and should not be compared numerically with completed runs.

To unblock: explicit user authorization to send the isolated BeGuardit benchmark
task, repository source excerpts and resulting tool observations to Codex's
hosted model through Pi Engineering CLI. Credentials and hidden evaluator data
are excluded. After authorization, use this frozen baseline and rubric; do not
change the task to improve Pi's prospects. The optional Codex control run is
deferred until the Pi benchmark is actually completed.

# Authorized Pi Run

## Authorization

The user explicitly authorized the frozen benchmark task, isolated source
context and tool observations to be sent to Codex's hosted model through Pi.
Secrets, credentials, production checkout contents, hidden tests/rubric and
evaluator logs were excluded from that authorization and were not supplied to Pi.
The source scan found no matches for the checked private-key/token/credential
patterns; this limited pattern scan is not a universal secret-detection guarantee.

## Environment

The solver was clean on `benchmark/pi-opsgraph-v1` at the exact frozen baseline
`f975fc13c14879f36236c4eb0f315d4c5159d243`. No remote was configured.
Pi remained 0.5.0. Configuration matched the saved preparation snapshot byte
for byte. Frozen rubric SHA256 matched
`670196b3a18532a0de97d28b3e081639027b462405bfcd51a79862694051d4bc`.
No challenge, public test, resource limit, Pi implementation or solver file was
changed to assist the run. Evaluator read denial was reproved before launch.

## Solver execution

| Metric | Observed value |
| --- | --- |
| Start UTC | 2026-09-13 02:51:44.166119 |
| End UTC | 2026-09-13 02:52:30.871535 |
| Wall duration | 46.705439 seconds |
| Pi active-task time | 45.867245 seconds |
| Task | task_8e279765f6834f14 |
| Pi outcome / process exit | verification_failed / 1 |
| Executed solver CLI invocations | 3: one run, two exact-hash approval continuations |
| Model steps exposed by Pi | 4 |
| Infrastructure restarts | 0 |
| Configured model | codex/default; resolved model identity not exposed |
| Tokens and cost | not exposed |

Pi listed the workspace, attempted two knowledge searches, and requested the
registered `next-docs` and `public` checks. Both were approved without hints.
Both checks returned exit 71 with `sandbox_apply: Operation not permitted`.
Pi then accurately reported that it had not implemented the feature or changed
files, identified defective file schemas, and reported the check-runner failure.
No files were written or implementation questions sent to the orchestrator.

The run was frozen at its terminal outcome. Its final commit remained the
baseline, tracked diff was empty and Git status clean. No repair or further
solver run was performed. No budget was increased: four of 100 steps and about
46 of 900 active seconds were consumed, below the 90-minute outer maximum.

## Result

**Failed: no OpsGraph implementation was produced.**

Two independently observed blockers must be distinguished:

1. **Pi 0.5.0 product defect.** Once checks are registered, its advertised
   `workspace_read.path`, `workspace_write.path`, `workspace_write.expected_hash`
   and search-query schemas inherit an enum containing the registered check
   names. Consequently normal file paths and `missing` cannot validate.
   Independent JSON-schema checks of the installed tool output rejected
   `AGENTS.md` and a new `lib/opsgraph.ts` write. Read-only code inspection found
   a shared mutable string-schema dictionary in `pi_tools.py:47`; setting the
   check-name enum at line 159 mutates the other fields using that same object.
   This was diagnosed, not repaired. It prevents the configured solver from
   exercising normal source read/write capabilities even without the other issue.
2. **Benchmark harness limitation.** The frozen outer solver sandbox launches
   registered checks that themselves invoke sandbox-exec. A harmless `true`
   command returned 0 in the single check sandbox but 71 in the nested arrangement.
   This reproduces the check failures independently of BeGuardit code. The
   preparation checks tested one sandbox and missed this combined launch failure.
   This is attributable to benchmark setup, not Pi's application implementation.

Neither defect is a demonstrated transient outage. An unchanged restart would
retain both. Fixing Pi or relaxing/changing the frozen execution arrangement
would invalidate this attempt, so no restart was used to improve its score.

## Score

This scores the **delivered artifact**, not an inference about the hosted model's
ability under functional tooling. No feature artifact exists, and baseline site
quality is not credited to Pi. Environment-confounded capability assessment is
explicitly limited below; the score must not be used as a clean model comparison.

| Category | Score | Evidence |
| --- | --- | --- |
| Functional correctness | 0/30 | Core module absent; feature tests cannot load |
| Robustness and security | 0/15 | No topology validation or scenario implementation to verify |
| UI/responsiveness | 0/15 | Feature route returns 404 at all three viewports |
| Accessibility | 0/10 | No OpsGraph workflow or nonvisual graph interface exists |
| Performance | 0/10 | No analysis implementation; required measurement cannot execute |
| Engineering quality | 0/10 | No implemented feature architecture/components |
| Testing/documentation | 0/10 | No solver-authored tests or feature documentation |
| **TOTAL** | **0/100** | Missing deliverable; product and harness blockers apply |

## Quality caps

The nonfunctional/absent core-analysis cap is 59; it does not further reduce
the zero artifact score. The existing application production build passes, so
the build-failure cap does not apply. Nontermination, XSS and hardcoding were
not established; their caps are not invented or applied. No thresholds changed.

## Hidden evaluation results

The frozen hidden suite was executed and failed at module import with
`ERR_MODULE_NOT_FOUND` for `lib/opsgraph.ts`. Its individual correctness cases
and performance measurements therefore did not run; this is **not** reported
as twenty executed algorithm failures. The public suite likewise failed loading
the same absent module. No failing test was removed or weakened.

Linear/branching/converging traversal, cycles, multiple roots, depth bounds,
malformed topology, ordering and untrusted-text behavior remain unimplemented
and unverified. Scenario reset, malformed URL state and export cannot be
exercised because the feature route does not exist. The malformed-state URL
also returned 404; this is not evidence of a safe scenario-state parser.

Independent lint, TypeScript and Next production build all returned 0 against
the frozen workspace. Those results establish that the original starter still
builds, not that Pi completed any benchmark behavior.

The existing repository Playwright suite was also invoked with the frozen
benchmark configuration. It returned 1 before tests ran: its webServer readiness
check timed out after 60 seconds, with repeated 404 responses for `/` and
`/index.html`. The export's `out/index.html` exists. This is another harness
readiness limitation, not a failed assertion against solver changes. It was not
repaired. The independent loopback browser review below succeeded separately.

Reproduction/evidence command families:

```sh
node --experimental-strip-types --test benchmarks/public/opsgraph.test.mjs
SOLVER=/private/tmp/pi-opsgraph-v1/solver node --experimental-strip-types --test /private/tmp/pi-opsgraph-v1/evaluator/hidden.mjs
npm run lint
npm run typecheck
npm run build
node_modules/.bin/playwright test --config=benchmarks/playwright.config.ts
node /private/tmp/pi-opsgraph-v1/evaluator/browser-review.cjs
```

The repository Playwright invocation used the single frozen check sandbox;
the controller retained exact commands, exit codes, stdout/stderr and timings
in `evaluation-*.meta.json`, `evaluation-*.stdout` and `evaluation-*.stderr`.

## Performance

The unchanged hidden evaluator contains the specified deterministic 10,000-node,
30,000-edge workload with two warm-ups and five measured trials. Import failure
prevented generation/analysis from executing. Warm-ups executed: 0; measured
trials: 0. Median and slowest valid time: **not measured**, not estimated.

## Responsive evaluation

An evaluation-only browser driver outside the solver served the frozen export
on a loopback port and blocked nonlocal browser requests. It captured and inspected:

| Viewport | HTTP result | Observed page | Page overflow |
| --- | --- | --- | --- |
| 390x844 | 404 | Existing BeGuardit not-found page | None |
| 1280x720 | 404 | Existing BeGuardit not-found page | None |
| 1440x900 | 404 | Existing BeGuardit not-found page | None |

There are no scenario controls, selected-node details, analysis results or
export controls to assess. Screenshots are in `pi-opsgraph-v1-assets/` beside
this report. Full-page capture preserves content below each viewport.

## Accessibility evaluation

Axe checks using WCAG 2 A/AA, 2.1 AA and 2.2 AA tags reported zero violations
on the existing 404 page at all three sizes. This is **not** an OpsGraph
accessibility pass. Keyboard scenario execution, focus treatment on graph
controls, non-color impact indicators and graph-list fallback are absent.

## Engineering-quality review

No solver implementation files, tests, components, dependencies or documentation
were added, modified or deleted. There is no feature architecture to grade.
The solver remained within scope and made no unsupported completion claim.
The file-schema issue is in Pi's tool boundary, not in the supplied BeGuardit
repository. Previous Pi regression-suite success did not cover this combination
of registered checks with general file-tool schemas.

## Autonomy metrics

- Clarification questions: 0. The final blocker report requested fixes, not
  implementation-choice clarification during the run.
- Approval continuations: 2; infrastructure restarts: 0.
- Failed approaches recovered from: none observed.
- Repository instructions inspected: no successful instruction-file read;
  `next-docs` was requested but could not execute.
- Own tests: public check requested, but sandbox prevented the test process.
- Own build: not requested or run by Pi.
- Own regressions detected/fixed: none; no implementation changes existed.
- Final limitation report: accurate on no changes and both observed blockers.
- Unrelated changed-line percentage: N/A (zero total changed lines, zero unrelated).
- Usage/cost/token information: not exposed. No estimate is substituted.

## Strongest behavior

Pi did not invent an implementation or passing checks. Its report correctly
identified the defective schema and sandbox errors and clearly stated what
remained undone. No hidden-test information or repair advice was provided.

## Weakest behavior

The installed configuration could not perform ordinary source-file operations
once checks were registered, and delivered no feature. The harness also failed
to provide a functioning nested check runner, preventing fair assessment of
the requested engineering workflow beyond discovery and blocker reporting.

## Self-recovered failures

None observed. Accurate diagnosis is recorded separately from successful recovery.

## Unrecovered failures

File-tool schema corruption and nested check-runner sandbox initialization.
Neither was repaired as part of this black-box benchmark.

## Unrelated changes

No solver changes. Production commit, status and tracked-diff digest matched
the preserved pre-benchmark evidence. No production environment, remote, DNS,
service or deployment was changed. Evaluation generated only local build/test
artifacts and evidence; it did not repair the frozen solution.

## Benchmark/environment limitations

This is one environment-confounded run, not a statistical model-quality result.
The original source checkout had uncommitted newer work, which remains excluded
from the committed benchmark. The runtime's 900-second task/64,000-character
context limits were preserved, although neither explains this early stop.
The hidden test interface was declared publicly before launch and remained fixed.
No recovery attempt was used because both failures reproduce under unchanged
configuration and one requires a product change prohibited in this attempt.

## Final assessment

**NO.** I would not trust this exact Pi 0.5.0 configuration to complete a
comparable multi-file task with limited supervision: its installed file schemas
reject normal source paths/hashes when checks are registered. The separate
harness failure limits broader conclusions about Pi or the hosted model.
Fixes belong in a separately authorized engineering task and a separately
identified future benchmark, not in this frozen score.
