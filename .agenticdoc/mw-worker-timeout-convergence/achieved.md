# Achieved: mw-worker-timeout-convergence

> 完成日期：2026-09-09
> 质检：✅ 通过（evidence/quality-gate-report-2026-09-09.md）

## 交付了什么

Worker 看门狗从"纯 30 分钟墙钟"重做为四层机制，全部在 agent-team-loop 扩展内（GC-1），Python/launcher/队列协议零改动：

1. **AC-001 activity watchdog**：全生命周期事件（message_update token 增量、message/turn/agent 边界、tool_execution_*）刷新活动时钟；无任何活动超过 idle 阈值（默认 10m，PI_WORKER_IDLE_MS 可调）判真挂死；[TIMEOUT] 行携带判别证据（最近 delta / 最近 tool 距今秒数）
2. **AC-002 per-task 预算**：task.md `timeout:` 分钟头 > PI_WORKER_TIMEOUT_MS > 默认 60m 墙钟兜底；worker 自读 task.md
3. **AC-003 deadline steer**：预算尾段（budget−min(5m, budget/4)）注入收尾指令（deliverAs: "steer"），agent 自行把 已完成/未完成/后续建议 写入最终回复 → output.md
4. **AC-004 收敛检查点**：min(30m, budget/2) 写 [CHECKPOINT] 机器判据行（elapsed/reads/writes/phases/uniq_targets/repeat_top/risk）+ steer worker 向 progress.md 自评（CKPT converging=yes|no）；每 10m 刷新；PM poll 发现首个 mid/high → triggerTurn 唤醒 PM 主窗口携证据判断（继续/收窄/分拆重派/PM 直执）
5. **AC-005/006**：widget ck 徽标（risk!=low 加 ⚠）；[FLOW]/[GOAL_CHECK]/[HEARTBEAT] 等既有格式零变更

## 目标如何达成

- 需求源于用户 OverCode 取证（4 个被误杀 worker 两模式：健康任务预算不足 / 长生成在途被杀），方案 B+A+C 两轮对话定稿（spec §4 D-1~D-5）
- 验证三层：vitest 87/87（本 key 净增 14，含 4 个 workerModeActivate 集成测试：idle 精准杀 / delta 滴流不杀 / 多 phase 看门狗存续 / 小预算三计时器顺序与 deliverAs 选项）；实跑两轮烟雾（Run 1 发现并修复 agent 运行中裸 sendUserMessage 抛 already-processing → followUp/steer 修复；Run 2 全路径 PASS，agent 在预算内自行收尾 exit=0）；npm run check 580=既有基线零交集
- goal.md GC-4 约束行同步修订为新的看门狗语义

## 学到了什么

- `pi.sendUserMessage` 在 agent 运行中（流式或工具执行中）必须带 deliverAs（steer/followUp），否则抛 "Agent is already processing"——两处 steer 的排队模式选择（checkpoint=followUp 不打断在途工作，deadline=steer 紧急注入）由实跑发现
- closure 内的计时器判定逻辑（idle interval）组件级单测测不到，必须走 workerModeActivate 集成测试（process.exit spy + fake timers + emit 事件）才能覆盖
- 机器 risk 判据（零写纯读=high）对非编码任务（如纯 sleep）会误报——设计上定位为 advisory，决断权在 PM 主窗口

## 遗留

验证欠债 3 项见质检报告（PM 升级 triggerTurn 实机首验待窗口重启；idle 阈值收紧待流式确认；evidence-requirement.md 模板对齐待闲时）。
