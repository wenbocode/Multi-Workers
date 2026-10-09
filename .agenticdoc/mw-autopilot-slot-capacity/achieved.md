# Achieved: mw-autopilot-slot-capacity

- key: `mw-autopilot-slot-capacity` · 问题域：**autopilot slot 为何只有 2、并行度是否够用**
- 定位（用户裁定）：**A** —— 主交付 = 门命题重设计 + 三分处置 + 护栏 + 硬前置修复；次级 = (c2) idle 心跳；(d) 只做观测与判据
- 规模：31 AC / 49 VC / **23 张实现卡**（T-01..T-23）；22 张开出时收口，T-23 由 quality-gate 判定后补开
- 本文件用途：按 QG 报告 `evidence/quality-gate-report-20260926-194528.md` 补齐两处**文档欠债**（R1 归因表、R3 五路结论），并作为 verify 阶段的目标对齐依据
- `goal.md` 锚点时间戳：`2026-09-09T16:21:38.4069260+08:00`

---

## 1. 系统行为变化

| 面 | 落地内容 | 关键锚点 |
|---|---|---|
| 门 schema v2 | 可选字段 + `gate_schema: 2` + `_REQUIRED_FIELDS` 导入期锁 + fail-closed 解析 | `autopilot/gates.py`；`autopilot/config.py` |
| 门字段默认值 | 唯一咽喉点盖章（`expires_at`/`default_action`，`stalled` 另需 `reason_code`）+ 写入侧闭集护栏 | `conductor.py:2490`/`:2496`/`:2480`/`:2365` |
| 自动决策 | 6 条可证伪命题 + `off\|shadow\|live` + 落盘熔断 `auto-brake.md` + append-only `auto-decisions.jsonl` + 夜/键配额 + 撤销 | `conductor.py:4370`/`:4422`/`:4433`/`:4632`/`:5645` |
| case 2 延后复核 | `pending-review` 不计终态、收口前置、48h 升级给人、合法重开走 T-01 守卫 | `conductor.py:2751`/`:70`/`:3031`/`:6120` |
| 消费记录持久化 | 门文件 `consumed_at`/`consumed_seq` 优先 + timeline 只读回退 + 复合键去重 | `conductor.py:298`/`:318`/`:368`/`:410`；6 个写点 `:488`/`:501`/`:508`/`:2550`/`:2594`/`:3054` |
| 取证与对账 | `autopilot/evidence.py`（sidecar `gate-evidence/1`）+ `evidence-reconciliation` 屏障 | 新建模块；`conductor.py` 接线 |
| 呈现（三层） | 每门恰 13 行 + 唯一哨兵 + DRIFT + `auto=off\|shadow\|live` + `mw autopilot gates [--json]` | `monitor.ts`；`console.ts`；`mw.py:3645`/`:3776` |
| 归属语义统一 | `origin`/`owner_key` 唯一权威谓词（`_row_belongs_to` 委派），`reconcile_orphans` 盖 `origin` | `mw_common.py:1620-1666`；`conductor.py:2369-2372`/`:4335`；`worker-store.ts:11-95`；`monitor.ts:618/626-627` |
| 看门狗 | `[IDLE_KILL]` + in-flight 分类 + 30s bash 心跳（仅 `PI_WORKER_TASK` 生效） | `mw.py`（T-04） |
| 守卫包 | D1 正则 `\d+`（gate-10000）+ D2 reject 守卫 + D4 stage 单调性/重开拒绝 | `conductor.py:310`/`:383-428`/`:2437`/`:2441` |
| 工具白名单 | `_autopilot/**` 封堵（保留 `_autopilot/xkey/**` 豁免） | `xkey-gate-guard.ts`；`conductor.py:99-106` |
| 配置镜像 | `auto_gate_mode` 六处 TS 镜像 + parity 语料 53→55 + 计数锁刷新 | `status-model.ts:105/122/141-143/285/301/327` |
| 状态枚举锁（T-23） | `KEY_STATUSES` 跨语言保序锁 + `_DEP_SATISFIED` 内部一致性 | `test/suite/autopilot-status-parity.test.ts`（收口期新增） |

---

## 2. (QG R1) 并行度上限的**成因三态表**（逐 cap 落定）

> 判定枚举（spec AC-002）：**设计约束**（有出处）/ **历史默认**（存在但无依据）/ **无依据**（否定结论须附反证范围声明）。
> 下表锚点均为 **PM 亲自复核**（除标注"引自调研笔记"者）。

| # | 上限 | 当前值 | 三态判定 | 判据（file:line） | 可配置性 |
|---|---|---|---|---|---|
| 1 | **key 层并发**（同一时刻在飞的 key 数） | **2** | **历史默认** —— 有默认值、有文档化、有取值域，但**无任何设计文档/注释/blame 解释为何取 2** | 判定点 `conductor.py:329` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"]))`；默认值 `config.py:59`（`"max_parallel_keys": 2`）；取值域 `config.py:81`（`(2, None)` ⇒ **下限 2、无上限**，即"只能调高不能调低"）；声明表 `config.py:16`；文档 `README.md:225` | 可配（`config.json`）；**floor=2 不可低于 2** |
| 2 | **per-key 串行**（同 key 同 tick 至多 1 个在飞 worker） | 硬编码 | **设计约束** | `conductor.py:327` `if key in in_flight_keys: continue  # wait for the in-flight worker`；`in_flight_keys` 派生 `:291-295`（非终态 ∧ 归属本 key） | 不可配（无对应配置键） |
| 3 | **worker 层全局并发**（同时运行的 worker 进程数） | **无显式上限** | **无依据 = 不存在该约束**（否定结论，附反证范围） | 引自调研笔记 RQ-1：`evidence/research/spec-concurrency-anchors-20260926.md:162-171`（范围 A–E：`packages/multi-workers/*.py` + `autopilot/*.py` 全量、`launcher.py` 全域、TS 扩展面、conductor 每 tick 可派发点、`round_budget` 语义）；**PM 复核的独立证据**：`README.md` 配置表无任何 worker 并发键（键集止于 `worker_timeout_min`） | 不可配 |
| 3′ | **cap 的旁路**（xkey 提案通道） | `xkey_repair=true` 时每 tick 可派 **N(approved tickets)** 个 worker，**不受 `max_parallel_keys` 约束** | **设计约束（有意旁路）** | 引自 RQ-1：`conductor.py:2875-2922`（`_xkey_proposal_stage` 在 `in_flight_keys` 计算**之前**执行）、`:243-254`、`_xkey_proposal_one:3005-3048`、`_XKEY_PROPOSAL_MAX_ATTEMPTS:2872`；**默认关**（`config.py:58` `xkey_repair=false`） | 可配（默认关） |
| 4 | **serve / launcher 层** | 无并发上限概念 | **设计约束（结构使然）** | `mw.py:353-374` 单线程监督循环（顺序检查 stop 文件 → `launcher_proc.poll()` → `proxy_proc.poll()` → `_conductor_supervise_step()` → `time.sleep(1)`）；launcher 亦单线程 `while True: _poll_once(); sleep`（引自 RQ-1：`launcher.py:844-880`） | 仅 launcher `--max-workers`（opt-in，不进项目配置） |

**由此得到的结论（本 key 的主判断）**：用户观察到的"slot 只有 2"= **第 1 行**（key 层默认 2、floor 2）；"并行度不够"的**真主因不是 cap 太小**，而是 **key 停在 gate 上等人**（见 §3 的 (c1)）；而 (c) 与槽位无关。

---

## 3. (QG R3) 五路最终结论（逐条回应 (c1)(c2)(c3)(c3′)(d)）

| 路 | 问题 | 结论 | 支撑 AC | 落地/证据 |
|---|---|---|---|---|
| **(c1)** | 门阻塞（key 停在门等人 ⇒ 占着 slot 不干活） | **本 key 主交付**：门命题重设计（事实性 vs 政策性授权两分）+ 三分处置 + 自动决策（`off\|shadow\|live`）+ 护栏（配额/熔断/账本/撤销）+ case 2 延后复核 | AC-006, AC-015..AC-020, AC-024, AC-025, AC-027, AC-030 | T-07/T-08/T-13/T-19/T-20/T-21；`conductor.py:4632`（4 guard + 2 approve）、`:4370`、`:6120`；`evidence/runs/verify-20260926-190302-evidence-collection.md` |
| **(c2)** | idle 看门狗误杀（"看起来在跑、什么都没干"的反面：真在跑却被判死） | 修：`[IDLE_KILL]` 判据 + in-flight 分类 + 30s bash 心跳（仅 `PI_WORKER_TASK` 生效）；真挂死仍判死 | AC-005, AC-013 | T-04（5/5 + 3 反证）、T-12（`timeout:` 头接线）；证据 `msc-d7 :: idle_kills=24, margin 1-22s` |
| **(c3)** | 占槽判定与归因（谁在占 slot、孤儿行算谁的） | 修：`origin`/`owner_key` 唯一权威谓词 + `reconcile_orphans` 盖章 + 两侧委派 + 孤儿窗 90min 观测 | AC-012, AC-021 | T-12/T-16（等价性 30 对 `mismatches=0`）；`mw_common.py:1620-1666` |
| **(c3′)** | 是否放宽 key 层 cap（把 2 调大） | **不改**：cap 不是瓶颈（§2 第 1 行 + §3 (c1)）；且放开 per-key 并发**前置条件不满足**（写面纪律只存在于 11/248 份任务书的散文里，机器判定为零）⇒ 属政策性授权，须人给 | AC-009, AC-014, AC-021 | 不动作；`evidence/research/spec-capacity-constraints-20260926.md`（含"不改"项取值域/校验/首个失败模式）；RQ-1 反证范围 |
| **(d)** | worker 层串行化点（同 key 内派发是否被硬串行） | **只做观测与判据，不放开**：per-key 串行是**硬顺序**且有三重结构保证；PM 手工派发路径存在 6 个并发/重叠样本（最长重叠 89.2s） | AC-005, AC-008, AC-013 | T-12/T-16 观测面；RQ-5（`serialization_points=7 manual_overlap_max=6 autopilot_overlap_max=1`）；design D-018 |

**自动决策的边界（用户裁定的决策树）**：可自举 → 是否挡不可逆动作 → 挡则当场人审 / 不挡则延后批量复核。落地为 `RULES` 的 **4 guard**（stage-confirm / stage-close / goal-change / xkey-authorize，一律升级给人）+ **2 approve**（`stalled` 且反证为假的假阴、`budget-exhausted`）。

---

## 4. AC 逐条证据索引

不在此重复正文（避免与证据包漂移），按需 grep 两份机器生成的索引：

| 需求 | 索引文件 | 覆盖 |
|---|---|---|
| 实现卡 `[VERIFY]` 断言 + 原始输出（按 AC/VC 绑定） | `evidence/runs/verify-20260926-190302-evidence-collection.md` | 22 张卡；19 张含逐字 `[VERIFY]` 行 |
| 分析层 AC/VC（无实现卡绑定，证据在调研笔记） | `evidence/runs/verify-20260926-190335-analysis-evidence-index.md` | 9 AC + 9 VC 的候选源与首次提及行 |
| AC 充分性判定标准 | `evidence-requirement.md`（ac_fingerprint `b623c94027ae`） | 31 AC + 49 VC 逐条 |
| 基线（既有红 / 环境红 / 抖动） | `evidence/baseline/baseline-20260926.md` + `evidence/runs/run-*.txt` | 3 套件原始输出 |
| 独立质量门 | `evidence/quality-gate-report-20260926-194528.md` | 108 问（0 ❌ / 13 ⚠️ / 95 ✅） |

**AC 与五路的对应**：AC-001..AC-004（上限清单/成因/利用率/占槽）→ §2 与 (c3)；AC-005..AC-009（idle/(c1)/审核材料/(d)/方案集）→ §3；AC-010..AC-013（镜像/可观测/(观察性逃逸口）→ §1；AC-014/AC-015（前置清单/反作用）→ §3 (c3′)；AC-016..AC-031（实现面与护栏）→ §1 表 + §4 索引。

---

## 5. 未实现 / 显式接受项（QG 的 R4、R5 与环境项）

| 项 | 状态 | 理由与判据 |
|---|---|---|
| **R4** 写面机器可读判据未落地（AC-014 / VC-016 / Q-VC-016） | **用户显式接受范围** | 本 key 定位 A 的**设计选择 D-018「只做观测与判据，不放开 per-key 并发」**：前置清单、现状反证（11/248 散文、`write_scope`/`写面` 生产代码零命中）、缺位时的首个失败模式**已交付**；schema v2 已留 `write_scope` 载体、T-07 xkey P3 已有 `blast_radius ⊆ write_scope` 谓词。**派发面重叠拒绝属"放开"之后才需要的实现**，故本 key 不做 |
| **R5** 绕门散文授权的机器判定（AC-031 / VC-048） | **已实现（T-24，收口期 QG 后补开）** | 研究级判据与实测样本已在（`evidence/research/design-gate-propositions-20260926.md` §6.2 P4 的 FM 手写 decision 行实测 + G11 "只读扫描 + fail-closed 视为未授权"）；本 key 未实现扫描器、无测试、无卡绑定。QG 建议的补法：doctor gates 增只读扫描 `_autopilot/evidence/cross-key-repair-request-*.md` 的 `decision:` 行 ⇒ I 类 issue + fail-closed |
| **R7** `dist/` 未重建 | **待执行（被跨 key 依赖阻塞）** | `packages/multi-workers/dist/extensions/agent-team-loop.js` 仍是旧枚举（4 值 `KEY_STATUSES`，无 `pending-review`；缺 6 个新事件名与 `auto_gate_mode`）。重建命令（沿用前一个 key 的实证流程）：`python -X utf8 packages/multi-workers/mw.py build` → `cd packages/coding-agent && npm run build` → `python -X utf8 packages/multi-workers/mw.py build --install --no-dist`。**阻塞原因**：工作树混有另一个 key（`mw-vision-role`）的未提交源码，此刻重建会把它未提交的功能一并编入本 key 的产物 |
| **R6** 证据采于混合工作树（归属） | **已在基线显式声明** | `evidence/baseline/baseline-20260926.md` §4.1：与 `mw-vision-role` 在 `autopilot/dispatch.py`、`test_autopilot_dispatch.py`、`worker-store.ts`、两份 CHANGELOG 上文件重叠，物理不可剥离 |
| **T-14 跨 key 字节锁重冻** | **用户接受** | `_GOLDEN_REGRESSION_SHA256`、`_L0_GOLDEN_SHA256` 两处重冻**带署名注释**（驱动变更 = 本 key T-15 的 13→14 计数刷新 + `mw-vision-role` T-03/T-13 的 vision 桶与 L0 扩展） |
| 环境基线红 | **非本 key 引入** | 包级既有 2 条；TS `test/suite/` 5 文件 14 例（AGENTS.md 的 Windows 语义类）；`test_conductor_kill_respawn` 经三次复跑判定为**根部全量负载下的抖动**（详见基线 §1） |

---

## 6. 目标对齐（`goal.md`）

- `goal.md` 的项目目标 = "让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目"。
- 本 key 服务的是该目标的**前提条件**：`worker 层无上限`（§2 第 3/3′ 行）意味着并行能力**不缺**，缺的是 **PM Agent 无人值守时对门的处置能力** —— 门一停、key 占着 slot 等人，整个 team 的吞吐就塌到"看起来在跑、什么都没干"。
- 因此本 key 的交付把"PM 不在场"这一时段从**不可用**推进到**有界可用**（自动决策只做可复算的事实性判断 + 配额/熔断/账本/撤销 + 政策性授权一律升级给人 + 影子期先攒证据），并保留"永不回退 stage"这一不可逆面的人审闸门。
- 与项目级约束的一致性：不引入中心化调度器（改动全在 conductor 的 tick 内，无新进程/新服务）、不修改 pi 核心（TS 侧全部在 extension 内）、worker 进程级隔离不变。

---

## 遗留

（本 key 交付后的遗留项与明确去向；含原先的未闭合项。）

### 7. 未闭合项（交付前必须由用户裁定或执行）

1. **dist 重建**（依赖另一个 key 先提交其工作树改动）。
2. **跨 key 提交流程**：路径级暂存无法只包含本 key 的文件（4 个文件重叠）⇒ 需 hunk 级暂存或请对方先提交。
3. **本 key 的 execute 波提交**：22 张卡的改动 + T-23 尚未提交（按"波次提交"约定，收口时一个提交，波内可 `--amend`）。
