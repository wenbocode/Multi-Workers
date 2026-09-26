# T-03 conductor 挂载 + config（W3 单写者）

key: `xkey-repair-mechanism` · 依赖: 冻结契约（`autopilot.xkey` 由 T-01 并行实现，**只 import 不重定义**） · 覆盖: VC-002,003,004,007,008,012

## 目标

把 `autopilot/xkey.py` 挂进 tick 控制流 + 扩 config。**不改判定契约**、**不搬逻辑**（判定逻辑属 T-01）。

## 挂载坐标（基线 `6d98c5ee3`，逐条核验后再改，漂移即报告）

| 位置 | 动作 |
|---|---|
| `conductor.py:172` `_consume_answered_gates(project_root, st)` | 在其函数体（`:274` 起）内加 **xkey 消费分支**：`kind == "xkey-authorize"` 且已答 ⇒ 记账（approved → 状态 `approved`；rejected → `rejected`）|
| `conductor.py:211` `_apply_stalled_approvals` / `:214` `_apply_stalled_rejections` | **消费分支必须排在其之前生效**——`_apply_stalled_*` 只认 stalled key（实测 `:2190`/`:2258` 附近），xkey approve 经其无法解冻 key，否则工单永远冻住（design D-010、RQ-D4 Q5）。两处既存冲突须规避：双 pending gate（`_gate_open` 语义）、已 stalled 幂等早退 |
| `conductor.py:214` 与 `:216`（`in_flight_keys = {`）之间 | 插入 `_xkey_aggregate(project_root, st, cfg)` 调用，受 `cfg["xkey_repair"]` 门控；位置理由：在 `_consume_answered_gates` 之后（先折叠已答）、在 `_apply_stalled_*` 之后（用**本 tick 已生效的终态视图**判 owner 终态）、在派发循环 `:224` 之前（新抬 gate 本 tick 可见） |
| `conductor.py:2093` `_gate_open(project_root, kind, *, loop=None, stage=None)` | 扩 **request_id 维度**：同一 `request_id` 只允许一个 pending `xkey-authorize` gate（新参数匹配 `gate.context_refs`，与 `loop` 同机制）。抬 gate 前必须先 `_gate_open(request_id=...)`（gate flood 红线：实测 6684 条/12h） |
| `conductor.py:1113-1127`（`_l3_prompt`，prompt 唯一构造点） | 在"必含两节"要求中追加**一行机器行**要求：`cross_key_test=<path>::<test_id> owner=<key> handoff=registered not_fixed_by_this_key=True`（**必须落在必含节内**，因为 conductor 读的是 deciding source；KV 行现只有 `evidence/runs/**` 有而 conductor 不读该目录——D-001）。**不改** `_l3_qualifies:1207` 判定契约 |
| `conductor.py:1233` `_l3_round_verdict` → `:1267` `_l3_provenance_record`（字段区 `:1294-1305`）→ `:1359` `_persist_l3_provenance` | 解析登记（扫**全部** sources，沿用 `_l3_resolve_source:1215` 的 fail-closed 语义），作**新可选参数**并入 provenance sidecar **新键** `registration`（不新增文件）。三条约束：去重键 `task_key` ⇒ 不可刷新（`:1385-1388`，一次性快照）；仅非 `no-verdict` 轮落盘；跨 key 聚合仍走账本 |
| `autopilot/config.py` + `_autopilot/config.json` | 新键 `xkey_repair`(bool, **默认 false**)、`xkey_verify_cmd`(list[str])、`xkey_verify_timeout_s`(int, 默认 1800)；沿用 `config.py:129-150` 的 `cached_load` mtime+size 语义 |

**幂等/零私有状态**：禁在 `ConductorState` 加内存游标；消费与去重全部从盘重派生（范式 `_consumed_gate_ids`（`:255-272` 附近）、`_resume_credits`）。

## 必须同步的既有测试（改 prompt 措辞会碰）

写侧：`test_reviewer_prompt_documents_fallback`（`:919` 附近）、`test_reviewer_prompt_documents_provenance`（`:556` 附近）、`test_dcr_reprompt_prompt_byte_exact`（`:939` 附近）。

## 最终目标（本卡必须达成的端到端行为）

`xkey_repair=True` 时：below 轮带**完整登记** ⇒ 账本建行 + 生成工单 + 抬 `xkey-authorize` gate（同 request_id 仅一个）；无登记 ⇒ 只写 escalation 记录、零工单（VC-002）。`xkey_repair=False` 时：**零行为变化**（VC-008：既有套件全绿）。

## 验收

- `cd packages/multi-workers && python -m pytest -q test_autopilot_fail_marker_forms.py test_autopilot_verdict_freshness.py test_autopilot_verdict_source_fallback.py`（加 `-s`）全绿。
- 既有全套件在本机基线上**零新增失败**（基线含 Windows 环境噪声，见根 `AGENTS.md`；基线数由 PM 在 T-06 提供）。
- 报告含：改动点 file:line 清单、开关关闭/开启两种情形的实测证据、未触碰 sha 锁区域的证明（git diff 范围）。

## 纪律

- **只写 `autopilot/conductor.py` + `autopilot/config.py`**（+ 报告）。**不改** `xkey.py`（T-01 的）、不改任何测试文件（除非上列 3 个写侧 prompt 测试确需同步——则最小改动并说明）、不改 TS。
- `_parse_l3_output` / `_md_section` 所在区域**禁止改动**（sha 锁）。
- 不跑全量套件（PM 负责）；不 commit。
