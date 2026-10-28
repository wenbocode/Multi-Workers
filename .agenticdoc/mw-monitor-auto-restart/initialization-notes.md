# PM State: mw-monitor-auto-restart

## Snapshot
- Key: mw-monitor-auto-restart
- Next Action: parallel read-only lifecycle and CLI evidence; PM serial design then file-isolated implementation.

## Decisions
- User requested automatic monitor stop/open; conditional incompatible-restart spec recorded, user said 推进. AC001–008 accepted scope; compatible instances reused.
- Depends on mw-decision-context; other key review/UI outstanding remains separate.
- No user live monitor/shared serve operation/browser/decision-model API/build/install/commit/config/framework modifications. Existing serve can dispatch read-only evidence workers.

## Parallel analysis
RQ1 identity/authentication/lifecycle/stop confirmation; RQ2 CLI starter/publication/locking/races/test seams. Read-only code, separate unique evidence files. PM alone writes phase docs. Coding exact disjoint write faces decided after research; joint verification serial on stable files.

## Evidence
- spec.md scope accepted by user 推进.
- pm-state initially missing; record created without machine-owned phase/claim lines; framework to initialize interfaces.
