# T08 TS生产接线与旧断言集中迁移（独立子写面）
type: coding
write_face:
  - packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
  - packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts
  - packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
  - packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts
  - packages/coding-agent/src/extensions/agent-team-loop/index.ts
  - packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
  - packages/coding-agent/test/suite/decision-context-integration.test.ts
  - packages/coding-agent/test/suite/decision-context-pm-producers.test.ts
  - packages/coding-agent/test/suite/decision-context-agent-materials.test.ts
  - packages/coding-agent/test/suite/triage-client-state.test.ts
  - packages/coding-agent/test/suite/triage-dispatch.test.ts
  - packages/coding-agent/test/suite/decision-association.test.ts
  - packages/coding-agent/test/suite/dp2-narrow.test.ts
  - packages/coding-agent/test/suite/dp3-answer.test.ts
  - packages/coding-agent/test/suite/decision-tool.test.ts
ac_refs: AC-001, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-014, AC-020
vc_refs: VC-001, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-014, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`；批准spec/design/plan。种子`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3218`真实dp1 dispatch回执位，`pm/decision-tool.ts:1`T04工具。T03/T04已done停写，T05CLI已交付47P，报告在各worker完整读，必读evidence/integration-handoff.md。另T08Python写面并行，你只TS，不改其文件。

## 要求
严格已批准功能闭环最高优先，非阻塞细节集中账，不泛研究。
- dp1真实consumer收到选择和真正派发/保留类型/告警处理后的自动consumed/executed/settled，通过T05 `mw decide lifecycle --stdin --json --project` `{meta,decision_id,dp,stage,event_id,...}`；同次精确关联，写失败动作不重复。不能只纯构造器或TS裸append。不模型返回就executed/settled。统一小写pm meta（T05接受大小写不须兼容两套builder），能复用已有最小builder不强制泛重构。
- dp2仅PM主动、原问题/标签不改，dp3两角色普通Agent提供背景候选且结果给提问者；receipt真实动作回执不假授权。worker完整activate必须隔离合成卡/harness定时器清理验证（可不启动实际worker业务过程但入口需证），不靠源码grep独证双角色。
- dp25受管PM路径选finalize需直接实际签收，不让ask_decision仅`run dp25`返回后要求PM二批再sign或重新模型。优先工具直接调用T05 `mw decide sign <key> --stdin --json`一次真实判断并签；continue/user-confirm则具体PM补缺/待确认结果与真实回执，自动签是已批准。观察路径另Pythonlane，不自动扩大dp2/dp3权限。
- T04真实CLI wiring日志disabled不验enabled材料，三阶段还各新logical_id，不能据此认同次链。用合成loopback+实际Python CLI证明TSproducer→POST+自动consumed→实际receipt；包含dp1、PM/workerdp3、PMdp2有/无worker、dp25finalize/continue/user-confirm；节点reader由Pythonlane，精确event/meta/decision_id不可手填fake最新。
- 保留vision/rag/codex能力，原自动dp2/auto narrow替换批准，旧dead seam在pm-orchestrator可清理或明确退役，不复活。旧TS断言迁移到新契约：不能保留被明确替换业务兼容、不删安全测试追绿。
- T01固定2000B和T03实卡2559B差异Python lane按实际完整材料与transport预算统一；TS材料原文不得静默裁剪，预算规则最终按发布接口（旧素材大于2000B不要预先宣布发送已通）。
TDD行为RED先行再最小GREEN，collection/修后回放非test-first；测试suite/harness.ts+faux、tmp HOME/USERPROFILE/PI_CODING_AGENT_DIR/env清理和读前spy，禁止真实provider/凭证/Jev/browser/build/install/service/commit。node_modules类型查不猜，不any/动态inline import/参数属性，不改pi核心；扩展API如改变按pi完整docs/examples。
首写允许面完整hash/原文快照+diff含untracked保留其它会话claims/review-split。大文件全文分页≤120行，10分钟内定点行为RED计划，禁止研究扩散。

## 写入允许面
- packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts
- packages/coding-agent/src/extensions/agent-team-loop/index.ts
- packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
- packages/coding-agent/test/suite/decision-context-integration.test.ts
- packages/coding-agent/test/suite/decision-context-pm-producers.test.ts
- packages/coding-agent/test/suite/decision-context-agent-materials.test.ts
- packages/coding-agent/test/suite/triage-client-state.test.ts
- packages/coding-agent/test/suite/triage-dispatch.test.ts
- packages/coding-agent/test/suite/decision-association.test.ts
- packages/coding-agent/test/suite/dp2-narrow.test.ts
- packages/coding-agent/test/suite/dp3-answer.test.ts
- packages/coding-agent/test/suite/decision-tool.test.ts

自身worker沙盒evidence/report由框架授权，不作为源码路径条目；不写PM状态。

## 写入禁止面
Python/UI/生成物/其它TS/其它测试/pi核心/框架/配置/dist/依赖锁/凭证/其它key；必要接口扩权先报告PM不自改。完整npm check由PM稳定统一，不worker全仓biome --write。

## 验收命令
`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-context-integration.test.ts`；全部修改测试定向逐文件run；相关定向tsgo及本面biome只读，错误必须修本key（19旧type errors不是他key豁免）。合成loopback actual Pythonargv/stdin可特定integration fixture，不paidprovider。禁full vitest/npm test/build。

## 改动历史
固定T08独立TS lane，另Python lane同时集成其面（不争写）。T03 15P/T04 28P局部但全链未闭；旧TS42F/83P+dp3旧23F/13P+decision-tool4F集中迁移，不碎修复。
2026-10-23首次尝试dc-t08-ts-integration终态done但业务BLOCKED：写面尾部中文句号造成路径不匹配，代码/测试零写入。仅修卡为逐行精确路径，重派同一T08写面，不修改门禁算子、不扩权；旧尝试草稿与基线保留，后续必须核对当前源码后运行真实行为RED，不将草稿或旧基线当GREEN。

## 交付格式
report.md+原RED/GREEN/UTC/exit/hash+真实HTTP/同次反馈/双角色入口和自动签证据；AC/VC输出仅运行断言，不预写伪成功；未验平台分列，低影响债集中，必要阻塞明确。完成所有本写面后PM独立稳定验收/review/quality，不能先冒称项目done。
