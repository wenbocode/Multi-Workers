# mw-dp-receipt-continuation · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-receipt-continuation
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

让 PM 沿同一正式裁决完成回执，遇到参数拒绝可逐步修正，窗口重载或写入超时后可从账本接续。

## 范围

控制与目标工作区均为本仓库。覆盖 pi PM 窗口的回执入口、现有生命周期账本和回执修正状态。RenderPerformance 的原 PASS 用于隔离回放。

## 验收标准

- AC-001: T-01 从真实工具入口送入缺失或不合法的参数，PM 收到一个带字段的 next；材料修正之前无回执写入。
- AC-002: T-02 重开后经当前认领从现有账本接续 RenderPerformance 原裁决和事件。重复提交该事件仍只有一条记录，新增 DP 请求为零，外来 key 或缺少正式裁决的情况被拒绝。
- AC-003: T-03 区分已知写入拒绝与结果不明。已知错误指向修正字段，状态不明先照原事件对账。首次计零，原样重发不计数，连续三次无进展只暂停该回执，有效修正可接续。

## 关键决策

PM 入口按当前认领复用现有正式裁决及单一生命周期写入器。把反馈状态随回执保存，使用原事件做幂等和对账。

## 执行与验收

- T-01 已完成。坏参数通过实际 pi 工具入口返回一个字段修正动作。
- T-02 已完成。经实际 PM 认领使用原正式裁决和原事件恢复回执。
- T-03 已完成。确定拒绝和未知结果分别修正与对账，三次无进展暂停同一回执。

## 接续须知

恢复时运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-dp-receipt-continuation`。
