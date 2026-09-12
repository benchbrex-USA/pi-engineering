"""Pi Engineering teaching runtime. Offline, stdlib-only, not production security."""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Callable, Literal, Protocol


class Denied(ValueError):
    """A request failed a deterministic validation or policy check."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    tenant: str
    actor: str
    run_id: str
    authenticated: bool = True

    def validate(self) -> None:
        if not self.authenticated or not all((self.tenant, self.actor, self.run_id)):
            raise Denied("authentication_required")


@dataclass(frozen=True)
class Evidence:
    id: str
    tenant: str
    text: str
    version: int = 1


@dataclass(frozen=True)
class ManifestItem:
    source_id: str
    version: int
    content_hash: str
    token_cost: int
    trust_class: str = "authorized source evidence"


@dataclass(frozen=True)
class ContextBundle:
    bundle_id: str
    run_id: str
    tenant: str
    query_hash: str
    source_snapshot: str
    evidence: tuple[Evidence, ...]
    manifest_items: tuple[ManifestItem, ...]
    token_cost: int
    token_budget: int | None
    truncated: bool
    excluded_items_and_reasons: tuple[dict, ...]

    def public_manifest(self) -> dict:
        """Metadata-only manifest for diagnostics; raw evidence text is excluded."""
        return {
            "bundle_id": self.bundle_id,
            "run_id": self.run_id,
            "tenant": self.tenant,
            "query_hash": self.query_hash,
            "source_snapshot": self.source_snapshot,
            "items": [asdict(item) for item in self.manifest_items],
            "token_cost": self.token_cost,
            "token_budget": self.token_budget,
            "truncated": self.truncated,
            "excluded_items_and_reasons": list(self.excluded_items_and_reasons),
        }


@dataclass(frozen=True)
class Action:
    tenant: str
    ticket: str
    expected_version: int
    status: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Proposal:
    answer: str
    citations: tuple[str, ...]
    action: Action | None


@dataclass(frozen=True)
class Outcome:
    status: str
    answer: str = ""
    action: Action | None = None
    receipt: dict | None = None
    steps: int = 0


class Model(Protocol):
    def __call__(self, request: str, evidence: list[Evidence], feedback: str) -> dict:
        ...


TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")
RetrievalMethod = Literal["bm25", "overlap"]


def tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def source_snapshot(evidence: list[Evidence] | tuple[Evidence, ...]) -> str:
    return digest([(e.id, e.version, digest(e.text)) for e in evidence])


class Repository:
    """Filtering is enforced before evidence reaches the model."""
    def __init__(self, evidence: list[Evidence]):
        self.evidence = tuple(evidence)

    def _allowed(self, principal: Principal) -> list[Evidence]:
        principal.validate()
        return [e for e in self.evidence if e.tenant == principal.tenant]

    def score(self, principal: Principal, query: str,
              method: RetrievalMethod = "bm25") -> list[tuple[Evidence, float]]:
        allowed = self._allowed(principal)
        query_terms = tokens(query)
        if not query_terms:
            return []
        if method == "overlap":
            terms = set(query_terms)
            scored = [(e, float(len(terms & set(tokens(e.text))))) for e in allowed]
        elif method == "bm25":
            scored = self._bm25(allowed, query_terms)
        else:
            raise ValueError("unknown retrieval method")
        return [(e, score) for e, score in sorted(scored, key=lambda x: (-x[1], x[0].id))
                if score > 0.0]

    def _bm25(self, evidence: list[Evidence], query_terms: list[str],
              k1: float = 1.2, b: float = 0.75) -> list[tuple[Evidence, float]]:
        if not evidence:
            return []
        doc_terms = {e.id: tokens(e.text) for e in evidence}
        avg_len = sum(len(value) for value in doc_terms.values()) / len(evidence) or 1.0
        unique_query_terms = tuple(dict.fromkeys(query_terms))
        scored: list[tuple[Evidence, float]] = []
        for item in evidence:
            terms = doc_terms[item.id]
            if not terms:
                scored.append((item, 0.0))
                continue
            length = len(terms)
            score = 0.0
            for term in unique_query_terms:
                frequency = terms.count(term)
                if frequency == 0:
                    continue
                doc_frequency = sum(1 for values in doc_terms.values() if term in values)
                idf = math.log(1.0 + (len(evidence) - doc_frequency + 0.5)
                               / (doc_frequency + 0.5))
                numerator = frequency * (k1 + 1.0)
                denominator = frequency + k1 * (1.0 - b + b * length / avg_len)
                score += idf * numerator / denominator
            scored.append((item, score))
        return scored

    def retrieve(self, principal: Principal, query: str, limit: int = 4,
                 method: RetrievalMethod = "bm25") -> list[Evidence]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        return [e for e, _ in self.score(principal, query, method)[:limit]]

    def build_context(self, principal: Principal, query: str, limit: int = 4,
                      token_budget: int | None = None,
                      method: RetrievalMethod = "bm25") -> ContextBundle:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        if token_budget is not None and (type(token_budget) is not int or token_budget < 1):
            raise ValueError("token_budget must be a positive integer")
        ranked = self.score(principal, query, method)
        selected: list[Evidence] = []
        manifest_items: list[ManifestItem] = []
        excluded: list[dict] = []
        used = 0
        for item, score in ranked:
            cost = len(tokens(item.text))
            if len(selected) >= limit:
                excluded.append({"source_id": item.id, "reason": "limit_exceeded",
                                 "score": round(score, 6)})
                continue
            if token_budget is not None and used + cost > token_budget:
                excluded.append({"source_id": item.id, "reason": "budget_exceeded",
                                 "token_cost": cost, "score": round(score, 6)})
                continue
            selected.append(item)
            manifest_items.append(ManifestItem(item.id, item.version, digest(item.text), cost))
            used += cost
        bundle_seed = {
            "run_id": principal.run_id,
            "tenant": principal.tenant,
            "query_hash": digest(query),
            "source_snapshot": source_snapshot(tuple(selected)),
            "selected": [(e.id, e.version) for e in selected],
            "budget": token_budget,
        }
        return ContextBundle(
            bundle_id=digest(bundle_seed)[:24],
            run_id=principal.run_id,
            tenant=principal.tenant,
            query_hash=digest(query),
            source_snapshot=source_snapshot(tuple(selected)),
            evidence=tuple(selected),
            manifest_items=tuple(manifest_items),
            token_cost=used,
            token_budget=token_budget,
            truncated=bool(excluded),
            excluded_items_and_reasons=tuple(excluded),
        )


def parse_proposal(raw: dict, principal: Principal) -> Proposal:
    if type(raw) is not dict or set(raw) != {"answer", "citations", "action"}:
        raise Denied("invalid_proposal_fields")
    answer, citations, data = raw["answer"], raw["citations"], raw["action"]
    if type(answer) is not str or not answer or len(answer) > 4000:
        raise Denied("invalid_answer")
    if (type(citations) is not list or not citations or len(citations) > 8
            or any(type(x) is not str for x in citations)
            or len(set(citations)) != len(citations)):
        raise Denied("invalid_citations")
    action = None
    if data is not None:
        if type(data) is not dict or set(data) != {"ticket", "expected_version", "status"}:
            raise Denied("invalid_action_fields")
        if (type(data["ticket"]) is not str or not data["ticket"]
                or type(data["expected_version"]) is not int
                or data["expected_version"] < 0
                or type(data["status"]) is not str
                or data["status"] not in {"open", "pending", "resolved"}):
            raise Denied("invalid_action")
        action = Action(principal.tenant, data["ticket"], data["expected_version"],
                        data["status"], tuple(citations))
    return Proposal(answer, tuple(citations), action)


def verify(proposal: Proposal, evidence: list[Evidence]) -> None:
    """Deliberately narrow: validates an extractive quote, not arbitrary semantics."""
    indexed = {e.id: e for e in evidence}
    if any(cid not in indexed for cid in proposal.citations):
        raise Denied("citation_not_in_authorized_evidence")
    if not any(proposal.answer in indexed[cid].text for cid in proposal.citations):
        raise Denied("answer_not_supported_by_exact_quote")


class Broker:
    """Trusted host API. Never expose issue_approval or DB access as model tools.

    Principal is trusted input in this simulation, NOT an authentication scheme.
    SQLite makes one local effect and receipt atomic; external APIs need their
    own idempotency/reconciliation protocol. The approval token is a local secret.
    """
    def __init__(self, path: str = ":memory:", now: Callable[[], float] = time.time):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.now = now
        self.policy_version = "policy-v1"
        self.fail_before_commit = False
        self.audit: list[dict] = []
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                tenant TEXT, ticket TEXT, status TEXT, version INTEGER,
                PRIMARY KEY(tenant, ticket));
            CREATE TABLE IF NOT EXISTS approvals (
                token_hash TEXT PRIMARY KEY, tenant TEXT, actor TEXT, run_id TEXT,
                action_hash TEXT, policy TEXT, expires REAL, consumed INTEGER);
            CREATE TABLE IF NOT EXISTS receipts (
                tenant TEXT, operation_key TEXT, actor TEXT, run_id TEXT,
                action_hash TEXT, body TEXT, PRIMARY KEY(tenant, operation_key));
        """)

    def close(self) -> None:
        self.db.close()

    def seed(self, tenant: str, ticket: str, status: str = "open", version: int = 0) -> None:
        self.db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?)",
                        (tenant, ticket, status, version))

    def read(self, p: Principal, ticket: str) -> dict:
        p.validate()
        row = self.db.execute("SELECT * FROM tickets WHERE tenant=? AND ticket=?",
                              (p.tenant, ticket)).fetchone()
        if row is None:
            raise Denied("ticket_unavailable")
        return dict(row)

    def _validate_action(self, p: Principal, action: Action) -> dict:
        p.validate()
        if (not isinstance(action, Action) or action.tenant != p.tenant
                or action.status not in {"open", "pending", "resolved"}
                or type(action.expected_version) is not int or action.expected_version < 0
                or not action.evidence_ids):
            raise Denied("action_policy_denied")
        return self.read(p, action.ticket)

    def issue_approval(self, p: Principal, action: Action, ttl: float = 60.0) -> str:
        current = self._validate_action(p, action)
        if current["version"] != action.expected_version:
            raise Denied("stale_resource")
        if not 0 < ttl <= 300:
            raise Denied("invalid_approval_ttl")
        token = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                        (hashlib.sha256(token.encode()).hexdigest(), p.tenant, p.actor,
                         p.run_id, digest(asdict(action)), self.policy_version, self.now() + ttl))
        return token

    def execute(self, p: Principal, action: Action, token: str, operation_key: str) -> dict:
        self._validate_action(p, action)
        if type(operation_key) is not str or not 1 <= len(operation_key) <= 128:
            raise Denied("invalid_operation_key")
        action_hash = digest(asdict(action))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT * FROM receipts WHERE tenant=? AND operation_key=?",
                (p.tenant, operation_key)).fetchone()
            if existing is not None:
                if (existing["action_hash"], existing["actor"], existing["run_id"]) != (
                        action_hash, p.actor, p.run_id):
                    raise Denied("idempotency_collision")
                self.db.execute("COMMIT")
                return json.loads(existing["body"])
            hashed_token = hashlib.sha256(token.encode()).hexdigest()
            approval = self.db.execute("SELECT * FROM approvals WHERE token_hash=?",
                                       (hashed_token,)).fetchone()
            if approval is None:
                raise Denied("approval_required")
            expected = (p.tenant, p.actor, p.run_id, action_hash, self.policy_version)
            observed = tuple(approval[k] for k in ("tenant", "actor", "run_id", "action_hash", "policy"))
            if observed != expected or approval["consumed"] or approval["expires"] <= self.now():
                raise Denied("approval_invalid")
            changed = self.db.execute(
                "UPDATE tickets SET status=?, version=version+1 "
                "WHERE tenant=? AND ticket=? AND version=?",
                (action.status, p.tenant, action.ticket, action.expected_version))
            if changed.rowcount != 1:
                raise Denied("stale_resource")
            receipt = {"operation_key": operation_key, "ticket": action.ticket,
                       "status": action.status, "version": action.expected_version + 1,
                       "action_hash": action_hash, "outcome": "committed"}
            self.db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
                            (p.tenant, operation_key, p.actor, p.run_id,
                             action_hash, canonical(receipt)))
            self.db.execute("UPDATE approvals SET consumed=1 WHERE token_hash=?", (hashed_token,))
            if self.fail_before_commit:
                raise RuntimeError("injected_failure")
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.audit.append({"event": "action_committed", "run_id": p.run_id,
                           "action_hash": action_hash})
        return receipt


# BEGIN WALKTHROUGH

def run(request: str, p: Principal, repository: Repository, model: Model,
        broker: Broker, max_steps: int = 3, deadline_seconds: float = 5.0,
        approval_token: str | None = None, operation_key: str | None = None) -> Outcome:
    p.validate()
    if type(max_steps) is not int or max_steps < 1 or deadline_seconds <= 0:
        raise ValueError("invalid_budget")
    started = time.monotonic()
    evidence = repository.retrieve(p, request)
    if not evidence:
        return Outcome("no_evidence")
    seen: set[str] = set()
    feedback = ""
    for step in range(1, max_steps + 1):
        if time.monotonic() - started >= deadline_seconds:
            return Outcome("deadline_exceeded", steps=step - 1)
        try:
            raw = model(request, evidence, feedback)
            if time.monotonic() - started >= deadline_seconds:
                return Outcome("deadline_exceeded", steps=step)
            fingerprint = digest(raw)
            if fingerprint in seen:
                return Outcome("no_progress", steps=step)
            seen.add(fingerprint)
            proposal = parse_proposal(raw, p)
            verify(proposal, evidence)
        except Denied as exc:
            feedback = str(exc)
            continue
        except Exception:
            return Outcome("model_or_adapter_error", steps=step)
        if proposal.action is None:
            return Outcome("answered", proposal.answer, steps=step)
        if approval_token is None or operation_key is None:
            return Outcome("awaiting_approval", proposal.answer, proposal.action, steps=step)
        try:
            receipt = broker.execute(p, proposal.action, approval_token, operation_key)
        except Denied:
            return Outcome("action_denied", proposal.answer, proposal.action, steps=step)
        except Exception:
            return Outcome("action_error_reconcile", proposal.answer, proposal.action, steps=step)
        observed = broker.read(p, proposal.action.ticket)
        if (observed["version"] < receipt["version"] or
                (observed["version"] == receipt["version"] and observed["status"] != receipt["status"])):
            return Outcome("receipt_inconsistent", steps=step)
        return Outcome("committed", proposal.answer, proposal.action, receipt, step)
    return Outcome("budget_exhausted", steps=max_steps)

# END WALKTHROUGH


def demo() -> None:
    p = Principal("aster", "operator-1", "run-1")
    repository = Repository([Evidence("policy-1", "aster", "Tickets may be marked pending.")])
    broker = Broker()
    broker.seed("aster", "T-1")
    def model(request: str, evidence: list[Evidence], feedback: str) -> dict:
        return {"answer": "Tickets may be marked pending.", "citations": ["policy-1"],
                "action": {"ticket": "T-1", "expected_version": 0, "status": "pending"}}
    draft = run("Tickets pending", p, repository, model, broker)
    print("First pass:", draft.status)
    assert draft.action is not None
    # Trusted human/UI boundary is simulated by this explicit host-side call.
    approval = broker.issue_approval(p, draft.action)
    result = run("Tickets pending", p, repository, model, broker,
                 approval_token=approval, operation_key="intent-1")
    print("Approved pass:", result.status)
    print("Receipt:", canonical(result.receipt))
    broker.close()


if __name__ == "__main__":
    demo()
