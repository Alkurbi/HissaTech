# HissaTech local assistant

Four assessment workflows: Marketing lead analysis, Customer Service ticket drafts,
Product feedback prioritization, and Tech incident triage. Runs on Python's standard
library, local Ollama inference, and SQLite. Fictional data and local mock actions
are assessment requirements.

## Setup and run

Install Python 3.11+ and Ollama. No Python dependencies are required.

```powershell
ollama pull mistral-nemo:latest
python -m hissatech.web
```

Keep Ollama running, then open http://127.0.0.1:8000. Download the model before
disconnecting outbound internet for the offline demonstration. Dashboard identities
are trusted test roles, not authentication. There is no canned-response fallback.

CLI examples from the project root:

```powershell
python -m hissatech request --role marketing --text "Analyze lead quality and campaign sources"
python -m hissatech request --role customer_service --text "Draft a response and ticket for S01"
python -m hissatech request --role product --text "Prioritize customer feedback into a backlog"
python -m hissatech request --role tech --text "Triage the incidents and propose tasks"
```

## Review actions

Requests only propose actions. Inspect the saved content before approving its
exact ID and hash. Replace `<id>` and `<hash>` with the returned values:

```powershell
python -m hissatech inspect --role ops_reviewer --proposal-id <id>
python -m hissatech approve --role ops_reviewer --proposal-id <id> --payload-hash <hash>
python -m hissatech outcome --role ops_reviewer --proposal-id <id>
```

Actions create local mock tickets/tasks, never contact customers or real systems.
Decisions and execution history persist across restarts.

## Test and reset

```powershell
python -m unittest discover -s tests -v
python -m hissatech --db fresh.sqlite3 request --role marketing --text "Analyze leads"
```

Use a new database to reset without deleting audit history. CLI and dashboard
have separate default databases; pass the same `--db` path to share history.
To capture fresh real-model evidence after disconnecting outbound internet:
`python -m hissatech.demo --offline-attested --output artifacts/new-run`.

## Presentation

- [System architecture](docs/architecture.svg) and [approval flow](docs/approval-flow.svg).
- [Handover](docs/handover.md): model, hardware, time, cost assumptions and limits.
- [Saved offline report](artifacts/assessment-audit-20261005-offline/report.html), [acceptance evidence](docs/acceptance.md), and [demo guide](docs/demo.md).

Marketing produces the required full report, not arbitrary filtered analytics.
Model narratives still require review. Test doubles are confined to automated
tests; production integrations and authentication are outside this assessment.
