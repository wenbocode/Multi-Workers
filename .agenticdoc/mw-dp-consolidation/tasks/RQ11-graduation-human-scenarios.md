---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-human-scenarios-20261025.md
---
# RQ11 — 毕业考：H01–H13场景边界与四选项后果

## 上下文
目标锚点`.agenticdoc/goal.md:5`，入口`.agenticdoc/mw-dp-consolidation/spec.md:1`及`.agenticdoc/mw-dp-consolidation/evidence/h13-signoff-gate-link-confirmation.md:1`。用户确认H01–H13原则后要求继续整体场景对账。完整SPEC/39AC/联合设计未批准，本轮纯文档审查。RQ10负责八DP/旧范围，RQ12负责AC机械性，本RQ独占十三H场景与恢复/审批/动作边界。

## 要求
1. 全文读spec.md及H01澄清、H02证据、gate-four-option-confirmation.md和H04～H13确认文件。可读inventory/panorama已有证据，但区分其旧现状与最新目标，不能据旧状态反推已批准新实现。
2. 给H01～H13逐行表：触发/待决事项、适用DP/理由、批准必要证据及权限、其他结果的边界、真实执行未完成时不得声称什么。H03是stalled场景，不能因共用四项就遗漏该场景自身条件；若仅通用合同未覆盖足够则明确待确认，不自补预算/限额/状态。
3. 从已有规则构造至少六个组合反例并推演：阶段关闭后启动、QG通过但key未签收、soft轮次与hard预算、跨key已有批准但claim冲突、goal/AC实质变更失效、halted人工停止、brake自批、未知队列重派等。可合并，不实际运行。寻找重复审批/权限越界/失败洗白/恢复死锁或需求矛盾，区分业务缺口与设计问题。
4. 明确H12受控恢复通道必须有授权且不得被熔断链自批，不可用不绕过；H13不默认扩所有key强制签收。没有实际预授权或预算值由讨论产生。建议只基于已确认规则，不自行决定新授权、schema或执行步骤。
5. 只读本key文档及goal，结论依赖文件全文读，注明未覆盖；不作新源码审计、不读活配置/gate/ledger/凭证。15分钟有界研究，唯一证据建议<=220行。
6. 禁源码/registry/配置/他key/原报告/PM文档修改；禁测试/build/install/commit/服务操作、额外ask_decision/provider探针。未知写待确认后完成研究，不编业务答案。只写唯一证据，不自建report.md。

## 交付格式
证据与最终回复均包含`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`；有path:line，事实/纸面推演/建议分开。不得宣称SPEC/AC/QG/实现验收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-human-scenarios-20261025.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-human-scenarios-20261025.md

## 写入禁止面
除唯一证据外所有文件；框架自身任务自动回执由框架维护，不人工修改。
