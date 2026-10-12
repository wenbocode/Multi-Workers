# Spec: mw-gate-verdict-hardening

> Key: mw-gate-verdict-hardening
> 创建时间: 2026-10-09
> 状态: confirmed（AC 已锁定）
> 来源: H:\git\E2Feature\.agenticdoc\_autopilot\reflect\ 四条 open 记录（l3-reviewer-stream-abort / pm-gate-idle-no-alert / gate-note-authorization-scope / monitor-frozen-after-mw-restart〔2026-10-09 追加〕）＋ 本项目 **IN-3 事故**复盘（`.agenticdoc/_incidents/in3-queue-reenqueue-20261010/`，2026-10-10 追加 ⇒ G5/G6）
> deps: `mw-autopilot-slot-capacity`（gate redesign）——已 DONE 并提交（`b8bc115ff` 核心 + `27e3c927e` dist + `10446aefb` 收口），写面已释放

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（无 status 行，三段有真内容 → 视为已确立）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的**无人值守收敛与门禁取证完整性**部分——autopilot（conductor + L3 门禁 + 人工闸门）是"并行开发"的编排内核，其静默停摆与门禁误判直接决定框架能否长跑。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——协调只经文件系统（`_workers.parallel` / `_index.parallel` / gate 文件 / timeline）；本 key 的提醒是**事件 + 文件**，不得新增常驻调度组件。
  - GC-2: 不修改 pi 核心——所有功能通过 Extension API / conductor 实现。
  - GC-3: Worker 进程级隔离——不改变 worker 生命周期机制。
  - GC-4: 不单方面抬 `PI_WORKER_IDLE_MS`（`mw-worker-timeout-convergence` 定调）；本 key 若触碰 L3 中止，走“指纹 + 有界重掷”，不靠放宽看门狗。
  - GC-5: **派发作用域分层**（2026-10-10）：PM 侧自动派发只作用本窗口 watch 的 key + `_scratch`；`mw` 指令面保持全局扫描。隔离靠作用域 + 判据，不靠新建服务/常驻组件。
  - GC-6: **产物自带状态 + 身份不可复用**（2026-10-10）：任务终态写入产物自身（`workers/<task>/run.json`），由 worker 自写；`task_key` = 一次运行，复审/补充必须新 key，旧产物只读；历史任务不回填。
- 冲突：无。
- 预期收益：本 key 达成后对项目目标的具体贡献（done 时在 achieved.md 对照判定）：
  1. 无人值守时待答闸门不再静默——最长静默从"人回来看"降到"提醒阈值 30min"（判定：AC-005~AC-008）。
  2. L3 流中止从"看起来跑过了"变成机械可判、可自愈——减少人工开闸与无意义重跑（判定：AC-001~AC-004）。
  3. AC/VC 生效文本的变更授权机器可判——阻断“闸门自由文本当授权”（判定：AC-009~AC-012）。
  4. 观测面不再撒谎——面板帧自证新鲜（冻结可见、可自动判过期），数据面变化 ≤2 个刷新周期内跟随（判定：AC-015~AC-018）。
  5. **队列不再能“整表复活”**：行缺失/不可读 ⇒ 零派发 + 告警（而非 250+ 任务全量重跑）；单轮派发有配额、spawn 有上限（判定：AC-020/021/023）。
  6. **本 key 执行不再影响历史 worker**：PM 侧派发作用域收窄到本 key（其它 key 行逐字节不变），且任务终态写在产物自身 ⇒ 即使队列被重建，done 任务也不会重跑（判定：AC-019/022/024）。

## §1 功能概述

### 1.1 目标

收口 E2Feature reflect 台账里四条**框架侧仍 open** 的根因，每条对应一个独立可验收的机器判据（G4 于 2026-10-09 追加；**G5/G6 于 2026-10-10 由 IN-3 事故追加**，来源从 reflect 账账扩到本项目事故复盘）：

- **G1 l3-reviewer-stream-abort**：L3 reviewer 轮次被 provider 流提前关闭（`stream closed before response.completed`），`output.md` 只剩占位模板，conductor 只能看到"无两节"，与"reviewer 写错文件"、"真 FAIL"混为一谈。目标：给该中止一个**机器指纹**（`l3-aborted`），与另外两类无裁决互不重合，并在轮预算内**有界自动重掷**。
- **G2 pm-gate-idle-no-alert**：闸门是"等人"的阻塞态，而框架唤醒语义是"事"驱动；一旦建门时无人看，之后无任何周期性提醒，实测最长静默 12 天/累计数十小时。目标：pending 超阈值产生**去重的主动提醒**，监视面可见"挂了多久 / BLOCKED_ON_HUMAN"。
- **G3 gate-note-authorization-scope**：闸门 note 的**自由文本**"属可修范围"被 repair worker 读成"授权改写 AC/VC 生效口径"。目标：授权范围**显式化**（gate 闭集授权字段），且 `advance *->done` 前对 AC/VC 文本变更做**机械授权检查**（fail-closed）。
- **G4 monitor-frozen-after-mw-restart**（2026-10-09 追加）：`/mw restart` 后 monitor 面板**冻结在旧帧**上——显示新 serve/conductor PID（看着活着）却 `workers: 0 running`（同刻 `_workers.parallel` 实有 running 行），且不报错、不自证过期。RQ-4 证伪了记录里的首要嫌疑（`launcher-beat.<pid>` 身份耦合：TS 侧命中 0）并钉出真实约束：**可见的陈旧帧 ⇒ 循环仍在跑、但每帧在改动 widget 之前就失败被吞**（`monitor.ts:828-833` 裸 catch）；停表会清 widget，所以不可能是停表。目标：帧携带**绝对采集时刻**（冻结可自证）+ 失败不静默丢帧 + 数据面变化有界跟随 + 会话替换后重挂。
- **G5 队列完整性**（“launcher 重启重排已 acked 任务”的真命题，2026-10-10 重定界）：**IN-3 事故**——`_workers.parallel` 被整表重建（252 行、单秒内、全为非终态），launcher 全量重派（峰值 66 并发），20+ key 的产物被重跑覆写，并**下游引发 IN-1/IN-2**（重跑出的 `mvr-t16` 删了 3,448 个 tracked 文件）。根因：**读侧静默丢行**（行格局 8→9 列漂移 + 长驻窗口跑 7..8 列解析器 ⇒ `return undefined`）+ **写侧无条件整表回写**（把丢弃固化为删除）⇒ `readAll()` 归零；叠加**无上限 spawn**、**判据不看终态**、**`_workers.acked` 不参与**、**丢行无告警**。目标：读侧不丢行且可计数告警 + 行缺失时 fail-closed + 单轮派发配额 + 有界 spawn（AC-020/021/023）。
- **G6 派发隔离与运行身份**（2026-10-10 用户要求，IN-3 同源）：① **隔离**——本 key 的一次派发就能把全项目队列翻面（PM 侧自动派发无作用域概念，副作用面 = 28 个 key）；② **产物自带状态**——任务终态只存于共享台账，台账重建即“复活”；实测活体样本：台账已 `done` 的 `msc-t14` 重跑进程在 11:45:40 又覆写了自己的 `output.md`；③ **身份不可复用**——worker 自声明 done 后不得重启，需补充则新起 worker。目标：PM 侧作用域收窄（写面限定本 key + `_scratch`；**读面保持全局只读**：可查任意 key 的行与状态但不得改/重派，见 AC-024；`mw` 指令保持全局）+ `run.json` 产物自带终态（终态永不重派 + `supersedes` 新 key）。（AC-019/022）

### 1.2 技术栈 / 语言

- Python（`packages/multi-workers/autopilot/`，conductor 为主）
- TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/`，面板 / status-model 镜像 / gate 写侧）
- 测试：pytest（Python 包根）+ vitest（coding-agent）

### 1.3 核心用户场景

1. **长跑无人值守**：PM 窗口夜间无人值守，某个 L3 轮流中止 → 机器打 `l3-aborted` 并自动重掷一次；若仍失败，停在明确的可判状态而不是"无裁决"。
2. **夜里建门**：conductor 建了 stalled / stage-close 门 → 超过 30min 无人答 → 框架主动提醒（同一门 ≤2 次）；早上 `mw doctor` / 面板第一眼能看到"哪个门挂了多久"。
3. **below→meets 翻转**：repair worker 想把 reviewer 判 below 的问题"修好" → 它不得改写已锁定 AC/VC 生效文本；若改了，`advance done` 必须因缺"用户批准记录"而拒绝。
4. **面板冻结**：面板停在 1 小时前的帧上 → 帧内“采集时刻”不再前进，超过 3 个刷新周期即显式告警；数据面一变化（`_workers.parallel` 落 running 行）面板 ≤8s 跟随，不需要人工 off/on。
5. **队列被重建（IN-3 重放）**：任一长驻窗口跑到旧解析器、或队列文件被外部清空/截断 → **不得**重新入列（零派发 + 告警），而不是把 250+ 个已终态任务当新的重跑。
6. **本 key 自己派活**：PM 在一个有 28 key / 250+ 行的项目里派 1 个任务 ⇒ 其它 key 的行逐字节不变（隔离）；同时 PM 对其它 key 保持**只读全局**：`list_tasks` 的 `scope:"all"` 能看全部 28 个 key 的行与状态，但对**他窗口 live 持有**的 key 一律拒绝派发/推进（AC-024）；写面收窄只加在 PM 自动派发上，`mw` 侧与未认领 key 不受限（AC-019）。
7. **复审已 done 的任务**：不想覆盖旧产物 ⇒ 新起 `<task>-r2` 并声明 `supersedes`；旧的 `done` 产物永不被重跑、也不被覆写（AC-022）。

### 1.4 范围说明（不做什么）

- 不重设计闸门命题体系（`mw-autopilot-slot-capacity` T-07 已做自动决策核心）；本 key 只补其未覆盖的三处。
- 不修改 `PI_WORKER_IDLE_MS` / `DEFAULT_IDLE_MS`（GC-4）。
- 不改 L3 判定的**严格性**（FAIL 判据、裁决源优先级不动；只加"中止"这一类的新指纹）。
- 不做 provider 侧流修复（模型/网关问题），只做框架侧的可判与自愈。`stream closed before response.completed` 逐字节出处不在本仓（来自网关/旧构建），指纹只按**子串**匹配，不断言该文本由 pi 产生。
- **不处理第四类**（RQ-1 发现）：reviewer 用**无节标题的散文** `report.md`（既无两节、也无 FAIL 行，现状判 below），实例 `FeatureMigrator/gui-monitor-hitl-e2e l3-a3`。它不是 aborted、也不该算真 FAIL；design 里显式声明其归属（视为 A 类「载体不符」变体），AC-002 仍只覆盖原三类。
- 不给 gate 增加"超时自动 approve/reject"（工具层 `xkey-gate-guard.ts` 的"只有人能答"语义保持）。
- 不动 TUI 渲染层（RQ-4 S6 已排除 `packages/tui/src` 侧丢更新）；G4 只改 `monitor.ts` 的采集/失败处理/生命周期。
- 不做 `launcher-beat.<pid>` 目录扫描（RQ-4 已证伪该耦合：TS 侧 src/dist/全局 bundle 三处 grep 合计 0 命中）——reflect 记录里的这条长期处置项作废。
- 不把“冻结”归因于 `/mw restart`：RQ-4 证明重启只杀/起 serve 及其子进程、**不触碰 pi 进程**（`.mw/window-model` mtime = 2026-09-23，10-09 无任何 `session_start`/`/reload` 痕迹）。
- **不把队列拆成 per-key 文件**（结构隔离）：本 key 只做**逻辑隔离**（作用域 + 判据 + 身份）；per-key 队列 + 只读聚合面板若要做，另立 key（用户 2026-10-10 定调）。
- **不把作用域收窄加到 `mw` 指令面，也不收窄读面**：`mw` CLI（launcher 全量 spawn / `update_status` 任意 key 回写）与 TS 侧默认 `scope:"cli"` 调用保持全局能力；`list_tasks` / `mw doctor` / 面板对**任意 key** 只读可见（用户 2026-10-10 定调）。原文举例的 `mw dispatch` 子命令实测**不存在**（`mw.py` 子命令表无 dispatch），故反向用例改为真实的全局写面，见 AC-019 修订。
- **不引入中心调度器**：仍只靠文件系统协调（GC-1）；`run.json` 是产物自身属性，不是新的“状态服务”。
- **不回填历史 `run.json`**：无该文件的历史任务行为与今日一致（P-018）；不批量补写历史目录。

## §2 业务约束

### 2.1 平台 / 环境

- Windows 开发机为主，Python 3.10+，Node/vitest。
- conductor 是常驻进程（`mw serve` 拉起）⇒ 框架侧改动需重启 serve 生效（P-015）。
- 多会话并行开发同一 cwd：`conductor.py`/`gates.py`/`status-model.ts` 曾是 `mw-autopilot-slot-capacity` 的写面，该 key 已提交（`b8bc115ff`）⇒ **写面冲突已解除**；残留脏文件（`dist/**`、`test_common.py`、`mw-vision-role/**`）非本 key 写面。

### 2.2 性能指标

- 提醒判定在既有 tick（默认 4s）内完成，不引入额外轮询进程（GC-1）。
- `l3-aborted` 判定在既有轮次收口路径内完成。**前提修正（RQ-1）**：`_l3_round_verdict`（`conductor.py:1556`）当前**并不读 `worker.log`**，且其状态门（`:1585-1586`）对 failed 直接短路 ⇒ 指纹必须挂在该状态门**之前**，design 需明示新增一次 `worker.log` 读取及其成本（不再宣称"零额外读取"）。
- G4 的帧内改动不新增 IO：采集时刻与失败摘要都是既有 tick 内的内存计算；失败时的降级帧不得引入新的文件读。

### 2.3 安全约束

- 授权字段与 done 前检查均 **fail-closed**：缺**批准记录**或**授权字段** ⇒ 视为未授权，不得放行。**唯一例外（以 AC-025⑤ 为准）**：契约身份锚 `evidence/contract-freeze.json` **缺失/损坏** ⇒ 视为「无锚 ⇒ 放行」（`no_anchor`），不属于本条「缺记录 ⇒ 未授权」；只有「**有锚 ∧ AC/VC 生效文本变更 ∧ 无批准记录**」才拒绝（对齐 design D-015 `[REVISED @ 2026-10-10 18:55]`：fail-closed 若覆盖到「无锚」，会把本仓全部历史 key 的 done 永久锁死，与 AC-013/P-018 冲突）。
- 提醒不含凭证；不修改 `~/.pi/agent/`（P-002）。

### 2.4 集成依赖

- timeline 事件机制（`timeline.py`）、gate frontmatter（`gates.py`）、roadmap key-status（`roadmap.py`）。
- PM hook / `triggerTurn` 通道（`mw-*` 既有提醒先例）用于把提醒推到 PM 主窗口。
- monitor 面板（`autopilot/monitor.ts` / `console.ts`）与 `mw doctor`（`mw_common.py`）作为可见面。

### 2.5 G5/G6 追加约束（2026-10-10，IN-3 驱动）

- **队列行格局与版本**：容忍 7..9 列 + 可选首行 `# mw-queue:vN`；**不可解析行必须计数 + 告警 + 回写保留**（不得静默丢行、不得隐式删除）；无头的历史文件**零回写**（P-018）。
- **派发安全性**：队列不可读/空 ⇒ **fail-closed 零派发 + 告警**（真·新项目除外）；单轮派发配额 `dispatch_max_per_scan`（默?3）；launcher 并发默认有上限 `launcher_max_workers`（默?8，不再是无限制）。
- **隔离（GC-5）**：PM 侧自动派发作用域 = 本窗口 watch key + `_scratch`；**`mw` 指令面保持全局**；**读面（`list_tasks` scope all/key、`mw doctor`、面板）对任意 key 保持全局只读**，写面（`dispatch_worker` 显式 `key` / `advance_phase`）对**他窗口 live 持有**的 key 必须先拒后动并返回固定码 `[cross-key-read-only]`（AC-024）。
- **产物自带状态（GC-6）**：`run.json` 由 worker 自写；launcher 仅补 `lost`；`done` 终态**永不重派**；复审/补充必须新 `task_key` + `supersedes`，旧产物只读；历史不回填。
- **新增配置键（本组 3）**：`dispatch_max_per_scan`（1..64，默认 3）、`launcher_max_workers`（1..64，默认 8）、`queue_alarm_delta`（10..10000，默认 50）⇒ `DEFAULT_CONFIG` **14 → 17**（T-18 落地）；T-02 的 G1/G2 3 键再 → **20**（两侧合计 20，见 design §2.5）。
- **性能**：每次 `agent_settled` 从“全项目 28 key 扫描 + 读全表”降为“本 key + 每候选 1 次小文件 stat/read”（副作用面 O(28 keys) → O(1)）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-10-09T08:45:14Z，编号永不回收
> 追加范围 G4（monitor 冻结）：AC-015 ~ AC-018 于 2026-10-09 顺延追加；旧编号与旧内容未改。
> 追加范围 G5/G6（派发隔离与运行身份）：AC-019 ~ AC-023 于 2026-10-10 顺延追加（用户要求：①隔离：本 key 的执行不得影响任何历史 worker；②产物必须自带状态，不能只靠队列记录；③worker 自声明 done 后不得重启，需补充则新起 worker）。旧编号与旧内容未改。
> 追加范围 G6-读侧（跨 key 只读权限）：**AC-024** 于 2026-10-10 顺延追加（用户要求：PM 可以看其它 key 的 workers 与状态，但不能有改、重新派发等操作，也就是只读）；同次把 AC-019② 的反向用例修订为真实存在的写面（`[REVISED @ 2026-10-10]`，编号未改）。

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 当一轮 L3 reviewer 的 `worker.log` 含 `stream closed before response.completed` 且 `done exit=0`、且该轮 `output.md` 缺 `## Quality Gate Report` 与 `## Achieved` 两节时，conductor 在该轮记录与 timeline 写入机器可读的 `l3-aborted` 标记（事件 + 持久字段），不得仅记为通用"无裁决"。 |
| AC-002 | 在构造输入下，三类"无有效裁决"（裁决源写错文件 / provider 流中止 / 真 FAIL 标记行）各命中且仅命中一类机器判据；同一输入不得同时判为两类。 |
| AC-003 | 被标 `l3-aborted` 的轮次在轮预算耗尽前自动重掷一轮（默认上限 1 次，可配置），重掷产生独立轮次记录与可观测计数；重掷出裁决则按正常路径推进。 |
| AC-004 | 反向判据：`worker.log` 无 `stream closed` 行、或 `output.md` 两节齐全的轮次，`l3-aborted` 假阳性 = 0。 |
| AC-005 | 任一 `status=pending` 的 gate 持续超过阈值（默认 30 min，可配置）时，框架在无人提问的情况下产生一次提醒（timeline 事件 + PM 侧可见推送）；同一 gate 最多提醒 2 次。 |
| AC-006 | gate 被应答（status ≠ pending）后，该 gate 不再产生任何提醒事件（零残留）。 |
| AC-007 | 提醒判据只对 pending gate 生效：已答 gate、已终态 stage 的 gate、以及非 gate 的静默（如 EXECUTE 期事件稀疏）不得触发提醒。 |
| AC-008 | 监视面（monitor 面板与 `mw doctor`）对 pending gate 显示其 pending 时长与 `BLOCKED_ON_HUMAN` 类置顶指示；显示与 gate 文件真实状态的偏差不超过一个 tick。 |
| AC-009 | gate frontmatter 新增显式授权字段（闭集动作类型，如 `retry` / `install` / `contract-change`）；未被该字段列出的动作类型不得被 worker 引用为授权源。 |
| AC-010 | worker（repair / phase-writer）提示词含硬约束：不得修改已锁定 AC/VC 的生效文本；确需变更必须走重开流程，并在产物中显式声明变更清单 + 授权源。 |
| AC-011 | `advance *->done` 前做机械检查：若本轮 diff 触及 `spec.md` / `design.md` 的 AC/VC 条文且不存在用户批准记录，则拒绝推进并在 timeline 留痕（分类机读，P-009 口径）。 |
| AC-012 | 反向判据：仅凭 gate 自由文本 note（如"放宽的是验证方式与文档同步，属可修范围"）引用为授权源 ⇒ 机械判为**未授权**（fail-closed），不得放行。 |
| AC-013 | 新增 gate 字段缺失时保持"未物化"：历史 gate 文件（含 `_gates-flood-20260924` 归档）照旧全部 parse 成功，`_REQUIRED_FIELDS` 一格不加；缺字段时渲染与加该功能前逐字节相同（P-018 口径）。 |
| AC-014 | G1/G2/G3/G4 每条机器判据附**非空洞对照**（摘掉/反转判据 ⇒ 对应用例转红），且所有 `[VERIFY]` 行数值来自实测，回执中"已机器校验"类声称必须带 `文件:行号` 或测试名坐标（P-016 / P-023 / P-025）。 |
| AC-015 | monitor 面板的每一帧携带**绝对采集墙面时刻**（并可选单调 tick 计数）；面板连续超过 3 个刷新周期未刷新（帧内时刻不前进）时，监视面显式告警"快照过期 / 刷新已停"，不得静默停留在旧帧。 |
| AC-016 | 数据面变化后，面板在 ≤2 个刷新周期（8 s）内跟随：`_workers.parallel` 有 N 行 `running` 时面板必须显示 `workers: N running`；该反向用例纳入自动化。 |
| AC-017 | tick 内失败不得静默丢帧：`monitor.ts` 的裸 catch（`:828-833`）改为产出**带诊断的降级帧**（含最近失败时刻与错误摘要），tick 内未受保护的读（`worker-store.ts:119`、`mw-runner.ts:85`）与 `finally` 内的 close 失败一律降级而非跳帧。 |
| AC-018 | 会话替换/重激活（`/new`、`/resume`、`/fork`、`/import`、`/reload`）后面板必须被重挂（`session_shutdown` 停表，或 `autoStartMonitor` 检测 ctx 变化后 stop+start），不得永久消失；`/mw restart` 后不需要任何手工 toggle。 |
| AC-019 | **派发隔离（作用域分层）**：① **PM 侧自动派发**（`agent_settled` 触发的扫描）的作用域必须收窄为“本窗口 watch 的 key + `_scratch`”，单次派发副作用面至多 1 行，项目内其它 key 的队列行（行数与状态）必须逐字节不变；② **PM 以外的写面**（launcher 按 `_workers.parallel` 全量 spawn、`mw_common.update_status()` 任意 key 回写、TS 侧默认 `scope:"cli"` 的程序化调用）保持全局能力，不受①限制。反向用例：①存在 28 个 key / 250+ 行队列时，PM 自动派发 1 个任务 ⇒ 其它行零变化；②同一状态下 `dispatchNewTasks(..., { scope: "cli" })` 仍能跨 key 派发；③未认领的新 key 经 `dispatch_worker(key=新 key)` 显式派发 ⇒ 成功（新建 key 流程不变）。[REVISED @ 2026-10-10：原文②把反向用例写成 `mw dispatch --key <其它 key>`，但实测 `mw.py` **没有** dispatch 子命令，故改为真实全局写面；“他人 live key 不可写”由 AC-024 承接。] **补充（T-20 落地）**：被作用域跳过的 key **必须可见**（一次扫描聚合一行 `kind="out-of-scope"` 告警）——收窄不得变成静默。 |
| AC-020 | **行缺失 fail-closed**：队列行缺失 / 不可读 / 整表为空时，重派必须拒绝：新增行数 = 0，并产出机器可读告警（事件 + 计数），队列保持原样。反向用例：清空 `_workers.parallel` 后触发扫描 ⇒ 新增 0 行 + 1 条告警。 |
| AC-021 | **单轮派发配额 + launcher 并发有界**：① 一轮扫描新增行数上限 N（默认 3，可配 `dispatch_max_per_scan`）：候选 > N 时**截断至 N**（配额内候选正常派发，派满即止）并对本次扫描告警，≤ N 时正常派发；② **launcher 并发上限永不为无界**：未显式传 `--max-workers` 时取 `launcher_max_workers`（默认 8，1..64；配置不可读/越界 ⇒ 回落 8），显式值优先；③ `_workers.acked` 参与派发：**已 acked 但队列行非终态**（队列被重建）⇒ 收敛为终态（`run.json` 终态优先，否则 `done`）且**不 spawn**，已 acked 行永不 spawn；ack 文件不可读/格式坏一律视为“无信息”，不得因此跳过任务。反向用例：①10 候选全合法 ⇒ 单轮新增 = 配额 + 告警；②12 候选 + `max_workers=None` ⇒ 恰好 8 个 spawn（不是 12）；③项目 config `launcher_max_workers=2` ⇒ 2 个 spawn；④acked 行 ⇒ 0 spawn；⑤ack 文件为垃圾内容 ⇒ 仍正常 spawn。[REVISED @ 2026-10-10：原文只写①单轮配额；②③ 是 D-027/IN-3 放大器 F1/F3 的封堵，由 T-18 落地（设计 §11.3）。] |
| AC-022 | **产物自带状态 + 运行身份不可复用**：每次 worker 运行在**自身目录**写入机器可读终态（至少含 `task_key`、`run_id`、`status`、`started_at`、`ended_at`、`exit`），且由 worker 自己写；派发/重派判据**首先**读该产物终态。终态为 `done` 的任务**永不重启**；需要补充或复审时以**新 task_key** 派发，并在新任务中声明 `supersedes: <旧 task_key>`；旧产物只读，不得覆写。**[REVISED @ 2026-10-10（T-20 落地）]**：①终态集 = `done\|failed\|needs-clarification\|lost`（TS 与 Python 恒等）；②**同一 task_key 一律不重跑**（含 `supersedes`，后者只作用于被替换的旧目录且要求其已终态）；③launcher 仅允许补写 `lost`（进程不在且无终止证据），保留现场、不改产物；④机器可读标记 `<!-- mw-run: … -->` 写在 harness 段首行（不得夺占 agent 写的 `VERDICT=`/`TASKS=` 文件首行）|
| AC-023 | **行格局可识别 + 读侧不得静默丢行**：队列行格局变更必须可被新旧读写侧**显式识别**（版本头或版本列）；读侧遇无法解析的行必须计数 + 告警，且回写时**不得删除**该行；`readAll()` 丢弃行数 > 0 时抑制本轮派发（替代现行为：静默 `return undefined` + 回写即删）。**写侧范围（REVISED @ 2026-10-10）**：**所有**队列写者——TS `upsert`、Python `update_status` / `archive_stale_entries` / `autopilot/dispatch.py` 的 upsert——必须**只重写自己那一行**，其余行（含无法解析行）逐行原文保留；无匹配行时**不得**重写文件（空项目首次写可建空文件）。行宽判据是 **7..9 的区间**（7/8/9 列全可读）。只读面（`mw doctor`）新增三条**无状态**形状判据：`queue-rows-unparsable`、`queue-burst-shape`（行数 > `queue_alarm_delta`（默认 50） ∧ 非终态占比 > 0.9）、`run-ledger-conflict`（T-20 落地后生效）。反向用例：①10 列行 ⇒ 计数=1 且回写后原文仍在；②三个 Python 写者各写一次后 `unparsable` 行原文仍在；③8 列行必须可读；④252 行 / 100% 非终态 ⇒ doctor 含 `queue-burst-shape`，健康队列**不含**。 |
| AC-024 | **PM 对他人 key 只读（读全局 / 写限定）**：① **读面不得受限**——同一窗口对任意 key 的读（`list_tasks` 的 `scope:"all"` / `scope:"key"`、`mw_status`、`mw doctor`、监视面板）必须始终可用，读面与写面守卫互不影响（不得因为“不是我的 key”而看不懂状态）；② **写面必须拒绝跨 key**——对**另一窗口 live 持有**（`_index.parallel` 行 Claim 列 `claimState == "held-live"`）的 key，`dispatch_worker`（显式 `key`）与 `advance_phase` 必须**在产生任何副作用之前**拒绝，返回机器可读固定码 `[cross-key-read-only]` 并指出正确下一步（`switch_key`）；③ **可写面保持**：本窗口自有 claim、**未认领**的 key（新建 key 流程：写 spec.md → advance → dispatch）、`_scratch`。反向用例：①同一窗口对 foreign-live key 执行 `list_tasks scope:"key"` ⇒ 正常返回该 key 的行；②同一窗口对同一 key 执行 `dispatch_worker(key=…)` ⇒ 拒绝且**零副作用**（无 task 目录、无队列行、无 `_workers.parallel` 文件）；③`advance_phase` 拒绝时 gate 脚本**不得被执行**；④未认领新 key 与自有 claim key ⇒ 派发正常成功。 |
| AC-025 | **G3 锚点必须由框架自身建立（否则 AC-011 在生产中永不触发）**：① **自动建立**——key 首次被观测到 `phase == design` 时冻结 AC 块、`phase == plan` 时冻结 VC 块；**每块最多写一次，已存在的非空块永不重写**（一次 tick 内合并为一次原子写）；② **建立留痕**——新增 timeline 事件 `contract-frozen`（`data={block, phase, source, freeze_rel, ids}`，P-009 机读分类）；③ **显式入口**——`mw autopilot contract-freeze --project <dir> --key <k> [--block ac|vc|all] [--force] [--json]`（缺块补齐；已存在且未变更的块默认跳过；已**变更**的块必须 `--force` 才重冻，并打印被替换的 id）；④ **不回溯**——`phase` 已在 `tasks/execute/verify/done` 的历史 key **不自动补锚**（P-018 口径：无历史可回填），其锚点只能由显式 CLI 建立；⑤ **缺失/损坏的锚一律视为无锚 ⇒ 放行**（与 T-04 `evaluate` 同口径；否则等于把所有历史 key 永久锁死，与 AC-013 冲突）。反向用例：①把临时 key 推进到 design 并跑一次 tick ⇒ 出现 sidecar 且**仅含 AC 块**；推进到 plan ⇒ VC 块加入且 AC 块**字节不变**；②改写一条 AC 文本 ⇒ `evaluate` 拒绝（G3 真活）；③再次 tick 不重写（文件 sha 不变、无第二个 `contract-frozen`）；④`--force` 才允许重冻。 `[ADDED @ 2026-10-10]` |

> 追加范围 G3-锚点（补齐 AC-011 的可达性）：**AC-025** 于 2026-10-10 顺延追加（T-11 交接 R1：design D-015 / §4.5 要求 `mw autopilot contract-freeze` 与两处接受边界冻结，但无卡承载 ⇒ G3 在生产中处于休眠态：无锚 ⇒ `no_anchor` ⇒ 永不拒绝）。旧编号与旧内容未改动。
> 注（2026-10-10，原地追加说明，不改 AC-014 原文）：AC-014 的"非空洞对照 + `[VERIFY]` 数值来自实测"要求随范围追加而**同样适用**于 G5（AC-019 ~ AC-021）与 G6（AC-022 ~ AC-023）及 AC-024 的每条机器判据。

## §4 风险与未决项

- ~~风险 R1：写面冲突~~ **已解除**（2026-10-09）：`mw-autopilot-slot-capacity` 已提交 `b8bc115ff`/`27e3c927e`/`10446aefb`；EXECUTE 前置门禁 D-003 满足。残留脏文件均在非本 key 写面。
- 风险 R2：**提醒过密变噪音**。缓解：按 gate id 去重（同一 gate ≤2 次）、answered 即停、阈值可配。
- 风险 R3：**`l3-aborted` 与既有 `l3-no-verdict` 语义打架**。缓解：只做"新增分类 + 回退到既有路径"，绝不改既有严格性；不动 `_L3_SOURCE_ORDER` 与 FAIL 判据。
- 风险 R4：**done 前 AC/VC diff 误伤合法变更**。缓解：只把"无批准记录的 AC/VC 文本变更"判红；批准记录通道复用既有 gate / decision 载体（不新造机制）。
- 待确认：授权字段是 gate schema v3 还是 v2 可选扩展（**RQ-3 定：走 v2 加性扩展，无需 v3**；字段形态与「创建时盖章 vs 应答时填写」待 design 定）。
- 待确认（RQ-2）：提醒推送通道——conductor 侧无推送原语（`sendMessage` 零命中），extension 侧唯一先例是 `ui-bridge.ts:131 deliverPmAlert`（`triggerTurn`，调用点 `pm-orchestrator.ts:584`）。AC-005 的「无人提问也收到」**必须**在 extension 侧新增 gate 消费者，否则只能发 timeline 事件（仅人下次跑命令可见）；design 必须明确取舍。
- 待确认（RQ-2）：提醒时间锚 = `created_at`（base required 字段，历史 v1 门也有）；**不得用 `expires_at`**（E2 实测 21 个门全 v1、该字段全缺，以其为键对历史门永不触发）。
- 待确认（RQ-2）：doctor 文本阈值当前为 24h/72h（`mw_common.py:2847-2849`），与 spec 的 30min 提醒阈值不一致；design 定是否统一（拉低文本阈值 vs 保持 doctor 零扰动仅靠新提醒事件）。
- 待确认（RQ-2）：AC-005「同一 gate ≤2 次」的计数载体——`_timeline_has_event` 是有界尾部布尔去重，不能表达次数；二选一：detail 序号（`reminder 1/2`）或复用 `auto-decisions.jsonl` 单写者 append ledger。
- 待确认（RQ-1）：AC-001 的「done exit=0」只指 `worker.log` 的 `[worker] done exit=0` 行；同轮 `_workers.parallel` 行 status **必为 failed**（6/6 实测，由 launcher 按真实退出码回写）⇒ 实现/夹具**不得**要求 `status=done`，否则 6/6 真例全漏判（`worker-mode.ts:1270-1297` 不读 `stopReason`，`print-mode.ts:141-147` 才设 exitCode=1）。
- 待确认（RQ-1）：G1 实现挂点与闭环——指纹挂 `conductor.py:1585` 状态门之前；重掷动作已存在于 `_verify_loop:1837` 的 no-verdict 分支（`:1886-1912`，重掷 dispatch `:1905-1911`），只需新增专用分类 + 不占共享轮预算的专用有界计数（建议独立 loop 标签复用 `state.used_rounds`）；必须同步 `STALL_REASON_CODES:4891`（测试钉死 `==12`，`test_autopilot_auto_decision.py:301`）与 `_recompute_l3_stall_code:5348`，否则判成 `stalled-reason-drift`。
- 待确认（RQ-1）：`l3-aborted` 作为 timeline 事件需两侧同步（`timeline.py:67-96` + `status-model.ts:962-988`，parity 测试 `autopilot-event-parity.test.ts` 集合相等）；若仅作为 gate `reason_code` 则 TS 透传、只改 Python。design 定取哪个（或两者）。
- 语料基线（RQ-1 二次执行，快照 `2026-10-09T12:30Z`，**活语料**——E2Feature 在两次快照之间新增了 3 个 L3 轮）：
  `worker.log` **878**（E2 621 + FeatureMigrator 257），L3 轮 **57**（E2 34 + FM 23，全部 `type: reviewer`）；
  `stream closed` 命中 **6**（全 E2、FM 0；6/6 同时满足 L3 + failed + 两节均缺 + `report.md` 缺席 + FAIL 标记 0 + `[END] exit=0`）；
  负例 **51**（`status=done` 49 + `failed` 2；四象限 `O1R1=28 / O0R1=16 / O1R0=4 / O0R0=3`，FAIL 标记 17）；
  `failed ∧ 两文件均缺` 的假阳性边界 = 8（其中 marker 拆分 6B/2D，2D = provider 403）。
  reflect 声称 7 例，**实测 6 例**。（首稿基线 844/54/48 已作废，见 `_orig/` 备份。）
- 待确认（RQ-4）：G4 的**触发语句不可得**——面板帧无采集时刻戳，留存证据无法区分"活帧"与"冻结帧"，冻结窗口只能给到 [15:21:13, 16:37:22]（4,569 s ≈ 1,142 个 4s tick）。因此 AC-015（帧自证新鲜）既是修复也是取证手段；design/plan 不得声称"已定位触发语句"。
- 待确认（RQ-4）：G4 与 G2 **必须串行改 `monitor.ts`**：两者都改类型区（`:156-176`）与 `readMonitorState` 的返回对象（`:386`）。G2 文档里的 `MonitorSnapshot(:488-495)` / `MonitorAutopilot(:155-166)` 锚点已陈旧，按实测重锚。
- 风险 R5：**G4 的"冻结"不可复现**（无日志、无快照留存、无逐 tick 心跳）⇒ 只能靠"帧自证 + 失败不静默"两条结构性修复；验收以 AC-016（跟随）与 AC-015（时刻前进）的合成夹具为准，不依赖复现原事故。
- 风险 R6：**会话替换后面板永久消失**（RQ-4 D6：`monitor.ts:825` 幂等早退 + 扩展工厂跨会话复用 + 重激活清 widget + runner invalidate）——症状与“冻结”不同（面板消失而非陈旧），但同属观测面不可信；AC-018 一并收口，并在 `autopilot-monitor.test.ts:761-765` 补反向用例（现状把“幂等不重启”当正确行为）。
- 风险 R7（G5/G6）：**改派发语义可能影响其它 key**——PM 侧收窄后可能漏派本应派的跨 key 任务。缓解：收窄**只加给 PM 自动派发**，PM 之外的写面保持全局（AC-019 反向用例②③），且读面对任意 key 全局只读（AC-024，看得见就不会瞎猜）；被跳过的候选写 `phase:"dispatch-alarm"/kind="out-of-scope"`（可见而非静默）。
- 风险 R8（G5/G6）：**`run.json` 与台账双源不一致**（历史任务无该文件 / 台账 done 而 run 说 running）。絯解：优先级 = `run.json` 终态 > 台账 > 无信息；冲突则告警且**不派发**；无 run 的历史任务**零回填**（行为与今日一致）。
- 风险 R9（G5/G6）：写面与另一 key 冲突（`mw_common.py`/`mw.py`/`worker-store.ts`/`pm-orchestrator.ts`；IN-3 期间又有孤儿 worker 写过 `packages/**`）。絯解：同文件一律串行（plan §1.2）；开工前 `git diff -- <path>` + `git status --porcelain` 复核（D-009 口径）。
- 未决 RQ-5：**已作废**（worker 被 IN-3 杀灭、无产出）；其取证需求由 PM 直执复盘取代（`evidence/incident-in3-queue-reenqueue-20261010.md` + 跨 key 归档 `_incidents/in3-queue-reenqueue-20261010/`）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- **timeline 事件机制 + 去重先例**（`autopilot/timeline.py`、`conductor._timeline_has_event`）——G2 提醒去重、G1 `l3-aborted` 留痕直接复用，勿新造事件总线。
- **gate frontmatter 允许集机制**（`autopilot/gates.py` 的 `FRONTMATTER_FIELDS` / `_LIST_FIELDS` / `_REQUIRED_FIELDS`）——G3 新增字段走既有可选字段通道，勿改解析器语义。
- **L3 provenance guard**（`conductor._l3_provenance_record`，`l3-verdict-provenance.json`）——"裁决来源可疑 ⇒ 机械降级"的现成先例；G1 的 `l3-aborted` 与之同族，可对齐记录形状。
- **散文不等于授权 的现成判据**（T-24 `mw_common._crosskey_prose_scan`，fail-closed）——G3 的"note 自由文本不当授权"可直接对齐其判据口径。
- **消费记录载体**（T-05 `consumed_at`/`consumed_seq` 复合键）——G3 若需"批准记录"指针，参考其"事实写进被引用文件"的做法。
- **PM hook / triggerTurn**（`mw-*` 既有）——G2 的 PM 侧推送通道。
- **分层 doctor 段**（T-13 `mw_common._doctor_gates` 的 I1–I8）——G2 的 `mw doctor` 可见面在此扩展。
- **面板 staleness 先例**（`monitor.ts:609` `staleAfterMs = max(30s, pollMs*5)` → `tickStale:635`；`formatDuration:651-658`）——G4 的"快照年龄 / 过期告警"复用同一机制与格式化。
- **fake timers 装配**（`autopilot-monitor.test.ts:230/483/605` + `vi.advanceTimersByTime(4000)`；`startMonitor(root, apply, { nowMs })` 可注入时钟）——AC-016 的"≤8s 跟随"可直接写成断言。

### 需规避坑点

- **P-007**（review 角色的唯一交付通道是最后一条消息；`stream closed` ⇒ 报告全丢）——G1 正是它的机器化收口：不得靠"提示词写短点"，必须有落盘/指纹。
- **P-009**（失败只记一行自由文本 = 无界空转；失败事件必须带机读分类）——G1 的分类、G2/G3 的留痕都按此口径。
- **P-014**（判据与表达措辞差：FAIL 只认一种字形 ⇒ 语料全漏）——G1 的三类判据必须正负语料双穷举。
- **P-016**（解除 skip 的用例可能是空洞的，必须非空洞对照）——AC-014 的硬要求。
- **P-019**（语义变更的下游卡必须当场认领）——G3 改 gate schema 语义，必须列全消费者。
- **P-023**（字段契约的验收夹具必须来自真代码路径；"唯一咽喉点"必须 grep 证明）——AC-009/AC-013 的硬要求。
- **P-025**（worker 回执可声称"已有机器证据"而证据不存在）——AC-014 的坐标要求。
- **P-017**（`npm run check` 会全仓 `--write`，多会话下破坏他人未提交改动）——本 key 与另一 key 并行，必须定向 lint。
- **P-021**（跨语言镜像的陈旧断言会留给下一个 key 引爆）——G3 改 `status-model.ts` 镜像，两侧都必须跑。
- **P-018**（给共享读取函数加"兜底合并"会覆盖更早 key 的冻结判据）——AC-013 的逐字节口径。
- **P-014 家族（判据与观测面差）**：G4 的"冻结"最初被归因到 `/mw restart` 与 `launcher-beat` 身份耦合，RQ-4 实测证伪（TS 侧 0 命中）⇒ 归因不得凭症状相似下结论，须有 grep 命中与 grep-0 两类证据。
- **P-009（失败必须机读分类）**：`monitor.ts:828-833` 的裸 catch 正是"失败只丢一帧、无痕"的形态；G4 的降级帧必须带失败时刻与摘要。
