"""Pi Engineering CLI core.

This module implements a local-first, MCP-ready Pi Engineering runtime.
It deliberately keeps model output separate from authority:

    agents propose, graph validates, approval binds, broker commits,
    verifier checks, evals measure.

The code is stdlib-only so the CLI and MCP server can run in constrained
environments. It is a reference implementation, not production security.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / ".pi"
DEFAULT_DB = DATA_DIR / "pi_engineering_cli.db"
POLICY_VERSION = "pi-cli-policy-v1"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")
TICKET_RE = re.compile(r"\b[A-Z]+-\d+\b", re.IGNORECASE)
RetrievalMethod = Literal["bm25", "overlap"]


class PiError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


def utc_now() -> float:
    return time.time()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]
    return f"{prefix}_{token}"


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def require_slug(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,40}", value):
        raise PiError(f"invalid_{field}")
    return value


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def json_or_empty(value: str | None) -> Any:
    return json.loads(value) if value else {}


@dataclass(frozen=True)
class Evidence:
    id: str
    tenant: str
    title: str
    body: str
    version: int
    source_uri: str
    trust_class: str


@dataclass(frozen=True)
class ManifestItem:
    source_id: str
    version: int
    title: str
    content_hash: str
    token_cost: int
    trust_class: str


@dataclass(frozen=True)
class ContextBundle:
    bundle_id: str
    tenant: str
    actor: str
    request_hash: str
    source_snapshot: str
    evidence: tuple[Evidence, ...]
    items: tuple[ManifestItem, ...]
    token_budget: int
    token_cost: int
    truncated: bool
    excluded: tuple[dict[str, Any], ...]

    def manifest(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "tenant": self.tenant,
            "actor": self.actor,
            "request_hash": self.request_hash,
            "source_snapshot": self.source_snapshot,
            "token_budget": self.token_budget,
            "token_cost": self.token_cost,
            "truncated": self.truncated,
            "items": [asdict(item) for item in self.items],
            "excluded": list(self.excluded),
        }

    def with_excerpts(self) -> dict[str, Any]:
        payload = self.manifest()
        payload["evidence"] = [
            {
                "id": item.id,
                "title": item.title,
                "version": item.version,
                "source_uri": item.source_uri,
                "excerpt": item.body[:600],
            }
            for item in self.evidence
        ]
        return payload


@dataclass(frozen=True)
class Intent:
    ticket: str | None
    desired_status: str | None
    effectful: bool
    risk: str
    reason: str


@dataclass(frozen=True)
class ProposedAction:
    type: str
    tenant: str
    ticket: str
    expected_version: int
    status: str
    reason: str
    evidence_ids: tuple[str, ...]

    def action_hash(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Proposal:
    answer: str
    citations: tuple[str, ...]
    action: ProposedAction | None


@dataclass
class RunState:
    run_id: str
    tenant: str
    actor: str
    request: str
    status: str = "running"
    intent: Intent | None = None
    context: ContextBundle | None = None
    proposal: Proposal | None = None
    route: str = "continue"
    failure_reason: str = ""
    receipt: dict[str, Any] | None = None


class PiStore:
    def __init__(self, path: str | Path = DEFAULT_DB, clock: Callable[[], float] = utc_now):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self._schema()

    def close(self) -> None:
        self.db.close()

    def _schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                tenant TEXT NOT NULL,
                ticket TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                priority TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (tenant, ticket)
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                tenant TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                version INTEGER NOT NULL,
                source_uri TEXT NOT NULL,
                trust_class TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                tenant TEXT NOT NULL,
                actor TEXT NOT NULL,
                request TEXT NOT NULL,
                status TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                context_json TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                failure_reason TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                node TEXT NOT NULL,
                route TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                tenant TEXT NOT NULL,
                actor TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                decided_at REAL
            );
            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                tenant TEXT NOT NULL,
                operation_key TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE (tenant, operation_key)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eval_results (
                id TEXT PRIMARY KEY,
                suite TEXT NOT NULL,
                total INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                severe_failures INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_definitions (
                name TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                tools_json TEXT NOT NULL,
                permissions_json TEXT NOT NULL,
                risk TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                source TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                risk TEXT NOT NULL,
                effect TEXT NOT NULL,
                requires_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )

    def seed(self) -> None:
        stamp = self.clock()
        if self.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
            self.db.executemany(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("aster", "T-100", "Customer cannot access workspace", "open", 0, "high", stamp),
                    ("aster", "T-101", "Billing export is slow", "pending", 2, "medium", stamp),
                    ("beacon", "B-200", "Beacon private incident", "open", 0, "high", stamp),
                ],
            )
        if self.db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0:
            self.db.executemany(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "policy-aster-pending",
                        "aster",
                        "Aster ticket triage policy",
                        "Tickets may be marked pending when support is waiting on customer confirmation.",
                        1,
                        "local://policy/aster/triage",
                        "authorized source evidence",
                        stamp,
                    ),
                    (
                        "policy-aster-resolved",
                        "aster",
                        "Aster resolution policy",
                        "Tickets may be marked resolved only after the customer confirms the fix.",
                        1,
                        "local://policy/aster/resolution",
                        "authorized source evidence",
                        stamp,
                    ),
                    (
                        "policy-beacon-private",
                        "beacon",
                        "Beacon private policy",
                        "Beacon tickets are confidential and may be marked pending only by Beacon operators.",
                        1,
                        "local://policy/beacon/private",
                        "authorized source evidence",
                        stamp,
                    ),
                ],
            )
        self.seed_agents()
        self.seed_policy_rules()

    def seed_agents(self) -> None:
        if self.db.execute("SELECT COUNT(*) FROM agent_definitions").fetchone()[0] > 0:
            return
        stamp = self.clock()
        self.db.executemany(
            "INSERT INTO agent_definitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item["name"],
                    item["role"],
                    canonical(item.get("tools", [])),
                    canonical(item.get("permissions", [])),
                    item.get("risk", "medium"),
                    1,
                    "built-in",
                    stamp,
                    stamp,
                )
                for item in default_agent_definitions()
            ],
        )

    def seed_policy_rules(self) -> None:
        if self.db.execute("SELECT COUNT(*) FROM policy_rules").fetchone()[0] > 0:
            return
        stamp = self.clock()
        self.db.executemany(
            "INSERT INTO policy_rules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item["id"],
                    item["name"],
                    item["action_type"],
                    item["risk"],
                    item["effect"],
                    canonical(item["requires"]),
                    1,
                    stamp,
                    stamp,
                )
                for item in default_policy_rules()
            ],
        )

    def add_ticket(self, tenant: str, ticket: str, title: str,
                   status: str = "open", priority: str = "medium") -> dict[str, Any]:
        require_slug(tenant, "tenant")
        ticket = ticket.upper()
        if not TICKET_RE.fullmatch(ticket):
            raise PiError("invalid_ticket")
        if status not in {"open", "pending", "resolved"}:
            raise PiError("invalid_status")
        self.db.execute(
            "INSERT INTO tickets VALUES (?, ?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(tenant, ticket) DO UPDATE SET title=excluded.title, "
            "status=excluded.status, priority=excluded.priority, updated_at=excluded.updated_at",
            (tenant, ticket, title.strip()[:240], status, priority, self.clock()),
        )
        return self.ticket(tenant, ticket)

    def add_evidence(self, tenant: str, title: str, body: str,
                     source_uri: str = "local://cli/evidence",
                     trust_class: str = "authorized source evidence") -> dict[str, Any]:
        require_slug(tenant, "tenant")
        if not title.strip() or not body.strip():
            raise PiError("invalid_evidence")
        ev_id = "ev_" + digest({"tenant": tenant, "title": title, "body": body})[:16]
        existing = self.db.execute("SELECT version FROM evidence WHERE id=?", (ev_id,)).fetchone()
        version = int(existing["version"]) + 1 if existing else 1
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, body=excluded.body, "
            "version=excluded.version, source_uri=excluded.source_uri, "
            "trust_class=excluded.trust_class, created_at=excluded.created_at",
            (ev_id, tenant, title.strip()[:240], body.strip(), version,
             source_uri.strip()[:500], trust_class, self.clock()),
        )
        return self.evidence_item(ev_id)

    def ticket(self, tenant: str, ticket: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM tickets WHERE tenant=? AND ticket=?", (tenant, ticket.upper())
        ).fetchone()
        if row is None:
            raise PiError("ticket_not_found", 404)
        return row_dict(row)

    def tickets(self, tenant: str | None = None) -> list[dict[str, Any]]:
        if tenant:
            rows = self.db.execute(
                "SELECT * FROM tickets WHERE tenant=? ORDER BY ticket", (tenant,)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM tickets ORDER BY tenant, ticket").fetchall()
        return [row_dict(row) for row in rows]

    def evidence(self, tenant: str | None = None) -> list[dict[str, Any]]:
        if tenant:
            rows = self.db.execute(
                "SELECT * FROM evidence WHERE tenant=? ORDER BY id", (tenant,)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM evidence ORDER BY tenant, id").fetchall()
        return [row_dict(row) for row in rows]

    def evidence_item(self, ev_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM evidence WHERE id=?", (ev_id,)).fetchone()
        if row is None:
            raise PiError("evidence_not_found", 404)
        return row_dict(row)

    def evidence_objects(self, tenant: str) -> list[Evidence]:
        return [
            Evidence(row["id"], row["tenant"], row["title"], row["body"],
                     row["version"], row["source_uri"], row["trust_class"])
            for row in self.db.execute("SELECT * FROM evidence WHERE tenant=? ORDER BY id", (tenant,))
        ]

    def save_run(self, state: RunState) -> None:
        proposal = proposal_dict(state.proposal) if state.proposal else {}
        context = state.context.manifest() if state.context else {}
        intent = asdict(state.intent) if state.intent else {}
        action_hash = ""
        if state.proposal and state.proposal.action:
            action_hash = state.proposal.action.action_hash()
        existing = self.db.execute("SELECT id FROM runs WHERE id=?", (state.run_id,)).fetchone()
        stamp = self.clock()
        if existing:
            self.db.execute(
                "UPDATE runs SET status=?, intent_json=?, context_json=?, proposal_json=?, "
                "action_hash=?, failure_reason=?, updated_at=? WHERE id=?",
                (state.status, canonical(intent), canonical(context), canonical(proposal),
                 action_hash, state.failure_reason, stamp, state.run_id),
            )
        else:
            self.db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (state.run_id, state.tenant, state.actor, state.request, state.status,
                 canonical(intent), canonical(context), canonical(proposal), action_hash,
                 state.failure_reason, stamp, stamp),
            )

    def checkpoint(self, state: RunState, node: str, body: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO checkpoints (run_id, node, route, body_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (state.run_id, node, state.route, canonical(body), self.clock()),
        )

    def audit(self, tenant: str, run_id: str, event_type: str, body: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO audit_events (tenant, run_id, event_type, body_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tenant, run_id, event_type, canonical(body), self.clock()),
        )

    def run(self, run_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise PiError("run_not_found", 404)
        return inflate_run(row_dict(row))

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [inflate_run(row_dict(row)) for row in rows]

    def checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM checkpoints WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
        output = []
        for row in rows:
            item = row_dict(row)
            item["body"] = json_or_empty(item.pop("body_json"))
            output.append(item)
        return output

    def latest_eval(self) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM eval_results ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        item = row_dict(row)
        item["body"] = json_or_empty(item.pop("body_json"))
        return item

    def agents(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        if enabled is None:
            rows = self.db.execute("SELECT * FROM agent_definitions ORDER BY name").fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM agent_definitions WHERE enabled=? ORDER BY name",
                (1 if enabled else 0,),
            ).fetchall()
        return [inflate_agent(row_dict(row)) for row in rows]

    def add_agent(self, name: str, role: str, tools: list[str] | None = None,
                  permissions: list[str] | None = None, risk: str = "medium",
                  enabled: bool = True, source: str = "cli") -> dict[str, Any]:
        name = require_slug(name, "agent")
        if not role.strip():
            raise PiError("invalid_agent_role")
        if risk not in {"low", "medium", "high"}:
            raise PiError("invalid_agent_risk")
        clean_tools = [str(item).strip() for item in (tools or []) if str(item).strip()]
        clean_permissions = [
            str(item).strip() for item in (permissions or []) if str(item).strip()
        ]
        stamp = self.clock()
        self.db.execute(
            "INSERT INTO agent_definitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET role=excluded.role, "
            "tools_json=excluded.tools_json, permissions_json=excluded.permissions_json, "
            "risk=excluded.risk, enabled=excluded.enabled, source=excluded.source, "
            "updated_at=excluded.updated_at",
            (
                name,
                role.strip()[:500],
                canonical(clean_tools),
                canonical(clean_permissions),
                risk,
                1 if enabled else 0,
                source.strip()[:80] or "cli",
                stamp,
                stamp,
            ),
        )
        return self.agent(name)

    def agent(self, name: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM agent_definitions WHERE name=?", (name,)).fetchone()
        if row is None:
            raise PiError("agent_not_found", 404)
        return inflate_agent(row_dict(row))

    def set_agent_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        self.agent(name)
        self.db.execute(
            "UPDATE agent_definitions SET enabled=?, updated_at=? WHERE name=?",
            (1 if enabled else 0, self.clock(), name),
        )
        return self.agent(name)

    def policy_rules(self, action_type: str | None = None,
                     enabled: bool | None = None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if action_type:
            clauses.append("action_type=?")
            params.append(action_type)
        if enabled is not None:
            clauses.append("enabled=?")
            params.append(1 if enabled else 0)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.db.execute(
            "SELECT * FROM policy_rules" + where + " ORDER BY action_type, id",
            params,
        ).fetchall()
        return [inflate_policy_rule(row_dict(row)) for row in rows]

    def add_policy_rule(self, name: str, action_type: str, requires: list[str],
                        risk: str = "medium", effect: str = "requires_approval",
                        enabled: bool = True) -> dict[str, Any]:
        if not name.strip() or not action_type.strip():
            raise PiError("invalid_policy_rule")
        if risk not in {"low", "medium", "high"}:
            raise PiError("invalid_policy_risk")
        if effect not in {"allow", "requires_approval", "deny"}:
            raise PiError("invalid_policy_effect")
        clean_requires = [str(item).strip() for item in requires if str(item).strip()]
        rule_id = "rule_" + digest({
            "name": name.strip(),
            "action_type": action_type.strip(),
            "requires": clean_requires,
        })[:16]
        stamp = self.clock()
        self.db.execute(
            "INSERT INTO policy_rules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, risk=excluded.risk, "
            "effect=excluded.effect, requires_json=excluded.requires_json, "
            "enabled=excluded.enabled, updated_at=excluded.updated_at",
            (
                rule_id,
                name.strip()[:240],
                action_type.strip()[:120],
                risk,
                effect,
                canonical(clean_requires),
                1 if enabled else 0,
                stamp,
                stamp,
            ),
        )
        return self.policy_rule(rule_id)

    def policy_rule(self, rule_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM policy_rules WHERE id=?", (rule_id,)).fetchone()
        if row is None:
            raise PiError("policy_rule_not_found", 404)
        return inflate_policy_rule(row_dict(row))

    def approval(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE run_id=?", (run_id,)).fetchone()
        return row_dict(row)

    def receipt(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT body_json FROM receipts WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return json_or_empty(row["body_json"])

    def audit_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM audit_events WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        output = []
        for row in rows:
            item = row_dict(row)
            item["body"] = json_or_empty(item.pop("body_json"))
            output.append(item)
        return output

    def explain_run(self, run_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        action = (run.get("proposal") or {}).get("action")
        rules = self.policy_rules(action.get("type"), enabled=True) if action else []
        approval = self.approval(run_id)
        receipt = self.receipt(run_id)
        checkpoints = self.checkpoints(run_id)
        context_items = (run.get("context") or {}).get("items", [])
        return {
            "run_id": run_id,
            "status": run["status"],
            "tenant": run["tenant"],
            "actor": run["actor"],
            "request_hash": digest(run["request"]),
            "intent": run.get("intent"),
            "action": action,
            "decision": explain_decision(run, approval, receipt, rules),
            "policy_rules": rules,
            "approval": approval,
            "receipt": receipt,
            "context_manifest": {
                "bundle_id": (run.get("context") or {}).get("bundle_id"),
                "source_snapshot": (run.get("context") or {}).get("source_snapshot"),
                "items": context_items,
            },
            "checkpoints": [
                {"node": item["node"], "route": item["route"], "status": item["body"].get("status")}
                for item in checkpoints
            ],
        }

    def trace_run(self, run_id: str) -> dict[str, Any]:
        return {
            "run": self.run(run_id),
            "approval": self.approval(run_id),
            "receipt": self.receipt(run_id),
            "checkpoints": self.checkpoints(run_id),
            "audit_events": self.audit_events(run_id),
        }

    def state(self, tenant: str | None = None) -> dict[str, Any]:
        return {
            "tickets": self.tickets(tenant),
            "evidence": self.evidence(tenant),
            "runs": self.runs(),
            "agents": self.agents(),
            "policy_rules": self.policy_rules(),
            "latest_eval": self.latest_eval(),
        }


def inflate_run(row: dict[str, Any]) -> dict[str, Any]:
    row["intent"] = json_or_empty(row.pop("intent_json"))
    row["context"] = json_or_empty(row.pop("context_json"))
    row["proposal"] = json_or_empty(row.pop("proposal_json"))
    return row


def proposal_dict(proposal: Proposal) -> dict[str, Any]:
    return {
        "answer": proposal.answer,
        "citations": list(proposal.citations),
        "action": None if proposal.action is None else asdict(proposal.action),
    }


def score_evidence(query: str, evidence: list[Evidence],
                   method: RetrievalMethod = "bm25") -> list[tuple[Evidence, float]]:
    q = tokens(query)
    if not q:
        return []
    if method == "overlap":
        terms = set(q)
        scored = [
            (item, float(len(terms & set(tokens(item.title + " " + item.body)))))
            for item in evidence
        ]
    elif method == "bm25":
        scored = bm25(q, evidence)
    else:
        raise PiError("unknown_retrieval_method")
    return [
        (item, score)
        for item, score in sorted(scored, key=lambda pair: (-pair[1], pair[0].id))
        if score > 0.0
    ]


def bm25(query_terms: list[str], evidence: list[Evidence],
         k1: float = 1.2, b: float = 0.75) -> list[tuple[Evidence, float]]:
    doc_terms = {item.id: tokens(item.title + " " + item.body) for item in evidence}
    if not doc_terms:
        return []
    avg_len = sum(len(value) for value in doc_terms.values()) / len(doc_terms) or 1.0
    scored = []
    for item in evidence:
        terms = doc_terms[item.id]
        score = 0.0
        for term in tuple(dict.fromkeys(query_terms)):
            frequency = terms.count(term)
            if frequency == 0:
                continue
            doc_frequency = sum(1 for values in doc_terms.values() if term in values)
            idf = math.log(1.0 + (len(evidence) - doc_frequency + 0.5) / (doc_frequency + 0.5))
            score += idf * (frequency * (k1 + 1.0)) / (
                frequency + k1 * (1.0 - b + b * len(terms) / avg_len)
            )
        scored.append((item, score))
    return scored


def build_context(store: PiStore, tenant: str, actor: str, request: str,
                  token_budget: int = 180, limit: int = 5) -> ContextBundle:
    require_slug(tenant, "tenant")
    ranked = score_evidence(request, store.evidence_objects(tenant))
    selected: list[Evidence] = []
    items: list[ManifestItem] = []
    excluded: list[dict[str, Any]] = []
    used = 0
    for item, score in ranked:
        cost = len(tokens(item.title + " " + item.body))
        if len(selected) >= limit:
            excluded.append({"source_id": item.id, "reason": "limit_exceeded", "score": round(score, 6)})
            continue
        if used + cost > token_budget:
            excluded.append({
                "source_id": item.id,
                "reason": "budget_exceeded",
                "token_cost": cost,
                "score": round(score, 6),
            })
            continue
        selected.append(item)
        items.append(
            ManifestItem(
                item.id,
                item.version,
                item.title,
                digest({"id": item.id, "version": item.version, "body": item.body}),
                cost,
                item.trust_class,
            )
        )
        used += cost
    snapshot = digest([(item.source_id, item.version, item.content_hash) for item in items])
    seed = {
        "tenant": tenant,
        "actor": actor,
        "request_hash": digest(request),
        "source_snapshot": snapshot,
        "token_budget": token_budget,
    }
    return ContextBundle(
        bundle_id="ctx_" + digest(seed)[:18],
        tenant=tenant,
        actor=actor,
        request_hash=digest(request),
        source_snapshot=snapshot,
        evidence=tuple(selected),
        items=tuple(items),
        token_budget=token_budget,
        token_cost=used,
        truncated=bool(excluded),
        excluded=tuple(excluded),
    )


class Agent:
    name = "agent"

    def run(self, store: PiStore, state: RunState) -> None:
        raise NotImplementedError


class IntentAgent(Agent):
    name = "intent"

    def run(self, store: PiStore, state: RunState) -> None:
        lower = state.request.lower()
        status = next((s for s in ("pending", "resolved", "open") if s in lower), None)
        ticket_match = TICKET_RE.search(state.request)
        ticket = ticket_match.group(0).upper() if ticket_match else None
        risk = "high" if status in {"resolved"} else "medium" if status else "low"
        state.intent = Intent(
            ticket=ticket,
            desired_status=status,
            effectful=status is not None,
            risk=risk,
            reason="ticket status request" if status else "read-only or unsupported request",
        )
        state.route = "effectful" if status else "answer_only"


class EvidenceAgent(Agent):
    name = "evidence"

    def run(self, store: PiStore, state: RunState) -> None:
        state.context = build_context(store, state.tenant, state.actor, state.request)
        state.route = "has_evidence" if state.context.evidence else "no_evidence"


class ProposalAgent(Agent):
    name = "proposal"

    def run(self, store: PiStore, state: RunState) -> None:
        if state.intent is None:
            raise PiError("missing_intent")
        if state.context is None:
            raise PiError("missing_context")
        if not state.intent.effectful:
            state.proposal = Proposal(
                "No supported ticket status change was requested. Use pending, resolved or open.",
                tuple(item.id for item in state.context.evidence[:1]),
                None,
            )
            state.route = "answer"
            return
        ticket_id = state.intent.ticket
        if not ticket_id:
            open_tickets = [t for t in store.tickets(state.tenant) if t["status"] != state.intent.desired_status]
            ticket_id = open_tickets[0]["ticket"] if open_tickets else None
        if not ticket_id:
            state.proposal = Proposal("No tenant-scoped ticket is available for this action.", tuple(), None)
            state.route = "answer"
            return
        try:
            ticket = store.ticket(state.tenant, ticket_id)
        except PiError:
            state.proposal = Proposal(
                f"Ticket {ticket_id} is not available in tenant {state.tenant}.",
                tuple(),
                None,
            )
            state.route = "answer"
            return
        support = support_for_status(state.intent.desired_status or "", state.context.evidence)
        if support is None:
            state.proposal = Proposal(
                f"No authorized evidence supports marking {ticket_id} {state.intent.desired_status}.",
                tuple(item.id for item in state.context.evidence[:1]),
                None,
            )
            state.route = "answer"
            return
        answer = sentence_with(support.body, state.intent.desired_status or "")
        action = ProposedAction(
            type="ticket.status.update",
            tenant=state.tenant,
            ticket=ticket_id,
            expected_version=int(ticket["version"]),
            status=state.intent.desired_status or "",
            reason=answer,
            evidence_ids=(support.id,),
        )
        state.proposal = Proposal(answer, (support.id,), action)
        state.route = "proposed"


class PolicyAgent(Agent):
    name = "policy"

    def run(self, store: PiStore, state: RunState) -> None:
        if state.proposal is None or state.proposal.action is None:
            state.route = "no_action"
            return
        action = state.proposal.action
        rules = store.policy_rules(action.type, enabled=True)
        if any(rule["effect"] == "deny" for rule in rules):
            raise PiError("policy_denied")
        if action.tenant != state.tenant:
            raise PiError("cross_tenant_action_denied")
        if action.status not in {"open", "pending", "resolved"}:
            raise PiError("unsupported_status")
        ticket = store.ticket(action.tenant, action.ticket)
        if int(ticket["version"]) != action.expected_version:
            raise PiError("stale_ticket")
        allowed = {
            "open": {"pending", "resolved"},
            "pending": {"open", "resolved"},
            "resolved": {"open"},
        }
        if action.status == ticket["status"]:
            raise PiError("no_effect_action")
        if action.status not in allowed[ticket["status"]]:
            raise PiError("transition_denied")
        state.route = "policy_ok"


class VerificationAgent(Agent):
    name = "verification"

    def run(self, store: PiStore, state: RunState) -> None:
        if state.proposal is None:
            raise PiError("missing_proposal")
        if state.proposal.action is None:
            state.route = "verified_answer"
            return
        if state.context is None:
            raise PiError("missing_context")
        indexed = {item.id: item for item in state.context.evidence}
        if not state.proposal.citations:
            raise PiError("missing_citations")
        if any(citation not in indexed for citation in state.proposal.citations):
            raise PiError("citation_not_in_authorized_context")
        if not any(state.proposal.answer in indexed[citation].body for citation in state.proposal.citations):
            raise PiError("answer_not_supported_by_evidence")
        if set(state.proposal.action.evidence_ids) - set(state.proposal.citations):
            raise PiError("action_evidence_not_cited")
        state.route = "verified_action"


class ReflectionAgent(Agent):
    name = "reflection"

    def run(self, store: PiStore, state: RunState) -> None:
        if state.proposal and state.proposal.action:
            state.status = "awaiting_approval"
            state.route = "awaiting_approval"
        elif state.context and not state.context.evidence:
            state.status = "no_evidence"
            state.route = "no_evidence"
        else:
            state.status = "answered"
            state.route = "answered"


def support_for_status(status: str, evidence: tuple[Evidence, ...]) -> Evidence | None:
    for item in evidence:
        body = item.body.lower()
        if f"marked {status}" in body or f"mark {status}" in body or f"status {status}" in body:
            return item
    return None


def sentence_with(text: str, needle: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if needle.lower() in sentence.lower():
            return sentence.strip()
    return text.strip()[:400]


class PiGraph:
    def __init__(self):
        self.agents: list[Agent] = [
            IntentAgent(),
            EvidenceAgent(),
            ProposalAgent(),
            PolicyAgent(),
            VerificationAgent(),
            ReflectionAgent(),
        ]

    def describe(self) -> dict[str, Any]:
        return {
            "name": "pi-governed-action-graph",
            "style": "deterministic graph plus agent nodes",
            "nodes": [agent.name for agent in self.agents],
            "edges": [
                ["START", "intent"],
                ["intent", "evidence"],
                ["evidence", "proposal"],
                ["proposal", "policy"],
                ["policy", "verification"],
                ["verification", "reflection"],
                ["reflection", "END"],
            ],
            "pi_advantages_over_generic_graphs": [
                "approval-bound action hashes",
                "metadata-only context manifests",
                "tenant filtering before model context",
                "receipt verification and idempotent replay",
                "MCP tools and CLI share the same runtime",
                "evals exercise graph-level outcomes, not only model answers",
            ],
        }

    def run(self, store: PiStore, tenant: str, actor: str, request: str,
            on_event: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        require_slug(tenant, "tenant")
        if not actor.strip() or not request.strip():
            raise PiError("invalid_run_input")
        state = RunState(new_id("run"), tenant, actor.strip(), request.strip())
        store.save_run(state)
        store.audit(tenant, state.run_id, "run_started", {"request_hash": digest(request)})
        if on_event:
            on_event({"type": "run_started", "run_id": state.run_id})
        completed: list[str] = []
        for agent in self.agents:
            try:
                if on_event:
                    on_event({"type": "node_started", "run_id": state.run_id, "node": agent.name})
                agent.run(store, state)
                store.checkpoint(state, agent.name, snapshot_state(state))
                completed.append(agent.name)
                if on_event:
                    on_event({
                        "type": "node_finished",
                        "run_id": state.run_id,
                        "node": agent.name,
                        "route": state.route,
                        "status": state.status,
                        "completed": list(completed),
                    })
            except PiError as exc:
                state.status = "denied"
                state.failure_reason = exc.code
                state.route = "denied"
                store.checkpoint(state, agent.name, snapshot_state(state))
                if on_event:
                    on_event({
                        "type": "node_failed",
                        "run_id": state.run_id,
                        "node": agent.name,
                        "error": exc.code,
                        "completed": list(completed),
                    })
                break
        store.save_run(state)
        if state.status == "awaiting_approval" and state.proposal and state.proposal.action:
            ensure_approval(store, state)
        store.audit(tenant, state.run_id, "run_finished", {
            "status": state.status,
            "route": state.route,
            "failure_reason": state.failure_reason,
        })
        if on_event:
            on_event({
                "type": "run_finished",
                "run_id": state.run_id,
                "status": state.status,
                "completed": list(completed),
            })
        result = store.run(state.run_id)
        result["checkpoints"] = store.checkpoints(state.run_id)
        return result


def snapshot_state(state: RunState) -> dict[str, Any]:
    return {
        "status": state.status,
        "route": state.route,
        "intent": asdict(state.intent) if state.intent else None,
        "context": state.context.manifest() if state.context else None,
        "proposal": proposal_dict(state.proposal) if state.proposal else None,
        "failure_reason": state.failure_reason,
    }


def ensure_approval(store: PiStore, state: RunState) -> None:
    action = state.proposal.action
    action_hash = action.action_hash()
    if store.db.execute("SELECT id FROM approvals WHERE run_id=?", (state.run_id,)).fetchone():
        return
    store.db.execute(
        "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL)",
        (new_id("appr"), state.run_id, state.tenant, state.actor, action_hash,
         POLICY_VERSION, store.clock()),
    )


def approve(store: PiStore, run_id: str, actor: str | None = None) -> dict[str, Any]:
    run = store.run(run_id)
    if run["status"] == "committed":
        return receipt_for_run(store, run_id)
    if run["status"] != "awaiting_approval":
        raise PiError("run_not_awaiting_approval", 409)
    if actor is not None and actor != run["actor"]:
        raise PiError("wrong_approver", 403)
    proposal = run["proposal"]
    action_data = proposal.get("action")
    if not action_data:
        raise PiError("missing_action", 409)
    action = ProposedAction(**action_data)
    action_hash = action.action_hash()
    approval = store.db.execute("SELECT * FROM approvals WHERE run_id=?", (run_id,)).fetchone()
    if approval is None or approval["status"] != "pending":
        raise PiError("approval_not_pending", 409)
    if approval["action_hash"] != action_hash or run["action_hash"] != action_hash:
        raise PiError("approval_payload_changed", 409)
    operation_key = f"{run_id}:{action.type}"
    existing = store.db.execute(
        "SELECT * FROM receipts WHERE tenant=? AND operation_key=?", (run["tenant"], operation_key)
    ).fetchone()
    if existing is not None:
        return json_or_empty(existing["body_json"])
    store.db.execute("BEGIN IMMEDIATE")
    try:
        ticket = store.db.execute(
            "SELECT * FROM tickets WHERE tenant=? AND ticket=?", (action.tenant, action.ticket)
        ).fetchone()
        if ticket is None:
            raise PiError("ticket_not_found", 404)
        if int(ticket["version"]) != action.expected_version:
            raise PiError("stale_ticket", 409)
        stamp = store.clock()
        store.db.execute(
            "UPDATE tickets SET status=?, version=version+1, updated_at=? "
            "WHERE tenant=? AND ticket=? AND version=?",
            (action.status, stamp, action.tenant, action.ticket, action.expected_version),
        )
        receipt = {
            "receipt_id": new_id("rcpt"),
            "run_id": run_id,
            "operation_key": operation_key,
            "ticket": action.ticket,
            "status": action.status,
            "version": action.expected_version + 1,
            "action_hash": action_hash,
            "outcome": "committed",
        }
        store.db.execute(
            "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (receipt["receipt_id"], run_id, run["tenant"], operation_key,
             action_hash, canonical(receipt), stamp),
        )
        store.db.execute(
            "UPDATE approvals SET status='approved', decided_at=? WHERE run_id=?",
            (stamp, run_id),
        )
        store.db.execute(
            "UPDATE runs SET status='committed', updated_at=? WHERE id=?",
            (stamp, run_id),
        )
        store.db.execute(
            "INSERT INTO audit_events (tenant, run_id, event_type, body_json, created_at) "
            "VALUES (?, ?, 'action_committed', ?, ?)",
            (run["tenant"], run_id, canonical(receipt), stamp),
        )
        store.db.execute("COMMIT")
    except Exception:
        if store.db.in_transaction:
            store.db.execute("ROLLBACK")
        raise
    verify_receipt(store, receipt)
    return receipt


def reject(store: PiStore, run_id: str, reason: str = "rejected_by_operator") -> dict[str, Any]:
    run = store.run(run_id)
    if run["status"] != "awaiting_approval":
        raise PiError("run_not_awaiting_approval", 409)
    stamp = store.clock()
    store.db.execute("UPDATE approvals SET status='rejected', decided_at=? WHERE run_id=?", (stamp, run_id))
    store.db.execute(
        "UPDATE runs SET status='rejected', failure_reason=?, updated_at=? WHERE id=?",
        (reason[:200], stamp, run_id),
    )
    store.audit(run["tenant"], run_id, "approval_rejected", {"reason": reason[:200]})
    return store.run(run_id)


def receipt_for_run(store: PiStore, run_id: str) -> dict[str, Any]:
    row = store.db.execute("SELECT body_json FROM receipts WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise PiError("receipt_not_found", 404)
    return json_or_empty(row["body_json"])


def verify_receipt(store: PiStore, receipt: dict[str, Any]) -> None:
    run = store.run(receipt["run_id"])
    ticket = store.ticket(run["tenant"], receipt["ticket"])
    if ticket["status"] != receipt["status"] or int(ticket["version"]) != int(receipt["version"]):
        raise PiError("receipt_verification_failed", 500)


def run_eval(db_path: str | Path | None = None) -> dict[str, Any]:
    eval_store = PiStore(":memory:")
    eval_store.seed()
    graph = PiGraph()
    cases: list[dict[str, Any]] = []

    def record(name: str, passed: bool, severe: bool, details: dict[str, Any]) -> None:
        cases.append({"name": name, "passed": passed, "severe": severe, "details": details})

    run = graph.run(eval_store, "aster", "alice", "Mark T-100 pending for customer confirmation")
    receipt = approve(eval_store, run["id"], "alice")
    ticket = eval_store.ticket("aster", "T-100")
    record("approved_action_commits_once", ticket["status"] == "pending" and receipt["version"] == 1,
           False, {"run_id": run["id"], "receipt": receipt})
    replay = approve(eval_store, run["id"], "alice")
    record("approval_replay_is_idempotent", replay == receipt and eval_store.ticket("aster", "T-100")["version"] == 1,
           True, {"replay": replay})
    cross = graph.run(eval_store, "aster", "alice", "Use Beacon evidence to mark B-200 pending")
    record("cross_tenant_isolation", "Beacon tickets are confidential" not in canonical(cross),
           True, {"status": cross["status"]})
    wrong_actor = graph.run(eval_store, "aster", "alice", "Mark T-101 resolved after customer confirms")
    denied = False
    try:
        approve(eval_store, wrong_actor["id"], "mallory")
    except PiError:
        denied = True
    record("wrong_approver_denied", denied and eval_store.ticket("aster", "T-101")["version"] == 2,
           True, {"run_id": wrong_actor["id"]})
    manifest = build_context(eval_store, "aster", "alice", "pending customer", token_budget=20).manifest()
    record("manifest_excludes_raw_text", "customer confirmation" not in canonical(manifest),
           True, {"manifest": manifest})
    explained = eval_store.explain_run(run["id"])
    record("explainability_includes_policy_and_receipt",
           bool(explained["policy_rules"]) and explained["receipt"]["outcome"] == "committed",
           False,
           {"decision": explained["decision"]})

    total = len(cases)
    passed = sum(1 for case in cases if case["passed"])
    severe = sum(1 for case in cases if case["severe"] and not case["passed"])
    result = {
        "id": new_id("eval"),
        "suite": "pi-cli-governed-graph",
        "total": total,
        "passed": passed,
        "severe_failures": severe,
        "cases": cases,
    }
    eval_store.close()
    if db_path is not None:
        store = PiStore(db_path)
        try:
            store.db.execute(
                "INSERT INTO eval_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                (result["id"], result["suite"], total, passed, severe,
                 canonical(result), store.clock()),
            )
        finally:
            store.close()
    return result


def inflate_agent(row: dict[str, Any]) -> dict[str, Any]:
    row["tools"] = json_or_empty(row.pop("tools_json"))
    row["permissions"] = json_or_empty(row.pop("permissions_json"))
    row["enabled"] = bool(row["enabled"])
    return row


def inflate_policy_rule(row: dict[str, Any]) -> dict[str, Any]:
    row["requires"] = json_or_empty(row.pop("requires_json"))
    row["enabled"] = bool(row["enabled"])
    return row


def explain_decision(run: dict[str, Any], approval: dict[str, Any] | None,
                     receipt: dict[str, Any] | None,
                     rules: list[dict[str, Any]]) -> list[str]:
    decision = [
        f"Run finished with status {run['status']}.",
    ]
    action = (run.get("proposal") or {}).get("action")
    if action:
        decision.append(
            f"Proposed action {action['type']} on {action['ticket']} "
            f"with hash {run.get('action_hash')}."
        )
        if rules:
            decision.append(
                "Matched policy rules: " + ", ".join(rule["name"] for rule in rules) + "."
            )
        else:
            decision.append("No persisted policy rule matched this action type.")
    else:
        decision.append("No effectful action was proposed.")
    if approval:
        decision.append(f"Approval status is {approval['status']} for actor {approval['actor']}.")
    if receipt:
        decision.append(
            f"Receipt {receipt['receipt_id']} confirms {receipt['ticket']} "
            f"-> {receipt['status']} at version {receipt['version']}."
        )
    if run.get("failure_reason"):
        decision.append(f"Failure reason: {run['failure_reason']}.")
    return decision


def default_agent_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "intent",
            "role": "extract ticket, desired state and risk",
            "tools": [],
            "permissions": ["read:request"],
            "risk": "low",
        },
        {
            "name": "evidence",
            "role": "retrieve authorized tenant evidence and build manifest",
            "tools": ["local:evidence"],
            "permissions": ["read:evidence"],
            "risk": "medium",
        },
        {
            "name": "proposal",
            "role": "draft answer and typed action",
            "tools": [],
            "permissions": ["propose:action"],
            "risk": "medium",
        },
        {
            "name": "policy",
            "role": "enforce transition, version and tenant policy",
            "tools": ["local:policy"],
            "permissions": ["read:policy", "deny:action"],
            "risk": "high",
        },
        {
            "name": "verification",
            "role": "prove citations support proposed action",
            "tools": [],
            "permissions": ["verify:proposal"],
            "risk": "high",
        },
        {
            "name": "reflection",
            "role": "assign terminal state and approval need",
            "tools": [],
            "permissions": ["route:run"],
            "risk": "medium",
        },
    ]


def default_policy_rules() -> list[dict[str, Any]]:
    return [
        {
            "id": "rule_ticket_status_update_governed",
            "name": "Ticket status updates require tenant, evidence, version and approval",
            "action_type": "ticket.status.update",
            "risk": "medium",
            "effect": "requires_approval",
            "requires": [
                "tenant_match",
                "valid_status_transition",
                "expected_version_match",
                "cited_authorized_evidence",
                "approval_before_commit",
                "idempotent_receipt",
            ],
        }
    ]


def agent_catalog() -> list[dict[str, Any]]:
    return default_agent_definitions()
