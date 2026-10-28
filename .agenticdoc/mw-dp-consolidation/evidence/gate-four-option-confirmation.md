# dp-gate-approve：四选项与PM预拟note（最新确认）

## 用户提案及确认

H03讨论中用户提出dp-gate-approve四选项：approve（预算内应该继续或目标达成）、steer（交PM发起dp-pm-steer）、need_fix（PM发起dp-auto）、reject（遗留并关闭方案）；approve选项说明附PM拟定的note，并询问意见。

PM同意四选项方向，补充note在送审前拟定、steer与need_fix职责区分及reject边界，最后询问：“是否按这四项修订dp-gate-approve，并采用上述note和reject边界？”用户答“确认”。

本轮显式替代此前本key已确认的approve/reject二选项目标契约，不改旧独立key历史或生产记录。

## 已确认含义

| 选项 | 业务含义与后续责任 |
|---|---|
| approve | 满足本次gate条件，按PM预先说明的动作继续或收尾；预算内或目标达成不是豁免必要证据、授权和硬门的充分理由。 |
| steer | 任务组织、主线、拆分或执行主体需调整，交PM发起dp-pm-steer。不是当前gate放行，也不是已整改。 |
| need_fix | 推进方式基本明确，但有具体技术/材料缺口，交PM发起dp-auto处理。不是当前gate放行，也不是已修复。 |
| reject | 拒绝本次推进方案；有明确且获授权的遗留关闭方案时按该方案收尾，不无条件关闭任意对象。 |

## PM note

approve的说明附送审前PM拟定的note：本次审批事项、批准后具体动作、目标/证据/预算/授权依据。再执行一轮修复与关闭当前stage必须明确区分。

PM note与决策模型理由分开保存；不把模型生成理由补造为送审前PM批准事项。精确字段/schema、存储结构及生命周期关联仍待设计。

## H02/H03与硬边界

- H02阶段成功关闭仍须必需交付/验证与整体验收成立，关闭不批准下一stage启动；非阻断遗留规则保留。
- reject拒绝本次成功关闭方案不等于自动批准另一个关闭动作；合法授权的遗留收尾不冒充达标stage关闭或dp-sign-key成功签收。
- 停滞key遗留关闭须披露未完成项/影响与权限，不自动取消项目目标或降低验收；超授权风险接受/目标取舍/预算追加须具体人工确认。
- 选择、实际执行、后续处理结果分别记录；不能因gate选择steer或need_fix就宣称已调用后继DP或完成整改。
- 材料非法/服务不可用/无有效选择保持调用失败/阻塞，不默认映射need_fix、reject或其他业务结果。

## 当前事实与未覆盖

既有静态路径见autopilot-human-decision-inventory.md与autopilot-runtime-panorama.md：`packages/multi-workers/autopilot/conductor.py:4146`/`:4215`当前stalled approve/reject分别恢复/closed-legacy，阶段关闭另有当前halted语义。当前registry dp15仍是旧continue/narrow/revoke，未按本key二选项或四选项目标改造。这里复用已有静态核验，不声称新运行验证。

本轮只写本key需求/证据/state，未改gate writer、消费者、状态转换、运行registry/schema、配置、服务或生产历史；没有实际审批、关闭、后继DP调用或签收。完整SPEC/19AC与联合设计未批准。

对齐`.agenticdoc/goal.md`：保留文件协调、角色/写面/预算约束与Worker隔离，明确PM编排及修复责任，不新建中心协调器。
