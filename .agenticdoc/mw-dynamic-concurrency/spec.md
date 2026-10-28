# Spec: mw-dynamic-concurrency

> Key: mw-dynamic-concurrency
> 创建时间: 2026-10-14
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 直接服务 goal「让一个 PM Agent 管理多个 Worker Agent **并行**开发同一个项目，解决单 Agent 无法并行的
  问题」中的"并行"承诺。现状是**静态死限**：key 层 `max_parallel_keys=2`、conductor 通道 per-key 硬串行 = 1，
  与依赖图无关；本 key 把并发上限改为**由依赖关系动态求出**，配置值退化为上界。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——前沿/上限每个 tick 由文件（`_roadmap.md` 的 `depends_on` + `_workers.parallel` + 任务书）重算。
  - GC-2: 不修改 pi 核心——实现落在 conductor（Python）与扩展派发面（TS）。
  - GC-3: 队列与索引写继续走文件锁 RMW。
  - GC-4: worker 看门狗语义不变；并发提高不得放宽超时/收敛检查点。
- 冲突：与上个 key `mw-autopilot-slot-capacity` 的 **D-018（per-key 不放开）/D-020（cap 不改）** 冲突。
  用户 2026-10-14 明确裁定：**接受覆盖 D-018**，但前置 = 先落写面判据（`mw-write-face-guard`）。本 spec 的 `deps` 指向该 key。
- 预期收益：并发度由"配置常量"变为"依赖前沿"；判定方式 = 在固定 roadmap 上复算 effective cap，
  与 min(配置上界, 前沿) 恒等；且并发提高后同文件多写者样本仍为 0（依赖 `mw-write-face-guard` 的 AC-005）。

## §1 功能概述

### 1.1 目标

把两层的并发闸都改成"依赖驱动 + 配置封顶"：

- **key 层**：每 tick 计算依赖前沿（`depends_on` 已满足且非终态的 key 集合），实起数 = `min(config 上界, 前沿大小)`；
  不再按固定 2 截断。
- **per-key（conductor 通道）**：在 key 内部按任务依赖图算出可并行任务前沿，实起数 = `min(per-key 配置上界, 任务前沿大小)`，
  且派发前经写面重叠拒绝（`mw-write-face-guard`）。

配置的静态值从"等于并发度"变为"并发度上界"。

### 1.2 技术栈 / 语言

- Python：`packages/multi-workers/autopilot/`（`conductor.py`、`config.py`、`roadmap.py`、`effective_config.py`、`dispatch.py`）
- TypeScript：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（配置镜像）+ `monitor.ts`（呈现）

### 1.3 核心用户场景

1. **宽前沿**：一个 stage 有 5 个互不依赖的 key，配置上界 8 → 5 个同时推进（今天只有 2 个）。
2. **窄前沿**：5 个 key 串成链，前沿恒为 1 → 只起 1 个，不受配置上界影响。
3. **key 内并行**：一个 key 的 tasks/ 有 4 张卡，其中 3 张写面互不重叠且无依赖 → conductor 同时派 3 个（今天 1 个）。
4. **配置封顶**：前沿 10、配置上界 4 → 起 4。
5. **回退**：把配置上界设为 1 → 回到全串行（可作为 kill switch）。

### 1.4 范围说明（不做什么）

- 不包含：写面声明与重叠拒绝本身（`mw-write-face-guard`，本 key 的前置）。
- 不包含：跨项目调度/统一配额（现状各自计额，维持）。
- 不包含：修改 worker 看门狗、超时或收敛检查点。
- 不包含：新增中心化队列/调度进程。
- **包含**（RQ-C2 证据新增的边界）：任务级依赖边的最小机器可读载体（卡头 `deps:` 一行 + 解析 + 消费），因为它是 per-key 动态并发的**前置使能件**，不单独拆 key。
- **不包含**：跨 key 的**任务级**依赖（`mw-a/tasks/T-1` 依赖 `mw-b/tasks/T-2`）——key 层 `depends_on` 已是唯一的跨 key 序，任务级跨 key 边必须显式拒绝（V7）。

## §2 业务约束

### 2.1 平台 / 环境

- 单机 Windows；conductor 是 `mw serve` 监督的常驻子进程，每 tick（默认 4s）从文件重算。
- 配置分层：项目层 `.agenticdoc/_autopilot/config.json`（fail-closed）；机器层 `~/.agents/autopilot-defaults.json`（仅 xkey 键）。

### 2.2 性能指标

- 每个 tick 的前沿/上限计算是纯本地文件推导；新增开销 < 20ms。
- 并发提高后必须可观测失败率（rate limit / 超时 / 锁竞争），不得静默降级。

### 2.3 安全约束

- fail-closed：依赖数据（roadmap `depends_on` / 任务依赖）不可解析时，回退到串行，不得默认放大并发。
- 写面不可判定的任务不得并行派发（继承 `mw-write-face-guard` 的 fail-closed）。
- 不因并发提高让 worker 拿到额外凭证。

### 2.4 集成依赖

- `mw-write-face-guard`（前置，`deps`）
- `.agenticdoc/_autopilot/_roadmap.md`（key 级 `depends_on`）
- `.agenticdoc/<key>/plan.md` / `tasks/*.md`（任务级依赖与写面）
- `.agenticdoc/_workers.parallel`（在飞行与前沿判定）

## §3 验收标准（AC）

> 状态：draft（未锁定）。研究完成后锁定编号。

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 roadmap 的 `depends_on` 可解析时，conductor 每 tick 计算的前沿集合 = {key | deps 全部终态 且 该 key 非终态}，且实起 key 数 = `min(配置上界, |前沿|)`（对 ≥3 组构造语料复算恒等） |
| AC-002 | 在 key 内任务依赖与写面可解析时，conductor 对单 key 的实起 worker 数 = `min(per-key 上界, |可并行任务前沿|)`，且不与在飞 worker 写面重叠（重叠对 = 0） |
| AC-003 | 在依赖数据或写面数据缺失/不可解析时，该层回退到串行（实起 = 1）并写审计行；不得默认放大 |
| AC-008 | 任务级依赖载体：任务卡头一行 `deps:`（`-`/空 = 无；逗号分隔任务 id，语法与 roadmap `depends_on` 同构），由**新增的独立解析器**读取（**不能复用 `card_audit._header_value`**：卡首行是 H1，`_HEADER_RE` 在 `card_audit.py:160-162` 直接 break，实测 5/5 真实卡返回空串）+ 卡头区域规则（H1 / 空行 / `## 元信息` / `- k: v`，遇正文即止）；**无 `deps:` 行 = 无依赖 = 立刻可派**（实测 317/434 张卡无依赖行）；派发 task.md 头回显该字段（插点 `dispatch.py:837` 之后、`phase:` 之前，不移动两侧已冻结行索引断言）；`card_sha256` 哈希卡文件 ⇒ **先写卡再派发**（给卡补 `deps:` 会使既有派发行变 tampered，本仓已有 3 例先例） |
| AC-009 | 任务级依赖图校验：悬空 id / 自依赖 / 环 / 跨 key 引用被检测；任一问题 → **整 key 串行回退**且写 timeline 事件，不得静默永锁。**id→卡文件 stem 的 join 必须用「数字核心」规则**（实测 146 个真实 dep token：stem 精确命中 0、既有 `_plan_task_file_stems` 命中 0、数字核心唯一命中 125），并对同核心多卡（如 `T-01-file-lock` 与 `T-01-task-protocol`，实测 10 例）给出歧义判据，否则真实存在的 `deps: T-1` 会全部假红 |
| AC-010 | key 层依赖图的语义校验在 conductor tick 内被执行（今日只有 CLI/doctor）；悬空/环/前向 stage 被发现时写 timeline 审计事件，不改 key 的 fail-closed 不派发行为 |
| AC-011 | **派发判定与队列写入在同一临界区**："该 key/卡是否已在飞"的复查必须在 `.mw/workers.lock` 内完成（check → append 之间无窗口），且同一 `task_key` 不可能被两个进程各 append 一次（用可观测的并发测试或双进程对拍证伪，不得只依赖 `upsert_worker_row` 的覆盖语义） |
| AC-012 | **在飞口径单源**：`_is_in_flight` / `_row_belongs_to` 的意义只由一处导出谓词定义，并同时服务于派发闸（`conductor.py:698-704/742/1770/2365/2556`）、gate facts（`:6986-6992`）、stage 关闭（`:1288-1292`）、提醒抑制（`:3001-3004`）/defer（`:7986-7990`）与面板 `slotsUsed`（`monitor.ts:917-932`）；口径改变不得让任一点静默滞后（含 `pending` 算不算在飞、`manual` 行算不算槽位两个子问题） |
| AC-013 | **`advance.advance()` 不得成为并发瓶颈**：per-key 并发 N > 1 时，任一 worker 的一次 advance（同步 `subprocess.run`，`advance.py:181-188`，超时 120s）不得阻塞同 tick 内其它 key/卡的派发判定；或给出实测量化（N 倍 tick 延迟可接受）作为等价证据 |
| AC-004 | 配置语义：`max_parallel_keys` 作为 key 层**上界**（默认值、floor、取值域两侧镜像一致）；新增 per-key 上界键（名称/默认/取值域两侧镜像一致），且既有 materialized config 文件不因此变为非法 |
| AC-005 | 呈现：autopilot monitor 同时显示"配置上界"与"本 tick effective 并发"两个量，且二者口径在同一快照内可复算一致 |
| AC-006 | 回退：把上界配置改为 1 时，key 层与 per-key 层均回到串行（实起 ≤1），无需重启 serve |
| AC-007 | 两语言配置镜像：TS `status-model.ts` 与 Python `config.py` 对新增/变更键的默认值、取值域、校验行为逐字段一致（parity 语料） |

## §4 风险与未决项

> 研究回填（RQ-C3，`.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-config-mirror-20261014.md`）

- 风险 1：并发提高后 provider rate limit / proxy 上游池（每端口 8 条流）成为新瓶颈（需实测，不得假设）。
- 风险 2（已实测定性）：任务级依赖**今天不存在任何机器可读载体**（证据 `spec-dependency-sources-20261014.md` §2/§5）：`plan.md` 的 `depends_on` 命中 0、只读"出现顺序"（`conductor.py:1717 _plan_task_order`）；434 张卡里独立 `- 依赖:` 64 行、嵌入 `- 波次: … · 依赖:` 47 行、旧式 `- deps:` 12 文件、裸 `deps:` 6 张，**零解析器**（`card_audit.py` 只消费 `card_path:`/`card_sha256:`）；派发 `task.md`（426 张）里 `deps:` 命中 0。⇒ 必须新增载体（AC-008）。**这是本 key 真正的最大工作量，不是把闸门从 1 改到 N。** 风险：声明为假（卡头写 `deps:` 但实际有隐含顺序）→ 用 AC-009 的校验 + fail-closed 串行回退兜底。
- 风险 3：per-key 并行与 `_index.parallel` claim / 单 active 语义、stage 单调性交互面未测。
- 风险 4（已实测收窄）：现存 `_autopilot/config.json` 实例**只有 2 个**（`H:/git/E2Feature` mpk=4、`H:/git/JCodingAss` mpk=2，均 8 键 partial）。把默认 2→8、floor 2→1 后显式 2/4 仍解析为 2/4（**对已 materialize 项目是空操作**），无文件者变 8，`1` 变为合法。故"既有项目被改坏"风险不成立；真实风险是**写路径会把 partial materialize 成全量键**（TS `status-model.ts:375 saveConfig`、Python `mw.py:3530`），且两侧 schema 互相 fail-closed（未知键作废整份）⇒ 新键必须两侧同波上线，否则 21 键文件被旧侧判 `unknown field(s)`。
- 风险 5（新增）：`max_parallel_keys` **只有项目层可配**——机器层写入被忽略并出诊断（`effective_config.py:62-65 EFFECTIVE_KEYS` 只含两个 xkey 键，实测 origin=default）。若要求"运维可全局封顶"，须显式扩 `EFFECTIVE_KEYS`；本 spec 未要求，按项目层处理。
- 风险 6（已实测）：`validate_roadmap` 已实现（悬空/自依赖/前向/环）但**conductor 从不调用**（`rg validate_roadmap conductor.py` 零命中；`mw_common.py:3694-3696` 原文即写明 "the conductor does not enforce it yet"）⇒ 今日悬空/环 = **静默永锁**（`conductor.py:740` 只 `continue`，无 timeline、无 gate）。AC-010 补可见性，不改 fail-closed 方向。
- 风险 7（新硬阻，实测）：**check-then-act 窗口** —— 在飞判定在 `.mw/workers.lock` **之外**（判据用 tick 开始的 `rows` 快照 `conductor.py:620`，写队列才取锁 `dispatch.py:1155-1156`）⇒ 两进程（serve 重启重叠 / `--once` 与常驻并存 / conductor 与 PM）同时通过判定 → 同 `task_key` 双写，且 `upsert_worker_row`（`mw_common.py:2161-2171`）的覆盖语义把第二次写掩盖（读回校验只查"恰好 1 行"，`dispatch.py:1185-1196`）。**这是放开并发前必须先关的洞**（AC-011）。
- 风险 8（新，实测）：在飞谓词的**爆炸半径**大——`_is_in_flight(` 11 个调用点（`conductor.py:702/1189/1289/1770/2366/2556/3001/4109/4995/6990/7988`），`_row_belongs_to` 5 个（`702/1289/4109/6990/7988`）；只改 `orchestrate` 会让"在飞"在派发链与 gate/closure/提醒之间语义漂移，且其中 `_stage_closure`（保守，安全）与 `_defer_declined_gate`（方向相反）需逐点定标（AC-012）。
- 风险 9（新，实测）：count 口径**三处已分叉** —— conductor（非终态+origin=conductor，pending 也算）/ `slotsUsed`（只数 running）/ `nonTerminalByKey`（path 口径，含 manual）；面板低估会直接使 AC-005 不可满足。实测本仓队列 419 行、`origin=conductor` **0 行**、`keys_conductor_inflight=0`（按 path 判则 3 个 key）。
- 风险 10（新，实测）：`_advance_key` 每调用 ≤1 派（`conductor.py:746`）、`execute_loop` 先 `return`（`:1799`）、`_advance_key` 三个分支各自 `return result.ok`（`:1610/1648/1693`）；若同 tick 第二次派发仍用 `rows` 快照，`_row_exists`（`:1640`）看到的是旧世界 → 重复派同一 `task_key`。
- 风险 11（新，实测边界）：per-key 串行 = **四重结构性判定**（`in_flight_keys` 布尔定义 `:698-704` 阻止整个 `_advance_key`；`execute_loop` `:1770`；`_verify_loop` `:2365/:2556`；stage 关闭屏障 `:1288`），共 17 个判定点（硬 gate 11）。故 per-key 放开不是"把 1 改 N"，而是四层判定同时改造。

- 待确认（RQ-C3 已答部分，其余待 C1/C2 收敛）：
  - 配置上界默认值：C3 实测证明"改默认对既有实例空操作"，故默认值可安全上调；具体值（8 vs 绑 `launcher_max_workers`）仍待定。
  - floor：`2 → 1` 会**翻转两处既有断言**——语料 `test/fixtures/autopilot-config-corpus.json:296-302`（`range-max-parallel-low` 期望 reject→accept）与 `test_autopilot_config.py:50`；两处必须随语义改。
  - per-key 新键落点已勘察完毕（约 30 处，见证据 §4）：Python 4 处（`config.py:83/120/122` + 消费点 `conductor.py:1736 execute_loop`，闸门现位于 `:1765-1771`）+ TS 9 处（`status-model.ts:76/132/194/325/347/379/1602/1738/1793`）+ 面板 `monitor.ts:933/1217` + parity 语料/重冻 6 处 + 计数锁 Python 6 张 / TS 3 张 + README/文档 + 2 个 dist bundle。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- conductor 每 tick 的纯文件重算范式（零私有状态）：`autopilot/conductor.py::orchestrate`（`deps_of` / `status_of` / `in_flight_keys`）。
- **key 层闸唯一消费点**：`conductor.py:744`（`if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"]))`；上一行 `:742` 是同 key 硬串行）。今天已是"在飞 ≥ cap 就停"的上界语义，语义变更只需重定默认/floor + 上游算前沿，消费点本身不改结构。
- **per-key 层闸落点**：`conductor.py:1736 def execute_loop`（`:1765` 任务序、`:1771 return False  # per-key serial: wait for the in-flight task`、`:1799 return result.ok`）——今天只派 1 个 task 就 return。
- roadmap key 级依赖解析：`autopilot/roadmap.py`（`Keys` 表 `depends_on` 列 `roadmap.py:433/483`、`dependency_graph` `roadmap.py:647`、`_find_cycle` `roadmap.py:596`、`validate_roadmap` `roadmap.py:528`）。
- **key 级前沿今天已可算，零数据缺口**：`frontier = {k | _deps_satisfied(deps_of[k], status_of) and status_of[k] not in _DISPATCH_SKIP_STATUSES}`，谓词已落 `conductor.py:740`（依赖）/`:742`（同 key 串行）/`:744`（cap）；终态集 `conductor.py:64 _DEP_SATISFIED = {done, closed-legacy}`（`pending-review` 故意不在内，是 D-005 红线）；`status_of` 来自 roadmap `> key-status:`（`conductor.py:657-658`）；`in_flight_keys` 来自 `_workers.parallel`（`conductor.py:698-702`）。实测复算：E2Feature 42 key → frontier 3（今日实起 min(2,3)=2）；JCodingAss 5 key 全 done → frontier 0。
- **任务级已有半边数据**：完成态 `conductor.py:1766-1768`（`_family_rows` 家族聚合 `conductor.py:1698`）、在飞态 `conductor.py:3539 _is_in_flight`、id↔stem join `conductor.py:2832 _plan_task_file_stems`。
- **每 tick 派发链已逐段坐实（27 段）**：主循环 `conductor.py:8370-8371`；`rows` 快照 = tick 内**唯一**在飞事实源且**不刷新**（`:620`）；"本轮最多派 N" 只有 4 处（roadmap-writer ≤1 `:630/644`、xkey 提案 ≤approved、**不受 key cap 约束且发生在 in_flight_keys 计算之前** `:695`、key 层 cap `:744`、每 key 每次 `_advance_key` ≤1 `:746`）；全 conductor 共 13 个 `dispatch.dispatch(` 调用点。
- **两条通道真正共享 = 同一队列文件 + 同一把 `.mw/workers.lock` + 唯一 spawn 消费者 launcher**（`launcher.py:1776/1805-1813/1854-1858/2008`），**不是同一套在飞计数**；`launcher_max_workers`（默认 8）才是全局真实并发上限。
- **（纠正上一轮认知）PM 手工行不计入 conductor 的 key 在飞**：`_row_belongs_to` → `mw_common.row_belongs_to`（`mw_common.py:2026-2036`）**origin 先决**（`if not worker_is_conductor(row): return False`），实测 419 行全 `manual`/legacy → `keys_conductor_inflight=0`；旁证测试 `test_autopilot_attribution.py::test_six_prefix_rows_are_manual_and_consume_no_slot`。
- TS 只读镜像：`status-model.ts:444/485/591`（`dependsOn` 仅展示、**无校验**）、`monitor.ts:915 blockedBy`。
- 配置分层与镜像：`autopilot/config.py`（`DEFAULT_CONFIG` / `_INT_RANGES`）+ `autopilot/effective_config.py` + TS `status-model.ts`。
- 观测面：`monitor.ts::deriveAutopilotPanel`（`slotsUsed` / `slotsMax` 已有槽位两量）。
- 前置件的写面判定（本 key 直接调用，不重造）。

### 需规避坑点

- P-018/P-019：改并发/派发共享语义前先查消费点与其它 key 冻结判据；本 key 触及全部派发路径。
- P-021：跨语言镜像（`max_parallel_keys` + 新 per-key 键）必须两侧同波 + parity 语料重冻。
- P-022：已知残差记录，不把已知分歧值放进 parity 语料。
- 已知失败模式（上个 key）：`max_parallel_keys` 对已 materialized 2 的项目改默认值是**空操作**——语义变更必须显式处理既有文件。
- 两侧 schema fail-closed（`config.py:152` unknown 分支 / `status-model.ts:252-258`）⇒ 新增/改键必须**两侧同波**（README.md:314、`docs/autopilot-observability-guide.md:23` 已有同名纪律）；否则一侧 materialize 出的全量键文件会让另一侧整份作废。
- 现有 **20 键**硬编码锁（改键即红，须同波改）：Python `test_autopilot_config.py:117/119-125/153/188`、`test_autopilot_effective_config.py:74/209`、`test_mw_autopilot_cli.py:124`、`test_mwgal_t12_stage_close_auto.py:658-667`、`test_mwgal_t15_reattest_confirm.py:720-729`、`test_mwds_t14_producer_skew.py:600`；TS `autopilot-console.test.ts:911/937`、`mwgal-t20-config-parity.test.ts:141/194/208`、`autopilot-config-parity.test.ts:356/361`。
- parity 语料重冻三件套：`test/fixtures/autopilot-config-corpus.json`（须补 `partial-key-<new>`，否则 P6 `covered == expected_keys` 直接红）→ 重算 sha256/count 同步 `test_autopilot_config_parity.py:60-61` 与 `autopilot-config-sync.test.ts:42-43` → 跑两侧 parity 全绿（当前冻结值 `sha256=1e27f5…744a, count=73`，实测与文件一致）。
- 文档漂移：`packages/multi-workers/README.md:312` 与 `conductor.py:139` 仍写"13 键"（现 20），本 key 顺带修正。
- 任务级新增依赖必须同时补 V1–V7 校验（证据 §4.4 附 7 条构造反例）：V1 悬空 id、V2 自依赖、V3 环、V4 plan-only id ↔ 卡文件名不一致（走 `_plan_task_file_stems` 候选映射，否则假红）、V5 引用了非 worker 执行的任务（428 张卡里 74 处 `负责 Agent: PM`）→ 死锁、V6 重试代数归一（`ap-<key>-<stem>-aN`，按 base stem）、V7 跨 key 任务级依赖显式拒绝。
- 任务级依赖的消费点是**单点**：`conductor.py:1717 _plan_task_order`（今天把"出现顺序"当序）与 `conductor.py:1771`（per-key 串行点）；orphan-last 可保留为 fail-closed 回退。
- 调研工具面摩擦（对 `mw-write-face-guard` 有用）：research/read-only 角色**没有 `write` 工具**（allowlist 无 write；`worker_file` 仅限 basename `progress.md`/`report.md`/`report-*.md`），证据文件只能经 bash 写；且 xkey-gate-guard 会拦截"命令文本同时含 `.agenticdoc/_autopilot` 片段 + 写动词"的命令（本轮实际遇到）。⇒ 写面声明必须覆盖"read-only 角色经 bash 写证据文件"这条路径。
