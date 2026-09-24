# Design 阶段调研证据：升级判定的过滤语义与备选方案

- Key: mw-crosskey-risk-escalation / Phase: DESIGN
- 日期: 2026-09-23
- 调研问题（RQ）：放宽升级过滤有哪些可选实现？哪一处改动面最小且不破坏既有性质？测试面如何覆盖两种形态？

## RQ-1 过滤条件的两种等价改写

现状（F1）第二分句为 `ownerKeyOf(entry, agenticdocRoot) !== watch.key → continue`。

- 形态 1（本设计 D-101）：`ownerKey !== watch.key && !owned → continue`。
- 形态 2：把 `owned` 折进一个谓词函数 `escalatable(entry, watch, root)` 并单测该函数。
- 比较：形态 2 更"可单测"，但要新增导出（扩大扩展面）且既有测试均在 `agent-team-loop.test.ts` 里走轮询端到端（`startWorkerPollLoop` + fake timers），新增导出会多一套并行测试路径。形态 1 完全落在既有轮询用例体裁内，改动 2 行、无新导出。
- 结论 F1：取形态 1；`owned` 显式 `?? false` 布尔化，保证 `undefined` 与"显式空 Set"在断言里可区分构造（VC-002 的两种形态）。

## RQ-2 判定是否应依赖 `ownerKeyOf` 的返回值语义

- `ownerKeyOf(entry, agenticdocRoot)` 由 `taskPath` 反推 owner key（`<root>/<ownerKey>/workers/<task>/task.md`），`_scratch` 也是合法 owner。
- 若把 owner 过滤整段删掉（方案 B），则 `ownerKeyOf` 不再被调用，`_scratch` 与别窗口 key 的 worker 都会投递 → 既有用例 `diverging workers owned by other keys never wake this window` 会直接失败。
- 结论 F2：`ownerKeyOf` 必须保留为"或"的一支；`owned` 只用来**补**，不用来**替**。

## RQ-3 测试构造细节（fake timers 下的可重现性）

- `startWorkerPollLoop(..., 100)` + `vi.advanceTimersByTime(500)` 在既有用例里稳定产生 5 个 tick。
- 判定 `escalated` 后，第二 tick 不再投递 → 可在一个 `it()` 内断言"1 条 + 第二 tick 仍 1 条"（既有 AC-004 用例即此写法）。
- 跨 key 构造只需把 `queueRunning(root, "key-b", "t-cross")` 与 `watch = { key: "key-a", dispatchedTaskKeys: new Set(["t-cross"]) }` 组合；`mkdtemp()` 沙箱 + `fs.rmSync` 收尾。
- 结论 F3：无需新夹具 helper；三个新用例与既有 AC-004 用例同体裁（`fakePi` / `queueRunning` / `mkdtemp`）。

## RQ-4 文案附加是否会影响既有断言

- 既有断言均为包含式（`toContain`）：`发散风险`、`'t-diverge'`、`risk=high`、`reads=74 writes=0`、`trace.log`、`progress.md`。
- 若把 `（owner key=…）` 无条件附加，watched key 用例文本会变但断言仍通过；然而 alert 是给 PM 读的，watched key 场景加 owner 属噪音。
- 结论 F4：条件附加（仅 `ownerKey !== watch.key`），watched key 文本逐字不变 —— 既有断言与 PM 阅读体验双保。

## 汇总

| # | 结论 | 影响 |
|---|------|------|
| F1 | 取"或"关系形态，改 2 行、不新增导出 | D-101 |
| F2 | `ownerKeyOf` 必须保留；全局广播会破既有守卫用例 | D-101 / D-104 |
| F3 | 3 个新用例可复用既有夹具与 fake-timer 体裁 | VC-001~003 |
| F4 | owner key 仅在异地时附加，watched key 文本不变 | D-102 / VC-004 |
