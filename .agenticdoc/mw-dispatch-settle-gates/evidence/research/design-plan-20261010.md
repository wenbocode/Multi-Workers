# design 阶段调研声明与设计问题清单 — `mw-dispatch-settle-gates`（2026-10-10）

本 note 是本 key design 阶段的调研声明（`evidence/research/design-*.md` 门禁）与设计问题清单。
spec 阶段已把**判据口径**钉死（`spec.md` 10 AC + §3.1/§3.2 + D1…D7），design 阶段只回答"落点、签名、边界与回归面"这四类问题。

## 1. 已定（design 不得推翻，只能细化）

| 项 | 决定 | 来源 |
|---|---|---|
| AC-002 锚与落点 | `_STAGE_TERMINAL_RANK`（`conductor.py:565`）+ 两级解析（`gate.stage` → `roadmap.stage_of_key`）+ 缺失 fail-open；落点 `pending_gate_reminders` 第 4 条件 | D-005 / `spec-stage-terminality-20261010.md` |
| AC-006 谓词 | 三级通道（`spec.md` §3.1）；语料回放 28 delivered / 2 正确 NC / 0 假阳性 | D-006 |
| AC-007 口径 | 有 `artifacts` ⇒ `## Deliverables`（排除 `output.md`/`progress.md`）；无 ⇒ 整段省略；`Exit Reason` 补 `toolCallCount` + `writes=` | D-006 |
| AC-010 | 读侧取末个非占位块（或按 run marker 分块）；settle 写侧幂等；**不废除 D-117 追加语义** | D-006 |
| 汇总：`halted` 口径 | 取 conductor 侧（不提醒），design 显式记 D | D-005 |

## 2. design 阶段要回答的问题（并发两个 RQ）

- **DRQ-1**（`mds-drq1-write-surface`）→ 收录 `evidence/research/design-write-surface-20261010.md`
  AC-005/AC-003：① 角色能力**单一声明源**在哪（TS `activeToolsForType` `worker-mode.ts:63-117` vs Python `dispatch.py` 的 REGISTRY），
  两侧现有 parity 测试是什么、能否扩展锁"无 write 工具的角色集合"；② 写意图模式的**假阳性面**（中文动词表、路径出现但为读目标、Markdown 引用块），
  并给可执行判定表；③ 拒绝的**落点**（`ui-bridge.ts` 哪个 handler、`dispatch_worker` 与 `/worker` 是否共用函数）与 `allowForeignWrite` 的审计落点；
  ④ 自动注入契约段的**注入点与幂等性**（同一 task.md 重派不得重复注入）。
- **DRQ-2**（`mds-drq2-settle-read`）→ 收录 `evidence/research/design-settle-read-20261010.md`
  AC-006/AC-010/AC-007：① `hasProductEvidence()` 收窄的**调用面**（唯一调用 `pm-orchestrator.ts:653` 语义是否兼容"未跑过"判定）；
  ② 结算写侧：`needs-clarification` + alarm 的**落点**（`worker-mode.ts::finishSuccess`？launcher `_exit_to_status`？两侧如何不重复判定），
  与 `run.json` 状态机（T-20 已在 `run-store.ts` 有终态集）如何对齐；③ 读侧 `readOutputSection`（`ui-bridge.ts:344`）的全部调用者
  （`readOutputSummary`、terminal-detail fallback chain、PM 回读、`/mw` 命令）与"末个非占位块"改法的兼容性；
  ④ 28 条回归面（D-008）逐条给出**改为新口径后的期望断言**。

## 3. 零调研声明

G-h（文档勘误）与 AC-001（doctor 面）/AC-004（`dispatch.py` 读 `run.json`）**不需要新调研**：
前者的坐标来自两份复审（已复现），后两者的落点已由 PM 在 spec 阶段定好（`mw_common.py:3064`+`:3086` 自读 gates 目录；
`dispatch.py:621-633` 仅写行）。design 阶段只为它们写"落点 + 反向用例"。
