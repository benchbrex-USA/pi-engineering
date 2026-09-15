"""Scrollback-native interface matching the supplied Specify CLI reference."""
from __future__ import annotations

import contextlib
import os
import re
from rich.live import Live

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding

from pi_workspace import VERSION
from pi_live import COLORS, ExecutionView, status_label


def clean(value):
    text = str(value)
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159
                                                       and c not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))


class Terminal:
    def __init__(self, plain=False, animate=True, console=None):
        self.console = console or Console(highlight=False, markup=False,
                                          no_color=plain or "NO_COLOR" in os.environ,
                                          color_system=None if plain else "auto")
        self.plain = plain
        self.command_prefix = "pi-engineering "
        self.animate = animate and self.console.is_terminal and not plain and "NO_COLOR" not in os.environ
        self.active_view = None

    def text(self, value="", style=None):
        value = clean(value)
        indent = len(value) - len(value.lstrip(" "))
        rendered = Text(value[indent:], style=style or "")
        self.console.print(Padding(rendered, (0, 0, 0, indent)) if indent else rendered)

    def header(self, workspace, config):
        self.console.print(Rule(style="#43e8f1", characters="-" if self.plain else "─"))
        brand = Text()
        brand.append(" PI ", style="bold #071114 on #43e8f1")
        brand.append(" ENGINEERING", style="bold")
        brand.append(f"  {VERSION}", style="#8b929c")
        self.console.print(brand)
        self.text()
        table = Table.grid(expand=True, padding=(0, 3))
        model = config.model.provider + "/" + config.model.model if config.model.model else "Not configured"
        values = [("WORKSPACE", workspace.root.name), ("MODEL", model),
                  ("CAPABILITIES", f"{sum(a.enabled for a in config.agents.values())} agents · {sum(s.enabled for s in config.servers.values())} MCP configured")]
        if self.console.width < 64:
            table.add_column()
            for label, value in values:
                table.add_row(Text(label, style="#8b929c"))
                table.add_row(Text(clean(value), style="bold"))
        else:
            for _ in values:
                table.add_column(ratio=1)
            table.add_row(*(Text(label, style="#8b929c") for label, _ in values))
            table.add_row(*(Text(clean(value), style="bold") for _, value in values))
        self.console.print(table)
        self.console.print(Rule(style="#3f6368", characters="-" if self.plain else "─"))
        self.text()

    def row(self, status, title, detail="", level=0):
        symbols = {"SUCCEEDED": "+" if self.plain else "✓", "FAILED": "x",
                   "WARNING": "!", "INFO": "i", "PROCESSING": "*", "WAITING": "o"}
        line = Text()
        if level:
            line.append(("|- " if self.plain else "├─ "), style="#56646d")
        line.append(f" {symbols.get(status, 'i')} {status} ", style=COLORS.get(status, ""))
        line.append(" " + clean(title), style="bold")
        self.console.print(Padding(line, (0, 0, 0, 2 * (level + 1))))
        if detail:
            self.text("  " * (level + 2) + clean(detail), "dim")

    def busy(self, label):
        if not self.animate:
            self.row("PROCESSING", label)
            return contextlib.nullcontext()
        return self.console.status(Text(" " + clean(label)), spinner="dots", refresh_per_second=8)

    @contextlib.contextmanager
    def operation(self, label):
        view = ExecutionView(label, clean)
        self.active_view = view
        try:
            if self.animate:
                with Live(view, console=self.console, refresh_per_second=10, transient=False):
                    try:
                        yield view
                    except BaseException:
                        view.finish(error=True)
                        raise
            else:
                self.row("PROCESSING", label)
                yield view
        finally:
            self.active_view = None

    def event(self, node, details):
        if self.active_view is not None:
            self.active_view.event(node, details)
            if self.animate:
                return
        if node in {"settled", "model_started", "workflow_progress"}:
            return
        labels = {"intake": "Task recorded", "context": "Gathering context", "propose": "Agent working",
                  "policy": "Checking tool permissions", "review": "Action needs review",
                  "execute": "Executing tool", "verify": "Observation recorded", "complete": "Task finished",
                  "unresolved": "Execution outcome unresolved", "rejected": "Action rejected"}
        status = status_label(details.get("status", "completed")) if node in {"complete", "rejected", "unresolved", "review"} else "PROCESSING" if node in {"propose", "execute"} else "SUCCEEDED"
        self.row(status, labels[node], details.get("tool", ""), level=1)

    def task(self, task):
        self.text()
        status = task["status"]
        self.row("SUCCEEDED" if status == "completed" else "WARNING" if status in {"awaiting_approval", "unresolved", "interrupted"}
                 else "FAILED", status.replace("_", " ").capitalize(), task["id"])
        if task.get("answer"):
            self.text()
            self.text(task["answer"])
        if task.get("error"):
            self.text(task["error"], "red")
        if status == "awaiting_approval":
            call = next(c for c in task["calls"] if c["status"] == "pending")
            self.row("WAITING", call["name"], "Exact proposed arguments")
            import json
            self.text(json.dumps(call["arguments"], indent=2, ensure_ascii=False))
            if "command_preview" in call:
                import shlex
                self.text("Command: " + shlex.join(call["command_preview"]), "bold")
            if call["name"] == "workspace_write":
                import difflib
                self.text("\n  Proposed change", "bold")
                for line in difflib.unified_diff((call.get("before") or "").splitlines(),
                        call["arguments"]["content"].splitlines(), fromfile="before", tofile="after", lineterm=""):
                    self.text(line, "#00ed74" if line.startswith("+") else "#ff626c" if line.startswith("-") else "")
            self.text(f"Action hash  {call['hash']}", "dim")
            self.text(f"{self.command_prefix}approve {task['id']} {call['hash']}", "#43e8f1")
            self.text(f"{self.command_prefix}reject {task['id']}", "dim")
        for call in task["calls"]:
            if call.get("receipt"):
                receipt = call["receipt"]
                self.row("INFO", receipt["id"], f"{call['name']} | {receipt['verification']}")

    def runs(self, runs):
        if not runs:
            self.row("INFO", "No tasks yet")
            return
        for task in runs:
            self.text(task["id"] + "  " + task["status"], "bold")
            self.text("  " + task["request"][:180], "dim")

    def help(self):
        self.text("  WORKSPACE COMMANDS", "bold #43e8f1")
        self.text()
        for command, detail in [
            ("<your task>", "Start a task with the selected agent"),
            ("/model set MODEL --endpoint URL", "Connect a model service"),
            ("/mcp add --help", "Configure a tool server"),
            ("/knowledge add PATH", "Index a source document"),
            ("/knowledge search QUERY", "Search current indexed sources"),
            ("/memory list", "Saved operator knowledge"),
            ("/check list", "Registered verification commands"),
            ("/workspace use PATH", "Switch active project"),
            ("/metrics", "Task outcomes and execution metrics"),
            ("/agent NAME", "Select an agent"), ("/agents", "Agents and allowed tools"),
            ("/tools", "Discover connected MCP tools"), ("/runs", "Recent tasks"),
            ("/show ID", "Task details and action preview"),
            ("/review", "Latest pending action"),
            ("/approve ID HASH", "Execute the exact reviewed action"),
            ("/reject ID", "Reject a proposed action"), ("/resume ID", "Continue an interrupted task"),
            ("/graph", "Execution graph"), ("/doctor", "Check model and MCP connections"),
            ("/help", "Commands"), ("/quit", "Exit"),
        ]:
            self.text("  " + command, "bold cyan")
            self.text("    " + detail, "dim")
