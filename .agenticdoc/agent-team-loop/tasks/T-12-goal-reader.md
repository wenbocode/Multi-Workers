# Task T-12: goal-reader.ts（goal elicitation 对话）

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-021]
- vc_refs: [VC-029]
- pattern_refs: []

## 描述
实现 `pm/goal-reader.ts`：处理 goal.md 的读取和多轮对话式生成（goal elicitation）。

**读取**：读取 `.agenticdoc/goal.md`，解析 `## Goal`、`## Context`、`## Key Constraints` 三节内容。

**Elicitation**（goal.md 不存在时）：
通过 pi TUI 发起多轮对话，引导用户描述目标（Goal）、背景（Context）、关键约束（Key Constraints）。
对话完成后写入 `.agenticdoc/goal.md`，三节均非空。

## 输入
- 依赖文件: `.agenticdoc/goal.md`（运行时文件）
- 依赖 Task: 无
- AC 约束:
  > AC-021: goal.md 不存在时，pm-orchestrator.ts 以 goal elicitation 模式启动对话，产出 goal.md 含 ## Goal / ## Context / ## Key Constraints 三节且各节内容非空

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/pm/goal-reader.ts`
  - `export async function readOrElicitGoal(agenticdocRoot: string, pi: PiApi): Promise<Goal>`
  - `Goal`: `{goal: string, context: string, keyConstraints: string}`
  - goal.md 不存在时发起多轮 TUI 对话，写入文件后返回
- 验证方式: VC-029（goal elicitation 产出 3 节非空，L2 E2E）
- 验证等级: Level 2

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: Pi TUI 对话 API 待确认（pi.prompt() 或类似）
- 处置: 实现前查 Pi Extension API 对话/提示 API
