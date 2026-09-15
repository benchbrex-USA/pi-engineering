"""Validated workspace configuration and durable task records."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from typing import Literal
from urllib.parse import urlparse
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


VERSION = "0.6.0"


def active_workspace():
    if os.environ.get("PI_WORKSPACE"):
        return os.environ["PI_WORKSPACE"]
    current = Path.cwd()
    for candidate in (current, *current.parents):
        if (candidate / ".pi-engineering" / "config.json").is_file():
            return str(candidate)
    preference = Path.home() / ".config" / "pi-engineering" / "workspace.json"
    try:
        selected = json.loads(preference.read_text())["workspace"]
        if Path(selected).is_dir():
            return selected
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return str(current)


def select_workspace(path):
    workspace = Workspace(path)
    destination = Path.home() / ".config" / "pi-engineering"
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=destination, prefix="workspace-")
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"workspace": str(workspace.root)}, stream)
        os.replace(temporary, destination / "workspace.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"workspace": str(workspace.root)}


class UserError(Exception):
    """An actionable error safe for the operator interface."""


class LockBusy(UserError):
    """A participating local process currently owns a requested lock."""


class ResourceBusy(UserError):
    """A declared workflow resource is currently owned by another task."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def valid_url(value: str) -> str:
    url = urlparse(value)
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("URLs must not contain credentials, queries or fragments")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Use HTTPS, or HTTP on localhost")
    if not url.hostname:
        raise ValueError("URL needs a hostname")
    return value.rstrip("/")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSettings(StrictModel):
    provider: Literal["ollama", "codex", "openai", "grok", "compat"] = "ollama"
    endpoint: str = "http://127.0.0.1:11434"
    model: str = ""
    token_env: str = ""
    timeout: int = Field(default=180, ge=1, le=3600)
    context_chars: int = Field(default=200000, ge=4000, le=8000000)
    output_tokens: int = Field(default=8192, ge=128, le=200000)

    _url = field_validator("endpoint")(valid_url)


class ServerSettings(StrictModel):
    transport: Literal["stdio", "http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    token_env: str = ""
    env: list[str] = Field(default_factory=list)
    enabled: bool = True
    read_tools: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def url_valid(cls, value):
        return valid_url(value) if value else value


class AgentSettings(StrictModel):
    role: str = "Complete the user's task using evidence and permitted tools."
    tools: list[str] = Field(default_factory=lambda: ["workspace_files", "workspace_read", "knowledge_search", "memory_search"])
    enabled: bool = True
    max_steps: int = Field(default=32, ge=1, le=10000)
    deadline_seconds: int = Field(default=1800, ge=10, le=86400)
    model: ModelSettings | None = None


class WorkspaceSettings(StrictModel):
    version: Literal[1] = 1
    model: ModelSettings = Field(default_factory=ModelSettings)
    servers: dict[str, ServerSettings] = Field(default_factory=dict)
    checks: dict[str, list[str]] = Field(default_factory=dict)
    agents: dict[str, AgentSettings] = Field(default_factory=lambda: {
        "engineer": AgentSettings(tools=["workspace_files", "workspace_read", "workspace_write", "workspace_check", "knowledge_search", "memory_search"], max_steps=64, deadline_seconds=3600),
        "researcher": AgentSettings(role="Research the task; cite tool observations and distinguish inference from evidence."),
        "reviewer": AgentSettings(role="Review evidence for defects and unmet criteria. Cite concrete findings; do not modify files."),
    })

    @field_validator("servers", "agents", "checks")
    @classmethod
    def names_valid(cls, value):
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name) for name in value):
            raise ValueError("Names must start with a lowercase letter; use letters, numbers, - or _")
        return value

    @field_validator("checks")
    @classmethod
    def checks_valid(cls, value):
        if any(not argv or not argv[0].strip() or any("\x00" in part for part in argv)
               for argv in value.values()):
            raise ValueError("Checks require a nonempty executable and NUL-free argv")
        return value


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise UserError(f"Workspace directory does not exist: {self.root}")
        self.directory = self.root / ".pi-engineering"
        self.config_path = self.directory / "config.json"

    def check_recovery(self):
        marker = self.root / ".pi-restore-in-progress"
        if marker.exists() or marker.is_symlink():
            raise UserError("Restore is unfinished. Preserve this workspace and restore the backup into a new empty directory.")

    def prepare(self):
        self.check_recovery()
        if self.directory.is_symlink():
            raise UserError("Workspace state directory must not be a symlink")
        self.directory.mkdir(mode=0o700, exist_ok=True)

    def config(self) -> WorkspaceSettings:
        self.check_recovery()
        if self.directory.is_symlink() or self.config_path.is_symlink():
            raise UserError("Workspace configuration must not use symlinks")
        if not self.config_path.exists():
            return WorkspaceSettings()
        try:
            return WorkspaceSettings.model_validate_json(self.config_path.read_text())
        except (ValueError, OSError) as exc:
            raise UserError(f"Invalid workspace configuration: {self.config_path}") from exc

    def save(self, config: WorkspaceSettings):
        self.prepare()
        config = WorkspaceSettings.model_validate(config.model_dump())
        descriptor, path = tempfile.mkstemp(prefix="config-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(config.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.config_path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @contextlib.contextmanager
    def lock(self, name: str):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
            raise UserError("Invalid record identifier")
        self.prepare()
        path = self.directory / (name + ".lock")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise UserError("Cannot open a regular workspace lock file") from exc
        with os.fdopen(descriptor, "a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LockBusy("This task is already running in another process") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    @contextlib.contextmanager
    def database(self):
        self.prepare()
        path = self.directory / "tasks.sqlite3"
        if any((self.directory / name).is_symlink() for name in
               ("tasks.sqlite3", "tasks.sqlite3-wal", "tasks.sqlite3-shm", "tasks.sqlite3-journal")):
            raise UserError("Task database and journals must not be symlinks")
        db = sqlite3.connect(path, timeout=10)
        os.chmod(path, 0o600)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
                created REAL NOT NULL
            );
        """)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, request: str, agent: str, config_hash: str):
        if not request.strip() or len(request) > 32000:
            raise UserError("Task must contain 1 to 32000 characters")
        task = dict(id="task_" + uuid.uuid4().hex[:16], request=request, agent=agent,
                    config_hash=config_hash, status="ready", messages=[], calls=[],
                    steps=0, elapsed=0.0, created=time.time(), answer="", error="")
        self.record(task, "created")
        return task

    def record(self, task, kind, details=None):
        with self.database() as db:
            db.execute("INSERT INTO tasks VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE "
                       "SET body=excluded.body, updated=excluded.updated",
                       (task["id"], canonical(task), time.time()))
            db.execute("INSERT INTO events(task_id,kind,body,created) VALUES(?,?,?,?)",
                       (task["id"], kind, canonical(details or {"status": task["status"]}), time.time()))

    def task(self, task_id):
        with self.database() as db:
            row = db.execute("SELECT body FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise UserError(f"Task not found: {task_id}. Use runs to list tasks.")
        return json.loads(row[0])

    def runs(self):
        self.check_recovery()
        if not (self.directory / "tasks.sqlite3").exists():
            return []
        with self.database() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT body FROM tasks ORDER BY updated DESC LIMIT 100")]

    def events(self, task_id):
        with self.database() as db:
            return [dict(row) | {"body": json.loads(row["body"])} for row in db.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY sequence", (task_id,))]
