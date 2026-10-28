# RQ4 — autopilot 显式人工 gate：生产 → 人工答案 → 消费（源码审计）

范围：六类 kind 的实例生产、写入、人工答案语义、消费者坐标，以及当前自动决策面（off/shadow/live）。
只读源码；未执行代码/测试，未读活 gate/ledger/凭证；无 ask_decision / provider 探针。
坐标格式 `path:line symbol`（conductor.py = `packages/multi-workers/autopilot/conductor.py`，gates.py / config.py 同目录）。

## 结论

1. 六 kind 的**全部生产者只有两处**：`conductor._create_gate`（:3903，内含 `gates.create` :3934 + `_stamp_gate_defaults` :3938）与 `tick` 里 goal-change 的直建点（:3812 `gates.create` 后手工 :3827 `_stamp_gate_defaults`）。TS 侧无生产者（`gate-writer.ts` 只 `answerGate` :169）。`gates.create`:457 是唯一写文件处；默认戳 `default_action=escalate-to-human`、`expires_at=created+48h`、`authorizes: []`（`_gate_default_fields`:4013）。
2. **生产 → 答案 → 消费**链按 kind 全部落实且有消费者（A-01..A-12 表），不存在"只有 gate 文件没有消费者"的 kind；但存在**两个例外形态**：(a) `stalled`/`budget-exhausted` 当 key 处于 `pending-review` 时由**另一消费者**处理，reject 语义从"closed-legacy（破坏性）"变成"rework→running"（`_apply_review_decisions`:4540）；(b) 同 kind `stalled` 的 re-attest 载体（`reattest-of:`）由 `_apply_reattests`:4661 消费，其生产者 `reattest_gate`:4608 **无生产调用点**（仅测试），当前不可达。
3. **自动面实际可达性远低于 RULES 表观**（F1..F6，均源码级事实，非线上判断）：`stage-confirm`、`budget-exhausted`、`goal-change`、`xkey-authorize` 四条规则的谓词**读的是没有任何生产者的 v2 字段**（`roadmap_validation`/`goal_sha256`、`used_rounds/round_limit/credits_used`、`goal_diff/goal_sha256_before|after`、`blast_radius/write_scope`），事实恒缺 ⇒ 恒 `escalate`（fail-closed）；`goal-change` 还额外**结构不可达**：其 pending 期间 `tick`:3845-3854 早退，`orchestrate`→`auto_decide_gates` 根本不跑。可真正走 approve 的只有 `stage-close`（`_stage_close_facts`:7269 从盘上重算）与 `stalled`（要求 `blocker_class=paperwork` + `proven-false-negative`）两条窄路，且 `stage-close` 还受 shadow 前置 + 证据 sidecar 绑定（`gate_evidence_state`:7551）制约。
4. **goal-change 的 approve/reject 在实现上无差别**：gate 被任一状态回答后 `tick`:3855-3862 一律刷新 baseline 并恢复，reject 不会保持 halted（问题文案承诺的 "reject to stay halted" 无消费者支持）。这是语义缺口，不是人工必要性证据。
5. **"当前仅人工"≠"只有人能判断"**：A-01 的结构校验+goal sha、A-02 的五条收口事实、A-03 的缺件明细都是**机器可判定事实**；它们的自动面失效原因是**缺生产者/缺绑定**（F1/F2/F6），不是业务未知。反例是 `stage-close reject`（A-03）与 `stalled reject`（A-05）——不可逆且无审计退路，属真实人工必要性（破坏性授权）。
6. 告警/通知**不是决策**：`_remind_pending_gates`:3515（`gate-reminder`/`remind-suppressed`）、`_review_escalate`:4379（48h 与 closure 触发）、`_trip_auto_breaker`:7792（burst-1h/60s、repeat-signature）只产生可见性与配额刹车，不写 gate 答案，也不改变 key/stage 状态。
7. **建议（与事实分列，不预设归属）**：
   - 可按新原则先 DP 的候选：A-02（stage-close approve，事实已齐且已有 approve 规则）、A-01 的机器部分（结构校验+goal 绑定，需补 `roadmap_validation`/`goal_sha256` 生产者）、A-07（budget 追加一轮，需补 round 计数 stamping）、A-10 的修复执行段（需补 `blast_radius`/`write_scope`）。
   - 保留人工的候选理由：A-05/A-03（不可逆+无审计/无回退，破坏性）、A-09（目标本身变更=业务意图，但当前 reject 语义应先修）、A-11 `contract-change`（冻结 AC/VC 的授权动作，属权限外）。
   - dp7/dp15/dp20 只作**候选覆盖标注**：dp7（gate 失败处置）候选覆盖 A-03/A-05/A-08 的拒绝后果；dp15（autopilot gate）为 A-01..A-12 的统一入口候选；dp20（stage 收口）候选覆盖 A-02/A-03。**缺材料**：dp15 无 gate-kind→DP 映射材料；**缺动作**：dp20 无 approve/reject 的机器动作编码（现为文件答案）。不预先锁定归属或合并。

## 证据

| 标签 | 生成（生产坐标） | 人工真实问题 / 可选动作 | approve 实际影响 | reject 实际影响 | 消费者坐标 |
|---|---|---|---|---|---|
| A-01 | `_activate_pending_stage`:1110 / `_create_stage_confirm_gate`:1145（首个 pending stage）；`_ensure_next_stage_gate`:1065（收口后开下一 stage）；去重 `_gate_open`:4039 | "Stage N（K keys，目标 …）确认启动？approve=启动并开始派发；reject=要求重新提案"（:1146-1152, :1078-1085） | `_consume_answered_gates`:910 → `_set_stage_status running`(:1028) + `gate-answered`；stage 转 running，`orchestrate`:595 开始派发 | 不作状态转移：`_activate_pending_stage`:1120-1136 走 `_latest_rejected_confirm`:1156 → 重新派 roadmap-writer（每 stage 上限 2 次，:1195 `used>=2` 停） | `_consume_answered_gates`:944-950；`_mark_gate_consumed`:872 |
| A-02 | `_stage_closure`:1272-1333（全部 key 终态 + 无 in-flight + 无证据争议 + dossier 落盘后 `_create_gate`:1326） | "Stage N 全部 key 已终态，闭环 dossier 已写入 … 确认闭环？approve=closed 并开放下一 stage"（:1320-1325） | stage→`closed` + `stage-close` 事件 + `_ensure_next_stage_gate`(:973) | — 见 A-03 | `_consume_answered_gates`:955-967 |
| A-03 | 同上 A-02 gate | 同上（reject 分支无独立文案） | — 见 A-02 | stage→`halted`；`_stage_activation`:1090 对 halted stage 直接 `return False`，只能人工编辑 `_roadmap.md` 恢复；`_stage_transition_allowed`:991 使 halted 终态不可回退 | `_consume_answered_gates`:968-975 |
| A-04 | `mark_stalled`:6367 → `_create_gate`:6418（容错字段 `reason_code/loop/used_rounds/round_limit/credits_used/blocker_class`，:6399-6416） | "key X 已 stalled（reason）——遗留关闭（closed-legacy），还是人工介入后重试？"（:6419-6422） | key-status `stalled`→`running` + `resume` 事件；`_resume_credits`:4124 每个封顶 loop 各加 1 轮 | 见 A-05 | `_apply_stalled_approvals`:4146 |
| A-05 | 同上 A-04 gate | 同上（reject = 遗留关闭） | — | key-status→`closed-legacy`（**全仓唯一 writer**，:4215）；删 bad-draft marker；破坏性，人工路径需 `--confirm-destructive`（`answer_gate_confirmed`:7981 / mw.py:9454） | `_apply_stalled_rejections`:4215 |
| A-06 | `_defer_declined_gate`:8277 → `defer_key_to_review`:4744 `_create_gate`:4794（仅 shadow/live；kind 复用 `stalled`/`budget-exhausted`，ref `review:<key>`） | "key 待复核：同 stage 其它 key 已终态——resume / rework / escalate 请复核"（:4768-4771） | key→`running`（resume）；stage 收口前置解除 | key→`running`（rework，**不产生 closed-legacy**）；超 48h 或 closure 触发 `review-escalated`（`_process_deferred_reviews`:4451） | `_apply_review_decisions`:4540 → `apply_review_decision`:4494 |
| A-07 | `_advance_key` L2 预算耗尽处 `_create_gate`:1713（refs=[loop]，**无 machine_fields**） | "L2 回路 X 已达 N 轮上限且仍有缺口——追加一轮修复，还是标记 stalled？"（:1715-1717） | `_budget_bonus`:4067 → 该 loop 追加 1 轮（used < limit+1） | 见 A-08 | `_advance_key`:1680-1685（`allowed` 计算处） |
| A-08 | 同上 A-07 gate | 同上 | — | `_budget_gate_rejected`:4079 → `mark_stalled`(:1714-1719) 产生 **A-04 的第二个 gate**（连锁决策） | `_advance_key`:1703-1712 |
| A-09 | `tick`:3812 `gates.create`（**唯一不走 `_create_gate` 的生产点**，手工 :3827 stamp + :3829 snapshot） | "goal.md changed while autopilot is active — review the new goal and approve resuming, or reject to stay halted."（:3813-3817） | goal baseline 刷新 + 解除 halt（:3855-3862）；**approve/reject 无差别** | 同 approve（不保持 halted）——语义缺口，见 结论 4 | `open_goal_change_gate`:586 + `tick`:3843-3862（轮询式，非消费式） |
| A-10 | `_xkey_ensure_gate`:5127 → `_create_gate`:5142（refs=[request_id, ticket_rel]；`xkey_repair` 默认 false，config.py:97-111） | "跨 key 红 file::test（owner K）请求解冻授权：追认后由框架执行受限修复，拒绝则留账本"（:5143-5146） | ticket→approved → `_xkey_proposal_stage`:5279 派 proposal → `_xkey_apply_stage`:6298（applied→verified→closed） | ticket→rejected，仅 ledger 落账（`_consume_xkey_gate`:5201） | `_consume_answered_gates`:952-955 → `_consume_xkey_gate`:5201 |
| A-11 | 无独立生产：`authorizes` 由 `_gate_default_fields`:4026 写成 `[]`，须人工在答案时手填 | 无 gate 问题文案；含义="此批准同时授权 contract-change" | 任一 **approved** 且 `key` 匹配、`authorizes` 含 `contract-change` 的 gate 即放行冻结契约变更（`contract_guard.gate_authorizes_contract_change`:322 / `evaluate`:384，消费点 conductor.py:2955 done 事务） | 无（reject 不授权） | `contract_guard.authorizing_gates`:334；`AUTHORIZES_ACTIONS` gates.py:203（`retry` **无生产消费者**，仅测试） |
| A-12 | `reattest_gate`:4608 → `_create_gate`:4655（kind 复用原 kind，ref `reattest-of:<id>`）；**无生产调用点**（grep：仅测试） | "… re-attest of gate-NNNN — evidence may have changed; judge again"（:4642-4649） | 阻塞 key（stalled/closed-legacy/pending-review）→`running` | 原判定保持不变（key 不动） | `_apply_reattests`:4661（当前仅测试可达） |

### 自动面明细（按 kind；`auto_decide_gates`:8467，`RULES`:6912-7001，`AUTO_RULE_BY_KIND`:7003）

| kind | 规则 / auto_action | 事实来源 | 今日可达结论 |
|---|---|---|---|
| stage-confirm | `stage-confirm-fact-guard` / guard（永不 approve） | `roadmap_validation`+`goal_sha256`（gate 字段）| **恒 escalate**：两字段无生产者（`_stage_closure`/`_create_stage_confirm_gate` 均不传 machine_fields）⇒ `proposition_stage_confirm`:6654 必失败 |
| stage-close | `stage-close-credentials` / **approve** | `_stage_close_facts`:7269（从盘重算五条） | **可 approve**（唯一事实完备的 approve 规则），但需：shadow 前置 `shadow_gate_allows`:7866（≥5 夜+≥20 shadow 决策+该规则有反例）、`gate_evidence_state`:7551 绑定成功（**off 期创建的 gate 无 sidecar ⇒ `not-bound` ⇒ escalate**）、夜配额 6/键配额 2（:6610-6611）、breaker 未跳 |
| stalled | `stalled-false-negative` / **approve** + `approve_extra` | gate 字段 + `recompute_stall_cause`:7093 + `recompute_false_negative_class`:7171 | **窄路可达**：须 `blocker_class=paperwork`（`BLOCKER_CLASS_KINDS` :6602 + `auto_decision_for_rule`:7027 前缀）**且** `false_negative_class=proven-false-negative`；`_stall_blocker_class`:6348 只在 bad-draft marker 含 achieved 失败时给 paperwork |
| budget-exhausted | `budget-exhausted-bounded` / approve | 同 gate 字段 `used/limit/credits` + `_blocking_gap_count`:7232 | **恒 escalate**：A-07 建 gate 不传 machine_fields ⇒ 三计数恒 None ⇒ `budget-count-drift` |
| goal-change | `goal-change-normative-guard` / guard | `goal_diff`/`goal_sha256_before|after`（gate 字段） | **双重不可达**：(a) 字段无生产者；(b) pending 期间 `tick`:3845-3854 早退，自动面整体不跑 |
| xkey-authorize | `xkey-authorize-s4-guard` / guard | `blast_radius`/`write_scope`（gate 字段）+ ticket verify 事实 | **恒 escalate**：两字段全仓无生产者（仅 parse/facts/测试） |

其它自动面事实：`default_action=escalate-to-human`+`expires_at=+48h` 对六 kind 统一（`_gate_default_fields`:4013，A-09 亦经 :3827）；`AUTO_COOLDOWN_SEC=30` 只进 `_auto_budget`:8117 报表、**不阻断**决策；case-2 延后仅对 `DEFERRABLE_GATE_KINDS`（:4312）且仅 shadow/live（`_defer_declined_gate`:8277）。

## 残留与未验证

1. **未读全文的部分**：conductor.py 共 8687 行的非 gate 段未逐行通读（:1-560 头部/锁、:1395-1690 L3 预算段、:1760-3230 execute/verify/done 事务主体、:3572-3769 提醒壳尾部与契约冻结、:4830-5127 defer 尾部与 xkey 挂载、:5287-6348 xkey apply/verify、:6478-6622 orphan 回收、:8500-8687 状态/CLI）。已用 `gate` 关键词扫描这些区段，未见第六种 gate 生产者或额外消费者；但"未逐行"即未证。
2. **stage-close 旧注释与实际规则冲突（已核）**：`_stage_closure` docstring:1274-1277 称 "a stalled key with a pending gate blocks closure — AC-024"，实际代码只用 `_STAGE_TERMINAL_STATUSES = ("done","closed-legacy")`（:78）判定：**任何**非终态（含 `pending-review`、无 gate 的 stalled、running）都阻断收口，"有 pending gate" 不是条件。注释为旧语义，规则以其后代码为准。
3. **A-09 语义缺口**：reject 不保持 halted 是源码事实（`tick`:3855-3862 无 status 分支）；是否属故意设计未在源码注释中说明，未验证。
4. **A-11 人工填 `authorizes`**：仅证 `contract_guard` 侧读取与 `[]` 默认；"人工填什么、由谁记录"无强制流程，未验证是否有 UI/CLI 提示（未读 monitor.ts / status-model.ts）。
5. **未验证线上状态**：未读活 gate 目录、auto-decisions.jsonl、auto-brake.md，故"当前项目 auto_gate_mode"与"是否已有 live 决策"均未断言；本文所有"恒 escalate"均为**代码路径必然性**，不是运行观测。
6. **dp7/dp15/dp20 归属未定**：仅标候选覆盖与缺材料/缺动作（见结论 7），未做映射设计；本 RQ 不锁合并方案。
7. 未执行任何测试/静态检查，未调用 ask_decision/真实 provider；本 worker 自身模型正常执行，不作"零模型"声明。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/tasks/RQ4-autopilot-human-gates.md`（sha256 与 task.md `card_sha256` 一致：3464aa60…72c4）。
- 源码（本 RQ 主证据）：`packages/multi-workers/autopilot/gates.py`（全文，:82 GATE_KINDS、:197 BLOCKER_CLASSES、:203 AUTHORIZES_ACTIONS、:457 create、:826 enumerate）；`config.py`（全文，:87 DEFAULT_CONFIG、:102 auto_gate_mode 默认 off、:122-123 枚举 off/shadow/live、:62-68 effective_config 仅 2 键可机层覆盖 → auto_gate_mode 只能在项目层）；`conductor.py`（gate 相关段全读，坐标见表）。
- 邻近只读核对：`packages/multi-workers/autopilot/contract_guard.py`（:322/:334/:384 authorizes 消费）、`effective_config.py`（:62-68）、`mw.py`（:9410 `_ap_gates` 只读视图、:9454 `_ap_answer`→`answer_gate_confirmed`）、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`（:169 `answerGate`，无创建）。
- 项目既有文档（仅作限制输入，不作证据）：`.agenticdoc/goal.md:5`；本 key `evidence/pm-research-review-20261024.md`（要求 producer→writer→consumer 坐标、区分实现事实与人工必要性）；旧 RQ2 `evidence/research/spec-gate-authority-20261024.md`（未复制其结论）。
- 未读：`monitor.ts`/`status-model.ts`/`console.ts`（UI 面）、`xkey.py` 内部、`write_face.py`、`roadmap.py` 内部；活 gate/ledger/凭证（按任务禁止）。
