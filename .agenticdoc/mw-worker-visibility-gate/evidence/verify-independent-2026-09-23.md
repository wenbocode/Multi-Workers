# Independent Verification Report — mw-worker-visibility-gate T-5 (Wave 3)

- Key: `mw-worker-visibility-gate` / Task: T-5-VERIFY
- Date: 2026-09-23 (19:00–19:10 local)
- Verifier: independent coding worker (mwvg-t5-verify); T-1/T-2/T-3/T-6 conclusions were read but **not reused** — every VC below was reproduced with my own fixtures and my own probe scripts.
- Probe scripts (all in `os.tmpdir()`, repo never written outside the mutation windows): `C:\Users\WENBOZ~1\AppData\Local\Temp\mwvg-t5\{probe-gate,probe-panel,probe-claim,probe-scan,probe-pitfalls}.mjs` (+ `m1-red.log`, `m2-red.log`, `m3-red.log`, `final-*.log`). Probes import the real source modules via Node 24 type-stripping (`node <probe>.mjs`), drive the **real** tool/command/scan entrances with fake `pi`/`ctx` objects, and exit non-zero on any failed check.
- Method notes:
  - VC-001/002/003/005/012 go through the real `dispatch_worker` tool entry (`registerWorkerTools` → captured tool.execute), with a goal.md **established** (status: active) so the §0 check is active — the strictest construction.
  - D-110's three call sites were each driven independently: (1) `dispatch_worker` tool, (2) `/worker` command (`registerWorkerCommands`), (3) `dispatchNewTasks` background scan (probe-scan, including the DESIGN-phase interception + unblock-after-docs, redone independently).
  - VC-009's risk source is the trace.log `[CHECKPOINT] … risk=<…>` line (per the task-book revision; `readTaskProgress` parses exactly that shape) — fixtures write `[CHECKPOINT] 2026-09-23T10:30:00.000Z elapsed=1800s reads=42 writes=3 phases=1/2 uniq_targets=2 repeat_top=9 risk=high`.
  - VC-007's "identical to pre-change" baseline is the **git HEAD** `renderWatchLines` extracted with `git show HEAD:…ui-bridge.ts` into a temp module (relative import specifiers rewritten to absolute file URLs; own-row rendering is untouched by this key's diff), run on the same fixtures and compared line-for-line.
  - VC-010 covers both D-108 call sites: `takeOverKey` (probe-claim) **and** the session-restore quiet re-claim via the real `restoreWatch`.

## 1. VC reproduction table

Command prefix for all probes: `cd C:\Users\WENBOZ~1\AppData\Local\Temp\mwvg-t5 && node <probe>.mjs` (exit 0 = all checks green).

| VC | Verdict | Command | Raw output snippet (grep'd from the probe stdout) |
|----|---------|---------|---------------------------------------------------|
| VC-001 | **PASS** | `node probe-gate.mjs` | `Dispatched worker 't-vc001' (type: research, role: research, model: route default (no dispatch.yml research default)) under key 'k-spec'. Task file: …\k-spec\workers\t-vc001\task.md…` / `[VERIFY] VC-001: spec_phase_pass=true task_md=true` |
| VC-002 | **PASS** | `node probe-gate.mjs` | `Worker dispatch blocked: key 'k-design' is missing phase documentation.` `- design.md missing or under 500 bytes` (exactly 1 occurrence; no other gaps; no `k-design\workers\` dir; queue empty) / `[VERIFY] VC-002: blocked=true design_gap=1 task_dir=false` |
| VC-003 | **PASS** | `node probe-gate.mjs` | `Worker dispatch blocked: key 'k-design2' is missing phase documentation.` `- evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)` (design.md ≥500B present → only the evidence gap) / `[VERIFY] VC-003: blocked=true design_evidence_gap=1` |
| VC-004 | **PASS** | `node probe-gate.mjs` | `gateTierOf("—")=spec dispatchDocGaps=[]` / `gateTierOf("")=spec dispatchDocGaps=[]` / `gateTierOf("init")=spec dispatchDocGaps=[]` / `gateTierOf("weird-phase")=spec dispatchDocGaps=[]` (design.md missing yet gaps empty); negative control `DESIGN` → `["design.md missing or under 500 bytes","evidence/research/design-*.md missing …"]`; tool entry with pm-state `- Phase: init` dispatches / `[VERIFY] VC-004: tier=spec design_gaps=0 variants=4` |
| VC-005 | **PASS** | `node probe-gate.mjs` | 4 spec-side gap lines: `- spec.md missing or under 500 bytes` / `- evidence/research/spec-*.md missing …` / `- spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established)` / `- spec.md has no numbered acceptance criteria (AC-NNN)`; no design-side line / `[VERIFY] VC-005: spec_gaps=4 design_gaps=0` |
| VC-006 | **PASS** | `node probe-panel.mjs` | `  ~ 1 elsewhere: _scratch(1 running)` (1 aggregate line, owner + count in line, max line len 59 ≤ 110; own empty state `  (no worker tasks)` kept ahead of it) / `[VERIFY] VC-006: agg_lines=1 owner_in_line=true count_in_line=true max_len=59` |
| VC-007 | **PASS** | `node probe-panel.mjs` | HEAD baseline output: `[mw] key-a | phase=EXECUTE | docs S- D- ev:0/2 | 1 running / 1 done / 1 failed / 1 unhandled` + `> own-run — (no-hb)` + `x own-fail` + `+ own-done`; current output with (a) 6th arg omitted, (b) explicit `undefined`, (c) empty Set, (d) Set naming only own-key tasks — all four **line-for-line equal to HEAD** even though the queue holds 2 cross-key `_scratch` rows; 0 `elsewhere` lines / `[VERIFY] VC-007: agg_lines=0 identical_baseline=true` |
| VC-008 | **PASS** | `node probe-panel.mjs` | `  ~ 2 elsewhere: key-b(1 running, 1 failed)` (unacked failed counted); needs-clarification variant: `  ~ 3 elsewhere: key-b(1 running, 1 failed, 1 needs-clarification)` / `[VERIFY] VC-008: agg_lines=1 terminal_counted=1` |
| VC-009 | **PASS** | `node probe-panel.mjs` | `  ~ 3 elsewhere: key-b(3 running; risk=high:1)` — 3 running rows, exactly 1 with a trace.log `[CHECKPOINT] … risk=high` line (one `risk=low`, one with no trace.log; neither inflates K) / `[VERIFY] VC-009: risk_marker=risk=high:1` |
| VC-010 | **PASS** | `node probe-claim.mjs` | `[VC-010 raw values] fileClaim='WENBOZHOU-PC4:45668' indexClaim='WENBOZHOU-PC4:45668' self='WENBOZHOU-PC4:45668'`; `headings=7 updated=1 crlf=27->27 lfTotal=27->27 bytes=528->535`; no warning, no `.tmp` residue / `[VERIFY] VC-010: claim_ids_equal=true headings=7 updated_lines=1` — and the same invariant on the **restoreWatch** quiet re-claim path (stale same-host dead pid re-claimed, mirror synced): `[VERIFY] VC-010 (restoreWatch path): claim_ids_equal=true headings=7 updated_lines=1` |
| VC-011 | **PASS** (revised D-111 semantics) | `node probe-claim.mjs` | (a) pm-state missing `- Claim-Id:` but with `- Key:` → takeover inserts: `claimLine='- Claim-Id: WENBOZHOU-PC4:45668'`, `crlf=26->27 lfTotal=26->27 bytes=514->547`, line sits directly after `- Key:` (exactly 1 Claim-Id line), stripping the inserted line + terminator reproduces the original bytes (outside_identical), no warning (old semantics would FAIL here: ok stays true with **no** warning, not `ok:false`) / `[VERIFY] VC-011: inserted=true ok=true outside_identical=true`; (b) neither Key nor Claim-Id → direct sync call returns `reason=pm-state.md has no '- Key:' or '- Claim-Id:' line`, bytes untouched, and the claim still succeeds with exactly 1 warning line: `WARNING: claim succeeded but k-nokey/pm-state.md was not synced (pm-state.md has no '- Key:' or '- Claim-Id:' line). The index row is authoritative.` / `[VERIFY] VC-011: no_key_line ok=false untouched=true` |
| VC-012 | **PASS** | `node probe-gate.mjs` | `Dispatched worker 't-vc012' (type: coding, role: coding, …) under key 'k-spec'…`; task.md frontmatter carries `type: coding` + `phase: SPEC` / `[VERIFY] VC-012: coding_at_spec_allowed=true` |
| VC-013 | **PASS-with-note** | `node probe-pitfalls.mjs` | `## P-011 claim 身份双写分叉——按 pm-state 判活会误判抢占（2026-09-23，mw-worker-visibility-gate）`; `索引行` present (`…而 `switch_key` 重写索引行时用…`), `liveness` present (`…用它判 liveness 与所有权…`), but the third calibration appears as **两处必须同值**, not the contiguous string `两处同值` (contiguous-substring hits=0) / `[VERIFY] VC-013: pitfalls_entry=true keywords=3 note=两处同值-appears-as-两处必须同值-contiguous-hits=0` |

**Tally: PASS 12, PASS-with-note 1, FAIL 0.**

Supplementary raw evidence for the D-110 wiring (my own constructions, not T-3's):

- `/worker` command (call site #2), SPEC-phase key passes: `Dispatched pi worker (manual-1790161080904) under key 'k-spec' [type: coding, role: coding, model: route default (no dispatch.yml coding default)].`
- `/worker` command, DESIGN-phase key blocked: `Worker dispatch blocked ('k-design'): design.md missing or under 500 bytes; evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts). Generate the phase docs first or dispatch under _scratch.`
- `dispatchNewTasks` background scan (call site #3), DESIGN phase: `[scan DESIGN raw gaps] ["design.md missing or under 500 bytes","evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)"]`, task NOT queued; after adding design.md + a design note the same task is queued `status: pending`; SPEC-phase key with **no** design.md dispatches with no gate event; a fully undocumented key gets the 3 spec-side gaps (no goal.md → §0 skipped) and is not queued.

## 2. Mutation counter-examples (red → byte-identical restore → green)

Procedure per mutation: sha256 before (H0) → byte-copy backup to temp → apply mutation → run the targeted probe (must exit non-zero with the expected VC red) → restore the file from the backup copy → sha256 after (H1) → H1 must equal H0 byte-for-byte → re-run the probe (must be green).

### M-1 — `gateTierOf` unknown-string branch returns `"design"`

- File: `packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts`
- Mutation: `? "design" : "spec"` → `? "design" : "design"`
- sha256 before: `9925fb91db02a6cf7db2a17ab7ec63b0898453c2e9c70b7505570d12ddf20719`
- **RED** (`node probe-gate.mjs`, exit 1): VC-001 red — the SPEC-phase dispatch now answers `Worker dispatch blocked: key 'k-spec' is missing phase documentation.` / `- design.md missing or under 500 bytes` / `- evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)` (the incident this key fixes); `[VERIFY] VC-001: spec_phase_pass=false task_md=false`; VC-004 red — `[VERIFY] VC-004: tier=MIXED design_gaps=NONZERO variants=4`; VC-005 red — `design_gaps=2`.
- Restored from backup → sha256 after: `9925fb91db02a6cf7db2a17ab7ec63b0898453c2e9c70b7505570d12ddf20719` — **byte-identical: true**
- **GREEN**: `node probe-gate.mjs` exit 0 — `[VERIFY] VC-001: spec_phase_pass=true task_md=true`, `[VERIFY] VC-004: tier=spec design_gaps=0 variants=4`, `[VERIFY] VC-005: spec_gaps=4 design_gaps=0`, `ALL-GREEN probe-gate failures=0`.

### M-2 — aggregate line drops the `risk=high` segment

- File: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- Mutation: `parts.push(\`${owner}(${countText}${highRisk > 0 ? `; risk=high:${highRisk}` : ""})\`)` → `parts.push(\`${owner}(${countText})\`)`
- sha256 before: `6a9c539002f0fa13af650a6e53687f532af7f8a4583d932744295f17582d71c6`
- **RED** (`node probe-panel.mjs`, exit 1): VC-009 red — the aggregate renders `  ~ 3 elsewhere: key-b(3 running)` with no risk marker; `[VERIFY] VC-009: risk_marker=MISSING`; `HAS-FAILURES probe-panel failures=1`.
- Restored from backup → sha256 after: `6a9c539002f0fa13af650a6e53687f532af7f8a4583d932744295f17582d71c6` — **byte-identical: true**
- **GREEN**: `node probe-panel.mjs` exit 0 — `[VERIFY] VC-009: risk_marker=risk=high:1`, `ALL-GREEN probe-panel failures=0`.

### M-3 — `takeOverKey`'s `syncPmStateClaimId` call short-circuited

- File: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- Mutation: `const claimSync = outcome.ok ? syncPmStateClaimId(...) : undefined` → `const claimSync = outcome.ok && false ? syncPmStateClaimId(...) : undefined`
- sha256 before: `6a9c539002f0fa13af650a6e53687f532af7f8a4583d932744295f17582d71c6` (same file state as M-2's green restore)
- **RED** (`node probe-claim.mjs`, exit 1, 8 failed checks): VC-010 red — the two claim values diverge exactly as D-108 predicts: `[VC-010 raw values] fileClaim='OLDHOST:1234' indexClaim='WENBOZHOU-PC4:112564' self='WENBOZHOU-PC4:112564'`; `[VERIFY] VC-010: claim_ids_equal=false`; VC-011(a) red — the insert branch is unreachable through takeover (`inserted=false`, no Claim-Id line in the file); the no-key-line branch's single warning also disappears (claimSync undefined → **silent** divergence). Notably the `restoreWatch` path stayed green — its `syncPmStateClaimId` call site lives in `pm-orchestrator.ts` and is untouched by M-3, which is precisely why D-108 wired **both** call sites.
- Restored from backup → sha256 after: `6a9c539002f0fa13af650a6e53687f532af7f8a4583d932744295f17582d71c6` — **byte-identical: true**
- **GREEN**: `node probe-claim.mjs` exit 0 — `[VERIFY] VC-010: claim_ids_equal=true headings=7 updated_lines=1`, `[VERIFY] VC-011: inserted=true ok=true outside_identical=true`, `[VERIFY] VC-011: no_key_line ok=false untouched=true`, `ALL-GREEN probe-claim failures=0`.

## 3. Regression (final state, after all mutations were restored)

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/extensions/agent-team-loop.test.ts \
  test/extensions/agent-team-loop-phase-docs-gate.test.ts \
  test/extensions/agent-team-loop-pm-state-claim.test.ts \
  test/extensions/agent-team-loop-watch-aggregate.test.ts \
  test/extensions/agent-team-loop-pm-state-sync.test.ts
→ Test Files  5 passed (5)
→ Tests  204 passed (204)      (0 failed)
→ EXIT=0
```

(204 = 173 + 11 + 8 + 7 + 5; the task book's "203 (− 1 重叠计数)" prediction does not materialize — "以实跑为准", actual is 204.)

```
cd H:/git/Multi-Workers && npm run check
→ biome: Checked 1092 files … No fixes applied
→ check:pinned-deps / check:ts-imports / check:shrinkwrap (up to date) /
   check:install-lock:coding-agent (up to date) / tsgo --noEmit / check:browser-smoke
→ EXIT=0
```

## 4. Git cleanliness (start vs end)

`git status --short` before any work and after all mutations + report writing — the 15 lines are **identical line-for-line**:

```
 M .agenticdoc/_index.parallel
 M .agenticdoc/_pitfalls.md
 M packages/coding-agent/CHANGELOG.md
 M packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
 M packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
 M packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts
 M packages/coding-agent/test/extensions/agent-team-loop.test.ts
?? .agenticdoc/mw-worker-visibility-gate/
?? .tmp/
?? hello-world.txt
?? packages/coding-agent/Python/
?? packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-claim.ts
?? packages/coding-agent/test/extensions/agent-team-loop-phase-docs-gate.test.ts
?? packages/coding-agent/test/extensions/agent-team-loop-pm-state-claim.test.ts
?? packages/coding-agent/test/extensions/agent-team-loop-pm-state-sync.test.ts
?? packages/coding-agent/test/extensions/agent-team-loop-watch-aggregate.test.ts
```

(The two deliverables of this task — this report and `workers/mwvg-t5-verify/output.md` — live inside the already-untracked `.agenticdoc/mw-worker-visibility-gate/`, so the status line set is unchanged. All pre-existing modifications belong to T-1/T-2/T-3/T-6 + the session's earlier keys; this task added no repo changes of its own, and both mutated files were restored byte-identically, proven by the sha256 pairs above.)

## 5. Gap list

1. **VC-013 letter gap (the only finding; 0 FAIL overall)**: the P-011 entry substantively carries all three calibrations — 索引行 (index row is authoritative), 两处必须同值 (both places must hold the same value), liveness (liveness is judged on the index row) — and the date + source key. But the AC-013/VC-013 literal term `两处同值` as a **contiguous substring** occurs 0 times; the entry phrases it `两处必须同值`. A quality gate that greps the raw text for the exact term would count keywords=2. Suggestion (one-word edit, PM's call, spec is locked): either append the exact term to the P-011 rule line (e.g. `**两处同值**（两处必须同值）——`) or record that the semantic equivalent satisfies AC-013.
2. Task-book regression-count prediction (203) vs actual (204): no overlap materializes; "以实跑为准" applies. Not a code gap.
3. No other gaps: all 13 VCs reproduced with self-constructed inputs; all 3 mutations caught red and restored byte-identically; regression 204/204 + `npm run check` EXIT=0.

## 6. Scope compliance

- Only new files created in the repo: this report + `workers/mwvg-t5-verify/output.md` (deliverables). No T-1/T-2/T-3/T-6 deliverable was touched.
- Mutations touched exactly 2 source files within their windows; both restored with byte-identical sha256 (evidence above). `pm-orchestrator.ts` was never mutated.
- No `dist/**`, no Python, no `mw build`, no commits, no test-file changes.
- All probe/experiment code lives in `os.tmpdir()` (`C:\Users\WENBOZ~1\AppData\Local\Temp\mwvg-t5\`), including the HEAD-baseline extraction (`head-ui-bridge.ts`) and its `node_modules` junction for bare-specifier resolution; none of it pollutes the repo.
