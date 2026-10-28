# RQ6 — Autopilot PM/框架侧上报人决策与 dp7/dp15/dp20 覆盖

> 审计面：TS autopilot 命令/通知面 + conductor gate 平面（6 kind）+ 框架 advance_phase.py 相位门 + 签收。
> 新原则：autopilot 放权，先 DP 自动判断、确需人才升级。本文件只列当前事实与候选，不宣称合并/新增已批准。

## 结论

1. **两套并行权威平面，零交叉**：真实人工门是 conductor 的 6 类 gate 文件（`gates.py` `GATE_KINDS`），由 TS `/autopilot gate`（`gate-writer.ts:169 answerGate`）或 `mw autopilot answer`（`conductor.py:7981 answer_gate_confirmed`）写 4 个 frontmatter 字段；dp7/dp15/dp20 在 autopilot 代码中**零调用**（`packages/multi-workers/autopilot/` 内仅 `dispatch.py:475` 注释提到 `decision_points.ESCALATED_REASONS`；TS autopilot 目录无命中），registry 三者 `wired=false`。所以现在不是"先 DP"，而是"只有 gate 平面"。
2. **已有自动决策机制不叫 DP**：`config.auto_gate_mode`（默认 `off`，`off|shadow|live`）+ `RULES` 6 条（每 kind 一条；stage-confirm/goal-change/xkey-authorize 是 `auto_action="guard"`，永不自动 approve）+ 夜间/键配额 + breaker + shadow 门（`SHADOW_MIN_NIGHTS=5`、`SHADOW_MIN_DECISIONS=20`）。它写 `.agenticdoc/_autopilot/auto-decisions.jsonl`（`decide|defer|revoke|escalate` 行），与 DP 材料契约/registry/回执**完全无关**——这是新原则下最直接的既有"DP 替身"，也是重复审批风险源。
3. **"当前可问 ≠ 能推进"**：dp15/dp20 是 P0 且 `executor=None`，可被 ask 并落答复，但无消费者读取其答案 → 业务动作 0；dp7 是 P2，注册的是 `_unwired_executor` 占位（`decision_points.py:496`，调用即 `NotImplementedError`），且实际相位失败路径根本不经过它。三者都缺"问项→真实动作"接线。
4. **dp7 的触发已被吞并**：相位门禁失败 → `_record_advance_result`（`conductor.py:1565`）分类 `interface-drift|gate-blocked|timeout-env|other`，连续 5 次（`advance_stall_ticks`）→ `mark_stalled(reason_code="advance-class")` → 生成 `stalled` gate（`conductor.py:6367/6418`）。失败本身**不请求人选择**；人被问的是 stalled 处理（C-11），而 dp7 的 `gate.verdict_age_hours` 与相位门无关。
5. **stage 闭环 ≠ key 签收**：stage-close 是 roadmap 状态机（approve→closed + 下一 stage-confirm；reject→halted），证据是每 key 终态 + in-flight + reconciliation + dossier + 凭证（`proposition_stage_close_credentials`）；dp25 是 key 决策档案签收（`advance_phase.py:309 _decision_signoff_problems` + `evidence/review/sign-final.md` 的 `counted_rows/rows_sha256`）。两者对象、消费者、证据不同，当前无证据复用机制。
6. **真正"只能人"的硬点**（事实层）：`stage-confirm`、`goal-change`、`xkey-authorize` 三个 guard 类（规则只 veto/放行检查，不产出 approve）→ approve 只能人工或 live 下无人可答；`stalled reject` 写 `closed-legacy`（不可逆）；`stage-close reject` → halted；`--authorizes` 是闭集 `{retry, contract-change}`（越集 fail-closed 不写）。新原则下候选：把这三类 guard 的**判定输入**升级为 DP（而非把不可逆动作放开），见下文覆盖表。

## 证据

### A. TS 命令面：控制命令 vs 通知 vs 真正决策

| ID | 上报面（path:line + symbol） | 触发 | 人工问题/实际选择 | 当前自动途径 | 消费者动作 | 人工必要性候选 | 交叉 |
|---|---|---|---|---|---|---|---|
| C-01 | `console.ts:181 cmdStatus`、`console.ts:448 cmdGates`、`cmdTimeline`、`cmdRoadmap` | 人主动敲命令 | 无（只读视图） | 全部本文件推导，无模型调用 | 仅 UI；status 顺手写 timeline watermark | 不适用：**是人工操作，不是被上报的业务决策** | — |
| C-02 | `console.ts:586 cmdSetEnabled`、`console.ts:638 cmdSetPaused` | `/autopilot enable|disable|pause|resume` | 是否开启/暂停编排 | 无自动途径（配置写 `.mw/autopilot-config.json`，锁内 RMW） | conductor 下一次 config 轮询生效；enable 还会 ensure mw serve（含 stale restart） | 候选保留人：治理开关，不是业务裁决 | — |
| C-03 | `console.ts cmdMonitor`（`/autopilot monitor`） | 人主动 | UI 偏好 | — | 仅 widget | 不适用 | — |
| C-04 | `console.ts:457 cmdGate` → `gate-writer.ts:169 answerGate` | 有 pending gate | approve / reject（+`--note`、`--authorizes`） | 人的直接答案；**无 DP 参与** | 写 `status/answered_at/answered_by/note(/authorizes)`，字节保真；conductor ≤5s 轮询消费 | 判据：动作不可逆或 guard 类（见 C-09/10/13/14）保留人；可逆且有机器谓词（C-11/12）候选先 DP | RQ4（gate 主表） |
| C-05 | `mw.py:12281 mw autopilot answer` → `conductor.py:7981 answer_gate_confirmed` | 同上（CLI 路径） | 同上；reject 必须 `--confirm-destructive`；已答 gate 拒绝重答（需 `reattest_gate`） | 无 | 同 C-04 四字段 | 同上；双入口语义已对齐（reject 需二次确认），属"动作契约"而非新决策 | RQ4/RQ5 |
| C-06 | `pm-orchestrator.ts:2368` gate 提醒（`reminderN`） | pending 超阈 | 无 | 通知去重（session entry） | 仅提示"等待人工应答" | 不适用：**通知 ≠ 选择** | — |
| C-07 | `pm-orchestrator.ts:~228`（phase 证据就位提醒） | spec/design 证据齐 | 无（"何时复查由你决定"） | 只 notify | 无 | 不适用：真门在 C-19 | — |
| C-08 | `pm-orchestrator.ts:~380 takeOverKey` | 写 spec/design/plan.md 自动接管失败 | 无（被他人 claim → watch-only） | 文件身份判定 | 仅 watch | 候选：claim 冲突属已退役 dp18；不在本 RQ 新增 | RQ4(退役) |

### B. 6 类 gate（真实业务决定平面）

`GATE_KINDS` = stage-confirm / stage-close / stalled / budget-exhausted / goal-change / xkey-authorize（`gates.py:82`）；`GATE_ACTIONS`（`console.ts:198`）只是**展示用后果表**，不是执行器。默认 `default_action: escalate-to-human` + `expires_at=created_at+48h`（`conductor.py:3923/4319`，唯一 choke point `_stamp_gate_defaults`）。

| ID | 创建/触发 | 人工问题（原文摘要） | 当前自动途径（`auto_gate_mode`） | 消费者动作 | 人工必要性候选 | 交叉 |
|---|---|---|---|---|---|---|
| C-09 | `conductor.py:1148 _create_stage_confirm_gate`、`:1082 _ensure_next_stage_gate`（roadmap 重写后） | "Stage N…确认启动？approve=启动并开始派发；reject=要求重新提案" | `stage-confirm-fact-guard`：**guard only**（结构校验空 + goal sha 绑定）；live 也不会 approve | approved→stage `running`；rejected→重新提案（`_dispatch_roadmap_writer`）；`_consume_answered_gates:910` | 候选 DP 化"提案合法性/目标对齐"判定；启动人审可保留（开放不可逆） | RQ4 |
| C-10 | `conductor.py:1326`（`_create_gate("stage-close")`，全部 key 终态 + dossier） | "确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理" | `stage-close-credentials`（`STAGE_CLOSE_AUTO_RULE_ID`）`auto_action="approve"`，受 shadow 门 + 夜/键配额约束 | approved→`closed` + `_ensure_next_stage_gate`；rejected→`halted` | 候选：连续 5 夜/20 决策后机器可放行**已有**凭证谓词；仍应保留"人可 revoke" | RQ4；与 dp20 交叉（见覆盖表） |
| C-11 | `conductor.py:6367 mark_stalled`→`:6418 _create_gate("stalled")`（轮次/审批/advance 连续失败） | "key 已 stalled（reason）——遗留关闭（closed-legacy），还是人工介入后重试？" | `stalled-false-negative` approve **额外要求** `blocker_class=="paperwork"` + `false_negative_class=="proven-false-negative"`（`auto_decision_for_rule:7027`） | approved→`_apply_stalled_approvals:4146`（stalled→running，一发 resume credit）；rejected→`_apply_stalled_rejections:4215`（→`closed-legacy`，**不可逆**） | 候选：approve 侧已适合先 DP；reject 侧（不可逆关闭）保留人 | RQ4/RQ5 |
| C-12 | `conductor.py:1713`（L2 轮次耗尽且仍有缺口） | "回路已达上限且仍有缺口——追加一轮修复，还是标记 stalled？" | `budget-exhausted-bounded` approve（used==limit+credits 且 gap>0） | 追加轮（`_budget_bonus`/`_resume_credits`）；reject→stall | 候选：先 DP（可逆、纯预算） | RQ4 |
| C-13 | `conductor.py:3812 tick` 内直接 `gates.create("goal-change")`（goal.md mtime 漂移） | "goal.md changed…review the new goal and approve resuming, or reject to stay halted." | `goal-change-normative-guard`：**guard only**（sha 变了且仅规范段变化）；无自动 approve | approve→解 halt/采纳；reject→保持 halt 并报告 | 候选：规范段 diff 判定可 DP，"目标语义变更"保留人（目标锚点属性） | RQ4；与 dp16 语义交叉（已退役，不新增） |
| C-14 | `conductor.py:5142 _xkey_ensure_gate`（跨 key 红修复票据） | "跨 key 红 file::test（owner K）请求解冻授权…" | `xkey-authorize-s4-guard`：**guard only**（重跑绿 + 票据绑定 + 半径在写面内） | approve→`_consume_xkey_gate:5201` 执行受限修复（`--authorizes retry` 语义）；reject→留账本 | 候选：先 DP 判"半径/绑定"；越面写授权仍留人（GC-5 安全约束不改） | RQ5（xkey 深链） |
| C-15 | `conductor.py:4655 reattest_gate`（证据漂移/重判） | 原 kind 的 re-attest（原答案被保留） | 走原 kind 的同一 RULES 规则 | 与原 kind 相同消费者 | 不新增 DP：它是同一事项的新证据版本（AC-011 语义） | RQ4 |
| C-16 | `conductor.py:4026/4319` TTL 常量 | 无问项 | 无自动（48h 后仅"应升级人"的展示/提醒锚点） | 提醒/审查阈值；不改判据 | 候选：TTL 保留为兜底，不 DP 化 | — |
| C-17 | `conductor.py:7027 auto_decision_for_rule`、`:8348 _auto_decide_one`、`:8467 auto_decide_gates` | 每 tick 扫描 pending gate | 由人选择哪些 kind 自动、shadow 观察、配额/熔断 | 写/不写 gate 状态 + `auto-decisions.jsonl` | **候选（结构性）**：把 RULES 的判定改为经 DP（材料/回执/审计复用），消除第二套账本；未批准 | — |
| C-18 | `conductor.py` `AUTO_NIGHT_CAP=6`、`AUTO_KEY_CAP=2`、`AUTO_BURST_*`、`auto-brake.md` | 自动决策过密 | 自动停机 + 记 escalate | 停止本 tick 自动决策 | 不适用（保护阀）；DP 化后应保留同一预算语义 | — |

### C. 框架 phase / L1/L2/L3 / 签收

| ID | 上报面 | 触发 | 人工问题/实际选择 | 当前自动途径 | 消费者动作 | 人工必要性候选 | 交叉 |
|---|---|---|---|---|---|---|---|
| C-19 | `advance_phase.py:52 GATES`、`:380 check_gate`、`:773 main` | 相位推进 | **不请求选择**：`GATE BLOCKED` + 逐项缺失/stderr、exit 1 | 无（硬检查） | 不写 pm-state/index；`done` 另有 `--summary` 必填 | 不适用：**硬拒绝 ≠ 需人选择** | — |
| C-20 | `advance_phase.py:309 _decision_signoff_problems`、`:37 DECISION_SIGNOFF_REL`；`decide_signoff.py:289 collect`/`:452 verdict` | 推进到 `done` 且该 key 有 `kind=decide` 行 | 签收结论 continue|narrow|revoke（人/PM 通过 `mw decide sign` 写机器行） | 无自动；`signoff: disable` 或零决策行才跳过 | 档案 sha 重算防签名后追加；`continue` 还要每行真 jev | 候选：签收保留人（dp25 业务不改）；**不把 stage-close 与之合并** | RQ4/RQ5 |
| C-21 | `.mw/decide.json` `signoff: disable`（`_decision_signoff_disabled`） | 项目配置 | 关掉签收 | 无 DP、无审批 | done 不要求 sign-final.md，仅打印 NOTE | 候选：逃生阀是否保留/收紧需用户裁定（现事实是存在且无决策记录） | RQ5 |
| C-22 | `conductor.py:1565 _record_advance_result`、`:1452 _classify_advance_failure` | `advance()` 非 0（`advance.py:164`，120s 超时→124） | 不请求选择（只写 timeline `class=`）+ 连续失败 `mark_stalled` | 重试→stalled（C-11） | `advance`/`config` 事件；stalled 冻结派发 | 候选：dp7 若保留，应改为消费该分类的结构化材料，见覆盖表 | RQ4 |
| C-23 | `conductor.py:1619 _advance_key`（L1 dossier 缺口）→ L2 verifier 修复轮；L3 写 `l3-verdict.txt` | 相位产物在但证据有 blocking gap | 不请求选择（机器派修复）；超预算才 C-12 | 自动派 phase-writer/verifier（loop `l2:*`） | 修复/判决；预算耗尽→budget gate | 候选：L1/L2 完全 DP 化（可逆、机器可判），人只看预算与 stalled | — |
| C-24 | 阶段质量：`GATES["done"]` 要求 `evidence/quality-gate-report-*.md` + `pm-state` PASS | done | 不请求选择（文件要求）；正式质量审核是 dp6（PM 工具面，RQ4） | 无自动 | advance 放行/拒绝 | dp6 业务不改；autopilot 侧**没有**质量人门 | RQ4 |

### D. dp7 / dp15 / dp20 覆盖表（registry 事实 + 真实对象）

| DP | registry（`decide_registry.json` / `decision_points.py`） | required fields（问项） | 真实对象与材料 | 覆盖判定 |
|---|---|---|---|---|
| dp7-gate-failure | P2，enabled=true，auto，`wired=false`，`executor="unwired"`（`:658`，占位器 `:496` 调用即 raise），无调用者 | `gate.name`、`gate.missing_items[]`、`gate.verdict_age_hours`、`gate.has_config_error`；问 `gate_cause` ∈ missing-evidence/stale-verdict/config/unknown | 真实失败= `advance_phase.py` exit code + stderr 缺失项 + `_classify_advance_failure` 四类（interface-drift/gate-blocked/timeout-env/other）+ 连续失败计数；`verdict_age` 与相位门无关，`missing_items` 未结构化落盘 | **材料不足/字段不对齐 + 动作未接线**：可问（answer 模式可回执），不能推进（executor raise；无消费者） |
| dp15-autopilot-gate | P0，`default_enabled=false`（默认关），auto，`wired=false`，`executor="none"`，无调用者 | `gate.kind` ∈ 6 值（与 `GATE_KINDS` 一致）、`pending_items[]`、`age_minutes`、`evidence_refs[]`；问 `gate_decision` ∈ continue/narrow/revoke | 真实答案= approve/reject（+`--authorizes` 闭集 retry/contract-change）+ note；判据分散在 v2 字段（`blocker_class`、`reason_code`、`verdicts_final`、`goal_sha256`、`blast_radius`/`write_scope`、`default_action`/`expires_at`）与各 kind 的消费动作 | **能表达 kind 名，不能表达判定与动作**：选项值域不对齐（continue/narrow/revoke vs approve/reject，revoke 无实现）；材料不足（无 kind 专属判据、无 authorizes）；动作未接线；六 kind 中 stage-close 与 dp20 重叠 |
| dp20-stage-close | P0，`default_enabled=false`，auto，`wired=false`，`executor="none"`，无调用者 | `stage.id`、`stage.tasks_done`、`stage.tasks_total`、`stage.open_blockers[]`、`stage.evidence_refs[]`；问 `stage_action` ∈ close/hold/rework | 真实闭环材料= 每 key 终态 verdict（meets / closed-legacy）、in-flight worker 行、reconciliation 争议、`stage-N-close.md` dossier、每 key 终期凭证（`proposition_stage_close_credentials`）；另有 `_stage_transition_allowed` 单调性（closed/halted 不可回退） | **材料不足**：tasks 计数不是闭环凭证（AC-010 恰好禁止用它代证）；动作未接线；与 dp15 的 stage-close kind 同一事项双归属 |

补充（只核必要交叉，业务不改）：dp2/dp3（PM 分拆/澄清，RQ4）、dp6（正式质量审核，RQ4）、dp25（key 决策签收，C-20）与上述三 DP **不共用证据版本/回执**；dp20 与 dp25 是不同对象（stage roadmap vs key 决策档案），不可合并签收；dp15 的 `revoke` 与 `auto-decisions.jsonl` 的 `revoke` phase 同名但无代码关联。

## 残留与未验证

- 全文阅读范围：`gate-writer.ts`(全)、`console.ts`(全)、`advance.py`(全)、`advance_phase.py`(全)、`decision_points.py`(dp1/7/8/9/15/16-25 段 + 注册/executor 段)、`decide_registry.json`(三 DP 条目)、`gates.py`(头 195 行 + 关键定义)、`mw.py`(autopilot 子命令段)。
- 部分阅读（未全文）：`conductor.py`(8727 行；读过 gate 创建/消费、auto 规则/预算、advance 失败、stalled、stage-close、xkey gate、reattest、answer 路径；其余 7600+ 行未读)、`monitor.ts`/`status-model.ts`(只读相关符号与注释)、`pm-orchestrator.ts`(228-345、2368 附近)、`closure.py`(未读)、`gates.py` 其余(create/parse 细节未读)、`xkey.py`(未读)。
- 未验证：`shadow_gate_allows` 是否已满足 5 夜/20 决策（不读生产 ledger）；`auto-decisions.jsonl` 实际分布；stage-close 凭证谓词在生产通过率；`--authorizes retry` 与 `_consume_xkey_gate` 的强制关系（未核 xkey.py）；dp15 的 `revoke` 是否曾有实现；PM 手工跑 `advance_phase.py` 与 conductor 路径是否完全等价；`reattest_gate` 的真实触发频率。
- 未运行任何测试/框架命令/共享服务/build/install/commit，未调用决策服务或 provider，未读写凭证/活 gate/活 ledger，未改源码。
- 未裁决事项：dp15 与 dp20 的 stage-close 双归属、dp7 是保留还是并入 gate 平面、`signoff: disable` 是否保留——均属联合设计/用户裁定，本文件不预设结论。

## 上下文来源

- `.agenticdoc/goal.md:5`（目标锚点）、`.agenticdoc/mw-dp-consolidation/spec.md`（§1.1 保留集合、§2 约束、AC-007/009/010/011）、`evidence/autopilot-three-dp-discussion.md`、`evidence/research/spec-confirmed-intent-20261024.md`（经 spec 引用）。
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`（:169 `answerGate`，:115 `rewriteAnswerFields`，`AUTHORIZES_ACTIONS` 闭集）。
- `.../autopilot/console.ts`（:181 `cmdStatus`、:198 `GATE_ACTIONS`、:350 `renderGateCards`、:448 `cmdGates`、:457 `cmdGate`、:586 `cmdSetEnabled`、:638 `cmdSetPaused`、`USAGE`）。
- `.../pm/pm-orchestrator.ts`（:228-345 阶段证据提醒/接管、:2368 gate 提醒）、`:1895+` gate-reminder session 协议。
- `packages/multi-workers/mw.py`（:12267-12300 `autopilot gates` / `autopilot answer`）。
- `packages/multi-workers/autopilot/advance.py`（:119 `locate_platform_dir`、:164 `advance`、:36 超时）。
- `.agents/skills/agentic-task/scripts/advance_phase.py`（:37 签收路径、:52 `GATES`、:309 `_decision_signoff_problems`、:380 `check_gate`、:486 `update_pm_state`、:773 `main`）。
- `packages/multi-workers/autopilot/conductor.py`（:910 `_consume_answered_gates`、:1065/1148 stage-confirm、:1326 stage-close、:1452 分类、:1565 `_record_advance_result`、:1619 `_advance_key`、:1713 budget gate、:3812 goal-change、:3903 `_create_gate`、:4026/4319 默认值与 TTL、:4146/4215 stalled 消费、:4655 reattest、:5142 xkey gate、:5201 `_consume_xkey_gate`、:6367/6418 stalled、:6880-7050 RULES/`auto_decision_for_rule`、:7365 `blocker_class_of`、:7981 `answer_gate_confirmed`、:8348 `_auto_decide_one`、:8467 `auto_decide_gates`）。
- `packages/multi-workers/autopilot/gates.py`（:82 `GATE_KINDS`、:130+ `FRONTMATTER_FIELDS`、`_REQUIRED_FIELDS`、`blocker_class` 扩展字段）。
- `packages/multi-workers/autopilot/config.py:102/123`（`auto_gate_mode` 默认 off 与枚举）、`status-model.ts:111/152/196`（TS 镜像）。
- `packages/multi-workers/decision_points.py`（:496 `_unwired_executor`、:658 dp7、:768 dp15、:811 dp20）、`packages/multi-workers/decide_registry.json`（三 DP 条目：tier/wired/executor/required_state_fields/questions）。
- `packages/multi-workers/decide_signoff.py:289 collect`、`:452 verdict`（签收机器行重算）。
