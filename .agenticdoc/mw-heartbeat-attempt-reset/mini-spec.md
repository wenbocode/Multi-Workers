# mini-spec: 多尝试 trace.log 的 [END]/[START] 配对（监控 up 恒 0s）

## 问题

worker 因模型错误重派 / fallback 时**复用同一个 trace.log**（追加写）。`shared/heartbeat.ts:readTaskProgress`
逐行扫描、`[START]` 只覆盖 `startTs`、`[END]` 只覆盖 `endTs/exitCode`，于是新尝试的 `[START]` 与
**上一次尝试遗留的 `[END]`** 被配对：

```
ELAPSED = max(0, END(prev) - START(current)) = max(0, -4.08s) = 0
```

实测（`workers/ds-qg-review/trace.log`，review worker 经 2 次 retry + 1 次 fallback）：

```
last lifecycle: END 09:23:12 exit=3  ->  START 09:23:16
parser: startTs=09:23:16  endTs=09:23:12  exitCode=3
elapsed = 0s          （真实已跑 12.4 min）
```

用户可见症状：watch widget 的 `up 0s` **永远不增长**（`pm/ui-bridge.ts:1132`）。
更严重的是 `exitCode=3` 残留：任何把 `exitCode !== undefined` 当终态判据的消费者会把**正在跑**的任务
读成"模型耗尽失败"。

## 修复（最小）

`readTaskProgress` 里：见到 `[START]` 时**重置上一尝试的终态字段**（`endTs=undefined`、`exitCode=undefined`、
`endPhases=undefined`）—— 一条 `[START]` 就是一次新尝试的开始，其之前的 `[END]` 不属于它。

不改 trace.log 格式、不改 launcher 追加行为、不改任何界面的渲染。

## 影响面

`shared/heartbeat.ts` 的 `readTaskProgress` 的所有消费者：watch widget（`pm/ui-bridge.ts:1127`）、
终态摘要、PM 分歧升级判定。

## 验收

1. 新增回归用例（`test/suite/worker-idle-heartbeat.test.ts`）：trace 含 `END(prev, exit=3)` 后接 `START(now)`，
   断言 `exitCode === undefined` 且 `elapsedMs > 0`（用 now-60s 的 START 时间戳）。
2. 同一文件既有用例全绿（单尝试 trace 行为不变）。
3. 用真实 `ds-qg-review` trace.log 手工复算：解析结果 `endTs=undefined`、`elapsedMs` ≈ 真实运行时长。

## 非目标

- 不修 launcher 复用 trace.log 的设计（append-only 对故障复盘有价值）。
- 不做"每次尝试独立 trace"的改造（改动面大，且会破坏 `[TOOL]` 全量历史）。
