"""SQLite snapshots, reviewer decisions, and atomic local mock execution."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterator
import uuid

from .domain import Response, canonical, digest, now


class RequestOwnershipLost(ValueError):
    pass


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
              request_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
              actor_role TEXT NOT NULL, input_fingerprint TEXT NOT NULL, route TEXT,
              source_ids_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              response_json TEXT, actor_id TEXT, processing_owner TEXT, lease_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS proposals (
              proposal_id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests,
              action_type TEXT NOT NULL, payload_canonical_json TEXT NOT NULL,
              payload_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(request_id, action_type, payload_hash));
            CREATE TABLE IF NOT EXISTS approvals (
              approval_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals,
              payload_hash TEXT NOT NULL, reviewer_role TEXT NOT NULL, decision TEXT NOT NULL,
              decided_at TEXT NOT NULL, reviewer_actor_id TEXT, approved_action_type TEXT, UNIQUE(proposal_id));
            CREATE TABLE IF NOT EXISTS executions (
              proposal_id TEXT PRIMARY KEY REFERENCES proposals, execution_key TEXT UNIQUE NOT NULL,
              adapter_result_json TEXT, outcome TEXT NOT NULL, attempts INTEGER NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mock_actions (
              proposal_id TEXT PRIMARY KEY REFERENCES proposals, action_id TEXT UNIQUE NOT NULL,
              action_type TEXT NOT NULL, created_at TEXT NOT NULL, payload_canonical_json TEXT, payload_hash TEXT);
            CREATE TABLE IF NOT EXISTS execution_attempts (
              proposal_id TEXT NOT NULL REFERENCES proposals, attempt INTEGER NOT NULL,
              outcome TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(proposal_id, attempt));
        """)
        # Preserve existing assessment databases. No destructive reset or inferred new payload.
        for table, columns in {
            "requests": {"actor_id": "TEXT", "processing_owner": "TEXT", "lease_until": "REAL NOT NULL DEFAULT 0"},
            "approvals": {"reviewer_actor_id": "TEXT", "approved_action_type": "TEXT"},
            "mock_actions": {"payload_canonical_json": "TEXT", "payload_hash": "TEXT"},
        }.items():
            existing = {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}
            for column, declaration in columns.items():
                if column not in existing:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        self.db.execute("UPDATE requests SET actor_id='legacy:' || actor_role WHERE actor_id IS NULL")
        self.db.execute("UPDATE approvals SET reviewer_actor_id='legacy:' || reviewer_role WHERE reviewer_actor_id IS NULL")
        self.db.execute("UPDATE approvals SET approved_action_type=(SELECT action_type FROM proposals WHERE proposals.proposal_id=approvals.proposal_id) WHERE approved_action_type IS NULL")
        self.db.commit()
        self.db.executescript("""
            CREATE TRIGGER IF NOT EXISTS immutable_proposal BEFORE UPDATE OF request_id,action_type,payload_canonical_json,payload_hash ON proposals
              BEGIN SELECT RAISE(ABORT, 'Proposal snapshots are immutable; create a new pending proposal.'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_approval BEFORE UPDATE ON approvals
              BEGIN SELECT RAISE(ABORT, 'Reviewer decisions are immutable.'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_mock_action BEFORE UPDATE ON mock_actions
              BEGIN SELECT RAISE(ABORT, 'Executed mock payloads are immutable.'); END;
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        # ponytail: serialize local mock writes. Real integrations need adapter-side execution-key reconciliation.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def cached_request(self, request_id: str, fingerprint: str) -> Response | None:
        row = self.db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if not row:
            return None
        if row["input_fingerprint"] != fingerprint:
            raise ValueError("request_id was reused with different input")
        return json.loads(row["response_json"]) if row["response_json"] else None

    def start_request(self, request_id: str, role: str, fingerprint: str, actor_id: str | None = None, owner: str | None = None) -> bool:
        owner = owner or str(uuid.uuid4())
        with self.transaction():
            row = self.db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row:
                if row["input_fingerprint"] != fingerprint:
                    raise ValueError("request_id was reused with different input")
                if row["response_json"] or row["lease_until"] > time.time():
                    return False
                self.db.execute("UPDATE requests SET processing_owner=?,lease_until=? WHERE request_id=?", (owner, time.time() + 300, request_id))
                return True
            self.db.execute("INSERT INTO requests (request_id,idempotency_key,actor_role,input_fingerprint,route,source_ids_json,status,created_at,response_json,actor_id,processing_owner,lease_until) VALUES (?, ?, ?, ?, 'pending', '[]', 'processing', ?, NULL, ?, ?, ?)",
                            (request_id, request_id, role, fingerprint, now(), actor_id or f"{role}-test", owner, time.time() + 300))
            return True

    def save_request(self, result: Response, role: str, fingerprint: str, owner: str | None = None) -> None:
        cursor = self.db.execute("UPDATE requests SET route=?,source_ids_json=?,status=?,response_json=?,lease_until=0 WHERE request_id=? AND actor_role=? AND input_fingerprint=? AND (? IS NULL OR processing_owner=?)",
                                 (result["department"], canonical(result["sources"]), result["action_status"], canonical(result), result["request_id"], role, fingerprint, owner, owner))
        if cursor.rowcount != 1:
            self.db.rollback()
            raise RequestOwnershipLost("Request ownership changed; retry the stable request ID.")
        self.db.commit()

    def propose(self, request_id: str, action_type: str, payload: dict[str, Any], owner: str | None = None) -> dict[str, str]:
        if action_type not in {"desk_ticket", "incident_task"} or not isinstance(payload, dict):
            raise ValueError("Only local mock tickets and incident tasks are supported.")
        payload_json, payload_hash = canonical(payload), digest(payload)
        with self.transaction():
            if owner is not None:
                request = self.db.execute("SELECT processing_owner,lease_until,response_json FROM requests WHERE request_id=?", (request_id,)).fetchone()
                if not request or request["processing_owner"] != owner or request["lease_until"] <= time.time() or request["response_json"]:
                    raise RequestOwnershipLost("A stale request worker cannot create a proposal.")
            row = self.db.execute("SELECT proposal_id,payload_hash,status FROM proposals WHERE request_id=? AND action_type=? AND payload_hash=?", (request_id, action_type, payload_hash)).fetchone()
            if row:
                return dict(row)
            proposal_id = str(uuid.uuid4())
            self.db.execute("INSERT INTO proposals VALUES (?, ?, ?, ?, ?, 'pending', ?)", (proposal_id, request_id, action_type, payload_json, payload_hash, now()))
            return {"proposal_id": proposal_id, "payload_hash": payload_hash, "status": "pending"}

    def inspect(self, proposal_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError("Unknown proposal ID.")
        payload = json.loads(row["payload_canonical_json"])
        if not isinstance(payload, dict) or digest(payload) != row["payload_hash"] or canonical(payload) != row["payload_canonical_json"]:
            raise ValueError("Persisted proposal failed its immutable payload check.")
        decision = self.db.execute("SELECT approval_id,decision,reviewer_role,reviewer_actor_id,decided_at FROM approvals WHERE proposal_id=?", (proposal_id,)).fetchone()
        return {"proposal_id": proposal_id, "request_id": row["request_id"], "action_type": row["action_type"], "status": row["status"], "payload_hash": row["payload_hash"], "payload": payload, "decision": dict(decision) if decision else None}

    def request_proposals(self, request_id: str) -> list[dict[str, Any]]:
        return [self.inspect(row["proposal_id"]) for row in self.db.execute("SELECT proposal_id FROM proposals WHERE request_id=? ORDER BY created_at", (request_id,))]

    def approve_and_execute(self, proposal_id: str, payload_hash: str, role: str, mode: str, actor_id: str | None = None) -> dict[str, Any]:
        if role != "ops_reviewer":
            raise PermissionError("Only Ops Reviewer may approve local actions under P03")
        self._check_mode(mode)
        with self.transaction():
            proposal = self.inspect(proposal_id)
            if proposal["payload_hash"] != payload_hash:
                raise ValueError("proposal ID or immutable payload hash does not match")
            if proposal["status"] == "pending":
                self.db.execute("UPDATE proposals SET status='approved' WHERE proposal_id=?", (proposal_id,))
                self.db.execute("INSERT INTO approvals (approval_id,proposal_id,payload_hash,reviewer_role,decision,decided_at,reviewer_actor_id,approved_action_type) VALUES (?, ?, ?, ?, 'approved', ?, ?, ?)",
                                (str(uuid.uuid4()), proposal_id, payload_hash, role, now(), actor_id or "ops_reviewer-test", proposal["action_type"]))
            elif proposal["status"] not in {"approved", "executing", "succeeded", "failed"}:
                raise ValueError(f"proposal is {proposal['status']}, not pending")
        return self.execute(proposal_id, mode)

    def reject(self, proposal_id: str, payload_hash: str, role: str, actor_id: str | None = None) -> None:
        if role != "ops_reviewer":
            raise PermissionError("Only Ops Reviewer may reject local actions")
        with self.transaction():
            proposal = self.inspect(proposal_id)
            if proposal["payload_hash"] != payload_hash or proposal["status"] not in {"pending", "rejected"}:
                raise ValueError("Only the exact pending proposal may be rejected.")
            if proposal["status"] == "rejected":
                return
            self.db.execute("UPDATE proposals SET status='rejected' WHERE proposal_id=?", (proposal_id,))
            self.db.execute("INSERT INTO approvals (approval_id,proposal_id,payload_hash,reviewer_role,decision,decided_at,reviewer_actor_id,approved_action_type) VALUES (?, ?, ?, ?, 'rejected', ?, ?, ?)",
                            (str(uuid.uuid4()), proposal_id, payload_hash, role, now(), actor_id or "ops_reviewer-test", proposal["action_type"]))

    def execution_result(self, proposal_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM executions WHERE proposal_id=?", (proposal_id,)).fetchone()
        result = dict(row) if row else {"proposal_id": proposal_id, "outcome": "not_executed"}
        action = self.db.execute("SELECT * FROM mock_actions WHERE proposal_id=?", (proposal_id,)).fetchone()
        if action and action["payload_canonical_json"] is None:
            result["outcome"] = "legacy_unverified"
        result["action"] = {"action_id": action["action_id"], "action_type": action["action_type"], "payload": json.loads(action["payload_canonical_json"]), "payload_hash": action["payload_hash"]} if action and action["payload_canonical_json"] is not None and result["outcome"] == "succeeded" else None
        result["attempt_history"] = [dict(attempt) for attempt in self.db.execute("SELECT attempt,outcome,created_at FROM execution_attempts WHERE proposal_id=? ORDER BY attempt", (proposal_id,))]
        return result

    @staticmethod
    def _check_mode(mode: str) -> None:
        if mode not in {"normal", "fail_once", "always_fail", "uncertain_once"}:
            raise ValueError("Unknown local adapter mode.")

    def execute(self, proposal_id: str, mode: str) -> dict[str, Any]:
        self._check_mode(mode)
        with self.transaction():
            proposal = self.inspect(proposal_id)
            approval = self.db.execute("SELECT * FROM approvals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not approval or approval["decision"] != "approved" or approval["reviewer_role"] != "ops_reviewer" or approval["payload_hash"] != proposal["payload_hash"] or approval["approved_action_type"] != proposal["action_type"]:
                raise PermissionError("Execution requires persisted approval of this exact payload.")
            if proposal["action_type"] not in {"desk_ticket", "incident_task"}:
                raise ValueError("Unsupported action type.")
            action = self.db.execute("SELECT * FROM mock_actions WHERE proposal_id=?", (proposal_id,)).fetchone()
            if action and action["payload_canonical_json"] is None:
                return self.execution_result(proposal_id)
            if action and (action["payload_hash"] != proposal["payload_hash"] or action["payload_canonical_json"] != canonical(proposal["payload"])):
                raise ValueError("Mock action does not match the approved payload.")
            if proposal["status"] in {"succeeded", "failed"}:
                if proposal["status"] == "succeeded" and not action:
                    raise ValueError("Success cannot be verified against a persisted mock action.")
                return self.execution_result(proposal_id)
            if proposal["status"] not in {"approved", "executing"}:
                raise ValueError("Proposal is not approved for execution.")
            for _ in range(2):
                previous = self.db.execute("SELECT * FROM executions WHERE proposal_id=?", (proposal_id,)).fetchone()
                attempts = previous["attempts"] if previous else 0
                if attempts >= 2:
                    return self.execution_result(proposal_id)
                self.db.execute("UPDATE proposals SET status='executing' WHERE proposal_id=?", (proposal_id,))
                if not action and (mode == "always_fail" or mode == "fail_once" and attempts == 0):
                    outcome = "adapter_failure" if mode == "always_fail" else "transient_failure"
                    self._record_attempt(proposal_id, attempts + 1, outcome)
                    self.db.execute("UPDATE proposals SET status=? WHERE proposal_id=?", ("failed" if outcome == "adapter_failure" else "approved", proposal_id))
                    if outcome == "adapter_failure":
                        return self.execution_result(proposal_id)
                    continue
                action_id = action["action_id"] if action else ("TICKET-" if proposal["action_type"] == "desk_ticket" else "TASK-") + proposal_id
                self.db.execute("INSERT OR IGNORE INTO mock_actions (proposal_id,action_id,action_type,created_at,payload_canonical_json,payload_hash) VALUES (?, ?, ?, ?, ?, ?)",
                                (proposal_id, action_id, proposal["action_type"], now(), canonical(proposal["payload"]), proposal["payload_hash"]))
                if mode == "uncertain_once" and attempts == 0:
                    self._record_attempt(proposal_id, 1, "uncertain")
                    return {**self.execution_result(proposal_id), "reconciliation_required": True}
                self._record_attempt(proposal_id, attempts + 1, "succeeded", {"action_id": action_id, "verified": True})
                self.db.execute("UPDATE proposals SET status='succeeded' WHERE proposal_id=?", (proposal_id,))
                return self.execution_result(proposal_id)
            return self.execution_result(proposal_id)

    def _record_attempt(self, proposal_id: str, attempt: int, outcome: str, result: dict[str, Any] | None = None) -> None:
        self.db.execute("INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(proposal_id) DO UPDATE SET adapter_result_json=excluded.adapter_result_json,outcome=excluded.outcome,attempts=excluded.attempts,updated_at=excluded.updated_at",
                        (proposal_id, proposal_id, canonical(result) if result else None, outcome, attempt, now()))
        self.db.execute("INSERT INTO execution_attempts VALUES (?, ?, ?, ?)", (proposal_id, attempt, outcome, now()))

    def history(self, role: str, actor_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT request_id,actor_id,actor_role,route,status,created_at,source_ids_json FROM requests WHERE (actor_id=? AND actor_role=?) OR ?='ops_reviewer' ORDER BY created_at", (actor_id, role, role))
        return [{**dict(row), "proposals": self.request_proposals(row["request_id"])} for row in rows]

    def request_response(self, request_id: str, role: str, actor_id: str) -> Response | None:
        row = self.db.execute("SELECT response_json FROM requests WHERE request_id=? AND ((actor_id=? AND actor_role=?) OR ?='ops_reviewer')",
                              (request_id, actor_id, role, role)).fetchone()
        if not row:
            raise PermissionError("Request is not available to this test identity.")
        return json.loads(row["response_json"]) if row["response_json"] else None
