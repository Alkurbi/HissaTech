# Architecture

One process, Python standard library, local Ollama, and SQLite. No orchestration
framework is needed for four bounded workflows and a small fixture set.

```text
CLI or local browser
  -> service: trusted identity, scope, request fingerprint and lease
  -> local model: interpret destination, never grant permissions
  -> scoped sources + workflow: calculate facts and enforce P01/P02/P03
  -> local model: draft from authorized facts, validate JSON and citations
  -> response + immutable proposal in SQLite (no action yet)

Ops reviewer -> service inspection -> approve exact ID + payload hash
  -> SQLite transaction -> mock ticket/task -> verified outcome + history
```

Marketing owns lead analysis, not sales or investment conversion. Customer
Service drafts acknowledgements and ticket proposals. Product turns feedback
into an evidenced backlog. Tech separates observed failures from hypotheses and
proposes incident tasks. Ops Reviewer is an approval role, not a fifth workflow.
Shared policies connect the workflows; one department cannot read another's raw
records. HR01 has no retrieval route.

`domain.py` owns request/response contracts. `service.py` is the reusable interface
boundary. `sources.py` validates role-scoped fixtures and aggregates leads.
`workflows.py` owns departmental rules. `model.py` owns local transport and output
contracts. `policies.py` enforces restrictions. `store.py` owns snapshots,
decisions, bounded mock execution, and history. `cli.py` only presents these calls.

The proposal hash binds the reviewer to canonical content. SQL triggers protect
snapshots and decisions. Unique execution keys and transactions prevent duplicate
local actions. Transient failures get at most two attempts; permanent failures
stop. An uncertain action is reconciled by its existing key before reporting
success. These guarantees cover the local mocks, not a future remote API.

The local browser calls the same service, supplies an explicit trusted test identity
outside the prompt, and displays the stored proposal before review. Production
would require an authenticated identity. A real integration needs
its own authorization, timeout, idempotency, and reconciliation contract before
replacing the mocks. New departments need an explicit scope, validated sources,
workflow, and service acceptance checks, not a generic autonomous agent.
