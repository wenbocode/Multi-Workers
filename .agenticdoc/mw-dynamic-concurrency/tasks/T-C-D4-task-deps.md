# T-C-D4 — 任务级依赖载体与前沿消费（RQ-D4）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 Worker 并行；文件驱动协调）。
- 总问题：**任务级依赖今天没有任何机器可读载体（plan.md 只有"出现顺序"），per-key 动态并发因此缺输入。要新增 `deps:` 卡头并把它接到前沿计算与 `execute_loop` 的派发闸上。**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 唯一被机器消费的排序信号是 plan 出现顺序：`packages/multi-workers/autopilot/conductor.py:1717`（`_plan_task_order`，orphan-last 在 `:1723-1727` 区段），调用点 `:1765`。
  - per-key 串行闸（第二重）：`packages/multi-workers/autopilot/conductor.py:1770-1771`（`if any(_is_in_flight(r) for r in fam): return False  # per-key serial`），派发后 `return result.ok` 在 `:1799` 区段。
  - 家族聚合与在飞态：`conductor.py:1698`（`_family_rows`）、`conductor.py:3539`（`_is_in_flight`）。
  - id ↔ stem 候选映射：`conductor.py:2832`（`_plan_task_file_stems`）。
  - 卡头解析家族（只消费两个 key，是本设计的落点）：`packages/multi-workers/autopilot/card_audit.py:129`（`_header_value`）、`:171`（`parse_card_path`）、`:181`（`parse_card_sha256`）；header 扫描窗 `:78`（`HEADER_SCAN_LINES = 40`）。
  - 派发头渲染闭集：`packages/multi-workers/autopilot/dispatch.py:826-866`（含 `:828 type:`…`:865-866 deny_globs:`），**无依赖字段**。
  - key 级依赖的既有范式（语法与校验照它建）：`packages/multi-workers/autopilot/roadmap.py:483`（`_parse_depends_on`）、`:528`（`validate_roadmap`）、`:557-575`（悬空/自依赖/前向判据）、`:596`（`_find_cycle`）。
  - 旧式 `- deps: [001]` 有 12 个文件（全在 `.agenticdoc/mw-dual-workspace/tasks/`），且**今天不被传播**（`dispatch.py:521-523` 的 fallback 从首个 H2 之后开始）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/`、其它 key、`.mw/`）。

## 要求

1. **载体语法定稿**：给出 `deps:` 的精确语法（`-`/空 = 无；`,` 分隔；大小写；是否容忍 `T-01`/`01`/`T-1` 三种写法；是否容忍解释性括号如 `T-07（台账）`），并给出**必须拒绝/必须容忍**的判定规则。必须与 `roadmap._parse_depends_on` 逐条对照指出相同与不同（roadmap 的是 key 名，这里是任务 id）。
2. **解析落点**：`card_audit.py` 的 `parse_card_deps` 具体形状（复用 `_header_value` 还是新正则）、扫描窗是否够（`HEADER_SCAN_LINES = 40`）、卡头在卡片的第几行、`- deps:` 与 `deps:` 两种写法是否都接受。
3. **派发头回显**：在 `dispatch.py:826-866` 加一行的位置与格式；不给依赖时不写行的判定；对 `card_sha256` 的影响（是否使既有 sha 失效——给出结论与理由）。
4. **校验 V1–V7 的实现位置**：逐条给出落在哪个文件/函数（新建 `task_graph.py` 还是复用 `conductor.py` 内的 helper），并给出每条的反例输入 + 期望判定（悬空、自依赖、环、plan-only id、`负责 Agent: PM` 的非 worker 任务、重试代数 `-aN` 归一、跨 key 引用）。
5. **前沿计算**：给出 `frontier_tasks` 的精确定义（输入：stem→deps、已完成 stem 集合、在飞卡身份集合、写面 A/B 判定），以及它与 `_plan_task_order`/`execute_loop` 的接线形状；说明 orphan（plan 未提）任务在依赖图里的默认依赖（建议：无依赖 = 立刻可派，还是保守串行？给理由）。
6. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md`（结论先行 + 语法定稿 + 落点表 + V1–V7 表 + 前沿定义 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印（例：现存 `- 依赖:`/`- deps:` 行的语法分布计数）。
