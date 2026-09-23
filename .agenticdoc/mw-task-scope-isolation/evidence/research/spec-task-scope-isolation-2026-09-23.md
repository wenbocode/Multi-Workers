# 证据：spec 阶段（mw-task-scope-isolation）

> 日期: 2026-09-23 · 类型: 零外部调研声明（仓库内代码事实核对）

## 声明

本 key 无外部依赖需要调研（不引入库、不改协议、不涉第三方面）。所需事实全部来自本仓代码，逐条核对如下（行号为 2026-09-23 工作树状态）。

## 事实清单

| # | 事实 | 位置 |
|---|------|------|
| F-1 | `list_tasks` 注册时 `parameters: Type.Object({})`——零参数，无法收窄 | `pm/ui-bridge.ts:1157-1160` |
| F-2 | 其实现为 `workerStore.readAll()`（`.agenticdoc/**/workers/*/task.md` 全部行）→ 跨所有 key + `_scratch`；行格式 `taskKey \| status \| cli[ \| model][ \| acked]`，**不含 owner** | `pm/ui-bridge.ts:1165-1173` |
| F-3 | watch widget **已经按窗口收窄**：`owned = readAll().filter(e => ownerKeyOf(e, agenticdocRoot) === key)`，`key = watch.key`（本窗口 claim 的 key） | `pm/ui-bridge.ts:458`、`734`（`renderWatchLines(..., key)`） |
| F-4 | 归属判定现成：`ownerKeyOf(entry, agenticdocRoot)` = taskPath 相对 `.agenticdoc` 的首段 = owner key（遗留根级行解析为自身 taskKey，天然不匹配任何 watched key） | `pm/ui-bridge.ts:258-261` |
| F-5 | `WorkerEntry` 无 dispatcher 字段：`taskKey \| status \| cli \| provider \| taskPath \| dispatchedAt \| updatedAt \| model`（`WORKER_COLS = 8`，兼容 7 列旧行） | `shared/worker-store.ts:7-19` |
| F-6 | `PmWatchState` 仅 `{ key: string \| undefined }`——每窗口状态对象，可自由扩展、测试可注入 | `pm/ui-bridge.ts:143-146` |
| F-7 | 共享 ack 路径 `ackTasks(workerStore, ackStore, targets)`：`"all"` = 全部终态未 ack 行；显式 key 只校验存在性与终态，**不校验归属** | `pm/ui-bridge.ts:402-436` |
| F-8 | ack 存储是项目级共享文件 `.agenticdoc/_workers.acked`（`taskKey \| ackedAt`，写时持 `.mw/workers.lock`） | `shared/ack-store.ts:9-20,38-42` |
| F-9 | `ackTasks` 的两个调用方：`ack_worker_result` 工具、`/mw ack` 命令（后者亦支持 `all`） | `pm/ui-bridge.ts:1145`、`2051` |
| F-10 | 派发归属由 `resolveOwnerKeyWithSync` 决定：显式 `key` 优先（无警告）→ 本窗口 claim 的 watch.key → 全局 active（被他窗口 live 持有时降级 `_scratch`）→ `_index.md active` → `_scratch`；**不修改 `watch.key`**，仅在不一致时警告 `/pm-key switch` | `pm/ui-bridge.ts:51-76`、`81-95`、`1035` |
| F-11 | 因此"本窗口派发的" ≠ "watch.key 的"：显式跨 key 派发（F-10 首条）与"watch 陈旧但拿到 active"两种情况都会落到别的 owner key 上 | 由 F-7/F-10 推出 |

## 结论（对 spec 的直接支撑）

- 越界面是**真实存在**的：`list_tasks`（F-1/F-2）与 ack（F-7/F-9）都不按窗口收窄，而 ack 的存储是项目共享（F-8）→ A 窗口 `all` 会静默清空 B 窗口的待处理清单。
- 归属判定**不需要新数据**：`ownerKeyOf` 已有（F-4），且与 widget 同口径（F-3），可以做到"工具看到的就是面板看到的"。
- 单靠 watch.key 不足以覆盖"自己派发的"（F-11）→ 需要一份**进程内派发记账**；`PmWatchState`（F-6）是天然落点，且不落盘、不动 `_workers.parallel`（F-5）与 Python 侧。
