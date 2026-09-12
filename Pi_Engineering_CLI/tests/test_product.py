from __future__ import annotations

import asyncio
import io
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from rich.console import Console

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_engine import Engine, GRAPH
from pi_terminal import Terminal, clean
from pi_tools import ToolBroker, OllamaModel, file_path
from pi_workspace import Workspace, UserError, ServerSettings, fingerprint
from pi_workflow import run_workflow


class SequenceModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    async def chat(self, messages, tools):
        self.calls += 1
        return next(self.responses)


def answer(text="Evidence reviewed"):
    return {"role": "assistant", "content": text, "tool_calls": []}


def tool(name, arguments):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}]}


class ProductTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.temp.name)
        self.config = self.workspace.config()
        self.workspace.save(self.config)

    def tearDown(self):
        self.temp.cleanup()

    async def test_real_file_observation_and_graph(self):
        (self.workspace.root / "source.txt").write_text("actual evidence")
        model = SequenceModel([tool("workspace_read", {"path": "source.txt"}), answer()])
        task = await Engine(self.workspace, model=model).start("Inspect source.txt")
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["calls"][0]["result"]["content"], "actual evidence")
        nodes = [e["kind"] for e in self.workspace.events(task["id"]) if e["kind"] in GRAPH]
        self.assertEqual(nodes, ["intake", "context", "propose", "policy", "execute", "verify", "propose", "complete"])

    async def test_write_requires_exact_approval_survives_restart_and_replays_once(self):
        model = SequenceModel([tool("workspace_write", {"path": "new.txt", "content": "new", "expected_hash": "missing"})])
        task = await Engine(self.workspace, model=model).start("Write new.txt")
        self.assertEqual(task["status"], "awaiting_approval")
        self.assertFalse((self.workspace.root / "new.txt").exists())
        engine = Engine(self.workspace, model=SequenceModel([answer()]))
        with self.assertRaises(UserError):
            await engine.advance(task["id"], "wrong")
        completed = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual((self.workspace.root / "new.txt").read_text(), "new")
        replay = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(replay["calls"], completed["calls"])
        self.assertEqual(completed["calls"][0]["receipt"]["verification"], "file_readback")

    async def test_changed_file_is_not_overwritten(self):
        path = self.workspace.root / "source.txt"
        path.write_text("before")
        task = await Engine(self.workspace, model=SequenceModel([tool("workspace_write", {
            "path": "source.txt", "content": "after", "expected_hash": fingerprint("before")})])).start("Edit")
        path.write_text("concurrent edit")
        task = await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(path.read_text(), "concurrent edit")
        self.assertEqual(task["status"], "unresolved")

    async def test_config_change_invalidates_approval(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "new.txt", "content": "new", "expected_hash": "missing"})
        self.config.agents["engineer"].tools.remove("workspace_write")
        self.workspace.save(self.config)
        with self.assertRaises(UserError):
            await Engine(self.workspace).advance(task["id"], task["calls"][0]["hash"])

    async def test_unavailable_tool_cannot_execute(self):
        task = await Engine(self.workspace, model=SequenceModel([tool("shell", {"command": "touch bad"})])).start("Do work")
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["calls"], [])

    async def test_invalid_schema_cannot_execute(self):
        task = await Engine(self.workspace, model=SequenceModel([tool("workspace_write", {"path": "new"})])).start("Do work")
        self.assertEqual(task["status"], "failed")
        self.assertFalse((self.workspace.root / "new").exists())

    async def test_repetition_stops_loop(self):
        call = tool("workspace_files", {})
        task = await Engine(self.workspace, model=SequenceModel([call, call])).start("Inspect")
        self.assertEqual(task["status"], "failed")
        self.assertEqual(len(task["calls"]), 1)

    async def test_read_after_write_is_allowed_for_verification(self):
        (self.workspace.root / "source.txt").write_text("before")
        read = tool("workspace_read", {"path": "source.txt"})
        model = SequenceModel([read, tool("workspace_write", {
            "path": "source.txt", "content": "after", "expected_hash": fingerprint("before")}), read, answer()])
        engine = Engine(self.workspace, model=model)
        task = await engine.start("Update and verify")
        self.assertEqual(task["status"], "awaiting_approval")
        task = await engine.advance(task["id"], task["calls"][-1]["hash"])
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["calls"][-1]["result"]["content"], "after")

    async def test_step_budget(self):
        self.config.agents["engineer"].max_steps = 1
        self.workspace.save(self.config)
        task = await Engine(self.workspace, model=SequenceModel([tool("workspace_files", {})])).start("Inspect")
        self.assertEqual(task["status"], "budget_exhausted")

    async def test_interrupted_dispatch_never_replays(self):
        task = await Engine(self.workspace).propose_tool("workspace_write", {
            "path": "new.txt", "content": "new", "expected_hash": "missing"})
        task["calls"][0]["status"] = "executing"
        task["node"] = "execute"
        task["status"] = "running"
        self.workspace.record(task, "execute")
        task = await Engine(self.workspace).advance(task["id"])
        self.assertEqual(task["status"], "unresolved")
        self.assertFalse((self.workspace.root / "new.txt").exists())

    async def test_reject_terminal_state(self):
        engine = Engine(self.workspace)
        task = await engine.propose_tool("workspace_write", {"path": "new.txt", "content": "x", "expected_hash": "missing"})
        engine.reject(task["id"])
        result = await engine.advance(task["id"], task["calls"][0]["hash"])
        self.assertEqual(result["status"], "rejected")

    async def test_workflow_dependencies_and_resume(self):
        path = self.workspace.root / "workflow.json"
        path.write_text(json.dumps({"nodes": {
            "inspect": {"agent": "researcher", "task": "inspect"},
            "review": {"agent": "reviewer", "task": "review", "depends_on": ["inspect"]}}}))
        model = SequenceModel([answer("observed"), answer("reviewed")])
        engine = Engine(self.workspace, model=model)
        flow = await run_workflow(self.workspace, path, engine)
        self.assertEqual(flow["status"], "completed")
        self.assertIn("observed", self.workspace.task(flow["nodes"]["review"])["request"])
        self.assertEqual(await run_workflow(self.workspace, path, engine), flow)
        self.assertEqual(model.calls, 2)

    async def test_workflow_cycle_no_tasks(self):
        path = self.workspace.root / "workflow.json"
        path.write_text(json.dumps({"nodes": {"a": {"agent": "engineer", "task": "x", "depends_on": ["a"]}}}))
        with self.assertRaises(UserError):
            await run_workflow(self.workspace, path, Engine(self.workspace))
        self.assertEqual(self.workspace.runs(), [])

    async def test_sdk_stdio_roundtrip_and_no_approval_tool(self):
        self.config.servers["pi"] = ServerSettings(command=sys.executable,
            args=[str(ROOT / "pi.py"), "--workspace", self.temp.name, "mcp-server"], read_tools=["pi_graph"])
        async with ToolBroker(self.workspace, self.config) as broker:
            self.assertIn("pi__pi_graph", broker.tools)
            self.assertNotIn("pi__pi_approve", broker.tools)
            result = await broker.call("pi__pi_graph", {})
            self.assertFalse(result["verified"])
            self.assertIn("intake", str(result))

    async def test_sdk_http_roundtrip(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "tests/http_mcp_fixture.py"),
            str(port), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(0.05)
            else:
                self.fail("MCP HTTP fixture did not start")
            self.config.servers["http"] = ServerSettings(transport="http", url=f"http://127.0.0.1:{port}/mcp")
            async with ToolBroker(self.workspace, self.config) as broker:
                self.assertFalse(broker.tools["http__inspect_value"]["read"])
                result = await broker.call("http__inspect_value", {"value": "contract-boundary"})
                self.assertIn("contract-boundary", str(result))
                with self.assertRaises(UserError):
                    await broker.call("http__inspect_value", {"invalid": 1})
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()

    async def test_model_http_contract_and_private_reasoning_projection(self):
        received = []
        async def serve(reader, writer):
            header = await reader.readuntil(b"\r\n\r\n")
            length = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n")
                          if line.lower().startswith(b"content-length:"))
            received.append(json.loads(await reader.readexactly(length)))
            body = json.dumps({"message": {"content": "observed", "thinking": "private", "tool_calls": []}}).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        try:
            self.config.model.endpoint = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            self.config.model.model = "contract-model"
            response = await OllamaModel(self.config.model).chat([{"role": "user", "content": "inspect"}], [])
            self.assertEqual(response["content"], "observed")
            self.assertNotIn("thinking", response)
            self.assertEqual(received[0]["model"], "contract-model")
            self.assertFalse(received[0]["stream"])
        finally:
            server.close()
            await server.wait_closed()

    async def test_cancel_model_call_then_resume_checkpoint(self):
        entered = asyncio.Event()
        class SlowModel:
            async def chat(self, messages, tools):
                entered.set()
                await asyncio.sleep(60)
        operation = asyncio.create_task(Engine(self.workspace, model=SlowModel()).start("Inspect"))
        await entered.wait()
        operation.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await operation
        saved = self.workspace.runs()[0]
        self.assertEqual(saved["status"], "interrupted")
        resumed = await Engine(self.workspace, model=SequenceModel([answer()])).advance(saved["id"])
        self.assertEqual(resumed["status"], "completed")

    def test_global_flags_after_commands(self):
        result = subprocess.run([sys.executable, str(ROOT / "pi.py"), "graph", "--json", "--workspace", self.temp.name],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), GRAPH)

    def test_path_escape_and_secrets_rejected(self):
        for path in ["../private", "/etc/passwd", ".env", ".git/config", ".pi-engineering/config.json", "key.pem"]:
            with self.subTest(path=path), self.assertRaises(UserError):
                file_path(self.workspace, path)
        (self.workspace.root / "link").symlink_to("/tmp")
        with self.assertRaises(UserError):
            file_path(self.workspace, "link/x")

    def test_lock_excludes_second_runner(self):
        with self.workspace.lock("same"):
            with self.assertRaises(UserError):
                with self.workspace.lock("same"):
                    pass

    def test_terminal_wrap_and_injection(self):
        for width in [32, 40, 80, 120, 180]:
            output = io.StringIO()
            terminal = Terminal(plain=True, console=Console(file=output, width=width, color_system=None))
            terminal.header(self.workspace, self.config)
            terminal.row("WARNING", "long " * 40, "detail " * 40)
            terminal.text("\x1b[2Jfake\x07\x1b]8;;https://bad\x07link\x1b]8;;\x07")
            self.assertNotIn("\x1b", output.getvalue())
            self.assertTrue(all(len(line) <= width for line in output.getvalue().splitlines()))
        self.assertEqual(clean("a\r\x00b"), "ab")

    def test_startup_does_not_seed_or_create_state(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run([sys.executable, str(ROOT / "pi.py"), "--workspace", root, "--json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["runs"], [])
            self.assertFalse((Path(root) / ".pi-engineering").exists())


if __name__ == "__main__":
    unittest.main()
