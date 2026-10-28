# T05 observation-seam — verification summary

All commands run by the worker in this session. Python commands run from
`packages/multi-workers` unless stated otherwise; raw stdout/stderr of every
step is in this directory (no tail).

Environment: Windows, PowerShell 5.1 host, Python 3.14.3, pytest 8.x.
No network, no paid model call, no shared service start/stop, no build, no
commit, no credential change.

## 0. Files touched

| File | Change |
|---|---|
| `packages/multi-workers/decision_points.py` | observation seam (`Observation`, `_validate_observation`, `_capture_scope`), shared pure `authorization_preview`/`_preview_of`, `_ArchiveTrace` + `_maybe_archive(trace=)`, `_DecisionCapture` (decision-end + book-snapshot), `decide_for` split into public wrapper + `_decide_for` steps 2..11, additive `DecisionOutcome` fields |
| `packages/multi-workers/decide_archive.py` | `state_digest` docstring only (narrative was wrong: canonical bytes != HTTP request bytes). No schema/validation/business change |
| `packages/multi-workers/test_decision_observation.py` | new, 30 tests |
| `decision_book.py` | **not modified** - see report (no writer/reader gap; the snapshot codec lives in `decision_points` to avoid the `decision_book` -> `decision_points` import cycle, and `check_book` stays T06's pre-submit gate) |

## 1. RED (before implementation)

```
cwd: packages/multi-workers
cmd: python -m pytest test_decision_observation.py -q
exit: 1
out: 29 failed in 0.53s   (AttributeError: module 'decision_points' has no attribute 'Observation')
log: red-pytest.txt
```

The failure is the missing API itself, not an import error of the test file: the
suite was written against the intended seam contract first.

## 2. GREEN

| # | cwd | command | exit | result | log |
|---|---|---|---|---|---|
| 1 | packages/multi-workers | `python -m pytest test_decision_observation.py -q` | 0 | `30 passed` | `green-pytest-observation.txt` |
| 2 | packages/multi-workers | **card acceptance** `python -m pytest test_decision_observation.py test_decide_run_authority.py -q` | 0 | `36 passed in 0.31s` | `green-pytest-acceptance.txt` |
| 3 | packages/multi-workers | repeat + consumers: `python -m pytest test_decision_observation.py test_decide_run_authority.py test_decision_points.py test_decide_policy.py test_decision_dashboard_contracts.py test_decision_context.py test_decision_book.py test_decide_archive.py test_decide_signoff.py test_decide_sign_auto.py test_decision_wire_store.py test_decision_wire_transport.py test_decide.py test_decide_cli.py test_decide_backends.py test_decide_dp_cli.py test_decide_report.py test_decision_roots_locks.py -q` | 0 | `873 passed in 29.99s` | `green-pytest-repeat.txt` |
| 4 | packages/multi-workers | whole package minus the credentialed e2e module: `python -m pytest -q --ignore=test_e2e_real.py -p no:cacheprovider` (credential env vars removed first) | 1 | `11 failed, 3612 passed, 1 skipped, 8 deselected in 522.34s` | `full-python-suite.txt` |
| 5 | repo root | `npx biome check --error-on-warnings .` (read-only) | 1 | `Checked 1194 files ... Found 3 warnings. Found 2 infos.` all in `packages/coding-agent/test/suite/mwoc-*.test.ts` (pre-existing baseline) | `npm-check-steps.txt` |
| 6 | repo root | `npm run check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` / `check:install-lock:coding-agent` / `npx tsgo --noEmit` / `check:browser-smoke` | 0 | each exit 0, full output | `npm-check-steps.txt` |
| 7 | repo root | `bash ./test.sh` | 1 | not runnable here: Windows has no WSL distro (`wsl.exe --list --online` message), so the sanctioned non-e2e wrapper could not execute | `non-e2e-suite.txt` |

`npm run check` was **not** executed as the single command: its first step is
`biome check --write --error-on-warnings .`, which rewrites
`packages/coding-agent/test/suite/mwoc-*.test.ts` (other sessions' uncommitted
work, outside this card's write face). The read-only equivalent plus the 6
remaining sub-steps are archived instead (same precedent as T01/T02/T02b/T02c/
T03/T04). This is not claimed as an equivalent full `npm run check`.

Test names (30 incl. the 4 parametrised preview cases): `test-names.txt`.

### 2.1 The 11 failures in the whole-package run (attribution)

None of the failing files is in this card's change set; each failure reproduces a
pre-existing or concurrent-session condition:

| Test | Cause | Evidence |
|---|---|---|
| `test_autopilot_readcap_injection::test_baseline_left_end_bound` / `::test_existing_regression_files_untouched` | pinned sha256 of `test_autopilot_dispatch.py` ≠ current file; the file is unmodified in git and untouched by this card | `full-python-suite.txt`, `git status` for that path is clean |
| `test_decision_monitor::test_history_is_fail_closed_without_a_redactor_and_redacts_with_one` | T10's monitor work landing concurrently: `decision_monitor.py` (13:28) and `test_decision_monitor.py` (13:29) were created *during* this run; pytest shows the assertion source as `???` (file rewritten mid-run) | `full-python-suite.txt`, file timestamps, both paths untracked |
| `test_autopilot_verdict_freshness::test_true_below_without_resume_stays_below` | verdict report round counter (`assert 3 in [2]`), unrelated module | `full-python-suite.txt` |
| `test_dispatch_decide_prepare::test_dp_without_required_state_fields_is_refused` | already reported by T04 as out-of-face (dispatch gate vs the new typed registry) | T04 report + `full-python-suite.txt` |
| `test_launcher::...::test_bom_historical_books_read_through_both_callsites`, `test_task_type_parity::test_bom_historical_books` | fixture `.agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md` is absent from this workspace | `full-python-suite.txt` |
| `test_mwds_t10_dispatch_run_state::test_missing_run_json_dispatches_byte_identically` | dispatched `task.md` text differs by a "恢复契约" section: `mw.py` (modified by another session, `git status M mw.py`) | `full-python-suite.txt` |
| `test_mwds_t27/t29 ... real_ts_judge` | `TypeError: argument of type 'NoneType'` - TS judge/dist not available in this run | `full-python-suite.txt` |
| `test_mwgal_t13_drift_identity::test_process_start_ms_probe` | process-start probe drift (369 s) on this host | `full-python-suite.txt` |

None of these tests imports `decision_points` / `decide_archive` /
`decision_book` directly (checked by grep), and my change set does not touch
their modules.

## 3. Mutant checks (tests are behaviour-bound, not self-certifying)

In-process mutants of the imported module (working tree untouched):
`mutant-check.py` + `mutant-pairing.txt`, `mutant-trace.txt`, `mutant-capture.txt`.

| mutant | what it removes | result |
|---|---|---|
| `pairing` | `_validate_observation` (intent/archive/scope/evidence contract) | exit 1, `2 failed, 24 passed, 4 deselected` |
| `trace` | `_ArchiveTrace.mark` (archive signal) | exit 1, `5 failed, 21 passed, 4 deselected` |
| `capture` | `_capture_scope` (scope creation/binding) | exit 1, `14 failed, 12 passed, 4 deselected` |

## 4. [VERIFY] metrics and their real source

All values below are read from the GREEN run / the ledger files the tests write;
none is self-reported. Layer: L1 (in-process fakes + real file I/O), no L2
surfaces claimed.

```
[VERIFY] VC-003: explicit_links=complete(decision-end.call_id == call-end.call_id,
          decision-end.book_ref == book-snapshot.book_ref) false_consumption=0
          pending_stages_labelled=true(archive not-attempted/skipped)
  source: test_decision_end_joins_the_real_call_end, test_book_snapshot_is_labelled_book_and_keeps_the_sent_state,
          test_decision_end_reports_created_replayed_and_skipped
[VERIFY] VC-004: internal_path=real(decide_for -> DecisionClient -> FakeBackend) executor_calls=0
          jev_evidence=absent (real Jev submission is T14; not claimed)
  source: test_observation_never_invokes_the_executor, test_disabled_dp_observation_bypasses_only_the_dp_gate
[VERIFY] VC-008: production_tree_bytes_changed=0 (sha256 of every file under the control root,
          before/after an observation) test_records=present(test wire + evidence)
          signoff_rows_sha256=not-run (no signoff fixture here; T06/T13 own the collect() hash chain)
  source: test_disabled_dp_observation_bypasses_only_the_dp_gate, test_observation_keeps_the_global_transport_switch
[VERIFY] VC-010: observe_bypass=enabled(dp gate only) executor_calls=0 production_disabled_backend_calls=0
          global_disabled_backend_calls=0 http_attempt_rows=0
  source: test_disabled_dp_observation_bypasses_only_the_dp_gate,
          test_production_path_of_the_same_disabled_dp_still_sends_nothing,
          test_observation_keeps_the_global_transport_switch, decision_wire.summarize(attempts)=0
[VERIFY] VC-011: invalid_or_missing_input_backend_calls=0 pairing_violation_rows=0
          synthetic_success=0 outcomes=explicit(escalated_reason/archive state on every row)
  source: the six observation-contract tests + test_observation_input_incomplete_sends_nothing
          + test_observation_refuses_a_broken_capture_module (importable module without the
          record_event/scope API is refused, not silently degraded)
[VERIFY] VC-017 (T05 part): capture_failure_keeps_business_result=true (status=suggested,
          capture_status=failed, channel=module-unavailable|test-scope)
  source: test_production_keeps_the_business_result_when_capture_is_unavailable,
          test_observation_capture_failure_is_reported
```

## 5. Not verified here

- Real Jev endpoint / real HTTP 429 / real timeout behaviour: T14 (manual,
  explicit) - `jev_evidence` is therefore **absent**, not "present".
- Browser/app window, monitor HTTP surface, page token: T10/T11.
- Production signoff `rows_sha256`/collect() hash chain after test submissions:
  T06/T13 (this card proves the *whole control tree* is byte-identical for an
  observation, which is the stronger local statement available without a
  signoff fixture).
- TS-side consumption of the new outcome fields (`capture_channel`,
  `archive_state`, `preview`, `snapshot_ref`, `call_id`): T09/T11.
- The 11 whole-package failures listed in §2.1 are outside this card and were
  not "fixed across the repo".
