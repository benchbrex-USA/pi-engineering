"""Workspace-scoped, versioned knowledge and explicit durable memory."""
import re
import hashlib
import time
import uuid

from pi_workspace import UserError, fingerprint, canonical


def audit(db, identifier, operation, details=None):
    db.execute("INSERT INTO events(task_id,kind,body,created) VALUES(?,?,?,?)",
               (identifier, operation, canonical(details or {}), time.time()))


def source_content(workspace, name):
    from pi_tools import file_path, read_file
    path = file_path(workspace, name)
    if path.suffix.lower() != ".pdf":
        body = read_file(path)
        return fingerprint(body), [("text", body)]
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise UserError("PDF must be a regular file of at most 20 MB")
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or len(reader.pages) > 250:
            raise UserError("PDF must be unencrypted and contain at most 250 pages")
        sections = [(f"page {index + 1}", page.extract_text() or "") for index, page in enumerate(reader.pages)]
        if sum(len(text) for _, text in sections) > 1000000:
            raise UserError("Extracted PDF text exceeds the 1 MB limit")
        if not any(text.strip() for _, text in sections):
            raise UserError("PDF has no extractable text; provide an OCR text version")
    except UserError:
        raise
    except Exception as exc:
        raise UserError("Cannot extract this PDF") from exc
    return hashlib.sha256(path.read_bytes()).hexdigest(), sections


class Knowledge:
    def __init__(self, workspace):
        self.workspace = workspace
        with workspace.database() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id TEXT PRIMARY KEY, uri TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                    digest TEXT NOT NULL, version INTEGER NOT NULL, updated REAL NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks USING fts5(
                    source_id UNINDEXED, locator UNINDEXED, body, tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                    source TEXT NOT NULL, version INTEGER NOT NULL, created REAL NOT NULL,
                    expires REAL, digest TEXT NOT NULL
                );
            """)

    def ingest(self, path):
        digest, sections = source_content(self.workspace, path)
        uri = "workspace:" + path
        identifier = "source_" + fingerprint(uri)[:20]
        with self.workspace.database() as db:
            existing = db.execute("SELECT * FROM knowledge_sources WHERE uri=?", (uri,)).fetchone()
            if existing and existing["digest"] == digest:
                return dict(existing) | {"unchanged": True}
            version = existing["version"] + 1 if existing else 1
            db.execute("DELETE FROM knowledge_chunks WHERE source_id=?", (identifier,))
            for section, body in sections:
                lines = body.splitlines(keepends=True)
                for start in range(0, len(lines), 40):
                    chunk = "".join(lines[start:start + 48])
                    for offset in range(0, len(chunk), 4000):
                        db.execute("INSERT INTO knowledge_chunks VALUES(?,?,?)",
                                   (identifier, f"{section}; lines {start + 1}-{min(start + 48, len(lines))}; offset {offset}", chunk[offset:offset + 4000]))
            db.execute("INSERT INTO knowledge_sources VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "digest=excluded.digest, version=excluded.version, updated=excluded.updated",
                       (identifier, uri, path, digest, version, time.time()))
            audit(db, identifier, "source_indexed", {"version": version, "digest": digest})
        return {"id": identifier, "uri": uri, "version": version, "digest": digest}

    def sources(self):
        with self.workspace.database() as db:
            return [dict(row) for row in db.execute("SELECT * FROM knowledge_sources ORDER BY title")]

    def forget_source(self, identifier):
        with self.workspace.database() as db:
            db.execute("DELETE FROM knowledge_chunks WHERE source_id=?", (identifier,))
            count = db.execute("DELETE FROM knowledge_sources WHERE id=?", (identifier,)).rowcount
            if count:
                audit(db, identifier, "source_removed")
        if not count:
            raise UserError("Knowledge source not found")
        return {"deleted": identifier}

    def search(self, query, limit=8):
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)[:24]
        if not tokens:
            return []
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with self.workspace.database() as db:
            rows = db.execute("SELECT k.source_id, k.locator, k.body, s.uri, s.version, s.digest, "
                              "bm25(knowledge_chunks) AS rank FROM knowledge_chunks k JOIN knowledge_sources s "
                              "ON s.id=k.source_id WHERE knowledge_chunks MATCH ? ORDER BY rank LIMIT ?",
                              (expression, min(max(limit, 1), 20))).fetchall()
        results = []
        from pi_tools import file_path, read_file
        for row in rows:
            result = dict(row)
            try:
                path = file_path(self.workspace, result["uri"].removeprefix("workspace:"))
                if path.suffix.lower() == ".pdf":
                    if path.stat().st_size > 20 * 1024 * 1024:
                        continue
                    current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
                else:
                    current_digest = fingerprint(read_file(path))
                if current_digest != result["digest"]:
                    continue
            except (UserError, OSError):
                continue
            result["trust"] = "untrusted_source_evidence"
            results.append(result)
        return results

    def remember(self, title, body, source, ttl_days=None, identifier=None):
        if not title.strip() or not body.strip() or not source.strip() or len(body) > 16000:
            raise UserError("Memory needs title, body (up to 16000 characters) and source")
        if ttl_days is not None and not 0 < ttl_days <= 3650:
            raise UserError("Memory expiry must be 1 to 3650 days")
        identifier = identifier or "memory_" + uuid.uuid4().hex[:16]
        with self.workspace.database() as db:
            existing = db.execute("SELECT version FROM memories WHERE id=?", (identifier,)).fetchone()
            version = existing[0] + 1 if existing else 1
            db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "title=excluded.title, body=excluded.body, source=excluded.source, version=excluded.version, "
                       "expires=excluded.expires, digest=excluded.digest",
                       (identifier, title, body, source, version, time.time(),
                        time.time() + ttl_days * 86400 if ttl_days else None, fingerprint(body)))
            audit(db, identifier, "memory_saved", {"version": version, "digest": fingerprint(body), "source": source})
        return {"id": identifier, "version": version}

    def memories(self, query=""):
        with self.workspace.database() as db:
            rows = db.execute("SELECT * FROM memories WHERE expires IS NULL OR expires>? ORDER BY created DESC",
                              (time.time(),)).fetchall()
        terms = set(re.findall(r"\w+", query.lower()))
        matches = [dict(row) | {"trust": "operator_saved_evidence"} for row in rows
                   if not terms or terms.intersection(re.findall(r"\w+", (row["title"] + " " + row["body"]).lower()))]
        return matches[:20]

    def forget(self, identifier):
        with self.workspace.database() as db:
            count = db.execute("DELETE FROM memories WHERE id=?", (identifier,)).rowcount
            if count:
                audit(db, identifier, "memory_removed")
        if not count:
            raise UserError("Memory not found")
        return {"deleted": identifier}
