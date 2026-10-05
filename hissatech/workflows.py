"""Department workflows using allowed fixtures and local inference."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from .domain import Response
from .model import Model, ModelOutputInvalid, grounded_draft
from .policies import RestrictedAccess, UnsafeContent, check_content, normalized
from .sources import Sources
from .store import Store


def response(request_id: str, department: str, result: Any, sources: list[str], missing: list[str], action: Any = None, status: str = "complete") -> Response:
    return {"request_id": request_id, "department": department, "result": result, "sources": sources,
            "missing_information": missing, "proposed_action": action, "action_status": status}


def marketing(request_id: str, model: Model, sources: Sources) -> Response:
    aggregate = sources.read("lead_aggregate")
    source_ids = aggregate.pop("source_ids")
    policies = {key: value for key, value in sources.read("policies").items() if key in {"P01", "P03"}}
    missing = ["No sale or investment conversion data is available."]
    for source, metrics in aggregate["by_source"].items():
        if metrics["spend_sar"] is None:
            missing.append(f"{source} spend is unknown, not zero.")
    if aggregate["missing_source_count"]:
        missing.append(f"{aggregate['missing_source_count']} unique lead(s) have an unknown source.")
    if aggregate["missing_budget_count"]:
        missing.append(f"{aggregate['missing_budget_count']} unique lead(s) have unknown budgets.")
    if aggregate["duplicate_conflicts"]:
        missing.append("Reconcile duplicate conflicts before treating provisional metrics as final.")
    if not aggregate["unique_leads"]:
        missing.append("No lead data is available; rates and acquisition costs have no denominator.")
    recommendations = [
        "Review Qualified leads for follow-up through approved channels; this analysis contacts nobody." if aggregate["qualified_leads"] else "Review lead qualification before choosing follow-up targets; no Qualified leads are recorded.",
        "Reconcile duplicate conflicts before allocating spend." if aggregate["duplicate_conflicts"] else
        "Complete unknown source, budget, and spend data before reallocating spend." if len(missing) > 1 else
        "Collect sale and investment outcomes before evaluating conversion; qualification is not a sale.",
    ]
    draft = grounded_draft(model, "a short English management summary of LEAD METRICS: give unique and qualified counts, qualification rate and unknowns. Source names are only the by_source keys, never policy or row IDs. Currency is SAR. NEVER use dollar signs or USD. null spend or cost is UNKNOWN, never zero or free. Do not replace the metrics with a restatement of policies", {"aggregates": aggregate, "missing_information": missing, "recommendations": recommendations, "policies": policies}, ["P01", "P03", *source_ids])
    if "$" in draft["text"] or re.search(r"\bUSD\b", draft["text"], re.I):
        raise ModelOutputInvalid("Lead spend is in SAR, not dollars.")
    for source, metrics in aggregate["by_source"].items():
        if metrics["spend_sar"] is None:
            for clause in re.split(r"(?<=[.!?])\s+|[;\n]", normalized(draft["text"])):
                clause = re.sub(r"\bnot\s+(?:zero|free)\b", "", clause)
                if source.casefold() in clause and re.search(r"(?:cost|spend)", clause) and re.search(r"\$\s*0\b|\bsar\s*0\b|\b(?:zero|free)\b|\b0\s+(?:cost|spend)\b|\b(?:cost|spend)\s*(?:is|:|=)?\s*0\b", clause):
                    raise ModelOutputInvalid("Unknown source spend cannot be described as zero or free.")
    return response(request_id, "marketing", {**aggregate, "management_summary": draft["text"], "draft_source_ids": draft["source_ids"],
                    "recommendations": recommendations,
                    "recommendation_source_ids": [["P03", *source_ids], ["P01", *source_ids]]},
                    ["P01", "P02", "P03", *source_ids], missing)


def support(request_id: str, text: str, model: Model, store: Store, sources: Sources, owner: str | None = None) -> Response:
    message = None
    if text.lstrip().startswith("{"):
        try:
            supplied = json.loads(text)
        except ValueError:
            supplied = None
        if not isinstance(supplied, dict) or set(supplied) - {"message", "customer_id", "language"} or not isinstance(supplied.get("message"), str) or not supplied["message"].strip():
            return response(request_id, "customer_service", "Supply JSON with message, optional customer_id, and language en or ar.", ["P02"], ["valid customer message"], status="needs_clarification")
        language = supplied.get("language", "ar" if re.search(r"[\u0621-\u064a]", supplied["message"]) else "en")
        identity = supplied.get("customer_id")
        if not isinstance(language, str) or language not in {"en", "ar"} or (identity is not None and (not isinstance(identity, str) or not identity.strip())):
            return response(request_id, "customer_service", "Use language en or ar and a nonempty customer_id, or omit unknown identity.", ["P02"], ["valid message metadata"], status="needs_clarification")
        message = {"id": f"REQUEST:{request_id}", "text": supplied["message"], "customer_id": identity, "language": language}
    else:
        messages = sources.read("support_messages")
        references = set(re.findall(r"\bS\d+\b", normalized(text).upper()))
        message = next((item for item in messages if item["id"] in references), None) if len(references) == 1 else None
    if not message:
        return response(request_id, "customer_service", "Please provide a support message ID or the customer message.", ["P02"], ["source message"], status="needs_clarification")
    try:
        check_content(message["text"])
    except (RestrictedAccess, UnsafeContent):
        return response(request_id, "customer_service", "The source contains restricted content or untrusted instructions. No authority or action changed.", [message["id"], "P03"], [], status="blocked")
    classification, priority, rationale = support_priority(message["text"])
    if not message["customer_id"]:
        question = "يرجى تقديم معرّف العميل لتحديد الحساب، دون تخمين هويتك." if message["language"] == "ar" else "Please provide the customer ID needed to locate the account. No identity was invented."
        return response(request_id, "customer_service", {"clarification": question, "classification": classification, "priority": priority, "priority_rationale": rationale}, [message["id"], "P02"], ["customer identity"], status="needs_information")
    language = "Arabic" if message["language"] == "ar" else "English"
    policy = sources.read("policies")["P02"]
    relevant_policy = " ".join(sentence for sentence in re.split(r"(?<=\.)\s+", policy) if "Draft acknowledgments" in sentence or "No refund" in sentence or ("credible report" in sentence if priority == "High" else "Ordinary access" in sentence))
    draft = grounded_draft(model, "a concise customer acknowledgement. Acknowledge ONLY what the customer reported; never assert we checked records, verified payment, or located their account. No work has started. Do not say we are investigating, reviewing or solving the problem. Do not promise an update time or resolution", {"message": message["text"], "classification": classification, "evidence_limit": "Customer self-report only. No account or payment verification was performed.", "policies": {"P02": relevant_policy}}, [message["id"], "P02"], language)
    if re.search(r"we are (?:currently )?(?:working|investigating|reviewing|solving)|نعمل (?:حاليا|حاليًا)|نقوم (?:حاليا |حاليًا )?(?:بمراجعة|بحل|بالتحقيق)", draft["text"], re.I):
        raise ModelOutputInvalid("A pending draft cannot claim investigation has started.")
    payload = {"message_id": message["id"], "message_text": message["text"], "customer_id": message["customer_id"], "language": message["language"], "classification": classification, "priority": priority, "priority_rationale": rationale, "draft": draft["text"], "source_ids": [message["id"], "P02"], "draft_source_ids": draft["source_ids"]}
    proposal = store.propose(request_id, "desk_ticket", payload, owner)
    return response(request_id, "customer_service", {"classification": classification, "priority": priority, "priority_rationale": rationale, "draft_response": draft["text"], "draft_source_ids": draft["source_ids"]}, [message["id"], "P02"], [], {**proposal, "action_type": "desk_ticket", "payload": payload}, "pending_approval")


def support_priority(text: str) -> tuple[str, str, str]:
    value = normalized(text)
    # ponytail: conservative bilingual phrase rules. Extend from observed messages, not model-selected urgency.
    payment = bool(re.search(r"payment|paid|دفع|دفعت|سداد", value))
    success = bool(re.search(r"success(?:ful|fully)?|succeeded|\bpaid\b|بنجاح|نجح", value)) and not bool(re.search(r"(?:not|never|haven't|hasn't|didn't).{0,25}(?:paid|success|succeed)|unsuccessful|failed|declined|فشل|لم ينجح|لم.{0,10}(?:أدفع|ادفع|الدفع|دفع)", value))
    missing = bool(re.search(r"confirmation.{0,15}(?:missing|absent|not (?:visible|received|shown|available))|(?:cannot|can't).{0,15}(?:see|find).{0,15}confirmation|(?:no|missing) confirmation|(?:not|never).{0,10}received.{0,10}confirmation|(?:لم|لا).{0,25}(?:تأكيد|التأكيد)|(?:تأكيد|التأكيد).{0,25}(?:مفقود|لم يظهر|غير موجود)", value))
    if re.search(r"confirmation.{0,15}not missing|(?:تأكيد|التأكيد).{0,15}(?:ليس مفقود|غير مفقود)", value):
        missing = False
    if payment and success and missing:
        return "payment confirmation missing", "High", "P02: reported successful payment with missing confirmation requires human investigation."
    if re.search(r"log.?in|sign.?in|access|دخول|الدخول", value):
        return "access request", "Normal", "P02: ordinary account-access requests are Normal priority."
    return "payment inquiry" if payment else "information request", "Normal", "P02: no evidenced successful-payment/missing-confirmation report; ordinary enquiries are Normal."


def product(request_id: str, model: Model, sources: Sources) -> Response:
    definitions = [
        ("fractional ownership research", ("fractional", "resale", "الملكية الجزئية"), "Investigate fractional resale feedback internally.", "Research records constraints and open questions without a release, transaction, or regulatory approval claim.", "Low", "P01 permits internal research only; commercial execution remains paused."),
        ("payment confirmation", ("payment", "confirmed", "دفع", "تأكيد"), "Investigate reported payment-confirmation uncertainty.", "Given a successful test payment, its confirmation state is visible; a missing state shows an investigation path.", "High", "P02 prioritizes credible successful-payment reports with missing confirmation, not feedback frequency."),
        ("login recovery", ("login", "recovery", "دخول"), "Investigate reported account-recovery friction.", "Given a test account, a user completes the documented recovery flow and signs in without unexplained steps.", "Normal", "Account-access friction affects usability; incident severity is not established by feedback count."),
        ("mobile lead form", ("mobile", "lead form", "جوال"), "Investigate reported mobile lead-form friction.", "At a 360-pixel viewport, required fields and validation remain visible and a valid test submission completes.", "Normal", "Mobile intake usability needs investigation; frequency alone does not establish incident severity."),
    ]
    feedback = sources.read("feedback")
    dependencies = {
        "fractional ownership research": ["Review P01 constraints before internal research; commercial execution remains paused.", "Investigate resale feasibility and unresolved regulatory questions; no approval or release is confirmed."],
        "payment confirmation": ["Reproduce reported confirmation gaps with authorized test-payment records.", "Inspect the payment-to-confirmation flow; backend behavior and ownership are unknown."],
        "login recovery": ["Document the existing recovery flow using authorized test accounts.", "Review authentication behavior and account-recovery requirements with the responsible team."],
        "mobile lead form": ["Reproduce the reported friction at a 360-pixel viewport.", "Inspect form validation and submission behavior using test data before choosing changes."],
    }
    for item in feedback:
        check_content(item["text"])
    themes: list[dict[str, Any]] = []
    assigned: set[str] = set()
    # ponytail: known bilingual themes, explicitly retain novel feedback for review instead of inventing a category.
    for name, terms, problem, criteria, priority, rationale in definitions:
        evidence = [item for item in feedback if item["id"] not in assigned and any(term in normalized(item["text"]) for term in terms)]
        evidence_ids = [item["id"] for item in evidence]
        if evidence_ids:
            assigned.update(evidence_ids)
            if name == "payment confirmation" and not any(support_priority(item["text"])[1] == "High" for item in evidence):
                priority, rationale = "Normal", "P02 urgency is not established: verify payment success and missing confirmation before escalation."
            themes.append({"theme": name, "evidence_ids": evidence_ids, "record_count": len(evidence_ids),
                           "problem_statement": problem, "acceptance_criteria": criteria, "priority": priority, "priority_rationale": rationale,
                           "implementation_dependencies": dependencies[name],
                           "dependency_status": "Investigation prerequisites, not verified implementation facts; owners, feasibility, approvals and dates are unknown."})
    themes.sort(key=lambda item: ({"High": 0, "Normal": 1, "Low": 2}[item["priority"]], -item["record_count"], item["theme"]))
    unclassified = [item["id"] for item in feedback if item["id"] not in assigned]
    evidence_sources = ["P01", "P02", "P03", *[item["id"] for item in feedback]]
    missing = ["Incident severity is not established by feedback frequency."]
    if unclassified:
        missing.append("Unclassified feedback needs human theme review: " + ", ".join(unclassified))
    if len(themes) < 3:
        missing.append("Fewer than three evidenced themes exist; no additional backlog items were invented.")
    draft = grounded_draft(model, "a short summary of the provided backlog themes in their given order. Keep their priorities unchanged, mention theme names and evidence IDs. Do not replace themes with policy headings", {"themes": themes[:3], "unclassified_feedback_ids": unclassified, "policies": {key: value for key, value in sources.read("policies").items() if key in {"P01", "P02"}}}, evidence_sources)
    return response(request_id, "product", {"themes": themes, "unclassified_feedback_ids": unclassified, "top_three_backlog_items": themes[:3], "priority_rationale": draft["text"], "draft_source_ids": draft["source_ids"]}, evidence_sources, missing, status="draft")


def tech(request_id: str, model: Model, store: Store, sources: Sources, owner: str | None = None) -> Response:
    incidents = sources.read("incidents")
    if not incidents:
        return response(request_id, "tech", "Provide incident logs before triage; severity and recovery are unknown.", ["P02"], ["incident logs"], status="needs_information")
    facts = [f"{item['id']}: {item['service']} reported {item['event']} for {item['request_id']}" for item in incidents]
    for fact in facts:
        check_content(fact)
    errors = [item for item in incidents if item["service"] == "lead_intake" and re.fullmatch(r"HTTP 5\d\d", item["event"])]
    timeouts = [item for item in incidents if "timeout" in normalized(item["event"])]
    repeated = len(errors) >= 2
    severity = "High" if repeated else "Normal"
    rationale = "P02: repeated lead-intake server errors require High priority." if repeated else "P02 repeated-error threshold is not evidenced. Normal provisional triage; broader impact is unknown."
    correlated = [item for item in timeouts if any(item["request_id"] == error["request_id"] for error in errors)]
    hypotheses = ["A timeout on the same request may be related; shared request IDs do not prove causation."] if correlated else ["The supplied logs do not establish a dependency failure or root cause."]
    successes = [item for item in incidents if item["service"] == "lead_intake" and re.fullmatch(r"HTTP 2\d\d", item["event"]) and errors and datetime.fromisoformat(item["timestamp"]) > max(datetime.fromisoformat(error["timestamp"]) for error in errors)]
    recovery = "A later successful request does not prove complete recovery: " + ", ".join(item["id"] for item in successes) if successes else "Complete recovery is unknown; no later successful lead-intake request is evidenced."
    request_ids = list(dict.fromkeys(item["request_id"] for item in errors))
    next_step = "Correlate traces for " + ", ".join(request_ids) + " with dependency logs; reproduce a failing request and compare a successful request." if errors else "Inspect the supplied service traces and establish customer impact before claiming an incident cause."
    evidence_sources = [item["id"] for item in incidents] + ["P02"]
    draft = grounded_draft(model, "a short internal diagnostic note. Distinguish HTTP server errors from dependency timeouts, facts from hypotheses. Preserve the provided severity, uncertainty and recovery assessment", {"observations": facts, "severity": severity, "severity_rationale": rationale, "hypotheses": hypotheses, "recovery_assessment": recovery, "next_step": next_step, "policies": {"P02": sources.read("policies")["P02"]}}, evidence_sources)
    payload: dict[str, Any] = {"severity": severity, "severity_rationale": rationale, "title": "Investigate evidenced service failures", "source_ids": evidence_sources, "next_step": next_step, "observed_facts": facts, "hypotheses": hypotheses, "recovery_assessment": recovery, "draft_note": draft["text"], "draft_source_ids": draft["source_ids"]}
    proposal = store.propose(request_id, "incident_task", payload, owner)
    return response(request_id, "tech", {"severity": severity, "severity_rationale": rationale, "observed_facts": facts, "hypotheses": hypotheses, "recovery_assessment": recovery, "next_diagnostic_step": next_step, "draft_note": draft["text"], "draft_source_ids": draft["source_ids"]}, evidence_sources, ["Root cause and complete recovery are unknown."], {**proposal, "action_type": "incident_task", "payload": payload}, "pending_approval")
