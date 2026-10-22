# dp1..dp6 事实清单（decision-substitution 用户文档素材）

采集时间：2026-10-21。只读采集，未跑 `mw decide run/ask/probe`、未改代码、未跑测试、无 git 写。
行号取自当日实际读到的文件版本。`questions_version` 用只读方式
（`PYTHONPATH=packages/multi-workers python -c "import decision_points; ..."`，无网络、无写盘）从注册表现算，
与 TS 侧镜像常量交叉核对一致。

通用锚点（Python 权威侧，`packages/multi-workers/decision_points.py`）：

- `DecisionPoint` dataclass + 导入期校验：`:300-345`（`default_enabled` 必须随 tier：P2 开、P1/P0 关 `:324`；P0 必须给 `p0_consequences` `:338-340`；P2 必须有 executor `:342-343`）
- `_questions_version`：`:280-297`（只哈希 VERSIONED_QUESTION_KEYS，`q-<8hex>`，instructions/labels/criteria 文案不改变版本）
- `_point` 工厂：`:385-410`（`default_enabled=(tier == "P2")` `:399`；`default_mode` 默认 `"auto"` `:401`）
- 泛型 state 组装 `_state_builder`：`:349-369`（固定 `v:1`、`dp`；并入 `trigger.data`；`trigger.key`→`key`、`trigger.task_key`→`task_key`；缺省补 `questions_version`；不为必填字段造默认值）
- `_unwired_executor`：`:372-380`（故意 raise NotImplementedError：DS-4 禁止默认动作，auto+act 时由 decide_for 转 `over-authority` 上抛人）
- `decide_for` 唯一入口：`:1666-2110`。步骤：unknown id 抛错 `:1721`；`enabled=false`→escalate `disabled`（build_state/网络之前）`:1729-1746`；mode 读取 `:1749-1750`；transport 未配置→`unavailable` `:1752-1774`；build_state 失败/非 mapping/缺必填→`input-incomplete` `:1776-1833`；canonical >2000B 两段截断后仍超→`input-oversize` `:1836-1862`；无可用答案→`low-confidence` `:1866-1903`；置信门（仅 `confidence_source=="api"`）`:1906-1938`；`mode=suggest` 或 `intent="answer"`→只留痕 `acted=false` `:1941-1966`；`executor is None`→`over-authority`(no executor) `:1978-1994`；执行 executor `:2008`；executor raise/返回空→`over-authority` `:2011-2063`
- `MIN_CONFIDENCE = 0.7`：`:90`；`MAX_STATE_BYTES = 2000`：`:87`；`_confidence_threshold`（显式参数 > `.mw/decide.json` extras `min_confidence` > 默认 0.7）：`:2102-2110`
- `REQUIRED_STATE_FIELDS`（仅 dp1/dp2/dp3 有条目）：`:872-921`；动态 choices 渲染 `resolve_dynamic_choices`：`:849-861`（`dynamic_choice_labels` `:833-846`，渲染后的候选 id 枚举才是模型可答集合，questions_version 不含候选数据）
- `decide_for` 归档 `_maybe_archive`：`:1525`
- P0 开关人工门 `--i-understand-p0`：`packages/multi-workers/mw.py:1806-1820`（`_dp_require_p0_confirmation`，非 P0 或带 flag 才放行，并打印 p0_consequences）；CLI 参数 `mw.py:9780-9784`；改判提示 `mw.py:2182-2200`

`questions_version` 现值（只读导入现算，2026-10-21）：

| dp | questions_version |
| --- | --- |
| dp1-dispatch-type | `q-09d3aad3`（TS 镜像 `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:98-113`，注释亦写 `q-09d3aad3`） |
| dp2-checkpoint-split | `q-ba8e970f`（TS 镜像 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1980-1992`） |
| dp3-worker-clarify | `q-fcbd3847`（TS 镜像 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4427-4428`） |
| dp4-failure-handling | `q-b93176a8` |
| dp5-test-triage | `q-cc104f59` |
| dp6-qg-verdict | `q-16b4bb5c` |

## 汇总表

| dp | tier | 默认 enabled/mode | 触发点 path:line | questions 类型 | 采纳落点 path:line |
| --- | --- | --- | --- | --- | --- |
| dp1-dispatch-type | P2 | true / auto | ui-bridge.ts:1730（每次 PM 派发，planDispatchFrontmatter 内；策略门 triage-client.ts:820） | 2×choice（triage_type/triage_risk，带 labels+instructions） | 只留痕+建议；采纳=ui-bridge.ts:281-293（dispatchDecisionOf，mode=auto 且类型一致才写 `decision:` 头行）；分歧唤醒 PM ui-bridge.ts:541-556 |
| dp2-checkpoint-split | P2 | true / auto | pm-orchestrator.ts:2602（PM 轮询 loop；条件 `:2592-2595` running + checkpoint risk mid/high，每任务一次） | 1×choice（checkpoint_action，带 labels+instructions） | narrow（唯一可执行动作）→ 写 `<taskDir>/steer-dp2.md` pm-orchestrator.ts:2620-2622 + trace :2399-2408；worker 消费 worker-mode.ts:2929/3825；其余全部回落人 alert pm-orchestrator.ts:2641-2652 |
| dp3-worker-clarify | P2 | true / auto | worker-mode.ts:3903（settle 路径 `exitCode===2` NC 时唯一插入点；策略门 :3699-3701；进程内一次预算 :3706） | choice + noul + choice(dynamic_choices)（answer_kind/answerable/candidate） | 注入 `[mw dp3-answer]` followUp 即采纳（actedDecision.acted=true）worker-mode.ts:3753-3780；3b/suggest/降级走原人工路径 :3782-3801 |
| dp4-failure-handling | P1 | false / auto | 未接线（已查 dp4-failure-handling / failure-handling / dp4，TS+Python 全仓，见未接线清单） | 1×choice（failure_action，无 labels/instructions） | 无执行器（executor=None）；`mw decide run`/ask_decision 只留痕 acted=false decision_points.py:1941-1966；强推 act 会 over-authority :1978-1994 |
| dp5-test-triage | P2 | true / auto | 未接线（已查 dp5-test-triage / test-triage，见未接线清单） | 1×choice（test_category，无 labels） | 注册但无执行器（_unwired_executor :524），只有 `mw decide run` 可手工调用；auto+act → over-authority |
| dp6-qg-verdict | P1 | false / auto | 未接线（已查 dp6-qg-verdict / qg-verdict，见未接线清单） | 1×choice（qg_verdict，无 labels） | 无执行器（executor=None）；同 dp4，只留痕/over-authority |

## dp1-dispatch-type（已接线：PM 派发旁路建议）

1. 注册身份：`decision_points.py:420` `dp_id="dp1-dispatch-type"`；`:421` `tier="P2"`；`:422` `description="派发 type/角色/范围"`；`default_enabled=True`（tier 规则 `_point:399`）；`default_mode="auto"`（`_point:401` 默认参数）。
2. 触发点（已接线）：PM 每次派发构建 frontmatter 时，`ui-bridge.ts:1730`（`planDispatchFrontmatter` `ui-bridge.ts:1628-1690` 内、任何派发落盘之前）调 `computeDispatchTriage`（`ui-bridge.ts:488-533`）；条件原文 `ui-bridge.ts:501` `if (!policy.enabled || !policy.dp1Enabled) return null;`（策略读 `.mw/decide.json` + `points.dp1.enabled !== false`，`triage-client.ts:235-243`）。子进程入口 `triageDispatch` `triage-client.ts:816-880`：同样的门 `:820` `if (!policy.enabled || !policy.dp1Enabled) return unavailable("disabled");`，随后 spawn `mw decide run`（`runDecideMw`，stdin 传 envelope）。
3. state 形状：TS 手工组装 `buildDp1DispatchState` `ui-bridge.ts:440-486`。字段：`v:1`、`dp`、`key`（任务 key）、`phase`、`task_type`、`requested_type`（现等于 task_type）、`risk`（`dispatchRisk(taskType, allowForeignWrite)`）、`risk_source:"pm-label"`、`authority_tier:"P2"`、`task_summary`（描述首行）、`questions_version`、`scope.write_scope`、`scope.ext`（写面）。角色不在 coding/research/review 枚举内→`{ok:false,reason:"missing"}`（`ui-bridge.ts:472-476`），回退冻结的 legacy 字符串 state 并留痕 `[DECISION] dp1 state=legacy reason=…`（`ui-bridge.ts:519-527`）。Python 必填清单 `REQUIRED_STATE_FIELDS["dp1-dispatch-type"]` `decision_points.py:874-888`（14 条路径，缺失→`input-incomplete`）。state 不含 `local_candidates`；`rendered` 只在 Python 动态渲染环节内部出现（dp3 用，dp1 无动态题）。
4. questions：`triage_type` choice `[coding,research,review]` + labels + instructions「这个任务应该派给哪一类 worker？」（`decision_points.py:424-431`）；`triage_risk` choice `[low,mid,high]` + labels + instructions「这个任务做错了的代价有多大？」（`:432-442`）。`questions_version=q-09d3aad3`（现算；TS 镜像 `triage-client.ts:107-113`）。
5. 答案采纳：Python 侧生产通道走 `mw decide run` 的 `intent="answer"`（`mw.py:947-949`），按 `decide_for` 步骤 9 永远 `acted=false` 只留痕（`decision_points.py:1941-1966`）。采纳是消费方事实（D-041）：`dispatchDecisionOf` `ui-bridge.ts:281-293`——仅当 `mode==="auto"` 且 `triage_type===dispatchedType` 且有 `decision_id` 才算采纳（写 task.md `decision:` 头行；AC-014：派发 type 永不被建议改写）。账本行 `triage-suggestion`（`ui-bridge.ts:551-560`、`triage-client.ts:922-930`）；分歧且 `alert_on_disagreement!==false` 才唤醒 PM（`emitDispatchTriage` `ui-bridge.ts:534-556`）。置信度仅透传展示（`confidenceSourceLabel` `triage-client.ts:902-908`）；Python 侧只有 `confidence_source=="api"` 低于阈值才 gate（`decision_points.py:1906-1938`，阈值 `MIN_CONFIDENCE=0.7 :90`、`_confidence_threshold :2102-2110`）。
6. 风险语义：P2（可逆、局部）→ 注册即默认 enabled，与 `--i-understand-p0` 无关（该门仅 P0，`mw.py:1808-1810`）。

## dp2-checkpoint-split（已接线：PM 轮询 loop 收窄收敛检查点）

1. 注册身份：`decision_points.py:450` `dp_id="dp2-checkpoint-split"`；`:451` `tier="P2"`；`:452` `description="checkpoint 拆/收/直执"`；`default_enabled=True`/`default_mode="auto"`（`_point:399/401`）。
2. 触发点（已接线）：PM 轮询 loop `startWorkerPollLoop` `pm-orchestrator.ts:2474-2660`。判定原文：`:2592` `const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;` → `:2593` `if (!ck || ck.risk === "low") continue;`（running worker 的收敛检查点机器判据 risk=mid/high 才继续；`escalated` 集合保证每任务本会话一次 `:2595`）。调用 `:2602-2609` `decideDp2Checkpoint(...)`；内部短路：`:2270-2271` `if (!policy.enabled) return undefined;`、`:2274-2276` `readDp2Authorization`（`.mw/decide-points.json` 的 dp2 行，`pm-orchestrator.ts:2067-2090`；缺省 enabled=true `:2068`）——两者都只是零 spawn 短路，授权以 Python 为准（D-036 注释 `:2271-2274`）。
3. state 形状：TS 手工组装 `buildDp2CheckpointState` `pm-orchestrator.ts:2126-2168`。字段：`v:1`、`dp`、`key`（owner key，clamp 48B）、`task_key`、`phase`（task.md `phase:`，缺省 "unknown" `:2193-2208`）、`task_type`（dp1 三值枚举，越界映射 coding `:2176-2181`）、`risk`（检查点机器判据）、`risk_source:"machine"`、`authority_tier:"P2"`、`questions_version`、`progress`：必填 `elapsed_min/budget_min/phases_done/phases_total/artifact_present`（`:2132-2142`；budget=task.md `timeout:` 分钟 > `PI_WORKER_TIMEOUT_MS` > 60m，`:2183-2190`）+ 可选 L1 `writes/uniq_targets/repeat_top/trend`（最近 3 条 `[CHECKPOINT]`，`readCheckpointTrend` `:2013-2031`，正则 `:2007`）`/last_land_age_min`。必填清单 `decision_points.py:889-904`。不含 `local_candidates`。
4. questions：`checkpoint_action` choice `[narrow,split,direct-exec,escalate]` + labels（收窄/拆分重派/PM 直执/必须问人）+ instructions「以当前进度，这一步该继续、拆小、直接执行还是上抛人？」（`decision_points.py:454-465`）。`questions_version=q-ba8e970f`（现算；TS 镜像 `pm-orchestrator.ts:1983-1992`）。
5. 答案采纳：答案读取+闭合映射 `pm-orchestrator.ts:2326-2343`（未知/缺值→`none`，无默认动作分支）；`decision.acted = mode === "auto" && decision.action === "narrow"`（`:2346-2348`，D-011：narrow 是机器唯一可执行动作）。acted 落点三步：存活探测 `probeDp2TaskLiveness` `:2617-2620`（非 running→fallback 行 `:1978`）；原子写 `<taskDir>/steer-dp2.md` `writeDp2SteerRequest` `:2358-2386`（首行 `[dp2-narrow-request]` 机器头 `:1974`，正文 `[mw dp2-narrow]` 前缀 `:1970`）；成功后 trace 关联行 `appendDp2ActedTrace` `:2399-2408`（`[DECISION] dp2 acted=1 decision_id=…`，仅在 steer 真落地后写）。worker 消费：`consumeDp2NarrowSteer` `worker-mode.ts:2881-2927`，before_agent_start `:2929` 与 settle `:3825` 两个入口，注入后写 `[dp2-consumed …]` 标记 `:4345/:4375-4391`。split/direct-exec/escalate/suggest/一切降级 → 原 PM alert 字节不变并唤醒人（`pm-orchestrator.ts:2641-2652`，附带 fallback 行仅 liveness 失败时 `:2651`）。置信度透传（`:2332`），Python api 门同上。
6. 风险语义：P2 → 默认 enabled；如需关掉 `mw decide dp off dp2-checkpoint-split`（`pm-orchestrator.ts:2630` 的改判提示），无 `--i-understand-p0` 关联。

## dp3-worker-clarify（已接线：worker NC 出口澄清替换）

1. 注册身份：`decision_points.py:470` `dp_id="dp3-worker-clarify"`；`:471` `tier="P2"`；`:472` `description="worker 澄清（dp3a 事实可查 / dp3b 意图需人 / dp3c 已表态复用）"`；`default_enabled=True`/`default_mode="auto"`（`_point:399/401`）。
2. 触发点（已接线）：worker settle 成功路径 `finishSuccess`（`worker-mode.ts:3811-3836`）内唯一插入点：`:3895-3902` 注释（dp3 输入全部在作用域、NC 产物未写、终态未提交）+ `:3903` 原文 `if (exitCode === 2 && attemptDp3Clarification([...].join("; "))) { return; }`（exitCode 2 = needs-clarification：无写角色无交付证据/恢复自检未过）。`attemptDp3Clarification` `worker-mode.ts:3696-3801`：门 `:3699-3701` `if (!policy.enabled) return false;`（D-007 零 spawn 零写）；预算 `:3706` `if (dp3AutoAnswered)` 进程内只自动答一次，其后全部回人工路径。
3. state 形状（专门 shape，完整列出）：TS 手工组装 `buildDp3State` `worker-mode.ts:4984-5010`。字段：`v:1`、`dp`、`key`、`phase`、`task_type`（`dp3TaskType` 三值映射 `:4787-4791`）、`risk`（`lastCheckpoint?.risk ?? "mid"` `:3722`）、`risk_source`（有检查点="machine" 否则 "pm-label" `:3724`）、`authority_tier:"P2"`、`questions_version`、`task_summary`（澄清问题 ≤600B 摘录 `:4989`）、`ambiguity:{kind:"scope",question:≤300B}`（契约枚举无 fact，dp3a 搭 scope；真实三分类由 `answer_kind` 答案承载，`:5002-5007`）、`local_candidates:[{id,label}]`（`buildDp3Candidates` `:4890-4929`：c1=固定 evidence 归档路径 + 仓库扫描命中，上限 `DP3_CANDIDATE_LIMIT=5 :4447`，label ≤80B `:4848-4854`）。canonical > `DP3_MAX_STATE_BYTES=2000`（`:4450`）→ escalate `input-oversize`（`:5111-5116`）。Python 必填清单 `decision_points.py:905-921`，显式含 `local_candidates :920`（没有它动态题无法渲染、零 HTTP，注释 `:916-918`）。动态键：`candidate` 题 `dynamic_choices:"local_candidates"`（`:499`），Python `resolve_dynamic_choices :849-861` 把候选 id 渲染成合法枚举；`rendered` 是 Python 侧内部渲染表（`dynamic_choice_labels :833-846`），不进 state。
4. questions（3 题）：`answer_kind` choice `[fact,intent,reuse]` + labels + instructions「这条澄清属于哪一类：能凭已给材料查到答案、需要人的意图判断、还是已有表态可复用？」（`decision_points.py:474-486`）；`answerable` `noul` + criteria `{true:"材料里直接有答案",false:"材料不足或需要人表态"}` + instructions（`:487-495`）；`candidate` choice + `dynamic_choices:"local_candidates"` + instructions「state.local_candidates 里哪一条最可能承载答案？」（`:496-501`）。`questions_version=q-fcbd3847`（现算=TS 镜像 `worker-mode.ts:4428`）。
5. 答案采纳：三子路径判定在 `decideDp3WorkerClarify` `worker-mode.ts:5042-5222`：3c 零 spawn 本地复用优先（`matchDp3Reuse :4693-4714`；score < `DP3_MIN_MATCH_SCORE=0.75 :4434` → escalate low-confidence 3c `:5071-5073`；入围线 `DP3_BORDERLINE_MATCH_SCORE=0.6 :4437`）；3b 默认：意图措辞/无可解析指涉/非定位问句 → escalate `intent` 3b（`:5087-5106`；`DP3_INTENT_RE :4717`、`DP3_LOCATOR_RE :4721`）；3a：一次服务调用（`:5109-5126`），子进程 `mode` 是唯一权威（缺/未知 → escalate unavailable `:5157-5166`）；置信度仅 `confidence_source=="api"` 时对照 `policy.minConfidence` 门（`:5168-5171`；默认 `DP3_MIN_CONFIDENCE=0.7 :4440`，可被 `.mw/decide.json min_confidence` 覆盖 `:4533-4538`）；`answerable` noul 概率 < `DP3_ANSWERABLE_MIN=0.5`（`:4444`）→ escalate（`:5196-5199`）；答案正文与 `path:line` 出处一律本地生成（模型只选候选 id：`resolveDp3CandidateAnswer :4953-4974`）。采纳=注入 steer：`worker-mode.ts:3753-3760` `actedDecision={...decision, acted:true}`（仅 `kind==="answer" && mode==="auto"`，`:3749-3751`），trace 冻结格式 `[DECIDE]` 行（`formatDp3TraceLine :5244-5260`）+ `[DECISION] dp3 acted=1 …` `:3770-3777`，followUp 载体 `pi.sendUserMessage(formatDp3AnswerSteer(...))` `:3780`，steer 固定前缀 `[mw dp3-answer]`（`:4431`，正文 `formatDp3AnswerSteer :5225-5238`），run 保持打开等下一 settle（`:3817-3820` 注释）。其余一切（3b/suggest/低置信/不可用/输入不完整/超预算）→ 返回 false 走原人工 `## Questions` 路径（`:3782-3801`）。Python 侧 dp3 executor 是 `_unwired_executor`（`:503`）→ 注册但无执行器，生产只经 `mw decide run` intent=answer 取建议；auto+act 会 over-authority。
6. 风险语义：P2 → 默认 enabled；策略读 `readDp3Policy` `worker-mode.ts:4518-4541`（`.mw/decide.json` transport 门权威；`.mw/decide-points.json` 行镜像非权威，分歧以 Python 为胜 `:4509-4517`），与 `--i-understand-p0` 无关。

## dp4-failure-handling（未接线）

1. 注册身份：`decision_points.py:506` `dp_id="dp4-failure-handling"`；`:507` `tier="P1"`；`:508` `description="失败处置"`；`default_enabled=False`（P1 规则 `:324`）；`default_mode="auto"`（`_point:401`）。
2. 触发点：未接线（已查关键词：`dp4-failure-handling`、`failure-handling`、`dp4`，范围 packages/coding-agent/src 全部 .ts + packages/multi-workers 全部 .py）。命中仅有：`decision-tool.ts:114`（PM ask_decision 工具的 24 id 白名单 `ASK_DECISION_DP_IDS`）、`triage-client.ts:373`（结构化 state 必填字段元数据，Python 端无对应条目，不生效）、`mw.py`/测试文件（注册表本身与 CLI 管理测试）。无任何生产调用点；可用通道=`mw decide run --dp dp4-failure-handling`（结构化路径，`mw.py:947-949` intent=answer）与 PM 的 ask_decision 工具（`decision-tool.ts`，`mw decide run` 同一子进程路径）。
3. state 形状：泛型 `_state_builder` `decision_points.py:349-369`（`v:1`、`dp`、`trigger.data` 并入、`key`/`task_key`、`questions_version` 补缺）。`REQUIRED_STATE_FIELDS` 无 dp4 条目（`:872-921` 仅 dp1/dp2/dp3），即实际必填仅 `v`/`dp`/`questions_version`（注释 `:873-875`）；`triage-client.ts:373` 记录的意图字段 `failure.kind` 目前只是 TS 元数据。无 `local_candidates`（无动态题）。
4. questions：`failure_action` choice `[retry,rework,escalate]`，无 labels、无 instructions（`decision_points.py:508-511`）。`questions_version=q-b93176a8`。
5. 答案采纳：无执行器（注册块 `:506-512` 未传 executor → `_point` 默认 None `:399-407`）。`mw decide run`/ask_decision 均为 `intent="answer"` → 步骤 9 只留痕 `acted=false`（`:1941-1966`）；若有人以 act 意图调 `decide_for`，`executor is None` → escalate `over-authority`(no executor)（`:1978-1994`）。即：注册但无执行器，只有 `mw decide run` 可手工调用，答案只留痕（归档行），无 steer/narrow/escalate 落点。
6. 风险语义：P1 → 注册默认关闭，需 `mw decide dp on dp4-failure-handling` 手工开启；P1 不触发 `--i-understand-p0` 门（仅 P0，`mw.py:1808-1810`）。

## dp5-test-triage（未接线）

1. 注册身份：`decision_points.py:514` `dp_id="dp5-test-triage"`；`:515` `tier="P2"`；`:516` `description="测试失败归类"`；`default_enabled=True`/`default_mode="auto"`（`_point:399/401`）。
2. 触发点：未接线（已查关键词：`dp5-test-triage`、`test-triage`、`dp5`，范围同上）。命中仅有 `decision-tool.ts:115`（ask_decision 白名单）、`triage-client.ts:374`（意图字段 `failure.kind/failure.test_name/failure.baseline_known` 元数据）、注册表与测试。无生产调用点。
3. state 形状：泛型 `_state_builder`（同 dp4）；无 `REQUIRED_STATE_FIELDS` 条目；无 `local_candidates`。
4. questions：`test_category` choice `[baseline-env,flaky,regression,unknown]`，无 labels、无 instructions（`decision_points.py:517-521`）。`questions_version=q-cc104f59`。
5. 答案采纳：executor=`_unwired_executor("dp5-test-triage")`（`:524`，占位器 `:372-380` 故意 raise）→ 注册但无执行器，只有 `mw decide run` 可手工调用；`intent="answer"` 只留痕（`:1941-1966`），auto+act 会 escalate `over-authority`（executor raise NotImplementedError，`:2011-2029`）。PM ask_decision 通道同理。
6. 风险语义：P2 → 注册默认 enabled，但无调用点与执行器，enabled 与否现无行为差异；无 `--i-understand-p0` 关联。

## dp6-qg-verdict（未接线）

1. 注册身份：`decision_points.py:527` `dp_id="dp6-qg-verdict"`；`:528` `tier="P1"`；`:529` `description="QG 结论处置"`；`default_enabled=False`（P1 规则 `:324`）；`default_mode="auto"`。
2. 触发点：未接线（已查关键词：`dp6-qg-verdict`、`qg-verdict`、`dp6`，范围同上）。命中仅有 `decision-tool.ts:116`（ask_decision 白名单）、`triage-client.ts:375`（意图字段 `closure` 元数据）、注册表与测试。无生产调用点。
3. state 形状：泛型 `_state_builder`；无 `REQUIRED_STATE_FIELDS` 条目；无 `local_candidates`。
4. questions：`qg_verdict` choice `[pass,fix,reopen]`，无 labels、无 instructions（`decision_points.py:529-533`）。`questions_version=q-16b4bb5c`。
5. 答案采纳：无执行器（注册块未传 executor → None）→ 同 dp4：`mw decide run`/ask_decision 只留痕（`:1941-1966`）；act 意图 → `over-authority`(no executor)（`:1978-1994`）。注册但无执行器，只有 `mw decide run` 可手工调用。
6. 风险语义：P1 → 注册默认关闭，手工开启无 `--i-understand-p0` 要求（仅 P0）。

## 未接线清单（dp4/dp5/dp6）

实际搜索记录（2026-10-21）：

- 关键词：`dp4-failure-handling`、`dp5-test-triage`、`dp6-qg-verdict`、`failure-handling`、`test-triage`、`qg-verdict`；范围 `packages/coding-agent/src/**/*.ts` 与 `packages/multi-workers/**/*.py`。
- TS 命中全部为**非调用点**：`decision-tool.ts:114-116`（PM ask_decision 工具的 `ASK_DECISION_DP_IDS` 24 id 白名单，`:105-134`；dp1/dp2/dp3 额外在客户端必填预检名单 `ASK_DECISION_ENFORCED_STATE_DP_IDS :143-150`）、`triage-client.ts:373-375`（`REQUIRED_STATE_FIELDS` 镜像元数据，仅 dp1/dp2/dp3 被 Python 强制 `decision_points.py:872-921`）。
- Python 命中全部为注册表定义（`decision_points.py:506/514/527`）、CLI 管理（`mw decide dp on/off/set`，`test_decide_dp_cli.py`）与 `decide_for` 单元测试（`test_decision_points.py:1143/1180/1272` 等）。
- 调用面穷尽：`decide_for` 的生产调用仅 `mw.py:947`（`mw decide run`，人工/PM 手工）；TS 侧 `triageDispatch` 唯一调用 `ui-bridge.ts:516`（dp1 默认 id），`decideDp2Checkpoint` 唯一调用 `pm-orchestrator.ts:2602`（硬编码 dp2 id），`decideDp3WorkerClarify` 唯一调用 `worker-mode.ts:3725`（硬编码 dp3 id）。dp4/dp5/dp6 因此无自动触发、无答案消费落点。

## 残留与未验证

- `questions_version` 现值由只读导入现算取得（非文档转抄）；`dp1/dp3` 与 TS 镜像常量一致（`q-09d3aad3`、`q-fcbd3847`）。dp2 TS 镜像 `pm-orchestrator.ts:1989-1992` 按同一 canonical 算法现算，未实际运行 TS 侧断言其等于 `q-ba8e970f`（算法相同、输入相同，漂移由 `test/suite/triage-client-state.test.ts` 类漂移锁测试覆盖——未跑测试，遵守禁令）。
- `dp2` 触发依赖 worker 写的 `[CHECKPOINT]` 行（`readTaskProgress`，`shared/heartbeat.ts`）；本卡未展开 heartbeat.ts 内部行号（非 dp 事实本体）。
- `mw decide ask`（人工面）不走 `decide_for`：`_decide_ask` `mw.py:1413-1459` 直接发请求（`_ASK_DP="dp-human-ask"` `mw.py:1128`，非注册 id），无 acted/授权语义——用户文档若提到 `decide ask` 需注明这一点。
