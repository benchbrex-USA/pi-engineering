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
    def __init__(self, responses):
        self.responses = list(responses)
        self.i = 0

    async def chat(self, messages, tools):
        response = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return response


class ToolErrorObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_file_read_becomes_observation_not_unresolved(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(temp)
            config = workspace.config()
            config.model.provider = "ollama"
            config.model.model = "dummy"
            workspace.save(config)
            model = SequenceModel([
                {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "workspace_read", "arguments": {"path": "missing.txt"}}}]},
                {"role": "assistant", "content": "File was missing; no further tools.", "tool_calls": []},
            ])
            task = await Engine(workspace, model=model).start("Read missing.txt and report.")
            self.assertEqual(task["status"], "completed")
            self.assertNotEqual(task["status"], "unresolved")
            self.assertTrue(any(c["name"] == "workspace_read" and c["status"] == "done" for c in task["calls"]))
            self.assertIn("error", task["calls"][0]["result"])


if __name__ == "__main__":
    unittest.main()
