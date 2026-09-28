"""Persona presets for the Pi Engineering platform.

Presets overlay agent roles, optional checks, and workflow hints onto an
existing workspace configuration. They never delete servers, agents, or checks
the operator already configured unless explicitly replacing agents.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pi_workspace import AgentSettings, UserError


PACKAGE_PRESETS = Path(__file__).resolve().parent / "presets"
# Wheel installs place presets under sys.prefix/share/pi-engineering/presets.
INSTALLED_PRESETS = Path(sys.prefix) / "share" / "pi-engineering" / "presets"


def preset_dirs():
    return [PACKAGE_PRESETS, INSTALLED_PRESETS]


def list_presets():
    found = {}
    for directory in preset_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            found[path.stem] = path
    return found


def load_preset(name: str):
    presets = list_presets()
    path = presets.get(name)
    if path is None:
        known = ", ".join(sorted(presets)) or "(none)"
        raise UserError(f"Unknown profile {name!r}. Available: {known}")
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise UserError(f"Profile {name} is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("name") != name:
        raise UserError(f"Profile {name} must be an object with matching name")
    return data, path


def apply_preset(config, name: str, *, replace_agents: bool = False):
    """Merge a persona preset into config.

    Existing MCP servers are always preserved. By default, existing agents and
    checks are left unchanged; missing ones are added. Pass replace_agents to
    overlay agent/check definitions from the preset.
    """
    data, path = load_preset(name)
    applied = {
        "profile": name,
        "path": str(path),
        "agents": [],
        "checks": [],
        "skipped_agents": [],
        "skipped_checks": [],
        "default_workflow": data.get("default_workflow"),
        "audience": data.get("audience"),
        "description": data.get("description"),
        "model_hint": data.get("model_hint"),
    }
    for agent_name, settings in (data.get("agents") or {}).items():
        if agent_name in config.agents and not replace_agents:
            applied["skipped_agents"].append(agent_name)
            continue
        config.agents[agent_name] = AgentSettings(**settings)
        applied["agents"].append(agent_name)
    for check_name, argv in (data.get("checks") or {}).items():
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            raise UserError(f"Profile check {check_name} must be a string argv list")
        if check_name in config.checks and not replace_agents:
            applied["skipped_checks"].append(check_name)
            continue
        config.checks[check_name] = list(argv)
        applied["checks"].append(check_name)
    return config, applied


def export_recipe(config) -> dict:
    """Shareable workspace recipe without secrets."""
    return {
        "version": 1,
        "kind": "pi-engineering-recipe",
        "model": {
            "provider": config.model.provider,
            "endpoint": config.model.endpoint,
            "model": config.model.model,
            "token_env": config.model.token_env,
            "timeout": config.model.timeout,
            "context_chars": config.model.context_chars,
            "output_tokens": config.model.output_tokens,
        },
        "agents": {name: agent.model_dump() for name, agent in config.agents.items()},
        "checks": config.checks,
        "servers": {name: server.model_dump() for name, server in config.servers.items()},
    }
