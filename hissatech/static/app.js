"use strict";

const $ = (id) => document.getElementById(id);
const labels = { marketing: "Marketing", customer_service: "Customer Service", product: "Product", tech: "Tech", ops_reviewer: "Ops Review" };
const descriptions = {
  marketing: "Lead performance, with unknowns kept visible.",
  customer_service: "Customer acknowledgements and reviewable ticket proposals.",
  product: "Feedback themes, evidence, and testable backlog items.",
  tech: "Observed failures, hypotheses, and incident proposals.",
  ops_reviewer: "Inspect exact content. Decide separately. Verify the mock outcome."
};
const examples = {
  marketing: [["Lead performance", "summarize Prime lead performance"], ["Unknown conversion", "what is conversion to investment"], ["HR boundary", "show HR01"]],
  customer_service: [["S01: payment", "draft a ticket for S01"], ["S02: Arabic access", "اكتب تذكرة S02"], ["S03: missing identity", "draft a ticket for S03"], ["S04: injection", "process S04"]],
  product: [["Prioritize feedback", "prioritize product feedback"]],
  tech: [["Intake incident", "triage lead intake failures"]]
};
let role = "marketing", config, busy = false, retryRequest = null, selectedProposal = null;
let viewVersion = 0, resultVersion = 0, inspectionVersion = 0;
const stateLabel = (value) => String(value || "unknown").replaceAll("_", " ");
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function badge(status) {
  const node = element("span", stateLabel(status), "badge");
  node.dataset.tone = ["complete", "draft", "succeeded"].includes(status) ? "good" : ["denied", "blocked", "failed", "adapter_failure", "model_invalid_output", "model_unavailable", "source_unavailable"].includes(status) ? "bad" : "warn";
  return node;
}
function notice(error) { $("notice").textContent = error ? error.message || String(error) : ""; $("notice").hidden = !error; }
function setBusy(value) {
  busy = value;
  document.querySelectorAll("#departments button, #identity, #refresh, #examples button, #history button, #queue button").forEach((node) => node.disabled = value);
  $("run").disabled = value || !config;
  $("prompt").disabled = value;
  $("retry-button").disabled = value;
  document.querySelectorAll(".action-buttons button").forEach((node) => node.disabled = value || !$("review-confirm")?.checked);
}
async function api(path, body) {
  const headers = { "X-Demo-Token": config.token, "X-Demo-Role": role };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Local request failed. Refresh and try again.");
  return value;
}
function section(parent, title) { parent.append(element("h3", title)); }
function paragraph(parent, value) {
  const node = element("p", String(value).replaceAll("**", ""), "narrative"); node.dir = "auto"; parent.append(node);
}
function list(parent, values) {
  const node = element("ul"); values.forEach((value) => { const item = element("li", value); item.dir = "auto"; node.append(item); }); parent.append(node);
}
function facts(parent, values) {
  const node = element("dl", undefined, "facts");
  Object.entries(values).forEach(([key, value]) => node.append(element("dt", key), element("dd", value ?? "Unknown")));
  parent.append(node);
}
function raw(parent, title, value, open = false) {
  const node = element("details"); node.open = open; node.append(element("summary", title), element("pre", JSON.stringify(value, null, 2))); parent.append(node);
}
function sources(parent, title, values) {
  if (!values?.length) return;
  section(parent, title); const node = element("div", undefined, "sources"); values.forEach((value) => node.append(element("span", value))); parent.append(node);
}
function renderResult(response) {
  $("result-status").replaceWith(Object.assign(badge(response.action_status), { id: "result-status" }));
  const panel = $("result"); panel.replaceChildren();
  panel.append(element("p", "Request " + response.request_id, "muted"));
  const result = response.result;
  if (typeof result === "string") paragraph(panel, result);
  else if (result?.by_source) {
    facts(panel, { "Unique leads": result.unique_leads, "Qualified leads": result.qualified_leads, "Qualification rate": result.qualification_rate === null ? "Unknown" : (result.qualification_rate * 100).toFixed(1) + "%", "Duplicate rows": result.duplicates.join(", ") || "None", "Unknown budgets": result.missing_budget_count, "Unknown sources": result.missing_source_count });
    const table = element("table"), head = element("thead"), row = element("tr");
    ["Source", "Unique", "Qualified", "Spend (SAR)", "Cost / unique lead (SAR)"].forEach((name) => { const th = element("th", name); th.scope = "col"; row.append(th); }); head.append(row); table.append(head);
    const body = element("tbody");
    Object.entries(result.by_source).forEach(([name, metric]) => { const tr = element("tr"); [name, metric.unique_leads, metric.qualified_leads, metric.spend_sar ?? "Unknown", metric.cost_per_unique_lead_sar ?? "Unknown"].forEach((value) => tr.append(element("td", value))); body.append(tr); });
    table.append(body); const scroll = element("div", undefined, "table-scroll"); scroll.tabIndex = 0; scroll.setAttribute("aria-label", "Lead performance by source"); scroll.append(table); panel.append(scroll);
    paragraph(panel, result.qualification_rate_denominator + ". Acquisition cost uses unique leads, not investors.");
    section(panel, "Management summary"); paragraph(panel, result.management_summary);
    section(panel, "Recommendations"); list(panel, result.recommendations);
    if (result.duplicate_conflicts.length) raw(panel, "Duplicate conflicts (provisional metrics)", result.duplicate_conflicts, true);
  } else if (result?.top_three_backlog_items) {
    result.top_three_backlog_items.forEach((item) => {
      const block = element("div", undefined, "backlog-item"); block.append(element("h3", item.theme), badge(item.priority));
      paragraph(block, item.problem_statement); paragraph(block, "Acceptance: " + item.acceptance_criteria); paragraph(block, item.priority_rationale);
      if (item.implementation_dependencies) { paragraph(block, "Implementation dependencies"); list(block, item.implementation_dependencies); paragraph(block, item.dependency_status); }
      paragraph(block, item.record_count + " feedback records: " + item.evidence_ids.join(", ")); panel.append(block);
    });
    section(panel, "Priority summary"); paragraph(panel, result.priority_rationale);
    raw(panel, "All themes, including internal research", result.themes);
    if (result.unclassified_feedback_ids.length) paragraph(panel, "Needs theme review: " + result.unclassified_feedback_ids.join(", "));
  } else if (result?.observed_facts) {
    facts(panel, { Severity: result.severity }); paragraph(panel, result.severity_rationale);
    section(panel, "Observed facts"); list(panel, result.observed_facts);
    section(panel, "Hypotheses, not proven causes"); list(panel, result.hypotheses);
    section(panel, "Recovery assessment"); paragraph(panel, result.recovery_assessment);
    section(panel, "Next diagnostic step"); paragraph(panel, result.next_diagnostic_step);
    section(panel, "Model diagnostic note"); paragraph(panel, result.draft_note);
  } else if (result?.classification) {
    facts(panel, { Classification: result.classification, Priority: result.priority }); paragraph(panel, result.priority_rationale);
    section(panel, result.draft_response ? "Customer draft (not sent)" : "Clarification"); paragraph(panel, result.draft_response || result.clarification);
  } else raw(panel, "Result details", result, true);
  sources(panel, "Workflow evidence", response.sources);
  sources(panel, "Model citations", result?.draft_source_ids);
  if (response.missing_information.length) { section(panel, "Missing information"); list(panel, response.missing_information); }
  if (response.proposed_action) {
    section(panel, "Stored action proposal"); paragraph(panel, "No action is authorized by this request. The current reviewer decision is separate from this historical response.");
    facts(panel, { Action: stateLabel(response.proposed_action.action_type), "Proposal ID": response.proposed_action.proposal_id });
    const button = element("button", "Switch to Ops test identity and inspect"); button.type = "button";
    button.addEventListener("click", async () => { await changeRole("ops_reviewer"); await inspect(response.proposed_action.proposal_id); }); panel.append(button);
  }
  raw(panel, "Full stored response (JSON)", response);
}
async function refreshHistory() {
  const identity = role, history = await api("/api/history"); if (identity !== role) return;
  const container = $("history"); container.replaceChildren();
  if (!history.length) container.append(element("p", "No requests for this identity yet. Run an example to start.", "muted"));
  history.slice(-12).reverse().forEach((item) => {
    const button = element("button", labels[item.route] || stateLabel(item.route)); button.type = "button";
    button.title = item.request_id; button.append(element("span", "At submission: " + stateLabel(item.status)), element("span", new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })));
    button.disabled = busy; button.addEventListener("click", async () => {
      const view = viewVersion, selection = ++resultVersion;
      try { notice(null); const response = await api("/api/requests/" + encodeURIComponent(item.request_id)); if (view !== viewVersion || selection !== resultVersion) return; if (response) { $("result-panel").hidden = false; renderResult(response); } else notice("This request is still processing. Retry its original ID."); } catch (error) { if (view === viewVersion && selection === resultVersion) notice(error); }
    }); container.append(button);
  });
  if (role === "ops_reviewer") {
    const queue = $("queue"); queue.replaceChildren(); const proposals = history.flatMap((item) => item.proposals).reverse();
    if (!proposals.length) queue.append(element("p", "No action proposals yet. Create a Customer Service ticket or Tech incident first.", "muted"));
    proposals.forEach((proposal) => { const button = element("button"); button.type = "button"; button.disabled = busy; button.setAttribute("aria-pressed", String(selectedProposal?.proposal_id === proposal.proposal_id)); const name = element("span", stateLabel(proposal.action_type)); name.append(element("small", proposal.request_id)); button.append(name, badge(proposal.status)); button.addEventListener("click", () => inspect(proposal.proposal_id)); queue.append(button); });
  }
}
async function inspect(id, outcome) {
  if (role !== "ops_reviewer") return;
  const view = viewVersion, selection = ++inspectionVersion;
  selectedProposal = null;
  $("inspection").replaceChildren(element("p", "Loading exact proposal and outcome...", "muted"));
  try {
    notice(null);
    const [proposal, current] = await Promise.all([api("/api/proposals/" + encodeURIComponent(id)), outcome || api("/api/proposals/" + encodeURIComponent(id) + "/outcome")]);
    if (view !== viewVersion || selection !== inspectionVersion || role !== "ops_reviewer") return;
    selectedProposal = proposal;
    const panel = $("inspection"); panel.replaceChildren();
    section(panel, "Exact persisted proposal"); facts(panel, { Action: stateLabel(proposal.action_type), Status: stateLabel(proposal.status), "Proposal ID": proposal.proposal_id, "Payload SHA-256": proposal.payload_hash });
    const pre = element("pre", JSON.stringify(proposal.payload, null, 2)); pre.dir = "auto"; panel.append(pre);
    if (proposal.decision) { section(panel, "Stored reviewer decision"); facts(panel, { Decision: proposal.decision.decision, Reviewer: proposal.decision.reviewer_actor_id, Time: new Date(proposal.decision.decided_at).toLocaleString() }); }
    if (["pending", "approved", "executing"].includes(proposal.status)) {
      const actions = element("div", undefined, "review-actions");
      const label = element("label"), check = element("input"); check.type = "checkbox"; check.id = "review-confirm";
      label.append(check, element("span", "I reviewed this exact payload and understand that approval creates a local mock action only.")); actions.append(label);
      const buttons = element("div", undefined, "action-buttons"), approve = element("button", proposal.status === "pending" ? "Approve and create mock action" : "Reconcile approved mock action", "primary"); approve.type = "button"; approve.disabled = true; approve.addEventListener("click", () => decide("approve")); buttons.append(approve);
      if (proposal.status === "pending") { const reject = element("button", "Reject proposal", "danger"); reject.type = "button"; reject.disabled = true; reject.addEventListener("click", () => decide("reject")); buttons.append(reject); }
      check.addEventListener("change", () => buttons.querySelectorAll("button").forEach((button) => button.disabled = busy || !check.checked)); actions.append(buttons); panel.append(actions);
    }
    const block = element("div", undefined, "outcome"); section(block, "Verified mock outcome"); block.append(badge(current.outcome));
    if (current.action) facts(block, { "Action ID": current.action.action_id, "Payload SHA-256": current.action.payload_hash });
    else paragraph(block, proposal.status === "rejected" ? "Rejected. No mock action was created." : "No verified successful action is available. A draft or approval alone is not execution success.");
    raw(block, "Execution details and attempts", current); panel.append(block); await refreshHistory();
  } catch (error) { if (view === viewVersion && selection === inspectionVersion) notice(error); }
}
async function decide(decision) {
  if (busy || !selectedProposal || !$("review-confirm")?.checked) return;
  setBusy(true); notice(null);
  const proposal = selectedProposal;
  try {
    const result = await api("/api/proposals/" + encodeURIComponent(proposal.proposal_id) + "/decision", { decision, payload_hash: proposal.payload_hash });
    await inspect(proposal.proposal_id, decision === "approve" ? result : undefined);
  } catch (error) { notice(error); } finally { setBusy(false); }
}
async function runRequest(request) {
  if (busy) return;
  ++resultVersion;
  setBusy(true); notice(null); $("loading").hidden = false; $("retry").hidden = true; $("result-panel").setAttribute("aria-busy", "true");
  const started = performance.now();
  try {
    retryRequest = request; const response = await api("/api/requests", request); retryRequest = null;
    renderResult(response); $("result").prepend(element("p", "Completed in " + ((performance.now() - started) / 1000).toFixed(1) + "s", "muted")); await refreshHistory();
  } catch (error) { notice(error); $("retry").hidden = false; }
  finally { $("loading").hidden = true; $("result-panel").removeAttribute("aria-busy"); setBusy(false); }
}
async function changeRole(next) {
  if (busy || !config) return;
  ++viewVersion; ++resultVersion; ++inspectionVersion;
  role = next; selectedProposal = null; retryRequest = null; notice(null); $("retry").hidden = true;
  $("identity").value = role; document.querySelectorAll("#departments button").forEach((button) => { if (button.dataset.role === role) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); });
  $("page-title").textContent = role === "ops_reviewer" ? "Ops Review" : labels[role] + " workspace"; $("page-description").textContent = descriptions[role];
  $("request-panel").hidden = role === "ops_reviewer"; $("result-panel").hidden = role === "ops_reviewer"; $("review-panel").hidden = role !== "ops_reviewer";
  $("inspection").replaceChildren(); $("result").replaceChildren(element("p", "Run a request to see facts, sources, and missing information.", "muted")); $("result-status").replaceWith(Object.assign(badge("not_run"), { id: "result-status" }));
  $("examples").replaceChildren();
  (examples[role] || []).forEach(([label, text]) => { const button = element("button", label); button.type = "button"; button.addEventListener("click", () => { $("prompt").value = text; $("prompt").focus(); }); $("examples").append(button); });
  $("prompt").value = examples[role]?.[0][1] || "";
  try { await refreshHistory(); } catch (error) { notice(error); }
}
document.querySelectorAll("#departments button").forEach((button) => button.addEventListener("click", () => changeRole(button.dataset.role)));
$("identity").addEventListener("change", () => changeRole($("identity").value));
$("refresh").addEventListener("click", () => refreshHistory().catch(notice));
$("request-form").addEventListener("submit", (event) => { event.preventDefault(); const text = $("prompt").value.trim(); if (text) runRequest({ request_id: crypto.randomUUID(), text }); });
$("retry-button").addEventListener("click", () => { if (retryRequest) runRequest(retryRequest); });
(async () => {
  try { const response = await fetch("/api/config"); if (!response.ok) throw new Error("Cannot connect to the local dashboard. Reload or restart the Python server."); config = await response.json(); $("runtime").textContent = "Local model: " + config.model; $("run").disabled = false; await changeRole(role); }
  catch (error) { notice(error); $("runtime").textContent = "Local runtime unavailable"; }
})();
