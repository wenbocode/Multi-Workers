# T-23 G3 Anchor Establishment — Worker Report

- **status**: DONE
- **task card**: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-23-g3-anchor.md`
- **worker**: `mwg-t23-g3-anchor`
- **baseline**: HEAD `776b82d7f`
- **key**: `mw-gate-verdict-hardening` (phase EXECUTE), AC-025 / VC-047 / F47
- **date**: 2026-10-10

## 1. Result

Implementer landed and verified. The G3 anchor is now produced in production:
a new key is anchored automatically the first time it is observed at the
`design` (AC block) and `plan` (VC block) boundaries, and the explicit
`mw autopilot contract-freeze` CLI anchors anything first-sight could not
(historical keys are never backfilled). `no_anchor => let through` is
unchanged (D-015 `[REVISED]`).

Write surface actually touched (only these four, plus the new test file):

| file | change |
|---|---|
| `packages/multi-workers/autopilot/conductor.py` | `_FIRST_SIGHT_BLOCKS`, `_CONTRACT_FROZEN_EVENT`, `_read_contract_text`, `_freeze_contract_first_sight`, `_freeze_block_first_sight` + one call in `tick` |
| `packages/multi-workers/mw.py` | `from autopilot import contract_guard`, `_CONTRACT_FREEZE_BLOCKS`, `_read_optional_text`, `_contract_freeze_plan`, `_write_contract_freeze`, `_ap_contract_freeze` + argparse `contract-freeze` subcommand + one dispatch line |
| `packages/multi-workers/autopilot/timeline.py` | `EVENT_TYPES` += `"contract-frozen"` (one name only, line 110) |
| `packages/multi-workers/test_autopilot_contract_freeze.py` | new (12 cases) |

`contract_guard.py`, `gates.py`, `mw_common.py`, `config.py`, all count-lock
test files and all TS were **not** touched.

## 2. Implementation coordinates

`conductor.py`:

- `conductor.py:2622` `_FIRST_SIGHT_BLOCKS = {"design": ("ac", "spec"), "plan": ("vc", "design")}`
- `conductor.py:2627` `_CONTRACT_FROZEN_EVENT = "contract-frozen"`; `:2628` `_FIRST_SIGHT_SOURCE = "conductor-first-sight"`
- `conductor.py:2631` `_read_contract_text` — `FileNotFoundError -> ""`, other OSError propagates to the single degrade path
- `conductor.py:2644` `_freeze_contract_first_sight(project_root, st, cfg)` — reads `state.read_key_states`, normalizes phase with `.strip().lower()`, skips every non boundary phase
- `conductor.py:2683` `_freeze_block_first_sight(...)` — the per-key/per-family worker
- `conductor.py:2749` `tick`
- `conductor.py:2768` the single call, inserted at step **2c** (after the `enabled/paused` gate and after `_remind_pending_gates`, before goal detection / `orchestrate`). L3 segment and `_done_transaction` untouched.

`mw.py`:

- `mw.py:43` `from autopilot import contract_guard`
- `mw.py:3566` dispatch `contract-freeze` in `cmd_autopilot`
- `mw.py:3887` `_CONTRACT_FREEZE_BLOCKS` (`ac -> spec`, `vc -> design`, `all` = both)
- `mw.py:3894` `_read_optional_text`
- `mw.py:3905` `_contract_freeze_plan` (pure per-block decision)
- `mw.py:3965` `_write_contract_freeze` (one `contract_guard.write_freeze`, tmp+replace)
- `mw.py:3977` `_ap_contract_freeze`
- `mw.py:5691` argparse `contract-freeze` (`--project` required, `--key` required, `--block {ac,vc,all}` default `all`, `--force`, `--json`)

`timeline.py:110` `"contract-frozen"`.

### The five contract points

1. **Auto-anchor timing** — only `design -> AC block` and `plan -> VC block`
   (`_FIRST_SIGHT_BLOCKS`, `conductor.py:2622/2677`).
2. **Merge + idempotent** — `read_freeze` keeps the existing other family
   (`_freeze_block_first_sight` merge loop), exactly **one** `write_freeze` per
   key per tick; a non-empty target block returns before any parse/write
   (`conductor.py:2703-2704`). Fast path for an anchored key = one
   `read_freeze` read, zero write, zero re-parse.
3. **No backfill** — `tasks/execute/verify/done/""` are absent from
   `_FIRST_SIGHT_BLOCKS`; a boundary without the artifact returns silently.
4. **Trace** — `contract-frozen` with
   `data={block, phase, source, freeze_rel, ids}` (ids sorted) on success, and
   the same keys with an empty `ids` on a degraded read/write.
5. **Never raises** — only `(OSError, ValueError)` is caught (UnicodeDecodeError
   is a ValueError); `read_freeze`/`extract_contract` are total by construction.
   A failure becomes a degraded `contract-frozen` event and `tick` still
   returns `ok`.

### CLI status semantics (documented decision)

The card fixes the enum `written|skipped|unchanged|refused` but not the
mapping; chosen and locked by tests:

- `written` — block written this run (missing filled, or changed + `--force`).
- `unchanged` — block present and its frozen shas equal the current text:
  the default "skip the write" path (text mode also says the write is skipped).
- `refused` — block present and different without `--force`: exit 1, replaced
  ids printed, **nothing written** (sha stable).
- `skipped` — block not selected by `--block`, or no source ids to anchor.

`--force` re-freeze prints the replaced ids and old/new family sha (`family_sha`
reused from `contract_guard`, no second sha extractor). Concurrency: no new
lock; the write path re-reads the sidecar right before `write_freeze` and
re-derives once, so a same-key writer that got there first wins and the write
stays idempotent (sidecar is a per-key file, not a shared queue).

## 3. [VERIFY]

### 3.1 new test file

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_freeze.py -q -p no:randomly
............                                                             [100%]
12 passed in 2.18s
```

### 3.2 regression files

```
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py test_autopilot_contract_guard.py test_mw_autopilot_cli.py -q -p no:randomly
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 4.46s
```

Zero red here (no new breakage). The count locks the card mentions are not in
this file set; see 3.4.

### 3.3 CLI (exact `[VERIFY]` 3 shape)

```
$ cd packages/multi-workers && python -X utf8 mw.py autopilot contract-freeze --project <tmp> --key demo-key --json
{
  "blocks": {
    "ac": { "ids": [ "AC-001" ], "status": "written" },
    "vc": { "ids": [ "VC-001" ], "status": "written" }
  },
  "freeze_rel": ".agenticdoc/demo-key/evidence/contract-freeze.json",
  "key": "demo-key"
}
```

Second run (unchanged) and the change/`--force` matrix:

```
run 2 unchanged:  {"blocks": {"ac": {"ids": ["AC-001"], "status": "unchanged"},
                              "vc": {"ids": ["VC-001"], "status": "unchanged"}, ...}}
run 3 changed no force:
                  {"blocks": {"ac": {"ids": ["AC-001"], "status": "refused"},
                              "vc": {"ids": ["VC-001"], "status": "unchanged"}, ...}}   exit=1
run 4 changed --force:
contract-freeze: demo-key freeze=.agenticdoc/demo-key/evidence/contract-freeze.json
contract-freeze: ac written ids=AC-001 replaced=AC-001 old_sha=fe421432166003bf23bb5d325d786b4fcb6c7950c234900a46e903a08755f6cd new_sha=104d948717d97ccaee88355747d20051cb393df841b509d1005cef7eb4f60cfc
contract-freeze: vc unchanged ids=VC-001
```

### 3.4 count locks (informational, not in the `[VERIFY]` set)

```
$ python -X utf8 -m pytest test_autopilot_timeline.py test_autopilot_auto_decision.py -q -p no:randomly
FAILED test_autopilot_timeline.py::test_append_line_schema_all_event_types        (23 expected vs 27 actual)
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed     (12 vs 14)
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code (12 vs 14)
3 failed, 39 passed
```

All three are count locks owned by **T-14**. The timeline lock was already red
before this card (26 names vs the 23 assertion; T-23 adds only `contract-frozen`
=> 27, still the same single red test). The two `== 12` reason-code locks come
from T-10's already-landed reason codes / `mark_stalled` sites. This card added
no new red test.

## 4. Non-hollow counterfactuals (A-E), really run

Each mutation was applied, the test run, then the file was restored from a
byte backup. Post-restore hashes: conductor `A331399…`, mw.py `CDEAA88…`,
timeline `6738221…` — identical to the pre-mutation hashes.

Reference hashes before any mutation:

```
A33139999B2004315F230D873F217EF8E92F6F00BB27125E373FB4315195FF19  conductor.py
CDEAA889D97061507904D6DAD57560C001CB9EC88B557A021E9B9B2515F43E07  mw.py
67382212F45E35A191FDE556C56B978CDDC51A16DC01F292F7CB9C6B5972F213  timeline.py
```

**A — remove the `tick` call** (`conductor.py:2768`): `2 failed, 10 passed`

- `test_vc047_first_sight_freezes_ac_then_vc_and_never_rewrites` red (sidecar
  never appears).
- `test_freeze_write_failure_degrades_without_breaking_tick` red
  (`assert 0 == 1` on the degraded `contract-frozen` count).

**B — drop the non-empty-block skip guard** (`conductor.py:2703-2704`): red on
exactly the named assertion.

```
time.sleep(1.05)
assert conductor.tick(project, st) == "ok"
> assert _file_sha(freeze_path) == sha_after_plan
E AssertionError: assert '520dcbc02b0c...3f60ae91b412e' == 'fca7aef4106e...956bba4721b7c'
1 failed in 1.33s
```

(The `sleep(1.05)` is in the test: without crossing a clock second the fresh
`frozen_at` would serialize to the same bytes and the sha assertion could not
see the rewrite at all. With the guard present no write happens, so the sha is
stable and green.)

**C — delete the success `contract-frozen` append** (`conductor.py:2732`): red

```
frozen_after_design = _frozen_events(project)
> assert len(frozen_after_design) == 1
E assert 0 == 1
1 failed in 0.25s
```

**D — default-overwrite instead of refuse in `_contract_freeze_plan`**
(`mw.py:3959-3961`): red

```
$ python -X utf8 -m pytest test_autopilot_contract_freeze.py::test_cli_changed_block_refused_without_force -q -p no:randomly
{"blocks": {"ac": {"ids": ["AC-001", "AC-002"], "status": "written"}, "vc": {... "unchanged"}} ...}
FAILED test_autopilot_contract_freeze.py::test_cli_changed_block_refused_without_force
1 failed in 0.36s
```

**E — real end-to-end** (`test_vc047_first_sight_freezes_ac_then_vc_and_never_rewrites`):

```
$ python -X utf8 -m pytest test_autopilot_contract_freeze.py::test_vc047_... -q -p no:randomly -s
[VERIFY] VC-047: ac_first=true vc_added=true spec_bytes_stable=true repeat_sha_stable=true events=2 refused=true
1 passed in 1.15s
```

The test drives: tmp key -> `DESIGN` -> tick => sidecar exists with `spec`
non-empty and `design == {}`; -> `PLAN` -> tick => `design` non-empty and the
`spec` block JSON bytes identical; repeat tick => file sha unchanged and
exactly 2 `contract-frozen` events; rewrite one AC text =>
`contract_guard.evaluate(...).ok is False` with `AC-001` in `changed_ids`
(the T-10 done guard can refuse on this anchor).

## 5. Test matrix (new file)

| case | asserts |
|---|---|
| `test_vc047_first_sight_freezes_ac_then_vc_and_never_rewrites` | contract 1/2/4 + E |
| `test_vc047_no_retroactive_anchor_for_later_phases` | TASKS/EXECUTE/VERIFY/DONE/empty => no sidecar, no event |
| `test_phase_design_without_spec_does_not_anchor_or_raise` | missing artifact => no action, no error |
| `test_contract_frozen_event_is_admitted` | `timeline.EVENT_TYPES` |
| `test_freeze_write_failure_degrades_without_breaking_tick` | contract 5 (`tick == "ok"`, degraded event) |
| `test_cli_fills_missing_blocks` | written + JSON shape |
| `test_cli_unchanged_block_is_left_untouched` | unchanged + file sha stable |
| `test_cli_changed_block_refused_without_force` | refused exit 1, replaced id, zero write, hint |
| `test_cli_force_refreezes_and_prints_shas` | force write, replaced id, old/new sha, anchor moved |
| `test_cli_block_scope_marks_other_block_skipped` | `--block ac` => vc skipped, design empty |
| `test_cli_subprocess_json_and_argparse` | `--key` required (exit 2), real subprocess JSON, project-relative |
| `test_execute_key_without_sidecar_is_anchored_only_by_cli` | P-018 no-backfill + CLI-only anchor |

## 6. Hard-rule compliance

- Only the four write surfaces were modified (verified by `git status --short`).
- No commit / no `git add -A`/`git add .` / no `git checkout .` / `git stash` /
  `git reset` / `git clean`.
- `.agenticdoc/_workers.parallel` / `_workers.acked` untouched; every test and
  every ad-hoc run used a tmp dir. `Get-ChildItem -Recurse -Filter
  contract-freeze.json .agenticdoc` is empty — no real project sidecar created.
- No process killed; no `npm run build`/`npm test`/full vitest/`npm run check`;
  Python tests run only as
  `python -X utf8 -m pytest <specific file> -q -p no:randomly`.
- `contract_guard.py`, `gates.py`, `mw_common.py`, `config.py`, count-lock test
  files and all TS untouched.
- Code quality: no broad `except` (only `(OSError, ValueError)` with the
  documented never-raises rationale); `mw.py` stayed CRLF-consistent
  (5935 CRLF, 0 lone LF); new/changed LF files are `conductor.py`,
  `timeline.py`, the test file.
