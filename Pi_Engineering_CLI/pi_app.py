"""User-facing application entry point."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

import httpx
from pydantic import ValidationError

from pi_engine import Engine, GRAPH
from pi_terminal import Terminal
from pi_tools import ToolBroker
from pi_workspace import AgentSettings, ServerSettings, UserError, VERSION, Workspace, active_workspace, select_workspace


def parser():
    p = argparse.ArgumentParser(prog="pi-engineering", description="Pi Engineering: agent tasks, governed tools and durable execution.")
    p.add_argument("--workspace", default=active_workspace(), help="Project directory (default: active workspace)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--plain", action="store_true")
    p.add_argument("--no-animate", action="store_true")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command")
    for name in ["setup", "init", "launch", "home", "doctor", "runs", "agents", "tools", "graph", "mcp-server"]:
        sub.add_parser(name)
    m = sub.add_parser("model").add_subparsers(dest="operation", required=True)
    s = m.add_parser("set")
    s.add_argument("model")
    s.add_argument("--provider", choices=["ollama", "codex"], default="ollama")
    s.add_argument("--endpoint", default="http://127.0.0.1:11434")
    s.add_argument("--token-env", default="")
    m.add_parser("show")
    a = sub.add_parser("agent").add_subparsers(dest="operation", required=True)
    a.add_parser("list")
    s = a.add_parser("set")
    s.add_argument("name")
    s.add_argument("--role", required=True)
    s.add_argument("--tools", nargs="*", default=["workspace_files", "workspace_read"])
    s.add_argument("--max-steps", type=int, default=16)
    s.add_argument("--model")
    s.add_argument("--provider", choices=["ollama", "codex"], default="ollama")
    for name in ["enable", "disable"]:
        a.add_parser(name).add_argument("name")
    m = sub.add_parser("mcp").add_subparsers(dest="operation", required=True)
    m.add_parser("list")
    s = m.add_parser("add")
    s.add_argument("name")
    s.add_argument("--url")
    s.add_argument("--token-env", default="")
    s.add_argument("--env", nargs="*", default=[])
    s.add_argument("--read-tools", nargs="*", default=[])
    s.add_argument("--command", dest="server_command")
    s.add_argument("--arg", action="append", default=[], help="Server argument; repeat, using --arg=VALUE for flags")
    m.add_parser("remove").add_argument("name")
    m.add_parser("qualify").add_argument("file", help="Read-only integration contract JSON")
    m.add_parser("schema").add_argument("tool", help="Inspect an MCP schema and its pin")
    s = sub.add_parser("run")
    s.add_argument("request")
    s.add_argument("--agent", default="engineer")
    s = sub.add_parser("call")
    s.add_argument("tool")
    s.add_argument("arguments", help="JSON object")
    s.add_argument("--agent", default="engineer")
    for name in ["show", "trace", "receipt", "resume", "reject"]:
        sub.add_parser(name).add_argument("id")
    s = sub.add_parser("approve")
    s.add_argument("id")
    s.add_argument("hash")
    s = sub.add_parser("reconcile")
    s.add_argument("id")
    s.add_argument("--outcome", required=True, choices=["executed", "not_executed", "unknown"])
    s.add_argument("--evidence", required=True)
    s = sub.add_parser("workflow")
    s.add_argument("file", help="JSON task DAG")
    knowledge = sub.add_parser("knowledge").add_subparsers(dest="operation", required=True)
    knowledge.add_parser("add").add_argument("path")
    knowledge.add_parser("list")
    knowledge.add_parser("search").add_argument("query")
    knowledge.add_parser("remove").add_argument("id")
    memory = sub.add_parser("memory").add_subparsers(dest="operation", required=True)
    s = memory.add_parser("add")
    s.add_argument("--title", required=True)
    s.add_argument("--body", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--ttl-days", type=int)
    s.add_argument("--id")
    memory.add_parser("list")
    memory.add_parser("search").add_argument("query")
    memory.add_parser("remove").add_argument("id")
    for name in ["backup", "restore"]:
        s = sub.add_parser(name)
        s.add_argument("path")
        s.add_argument("--key-env", default="PI_BACKUP_PASSPHRASE")
    sub.add_parser("metrics")
    s = sub.add_parser("workspace").add_subparsers(dest="operation", required=True)
    s.add_parser("use").add_argument("path")
    s.add_parser("show")
    checks = sub.add_parser("check").add_subparsers(dest="operation", required=True)
    checks.add_parser("list")
    s = checks.add_parser("add")
    s.add_argument("name")
    s.add_argument("--command", dest="check_command", required=True)
    s.add_argument("--arg", action="append", default=[])
    def globals_after_command(current):
        for action in list(current._actions):
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    child.add_argument("--workspace", default=argparse.SUPPRESS)
                    child.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
                    child.add_argument("--plain", action="store_true", default=argparse.SUPPRESS)
                    child.add_argument("--no-animate", action="store_true", default=argparse.SUPPRESS)
                    globals_after_command(child)
    globals_after_command(p)
    return p


async def doctor(workspace):
    config = workspace.config()
    checks = [{"name": "Workspace", "ok": workspace.config_path.exists(), "detail": str(workspace.root)}]
    try:
        with workspace.database() as db:
            integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        checks.append({"name": "Task database", "ok": integrity == "ok", "detail": integrity})
    except Exception:
        checks.append({"name": "Task database", "ok": False, "detail": "Cannot open task database"})
    try:
        if config.model.provider == "codex":
            process = await asyncio.create_subprocess_exec("codex", "login", "status",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(process.wait(), 10)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            checks.append({"name": "Model", "ok": process.returncode == 0,
                           "detail": "Codex authenticated" if process.returncode == 0 else "Run codex login"})
            return checks + await connection_checks(workspace, config)
        headers = {}
        if config.model.token_env and os.environ.get(config.model.token_env):
            headers["Authorization"] = "Bearer " + os.environ[config.model.token_env]
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(config.model.endpoint + "/api/tags", headers=headers)
            response.raise_for_status()
        names = [x["name"] for x in response.json().get("models", [])]
        checks.append({"name": "Model", "ok": config.model.model in names,
                       "detail": config.model.model or "No model selected; use model set"})
    except Exception:
        checks.append({"name": "Model", "ok": False, "detail": "Endpoint unavailable; configure a running Ollama service"})
    return checks + await connection_checks(workspace, config)


async def connection_checks(workspace, config):
    checks = []
    for name, server in config.servers.items():
        if not server.enabled:
            continue
        isolated = config.model_copy(deep=True)
        isolated.servers = {name: server}
        try:
            async with ToolBroker(workspace, isolated) as broker:
                count = len([t for t in broker.tools.values() if t["server"] == name])
            checks.append({"name": name, "ok": True, "detail": f"{count} MCP tools discovered"})
        except Exception:
            checks.append({"name": name, "ok": False, "detail": "MCP initialization failed; check command, endpoint and environment"})
    return checks


async def dispatch(args, workspace, terminal):
    if args.command == "mcp" and args.operation == "qualify":
        from pi_qualification import qualify
        return await qualify(workspace, args.file)
    if args.command == "mcp" and args.operation == "schema":
        from pi_workspace import fingerprint
        async with ToolBroker(workspace, workspace.config(), [args.tool]) as broker:
            if args.tool not in broker.tools or broker.tools[args.tool]["server"] == "local":
                raise UserError("Configured MCP tool not found")
            tool = broker.tools[args.tool]
            return {"tool": args.tool, "read": tool["read"], "inputSchema": tool["inputSchema"],
                    "input_schema_sha256": fingerprint(tool["inputSchema"])}
    config = workspace.config()
    command = args.command
    engine = Engine(workspace, None if args.json else terminal.event)
    if command in {"init", "setup"}:
        if not workspace.config_path.exists():
            workspace.save(config)
        return {"status": "configured", "workspace": str(workspace.root), "config": str(workspace.config_path),
                "next": "model set MODEL --endpoint URL" if not config.model.model else "run YOUR_TASK"}
    if command == "model":
        if args.operation == "set":
            config.model = config.model.model_copy(update={"provider": args.provider, "model": args.model, "endpoint": args.endpoint, "token_env": args.token_env})
            workspace.save(config)
        return config.model.model_dump()
    if command == "agent":
        if args.operation == "set":
            config.agents[args.name] = AgentSettings(role=args.role, tools=args.tools, max_steps=args.max_steps)
            if args.model:
                from pi_workspace import ModelSettings
                config.agents[args.name].model = ModelSettings(provider=args.provider, model=args.model)
            workspace.save(config)
        elif args.operation in {"enable", "disable"}:
            if args.name not in config.agents:
                raise UserError("Agent not found")
            config.agents[args.name].enabled = args.operation == "enable"
            workspace.save(config)
        return {name: value.model_dump() for name, value in config.agents.items()}
    if command == "mcp":
        if args.operation == "add":
            if bool(args.url) == bool(args.server_command):
                raise UserError("Supply exactly one of --url or --command")
            config.servers[args.name] = ServerSettings(transport="http" if args.url else "stdio",
                command=args.server_command or "", args=args.arg, url=args.url or "",
                env=args.env, token_env=args.token_env, read_tools=args.read_tools)
            workspace.save(config)
        elif args.operation == "remove":
            if args.name not in config.servers:
                raise UserError("MCP connection not found")
            del config.servers[args.name]
            workspace.save(config)
        return {name: value.model_dump() for name, value in config.servers.items()}
    if command == "tools":
        async with ToolBroker(workspace, config) as broker:
            return list(broker.tools.values())
    if command == "agents":
        return {name: value.model_dump() for name, value in config.agents.items()}
    if command == "graph":
        return GRAPH
    if command == "run":
        with terminal.busy("Working on your task") if not args.json else contextlib.nullcontext():
            return await engine.start(args.request, args.agent)
    if command == "call":
        return await engine.propose_tool(args.tool, json.loads(args.arguments), args.agent)
    if command in {"approve", "resume"}:
        return await engine.advance(args.id, args.hash if command == "approve" else None)
    if command == "reject":
        return engine.reject(args.id)
    if command == "reconcile":
        return engine.reconcile(args.id, args.outcome, args.evidence)
    if command == "runs":
        return workspace.runs()
    if command == "show":
        return workspace.task(args.id)
    if command == "trace":
        return workspace.events(args.id)
    if command == "receipt":
        return [c["receipt"] for c in workspace.task(args.id)["calls"] if "receipt" in c]
    if command == "doctor":
        return await doctor(workspace)
    if command == "workflow":
        from pi_workflow import run_workflow
        return await run_workflow(workspace, Path(args.file), engine)
    if command in {"knowledge", "memory"}:
        from pi_knowledge import Knowledge
        knowledge = Knowledge(workspace)
        if command == "knowledge":
            if args.operation == "add":
                return knowledge.ingest(args.path)
            if args.operation == "list":
                return knowledge.sources()
            if args.operation == "search":
                return knowledge.search(args.query)
            return knowledge.forget_source(args.id)
        if args.operation == "add":
            return knowledge.remember(args.title, args.body, args.source, args.ttl_days, args.id)
        if args.operation == "remove":
            return knowledge.forget(args.id)
        return knowledge.memories(args.query if args.operation == "search" else "")
    if command in {"backup", "restore", "metrics"}:
        import pi_operations
        if command == "metrics":
            return pi_operations.metrics(workspace)
        return getattr(pi_operations, command)(workspace, args.path, args.key_env)
    if command == "workspace":
        return select_workspace(args.path) if args.operation == "use" else {"workspace": str(workspace.root)}
    if command == "check":
        if args.operation == "add":
            config.checks[args.name] = [args.check_command, *args.arg]
            workspace.save(config)
        return config.checks
    raise UserError("Unknown command. Use --help for available commands.")


def display(result, terminal, as_json=False, command=None):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    elif command == "graph":
        terminal.text("  TASK EXECUTION", "bold")
        terminal.text("  Intake -> Context -> Propose -> Policy")
        terminal.text("                          |          |")
        terminal.text("                       Complete    Review (writes)")
        terminal.text("                                     |")
        terminal.text("                                  Execute -> Verify")
        terminal.text("                                     |          |")
        terminal.text("                                 Unresolved   Propose")
        terminal.text("\n  Review can reject. Every loop consumes the task budget.", "dim")
    elif command in {"agents", "agent"}:
        for name, agent in result.items():
            terminal.row("INFO" if agent["enabled"] else "WARNING", name, agent["role"])
            terminal.text("    Tools: " + (", ".join(agent["tools"]) or "none"), "dim")
            terminal.text(f"    Budget: {agent['max_steps']} steps / {agent['deadline_seconds']} seconds", "dim")
    elif command == "mcp" and "probes" in result:
        terminal.row("SUCCEEDED" if result["status"] == "passed" else "FAILED",
                     "Integration qualification " + result["status"], result["id"])
        for probe in result["probes"]:
            terminal.row("SUCCEEDED" if probe["passed"] else "FAILED", probe["name"],
                         f"{probe['tool']} | {probe['seconds']} s" +
                         (" | " + probe["error_type"] if "error_type" in probe else ""), level=1)
    elif command == "mcp" and "input_schema_sha256" in result:
        terminal.row("INFO", result["tool"], "Read permitted" if result["read"] else "Review required")
        terminal.text("Schema hash: " + result["input_schema_sha256"])
        terminal.text(json.dumps(result["inputSchema"], indent=2))
    elif command == "mcp":
        if not result:
            terminal.row("INFO", "No MCP connections", "pi-engineering mcp add --help")
        for name, server in result.items():
            terminal.row("INFO", name, server["url"] or " ".join([server["command"], *server["args"]]))
    elif command == "model":
        terminal.row("INFO", result["model"] or "No model selected",
                     "Codex CLI (saved authentication)" if result["provider"] == "codex" else result["endpoint"])
    elif command in {"setup", "init"}:
        terminal.row("SUCCEEDED", "Workspace initialized", result["workspace"])
        terminal.text("  pi-engineering " + result["next"], "cyan")
    elif command == "check":
        if not result:
            terminal.row("INFO", "No verification commands registered")
        for name, argv in result.items():
            terminal.row("INFO", name, shlex.join(argv))
    elif command == "workspace":
        terminal.row("INFO", "Active workspace", result.get("workspace", ""))
    elif command == "knowledge" and isinstance(result, list):
        if not result:
            terminal.row("INFO", "No matching sources")
        for item in result:
            terminal.row("INFO", item.get("title", item.get("uri", "Source")), item.get("locator", item.get("id", "")))
            if item.get("body"):
                terminal.text("    " + item["body"][:400], "dim")
    elif command == "memory" and isinstance(result, list):
        if not result:
            terminal.row("INFO", "No saved memory matches")
        for item in result:
            terminal.row("INFO", item["title"], f"{item['id']} | version {item['version']} | {item['source']}")
            terminal.text("    " + item["body"][:400], "dim")
    elif command in {"backup", "restore"}:
        terminal.row("SUCCEEDED", "Backup encrypted" if command == "backup" else "Backup restored",
                     result.get("backup", result.get("restored", "")))
    elif command == "metrics":
        terminal.row("INFO", f"{result['tasks']} tasks", f"{result['model_steps']} model steps / {result['tool_calls']} tool calls")
        for status, count in result["states"].items():
            terminal.text(f"    {status}: {count}")
    elif isinstance(result, dict) and "calls" in result:
        terminal.task(result)
    elif isinstance(result, list) and result and isinstance(result[0], dict) and "calls" in result[0]:
        terminal.runs(result)
    elif isinstance(result, list) and result and isinstance(result[0], dict) and "ok" in result[0]:
        for item in result:
            terminal.row("SUCCEEDED" if item["ok"] else "WARNING", item["name"], item["detail"])
    elif isinstance(result, list) and result and isinstance(result[0], dict) and "inputSchema" in result[0]:
        for item in result:
            terminal.row("INFO", item["name"], "Read permitted" if item["read"] else "Review required")
            terminal.text("    " + item["description"], "dim")
    else:
        terminal.text(json.dumps(result, indent=2, ensure_ascii=False))


def interactive(workspace, terminal):
    import readline
    terminal.command_prefix = "/"
    commands = ["/help", "/setup", "/model", "/mcp", "/agents", "/agent", "/tools", "/runs", "/show", "/approve", "/reject", "/resume", "/graph", "/doctor", "/knowledge", "/memory", "/metrics", "/backup", "/restore", "/check", "/workspace", "/workflow", "/quit"]
    def complete(text, state):
        matches = [name for name in commands if name.startswith(text)]
        return matches[state] if state < len(matches) else None
    readline.set_completer(complete)
    readline.parse_and_bind("bind ^I rl_complete" if "libedit" in (readline.__doc__ or "") else "tab: complete")
    config = workspace.config()
    terminal.header(workspace, config)
    if not config.model.model:
        terminal.row("WARNING", "Connect a model", "/model set MODEL --endpoint URL")
    terminal.text("  What would you like to work on?", "bold")
    terminal.text("  /help  commands    /tools  connections    /runs  history", "dim")
    agent = "engineer"
    while True:
        try:
            line = input(f"\n{agent} > ").strip()
        except EOFError:
            return 0
        except KeyboardInterrupt:
            terminal.text()
            continue
        if not line:
            continue
        if line in {"/quit", "/exit"}:
            return 0
        if line == "/help":
            terminal.help()
            continue
        if line.startswith("/agent ") and len(line.split()) == 2:
            selected = line.split(maxsplit=1)[1]
            if selected in workspace.config().agents and workspace.config().agents[selected].enabled:
                agent = selected
                terminal.row("INFO", f"Agent: {agent}")
            else:
                terminal.row("FAILED", "Agent unavailable", "Use /agents")
            continue
        try:
            tokens = shlex.split(line[1:]) if line.startswith("/") else ["run", line, "--agent", agent]
            args = parser().parse_args(tokens)
            args.json = False
            if "--workspace" in tokens or any(t.startswith("--workspace=") for t in tokens):
                workspace = Workspace(args.workspace)
            result = asyncio.run(dispatch(args, workspace, terminal))
            display(result, terminal, command=args.command)
            if args.command == "workspace" and args.operation == "use":
                workspace = Workspace(args.path)
                agent = "engineer"
                terminal.header(workspace, workspace.config())
        except KeyboardInterrupt:
            terminal.row("WARNING", "Task interrupted", "Use /runs to inspect the checkpoint")
        except SystemExit:
            continue
        except Exception as exc:
            terminal.row("FAILED", str(exc) if isinstance(exc, (UserError, ValueError)) else type(exc).__name__,
                         "Use /doctor to check connections")


def main(argv=None):
    args = parser().parse_args(argv)
    terminal = Terminal(args.plain, not args.no_animate)
    try:
        workspace = Workspace(args.workspace)
        if args.command == "mcp-server":
            from pi_server import serve
            serve(workspace)
            return 0
        if args.command in {None, "launch", "home"}:
            if sys.stdin.isatty() and sys.stdout.isatty() and not args.json and args.command != "home":
                return interactive(workspace, terminal)
            if args.json:
                display({"workspace": str(workspace.root), "configured": workspace.config_path.exists(),
                         "model": workspace.config().model.model, "runs": workspace.runs()}, terminal, True)
            else:
                terminal.header(workspace, workspace.config())
                if not workspace.config().model.model:
                    terminal.row("WARNING", "Model not configured", "pi-engineering model set MODEL --endpoint URL")
                terminal.runs(workspace.runs())
                terminal.text("\n  pi-engineering --help", "cyan")
            return 0
        result = asyncio.run(dispatch(args, workspace, terminal))
        display(result, terminal, args.json, args.command)
        if args.command == "doctor":
            return 0 if all(c["ok"] for c in result) else 1
        if isinstance(result, dict) and result.get("status") in {"failed", "unresolved", "budget_exhausted", "verification_failed"}:
            return 1
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        message = str(exc) if isinstance(exc, UserError) else "Invalid configuration or input" if isinstance(exc, (ValidationError, ValueError)) else type(exc).__name__
        if args.json:
            print(json.dumps({"error": message}), file=sys.stderr)
        else:
            terminal.row("FAILED", message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
