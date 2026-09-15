import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_models import openai_messages


class OpenAIToolProjectionTests(unittest.TestCase):
    def test_projects_tool_name_transcript_to_tool_call_ids(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "workspace_files", "arguments": {}}},
                {"function": {"name": "knowledge_search", "arguments": {"query": "x"}}},
            ]},
            {"role": "tool", "tool_name": "workspace_files", "content": "{\"files\":[]}"},
            {"role": "tool", "tool_name": "knowledge_search", "content": "{\"observations\":[]}"},
        ]
        projected = openai_messages(messages)
        self.assertEqual(projected[1]["tool_calls"][0]["id"], "call_0")
        self.assertEqual(projected[1]["tool_calls"][1]["function"]["arguments"], json.dumps({"query": "x"}))
        self.assertEqual(projected[2]["tool_call_id"], "call_0")
        self.assertEqual(projected[3]["tool_call_id"], "call_1")
        self.assertNotIn("tool_name", projected[2])


if __name__ == "__main__":
    unittest.main()
