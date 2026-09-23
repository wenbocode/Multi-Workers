# T-03: 回归、变更记录与验证（AC-008）

> Key: mw-task-scope-isolation · 阶段: EXECUTE · 2026-09-23 · 依赖: T-01, T-02

## 目标

补齐既有用例的行为变更适配、文档与验证证据。

## 改动点

1. 既有用例适配（行为变更是有意为之，非"修测试"）：
   - `VC-005: ack_worker_result tool acks and reports like /mw ack` → watch 用 `{ key: "key-a" }`（任务归属本来就是 `key-a`，`terminalRow` 硬编码）；
   - `VC-011: list_tasks badges acked rows` → 用 `{ scope: "all" }` 并适配 owner 前缀（行匹配从 `startsWith` 改为 `includes`）。
2. `packages/coding-agent/CHANGELOG.md` 的 `[Unreleased] / ### Changed` 追加三条：`list_tasks` 默认收窄 + owner 前缀 + `/mw ack`、`ack_worker_result` 的窗口级收窄（跨窗口 ack 改为拒绝 + 指引）。
3. 验证：
   - `test/extensions/agent-team-loop.test.ts` 目标用例 + 全文件回归；
   - `npm run check`（biome / pinned-deps / ts-imports / shrinkwrap / install-lock / tsgo）零 error/warning/info。
4. 记录：`pm-state.md` 证据账本 + `achieved.md` + quality-gate 报告。

## 完成判据

全文件用例绿、`npm run check` 0/0/0、AC-001..AC-008 逐条有证据引用；未重建 bundle（生效需 `mw build --install` + 新窗口，作为遗留登记）。
