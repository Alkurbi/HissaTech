// Run this function in the dashboard browser after creating at least two proposals.
// Read-only regression: deliberately reorder real HTTP reads without changing data.
async function dashboardRaceChecks() {
  await changeRole("ops_reviewer");
  const history = await api("/api/history");
  const proposals = history.flatMap((item) => item.proposals);
  if (proposals.length < 2) throw new Error("Create two local proposals before this browser check.");
  const nativeFetch = window.fetch;
  const results = {};
  let release, reached;
  try {
    const gate = new Promise((resolve) => release = resolve);
    const seen = new Promise((resolve) => reached = resolve);
    window.fetch = async (...args) => {
      if (String(args[0]).endsWith("/" + proposals[0].proposal_id + "/outcome")) { reached(); await gate; }
      return nativeFetch(...args);
    };
    const earlier = inspect(proposals[0].proposal_id);
    await seen;
    await inspect(proposals[1].proposal_id);
    release(); await earlier;
    results.inspection = document.querySelectorAll("#inspection .outcome").length === 1 && selectedProposal.proposal_id === proposals[1].proposal_id;
    window.fetch = nativeFetch;

    await changeRole("ops_reviewer");
    const historyGate = new Promise((resolve) => release = resolve);
    const historySeen = new Promise((resolve) => reached = resolve);
    window.fetch = async (...args) => {
      if (String(args[0]).includes("/api/requests/")) { reached(); await historyGate; }
      return nativeFetch(...args);
    };
    document.querySelector("#history button").click();
    await historySeen;
    await changeRole("marketing");
    release();
    await new Promise((resolve) => setTimeout(resolve, 100));
    results.historyIdentity = !document.getElementById("result").textContent.includes("Request ");
    if (Object.values(results).some((passed) => !passed)) throw new Error("Dashboard read race regression: " + JSON.stringify(results));
    return results;
  } finally { window.fetch = nativeFetch; if (release) release(); }
}
