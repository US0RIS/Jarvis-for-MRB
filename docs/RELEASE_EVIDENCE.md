# Release evidence — `jarvis-release-gate`

`criteria.md` §4 requires one auditable acceptance record per gate, all bound to one frozen
candidate SHA. `jarvis_mrb/release_gates.py` is that ledger. It sits on top of the Agency
A1–A12 harness (`jarvis-agency-real-gate`) rather than replacing it.

## Storage

- `%APPDATA%\JarvisForMRB\release_evidence.sqlite3`: candidates, sessions, records and the
  client builds the backend has actually seen. SQLite triggers make records append-only, and
  each record carries `prev_hash`/`record_hash`, so tampering breaks the chain
  (`verify_chain`).
- `%APPDATA%\JarvisForMRB\release_evidence\<sha12>\<gate>-<result>-<id>.json`: a readable export
  of every record. The SQLite ledger is authoritative.

## Identity

- The running backend reports `code_sha` and `boot_id` on `/health`. It reports the full identity
  (SHA, clean tree, installation fingerprint, world schema) on authenticated `GET /release/identity`.
- The iOS build phase **Stamp Jarvis build SHA** writes `JarvisBuildSHA` into the app's
  Info.plist. The value is `<sha>` or `<sha>-dirty`, or `unstamped` if git was unavailable.
  The app sends it as `X-Jarvis-Client-Build`, together with `X-Jarvis-Client-Device`
  (identifierForVendor), and only to the private Jarvis backend. The value is shown in
  Settings → Jarvis Server.

## Workflow (on the Windows host, from the deployed checkout, same Python as the service)

```powershell
jarvis-release-gate validate      # compileall + full unittest + Agency A1–A12 synthetic + world diagnostics
jarvis-release-gate freeze        # clean tree + passing validation for this exact SHA/installation
jarvis-release-gate identity      # this checkout vs the running service vs phones seen

jarvis-release-gate start C19 --user-entry-surface "..." --literal-user-request "..." `
    --devices "..." --real-services-or-providers "..." --expected-observable-result "..."
#   ... the user performs the test through normal Jarvis use ...
jarvis-release-gate evaluate <session>          # derived checks, no record written
jarvis-release-gate finalize <session> --result PASS|FAIL|BLOCKED `
    --actual-observable-result "..." --external-readback-or-independent-evidence "..." `
    --permission-or-grant-evidence "..." --failure-case-exercised "..." --artifacts "..." `
    --attest "the lamp visibly turned on"       # required for C18, C19, C22
jarvis-release-gate status                      # C00–C22 for the frozen candidate; exit 0 only if all PASS
```

## What a PASS requires

1. The frozen candidate exists. It was frozen from a clean tree, with a passing validation run
   for the exact SHA and installation.
2. The checkout and the running service report that SHA with a clean tree and the same
   installation fingerprint. The session was started under that candidate.
3. For Agency-backed gates, the session window contains a valid, same-SHA/env REAL receipt for
   each required Agency gate:

   | Gate | Required Agency receipts |
   |------|--------------------------|
   | C04 | A1 |
   | C05 | A2 |
   | C06 | A3, A11 |
   | C07 | A4 |
   | C08 | A5, A6 |
   | C09 | A8 |
   | C11 | A7, A9 |

4. All gate-specific derived checks pass. These are registered in
   `jarvis_mrb/release_gate_evaluators.py`.
5. Every §4 field is filled, including the failure case. The gates that require a human physical
   observation (C18, C19, C22) also need an `--attest`.

FAIL and BLOCKED records are always accepted and remain in the ledger. Freezing a new SHA
starts a new candidate, and every gate on it starts again as `UNPROVEN`.

These tools set up and inspect tests. They never perform the behavior under test (`criteria.md` §3.2).
