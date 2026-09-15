# Mini-Spec: mw-owner-key-per-window

- Date: 2026-09-14
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

多窗口并行开发时，`dispatch_worker` / `/worker` 不带显式 `key` 的派发落到"其它 key"——即全局 `_index.parallel` 最新 active 行。每个窗口 claim 自己的 key 都会把其他 active 行降级（单 active 纪律），全局 active 永远指向最后 claim 的窗口，于是先 claim 的窗口派 worker 全部落进后 claim 窗口的 key。

## Root Cause

`resolveOwnerKeyWithSync`（`pm/ui-bridge.ts`）的默认 owner 解析顺序是 全局 activeKey() > _index.md 指针 > _scratch，本窗口 watch 只用来发 mismatch 警告（"dispatch follows the active key, never a stale watch"）。该语义早于 claim 体系（host:pid 存活检查）：监控 widget、结果回传都已按本窗口 watch 过滤（pm-orchestrator "every window decides its own key"），唯独派发路径还跟全局 active 集。

## Change

Owner 解析改为本窗口优先：

1. 显式 `key` 参数（不变）。
2. 本窗口 watch 的 key 且持有该行 claim（`claimId === windowClaimId()`）→ 派到该 key；`_scratch` watch 短路返回 `_scratch`。重启后 `restoreWatch` 静默重绑 claim，判定跨重启成立。
3. watch 过期/无 watch：回退全局 active 行，但仅当该行未被其他**活**窗口持有（`claimState !== "held-live"`）；否则不注入他人 key，落 `_scratch` 并每 key 警告一次。
4. `_index.md` 指针（仅当无 active 行）、`_scratch`（不变）。

配套：`IndexStore.activeEntry()` 暴露完整行（含 claimId），`activeKey()` 委托之；`dispatch_worker` 的 `key` 参数描述同步更新；新增 `warnForeignActiveOnce`。

## Files

- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（MW-001 / MW-002；`spawnLivePid` 提升到模块级；VC-003 原语义保留为"watch 无 claim"场景）
- `packages/coding-agent/CHANGELOG.md`（[Unreleased] Fixed）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 窗口持有 claim 的 watch key 优先于全局最新 active 行 | MW-001 |
| AC-002 | 活窗口持有的 active 行不再被注入，降级 `_scratch` 并警告一次 | MW-002 |
| AC-003 | watch 无 claim 时维持原行为（跟随 active key + mismatch 警告） | VC-003 |
| AC-004 | 显式 `key` 仍最高优先 | 既有行为，代码路径未动 |

## Result

- 测试：`agent-team-loop.test.ts` 118/118 passed（含新增 MW-001/MW-002）。
- `npm run check`：biome / pinned-deps / ts-imports / shrinkwrap / install-lock / tsgo --noEmit / browser-smoke 全部通过，无告警。
- 状态：完成（本 key 直接执行，无 worker 派发）。
