# Spec 阶段调研证据：跨 key 分化升级投递的既有实现与所有权语义

- Key: mw-crosskey-risk-escalation / Phase: SPEC
- 日期: 2026-09-23
- 调研问题（RQ）：monitor 的分化升级当前按什么口径过滤？同一 key 的派发面还有哪些"所有权"语义？放宽过滤的边界在哪里？

## RQ-1 升级循环的现状（file:line）

`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`：

- `startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui, pollIntervalMs)` — 单一 `setInterval`；闭包内两个进程内集合：`notified`（终态摘要，基线快照先入集合）与 `escalated`（升级去重，`AC-004` 注释：每 task 每窗口一次）。
- 升级循环（约 `:558-578`）：
  ```ts
  for (const entry of entries) {
    if (entry.status !== "running" || escalated.has(entry.taskKey)) continue;
    if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
    const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;
    if (!ck || ck.risk === "low") continue;
    escalated.add(entry.taskKey);
    deliverPmAlert(pi, `[mw] 发散风险：worker '${entry.taskKey}' 检查点 risk=${ck.risk}…`);
  }
  ```
- 结论 F1：过滤条件由**两个**与"归属"有关的分句组成——`!watch.key`（未 watch 任何 key 时完全不升级）与 `ownerKeyOf(...) !== watch.key`（只升级 watched key 的 worker）。本 key 只动第二句。

## RQ-2 "所有权"的第二套语义

`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 的 `PmWatchState`：

```ts
export interface PmWatchState {
  key: string | undefined;                    // 本窗口 watch 的 key
  dispatchedTaskKeys?: Set<string>;           // 本窗口在本进程内派发过的 task（mw-task-scope-isolation）
}
```

注释明确：owner key 不总是 watched key——显式 `key:` 派发被接受（`resolveOwnerKeyWithSync`），全局 active 兜底也会落到别处；`dispatchedTaskKeys` 就是"这些也是本窗口的活"的登记面，`list_tasks`（`scope:"mine"`）与 `ack_worker_result` 已按它扩面。它**进程内、不持久化、不跨窗口共享**。

- 结论 F2：项目里已有"本窗口派发 = 本窗口的活"这一所有权语义，但升级投递面没消费它——同一批队列行呈现"面板/工具可见、升级不可见"的错位（与 `mw-worker-visibility-gate` 修的面板不可见属同一类，只是方向相反）。

## RQ-3 现有测试对"边界"的约束

`packages/coding-agent/test/extensions/agent-team-loop.test.ts`：

- `AC-004: poll loop wakes the PM once on a mid/high checkpoint (triggerTurn) and leaves low-risk alone`（约 `:3911-3962`）：watched key 内 high 升级 1 条、low 不升级、第二 tick 不重复；断言 alert 文本含 `发散风险`、`'t-diverge'`、`risk=high`、`reads=74 writes=0`、`trace.log`、`progress.md`，且 `options[0]?.triggerTurn === true`。
- `AC-004: diverging workers owned by other keys never wake this window`（约 `:3964-4000`）：owner `key-b` 的 running + risk=high worker 在 watch `key-a` 时 → `messages` 长度 0。
- 夹具：`fakePi()`（`sendMessage` 文本/options 捕获）、`queueRunning(root, key, taskKey)`（写 task.md + `WorkerStore.upsert` running）、`vi.useFakeTimers()` + `advanceTimersByTime(500)`、`startWorkerPollLoop(..., 100)`。

- 结论 F3：第二个用例正是本 key 放宽容忍度的**反例守卫**。它的夹具里 `dispatchedTaskKeys` 未定义，因此"owner≠watched 且未派发 → 静默"的性质在该用例下必须继续成立——放宽必须写成"owner == watched **或** dispatched 含该 task"，而不能去掉 owner 过滤。

## RQ-4 投递口与判据读取

- `deliverPmAlert(pi, text)`：唯一投递口，内部 `pi.sendMessage({content}, {triggerTurn: true})`（既有用例断言 `triggerTurn`）。
- `readTaskProgress(path.dirname(entry.taskPath))?.checkpoint`：从 `trace.log` 解析 `[CHECKPOINT] … risk=<low|mid|high>`（`mw-worker-progress-persist` 后 `progress.md` 另有 `[machine]` 展示行，但 risk 判据仍在 trace.log）。
- `ownerKeyOf(entry, agenticdocRoot)`：由 `entry.taskPath` 反推 `<root>/<ownerKey>/workers/<task>/task.md` 的 owner key（`_scratch` 亦然）。

- 结论 F4：放宽不需要碰投递口与判据读取；alert 文本需要新增"owner key"信息才能让 PM 判断上下文（watched key 自身的用例断言文本是"包含式"断言，新增尾部信息不会破坏它们——但为稳妥，本 key 只在 owner≠watched 时附加）。

## 汇总

| # | 结论 | 出处 |
|---|------|------|
| F1 | 升级过滤有两个归属分句，本 key 只动第二句 | `pm-orchestrator.ts:564-578` |
| F2 | 已有 `dispatchedTaskKeys` 所有权语义，升级面未消费 | `ui-bridge.ts` `PmWatchState` 注释 |
| F3 | 既有"别键静默"用例是放宽的硬反例守卫 | `agent-team-loop.test.ts:3964-4000` |
| F4 | 放宽只需改过滤 + 条件性附加 owner key 文案 | `deliverPmAlert` / `readTaskProgress` / `ownerKeyOf` |
