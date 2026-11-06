"""Deterministic graph scheduling, recovery and offline-interface contracts."""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pi_app import main
from pi_engine import Engine
from pi_workflow import Workflow, identity, inspect_workflow, read_flow, run_workflow, save_flow
from pi_workspace import UserError, Workspace, fingerprint


def answer(text="observed"):
    return {"role": "assistant", "content": text, "tool_calls": []}


def node(task, deps=(), **extras):
    return dict(agent="engineer", task=task, depends_on=list(deps), **extras)


class GraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Workspace(self.temp.name)
        self.path = Path(self.temp.name) / "graph.json"

    def plan(self, nodes, **extra):
        self.path.write_text(json.dumps(dict(nodes=nodes, **extra)))
        return self.path

    async def test_child_releases_without_unrelated_slow_peer(self):
        child_started = asyncio.Event()
        order = []
        class Model:
            async def chat(self, messages, tools):
                task = messages[-1]["content"].split("\n")[0]
                if task == "slow":
                    await asyncio.wait_for(child_started.wait(), 1)
                if task == "child":
                    child_started.set()
                order.append(task)
                return answer()
        self.plan({"fast": node("fast"), "slow": node("slow"), "child": node("child", ["fast"])}, concurrency=2)
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(flow["status"], "completed")
        self.assertLess(order.index("child"), order.index("slow"))

    async def test_review_blocks_only_its_descendants_and_resume_reuses_success(self):
        calls = []
        class Model:
            async def chat(self, messages, tools):
                task = messages[1]["content"].split("\n")[0]
                calls.append(task)
                if task == "write" and messages[-1]["role"] == "user":
                    return {"role": "assistant", "content": "", "tool_calls": [{"function": {
                        "name": "workspace_write", "arguments": {"path": "out.txt", "content": "ok", "expected_hash": "missing"}}}]}
                return answer()
        self.plan({"a": node("write"), "b": node("read"), "c": node("child", ["b"]), "d": node("join", ["a", "c"])})
        engine = Engine(self.workspace, model=Model())
        flow = await run_workflow(self.workspace, self.path, engine)
        self.assertEqual(flow["status"], "awaiting_approval")
        self.assertEqual(self.workspace.task(flow["nodes"]["c"])["status"], "completed")
        self.assertNotIn("d", flow["nodes"])
        self.assertFalse((self.workspace.root / "out.txt").exists())
        explained = inspect_workflow(self.workspace, self.path, True)
        self.assertEqual(next(n for n in explained["nodes"] if n["node"] == "a")["reason"], "operator_approval_required")
        task = self.workspace.task(flow["nodes"]["a"])
        await engine.advance(task["id"], task["calls"][0]["hash"])
        resumed = await run_workflow(self.workspace, self.path, engine)
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(calls.count("child"), 1)
        self.assertEqual(calls.count("read"), 1)
        self.assertEqual((self.workspace.root / "out.txt").read_text(), "ok")

    async def test_resources_serialize_and_priority_is_deterministic(self):
        active = 0
        maximum = 0
        order = []
        class Model:
            async def chat(self, messages, tools):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                order.append(messages[1]["content"])
                await asyncio.sleep(.01)
                active -= 1
                return answer()
        self.plan({"z": node("z", resources=["repo"], priority=10),
                   "b": node("b", resources=["repo"]), "a": node("a", resources=["repo"])}, version=2)
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(flow["status"], "completed")
        self.assertEqual(maximum, 1)
        self.assertEqual(order, ["z", "a", "b"])

    async def test_concurrency_bound_and_all_nodes_finish(self):
        active = 0
        maximum = 0
        class Model:
            async def chat(self, messages, tools):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(.01)
                active -= 1
                return answer()
        self.plan({str(i): node(str(i)) for i in range(7)}, concurrency=2)
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(flow["status"], "completed")
        self.assertEqual(maximum, 2)
        self.assertEqual(len(flow["nodes"]), 7)

    async def test_resource_lock_applies_to_manual_resume(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "out.txt", "content": "ok", "expected_hash": "missing"})
        task["workflow_resources"] = ["repo"]
        self.workspace.record(task, "workflow_bound")
        with self.workspace.lock("resource_" + fingerprint("repo")):
            with self.assertRaises(UserError):
                await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
        self.assertFalse((self.workspace.root / "out.txt").exists())
        result = await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(result["status"], "completed")

    async def test_external_resource_conflict_is_bounded_and_other_branch_continues(self):
        class Model:
            async def chat(self, messages, tools):
                return answer()
        self.plan({"a": node("locked", resources=["repo"]), "b": node("independent")}, version=2)
        with self.workspace.lock("resource_" + fingerprint("repo")):
            result = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.workspace.task(result["nodes"]["b"])["status"], "completed")
        resumed = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(resumed["status"], "completed")

    async def test_cancellation_drains_children_and_preserves_recovery(self):
        entered = asyncio.Event()
        stopped = []
        class Model:
            async def chat(self, messages, tools):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.append(True)
        self.plan({"a": node("a"), "b": node("b", ["a"])})
        execution = asyncio.create_task(run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model())))
        await entered.wait()
        execution.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await execution
        self.assertEqual(stopped, [True])
        flow = read_flow(self.workspace, identity(self.path, Workflow.model_validate_json(self.path.read_text())))
        self.assertEqual(flow["status"], "interrupted")
        self.assertNotIn("b", flow["nodes"])
        self.assertEqual(self.workspace.task(flow["nodes"]["a"])["status"], "interrupted")
        class Finish:
            async def chat(self, messages, tools):
                return answer()
        self.assertEqual((await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Finish())))["status"], "completed")

    async def test_failure_does_not_release_join_but_independent_work_finishes(self):
        class Model:
            async def chat(self, messages, tools):
                if messages[1]["content"] == "fail":
                    raise UserError("fixture failure")
                return answer()
        self.plan({"a": node("fail"), "b": node("good"), "c": node("join", ["a", "b"])})
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(flow["status"], "failed")
        self.assertNotIn("c", flow["nodes"])
        self.assertEqual(self.workspace.task(flow["nodes"]["b"])["status"], "completed")

    async def test_completed_config_drift_refused_before_model(self):
        class Model:
            async def chat(self, messages, tools):
                return answer()
        self.plan({"a": node("a")})
        await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        config = self.workspace.config()
        config.agents["engineer"].role = "changed"
        self.workspace.save(config)
        with self.assertRaisesRegex(UserError, "configuration changed"):
            await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        view = inspect_workflow(self.workspace, self.path, True)
        self.assertEqual(view["status"], "failed")
        self.assertFalse(any(n["ready"] for n in view["nodes"]))

    async def test_legacy_id_and_migration_do_not_repeat_completed_task(self):
        class Model:
            async def chat(self, messages, tools):
                return answer()
        self.plan({"a": node("a")})
        plan = Workflow.model_validate_json(self.path.read_text())
        original = {"version": 1, "concurrency": 4, "nodes": {"a": node("a")}}
        self.assertEqual(identity(self.path, plan), "flow_" + fingerprint({"path": str(self.path.resolve()), "plan": original})[:20])
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        for field in ("schema_version", "workspace_hash", "revision"):
            del flow[field]
        save_flow(self.workspace, flow)
        with patch.object(Engine, "advance", side_effect=AssertionError("must not repeat")):
            result = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(len(self.workspace.runs()), 1)

    async def test_wrong_workspace_or_schema_is_refused(self):
        class Model:
            async def chat(self, messages, tools):
                return answer()
        self.plan({"a": node("a")})
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        for field, value in (("workspace_hash", "wrong"), ("schema_version", 999), ("revision", "wrong")):
            with self.subTest(field=field):
                save_flow(self.workspace, dict(flow, **{field: value}))
                with self.assertRaisesRegex(UserError, "incompatible"):
                    await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))

    async def test_invalid_graphs_create_no_state(self):
        fixtures = [dict(nodes={}), dict(nodes={"a": node("x", ["missing"])}),
                    dict(nodes={"a": node("x", ["a"])}), dict(nodes={"a": node("x", priority=1)}),
                    dict(nodes={"a": node("x", resources=["x", "x"])}, version=2),
                    dict(nodes={"a": node("x", resources=["bad\x1bname"])}, version=2),
                    dict(nodes={"a": node("x", ["b", "b"]), "b": node("b")}),
                    dict(nodes={"a": dict(agent="unknown", task="x")}),
                    dict(nodes={"a": dict(node("x"), join="any")}),
                    dict(nodes={"a": node("x")}, concurrency=0)]
        for fixture in fixtures:
            self.path.write_text(json.dumps(fixture))
            with self.subTest(fixture=fixture), self.assertRaises(UserError):
                await run_workflow(self.workspace, self.path, Engine(self.workspace))
        self.path.write_text('{"nodes":{"a":{"agent":"engineer","task":"x"},"a":{"agent":"engineer","task":"y"}}}')
        with self.assertRaises(UserError):
            inspect_workflow(self.workspace, self.path)
        self.assertFalse(self.workspace.directory.exists())

    async def test_offline_cli_json_no_models_tools_or_state(self):
        self.plan({"a": node("private task text"), "b": node("b", ["a"])})
        # main owns its event loop; execute it in a thread outside this test loop.
        for option in ("--validate", "--explain"):
            stdout = io.StringIO()
            with patch.object(Engine, "advance", side_effect=AssertionError("external call")), contextlib.redirect_stdout(stdout):
                code = await asyncio.to_thread(main, ["workflow", str(self.path), option, "--json", "--workspace", self.temp.name])
            data = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(data["offline"])
            self.assertNotIn("private task text", stdout.getvalue())
            self.assertEqual(data["nodes"][1]["blockers"], [{"node": "a", "status": "pending"}])
        self.assertFalse(self.workspace.directory.exists())

    async def test_unknown_dispatch_is_not_retried_or_consumed(self):
        class Propose:
            async def chat(self, messages, tools):
                return {"role": "assistant", "content": "", "tool_calls": [{"function": {
                    "name": "workspace_write", "arguments": {"path": "out.txt", "content": "ok", "expected_hash": "missing"}}}]}
        self.plan({"a": node("write"), "b": node("join", ["a"])})
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Propose()))
        task = self.workspace.task(flow["nodes"]["a"])
        task["calls"][0]["status"] = "executing"
        task.update(node="execute", status="running")
        self.workspace.record(task, "execute")
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Propose()))
        self.assertEqual(flow["status"], "unresolved")
        self.assertNotIn("b", flow["nodes"])
        self.assertFalse((self.workspace.root / "out.txt").exists())
        again = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Propose()))
        self.assertEqual(again, flow)

    async def test_exhausted_step_budget_blocks_descendants(self):
        class Model:
            async def chat(self, messages, tools):
                return {"role": "assistant", "content": "", "tool_calls": [{"function": {
                    "name": "workspace_files", "arguments": {}}}]}
        config = self.workspace.config()
        config.agents["engineer"].max_steps = 1
        self.workspace.save(config)
        self.plan({"a": node("a"), "b": node("b", ["a"])})
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
        self.assertEqual(flow["status"], "budget_exhausted")
        self.assertNotIn("b", flow["nodes"])

    async def test_plan_revision_creates_fresh_unapproved_actions(self):
        class Propose:
            async def chat(self, messages, tools):
                return {"role": "assistant", "content": "", "tool_calls": [{"function": {
                    "name": "workspace_write", "arguments": {"path": "out.txt", "content": "ok", "expected_hash": "missing"}}}]}
        self.plan({"a": node("first")})
        first = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Propose()))
        self.plan({"a": node("changed")})
        second = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Propose()))
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["nodes"]["a"], second["nodes"]["a"])
        self.assertEqual(second["status"], "awaiting_approval")
        self.assertFalse(self.workspace.task(second["nodes"]["a"])["calls"][0].get("approved"))

    async def test_state_and_plan_errors_do_not_expose_payloads(self):
        self.path.write_text(json.dumps({"nodes": {"a": dict(node("secret payload"), priority="invalid")}}))
        with self.assertRaises(UserError) as caught:
            inspect_workflow(self.workspace, self.path)
        self.assertNotIn("secret payload", str(caught.exception))
        self.assertIn("integer", str(caught.exception))

    async def test_partial_multi_resource_acquisition_releases_first_lock(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "out.txt", "content": "ok", "expected_hash": "missing"})
        task["workflow_resources"] = ["a", "b"]
        self.workspace.record(task, "workflow_bound")
        with self.workspace.lock("resource_" + fingerprint("b")):
            with self.assertRaises(UserError):
                await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
            with self.workspace.lock("resource_" + fingerprint("a")):
                pass
        self.assertFalse(self.workspace.task(task["id"])["calls"][0].get("approved"))

    async def test_resource_lock_is_shared_across_processes(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "out.txt", "content": "ok", "expected_hash": "missing"})
        task["workflow_resources"] = ["repo"]
        self.workspace.record(task, "workflow_bound")
        script = ("import sys\nfrom pi_workspace import Workspace, fingerprint\n"
                  "with Workspace(sys.argv[1]).lock('resource_' + fingerprint('repo')):\n"
                  " print('ready', flush=True)\n sys.stdin.read(1)\n")
        process = subprocess.Popen([sys.executable, "-c", script, self.temp.name],
                                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 15), "ready\n")
            with self.assertRaisesRegex(UserError, "resource is busy"):
                await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
        finally:
            process.communicate("x", timeout=3)
        self.assertEqual(process.returncode, 0)
        self.assertFalse((self.workspace.root / "out.txt").exists())

    async def test_cancel_after_dispatch_preserves_unknown_effect(self):
        dispatched = asyncio.Event()
        class Model:
            async def chat(self, messages, tools):
                return {"role": "assistant", "content": "", "tool_calls": [{"function": {
                    "name": "workspace_files", "arguments": {}}}]}
        async def delayed(*args):
            dispatched.set()
            await asyncio.Event().wait()
        self.plan({"a": node("a"), "b": node("b", ["a"])})
        with patch("pi_tools.ToolBroker.call", side_effect=delayed) as tool:
            execution = asyncio.create_task(run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model())))
            await asyncio.wait_for(dispatched.wait(), 1)
            execution.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await execution
            flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Model()))
            self.assertEqual(flow["status"], "unresolved")
            self.assertNotIn("b", flow["nodes"])
            self.assertEqual(tool.call_count, 1)

    async def test_manual_approval_cannot_cross_workspace_binding(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "out.txt", "content": "ok", "expected_hash": "missing"})
        task["workflow_binding"] = {"workspace_hash": fingerprint("different workspace")}
        self.workspace.record(task, "workflow_bound")
        with self.assertRaisesRegex(UserError, "different workspace"):
            await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
        self.assertFalse((self.workspace.root / "out.txt").exists())
