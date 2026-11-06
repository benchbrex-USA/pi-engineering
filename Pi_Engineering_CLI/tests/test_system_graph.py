from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pi_system import _components, check_system, impact, inspect_system, load_system, sample_system, trace
from pi_workspace import UserError


class SystemGraphTests(unittest.TestCase):
    def fixture(self, name):
        return ROOT / "examples" / "systems" / name

    def test_examples_are_valid_and_inspectable(self):
        for name, domain in (("software.json", "software"), ("security.json", "security"),
                             ("wiring-harness.json", "wiring")):
            graph, digest = load_system(self.fixture(name))
            inspected = inspect_system(graph, digest)
            self.assertEqual(inspected["domain"], domain)
            self.assertEqual(len(digest), 64)

    def test_impact_is_shortest_deterministic_and_bounded(self):
        graph, _ = load_system(self.fixture("software.json"))
        result = impact(graph, ["api"])
        self.assertEqual(result["affected"], ["events", "orders", "payments", "fulfillment"])
        self.assertEqual(result["distances"]["fulfillment"], 2)
        self.assertEqual(impact(graph, ["api"], max_depth=1)["affected"], ["events", "orders", "payments"])

    def test_trace_returns_shortest_path_and_unreachable_state(self):
        graph, _ = load_system(self.fixture("software.json"))
        self.assertEqual(trace(graph, "web", "fulfillment")["path"], ["web", "api", "events", "fulfillment"])
        self.assertFalse(trace(graph, "fulfillment", "web")["reachable"])

    def test_security_check_exposes_attack_path(self):
        graph, _ = load_system(self.fixture("security.json"))
        result = check_system(graph)
        paths = result["analysis"]["attack_paths"]
        self.assertEqual(paths[0]["path"], ["internet", "gateway", "session-api", "admin-role"])
        self.assertTrue(any(path["asset"] == "customer-data" for path in paths))

    def test_wiring_check_calculates_shared_current(self):
        graph, _ = load_system(self.fixture("wiring-harness.json"))
        result = check_system(graph)
        self.assertEqual(result["status"], "passed")
        shared = next(item for item in result["analysis"]["circuits"]
                      if item["source"] == "battery" and item["target"] == "fuse")
        self.assertAlmostEqual(shared["current_a"], 2.8)
        self.assertEqual(shared["utilization_percent"], 56.0)

    def test_wiring_finds_open_circuit_overvoltage_and_overcurrent(self):
        data = json.loads(self.fixture("wiring-harness.json").read_text())
        data["nodes"][0]["properties"]["voltage_v"] = 24
        data["nodes"].append({"id": "orphan-load", "kind": "load", "properties": {"current_a": 1}})
        data["links"][0]["properties"]["max_current_a"] = 1
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.json"
            path.write_text(json.dumps(data))
            graph, _ = load_system(path)
        codes = {item["code"] for item in check_system(graph)["findings"]}
        self.assertTrue({"OPEN_CIRCUIT", "OVERVOLTAGE", "OVERCURRENT"}.issubset(codes))

    def test_wiring_rejects_negative_capacity_and_draw(self):
        data = json.loads(self.fixture("wiring-harness.json").read_text())
        data["links"][0]["properties"]["max_current_a"] = -5
        data["nodes"][4]["properties"]["current_a"] = -2
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.json"
            path.write_text(json.dumps(data))
            graph, _ = load_system(path)
        result = check_system(graph)
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"INVALID_CAPACITY", "INVALID_CURRENT"}.issubset(codes))
        self.assertEqual(result["status"], "failed")
        # A negative draw must not corrupt the shared-wire sum.
        shared = next(item for item in result["analysis"]["circuits"]
                      if item["source"] == "battery" and item["target"] == "fuse")
        self.assertAlmostEqual(shared["current_a"], 1.4)

    def test_wiring_zero_capacity_carrying_current_is_overcurrent(self):
        data = json.loads(self.fixture("wiring-harness.json").read_text())
        data["links"][0]["properties"]["max_current_a"] = 0
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.json"
            path.write_text(json.dumps(data))
            graph, _ = load_system(path)
        result = check_system(graph)
        self.assertEqual(result["status"], "failed")
        self.assertIn("OVERCURRENT", {item["code"] for item in result["findings"]})

    def test_invalid_reference_and_duplicate_json_key_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"version":1,"name":"x","name":"y","nodes":[{"id":"a"}],"links":[]}')
            with self.assertRaisesRegex(UserError, "Duplicate JSON key"):
                load_system(path)
            path.write_text(json.dumps({"version": 1, "name": "x", "nodes": [{"id": "a"}],
                                        "links": [{"source": "a", "target": "missing"}]}))
            with self.assertRaisesRegex(UserError, "missing nodes"):
                load_system(path)

    def test_cycle_detection_does_not_label_downstream_nodes(self):
        data = {"version": 1, "name": "cycle", "domain": "software", "nodes": [
            {"id": "a"}, {"id": "b"}, {"id": "downstream"}], "links": [
            {"source": "a", "target": "b"}, {"source": "b", "target": "a"},
            {"source": "b", "target": "downstream"}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "graph.json"
            path.write_text(json.dumps(data))
            graph, digest = load_system(path)
        self.assertEqual(inspect_system(graph, digest)["topology"]["cycles"], ["a", "b"])

    def test_components_build_adjacency_once_and_include_weak_links(self):
        from unittest.mock import patch
        import pi_system

        graph = pi_system.SystemGraph.model_validate({
            "version": 1, "name": "components",
            "nodes": [{"id": name} for name in ("a", "b", "c", "d")],
            "links": [{"source": "a", "target": "b"}, {"source": "c", "target": "b"}],
        })
        with patch("pi_system._maps", wraps=pi_system._maps) as maps:
            self.assertEqual(_components(graph), [["a", "b", "c"], ["d"]])
        maps.assert_called_once_with(graph)

    def test_cli_json_contract(self):
        result = subprocess.run([sys.executable, str(ROOT / "pi_app.py"), "system", "impact",
            str(self.fixture("software.json")), "api", "--json"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["affected"][0], "events")

    def test_sample_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "system.json"
            result = sample_system("wiring", str(path))
            self.assertEqual(result["graph"]["domain"], "wiring")
            with self.assertRaisesRegex(UserError, "already exists"):
                sample_system("wiring", str(path))


if __name__ == "__main__":
    unittest.main()
