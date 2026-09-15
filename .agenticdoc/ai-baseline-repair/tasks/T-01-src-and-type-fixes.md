# T-01: src 与单点类型修复

> Key: ai-baseline-repair | 依赖: 无 | 模式: PM 直执 | AC refs: AC-001, AC-004 | VC refs: VC-001, VC-004

## 目标

D-001 + D-004 + D-005：cloudflare TS2353、timi TS1294、tool-choice TS2339 三处修复。

## 步骤

1. `packages/ai/src/providers/cloudflare-ai-gateway.ts`：镜像上游（758a0ee9b）——`type CloudflareAIGatewayApi` 别名 + `createProvider<CloudflareAIGatewayApi>` + 「catalog 增删 workers-ai 条目、api map 钉死三 API」注释
2. `packages/ai/test/timi-dispatch.test.ts:30`：`constructor(readonly captured: unknown)` → 显式 `readonly captured: unknown` 字段声明 + 构造器 `this.captured = captured` 赋值
3. `packages/ai/test/openai-completions-tool-choice.test.ts:1410`：`model.compat?.maxTokensField` 在 union 上窄化后访问（`"maxTokensField" in` 判别或 api 判别），断言语义不变

## 验收

- [x] tsgo：26 → 0（三错消除，无新错；VC-001）
- [x] cloudflare 三 API 注册仍在（D-001 显式泛型 + 注释；VC-004）
- [x] biome 零告警

## 验证状态

验收通过（2026-09-10）：tsgo exit 0（26→23→0）；evidence/runs/regression-2026-09-10.md §1
