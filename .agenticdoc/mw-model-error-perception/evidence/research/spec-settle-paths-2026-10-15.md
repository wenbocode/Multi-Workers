# TRQ2 — agent_settled 对 error turn 的盲视：settle 路径全核验（settle paths）

- key：`mw-model-error-perception`；worker：`trq2-settle-paths`；日期：2026-10-15
- 方法：逐行读码（行号为当前工作树实际行号）+ 可运行探针实测（`probe-settle-paths.test.ts`，与本文件同目录，faux provider 全 500，5/5 通过）。
- 说明：卡片「交付格式：唯一证据文件」指本文件为唯一交付物；同目录的 `probe-settle-paths.test.ts` 是复现工具（非交付正文），保留以便修复任务直接复用。

## 结论

PM 预判全部方向性成立，其中两条比预判更严重：

1. **confirm**：`agent_settled` 在重试耗尽后的 error turn 上无条件触发。`_runAgentPrompt` 的 finally 调 `_emitAgentSettled()`（agent-session.ts:**1073**，非预判的 :1081），后者无条件向扩展与公共订阅发 `agent_settled`（:596-604）。session 层自动重试（默认 enabled=true / maxRetries=3 / baseDelayMs=2000，settings-manager.ts:818-824）耗尽后照常 settle。regression `6363-agent-settled-event.test.ts` 已锁此行为。
2. **confirm**：worker-mode 的 `agent_settled` handler（worker-mode.ts:**3707-3777**）不检查最后一条 assistant 消息的 `stopReason`：首 settle 无条件发 `phases[0].prompt`（:3715-3726）；后续 settle 一律按 phase 完成处理（:3730-3757），error settle 会写 phase 文件、记 `[GOAL_CHECK]`、推进 phase 机。
3. **confirm（且强于预判）**：全 phase 耗尽或无 phases 时走 `settleOrSelfCheck()`（:3659，调用点 :3726/:3757）→ `finishSuccess()`（:3535）。write 角色 `evidence.delivered=true` 硬编码（:3547-3549），全 500 时无任何声明、`judgeRecovery=false` → `gaps.ok=true` → **exit 0 / run.json `done`**（:3566），不是预判的「可能 exit 2」——默认结局就是满分 done。Exit Reason 为 `Agent settled after 0 tool call(s). writes=none`，全程无一处提到 500（探针 C-1/C-3 字节级证实）。
4. **confirm（新发现，独立缺陷）**：print mode（`pi -p`，launcher.py:1372-1400 的实际 spawn 形态）下 **phase 机根本跑不过第 1 个 settle**：`session.prompt()` 在首次 settle 后即 resolve（此时 settle-handler 经 `sendUserMessage` 触发的 phase-1 run 仍在飞行，probe A 实测 `isIdle=false`、settles=1）；print mode 随即读最后一条消息（error assistant → OS exit code 1）并 `dispose()` → `agent.abort()` 把 phase-1 run 打成 `aborted`，settle 机冻结在 1，`finishSuccess` 永不执行；进程自然退出时 `process.on("exit")` 安全网（:2736-2757）补写 crash output.md（exit=1、`Process exited before output.md was written`）并 `finishRun("failed", 1)`。worker-mode 无 `session_shutdown` handler，无任何拦截。
5. **confirm**：idle 看门狗被 error 自旋投毒。`turn_end`/`agent_end`（以及 message_start/end、turn_start、agent_start）在**每次 error attempt** 上都触发并 `touch()` 刷新 `lastActivityAt`（:3036-3055；agent-loop.ts:203-209 error 路径保证 turn_end+agent_end；agent.ts:502-520 抛错路径同样合成二者）。probe B：3 个全 500 prompt（maxRetries=1，每 prompt 2 attempts）产生 **6 次 turn_end/agent_end**（生产默认 maxRetries=3 → 每 prompt 4 次）。10 分钟 idle 墙在持续 500 下永不命中；实际兜底是 phase 耗尽（分钟级）而非 60 分钟 wall。
6. **confirm**：`markOutcome`（:2655-2662）与 `recordEnd`（:3156-3185）映射精确为 0=done / 2=needs-clarification / 其他=failed；launcher `_exit_to_status`（launcher.py:409-415）同构，且 reap 为 product-first：run.json 终态优先于 OS exit code，冲突时写 reap-conflict 行到 launcher.log（launcher.py:418-449）。

## 证据

### 1. 预判核验表

| # | 预判 | 结论 | 实际行号/事实 |
|---|------|------|---------------|
| 1 | `_runAgentPrompt` finally 无条件 `_emitAgentSettled()`（agent-session.ts:1081） | confirm（行号修正） | agent-session.ts:1069-1079；finally 内调用在 **:1073**；`_emitAgentSettled` :596-604（先置 `_isAgentRunActive=false` 再 emit） |
| 2 | 重试耗尽后 error turn 仍触发 settle | confirm | `_prepareRetry` :2681-2734（超预算回退并返回 false）→ while 循环退出 → finally settle；`auto_retry_end success=false` :1088-1096；regression #6363 锁定 `agent_settled:1` |
| 3 | worker-mode settle handler 不检查 `stopReason==="error"`（:3707-3776） | confirm | :3707-3777；`turn_end` handler :3045 与 `agent_end` handler :3141-3154 均不读 payload 的 stopReason/errorMessage |
| 4 | 首 settle 无条件发 phases[0].prompt（:3715-3723） | confirm | :3715-3726（:3721 sendUserMessage、:3722 nextPhaseIdx=1） |
| 5 | 后续 settle 一律按 phase 完成（:3729-3760） | confirm | :3730-3757：writePhaseFile :3733、appendGoalCheck :3741、completedPhaseIdx++ :3743、下发下一 phase :3746-3753、耗尽后 settleOrSelfCheck :3757 |
| 6 | 全耗尽走 settleOrSelfCheck（:3646）→ finishSuccess（:3536+） | confirm（行号修正） | settleOrSelfCheck 定义 **:3659**（调用 :3726/:3757）；finishSuccess 定义 **:3535**；exitCode 三元 :3566 |
| 7 | write 角色 `evidence.delivered=true`（:3548-3549） | confirm | :3547-3549；writeless 角色走 `hasDeliverableEvidence`（deliverable-evidence.ts:190-262） |
| 8 | 「可能 exit 2 但 Exit Reason 误导，甚至 exit 0」 | confirm 且加强 | 全 500 的 write 角色默认 **exit 0/done**（无声明 → ledger ok，judgeRecovery=false → 无缺失段）；exit 2 只出现在 writeless 角色（no-product 路径） |
| 9 | error turn 与成功 turn 的可观测差异（:3139-3153） | confirm（差异清单见下节） | agent_end/turn_end payload 均携带 stopReason/errorMessage（agent/types.ts:425-428），worker-mode 不读 |
| 10 | idle 看门狗被 error 自旋投毒（:3045-3049） | confirm | touch 注册 :3036-3055（turn_end :3045）；idle 判定 :3437-3460（双条件 raw-idle + delta-idle，raw 被 turn_end 持续刷新）；probe B 实测每 error attempt 均刷新 |
| 11 | markOutcome（:2655）/ recordEnd（:3156）映射 | confirm | :2655-2662 / :3156-3185；launcher.py:409-415 同构；product-first reap launcher.py:418-449 |

### 2. error turn vs 成功 turn：worker-mode 可观测面全部差异

| 观测点 | 成功 turn | error turn（重试耗尽后） | worker-mode 是否使用 |
|---|---|---|---|
| `turn_end` payload `{message, toolResults}` | message.stopReason 正常、toolResults 为本 turn 结果 | stopReason=`error`、errorMessage 有值、**toolResults=[]**（agent-loop.ts:203-209 直接 return） | 不读（:3045 忽略 payload） |
| `agent_end` payload `{messages, willRetry}` | 末条 assistant stopReason 正常；willRetry=false | 末条 assistant stopReason=`error`、errorMessage 有值；耗尽时 willRetry=false（agent-session.ts:651 注入） | 只扫描 text（:3141-3154），**stopReason/errorMessage/willRetry 全部可用且未读** |
| 末条 assistant content | 含 text | 通常为空（pre-connect 失败由 `handleRunFailure` 合成空 content，agent.ts:502-520） | `lastAssistantText` **保持旧值**（stale）→ phase 文件可能写入上一个 phase 的旧文本（:3733 的 `lastAssistantText \|\| "Phase N complete"`） |
| `message_update` delta | 有 | pre-connect 失败无（合成消息）；mid-stream 失败可能有（faux 实测有，probe B deltas=18） | `touch("delta")`+delta 时钟（:3039-3041） |
| 工具事件 `[TOOL]/[TOOL_ERR]/[WRITE_FILE]` | 有 | 全无 → `tools=0`、ledger 无事件 | trace 只剩 lifecycle 行 |
| usage | 正常 | EMPTY_USAGE（合成消息）→ 上下文 token 走估算路径（agent-session.ts:2027） | 不相关 |
| session 级事件 | — | `auto_retry_start`/`auto_retry_end(success=false)` | 未订阅 |
| print mode stdout/stderr | 最终文本 → stdout（OS exit 0） | `console.error(errorMessage)` → **stderr**，OS exit 1（print-mode.ts:124-135） | worker.log 只重定向 stdout |

### 3. 三类形态端到端结局表（模型全程 500；生产形态 = launcher `pi --provider … -p <starter>` print mode）

| 形态 | 终端 status（run.json/队列） | OS exit code | output.md `## Exit Reason` 实际文本 | trace.log 关键行 | PM 看到什么 |
|---|---|---|---|---|---|
| a) 带 phases（如 coding, N=2） | **failed**（exit-safety-net `finishRun("failed",1)`；`[END]` 缺失） | 1（print mode 读到 error assistant；若 run#2 的 user 消息先落 state 则竞态为 0，probe A 实测为 1） | `Process exited before output.md was written (crash or unexpected exit).`（marker `status=failed`） | `[START] pid`、`[START] … phases=2`、`[MODEL]`、`[PHASE] … start 1/2 build` 之后**无 [END]**（recordEnd 未执行）；stderr 有 `HTTP 500 …` | 队列 failed；output.md 是 crash 块；**没有任何一行指出模型 500**（仅 stderr/launcher 侧可能见到）；phase 机冻结在 1/N |
| b) 无 phases writeless（review/research） | **needs-clarification**（exit=2）+ `no-product` 告警行（recordDispatchAlarm, :3609-3617） | 1（print mode），被 product-first reap 覆盖为 run.json 的 needs-clarification | 不适用（exit=2 走 `## Questions`）：`no-product: no report file and no output text writes=none \| 缺失段：结论、证据、残留与未验证、上下文来源` + `## Recovery Gaps` | `[FLOW] … recovery-gap missing=结论\|证据\|残留与未验证\|上下文来源 selfcheck=pending`、`[END] … exit=2 … tools=0 phases=-` | needs-clarification；但措辞指向「恢复契约缺段/no-product」，**不指向模型故障**；TL;DR/Summary 为兜底文案 "Task completed." |
| c) 无 phases write（coding） | **done**（exit=0） | 1（print mode）→ reap 冲突行进 launcher.log，队列仍取 run.json=done | `Agent settled after 0 tool call(s). writes=none`（marker `status=done`） | `[END] … exit=0 … tools=0 phases=-`；全程无 error/500 字样 | **满分 done**。模型全程不可用被记为成功完成——预判中「最坏结局」即此，且为默认结局 |

探针产物（全部 500、逐 settle）：C-1（phased，逻辑层）`[END] exit=0 tools=0 phases=2/2`、`phase-1.md` 内容 `Phase 1 complete`（兜底文案）、output/trace/run.json 均无 500 字样；C-2（research）如上表 b；C-3（coding）如上表 c；A/B（真实 AgentSession）如结论 4/5。

### 4. print mode 交互事实（probe A/B + 读码）

- `runPrintMode`（print-mode.ts:33-152）：`await session.prompt(initialMessage)` 在**首次 settle 后即 resolve**——settle-handler 里 `pi.sendUserMessage()`（agent-session.ts:2373-2376，fire-and-forget）触发的 phase run 不被等待。probe A 实测 resolve 时 `isIdle=false`、`settles=1`、faux 响应已多消耗 1 条。
- 随后 print mode 读 `state.messages` 末条：error assistant → `console.error(errorMessage)`、`exitCode=1`（print-mode.ts:124-135）；main.ts:918-930 `process.exitCode = exitCode` 后 **自然退出（非 process.exit）**。
- finally 中 `disposeRuntime()` → `session.dispose()` → `agent.abort()`（agent-session.ts:839-857）：probe A 实测在飞的 phase run 被打为 `stopReason="aborted"`，settle 计数冻结在 1，公共事件流断开；若 dispose 时 run#2 尚未进入 `agent.prompt`（`activeRun` 为空，agent.ts:319-321），abort 是 no-op，该 run 会在无人监听下游跑完后随事件循环排空自然退出——两种交错殊途同归：**phase 机截断，终态由 exit-safety-net 兜底为 failed(1)**。
- 对照组（probe B，等待空闲的驱动）：`["task","phase-1 prompt","phase-2 prompt"]` 全部执行、3 次 settle 全部落在 error turn、末条 `stopReason="error"`——session 层 phase 机本身能转，**是 print mode 的生命周期截断了它**。也即：phased 任务在今天的 `pi -p` 生产形态下从未真正多 phase 执行过（`.agenticdoc` 全库无任何 `progress/phase-*.md`/`[PHASE]` 实迹佐证）。
- worker-mode 自身的 `process.exit` 仅出现在：settle handler catch（:3773）、`timeoutExit`（:3251）、image-cap/startup 拒绝（:2706、:2560、:2623）。正常 settle 路径依赖 print mode 自然退出。

### 5. idle 看门狗投毒判定

- touch 面：`message_update/message_start/message_end/turn_start/turn_end/agent_start/tool_*` → `lastActivityAt`（:3036-3055）；`agent_end` handler 额外 `touch("agent_end")`（:3142）。
- error 路径保证 `turn_end`+`agent_end` 触发（agent-loop.ts:203-209、agent.ts:502-520）→ 每次 error attempt（生产默认 4 次/prompt，含 2s/4s/8s backoff）都刷新活动时钟 → `idleTimer`（30s tick，:3437-3460）的 raw-idle 条件永不满足；无在飞工具分支的 delta 二次确认（lastDeltaAt）也不救，因为 raw 条件先不成立。
- 实际终止子：phase 耗尽 → finishSuccess（分钟级）；无 phases → 首次 settle 即终止。60 分钟 wall（DEFAULT_BUDGET_MS=60m，:235/:248-253）只在「phases×cycle 超预算」或 checkpoint/deadline steer（:3412-3435，settle 态下 sendUserMessage 直接开新 run → 更多 error cycle）把循环拉长时才兜底。预判「只能靠 60m wall 或 phase 耗尽兜底」成立，且 phase 耗尽是事实上的主终止子。

### 6. markOutcome / recordEnd 映射核验

- `markOutcome`（:2655-2662）：`0→done, 2→needs-clarification, 其余→failed`；`writeOutputGuarded`（:2642-2648）先 mark 再写 output.md；`finishRun`（:2666-2674）持久化 run.json；`recordEnd`（:3156-3185）统一走这三步并写 `[END] exit= elapsed= tools= phases=` 与 worker.log 状态行。
- launcher 侧 `_exit_to_status`（launcher.py:409-415）同构；`_reap_status`（:418-449）product-first：run.json 终态 > OS exit；分歧写 `[launcher] <key>: reap status conflict run.json=… exit=… used=…` 进 `.mw/launcher.log`。

## 结论→决策映射

1. **fail-fast 应挂在 `agent_end`**：worker-mode 已收到 `event.messages` 与 session 注入的 `willRetry`（agent-session.ts:651）——在 :3141 handler 里记录 `lastStopReason`/`lastErrorMessage`（取末条 assistant）。settle 时刻 `willRetry` 必为 false，故 `agent_settled` 判「error settle」的充分条件就是 `lastStopReason === "error" || "aborted"`。无需新事件。
2. **phase 机区分 error settle**：仅当 `lastStopReason !== "error"/"aborted"` 才允许 writePhaseFile/[GOAL_CHECK]/推进；error settle 应：记 `[MODEL_ERROR] stopReason=… msg=…` trace 行 → 同一 phase 重试上限（K 次后）或立即写失败 output.md（携带 errorMessage）→ `recordEnd(1)` → 终止，不再下发下一 phase、不写 phase 文件、不走 finishSuccess 的成功判定。
3. **无 phases 角色**：error settle 直接失败收尾（携带 errorMessage），跳过基于空/stale 文本的 recovery/no-product 判定（否则出现 "Task completed." 兜底 TL;DR 或误导性缺段清单）。
4. **看门狗**：error 边界事件不计入活动时钟（touch 前查 stopReason），或增加「连续 error settle 计数」预算（N 次即 `timeoutExit("idle","error spin")`），封掉投毒。
5. **print mode/生命周期**：phased 任务在 `pi -p` 下无法越过 phase 1，与 error 无关。修复选项：worker-mode 在 `taskDone` 后自行 `process.exit(exitCode)`（放弃「让 pi 自然退出以保 worker.log 刷新」的前提，需同步处理 stdout flush），或 phase 下发改用 `deliverAs:"followUp"` 前先确认驱动方会等待队列排空；同时消除 OS exit(1) 与 run.json done 的分歧（现靠 product-first reap 掩盖）。

## 残留与未验证

- 生产 provider 层重试计数：`settings.retry.provider.maxRetries` 默认 undefined → `retryProviderRequest` 0 次（packages/ai/src/utils/provider-retry.ts:109），pre-connect 500 直接终局并带 `outerRetryEligible:false` 诊断（retry.ts:219-238）从而跳过 session 重试——完整链路数值归 TRQ1；timi 代理路由的错误文案分类未验证。
- probe A 中 print mode 读到哪条消息属竞态（实测读到 error assistant → exit 1）；真实 provider 的 preflight（auth 检查）更慢，error-read 概率更高，但未在生产二进制下复测。
- faux provider 的 error 流会产生 `message_update`（probe B deltas=18）；真实 provider pre-connect 失败无 delta。投毒结论不依赖 delta（边界事件必然刷新 raw 时钟）。
- phase 文件 stale-text 隐患（phase N 落盘 phase N-1 的旧回复）由代码推导（:3141-3154 + :3733），未端到端复现（全 500 场景无可 stale 的成功文本）。
- `.agenticdoc` 全库无 phased 实迹（无 `progress/phase-*.md`、无 `[PHASE]` 行）：phased 截断缺陷属「代码+探针」级结论，未经生产 run 佐证。
- print mode 的 stderr（`HTTP 500 …` 行）最终落在 worker.log 还是 launcher 侧文件未验证。

## 上下文来源

- 任务卡：`tasks/TRQ2-settle-paths.md`（sha256 `00ff6f28d573149835a55b95f00ad5f6e0b66673b3a67800b526198fd3c0cf60`）
- 读取来源（行号为 2026-10-15 工作树）：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`：:235-293（默认 60m/10m/锚点/steer）、:2373 附近 sendUserMessage ctx、:2642-2674（writeOutputGuarded/markOutcome/finishRun）、:2685-2757（session_start/exit 安全网）、:3036-3055（touch 面）、:3141-3154（agent_end handler）、:3156-3185（recordEnd）、:3226-3251（timeoutExit）、:3363-3410（checkpoint/steer）、:3437-3466（idle/wall timer）、:3470-3476（phase 状态）、:3530-3646（finishSuccess）、:3659-3705（settleOrSelfCheck）、:3707-3777（agent_settled handler）
  - `packages/coding-agent/src/core/agent-session.ts`：:315、:587-604（idle/_emitAgentSettled）、:640-698（_handleAgentEvent/willRetry）、:839-857（dispose）、:878-884（isStreaming/isIdle）、:1069-1106（_runAgentPrompt/_handlePostAgentRun）、:1480-1511（sendUserMessage）、:2010-2060（_checkCompaction error 分支）、:2373-2376（ctx sendUserMessage fire-and-forget）、:2640-2734（_isRetryableError/_prepareRetry）
  - `packages/coding-agent/src/core/settings-manager.ts`：:29-34、:818-845（retry 默认 3/2000ms、provider retry 默认 0）
  - `packages/coding-agent/src/core/sdk.ts`：:302-333（streamFn 的 provider maxRetries 传递）
  - `packages/coding-agent/src/main.ts`：:918-930（print mode exitCode → process.exitCode）
  - `packages/coding-agent/src/modes/print-mode.ts`：:33-152（runPrintMode 全流程）
  - `packages/agent/src/agent.ts`：:344-350、:482-528（runWithLifecycle/finishRun/handleRunFailure）、:319-330（abort/waitForIdle）
  - `packages/agent/src/agent-loop.ts`：:120-235（runLoop error 路径 turn_end+agent_end+return）
  - `packages/agent/src/types.ts`：:422-431（agent_end/turn_end payload）
  - `packages/ai/src/utils/retry.ts`：:7-66、:91-103、:162-239（可重试分类/边界诊断/retryAssistantCall）
  - `packages/ai/src/utils/provider-retry.ts`：:97-125（pre-connect 重试，默认 0）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`：:357-427（readTerminalGaps）、:443-522（writeOutput 段落模板/Exit Reason/Questions）、:602-640（[START]/[MODEL]/[PHASE]）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/phase-runner.ts`（全文件，phase 文件落点 `<taskKey>/progress/phase-N.md`）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/deliverable-evidence.ts`（全文件，三通道判定）
  - `packages/multi-workers/launcher.py`：:409-449（_exit_to_status/_reap_status）、:1372-1400（spawn 形态 `pi … -p`）
  - 测试：`test/suite/regressions/6363-agent-settled-event.test.ts`、`test/suite/harness.ts`、`test/suite/agent-session-retry-events.test.ts`、`test/suite/dual-root-worker.test.ts`（FakeWorkerPi 形态）
  - 实测：`evidence/research/probe-settle-paths.test.ts`（vitest 5/5 通过，输出全文见测试日志：C-1/C-2/C-3 trace+output+run.json、probe A atResolve/afterDispose、probe B 事件计数）
