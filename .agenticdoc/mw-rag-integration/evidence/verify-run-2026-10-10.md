# verify-run-2026-10-10 — `mw-rag-integration` re-verification (stale mass re-dispatch)

> **This is NOT the authoritative K1/K2 record for key `mw-rag-integration`.**
> That record is `evidence/verify-run-2026-09-22.md` (committed, 28/28 VC PASS).
> The key has been `DONE` in `.agenticdoc/_index.parallel` since 2026-09-22 18:56,
> and the follow-on keys `mw-rag-integration-fix`, `mw-rag-config-guide` and
> `mw-rag-window-parity` are also `DONE`.
>
> This file records what a fresh re-verification of the **current** tree yields.
> It was triggered by a **stale mass re-dispatch**: on 2026-10-10T02:50Z the whole
> `.agenticdoc/_workers.parallel` history (≈200 already-closed worker rows,
> including this one) was set back to `running` and replayed.
>
> **Result: 27 PASS / 1 FAIL.** The single FAIL is VC-017 L2 (180s slow call under
> the idle watchdog); its L1 half still passes. Root cause and evidence in §3.
> Per the task's completion rule this is a blocking FAIL, so no PASS claim is made.

## 0. Environment under which this run happened (read first)

- HEAD: `10446aefb69c1ccf2505cf1e3d8cfa7edc39d48b` — *docs(agentic): close
  mw-autopilot-slot-capacity with its gold-gate evidence and leftovers*
  (2026-10-09 16:30 +0800).
- Machine: Windows, PowerShell 5.1 host; `node v24.19.0`, `npm 11.17.0`.
  `python` resolves to the slow Windows Store alias; the real interpreter used for
  every Python command below is
  `C:\Users\wenbozhou\AppData\Local\Python\pythoncore-3.14-64\python.exe` (3.14.3,
  pytest 9.0.2) — the same kind of override the docs sanction (`MW_RAG_PYTHON`).
- **The working tree was moving for the whole run.** ~200 replay workers were
  concurrently editing other keys' files. Directly observed during the run:
  - `packages/coding-agent/src/extensions/agent-team-loop/{pm/ui-bridge.ts,
    rag/adapter.ts,autopilot/console.ts,autopilot/status-model.ts,
    shared/phase-docs.ts}` were modified and reverted repeatedly by other
    sessions (e.g. a fresh esbuild build differed from the tracked bundle by
    `fs23.mkdirSync(taskDir,…)` placement and by `KEY_STATUSES` missing
    `pending-review` at different instants).
  - At **~11:29–11:31 local** a concurrent process ran a mass working-tree
    checkout/restore: `git status` showed **3056 tracked files as deleted**
    (including all of `packages/coding-agent/src/**`), then the count fell back to
    0 over ~2 minutes. Nothing in this key was written during that window; the
    tree was restored to HEAD (the foreign edits above were discarded).
- Consequence: every measurement below is tagged with whether it ran **before**
  or **after** that restore. Where a batch failure could be contention, an
  isolation re-run is included (§6). No isolation re-run of a RAG test failed.

## 1. Command inventory

Full raw stdout/stderr for every command below is archived (durable, not the
ephemeral `$TEMP` copies) in
`evidence/verify-run-2026-10-10-raw/` — e.g. `ts-rag2.txt`, `slow.txt`,
`py-rag3.txt`, `ts-ext.txt`, `py-full.txt`, `npm-check3.txt`,
`phase_axis_check.py`. The per-VC raw lines in §2 are extracted verbatim from
there.

| # | Command | Workdir | Result |
|---|---|---|---|
| 1 | `node ../../node_modules/vitest/dist/cli.js --run <16 × test/suite/rag-*.test.ts>` (pre-restore) | `packages/coding-agent` | 15 passed \| 1 skipped (16); **124 passed \| 6 skipped (130)**; 0 failed |
| 2 | same command (post-restore, clean) | `packages/coding-agent` | 15 passed \| 1 skipped (16); **129 passed \| 1 skipped (130)**; 0 failed; 30.35s |
| 3 | `MW_RAG_SLOW=1 node … --run test/suite/rag-e2e-slow.test.ts` | `packages/coding-agent` | **1 failed (1)**; 180.06s — VC-017 L2, see §3 |
| 4 | `python -m pytest test_rag_*.py -q -s` (8 files, pre-restore) | `packages/multi-workers` | **96 passed**; 139.88s |
| 5 | same command (post-restore, clean) | `packages/multi-workers` | **96 passed**; 13.65s |
| 6 | `node … --run <13 × autopilot-*/worker test/suite/*.test.ts>` | `packages/coding-agent` | 1 failed \| 12 passed (13); **1 failed \| 135 passed \| 1 skipped (137)** |
| 7 | isolation re-run of #6's failing file + the 3 failing extension files | `packages/coding-agent` | **4 passed (4); 209 passed (209)** |
| 8 | `node … --run <21 × test/extensions/agent-team-loop*.test.ts>` | `packages/coding-agent` | 3 failed \| 18 passed (21); **8 failed \| 492 passed \| 2 skipped (502)** |
| 9 | `python -m pytest -q -s` (full, non-e2e) | `packages/multi-workers` | **3 failed \| 1387 passed \| 10 deselected**; 975.25s |
| 10 | isolation re-run of #9's 3 failures | `packages/multi-workers` | 1 passed, **2 still failed** (both non-RAG, other keys/live state) |
| 11 | `npm run check` (pre-restore) | repo root | **EXIT_CODE=0**; Checked 1105 files, No fixes applied; tsgo clean |
| 12 | `npm run check` (post-restore) | repo root | **EXIT_CODE=0** |
| 13 | `build-extension.sh` command chain (esbuild + jiti self-check) writing the tracked bundle | repo root | **exit 0**; `Self-check OK: default export loads as a function (activate)`; bundle sha256 **unchanged** (`52187720…`, 952453 B) |
| 13b | fresh esbuild build of `index.ts` → temp file, sha256 vs tracked bundle | repo root | **byte-identical** (both `52187720…`, 952453 B); see §5 |
| 14 | independent T-14 phase-axis script (`phase_axis_check.py`) | repo root | see §4 |

`[VERIFY]`-visibility caveat (2 prior incidents): vitest runs `silent:
"passed-only"`, so a green-case `console.log` is swallowed — TS evidence lines must
use `process.stdout.write`. All RAG `[VERIFY]` lines below were recovered from raw
stdout; Python lines need `pytest -q -s` (used).

## 2. Per-VC result table (fresh 2026-10-10 run)

Sources: `ts-rag2` = command #2 raw stdout, `py-rag3` = command #5 raw stdout,
`slow` = command #3 raw stdout. Verdict equals the value the `design.md` §7
`Output:` line requires.

| VC | Layer | Source task | Verdict | Fresh output (raw, leading vitest dots stripped) |
|---|---|---|---|---|
| VC-001 | L1 | T-04/T-11 | PASS | `VC-001: rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true budget_file_absent=true` (ts); `VC-001: injected_vars=0` (py) |
| VC-002 | L1 | T-01 | PASS | `VC-002: server=S url_match=true origin=project` |
| VC-003 | L1 | T-04 | PASS | `VC-003: rejected=true error_kind=unknown-rag-server queued=0` |
| VC-004 | L1 | T-04 | PASS | `VC-004: tools=6 chat_visible=false server_enums=6/6` |
| VC-005 | L1 | T-04 | PASS | `VC-005: error_kind=capability message_match=true api_calls=0` |
| VC-006 | L1 | T-02 | PASS | `VC-006: citation_roundtrip=true line_hint=123 exists=true` |
| VC-007 | L1 | T-02 | PASS | `VC-007: unconfigured_hint=true missing_file_distinct=true` |
| VC-008 | L1 | T-02 | PASS | `VC-008: role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search` (the later `mw-rag-integration-fix` key replaced the original `research_rewrite=true coding_rewrite=false` boolean form with this stronger assertion on the actual wire tool name; `fixture_calls=1` still pins a single call) |
| VC-009 | L1 | T-03 | PASS | `VC-009: session_handshake=true session_id_present=true requests=2` / `error_kind=connect elapsed_lt_2000ms=true elapsed_ms=9` / `reset_kind=connect reset_not_timeout=true` / `slow_kind=timeout throttled=true` / `delivered_lost_kind=timeout delivered=true calls=2` / `http500_kind=protocol missing_session_kind=protocol` / `tool_error_kind=tool` / `token_ok=true mismatch_kind=protocol secret_hits=0` / `cli_argv_intact=true shell_used=false` / `cli_exit2=connect cli_exit3=tool` |
| VC-010 | L1 | T-05 | PASS | `VC-010: short_circuited=true api_calls=0 capability_not_counted=true` |
| VC-011 | L1 | T-05 | PASS | `VC-011: rag_call_types=6 impact_results_semantics=affected-files` (the `rag_call` line carries `mcp_tool=`; `evidence.ts:52` appends it, `rag-evidence.test.ts:248,283` pins the format) |
| VC-012 | L1 | T-05 | PASS | `VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true` |
| VC-013 | L2 | T-05/T-06/T-07/T-08 | PASS | ts: `VC-013: secret_hits=0 error_redacted=true argv_clean_scope=T-07/T-08`; py: `secret_hits=0 argv_clean=true token_in_env=true measured=spawn-argv`, `secret_hits=0 enabled=A disabled_token_absent=true`, `provider_creds=0 rag_token_envs=0`, `secret_hits=0 argv_clean=measured_in:test_rag_launcher error_redacted=true` — **`argv_clean` is measured on the real spawn argv** |
| VC-014 | L2 | T-10/T-14 | PASS | ts: `required_unused_emitted=true output_marked=true idempotent=true`, `citation_present_emitted=false`, `not_required_writes=0`, `rag_disabled_writes=0`; py: `status=done trace=rag-required-missing output_marked=true` |
| VC-015 | L0+L1 | T-09 | PASS | ts: `parity_unchanged=pass tools=11 conductor_dispatchable=false`, `rag_chat_visible_only_for=rag-research gated_types=5`; py: `registry_entry=rag-research tool_count=11`, `role=research`, `conductor_dispatch_refused=true queued=0 timeline=type-rejected`, `l0_untouched=true` |
| VC-016 | L1 | T-05 | PASS | `VC-016: rejected=true chat_calls=2 concurrent_single_grant=true` |
| **VC-017** | L1+L2 | T-05 (L1) / T-11 (L2) | **L1 PASS / L2 FAIL** | L1: `VC-017: heartbeat_interval_le_30s=true pings=5 l2_worker_alive_scope=T-11`. L2: `[worker] failed exit=1 elapsed=1m tools=0` + `AssertionError: expected "Mock" to not be called at all, but actually been called 1 times` (exitSpy called with `1`); **no `VC-017: worker_alive=…` line emitted**. See §3. |
| VC-018 | L2 | T-09 | PASS | `doc_exists=true sections=6 citations_parseable=true`; `missing_section_detected=true sections=5`; `unparseable_citation_detected=true count=1`; `missing_doc_detected=true sections=0` |
| VC-019 | L1 | T-10 | PASS | `VC-019: negative_exit=1 scan_boundary=rag-dir-only attribution=present writes=0` |
| VC-020 | L1 | T-10/T-14 | PASS | ts: `worker_reads_phase=true missing=unknown`, `phase_written=true ts_empty_byte_identical=true`; py: `role_only=missing phase_only=missing call_without_citation=missing`, `phase_empty_byte_identical=true golden_match=true`, `phase_written=true value=DESIGN`, `phase_written=true worker_reads_phase=true audit_consistent=true`, `unknown_phase_omitted=true scratch_omitted=true`, `audit_consistent=true phase=design required_missing=1`; **plus the independent re-check in §4** |
| VC-021 | L1 | T-05/T-10/T-14 | PASS | `VC-021: degraded_flag=true trace_delta=rag-rewrite-degraded clean_delta=0` (ts and py) |
| VC-022 | L2 | T-07 | PASS | `VC-022: torn_refused=true unrelated_change_ok=true health_excluded=true`; `golden_bytes=347 idempotent=true` |
| VC-023 | L1 | T-08 | PASS | `VC-023: sync_installed=true sha_match=true activate_no_write=covered_by(T-04 VC-001)` |
| VC-024 | L0+L1 | T-01/T-06 | PASS | `VC-024: field_merge=true array_replace=true null_delete=true origin_per_field=true` (ts and py) |
| VC-025 | L1 | T-05 | PASS | `VC-025: cumulative_rejected=true wall_guard_chat_rejected=true cheap_call_allowed=true` |
| VC-026 | L0 | T-02 | PASS | `VC-026: grammar_cases=5 roundtrip=5/5` |
| VC-027 | L0+L1 | T-12 | PASS | `VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fixture_digest_match=true` |
| VC-028 | L1 | T-13 | PASS | `VC-028: mapped_names=6/6 sources_merged=true multi_rounds_tool=rag_search_multi_rounds` |

Tally: **27 PASS / 1 FAIL (VC-017 L2)**. Missing evidence: none — every VC has a
fresh raw line except the VC-017 L2 half, which is an evidenced FAIL, not a blank.

Assertion-command mapping for the table above (each command is the one whose raw
stdout carries the `[VERIFY]` line; full outputs in §1 / the raw dir):

- TS face of VC-001…VC-018, VC-020, VC-021, VC-024…VC-028 → command **#2**
  (`ts-rag2.txt`; the same lines also appear in the pre-restore `ts-rag.txt`).
- Python face of VC-001, VC-013, VC-014, VC-015, VC-019, VC-020, VC-021, VC-022,
  VC-023, VC-024 → command **#5** (`py-rag3.txt`; pre-restore `py-rag.txt` is
  identical apart from contention).
- VC-017 L1 → command **#2**; VC-017 L2 → command **#3** (`slow.txt`).

The assertion text each line must satisfy is `design.md` §7 `Output:`
(per-VC), reproduced in `evidence/verify-run-2026-09-22.md` §2.

### 2.1 VC-028 / AC-018 mapping cross-check (`mcp_tool`)

The logical→wire table was read directly out of
`packages/coding-agent/src/extensions/agent-team-loop/rag/adapter.ts` (`RAG_TOOL_MAP`):

```
rag_search:   { mcp: ["rag_search"],            multi: "rag_search_multi_rounds" }
rag_symbol:   { mcp: ["rag_symbol"] }
rag_graph:    { mcp: ["graph_query"] }
rag_impact:   { mcp: ["rag_impact"] }
rag_sources:  { mcp: ["list_sources", "list_collections"], merge: "sources" }
rag_feedback: { mcp: ["rag_feedback"] }
rag_chat:     { mcp: ["rag_chat"] }
```

Fresh evidence line: `VC-028: mapped_names=6/6 sources_merged=true
multi_rounds_tool=rag_search_multi_rounds`. The audit side reads the actual wire
name from the evidence line's `mcp_tool=` field (`rag/evidence.ts`), and
`rag-evidence.test.ts` pins the `rag_call … mcp_tool=` format. This matches the
README table (`packages/multi-workers/README.md` lines 363–369).

## 3. VC-017 L2 FAIL — evidence and root cause

### 3.1 Observed (command #3, raw stdout)

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[worker] start task=t-slow type=rag-research phases=-
[worker] failed exit=1 elapsed=1m tools=0
x

 FAIL  test/suite/rag-e2e-slow.test.ts > VC-017 L2: 180s rag_chat under a 60s idle watchdog > worker survives the slow call; rag_call ms >= 180000; watchdog armed
AssertionError: expected "Mock" to not be called at all, but actually been called 1 times
Received:
  1st Mock call:
    Array [ 1 ]
 Number of calls: 1
  test/suite/rag-e2e-slow.test.ts:209:25
    207|     expect(SLOW_MS).toBeGreaterThanOrEqual(180_000);
    208|     // Worker alive: the idle watchdog never fired its process.exit(1).
    209|     expect(exitSpy).not.toHaveBeenCalled();
    210|     // Heartbeat kept the idle watchdog fed.
    211|     expect(pings).toBeGreaterThanOrEqual(4);

 Test Files  1 failed (1)
      Tests  1 failed (1)
   Duration  187.81s (tests 180.06s)
```

The worker was killed by the idle watchdog at ~60 s even though the `rag_chat`
call was in flight for 180 s. The `[VERIFY] VC-017: worker_alive=…` line was never
reached, so the L2 half of VC-017 has **no evidence** on the current tree. The L1
half (`heartbeat_interval_le_30s=true pings=5`) still passes.

### 3.2 Root cause — a later commit changed the `tool_execution_update` handler

The slow test feeds the heartbeat through a payload-less fake event
(`rag-e2e-slow.test.ts:~198`):

```ts
() => {
    pings += 1;
    worker.emit("tool_execution_update");   // <- no payload
},
```

The handler changed in `b8bc115ff` — *feat(multi-workers,coding-agent): redesign
the autopilot gate propositions with bounded auto-decision* (2026-10-09 16:27,
**HEAD~1**, a different key) — which added in-flight-tool tracking and now
dereferences `event.toolCallId` unconditionally
(`worker/worker-mode.ts:933-937`):

```ts
pi.on("tool_execution_update", (event) => {
    const tool = inFlightTools.get(event.toolCallId);   // throws when event === undefined
    if (tool) tool.lastActivityAt = Date.now();
    touch("tool_update");
});
```

With `payload === undefined`, `event.toolCallId` throws inside `worker.emit(...)`;
the throw is swallowed by `withHeartbeat`'s `try/catch`
(`rag/budget.ts:279`), so `touch("tool_update")` is never reached. No other
activity event fires during a 180 s in-flight tool call, the 60 s idle watchdog
sees silence, and it kills the worker. `git log` proof of the contract change:

```
$ git log --oneline -S "inFlightTools" -- .../worker/worker-mode.ts
b8bc115ff feat(multi-workers,coding-agent): redesign the autopilot gate propositions with bounded auto-decision

$ git log --oneline -1 -- .../test/suite/rag-e2e-slow.test.ts
75298ee4e feat(multi-workers,coding-agent): RAG integration closure (window surface, config parity, config guide) plus the pending worktree keys
```

### 3.3 Note on which side is "wrong" (for the PM's decision)

The real pi event type `ToolExecutionUpdateEvent` declares `toolCallId: string` as
required (`core/extensions/types.ts`), so the test's payload-less fake no longer
matches the host contract; conversely the handler could be defensive
(`event?.toolCallId`). Either of these one-liners would make the test pass:

- the test's fake should emit `{ toolCallId: "slow-call-1", … }`; or
- `worker-mode.ts` should read `event?.toolCallId` (and keep `touch()` firing even
  when no tool is in flight).

**Neither was applied here.** The task's hard constraint is *既有测试零修改*, and
`AGENTS.md` requires an active AgenticTask key for implementation — this key is
`DONE` and the offending commit belongs to another closed key
(`mw-autopilot-slot-capacity`). Per the task instruction ("有 FAIL … 停下并在
output.md 写清"), this is reported, not papered over.

## 4. T-14 phase-axis — independent re-check

Script: `$TEMP\t11-verify\phase_axis_check.py` (imports
`packages/multi-workers/autopilot/dispatch.py`). Raw output:

```
[VERIFY] T11-phase: empty_identical=True
[VERIFY] T11-phase: phase_written_head=['---', 'type: coding', 'phase: DESIGN', 'origin: conductor', 'loop: t', 'attempt: 1']
[VERIFY] T11-phase: order_type_before_phase=True type_idx=1 phase_idx=2
[VERIFY] T11-phase: owner_phase_mw_rag='DONE'
[VERIFY] T11-phase: owner_phase_scratch=''
[VERIFY] T11-phase: owner_phase_missing=''
```

- `phase=""` renders **byte-identically** to omitting the argument (`True`), and
  `phase="DESIGN"` writes `phase: DESIGN` immediately after `type: coding` — the
  same facts the Python/TS suites assert (`VC-020: phase_empty_byte_identical=true
  golden_match=true`, `phase_written=true value=DESIGN`, `ts_empty_byte_identical=true`).
- `_owner_phase(repo, "mw-rag-integration")` now returns **`DONE`**, not the
  `EXECUTE` recorded when the original T-11 ran: the key was advanced to `DONE` on
  2026-09-22 18:56, so `pm-state.md`'s `- Phase:` line legitimately reads `DONE`.
  The mechanism is right; the expectation in the task text is stale. `_scratch`
  and a missing key both return `""` (never guessed), as required.
- `mw rag audit` consistency is evidenced by
  `VC-020: audit_consistent=true phase=design required_missing=1` and
  `phase_written=true worker_reads_phase=true audit_consistent=true`.

## 5. Extension bundle (`packages/multi-workers/dist/extensions/agent-team-loop.js`)

The tracked bundle was rebuilt with the exact `build-extension.sh` command chain
(esbuild + the jiti loader self-check) and compared against a temp-file build:

```
$ node <exact build-extension.sh esbuild options, outfile=tracked bundle>
  packages\multi-workers\dist\extensions\agent-team-loop.js  930.1kb
Done in 57ms
Self-check OK: default export loads as a function (activate)
$ sha256 tracked after  = 52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B  (952453 B)
$ sha256 fresh (temp)   = 52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B  (952453 B)
$ git diff --no-index tracked fresh   ->  exit 0 (identical)
$ git status --porcelain -- <tracked bundle>  ->  empty (unchanged vs HEAD)
```

(`build-extension.sh` is a bash script and this box has no working bash — `bash`
resolves to the WSL stub. Its two node commands were replicated verbatim; raw
output in `verify-run-2026-10-10-raw/build-tracked.txt`.)

Conclusion: the tracked bundle **already carries this key's final source** (it was
rebuilt in commit `27e3c927e` after T-14, and the T-14 phase-axis code
`planDispatchFrontmatter` is present in it). The required rebuild was performed and
produced **zero byte change**; `git status` for the bundle stayed clean, so nothing
is stale.

Caveat worth recording: mid-run, while other sessions held uncommitted edits to
`pm/ui-bridge.ts` / `autopilot/status-model.ts`, fresh builds transiently differed
from the tracked bundle by exactly those foreign edits (line placement of
`fs23.mkdirSync(taskDir,…)`; `KEY_STATUSES` missing `pending-review`). After the
mass restore those edits vanished and the build became byte-identical. This is the
same class of interference the 2026-10-09 re-run documented.

## 6. Zero-regression / full-suite results and failure attribution

### 6.1 TS RAG suites

- pre-restore: `15 passed | 1 skipped (16)`, **124 passed | 6 skipped (130)**, 0 failed.
- post-restore (clean): `15 passed | 1 skipped (16)`, **129 passed | 1 skipped
  (130)**, 0 failed, 30.35s.
- The 1 skipped file is `rag-e2e-slow.test.ts` (default-skipped; run explicitly in #3).

### 6.2 TS autopilot / worker suites (`autopilot-*`, `worker-*`, `cross-drive-worker`, `dual-root-worker`)

`1 failed | 12 passed (13)`, **1 failed | 135 passed | 1 skipped (137)**.
Failure: `test/suite/autopilot-gate-presentation.test.ts > … renders one line per
pending gate with age and DRIFT` — expected `DRIFT(`. It **passes in isolation**
(command #7: 209 passed across 4 files), so it was a transient caused by a
concurrent edit to `autopilot/console.ts` (observed modified and reverted during
the run). Not RAG.

### 6.3 TS extension suites (`test/extensions/agent-team-loop*.test.ts`)

`3 failed | 18 passed (21)`, **8 failed | 492 passed | 2 skipped (502)**. All 8
failures are in three files owned by other keys —
`agent-team-loop-vision-autoroute.test.ts`, `agent-team-loop-vision-gate.test.ts`
(mw-vision-role), `agent-team-loop.test.ts` (mw-dispatch-role-escape) — and every
one of them **passes in isolation** (command #7: 209 passed). All are dispatch
refusal / `workerDirExists(...)` assertions, i.e. transient reads of
concurrently-edited dispatch code. None is RAG.

### 6.4 Python full suite

`python -m pytest -q -s` → **3 failed | 1387 passed | 10 deselected** (975.25s).

| failing test | isolation re-run | attribution |
|---|---|---|
| `test_autopilot_pending_review.py::test_t21_shadow_then_live_flip_still_records_the_executed_row` | **passed** | contention (a concurrent worker was toggling `pending-review` in `status-model.ts`) |
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | **still fails** | non-RAG, pre-existing: frozen baseline sha `219ed80…` vs HEAD blob `6be60fe…` (cross-key frozen-expectation drift in `autopilot/dispatch.py`) |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | **still fails** | non-RAG, live external state: reads `H:/git/E2Feature/.agenticdoc/<key>/l3-verdict.txt` + L3 rounds; the live round-3 report does not match the persisted verdict |

None of the three imports RAG code. `test_autopilot_l0.py` is unchanged
(`git diff --stat` empty). The RAG-only sweep `test_rag_*.py` is 96/96 green
(commands #4 and #5).

### 6.5 `npm run check`

Pre- and post-restore both **EXIT_CODE=0**, `Checked 1105 files … No fixes
applied`, `check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` /
`check:install-lock:coding-agent` / `tsgo --noEmit` / `check:browser-smoke` all
silent-or-OK.

## 7. Modification-surface audit

- **Hard assertion — `test_autopilot_l0.py`**: `git diff --stat
  packages/multi-workers/test_autopilot_l0.py` → **empty** (zero diff). ✔
- **Hard assertion — `index.ts`**: `git status --porcelain -- '**/index.ts'` →
  **empty**. This key does not touch `packages/coding-agent/src/extensions/
  agent-team-loop/index.ts`. ✔ (A transient mass-checkout window at ~11:29 showed
  thousands of files as ` D`, all restored; see §0.)
- **This key's RAG extension surface** (`src/extensions/agent-team-loop/{rag,
  worker,pm,shared}/**`, `test/suite/rag-*.test.ts`) is **clean vs HEAD** after the
  mass restore (`git status --porcelain` → empty). The pre-restore foreign edits to
  `rag/adapter.ts`, `pm/ui-bridge.ts`, `worker/worker-mode.ts`,
  `rag-{adapter,parity,transport}.test.ts`, `autopilot/console.ts`,
  `shared/phase-docs.ts` belonged to other replay workers and were discarded by
  that restore.
- **Bundle**: `packages/multi-workers/dist/extensions/agent-team-loop.js` is
  clean vs HEAD and byte-identical to a fresh build (§5). ✔
- **Foreign changes present in the tree at audit time** (NOT this key):
  `.agenticdoc/<many other keys>/**`, and under `packages/multi-workers/`:
  `CHANGELOG.md`, `UPDATE.md`, `docs/rag-config-guide.md`, `autopilot/conductor.py`,
  `autopilot/effective_config.py`, `mw.py`, `mw_common.py`,
  `test_autopilot_pending_review.py`, `test_autopilot_xkey_registration.py`,
  `test_common.py`, `test_doctor_autopilot.py`, `test_mw_autopilot_cli.py`; plus
  untracked `.agenticdoc/mw-gate-verdict-hardening/`,
  `.agenticdoc/mw-workspace-incident-probe/`,
  `.agenticdoc/mw-worktree-junction-guard/`, `.tmp/`, `hello-world.txt`.
  These are live edits by concurrently replayed workers of other keys and are not
  counted as this key's change surface.
- **Environment noise** (standalone, neither deleted nor committed): none of the
  previously-noted `packages/coding-agent/Python/_cache/` exists on this machine
  now; `packages/ai/src/providers/data/` remains a gitignored local generation dir.
- **Nothing in this key was written by this re-run** except
  `evidence/verify-run-2026-10-10.md` and `workers/mw-rag-t11-verify/output.md`.

## 8. Guard blunt-edges (as required by the task)

Both are text-layer proxies that misfire on comments/readers; neither was relaxed.

1. `packages/multi-workers/test_rag_cli.py::test_extension_source_never_references_the_installed_skill`
   matches the literal `mw-rag.md` / `mw-rag/SKILL` in **any** `.ts` source. T-04's
   and T-09's comments were each reworded to get past it. Anyone writing a comment
   that names the shipped skill path will trip it again. It passes on the current
   tree.
2. `packages/multi-workers/test_autopilot_l0.py::test_vc007_static_scan` bans the
   literal `- Phase:` in `autopilot/*.py` (intent: only `advance_phase.py` may
   **write** that interface line). `autopilot/dispatch.py`'s reader splits it as
   `_PHASE_LINE_KEY = "Phase:"` + `prefix = "- " + _PHASE_LINE_KEY`. Reading is
   collateral damage; code and test both stay as-is.

## 9. Documentation / CHANGELOG verification

Already landed by the original T-11 closure; verified present on the current tree
and **not duplicated**:

- `packages/multi-workers/README.md` "RAG 接入（可配置）" section (lines ~296–385):
  two-layer config table, `target.yml` `rag:` example, `mw rag
  list|probe|audit|sync`, the `MW_RAG_SERVERS_FILE` / `MW_RAG_SERVERS_HOME` /
  `MW_RAG_PYTHON` hooks, `token_env`-only credentials, and the **AC-018
  logical→wire mapping table** (lines 363–369). The `phase:` header contract is
  documented at lines 326–328.
- `packages/coding-agent/docs/environment-variables.md`: `MW_RAG_SERVERS_FILE`
  (line 99), `MW_RAG_SERVERS_HOME` (100), `MW_RAG_PYTHON` (101, with the
  Windows-`python` / other-`python3` default).
- `packages/multi-workers/CHANGELOG.md` and `packages/coding-agent/CHANGELOG.md`:
  the `mw-rag-integration` entry sits under `## [Unreleased] → ### Added` (lines 17
  and 15 respectively); released sections untouched.

## 10. Limitations

- **No live rag-mcp service was contacted.** AC-018/VC-028 and all RAG behaviour are
  validated against fixtures built from the vendor
  `references/tools-reference.md`; the wire-name mapping is verified only at the
  adapter/fixture level. A real-server smoke test remains outstanding.
- **The tree moved for the whole run** (§0), including a concurrent mass
  checkout/restore that temporarily deleted 3056 tracked files. Batch failures were
  classified by isolation re-runs, which is weaker than a frozen tree but is the
  only option in this environment. No RAG test is red in isolation.
- This run **does not supersede** `evidence/verify-run-2026-09-22.md`; the key
  remains `DONE` on the strength of that record. This file documents that a fresh
  re-verification of the current tree yields 27/28, with VC-017 L2 broken by a
  later key's commit (`b8bc115ff`).
- VC-017 L2 covers only "worker survives a slow call + heartbeat keeps the
  watchdog fed + watchdog armed"; it does not cover network-flap recovery.
