# RQ-1：编排面勘察 —— 扇出/汇合今天能挂在哪（research）

- Key: claim-driven-review-orchestration
- type: research
- 唯一证据文件：`evidence/research/spec-rq1-orchestration-seams-20261022.md`（只写这一个文件）

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」）。
- 上游交付：`claim-driven-review` 已把「断言驱动审查」做成单单元能力（`shared/dispatch-card.ts:724` `parseClaimsBlock`、
  `:1042` `claimBudgetCaps`；`pm/ui-bridge.ts:2834` `readDispatchCard`；`worker/worker-mode.ts:1034` `claimSettlementGaps`），
  实跑 `exit=0`：5 条 claim / 13 次放行取数（`claim-driven-review/evidence/t07-e2e-results-20261022.md`）。
- 本 RQ 只回答「编排层要挂在哪」，不设计判据（那是 RQ-2），不碰度量（RQ-3）。

## 要求（逐个回答，每条给 `path:line`）

1. **派发入口全图**：`dispatch_worker` 工具（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`）与
   conductor（`packages/multi-workers/autopilot/dispatch.py` + `launcher.py` + `mw_common.py` 的 `_poll_once`/队列行）
   两条通道，各自消费什么、写什么文件、谁把行推进 `_workers.parallel`。给出两条通道的差异表（字段级）。
2. **一个 task 能否扇出 N 个兄弟 task**：队列行格式（`task_key | status | cli | provider | task.md | started | updated | ? | manual`）
   是否允许多行同属一个逻辑任务；有没有现成的「汇合/join」语义（`_workers.acked`、`_workers.stale.parallel` 的作用）。
3. **claim 数门禁的落点**：`claimsGaps`（`dispatch-card.ts:985`）现在只有 `budget-sum>40` 与 manual 溢出；
   加一条「`n > 5` 需要拆分」的判定，放这里会不会与既有 `CLAIM_BUDGET_SUM_MAX` 语义打架（算一下 6/10/20 条时的
   `Σ预算`、`fileCap`、每 claim 取数，指出 20 条卡今天的实际命运）。
4. **merge 单元的读面**：merge 只读 `workers/<task>-u*/report.md`，`read_scope` 能不能只放这些文件
   （`read-scope.ts:118` `isSameOrUnder` 的文件级条目语义）？`worker_file` 与 read 工具的白名单差异。
5. **可复用物与空白**：现有代码里能直接复用的（triage 分类器、`DispatchCardGate`、`writeDispatchTaskMd`、
   `_read_scope_caps`）与必须新写的（拆卡函数、merge 卡模板、子卡 id 重映射），逐项列 `path:line` 或明确写「空白」。
6. **风险点**：并行写同一 `_workers.parallel` 的锁、同 key 的 serial-only 守卫（实测会 hold）、
   子卡与母卡的 `card_sha256` 关系、worker 超时看门狗在 5 个小单元上的叠加效应。

## 交付格式

`evidence/research/spec-rq1-orchestration-seams-20261022.md`：先一张结论表（问题 → 结论 → 证据锚点），
再分节展开，末尾一节 `## 未覆盖面` 声明没读到的部分。全部结论必须带 `path:line`，不许写推测不标注。

## 写入允许面

- `.agenticdoc/claim-driven-review-orchestration/evidence/research/spec-rq1-orchestration-seams-20261022.md`

## 写入禁止面

- 任何 `packages/**` 源码、`.agenticdoc/claim-driven-review/**`、其他 key 的目录、`dist/**`

## 验收命令

无（research 只读）；产物必须非空且每个结论带锚点。
