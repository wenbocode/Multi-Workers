# H02：阶段关闭条件（已确认，运行未迁移）

## 本轮问答

八个DP职责和目标名称确认后恢复H02需求讨论。PM提出：dp-gate-approve判断当前stage是否满足关闭条件；PM准备阶段目标/必需交付、必需key有效签收结论、跨key集成/阶段验收、未完成/未验证项及影响。不能只凭Worker done或key已签收关闭。

PM最后问题：“是否认可这些阶段关闭条件，以及‘允许非阻断遗留，但不允许遗漏必需交付／验证’的规则？”用户答“认可”。

## 已确认业务边界

- approve：本阶段必要交付与验收满足，允许关闭当前stage；不等于已执行关闭，更不批准下一stage启动。
- reject：不满足关闭条件，说明具体阻断，不允许关闭；不直接选择返工、补证或任务重排。这些由PM通过dp-pm-steer或dp-auto协调。
- 必需交付或必需验证未完成，不能关闭；有效key签收不能代替跨key/阶段整体验证。
- 非阻断且不影响本阶段验收的遗留项，可以明确披露后带遗留关闭；不要求整个项目零未完成。
- 需要用户接受的风险或目标取舍，须先取得具体确认；审批不能自行降低验收要求或授予权限，原硬门保留。
- 复用dp-QG与dp-sign-key有效证据，不增加独立阶段关闭DP或同gate第二次审批。

## 静态事实与未批准部分

既有静态证据见autopilot-runtime-panorama.md、autopilot-three-dp-discussion.md：`packages/multi-workers/autopilot/conductor.py:1272`阶段关闭、`_consume_answered_gates:910`消费路径。此前核得当前stage-close reject会halted且终态吸收，approve仅关闭当前stage并开放下阶段确认；这里只引用既有静态研究，不宣称本轮重测。

本轮未批准具体reject状态转换、hold/rework映射、补证重判调度、材料schema、迁移执行器或部署。不得把目标业务reject语义冒充现有程序已调整；不得把本轮认可当作任何真实stage关闭、gate答复或key签收。

对齐`.agenticdoc/goal.md`：文件驱动协调和权限/隔离/锁协议不变，以阶段整体验收服务多Worker共同交付。完整SPEC/19AC及联合设计仍未批准，旧独立key验收不回写。
