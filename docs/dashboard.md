# Local dashboard

The browser interface calls the same service as the CLI. It does not grant roles
from prompts or perform real external actions. Explicit role switching is for the
assessment's trusted test identities, not production authentication.

```powershell
python -m hissatech.web
```

Default address: `http://127.0.0.1:8000/`. Default model: the existing local
`mistral-nemo:latest`. The dashboard keeps its own `dashboard.sqlite3` so opening
the UI does not alter previously saved demonstration databases.

Options: `--port`, `--db`, and `--model` (an installed Ollama model).
There is no template-response mode. Stop with Ctrl+C.

The server binds only loopback, serves three explicit frontend assets, validates
Host and Origin, requires a per-start browser token for API access, limits JSON
body size, and applies a same-origin content security policy. Nothing is fetched
from a CDN. Each HTTP operation opens its own SQLite connection; all workflows
and reviewer checks stay in the existing application service.

Local test identity selection is not a security boundary against another user or
process on the same machine. Do not expose this prototype through a reverse proxy
or port forwarding. Production requires real authenticated sessions and a suitable
application server, not Python's demonstration HTTP server.

The immutable request response is historical. An approved proposal does not edit
that original response. Reviewer inspection and outcome retrieval show its current
decision and verified execution state separately.

Use department navigation to select a test identity. Example buttons only fill
the request; press Run request to generate locally. Recent requests reopen the
stored response. For a proposed action, switch explicitly to Ops Review, inspect
the payload/hash, check the review acknowledgement, then approve or reject.

Browser checks exercised real S01 inference and approval, with matching proposal
and executed payload hashes. The published evidence contains fresh screenshots
of generated department outputs, not live dashboard interaction. Earlier desktop,
mobile and Lighthouse checks are not bundled as evidence of the current run.

`tests/dashboard_browser_checks.js` is a read-only browser regression. After two
proposals exist, run its `dashboardRaceChecks()` function in the loaded dashboard's
browser context. It delays actual reads to check that an older proposal outcome
cannot appear under a newer proposal and that an old history read cannot repaint
a new identity's workspace.
