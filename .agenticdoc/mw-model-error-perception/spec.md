# Spec: mw-model-error-perception
> **实现期修订索引（2026-10-15，D3 进程级化）**：涉及「followUp 重发」「worker 侧 N=2 连续计数 / PI_WORKER_MODEL_ERR_MAX 为 worker 预算」的段落为 pre-D3 历史文本，一律以 design §2 决策 D3 的修订记录为准（worker 首个 error settle 直接 exit 3，`[MODEL_ERR] run=1`；预算与 `[MODEL_RETRY]` 计数在 launcher；挂起型 idle 击杀改判 exit 3）。AC-002 的「连续失败计数」按此读作 run=1。


> Key: mw-model-error-perception
> 创建时间: 2026-10-15
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「Agent Team 协作框架」中 Worker 执行可靠性一环——goal 已有「Worker 超时看门狗（activity watchdog + 墙钟兜底 + 收敛检查点）」约束，本 key 补齐其盲区：模型层故障（HTTP 5xx / 连接受限 / 流中断）造成的伪成功、僵尸自旋与不可归因死亡。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心，全部通过 Extension API（worker-mode.ts 扩展侧实现）
  - GC-2: 文件驱动协调，证据落 trace.log / worker.log / output.md，不新增中心化组件
  - GC-3: 看门狗语义延续 mw-worker-timeout-convergence（idle/wall/证据行格式），只补盲区不改既有契约
- 冲突：无。
- 预期收益：模型故障时 worker 快速失败（默认 retry 预算下 < 15 分钟，目标值待 RQ-1 修正）且 PM 可从 Exit Reason / trace 直接归因「model unavailable: <错误文本>」；消灭「模型全挂却 exit=0/done 伪成功」与「连续重派 12 次无人察觉」两类历史事故（判定方式：AC-001~AC-007 全过 + faux provider 注入测试）。

## §1 功能概述

### 1.1 目标

让 worker 进程对模型层故障具备感知与分级降级能力：连续 error agent run 达到阈值即**切换备用模型**（按任务类别配置的 fallback 数组，会话内热切换）；所有备用耗尽才熔断退出并留下机器可读证据；error turn 不得推进 phase 机、不得伪成功；中间产物在降级/熔断全程保留可读；PM 侧能从终态产物直接读到模型故障根因与已试模型链，并能感知「同 key 反复 model-error 终结」的重派回路。

### 1.2 技术栈 / 语言

TypeScript（pi 扩展 `packages/coding-agent/src/extensions/agent-team-loop/worker/`；PM 侧告警消费）；测试 vitest + faux provider（禁真实 API）。

### 1.3 核心用户场景

1. 场景 A：PM 派发 worker 后主模型持续 500/连接拒绝——worker 在该模型上重试有界次数后**热切换到类别配置的备用模型**继续任务，上下文不丢。
2. 场景 B：主模型+全部备用模型均不可用——worker 熔断退出，Exit Reason 列出已试模型链与各自错误，exit 1/failed。
3. 场景 C：带 phases 的任务书遇到模型故障——phase 机不因 error settle 推进，不写伪 "Phase N complete"，不伪成功。
4. 场景 D：模型间歇性抖动后恢复——三层重试（调用内 auto-retry / 跨 run 重发 / 成功归零）保证抖动不触发降级。
5. 场景 E：降级/熔断发生时，已产出的中间产物（phase 文件、progress、已写文件、最后回复文本）完整保留并出现在终局 output.md。
6. 场景 F：同 key 连续多个 worker 因模型错误终结——PM 侧出现 model-error 告警，打破「无限重派无感知」回路。

### 1.4 范围说明（不做什么）

- 不包含：provider/SDK 层重试策略改动（packages/ai 重试参数保持现状）
- 不包含：PM 主窗口自身的模型错误处理（另一链路）
- 不包含：conductor 侧 `_l3_stream_aborted` 泛化（Python stalled-gate 语义，拆后续 key）
- 备用模型切换后会话内继续（不重派进程）；不做跨 worker 的全局模型路由调度

## §2 业务约束

### 2.1 平台 / 环境

Windows/Linux 双平台；worker 为独立 pi 进程（print mode）；fail-fast 退出路径须沿用 timeoutExit 的同步落盘 + killTrackedDetachedChildren + process.exit 模式（worker-mode.ts:3226）。

### 2.2 性能指标

fail-fast 触发（证据：spec-retry-chain-2026-10-15 / spec-settle-paths-2026-10-15）：
- 阈值默认连续 **2** 个 error agent run（[AI 推荐←TRQ-1]；`PI_WORKER_MODEL_ERR_MAX` env 可调，0=禁用熔断仅记证据）
- 快败型故障（HTTP 5xx/拒连，默认路由 0 provider 重试 + agent 级 3 次 2/4/8s）：单 error run ≈15s，fail-fast 总耗时 < 2 分钟
- 静默挂起型：每次 attempt 受 httpIdleTimeoutMs=300s（sdk.ts:309-312）约束，单 error run ≈20m14s；由两条有界路径兜底：① error 边界事件不喂活动钟后 idle 看门狗 ≤ ~11 分钟击杀（附 model-error 嫌疑标记）② N=2 error-run 链 ≈40m14s < wall 60m
- 硬性上界：任何模型故障形态下 worker 终局 < 60 分钟 wall 墙

### 2.3 安全约束

无新增凭证/网络面；证据行只含错误文本截断（≤200 字符），不含请求体。

### 2.4 集成依赖

依赖既有：settings.retry（agent-session auto-retry）、trace.log 行协议（[MODEL_ERR]/[MODEL_FALLBACK] 新行型）、run.json/output.md 终态协议、recordDispatchAlarm 告警通道、`.mw/dispatch.yml` 顶层配置（`fallback_models`，注意 mw.py:3524/3539/3553 三处 `_model_write` 整文件重写须扩展保留新键）与 launcher 重派链（credential/route 校验复用 mw-dispatch-reliability 遗产）。不使用 `pi.setModel`（其成功路径写全局 `~/.pi/agent/settings.json`，settings-manager.ts:700-706，违反 protected-config 原则）。

## §3 验收标准（AC）

> AC 状态: DRAFT（待用户确认后锁定；编号永不回收）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在模型对 worker 的 LLM 调用持续返回可重试错误时：worker 在首个 error agent run（run 内 auto-retry 耗尽后）即 exit 3；launcher 对同一模型最多重试 N=2 次进程（PI_WORKER_MODEL_ERR_MAX，默认 2），耗尽后按备用链推进；全部耗尽后 run.json status=failed；快败型故障每模型阶段 < 2 分钟，静默挂起型由 idle 看门狗（无在飞工具 + last_model_error=yes）改判 exit 3 进备用链，总时长始终 < 60 分钟 wall 墙 |
| AC-002 | 在每个 agent run 以 stopReason=error 终止时，worker 向 trace.log 追加一行 `[MODEL_ERR]`（时间戳、当前模型、本次失败序号——D3 修订后每进程恒为 run=1，跨进程次数由 launcher `[MODEL_RETRY]` 承载、errorMessage 截断≤200 字符），并在 idle 看门狗或正常完成时，若最后一条 message 为 error，`[IDLE_KILL]` 中标注 model-error 终止性 |
| AC-003 | 在 agent_settled 时最后一条 assistant 消息 stopReason=error 的条件下，worker-mode 不写 phase 完成文件、不 appendPhase done、不发送下一 phase prompt、不进入 finishSuccess 成功判定（模型全程 500 的 write 角色不得以 exit 0/done 终局） |
| AC-004 | 在熔断终局时，output.md `## Exit Reason` 以 `model unavailable:` 开头并含已试模型链（每个模型的 error run 数）与最后一次 errorMessage 文本，PM 终端回读零改动可读到该根因 |
| AC-005 | 在 run 内 transient 错误被 auto-retry 恢复（最终成功 assistant 消息）时，settle 走正常流程、不 exit 3（抖动回归保护）；跨进程重试由 launcher 同模型重试承担 |
| AC-006 | 在同 key 连续 2 个 worker 以 model-unavailable 终结时 [AI 推荐]，PM 轮询循环终态分支（pm-orchestrator.ts:1603 附近）记录 kind=model-error 告警，PM/autopilot 经既有通道可读 |
| AC-007 | 在 faux provider 注入连续 error turn 的测试下，AC-001/003/005 三路径有自动化覆盖（管线级 createHarness + 时序级 fakePi + 纯函数断言），`./test.sh` 相应套件全绿 |
| AC-008 | 在 `.mw/dispatch.yml` 顶层为某任务类别配置 `fallback_models` 数组且 worker 以 exit 3 终结时，launcher 先对同一模型按 PI_WORKER_MODEL_ERR_MAX（默认 2）做同模型进程重试（trace 推导计数、重启安全），耗尽后按数组顺序用下一个备用模型重派同一任务（`--model` flag，env 注入，已试模型链随 env 传递）；未配置 fallback 的类别同模型重试耗尽后直接 failed |
| AC-009 | 在同模型重试/模型切换发生时，launcher 分别向 trace.log 追加 `[MODEL_RETRY] model=<m> attempt=<k>` / `[MODEL_FALLBACK] from=<m> to=<n> attempt=<k>`；备用候选凭证缺失/不存在时预校验跳过（不写全局 settings.json，不调用 setModel）；重派 worker 从 task.md+磁盘产物重播种 |
| AC-010 | 在降级或熔断终局时，output.md 携带中间产物：已写文件清单（collectArtifacts）、已完成 phase 数、lastAssistantText 截断摘要，且降级过程不丢弃/不重置任何已落盘产物 |

## §4 风险与未决项

- 风险：error 边界事件（turn_end/agent_end of error attempts）排除出活动钟是看门狗语义变更——合法恢复场景（连续失败 ~10 分钟后第 4 次成功）会被 idle 击杀截断；缓解：快速失败型不受影响（~15s），且降级/熔断本身已提供有界终止；须在 design 中核对 worker-idle-heartbeat.test.ts 既有断言。
- 风险：备用模型与主模型的能力差异（上下文窗口/工具能力/凭证缺失）——切模型后长上下文可能溢出、setModel 返回 false 时须视为耗尽跳过；design 需定模型解析与验证路径。
- 风险：降级重发当前 prompt 的幂次——phase 场景重发当前 phase prompt（不推进）；无 phases 场景重发初始 prompt；N 计数按模型隔离，切换时重置。
- 风险（TRQ-2 新发现，越界记录）：print mode 下 `session.prompt()` 首 settle 即 resolve、dispose 把在飞 phase run 打成 aborted——phased 任务在 print mode 本就冻结在 settle 1（与模型错误无关的既有缺陷；全库无 phased 生产实迹）。本 key 不修，AC-003 在 phased 面上的防护仍按代码语义实施。
- 风险：硬崩路径不产生 agent_end（TRQ-3 残留），降级/熔断覆盖不到硬崩——由 OS exit + launcher `_exit_to_status` 兜底，本 key 不扩。
- 待确认：阈值 N=2（PI_WORKER_MODEL_ERR_MAX 可调）、告警阈值 K=2、dispatch.yml fallback 配置键名与任务卡 `model:` 头的优先级互動（design 定）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- mw-worker-timeout-convergence 的 watchdog 定时器套件与证据行模式（worker-mode.ts:3184-3470：idleTimer/wallTimer/appendTimeout/[IDLE_KILL] 证据行）——fail-fast 复用同一落盘与退出模式。
- recordDispatchAlarm no-product 告警通道（worker-mode.ts:3619-3626 写入 + pm-orchestrator 消费）——model-error kind 沿用同一机制。
- faux provider 测试基建（packages/coding-agent/test/suite/harness.ts，TRQ-4 盘点中）——AC-007 的注入手段。
- mw-worker-output-contract 的 output.md/`## Exit Reason` 终态协议——AC-004 的展示面。

### 需规避坑点

- _pitfalls.md 2026-09-22：review worker `stream closed before response.completed` 空产出仍进入判读——error 终局不得被判读为有效产物。
- _pitfalls.md wfg-i03 事故：worker 连续 12 次失败重派无人察觉（resume-credit 逐轮 +1、人工 approve 无配额，TRQ-3 机理反推）——本 key 的告警/熔断正是对该坑的修复。
- _pitfalls.md env 继承链：PI_WORKER_* env 经 serve→launcher→worker 传递，新增 `PI_WORKER_MODEL_ERR_MAX` 须显式进 launcher._build_env，否则静默失效。
- worker-mode.ts:3531：handler 内 process.exit 截断 stdout flush——退出前所有写必须同步完成（timeoutExit 模式）。
- TRQ-3：`recordDispatchAlarm` 现有 10 种 kind 几乎无读方——新 kind 必须接有读方的通道（pm-orchestrator.ts:1603 轮询终态分支），否则重蹈覆辙。
