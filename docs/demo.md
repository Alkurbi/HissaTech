# Demo guide (under seven minutes)

Setup: Python 3.11+, Ollama running, selected model installed. Run from the project
root. Disconnect outbound internet before recording the offline attestation.

```powershell
python -m unittest discover -s tests -v
python -m hissatech.demo --offline-attested
```

The runner generates a fresh database and saves JSON/HTML without changing fixture
data. It uses scripted trusted Ops approval of local mocks only. For a live review,
inspect the proposal and approve manually through the CLI instead.

Suggested walkthrough:

1. 0:00 to 0:45: show architecture and local-only boundaries.
2. 0:45 to 1:45: Marketing, seven unique leads, three qualified, duplicate L04,
   unknown spend and no investment-conversion data.
3. 1:45 to 3:00: S01 High, S02 Arabic Normal, S03 missing identity, S04 blocked.
4. 3:00 to 4:00: Product evidence counts, top three, fractional research only.
5. 4:00 to 5:00: Tech High, possible timeout relationship, recovery unknown.
6. 5:00 to 6:15: inspect stored payload, approval hash, fail-once recovery,
   uncertain outcome reconciliation, same action ID after database reopen.
7. 6:15 to 7:00: HR denial, wrong role, P01 publication block, ambiguity, limits.

Manual review commands (substitute the stored proposal ID and hash):

```powershell
python -m hissatech inspect --role ops_reviewer --proposal-id <id>
python -m hissatech approve --role ops_reviewer --proposal-id <id> --payload-hash <hash>
python -m hissatech outcome --role ops_reviewer --proposal-id <id>
python -m hissatech history --role ops_reviewer
```

For a fresh run, prefer a new database via global `--db <new-file>` rather than
deleting audit history. Global `--model <installed-name>` must precede the command.
Earlier failed model runs are preserved under `artifacts/`, not claimed as passes.

Submission run: [saved report](../artifacts/assessment-audit-20261005-offline/report.html),
[full JSON evidence](../artifacts/assessment-audit-20261005-offline/evidence.json), and
[acceptance index](acceptance.md). Fresh Marketing, Arabic support, Product and
Tech screenshots capture the saved real-model output pages. They show generated
evidence, not a live dashboard interaction or a prerecorded model response.

Final deterministic verification: 68 tests passed; mypy reported no issues in
12 application files. Standards and specification reviews have no remaining blocking
findings in the earlier review. New submission checks are documented in the
acceptance index. Narrative citation completeness remains a disclosed limitation.

The runner also records rejection, mismatched approval hashes, permanent adapter
failure, repeated requests and an unavailable local inference endpoint. Adapter
modes are fault simulations; the unavailable endpoint is not model output.
These are separate from the real-model department examples.
