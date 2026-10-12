# verify-run-2026-10-09 — mw-rag-integration re-verification (stale re-dispatch)

> **Context.** This file is NOT the authoritative K1/K2 record for key
> `mw-rag-integration`. That record is `evidence/verify-run-2026-09-22.md`
> (committed, 28/28 VC PASS) and the key is `DONE` in `.agenticdoc/_index.parallel`
> since 2026-09-22 18:56. This run was triggered by a **stale re-dispatch** of
> `workers/mw-rag-t11-verify/task.md` on 2026-10-09 (the worker row was replayed
> from `_workers.parallel`, together with ~200 other already-closed worker rows).
> The purpose of this file is to record what a fresh re-verification of the
> **current** tree yields, and to report the one VC that no longer reproduces.
>
> All outputs are raw PowerShell/vitest/pytest stdout captured on this machine
> (Windows, 2026-10-09). Values equal to the `design.md` §7 `Output:` expectations
> are PASS unless stated otherwise.

## 0. Environment under which this run happened (read first)

The concurrent replay of ~200 stale worker rows means the git working tree was
being mutated **while these commands ran**. Evidence of that live mutation:

- `packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts` was
  observed modified (`requireString2`) and then reverted to the committed
  `optionalTrimmedString` seconds later.
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`
  became modified (`--project=.` vs `--project=${projectDir}`) during the run.
- `packages/multi-workers/{autopilot/effective_config.py,mw.py,test_common.py,
  test_autopilot_xkey_registration.py,test_mw_autopilot_cli.py}` are modified by
  other keys' live workers.
- A foreign git worktree `H:/git/Multi-Workers/.tmp-t13-wt` (created by the
  concurrently running `mw-rag-t13-toolmap` replay) contains a copy of
  `biome.json` and breaks root-level `npm run check` (see §5).

Consequences: (a) contention-induced failures are distinguished from real ones by
isolation re-runs below; (b) the RAG bundle was deliberately **not** rebuilt (see §6)
because any rebuild would fold another key's in-progress edit into this key's
tracked artifact.

`python` on this box resolves to the slow Windows Store App Execution Alias
(`WindowsApps\python.exe`, `python -c "print('hi')"` = **13,475 ms**). The RAG
`transport: skill` tests spawn `python`; where that matters, the direct
interpreter (`...\Python\pythoncore-3.14-64\python.exe`, 4,664 ms) was injected
via `MW_RAG_PYTHON`, which is exactly the documented override.

## 1. Command inventory

| # | Command | Workdir | Result |
|---|---|---|---|
| 1 | `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-*.test.ts` (file list) | `packages/coding-agent` | 1 failed | 122 passed | 7 skipped (130); the 1 failure is env contention, see §3 |
| 2 | `MW_RAG_PYTHON=<real py> node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-transport.test.ts` | `packages/coding-agent` | **11 passed (11)** — isolation re-run of the #1 failure |
| 3 | `MW_RAG_SLOW=1 node ... --run test/suite/rag-e2e-slow.test.ts` | `packages/coding-agent` | **1 failed (1)** — VC-017 L2 regression, see §4 |
| 4 | `python -m pytest test_rag_*.py -q -s` | `packages/multi-workers` | 1 failed | 95 passed; the 1 failure is a transient lock, see §3 |
| 5 | `python -m pytest test_rag_*.py::...guard... -q` (isolation) | `packages/multi-workers` | **1 passed** |
| 6 | `python -m pytest -q` (full, non-e2e) | `packages/multi-workers` | 7 failed | 1381 passed | 10 deselected (659.95 s) — attribution in §5 |
| 7 | isolation re-run of the 7 failures | `packages/multi-workers` | 5 passed, **2 still failed** (both autopilot, not RAG) |
| 8 | `npx tsgo --noEmit` | repo root | **exit 0**, no diagnostics |
| 9 | `npx biome check packages` (read-only, scoped) | repo root | **exit 0** — Checked 1104 files, No fixes applied |
| 10 | `check:pinned-deps` / `check:ts-imports` / `check:shrinkwrap` / `check:install-lock` / `check:browser-smoke` | repo root | all **exit 0** |
| 11 | `npm run check` (root, as written) | repo root | **exit 1** at biome because of the foreign `.tmp-t13-wt/biome.json` (see §5) |
| 12 | fresh esbuild build → temp file, compare to tracked bundle | repo root | differs from tracked by exactly 1 line = a foreign in-progress edit (see §6) |

## 2. Per-VC result table (fresh 2026-10-09 run)

`[VERIFY]` lines recovered from runs #1/#2 (TS) and #4 (Python). Lines are shown
verbatim (leading vitest progress dots stripped).

| VC | Layer | Source | Verdict | Fresh output |
|---|---|---|---|---|
| VC-001 | L1 | T-04 | PASS | `[VERIFY] VC-001: rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true budget_file_absent=true`; `[VERIFY] VC-001: injected_vars=0` |
| VC-002 | L1 | T-01 | PASS | `[VERIFY] VC-002: server=S url_match=true origin=project` |
| VC-003 | L1 | T-04 | PASS | `[VERIFY] VC-003: rejected=true error_kind=unknown-rag-server queued=0` |
| VC-004 | L1 | T-04 | PASS | `[VERIFY] VC-004: tools=6 chat_visible=false server_enums=6/6` |
| VC-005 | L1 | T-04 | PASS | `[VERIFY] VC-005: error_kind=capability message_match=true api_calls=0` |
| VC-006 | L1 | T-02 | PASS | `[VERIFY] VC-006: citation_roundtrip=true line_hint=123 exists=true` |
| VC-007 | L1 | T-02 | PASS | `[VERIFY] VC-007: unconfigured_hint=true missing_file_distinct=true` |
| VC-008 | L1 | T-02 | PASS | `[VERIFY] VC-008: research_rewrite=true coding_rewrite=false`; `[VERIFY] VC-008: role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search` |
| VC-009 | L1 | T-03 | PASS | 10 lines incl. `session_handshake=true ... requests=2`, `error_kind=connect elapsed_lt_2000ms=true elapsed_ms=7`, `reset_kind=connect`, `slow_kind=timeout throttled=true`, `delivered_lost_kind=timeout delivered=true calls=2`, `http500_kind=protocol missing_session_kind=protocol`, `tool_error_kind=tool`, `token_ok=true mismatch_kind=protocol secret_hits=0`, `cli_argv_intact=true shell_used=false`, `cli_exit2=connect cli_exit3=tool` |
| VC-010 | L1 | T-05 | PASS | `[VERIFY] VC-010: short_circuited=true api_calls=0 capability_not_counted=true` |
| VC-011 | L1 | T-05 | PASS | `[VERIFY] VC-011: rag_call_types=6 impact_results_semantics=affected-files` |
| VC-012 | L1 | T-05 | PASS | `[VERIFY] VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true` |
| VC-013 | L2 | T-05/T-06 | PASS | `[VERIFY] VC-013: secret_hits=0 error_redacted=true argv_clean_scope=T-07/T-08`; `[VERIFY] VC-013: secret_hits=0 argv_clean=true token_in_env=true measured=spawn-argv`; `[VERIFY] VC-013: secret_hits=0 enabled=A disabled_token_absent=true`; `[VERIFY] VC-013: provider_creds=0 rag_token_envs=0`; `[VERIFY] VC-013: secret_hits=0 argv_clean=measured_in:test_rag_launcher error_redacted=true` |
| VC-014 | L2 | T-10/T-14 | PASS | `[VERIFY] VC-014: required_unused_emitted=true output_marked=true idempotent=true`; `citation_present_emitted=false`; `not_required_writes=0`; `rag_disabled_writes=0`; py: `status=done trace=rag-required-missing output_marked=true` |
| VC-015 | L0+L1 | T-09 | PASS | `[VERIFY] VC-015: parity_unchanged=pass tools=11 conductor_dispatchable=false`; `rag_chat_visible_only_for=rag-research gated_types=5`; py: `registry_entry=rag-research tool_count=11`, `role=research`, `conductor_dispatch_refused=true queued=0 timeline=type-rejected`, `l0_untouched=true` |
| VC-016 | L1 | T-05 | PASS | `[VERIFY] VC-016: rejected=true chat_calls=2 concurrent_single_grant=true` |
| **VC-017** | L1+L2 | T-05 (L1) / T-11 (L2) | **L1 PASS / L2 FAIL** | L1: `[VERIFY] VC-017: heartbeat_interval_le_30s=true pings=5 l2_worker_alive_scope=T-11`. **L2: run #3 FAILED — no `[VERIFY] VC-017: worker_alive=...` line emitted** (see §4) |
| VC-018 | L1 | T-09 | PASS | `[VERIFY] VC-018: doc_exists=true sections=6 citations_parseable=true`; plus the three negative cases `missing_section_detected=true sections=5`, `unparseable_citation_detected=true count=1`, `missing_doc_detected=true sections=0` |
| VC-019 | L1 | T-10 | PASS | `[VERIFY] VC-019: negative_exit=1 scan_boundary=rag-dir-only attribution=present writes=0` |
| VC-020 | L1 | T-10/T-14 | PASS | `worker_reads_phase=true missing=unknown`; `phase_written=true ts_empty_byte_identical=true`; py: `role_only=missing phase_only=missing call_without_citation=missing`, `phase_empty_byte_identical=true golden_match=true`, `phase_written=true value=DESIGN`, `phase_written=true worker_reads_phase=true audit_consistent=true`, `unknown_phase_omitted=true scratch_omitted=true`, `audit_consistent=true phase=design required_missing=1` |
| VC-021 | L1 | T-05/T-10/T-14 | PASS | `[VERIFY] VC-021: degraded_flag=true trace_delta=rag-rewrite-degraded clean_delta=0` (TS and py) |
| VC-022 | L2 | T-07 | PASS | `[VERIFY] VC-022: torn_refused=true unrelated_change_ok=true health_excluded=true`; `golden_bytes=347 idempotent=true` |
| VC-023 | L1 | T-08 | PASS | `[VERIFY] VC-023: sync_installed=true sha_match=true activate_no_write=covered_by(T-04 VC-001)` |
| VC-024 | L0+L1 | T-01/T-06 | PASS | `[VERIFY] VC-024: field_merge=true array_replace=true null_delete=true origin_per_field=true` (TS and py) |
| VC-025 | L1 | T-05 | PASS | `[VERIFY] VC-025: cumulative_rejected=true wall_guard_chat_rejected=true cheap_call_allowed=true` |
| VC-026 | L0 | T-02 | PASS | `[VERIFY] VC-026: grammar_cases=5 roundtrip=5/5` |
| VC-027 | L0+L1 | T-12 | PASS | `[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fixture_digest_match=true` |
| VC-028 | L1 | T-13 | PASS | `[VERIFY] VC-028: mapped_names=6/6 sources_merged=true multi_rounds_tool=rag_search_multi_rounds` |

Tally: **27 PASS / 1 FAIL (VC-017 L2)**. Per the task's completion rule this is a
blocking FAIL, so no PASS claim is made for this re-run.

## 3. Contention failures that pass in isolation (not regressions)

### 3.1 `rag-transport.test.ts` (TS)

Run #1 failed:

```
FAIL  test/suite/rag-transport.test.ts > cli bridge (skill transport) > maps exit codes 0/2/3 to success/connect/tool
Error: Test timed out in 30000ms.
...
Error: EPERM, Permission denied: \\?\C:\Users\...\Temp\rag-transport-t8jGI2
 Test Files  1 failed | 14 passed | 1 skipped (16)
      Tests  1 failed | 122 passed | 7 skipped (130)
```

Root cause is the interpreter, not the code: the test spawns the resolved
interpreter twice inside a 30 s test budget; the machine's `python` alias costs
~13.5 s per spawn (§0). Isolation re-run with the direct interpreter
(`MW_RAG_PYTHON=...pythoncore-3.14-64\python.exe`) gives:

```
[VERIFY] VC-009: cli_exit2=connect cli_exit3=tool
 Test Files  1 passed (1)
      Tests  11 passed (11)
   Duration  29.91s
```

Exit 0. So the failure is environment (Windows Store alias + machine load), not a
RAG regression.

### 3.2 `test_rag_cli.py::...guard...` (Python)

Run #4 failed with a transient lock:

```
E  PermissionError: [Errno 13] Permission denied: 'H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\pm\pm-orchestrator.ts'
1 failed, 95 passed in 126.91s
```

The guard scans all extension `.ts` files; a concurrent worker held
`pm-orchestrator.ts` open. Isolation re-run:

```
test_rag_cli.py::RagCliTest::test_extension_source_never_references_the_installed_skill
1 passed in 0.19s
```

Not a regression.

## 4. VC-017 L2 FAIL — detail, root cause, evidence

### 4.1 Observed result (run #3)

```
[worker] start task=t-slow type=rag-research phases=-
[worker] failed exit=1 elapsed=1m tools=0
x
 FAIL  test/suite/rag-e2e-slow.test.ts > VC-017 L2: 180s rag_chat under a 60s idle watchdog > worker survives the slow call; rag_call ms >= 180000; watchdog armed
AssertionError: expected "Mock" to not be called at all, but actually been called 1 times
Received:
  1st Mock call: Array [ 1 ]
 test/suite/rag-e2e-slow.test.ts:209:25
    207|     expect(SLOW_MS).toBeGreaterThanOrEqual(180_000);
    208|     // Worker alive: the idle watchdog never fired its process.exit(1).
    209|     expect(exitSpy).not.toHaveBeenCalled();
    210|     // Heartbeat kept the idle watchdog fed.
    211|     expect(pings).toBeGreaterThanOrEqual(4);
 Test Files  1 failed (1)
      Tests  1 failed (1)
   Duration  184.91s (tests 180.20s)
```

Interpretation: the worker was killed by the idle watchdog at ~60 s
(`[worker] failed exit=1 elapsed=1m`, `exitSpy` called with `1`) even though the
`rag_chat` call was in flight for 180 s. The `[VERIFY] VC-017: worker_alive=...`
line was never reached, so the L2 half of VC-017 has **no evidence** on the
current tree.

### 4.2 Root cause: a later key changed the `tool_execution_update` contract

The test feeds the heartbeat through a payload-less fake event:

```
test/suite/rag-e2e-slow.test.ts:
  () => {
      pings += 1;
      worker.emit("tool_execution_update");   // <- no payload
  },
```

The contract changed in commit `b8bc115ff` ("redesign the autopilot gate
propositions with bounded auto-decision"), which introduced in-flight-tool
tracking and made the handler dereference `event.toolCallId` unconditionally:

```
# git show 75298ee4e (the commit that added rag-e2e-slow.test.ts):
    pi.on("tool_execution_update", touch);

# git show b8bc115ff (later commit, current HEAD):
    pi.on("tool_execution_update", (event) => {
        const tool = inFlightTools.get(event.toolCallId);   // <- throws on undefined
        if (tool) tool.lastActivityAt = Date.now();
        touch("tool_update");
    });
```

With `payload === undefined`, `event.toolCallId` throws inside
`worker.emit(...)`; the throw is swallowed by `withHeartbeat`'s `try/catch`
(`rag/budget.ts:279`), so `touch("tool_update")` is never reached, the 60 s idle
watchdog sees no activity for 60 s, and it kills the worker. The later commit did
not update the default-skipped slow test, so nothing caught it in CI (the test is
`describe.skipIf(MW_RAG_SLOW !== "1")`).

`git log` proof of the contract change:

```
$ git log --oneline -S "inFlightTools" -- .../worker/worker-mode.ts
b8bc115ff feat(multi-workers,coding-agent): redesign the autopilot gate propositions with bounded auto-decision
$ git log --oneline -- .../test/suite/rag-e2e-slow.test.ts
75298ee4e feat(multi-workers,coding-agent): RAG integration closure (window surface, config parity, config guide) plus the pending worktree keys
```

The slow test is committed earlier than the handler change, and the handler
change is the only writer of that contract.

### 4.3 Why this was not fixed here

- Task hard constraint: **既有测试零修改** (`rag-e2e-slow.test.ts` is a committed
  `*.test.ts`).
- Key `mw-rag-integration` is `DONE`; the offending commit belongs to a different
  key. Per `AGENTS.md` a non-trivial change needs an active key, so a worker on a
  closed key must not write the one-line fix (adding a payload to the emit).
- The task explicitly says: a VC that cannot be evidenced must be reported, not
  papered over. Hence VC-017 L2 is reported **FAIL**, not "未验证".

## 5. Full-suite runs

### 5.1 `npm run check` (root) — blocked by a foreign worktree

```
$ npm run check
  × Found a nested root configuration, but there's already a root configuration.
  i The other configuration was found in H:\git\Multi-Workers.
  × Biome exited because the configuration resulted in errors. Please fix them.
exit=1
```

Cause: `H:/git/Multi-Workers/.tmp-t13-wt` is a git worktree (detached at
`10446aefb`) created by the concurrently running `mw-rag-t13-toolmap` replay
worker; it contains its own `biome.json`, which root-level `biome check .`
discovers as a nested root config. It is not this key's artifact and was not
touched (deleting another session's worktree violates the repo's git rules).

Equivalent, non-destructive measurements that all pass:

```
$ npx biome check packages
Checked 1104 files in 576ms. No fixes applied.        # exit 0

$ node scripts/check-pinned-deps.mjs          # exit 0
$ node scripts/check-ts-relative-imports.mjs  # exit 0
$ node scripts/generate-coding-agent-shrinkwrap.mjs --check
packages/coding-agent/npm-shrinkwrap.json is up to date.   # exit 0
$ node scripts/generate-coding-agent-install-lock.mjs --check
packages/coding-agent/install-lock is up to date.          # exit 0
$ node scripts/check-browser-smoke.mjs        # exit 0
$ npx tsgo --noEmit                           # exit 0, no diagnostics
```

So every component of `npm run check` is green; the single blocker is the foreign
nested `biome.json`.

### 5.2 `python -m pytest -q` (packages/multi-workers)

```
7 failed, 1381 passed, 10 deselected in 659.95s (0:10:59)
```

Failures and attribution (isolation re-run of all 7):

| Test | Isolation re-run | Attribution |
|---|---|---|
| `test_rag_docs.py::RagDocsTest::test_vc206_manual_matches_print_output` | **passed** | contention (tree mutated mid-run) |
| `test_rag_init.py::RagInitTest::test_vc201_clean_project_creates_a_usable_config` | **passed** | contention |
| `test_rag_research.py::test_registry_snapshot_matches_ts_allowlists` | **passed** | contention (TS allowlists being edited) |
| `test_mwpp_collection_parity.py::test_vc008_allowlist_snapshot_unchanged` | **passed** | contention (image-model allowlist churn) |
| `test_update_env.py::TestCheckUpdateEnv::test_sourcemap_anchor_flags_historical_181a75332_shape` | **passed** | contention (`status-model.ts` temporarily absent) |
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | **still fails** | NOT RAG — frozen git-blob assertion vs a concurrently edited source (`frozen=219ed80…` vs `git_blob=6be60fe…`) |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | **still fails** | NOT RAG — reads another key's L3 rounds and the live round-3 report does not match the last round (`assert 3 in [2]`); gate-verdict churn from the live autopilot workers |

Neither persisting failure imports RAG code; both are driven by the live
`mw-autopilot-*` / gate-redesign workers editing their own sources. **No RAG test
is red in isolation.**

`test_autopilot_l0.py` is unchanged: `git diff --stat packages/multi-workers/test_autopilot_l0.py` is empty.

## 6. Extension bundle audit (deliberately NOT rebuilt)

The tracked bundle `packages/multi-workers/dist/extensions/agent-team-loop.js`
already carries the RAG tool-name mapping:

```
$ Select-String ... graph_query|rag_search_multi_rounds|list_collections  -> 5 hits
```

A fresh esbuild build of `index.ts` (same options as `build-extension.sh`) was
written to a temp file and compared line-by-line with the tracked bundle. It
differed by **exactly one line**, and that line matched a foreign uncommitted
working-tree edit (observed twice):

- build #1 vs tracked: `requireString2` vs `optionalTrimmedString` for
  `server '<name>'.skill.dir` — matched a transient working-tree edit of
  `rag/config.ts`; HEAD's version is `optionalTrimmedString`, same as the bundle.
- build #2 vs tracked: `--project=.` vs `--project=${projectDir}` — matched the
  concurrent edit of `shared/mw-runner.ts`.

Conclusion: the tracked bundle is byte-current with the committed HEAD source
(the only deltas were other sessions' in-progress edits). Rebuilding would have
written another key's uncommitted change into this key's tracked artifact, and
would race the ~200 concurrent workers; per `AGENTS.md` that stomp is not done.
This is an explicit, documented deviation from T-11's "must rebuild" instruction,
with the intent (tracked bundle reflects this key's source) already satisfied.

## 7. Modification-surface audit

- Hard assertion: `git diff --stat packages/multi-workers/test_autopilot_l0.py`
  → **empty** (zero diff).
- Hard assertion: no `index.ts` modified by this key (`git status -- '**/index.ts'`
  → empty).
- This key's RAG source/test surface is **clean** w.r.t. HEAD:
  `git status --porcelain -- .../agent-team-loop/{rag,worker,pm,shared}
  packages/multi-workers/{skills,README.md,test_rag_*.py}
  packages/coding-agent/docs/environment-variables.md
  packages/*/CHANGELOG.md .../dist/extensions/agent-team-loop.js`
  → empty at audit time.
- Uncommitted changes present in the tree belong to **other keys' live workers**
  (not this key), observed during the run:
  `packages/multi-workers/{autopilot/effective_config.py,mw.py,test_common.py,
  test_autopilot_xkey_registration.py,test_mw_autopilot_cli.py}`,
  `packages/coding-agent/src/extensions/agent-team-loop/{rag/config.ts,
  rag/adapter.ts,shared/mw-runner.ts}`, plus many `.agenticdoc/<other-key>/**`
  evidence files and the foreign worktrees `.tmp-t13-wt/`, `.tmp-worker-t22/`,
  `.tmp/`, `hello-world.txt`.
- Environment noise (not this key, not deleted, not committed):
  `packages/coding-agent/Python/_cache/` (Python install-manager cache),
  `packages/ai/src/providers/data/` (gitignored generated model data).

No file was written by this verification except this evidence file and
`workers/mw-rag-t11-verify/output.md`.

## 8. Guard blunt-edges (repeated for the record)

1. `test_rag_cli.py:344` flags any `.ts` source that contains the literal
   `mw-rag.md` or `mw-rag/SKILL` — a text-layer proxy for "the extension must not
   install the skill". Comments are collateral damage (T-04 and T-09 both had to
   reword comments; the guard was NOT relaxed). The guard passes on the current
   tree.
2. `test_autopilot_l0.py:135` bans the literal `- Phase:` in `autopilot/*.py`
   (intent: only `advance_phase.py` may **write** that interface line). The reader
   in `autopilot/dispatch.py:119,139` splits it: `_PHASE_LINE_KEY = "Phase:"` and
   `prefix = "- " + _PHASE_LINE_KEY`. Reading is collateral damage; code and test
   both stay as-is.

## 9. Documentation / CHANGELOG (already landed; verified present, not re-edited)

- `packages/multi-workers/README.md`: RAG section present, including the AC-018
  logical→wire mapping table: `rag_search`→(`rag_search_multi_rounds` when rewrite
  on), `rag_graph`→`graph_query`, `rag_sources`→`list_sources`+`list_collections`
  (merged), the rest same-name (README lines ~365-369).
- `packages/coding-agent/docs/environment-variables.md`: `MW_RAG_SERVERS_FILE`
  (line 99), `MW_RAG_SERVERS_HOME` (100), `MW_RAG_PYTHON` (101).
- Both `CHANGELOG.md` `## [Unreleased] → ### Added` sections carry the RAG
  entries (plus other keys' entries).
- These were already written under the original T-11 closure; they are not
  duplicated here.

## 10. Limitations

- **Not tested against a real rag-mcp service.** AC-018/VC-028 and all RAG
  behaviour are validated against fixtures built from the vendor
  `references/tools-reference.md`; no live server was contacted. This limitation
  is inherited from the original key and still stands.
- This re-run does not supersede `evidence/verify-run-2026-09-22.md`; the latter
  remains the K1/K2 record for the closed key.
- The working tree was moving during the run; contention failures were classified
  by isolation re-runs, which is weaker than a frozen tree but is the only option
  in this environment.
- VC-017 L2 is the sole FAIL; all other 27 VCs reproduce PASS on the current tree.
