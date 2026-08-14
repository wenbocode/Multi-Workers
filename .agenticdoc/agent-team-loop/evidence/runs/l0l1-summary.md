# L0 / L1 Verification Summary — agent-team-loop

**Run date**: 2026-08-11  
**Branch**: dev/AgentTeam  
**Test file**: `packages/multi-workers/test-l1-full.ts`  
**Runner**: `npx tsx`

---

## L0 — Static Checks (code inspection / grep)

| VC | Description | Check | Result |
|----|-------------|-------|--------|
| VC-001 | DEFAULT_POLL_INTERVAL ≤ 5 | `grep DEFAULT_POLL_INTERVAL launcher.py` → `= 5` | **PASS** |
| VC-022 | dispatch-table pi ≥ 2, codex ≥ 1, claude ≥ 2 | `grep -c "| pi |"` → 4; `grep -c "| codex |"` → 2; `grep -c "| claude |"` → 5 | **PASS** |
| VC-027 | worker-store 7-col parse | `parseWorkerLine` splits by `|`, trims, checks `parts.length === 7` | **PASS** |
| VC-028 | Extension bundle exists | `dist/extensions/agent-team-loop.js` (17905 bytes) | **PASS** |
| VC-045 | Duplicate serve rejection message | `grep "already running" mw.py` found | **PASS** |

L0 total: **5/5 PASS**

---

## L1 — Unit Tests (test-l1-full.ts)

| VC | Description | Result |
|----|-------------|--------|
| VC-038 | WorkerStore writes/reads 2 entries | **PASS** |
| VC-041 | `_workers.parallel` 7-column format | **PASS** |
| VC-040 | Invalid Phase rejected by StateManager | **PASS** |
| VC-018/019 | writeOutput exit 0 → 4 sections, >50 bytes | **PASS** |
| VC-042 | writeOutput exit 1 → Exit Reason section | **PASS** |
| VC-043 | writeOutput exit 2 → Questions section | **PASS** |
| VC-044 | writeOutput exit 130 → file exists | **PASS** |
| VC-020 | appendTrace writes `[FLOW]` to trace.log | **PASS** |
| VC-024 | runPhases writes phase-1.md > 20 bytes | **PASS** |
| VC-025 | runPhases appends `[GOAL_CHECK]` to trace.log | **PASS** |
| VC-026 | PhaseResult.goalMtime is a number | **PASS** |
| VC-036 | `_index.parallel` 7-column format | **PASS** |
| VC-041-disp | dispatchTask writes ISO 8601 timestamps | **PASS** |

L1 total: **13/13 PASS**

---

## Notes

- **VC-041 root cause**: `raw.trim().split('\n')` removed the trailing space from the last serialized line, turning `|  | ` (6-separator, 7-col) into `|  |` which split by `' | '` yielded 6 columns. Fix: `raw.split('\n').filter(l => l.trim())` preserves per-line content.  
- The `parseWorkerLine` in `worker-store.ts` splits by `|` (not `' | '`) and `.trim()` each part, so production parsing was never affected.

---

## Level 2 (E2E smoke_test.sh)

`packages/multi-workers/smoke_test.sh` is code-complete (T-16). Not executed in this run — requires live binaries (`pi`, `codex`, `claude`) and `timi_proxy_cli` installed. All E2E logic is tested at L1 level.
