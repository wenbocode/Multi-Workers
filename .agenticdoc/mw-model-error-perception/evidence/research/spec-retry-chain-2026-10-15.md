# Research: worker 模型持续失败的完整重试链路量化（spec-retry-chain, TRQ1）

key: mw-model-error-perception / card: tasks/TRQ1-retry-chain.md
日期: 2026-10-15 · 方法: 静态读码 + 依赖源码核验（无运行时实验，见 §残留）

## 0. 调研方法与出处

逐层读码：provider SDK 层（node_modules/openai 6.26.0、@anthropic-ai/sdk 0.91.1、undici 8.9.0）→ packages/ai provider/api 层 → packages/agent 事件循环 → packages/coding-agent agent-session 重试层 → worker-mode 看门狗 → multi-workers launcher/mw_common。所有结论给 文件:行号。卡内预研修正两处路径：

- `packages/ai/src/timi-responses.ts` 实际为 `packages/ai/src/api/timi-responses.ts`（:34 内容一致）。
- timi provider 注册了两个 API：`anthropic-messages` 是**裸 anthropicMessagesApi()**，不带 timi 包装（`packages/ai/src/providers/timi.ts:38-46`）；只有 `openai-responses` 走 timiResponsesApi。timi.json 中 glm-5.3 / deepseek-v4.1-flash 等 `api: "anthropic-messages"`，gpt-5.5-r3 / gpt-5.6-* 为 `openai-responses`。**mw worker 默认模型（launcher.py:1372 无 model 时 timi 路由默认 glm-5.3；settings.json defaultModel=deepseek-v4.1-flash）都是 anthropic-messages 路由**——即下文「路由 B」，provider 级重试为 0 而非 8。

### 0.1 链路分层事实（核验卡内已知事实）

1. **provider 级重试**（`packages/ai/src/utils/provider-retry.ts`）：
   - `retryProviderRequest` 默认 `maxRetries ?? 0`（:109）；SDK 自身重试被强制关闭（openai-responses.ts:147、anthropic-messages.ts:557 均 `maxRetries: 0`）。
   - 可重试判定 `isRetryableProviderError`（:22-37）：`x-should-retry` 头 > `status === undefined`（网络层错误，视为可重试）> 408/409/429/≥500（:29-33）。
   - 退避：服务端 `retry-after-ms`/`retry-after` 优先（:53-59），超过 `maxRetryDelayMs`（coding-agent 默认 60000，settings-manager.ts:843）**直接抛错终止整条链**（:43-46，错误文本含 "retry delay"）；否则 `min(0.5·2^i, 8)s × (1 − rand·0.25)`（:65-66），`DEFAULT_MAX_RETRY_DELAY_MS = 60_000` 只约束服务端请求值（:1）。
   - SDK 级（openai 6.26.0）默认 `timeout 600000ms/10min`（client.js:138,573）、`maxRetries ?? 2`（client.js:148）——**均被 pi 覆盖**（timeout 见 §2；maxRetries=0）。
2. **timi 路由 openai-responses**（`packages/ai/src/api/timi-responses.ts`）：`options?.maxRetries ?? 8`（:34）——coding-agent 未设置 provider.maxRetries 时（默认 undefined，settings-manager.ts:842）timi 模型拿到 **8 次 provider 重试（9 次请求）**；非 timi 模型落到 retryProviderRequest 的 `?? 0`（1 次请求）。
   - `wrapStream`（:66-84）：错误若发生在 provider `start` 事件之前（整条重试链耗尽后），附加 `PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC` 且 `outerRetryEligible: false`（:67-77）。`isRetryableAssistantError` 见此诊断直接判不可重试（`packages/ai/src/utils/retry.ts:246-250`）→ **路由 A 的 pre-start 失败（持续 500 / 连接拒绝 / 挂起）不做 agent 级重试，一次调用即终局**。
3. **agent 级 auto-retry**（`packages/coding-agent/src/core/agent-session.ts`）：
   - 预算：`settings.retry` 默认 `enabled=true, maxRetries=3, baseDelayMs=2000`（settings-manager.ts:814-823）；退避 `baseDelayMs·2^(n-1)` = 2s/4s/8s，固定无抖动（:2695），sleep 可中断（:2714）。
   - 计数器在任意成功 assistant 后清零（:671-679）；耗尽后 `_retryAttempt` 归零（:1095）→ **每个新 turn（含 phase 重发）都重新拿满 3 次预算**。
   - 事件：`auto_retry_start`（:2697-2704，每次重试 sleep 前发）与 `auto_retry_end`（成功 :671-679 / 取消 :2716-2726 / 终局 :1088-1095——注意终局只在**整轮结束后发一次**，attempt=最后完成的次数；重试对之间只有 start 没有 end）。
   - 归属：`auto_retry_start/end` 是 **AgentSessionEvent**（:166-167），唯一消费者是 TUI（interactive-mode.ts:3329,3342）。扩展事件面 `pi.on` 的重载列表（core/extensions/types.ts:1201-1242）**不含 auto_retry_\*/summarization_retry_\***——**扩展不能直接订阅，只能从 message_end(stopReason=error) 的重复周期推断**。
4. **事件时序根规则**（`packages/agent/src/agent-loop.ts`）：assistant 的 `message_start` 只在 provider `start` 事件后发（:319-325）；`done/error` 分支若从未收到 start，则补发 message_start + message_end（:346-361）。**provider 重试链（retryProviderRequest 循环）发生在 streamFn 调用内部、start 之前 → 整条链期间 agent 层零事件**。error turn 以 turn_end + agent_end 收束（:196-200）。
5. **超时注入**（`packages/coding-agent/src/core/sdk.ts:304-323`）：`timeoutMs = options?.timeoutMs ?? settings.retry.provider.timeoutMs ?? effectiveTimeoutMs`，其中 `effectiveTimeoutMs = httpIdleTimeoutMs === 0 ? 2147483647 : httpIdleTimeoutMs`（:309-311）；`httpIdleTimeoutMs` 默认 300_000（http-dispatcher.ts:7）。→ **SDK 请求永远带 timeout（默认 300s），SDK 自带 10min 默认永不生效**。该 timeout 经 openai-responses.ts:148 / anthropic-messages.ts:556 传给 SDK `timeout`。
6. **传输层超时**（`packages/coding-agent/src/core/http-dispatcher.ts:81-107`）：`configureHttpDispatcher` 把 undici EnvHttpProxyAgent 的 `headersTimeout` 和 `bodyTimeout` 都设为 httpIdleTimeoutMs（默认 300s）；在 cli.ts:27、main.ts:545/811、interactive-mode.ts:1884 装配。undici 8.9.0 默认同样是 headersTimeout/bodyTimeout=300e3、connect.timeout=10e3（node_modules/undici/types/client.d.ts:36-46、lib/dispatcher/client.js:276）；**undici 语义 delay=0 → 不设定时器 = 完全禁用**（lib/dispatcher/client-h1.js:246-266 `if (delay)`）。
7. **worker 看门狗**（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`）：
   - 预算：wall 默认 60m（:236），task.md `timeout:` > PI_WORKER_TIMEOUT_MS > 默认（:254-259）；idle 默认 10m（:242），PI_WORKER_IDLE_MS 可调（:262-266）；in-flight 工具分支阈值 max(idleMs, 30m)（:281,285-287）。
   - 活动源：`pi.on("message_update"/"message_start"/"message_end"/"turn_start"/"turn_end"/"agent_start"/"tool_execution_update"/"tool_execution_end")` 全部 touch lastActivityAt（:3038-3052）——**message_end / turn_end / agent_end 都算活动**。
   - idle 分支（:3403-3458）：无 in-flight 工具时，`idleForMs ≥ idleMs` **且** delta 时钟也 ≥ idleMs（:3436-3440）才杀；Exit Reason 文本 `no activity for Ns (last delta Xs ago, last tool Ys ago)`（:3457）。wall 分支（:3460-3466）：`budget Ns exceeded (last activity Xs ago)`。两者都写 run.json（exitCode 1, exitReason `idle timeout: …` / `wall timeout: …`，:3228-3251）后 `process.exit(1)`。

## 1. 四类故障逐一事实

**路由 A** = timi + openai-responses（gpt-5.5-r3、gpt-5.6-*、gpt-6-*）：provider 8 重试（9 请求）+ pre-start 边界诊断（无 agent 重试）。
**路由 B/C** = timi + anthropic-messages（glm-5.3、deepseek-v4.1-flash，mw 默认）与直连 provider（anthropic/deepseek/zai-coding-cn/openai-codex）：provider 0 重试（1 请求）+ 无边界诊断（agent 级 3 重试、4 尝试、退避 2/4/8s）。

每尝试超时上限（默认配置）= 300s（SDK timeout = headersTimeout；undici bodyTimeout 300s 兜中流静默）。

### 1.1 持续 HTTP 500（服务器快速回 5xx）

| | 重试次数 | 退避序列 | 最坏墙钟 | 事件序列 |
|---|---|---|---|---|
| A | provider 8（共 9 请求） | 0.5/1/2/4/8/8/8/8s ×[0.75,1]（Σ 29.6–39.5s） | **≈30–40s** | 链内零事件；终局 message_start+message_end(error, 带 outerRetryEligible:false 诊断)→turn_end→agent_end→agent_settled。**无 auto_retry_\*** |
| B/C | agent 3（共 4 请求） | 2/4/8s | **≈15s** | 每尝试：agent_start→turn_start→message_start→message_end(error)→turn_end→agent_end；对间 auto_retry_start(1..3)；终局 auto_retry_end(success:false, attempt:3, finalError)；最后 agent_settled |

错误形态见 §3（`500 …` / `OpenAI API error (500): 500 …`）。5xx 命中 provider 可重试（provider-retry.ts:29-33）与 agent 可重试文本（retry.ts:32）。

### 1.2 连接拒绝（快速 RST，如本地代理端口已死）

| | 重试次数 | 退避序列 | 最坏墙钟 |
|---|---|---|---|
| A | provider 8 | 同 §1.1 | **≈30–40s**（若主机不可达无 RST：undici connect.timeout 10s/次 → 9×10s+39.5s ≈ **130s**） |
| B/C | agent 3 | 2/4/8s | **≈15s**（不可达变体 4×10s+14s ≈ 54s） |

事件序列同 §1.1 对应行。错误形态 `Connection error.`（status undefined → provider 级视为可重试 provider-retry.ts:28；agent 级命中 retry.ts:50）。

### 1.3 连接挂起（响应字节全无，headers 不达）

| | 重试次数 | 最坏墙钟 | 事件序列 |
|---|---|---|---|
| A | provider 8（每次 ≈300s 后 `Request timed out.`，provider-retry.ts:28 判可重试） | 链本身 9×300s+39.5s ≈ **45m39s，但 worker 在 ≈10m 被 idle 看门狗先杀** | **链内（10 分钟）零事件**：lastActivityAt 停在 turn_start/agent_start，无 delta → idle 分支 600s 触发（deltaIdle=∞）。Exit Reason = `idle timeout: no activity for 600s (last delta -, last tool Xs)`——**根因被看门狗掩盖** |
| B/C | agent 3（每尝试 ≈300s 超时→error） | 4×300s+14s ≈ **20m14s**，错误正常浮出 | 每尝试末尾 message_end(error)+agent_end **touch 活动钟**（间隔 ≈302–308s < 600s）→ **idle 永不触发**；auto_retry_start/end 照常；约 20 分钟终局失败，60m wall 不参与 |

变体（headers 已达、中流静默）：SDK timeout 在 fetch 返回 headers 时即 clear（openai client.js:389-413，`finally clearTimeout`），只剩 undici bodyTimeout=300s 兜底（错误文本未逐字核验，见 §残留）；对重试结构的影响与 §1.4 相同（中流错误不进 provider 重试链）。

### 1.4 流中断（stream closed before response.completed）

- 错误浮出点：openai 路由 processResponsesStream 抛出 → openai-responses.ts:171（无终态事件干净关闭）或 :184-195（传输异常）；anthropic 路由 :760-768。**此时 provider `start` 已发** → timi wrapStream 视为 started，**不加边界诊断** → agent 级可重试（错误文本命中 retry.ts "terminated"/"ended without" 等）。中流错误不经过 retryProviderRequest（它只包 `responses.create().withResponse()`，openai-responses.ts:149-156）→ provider 级不重试，直接冒泡为一次 agent 级失败。
- 墙钟：快速断流（连上即断）A/B/C 均为 **4 请求 + 14s ≈ 15s**；复合最坏（每次重试先 300s 挂起再断）4×300s+14s ≈ **20m14s**，每次尝试有 message_start/delta/message_end 活动 → idle 不触发。
- 事件序列：message_start→message_update(delta…)→message_end(error)→turn_end→agent_end→（B/C）auto_retry_start→…→auto_retry_end。**delta 活动使本类故障对 idle 看门狗完全不可见，只能靠错误浮出或 wall 兜底。**

## 2. 无超时/永久挂起判定

- **默认配置不存在传输层无界挂起**：SDK timeout 恒为 httpIdleTimeoutMs=300s（sdk.ts:309-312 覆盖 SDK 默认 600s）；undici headersTimeout=bodyTimeout=300s（http-dispatcher.ts:88-89）。卡内预研「provider.timeoutMs 默认未设 → 无超时」**不成立**：未设时会落到 httpIdleTimeoutMs，不是无超时。
- **两条边界路径**：
  1. `httpIdleTimeoutMs: 0`（"disabled"）：undici 两个超时被**彻底禁用**（client-h1.js:258 `if (delay)` 不设定时器），SDK timeout 映射为 2147483647ms≈24.8 天（sdk.ts:309-311）→ 全静默挂起在传输层无界。但 worker 层仍被 idle 看门狗 10m 封顶（静默无 delta）。设置该值需要用户显式配置（HTTP_IDLE_TIMEOUT_CHOICES，http-dispatcher.ts:9-14），非默认。
  2. **慢滴漏逃逸**（默认配置下唯一的真无界路径）：流保持每 <10min 产出至少一个 delta 字节/事件 → bodyTimeout 被任意字节重置、idle 看门狗被 message_update 重置 → 只剩 wall（60m 默认，或 task.md timeout:/PI_WORKER_TIMEOUT_MS）。SSE keep-alive 注释（`: ping`）只重置 bodyTimeout 不产生 delta → 10m 内被 idle 杀。LLM 正常生成不可能 10 分钟无 delta，故此路径要求上游半开/畸慢连接，现实概率低但存在。
- **idle 看门狗逃逸判定**：只有持续产生 touch 事件的失败模式能逃逸 idle——即 §1.4 的中流错误自旋与跨 phase 的 error 自旋（每次 turn_end/agent_end touch，worker-mode.ts:3044-3046）→ 最长存活 = wall 60m。**纯静默路径（§1.3 路由 A）不但不逃逸，反而必然在 10m 触发 idle 杀，代价是根因被 Exit Reason 掩盖**（对 PM 表现为「idle timeout」而非模型故障）。

## 3. errorMessage 典型文本形态（供 trace / Exit Reason 识别）

| 故障 | openai 路由文本 | anthropic 路由文本 | 来源 |
|---|---|---|---|
| HTTP 5xx | `OpenAI API error (500): 500 {<body JSON>}`；空体时 `…: 500 status code (no body)` | `500 {<body>}` / `500 status code (no body)`（裸 error.message，无前缀） | formatProviderError（utils/error-body.ts:128-141）+ openai-responses.ts:86-88,187；anthropic-messages.ts:767 |
| 连接拒绝/网络 | `Connection error.`（cause 不入 message） | `Connection error.` | openai core/error.js:78；@anthropic-ai/sdk core/error.js:78 |
| SDK 超时（挂起） | `Request timed out.` | `Request timed out.` | openai core/error.js:88；anthropic core/error.js:88 |
| 中流传输断 | `terminated`（undici TypeError 原样穿透，streaming.js:75）/ `other side closed` / `fetch failed` | 同左（裸 message） | openai core/streaming.js:44-77；undici |
| 流提前结束（无终态事件） | `OpenAI Responses stream ended without a stop reason` | （anthropic 对应 `stream ended before message_stop` 类文本） | openai-responses.ts:171 |
| 服务端 retry-after 超上限 | `Server requested Ns retry delay (max: 60s). <原错误>` | 同左 | provider-retry.ts:43-46 |

可重试性判定与识别可复用同一正则表：`packages/ai/src/utils/retry.ts:27-103`（RETRYABLE：`500`/`connection.?refused`/`timed? out`/`terminated`/`ended without`/`retry delay`…）与 ：8-25（NON_RETRYABLE 配额类）。诊断字段：路由 A 的 pre-start 失败在 `AssistantMessage.diagnostics[]` 携带 `provider_retry_boundary` + `outerRetryEligible:false`（types.ts:418；retry.ts:236-239）——**这是区分「provider 链耗尽」与「agent 级重试后仍失败」的机器判据**。

## 4. worker 实际 retry 设置来源

1. **launcher.py spawn env 不注入任何 retry/timeout 设置**：`_build_env`（launcher.py:268-369）只注入凭证（TIMI_API_KEY/ZAI_CODING_CN_API_KEY/ANTHROPIC_API_KEY/DEEPSEEK_API_KEY/代理 route）、可选 `TIMI_BASE_URL`/`*_BASE_URL`、`PI_WORKER_TASK`，`_stripped_env`（:127-152）做凭证剥离；`_build_command`（:1358-1396）只是 `pi [--provider X] [--model M] -p <starter>`（timi 无 model 默认 glm-5.3，:1372）。**推论**：`PI_WORKER_IDLE_MS`/`PI_WORKER_TIMEOUT_MS` 也不会被 mw 注入，但 worker env = `dict(os.environ)` 剥凭证，serve 进程若被用户设置了这两个变量会原样继承。
2. **mw 不改写 `~/.pi/agent/settings.json` 的 retry**：该文件在受保护清单（mw_common.py:1291-1297 PROTECTED_AGENT_CONFIG_FILES，:1322 assert_not_protected_agent_config 硬禁框架写入）；唯一例外是 `ensure_pi_shell_path`（:1439+）只合并写 `shellPath`，且仅限用户显式 `mw setup`/`doctor --fix`。本机实测 `~/.pi/agent/settings.json` 无 `retry` 键、仓库无 `.pi/settings.json` → **worker 生效值 = 代码默认**：agent 级 enabled/maxRetries 3/baseDelayMs 2000；provider 级 timeoutMs/maxRetries 未设 → 路由 A 链上 8 次重试 + 300s/尝试，路由 B/C 0 次重试 + 300s/尝试；httpIdleTimeoutMs=300s（经 cli.ts:27 / main.ts:811 装配）。
3. 设置合并序：全局 `~/.pi/agent/settings.json` deep-merge 项目 `<cwd>/.pi/settings.json`（settings-manager.ts:201,310）；`retry.maxDelayMs` 旧键迁移到 `retry.provider.maxRetryDelayMs`（:420-438）。

## 5. 结论 → 决策映射（fail-fast 阈值设计依据）

1. **感知挂点应为 `pi.on("message_end")`**：每条链路（含路由 A 的单链终局）都以 message_end(stopReason="error", errorMessage, diagnostics) 收束，这是扩展唯一能拿到的模型错误事实；worker-mode 现状只取 text（agent_end 处 ：3139-3153），errorMessage 全程丢弃（forensics #2 的量化补全）。
2. **「持续失败」在 agent 级的真实预算**：路由 B/C = 每 turn 最多 4 尝试/3 重试（快速失败 ≈15s 定局；挂起 20m14s 定局），turn 间预算重置 → 跨 phase 的 error 自旋不受重试预算约束，只有 wall 60m 兜底（forensics #3 的边界：只有**有事件**的自旋免于 idle；**静默**链必被 idle 10m 杀）。
3. **fail-fast 阈值建议设在「连续 2 个 error turn」**（绝对上限 3）：快速 500/拒连场景 worker 在 ≤ ~30–45s 内熔断可见（2 turn × ~15s）；挂起场景天然被 10m idle（路由 A）或单 turn 20m14s（路由 B/C）封顶，连续计数 2 时最坏 ≈ 40m 仍 < wall。阈值取 3（默认耗尽）会让挂起类最坏逼近 60m wall，PM 感知延迟翻倍。路由 A 的 pre-start 失败单 turn 只产生 1 个 error turn（边界诊断禁了 agent 重试），**连续 turn 计数天然覆盖它**；判定「重试耗尽」用 diagnostics 的 `provider_retry_boundary`，判定「重试后仍失败」用 errorMessage 文本（§3 表）。
4. **修复感知缺口的两个正交杠杆**：(a) trace/Exit Reason 落 [MODEL_ERR] + errorMessage（识别表见 §3）；(b) 对路由 A 的静默挂起，把「idle timeout + 全程零 delta + 零工具」的 Exit Reason 组合在 PM 侧翻译为「疑似模型连接故障」——现有 run.json exitReason 字符串已可判（`idle timeout: no activity for 600s (last delta -, last tool …)`，worker-mode.ts:3457）。

## 结论

- 链路总量：路由 A（timi openai-responses）= provider 8 重试 × 300s 上限 + 边界诊断短路 agent 重试；路由 B/C（mw 默认 glm-5.3/deepseek-v4.1-flash 等 anthropic-messages 路由 + 全部直连）= provider 0 重试 + agent 3 重试（2/4/8s）。
- 默认无传输层无界挂起（300s×3 处超时）；唯一无界路径是 <10min 间隔 delta 滴漏（仅 wall 兜底）与显式 httpIdleTimeoutMs=0。
- 最坏耗时：快速失败 A≈40s / B≈15s；挂起 A≈10m（被 idle 杀、根因掩盖）/ B≈20m14s；中流断 ≈15s–20m；全部 ≤ wall 60m。
- auto_retry_start/end 仅 session 事件层（TUI 专用），扩展不可订阅；可订阅的等价信号是 message_end(stopReason=error) 周期 + diagnostics.provider_retry_boundary。
- errorMessage 形态已列全（§3），trace/Exit Reason 识别可直接复用 retry.ts 的正则表。
- fail-fast 阈值：连续 2 个 error turn 熔断（上限 3），PM 侧用 exitReason 组合区分「模型故障」与「真空闲」。

## 残留与未验证

- undici bodyTimeout 触发时的错误文本（`Response body timeout`?）未逐字核验（§1.3 变体）；不影响 300s 上限结论。
- 全部数字为静态推演（读码 + 依赖源码），无真实故障注入实测；`x-should-retry`/`retry-after` 等服务端头会改变退避（上限已核验：>60s 即断链）。
- openai-codex 路由（DEFAULT_MAX_RETRIES=0，openai-codex-responses.ts:61,394-396）只核验了重试次数，其退避细节（isRetryableError 分支）未展开——mw codex worker 走 codex CLI 而非 pi 时与本链路无关。
- 死锁变体「headers 已达后每 <10min 一个 SSE 注释、无 delta」超过 300s bodyTimeout 的成立性依赖 undici bodyTimeout 对注释字节的计数（按规范任意字节重置，未实测）。
- 本机 `~/.pi/agent/settings.json` 快照（2026-10-15）：无 retry 键；若用户机器配置了 retry/provider 键，数值按 §4.3 合并序变化。

## 上下文来源

- 代码：packages/ai/src/utils/{provider-retry,retry,error-body}.ts；packages/ai/src/api/{timi-responses,openai-responses,anthropic-messages,openai-codex-responses}.ts；packages/ai/src/providers/{timi.ts,data/timi.json}；packages/agent/src/agent-loop.ts；packages/coding-agent/src/core/{agent-session,settings-manager,sdk,http-dispatcher}.ts + cli.ts/main.ts/modes/interactive/interactive-mode.ts；packages/coding-agent/src/core/extensions/types.ts；packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts；packages/multi-workers/{launcher.py,mw_common.py,autopilot/dispatch.py}。
- 依赖源码（node_modules 实装版本）：openai 6.26.0（client.js/core/error.js/core/streaming.js）；@anthropic-ai/sdk 0.91.1（core/error.js）；undici 8.9.0（types/client.d.ts、lib/dispatcher/client*.js）。
- 本仓库环境快照：~/.pi/agent/settings.json、无项目级 .pi/settings.json。
- 前序证据：evidence/research/spec-problem-forensics-2026-10-15.md（本文件是其 RQ-1 量化任务，修正/精化其 #3 的 idle 失效边界）。
