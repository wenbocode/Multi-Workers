# Research: parallel-protocol（spec 阶段零调研声明）

> Key: mw-parallel-protocol
> 日期: 2026-09-22
> 类型: 零调研声明

## 研究问题

本 key 是否存在需要外部调研的关键决策（技术选型 / 三方 API 行为 / 版本兼容 / 未知运行时语义）？

## 结论

**无。** 本次改动的全部依据均来自本仓库已有代码事实，逐条列出：

1. `pi.on("before_agent_start")` 的契约与返回类型：`packages/coding-agent/src/core/extensions/types.ts:698-709`（`BeforeAgentStartEvent`）与 `:1097-1101`（`BeforeAgentStartResult{ message?, systemPrompt? }`），文档 `packages/coding-agent/docs/extensions.md:521-558`。
2. 处理器链式语义（多扩展追加、`event.systemPrompt` 已含前序修改）：同文档同节。
3. PM/worker 分支：`packages/coding-agent/src/extensions/agent-team-loop/index.ts`（`if (process.env.PI_WORKER_TASK) workerModeActivate else pmActivate`）。
4. 既有先例（worker 侧已在用该钩子）：`worker/worker-mode.ts:560`、`rag/tools.ts` 的 `applyRagTools`。
5. 调研类角色只读、无文件冲突：`worker/worker-mode.ts:48-58`（`research: read/find/grep/ls/bash`、`review: read/find/grep/ls`、`rag-research` 为 read + rag_*）。
6. 证据文件按前缀计数、gate 只要求 `>= 1`：`shared/phase-docs.ts:44,63-97`。
7. 命名约定 `evidence/research/spec-{topic}-{date}.md`：AgenticTask 框架 `core/workflows/requirements.md` Step 3.6（`system-design.md` step 5 同构）。

## 待验证假设（实现后由测试验证，不构成预实现风险）

- H-1: 幂等判重（上一轮 `systemPrompt` 再喂回处理器应返回 `undefined`）在真实调用序列中成立——由新增单测覆盖。
- H-2: 注入文本不改动门禁语义——由文本内容评审 + 现有门禁测试（`test/suite/agent-team-loop-implementation-gate.test.ts`）回归覆盖。

## 来源

- 本仓库代码（上述文件:行），无外部资料、无三方 API 行为依赖。
