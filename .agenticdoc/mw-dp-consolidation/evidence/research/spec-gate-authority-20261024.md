# RQ2: 四门职责与现有授权边界（只读研究）

Key: mw-dp-consolidation ｜ 类型: research ｜ 时间预算 15m
结论口径：只列证据与未批准提案，不宣称任何设计已批准，不改动源码/配置/gate/phase。

## 结论

1. 六类 gate 的真实授权面**不在决策服务里**：`dp15-autopilot-gate` 在 registry 中 `wired=false`、`executor=none`（`packages/multi-workers/decide_registry.json:1000`），全仓无生产 producer（仅 `mw.py:3077` 契约探针与 `pm/decision-tool.ts:147` allowlist）。真实创建者只有 conductor，真实消费者是 gate 文件 + conductor 规则表；人工路径是 TS `/autopilot gate` writer（`autopilot/gate-writer.ts:1`）。
2. 六类 gate 的机器权限**按 kind 分级**，不是统一"全人工"：`RULES` 里 stage-confirm / goal-change / xkey-authorize 是 `guard`（只否决、从不自动应答），stalled / budget-exhausted / stage-close 是 `approve`（`conductor.py:6893 RULES`；各 rule `:6894/:6908/:6935/:6954/:6969/:6983`）。但 stage-close 与注释 `conductor.py:6535`（"stage-confirm / stage-close fact planes are GUARDS ONLY … never auto-answer"）冲突 → 必须先冻结谁为准（见 D1）。
3. 自动放行默认关闭且四重前置：`auto_gate_mode` 默认 `off`（`autopilot/config.py:102`）；`live` 还要过证据绑定 `gate_evidence_state`（`conductor.py:7551`）、shadow 历史闸 `shadow_gate_allows`（`conductor.py:7866`）、夜/键配额（`conductor.py:8427`）。因此"现有授权边界"= 默认全人工 + 显式 opt-in 的窄自动面。
4. dp6/dp7/dp20 三个 DP 同样 `wired=false`：dp6/dp20 `executor=none`，dp7 executor 是必抛 over-authority 的占位（`decision_points.py:496 _unwired_executor`）。今天真实的质量审核与阶段收尾**不是** DP 产生的，而是 L3 审阅 worker + done 凭据 + stage-close gate。
5. dp25 是唯一已接线的收尾面，写权单点：`mw._decide_sign_finish`（`mw.py:4876`）只在 `conclusion == "finalize"` 时写 sign-off（`mw.py:4906`、`:4937`），canonical 签收只有一处（`decide_signoff.write_signoff` `decide_signoff.py:698`）。"四门再加一次签收"即新增第二审批，不允许。
6. 已定位 3 个真实缺口（非提案）：stage-close 注释/代码矛盾；`authorizes: retry` 有声明无消费者（只有 `contract-change` 被 `contract_guard.py:323` 消费）；dp25 两套结论词表（registry `finalize|continue|user-confirm` vs `decide_signoff.CONCLUSIONS=continue|narrow|revoke` `decide_signoff.py:83`）。

## 证据

### 1. 六类 gate 现有授权表（创建 → 判据 → 自动 → 人工 → approve/reject 实际动作）

| kind | 生产创建（路径:行 符号） | 机器判据（proposition） | 自动放行 | 人工 fallback | approve 实际动作 | reject 实际动作 |
|---|---|---|---|---|---|---|
| stage-confirm | `conductor.py:1145 _create_stage_confirm_gate`；`:1065 _ensure_next_stage_gate`（stage-close 后开下一 stage）；`:1110 _activate_pending_stage` | `conductor.py:6894` rule `stage-confirm-fact-guard` → `proposition_stage_confirm`（roadmap 结构校验为空 + goal sha 绑定），`auto_action="guard"` | **否（guard only）** | 人工答案或缺省阻塞；reject 后 `_activate_pending_stage:1110` 走 roadmap-writer 重提案（上限 2 次） | `_consume_answered_gates:947` → `_set_stage_status(...,"running")`，本 tick 开始派发 | 不推进；roadmap mtime 早于 rejection 才重提案，否则等人改 roadmap |
| stage-close | `conductor.py:1272 _stage_closure`（`:1294` 全 key 终态、`:1296` 无 in-flight、`:1306` reconciliation barrier、`:1326 _create_gate`） | `conductor.py:6908` rule `stage-close-credentials` → `proposition_stage_close_credentials:6711` 五条：终态/无 in-flight/无争议/dossier 在盘/每 key 五凭据（`_done_credentials_present:2560`），`auto_action="approve"` | **是（代码允许，与 `:6535` 注释矛盾）**：`_auto_decide_one:8348` → 绑定 `gate_evidence_state:7551` → `shadow_gate_allows:7866` → 配额 `:8427` → `answer_gate_auto:7913` 写 `answered_by=conductor-auto`+`auto_policy_id` | 默认 `off` 时全人工；证据不绑定/漂移 → `escalate`（`_auto_decide_one` live 分支） | `_consume_answered_gates:954` → stage `closed` + `_ensure_next_stage_gate:965` | stage `halted`（`:968`），`_stage_activation:1099` 暂停直到人改 roadmap |
| stalled | `conductor.py:6367 mark_stalled` → `:6418 _create_gate(...,"stalled",...)`（14 个调用点触发，reason_code 闭集 `:6553 STALL_REASON_CODES`） | `conductor.py:6935` rule `stalled-false-negative` → `proposition_stalled`；另有 `blocker_class` 前置：仅显式 `paperwork` 可 approve（`auto_decision_for_rule:7040`，`BLOCKER_CLASS_KINDS:6602`，materialize `_stall_blocker_class:6348`） | **是（窄）** | 非 paperwork / 证据漂移 → `escalate`；declined 可 `_defer_declined_gate:8277` 把 key 停到 `pending-review`（live 才改状态，shadow 零副作用） | `_apply_stalled_approvals:4146` → key-status `running` + `_resume_credits:4124`（每受限于本 key 的 loop 各 +1 轮） | `_apply_stalled_rejections:4215` → `closed-legacy`（`timeline` `stalled` 事件） |
| budget-exhausted | `conductor.py:1713 _advance_key`（L2 回路到上限且仍有缺口，`refs=[loop]`） | `conductor.py:6954` rule `budget-exhausted-bounded` → `proposition_budget_exhausted`（used==limit+credits 且 blocking gaps 仍在） | **是（窄）** | 不满足 → escalate；reject 后同 loop 再上限直接 stalled（`_budget_gate_rejected:4079`，调用点 `:1697`） | `_budget_bonus:4067` → 恰好一轮追加 | `mark_stalled(..., reason_code="l2-budget-rejected")`（`conductor.py:1699`） |
| goal-change | `conductor.py:3811` tick 内 `gates.create(...,"goal-change")`（绕过 `_create_gate`，同时 `goal-halt`；`:3830` 注释明确"pure human-decision gate，无 machine judgement"） | `conductor.py:6969` rule `goal-change-normative-guard` → `proposition_goal_change`，`auto_action="guard"`（只否决） | **否（guard only；`:6539` 明示 POLICY face 从不自动）** | 人工 approve/reject 是唯一权威；gate 打开期间 tick 返回 `halted-goal-change`（`:3842`） | 轮询消费（`:923` 注释"polled, not transitioned"）：baseline 刷新为当前 goal mtime 并恢复（`:3849`） | 保持 halted，等待人工改 goal 或再次应答 |
| xkey-authorize | `conductor.py:5127 _xkey_ensure_gate`（`cfg["xkey_repair"]` 门控，一 request_id 一 gate，`:5140 _gate_open` 去重） | `conductor.py:6983` rule `xkey-authorize-s4-guard` → `proposition_xkey_authorize:6839`（red_after==0、rc==0、test_id 绑定、blast_radius ⊆ write_scope），`auto_action="guard"` | **否（guard only）** | 人工批准是唯一推进路径；不可解析 ticket → `_xkey_escalate:5156`（零 gate 零自动） | `_consume_xkey_gate:5201` → ledger `approved` + ticket 状态；随后 `_xkey_proposal_stage:5279` 派提案 worker，apply 前再过边界预检 | ledger `rejected` + ticket 状态落账（同样 `:5201` 单点消费，不冻结 ticket 但不再推进） |

授权记录字段：`authorizes` 闭集 `{retry, contract-change}`（`autopilot/gates.py:203 AUTHORIZES_ACTIONS`，解析 fail-closed `:735`）；只重写既有行、缺失即拒（`gate-writer.ts` ANSWER_FIELDS + `--authorizes`）。
消费端：仅 `contract_guard.py:323 _gate_allows_contract_change`（approved + 含 `contract-change` 才允许 AC/VC 文本改写；否则 `contract-refused` + `contract-unauthorized` stall，`conductor.py:2975`）。`retry` 无任何生产消费者（grep `retry` 无命中）→ 声明权与实际动作不一致。

### 2. 四 DP 现状与缺口

| DP | registry 事实 | 生产 producer | 生产 consumer | 缺口 |
|---|---|---|---|---|
| dp6-qg-verdict | `decide_registry.json:344`：`wired=false`、`executor="none"`、`wiring_note`"未接线；QG 结论现由 quality gate 人工审核"；材料 `qg.checks_total/checks_failed/blocking/scope`；选项 `pass|fix|reopen`；`triage-client.ts:429` 有 `"closure"` 归属条目 | 无。真实质量面 = L3 审阅轮 `## Quality Gate Report` + `_l3_round_verdict`（`conductor.py:2336`，qg 段落抽取 `:2983`）+ done 五凭据 `_done_credentials_present:2560`（`l3-verdict.txt=meets`、`l3-report.md`、`quality-gate-report-*.md`、`achieved.md>=200B`、`pm-state.md PASS`） | 无 DP 侧消费；`pass/fix/reopen` 不驱动任何动作 | 无"正式审核结论"载体：`qg.*` 无 builder、verdict 无消费者；机器硬门（凭据/绑定/争议屏障）事实上高于任何审核意见 |
| dp7-gate-failure | `decide_registry.json:419`：`wired=false`、`executor="unwired"`、`wiring_note`"未接线；相位门禁失败现走 autopilot 门禁告警（占位执行器 act 必抛 over-authority）"；材料 `gate.name/missing_items/verdict_age_hours/has_config_error`；选项 `missing-evidence|stale-verdict|config|unknown` | 无 | 无 | 只有原因分类，无动作、无回执；`_unwired_executor:496` 的 act 必抛 = "绝不执行"；与真实失败面（stall reason_code 闭集 `:6553`、gate 告警、advance 门禁）无映射 |
| dp15-autopilot-gate | `decide_registry.json:1000`：`wired=false`、`executor="none"`、`wiring_note`"未接线；autopilot 人工门由 gate 文件 + conductor 放行规则承担，P0 默认关"；材料 `gate.kind`（六值闭集）/`pending_items`/`age_minutes`/`evidence_refs`；选项 `continue|narrow|revoke`；`pm/decision-tool.ts:147` 可调用 | 无（仅 `mw.py:3077` 契约探针） | 无 | DP 词表与实际 gate verdict 词表不一致（gate 只有 approved/rejected + `authorizes` 子集），`continue/narrow/revoke` 无处落地；P0 默认关 |
| dp20-stage-close | `decide_registry.json:1354`：`wired=false`、`executor="none"`、`wiring_note`"stage 闭环由 autopilot stage-close 人工门承担"；材料 `stage.id/tasks_done/tasks_total/open_blockers/evidence_refs`；契约仅 `tasks_done<=tasks_total`（`decision_points.py:2506`）；选项 `close|hold|rework` | 无 | 无 | 与 stage-close gate 同对象双表示（close|hold|rework vs approve|reject），今天只有 gate 有消费者；缺"多 key 阶段集成证据"判据（registry 只到计数） |
| dp25-signoff-conclusion | `decide_registry.json:1699`：`wired=false` 但 `executor="wired"`、五段材料（delivery_goal/actual_completion/verified/unverified/unfinished_impact）、选项 `finalize|continue|user-confirm` | `decide_signoff.auto_conclusion:384`（`mw decide sign` 路径） | `mw._decide_sign_finish:4876`：`finalize`→`write_signoff`+lifecycle `record_signoff`（`:4965`）；`continue/user-confirm`→不写、handoff 指令（`:4990`） | 双词表：`decide_signoff.CONCLUSIONS=("continue","narrow","revoke")`（`:83`）+答案校验（`:437`）与 registry `finalize|continue|user-confirm` 不一致；其余为待设计项，不新增第二次签收 |

### 3. 四门联合职责与触发矩阵（现状事实；"提案归属"列均为**未批准**）

| 审核对象 | 唯一触发 | 材料来源（可复核） | 问题/选项（现状） | 现归属 | 提案归属（未批准） |
|---|---|---|---|---|---|
| stage 启动提案 | roadmap 写入且 stage `pending`（`conductor.py:1110`） | `_roadmap.md` + goal sha + roadmap 结构校验 | approve=启动/reject=重提案 | 人工（stage-confirm gate） | dp15（协议门）保留；dp20 不参与启动 |
| stage 收尾（多 key 联合验收） | 全 key 终态 + 无 in-flight + 无证据争议（`:1294`-`:1306`） | `stages/stage-N-close.md` dossier + 每 key 五凭据 + `_key_evidence_resolution` 绑定 | approve=closed/reject=halted | stage-close gate（人工，可窄自动） | dp20 唯一 owner（close/hold/rework → 映射 approve/reject）；dp15 只做 gate 协议/机械 guard，不重复裁决 |
| 质量结论（key/round） | L3 审阅轮产出 `## Quality Gate Report` 与 `l3-verdict.txt` | `l3-verdict.txt`/`l3-report.md`/`quality-gate-report-*.md`/`achieved.md`/`pm-state.md` + 证据绑定 | `pass|fix|reopen`（无消费者） | L3 worker + done 凭据（无 DP） | dp6 正式审核 owner，结论闭集待冻结；dp6 只出审核结论与缺口，不写 sign-off、不覆盖机器硬门 |
| 相位门禁失败 | advance/phase 门禁失败或 gate 告警（`dp7 wiring_note`） | `gate.name`/`missing_items`/`verdict_age_hours`/`has_config_error` | 4 类原因（无动作） | 无（占位 executor 必抛） | dp7 只做**失败处置**（重跑/整改/上报），不改写原门禁判据；与 dp6 分工：dp6 判"是否达标"，dp7 判"没达标怎么办" |
| 单 key loop 上限（stalled/budget） | L2/L3 回路耗尽或拒绝（`conductor.py:1697`、`:6367`） | 门槛字段（reason_code/used/limit/credits）+ 重算 cause/false-negative + blocker_class | approve=重试/reject=遗留关闭；budget approve=加一轮/reject=stalled | stalled/budget gate（人工，可窄自动） | 流程授权归 dp15（重试/遗留关闭/加轮），任务处置归 dp2（继续/拆小/直执/上抛）；同一事件只由一方裁决，另一方只读材料 |
| goal 变更 | `goal.md` mtime 变化（`:3811`） | goal sha before/after + normative diff | approve=恢复/reject=保持 halt | 人工（goal-change gate） | dp15 保留（纯人工 policy 面） |
| 跨 key 授权 | xkey ticket 待授权（`:5127`） | ticket + 验证事实 + blast_radius/write_scope | approve=追认修复/reject=留账 | 人工（xkey-authorize gate） | dp15 保留；`authorizes` 子集必须与其消费者一一对应（现 `retry` 无消费者） |
| 交付签收 | `mw decide sign`（任意 key） | 决策归档行 + 哈希链 + 五段 sign-off 材料（`decide_signoff.py:343 signoff_state`） | `finalize|continue|user-confirm` | dp25（唯一写者 `mw.py:4906`） | dp25 保持唯一签收；dp6 审核结论只能作为材料进入，不产生第二次审批 |

非重复审核分工（提案要点，未批准）：
- stage-close：dp20 裁决"阶段能否收尾"，dp15 只承载 gate 协议与该 gate 的机械 guard/审计；同一 stage 同一证据版本只允许一次有效裁决，第二次进入只读展示。
- stalled：dp15 裁决"流程性授权"（是否给重试 credit / 是否遗留关闭），dp2 裁决"任务级处置"（继续/拆小/直执/上抛）；以事件类型区分（`checkpoint` vs `loop-exhausted`），同一事件不得双审。
- dp6/dp25：证据复用而非重复审批 —— dp6 结论文本可进 dp25 `unfinished_impact`/`verification_evidence.unverified`；dp25 不重判质量，dp6 不写 sign-off。

### 4. 建议动作与失败策略（提案，未批准）

方案 A（最小改动，建议先评审）：**对象 owner 制**
- dp15 = 六类 gate 的协议裁决者（continue=approve / narrow=限定 `authorizes` 子集 / revoke=reject），但不新增执行权：verdict 仍只能经 gate 文件 + 现有消费者（`_consume_answered_gates:910`）落地。
- dp6 = 质量正式审核（结果闭集建议 `met|gaps|blocked`，必须携带可复核证据路径 + 缺口清单）；`blocked`/证据缺失时禁止任何"通过"；不得覆盖 `_done_credentials_present`/`evidence_reconciliation_blocks`。
- dp7 = 失败处置（闭集建议 `rerun|rework|escalate|hold`），必须回执到具体 gate/stall 事件；不改原判据。
- dp20 = stage 收尾唯一 owner（close/hold/rework）；stage-close gate 的 approve/reject 由 dp20 结论写入，dp15 不再对该 kind 出第二结论。
- 失败/不可用策略：决策服务不可用或材料非法 → 不写 gate、不放行、返回阻塞原因；`auto_gate_mode=off`（默认）保持全人工；任何 `escalate` 保持 gate pending 并留 timeline。

方案 B（更彻底，改动面大）：**kind 归并**
- 把 stage-close 并入 dp15（stage-close 只是 kind），dp20 退役或降为材料 builder；dp6 结论作为 stage-close 与 stalled 的必需材料；dp7 退役并入 dp15 的失败分支。
- 与方案 A 的实际差别：A 中 stage-close 的唯一裁决者是 dp20、dp15 只做协议；B 中 dp15 是全部六类唯一裁决者，dp20 不裁决。B 需删除/降级既有 DP 语义与 `wiring_note`，属"改框架门禁语义"，必须单独批准。

两方案共同的不可接受项（记为待批准）：新增 gate 自动应答权；让 dp6 结论直接放行机器硬失败；dp25 增加第二次签收；用 DP 结论替代现有 gate 消费者。

## 待用户决策（必须点名批准，未批准不得实施）

- D1 stage-close 自动面：`conductor.py:6535` 注释（stage-confirm/stage-close 只做 guard、从不自动应答）与 `RULES:6908` + `_auto_decide_one:8348` 的 `approve` 事实矛盾。需冻结：收紧为 guard-only（缩小现有代码行为），或承认 T-12 凭据放行是既有边界（改注释）。二者都改变"现有边界"的解释，不能由研究自行裁定。
- D2 dp15 是否成为 gate 的真实裁决生产者（=新增一个可应答 gate 的模型环节/执行权）。当前 P0 默认关、无 producer；接 line 即扩权。
- D3 dp6 正式审核结论闭集，以及 dp6 结论能否作为 done/stage-close 的必要材料（现机器硬门优先）。
- D4 dp7 真实动作集与接线（占位 executor 必抛 over-authority；接 line 即新增执行权）。
- D5 `authorizes: retry` 的消费者（现只有 `contract-change` 有消费者）——补消费者或从闭集移除。
- D6 dp25 双词表统一方向（registry `finalize|continue|user-confirm` vs `decide_signoff.CONCLUSIONS`）；不得以统一为名新增第二次签收。
- D7 stage-close 归属（方案 A 的 dp20 owner vs 方案 B 的 dp15 归并）。

## 残留与未验证

- 未做运行期探针：任何项目是否已把 `auto_gate_mode` 设为 `shadow|live`（需读项目层 config，本次只读源码）。
- 未完整审计 TS 展示/告警：`autopilot/monitor.ts`、`autopilot/console.ts` 只确认存在 `GATE_KINDS` 镜像（`status-model.ts:689`）与 gate 解析（`:1079`），未逐条核对是否把 `answered_by=conductor-auto` 显示为人工答案。
- 未审计 `pm/decision-tool.ts:147` allowlist 对 dp15 的实际可调用性与 `triage-client.ts:429` 的 `closure` 归属语义（仅见列表项）。
- 未进入 AgenticTask 框架侧 `advance_phase` 门禁实现（dp7 所称"相位门禁失败"的真实判据），本报告只按 `wiring_note` 与 stall reason_code 闭集取证。
- 未验证 dp6 的 `qg.*` 是否有任何历史生产 ledger 行（未读 `.agenticdoc/_autopilot/decisions.jsonl`，且不在本任务写面内）。
- `stalled` 在 dp15/dp2 的最终分工依赖 dp2 现有业务契约（`mw-decision-context` 基线）；本报告只做非重复性提案，未改动 dp2 语义。
- 所有"提案归属/方案 A/B/结果闭集"均未获批准；本文件不是 spec 或 design。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq2-gate-authority/task.md`（RQ2 范围与写入面）。
- 需求与决策基线：`.agenticdoc/mw-dp-consolidation/spec.md`、`key-decision.md`、`evidence/research/spec-confirmed-intent-20261024.md`。
- 目标锚点：`.agenticdoc/goal.md:5`。
- 代码证据：`packages/multi-workers/autopilot/{gates.py,conductor.py,config.py,contract_guard.py}`、`packages/multi-workers/{decide_registry.json,decision_points.py,decide_signoff.py,mw.py}`、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/{gate-writer.ts,status-model.ts}`、`packages/coding-agent/src/extensions/agent-team-loop/pm/{decision-tool.ts,triage-client.ts}`。
