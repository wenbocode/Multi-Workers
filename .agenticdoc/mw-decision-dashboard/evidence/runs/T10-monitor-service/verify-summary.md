# T10 monitor-service verify summary

- Card: `tasks/T10-monitor-service.md`; worker: `workers/dd-monitor-service/`
- AC slice: AC-006, AC-007, AC-015, AC-017; VC: VC-006, VC-007, VC-015, VC-018
- Host: Windows, Python 3.14.3, pytest 9.0.2. All fixtures are isolated `tmp_path`
  control roots; loopback HTTP only; no browser, no shared service, no network,
  no credentials, no production carrier written.

## Command log

| # | Command | cwd | exit | Result | Log |
|---|---|---|---:|---|---|
| RED 1 | `python -m pytest test_decision_monitor.py -q` (module absent) | packages/multi-workers | 2 | `ModuleNotFoundError: No module named 'decision_monitor'` (1 collection error) | `red-pytest-initial.txt` |
| RED 2 | same (implementation present, 4 fixture failures) | packages/multi-workers | 1 | `4 failed, 30 passed, 1 skipped` - archive free-text carrier rejected by `decide_archive` vocabulary | `green-pytest-initial.txt` |
| RED 3 | same (detail route bug) | packages/multi-workers | 1 | `2 failed, 32 passed, 1 skipped` - `_act_history_detail` deleted its own query dict (500) | `green-pytest-run2.txt` |
| RED 4 | same (dependency in flight) | packages/multi-workers | 1 | `3 failed, 34 passed, 1 skipped` - T07 `decision_history._fold_calls()` sanitizer call site mid-edit (`TypeError`), monitor correctly answers `503 history-unavailable` | `pytest-green-final-repeat.txt`, `dependency-in-flight.txt` |
| GREEN 1 | same | packages/multi-workers | 0 | `37 passed, 1 skipped` | `pytest-green-acceptance.txt` |
| GREEN 2 (repeat) | same | packages/multi-workers | 0 | `37 passed, 1 skipped` | `pytest-green-repeat2.txt` |
| Names | `python -m pytest test_decision_monitor.py -q --collect-only` | packages/multi-workers | 0 | 38 tests collected | `test-names.txt` |
| Neighbours | `python -m pytest test_decision_history.py test_decision_roots_locks.py test_decision_dashboard_contracts.py test_decision_observation.py -q` | packages/multi-workers | 0 | `228 passed` | `neighbour-pytest.txt` |
| Re-run after T07 changed again | `python -m pytest test_decision_monitor.py -q` | packages/multi-workers | 0 | `37 passed, 1 skipped` at `decision_history.py sha256=3CA7ACEB...` | `dependency-hash-at-green.txt` |
| Check | `npx biome check --error-on-warnings .` (read-only substitute for `npm run check` step 1) | repo root | 1 | `Checked 1194 files. No fixes applied. Found 3 warnings. Found 2 infos.` all in other sessions' `packages/coding-agent/test/suite/mwoc-*.test.ts` | `check-biome-readonly.txt` |
| Check | `npm run check:pinned-deps` | repo root | 0 | pass | `check-pinned-deps.txt` |
| Check | `npm run check:ts-imports` | repo root | 0 | pass | `check-ts-imports.txt` |
| Check | `npm run check:shrinkwrap` | repo root | 0 | pass | `check-shrinkwrap.txt` |
| Check | `npm run check:install-lock:coding-agent` | repo root | 0 | pass | `check-install-lock.txt` |
| Check | `npx tsgo --noEmit` | repo root | 0 | pass | `check-tsgo.txt` |
| Check | `npm run check:browser-smoke` | repo root | 0 | pass | `check-browser-smoke.txt` |
| Isolation | `git status` + repo `.mw` glob + `netstat` LISTENING scan | repo root | 0 | only the two allowed new files; no `decide-monitor*` under repo `.mw`; no LISTENING socket in 43170..43269 | `isolation-check.txt` |

Deviation: `npm run check` step 1 is `biome check --write .`, which rewrites
tracked test files owned by other sessions (`mwoc-*.test.ts`). Ran it read-only
(no `--write`) and left the full-output `npm run check` to T15, matching the
T02b/T03/T07 precedent. Per-sub-step exit codes are in `check-exit-codes.txt`.
The dependency snapshot used for the green acceptance run:
`decision_history.py sha256 = CE294BF53FCA4B36C8A47C5102167280FAC665E6686C168656F3182C33D63DA2`
(recorded in `dependency-hash-at-green.txt`; T07's own suite was 39 passed at
that moment). T07 changed the file once more during this card
(`3CA7ACEBE66296C22750639B915EB801D6346FE2159C91E830FD4E6FDE9B904E`) and the
monitor suite stayed green (`37 passed, 1 skipped`, exit 0).

## [VERIFY] metrics and their real sources

| Metric | Value | Producing test / assertion |
|---|---|---|
| port_candidates == 100, in 43170..43269, deterministic | pass | `test_port_candidates_are_deterministic_and_in_range` |
| bind_and_hold skips the held port (no probe-then-release) | pass | `test_bind_holds_first_free_candidate_and_skips_occupied` |
| unrelated_kills = 0 on range exhaustion (`range-exhausted`) | pass (occupant still accepts a connection, socket fd valid) | `test_full_range_exhaustion_fails_without_touching_the_occupant` |
| exclusive bind: a second `SO_REUSEADDR` binder is refused | pass | `test_listener_is_exclusive_against_a_reuseaddr_rebinder` |
| state json carries identity only; control token never in it | pass | `test_state_file_holds_identity_only_and_secret_stays_separate` |
| POSIX secret mode 0600 | skipped on Windows (1 skip) | `test_secret_file_is_owner_only_on_posix` |
| boot code: single use, 60s TTL, exact Origin | pass | `test_bootstrap_is_single_use_origin_bound_and_expires` |
| long-term secret occurrences in URL/argv = 0; code only in fragment | pass | `test_window_url_keeps_the_boot_code_in_the_fragment_only` |
| page token cannot shutdown/mint code; control token cannot use page routes | pass (`wrong-role`) | `test_page_token_cannot_shutdown_or_mint_a_new_code`, `test_control_token_cannot_use_page_routes` |
| control-only re-open mints a fresh single-use code | pass | `test_control_token_can_mint_a_fresh_single_use_window_code` |
| Host closed set (exact `127.0.0.1:<port>`) | pass (`host-not-allowed`) | `test_host_header_must_be_exact_loopback_and_port` |
| Origin + Sec-Fetch-Site closed sets | pass (`origin-not-allowed`, `cross-site-blocked`) | `test_sec_fetch_site_closed_set_and_origin_rules` |
| no CORS / no Set-Cookie; CSP/nosniff/no-referrer/no-store present | pass | `test_no_cors_no_cookies_and_security_headers` |
| body cap 256 KiB (413 before read), chunked refused (400) | pass | `test_body_limit_and_chunked_rejection` |
| closed route set; no act/file route; wrong method 405 | pass (404/405) | `test_unknown_routes_and_wrong_methods_are_rejected` |
| authenticated shutdown control-only and actually stops | pass | `test_shutdown_is_control_only_and_really_stops_the_instance` |
| F-1 capture disabled vs module unavailable are distinct | pass (`disabled` / `unavailable`) | `test_capture_disabled_and_capture_module_unavailable_are_distinct` |
| history free text fail-closed with no redactor; redacted+marked with one | pass | `test_history_is_fail_closed_without_a_redactor_and_redacts_with_one` |
| F-4 per-row capture_status kept, envelope = worst | pass (`failed` row, `ok` row, envelope `failed`) | `test_history_filters_and_per_row_capture_status_with_worst_envelope` |
| opaque-id-only history detail (no path/raw id routing) | pass (404) | `test_history_detail_is_opaque_id_only` |
| playground unavailable without T06 provider, zero calls | pass (`playground-unavailable`) | `test_playground_routes_are_unavailable_without_a_provider` |
| playground closed before any provider call when no redactor | pass (`playground-redactor-unavailable`, spy empty) | `test_playground_requires_the_redactor_before_any_provider_call` |
| submit closed keys; act/executor/authority fields refused, zero calls | pass (`forbidden-field` / `unknown-field` / `invalid-field` / `missing-field`) | `test_submit_is_closed_set_and_refuses_execution_or_authorization_fields` |
| passive routes never reach submit (open/health/poll/history/dps/scaffold/validate) | pass | `test_passive_routes_never_reach_submit` |
| `/api/dps` is read-only (25 dps, effective enabled/mode, transport unknown) | pass | `test_dps_route_is_read_only_registry_and_authorization` |
| two projects: ports/tokens/identity separate, stop A leaves B healthy | pass (project_crosstalk = 0) | `test_two_projects_keep_identity_tokens_and_ports_separate` |
| reuse a healthy instance without rewriting state/secret | pass | `test_ensure_instance_reuses_a_healthy_instance_without_rewriting_state` |
| start-lock conflict keeps state + emits recovery guide | pass | `test_start_lock_conflict_keeps_state_and_reports_a_recovery_guide` |
| dead lock owner moved aside (never deleted) | pass | `test_dead_start_lock_owner_is_moved_aside_not_deleted` |
| stale state then secret moved stepwise, old bytes preserved | pass (`moved == ["state","secret"]`) | `test_stale_state_and_secret_are_moved_stepwise_after_proven_death` |
| foreign-project state refused, nothing moved | pass (`incompatible-instance`) | `test_foreign_project_state_is_a_conflict_and_is_not_moved` |
| alive-but-unhealthy instance kept, state/secret unchanged | pass (`instance-unresponsive` + guide) | `test_alive_but_unhealthy_instance_is_kept_with_a_guide` |
| malformed state and recycled PID are unknown, untouched | pass (`instance-unknown`) | `test_malformed_and_pid_reuse_state_stay_unknown_and_untouched` |
| protocol/code identity conflict does not replace a live instance | pass (`incompatible-instance`) | `test_incompatible_protocol_or_code_identity_is_a_conflict` |
| browser absence is explicit; spawn failure never claims a window | pass | `test_detect_browser_absent_reports_an_explicit_reason`, `test_launch_app_window_reports_failures_without_claiming_a_window` |

## AC/VC coverage of this slice (not the campaign-level closure)

- AC-006 / VC-006: loopback-only listener, 43170..43269 port choice, health
  identity, argv/URL contract and explicit no-browser failure are proven at
  L1/L2 (loopback HTTP + argv). The *real* Chrome/Edge app window and its two
  tabs remain T12/T14 + the dashboard assets (T11); not claimed here.
- AC-007 / VC-007: occupied port, all-occupied range, reuse, crash recovery
  (dead owner state/secret + dead start lock), unknown/PID-reuse/foreign-project
  refusals, and two-project isolation are proven. Real OS-level crash/TIME_WAIT
  behaviour on a shared machine and the browser fallback UI remain T14.
- AC-015 / VC-015: bad Host/Origin/Sec-Fetch-Site/token/role, boot replay,
  oversized and chunked bodies, act/executor smuggling, and passive zero-call
  paths are proven with real HTTP requests; DOM/XSS evidence belongs to T11.
- AC-017 / VC-001/015: no act route exists, submit refuses execution and
  authorization fields before any provider call, authorization table is never
  written by this module. The window/CLI entry refusal itself is T12.

## Residual / not verified

- T06 playground is only a seam (signatures + zero-call fail-closed); no real
  submission, dedupe or wire capture is wired here.
- T08 CLI (`mw decide monitor [status|stop]`) and T12 window entry are not
  implemented; `ensure_instance`'s subprocess `starter` and `serve()` are ready
  for them.
- History HTML rendering, CSP-in-browser evidence and the two tabs are T11.
- Real Jev/model calls: none, by design (zero paid calls in this card).
- `npm run check` was run as read-only subtests (see deviation); full-output run
  is T15's.
- `decision_history.py` changed twice during verification (concurrent T07
  hardening). The final green run pins its hash; the monitor adapts to the new
  `load_history(..., redact=...)` contract instead of duplicating redaction.
