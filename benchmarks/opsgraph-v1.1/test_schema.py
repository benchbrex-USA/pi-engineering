"""Regression for check-name constraints leaking into unrelated tool fields."""
import asyncio
from types import SimpleNamespace
from pi_tools import ToolBroker
from jsonschema import Draft202012Validator

async def test():
    config = SimpleNamespace(checks={"public": {}, "next-docs": {}}, servers={})
    async with ToolBroker(None, config) as broker:
        examples = {
            "workspace_read": [{"path": "AGENTS.md"}, {"path": "lib/opsgraph.ts"}],
            "workspace_write": [dict(path="lib/opsgraph.ts", content="test", expected_hash=h)
                                for h in ["missing", "a" * 64]],
            "knowledge_search": [{"query": "arbitrary source search"}],
            "memory_search": [{"query": "arbitrary memory search"}],
            "workspace_check": [{"name": "public"}, {"name": "next-docs"}],
        }
        identities = []
        for name, examples_for_tool in examples.items():
            schema = broker.tools[name]["inputSchema"]
            for example in examples_for_tool:
                Draft202012Validator(schema).validate(example)
            for field, value in schema["properties"].items():
                identities.append(id(value))
                assert ("enum" in value) == (name == "workspace_check" and field == "name")
        assert len(identities) == len(set(identities))
        assert not Draft202012Validator(broker.tools["workspace_check"]["inputSchema"]).is_valid({"name": "other"})
    print("PASS: independent properties; multiple checks; paths, hashes, searches; enum restricted")

asyncio.run(test())
