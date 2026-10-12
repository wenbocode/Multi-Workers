# T-14 count-locks — report (mw-gate-verdict-hardening)

- Key: `mw-gate-verdict-hardening` (phase=EXECUTE), card `mwg-t14-count-locks`
- Baseline: HEAD `776b82d7f`
- Status: **DONE** — all four count locks refreshed to the new semantics on both
  sides; `[VERIFY] 1/2/4` green; `[VERIFY] 3` green except one documented
  pre-existing environment red (below).
- No commit, no production logic change (all four control-experiment edits were
  restored byte-for-byte; shas recorded in §4).

## 1. Edits (file:line, old → new, why)

### Python

1. `packages/multi-workers/test_autopilot_auto_decision.py`
   - `:301` `assert len(conductor.STALL_REASON_CODES) == 12` → `== 14`.
     Why: the production closed set grew from 12 to 14 — T-01 added
     `l3-aborted`, T-10 added `contract-unauthorized`. Verified live:
     `len(STALL_REASON_CODES)==14` and it is still a subset of `REASON_CODES`
     (47 codes).
   - `:333` `assert len(calls) == 12, f"expected 12 call sites..."` → `== 14`.
     Why: the conductor source now has 14 `mark_stalled(...)` call sites; the
     two new producers are the `l3-aborted` and `contract-unauthorized`
     `mark_stalled` calls. Each call site still carries `reason_code=`.
   - `:338` set-equality `assert codes == set(conductor.STALL_REASON_CODES)`
     left **unchanged** — after the two count fixes it already holds: the 14
     `reason_code="..."` literals in `conductor.py` are exactly the 14
     `STALL_REASON_CODES` (independently dumped, see §2). No relaxation.
   - `:330` renamed `test_all_twelve_mark_stalled_call_sites_pass_a_reason_code`
     → `test_all_mark_stalled_call_sites_pass_a_reason_code`; `:297` section
     comment `12-call-site` → `14-call-site`. Why: a test whose name says
     "twelve" while asserting 14 is the same stale-assertion landmine P-021
     targets. Name had no other references in the repo.
2. `packages/multi-workers/test_autopilot_timeline.py`
   - Added module-level `LOCKED_EVENT_TYPES = frozenset({...})` (`:34-62`) with
     the 27 frozen D-109 names (incl. `contract-frozen`).
   - `:91-94` replaced the hard count `assert len(tl.EVENT_TYPES) == 23` with
     `assert tl.EVENT_TYPES == LOCKED_EVENT_TYPES` (added/removed diff in the
     failure message).
   - `:100-101` derived the line count/seq range from `len(LOCKED_EVENT_TYPES)`
     instead of the magic `23` / `range(1, 24)`.
   - `:108` `_verify(event_lines=14, ...)` → `event_lines=len(events)` (the old
     literal 14 was already stale before this card).
   - **Why set equality is stronger than a count**: a rename (e.g.
     `contract-frozen` → `contract-froze`) keeps `len(EVENT_TYPES)` at 27 but
     breaks the vocabulary; a count-only lock stays green. Set equality against
     the literal reddens on any add/remove/rename, and the message names the
     exact delta. Control C proves it fires when one name is removed.
3. `packages/multi-workers/test_autopilot_config_parity.py`
   - `:60` `FROZEN_CORPUS_SHA256` `49218...743e3` → `1e27f5...4744a`.
   - `:61` `FROZEN_CORPUS_COUNT` `64` → `73`.
   - `:23/:166/:392` docstrings "17-key" → "20-key"; `:422-426` the two parsed
     key-count asserts `== 17` → `== 20`; `:437` `effective_view_17=true` →
     `effective_view_20=true`.
   - Why: T-02's three config keys (`l3_abort_retry_limit`,
     `gate_reminder_after_min`, `gate_reminder_max`) are live in
     `config.DEFAULT_CONFIG`, so the parsed view is 20 keys on both sides. The
     corpus lacked a single-key accept case for each of those three keys, so
     `test_p6_partial_single_key`'s `covered == expected_keys` could not pass
     without adding them (P-021: the corpus was the stale lock, not the
     assertion).
4. `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`
   - Append-only, 64 → **73** cases (+9): 3 single-key `accept` cases (one per
     T-02 key, `D2`) + 6 out-of-range `reject` cases (both bounds per key,
     `D5`). No existing case deleted/replaced; the first 64 cases are
     byte-identical to the pre-task state (verified by reconstructing the
     pre-edit JSON: append-only diff, see §3).
   - Why 6 rejects not 3: a range is only locked when both bounds are
     exercised — one reject per key tests one direction only. This matches the
     corpus's existing precedent (`range-poll-min`/`range-poll-max`, and T-18's
     `range-launcher-max-workers-low`/`-high`).
5. `packages/multi-workers/test_autopilot_readcap_injection.py`
   - **No change.** The card allowed a deliberate re-freeze of the
     `test_autopilot_config.py` golden sha, but nothing here changed: I did not
     touch `test_autopilot_config.py`, and T-02 had already re-frozen that entry
     (`:998-1006`, `27b222b9...`). Confirmed
     `test_existing_regression_files_untouched` passes.

### TypeScript

6. `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
   - `EVENT_TYPES` (`:1067-1081`) += `"contract-frozen"` (with a comment naming
     T-23/AC-025 as the Python producer). This is the TS half T-23 deliberately
     left out to avoid colliding with T-12's `authorizes` edit in the same file.
   - Nothing else in the file touched: `GATE_JSON_LIST_FIELDS`,
     `GATE_FRONTMATTER_FIELDS` (40-name order), `ageMs`, the 20-key config
     mirror and `AUTHORIZES_ACTIONS` are as T-05/T-12 left them (verified by
     running the same-file suites in `[VERIFY] 2/4`).
7. `packages/coding-agent/test/suite/autopilot-event-parity.test.ts`
   - **No numeric change needed.** The judge is already set equality with
     `process.stdout.write(...count=${ts.length})` (no magic number), so once
     `contract-frozen` landed in `status-model.ts` the test goes green. Verified
     `[VERIFY] VC-012: equal=true count=27`.
8. `packages/coding-agent/test/suite/autopilot-console.test.ts`
   - **No change needed.** The `:374-378` gates `toEqual` already carries the
     post-T-05/T-12 shape `{id, kind, status, ageMs}` (T-05 added `ageMs`;
     T-12's `authorizes` is a parse-surface/extension field and is **not** part
     of `GateView`, so it correctly does not appear in the JSON gates group).
     The suite is green; editing it to a different shape would have required a
     production change outside this card's write face.
9. `packages/coding-agent/test/suite/autopilot-config-sync.test.ts`
   - `FROZEN_CORPUS_SHA256` → `1e27f5...4744a`; `FROZEN_CORPUS_COUNT` `64` →
     `73` (`:38-39`). Docstring `:11` and comment `:168` "14 keys" → "20 keys".
10. `packages/coding-agent/test/suite/autopilot-config-parity.test.ts`
    - `:356` `toBe(17)` → `toBe(20)` (py parsed); `:361` `toBe(17)` → `toBe(20)`
      (ts merged); `:18/:119/:343/:355/:360` comments/name "14/17-key" →
      "20-key"; `:376` `effective_view_17` → `effective_view_20`.

## 2. P-021 — per-item semantic diff (before re-freeze)

Live dumps (not hand-copied):

- `STALL_REASON_CODES` = 14, superset of the old 12 with
  `l3-aborted` and `contract-unauthorized`; all 14 are in `REASON_CODES` (47).
- `conductor.py` `mark_stalled(` call sites = 14; the 14 `reason_code` literals
  are set-equal to the production constant (independently dumped, `equal=True`).
- `timeline.EVENT_TYPES` = 27:
  `advance, beat, config, contract-frozen, contract-refused, dispatch,
  evidence-reconciliation, gate-answered, gate-auto-decision, gate-auto-revoke,
  gate-created, gate-reminder, goal-halt, goal-snapshot, l3-aborted,
  l3-no-verdict, reconcile, resume, review-decided, review-escalated, skip,
  stage-close, stage-reopen-refused, stalled, target-config-rejected,
  type-rejected, worker-terminal`.
- config keys = 20 (`config.DEFAULT_CONFIG`); single-key corpus coverage now
  `fields_covered=20`.

## 3. Corpus diff (append-only)

Reconstructed pre-edit JSON (drop the 9 new ids) is byte-identical to the
current file for the first 64 cases; unified diff `@@ -761,4 +761,115 @@` is
purely additive. Added ids:

```
partial-key-l3_abort_retry_limit        accept  {"l3_abort_retry_limit": 1}        D2
partial-key-gate_reminder_after_min     accept  {"gate_reminder_after_min": 30}    D2
partial-key-gate_reminder_max           accept  {"gate_reminder_max": 2}           D2
range-l3-abort-retry-limit-low          reject  {"l3_abort_retry_limit": -1}       D5
range-l3-abort-retry-limit-high         reject  {"l3_abort_retry_limit": 11}       D5
range-gate-reminder-after-min-low       reject  {"gate_reminder_after_min": 0}     D5
range-gate-reminder-after-min-high      reject  {"gate_reminder_after_min": 1441}  D5
range-gate-reminder-max-low             reject  {"gate_reminder_max": 0}           D5
range-gate-reminder-max-high            reject  {"gate_reminder_max": 3}           D5
```

New corpus sha256 (both sides): `1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a`,
count 73.

## 4. [VERIFY] raw outputs

### 1) Python locks — GREEN

```
cd packages/multi-workers
python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_timeline.py test_autopilot_config_parity.py -q -p no:randomly
...............................................                          [100%]
47 passed in 0.78s
```
With `-s`, the refreshed [VERIFY] lines:
```
[VERIFY] VC-019: event_lines=27 per_type=all schema=valid
[VERIFY] VC-025: reason_codes=47 stall_codes=14
[VERIFY] VC-025: call_sites=14 mapped_codes=14
[VERIFY] P4: corpus_sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a cases=73 categories=D1,D2,D3,D4,D5,D6
[VERIFY] P6: partial_single_key=35 raw_view_partial=true effective_view_20=true fields_covered=20
```

### 2) TS locks — GREEN

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/suite/autopilot-console.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-config-parity.test.ts
 [VERIFY] P4: corpus_sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a cases=73 categories=D1,D2,D3,D4,D5,D6
 [VERIFY] P5: key_order_match=true defaults_match=true bool=3 list=1 str=1 enum=1 int=14
 [VERIFY] VC-012: equal=true count=27
 [VERIFY] P1: crosslang_verdict_match=73/73
 [VERIFY] P2: canonical_sha_match=38 sha256_equal=true
 [VERIFY] P3: py_to_ts_idempotent=38 ts_to_py_idempotent=38
 [VERIFY] P6: partial_single_key=35 raw_view_partial=true effective_view_20=true fields_covered=20
 Test Files  4 passed (4)
      Tests  47 passed (47)
```

### 3) Sidecar regression set — 1 documented pre-existing red

```
cd packages/multi-workers
python -X utf8 -m pytest test_autopilot_readcap_injection.py test_autopilot_config.py test_autopilot_effective_config.py test_mw_autopilot_cli.py test_doctor_gates.py -q -p no:randomly
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound
1 failed, 153 passed, 66 warnings in 33.08s
```

`test_baseline_left_end_bound` is **pre-existing and environment-local**, not a
T-14 regression: it compares the frozen `baseline_20260924/dispatch.head.py`
copy (`219ed80...`) against `git show HEAD:packages/multi-workers/autopilot/dispatch.py`
(`6be60fe...`). None of this card's edits touch `dispatch.py`, and the test file
itself documents the red as expected on a machine whose HEAD moved past the
frozen baseline (`test_autopilot_readcap_injection.py:263-266`, `:944-946`).
The golden-sha guard `test_existing_regression_files_untouched` **passes**
(`test_autopilot_config.py` untouched, T-02's re-freeze intact).

### 4) Event parity + extension integration — GREEN

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/extensions/agent-team-loop.test.ts
[VERIFY] VC-012: equal=true count=27
 Test Files  2 passed (2)
      Tests  193 passed (193)
```

## 5. Non-hollow controls (actual red/green + byte-identical restore)

Each control temporarily edited a **production** file, ran the lock, then
restored the exact bytes (sha256 before == after).

- **A. `STALL_REASON_CODES` back to 12** (`conductor.py`, dropped
  `l3-aborted` + `contract-unauthorized`):
  ```
  >  assert len(conductor.STALL_REASON_CODES) == 14
  E  AssertionError: assert 12 == 14
  FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
  1 failed
  ```
  → the lock reads the production constant, not a copied list. Restore:
  `a33139999b2004315f230d873f217ef8e92f6f00bb27125e373fb4315195ff19`
  before == after; test green again.
- **B. Removed one single-key accept case** (`partial-key-gate_reminder_max`)
  and "fake-synced" the sha/count (72):
  ```
  [VERIFY] P4 passed (fake-synced sha)
  >  assert covered == expected_keys, sorted(expected_keys - covered)
  E  AssertionError: ['gate_reminder_max']
  FAILED test_autopilot_config_parity.py::test_p6_partial_single_key
  1 failed, 1 passed
  ```
  → the parity coverage assertion catches a hollowed corpus even after a
  re-freeze. Restored: corpus 73 /
  `1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a`;
  parity test `FROZEN_CORPUS_COUNT = 73` present; P4/P6 green.
- **C. `timeline.EVENT_TYPES` back to 26** (dropped `contract-frozen`):
  ```
  E  AssertionError: EVENT_TYPES drifted: added=[] removed=['contract-frozen']
  FAILED test_autopilot_timeline.py::test_append_line_schema_all_event_types
  1 failed
  ```
  → set equality, not a count. Restore:
  `67382212f45e35a191fde556c56b978cddc51a16dc01f292f7cb9c6b5972f213`
  before == after; test green again.
- **D. `status-model.ts EVENT_TYPES` without `contract-frozen`**:
  ```
  AssertionError: python-only event types (TS mirror missing them):
    expected [ 'contract-frozen' ] to deeply equal []
  FAILED test/suite/autopilot-event-parity.test.ts
  1 failed | 2 passed
  ```
  → both sides really are compared. Restore:
  `d2f325b18637495fbd78fdcc78838907291ab79a8d0fa983d73bf410566fa70`
  before == after; `equal=true count=27`.

## 6. Residual notes

- `autopilot-console.test.ts:374-378` was listed as a deliverable in the card,
  but the expected shape had already been refreshed by T-05 (`ageMs`); T-12's
  `authorizes` deliberately never enters `GateView`. No edit was required and
  the suite is green — flagging in case the PM expected a churn-free no-op to be
  recorded explicitly (it is).
- The card's "+3 out-of-range reject" was implemented as 6 (both bounds/key),
  matching existing corpus precedent; see §1.4.
- No commit, no `git add`, no production logic kept modified; all control edits
  restored and sha-verified.
