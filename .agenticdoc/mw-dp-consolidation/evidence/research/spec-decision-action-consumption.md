# RQ8 — DP 答案如何成为 PM 动作（现状）

范围：只读静态。全文读 `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（2072 行）。
外围按调用点读：`index.ts`(84-103)、`pm-orchestrator.ts`(1932-2090 dp2 段)、`triage-client.ts`(375-435)、
`worker/worker-mode.ts`(3270-3340, 4144-4300, 4939-4999, 5345-5800)、`decision_points.py`(490-530, 600-675, 1530-1600, 4958-5005)、
`decision_lifecycle.py` 常量区。未全文读 pm-orchestrator(123k)/worker-mode(~6000 行)/mw.py/triage-client。

## 结论

1. **答案的唯一消费面是工具返回值本身。** `ask_decision.execute`（decision-tool.ts:1877）把 `outcome.text`
   当作文本结果交回当前窗口（`{content:[{type:"text",text}]}`：1938-1941 成功、1956-1959 失败、1959-1960 terminate）。
   这是 LLM 上下文注入，不是任何执行器。工具内没有"答案→业务动作"的代码。
2. **没有通用 selection→action 转换器。** 全仓 `selection` 只有两处机器消费者：dp3 helper
   `resolveHandlingSelection`(728，用于 worker-mode.ts:5730) 与 trace 行(1934)。PM 侧 `payload.selection` 只进模型上下文。
   四节答案的业务含义（narrow/split/direct-exec/escalate 等）完全靠 `promptGuidelines`(1852-1878) 约束 PM 自己去调用工具。
3. **三层记录彼此独立。**
   - `consumed`：material 路径自动写，`runMaterialAskDecision` 1358 `payload.feedback = await writeDecisionLifecycle(... stage:"consumed")`；
     dp25 由 CLI 自己写（1377-1384 docstring）。legacy 路径（含 dp7）**不写任何 feedback**。
   - `executed`/`settled`：只能由 `decision_receipt`(1964-2059) 写；先 `asked.get(decision_id)`(2004)，
     而 `asked` 只在 `isMaterialDp(dp) && outcome.meta !== undefined`（1916）时填充 → 只有 dp2/dp3/dp25 可 receipt。
     动作白名单 `DECISION_EXECUTED_ACTIONS`(2015)、结果白名单 `DECISION_OUTCOMES`(2031)，未知值 refused 不落账。
   - 写者 `writeDecisionLifecycle`(889) 只落 lifecycle event（decision_lifecycle.py:96-116 常量；record_consumed/executed/settled 796-880），无业务副作用。
4. **真实动作归谁：** PM 侧动作是 PM LLM 自己用 write/edit/派单工具做的；没有任何 PM 代码把 dp2 答案转成派单/收窄。
   唯一端到端代码通道是反向的：PM 手写 `<taskDir>/steer-dp2.md` → worker `consumeDp2NarrowSteer`(3279) 在
   `before_agent_start`(3327) 与 settle(4313) 注入 followUp（`pi.sendUserMessage(..., deliverAs:"followUp")` 3300）。
   dp25 的"动作"是 `mw decide sign --stdin` 自己写 `evidence/review/sign-final.md`（1385-1455），工具只映射 receipt（1382 自述"never signs"）。
5. **`acted=true` ≠ 业务已执行。** material dp 的 `acted` 是子进程逐字透传（1332；`intent="answer"` 归档值为 false）；
   dp25 的 `acted` 是本地从 `signoff_status ∈ {written,existing,not-required}` 反推（1481）。前者是"Python 没执行动作"的声明，
   后者是"CLI 真的签了/不需要签"的映射，都不代表 PM 做了 narrow/split。
6. **dp7 现状（未接线）。** dp7 不在 `ASK_DECISION_MATERIAL_DP_IDS`(219) 也不在 `ASK_DECISION_ENFORCED_STATE_DP_IDS`(169)：
   - 走 `runLegacyAskDecision`(1500)，state 只由 `buildDecisionState`(389) 产出（schema_version/decision_point/key/task_key/task_summary），
     **没有 `gate.*`**；`missingDecisionStateFields`(421) 对 dp7 直接返回 []（非 material、非 enforced），所以客户端不拦，白花一次 spawn。
   - Python 侧 dp7 的 `required_state_fields` 是 `gate.name`/`gate.missing_items`/`gate.verdict_age_hours`/`gate.has_config_error`
     （decision_points.py:1567-1573），`decide_for`(4958) step5 必然拒 → 工具表现为 `unavailable`（reason 经映射 1263-1270）。
     `material` schema 是封闭键集，也没有 gate.* 可填（MATERIAL_SCHEMA 1657-1756）。
   - dp7 执行器 `_unwired_executor("dp7-gate-failure")`（decision_points.py:668, 496-512）：只 raise；而 `intent="answer"`
     在 step 9 前返回、根本不触达执行器（decision_points.py:521 注释）→ 对本次 ask 通道无影响。
   - dp7 的问题只有归因项 `gate_cause ∈ {missing-evidence,stale-verdict,config,unknown}`（decision_points.py:658-668），
     **不存在"下一步处置"问题**；用户定义的"相位门失败归因后的 PM 下一步处置选择"在当前 registry 里没有承载。
   - dp7 也无法 receipt：`asked`(1830/1918) 不登记非 material dp → `decision_receipt` 恒 `unknown-decision` refused(2009-2010)。
7. **dp2 是 PM 主动、机器不碰。** `pm-orchestrator.ts:1932-1950` 明说机器从不问 dp2、从不按答案动作，旧 `narrow`→`steer` 自动短路
   已移除；`decideDp2Checkpoint` 已退役(2074-2089)，仅保留 `DP2_STEER_FILE`/`DP2_NARROW_MARKER`/`DP2_STEER_REQUEST_HEADER`
   作为 worker 消费契约(1955-1966)。PM 通过 `ask_decision` 填 material（`DECISION_MATERIAL_PROMPTS.dp2` 768-773）再自己写 steer 文件。
   PM 分支注册无 taskPath（index.ts:102 `registerAskDecisionTool(pi,{initiatorRole:"pm"})`）→ `tracePath` 为 undefined，
   PM 的 `[DECISION]` 行不落盘（appendDecisionTrace 1632 对 undefined 直接返回）。
8. **dp3 历史自动 helper 仍在但生产不可达。** `attemptDp3Clarification`(4156) 是唯一调用点(4185)，它**不传 `material`**；
   `decideDp3WorkerClarify`(5654) 在 `input.material === undefined` 时直接 `escalate("input-incomplete","no agent-prepared dp3 material (ask_decision owns dp3)")`(5678)，
   于是 `answer`(auto steer)/`handling` 分支(4234-4266, 4211-4233)在生产恒不执行，只留 `[DECIDE]` 行 + 人路。
   当前 dp3 的真实材料路径只有 `ask_decision`（material dp，consumed 自动写，无 steer）。
9. **dp25 与其余 DPs 的业务合同未改**：dp25 由 `mw decide sign --stdin --json`(buildSignArgv 864) 一次判断即签，
   工具不二次签收（1382 自述；1456-1478 映射），`second_approval` 恒 0。

## 证据

- `decision-tool.ts:1219-1240` `runAskDecision`：dp25→sign(1238)、material→(1239)、其余 legacy(1240)；role 拒绝(1228)。
- `decision-tool.ts:1294-1371` `runMaterialAskDecision`：material 校验(1299-1305)、`buildDecisionToolMeta`(1309)、
  viaStdin 信封(1316-1322)、`buildSelection`(1336)、`consumed` 自动写(1358-1367)。
- `decision-tool.ts:744-758` `buildSelection`：dp3 走 `resolveHandlingSelection`(728)，其余取首个 question 的 string value。
- `decision-tool.ts:1500-1545` `runLegacyAskDecision`：state 构造 + `missingDecisionStateFields` 预检 + 无 selection/feedback；
  `question` 过滤 1525-1531。
- `decision-tool.ts:1877-1962` `ask_decision.execute`：key 归属拒绝(1894-1902)、task_key 拒绝(1904-1908)、
  `asked.set` 仅 material(1916-1919)、trace `[DECISION]`(1928-1937)、失败计数与 `terminate`(1959-1960)。
- `decision-tool.ts:1987-2058` `decision_receipt.execute`：`asked.get`(2004)、action/outcome 白名单(2015/2031)、
  `writeDecisionLifecycle`(2046)、`[DECISION_RECEIPT]` trace(2047-2050)。
- `decision-tool.ts:889-921` `writeDecisionLifecycle`：receipt 解析(903)，`receipt.recorded !== true` → failed(907-911)，duplicate 保留(916-918)。
- `decision-tool.ts:1657-1756` `MATERIAL_SCHEMA` + 169-180 enforced 集合 + 219-224 material 集合（dp7 均不在）。
- `pm-orchestrator.ts:1932-1950` dp2 段注释；`:1955-1966` steer 契约常量；`:2074-2089` 退役说明（无机器调用者）。
- `worker-mode.ts:3279-3321` `consumeDp2NarrowSteer`；`:3327`/`:4313` 两个调用点；`:4939` `formatDp2NarrowSteer`。
- `worker-mode.ts:4156-4270` `attemptDp3Clarification`（唯一 `decideDp3WorkerClarify` 调用 4185，未传 material）；
  `:5654-5690` `decideDp3WorkerClarify` 前置 escalate（5678）；`:5700-5710` 子进程信封；`:5720-5756` 答案/handling 映射；
  `:5765` `formatDp3AnswerSteer`。
- `decision_points.py:640-670` dp2/dp3/dp7 registry（问题 id、choices、executor）；`:1567-1573` dp7 required_state_fields；
  `:496-512` `_unwired_executor`；`:521` "intent=answer 永远不触达执行器"。
- `index.ts:84-103` 两角色注册（worker 带 taskPath，PM 只带 role）。
- `decision_lifecycle.py:96-116` OUTCOMES/EXECUTED_ACTIONS/RESULT_STATUSES；`:796-880` record_consumed/executed/settled。

## 残留与未验证

- 未全文：`pm-orchestrator.ts`(123k)、`worker-mode.ts`(~6000 行)、`triage-client.ts`(48k)、`mw.py`、`decision_lifecycle.py`。
  本报告未声明这些文件里不存在其它 dp2/dp7 调用者；已核对的是"注册点 + 明示退役注释 + 全仓 grep 无 dp7 消费者"。
- **不等同于运行事实**：dp7 的 `input-incomplete` 是按 registry required_state_fields 静态推断，未真实 ask（禁止）。
- dp3 helper 走 `runDecideMw` **未置 `viaStdin`**（worker-mode.ts:5700-5706），却送 `{material,meta}`；Python 侧该路由是否接受未验证（helper 本来就不可达）。
- dp2 steer 文件的 PM 写入端无代码（PM 用通用 write 工具）：未在本轮核 PM 提示词是否明确要求写该文件（属 RQ9 注入面）。
- PM 窗口 `tracePath=undefined`：PM 决策不落 trace 为静态结论，未在真实 PM 会话验证。
- 未运行任何测试/build，未调用真实 ask/provider，未读活 gate/ledger/凭证。

## 上下文来源

- `.agenticdoc/goal.md:5`
- `.agenticdoc/mw-dp-consolidation/tasks/RQ8-decision-action-consumption.md`（本卡）
- `.agenticdoc/mw-dp-consolidation/workers/dpc-rq8-decision-action-consumption/task.md`（dispatch card）
- 源码：decision-tool.ts（全文）/ pm-orchestrator.ts(1932-2090) / triage-client.ts(375-435) / worker-mode.ts 指定段 /
  decision_points.py 指定段 / decision_lifecycle.py 常量区 / index.ts(84-103)
