# T-01 — RQ-1｜gate reminder 的判据与调用链全景

type: research
phase: spec
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq1-reminder-chain-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守并行开发 ⇒ 编排链路不得静默失效）。
- 已核实事实（可直接引用，但必须自己复看确认）：
  - `packages/multi-workers/autopilot/conductor.py:2558` —— `if any(_is_in_flight(row) for row in rows): return []`（全项目级整体抑制）。
  - 同文件 `:2559-2561` cap 判断、`:2562-2566` stage 终止抑制、`:2688-2735` `_remind_pending_gates` 只写台账 + timeline（无 stderr）。
  - `:2511-2524` `_reminder_count`（`phase:"remind"` 计数）；`:2500-2508` 声明与 `D-006` 的时间窗理由。
  - 配置：`packages/multi-workers/autopilot/config.py:57/:103/:134`（`gate_reminder_max` 默认 2、闭区间 `[1,2]`）与 TS 镜像 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:190-191`。
  - 消费端：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1283/:1472/:1502`。
- 允许并鼓励自行扩大取证范围（全仓只读，含其他 key 的目录、`H:\git\E2Feature`）；在证据文件里给出**上下文来源清单**。

## 要求

1. 画出 gate reminder 的完整链路：**生产者（谁创建 gate）→ 判据（四条件）→ 写入面 → 消费面 → 人对它的可见面**，逐节点给 `path:line`。
2. 对四种抑制条件逐一给出**历史证据**：在 `H:\git\E2Feature`（与必要时 `H:\git\Multi-Workers`）的 `.mw/conductor.log`、`.agenticdoc/_autopilot/gates/`、`auto-decisions.jsonl` 中，实际发生过多少次 `phase:"remind"` 提醒、哪些 gate 曾长时间 `pending`、最长静默多久（给命令 + 原始输出片段 + 计数）。
3. 穷举所有会让提醒**永久静默**的路径（含 tick 停摆、conductor 进程死亡、cap 用尽、整体抑制、timeline 200 条尾窗、serve 未重启导致旧代码继续跑）。
4. 只读：不得修改任何文件；唯一允许写的文件是本卡声明的证据文件。

## 交付格式

证据文件按统一规范：**结论先行**（3-6 条判定）＋逐条判据（命令 + 原始输出片段 + 计数）＋**上下文来源清单**（读过哪些文件的哪些行）＋未覆盖面声明（哪些没查、为什么）。结论必须可与"我核对了哪些行"一一对应。
