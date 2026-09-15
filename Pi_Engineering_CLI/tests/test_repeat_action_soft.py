from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_engine import Engine
from pi_workspace import Workspace


class SequenceModel:
    def __init__(self):
        self.i = 0

    async def chat(self, messages, tools):
        self.i += 1
        if self.i == 1:
            return {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "workspace_files", "arguments": {}}}]}
        if self.i == 2:
            # illegal repeat of identical read action
            return {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "workspace_files", "arguments": {}}}]}
        return {"role": "assistant", "content": "Mapped risks from prior observations.", "tool_calls": []}


class RepeatActionSoftTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_read_does_not_fail_task(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            (workspace.root / "README.md").write_text("hello")
            config = workspace.config()
            config.model.model = "dummy"
            workspace.save(config)
            task = await Engine(workspace, model=SequenceModel()).start("Map risks")
            self.assertEqual(task["status"], "completed")
            self.assertIn("Mapped risks", task.get("answer", ""))


if __name__ == "__main__":
    unittest.main()
