# 四DP简洁输入契约与真实输入producer（RQ-D1，只读设计研究）

> key mw-decision-context；时点 2026-10-22，HEAD 54f194d69 + 工作树未提交改动。
> 标记：**[事实]**=源码可核（给 path:line）；**[建议]**=候选，未获用户确认；**[未决]**=需人裁决或未核实。
> 未做：真实模型调用、HTTP 抓包、服务起停、安装/测试、凭证读取、任何源码写。行号随工作树可能漂移。
> 上游：`spec.md:1` AC001–007/020；`evidence/research/spec-dispatch-midflight-20261022.md`、`spec-clarify-signoff-20261022.md`。
> 范围：只做四DP契约与输入producer；反馈存储/签收/UI 归 RQ2/RQ3。

## 1 结论先行（给PM）

1. 四DP现在**没有**“简洁输入”契约：dp1 发 13 必填+2可选（含 `authority_tier/phase/risk_source/requested_type`），dp2 只发机器计数、无自评原文，dp3 同一问题原文重 3 份且 `harnessDetail` 从未发送，dp25 只发计数。[事实]
2. 身份/审计键**不是producer能单方面删掉的**：`_state_builder` 无条件注入 `schema_version/decision_point/key/task_key/questions_version`（`decision_points.py:443-465`），`STATE_IDENTITY_PATHS` 始终合法（`:1231-1235`, `:2413`）。要满足 AC-002 必须有**一个发送前投影缝**，否则只能改 Python 注入逻辑。[事实+推断]
3. dp2 自评有真实来源（worker 自己写的 `CKPT <n>m converging=…` 行）但**PM 侧今天没有 reader**：`progress.md` 不在 `readDp2ArtifactStatus` 的期望清单内（`pm-orchestrator.ts:2210`），state 里也没有对应键。[事实]
4. dp3 的“PM→用户”路径**不存在 producer**：`ask_decision` 只在 worker 分支注册（`index.ts:84-90`），PM 提问是自由文本。[事实]
5. 推荐：**业务字段走 registry 契约收紧 + 身份/审计字段走单一发送投影**（§6 方案C），机器选项值改名会改 `questions_version` 哈希，必须同步 TS 镜像常量（§3）。

## 2 四DP契约与producer现状（事实表）

| DP | 注册问题（`decision_points.py`） | 必填字段（`REQUIRED_STATE_FIELDS`） | 生产入口 | 消费点 |
|---|---|---|---|---|
| dp1 | `triage_type`(coding/research/review，3条label) + `triage_risk`(low/mid/high)（`:546-572`） | 13：`schema_version,decision_point,key,phase,task_type,requested_type,risk,risk_source,authority_tier,task_summary,questions_version,scope.write_scope,scope.file_extensions`（`:1258-1271`） | `ui-bridge.ts:529-582 buildDp1DispatchState`，调用点 `:1835-1847` | `triage-client.ts:915-922`（`triage_type`）、`ui-bridge.ts:292-294`（acted 门槛）、`:628`（disagreement） |
| dp2 | `checkpoint_action`(narrow/split/direct-exec/escalate)（`:576-592`） | 14：同上通用9 + `progress.elapsed_minutes,budget_minutes,phases_done,phases_total,artifact_present`（`:1273-1287`） | `pm-orchestrator.ts:2137-2200 buildDp2CheckpointState` ← `:2336 decideDp2Checkpoint` ← 轮询 `:2669-2690` | `:2413-2422` 值→action 闭合映射、`:2430 acted`、`writeDp2SteerRequest :2438+` |
| dp3 | `answer_kind`(fact/intent/reuse) + `answerable`(noul) + `candidate`(dynamic，`:596-627`） | 13：通用9 + `key,task_summary,ambiguity.kind,ambiguity.question,local_candidates`（`:1289-1303`） | `worker-mode.ts:5570-5616 buildDp3State` ← `:5652 decideDp3WorkerClarify` ← `:4156 attemptDp3Clarification` | `:5760-5820`：`answer_kind` 为第一判据，`answerable` 概率门，`candidate` 选本地候选，答案文本取自本地文件（`:5539-5558`） |
| dp25 | `q-conclusion`(continue/narrow/revoke)（`:863-892`） | 5：`key,rows_total,rows_available,chain_ok,p0_open`（`:1458-1464`）；可选 `rows_escalated,escalated_reasons,engine_violations`（`:2126-2131`） | `decide_signoff.py:340-380 signoff_state` ← `:381-430 auto_conclusion` ← `mw decide sign` | `decide_signoff.py:449-491 verdict`（本地复判）、`mw decide sign` 写签收文件 |

共同事实：
- 模型侧提问 = registry 的 `questions` 渲染（`decision_backends.py:803-843`）；请求体恰 `{model,state,questions}`（`:845-860`），`state` 原样透传，Python 不二次裁剪。
- 门：必填缺失→`input-incomplete`（`:4783-4801`）；类型/枚举/闭键集→`input-incomplete`（`:4807-4840`）；>2000B 两阶段裁剪后仍超→`input-oversize`（`:4859-4874`，`MAX_STATE_BYTES=2000` `:145`）。
- 裁剪顺序：`context` 先按预算拟合（`:2646-2664`）→ 丢 `OPTIONAL_STATE_PATHS`（`:2136-2141`）→ 半分 `TRUNCATABLE_STATE_PATHS=("task_summary","ambiguity.question")`（`:2144`）。
- 动态选项形状冻结：`{id:"c1".."c5", label: 单行 ≤80 字符}`，id 必须连续（`:1102-1139`），label 是模型唯一能看到的候选说明；`questions_version` 只哈希 `id/type/choices/dynamic_choices`（`:376-390`），**不含 label 文本**。
- `context` 只接受 5 个槽：`task_excerpt(1200)/change_summary(800)/candidate_snippets(5×200)/artifact_status(24)/error_excerpt(1500)`，按 dp 白名单（`decision_context.py:55-109`）。

## 3 机器选项标签建议（**建议**，含哈希代价）

| DP | 新机器值 | 中文 label（固定说明，随问题发送） | 影响 |
|---|---|---|---|
| dp1 | `coding` / `research` / `review` 不变 | 需要写代码或改代码或跑命令 / 只做检索取证不改代码 / 审计别人已完成的产出 | 删 `triage_risk` **仍改版本**（哈希含整张问题表）→ 新 `q-*`，需改 TS 镜像 `triage-client.ts:93-113 DP1_QUESTIONS` |
| dp2 | `continue` / `narrow` / `split` / `handback` | 继续执行 / 收窄任务 / 拆分任务 / 交回PM | 改 `choices` → 新 `q-*`，必须同步 `pm-orchestrator.ts:1986-1999 DP2_QUESTIONS_CANONICAL` 与 `:2413-2422` 映射；`direct-exec` 退役，`handback` 不自动终止/不PM直执 |
| dp3 | 单问 `handling`，`dynamic_choices` → 状态键（如 `handling_options`） | 候选由提问Agent生成：label = `选项名：一句说明`（≤80字符） | 删 `answer_kind/answerable` → 新 `q-*`；`local_candidates` 语义改变（见 §6 建议改名） |
| dp25 | `finalize` / `continue` / `user-confirm` | 可以收尾 / 继续完成 / 交用户确认 | 改 `choices` → 新 `q-*`；签收词表 `decide_signoff.py:82 CONCLUSIONS`、`verdict :449-491`、`mw decide sign` 与 `ui-bridge.ts:4762 CONCLUSION_LINE` 需同步（**RQ2 所有者确认**） |

原则：机器值是契约（进哈希），中文说明是文案（不进哈希）；旧标签语义不同（`revoke`=撤签、`narrow`=降级），不做历史重映射，旧档案只读不改写。

## 4 简洁输入（**建议**字段草案，未确认）

共享路径（`STATE_FIELD_DESCRIPTIONS` 为全局表，同名路径必须同 spec，`decision_points.py:2457-2516` 导入期校验）：

| 字段 | 类型/上限 | 内容来源（原文优先） |
|---|---|---|
| `task_goal` | string ≤400B | 卡片 `## 上下文` 目标段原文 |
| `task_requirements` | string ≤700B | 卡片 `## 要求` 原文 |
| `deliverables` | string ≤400B | 卡片 `## 交付格式`/`## 唯一证据文件` 原文（无则显式 `未知：卡片无交付物段`） |

dp1：`task_goal + task_requirements + deliverables`，问题仅 `dispatch_type`（§3）。**不传** `task_type/risk/risk_source/requested_type/scope.*`。[建议]
dp2：`task_goal + task_requirements + deliverables`（同 dp1 三字段，来自 `task.md`）+ `worker_self_assessment`（string ≤600B，**worker 原文**：`CKPT …` 行 + `## 完成记录` 尾段）+ 复用 `progress.elapsed_minutes/budget_minutes`（已有类型/生产/消费）；`anomaly`（object，可选，仅明显异常时附 1–2 个机器计数）。删除 `progress.phases_done/phases_total/artifact_present/writes/uniq_targets/repeat_top/trend` 与 `context.change_summary`/`artifact_status` 的默认发送。[建议]
dp3：`question`（string ≤300B，**仅 1 份**）+ `background.{goal,current_state,why,constraints}`（4×string ≤160B，由提问Agent生成；未知写 `未知：…`，不得填事实）+ `handling_options`（`{id,label}` ≤5，label 含说明）。删除 `ambiguity.*`、`task_summary` 重复、`answer_kind`、`answerable`。[建议]
dp25：`delivery_goal/completion/verified_evidence/unverified_items/unfinished_impact`（5×string ≤350B，PM 生成，已验证/未验证分列）。链/计数等本地硬门事实**不进模型材料**（AC-007 不以计数作结论；硬门集合归 RQ2）。[建议]

字节预算提示：2000B 含 JSON 开销；中文 1 字≈3B，dp3 的 4 段+4 选项约 1500–1900B。**超预算必须 `input-oversize` 拒绝（零发送），不得静默裁剪某一段**（AC-020）；是否放宽 dp3 上限由 RQ3 用真实样例定边界。[建议+未决]

## 5 固定生成提示（**建议**，文案可进代码常量/工具描述）

dp3 背景与候选（发给提问Agent，Worker 与 PM 同一份）：
```
先给出你的问题原文；再按四段写背景：目标（这条任务要达成什么）/现状（已确认的事实、已试过什么）/为什么需要决策（卡在哪）/约束与影响（预算、写面、下游）。未知就写「未知：…」，不要编造。
然后针对该问题给 1–5 个互不相同的处理候选，每个写成「选项名：一句说明」，说明代价或后果；候选是可选做法，不是已存在的答案。
```
dp25 四段（发给 PM）：
```
按四段给材料：交付目标（key 的验收目标原文）/实际完成情况（已落盘产物与行为）/验证证据（逐条，标已执行或未执行，未验证单列）/未完成项及影响。不得用调用次数或完成声明代替证据；未知写「未知：…」。
```
dp2 无LLM提示：自评行由 worker 的 checkpoint steer 生成（`worker-mode.ts:367-390`），PM **原文摘取**，不加解释。

## 6 两条实现路径比较（含推荐）

**方案A：registry 契约收紧（逐DP改必填集+新字段+新context槽）**
- 改动：`decision_points.py` 四个 `_point` 块 + `REQUIRED_STATE_FIELDS`/`STATE_FIELD_DESCRIPTIONS`/`OPTIONAL_STATE_FIELDS`；`decision_context.py` 新槽；`scripts/gen_decide_registry_ts.py` 重生成；`triage-client.ts:REQUIRED_FIELDS_BY_DP`+校验器；四个 builder。
- 优点：字段表仍是唯一权威；闭键集继续拒绝未知键；TS 由 Python 生成，一处改多处同步；模型看到什么=契约声明什么。
- 缺点：影响面最大（Python 8+ 测试、TS 4 文件、3 个生成物）；`key/phase/authority_tier` 等**不在producer手里**（`_state_builder` 注入），单靠A删不掉。

**方案B：发送前投影（保留现有字段表，只投影模型看到的 state）**
- 改动：`decision_points.py` 一处（`_decide_for` 在契约门之后、`_fit_state` 之前丢弃审计/身份路径），producer 不动。
- 优点：AC-002 由构造保证，一条测试即可对 HTTP body 断言；改动点最少。
- 缺点：registry 声明 ≠ 实际发送（两个真相）；`state_digest/快照/observation book 的 sent_state 相等性`（`:4880-4905`）需同时投影；模型材料仍是旧字段（`triage_risk` 问题还在）。

**推荐方案C（A 的业务部分 + B 的审计部分，最小接线）**
1. 业务字段按 §4 收进契约（A）。2. 身份/审计（`schema_version/decision_point/questions_version` + 该DP不想要的 `key/phase/task_type/risk/authority_tier`）用一个常量 `MODEL_STATE_OMIT` 在 `_decide_for` 发送前剔除，快照/digest 取剔除后的 state；档案行仍由 `decision_id`/trigger 建（不经 state）。
3. 问题表改 §3（新 `q-*`）；4. 重生成 `decide_registry.json` / `decide-registry.generated.ts` / `decide_book_template.json`；5. 四个 producer 按 §7 改；6. 每字段一条生产路径测试（§9）。
- 代价：仍是跨层改动，但业务语义落在 registry（可读、可校验），审计分离只多一处（可单测）。

## 7 各字段真实 writer / reader / 拒绝路径

| 字段（新契约） | writer（真实入口） | reader | 拒绝路径 | 生产路径测试建议 |
|---|---|---|---|---|
| dp1 `task_goal/task_requirements/deliverables` | `ui-bridge.ts:1835` 的 `description`（=卡片正文，`writeDispatchTaskMd {body: description}` `:3328`）与 `cardGate.sections`（`:3315`）；新写者 `buildDp1DispatchState` | 模型；消费侧只读 `dispatch_type`（`triage-client.ts:915`） | 空/超长→`input-incomplete`/`input-oversize`（`:4783`,`:4859`）；类型不在三角色→**producer 侧零发送**（见§8 vision/rag） | `buildDp1DispatchState` 单测（字节+`assertStateMatchesRegistry`）+ Python stub backend 断言 state 键集；`:292-294` acted 门槛回归 |
| dp2 `worker_self_assessment` | 新写者：PM 侧 `buildDp2CheckpointState`（`pm-orchestrator.ts:2137`）读 `taskDir/progress.md` 的 `CKPT` 行/`## 完成记录`（正则已有 `worker-mode.ts:545 PROGRESS_DONE_RE`，可复用扩展） | 模型 | 自评缺失→**建议不发**（`decideDp2Checkpoint` 返回 undefined，保留原告警）；空串不得当“无异常” | 造 3 个 taskDir fixture（有自评/无自评/writeless 仅 reply）断言 spawn 次数 0/1 与返回 |
| dp2 `progress.elapsed_minutes/budget_minutes` | 已有 `CheckpointInfo.elapsedS`+`readDp2TaskHeader`（`:2142`,`:2347-2356`） | 模型 | 负数/非整数→`input-incomplete`（`min_value`） | 现测试覆盖，补“预算<已用”边界 |
| dp3 `question` | worker：`worker-mode.ts:4156 attemptDp3Clarification`（`lastAssistantText`）；PM：**新producer**（§8） | 模型 | 空→`input-incomplete`（`:5661-5668`） | 两种角色各一条 builder 测试 |
| dp3 `background.*` | 提问Agent（worker 自己的 turn / PM 工具调用）；producer 只做截断与校验 | 模型 | 任一段空→`input-incomplete`（建议必填四段，未知用显式标记） | 缺段 fixture → stdout 0 字节、exit≠0 |
| dp3 `handling_options` | 提问Agent生成 → `buildDp3State` 归一化为 `{id:"c1..c5",label}`（沿用 `decision_points.py:1109-1139` 校验） | 模型（dynamic choice label）；消费侧读选中 id | 0 条/超5条/超80字符/含换行→`input-incomplete`（`dynamic_choices_value_error`） | 5/6 条边界 + 超长 label；`resolve_dynamic_choices` 单测 |
| dp25 五段 | PM（新写者）→ `signoff_state` 或新 builder；本地硬门另算（RQ2） | 模型 | 缺段→`input-incomplete`；已验证/未验证混一列→建议校验器拒 | PM 侧 builder 单测 + stub backend 断言 state 五键、无 `rows_*` |

## 8 producer 接线（两个缺口 + vision/rag 边界）

- **dp3 PM→用户（缺口）**：今天无 producer。建议把 `ask_decision`（`index.ts:84-90` 仅 worker 注册）扩为 PM+worker 共用，并给它三个可选参数 `background{goal,current_state,why,constraints}`、`options[{label,description}]`、`dp=dp3`；`buildDecisionState`（`decision-tool.ts:267-278`）按 dp 组装，`missingDecisionStateFields`（`:299`）继续在本地拦缺字段。优点：复用已存在的 spawn/anti-retry/`decision_id` 透传（`decision-tool.ts:40-75`），PM 侧零新通道。次选：新纯函数 `decideDp3PmClarify` 放在 `pm/`，由 PM 在提问前调用——但 PM 提问点分散，找不到唯一位点。[事实+建议]
- **dp2 自评（缺口）**：PM 从不读 `progress.md`（`:2210` 清单无它，`:2727` 只在告警文案里提路径）。需新增有界读（尾 4KB、只取最后 `CKPT` 行 + `## 完成记录` 尾段），不放宽 `readScope`。
- **vision/rag 边界**：dp1 现在对不在三角色内的 `taskType` 返回 `{ok:false,reason:"missing"}` 并**回退 legacy 16KB state**（`ui-bridge.ts:552-556`,`:609-615`），legacy 自带 `DP1_QUESTIONS`（含 `triage_risk`）。新契约删除 legacy 分支后，vision/rag 派发必须 **producer 侧跳过 dp 调用（零 HTTP）并保留原 type**，不得映射成三类之一；`ui-bridge.ts:293 auto && triage_type===dispatchedType` 天然不会改写类型，但 legacy 删除需一条“vision/rag 派发 0 次 decide”回归。[事实+建议]

## 9 dp2 自评来源、次序与缺失处置（分事实/建议/未决）

- **[事实] 真值来源**：worker 框架写 `[CHECKPOINT] ts elapsed=… reads= writes= phases= uniq_targets= repeat_top= risk=…` 到 `trace.log`（`worker/output-writer.ts:726-742`），writeless 角色额外写 `CKPT <n>m [machine] …` 到 `progress.md`（`:755-762`, `worker-mode.ts:3929-3945`）；**agent 自评**是 steer 要求它追加的 `CKPT <X>m converging=yes|no eta≈<Y>m <理由>`（`worker-mode.ts:367-390`），writeless 可只写在回复里。[事实]
- **[事实] 次序**：机器行先落盘 → `sendUserMessage(checkpointSteerText, {deliverAs:"followUp"})`（`:3948-3958`，等当前 turn 结束）→ agent 下一轮才写自评。PM 每 4s 轮询（`pm-orchestrator.ts:107`），首个 `risk != low` 检查点即触发 dp2（`:2669-2690`），**早于** 自评行落盘的概率很高；且 `escalated.add(taskKey)`（`:2576`,`:2671`）使每个 task 每个 PM 会话只试一次，不会等下一检查点。
- **[事实] 缺 reader**：`CheckpointInfo.progressDone` 只由 `PROGRESS_DONE_RE`（`worker-mode.ts:545`）判 `converging=yes` 用于 risk，dp2 state 无对应键；`report.md/progress.md` 正文从不进 dp2。
- **[建议] 异常计数最小规则**（只用已有机器事实，不新增指标）：仅当 `repeat_top>=4`（打转，registry 现成阈值 `worker-mode.ts:516-530`）或 `writes==0 且 elapsed>=anchor`（30m，`:404`）或 `artifact_present==false 且 elapsed>=anchor` 时，附 `anomaly:{repeat_top,writes,artifact_present,elapsed_minutes}`；否则不附。
- **[建议] 缺自评处置**：不发 dp2（`decideDp2Checkpoint` 返回 undefined → 原 PM 告警逐字不变、`triggerTurn` 照旧），并在 trace 记 `dp2 skipped: no self-assessment`；理由：DP 的判断对象就是 worker 自述，缺失时人看原始告警更诚实。
- **[未决]** 阈值（是否就用 4/0/30m）、是否允许“下一检查点重试一次”、writeless 只写在回复里的自评是否要从 transcript 取（涉 L2 材料边界）。

## 10 旧契约/生成物/下游清单（改与不改的边界）

必须一起改（否则漂移或拒绝）：
- Python：`decision_points.py`（四 `_point` 块 `:546,:576,:596,:863`；`REQUIRED_STATE_FIELDS :1256-1472`；`STATE_FIELD_DESCRIPTIONS :1473+` 新增路径；`OPTIONAL_STATE_FIELDS :2114-2133`；`TRUNCATABLE_STATE_PATHS :2144`；发送投影新常量）；`decision_context.py` 若加新槽（`:55-109`,`SLOT_CUT_ORDER :119-125`）；`decide_signoff.py`（dp25 词表，RQ2）；`decide_book_template.json`（dp3 段落 `:1-45`）、`decide_registry.json`。
- TS：`shared/decide-registry.generated.ts`（由 `scripts/gen_decide_registry_ts.py` 重生成，禁止手改）；`pm/triage-client.ts`（`REQUIRED_FIELDS_BY_DP :380`、`TASK_TYPE_CHOICES :404`、`DP1_QUESTIONS :93-96`、`DP1_QUESTIONS_VERSION :104-113`）；`pm/ui-bridge.ts`（builder+legacy 分支）；`pm/pm-orchestrator.ts`（builder+`DP2_QUESTIONS_CANONICAL :1986`+映射）；`worker/worker-mode.ts`（`buildDp3State`、常量 `DP3_QUESTIONS_VERSION :4970`、消费分支 `:5760-5820`）；`pm/decision-tool.ts`（PM dp3 入口）。
- 测试锁：`test_decide_registry_contract.py`（`:340` Python↔TS 必填一致、`:353` 三个 TS producer、`:381` dp3 需 `local_candidates`）、`test_decide_registry_export.py`（`:49/128` wired 集合恰为 dp1/dp2/dp3）、`test_decide_registry_ts_lock.py`、`test_decision_input_contract_migration.py`、`test_decision_required_refusal.py`、`test_decision_full_value_freeze.py`、`decision_book/playground/dashboard` 相关、`worker-mode.test.ts`/`pm-orchestrator` 套件。

不得改（避免误删 21 个 DP / vision / rag）：
- 21 个非四DP 的 `_point` 块、`REQUIRED_STATE_FIELDS` 其余键、`STATE_FIELD_DESCRIPTIONS` 其余路径（全局表，新增路径不得复用他人含义）。
- dp1 三角色之外的 `vision/rag-research/codex` 派发路径与 `dispatch.yml` 的 model 路由（`:1861-1870`）；legacy 分支删除必须同时落“vision/rag 零 decide 调用 + 类型不变”测试（§8）。
- `decision_backends.py` 的 Jev 原生返回解析（`usage/confidence/probabilities` 保留在本地日志，不转成业务问题，`spec.md:1` §1.3）。

## 11 给PM的接口草案（可落 design，不含实现）

```python
# decision_points.py（形状草案，命名待确认）
MODEL_STATE_OMIT = {          # 发送前剔除；快照/digest 用剔除后的 state
  "dp1-dispatch-type": ("schema_version","decision_point","questions_version","key","phase",
                        "task_type","requested_type","risk","risk_source","authority_tier"),
  "dp2-checkpoint-split": (..., "authority_tier"),
  "dp3-worker-clarify": (..., "authority_tier","task_type","risk","risk_source"),
  "dp25-signoff-conclusion": (...),
}
# 每DP业务必填（dp1/dp2）：("task_goal","task_requirements","deliverables")
# dp2 追加 ("worker_self_assessment")，复用 ("progress.elapsed_minutes","progress.budget_minutes")
# dp3：（"question","background.goal","background.current_state","background.why",
#        "background.constraints","handling_options"）
# dp25：（"delivery_goal","completion","verified_evidence","unverified_items","unfinished_impact")
```
```ts
// 唯一新增入口（PM+worker 共用 ask_decision 时）
registerAskDecisionTool(pi, { roles: ["worker","pm"], dp3Material: true });
// 纯 builder 草案
buildDp3ClarifyState({key, phase, question, background, options}): Record<string, unknown>;
buildDp2CheckpointState({..., selfAssessment?: string}): Record<string, unknown>; // 缺失则不调用
```

## 12 待决（人不裁决前不实现）

1. dp2 四机器值改名的定位（`handback` vs 保留 `escalate`）；§3 表整体确认。
2. dp2 异常阈值与“缺自评不发/显式标记”二选一（§9）。
3. 2000B 是否对 dp3/dp25 放宽（以 RQ3 真实样例为据，不先定任意上限）。
4. dp3 状态键是否从 `local_candidates` 改名 `handling_options`（语义：事实答案→处理候选；会动 book 模板/TS 锁/测试）。
5. dp25 词表与本地硬门/签收归 RQ2；`p0_open` 是否移出模型输入同属 RQ2。
6. `ask_decision` 是否对 PM 开放（或另建 PM 专用工具），影响 AC-010 的角色/任务关联。
