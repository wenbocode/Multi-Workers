# Task T-09: /mw doctor 摘要活性行

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-004]
- vc_refs: [VC-007]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（/mw doctor 播报）或 `shared/mw-runner.ts`（formatter 所在处，实现时以 rg 定位为准）（design D-004）：
1. doctor JSON 摘要格式化处新增活性行：`workers alive: n | stale: k1, k2 | no-heartbeat: n`（各段仅在计数 >0 时显示；全无 running 时整行省略）
2. stale 任务名必须列出（VC-007 断言点）
3. vitest：fake doctor JSON（含 worker_liveness 节三种 verdict）→ 摘要字符串断言；无节/空 running 的向后兼容
4. 与 T-08 的 JSON 字段名严格一致（task_key/verdict）

## 输入
- 依赖文件: /mw doctor 播报格式化处（ui-bridge.ts / mw-runner.ts，rg "doctor" 定位）、test/extensions/agent-team-loop.test.ts
- 依赖 Task: T-08（JSON 结构）
- AC 约束:
  > AC-004: 活性判定机制可经命令/播报消费

## 预期产出
- 摘要活性行 + vitest 用例（VC-007）
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:27 | mw-runner DoctorJson 增 worker_liveness 字段；formatDoctorReport 增活性行（`worker 活性: 存活 N; 疑似挂起: <task>; 无心跳 N`，仅 running>0 时）；VC-007 用例（三判定行 + 无节向后兼容） | PASS: 61/61（定向 vitest；实现处为 ui-bridge formatDoctorReport，非 mw-runner formatter） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
