# spec 阶段调研状态声明（bootstrap，PM 自撰）

- Key: `mw-autopilot-gate-alarm-liveness`｜日期: 2026-10-13｜阶段: SPEC
- 性质：**PM 手写的种子声明**，用于满足"每个 key 至少一条 `evidence/research/spec-*.md`"；正式调研由 T-01..T-04 四张 research 卡并行补齐（唯一证据文件见下）。

## 1. 已由 PM 亲自核实的事实（可复查的 `path:line`）

| 事实 | 落点 |
|---|---|
| 提醒发射被**全项目级**整体抑制（任一 worker 在飞 ⇒ 所有 gate 不提醒） | `packages/multi-workers/autopilot/conductor.py:2558` |
| cap 上限闭区间 `[1,2]`（Python 与 TS 双镜像） | `autopilot/config.py:57/:103/:134`、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:190-191` |
| 提醒只写台账 + timeline，无 stderr/面板/通知 | `conductor.py:2688-2735`（`_remind_pending_gates`） |
| stage 终止抑制 | `conductor.py:2562-2566` |
| 既有 fail-open 原则（缺记录不得静音） | `conductor.py:2535-2550`（`pending_gate_reminders` docstring） |
| `kind` 集合只有 `stalled`，无 `blocker_class`；`re-attest` 全仓零命中 | `autopilot/gates.py:44/:76` + grep |
| `stalled` 出口仅 approve（续跑）/ reject（→`closed-legacy`），`:3326` 注释暗示可能可逆 | `conductor.py:264-268`、`:3319-3345` |
| conductor 是 serve 第三子进程，`/mw restart` 才重拉；Python 侧无 commit 自证 | `mw.py:5/:49/:140-198/:372-374` |
| TS 侧已有 stale-serve 检测前例 | `shared/mw-runner.ts:195-330`、`autopilot/console.ts:611/:629` |
| 双通道 fail-loud 封装已存在（可直接复用） | `conductor.py:2594-2660`（`_ROADMAP_ALARM_SEEN`/`_emit_roadmap_failure`/`_emit_roadmap_warnings`） |
| 上游输入（对方给 mw 的 5 条请求） | `H:\git\E2Feature\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md` |

## 2. 本阶段并行调研任务（唯一证据文件）

- RQ-1 → `evidence/research/spec-rq1-reminder-chain-20261013.md`（链路 + 四条件历史证据 + 全部永久静默路径）
- RQ-2 → `evidence/research/spec-rq2-stalled-state-machine-20261013.md`（`stalled` 全部出口 + 回环语义 + re-attest 落点）
- RQ-3 → `evidence/research/spec-rq3-serve-metadata-drift-20261013.md`（`serve.meta` 现状 + commit 采集与比对最小改动面）
- RQ-4 → `evidence/research/spec-rq4-schema-and-view-surface-20261013.md`（存量 gate 字段统计 + `blocker_class` 兼容矩阵 + 面板常驻行插入点）

## 3. 未覆盖面声明

- 本声明不做任何**独立取证**（不代替 RQ）：它只是把 PM 已核实的落点固化，避免 RQ 重复劳动；RQ 必须自行复看并给出命令与原始输出。
- 尚未查证：`H:\git\E2Feature` 的 `gates/` 存量字段分布、`auto-decisions.jsonl` 中 `phase:"remind"` 的真实计数、`closed-legacy ⟷ stalled` 回环实例 —— 分别由 RQ-4、RQ-1、RQ-2 负责。
