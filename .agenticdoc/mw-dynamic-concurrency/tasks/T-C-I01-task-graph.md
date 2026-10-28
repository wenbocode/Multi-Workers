# T-C-I01 · 任务图模块 `task_graph.py`（B0，纯新增，不放开任何并发）

- type: coding
- key: mw-dynamic-concurrency

## 写入允许面

- `packages/multi-workers/autopilot/task_graph.py`（新建）
- `packages/multi-workers/test_task_graph.py`（新建）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/autopilot/conductor.py`、`autopilot/config.py`、`autopilot/dispatch.py`、`packages/coding-agent/**` 全部只读（它们分别属于 M-02/M-03/M-04 与前置 key `mw-write-face-guard`）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — PM 管多个 Worker 并行开发同一项目；本 key 的目的是把"每 key 一次只跑 1 个 worker"的硬编码串行改成**由依赖前沿决定、动态取最大**，而 key 层上界只作为上界。本卡交付其地基：**从任务卡头解析任务级依赖 + 校验 + 算前沿**。
- **本卡为什么可以现在就做（而 M-03 不能）**: 用户已接受的先决条件是"**写面判定必须先落地才放开并发**"。本卡只新增一个**纯函数模块**（不读队列、不改任何上界、不影响任何派发），不构成"放开"；改 `max_parallel_keys` 默认/下限的 M-03 才是"放开"本身，必须等前置 key `mw-write-face-guard` DONE。见 `.agenticdoc/mw-dynamic-concurrency/plan.md` §0。
- **已坐实的事实（直接引用，不要重做）**（证据：`.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md`）:
  - **今天任务级依赖没有机器可读载体**：`conductor.py:1717 _plan_task_order` 只按卡的出现顺序；`plan.md` 的 `depends_on` 命中 0。
  - **卡头解析不能复用现成件**：`packages/multi-workers/autopilot/card_audit.py:82` 的 `_HEADER_RE` 在 `:160-162` 遇正文即 `break`，对 5/5 真实卡返回空串 ⇒ 必须新写独立的 `parse_card_deps`（AC-008 明确要求）。
  - **真实卡面分布（必须复现的量级）**：434 张卡里 64 张 `- 依赖:`、47 张内嵌、12 张 `- deps: [001]`、6 张裸 `deps:` ⇒ 共 **117 张有行 / 317 张无行**；**0 张派发产物 task.md 带 `deps:`**。
  - **依赖 token 的 join 规则**：146 个真实依赖 token ⇒ 按文件 stem 精确匹配命中 **0**，按**数字核心**匹配唯一命中 **125**，同核歧义 **10**（如 `T-01-file-lock` vs `T-01-task-protocol`）。所以 join 只能用"数字核心"，且必须处理歧义，否则 `deps: T-1`（真实存在于 `mw-rag-window-parity`）会全部假红。
  - **卡头扫描窗口**：max 依赖行在 19 行 ⇒ `HEADER_SCAN_LINES=40` 实测够用。
- **前置决策（逐条实现）**: `.agenticdoc/mw-dynamic-concurrency/design.md` D-103（`parse_card_deps` 载体与算法）、D-104（V1–V7 校验；**任一 V 问题 ⇒ 整 key 串行回退 + timeline 事件**，本卡只负责"判定出问题"，写事件由 M-02 做）、D-110（**区间写法 `T-01…T-13` 判 Unsupported，不做展开**）。

## 要求

1. **`autopilot/task_graph.py`（新建）**，纯函数、无 I/O、无全局状态，导出：
   - `parse_card_deps(card_text: str) -> list[str]`：卡头区域规则 = H1 起、空行、`## 元信息` 小节、`- key: value` / `key: value` 行，**遇正文（首个非元信息小节标题或首个非 `- k: v` 的正文行）即止**；同时识别 `- deps:` / `- 依赖:` / `deps:` / `- 依赖：`（全角冒号）四种真实写法；行内取逗号分隔的 id；`-`/空 = 无依赖。
   - 校验 V1–V7（每个都返回结构化 problem，带 `kind` + 原文行号 + 原文片段）：
     V1 未知 id（不在本 key 卡集）/ V2 悬空（引用的 id 无对应卡）/ V3 环（含自引用）/ V4 跨 key 引用 / V5 重复声明 / V6 自引用 / V7 **Unsupported 语法（区间 `T-01…T-13`、`…`、`~`、`*` 通配）**。
   - `numeric_core(card_id_or_stem) -> str`（`T-01-x` → `01`，`T-1` → `1` ⇒ 归一后 `1 == 01`）+ `join_deps(deps, card_ids) -> dict`：数字核心唯一命中 = 绑定；同核多命中 = **歧义 problem**（不得任选一个）。
   - `frontier(deps_by_id, terminal_ids) -> list[str]`：未满足依赖为空（全部前置已终态/不存在）的卡，顺序 = 传入的卡序（保持 `_plan_task_order` 的稳定性）。
   - 只要出现任一 V-problem / 歧义，**对外必须给"整 key 串行回退"的信号**（例如 `plan_is_serializable=False`），不得部分生效、不得默认放大。
2. **真实卡面必须复现**：测试里对仓库真实卡抽样跑一遍，断言 §上下文里的分布量级（117/317 有行/无行；146 token ⇒ 唯一 125 + 歧义 10）。数量允许因新增卡而漂移，但**卡内必须写明你实测到的数字**，并在断言里用"实测值 ± 已知漂移"，不要硬编码我这里的数字。
3. **不得复用 `card_audit._header_value`**（实测不可用）；不得 import `conductor.py`（避免把 tick 依赖带进纯函数模块）。
4. **证据必须带**：V1–V7 的正反例各一条（含区间写法 `T-01…T-13` 判 Unsupported 的原文）；`deps: T-1` 与 `T-01-*` 的 join 结果；真实卡抽样的 `[VERIFY]` 数值；前沿计算的 3 组构造（链式 → 恒 1；扇出 → = 可并行数；混合）；残留与未覆盖面。

## 交付格式

- 代码：`packages/multi-workers/autopilot/task_graph.py`、`packages/multi-workers/test_task_graph.py`
- 唯一证据文件（本卡唯一允许写入的报告路径）: `.agenticdoc/mw-dynamic-concurrency/evidence/T-C-I01-task-graph.md`
  结构：`## TL;DR`／`## 交付物`／`## 验收输出`（pytest 原文）／`## 真实卡面实测`（逐条 `[VERIFY]`：case 原文 + 命令 + 实际数值）／`## V1–V7 与前沿构造`／`## 残留与未验证`／`## 上下文来源`／`## 改动历史`（`file:line` before→after）
- 本卡**不改**任何派发行为：`conductor.py` 的调用是 M-02 的事。

## 验收命令

```
cd packages/multi-workers; python -m pytest test_task_graph.py -q
```

（可选回归：`python -m pytest -q`。**不要**跑 `npm run check`——多 session 工作树里它会执行仓库级 `biome --write`。）

## 硬约束

- 只写"写入允许面"里的两个文件。
- 不写 timeline、不发事件、不读 `_workers.parallel`（本卡是纯函数；副作用在 M-02）。
- 不实现区间展开（D-110：判 Unsupported）。**可逆点**：把区间识别集中到一个 `_RANGE_RE` 常量，日后要展开只改这一处 + 语料。

## 改动历史

唯一证据文件里必须给出 `## 改动历史`：每个新增/修改文件的 `file:line` before→after；本卡两个文件均为**新建**（写"新建"）。
