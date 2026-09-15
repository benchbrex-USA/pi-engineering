from __future__ import annotations

import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_tools import local_schemas


class SchemaIsolationTests(unittest.TestCase):
    def test_check_enum_does_not_poison_file_tools(self):
        schemas = local_schemas()
        schemas["workspace_check"]["inputSchema"]["properties"]["name"]["enum"] = [
            "public", "next-docs"
        ]
        path_schema = schemas["workspace_read"]["inputSchema"]["properties"]["path"]
        write_path = schemas["workspace_write"]["inputSchema"]["properties"]["path"]
        expected = schemas["workspace_write"]["inputSchema"]["properties"]["expected_hash"]
        self.assertNotIn("enum", path_schema)
        self.assertNotIn("enum", write_path)
        self.assertNotIn("enum", expected)
        Draft202012Validator(schemas["workspace_read"]["inputSchema"]).validate({"path": "AGENTS.md"})
        Draft202012Validator(schemas["workspace_write"]["inputSchema"]).validate({
            "path": "lib/opsgraph.ts",
            "content": "export {}",
            "expected_hash": "missing",
        })
        with self.assertRaises(ValidationError):
            Draft202012Validator(schemas["workspace_check"]["inputSchema"]).validate({"name": "not-a-check"})


if __name__ == "__main__":
    unittest.main()
