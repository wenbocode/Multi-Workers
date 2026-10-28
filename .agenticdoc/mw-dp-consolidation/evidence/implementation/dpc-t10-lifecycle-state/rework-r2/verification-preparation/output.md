# T10 R2 stage C: independent re-verification preparation (no execution)

## 结论

Stage C is *prepared*, not performed. This worker produced a new guarded PM
runner, a new child-side guard / in-child preflight / import probe, an
independent boundary suite for the remaining AC-050 / AC-052 contracts and a
pure AST/text verifier, and bound all of them to the current bytes. It did **not**
import a product, run pytest, collect a node id, execute the runner, or write
any OS object outside its own evidence face. No green run, PASS, QG verdict,
T10 handoff, S2 pass, signoff or `recovery-complete` is claimed, and the original
stage-A/B records (including the stage-B `needs-clarification` / `exit 2` and the
unrecorded shell-command machine-event gap) are left byte-identical.

Key results:

- **Read to EOF (this worker, current bytes):** `decision_wire.py` 82286 B /
  2314 LF, `decision_lifecycle.py` 65501 B / 1647 LF, `decision_task_state.py`
  3871 B / 82 LF, `test_decision_context_lifecycle.py` 65105 B / 1815 LF,
  `test_decision_task_state.py` 15480 B / 278 LF, and all four audited
  `pm-controlled` scripts (754/245/142/90 LF). The associated single-source
  surface of `decision_points.py` / `decision.py` / `mw_common.py` was read only
  in the declared ranges - those three are **not** full reads and are recorded as
  such (`checks/read-audit.json`).
- **Erratum (not a history rewrite):** the stage-B report's "2265 / 1549 / 83"
  and "1816 / 279" line counts describe the *pre-repair* bytes with a
  `split("\n")` convention (newlines 2264 / 1548 / 82; tests 1815 / 278). The
  current files are 2314 / 1647 / 82 LF (tests 1815 / 278). The two products
  grew by exactly the repair; `decision_task_state.py` did not change at all.
- **Bindings verified, not assumed:** the runner's product/test/helper/extra-suite
  digests were re-derived from the bytes on disk by a pure AST/text checker
  (67 checks, `ok=true`, rc 0), together with the protected counts the runner
  asserts: 1891 mirror files, 14 `.pyc`, 744 old-evidence files.
- **Guard strengthened:** the sentinel row now carries the child label and the
  parent pid, so the audit proves the guard was installed in *every* guarded
  Python child (including the preflight's grandchild) instead of extrapolating
  from one process; the guard/probe/preflight additionally prove the fail-closed
  branches (missing sentinel configuration and an uncreatable sentinel path must
  terminate each interpreter with `86` and no output) before any product stage
  is entered.
- **Boundary suite:** 12 test functions -> 16 items on Windows (15 on POSIX,
  where the case-variant item is skipped). Predicted attribution: **15 expected
  green, 1 predicted red** - `test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation`.
  Nothing was executed; the prediction is a code reading with its root cause
  stated, and the PM's run decides it.

## 证据

### A. Read-to-EOF audit of the current bytes (canonical paths)

| 文件 | bytes | newlines | logical lines | sha256 | read range |
| --- | --- | --- | --- | --- | --- |
| `implementation-worktree/packages/multi-workers/decision_wire.py` | 82286 | 2314 | 2314 | `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc` | 1..EOF (2314) |
| `implementation-worktree/packages/multi-workers/decision_lifecycle.py` | 65501 | 1647 | 1647 | `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5` | 1..EOF (1647) |
| `implementation-worktree/packages/multi-workers/decision_task_state.py` | 3871 | 82 | 82 | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` | 1..EOF (82) |
| `implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py` | 65105 | 1815 | 1815 | `1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9` | 1..EOF (1815) |
| `implementation-worktree/packages/multi-workers/test_decision_task_state.py` | 15480 | 278 | 278 | `30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f` | 1..EOF (278) |
| `rework-r2/pm-controlled/run_pm_tests.py` | 33108 | 754 | 754 | `5b019aec41bdf7017b56698d339402827f0890556e50a0b9d7116794fd203cbc` | 1..EOF |
| `rework-r2/pm-controlled/sitecustomize.py` | 8302 | 245 | 245 | `d2a15fad32af1b755f0164a16d3cfb3543ef8fd5169f13eacbc8971e0809ea5a` | 1..EOF |
| `rework-r2/pm-controlled/guard_preflight.py` | 5389 | 142 | 142 | `085cae83c3477820305af0f504bf62ffdbc4930d5ce4d9c3f1e807382d6e7cb0` | 1..EOF |
| `rework-r2/pm-controlled/probe_imports.py` | 2922 | 90 | 90 | `cac791a30affbd04746df9e0e4a18c20492020ac5f656aad30042cd710c26ee6` | 1..EOF |
| `implementation-worktree/packages/multi-workers/decision_points.py` | 305745 | 7102 (CRLF) | 7102 | `78e72e03cfe3b03f0349d95113c1947713b91c4a143bbaaada404f08db7443e6` | **surface only**: 1340-1400, 2085-2115, 3230-3310, 3820-4340 |
| `implementation-worktree/packages/multi-workers/decision.py` | 119248 | 2740 | 2740 | `ef9c2c68eee18bb93ad716c76c7b146279ac5f111c9f626c68a01d1c35ed691e` | **surface only**: 140-210 |
| `implementation-worktree/packages/multi-workers/mw_common.py` | 269301 | 6248 | 6248 | `80af680d21efed0dbb51182c3b693a81efe2368fc0fc1114465fdb259ff7daf0` | **surface only**: `acquire_lock` / `release_lock` |

Surface-read scope: `decision_points.py` (`require_active_dp`, `ENTRY_CHOICES`,
`REQUIRED_STATE_FIELDS`, `resolve_entry_choices`, `pm_candidate_issues`,
`entry_candidates_issues`, `entry_material_issues`, `entry_choice_issues`,
`basis_catalog_issues`, `basis_selection_issues`, `preparation_issues`,
`prepared_request_issues`), `decision.py` (`REASON_CODES`,
`REASON_INPUT_INCOMPLETE`, `_PREPARED_REASONS`, `_PREPARED_RESULT_FIELDS`),
`mw_common.py` (`acquire_lock`, `release_lock`). The unrelated legacy
registry/renderer/executor tail of `decision_points.py` was not read end-to-end;
that is a stated read-scope limit, not a claim about it. `decision_points.py` is
the only CRLF file in this set (7102 CRLF); every other file listed above is
LF-only with a final newline.

`decision_task_state.py` is the only product whose bytes equal its pre-repair
copy; the two repaired products equal `product-repair/after-bytes/` byte for
byte (verified twice: here and by the stage-B absorption check).

### B. Static verification actually executed (the only command this worker ran)

```text
python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/static_verify.py
rc=0, 67 checks ok, problems=[], counts {mirror 1891, pyc 14, old_evidence 744, own files 6}
```

Logs: `checks/static_verify.stdout`, `checks/static_verify.stderr` (empty),
`checks/static_verify.rc`, machine result `checks/static_verify.result.json`,
read audit `checks/read-audit.json`. The checker only reads bytes, `ast.parse`s
them and compares text/index positions; it writes nothing except its own two
`checks/*.json` files inside this stage's face.

Notable checks it enforced (all `ok`):

- runner ↔ disk binding for `PRODUCTS`, `ASSIGNED_TEST_SHA256`, `LIVE_SHA256`,
  `HELPER_SCRIPTS`, `EXTRA_SUITE_SHA256`, and
  `EXTRA_EXPECTED_FUNCTIONS == ast`-derived test functions of the boundary suite;
- `FOCUS_NODE_IDS` ⊆ declared test functions of the assigned lifecycle suite;
- item bindings: historical floor 116, bound assigned items 130, extra-suite
  floor 15; protected counts 1891 / 14 / 744;
- the runner imports no product module; the boundary suite imports exactly
  `{__future__, json, os, pathlib, sys, threading, pytest, decision_lifecycle,
  decision_points, decision_task_state, decision_wire}`;
- product surface delta vs `product-repair/before-bytes/`: added exactly
  `{_same_path_component, recorded_task_state}` (wire) and
  `{_recorded_after_floor, _canonical_json, _dynamic_entry_answer_issues,
  _refuse_entry_issues}` (lifecycle), removed nothing, classes unchanged;
- `decision_wire`: `recorded_task_state` exists and is used by `build_event`;
  `if guard is not None:` is inside the append lock and precedes
  `if dedupe_event_id:`; `_CASE_INSENSITIVE_PATHS = os.name == "nt"`;
- `decision_lifecycle`: `STAGES`, `OUTCOMES`, `TASK_TERMINALS`,
  `EXECUTED_ACTIONS` (10) and `REQUEST_RESULT_FIELDS` (12) unchanged; the
  request row is built before the content-addressed id is derived from it;
  `_recorded_after_floor` runs as a precheck **before** `_append`, which is the
  recorded root cause of the predicted-red replay item;
- `decision_task_state`: `FIELDS` / `STATUSES` / `SOURCES` unchanged;
- stage-A audit cross-check (both assigned suites), stage-B absorption
  cross-check (five digests), red-disposition `products-before.json` cross-check,
  both PM red-run `report.json` files present and hashed.

### C. Guard, environment and fail-closed design (as delivered, unexecuted)

- Child environment is a whitelist only (`HOME`, `USERPROFILE`, `TEMP`, `TMP`,
  `PYTHONPYCACHEPREFIX`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`,
  `PYTHONIOENCODING=utf-8`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
  `PYTHONPATH=<this stage>`, `DPC10_GUARD_FILE`, `DPC10_GUARD_RUN`) plus the OS
  passthrough (`SYSTEMROOT`, `WINDIR`, `PATH`, `PATHEXT`, `COMSPEC`); the runner
  refuses if any credential-shaped name is present in that mapping.
- `sitecustomize.py` fails closed (exit 86) when it cannot write its sentinel and
  patches `socket.socket.connect/connect_ex/bind/sendto/sendmsg`,
  `socket.create_connection`, `getaddrinfo`/`gethostbyname*`, plus every
  `os.exec*`/`spawn*`/`system`/`popen`/`startfile`; `subprocess.Popen` is refused
  unless the target is this interpreter, `-B` is present, no `-S`/`-I`/`-E` is
  used, `shell` is false and the full guard environment is inherited unchanged.
- `guard_preflight.py` (a guarded child) proves refusals for DNS, TCP, UDP,
  **HTTP** (`http.client`), a non-Python child, `-B`-less, `-S`, `-I`, `-E`,
  a popped `PYTHONPATH` and `shell=True`, proves a Python grandchild is allowed
  and inherits the guard, proves file IO still works and that no
  credential-shaped name is visible.
- Parent-side fail-closed controls (real children, run by the PM only):
  `guard-negative-no-sentinel` (missing `DPC10_GUARD_FILE` -> rc 86, empty
  stdout), `guard-negative-unwritable-sentinel` (sentinel parent directory never
  created -> rc 86, empty stdout, path and parent still absent),
  `guard-negative-control` (valid sentinel -> rc 0 and the marker printed).
- Sentinel audit is per child label **and** per pid: every launched guarded child
  must show both `import` and `guard-installed`, the preflight's grandchild pid
  must be among them, no pid may carry two labels, every row must carry this run
  label and `dont_write_bytecode=true`, and every `guard-installed` row must
  report `credential_env_names == []`.

### D. Exact PM argv (to be run by the PM, not by this worker)

```text
cwd = .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers
python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/run_pm_tests.py \
  --fixture-root C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification \
  --label <new-label> --focus --extra
```

The runner then executes, each in its own guarded child with its own raw
`stdout`/`stderr`/`rc`/`argv`/`cwd` (`runs/<label>/`), with
`cwd=<isolated packages dir>` and distinct `--basetemp`:

```text
# assigned two suites (the original acceptance command, unchanged wording)
python -B -m pytest -p no:cacheprovider -q --basetemp <label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py
# focused stage-A node ids
python -B -m pytest -p no:cacheprovider -q --basetemp=<label>/pytest-basetemp-focus test_decision_context_lifecycle.py::<11 node ids>
# extra boundary suite, fresh basetemp
python -B -m pytest -p no:cacheprovider -q --basetemp <label>/pytest-basetemp-extra <evidence>/test_t10_r2_boundaries.py
```

plus `--collect-only` for both stages (assigned -> `collection.node-ids.txt`,
extra -> `collection-extra.node-ids.txt`), the import probe
(`python -B <evidence>/probe_imports.py <isolated packages dir>`) and the guard
preflight (`python -B <evidence>/guard_preflight.py`).

Exit-code contract: `0` all runs passed, `1` a test run really failed (the pytest
code is propagated, never rewritten), `2` harness/precondition/protection
failure, `3` refused. Because one boundary item is *expected* red on the current
products, a fully correct `--extra` run exits `1` with `problems=[]` and
`extra.predicted_red.observed_failing=["test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation"]`;
that is a stated expectation, not a harness failure and not a green claim.

### E. Expected items and attribution (not observed)

- Assigned two suites: 130 items (105 + 25 from the stage-A audit of these exact
  digests; the runner asserts the declared test functions are all still
  collected, the historical floor 116 and the bound 130). The audited id list
  for the same bytes is
  `rework-r2/pm-controlled/runs/t10-r2-red-20261028T065500Z/collection.node-ids.txt`
  (130 lines); the PM run writes its own copy.
- Extra boundary suite: 16 items on Windows / 15 on POSIX, in this order:
  1. `test_two_writers_recording_the_same_request_add_exactly_one_fact` - predicted green
  2. `test_a_second_real_fact_stays_visible_and_grants_no_action[refusal]` - predicted green
  3. `test_a_second_real_fact_stays_visible_and_grants_no_action[split]` - predicted green
  4. `test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation` - **predicted red (AC-052 replay)**
  5. `test_a_recorded_fact_replays_as_a_duplicate_before_any_later_observation` - predicted green (control)
  6. `test_a_new_older_observation_is_still_refused` - predicted green (control: S5 not weakened)
  7. `test_a_newer_recorded_observation_blocks_an_older_append_from_a_second_writer` - predicted green
  8. `test_two_writers_racing_the_append_lock_never_order_an_older_observation_last` - predicted green
  9. `test_a_known_secret_before_can_be_restated_and_is_never_stored_raw` - predicted green
  10. `test_a_before_that_is_not_the_recorded_observation_is_refused[substantively-different]` - predicted green
  11. `test_a_before_that_is_not_the_recorded_observation_is_refused[reordered]` - predicted green
  12. `test_a_before_that_is_not_the_recorded_observation_is_refused[observed-list-changed-to-unrecorded]` - predicted green
  13. `test_a_before_that_is_not_the_recorded_observation_is_refused[unrecorded-changed-to-observed-empty]` - predicted green
  14. `test_an_exact_before_restatement_is_accepted_with_null_and_empty_kept_apart` - predicted green
  15. `test_the_production_path_refusal_is_the_test_scopes_rule` - predicted green (skipped on POSIX)
  16. `test_the_boundary_suite_runs_isolated_from_the_live_repository` - predicted green

### F. Runner vs the audited `pm-controlled` runner (25 differences that matter)

1. Path anchors are resolved and *verified* (`_resolve_harness`) instead of blind
   `parents[N]` offsets: it asserts the directory names, the isolated/live
   distinctness and the rework/own-face layout, and refuses (rc 3) otherwise.
2. Binds three products **and both** assigned suites (the old runner pinned only
   the lifecycle test explicitly and leaned on the stage-A audit for the other).
3. Binds its own four scripts and the extra suite by digest, so a run cannot use
   a different guard, probe or boundary suite than the audited one.
4. Refuses to run without `sys.dont_write_bytecode` and outside the approved
   fixture root (kept from the controlled revision).
5. Parent-side assertion that no credential-shaped name is in the child env.
6. Adds the three parent-side fail-closed guard controls with raw logs.
7. Extends the in-child preflight with HTTP, `-I`, `-E` and `shell=True`
   refusals (the old one covered DNS/TCP/UDP, non-Python child, missing `-B`,
   `-S` and a popped `PYTHONPATH`).
8. Sentinel rows gained `child` + `ppid`; the guard requires the child label in
   the inherited environment tuple.
9. Sentinel audit is per label *and* per pid for every launched child, not only
   the preflight child; a pid with two labels is a failure.
10. Every sentinel row must show `dont_write_bytecode=true`; every
    `guard-installed` row must show an empty credential-name list.
11. Import probe reports `inside_packages_dir` and the module parent; the runner
    additionally requires the isolated dir to be `sys.path[0]` and the live dir
    to be absent from `sys.path`.
12. Collection now also asserts the bound 130 items (floor 116 kept as history)
    and the focused ids, and separately collects the extra suite.
13. The extra suite gets its own `--collect-only` and its own `--basetemp`; no
    two runs share a basetemp (the old focus run shared nothing either, but the
    extra stage is new).
14. `--extra` is a separate flag; `--focus` is kept as its own run.
15. Protection set extended: predecessor face (`pm-controlled` + its two red
    runs, `product-repair`, `test-preparation`) and this stage's own delivered
    face are snapshotted and diffed, in addition to the mirror/pyc/744/live set.
16. The `.pyc` comparison is by content (added/removed/changed), not only by
    count.
17. Assigned test digests are protected before *and* after the run.
18. A missing stage-A audit result is a precondition failure (the old code
    silently skipped the test cross-check when the file was absent).
19. Stage-ordered early stop: preconditions -> guard negative controls ->
    preflight -> import probe -> collection -> assigned run -> focus ->
    extra collection -> extra run. A guard/import/collect failure never reaches
    the next product stage.
20. `report.json` records both pytest codes, the focus code and the extra code
    separately, plus the pre-repair red set as an *observation*
    (`still_failing`), never as an asserted green.
21. No `rc` rewriting: the assigned pytest code wins, then focus, then extra; a
    harness problem always returns 2 and a real failure is never turned into 0.
22. Raw stdout/stderr are written before any parsing for every child, including
    the three negative controls (the old runner did the same for its five).
23. `meta.json` records the runner's own digest and the full binding table.
24. The whole predecessor face and the own face are diffed after the run, so an
    artifact mutated by a child is a reported harness failure.
25. The docstring and the network claim are updated: the claim is "the guard was
    installed in every guarded child and refused egress in the self-control",
    never "no socket was ever opened".

## 改动清单

| 文件 | 变更 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/run_pm_tests.py` | new stage-C PM runner (55026 B, 1352 LF, sha256 `2e6db8d2a0382f47f2b9aa4b9eb5d40556ed3a1848ba81e46a16cb0fe949adc9`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/sitecustomize.py` | new child-side guard: sentinel with child label/ppid, network + subprocess refusal, fail-closed exit 86 (8902 B, 262 LF, sha256 `34a7fb04db4506250211f63870e4c54b7cb769547ac11bfe99cf306a4f90e94d`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/guard_preflight.py` | new in-child self-control incl. HTTP, `-I`, `-E`, `shell=True` (6255 B, 173 LF, sha256 `6515a78ea8bef8e76ecef815c7087f91231dd7a100e892a86638d73b79ec9bb2`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/probe_imports.py` | new import-provenance probe with `inside_packages_dir` (3483 B, 104 LF, sha256 `f2ff1a7bf5f5b7f48f124cd1812d79c5101acc002b64c2c9656dd655179665cb`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/test_t10_r2_boundaries.py` | new independent boundary suite, 12 functions / 16 items (33533 B, 856 LF, sha256 `5abd812bf5f496ae37b91888f7cb9dc90f31b0290eefd2a1f454bf30bd90f771`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/static_verify.py` | new pure AST/text verifier (25622 B, 649 LF, sha256 `2241916b1f35fbc24557f780d8bc6425d0cdb218598cc0e1a1a3b82c64f978e1`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/static_verify.result.json` | machine result of the verifier (`ok=true`, 67 checks; 19704 B, sha256 `e2768ebd7cf9f82255a017901dd4f3308d02af814ebc14c35eb9dc3a54af84b2`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/read-audit.json` | per-file bytes/LF/lines/sha256/read-range record (9241 B, sha256 `1d39e24b43c6a20d032391a947befc14de998ff7d8901887a3bf4a6ae9c93dc0`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/static_verify.stdout` | verifier stdout, verbatim (385 B, sha256 `1b8156eec7b1df96a53795bbd7666d51d88cd30882f9a7e8b7b20e16103c8a64`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/static_verify.stderr` | verifier stderr, 0 bytes (sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/static_verify.rc` | verifier exit code `0` (2 B, sha256 `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/checks/delivery.json` | digest/bytes/lines manifest for every delivered file (excludes itself) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/report.md` | this report, five sections (bytes/LF and post-edit sha256 in `checks/delivery.json`) |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/output.md` | byte-identical delivery copy of this report (same digest as `report.md`, see `checks/delivery.json`) |

Nothing else was written: the three products, both assigned suites, the
stage-A/B evidence, the `pm-controlled` scripts and their two red runs, the
`product-repair` delivery, the isolated mirror, the 14 `.pyc` files, the five
live files, the worker card/state/DAG/ledger/config and the whole OS face stay
untouched (the static verifier re-hashed them and the runner re-checks them
before and after its own run).

## 残留与未验证

- **No execution at all.** No pytest, no `--collect-only`, no product/test
  import, no runner execution, no decision CLI, no service, no generator, no
  network, no dependency install. The only command executed was
  `python -B .../static_verify.py` (pure AST/text) plus read-only digest/count
  probes; every behavioural statement above is a *reading*, not an observation.
- **The boundary suite's 15/1 split is a prediction.** Item 4 states the AC-052
  per-`event_id` idempotency contract and is expected to fail on the current
  products because `record_lifecycle` runs `_recorded_after_floor` before
  `_append` and `append_event` runs `guard()` before the `dedupe_event_id` scan,
  so an already-recorded fact is refused as an input error instead of returning
  `duplicate`. This was **not reproduced**; the precise expectation, the root
  cause and the fix direction (honour an already-present `event_id` before the
  floor refuses, inside the lock) are in the test docstring. No product change
  was made and no assertion was weakened to hide it.
- **No new semantics introduced.** No global `decision_id` uniqueness, no
  single-terminal rule, no builder privatization, no `decision.py` or live-file
  change. The replay item only restates the existing per-`event_id` idempotency
  contract; the two S5 controls pin that the non-decreasing floor must stay
  strict for *new* event ids.
- **The controlled interleave is scheduling, not a fake lock.** The two
  concurrency items wrap `decision_wire.append_event` only to *order* the threads
  (a `threading.Barrier` for the real lock race, an event handshake for the
  deterministic refusal). The production guard, lock, dedupe scan and append all
  run; no lock is stubbed, no writer is copied and no `sleep` is used to win a
  race. If the real product ever spawned a thread-unsafe cache this would show
  up as a failure, not as a pass.
- **Secret equivalence class (observed, not pinned).** `_check_before` compares
  the *recorded* (redacted) representation, so two different raw snapshots that
  redact to the same recorded text are indistinguishable and would both be
  accepted as the creation fact's `before`. No secret reaches the ledger in that
  case and no later state is backfilled, but the equivalence-class property is
  recorded here rather than turned into a test assertion, because deciding it is
  a contract question this stage may not settle.
- **8.3 short names remain unverified** (only case-variant `.agenticdoc`
  components are covered and pinned; no live-path or 8.3 probe was added).
- **S2 / S6 / S8 and the 8.3 item stay unknown**; nothing here closes them.
- **PM obligations that remain.** The PM must (a) finish its own full-EOF read of
  the five files, (b) run the delivered runner on a *new* label with `--focus
  --extra` in the approved fixture root, (c) keep the raw logs, (d) treat the
  expected-red item and the pre-repair red set as observations, and (e) decide
  whether the replay contract gap goes to the next writer. A `1` exit code from
  the `--extra` run with `problems=[]` is the predicted outcome, not a pass.
- **`npm run check` stays with T32 PM-direct** and was not run here.
- **Item-count caveat.** 130 is asserted as a *bound* for the pinned digests and
  116 remains the historical floor; the extra suite's floor is 15. Neither is a
  claim that the totals can never grow.

## 上下文来源

- `.agenticdoc/mw-dp-consolidation/workers/dpc-t10-r2-verification-preparation/task.md`
  (dispatch card, read to EOF)
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md`
  (original AC-004/012/014/049/050/051/052 and VC contract, read to EOF)
- `.agenticdoc/goal.md:5` (project goal)
- Current isolated products (read to EOF): `decision_wire.py`,
  `decision_lifecycle.py`, `decision_task_state.py`; current assigned suites
  (read to EOF): `test_decision_context_lifecycle.py`,
  `test_decision_task_state.py`
- Audited controlled harness (read to EOF):
  `rework-r2/pm-controlled/{run_pm_tests.py,sitecustomize.py,guard_preflight.py,probe_imports.py}`
- Associated single-source surface (declared ranges): `decision_points.py`,
  `decision.py`, `mw_common.py`
- `rework-r2/product-repair/report.md`, `diff/*.diff`,
  `before-bytes/`, `after-bytes/` (stage-B local product delivery)
- `rework-r2/pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/`
  (`pytest.stdout` 8F/122P, `focus.stdout` 8F/6P, `report.json`,
  `collection.node-ids.txt` 130 items, `guard-sentinel.jsonl`)
- `rework-r2/pm-controlled/runs/t10-r2-red-20261028T065500Z/` (second full red
  run, same counts, full ids)
- `rework-r2/test-preparation/report.md` and
  `checks/verify_tests.result.json` (stage-A audit: item estimates 105 + 25,
  preserved functions, skip markers)
- `evidence/implementation/t10-r2-red-disposition-20261028/check.json`,
  `products-before.json`, `report.md` (pre-repair digests and disposition)
- `evidence/implementation/t10-r2-product-absorption-20261028/check.json`
  (byte/scope absorption: 1891 mirror, 14 `.pyc`, 744 old evidence, live
  unchanged, original `needs-clarification` / `exit 2` retained)
