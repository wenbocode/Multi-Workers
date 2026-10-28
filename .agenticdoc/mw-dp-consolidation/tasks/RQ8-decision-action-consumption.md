---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-decision-action-consumption.md
---
# RQ8 — DP答案如何成为PM动作（现状，不设计）

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。DP7用户定义是相位门失败归因后的PM下一步处置选择；流程/选项未敲定。用户问DP选择后如何成为下一步动作并注入窗口上下文。入口 `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1790`、`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1948`。RQ9核具体注入，本RQ核工具返回/消费/动作边界。

## 要求
1. 全文读decision-tool.ts，跟踪runAskDecision/material branch及注册execute；沿必要调用读triage-client/DP2与DP3消费者完整相关函数。声明外围未全文范围，不以函数存在冒充生产调用。
2. 分别说明直接ask工具结果回当前LLM上下文、consumed/执行/settled记录、真实PM动作是谁执行、是否有通用selection-to-action转换器。记录反馈不是动作，不宣称acted=true必定业务已执行。
3. 核dp7现材料/问题/执行器及接线限制；dp2 PM主动调用、PM写steer、dp3 Worker历史自动helper与当前材料路径、dp25 CLI签收分清，四DP业务合同不改。
4. 只读静态，15分钟预算，证据<=180行；禁测试、build/install/commit、真实ask/provider、服务操作、凭证/活gate/ledger读取或源码修改，不自建report.md。

## 交付格式
证据及最终回复均四节：`## 结论 / ## 证据 / ## 残留与未验证 / ## 上下文来源`。链路给path:line+完整函数名；明确未接线、建议、真实动作的区分。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-decision-action-consumption.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-decision-action-consumption.md

## 写入禁止面
其他证据/PM文档、源码、配置、活gate/ledger、凭证、服务；自身自动回执仅框架维护。
