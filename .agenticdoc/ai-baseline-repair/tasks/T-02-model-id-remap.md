# T-02: model ID 映射全量执行

> Key: ai-baseline-repair | 依赖: 无（与 T-01 可乱序） | 模式: PM 直执 | AC refs: AC-002 | VC refs: VC-005

## 目标

D-002：15 处 TS2345 按 design 映射表执行。

## 映射表（执行版）

| 模式 | 位置 | 旧 | 新 |
|---|---|---|---|
| M1 | abort:157 | `("anthropic","claude-opus-4-1-20250805")` | `claude-sonnet-4-6` |
| M1 | context-overflow:207 | `("google","gemini-2.0-flash")` | `gemini-2.5-flash` |
| M1 | tool-call-id-norm:48,118 | `("github-copilot","gpt-5.2-codex")` | `gpt-5.5` |
| M1 | total-tokens:228 | `("google","gemini-2.0-flash")` | `gemini-2.5-flash` |
| M2 | stream:707 | `("cloudflare-ai-gateway","claude-sonnet-4-5")` | `claude-sonnet-4.5` |
| M3 | empty:330 / empty-tools:167,204,237 / stream:647 / tokens:173 / tool-call-without-result:178 / total-tokens:341 / unicode:517 | `("cloudflare-ai-gateway","workers-ai/@cf/moonshotai/kimi-k2.6")` ×8 | `("cloudflare-workers-ai","@cf/moonshotai/kimi-k2.6")`，describe 标题 "Cloudflare AI Gateway → Workers AI …" → "Cloudflare Workers AI …" |

跳过：上游 qwen-token-plan-individual 新增块（×6，provider 不存在）——evidence 注记。

## 步骤

1. 逐处编辑（M3 含 describe 标题同步改）
2. `tmp/verify-ids.py`：全部新 ID 在 `packages/ai/src/providers/data/*.json` 断言存在（VC-005），跑完删
3. tsgo 复核：TS2345 清零（23 → 8）

## 验收

- [x] tsgo TS2345 = 0，无新错（26→0 含 T-01/T-03 合并验证）
- [x] VC-005 等价核对：全部新 ID 在目录中（gemini-2.5-flash/claude-sonnet-4-6/gpt-5.5/claude-sonnet-4.5 逐一验证存在）
- [x] biome 零告警

## 验证状态

验收通过（2026-09-10），但方案升级：初版「删块+fixture」在运行时暴露 compat 层目录门禁问题（evidence §2），根修为镜像上游 generator 镜像块（workers-ai 目录 → gateway），删块/fixture 全部回滚，仅保留 M1/M2 换 ID 5 处；运行时失败对齐处置见 evidence §3。tsgo exit 0 + ai 套件 838 passed + npm run check exit 0
