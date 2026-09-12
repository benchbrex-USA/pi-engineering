"""Live-provider acceptance. No simulated model responses; isolated test workspace."""
import asyncio
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pi_engine import Engine
from pi_knowledge import Knowledge
from pi_workspace import Workspace, ModelSettings


async def run_trial():
    results = []
    with tempfile.TemporaryDirectory(prefix="pi-live-") as directory:
        workspace = Workspace(directory)
        config = workspace.config()
        config.model = ModelSettings(provider="codex", model="default", timeout=180)
        workspace.save(config)
        token = uuid.uuid4().hex[:12]
        (workspace.root / "policy.txt").write_text(f"The public release label is {token}. This label is public, not a credential.\n")
        Knowledge(workspace).ingest("policy.txt")
        Knowledge(workspace).remember("Public deployment channel", f"The public deployment channel is channel-{token}.", "test operator", 1)
        cases = [
            ("retrieval", "Use knowledge_search to find the public release label. Return that public label and cite its source."),
            ("memory", "Use memory_search to find the public deployment channel. Return the channel name and source."),
            ("approved_write", f"Use workspace_write to create result.txt containing exactly {token}, with expected_hash missing. Do not claim success before tool execution."),
        ]
        for name, request in cases:
            started = time.monotonic()
            engine = Engine(workspace)
            task = await engine.start(request)
            if name == "approved_write" and task["status"] == "awaiting_approval":
                assert not (workspace.root / "result.txt").exists()
                task = await engine.advance(task["id"], task["calls"][-1]["hash"])
            passed = task["status"] == "completed"
            if name == "retrieval":
                passed = passed and token in task["answer"] and any(c["name"] == "knowledge_search" for c in task["calls"])
            elif name == "memory":
                passed = passed and "channel-" + token in task["answer"] and any(c["name"] == "memory_search" for c in task["calls"])
            else:
                passed = passed and (workspace.root / "result.txt").is_file() and (workspace.root / "result.txt").read_text() == token
            results.append({"case": name, "passed": passed, "status": task["status"], "error": task["error"],
                            "seconds": round(time.monotonic() - started, 2), "steps": task["steps"],
                            "answer": task["answer"], "observations": [c.get("result") for c in task["calls"]],
                            "arguments": [c["arguments"] for c in task["calls"]],
                            "tools": [c["name"] for c in task["calls"]]})
            print(json.dumps(results[-1]), flush=True)
    return results


async def main(trials):
    results = []
    for trial in range(trials):
        results.extend(dict(row, trial=trial + 1) for row in await run_trial())
    report = Path(__file__).resolve().parents[1] / "reports" / "live.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(case["passed"] for case in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, choices=range(1, 11), default=1)
    raise SystemExit(asyncio.run(main(parser.parse_args().trials)))
