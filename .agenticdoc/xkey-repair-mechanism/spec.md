# Spec: xkey-repair-mechanism

> Key: xkey-repair-mechanism
> 创建时间: 2026-09-26
> 状态: draft
> deps: mw-l3-fail-marker-forms（消费其 L3 provenance / fail_line 穿线产物）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架……文件驱动的去中心化协调」与「任务调度器」——把跨 key 冻结面失效的处置从**人肉治理协议**变为**框架能力**：conductor 自动聚合已登记的跨 key 红、生成机器可读工单与修复提案、经人工追认 gate 后受限执行并闭合写回。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——协调仍通过文件系统（`_workers.parallel` / `_index.parallel` / 账本文件）+ 文件锁完成
  - GC-2: 工具白名单按任务类型——受限修复 worker 的写面/工具面必须显式收窄并在落盘前机械强制
  - GC-3: Worker 进程级隔离——修复 worker 是独立 pi 进程，崩溃不影响 conductor 与其它 worker
  - GC-4: 不修改 pi 核心——全部通过 `packages/multi-workers`（Python）与既有 Extension API 实现
  - GC-5: `goal.md` 为项目级目标锚点（本机制不得改动它）
- 冲突：无
- 预期收益：本 key 达成后对项目目标的具体贡献（可观察、可验证；done 时在 achieved.md 对照判定）
  - (1) 跨 key 红不再"无 owner 滞留"：从"两处各自登记、无人可修"变为"聚合为待处置队列 → 人工追认 → 机械受限闭合"（判定：AC-001/003/007）
  - (2) 治理动作可机械审计：授权范围精确到冻结常量块，越界即 fail-closed，证据包字段强制完备（判定：AC-005/006）
  - (3) 并行安全不被破坏：不扩写面、无登记红只升级不提案、解冻权只给人（判定：AC-002/004）
  - (4) FM 真实工单一单闭环、红数 1→0（判定：AC-009/010）

## §1 功能概述

### 1.1 目标

**问题背景**：FeatureMigrator 的 Stage 2 出现一处跨 key 红——发货 key `cli-run-state-and-events` 新增顶层命令组 `runs`（共 13 组），使先已 DONE 的 `cli-hitl-channel` 所持有的 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（`TOP_LEVEL_GROUPS` 冻结为 12 组）转红。两侧 L3 都**正确**判定"不该由自己修"并各自登记（`cross_key_test=… owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True` / K-1 遗留），结果是**同一处红被登记两次、写面图上无 owner**。处置靠人工写一份 XKEY 申请（`request_id / affected_keys / 候选处置 / 拟授权边界 / 追认入口 / decision:`）再手工最小修。

**根因（五层，逐层收敛）**：
1. **表象**：没有 key 的写面覆盖该测试文件。
2. **所有权模型**：框架的分解是**按 key×相位的文件分区**，而**制品图不是分区的**——产品面变更与验证面快照断言之间存在跨 key 耦合边。**分区无法覆盖非分区的耦合图**，耦合边两端都合理拒修。
3. **状态机**：检测（L3 全量扫描 + 交接登记）与授权（人的解冻能力）都在，缺的是**传导通道**；`owner` 指向终态 key，而框架闭包是硬态（AC 冻结，正确），"修复权"不随 key 关闭续存——状态机里没有"治理级修复"这条边。
4. **快照权威**：冻结快照是**对共享面的断言**，其真值取决于其它 key 的交付物，权威却被钉在某个已关闭 key 的文件里。于是**授权漂移与真回归在机制层面不可区分**（都表现为"那个测试红"）——经典的陈旧权威 / 快照失效。
5. **规划期盲区**：同阶段 key 被规划为独立并行单元，规划期不产出耦合边；耦合在实现后的 L3 才被发现，此时对方已 DONE，发现无处可去（A 写面按纪律关着、B 终态、无第三条通道）。

**第一性归纳**：写面纪律是并行安全的必要条件，但写面的分区不可能覆盖非分区的耦合图——**耦合边需要一条独立于写面的「治理通道」**。通道输入是耦合边（已登记的交接），输出是**机械受限**的最小改动（限界能收窄，正因为耦合边精确指名了那个断言）。**二阶根因**：信息局部记录、全局孤立——没有跨 key 红账本，检测到的红只能停在各自报告里。

**同族先例与复发证据**：这不是第一次。FM reflect 台账 **A-06**（`_autopilot/reflect/plan-writeface-gap.md`）是同一族的第一次——同一形状：`P5 的判据把"全量套件"纳进来，写面却没有覆盖"套件红了要改哪里"`（`:37`）、**`红没有 owner`**（`:38`），结论 `key 在原 plan 下结构性不可收敛（不是执行失败）`（`:22`）。A-06 走的是**另一份手写协议**——`gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`（110 行，含三条人工追认行 `decision: approved by user-via-pm-window` `:72/:86/:104`、精确到 4 条路径的白名单例外、每条 `old sha256 → new sha256` + `reason` + 禁止放宽断言）。即：**同一类治理动作已被人手搓了两次、用了两个不同的文件名形状**（refreeze-request / cross-key-repair-request），各自重新发明了同一套要素。A-06 留下的三条教训（`plan-writeface-gap.md:57-59`：白名单必须覆盖本阶段全部失败面；**红必须显式指派 owner，不得默认"下一阶段会修"**；跨阶段门槛判据必须写明"红且不在本阶段写面内怎么办"）至今**没有一条被机制化**——这就是第二次出现的直接原因。

**附带发现（取证质量）**：那份手写申请自身的取证不可核——逐字核对发现 `cross-key-repair-request-…:30` 的"§遗留第 96 行 <引文>"**非逐字转述且定位不成立**（该行实为另一条摘要），`:19` 的"定义见 :1 附近"实为 `:243-244`，`created_at 2026-09-25T02:20Z` 与内容/追认时间矛盾；"跨 key 修复轮"一词全库仅存在于该申请文件及其转引（无任何既有承诺，RQ-2 Q4）。**人写散文引文不可核 → 机制的工单必须机器生成且逐字锚定**（P-014 家族）。

**本 key 做什么**：在框架层实现该治理通道——跨 key 红账本（聚合+去重）→ 仅对已登记耦合边生成机器可读工单与修复提案 → 人工追认 gate（仅人可答）→ 受限修复 worker（写面精确到冻结常量块，diff 边界机械强制）→ 证据包 → 双 key 闭合写回。

**前置交付（R-1 已证实）**：现状 `cross_key|crosskey|handoff` 在 `packages/multi-workers/**/*.py` 命中 **0**（`evidence/research/spec-reusable-parts-20260926.md` §4/§7）——交接登记只是 L3 散文，**不存在机器解析点**；`(file, test_id)` 亦无拆分器、`[VERIFY]` 无消费侧。故治理通道的第一步是**交接登记的机器可读化**（写侧结构化字段 + 读侧对既有散文形状的兼容解析，双侧测试锁，P-005）；否则 AC-001 的账本无输入、AC-010 的 FM 重放无从触发。

### 1.2 技术栈 / 语言

Python 3.14（`packages/multi-workers`：conductor / mw_common / launcher），复用既有文件锁与 gate 机制；测试 pytest（本仓 `test.sh` 语义 + hermetic 模式）；不触碰 pi 核心。

### 1.3 核心用户场景

1. **场景 A（检测-无 owner）**：发货 key 的 L3 跑全量套件发现红并登记交接后，conductor 在后续 tick 把该红聚合进账本，识别出 owner 为终态 key，生成"待追认"工单；人不介入时它停留在队列中（幂等、不重复登记）。
2. **场景 B（追认-受限修复）**：人查看工单与提案（含精确边界与证据包），在 gate 上作答 approve；框架派受限 worker 落最小改动，机械校验 diff 边界，跑定向复跑与全量对照，证据包完备后闭合，并把两个 key 的登记标注闭合。
3. **场景 C（真回归-只升级）**：某红没有交接登记（或 owner 非终态），机制**不生成提案**，只生成升级记录，交回人工/PM 判断——防止把真 bug 用更新快照的方式盖住。
4. **场景 D（拒绝/无响应）**：人 reject 或长期不答，工单进入明确的拒绝/超时状态（有去向、有预算），不空转、不静默丢弃。

### 1.4 范围说明（不做什么）

- **不做 T3（无 gate 全自动改冻结面）**——冻结的语义就是"只有人能解冻"，自动解冻使守卫失效。
- **不做规划期的耦合边静态分析**（不在 plan 阶段预测"A 加命令组会红 B 的冻结表"）——本 key 只做运行期检测 + 治理通道。A-06 的三条教训中 #1/#3（"白名单必须覆盖本阶段全部失败面""跨阶段门槛判据必须写明红且不在写面内怎么办"）属**规划期**前置，留待后续可能 key；#2（**红必须显式指派 owner**）正是本 key 的运行期核心。
- **不改写面模型本身**（不把 B 的文件划给 A、不扩 A 的写面）。
- **不自动修真回归**——无登记红只升级。
- **不做跨项目共享账本**——每项目独立，保持文件驱动去中心化（GC-1）。

## §2 业务约束

### 2.1 平台 / 环境

Windows 开发机（PowerShell 陷阱见 §5）；常驻于 `mw serve` 的 conductor tick 内；账本/工单/gate payload 一律 Python 原子写（禁 PS 文本命令，P-001/P-003）。

### 2.2 性能指标

conductor 单 tick 内聚合扫描为 **O(新增 verdict 数)** 的增量读取（不重复全量解析历史 verdict）；账本写入幂等，重复扫描不产生新行；对既有 conductor tick 周期的扰动可忽略（以既有 tick 测试不超时为准）。

### 2.3 安全约束

- **解冻权只给人**：`xkey-authorize` gate 的作答仅经 TUI 命令通道生效；PM/agent 代答必须被可观测地拒绝（状态不前进）。**实现面（RQ-D4 定案）**：现存 `answered_by` 只是自报的 `hostname:pid`（`gate-writer.ts:147` / `ui-bridge.ts:171-172`），人与 agent 同 pid 同权限，**不存在密码学判别**；`gates.py:13-15` 更明文"手工改文件也是合法作答"。因此该判据由三件组合实现：(i) 入口收窄（worker 模式不注册 `/autopilot`；`cmdGate` 加 `ctx.hasUI` 门，挡 print/RPC/派生的 `pi -p`）；(ii) **新建件**——仿 `shared/protected-config.ts:247-269` 的 `tool_call` 硬拦截，禁止 agent 工具层（`write`/`edit`/`bash`）写 gate 目录（这是唯一能产生"可观测拒绝"的落点）；(iii) 审计披露（作答来源入证据包）。**显式否决 nonce 挑战-响应**（同权限 agent 可读盘上的 nonce，零判别力）。残余面如实声明：绕开工具层的同权限进程仍可直写——工具层是 agent 的唯一通道。
- **无授权零写操作**：工单未获追认前，被涉及文件字节不变（可机械校验）。
- **边界机械强制**：修复 diff 只允许触碰工单声明的冻结常量块所在行集合；越界即作废（fail-closed），无人工例外路径。
- **不提案无登记红**：无交接登记或 owner 不可解析到终态 key → 只升级。

### 2.4 集成依赖

| 依赖 | 用途（落点/RQ-3 实测锚点） |
|---|---|
| L3 判定链 provenance（`l3-verdict-provenance.json`，`conductor.py:1267`，字段 `:1293-1305`） | **红来源唯一现成机读入口**：可得 `fail_line` + `deciding_source` + `round/task_key`；**不含 `(file, test_id)` 与交接登记** → 自建最小解析器 + 结构化登记（AC-011） |
| gate 协议（`autopilot/gates.py`：12 字段 frontmatter `:65/:83`、锁内原子写 `:198`、seq 重扫 `:243`；消费 `conductor.py:255/274`） | `xkey-authorize` gate 抬起/作答/消费；**承载约束**：`question` 单行、`context_refs` 单行列表（`gates.py:209-238`）→ 复合工单必须是**独立文件**，gate 仅指路；新 kind 须**两侧闭集镜像**（`gates.py:52` ↔ `autopilot/status-model.ts:467` + TS 解析放行，否则面板枚举抛 `GateFormatError`） |
| 授权/闭环范式（`autopilot/closure.py` 三条件授权 `:105/123/151/159`；自持预算 reprompt `conductor.py:1580-1626`；闭合事务 `_done_transaction:1715`；机械封口 `:1415`） | AC-005 边界强制沿用同族三条件（授权快照 ∧ 文件 sha 未漂移 ∧ 行集合 ⊆ 声明集）；AC-006 "缺一不闭合"复用机械封口判据范式；证据包组装器**新建**（碎片可复用） |
| 受限修复 worker（`dispatch.py` + `worker-mode.ts` 读面/工具白名单/REGISTRY parity + `launcher._stripped_env`） | GC-2/GC-3 现成；但 **diff 行集合边界无先例**（`shared/protected-config.ts` 是路径集合拦截，需改造），AC-005 的行集合校验**需新建** |
| 文件锁与原子写原语（`mw_common.acquire_lock:1480`；append-only+去重+原子写范式 `conductor.py:1359`） | 跨 key 红账本（AC-001 幂等、Q9 并发） |
| per-project 配置面（`autopilot/config.py:38/51/75` + TS 镜像 `status-model.ts:82/112/149/199`） | AC-008 开关 `xkey_repair`（默认 false，落 config.json 不落 env，P-015） |

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-26T03:55:43Z，编号永不回收

> 修订记录：AC-004/005/010 于 2026-09-26 spec 期调研回读后修订（均带 `[REVISED @ 2026-09-26]` 标注，编号未动）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 conductor 已消费至少一个含跨 key 交接登记的 L3 判定的前提下，跨 key 红账本对每处 `(file, test)` 红生成**恰好 1 行**记录，字段含 `source_key / owner_key / test_id / reason / status`；重复扫描后行数不变（幂等） |
| AC-002 | 在存在全量套件红但**无**交接登记（或 owner 无法解析到终态 key）的前提下，机制生成升级记录且**生成 0 个修复提案**、0 个写面授权 |
| AC-003 | 在红的 owner 为终态 key 且交接登记齐全的前提下，机制生成机器可读工单，字段含 `request_id / affected_keys / 拟授权边界(精确到 file + 冻结常量块) / 追认入口`；工单生成后至追认前，被涉及文件字节数不变 |
| AC-004 | 在工单待追认状态下，`xkey-authorize` gate 的作答仅经 TUI 命令通道生效：(i) worker 模式窗口（`PI_WORKER_TASK` 存在）不注册该命令，无 UI 进程（print/RPC/派生的 `pi -p`）作答被拒；(ii) agent 工具层（`write`/`edit`/`bash`）对 gate 目录的任何写入被拦截（可观测：拦截记录 + gate 文件字节不变）；(iii) 每次成功作答记录来源（窗口 claimId / 模式 / 命令通道）并在闭合证据中显式披露"判别手段 = 命令通道 + 模式门，非密码学证明"。[REVISED @ 2026-09-26] |
| AC-005 | 在工单获追认后，修复触碰的行集合是工单声明冻结常量块行集合的子集；构造一处越界改动（含断言主体或其它文件）时，机制判定边界违规、工单不得进入 applied→closed，且被涉及文件最终 sha256 等于工单创建时的 sha256（零残留；前置校验或快照回滚二路径取一，设计阶段定死）[REVISED @ 2026-09-26] |
| AC-006 | 闭合证据包包含 `old→new sha256 / reason / 是否放宽断言=否 / 定向复跑命令与原始 stdout / 全量套件红数 before→after` 五项；缺任一项时工单不得置为已闭合 |
| AC-007 | 闭合后，账本该行状态为 closed，且两个受影响 key 的登记（source 的交接登记 + owner 的遗留登记）均被标注闭合；对同一工单重复闭合为幂等（无新增行、无重复标注） |
| AC-008 | 机制默认关闭；per-project 配置开启后生效；关闭时对既有 conductor 流程零行为变化（既有相关测试全绿） |
| AC-009 | 在合成的 fixture 项目（两个 key + 一处冻结常量 + 一处由发货 key 合法变更引发的红）上端到端重放：账本→工单→gate→受限修复→证据包→闭合全链完成后，fixture 的冻结断言由红转绿，全量红数 1→0 |
| AC-010 | 在 FeatureMigrator 真实工单（XKEY-2026-09-25-01）上重放：**前态由逐字语料构造的 fixture 重建**（用户 2026-09-26 裁定选路 b；pre-fix 隔离副本仅作后备）——fixture 复刻 `cli_groups=13` vs 冻结 12 的真实形状与 FM 的**散文登记原文**（含 `[VERIFY] REPAIR-R1-F1: cross_key_test=… owner=… handoff=registered not_fixed_by_this_key=True` 与 K-1 类变体）；人工追认后 `pytest tests/test_hitl_channel.py -q` 由 1 failed 转为全绿、全量套件红数 1→0，且证据包含 old/new sha256 与"是否放宽断言=否" [REVISED @ 2026-09-26] |
| AC-011 | 在 L3 判定落盘跨 key 交接登记时，登记以机器字段形式写入（至少含 `file / test_id / owner_key / handoff / 冻结块标识`）；对既有散文形登记（FM XKEY-2026-09-25-01 语料）提供兼容解析，解析结果与人工判读逐字段一致（语料驱动测试；写侧 + 读侧双侧测试锁，P-005） |

## §4 风险与未决项

- **R-1（已证实，范围已纳入）**：交接登记是**散文**而非机器字段——实测 `cross_key|crosskey|handoff` 在 `packages/multi-workers/**/*.py` 命中 **0**；L3 prompt 只要求 `## Quality Gate Report` + `## Achieved` 两节，机器只解析节存在性与 `FAIL` 词形；provenance 字段闭合且值域只有 `meets|below`（RQ-1 Q1 / RQ-3 §4）。故"交接登记机器可读化 + 对既有散文形的兼容解析"是本 key 的**前置交付**（AC-011），不再是待确认风险；写侧（L3 输出形状）+ 读侧（conductor 解析）双侧测试锁（P-005）。
- **R-2**：启发式定位"失败行 → 冻结常量块"可能漂。缓解：边界机械强制兜底；定位不确定时降级为**仅提案不执行**。
- **R-3（已证实：gate 无超时机制）**：现存 gate 协议无 TTL/提醒字段（`gate.*expire|remind` 0 命中，RQ-1 Q2），时间维度靠**回路预算 + `advance_stall_ticks` + `mark_stalled`**（RQ-3 §3）。故工单"超时"须落在预算/streak 上，状态可见、不丢单。
- **R-4**：AC-010 会写入外部项目树（FeatureMigrator）。未获人工追认前零写；追认是 AC 的前置条件。
- **R-5（新，来自 RQ-1 Q3/Q4）**：两个能力缺口已在 spec 边界外被证实——(a) **框架不跑全量套件、不做"跨 key vs 自身回归"分类**（`autopilot/**` 无 pytest 调用，L3 证据记录制不重跑）→ "红"的唯一来源是 L3 agent 的报告/判定源文本，故检测依赖 AC-011 的结构化改造；(b) **写面无按路径强制**（`read_scope/deny_globs` 只拦 read 系工具，`write/edit/bash` 直接放行，RQ-1 Q3）→ AC-005 的"零残留"只能靠前置校验或快照回滚实现，设计阶段必须定死其中一条；证据包的"定向复跑原始 stdout"也需机制自带执行路径（框架现无此能力）。
- **R-6（AC-010 的前态已消失）**：FM 那处红已被人手修复（RQ-2 Q6：静态比对 13==13；申请文件 `:57` 已有 `decision: approved (R1)`）。→ AC-010 的重放必须基于**重建前态**（pre-fix 隔离副本或逐字语料 fixture），且**不得污染 FM 工作树**。
- **待确认（batch 2，均为 [AI 推荐]，见 key-decision.md）**：reject 后去向（留账本可重开）；工单状态机与去重键 `(file, test_id, 冻结块指纹)`；多窗口并发下的账本读改写语义（文件锁 + conductor 单点推进）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

对着 `_arch_snapshot.md` §2 资产清单点名：

| 资产 | 位置（RQ-3 实测锚点） | 本 key 用法（直接复用 / 需改造 / 新建） |
|---|---|---|
| 文件锁与原子写原语 | `mw_common.acquire_lock:1480`；`conductor.py:1359`（append-only+去重+原子写） | 账本（AC-001 幂等、Q9 并发）——**直接复用** |
| gate 协议整体 | `autopilot/gates.py:52/65/83/116/198/243/480`、`conductor.py:255/274/2064`、`gate-writer.ts:139` | `xkey-authorize` 抬起/作答/消费——**直接复用**；kind 扩展需两侧闭集镜像（`gates.py:52` ↔ `status-model.ts:467/595`）；**仅人可答判别 + 超时（无 TTL）需新建** |
| 授权/闭环范式 | `autopilot/closure.py:105/123/151/159`（三条件授权）、`conductor.py:1580-1626`（自持预算 reprompt）、`:1715`（闭合事务）、`:1415`（机械封口） | AC-005 三条件同族、Q7 reject 去向预算、AC-006 "缺一不闭合"——**新建（范式复用）**；**证据包组装器不存在，需新建** |
| provenance / fail_line 穿线 | `conductor.py:1164/1215/1233/1267`（sidecar 字段 `:1293-1305`） | 红来源唯一现成机读入口（fail_line + deciding_source + round/task_key）——**直接复用**；**`(file, test_id)` 与交接登记不可得 → 新建解析器** |
| 派发 + 读面/工具白名单 + 凭证隔离 | `dispatch.py:70-107`、`worker-mode.ts:52-83/763-772`、`launcher._stripped_env` | 受限修复 worker（GC-2/GC-3）——**直接复用**；**行集合写面边界无先例（`protected-config.ts` 是路径集合）→ 新建** |
| per-project 配置面 | `config.py:38/51/75/129-150`、`status-model.ts:82/112/149/199` | AC-008 开关 `xkey_repair_enabled`（默认 false）——**直接复用**（不落 env，P-015） |
| 跨 key 风险升级先例 | `mw-crosskey-risk-escalation`（`pm-orchestrator.ts:564-578`、`ui-bridge.ts:154`） | **设计原则参照**（升级带 owner + 幂等 + 低风险抑制）；实测代码复用面 ≈0——它解决的是"派到别键的 worker 的 PM 通知归属"，与跨 key 红修复权治理不是同一问题（RQ-3 §2） |
| L3 判定链 / 全量套件 | `conductor.py:1113-1124`（L3 prompt 只要求两节、不重跑）、`:1076/:1155-1185`（仅解析 FAIL 词形） | **不成立**：框架不跑套件、不做"跨 key vs 自身回归"分类（RQ-1 Q4）——红检测须由 AC-011 的结构化改造补上 |
| hermetic serve 测试模式（fake Popen + TEST_* 凭证） | `test_serve_doctor.py` | 机制测试不依赖真机——**直接复用** |
| watchdog / 树杀 / 孤儿 reconcile | `mw_common` + `worker-mode.ts` | 修复 worker 生命周期——**直接复用** |

### 需规避坑点

对着 `_pitfalls.md` 点名（P-001…P-015）：

- **P-001**（PS 文本管道损坏 UTF-8）：账本/工单/gate payload 一律 Python 原子写，不用 PowerShell 文本命令。
- **P-003**（`open(p,"w")` 先截断）：账本与工单写入必须原子（临时文件 + 替换）。
- **P-005**（跨语言契约"只有读者没有写者"）：若交接登记机器可读化，须有"写侧（L3 输出）+ 读侧（conductor 解析）"双侧测试。
- **P-009**（失败只记一行自由文本、无预算无门禁 = 无界空转）：工单状态机必须有超时/预算与明确去向。
- **P-011**（claim 身份双写分叉）：账本判活不得依赖 pm-state 派生身份。
- **P-012**（子进程失败原文是唯一词表载体）：修复 worker 失败必须留原始 stderr 到盘。
- **P-013**（转录器在下一 `## ` 行截断）：工单/gate payload 若用 markdown 承载，控制形状避免截断。
- **P-014**（判据与表达措辞差）：红/交接登记的形状识别要语料驱动、多字形覆盖。
- **P-015**（serve 的 env 参数不落盘）：机制开关落 config.json（落盘）而非 env，避免重启丢配置。
