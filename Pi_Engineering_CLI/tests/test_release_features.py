import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import sys
from unittest.mock import patch

from test_product import SequenceModel, answer
from pi_engine import Engine
from pi_knowledge import Knowledge
from pi_operations import backup, restore, metrics
from pi_workspace import Workspace, UserError
from pi_workflow import run_workflow


class ReleaseFeatures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.temp.name)
        self.workspace.save(self.workspace.config())

    def tearDown(self):
        self.temp.cleanup()

    def test_knowledge_version_staleness_and_deletion(self):
        path = self.workspace.root / "policy.txt"
        path.write_text("The public release label is maple.")
        knowledge = Knowledge(self.workspace)
        first = knowledge.ingest("policy.txt")
        self.assertEqual(knowledge.search("release")[0]["version"], 1)
        self.assertTrue(knowledge.ingest("policy.txt")["unchanged"])
        path.write_text("The public release label is spruce.")
        self.assertEqual(knowledge.search("release"), [])
        self.assertEqual(knowledge.ingest("policy.txt")["version"], 2)
        self.assertIn("spruce", knowledge.search("release")[0]["body"])
        knowledge.forget_source(first["id"])
        self.assertEqual(knowledge.search("release"), [])

    def test_memory_provenance_expiry_replacement_and_forgetting(self):
        knowledge = Knowledge(self.workspace)
        saved = knowledge.remember("Release", "Release label maple", "operator", 1)
        self.assertEqual(knowledge.memories("maple")[0]["source"], "operator")
        updated = knowledge.remember("Release", "Release label spruce", "operator", 1, saved["id"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(knowledge.memories("maple"), [])
        with patch("pi_knowledge.time.time", return_value=time.time() + 86401):
            self.assertEqual(knowledge.memories(), [])
        knowledge.forget(saved["id"])
        self.assertEqual(knowledge.memories(), [])

    def test_workspace_memory_isolation(self):
        knowledge = Knowledge(self.workspace)
        knowledge.remember("Private", "workspace one", "operator")
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(Knowledge(Workspace(other)).memories(), [])

    def test_search_escapes_fts_operators(self):
        knowledge = Knowledge(self.workspace)
        self.assertEqual(knowledge.search('" OR * NEAR(foo)'), [])

    def test_metrics_uses_nearest_rank_p95(self):
        for elapsed in range(1, 21):
            self.workspace.record({
                "id": f"task_{elapsed}", "status": "completed",
                "steps": 0, "elapsed": elapsed, "calls": [],
            }, "created")
        self.assertEqual(metrics(self.workspace)["p95_elapsed_seconds"], 19)

    async def test_encrypted_backup_restore_and_wrong_key(self):
        await Engine(self.workspace, model=SequenceModel([answer()])).start("inspect")
        Knowledge(self.workspace).remember("Release", "maple", "operator")
        with tempfile.TemporaryDirectory() as other, patch.dict(os.environ, {"PI_TEST_BACKUP": "a-long-test-only-passphrase"}):
            destination = Path(other) / "backup.pi"
            backup(self.workspace, destination, "PI_TEST_BACKUP")
            self.assertNotIn(b"maple", destination.read_bytes())
            target = Path(other) / "restored"
            target.mkdir()
            restored = Workspace(target)
            restore(restored, destination, "PI_TEST_BACKUP")
            self.assertEqual(Knowledge(restored).memories()[0]["body"], "maple")
            self.assertEqual(metrics(restored)["states"], {"completed": 1})
            with self.assertRaises(UserError):
                restore(restored, destination, "PI_TEST_BACKUP")
            empty = Path(other) / "empty"
            empty.mkdir()
            with patch.dict(os.environ, {"PI_TEST_BACKUP": "different-long-passphrase"}):
                with self.assertRaises(UserError):
                    restore(Workspace(empty), destination, "PI_TEST_BACKUP")
            self.assertFalse((empty / ".pi-engineering").exists())

    async def test_parallel_branches_join_after_both_complete(self):
        class BarrierModel:
            def __init__(self):
                self.entered = 0
                self.ready = asyncio.Event()
            async def chat(self, messages, tools):
                self.entered += 1
                if self.entered == 2:
                    self.ready.set()
                await asyncio.wait_for(self.ready.wait(), 2)
                return answer("branch observed")
        path = self.workspace.root / "workflow.json"
        path.write_text(json.dumps({"nodes": {
            "left": {"agent": "engineer", "task": "left"},
            "right": {"agent": "engineer", "task": "right"},
            "join": {"agent": "reviewer", "task": "join", "depends_on": ["left", "right"]}}}))
        model = BarrierModel()
        flow = await run_workflow(self.workspace, path, Engine(self.workspace, model=model))
        self.assertEqual(flow["status"], "completed")
        self.assertEqual(model.entered, 3)
        request = self.workspace.task(flow["nodes"]["join"])["request"]
        self.assertIn("left", request)
        self.assertIn("right", request)

    async def test_registered_check_requires_approval_and_failure_is_not_success(self):
        config = self.workspace.config()
        config.checks["failing"] = [sys.executable, "-c", "raise SystemExit(2)"]
        self.workspace.save(config)
        engine = Engine(self.workspace)
        task = await engine.propose_tool("workspace_check", {"name": "failing"})
        self.assertEqual(task["status"], "awaiting_approval")
        task = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(task["status"], "verification_failed")
        self.assertEqual(task["calls"][0]["result"]["exit_code"], 2)

    async def test_registered_check_success_records_output(self):
        config = self.workspace.config()
        config.checks["passing"] = [sys.executable, "-c", "print('verified')"]
        self.workspace.save(config)
        engine = Engine(self.workspace)
        task = await engine.propose_tool("workspace_check", {"name": "passing"})
        task = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(task["status"], "completed")
        self.assertTrue(task["calls"][0]["result"]["check_passed"])
        self.assertIn("verified", task["calls"][0]["result"]["output"])

    async def test_check_environment_is_restricted(self):
        config = self.workspace.config()
        config.checks["env-probe"] = ["env"]
        self.workspace.save(config)
        engine = Engine(self.workspace)
        task = await engine.propose_tool("workspace_check", {"name": "env-probe"})
        with patch.dict(os.environ, {"PI_PROBE_SECRET": "never-leak"}):
            task = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(task["status"], "completed")
        output = task["calls"][0]["result"]["output"]
        self.assertIn("PATH=", output)
        self.assertNotIn("PI_PROBE_SECRET", output)
