import asyncio
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
import socket
from unittest.mock import patch

from pi_models import bounded_exchange
from pi_qualification import qualify
from pi_workspace import Workspace, WorkspaceSettings, UserError, fingerprint, ServerSettings
from pi_tools import ToolBroker
from pi_app import display
from pi_terminal import Terminal
from rich.console import Console


class QualificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Workspace(self.temp.name)
        self.workspace.save(self.workspace.config())
        self.schema = {"type": "object", "properties": {}, "additionalProperties": False}
        self.probe = {"name": "tenant-read", "tool": "customer__inspect", "arguments": {},
                      "input_schema_sha256": fingerprint(self.schema),
                      "response_schema": {"type": "object", "required": ["tenant"],
                                          "properties": {"tenant": {"const": "test-tenant"}}}}
        self.dispatched = []
        owner = self
        class Broker:
            def __init__(self, *args):
                self.tools = {"customer__inspect": {"inputSchema": owner.schema,
                              "server": "customer", "read": owner.read}}
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def validate(self, name, arguments):
                if name not in self.tools:
                    raise UserError("unavailable")
            async def call(self, name, arguments):
                owner.dispatched.append(name)
                return {"server_response": {"tenant": owner.tenant, "private": "not-in-report"}}
        self.factory = Broker
        self.read = True
        self.tenant = "test-tenant"

    async def run_contract(self):
        path = self.workspace.root / "contract.json"
        path.write_text(json.dumps({"probes": [self.probe]}))
        return await qualify(self.workspace, path, self.factory)

    async def test_pinned_read_contract_and_redacted_audit(self):
        result = await self.run_contract()
        self.assertEqual(result["status"], "passed")
        self.assertNotIn("not-in-report", json.dumps(result))
        events = self.workspace.events(result["id"])
        self.assertEqual(events[0]["kind"], "integration_qualification")
        self.assertNotIn("not-in-report", json.dumps(events))

    async def test_effectful_probe_refused_before_dispatch(self):
        self.read = False
        with self.assertRaises(UserError):
            await self.run_contract()
        self.assertEqual(self.dispatched, [])

    async def test_schema_drift_refused_before_dispatch(self):
        self.probe["input_schema_sha256"] = "0" * 64
        with self.assertRaises(UserError):
            await self.run_contract()
        self.assertEqual(self.dispatched, [])

    async def test_wrong_tenant_fails_contract(self):
        self.tenant = "other-tenant"
        self.assertEqual((await self.run_contract())["status"], "failed")

    async def test_remote_schema_reference_refused(self):
        self.probe["response_schema"] = {"$ref": "https://example.com/schema"}
        with self.assertRaises(UserError):
            await self.run_contract()
        self.assertEqual(self.dispatched, [])

    async def test_model_event_output_is_bounded(self):
        process = await asyncio.create_subprocess_exec(sys.executable, "-c",
            "import sys; sys.stdout.write('x'*10000)", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE)
        try:
            with self.assertRaises(UserError):
                await bounded_exchange(process, b"public input", limit=1000)
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()

    def test_config_symlink_refused(self):
        self.workspace.config_path.unlink()
        self.workspace.config_path.symlink_to(self.workspace.root / "other.json")
        with self.assertRaises(UserError):
            self.workspace.config()

    def test_lock_symlink_refused(self):
        (self.workspace.directory / "probe.lock").symlink_to(self.workspace.root / "unrelated")
        with self.assertRaises(UserError):
            with self.workspace.lock("probe"):
                self.fail("symlink accepted")
        self.assertFalse((self.workspace.root / "unrelated").exists())

    def test_journal_symlink_refused(self):
        (self.workspace.directory / "tasks.sqlite3-wal").symlink_to(self.workspace.root / "unrelated")
        with self.assertRaises(UserError):
            with self.workspace.database():
                self.fail("symlink accepted")

    def test_invalid_check_configuration_refused(self):
        for checks in ({"bad": []}, {"bad": [""]}, {"bad": ["echo", "\x00"]}):
            with self.assertRaises(ValueError):
                WorkspaceSettings(checks=checks)

    def test_qualification_and_schema_render_without_color_or_overflow(self):
        for width in (32, 80, 120):
            output = io.StringIO()
            terminal = Terminal(plain=True, console=Console(file=output, width=width, color_system=None))
            display({"status": "failed", "id": "qualification_test", "probes": [
                {"name": "tenant", "tool": "customer__inspect", "passed": False,
                 "seconds": .01, "error_type": "ValidationError"}]}, terminal, command="mcp")
            display({"tool": "customer__inspect", "read": True,
                     "input_schema_sha256": fingerprint(self.schema), "inputSchema": self.schema},
                    terminal, command="mcp")
            rendered = output.getvalue()
            self.assertIn("FAILED", rendered)
            self.assertNotIn("\x1b", rendered)
            self.assertTrue(all(len(line) <= width for line in rendered.splitlines()))

    async def test_real_http_bearer_auth_accepts_correct_and_rejects_wrong_token(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        fixture = Path(__file__).with_name("http_mcp_fixture.py")
        process = await asyncio.create_subprocess_exec(sys.executable, str(fixture), str(port),
            env={**os.environ, "PI_FIXTURE_TOKEN": "public-test-token"},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(.05)
            else:
                self.fail("HTTP fixture did not start")
            config = self.workspace.config()
            config.servers["protected"] = ServerSettings(transport="http",
                url=f"http://127.0.0.1:{port}/mcp", token_env="PI_TEST_CLIENT_TOKEN")
            with patch.dict(os.environ, {"PI_TEST_CLIENT_TOKEN": "wrong"}):
                with self.assertRaises(Exception):
                    async with ToolBroker(self.workspace, config):
                        pass
            with patch.dict(os.environ, {"PI_TEST_CLIENT_TOKEN": "public-test-token"}):
                async with ToolBroker(self.workspace, config) as broker:
                    result = await broker.call("protected__inspect_value", {"value": "authenticated"})
                    self.assertIn("authenticated", str(result))
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()
