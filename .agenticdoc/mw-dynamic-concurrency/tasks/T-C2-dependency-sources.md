# T-C2 — 依赖数据源（RQ-C2）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-dependency-sources-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**依赖图今天能从哪读出来？key 级与任务级各有什么机器可读载体，缺什么？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - roadmap schema 与 key 级 `depends_on`：`packages/multi-workers/autopilot/roadmap.py`（`Keys` 表 `| key | role | depends_on |`，`_DEPS`/验证逻辑在 `validate_roadmap`）。
  - 依赖满足判定：`conductor.py::_deps_satisfied`（`_DEP_SATISFIED` 集合）。
  - 任务级现状：`conductor.py::_plan_task_order`（plan.md 出现顺序，非依赖）；`_missing_plan_tasks`。
  - 任务卡 envelope：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`。
  - 关键锚点（可引用）：`packages/multi-workers/autopilot/conductor.py:744`（key 层闸）、`packages/multi-workers/autopilot/dispatch.py:964`（`dispatch()` 定义）、`packages/multi-workers/launcher.py:819`（唯一 spawn 点）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 dist、其它 key、`.agenticdoc/**/plan.md` 实例、`.mw/dispatch-table.md`）。

## 要求

1. **key 级依赖**：roadmap `depends_on` 的语法、解析函数 `file:line`、验证规则（同 stage / 更早 stage）、`_deps_satisfied` 的终态集合；给出 2 个真实 `_roadmap.md` 实例片段（其它 key 的，只读）。
2. **任务级依赖现状三态**：`plan.md`、`tasks/*.md`（任务卡）、task.md 头、wave/批次字段逐一 grep，回答"今天是否存在机器可读的任务级依赖"，否者给出证据（只有散文/顺序）。
3. **前沿计算所需数据缺口**：要算 key 层前沿只需什么、要算任务级前沿还缺什么；缺的每项给"最小新增载体"候选（字段名 + 落点 `file:line`）。
4. **环与悬空引用**：现有验证是否检测依赖环 / 悬空 key（给判定原文）；任务级若新增依赖需要哪些校验（给出反例）。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-dependency-sources-20261014.md`（结论先行 + 逐条判据 + 缺口表 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
