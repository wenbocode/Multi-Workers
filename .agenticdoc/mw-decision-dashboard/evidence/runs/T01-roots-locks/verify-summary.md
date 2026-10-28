# T01 roots-locks - verification summary

Scope of this file: the T01 slice only (control-root resolver + lock deadline +
lock-owner identity helpers). It does not claim VC-007/VC-017/VC-018 as a
whole; the remaining halves belong to T02 (wire/record), T10 (monitor start /
stale recovery) and T13 (cross-root integration).

## Commands, cwd, exit codes

| # | command | cwd | exit | evidence |
|---|---|---|---|---|
| 1 | `python -m pytest test_decision_roots_locks.py -q` (RED, before implementation) | `packages/multi-workers` | 1 (`25 failed, 2 passed`) | `red-pytest.txt` |
| 2 | `python -m pytest test_decision_roots_locks.py -q` (GREEN, after implementation) | `packages/multi-workers` | 0 (`27 passed`) | `green-pytest.txt` |
| 3 | `python -m pytest test_serve_meta.py test_mwds_t10_dispatch_run_state.py test_autopilot_dispatch.py test_decision_roots_locks.py -q` | `packages/multi-workers` | 1 (`1 failed, 63 passed`) | `regression-neighbours-pytest.txt` |
| 4 | `npx biome check --error-on-warnings .` (read-only) | repo root | 1 (3 warnings / 2 infos) | `npm-check-steps.txt` |
| 5 | `npm run check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` / `check:install-lock:coding-agent` | repo root | 0 / 0 / 0 / 0 | `npm-check-steps.txt` |
| 6 | `npx tsgo --noEmit` | repo root | 0 | `npm-check-steps.txt` |
| 7 | `npm run check:browser-smoke` | repo root | 0 | `npm-check-steps.txt` |
| 8 | `python -c "import mw, launcher, mw_common"` | `packages/multi-workers` | 0 | console (see report) |
| 9 | `python -m pytest test_common_target_config.py test_mw_target.py -q` | `packages/multi-workers` | 0 (`17 passed`) | `target-config-neighbours-pytest.txt` |

## RED -> GREEN

- RED (`red-pytest.txt`): `25 failed, 2 passed` - the two failures-free tests are
  the historical `acquire_lock` behaviour (`default_message_and_release`,
  `default_retry_budget_is_unchanged`), everything new was missing/incomplete.
- GREEN (`green-pytest.txt`): `27 passed`; re-ran 3x, stable (no timing flake).

## Test names per behaviour

Resolver (AC-007 / VC-018 slice):
- `test_resolve_control_root_accepts_project_shape`
- `test_resolve_control_root_peels_agenticdoc_and_key_shapes`
- `test_resolve_control_root_accepts_relative_project`
- `test_resolve_control_root_refuses_unknown_root` (also asserts no `.agenticdoc` created)
- `test_resolve_control_root_require_control_false_reports_refused`
- `test_resolve_control_root_require_control_false_still_uses_evidence`
- `test_resolve_control_root_probes_declared_workspace_root`
- `test_resolve_control_root_does_not_guess_distant_control`
- `test_resolve_control_root_refuses_ambiguous_second_root`
- `test_resolve_control_root_refuses_nested_agenticdoc_shapes`
- `test_resolve_control_root_propagates_bad_target_config` (invalid-yaml + invalid-config)

Lock deadline / default semantics (AC-008 / VC-017 slice):
- `test_acquire_lock_default_message_and_release`
- `test_acquire_lock_default_retry_budget_is_unchanged`
- `test_acquire_lock_deadline_stops_within_budget`
- `test_acquire_lock_zero_deadline_fails_fast`
- `test_acquire_lock_deadline_success_path_is_immediate`
- `test_acquire_lock_rejects_negative_deadline`

Lock owner identity (AC-007 / VC-007 stale-recovery input):
- `test_lock_owner_state_absent_then_alive_then_absent`
- `test_write_lock_owner_requires_an_existing_lock`
- `test_lock_owner_state_dead_owner`
- `test_lock_owner_state_pid_reuse_is_unknown`
- `test_lock_owner_state_unprobeable_start_is_unknown`
- `test_lock_owner_state_legacy_empty_file_is_not_stealable`
- `test_lock_owner_state_garbage_and_unknown_schema_are_unknown`
- `test_lock_owner_state_matches_real_process_identity` (real Windows GetProcessTimes probe)
- `test_read_lock_owner_normalizes_and_rejects_noise`
- `test_lock_owner_states_constant_is_exhaustive`

## [VERIFY] metrics (T01 slice, real sources)

- [VERIFY] T01-root: project/agenticdoc/key_shapes_resolve_same_control=true
  target_probe_shallow_only=true ambiguous_refusals=2 unknown_refusals=1
  second_archive_created=0 readonly_probe_writes=0
  Source: tests `accepts_project_shape`, `peels_agenticdoc_and_key_shapes`,
  `probes_declared_workspace_root`, `does_not_guess_distant_control`,
  `refuses_ambiguous_second_root`, `refuses_nested_agenticdoc_shapes`,
  `refuses_unknown_root` (`green-pytest.txt`); real-repo probe output in report.
- [VERIFY] T01-lock: default_message_unchanged=true default_backoff_unchanged=true
  deadline_budget_enforced=true max_observed_wait_lt_2s=true
  foreign_lock_deleted=0
  Source: `green-pytest.txt` (lock deadline tests); `red-pytest.txt` shows the
  same two default tests passing before implementation (unchanged semantics).
- [VERIFY] T01-owner: owner_states=5 stealable_states=[dead-only]
  unknown_never_stealable=true legacy_never_stealable=true
  real_start_identity_match=true
  Source: `green-pytest.txt` (owner identity tests).
- Not claimed by T01: VC-007 stale-file recovery/port precedence/no-browser,
  VC-017 wire/report business-result invariance, VC-018 monitor crosstalk -
  they need T02/T10/T13 and are NOT asserted passed here.

## Environment / baseline notes

- `mwoc-*.test.ts` biome diagnostics (3 warnings, 2 infos) live in committed
  files from `a100012f7` (2026-10-15), not in T01 files: `npm run check`'s
  biome `--write` step was therefore skipped (it would edit files outside this
  task's write surface) and run read-only with `--error-on-warnings`.
- `test_mwds_t10_dispatch_run_state.py::test_missing_run_json_dispatches_byte_identically`
  fails on a dispatch-card literal; `shared/dispatch-card.ts` carries another
  session's unstaged diff (13+/7-). Out of T01 write surface - reported to PM.
