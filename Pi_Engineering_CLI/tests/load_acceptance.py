"""Multi-process durable-state qualification, not a model-speed benchmark."""
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pi_workspace import Workspace


def worker(arguments):
    directory, count = arguments
    workspace = Workspace(directory)
    latencies = []
    for index in range(count):
        started = time.monotonic()
        task = workspace.create(f"storage-check-{index}", "engineer", "qualification")
        task["status"] = "completed"
        workspace.record(task, "complete")
        assert workspace.task(task["id"])["status"] == "completed"
        latencies.append(time.monotonic() - started)
    return latencies


if __name__ == "__main__":
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as directory:
        workspace = Workspace(directory)
        with workspace.database():
            pass
        with multiprocessing.get_context("spawn").Pool(4) as pool:
            batches = pool.map(worker, [(directory, 50)] * 4)
        with workspace.database() as db:
            assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 200
            assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 400
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        latencies = sorted(value for batch in batches for value in batch)
        report = {"passed": True, "processes": 4, "tasks": 200, "events": 400,
                  "seconds": round(time.monotonic() - started, 3),
                  "p95_create_update_read_seconds": round(latencies[189], 4)}
        print(json.dumps(report))
        target = Path(__file__).resolve().parents[1] / "reports" / "load.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
