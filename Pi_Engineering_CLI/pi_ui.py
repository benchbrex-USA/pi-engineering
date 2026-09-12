"""Terminal experience layer for Pi Engineering CLI.

The UI is deliberately dependency-free and script-safe. Human output gets
structured panels, status maps and optional lightweight animation. JSON output
and MCP responses bypass this layer entirely.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import textwrap
from typing import Any, Iterable


GRAPH_NODES = ["intent", "evidence", "proposal", "policy", "verification", "reflection"]


class TerminalUI:
    def __init__(self, plain: bool = False, animate: bool = True, stream: Any | None = None):
        self.stream = stream or sys.stdout
        self.plain = plain
        self.color = self._supports_color() and not plain
        self.unicode = supports_utf8() and not plain
        self.animate = animate and self.color and self.stream.isatty()
        self._last_progress_len = 0
        self.command = command_label()

    def _supports_color(self) -> bool:
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("TERM") == "dumb":
            return False
        return bool(getattr(self.stream, "isatty", lambda: False)())

    def c(self, text: str, name: str) -> str:
        if not self.color:
            return text
        codes = {
            "muted": "2",
            "bold": "1",
            "green": "32",
            "yellow": "33",
            "red": "31",
            "blue": "34",
            "cyan": "36",
            "magenta": "35",
            "accent": "38;2;96;165;250",
            "success": "38;2;74;222;128",
            "warn": "38;2;250;204;21",
            "danger": "38;2;248;113;113",
            "border": "38;2;99;102;241",
        }
        return f"\033[{codes.get(name, '0')}m{text}\033[0m"

    def raw_style(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def render(self, payload: Any, view: str | None = None) -> str:
        if view == "home":
            return self.home(payload)
        if view == "tour":
            return self.tour()
        if view == "demo":
            return self.demo(payload)
        if view == "init":
            return self.init(payload)
        if view == "run":
            return self.run_summary(payload)
        if view == "state":
            return self.state(payload)
        if view == "agents":
            return self.agents(payload)
        if view == "policies":
            return self.policies(payload)
        if view == "why":
            return self.why(payload)
        if view == "trace":
            return self.trace(payload)
        if view == "receipt":
            return self.receipt(payload)
        if view == "eval":
            return self.eval(payload)
        if view == "palette":
            return self.palette(payload)
        if view == "doctor":
            return self.doctor(payload)
        if view == "preview":
            return self.preview()
        return self.generic(payload)

    def banner(self, title: str, subtitle: str = "") -> str:
        width = min(max(72, len(title) + 8, len(subtitle) + 8), terminal_width())
        tl, tr, bl, br, h, v = self.box_chars()
        lines = [
            tl + h * (width - 2) + tr,
            v + " " + pad_ansi(self.c(title, "bold"), width - 4) + " " + v,
        ]
        if subtitle:
            lines.append(v + " " + pad_ansi(self.c(subtitle, "muted"), width - 4) + " " + v)
        lines.append(bl + h * (width - 2) + br)
        return "\n".join(lines)

    def panel(self, title: str, lines: Iterable[str]) -> str:
        width = min(max(56, len(strip_ansi(title)) + 8), terminal_width())
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(wrap_line(line, width - 4))
        width = min(
            max([len(strip_ansi(title)) + 8] + [len(strip_ansi(line)) + 4 for line in wrapped] + [52]),
            terminal_width(),
        )
        tl, tr, bl, br, h, v = self.box_chars()
        left, right, sep_left, sep_right = self.side_chars()
        output = [tl + h * (width - 2) + tr, v + " " + pad_ansi(self.c(title, "bold"), width - 4) + " " + v]
        output.append(sep_left + h * (width - 2) + sep_right)
        for line in wrapped:
            output.append(left + " " + pad_ansi(line, width - 4) + " " + right)
        output.append(bl + h * (width - 2) + br)
        return "\n".join(output)

    def table(self, headers: list[str], rows: list[list[Any]]) -> str:
        values = [[str(cell) for cell in row] for row in rows]
        widths = [
            max(len(headers[i]), *(len(strip_ansi(row[i])) for row in values)) if values else len(headers[i])
            for i in range(len(headers))
        ]
        def row_line(cells: list[str]) -> str:
            return "  ".join(pad_ansi(cell, widths[index]) for index, cell in enumerate(cells))

        output = [row_line([self.c(head, "bold") for head in headers])]
        output.append(row_line(["-" * width for width in widths]))
        for row in values:
            output.append(row_line(row))
        return "\n".join(output)

    def section(self, title: str, lines: Iterable[str]) -> str:
        output = [self.c(title, "bold")]
        output.extend(lines)
        return "\n".join(output)

    def hint(self, text: str) -> str:
        marker = "›" if self.unicode else ">"
        return "  " + self.c(marker, "accent") + " " + text

    def status_key(self, status: str) -> str:
        return {
            "success": "ok",
            "succeeded": "ok",
            "pass": "ok",
            "passed": "ok",
            "processing": "run",
            "sync": "run",
            "syncing": "run",
            "running": "run",
            "warning": "warn",
            "failed": "error",
            "fail": "error",
            "failure": "error",
            "help": "info",
            "idle": "wait",
            "waiting": "wait",
        }.get(status, status)

    def icon_char(self, status: str) -> str:
        status = self.status_key(status)
        if self.unicode:
            icons = {
                "ok": "✓",
                "warn": "▲",
                "error": "×",
                "wait": "○",
                "run": "*",
                "info": "ⓘ",
            }
        else:
            icons = {
                "ok": "OK",
                "warn": "!",
                "error": "X",
                "wait": "-",
                "run": "*",
                "info": "i",
            }
        return icons.get(status, icons["info"])

    def icon(self, status: str) -> str:
        status = self.status_key(status)
        color = {
            "ok": "success",
            "warn": "warn",
            "error": "danger",
            "run": "accent",
            "wait": "muted",
            "info": "muted",
        }.get(status, "muted")
        return self.c(self.icon_char(status), color)

    def status_label(self, status: str) -> str:
        status = self.status_key(status)
        return {
            "ok": "SUCCEEDED",
            "run": "PROCESSING",
            "info": "INFO",
            "warn": "WARNING",
            "error": "FAILED",
            "wait": "WAITING",
        }.get(status, status.upper())

    def status_color(self, status: str) -> str:
        status = self.status_key(status)
        return {
            "ok": "success",
            "run": "accent",
            "info": "blue",
            "warn": "warn",
            "error": "danger",
            "wait": "muted",
        }.get(status, "muted")

    def pill(self, status: str, label: str | None = None) -> str:
        status = self.status_key(status)
        text = label or self.status_label(status)
        raw = f" {self.icon_char(status)} {text} "
        if not self.color:
            return "[" + raw.strip() + "]"
        styles = {
            "ok": "1;30;48;2;34;197;94",
            "run": "1;30;47",
            "info": "1;37;44",
            "warn": "1;30;48;2;250;204;21",
            "error": "1;37;48;2;239;68;68",
            "wait": "1;37;100",
        }
        return self.raw_style(raw, styles.get(status, "1;37;100"))

    def rule(self, width: int | None = None) -> str:
        h = "─" if self.unicode else "-"
        return self.c(h * (width or min(terminal_width(), 110)), "muted")

    def component_label(self, text: str) -> str:
        raw = " " + text + " "
        if not self.color:
            return text
        return self.raw_style(raw, "1;38;2;167;139;250;48;2;30;27;75")

    def header_component(self, title: str, subtitle: str = "",
                         fields: dict[str, Any] | None = None) -> str:
        width = min(terminal_width(), 110)
        field_text = ""
        if fields:
            field_text = "   ".join(
                self.c(str(key), "muted") + " " + self.c(str(value), "bold")
                for key, value in fields.items()
            )
        left_width = max(30, width - len(strip_ansi(field_text)) - 3)
        title_line = pad_ansi(self.c(title, "bold"), left_width)
        if field_text:
            title_line += " " + field_text
        lines = [self.rule(width), title_line]
        if subtitle:
            lines.append(self.c(subtitle, "muted"))
        lines.append(self.rule(width))
        return "\n".join(lines)

    def callout(self, status: str, title: str, body: str) -> str:
        status = self.status_key(status)
        clean_body = wrap_line(body, min(terminal_width(), 78) - 4)
        width = min(
            max(
                len(strip_ansi(self.pill(status))) + len(title) + 6,
                *(len(strip_ansi(line)) + 4 for line in clean_body),
                52,
            ),
            terminal_width(),
        )
        tl, tr, bl, br, h, v = self.box_chars()
        border_color = self.status_color(status)
        output = [self.c(tl + h * (width - 2) + tr, border_color)]
        headline = self.pill(status) + " " + self.c(title, "bold")
        output.append(self.c(v, border_color) + " " + pad_ansi(headline, width - 4) + " " + self.c(v, border_color))
        for line in clean_body:
            output.append(self.c(v, border_color) + " " + pad_ansi(self.c(line, "muted"), width - 4) + " " + self.c(v, border_color))
        output.append(self.c(bl + h * (width - 2) + br, border_color))
        return "\n".join(output)

    def rule_row(self, status: str, name: str, detail: str = "",
                 meta: str = "", progress: float | None = None, level: int = 1) -> str:
        indent = "  " * level
        pieces = [
            indent + pad_ansi(self.pill(status), 16),
            pad_ansi(self.c(name, "bold"), 20),
        ]
        if detail:
            pieces.append(detail)
        if progress is not None:
            pieces.append(self.progress_bar(progress, 12))
            pieces.append(f"{int(max(0.0, min(1.0, progress)) * 100)}%")
        if meta:
            pieces.append(self.c(meta, "muted"))
        return " ".join(pieces)

    def progress_bar(self, ratio: float, width: int = 14) -> str:
        ratio = max(0.0, min(1.0, ratio))
        filled = int(round(ratio * width))
        if self.unicode:
            bar = "█" * filled + "░" * (width - filled)
        else:
            bar = "#" * filled + "-" * (width - filled)
        color = "success" if ratio >= 1.0 else "accent" if ratio > 0.0 else "muted"
        return self.c(bar, color)

    def status_row(self, status: str, label: str, value: Any = "",
                   detail: str = "", level: int = 1, ratio: float | None = None) -> str:
        indent = "  " * level
        pieces = [
            indent + self.icon(status),
            pad_ansi(self.c(label, "bold") if level == 0 else label, 16),
        ]
        if ratio is not None:
            pieces.append(self.progress_bar(ratio))
        if value != "":
            pieces.append(str(value))
        if detail:
            pieces.append(self.c(detail, "muted"))
        return " ".join(pieces)

    def command_row(self, command: str, description: str, level: int = 1) -> str:
        indent = "  " * level
        marker = self.c("›" if self.unicode else ">", "accent")
        return indent + marker + " " + pad_ansi(self.c(command, "accent"), 42) + " " + description

    def process_tree(self, completed: Iterable[str] = (), active: str | None = None,
                     failed: str | None = None) -> list[str]:
        done = set(completed)
        output = []
        for index, node in enumerate(GRAPH_NODES):
            if node == failed:
                status, ratio, detail = "error", 1.0, "blocked"
            elif node == active:
                status, ratio, detail = "run", 0.55, "running"
            elif node in done:
                status, ratio, detail = "ok", 1.0, "complete"
            else:
                status, ratio, detail = "wait", 0.0, "waiting"
            prefix = "└─" if self.unicode and index == len(GRAPH_NODES) - 1 else "├─" if self.unicode else "-"
            output.append("  " + self.c(prefix, "muted") + " " + self.status_row(status, node, detail=detail, level=0, ratio=ratio))
        return output

    def box_chars(self) -> tuple[str, str, str, str, str, str]:
        if self.unicode:
            return "╭", "╮", "╰", "╯", "─", "│"
        return "+", "+", "+", "+", "-", "|"

    def side_chars(self) -> tuple[str, str, str, str]:
        if self.unicode:
            return "│", "│", "├", "┤"
        return "|", "|", "+", "+"

    def workflow(self, active: str | None = None, completed: Iterable[str] = ()) -> str:
        done = set(completed)
        chunks = []
        for node in GRAPH_NODES:
            if node == active:
                label = self.c("[" + node.upper() + "]", "cyan")
            elif node in done:
                label = self.c("[" + node + ":ok]", "green")
            else:
                label = "[" + node + "]"
            chunks.append(label)
        return " -> ".join(chunks)

    def progress_event(self, event: dict[str, Any]) -> None:
        if not self.animate:
            return
        kind = event.get("type")
        node = event.get("node")
        if kind == "node_started" and node:
            for frame in "-\\|/":
                message = f"{frame} Pi graph {self.workflow(active=node)}"
                self._write_progress(message)
                time.sleep(0.035)
        elif kind == "node_finished" and node:
            completed = event.get("completed", [])
            self._write_progress(f"* Pi graph {self.workflow(completed=completed)}")
        elif kind == "run_finished":
            self.clear_progress()

    def _write_progress(self, message: str) -> None:
        clean_len = len(strip_ansi(message))
        padding = " " * max(0, self._last_progress_len - clean_len)
        self.stream.write("\r" + message + padding)
        self.stream.flush()
        self._last_progress_len = clean_len

    def clear_progress(self) -> None:
        if not self._last_progress_len:
            return
        self.stream.write("\r" + " " * self._last_progress_len + "\r")
        self.stream.flush()
        self._last_progress_len = 0

    def tour(self) -> str:
        return "\n\n".join([
            self.header_component(
                "Pi Engineering CLI",
                "agents propose, policy gates, receipts prove",
                {"mode": "guided", "surface": "terminal"},
            ),
            self.section("Start Here", [
                self.command_row(self.command + " init", "prepare local state"),
                self.command_row(self.command + " demo", "walk through the safe sample"),
                self.command_row(self.command + " run --tenant aster --actor alice \"Mark T-100 pending\"", "run a governed task"),
                self.command_row(self.command + " approve RUN_ID --actor alice", "commit only after review"),
            ]),
            self.section("Operating Model", [
                self.rule_row("run", "Agents", "propose typed actions"),
                self.rule_row("ok", "Policy", "checks tenant, version and evidence"),
                self.rule_row("ok", "Approval", "binds action hash before commit"),
                self.rule_row("ok", "Receipt", "proves exactly what changed"),
            ]),
            self.section("Find Your Way", [
                self.command_row(self.command + " palette approve", "search by intent"),
                self.command_row(self.command + " doctor", "check install health"),
                self.command_row(self.command + " launch", "open interactive mode"),
                self.command_row(self.command + " trace RUN_ID --json", "machine-readable audit path"),
            ]),
        ])

    def home(self, payload: dict[str, Any]) -> str:
        state = payload.get("state", {})
        eval_result = state.get("latest_eval") or {}
        eval_status = "not run"
        if eval_result:
            eval_status = f"{eval_result.get('passed', 0)}/{eval_result.get('total', 0)} passing"
        run_status = "run" if state.get("runs") else "wait"
        eval_key = "ok" if eval_result else "warn"
        top = [
            self.header_component(
                "Pi Engineering Command Center",
                "governed agent operations for the terminal",
                {"actor": "operator", "repository": "local", "mode": "approval-first"},
            ),
            self.section("Signals", [
                self.table(
                    ["Signal", "Value", "Meaning"],
                    [
                        ["Tickets", len(state.get("tickets", [])), "tenant work queue"],
                        ["Agents", len(state.get("agents", [])), "registered roles"],
                        ["Policies", len(state.get("policy_rules", [])), "governance rules"],
                        ["Runs", len(state.get("runs", [])), "recent graph executions"],
                        ["Eval", eval_status, "quality gate"],
                    ],
                ),
            ]),
            self.section("Workflow", [
                self.rule_row("ok", "Intent", "request interpreted and scoped"),
                self.rule_row("ok", "Evidence", "tenant-scoped manifest only"),
                self.rule_row("ok", "Proposal", "typed action or answer"),
                self.rule_row("ok", "Policy", "governance rule check"),
                self.rule_row("ok", "Verify", "version and hash proof"),
                self.rule_row("wait", "Approve", "human gate before commit"),
            ]),
            self.section("System Readiness", [
                self.rule_row("ok", "Tickets", "tenant queue available", str(len(state.get("tickets", []))) + " loaded"),
                self.rule_row("ok", "Agents", "roles and tools registered", str(len(state.get("agents", []))) + " roles"),
                self.rule_row("ok", "Policies", "requirements loaded", str(len(state.get("policy_rules", []))) + " rules"),
                self.rule_row(run_status, "Runs", "recent graph executions", str(len(state.get("runs", []))) + " runs"),
                self.rule_row(eval_key, "Eval", "quality gate", eval_status),
            ]),
            self.section("Next Best Actions", [
                self.command_row(self.command + " demo", "guided sample with DEMO-100"),
                self.command_row(self.command + " palette approve", "find approval workflow commands"),
                self.command_row(self.command + " doctor", "verify terminal and install health"),
                self.command_row(self.command + " launch", "keyboard-driven command center"),
            ]),
            self.callout("info", "Use JSON for agents", self.command + " trace RUN_ID --json keeps this same system scriptable through MCP and automation."),
        ]
        return "\n\n".join(top)

    def hero(self, title: str, subtitle: str) -> str:
        return "\n".join([
            self.c(title, "bold"),
            self.c(subtitle, "muted"),
        ])

    def demo(self, payload: dict[str, Any]) -> str:
        run = payload.get("run", {})
        lines = [
            "Seeded a small workspace, then asked Pi to handle a safe sample task.",
            f"Run: {run.get('id', '(unknown)')} [{run.get('status', 'unknown')}]",
        ]
        action = (run.get("proposal") or {}).get("action")
        if action:
            lines.append(f"Proposed: {action['ticket']} -> {action['status']}")
            lines.append("Next: " + self.command + " approve " + run["id"] + " --actor " + run["actor"])
            lines.append("Inspect first: " + self.command + " why " + run["id"])
        return "\n\n".join([
            self.header_component("Guided Pi Run", "a newcomer-safe walkthrough", {"tenant": run.get("tenant", "-"), "actor": run.get("actor", "-")}),
            self.section("What Happened", [
                self.rule_row("ok", "Seeded", "safe sample workspace"),
                self.rule_row("run", "Run", "[" + run.get("status", "unknown") + "]", run.get("id", "(unknown)")),
                self.rule_row("wait", "Review", "inspect before approval"),
            ] + [self.hint(line) for line in lines[2:]]),
            self.run_summary(run),
        ])

    def init(self, payload: dict[str, Any]) -> str:
        state = payload.get("state", {})
        return "\n\n".join([
            self.header_component("Pi Initialized", "local governed workspace is ready", {"db": str(payload.get("db", "-"))}),
            self.section("Workspace", [
                self.rule_row("ok", "Database", str(payload.get("db", "-"))),
                self.rule_row("ok", "Tickets", str(len(state.get("tickets", [])))),
                self.rule_row("ok", "Agents", str(len(state.get("agents", [])))),
                self.rule_row("ok", "Policies", str(len(state.get("policy_rules", [])))),
            ]),
            self.section("Next Moves", [
                self.command_row(self.command + " tour", "learn the model"),
                self.command_row(self.command + " demo", "run the safe sample"),
                self.command_row(self.command + " state", "inspect local state"),
            ]),
        ])

    def run_summary(self, payload: dict[str, Any]) -> str:
        status = payload.get("status", "unknown")
        action = (payload.get("proposal") or {}).get("action")
        checkpoints = [cp.get("node") for cp in payload.get("checkpoints", [])]
        run_key = "ok" if status in {"answered", "committed"} else "warn" if status == "awaiting_approval" else "run"
        lines = [
            self.rule_row(run_key, "Run", status, payload.get("id", "(unknown)")),
            self.rule_row("ok", "Tenant", str(payload.get("tenant", "-"))),
            self.rule_row("ok", "Actor", str(payload.get("actor", "-"))),
        ]
        for node in GRAPH_NODES:
            done = node in checkpoints
            lines.append(self.rule_row("ok" if done else "wait", node.title(), "complete" if done else "waiting"))
        if action:
            lines.extend([
                self.rule_row("wait", "Action", action["type"]),
                self.rule_row("wait", "Target", action["ticket"] + " -> " + action["status"]),
                self.rule_row("wait", "Hash", str(payload.get("action_hash"))),
            ])
            if status == "awaiting_approval":
                lines.append(self.command_row(self.command + " why " + payload["id"], "review evidence and policy"))
                lines.append(self.command_row(self.command + " approve " + payload["id"] + " --actor " + payload["actor"], "commit with receipt"))
        answer = (payload.get("proposal") or {}).get("answer")
        if answer:
            lines.append(self.rule_row("info", "Answer", answer))
        parts = [self.header_component("Pi Run", "checkpointed graph execution", {"status": status})]
        if status == "awaiting_approval" and action:
            parts.append(self.callout("warn", "Approval required", "Review the explanation and approve only if the proposed action matches the evidence."))
        parts.append(self.section("Run Trace", lines))
        return "\n\n".join(parts)

    def workflow_line(self, labels: list[str]) -> str:
        connector = self.c(" ── ", "muted") if self.unicode else " -> "
        parts = [self.c(label, "accent") for label in labels]
        return connector.join(parts)

    def state(self, payload: dict[str, Any]) -> str:
        ticket_rows = [
            [item["tenant"], item["ticket"], item["status"], "v" + str(item["version"]), item["title"][:42]]
            for item in payload.get("tickets", [])[:8]
        ]
        parts = [self.header_component("Pi State", "workspace at a glance", {"scope": payload.get("tenant") or "all"}), self.section("Summary", [
            self.rule_row("ok", "Tickets", str(len(payload.get("tickets", [])))),
            self.rule_row("ok", "Evidence", str(len(payload.get("evidence", [])))),
            self.rule_row("ok", "Runs", str(len(payload.get("runs", [])))),
            self.rule_row("ok", "Agents", str(len(payload.get("agents", [])))),
            self.rule_row("ok", "Policies", str(len(payload.get("policy_rules", [])))),
        ])]
        if ticket_rows:
            parts.append(self.table(["Tenant", "Ticket", "Status", "Version", "Title"], ticket_rows))
        return "\n\n".join(parts)

    def agents(self, payload: list[dict[str, Any]]) -> str:
        lines = [
            self.rule_row("ok" if item.get("enabled", True) else "wait", item["name"], item["role"][:56], item.get("risk", "medium"))
            for item in payload
        ]
        return "\n\n".join([self.header_component("Pi Agents", "roles, permissions and tool reach", {"count": len(payload)}), self.section("Registry", lines)])

    def policies(self, payload: list[dict[str, Any]]) -> str:
        lines = [
            self.rule_row("ok" if item.get("enabled", True) else "wait", item["action_type"], ",".join(item.get("requires", []))[:64], item["effect"])
            for item in payload
        ]
        return "\n\n".join([self.header_component("Pi Policies", "action requirements before commit", {"count": len(payload)}), self.section("Rules", lines)])

    def why(self, payload: dict[str, Any]) -> str:
        lines = payload.get("decision", [])
        action = payload.get("action")
        if action:
            lines.append("Action target: " + action["ticket"] + " -> " + action["status"])
        return "\n\n".join([
            self.header_component("Why This Run", "decision path and evidence gates", {"run": payload.get("run_id", "")}),
            self.section("Decision", [self.rule_row("info", "Step", line) for line in lines]),
        ])

    def trace(self, payload: dict[str, Any]) -> str:
        checkpoints = payload.get("checkpoints", [])
        rows = [
            [str(index + 1), item["node"], item["route"], item.get("body", {}).get("status", "-")]
            for index, item in enumerate(checkpoints)
        ]
        parts = [self.header_component("Pi Trace", "checkpoints and audit events", {"run": payload.get("run", {}).get("id", "")})]
        if rows:
            parts.append(self.table(["#", "Node", "Route", "Status"], rows))
        audit = payload.get("audit_events", [])
        if audit:
            parts.append(self.section("Audit", [self.rule_row("ok", item["event_type"]) for item in audit]))
        return "\n\n".join(parts)

    def receipt(self, payload: dict[str, Any]) -> str:
        return "\n\n".join([
            self.header_component("Commit Receipt", "idempotent proof of change", {"outcome": payload.get("outcome", "committed")}),
            self.section("Receipt", [
                self.rule_row("ok", "Receipt", payload["receipt_id"]),
                self.rule_row("ok", "Run", payload["run_id"]),
                self.rule_row("ok", "Ticket", payload["ticket"]),
                self.rule_row("ok", "Status", payload["status"]),
                self.rule_row("ok", "Version", str(payload["version"])),
                self.rule_row("info", "Hash", payload["action_hash"]),
            ]),
        ])

    def eval(self, payload: dict[str, Any]) -> str:
        total = max(int(payload.get("total") or 0), 1)
        passed = int(payload.get("passed") or 0)
        return "\n\n".join([
            self.header_component("Pi Eval", f"{passed}/{payload.get('total')} passed; severe_failures={payload.get('severe_failures')}", {"suite": payload.get("suite", "graph")}),
            self.section("Suite", [
                self.rule_row("ok" if passed == payload.get("total") else "warn", "Pass rate", f"{passed}/{payload.get('total')}", progress=passed / total),
            ] + [
                self.rule_row("ok" if case["passed"] else "error", case["name"], "severe" if case["severe"] else "")
                for case in payload.get("cases", [])
            ]),
        ])

    def palette(self, payload: dict[str, Any]) -> str:
        query = payload.get("query") or "all"
        rows = [
            [item["name"], item["category"], item["command"], item["description"][:44]]
            for item in payload.get("matches", [])
        ]
        if not rows:
            rows = [["No match", "-", self.command + " palette", "Try a broader keyword"]]
        return "\n\n".join([
            self.header_component("Pi Command Palette", "search: " + query, {"matches": len(payload.get("matches", []))}),
            self.section("Matches", [
                self.command_row(item["command"], item["name"] + " · " + item["description"], level=1)
                for item in payload.get("matches", [])
            ] or [self.command_row(self.command + " palette", "Try a broader keyword")]),
        ])

    def doctor(self, payload: dict[str, Any]) -> str:
        return "\n\n".join([
            self.header_component("Pi Doctor", "installation and capability check", {"checks": len(payload.get("checks", []))}),
            self.section("Checks", [
                self.rule_row(check["status"] if check["status"] != "fail" else "error", check["name"], check["detail"])
                for check in payload.get("checks", [])
            ]),
        ])

    def preview(self) -> str:
        return "\n\n".join([
            self.header_component(
                "Pi CLI Components",
                "states inspired by command-line interface design practice",
                {"variant": "component-library", "renderer": "ansi"},
            ),
            self.section("Terminal Starting Point", [
                self.rule_row("info", "default", self.command, "ready"),
                self.rule_row("run", "changes", "approval queue has pending work", "needs review"),
                self.rule_row("ok", "up-to-date", "MCP tools and local state are loaded", "current"),
            ]),
            self.section("Feedback States", [
                self.rule_row("run", "PROCESSING", "evidence manifest", "building context", progress=0.58),
                self.rule_row("info", "INFO", "palette", "search by intent, not command names"),
                self.rule_row("ok", "SUCCEEDED", "receipt saved", "action committed with audit trail"),
                self.rule_row("warn", "WARNING", "approval needed", "review policy before commit"),
                self.rule_row("error", "FAILED", "stale version", "rerun with fresh ticket state"),
            ]),
            self.section("Progress Labels", [
                "  " + self.pill("run") + "  processing",
                "  " + self.pill("info") + "        info",
                "  " + self.pill("ok") + "   succeeded",
                "  " + self.pill("warn") + "    warning",
                "  " + self.pill("error") + "     failed",
            ]),
            self.section("Nested Process", [
                self.rule_row("ok", "Intent", "complete"),
                self.rule_row("ok", "Evidence", "complete"),
                self.rule_row("run", "Proposal", "building action", progress=0.55),
                self.rule_row("wait", "Policy", "waiting"),
                self.rule_row("wait", "Verify", "waiting"),
                self.rule_row("wait", "Approve", "waiting"),
            ]),
            self.section("Callouts", [
                self.callout("info", "Update available", "Run " + self.command + " doctor to review installed capabilities."),
                self.callout("ok", "You are ready", "Agents, policies, evals, receipts and MCP tools are wired into one CLI."),
                self.callout("warn", "Approval required", "Effectful actions wait for a human decision before commit."),
                self.callout("error", "Policy blocked", "The requested action did not satisfy tenant scope or version checks."),
            ]),
            self.section("Rule Rows", [
                self.rule_row("ok", "Evidence", "manifest created", "9ms"),
                self.rule_row("run", "Policy", "pulling rules from local registry", "repository"),
                self.rule_row("run", "Verification", "hashing action", "asset", progress=0.35),
                self.rule_row("error", "Commit", "version mismatch at ticket T-100", "rule"),
            ]),
            self.section("Commands", [
                self.command_row(self.command + " run --tenant aster --actor alice \"Mark T-100 pending\"", "start governed execution"),
                self.command_row(self.command + " why RUN_ID", "explain before approve"),
            ]),
        ])

    def generic(self, payload: Any) -> str:
        if isinstance(payload, list):
            if not payload:
                return "(none)"
            first = payload[0]
            if isinstance(first, dict) and {"name", "role", "permissions", "tools"}.issubset(first):
                return self.agents(payload)
            if isinstance(first, dict) and {"id", "action_type", "requires", "effect"}.issubset(first):
                return self.policies(payload)
            return "\n".join(self.generic(item) for item in payload)
        if not isinstance(payload, dict):
            return str(payload)
        if "receipt_id" in payload:
            return self.receipt(payload)
        if {"id", "status", "tenant", "actor", "proposal"}.issubset(payload):
            return self.run_summary(payload)
        if {"passed", "total", "cases"}.issubset(payload):
            return self.eval(payload)
        if "tickets" in payload and "evidence" in payload:
            return self.state(payload)
        if "decision" in payload and "run_id" in payload:
            return self.why(payload)
        return "\n".join(f"{key}: {value}" for key, value in payload.items())


def strip_ansi(value: str) -> str:
    output = []
    i = 0
    while i < len(value):
        if value[i:i + 2] == "\033[":
            i += 2
            while i < len(value) and value[i] != "m":
                i += 1
            i += 1
            continue
        output.append(value[i])
        i += 1
    return "".join(output)


def pad_ansi(value: str, width: int) -> str:
    return value + " " * max(0, width - len(strip_ansi(value)))


def command_label() -> str:
    name = os.path.basename(sys.argv[0] or "")
    if name in {"", "pi.py", "__main__.py"}:
        return "python3 pi.py"
    return name


def terminal_width(default: int = 96) -> int:
    return max(56, min(shutil.get_terminal_size((default, 24)).columns, 120))


def wrap_line(value: str, width: int) -> list[str]:
    clean_width = max(24, width)
    if len(strip_ansi(value)) <= clean_width:
        return [value]
    # Keep wrapping conservative for styled strings; most long wrapped content is unstyled commands.
    return textwrap.wrap(value, clean_width, break_long_words=False, break_on_hyphens=False) or [""]


def supports_utf8() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding
