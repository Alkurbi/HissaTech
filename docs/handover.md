# Assessment handover

Delivered: four department workflows, CLI and local dashboard, scoped retrieval,
bilingual drafts, immutable approval-gated mock actions, and durable history.
AI coding assistants and ECC/Impeccable skills supported design, implementation,
tests and review. Candidate last reported **8 hours total**, including the dashboard
and earlier submission fixes. Time for later cleanup has not been reconfirmed.
No hosted inference or real company integration is used.

Machine observed: Intel Core i7-14700KF, NVIDIA RTX 4070 Ti SUPER, approximately
63.79 GiB RAM, Windows, Python (exact version in evidence metadata), Ollama 0.32.1.
Selected model: `mistral-nemo:latest`, installed ID `e7e06d107c6c`, 12.2B parameters,
Q4_0, approximately 7.1 GB on disk. Installed model metadata identifies Apache 2.0.
Weights are not bundled. Smaller `qwen2.5:3b` was tested but produced unsupported
narrative facts, so it is not the selected submission model.

October 5 normal department examples took 1.2 to 3.3 seconds end to end.
An earlier cold request took about 30 seconds. The refreshed
[submission report](../artifacts/assessment-audit-20261005-offline/report.html) has exact
current per-call and end-to-end measurements. These are examples, not percentiles.

The operator reconfirmed disconnected outbound internet for the refreshed run. It
uses loopback inference, local files, and mock adapters. Network isolation was
not independently verified and no network settings were changed by the assistant.

Cost assumptions: no new hardware, paid API, or runtime package cost. Illustrative
electricity estimate, not a measured bill: assume 0.30 kW average power and
0.25 SAR/kWh for one hour of demonstration, yielding 0.075 SAR. These are arbitrary
planning assumptions, not verified consumption or tariff. Engineering cost is
8 times the candidate's hourly rate, which was not supplied. Hardware depreciation
and model-download costs are excluded; actual total monetary cost remains unknown.

Evidence: [acceptance index](acceptance.md) and [demo/screenshots](demo.md).
All 68 deterministic tests pass; cached offline type checks pass for 12
application files. The index
distinguishes real inference from controlled faults. Approvals and exact executed
payloads survive database reopen. Earlier reviews had no blocking findings;
current submission changes have separate automated checks.

Limits: trusted CLI identities are not authentication. Narrative checks and
bilingual phrase rules are conservative heuristics, not proof of grounding or
complete injection detection. Model citations may be less complete than workflow
evidence. Known Product themes have a finite vocabulary; novel feedback is retained
for review. Dependencies are investigation prerequisites, not confirmed facts.
Marketing remains the full required report, not filtered conversational analytics.
No canned model mode or fallback is available through the application.
SQLite serializes local writes. Real Zoho/CRM/Slack/Drive integrations and
production deployment are deliberately excluded. The HTTP server is demo-only.

Controlled integration: first establish authenticated identities, least-privilege
credentials and sandbox data. Pilot Zoho Desk draft-ticket creation behind exact
payload approval, adapter-side idempotency and uncertain-outcome reconciliation.
CRM reads and Slack/Drive writes need separately authorized scopes, redacted audit
logs and failure tests. Keep financial, account-changing and customer-send actions
disabled until explicitly designed and approved. Rehearse a feedback addition and
incorrect-model-output investigation for the live review.
Source repository: https://github.com/Alkurbi/HissaTech.
