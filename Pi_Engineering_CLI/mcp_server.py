#!/usr/bin/env python3
"""MCP stdio server for Pi Engineering.

The server exposes the same governed runtime used by pi.py. It implements the
small JSON-RPC surface needed by MCP clients: initialize, tools/list and
tools/call.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

from pi_core import (
    DEFAULT_DB,
    PiError,
    PiGraph,
    PiStore,
    agent_catalog,
    approve,
    reject,
    run_eval,
)


PROTOCOL_VERSION = "2025-06-18"


def tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "pi.run_task",
            "description": "Run the governed Pi Engineering agent graph for a tenant request.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tenant", "actor", "request"],
                "properties": {
                    "tenant": {"type": "string"},
                    "actor": {"type": "string"},
                    "request": {"type": "string"},
                },
            },
        },
        {
            "name": "pi.approve",
            "description": "Approve and commit an awaiting-approval Pi Engineering run.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "actor": {"type": "string"},
                },
            },
        },
        {
            "name": "pi.reject",
            "description": "Reject an awaiting-approval Pi Engineering run.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        {
            "name": "pi.state",
            "description": "Read tickets, evidence, recent runs and latest eval state.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"tenant": {"type": "string"}},
            },
        },
        {
            "name": "pi.add_ticket",
            "description": "Add or update a tenant-scoped ticket.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tenant", "ticket", "title"],
                "properties": {
                    "tenant": {"type": "string"},
                    "ticket": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "pending", "resolved"]},
                    "priority": {"type": "string"},
                },
            },
        },
        {
            "name": "pi.add_evidence",
            "description": "Add authorized evidence for a tenant.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tenant", "title", "body"],
                "properties": {
                    "tenant": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "source_uri": {"type": "string"},
                    "trust_class": {"type": "string"},
                },
            },
        },
        {
            "name": "pi.graph",
            "description": "Describe the Pi governed action graph.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
        {
            "name": "pi.agents",
            "description": "List built-in Pi Engineering agents.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
        {
            "name": "pi.agent_add",
            "description": "Add or update an agent registry entry.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "role"],
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "permissions": {"type": "array", "items": {"type": "string"}},
                    "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                    "enabled": {"type": "boolean"},
                },
            },
        },
        {
            "name": "pi.policy_list",
            "description": "List persisted Pi policy rules.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action_type": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
            },
        },
        {
            "name": "pi.policy_add",
            "description": "Add or update a persisted Pi policy rule.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "action_type", "requires"],
                "properties": {
                    "name": {"type": "string"},
                    "action_type": {"type": "string"},
                    "requires": {"type": "array", "items": {"type": "string"}},
                    "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                    "effect": {"type": "string", "enum": ["allow", "requires_approval", "deny"]},
                    "enabled": {"type": "boolean"},
                },
            },
        },
        {
            "name": "pi.why",
            "description": "Explain why a run reached its current state.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
        },
        {
            "name": "pi.trace",
            "description": "Return full checkpoints and audit events for a run.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
        },
        {
            "name": "pi.receipt",
            "description": "Return the commit receipt for a run.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
        },
        {
            "name": "pi.eval",
            "description": "Run the graph-level Pi Engineering eval suite.",
            "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
    ]


class MCPRuntime:
    def __init__(self, db_path: str = str(DEFAULT_DB), debug: bool = False):
        self.store = PiStore(db_path)
        self.store.seed()
        self.debug = debug
        self.graph = PiGraph()

    def close(self) -> None:
        self.store.close()

    def response(self, request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def error(self, request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": err}

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        if request_id is None and method and method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                return self.response(request_id, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "pi-engineering-cli", "version": "1.0.0"},
                })
            if method == "tools/list":
                return self.response(request_id, {"tools": tool_schema()})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                return self.response(request_id, self.call_tool(name, arguments))
            return self.error(request_id, -32601, "Method not found", {"method": method})
        except Exception as exc:
            data = {"type": type(exc).__name__}
            if self.debug:
                data["traceback"] = traceback.format_exc()
            return self.error(request_id, -32603, "Internal error", data)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "pi.run_task":
                payload = self.graph.run(
                    self.store,
                    str(arguments["tenant"]),
                    str(arguments["actor"]),
                    str(arguments["request"]),
                )
            elif name == "pi.approve":
                payload = approve(self.store, str(arguments["run_id"]), arguments.get("actor"))
            elif name == "pi.reject":
                payload = reject(self.store, str(arguments["run_id"]), str(arguments.get("reason", "rejected_by_operator")))
            elif name == "pi.state":
                tenant = arguments.get("tenant")
                payload = self.store.state(str(tenant) if tenant else None)
            elif name == "pi.add_ticket":
                payload = self.store.add_ticket(
                    str(arguments["tenant"]),
                    str(arguments["ticket"]),
                    str(arguments["title"]),
                    str(arguments.get("status", "open")),
                    str(arguments.get("priority", "medium")),
                )
            elif name == "pi.add_evidence":
                payload = self.store.add_evidence(
                    str(arguments["tenant"]),
                    str(arguments["title"]),
                    str(arguments["body"]),
                    str(arguments.get("source_uri", "local://mcp/evidence")),
                    str(arguments.get("trust_class", "authorized source evidence")),
                )
            elif name == "pi.graph":
                payload = self.graph.describe()
            elif name == "pi.agents":
                payload = self.store.agents() or agent_catalog()
            elif name == "pi.agent_add":
                payload = self.store.add_agent(
                    str(arguments["name"]),
                    str(arguments["role"]),
                    list(arguments.get("tools", [])),
                    list(arguments.get("permissions", [])),
                    str(arguments.get("risk", "medium")),
                    bool(arguments.get("enabled", True)),
                    "mcp",
                )
            elif name == "pi.policy_list":
                payload = self.store.policy_rules(
                    arguments.get("action_type"),
                    arguments.get("enabled"),
                )
            elif name == "pi.policy_add":
                payload = self.store.add_policy_rule(
                    str(arguments["name"]),
                    str(arguments["action_type"]),
                    list(arguments["requires"]),
                    str(arguments.get("risk", "medium")),
                    str(arguments.get("effect", "requires_approval")),
                    bool(arguments.get("enabled", True)),
                )
            elif name == "pi.why":
                payload = self.store.explain_run(str(arguments["run_id"]))
            elif name == "pi.trace":
                payload = self.store.trace_run(str(arguments["run_id"]))
            elif name == "pi.receipt":
                payload = self.store.receipt(str(arguments["run_id"]))
                if payload is None:
                    raise PiError("receipt_not_found", 404)
            elif name == "pi.eval":
                payload = run_eval(self.store.path)
            else:
                raise PiError("unknown_tool", 404)
            return tool_result(payload)
        except PiError as exc:
            return tool_result({"error": exc.code, "status": exc.status}, is_error=True)
        except (KeyError, TypeError, ValueError) as exc:
            return tool_result({"error": "invalid_tool_arguments", "detail": str(exc)}, is_error=True)


def tool_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def process_line(runtime: MCPRuntime, line: str) -> str | None:
    if not line.strip():
        return None
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error", "data": str(exc)},
        })
    if isinstance(message, list):
        responses = [runtime.handle(item) for item in message]
        responses = [item for item in responses if item is not None]
        return json.dumps(responses) if responses else None
    response = runtime.handle(message)
    return json.dumps(response) if response is not None else None


def serve_stdio(db_path: str = str(DEFAULT_DB), debug: bool = False) -> None:
    runtime = MCPRuntime(db_path, debug=debug)
    try:
        for line in sys.stdin:
            response = process_line(runtime, line)
            if response is not None:
                print(response, flush=True)
    finally:
        runtime.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pi Engineering MCP stdio server")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    serve_stdio(args.db, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
