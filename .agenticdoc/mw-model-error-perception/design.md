# Design: mw-model-error-perception
> **实现期修订索引（2026-10-15，D3 进程级化）**：涉及「followUp 重发」「worker 侧 N=2 连续计数 / PI_WORKER_MODEL_ERR_MAX 为 worker 预算」的段落为 pre-D3 历史文本，一律以 design §2 决策 D3 的修订记录为准（worker 首个 error settle 直接 exit 3，`[MODEL_ERR] run=1`；预算与 `[MODEL_RETRY]` 计数在 launcher；挂起型 idle 击杀改判 exit 3）。AC-002 的「连续失败计数」按此读作 run=1。


> Key: mw-model-error-perception
> 创建时间: 2026-10-15
> 输入 spec: `.agenticdoc/mw-model-error-perception/spec.md`（AC-001~AC-010，共 10 条）
> 证据: evidence/research/spec-problem-forensics-2026-10-15.md、spec-retry-chain-2026-10-15.md、spec-settle-paths-2026-10-15.md、spec-pm-perception-path-2026-10-15.md、spec-test-infra-2026-10-15.md、design-fallback-mechanics-2026-10-15.md

## §0 锚定

- Goal 继承：GC-1（Extension API only，不改 pi 核心）、GC-2（文件驱动证据）、GC-3（看门狗语义延续）
- 用户已裁决：降级采用**进程级备用**（方案 A）——不调用 `pi.setModel`（其成功路径写全局 `~/.pi/agent/settings.json`，settings-manager.ts:700-706，违反 protected-config 原则）；launcher 用下一个备用模型重派同一任务

## §1 架构总览

故障处理管线分四段，跨 TS 扩展与 Python 服务两侧：

```
[worker 进程内] worker-mode.ts
  agent_end(record lastError) → agent_settled(每 run 链一次)
    ├─ last assistant stopReason==error?
    │    ├─ 是 → 连续计数+1，[MODEL_ERR] 落 trace
    │    │     ├─ 计数 < N → sendUserMessage(当前 prompt, followUp) 重发
    │    │     └─ 计数 ≥ N → 有界退出 exit 3（同步落盘 output.md/trace/run.json 后 process.exit(3)）
    │    └─ 否 → 计数归零，既有 settle 流程（phase 推进/settleOrSelfCheck）不变
  error 边界事件不刷新活动钟；[IDLE_KILL] 附 model-error 嫌疑标记

[launcher] launcher.py（reap 分支）
  exit==3 且 PI_WORKER_FALLBACK_MODELS 尚有剩余
    → 预校验下一个备用（route/凭证）
    → trace 追加 [MODEL_FALLBACK] from= to= attempt=
    → 同任务重派：--model <next>，PI_WORKER_FALLBACK_INDEX+1，PI_WORKER_TRIED_MODELS 追加
  exit==3 且无剩余（或未配置）→ status=failed，Exit Reason 透传 model unavailable 链

[配置] mw.py / mw_common.py
  dispatch.yml 顶层 fallback_models: {<type>: [provider/model, ...]}
  校验（格式/单行/去重主模型）+ 三处 _model_write 整文件重写保留新键（mw.py:3524/3539/3553）

[PM] pm-orchestrator.ts
  轮询终态分支（:1603 recordWriteScopeResidualRisks 旁）：同 key 连续 K=2 个
  model-error 终结 → recordDispatchAlarm(kind=model-error)；非 model-error 终结清零
```

## §2 架构决策

### 决策 D1：错误判定与动作钩子

**决策摘要**：在哪个月经点判定「一个 error agent run」并触发计数/重发/退出。

| 方案 | Pros | Cons |
|------|------|------|
| A. agent_end 记录 + agent_settled 动作 | agent_settled 每 run 链恰好一次（agent-session.ts:596-604 finally）；与既有 phase 机同一钩子，无重入；agent_end 每次 attempt 都触发，仅做 lastError 记录安全 | 需要跨事件传状态（一个变量） |
| B. 全部挂 agent_end | 单钩子 | agent_end 每 attempt 触发（内部重试 3 次=3 个 agent_end），会 mid-retry 误计数/误重发 |
| C. 订阅 auto_retry 事件 | 语义最准 | 扩展订阅不到（session 层事件，TRQ-1 证据） |

**推荐**：A。**依据**：TRQ-1（auto_retry 不可订阅）、TRQ-2（agent_settled 在 error turn 无条件触发的实测探针）。

### 决策 D2：降级机制（用户已裁决）

| 方案 | Pros | Cons |
|------|------|------|
| A. 进程级备用：exit 3 → launcher 重派 | 零全局配置副作用；进程隔离天然按模型隔离计数；launcher 已有 spawn/route/凭证校验能力 | 跨进程上下文丢失（worker 本就文件原生，task.md+产物重播种） |
| B. 会话内 setModel 热切换 | 上下文保留 | setModel 成功路径写全局 settings.json（protected-config 违约）；并行 worker 竞态；去掉全局写需改 core（GC-1 违约） |

**推荐**：A（用户已确认）。**依据**：TRQ-5 + PM 复核 settings-manager.ts:700-706。

### 决策 D3：error settle 的重发语义（✂ 2026-10-15 实现期修订：重试全部进程级）

**原方案 A（followUp 重发）被 PM 读码否决**：`agent_settled` 在 session 层 `_runAgentPrompt` 的 finally 中发出（agent-session.ts:596-604），而 followUp 队列的 drain 在 `agent.prompt()` 内部循环（packages/agent/src/agent.ts:368-376）——settle 期入队的 followUp 在 prompt() 返回后无人消费；print mode `session.prompt()` 返回即 dispose（print-mode.ts:131+），排队消息被 abort。**生产 print mode 下 in-process 重发链不工作**（与 phased 机冻结同机理，TRQ-2 probe A 实测）。

**修订后方案（与 D2 进程级同构）**：

| 方案 | Pros | Cons |
|------|------|------|
| A'. worker 在 error settle 直接 exit 3；每模型 N=2 次尝试预算移到 launcher（同模型重试，trace 推导计数、重启安全）；挂起型 idle 击杀（无在飞工具 + last_model_error=yes）同样 exit 3 进备用链 | 生产/测试行为一致；零 core 改动；进程级隔离天然按模型计数 | 每次重试丢会话上下文（task.md+产物重播种，与 D2 一致） |
| B'. 修 print mode drain 队列 | 顺带修复 phased 既有缺陷 | core 手术 + 新 session API，超出本 key 范围（GC-1） |

**推荐**：A'。抖动保护层级重排：① run 内 auto-retry（3 次）② 同模型进程重试（launcher，N=2）③ 备用模型链 ④ 熔断 failed。**依据**：agent.ts:368-376 与 print-mode.ts:131 读码 + TRQ-2 probe A。

### 决策 D4：error 边界事件与活动钟

**决策摘要**：error attempt 的 turn_end/agent_end 是否刷新 idle 看门狗的 lastActivityAt。

| 方案 | Pros | Cons |
|------|------|------|
| A. error 边界事件不刷新活动钟 + [IDLE_KILL] 附 model-error 嫌疑标记 | 静默挂起型 ~11 分钟被 idle 墙击杀（对比 N=2 链的 ~40 分钟）；idle-kill 根因不再被掩盖 | 慢恢复（>10 分钟后自愈）被截断——本就等价于模型不可用，降级/熔断会接管 |
| B. 保持活动钟，只靠 N=2 | 零看门狗语义变更 | 挂起型 worker 存活 ~40 分钟，PM 长时间无根因可见 |

**推荐**：A。**依据**：TRQ-1（路由 B/C 挂起型单 error run ≈20m14s）、TRQ-2（idle 投毒实测 probe B）。须回归核对 worker-idle-heartbeat.test.ts 既有断言。

### 决策 D5：fallback 配置与注入

**决策摘要**：`fallback_models` 放哪、怎么进 worker。

| 方案 | Pros | Cons |
|------|------|------|
| A. dispatch.yml 顶层键（按 type）+ launcher inject_fallback_env 注入 PI_WORKER_FALLBACK_MODELS/_INDEX/_TRIED | 与角色/模型默认值同源；launcher 派发时可预校验 route/凭证；任务卡 `model:` 主模型覆盖正交（fallback 仍适用，按 provider+id 去重） | 必须同步扩展三处 `_model_write`（mw.py:3524/3539/3553 整文件重写），否则静默丢键 |
| B. 任务卡 model-fallback: 头 | 任务级粒度 | 配置散落、无集中校验、launcher 注入链仍要新建，收益不抵 |

**推荐**：A。**依据**：TRQ-5（models.<role> 值被两侧硬校验为单行字符串，顶层键是唯一不破坏既有校验的落点；inject_rag_env 先例 launcher.py:1979）。

### 决策 D6：模型耗尽的机器信号

| 方案 | Pros | Cons |
|------|------|------|
| A. 专用退出码 3（markOutcome else 分支仍映射 failed；launcher 在状态映射前拦截 3） | 机器可读、零文本解析；对 run.json 语义无侵入 | 新增一个退出码值（0/1/2/3） |
| B. Exit Reason 文本标记解析 | 不新增退出码 | 脆弱（自由文本），launcher 解析 worker 产物方向反了 |

**推荐**：A。**依据**：launcher `_exit_to_status` 与 markOutcome 同构映射（TRQ-2 核验），3 落 else=failed，仅 launcher 增加拦截分支。

### 决策 D7：PM 侧告警

| 方案 | Pros | Cons |
|------|------|------|
| A. pm-orchestrator 轮询终态分支记 kind=model-error（K=2/key，非 model-error 终结清零） | 唯一同时具备去重/owner/双通道的插桩点（TRQ-3 ：1603）；TS 侧闭环 | 不阻断 conductor 自动重派（留人工/后续 key） |
| B. conductor `_l3_stream_aborted` 泛化 + mark_stalled(model-error-loop) | 能实际止住重派回路 | Python stalled-gate 语义，独立成键更稳 |

**推荐**：本 key 做 A；B 拆后续 key（用户已确认范围）。**依据**：TRQ-3（8 条重派回路盘点、resume-credit 机理）。

## §3 模块设计

### 3.1 worker-mode.ts（TS 扩展，唯一 worker 侧行为面）

新增状态：`consecutiveModelErrRuns: number`、`currentModelId: string`（session_start 从 ctx.model/`[MODEL]` D-116 同源读取）、`triedModels: string[]`（env PI_WORKER_TRIED_MODELS 初始化）。

变更点：
1. `agent_end`（:3139）：提取末位 assistant `stopReason`/`errorMessage` 存 `lastErrorInfo`（仅记录）。
2. `agent_settled`（:3707 handler 顶部、taskDone 检查后）：
   - `lastErrorInfo?.stopReason === "error"` → `consecutiveModelErrRuns++`；appendTrace `[MODEL_ERR]`；计数 ≥ N（resolveModelErrMax，默认 2，PI_WORKER_MODEL_ERR_MAX，0=禁用只记证据）→ 走 modelExhaustedExit（复用 timeoutExit 模式：同步写 output.md（Exit Reason `model unavailable: tried=<链> last=<err>` + collectArtifacts + phase 进度 + lastAssistantText 截断）→ appendEnd → recordEnd(3) → killTrackedDetachedChildren → process.exit(3)）；计数 < N → `pi.sendUserMessage(当前 prompt, {deliverAs:"followUp"})`（phased=当前 phase prompt，无 phases=初始 task 内容）。
   - 非 error → 计数归零，既有流程不动（AC-003：error settle 不进入 phase 推进/finishSuccess——在 settle handler 的 phase 推进与 settleOrSelfCheck 分支前拦截）。
3. 活动钟（:3035-3052）：`touch` 调用点改为携带 stopReason 感知——error 边界事件（message_end/turn_end/agent_end 其末位 assistant 为 error）不刷新 lastActivityAt/lastDeltaAt；idle 击杀路径（appendIdleKillEvidence）增加 `last_model_error=<bool>` 字段。
4. 退出码类型 `0|1|2` 扩为 `0|1|2|3`；markOutcome 不变（3 走 else=failed）。

不改动：watchdog 定时器结构、heartbeat、phase 机成功路径、输出协议（仅 output.md Exit Reason/新增字段）。

### 3.2 launcher.py（Python，重派执行者）

1. `inject_fallback_env`（inject_rag_env 旁，:1979）：从 dispatch.yml 顶层 `fallback_models[task_type]` 解析，注入 `PI_WORKER_FALLBACK_MODELS`（csv "provider/model"）、`PI_WORKER_FALLBACK_INDEX`（0）、`PI_WORKER_MODEL_ERR_MAX`（透传 serve env）。
2. reap 分支（product-first :418-454 区域）：worker exit==3 且 INDEX+1 < 数组长 → 预校验下一备用（route 存在 + 凭证，复用 mw-dispatch-reliability 校验器；不合格跳过并续试下一个）→ trace.log 追加 `[MODEL_FALLBACK] from=<m> to=<n> attempt=<k>` → 同任务重派（`--model <next>`、INDEX+1、TRIED 追加；新 run_id，task_key 不变）。无剩余 → 既有 failed 终态（Exit Reason 透传）。
3. 重派次数硬上限 = fallback 数组长度（无额外配额），不与 resume-credit 互動。

### 3.3 mw.py / mw_common.py（配置层）

1. dispatch.yml 顶层 `fallback_models: {coding: [...], review: [...], ...}` schema：值=模型 id 列表（"provider/model" 单行）、与主模型去重、上限 4。
2. 三处 `_model_write`（mw.py:3524/3539/3553）重写时保留 `fallback_models` 键（读-改-写，非整表替换）。
3. `mw doctor`：fallback 配置校验（格式/凭证预检 warn）。

### 3.4 pm-orchestrator.ts（PM 感知）

轮询终态分支（:1603 recordWriteScopeResidualRisks 旁）：从 run.json/Exit Reason 判定 model-error 终结（exit 3 且重派链耗尽，或 run.json 新增 `model_exhausted: true` 字段）；同 key 连续 K=2 → `recordDispatchAlarm(kind="model-error")`；非 model-error 终结清零计数。

### 3.5 明确不做

- 不改 packages/ai 重试参数；不改 pi core；不写 `~/.pi/agent` 任何文件；不处理 PM 主窗口模型错误；不动 conductor stalled-gate（后续 key）；不修 print-mode phased 冻结缺陷（越界记录于 spec §4）。

## §4 数据与协议

| 协议 | 定义 |
|------|------|
| `[MODEL_ERR]` | `[MODEL_ERR] <iso> model=<provider/model> run=<k> err=<截断200>`（worker-mode 写 trace.log） |
| `[MODEL_FALLBACK]` | `[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>`（launcher 写 trace.log） |
| `[IDLE_KILL]` 新字段 | `last_model_error=yes/no` |
| 退出码 3 | model-exhausted；run.json status=failed（else 分支）；launcher 拦截重派 |
| env | `PI_WORKER_MODEL_ERR_MAX`（int，默认 2，0=禁用）、`PI_WORKER_FALLBACK_MODELS`（csv）、`PI_WORKER_FALLBACK_INDEX`（int）、`PI_WORKER_TRIED_MODELS`（csv） |
| run.json | 新字段 `model_exhausted: true`（exit 3 时） |
| dispatch.yml | 顶层 `fallback_models: {<type>: ["provider/model", ...]}` |

## §5 测试设计

1. TS 纯函数：resolveModelErrMax、trace 行格式 regex、Exit Reason 组装（对齐 mwoc-w4 纯函数先例）。
2. TS 管线级（createHarness + faux）：连续 N 条 `fauxAssistantMessage("", {stopReason:"error", errorMessage:"HTTP 500"})`（packages/ai/src/providers/faux.ts:114）→ 断言 exit 3、[MODEL_ERR] 行数=2、phase 文件未写、output.md 含 model unavailable + 中间产物清单；交错成功 → 计数归零不退出（AC-005/007）。
3. TS 时序级（fakePi + fake timers，worker-idle-heartbeat.test.ts 先例）：error 边界事件不喂活动钟 → idle 墙 10 分钟击杀 + `last_model_error=yes`；成功事件照常喂钟（回归）。
4. Python：launcher exit-3 重派（fake pi spawn，test_launcher.py 模式）、fallback 预校验跳过、`_model_write` 保留键、dispatch.yml 校验；`test.sh`/pytest 相应套件全绿。
5. 保护断言：全程无 `~/.pi/agent` 写（protected-config 测试既有模式）。

## §6 风险与缓解

| 风险 | 缓解 |
|------|------|
| 活动钟语义变更破坏既有 idle 测试/合法慢恢复 | §5.3 回归；慢恢复截断等价于模型不可用，由降级/熔断接管（spec §4） |
| 重派上下文断裂 | task.md+trace/progress 产物重播种（D-116 既有）；[MODEL_FALLBACK] 留痕可审计 |
| `_model_write` 静默丢键 | §5.4 专项断言 |
| 跨 provider 备用无凭证 | launcher 预校验跳过（§3.2），doctor warn |
| 硬崩无 agent_end，管线不触发 | OS exit + launcher `_exit_to_status` 兜底（spec §4 明示不扩） |
