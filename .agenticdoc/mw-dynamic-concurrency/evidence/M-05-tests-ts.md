# M-05-tests-ts — evidence (MDC B3, TS half: VC-107 / VC-108)

Key `mw-dynamic-concurrency`, card `T-C-M05-tests-ts`. Added test only, no
production code touched. Single code write face:
`packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts`.

## ① Raw vitest output + explicit file arguments

### Command A — the new file alone (P-032: explicit file argument)

```text
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-concurrency-panel.test.ts
```

Raw output (complete):

```text

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-107 recompute cap=8 used=2 eff=2 frontier=2 render="autopilot: cap 8 | eff 2 (frontier 2)"
[VERIFY] VC-107 recompute cap=1 used=2 eff=1 frontier=2 render="autopilot: cap 1 | eff 1 (frontier 2)"
[VERIFY] VC-107 edge=pending slotsUsed=1
[VERIFY] VC-107 edge=manual slotsUsed=0
[VERIFY] VC-107 edge=terminal slotsUsed=0
[VERIFY] VC-107 edge=mixed slotsUsed=2
[VERIFY] VC-108 field=max_parallel_keys ts_default=8 py_default=8 ts_range=[1,null] py_range=[1,null]
[VERIFY] VC-108 field=max_workers_per_key ts_default=4 py_default=4 ts_range=[1,null] py_range=[1,null]
···[VERIFY] VC-108 corpus range-max-parallel-low=accept range-max-parallel-min=accept partial-key-max_workers_per_key=accept range-max-parallel-below-floor=reject
·

 Test Files  1 passed (1)
      Tests  4 passed (4)
   Start at  17:32:58
   Duration  1.37s (transform 105ms, setup 0ms, import 133ms, tests 1.10s, environment 0ms)
```

### Command B — new file + the existing concurrency-sensitive suites

```text
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-concurrency-panel.test.ts test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-monitor.test.ts
```

Raw tail (the four files share one runner; preceding `[VERIFY]` lines are the
existing suites):

```text
[VERIFY] P5: key_order_match=true defaults_match=true keys=21 bool=4 list=1 str=1 enum=1 int=15 optional=envelope_fallback
···[VERIFY] P1: crosslang_verdict_match=77/77
·[VERIFY] P2: canonical_sha_match=41 sha256_equal=true
[VERIFY] P3: py_to_ts_idempotent=41 ts_to_py_idempotent=41
··[VERIFY] P6: partial_single_key=38 raw_view_partial=true effective_view_21=true fields_covered=21
·

 Test Files  4 passed (4)
      Tests  36 passed (36)
   Start at  17:33:03
   Duration  2.29s (transform 673ms, setup 0ms, import 1.04s, tests 3.31s, environment 0ms)
```

New file contributes 4 of the 36 tests. The existing `autopilot-config-parity`
(4), `autopilot-config-sync` (2) and `autopilot-monitor` (26) tests are
unmodified and all pass.

### Command C — type check

```text
cd H:/git/Multi-Workers/packages/coding-agent
npx tsgo --noEmit
```

Result: exit code 0, no diagnostics.

## ② VC-107 — four slot-accounting boundary cases, measured

Shared fixture for every case: roadmap `Stage 1` `status: running` with
`key-status: kA=running, kB=running, kC=running, kD=done` and the keys table
`kA/-`, `kB/-`, `kC/kB`, `kD/-` ⇒ panel `|F| = kA + kB = 2` (kC blocked by the
still-running kB, kD dispatch-skipped as terminal). Config
`enabled: true, max_parallel_keys: 8`. All rows are read from one
`.agenticdoc/_workers.parallel`, all snapshots at
`2026-10-14T10:00:00+00:00`.

| # | boundary | `_workers.parallel` rows | `slotsUsed` |
|---|----------|--------------------------|-------------|
| ① | `pending` conductor counts | `ap-kB-1 pending / owner kB / conductor` | **1** |
| ② | `manual` never owns a slot | `ap-kA-1 running / owner kA / manual` | **0** |
| ③ | terminal rows free their key | `ap-kA-1 done / conductor`, `ap-kB-1 failed / conductor` | **0** |
| ④ | mixed key counts once | `kA: running+conductor, pending+conductor, running+manual` + `kB: pending+conductor` | **2** (kA once + kB once, not 4 rows) |

Discrimination notes (asserted in-file):

- ① `slotsUsed = 1` while the running-only worker list is EMPTY and
  `keys[kB].inFlight = 0` — the slot comes from the non-terminal conductor set,
  not from the running scan. A running-only `used` would read 0 here.
- ② the row IS in `workers` (`workers.length = 1`) yet `slotsUsed = 0` and
  `keys[kA].inFlight = 0` — `origin=manual` bars the slot.
- ③ both terminal rows are conductor-origin yet `slotsUsed = 0`.
- ④ one key with two conductor rows + one manual row counts once (`slotsUsed = 2`
  total with kB, not 3 conductor rows and not 4 rows).

Same-snapshot recompute (one row set + one roadmap, two configs):

```text
[VERIFY] VC-107 recompute cap=8 used=2 eff=2 frontier=2 render="autopilot: cap 8 | eff 2 (frontier 2)"
[VERIFY] VC-107 recompute cap=1 used=2 eff=1 frontier=2 render="autopilot: cap 1 | eff 1 (frontier 2)"
```

Row set: `kA running/conductor`, `kB pending/conductor`, `kC running/manual`,
`kD done/conductor`. The asserted equation is
`slotsEffective === Math.min(slotsCap, frontierSize)` computed in-test from the
same snapshot: `cap8 -> 2 == min(8,2)`, `cap1 -> 1 == min(1,2)`. `slotsUsed`
stays 2 at both caps (the config upper bound does not change who is in flight).
The renderer exposes all three quantities on one legible line
(`autopilot: cap C | eff E (frontier F)`), asserted verbatim plus per-field
`toContain`.

## ③ VC-108 — frozen-value list (field / TS value / Python value / corpus case)

Python values come from a live `spawnSync` of `autopilot/config.py`
(`DEFAULT_CONFIG`, `_INT_RANGES`), compared field-by-field to the TS mirror.

| field | TS value | Python value | corpus case |
|-------|----------|--------------|-------------|
| `max_parallel_keys` default | `8` (`status-model.ts:141`) | `8` (`config.py:91`) | `partial-key-max_parallel_keys` `{"max_parallel_keys": 2}` = accept |
| `max_parallel_keys` range | `[1, null]` (`status-model.ts:202`) | `(1, None)` (`config.py:127`) | `range-max-parallel-low` `{"max_parallel_keys": 1}` = **accept**; `range-max-parallel-min` `{"max_parallel_keys": 2}` = accept; `range-max-parallel-below-floor` `{"max_parallel_keys": 0}` = reject |
| `max_workers_per_key` default | `4` (`status-model.ts:142`) | `4` (`config.py:92`) | `partial-key-max_workers_per_key` `{"max_workers_per_key": 4}` = accept |
| `max_workers_per_key` range | `[1, null]` (`status-model.ts:203`) | `(1, None)` (`config.py:128`) | `range-max-workers-per-key-min` `{"max_workers_per_key": 1}` = accept; `range-max-workers-per-key-low` `{"max_workers_per_key": 0}` = reject |

Measured cross-side line (TS == Python on both fields):

```text
[VERIFY] VC-108 field=max_parallel_keys ts_default=8 py_default=8 ts_range=[1,null] py_range=[1,null]
[VERIFY] VC-108 field=max_workers_per_key ts_default=4 py_default=4 ts_range=[1,null] py_range=[1,null]
[VERIFY] VC-108 corpus range-max-parallel-low=accept range-max-parallel-min=accept partial-key-max_workers_per_key=accept range-max-parallel-below-floor=reject
```

Corpus handling: read-only `JSON.parse` of
`packages/multi-workers/test/fixtures/autopilot-config-corpus.json`; named cases
located by id (a missing id throws, fail-closed); verdicts computed through the
real `validateConfigData` and also checked against each case's frozen
`expected.verdict`. The corpus whole-file sha256 is intentionally NOT asserted
here — that is the existing P4 suite's job, and re-freezing must not break this
file. The floor's negative control (`0 -> reject`) keeps the accepts from being
vacuous.

## ④ Consistency with the absorbed M-02 / M-03 conclusions

- In-flight predicate is single-sourced (AC-012, D-106/D-019). `slotsUsed` is a
  count of KEYS from `conductorInflightKeys`, built in
  `monitor.ts:518-528` with `!TERMINAL_WORKER_STATUSES.has(status) ∧
  owner !== "" ∧ workerBelongsToKey(entry, owner)`. The predicate itself is
  `shared/worker-store.ts:65-70`:
  `workerOrigin(entry) === "conductor" && workerOwnerKey(entry) === key`
  (origin filter INSIDE the predicate) — hence `pending` counts and `manual`
  never owns a slot. This is byte-for-byte the Python
  `mw_common.row_belongs_to` (`mw_common.py:2026-2034`:
  `worker_is_conductor(row)` first, then `worker_owner_key(row) == key`) that
  M-02/M-03 absorbed. Tests ①②③④ are the executable form of that decision.
- `slotsCap = config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`
  (`monitor.ts:968`), `slotsEffective = min(slotsCap, frontierSize)`
  (`monitor.ts:994`), `frontierSize` from the running-stage frontier
  (`monitor.ts:954-966`), render line `monitor.ts:1289-1292` — matches M-03 ③
  (`cap8 -> eff 2`, `cap1 -> eff 1`) exactly.
- `frontierSize` is the panel's own `|F|`, an upper bound on the conductor's
  `|F|` (TS does not read the key claim, `monitor.ts:948-953`). Per the card,
  assertions use the panel `|F|` and never assume equality with a conductor
  count.
- VC-108 mirrors the M-03 ④/P5 values: `max_parallel_keys` default 8 / range
  `(1, None)`, `max_workers_per_key` default 4 / range `(1, None)`, and the
  corpus widening `range-max-parallel-low` reject -> accept at payload
  `{"max_parallel_keys": 1}`.

## ⑤ Write face / exclusions

- Written: `packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts`,
  `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-ts.md`.
- Not touched: any `packages/coding-agent/src/**`, any Python source, any
  existing test file, the frozen corpus JSON, `dist/**`. No `npm run check`
  (P-017), no unfiled-argument vitest (P-032), no git write.
- No `.skip` / `.only` / `.todo`; no existing assertion relaxed.
