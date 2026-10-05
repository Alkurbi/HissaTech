# Acceptance evidence

Current bundle: [report](../artifacts/assessment-audit-20261005-offline/report.html),
[JSON and history](../artifacts/assessment-audit-20261005-offline/evidence.json).
Both include department cases, routing checks, controlled failures, approval
decisions and execution history. Redundant exports and the generated database
are omitted. The trimmed source checkout passes all 68 automated tests.

| Assessment scenario | Saved evidence | Automated check |
| --- | --- | --- |
| English and Arabic, all departments | cases[0] through cases[6] | test_model_path.py, test_marketing_support.py, test_remaining.py |
| Duplicate L04, denominators and unknown spend | cases[0]; cases[10] for unknown conversion | test_marketing_support.py |
| Missing identity, ambiguous request | cases[3], cases[11] | test_app.py, test_model_path.py |
| Missing source | acceptance_checks: missing_source | test_permissions.py |
| Repeated request | acceptance_checks: repeat_request | test_app.py, test_demo.py |
| Repeated approval and database restart | evidence.json: decisions, first and after_restart; exactly one action assertion | test_remaining.py, test_app.py |
| Rejected approval or edited hash | acceptance_checks: rejected, edited_hash; no stored actions | test_app.py, test_demo.py |
| Transient adapter failure and bounded retry | decisions[0], two attempts, one action | test_app.py |
| Uncertain action reconciled after reopen | decisions[1], same execution key | test_remaining.py |
| Model unavailable or adapter always fails | acceptance_checks: model_unavailable, always_fail | test_model_path.py, test_demo.py |
| Injection, HR01 and wrong trusted role | cases[4], cases[7], cases[9] | test_permissions.py |
| P01 publication prohibited | cases[8]; Product internal research in cases[5] | test_app.py |
| Product dependencies and novel feedback | cases[5]; unknown dependencies explicitly labeled | test_remaining.py |

Real inference is used for interpretation and drafting in the department cases and
the ticket drafts underlying rejection/approval checks. Outage, missing-source and
adapter failure scenarios deliberately exercise controlled faults and are labeled.
Automated tests use doubles except transport-specific local-server tests. A passing
status is not semantic proof: manually inspect narrative claims against supplied
facts and citations. No salary fixture value is loaded by application retrieval.

Run `python -m unittest discover -s tests -v` for the complete suite.
Run `python -m hissatech.demo --offline-attested --output artifacts/new-run` only
after disconnecting outbound internet. The output directory must not already exist.
Do not overwrite the selected submission evidence with an unreviewed run.
