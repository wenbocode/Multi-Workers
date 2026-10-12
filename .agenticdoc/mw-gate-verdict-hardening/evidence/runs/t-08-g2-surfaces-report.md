# T-08 report — G2 surfaces (monitor layer A + console layer B), AC-008 / VC-011

- Key: `mw-gate-verdict-hardening` (phase=EXECUTE)
- Worker: `mwg-t08-g2-surfaces` (baseline `776b82d7f`; `git status` of the write surface started clean)
- Card: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-08-g2-surfaces.md`
- Write surface touched (only these three):
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
  - `packages/coding-agent/test/suite/autopilot-monitor.test.ts`
  - `packages/coding-agent/test/suite/autopilot-console.test.ts` (T-05's uncommitted `ageMs` changes preserved)
- Not touched: `console.ts`, `status-model.ts`, any Python file, any coordination file. Not committed, nothing staged.

## 0. Concurrent-worker note (read first)

A duplicate worker `mwg-t08b-g2-surfaces` was launched for the same card (`_workers.parallel` marks this worker `failed` after a startup `_workers.parallel` permission race, while this pi process kept running; see §5). This worker nonetheless completed the card; §5 records the collision.

## 1. Deliverables with coordinates

### 1.1 Snapshot-level `blockedOnHuman` (task item 1)

- `monitor.ts:184` — `MonitorSnapshot.blockedOnHuman: boolean` (top-level, next to `workers`/`gates`, doc says the file-only truth table + render-time 3rd axis).
- `monitor.ts:42` — import `blockedOnHuman`; `monitor.ts:50` — import `TERMINAL_WORKER_STATUSES` (both T-05, `status-model.ts:1313/:1322`).
- `monitor.ts:364-369` — `readMonitorState` counts `nonTerminalRows` in the SAME `WorkerStore(...).readAll()` pass, using `!TERMINAL_WORKER_STATUSES.has(entry.status)` (NOT `status === "running"`, design D-008/F6).
- `monitor.ts:403-404` — before `return`: `const blocked = blockedOnHuman(gates.length, nonTerminalRows);` then `return { serve, conductor, autopilot, workers, gates, blockedOnHuman: blocked };`

The field is the **two-axis** file-only predicate (same口径 as T-07); the TS-only third axis `tickStale` is applied at render time (T-05's `blockedOnHuman` docstring at `status-model.ts:1315-1321`). No new write path: `monitor.ts` still imports only `node:fs` read APIs; the three-tick byte-identity test stays green (§2).

### 1.2 Render: `BLOCKED_ON_HUMAN` top line (task item 2)

- `monitor.ts:738-753` — inside the `if (s.autopilot.enabled)` branch, after the autopilot summary line, **before** the attention list (`const stallByKey`/`const attention`), insert:

```
if (s.blockedOnHuman && !a.tickStale) {
    lines.push(
        trunc(
            `BLOCKED_ON_HUMAN: ${s.gates.length} pending gate(s), 0 non-terminal workers -> /autopilot gates`,
            MONITOR_LINE_MAX,
        ),
    );
}
```

- `trunc` keeps the head (`monitor.ts:657-659`), so the marker never loses its head. Marker literal is defined once in production code (`monitor.ts:748`); the only other occurrence is T-05's doc comment (`status-model.ts:1315`), not a second marker.
- Monitor gate rows already carried `age=` (`formatDuration`) from the earlier AC-012 work; no change needed there.

### 1.3 Panel height (task item 4)

Sections are unconditional as before: `serve:` / `conductor:` / `workers: 0 running` / `gates: 0 pending` always push a line. The `BLOCKED_ON_HUMAN` line is a state marker (VC-011 requires it only when actually blocked); it does not replace or remove any section.

### 1.4 Console layer B (task item 3) — no code change required

`/autopilot status` renders its gate rows in `status-model.ts` `renderStatusText` (called by `console.ts:cmdStatus`), and T-05 already wired `GateView.ageMs` → ` age=<coarse>` (`status-model.ts:1307` field, `1472` `formatCoarseAge`, `1502` `const age = g.ageMs === null ? "?" : formatCoarseAge(g.ageMs)`). The `?` branch guarantees no `NaN`. `console.ts` itself has no un-aged gate row: `/autopilot gates` already renders `waited=` (`console.ts:renderGateCards`). Per the card ("`status-model.ts` … 能不动就不动") this file was left untouched; instead the behavior is now test-locked (§1.5).

### 1.5 Tests

- `autopilot-monitor.test.ts:483-539` — new describe `G2 AC-008/VC-011: pending-gate age + BLOCKED_ON_HUMAN marker`:
  - fixture (a) pending gate + 0 non-terminal rows ⇒ `blockedOnHuman === true` + `BLOCKED_ON_HUMAN` line present;
  - same fixture checks `renderStatusText` contains `gate-0007 stalled pending age=30m` (age_shown) and prints `[VERIFY] VC-011: age_shown=true blocked_marker=true`;
  - fixture (c) same gate + one `pending` worker row ⇒ `false`; + one `running` row ⇒ `false` (truth table is not `running`-based);
  - stale-beat fixture (`tickStale=true`) ⇒ field stays `true`, marker suppressed (render-time 3rd axis).
- `autopilot-console.test.ts:431-455` — new `AC-008/VC-011` test: fixture gates render ` age=1h 0m` and a hand-built `ageMs: null` model renders `age=?` with no `NaN`.
- Existing snapshot literals gained `blockedOnHuman: false` (`autopilot-monitor.test.ts:563/576/595/623/705`); no test expectation about unrelated behavior changed.

## 2. `[VERIFY]` — command text + real output

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-console.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-011: age_shown=true blocked_marker=true
·········································································

 Test Files  3 passed (3)
      Tests  73 passed (73)
   Start at  18:21:19
   Duration  1.00s (transform 759ms, setup 0ms, import 1.36s, tests 789ms, environment 0ms)
```

All three requested files exist (`autopilot-gate-presentation.test.ts` confirmed via `Get-ChildItem test/suite -Filter "autopilot-gate*"`), so the command was run verbatim.

`tsgo --noEmit` (repo root, read-only): `EXIT=0`, no diagnostics.

`biome check` on the three touched files: `Checked 3 files in 28ms. No fixes applied.`

## 3. Non-hollow controls (real red)

### 3.1 Drop the `BLOCKED_ON_HUMAN` line ⇒ `blocked_marker` turns red

Edit: `if (s.blockedOnHuman && !a.tickStale)` → `if (false && s.blockedOnHuman && !a.tickStale)`.

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·········x·············
 FAIL  test/suite/autopilot-monitor.test.ts > G2 AC-008/VC-011: pending-gate age + BLOCKED_ON_HUMAN marker > VC-011: status rows show pending age and the panel marks the human-blocked state
AssertionError: expected undefined to be defined
 ❯ test/suite/autopilot-monitor.test.ts:495:19
    494| 			const marker = renderMonitorLines(blocked).find((l) => l.startsWith("BLOCKED_ON_HUMAN"));
    495| 			expect(marker).toBeDefined();

 Test Files  1 failed (1)
      Tests  1 failed | 22 passed (23)
```

Reverted; §2 back to green.

### 3.2 Use `status === "running"` instead of non-terminal ⇒ truth table turns red

Edit: `if (!TERMINAL_WORKER_STATUSES.has(entry.status)) nonTerminalRows += 1;` → `if (entry.status === "running") nonTerminalRows += 1;`.

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

········[VERIFY] VC-011: age_shown=true blocked_marker=true
·x·············
 FAIL  test/suite/autopilot-monitor.test.ts > G2 AC-008/VC-011: pending-gate age + BLOCKED_ON_HUMAN marker > VC-011: status rows show pending age and the panel marks the human-blocked state
AssertionError: expected true to be false // Object.is equality
- Expected
+ Received

- false
+ true
 ❯ test/suite/autopilot-monitor.test.ts:514:38
    513| 			const pendingRow = readMonitorState(root, NOW_MS);
    514| 			expect(pendingRow.blockedOnHuman).toBe(false);

 Test Files  1 failed (1)
      Tests  1 failed | 22 passed (23)
```

Reverted; §2 back to green. Together the two fixtures (`pending` row vs `running` row) show the truth table is not constant.

## 4. Cross-task red / lock ownership (not touched, per hard rule 2)

- `autopilot-config-parity.test.ts:356` P6 still hardcodes the parsed-view count `17`, now stale at `20`; it is T-14's lock and left red:

```
 FAIL  test/suite/autopilot-config-parity.test.ts > autopilot config cross-language parity (AC-006 / VC-006) > P6: a partial file yields the raw view (py) and the full 14-key parsed view (py + ts)
AssertionError: int-valid-4: py parsed key count: expected 20 to be 17
 ❯ test/suite/autopilot-config-parity.test.ts:356:82
```

  P1/P2/P3 (the real cross-language judges) were green: `crosslang_verdict_match=64/64`, `canonical_sha_match=35 sha256_equal=true`, `py_to_ts_idempotent=35 ts_to_py_idempotent=35`.
- The config count locks in `autopilot-console.test.ts` were T-05-refreshed to `20`; T-08 added no config lock.

## 5. Serial-chain boundary, read-only, and concurrency

- T-08 → T-13 chain: no `collectedAtMs`/`tickCount`/degraded-frame field added; `startMonitor`/`stopMonitor` lifetime untouched (G4/T-13).
- `monitor.ts` gained no write path; `autopilot-monitor.test.ts`'s "three ticks leave every file byte-identical" case is green in §2.
- Concurrency: while this worker ran, a second process `mwg-t08b-g2-surfaces` (PI_WORKER_TASK pointing at its own task.md) was launched for the same card; `_workers.parallel` shows this worker `failed` at `10:16:50` and t08b `running` from `10:17:35` (this process's `worker.log` has the startup `Permission denied: _workers.parallel` race). The files were still clean when this worker wrote, so this report's coordinates/evidence describe the actual working-tree state. If t08b also lands the same card, the duplicate is a queue-status race, not two divergent implementations; the evidence file below is shared between both workers.

## 6. Hygiene

- Files UTF-8/LF (no CRLF/FFFD introduced), tabs unchanged.
- No `any`, no inline import, no enum/namespace/parameter-property; no keybinding hardcoding.
- `git status` of the write surface:

```
 M packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts
 M packages/coding-agent/test/suite/autopilot-console.test.ts
 M packages/coding-agent/test/suite/autopilot-monitor.test.ts
```

- Nothing staged; no commit.
