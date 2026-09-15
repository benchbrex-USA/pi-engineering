"""Render visual QA artifacts from an actual local approval/write roundtrip."""
import asyncio
import io
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rich.console import Console
from rich.terminal_theme import TerminalTheme
from pi_engine import Engine
from pi_live import ExecutionView
from pi_terminal import Terminal, clean
from pi_workspace import Workspace


async def main(destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pi-visual-") as temporary:
        root = Path(temporary) / "Pi-Engineering"
        root.mkdir()
        workspace = Workspace(root)
        config = workspace.config()
        config.model.provider, config.model.model = "codex", "default"
        workspace.save(config)
        view = ExecutionView("Workspace change", clean)
        engine = Engine(workspace, event=view.event)
        task = await engine.propose_tool("workspace_write", {
            "path": "release-notes.md", "content": "# Release notes\n\nVerified changes and review receipts.\n", "expected_hash": "missing"})
        for state in ("review", "completed"):
            if state == "completed":
                view = ExecutionView("Approved execution", clean)
                engine.event = view.event
                task = await engine.advance(task["id"], task["calls"][0]["hash"])
            view.finish(task)
            for width in (40, 100):
                console = Console(file=io.StringIO(), width=width, height=60, record=True, force_terminal=True, color_system="truecolor", no_color=False)
                terminal = Terminal(console=console)
                terminal.header(workspace, config)
                console.print(view)
                terminal.task(task)
                console.save_svg(str(destination / f"{state}-{width}.svg"), title="Pi Engineering",
                    theme=TerminalTheme((10, 14, 17), (229, 235, 238),
                        [(10,14,17), (255,98,108), (0,237,116), (255,228,92), (73,104,245), (207,131,246), (67,232,241), (229,235,238)],
                        [(139,146,156), (255,98,108), (0,237,116), (255,228,92), (73,104,245), (207,131,246), (67,232,241), (255,255,255)]))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
