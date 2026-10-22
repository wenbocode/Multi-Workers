# design-transport-b2-contract —— B2 过渡后端传输契约实测 + systemone schema（RQ-D3）

- key: mw-jev-provider-integration · 相位: DESIGN · 日期: 2026-10-16
- 方式: 只读调研 + 实机探针（不改源码/配置，不 commit）；凭证运行期从 `~/.pi/agent/auth.json` 读取，全文未落任何明文（key_present=True）
- 实测脚本: 临时目录 `d3_probe.py`（urllib stdlib，key 只进 Authorization header，不打印不落盘），跑完已删除
- 调用预算: **3 次真实模型调用**（探针 A/B/C，均 max_tokens=64）+ **1 次零推理 schema 探针**（探针 D：无效 model 名，网关在校验层直接 400，不触达任何模型、不消耗推理配额，特此披露）
- 结论速览: `/v1/messages` 完全可用且支持强制工具调用（B2 首选承载）；`response_format` 被严格 schema 校验拒绝；`/responses` 可用但 reasoning 吞掉全部 max_output_tokens 且响应体是 litellm 混血形状（不推荐承载）；systemone 四种 question 字段与 confidence 公式均有官方定义。

---

## Q1 `/v1/messages` + `glm-5.3-flashx` 实际契约（实测 探针A）

**结论**：非流式 POST 完全可用。请求字段 `model` / `max_tokens` / `temperature` / `system` / `messages` 全部被接受（HTTP 200）；响应是标准 anthropic-messages 形状，但有两处代理侧特征：`id` 是网关生成的 UUID（非 `msg_` 前缀），且 `glm-5.3-flashx`（目录标注 `reasoning: true`，`packages/ai/src/providers/data/timi.json`）**必然先输出 `thinking` 块再输出 `text` 块**，解析方必须按块类型处理而非按顺序拼接。

实测记录（探针A，2026-10-16，2477 ms）：

- 请求体（截断 ≤400 字符）：
  ```json
  {"model": "glm-5.3-flashx", "max_tokens": 64, "temperature": 0.2, "system": "You are a decision function. Output only compact JSON.", "messages": [{"role": "user", "content": "Is 7 a prime number? Reply exactly {\"answer\":\"yes\"} or {\"answer\":\"no\"}"}]}
  ```
- 响应（截断 ≤400 字符，HTTP 200，`content-type: application/json`）：
  ```json
  {"id": "2f013a04-d7ef-40f5-a2b5-a7edd2064a41", "content": [{"signature": "6a3d674ee59447368d8ae5e5", "thinking": "The user asks if 7 is a prime number. 7 is prime (divisible only by 1 and 7). They want exactly {\"answer\":\"yes\"} or {\"answer\":\"no\"}. Output only compact JSON.", "type": "thinking"}, {"text": "{\"answer\":\"yes\"}", "type": "text"}], "model": "glm-5.3-flashx", "role": "assistant
  ```
- 完整顶层字段（实测全集）：`content, id, model, role, stop_reason, stop_sequence, type, usage`
- `stop_reason: "end_turn"`，`stop_sequence: null`，`type: "message"`，`role: "assistant"`
- `usage`（完整）：`{"input_tokens": 44, "output_tokens": 53, "server_tool_use": {}, "cache_creation_input_tokens": null, "cache_read_input_tokens": null}`
- 关键观察：thinking 块带 `signature`（24 字符）且排在首位；text 块严格按提示词只含 `{"answer":"yes"}`（verbatim 实测）——纯提示词 JSON 约束在此模型上 n=1 成立。

**非流式 vs 流式差异**：本探针测的是非流式（`stream` 缺省）。仓内 pi 的 anthropic-messages 实现**永远以流式调用**（`packages/ai/src/api/anthropic-messages.ts:560` `client.messages.create({ ...params, stream: true }, ...)`），流式 SSE 事件形状（message_start/content_block_delta/message_delta 里的 stop_reason 与 usage 时点）本轮未实测，记入残留。B2 最小模板用非流式（见 Q6），不受此残留影响。

**字段接受性汇总（实测）**：

| 请求字段 | 结果 | 证据 |
| --- | --- | --- |
| `model` | 接受，响应原样回填 `glm-5.3-flashx`（无前缀回填） | 探针A |
| `max_tokens` | 接受并生效（64；usage.output_tokens=53 未触顶） | 探针A |
| `temperature` | 接受（0.2） | 探针A |
| `system` | 接受（string 形式） | 探针A |
| `tools` + `tool_choice` | 接受并强制执行，`stop_reason: "tool_use"` | 探针B（Q2） |
| `response_format` | **拒绝**，400 `unknown_fields` | 探针D（Q2） |
| header `anthropic-version: 2023-06-01` | 接受（是否必需未单独验证） | 探针A/B |

## Q2 强制结构化 JSON 的可用路径

**结论**：推荐路径是 **`tools` + `tool_choice: {"type":"tool","name":...}` 强制工具调用**（实测可用、schema 形状受 `input_schema` 约束、解析确定性高）；`response_format` **不可用**（被网关严格 schema 校验以 `unknown_fields` 拒绝）；纯提示词约束可用（探针A n=1 严格遵守）但无 schema 强制力，只能做回退。

**实测证据 1 —— 强制工具调用可用（探针B，5385 ms，HTTP 200）**：

- 请求体（截断）：
  ```json
  {"model": "glm-5.3-flashx", "max_tokens": 64, "tools": [{"name": "submit_decision", "description": "Submit the structured decision answer", "input_schema": {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}, "confidence": {"type": "number"}}, "required": ["answer", "confidence"]}}], "tool_choice": {"type": "tool", "name": "submit_decision"}, "messages": [{"role": "user", "content": "Is 7 a prime number?"}]}
  ```
- 响应块结构（实测全集）：`content = [thinking, text, tool_use]`，`stop_reason: "tool_use"`
- `tool_use` 块字段（实测全集）：`{"type","id","name","input"}`，其中 `id: "call_97ccef0e32814e9cb3d17a90"`（OpenAI 风格 id，非 anthropic `toolu_` 前缀——又一处代理侧痕迹），`input: {"answer": "yes", "confidence": 1.0}`（verbatim）
- **解析要点**：即使 `tool_choice` 强制指定工具，模型仍会附带 text 块（"Yes, 7 is a prime number. It is a natural number..."）——解析器必须**只认 `type=="tool_use"` 的块**，忽略 text/thinking。

**实测证据 2 —— `response_format` 被拒（探针D，零推理 schema 探针，470 ms）**：

- 请求体：`{"model": "zzz-nonexistent-probe", "max_tokens": 1, "response_format": {"type": "json_object"}, "messages": [...]}`
- 响应（HTTP 400，verbatim，157 字节）：
  ```json
  {"type": "error", "error": {"type": "invalid_request_error", "message": "请求参数校验失败 —— unknown_fields: 存在非法/不支持字段（请对照 anthropic SDK 文档）: ['response_format']"}}
  ```
- 该端点对**未知顶层字段按名报告并整体拒绝**，与 PM 探针（`state`/`questions` → 同样 400 `unknown_fields`，见 `spec-jev-live-probe-20261016.md` 二轮探针表）一致。=> 任何 anthropic-messages schema 之外的字段（`response_format`、`json_schema`、systemone 的 `state`/`questions`）都进不来。

**仓内既有实现佐证**：`packages/ai/src/api/timi-responses.ts` 的 `normalizePayload` 对 `/responses` 路径做两件兼容（删 `store` 字段——"Timi rejects payloads that contain it" `timi-responses.ts:19`；补空 tool description）——说明该网关对 openai-responses schema 同样严格校验，且 litellm 会因净载荷细节整包拒绝。B2 走 `/v1/messages` 直连时不经过这层（Python 直发 fetch），但设计者须知该网关"净 schema"语义。

**推荐做法**：主路径 = 强制工具调用（`input_schema` 承载问题 schema）；回退路径 = 提示词约束 + text 块 JSON 解析 + 严格校验；放弃 `response_format`。

## Q3 错误形态归一

**结论**：该网关的错误形态有六类，其中「HTTP 200 但 body 是错误」与「404 返回 HTML」两类最容易被 naive 客户端漏判。仓内归一点：状态码与 header 语义在 `packages/ai/src/utils/provider-retry.ts:23-35`（`x-should-retry` header 优先；408/409/429/≥500 可重试；status undefined 视为可重试）、`retry-after-ms`/`retry-after`（`provider-retry.ts:51-60`，默认上限 60s `provider-retry.ts:1`）、SDK 重试关闭点 `packages/ai/src/api/anthropic-messages.ts:557`（`maxRetries: 0`）+ 外层 `retryProviderRequest`（:559-566）；错误文本级分类在 `packages/ai/src/utils/retry.ts`（`RETRYABLE_PROVIDER_ERROR_PATTERN`：429/rate limit/timeout/5xx/connection 等；`NON_RETRYABLE_PROVIDER_LIMIT_ERROR_PATTERN`：quota/billing）；timi 对 /responses 预启动错误打 `outerRetryEligible:false` 边界诊断（`timi-responses.ts` wrapStream + `retry.ts` `PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC`）。

**该端点实测/记录的错误体**：

| 类别 | 状态码 | 实际返回体（脱敏截断） | 来源 |
| --- | --- | --- | --- |
| schema 校验失败 | 400 | `{"type":"error","error":{"type":"invalid_request_error","message":"请求参数校验失败 —— unknown_fields: ... ['response_format']"}}`（application/json） | 探针D 本轮实测 |
| 限流 | 429 | `{"type":"error","error":{"type":"rate_limit_error","message":"API调用失败: {'error': {'message': 'Too Many Requests'}}"}}`，**无 retry-after 头**，持续 ≥90s | PM 探针 P2 + 90s 复测（spec-jev-live-probe） |
| 模型不可用 | 403 | `permission_error`「该模型不可用，请确认传入 model」 | PM 探针 P4（jev-preview/版本化 id） |
| 路径不存在 | 404 | **HTML** `Not Found`（非 JSON） | PM 探针 P5/P6（`/v1/chat/completions`、`/v1/responses`） |
| HTTP 200 但 body 是错误 | 200 | `{"error":{"message":"该模型不可用...","code":"304"}}`；及 `litellm.BadRequestError: Unmapped LLM provider...` | PM 探针 P8 + 二轮（`/responses` + jev/前缀模型） |
| 5xx / 超时 / 连接失败 | 5xx/— | 本轮未实测（无法安全诱导）；仓内策略按可重试处理 | 残留，见下 |

**客户端应识别的错误类别清单（B2 决策客户端的处置语义）**：

1. `400 invalid_request_error`（JSON，中文 message 带 `unknown_fields`/`参数校验失败`）→ **不可重试**，请求构造错误，修正后重发。
2. `403 permission_error`（「该模型不可用」）→ **不可重试**，模型 id/白名单问题，上报配置错误。
3. `404`（**可能 HTML**）→ **不可重试**，先判 content-type：非 JSON 即路由/网关问题。
4. `429 rate_limit_error`（JSON）→ **可重试**，指数退避；**无 retry-after 头**，退避参数只能自定（仓内 `provider-retry.ts` 对缺失 retry-after 用指数+抖动，默认封顶 60s）。
5. 5xx / 超时 / 连接错误 → **可重试**（`provider-retry.ts:29-34` + `retry.ts` 文本模式均归可重试）。
6. **HTTP 200 但 body 含 `error` 字段 / `litellm.*Error` 文本** → 必须解析 body 判定（litellm 透传形态），不可只看状态码。
7. `content-type` 非 JSON 的成功响应 → 协议错误，按 404 类处置。
8. 响应 `content` 无 `tool_use` 块（在强制 tool_choice 下）→ 契约违约，按可重试降级处理（先试 text-JSON 回退）。

## Q4 `/responses` 作为备选承载

**结论**：可用但**不推荐**承载 B2 结构化问答。实测三处硬伤：reasoning 吞掉整个 `max_output_tokens` 预算导致正文为空；响应体是 litellm 混血形状（`object` 与 Responses 顶层字段不自洽）；`model` 字段回填内部 provider 前缀。`/v1/messages` 在预算语义、原生 `tool_choice`、形状标准性上全面占优。

实测记录（探针C，2026-10-16，2969 ms，HTTP 200，`POST /responses`）：

- 请求体：`{"model": "glm-5.3-flashx", "max_output_tokens": 64, "input": "Is 7 a prime number? Reply with JSON {\"answer\":\"yes\"} or {\"answer\":\"no\"}"}`
- 响应（截断 ≤400 字符）：
  ```json
  {"id": "5f415376-326e-485d-8602-4c9c3fbff2f4", "created_at": 1792142851, "error": null, "incomplete_details": null, "instructions": null, "metadata": {}, "model": "zai/glm-5.3-flashx", "object": "chat.completion", "output": [{"type": "reasoning", "id": "rs_2909032532719924199", "status": "incomplete", "role": "assistant", "content": [{"type": "output_text", "text": "The user asks if 7 is a prime n
  ```
- 顶层字段全集（实测）：`created_at, error, id, incomplete_details, instructions, max_output_tokens, metadata, model, object, output, parallel_tool_calls, previous_response_id, reasoning, status, store, temperature, text, tool_choice, tools, top_p, truncation, usage, user`（其中回显的 `max_output_tokens: null`、`tool_choice: "auto"`、`tools: []` 与请求不符——litellm 回显层不忠实）
- **model 回填现象（实测复现 PM P7）**：请求 `glm-5.3-flashx` → 响应 `"model": "zai/glm-5.3-flashx"`（litellm 内部 provider 前缀回填；对照探针A 的 `/v1/messages` 原样回填无前缀）。
- **致命观察（budget 语义）**：`output = [{type:"reasoning", status:"incomplete", content:[output_text 约 60 token 的思考文本]}, {type:"message", status:"incomplete", content:[{type:"output_text", text:""}]}]`，顶层 `status: "incomplete"`；`usage: {"input_tokens": 33, "output_tokens": 64, "output_tokens_details": {"reasoning_tokens": 64, ...}, "total_tokens": 97}` —— **reasoning_tokens=64 = 全部输出预算，message 正文为空串**。同一问题同一预算在 `/v1/messages` 上（探针A）能同时产出 thinking+JSON 正文（output_tokens=53）。
- usage 形状：`input_tokens_details.cached_tokens`、`output_tokens_details.reasoning_tokens/text_tokens`、`cost: null`（openai 风格，与 anthropic 侧 cache_read/cache_creation 字段族不同）。

**取舍判定**：

| 维度 | `/v1/messages` | `/responses` |
| --- | --- | --- |
| 强制结构化 | `tools`+`tool_choice` 原生可用（探针B） | 未实测；仓内需 normalizePayload 兼容（timi-responses.ts），已知该路径会因载荷细节整包拒绝 |
| token 预算语义 | thinking+正文共享 max_tokens，64 够答小问题（探针A） | reasoning 独占预算，正文空（探针C），需数倍预算且不可控 |
| 响应形状 | 标准 anthropic，仅 id 格式/签名两处代理痕迹 | litellm 混血：`object:"chat.completion"`、回显字段失真、model 加前缀 |
| 与 pi 既有链路 | anthropic-messages adapter 已覆盖 | openai-responses adapter + timi 包装层已覆盖，但 B2 是 Python 直连，不经过 |

## Q5 systemone 官方 schema 细节（官方文档实测抓取）

**结论**：四种 question 的字段、`answers` 形状、confidence 语义与公式、官方错误码全部有官方定义；**注意 noul 答案没有 confidence 字段**（概率即答案），box 需要显式 danger-zone header 且官方标注未到生产级。抓取方式：Mintlify `<path>.md` 纯文本，`curl.exe -s -L`，HTTP 200。

### choice / score / noul / box 字段定义（来源 https://docs.typesafe.ai/api ，行号为该 md 文件内行号）

- **noul**（api.md L90-130）：`type:"noul"` + `instructions`（string|object|array，必填，yes/no 问题）；可选 `criteria: {"true": <什么算 yes>, "false": <什么算 no>}`（各为 string|object|array）。答案：`{"type":"noul","noul": <number>}`——"The yes/no answer on a scale from 0 (no) to 1 (yes)"（L246）。
- **choice**（api.md L131-168）：`type:"choice"` + `instructions`（必填）+ `criteria: map<option, string|object|array|null>`（**必填**，rubric 描述，null 表示无需补充；**每题最多 255 个选项**，L141）。答案：`{"type":"choice","choice": <最高概率选项>, "probabilities": {每选项→和为 1 的概率}, "confidence": <number>}`（L265-281）。
- **score**（api.md L169-196）：`type:"score"` + `instructions`（必填）+ `criteria: array<string|object|array>`（**必填**，有序等级描述，**≥2 且 ≤10 级**，L179）。答案：`{"type":"score","score": <概率加权值，可落在等级之间>, "legend": {等级号→描述}, "probabilities": {等级号(字符串)→概率，和为 1}, "confidence": <number>}`（L302-322）。
- **box**（https://docs.typesafe.ai/primitives/box.md ）：`type:"box"` + `instructions`（**无 criteria**）；必须随请求发 `TypeSafe-Danger-Zone-Images: true` header，官方标注 "Dreamer-ready...aren't yet up to our standards to call ready for production"（box.md B10-B12）。答案：`{"type":"box","box":{"top","bottom","left","right"}}`，四边为图像宽高分数 0..1，`left<right`、`top<bottom`（B77）；**没有"未找到"答案**——目标不存在也返回四个边（B136），应配 noul 问存在性；一题一框，多目标多题（B145）。

### answers 响应形状（api.md L197-236）

```json
{"model": "<执行的模型>", "answers": {"<问题id>": {"type": "...", ...}}, "usage": {"input_tokens": <int>, "output_tokens": <int>}}
```
- `answers` 是 `map<string, Answer>`，key 与请求 `questions` 的 key 一一对应；**问题 id 不发给底层模型、不参与推理**（L35）——即客户端可任意命名，answer 按 id 对齐回来。
- 响应只有 `model` / `answers` / `usage` 三个顶层字段（L201-221）。

### confidence 语义与取值范围（https://docs.typesafe.ai/confidence ）

- 取值 **0..1**，"collapses that shape into a single number from 0 to 1"（confidence.md L301）；**由概率分布形状派生，不是独立打分**："Confidence is derived from the probabilities"（L303 节标题）。
- 公式（confidence.md L376-442）：
  - noul：**不返回 confidence**（L384 "TypeSafe returns no separate confidence for it. The probability already carries..."）；文档建议需要时用 `|2p - 1|`（L389）。
  - choice：`(p_max − 1/n) / (1 − 1/n)`（L399）——最高概率超出均分的程度，均匀分布=0，全押=1。
  - score：`max(0, 1 − Σ p_i·|i−m| / MAD_unif)`（L425），按等级距离加权，邻近等级降 confidence 少、远等级降得多（L430-432）。
- 官方使用模式：confidence 三段式阈值（L321 "divide confidence into three ranges, each producing a different system behavior"）；"I don't know" 是有用信号（L313）；阈值随风险调整（L331，示例：`confidence < 0.5` 必须人工复核，`confidence > 0.9` 才可自动执行，L353-370）。

### 官方错误码（api.md L342-358，verbatim 表）

| 状态码 | 含义 |
| --- | --- |
| `400 Bad Request` | body 违反请求规则（非法 UTF-8、嵌套过深、非有限数、坏压缩体） |
| `401 Unauthorized` | 缺失/无效 API key |
| `413 Payload Too Large` | body 超 32 MiB |
| `415 Unsupported Media Type` | 不支持的 Content-Encoding / 多层压缩 |
| `422 Unprocessable Entity` | 请求体校验失败（缺必填字段/畸形 question），body 指明字段 |
| `429 Too Many Requests` | 超限流，退避后重试 |
| `529 Overloaded` | 上游过载，短暂后退重试 |

- 限流按 organization 计（models.md）；官方建议对 429/529 指数退避（api.md L358）；官方 SDK 示例策略 `RetryPolicy(max_retries=3, backoff_max=0.2, timeout=1.0)`（RQ-1 已录，https://docs.typesafe.ai/sdk/python/usage/basic ）。

## Q6 结论：B2 最小可行请求模板 + 置信度局限 + B1 对齐点

### B2 最小可行请求模板（实测可行组合）

```text
POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/messages
Headers:
  Content-Type: application/json
  Authorization: Bearer <TIMI_API_KEY>   # 运行期读 auth.json 的 timi 字段（见文首凭证说明）
  anthropic-version: 2023-06-01          # 实测被接受
Body:
{
  "model": "glm-5.3-flashx",
  "max_tokens": 1024,                          # ≥512：thinking 块与 JSON 正文共享预算（探针A: 小问题已耗 53）
  "temperature": 0,                            # 决策调用要确定性；0.2 实测被接受
  "system": "You are a decision function for an agent-team framework. Answer ONLY via the submit_decision tool. Keep reasoning short.",
  "tools": [{
    "name": "submit_decision",
    "description": "Submit the structured decision answer",
    "input_schema": {
      "type": "object",
      "properties": {                          # 每个问题一个属性；属性名 = question id（对齐 B1 answers 键）
        "route":      {"type": "string", "enum": ["coding", "review", "research"]},   # choice → enum
        "risk":       {"type": "integer", "minimum": 1, "maximum": 5},                # score → 有界整数
        "blocked":    {"type": "boolean"},                                            # noul → boolean
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}                  # 模型自报，见局限声明
      },
      "required": ["route", "risk", "blocked", "confidence"]
    }
  }],
  "tool_choice": {"type": "tool", "name": "submit_decision"},
  "messages": [{
    "role": "user",
    "content": "state: <任务状态序列化>\nquestions: <每题一行 id+说明+判据，禁止 systemone 的 state/questions 顶层字段>"
  }]
}
解析与校验规则（按优先级）:
  1. 状态码非 200 → 按 Q3 类别表处置（400/403 不重试；429/5xx 指数退避；非 JSON body 一律按协议错误）。
  2. HTTP 200 但 body 含 "error" 字段 → litellm 透传错误，按 Q3 第 6 类处置。
  3. 取 content 中 type=="tool_use" 的块（忽略 thinking/text；即使强制 tool_choice 也会出现 text 块，探针B 实测）。
  4. 校验 input：JSON 可解析、必需键齐全、enum/min/max 越界检查；不合格 → 1 次修正重发（把校验错误回喂 user 消息），再失败走回退。
  5. 回退路径（tool 路径不可用时）：提示词约束 JSON + 解析 text 块 + 同一校验器（探针A 证明该模型能严格遵守，n=1）。
  6. stop_reason 语义：tool_use=成功；end_turn 且无 tool_use=模型未走工具，先试 text 回退再判失败。
禁止携带：response_format（实测 400）、state/questions（PM 探针实测 400 unknown_fields）、store（timi-responses.ts:19 佐证该网关拒收）。
```

### 错误类别清单

见 Q3 表格与 8 条处置清单（schema 400 / 模型 403 / 路由 404-HTML / 限流 429 无 retry-after / 5xx-超时 / 200-含错误体 / 非 JSON 成功体 / 强制工具下无 tool_use 块）。与 B1（systemone 官方 400/401/413/415/422/429/529）的映射：400↔422 同为校验类（语义不同：llmproxy 是 unknown_fields，typesafe 是字段级 422）、429↔429、5xx↔529、401 类 B2 侧未单测（key 缺失时网关行为未验证）。

### 置信度局限声明

- **B2 的 confidence 是模型自报数字，不是校准概率**。实测探针B 中 glm-5.3-flashx 对平凡事实自报 `confidence: 1.0`——典型过自信；无任何分布语义背书，与 `usage` 无关联，不可用于阈值自动化。B2 侧 confidence 只能当**弱排序信号**（同模型同 prompt 下相对比较），不得当作 B1 的 `confidence` 等价物。
- **B1 的 confidence 有官方定义**：0..1、由概率分布形状派生、公式公开（choice/score 见 Q5；noul 无 confidence 字段，概率即答案）——两套语义**不可比、不可互换**。B2→B1 切换时，凡用 confidence 做门控的代码必须重新标定（官方三段式阈值模式只适用于 B1）。
- 修正建议：B2 的 `input_schema` 里的 confidence 属性可改名 `self_reported_confidence` 以免调用方误用；或 B2 模板干脆不请求该字段，置信度留空，等 B1。

### B1（jev/systemone）可用时的接口对齐点

1. **键对齐**：B2 模板的 tool `input_schema` 属性名 = B1 `questions` map 的 key = B1 `answers` map 的 key（api.md L35：id 不参与推理）。切换时只需把「schema 属性」翻译成「Question 对象」（choice→criteria map、score→criteria 数组、noul→boolean、box→不适用 B2）。
2. **state 对齐**：B2 把 state 编码进 system/user 消息文本；B1 是结构化 `state` 顶层字段（string|object|array）。序列化约定（对象 vs 拍平文本）是切换时唯一需要统一的编码层。
3. **响应对齐**：B2 `tool_use.input` ≈ B1 `answers`（键结构相同）；B2 无 probabilities/noul-p，B1 有——依赖概率的下游逻辑必须走 B1，B2 只有离散值+自报置信度。
4. **错误对齐**：429 两边都有（B2 无 retry-after 头，B1 官方要求退避+529）；校验错误语义不同（unknown_fields vs 422 字段级）。
5. **鉴权/传输对齐**：同为 `Authorization: Bearer`；endpoint 从 llmproxy `/v1/messages` 换成 systemone `/v1/systemone`（B1 经 llmproxy 的实际入口仍未暴露——PM 三轮探针 20+ 路径全 404，D-1 仍开）；box 类型需要额外 header，B2 传输模板无需预留。
6. **usage 对齐**：字段名不同（anthropic 侧 `cache_read_input_tokens` 等 vs systemone `input_tokens/output_tokens`），计费/预算统计需适配层。

## 残留与未验证

- **流式 SSE 形状未实测**（pi 主链路永远 stream:true，`anthropic-messages.ts:560`）；B2 非流式模板不受影响，但若未来复用 packages/ai 的 anthropic-messages adapter 需补测 message_delta 里 usage/stop_reason 的到达时点。
- **5xx / 超时 / 连接失败的网关真实返回体未实测**（无法安全诱导）；处置语义沿用仓内 `provider-retry.ts` 策略。
- **`/responses` 的 `tools`+`tool_choice` 未实测**（预算已用尽 3/3）；其 reasoning 独占预算问题（探针C）已足以否决其作为 B2 承载。
- **`anthropic-version` header 是否必需未单测**（所有探针都带它且成功）。
- **temperature=0 未实测**（实测 0.2）；决策调用的确定性参数需在实现时自测。
- **纯提示词 JSON 约束的可靠性样本量 n=1**（探针A）；提示词回退路径投产前应做小样本评估（≥20 次）。
- **max_tokens=1024 预算值是推断**（探针A 实测小问题耗 53；真实决策 prompt 更长，thinking 消耗未建模），实现时应按 P95 观测再调。
- 429（jev-latest 在 `/v1/messages`）是否消退仍属上游配额问题，本轮未复测 jev（与本调研目标无关，B2 用 glm 不受影响）。
- B2 单次调用延迟实测 2.5-5.4s（含 thinking）；决策调用在 mw 看门狗语境下的 SLA 未评估。

## 上下文来源

| 来源 | 用途 |
| --- | --- |
| 实机探针 A/B/C/D（本轮，2026-10-16） | Q1/Q2/Q3/Q4 全部实测证据；脚本与原始响应体在临时目录，正文已按 ≤400 字符脱敏截断录入 |
| PM 探针记录 `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-live-probe-20261016.md` | Q3 的 429/403/404-HTML/200-含错误体证据；`state`/`questions` 400 证据；`/responses` 前缀回填先例（P7） |
| `packages/ai/src/providers/timi.ts:8` | baseUrl 常量（timiai，非 timia） |
| `packages/ai/src/providers/data/timi.json`（glm-5.3-flashx 条目） | reasoning=true、ctx 200K、maxTokens 64K、cost 全 0 标注 |
| `packages/ai/src/api/anthropic-messages.ts:556-566` | SDK maxRetries:0 + retryProviderRequest + 恒 stream:true（:560） |
| `packages/ai/src/utils/provider-retry.ts:1,23-35,51-60` | 可重试状态码、x-should-retry、retry-after 处理、60s 上限 |
| `packages/ai/src/utils/retry.ts` | 错误文本级可重试分类 + quota 不可重试清单 + PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC |
| `packages/ai/src/api/timi-responses.ts` | /responses 路径的网关净 schema 兼容（store 拒收、空 tool description） |
| https://docs.typesafe.ai/api （api.md，HTTP 200 抓取） | Q5：question 字段、answers/usage 形状、错误码表 |
| https://docs.typesafe.ai/primitives/box.md （HTTP 200 抓取） | Q5：box 字段、danger-zone header、无"未找到"语义 |
| https://docs.typesafe.ai/confidence （HTTP 200 抓取） | Q5/Q6：confidence 公式（noul/choice/score）、三段式阈值 |
| https://docs.typesafe.ai/llms.txt （HTTP 200 抓取） | Q5：文档索引（box/confidence/patterns 定位） |
| RQ-1 证据 `spec-typesafe-api-20261016.md` | Q5 交叉核验（429/529、RetryPolicy、模型 id/别名）、Q6 对齐点 |
| RQ-3 证据 `spec-jev-decision-surface-20261016.md` | Q6：B1 进入决策面的配置/回退/反馈链约束 |
