"""Encrypted backups, integrity checks and operational metrics."""
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from pi_workspace import UserError, WorkspaceSettings


MAGIC = b"PIBACKUP1"
MAX_BACKUP = 128 * 1024 * 1024


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def key_from_env(name, salt):
    secret = os.environ.get(name, "")
    if len(secret) < 16:
        raise UserError(f"Set {name} to a passphrase of at least 16 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(secret.encode())


def backup(workspace, destination, key_env):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise UserError("Backup destination already exists; choose a new filename")
    salt, nonce = os.urandom(16), os.urandom(12)
    key = key_from_env(key_env, salt)
    with tempfile.TemporaryDirectory(prefix="pi-backup-") as temporary:
        snapshot = Path(temporary) / "tasks.sqlite3"
        with workspace.database() as db:
            target = sqlite3.connect(snapshot)
            try:
                db.backup(target)
            finally:
                target.close()
        if snapshot.stat().st_size > MAX_BACKUP:
            raise UserError("Database exceeds the supported backup size")
        data = io.BytesIO()
        with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("config.json", workspace.config().model_dump_json())
            archive.write(snapshot, "tasks.sqlite3")
        encrypted = MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, data.getvalue(), MAGIC)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
    return {"backup": str(destination), "bytes": len(encrypted), "encryption": "AES-256-GCM / scrypt"}


def restore(workspace, source, key_env):
    workspace.check_recovery()
    if workspace.directory.exists() or workspace.directory.is_symlink():
        raise UserError("Restore requires a workspace without existing .pi-engineering state")
    path = Path(source)
    if path.stat().st_size > MAX_BACKUP:
        raise UserError("Backup exceeds the size limit")
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise UserError("Unsupported backup format")
    salt, nonce, encrypted = data[9:25], data[25:37], data[37:]
    try:
        payload = AESGCM(key_from_env(key_env, salt)).decrypt(nonce, encrypted, MAGIC)
    except UserError:
        raise
    except Exception as exc:
        raise UserError("Backup authentication failed: wrong passphrase or damaged backup") from exc
    with ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.namelist()) != 2 or set(archive.namelist()) != {"config.json", "tasks.sqlite3"}:
            raise UserError("Invalid backup contents")
        if sum(item.file_size for item in archive.infolist()) > MAX_BACKUP:
            raise UserError("Expanded backup exceeds the size limit")
        config = WorkspaceSettings.model_validate_json(archive.read("config.json"))
        database = archive.read("tasks.sqlite3")
    with tempfile.TemporaryDirectory(prefix="pi-restore-") as directory:
        temporary = Path(directory) / "tasks.sqlite3"
        temporary.write_bytes(database)
        db = sqlite3.connect(temporary)
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise UserError("Backup database integrity check failed")
            db.execute("SELECT id,body,updated FROM tasks LIMIT 0")
            db.execute("SELECT sequence,task_id,kind,body,created FROM events LIMIT 0")
        except sqlite3.DatabaseError as exc:
            raise UserError("Backup does not contain a valid Pi task database") from exc
        finally:
            db.close()
    marker = workspace.root / ".pi-restore-in-progress"
    descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("Restore pending; do not use this workspace until publication completes.\n")
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(workspace.root)
    # Persist both files before publication. The durable marker fails closed on
    # interruption, including between directory publication and marker removal.
    with tempfile.TemporaryDirectory(prefix=".pi-restore-", dir=workspace.root) as staging:
        stage = Path(staging) / "state"
        stage.mkdir(mode=0o700)
        for name, content in (("tasks.sqlite3", database),
                              ("config.json", config.model_dump_json(indent=2).encode())):
            descriptor = os.open(stage / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        sync_directory(stage)
        if workspace.directory.exists() or workspace.directory.is_symlink():
            raise UserError("Workspace state appeared during restore; publication refused")
        os.rename(stage, workspace.directory)
        sync_directory(workspace.root)
    marker.unlink()
    sync_directory(workspace.root)
    return {"restored": str(workspace.root), "integrity": "ok"}


def metrics(workspace):
    with workspace.database() as db:
        rows = [json.loads(row[0]) for row in db.execute("SELECT body FROM tasks")]
    states = {}
    for row in rows:
        states[row["status"]] = states.get(row["status"], 0) + 1
    elapsed = sorted(row["elapsed"] for row in rows)
    p95_index = (95 * len(elapsed) + 99) // 100 - 1
    return {"tasks": len(rows), "states": states, "model_steps": sum(row["steps"] for row in rows),
            "tool_calls": sum(len(row["calls"]) for row in rows),
            "p95_elapsed_seconds": elapsed[p95_index] if elapsed else 0}
