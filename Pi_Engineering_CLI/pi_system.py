"""Deterministic system-graph analysis for software, security and wiring."""
from __future__ import annotations

from collections import Counter, deque
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pi_workspace import UserError


MAX_BYTES = 5_000_000
MAX_NODES = 10_000
MAX_LINKS = 50_000
PACKAGE_EXAMPLES = Path(__file__).resolve().parent / "examples" / "systems"
INSTALLED_EXAMPLES = Path(sys.prefix) / "share" / "pi-engineering" / "examples" / "systems"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SystemNode(StrictModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
    label: str = Field(default="", max_length=240)
    kind: str = Field(default="component", min_length=1, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


class SystemLink(StrictModel):
    source: str
    target: str
    kind: str = Field(default="connects", min_length=1, max_length=64)
    label: str = Field(default="", max_length=240)
    properties: dict[str, Any] = Field(default_factory=dict)


class SystemGraph(StrictModel):
    version: Literal[1]
    name: str = Field(min_length=1, max_length=240)
    domain: Literal["generic", "software", "security", "wiring"] = "generic"
    description: str = Field(default="", max_length=2000)
    nodes: list[SystemNode] = Field(min_length=1, max_length=MAX_NODES)
    links: list[SystemLink] = Field(default_factory=list, max_length=MAX_LINKS)

    @model_validator(mode="after")
    def topology(self):
        identities = [node.id for node in self.nodes]
        if len(identities) != len(set(identities)):
            raise ValueError("node ids must be unique")
        known = set(identities)
        missing = sorted({value for link in self.links for value in (link.source, link.target) if value not in known})
        if missing:
            raise ValueError("links reference missing nodes: " + ", ".join(missing))
        return self


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise UserError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def load_system(path: str | Path) -> tuple[SystemGraph, str]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise UserError("System graph file does not exist")
    raw = source.read_bytes()
    if len(raw) > MAX_BYTES:
        raise UserError("System graph exceeds 5 MB")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        json.dumps(data, allow_nan=False)
        graph = SystemGraph.model_validate(data)
    except UserError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            detail = "; ".join(error["msg"] for error in exc.errors(include_input=False))
        else:
            detail = str(exc).split("\n")[0]
        raise UserError("Invalid system graph: " + detail) from exc
    return graph, sha256(raw).hexdigest()


def _maps(graph: SystemGraph):
    forward = {node.id: [] for node in graph.nodes}
    reverse = {node.id: [] for node in graph.nodes}
    edge_map: dict[tuple[str, str], list[int]] = {}
    for index, link in enumerate(graph.links):
        forward[link.source].append(link.target)
        reverse[link.target].append(link.source)
        edge_map.setdefault((link.source, link.target), []).append(index)
    for mapping in (forward, reverse):
        for values in mapping.values():
            values.sort()
    return forward, reverse, edge_map


def _distances(graph: SystemGraph, roots: list[str], direction="downstream", max_depth=None):
    known = {node.id for node in graph.nodes}
    invalid = sorted(set(roots) - known)
    if invalid:
        raise UserError("Unknown node: " + ", ".join(invalid))
    if max_depth is not None and max_depth < 0:
        raise UserError("max-depth must be non-negative")
    forward, reverse, _ = _maps(graph)
    if direction == "downstream":
        neighbors = forward
    elif direction == "upstream":
        neighbors = reverse
    else:
        neighbors = {key: sorted(set(forward[key] + reverse[key])) for key in forward}
    distance = {root: 0 for root in sorted(set(roots))}
    queue = deque(sorted(distance))
    while queue:
        current = queue.popleft()
        if max_depth is not None and distance[current] >= max_depth:
            continue
        for target in neighbors[current]:
            if target not in distance:
                distance[target] = distance[current] + 1
                queue.append(target)
    return distance


def impact(graph: SystemGraph, roots: list[str], direction="downstream", max_depth=None):
    distance = _distances(graph, roots, direction, max_depth)
    root_set = set(roots)
    affected = sorted((node for node in distance if node not in root_set), key=lambda node: (distance[node], node))
    return {"kind": "system_impact", "system": graph.name, "direction": direction,
            "failed": sorted(root_set), "affected": affected,
            "distances": {node: distance[node] for node in sorted(distance, key=lambda node: (distance[node], node))}}


def trace(graph: SystemGraph, start: str, end: str, direction="downstream"):
    if start == end:
        _distances(graph, [start], direction, 0)
        path = [start]
    else:
        forward, reverse, _ = _maps(graph)
        neighbors = forward if direction == "downstream" else reverse
        if start not in neighbors or end not in neighbors:
            raise UserError("Unknown start or end node")
        parent = {start: None}
        queue = deque([start])
        while queue and end not in parent:
            current = queue.popleft()
            for target in neighbors[current]:
                if target not in parent:
                    parent[target] = current
                    queue.append(target)
        path = []
        if end in parent:
            current = end
            while current is not None:
                path.append(current)
                current = parent[current]
            path.reverse()
    return {"kind": "system_trace", "system": graph.name, "direction": direction,
            "from": start, "to": end, "reachable": bool(path), "hops": max(0, len(path) - 1), "path": path}


def _nearest_paths(graph: SystemGraph, roots: list[str]):
    forward, _, _ = _maps(graph)
    parent = {}
    origin = {}
    queue = deque()
    for root in sorted(set(roots)):
        if root not in forward:
            raise UserError("Unknown node: " + root)
        parent[root] = None
        origin[root] = root
        queue.append(root)
    while queue:
        current = queue.popleft()
        for target in forward[current]:
            if target not in parent:
                parent[target] = current
                origin[target] = origin[current]
                queue.append(target)
    return parent, origin


def _path_from_parents(parent, target):
    if target not in parent:
        return []
    path = []
    current = target
    while current is not None:
        path.append(current)
        current = parent[current]
    return list(reversed(path))


def _components(graph: SystemGraph):
    forward, reverse, _ = _maps(graph)
    visited = set()
    result = []
    for root in sorted(forward):
        if root in visited:
            continue
        component = []
        visited.add(root)
        queue = deque([root])
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(set(forward[current] + reverse[current])):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        result.append(sorted(component))
    return result


def _cycle_nodes(graph: SystemGraph):
    forward, reverse, _ = _maps(graph)
    visited = set()
    finished = []
    for root in sorted(forward):
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, 0)]
        while stack:
            node, offset = stack[-1]
            if offset < len(forward[node]):
                target = forward[node][offset]
                stack[-1] = (node, offset + 1)
                if target not in visited:
                    visited.add(target)
                    stack.append((target, 0))
            else:
                finished.append(node)
                stack.pop()
    assigned = set()
    cyclic = set()
    self_links = {link.source for link in graph.links if link.source == link.target}
    for root in reversed(finished):
        if root in assigned:
            continue
        component = set()
        stack = [root]
        assigned.add(root)
        while stack:
            node = stack.pop()
            component.add(node)
            for target in reverse[node]:
                if target not in assigned:
                    assigned.add(target)
                    stack.append(target)
        if len(component) > 1 or component & self_links:
            cyclic.update(component)
    return sorted(cyclic)


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UserError(f"{field} must be a number")
    return float(value)


def _finding(severity, code, message, subject=""):
    return {"severity": severity, "code": code, "subject": subject, "message": message}


def _security_analysis(graph: SystemGraph):
    entries = sorted(node.id for node in graph.nodes if node.kind in {"entry", "actor", "interface"})
    assets = sorted(node.id for node in graph.nodes if node.kind in {"asset", "secret", "privilege"})
    parent, origin = _nearest_paths(graph, entries)
    paths = []
    for asset in assets:
        route = _path_from_parents(parent, asset)
        if route:
            paths.append({"entry": origin[asset], "asset": asset, "hops": len(route) - 1, "path": route})
    paths.sort(key=lambda item: (item["hops"], item["entry"], item["asset"]))
    return {"entries": entries, "assets": assets, "attack_paths": paths[:100], "paths_truncated": len(paths) > 100}


def _wiring_analysis(graph: SystemGraph):
    sources = sorted(node.id for node in graph.nodes if node.kind in {"source", "power-source", "supply"})
    loads = sorted(node.id for node in graph.nodes if node.kind in {"load", "device"})
    nodes = {node.id: node for node in graph.nodes}
    _, _, edge_map = _maps(graph)
    parent, origin = _nearest_paths(graph, sources)
    currents = Counter()
    routes = []
    for load in loads:
        path = _path_from_parents(parent, load)
        selected_source = origin.get(load)
        current = nodes[load].properties.get("current_a")
        if path and current is not None:
            current = _number(current, f"{load}.current_a")
            if current >= 0:
                # A negative draw is invalid data; do not corrupt shared-wire sums.
                for pair in zip(path, path[1:]):
                    for edge_index in edge_map[pair]:
                        currents[edge_index] += current
        routes.append({"load": load, "source": selected_source,
                       "path": path, "current_a": current})
    utilization = []
    for index, link in enumerate(graph.links):
        capacity = link.properties.get("max_current_a")
        used = currents[index]
        utilization.append({"link": index, "source": link.source, "target": link.target,
                            "current_a": used, "max_current_a": capacity,
                            "utilization_percent": round(100 * used / _number(capacity, f"link {index}.max_current_a"), 2)
                            if capacity is not None and _number(capacity, f"link {index}.max_current_a") > 0 else None})
    return {"sources": sources, "loads": loads, "routes": routes, "circuits": utilization}


def check_system(graph: SystemGraph):
    findings = []
    components = _components(graph)
    if len(components) > 1:
        findings.append(_finding("WARNING", "DISCONNECTED", f"Graph has {len(components)} disconnected components"))
    duplicates = Counter((link.source, link.target, link.kind) for link in graph.links)
    for key, count in sorted(duplicates.items()):
        if count > 1:
            findings.append(_finding("WARNING", "DUPLICATE_LINK", f"Link occurs {count} times", " -> ".join(key[:2])))
    for link in graph.links:
        if link.source == link.target:
            findings.append(_finding("WARNING", "SELF_LINK", "Node links to itself", link.source))
    cycles = _cycle_nodes(graph)
    if cycles and graph.domain in {"software", "wiring"}:
        findings.append(_finding("WARNING", "DIRECTED_CYCLE", "Directed cycle includes: " + ", ".join(cycles)))

    analysis = None
    if graph.domain == "security":
        analysis = _security_analysis(graph)
        if not analysis["entries"]:
            findings.append(_finding("WARNING", "NO_ENTRY", "No entry, actor, or interface nodes declared"))
        if not analysis["assets"]:
            findings.append(_finding("WARNING", "NO_ASSET", "No asset, secret, or privilege nodes declared"))
        for path in analysis["attack_paths"]:
            findings.append(_finding("WARNING", "ATTACK_PATH",
                f"Reachable in {path['hops']} hops: {' -> '.join(path['path'])}", path["asset"]))
    elif graph.domain == "wiring":
        analysis = _wiring_analysis(graph)
        nodes = {node.id: node for node in graph.nodes}
        if not analysis["sources"]:
            findings.append(_finding("ERROR", "NO_POWER_SOURCE", "No source, supply, or power-source node declared"))
        for route in analysis["routes"]:
            load = nodes[route["load"]]
            if not route["source"]:
                findings.append(_finding("ERROR", "OPEN_CIRCUIT", "Load has no directed path from a power source", load.id))
                continue
            source = nodes[route["source"]]
            voltage = source.properties.get("voltage_v")
            minimum = load.properties.get("min_voltage_v")
            maximum = load.properties.get("max_voltage_v")
            if voltage is not None:
                voltage = _number(voltage, f"{source.id}.voltage_v")
                if minimum is not None and voltage < _number(minimum, f"{load.id}.min_voltage_v"):
                    findings.append(_finding("ERROR", "UNDERVOLTAGE", f"{voltage:g} V is below load minimum", load.id))
                if maximum is not None and voltage > _number(maximum, f"{load.id}.max_voltage_v"):
                    findings.append(_finding("ERROR", "OVERVOLTAGE", f"{voltage:g} V exceeds load maximum", load.id))
            if route["current_a"] is None:
                findings.append(_finding("WARNING", "UNRATED_LOAD", "Load has no current_a property", load.id))
            elif route["current_a"] < 0:
                findings.append(_finding("ERROR", "INVALID_CURRENT", "Load current is negative", load.id))
        for circuit in analysis["circuits"]:
            link = graph.links[circuit["link"]]
            if link.kind in {"wire", "power"} and circuit["max_current_a"] is None:
                findings.append(_finding("WARNING", "UNRATED_WIRE", "Power link has no max_current_a property",
                                         f"{link.source} -> {link.target}"))
            if circuit["max_current_a"] is not None and circuit["max_current_a"] < 0:
                findings.append(_finding("ERROR", "INVALID_CAPACITY",
                    "max_current_a must not be negative", f"{link.source} -> {link.target}"))
            elif circuit["utilization_percent"] is not None and circuit["utilization_percent"] > 100:
                findings.append(_finding("ERROR", "OVERCURRENT",
                    f"{circuit['current_a']:g} A exceeds {float(circuit['max_current_a']):g} A capacity",
                    f"{link.source} -> {link.target}"))
            elif circuit["max_current_a"] == 0 and circuit["current_a"]:
                findings.append(_finding("ERROR", "OVERCURRENT",
                    f"{circuit['current_a']:g} A exceeds 0 A capacity",
                    f"{link.source} -> {link.target}"))
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    findings.sort(key=lambda item: (order[item["severity"]], item["code"], item["subject"]))
    errors = sum(item["severity"] == "ERROR" for item in findings)
    warnings = sum(item["severity"] == "WARNING" for item in findings)
    return {"kind": "system_check", "system": graph.name,
            "status": "failed" if errors else "warning" if warnings else "passed",
            "summary": {"errors": errors, "warnings": warnings}, "findings": findings,
            "analysis": analysis}


def inspect_system(graph: SystemGraph, digest: str):
    forward, reverse, _ = _maps(graph)
    check = check_system(graph)
    return {"kind": "system_inspection", "name": graph.name, "domain": graph.domain,
            "description": graph.description, "sha256": digest,
            "topology": {"nodes": len(graph.nodes), "links": len(graph.links),
                "components": len(_components(graph)),
                "roots": sorted(node for node in forward if not reverse[node]),
                "leaves": sorted(node for node in reverse if not forward[node]),
                "cycles": _cycle_nodes(graph)},
            "node_kinds": dict(sorted(Counter(node.kind for node in graph.nodes).items())),
            "link_kinds": dict(sorted(Counter(link.kind for link in graph.links).items())),
            "health": check["summary"], "status": check["status"], "analysis": check["analysis"]}


def validate_system(path):
    graph, digest = load_system(path)
    return {"kind": "system_validation", "status": "valid", "name": graph.name,
            "domain": graph.domain, "nodes": len(graph.nodes), "links": len(graph.links), "sha256": digest}


def sample_system(domain: str, output: str | None = None):
    filename = {"software": "software.json", "security": "security.json", "wiring": "wiring-harness.json"}[domain]
    source = next((directory / filename for directory in (PACKAGE_EXAMPLES, INSTALLED_EXAMPLES)
                   if (directory / filename).is_file()), None)
    if source is None:
        raise UserError("Installed system examples are missing")
    graph, _ = load_system(source)
    data = graph.model_dump(mode="json")
    if output:
        destination = Path(output).expanduser().resolve()
        if destination.exists() or destination.is_symlink():
            raise UserError("Output already exists; choose a new path")
        if not destination.parent.is_dir():
            raise UserError("Output parent directory does not exist")
        destination.write_text(json.dumps(data, indent=2) + "\n")
        return {"kind": "system_sample", "domain": domain, "output": str(destination), "graph": data}
    return {"kind": "system_sample", "domain": domain, "output": None, "graph": data}
