"""Trusted demo identity and CLI presentation."""

from __future__ import annotations

import argparse
import json
import uuid

from .domain import ROOT, ROLES, Request
from .model import DEFAULT_MODEL, LocalModel
from .service import decide_proposal, get_history, get_outcome, inspect_proposal, submit_request
from .store import Store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HissaTech local assessment prototype")
    parser.add_argument("--db", default=str(ROOT / "hissatech.sqlite3"))
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Installed Ollama model name")
    sub = parser.add_subparsers(dest="command", required=True)
    request = sub.add_parser("request")
    request.add_argument("--role", required=True, choices=sorted(ROLES))
    request.add_argument("--actor-id", default=None)
    request.add_argument("--text", required=True)
    request.add_argument("--request-id", default=None)
    approve = sub.add_parser("approve")
    approve.add_argument("--role", required=True)
    approve.add_argument("--actor-id", default=None)
    approve.add_argument("--proposal-id", required=True)
    approve.add_argument("--payload-hash", required=True)
    approve.add_argument("--adapter-mode", choices=["normal", "fail_once", "always_fail", "uncertain_once"], default="normal")
    reject = sub.add_parser("reject")
    reject.add_argument("--role", required=True)
    reject.add_argument("--actor-id", default=None)
    reject.add_argument("--proposal-id", required=True)
    reject.add_argument("--payload-hash", required=True)
    for command in ("inspect", "outcome"):
        read = sub.add_parser(command)
        read.add_argument("--role", required=True)
        read.add_argument("--proposal-id", required=True)
    history = sub.add_parser("history")
    history.add_argument("--role", required=True)
    history.add_argument("--actor-id", default=None)
    args = parser.parse_args(argv)
    if args.model == "template":
        parser.error("Template responses are not available. Use an installed Ollama model.")
    store = Store(args.db)
    result: object
    try:
        if args.command == "request":
            model = LocalModel(args.model)
            result = submit_request(Request(args.request_id or str(uuid.uuid4()), args.role, args.text, args.actor_id), store, model)
        elif args.command == "approve":
            result = decide_proposal(args.proposal_id, args.payload_hash, args.role, "approve", store, args.adapter_mode, args.actor_id)
        elif args.command == "reject":
            result = decide_proposal(args.proposal_id, args.payload_hash, args.role, "reject", store, actor_id=args.actor_id)
        elif args.command == "inspect":
            result = inspect_proposal(args.proposal_id, args.role, store)
        elif args.command == "outcome":
            result = get_outcome(args.proposal_id, args.role, store)
        else:
            result = get_history(args.role, store, args.actor_id)
    except (ValueError, PermissionError) as error:
        result = {"error": str(error)}
    finally:
        store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
