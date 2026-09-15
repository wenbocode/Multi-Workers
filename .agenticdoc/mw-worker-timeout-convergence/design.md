# Design: mw-worker-timeout-convergence

> 对应 spec AC-001~AC-006。改动全部在 agent-team-loop 扩展（GC-1），Python/launcher/队列协议零改动（AC-006）。

## D-001 预算与阈值解析（AC-002）

```
budgetMs = task.md `timeout:`（分钟）× 60_000
         ?? Number(PI_WORKER_TIMEOUT_MS)
         ?? 60 * 60_000            // 新默认（原 30m）
idleMs   = Number(PI_WORKER_IDLE_MS) ?? 10 * 60_000
checkpointAtMs = min(30m, budgetMs / 2)
steerAtMs      = budgetMs - min(5m, budgetMs / 4)
```

- parseTaskMd 增加 `timeout` 头解析（与 `type:`/`model:` 同风格，首个匹配的 `timeout: <int>` 行，≤0 忽略）
- 60m 默认下 checkpointAt=30m（用户锚点）、steerAt=55m；2m 烟雾预算下 checkpointAt=1m、steerAt=1.5m——路径全部可被小预算实跑覆盖

## D-002 activity watchdog（AC-001）

- `lastActivityAt` 由全部生命周期事件刷新：`message_update`（token 增量，判别器）、`message_start`、`message_end`、`tool_execution_start/update/end`、`turn_start/end`、`agent_start/end`
- `idleTimer` = setInterval(30s, unref)：`!settled && now-lastActivity > idleMs` → 走超时路径，reason=`idle: no activity for <N>s (last delta <a>s ago, last tool <b>s ago)`（delta/tool 时间戳分别记录）
- `wallTimer` = setTimeout(budgetMs, unref)：reason=`wall: budget <N>s exceeded (last activity <a>s ago)`——墙钟退居兜底，被它杀到说明预算真的不够（PM 侧按 Exit Reason 决定加预算重试）
- settle 时全部清除；已 settle 后各回调自守卫直接 return
- 非流式 provider 退化：message_update 不来 → inter-turn 间隙计入 idle——10m 阈值覆盖已观测 7m 合法长调用（D-2026-09-09-3）

## D-003 收敛检查点（AC-004）

信号采集（worker-mode 内已有计数器扩展）：
- `toolCounts: Map<name, n>`（reads = read+grep+find+ls+glob 计数和；writes = write+edit 计数和）
- `writeTargets: Set<path>`（唯一写目标）；`readCounts: Map<path, n>`（重复读 top）
- phases done/total：checkpoint 时调 readTaskProgress(taskDir)（复用 [PHASE] 解析，不重造）

risk 启发式（纯机器判据，advisory——PM 才是决断者）：
```
high: writes === 0 && elapsed >= 30m          // cpr-007 模式：纯探索零产出
mid:  (phasesTotal > 0 && phasesDone === 0 && elapsed >= 30m)
   || repeatTop >= 4                           // phase 框架未动 / 原地打转
low:  其余                                     // 写入在推进
```

落盘与播报：
- `[CHECKPOINT] <ts> elapsed=<s> tools=<n> reads=<n> writes=<n> phases=<d>/<t> uniq_targets=<n> repeat_top=<k> risk=<low|mid|high>`（appendCheckpoint，output-writer）
- steer worker：`sendMessage(..., {triggerTurn:true})` → "检查点：自评收敛性，把一行 `CKPT <m>m converging=yes|no eta≈<m>m <理由>` 追加到 <taskDir>/progress.md；不收敛则立即收窄范围"
- 每 10m 重复（直至 settle），每次全量重算

## D-004 PM 升级通道（AC-004/005）

- ui-bridge：`deliverPmAlert(pi, text)` = sendMessage + triggerTurn（deliverWorkerResult 改为调用它；语义同"finish call"）
- poll 循环：running 行读 readTaskProgress → 有 checkpoint 时 widget 运行行加 `ck<m>m[⚠]<risk>`；`escalated: Set<taskKey>` 内存去重，首个 mid/high → deliverPmAlert（证据 + trace/progress 路径 + 判断指令四选一：继续等待/steer 收窄/杀掉分拆重派/PM 直执）
- 终态 readback（PM_CONTINUE_HINT）追加超时分支：Exit Reason 含超时 → 双倍预算重试一次 → 再失败转 PM 直执（提示词层，无新协议）
- heartbeat.ts：readTaskProgress 增量解析 [CHECKPOINT]（取最后一行），TaskProgress 增 `checkpoint` 字段；旧 bundle trace 无此行 → undefined，优雅降级

## D-005 超时输出（AC-001/006）

- appendTimeout 签名扩展：`appendTimeout(key, root, kind: "idle"|"wall", detail)`；行格式 `[TIMEOUT] <ts> <kind>: <detail>`
- output.md exitReason 携带 kind + detail + 最后一次 checkpoint 摘要（risk/reads/writes）——PM readback 全文可见
- 旧格式 `no agent_settled within <s>s` 不再产出（[FLOW]/[GOAL_CHECK]/[HEARTBEAT] 不受影响；Python 零解析依赖）

## D-006 测试面（vitest，agent-team-loop.test.ts）

预算解析优先级；idle/wall 触发与互斥（fake timers + 模拟事件 touch）；delta 滴流不误杀；checkpoint 信号计算三分支；appendCheckpoint/readTaskProgress 行往返；steer 文案与触发时刻；PM 升级（fake pi 捕获 triggerTurn、mid/high 一次 low 不打扰）；widget 徽标；既有 73 用例零回归。
