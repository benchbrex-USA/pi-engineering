import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

from pi_runtime import Action, Broker, Denied, Evidence, Principal, Repository, run
from experiments import kv_cache_bytes, recall_at_k, reciprocal_rank, reciprocal_rank_fusion, wilson_interval


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.p = Principal("aster", "alice", "run-1")
        self.b = Broker(now=lambda: self.clock[0])
        self.b.seed("aster", "T-1")
        self.b.seed("beacon", "T-2")
        self.repo = Repository([
            Evidence("A1", "aster", "Tickets may be marked pending."),
            Evidence("B1", "beacon", "Tickets are confidential for Beacon.")])
        self.raw = {"answer": "Tickets may be marked pending.", "citations": ["A1"],
                    "action": {"ticket": "T-1", "expected_version": 0, "status": "pending"}}
        self.action = Action("aster", "T-1", 0, "pending", ("A1",))

    def tearDown(self):
        self.b.close()

    def model(self, request, evidence, feedback):
        return copy.deepcopy(self.raw)

    def execute(self, **kwargs):
        return run("Tickets pending", self.p, self.repo, self.model, self.b, **kwargs)

    def test_missing_approval(self):
        self.assertEqual(self.execute().status, "awaiting_approval")
        self.assertEqual(self.b.read(self.p, "T-1")["version"], 0)

    def test_authorized_commit(self):
        token = self.b.issue_approval(self.p, self.action)
        result = self.execute(approval_token=token, operation_key="intent-1")
        self.assertEqual(result.status, "committed")
        self.assertEqual(self.b.read(self.p, "T-1")["status"], "pending")

    def test_scope_before_model(self):
        evidence = self.repo.retrieve(self.p, "Tickets")
        self.assertEqual([x.id for x in evidence], ["A1"])

    def test_bm25_retrieval_prefers_specific_short_evidence(self):
        repo = Repository([
            Evidence("generic", "aster", "pending pending pending " + "filler " * 30),
            Evidence("specific", "aster", "Ticket ABC-123 may be marked pending."),
        ])
        result = repo.retrieve(self.p, "ABC-123 pending", limit=2)
        self.assertEqual([x.id for x in result], ["specific", "generic"])

    def test_overlap_retrieval_remains_available_as_baseline(self):
        repo = Repository([
            Evidence("generic", "aster", "pending pending pending " + "filler " * 30),
            Evidence("specific", "aster", "Ticket ABC-123 may be marked pending."),
        ])
        bm25 = [e.id for e, _ in repo.score(self.p, "ABC-123 pending", "bm25")]
        overlap = [e.id for e, _ in repo.score(self.p, "ABC-123 pending", "overlap")]
        self.assertEqual(bm25[0], "specific")
        self.assertEqual(set(overlap[:2]), {"generic", "specific"})

    def test_context_bundle_budget_and_manifest(self):
        repo = Repository([
            Evidence("short", "aster", "Tickets may be marked pending.", version=3),
            Evidence("long", "aster", "Tickets may be escalated after manager review.", version=4),
        ])
        bundle = repo.build_context(self.p, "Tickets may be marked", token_budget=5)
        self.assertEqual([x.id for x in bundle.evidence], ["short"])
        self.assertTrue(bundle.truncated)
        self.assertEqual(bundle.manifest_items[0].source_id, "short")
        self.assertEqual(bundle.manifest_items[0].version, 3)
        self.assertEqual(bundle.token_cost, 5)
        self.assertEqual(bundle.excluded_items_and_reasons[0]["reason"], "budget_exceeded")

    def test_public_manifest_excludes_raw_text(self):
        repo = Repository([Evidence("secret", "aster", "Internal approval secret phrase.")])
        manifest = repo.build_context(self.p, "approval").public_manifest()
        self.assertNotIn("Internal approval secret phrase.", str(manifest))
        self.assertEqual(manifest["items"][0]["source_id"], "secret")
        self.assertIn("content_hash", manifest["items"][0])

    def test_context_snapshot_changes_with_source_version(self):
        first = Repository([Evidence("A1", "aster", "Tickets may be marked pending.", version=1)])
        second = Repository([Evidence("A1", "aster", "Tickets may be marked pending.", version=2)])
        self.assertNotEqual(
            first.build_context(self.p, "Tickets").source_snapshot,
            second.build_context(self.p, "Tickets").source_snapshot,
        )

    def test_context_rejects_invalid_budget(self):
        with self.assertRaises(ValueError):
            self.repo.build_context(self.p, "Tickets", token_budget=0)

    def test_unauthenticated(self):
        with self.assertRaises(Denied):
            self.repo.retrieve(replace(self.p, authenticated=False), "Tickets")

    def test_cross_tenant_ticket(self):
        with self.assertRaises(Denied):
            self.b.read(self.p, "T-2")

    def test_cross_tenant_action(self):
        with self.assertRaises(Denied):
            self.b.issue_approval(self.p, replace(self.action, tenant="beacon", ticket="T-2"))

    def test_no_evidence(self):
        result = run("unmatched", self.p, self.repo, self.model, self.b)
        self.assertEqual(result.status, "no_evidence")

    def test_bad_citation(self):
        self.raw["citations"] = ["B1"]
        self.assertEqual(self.execute(max_steps=1).status, "budget_exhausted")

    def test_unsupported_answer(self):
        self.raw["answer"] = "Any action is permitted."
        self.assertEqual(self.execute(max_steps=1).status, "budget_exhausted")

    def test_unknown_fields(self):
        self.raw["action"]["tenant"] = "beacon"
        self.assertEqual(self.execute(max_steps=1).status, "budget_exhausted")

    def test_invalid_numeric_type(self):
        self.raw["action"]["expected_version"] = True
        self.assertEqual(self.execute(max_steps=1).status, "budget_exhausted")

    def test_no_progress(self):
        self.raw["citations"] = ["missing"]
        self.assertEqual(self.execute().status, "no_progress")

    def test_read_only_answer(self):
        self.raw["action"] = None
        self.assertEqual(self.execute().status, "answered")

    def test_model_failure(self):
        def broken(*args):
            raise RuntimeError("provider secret must not escape")
        result = run("Tickets", self.p, self.repo, broken, self.b)
        self.assertEqual(result.status, "model_or_adapter_error")
        self.assertNotIn("secret", str(result))

    def test_expired_approval(self):
        token = self.b.issue_approval(self.p, self.action)
        self.clock[0] += 61
        with self.assertRaises(Denied):
            self.b.execute(self.p, self.action, token, "intent-1")

    def test_wrong_actor(self):
        token = self.b.issue_approval(self.p, self.action)
        with self.assertRaises(Denied):
            self.b.execute(replace(self.p, actor="mallory"), self.action, token, "intent-1")

    def test_wrong_run(self):
        token = self.b.issue_approval(self.p, self.action)
        with self.assertRaises(Denied):
            self.b.execute(replace(self.p, run_id="run-2"), self.action, token, "intent-1")

    def test_stale_policy(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.policy_version = "policy-v2"
        with self.assertRaises(Denied):
            self.b.execute(self.p, self.action, token, "intent-1")

    def test_changed_payload(self):
        token = self.b.issue_approval(self.p, self.action)
        with self.assertRaises(Denied):
            self.b.execute(self.p, replace(self.action, status="resolved"), token, "intent-1")

    def test_stale_resource(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.db.execute("UPDATE tickets SET version=version+1 WHERE tenant='aster'")
        with self.assertRaises(Denied):
            self.b.execute(self.p, self.action, token, "intent-1")

    def test_idempotent_replay(self):
        token = self.b.issue_approval(self.p, self.action)
        first = self.b.execute(self.p, self.action, token, "intent-1")
        second = self.b.execute(self.p, self.action, token, "intent-1")
        self.assertEqual(first, second)
        self.assertEqual(self.b.read(self.p, "T-1")["version"], 1)

    def test_key_collision(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.execute(self.p, self.action, token, "intent-1")
        with self.assertRaises(Denied):
            self.b.execute(self.p, replace(self.action, status="resolved"), token, "intent-1")

    def test_consumed_token_cannot_authorize_new_intent(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.execute(self.p, self.action, token, "intent-1")
        with self.assertRaises(Denied):
            self.b.execute(self.p, self.action, token, "intent-2")

    def test_rollback_is_atomic(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.fail_before_commit = True
        with self.assertRaises(RuntimeError):
            self.b.execute(self.p, self.action, token, "intent-1")
        self.assertEqual(self.b.read(self.p, "T-1")["version"], 0)
        self.assertEqual(self.b.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 0)
        self.b.fail_before_commit = False
        self.assertEqual(self.b.execute(self.p, self.action, token, "intent-1")["outcome"], "committed")

    def test_minimal_audit(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.execute(self.p, self.action, token, "intent-1")
        self.assertEqual(set(self.b.audit[0]), {"event", "run_id", "action_hash"})
        self.assertNotIn(token, str(self.b.audit))

    def test_invalid_budgets(self):
        with self.assertRaises(ValueError):
            self.execute(max_steps=0)

    def test_deadline_before_call(self):
        with patch("pi_runtime.time.monotonic", side_effect=[0.0, 6.0]):
            self.assertEqual(self.execute().status, "deadline_exceeded")

    def test_deadline_after_call(self):
        with patch("pi_runtime.time.monotonic", side_effect=[0.0, 0.0, 6.0]):
            self.assertEqual(self.execute().status, "deadline_exceeded")

    def test_budget_exhaustion_with_new_invalid_proposals(self):
        count = [0]
        def varying(*args):
            count[0] += 1
            return {"answer": "unsupported " + str(count[0]), "citations": ["A1"], "action": None}
        result = run("Tickets", self.p, self.repo, varying, self.b, max_steps=3)
        self.assertEqual((result.status, result.steps, count[0]), ("budget_exhausted", 3, 3))

    def test_broker_denial_reaches_public_status(self):
        result = self.execute(approval_token="not-a-token", operation_key="intent-1")
        self.assertEqual(result.status, "action_denied")

    def test_atomic_error_requires_reconciliation_status(self):
        token = self.b.issue_approval(self.p, self.action)
        self.b.fail_before_commit = True
        result = self.execute(approval_token=token, operation_key="intent-1")
        self.assertEqual(result.status, "action_error_reconcile")
        self.assertEqual(self.b.read(self.p, "T-1")["version"], 0)

    def test_persistent_approval_survives_broker_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "state.db")
            first = Broker(path, now=lambda: self.clock[0])
            first.seed("aster", "T-1")
            token = first.issue_approval(self.p, self.action)
            first.close()
            second = Broker(path, now=lambda: self.clock[0])
            try:
                result = second.execute(self.p, self.action, token, "intent-1")
                self.assertEqual(result["outcome"], "committed")
            finally:
                second.close()


class MathTests(unittest.TestCase):
    def test_rrf(self):
        result = reciprocal_rank_fusion([["A", "B", "C"], ["B", "D", "A"]])
        self.assertEqual(result[0][0], "B")

    def test_duplicate_ranks_rejected(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([["A", "A"]])

    def test_recall(self):
        self.assertEqual(recall_at_k(["A", "B", "C"], {"B", "D"}, 2), 0.5)

    def test_rr(self):
        self.assertEqual(reciprocal_rank(["A", "B"], {"B"}), 0.5)

    def test_wilson(self):
        lo, hi = wilson_interval(90, 100)
        self.assertAlmostEqual(lo, 0.8256, places=3)
        self.assertAlmostEqual(hi, 0.9448, places=3)

    def test_wilson_zero(self):
        lo, hi = wilson_interval(0, 100)
        self.assertAlmostEqual(lo, 0.0)
        self.assertLess(hi, 0.04)

    def test_kv(self):
        self.assertEqual(kv_cache_bytes(32, 8, 128, 8192, 4, 2), 4 * 2**30)

    def test_bad_dimensions(self):
        with self.assertRaises(ValueError):
            kv_cache_bytes(32, 8, 128, 8192, 0, 2)


if __name__ == "__main__":
    unittest.main()
