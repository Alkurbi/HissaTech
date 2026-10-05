"""Interface-independent request orchestration."""

from __future__ import annotations

from pathlib import Path
import uuid

from .domain import ROLES, WORKFLOW_ROLES, Request, Response, digest
from .model import Model, ModelOutputInvalid, ModelUnavailable, interpret
from .store import RequestOwnershipLost, Store
from .policies import RestrictedAccess, UnsafeContent, check_request_scope
from .sources import Sources, SourceUnavailable
from .workflows import marketing, product, response, support, tech


def handle_request(store: Store, role: str, text: str, request_id: str, model: Model, data_directory: Path | None = None, actor_id: str | None = None) -> Response:
    if role not in ROLES:
        raise ValueError("unknown trusted role")
    actor_id = trusted_actor(role, actor_id)
    fingerprint = digest({"role": role, "text": text, "actor_id": actor_id})
    cached = store.cached_request(request_id, fingerprint)
    if cached:
        return cached
    owner = str(uuid.uuid4())
    if not store.start_request(request_id, role, fingerprint, actor_id, owner):
        return store.cached_request(request_id, fingerprint) or response(request_id, "unrouted", "This request is already processing. Retry the same request ID; no duplicate action was started.", [], ["completed request"], status="processing")
    recovered = store.request_proposals(request_id)
    if recovered:
        proposal = recovered[-1]
        recovered_route = "customer_service" if proposal["action_type"] == "desk_ticket" else "tech"
        result = response(request_id, recovered_route, {"recovered_persisted_proposal": True, "payload": proposal["payload"]}, proposal["payload"].get("source_ids", []), [], proposal, "pending_approval" if proposal["status"] == "pending" else proposal["status"])
        store.save_request(result, role, fingerprint, owner)
        return result
    try:
        check_request_scope(role, text)
    except RestrictedAccess as error:
        result = response(request_id, "restricted", str(error), ["P03"], [], status="denied")
    except UnsafeContent as error:
        result = response(request_id, "unrouted", str(error), ["P01", "P03"], [], status="blocked")
    else:
        try:
            interpretation = interpret(model, text)
            route = interpretation["department"]
        except ModelUnavailable as error:
            result = response(request_id, "unrouted", str(error), [], ["local model"], status="model_unavailable")
        except ModelOutputInvalid as error:
            result = response(request_id, "unrouted", str(error), [], ["valid model interpretation"], status="model_invalid_output")
        except RestrictedAccess as error:
            result = response(request_id, "restricted", str(error), ["P03"], [], status="denied")
        except UnsafeContent as error:
            result = response(request_id, "unrouted", str(error), ["P01", "P03"], [], status="blocked")
        else:
            if not route:
                result = response(request_id, "unrouted", interpretation["clarification"], [], ["department"], status="needs_clarification")
            elif role not in {WORKFLOW_ROLES[route], "ops_reviewer"}:
                result = response(request_id, route, "Access denied for this trusted role.", ["P03"], [], status="denied")
            else:
                try:
                    sources = Sources(role) if data_directory is None else Sources(role, data_directory)
                    if route == "marketing":
                        result = marketing(request_id, model, sources)
                    elif route == "customer_service":
                        result = support(request_id, text, model, store, sources, owner)
                    elif route == "product":
                        result = product(request_id, model, sources)
                    else:
                        result = tech(request_id, model, store, sources, owner)
                except RequestOwnershipLost:
                    return response(request_id, route, "Another worker owns this request. Retry its stable ID; this worker created no proposal.", [], ["current request outcome"], status="processing")
                except RestrictedAccess as error:
                    result = response(request_id, route, str(error), ["P03"], [], status="denied")
                except UnsafeContent as error:
                    result = response(request_id, route, str(error), ["P01", "P03"], [], status="blocked")
                except ModelUnavailable as error:
                    result = response(request_id, route, str(error), [], ["local model"], status="model_unavailable")
                except ModelOutputInvalid as error:
                    result = response(request_id, route, str(error), [], ["valid grounded model output"], status="model_invalid_output")
                except SourceUnavailable as error:
                    result = response(request_id, route, str(error), [], ["authorized local source"], status="source_unavailable")
    store.save_request(result, role, fingerprint, owner)
    return result


def submit_request(request: Request, store: Store, model: Model, data_directory: Path | None = None) -> Response:
    """Submit a request through the boundary shared by all interfaces."""
    return handle_request(store, request.role, request.text, request.request_id, model, data_directory, request.actor_id)


def trusted_actor(role: str, actor_id: str | None = None) -> str:
    if role not in ROLES or actor_id is not None and (not isinstance(actor_id, str) or not actor_id.strip()):
        raise ValueError("Invalid trusted identity or role.")
    return actor_id or f"{role}-test"


def inspect_proposal(proposal_id: str, role: str, store: Store) -> dict:
    trusted_actor(role)
    if role != "ops_reviewer":
        raise PermissionError("Only Ops Reviewer may inspect full action proposals.")
    return store.inspect(proposal_id)


def decide_proposal(proposal_id: str, payload_hash: str, role: str, decision: str, store: Store, mode: str = "normal", actor_id: str | None = None) -> dict:
    actor_id = trusted_actor(role, actor_id)
    if decision == "approve":
        return store.approve_and_execute(proposal_id, payload_hash, role, mode, actor_id)
    if decision == "reject":
        store.reject(proposal_id, payload_hash, role, actor_id)
        return {"proposal_id": proposal_id, "outcome": "rejected_no_action_created"}
    raise ValueError("Decision must be approve or reject.")


def get_outcome(proposal_id: str, role: str, store: Store) -> dict:
    proposal = inspect_proposal(proposal_id, role, store)
    result = store.execution_result(proposal_id)
    if result["outcome"] == "succeeded" and (not result["action"] or digest(result["action"]["payload"]) != proposal["payload_hash"]):
        raise ValueError("The recorded action outcome cannot be verified.")
    return result


def get_history(role: str, store: Store, actor_id: str | None = None) -> list[dict]:
    return store.history(role, trusted_actor(role, actor_id))


def get_request_result(request_id: str, role: str, store: Store, actor_id: str | None = None) -> Response | None:
    return store.request_response(request_id, role, trusted_actor(role, actor_id))
