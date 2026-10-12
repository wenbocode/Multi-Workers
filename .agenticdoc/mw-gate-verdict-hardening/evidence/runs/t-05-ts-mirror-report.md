# T-05 report — TS mirror three-piece set (events / `GateView.ageMs` / 3 config keys)

- Key: `mw-gate-verdict-hardening` (phase=EXECUTE)
- Worker: `mwg-t05-ts-mirror`
- Baseline: `776b82d7f`; `git status --porcelain -- .../status-model.ts` started as ` M` (T-18's uncommitted G5/G6 changes already in the worktree).
- Write surface touched (only these two):
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
  - `packages/coding-agent/test/suite/autopilot-console.test.ts`
- Not committed. No Python file, no `worker-store.ts` / `pm-orchestrator.ts` touched.

## Result

All three `[VERIFY]` targets green. T-03 (Python `timeline.py`) and T-02 (Python `config.py`) landed in the worktree during this card, so the event and config sets are now genuinely equal cross-language: `autopilot-event-parity.test.ts` reports `equal=true count=26`, `autopilot-config-sync.test.ts` P5 reports `key_order_match=true defaults_match=true`. One pre-existing stale count lock remains red and is outside this card's write surface (`autopilot-config-parity.test.ts` P6 `17` → `20`, T-14 debt — red text in §4).

## 1. Deliverables with coordinates

### 1.1 `EVENT_TYPES` +3 (AC-001)

`status-model.ts:1048-1050` — appended verbatim `l3-aborted` / `gate-reminder` / `contract-refused` (Python source `packages/multi-workers/autopilot/timeline.py:104-106`). Set is now 26 names, set-equal to Python.

### 1.2 `GateView.ageMs` (AC-007/AC-008, D-009)

- `status-model.ts:1307` — `ageMs: number | null` added to `GateView` (existing `id`/`kind`/`status` types and semantics unchanged).
- `status-model.ts:1397` — `deriveStatusModel(projectDir, nowMs = Date.now())` (optional clock; existing one-arg call sites keep working).
- `status-model.ts:1434-1441` — computed at collect time from `GateRecord.createdAt` (required field, `status-model.ts:680`): `Number.isNaN(createdMs) ? null : Math.max(0, nowMs - createdMs)`. No fallback to `expires_at` (historical v1 gates all lack it).
- `status-model.ts:1472-1479` + `:1498-1502` — `renderStatusText` pending-age suffix ` age=<coarse>` (D-009 text face); `formatCoarseAge` mirrors `monitor.ts`'s `formatDuration`.

### 1.3 Config mirror 17 → 20 (AC-003/AC-005, D-007)

Values/domains verbatim from plan §2.1 / T-02, appended after T-18's three keys (T-18 values/domains untouched):

| key | default | range | coordinates |
|---|---|---|---|
| `l3_abort_retry_limit` | 1 | 0..10 | `:120` (iface), `:149` (default), `:188` (range), `:320` (intOf), `:346` (merge), `:378` (save) |
| `gate_reminder_after_min` | 30 | 1..1440 | `:124`, `:150`, `:189`, `:321`, `:347`, `:379` |
| `gate_reminder_max` | 2 | 1..2 | `:128`, `:151`, `:190`, `:322`, `:348`, `:380` |

`DEFAULT_CONFIG` is now 20 keys in the same order as `config.py` (`config.py:66-85`). None of the three is added to any machine-overridable registry (only `BOOL_FIELDS`/`LIST_FIELDS`/`STR_FIELDS` feed that; unchanged).

### 1.4 `blocked_on_human` truth table (AC-007 cross-language口径, D-008)

`status-model.ts:1313` `TERMINAL_WORKER_STATUSES = {done, failed, needs-clarification, lost}` (mirror of `mw_common.py:166`), and `status-model.ts:1322-1324`:

```
export function blockedOnHuman(pendingGates: number, nonTerminalRows: number): boolean {
	return pendingGates > 0 && nonTerminalRows === 0;
}
```

Exported as the single TS-side definition of the truth table for T-08's `monitor.ts` `blockedOnHuman` (design D-009 forbids a per-gate field; the third `tickStale` axis stays render-time in `monitor.ts`). Not wired into `AutopilotStatus` on purpose — the versioned status schema does not carry it.

## 2. `[VERIFY]` — command text + real output

### 2.1 Event + status parity

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/suite/autopilot-status-parity.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-012: equal=true count=26
·[VERIFY] VC-011: equal=true count=5 ordered=true dep_satisfied=2 pending_review_not_dep=true closed_legacy_dep=true subset=true
·····

 Test Files  2 passed (2)
      Tests  6 passed (6)
   Start at  18:14:16
   Duration  2.14s (transform 66ms, setup 0ms, import 94ms, tests 2.23s, environment 0ms)
```

### 2.2 Console (gates `toEqual` + config locks refreshed)

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·····································

 Test Files  1 passed (1)
      Tests  37 passed (37)
   Start at  18:14:23
   Duration  1.03s (transform 289ms, setup 0ms, import 483ms, tests 431ms, environment 0ms)
```

### 2.3 Combined confirmation after the two non-hollow controls were reverted

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/suite/autopilot-status-parity.test.ts test/suite/autopilot-console.test.ts
```

```
[VERIFY] VC-012: equal=true count=26
·[VERIFY] VC-011: equal=true count=5 ordered=true dep_satisfied=2 pending_review_not_dep=true closed_legacy_dep=true subset=true
··········································

 Test Files  3 passed (3)
      Tests  43 passed (43)
```

### 2.4 Extra (not required by the card, run to prove the config mirror is real cross-language)

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-sync.test.ts
```

```
[VERIFY] P4: corpus_sha256=49218997d5f28f6e2e4577cd8566cabd1294afa6cb559717c0c47fa25bd743e3 cases=64 categories=D1,D2,D3,D4,D5,D6
[VERIFY] P5: key_order_match=true defaults_match=true bool=3 list=1 str=1 enum=1 int=14
··

 Test Files  1 passed (1)
      Tests  2 passed (2)
```

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-protocol.test.ts test/suite/autopilot-read-scope.test.ts
```

```
 Test Files  4 passed (4)
      Tests  71 passed (71)
```

## 3. Non-hollow controls (real red / green)

### 3.1 Drop one event name ⇒ event-parity set-equality turns red

Edit: removed `"contract-refused",` from `status-model.ts` (`EVENT_TYPES`).

```
 FAIL  test/suite/autopilot-event-parity.test.ts > autopilot event vocabulary parity (AC-010 / AC-021 / AC-022, VC-012) > EVENT_TYPES is set-equal across Python and TS (both difference sets empty)
AssertionError: python-only event types (TS mirror missing them): expected [ 'contract-refused' ] to deeply equal []

- Expected
+ Received

- []
+ [
+   "contract-refused",
+ ]

 ❯ test/suite/autopilot-event-parity.test.ts:81:70
     79|   const pyOnly = py.filter((name) => !tsSet.has(name)).sort();
     80|   const tsOnly = ts.filter((name) => !pySet.has(name)).sort();
     81|   expect(pyOnly, "python-only event types (TS mirror missing them)").toEqual([]);

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed (3)
```

Reverted; §2.1 back to green.

### 3.2 Shift one config default by one ⇒ config parity lock turns red

Edit: `queue_alarm_delta: 50` → `51` in `DEFAULT_CONFIG`.

```
 FAIL  test/suite/autopilot-config-sync.test.ts > autopilot config new-key mirror (P5) > matches the Python registries byte-for-byte: order, defaults, types, ranges
AssertionError: expected '{"enabled":false,...,"queue_alarm_delta":51,...}' to be '{"enabled":false,...,"queue_alarm_delta":50,...}' // Object.is equality

Expected: "...\"queue_alarm_delta\":50,\"l3_abort_retry_limit\":1,..."
Received: "...\"queue_alarm_delta\":51,\"l3_abort_retry_limit\":1,..."

 ❯ test/suite/autopilot-config-sync.test.ts:159:42
    158|   expect(Object.keys(DEFAULT_CONFIG)).toEqual(py.keys);
    159|   expect(JSON.stringify(DEFAULT_CONFIG)).toBe(JSON.stringify(py.defaults));

 Test Files  1 failed (1)
      Tests  1 failed | 1 passed (2)
```

Reverted; §2.4 back to green. (The console lock is equally sensitive: `autopilot-console.test.ts:877` now asserts `20` keys and `:385-387` asserts the exact `ageMs`.)

## 4. Dependency / lock notes

- **T-03 landed** during this card: Python `timeline.py:104-106` already carries the three names ⇒ event parity is genuinely set-equal, not a two-sided hole.
- **T-02 landed** during this card: Python `config.py` carries the exact same three keys/domains. `autopilot-config-sync.test.ts` P5 (`Object.keys`/defaults/ranges byte-identical to the real Python subprocess) is green.
- **Still red, owned elsewhere (not in this card's write surface):** `autopilot-config-parity.test.ts` P6 hardcodes the parsed-view count as `17` (lines `356`/`361`, comment `:355`/`:376`), which is now stale at `20`:

```
 FAIL  test/suite/autopilot-config-parity.test.ts > autopilot config cross-language parity (AC-006 / VC-006) > P6: a partial file yields the raw view (py) and the full 14-key parsed view (py + ts)
AssertionError: int-valid-4: py parsed key count: expected 20 to be 17 // Object.is equality

- Expected
+ Received

- 17
+ 20

 ❯ test/suite/autopilot-config-parity.test.ts:356:82

 Test Files  1 failed (1)
      Tests  1 failed | 3 passed (4)
```

The P1/P2/P3 differential halves (the real cross-language judges) pass: `crosslang_verdict_match=64/64`, `canonical_sha_match=35 sha256_equal=true`, `py_to_ts_idempotent=35 ts_to_py_idempotent=35`. The `17`→`20` count lock should be refreshed by the card that owns that file (T-14 / key收口).
- `tickStale` untouched: still TS-only, no second staleness concept introduced.
- Existing `GateView` field types/semantics unchanged; only `ageMs` added. No existing field removed or retyped.

## 5. Console test updates (necessarily red before, refreshed here)

| location | change |
|---|---|
| `autopilot-console.test.ts:83` | added `STATUS_NOW_MS` (deterministic clock so `ageMs` is exact, not wall-clock flaky) |
| `autopilot-console.test.ts:355` | `deriveStatusModel(root, STATUS_NOW_MS)` |
| `autopilot-console.test.ts:383-387` | gates `toEqual` gains `ageMs: 3_600_000` on all three rows (was `:374-378`) |
| `autopilot-console.test.ts:433-434` | second-derivation test passes the same `STATUS_NOW_MS` to both calls (keeps "no process state" true) |
| `autopilot-console.test.ts:874-881` | title/assert `17` → `20`; asserts the 3 G1/G2 keys land after T-18's three |
| `autopilot-console.test.ts:914-916` | `INT_RANGES` key list gains the three new keys |
| `autopilot-console.test.ts:1231-1237` | `enable` config `toEqual` gains the three keys; length `17` → `20` |

## 6. Hygiene

- `biome check` on both files: clean (no fixes applied).
- `tsgo --noEmit` (repo root): no output ⇒ typecheck clean.
- Both files: UTF-8, `FFFD=0`, `CRLF=0`.
- `git status` for the two files only; nothing staged, nothing committed.
