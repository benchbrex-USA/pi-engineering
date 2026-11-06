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
    s.add_argument("--provider", choices=["ollama", "codex", "openai", "grok", "compat"], default="ollama")
    s.add_argument("--endpoint", default="http://127.0.0.1:11434")
    s.add_argument("--token-env", default="")
    s.add_argument("--timeout", type=int, default=None)
    s.add_argument("--context-chars", type=int, default=None)
    s.add_argument("--output-tokens", type=int, default=None)
    m.add_parser("show")
    brain = sub.add_parser("brain").add_subparsers(dest="operation", required=True)
    brain.add_parser("show")
    bs = brain.add_parser("set")
    bs.add_argument("model", help="Any model id your endpoint accepts — Pi does not gate model names")
    bs.add_argument("--provider", choices=["ollama", "codex", "openai", "grok", "compat"], default="compat")
    bs.add_argument("--endpoint", default="https://api.x.ai/v1")
    bs.add_argument("--token-env", default="XAI_API_KEY")
    bs.add_argument("--timeout", type=int, default=300)
    bs.add_argument("--context-chars", type=int, default=500000)
    bs.add_argument("--output-tokens", type=int, default=16384)
    bs.add_argument("--agent-steps", type=int, default=128, help="Raise engineer max_steps for long autonomous runs")
    bs.add_argument("--agent-deadline", type=int, default=7200, help="Raise engineer deadline_seconds")
    brain.add_parser("open", help="Show how open-brain mode works")
    a = sub.add_parser("agent").add_subparsers(dest="operation", required=True)
    a.add_parser("list")
    s = a.add_parser("set")
    s.add_argument("name")
    s.add_argument("--role", required=True)
    s.add_argument("--tools", nargs="*", default=["workspace_files", "workspace_read"])
    s.add_argument("--max-steps", type=int, default=32)
    s.add_argument("--deadline-seconds", type=int, default=1800)
    s.add_argument("--model")
    s.add_argument("--provider", choices=["ollama", "codex", "openai", "grok", "compat"], default="ollama")
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
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true", help="Validate graph offline; no tasks or inference")
    mode.add_argument("--explain", action="store_true", help="Inspect saved node blockers without executing")
    knowledge = sub.add_parser("knowledge").add_subparsers(dest="operation", required=True)
    knowledge.add_parser("add").add_argument("path", help="File to index, relative to the workspace root (text or PDF)")
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
    profile = sub.add_parser("profile").add_subparsers(dest="operation", required=True)
    profile.add_parser("list")
    s = profile.add_parser("show")
    s.add_argument("name")
    s = profile.add_parser("apply")
    s.add_argument("name")
    s.add_argument("--replace-agents", action="store_true",
                   help="Overlay preset agents/checks onto existing names (servers still preserved)")
    recipe = sub.add_parser("recipe").add_subparsers(dest="operation", required=True)
    recipe.add_parser("export")
    system = sub.add_parser("system", help="Analyze software, security, wiring, or generic system graphs")
    system_sub = system.add_subparsers(dest="operation", required=True)
    for operation in ("validate", "inspect", "check"):
        system_sub.add_parser(operation).add_argument("file")
    s = system_sub.add_parser("trace", help="Find the shortest evidence path between two nodes")
    s.add_argument("file")
    s.add_argument("--from", dest="start", required=True)
    s.add_argument("--to", dest="end", required=True)
    s.add_argument("--direction", choices=["downstream", "upstream"], default="downstream")
    s = system_sub.add_parser("impact", help="Calculate upstream or downstream blast radius")
    s.add_argument("file")
    s.add_argument("nodes", nargs="+")
    s.add_argument("--direction", choices=["downstream", "upstream", "both"], default="downstream")
    s.add_argument("--max-depth", type=int)
    s = system_sub.add_parser("sample", help="Create or print a starter system graph")
    s.add_argument("domain", choices=["software", "security", "wiring"])
    s.add_argument("--output")

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
        if config.model.provider in {"openai", "grok", "compat"}:
            from pi_models import OpenAICompatModel
            try:
                token = OpenAICompatModel(config.model)._token()
                ok = bool(token) and bool(config.model.model)
                detail = f"{config.model.provider}/{config.model.model or '?'}" + (
                    " (API key or grok login ready)" if ok else " — set model and API key or run grok login")
            except Exception as exc:
                ok, detail = False, str(exc)
            checks.append({"name": "Model", "ok": ok, "detail": detail})
            return checks + await connection_checks(workspace, config)
        if not config.model.model:
            checks.append({"name": "Model", "ok": False,
                           "detail": "No model configured. Run: pi-engineering model set MODEL --endpoint URL"})
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
    labels = {"run": "Agent execution", "call": "Prepare action", "approve": "Approved execution",
              "resume": "Resume checkpoint", "workflow": "Agent workflow", "profile": "Persona presets", "recipe": "Export shareable recipe", "doctor": "Connection checks",
              "tools": "Discover tools", "backup": "Encrypt backup", "restore": "Restore workspace"}
    label = labels.get(args.command)
    if args.command == "workflow" and (args.validate or args.explain):
        label = None
    if not args.json and label:
        with terminal.operation(label) as view:
            result = await _dispatch(args, workspace, terminal)
            view.finish(result)
            return result
    return await _dispatch(args, workspace, terminal)


async def _dispatch(args, workspace, terminal):
    if args.command == "system":
        from pi_system import check_system, impact, inspect_system, load_system, sample_system, trace, validate_system
        if args.operation == "sample":
            return sample_system(args.domain, args.output)
        if args.operation == "validate":
            return validate_system(args.file)
        graph, digest = load_system(args.file)
        if args.operation == "inspect":
            return inspect_system(graph, digest)
        if args.operation == "check":
            return check_system(graph)
        if args.operation == "trace":
            return trace(graph, args.start, args.end, args.direction)
        return impact(graph, args.nodes, args.direction, args.max_depth)
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
    if command == "brain":
        if args.operation == "open":
            return {
                "philosophy": "Pi scales with the brain you connect. Model ids and OpenAI-compatible endpoints are open.",
                "authority": "Models only propose. Approvals, allowlists, and verification stay operator-controlled.",
                "set": "pi-engineering brain set MODEL --provider compat --endpoint https://YOUR_HOST/v1 --token-env YOUR_KEY_ENV",
                "ceilings": {
                    "max_steps": 10000,
                    "deadline_seconds": 86400,
                    "context_chars": 8000000,
                    "output_tokens": 200000,
                    "timeout": 3600,
                },
            }
        if args.operation == "show":
            agent = config.agents.get("engineer")
            return {
                "brain": config.model.model_dump(),
                "engineer_budget": {
                    "max_steps": agent.max_steps if agent else None,
                    "deadline_seconds": agent.deadline_seconds if agent else None,
                },
                "note": "Performance tracks model quality; raise budgets with brain set when the task needs a longer run.",
            }
        # brain set
        endpoint, token_env = args.endpoint, args.token_env
        if args.provider in {"grok", "compat"} and endpoint in {"", "http://127.0.0.1:11434"}:
            endpoint = "https://api.x.ai/v1"
        if args.provider == "grok" and not token_env:
            # Environment variable name, not a secret value.
            token_env = "XAI_API_KEY"  # nosec
        if args.provider == "openai" and endpoint in {"", "http://127.0.0.1:11434"}:
            endpoint = "https://api.openai.com/v1"
        config.model = config.model.model_copy(update={
            "provider": args.provider,
            "model": args.model,
            "endpoint": endpoint,
            "token_env": token_env,
            "timeout": args.timeout,
            "context_chars": args.context_chars,
            "output_tokens": args.output_tokens,
        })
        if "engineer" in config.agents:
            config.agents["engineer"] = config.agents["engineer"].model_copy(update={
                "max_steps": args.agent_steps,
                "deadline_seconds": args.agent_deadline,
            })
        workspace.save(config)
        return {"brain": config.model.model_dump(),
                "engineer_budget": {"max_steps": args.agent_steps, "deadline_seconds": args.agent_deadline}}

    if command == "model":
        if args.operation == "set":
            endpoint, token_env = args.endpoint, args.token_env
            if args.provider in {"grok", "compat"}:
                if endpoint in {"", "http://127.0.0.1:11434"}:
                    endpoint = "https://api.x.ai/v1"
                if not token_env and args.provider == "grok":
                    # Environment variable name, not a secret value.
                    token_env = "XAI_API_KEY"  # nosec
            elif args.provider == "openai" and endpoint in {"", "http://127.0.0.1:11434"}:
                endpoint = "https://api.openai.com/v1"
            update = {"provider": args.provider, "model": args.model, "endpoint": endpoint, "token_env": token_env}
            for key, attr in (("timeout", "timeout"), ("context_chars", "context_chars"), ("output_tokens", "output_tokens")):
                value = getattr(args, attr, None)
                if value is not None:
                    update[key] = value
            config.model = config.model.model_copy(update=update)
            workspace.save(config)
        return config.model.model_dump()
    if command == "agent":
        if args.operation == "set":
            config.agents[args.name] = AgentSettings(role=args.role, tools=args.tools, max_steps=args.max_steps, deadline_seconds=getattr(args, "deadline_seconds", 1800))
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
        from pi_workflow import run_workflow, inspect_workflow
        if args.validate or args.explain:
            return inspect_workflow(workspace, Path(args.file), args.explain)
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
    if command == "profile":
        from pi_profile import apply_preset, list_presets, load_preset
        if args.operation == "list":
            rows = []
            for name, path in list_presets().items():
                data, _ = load_preset(name)
                rows.append({"name": name, "audience": data.get("audience", ""),
                             "description": data.get("description", ""), "path": str(path)})
            return rows
        if args.operation == "show":
            data, path = load_preset(args.name)
            return {**data, "path": str(path)}
        config, applied = apply_preset(config, args.name, replace_agents=getattr(args, "replace_agents", False))
        workspace.save(config)
        return applied
    if command == "recipe":
        from pi_profile import export_recipe
        if args.operation == "export":
            return export_recipe(config)
    raise UserError("Unknown command. Use --help for available commands.")


def display(result, terminal, as_json=False, command=None):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    elif command == "workflow":
        from pi_live import status_label
        terminal.row("INFO" if result["status"] == "validated" else status_label(result["status"]),
                     "Workflow " + result["status"], result["id"])
        if result.get("kind") == "workflow_inspection":
            terminal.text("  Revision: " + result["revision"], "dim")
            terminal.text("  Checkpoint: " + result["compatibility"], "dim")
            for node in result["nodes"]:
                terminal.row("INFO" if node["ready"] else "WARNING" if node["blockers"] else status_label(node["status"]),
                             node["node"], node["reason"].replace("_", " "), level=1)
                if node["task_id"]:
                    terminal.text("    " + node["task_id"], "dim")
                for blocker in node["blockers"]:
                    terminal.text("    Needs " + blocker["node"] + ": " + blocker["status"], "dim")
                if node["resources"]:
                    terminal.text("    Exclusive: " + ", ".join(node["resources"]), "cyan")
                if node["status"] != "completed":
                    terminal.text("    " + node["next_action"], "cyan")
        else:
            for name, task_id in result["nodes"].items():
                terminal.text("    " + name + "  " + task_id)
            if result["status"] != "completed":
                terminal.text("  Use workflow FILE --explain to inspect blockers", "cyan")
    elif command == "system":
        kind = result.get("kind")
        if kind == "system_sample":
            terminal.row("SUCCEEDED", result["domain"].capitalize() + " system graph",
                         result["output"] or "Starter graph")
            if not result["output"]:
                terminal.text(json.dumps(result["graph"], indent=2, ensure_ascii=False))
        elif kind == "system_validation":
            terminal.row("SUCCEEDED", result["name"], f"{result['domain']} | {result['nodes']} nodes | {result['links']} links")
            terminal.text("    Evidence " + result["sha256"], "dim")
        elif kind == "system_inspection":
            status = "FAILED" if result["status"] == "failed" else "WARNING" if result["status"] == "warning" else "SUCCEEDED"
            topology = result["topology"]
            terminal.row(status, result["name"], result["domain"])
            terminal.text(f"    {topology['nodes']} nodes  {topology['links']} links  {topology['components']} components", "bold")
            terminal.text("    Node types  " + ", ".join(f"{name}:{count}" for name, count in result["node_kinds"].items()), "cyan")
            terminal.text("    Link types  " + ", ".join(f"{name}:{count}" for name, count in result["link_kinds"].items()), "cyan")
            if topology["cycles"]:
                terminal.text("    Cycles  " + " -> ".join(topology["cycles"]), "yellow")
            terminal.text(f"    Health  {result['health']['errors']} errors  {result['health']['warnings']} warnings", "dim")
        elif kind == "system_check":
            status = "FAILED" if result["status"] == "failed" else "WARNING" if result["status"] == "warning" else "SUCCEEDED"
            terminal.row(status, result["system"], f"{result['summary']['errors']} errors | {result['summary']['warnings']} warnings")
            for finding in result["findings"]:
                row_status = "FAILED" if finding["severity"] == "ERROR" else "WARNING" if finding["severity"] == "WARNING" else "INFO"
                terminal.row(row_status, finding["code"], finding["message"] + ((" | " + finding["subject"]) if finding["subject"] else ""), level=1)
        elif kind == "system_trace":
            terminal.row("SUCCEEDED" if result["reachable"] else "WARNING",
                         f"{result['from']} -> {result['to']}", f"{result['hops']} hops" if result["reachable"] else "No path")
            if result["path"]:
                terminal.text("    " + "  ->  ".join(result["path"]), "bold cyan")
        elif kind == "system_impact":
            terminal.row("INFO", result["system"], f"{len(result['affected'])} affected | {result['direction']}")
            for node in result["failed"]:
                terminal.row("FAILED", node, "origin", level=1)
            for node in result["affected"]:
                terminal.row("WARNING", node, f"distance {result['distances'][node]}", level=1)
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
    from pi_prompt import Composer
    terminal.command_prefix = "/"
    composer = Composer(plain=terminal.plain or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb")
    config = workspace.config()
    terminal.header(workspace, config)
    if not config.model.model:
        terminal.row("WARNING", "Connect a model", "/model set MODEL --endpoint URL")
    terminal.text("  What are we building?", "bold #43e8f1")
    terminal.text("  /help    /tools    /review    /runs", "dim")
    agent = "engineer"
    while True:
        try:
            line = composer.read(workspace, agent)
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
        if line == "/review":
            pending = next((task for task in workspace.runs() if task["status"] == "awaiting_approval"), None)
            if pending:
                terminal.task(pending)
            else:
                terminal.row("INFO", "No actions awaiting review")
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
        if args.command == "workflow" and result.get("status") in {"rejected", "interrupted"}:
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
