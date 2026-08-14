# Plan: Timi GPT Pi Routing

## 概览
- Key: timi-gpt-pi-routing
- Spec: .agenticdoc/timi-gpt-pi-routing/spec.md
- 预计阶段数: 3
- 创建时间: 2026-08-14

## 已完成（无需重做）

以下源文件已在上轮完成，测试覆盖 VC-001/VC-007：
- `packages/ai/src/providers/timi.ts` — 混合 API provider ✓
- `packages/ai/src/providers/data/timi.json` (source) — 协议分类正确 ✓
- `packages/ai/test/timi-models.test.ts` — VC-001/VC-007 测试 ✓

## 阶段列表

### Stage 1: TypeScript provider fixes + tests
**目标**: 修复 TS 层的跨协议历史、重试边界、默认模型、dispatcher routing；写完所有 TS L1 测试
**依赖**: 无
**产出**:
- `packages/ai/src/utils/retry.ts` — 新增 PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC 常量 + isRetryableAssistantError 判断
- `packages/ai/src/api/timi-responses.ts` — 新增流事件包装（追踪 start，为 pre-start error 追加诊断）
- `packages/ai/src/api/openai-responses-shared.ts` — thinking 签名回放加 API 匹配守卫
- `packages/ai/src/api/anthropic-messages.ts` — thinking block 回放加 API 匹配守卫
- `packages/coding-agent/src/core/model-resolver.ts` — timi 默认模型改为 gpt-5.6-sol
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` — Pi 任务设置 provider: "timi"
- `packages/ai/test/cross-api-thinking-history.test.ts` — VC-006
- `packages/ai/test/timi-responses.test.ts` — VC-004/VC-005
- `packages/coding-agent/test/model-resolver.test.ts` — 追加 VC-003
- `packages/ai/test/providers.test.ts` 或新文件 — VC-002

**Tasks**: 见 tasks/001-ts-cross-protocol-history.md, tasks/002-ts-retry-boundary.md, tasks/003-ts-model-resolver-dispatch.md

### Stage 2: Python fixes + tests
**目标**: Launcher 路由改造（Pi/timi + Codex native）；完全移除 port-7002 codex；mw serve fail-closed 监控
**依赖**: Stage 1 完成
**产出**:
- `packages/multi-workers/launcher.py` — Pi/timi 路由 + Codex native 路由 + 移除 --codex-port
- `packages/multi-workers/providers.json` — 删除 codex 条目
- `packages/multi-workers/proxy_multi.py` — 移除 codex proxy + --codex-port
- `packages/multi-workers/mw.py` — 移除 --codex-port + fail-closed 子进程监控 + stop-request 文件 + 跨平台存活检查
- `packages/multi-workers/smoke_test.sh` — 移除 17002/codex-port
- `packages/multi-workers/dispatch-table.md` — 更新 Codex 行 + 新增 Pi/Timi 行
- `packages/multi-workers/test_launcher.py` — VC-008/VC-009/VC-010
- `packages/multi-workers/test_proxy_service.py` — VC-011/VC-012

**Tasks**: 见 tasks/004-py-launcher-routing.md, tasks/005-py-remove-codex-7002.md, tasks/006-py-mw-supervision.md

### Stage 3: Build & verify
**目标**: npm run check 通过 → npm run build 通过 → dist 验证 + 凭证扫描
**依赖**: Stage 1 + Stage 2 完成
**产出**:
- `npm run check` 零错误 ✓
- `npm run build` 零错误 ✓
- `packages/ai/dist/providers/data/timi.json` — 协议分类匹配 AC-001 ✓
- `packages/ai/dist/providers/timi.js` — 含双 API 实现 ✓
- 凭证泄漏扫描 PASS

**Tasks**: 见 tasks/007-build-verify.md

## 状态总览

| Task | Stage | 状态 | 负责 Agent |
|------|-------|------|-----------|
| 001-ts-cross-protocol-history | 1 | ⬜ pending | - |
| 002-ts-retry-boundary | 1 | ⬜ pending | - |
| 003-ts-model-resolver-dispatch | 1 | ⬜ pending | - |
| 004-py-launcher-routing | 2 | ⬜ pending | - |
| 005-py-remove-codex-7002 | 2 | ⬜ pending | - |
| 006-py-mw-supervision | 2 | ⬜ pending | - |
| 007-build-verify | 3 | ⬜ pending | - |
