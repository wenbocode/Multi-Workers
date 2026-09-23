# 证据：design 阶段（mw-task-scope-isolation）

> 日期: 2026-09-23 · 类型: 仓库内核查（为 D-2/D-3/D-4/D-5 取证）

## D-2/D-4 的调用面核查

| 核查 | 结论 | 位置 |
|---|---|---|
| `ackTasks` 的调用方数量 | 恰好 2 个：`ack_worker_result` 工具、`/mw ack` 命令；无第三方调用 | `pm/ui-bridge.ts:1145`、`2051` |
| `list_tasks` 的注册方 | 1 处（`registerWorkerTools`），worker 模式不注册（worker 工具白名单无此项） | `pm/ui-bridge.ts:1157` |
| Python 侧是否读 `_workers.acked` | 无任何引用（`grep _workers.acked packages/multi-workers/**/*.py` 为空）→ 收窄写入路径不影响 launcher/conductor | — |
| 既有测试对 `PmWatchState` 的构造 | 以字面量 `{ key: undefined }` / `{ key: "key-a" }` 构造（≥5 处）→ 新字段必须是**可选**的，否则改动面扩散到与本 key 无关的用例 | `test/extensions/agent-team-loop.test.ts:1626,1663,1694,2757,2792,2827+` |
| 既有 ack 测试的任务归属 | `terminalRow(root, taskKey, status)` 固定写入 `key-a/workers/<task>/`（owner key = `key-a`）→ 收窄后这些用例需要把 watch.key 设为 `key-a` | `test/extensions/agent-team-loop.test.ts:2671-2685` |
| `list_tasks` 既有断言的行匹配方式 | `text.split("\n").find(l => l.startsWith("t-old"))` → 行首加 owner 前缀会命中失败，必须同步更新（输出格式是有意变更） | `test/extensions/agent-team-loop.test.ts:2871-2876` |

## D-1 归属模型的再确认

- `ownerKeyOf` 只依赖 `entry.taskPath`（`ui-bridge.ts:258-261`），不改 `_workers.parallel`（`WORKER_COLS = 8`，`shared/worker-store.ts:19`）即可获得归属 → 满足 GC-2（Python 零改动）。
- 显式跨 key 派发确实存在且无警告：`resolveOwnerKeyWithSync` 首条分支 `if (explicitKey) return explicitKey;`（`ui-bridge.ts:55-57`）→ 证明 `watch.key` 单口径不足，需要进程内记账（D-1 的 F-11 结论成立）。

## D-5 的质量门禁落点

- `test/extensions/agent-team-loop.test.ts` 已有 170 个通过用例（含 watch widget / dispatch 路由 / ack 校验），是本 key 的回归基线。
- `npm run check` 覆盖 biome + tsgo（erasable syntax 检查在内），无需额外脚手架。
