# T03 PM dp1原文与dp2去自动执行

type: coding
ac_refs: AC-001, AC-003, AC-004, AC-010, AC-014
vc_refs: VC-001, VC-003, VC-004, VC-010, VC-014

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`；源锚`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:528` buildDp1DispatchState、`pm/pm-orchestrator.ts:2336`旧dp2调用/auto narrow。T01 Python契约/T02反馈正在实现，T04后续独占decision-tool/index/worker-mode。不双写。

## 要求
按用户批准修改dp1 producer用任务目标/要求/交付物完整原文，类型问题仅coding/research/review，不加risk/reason问；vision/rag等原生角色边界保留，派发建议不扩大自动改type授权。三固定说明用户原定义。
dp2只PM主动：去pm-orchestrator自动dp2调用及其旧自动narrow任务执行分支，保留通用watchdog/checkpoint告警，不新增自评产物/等待/异常阈值。PM手动入口由T04受管工具负责，你不写decision-tool。删除已明确替换路径获用户授权，无需重复问。
CLI T05将实现`mw decide run <dp> --stdin`（本地envelope），Producer材料`{material:{task_goal,task_requirements,task_deliverables},meta:{record_version:2,logical_id,key,task_key,initiator_role:'PM',retry_of:null}}`，独立UUID生产，task派发前预留真实id、不猜最新。如现triage transport必须复用现stdin wrapper，按现架构精准接线并报告T05要求；identity绝不进model。
现Python CLI稳定前验证真实TS producer→stdin或loopback mock边界，后续集成T05一轮统一。dp1实际consumer收到及派发/保留类型/不一致告警结束后的真实反馈，T02唯一Python writer/T05 CLI精确签名交付后接，不TS裸append、不consumed当settled。先独立producer/去自动路径实现，不等接口空转。
正确行为RED先于实现；使用suite/harness.ts+faux，不激活真实provider/token/真实凭证。首写保存允许面基线hash/diff含untracked，外来review-split/claims功能保留，别覆盖。大文件完整分页read≤120行，不无限dump/研究；10分钟内产出行为RED计划。已批准设计最高优先，低影响债集中账。
不改extension API，无需核心改动；若涉及API时先读pi对应完整docs/examples，禁止猜类型/内联imports/any，现node_modules类型可查。配置键绑定不能硬编码。

## 写入允许面
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/test/suite/decision-context-pm-producers.test.ts`

## 写入禁止面
其它TS（decision-tool/index/worker-mode/生成物）、Python、旧测试、pi核心/框架脚本/dist/deps锁/配置/真实凭证/其它key；不越面追旧断言GREEN。

## 验收命令
`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-context-pm-producers.test.ts` 使用harness+faux/env合成，逐条日志UTC/exit保存；相关静态类型可窄检查。npm run check PM稳定统一，不worker全仓biome写。不得npm test/build/full vitest/service/browser/Jev/commit/install。

## 状态
代码完成/局部验证通过（15P原日志PM全文readback report150行/output/run，ack），实际CLI与反馈落盘未实现，最终T08承接；T03角色PM≠T02 pm、反馈信封不同、2559B材料≠T01 2000B预算需按integration-handoff.md统一，不扩研究。

## 改动历史
初派；先独立producer和自动路径撤除，T01/T02/T05联动后续一次接线；不新任务。保留允许面当前其它keydiff，精准修改本设计范围。

## 交付格式
report.md+自身evidence RED/GREEN原日志/UTC/exit/hash、dp1最终材料原文与实际stdin例子、去自动dp2证据/告警仍在、consumer回执接线坐标/需T05精确CLI约束、局部 vs全链分列。低影响债集中报告不研究。
