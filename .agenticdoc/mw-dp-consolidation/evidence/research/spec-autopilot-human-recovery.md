# RQ5 — autopilot 非普通 gate、失败恢复与跨 key 人工决策（事实盘点）

## 结论

- 非普通 gate 的"真实人工选择"只有 6 组聚合决策面，不是 N 个：**S1 key 失败恢复（stall 家族）/ S2 pending-review 复核 / S3 re-attest 重评 / S4 xkey ticket 授权 / S5 合同变更授权 / S6 goal-change 与 stage 级 halt（RQ4 主表已覆盖，本 RQ 仅交叉引用）**。
- 14 条 `STALL_REASON_CODES` **不构成 14 个决策**：它们只是同一扇 `stalled` gate 的 `reason_code` 字段与机器复算对象；人类面对的问题句、可选语义、消费者、状态变化全部同一（B-01/B-02）。
- S1 的 approve/reject 不是"继续/停止"的同义反复：approve = 对**每个**受该 key 约束的回路各 +1 轮（一次性、不可复用），reject = `closed-legacy`（状态机内不可逆，唯一写者）。这是实质业务判断（再投轮 vs 弃坑），且需要二次确认（B-03/B-04）。
- `pending-review` 本身不是决策点，是"拒绝当场裁决"的容器；机器已获权把 `stalled`/`budget-exhausted` 自动延后到该状态（`DEFERRABLE_GATE_KINDS`）。真正的人类选择仍是 resume/rework/escalate，且 escalate 分支**只记事件、不改状态**（B-05/B-06）。
- xkey 的真实授权是"允许框架在 `write_scope` 内改冻结块"，**不是追认已发生的修改**：proposal 只在 ticket 已 `approved` 后才派发；apply 前有 metadata 一致 + `check_boundary` + sha 漂移零写三重 fail-closed；未授权状态被 `_UNAUTHORIZED_APPLY_STATUSES` 拒绝（B-08）。
- 授权消费与 retry 是**两件事**、结论相反：授权被一次性消费（apply→closed 或 verify_failed 均为 terminal，无自动 retry）；失败后重试的真实入口是人工清 `proposal_exhausted_at` 或新 ticket，不消耗也不复活旧授权（B-09/B-10）。
- 合同变更"需要人类同意"是真的且 fail-closed（done transaction 第一步），但**授权未被消费**：`authorizing_gates` 只查 `status==approved` + `authorizes` 含 `contract-change` + key 匹配，不绑 kind、不查 `consumed_at` ⇒ 一次批准对该 key 后续所有 AC/VC 改写永久有效（B-11）。
- DP 覆盖初判：dp7 只有失败分类、无执行体；dp20 只覆盖 stage 关闭；dp15 是"gate 存在 + continue/narrow/revoke"的通用出口，**是唯一形状上能覆盖 S1–S4 应答面的既有 DP，但缺 "retry/再投一轮" 与 "closed-legacy 不可逆" 语义**；S1 的"再投轮 vs 收窄"更贴 dp2；S2 若要机器判需 dp6(dp6 亦未 wired)。【建议】不新增 DP，dp15 承载 gate 应答、dp2 承载轮次取舍、不可逆分支走破坏性确认语义。
- 剩余人工必要性（事实层面不可去）：`closed-legacy` 不可逆写入、合同变更的"谁授权什么"白名单语义、xkey `blast_radius ⊆ write_scope` 的业务判断。其余（paperwork 类 stall、defer、reattest 重评、证据刷新后的复核）已具备机器判据，适合"先 DP"。

## 证据

阅读范围：`conductor.py` 全文分段读完（约 8700 行，含 tick/orchestrate/所有 stall·review·reattest·xkey·auto 段）、`contract_guard.py` 全文（367 行）、`xkey.py` 1–1260 行（余约 176 行未读，见残留）。行号取自本次 grep 的符号定义行。

- **B-01（S1 stall 家族：唯一决策面）** 触发：14 个 `mark_stalled` 调用点（`conductor.py:1565 _record_advance_result`、`_advance_key` 预算/派发、`execute_loop`、`_verify_loop` 五分支、`_done_transaction`）。人工问题：「遗留关闭（closed-legacy），还是人工介入后重试？」作用对象：一个 key 的 roadmap `key-status`。机器处理：`RULES` 中 `stalled-false-negative`（`proposition_stalled` + `blocker_class=="paperwork"` 前缀），默认 `auto_gate_mode=off`。仍报人：`blocker_class=judgment`/缺失、`recompute_false_negative_class=="undecidable"`、reason/count 漂移。消费者：`conductor.py:4146 _apply_stalled_approvals`（→`running` + `resume` 事件）、`:4215 _apply_stalled_rejections`（→`closed-legacy`）。创建者：`:6367 mark_stalled` 同时落 achieved 草稿 + `patterns/<key>/stall-lesson.md`。
- **B-02（14 原因 ≠ 14 决策）** `STALL_REASON_CODES`（闭集，`conductor.py:6560` 附近）只用于：写 gate 机器字段（`_stamp_gate_defaults` 校验闭集）、以及 `recompute_stall_cause`（`:7400` 附近，按 loop 前缀重新推导 family）做 `reason_code == cause_class` 的可反驳核对。人看到的问题句、approve/reject 语义、消费者均与 reason 无关。
- **B-03（轮次语义，事实）** `conductor.py:4124 _resume_credits` 文档与实现：一个 approved `stalled` gate 在**每个**受该 key 约束的回路（L2 边界 / EXECUTE retry / L3 收敛 / L3 repair）各 +1 轮，`used` 单调来自 append-only 队列行 ⇒ 花完即再次封顶，需新的 stall→approve 周期。
- **B-04（reject 不可逆 + 二次确认）** `REJECT_CONSEQUENCE_STATEMENT`（`conductor.py:120` 附近）与 `:7981 answer_gate_confirmed`：`decision=="reject"` 且 `confirm=False` 时**零写入**返回准确后果（状态机内不可逆；恢复=手改 `_roadmap.md` 一到两行；代价=无审计痕迹 + 轮次不退）；已应答 gate 拒答，重评只能 `reattest_gate`。
- **B-05（S2 pending-review 生产/消费）** 生产：`conductor.py:4744 defer_key_to_review`（唯一 `pending-review` 状态写者，建 deferrable gate 作复核把手）；机器自动生产：`:8277 _defer_declined_gate`（仅 `DEFERRABLE_GATE_KINDS=("stalled","budget-exhausted")`，shadow 零改状态、live 才落盘）。消费：`:4540 _apply_review_decisions` approve→`resume`/reject→`rework`，**两者都 → `running`**，无 `done`/`closed-legacy` 出口。不变量：不在 `_DEP_SATISFIED`、在 `_DISPATCH_SKIP_STATUSES`、阻断 `_stage_closure`（`conductor.py:1272`）。
- **B-06（escalate 不是决策）** `conductor.py:4451 _process_deferred_reviews` 两个升级信号（`expires_at`/`created_at+48h` 到期；同 stage 其它 key 全终态）都只调 `_review_escalate`（`:4370` 附近）：追加一条去重的 `review-escalated`（含 `age_s`/`deadline_s`/`default_action`），**key-status 不变、不新建门**。⇒ 机器已"报人"，但人的操作入口仍是原来那扇 gate。
- **B-07（S3 re-attest）** `conductor.py:4608 reattest_gate`：新建**一扇新门**（同 kind/stage/key，`context_refs` 追加 `reattest-of:<原 id>`，原门字节不动）；无 pending 重评门时幂等返回。`:4661 _apply_reattests`：approved 只把 `stalled`/`closed-legacy`/`pending-review` → `running`（`_REATTEST_REOPEN_STATUSES`，显式排除 `done`）；rejected 保持原判并消费答案。生产侧无自动规则会生成 reattest ⇒ 这是纯人工重评入口（CLI）。
- **B-08（S4 xkey 授权前后关系）** 授权前：`:4967 _xkey_aggregate` 由 L3 判定源里的 handoff 登记 → ledger `detected` → ticket `ticketed` → `:5127 _xkey_ensure_gate` 一 request 一门。授权后：`:5201 _consume_xkey_gate` 写 ledger `approved` + `ticket.status=approved`；**此后** `:6190 _xkey_apply_one` 才要求 proposal 存在，且 S1 `_xkey_proposal_matches`、`xkey.py:check_boundary`（文件/行集合/untouchable/sha 四重）、`xkey.py:apply_block_replace`（当前块 sha ≠ ticket sha 抛 `XKeyShaDrift`，零写）。反向保证：`xkey.py:_UNAUTHORIZED_APPLY_STATUSES` 对 `detected/ticketed/rejected/timed-out/boundary_violation/escalated` 直接抛 `XKeyAuthorizationError`。⇒ 人授权的是"未来一次受限写入的许可"，proposal 在授权后才产生。
- **B-09（授权消费 vs retry，分别核验）** 消费：`ticket` 状态机 `approved→applied→verified→closed`，`_XKEY_APPLY_ENTRIES` 只允许 approved/applied/verified 重入，`_XKEY_TERMINAL_STATUSES`（含 `verify_failed`/`boundary_violation`）阻止再进 ⇒ 授权一次性。retry：S4 校验不绿走 `:5881 _xkey_verify_failed`（按 `pre-apply.bak` 字节回滚 + `verify_failed` terminal），**没有自动重试路径**，也不复用旧授权。
- **B-10（xkey 人工恢复入口，无门无 DP）** `_XKEY_PROPOSAL_MAX_ATTEMPTS=2`，耗尽写 ticket `proposal_exhausted_at` + `:5363 _xkey_proposal_exhaust`（ledger history + `escalation.md` + timeline）。人可清该字段或直接落 proposal 续跑；这条路径不经过任何 gate/DP。
- **B-11（S5 合同变更：需人同意为真，授权未消费）** `conductor.py:2932 _done_transaction` 首步 `contract_guard.evaluate`（`contract_guard.py:323`）；`ok=False` → `contract-refused` 事件 + `mark_stalled(reason_code="contract-unauthorized")`，在任何 QG/achieved/pm-state 写之前。授权载体：`contract_guard.authorizing_gates` = `status=="approved"` ∧ `authorizes` 含 `contract-change` ∧ `gate.key==key`；kind 不绑、`note`/`answered_by` 不读、**不查 `consumed_at`** ⇒ 与 B-03 的"credits 不复用"相反，这里一次批准对该 key 永久有效。
- **B-12（合同冻结的产生面）** `conductor.py:3769 tick` → `_freeze_contract_first_sight`：仅在 `_index.parallel` phase 为 `design`（冻 AC）/`plan`（冻 VC）且该 block 为空时写一次 sidecar；历史 key 不回溯 ⇒ 人工另走 `mw autopilot contract-freeze`（CLI，非门）。
- **B-13（S6 stage 级 halt/恢复，RQ4 交叉）** `conductor.py:1090 _stage_activation` 遇任一 stage `halted` 立即返回（暂停直到人改 roadmap）；`_set_stage_status` 非单调写被 `_stage_transition_allowed` 拒并记去重 `stage-reopen-refused`；stage-close reject → `halted`（不可逆）。恢复 = 手改 `_roadmap.md`，无门、无 DP。**与 RQ4 `stage-close` 行重复**：RQ4 记 gate 层 approve/reject 语义，本 RQ 只补"reject 后的恢复入口是手改 roadmap"这一事实。
- **B-14（auto 面的人工恢复，容易漏）** `:7683 revoke_auto_decision`（按 `decision_id` 追加负记录，`answered-revoked` 集合生效，不改 gate 字节）；`.agenticdoc/_autopilot/auto-brake.md` 需人清才恢复自动；`shadow_prerequisites`/`shadow_gate_allows`（≥5 夜 ∧ ≥20 shadow 决定 ∧ 每规则至少一次反例）把 shadow→live 的信任判断留给人。人在这里做的是"信任/撤销"，不是业务裁决。
- **B-15（RQ4 交叉与不重复部分）** RQ4 主表覆盖 `stage-confirm`/`stage-close`/`stalled`/`budget-exhausted`/`goal-change`/`xkey-authorize` 六类的 gate 层事实（创建点、proposition、approve/reject 实际动作）与 dp6/dp7/dp15/dp20/dp25 的 wired 状态。本 RQ 不重述这些，只补：stall reason 的聚合性、pending-review/reattest 两条独立恢复通道、xkey 授权前后顺序与消费/retry 分离、合同变更授权的未消费性、以及"reject 后手改 roadmap"这一无门恢复面。

## 残留与未验证

- 未运行任何代码/测试/autopilot，未读活 ledger/gate/凭证/服务；全部为源码静态阅读（符合任务约束），因此"实际发生过几次"类问题无实测数据。
- `xkey.py` 末约 176 行（`run_verification` 尾部、`evidence_bundle_write`、`closed` 判定）**未读**；B-09 中"closed 才闭合"依据来自 conductor 侧 `_xkey_write_evidence` 读 `document["closed"]`，未验证 xkey 侧缺失项集合。
- 未完整读 `dispatch.py`(109KB)/`gates.py`/`state.py`/`advance.py`/`closure.py`/`roadmap.py`/`evidence.py`，仅按 conductor 调用面确认签名与语义；`gates.create` 的 13-key 输出、`consumed_at` 语义未逐行核验。
- 行号来自 grep 定义行，块内引用（如 `:6560`、`:7400`、`:4370`、`:120`）为同段近似位置，可能有 ±10 行偏差。
- 未核验历史事故实例（E2Feature / JCodingAss / FeatureMigrator 6684-gate 事件）的现场数据，只引用代码注释所述的结论。
- DP 覆盖初判是**建议**，未修改 registry / 四 DP 业务 / impl 计划；本 RQ 不锁定"合并或新增"。

## 上下文来源

- 目标锚点 `.agenticdoc/goal.md:5`；任务卡 `.agenticdoc/mw-dp-consolidation/tasks/RQ5-autopilot-human-recovery.md`（含 dispatch card 上下文与入口行号）。
- 源码：`packages/multi-workers/autopilot/conductor.py`（全文分段）、`contract_guard.py`（全文）、`xkey.py`（1–1260）。
- 交叉证据：`.agenticdoc/mw-dp-consolidation/evidence/research/spec-gate-authority-20261024.md`（RQ4 六类 gate 主表 + dp6/dp7/dp15/dp20/dp25 段），本 RQ 不重复其 gate 层事实。
- 未改写任何原研究报告、spec/design/plan、registry、活 gate/ledger、源码。
