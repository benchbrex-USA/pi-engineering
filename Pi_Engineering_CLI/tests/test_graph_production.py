"""P0/P1 graph production seals: side effects, inspection schema, resume matrix, packs."""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_app import main
from pi_engine import Engine
from pi_workflow import inspect_workflow, load_plan, run_workflow
from pi_workspace import Workspace
from pi_profile import apply_preset, list_presets, load_preset


def node(task="work", depends_on=None, priority=0, resources=None):
    return {"agent": "engineer", "task": task, "depends_on": depends_on or [],
            "priority": priority, "resources": resources or []}


class GraphProductionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.temp.name)
        self.config = self.workspace.config()
        self.workspace.save(self.config)
        self.path = Path(self.temp.name) / "plan.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_plan(self, nodes, version=2, concurrency=2):
        self.path.write_text(json.dumps({"version": version, "concurrency": concurrency, "nodes": nodes}))

    def test_inspection_schema_version_present(self):
        self.write_plan({"a": node("a"), "b": node("b", ["a"])})
        data = inspect_workflow(self.workspace, self.path, False)
        self.assertEqual(data["inspection_schema"], 1)
        self.assertEqual(data["kind"], "workflow_inspection")
        self.assertTrue(data["offline"])

    def test_validate_writes_no_sqlite_and_explain_is_readonly(self):
        self.write_plan({"a": node("secret-task-payload"), "b": node("b", ["a"])})
        state = Path(self.workspace.directory)
        before = list(state.glob("*")) if state.exists() else []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["workflow", str(self.path), "--validate", "--json", "--workspace", self.temp.name])
        self.assertEqual(code, 0)
        self.assertFalse((state / "tasks.sqlite3").exists())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["workflow", str(self.path), "--explain", "--json", "--workspace", self.temp.name])
        self.assertEqual(code, 0)
        if (state / "tasks.sqlite3").exists():
            # explain may open readonly; ensure no workflows/tasks inserted by validate/explain alone
            with sqlite3.connect(state / "tasks.sqlite3") as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "workflows" in tables:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM workflows").fetchone()[0], 0)
                if "tasks" in tables:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_product_workflow_packs_load(self):
        for path in sorted((ROOT / "workflows").glob("*.json")):
            plan = load_plan(path, self.config)
            self.assertGreaterEqual(len(plan.nodes), 1)
            self.assertLessEqual(len(plan.nodes), 32)

    def test_persona_default_workflows_exist_and_load(self):
        for name in list_presets():
            data, _ = load_preset(name)
            rel = data.get("default_workflow")
            self.assertTrue(rel, name)
            path = ROOT / rel
            self.assertTrue(path.is_file(), f"missing {path}")
            load_plan(path, self.config)

    def test_resume_matrix_dependency_readiness(self):
        """Table-driven: child ready only when parent completed; joins stay all-success."""
        statuses = [
            ("completed", True, "ready"),
            ("awaiting_approval", False, "dependencies_not_successful"),
            ("unresolved", False, "dependencies_not_successful"),
            ("failed", False, "dependencies_not_successful"),
            ("rejected", False, "dependencies_not_successful"),
            ("budget_exhausted", False, "dependencies_not_successful"),
            ("interrupted", False, "dependencies_not_successful"),
            ("running", False, "dependencies_not_successful"),
            ("pending", False, "dependencies_not_successful"),
        ]
        from pi_workflow import node_view

        class FakeTask(dict):
            pass

        for parent_status, child_ready, reason in statuses:
            plan_nodes = {
                "parent": type("N", (), {"depends_on": [], "priority": 0, "resources": []})(),
                "child": type("N", (), {"depends_on": ["parent"], "priority": 0, "resources": []})(),
            }
            # Use real plan via load_plan for fidelity
            self.write_plan({
                "parent": node("p"),
                "child": node("c", ["parent"]),
            })
            plan = load_plan(self.path, self.config)
            tasks = {
                "parent": {"id": "t_parent", "status": parent_status},
            }
            rows = {row["node"]: row for row in node_view(plan, tasks)}
            self.assertEqual(rows["child"]["ready"], child_ready, parent_status)
            if not child_ready:
                self.assertEqual(rows["child"]["reason"], reason, parent_status)
                self.assertEqual(rows["child"]["blockers"], [{"node": "parent", "status": parent_status}])
            else:
                self.assertTrue(rows["child"]["ready"])

    async def test_all_success_join_blocks_on_failed_sibling(self):
        # Exhaust step budget on leaves so join cannot complete (all-success).
        self.config.agents["engineer"].max_steps = 1
        self.workspace.save(self.config)

        class Loop:
            async def chat(self, messages, tools):
                return {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "workspace_files", "arguments": {}}}]}

        self.write_plan({
            "a": node("a"),
            "b": node("b"),
            "join": node("join", ["a", "b"]),
        }, concurrency=2)
        flow = await run_workflow(self.workspace, self.path, Engine(self.workspace, model=Loop()))
        self.assertNotEqual(flow.get("status"), "completed")
        self.assertNotIn("join", flow.get("nodes", {}))
        for leaf in ("a", "b"):
            if leaf in flow.get("nodes", {}):
                self.assertEqual(self.workspace.task(flow["nodes"][leaf])["status"], "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
