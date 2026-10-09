# 证据归集：mw-autopilot-slot-capacity（20260926-194558）

本文件由 `.tmp/msc-qg-evidence.py` **机器生成**：从每张实现卡的回执 `workers/<task>/report.md` 中
逐字抽取 `[VERIFY]` 行与原始输出片段，按卡面的 `- AC: … · VC: …` 绑定索引。
供 quality-gate 工作流按 AC/VC 编号 grep 使用（Step 3 证据链核查）。

- 实现卡数: **22**，其中**回执缺失 0** 
- AC 覆盖事件数: 21 · VC 覆盖事件数: 35

**已知污染与口径注记（PM 声明，供 quality-gate 判定时参考）**

1. T-07 回执的 pytest 输出里含**前一个 key**（`mw-autopilot-verify-cli`）的 `[VERIFY] VC-009: ...` 审计行，
   其编号体系与本 key 不同 ⇒ 按 `VC-009` 字面 grep 本文件会命中无关行；本 key 的 VC-009 属分析层（无实现卡）。
2. 本文件附录是各卡回执的**原始输出逐字汇集**，不保证可读性（回执自身的粘贴质量决定）；
   判定应以回执原文与 `evidence/runs/run-*.txt` 为准。
3. 调研语料实为 **24 份**（`spec-*` 17 份 + `design-*` 7 份），此前任务书里写的「14+7」为计数笔误。
4. 本文件曾于生成时出现「附录逐字符折行」缺陷（`*str` 解包），已修复并重新生成；原始缺陷见 `.agenticdoc/_pitfalls.md` 的对应条目。

## 按 AC 索引

| AC | 引用它的 [VERIFY] 断言数 |
|---|---|
| AC-005 | 0 |
| AC-006 | 2 |
| AC-007 | 1 |
| AC-010 | 12 |
| AC-012 | 3 |
| AC-013 | 8 |
| AC-016 | 4 |
| AC-017 | 4 |
| AC-018 | 19 |
| AC-019 | 21 |
| AC-020 | 9 |
| AC-021 | 52 |
| AC-022 | 3 |
| AC-023 | 2 |
| AC-024 | 4 |
| AC-025 | 4 |
| AC-026 | 6 |
| AC-027 | 45 |
| AC-028 | 37 |
| AC-029 | 6 |
| AC-030 | 5 |
| AC-031 | 2 |

## 按 VC 索引

| VC | 引用它的 [VERIFY] 断言数 |
|---|---|
| VC-004 | 0 |
| VC-005 | 0 |
| VC-006 | 0 |
| VC-007 | 2 |
| VC-008 | 1 |
| VC-011 | 15 |
| VC-012 | 1 |
| VC-014 | 3 |
| VC-015 | 8 |
| VC-018 | 4 |
| VC-019 | 4 |
| VC-020 | 4 |
| VC-021 | 4 |
| VC-022 | 15 |
| VC-023 | 4 |
| VC-024 | 19 |
| VC-025 | 5 |
| VC-026 | 5 |
| VC-027 | 51 |
| VC-028 | 51 |
| VC-029 | 0 |
| VC-030 | 0 |
| VC-031 | 2 |
| VC-032 | 2 |
| VC-033 | 4 |
| VC-034 | 4 |
| VC-035 | 4 |
| VC-036 | 4 |
| VC-037 | 1 |
| VC-038 | 4 |
| VC-039 | 45 |
| VC-040 | 20 |
| VC-041 | 20 |
| VC-042 | 20 |
| VC-043 | 47 |
| VC-044 | 2 |
| VC-045 | 2 |
| VC-046 | 4 |
| VC-047 | 4 |
| VC-049 | 2 |

## 逐卡原始证据

### T-01: conductor 守卫包（D1 正则 + D2 reject 对称守卫 + D4 stage 单调性）
- 回执: `workers\msc-t01-conductor-guards\report.md`
- AC: AC-022, AC-028 · VC: VC-029, VC-030, VC-031, VC-042

(回执未含 [VERIFY] 行)

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_guards.py -q
........                                                                 [100%]
8 passed in 0.17s
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_conductor_stage.py test_autopilot_closure.py -q
.......................................................................  [100%]
71 passed in 1.62s
> python -X utf8 -m pytest test_autopilot_stall.py test_autopilot_gates.py test_autopilot_roadmap.py test_autopilot_verdict_freshness.py -q
........................................................................ [ 73%]
.................F........                                               [100%]
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
1 failed, 97 passed
> (H:\git\mw-t01-baseline) cd packages/multi-workers && python -X utf8 -m pytest \
    test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below -q
E       AssertionError: latest report is not from the last round
E       assert 3 in [2]
FAILED ... 1 failed in 0.36s
> python -X utf8 -m pytest test_autopilot_gate_guards.py -q
    def test_gate_consumption_matches_five_digit_ids(...):
        st.timeline.append(
            "gate-answered", stage=1, detail="gate-10000 approved → stage 1 running"
        )
>       assert conductor._consumed_gate_ids(project) == {"gate-10000"}
E       AssertionError: assert set() == {'gate-10000'}
FAILED test_autopilot_gate_guards.py::test_gate_consumption_matches_five_digit_ids
1 failed, 7 passed in 0.23s
> python -X utf8 -m pytest test_autopilot_gate_guards.py -q
        _set_key_status(project, "k1", 1, "stalled")
        conductor._apply_stalled_rejections(project, st, {"k1": "stalled"}, {"k1": 1})
        rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
>       assert rm.stages[0].key_status["k1"] == "stalled"  # replay was refused
E       AssertionError: assert 'closed-legacy' == 'stalled'
FAILED test_autopilot_gate_guards.py::test_rejected_stalled_gate_is_consumed_once
1 failed, 7 passed in 0.23s
> python -X utf8 -m pytest test_autopilot_gate_guards.py -q
        assert conductor._consume_answered_gates(project, st, cfg) is True
>       assert _stage_status(project, 1) == "closed"
E       AssertionError: assert 'running' == 'closed'
FAILED test_autopilot_gate_guards.py::test_closed_stage_reopen_refused_and_deduped
FAILED test_autopilot_gate_guards.py::test_terminal_family_cross_convert_refused
FAILED test_autopilot_gate_guards.py::test_stage_confirm_replay_cannot_reopen_closed_stage
3 failed, 5 passed in 0.23s
```

</details>
### T-02: 跨语言事件集合对齐（D3 守卫 + 新事件名单）
- 回执: `workers\msc-t02-ts-event-parity\report.md`
- AC: AC-010, AC-021, AC-022 · VC: VC-012

**回执中的 [VERIFY] 行（逐字）**

- `[VERIFY] VC-012: equal=true count=23`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-012: equal=true count=23
···

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  16:57:00
   Duration  1.24s (transform 52ms, setup 0ms, import 65ms, tests 709ms, environment 0ms)
................                                                         [100%]
16 passed in 0.11s
 Test Files  2 passed (2)
      Tests  57 passed (57)
 FAIL  test/suite/autopilot-event-parity.test.ts > autopilot event vocabulary parity (AC-010 / AC-021 / AC-022, VC-012) > EVENT_TYPES is set-equal across Python and TS (both difference sets empty)
AssertionError: python-only event types (TS mirror missing them): expected [ 'target-config-rejected' ] to deeply equal []
 FAIL  test/suite/autopilot-event-parity.test.ts > ... > pre-admits every T-02 event name on both sides and in the default view
AssertionError: ts EVENT_TYPES missing target-config-rejected: expected false to be true
      Tests  2 failed | 1 passed (3)
 FAIL  test/suite/autopilot-event-parity.test.ts > ... > EVENT_TYPES is set-equal across Python and TS (both difference sets empty)
AssertionError: python-only event types (TS mirror missing them): expected [ 'review-decided' ] to deeply equal []
 FAIL  test/suite/autopilot-event-parity.test.ts > ... > pre-admits every T-02 event name on both sides and in the default view
AssertionError: ts EVENT_TYPES missing review-decided: expected false to be true
      Tests  2 failed | 1 passed (3)
```

</details>
### T-03: gate schema v2 字段 + `auto_gate_mode` 配置键
- 回执: `workers\msc-t03-gate-schema-v2\report.md`
- AC: AC-018, AC-019, AC-026 · VC: VC-011, VC-024, VC-038

**回执中的 [VERIFY] 行（逐字）**

- `## 3. `[VERIFY]` raw output`
- `task's write surface. The Python change set is verified by the task's `[VERIFY]` command`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
packages/multi-workers/autopilot/gates.py   | 261 ++++++++++++++++++++++---
packages/multi-workers/autopilot/config.py  |  21 ++-
packages/multi-workers/test_autopilot_gate_schema_v2.py (new, 27 tests)
base(12): id, kind, stage, key, created_at, created_by, question, context_refs,
          status, answered_at, answered_by, note
v2 1..26: reason_code, evidence_refs, loop, used_rounds, round_limit, credits_used,
          observed_at, verdicts_final, open_items, subject_sha256, roadmap_validation,
          proposal_sha256, goal_sha256, constraints, goal_sha256_before,
          goal_sha256_after, goal_diff, write_scope, blast_radius, answer_source,
          auto_policy_id, expires_at, evidence_anchor_mtime_ns, default_action,
          out_of_band_actions, gate_schema
consumed: consumed_at, consumed_seq
['id','kind','stage','key','created_at','created_by','question','context_refs',
 'status','answered_at','answered_by','note',
 'reason_code','evidence_refs','loop','used_rounds','round_limit','credits_used',
 'observed_at','verdicts_final','open_items','subject_sha256','roadmap_validation',
 'proposal_sha256','goal_sha256','constraints','goal_sha256_before',
 'goal_sha256_after','goal_diff','write_scope','blast_radius','answer_source',
 'auto_policy_id','expires_at','evidence_anchor_mtime_ns','default_action',
 'out_of_band_actions','gate_schema','consumed_at','consumed_seq']
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_schema_v2.py test_autopilot_config.py test_autopilot_gates.py -q
.............................................FF.....................F... [ 72%]
...........................                                              [100%]
================================== FAILURES ===================================
__________________ test_default_config_has_13_keys_in_order ___________________

    def test_default_config_has_13_keys_in_order() -> None:
>       assert len(cfg.DEFAULT_CONFIG) == 13
E       AssertionError: assert 14 == 13
E        +  where 14 = len({'advance_stall_ticks': 5, 'auto_gate_mode': 'off', 'enabled': False, 'l2_read_byte_cap': 65536, ...})

test_autopilot_config.py:113: AssertionError
_________________ test_partial_file_returns_only_written_keys _________________

    def test_partial_file_returns_only_written_keys(tmp_path: pathlib.Path) -> None:
        """... The complete 13-key view has its own sources. ..."""
        ...
>       assert len(cfg.default_config()) == 13
E       AssertionError: assert 14 == 13

test_autopilot_config.py:134: AssertionError
_ TestParseRoundTrip.test_frontmatter_has_all_schema_fields_in_canonical_order _

    def test_frontmatter_has_all_schema_fields_in_canonical_order(self, tmp_path):
        ...
>       assert keys == list(gates.FRONTMATTER_FIELDS)
E       AssertionError: assert ['id', 'gate_...ated_at', ...] == ['id', 'kind'...ated_by', ...]
E         At index 1 diff: 'gate_schema' != 'kind'
E         Right contains 27 more items, first extra item: 'evidence_refs'

test_autopilot_gates.py:221: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_config.py::test_default_config_has_13_keys_in_order - A...
FAILED test_autopilot_config.py::test_partial_file_returns_only_written_keys
FAILED test_autopilot_gates.py::TestParseRoundTrip::test_frontmatter_has_all_schema_fields_in_canonical_order
3 failed, 96 passed in 3.64s
test_autopilot_gate_schema_v2.py::test_real_historical_v1_gate_file_still_parses PASSED
test_autopilot_gate_schema_v2.py::test_unknown_field_fails_closed_naming_the_field PASSED
test_autopilot_gate_schema_v2.py::test_bad_json_evidence_refs_fails_closed PASSED
test_autopilot_gate_schema_v2.py::test_required_fields_unchanged_exact_set_and_length PASSED
============================== 4 passed in 0.07s ==============================
(a) baseline: legacy v1 parses, gate_schema=1
(a) defect caught (v2-required -> legacy rejected): ...\gate-0008.md: missing frontmatter field(s): reason_code
(b) baseline caught: ...\gate-0001.md: unknown frontmatter field 'bogus_field' (line 14)
(b) DEFECT: unknown field accepted -> gate-0001
(c) baseline caught: ...\gate-0001.md: evidence_refs must be a block list, [] or a single-line JSON array (line 14): Expecting ',' delimiter: line 1 column 10 (char 9)
(c) DEFECT: bad JSON silently became -> []
(d) defect caught: required set drifted to 7
counterfactual harness done
16 failed, 1203 passed, 10 deselected, 70 warnings in 128.09s (0:02:08)
```

</details>
### T-04: idle 看门狗：in-flight 分类判定 + 心跳 + `[IDLE_KILL]` 证据（c2）
- 回执: `workers\msc-t04-idle-heartbeat\report.md`
- AC: AC-005 · VC: VC-004, VC-005, VC-006

(回执未含 [VERIFY] 行)

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-idle-heartbeat.test.ts
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[worker] start task=t-alive type=coding phases=-
[worker] start task=t-hang type=coding phases=-
[worker] failed exit=1 elapsed=1m tools=0
[worker] start task=t-hung-tool type=coding phases=-
[worker] failed exit=1 elapsed=30m tools=1
·····

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  17:00:38
   Duration  1.08s (transform 416ms, setup 0ms, import 861ms, tests 50ms, environment 0ms)
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
[worker] start task=t-alive type=coding phases=-
[worker] failed exit=1 elapsed=30m tools=1
 FAIL  test/suite/worker-idle-heartbeat.test.ts > ... > VC-005: a real bash heartbeat keeps a silent long command alive past toolIdleMs
AssertionError: expected "Mock" to not be called at all, but actually been called 1 times
Received:
  1st Mock call:
    Array [ 1, ]
Number of calls: 1
 ❯ test/suite/worker-idle-heartbeat.test.ts:154:23
 FAIL / 1 failed | 4 skipped
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
[worker] start task=t-hung-tool type=coding phases=-
 FAIL  test/suite/worker-idle-heartbeat.test.ts > ... > VC-006: a hung in-flight tool is still killed at the tool-idle bound, with [IDLE_KILL] evidence
AssertionError: expected "Mock" to be called with arguments: [ 1 ]
Number of calls: 0
 ❯ test/suite/worker-idle-heartbeat.test.ts:213:19
 FAIL / 1 failed | 4 skipped
[worker] failed exit=1 elapsed=1m tools=0
[worker] failed exit=1 elapsed=30m tools=1
 FAIL  ... > VC-006: no in-flight tool and no token delta is still killed, with complete [IDLE_KILL] evidence
AssertionError: an idle kill must carry [IDLE_KILL] evidence: expected undefined to be defined
 ❯ test/suite/worker-idle-heartbeat.test.ts:178:64
 FAIL  ... > VC-006: a hung in-flight tool is still killed at the tool-idle bound, with [IDLE_KILL] evidence
AssertionError: the bounded in-flight kill must carry [IDLE_KILL] evidence: expected undefined to be defined
 ❯ test/suite/worker-idle-heartbeat.test.ts:216:78
 FAIL / 2 failed | 3 skipped
[IDLE_KILL] <ISO-8601> tool_in_flight=<name|none> tool_run_s=<N|-> tool_idle_s=<N|-> silence_s=<N> threshold_s=<N> threshold_kind=<idle|tool_idle> last_activity=<source>
[IDLE_KILL] 2026-09-26T09:01:22.267Z tool_in_flight=none tool_run_s=- tool_idle_s=- silence_s=60 threshold_s=60 threshold_kind=idle last_activity=session_start
[TIMEOUT] 2026-09-26T09:01:22.267Z idle: no activity for 60s (last delta -s ago, last tool -s ago)

[IDLE_KILL] 2026-09-26T09:30:22.273Z tool_in_flight=bash tool_run_s=1800 tool_idle_s=1800 silence_s=1800 threshold_s=1800 threshold_kind=tool_idle last_activity=tool_start
[TIMEOUT] 2026-09-26T09:30:22.273Z idle: in-flight tool bash silent for 1800s (tool running 1800s, threshold 1800s, last activity tool_start)
```

</details>
### T-05: 消费记录载体：门文件字段 + timeline 只读回退
- 回执: `workers\msc-t05-consumption-carrier\report.md`
- AC: AC-022, AC-023, AC-028 · VC: VC-031, VC-032, VC-043

**回执中的 [VERIFY] 行（逐字）**

- `## 2. [VERIFY] 原文与输出`
- `6. **未跑 `npm run check`**：本卡仅改 Python（TS `GATE_FRONTMATTER_FIELDS` 已由 T-03/T-09 含 `consumed_at`/`consumed_seq`，`status-model.ts:616-617`），`npm run check` 的 `biome check --write` 会重排其它并行会话的 TS 文件，违反本卡"只碰独占写面"，故跳过；Python 侧验证以本卡 `[VERIFY]` 为准。`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_consumption.py -q
.......                                                                  [100%]
7 passed in 0.12s
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py -q
............................................................             [100%]
60 passed in 1.40s
$ python -X utf8 -m pytest test_autopilot_gate_guards.py test_autopilot_gate_schema_v2.py test_autopilot_gates.py -q
73 passed in 0.27s

$ python -X utf8 -m pytest test_autopilot_xkey_cwd.py test_autopilot_timeline.py test_autopilot_conductor_stage.py test_autopilot_stall.py -q
50 passed in 1.01s

$ python -X utf8 -m pytest test_autopilot_xkey_registration.py test_autopilot_conductor_exec.py -q
60 passed in 1.38s

$ python -X utf8 -m pytest test_autopilot_e2e.py -q
3 passed, 8 deselected in 5.30s
=== (a) timeline rotated away (2-generation loss) ===
carrier written: True consumed_seq: 1
NEW _consumed_gate_ids={'gate-0001'}  -> GREEN (resolves via carrier)
OLD timeline-only      =set()  -> RED (consumption lost)
gate-answered events after replay: 0

=== (b) reused id, stale event predates the live file ===
NEW composite key      =set()  -> GREEN (new gate unconsumed)
OLD id-only key        ={'gate-0001'}  -> RED (new answer silently swallowed)
fresh answer applied, stage 1 status: running

=== (c) consume the same gate twice ===
field writes: 1 | gate-answered events: 1 | bytes identical: True
GREEN
```

</details>
### T-06: 证据快照 sidecar 与取证源解析（D-007 落地）
- 回执: `workers\msc-t06-evidence-provenance\report.md`
- AC: AC-029 · VC: VC-044, VC-045

**回执中的 [VERIFY] 行（逐字）**

- `## [VERIFY]（命令原文 + 原始输出）`
- `[VERIFY] T-06 evidence-provenance: module=packages/multi-workers/autopilot/evidence.py(new) tests=packages/multi-workers/test_autopilot_evidence.py(new) api=[snapshot(paths)->[{path,sha256,mtime_ns,bytes}], changed(before,after)->[path], evidence_digest, sidecar_path/read_sidecar/write_sidecar, record_snapshot(created|consumed), binding_of, resolve_value, resolve -> {value,binding,status,auto_release,drift,disputes,reasons,sources}] schema=gate-evidence/1 sidecar=<gates>/gate-NNNN.evidence.json reasons=[created,consumed] taken_by=conductor roles=12(min) boundary=writes_only_inside_gates, corrupt_sidecar_never_overwritten, existing_evidence_read_only min_semantics=meets>below>indeterminate correction=one_way(below only; upward ignored; stale=>indeterminate) bound=value_meets AND binding_present_and_matching missing_binding=not bound docstring_phrase='no single linear precedence, the sources answer three different propositions' verify='cd packages/multi-workers; python -X utf8 -m pytest test_autopilot_evidence.py -q' result=20 passed in 0.14s counterfactual_a=GREEN(changed non-empty; drift-blind mutant RED) counterfactual_b=GREEN(value=meets binding=unbound status='not bound'; default-bound mutant RED) counterfactual_c=GREEN(value=below; correction-blind mutant RED) anchor=E2 feature-l3-readcap-injection sha256('meets\n')=1e01e3da4a54438288d5e205b7aa535dd8e34c3eb6c3e0e9b2d1ff829f1417d2 correction(original_sha256,counted_as_done=false,dispositions=[pending-authorization],corrected_value=below) roadmap=...=done stage=closed t03_touched=no conductor_wiring=T-07 commits=0`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
cd packages/multi-workers; python -X utf8 -m pytest test_autopilot_evidence.py -q
....................                                                     [100%]
20 passed in 0.14s
== real implementation (all three must be GREEN) ==
  real case (a): GREEN  (a) changed[]=['C:/Users/WENBOZ~1/AppData/Local/Temp/tmp6f1kd7od/l3-verdict.txt']
  real case (b): GREEN  (b) value=meets binding=unbound status='not bound' auto_release=False
  real case (c): GREEN  (c) value=below status='not bound' disputes=['correction', 'claimed-done-without-bound-meets']
== mutant 1: changed() always [] (drift-blind) ==
  mutant-1 case (a): RED    (a) changed=[]
  mutant-1 case (b): GREEN  ...
  mutant-1 case (c): GREEN  ...
== mutant 2: binding_of() defaults to bound ==
  mutant-2 case (a): GREEN  ...
  mutant-2 case (b): RED    (b) binding=bound
  mutant-2 case (c): GREEN  ...
== mutant 3: correction never in force (correction-blind) ==
  mutant-3 case (a): GREEN  ...
  mutant-3 case (b): GREEN  ...
  mutant-3 case (c): RED    (c) value=indeterminate
[VERIFY] T-06 evidence-provenance: module=packages/multi-workers/autopilot/evidence.py(new) tests=packages/multi-workers/test_autopilot_evidence.py(new) api=[snapshot(paths)->[{path,sha256,mtime_ns,bytes}], changed(before,after)->[path], evidence_digest, sidecar_path/read_sidecar/write_sidecar, record_snapshot(created|consumed), binding_of, resolve_value, resolve -> {value,binding,status,auto_release,drift,disputes,reasons,sources}] schema=gate-evidence/1 sidecar=<gates>/gate-NNNN.evidence.json reasons=[created,consumed] taken_by=conductor roles=12(min) boundary=writes_only_inside_gates, corrupt_sidecar_never_overwritten, existing_evidence_read_only min_semantics=meets>below>indeterminate correction=one_way(below only; upward ignored; stale=>indeterminate) bound=value_meets AND binding_present_and_matching missing_binding=not bound docstring_phrase='no single linear precedence, the sources answer three different propositions' verify='cd packages/multi-workers; python -X utf8 -m pytest test_autopilot_evidence.py -q' result=20 passed in 0.14s counterfactual_a=GREEN(changed non-empty; drift-blind mutant RED) counterfactual_b=GREEN(value=meets binding=unbound status='not bound'; default-bound mutant RED) counterfactual_c=GREEN(value=below; correction-blind mutant RED) anchor=E2 feature-l3-readcap-injection sha256('meets\n')=1e01e3da4a54438288d5e205b7aa535dd8e34c3eb6c3e0e9b2d1ff829f1417d2 correction(original_sha256,counted_as_done=false,dispositions=[pending-authorization],corrected_value=below) roadmap=...=done stage=closed t03_touched=no conductor_wiring=T-07 commits=0
```

</details>
### T-07: 命题重写 + 自动决策核心（留痕/配额/熔断/影子/对账）
- 回执: `workers\msc-t07-auto-decision-core\report.md`
- AC: AC-016, AC-017, AC-018, AC-019, AC-020, AC-024, AC-025, AC-029 · VC: VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-033, VC-034, VC-035, VC-036, VC-046, VC-047

**回执中的 [VERIFY] 行（逐字）**

- `............................................................[VERIFY] VC-009: audit_complete=0`
- `.[VERIFY] VC-009: audit_missing=1 gaps_nonempty=true`
- `.[VERIFY] VC-009: ac_extract=correct`
- `.[VERIFY] VC-009: decision_map_parity=true`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
[CMD1] cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py -q
..........................                                               [100%]
26 passed in 0.33s

[CMD2] cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py test_autopilot_audit.py test_autopilot_timeline.py -q
............................................................[VERIFY] VC-009: audit_complete=0
.[VERIFY] VC-009: audit_missing=1 gaps_nonempty=true
.[VERIFY] VC-009: ac_extract=correct
.[VERIFY] VC-009: decision_map_parity=true
......... [ 86%]
...........                                                              [100%]
83 passed in 2.33s
(a) tautology: GREEN=True RED=True real=escalate naive=approve
(b) per-rule-false: GREEN=True RED=True real={'escalate'}
(c) shadow-zero-delta: GREEN=True RED=True
(d) persisted-breaker: GREEN=True RED=True
(e) revoke-one: GREEN=True RED=True
(f) answered_by-display-only: GREEN=True RED=True
```

</details>
### T-08: 待复核状态（case 2）+ 合法重开（两侧同波）
- 回执: `workers\msc-t08-pending-review\report.md`
- AC: AC-027, AC-028 · VC: VC-039, VC-040, VC-041, VC-042, VC-043

**回执中的 [VERIFY] 行（逐字）**

- ``[VERIFY]` markers emitted by the new suite (`pytest -s`):`
- `[VERIFY] VC-039: enum=1 dep_satisfied=0 dispatched=0 unknown_value_fail_closed=true`
- `[VERIFY] VC-D2-02: dep_locked=true negative_control=dispatched`
- `[VERIFY] VC-D2-03: pending_review_rows=0 negative_control=dispatched`
- `[VERIFY] VC-039: blocked=true counterfactual_dossier=1`
- `[VERIFY] VC-040: batched=2 counterfactual_batched=0`
- `[VERIFY] VC-040: in_flight_excluded=true`
- `[VERIFY] VC-041: escalated=1 state_unchanged=true counterfactual_escalated=0`
- `[VERIFY] VC-041: fallback=created_at+48h state_unchanged=true`
- `[VERIFY] VC-042: resume=running rework=running escalate=stalled done_exit=rejected closed_legacy_exit=rejected`
- `[VERIFY] VC-042: approved=running rejected=running closed_legacy_produced=0 replay_idempotent=true`
- `[VERIFY] VC-042: refused=1 dedup=true stage=closed`
- `[VERIFY] VC-043: stage=closed new_gates=0`
- `[VERIFY] VC-024: kinds=6 missing_fields=0 ttl_hours=48 default_action=escalate-to-human`
- `[VERIFY] VC-024: missing_fields=0 healthy=true gates_text_line=0`
- `[VERIFY] VC-045: snapshot_sha_matches=true replay_misbound=0`
- `···························[VERIFY] P1: crosslang_verdict_match=55/55`
- `·[VERIFY] P2: canonical_sha_match=32 sha256_equal=true`
- `·····················[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32`
- `··[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
_process_deferred_reviews(project_root, st, stage, status_of, rows)   # :308
_stage_closure(project_root, st, stage, rm_path, status_of, rows)     # :309
for entry in stage.keys:
    if status_of.get(key) in _DISPATCH_SKIP_STATUSES: continue        # :314
path = gates.create(...)                                # :2472
fields = _gate_default_fields(path)                     # :2474  (existing mechanism: _rewrite_gate_fields)
if machine_fields:
    fields.update({k: str(v) for k, v in machine_fields.items()})
if fields:
    _rewrite_gate_fields(path, fields)                  # :2479  <- BEFORE the snapshot
snapshot_gate_created(project_root, path)               # :2481
created_at: 2026-09-26T09:47:03+00:00
...
default_action: escalate-to-human
expires_at: 2026-09-28T09:47:03+00:00
reason_code: l3-no-verdict
mode=create
reason_code=None expires_at=None default_action=None
missing_fields=['reason_code', 'expires_at', 'default_action']
healthy=False
issues=["gate gate-0001 (stalled, key=k1) pending since 2026-09-26T09:38:45+00:00 with no expires_at/default_action - set the default action or answer the gate (AC-019: no implicit permanent retention)"]
doctor_gates_text=['gates: 1 pending (1s oldest, 0 parse error(s), 0 drift)']
mode=_create_gate
reason_code='l3-no-verdict' expires_at=None default_action=None
missing_fields=['expires_at', 'default_action']
healthy=False
issues=["gate gate-0001 (stalled, key=k1) pending since 2026-09-26T09:39:03+00:00 with no expires_at/default_action - set the default action or answer the gate (AC-019: no implicit permanent retention)"]
doctor_gates_text=['gates: 1 pending (0s oldest, 0 parse error(s), 0 drift)']
mode=_create_gate
reason_code='l3-no-verdict' expires_at='2026-09-28T09:45:49+00:00' default_action='escalate-to-human'
missing_fields=[]
healthy=True
issues=[]
doctor_gates_text=[]
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q
...............                                                          [100%]
15 passed in 0.84s

$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_closure.py test_autopilot_conductor.py test_doctor_gates.py test_autopilot_auto_decision.py -q
116 passed, 52 warnings in 20.21s
[VERIFY] VC-039: enum=1 dep_satisfied=0 dispatched=0 unknown_value_fail_closed=true
[VERIFY] VC-D2-02: dep_locked=true negative_control=dispatched
[VERIFY] VC-D2-03: pending_review_rows=0 negative_control=dispatched
[VERIFY] VC-039: blocked=true counterfactual_dossier=1
[VERIFY] VC-040: batched=2 counterfactual_batched=0
[VERIFY] VC-040: in_flight_excluded=true
[VERIFY] VC-041: escalated=1 state_unchanged=true counterfactual_escalated=0
[VERIFY] VC-041: fallback=created_at+48h state_unchanged=true
[VERIFY] VC-042: resume=running rework=running escalate=stalled done_exit=rejected closed_legacy_exit=rejected
[VERIFY] VC-042: approved=running rejected=running closed_legacy_produced=0 replay_idempotent=true
[VERIFY] VC-042: refused=1 dedup=true stage=closed
[VERIFY] VC-043: stage=closed new_gates=0
[VERIFY] VC-024: kinds=6 missing_fields=0 ttl_hours=48 default_action=escalate-to-human
[VERIFY] VC-024: missing_fields=0 healthy=true gates_text_line=0
[VERIFY] VC-045: snapshot_sha_matches=true replay_misbound=0
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
    test/suite/autopilot-config-parity.test.ts test/suite/autopilot-console.test.ts test/suite/autopilot-monitor.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
···························[VERIFY] P1: crosslang_verdict_match=55/55
·[VERIFY] P2: canonical_sha_match=32 sha256_equal=true
·····················[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32
··[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14
···········
 Test Files  3 passed (3)
      Tests  62 passed (62)
$ python -X utf8 .tmp/t08_counterfactuals.py a   # remove the pending-review status change
(a) GREEN: closure-precondition batch with pending-review = pass
(a) RED as expected (pending-review removed): AssertionError

$ python -X utf8 .tmp/t08_counterfactuals.py b   # remove expires_at/default_action stamps
(b) GREEN: defaults present, missing_fields=[] healthy=True
(b) RED as expected: missing expires_at/default_action
(b) RED as expected: missing_fields=['expires_at', 'default_action'] healthy=False

$ python -X utf8 .tmp/t08_counterfactuals.py c   # move the stamps AFTER the evidence snapshot
(c) GREEN: defaults-before-snapshot sha_match=True
(c) RED as expected: late-stamp sha_match=False refusal=replay-misbound

$ python -X utf8 .tmp/t08_counterfactuals.py d   # count pending-review as terminal
(d) GREEN: pending-review blocks stage closure
(d) RED as expected: pending-review counted terminal -> stage closed
```

</details>
### T-09: 三层呈现（层 A/B + 字段镜像 + DRIFT + 禁 LLM）
- 回执: `workers\msc-t09-ts-presentation\report.md`
- AC: AC-007, AC-012, AC-021, AC-026 · VC: VC-008, VC-014, VC-027, VC-028, VC-037, VC-038

**回执中的 [VERIFY] 行（逐字）**

- `## `[VERIFY]` raw output`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-gate-presentation.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

············

 Test Files  1 passed (1)
      Tests  12 passed (12)
   Start at  17:12:52
   Duration  1.43s (transform 293ms, setup 0ms, import 501ms, tests 806ms, environment 0ms)
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/suite/autopilot-monitor.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·························································

 Test Files  2 passed (2)
      Tests  57 passed (57)
   Start at  17:12:57
   Duration  1.07s (transform 635ms, setup 0ms, import 1.05s, tests 520ms, environment 0ms)
 ✓ gate frontmatter mirror (VC-D6-06) > mirrors gates.FRONTMATTER_FIELDS item-for-item in the same order (40 names) 159ms
 ✓ gate frontmatter mirror (VC-D6-06) > parses a v2 gate with both evidence_refs encodings and rejects unknown fields 5ms
 ✓ layer B gate card contract (AC-026) > renders exactly 1 + 13*N lines: N=1 -> 14, N=3 -> 40 7ms
 ✓ layer B gate card contract (AC-026) > keeps every line <= 110 columns even with a 400-char question and long v2 values 3ms
 ✓ layer B gate card contract (AC-026) > renders the one sentinel literal for absent v2 fields and no hedge prose 3ms
 ✓ layer B gate card contract (AC-026) > reports missing fields only for pending gates, never for answered history 2ms
 ✓ layer B gate card contract (AC-026) > L6/L8/L9/L12/L13 carry evidence, replay history, default/ttl/auto, open items and answer source 7ms
 ✓ layer B gate card contract (AC-026) > marks DRIFT( when an evidence mtime is newer than created_at, and omits it otherwise 6ms
 ✓ layer B gate card contract (AC-026) > shows auto=off when the kill switch is absent and auto=live when set to live 3ms
 ✓ layer A monitor gate lines (AC-012) > renders one line per pending gate with age and DRIFT, all <= 110 columns 12ms
 ✓ layer A monitor gate lines (AC-012) > omits DRIFT when the evidence is older than created_at 3ms
 ✓ render functions never reference dispatch/model/provider (VC-D6-05) > keeps monitor renderMonitorLines, console cmdGates and renderGateCards free of model calls 3ms

 Test Files  1 passed (1)
      Tests  12 passed (12)
   FAIL layer B ... marks DRIFT( when an evidence mtime is newer than created_at, and omits it otherwise
   AssertionError: expected 'evidence: _autopilot/stages/stage-1-close.md (8B, sections=[Keys], mtime=2026-09-27T01:00:00.000Z)' to contain 'DRIFT('
   FAIL layer A ... renders one line per pending gate with age and DRIFT, all <= 110 columns
   AssertionError: expected 'gates: 2 pending - gate-0008 (stage-close) stage=1 age=3h 55m -> /autopilot gate gate-0008 approve|reject' to contain 'DRIFT('
    Test Files  1 failed (1)   Tests  2 failed | 10 passed (12)
   FAIL layer B ... keeps every line <= 110 columns even with a 400-char question and long v2 values
   AssertionError: gate-0001 [stalled] ... waited=3.9h: expected 126 to be less than or equal to 110
   FAIL layer B ... L6/L8/L9/L12/L13 carry evidence, replay history, default/ttl/auto, open items and answer source
   AssertionError: Q: proceed? (full: ...gate-0008.md): expected 128 to be less than or equal to 110
    Test Files  1 failed (1)   Tests  2 failed | 10 passed (12)
TS count=40  PY count=40
01  ==  ts=id                         py=id
02  ==  ts=kind                       py=kind
03  ==  ts=stage                      py=stage
04  ==  ts=key                        py=key
05  ==  ts=created_at                 py=created_at
06  ==  ts=created_by                 py=created_by
07  ==  ts=question                   py=question
08  ==  ts=context_refs               py=context_refs
09  ==  ts=status                     py=status
10  ==  ts=answered_at                py=answered_at
11  ==  ts=answered_by                py=answered_by
12  ==  ts=note                       py=note
13  ==  ts=reason_code                py=reason_code
14  ==  ts=evidence_refs              py=evidence_refs
15  ==  ts=loop                       py=loop
16  ==  ts=used_rounds                py=used_rounds
17  ==  ts=round_limit                py=round_limit
18  ==  ts=credits_used               py=credits_used
19  ==  ts=observed_at                py=observed_at
20  ==  ts=verdicts_final             py=verdicts_final
21  ==  ts=open_items                 py=open_items
22  ==  ts=subject_sha256             py=subject_sha256
23  ==  ts=roadmap_validation         py=roadmap_validation
24  ==  ts=proposal_sha256            py=proposal_sha256
25  ==  ts=goal_sha256                py=goal_sha256
26  ==  ts=constraints                py=constraints
27  ==  ts=goal_sha256_before         py=goal_sha256_before
28  ==  ts=goal_sha256_after          py=goal_sha256_after
29  ==  ts=goal_diff                  py=goal_diff
30  ==  ts=write_scope                py=write_scope
31  ==  ts=blast_radius               py=blast_radius
32  ==  ts=answer_source              py=answer_source
33  ==  ts=auto_policy_id             py=auto_policy_id
34  ==  ts=expires_at                 py=expires_at
35  ==  ts=evidence_anchor_mtime_ns   py=evidence_anchor_mtime_ns
36  ==  ts=default_action             py=default_action
37  ==  ts=out_of_band_actions        py=out_of_band_actions
38  ==  ts=gate_schema                py=gate_schema
39  ==  ts=consumed_at                py=consumed_at
40  ==  ts=consumed_seq               py=consumed_seq
item-for-item same order: true
```

</details>
### T-10: 守卫覆盖面：`_autopilot/**` 纳入封堵（安全属性）
- 回执: `workers\msc-t10-guard-coverage\report.md`
- AC: AC-020, AC-030 · VC: VC-025, VC-026

**回执中的 [VERIFY] 行（逐字）**

- `## 3. `[VERIFY]` 原文与输出`
- ``xkeyGuardedDir` 追加 `"gates"`。命令同 `[VERIFY]`。原始输出：`
- `改动（临时）：`boundary()` 返回 `""`（即只剩 plain substring 匹配）。命令同 `[VERIFY]`。原始输出：`
- `⇒ 缺路径边界时 `_autopilotX` 被误伤（路径判定、bash 判定、真实派发三处红）。说明边界**确实存在且被测试锚定**。随后从备份还原，重跑 `[VERIFY]` 复绿（见 §3）。`
- `- 对照实验的临时改动全部从 `%TEMP%` 备份还原，最终 `[VERIFY]` 复绿。`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/xkey-gate-guard-coverage.test.ts
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

···········

 Test Files  1 passed (1)
      Tests  11 passed (11)
   Start at  17:03:29
   Duration  3.49s (transform 2.16s, setup 0ms, import 3.14s, tests 225ms, environment 0ms)
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

xxx·xxx····

 Test Files  1 failed (1)
      Tests  6 failed | 5 passed (11)
 FAIL  test/suite/xkey-gate-guard-coverage.test.ts > xkey guard path matcher (T-10, VC-025/VC-026) > blocks every _autopilot audit/control target by absolute path
AssertionError: timeline.jsonl: expected false to be true // Object.is equality
- Expected
+ Received
- true
+ false
 ❯ test/suite/xkey-gate-guard-coverage.test.ts:177:68

 FAIL  test/suite/xkey-gate-guard-coverage.test.ts > xkey guard real tool_call dispatch (T-10, VC-025/VC-026) > VC-025: write/edit of timeline.jsonl, config.json, auto-decisions.jsonl and gates/** are all refused, never land, and leave a trace
AssertionError: expected false to be true // Object.is equality
 ❯ test/suite/xkey-gate-guard-coverage.test.ts:293:27
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

···x·x·x···

 Test Files  1 failed (1)
      Tests  3 failed | 8 passed (11)
 FAIL  test/suite/xkey-gate-guard-coverage.test.ts > xkey guard path matcher (T-10, VC-025/VC-026) > does NOT hit path-boundary lookalikes (_autopilotX, _autopilot-backup)
AssertionError: expected true to be false // Object.is equality
- Expected
+ Received
- false
+ true
 ❯ test/suite/xkey-gate-guard-coverage.test.ts:199:77

 FAIL  test/suite/xkey-gate-guard-coverage.test.ts > xkey guard path matcher (T-10, VC-025/VC-026) > verdicts on bash commands: writes refused, reads allowed, lookalikes untouched
AssertionError: echo x > .agenticdoc/_autopilotX/timeline.jsonl: expected true to be false // Object.is equality
 ❯ test/suite/xkey-gate-guard-coverage.test.ts:234:80

 FAIL  test/suite/xkey-gate-guard-coverage.test.ts > xkey guard real tool_call dispatch (T-10, VC-025/VC-026) > does not hit the _autopilotX lookalike: the write lands and no trace is recorded
AssertionError: expected true to be false // Object.is equality
 ❯ test/suite/xkey-gate-guard-coverage.test.ts:324:31
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1098 files in 594ms. Fixed 2 files.

> pi-monorepo@0.0.3 check:pinned-deps
> node scripts/check-pinned-deps.mjs


> pi-monorepo@0.0.3 check:ts-imports
> node scripts/check-ts-relative-imports.mjs


> pi-monorepo@0.0.3 check:shrinkwrap
> node scripts/generate-coding-agent-shrinkwrap.mjs --check

packages/coding-agent/npm-shrinkwrap.json is up to date.

> pi-monorepo@0.0.3 check:install-lock:coding-agent
> node scripts/generate-coding-agent-install-lock.mjs --check

packages/coding-agent/install-lock is up to date.

> pi-monorepo@0.0.3 check:browser-smoke
> node scripts/check-browser-smoke.mjs
```

</details>
### T-11: parity 语料重冻（`auto_gate_mode` 两侧镜像 + 计数断言）
- 回执: `workers\msc-t11-parity-corpus\report.md`
- AC: AC-010, AC-018 · VC: VC-011, VC-022

**回执中的 [VERIFY] 行（逐字）**

- `[VERIFY] P4: corpus_sha256=c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6 cases=55 categories=['D1', 'D2', 'D3', 'D4', 'D5', 'D6']`
- `[VERIFY] P1: crosslang_verdict_match=55/55`
- `[VERIFY] P2: canonical_sha_match=32 sha256_equal=true`
- `[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32`
- `[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14`
- `[VERIFY] P4: corpus_sha256=c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6 cases=55 categories=D1,D2,D3,D4,D5,D6`
- `[VERIFY] P5: key_order_match=true defaults_match=true bool=3 list=1 str=1 enum=1 int=8`
- `[VERIFY] P1: crosslang_verdict_match=55/55`
- `[VERIFY] P2: canonical_sha_match=32 sha256_equal=true`
- `[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32`
- `[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
for (const [field, allowed] of Object.entries(ENUM_FIELDS)) {
    if (!(field in cfg)) continue;
    const value = cfg[field];
    if (typeof value !== "string" || !allowed.includes(value)) {
        errors.push(`${field}: expected one of ${allowed.join(", ")}, got ${JSON.stringify(value)}`);
    }
}
old sha256 = 951987eaf2abebfa256365ed6642ce1ae0b077a2a6a6c18b4f974729c7dc594d
old count  = 53
new sha256 = c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6
new count  = 55

removed: none
changed: none
added (2):
  + {"id": "enum-auto-gate-mode-invalid", "categories": ["D5"], "payload_text": "{\"auto_gate_mode\": \"on\"}", "expected": {"verdict": "reject", "error_fields": ["auto_gate_mode"]}}
  + {"id": "partial-key-auto_gate_mode", "categories": ["D2"], "payload_text": "{\"auto_gate_mode\": \"live\"}", "expected": {"verdict": "accept", "error_fields": []}}

OK: additive-only, no case removed or modified
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config_parity.py -q
.....                                                                    [100%]
5 passed in 0.50s
[VERIFY] P4: corpus_sha256=c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6 cases=55 categories=['D1', 'D2', 'D3', 'D4', 'D5', 'D6']
[VERIFY] P1: crosslang_verdict_match=55/55
[VERIFY] P2: canonical_sha_match=32 sha256_equal=true
[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32
[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14
5 passed in 0.34s
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] P4: corpus_sha256=c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6 cases=55 categories=D1,D2,D3,D4,D5,D6
[VERIFY] P5: key_order_match=true defaults_match=true bool=3 list=1 str=1 enum=1 int=8
[VERIFY] P1: crosslang_verdict_match=55/55
[VERIFY] P2: canonical_sha_match=32 sha256_equal=true
[VERIFY] P3: py_to_ts_idempotent=32 ts_to_py_idempotent=32
[VERIFY] P6: partial_single_key=29 raw_view_partial=true effective_view_14=true fields_covered=14

 Test Files  2 passed (2)
      Tests  6 passed (6)
   Duration  955ms
cases 55 -> 54; sha re-frozen; FROZEN_CORPUS_COUNT stays 55
RED as required:
    File "H:\git\Multi-Workers\packages\multi-workers\test_autopilot_config_parity.py", line 314, in test_p4_corpus_integrity
      assert len(corpus["cases"]) == FROZEN_CORPUS_COUNT
  AssertionError
AssertionError: expected 54 to be 55 // Object.is equality
    104|   expect(CORPUS.cases.length).toBe(FROZEN_CORPUS_COUNT);
      Tests  1 failed | 1 passed (2)
AssertionError: enum-auto-gate-mode-invalid: ts vs corpus: expected 'accept' to be 'reject' // Object.is equality
Expected: "reject"
    275|    expect(tsCase.verdict, `${testCase.id}: ts vs corpus`).toBe(testCase.expected.verdict);
AssertionError: partial-key-auto_gate_mode: ts canonical sha: expected 'c58a55a8…' to be 'bcec357b…'
AssertionError: partial-key-auto_gate_mode: py -> ts bytes: expected 'c58a55a8…' to be 'bcec357b…'
      Tests  3 failed | 1 passed (4)
FAIL ... > AC-006/AC-012: the 13-key mirror registers xkey_verify_cwd as a string ...
AssertionError: expected [ 'enabled', 'paused', …(12) ] to have a length of 13 but got 14
FAIL ... > AC-025: /autopilot enable writes config ...
AssertionError: expected { enabled: true, paused: false, …(12) } to deeply equal { enabled: true, paused: false, …(11) }
+   "auto_gate_mode": "off",
      Tests  2 failed | 35 passed (37)
```

</details>
### T-12: 归属语义统一（`origin` 列）与 `worker_timeout_min` 接线
- 回执: `workers\msc-t12-attribution-timeout\report.md`
- AC: AC-013, AC-021 · VC: VC-015, VC-027, VC-028

**回执中的 [VERIFY] 行（逐字）**

- `## 3. [VERIFY] — raw output`
- `[VERIFY] VC-015: columns=7/8/9 ts_order_locked=true`
- `.[VERIFY] VC-027: distinguishable=true`
- `.[VERIFY] VC-028: fallback=path misjudged_conductor=false`
- `.[VERIFY] counterfactual-a: rows=6 judged=manual capacity=0 prefix_would_count=6`
- `.[VERIFY] call-sites: agree=3/3 rows=3`
- `..[VERIFY] counterfactual-b: header=timeout: 45 absent_when_unconfigured=true`
- `..[VERIFY] dispatch: origin=conductor timeout=45 row_verified=true`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
def worker_origin(row) -> str:            # "conductor" | "manual"
    raw = str(row.get("origin", "") or "").strip().lower()
    return WORKER_ORIGIN_CONDUCTOR if raw == WORKER_ORIGIN_CONDUCTOR else WORKER_ORIGIN_MANUAL

def worker_path_key(task_path) -> str:    # ".agenticdoc/<key>/workers/..." -> <key>, else ""
    match = _WORKER_PATH_KEY_RE.search(str(task_path or "").replace("\\", "/"))
    return match.group(1) if match else ""

def worker_owner_key(row) -> str:         # origin-independent, path fallback (VC-028)
    return worker_path_key(str(row.get("task_path", "")))

def worker_is_conductor(row) -> bool:
    return worker_origin(row) == WORKER_ORIGIN_CONDUCTOR

def row_belongs_to(row, key) -> bool:     # the unified slot predicate
    if not worker_is_conductor(row):
        return False
    return worker_owner_key(row) == key
normalizeWorkerOrigin(raw)  // only literal "conductor" -> "conductor", everything else -> "manual"
workerOrigin(entry)         // entry.origin ?? "manual"   (legacy rows are manual)
workerOwnerKey(entry)       // WORKER_PATH_KEY_RE on taskPath, or ""
workerBelongsToKey(entry,key) // workerOrigin(entry)==="conductor" && workerOwnerKey(entry)===key
...........                                                              [100%]
11 passed in 0.12s
[VERIFY] VC-015: columns=7/8/9 ts_order_locked=true
..{"cli": "pi", "dispatched_at": "2026-09-26T00:00:00.000Z", "model": "gpt-5", "origin": "manual", "provider": "timi", "status": "running", "task_key": "manual-task", "task_path": "H:/proj/.agenticdoc/k/workers/manual-task/task.md", "updated_at": "2026-09-26T00:00:00.000Z"}
.[VERIFY] VC-027: distinguishable=true
.[VERIFY] VC-028: fallback=path misjudged_conductor=false
.[VERIFY] counterfactual-a: rows=6 judged=manual capacity=0 prefix_would_count=6
.[VERIFY] call-sites: agree=3/3 rows=3
..[VERIFY] counterfactual-b: header=timeout: 45 absent_when_unconfigured=true
..[VERIFY] dispatch: origin=conductor timeout=45 row_verified=true
.
11 passed in 0.10s
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

······

 Test Files  1 passed (1)
      Tests  6 passed (6)
   Start at  17:16:29
   Duration  360ms (transform 26ms, setup 0ms, import 20ms, tests 11ms, environment 0ms)
        # Capacity (conductor's in_flight_keys caliber): no key is owned.
        canonical_keys = {
            key for key in roadmap_keys if any(mw_common.row_belongs_to(r, key) for r in rows)
        }
>       assert canonical_keys == set()
E       AssertionError: assert {'feature-cig...control-hitl'} == set()
E
E       Extra items in the left set:
E         'feature-false-meets-remediation'
E         'feature-sampling-human-channel'
E         'feature-cigate-install-kit'
E         'feature-l3-verdict-source-fallback'
E         'feature-gui-time-mvp-board'
E         'gui-run-control-hitl'
E         Use -v to get more diff

test_autopilot_attribution.py:185: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_attribution.py::test_six_prefix_rows_are_manual_and_consume_no_slot
1 failed, 10 deselected in 0.18s
        assert result.ok and result.row_verified
        task_md = result.task_md.read_text(encoding="utf-8")
>       assert "timeout: 45" in task_md
E       AssertionError: assert 'timeout: 45' in '---\ntype: phase-writer\norigin: conductor\nloop: exec:k1:t-12\nattempt: 1\n---\n\nWire it.\n\n'

test_autopilot_attribution.py:302: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_attribution.py::test_render_task_md_renders_timeout_header
FAILED test_autopilot_attribution.py::test_dispatch_writes_origin_and_reachable_timeout
2 failed, 1 passed, 8 deselected in 0.19s
```

</details>
### T-13: doctor gate 段（I1–I8）+ `mw autopilot gates --json`
- 回执: `workers\msc-t13-doctor-cli\report.md`
- AC: AC-006, AC-012, AC-019, AC-031 · VC: VC-007, VC-014, VC-024, VC-049

**回执中的 [VERIFY] 行（逐字）**

- `| `packages/multi-workers/test_doctor_gates.py` | new test file, 30 cases + `[VERIFY]` markers | whole file |`
- ``[VERIFY]` markers asserted by the suite:`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
### python -X utf8 -m pytest test_doctor_gates.py -q
30 passed, 52 warnings in 18.59s

### python -X utf8 -m pytest test_autopilot_audit.py test_mw_autopilot_cli.py -q
30 passed in 1.80s
(a) parse_errors: 1
(a) issue_fix_string: ['gate file invalid: ...gate-0099.md (...missing frontmatter field(s): question, created_at, created_by, kind) - fix the frontmatter or move the file out of _autopilot/gates']
(a) exit_code: 1
    text row: gates: 0 pending (0s oldest, 1 parse error(s), 0 drift)
(b) segment_present: True
(b) healthy: True
(b) gates_line_in_text: False
(b) issues: []
(c) snapshot_identical: True
(c) entries: 5
(d) roadmap_validation: {"path": "..._roadmap.md", "exists": true,
                        "problems": ["stage 1: Keys table has no key rows (>= 1 required)"], "error": null}
(d) suggestions: ['roadmap invalid: stage 1: Keys table has no key rows (>= 1 required) - validate_roadmap ran but the conductor does not enforce it yet']
```

</details>
### T-14: 文档 + 产物重建 + 全量回归收口
- 回执: `workers\msc-t14-docs-dist-regression\report.md`
- AC: (无) · VC: (无)

(回执未含 [VERIFY] 行)

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
> cd packages/multi-workers && python -X utf8 -m pytest -q
...
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
2 failed, 1373 passed, 10 deselected, 126 warnings in 153.61s (0:02:33)
> cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/
 Test Files  5 failed | 88 passed | 1 skipped (94)
      Tests  15 failed | 498 passed | 3 skipped (516)
   Start at  18:37:41
   Duration  289.97s
> cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/
 Test Files  21 passed (21)
      Tests  502 passed (502)
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_readcap_injection.py test_rag_research.py -q
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
1 failed, 21 passed in 0.52s
packages/multi-workers/CHANGELOG.md
packages/coding-agent/CHANGELOG.md
packages/multi-workers/UPDATE.md
packages/multi-workers/test_autopilot_readcap_injection.py   (expectation refresh only)
packages/multi-workers/test_rag_research.py                 (expectation refresh only)
```

</details>
### T-15: 计数锁刷新（T-03 协调缺口修补）
- 回执: `workers\msc-t15-count-locks\report.md`
- AC: AC-018, AC-026 · VC: VC-011, VC-024, VC-038

**回执中的 [VERIFY] 行（逐字）**

- `## 4. [VERIFY] 原文与输出`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
DEFAULT_CONFIG      = 14
FRONTMATTER_FIELDS  = 40
EFFECTIVE_KEYS      = ('xkey_verify_cmd', 'xkey_verify_cwd')   # 2 个，无 auto_gate_mode
assert keys == list(gates.FRONTMATTER_FIELDS)
assert len(keys) == 12
# Count/order changed in mw-autopilot-slot-capacity (T-03): the schema
# grew 12 -> 40 fields and create() now emits the v2 `gate_schema`
# marker as the second line, so the emitted block is base 12 + marker.
assert len(gates.FRONTMATTER_FIELDS) == 40
assert keys == [
    gates.FRONTMATTER_FIELDS[0],
    "gate_schema",
    *gates.FRONTMATTER_FIELDS[1:12],
]
assert len(keys) == 13  # base 12 + gate_schema
def test_machine_layer_effective_keys_stay_two_and_exclude_auto_gate_mode() -> None:
    """Machine layer stays exactly {xkey_verify_cmd, xkey_verify_cwd}: the v2
    auto_gate_mode key is project/default only, never machine-overridable.

    Count lock refreshed/negative lock added by mw-autopilot-slot-capacity (T-03).
    Counterfactual: adding `auto_gate_mode` to EFFECTIVE_KEYS turns this red.
    """
    assert ec.EFFECTIVE_KEYS == ("xkey_verify_cmd", "xkey_verify_cwd")
    assert len(ec.EFFECTIVE_KEYS) == 2
    assert "auto_gate_mode" not in ec.EFFECTIVE_KEYS
........................................................................ [ 58%]
....................................................                     [100%]
124 passed in 3.10s
..FFF                                                                    [100%]
================================== FAILURES ===================================
___________________________ test_p2_crosslang_bytes ___________________________
E           AssertionError: int-valid-4: canonical bytes differ (py=c58a55a8ca515015cbfc03a0a25c00e2277e7d463c2a35463c25cc34d0bb9cf9 ts=54ad9735d02c11a1e47b77615d77b2fd2d020766f5eee533ff2e0850cc2fae95)
test_autopilot_config_parity.py:351: AssertionError
________________________ test_p3_crossread_idempotence ________________________
E           AssertionError: int-valid-4: ts cross-read
E           assert 'reject' == 'accept'
test_autopilot_config_parity.py:370: AssertionError
_________________________ test_p6_partial_single_key __________________________
E           AssertionError: int-valid-4: py effective key count
E           assert 14 == 13
test_autopilot_config_parity.py:423: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_config_parity.py::test_p2_crosslang_bytes - AssertionEr...
FAILED test_autopilot_config_parity.py::test_p3_crossread_idempotence - Asser...
FAILED test_autopilot_config_parity.py::test_p6_partial_single_key - Assertio...
3 failed, 2 passed in 0.71s
>       assert len(cfg.DEFAULT_CONFIG) == 15
E       AssertionError: assert 14 == 15
test_autopilot_config.py:114: AssertionError
FAILED test_autopilot_config.py::test_default_config_has_14_keys_in_order - A...
1 failed in 0.12s
>       assert len(keys) == 14  # base 12 + gate_schema
E       AssertionError: assert 13 == 14
E        +  where 13 = len(['id', 'gate_schema', 'kind', 'stage', 'key', 'created_at', ...])
test_autopilot_gates.py:230: AssertionError
1 failed in 0.12s
real EFFECTIVE_KEYS=('xkey_verify_cmd', 'xkey_verify_cwd') len=2 -> GREEN
patched EFFECTIVE_KEYS=('xkey_verify_cmd', 'xkey_verify_cwd', 'auto_gate_mode') -> RED (AssertionError)
```

</details>
### T-16: 归属判据委派（T-12 遗留缺口修补）
- 回执: `workers\msc-t16-attribution-delegation\report.md`
- AC: AC-021 · VC: VC-027, VC-028

**回执中的 [VERIFY] 行（逐字）**

- `Raw `[VERIFY]` lines from `pytest test_autopilot_attribution.py -q -s``
- `[VERIFY] equivalence row=conductor/keyed/k1 key=k1 local=True canonical=True equal=True`
- `[VERIFY] equivalence row=conductor/keyed/k1 key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/keyed/k1 key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/keyed/k2 key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/keyed/k2 key=k2 local=True canonical=True equal=True`
- `[VERIFY] equivalence row=conductor/keyed/k2 key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/scratch key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/scratch key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=conductor/scratch key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/keyed key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/keyed key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/keyed key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/scratch key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/scratch key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/scratch key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/backslash key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/backslash key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=legacy/no-origin/backslash key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=unknown-origin key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=unknown-origin key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=unknown-origin key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=empty-origin key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=empty-origin key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=empty-origin key=k3 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/other-key key=k1 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/other-key key=k2 local=False canonical=False equal=True`
- `[VERIFY] equivalence row=manual/other-key key=k3 local=False canonical=False equal=True`
- `[VERIFY] counterfactual-b: rows=10 pairs=30 mismatches=0 prefix_divergence_rows=7`
- `[VERIFY] equivalence row=conductor/scratch          key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=manual/keyed               key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k1 local=True canonical=False equal=False`
- `[VERIFY] equivalence row=legacy/no-origin/scratch   key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=legacy/no-origin/backslash key=k2 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=unknown-origin             key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=empty-origin               key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=manual/other-key           key=k1 local=True  canonical=False equal=False`
- `[VERIFY] equivalence row=manual/other-key           key=k3 local=True  canonical=False equal=False`
- `[VERIFY] T-16: delegate=single_canonical origin_stamp=conductor.py:4335 row_belongs_to=delegates:2372 monitor=workerBelongsToKey/workerOwnerKey:618,624-627 equivalence=30/30 mismatches=0 counterfactual_a=red(slotsUsed 0 vs 1) counterfactual_b=red(9/30 mismatch) counterfactual_c=red(1 vs 0) verify=13+54+27 green`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
   def _row_belongs_to(row: dict, key: str) -> bool:
       """Single canonical owner predicate (T-12/AC-021): delegate to
       `mw_common.row_belongs_to`; no local prefix/path rule may exist here."""
       return mw_common.row_belongs_to(row, key)
   "model": "",
   # D-019/AC-021: the read side normalises a missing
   # origin to `manual`, which would drop this re-created
   # conductor row from slot accounting (`slotsUsed`
   # under-counts, `manualRunning` over-counts). Stamp it
   # exactly like dispatch.py does for fresh rows.
   "origin": mw_common.WORKER_ORIGIN_CONDUCTOR,
     const busyKeys = new Set<string>();
     for (const w of workers) {
         const owner = workerOwnerKey(w);
         if (owner !== "" && allKeys.includes(owner) && workerBelongsToKey(w, owner)) busyKeys.add(owner);
     }
[VERIFY] equivalence row=conductor/keyed/k1 key=k1 local=True canonical=True equal=True
[VERIFY] equivalence row=conductor/keyed/k1 key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/keyed/k1 key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/keyed/k2 key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/keyed/k2 key=k2 local=True canonical=True equal=True
[VERIFY] equivalence row=conductor/keyed/k2 key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/scratch key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/scratch key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=conductor/scratch key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/keyed key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/keyed key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/keyed key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/scratch key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/scratch key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/scratch key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/backslash key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/backslash key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=legacy/no-origin/backslash key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=unknown-origin key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=unknown-origin key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=unknown-origin key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=empty-origin key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=empty-origin key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=empty-origin key=k3 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/other-key key=k1 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/other-key key=k2 local=False canonical=False equal=True
[VERIFY] equivalence row=manual/other-key key=k3 local=False canonical=False equal=True
[VERIFY] counterfactual-b: rows=10 pairs=30 mismatches=0 prefix_divergence_rows=7
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_attribution.py -q
.............                                                            [100%]
13 passed in 0.11s
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py -q
......................................................                   [100%]
54 passed in 2.20s
> cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/worker-store.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

···························

 Test Files  2 passed (2)
      Tests  27 passed (27)
   Start at  17:33:25
   Duration  853ms (transform 294ms, setup 0ms, import 505ms, tests 139ms, environment 0ms)
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_e2e.py -q
3 passed, 8 deselected in 7.49s
> cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
 Test Files  1 passed (1)
      Tests  177 passed (177)
autopilot-gate-presentation.test.ts / autopilot-console.test.ts / autopilot-event-parity.test.ts
 Test Files  3 passed (3)
      Tests  52 passed (52)
>       assert row["origin"] == mw_common.WORKER_ORIGIN_CONDUCTOR
E       AssertionError: assert '' == 'conductor'
test_autopilot_attribution.py:336: AssertionError
FAILED test_autopilot_attribution.py::test_reconcile_orphans_stamps_conductor_origin
1 failed, 12 passed in 0.27s
[RED-A] row_origin_raw='' worker_origin=manual row_belongs_to_k1=False slotsUsed=0 manualRunning=1
[VERIFY] equivalence row=conductor/scratch          key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=manual/keyed               key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=legacy/no-origin/keyed-prefix key=k1 local=True canonical=False equal=False
[VERIFY] equivalence row=legacy/no-origin/scratch   key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=legacy/no-origin/backslash key=k2 local=True  canonical=False equal=False
[VERIFY] equivalence row=unknown-origin             key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=empty-origin               key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=manual/other-key           key=k1 local=True  canonical=False equal=False
[VERIFY] equivalence row=manual/other-key           key=k3 local=True  canonical=False equal=False
>       assert mismatches == [], mismatches
FAILED test_autopilot_attribution.py::test_row_belongs_to_delegates_to_canonical_predicate
1 failed, 12 passed in 0.27s
 FAIL  test/suite/autopilot-monitor.test.ts > autopilot progress section (AC-006/AC-007) > T-16/AC-021: slot ownership uses origin+path, not the ap- prefix
AssertionError: expected 1 to be +0 // Object.is equality
- Expected
+ Received
- 0
+ 1
...
      Tests  1 failed | 20 passed (21)
[VERIFY] T-16: delegate=single_canonical origin_stamp=conductor.py:4335 row_belongs_to=delegates:2372 monitor=workerBelongsToKey/workerOwnerKey:618,624-627 equivalence=30/30 mismatches=0 counterfactual_a=red(slotsUsed 0 vs 1) counterfactual_b=red(9/30 mismatch) counterfactual_c=red(1 vs 0) verify=13+54+27 green
```

</details>
### T-17: TS 计数锁刷新（T-11 协调缺口修补）
- 回执: `workers\msc-t17-ts-count-locks\report.md`
- AC: AC-018, AC-026 · VC: VC-011, VC-024

**回执中的 [VERIFY] 行（逐字）**

- `## 4. [VERIFY] — raw output`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts
FAIL ... > AC-006/AC-012: the 13-key mirror registers xkey_verify_cwd as a string ...
AssertionError: expected [ 'enabled', 'paused', …(12) ] to have a length of 13 but got 14   (:870)
FAIL ... > AC-025: /autopilot enable writes config ...
AssertionError: expected { enabled: true, paused: false, …(12) } to deeply equal { ... }      (:1181)
+   "auto_gate_mode": "off"
 Test Files  1 failed (1)
      Tests  2 failed | 35 passed (37)
-	it("AC-006/AC-012: the 13-key mirror registers xkey_verify_cwd as a string and exports the registries", () => {
-		expect(Object.keys(DEFAULT_CONFIG)).toHaveLength(13);
-		expect(Object.keys(DEFAULT_CONFIG).at(-1)).toBe("xkey_verify_cwd"); // config.py DEFAULT_CONFIG order
+	it("AC-006/AC-012: the 14-key mirror registers auto_gate_mode last and exports the registries", () => {
+		// Count changed 13 -> 14 in mw-autopilot-slot-capacity (T-03 added auto_gate_mode).
+		expect(Object.keys(DEFAULT_CONFIG)).toHaveLength(14);
+		// Count changed 13 -> 14 in mw-autopilot-slot-capacity (T-03 added auto_gate_mode).
+		expect(Object.keys(DEFAULT_CONFIG).at(-1)).toBe("auto_gate_mode"); // config.py DEFAULT_CONFIG order
@@  /autopilot enable
 			const enabled = JSON.parse(fs.readFileSync(configFile, "utf8"));
+			// Count changed 13 -> 14 in mw-autopilot-slot-capacity (T-03 added auto_gate_mode).
 			expect(enabled).toEqual({
 				...
 				xkey_verify_cwd: "",
+				auto_gate_mode: "off",
 			});
-			expect(Object.keys(enabled)).toHaveLength(13);
+			// Count changed 13 -> 14 in mw-autopilot-slot-capacity (T-03 added auto_gate_mode).
+			expect(Object.keys(enabled)).toHaveLength(14);
// T-17 negative lock, mirroring T-15's Python
// test_machine_layer_effective_keys_stay_two_and_exclude_auto_gate_mode:
// the TS mirror has no `EFFECTIVE_KEYS` export (readConfig is merge-on-read;
// the machine layer is Python-only -- T-11 report section 1), so the closest
// analogue is the xkey registry pair = the Python machine-overridable set
// (EFFECTIVE_KEYS == xkey_verify_cmd + xkey_verify_cwd). It must stay exactly
// those two keys and never gain auto_gate_mode (project-layer only, D-010).
const tsMachineOverridable = [...LIST_FIELDS, ...STR_FIELDS];
expect(tsMachineOverridable).toEqual(["xkey_verify_cmd", "xkey_verify_cwd"]);
expect(tsMachineOverridable).toHaveLength(2);
expect(tsMachineOverridable).not.toContain("auto_gate_mode");
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·····································

 Test Files  1 passed (1)
      Tests  37 passed (37)
   Start at  17:23:50
   Duration  960ms (transform 261ms, setup 444ms, tests 403ms, environment 0ms)
 FAIL  test/suite/autopilot-console.test.ts > ... > AC-006/AC-012: the 14-key mirror ...
AssertionError: expected [ 'enabled', 'paused', …(12) ] to have a length of 15 but got 14
- Expected
+ Received
- 15
+ 14
 ❯ test/suite/autopilot-console.test.ts:871:39
    871|  expect(Object.keys(DEFAULT_CONFIG)).toHaveLength(15);
 Test Files  1 failed (1)
      Tests  1 failed | 36 passed (37)
 FAIL  test/suite/autopilot-console.test.ts > ... > AC-006/AC-012: the 14-key mirror ...
AssertionError: expected [ 'xkey_verify_cmd', …(2) ] to deeply equal [ Array(2) ]
- Expected
+ Received
  [
    "xkey_verify_cmd",
    "xkey_verify_cwd",
+   "auto_gate_mode",
  ]
 ❯ test/suite/autopilot-console.test.ts:882:32
    882|  expect(tsMachineOverridable).toEqual(["xkey_verify_cmd", "xkey_verify_cwd"]);
 Test Files  1 failed (1)
      Tests  1 failed | 36 passed (37)
```

</details>
### T-18: 时效默认字段的旁路创建点修补（T-08 遗留）
- 回执: `workers\msc-t18-gate-default-bypass\report.md`
- AC: AC-019 · VC: VC-024

**回执中的 [VERIFY] 行（逐字）**

- `Status: **complete**. Both `[VERIFY]` suites green, both counterfactuals actually run`
- `## 4. `[VERIFY]` raw output`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
def _stamp_gate_defaults(
    path: pathlib.Path, machine_fields: dict[str, str] | None = None
) -> None:
    """Write the time-effectiveness defaults into a freshly created gate file.

    Thin shared helper so the default-value logic lives in exactly one place:
    both production creation sites — :func:`_create_gate` (the choke point) and
    the goal-change site in :func:`tick` — call it. It MUST run before
    :func:`snapshot_gate_created`; stamping after the snapshot changes the
    bytes and breaks T-06's `gate_file.sha256` replay binding. Caller
    ``machine_fields`` win over the defaults."""
    fields = _gate_default_fields(path)
    if machine_fields:
        fields.update({k: str(v) for k, v in machine_fields.items()})
    if fields:
        _rewrite_gate_fields(path, fields)
        path = gates.create(
            gates_dir(project_root), kind, question,
            context_refs=list(refs), stage=stage, key=key,
        )
        _stamp_gate_defaults(path, machine_fields)
        # T-07: the `created` evidence snapshot is taken here, inside the gates
        # lock (T-06 delivery item 2). No-op when auto_gate_mode is off.
        snapshot_gate_created(project_root, path)
                    goal_gate = gates.create(
                        gates_dir(project_root),
                        "goal-change",
                        "goal.md changed while autopilot is active — review the "
                        "new goal and approve resuming, or reject to stay halted.",
                        context_refs=[str(goal_path(project_root))],
                    )
                    # T-18: this site creates the gate directly (not through
                    # `_create_gate`), so it must stamp the time-effectiveness
                    # defaults itself — and BEFORE the `created` snapshot, or
                    # the T-06 `gate_file.sha256` replay binding breaks. The
                    # goal-change gate is a POLICY face (never auto-answered),
                    # so no predicate outcome exists yet; the site declares the
                    # creation trigger as its fact-plane `reason_code`.
                    _stamp_gate_defaults(
                        goal_gate, {"reason_code": "goal-md-mtime-moved"}
                    )
                    snapshot_gate_created(project_root, goal_gate)
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q
.................                                                        [100%]
17 passed in 1.39s
cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py test_autopilot_gate_guards.py test_autopilot_closure.py -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
70 passed, 52 warnings in 18.67s
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_gate_schema_v2.py -q -p no:warnings
55 passed in 1.42s
tick=halted-goal-change
kind=goal-change
expires_at=None
default_action=None
missing_fields=['reason_code', 'expires_at', 'default_action']
doctor missing_fields=[{'id': 'gate-0001', 'fields': ['reason_code', 'expires_at', 'default_action']}]
healthy=False
issues=['gate gate-0001 (goal-change, scope=none) pending since 2026-09-26T09:55:40+00:00 with no expires_at/default_action - set the default action or answer the gate (AC-019: no implicit permanent retention)']
gates_text_line=True
tick=halted-goal-change
kind=goal-change
expires_at=2026-09-28T09:55:45+00:00
default_action=escalate-to-human
missing_fields=[]
doctor missing_fields=[]
healthy=True
issues=[]
gates_text_line=False
=== BEFORE pytest ===
F.                                                                       [100%]
================================== FAILURES ==================================
__________ test_goal_change_gate_carries_time_effectiveness_defaults __________
...
    assert gate.kind == "goal-change"
>   assert gate.default_action == "escalate-to-human"
E   AssertionError: assert None == 'escalate-to-human'
E    +  where None = Gate(id='gate-0001', kind='goal-change', ...,
E    default_action=None, ...)
test_autopilot_pending_review.py:625: AssertionError
=========================== short test summary info ===========================
FAILED test_autopilot_pending_review.py::test_goal_change_gate_carries_time_effectiveness_defaults
1 failed, 1 passed, 15 deselected in 0.17s
recorded_sha=69295a581d29c366a6d57876e7092faaa4582be23f026e775fbb12e036f9157d
current_sha =a08742c2e3dd4319696005fe949c588a069ba583a064647e2fa5226ac04f89b0
sha_match=False
binding=unbound
drift=False
refusal=replay-misbound
E       AssertionError: assert '7e3ae561908e...a6377c85f3161' == '3d24eb12db32...54edc1417cebc'
FAILED test_autopilot_pending_review.py::test_goal_change_defaults_are_written_before_the_created_snapshot
1 failed, 16 deselected in 0.24s
recorded_sha=bd838713150757ef15ce8601f3c0a44839e330c8692c19a524017304fe59521e
current_sha =bd838713150757ef15ce8601f3c0a44839e330c8692c19a524017304fe59521e
sha_match=True
binding=bound
drift=False
refusal=None
```

</details>
### T-19: case 2 生产者接线（本 key 主交付的最后一块）
- 回执: `workers\msc-t19-case2-producer\report.md`
- AC: AC-027, AC-028 · VC: VC-039, VC-043

**回执中的 [VERIFY] 行（逐字）**

- `Status: **DONE** — all `[VERIFY]` green, all three counterfactuals demonstrably`
- `## 3. `[VERIFY]` raw output`
- `T-19 `[VERIFY]` lines (`-s`):`
- `[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`
- `[VERIFY] T-19: irreversible_kinds=4 xkey_status=stalled escalate_record=1`
- `[VERIFY] T-19: off_bytes_identical=true key_status_line=> key-status: k1=stalled, k2=done`
- `[VERIFY] T-19: in_flight_skips_deferral=true key_status=stalled`
- `Raw assertion result (see `[VERIFY]` line above):`
- `[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
# Case-2 producer allowlist (T-19 / AC-027), frozen from design §2's three-way
# decision tree: "E(机器不能应答) --> 挡不可逆推进? 是 --> 当场人审 不给延后;
# 否 --> case 2 待复核 pending-review". `stalled` / `budget-exhausted` are
# recoverable and block no irreversible action, so a declined auto-decision may
# park them in `pending-review`. `stage-confirm`/`stage-close` gate an
# irreversible stage transition and `goal-change`/`xkey-authorize` are policy
# authorisations: they are NEVER deferred and stay case 3 = immediate review.
# Same frozen value as `_REVIEW_GATE_KINDS` above, but the answer side (T-08)
# and the deferral side (T-19) are separate contracts and evolve separately.
DEFERRABLE_GATE_KINDS = ("stalled", "budget-exhausted")
    if decision is None:
        # Guard passed: necessary, not sufficient. A deferrable kind is still a
        # case-2 candidate (design section 2: the machine cannot answer -> 待复核).
        _defer_declined_gate(project_root, st, gate, mode)
        return
    if decision == "escalate":
        # Decline path (proposition false / extra reason failed / tautology /
        # rule not auto-executable). A deferrable kind becomes case 2 here; the
        # deferral IS the disposition, so no `gate-auto-decision` row is
        # written. Every other kind (and an in-flight/deferred-unavailable key)
        # stays case 3 and falls through to the existing escalate record.
        if _defer_declined_gate(project_root, st, gate, mode):
            return
        if _escalate_recorded(rows, gate.id, reason_code):
            return  # dedup: one escalate record per (gate, reason)
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q
.....................                                                    [100%]
21 passed in 1.48s
$ cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_closure.py test_autopilot_conductor.py -q
........................................................................ [ 83%]
..............                                                           [100%]
86 passed in 1.74s
[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
[VERIFY] T-19: irreversible_kinds=4 xkey_status=stalled escalate_record=1
[VERIFY] T-19: off_bytes_identical=true key_status_line=> key-status: k1=stalled, k2=done
[VERIFY] T-19: in_flight_skips_deferral=true key_status=stalled
4 passed, 17 deselected in 0.16s
[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
def test_case2_producer_makes_pending_review_reachable_end_to_end(...):
    ...
    # step 1: one auto-decision pass is enough to park the key
    conductor.auto_decide_gates(project, st, cfg)
>   assert _key_status(project, "k1") == "pending-review"
E   AssertionError: assert 'stalled' == 'pending-review'
E     - pending-review
E     + stalled
test_autopilot_pending_review.py:741: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_pending_review.py::test_case2_producer_makes_pending_review_reachable_end_to_end
1 failed, 20 deselected in 0.28s
CF-A key-status: {'k1': 'stalled', 'k2': 'done'}
CF-A gate status: pending
CF-A pending-review events: []
CF-A review-escalated events: []
CF-A gate-auto-decision events: ['gate-auto-decision']   # the old case-3 escalate
>   assert tuple(conductor.DEFERRABLE_GATE_KINDS) == ("stalled", "budget-exhausted")
E   AssertionError: assert ('stalled', '...'stage-close') == ('stalled', '...et-exhausted')
E     Left contains one more item: 'stage-close'
test_autopilot_pending_review.py:788: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_pending_review.py::test_irreversible_and_policy_gate_kinds_are_never_deferred
1 failed, 20 deselected in 0.23s
CF-C before sha256: 88917e22b45b8e82ef1412c3645f46a414b11292ae93d0724d287c00aed91d9b
CF-C after  sha256: 88917e22b45b8e82ef1412c3645f46a414b11292ae93d0724d287c00aed91d9b
CF-C byte-identical: True
CF-C before line: > key-status: k1=stalled, k2=done
CF-C after  line: > key-status: k1=stalled, k2=done
CF-C k1 status: stalled
```

</details>
### T-20: `reason_code` 必需集按 kind 收敛 + 冻结闭集写入护栏（T-13/T-18 契约冲突）
- 回执: `workers\msc-t20-reason-code-scope\report.md`
- AC: AC-019, AC-026 · VC: VC-024

**回执中的 [VERIFY] 行（逐字）**

- ``[VERIFY]` markers emitted by the new cases: `VC-024` (per-kind missing_fields=0,`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
### cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py -q
................................                                         [100%]
32 passed in 21.25s
### cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py test_autopilot_auto_decision.py test_autopilot_conductor.py -q
........................................................................ [ 93%]
.....                                                                    [100%]
77 passed in 6.47s
### python -X utf8 -m pytest test_autopilot_gate_schema_v2.py test_autopilot_gate_guards.py \
      test_autopilot_gates.py test_autopilot_gate_consumption.py test_serve_doctor.py \
      test_autopilot_audit.py test_mw_autopilot_cli.py -q
138 passed in 12.34s
stage-confirm      missing=['reason_code']              reason_code=None                   healthy=True gates_line=True
stage-close        missing=['reason_code']              reason_code=None                   healthy=True gates_line=True
stalled            missing=[]                           reason_code='l2-budget-rejected'   healthy=True gates_line=False
budget-exhausted   missing=['reason_code']              reason_code=None                   healthy=True gates_line=True
goal-change        missing=[]                           reason_code='goal-md-mtime-moved'  healthy=True gates_line=False
xkey-authorize     missing=['reason_code']              reason_code=None                   healthy=True gates_line=True
stage-confirm      missing=[]                           reason_code=None                   healthy=True gates_line=False
stage-close        missing=[]                           reason_code=None                   healthy=True gates_line=False
stalled            missing=[]                           reason_code='l2-budget-rejected'   healthy=True gates_line=False
budget-exhausted   missing=[]                           reason_code=None                   healthy=True gates_line=False
goal-change        missing=[]                           reason_code=None                   healthy=True gates_line=False
xkey-authorize     missing=[]                           reason_code=None                   healthy=True gates_line=False
raw gates.create() WITHOUT defaults write-back:
  stage-confirm      missing=['expires_at', 'default_action']                     healthy=False
  stage-close        missing=['expires_at', 'default_action']                     healthy=False
  stalled            missing=['expires_at', 'default_action', 'reason_code']      healthy=False
  budget-exhausted   missing=['expires_at', 'default_action']                     healthy=False
  goal-change        missing=['expires_at', 'default_action']                     healthy=False
  xkey-authorize     missing=['expires_at', 'default_action']                     healthy=False
$ python -X utf8 -m pytest \
    test_doctor_gates.py::test_reason_code_not_required_for_human_decision_kinds \
    test_autopilot_pending_review.py::test_reason_code_requirement_is_per_kind -q
E       AssertionError: [{'fields': ['reason_code'], 'id': 'gate-0001'}, {'fields': ['reason_code'], 'id': 'gate-0002'},
 {'fields': ['reason_code'], 'id': 'gate-0003'}, {'fields': ['reason_code'], 'id': 'gate-0004'}, {'fields': ['reason_code'], 'id': 'gate-0005'}]
E       assert [{'fields': [... 'gate-0005'}] == []
test_doctor_gates.py:432: AssertionError
E           AssertionError: ('stage-confirm', WindowsPath('.../stage-confirm/.agenticdoc/_autopilot/gates/gate-0001.md'))
E           assert ['reason_code'] == []
test_autopilot_pending_review.py:700: AssertionError
=========================== short test summary info ===========================
FAILED test_doctor_gates.py::test_reason_code_not_required_for_human_decision_kinds
FAILED test_autopilot_pending_review.py::test_reason_code_requirement_is_per_kind
2 failed in 0.75s
file=...\proj\.agenticdoc\_autopilot\gates\gate-0001.md
parsed reason_code='goal-md-mtime-moved'
in REASON_CODES=False
frontmatter reason_code line: reason_code: goal-md-mtime-moved
E       assert "goal-md-mtime-moved" not in text
E         'goal-md-mtime-moved' is contained here:
E           son_code: goal-md-mtime-moved
test_autopilot_pending_review.py:732: AssertionError
FAILED test_autopilot_pending_review.py::test_illegal_reason_code_is_dropped_and_logged
1 failed in 0.15s
```

</details>
### T-21: 延后处置必须留台账行（影子与实动共用），修正影子期的失真
- 回执: `workers\msc-t21-defer-ledger\report.md`
- AC: AC-027, AC-028 · VC: VC-039, VC-043

**回执中的 [VERIFY] 行（逐字）**

- `- 影子门槛：`shadow_prerequisites` 计 `mode=="shadow" and phase=="decide"`。影子延后行计入（见 §6 的 `[VERIFY] T-21` 计数 0→1），且 `prop_ok=False` 使其同时作为该 rule 的反例见证。`
- `新增用例的 `[VERIFY]`（`pytest -q -s -k t21`）：`
- `[VERIFY] T-21: shadow_row=defer/executed=false/mode=shadow gate_sha256_unchanged=true roadmap_sha256_unchanged=true decision_rows=1`
- `[VERIFY] T-21: live_row=defer/executed=true/mode=live key_status=pending-review escalate_rows=0 decision_rows=1`
- `[VERIFY] T-21: shadow_decisions_before=0 shadow_decisions_after=1 nights_before=0 nights_after=0`
- `[VERIFY] T-21: stage_close=escalate defer_rows=0 decision_rows=1`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
shadow: {"decision": "defer", "executed": false, "mode": "shadow", "reason_code": "stalled-reason-drift"}
live:   {"decision": "defer", "executed": true, "mode": "live", "reason_code": "stalled-reason-drift"}
shadow: {"decision": "escalate", "executed": false, "mode": "shadow", "reason_code": "stalled-reason-drift"}
live:   {"decision": "defer", "executed": true, "mode": "live", "reason_code": "stalled-reason-drift"}
before: night_used=0 key_used=0 executed_rows=0
after:  night_used=1 key_used=1 executed_rows=1
tick2:  night_used=1 key_used=1 executed_rows=1
defer row: executed=True night=2026-09-25 decision=defer escalate_rows=0
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q
...........................                                              [100%]
27 passed in 4.80s

cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_conductor.py -q
......................................................                   [100%]
54 passed in 1.64s
[VERIFY] T-21: shadow_row=defer/executed=false/mode=shadow gate_sha256_unchanged=true roadmap_sha256_unchanged=true decision_rows=1
[VERIFY] T-21: live_row=defer/executed=true/mode=live key_status=pending-review escalate_rows=0 decision_rows=1
[VERIFY] T-21: shadow_decisions_before=0 shadow_decisions_after=1 nights_before=0 nights_after=0
[VERIFY] T-21: stage_close=escalate defer_rows=0 decision_rows=1
4 passed, 23 deselected in 0.12s
python -X utf8 -m pytest test_autopilot_e2e.py test_autopilot_closure.py test_autopilot_stall.py \
  test_autopilot_gate_guards.py test_autopilot_gate_consumption.py test_autopilot_attribution.py test_autopilot_audit.py -q
87 passed, 8 deselected in 7.68s
$ python -X utf8 -m pytest test_autopilot_pending_review.py -q -k t21_shadow_deferral_records_one_row
>       assert (row["decision"], row["executed"], row["mode"]) == (
            "defer", False, "shadow"
        )
E       AssertionError: assert ('escalate', False, 'shadow') == ('defer', False, 'shadow')
E         At index 0 diff: 'escalate' != 'defer'
FAILED test_autopilot_pending_review.py::test_t21_shadow_deferral_records_one_row_with_zero_state_change
1 failed, 26 deselected in 0.17s
shadow: {"decision": "escalate", "executed": false, "mode": "shadow", "reason_code": "stalled-reason-drift"}
live:   {"decision": "defer", "executed": true, "mode": "live", "reason_code": "stalled-reason-drift"}
>       rows = _gate_rows(project, gate.id)
>       assert len(rows) == 1, rows
E       AssertionError: []
E       assert 0 == 1
FAILED test_autopilot_pending_review.py::test_t21_live_deferral_records_executed_row_and_no_escalate
1 failed, 26 deselected in 0.24s
>       assert _sha256_file(rm_path) == roadmap_sha, "shadow must not touch the roadmap"
E       AssertionError: shadow must not touch the roadmap
E       assert '06eb7347fecb...ea6c6c4996352' == 'db9b0336afc4...264c124f9e84b'
FAILED test_autopilot_pending_review.py::test_t21_shadow_deferral_records_one_row_with_zero_state_change
1 failed, 26 deselected in 0.25s
```

</details>
### T-22: 证据行陈旧性审计（`[VERIFY]` 数值不得是硬编码字面量）
- 回执: `workers\msc-t22-evidence-line-audit\report.md`
- AC: AC-019, AC-027 · VC: VC-024, VC-039, VC-043

**回执中的 [VERIFY] 行（逐字）**

- `# T-22 receipt — `[VERIFY]` evidence-line freshness audit`
- `.[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`
- `.[VERIFY] T-19: step1=pending-review gate=pending defer_rows=1 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`
- `[VERIFY] T-19: step1=pending-review gate=pending defer_rows=2 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`
- `(`[VERIFY]` lines require `-s`; the full `-q -s` corpus was captured and`
- `[VERIFY] T-19: step1=pending-review gate=pending defer_rows=1 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0`
- `| doctor_gates.py:666-684 | (VC-007/014/024/049) | — | not `_verify` | out of scope: `test_verify_marker` uses direct `print("[VERIFY] ...")` prose, no `k=v` numeric judgement |`
- `| attribution.py:381 | (equivalence loop) | — | measured | direct `print("[VERIFY] equivalence ...")` already computes `local`/`canonical`/`equal` from the predicate |`
- `The before/after `[VERIFY]` corpus diff shows only 4 changed lines. Besides the`
- `Python suites named in `[VERIFY]` were executed.`

<details><summary>回执原始输出片段（自动汇集，未改写）</summary>

```text
.[VERIFY] T-19: step1=pending-review gate=pending auto_decision_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
.[VERIFY] T-19: step1=pending-review gate=pending defer_rows=1 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
    ledger_rows = conductor.auto_decision_rows(project)
    step3_status = _key_status(project, "k1")
    _verify(
        "T-19",
        step1=step1_status,
        gate=gate.status,
        defer_rows=sum(
            1 for row in ledger_rows if row.get("decision") == "defer"
        ),
        escalate_rows=sum(
            1 for row in ledger_rows if row.get("decision") == "escalate"
        ),
        step2="review-escalated{closure}",
        stage_close=stage_close_at_step2,
        step3=step3_status,
        done_exit=int(step3_status in ("done", "closed-legacy")),
    )
[VERIFY] T-19: step1=pending-review gate=pending defer_rows=2 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
1 passed in 0.15s
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py test_autopilot_auto_decision.py test_doctor_gates.py test_autopilot_attribution.py -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
98 passed, 56 warnings in 25.35s
[VERIFY] T-19: step1=pending-review gate=pending defer_rows=1 escalate_rows=0 step2=review-escalated{closure} stage_close=0 step3=running done_exit=0
1 passed in 0.15s
```

</details>
