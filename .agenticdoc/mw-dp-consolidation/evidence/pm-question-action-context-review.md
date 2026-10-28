# PM问题、DP答案、动作与窗口上下文：本轮静态综合

## 范围与结论

用户原问题：PM能否自动枚举问题及问题描述？目前PM将问题抛给人的机制是什么？DP选择完成后，如何转成下一步动作并注入PM窗口上下文？

本轮只读源码调查，继续SPEC，不敲定DP7/15/20流程、schema、枚举、消费者，不修改源码/活授权或推进phase。三并行RQ唯一证据已回读、终态全部acked；ack不代表正式验收。

1. **PM模型可以根据现场材料整理多个问题和问题描述，但当前审到的PM入口没有跨任务统一问题清单生成器。** 机器摘要/告警不等于完整业务问题；模型整理不保证完整、去重、排序或可靠回答绑定。没有把有限搜索提升为全仓不存在的证明。
2. **当前“报PM”和“报人”不同。** 终态回读/告警/部分门提醒调用deliverPmAlert，让PM模型收到事件。PM继续提示词要求needs-clarification时整理问题向用户澄清，人工主要通过会话回答。pending gate另有gate id和命令式应答路径。没有查证一个统一的人类问题列表与回答→任务自动恢复器。
3. **PM主动ask_decision时，结果已是当前turn的工具返回，无需再重复外部注入。** PM依据selection与已有材料，自己调用被允许的工具落实动作；收到答案、实际动作、settled分开记录。没有本轮已证实的通用DP7选择→动作转换器。
4. **外部事件的PM窗口运输已存在，但不是DP7消费者。** deliverPmAlert触发空闲turn；流式中进steer队列，待agent循环消费。displaySummary空闲时仅显示/入上下文、不唤醒；流式时同样会默认排steer。不能把可显示、入上下文、唤醒、排队、已执行等同。
5. **DP7当前定义与用户抽象不符且未接线。** 注册表当前仍是gate_cause原因选项，不承载“归因后PM下一步处置”。其材料/生产者/答案消费者/回执支撑均不能假定已具备。不能因ask工具enum允许dp7就称它已可推进。

## 可核查的现有链路

### A. 问题与报人
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1868` PM_CONTINUE_HINT：给PM模型“needs-clarification→整理问题向用户澄清”的指令，不是问题清单生成器。
- 同文件 `startWorkerPollLoop:2091`：事件按窗口watch/派发归属过滤；终态正文在2294–2303经deliverWorkerResult/readback运输。2366–2370的gate提醒附`/autopilot gate <id> approve|reject`，是可绑定gate的特殊路径，不是普通聊天回答的通用绑定器。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1112` readTerminalDetail：needs-clarification取Questions首行，退回log末行或no output；这是widget摘要，不能替代正文/业务问题。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1137` unavailableDirective：服务不可用时明确停止门控动作、禁止猜/绕过、报告blocked并等人工。是当前失败处理契约，不证明某个工程问题本质必须人工裁决。

### B. 答案与真实动作
- `decision-tool.ts:1877` ask_decision.execute返回content文本；成功包含selection的路径回到当前调用模型。
- `decision-tool.ts:1294` runMaterialAskDecision：校验PM/Worker原材料，将answer对应回所送候选，写consumed；不执行业务。
- `decision-tool.ts:1987` decision_receipt.execute：本窗口已发起/同logical_id的明确executed/settled回执，只记账，不执行动作。不能泛化到所有legacy DP都具备该能力。
- `pm-orchestrator.ts:2081` RETIRED说明：自动dp2问答/写steer移除；checkpoint唤醒PM，由PM主动提供业务材料问dp2并按权限处理。
- `worker/worker-mode.ts:3279` consumeDp2NarrowSteer：PM可手写steer-dp2.md，Worker读文件后sendUserMessage(followUp)，并作消费标记。它不是selection自动生成派单/修复的消费者。
- `decision-tool.ts:1385` runSignoffAskDecision为dp25专属`mw decide sign`链：CLI承担一次判断/签收，不能据此把全部DP称纯无副作用，也不能据此泛化自动业务执行。

### C. 窗口运输
- `ui-bridge.ts:201` displaySummary；`:218` deliverPmAlert；`:232` deliverWorkerResult。
- `packages/coding-agent/src/core/agent-session.ts:1437` sendCustomMessage：nextTurn暂存；流式followUp/steer排队；空闲triggerTurn调用_runAgentPrompt；空闲无trigger仅追加消息与session。
- 同文件 `sendUserMessage:1480`调用prompt，空闲可以启动turn，流式需指定排队方式；名称里的User代表用户消息角色，**不表示向真人发送通知/问题**。
- 核心只读，无pi-core修改。外部事件到PM上下文并不自动携带用户授权，也不自动执行业务工具。

## 对RQ原报告的限定/纠正（原件保留）

1. RQ7“全扩展无ui.select”“报人只有三处”“不存在统一枚举器”“唯一带id绑定是decision”的绝对范围不采纳。主审全文+外围片段/grep只能支撑已核路径；gate已有id绑定，未审遍外部调用/所有UI。
2. RQ7把nudgeGoalUnestablished的sendUserMessage当直接“对真人提问”不正确：核心sendUserMessage启动/排队模型prompt，不是human input API。PM/会话可显示它，但不能由此声明已收真人问题/答案。
3. RQ7机器合成Questions是已核finish路径事实，不推广到所有Worker/历史产物的Questions来源。固定旧DP2 canonical/version残留不能当当前业务问答合同；真正材料/原文合同保留不改。
4. RQ8“答案唯一消费面”“全仓selection只有两处”“唯一端到端通道”“executed/settled只能由工具写”均限定到其审到的路径。真实dispatch/CLI等也有专属写者；dp25自己有签收副作用。跨模块/全仓穷尽未证明。
5. RQ8 dp7按工具buildDecisionState未提供gate字段→Pythonrequired字段拒绝是静态推断，未作真实ask探针，不声称当前服务已复现。缺少通用材料/消费者是当前设计债，不要求立刻修源码。
6. RQ9“ask_decision不是注入”应表述为**不是sendMessage外部消息注入，但工具结果本身进入模型上下文**。二者术语不能造成“PM看不到答案”的误解。
7. RQ9把dp3旧answer steer分支当当前可用链不采纳：Worker settle唯一调用没material，decideDp3WorkerClarify在5678明确退回input-incomplete；所读当前材料返回handling，不是旧事实answer。只保留分支存在的事实，当前生产路径并未证明可达。
8. RQ9把dp2/dp3都称“文件→followUp”不精确：dp2有文件，旧dp3分支是函数直接sendUserMessage。其表中“工具不显示”“Worker不会唤醒”“当前turn结束即执行followUp”也不采纳：工具卡可显示；空闲sendUserMessage可起turn；followUp在循环本将停止时消费，不必等同一个assistant响应结束。注入不等于选中动作已执行。
9. RQ9外围pm-orchestrator的5793行和证据74行口径不可靠（RQ7主审全文2680行）；不据报告数字声明覆盖/行数，函数锚点以源文件读取为准。

## 尚未决定

- 可供继续讨论的DP7抽象：PM依据相位门失败、归因、已有尝试和约束准备明确问题及具体行动候选，DP判断接下来选择哪种处置。这是建议分工，不是用户已批准schema、固定菜单或流程。
- 本轮说明现机制，不确认新的触发次数、状态、优先级、调用顺序、行动枚举或自动执行权限。H02仍暂停。
- 旧服务stale提示PID43656，本轮mw_status观察PID51788；没有重启操作/已加载最新模块的证明。源码结论不等于当前运行实例验收。

## 来源与验证限制

- RQ7：`evidence/research/spec-pm-question-generation.md`，全文pm-orchestrator，外围片段。
- RQ8：`evidence/research/spec-decision-action-consumption.md`，全文decision-tool，外围片段。
- RQ9：`evidence/research/spec-window-context-injection.md`，全文ui-bridge，核心完整相关函数/外围片段。
- PM独立回读三证据/终态、校验上述提示词/运输/核心/旧helper关键函数；不声明PM全文审遍外围/全仓零遗漏。
- 无测试/build/install/commit、无额外ask/provider探针、无服务操作/活gate与ledger改动；派发走正常授权research，可能使用原有dp1，不能宣称整个研究零模型。
