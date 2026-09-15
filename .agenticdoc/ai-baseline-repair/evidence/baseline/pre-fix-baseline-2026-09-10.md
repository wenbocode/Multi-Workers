# 修复前基线（2026-09-10，ai-baseline-repair 开工时）

> L2 对比锚点：所有「修复后」数字以此为对照。来源：spec-baseline-forensics-2026-09-10.md（tsgo 26 错清单）+ 当日两次 vitest 运行。

## 1. tsgo（`npx tsgo --noEmit`，packages/ai 树内）

**26 个错误**：src 1（cloudflare-ai-gateway.ts:19 TS2353 "openai-completions" 不在 api map）+ test 25。
按码：TS2345×15（过时 model ID：`gpt-5.2-codex`、`workers-ai/@cf/moonshotai/kimi-k2.6`、`gemini-2.0-flash` 等）/ TS2352×4（ResponseInputItem cast）/ TS2339×2 / TS1294（timi-dispatch 参数属性，非可擦语法）/ TS2353 / TS2367 / TS2741 / TS2322 各 1。
最大簇：cross-api-thinking-history.test.ts 8 处（StopReason "end_turn" vs "stop"、流事件 union、fixture baseUrl 缺失）。

## 2. packages/ai 运行时套件（vitest --run，包根）

**8 failed**（全部为目录-测试漂移类）：baseten-models（GLM-5.2 compat 形状）、fireworks-models（Fire Pass turbo router 模型缺失）、github-copilot-oauth（`expected ['gpt-4.1'] got []`）、openai-completions-tool-choice（opencode `maxTokensField` undefined）、timi-models（15≠14：目录多 glm-5.3）、及 empty-tools/gateway 相关。

## 3. 下游包（同机 Windows）

- packages/agent：2 个失败**文件**（nodejs-env + tools bash），13 个失败测试。
- packages/coding-agent：85 个失败测试（ai 修复后复核为 76，差值 9 个由 catalog 依赖连带修复）。

## 4. CI 语境

ci.yml 仅 ubuntu-latest（push/PR main）；dev/AgentTeam 分支从未被 CI 跑过；上述数字在 Linux CI 上不可见。
