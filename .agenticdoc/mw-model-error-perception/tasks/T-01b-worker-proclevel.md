# T-01b: worker 错误路径进程级化（worker-mode.ts 修订）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（GC-1 不改 core / GC-2 文件证据 / GC-3 看门狗语义）。
- 背景：T-01 已落地 error 状态机，但 PM 读码裁决（design.md §2 D3 修订记录）：`agent_settled` 期入队的 followUp 在 print mode 下无人消费（agent.ts:368-376 drain 在 `agent.prompt()` 内部、settle 在其后；print-mode.ts:131 prompt 返回即 dispose）——**in-process 重发链生产不工作**。经用户确认的进程级架构（D2 方案 A）延伸：重试也全部进程级。
- spec 修订：AC-001/005/008/009 已更新（`.agenticdoc/mw-model-error-perception/spec.md`）；design §2 D3 修订版为实施蓝图。
- 现状锚点（T-01 交付）：worker-mode.ts error early-return 分支（:3811+）、`modelExhaustedExit`（:3780）、`currentPromptForRetry`（:3758）、`resolveModelErrMax`/`parseTriedModels`（文件末尾纯函数区）、`IdleKillEvidence.lastModelError`（:2430/:2453）、timeoutExit（:3226）、`[IDLE_KILL]` 两处调用（:3468/:3496）。

## 要求

1. **删除 in-process 重发**：agent_settled error 分支不再 sendUserMessage(followUp)，error settle 一律走 `modelExhaustedExit(lastError)`（exit 3）；移除 `currentPromptForRetry` 与 `consecutiveModelErrRuns` 计数逻辑（每进程至多一个 error run，计数失去意义）；`[MODEL_ERR]` 行保留（run=1）。
2. **移除 worker 侧 N 预算**：`PI_WORKER_MODEL_ERR_MAX` 语义移交 launcher（同模型重试次数）；worker 侧删除 `resolveModelErrMax` 及其调用；`PI_WORKER_FALLBACK_INDEX/TRIED` env 消费不变。
3. **挂起型改判**（design D4 补丁）：timeoutExit 的 idle 分支，若 `freshestInFlightTool()===undefined`（无在飞工具，卡在 LLM 调用）且 `lastModelError` 为真（本进程出现过 error 边界）或本进程零成功 assistant（纯首调挂起），则按 model-exhausted 处理：写既有 [IDLE_KILL]/[TIMEOUT] 证据行后 exit 3 + run.json `model_exhausted:true`；有在飞工具（真工具挂死）保持 exit 1。
4. AC-003 拦截、[MODEL_ERR]/[IDLE_KILL] 行格式、modelExhaustedExit 的 output.md 组装（含中间产物）保持 T-01 已实现语义。
5. 禁止：改 output-writer 已有协议（除非类型必需）、pm/**、Python 侧、packages/ai、core、`~/.pi`、恢复 followUp 重发。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`

## 写入禁止面

- output-writer.ts（T-01 已定型）、其他任何文件、`~/.pi`

## 验收命令

```
npm run check
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-idle-heartbeat.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```

- 全绿；fake-pi 冒烟：单条 faux error settle → exits=[3] + run.json model_exhausted + [MODEL_ERR] run=1；in-run 恢复（error 后 success）→ 正常 settle 不 exit；无在飞工具 idle 墙 → exit 3；在飞工具 idle 墙 → exit 1

## 改动历史

- 2026-10-15 创建（D3 修订衍生，依赖 T-01）
