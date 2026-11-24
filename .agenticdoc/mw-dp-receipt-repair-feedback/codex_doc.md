# mw-dp-receipt-repair-feedback · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-receipt-repair-feedback
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

让 PM 收到回执拒绝后能知道如何继续原裁决的工作。落实 `mw-dp-repair-loop` 对现行执行入口受阻时的一步反馈约定。

## 范围

控制及目标工作区为本仓库。修改窗口 `decision_receipt` 的反馈与回归。复用现有认领、裁决绑定和生命周期写入器。

## 验收标准

- AC-001: 无任务裁决收到任务观察对象时，零写入并返回一个 next，指定 PM 把 task_after 改为 null，沿原裁决、阶段和事件重交。纠正后写入一次，新增 DP 请求数为零，成功回执省略 next。
- AC-002: 不合法的任务观察、action 或 outcome 返回对应字段和一个修正动作。未绑定的裁决或认领要求先核实绑定。回执写入失败先按原事件核对账本。所有拒绝和不确定结果都保留原身份。

## 关键决策

窗口回执反馈使用一个 `next`，带责任方、动作与完成条件，并在有事件标识时保留该标识。使用原阶段的真实事实，交由原写入器核验。

## 执行与验收

<!-- 按需要列出工作项、执行者、进度及 evidence 中的验证路径。区分自验与独立复核。 -->

## 接续须知

恢复时运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-dp-receipt-repair-feedback`。
