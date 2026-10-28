# Design: mw-dynamic-concurrency

> Key: mw-dynamic-concurrency
> Phase: DESIGN
> 上游: `spec.md`（AC 已锁 13 条）、`evidence/research/spec-{dispatch-chain,dependency-sources,config-mirror}-20261014.md`
> 前置 key: `mw-write-face-guard`（`deps`；写面声明与派发层重叠拒绝 B 层）
> 状态: draft（D-101..D-109 由 PM 起草，待 design 调研回读后复核）

## §0 Goal Alignment

- 来源 `.agenticdoc/goal.md`：让一个 PM Agent 管理多个 Worker Agent **并行**开发；文件驱动去中心化协调。
- 判定面：**实起并发 = min(配置上界, 依赖前沿)**，且并发提高后同文件多写者对 = 0（依赖前置 key 的 AC-005）。
- 基线（实证）：E2Feature 42 key、前沿 3，今日实起 min(2,3)=2；conductor 通道 per-key 恒 1（四重结构性判定，17 判定点）。
- 不做（spec §1.4）：写面机制本身、跨 key 任务级依赖、worker 看门狗语义、中心化调度器。

## §1 架构

并发度由"配置常量"改为"依赖前沿"，配置退化为**上界**。两层各自独立：

```
key 层（conductor.orchestrate）
  frontier_keys = {k | _deps_satisfied(deps_of[k], status_of)
                      and status_of[k] not in _DISPATCH_SKIP_STATUSES
                      and claim free}
  start_keys    = frontier_keys 前 min(cfg.max_parallel_keys, |frontier_keys|) 个
                  （在飞 key 已占用名额，按计数而非布尔）

per-key 层（conductor.execute_loop）
  frontier_tasks = {t | deps_of_task[t] ⊆ done_tasks  and  write_face(t) 与在飞不交}
  start_tasks    = 前 min(cfg.max_workers_per_key, |frontier_tasks|) 个
```

数据源：key 前沿今天已可算（`conductor.py:740`）；任务级依赖**需新增载体**（D-103）。

## §2 决策表

| # | 决策 | 取值 | 依据 |
|---|------|------|------|
| D-101 | `max_parallel_keys` 语义 | 从"硬上限"改为**上界**：实起 = `min(cap, |key frontier|)`；默认 **2 → 8**，floor **2 → 1**（1 = kill switch，AC-006 今天不可达） | spec 风险 4/9、AC-004/006；C3 实测改默认对既有 2 实例空操作 |
| D-102 | 新增 per-key 上界键 | 名 `max_workers_per_key`，默认 **4**，floor **1**，无上限；仅项目层可配（不进 `EFFECTIVE_KEYS`） | AC-004；C3 §1.5 机器层纪律 |
| D-103 | 任务级依赖载体 | 任务卡头一行 `deps: T-01, T-02`（`-`/空 = **无依赖 = 立刻可派**），语法与 `roadmap._parse_depends_on` 同构；解析 = **新增独立 `parse_card_deps`**（**不能复用 `card_audit._header_value`**：卡首行 H1 在 `card_audit.py:160-162` 直接 break，5/5 真实卡实测返回空串）+ 卡头区域规则；派发 `task.md` 头回显（插点 `dispatch.py:837` 之后、`phase:` 之前，不动两侧冻结行索引断言） | AC-008；C2 §3.3 G1/G3；RQ-D4 §2/§4 |
| D-104 | 任务图校验 | 悬空/自依赖/环/跨 key（V1–V7）；环检测泛化 `roadmap._find_cycle`（输入换成 `dict[str, set[str]]`）；id→stem join 用**数字核心**规则 + 同核心歧义判据（实测 stem 精确命中 0/146，数字核心唯一命中 125，歧义 10）；**任一 V 问题 ⇒ 整 key 串行回退 + timeline**；落新模块 `autopilot/task_graph.py`（`card_audit` 是叶子模块，不得反向 import conductor） | AC-003/AC-009；RQ-D4 §3/§5 |
| D-105 | 在飞判定进锁 | 临界区 = `dispatch()` **已持的那一次** `acquire_lock`（`dispatch.py:1156`），锁内做"读队列 → 判同 `task_key` 非终态 → 建 task.md → upsert"；**调用方不得再持锁**（嵌套 `O_CREAT|O_EXCL` 会退避至 `RuntimeError`，实测累计 14.6h）；两条通道**已共用** `.mw/workers.lock`，**不引入 per-key 锁**；PM 侧新增锁内判定 + 锁内 `produce()` 入队（调用点 3 处）；锁内判据必须是 **identity 级**（否则与 per-key 并发放开冲突） | AC-011/AC-014；RQ-D3 §2/§3/§5 |
| D-106 | 在飞口径单源 | 导出一个谓词（Python）+ 一个镜像（TS，经 parity）；`pending` **算**在飞（保持今天语义）；`manual` 行**不占** conductor 槽位（保持 D-019/T-12）；`slotsUsed` 改为与 conductor 同口径（实测今天 `slotsUsed=1` vs conductor 含 pending `=2`）；三处只读消费者（`_stage_closure`/`pending_gate_reminders`/`_defer_declined_gate`）**保持快照**（不创建行、失败方向有界、进锁会引入锁序与 30s stale-steal 风险） | AC-012；C1 §C6/§D9；RQ-D3 §6 |
| D-107 | `advance.advance()` 阻塞 | 先量化：复用 `beat.data`（`EVENT_TYPES` 取值）打点，算 `window_share=Σadvance_ms/Σtick_ms`；实测 1 周后再决定是否上独立执行器。**边界事实**：每 tick 同步 advance 次数上界 = `|前沿|` ≤ cap（`_advance_key` 返回 False 不占名额） | AC-013；RQ-D5 §5 |
| D-108 | roadmap 语义校验进 tick | conductor 每 tick 调用 `validate_roadmap`，问题去重后写 timeline 事件（同一 problem 每 stage 只写一次，避免 4s 抖动）；不改 fail-closed 不派发行为 | AC-010；C2 §4.2/§4.3 |
| D-109 | 呈现 | 面板同时显示"配置上界 / 本 tick effective 并发 / 前沿大小"三个量，且口径与 conductor 同一快照可复算 | AC-005/AC-012；C1 §D9、C3 §4.2 T9 |
| D-110 | 卡头依赖的区间写法 | **拒绝** `deps: T-01…T-13` 这类区间/省略写法（实测 3 张卡在用）：一律按 V-problem 处理 ⇒ **整 key 串行回退 + timeline 事件**，不引入"区间展开"解析规则。理由：解析规则每多一条就多一个 fail-open 面，而 V1–V7 已定义任何 V 问题都回退串行（安全侧）；区间写法 434 张卡里仅 3 张，收益低于风险。**可逆点**：`task_graph.py` 保留显式 `Unsupported → V-range` 分支，日后要展开时在此处加规则 + 冻结语料 | AC-004/AC-006；RQ-D4 §2/§5 |

## §3 接口与改动面

### 3.1 配置（两侧同波，P-021）

| 键 | Python | TS |
|---|---|---|
| `max_parallel_keys` | `config.py:87` 默认 8；`:122` `(1, None)`；docstring `:16` | `status-model.ts:136` 默认 8；`:196` `[1, null]` |
| `max_workers_per_key`（新） | `config.py` **紧接 `max_parallel_keys` 之后插入**（`DEFAULT_CONFIG` 与 `_INT_RANGES` 均在 index 4 位），值 `(1, None)` | `status-model.ts` 同位置（`DEFAULT_CONFIG` 与 `INT_RANGES`），并进 `intOf`/merged read/saveConfig/StatusConfigView/`--json`/文本摘要 |

> **插位纠正（RQ-D5 实测）**：不能追加到表尾 —— `test_autopilot_config.py:119-127` 与 `autopilot-console.test.ts:912-919` 锁了键序，表尾追加会翻 9 条断言。

连带锁（研究已穷举）：parity 语料补 `partial-key-max_workers_per_key` + 重算 sha256/count；Python 计数锁 6 张、TS 3 张 `20 → 21`；`range-max-parallel-low` 期望 reject → accept；README/`conductor.py:139` 的"13 键"文案。

### 3.2 任务级依赖

- 卡头（作者面）：`- deps: T-01, T-02`（新增独立 `parse_card_deps`，卡头区域规则 H1/空行/`## 元信息`/`- k: v`，遇正文即止；`HEADER_SCAN_LINES=40` 实测够用：max 依赖行 19）。
- 派发产物（`dispatch.py:826-866` header 闭集）：在 `:837 card_sha256:` 之后、`phase:` 之前新增一行 `deps: <逗号列表>`（无依赖不写）；不移动既有行索引（TS 侧已冻结断言 `agent-team-loop.test.ts:5735`、`vision-autoroute.test.ts:465`）；TS `mergeCardHeader`（`ui-bridge.ts:2030`）须同波改（P-021）。
- 摘要纪律：`card_sha256` 哈希**卡文件**（`dispatch.py:577`）⇒ 派发头回显中性，但给卡补 `deps:` 会让该卡既有派发行变 `tampered_cards`（本仓 3 例先例）⇒ **先写卡再派发**。
- 消费：`conductor.py:1717 _plan_task_order`（签名加 `deps_by_stem`）+ `conductor.py:1765-1800 execute_loop`（把"见在飞即 return"改为"在飞数 ≥ min(上界, 前沿) 才等"）；前沿序仍按 `_plan_task_order`。

### 3.3 在飞判定

- Python：`_is_in_flight` / `_row_belongs_to` 保持不变（已是单源，`mw_common.row_belongs_to` origin 先决），但其**调用位置**要在锁内复查。
- 新增：`conductor` 与 `worker-store` 各自在锁内重算"该 key 在飞计数 + 在飞卡身份集合"。

## §4 验证计划（VC）

| VC | 判据 |
|---|---|
| VC-101 | 前沿恒等：对 ≥3 组构造 roadmap/任务图复算，实起 = `min(配置上界, |前沿|)`，逐 tick 可重现 |
| VC-102 | 窄前沿不放大：链式依赖（前沿恒 1）时无论上界多大，实起 = 1 |
| VC-103 | 回退：上界 = 1 时两层实起 ≤ 1，且**不需要重启 serve**（配置热读已验证 `conductor.py:3432-3447`） |
| VC-104 | fail-closed：依赖不可解析/悬空/环/写面未声明 → 该层实起 = 1 + 审计行；不得默认放大 |
| VC-105 | 并发安全：N≥4 并行时用 `_workers.parallel` + 写面复算，同文件多写者对 = 0 |
| VC-106 | 无重复派发：注入并发（双进程/双 tick 重入）下同 `task_key` 只产生 1 行（AC-011） |
| VC-107 | 口径一致：面板三量与 conductor 同快照复算一致（AC-012/AC-109） |
| VC-108 | parity：新增键的默认值/取值域/校验两侧逐字段一致，语料冻结值更新 |
| VC-109 | 性能：`advance` 墙钟占比实测（`window_share=Σadvance_ms/Σtick_ms`，经 `beat.data`）；并发 N≥4 时 tick stall 量化（AC-013） |

> 并发安全基线（RQ-D3 真实复现，已写进 VC-106 判据）：今天判据不是"行数"（覆盖语义下恒 1 行），而是 **`ok=True` 次数 == 1 且 timeline `dispatch` 事件数 == 1**。实测双进程对拍 = 2 事件 / 1 行；形状原型（判定进锁）= 5 连跑均 `grants=1/refusals=1/rows=1`。

## §5 风险与缓解

| 风险 | 缓解 |
|---|---|
| 前沿算得出但写面判不了 | 前置 key `mw-write-face-guard` 必须 DONE 才能进 EXECUTE；未声明写面 = serial-only（不在本 key 内重复实现） |
| 任务级 `deps:` 声明为假 | D-104 校验 + fail-closed 串行回退；`[VERIFY]` 复算"前沿非空但声明为无依赖"的样本数 |
| 配置语义变更对既有项目空操作 | 显式说明：改默认不会改变已写显式值的项目；如需迁移，进 plan 阶段作为可选步骤 |
| 并发提高撞 provider rate limit | 不假设；EXECUTE 阶段以失败率/超时率实测（spec §2.2） |
| 两侧镜像漂移 | D-109 + 冻结语料（P-021/P-022） |

## §6 待确认 / 交给 design 调研

- RQ-D3（锁临界区与重复派发防护）、RQ-D4（任务级依赖载体 + 校验 + 前沿消费）、RQ-D5（配置改动集 + parity 重冻 + 面板口径 + advance 阻塞量化）。
