# Extension assignments and evidence

The PDF contains the full 16-module course. These tasks extend the offline lab.
Keep all external effects in fixtures or an explicitly authorized sandbox.

1. Add a typed no-answer proposal without breaking invalid-output handling.
   Evidence: tests for absent evidence, conflicting evidence and unsupported claims.
2. Replace word overlap with BM25 and compare against the original retriever.
   Evidence: labeled queries, per-query recall and no-answer performance.
3. Add a context budget and source-version manifest.
   Evidence: overflow, stale version and secret-exclusion tests.
4. Add scoped memory with expiry and deletion of derived retrieval entries.
   Evidence: cross-tenant read denial, expiry, correction and deletion tests.
5. Extract the run controller into explicit nodes and persisted checkpoints.
   Evidence: restart before and after approval without duplicate effects.
6. Implement a real policy layer for ticket transitions and actor roles.
   Evidence: unauthorized transitions denied even with a forged proposal.
7. Add durable audit events in the same local transaction as the receipt.
   Evidence: crash/rollback tests proving event and effect consistency.
8. Build a simulated remote provider with committed-but-response-lost behavior.
   Evidence: unknown outcome, reconciliation and no duplicate logical effect.
9. Add true timeout isolation around a deliberately blocking model stub.
   Evidence: bounded wall time and cleanup without leaking background work.
10. Add a human-readable approval preview and a safe public event projection.
    Evidence: changed payload invalidates approval; private fields never stream.
11. Build paired evaluation over two proposal strategies and multiple trials.
    Evidence: isolated fixtures, confidence intervals, failure slices and costs.
12. Produce a release packet with a threat model, rollback plan and known limits.
    Evidence: every acceptance criterion links to an artifact or test result.

## Implemented in this companion snapshot

- Assignment 2 now has a first implementation: Repository defaults to BM25,
  and the original word-overlap scorer remains available as `method="overlap"`.
  Evidence: `test_bm25_retrieval_prefers_specific_short_evidence` and
  `test_overlap_retrieval_remains_available_as_baseline`.
- Assignment 3 now has a first implementation: `build_context` returns a
  budgeted `ContextBundle` with source IDs, versions, content hashes, token
  costs, truncation state and exclusion reasons. Evidence:
  `test_context_bundle_budget_and_manifest`,
  `test_public_manifest_excludes_raw_text`,
  `test_context_snapshot_changes_with_source_version` and
  `test_context_rejects_invalid_budget`.

Do not weaken existing tests to make an extension pass. Document intentional
contract changes and add stronger tests for the new behavior.
