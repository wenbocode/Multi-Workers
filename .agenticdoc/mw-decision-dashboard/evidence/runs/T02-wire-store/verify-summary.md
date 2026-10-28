# T02 wire-store - verification summary

Scope: the T02 slice only - `decision_wire.py` (scope/call/context, capture,
redaction, byte/length/hash accounting, 64 KiB line budget, locked append,
read side). It does NOT claim AC-005/008/012/016 or VC-005/008/012/016/017 as a
whole: real HTTP byte comparison, the production redactor set, archive/triage/
signoff byte invariance, monitor rendering and cross-process isolation belong to
T03/T05/T06/T07/T10/T13.

## Commands, cwd, exit codes

| # | command | cwd | exit | evidence |
|---|---|---|---|---|
| 1 | `python -m pytest test_decision_wire_store.py -q` (RED, tests written first, module absent) | `packages/multi-workers` | 1 | `red-pytest.txt` |
| 2 | `python -m pytest test_decision_wire_store.py -q` (GREEN) | `packages/multi-workers` | 0 | `green-pytest.txt` |
| 3 | same command x3 (flake check) | `packages/multi-workers` | 0/0/0 | `green-pytest-repeat.txt` |
| 4 | `python -m pytest test_decision_roots_locks.py test_decide_backends.py -q` | `packages/multi-workers` | 0 | `regression-neighbours-pytest.txt` |
| 5 | `npx biome check --error-on-warnings .` (read-only, `npm run check` step 1 without `--write`) | repo root | 1 | `biome-readonly-check.txt` |
| 6 | `npm run check:pinned-deps` | repo root | 0 | `npm-check-steps.txt` |
| 7 | `npm run check:ts-imports` | repo root | 0 | `npm-check-steps.txt` |
| 8 | `npm run check:shrinkwrap` | repo root | 0 | `npm-check-steps.txt` |
| 9 | `npm run check:install-lock:coding-agent` | repo root | 0 | `npm-check-steps.txt` |
| 10 | `npx tsgo --noEmit` | repo root | 0 | `npm-check-steps.txt` |
| 11 | `npm run check:browser-smoke` | repo root | 0 | `npm-check-steps.txt` |
| 12 | `python -c "import decision_wire"` + `python -m py_compile decision_wire.py test_decision_wire_store.py` | `packages/multi-workers` | 0 | console (report) |

`npm run check` as a single command was not executed: its first step is
`biome check --write .`, which rewrites `packages/coding-agent/test/suite/mwoc-*.test.ts`
(3 warnings / 2 infos, committed in `a100012f7`, not this task) - outside this
task's write surface. All later steps were run individually (rows 6-11), and
biome was run read-only. This is the same deviation T01 recorded and reported.

## RED -> GREEN

- RED (`red-pytest.txt`): `ERROR collecting test_decision_wire_store.py` /
  `ModuleNotFoundError: No module named 'decision_wire'` - the 54 behaviour
  tests existed before any implementation file did, so nothing was collected.
- First implementation pass: 43 passed, 9 failed (console only, not archived).
  Every failure was fixed at the root, not in the tests:
  1. `WireScope(sink=None)` raised `TypeError` before validation -> explicit
     `WireScopeError` before `pathlib.Path()`.
  2. capture objects passed through `build_event` were not JSON serializable ->
     `build_event` normalises `Capture` to its dict for `request`/`response`/`book`.
  3. Windows `os.open` defaults to text mode and wrote CRLF -> added
     `O_BINARY` to both append and tail-repair opens (UTF-8 + LF only).
  4. a long line that arrived complete in one read chunk was not counted as
     `oversized_line` -> length check at consumption.
  5. `call_end_event` had no `wire_attempts` override -> added (defaults to
     `call.attempts_started`).
  Two test-side mistakes (an unrealistic truncation fixture and an invalid
  half-line JSON completion) were corrected as test bugs.
- A real gap found by review after GREEN: the 25% shrink cut in
  `serialize_event` could split a secret and persist its prefix. Fixed with a
  `scrub_tail_prefix` pass per shrink round; regression test
  `test_serialized_shrink_never_persists_a_secret_prefix` fails without it
  (the flag can only be set by that scrub).
- GREEN (`green-pytest.txt`): `54 passed`;
  `green-pytest-repeat.txt`: 54 passed three times, stable.

## Test names per behaviour (54)

Identity/scope: `test_new_call_ids_are_uuid4_hex_and_unique`,
`test_call_state_attempt_index_is_per_call`,
`test_scope_requires_explicit_sink_and_project_id`,
`test_test_scope_refuses_the_production_ledger`,
`test_test_scope_is_fail_closed_but_production_is_best_effort`,
`test_project_id_is_stable_and_path_independent`,
`test_sink_helpers_point_at_the_documented_paths`.

Context: `test_scope_and_call_context_default_to_none`,
`test_use_binds_and_resets_scope_and_call`, `test_use_resets_on_exception`,
`test_call_context_creates_a_fresh_call`,
`test_nested_use_restores_the_outer_binding`,
`test_thread_context_does_not_inherit_binding`.

Schema: `test_event_has_schema_and_common_fields`,
`test_event_rejects_unknown_kind`, `test_event_omits_unknown_fields`,
`test_attempt_event_requires_a_call_state`,
`test_transport_hook_without_a_call_is_a_silent_skip`,
`test_attempt_index_increments_per_post_not_per_call`,
`test_decision_event_uses_the_last_call_of_its_scope`,
`test_event_actor_and_answer_source_are_explicit`.

Capture: `test_capture_byte_exact_plain_text`,
`test_capture_redacts_before_truncating`,
`test_capture_counts_every_occurrence`,
`test_capture_without_redactor_omits_text_fail_closed`,
`test_capture_invalid_utf8_uses_lossless_latin1`,
`test_capture_truncates_at_the_byte_segment_cap`,
`test_capture_scrubs_a_secret_split_at_the_segment_boundary`,
`test_capture_scrubs_a_secret_split_at_the_read_boundary`,
`test_capture_of_none_is_not_recorded`,
`test_capture_hash_never_hashes_the_raw_wire_bytes`,
`test_persisted_ledger_never_contains_the_secret`.

Line budget: `test_serialized_line_shrinks_text_until_it_fits`,
`test_serialized_line_omits_text_when_metadata_alone_is_too_big`,
`test_serialized_line_falls_back_to_a_minimal_capture_failed_row`,
`test_serialized_line_keeps_cjk_unescaped_and_has_no_inner_newline`,
`test_serialized_shrink_never_persists_a_secret_prefix`.

Append: `test_append_event_writes_one_jsonl_line`,
`test_append_short_write_loop_completes_the_line`,
`test_append_fsyncs_before_releasing`,
`test_append_terminates_a_dangling_tail_without_truncating`,
`test_append_lock_timeout_is_reported_and_keeps_the_foreign_lock`,
`test_append_failure_warns_once_per_logical_call`,
`test_append_creates_parent_directories`,
`test_capture_status_distinguishes_ok_partial_and_failed`,
`test_merge_capture_status_prefers_the_worst_value`,
`test_serialize_failure_is_failed_status_not_an_exception`.

Read side: `test_read_events_missing_file_is_empty`,
`test_read_events_reports_bad_json_bad_utf8_and_unknown_schema`,
`test_read_events_reports_an_incomplete_tail_and_resumes_from_it`,
`test_read_events_skips_an_oversized_line_and_continues`,
`test_read_events_detects_rotation`,
`test_summarize_counts_calls_attempts_and_decisions`,
`test_test_scope_writes_only_its_own_sink`.

## [VERIFY] metrics (real sources = the tests above)

- [VERIFY] T02-capture: secret_occurrences_persisted=0 capture_markers_present=true
  decode_errors_marked=true sha_is_of_stored_text=true
  Source: `test_persisted_ledger_never_contains_the_secret`,
  `test_capture_redacts_before_truncating`, `test_capture_counts_every_occurrence`,
  `test_capture_without_redactor_omits_text_fail_closed`,
  `test_capture_invalid_utf8_uses_lossless_latin1`,
  `test_capture_hash_never_hashes_the_raw_wire_bytes`; `green-pytest.txt`.
- [VERIFY] T02-limits: line_cap_respected=true text_omitted_on_overflow=true
  boundary_scrubbed_on_both_cuts=true stored_len_matches_stored_text=true
  Source: the five `test_serialized_*` tests plus the two
  `test_capture_*_boundary` tests.
- [VERIFY] T02-lock: lock_budget_enforced=true foreign_lock_deleted=0
  short_write_completed=true tail_repaired_without_truncate=true fsync_called=true
  Source: `test_append_lock_timeout_is_reported_and_keeps_the_foreign_lock`
  (elapsed < 2 s, lock file still present), `test_append_short_write_loop_completes_the_line`,
  `test_append_terminates_a_dangling_tail_without_truncating`,
  `test_append_fsyncs_before_releasing`.
- [VERIFY] T02-failure: raises_into_caller=0 warnings_per_logical_call=1
  status_channels=WriteResult+capture_status
  Source: `test_append_failure_warns_once_per_logical_call`,
  `test_serialize_failure_is_failed_status_not_an_exception`,
  `test_capture_status_distinguishes_ok_partial_and_failed`.
- [VERIFY] T02-read: reader_crashes=0 bad_json=1 bad_utf8=1 unknown_schema=2
  oversized_line=1 incomplete_tail=1 rotated=1
  Source: the four `test_read_events_*` tests.
- [VERIFY] T02-counts: calls=2 attempts=3 decisions=1 lost_attempts=0
  Source: `test_summarize_counts_calls_attempts_and_decisions`,
  `test_attempt_index_increments_per_post_not_per_call`.
- [VERIFY] T02-isolation: test_rows_in_production=0 test_sink_only=true
  Source: `test_test_scope_writes_only_its_own_sink`,
  `test_test_scope_refuses_the_production_ledger`.
- NOT claimed by T02: VC-005 DOM/browser output, VC-008 real signoff/archive/
  triage byte invariance, VC-016 real HTTP boundary bytes, VC-012 duplicate
  submission zero-POST, VC-017 business-result invariance end-to-end.

## Environment / baseline notes

- Biome read-only: 3 warnings / 2 infos, all in `packages/coding-agent/test/suite/mwoc-*.test.ts`
  (committed `a100012f7`), identical to the T01 baseline; no diagnostic in any
  file this task touched.
- Other sessions were editing `decision_points.py`, `decision_book.py`,
  `decide_registry*`, `ui-bridge.ts` etc. while these check steps ran (this task
  wrote no tracked file). The `npm run check` numbers above therefore describe
  the repo tree at run time, not an isolated worktree.
- T01 reported an unrelated red on `test_mwds_t10_dispatch_run_state.py`
  caused by another session's unstaged `shared/dispatch-card.ts`; not run here
  (outside this card's command list) and not fixed.
- Neighbour regression `test_decision_roots_locks.py` + `test_decide_backends.py`:
  86 passed (lock/deadline/resolver and transport suites unaffected).
- No network, no paid model, no build, no commit, no service start/stop, no
  lockfile or credential change.
