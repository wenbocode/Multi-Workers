# KDR: xkey-repair-mechanism

## R（需求）

- 技术栈: Python 3.14（`packages/multi-workers`：conductor / mw_common / launcher）+ pytest；不触碰 pi 核心。
- 边界: 只做**运行期**跨 key 红的治理通道（账本 → 工单 → 人工追认 → 受限修复 → 证据包 → 闭合写回）；不做规划期耦合边预测、不改写面模型、不做无 gate 全自动、不修真回归。
- 关键约束: 解冻权只给人（gate 仅人可答，PM 仅能起草）；无授权零写操作；修复 diff 边界机械强制（精确到冻结常量块行集合，越界 fail-closed）；无交接登记的红只升级不提案；开关落 config.json（不落 env）；协调保持文件驱动（GC-1）。

### 澄清记录（用户裁定 2026-09-26）

| 编号 | 问题 | 裁定 |
|---|---|---|
| Q1 | 自动化档位 | **T2**：检测 + 提案 + 追认后**受限执行**（gate approve → 框架派受限 worker 落盘 + 机械强制边界 + 验证包 + 闭合自动写回）。T3（无 gate 全自动）明确排除。 |
| Q2 | 触发来源与提案前提 | 聚合已登记的跨 key 红为**硬前提**：仅 `handoff=registered` + owner 可解析到终态 key 才可自动提案；无登记红（可能是真回归）**只升级不提案**。 |
| Q3 | 追认 gate 答者 | **仅人可答**；PM 窗口只能起草，代答必须被可观测地拒绝（默认关，显式授权记录才开）。 |
| Q4 | 生效面 / MVP 验收 | per-project **config 开关**（默认关），FM opt-in 试点；验收 = FM 真实工单 XKEY-2026-09-25-01 端到端重放 + 本仓合成 fixture 用例。 |
| Q5 | 冻结块边界定位 | **启发式为主**（provenance 的 fail file:line → 同文件最近冻结常量块）+ **diff 边界机械强制兜底**；定位不确定 → 降级为仅提案不执行。 |
| Q6 | 问题背景与根因 | 用户要求"洞察地说明"——已落 spec §1.1 五层根因（表象 / 所有权模型 / 状态机 / 快照权威 / 规划期盲区）+ 第一性归纳（写面分区 vs 非分区耦合图 → 需独立治理通道）+ 二阶根因（聚合缺失）。 |

### 待确认（batch 2，[AI 推荐]，用户未逐条裁定，按推荐写入 spec 供 Step 5 复核）

| 编号 | 问题 | [AI 推荐] |
|---|---|---|
| Q7 | reject 后去向 | reject → 工单转 `rejected` 且**留账本**（不静默丢弃）；同 (file,test) 后续再次被登记且内容有变 → 允许重开（新 request_id）；不变则保持 rejected 不重复提案 |
| Q8 | 工单状态机与去重键 | 去重键 = `(file, test_id, 冻结块指纹)`；状态机 `detected → ticketed → pending-auth → approved → applied → verified → closed`，旁支 `rejected / escalated / stale`；超时沿用 stalled-gate 家族 |
| Q9 | 多窗口并发 | 账本读改写走既有文件锁（O_CREAT|O_EXCL）；同一工单的推进只在 conductor 单点发生（worker 只落修复，不改状态） |
| Q10 | AC-010 重建前态选路 | **用户裁定 2026-09-26：选 (b)**——由逐字语料构造 fixture（可控可重复，与"语料要能逐字核"的教训一致）；(a) pre-fix 隔离副本作后备 |

### 证据驱动的范围修正（spec 期调研回读，2026-09-26）

| 来源 | 事实 | 对 spec 的修正 |
|---|---|---|
| RQ-3 §4/§7 + RQ-1 Q1 | `cross_key\|crosskey\|handoff` 在 `packages/multi-workers/**/*.py` 命中 **0**；L3 prompt 只要求 `## Quality Gate Report` + `## Achieved` 两节；provenance 值域只有 `meets\|below` | R-1 从"待确认风险"→ **已证实**，成为**前置交付**：新增 **AC-011**（交接登记机器可读化 + 散文兼容解析，双侧测试锁） |
| RQ-1 Q3 | `read_scope/deny_globs` 只拦 read 系工具，`write/edit/bash` 直接放行；**无按路径写面强制** | **AC-005 重写**为可达判据：越界时工单不得 applied→closed 且被涉及文件 sha256 回到工单创建时（零残留）——前置校验或快照回滚二路径取一，设计阶段定死；新增 **R-5** |
| RQ-1 Q4 | 框架**不跑全量套件**、不做"跨 key vs 自身回归"分类（L3 证据记录制不重跑） | §5 记忆表该行由"直接复用"改正为"**不成立**"；R-5 记录"红检测须由 AC-011 补上" |
| RQ-1 Q2 + RQ-3 §3 | gate 无 TTL/提醒字段；`answered_by` 仅 claimId，人与 agent 协议上不可区分 | R-3 改为"时间维度靠回路预算 + `advance_stall_ticks` + `mark_stalled`"；§2.3 明写"仅人可答判别是新建件" |
| RQ-3 §2 | `mw-crosskey-risk-escalation` 是**不同问题**（PM 通知归属），代码复用面 ≈0 | §2.4/§5 该行降级为"**设计原则参照**" |
| RQ-3 §1/§5/§6 | 三条件授权/自持预算/闭合事务/机械封口可复用；**证据包组装器不存在**；行集合边界无先例；新 kind 须两侧闭集镜像 | §2.4/§5 复用表换为带 file:line 锚点的"直接复用/需改造/新建"三态 |
| RQ-2 Q1 | A-06（同族第一次）= `reflect/plan-writeface-gap.md`，经 **`refreeze-request-20260925-guarded-closeout.md`** 三条人工追认行（`:72/:86/:104`）闭合；A-06 自己就写着 `红没有 owner`（`:38`）+ 三条教训（`:57-59`）至今未机制化 | §1.1 新增"**同族先例与复发证据**"段：**同一治理动作被人手搓了两次、两个文件名形状**（refreeze / cross-key-repair），各自重发明同一套要素 |
| RQ-2 Q2 | 手写申请自身取证不可核：`:30` 引文**非逐字且行号不成立**、`:19` 定位错、`created_at` 与追认时间矛盾 | §1.1 新增"**附带发现（取证质量）**"：工单必须**机器生成 + 逐字锚定**（P-014 家族） |
| RQ-2 Q4 | "跨 key 修复轮"**无任何既有承诺**（全库仅存在于该申请文件与其转引）——B 侧 L3 的引用是希望式措辞 | §1.1 根因第 3/5 层证据补强（确认没现成通道） |
| RQ-2 Q6 | FM 那处红**已被人手修复**（静态 13==13；申请文件 `:57` 已有 `decision: approved (R1)`） | **AC-010 修正**：重放须先重建前态（pre-fix 隔离副本或逐字语料 fixture）；新增 **R-6**（不得污染 FM 工作树） |
| RQ-2 Q1 + A-06 教训 | A-06 三条教训中 #1/#3 属规划期前置（白名单覆盖全部失败面 / 跨阶段门槛写明去向） | §1.4 明写：规划期前置列后续可能 key；#2（红必须显式指派 owner）正是本 key 运行期核心 |

复用比例实测（RQ-3）：直接复用 ≈35–40% / 需改造 ≈40% / 需新建 ≈20–25%（新建集中在治理语义本身：账本、仅人可答、行集合边界、工单/证据包形状、交接登记解析）。

## A（架构）← system-design 追加

- D001 交接登记承载: 选 写侧一行机器行 + 读侧解析并入 provenance sidecar，否 新读面/独立 sidecar（写的东西必须落在读得到的面上；KV 行现仅在 `evidence/runs/**` 而 conductor 不读该目录）
- D002 账本载体: 选 单一 project-level JSON sidecar + 锁内 RMW，否 markdown 表（P-013 截断）/ 一对象一文件（机器真值须可靠、去重 O(1)）
- D003 工单载体: 选 独立文件（30 字段，`request_id` 由 conductor mint），否 塞进 gate payload（`question`/`context_refs` 单行限制）
- D004 落点: 选 `_autopilot/xkey/`，否 受影响 key 的 `evidence/`（DONE key 不可写、跨 key 无单 owner）
- D005 应用路径: 选 (b) worker 产提案 + conductor 前置校验后应用，否 (a) worker 直写 + 回滚（写面零路径强制、仓内无回滚原语；FM 上 implementation-gate 根本不触发）
- D006 冻结块定位: 选 混合（机器 AST + 工单声明 + 应用时字节复核），否 纯启发式（10 变体 5 类不可解）/ 纯人工声明（人写不出精确行范围）
- D007 验证执行: 选 conductor 直接 subprocess，否 worker（全量套件 630.51s 撞 10min idle 看门狗）
- D008 仅人可答: 选 入口收窄 + `tool_call` 写拦截 + 审计披露，否 nonce（零判别力）/ 纯审计（不拒绝任何东西）
- D009 kind 扩展: 选 两侧闭集镜像 + conductor 与 kind 同版本，否 只改一侧（旧 Python conductor 每 tick skip）
- D010 挂载与顺序: 选 step F 消费 xkey + `:214/:216` 之间聚合 + `_gate_open` 扩 request_id，否 沿用现有 gate 去重（6684 条/12h 洪泛）
- D011 锚定口径: 选 字节 sha，否 行号（混合换行使行号漂移：Python `:220` vs PowerShell `:209`）
- D012 哈希口径: 选 字节精确 sha + `sha256_eol_normalized` 副字段，否 只归一化（需区分跨工具漂移与真实改动）

## I（实施）← PM 执行中追加
