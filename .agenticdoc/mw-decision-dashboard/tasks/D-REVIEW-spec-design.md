# D-REVIEW 独立审计 spec 与 design

type: review

## 上下文
- 用户明确要求一个review worker审查spec/design；当前Phase DESIGN，尚未编码，禁止以没有实现为缺陷。
- Goal `.agenticdoc/goal.md`；审计主文档 `.agenticdoc/mw-decision-dashboard/spec.md:1`、`.agenticdoc/mw-decision-dashboard/design.md:1`；辅助 `evidence-requirement.md` 与五份design研究证据。
- `packages/multi-workers/decision_backends.py:246` 实际HTTP边界；`packages/multi-workers/decide_signoff.py:287` 签收冻结面，行号漂移时按函数查。
- PM已合并首轮三组及RQ4/RQ5负空间研究，不代表设计正确；17/17 AC机械映射与Mermaid PASS只能证明格式，不证明语义。

## 审计目标
完整阅读spec.md/design.md/evidence-requirement.md，独立判断是否可进入PLAN。重点：用户意图与范围是否被设计缩减/扩大；AC→VC是否真正充分且可执行、矛盾/虚假断言；人工回答/覆盖是否只是记录或符合需求；动态候选/历史缺失处理；内部真实Jev/disabled/P0与全局配置；测试全部旁账/签收隔离；call/attempt/decision/schema/上下文；Host/Origin/token/secret/截断/窗口生命周期；单写者、并发锁和双根fail-closed；25DP必填字段业务意义与预算；真实接线验收而非mock自证。对关键代码前提进行只读核实，不把PM/研究结论当权威。优先找阻止实施的实质问题，不泛泛风格建议。

## 要求
只读审计，不能修改主文档、代码、配置、档案，不能执行网络/模型/测试/构建/服务起停。不得因尚无实现批评实现缺失；可以指出未定义实施接口或不可完成的验证。Finding须有精确path:line、对应AC/VC、触发条件、后果及最小修正建议；按P0/P1/P2排列，区分已确认缺陷与待核实风险，不重复已被合并修复的研究建议。明确PASS/CHANGES_REQUIRED及阻止PLAN的条目。用户要求一个review worker，本任务单人综合审计，不再派子任务。

## 未覆盖面声明
不审实现质量（当前无实现），不声称Windows真实窗口/锁性能/实际Jev验证通过；报告列实际已读文件与未覆盖面，无法核实项明确标记。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-spec-design/**`（仅自身report/output，不写evidence或任何外部文件）

## 写入禁止面
- spec.md/design.md/evidence-requirement.md/pm-state.md/其他任务或key、所有源代码/配置/生产档案。

## 交付格式
自身report.md：审计结论、P0/P1/P2 Findings、AC/VC覆盖盲区、核实证据、未覆盖面；finding精确行号与最小修改，≤250行。若无缺陷说明残余风险，不伪造问题。最终摘要≤40行，列阻塞项数量、报告路径。相关主文档读全，源文件相关函数完整分页；pi API如涉及先完整读相关官方docs及交叉引用。
