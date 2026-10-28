# Spec: mw-monitor-auto-restart

> Key: mw-monitor-auto-restart
> Status: scope locked (AC-001..008); user confirmed design including literal old-process exit and asset fingerprint. Source implementation evidence in evidence/implementation-report.md; not whole-key accepted/deployed.
> Depends on: mw-decision-context

## §0 Goal Alignment
Source: .agenticdoc/goal.md. Support reliable PM decision-workbench access after source updates without repeated manual stop/open; Python CLI lifecycle only, no pi-core changes, no new centralized scheduler. Preserve file-lock coordination and process/credential isolation. No goal changes.
预期收益：在身份可验证的不兼容实例场景，一条 monitor/open 命令完成安全替换，手动 stop/open 次数从2条降至1条；兼容场景零重启、异常场景零强杀/删除现场（AC002–005）。Scope source: evidence/research/spec-user-confirmation-20261024.md.

## §1 Scope
When `mw decide monitor` or `mw decide monitor open --project .` encounters an existing compatible healthy instance, reuse it. When the recorded instance is incompatible with current code/protocol, automatically verify authenticated instance/project identity, gracefully stop it, confirm actual shutdown, then start/open the current instance. No existing instance: ordinary start/open. `--no-open` remains respected. `status` and explicit `stop` retain their behavior.

User intent is single-command refresh of monitor after code changes, not build/install, model calls, or deleting history. Proposed conditional restart (compatible reuse), not gratuitous restart of every compatible instance. Any force-restart command/UI extension would need separate confirmation.

## §2 Safety and exclusions
- Never unauthenticated shutdown, stop foreign project/process, reuse stale secret without identity proof, force kill, delete live instance state, or start replacement before confirmed exit.
- Unknown/unresponsive/mismatched identity, failed authenticated stop or shutdown timeout: fail closed, preserve state and report actionable error.
- Concurrent opens/restart races must use existing lifecycle locking and identity rechecks, with at most one replacement instance.
- Preserve all history/test submissions and state outside lifecycle-controlled identity/secret publication. No automatic observation submit/retry/provider/credential probe.
- Implementation tests use synthetic dependencies/private temporary project loopback only. Do not operate user's live monitor or shared mw serve, real browser, install/build/commit/framework/config.
- Eight-DP consolidation and outstanding case-dropdown/UI fixes excluded.

## §3 Acceptance Criteria (locked)
| ID | Observable acceptance |
|---|---|
| AC-001 | Given no instance, monitor open starts exactly one healthy instance and opens one window (zero windows with --no-open). |
| AC-002 | Given authenticated healthy compatible instance, open reuses identity/PID, with zero stop/start calls. |
| AC-003 | Given authenticated incompatible instance of same project, open orders verify→graceful stop→confirmed exit→new start→window open; exactly one replacement. |
| AC-004 | Given project/instance identity mismatch or missing authentication proof, open returns failure with zero shutdown/start/window calls and unchanged existing state. |
| AC-005 | Given failed stop/unresponsive instance/shutdown timeout, open returns failure with zero replacement/strong-kill/delete-live-state and preserves evidence. |
| AC-006 | Given concurrent opens during replacement, at most one active replacement and no stale-identity stop/delete. |
| AC-007 | Given automatic replacement, --no-open prevents browser/window operation; history and test submission bytes remain unchanged. |
| AC-008 | Given explicit status/stop commands, existing contracts remain unchanged; no start/window/model calls added. |

## §4 Initial evidence and next design work
Known source anchors: packages/multi-workers/decision_monitor.py:2663 ensure_instance; :2539 AttachedInstance.stop; packages/multi-workers/mw.py:5565 _monitor_open, :5301 _monitor_read_recorded, :5708 _monitor_stop. Existing incompatibility currently refuses stop-first; these anchors require full inspection before design/code.
Parallel analysis before spec/design: independent RQ1 authenticated lifecycle/identity/shutdown and RQ2 CLI starter/publication/race/test seam; research reads disjoint questions/unique evidence files. PM writes phase documents serially. Coding file ownership boundaries decided after design. At initial requirements recording no worker dispatch or code edits had occurred. Subsequent research RQ1 completed and acked; RQ2 performed by PM after dispatch held. Two unintended automatic dp1 API calls from dispatch were disclosed and recorded in pm-state.md; no subsequent dispatch/model calls. See evidence/research/spec-lifecycle-20261024.md and spec-cli-20261024.md.

## §5 可复用资产
Source: .agenticdoc/_arch_snapshot.md §1.1/1.3/2. Reuse Python mw.py/mw_common file-lock/process identity primitives rather than a new coordinator; existing monitor start_lock/health/identity_matches/AttachedInstance.stop/detached starter and wait_health as verified by RQ1/RQ2. Reuse hermetic test pattern and framework advance_phase/audit_phase, not shared service operations. No new dependencies/core changes.

## §6 需规避坑点
Source: .agenticdoc/_pitfalls.md P-001/P-002/P-003/P-005/P-010/P-011/P-017/P-018. Preserve original bytes/newlines; use edit/explicit UTF-8/atomic writes, never PowerShell text round trips; never touch shared config/credentials. Test actual CLI writer of replacement opt-in/report, not hand-filled fixtures only. Phase/claim only framework tools. Keep low-level default behavior and status/stop unchanged. Full npm check only in protected snapshot if required; never apply foreign formatter output. Local complication: automatic dispatch caused two dp1 API calls, so further dispatch paused; direct PM code work only after design approval. Confirmed source gap: UI assets excluded from current compatibility fingerprint; design inclusion approved by user and implemented; see evidence/implementation-report.md.
