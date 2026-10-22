# FIX-K：给 timi provider 补上 Jev 自己的 api（`typesafe-systemone`）

- type: coding
- owner key: mw-decision-substitution
- 问题（用户 2026-10-20 指出）：`timi/jev-latest` 现在走的是 anthropic 聊天协议，和 glm、deepseek
  一样发到 llmproxy 的 `/v1/messages`，所以必然拿不到答案（实测持续 429）。Jev 是**问答/决策**接口，
  不生成文本、不流式，timi provider 根本没实现它的 api —— 本卡补上。

## 实测证据（2026-10-20，PM 直跑，供你定位，不要重复联网）

- `packages/ai/src/providers/timi.ts` 只有 `anthropic-messages` 与 `openai-responses` 两个 api，
  21 行；`packages/ai/scripts/generate-models.ts:724-736` 把 `jev-latest` 声明为
  `api: "anthropic-messages"`、`reasoning: true`、`contextWindow: 200000`（三处都与官方契约不符）。
- llmproxy：`POST /v1/systemone`（及 `/systemone`、`/typesafe/v1/systemone` 等 10 条路径）**全部 404**；
  `GET /v1/models/jev-latest` **200**；`POST /v1/messages` model=jev-latest **429**。
- 官方契约：`POST {baseUrl}/v1/systemone`，body `{model, state, questions}`，Bearer 鉴权，
  响应 `{model, answers, usage}`，题型 `noul|choice|score|box`，**无流式、无文本生成**
  （`https://api.typesafe.ai/api/system-one.md`，本地副本 `H:\tmp\ts-api.md`）。

## 本卡要做的

1. 新增 `packages/ai/src/api/typesafe-systemone.ts`，导出 `typesafeSystemoneApi(): ProviderStreams`：
   - **输入约定**（写进文件头注释）：取最后一条 user 消息的文本；必须是 JSON 对象且含 `state` 与
     `questions` 两个键，否则不发明映射、直接返回 `error` 事件，文本为
     `typesafe-systemone expects the last user message to be a JSON object {"state": ..., "questions": {...}}`。
   - **请求**：`POST ${model.baseUrl}/v1/systemone`，`Authorization: Bearer <apiKey>`、
     `Content-Type: application/json`，body 只放 `{model: model.id, state, questions}`（不透传 chat 字段）。
   - **响应**：一次性 JSON；把 `answers` 以紧凑 JSON 作为 assistant 文本返回，`usage` 的
     `input_tokens`/`output_tokens` 映射进 `AssistantMessage` 的用量字段；`model` 字段回填上游返回的
     `model`（不存在则用 `model.id`）。
   - **不流式**：单次 fetch，事件序列按 `packages/ai/src/types.ts` 的 `AssistantMessageEvent` 联合体构造
     （`start` → 文本增量 → `done`）；非 2xx 时按现有 api 模块的惯例返回 `error` 事件
     （参考 `packages/ai/src/api/pi-messages.ts` 的结构，先读它再写）。
   - 429/5xx 不自行重试（保持简单），错误文本带状态码与响应体前 200 字符。
2. `packages/ai/src/providers/timi.ts`：
   - api map 加 `"typesafe-systemone": typesafeSystemoneApi()`，并放宽 `Provider<...>` 的 api 联合类型。
   - 构造 models 时对 **`jev-latest`** 覆写 `api: "typesafe-systemone"`（其余模型不动），
     附注释说明：目录数据（`generate-models.ts`）的 api 字段留待下一次再生效的目录刷新（本卡禁止
     改 `models.generated.ts`，也禁止跑生成脚本——它需要联网）。
3. `packages/ai/CHANGELOG.md`：`## [Unreleased]` → `### Added` 追加一条（英文、无 emoji）。

## 必做用例（新建 `packages/ai/test/typesafe-systemone.test.ts`）

先找本仓已有的 fetch stub 惯例（在 `packages/ai/test` 里 `grep -rl "globalThis.fetch"` 挑一个最接近的照做），
用 stub 而不是真网络：

1. 合法 `{state, questions}` → 请求 URL 以 `/v1/systemone` 结尾、body 恰好是
   `{model, state, questions}`（无 `messages`/`stream`/`tools` 泄漏）、header 带 `Bearer`；
   assistant 文本是 `answers` 的紧凑 JSON。
2. 非 JSON 用户消息 → `error` 事件，文本含 `expects the last user message`，且**零 fetch 调用**。
3. 上游 429 → `error` 事件，文本含 `429`。
4. `timiProvider()` 返回的 `jev-latest` 条目 `api === "typesafe-systemone"`，其它模型 api 不变。

## 写入允许面

- `packages/ai/src/api/typesafe-systemone.ts`（新建）
- `packages/ai/src/providers/timi.ts`
- `packages/ai/test/typesafe-systemone.test.ts`（新建）
- `packages/ai/CHANGELOG.md`

## 写入禁止面

- `packages/ai/src/models.generated.ts`、`packages/ai/scripts/generate-models.ts`（目录刷新另卡）
- `packages/ai/src/api/` 下其它既有文件、`packages/ai/src/types.ts`
- `packages/multi-workers/**`、`packages/coding-agent/**`
- `docs/**`、`.agenticdoc/**`
- 禁止 `git` 写操作、`npm run check`、`npm run build`、全量 vitest、任何真实网络请求（不要调 llmproxy 或 typesafe）、`Set-Content`

## 验收命令

```bash
cd packages/ai
npx tsgo --noEmit
npx biome check src/api/typesafe-systemone.ts src/providers/timi.ts test/typesafe-systemone.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/typesafe-systemone.test.ts
```

## 交付格式

`report.md`：结论 / 改动落点（文件:行）/ 三条验收命令输出原文 / 残留（必须写明：
**llmproxy 当前无 `/v1/systemone` 路由，本卡无法联网验证真调用**）/ 未覆盖面。

## 种子

- 目标锚点：`.agenticdoc/goal.md`（jev 作为决策模型，而不是聊天模型）
- 现状锚点：`packages/ai/src/providers/timi.ts:1-21`（api map 只有两个）、`:8`（baseUrl 默认值）、
  `packages/ai/scripts/generate-models.ts:724-736`（jev-latest 目录条目）、
  `packages/ai/src/utils/event-stream.ts:4-80`（`AssistantMessageEventStream`）、
  `packages/ai/src/api/pi-messages.ts`（最小 api 模块模板，先读）
- 契约来源：`https://api.typesafe.ai/api/system-one.md`；本仓调研
  `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-typesafe-api-20261016.md`

## 改动历史

- 2026-10-20 建卡：用户指出 timi provider 未实现 jev 的 api，jev-latest 被误挂在 anthropic-messages 上。
