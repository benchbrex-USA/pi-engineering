"""Transient terminal projection of real engine events, never execution state."""
from dataclasses import dataclass, field
import time

from rich.padding import Padding
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text


COLORS = {"SUCCEEDED": "bold #07110b on #00ed74", "FAILED": "bold #180606 on #ff626c",
          "WARNING": "bold #171301 on #ffe45c", "WAITING": "bold #171301 on #ffe45c",
          "PROCESSING": "bold #031416 on #43e8f1", "INFO": "bold #ffffff on #4968f5"}
PHASES = {"intake": "Recorded", "context": "Context", "propose": "Reasoning",
          "policy": "Policy", "review": "Review", "execute": "Execute", "verify": "Verify",
          "complete": "Finished", "unresolved": "Unresolved", "rejected": "Rejected"}


def badge(status):
    symbol = {"SUCCEEDED": "✓", "FAILED": "×", "WARNING": "!", "WAITING": "Ⅱ",
              "PROCESSING": "●", "INFO": "i"}.get(status, "i")
    return Text(f" {symbol} {status} ", style=COLORS.get(status, COLORS["INFO"]))


def status_label(status):
    if status == "completed":
        return "SUCCEEDED"
    if status in {"awaiting_approval", "interrupted", "unresolved", "rejected"}:
        return "WAITING" if status == "awaiting_approval" else "WARNING"
    if status in {"failed", "verification_failed", "budget_exhausted"}:
        return "FAILED"
    return "PROCESSING"


@dataclass
class Activity:
    agent: str
    task_id: str
    node: str = "intake"
    status: str = "running"
    steps: int = 0
    tool: str = ""
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    observations: list[str] = field(default_factory=list)


class ExecutionView:
    def __init__(self, label, sanitize):
        self.label = sanitize(label)
        self.clean = sanitize
        self.started = time.monotonic()
        self.activities = {}
        self.finished = None
        self.status = "running"
        self.spinner = Spinner("dots", style="#43e8f1")
        self.progress = None

    def event(self, node, details):
        if node == "workflow_progress":
            self.progress = (details["completed"], details["total"])
            return
        if node == "model_started":
            node = "propose"
        identity = details.get("task_id", "task")
        activity = self.activities.setdefault(identity, Activity(self.clean(details.get("agent", "agent")), identity))
        if node != "settled":
            activity.node = node
        activity.status = details.get("status", "running")
        activity.steps = details.get("steps", activity.steps)
        activity.tool = self.clean(details.get("tool", ""))
        if node == "verify" and activity.tool:
            activity.observations.append(activity.tool)
        if node in {"settled", "complete", "review", "unresolved", "rejected"}:
            activity.finished = time.monotonic()
        else:
            activity.finished = None

    def finish(self, result=None, error=False):
        self.finished = time.monotonic()
        if error:
            self.status = "failed"
        elif isinstance(result, dict):
            self.status = result.get("status", "completed")
        elif isinstance(result, list) and any(isinstance(row, dict) and row.get("ok") is False for row in result):
            self.status = "failed"
        else:
            self.status = "completed"
        if self.status in {"passed", "configured"}:
            self.status = "completed"

    def __rich_console__(self, console, options):
        elapsed = (self.finished or time.monotonic()) - self.started
        header = Table.grid(expand=True, padding=(0, 1))
        header.add_column(width=2 if self.finished is None else 14)
        header.add_column(ratio=1)
        header.add_column(justify="right", width=8)
        header.add_row(self.spinner if self.finished is None else badge(status_label(self.status)),
                       Text(self.label, style="bold"), Text(f"{elapsed:.1f}s", style="#8b929c"))
        yield Rule(style="#3f6368")
        yield Padding(header, (1, 0))
        if self.progress is not None:
            completed, total = self.progress
            yield Text(f"  {completed}/{total} workflow nodes completed", style="#8b929c")
            yield Padding(ProgressBar(total=total, completed=completed, complete_style="#00ed74",
                                      finished_style="#00ed74", style="#26333a"), (0, 2, 1, 2))
        activities = list(self.activities.values())
        for index, activity in enumerate(activities):
            state = status_label(activity.status)
            title = Text("└─ " if index == len(activities) - 1 else "├─ ", style="#56646d")
            title.append(activity.agent.upper(), style="bold #43e8f1")
            title.append("  " + self.clean(activity.task_id), style="#8b929c")
            yield Padding(title, (0, 0, 0, 2))
            row = Text("│  ", style="#56646d")
            row.append_text(badge(state))
            row.append(" " + PHASES.get(activity.node, activity.node), style="bold #e2e8ea")
            if activity.tool:
                row.append(" · " + activity.tool, style="#e2e8ea")
            if activity.steps:
                row.append(f"  step {activity.steps}", style="#8b929c")
            yield Padding(row, (0, 0, 0, 2))
            if options.max_width >= 64:
                phases = Text("│  ", style="#56646d")
                for phase in ("context", "propose", "policy", "review", "execute", "verify"):
                    phases.append(PHASES[phase], style="bold #43e8f1" if phase == activity.node else "#8b929c")
                    if phase != "verify":
                        phases.append(" › ", style="#56646d")
                yield Padding(phases, (0, 0, 0, 2))
            for tool in activity.observations[-3:]:
                yield Padding(Text("│  ✓ " + tool + " · observation recorded", style="#00ed74"), (0, 0, 0, 2))
        yield Text("")
        yield Rule(style="#3f6368")
