# PDF scope audit, October 5

Source: HissaTech AI Engineer Practical Assessment.pdf, pages 1 to 7.
This checks the PDF requirements, not a general conversational-agent product.

## Current verification

- 69 automated tests pass. Their inference doubles are isolated in `tests/`.
- Cached offline mypy check passes for 13 application/packaging files.
- Browser JavaScript syntax check passes.
- [Fresh real-model report](../artifacts/assessment-audit-20261005-offline/report.html):
  12 workflow/safety cases, 3 routing regressions, 6 rejection/failure checks.
- Three approved actions remain verified after reopening SQLite. Repeated
  approval retains one action per proposal. Attempt counts are 2, 2, and 1.
- Outbound internet disconnection is operator-attested, not independently verified.

## Requirement-by-requirement findings

| PDF requirement | Finding | Checkable evidence |
| --- | --- | --- |
| One entry point, trusted role, four workflows (p1) | Implemented through the shared service, CLI and local dashboard. Role is never taken from prompt text. | `service.py`, `cli.py`, `web.py`, service and web tests |
| Real local interpretation and grounded text (p1) | Real Ollama inference. CLI/dashboard template mode removed; no fake fallback on failure. | Current report's model calls; `model.py`; entry-point regression test |
| Consistent response and local history (p1) | Department, result, sources, gaps, proposal and status persisted. Actor/role history scopes enforced. | `domain.py`, `store.py`, service/web tests |
| Marketing analysis by source and status (p2) | Supplied fixture produces 7 unique, 3 qualified, 3/7 qualification rate, duplicate L04, source/status breakdowns and explicit denominators. | Case 00; marketing tests |
| Known spend, missing values, two recommendations (p2) | Paid Search SAR 600 and Social SAR 400 per unique lead. Unknown spend stays null. Two code-selected, evidence-linked recommendations. | Case 00; marketing tests |
| Marketing privacy and P01 prohibition (p2-p3) | Model sees aggregates, not raw contacts/budgets. Fractional publication produces no action. | Case 08; captured-context permission tests |
| Support classification, P02 priority, customer language (p2) | S01 High; S02 Normal with actual Arabic draft. Source and policy references retained in response and payload. | Cases 01-02; support tests |
| Missing identity and injection (p2-p3) | S03 asks only for identity, no proposal. S04 is blocked, no role change or refund. | Cases 03-04; permission/support tests |
| Product themes and three backlog items (p2) | Supplied feedback grouped with counts and IDs. Top three include problem, priority rationale, testable criteria and dependencies. Fractional feedback is internal research only. | Case 05; Product tests |
| Tech observations, hypotheses and diagnostic step (p2) | High severity for repeated intake errors. R101 timeout correlation is a hypothesis; I04 does not prove recovery. Task stays pending until approval. | Case 06; incident tests |
| Ambiguous and unavailable answers (p2) | Exact PDF ambiguity request asks one question. Conversion data is explicitly unavailable in `missing_information`; no conversion metric invented. | Cases 10-11 |
| Exact persisted action and authorized approval (p3) | Immutable payload, canonical hash and trusted Ops decision checked before execution. Rejection and changed hashes create no action. | Saved decisions; acceptance checks `rejected`, `edited_hash`; approval tests |
| Repetition, restart, bounded failures (p3-p4) | Stable request/proposal keys; verified local records after reopen. Transient retries bounded at two attempts. Permanent/outage cases report failure without false success. | Saved decisions; acceptance checks; restart/transport tests |
| HR01 isolation (p3-p4) | No retrieval route, no fixture contents passed to inference or returned in history. | Case 07; permission tests; source allowlist |
| Setup, fixtures, tests, saved outputs (p5) | Stdlib runtime, documented installed model/download, fresh database reset, original fictional fixtures, actual generated evidence. | README; `data/`; current report; verification guide |
| Screenshots or short recording (p5) | Fresh screenshots of saved real-model department outputs accompany the current evidence. These are generated-output captures, not live dashboard interaction. | Current evidence PNGs and case JSON/HTML |
| Handover and engineering disclosure (p5) | Hardware, model/license, measurements, cost assumptions, limits and controlled future integration documented. Eight hours is the last user-reported total, not a new measurement. | `handover.md` |
| Add feedback and explain a wrong output in review (p5) | Added records in known themes update counts; novel themes are retained for review. Wrong routing is reproduced through real-model regression checks, not hidden by the test double. | `test_remaining.py`; `routing.json`; limits below |

The automated checks verify calculations and control boundaries. A passing status
alone does not establish narrative correctness. Current Marketing, support,
Product and Tech narratives were read against their supplied facts.

## What was removed or corrected

- Removed `TemplateModel` from application code and its selectable CLI/dashboard
  mode. The test double remains only in `tests/model_double.py`.
- Removed the dashboard's fake-model mode flag and obsolete asset placeholder.
- Preserved schema field order and clarified routing responsibilities. Short
  lead requests and genuinely unspecified requests are now checked with the
  installed model. There is no new production keyword-routing fallback.
- Replaced demonstration wording variations with the PDF's exact requests where
  provided, including `answer S02 in Arabic` and `Please handle this issue`.
- Retained the PDF's fictional data, local ticket/task adapters and fault modes.
  They are required assessment components, not pretend model responses.

## Limits to say plainly in the interview

1. Marketing produces the full required report. Arbitrary source/status filters
   and focused conversational analytics are not implemented. A conversion
   question receives that report with the explicit missing-data warning, not a
   separate conversational answer.
2. Product uses code-defined theme matching and backlog templates. Its summary
   uses real inference; it is not an autonomous backlog planner. Novel feedback
   is disclosed for human review rather than silently assigned a made-up theme.
3. Support priority and text-safety screening use conservative bilingual phrase
   rules. They are not complete semantic or injection detection.
4. Model citation lists can omit supporting records. Complete workflow evidence
   is separate; allowed citations and valid JSON are not proof of every claim.
5. Trusted test identities are not production authentication. Local records are
   not Zoho tickets, external replies, deployed fixes or verified payment records.
6. One successful model run and three wording regressions do not establish
   reliability for every possible phrasing. Keep the recorded examples and limits.

## Deliberately deferred

General chat, arbitrary analytics queries, autonomous tool planning, additional
frameworks, new UI features, real connectors and production identity/deployment.
None is necessary to demonstrate the PDF's four bounded workflows.

Earlier source ZIPs and evidence directories are historical. Use the current
audit ZIP and evidence for the cleaned application; do not mix old template-mode
instructions or screenshots into claims about this run.
