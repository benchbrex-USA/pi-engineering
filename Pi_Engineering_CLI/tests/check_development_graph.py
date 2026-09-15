"""Check development evidence/dependencies, not runtime workflow semantics."""
from graphlib import TopologicalSorter
import json
from pathlib import Path


def check():
    root = Path(__file__).resolve().parents[1]
    graph = json.loads((root / "graph-development.json").read_text())
    assert graph["kind"] == "development-task-graph"
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"])
    for node in nodes.values():
        assert set(("id", "objective", "dependencies", "acceptance", "status", "evidence", "notes")) <= node.keys()
        assert node["status"] in {"pending", "ready", "active", "blocked", "failed", "complete", "skipped"}
        assert all(dependency in nodes for dependency in node["dependencies"])
        if node["status"] in {"ready", "active", "complete"}:
            assert all(nodes[dependency]["status"] == "complete" for dependency in node["dependencies"])
        if node["status"] == "complete":
            assert node["evidence"]
            assert all((root / evidence).is_file() for evidence in node["evidence"])
        if node["status"] == "blocked":
            assert node.get("blocker") and node.get("unblocks_when")
    tuple(TopologicalSorter({key: node["dependencies"] for key, node in nodes.items()}).static_order())
    print("Development graph: identities, dependencies, states and evidence references valid")


if __name__ == "__main__":
    check()
