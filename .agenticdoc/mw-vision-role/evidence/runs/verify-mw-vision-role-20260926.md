# Verification Closeout: mw-vision-role

- key: `mw-vision-role`
- task: `T-14 验证收口与证据账本` (AC-012 / VC-012)
- run date: 2026-09-26
- host: Windows, PowerShell 5.1 host; POSIX commands run through Git Bash (`D:\Program Files\Git\bin\bash.exe`)
- toolchain: node v24.19.0, vitest 4.1.9, Python 3.14.3 (`packages/multi-workers`), pytest
- write face: this document only. No source/test file left modified (see §7.5 restoration hashes).

## 0. Verdict (read this first)

**NOT fully verified.** Two blockers and two evidence gaps:

1. **BLOCKER — VC-012 `check=green` fails.** `npx tsgo --noEmit` is RED with 4 errors in
   `packages/coding-agent/test/suite/rag-required.test.ts` (`description` prop missing). The type
   `planDispatchFrontmatter({... description: string ...})` was made **required** by this key
   (T-05/T-06); `rag-required.test.ts` is unmodified vs HEAD and its 4 `base` call sites predate
   that field. This is introduced by this key (HEAD's signature has no `description`), so it is not
   baseline noise. T-09/T-12 had already surfaced these 4 errors but classified them as another
   session's / HEAD-pre-existing; the type change is this key's.
2. **BLOCKER (deploy/bundle staleness) — the L2-1 procedure as written does not exercise this key's
   code.** The card-exact command (global bundled extension) produced **no** `[IMAGE-CAP]` and
   `rc=0`. Root cause: the globally installed bundle
   `~/.pi/agent/extensions/agent-team-loop.js` (mtime 2026-09-26 15:15:39, 925286 B, source
   `packages/multi-workers/dist/extensions/agent-team-loop.js`, same mtime/size) predates T-09 and
   contains **0** occurrences of `IMAGE-CAP`; it shadows the repo source builtin at runtime. The
   repo source behaves correctly (proven by the isolated `-ne` run in §5.2: `[IMAGE-CAP]` line +
   `rc=1` + `worker.log`/`trace.log`/`output.md`). Post-merge/release action: rebuild + reinstall the
   bundle (`mw build`) so the feature is actually reachable in real windows.
3. **EVIDENCE GAP — VC-003 and VC-007 emit no `[VERIFY]` line.** No test in the repo emits the
   evidence-requirement strings `source=config:vision task_override=task` (VC-003) or
   `queue_delta=1 images_line=yes order_ok=true` (VC-007). The underlying behaviors are exercised
   (VC-007 allow case passes in `agent-team-loop-vision-gate.test.ts`; Python `resolve_dispatch_model`
   has generic role tests) but the machine-readable evidence lines are absent — `resolve_dispatch_model(
   task_type="vision")` is not directly tested anywhere, and the VC-007 allow test has no marker.
4. Scoped tests: **Python 202 passed / 2 failed** (both documented baseline noise, §3) and
   **TS 200 passed / 0 failed**; **biome clean**. So AC-012 is `scoped_tests=green (baseline
   excluded)` + `check=FAILED`.

The remainder of this document is the raw evidence behind those statements.

---

## 1. Step 1 — scoped test raw output (full, untrimmed)

Commands (run from `packages/multi-workers` / `packages/coding-agent`, output `tee` to the paths
below). Logs are kept verbatim at:
`C:/Users/wenbozhou/AppData/Local/Temp/mw-vision-py.log`,
`C:/Users/wenbozhou/AppData/Local/Temp/mw-vision-ts.log`.
The Python console emitted a few cp936 bytes; those invalid UTF-8 bytes are shown as `U+FFFD` here
(no content lines were dropped/trimmed).

### 1.1 Python

```
cd packages/multi-workers
python -m pytest test_dispatch_models.py test_autopilot_l0.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_serve_doctor.py test_rag_phase.py test_autopilot_readcap_injection.py test_common.py -q -s 2>&1 | tee C:/Users/wenbozhou/AppData/Local/Temp/mw-vision-py.log
```

Full output:

```
....................[launcher] Warning: dispatch.yml unreadable: while parsing a flow sequence
  in "<unicode string>", line 1, column 9:
    models: [broken
            ^
expected ',' or ']', but got '<stream end>'
  in "<unicode string>", line 2, column 1:
    
    ^ �� model defaults fall back to the window model / per-cli defaults
............[mw model set] review = timi/glm-5.3-air �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model set] coding = codex/gpt-5.6-sol �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model clear] removed review �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model clear] removed all roles �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_set_show_clear_roundtrip0\.mw\dispatch.yml
.[mw model set] Error: value must be 'prefix/model' (e.g. timi/glm-5.3), got 'noslash'
[mw model set] Error: unknown prefix 'bogus' (valid: claude, claude_cli, codex, codex_cli, deepseek, timi, zai)
.[mw model set] Error: existing dispatch.yml is unusable (dispatch.yml unreadable: while parsing a flow sequence
  in "<unicode string>", line 1, column 9:
    models: [broken
            ^
expected ',' or ']', but got '<stream end>'
  in "<unicode string>", line 2, column 1:
    
    ^) �� fix or remove it before writing
...[mw model set] vision = timi/deepseek-v4-flash-vision-exp �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_yes_writes_vision_role0\.mw\dispatch.yml
...[mw model set] Error: --force is only valid for the 'vision' role (got 'coding'); it only skips the image-capability probe
.[mw model set] main = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] coding = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] review = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] research = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_other_roles_never_probe0\.mw\dispatch.yml
.[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0
[mw model set] vision = timi/deepseek-v4-flash-vision-exp �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_verify_vc0010\.mw\dispatch.yml
.[VERIFY] VC-002: rc=nonzero roles=5
usage: python.exe -m pytest model set [-h] --project PROJECT [--force]
                                      ROLE PROVIDER/MODEL
python.exe -m pytest model set: error: argument ROLE: invalid choice: 'villain' (choose from main, coding, review, research, vision)
.[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0
[mw model set] --force: image-capability probe skipped for timi/glm-5.3
[mw model set] vision = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7605\test_verify_vc0130\.mw\dispatch.yml
[mw model set] Error: timi/glm-5.3 reports images=no �� a 'vision' role model must accept image input
[mw model set] Suggest: pick a vision-capable model, e.g. `mw model set vision timi/deepseek-v4-flash-vision-exp`, or override with `mw model set vision timi/glm-5.3 --force`
......[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip
.[VERIFY] VC-015: show_images=yes/no/unknown rc=0
.[VERIFY] VC-007: phase_direct_writes=0 goal_writes=0 advance_via_script=all files_scanned=15
.[VERIFY] VC-007: runtime_advance_events=2 exit_codes=0,1 schema=exit=<n> on all
.[VERIFY] VC-023: registry_parity=per-type-exact types=7 verifier_entry=explicit ts_buckets=['coding', 'fallback', 'research', 'review']
.[VERIFY] VC-023: unknown_rows=0 rejection=type-rejected fallback=none
.[VERIFY] VC-023: worker_fail_closed=1 ts_suite=autopilot-protocol.test.ts ts_run=passed manual_fallback=full-set
.[VERIFY] VC-014: surfaces=4 token_set_ok=true
.[VERIFY] VC-023: registry_types=7 unknown_tools=0
.[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true
.[VERIFY] VC-023: parity_snapshot_types=7
..[VERIFY] VC-023: optional_fields_omitted=true
.[VERIFY] VC-023: rows=1 row_verified=true lock_cleaned=true timeline_dispatch=true
.[VERIFY] VC-023: scratch_sentinel_key=true
..[VERIFY] VC-023: unknown_rows=0 type_rejected_event=true no_fallback=true
.[VERIFY] VC-023: verifier_scope_required=true verifier_with_scope_rows=1
..[VERIFY] VC-013: single_no_yml_snapshot=true
.[VERIFY] VC-013: deny_globs_line=true control_scope=true
[VERIFY] VC-009: game_abs=true engine_abs=true
.[VERIFY] VC-013: scopeless_deny_injected=true no_scope_forced=true
....[VERIFY] VC-013: broken_yml_rows=0 fail_closed=true
.[VERIFY] VC-008: parity_pass=true snapshot_equal=true keys=11
[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true
......[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve.
.[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve.
....................OK: claimed 'key-a' with ClaimId=WENBOZHOU-PC4:82608
.CONFLICT: key 'key-live' is already active (ClaimId: WENBOZHOU-PC4:25496).
Use --force to take over.
CONFLICT: key 'key-legacy' is already active (ClaimId: 20260808-174558-3176).
Use --force to take over.
OK: claimed 'key-dead' with ClaimId=WENBOZHOU-PC4:82608
OK: claimed 'key-live' with ClaimId=WENBOZHOU-PC4:82608
.[VERIFY] VC-020: phase_empty_byte_identical=true golden_match=true
.[VERIFY] VC-020: phase_written=true value=DESIGN
.[VERIFY] VC-020: phase_written=true worker_reads_phase=true audit_consistent=true
.[VERIFY] VC-020: unknown_phase_omitted=true scratch_omitted=true
.[VERIFY] VC-020: audit_consistent=true phase=design required_missing=1
.[VERIFY] VC-001: tasks=3 file_cap_lines=3 byte_cap_lines=3 order_ok=true ok=true
.[VERIFY] VC-002: readFileCap=64 readByteCap=2097152 equals_config=true fallback_used=false ok=true
.[VERIFY] VC-003: rerender_value=20 cap_literal_assignments=0 ok=true
.[VERIFY] AC-004: file_cap=128 byte_cap=4194304 max_calls=57 max_bytes=913636 renders=true ge_2x=true ok=true
.[VERIFY] AC-005: max_calls=57 max_bytes=913636 derived_rejections=0 tight_rejections=53 ok=true
.[VERIFY] AC-006: dispatched_tasks=1 cap_lines=2 cap_equals_config=true restart_half=deferred_T-006 ok=true
.[VERIFY] VC-007: byte_identical=true cap_lines=0 config_created=false ok=true
.[VERIFY] VC-008: byte_identical=true cap_lines=0 dispatch_ok=true ok=true
.[VERIFY] VC-009: cases=3 exceptions=0 dispatch_ok=3 cap_lines=0 config_contract_unchanged=true ok=true
.[VERIFY] VC-010: cap_file_at=3 cap_byte_over=150 rendered=true ok=true
.[VERIFY] VC-011: invalid_cases=5 unlimited_cases=0 fallback_defaults=true still_blocks=true ok=true
.[VERIFY] VC-012: missing_section=below fail_row=below ok=true
.F.[VERIFY] VC-009: zero_byte=true frozen_copy=true
[VERIFY] VC-009-order: line_order=type<phase<images<model order_ok=true
.F........................................[VERIFY] VC-012: parse_end_exit=0
[VERIFY] VC-012: parse_end_exit=1
[VERIFY] VC-012: parse_end_exit=2
..[VERIFY] VC-012: parse_end_exit=None
.........[VERIFY] VC-013: beat_guard=True, window=90
..........................[VERIFY] VC-013: probe_yes=yes probe_no=no probe_unknown=unknown
.[VERIFY] VC-015: pytest_failed=2 new_tests=17 ac_covered=12 fail_closed_cases=4 ok=false

================================== FAILURES ===================================
________________________ test_baseline_left_end_bound _________________________

    def test_baseline_left_end_bound() -> None:
        """The frozen pre-fix renderer equals the git HEAD blob (sha256) — the
        byte-identical comparisons above are anchored to the real left end."""
        if not HEAD_DISPATCH.is_file():
            pytest.skip("frozen baseline copy not reachable (portable fallback in use)")
        frozen = hashlib.sha256(HEAD_DISPATCH.read_bytes()).hexdigest()
        git_blob = hashlib.sha256(_git("show", f"HEAD:{DISPATCH_RELATIVE}")).hexdigest()
>       assert frozen == git_blob
E       AssertionError: assert '219ed8090210...e9bd66bc8610a' == '06d84b528bfd...53a327efdaf01'
E         
E         - 06d84b528bfdab34ab7e9d95c9719301acdc6d3234092d4694553a327efdaf01
E         + 219ed8090210630f5f2136b0f544900bc955309c60936ac351de9bd66bc8610a

test_autopilot_readcap_injection.py:907: AssertionError
__________________ test_existing_regression_files_untouched ___________________

    def test_existing_regression_files_untouched() -> None:
        """AC-015 / D-012: the two pre-existing regression files (golden left end
        for AC-007/AC-008) are byte-untouched vs git HEAD. Assertion-only (no
        [VERIFY] line): the hashes are recorded in the runner's result JSON."""
        for name in ("test_autopilot_config.py", "test_autopilot_dispatch.py"):
            live = hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest()
            blob = hashlib.sha256(
                _git("show", f"HEAD:packages/multi-workers/{name}")
            ).hexdigest()
>           assert live == blob, (name, live, blob)
E           AssertionError: ('test_autopilot_config.py', '5a728d0dec0a4b474da1fd8589d67eafe284afa90c44168fc53936cb13b1fa11', '79423f9db35dfe6f1f71134e325b37ab7612c368749e50be4395a7ea59a4d0cc')
E           assert '5a728d0dec0a...936cb13b1fa11' == '79423f9db35d...5a7ea59a4d0cc'
E             
E             - 79423f9db35dfe6f1f71134e325b37ab7612c368749e50be4395a7ea59a4d0cc
E             + 5a728d0dec0a4b474da1fd8589d67eafe284afa90c44168fc53936cb13b1fa11

test_autopilot_readcap_injection.py:998: AssertionError
=========================== short test summary info ===========================
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_readcap_injection.py::test_existing_regression_files_untouched
2 failed, 202 passed in 20.27s
```

Note: `[VERIFY] VC-015: pytest_failed=2 ... ok=false` and the `VC-003`/`VC-007`/`VC-008`/
`VC-009`/`VC-011`/`VC-012`/`VC-013`/`VC-020`/`VC-023` lines in this log belong to **other keys**
(`mw-autopilot-readcap`, `mw-autopilot-slot-capacity`) whose test files share the scoped file list
and reuse the same VC numbers. They are NOT this key's evidence; this key's lines are enumerated
per-VC in §4.

### 1.2 TypeScript

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-image-cap.test.ts 2>&1 | tee C:/Users/wenbozhou/AppData/Local/Temp/mw-vision-ts.log
```

Full output:

```

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[worker] start task=t-image-cap type=vision phases=-
[IMAGE-CAP] model=glm-5.3 provider=timi task=t-image-cap declared=images:yes
[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true
[worker] start task=t-image-ok type=vision phases=-
[worker] start task=t-no-images type=coding phases=-
[worker] start task=t-image-nomodel type=vision phases=-
····[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false
[VERIFY] VC-008: failopen_ok=true queue_delta=1
········[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true
·[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1
········································································································[worker] start task=w1 type=coding phases=-
·················[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0
[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0
··················[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0
[worker] start task=t-hang type=coding phases=-
[worker] failed exit=1 elapsed=1m tools=0
[worker] start task=t-stream type=coding phases=-
[worker] done exit=0 elapsed=3m tools=0
[worker] start task=t-phases type=coding phases=2
[worker] failed exit=1 elapsed=1m tools=0 phases=0/2
[worker] start task=t-order type=coding phases=-
[worker] failed exit=1 elapsed=3m tools=0
[worker] start task=w1 type=coding phases=-
······································[VERIFY] VC-004: role_for_vision=vision mirror_ok=true
··········

 Test Files  4 passed (4)
      Tests  200 passed (200)
   Start at  17:49:42
   Duration  4.05s (transform 771ms, setup 0ms, import 1.74s, tests 3.61s, environment 0ms)
```

Post-control re-run of the same 4 files: `Test Files 4 passed (4) / Tests 200 passed (200)`.

Note: the TS log contains `[VERIFY] VC-001/VC-002/VC-003` from `agent-team-loop-checkpoint-wiring`
that belong to other keys (same-named VCs). This key's TS lines are VC-004/006/008/011/016/017.

---

## 2. Step 2 — static checks (no `--write`)

### 2.1 biome (`--error-on-warnings`, no `--write`)

```
cd H:/git/Multi-Workers
npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```
```
Checked 317 files in 214ms. No fixes applied.
```
`rc=0`, no errors, no warnings.

### 2.2 tsgo

```
cd H:/git/Multi-Workers
npx tsgo --noEmit
```
```
packages/coding-agent/test/suite/rag-required.test.ts(177,43): error TS2741: Property 'description' is missing in type '{ cwd: string; cli: string; provider: string; taskType: string; model: string; modelReason: string; registry: undefined; }' but required in type '{ cwd: string; cli: string; provider: string; taskType: string; phase?: string | undefined; images?: "no" | "yes" | undefined; description: string; model: string; modelReason: string; registry: ModelRegistry | undefined; }'.
packages/coding-agent/test/suite/rag-required.test.ts(182,41): error TS2741: Property 'description' is missing in type '{ cwd: string; cli: string; provider: string; taskType: string; model: string; modelReason: string; registry: undefined; phase: string; }' but required in type '{ cwd: string; cli: string; provider: string; taskType: string; phase?: string | undefined; images?: "no" | "yes" | undefined; description: string; model: string; modelReason: string; registry: ModelRegistry | undefined; }'.
packages/coding-agent/test/suite/rag-required.test.ts(187,41): error TS2741: Property 'description' is missing in type '{ cwd: string; cli: string; provider: string; taskType: string; model: string; modelReason: string; registry: undefined; phase: string; }' but required in type '{ cwd: string; cli: string; provider: string; taskType: string; phase?: string | undefined; images?: "no" | "yes" | undefined; description: string; model: string; modelReason: string; registry: ModelRegistry | undefined; }'.
packages/coding-agent/test/suite/rag-required.test.ts(191,43): error TS2741: Property 'description' is missing in type '{ cwd: string; cli: string; provider: string; taskType: string; registry: undefined; phase: string; model: string; modelReason: string; }' but required in type '{ cwd: string; cli: string; provider: string; taskType: string; phase?: string | undefined; images?: "no" | "yes" | undefined; description: string; model: string; modelReason: string; registry: ModelRegistry | undefined; }'.
rc=2
```

Attribution (measured, not inferred):

- `rag-required.test.ts` is byte-identical to HEAD (`git diff --stat HEAD -- .../rag-required.test.ts` is empty).
- HEAD's `planDispatchFrontmatter` input type has no `description`
  (`git show HEAD:.../ui-bridge.ts` lines 1024-1035: `cwd, cli, provider, taskType, phase?, model,
  modelReason, registry`).
- The working tree has `+ description: string;` (git diff of `ui-bridge.ts`), added by this key's
  T-05/T-06 auto-detect work. So the 4 errors are **this key's** (not baseline noise).
- T-09 (`output.md` §note 1) and T-12 (`output.md` lines 618/680) had already reported the same 4
  errors but treated them as "another session's in-flight change" / "HEAD pre-existing". The
  signature diff above shows the change is this key's own T-06 edit.

---

## 3. Step 3 — baseline comparison

Allowed existing reds are documented in `evidence-requirement.md` §已知基线噪声 and pm-state E-04/E-06.

Python scoped failures = exactly 2, both pre-existing baseline noise:

1. `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` — E-04: the frozen fixture
   copy `head_dispatch.py` sha256 `219ed809…` != `git show HEAD:.../dispatch.py` sha256 `06d84b52…`.
   Unrelated to `images:`. (0 references to this key's changes.)
2. `test_autopilot_readcap_injection.py::test_existing_regression_files_untouched` — asserts
   `test_autopilot_config.py` and `test_autopilot_dispatch.py` are byte-identical to `HEAD:`. Both
   differ in the current working tree:
   - `test_autopilot_config.py`: live `5a728d0d…` vs HEAD `79423f9d…` — other session
     (`mw-autopilot-slot-capacity`), recorded as E-06.
   - `test_autopilot_dispatch.py`: live `66cf1f5f…` vs HEAD `cda5be7b…` — **this key's T-03**
     (AC-005/AC-019 re-freeze: added the `vision` bucket + `test_vision_conductor_dispatchable`).
   Because the assertion compares the live file to the `HEAD:` blob, it reddens on **any**
   uncommitted authoring of those two files; it is a working-tree/commit-time artifact, not a code
   regression, and it will clear once the key (and the other session's work) are committed. The
   test fails on the first name (`test_autopilot_config.py`) before reaching the dispatch file.
   Both causes are uncommitted-worktree, so the card's "existing red" allowance applies; flagged
   here for honesty since one of the two files is this key's.

No `agent-team-loop*` / `worker-mode*` / `dispatch-models*` test failed. TS scoped: 0 failures.
Fresh-vs-baseline delta (202 passed vs E-08's 164 passed) is entirely other keys' added tests in the
same shared files.

---

## 4. Step 4 — per-AC/VC `[VERIFY]` ledger

Legend: `PASS` = required line present in the raw output above; `GAP` = required line absent;
`BLOCKED` = process evidence fails.

| VC | AC | observed `[VERIFY]` line (this key) | where | status |
|----|----|--------------------------------------|-------|--------|
| VC-001 | AC-001 | `[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0` | py log | PASS |
| VC-002 | AC-002 | `[VERIFY] VC-002: rc=nonzero roles=5` | py log | PASS |
| VC-003 | AC-003 | **absent** (expected `source=config:vision task_override=task`) | — | **GAP** |
| VC-004 | AC-004 | `[VERIFY] VC-004: role_for_vision=vision mirror_ok=true` | ts log | PASS |
| VC-005 | AC-005 | `[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true` | py log | PASS |
| VC-006 | AC-006 | `[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false` | ts log | PASS |
| VC-007 | AC-007 | **absent** (expected `queue_delta=1 images_line=yes order_ok=true`) | — | **GAP** |
| VC-008 | AC-008 | `[VERIFY] VC-008: failopen_ok=true queue_delta=1` | ts log | PASS |
| VC-009 | AC-009 | `[VERIFY] VC-009: zero_byte=true frozen_copy=true` + `[VERIFY] VC-009-order: line_order=type<phase<images<model order_ok=true` | py log | PASS |
| VC-010 | AC-010 | `[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip` | py log | PASS |
| VC-011 | AC-011 | `[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true` + L2 (§5) | ts log + §5 | PASS |
| VC-012 | AC-012 | see §9 (tsgo red) | §2 | **BLOCKED** |
| VC-013 | AC-013 | `[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0` | py log | PASS |
| VC-014 | AC-014 | `[VERIFY] VC-014: surfaces=4 token_set_ok=true` | py log | PASS |
| VC-015 | AC-015 | `[VERIFY] VC-015: show_images=yes/no/unknown rc=0` | py log | PASS |
| VC-016 | AC-016 | `[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true` | ts log | PASS |
| VC-017 | AC-017 | `[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1` (revised expected string, design §7) | ts log | PASS |
| VC-018 | AC-018 | n/a (obsolete) | — | N/A |
| VC-019 | AC-019 | `[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true` | py log | PASS |

GAP detail:

- VC-003 (AC-003): repo-wide grep of `packages/**/*.py` and `packages/**/*.ts` for
  `source=config` / `config:vision` / `task_type="vision"` returns **zero** hits. The generic
  `TestResolveDispatchModel` cases in `test_dispatch_models.py` cover review/research/coding but
  never `task_type="vision"`. Behavior is reachable through generic tables but has no direct
  assertion and no `[VERIFY]` line.
- VC-007 (AC-007): `agent-team-loop-vision-gate.test.ts` has the correct behavioral test
  (`"input:text,image + images:yes dispatches and writes the ordered head"`, lines 277-303:
  asserts `Dispatched worker 't2'`, `_workers.parallel +1`, `^images: yes$`, and strict
  `type < phase < images < model` order). It passes in the 200, but emits no `[VERIFY]` marker;
  repo-wide grep for `images_line=yes` is zero.

---

## 5. Step 4 (card) — human L2-1: real-process `[IMAGE-CAP]` backstop

### 5.1 Card-exact command (global bundled extension) — did NOT fire

Temp project `T=C:/Users/wenbozhou/AppData/Local/Temp/l2a`, task
`T/.agenticdoc/l2k/workers/l2t/task.md`:

```
type: coding
phase: 1
images: yes

say ok
```

```
cd "$T"
PI_WORKER_TASK="$T/.agenticdoc/l2k/workers/l2t/task.md" \
  bash H:/git/Multi-Workers/pi-test.sh --model timi/deepseek-v4.1-flash -p "say ok"; echo "rc=$?"
```

Raw output:

```
[worker] start task=l2t type=coding phases=-
[worker] done exit=0 elapsed=2s tools=0
ok
rc=0
```

No `[IMAGE-CAP]`; **rc=0**; the task body executed. `trace.log` from that run:

```
[START] pid=97804
[START] 2026-09-26T09:51:20.127Z task=l2t type=coding phases=-
[MODEL] 2026-09-26T09:51:20.291Z model=deepseek-v4.1-flash
[END] 2026-09-26T09:51:21.754Z exit=0 elapsed=2s tools=0 phases=-
```

Diagnosis (measured):

- `timi/deepseek-v4.1-flash` is `input:["text"]` (images=no) in
  `packages/ai/src/providers/data/timi.json`, so a correct run must refuse.
- `parseTaskMd(taskPath)` on the exact file returns `images=true` (diagnostic script
  `diag-parse.ts`, output `type="coding" phase="1" images=true taskKey="l2t"`).
- A debug `-e` extension added to the worker run printed, at the same `session_start`:
  `{"id":"deepseek-v4.1-flash","provider":"timi","input":["text"],"inputIncludesImage":false}`
  and `meta={"images":true,"type":"coding"}` — i.e. every operand of the backstop condition was
  true, yet the builtin handler did not fire.
- The globally installed bundle shadows the source builtin:
  `~/.pi/agent/extensions/agent-team-loop.js` = `packages/multi-workers/dist/extensions/agent-team-loop.js`
  (925286 B, mtime `2026-09-26 15:15:39`, pre-T-09) and contains **0** occurrences of `IMAGE-CAP`
  (grep count 0; `meta.images` count 0). `mw build` (which copies the bundle) had not run since
  T-09. The card's assumption "扩展是 bundled，任意目录都加载" is exactly the failure mode.

### 5.2 Isolated source builtin (`-ne`: extension discovery off) — DID fire

```
cd "$T"
PI_WORKER_TASK="$T/.agenticdoc/l2k/workers/l2t/task.md" \
  bash H:/git/Multi-Workers/pi-test.sh -ne --model timi/deepseek-v4.1-flash -p "say ok"
```

Raw output (stdout is fd 1, which the launcher redirects into `worker.log`):

```
[worker] start task=l2t type=coding phases=-
[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
rc=1
```

Artifacts written in `T/.agenticdoc/l2k/workers/l2t/` (the task dir, same as the card expects):

- `worker.log` (stdout capture):
  ```
  [worker] start task=l2t type=coding phases=-
  [IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
  rc=1
  ```
- `trace.log`:
  ```
  [START] pid=100652
  [START] 2026-09-26T09:55:34.929Z task=l2t type=coding phases=-
  [MODEL] 2026-09-26T09:55:34.951Z model=deepseek-v4.1-flash
  [ERROR] 2026-09-26T09:55:34.951Z [IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
  ```
- `output.md`:
  ```
  ## TL;DR

  Task refused (image capability).

  ## Summary

  Task refused (image capability).

  ## Exit Reason

  [IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
  ```

Process exit code: `rc=1`. Zero model tokens: `process.exit(1)` runs in `session_start` before the
first turn.

Conclusion: the source backstop is correct; the L2-1 procedure must either run with `-ne` or the
bundle must be rebuilt (`mw build`) before the check. As written, production uses the stale bundle
and the backstop would not fire.

---

## 6. Step 5 — human L2-2: real vision round-trip

Input image (Python stdlib `struct`+`zlib`, no third-party deps):

```
path:  C:\Users\wenbozhou\AppData\Local\Temp\mwv14\red-square.png
bytes: 133
w,h,color: 64x64 rgb(255,0,0) pure red square
sha256: d17c994f536ddb73295df2d420f31be54a3f4b860b77f900d1ae372a6a99106b
```

Command (from repo root, `PI_WORKER_TASK` unset so it is a normal session):

```
cd H:/git/Multi-Workers
env -u PI_WORKER_TASK bash pi-test.sh \
  --model timi/deepseek-v4-flash-vision-exp \
  -p "Read the image C:/Users/wenbozhou/AppData/Local/Temp/mwv14/red-square.png with the read tool. Reply exactly two words: the color, then the shape."
```

Raw output:

```
red square
rc=0
```

New session JSONL created by this run (diff of the session dir listing):
`C:/Users/wenbozhou/.pi/agent/sessions/--H--git-Multi-Workers--/2026-09-26T09-56-03-501Z_01a0dd24-ad2d-7fa6-a30f-347509628446.jsonl`

Expectation ① (behavior) — the reply names the correct color and shape: **`red square`** (matches
the deterministic all-red 64x64 PNG). ✅

Expectation ② (mechanism) — the session contains a real image content block, not the degradation
line:

```
"type":"image" occurrences: 1
data:image/png occurrences: 0            (JSONL stores raw base64, no data: prefix)
"does not support images" occurrences: 0
```

Line 7 (truncated at 420 chars; base64 carries the PNG magic `iVBORw0KGgo…` = 89 50 4E 47 0D 0A 1A 0A):

```
{"type":"message","id":"decafc54","parentId":"7d3ac4f7","timestamp":"2026-09-26T09:56:06.226Z","message":{"role":"toolResult","toolCallId":"call_00_ZryBvtfnZb7Zc7pYGSz47183","toolName":"read","content":[{"type":"text","text":"Read image file [image/png]"},{"type":"image","data":"iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAATElEQVR42u3PQQkAAAgAsetfWiP4FgYrsKZeS0BAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBA
```

Line 8 (assistant reply + model attribution):

```
{"type":"message","id":"f3b38d13",...,"message":{"role":"assistant","content":[...,{"type":"text","text":"red square"}],"api":"anthropic-messages","provider":"timi","model":"deepseek-v4-flash-vision-exp","usage":{"input":292,"output":3,...},"stopReason":"stop",...}}
```

Both expectations met; no provider unavailability, no blocker.

---

## 7. Step 7 — non-vacuous controls ("restore the defect ⇒ red")

Method: temporarily mutate the implementing line, run the specific VC test, capture the failure,
then restore the exact original text. All mutations were reverted; restoration is byte-verified in
§7.5. No other agent's work was touched.

### 7.1 VC-006 (gate refusal) — red

Mutation (`pm/ui-bridge.ts`): `if (imagesRequested) {` → `if (imagesRequested && false) {`.

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts -t 'VC-006'
```
```
 FAIL  test/extensions/agent-team-loop-vision-gate.test.ts > dispatch capability gate (mw-vision-role T-06) > VC-006: input:text + images:yes is refused with zero side effects
AssertionError: expected 'Dispatched worker \'t1\' (type: codin…' to contain 'images'

Expected: "images"
Received: "Dispatched worker 't1' (type: coding, role: coding, model: timi/glm-5.3 (no dispatch.yml coding default)) under key 'k'. Task file: C:\Users\WENBOZ~1\AppData\Local\Temp\atl-vision-gate-gMrXPD\k\workers\t1\task.md. Check mw_status to confirm the service is running."

 ❯ test/extensions/agent-team-loop-vision-gate.test.ts:269:19

 Test Files  1 failed (1)
      Tests  1 failed | 7 skipped (8)
```
Without the gate the dispatch is allowed and the refusal message disappears ⇒ the VC-006 test is
non-vacuous.

### 7.2 VC-008 (unknown ⇒ fail-open) — red

Mutation (`pm/ui-bridge.ts`): `if (capability === "no") {` → `if (capability !== "yes") {`
(restores the "treat unknown as no" defect).

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts -t 'VC-008'
```
```
 FAIL  test/extensions/agent-team-loop-vision-gate.test.ts > ... > VC-008: undecidable registry lookups fail open (unknown is not no)
AssertionError: expected 'Task declares images (or references a…' to contain 'Dispatched worker \'t1\''

Expected: "Dispatched worker 't1'"
Received: "Task declares images (or references an image file) but model 'timi/glm-5.3' cannot take image input. Use 'mw model set vision <provider/model>' to configure a vision role, or declare 'images: no' if the task does not need the image."

 ❯ test/extensions/agent-team-loop-vision-gate.test.ts:367:19

 Test Files  1 failed (1)
      Tests  1 failed | 7 skipped (8)
```
An undecidable registry lookup is refused instead of failing open ⇒ the VC-008 test is non-vacuous.

### 7.3 VC-009 (undeclared ⇒ zero bytes) — red

Mutation (`packages/multi-workers/autopilot/dispatch.py`): `if images:` → `if images is not None:`
(the exact pitfall called out by design D-003).

```
cd packages/multi-workers
python -m pytest test_autopilot_readcap_injection.py::test_vc009_images_zero_byte_and_position -q -s
```
```
>       assert live == empty, (live, empty)
E       AssertionError: ("---
E         type: verifier
E         phase: EXECUTE
E         model: deepseek-v4.1-flash
E         ...
E           ---
E           type: verifier
E           phase: EXECUTE
E         - images: 
E           model: deepseek-v4.1-flash
E           origin: conductor...
E         ...

test_autopilot_readcap_injection.py:960: AssertionError
FAILED test_autopilot_readcap_injection.py::test_vc009_images_zero_byte_and_position
1 failed in 0.15s
```
`images=""` leaks an `images: ` line while `images=None` does not ⇒ the frozen-copy/zero-byte
assertion is non-vacuous.

### 7.4 VC-011 (worker backstop) — red

Mutation (`worker/worker-mode.ts`): prepend `false && ` to
`if (meta.images === true && ctx.model && Array.isArray(ctx.model.input) && !ctx.model.input.includes("image"))`.

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-image-cap.test.ts -t 'VC-011'
```
```
 FAIL  test/extensions/agent-team-loop-image-cap.test.ts > worker image-capability backstop (VC-011) > VC-011: `images: yes` + text-only runtime model refuses with [IMAGE-CAP] and exit(1)
AssertionError: expected "Mock" to be called with arguments: [ 1 ]

Number of calls: 0

 ❯ test/extensions/agent-team-loop-image-cap.test.ts:126:20

 Test Files  1 failed (1)
      Tests  1 failed | 3 passed (4)
```
Removing the check drops `process.exit(1)` ⇒ the VC-011 test is non-vacuous.

### 7.5 Restoration verification

Baseline sha256 captured before any mutation, re-checked after all four controls:

```
74136ad9ed6c6eb720e366d4ad2eb3cdbda11a923c6fb90c4c97355b8fc00271 *packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
58da581c67f06b3c19374c52517d574312d6260fd451d607b068cb30403bf70a *packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
6be60fe5ae42646732a1ace23a704e95f9b588339c05fec51e70769643c91469 *packages/multi-workers/autopilot/dispatch.py
```

Post-restore re-run: 4 TS files `200 passed`, VC-009 pytest `1 passed`.

---

## 8. Findings to report to PM (no fix attempted here)

1. **`tsgo` red (VC-012 blocker).** `pm/ui-bridge.ts` requires `description: string` in
   `planDispatchFrontmatter`; `test/suite/rag-required.test.ts` (unmodified, rag key's T-14) has 4
   call sites without it. Suggested (PM decides): make `description` optional and default to `""`
   inside `planDispatchFrontmatter` — `detectImageNeed(cwd, "")` already returns false with no I/O,
   so AC-009 zero-byte/perf is preserved — or add `description: ""` to the 4 rag call sites.
   Already surfaced by T-09/T-12 but left open.
2. **Stale bundled extension (L2-1 blocker / deploy gap).** `packages/multi-workers/dist/extensions/agent-team-loop.js`
   and the global copy predate T-09/T-12/T-15 and lack `IMAGE-CAP`; because discovery shadows the
   source builtin, the key's behavior is unreachable in real windows until `mw build` regenerates
   and reinstalls the bundle. Recommend running `mw build` (and re-running the card-exact L2-1)
   before declaring the key done; alternatively the L2-1 recipe should mandate `-ne` for
   source verification. This also means E-10's `mw model show`/`mw doctor` came from the Python CLI
   (fresh source), not from the stale JS bundle — the TS render path (`ui-bridge.ts` doctor
   `images=`) is verified only by unit tests, not by a real window during this closeout.
3. **VC-003 / VC-007 have no `[VERIFY]` line** (evidence-requirement mismatch). Either add the
   expected markers/assertions (`resolve_dispatch_model(task_type="vision")`;
   gate allow-case marker) or re-issue the evidence-requirement. Behavior is otherwise covered.
4. **Readcap byte-identity test is at odds with the authorized T-03 re-freeze** of
   `test_autopilot_dispatch.py` (§3.2). Commit-time transient, but PM should confirm whether the
   readcap `test_existing_regression_files_untouched` file list needs narrowing.

## 9. VC-012 process evidence

```
[VERIFY] VC-012: scoped_tests=green(baseline_red=2) check=FAILED
```

The locked expected string is `[VERIFY] VC-012: scoped_tests=green check=green`. It is NOT emitted
because `npx tsgo --noEmit` exits `rc=2` with 4 errors (§2.2). Emitting the green string would be a
false pass (P-016). scoped_tests = 202 py passed (+2 documented baseline reds) / 200 ts passed;
biome clean; tsgo **red**.

## 10. Known leftovers not in this key (context, unchanged)

- Windows environment baseline: 89 known failures (`packages/agent` 13 + `packages/coding-agent`
  76), per `AGENTS.md`; not re-run here.
- Readcap `test_baseline_left_end_bound` (E-04) and `test_existing_regression_files_untouched`
  (E-06) are pre-existing/commit-time reds.
- Cross-key VC-number collisions in shared test files (`VC-003/007/008/009/011/012/013/015/020/023`
  emitted by `mw-autopilot-readcap` / `mw-autopilot-slot-capacity`); only the per-key-belonging
  lines are counted as evidence here.

---

## 附录 A — T-17/T-18 修复后复验（2026-09-26，T-19）

> 本附录**只追加**，不改写上文 T-14 原文。上文 §0/§9 的
> `[VERIFY] VC-012: scoped_tests=green(baseline_red=2) check=FAILED` 是当时的正确判定（拒绝放行），
> **已被本附录 §A.7 的复验结论取代**：T-17 修掉 4×TS2741 后 `tsgo rc=0`，T-18 补齐 VC-003/VC-007
> 逐字证据；B2（全局 bundle 陈旧）是部署问题，见 §A.8「遗留」，不作为代码缺陷。
>
> 本附录全部为**当次真实执行**的原始输出（命令 + stdout/stderr），无 worker 自述转述。
> 复验环境：仓库根 `H:/git/Multi-Workers`，HEAD `c3edc20fe`，Python 3.14.3 / node v24.19.0 /
> vitest 4.1.9；PowerShell 5.1 host，日志由 `cmd /c` 重定向落盘后逐字回贴。
>
> **写面声明**：本 key 本次只改本文件（`evidence/runs/verify-mw-vision-role-20260926.md`），
> 未改任何 `packages/**` 源码/测试。

### A.1 `npx tsgo --noEmit`（仓库根）— rc=0、零输出

```bash
cd H:/git/Multi-Workers
npx tsgo --noEmit
```

完整输出（stdout+stderr）：

```
(empty - no diagnostics)
```

```
rc=0
```

对照上文 §2.2：T-14 当时 4×`TS2741 @ test/suite/rag-required.test.ts`、`rc=2`；T-17 把
`planDispatchFrontmatter` 的 `description` 改为可选（`description?:` + `input.description ?? ""`）后本项归零。

### A.2 触达面全量两套（完整输出，不 tail）

#### A.2.1 Python（cwd = `packages/multi-workers`）

```bash
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test_dispatch_models.py test_autopilot_l0.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_serve_doctor.py test_rag_phase.py test_autopilot_readcap_injection.py test_common.py -q -s
```

完整输出（逐字，cp936 无效字节显示为 `U+FFFD`/`��`，无内容行被删改）：

```
....................[launcher] Warning: dispatch.yml unreadable: while parsing a flow sequence
  in "<unicode string>", line 1, column 9:
    models: [broken
            ^
expected ',' or ']', but got '<stream end>'
  in "<unicode string>", line 2, column 1:
    
    ^ �� model defaults fall back to the window model / per-cli defaults
............[mw model set] review = timi/glm-5.3-air �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model set] coding = codex/gpt-5.6-sol �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model clear] removed review �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_set_show_clear_roundtrip0\.mw\dispatch.yml
[mw model clear] removed all roles �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_set_show_clear_roundtrip0\.mw\dispatch.yml
.[mw model set] Error: value must be 'prefix/model' (e.g. timi/glm-5.3), got 'noslash'
[mw model set] Error: unknown prefix 'bogus' (valid: claude, claude_cli, codex, codex_cli, deepseek, timi, zai)
.[mw model set] Error: existing dispatch.yml is unusable (dispatch.yml unreadable: while parsing a flow sequence
  in "<unicode string>", line 1, column 9:
    models: [broken
            ^
expected ',' or ']', but got '<stream end>'
  in "<unicode string>", line 2, column 1:
    
    ^) �� fix or remove it before writing
...[mw model set] vision = timi/deepseek-v4-flash-vision-exp �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_yes_writes_vision_role0\.mw\dispatch.yml
...[mw model set] Error: --force is only valid for the 'vision' role (got 'coding'); it only skips the image-capability probe
.[mw model set] main = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] coding = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] review = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_other_roles_never_probe0\.mw\dispatch.yml
[mw model set] research = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_other_roles_never_probe0\.mw\dispatch.yml
.[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0
[mw model set] vision = timi/deepseek-v4-flash-vision-exp �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_verify_vc0010\.mw\dispatch.yml
.[VERIFY] VC-002: rc=nonzero roles=5
usage: python.exe -m pytest model set [-h] --project PROJECT [--force]
                                      ROLE PROVIDER/MODEL
python.exe -m pytest model set: error: argument ROLE: invalid choice: 'villain' (choose from main, coding, review, research, vision)
.[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0
[mw model set] --force: image-capability probe skipped for timi/glm-5.3
[mw model set] vision = timi/glm-5.3 �� C:\Users\wenbozhou\AppData\Local\Temp\pytest-of-wenbozhou\pytest-7642\test_verify_vc0130\.mw\dispatch.yml
[mw model set] Error: timi/glm-5.3 reports images=no �� a 'vision' role model must accept image input
[mw model set] Suggest: pick a vision-capable model, e.g. `mw model set vision timi/deepseek-v4-flash-vision-exp`, or override with `mw model set vision timi/glm-5.3 --force`
......[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip
.[VERIFY] VC-015: show_images=yes/no/unknown rc=0
.[VERIFY] VC-003: source=config:vision task_override=task
.[VERIFY] VC-007: phase_direct_writes=0 goal_writes=0 advance_via_script=all files_scanned=15
.[VERIFY] VC-007: runtime_advance_events=2 exit_codes=0,1 schema=exit=<n> on all
.[VERIFY] VC-023: registry_parity=per-type-exact types=7 verifier_entry=explicit ts_buckets=['coding', 'fallback', 'research', 'review']
.[VERIFY] VC-023: unknown_rows=0 rejection=type-rejected fallback=none
.[VERIFY] VC-023: worker_fail_closed=1 ts_suite=autopilot-protocol.test.ts ts_run=passed manual_fallback=full-set
.[VERIFY] VC-014: surfaces=4 token_set_ok=true
.[VERIFY] VC-023: registry_types=7 unknown_tools=0
.[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true
.[VERIFY] VC-023: parity_snapshot_types=7
..[VERIFY] VC-023: optional_fields_omitted=true
.[VERIFY] VC-023: rows=1 row_verified=true lock_cleaned=true timeline_dispatch=true
.[VERIFY] VC-023: scratch_sentinel_key=true
..[VERIFY] VC-023: unknown_rows=0 type_rejected_event=true no_fallback=true
.[VERIFY] VC-023: verifier_scope_required=true verifier_with_scope_rows=1
..[VERIFY] VC-013: single_no_yml_snapshot=true
.[VERIFY] VC-013: deny_globs_line=true control_scope=true
[VERIFY] VC-009: game_abs=true engine_abs=true
.[VERIFY] VC-013: scopeless_deny_injected=true no_scope_forced=true
....[VERIFY] VC-013: broken_yml_rows=0 fail_closed=true
.[VERIFY] VC-008: parity_pass=true snapshot_equal=true keys=11
[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true
......[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve.
.[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve.
....................OK: claimed 'key-a' with ClaimId=WENBOZHOU-PC4:32920
.CONFLICT: key 'key-live' is already active (ClaimId: WENBOZHOU-PC4:44504).
Use --force to take over.
CONFLICT: key 'key-legacy' is already active (ClaimId: 20260808-174558-3176).
Use --force to take over.
OK: claimed 'key-dead' with ClaimId=WENBOZHOU-PC4:32920
OK: claimed 'key-live' with ClaimId=WENBOZHOU-PC4:32920
.[VERIFY] VC-020: phase_empty_byte_identical=true golden_match=true
.[VERIFY] VC-020: phase_written=true value=DESIGN
.[VERIFY] VC-020: phase_written=true worker_reads_phase=true audit_consistent=true
.[VERIFY] VC-020: unknown_phase_omitted=true scratch_omitted=true
.[VERIFY] VC-020: audit_consistent=true phase=design required_missing=1
.[VERIFY] VC-001: tasks=3 file_cap_lines=3 byte_cap_lines=3 order_ok=true ok=true
.[VERIFY] VC-002: readFileCap=64 readByteCap=2097152 equals_config=true fallback_used=false ok=true
.[VERIFY] VC-003: rerender_value=20 cap_literal_assignments=0 ok=true
.[VERIFY] AC-004: file_cap=128 byte_cap=4194304 max_calls=57 max_bytes=913636 renders=true ge_2x=true ok=true
.[VERIFY] AC-005: max_calls=57 max_bytes=913636 derived_rejections=0 tight_rejections=53 ok=true
.[VERIFY] AC-006: dispatched_tasks=1 cap_lines=2 cap_equals_config=true restart_half=deferred_T-006 ok=true
.[VERIFY] VC-007: byte_identical=true cap_lines=0 config_created=false ok=true
.[VERIFY] VC-008: byte_identical=true cap_lines=0 dispatch_ok=true ok=true
.[VERIFY] VC-009: cases=3 exceptions=0 dispatch_ok=3 cap_lines=0 config_contract_unchanged=true ok=true
.[VERIFY] VC-010: cap_file_at=3 cap_byte_over=150 rendered=true ok=true
.[VERIFY] VC-011: invalid_cases=5 unlimited_cases=0 fallback_defaults=true still_blocks=true ok=true
.[VERIFY] VC-012: missing_section=below fail_row=below ok=true
.F.[VERIFY] VC-009: zero_byte=true frozen_copy=true
[VERIFY] VC-009-order: line_order=type<phase<images<model order_ok=true
.F........................................[VERIFY] VC-012: parse_end_exit=0
[VERIFY] VC-012: parse_end_exit=1
[VERIFY] VC-012: parse_end_exit=2
..[VERIFY] VC-012: parse_end_exit=None
.........[VERIFY] VC-013: beat_guard=True, window=90
..........................[VERIFY] VC-013: probe_yes=yes probe_no=no probe_unknown=unknown
.[VERIFY] VC-015: pytest_failed=2 new_tests=17 ac_covered=12 fail_closed_cases=4 ok=false

================================== FAILURES ===================================
________________________ test_baseline_left_end_bound _________________________

    def test_baseline_left_end_bound() -> None:
        """The frozen pre-fix renderer equals the git HEAD blob (sha256) — the
        byte-identical comparisons above are anchored to the real left end."""
        if not HEAD_DISPATCH.is_file():
            pytest.skip("frozen baseline copy not reachable (portable fallback in use)")
        frozen = hashlib.sha256(HEAD_DISPATCH.read_bytes()).hexdigest()
        git_blob = hashlib.sha256(_git("show", f"HEAD:{DISPATCH_RELATIVE}")).hexdigest()
>       assert frozen == git_blob
E       AssertionError: assert '219ed8090210...e9bd66bc8610a' == '06d84b528bfd...53a327efdaf01'
E         
E         - 06d84b528bfdab34ab7e9d95c9719301acdc6d3234092d4694553a327efdaf01
E         + 219ed8090210630f5f2136b0f544900bc955309c60936ac351de9bd66bc8610a

test_autopilot_readcap_injection.py:907: AssertionError
__________________ test_existing_regression_files_untouched ___________________

    def test_existing_regression_files_untouched() -> None:
        """AC-015 / D-012: the two pre-existing regression files (golden left end
        for AC-007/AC-008) are byte-untouched vs git HEAD. Assertion-only (no
        [VERIFY] line): the hashes are recorded in the runner's result JSON."""
        for name in ("test_autopilot_config.py", "test_autopilot_dispatch.py"):
            live = hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest()
            blob = hashlib.sha256(
                _git("show", f"HEAD:packages/multi-workers/{name}")
            ).hexdigest()
>           assert live == blob, (name, live, blob)
E           AssertionError: ('test_autopilot_config.py', '5a728d0dec0a4b474da1fd8589d67eafe284afa90c44168fc53936cb13b1fa11', '79423f9db35dfe6f1f71134e325b37ab7612c368749e50be4395a7ea59a4d0cc')
E           assert '5a728d0dec0a...936cb13b1fa11' == '79423f9db35d...5a7ea59a4d0cc'
E             
E             - 79423f9db35dfe6f1f71134e325b37ab7612c368749e50be4395a7ea59a4d0cc
E             + 5a728d0dec0a4b474da1fd8589d67eafe284afa90c44168fc53936cb13b1fa11

test_autopilot_readcap_injection.py:998: AssertionError
=========================== short test summary info ===========================
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_readcap_injection.py::test_existing_regression_files_untouched
2 failed, 203 passed in 17.54s
```

**逐文件红/绿判定**（每文件单独 `-q --tb=no` 复核，同一工作区）：

| 文件 | 结果 | 判定 | 归属 |
|------|------|------|------|
| `test_dispatch_models.py` | `53 passed`，rc=0 | GREEN | 本 key（含 T-18 新增 `TestVisionRoleResolution`） |
| `test_autopilot_l0.py` | `6 passed`，rc=0 | GREEN | 本 key 触达面 |
| `test_autopilot_dispatch.py` | `18 passed`，rc=0 | GREEN（工作区文件被改动） | **T-03 授权重冻的未提交工作区现象**，非本 key 回归 |
| `test_mwpp_collection_parity.py` | `1 passed`，rc=0 | GREEN | 本 key（T-03 语料重冻） |
| `test_serve_doctor.py` | `28 passed`，rc=0 | GREEN | 本 key 触达面 |
| `test_rag_phase.py` | `5 passed`，rc=0 | GREEN | AC-009 既有 golden |
| `test_autopilot_readcap_injection.py` | `2 failed, 15 passed`，rc=1 | RED（2 条） | **既有基线 E-04 / E-06**，与本 key 无关 |
| `test_common.py` | `77 passed`，rc=0 | GREEN | 本 key 触达面 |
| **合计** | **2 failed, 203 passed** | 2 条红均为既有基线 | 本 key 引入红 = **0** |

2 条红逐条归因（与上文 §3 一致）：

1. `test_baseline_left_end_bound` — **E-04**：冻结副本 `219ed809…` ≠ `HEAD:…/dispatch.py`
   `06d84b52…`；与 `images:` 无关，§3 已知基线。
2. `test_existing_regression_files_untouched` — **E-06**：断言 `test_autopilot_config.py` /
   `test_autopilot_dispatch.py` 与 `HEAD:` 逐字节相等；当前工作区两文件都非 HEAD：
   - `test_autopilot_config.py` diff（12+/8-）来自**其他会话** `mw-autopilot-slot-capacity`（T-03
     新增 `auto_gate_mode` 键、键数 13→14；见 `git diff` 注释原文），E-06 既有。
   - `test_autopilot_dispatch.py` diff（47+/1-）来自**本 key T-03 授权重冻**（新增
     `rag-research`/`vision` 类型、`dispatch.tool_set("vision")`、`test_vision_conductor_dispatchable`；
     `git diff` 注释 `mw-vision-role T-03 (AC-005)`）。该断言在第 1 个名字
     (`test_autopilot_config.py`) 即失败，未走到 dispatch 文件；但它比对 live-vs-HEAD，
     **任何** 授权重冻的未提交状态都会使其变红 ⇒ **「非本 key 的未提交工作区现象」**（本 key 的部分是
     T-03 授权行为本身），提交后消失。

> 注意：本 8 文件 pytest stdout 里出现的 `[VERIFY] VC-003/VC-007/VC-008/VC-009/VC-011/VC-012/VC-013/VC-015/VC-020/VC-023`
> 大部分来自**其他 key**（`mw-autopilot-readcap`、`mw-autopilot-slot-capacity`）共享同一测试文件、复用同名 VC 编号；
> 本 key 逐 VC 归属见 §A.3 与 §A.6。

#### A.2.2 TypeScript（cwd = `packages/coding-agent`）

```bash
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-image-cap.test.ts
```

完整输出：

```

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[worker] start task=t-image-cap type=vision phases=-
[IMAGE-CAP] model=glm-5.3 provider=timi task=t-image-cap declared=images:yes
[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true
[worker] start task=t-image-ok type=vision phases=-
[worker] start task=t-no-images type=coding phases=-
[worker] start task=t-image-nomodel type=vision phases=-
····[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false
[VERIFY] VC-008: failopen_ok=true queue_delta=1
[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true
·········[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1
·········[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true
······························································································[worker] start task=w1 type=coding phases=-
··································[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0
[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0
[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0
[worker] start task=t-hang type=coding phases=-
[worker] failed exit=1 elapsed=1m tools=0
[worker] start task=t-stream type=coding phases=-
[worker] done exit=0 elapsed=3m tools=0
[worker] start task=t-phases type=coding phases=2
[worker] failed exit=1 elapsed=1m tools=0 phases=0/2
[worker] start task=t-order type=coding phases=-
[worker] failed exit=1 elapsed=3m tools=0
[worker] start task=w1 type=coding phases=-
·········································[VERIFY] VC-004: role_for_vision=vision mirror_ok=true
··········

 Test Files  4 passed (4)
      Tests  201 passed (201)
   Start at  18:07:40
   Duration  3.73s (transform 796ms, setup 0ms, import 1.77s, tests 3.45s, environment 0ms)
```

**逐文件红/绿判定**（每文件单独 `--run` 复核）：

| 文件 | 结果 | 判定 | 归属 |
|------|------|------|------|
| `test/extensions/agent-team-loop.test.ts` | `Tests 177 passed (177)`，rc=0 | GREEN | 本 key 触达面 |
| `test/extensions/agent-team-loop-vision-gate.test.ts` | `Tests 9 passed (9)`，rc=0 | GREEN | 本 key（含 T-18 新增 VC-007 用例） |
| `test/extensions/agent-team-loop-vision-autoroute.test.ts` | `Tests 11 passed (11)`，rc=0 | GREEN | 本 key |
| `test/extensions/agent-team-loop-image-cap.test.ts` | `Tests 4 passed (4)`，rc=0 | GREEN | 本 key |
| **合计** | **201 passed / 0 failed** | 全绿 | 本 key 引入红 = **0** |

> 本 TS 日志里的 `[VERIFY] VC-001/VC-002/VC-003` 来自 `agent-team-loop-checkpoint-wiring`（其他 key，同名 VC）；
> 本 key 的 TS 行为 VC 为 `VC-004/006/007/008/011/016/017`。

### A.3 VC-003 / VC-007 逐字证据（本 key，T-18 补齐）

```
[VERIFY] VC-003: source=config:vision task_override=task
```

```
[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true
```

- `VC-003` 出现在 §A.2.1 Python stdout（`test_dispatch_models.py::TestVisionRoleResolution`；无 `-s` 之外的重定向，`print(flush=True)`），源文件即 T-18 新增用例。
- `VC-007` 出现在 §A.2.2 TS stdout（`agent-team-loop-vision-gate.test.ts` 新增 `describe`；`process.stdout.write`），源文件即 T-18 新增用例。
- 对照上文 §4 的 GAP 行（两条当时标 `GAP`）：本附录**取代**该判定为 `PASS`。

### A.4 静态检查 biome（无 `--write`）

本 key 四个改动源码文件 + 相关测试文件（含 T-17 目标 `rag-required.test.ts`）：

```bash
cd H:/git/Multi-Workers
npx biome check --error-on-warnings \
  packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts \
  packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts \
  packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts \
  packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts \
  packages/coding-agent/test/extensions/agent-team-loop.test.ts \
  packages/coding-agent/test/extensions/agent-team-loop-vision-gate.test.ts \
  packages/coding-agent/test/extensions/agent-team-loop-vision-autoroute.test.ts \
  packages/coding-agent/test/extensions/agent-team-loop-image-cap.test.ts \
  packages/coding-agent/test/suite/rag-required.test.ts
```

```
Checked 9 files in 82ms. No fixes applied.
rc=0
```

宽面复核（同 §2.1 口径，用于确认跨会话噪声）：

```bash
npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

```
Checked 317 files in 177ms. No fixes applied.
rc=0
```

结论：本次两轮 `rc=0`，**无** `autopilot/*.ts` 等跨会话文件报错，因此无「范围外跨会话噪声」需要标注；本 key 复验范围内 biome 干净。

### A.5 真实仓库端到端复跑（幂等、无副作用）

```bash
cd H:/git/Multi-Workers/packages/multi-workers
python mw.py model show --project H:/git/Multi-Workers
```

```
config: H:\git\Multi-Workers\.mw\dispatch.yml
window model: timi/deepseek-v4-flash-vision-exp
main: timi/deepseek-v4.1-flash images=no
coding: timi/deepseek-v4.1-flash images=no
review: timi/glm-5.3 images=no
research: timi/deepseek-v4.1-flash images=no
vision: (unset) �� timi/deepseek-v4-flash-vision-exp [window] images=yes
rc=0
```

5 条角色行（main/coding/review/research/vision）**均含 `images=`**（AC-015 可见面）。

```bash
python mw.py doctor --project H:/git/Multi-Workers --json
```

关键字段（完整 JSON 见本次运行 stdout；此处不删改语义，仅摘该 key 相关段）：

```json
"dispatch": {
  "exists": true,
  "models": {
    "coding": "timi/deepseek-v4.1-flash",
    "main": "timi/deepseek-v4.1-flash",
    "research": "timi/deepseek-v4.1-flash",
    "review": "timi/glm-5.3"
  },
  "window_model": "timi/deepseek-v4-flash-vision-exp",
  "images": {
    "coding": "no",
    "main": "no",
    "research": "no",
    "review": "no"
  }
}
...
"summary": {
  "healthy": true,
  "issues": [],
  "suggestions": [
    "extension bundle older than source - run '/mw build' or 'mw.py build --install'",
    "routes without credentials (env of the mw process): claude (env ANTHROPIC_API_KEY unset); claude-cli (env ANTHROPIC_AUTH_TOKEN unset); deepseek (env DEEPSEEK_API_KEY unset)"
  ]
}
```

```
rc=0
```

`images=no` 相关 suggestion 过滤（AC-010 / T-15 的原始判定式）：

```bash
python mw.py doctor --project H:/git/Multi-Workers --json | python -c "import sys,json;d=json.load(sys.stdin);print([s for s in d['summary']['suggestions'] if 'images=no' in s])"
```

```
[]
rc=0
```

对照 T-15 验收：`dispatch.images` 字段保留、`images=no` suggestion 列表为空、`healthy=true`、退出码 0；`vision` 未配置故无 vision 相关告警（符合 T-15 收窄语义）。

### A.6 18 条活跃 AC 汇总（AC-018 OBSOLETE 不计入）

| AC | 证据位置（本文件） | 判定 |
|----|--------------------|------|
| AC-001 | §A.2.1 逐字 `[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0` | PASS |
| AC-002 | §A.2.1 `[VERIFY] VC-002: rc=nonzero roles=5` + stderr 枚举 `main, coding, review, research, vision` | PASS |
| AC-003 | §A.3 `[VERIFY] VC-003: source=config:vision task_override=task`（T-18 新增） | PASS |
| AC-004 | §A.2.2 `[VERIFY] VC-004: role_for_vision=vision mirror_ok=true` | PASS |
| AC-005 | §A.2.1 `[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true` | PASS |
| AC-006 | §A.2.2 `[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false` | PASS |
| AC-007 | §A.3 `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`（T-18 新增） | PASS |
| AC-008 | §A.2.2 `[VERIFY] VC-008: failopen_ok=true queue_delta=1` | PASS |
| AC-009 | §A.2.1 `[VERIFY] VC-009: zero_byte=true frozen_copy=true` + `[VERIFY] VC-009-order: line_order=type<phase<images<model order_ok=true` | PASS |
| AC-010 | §A.2.1 `[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip` + §A.5 `images=no` suggestion `[]` rc=0 | PASS |
| AC-011 | §A.2.2 `[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true` + 上文 §5.2 真进程 `[IMAGE-CAP]` rc=1 | PASS |
| AC-012 | §A.1 `tsgo rc=0` 零输出 + §A.2 两套 scoped tests（py 2 红均基线、ts 0 红）+ §A.4 biome clean + §A.7 新判定行 | PASS |
| AC-013 | §A.2.1 `[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0` | PASS |
| AC-014 | §A.2.1 `[VERIFY] VC-014: surfaces=4 token_set_ok=true` | PASS |
| AC-015 | §A.2.1 `[VERIFY] VC-015: show_images=yes/no/unknown rc=0` + §A.5 `mw model show` 5 行均含 `images=` | PASS |
| AC-016 | §A.2.2 `[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true` | PASS |
| AC-017 | §A.2.2 `[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1` | PASS |
| AC-018 | OBSOLETE，不计入 | N/A |
| AC-019 | §A.2.1 `[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true` | PASS |

### A.7 复验判定（取代 T-14 §9）

```
[VERIFY] VC-012: scoped_tests=green check=green   （取代 T-14 的 check=FAILED；T-17 修复 tsgo）
```

依据：`scoped_tests` = Python 203 passed / 2 failed（2 failed 均为既有基线 E-04/E-06，本 key 引入红 = 0）
+ TS 201 passed / 0 failed；`check` = `npx tsgo --noEmit` rc=0 零输出（§A.1）+ biome `--error-on-warnings` rc=0（§A.4）。
上文 T-14 §9 的 `check=FAILED` 保留为历史记录，**自本附录起被取代**。

### A.8 遗留（非本 key 代码缺陷，需 PM/用户后续处置）

1. **B2 部署陈旧（待用户决定 `/mw build` + `/mw restart`）**：全局 bundle `~/.pi/agent/extensions/agent-team-loop.js`
   早于 T-09（`IMAGE-CAP` grep=0、遮蔽源 builtin）。本次 `mw doctor --json` 亦实测到该状态：
   `bundle.stale=true`，`global_bundle_mtime=2026-09-26T15:15:39`，`source_newest_mtime=2026-09-26T18:05:30`，
   `summary.suggestions[0]=` `extension bundle older than source - run '/mw build' or 'mw.py build --install'`。
   源 builtin 真进程 L2-1 已通过（T-14 §5.2，`[IMAGE-CAP]` + rc=1），证据在上文；未重启前运行中窗口仍用旧代码。
2. **本仓库 `.mw/dispatch.yml` 尚未配置 `vision` 角色**：§A.5 `mw model show` 显示
   `vision: (unset) �� timi/deepseek-v4-flash-vision-exp [window]`；真实视觉派发需用户先执行
   `mw model set vision timi/deepseek-v4-flash-vision-exp`（模型可用性已由 T-14 §6 的 `--model` 直跑验证）。
3. **既有基线红 E-04/E-06**：与 `images:` / 本 key 无关，未修（E-04 = readcap 冻结副本 sha256；
   E-06 = `test_autopilot_config.py` 其他会话未提交 + `test_autopilot_dispatch.py` 本 key 的 T-03 授权重冻，
   提交后消失）。

