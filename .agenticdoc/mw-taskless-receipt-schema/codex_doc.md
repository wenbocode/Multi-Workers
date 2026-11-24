# mw-taskless-receipt-schema · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-taskless-receipt-schema
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

让没有绑定任务的 PM 正式裁决可以记录实际执行和处理结果，避免收尾卡在可选任务观察上。

## 范围

控制与目标工作区均为本仓库。修复 `decision_receipt` 参数及传给生命周期写入器的材料。RenderPerformance 仅用于只读确认场景。

## 验收标准

- AC-001: 接受一项没有 task_key 的 PM 裁决后，窗口回执可省略 task_after 或传 null。两种都使用原决策与事件标识，写入器参数均无 task_after，新增 DP 请求数为零。
- AC-002: 无任务决策附实际任务对象时拒绝，零回执写入。带任务的决策仍可记录有效观察。用窗口注册工具提供的 schema 验证上述输入。

## 关键决策

保留可选声明，使 null 等同省略。传真实对象时继续校验任务绑定和观察事实。沿用窗口内现有裁决绑定。

## 执行与验收

<!-- 按需要列出工作项、执行者、进度及 evidence 中的验证路径。区分自验与独立复核。 -->

## 接续须知

恢复时运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-taskless-receipt-schema`。
