# T-09: G2 PM 侧消费者（ledger → `deliverPmAlert`）+ G4 `session_shutdown` 停表

- 波次: **1** · 依赖: T-03
- 写面（独占）:
  - `.../agent-team-loop/pm/pm-orchestrator.ts`（`startWorkerPollLoop` `:519`）
  - `.../agent-team-loop/pm/ui-bridge.ts`（仅在需要幂等包装时）
- AC: AC-005, AC-018 · VC: VC-007, VC-023
- 基线: `10446aefb`

## 目标

让"无人提问也收到提醒"真正成立——conductor 侧**没有推送原语**（`sendMessage` 0 命中），唯一的 PM 唤醒通道是 `ui-bridge.ts:131 deliverPmAlert`（`:139 triggerTurn: true`）。本卡在 extension 侧新增该消费者，**不自己再判一次**（判定归 `T-07`）。

## 交付物

- `pm-orchestrator.ts` 的 poll 循环（`:519`，现只读 `workerStore.readAll()`）新增：定期读 `auto-decisions.jsonl` 的 `phase == "remind"` 新行 ⇒ 逐条 `deliverPmAlert`。
- **幂等**：`deliverPmAlert` 现有实现**无幂等**（DRQ-2 F1）⇒ 新增"会话水位 / 已推送 seq"去重，保证同一 ledger 行不重复推送（重启/多窗口都不得翻倍）。
- 多窗口：按 `gate.key` 作用域（stage 级门只推一次）。
- **G4 半边**：新增 `session_shutdown` 停表（先例：`pm-orchestrator.ts:726-732`、`index.ts:28-35`；`console.ts:690-693` 注释已留此扩展点）。

## 契约（不得重定义）

- 只**读** ledger，不写；不修改 conductor 的任何文件。
- 不得把判定逻辑复制到 TS（会造成两侧分叉；DRQ-2 明确取"Python 判定 / TS 送达"路径）。
- 不改 `deliverWorkerResult` 的既有行为（终态回读通道）。
- 停表必须走既有 `stopMonitor` 语义（不清空非活动状态）。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts`

## 非空洞对照（必须附在回执里）

- 同一 ledger 行喂两次 ⇒ `deliverPmAlert` 只被调用 **1** 次（幂等生效；摘掉水位断言必须转红）。
- 发一次 `session_shutdown` ⇒ 面板停表且**不**残留 timer（摘掉该 hook ⇒ 用例转红，对应 VC-023）。

## 风险与注意

- poll 循环是最热的既有代码：**只加一个读取分支**，不改既有 `workerStore` 路径与触发顺序。
- 与 `T-12` 的 `console.ts` 改动无文件重叠；与 `T-13` 的 `monitor.ts` 无重叠。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-09-pm-consumer/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
