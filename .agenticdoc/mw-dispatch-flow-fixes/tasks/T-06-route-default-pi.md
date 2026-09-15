# Task T-06: pickWorkerRoute 默认 pi（移除 claude 硬路由）

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-006, AC-007]
- vc_refs: [VC-009, VC-010]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` `pickWorkerRoute`（design D-005）：
1. 删除 `if (/^type:\s*(review|research)/im.test(taskContent)) return { cli: "claude", provider: "" };` 一行——`type: codex → codex` 保留，其余（含 review/research）落默认 `pi/timi`
2. dispatch_worker 工具与 /worker 命令的显式 cli 参数行为不变（typeField 映射保留：显式 claude 仍写 `type: review` 且队列行 cli=claude）
3. vitest 正向断言：
   - VC-009：扫描路径 task.md `type: review` → 队列行 cli=pi、provider=timi
   - VC-010：dispatch_worker 显式 cli=claude → 队列行 cli=claude（回归）；`type: research` 内容扫描 → pi/timi
4. 文档同步：仓库内提及 review→claude 路由的文档/注释（rg 确认 packages/multi-workers/dispatch-table.md、扩展 README 或注释）改为默认 pi 语义
5. 类型与格式注意：既有扫描用例全用 `type: coding`，无该映射断言（已核实）——新增断言为主，无改写负担

## 输入
- 依赖文件: pm/pm-orchestrator.ts（pickWorkerRoute）、test/extensions/agent-team-loop.test.ts、提及路由的文档
- 依赖 Task: 无
- AC 约束:
  > AC-006: 无 claude 凭证环境下，派发 type: review 任务时 launcher spawn 的 CLI 为 pi、provider 为 timi（原 type→claude 硬路由移除）
  > AC-007: 显式 cli=claude 仍路由 claude；type: review|research 字段本身不再触发 claude 路由

## 预期产出
- pickWorkerRoute 修改 + 正向断言 + 文档同步
- 验证方式: 定向 vitest + `npm run check` + rg 确认无残留 review→claude 文档表述
- 验证等级: Level 1（无凭证环境实跑归 VC-012/T-11）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:21 | pickWorkerRoute 删 review\|research→claude 行（codex 保留）；VC-009/010 扫描路由断言（review/research→pi/timi、codex→codex）+ 显式 cli=claude 工具路径断言；dispatch_worker cli 参数描述同步新语义；rg 确认无残留文档表述 | PASS: 60/60（定向 vitest） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
