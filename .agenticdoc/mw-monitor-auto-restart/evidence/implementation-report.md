# Safe monitor auto-restart: source implementation report

## Delivery / boundaries
User confirmed design, including literal old-process exit and dashboard-asset fingerprint. Source implementation in decision_monitor.py + three local _monitor_open edits in mw.py; two new targeted test files. No current/shared monitor or mw serve operation, real browser/provider/decision API/build/install/commit/framework/config/other-key edits during implementation. Prior research-dispatch two unintended dp1 calls remain disclosed in PM state, not erased. RQ1 done/acked; no new worker dispatch.

## Behavior
- CLI bare monitor/open opts into replacement; compatible authenticated healthy instance reused, no gratuitous restart. Low-level default and explicit status/stop unchanged.
- Incompatible same-project live instance: authenticate recorded health/identity; recheck state/secret/guard/process/self-PID; authenticated AttachedInstance.stop; require stopped=true/detail=null/port_probe=refused/state=absent plus same instance/port; wait bounded10s for provably dead old process; recheck guard/files/port; existing new starter/publication/health; then optional window.
- Unknown/recycled PID/self-PID/identity/auth/stop/file/port uncertainty fail closed, zero replacement/strong-kill/caller state deletion. Secret lstat absence proof avoids exists() silently suppressing errors/broken-link material. Existing stale recovery separate, not used to clear files on successful replacement.
- Module + sorted HTML/CSS/JS labels/raw bytes fingerprint, length framing, same fingerprint field/protocol/schema. Asset-only edit detected on next CLI import. Other transitively imported module cache invalidation not guaranteed.
- Returned/JSON replacement includes previous identity, actual stop result and process_exit_confirmed. Old exit flag true on observed death even if a foreign listener prevents start; starter/health errors retain partial-outcome metadata. Text mode distinguishes replaced; no control token/boot URL added.

## RED → GREEN evidence
All logs and UTC/argv/cwd/rc metadata retained under evidence/runs/.
- red1: lifecycle15F6P (real prior incompatibility refusal, three unchanged asset hashes, missing-asset refusal); CLI2F2P (actual _monitor_open omitted opt-in), not missing-keyword TypeError.
- green1: lifecycle21P / CLI4P.
- red2:1F23P reproduces old process dead but partial-error exit flag false. Fixed assignment at actual death observation. Subsequent delayed-wait/starter-failure tests were added after main implementation, not claimed test-first.
- green2:26P/4P including private random-port synthetic detached old server with real authenticated HTTP/stop/OS exit/new MonitorInstance health, no provider factories.
- red3:1F27P reproduces exists() false suppressing uncertainty then overwriting foreign synthetic secret. Fixed secret lstat proof.
- final2:28P lifecycle +4P CLI, both exit0, explicit no-signal/no-spawn unit spies; state/secret caller-unlink counter excludes simulated server-owned cleanup. Synthetic old child exits on graceful request or its own15s timer; parent never kills it.

## Stable targeted final verification
Distinct tests (not repeated-run sum): **275 passed, 1 skipped**.
- final2 new lifecycle28 + CLI4; final1 same production bytes existing monitor55P1S, three named pure CLI parser/argv/help probes3P, assets9P, dashboard contracts119P, playground13P, readable UI44P. All ten final1 command exits0; final2 both0.
- Existing Windows skip: POSIX mode-bit isolation test (test_decision_monitor.py:601), not a new waived failure.
- Full original CLI subprocess suite NOT run: contains default shared port-range/browser-stub/force-cleanup paths. Three safe existing CLI probes + new actual _monitor_open boundary probes run instead. Real CLI detached child restart and real-browser/current-monitor acceptance remain unverified.
- Fresh check-design.py exit0: Mermaid0errors0warnings, AC→VC mapping8/8 (document coverage only, not formal runtime AC acceptance).

## AC source-evidence map (not whole-key signoff)
| AC/VC | Source evidence |
|---|---|
|001| empty private project starts one healthy MonitorInstance; new tests + _monitor_open window/no-open stub paths |
|002| actual compatible same-process healthy reuse, raw identity/secret equal; prior monitor55 contracts |
|003| fake-boundary strict order and real synthetic detached old server exits before in-process replacement starter; each HTML/CSS/JS edit changes hash |
|004| five identity/auth/project/unknown scenarios, token-changed-health recheck, self-owner refusal, original bytes preserved |
|005| five strict-stop result refusals; closed port/live or unknown PID; foreign state/secret/port; truthful partial failure; no-kill/unlink spies |
|006| reentrant second ensure while stop holds actual start_lock conflicts, only one start; compatible subsequent reuse tested separately |
|007| actual CLI no-open writer/stub count0, synthetic history/submission bytes equal, boot/control strings absent from report |
|008| actual status/stop routes never enter ensure/window; unchanged source bytes in these functions; existing named CLI probes pass |

## Full npm check blocker (fresh, protected copy)
Commands full output archived: evidence/full-check-final/{stdout.log,stderr.log,metadata.json,source-hashes.json}.
Copied11821 current working-tree files; reused existing node_modules junction, no install/build. Exit1:3warnings2infos in three outside-card TS files:
- packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts
- packages/coding-agent/test/suite/mwoc-w2-contract-judgment.test.ts
- packages/coding-agent/test/suite/mwoc-w3-ledger-extractor.test.ts
formatter_changes=[]; original_changed_during_check=[]. No foreign formatter results applied. Downstream pinned-deps/import/shrinkwrap/install-lock/tsgo/browser-smoke chain did NOT run. This is not full-quality green. Earlier full-check evidence retained separately.

## Byte integrity / impact surface
verify-source-integrity.py exit0; evidence/source-integrity.json + *.session.diff.
- mw.py frozen568074B →568207B, exact replay of three allowed edits; CRLF13015→13016 (one added line), all prior foreign dirty bytes preserved.
- decision_monitor.py frozen117336B →123526B; LF retained; all bytes outside fingerprint/orchestration/ensure/documented module intro unchanged. Baseline before SHA915288303e7200ce...; current source SHA897161c88a2840c4... (source hash differs from combined compatibility fingerprint).
- No restoration guessed from lossy diffs; frozen original bytes remain evidence/baseline/. Tests only two new files; no other existing test modified.

## Next / residual
Remain EXECUTE: source feature implemented/targeted-tested, independent review/formal8AC quality and full-check completion pending. Coordinate outside-scope diagnostics with owner; no unilateral TS edits. No new decision/provider/worker calls. No deployed/current-monitor/browser success claim. Python source feature requires no build/install; next user-run `python packages/multi-workers/mw.py decide monitor open --project .` loads new CLI and safely replaces verifiable incompatible old instance; assistant has not executed this against user's project instance. Unsupported/malformed state or unverifiable older protocol stays error, not bypassed.
