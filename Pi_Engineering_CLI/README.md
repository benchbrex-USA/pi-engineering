# Pi Engineering

A terminal workspace for graph-based agent tasks and MCP tools. The installed
command now starts the task interface; the previous ticket teaching application
is archived in `pi_legacy.py` and is not included in the Python distribution.

## Install and start

Python 3.11 or later is required. Install into an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/pi-engineering --workspace /path/to/project
```

On this Mac, `pi-engineering` points to the project's isolated `.venv` console
script. `install.sh` installs pinned dependencies there, checks compatibility and
updates only a recognized Pi symlink; system Python packages remain unchanged.
Rerun it after source updates. The Python package is the portable installation.

## Open brain

Pi is an advanced agent whose performance scales with the model you attach.
Model names are not allowlisted. Use any Codex login, Ollama tag, Grok id, or
OpenAI-compatible endpoint (`--provider compat`).

```sh
pi-engineering brain open
pi-engineering brain set grok-4.6 --provider grok
pi-engineering brain set YOUR_MODEL --provider compat --endpoint https://YOUR_HOST/v1 --token-env YOUR_KEY_ENV
pi-engineering brain show
```

Authority stays local: the brain proposes; you approve writes and grant tools.

## Persona profiles

Apply an audience preset without wiping your workspace:

```sh
pi-engineering profile list
pi-engineering profile show developer
pi-engineering profile apply developer
pi-engineering profile apply hacker --replace-agents
pi-engineering recipe export --json
pi-engineering workflow workflows/implement-review.json --validate --json
```

Supported built-in profiles: `developer`, `hacker`, `cto`.

## Connect a model

Pi supports Grok (login or `XAI_API_KEY`), an authenticated Codex CLI, or Ollama's real chat/tool API. On this
Mac, Codex is configured and live acceptance checks passed using its existing
ChatGPT login. No credentials are copied into Pi configuration.

```sh
pi-engineering setup
pi-engineering model set grok-4.6 --provider grok
# or: pi-engineering model set default --provider codex
pi-engineering doctor
pi-engineering workspace use /path/to/project
pi-engineering
```

Codex receives the selected task and observations through its hosted service.
Only grant tools for data you authorize that service to process. Pi disables
Codex native shell, apps, web search and subagents; proposed effects return to
Pi's approval gate. This is application policy, not an OS security boundary.
For local processing, install and
start Ollama using https://docs.ollama.com/quickstart, and pull a model with tool
calling support appropriate for the machine. Pi does not download large models
or silently substitute a simulated model.

```sh
pi-engineering setup
pi-engineering model set YOUR_INSTALLED_MODEL --provider ollama --endpoint http://127.0.0.1:11434
pi-engineering doctor
pi-engineering
```

For a protected HTTPS Ollama endpoint, use `--token-env ENVIRONMENT_VARIABLE`.
Only the environment variable name is saved. Do not place secrets in command
arguments, server URLs, task prompts or committed configuration files.

In the session, type a task in ordinary language. `/help` lists actions; Ctrl-P
opens searchable commands, Tab and arrow keys select completions, arrow keys
recall session input, and `/review` opens the latest pending action. Ctrl-C interrupts the
active task, and `/quit` exits. The screen stays in terminal scrollback.

```sh
pi-engineering run "Review pi_engine.py for incorrect recovery behavior and cite file paths"
pi-engineering runs
pi-engineering show TASK_ID
pi-engineering trace TASK_ID --json
```

Use `--workspace DIRECTORY` to select the project. Global flags work before or
after commands. `--plain`, `NO_COLOR`, and `--no-animate` disable visual effects;
`--json` produces machine-readable output without terminal decoration.

## Connect MCP servers

Stdio starts the explicitly configured command with an argument array, never a
shell string. Streamable HTTP supports HTTPS and loopback HTTP. SDK protocol
negotiation, request IDs, tool schemas and pagination are used directly.

```sh
pi-engineering mcp add repository --command /absolute/path/to/server --arg=--stdio
pi-engineering mcp add operations --url https://YOUR_HOST/mcp --token-env OPERATIONS_TOKEN
pi-engineering tools
pi-engineering doctor
```

`--env NAME` explicitly forwards an environment variable to a stdio server.
Normal SDK OS environment variables are also available. MCP programs run as the
local OS user; only configure trusted programs. Pi is not an OS process sandbox.

Tool names use `SERVER__TOOL`. Discovering a tool does not grant agent access.
Grant an exact tool list to each agent:

```sh
pi-engineering agent set engineer --role "Implement and verify the requested change" \
  --tools workspace_files workspace_read workspace_write repository__inspect
```

Remote tools require review by default, regardless of their annotations. Use
`mcp add ... --read-tools TOOL_NAME` only for tools the operator has independently
classified as safe reads. The list uses original server tool names, not aliases.
Re-adding a connection replaces its complete definition; include retained flags.

## Qualify an integration

Inspect the exact schema and copy its pin into an operator-reviewed contract:

```sh
pi-engineering mcp schema operations__inspect --json
pi-engineering mcp qualify integration.json --json
```

The contract format is:

```json
{
  "version": 1,
  "probes": [{
    "name": "tenant-identity",
    "tool": "operations__inspect",
    "arguments": {},
    "input_schema_sha256": "REPLACE_WITH_THE_REVIEWED_SCHEMA_HASH",
    "response_schema": {
      "type": "object",
      "required": ["structuredContent"],
      "properties": {
        "structuredContent": {
          "type": "object",
          "required": ["tenant_id"],
          "properties": {"tenant_id": {"const": "EXPECTED_TENANT"}}
        }
      }
    }
  }]
}
```

This is a contract template, not a preconfigured customer integration. Match its
fields to your actual server. Qualification refuses writes, local tools, schema
drift and external schema references before calling a probe. A failed response
assertion exits nonzero. Reports and audit events contain hashes, timing and
status, not raw customer responses. Read classification is an operator assertion;
Pi cannot prove that a falsely labeled server tool has no effects.

## Graph and agents

The persisted graph is `intake -> context -> propose -> policy -> review ->
execute -> verify`, with a bounded return to `propose`. Read tools skip review.
An answer completes the loop; failed and unknown effects do not become success.
`graph --json` returns the legal edge map; `trace` returns actual checkpoints.

The default agents are engineer, researcher and reviewer. Engineer can read and
propose file writes. Researcher and reviewer have read access only. A role is a
model instruction, while the tool allowlist is enforced by the host.

Workflow JSON declares a DAG under `nodes`. Each named node has `agent`, `task`,
and `depends_on` (a list of node names). Run it with `workflow FILE.json`. Pi uses
Python's topological sorter to reject cycles and orders all dependencies before
their consumers. Completed predecessors supply labeled observations to successors.
Independent branches execute concurrently, with a default limit of four and
an optional workflow-level `concurrency` integer from 1 to 8. Dependencies join
only after predecessor completion. Maximum graph size is 32 nodes. Agent model
overrides use `agent set NAME --model MODEL --provider codex|ollama` together
with the desired role and complete tool list.

Re-running the same file resumes its saved graph without replaying completed
nodes. A changed plan or different absolute filename identifies a new graph.
After approving a paused node, run the workflow command again to continue.

Version 0.5 schedules as each task finishes: unrelated slow or approval-paused
branches no longer hold back ready dependents. Every join still requires all
prerequisites to succeed. Completed processing does not override failed checks.

```sh
pi-engineering workflow workflows/review.json --validate --json
pi-engineering workflow workflows/review.json
pi-engineering workflow workflows/review.json --explain
```

Validation and explanation are offline: no inference, MCP discovery or tool
dispatch. Explain includes revision, task IDs, blockers and next actions, without
task prompts or tool payloads. Its workflow status is the last saved scheduler
snapshot; task statuses are current. Run again after approving a task to refresh
the workflow outcome. JSON success output stays on stdout, errors on stderr;
failed/unknown/exhausted/rejected/interrupted outcomes return 1, pending review
returns 0 (preserved behavior), and Ctrl-C returns 130.

Plans with `"version": 2` can add node `priority` (-100 to 100, higher first)
and `resources` (exclusive named resources). Equal priorities sort by node name.
Declare the same resource on tasks that must not overlap, e.g. `"resources":
["repo:working-tree"]`. These are scheduling constraints, not new permissions.
Locks cover participating local tasks and manual approval/resume, not unrelated
programs or undeclared remote conflicts. External lock contention stops that
node's dispatch for this invocation; `--explain` gives the retry action.

Checkpoint schema 2 binds workspace location, plan revision and each task;
configuration drift refuses reuse, including completed nodes. Valid v1 records
upgrade automatically without changing their flow ID. No SQL data is deleted.
Moving a workspace intentionally requires a new graph revision/path; completed
records remain inspectable. Old releases do not enforce new resource semantics:
do not use them to resume v2 tasks. To roll back the package, stop active work,
retain state and install the retained 0.4.0 wheel, then use a fresh workspace and
v1 plans only. Do not downgrade or strip metadata on existing checkpoints.
See GRAPH_UPGRADE.md and GRAPH_VERIFICATION.md for scope, evidence and backlog.

## Approval and recovery

File edits show exact arguments and a before/after diff. Approval binds the action
hash, tool schema and workspace configuration, and expires after one hour. File
writes additionally compare the observed prior content hash and verify readback.

```sh
pi-engineering approve TASK_ID EXACT_ACTION_HASH
pi-engineering reject TASK_ID
pi-engineering resume TASK_ID
pi-engineering receipt TASK_ID --json
```

The runtime persists dispatch before calling a tool. A crash or timeout after
dispatch leaves an unresolved outcome and blocks automatic replay. Check the
target system, then record evidence with:

```sh
pi-engineering reconcile TASK_ID --outcome executed --evidence "TARGET_RECEIPT_REFERENCE"
```

Reconciliation records an operator assertion; it does not re-execute the call or
pretend that an assertion is independent verification. Begin a new task after
checking the external state. Changed configuration, expired approval and exhausted
budgets also require a new task. Interrupted model requests can be resumed.

Local receipts distinguish verified file readback from a remote server response.
A model answer means the agent loop finished, not that every factual claim was
independently verified. No generic protocol can prove arbitrary business effects.

## Expose Pi to another agent

Configure that client's stdio command as:

```sh
pi-engineering --workspace /absolute/project mcp-server
```

The official MCP SDK server exposes `pi_runs`, `pi_task`, `pi_agents`, `pi_graph`,
`pi_run`, and `pi_propose`. Approval and configuration mutation are deliberately
absent from this surface. An agent cannot approve its own effect through Pi MCP.
The server is stdio-only and scoped to its configured local workspace.

## Storage and operations

State lives in the selected project's `.pi-engineering/`: versioned `config.json`,
SQLite task checkpoints, receipts, event history, and run locks. Configuration is
atomically replaced. State permissions are restricted to the current OS user.
Do not commit this directory: it contains task input and tool observations.

Use the encrypted online backup command described below. Old `.pi/` ticket
records are untouched. No automatic migration reinterprets old approvals.
The current threat boundary is one trusted OS user, not a hosted multi-tenant API.

`doctor` checks configuration, SQLite integrity, model discovery, and every
enabled MCP connection. It exits nonzero when any check fails. Task execution
exits nonzero for failed, unresolved or budget-exhausted tasks; paused approval
is a successfully recorded proposal and exits zero. Interrupt exits 130.

## Retrieval and memory

```sh
pi-engineering knowledge add handbook.pdf
pi-engineering knowledge search "approval policy"
pi-engineering knowledge list
pi-engineering memory add --title "Release policy" --body "Require review" --source "Operator" --ttl-days 90
pi-engineering memory search "release"
pi-engineering memory remove MEMORY_ID
pi-engineering knowledge remove SOURCE_ID
```

Local PDF/text ingestion stores page/line citations, source hashes and versions.
SQLite FTS5 BM25 retrieval excludes changed or missing sources until re-indexed.
This is lexical retrieval, not semantic vector search. PDF limits are 20 MB,
250 pages and one million extracted characters; scanned PDFs need external OCR.
Agents receive retrieval only through granted `knowledge_search` and
`memory_search` tools. Memories are operator-saved, versioned and expiring;
models cannot silently persist their own claims. Removal affects active retrieval,
not historical task observations or existing backup copies. State is private to
the OS user but not encrypted on disk by Pi; use device encryption where required.

## Verification commands

Register trusted argv commands, then grant `workspace_check` to an agent. No
arbitrary shell string is accepted from the model. Each execution requires exact
approval and shows its configured argv. Commands run as the OS user, may execute
project code and access that user's files, and are not sandboxed.

```sh
pi-engineering check add tests --command python3 --arg=-m --arg=unittest --arg=discover --arg=-s --arg=tests
pi-engineering check list
pi-engineering call workspace_check '{"name":"tests"}'
```

Checks have a 120-second timeout and 64 KB captured output limit. Nonzero exit
codes produce `verification_failed`, not a successful task. File readback and
test outcomes remain distinct evidence; a passing check only proves its assertions.

## Backup and recovery

Set `PI_BACKUP_PASSPHRASE` securely in the process environment, then:

```sh
pi-engineering backup /secure/location/project.pi
pi-engineering --workspace /empty/project restore /secure/location/project.pi
pi-engineering metrics
```

Backups use SQLite online snapshots and AES-256-GCM with a scrypt-derived key.
They contain configuration and task/knowledge/memory state, not project files or
model credentials. Keep the passphrase separately; it cannot be recovered.
Restore validates authentication, archive bounds, config and database integrity,
and refuses existing state. Restore project files separately for source validation.
Stop changing configuration during a backup so it matches the database snapshot.

Restore stages and synchronizes the database/configuration before publication.
An interrupted restore leaves `.pi-restore-in-progress`; Pi refuses to use that
workspace. Preserve it for diagnosis and restore the original encrypted backup
into another empty directory, then use `workspace use` to switch there. Do not
delete the marker to make partially restored state appear healthy.

## Verification and release status

Run `python3 -m unittest discover -s tests -v`. Product tests cover graph paths,
MCP SDK subprocess transport, permission enforcement, exact approval, restart,
no-replay behavior, file conflicts, cycle detection and terminal widths.
Legacy tests separately preserve the old teaching runtime behavior.

Version 0.5.0 adds completion-driven graph scheduling and offline inspection to the live terminal interface, live-model acceptance, public external MCP acceptance,
parallel graph execution, memory/retrieval and encrypted recovery evidence. See
`VERIFICATION.md` and `reports/` for measured results and remaining gates.
Customer-specific integrations, representative-user testing and independent
security qualification are not implied by these checks. No fourfold performance
claim or universal production-readiness certification is made.

The installer applies `requirements.lock` for reproducible runtime versions.
The lock was tested on macOS arm64; Intel Macs may require a source build of
cryptography and are not qualified by this release. `SECURITY.md` describes the
security boundary, automated checks and customer acceptance procedure.

## Production engineering

Full system audit, production definition of done, workstreams, and implementation prompts:

- [docs/PRODUCTION_ENGINEERING_SPEC.md](docs/PRODUCTION_ENGINEERING_SPEC.md)
- [docs/ENGINEERING_PROMPTS.md](docs/ENGINEERING_PROMPTS.md)
