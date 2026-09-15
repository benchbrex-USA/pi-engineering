import asyncio
import io
import tempfile
import unittest
from unittest.mock import patch

from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError
from rich.console import Console

from pi_engine import Engine
from pi_live import ExecutionView
from pi_prompt import CommandCompleter, CommandValidator
from pi_terminal import Terminal, clean
from pi_workspace import Workspace


class TerminalExperienceTests(unittest.IsolatedAsyncioTestCase):
    def test_completion_searches_commands_and_descriptions(self):
        completer = CommandCompleter()
        self.assertIn("/review", [c.text for c in completer.get_completions(Document("/pending"), None)])
        completer.agents = ["engineer", "reviewer"]
        self.assertEqual([c.text for c in completer.get_completions(Document("/agent rev"), None)], ["reviewer"])
        self.assertEqual(list(completer.get_completions(Document("plain task"), None)), [])

    def test_approval_completion_never_inserts_an_approval_hash(self):
        completer = CommandCompleter()
        completer.tasks = [{"id": "task_123", "status": "awaiting_approval"}]
        self.assertEqual([c.text for c in completer.get_completions(Document("/approve "), None)], ["task_123"])
        self.assertEqual(list(completer.get_completions(Document("/approve task_123 "), None)), [])

    def test_input_validation(self):
        validator = CommandValidator()
        validator.validate(Document("Review this source"))
        validator.validate(Document('/knowledge search "approval policy"'))
        for invalid in ("/invented", '/knowledge search "unclosed'):
            with self.assertRaises(ValidationError):
                validator.validate(Document(invalid))

    def test_live_projection_parallel_states_and_widths(self):
        view = ExecutionView("Agent workflow", clean)
        view.event("propose", {"task_id": "task_one", "agent": "researcher", "status": "running", "steps": 2})
        view.event("review", {"task_id": "task_two", "agent": "engineer", "status": "awaiting_approval", "tool": "workspace_write"})
        for width in (32, 40, 80, 120):
            output = io.StringIO()
            Console(file=output, width=width, color_system=None).print(view)
            rendered = output.getvalue()
            self.assertIn("WAITING", rendered)
            self.assertNotIn("100%", rendered)
            self.assertTrue(all(len(line) <= width for line in rendered.splitlines()))
        self.assertEqual(len(view.activities), 2)

    def test_failure_is_not_rendered_as_success(self):
        view = ExecutionView("Registered checks", clean)
        view.event("complete", {"task_id": "task_check", "status": "verification_failed"})
        view.finish({"status": "verification_failed"})
        output = io.StringIO()
        Console(file=output, color_system=None).print(view)
        self.assertIn("FAILED", output.getvalue())
        self.assertNotIn("SUCCEEDED", output.getvalue())

    def test_known_workflow_total_does_not_create_fake_agent_activity(self):
        view = ExecutionView("Workflow", clean)
        view.event("workflow_progress", {"completed": 2, "total": 4})
        self.assertEqual(view.activities, {})
        output = io.StringIO()
        Console(file=output, width=40, color_system=None).print(view)
        self.assertIn("2/4 workflow nodes completed", output.getvalue())

    def test_live_cleanup_on_interruption(self):
        terminal = Terminal(console=Console(file=io.StringIO(), force_terminal=True))
        with self.assertRaises(KeyboardInterrupt):
            with terminal.operation("Interrupted"):
                raise KeyboardInterrupt()
        self.assertIsNone(terminal.active_view)
        self.assertFalse(terminal.console._live_stack)

    def test_bright_colors_and_no_color_fallback(self):
        output = io.StringIO()
        terminal = Terminal(console=Console(file=output, force_terminal=True, color_system="truecolor", no_color=False))
        terminal.row("SUCCEEDED", "Verified")
        self.assertIn("48;2;0;237;116", output.getvalue())
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            self.assertFalse(Terminal().animate)

    async def test_real_engine_events_drive_review_and_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(directory)
            workspace.save(workspace.config())
            view = ExecutionView("Local file task", clean)
            engine = Engine(workspace, event=view.event)
            pending = await engine.propose_tool("workspace_write", {"path": "result.txt", "content": "observed", "expected_hash": "missing"})
            self.assertEqual(view.activities[pending["id"]].status, "awaiting_approval")
            result = await engine.advance(pending["id"], pending["calls"][0]["hash"])
            self.assertEqual(view.activities[result["id"]].status, "completed")
            self.assertEqual(view.activities[result["id"]].observations, ["workspace_write"])
