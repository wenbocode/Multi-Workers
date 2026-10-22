# D4 设计调研：`ask_decision` 工具 + `tool_call` 钩子 + 工具白名单

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-ask-tool-hook-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"不修改 pi 核心：所有功能通过 Extension API 实现"）
- 超时: 30m

## 上下文（已冻结）

spec §5.3：决策调用走 `ask_decision` 工具、答案作为**工具返回值**回灌；拦截用扩展 `tool_call` 钩子（`{block:true, reason}`）；**禁用**伪造 user 消息；`context` 钩子禁放同步决策。

关键锚点：`packages/coding-agent/src/core/agent-session.ts:480`（tool_call 钩子调用点）、`packages/coding-agent/src/core/agent-loop.ts:636-641`（block 落地）、`packages/coding-agent/src/core/extensions/types.ts:139-141`（confirm/input/select）、`:830-831`（input 事件 source）、`packages/coding-agent/src/core/extensions/runner.ts:236-238`（headless UI noOp → fail-closed）、`packages/coding-agent/src/core/agent-session.ts:213-215`、`core/sdk.ts:55-70`（会话级 allow/deny）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts`（既有自定义工具范例）、`pm/triage-client.ts`（既有 Python 调用范例）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 工具注册 API**：当前 pi 扩展如何注册一个自定义工具（参数 schema、description、execute 签名、返回形状、错误返回）。以 `worker-file-tool.ts` 为范例给出可直接抄的最小骨架；指出工具在 PM 模式与 worker 模式下的可见性差异（`PI_WORKER_TASK` 开关）。
- **RQ-2 工具返回值契约**：`ask_decision` 的入参（dp id / question / trigger 摘要）与返回值（`{answer, confidence, source, decision_id, mode}` 或 `{unavailable, reason}`）。返回值如何被 LLM 消费（进对话上下文的具体形态）；如何避免模型把 `unavailable` 当成"可以自己猜"。
- **RQ-3 钩子拦截**：用 `tool_call` 钩子做 dp 级拦截的具体写法（返回值类型、异步、超时、异常）；被 block 后 LLM 侧看到什么（error toolResult 文本），如何保证它不会无限重试同一工具。给出一个"dp12 破坏性操作被拦"的端到端示例。
- **RQ-4 headless/print/rpc 行为**：三种非交互模式下工具与钩子是否都生效（对照 `runner.ts:236-238` 的 fail-closed）；若某模式下工具不可用，必须给失败路径（上抛人而非静默放行）。
- **RQ-5 白名单与写面守卫的关系**：dp 级开关与既有工具白名单（research/coding/review 的 allowlist）、`worker-file-tool` 的写面守卫（`worker-mode.ts:2986`）是什么关系（叠加还是替代）；新增 `ask_decision` 要不要加进白名单的每个角色；给出建议与理由。
- **RQ-6 失败安全**：Python 侧不可用 / 超时（20s 硬超时先例 `triage-client.ts`）/ 返回非法 JSON / 配置禁用，四种情况下工具应返回什么、LLM 应看到什么、如何留痕；证明没有任何一条路径会"默认继续"。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-ask-tool-hook-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；`## Q1..Q6` + `Q-answered: 6/6`；结论带 `path:line`；未确认写"未验证"。
- 不修改源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-ask-tool-hook-20261019.md
```
期望 6。
