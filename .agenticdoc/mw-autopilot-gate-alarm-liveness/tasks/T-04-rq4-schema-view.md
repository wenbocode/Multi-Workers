# T-04 — RQ-4｜gates schema 兼容面与 monitor 常驻行的插入点

type: research
phase: spec
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq4-schema-and-view-surface-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守 ⇒ 状态必须"看一眼就知道"，而不是等推送）。
- 已核实事实：
  - `packages/multi-workers/autopilot/gates.py:44`（gate 文件的 kind 集合）、`:76`（含 `stalled`）；全仓 `blocker_class` 零命中。
  - TS 镜像与视图：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:636+`（"gates (view-side enumeration, mirror of autopilot/gates.py)"）、`:14`（`gates/gate-{seq:04d}.md` 形态）、`:61-63`（`gates.lock`）、`:101-129`（`auto_gate_mode`/`gate_reminder_after_min`/`gate_reminder_max` 配置面）、`:190-191`（闭区间镜像）。
  - 既有测试：`packages/multi-workers/test_autopilot_gate_schema_v2.py`、`packages/coding-agent/test/suite/autopilot-config-parity.test.ts`、`autopilot-console.test.ts`、`packages/multi-workers/autopilot/contract_guard.py`（契约守卫）。
- 允许自行扩大取证（全仓只读 + `H:\git\E2Feature\.agenticdoc\_autopilot\gates\` 的**真实存量 gate 文件**）；给上下文来源清单。

## 要求

1. **清点存量 gate 的真实字段分布**（在 `H:\git\E2Feature` 与 `H:\git\Multi-Workers` 的 `gates/` 目录上统计：共几个、v1/v2 各几、每个字段出现率）⇒ 结论必须回答"新增 `blocker_class` 时旧文件缺字段的比例"。
2. 给出 **`blocker_class` 的兼容矩阵**：写入端（谁写 gate 文件、哪几个调用点）、解析端（Python 与 TS 双端）、缺省语义（缺字段 ⇒ `judgment`）、以及 `contract_guard.py`/schema 测试需要同步的位置，逐条 `path:line`。
3. 定位 **monitor 常驻 pending-gate 行的插入点与渲染链**：从 `status-model.ts` 的 gate 枚举 → 面板/console 的渲染函数 → 现有行格式与宽度约束（`monitor.ts` / `console.ts`）；回答"常驻行要不要新的状态源，还是复用现有枚举 + 已等时长计算（`gates.py` 的 `created_at` 解析）"。
4. 回答：**面板常驻行在"提醒被抑制"时如何表达原因**（复用 AC-002 的抑制原因枚举），有无现成字段可承载。
5. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

结论先行＋真实数据统计（表格 + 命令 + 计数）＋兼容矩阵（表）＋插入点定位（`path:line`）＋上下文来源清单＋未覆盖面声明。
