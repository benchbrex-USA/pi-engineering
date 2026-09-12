# Pi Engineering product correction

## Outcome
A terminal workspace for real bounded AI tasks and MCP operations, grounded in
the playbook's separation of proposals, authority, execution and verification.
The support-ticket teaching case is not the product definition.

## Evidence and constraints
- The old CLI seeded fictional tenants on startup and only executed a fixed
  ticket-status parser. Agent registry tool strings were not connected tools.
- The requested visual reference is Yann-Edern Gillet's Specify CLI: horizontal
  header rules, contextual identity columns, ANSI status labels, aligned nested
  processing rows, concise callouts. Purple Figma component outlines and macOS
  window controls are design-editor/terminal chrome, not product UI.
- No browser dashboard, demo-first navigation, fabricated progress or performance
  claims. No claim of fourfold superiority without a comparative benchmark.

## Acceptance criteria
1. Startup creates no business data; setup records an explicit workspace/model.
2. Plain-language tasks invoke a configured real model, within call/time bounds.
3. MCP stdio and Streamable HTTP discovery and calls use the official SDK.
4. Each agent has an enforced tool allowlist. Remote annotations do not grant
   read authority. The operator explicitly identifies tools allowed without review.
5. Writes pause on exact argument/configuration hashes; only the local operator
   can approve. MCP clients can propose and inspect but cannot approve themselves.
6. Execution attempts are persisted before dispatch. Interrupted calls are
   unresolved, never silently retried. Completed calls survive process restart.
7. Terminal output sanitizes untrusted control characters, wraps to terminal
   width, works without color, and leaves the cursor/terminal usable on exit.
8. Runs, tool arguments, outputs and receipts are inspectable; external outcome
   claims distinguish server responses from independently verified business state.

## Architecture decision
Keep Python and SQLite, replace the application entry point, use Rich for terminal
layout/live indicators and the pinned MCP 1.x SDK for transport. Store versioned
project configuration separately from durable run state. Use a bounded model/tool
loop per named agent, with explicit handoffs through separate tasks. Ollama's chat
API supplies a configurable local or HTTPS model endpoint. An authenticated Codex
adapter also supports hosted operation with native tools disabled. Independent
DAG branches run concurrently. FTS5 provides versioned cited retrieval; operator
memory has provenance and expiry. No production model is simulated.

Alternatives: Ink would reproduce the article's original implementation stack but
require replacing the Python runtime; a full-screen TUI would lose the article's
scrollback-oriented workflow. Neither is needed for visual fidelity.

## Failure semantics
Missing model or connection: actionable configuration error. Invalid model/tool
schema: stop without dispatch. Unknown execution outcome: preserve the attempt,
block replay, require operator reconciliation. Concurrent resume: exclusive run
lock. Changed server/agent config: approval invalidated. Cancellation: persist
interrupted state and do not claim cancellation of remote effects.

## Release evidence
Verify real SDK subprocess roundtrips, persistence, policy denial, approval binding,
replay protection, interruption, malformed inputs and narrow/large terminal output.
Live model quality, external integration qualification, representative-user UX
testing and deployment security review remain release requirements, not claims
inferred from local tests. The trust boundary is a single local OS user.
