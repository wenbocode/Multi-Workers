# Design: mw-task-scope-isolation

> Key: mw-task-scope-isolation · 阶段: DESIGN · 2026-09-23
> 上游: spec.md（AC-001..AC-008）· 证据: evidence/research/spec-task-scope-isolation-2026-09-23.md

## 1. 归属模型（D-1）

**一个任务的归属 = 它的 owner key**（`ownerKeyOf(entry, agenticdocRoot)`，即 taskPath 相对 `.agenticdoc` 的首段；`_scratch` 是普通 owner key）。不用 "dispatcher" 概念——`WorkerEntry` 无此字段（F-5），补字段要动 `_workers.parallel` 列与 launcher/mw_common 解析 + 并发重写，收益不抵成本。

**"本窗口的" = watch.key 的 ∪ 本窗口本进程派发的**：

- `watch.key`：本窗口 claim/executes 的 key，也是底部 widget 的口径（F-3）。该 key 下的一切任务都是这个窗口的责任（别的窗口按 F-10 会降级 `_scratch` 或显式跨 key 派发）。
- 本进程派发记账：覆盖 F-11 的两种情况（显式跨 key 派发；watch 陈旧但拿 active）。记在 `PmWatchState`（F-6）里，**不落盘**——重启后退化为纯 `watch.key` 口径（正常情况下两者一致，因为默认派发落到 watch.key）。

被否决的替代方案：

| 方案 | 否决理由 |
|---|---|
| 只用 `watch.key` | F-11：显式跨 key 派发的任务看不见、ack 不了；与"自己派发的"字面语义不符 |
| 给 `_workers.parallel` 加 dispatcher 列 | Python 侧（launcher/mw_common）+ 并发重写协议同步改动，跨语言格式变更，收益不抵成本 |
| 每窗口一个 ack 文件（`_workers.acked.<pid>`） | 治的是展示端，且引入每窗口状态文件与残留清理；真实问题在写入端越界，收窄写入即可 |

## 2. `mine` 的判定函数（D-2）

```ts
/** 本窗口是否"拥有"这一行：watch.key 的，或本窗口本进程派发过的。 */
function ownedByThisWindow(entry: WorkerEntry, watch: PmWatchState, agenticdocRoot: string): boolean {
	return ownerKeyOf(entry, agenticdocRoot) === watch.key || watch.dispatchedTaskKeys.has(entry.taskKey);
}
```

- 纯函数、无 I/O、可单测；`watch.dispatchedTaskKeys: Set<string>`（新字段）。
- fail-closed：`watch.key === undefined` 且不在记账里 → 不是本窗口的。
- 记账写入点：`dispatch_worker` 成功创建 task.md 之后（`ui-bridge.ts:1035` 附近的 owner 解析之后）`watch.dispatchedTaskKeys.add(task_key)`；`_scratch` 同样记账。

## 3. `list_tasks`（D-3）

签名：`scope?: "mine" | "key" | "all"`（默认 `"mine"`）、`key?: string`。

| scope | 集合 | 空结果文案 |
|---|---|---|
| `mine`（默认） | `ownedByThisWindow` | 有 watch key 或无记账 → `No tasks found for this window (key: <k>). Use scope:"all" to list every key.`；两者都无 → 额外给 `switch_key` 指引 + 明确说明未列出其它窗口的任务 |
| `key` | `ownerKeyOf === key` | 缺 `key` → 参数错误文本（`scope:"key" requires key`），不抛异常 |
| `all` | `readAll()`（现状，含 acked 徽标） | `No tasks found.` |

行格式统一为 `<owner> :: <taskKey> | <status> | <cli>[ | model: <m>][ | acked]`（AC-001 要求可读归属）。`all` 的输出因此与改动前**语义**一致、但**多了 owner 前缀**——这是有意的可读性变更，记入 CHANGELOG。

未知 scope 值：按参数错误处理（fail-closed，不静默当 `all`）。

## 4. ack 收窄（D-4）

`ackTasks` 增加可选的归属谓词（保持它对路径/窗口状态零依赖，两个调用方（F-9）各自注入）：

```ts
export async function ackTasks(
	workerStore: WorkerStore,
	ackStore: AckStore,
	targets: string[] | "all",
	ownedBy?: (entry: WorkerEntry) => boolean,
): Promise<{ acked: string[]; rejected: Array<{ key: string; reason: string }> }>
```

- `"all"`：只收 `ownedBy?.(e) !== false` 的行（未传谓词 = 旧行为，供既有单测与未来非窗口调用方使用）。
- 显式 key：新增归属校验——`ownedBy(entry) === false` → rejected，reason = `owned by key '<owner>' — this window owns '<watchKey|none>'; run /pm-key switch <owner> to align, or ack it from that window`。
- 拒绝路径**不写盘**（AC-006）：沿用既有结构，只有 `acked` 数组进 `ackStore.ack()`。
- 判定顺序：存在性 → 终态 → 归属（保留既有 reason 文案，新增一条互不覆盖）。

两个调用方：

- `ack_worker_result`（`ui-bridge.ts:1145`）：传 `(e) => ownedByThisWindow(e, watch, agenticdocRoot)`。
- `/mw ack`（`ui-bridge.ts:2051`）：同一个谓词（命令与工具必须同语义，AC-007）。

## 5. 兼容与变更记录（D-5）

| 变更 | 类型 | 记录 |
|---|---|---|
| `list_tasks` 默认收窄为 `mine` | 行为变更（有 `scope:"all"` 逃逸口） | CHANGELOG Unreleased / Changed |
| `list_tasks` 行加 owner 前缀 | 输出格式变更 | 同上（指明工具描述同步更新） |
| `/mw ack` + `ack_worker_result` 只作用于本窗口 | 行为变更（跨窗口 ack 由拒绝 + 指引替代） | CHANGELOG Unreleased / Changed |

## 6. 测试策略

- 单元：`ownedByThisWindow`（watch.key 命中 / 记账命中 / 都不命中 / watch.key 为 undefined）。
- 工具面：`list_tasks` 三档 scope + 缺参 + 未知 scope + 空结果文案（含 `switch_key` 指引）。
- ack：本窗口 `all` 只 ack 自己的；跨 owner key 显式 ack → rejected + 文件无新增行；显式跨 key 派发后可见可 ack（AC-007）。
- 回归：既有 `test/extensions/agent-team-loop.test.ts` 全绿（widget / dispatch 路由 / 既有 ack 校验用例），`npm run check` 0/0/0。
- 落点：`test/extensions/agent-team-loop.test.ts`（该文件已含 `list_tasks`/`ackTasks`/`ack_worker_result` 共 20 处引用，沿用同一 harness 与 fake pi）。

## 7. 风险

| 风险 | 处置 |
|---|---|
| PM 依赖 `list_tasks` 做全局查重 | 工具描述写明 `scope:"all"`；默认文案在空结果时给出指引 |
| 本进程记账在窗口重启后丢失 | 已知且可接受：重启后 watch.key 口径仍覆盖默认派发路径；需要全局视野时 `scope:"all"`（记入 spec §1.4） |
| `/mw ack all` 语义变化影响既有用户习惯 | CHANGELOG 明确；拒绝路径文案给出替代动作（切 key 或到那个窗口 ack） |
