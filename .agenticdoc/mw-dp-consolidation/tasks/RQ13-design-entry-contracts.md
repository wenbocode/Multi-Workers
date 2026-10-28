---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-entry-contracts-20261026.md
---
# RQ13 — 八入口与backend协议设计取证

## 上下文
目标`.agenticdoc/goal.md:5`；用户已整体确认`.agenticdoc/mw-dp-consolidation/spec.md:1`的53AC，锁定时间2026-10-25T23:37:14+08:00，本key DESIGN，联合设计/实施未批准。并行边界见evidence/design-parallel-analysis-20261026.md。本RQ只研究注册、业务材料、backend校验/名称及历史分层；不替RQ14定gate状态、RQ15定PM调度、RQ16定Worker终态或RQ17定签收硬门。

## 要求
1. 全文读spec及PM毕业考勘误，按八个精确名整理当前/目标差异：dp-w-type、dp-pm-steer、dp-w-check-task、dp-QG、dp-gate-approve、dp-sign-key、dp-auto、dp-route。六旧职责迁移、19退出独立职责，两新增；无旧编号运行别名，原历史只读。dp-auto不沿用旧dp3的2..5/ID限制，签收数组不改null。
2. 全文读所采用的主要文件，优先packages/multi-workers/decide_registry.json:1、decision.py:1、decision_points.py、decision_wire.py及相关纯契约测试/模板；每个结论给具体path:line。可只读搜索其他实际入口用于后续盘点，但未全文读者仅列定位/未覆盖，不冒充全入口已审计。不读活配置/gate/ledger/凭证/安装内存。
3. 提出业务material/本地identity/meta/模型材料隔离、选择校验、非法/未知/不可用处理、schema/注册单一事实源与Python/TS同步的至少两种方案，给pros/cons与证据支持的推荐。明确候选字段/枚举只是设计建议，不扩大角色权限、不造授权/预算、不恢复旧入口。
4. 列后续需触及的精确候选文件及下游接口、建议L0/L1/L2断言，重点AC001～004、011～014、040～044、050～052；不用测试数量代证。25分钟有界只读研究，报告建议<=220行；超范围明确未覆盖。
5. 禁源码/registry/工具schema/CLI/配置/原报告/PM文档/他key修改；禁测试/build/install/commit、服务操作、额外ask_decision/provider探针。只写唯一证据，不自建report.md；框架自动run/output由框架维护。

## 交付格式
唯一证据及最终回复均有`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。现有事实/目标要求/方案建议/授权未定分开，给可复查路径与行号；不宣称实现、SPEC/AC/QG/设计或签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-entry-contracts-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-entry-contracts-20261026.md

## 写入禁止面
除上述证据外所有文件；不人工修改框架自动回执。
