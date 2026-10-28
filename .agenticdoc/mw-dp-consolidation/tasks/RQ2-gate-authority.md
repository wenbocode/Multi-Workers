---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-gate-authority-20261024.md
---

# RQ2: 四门职责与现有授权边界

## 上下文
目标锚点：`.agenticdoc/goal.md:5`。需求：`.agenticdoc/mw-dp-consolidation/spec.md`、`key-decision.md`。用户确认dp6承担正式质量审核；dp15按当前设定边界给autopilot模式做gate审核；dp6/dp7/dp15/dp20联合设计，dp1/dp2/dp3/dp25业务不改。
入口证据：`packages/multi-workers/decide_registry.json:1000`（dp15含六类gate），`packages/multi-workers/autopilot/gates.py:82`（GATE_KINDS），`packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:1`（人工answer writer）。还需追踪conductor实际创建与消费，不能据旧登记的未接线注释推断现有全人工。
RQ2只负责四门业务、实际授权、与dp2/dp25的交叉，不负责25DP删除inventory（RQ1）和历史UI迁移（RQ3）。

## 要求
1. 对stage-confirm/stage-close/stalled/budget-exhausted/goal-change/xkey-authorize分别追踪生产创建、机器判据、自动放行、人工fallback、approve/reject和authorizes实际动作，列路径:行号+符号；特别区分既有自动权限与需要人类明确授权的边界。
2. 核对dp6当前质量门/L3与正式审核证据链、dp7当前失败分类及处理缺口、dp20阶段收尾与dp25单key签收；不要把建议、采纳、round ok当真实动作或完成。
3. 提出四门联合职责矩阵和最多两套有实际差别的设计建议：触发、材料、问题/选项、审核归属、verdict动作、不可用/失败策略。不得把提案称用户批准。
4. 对stage-close在dp15/dp20之间、stalled在dp15/dp2之间给出非重复审核分工；dp6必须正式审核，不改成仅争议建议；dp25不能新增第二次签收审批。
5. 不扩大或未经批准缩小现有边界；任何需要新增执行权、改框架门禁或更换现有gate语义的提案必须点名待批准事项。
6. 时间预算约15分钟；报告<=180行。聚焦符号定点读取，不无界全仓dump。事实不足直接记未覆盖面。
7. 不运行测试、真实模型请求、共享服务、monitor、sign、build、install、commit；不调用ask_decision；不访问凭证，不改phase。

## 交付格式
唯一证据含：六类gate现有授权表、四DP现状/缺口、联合职责及触发矩阵、建议动作与失败策略、待用户决策、未覆盖面。每个关键事实附路径:行号+符号。先落盘骨架再填证据；可用worker_file按本key的evidence相对路径落盘。最终回复只给摘要和证据路径，不写spec或design。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-gate-authority-20261024.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-gate-authority-20261024.md

## 写入禁止面
源码、registry和生成物、配置、framework、spec/design/plan/pm-state、其他RQ证据、生产ledger及gate文件禁止修改。除框架自动管理的自身worker产物外，不写其他路径。
