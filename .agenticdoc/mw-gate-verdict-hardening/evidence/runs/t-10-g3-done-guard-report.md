# T-10 report: G3 done 前机械检查 + 字段物化 + 提示词硬约束

- Key: `mw-gate-verdict-hardening`（phase=EXECUTE）
- Card: `.agenticdoc/mw-gate-verdict-hardening/tasks/T-10-g3-done-guard.md`
- Worker task: `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t10-g3-done-guard/task.md`
- Baseline HEAD: `776b82d7f`
- 开工时写面快照：`git status --porcelain -- packages/multi-workers/autopilot/conductor.py` -> ` M packages/multi-workers/autopilot/conductor.py`（T-01 + T-07 的未提交改动在内，未回退；本次为串行链第三段）
- AC: AC-010 / AC-011 / AC-012 / AC-013 · VC: VC-013 / VC-014 / VC-015 / VC-016
- Result: **PASS**（两条 `[VERIFY]` 只剩 T-14 认领的 2 个 `== 12` 计数锁红；新增 16 测试全绿；3 组非空洞对照全部按预期转红并已逐字节还原）

## 1. 交付物（符号 + 当前实际行号）

### 1.1 done 前 fail-closed 检查（AC-011 / VC-014）

`_done_transaction`（`autopilot/conductor.py:2221`）：在 DONE-resume 早退之后、任何写盘（`try:` `:2268`）之前，调 T-04 的 `contract_guard.evaluate`：

| 坐标 | 内容 |
|---|---|
| `conductor.py:2244-2246` | `contract_guard.evaluate(key_dir, gates_dir(project_root), key=key)`（不重写判定，直接复用 T-04） |
| `conductor.py:2247-2260` | 不通过 ⇒ `timeline.append("contract-refused", data={changed_ids, freeze_rel, carrier})` |
| `conductor.py:2261-2266` | `mark_stalled(..., reason_code="contract-unauthorized")`（无 loop 标签 ⇒ 走 `_stall_family` 的 G3 分支） |
| `conductor.py:2267` | `return "gated", ""` ⇒ 不写 QG / achieved / pm-state / 不调 advance |
| `conductor.py:2229-2238` | docstring 记录「FIRST check-before-write」语义 |

无 freeze sidecar ⇒ `evaluate` 返回 `ok=True, no_anchor=True` ⇒ 守卫为 no-op（AC-013 零扰动）。

### 1.2 字段物化（AC-009 半边，不碰 `gates.create()`）

- `_gate_default_fields`（`conductor.py:2836`）：`conductor.py:2849` 默认字段集变为 `{"default_action": ..., "authorizes": "[]"}`；docstring `:2846-2848` 说明物化理由（`gates.create()` 13 键输出冻结，人应答时填值）。
- `_stamp_gate_defaults`（`conductor.py:2782`）经该 helper 写入，无需额外改动；两个生产建门点（`_create_gate` `:2721` 附近、`tick` goal-change `:2616` 附近）自动覆盖。
- `gates.create()` 零改动（13 键锁保持；`test_autopilot_gates.py` 全绿）。

### 1.3 提示词逐字硬约束（AC-010 / VC-013）

- 单一模块常量 `_CONTRACT_CONSTRAINT`（`conductor.py:1459`），独立于 `contract_guard.py` 的字符串。
- 三处末尾行拼接（同一条常量、逐字相同）：
  - `_repair_prompt`（`conductor.py:1466`）-> 追加于 `:1478-1479`
  - `_phase_writer_prompt`（`conductor.py:2454`）-> `:2459-2460`
  - `_fix_writer_prompt`（`conductor.py:2476`）-> `:2490-2491`

### 1.4 reason_code 闭集 + 复算一致性

- `STALL_REASON_CODES`（`conductor.py:5178`）新增 `"contract-unauthorized"`（`:5192`），13 -> 14。
- `_stall_family`（`conductor.py:5577`）：无 loop 且 `reason_code == "contract-unauthorized"` ⇒ 归 `"l3"`（`:5595`），复算经 `_recompute_l3_stall_code` 收口，避免 `stalled-reason-drift`。
- `_recompute_l3_stall_code`（`conductor.py:5645`）：`:5654-5658` 独立复算 G3——重跑 `contract_guard.evaluate`，仍拒 ⇒ `contract-unauthorized`，否则 `advance-class`。

写面纪律：`conductor.py`（上述四段）+ 新建测试文件 `packages/multi-workers/test_autopilot_done_contract_guard.py`。未改 L3 判据（T-01）与 `tick` 段（T-07），未改 `gates.py` / `contract_guard.py`（T-04 写面），未 commit，未 `git add -A`。

## 2. `[VERIFY]`（命令原文 + 真实输出）

### 2.1

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_guard.py test_autopilot_conductor.py test_autopilot_auto_decision.py -q -p no:randomly
..................................................FF.................    [100%]
================================== FAILURES ===================================
____________________ test_reason_code_closed_set_is_closed ____________________
>       assert len(conductor.STALL_REASON_CODES) == 12
E       AssertionError: assert 14 == 12
test_autopilot_auto_decision.py:301: AssertionError
_________ test_all_twelve_mark_stalled_call_sites_pass_a_reason_code __________
>       assert len(calls) == 12, f"expected 12 call sites, found {len(calls)}"
E       AssertionError: expected 12 call sites, found 14
test_autopilot_auto_decision.py:333: AssertionError
=========================== short test summary info ===========================
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code
2 failed, 67 passed in 1.86s
```

只有 `:301` 与 `:333` 的 `== 12` 计数锁红（**归 T-14**）。`test_autopilot_auto_decision.py:335/338`（"调用点都带 code" + 集合相等）**保持绿**，实测：

```
> cd packages/multi-workers && python -X utf8 .tmp/t10_check_codes.py   # 临时脚本，已删除
call_sites 14
missing_reason_code []
codes_subset True
codes_equal True
extra []
missing_codes []
assertion_335_338_green True
```

即 14 个 `mark_stalled` 调用点全部带 `reason_code=`，且源码内码集合与 `STALL_REASON_CODES` 完全相等。T-14 只需把 `:301`/`:333` 的 `== 12` 改成 `== 14`。

### 2.2

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_closure.py -q -p no:randomly
................................                                         [100%]
32 passed in 0.10s
```

### 2.3 新增测试（本卡交付的 G3 夹具，16 项）

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_done_contract_guard.py -q -p no:randomly -s
[VERIFY] VC-013: prompts=3 verbatim=true
[VERIFY] VC-014: refused=true changed_ids=1 classified=true
[VERIFY] VC-014-carrier: authorized=true carrier=gate-0001
[VERIFY] VC-015: gate=gate-0001 authorized=false
[VERIFY] VC-015: gate=gate-0002 authorized=false
[VERIFY] VC-015: gate=gate-0003 authorized=false
[VERIFY] VC-015: gate=gate-0004 authorized=false
[VERIFY] VC-015: gate=gate-0005 authorized=false
[VERIFY] VC-015: gate=gate-0014-shape authorized=false
[VERIFY] VC-016: freeze=absent refused=false
[VERIFY] VC-016-materialize: stamped_authorizes=[] create_keys=13
16 passed in 0.24s
```

`[VERIFY]` 行数值全部来自夹具实测（`test_autopilot_done_contract_guard.py`）：

| 断言 | 测试名 |
|---|---|
| `contract-refused` 事件 `data.changed_ids==["AC-001"]`、`freeze_rel`、`carrier is None`；无 QG/pm-state/l3-verdict；advance 未调 | `test_vc014_done_refused_without_approval_and_classified` |
| `authorizes:["contract-change"]` 的 approved 门 ⇒ `advanced`、advance 调 1 次 | `test_vc014_approved_authorizing_gate_allows_done` |
| pending / rejected / 越 key / `["retry"]` / 散文 note ⇒ `gated` | `test_vc015_no_non_machine_or_non_scoped_record_authorizes_done`（5 参数化例） |
| E2 真实 `gate-0014` note 形状（含"属可修范围"，无 `authorizes`）⇒ `gated` | `test_vc015_e2feature_gate_0014_shape_is_not_an_authorization` |
| 无 freeze ⇒ `advanced`、无事件、无 stall gate | `test_ac013_no_freeze_is_a_noop_for_the_done_transaction` |
| 有 freeze + 文本未变 ⇒ `advanced` | `test_ac013_done_refused_does_not_fire_when_frozen_text_is_unchanged` |
| `_create_gate` 产物 `authorizes==[]` 且原文含 `\nauthorizes: []\n`；`gates.create()` 仍 13 键 | `test_new_gate_materializes_an_empty_authorizes_field` |
| `_gate_default_fields` 含 `authorizes=="[]"` | `test_gate_default_fields_includes_authorizes` |
| `STALL_REASON_CODES` 14 项且含 `contract-unauthorized` | `test_contract_unauthorized_is_in_the_reason_code_closed_set` |
| 拒后 roadmap key_status 落 `stalled` | `test_stalled_gate_lookup_and_roadmap_round_trip` |

真实反例夹具：`H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0014.md` 本机可访问，已逐字引用其 `note`（kind=stalled / status=approved / answered_by=wenbozhou / 无 `authorizes`）；夹具形状按该文件裁剪，未入仓。

### 2.4 邻域回归（bound blast radius）

```
> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gates.py test_autopilot_gate_schema_v2.py test_autopilot_pending_review.py test_autopilot_gate_consumption.py test_autopilot_gate_guards.py test_autopilot_verdict_provenance_guard.py test_autopilot_verdict_source_fallback.py -q -p no:randomly
139 passed in 13.72s

> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor_exec.py test_autopilot_l3_aborted.py test_autopilot_stall.py test_autopilot_gate_reminder.py test_autopilot_evidence.py test_autopilot_audit.py test_autopilot_attribution.py test_autopilot_docs.py -q -p no:randomly
127 passed in 4.27s
```

更宽一轮（15 个文件）257 passed / 4 failed，4 个失败**全部与本卡写面无关**、且是并行会话在飞：

| 失败 | 归因 |
|---|---|
| `test_autopilot_timeline.py::test_append_line_schema_all_event_types` | `timeline.py` 事件集计数（T-03 预登记 3 新事件，T-14 收口） |
| `test_autopilot_config_parity.py::test_p6_partial_single_key` | `config.py` 17 -> 20 键（T-02/T-18，T-14 收口） |
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | `autopilot/dispatch.py` 被并行卡改动（git blob 失配），非本卡文件 |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | 只读外部 `H:\git\E2Feature` 真实数据变动（latest report 非末轮），非本卡 |

`git status --porcelain -- packages/multi-workers/` 证实 `config.py`/`dispatch.py`/`timeline.py`/`gates.py`/`mw_common.py`/`launcher.py` 均有**其它会话**未提交改动。未运行 `npm run check`（`biome check --write .` 会写其它会话的 TS 文件；且本卡只动 Python，卡片硬规则 3 限定 Python 只用 pytest）。

## 3. 非空洞对照（真跑红/绿，已逐字节还原）

还原校验：CF 前后 `sha256(conductor.py)=560fea6a0226fa7306910ff2ec68d8f2549740ea845409e07d475f69dfe2943c`、`sha256(contract_guard.py)=7748469cb55ed184e0df25d137bee1de1a747c7be28cace2ee443dabe0fb3e66` 完全相同。

### CF-1 摘掉 done 前检查 ⇒ VC-014 转红

临时把 `conductor.py:2247` 的 `if not contract.ok:` 改为 `if False:`，跑拒绝对用例：

```
> python -X utf8 -m pytest test_autopilot_done_contract_guard.py::test_vc014_done_refused_without_approval_and_classified -q -p no:randomly
>       assert verdict == "gated" and err == ""
E       AssertionError: assert ('advanced' == 'gated'
1 failed in 0.25s
```

⇒ "AC 文本被改 + 无批准记录"用例**能推进**，判据是本条 fire 的原因。还原后该文件 16 passed。

### CF-2 放宽批准记录判据（接受 pending/散文 note）⇒ VC-015 转红

临时把 `contract_guard.authorizing_gates` 的 `status=="approved"` 去掉并把 `gate.note` 当授权源：

```
> python -X utf8 -m pytest test_autopilot_done_contract_guard.py -q -p no:randomly
FAILED test_autopilot_done_contract_guard.py::test_vc014_done_refused_without_approval_and_classified
FAILED test_autopilot_done_contract_guard.py::test_vc015_no_non_machine_or_non_scoped_record_authorizes_done[gate-0001-pending-k1-authorizes0-None]
FAILED test_autopilot_done_contract_guard.py::test_vc015_no_non_machine_or_non_scoped_record_authorizes_done[gate-0002-rejected-k1-authorizes1-None]
FAILED test_autopilot_done_contract_guard.py::test_vc015_no_non_machine_or_non_scoped_record_authorizes_done[gate-0005-approved-k1-None-contract-change \u5c5e\u53ef\u4fee\u8303\u56f4]
4 failed, 11 passed in 0.41s
```

（越 key 的 gate-0003 与只含 `["retry"]` 的 gate-0004 仍绿 —— key 作用域与闭集未被放宽。）还原后 `contract_guard.py` sha 不变。

### CF-3 三条 prompt 里删掉一处常量 ⇒ VC-013 转红

临时从 `_fix_writer_prompt` 去掉 `+ _CONTRACT_CONSTRAINT`：

```
> python -X utf8 -m pytest test_autopilot_done_contract_guard.py::test_vc013_three_prompts_carry_the_same_constraint_verbatim -q -p no:randomly
E           AssertionError: fix-writer
E           assert '- 硬约束：不得修改已锁定 AC/VC 的生效文本...' in '补证 key k1 ... 不改动无关 artifact。\n'
1 failed in 0.23s
```

⇒ 三处并非"某处一模一样的另一份手抄"，锁真的读同一常量。还原后 `conductor.py` sha 不变。

## 4. 契约遵守

- 判定不读 `gate.note`/`answered_by`、不解析 design.md 散文：判定全在 `contract_guard.evaluate`/`authorizing_gates`（T-04），本卡只调用。VC-015 含 E2 真实 note 形状用例。
- prompt 常量是 `contract_guard.py` 之外的独立字符串：`test_vc013_constraint_is_a_standalone_literal_outside_contract_guard` 断言该串不在 `contract_guard.py` 源码中。
- 未改 `gates.create()`（13 键）+ `_REQUIRED_FIELDS` 6 格：`test_new_gate_materializes_an_empty_authorizes_field` 复验。
- 零扰动：无 freeze ⇒ 守卫 no-op、无事件、无 stall gate（VC-016 两用例）。
- 未改 L3 判据（T-01）与 `tick` 段（T-07）；`autopilot/gates.py`、`autopilot/contract_guard.py` 最终 sha 与 T-04 交付一致（未留任何 CF 残迹）。
- 未发现 `authorizes` 之外的既有"批准记录"载体（如 `xkey-authorize`）；判定按卡要求不绑 kind，直接消费 T-04 的 `authorizes` 字段，未自创第二种语义。

## 5. 注意事项 / handoff

- `test_autopilot_auto_decision.py:301`（`len(STALL_REASON_CODES)==12`）与 `:333`（`len(calls)==12`）现为 **14**，**按卡留给 T-14** 改；`:335/338` 实测绿。T-01 已把计数从 12 推到 13，本卡推到 14。
- 本卡把 `contract-unauthorized` 的复算挂在 `_recompute_l3_stall_code`（`_stall_family` 无 loop 时归 `"l3"`），以满足卡文"`_recompute_l3_stall_code` 同步"。语义上该分支先于 L3 轮次判定、且只对 `reason_code=="contract-unauthorized"` 的门生效，不影响正常 L3 stall 的复算。
- T-11（CLI/doctor）与 T-12（TS 写侧）仍在使用同一 `contract_guard.evaluate`；本卡未新增 doctor/CLI 面。
- 本次未 commit（按硬规则 1）。
