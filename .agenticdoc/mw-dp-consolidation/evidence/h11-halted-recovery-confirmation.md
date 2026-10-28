# H11：halted stage受控恢复（已确认）

## 本轮确认

PM提出halted可受控恢复，但保留停止事实、核实新证据及预算授权；明确人工停止/撤权不能由DP自行解除。用户答“认可”。

## 已确认业务规则

- 不直接把halted改回running制造正常推进假象；原停止事实保留，用恢复记录或新版本关联原停止与本次恢复，具体结构留设计。
- PM note列停止原因（工程阻断/预算/用户停止）、原因消除证据、stage/版本/受影响key、目标/方案/授权/剩余预算、恢复动作与结束判据。
- approve恢复条件成立，按note限定恢复；steer交PM调整不适合继续的任务计划；need_fix交PM补停止原因或恢复材料的具体缺口；reject不批准当前恢复，仅有明确获授权遗留方案时收尾。
- 不抹去原halted历史，不重置已消耗预算，不绕机器硬保护；选择不冒充已恢复。
- 明确用户停止/撤销授权，即使技术原因消除仍需恢复所需明确授权，DP不覆盖用户停止指令。

## 当前静态事实与未批准部分

既有autopilot-human-decision-inventory.md H11引用`packages/multi-workers/autopilot/conductor.py:1090`的_stage_activation：halted返回，当前状态机不允回退，依赖人工改roadmap且无受控恢复入口。本文复用静态核验，不宣称已实现恢复记录/新版本机制。

具体恢复结构、状态转换、授权/预算证明、版本/关联、schema/消费者留设计。本轮不允许模型手工改状态/roadmap、移除人工停止或自行重获权限；未实际恢复/执行后继DP/重置预算。

只写本keydraft证据/spec/state，无他key/roadmap/源码/registry/配置/活gate/历史/服务或phase变更。新增本keyAC-034/035验收草案，完整SPEC/35AC及联合设计未批准，旧独立key验收/历史不回写。

对齐`.agenticdoc/goal.md`：保留文件驱动状态、用户授权/角色/写面/预算与进程隔离，不靠模型回答抹去停止记录或制造执行权限。
