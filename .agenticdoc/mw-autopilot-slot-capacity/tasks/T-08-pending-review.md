# T-08: 待复核状态（case 2）+ 合法重开（两侧同波）

- 波次: **3** · 依赖: T-07
- 写面（独占）: 
  - `packages/multi-workers/autopilot/conductor.py`（收口段 `:266-271` + `:616-656`）
  - `packages/multi-workers/autopilot/roadmap.py`（key-status enum）
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（key-status 段）
  - `packages/multi-workers/test_autopilot_pending_review.py`（新建）
- AC: AC-027, AC-028 · VC: VC-039, VC-040, VC-041, VC-042, VC-043
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

非阻塞延后复核的落地形态：**不计入 stage 终态**、改为**收口前置**，并有时间兜底与合法重开路径。

## 交付物

- key-status 新增 `pending-review`（两侧同波；`_DEP_SATISFIED:56` **不含**它 ⇒ 不解锁依赖；`_stage_closure:629-631` 终态集不变）。
- 收口前置（落点 `:266-271`）：同 stage 其它 key 全终态 ∧ 该 key 无 in-flight 行 ⇒ 推批量复核，**不自动收口**；`conductor.py:274` 的字面量跳过元组必须加上新状态（漏加 ⇒ 待复核 key 继续被派发）。
- 时间兜底 48h ⇒ 写 `review-escalated` 升级给人，**不改状态**。
- 合法重开：`review-decided{resume|rework|escalate}` 只动 key-status（resume/rework → `running`；escalate → `stalled`），**无 `done` 出口、无 `closed-legacy` 出口**；conductor 永不主动重开 stage。
- 消费者穷举（Python 17 读点 + TS 10 读点 / 6 写点）逐点核对，跨语言 enum fail-closed（未知值 ⇒ 跳 tick）保持。

## 契约（不得重定义）

- `pending-review` 是**非终态**；monitor 与 `_DEP_SATISFIED` 是两份独立镜像字面量，都要按同一语义处理。
- 阶段永不回退（依赖 T-01 的单调判据）。
- 历史 stage 不回改。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-status-model.test.ts`

## 非空洞对照（必须附在回执里）

- 存在待复核 key ⇒ `stage-close` 门**不建**、stage **不收口**（VC-039 红若收口）。
- 同 stage 其它 key 全终态 ⇒ 同一 tick 推**全部**待复核 key（VC-040）。
- 超 48h ⇒ 升级事件写入且状态**不变**（VC-041）。
- 构造 conductor 主动重开 stage ⇒ 被单调判据拒绝（VC-042）。
- `pending-review` 若被误当终态 ⇒ `_stage_closure` 提前收口用例必须红。

## 风险与注意

- 未知 key-status 值会让 conductor **跳整个 tick** ⇒ 两侧必须同波上线（单侧 = 停摆）。
- `status-model.ts` 在本卡再次被碰 ⇒ 与 T-02/T-09 严格串行（波次已保证）。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-08-pending-review/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
