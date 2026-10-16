# T-05: TS 测试（worker 状态机 + PM 告警）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`；约束：`test/suite/` 用 harness + faux provider，禁真实 API（AGENTS.md）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-005/007）；design：design.md §5.1/5.2/5.3/5.5（测试蓝图）、§4 契约。
- 依赖：T-01（状态机）、T-01b（进程级化，2026-10-15 合入：error settle 一律 exit 3、无重发；挂起型 idle 改判判据 `lastErrorInfo !== undefined || (!sawSuccessfulAssistant && agentRunStarted)`；`[MODEL_ERR] run=1`）、T-04（pm-orchestrator 告警）均已合入。
- 实现锚点（行号以当前文件为准，先自行定位）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（`timeoutExit(kind, detail, modelExhausted?)`、`modelExhaustedExit`、`noteBoundary`、agent_start/agent_settled 处理、文件末尾纯函数区 `parseTriedModels`/`formatModelUnavailableReason`）、`worker/output-writer.ts`（writeOutput exitCode 3 渲染）、`packages/agent/src/agent-loop.ts:109`（agent_start 先于 runLoop）。
- 仿真手段（TRQ-4 取证）：`fauxAssistantMessage(content, {stopReason:"error", errorMessage:"HTTP 500"})`（packages/ai/src/providers/faux.ts:114，FauxResponseStep=AssistantMessage 可直接注入）；管线级先例 test/extensions/agent-team-loop-checkpoint-wiring.test.ts:366-404（createHarness + extensionFactories + setResponses）；时序级先例 test/suite/worker-idle-heartbeat.test.ts（fakePi + fake timers + env 注入）。

## 要求

1. 新文件 `packages/coding-agent/test/suite/worker-model-error-perception.test.ts`（**注意：D3 已修订为进程级**，worker 在首个 error settle 即 exit 3，无 in-process 重发）：
   - 管线级（createHarness + faux + settings.retry baseDelayMs:1）：单条 faux error assistant → 断言 exit 3、trace 含 1 行 `[MODEL_ERR]`（注意实际落盘为 `[FLOW] <iso> [MODEL_ERR] …`，用 includes/字段断言勿锚行首）、run.json `model_exhausted: true` 且 status=failed、output.md `## Exit Reason` 以 `model unavailable:` 开头且含 tried 链与 last err、中间产物字段在（AC-001/003/004）
   - 抖动保护：faux error 后跟 faux success（run 内 auto-retry 恢复路径）→ settle 正常 done、不 exit 3（AC-005）
   - 无 phases write 角色：全 500 不得 exit 0/done（AC-003 反向断言）
2. 时序级（fakePi + fake timers）：① 挂起型改判：无在飞工具 + lastModelError → idle 墙（缩短值）击杀时 exit 3 且 run.json model_exhausted、`[IDLE_KILL]` 含 `last_model_error=yes`；② 在飞工具 tool-idle 击杀仍 exit 1；③ 成功事件照常喂钟（回归既有 worker-idle-heartbeat 期望）
3. PM 告警：同 key 连续 2 次 model-error 终态 → kind=model-error 告警记录；中间非 model-error 终态清零（AC-006）
4. 环境变量：worker 侧不再消费 `PI_WORKER_MODEL_ERR_MAX`（预算已移 launcher）；`PI_WORKER_FALLBACK_INDEX/TRIED_MODELS` 链在 Exit Reason 的呈现断言
5. 禁止：改 src 实现（发现问题报 PM，不自行修 src）；真实网络/凭证

## 写入允许面

- `packages/coding-agent/test/suite/worker-model-error-perception.test.ts`（新建）
- `packages/coding-agent/test/extensions/` 下既有 pm/worker 测试文件的**最小断言适配**（若 T-01 行为变更导致既有断言过时，允许改断言并在交付说明逐条列出）

## 写入禁止面

- src/**（实现修复走 PM 决策）、Python 侧

## 交付格式

- 新建测试文件 + 最小断言适配清单（仅限写入允许面）
- 交付说明：断言面与 AC 对映、两类 harness 先例的复用说明；验收命令输出摘要；发现的实现问题清单（如有，仅报告不修）

## 验收命令

```
npm run check
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-model-error-perception.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-idle-heartbeat.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts
```

- 全绿（从 packages/coding-agent 下执行；npm run check 中 biome 对 mwoc-*.test.ts 的既有基线告警不阻塞本任务，逐条注明即可）

## 改动历史

- 2026-10-15 任务创建（T-05，Stage 2，依赖 T-01/T-04）；同日修订：D3 进程级语义、T-01b 合入锚点、vitest 路径修正、补锚点与交付格式
