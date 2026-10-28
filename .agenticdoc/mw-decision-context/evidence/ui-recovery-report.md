# T11 PM recovery — 2026-10-23

## Authority and ownership
User approved PM takeover with “继续” after dp4 service disabled. Failed worker remains failed/acked; no fabricated worker output or completion. PM owns only original T11 seven paths; T10 remains sole backend writer. No dispatch/model call/build/install/service/config/framework/commit operation.

## Investigation and changes
Original V8 worker crash was heap exhaustion, not timeout. Correctly decoded archived UTF-16 logs into evidence/ui-recovery; independent isolated file-by-file replay reproduced 7 failures (assets3/workbench4), contracts119P and readable fixture15P. Full raw stdout/stderr and UTC/argv/cwd/exit are retained in *metadata.json.

Pre-PM seven originals, sha256/bytes and git status/diff saved under evidence/ui-recovery. Worker JS CRLF differed from static asset loader LF. Explicit byte-only CRLF→LF recovery preserves all UTF-8 text; newline-recovery.json records hashes/count (no guessed CJK restoration).

Migrated outdated case shell assertions to complete native question mapping, preserving auth/containment/no-model/security assertions. Minimal logs no longer require technical provenance/book/version details; underlying API facts asserted retained. Legacy receipt labels now explicitly distinguish inferred/unknown from recorded instead of presenting inference as an actual receipt.

Graph defects found during full inspection: downward edge ended at next node bottom (crossed body), and production/test SVG used duplicate marker id. DOM regression RED saved; corrected endpoint and graph-specific marker ids. Key node hides record_version/logical_id as approved.

Actual T10 interface is questions mapping, not T11 arrays. Updated fixture to native mapping, reproduced 4 failures (no questions editor), then changed editor/collection/reset to mapping; submitted body retains native keys. policy_result.selection mapping uses readable formatFree rather than [object Object].

## Independent verification
- red: assets3F6P; workbench4F13P; contracts119P; readable15P (fixture only).
- red-graph: 2 directed marker tests failed before fix. RED per-node logs overwrite same suite basename in this runner; metadata preserves both commands; second stdout is retained. Geometry was asserted with marker RED then GREEN, not separately isolated RED.
- red-map: readable4F11P before mapping fix.
- green-map: assets9P, workbench17P, contracts119P, readable15P; all exit0.
- joint-case: readable16P exit0, including real private-loopback /api/test/cases + /api/dps payload → shipped DOM all four cases/editor native question mappings; zero observe POST. Added joint test is post-implementation acceptance, not new feature test-first claim.

## Remaining acceptance gaps
T10 is still running and report was modified after its initial completion claim; final logs/hash/report absorption pending. No protected full npm check yet (wait backend stop). No new deployment or visual/browser acceptance.

AC024 criteria edit has a real scope discrepancy: T10 interface permits only instructions edits and rejects changed static criteria; approved scope requires editable instructions/criteria with fixed DP allowlists. PM must review and resolve, not silently narrow AC. Production/test graph shared renderer works, but submissionDagNodes still creates detail:null and does not expose real observation material/policy/captures in clicked test nodes; existing fixture count alone does not accept this. Full observation HTTP→DOM/send-preview equivalence remains pending.

Prior TS encoding uncertainty and framework finalize gate blocker remain. No 24AC or phase-completion claim.
