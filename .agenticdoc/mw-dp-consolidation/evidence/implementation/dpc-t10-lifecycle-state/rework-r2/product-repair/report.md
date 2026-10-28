# T10 R2 stage B - product repair (local product delivery, NOT verified)

## 结论

Local product delivery only: the three isolated products were repaired for the six
true-red specification gaps of the PM's red disposition (S1, S3, S5, S7, S4) with
minimal diffs, and the unchanged `decision_task_state.py` carries no edit. This is
**not** a PASS, not a T10 handoff, not S2/QG/signoff: I did not run pytest, did not
import any product, did not run any generator/runner/service/decision CLI, did not
write any OS fixture, `%TEMP%` or live path, and I did not add or edit a test. Every
claim below is static (AST/text on bytes) or a reading of the PM's own red output.
The two assigned suites must be re-run by the PM under a new label before any green
claim; expected next state is 130 items / 8 previously-red items green + 122
controls (the count may grow, 116 is not a fixed total).

S2/S6/S8 stay unknown and untouched: no global `decision_id` uniqueness, no
single-terminal rule, no builder privatization, no `decision.py` change.

## 证据

### Before / after (canonical paths, bytes and SHA256; LF, final newline, UTF-8)

| file | before bytes | before SHA256 | after bytes | after SHA256 | diff |
| --- | --- | --- | --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py` | 79832 | `8863e534f0a74edec1fc0105c0619c9dd19c85a472b82db6d622c23a7f85a5e6` | 82286 | `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc` | `diff/decision_wire.py.diff` |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py` | 60811 | `0c0f7fffb353cc829e054dfbeec409915cb4bebce11d998c5d810feb533dc8e4` | 65501 | `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5` | `diff/decision_lifecycle.py.diff` |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py` | 3871 | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` | 3871 | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` | `diff/decision_task_state.py.diff` (empty) |

The before copies are saved byte-exact under
`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/before-bytes/`
and the after copies under `.../product-repair/after-bytes/`; the unified diffs
under `.../product-repair/diff/`. The before SHAs equal the PM's protected
`check.json` (`evidence/implementation/t10-r2-red-disposition-20261028/check.json`).

Read-to-EOF record (the three products as delivered to me, before repair; both
tests read after the repair and proven byte-unchanged): `decision_wire.py` 2265
lines, `decision_lifecycle.py` 1549 lines, `decision_task_state.py` 83 lines,
`test_decision_context_lifecycle.py` 1816 lines, `test_decision_task_state.py`
279 lines; both assigned tests re-hashed byte-identical to the protected digests
(`1bca28c5...eae9`, `30c6e4dd...dc23f`) after the repair. PM red stdout absorbed to
EOF: `.../pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/pytest.stdout`
(8 failed, 122 passed) and `.../t10-r2-red-20261028T065500Z/pytest.stdout`
(8 failed, 122 passed; focus 8 failed, 6 passed); copies in
`.../product-repair/pm-red-read/` (the control run `report.json` SHA equals the
PM-protected `ea8d8d2c...cb1b`).

### True red -> root cause -> minimal fix (with preserved controls)

- **S1 (both red items).** `record_request` defaulted to
  `_stable_event_id("rq", logical_id, dp, parent_ref or "-")`; every request of one
  logical id got the same id, so the refusal row's id made the later real choice
  (and a different choice) a silent `duplicate` with zero rows written.
  Fix: `record_request` now derives the default `rq` id from the canonical JSON
  of the built, fully sanitized row (every association and payload field, with
  only `ts` and the placeholder uuid excluded) via `_canonical_json` +
  `_stable_event_id`, then writes that id into the row. Identical recorded
  content -> identical id -> `duplicate` with zero bytes (control preserved);
  any different fact (choice, basis, actor, decision id, before snapshot)
  -> its own row, first row never rewritten. The duplicate scan itself still
  runs in `decision_wire.append_event(dedupe_event_id=True)` inside the existing
  `mw_common.acquire_lock` `O_CREAT|O_EXCL` lock, so no read-before-write conflict
  decision was introduced.
- **S3 (both parametrized red items).** `record_request` validated the basis
  catalog only; `preparation_issues` skips `applies_to` legality when the legal
  choice set is empty, so `dp-auto` with missing/one-item `handling_options`
  recorded any invented choice. Fix: `_dynamic_entry_answer_issues` (only for
  `require_active_dp(dp_id).kind == "dynamic-candidates"`) calls the single source
  `decision_points.entry_choice_issues` (which uses `resolve_entry_choices`) and
  `decision_points.entry_material_issues` (candidate-set contract); `_refuse_entry_issues`
  raises the first issue after passing the message through the injected redactor.
  No candidate syntax, id scheme, `cN`/2..5 copy or basis vocabulary was added.
  Fixed entries keep their frozen enum (no new material gate), so the old
  `dp-pm-steer` `_material()` helper contract and the old 116 items are not
  re-gated; the legal 2-candidate + selected-basis positive control stays recordable.
- **S5 (red item).** `record_lifecycle` compared `task_after` only with
  `meta.task_before` and the creation fact's stored before; an already recorded
  later after snapshot was never a floor, so an older observation could be
  appended after a newer one. Fix: `_recorded_after_floor` mirrors
  `record_terminal` (same `_ledger_facts` key/task/logical association, validated
  `observed_at` non-decreasing against every prior `task_after` of that logical
  record); it runs before the write and again as an `append_event(..., guard=...)`
  precondition **inside the append lock**, so two writers cannot both pass it
  (read-then-append TOCTOU closed without a new lock). `None`/unrecorded axes are
  never guessed or replaced by "now"; a failed lock round still returns
  `status="failed"` and writes no `executed`/`settled` fact (control preserved).
- **S7 (red item).** `_check_before` compared the ledger's recorded (redacted)
  before against the caller's raw snapshot, so a known-secret-bearing `before`
  never matched after being stored redacted. Fix: new
  `decision_wire.recorded_task_state` is the one validate->sanitize projection the
  store itself applies (`build_event` now delegates to it); `_check_before`
  compares that projection with the recorded row. Backfill refusal, `None` vs `[]`,
  list order sensitivity and non-empty-axis rules are unchanged; the secret is
  still never stored (the row keeps `["<redacted> private step"]`), and only the
  exact recorded form is accepted - no arbitrary masked snapshot is treated as a
  before or as a permission.
- **S4 (both red items).** `_is_inside_agenticdoc` used byte equality of path
  parts; on Windows `.AgenticDoc` is the same directory, so a test-scope sink under
  a case variant passed. Fix: `_same_path_component` compares with
  `os.path.normcase` only when `os.name == "nt"` (POSIX keeps byte equality). The
  production-ledger tail rule and the "any `.agenticdoc` component" rule are
  otherwise unchanged, production-scope fixtures are untouched, and no case or 8.3
  spelling is treated as a licence; no live-path probe was added.

### Retained original guarantees

- Lock: the only write path is still `append_event` with
  `O_CREAT|O_EXCL` `mw_common.acquire_lock` (short budget/retries), tail repair,
  short-write loop and fsync; the new guard runs inside that same lock.
- Idempotency: same `event_id` -> `duplicate`, zero bytes; dedupe by `event_id`
  only, never by `(decision_id, word)`.
- Secrets: `_guard_secret` on every structural value, `_bounded_text` redact-then-
  refuse, redactor mandatory on the store, `preparation_issues` messages withheld
  when the redactor hits; the new entry-issue path applies the same check.
- Legal controls: identical repeated request -> duplicate; legal `dp-auto`
  candidate -> recorded with `basis_source="pm-prepared"`; increasing
  `executed`(09:00) -> `settled`(10:00) accepted; lock-held round -> `failed`, no
  `executed`; exact-case `.agenticdoc` still refused; S9 producer-constant test
  unchanged (`REQUEST_RESULT_FIELDS <= _PREPARED_RESULT_FIELDS`,
  `REQUEST_REASONS == _PREPARED_REASONS`, `BASIS_SOURCE` same source).
- Vocabularies/API: `EXECUTED_ACTIONS`, `OUTCOMES`, `STAGES`,
  `REQUEST_RESULT_FIELDS`, `DecisionMeta`, the four feedback words and all public
  signatures are unchanged; `append_event` gained one additive keyword `guard`.

### Pure static verification (the only commands this worker executed)

```text
python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/static_verify.py \
  .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers \
  .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/before-bytes \
  .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair
rc=0, stderr 0 bytes, problems=[]
```

The checker only reads bytes, `ast.parse`s them and does text/index assertions; it
does not import the products. It asserts: 3/3 products parse; both tests are
byte-identical to the protected digests; before SHAs match the protected values;
no top-level definition removed; the import set is unchanged; explicit checks for
S1 content-addressed id + in-lock dedupe, S3 single-source dynamic validation
without a copied candidate syntax, S5 recorded-after floor + in-lock guard, S7
recorded-representation equality, S4 platform component identity + intact
production rule + no 8.3 probe, no global `decision_id` uniqueness, and
`decision_task_state.py` unchanged. Output: `checks/static_verify.stdout`,
stderr/rc: `checks/static_verify.stderr`, `checks/static_verify.rc`.

Live files were not touched: current live SHAs still equal the PM's recorded live
values (`decision_wire.py 076fd3de...1579`, `decision_lifecycle.py e4ea5183...3248`,
`decision_task_state.py e82fc6b9...e35e9`, tests `106f1719...24f8`,
`c3de3c04...7de8`), and the worktree still has exactly 14 `.pyc` in the two
pre-existing `__pycache__` directories (mtimes unchanged).

A second read-only auditor (`checks/final_audit.py`, cwd = repo root) re-checked
that the `after-bytes/` copies equal the worktree products, both assigned tests
are byte-identical to their protected digests, all five live files equal the
PM-recorded live digests, the `.pyc` count is still 14, `report.md == output.md`,
the five sections are present in order and the change table starts with `文件`:
`rc=0`, `problems=[]` (`checks/final_audit.stdout`, `checks/final_audit.rc`).

## 改动清单

| 文件 | 变更 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py` | `_same_path_component` + nt-only `os.path.normcase` component identity for the `.agenticdoc` test-scope rule; new `recorded_task_state` (validate->sanitize recorded snapshot, used by `build_event`); `append_event(..., guard=None)` lock-scoped precondition that propagates the caller's own refusal without writing/sidecar; docstrings |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py` | `_check_before(store, ...)` compares the recorded representation; `_recorded_after_floor` + in-lock guard for `executed`/`settled`; `record_request` content-addressed `rq` id over the built (sanitized) row plus `_dynamic_entry_answer_issues`/`_refuse_entry_issues` using `decision_points.entry_choice_issues`/`entry_material_issues` for `dynamic-candidates` only; docstrings |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py` | no change (byte-identical); deliberately not edited because no S item needs it |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/report.md` | this report |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/output.md` | same five-section delivery text |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/static_verify.py` | pure AST/text checker (no product import, no writes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/static_verify.stdout` | checker stdout (rc=0, problems=[]) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/static_verify.stderr` | checker stderr (0 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/static_verify.rc` | checker exit code |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/final_audit.py` | read-only delivery auditor (no product import, no writes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/final_audit.stdout` | auditor stdout (rc=0, problems=[]) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/checks/final_audit.rc` | auditor exit code |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/before-bytes/decision_wire.py` | protected before copy (79832 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/before-bytes/decision_lifecycle.py` | protected before copy (60811 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/before-bytes/decision_task_state.py` | protected before copy (3871 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes/decision_wire.py` | after copy (82286 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes/decision_lifecycle.py` | after copy (65501 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes/decision_task_state.py` | after copy (3871 bytes, unchanged) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/diff/decision_wire.py.diff` | unified diff before->after (6501 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/diff/decision_lifecycle.py.diff` | unified diff before->after (14513 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/diff/decision_task_state.py.diff` | empty diff (0 bytes) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-controls-20261028T064853Z/pytest.stdout` | PM red run 1 full pytest stdout copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-controls-20261028T064853Z/focus.stdout` | PM red run 1 focus stdout copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-controls-20261028T064853Z/report.json` | PM red run 1 report copy (SHA equals the protected red report) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-controls-20261028T064853Z/pytest.summary.json` | PM red run 1 summary copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-20261028T065500Z/pytest.stdout` | PM red run 2 full pytest stdout copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-20261028T065500Z/focus.stdout` | PM red run 2 focus stdout copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-20261028T065500Z/report.json` | PM red run 2 report copy |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/pm-red-read/t10-r2-red-20261028T065500Z/pytest.summary.json` | PM red run 2 summary copy |

## 残留与未验证

- **No test execution by me.** I did not run pytest, collect node ids, import any
  product, run the runner/generator/service/HTTP/decision CLI/provider/npm
  check/build/install/commit, or write an OS fixture, `%TEMP%` or live path. No
  green run, PASS, QG, S2 handoff, signoff or "T10 done" is claimed; the repaired
  red items are only expected green.
- **PM next step (exact).** In the approved OS fixture root under a new label, in
  the real isolated cwd (`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`),
  with minimal env and cache/plugin guards:
  `python -B -m pytest -p no:cacheprovider -q --basetemp <PM new label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py`,
  then re-verify the focus set, the 8 red items, the old controls (duplicate,
  dp-auto in-set, increasing order, lock-failure round, exact-case path, S9),
  the protection counts and the live SHAs independently. Then ack this terminal
  state and continue the independent T10 qualification.
- **Static-only reasoning risk.** The S3 positive control depends on
  `entry_material_issues("dp-auto", _auto_material([...]))` returning no issue for
  the test's material (all required `dp-auto` paths present, candidate set valid,
  `background` keys declared); I verified this by reading the validators, not by
  execution. If a real run disagrees, the report of the failing field is the next
  fix entry point; I did not weaken the dynamic check or the old assertions.
- **Concurrency not exercised.** S1 identity/dedupe and the S5 guard are
  lock-scoped by construction, but no concurrent test exists in the assigned
  (read-only) test face; a real two-writer interleaving remains unproven. A future
  test face may add one - I did not add a test.
- **8.3 short names unverified.** The S4 fix covers case-variant components only;
  no 8.3 short-name path was constructed or proven, and no live-path probe was
  added.
- **S2/S6/S8 unknown.** No global `decision_id` uniqueness, no single-terminal
  prohibition, no builder privatization, no `decision.py` extension, no unrelated
  refactor, no restored retired entry, no change to old history/cases/evidence.
- **Read scope note.** I read the three products, both assigned tests, the PM's
  two full red stdout/focus outputs, the original approved
  `T10-lifecycle-state.md` (81 lines to EOF) and the adopted single-source
  protocol surface of `decision_points.py` (entry/choice tables, required/optional
  state fields, typed/cross validators, `resolve_entry_choices`,
  `entry_material_issues`, `entry_choice_issues`, `basis_catalog_issues`,
  `basis_selection_issues`, `preparation_issues`, `prepared_request_issues`) plus
  `decision.py`'s frozen `_PREPARED_RESULT_FIELDS`/`_PREPARED_REASONS`. The
  unrelated legacy registry/renderer/executor tail of `decision_points.py` was not
  read end-to-end because this writer calls none of it; that is a stated read-scope
  limit, not a product claim.

## 上下文来源

- `.agenticdoc/mw-dp-consolidation/workers/dpc-t10-r2-product-repair/task.md`
  (dispatch card, sha256 `b7e04eaa...28e3`)
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`
  (AC-004/012/014/049/050/051/052 and VC contract, read to EOF)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-red-disposition-20261028/check.json`
  (fresh before SHAs, card SHA, protected live/test digests)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/`
  (`pytest.stdout` 8F/122P, `focus.stdout` 8F/6P, `report.json`)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-20261028T065500Z/`
  (second full run, 8F/122P)
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/report.md`
  and `diff/` (stage A: 14 added items, tests unchanged since)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py`
  (read to EOF; stage-A S1/S3/S5/S7/S4/S9 items and controls)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_task_state.py`
  (read to EOF; snapshot equality/null-vs-empty and agent-report boundary)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py`
  (adopted single-source protocol: `ENTRY_CHOICES`, `ENTRY_CANDIDATE_SOURCE`,
  `ENTRY_CANDIDATE_BOUNDS`, required/optional state fields, typed/cross validators,
  `resolve_entry_choices`, `pm_candidate_issues`, `entry_candidates_issues`,
  `entry_material_issues`, `entry_choice_issues`, `basis_catalog_issues`,
  `basis_selection_issues`, `preparation_issues`, `prepared_request_issues`)
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py`
  (`_PREPARED_RESULT_FIELDS`, `_PREPARED_REASONS`, `REASON_CODES`)
- `.agenticdoc/goal.md:5` (project goal) and
  `.agenticdoc/mw-dp-consolidation/spec.md:128`, `design.md:201` as cited by the
  original card
