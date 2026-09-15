"""Keyboard-first input, searchable commands and in-memory session history."""
import shlex

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import Validator, ValidationError

from pi_terminal import clean


COMMANDS = {
    "/help": "Commands", "/setup": "Initialize workspace", "/model show": "Active model",
    "/model set": "Configure model",
    "/brain show": "Brain capacity", "/brain set": "Attach any open model", "/brain open": "Open-brain philosophy", "/mcp list": "MCP connections", "/mcp add": "Connect MCP server",
    "/mcp schema": "Inspect tool contract", "/mcp qualify": "Run integration contract",
    "/agents": "Agent permissions", "/agent": "Switch agent", "/agent set": "Configure agent",
    "/tools": "Available tools", "/runs": "Task history", "/show": "Task and action details",
    "/review": "Latest pending approval", "/approve": "Approve exact action hash",
    "/reject": "Reject pending action", "/resume": "Resume task", "/trace": "Task checkpoints",
    "/receipt": "Execution receipts", "/graph": "Execution graph", "/doctor": "Connection health",
    "/knowledge add": "Index document", "/knowledge search": "Search indexed sources",
    "/knowledge list": "Indexed documents", "/memory list": "Saved memory",
    "/memory add": "Save operator memory", "/memory search": "Search memory",
    "/metrics": "Execution metrics", "/check list": "Registered checks",
    "/check add": "Register check", "/workspace show": "Active project",
    "/workspace use": "Switch project", "/workflow": "Agent graph: FILE, --validate or --explain blockers",
    "/profile list": "Persona presets", "/profile show": "Show a persona preset",
    "/profile apply": "Apply a persona preset", "/recipe export": "Export shareable recipe",
    "/backup": "Encrypted backup", "/restore": "Restore backup", "/quit": "Exit Pi",
}


class CommandCompleter(Completer):
    def __init__(self):
        self.agents = []
        self.tasks = []

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        if text.startswith("/agent ") and not text.startswith("/agent set"):
            prefix = text[len("/agent "):]
            if "set".startswith(prefix):
                yield Completion("set", start_position=-len(prefix), display_meta="configure agent")
            for name in self.agents:
                if name.startswith(prefix):
                    yield Completion(name, start_position=-len(prefix), display_meta="agent")
            return
        if any(text.startswith(command + " ") for command in ("/show", "/trace", "/receipt", "/resume", "/reject", "/approve")):
            prefix = text.split(" ", 1)[1]
            for task in self.tasks:
                if task["id"].startswith(prefix):
                    yield Completion(task["id"], start_position=-len(prefix), display_meta=clean(task["status"]))
            return
        query = text[1:].lower()
        for command, description in COMMANDS.items():
            if command.startswith(text) or (query and query in description.lower()):
                yield Completion(command, start_position=-len(text), display_meta=description)


class CommandValidator(Validator):
    def validate(self, document):
        text = document.text.strip()
        if not text.startswith("/"):
            return
        try:
            parts = shlex.split(text)
        except ValueError:
            raise ValidationError(message="Close the quoted argument before continuing", cursor_position=len(text))
        known = {command.split()[0] for command in COMMANDS} | {"/exit", "/init", "/home", "/launch", "/call", "/reconcile"}
        if parts and parts[0] not in known:
            raise ValidationError(message="Unknown command. Press Ctrl-P to choose a command.", cursor_position=len(text))


class Composer:
    def __init__(self, plain=False):
        self.plain = plain
        self.completer = CommandCompleter()
        bindings = KeyBindings()

        @bindings.add("c-p")
        def palette(event):
            event.current_buffer.text = "/"
            event.current_buffer.cursor_position = 1
            event.current_buffer.start_completion(select_first=False)

        self.session = None if plain else PromptSession(
            completer=self.completer, complete_while_typing=True,
            reserve_space_for_menu=7, auto_suggest=AutoSuggestFromHistory(),
            validator=CommandValidator(), validate_while_typing=False,
            key_bindings=bindings, color_depth=ColorDepth.TRUE_COLOR,
            style=Style.from_dict({
                "": "#e6edf0", "completion-menu.completion": "bg:#151b20 #b6c2ca",
                "completion-menu.completion.current": "bg:#43e8f1 #071114 bold",
                "completion-menu.meta.completion": "bg:#151b20 #8b929c",
                "completion-menu.meta.completion.current": "bg:#43e8f1 #071114",
                "auto-suggestion": "#727d86", "validation-toolbar": "bg:#ff626c #180606",
            }))

    def read(self, workspace, agent):
        if self.plain:
            return input(f"\n{agent} > ").strip()
        self.completer.agents = [name for name, entry in workspace.config().agents.items() if entry.enabled]
        self.completer.tasks = workspace.runs()
        pending = sum(task["status"] == "awaiting_approval" for task in self.completer.tasks)
        message = [("", "\n"), ("bg:#43e8f1 #071114 bold", " PI "),
                   ("#43e8f1 bold", " " + clean(agent)), ("#8b929c", " · " + clean(workspace.root.name))]
        if pending:
            message.append(("#ffe45c", f" · {pending} awaiting review"))
        message.extend([("", "\n"), ("#43e8f1 bold", "❯ ")])
        return self.session.prompt(message).strip()
