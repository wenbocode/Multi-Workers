# T-01: worker 侧模型错误状态机（worker-mode.ts + output-writer.ts）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（Extension API only GC-1；文件驱动证据 GC-2；看门狗语义延续 GC-3）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-001~005 worker 半）；design：`.agenticdoc/mw-model-error-perception/design.md` §3.1（本任务实现蓝图）、§2 决策 D1/D3/D4/D6、§4 协议契约（env/trace 行/退出码 3）。
- 关键锚点（TRQ-2/TRQ-5 取证，行号以当前文件为准自行校对）：
  - `agent_end` 仅提取文本：worker-mode.ts:3139-3153
  - `agent_settled` handler（error 盲视区）：worker-mode.ts:3707-3777；首 settle 发 phase 1 :3715-3726；phase 推进 :3729-3760
  - `touch`/活动钟：worker-mode.ts:3035-3052；idleTimer :3403-3460；appendIdleKillEvidence :2439-2448
  - 有界退出模式（同步落盘→kill 子进程→exit）：timeoutExit :3226-3253；markOutcome :2655（0=done/2=nc/else=failed，**不改**，3 萰 else）；recordEnd :3156
  - followUp 重发先例：worker-mode.ts:3368-3394（checkpoint steer）
  - env 解析先例：resolveIdleMs :256-260；phase 状态 :3470-3476；finishSuccess :3536+（error settle 不得进入）
  - 当前模型来源：session_start 的 ctx.model（D-116 `[MODEL]` 行同源）
- 事实约束：agent_end 每 attempt 触发（内部 auto-retry 3 次=3 个 agent_end），agent_settled 每 run 链恰一次（agent-session.ts:596-604 finally）——计数/重发/退出只能挂 agent_settled，agent_end 仅记录 lastError（design D1 方案 A）。

## 要求

按 design §3.1 实现，逐条：

1. 新增状态：`consecutiveModelErrRuns`、`currentModelId`（session_start ctx.model）、`triedModels`（env `PI_WORKER_TRIED_MODELS` csv 初始化，追加当前模型）。
2. `agent_end`：提取末位 assistant `stopReason`/`errorMessage` 存 `lastErrorInfo`（不动作）。
3. `agent_settled` handler 在 taskDone 检查后、**initialSettled/phase 推进/settleOrSelfCheck 全部分支之前**插入 error 分支：
   - stopReason==="error" → 计数+1、appendTrace `[MODEL_ERR] <iso> model=<p/m> run=<k> err=<截断200>`；计数 ≥ N（`resolveModelErrMax`：PI_WORKER_MODEL_ERR_MAX int 默认 2，0=禁用计数仅记证据）→ `modelExhaustedExit`：同步写 output.md（`## Exit Reason` = `model unavailable: tried=<triedModels 链> last=<err>` + collectArtifacts + phase 进度 + lastAssistantText 截断 200）→ appendEnd/recordEnd(3) → killTrackedDetachedChildren → process.exit(3)；计数 < N → `pi.sendUserMessage(当前 prompt, {deliverAs:"followUp"})`（phased=当前 phase prompt；无 phases=初始 task 内容），**不推进 initialSettled/phase 状态**
   - 非 error → 计数归零，既有流程原样（AC-005）
4. AC-003 语义：error settle 永不写 phase 完成文件、不 appendPhase done、不进入 finishSuccess 成功判定（由第 3 条 early-return 保证）。
5. 活动钟（design D4 方案 A）：message_end/turn_end/agent_end 三个 handler 中，若事件末位 assistant 为 stopReason==="error"，则**不调用 touch**（不刷新 lastActivityAt/lastDeltaAt），但仍记录 lastErrorInfo；`appendIdleKillEvidence` 增加 `last_model_error=yes|no` 字段（同步改 IdleKillEvidence 接口与 [IDLE_KILL] 行格式）。
6. recordEnd/退出码类型 `0|1|2` 扩为 `0|1|2|3`；exit 3 时 run.json 写 `model_exhausted: true`（writeRunState 协议扩展）；markOutcome 本体不改。
7. 禁止：改 packages/ai、pi core、pm/*、Python 侧、任何 `~/.pi` 路径、setModel。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（仅退出码/字段类型扩展与 output.md 字段）

## 写入禁止面

- test/**（T-05 所有）、pm/**、packages/ai/**、core/**、Python 全部、`.pi/` 用户配置

## 验收命令

```
npm run check
node node_modules/vitest/dist/cli.js --run test/suite/worker-idle-heartbeat.test.ts   # 从 packages/coding-agent 下
node node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```

- 全绿；若活动钟变更破坏既有 idle 断言，优先在 D4 方案 A 内修正实现，确不可行时回退 D4 方案 B（仅加 last_model_error 标记不移除喂钟）并在交付说明中记录
- 并行说明：其他并行 worker 正在改 mw.py/launcher.py/pm-orchestrator.ts，check 中那些文件的报错不归你修

## 改动历史

- 2026-10-15 任务创建（T-01，Stage 1）
