---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-pm-question-generation.md
---
# RQ7 — PM问题枚举、描述与报人机制

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。用户先聊DP抽象、不敲定流程；DP7目前讨论相位门失败归因后的PM下一步选择。用户问PM能否自动枚举问题及描述、当前如何抛问题给人。入口 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1868`、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1121`。RQ8另核DP返回/动作，RQ9另核注入API，本RQ只核问题来源和“报PM/报人”的区别。

## 要求
1. 全文读pm-orchestrator.ts；沿必要函数追踪Worker Questions、gate reminder和checkpoint内容来源。未全文读的外围文件明确声明，不能仅靠注释宣称全链已通。
2. 区分PM模型根据上下文整理问题、机器提取既有Questions/失败摘要、固定提示词/告警、结构化决策材料与系统统一问题枚举器。找有没有实际通用枚举器，不将没找到夸大成全仓不存在。
3. 列实际生产者→载体→PM消费者→人工问题出口；尤其PM窗口被唤醒不等于人已被提问，UI通知不等于用户回答自动绑定任务。
4. 只读静态，15分钟预算，证据<=180行；禁止tests/build/install/commit、真实ask_decision/provider探针、服务起停、凭证/活gate/ledger读取和任何源码写入。不自建report.md。

## 交付格式
证据及最终回复均含 `## 结论 / ## 证据 / ## 残留与未验证 / ## 上下文来源`。核心结论附path:line+完整函数名；没验证的运行中bundle/模型效果保持未知。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-pm-question-generation.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-pm-question-generation.md

## 写入禁止面
其他证据/PM文档、源码、配置、活gate/ledger、凭证、服务；自身自动回执仅框架维护。
