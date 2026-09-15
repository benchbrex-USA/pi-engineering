"""Synthetic scheduling timings, identical workload before and after upgrade."""
import asyncio
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pi_engine import Engine
from pi_workflow import run_workflow
from pi_workspace import Workspace


async def measure():
    samples = []
    for _ in range(5):
        with tempfile.TemporaryDirectory() as root:
            workspace = Workspace(root)
            class TimedModel:
                async def chat(self, messages, tools):
                    request = messages[-1]["content"].split("\n")[0]
                    await asyncio.sleep({"fast": .03, "slow": .20, "child": .20}[request])
                    return {"role": "assistant", "content": "observed", "tool_calls": []}
            path = Path(root) / "workflow.json"
            path.write_text(json.dumps({"concurrency": 2, "nodes": {
                "fast": {"agent": "researcher", "task": "fast"},
                "slow": {"agent": "researcher", "task": "slow"},
                "child": {"agent": "reviewer", "task": "child", "depends_on": ["fast"]}}}))
            started = time.perf_counter()
            result = await run_workflow(workspace, path, Engine(workspace, model=TimedModel()))
            assert result["status"] == "completed"
            samples.append(time.perf_counter() - started)
    print(json.dumps({"kind": "synthetic-async-sleep-no-external-tools", "trials": len(samples),
                      "seconds": samples, "median": statistics.median(samples),
                      "minimum": min(samples), "maximum": max(samples)}, indent=2))


if __name__ == "__main__":
    asyncio.run(measure())
