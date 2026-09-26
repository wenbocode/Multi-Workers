# T-14: 文档 + 产物重建 + 全量回归收口

- 波次: **4** · 依赖: T-01…T-13（全部）
- 写面（独占）: 
  - `packages/multi-workers/CHANGELOG.md`
  - `packages/coding-agent/CHANGELOG.md`
  - `packages/multi-workers/UPDATE.md`
  - `packages/*/dist/**`（仅在有用户指令时重建）
- AC: 全部 · VC: 全部
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

对外可见面收口：CHANGELOG、运维文档、产物一致性、全量回归与基线对照。

## 交付物

- 两份 CHANGELOG 的 `## [Unreleased]` 下按节追加（Added / Changed / Fixed），不重复既有小节标题。
- `UPDATE.md`：新键 `auto_gate_mode`、新事件、新字段、`pending-review`、doctor gate 段的运维说明。
- 产物重建（**仅在用户显式指令下**执行 `npm run build`）与 dist 一致性判据 `git -c core.fileMode=false diff --exit-code -- packages/*/dist`。
- 全量回归：`npm run check`（完整输出，不 tail）+ `./test.sh`；对照基线红集合（`2 failed, 1007 passed, 10 deselected` + 两条既有红）。

## 契约（不得重定义）

- 不修改已发布版本节；不在 CHANGELOG 里复读 AC/VC。
- 不提交 lockfile（无依赖变更）。

## [VERIFY]

- `npm run check`（repo 根，完整输出）
- `./test.sh`（repo 根，非 e2e 全量）
- `git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist`（若已重建）

## 非空洞对照（必须附在回执里）

- 回归红集合若比基线多 ⇒ 必须定位到具体卡并回退该卡改动，不得只更新基线。

## 风险与注意

- dist 重建是用户指令性动作（AGENTS.md：不得擅自 `npm run build`）；未获指令时本卡只做 CHANGELOG/UPDATE/回归。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-14-docs-dist-regression/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
