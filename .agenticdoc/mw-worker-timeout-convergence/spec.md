# Spec: mw-worker-timeout-convergence

> status: active
> created: 2026-09-09
> 需求来源：用户报告 worker 超时假死（OverCode certify-parsed-reuse 4 个超时 worker 取证，见 research/overcode-timeout-forensics-2026-09-09.md）+ 两轮对话设计确认（方案 B+A+C + 收敛检查点，用户拍板"按推荐"）。

## §0 Goal Alignment

> [APPENDED @ 2026-09-09 恢复复验轮：goal.md 已确立，补齐 Step 0 软门禁要求的目标对齐节；内容自本 key 需求来源与 goal.md 修订记录追溯，AC 集合不变（AC-001~006）]

- **对齐**：goal.md「核心交付」的 Worker 进程级隔离——看门狗保证单个 worker 挂死/超预算不拖垮整体协作；「解决单 Agent 长上下文溢出」的前提是 worker 能被可靠地终结与收敛
- **GC 继承**：本 key 即 goal.md Key Constraints 中 watchdog 语义行（2026-09-09 修订）的落地本体：activity watchdog（无活动 10m 判真挂死，PI_WORKER_IDLE_MS 可调）+ 墙钟兜底（默认 60m，task.md `timeout:` 分钟头 > PI_WORKER_TIMEOUT_MS > 默认）+ 30 分钟收敛检查点（[CHECKPOINT] 机器判据 + worker 自评，mid/high 经 triggerTurn 升级 PM 主窗口）+ deadline steer
- **冲突**：无。全部实现位于 agent-team-loop 扩展内（不修改 pi 核心）；[CHECKPOINT]/新 [TIMEOUT] 走既有 trace.log（文件驱动协调，无中心化调度器）；Python/launcher/队列协议零改动
- **预期收益**：消灭「健康任务被误杀」（OverCode cpr-004/005）与「真挂死占用资源至预算耗尽」（cpr-003/007）两类损失；发散任务在 30m 检查点被 PM 主动收敛（继续/收窄/分拆/直执）而非被动等死；[TIMEOUT] 携带判据使误杀可归因

## §1 背景

现行 watchdog（worker-mode.ts）是纯墙钟：任务起点 setTimeout(30m)，agent_settled 未到即强杀。它同时承担"预算控制"与"挂死检测"两个职责，对两者都不合格：

- 预算不足的健康任务被杀（OverCode cpr-004：被杀前 28 秒还在干活；cpr-005：死在收尾验证）
- 慢生成在途被杀（cpr-003：生成最终报告时被杀；cpr-007：~300 行实现生成在途被杀）
- 且与真 network hang 不可区分（心跳只证明事件循环活着）

关键未用信号：pi 扩展 API 的 `message_update` 事件（token 级流式增量）——增量在流 = 调用活着；无增量 = 真挂死。

## §2 需求（AC）

- **AC-001 activity watchdog**：worker 以"无任何活动"（message_update / message_start|end / tool_execution_* / turn_* / agent_* 事件）持续超过 idle 阈值（默认 10m，PI_WORKER_IDLE_MS 可调）且未 settle 判定真挂死；[TIMEOUT] 行记录判据（最近 delta/tool 距今秒数），output.md exitReason 同步携带
- **AC-002 per-task 预算**：task.md `timeout:` 头（分钟）> PI_WORKER_TIMEOUT_MS 环境变量 > 默认 60m 墙钟兜底；worker 自读 task.md，零队列/launcher/Python 协议改动
- **AC-003 deadline steer**：预算临近（budget - min(5m, budget/4)）仍未 settle 时，worker 侧注入收尾指令：停止新工作、写 output.md（已完成/未完成/后续建议）——成果由 agent 自己落盘，不依赖 exit 安全网
- **AC-004 收敛检查点与 PM 升级**：min(30m, budget/2) 未 settle 时写 `[CHECKPOINT]` 行（elapsed、reads/writes、phases done/total、uniq 写目标、重复读 top、risk 分级），并 steer worker 向 progress.md 追加自评（`CKPT <m>m converging=yes|no eta≈<m>m`）；此后每 10m 刷新直至 settle。risk 启发式（advisory）：high = 30m+ 零写纯读；mid = 有 phase 框架但 0 完成或同目标重复读 ≥4；low = 其余。PM poll 循环发现 running 行首个 mid/high checkpoint → triggerTurn 唤醒 PM 主窗口，消息带机器证据 + trace/progress 路径 + 判断指令（继续等待 / steer 收窄 / 杀掉分拆重派 / PM 直执）；low 只进 widget 与日志不打扰
- **AC-005 widget 检查点徽标**：watch widget 运行行在有 checkpoint 后显示 `ck<m>m <risk>` 徽标（risk!=low 加警示符）
- **AC-006 兼容性**：[FLOW]/[GOAL_CHECK]/[HEARTBEAT] 格式不变；[START]/[END]/[TOOL] 等既有行不变；[CHECKPOINT]/新 [TIMEOUT] 为纯增量；Python 侧零改动（doctor 只解析 HEARTBEAT 前缀锚定行）；PI_WORKER_TIMEOUT_MS 语义保留（从"唯一墙钟"降级为"全局默认预算"）

## §3 验收基线

OverCode 四案例映射：cpr-004 → AC-002 预算；cpr-005 → AC-003 steer；cpr-003 → AC-003 + AC-001（不误杀滴流中的长生成）；cpr-007 → AC-002 + AC-001 + AC-004（high risk 升级 PM 分拆判断）。

## §4 决策记录

- D-2026-09-09-1（用户）：方案 B+A+C 全采纳；GC-4 修订为 "activity watchdog（idle 10m 判真挂死）+ 墙钟兜底默认 60m + per-task 可调"
- D-2026-09-09-2（用户）：超 30m 必须有执行日志收敛判据；发散任务可能要分拆，由 PM 主窗口结合最全上下文判断风险
- D-2026-09-09-3（设计）：idle 阈值取 10m（保守于已观测 7m 合法单次长调用；确认 timi 路径流式后可收紧）
- D-2026-09-09-4（设计）：检查点时刻 = min(30m, budget/2)（60m 默认预算下锚定用户要求的 30m；小预算下按比例提前，可被烟雾测试覆盖）
- D-2026-09-09-5（设计）：超时不引入新终态/exit code——PM readback 已携带 output.md Exit Reason 全文，重试策略走提示词层（PM_CONTINUE_HINT 补充超时→双倍预算重试一次→再失败转 PM 直执）

## 可复用资产

> [APPENDED @ 2026-09-09 恢复复验轮，前馈门禁对齐；条目来自质检轮已验证的实现]

- `heartbeat.ts` 的 `readTaskProgress` / `[CHECKPOINT]` 末行解析——后续 trace.log 行扩展的解析范式
- `output-writer.ts` 的 `appendCheckpoint` / `appendTimeout(kind, detail)`——结构化生命周期行的写入范式
- `workerModeActivate` 集成测试模式（`process.exit` spy + fake timers + 扩展事件 emit）——closure 内计时器逻辑的唯一有效测试法
- `computeRisk` 启发式与 `resolveBudgetMs` / `parseTaskMd` timeout 头——其它 worker 策略（重试、预算分配）可直接复用

## 需规避坑点

> [APPENDED @ 2026-09-09 恢复复验轮，前馈门禁对齐；条目来自 achieved.md「学到了什么」与实跑记录]

- `pi.sendUserMessage` 在 agent 运行中（流式/工具执行中）必须带 `deliverAs`（steer/followUp），否则报 "Agent is already processing"；两档语义：checkpoint=followUp 不打断在途工作，deadline=steer 紧急注入
- closure 内的 idle interval 判定逻辑组件级单测测不到，必须走 `workerModeActivate` 集成测试
- 机器 risk 判据（零写纯读=high）对非编码任务（如纯 sleep）会误报——定位 advisory，决断权在 PM 主窗口
- stale built-in 扩展副本（未重建的 dist）会以 `exitWithSuccess` 抢杀 print-mode 进程——扩展行为实机验证前先确认 dist/bundle 已重建（见 mw-stale-builtin-fix archived key）
