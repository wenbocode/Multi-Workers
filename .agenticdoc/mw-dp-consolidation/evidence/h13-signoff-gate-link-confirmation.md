# H13：dp-sign-key与收尾硬门衔接（已确认）

## 本轮确认

PM提出签收结论/证据与收尾硬门真实衔接，不替代其他验收、不重复批准、不默认扩大强制签收范围。用户答“认可”。之后进行整体“毕业考”场景/职责/路由/AC对账，不把需求确认当作实现验收。

## 已确认规则

- 保留dp-sign-key finalize/continue/user-confirm及原交付目标/实际完成/验证证据/未完成影响材料，不重定义签收。
- 按已有批准规则需要签收的key，只有有效finalize及对应签收证据才满足签收条件；continue/user-confirm不冒充成功。
- 签收不豁免必要QG、验收、claim、契约、证据等硬检查，QG通过不自动签收。
- 既有同次判断与签收写入机制保留，无第二次PM批准；签收文件不等于phase已done或stage自动关闭。
- 收尾硬门须正确识别finalize实际契约，不伪造旧标签或关闭硬门绕过词表适配缺口。
- 强制签收范围按原已批准规则，不因命名迁移自动扩到所有key，不用disable规避原必需签收。
- 影响签收条件的实质变化后不能无条件沿用旧签收；具体有效性/版本/证据关联留设计，原历史不补造。

## 既有静态事实与未批准部分

既有autopilot-human-decision-inventory.md H13引用`.agents/skills/agentic-task/scripts/advance_phase.py:309`的_decision_signoff_problems：kind=decide且未显式disable时有条件签收硬门。此前核得旧接受词表continue/narrow/revoke与dp25 finalize不匹配；不是必须人签或新stage gate的证据。

`packages/multi-workers/decide_registry.json:1699`起原dp25条目与既有PM源码核验给出同次mw decide sign判断且finalize写签收。这里只复用静态证据，不宣称当前安装/运行已适配新命名或新词表。

框架脚本/安装镜像修改面、签收有效性/关联/schema、词表/消费者和完整链测试留联合设计及明确写面授权；本轮不授源代码改动或服务运行权限。

只写本keydraft文档，无实际sign调用/签收/phase推进/硬门豁免/disable或他key/源码/registry/配置/历史/服务改动。新增AC-038/039验收草案，完整SPEC/39AC及联合设计未批准，旧独立key26AC与签收债仍保留。

对齐`.agenticdoc/goal.md`：保留文件证据协调、目标对齐、角色/写面/claim/硬门约束及Worker隔离，决定、执行、签收与阶段完成不互相冒充。
