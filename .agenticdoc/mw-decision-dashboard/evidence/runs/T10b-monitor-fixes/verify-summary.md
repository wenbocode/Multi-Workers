# T10b verify summary - finding -> fix -> test -> evidence -> remaining

All assertions below are real test assertions in `test_decision_monitor.py` (52 passed + 1 POSIX-only
skip) unless marked otherwise. Logs live next to this file.

## P1 (review P1-1) stale recovery requires a real ECONNREFUSED

Fix: `probe_recorded_port` / `classify_connect_error` / `REFUSED_ERRNOS` (POSIX `ECONNREFUSED` and
Windows `WSAECONNREFUSED`/10061). `recover_stale` now requires all three conditions under the
verified start-lock guard: provably dead PID + explicit refusal on the recorded port + a lock-internal
identity re-read. A timeout, a permission/other error, or a *successful* connection (an unrelated
listener) is `instance-unknown` and keeps state+secret with the manual guide.
Tests: `test_probe_recorded_port_reports_a_real_refusal_and_maps_windows_code`,
`test_recover_stale_keeps_state_when_the_recorded_port_serves_another_process`,
`test_recover_stale_keeps_state_when_the_port_probe_is_inconclusive`,
`test_stale_state_and_secret_are_moved_stepwise_after_proven_death`.
[VERIFY] probe_refused=real-loopback errno=10061 elapsed=2.06s; unrelated_listener->connected and
occupant still reachable; unknown/raising probe -> state+secret preserved; recovery report carries
{"liveness":"dead","port_probe":{"result":"refused",...}} and no token/body.
Remaining: real crash/TIME_WAIT and non-Windows hosts not exercised; the RST arrives after ~2 s on
this Windows box, so `PROBE_TIMEOUT_S=3.0` (a shorter timeout would conservatively return unknown).
Harness note: the unrelated-listener fixture uses backlog 16 because the monitor's own probe connection
fills a backlog of 1, which made the test's connect-back assertion time out (test-only adjustment, no
assertion weakened).

## P2-1 nested book execution/authorization smuggling

Fix: `_book_state_scope` builds the dp's registered state paths from `decision_points`
(required+optional+structural, declared `object` subtrees free) and `_smuggled_book_paths` refuses
forbidden key names only outside those typed paths, at any nesting level; unknown `dp` is refused
before any provider call. `PLAYGROUND_PROVIDER_OBLIGATIONS` and the `_act_submit`/`MonitorDeps`
docstrings pin T06's mandatory `decision_book.check_book` duties (closed set/types/enums/placeholder/
evidence/budget/secret).
Tests: `test_submit_refuses_nested_execution_fields_before_any_provider_call` (state field, deep
state field, context slot, envelope; `spy.calls == []`),
`test_submit_accepts_registered_typed_fields_whose_names_look_forbidden` (dp12 `action.command`,
dp24 `project.path`, dp1 `history` subtree -> 200, three provider calls),
`test_submit_refuses_an_unregistered_dp_before_any_provider_call`,
`test_playground_seam_declares_the_provider_book_obligations`.
Remaining: the monitor does not run `check_book` itself (provider/T06 owns it); `/api/test/validate`
still forwards the book (only submit is the execution-adjacent route) - flagged for PM if broader
early refusal is wanted.

## P2-2 report metadata correction

Fix: new `report-corrections.md` records 1830/1267 (original) vs 2090/1433 (review) vs measured
2089/1432 at baseline and 2535/1863 after this card, plus the corrected range/window/stale metrics.
The original T10 report is not overwritten. POSIX 0600 skip retained.
Remaining: none for this card; PM must sync any citation of the old numbers.

## P2-3 real 100-port exhaustion

Fix: test-only (the loop already attempted all candidates). New
`test_full_100_port_isolated_range_exhaustion_leaves_every_occupant_alive` holds a full contiguous
100-port local block outside the monitor range, asserts `range-exhausted` with
`attempted_count == 100` (echo 20), then connects to all 100 occupants. The old single-port test is
renamed honestly.
[VERIFY] block 25101..25200, attempted_count=100, occupants accepting=100, sockets open=100
(`probe-observations.txt`). If a block is occupied the helper leaves the occupiers untouched and
tries another block (skip with a recorded list only if none is free).

## P2-4 AttachedInstance.stop silent failure

Fix: `AttachedInstance.stop()` returns
`{"stopped","detail","port","instance_id","port_probe","state"}`; `stopped=True` only when the port
provably refuses afterwards. A refused request or an inconclusive probe returns `stopped=False` with
`detail`; nothing is killed and state/secret are never deleted (state="retained" is reported).
Tests: `test_attached_stop_reports_a_refusal_instead_of_silent_success` (wrong token -> stopped False,
detail contains "refused", live instance healthy, state+secret intact),
`test_attached_stop_reports_success_and_leaves_no_state`.
Remaining: T08 CLI must consume the new dict (API change listed in report).

## P2-5 recover_stale lock discipline

Fix: `start_lock` yields a `StartLockGuard` (pid+start_ms+path); `recover_stale(guard=...)` verifies
it before the decision and again before each move. A bare call acquires and releases the lock itself.
After the state move the state is re-read (a new state -> abort with `moved=["state"]`,
`secret_preserved=True`) and the secret's file identity (inode/size/mtime) is compared (a rewritten
secret -> abort, preserved). No new secret is ever moved.
Tests: `test_recover_stale_bare_call_takes_and_releases_the_start_lock`,
`test_recover_stale_runs_under_a_verified_guard`,
`test_recover_stale_refuses_a_guard_whose_lock_was_lost` (nothing moved),
`test_recover_stale_never_moves_a_fresh_secret_published_after_the_state_move`
(monkeypatched publisher after the state move; fresh state+secret intact).
Remaining: a bare `recover_stale` called while *already holding* the lock without a guard now fails
loudly (`start-lock-conflict`) by design; T08 must pass the guard.

## P2-6 window result semantics

Fix: `launch_app_window` returns `spawned` + `visibility` (`not-verified` when the spawner returned,
`not-opened` on failure); `ok` is removed. Docstring says spawned=True never proves a visible window.
Tests: `test_detect_browser_absent_reports_an_explicit_reason`,
`test_launch_app_window_reports_failures_without_claiming_a_window` (asserts `"ok" not in result`).
Remaining: real Chrome/Edge window + 2 tabs stays VC-006/T12/T14; no browser is started by tests.

## Joint history API re-verification

Test: `test_history_read_side_contract_is_jointly_verified_with_current_history_api` reads the
current `decision_history.load_history(..., redact=...)`: with a redactor every record has
`enabled` marks and substitutions; with `redact=None` marks are disabled and omission/drop counters
are non-zero; the monitor `/api/history` summary counts match the marks and the secret never appears.
No history file was modified by this card. T07b was in flight; hashes and the one transient
T07b-owned failure are recorded in `dependency-history-inflight.txt`.
