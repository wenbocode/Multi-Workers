# RQ13 — 八入口注册/业务材料/backend 协议与历史分层取证

- Key: mw-dp-consolidation（本 key DESIGN，联合设计/实施未批准）；时间盒 25 分钟只读；未跑测试/build/服务/裁决/provider 探针。
- 只读面：spec.md 全文、graduation-pm-review-20261025.md 全文、decide_registry.json 全文、decision_points.py 主要结构（见“未全文读”）、decision.py/decision_backends.py/decision_wire.py 定点段、decision-tool.ts 常量与两侧契约测试。
- 本文只给现状/目标/建议三段分离的取证，不宣称 SPEC/AC/QG/设计/签收通过，不冻结任何 schema。

## 结论

**A. 现状（事实）**
1. 运行期可调用集合由 `decision_points.DP_REGISTRY` 单表决定：25 条 `_point(...)`（`packages/multi-workers/decision_points.py:540-889`），导入期 `EXPECTED_DP_COUNT = 25`（`:191`）+ `_validate_registry`（`:892-905`）强制条数与唯一 id；`get_decision_point` 对未注册 id 抛 `DecisionInputError`（`:908-913`）。因此“AC-001 可调用集合精确等于八名”在本设计里等价于“这张表恰好八行 + 旧 id 走明确拒绝路径”。
2. 该表单源派生出两份机器可读副本：`decide_registry.json`（`"generated_from": "decision_points.DP_REGISTRY"`，schema 3，`decide_registry.json:2-3`，25 条 id 位于 `:12,66,135,199,271,344,419,488,581,649,720,789,856,930,1000,1079,1145,1212,1278,1354,1431,1493,1561,1624,1699`）与 TS `shared/decide-registry.generated.ts`（`"dp1-dispatch-type": {` 起 `:37`，25 条）。两者分别由 `mw decide dp export --write` 与 `scripts/gen_decide_registry_ts.py` 生成，并有字节级漂移锁（`test_decide_registry_export.py:2-22`、`test_decide_registry_ts_lock.py:1-40`）。
3. 但工具面存在第三份**手写**清单：`ASK_DECISION_DP_IDS`（`pm/decision-tool.ts:132-158`，25 条硬编码）+ `ASK_DECISION_ENFORCED_STATE_DP_IDS`（`:169-174`）+ `ASK_DECISION_PM_ONLY_DP_IDS`（`:214`）+ `ASK_DECISION_MATERIAL_DP_IDS`（`:219-223`）+ dp3 专用常量（`:226-229`）。它只靠测试用**源码正则**与 Python 对齐（`packages/coding-agent/test/suite/decision-tool.test.ts:774-779`：`_point(\s*dp_id="` 匹配出 25 条），不是生成物。
4. 业务 material / 本地 identity / meta 隔离已有一套机制，但只覆盖四个 dp：`STATE_IDENTITY_PATHS`（`decision_points.py:1497-1501`）写 `schema_version/decision_point/questions_version`；`AUDIT_STATE_PATHS`（`:2472`）只放 `key/task_key/trigger_id` 且永不投影；`MODEL_STATE_FIELDS` 白名单只声明 dp1/dp2/dp3/dp25（`:2437-2470`），其余 21 个 dp 由 `model_state_for` 原样发送（`:2980-3005`，docstring 明说 “other 21 dps ... shallow copy”）。其余每个 dp 的必填事实集中在 `REQUIRED_STATE_FIELDS`（`:1522-…`）、类型/枚举/上限在 `STATE_FIELD_DESCRIPTIONS`（`:1710-…`）、跨字段事实在 `STATE_FIELD_CROSS_CHECKS`（`:2491-2515`）。
5. 选择校验现状：答案必须是已注册 qid 且值落在该 q 的合法枚举，否则 `low-confidence` 升级（`_unusable_answer` `:4439-4470`，`_value_fits` `:4411-4437`）；动态枚举由 state 渲染（dp3 `handling_options`），渲染失败即 `input-incomplete`（`:1152-1205`）；缺失必填/类型/闭集违规在 `_decide_for` step 5/5b 全量拒绝且零发送（`:5250-5310`），未知 dp 抛错、禁用→`disabled`、传输关闭/不可用→`unavailable`、超预算→`input-oversize`、无 executor/执行器抛错→`over-authority`（`:5063-…`，步骤注释 `:4958-5020`）。
6. backend 面只有一个传输实现：`TimiDecisionsBackend`，`name = DECISIONS_TRANSPORT`（`decision_backends.py:792-800`，常量 `:134`），`confidence_source=api`；`DecisionClient._backend_name` 只是读取 `name`/`cfg.transport`，缺省 `"none"`（`decision.py:2015-2023`），`REASON_CODES` 七值闭集（`decision.py:123-155`）。即 “backend 校验/名称” 目前没有 dp 维度，dp id 只用于请求/证据行标注（`decision.py:2082-2112` 的 `_emit(dp=...)`）。
7. 历史面：archive/wire 有各自闭集与版本（`decision_wire.py:104` `SCHEMA_VERSION=1`、`:181-256` `_KIND_FIELDS`/`EVENT_KINDS`、`:121` `SCOPE_KINDS`），原始行形状不改的设计意图明确（`decision_wire.py:1-12`）。旧 id 在多个消费者里被硬编码：`decision_monitor.py:210-212`（dp2/dp3/dp25→文件名）、`decision_book.py:113-114`、`decide_book_template.json:3-8`、`decide_cases/dp{1,2,3,25}.json`、`mw.py:3139-3160`（每 dp 探针值）、`mw.py:3829`（按 dp3 统计）、`mw.py:12752`（`mw decide book new dp3-worker-clarify` 帮助串）、`decision_context.py:110`（`error_excerpt` producers 含 dp7）。

**B. 目标要求（spec 已确认，非实现）**
1. 目标可调用八名：dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route（`spec.md:20-33`，`:86-87`）；六迁移=dp1/dp2/dp3/dp6/dp15/dp25，19 项退出独立职责（含 dp7 交 dp-auto、dp20 关闭 gate 交 dp-gate-approve 承接但 id 退出），无旧编号运行别名（`spec.md:34-36`，毕业考勘误 1 见 `graduation-pm-review-20261025.md`）。
2. dp-w-type 候选固定 coding/research/review/vision 且 vision 需图像能力门禁，不移除 rag-research/decide_prepare 等既有框架类型（`spec.md:39`、AC-044 `spec.md:176`）。
3. dp-pm-steer 四 ID 不变、语义细化（narrow 不降目标/验收，split 独立单元并行，direct-exec 依赖当前 PM 上下文，escalate 给具体人工必要性与问题）（`spec.md:40`、AC-045）。
4. dp-w-check-task 三固定选项、fire-and-forget 自主到终态、不以“上报 PM 等待”为选项，补证须有结束判据（`spec.md:41`、AC-046/047）；原 dp3 的 2～5/c1..cN 动态候选不再作为本 key 目标合同。
5. dp-QG 保持 pass/fix/reopen 三业务选项与可复核依据/缺口/未覆盖面要求（`spec.md:42`、AC-005/053），不改目标/验收、不派返工、不代签收。
6. dp-gate-approve 四选项 approve/steer/need_fix/reject + 送审前 PM 预拟 note（审批事项、批准后动作、目标/证据/预算/授权依据）与模型理由分开保存（`spec.md:49`、AC-007），并承接 dp20 阶段关闭条件（`spec.md:60`、AC-010）。
7. dp-sign-key 保持 mw-decision-context 四部材料与 finalize/continue/user-confirm；`verified/unverified/unfinished_impact` 为数组、`[]` 表真实无、缺项不能变 null（`spec.md:38`、AC-004、AC-051、毕业考勘误 6）。
8. dp-auto：PM 准备可区分候选→只从候选里选并给理由/关键依据，不临时造方案；**不沿用旧 dp3 的 2..5/c1..cN/label80 限制**，不代固定 DP/不降目标/豁免硬门；材料非法、服务不可用、无有效选择属调用失败/阻塞而非业务选项（`spec.md:80`、AC-042、毕业考勘误 5）。
9. dp-route：只在其余七入口中选，选择与依据可见，业务结论/动作不得由路由推断，固定节点直调不强制加路由，角色不因路由变更（`spec.md:82-85`、AC-040/041）。
10. 八入口统一需明确触发/材料/选项/结论/实际动作/失败与不可用/有效性边界（`spec.md:118-120`），全局失败防御 AC-012、去重 AC-011、历史只读 AC-013、跨语言链 AC-014、动作/快照/幂等 AC-050～052。

**C. 方案建议（设计输入，未获授权）**
1. 注册与 schema 单一事实源：建议 **方案 C = “八行活动表 + 只读退役映射”**（详见证据 §5），而不是保留 25 行加过滤位。理由：现状权威点就是“表即集合”，八行表让 AC-001/002 可直接观测；退役映射只做拒绝+历史解释，天然不构成运行别名。附带要求：工具枚举改为由快照生成（消除 `decision-tool.ts:132` 手写清单这一第二事实源），并把 dp3 专用动态限制绑定到“该 dp 的机制”而不是全局常量。
2. 业务 material/identity/meta：建议八入口全部显式声明模型白名单（沿用 `MODEL_STATE_FIELDS` 机制，不新造 schema），identity 与 `key/task_key/trigger_id` 恒本地；`context` 块继续只作为可选工程输入。
3. 选择校验与失败分类：建议复用既有七值 `escalated_reason` 与 `input-incomplete` 路径，不新增 outcome/reason 词表；旧 id 拒绝与 route 无匹配走**材料/输入侧**拒绝（附闭集 detail），不把失败包装成业务选项。
4. 硬约束提醒（设计必须处理，不是建议）：`DYNAMIC_CHOICES_MAX = 5`（`decision_points.py:1110`）与 dp-route 的 7 个目标冲突；若沿用 `dynamic_choices` 实现 dp-route 或 dp-auto，会连带继承 1..5/c1..cN/label≤80/≥2 且 label 互异/必须带 description 的规则（`:1117-1150`、`STATE_FIELD_CROSS_CHECKS` dp3 规则 `:2511-2514`），与 AC-042 明确冲突。

**D. 授权未定**
具体字段名/枚举/schema、技术 ID、role 资格矩阵、gate 状态转换、消费者与写面均**未定**；本 RQ 只给候选与断言建议，不扩大角色权限、不造授权/预算、不恢复旧入口。

## 证据

### §1 现存八名对应的现状行（每项：现状 → 目标差异）
| 目标名 | 现状行 | 现状可核事实 | 目标差异（spec） |
|---|---|---|---|
| dp-w-type | dp1（`decide_registry.json:12-65`；`decision_points.py:575-593`） | P2/auto/enabled，`wired=true`（trigger `pm/ui-bridge.ts:1730`，adopted `:281`），executor=`unwired`；单选 `triage_type` 三枚举 coding/research/review；必填 task_goal/requirements/deliverables；有模型白名单 | 增 vision（四固定）；图像能力门禁；不得移除 rag-research/decide_prepare 等框架类型（AC-044） |
| dp-pm-steer | dp2（`decide_registry.json:66-134`；`decision_points.py:594-612`） | P2/auto/wired（`pm/pm-orchestrator.ts:2602`/`:2620`），executor unwired；四枚举 narrow/split/direct-exec/escalate；可选 `worker_execution`（`OPTIONAL_STATE_FIELDS` `decision_points.py:2424-2431`） | ID 不变、语义细化；PM 角色；真实执行须协调在途任务/写面（AC-045） |
| dp-w-check-task | dp3（`decide_registry.json:135-198`；`decision_points.py:614-626`） | P2/auto/wired（`worker/worker-mode.ts:3903`/`:3753`）；**动态** `dynamic_choices: handling_options`；≥2 候选、c1..cN 连续、≤5、label≤80、description 必填且 label 互异（`decision_points.py:1117-1150`,`:2491-2515`）；必填 question+四项 background+handling_options | 三固定业务选项（继续/终止/有界补证），取消“上报等待”；技术终态映射留设计（AC-046/047） |
| dp-QG | dp6（`decide_registry.json:344-418`） | P1/disabled/未接线/executor=None；pass/fix/reopen；必填 `qg.checks_total/checks_failed/blocking/scope` + 跨字段 checks_failed≤total | 语义扩为正式审核（依据/缺口/未覆盖面）；不得机器通过即正式通过（AC-005/053） |
| dp-gate-approve | dp15（`decide_registry.json:1000-1078`）+ dp20（`:1354-1430`） | 两者皆 P0/disabled/未接线/executor=None；dp15 三枚举 continue/narrow/revoke + `gate.kind` 六值枚举（stage-confirm/stage-close/stalled/budget-exhausted/goal-change/xkey-authorize，`decision_points.py:1507-1514`）；dp20 close/hold/rework + stage.* | 四选项 approve/steer/need_fix/reject + 预拟 note；承接阶段关闭（AC-007/010）；H01–H13 十三事项不能只用六类 gate.kind 表达 |
| dp-sign-key | dp25（`decide_registry.json:1699-1771`） | P2/auto；executor=`wired` 但无 TS 调用点，唯一入口 `mw decide sign`（wiring_note）；四部材料 + `empty_is_value: true`（required 表 `decision_points.py:1695-1708`，模型白名单 `:2459-2466`） | 业务合同不变；`[]`≠null；finalize 由 CLI 写签收、无第二次 PM 批准（AC-038/051） |
| dp-auto | 无行；材料侧承接 dp7（`decide_registry.json:419-487`：gate.name/missing_items/verdict_age_hours/has_config_error） | dp7 现为 P2/未接线/executor unwired | 新增，候选由 PM 现场准备，不套 dp3 数量/ID 限制（AC-009/042） |
| dp-route | 无行 | — | 新增，七目标、选择可见、不代业务结论（AC-040/041）；7>DYNAMIC_CHOICES_MAX=5 |

### §2 material/identity/meta 与选择校验（现存可复用 vs 缺口）
- 可复用：身份三键与审计三键分离（`:1497-1501`,`:2472`）；闭集键校验（`state_unknown_key_issues` `:2778-2836`）；类型/枚举/上限/跨字段（`state_field_issues` `:2683-2706`）；发送前单次投影+预算裁剪（`send_state`，step 6 `:5355` 调用处）；答案值与闭集校验（`_value_fits`/`_unusable_answer`）。
- 缺口：八入口里 dp-QG（dp6）、dp-gate-approve（dp15/dp20）、dp-auto、dp-route 都**没有** `MODEL_STATE_FIELDS` 白名单，identity 会随 state 一起送模型（`model_state_for:2980-3005`）；dp-gate-approve 需要“PM note 与模型理由分开保存”，现状 `state` 无此分列（archived row 只有 `note` 与 `answer`，`decision.py:2082-2112`）；`empty_is_value` 现状语义正确（`_is_blank` 只判 `None`/空串，`:3007-3011`，`[]` 合法）。
- 失败/不可用现状：见结论 A5；ask_decision 侧把 Python 结果映射为 `reason`+`missing_fields` 且零业务动作（`decision-tool.ts:317-325`, `:1-20` 头注释），角色拒绝为 `role-forbidden`（`:232`）。

### §3 backend/传输面
- 单传输 `timi-decisions`（`decision_backends.py:792-800`，常量 `:134`）；问题构造按 type（noul/choice/score）注入 `instructions` 与 criteria（`:633-706`）；动态候选缺失即 `missing_fields=[...]`（`:719-740`）；`REASON_CODES` 七值（`decision.py:141-155`）。
- 结论：backend 层与 dp 名解耦，注册改名**不需要**改 backend 协议；需要改的是“dp id → 证据行/账本/监控映射”的下游字符串（见 §4）。

### §4 退役/历史分层现状
- 历史只读能力已存在（wire/archive 独立 schema 与闭集，见 A7），但“按旧 id 读取历史”的消费者是硬编码表：`decision_monitor.py:210-212`、`decision_book.py:113-114`、`decide_cases/*.json`、`mw.py:3139-3160`,`:3829`,`:12752`、`decision_context.py:110`。
- 现状无“退役”概念：未注册 id 一律 `DecisionInputError`（`decision_points.py:908-913`），无法区分“拼错”和“已退役”，AC-002 需要的“明确拒绝 + 历史仍可解释”目前无载体。

### §5 方案对比（注册/schema 单一事实源 + Python/TS 同步）
| 方案 | 做法 | pros（有证据） | cons |
|---|---|---|---|
| A 25 行保留 + `status` 过滤 | 原表加 `status: active|retired`，运行前过滤 | 漂移锁/生成链零改动（A2） | `EXPECTED_DP_COUNT`/`_validate_registry` 语义要重写（`:191`,`:892`）；“可调用集合=8”需第二处过滤权威；retired 行重新启用无机械闸；空问题集与 `questions_version` 哈希语义未定（`_questions_version:404-421`） |
| B 八行活动表 + 独立历史映射 | `DP_REGISTRY` 只留 8 条；另设只读 `RETIRED_DP_IDS`（id→承接名/说明）仅用于拒绝与历史解释 | AC-001/002/003 可直接观测（表=集合，拒绝路径单一）；无过滤权威；历史映射天然非运行别名 | 二十五条 pin 的测试/导出必须同步迁移（`test_decide_registry_export.py`、`decision-tool.test.ts:774-779`）；两表存在被误当双权威的风险 |
| **C=B + 生成枚举（推荐）** | 在 B 上把 `ASK_DECISION_DP_IDS` 改为快照生成，dp3 动态限制绑定到 dp 名而非全局常量 | 消除唯一手写清单（`decision-tool.ts:132`），继承既有字节锁（A2）；AC-001/002 可机械核；dp-auto 不继承 2..5 有结构保证 | 需要一次生成器/锁改造；`DYNAMIC_CHOICES_MAX=5` 与 7 目标冲突必须显式解决（C4） |

（备选是否给“退役 id 说明文本”入工具 schema 属细节，不在本文冻结。）

### §6 下游候选文件与建议断言
候选写面（仅定位，未审计全仓）：`decision_points.py`（`:191`,`:540-889`,`:892-913`,`:1110-1205`,`:1522`,`:1710`,`:2424-2515`,`:2980-3005`）、`decide_registry.json`、`scripts/gen_decide_registry_ts.py`、`shared/decide-registry.generated.ts`、`pm/decision-tool.ts:132-234`、wiring 行 `pm/ui-bridge.ts:1730/281`、`pm/pm-orchestrator.ts:2602/2620`、`worker/worker-mode.ts:3903/3753`、`mw.py:3139-3160/3829/12752`、`decision_monitor.py:210-212`、`decision_book.py:113-114`、`decide_book_template.json`、`decide_cases/*.json`、`decision_context.py:110`；测试锁 `test_decide_registry_{export,contract,ts_lock}.py`、`decision-tool.test.ts:774-790`。
建议断言（只给判定骨架，不用测试数量代证）：
- **L0（契约/静态，覆盖 AC-001～003、044、051）**：活动注册 id 集合 == 八精确名；退役映射不参与可调用集合；工具 schema 枚举 == 快照（生成物相等）；dp-w-type 枚举四值；dp-sign-key 三数组 `empty_is_value` 且 `None` 仍拒绝；dp-auto/dp-route 无 cN/≤5 结构约束。
- **L1（路径，覆盖 AC-002、011、012、040、043）**：旧 id 请求 → 明确拒绝（闭集 detail 区分退役/未知），传输调用 0、业务动作 0、历史字节不变；八入口分别构造 材料非法/缺失/服务不可用/无有效选择 → 阻塞且零业务动作；route 选择与固定直调产生不同 decision_id 且 route 侧零业务放行；同对象同证据版本重放不新增同事项审批。
- **L2（生产路径隔离，覆盖 AC-013、014、041、042、050、052）**：每入口一次生产 producer→writer→consumer→projection 隔离运行；dp-auto 选择 ⊆ 已准备候选 id；执行/结算与任务前后快照可关联，未执行回合不伪造 executed；并发/双 Worker 同文件写为 0。

## 残留与未验证
1. 未全文读：`decision.py`（2023 行，只读 `:1916-2112` 输入校验/后端/emit 与常量区）、`decision_points.py`（5312 行，只读注册表、契约表、动态候选、decide_for 全流程）、`decision_wire.py`（1838 行，只读头注释与闭集常量）、`decision_backends.py`（只读 `:620-850`）、`decision_book.py`/`decide_archive.py`/`decision_monitor.py`/`decide_signoff.py`（仅 grep 定位）；因此不宣称“全入口/全消费者已审计”。
2. 未核 TS 实现（仅常量与测试），未核 dashboard/playground/case UI 可提交面是否另有旧 id 枚举；未核 `.mw/decide-points.json` 活配置、gate 文件、ledger、凭证（按任务书禁读）；未运行任何测试。
3. 未核 `decide_signoff.py:390` docstring 仍写 “continue|narrow|revoke”（与 dp25 实际 finalize/continue/user-confirm 不一致）是纯注释漂移还是另有消费路径 —— 留 RQ17 与设计阶段。
4. dp-auto「不套 2..5」与 dp-route「七目标 > 动态上限 5」的具体技术机制（静态枚举 vs 新动态机制 vs 放宽上限）未定，需联合设计批准；本文不选型冻结。
5. 未定：精确 schema/字段名/技术 ID、role 资格矩阵（勘误 3 明确不能从现状 PM-only 集合反推）、gate 状态转换与消费、写面与门禁批准；本轮不做实现、不删源码/配置。

## 上下文来源
- `.agenticdoc/goal.md:5`（项目目标锚点）。
- `.agenticdoc/mw-dp-consolidation/spec.md:1`（用户已确认 53AC，锁定 2026-10-25T23:37:14+08:00；`§1.1:20-36`、`§1.2:38-62`、`§1.3:67-71`、`§1.5:78-88`、`§1.6:98-110`、`§2:118-120`、`§3:121-179`、`§4:181-…`）。
- `.agenticdoc/mw-dp-consolidation/evidence/graduation-pm-review-20261025.md`（PM 毕业考勘误 1–14；本次按勘误 1/3/5/6/7 约束边界）。
- `.agenticdoc/mw-dp-consolidation/evidence/design-parallel-analysis-20261026.md`（RQ13 唯一边界：注册/材料/backend 协议/名称/历史分层；不代 RQ14–17）。
- `.agenticdoc/mw-dp-consolidation/tasks/RQ13-design-entry-contracts.md`（任务书与写面）。
- 源码证据：`packages/multi-workers/{decision_points.py,decide_registry.json,decision.py,decision_backends.py,decision_wire.py,mw.py,decision_context.py,decision_monitor.py,decision_book.py,decide_cases/*,scripts/gen_decide_registry_ts.py}`、`packages/coding-agent/src/extensions/agent-team-loop/{shared/decide-registry.generated.ts,pm/decision-tool.ts}`、`packages/coding-agent/test/suite/decision-tool.test.ts`（行号见各节）。
