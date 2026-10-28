# T10 R2 stage D - AC052 replay repair (local product delivery, NOT verified)

## 结论

Local product delivery only. The single true-red item this round is the PM's own
AC052 replay probe (1 failed, rc=1 in
`rework-r2/pm-postfix-tests/runs/t10-r2-replay-probe-first/`): an `executed`
event that is already recorded cannot be replayed after a later `settled`,
because `record_lifecycle` ran the recorded-`task_after` floor precheck before
the append, and `append_event` ran the caller `guard` before the in-lock
`event_id` dedupe scan. Both orders are repaired:

* `decision_wire.append_event` now answers an already recorded `event_id` as
  `duplicate` (zero bytes, no guard, no failure sidecar) inside the same append
  lock, before the guard, and still guards every event that is really appended;
* `decision_lifecycle.record_lifecycle` keeps the fail-fast floor precheck for a
  **new/unknown** `event_id` and stands aside only when that exact `event_id` is
  already in the ledger; the authoritative judgment (dedupe first, then the same
  floor comparison as the in-lock guard) is unchanged.

`event_id` is the only duplicate key: no content equality, no global
`decision_id` uniqueness, no single-terminal rule, no `decision.py` or test
change. This is **not** a PASS, not "postfix green", not a T10 handoff, not
S2/QG/signoff. I did not run pytest, collection, any product/test/runner import,
any generator/service/CLI/HTTP call, and I wrote no OS fixture, `%TEMP%`, live
ledger or copy: every new artifact below was produced by an explicit editor
write into this role's evidence face, and all verification is `python -B` pure
AST/text on bytes.

## 证据

### Before / after (canonical paths, bytes and SHA256)

| 文件 | before bytes | before SHA256 | after bytes | after SHA256 | diff |
| --- | --- | --- | --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py` | 82286 | `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc` | 83177 (+891, docstring + reorder) | `03f4373f6328b05d5abedd5d686dda3b155b08436908beb8f6d29585dcf0639c` | `rework-r2/replay-repair/diff/decision_wire.py.diff` |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py` | 65501 | `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5` | 67575 (+2074, precheck split) | `2ab3ac15d80e2f90987366a380d376fde17482917759d40d5dd07d5b427244a2` | `rework-r2/replay-repair/diff/decision_lifecycle.py.diff` |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py` | 3871 | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` | 3871 (no change) | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` | `rework-r2/replay-repair/diff/decision_task_state.py.diff` |

The before bytes are the byte-exact `product-repair/after-bytes/` copies left by
stage B: their SHAs equal the card's declared before SHAs and the PM fresh-before
record (`t10-r2-green-replay-disposition-20261028/check.json`), verified by
`checks/baseline_verify.stdout.json` (`equal_to_declared: true` for all three).
Before the first edit I re-hashed the three worktree products in this session and
they matched those same three SHAs, so the copies are this round's before state; I
added no new copy because for this role every OS write (including `Copy-Item`) is
forbidden. Both assigned suites are byte-identical to their protected digests
(`1bca28c5...e6ae9`, `30c6e4dd...d23f`, 65105 / 15480 bytes) before and after.

Read to actual EOF before editing (AST parse requires the whole file): the three
products (82286 / 65501 / 3871 bytes), both suites (65105 / 15480 bytes), this
card, the original `tasks/isolated/T10-lifecycle-state.md` (AC-050/AC-052 text),
the PM's `check.json`, the four PM postfix run directories (report/stdout/meta) and
the stage-C boundary suite. The PM probe is 1 failed / rc=1 with the failing frame
`record_lifecycle -> _recorded_after_floor -> LifecycleInputError: task after
observation precedes task before observation`
(`runs/t10-r2-replay-probe-first/pytest-replay.stdout`), after two real green
130-passed + focus-14-passed runs of the same bytes; I did not re-run any of them.

### Exact lock-internal order (code, not observation)

`decision_wire.append_event` (one `mw_common.acquire_lock`, no second lock, no
second ledger):

1. `serialize_event` + `sink.parent.mkdir` (unchanged, outside the lock);
2. `mw_common.acquire_lock(O_CREAT|O_EXCL, budget=0.25s, retries=5)`;
3. **dedupe scan** `_event_id_present(sink, event_id)`; on a hit:
   `scope._record_write(None)` and `WriteResult(status="duplicate",
   event_id=<same>)` — zero bytes, no tail repair, no guard call, no sidecar;
4. on a miss: `guard()` = `_recorded_after_floor` -> `_ledger_facts` (creation
   association + damaged-ledger refusal) -> `_refuse_preceding_after` (creation
   before + every prior `task_after` of the same `logical_id`); a refusal raises
   `LifecycleInputError`, which propagates through `_append` unchanged and writes
   no sidecar;
5. `_terminate_dangling_tail`, `os.open(O_WRONLY|O_CREAT|O_APPEND)`, short-write
   loop, `fsync`;
6. `finally: release_lock(lock)` on every path (duplicate and refusal included).

`decision_lifecycle.record_lifecycle` (outside the lock, fast path only): after
`validate_task_state` / `validate_observation_order(meta.task_before, task_after)`
it reads `_ledger_facts` and calls `_event_is_recorded(events, event_id)`; the
floor `_refuse_preceding_after` runs only when that id is **not** recorded. A new
or unknown id therefore keeps today's fail-fast `LifecycleInputError` with zero
bytes and no lock spent, and the same check is re-run inside the lock as the
guard, so a newer observation recorded between precheck and append is still
refused (no read-before-write TOCTOU: both final decisions — dedupe hit, floor
for a new id — are taken on the locked bytes).

### Why this is exactly the AC052 repair and nothing more

* A replay of a recorded `event_id` appends nothing, so its `task_after` is not a
  new observation: the floor does not apply, and the answer is the original
  recorded fact (`duplicate`, `recorded=True`, same `event_id`, zero bytes, no
  overwrite, no `<ledger>-errors.jsonl` row, no leftover `.lock`).
* A new/unknown `event_id` with an older `task_after` still fails closed: the
  precheck raises before the lock, and if it passed the race the in-lock guard
  raises with zero bytes (stage-C's two-writer control).
* The duplicate short-circuit keys on `_event_id_of(row) == event_id` only —
  `same_snapshot`, content equality and any global id rule are absent from the
  new helper; `_refuse_preceding_after` still validates every prior snapshot and
  skips other `logical_id`s.
* Association/before legality, secret boundary, metadata `null != []` and order,
  legal new-observation writes, failed-round `locked`/`lock-timeout` semantics and
  lock release are untouched: the AST-level definition diff is
  `append_event` (wire), `_recorded_after_floor` + `record_lifecycle`
  (lifecycle), plus the new `_event_is_recorded` / `_refuse_preceding_after`; every
  other definition, `record_terminal`, `record_request`, `record_note`,
  `record_start`, `_check_before`, `_check_parent_ref` and `_guard_secret` is
  AST-identical to the before bytes.

### Static verification actually executed (the only commands this role ran)

```text
python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/baseline_verify.py \
  .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers \
  .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes \
  .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2
rc=0, problems=[]

python -B .../replay-repair/checks/static_verify.py \
  .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers \
  .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes
rc=0, problems=[], forbidden_modules_imported=[]

python -B .../replay-repair/checks/diff_products.py <baseline-dir> <worktree-dir> <file>   (3 runs, one per product)
rc=0 each

python -B .../replay-repair/checks/final_audit.py <worktree-dir> <baseline-dir> <replay-repair-dir>
rc=0, problems=[] (see checks/final_audit.stdout.json)
```

`static_verify.py` asserts, on bytes only: 3/3 products parse; no module-level
definition was removed; the changed/added definition set is exactly the one above;
`append_event` orders dedupe -> guard -> real append -> release inside the single
lock and still reaches `_event_id_present` before `status='duplicate'`; the
lifecycle floor still compares the creation before and every prior same-logical
`task_after`, still raises `LifecycleInputError`, and is still bound as
`_append(..., guard=<family>)`; the replay test is `event_id`-only; both suites
equal their protected digests; the checker imported no product/test/pytest module.

It also reports (informationally, never as a problem) the stage-C
preparation-time static expectations that this round necessarily supersedes:
`wire_guard_slot_before_dedupe`, `lifecycle_floor_precheck_before_append`,
`product_matches_delivered_after` for wire/lifecycle, and the two new lifecycle
helpers. Their stage-C code pins the *stage-B* bytes, the guard-before-dedupe
order and its own helper set, so they must read False/extra now; the 16
behavioural boundary items — not that preparation-time checker — are the
acceptance oracle for this delivery.

`baseline_verify.py` records the stage-C runner, stage-C suite, stage-C static
result, the PM probe suite/meta/stdout, both PM postfix reports and the stage-B
report SHAs; `final_audit.py` re-hashes them and fails on any change, re-derives
each `diff/*.diff` from the bytes (a hand-edited diff fails), and checks
`report.md == output.md`, the five sections in order, the `文件` table header, and
that every file this role created is listed with an existing canonical path.

Immutable evidence SHAs at this write (`final_audit.py` re-check):
`pm-postfix-tests/test_replay_probe.py 62c03940...4371fb`,
`runs/t10-r2-replay-probe-first/pytest-replay.stdout ffb0ce1b...c0efa1e`,
`pytest-replay.meta.json 6f72f8ca...40dca805`,
`runs/t10-r2-postfix-first/report.json d987ed6d...e561a6f`,
`runs/t10-r2-postfix-second/report.json cd5f409f...8e6200e0`,
`verification-preparation/test_t10_r2_boundaries.py 5abd812b...90f771`,
`verification-preparation/run_pm_tests.py 2e6db8d2...49adc9`,
`verification-preparation/checks/static_verify.result.json e2768ebd...4af84b2`,
`product-repair/report.md d7cd1ca5...1a44bd4`.

## 残留与未验证

- **No execution by me.** No pytest, no `--collect-only`, no import of any
  product/test/runner, no fake scope, no service/provider/HTTP/CLI, no
  `npm check`, no install/build/commit, and no OS write of any kind (no fixture,
  `%TEMP%`, redirect, delete or copy). The AC052 probe is **not** verified green
  by me; it is only expected to pass, by static reading of the two repaired
  orders.
- **PM verification still required (exact).** Under a new approved label, in the
  real isolated cwd with a fresh `--basetemp` and the existing env/plugin guards:
  run the two assigned suites twice (expect 130 passed) plus the focus set (expect
  14 passed), then the independent AC052 probe (expect green), then all 16 stage-C
  boundary items (concurrency, replay before/after a later observation, secret and
  guard controls) against the **new** product SHAs
  `03f4373f6328b05d5abedd5d686dda3b155b08436908beb8f6d29585dcf0639c` /
  `2ab3ac15d80e2f90987366a380d376fde17482917759d40d5dd07d5b427244a2` /
  `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d`.
  The earlier 130+/14+ runs are history for the *before* bytes, not postfix
  evidence.
- **`record_terminal` keeps its own pre-append floor check.** It has the same
  shape (inline floor comparison before the append) but its idempotency key is
  derived from `(logical_id, terminal)`, so a repeated terminal already collapses
  to one row and the older-`task_after` replay case was **not** reproduced. I did
  not touch it (no new dedupe shortcut there); a future card may align it, and
  until then an identical terminal replay with an older snapshot would still raise
  instead of returning `duplicate`.
- **Concurrency is reasoned, not executed here.** The stage-C two-writer tests
  exercise the real lock race; my claim is limited to the code order above.
- **Unknown/untouched:** secret equivalence classes and 8.3 short-name behaviour
  remain unverified and unmodified; no `decision.py` or protocol change; S2/S6/S8
  (global `decision_id` uniqueness, single terminal, builder privatisation) are
  not introduced; no test, stage-A/B/C or PM artifact was edited or deleted; the
  historical ledger gaps of stages B/C are not backfilled.
- **Stage-C `verification-preparation/static_verify.py` is not a postfix
  oracle.** It pins `product_matches_delivered_after:*` (stage-B bytes),
  `stage_b_products_unchanged_since_absorption`, `wire_guard_slot_before_dedupe`
  and `lifecycle_floor_precheck_before_append` at the very facts this repair had
  to change, so it will report those as failing against the new bytes. I did not
  touch it (read-only, outside this write face); `static_verify.stdout.json`
  records the computed verdicts, and the 16 behavioural items in
  `test_t10_r2_boundaries.py` plus the AC052 probe stay the acceptance oracle.
- **Static-only risk.** The new precheck changes which call path raises first for
  a *new* older observation only in that the floor comparison is now factored into
  `_refuse_preceding_after`; the error class/message (`LifecycleInputError` from
  `TaskStateInputError`) and the zero-byte outcome are unchanged. If a real run
  disagrees, the failing field name in the assertion is the next entry point.

## 上下文来源

- `.agenticdoc/mw-dp-consolidation/workers/dpc-t10-r2-replay-repair/task.md`
  (this dispatch card, read to EOF)
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`
  (AC-050 / AC-052 and the writer constraints, read to EOF)
- `.agenticdoc/goal.md:5` (project goal)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-green-replay-disposition-20261028/check.json`
  (declared product/test SHAs, two green 130P + focus 14P runs, the probe 1F/rc1,
  stage-C status `needs-clarification`/exit 2 and the machine-JSON gaps)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/test_replay_probe.py`
  and `runs/t10-r2-replay-probe-first/{pytest-replay.stdout,pytest-replay.meta.json,report.json}`
  (the reproduced red and its exact traceback)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/runs/t10-r2-postfix-{first,second}/report.json`
  (the two green runs of the before bytes)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/test_t10_r2_boundaries.py`
  (stage-C AC052 replay item, its `PREDICTED_RED` note and the two S5 controls)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/report.md`
  and `after-bytes/` (stage-B S1/S3/S5/S7/S4 repair and the byte-exact baseline)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py`,
  `decision_lifecycle.py`, `decision_task_state.py` (read to EOF before editing)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py`,
  `test_decision_task_state.py` (read to EOF; T22 duplicate-snapshot item and the
  S5 non-decreasing controls that must stay)

## 改动清单

| 文件 | 变更 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py` | `append_event`: the in-lock `event_id` dedupe scan now runs before the caller `guard` (a recorded id is `duplicate` with zero bytes, no guard, no sidecar), the guard still runs before every real append inside the same single `O_CREAT\|O_EXCL` lock, plus the module/function docstrings describing that order; no other definition changed |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py` | Split the floor into `_refuse_preceding_after` (pure comparison: creation before + every prior same-logical `task_after`, damaged snapshot refused) and `_recorded_after_floor` (the lock-scoped `append_event(..., guard=...)` form); new `_event_is_recorded` (event-id-only replay test); `record_lifecycle`'s fail-fast precheck now runs the floor only for a not-yet-recorded `event_id`; docstrings |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py` | no change (byte-identical, deliberately not edited) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/report.md` | this five-section report |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/output.md` | byte-identical delivery copy of this report |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/baseline_verify.py` | read-only baseline/integrity checker (no product import, no writes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/baseline_verify.stdout.json` | checker stdout (rc=0, problems=[]) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/baseline_verify.stderr` | checker stderr (0 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/baseline_verify.rc` | checker exit code (0) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/static_verify.py` | read-only AST/text verifier (order, definitions, protected suites, no product import, stage-C pinned-expectation report) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/static_verify.stdout.json` | verifier stdout (rc=0, problems=[]) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/static_verify.stderr` | verifier stderr (0 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/static_verify.rc` | verifier exit code (0) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/diff_products.py` | read-only unified-diff generator (baseline copy -> current product) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/final_audit.py` | read-only delivery auditor (recorded SHAs vs live bytes, diff regeneration, report sections/table, inventory) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/final_audit.stdout.json` | auditor stdout (rc=0, problems=[]) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/final_audit.stderr` | auditor stderr (0 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/checks/final_audit.rc` | auditor exit code (0) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/diff/decision_wire.py.diff` | unified diff before -> after (docstrings + dedupe-before-guard reorder) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/diff/decision_lifecycle.py.diff` | unified diff before -> after (floor split, replay precheck, guard unchanged) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/diff/decision_task_state.py.diff` | empty diff marker (byte-identical) |
