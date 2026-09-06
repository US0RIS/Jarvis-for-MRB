# Jarvis World Model Operations

This document is the deployment, verification, and rollback contract for the unified Jarvis world model. It intentionally separates **source-complete** from **deployed and verified**.

## Supported source state

The current source tree expects world schema version **4**.

The backend must not be considered operationally upgraded merely because the repository was pulled. A successful deployment requires dependency installation, schema preparation, regression tests, diagnostics, service restart, and runtime checks.

## Home-PC deployment sequence

Run these from the `Jarvis-for-MRB` repository on the Windows backend PC after pulling the desired commit.

```powershell
git pull
py -3.14 -m pip install -e .
jarvis-world-prepare
py -3.14 -m unittest discover -s tests -v
jarvis-world-check
```

`jarvis-world-prepare` performs, in order:

1. Versioned/idempotent world-schema migration.
2. A bounded pre-upgrade SQLite backup when an existing world database is present.
3. Existing core world backfill if its completion sentinel is absent.
4. Existing extended scheduler/background/expense/journal backfill if its completion sentinel is absent.
5. Linker refresh.
6. Project-term reconciliation.
7. Document-version analysis.
8. Persistent-intention refresh.
9. Executive-loop refresh.
10. Full world diagnostics.

Do not use `--force-backfill` during an ordinary upgrade. It exists for deliberate recovery/reconstruction only.

## Migration behavior

The migration authority is `jarvis_mrb.world_migrations`.

- Target version: `4`.
- Version advances only after a migration step returns successfully.
- A database claiming a schema newer than this build supports is refused.
- Existing world data is backed up before an upgrade by default.
- Backups are stored under `%APPDATA%\JarvisForMRB\backups`.
- Only the three most recent pre-upgrade world backups are retained.
- SQLite WAL mode is enabled after migration.
- Migration is also run before backend runtime threads are started. A migration exception is intentionally startup-fatal.

The standalone migration command is:

```powershell
jarvis-world-migrate
```

Use this only when schema migration is needed without historical preparation. Normal deployment should use `jarvis-world-prepare`.

## Diagnostics contract

`jarvis-world-check` exits non-zero when a hard integrity invariant fails.

Hard failures include:

- unsupported or incomplete schema version;
- missing required schema tables;
- SQLite integrity failure;
- foreign-key violations;
- current derived relations without evidence;
- relation `evidence_count` disagreement with actual evidence rows;
- person→project associations without structured participant evidence;
- stale active intention/commitment links;
- goal/intention status disagreement;
- Known People privacy revocation leaks;
- current graph relations involving tombstoned Known People identities;
- multiple current Executive decisions for one intention;
- same-value project-term conflicts;
- term conflicts without their provenance event;
- document-version pairs without a comparison event;
- invalid action-verification states;
- `verified` action outcomes without a `verification.verified` event.

Warnings include disputed beliefs, linker lag, overdue pending verification, explicitly unverifiable effects, degraded runtime providers, non-WAL journal mode after migration, and excessive world-database growth.

## Runtime failure isolation

The proactive runtime tracks provider health in `runtime_subsystem_health`.

Calendar monitoring, urgent-mail monitoring, action verification, meeting prefetch, PC context, resource monitoring, audio damping, and daily-journal startup are isolated from one another. One failing provider must not suppress another provider's checks.

Core world migration and the action audit/verification wrapper are different: their absence would invalidate the state/action contract, so backend initialization refuses to proceed safely rather than silently running without them.

## iPhone snapshot safety

Only `goals`, `waiting`, and `people` are authoritative deletion/revocation collections, and only when the corresponding key is present **and is a list**.

- Explicit `[]` means the authoritative collection is empty and may retire/revoke prior current state.
- Missing keys mean the snapshot is partial; no retirement/revocation occurs.
- Malformed non-list values mean unknown/partial; no retirement/revocation occurs.

Known People removal revokes only the iPhone face-enrollment identity and its copied local profile metadata. It does not silently erase independently sourced Gmail/Calendar/history evidence.

## Graph-association safety

A person's textual mention next to a project does not establish `associated_with_project`.

Person→project association requires structured participant evidence such as sender, recipient, attendee, organizer, assignee, owner, speaker, or participant. Legacy current person→project edges that lack such evidence are retired during migration; their source events/evidence remain in history.

## Rollback

If migration or post-deployment diagnostics fail:

1. Stop the Jarvis service.
2. Preserve the failed `%APPDATA%\JarvisForMRB\world_model.sqlite3` under a different filename for diagnosis.
3. Select the newest pre-upgrade backup under `%APPDATA%\JarvisForMRB\backups` that predates the failed migration.
4. Copy that backup back to `%APPDATA%\JarvisForMRB\world_model.sqlite3`.
5. Restore the previously deployed source commit if necessary.
6. Reinstall that source version's dependencies.
7. Run its diagnostics before restarting the service.

Do not merge or manually edit SQLite rows during an ordinary rollback.

## Final test-phase checklist

These items are intentionally deferred until the source passes are complete and the backend PC/iPhone are available.

### Backend

- `py -3.14 -m pip install -e .`
- `jarvis-world-prepare`
- `py -3.14 -m unittest discover -s tests -v`
- `jarvis-world-check`
- restart `jarvis_mrb.service`;
- verify `/health`;
- verify Gmail/Calendar connectivity;
- verify action audit shows installed;
- exercise at least one read verification and one independently observable write verification;
- verify proactive loop continues after an intentionally unavailable noncritical provider.

### iPhone

- Build the companion app from the matching source revision in Xcode.
- Install/run on the target iPhone.
- Verify authenticated persistent WebSocket reconnect.
- Verify semantic world-snapshot deduplication.
- Verify an explicit empty authoritative list reconciles appropriately.
- Verify a deliberately partial/missing-key snapshot does not retire state.
- Confirm no biometric feature prints, enrollment images, raw camera/audio, incident media, clipboard contents, or privacy-zone coordinates cross the snapshot boundary.

### Acceptance boundary

Criterion 11 is not operationally complete until the above backend and iPhone checks actually run successfully. Source implementation can be complete before that; deployment verification cannot be claimed in advance.
