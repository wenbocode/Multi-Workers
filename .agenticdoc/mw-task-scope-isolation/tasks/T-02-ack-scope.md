# T-02: ack 收窄（AC-005, AC-006, AC-007）

> Key: mw-task-scope-isolation · 阶段: EXECUTE · 2026-09-23 · 依赖: T-01（`ownedByThisWindow`）

## 目标

`ack_worker_result` 与 `/mw ack` 只作用于本窗口（design §4）。

## 改动点

1. `ackTasks` 增加第 4 个可选参数 `ownedBy?: (entry: WorkerEntry) => boolean`：
   - `"all"`：只取 `ownedBy?.(e) !== false && isTerminalStatus(e.status) && !alreadyAcked.has(e.taskKey)`；
   - 显式 key：在存在性/终态之后新增归属校验，不通过 → `rejected`，reason 含 owner key、本窗口 key 与 `/pm-key switch <owner>` 指引（现有 reason 文案不变，新增一条互不覆盖）；
   - 未传谓词 = 旧行为（保留给既有单测与未来非窗口调用方）。
2. 两个调用方注入同一个谓词：`ownedByThisWindow(e, watch, agenticdocRoot)`：
   - `ack_worker_result`（`ui-bridge.ts:1145`）；
   - `/mw ack`（`ui-bridge.ts:2051`）。
3. 拒绝路径不得调用 `ackStore.ack()`（AC-006 的"文件无新增行"）。

## 完成判据

AC-005/AC-006/AC-007 由新用例覆盖：跨 owner key 的显式 ack 被拒且 `_workers.acked` 不变；`all` 只 ack 本窗口；显式跨 key 派发的任务可被本窗口 ack。
