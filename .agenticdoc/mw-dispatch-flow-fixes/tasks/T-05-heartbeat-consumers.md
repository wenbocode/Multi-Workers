# Task T-05: 心跳消费面（widget 活进度 + 终态摘要统计）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-012, AC-013]
- vc_refs: [VC-018, VC-019]
- pattern_refs: []

## 描述
`pm/ui-bridge.ts`（renderWatchLines）+ `pm/pm-orchestrator.ts`（终态摘要）（design D-008）：
1. `renderWatchLines` running 任务行增强（经 `readHeartbeatInfo(taskDir)`，taskDir = path.dirname(entry.taskPath)）：
   - 有心跳：`> task-key ph 2/3 hb 15s`（ageMs 格式化为 s/m）；ageMs > HEARTBEAT_STALE_MS → 行尾追加 `STALE`
   - 无心跳（旧 bundle/极早期）：`> task-key (no-hb)`
   - pending 行不变；终态行不变（已有 summary 细节）
2. 终态摘要（startWorkerPollLoop 内 displaySummary 调用处）：trace 含 ≥2 条 [HEARTBEAT] 时追加 ` ({duration}, ph {i}/{n})`（duration = firstTs→lastTs 人读格式；phase 完成度取最后一条 [HEARTBEAT] 的 phase）；<2 条保持现状格式
3. 单测（VC-018/VC-019）：构造 trace.log 三态（新鲜/陈旧/无）→ renderWatchLines 行断言；终态摘要 ≥2 hb 附统计、<2 hb 不附
4. 既有 renderWatchLines 用例（counts/phase/failure details）回归不破

## 输入
- 依赖文件: pm/ui-bridge.ts、pm/pm-orchestrator.ts、shared/heartbeat.ts（T-04）
- 依赖 Task: T-04
- AC 约束:
  > AC-012: watch widget 的 running 任务行显示心跳派生进度，随 poll 周期（≤5s）刷新；>90s 显示 STALE；无 [HEARTBEAT] 显示 no-hb 占位
  > AC-013: 终态摘要附带总时长与 phase 完成度；心跳 <2 条保持现状格式

## 预期产出
- widget 行增强 + 终态统计
- vitest 用例（VC-018/VC-019）+ 既有用例回归
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1（widget 4s 刷新为既有机制，L2 观察在 T-11）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:18 | renderWatchLines running 行 ph/hb/STALE/(no-hb)（formatHeartbeatAge 共享）+ 终态摘要 heartbeatStatsSuffix（<2 hb 保持原格式）；VC-018/019 用例 | PASS: 57/57（定向 vitest；含既有 renderWatchLines/summary scoping 回归） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
