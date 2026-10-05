"""Capture real local inference and restart/reviewer evidence in a fresh directory."""

import argparse
from datetime import datetime, UTC
import http.client
import html
import json
from pathlib import Path
import platform
import tempfile
import time

from .domain import Request
from .model import DEFAULT_MODEL, LocalModel, Model, interpret
from .service import decide_proposal, get_history, get_outcome, inspect_proposal, submit_request
from .store import Store


class MeasuredModel(LocalModel):
    def __init__(self, model: str):
        super().__init__(model)
        self.calls: list[dict] = []

    def generate(self, prompt: str) -> str:
        start = time.perf_counter()
        try:
            return super().generate(prompt)
        finally:
            self.calls.append({"task": prompt.split(" ", 1)[0], "seconds": round(time.perf_counter() - start, 4)})


def local_metadata(model: str) -> dict:
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=5)
    try:
        connection.request("POST", "/api/show", json.dumps({"model": model}), {"Content-Type": "application/json"})
        reply = connection.getresponse()
        if reply.status != 200:
            return {"model": model, "metadata_status": f"HTTP {reply.status}"}
        metadata = json.loads(reply.read(1_048_576))
        return {"model": model, "details": metadata.get("details"), "model_info": metadata.get("model_info"),
                "license_name": metadata.get("license", "Unknown").splitlines()[0]}
    except (OSError, ValueError, http.client.HTTPException) as error:
        return {"model": model, "metadata_status": type(error).__name__}
    finally:
        connection.close()


def acceptance_checks(store: Store, model: Model) -> list[dict]:
    """Save explicit assertions for rejection, edited hashes, outages and terminal failures."""
    checks = []
    for scenario in ("rejected", "edited_hash", "always_fail", "repeat_request"):
        request = Request(f"acceptance-{scenario}", "customer_service", "draft a ticket for S01", "demo-customer_service")
        response = submit_request(request, store, model)
        proposal = response["proposed_action"]
        if response["action_status"] != "pending_approval" or not proposal:
            raise ValueError(f"Cannot demonstrate {scenario}: real drafting failed.")
        error = None
        if scenario == "rejected":
            decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "reject", store, actor_id="demo-reviewer")
        elif scenario == "edited_hash":
            try:
                decide_proposal(proposal["proposal_id"], "0" * 64, "ops_reviewer", "approve", store, actor_id="demo-reviewer")
            except ValueError as caught:
                error = str(caught)
            if not error:
                raise ValueError("Edited approval hash was accepted.")
        elif scenario == "always_fail":
            decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", store, "always_fail", "demo-reviewer")
        else:
            repeated = submit_request(request, store, model)
            if repeated != response or len(store.request_proposals(request.request_id)) != 1:
                raise ValueError("Repeated request did not retain exactly one proposal.")
        outcome = get_outcome(proposal["proposal_id"], "ops_reviewer", store)
        expected = "adapter_failure" if scenario == "always_fail" else "not_executed"
        action_count = store.db.execute("SELECT COUNT(*) FROM mock_actions WHERE proposal_id=?", (proposal["proposal_id"],)).fetchone()[0]
        if outcome["outcome"] != expected or outcome["action"] is not None or action_count != 0:
            raise ValueError(f"Unexpected action or outcome for {scenario}.")
        checks.append({"scenario": scenario, "passed": True, "error": error,
                       "inspection": inspect_proposal(proposal["proposal_id"], "ops_reviewer", store),
                       "outcome": outcome, "stored_action_count": action_count,
                       "mode": "simulated local adapter failure" if scenario == "always_fail" else "real draft, controlled reviewer operation"})
    # Port zero cannot serve Ollama. This exercises a real transport failure without stopping the user's model.
    unavailable = submit_request(Request("acceptance-model-unavailable", "customer_service", "draft a ticket for S01"), store, LocalModel("unavailable", port=0, timeout=1))
    if unavailable["action_status"] != "model_unavailable" or unavailable["proposed_action"] is not None or store.request_proposals(unavailable["request_id"]):
        raise ValueError("Model outage produced a proposal or false success.")
    checks.append({"scenario": "model_unavailable", "passed": True, "mode": "deliberate unavailable local endpoint, not a real model generation", "response": unavailable})
    with tempfile.TemporaryDirectory() as directory:
        missing = submit_request(Request("acceptance-missing-source", "marketing", "summarize Prime lead performance"), store, model, Path(directory))
    if missing["action_status"] != "source_unavailable" or missing["proposed_action"] is not None:
        raise ValueError("Missing source produced an action or fabricated data.")
    checks.append({"scenario": "missing_source", "passed": True, "mode": "real interpretation, deliberately empty fixture directory", "response": missing})
    return checks


def routing_checks(model: Model) -> list[dict]:
    """Real-model regressions. Test questions are not production routing rules."""
    checks = []
    for text, expected in (("how many leads", "marketing"),
                           ("how many duplicates leads", "marketing"),
                           ("Can you deal with this problem?", None)):
        result = interpret(model, text)
        if result["department"] != expected:
            raise ValueError(f"Routing regression: {text!r} expected {expected}, received {result}.")
        checks.append({"request": text, "expected_department": expected, "interpretation": result, "passed": True})
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--offline-attested", action="store_true", help="Record the operator's statement that outbound internet is disconnected; this runner does not alter or verify network settings.")
    parser.add_argument("--output", type=Path, default=Path("artifacts") / datetime.now(UTC).strftime("demo-%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if args.model == "template":
        parser.error("This evidence runner requires real local inference, not template mode.")
    args.output.mkdir(parents=True, exist_ok=False)
    model = MeasuredModel(args.model)
    store = Store(args.output / "demo.sqlite3")
    cases = [
        ("marketing", "summarize Prime lead performance"),
        ("customer_service", "draft a ticket for S01"),
        ("customer_service", "answer S02 in Arabic"),
        ("customer_service", "draft a ticket for S03"),
        ("customer_service", "process S04"),
        ("product", "prioritize the product feedback"),
        ("tech", "triage the intake failures"),
        ("marketing", "show HR01 salary"),
        ("marketing", "publish a fractional ownership campaign"),
        ("tech", "draft a ticket for S01"),
        ("marketing", "what is conversion to investment"),
        ("marketing", "Please handle this issue"),
    ]
    records: list[dict] = []
    try:
        routing = routing_checks(model)
        (args.output / "routing.json").write_text(json.dumps(routing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"routing regressions: {len(routing)} passed", flush=True)
        for index, (role, text) in enumerate(cases):
            start = time.perf_counter()
            call_start = len(model.calls)
            result = submit_request(Request(f"demo-{index}", role, text, f"demo-{role}"), store, model)
            expected = ["complete", "pending_approval", "pending_approval", "needs_information", "blocked", "draft", "pending_approval", "denied", "blocked", "denied", "complete", "needs_clarification"][index]
            if result["action_status"] != expected:
                raise ValueError(f"Case {index} expected {expected}, received {result['action_status']}. Partial outputs are not passing evidence.")
            record = {"role": role, "request": text, "total_seconds": round(time.perf_counter() - start, 4),
                      "model_calls": model.calls[call_start:], "response": result}
            records.append(record)
            (args.output / f"case-{index:02d}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            (args.output / f"case-{index:02d}.html").write_text("<!doctype html><meta charset='utf-8'><style>body{font:16px system-ui;margin:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px monospace}</style><h1>" + html.escape(role) + "</h1><p>Real local inference, mock actions only. " + html.escape(result["action_status"]) + "</p><pre>" + html.escape(json.dumps(record, ensure_ascii=False, indent=2)) + "</pre>", encoding="utf-8")
            print(f"case {index:02d}: {role} -> {result['action_status']} ({record['total_seconds']}s)", flush=True)
        proposals = [record["response"]["proposed_action"] for record in records if record["response"]["proposed_action"]]
        decisions = []
        for index, proposal in enumerate(proposals):
            inspection = inspect_proposal(proposal["proposal_id"], "ops_reviewer", store)
            mode = "fail_once" if index == 0 else "uncertain_once" if index == 1 else "normal"
            first = decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", store, mode, "demo-reviewer")
            store.close()
            store = Store(args.output / "demo.sqlite3")
            repeated = decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", store, mode, "demo-reviewer")
            if repeated["outcome"] != "succeeded" or not repeated["action"] or repeated["action"]["payload_hash"] != proposal["payload_hash"]:
                raise ValueError("Restart did not preserve verified execution.")
            repeated_again = decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", store, mode, "demo-reviewer")
            if repeated_again != repeated or store.db.execute("SELECT COUNT(*) FROM mock_actions WHERE proposal_id=?", (proposal["proposal_id"],)).fetchone()[0] != 1:
                raise ValueError("Repeated approval changed the action or created duplicates.")
            decisions.append({"inspection": inspection, "first": first, "after_restart": repeated})
        acceptance = acceptance_checks(store, model)
        bundle: dict = {"created_at": datetime.now(UTC).isoformat(), "python": platform.python_version(), "platform": platform.platform(),
                  "model_metadata": local_metadata(args.model), "offline_verification": "operator-attested disconnected; not independently verified" if args.offline_attested else "pending: outbound internet was not disabled by this runner",
                  "scope": "Real local inference, fictional fixtures, local mock actions only. Narrative quality needs human review.",
                  "routing_checks": routing, "cases": records, "decisions": decisions, "acceptance_checks": acceptance, "history": get_history("ops_reviewer", store, "demo-reviewer")}
        (args.output / "acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "evidence.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        rows = "".join(f"<tr><td>{index}</td><td>{record['role']}</td><td>{record['response']['action_status']}</td><td>{record['total_seconds']}</td></tr>" for index, record in enumerate(records))
        (args.output / "report.html").write_text("<!doctype html><meta charset='utf-8'><title>HissaTech real local demo</title><h1>HissaTech real local demo</h1><p>" + html.escape(bundle["offline_verification"]) + ". Mock actions only.</p><table><tr><th>Case</th><th>Role</th><th>Status</th><th>Seconds</th></tr>" + rows + "</table><h2>Saved outputs</h2><pre>" + html.escape(json.dumps(bundle, ensure_ascii=False, indent=2)) + "</pre>", encoding="utf-8")
        print(f"Evidence: {args.output.resolve()}", flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
