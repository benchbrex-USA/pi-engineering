# Pi Engineering - Offline Reference Lab

Framework concept: Developer Parth Patel, Founder of BeGuardit and BenchBrex.
Research edition: September 12, 2026.

This is a teaching companion to the Pi Engineering technical playbook and course.
It uses only the Python standard library, a scripted model and local SQLite.
It makes no network calls, uses no API keys and performs no real external actions.

## Run

Use Python 3.10 or newer. The delivered code was tested on Python 3.13.5.
From this directory:

```sh
python -m unittest -v
python pi_runtime.py
python experiments.py
```

The delivered suite contains 46 tests. The demo first reports awaiting_approval,
then committed after a host-side simulated approval. The ticket fixture changes
from open/version 0 to pending/version 1. Replaying the same logical operation
returns its stored receipt rather than creating another update.

## Files

- pi_runtime.py: contracts, tenant-scoped BM25 retrieval, context manifests,
  strict proposal parsing, extractive verification, local approval registry,
  transactional broker and loop.
- experiments.py: reciprocal rank fusion, retrieval metrics, Wilson intervals and
  simplified KV-cache capacity arithmetic.
- test_runtime.py: unit and local integration tests, including injected failures.
- assignments.md: extension tasks and acceptance evidence.
- test_results.txt: test run captured for this edition.
- sources.json: the manual's reference registry.

## Security and scope limitations

Principal is a trusted host input in the simulation. The authenticated boolean is
not real authentication. There is no session verification, role system or remote
identity provider. The whole Python process, including scripted model functions,
is trusted code; only returned model data is treated as untrusted.

The model is deterministic fixture code, not an LLM. The retriever is sparse
lexical BM25, with word-overlap retained only as a baseline comparison. It is
not an embedding system, reranker or semantic proof engine. Context token costs
are approximate word-token counts for lab budgeting, not provider accounting.
The verifier checks an exact quote and citation membership; it does not establish
general factual correctness or that the cited policy authorizes a proposed
business action. The broker demonstrates tenant and approval constraints, not a
complete business-policy engine.

issue_approval is a trusted-host method. It simulates a human/UI approval boundary
and must never be exposed as a model-callable tool. Approval tokens are secrets;
the demo does not print them. Production needs real identity, role checks,
protected storage, credential controls and an independently reviewed UI.

The local business mutation, receipt and approval consumption share one SQLite
transaction. This does not imply exactly-once behavior for remote APIs. Local
audit events are in memory and are appended after commit, so they are not a
durable atomic audit trail. A production system needs a durable event/outbox path.

The loop checks a deadline before and after synchronous model calls but does not
preempt a blocked call. It limits calls, not provider token charges or real spend.
Production adapters need transport timeouts, cancellation and cost reservations.

No live-provider integration, model training, GPU benchmark, distributed load
qualification, security penetration test or regulatory certification was run.
The remaining course labs are assignments, not claims of completed experiments.
