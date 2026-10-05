# Acceptance evidence

Current bundle: [report](../artifacts/assessment-audit-20261005-offline/report.html),
[JSON and history](../artifacts/assessment-audit-20261005-offline/evidence.json),
[fault and rejection checks](../artifacts/assessment-audit-20261005-offline/acceptance.json),
and [real-model routing regressions](../artifacts/assessment-audit-20261005-offline/routing.json).
The report embeds the complete bundle. `demo.sqlite3` retains exact proposals,
approvers, actions and attempts. Earlier exploratory runs are not submission evidence.
The cleaned ZIP was extracted into a fresh directory: all 69 tests passed, and
a real-model S01 request returned a pending proposal from that extracted copy.
The [October 5 PDF scope audit](assessment-audit.md) describes the runtime cleanup,
exact-PDF request checks, current limits and deferred features.

| Assessment scenario | Saved evidence | Automated check |
| --- | --- | --- |
| English and Arabic, all departments | case-00 through case-06 JSON/HTML | test_model_path.py, test_marketing_support.py, test_remaining.py |
| Duplicate L04, denominators and unknown spend | case-00; case-10 for unknown conversion | test_marketing_support.py |
| Missing identity, ambiguous request | case-03, case-11 | test_app.py, test_model_path.py |
| Missing source | acceptance.json: missing_source | test_permissions.py |
| Repeated request | acceptance.json: repeat_request | test_app.py, test_demo.py |
| Repeated approval and database restart | evidence.json: decisions, first and after_restart; exactly one action assertion | test_remaining.py, test_app.py |
| Rejected approval or edited hash | acceptance.json: rejected, edited_hash; no stored actions | test_app.py, test_demo.py |
| Transient adapter failure and bounded retry | decisions[0], two attempts, one action | test_app.py |
| Uncertain action reconciled after reopen | decisions[1], same execution key | test_remaining.py |
| Model unavailable or adapter always fails | acceptance.json: model_unavailable, always_fail | test_model_path.py, test_demo.py |
| Injection, HR01 and wrong trusted role | case-04, case-07, case-09 | test_permissions.py |
| P01 publication prohibited | case-08; Product internal research in case-05 | test_app.py |
| Product dependencies and novel feedback | case-05; unknown dependencies explicitly labeled | test_remaining.py |

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
