# RQ14 设计取证：H01～H12 的现有 gate 效果、四选项消费、授权/预算/版本与 H12 隔离恢复

- Key: mw-dp-consolidation；任务 dpc-rq14-design-autopilot；角色 research（只读＋唯一证据）
- 时间基准：2026-10-26；代码基线 = 工作区当前 HEAD 无改动读取
- 性质：静态源码/文档取证 + 候选设计。**不是**设计批准、运行验证、AC/QG/签收结论。

## 结论

1. 现运行只有 **6 种 gate kind**（`stage-confirm`/`stage-close`/`stalled`/`budget-exhausted`/`goal-change`/`xkey-authorize`，gates.py:82）和 **3 种 status**（pending/approved/rejected，gates.py:91）。H01～H12 在代码里**没有一对一入口**：H01→stage-confirm、H02→stage-close、H03/H04→stalled/budget-exhausted、H05→pending-review（gate 作复核把手）、H06→goal-change、H07→xkey-authorize、H08→contract-freeze＋`authorizes:["contract-change"]`、H09/H10→roadmap-writer/xkey-proposal 的 2 次上限、H11/H12 **没有恢复通道**（只有人工改文件）。四选项（approve/steer/need_fix/reject）**无法用现有 status 表达**——需一条与 `authorizes`/`blocker_class` 同形的扩展字段（不破 gate 40 名冻结序），否则 steer/need_fix 必然被折叠成 approve/reject。
2. 现有"消费"是**按对象/副作用**分治而非统一 note 消费：stage-confirm approved→`running`、stage-close approved→`closed`+开下一 stage gate、stage-close rejected→`halted`、stalled approved→`running`（并授 1 轮 credit）、stalled rejected→`closed-legacy`（全仓唯一写入者）、xkey approved/rejected→ticket status、goal-change **任何答复都刷新 baseline**。后两条与 H06/H12 目标直接冲突。
3. 判据事实面已相当强：stalled/stage-close 的关键事实**从磁盘重算**（conductor.py:7093/7124/7171/7269），不是读回 gate 自己写的 v2 字段；`blocker_class` 缺省折叠为 `judgment`（7365），自动 approve 只对显式 `paperwork` 放行（7027，`BLOCKER_CLASS_KINDS={"stalled"}` 6602）。这意味着 H01～H12 的目标规则大部分可**复用在既有重算谓词上**，不需要新判据体系。
4. 硬门/幂等/不可用三件已有可复用机制：`_mark_gate_consumed`（872，写 `consumed_at`，重复调用零写入）＋`_consumed_gate_ids`（780，按 `(id, created_at)` 防 gate id 归档复用误判）＋gates 锁（`acquire_conductor_lock`，30s 陈旧接管）；队列不可读 `GateQueueUnreadable`（gates.py:230/373）在 tick 记 `config` 并返回 `error`，不折叠成"0 pending"（conductor.py:3836）。
5. **H12 现状不等于"活项目已熔断/死锁"**：`auto-brake.md` 只让 `auto_decide_gates` 早退（conductor.py:8480），`tick`/`orchestrate` 继续运行、人工 gate 仍被消费。因此静态事实**不能**推断熔断或死锁。恢复通道推荐"零新能力的隔离面"：恢复 gate 的 kind 在 `AUTO_RULE_BY_KIND` 中**没有规则**（8467 的 `rule is None → continue`），自动链因此**结构上无法**自批；brake 的清除只能由同一受控 CLI 在"原因消除证据 + 预授权 + 硬检查"三项成立后执行，且恢复记录追加而非删文件。
6. 两个"具体条件复核与行动消费"方案：**(S1) 复用 gate 文件 + `consumed_at` 单一记录**（推荐）vs **(S2) 独立 note/审批 sidecar + 二次消费表**。S1 优点是与现有幂等/锁/归档语义一致、无新持久面；缺点是 note 与模型理由分离需借 `constraints`/`evidence_refs` 现有 JSON 字段或 evidence sidecar，且 `expires_at` 之类字段无法表达"冻结于送审时刻"。S2 优点是绑定紧、可冻结，缺点是新增第二套账本（与 SPEC §5"不另造第二套决策账本"张力大）。
7. **实际预算/预授权值仍未设置**：代码里只有自动决策配额（`AUTO_NIGHT_CAP=6`/`AUTO_KEY_CAP=2`/`AUTO_BURST_60S=17`/`AUTO_BURST_1H=100`/`AUTO_COOLDOWN_SEC=30`，6610-6615）与 shadow 门槛（5 夜/20 次，6618）；**硬预算没有对应字段或计量实现**，软轮 credit 是"每个已批准 stalled gate 对每个封顶 loop 各 1 轮"（4124），由 dispatch 行单调派生而不可重置。本 RQ 不产生任何授权或数值。

## 证据

### E0 完整读取范围（区分已核/未核）

**全文读**：`.agenticdoc/mw-dp-consolidation/spec.md`（201 行，含 §1.6 H 表与 AC-001～053）；`evidence/graduation-pm-review-20261025.md`（毕业考勘误）；`evidence/gate-four-option-confirmation.md`；`evidence/h12-breaker-recovery-confirmation.md`；`packages/multi-workers/autopilot/gates.py`（859 行，全文）；`packages/multi-workers/autopilot/contract_guard.py`（449 行，全文）。

**分段读（conductor.py，共 8728 行）已核区段**：1–160（头部/常量/锁语义）、560–1010（`open_goal_change_gate`/`orchestrate`/`_consumed_gate_ids`/`_rewrite_gate_consumed`/`_mark_gate_consumed`）、1060–1400（stage gate 创建、`_stage_activation`、`_roadmap_writer_*`、`_stage_closure`）、3440–3760（提醒、`_freeze_contract_first_sight`、`tick`）、3760–4140（`_create_gate`/`_stamp_gate_defaults`/`_gate_open`/`_budget_*`/`_resume_credits`）、4140–4430（`_apply_stalled_approvals`/`_apply_stalled_rejections`/`_review_deadline`/`review_batch`）、4594–4834（`reattest_gate`/`_apply_reattests`/`defer_key_to_review`）、5120–5300（`_xkey_ensure_gate`/`_consume_xkey_gate`）、6348–6478（`_stall_blocker_class`/`mark_stalled`）、6540–6622（`REASON_CODES`/配额/断路器常量）、6622–7212（提案谓词/RULES/`rule_falsifiable`/`auto_decision_for_rule`/`recompute_*`）、7212–7920（`gate_facts`/`_stage_close_facts`/`blocker_class_of`/evidence sidecar/ledger/authority/revoke/breaker/shadow）、7913–8520（`answer_gate_auto`/`answer_gate_confirmed`/`_auto_decide_one`/`auto_decide_gates`/`_key_evidence_resolution`）、8520–8728（尾段 `main`）。

**未新核（不得由本证据推断）**：conductor.py 的 EXECUTE/VERIFY/L3 内体（约 1953–3232，仅读其被消费的 `_l3_*`/`_done_credentials_present` 签名与注释）、`_xkey_apply_*` 与 proposal 正文（约 5300–6350）、`reconcile_orphans`（6469–6546）、`_advance_key` 全链（1619–1742）；`autopilot/xkey.py`（1436 行）**未读**；`config.py`/`state.py`/`dispatch.py`/`write_face.py`/`evidence.py` 未全文读（仅按引用点看注释与调用形状）。**不宣称任一 H 的运行全链已核。**

### E1 H01～H12：现有触发/条件/写入 vs 目标差异

| H | 现有触发与条件（path:line） | 现有写入/消费 | 与已确认目标的差异 |
|---|---|---|---|
| H01 stage 启动 | `_activate_pending_stage`（1110）→ `_create_stage_confirm_gate`（1145）；`_gate_open(kind,stage)` 去重（4039）；`_stamp_gate_defaults`（3952）写 `default_action`/`expires_at(+48h)`/`authorizes: []` | approved → key-status 不变，stage `pending→running`（`_consume_answered_gates`:910）＋`gate-answered`＋`consumed_at`；rejected → `_latest_rejected_confirm`（1156）触发 roadmap-writer 重提案（上限 2：`used>=2 → return`，1190） | 目标要求"边界内先 DP 判断、不逐 stage 人工授权"。现有是**人工 gate**；自动 pass 对 stage-confirm 只有 guard 规则（`stage-confirm-fact-guard`，`auto_action="guard"`），即**永不自批**——需设计才能成为 H01 的 DP 入口 |
| H02 stage 关闭 | `_stage_closure`（1272）：全部 key ∈ `_STAGE_TERMINAL_STATUSES`（96）且无 in-flight row 且 `evidence_reconciliation_blocks`（8613）为假 → 写 dossier → 开 `stage-close` gate | approved → `closed`＋`_ensure_next_stage_gate`（1065，开下一 stage）；rejected → **`halted`**（无限期暂停，`_stage_activation`(1090) 见 halted 即 return False） | 目标是"四选项 + reject 不一律 halted + 非阻断遗留可带遗留关闭"。现有 `proposition_stage_close_credentials`（6711）要求"凭证齐全/无争议/dossier 在册"，比"非阻断遗留可披露"更严；**任意非 done 都阻断**，无法表达"非阻断" |
| H03 stalled | `mark_stalled`（6367）由 14 处调用（`STALL_REASON_CODES` 6560）；gate 带 `reason_code`/`loop`/`used_rounds`/`round_limit`/`credits_used`/`blocker_class` | approved → `stalled→running`＋1 credit/loop（`_apply_stalled_approvals` 4146 + `_resume_credits` 4124）；rejected → **`closed-legacy`**（4215，全仓唯一写入者，人工 confirm 才写，7981） | 目标"核停滞原因/尝试/方案/余预算，限定继续或**获授权**遗留收尾，不降目标"。现有 reject 无条件折叠成 closed-legacy，没有"授权方案"维度，也没有 note |
| H04 软轮次 | 同 H03（stalled）与 `budget-exhausted`（`_budget_bonus` 4067/`_budget_gate_rejected` 4079，按 `loop` 标签**轮询**，非消费） | approved budget-exhausted → 该 loop 多 1 轮；rejected → 该 loop 的 key stall | 目标"approve 只批准限定追加、不得变相无限续跑"。现有 budget gate **无 `consumed_at` 消费记录**（gates.py 文档与 `_consume_answered_gates` 注释明示 budget-exhausted/goal-change 是 polled），同一 approved gate 在整段 loop 生命期内**持续有效**；无"追加量/结束判据/理由"字段 |
| H05 pending-review | `defer_key_to_review`（4744，case-2 仅 `DEFERRABLE_GATE_KINDS=("stalled","budget-exhausted")` 4425）；`review_gate_for_key`（4354）取最老 pending gate 作把手；48h deadline（`_review_deadline` 4322/`REVIEW_DEADLINE_SEC`） | `_apply_review_decisions`（4540）：resume/rework→`running`、escalate→`stalled`；`_review_escalate`（4379）只记事件不动状态 | 目标"到期/事件只触发复核，恢复仍需条件；reject 不默认返工"。现有 **没有 approve 语义**：任何 resume/rework 只写 key status，**无 note/证据/预算校验**，也无"reject 拒绝当前恢复方案"的落点 |
| H06 goal 变化 | `tick`（3769）mtime 与 `st.goal_baseline` 比对 → 开 1 个 `goal-change` gate 并 halt（`open_goal_change_gate` 586 去重） | **任何答复**都刷新 baseline 并继续（tick 内 `if gate_open or st.goal_halted:` 分支），无 approved/rejected 区分；`proposition_goal_change`（6823）只作 guard（`auto_action="guard"`） | 目标"仅有效 approve 按 note 采用新版本；reject 不自动采用/刷新 baseline"。现有实现**违反**该条（reject 也刷新）——这是最明确的缺口之一 |
| H07 跨 key 修复 | `_xkey_aggregate`（4967）→`_xkey_ensure_gate`（5127，`request_id` 去重）；gate 带 `blast_radius`/`write_scope`；谓词 `proposition_xkey_authorize`（6839）要求 red_after==0 ∧ rc==0 ∧ test_id 绑定 ∧ blast ⊆ scope | `_consume_xkey_gate`（5201）：approved/rejected 写 ticket status＋ledger（含 `decisions[{decision,by,at,note}]`）＋`consumed_at` | 目标"note 限定必要性/目标 key/文件/动作/影响/授权/验证；approve 仅批准限定方案"。ledger 的 `decisions` 已带 note，是最接近目标的结构；缺"限定写面消费"与"执行另留证据"分离 |
| H08 冻结 AC/VC | `_freeze_contract_first_sight`（3664）：design 阶段冻结 spec 块、plan 阶段冻结 design 块，写 `<key>/evidence/contract-freeze.json`，非空块永不重写 | `contract_guard.evaluate`（384）判定：有变更且存在 `status=="approved" ∧ "contract-change" ∈ authorizes ∧ gate.key==key` 的 gate → ok（`find_authorizing_gate` 350）；**kind 不绑定、note/answered_by 从不读**（334 注释） | 目标"approve 只批准指定 key 具体条目变更、受影响重验、reject 不改契约"。现有授权是**整 key 级、永续**的（无条目集、无过期、无"重验"钩子），变更后不触发任何重验 |
| H09 proposal 耗尽 | roadmap-writer 每 stage 上限 2（1176–1215）；xkey proposal 上限 2（`_XKEY_PROPOSAL_MAX_ATTEMPTS`，5319 附近注释） | 耗尽即 **停止自动派发**、留 `config`/escalation 记录，等人工改文件 | 目标"先核派发/执行/接收失败与在途状态、未知不当空队列、受控有界重派、保留失败"。现有是**硬停**，没有"原因已消除"的恢复入口，也没有"在途核查"判据（除 in-flight row 检查） |
| H10 roadmap 重规划 | `_latest_rejected_confirm`→`_dispatch_roadmap_writer(rejected_note=…)`（1110/1176）；`attempt = used+1` | 重提案覆盖 `_roadmap.md`（writer），旧提案仅以 gate 文件＋timeline 留存 | 目标"实质修订依据/剩余预算/结束判据；新 stage 仍按 H01；不清次数"。现有 note 是自由文本（`rejected_note`），次数由 dispatch 行派生（不可清）——`次数不清`已成立，`依据/预算`未结构化 |
| H11 halted 恢复 | `_stage_activation`（1090）见 `halted` 即 return False；`_stage_transition_allowed`（991）把 `halted` 归入 terminal rank=2 且 terminal 吸收 → **导体自内无任何 halted→running 路径** | 仅人工改 `_roadmap.md`（无审计事件的 out-of-band 写） | 目标"保留停止事实、用恢复记录/新版本关联恢复、不重置消耗、人工停止/撤权不可 DP 自解"。现有**没有恢复通道**，也**没有停止事实记录**（halted 只是 key-status/status 值） |
| H12 熔断恢复 | `_auto_breaker_signal`（7762：60s≥17、1h≥100、同 `(key,rule,reason)` ≥2）→`_trip_auto_breaker`（7792）create-once 写 `auto-brake.md`＋一条 `executed:false` 的 escalate 行；`auto_breaker_state`（7742）每次从文件重推 | 熔断后 `auto_decide_gates` 早退（8480）；**tick 继续**、人工 gate 继续被消费；清除 = 人工删 `auto-brake.md`（7792 注释 "until a human clears this file"） | 目标"先停；原因消除＋预授权＋硬检查成立才经**明确受控恢复通道**；被熔断链路不得自批；不可用不默认批准"。现有**删除即恢复**、无原因证据/预授权/观察期/再熔断规则，且 `revoke_auto_decision`（7683）只撤销单条 decision，**不能撤销熔断** |

### E2 四选项的 gate-specific 效果（候选，非实现）

共同前置（全部四选项）：**PM note 送审前拟定并与模型理由分开存储**；note 绑定对象＝gate id ＋ 该 gate 的 `created` evidence 快照 sha256（`snapshot_gate_created` 7490，已含 `gate_file.sha256` 与证据 sha，可直接做冻结锚点，无需新字段）；**送审后冻结**＝note 的 sha 进入 sidecar，`answer` 时不重写 note；判定读 note 而非 `answered_by`（7675 `auto_authority_fields` 已明确排除 display 字段）。

| 选项 | 本 gate 内效果 | 禁止的效果 | 后继/消费锚点 |
|---|---|---|---|
| approve | 仅执行该 kind 已有消费者（E1 列）＋**按 note 限定的动作**（H04 追加轮次/L02 关闭/H12 恢复），并写 `consumed_at`（872）与 `gate-answered` | 不豁免硬门（contract_guard/claim/写面/凭证）；不新增权限/预算；不代替 dp-QG/dp-sign-key；不自动启动下一 stage（现有 `_ensure_next_stage_gate` 只是**开**下一 gate，不启动，1065 已符合） | `consumed_at`＋evidence `consumed` 快照（7518），sha 差异即漂移见证 |
| steer | **不改 state**，只记录 `decision=steer`（新扩展字段）＋一条待消费的后继请求标记；由 PM 发起 dp-pm-steer | 不作为放行/已整改证据；不计入 `_consumed_gate_ids` 的业务动作集；不 reset 轮次 | 后继调用证据需 PM 侧产生（dp-pm-steer 的 request/logical_id），与本 gate 的 `consumed_at` 分开 |
| need_fix | 同上，指向 dp-auto；**不修复** | 不得隐式 approve 或 defer 成 pending-review 替代整改 | 同上；须能观测"后继未发起/调用失败/返回选择/实际整改"四态（AC-049） |
| reject | 默认**不改 state**（关键差异）：`stalled` reject→closed-legacy 与 `stage-close` reject→halted 必须改为"仅当 note 内含明确获授权遗留方案时"才执行，否则只记拒绝 | 不一律 closed/halted/rework；不刷新 goal baseline（H06）；不删 brake（H12）；不自动关闭 key/项目 | 拒绝记录追加；被拒对象的原状态与轮次保持（现 `closed-legacy` 由 4215 硬写，需加前置授权判据） |

**同事项不双批**：H03/H04 若"同一轮投入"只留一个 owner —— 实现上以 `(gate.key, loop)` 去重：现有 `_budget_bonus`/`_budget_gate_rejected` 用 `loop` 标签匹配（4067/4079），而 stalled gate 也带 `loop`；因此"同 loop 已有 pending/approved stalled gate"时不得再起 budget-exhausted gate（当前**两条路径可同时存在**，`mark_stalled` 6367 与 `_advance_key` 各自建 gate，只在 `_gate_open` 的 `loop` 维度重复时被挡）。H09/H10 按问题用 dp-pm-steer/dp-auto，只有"独立审批事项"才加 gate（如跨 key 写面）；现 xkey gate 正是这种独立事项（5127），proposal/roadmap 耗尽**不应**再包一层 gate。

### E3 ≥2 个"具体条件复核与行动消费"方案

**S1（推荐）单一 gate 文件 ＋ `consumed_at` ＋ evidence sidecar 作冻结锚**
- 复核：新增 `gate_facts`-同构的 `review_facts(gate)`（复用 7381 分派表），对 H01～H12 各给"可复核条件"布尔集与缺失项名（现有 `proposition_*` 6654 已是此形，`detail` 已能列缺失项）。
- 消费：沿用 `_mark_gate_consumed`（872）+ `_consumed_gate_ids`（780）+ gates 锁；steer/need_fix 只落"后继请求待发"标记，不写业务副作用，故不需要消费锁竞争。
- 冻结：`snapshot_gate_created`（7490）已在 gates 锁内、`_stamp_gate_defaults` 之后取快照 → note sha 与 `gate_file.sha256` 同点冻结；漂移由 `evidence.changed` 判定（现有 `gate_evidence_state` 7551 已实现 replay-misbound / evidence-drift）。
- pros：零新账本（符合 SPEC §5）、幂等与并发语义已验证（`test_*` 之外的既有语义见 872/780 注释）、归档 id 复用已有防护（780 的 `(id, created_at)`）。cons：note 的"送审前"性质只能靠"created 快照后 note 不再变"的约定＋漂移判据，不是 schema 级保证；`expires_at` 无法表达"note 冻结时刻"。

**S2 独立 note sidecar（`gates/<id>.note.json`）＋二次消费表**
- 复核：note 文件独立 sha，`submitted_at`/`submitted_by`/对象集（key/条目/动作）显式；消费另写 `note-consumed.jsonl`。
- pros：绑定与冻结是 schema 级；四选项表达干净（不必借 `constraints`/`evidence_refs`）；可承载 H07/H08 的"限定文件/条目集"。
- cons：新增第二套账本（与"不另造第二套决策账本"张力）；并发需第 3 把锁；两个消费真源（`consumed_at` vs `note-consumed`）易漂移，必须规定单一裁决者。
- 推荐：**S1 为骨架，仅把 S2 的"对象集/冻结时刻"两点以既有 JSON 字段承载**——`write_scope`（gate 已有，gate JSON list）承载限定文件/条目集、`constraints` 承载预算/授权依据、`evidence_refs` 承载 note 引用的证据路径；这样"限定方案"可判定且不新增字段。若 RQ13 判定 `write_scope` 语义冲突，再退到 S2。

### E4 H12：恢复通道隔离的可落地方案比较

现状事实（必须承重）：熔断只关闭自动 pass（8480 `if breaker.get("active"): return`），`tick` 仍运行 `orchestrate`；`AUTO_RULE_BY_KIND`（7003）是 `gate_kind → AutoRule` 的**白名单字典**，`auto_decide_gates` 对无规则 kind 直接 `continue`（8476–8478）。因此"某 kind 永不被自动链决定"是**构造性保证**，不需要新隔离进程。

| 方案 | 机制 | 隔离强度 | pros | cons |
|---|---|---|---|---|
| R1 同链加规则 | 给恢复 gate 加 AutoRule（approve） | 无隔离：熔断链自己判定并写答案 → **明确违反 H12** | 实现最省 | 自批解锁；不可用时会走 escalate 分支而非阻塞；不采 |
| R2 复用现有 kind＋`reattest-of` 载体，靠自动链无规则 | 恢复 gate 用现有 kind（如 `stalled`/`stage-close`）＋`context_refs` 加 `breaker-recovery:`；不注册 AutoRule；答复只走 `answer_gate_confirmed`（7981，人类身份必填、reject 需二次确认） | 中：自动链"无法"决定（无规则），但仍与业务 gate 同池，可能被其它通用消费者（4146/4215/4540）读到并改写 key status | 零 schema 变更；复用 consumed/幂等 | 语义污染：业务消费者会把它当 stalled 处理（`_apply_stalled_approvals` 只按 kind+status 匹配）→ 必须新增 `reattest_of` 同形的跳过判据；`goal-change` 类"任何答复都刷新"的风险同源 |
| R3 新 kind `breaker-recovery`（gates.py `GATE_KINDS` 闭集需扩）＋专用恢复 CLI | 恢复判定三条件：①原因消除证据（`_auto_breaker_signal` 的同一输入重算为 None，只读、不写账本）②预授权记录（人工、能力/预算/观察期限定、带 expiry）③硬检查（`shadow_gate_allows` 7866 + evidence binding + 未撤权）。CLI 在同一 gates 锁内：验证三项 → 写"恢复记录"行（追加，不删 `auto-brake.md`）→ 标 brake 为 `recovered_at` → 只在观察期结束后才可能再次放开自动 pass | 高：自动链对无规则 kind 结构上跳过；恢复动作与业务消费者分池（kind 过滤）；不可用时 CLI 返回阻塞而非 approve | 语义清晰、可观测、可审计（恢复记录与熔断记录并存）；单点 CLI 易加锁 | 需要 gates.py 闭集扩展（schema 变更 → RQ13 批准）；需要 brake 文件从"存在即熔断"改为"带状态字段"（现 `auto_breaker_state` 只读 `reason`/`triggered_at`，7742） |
| R4 独立进程/信号 | 由 mw serve 之外的 supervisor 观察并清除 | 最高 | 与被熔断进程彻底分离 | 引入新常驻组件（与 GC-1/GC-3 冲突风险）、运维面扩大；本项目当前无此需求证据 |

推荐：**R3（新 kind + 专用恢复 CLI）**，因为只有它能同时满足"先停/原因消除/预授权/硬检查/不自批/不可用阻塞/记录不删"七条，并且与现有 `GateQueueUnreadable`（失败可见）和 `consumed_at`（幂等）语义一致；若 RQ13 判定 schema 变更成本过高，退 **R2 + 显式跳过判据**（须同时禁止 `_apply_stalled_*`、`_apply_review_decisions`、`tick` 的 goal 分支处理它）。**被明确否决**：R1。**不选**：R4（无需求证据，新增常驻面）。

必守不变量（三方案共通）：①恢复判断**不读也不清** `auto-brake.md`（清理由 CLI 在验证后写 `recovered_at`）；②恢复记录与熔断记录**并存**，历史不改写；③观察期内再次触发 `_auto_breaker_signal` 则重新熔断且不得自动恢复；④决策服务/材料不可用 → 阻塞并列出缺失项，**不得**默认 approve 或偷换通道；⑤用户停用/撤权优先于任何 DP 结果。

### E5 幂等/并发/未知/预算/版本/人工停止（设计要求清单）

- 幂等：gate 消费以 `consumed_at` 为唯一真源（872），`_consumed_gate_ids` 以 `(id, created_at)` 兜底归档复用（780）；四选项的 steer/need_fix **不写 business 副作用**，故只需"后继请求已发"幂等标记（现 `_defer_recorded`/`_escalate_recorded` 8104/8083 即为同形先例）。
- 并发：gates 锁（`acquire_conductor_lock`，30s 陈旧接管）包裹所有 gate 文件改写；roadmap 锁包裹 key-status 写；**禁止**在持锁期间做 evidence 大范围 snapshot（现有实现已把 snapshot 放在锁内小节内，7518/assert）。跨进程（CLI 恢复）必须复用同一锁名。
- 未知队列不当空：`queue_entries` 三分（缺目录=None、空目录=[]、不可读=raise，gates.py:373）+ tick 转 `config`/`error`（3836）。任何新消费者必须同样分三态。
- 标记受控恢复/保留失败：`closed-legacy`、`halted`、`brake`、`stalled` 都必须"追加恢复记录/新版本关联"，**不得**改状态值造成功（现 `_apply_stalled_rejections` 4215 直接写 closed-legacy，若要满足 H09/H11 需加"授权方案"前置与恢复记录）。
- 软轮 vs 硬预算：软轮 credit 由 dispatch 行派生（4124，单调不可重置）；硬预算**当前无字段无计量**，因此"approve 追加软轮不越硬预算"在代码里**无法验证**，需 RQ13 决定表示法；本 RQ 不设数值。
- goal/冻结契约变更失效：goal 变化已 halt（tick 3769）+ `proposition_goal_change` guard（6823）；冻结契约变化由 `contract_guard.diff_contract`（292）+ `evaluate`（384）判定，但**授权是永续整 key 级** → 目标要求"受影响旧批准不放行、仅指定条目变更"，需把授权对象细化为 `write_scope` 的 id 集合并对 `changed_ids` 求交（现成的 `ContractDiff.changed_ids`）。
- 人工停止/撤权不可自解：现有 `revoke_auto_decision`（7683）只撤销**单条** decision，**不能**撤销熔断；`halted` 无通道；`goal-change` reject 亦恢复。三处都必须新增"人工指令/撤权记录优先于任何 DP 结果"的硬前置。

### E6 候选写面、接口需求、可观测 VC 建议

**候选写面（精确，均待批准，不在本次实施）**
1. `packages/multi-workers/autopilot/gates.py`：`GATE_KINDS`（82）扩展 `breaker-recovery`（若选 R3）；如需四选项表达，采用 `_SCALAR_EXTENSION_FIELDS`（`blocker_class` 同形，gates 已声明"扩展字段不入 40 名冻结序"）新增 `gate_decision` ∈ {approve, steer, need_fix, reject}；**不改** `FRONTMATTER_FIELDS` 顺序与 `_REQUIRED_FIELDS` 6 字段断言（gates.py:180）。
2. `packages/multi-workers/autopilot/conductor.py`：`gate_facts`(7381) 增 H05/H06/H09/H10/H11 分支；`auto_decision_for_rule`(7027) 增 steer/need_fix 谓词（现状只有 approve/guard/escalate/None）；`_consume_answered_gates`(910) 的 goal-change 分支改为 approved-only；`tick`(3769) baseline 刷新改 approved-only；`_apply_stalled_rejections`(4215)/`_consume_answered_gates` 的 stage-close rejected 加"获授权遗留方案"前置；新增 `breaker_recovery_*` 一组（无 AutoRule 注册，显式加入三处消费者跳过集）。
3. `packages/multi-workers/autopilot/contract_guard.py`：`authorizing_gates`(334) 增"id 集合交集 ∧ 未过期"判据（复用 `ContractDiff.changed_ids` 292）。
4. 账本（已存在，追加不新建文件）：`.agenticdoc/_autopilot/auto-decisions.jsonl` 增 `phase="recovery"`/`"steer"`/`"needfix"` 行；`_AUTO_AUTHORITY_KEYS`(7668) 需为恢复记录扩字段（**唯一** schema 点）。
5. 禁止面（本 RQ 从未触碰）：源码、配置、`auto-brake.md`、活 gate、ledger、`_roadmap.md`、其它 key、原研究、PM 文档、`report.md`。

**与 PM / RQ13 / RQ17 的接口需求**
- PM（RQ15）：提供 note 的对象集与冻结时刻（写 `write_scope`/`constraints`/`evidence_refs`）；steer/need_fix 的后继请求证据（dp-pm-steer/dp-auto 的 logical_id）；不得以 gate 选择声明代替后继调用。
- RQ13（设计契约）：裁决①四选项载体（扩展标量 vs 新 status 值 vs sidecar）；②`GATE_KINDS` 是否扩 `breaker-recovery`；③硬预算表示法与计量（当前**无**）；④冻结契约授权粒度（id 集合）与失效规则；⑤role 资格（PM 准备 note ≠ 新工具权限）。
- RQ17（签收/投影）：gate approve ≠ key 签收；stage-close approved 必须仍要求每个必需 key 的有效签收证据（现 `proposition_stage_close_credentials` 6711 已校验 `l3-verdict`/`l3-report`/`achieved`/dossier，但没有 dp-sign-key 语义）；恢复/撤销记录的投影不得被读作"完成"。

**可观测 VC 建议（机器可判，对应 AC 编号）**
- VC-RQ14-01（AC-007/049）：同一 gate 上 `gate_decision ∈ {steer,need_fix}` 时，`consumed_at` 为空、key/stage status 前后字节相同、且存在一条指向 dp-pm-steer/dp-auto 的后继请求记录。
- VC-RQ14-02（AC-007）：`reject` 且 note 无"获授权遗留方案"时，`closed-legacy`/`halted` 写入次数 = 0，gate 记 `decision=reject`。
- VC-RQ14-03（AC-008/012）：`auto_gate_mode=live` 下构造 evidence 绑定失败，`answer_gate_auto` 对目标 gate 的写入次数 = 0，`reason_code ∈ ENGINE_REASON_CODES`。
- VC-RQ14-04（AC-010/048）：stage 存在 `pending-review` key 时 `stage-close` gate 数为 0（现由 `_STAGE_TERMINAL_STATUSES` 保证，可回归锁定）。
- VC-RQ14-05（AC-015/019）：同一 goal sha + 同一 stage 版本重复 tick，`stage-confirm` gate 新建数 ≤ 1，`gate-answered` 事件数 ≤ 1。
- VC-RQ14-06（AC-016/017）：缺工程证据时 stage 启动写入 0 且事件 `detail` 列出缺失项名；缺业务意图时产生具体人工问题而非默认 approve。
- VC-RQ14-07（AC-020/021）：`used_rounds` 在追加后 +1，`round_limit`/`credits_used` 只按 note 授权增量变化，硬预算越界写入 0（需 RQ13 定义硬预算字段才可观测）。
- VC-RQ14-08（AC-022/023）：`expires_at` 到期只产生 1 条复核触发记录（`review-escalated` 去重 4379），状态写入 0。
- VC-RQ14-09（AC-024/025）：`goal-change` 为 rejected 时 `goal-snapshot` 事件数 = 0、baseline 值不变（当前**会**刷新 → 该 VC 现在应为 FAIL，正是设计输入）。
- VC-RQ14-10（AC-026/027）：`blast_radius.files ⊄ write_scope` 时 xkey approve 写入 = 0（现由 `proposition_xkey_authorize` 6839 保证）。
- VC-RQ14-11（AC-028/029）：AC/VC 变更未在授权 id 集合内时 `contract-unauthorized` stall 产生 1 次、done 写入 0；受影响条目重验记录存在。
- VC-RQ14-12（AC-030/031/032/033）：proposal/roadmap 耗尽后旧提案文件字节不变、新提案为新文件/新 attempt、次数计数器不下降。
- VC-RQ14-13（AC-034/035）：`halted` 在无恢复记录时 `running` 写入 0；人工停止/撤权存在时任何 DP 结果导致的恢复次数 = 0。
- VC-RQ14-14（AC-036/037）：熔断存在时自动链对恢复 gate 的决定数 = 0；无预授权或缺证据时 `auto-brake.md` 字节不变；恢复记录与熔断记录**同时**存在。
- VC-RQ14-15（AC-052）：同 `(gate.id, created_at, note sha)` 重放 → 业务动作数 1、`consumed_at` 只写一次；并发两个写者时 gate 文件 sha 只发生一次受控变更（锁）。

## 残留与未验证

1. **未全文读** conductor.py 的 EXECUTE/VERIFY/L3（1953–3232）、`_advance_key`（1619–1742）、xkey apply 正文（5300–6350）、`reconcile_orphans`（6469–6546）；`xkey.py`/`config.py`/`state.py`/`dispatch.py`/`write_face.py`/`evidence.py` 未全文读。H04/H09/H10 的 loop 计数与在途判定细节因此**未被独立核实**，仅按 `_resume_credits`/`used_rounds`/`_row_exists` 的注释与调用形状取证。
2. 未运行任何测试、未起服务、未读任何 provider 凭证、未调用决策服务或额外裁决、未读取或清除 `auto-brake.md`、未读活 gate/ledger/roadmap/其他 key。**未验证任何 live 模式或项目当前熔断/暂停状态**；由静态事实推断活项目"已熔断/死锁"被明确拒绝。
3. 四选项载体、`GATE_KINDS` 扩展、硬预算表示法、note 冻结的 schema 级保证、恢复预授权值均为**未决**；本 RQ 不设置也不推断数值。
4. H11 的"恢复记录/新版本关联"在现有代码中**不存在**，本证据只给出候选（追加恢复行 + 新版本引用），未设计其存储位置。
5. `halted`/`closed-legacy`/`brake` 三者的恢复语义在 SPEC 中已确认，但实现面全部缺失；不得据本证据宣称 AC-034～037 可判 PASS。
6. 本证据不构成设计批准、写面批准、AC/QG/签收结论；DESIGN 阶段仍待用户与 PM 批准。

## 上下文来源

- `.agenticdoc/goal.md:5`（项目目标锚点）；`.agenticdoc/mw-dp-consolidation/spec.md:1`（53AC 已锁 2026-10-25T23:37:14+08:00；§1.1 八入口、§1.2 各 H 摘要、§1.6 H01–H13 归属映射、§3 AC-007～010/015～037/048/049/052）。
- `.agenticdoc/mw-dp-consolidation/evidence/graduation-pm-review-20261025.md`（毕业考勘误：13 条不采纳的越界推导、修订映射、残留）；`.agenticdoc/mw-dp-consolidation/evidence/gate-four-option-confirmation.md`（四选项与 PM note/reject 边界已确认）；`.agenticdoc/mw-dp-consolidation/evidence/h12-breaker-recovery-confirmation.md`（H12 已确认规则与"凹断不必然停整个 conductor"的静态事实）。
- 源码（全文/分段读，见 E0）：`packages/multi-workers/autopilot/gates.py`、`packages/multi-workers/autopilot/contract_guard.py`、`packages/multi-workers/autopilot/conductor.py`（已核区段见 E0）。
- 历史静态观察（**未新核，仅转引**）：`evidence/autopilot-human-decision-inventory.md`、`evidence/autopilot-runtime-panorama.md`（H12 与 `_trip_auto_breaker` 的既有引用）、`evidence/research/spec-runtime-inventory-20261024.md`。
- 任务书：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq14-design-autopilot/task.md`（要求 1～5、禁写面、四节交付契约）。
