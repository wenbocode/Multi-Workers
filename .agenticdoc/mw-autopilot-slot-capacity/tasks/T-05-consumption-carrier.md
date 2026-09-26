# T-05: 消费记录载体：门文件字段 + timeline 只读回退

- 波次: **1** · 依赖: T-01, T-03
- 写面（独占）: 
  - `packages/multi-workers/autopilot/conductor.py`（消费段 `:297-379`）
  - `packages/multi-workers/test_autopilot_gate_consumption.py`（新建，若 T-01 已建则追加）
- AC: AC-022, AC-023, AC-028 · VC: VC-031, VC-032, VC-043
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

把"门已被消费"这一事实从**可被轮转剪掉的 timeline 反推**改为**门文件内的持久字段**（D-004），并保留 timeline 只读回退以兼容历史。

## 交付物

- 应答/消费路径写 `consumed_at`（ISO）+ `consumed_seq`（单调序号，来源同 `created_at` 族）。
- `_consumed_gate_ids` 改为**门字段优先**：命中 `consumed_at` 即已消费；缺失时**只读**回退到 timeline 反推（不改写历史）。
- 去重键改**复合 `(id, created_at)`**（gate id 跨归档重用：FM `gates/` max=10 vs 归档 `gate-0004..6687`）。
- 幂等：同一门重复消费不重写字段、不追加事件。

## 契约（不得重定义）

- timeline 回退路径**只读**；`auto-decisions.jsonl` 与消费记录是两件事（后者归 T-07）。
- 字段名固定 `consumed_at` / `consumed_seq`（T-03 已解析）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_consumption.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py -q`

## 非空洞对照（必须附在回执里）

- 把 timeline 历史（含 `gate-answered`）整体移走（模拟 2 代轮转）⇒ 消费判定**仍必须命中**（新载体生效）。
- 构造同 id 不同 `created_at` 的重用 fixture ⇒ 必须**不**判为已消费（复合键生效；旧键会误判）。
- 重复消费同一门 ⇒ 字段与事件计数不增。

## 风险与注意

- `_set_stage_status` / `_apply_stalled_rejections` 与 T-01 同文件 ⇒ 严格串行，开工前确认 T-01 已提交。
- JC `gate-0008` 形态（重放已答门）必须被本卡修法与 T-01/D4 联合覆盖，用例照抄真实字段值。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-05-consumption-carrier/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
