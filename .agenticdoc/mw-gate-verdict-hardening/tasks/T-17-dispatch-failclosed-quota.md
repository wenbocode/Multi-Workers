# T-17: G5-B 派发 fail-closed + 单轮配额

- 波次: **3** · 依赖: **T-09**（同文件 `pm-orchestrator.ts`，必串行）
- 写面（独占）: `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- 只读参考: `shared/worker-store.ts`（T-15 产物 `readQueue()`）、`shared/run-store.ts`（T-20 产物；**本卡先按"不存在 ⇒ 不约束"实现，T-20 落地后接入**）
- AC: **AC-020 / AC-021** · VC: **VC-027 / VC-028 / VC-029**
- 基线: `10446aefb`

## 问题（IN-3 放大器 F2/F4）

`dispatchNewTasks`（`:393-476`）的判据是"队列里**有没有**该 task_key 的行"：

- `:402` `const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey))`
- `:428` `if (dispatched.has(taskKey)) continue;`
- `:435` `isConductorTask` 跳过（所以事故里 0 个 `ap-*`）
- `:466` 派发时写 `status: "pending"`
- 触发点 `:737-744` `pi.on("agent_settled", …)`

⇒ 只要 `readAll()` 归零，**全部历史任务在同一轮被重新入列**（事故：252 行、单秒、峰值 66 并发）。判据里没有任何"终态"概念，也没有任何配额。

## 交付

1. 判据改序（严格顺序，任一前置不满足 ⇒ **本轮零派发**）：

```
1. q = readQueue();  q.unparsable.length > 0        -> abort(告警 queue-rows-unparsable)
2. cands = discoverTasks(scope)                      // scope 由 T-19 引入，本卡可先用现有全集
3. for c in cands: if terminalInRunState(c) || terminalInLedger(c): continue
4. if q.rows.length === 0 && !anyTerminalEvidence(cands): abort(告警 queue-unreadable)
5. if newRows >= cfg.dispatch_max_per_scan: abort(告警 dispatch-quota)
6. upsert(pending)（+ T-20 落地后 writeRunState(pending)）
```

2. `anyTerminalEvidence(cands)` = 候选集中**任一**存在：`run.json` 终态 ∨ 台账历史终态行 ∨ `<key>/evidence/` 下产物存在。
3. 告警载体：`auto-decisions.jsonl` 追加 `{ phase: "dispatch-alarm", kind: "queue-rows-unparsable" | "queue-unreadable" | "dispatch-quota", count, at }`（同族于 G2 的 `phase:"remind"`；8 个消费者按 `row.get("phase") == "decide"` 过滤 ⇒ 对它们不可见）。
4. 复用 G2（T-09）的 `deliverPmAlert` 通道把 `dispatch-quota` 推给 PM。

## 契约（冻结）

- **fail-closed 方向**：宁可少派一轮，不可在多派与少派之间选多派。
- 新告警 **禁止**使用新的 `phase` 之外的新机制（不新增 timeline 事件类型、不新增 sidecar 文件）。
- 判据里**不得**再出现"仅凭队列行存在与否"决定派发。
- 健康队列（无 unparsable、有终态信息、候选 ≤ 配额）上的派发结果必须与今日**逐行相同**。

## [VERIFY]

```
cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py -q
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts
```

## 非空洞对照

1. 第 1 步 `abort` 改 `continue` ⇒ `test_unparsable_suppresses_all_dispatch` 必红（派发数 > 0）。
2. 配额检查移到第 6 步之后 ⇒ `test_dispatch_quota` 必红（单轮派发 = 候选数）。
3. 去掉 `anyTerminalEvidence` 分支 ⇒ `test_empty_queue_new_project_dispatches` 必红（真·新项目被误阻）。

## 回执

写入 `workers/t-17-dispatch-failclosed/report.md`，写完立即复制到 `evidence/runs/`。
