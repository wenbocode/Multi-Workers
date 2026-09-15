# 调研留底：design 阶段关键取证（2026-09-10）

> Key: ai-baseline-repair
> 支撑：design.md §0/D-001~D-008 的每个架构选择

## 1. 上游可达性与修复参照（D-001/D-002 的依据）

- `upstream` remote 已添加（https://github.com/earendil-works/pi-mono.git），`upstream/main` = 4bd3f48df（2026-09-10 仍在维护，近期提交全是 catalog 维护：`fix(ai): remove retired GPT-5.4 Codex models` 等）
- 10/11 个出错共享测试文件上游晚于我们更新：empty/tokens/total-tokens/unicode/abort/context-overflow = 08-19 (164507bba)；tool-call-id-normalization + openai-completions-empty-tools = 09-07 (aa23e784c)；stream = 09-10 (2e6fe2f98)
- `cross-api-thinking-history.test.ts` **不在 upstream**（fork 特有）——只能手工修（D-003）
- 上游 cloudflare-ai-gateway.ts（758a0ee9b, 08-28）的 TS2353 修法：显式 `createProvider<CloudflareAIGatewayApi>` + 类型别名 + 「gateway catalog 随时间增删 workers-ai 条目，api map 钉死三 API 是刻意的」注释——D-001 逐字镜像

## 2. 上游测试 diff 逐 hunk 判定（D-002 选择性镜像清单）

| 文件 | 上游 hunk | 采纳 | 原因 |
|---|---|---|---|
| abort | claude-opus-4-1-20250805 → claude-sonnet-4-6 | 是 | 我们 anthropic 目录含 sonnet-4-6，thinking abort 意图保留 |
| abort/tokens | 新增 qwen-token-plan-individual 块 | 否 | 该 provider 不在我们 generator 输出（依赖 54 文件分歧外的 src），GC-A4 |
| empty-tools | 仅注释 URL 修正 (issues/3649) | 是 | 无害 |
| tool-call-id-norm | github-copilot gpt-5.2-codex → gpt-5.5 ×4 | 是 | 我们 github-copilot 目录含 gpt-5.5（已验证） |
| empty/total-tokens/unicode/context-overflow | gemini-2.0-flash → gemini-2.5-flash | 是 | 我们 google 目录含 gemini-2.5-flash |
| 同上 | 新增 qwen-token-plan-individual 块 ×4 | 否 | 同 abort |
| （无上游对应）gateway+kimi 8 处 | 上游未改这些行 | 自定 | 见 §3 |

## 3. models.dev 实时查证（gateway+kimi 重定向的依据，2026-09-10）

`GET https://models.dev/api.json`（Python urllib，30s 超时）：
- cloudflare-ai-gateway provider：44 模型，**workers-ai upstream 条目 = 0**，kimi 仅 `moonshotai/kimi-k3`（openai-completions）
- 我们本地 `data/cloudflare-ai-gateway.json` 与该实况一致（再生成零 diff）
- 结论：`getModel("cloudflare-ai-gateway", "workers-ai/...")` 在我们 generator 下无静态类型解；上游测试保留该行依赖其新一代 generator 的合成逻辑（与我们的 generate-models.ts 有 485+/443- 分歧，超出本 key 范围）
- 重定向方案：`("cloudflare-workers-ai", "@cf/moonshotai/kimi-k2.6")`——同模型同 api（openai-completions/compat），文件内已有 4 处同款先例（empty:310、tokens:165、total-tokens:316、unicode:501）

## 4. 目录与类型面现场（D-003/D-005 的依据）

- `StopReason = "pending"|"stop"|"length"|"toolUse"|"error"|"aborted"|"deferred"`（types.ts:388）——"end_turn" 已废
- 流终止事件 = `{ type: "done"; reason: ...; message: AssistantMessage }`（types.ts:525）——无 "stop" 事件、payload 字段是 `.message`
- `OpenAICompletionsCompat.maxTokensField` 存在（types.ts:545）、`OpenAIResponsesCompat` 无此字段——union 直取报 TS2339，须窄化
- anthropic 直连目录用连字符 id（claude-sonnet-4-6），**cloudflare-ai-gateway 目录用点号 id（claude-sonnet-4.5）**——stream:707 的修复依据
- timi-dispatch.test.ts:30 TS1294 = `constructor(readonly captured: unknown)` 参数属性（erasableSyntaxOnly 违例）

## 5. CI/分支事实（D-007 归因输入）

- ci.yml 仅 `ubuntu-latest`，push 仅 `branches: [main]`；dev/AgentTeam 推送不触发 CI → 整个 pi 导入栈从未被 CI 覆盖
- origin/main = 651d5d6a（导入前）；origin/dev/AgentTeam = 357296d89；本地 = 28f898a7f（新提交 mw-widget-terminal-lifecycle 修复）
- 本机无 gh CLI、GitHub API 403（私有仓无 token）→ CI 历史不可直查，AC-007 以 worktree 本地复现替代并标注置信度
