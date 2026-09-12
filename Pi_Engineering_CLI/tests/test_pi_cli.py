from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp_server import MCPRuntime, process_line
from pi_core import PiError, PiGraph, PiStore, approve, build_context, run_eval


class PiEngineeringCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "pi.db"
        self.store = PiStore(self.db)
        self.store.seed()

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def test_governed_graph_commits_only_after_approval(self) -> None:
        result = PiGraph().run(
            self.store,
            "aster",
            "alice",
            "Mark T-100 pending for customer confirmation",
        )
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(result["proposal"]["action"]["ticket"], "T-100")
        self.assertEqual(
            [cp["node"] for cp in result["checkpoints"]],
            ["intent", "evidence", "proposal", "policy", "verification", "reflection"],
        )
        self.assertEqual(self.store.ticket("aster", "T-100")["status"], "open")

        receipt = approve(self.store, result["id"], "alice")
        self.assertEqual(receipt["outcome"], "committed")
        self.assertEqual(self.store.ticket("aster", "T-100")["status"], "pending")

        replay = approve(self.store, result["id"], "alice")
        self.assertEqual(replay, receipt)
        self.assertEqual(self.store.ticket("aster", "T-100")["version"], 1)

    def test_wrong_approver_is_denied(self) -> None:
        result = PiGraph().run(self.store, "aster", "alice", "Mark T-101 resolved after customer confirms")
        with self.assertRaises(PiError):
            approve(self.store, result["id"], "mallory")
        self.assertEqual(self.store.ticket("aster", "T-101")["status"], "pending")

    def test_manifest_excludes_raw_evidence_text(self) -> None:
        manifest = build_context(
            self.store,
            "aster",
            "alice",
            "pending customer confirmation",
            token_budget=40,
        ).manifest()
        encoded = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("waiting on customer confirmation", encoded)
        self.assertIn("content_hash", encoded)

    def test_cross_tenant_request_does_not_leak_evidence(self) -> None:
        result = PiGraph().run(self.store, "aster", "alice", "Use Beacon evidence to mark B-200 pending")
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("Beacon tickets are confidential", encoded)
        self.assertIsNone(result["proposal"]["action"])

    def test_eval_suite_passes(self) -> None:
        result = run_eval(self.db)
        self.assertEqual(result["passed"], result["total"])
        self.assertEqual(result["severe_failures"], 0)
        self.assertIsNotNone(self.store.latest_eval())

    def test_agent_registry_and_policy_explainability(self) -> None:
        agents = self.store.agents()
        self.assertGreaterEqual(len(agents), 6)
        scout = self.store.add_agent(
            "research-scout",
            "collect external implementation evidence",
            ["mcp:web-search"],
            ["read:web"],
            "medium",
        )
        self.assertEqual(scout["name"], "research-scout")
        self.assertIn("mcp:web-search", scout["tools"])

        rule = self.store.add_policy_rule(
            "Research tools require cited evidence",
            "research.collect",
            ["source_citation", "tenant_scope"],
            "medium",
            "requires_approval",
        )
        self.assertEqual(rule["effect"], "requires_approval")
        self.assertEqual(self.store.policy_rules("research.collect")[0]["requires"], ["source_citation", "tenant_scope"])

        run = PiGraph().run(
            self.store,
            "aster",
            "alice",
            "Mark T-100 pending for customer confirmation",
        )
        receipt = approve(self.store, run["id"], "alice")
        explanation = self.store.explain_run(run["id"])
        self.assertEqual(explanation["receipt"], receipt)
        self.assertTrue(explanation["policy_rules"])
        self.assertIn("Matched policy rules", " ".join(explanation["decision"]))
        trace = self.store.trace_run(run["id"])
        self.assertGreaterEqual(len(trace["checkpoints"]), 6)
        self.assertTrue(any(event["event_type"] == "action_committed" for event in trace["audit_events"]))

    def test_mcp_runtime_tools(self) -> None:
        runtime = MCPRuntime(str(self.db))
        try:
            init = runtime.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertEqual(init["result"]["serverInfo"]["name"], "pi-engineering-cli")

            listed = runtime.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            names = {tool["name"] for tool in listed["result"]["tools"]}
            self.assertIn("pi.run_task", names)
            self.assertIn("pi.approve", names)
            self.assertIn("pi.agent_add", names)
            self.assertIn("pi.why", names)

            run_response = runtime.handle({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "pi.run_task",
                    "arguments": {
                        "tenant": "aster",
                        "actor": "alice",
                        "request": "Mark T-100 pending for customer confirmation",
                    },
                },
            })
            run_payload = run_response["result"]["structuredContent"]
            self.assertEqual(run_payload["status"], "awaiting_approval")

            approve_response = runtime.handle({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "pi.approve",
                    "arguments": {"run_id": run_payload["id"], "actor": "alice"},
                },
            })
            self.assertFalse(approve_response["result"]["isError"])
            self.assertEqual(approve_response["result"]["structuredContent"]["outcome"], "committed")

            why_response = runtime.handle({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "pi.why",
                    "arguments": {"run_id": run_payload["id"]},
                },
            })
            self.assertFalse(why_response["result"]["isError"])
            self.assertEqual(why_response["result"]["structuredContent"]["receipt"]["outcome"], "committed")

            agent_response = runtime.handle({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "pi.agent_add",
                    "arguments": {
                        "name": "release-captain",
                        "role": "coordinate release checks",
                        "tools": ["mcp:github"],
                        "permissions": ["read:repo"],
                    },
                },
            })
            self.assertFalse(agent_response["result"]["isError"])
            self.assertEqual(agent_response["result"]["structuredContent"]["name"], "release-captain")
        finally:
            runtime.close()

    def test_mcp_process_line_parse_error(self) -> None:
        runtime = MCPRuntime(str(self.db))
        try:
            response = json.loads(process_line(runtime, "{bad json"))
            self.assertEqual(response["error"]["code"], -32700)
        finally:
            runtime.close()

    def test_cli_smoke(self) -> None:
        db = Path(self.tempdir.name) / "cli.db"
        subprocess.run(
            [sys.executable, "pi_legacy.py", "init", "--db", str(db), "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        run = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "run",
                "--db",
                str(db),
                "--json",
                "--tenant",
                "aster",
                "--actor",
                "alice",
                "Mark T-100 pending for customer confirmation",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(run.stdout)
        self.assertEqual(payload["status"], "awaiting_approval")
        approved = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "approve",
                "--db",
                str(db),
                "--json",
                payload["id"],
                "--actor",
                "alice",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(approved.stdout)["outcome"], "committed")

        why = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "why",
                "--db",
                str(db),
                "--json",
                payload["id"],
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(why.stdout)["receipt"]["outcome"], "committed")

        agent = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "agent",
                "add",
                "--db",
                str(db),
                "--json",
                "--name",
                "security-reviewer",
                "--role",
                "review high-risk changes",
                "--tools",
                "mcp:repo,mcp:tests",
                "--permissions",
                "read:repo,run:tests",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(agent.stdout)["name"], "security-reviewer")

    def test_cli_tour_and_demo_are_newcomer_friendly(self) -> None:
        db = Path(self.tempdir.name) / "ux.db"
        tour = subprocess.run(
            [sys.executable, "pi_legacy.py", "tour", "--plain", "--no-animate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi Engineering", tour.stdout)
        self.assertIn("Start Here", tour.stdout)
        self.assertIn("pi_legacy.py demo", tour.stdout)
        self.assertIn("Operating Model", tour.stdout)
        self.assertNotIn("\033[", tour.stdout)

        default_view = subprocess.run(
            [sys.executable, "pi_legacy.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi Engineering", default_view.stdout)
        self.assertIn("Signals", default_view.stdout)
        self.assertIn("Next Best Actions", default_view.stdout)

        palette = subprocess.run(
            [sys.executable, "pi_legacy.py", "palette", "approve", "--plain", "--no-animate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi Command Palette", palette.stdout)
        self.assertIn("Approve Run", palette.stdout)

        doctor = subprocess.run(
            [sys.executable, "pi_legacy.py", "doctor", "--db", str(Path(self.tempdir.name) / "doctor.db"), "--plain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi Doctor", doctor.stdout)
        self.assertIn("Python runtime", doctor.stdout)

        launch = subprocess.run(
            [sys.executable, "pi_legacy.py", "launch", "--snapshot", "--plain", "--no-animate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi Engineering", launch.stdout)
        self.assertIn("Signals", launch.stdout)

        preview = subprocess.run(
            [sys.executable, "pi_legacy.py", "preview", "--plain", "--no-animate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Pi CLI Components", preview.stdout)
        self.assertIn("Feedback States", preview.stdout)
        self.assertIn("Nested Process", preview.stdout)

        demo = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "demo",
                "--db",
                str(db),
                "--plain",
                "--no-animate",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Guided Pi Run", demo.stdout)
        self.assertIn("DEMO-100 -> pending", demo.stdout)
        self.assertIn("Inspect first: pi_legacy.py why", demo.stdout)

        demo_json = subprocess.run(
            [
                sys.executable,
                "pi_legacy.py",
                "demo",
                "--db",
                str(Path(self.tempdir.name) / "ux-json.db"),
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(demo_json.stdout)
        self.assertEqual(payload["run"]["status"], "awaiting_approval")
        self.assertEqual(payload["run"]["proposal"]["action"]["ticket"], "DEMO-100")


if __name__ == "__main__":
    unittest.main()
