# FIX-N：`packages/ai` 的 jev api 改指向 timiai 的 `/v1/decisions`

- type: coding
- owner key: mw-decision-substitution
- 前置：FIX-K 建了 `typesafe-systemone` api，指向 `{baseUrl}/v1/systemone`。用户 2026-10-20 裁定
  **「是要接 `timi/jev-latest`，不是 typesafe」**，且 timiai 网关的真实路径是
  `POST {baseUrl}/v1/decisions`（已实测 200，见 `.agenticdoc/mw-decision-substitution/jev接入.md`）。
  本卡把 api 改名并改路径。

## 契约（timi decisions，实测）

```
POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions
Authorization: <timi key>            # 平台个人 API Key
Content-Type: application/json
{"model":"jev-latest","state":<str|obj|array>,"questions":{<qid>:{type,instructions,criteria?}}}
→ {"model":"jev-latest","answers":{...},"usage":{"input_tokens":N,"output_tokens":N}}
```

无流式；`choice`/`score` 的 `criteria` 必填，`noul` 可选；题型只有 `noul|choice|score`。

## 本卡要做的

1. 把 `packages/ai/src/api/typesafe-systemone.ts` 重命名为 `packages/ai/src/api/timi-decisions.ts`，
   导出 `timiDecisionsApi(): ProviderStreams`：
   - 输入约定不变（最后一条 user 消息必须是含 `state` + `questions` 的 JSON，否则零请求 `error`），
     错误文案改成 `timi-decisions expects the last user message to be a JSON object {"state": ..., "questions": {...}}`。
   - 请求 URL 改为 `${baseUrl}/v1/decisions`；header `Authorization: <apiKey>`（**不加 `Bearer` 前缀**，
     文档与实测都是裸 key；加前缀会 401 风险，别猜）。
   - body 仍只 `{model, state, questions}`；响应解析、`answers` 作文本、usage 映射、非 2xx 错误文本保持不变。
   - 文件头注释改写成 timi decisions 契约（出处：`jev接入.md`；并注明没有 box、没有自由文本）。
2. `packages/ai/src/providers/timi.ts`：api map 键从 `"typesafe-systemone"` 改成 `"timi-decisions"`，
   `TimiApi` 联合类型同步；对 `jev-latest` 的覆写值改成 `"timi-decisions"`（注释同步）。
3. `packages/ai/test/typesafe-systemone.test.ts` → `packages/ai/test/timi-decisions.test.ts`：
   用例保留 6 条，但断言 URL 以 `/v1/decisions` 结尾、header 是**裸 key**（`authorization === key`，
   不是 `Bearer ...`），其余（body 精确匹配、非 JSON 零请求、429 报错、provider 只改 jev-latest）不变。
4. `packages/ai/CHANGELOG.md`：改写刚才那条 `[Unreleased]/### Added` 条目为
   `Added the timi-decisions API ... POST /v1/decisions ... instead of the chat endpoint`。

## 写入允许面

- `packages/ai/src/api/timi-decisions.ts`（新建；旧 `typesafe-systemone.ts` 删除）
- `packages/ai/src/providers/timi.ts`
- `packages/ai/test/timi-decisions.test.ts`（新建；旧 `typesafe-systemone.test.ts` 删除）
- `packages/ai/CHANGELOG.md`

## 写入禁止面

- `packages/ai/src/models.generated.ts`、`packages/ai/scripts/generate-models.ts`
- `packages/ai/src/types.ts`、`packages/ai/src/api/` 下其它文件
- `packages/multi-workers/**`、`packages/coding-agent/**`、`docs/**`、`.agenticdoc/**`
- 禁止 `git` 写操作、`npm run check`、`npm run build`、全量 vitest、任何真实网络请求、`Set-Content`

## 验收命令

```bash
cd packages/ai
npx tsgo --noEmit
npx biome check src/api/timi-decisions.ts src/providers/timi.ts test/timi-decisions.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/timi-decisions.test.ts
```

## 交付格式

`report.md`：结论 / 改动落点（文件:行）/ 三条验收输出原文 / 残留（写明：本卡不联网，
真调用由 PM 用 `mw decide` 或 `pi -p` 验）/ 未覆盖面。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 接入契约：`.agenticdoc/mw-decision-substitution/jev接入.md`（`/v1/decisions`、criteria 规则、响应字段表）
- 现状锚点：`packages/ai/src/api/typesafe-systemone.ts:1-40`（头注释与常量）、`:150-175`（请求 URL/header）；
  `packages/ai/src/providers/timi.ts:11`（联合类型）、`:20-28`（jev 覆写）、`:33`（api map）
- PM 实测（2026-10-20）：`POST /v1/decisions`（裸 timi key）→ 200；同一 key 走 `/v1/systemone` → 404

## 改动历史

- 2026-10-20 建卡：timi 网关的真实决策入口是 `/v1/decisions`，不是 typesafe 的 `/v1/systemone`。
