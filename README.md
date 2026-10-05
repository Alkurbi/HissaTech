# HissaTech local agent prototype

This is a local CLI and browser prototype for the HissaTech AI Engineer Practical Assessment. It uses local JSON fixtures, SQLite, local model inference through Ollama, and mock adapters only.

## Requirements

- Python 3.11 or newer. No Python packages are required.
- Ollama, with a locally downloaded instruction model. The default is `mistral-nemo:latest`, tested on the handover machine for English and Arabic.

Reference environment: Python 3.13.5, Ollama 0.32.1, model ID `e7e06d107c6c`,
12.2B Q4_0. Verify the ID with `ollama list`: the downloadable tag can change.
There are no third-party Python runtime dependencies to pin. Tests use stdlib
`unittest`; optional type-check tooling is not required to run the submission.

Download the model once while internet access is available:

```powershell
ollama pull mistral-nemo:latest
```

After download, run Ollama locally and disable outbound internet. The application calls only `127.0.0.1:11434`.

## Run

For the browser dashboard:

```powershell
python -m hissatech.web
```

Open `http://127.0.0.1:8000/`. It uses the same service and a separate
`dashboard.sqlite3`. See [dashboard guide](docs/dashboard.md) for identity,
review, and local-only security boundaries.

Use a real local model:

```powershell
python -m hissatech request --role customer_service --text "draft a ticket for S01"
```

The JSON response includes a pending proposal ID and immutable payload hash. Approve it using the trusted test identity:

```powershell
python -m hissatech approve --role ops_reviewer --proposal-id <proposal-id> --payload-hash <payload-hash>
```

Other requests:

```powershell
python -m hissatech request --role marketing --text "summarize Prime lead performance"
python -m hissatech request --role customer_service --text "draft a ticket for S02"
python -m hissatech request --role product --text "prioritize product feedback"
python -m hissatech request --role tech --text "triage lead intake failures"
```

The CLI, dashboard, and evidence runner require real Ollama inference. There is
no canned-response mode or fallback. The deterministic model double lives only
in `tests/model_double.py` and is not imported by the application.

## Marketing and support inputs

Marketing runs the assessment's full lead-analysis workflow, not arbitrary
conversational queries or source filters. It reports unique leads, status counts by source, qualification rates,
known spend and cost denominators, and counts of unknown budgets and sources.
Conflicting duplicate imports identify row IDs and changed field names, not
contact IDs or budget values. The first import is retained and conflicting metrics
are explicitly provisional. Missing information and two recommendations are derived
from current data. Qualification is not investment conversion.

Support accepts exactly one fixture reference, such as `draft a ticket for S01`.
Unknown or multiple references ask for clarification. Mentioning payment alone
does not substitute a customer's message.

To supply a new message, pass a JSON object as the request text. Supported fields
are `message`, optional `customer_id`, and optional `language` (`en` or `ar`).
Omitted language is inferred from Arabic characters; omitted identity asks only
for the customer ID and creates no proposal. For example, through the shared service:

```python
import json
from hissatech.domain import Request
from hissatech.model import LocalModel
from hissatech.service import submit_request
from hissatech.store import Store

text = json.dumps({
    "message": "My payment succeeded but confirmation is missing.",
    "customer_id": "C09",
    "language": "en",
})
store = Store("hissatech.sqlite3")
try:
    result = submit_request(Request("customer-message-1", "customer_service", text),
                            store, LocalModel("mistral-nemo:latest"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
finally:
    store.close()
```

`proposed_action.payload` contains the exact customer message and draft stored for
approval, with language, identity, classification, priority rationale, and sources.
Customer Service never sends the reply or executes its pending proposal.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests cover the assessment scenarios using the deterministic test model. Demonstrate at least one workflow with Ollama during review.

## Design boundaries

The CLI calls the interface-independent application service using an immutable
validated request. Domain contracts, local inference, workflows, and SQLite
storage have separate modules. The browser and CLI submit the same request
through the service without reproducing workflow logic. The obsolete `app.py`
compatibility imports have been removed.

- The model is used for request interpretation and grounded drafting only.
- Interpretation returns a validated department or one clarification question.
  Drafts use JSON contracts with source IDs checked against the supplied context.
  Each result retains the model's actual citations as `draft_source_ids`, separate
  from the workflow's overall evidence in `sources`.
  Malformed output returns `model_invalid_output`; local transport failures return
  `model_unavailable`. Neither failure creates a ticket or task proposal.
- The Ollama adapter uses schema-constrained JSON, deterministic sampling, a 30-second
  wall-clock deadline per inference call, a bounded response size, and rejects incomplete generations.
  Transport connections are closed on success and failure.
- Code controls route validation, role checks, P01 to P03, calculations, approvals, persistence, retries, and adapter execution.
- `data/hr01.json` is an isolated test fixture. Application code never loads it.
- Marketing aggregation reads raw leads internally but returns only de-identified aggregates to the model and user.
- Retrieval uses an explicit source-name and role allowlist in `sources.py`.
  Unknown names, paths, cross-department reads, and HR01 have no retrieval route.
  Request and draft checks reject common authority-changing instructions and
  unsupported execution claims. These checks do not grant approval or execute actions.
  Missing files or invalid JSON return `source_unavailable` without a proposal.
- A proposal stores immutable canonical JSON plus SHA-256 hash. Approval must match both the proposal ID and hash.
- The mock adapter uses the proposal ID as its execution key, so repeats and restarts cannot create duplicate tickets or tasks.

## Reset

For a clean start without deleting history, choose a new database:

```powershell
python -m hissatech --db fresh-demo.sqlite3 request --role marketing --text "summarize Prime lead performance"
python -m hissatech.web --db fresh-dashboard.sqlite3
```

The browser and CLI otherwise use separate default databases. Keep fixture files
unchanged for the assessment; experiment with a copy. New requests read current
files; reusing a request ID returns its historical response.

## Known limits

- Routing uses the local model, not a production keyword matcher. Ambiguous
  requests ask one clarification; model interpretation can still be wrong.
- The CLI has no authentication because the assessment uses trusted test identities.
- Mock adapters do not contact Zoho Desk, CRM, Slack, or Drive.
- See [handover](docs/handover.md), [architecture](docs/architecture.md), and [demo guide](docs/demo.md) for measurements and submission evidence.
- Valid JSON and allowed citations do not prove every narrative claim is correct.
  Text safety checks are conservative heuristics, not complete injection detection.
  Support priority uses conservative English and Arabic evidence phrases; extend
  these rules from reviewed messages when additional wording needs support.
  Review real-model outputs for factual grounding and policy compliance. Automated
  tests use doubles; real Ollama evidence is captured separately by `hissatech.demo`.

## Review and evidence

Use `inspect --role ops_reviewer --proposal-id <id>` before approving, then
`outcome --role ops_reviewer --proposal-id <id>` to verify the executed payload.
`history --role ops_reviewer` lists persisted requests and decisions. Department
history is restricted to its trusted actor and role. `--actor-id` distinguishes
test users; it is not production authentication.

```powershell
python -m hissatech.demo --offline-attested
```

This creates a fresh SQLite database, twelve real-model cases, reviewer/restart
evidence, and HTML reports under `artifacts/`. Only use `--offline-attested` after
disconnecting outbound internet yourself. It records your statement, not an
independent network test. No network settings are changed.

SQLite migrations are additive. Legacy actions without stored executed payloads
remain `legacy_unverified`. Interrupted requests can resume after a five-minute
lease; stale workers cannot create proposals after takeover. Use a new request
ID when changing input or using a legacy cached request with different identity.

## Submission

Start with [acceptance evidence](docs/acceptance.md), [handover](docs/handover.md),
the [PDF scope audit](docs/assessment-audit.md), and the
[seven-minute walkthrough](docs/demo.md). Build a source ZIP using:

```powershell
python scripts/package_submission.py --evidence artifacts/assessment-audit-20261005-offline --output dist/hissatech-assessment-audit-20261005.zip
```

The packager includes source, browser assets, tests, fixtures, docs, and the selected
evidence only. It excludes model weights, environments, caches, working databases,
temporary directories, agent configuration, and exploratory runs. The selected
evidence database is included deliberately for read-only inspection.
