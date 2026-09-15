# Spec: mw-dispatch-flow-fixes

> Key: mw-dispatch-flow-fixes
> 创建时间: 2026-09-07
> 状态: locked（2026-09-07 20:43 用户确认，AC 锁定；七项决策全落定）
> 来源：goal-autopilot key 的 worker 流程测试（ga-spec-review-1 运行）发现的缺陷，用户确认立 key修复；缺陷④（docs-gate 噪音/播报泛滥）为澄清第二轮并入

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（存量格式，三段有真内容，视为已确立）

- 对齐：本 spec 服务于 goal「文件驱动的去中心化协调」的可靠性——派发归属正确、进度可观测、默认路由无凭证依赖，是 mw 多 worker 协作的底层正确性
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心——全部经 Extension API
  - GC-2: 文件锁并发控制——新增的状态/日志写入遵循既有锁协议
  - GC-3: Worker 进程级隔离——心跳机制不得引入跨 worker 通信
  - GC-4: 30 分钟看门狗保留——心跳是其补充（更早发现挂起），不替代
- 冲突：无
- 预期收益：dispatch 归属错位归零（task.md 全部落在正确 key 名下）；worker 挂起可在分钟级（而非 30 分钟）被发现；review/research 任务默认路由 pi/timi 无需人工干预；docs-gate 噪音归零（全终态 key 不再每 session 告警）且窗口播报单通道化。判定方式：本 key done 后跑一次与 ga-spec-review-1 同规格的 review 派发（三项全部符合）+ 新开窗口不出现旧 key 的 docs-gate 告警

## §1 功能概述

### 1.1 目标

修复 mw worker 派发流程的四个缺陷：① dispatch_worker 的 owner key 解析与窗口激活 key 不同步（watch 状态陈旧时任务落错目录）；② worker 执行期无进度心跳（长 LLM 生成期间无活性信号，trace 仅在 tool_call 时写入）；③ `type: review|research` 被硬路由到 claude（pickWorkerRoute 内容匹配，不感知凭证），无 claude 凭证环境即 spawn 失败——ga-spec-review-1 靠人工改派 pi 才完成；④ docs-gate 告警无窗口作用域与重复触发——对名下任务全部已入队的 key 也评估告警（每新 session 重复），且任何 key 的告警广播到每个窗口（与窗口认领 key 无关；worker 终态摘要已按 watch key 过滤，gate 告警未对齐该语义）。缺陷③修复方案为全局默认 pi，缺陷④修复方案 = gate 收敛 + 播报按窗口认领 key 过滤（均见 §4 与调研留底）。

### 1.2 技术栈 / 语言

TypeScript（agent-team-loop extension：dispatch key 解析、心跳写入、默认路由修改）；Python 侧预计零改动（全局默认 pi 为静态决策，mw_common 检测能力不新增不重复）

### 1.3 核心用户场景

1. PM 窗口激活 key K 后 dispatch worker → task.md 落在 `{K}/workers/{task-key}/`，与窗口状态一致
2. worker 长时间生成回复期间，监控方（PM 会话/未来 conductor）能从结构化日志区分"在工作"与"疑似挂起"
3. 派发 `type: review` 任务（未显式指定 cli）→ 默认路由 pi/timi，无论 claude 凭证是否存在均无需人工干预；确需 claude 时显式传 cli=claude，凭证缺失则按既有隔离语义失败并留原因（可观测，不静默）
4. 新开 pi 窗口：mw 播报仅覆盖本窗口认领 key 的相关 worker 事件（终态摘要、该 key 的 docs-gate 告警）；名下任务全部已入队的 key 不再触发 gate 告警；非本窗口认领 key 的事件不在此窗口播报

### 1.4 范围说明（不做什么）

- 不改 30 分钟看门狗语义（心跳只做早期发现）
- 不做多 worker 间通信（GC-3）
- 不改 `type: codex → codex` 的内容路由（显式类型语义：type: codex 表示任务须用 codex 执行；缺凭证沿用 mw-dispatch-reliability 隔离语义 failed）
- 不做 claude 凭证配置本身（那是环境问题，本 key 只改默认路由语义）
- 不含 goal-autopilot 的 conductor/时间线设计（那是另一个 key 的范围）

## §2 业务约束

### 2.1 平台 / 环境

Windows + Unix 跨平台；extension 内改动需保持 build 产物单文件 bundle 约定

### 2.2 性能指标

- 心跳条目间隔 ≤ 60s（worker 存活期间）
- 活性判定阈值与心跳间隔解耦（可配置，默认 90s）
- 路由决策保持静态：派发路径不引入可用性检测调用/轮询，派发延迟不增加

### 2.3 安全约束

心跳/状态文件写入遵循既有文件锁协议；不写入敏感信息（凭证、完整 prompt 内容）

### 2.4 集成依赖

- 与 mw-dispatch-reliability key 的复用边界（用户已确认）：路由可用性检测唯一来源 = `mw_common.py`（route_precheck / resolve_credential），本 key 不新增第二套检测；全局默认 pi 方案下默认路由是静态决策、无运行时可用性判定链，显式路由缺凭证沿用其 D-001 per-task failed 语义（本 key 不得破坏，AC-009 为回归保护）（调研：evidence/research/spec-routing-decisions-2026-09-07.md）
- dispatch_worker 工具注册处：`pm/ui-bridge.ts`（registerWorkerTools）
- trace 写入：`worker/output-writer.ts`
- docs gate 与播报：`pm/pm-orchestrator.ts` dispatchNewTasks（gate 评估顺序、warnedKeys）+ displaySummary 调用点（调研：evidence/research/spec-docgate-summary-2026-09-07.md）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-07T20:43:55+08:00，编号永不回收
> 追加 @ 2026-09-07 设计审核轮（用户提出 PM 侧 monitor 消费面）：AC-012/013，编号顺延

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在窗口激活 key 为 K 的条件下（激活信号按 D-001 解析链：`_index.parallel` 最新 active 行；其全 idle 时降级读 `_index.md` active = K；或经 /pm-key switch / switch_key / phase-doc 写入触发的 auto-takeover 认领 K），经该窗口 dispatch_worker 派发的任何 task.md 路径为 `{K}/workers/{task-key}/task.md`（当前缺陷：session 恢复后 watch 陈旧时落到旧 key 名下，实例 ga-spec-review-1 落在 agent-team-loop）。[REVISED @ 2026-09-08 L2 评审轮：原括注把「_index.md active = K」列为独立充分条件，宽于 D-001 链（parallel 最新 active 优先于 _index.md）；改为按解析链表述，语义不变] |
| AC-002 | 在窗口 watch 状态与激活 key 不一致（session 恢复、异常序）的条件下，派发前完成同步：以激活 key 为准并输出一次告警（时间线/日志留痕），不静默使用陈旧 watch |
| AC-003 | 在 worker 执行期间（含单次 LLM 生成 > 60s 的阶段），结构化进度条目以 ≤ 60s 间隔持续写入（trace.log 或专用 status 文件），条目含时间戳与 task-key，格式机器可解析（如 `[HEARTBEAT] ts=... task=...`） |
| AC-004 | 提供从结构化日志计算活性判定的机制（脚本或命令）：最后一条条目距今超过阈值（默认 90s，可配置）时输出 stale 判定，距今未超时输出 alive |
| AC-005 | 心跳机制不改变既有协议语义：output.md 四节结构、exit code 映射（0/1/2/130）、trace.log 既有 [FLOW]/[GOAL_CHECK] 条目格式均保持不变（additive） |
| AC-006 | 在 ANTHROPIC_API_KEY 与 ANTHROPIC_AUTH_TOKEN 均未设置的环境下，派发 `type: review` 任务（未显式指定 cli，经 dispatch_worker 默认或 dispatchNewTasks 扫描路径）时，launcher spawn 的 CLI 为 pi、provider 为 timi，任务可正常完成——不依赖 claude 凭证存在与否（原 `type→claude` 硬路由移除） |
| AC-007 | 在 claude 路由凭证可用的环境下，显式指定 cli=claude（dispatch_worker 工具参数）派发的任务仍路由 claude 并正常执行；`type: review|research` 字段本身不再触发 claude 路由 |
| AC-008 | 修复后重放同规格 review 派发场景（派发窗口认领 key 名下；原事故实例为 goal-autopilot，回归以有完整 phase docs 的当前认领 key 重放——goal-autopilot 处 SPEC 阶段，其下派发被 docs gate 拦截属正确行为）：task 落在派发窗口认领 key/workers/ 名下、执行期心跳条目持续、`type: review` 任务默认路由 pi/timi 完成且无人工路由干预，三项全部满足。[REVISED @ 2026-09-08：落点由字面 goal-autopilot 改为派发窗口认领 key，用户决策 9；三项断言不变] |
| AC-009 | 在 ANTHROPIC_API_KEY 与 ANTHROPIC_AUTH_TOKEN 均未设置的环境下，显式指定 cli=claude 派发任务时，任务不降级：status=failed、worker.log 包含缺失凭证原因、mw 服务与同批其他任务不受影响（mw-dispatch-reliability D-001 隔离语义回归保护） |
| AC-010 | 在某 key 名下全部 worker 任务均已在队列（workers/ 下无未入队 task.md）的条件下，新 session 的 dispatchNewTasks 扫描不得对该 key 产生 docs-gate 告警；docs-gate 仅对存在 ≥1 个未入队任务且 phase 文档缺失的 key 评估并告警（现状缺陷：agent-team-loop、mw-dispatch-reliability 任务全部终态仍每 session 各告警一次） |
| AC-011 | mw 播报类通知按窗口认领 key 作用域过滤：worker 终态摘要仅播报本窗口认领 key（watch.key）名下的任务（固化现有过滤语义，防回归）；dispatchNewTasks 扫描产生的 docs-gate 告警仅在该 key 为本窗口认领 key 时播报，非认领 key 的 gate 状态不产生播报（无认领 key 的窗口不播 gate 告警；dispatch_worker 工具的同步 blocked 反馈与 mw 服务级播报不受本 AC 影响） |
| AC-012 | 在本窗口认领 key 名下存在 running worker 且其 trace.log 含 [HEARTBEAT] 条目的条件下，watch widget（belowEditor）的该任务行显示心跳派生进度（phase i/n 与最近心跳距今），随 poll 周期（≤5s）刷新；最近心跳距今超过 90s 时该行显示 STALE 标记；无 [HEARTBEAT] 条目的 running 任务显示 no-hb 占位（兼容旧 bundle 任务） |
| AC-013 | 在 worker 进入终态且其 trace.log 含 ≥2 条 [HEARTBEAT] 条目的条件下，终态摘要（worker-summary）附带心跳派生统计：总时长与 phase 完成度（时长为 formatHeartbeatAge 粗粒度桶如 `(6m, ph 3/3)`），无心跳时不附带（保持现状格式） |
| AC-014 | worker 进入终态时，watching 窗口的终态消息自动回读该任务 output.md 全文（上限 20,000 字符，超出截断并附文件路径指路），PM 无需手动读文件即可处理成果；无 output.md 时保持既有 spawn-failure/无输出提示。[APPENDED @ 2026-09-08 评审后用户决策：worker 成果需自动交付到对话（原实现仅回 Summary 节选，需人工触发读全文）] |
| AC-015 | 本窗口 watch key 名下 worker 进入终态（done/failed/needs-clarification）时，终态回读消息以 `triggerTurn: true` 发送（finish call）：PM 空闲时立即触发一次 LLM turn 处理成果并继续 PM 循环（吸收结果→派发下一任务/推进 phase/汇报），PM 流式中按 steer 语义注入当前 turn；消息尾部附带下一步指引文案。非终态/初始化/告警类播报保持被动（不消耗 agent turn）。notified 去重语义不变：每 taskKey 每 session 至多触发一次。[APPENDED @ 2026-09-09 用户缺陷报告 1：终态 summary 仅显示不推进，dispatch→monitor 后中断，需补全 finish call→pm run 环节] |
| AC-016 | worker（pi 路由）执行期 trace.log 含结构化进度与报错，不止测活：`[START]`（task/type/phases）、`[PHASE] start|done i/n [name]`、`[TOOL] <tool> <目标摘要>`（read/write/edit 路径、bash 首行命令、grep/find pattern）、`[TOOL_ERR]`（失败工具首行错误）、`[TIMEOUT]`/`[ERROR]`、`[END] exit= elapsed= tools= phases=`；worker.log 非空：成功路径由 pi print-mode 输出最终回复（成功路径不得在 agent_settled 内 process.exit），失败/超时路径同步写入（fs.writeSync）`[worker]` 状态行；watch widget 运行行显示 `up <elapsed>` 与最近 [TOOL] 动作；终态摘要时长优先取 [START]→[END] 精确区间。既有 [FLOW]/[GOAL_CHECK] 行格式不变（additive），[HEARTBEAT] 行格式不变（时长改由 [START]/[END] 承载）。[APPENDED @ 2026-09-09 用户缺陷报告 2：trace.log 只能测活无中间进度/状态/报错，worker.log 无内容] |

## §4 风险与未决项

- 风险：dispatch key 解析根因未定位（watch 状态来源 vs active 指针读取）——执行窗口先定位再修，AC-001/002 为行为契约
- 风险：心跳写入需要 worker 进程内有定时机制，注意 agent 生成期间 extension 代码是否可执行（若被阻塞，需在 pi runner 层面找挂点，先验证再设计）
- 风险：移除 `review|research→claude` 硬路由是行为变更（非 additive）：既有 vitest 无该映射断言（已核实），但需新增默认 pi 正向断言，并同步 agent-team-loop 侧提及该映射的文档/说明
- 已决（2026-09-07 用户澄清）：路由语义 = 全局默认 pi（弃凭证 fallback 方案）；显式 cli=claude 缺凭证不降级（沿用 D-001）；可用性检测唯一来源 mw_common（调研：evidence/research/spec-routing-decisions-2026-09-07.md）；docs-gate 仅对有未入队任务的 key 评估 + 播报按窗口认领 key 过滤（调研：evidence/research/spec-docgate-summary-2026-09-07.md）。权衡：未认领 key 的 gate 告警无窗口播报面（归属窗口负责；无窗口认领时仅 widget/doctor 可见——接受）；早先"每窗口单一可更新播报面"方案经第三轮澄清弃用（作用域过滤后不再需要，也避开 sendMessage append-only 约束）

## §5 记忆前馈（对接项目级记忆门禁）

> 记忆三件套当前不存在，以仓库实际资产与相邻 key 执行记录如实填写。

### 可复用资产

- `pm/ui-bridge.ts` registerWorkerTools：dispatch_worker 工具注册与 key 参数解析处（修复点 1）
- `worker/output-writer.ts` appendTrace / `worker/phase-runner.ts`：trace 写入与 phase 检查点（心跳挂点）
- mw serve 的 route 可用性预检（mw.log 已输出 route missing/available）：降级判定的现成信号源
- mw-dispatch-reliability D-001 隔离语义及其 L1/L2 回归（VC-001/VC-002、evidence/runs/l2-claude-isolation-rerun.txt）：显式 claude 失败路径的现成行为基准（AC-009）
- mw-dispatch-reliability key 的 per-task 凭证失败隔离设计：路由感知修复的协调对象
- ga-spec-review-1 完整运行样本（task/trace/output/队列行）：AC-008 的回归基准

### 需规避坑点

- worker spawn 凭证失败必须 per-task 隔离，不得拖垮整批派发（mw-dispatch-reliability）
- 管道分隔文件解析 trailing-space/空行处理（agent-team-loop VC-041）
- Windows CRLF/UTF-8 读写不对称（update_index.py P1-1）
- 长生成期间 extension 代码可能无执行机会（本 key 风险清单第 2 条，先验证）
