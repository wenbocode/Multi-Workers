---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-ac-coverage-20261025.md
---
# RQ12 — 毕业考：39AC覆盖与机械可验性

## 上下文
目标锚点`.agenticdoc/goal.md:5`，入口`.agenticdoc/mw-dp-consolidation/spec.md:1`及`.agents/skills/agentic-task/references/workflow-requirements.md:175`（AC推导规则；实际行号以读取为准）。用户要整体需求“毕业考”，不是现在运行实现验收。39条AC未锁，H01–H13原则逐项确认不代表全AC批准。RQ10负责职责/旧范围矛盾，RQ11负责H业务边界，本RQ独占验收覆盖/可观测性/缺少正反例。

## 要求
1. 全文读spec.md及workflow-requirements.md，逐条审查AC-001～039的前置条件/对象/可观测结果/量化断言。给紧凑39行表，指出只是写“次数0”但触发、产物/消费、成功路径仍不可验证的项；不把缺技术schema一律当缺业务确认。
2. 对八DP和H01–H13给AC覆盖映射，重点核dp-auto动态候选、dp-route七目标/直调/角色资格、非法材料/不可用/无效选择、DP答案/后继调用/真实动作/settled的区别，以及Worker自主终态/有限补证；提出遗漏的候选AC（不用现有编号冒充已批准新增，不编辑spec）。
3. 每个主要缺口给可构造输入、预期观测及禁止副作用的纸面例，不编实际测试结果。正路径、边界、异常、并发/版本/历史隔离分开。保留null与[]、同关联/时间递增/历史不回填等既有上下文证据原则；相关现契约只从本key已有证据引用，未全文核旧独立key不宣称验收。
4. 旧AC-001～003范围问题只标交RQ10主责，不重复做全量退役审计。原编号永不重用，待完整SPEC审核后才锁定；无实际来源的性能数值不补。
5. 只读本key文档、goal及上述workflow规则，结论依赖文件全文读，注明未覆盖；不作新源码审计、不读活配置/gate/ledger/凭证。15分钟有界研究，唯一证据建议<=220行。
6. 禁源码/registry/配置/他key/原报告/PM文档修改；禁测试/build/install/commit/服务操作、额外ask_decision/provider探针。未知写待确认后完成研究，不编业务答案。只写唯一证据，不自建report.md。

## 交付格式
证据与最终回复均包含`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`，有path:line，事实/纸面推演/候选AC分开；不得宣称SPEC/AC/QG/实现验收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-ac-coverage-20261025.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-graduation-ac-coverage-20261025.md

## 写入禁止面
除唯一证据外所有文件；框架自身任务自动回执由框架维护，不人工修改。
