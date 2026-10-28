---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-pm-orchestration-20261026.md
---
# RQ15 — PM准备、路由、后继与真实处理接口设计

## 上下文
`.agenticdoc/goal.md:5`为锚；`.agenticdoc/mw-dp-consolidation/spec.md:1`完整53AC已确认并锁定于2026-10-25T23:37:14+08:00，本key DESIGN。只作联合设计取证，未授权设计/schema/写面/实现。本RQ主责TS PM工具/窗口注入/后继组织；不替协议、gate执行、Worker自主终态、签收硬门/投影其他RQ下结论。

## 要求
1. 全文读spec、PM毕业考/问题上下文综合，全文读采用的主要源文件：packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1、pm-orchestrator.ts、ui-bridge.ts，注册入口index.ts及相关纯测试按需全文读。给真实producer/writer/consumer/caller path:line，注明未覆盖，不拿helper存在或旧注释证明运行接线。
2. 比较至少两种事件送达PM→准备问题/候选/背景→固定直调或临时路由→目标材料判断→权限内执行→真实回执的设计方案，明确角色资格/decision主体与任务关联；sendUserMessage是模型上下文而非真人，工具结果已入模型上下文，不重复组织同事项审批。
3. 具体设计建议：gate选择steer/need_fix后PM发起对应后继请求，区分选择/请求/失败/执行/settled；回合结算不等于业务完成。不因路由授角色，不把PM强行作为Worker自身可达性主体，不把不可用默认候选/放行，不造id/已执行回执。当前自动dp3缺材料/混填反馈事实与未来角色设计分开。
4. 保持dp-pm-steer四项目标/预算不变，split独立并行且协调在途写面，direct-exec必须有当前PM上下文理由，escalate为具体用户必要性。给准备材料、关联/幂等及重审/消费接口建议、精确候选写面与AC011/012/014/040～045/049～052的L0/L1/L2 VC断言，不替RQ13冻结业务schema。
5. 25分钟有界只读报告，建议<=220行。禁源码/工具schema/registry/配置/活gate/ledger/凭证/他key/原报告/PM文档修改，禁测试/build/install/commit/服务操作/额外ask_decision/provider探针。只写唯一证据，不建report.md；框架自动run/output由框架维护。

## 交付格式
唯一证据及最终回复均有`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。事实/目标/方案/权限未定分开，列完整读取及未覆盖；不宣称设计、实现、AC/QG/签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-pm-orchestration-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-pm-orchestration-20261026.md

## 写入禁止面
除上述证据外所有文件；不人工修改框架自动回执。
