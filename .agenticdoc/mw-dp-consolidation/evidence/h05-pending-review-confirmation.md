# H05：pending-review复核与恢复（已确认）

## 本轮确认

PM提出pending-review不默认等人；事件或到期只触发复核，恢复、整改或收尾须按有效证据及dp-gate-approve四选项决定。用户答“认可”。

## 已确认业务规则

- pending-review等待条件/证据复核，不默认等待真人批准。复核期限、依赖key交付或新证据可触发重新评估；触发不证明恢复条件满足，也不自动证明人工必要性。
- 判断原目标是否有效、原阻断是否解除，以及当前证据/授权/预算是否支持恢复；不能仅凭经过一段时间恢复。
- approve：上述条件满足，按送审前PM note恢复。
- steer：任务组织/推进方式需调整，PM发起dp-pm-steer。
- need_fix：具体技术、质量或材料缺口仍存在，PM发起dp-auto组织处理；不是已整改/已恢复。
- reject：拒绝当前恢复方案；仅存在明确且获授权遗留关闭方案时收尾，不再把reject默认解释为返工。
- 质量事实复用dp-QG有效结论；确需新的正式质量判断才重新审核，不因触发复核重复审核同一份有效证据。
- 恢复不自动增加预算、改变目标或扩大写面；缺新业务意图/权限或需风险接受时给具体人工问题。

## 当前事实与未批准部分

既有静态清单autopilot-human-decision-inventory.md H05引用`packages/multi-workers/autopilot/conductor.py:4451`/`:4540`：48h或其他key终态触发复核升级；原stalled/budget gate approve=resume、reject=rework，两者运行到running。本文复用静态核验，不宣称新运行测试；48h为当前事实，不因本轮认可冻结为目标阈值。

具体触发条件/阈值、证据版本失效、状态转换、schema和消费者留设计。当前approve/reject二值gate协议与新的四选项业务契约尚未迁移，不将need_fix映射为旧reject来声称已接线。

本轮无源码/registry/配置/活gate/历史/服务变更，无真实复核、后继DP调用、恢复、返工或关闭。AC-022/023仅本项验收推导，完整SPEC/23AC及联合设计未批准，旧独立key验收不回写。

对齐`.agenticdoc/goal.md`：PM协调多Worker而保留角色/写面/预算与文件驱动协议，不新增同步Worker等待PM链路。
