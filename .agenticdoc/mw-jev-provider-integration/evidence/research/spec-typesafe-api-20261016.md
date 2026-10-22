# typesafe.ai API 契约调研（RQ-1 · mw-jev-provider-integration）

- 任务：jev-rq1-typesafe-docs（owner key: mw-console-storm-hardening）
- 日期：2026-10-16 · 调研方式：`curl.exe` 拉取官方文档（Mintlify，取 `<path>.md` 纯文本变体，HTML 原文未落仓）
- 资料源索引：https://docs.typesafe.ai/llms.txt （官方 llms.txt 文档索引）
- 核心结论（一句话）：**typesafe.ai 的 Jev 不是 LLM，是"System One"结构化决策 API；只有一个自定义端点 `POST /v1/systemone`，与 packages/ai 的任何 chat 协议族（anthropic-messages / openai-responses / openai-chat-completions）均不对齐。**

---

## 七问逐条结论

### Q1 端点契约

**结论**：唯一业务端点是 `POST https://api.typesafe.ai/v1/systemone`（请求 = `state` + `questions` 映射，响应 = `answers` 映射，一次性 JSON），另有 `GET /v1/models` 列模型；**不存在 chat/completions 端点**，与 packages/ai 现有三种 api 类型均不对齐。

官方原文摘录（api.md）：
```http
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API_KEY>
Content-Type: application/json
```
请求体仅三个字段：`state`（string | object | array）、`model`（string）、`questions`（map<string, Question>，type ∈ choice / score / noul / box）。

来源：https://docs.typesafe.ai/api · https://docs.typesafe.ai/introduction/quickstart#call-it-the-api

### Q2 鉴权

**结论**：单一 header `Authorization: Bearer <API_KEY>`；key 从 `https://console.typesafe.ai/keys` 获取，官方建议存 env `TYPESAFE_API_KEY`；限流按 **organization** 维度计，文档未见 team/project 维度凭据。

官方原文摘录（models.md / quickstart.md）：
```
Get an API key from the TypeSafe console (https://console.typesafe.ai/keys).
Rate limits are set per organization.
```

来源：https://docs.typesafe.ai/introduction/quickstart · https://docs.typesafe.ai/models#rate-limits

### Q3 模型族与 id

**结论**：单一模型族 Jev，两个版本 id + 两个别名；**没有 reasoning 能力/参数**，输入 text-only；上下文默认 64k per-request / 32k per-question（加 header `TypeSafe-Danger-Zone-Long-Context: true` 升到 262k）；响应 `model` 字段回填版本化 id（如 `jev-1.13.0`）。

官方原文摘录（models.md）：
```
| Model ID | jev-1.14.0 | jev-1.13.0 |          （Jev 1.14 自 2026-10-14 起可用）
| Context length | 64k per-request / 32k per-question | （同左）
| Input | Text | Text |
| Alias jev-latest → jev-1.13.0 | Alias jev-preview → jev-1.14.0 |
```
价格 $42/Btok（十亿输入 token）/ $0.042/Mtok，输出 token 免费。`GET /v1/models` 当前只列别名，但版本化 id 始终可直接用作 `model` 值。

**与仓内现状的差异**：`packages/ai/src/providers/data/timi.json` 的 jev-latest 条目标注 `200K ctx`、`reasoning=true`；官方直连契约为 64k/32k（262k 需显式 header）且无 reasoning 字段。若 timi 代理未做协议改写，这两个标注与上游不符。

来源：https://docs.typesafe.ai/models

### Q4 限流与配额（429 语义）

**结论**：限流按 org 计，双口径 **tokens/sec + requests/sec**；超限返回 `429 Too Many Requests`，上游过载另有 `529 Overloaded`；官方建议指数退避并遵循 `retry-after` header；官方 SDK 默认自动重试（示例策略 `RetryPolicy(max_retries=3, backoff_max=0.2, timeout=1.0)`）。具体 RPM/TPM 数值不在文档中，发布在 `https://console.typesafe.ai/rate-limits`。

官方原文摘录（api.md / models.md）：
```
| 429 Too Many Requests | You have exceeded your rate limit. Back off and retry after a short delay. |
| 529 Overloaded | TypeSafe is temporarily overloaded. Retry after a short delay. |
retry the request with exponential backoff instead of retrying immediately
```

**关联仓内记录**：mini-spec（mw-timi-models-add）实测 anthropic `/v1/messages` 429 —— 429 是 typesafe 体系真实存在的行为，但按本文档 `/v1/messages` 本身不是 typesafe 的端点，429 更可能来自 timi 代理层或 org 级配额，需在 timi 侧核实。

来源：https://docs.typesafe.ai/api#errors · https://docs.typesafe.ai/api#handling-rate-limits · https://docs.typesafe.ai/models#rate-limits

### Q5 reasoning/thinking 参数

**结论**：**不存在**。API 请求体只有 `state` / `model` / `questions`，无任何 reasoning/thinking/extended-thinking 参数；Jev 是决策模型不生成文本，最接近的概念是响应侧只读的 `confidence`（由 probabilities 派生，0–1，不可作为请求参数传入）。

官方原文摘录（introduction.md / api.md）：
```
No text generation, no parsing. You get typed values and probability distributions...
（请求体字段全集：state, model, questions —— 无其它顶层字段）
```

来源：https://docs.typesafe.ai/api#request-body · https://docs.typesafe.ai/introduction · https://docs.typesafe.ai/confidence

### Q6 流式支持（SSE）

**结论**：**无流式支持**。API reference 全文无 `stream` 参数、无 SSE/`text/event-stream` 事件定义，响应为一次性 JSON（grep 全部 7 份文档：streaming API 相关 0 处；唯一 "stream" 出现在描述 LLM 与 Jev 的差异时）。

官方原文摘录（coding-agents.md）：
```
Coding agents rely on an LLM that streams text, calls tools, and edits files...
Jev does none of that.
```

来源：https://docs.typesafe.ai/api · https://docs.typesafe.ai/introduction/coding-agents

### Q7 coding-agents 页对 pi 类 agent 的建议

**结论**：官方明确 Jev **不是** coding-agent 的后端模型（"There is no `model: \"jev-latest\"` setting that turns your coding agent into a Jev-powered agent"）；推荐做法是给 coding agent 安装 TypeSafe agent skill（Claude Code plugin，或通用 `npx skills add typesafe-ai/skills --skill typesafe-ai`；SKILL.md 开源在 GitHub typesafe-ai/skills），让 agent **写调用 Jev API 的代码**，而非把 Jev 当模型驱动 agent。文档未提及 pi；也无需 base_url/model 字符串格式的接入说明——唯一的 env 约定是 `TYPESAFE_API_KEY`，唯一的端点是 `https://api.typesafe.ai/v1/systemone`。

官方原文摘录（coding-agents.md）：
```
Jev is not a drop-in replacement for the LLM behind Claude Code, Cursor, opencode...
There is no `model: "jev-latest"` setting that turns your coding agent into a Jev-powered agent.
Install the TypeSafe agent skill. It gives Claude Code, Codex, and other agents full context on the Jev API...
```

来源：https://docs.typesafe.ai/introduction/coding-agents · https://docs.typesafe.ai/agent-skill · https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md

---

## 补充：jev-latest 与 use-case-map 的对应（任务审计目标第 4 项）

use-case-map 按行业/决策形态组织，不按模型 id 分桶；Jev 是当前唯一模型族，所有桶都用它。与 goal.md（Agent Team 协作框架）最相关的桶：

- **Harness Engineering**："model routing, semantic context retrieval, LLM error detection and guardrails, reasoning trace classification at lightspeed and a fraction of the cost" —— 与 mw 的 PM 分诊 / review 路由 / worker 产出把关同构。
- **Model routing / Routing**："chooses which LLM receives each prompt"、"escalate requests that need a more expensive model" —— 与 provider 路由架构互补（Jev 可做便宜的路由判据，本身不做生成）。
- 任务形态映射中 Jev 覆盖：Classification / Detection / Scoring / Routing / Verification（均返回概率 + confidence）。

来源：https://docs.typesafe.ai/concepts/use-case-map

---

## 对 packages/ai 的接线建议

1. **对齐哪个 api 类型：都不对齐。** 上游唯一端点是自定义 `POST /v1/systemone`（state+questions→answers，非流式，Bearer 鉴权），不是 anthropic-messages / openai-responses / openai-chat-completions 的任何一个。把 jev-latest 以 `api=anthropic-messages` 挂进模型目录与官方契约冲突——历史上 `/v1/messages` 429 与 `/responses` "Unmapped LLM provider" 两个现象与该结论一致（typesafe 没有这两种协议；429 若来自 typesafe 也只能出现在它自己的端点上，或来自 timi 代理层）。
2. **缺什么（若坚持接进 packages/ai）**：需要新的 api 类型（如 `typesafe-systemone`）+ provider 实现：请求映射（消息/工具语义 → state+questions 无官方映射，需自研约定）、`Authorization: Bearer`、非流式响应、429/529 指数退避（`retry-after`）、`GET /v1/models` 接线。**不建议**：把 chat 请求强行合成 questions 属于无官方依据的发明，且 Jev 不具备 coding-agent 所需的文本生成/工具调用能力，作为 coding 模型不可用。
3. **更贴合 goal.md 的定位**：Jev 适合做 mw 框架内的**辅助决策服务**（PM 任务分诊、review 结论复核、worker 产出 gate 的廉价校验——对应官方 Harness Engineering / Guardrails 桶），由 mw 后台（Python）或独立 client 直接调 `/v1/systemone`，不进入 packages/ai 的 chat 模型目录；coding-agent 主模型仍由 LLM 提供。
4. **若保留 timi.json 现有条目**：须先核实 timi 代理（llmproxy）对 jev 实际暴露的协议——若 timi 已把 jev 映射为 anthropic-messages 兼容端点，则以 timi 实测为准（官方文档只证明 typesafe 直连不支持）；同时修正目录标注（ctx 应为 64k/32k、262k 需 header；reasoning=true 无上游依据；输出 token 免费、计价 $42/Btok 输入）。
5. **凭证隔离**：按 goal.md 凭证约束，需要 Jev 的 worker 只注入 `TYPESAFE_API_KEY`；与其它 provider key 互斥。

## 上下文来源

| 页面 | URL | 用途 |
| --- | --- | --- |
| Introduction | https://docs.typesafe.ai/introduction | 平台定位（Q1/Q5） |
| Quick start | https://docs.typesafe.ai/introduction/quickstart | 端点/鉴权/响应形状（Q1/Q2） |
| Jev with coding agents | https://docs.typesafe.ai/introduction/coding-agents | Q6/Q7 |
| Example use cases | https://docs.typesafe.ai/concepts/use-case-map | use-case 桶映射 |
| Models | https://docs.typesafe.ai/models | Q3/Q4（模型 id、上下文、限流、别名） |
| API reference | https://docs.typesafe.ai/api | Q1/Q4/Q5/Q6（请求/响应/错误全集） |
| SDK basic usage | https://docs.typesafe.ai/sdk/python/usage/basic | Q4（RetryPolicy 默认值） |
| llms.txt | https://docs.typesafe.ai/llms.txt | 文档索引 |

抓取方式备注：Mintlify 站点支持 `<path>.md` 取纯文本（本次 7 个文件均为 HTTP 200，原文 HTML 未落仓，证据只留摘录）。
