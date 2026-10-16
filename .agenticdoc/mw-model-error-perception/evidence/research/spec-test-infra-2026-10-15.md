# spec-test-infra — 模型持续 500/断连 fail-fast 测试基础设施盘点 (TRQ4, 2026-10-15)

为「模型持续 500/断连 → worker fail-fast + 证据落盘」新测试写盘点：既有 watchdog/timeout 测试驱动方式、faux provider 注入能力、ai 层重试覆盖、结论→决策映射。所有 file:line 已在本仓核验。

## 1. 现有 watchdog/timeout 测试清单（mw-worker-timeout-convergence / T-04 遗产）

### 1.1 `packages/coding-agent/test/suite/worker-idle-heartbeat.test.ts`（idle + tool-idle watchdog）

- 驱动方式：**不起 session、不碰 provider**。直接 `workerModeActivate(pi as unknown as ExtensionAPI)` 对打桩 `FakeWorkerPi`（仅 `on`/`sendUserMessage`/`emit`，:48-66），`vi.useFakeTimers()` 驱动 watchdog interval，`vi.spyOn(process, "exit")` 捕获 kill（:97-99, :117-119）。
- 注入手段：`makeWorkerTask()`（:58-73）写临时 `root/key-a/workers/<key>/task.md` 并设 `PI_WORKER_TASK` / `PI_WORKER_IDLE_MS=60000` / `PI_WORKER_TIMEOUT_MS=2h`；事件流用 `pi.emit("tool_execution_start" | "tool_execution_update" | ...)` 伪造（:126-131）；bash 心跳由真实 `createBashToolDefinition(root, { operations: { exec: () => never-resolving promise } })` 的 onUpdate 发出（:120-141）。
- 断言面：`[IDLE_KILL]` 行字段全契据（`tool_in_flight`/`tool_run_s`/`tool_idle_s`/`silence_s`/`threshold_s`/`threshold_kind`/`last_activity`，:171-183, :202-210）、trace 含 `[TIMEOUT]`（:186）、纯函数级 `DEFAULT_TOOL_IDLE_MS`/`resolveToolIdleMs`（:232-236）。

### 1.2 `packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts`（checkpoint + 真实管线 trace 证据）

- 驱动方式 A（watchdog 时序）：fake-timer `fakeWorkerPi()` + `startWorker()`（:156-167，写 task.md + `PI_WORKER_IDLE_MS=60000` 后 `workerModeActivate`）+ `trickleToAnchor()`（:174-179，15s×5 前进时钟并 `emit("message_update")` 喂 idle 看门狗）。
- 驱动方式 B（**真实 pi 管线 + faux**）：`createHarness({ extensionFactories: [async (pi) => { await workerModeActivate(pi); }] })`（:366-373）+ `harness.setResponses([fauxAssistantMessage([fauxToolCall(...)], { stopReason: "toolUse" }), fauxAssistantMessage("done")])` + `harness.session.prompt(...)`，断言 trace.log 中 `[TOOL] worker_file`（VC-005, :382-404）/ `[TOOL_ERR] worker_file`（VC-006, :406-429，含 schema 拒绝路径 :431-457）。
- 纯函数级：`checkpointSteerText` 冻结基线逐字节（:243-254）、`toolsForType`/`activeToolsForType` 十键快照（:64-82, :296-313）、`appendProgressLine` append-only（:225-248）。

### 1.3 `packages/coding-agent/test/suite/mwoc-w4-checkpoint-invariants.test.ts`（landing 判据 + I3 不变量）

- 纯函数级：`computeRisk` writeless/legacy 全分支（:61-141）、`collectLandingSignals`（ledger 为唯一来源 + T-12 mtime 钳制，:146-224）、`landFreshMs`（:143-147）、`CHECKPOINT_LINE_RE` 新旧行解析——**手写 trace.log 后走 `readTaskProgress`**（:231-273）。
- fake-timer 集成级：`[CHECKPOINT]` trace 行发射（AC-009 replay, :296-360，同一 startWorker/trickleToAnchor 形状）；I3-a 正常活动无 kill、I3-b 真挂死 `exit=1` + `[TIMEOUT]` + output.md 标记（:363-405）、I3-c 预算尾段顺序 checkpoint(`deliverAs:"followUp"`) → deadline steer(`deliverAs:"steer"`) → wall kill（`wall: budget 180s exceeded` + `exit=1`，:407-447）。
- 真实工件回放：仓库内 wjg-w12 trace（:403-440 区域，工件缺失时显式 skip 不假绿）。

### 1.4 其他同型测试

- `test/extensions/agent-team-loop.test.ts`（worker 循环时序，checkpoint-wiring 头注声明同形状）。
- `test/extensions/agent-team-loop-worker-tree-kill.test.ts`（:26 import workerModeActivate，:72-82 同款 `PI_WORKER_IDLE_MS=60000` 环境注入）；`-live` 变体起真实子进程。
- 墙钟预算：`resolveBudgetMs(meta.timeoutMin, PI_WORKER_TIMEOUT_MS)`（src worker-mode.ts:248-253, :3195），task.md `timeout:` 分钟头优先；断言见 1.1（wall 不得先于 tool-idle）与 1.3 I3-c。

### 1.5 trace 行文法（纯断言面，output-writer.ts）

`[FLOW]` :559-565；`[TOOL]` :616-622；`[TOOL_ERR]` :625-631；`[TIMEOUT] ts <idle|wall>: <detail>` :638-640；**`[ERROR] ts <msg>` 已存在**（:706-712，截断首行 160 字符）但仅用于 refusal/收尾异常（worker-mode.ts:2608, :2704, :3762），**模型错误 turn 从不落 `[ERROR]`**；`[END] ts exit=N elapsed=Xs tools=N phases=d/t` :725-734。`[IDLE_KILL]` worker-mode.ts:2435-2450；`[CHECKPOINT]` worker-mode.ts:3264-3293，行格式由 `shared/heartbeat.ts` `readTaskProgress`/`CHECKPOINT_LINE_RE` 镜像解析（output-writer.ts:567-570 keep-in-sync 注释）——**新证据行必须同步两处，均可纯函数断言**。

## 2. faux provider 能力判定

锚点勘误：faux 在 `packages/ai/src/providers/faux.ts`（卡片写的 `packages/ai/src/faux.ts` 目录少一层；行号 114 正确）。

- **可注入 `stopReason:"error"` + `errorMessage:"HTTP 500"`：是，零改动。** `fauxAssistantMessage(content, { stopReason, errorMessage })`（faux.ts:76-92，`FauxResponseStep = AssistantMessage | FauxResponseFactory` :107-114）；`streamWithDeltas` 对 error/aborted 推 `{type:"error", reason, error}` 终态事件并 end（:426-430）。既有用例：packages/ai/test/faux-provider.test.ts:438-452（脚本化 error）、:463-501（aborted）、:130-133（队列耗尽→error）。
- **连续 N 个 error turn：是，三条路。**
  1. 显式队列 `setResponses([err, err, ..., ok])`（session 层先例 agent-session-retry-events.test.ts:38-42）；
  2. `FauxResponseFactory` 每次调用返回 error 消息（faux.ts:107-112），工厂内 throw 也被 catch 转 `createErrorMessage`（:307-316, catch 在 :604-614）；
  3. 队列耗尽 → 每次调用都报 "No more faux responses queued" error（:510-521）——**无限 500 捷径**，但 errorMessage 固定；断言需要精确 "HTTP 500" 文本时用路 1/2。
- **流中断（mid-stream cut）：faux 本体无注入钩子**（中断仅经 signal → `stopReason:"aborted"` 全量分支）。既有模式是自定义 `streamFn` + `EventStream` 子类手工 push `{type:"error", reason:"error", error}`：test/agent-session-retry.test.ts:19-27, :47-66；regressions/6647 同型。`RegisterFauxProviderOptions.tokensPerSecond` 可做慢流。**对本 key 而言 errorMessage 级注入已足够**：重试分类基于 errorMessage 字符串（packages/ai/src/utils/retry.ts:27-34，`"500"|"502"|"503"|"504"|"524"|overloaded|...`；非重试 :8-25 quota/billing），只有 AC 明确要求 mid-stream 掉线时才需要自定义 streamFn。
- **Harness 集成**：`test/suite/harness.ts` `createHarness`（:98-222）→ `registerFauxProvider`（:103-106）+ `harness.setResponses`（:209）+ `settings: { retry: { enabled, maxRetries, baseDelayMs } }`（HarnessOptions.settings :65 → `SettingsManager.inMemory` :113；retry 用法先例 agent-session-retry-events.test.ts:34）。worker-mode 挂进真实管线走 `extensionFactories`（checkpoint-wiring :366-373 先例）。
- **缺口（即新特性目标）**：worker-mode 对 `message_end` 只 `touch()`（worker-mode.ts:3043），对 `agent_end` 只抓最后 assistant 文本（:3139-3152）；**无错误 turn 计数、无模型错误证据行、无 fail-fast**。持续 500 现状：session 自动重试耗尽 → `agent_end(willRetry=false)` → worker 走普通 `recordEnd`（exit 按 product 判 0/1/2），或被 idle/wall 看门狗误标。`[ERROR]` writer 在手（output-writer.ts:706），复用即可。

## 3. packages/ai 层重试覆盖（已有，不重复）

- `packages/ai/test/retry.test.ts`：`isRetryableAssistantError` 分类全覆盖（显式 retry 指引、Bun socket drop、DNS 簇 :37-43、Responses early-EOF、overloaded、524、500 族；非重试 quota/429-limit）；`retryAssistantCall` 策略全覆盖（立即成功、aborted 不重试、非重试不重试、maxRetries 耗尽返回终错、成功即停、policy disabled、onRetryScheduled 事件、signal 中止 backoff）。
- `packages/ai/test/provider-retry.test.ts`：`retryProviderRequest`（429+retry-after-ms 假时钟、`x-should-retry:false`、retry-after 上限、上限豁免、中止）。
- Session 环路：`test/suite/agent-session-retry-events.test.ts`（faux 注入 error turn；`auto_retry_start/end`、`agent_end.willRetry`、maxRetries=2 三错耗尽 `end:false`、非重试单发、`abortRetry`、重试恢复后 tool 调用等待）+ `test/agent-session-retry.test.ts`（自定义 streamFn；`finish_reason: network_error`）；回归：3317（network connection lost）、6904（DNS，setResponses 注入）、6647（compaction 流断）、6019、7572。
- **判定：ai 层分类/退避/事件面已闭环。新 key 测试只测 worker-mode 感知层（计数、阈值、fail-fast、落盘证据），消费到达 worker 的 `stopReason/errorMessage`，绝不重测 `isRetryableAssistantError`。**

## 4. 注入方案建议与结论→决策映射

### 落点

- 新文件 `packages/coding-agent/test/suite/worker-model-error-perception.test.ts`（AGENTS.md：suite 目录用 harness.ts + faux provider；全部 mw* 测试集中于 test/suite/）。单测命令（包根）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-model-error-perception.test.ts`。

### 「连续 N 个 error turn」注入

1. **管线级（首选集成断言）**：`createHarness({ extensionFactories: [async (pi) => { await workerModeActivate(pi); }], settings: { retry: { enabled: true, maxRetries: 2, baseDelayMs: 1 } } })` + `setResponses([fauxAssistantMessage("", { stopReason: "error", errorMessage: "HTTP 500" }) × 3])` —— session 吸收 2 次，第 3 次 `agent_end(willRetry=false)` 到达 worker-mode → 断言 fail-fast + trace 证据 + output.md/run.json 标记 + exit 码。混合序列用同法拼：`[err,err,ok]`（重试吸收后继续，不 fail-fast）、非重试（`errorMessage:"invalid_api_key"`）单发立即 fail-fast。**用真 timers（baseDelayMs:1），勿与 vi.useFakeTimers 混用于 session.prompt**（agent-session-retry-events 先例）。
2. **看门狗时序级（确定性计数）**：worker-idle-heartbeat 的 fakePi 形状——合成 `{role:"assistant", stopReason:"error", errorMessage:"HTTP 500"}` 消息经 `pi.emit("message_end"/"agent_end", ...)` 驱动阈值计数，fake timers 下无退避抖动；断言跨阈值 `process.exit(1)` + 证据行。
3. **队列耗尽捷径**（烟雾用）：`setResponses([])` 后 faux 对每次调用回 "No more faux responses queued" error——无限错误源，但断言不得绑定该 errorMessage 文本。
4. **真流断**：仅当 AC 要求 mid-stream 掉线时，采用 test/agent-session-retry.test.ts:47-66 的自定义 streamFn + EventStream 子类模式（faux 不覆盖此形态）。

### 只能/宜做纯函数级的断言

- 新阈值解析函数（env 覆盖 > 默认，仿 `resolveIdleMs` worker-mode.ts:256-260 形状）：默认值、env 覆盖、非法值回退。
- 新证据行格式：复用 `appendError`/新 `[ERROR]` 族行——截断 160 首行（output-writer.ts:706-712）；`shared/heartbeat.ts` 侧新解析 regex 用手写 trace.log 驱动（mwoc-w4 CHECKPOINT_LINE_RE :231-273 模式），两处 keep-in-sync 各自锁定。
- 计数策略纯逻辑：非错误 turn 重置计数、达到 N 才触发、不会误伤正常 turn。
- **不重测**：ai 层 `isRetryableAssistantError`、provider 429 语义、session `auto_retry_*` 事件序（§3 已覆盖）。

### 集成级断言（必须走真实管线）

trace.log 出现模型错误证据行且在 `[END]` 之前；`[END] exit=` 与 run.json status 与 output.md Exit Reason 三处一致（recordEnd 单点映射 worker-mode.ts:3154-3180 的既有不变量延伸）；瞬时错误（被重试吸收）后 worker 继续、不落证据行。

### 约束与已知坑

- worker-mode 每次激活挂 process-exit 钩子 → 同文件多激活需 `process.setMaxListeners(50)`（checkpoint-wiring/mwoc-w4 头注先例）。
- 不碰真实 provider API（AGENTS.md 硬约束）；不起新子进程（tree-kill-live 除外），规避 Windows 76-test 环境噪声基线。
- 涉 mtime 的断言用 T-12 钳制手法（mwoc-w4 :161-176），NTFS 粒度。
- `[ERROR]` writer 已存在，勿新造平行行格式；证据行设计需同时给出 heartbeat.ts 镜像 regex 的更新点。
