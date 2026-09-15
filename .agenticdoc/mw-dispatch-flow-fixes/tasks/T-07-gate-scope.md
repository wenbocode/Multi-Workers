# Task T-07: docs gate 收敛 + 播报作用域

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-010, AC-011]
- vc_refs: [VC-013, VC-014, VC-015, VC-016]
- pattern_refs: []

## 描述
`pm/pm-orchestrator.ts`（dispatchNewTasks + pmActivate 接线）（design D-006）：
1. `dispatchNewTasks` 重排：per-owner 先收集未入队任务（isDirectory、非 `.` 前缀、task.md 存在、不在 dispatched 集合）→ 列表为空则 `continue`（不评估 gate、零开销）→ 非空才 `dispatchDocGaps` 评估；gaps 非空仍 `continue`（阻塞语义全局不变），否则派发全部未入队任务
2. `ui-bridge.ts` 新增 `makeScopedDocGateNotifier(pi, watch): (key, gaps) => void`：仅 `key === watch.key` 时 `displaySummary`（gate 告警文案不变），否则静默；pmActivate 的 `onDocGate` 接线改用之
3. 终态摘要作用域（AC-011 固化）：现有 `ownerKeyOf(entry) !== watch.key` 过滤已存在——新增显式单测防回归（VC-016，fake pi 捕获 sendMessage：watch key 名下任务 1 条、他 key 0 条）
4. vitest（既有 undoc-key 用例语义不变）：
   - VC-013：undoc key + 全部任务已入队 → gates 数组 0 次
   - VC-014：undoc key + 1 未入队 → gates 1 次（每 session）且不入队（既有用例保持）
   - VC-015：scoped notifier——watch=K 时 K 事件播报 1 条、J 事件 0 条；无 watch 全 0

## 输入
- 依赖文件: pm/pm-orchestrator.ts（dispatchNewTasks/startWorkerPollLoop/pmActivate）、pm/ui-bridge.ts、test/extensions/agent-team-loop.test.ts
- 依赖 Task: 无
- AC 约束:
  > AC-010: docs-gate 仅对存在 ≥1 个未入队任务且 phase 文档缺失的 key 评估并告警
  > AC-011: 播报按窗口认领 key 作用域过滤（终态摘要 + 扫描 gate 告警；dispatch_worker 同步 blocked 反馈与 mw 服务级播报不受影响）

## 预期产出
- dispatchNewTasks 重排 + scoped notifier + 接线
- vitest 用例（VC-013~016）+ 既有用例回归
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:22 | dispatchNewTasks 未入队收集前置（空则 continue，不评估 gate）+ makeScopedDocGateNotifier + pmActivate 接线；VC-013（全入队 undoc → 0 gate + 对照 undoc-live 仍 gate）+ VC-015（watch 作用域三态）；VC-016 由既有 "stays silent without a watched key" 用例覆盖（含他 key 任务断言） | PASS: 60/60（定向 vitest；含既有 undoc gate/once/docs-exist 用例回归） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
