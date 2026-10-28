---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-window-context-injection.md
---
# RQ9 — 事件/答案到PM与Worker窗口上下文运输

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。用户问当前PM报人机制与DP选择后如何变动作注入窗口，先说明现有机制，不敲定新流程。入口 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:201`、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4912`。RQ7问题来源、RQ8答案消费，本RQ只核上下文消息与文件steer运输。

## 要求
1. 全文读ui-bridge.ts；跟踪deliverPmAlert/displaySummary、startWorkerPollLoop调用与gate提醒；worker-mode只要求相关完整消费者函数（steer-dp2.md、DP3 answer steer）。报告全文/局部/未读范围。
2. 校验pi.sendMessage triggerTurn与sendUserMessage followUp/steer的实际核心实现（只读相关完整函数与类型），不修改pi核心，不以注释代替调用证据。指出显示、进入上下文、唤醒、排队、实际执行四者差异。
3. PM当前调用ask_decision的tool result与外部消息注入不同。记录当前是否已有通用DP7选择注入器；不得把DP3注入Worker和DP2 PM手写steer当同一通用机制，也不能把已无调用的旧helper称当前自动链。
4. 15分钟预算，证据<=180行；禁测试/build/install/commit、真实ask/provider、服务操作、凭证/活配置/gate/ledger读取或任何源码写入，不自建report.md。

## 交付格式
证据与最终回复均 `## 结论 / ## 证据 / ## 残留与未验证 / ## 上下文来源`；每条链有path:line+完整函数名。运行实例模块身份和实际delivery效果未执行就标未知。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-window-context-injection.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-window-context-injection.md

## 写入禁止面
其他证据/PM文档、源码、配置、活gate/ledger、凭证、服务；自身自动回执仅框架维护。
