# T-01: 归属模型 + list_tasks scope（AC-001..AC-004, AC-007 记账）

> Key: mw-task-scope-isolation · 阶段: EXECUTE · 2026-09-23 · 依赖: 无

## 目标

在 `pm/ui-bridge.ts` 落地归属模型与 `list_tasks` 的 scope 参数。

## 改动点

1. `PmWatchState` 增加**可选**字段 `dispatchedTaskKeys?: Set<string>`（可选是为了不改既有 `{ key: ... }` 字面量调用点，design D-2）。
2. 新增导出纯函数：

```ts
export function ownedByThisWindow(entry: WorkerEntry, watch: PmWatchState, agenticdocRoot: string): boolean
```

= `ownerKeyOf(entry, agenticdocRoot) === watch.key || watch.dispatchedTaskKeys?.has(entry.taskKey) === true`。

3. `dispatch_worker` 成功入库后记账：`(watch.dispatchedTaskKeys ??= new Set()).add(task_key)`（`ui-bridge.ts:1035` 附近的 owner 解析之后）。
4. `list_tasks`：
   - 参数 `scope?: "mine" | "key" | "all"`（默认 `"mine"`）、`key?: string`；
   - `mine` → `ownedByThisWindow`；`key` → `ownerKeyOf === key`（缺 `key` → 参数错误文本）；`all` → `readAll()`；未知 scope → 参数错误文本（fail-closed，不静默当 all）；
   - 行格式 `<owner> :: <taskKey> | <status> | <cli>[ | model: m][ | acked]`；
   - 空结果文案分支见 design §3（无 watch key 且无记账时给 `switch_key` / `scope:"all"` 指引）；
   - 更新工具 `description`（写明默认 scope 与 `scope:"all"` 逃逸口、owner 前缀）。

## 完成判据

AC-001..AC-004 与 AC-007 的记账部分由 `test/extensions/agent-team-loop.test.ts` 新用例覆盖并通过。
