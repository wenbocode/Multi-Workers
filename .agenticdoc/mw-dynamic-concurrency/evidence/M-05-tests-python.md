# M-05-tests-python — evidence (MDC B3, Python half: VC-101 / VC-102 / VC-103 / VC-104)

Key `mw-dynamic-concurrency`, card `T-C-M05-tests-python`. Added tests only, no
production code touched. Single code write face:
`packages/multi-workers/test_mdc_concurrency.py` (523 lines, 10 named tests).

Every case drives the real `conductor.tick` → `execute_loop` path and reads the
**measured** dispatch count out of the real queue file through
`mw_common.parse_workers_file`. The expected value is never re-derived with
`autopilot.task_graph.frontier` (that would be circular self-validation); it
comes from the deliberately constructed corpus shape (N independent dep-free
tasks ⇒ N; a chain head ⇒ 1; M eligible keys ⇒ M) and the measurement is
whatever the queue file actually holds.

Observation points (all real files, no private state):

- dispatch rows → `.agenticdoc/_workers.parallel`. Note: the real single queue
  file is `.agenticdoc/_workers.parallel` (`mw_common.workers_path`,
  `mw_common.py:1716-1717`), not a per-key file; `mw_common.parse_workers_file`
  is the reader the conductor itself uses, and rows are filtered to the
  `ap-<key>-` identity.
- audit lines → `.agenticdoc/_autopilot/timeline.jsonl`: `config` events with
  the "task graph unusable" alarm (`_audit_task_graph_problems` /
  `_emit_alarm`), or the WFG `write-face-undeclared` / `write-face-overlap`
  events.
- stall guard → absence of a `stalled` timeline event.
- key status → the `> key-status:` line of
  `.agenticdoc/_autopilot/_roadmap.md`.
- `advance.advance` is the only injected seam (a no-op returning exit 0) so the
  tests never spawn the real phase subprocess.

## ① Raw pytest output + explicit file arguments (P-032)

### Command A — the new file alone

```text
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q test_mdc_concurrency.py
```

Raw output (complete), exit code **0** (`$LASTEXITCODE=0`):

```text
..........                                                               [100%]
10 passed in 0.52s
```

### Command B — `-q -s -v`, the measured lines behind each assertion

```text
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q -s -v test_mdc_concurrency.py
```

Raw output (complete), exit code **0**:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: H:\git\Multi-Workers\packages\multi-workers
configfile: pytest.ini
plugins: anyio-4.12.1, Faker-40.13.0, respx-0.23.1
collected 10 items

test_mdc_concurrency.py::test_vc101_per_key_cap_above_frontier [VERIFY] VC-101a: corpus=3 independent dep-free tasks per_key_bound=4 measured_tick1=3 measured_tick2_new=0
PASSED
test_mdc_concurrency.py::test_vc101_per_key_bound_truncates_each_tick [VERIFY] VC-101b: corpus=5 independent dep-free tasks per_key_bound=2 measured_tick1=2 measured_tick2_new=2
PASSED
test_mdc_concurrency.py::test_vc101_per_key_chain_starts_one_per_tick [VERIFY] VC-101c: corpus=chain T-2 deps T-1 per_key_bound=4 measured_tick3_new=1 new=['ap-k1-T-2']
PASSED
test_mdc_concurrency.py::test_vc101_key_layer_min_bound_frontier [VERIFY] VC-101d: corpus=3 eligible keys measured={1: 1, 2: 2, 8: 3}
PASSED
test_mdc_concurrency.py::test_vc102_chain_frontier_not_amplified [VERIFY] VC-102: corpus=chain T-2 deps T-1 measured={8: 1, 4: 1}
PASSED
test_mdc_concurrency.py::test_vc103_bound_one_serial_same_process_no_restart [VERIFY] VC-103: wide_keys=2 wide_per_key=4 narrow_new_rows=1 narrow_new_keys=1 same_process=True
PASSED
test_mdc_concurrency.py::test_vc104_dangling_dep_serial_fallback_audited [VERIFY] VC-104a: case=dangling dep rows_tick1=1 audit_lines=1
PASSED
test_mdc_concurrency.py::test_vc104_dependency_cycle_serial_fallback_audited [VERIFY] VC-104b: case=dependency cycle rows_tick1=1 audit_lines=1
PASSED
test_mdc_concurrency.py::test_vc104_undeclared_write_face_serial_only_audited [VERIFY] VC-104c: case=undeclared write face per_key_bound=4 rows_tick1=1 audit_lines=1
PASSED
test_mdc_concurrency.py::test_vc104_overlapping_write_face_refused_without_stall [VERIFY] VC-104d: case=overlapping write faces rows_tick1=1 overlap_events=1 stalled_events=0 key_status=running
PASSED

============================= 10 passed in 0.51s ==============================
```

(The `[conductor] task graph unusable for k1: ...` lines on stderr in the VC-104
cases are the `_emit_alarm` stderr leg of the audit — expected.)

### Command C — full `python -m pytest -q`

```text
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q
```

Raw tail, exit code **1**:

```text
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable
FAILED test_task_type_parity.py::test_bom_historical_books - AssertionError: ...
7 failed, 2215 passed, 10 deselected, 2 warnings in 407.89s (0:06:47)
```

### Baseline comparison

| run | failed | passed | deselected |
|-----|--------|--------|------------|
| card baseline | 6 | 2206 | 10 |
| this run | 7 | 2215 | 10 |

- Collected total grew by exactly the 10 new tests (2222 → 2232).
- Of the 10 new tests: **10 pass, 0 fail**.
- Among the pre-existing tests the totals are 2205 pass / 7 fail, i.e. exactly
  one test flipped pass → fail versus the baseline. That one is
  `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` (see ⑦).
- The other 6 red are the baseline's known external reds: E2Feature
  `verdict_freshness` (1), missing other-key task books `test_launcher` +
  `test_task_type_parity` (2), TS subprocess runner flakiness
  `test_mwds_t27` + `test_mwds_t29` (2), `test_rag_launcher` (1).

## ② VC-101 — frontier identity, started = min(layer bound, |frontier|)

Four corpora, each one project, each measured from
`.agenticdoc/_workers.parallel` immediately after `conductor.tick`:

| case | corpus | layer | bound | `|frontier|` by construction | measured |
|------|--------|-------|-------|------------------------------|----------|
| 101a | 3 independent dep-free tasks, disjoint faces | per-key | 4 | 3 | 3 rows; 2nd tick +0 |
| 101b | 5 independent dep-free tasks, disjoint faces | per-key | 2 | 5 | tick1 2 rows; after 2 done tick2 +2 |
| 101c | chain `T-2 deps T-1` | per-key | 4 | 1 | 1 row; +0 while T-1 in flight; +1 (`T-2`) after T-1 done |
| 101d | 3 eligible dep-free keys | key | 1 / 2 / 8 | 3 | 1 / 2 / 3 keys |

- 101a: after the head tick, all three tasks are in flight ⇒ the next tick's
  frontier is empty and the queue file gains no row (`measured_tick2_new=0`).
- 101b: the per-key bound truncates each tick (2), and after two rows are set
  `done` the next tick starts the next 2 — the bound is recomputed per tick.
- 101c: proves the chain head is the only startable task (bound 4 does not
  amplify), and consumption advances the frontier once the head is terminal.
- 101d: the key layer is measured as the set of `ap-` owners that gained rows;
  `max_parallel_keys` ∈ {1,2,8} gives {1,2,3} against 3 eligible keys.

The expected values come from the corpus sizes above — never from calling
`task_graph.frontier` in the test.

## ③ VC-102 — narrow frontier is not amplified

`test_vc102_chain_frontier_not_amplified`: chain `T-2 deps T-1`, two separate
projects with `max_workers_per_key` = 8 and 4 (key bound 8 in both). Both
measured exactly 1 row; a second tick with the head still in flight adds
nothing. `[VERIFY] VC-102: ... measured={8: 1, 4: 1}`.

## ④ VC-103 — bound = 1 is serial, hot config read, no restart

One project, one `ConductorState` (hence one process) for both ticks:

1. `max_parallel_keys=8`, `max_workers_per_key=4`, 2 keys × 6 independent
   tasks each ⇒ measured 2 keys, 4 rows in `k1` (`wide_keys=2 wide_per_key=4`).
2. All 8 rows are set `done` (so in-flight state cannot mask the next tick),
   then **only `.agenticdoc/_autopilot/config.json` is rewritten** to
   `max_parallel_keys=1` + `max_workers_per_key=1`.
3. The same `st` ticks again: `narrow_new_rows=1 narrow_new_keys=1` — at most
   one task (per-key layer) and one key (key layer) started, proving
   `_load_effective_config` re-reads the file every tick with no serve restart.

## ⑤ VC-104 — fail-closed, serial + audit, overlap never stalls

| case | corpus | measured rows | audit | stall |
|------|--------|---------------|-------|-------|
| 104a dangling | `T-2 deps T-99-missing` (+ `T-1` dep-free), bound 4 | 1 | 1 `config` "task graph unusable … deps-dangling:T-2@3:T-99-missing" | none |
| 104b cycle | `T-1 deps T-2`, `T-2 deps T-1`, bound 4 | 1 | 1 `config` "… deps-cycle:T-1@3:T-2" | none |
| 104c undeclared face | 3 cards with no `## 写入允许面`, bound 4 | 1 | 1 `write-face-undeclared` | none |
| 104d overlap | `T-1 src/shared/**`, `T-2 src/shared/deep/**`, bound 4 | 1 (`T-1`) | 1 `write-face-overlap` | **0** (`stalled_events=0`, key-status `running`) |

- 104a also shows no permanent lock: after `T-1` is `done`, the next tick starts
  `T-2` (rows 1 → 2) while the audit line stays at exactly 1 (per-problem
  dedup) — `audit_lines=1`.
- 104d asserts the refused second dispatch leaves no row and, crucially, that
  `execute_loop` treats the write-face refusal as "wait for the next tick":
  no `stalled` timeline event and the roadmap `key-status` stays `running`.

## ⑥ New test count = file line distribution

`packages/multi-workers/test_mdc_concurrency.py`: 523 lines total, 10 named
test functions (no test covers more than one VC):

| test function | start line | lines |
|---------------|-----------|-------|
| `test_vc101_per_key_cap_above_frontier` | 210 | 35 |
| `test_vc101_per_key_bound_truncates_each_tick` | 245 | 36 |
| `test_vc101_per_key_chain_starts_one_per_tick` | 281 | 35 |
| `test_vc101_key_layer_min_bound_frontier` | 316 | 27 |
| `test_vc102_chain_frontier_not_amplified` | 343 | 28 |
| `test_vc103_bound_one_serial_same_process_no_restart` | 371 | 48 |
| `test_vc104_dangling_dep_serial_fallback_audited` | 419 | 29 |
| `test_vc104_dependency_cycle_serial_fallback_audited` | 448 | 20 |
| `test_vc104_undeclared_write_face_serial_only_audited` | 468 | 26 |
| `test_vc104_overlapping_write_face_refused_without_stall` | 494 | 30 |

VC split: VC-101 ×4, VC-102 ×1, VC-103 ×1, VC-104 ×4. The remaining ~175 lines
are the module docstring + shared harness (`_project`, `_roadmap`, `_card`,
`_set_bounds`, `_noop_advance`, `_state`, queue/timeline/roadmap readers).

## ⑦ The one extra full-suite failure is parallel work, not this card

`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` fails in
isolation too:

```text
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q test_autopilot_readcap_injection.py::test_baseline_left_end_bound
```

```text
>       assert frozen == git_blob
E       AssertionError: assert '219ed8090210...e9bd66bc8610a' == '960cceec5c70...1b8dc2d05ec36'
```

The assertion compares a frozen external copy
(`H:\git\E2Feature\.agenticdoc\...\baseline_20260924\dispatch.head.py`, via
`MW_READCAP_BASELINE_DIR`) against `git show HEAD:packages/multi-workers/autopilot/dispatch.py`.
It is outside this card's write face and fails before `test_mdc_concurrency.py`
is even collected (alphabetical collection order `test_autopilot_*` <
`test_mdc_*`). The in-flight parallel cards are exactly on that seam:
`git diff --stat` shows `autopilot/dispatch.py` (+430 lines, MDC M-04
identity-dedup) and `test_autopilot_readcap_injection.py` (9 lines) modified in
the working tree. No production code was changed to accommodate it.

## ⑧ Write face / exclusions

- Written: `packages/multi-workers/test_mdc_concurrency.py` (new),
  `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-python.md` (this file).
- Not touched: any production code (`autopilot/**`, `mw_common.py`, `mw.py`,
  `launcher.py`), any existing test file, the frozen corpus JSON under
  `test/fixtures/`, all `packages/coding-agent/**` and `dist/**`.
- No `pytest.mark.skip` / `xfail` / `only`; no existing assertion relaxed or
  removed; no unfiled-argument pytest (P-032); no `npm run check` (P-017); no
  git write operation; no temp probe script left behind.
