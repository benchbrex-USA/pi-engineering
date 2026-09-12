"""Qualify an actual public MCP connection without private customer data."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pi_tools import ToolBroker
from pi_workspace import Workspace, ServerSettings, fingerprint
from pi_qualification import qualify


async def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as directory:
        workspace = Workspace(directory)
        config = workspace.config()
        config.servers["deepwiki"] = ServerSettings(transport="http", url="https://mcp.deepwiki.com/mcp",
                                                    read_tools=["read_wiki_structure"])
        workspace.save(config)
        async with ToolBroker(workspace, config) as broker:
            tool = "deepwiki__read_wiki_structure"
            schema_hash = fingerprint(broker.tools[tool]["inputSchema"])
        contract = workspace.root / "contract.json"
        contract.write_text(json.dumps({"probes": [{"name": "public-sdk-structure", "tool": tool,
            "arguments": {"repoName": "modelcontextprotocol/python-sdk"}, "input_schema_sha256": schema_hash,
            "response_schema": {"type": "object", "required": ["content"],
                                "properties": {"content": {"type": "array", "minItems": 1}}}}]}))
        qualification = await qualify(workspace, contract)
        assert qualification["status"] == "passed"
        report = {"provider": "DeepWiki", "transport": "Streamable HTTP", "tool": tool,
                  "repository": "modelcontextprotocol/python-sdk", "passed": True,
                  "seconds": round(time.monotonic() - started, 2), "qualification": qualification}
        print(json.dumps(report))
        destination = Path(__file__).resolve().parents[1] / "reports" / "integration.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
