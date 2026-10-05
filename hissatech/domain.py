"""Shared request and response contracts and stable serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ROLES = {"marketing", "customer_service", "product", "tech", "ops_reviewer"}
WORKFLOW_ROLES = {
    "marketing": "marketing",
    "customer_service": "customer_service",
    "product": "product",
    "tech": "tech",
}


@dataclass(frozen=True)
class Request:
    request_id: str
    role: str
    text: str
    actor_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "role", "text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string")
        if self.role not in ROLES:
            raise ValueError("unknown trusted role")
        if self.actor_id is not None and (not isinstance(self.actor_id, str) or not self.actor_id.strip()):
            raise ValueError("actor_id must be a nonempty trusted identity")


class Response(TypedDict):
    request_id: str
    department: str
    result: Any
    sources: list[str]
    missing_information: list[str]
    proposed_action: Any
    action_status: str


def now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
