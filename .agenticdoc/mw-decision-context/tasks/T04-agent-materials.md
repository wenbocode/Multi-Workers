# T04 PM/Worker材料工具与双角色dp3

type: coding
ac_refs: AC-005, AC-006, AC-007, AC-010, AC-014
vc_refs: VC-005, VC-006, VC-007, VC-010, VC-014

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`。种子`packages/coding-agent/src/extensions/agent-team-loop/index.ts:84` ask_decision worker限定，`pm/decision-tool.ts:267`通用工具state，`worker/worker-mode.ts:5476` buildDp3Candidates/resolveDp3CandidateAnswer/buildDp3State/decideDp3WorkerClarify（按符号）。T03独占ui-bridge/triage-client/pm-orchestrator，不争写。
T01/T02已done全文report在workers/dc-t01-contract及dc-t02-lifecycle；新registry生成物可读。T05运行独占mw/签收，CLI本地meta接口见本卡，不改Python。

## 要求
- PM/worker共用现ask_decision扩展入口，非新生成服务。PM仅PM主动dp2；worker不能借入口调用PM限定dp2或生产dp25签收。
- 普通提问Agent按固定提示先提供question原文、background{task_goal,current_state,decision_reason,constraints_impact}与针对问题处理handling_options[{id,label,description}]。未知显式未知，不自动检索旧事实答案替代生成，不Jev生成文本。两角色Worker→PM/PM→用户均能调用，结果精确原提问者/候选，单选原生handling标签c1..cN。
- dp3新候选>=2<=5、id连续、label<=80字符原生限制、description非空且不截断说明；不要旧fact/intent/reuse/answerable多问或预存旧回答复用。旧intent权限/复用功能只在与新已替代路径重叠时改，不删其它功能。
- PM dp25提供delivery_goal/actual_completion string，verification_evidence{verified:string[],unverified:string[]},unfinished_impact:string[]，[]可合法真实无缺口；材料生成普通Agent已有上下文，不counts代证据。发起sign直接由T05实现，不PM二次批准；continue/user-confirm结果需PM提出具体缺口/待确认。
- dp2任务三原文字段+pm_decision_background string，可选worker_execution string，保留原instructions/choices/labels；提供工具schema/固定准备提示给PM，未worker合法，不自动动作/杀worker/授权。收窄变目标仍问用户、直执先协调写面、高风险提出具体问题。
- `mw decide run <dp> --stdin`本地envelope `{material,meta:{record_version:2,logical_id,key,task_key:null|真实task,initiator_role:'pm'|'coding'|'research'|'review',retry_of:null|前id}}`；UUID每真实调用新id，不猜最近task。T05最终cmd如有必要报告PM；不临时实现第二CLI。
- 自动反馈经`mw decide lifecycle --stdin` `{meta,decision_id,dp,stage:'consumed'|'executed'|'settled',event_id,answer?,action?,result?,outcome?,reason?}`，匹配T02 writer；consumed收到，executed确有动作，settled本次真实处理完成，不模型返回就填executed。工具可提供处理结果回执操作供Agent在实际行动后自动使用，不额外人工点接收。未知动作只未记录。T02角色小写pm。
- 先独立材料/权限/faux工具生产路径RED→GREEN，T05 CLI可用后真实合成argv/stdin一次接线验证；仅手填日志不是闭环。严禁测试真实provider或用户凭证，tmp HOME/USERPROFILE/PI_CODING_AGENT_DIR env合成和读前spy。suite/harness.ts+faux provider。无service/build/install/browser/Jev/commit。
代码标准top-level imports/erasable TS/no any/可配keybind；现扩展API若需改使用方式须读完整pi相应docs/examples，不凭猜；不改pi核心。大文件分页完整读≤120行避免回灌，10分钟内RED计划，禁止泛研究。首写保存允许面完整hash/diff/untracked保留外来claims/review-split。

## 写入允许面
- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/decision-context-agent-materials.test.ts`

## 写入禁止面
ui-bridge/triage-client/pm-orchestrator/生成物/Python/其它测试/core/框架脚本/配置/dist/deps锁/凭证/其它key；必要共用TS接口改动报告PM精准认领，不越面追绿。

## 验收命令
`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-context-agent-materials.test.ts`（harness faux+合成env），真实TS工具执行回执+生产stdin边界断言，不realprovider。定向类型可检查。完整npm check PM稳定统一；禁止full vitest/npm test/build。

## 改动历史
初派；T01 42P、T02 61/88/25P局部交付，T05 CLI实现中。独占上述TS面，保留并发已有diff。旧测试断言迁移统一T08收口，不分散修。

## 交付格式
report.md+自身evidence正确RED/GREEN原日志/UTC/exit/hash、两角色真实入口schema/权限/材料与candidate选择、PMdp2/dp25提示、实际反馈调用事实、局部faux/HTTP/平台未验分列。T05接线需项和低影响债集中一份报告，无新增研究或滚动碎任务。
