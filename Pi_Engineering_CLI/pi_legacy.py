#!/usr/bin/env python3
"""Archived ticket teaching CLI. Not the installed product entry point."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import select
import shutil
import sys
import termios
import tty
from pathlib import Path
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
from pi_ui import TerminalUI, command_label


DEFAULT_DEMO_REQUEST = "Mark DEMO-100 pending for customer confirmation"


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def ui_for(args: argparse.Namespace | None = None) -> TerminalUI:
    return TerminalUI(
        plain=bool(getattr(args, "plain", False)),
        animate=not bool(getattr(args, "no_animate", False)),
    )


def emit(payload: Any, as_json: bool = False,
         args: argparse.Namespace | None = None, view: str | None = None) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=json_default))
        return
    print(ui_for(args).render(payload, view=view))


def human(payload: Any) -> str:
    if isinstance(payload, list):
        return "\n".join(human(item) for item in payload) or "(none)"
    if not isinstance(payload, dict):
        return str(payload)

    if "receipt_id" in payload:
        return (
            f"committed {payload['ticket']} -> {payload['status']} "
            f"(version {payload['version']}, receipt {payload['receipt_id']})"
        )
    if {"id", "status", "tenant", "actor", "proposal"}.issubset(payload):
        action = payload.get("proposal", {}).get("action")
        lines = [
            f"run {payload['id']} [{payload['status']}]",
            f"tenant={payload['tenant']} actor={payload['actor']}",
        ]
        if action:
            lines.append(
                f"action={action['type']} {action['ticket']} -> {action['status']} "
                f"hash={payload.get('action_hash')}"
            )
            if payload["status"] == "awaiting_approval":
                lines.append(f"approve with: python3 pi.py approve {payload['id']} --actor {payload['actor']}")
        answer = payload.get("proposal", {}).get("answer")
        if answer:
            lines.append(f"answer={answer}")
        if payload.get("failure_reason"):
            lines.append(f"failure={payload['failure_reason']}")
        return "\n".join(lines)
    if {"passed", "total", "cases"}.issubset(payload):
        case_lines = [
            f"- {'PASS' if case['passed'] else 'FAIL'} {case['name']}"
            for case in payload["cases"]
        ]
        return (
            f"eval {payload['suite']}: {payload['passed']}/{payload['total']} passed; "
            f"severe_failures={payload['severe_failures']}\n" + "\n".join(case_lines)
        )
    if "tickets" in payload and "evidence" in payload:
        return (
            f"tickets={len(payload['tickets'])} evidence={len(payload['evidence'])} "
            f"runs={len(payload.get('runs', []))}"
        )
    if {"ticket", "status", "tenant"}.issubset(payload):
        return (
            f"{payload['tenant']}/{payload['ticket']} [{payload['status']}] "
            f"v{payload['version']} {payload['title']}"
        )
    if {"id", "title", "tenant", "trust_class"}.issubset(payload):
        return f"{payload['tenant']}/{payload['id']} {payload['title']} ({payload['trust_class']})"
    if {"name", "role", "permissions", "tools"}.issubset(payload):
        enabled = "enabled" if payload.get("enabled", True) else "disabled"
        return f"{payload['name']} [{enabled}, {payload.get('risk', 'medium')}] {payload['role']}"
    if {"id", "action_type", "requires", "effect"}.issubset(payload):
        enabled = "enabled" if payload.get("enabled", True) else "disabled"
        return (
            f"{payload['id']} [{enabled}, {payload['effect']}] "
            f"{payload['action_type']} requires={','.join(payload['requires'])}"
        )
    if "decision" in payload and "run_id" in payload:
        return "why " + payload["run_id"] + "\n" + "\n".join(f"- {line}" for line in payload["decision"])
    if "nodes" in payload and "edges" in payload:
        return (
            f"{payload['name']}: " + " -> ".join(payload["nodes"]) + "\n"
            "advantages: " + "; ".join(payload["pi_advantages_over_generic_graphs"])
        )
    return json.dumps(payload, indent=2, sort_keys=True, default=json_default)


def store_for(args: argparse.Namespace) -> PiStore:
    store = PiStore(args.db)
    if getattr(args, "seed", False):
        store.seed()
    return store


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite state path")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--seed", action="store_true", help="Seed sample data before running command")
    parser.add_argument("--plain", action="store_true", help="Disable terminal styling")
    parser.add_argument("--no-animate", action="store_true", help="Disable terminal animation")


def command_init(args: argparse.Namespace) -> None:
    store = PiStore(args.db)
    try:
        store.seed()
        emit({"db": str(args.db), "status": "initialized", "state": store.state()}, args.json, args, view="init")
    finally:
        store.close()


def command_run(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        ui = ui_for(args)
        progress = None if args.json else ui.progress_event
        result = PiGraph().run(store, args.tenant, args.actor, args.request, on_event=progress)
        emit(result, args.json, args, view="run")
    finally:
        store.close()


def command_approve(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(approve(store, args.run_id, args.actor), args.json, args, view="receipt")
    finally:
        store.close()


def command_reject(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(reject(store, args.run_id, args.reason), args.json, args, view="run")
    finally:
        store.close()


def command_state(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.state(args.tenant), args.json, args, view="state")
    finally:
        store.close()


def command_ticket_add(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.add_ticket(args.tenant, args.ticket, args.title, args.status, args.priority), args.json, args)
    finally:
        store.close()


def command_ticket_list(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.tickets(args.tenant), args.json, args)
    finally:
        store.close()


def command_evidence_add(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(
            store.add_evidence(args.tenant, args.title, args.body, args.source_uri, args.trust_class),
            args.json,
            args,
        )
    finally:
        store.close()


def command_evidence_list(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.evidence(args.tenant), args.json, args)
    finally:
        store.close()


def command_graph(args: argparse.Namespace) -> None:
    emit(PiGraph().describe(), args.json, args)


def command_agents(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        agents = store.agents()
        emit(agents if agents else agent_catalog(), args.json, args, view="agents")
    finally:
        store.close()


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def command_agent_list(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.agents(args.enabled), args.json, args, view="agents")
    finally:
        store.close()


def command_agent_add(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(
            store.add_agent(
                args.name,
                args.role,
                split_csv(args.tools),
                split_csv(args.permissions),
                args.risk,
                not args.disabled,
            ),
            args.json,
            args,
        )
    finally:
        store.close()


def command_agent_enable(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.set_agent_enabled(args.name, True), args.json, args)
    finally:
        store.close()


def command_agent_disable(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.set_agent_enabled(args.name, False), args.json, args)
    finally:
        store.close()


def command_policy_list(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.policy_rules(args.action_type, args.enabled), args.json, args, view="policies")
    finally:
        store.close()


def command_policy_add(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(
            store.add_policy_rule(
                args.name,
                args.action_type,
                split_csv(args.requires),
                args.risk,
                args.effect,
                not args.disabled,
            ),
            args.json,
            args,
        )
    finally:
        store.close()


def command_policy_explain(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.explain_run(args.run_id), args.json, args, view="why")
    finally:
        store.close()


def command_why(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.explain_run(args.run_id), args.json, args, view="why")
    finally:
        store.close()


def command_trace(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.trace_run(args.run_id), args.json, args, view="trace")
    finally:
        store.close()


def command_receipt(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        receipt = store.receipt(args.run_id)
        if receipt is None:
            raise PiError("receipt_not_found", 404)
        emit(receipt, args.json, args, view="receipt")
    finally:
        store.close()


def command_checkpoints(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        emit(store.checkpoints(args.run_id), args.json, args)
    finally:
        store.close()


def command_eval(args: argparse.Namespace) -> None:
    emit(run_eval(args.db), args.json, args, view="eval")


def command_home(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        store.seed()
        emit({"state": store.state()}, args.json, args, view="home")
    finally:
        store.close()


def command_tour(args: argparse.Namespace) -> None:
    command = command_label()
    payload = {
        "title": "Pi Engineering CLI",
        "flow": ["init", "demo", "run", "why", "approve", "receipt"],
        "commands": [
            command + " init",
            command + " demo",
            command + " run --tenant aster --actor alice \"Mark T-100 pending\"",
            command + " why RUN_ID",
            command + " approve RUN_ID --actor alice",
        ],
    }
    emit(payload, args.json, args, view="tour")


def command_palette(args: argparse.Namespace) -> None:
    query = " ".join(args.query or []).strip().lower()
    catalog = command_catalog(command_label())
    if query:
        terms = query.split()
        matches = [
            item for item in catalog
            if all(term in searchable_command(item) for term in terms)
        ]
    else:
        matches = catalog
    emit({"query": query, "matches": matches[:12]}, args.json, args, view="palette")


def command_doctor(args: argparse.Namespace) -> None:
    checks = []
    py_ok = sys.version_info >= (3, 11)
    checks.append({
        "name": "Python runtime",
        "status": "ok" if py_ok else "warn",
        "detail": sys.version.split()[0] + (" supported" if py_ok else " older than tested 3.11"),
    })
    installed = shutil.which("pi-engineering")
    checks.append({
        "name": "Installed command",
        "status": "ok" if installed else "warn",
        "detail": installed or "not found on PATH",
    })
    existing_pi = shutil.which("pi")
    checks.append({
        "name": "Existing pi command",
        "status": "warn" if existing_pi else "ok",
        "detail": existing_pi or "no conflict detected",
    })
    rich = importlib.util.find_spec("rich") is not None
    textual = importlib.util.find_spec("textual") is not None
    checks.append({
        "name": "Rich-capable terminal layer",
        "status": "ok" if rich else "warn",
        "detail": "rich installed" if rich else "rich not installed; using built-in renderer",
    })
    checks.append({
        "name": "Textual TUI backend",
        "status": "ok" if textual else "warn",
        "detail": "textual installed" if textual else "optional future upgrade not installed",
    })
    try:
        store = PiStore(args.db)
        store.seed()
        state = store.state()
        store.close()
        checks.append({
            "name": "Local state",
            "status": "ok",
            "detail": f"{len(state['tickets'])} tickets, {len(state['agents'])} agents, {len(state['policy_rules'])} policies",
        })
    except Exception as exc:
        checks.append({"name": "Local state", "status": "fail", "detail": type(exc).__name__})
    emit({"checks": checks}, args.json, args, view="doctor")


def command_preview(args: argparse.Namespace) -> None:
    payload = {
        "states": ["success", "warning", "error", "sync", "help"],
        "principles": ["feedback", "hierarchy", "progress", "contextual help"],
    }
    emit(payload, args.json, args, view="preview")


def command_launch(args: argparse.Namespace) -> None:
    if args.snapshot or args.json or not sys.stdout.isatty() or not sys.stdin.isatty():
        command_home(args)
        return
    store = store_for(args)
    store.seed()
    ui = ui_for(args)
    view = "home"
    message = "h home  s state  a agents  p policies  e eval  d demo  v preview  ? palette  q quit"
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write("\033[?1049h\033[?25l")
        sys.stdout.flush()
        while True:
            sys.stdout.write("\033[H\033[J")
            current_view = view
            sys.stdout.write(render_launch_view(ui, store, current_view, message, args))
            if current_view == "demo":
                view = "home"
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], 0.25)
            if not ready:
                continue
            key = sys.stdin.read(1)
            if key in {"q", "\x03", "\x04"}:
                break
            if key == "h":
                view = "home"
                message = "Command center refreshed."
            elif key == "s":
                view = "state"
                message = "State view."
            elif key == "a":
                view = "agents"
                message = "Agent registry."
            elif key == "p":
                view = "policies"
                message = "Policy registry."
            elif key == "e":
                view = "eval"
                message = "Eval suite ran."
            elif key == "d":
                view = "demo"
                message = "Guided demo run created. Review it before approval."
            elif key == "v":
                view = "preview"
                message = "Component preview."
            elif key == "?":
                view = "palette"
                message = "Command palette."
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        store.close()
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def command_demo(args: argparse.Namespace) -> None:
    store = store_for(args)
    try:
        store.seed()
        if args.tenant == "aster" and args.request == DEFAULT_DEMO_REQUEST:
            store.add_ticket("aster", "DEMO-100", "Guided demo ticket", "open", "low")
        ui = ui_for(args)
        progress = None if args.json else ui.progress_event
        run = PiGraph().run(store, args.tenant, args.actor, args.request, on_event=progress)
        emit({"run": run}, args.json, args, view="demo")
    finally:
        store.close()


def command_mcp(args: argparse.Namespace) -> None:
    from mcp_server import serve_stdio

    serve_stdio(args.db)


def command_catalog(command: str) -> list[dict[str, str]]:
    return [
        {
            "name": "Command Center",
            "category": "start",
            "command": command,
            "description": "Open the adaptive home view with live workspace signals.",
        },
        {
            "name": "Interactive Launch",
            "category": "start",
            "command": command + " launch",
            "description": "Open a keyboard-driven terminal command center.",
        },
        {
            "name": "Guided Demo",
            "category": "learn",
            "command": command + " demo",
            "description": "Create a safe DEMO-100 run and learn the workflow.",
        },
        {
            "name": "Run Task",
            "category": "work",
            "command": command + " run --tenant aster --actor alice \"Mark T-100 pending\"",
            "description": "Run the governed agent graph for a real request.",
        },
        {
            "name": "Explain Run",
            "category": "inspect",
            "command": command + " why RUN_ID",
            "description": "Explain policy, approval, evidence and receipt state.",
        },
        {
            "name": "Trace Run",
            "category": "inspect",
            "command": command + " trace RUN_ID",
            "description": "Inspect checkpoints and audit events.",
        },
        {
            "name": "Approve Run",
            "category": "govern",
            "command": command + " approve RUN_ID --actor alice",
            "description": "Commit an approved effectful action with a receipt.",
        },
        {
            "name": "Agent Registry",
            "category": "configure",
            "command": command + " agent list",
            "description": "Review roles, tools, permissions and risk.",
        },
        {
            "name": "Policy Registry",
            "category": "govern",
            "command": command + " policy list",
            "description": "Review action requirements before commits.",
        },
        {
            "name": "Doctor",
            "category": "health",
            "command": command + " doctor",
            "description": "Check installation, renderer and state health.",
        },
        {
            "name": "Preview Components",
            "category": "design",
            "command": command + " preview",
            "description": "Inspect CLI feedback states and component patterns.",
        },
        {
            "name": "MCP Server",
            "category": "integrate",
            "command": command + " mcp-server",
            "description": "Expose Pi tools over MCP stdio.",
        },
        {
            "name": "Eval Suite",
            "category": "quality",
            "command": command + " eval",
            "description": "Run graph-level reliability and safety evals.",
        },
    ]


def searchable_command(item: dict[str, str]) -> str:
    return " ".join(item.values()).lower()


def render_launch_view(ui: TerminalUI, store: PiStore, view: str,
                       message: str, args: argparse.Namespace) -> str:
    if view == "state":
        body = ui.render(store.state(), view="state")
    elif view == "agents":
        body = ui.render(store.agents(), view="agents")
    elif view == "policies":
        body = ui.render(store.policy_rules(), view="policies")
    elif view == "eval":
        body = ui.render(run_eval(args.db), view="eval")
    elif view == "demo":
        store.add_ticket("aster", "DEMO-100", "Guided demo ticket", "open", "low")
        body = ui.render(
            {"run": PiGraph().run(store, "aster", "newcomer", DEFAULT_DEMO_REQUEST)},
            view="demo",
        )
        view = "home"
    elif view == "palette":
        body = ui.render(
            {"query": "all", "matches": command_catalog(command_label())},
            view="palette",
        )
    elif view == "preview":
        body = ui.render({}, view="preview")
    else:
        body = ui.render({"state": store.state()}, view="home")
    footer = ui.panel("Launch Controls", [message])
    return body + "\n\n" + footer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=command_label(),
        description="Pi Engineering CLI: governed agent graph, approvals, receipts and MCP server.",
    )
    add_common(parser)
    parser.set_defaults(func=command_home)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("home", help="Show the Pi command center")
    add_common(p)
    p.set_defaults(func=command_home)

    p = sub.add_parser("tour", help="Show a newcomer-friendly tour")
    add_common(p)
    p.set_defaults(func=command_tour)

    p = sub.add_parser("palette", help="Search the command palette")
    add_common(p)
    p.add_argument("query", nargs="*")
    p.set_defaults(func=command_palette)

    p = sub.add_parser("doctor", help="Check installation and terminal capabilities")
    add_common(p)
    p.set_defaults(func=command_doctor)

    p = sub.add_parser("preview", help="Preview Pi CLI feedback components")
    add_common(p)
    p.set_defaults(func=command_preview)

    p = sub.add_parser("launch", help="Open the interactive Pi command center")
    add_common(p)
    p.add_argument("--snapshot", action="store_true", help="Render one screen without entering TUI mode")
    p.set_defaults(func=command_launch)

    p = sub.add_parser("demo", help="Run a guided sample workflow")
    add_common(p)
    p.add_argument("--tenant", default="aster")
    p.add_argument("--actor", default="newcomer")
    p.add_argument("--request", default=DEFAULT_DEMO_REQUEST)
    p.set_defaults(func=command_demo)

    p = sub.add_parser("init", help="Initialize local state")
    add_common(p)
    p.set_defaults(func=command_init)

    p = sub.add_parser("run", help="Run the governed agent graph")
    add_common(p)
    p.add_argument("request")
    p.add_argument("--tenant", required=True)
    p.add_argument("--actor", required=True)
    p.set_defaults(func=command_run)

    p = sub.add_parser("approve", help="Approve and commit a pending run")
    add_common(p)
    p.add_argument("run_id")
    p.add_argument("--actor")
    p.set_defaults(func=command_approve)

    p = sub.add_parser("reject", help="Reject a pending run")
    add_common(p)
    p.add_argument("run_id")
    p.add_argument("--reason", default="rejected_by_operator")
    p.set_defaults(func=command_reject)

    p = sub.add_parser("state", help="Show current Pi state")
    add_common(p)
    p.add_argument("--tenant")
    p.set_defaults(func=command_state)

    ticket = sub.add_parser("ticket", help="Manage tickets").add_subparsers(dest="ticket_command", required=True)
    p = ticket.add_parser("add", help="Add or update a ticket")
    add_common(p)
    p.add_argument("--tenant", required=True)
    p.add_argument("--ticket", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--status", default="open", choices=["open", "pending", "resolved"])
    p.add_argument("--priority", default="medium")
    p.set_defaults(func=command_ticket_add)

    p = ticket.add_parser("list", help="List tickets")
    add_common(p)
    p.add_argument("--tenant")
    p.set_defaults(func=command_ticket_list)

    evidence = sub.add_parser("evidence", help="Manage authorized evidence").add_subparsers(
        dest="evidence_command",
        required=True,
    )
    p = evidence.add_parser("add", help="Add or update evidence")
    add_common(p)
    p.add_argument("--tenant", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--source-uri", default="local://cli/evidence")
    p.add_argument("--trust-class", default="authorized source evidence")
    p.set_defaults(func=command_evidence_add)

    p = evidence.add_parser("list", help="List evidence")
    add_common(p)
    p.add_argument("--tenant")
    p.set_defaults(func=command_evidence_list)

    p = sub.add_parser("graph", help="Describe the governed graph")
    add_common(p)
    p.set_defaults(func=command_graph)

    p = sub.add_parser("agents", help="List built-in agents")
    add_common(p)
    p.set_defaults(func=command_agents)

    agent = sub.add_parser("agent", help="Manage agent registry").add_subparsers(
        dest="agent_command",
        required=True,
    )
    p = agent.add_parser("list", help="List registered agents")
    add_common(p)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--enabled", dest="enabled", action="store_true")
    group.add_argument("--disabled", dest="enabled", action="store_false")
    p.set_defaults(enabled=None, func=command_agent_list)

    p = agent.add_parser("add", help="Add or update an agent definition")
    add_common(p)
    p.add_argument("--name", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--tools", help="Comma-separated tool names")
    p.add_argument("--permissions", help="Comma-separated permissions")
    p.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--disabled", action="store_true")
    p.set_defaults(func=command_agent_add)

    p = agent.add_parser("enable", help="Enable an agent")
    add_common(p)
    p.add_argument("name")
    p.set_defaults(func=command_agent_enable)

    p = agent.add_parser("disable", help="Disable an agent")
    add_common(p)
    p.add_argument("name")
    p.set_defaults(func=command_agent_disable)

    policy = sub.add_parser("policy", help="Manage and inspect policy rules").add_subparsers(
        dest="policy_command",
        required=True,
    )
    p = policy.add_parser("list", help="List policy rules")
    add_common(p)
    p.add_argument("--action-type")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--enabled", dest="enabled", action="store_true")
    group.add_argument("--disabled", dest="enabled", action="store_false")
    p.set_defaults(enabled=None, func=command_policy_list)

    p = policy.add_parser("add", help="Add or update a policy rule")
    add_common(p)
    p.add_argument("--name", required=True)
    p.add_argument("--action-type", required=True)
    p.add_argument("--requires", required=True, help="Comma-separated requirement names")
    p.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--effect", default="requires_approval", choices=["allow", "requires_approval", "deny"])
    p.add_argument("--disabled", action="store_true")
    p.set_defaults(func=command_policy_add)

    p = policy.add_parser("explain", help="Explain which policies governed a run")
    add_common(p)
    p.add_argument("run_id")
    p.set_defaults(func=command_policy_explain)

    p = sub.add_parser("why", help="Explain a run decision")
    add_common(p)
    p.add_argument("run_id")
    p.set_defaults(func=command_why)

    p = sub.add_parser("trace", help="Show a run trace with checkpoints and audit events")
    add_common(p)
    p.add_argument("run_id")
    p.set_defaults(func=command_trace)

    p = sub.add_parser("receipt", help="Show the receipt for a committed run")
    add_common(p)
    p.add_argument("run_id")
    p.set_defaults(func=command_receipt)

    p = sub.add_parser("checkpoints", help="Show run checkpoints")
    add_common(p)
    p.add_argument("run_id")
    p.set_defaults(func=command_checkpoints)

    p = sub.add_parser("eval", help="Run graph-level evals")
    add_common(p)
    p.set_defaults(func=command_eval)

    p = sub.add_parser("mcp-server", help="Run JSON-RPC MCP server over stdio")
    add_common(p)
    p.set_defaults(func=command_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except PiError as exc:
        print(json.dumps({"error": exc.code, "status": exc.status}), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
