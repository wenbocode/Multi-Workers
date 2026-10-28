# 联合设计并行分析与边界

## 输入与目的

用户确认完整SPEC/53AC后要求继续。AC Locked at 2026-10-25T23:37:14+08:00，快照evidence/spec-locked-20261025.md；正文指纹d73c3050ab0ec4a0af7ddeb169264257638cdfdfb5f34d63f734528d4a20737e。已通过advance_phase进入DESIGN，不是design批准或运行验收。

## 可并行单元

| RQ | 唯一问题/主要读面 | 唯一证据 |
|---|---|---|
| RQ13 | 八入口注册/业务材料/backend协议、名称与历史分层 | research/design-entry-contracts-20261026.md |
| RQ14 | conductor各gate消费、H01～H12状态/预算/授权/恢复隔离 | research/design-autopilot-effects-20261026.md |
| RQ15 | PM tool/窗口事件、准备→判断→后继请求→处理、角色与回执 | research/design-pm-orchestration-20261026.md |
| RQ16 | Worker可达性三项/自主终态、vision派发与角色/写面 | research/design-worker-feasibility-20261026.md |
| RQ17 | finalize硬门/历史与投影、跨层观测和VC/写面建议 | research/design-signoff-observation-20261026.md |

共享SPEC/goal只读；源码可交叉核接口，但五个问题不得互相代作结论。每份证据只允许所属研究者写，无共享schema或design写面。25分钟有界研究，每个RQ最多一轮，预算/未知不能自造为运行值；超范围标未覆盖，不承诺全仓审计。

## 必须串行

PM保存需求锁定、相位/claim操作和唯一design.md正文。研究返回后逐份全文回读/ack，串行对齐角色/业务材料、note/版本/授权、gate后果、后继调用、签收及历史来源，提出至少两个可比方案及证据支撑的推荐，用户审核后才定设计。53AC→VC、全入口/异常Flow与证据需求由PM统一编号，不让各RQ独立冻结不同schema/动作/状态。

## 资源与权限

派发前list_tasks全项目无running；mw PID51788仅证明运行状态，不证明最新内存模块，不重启。正常research派发可按用户既有授权真实触发旧dp1；无额外决策/provider探针、测试/build/install/commit、活配置/gate/ledger/凭证读取或修改。只写本key文档；goal/其他key/源码/registry/工具schema/CLI/框架脚本均不改。H12不实际解锁，H13不实际签收。

## 后续

研究成功≠方案采纳≠design通过。完整设计、53AC→VC覆盖、Mermaid检查、证据需求及精确候选写面审核前不推进PLAN或实施。旧独立26AC、monitor8AC、格式/check/部署和其他债保留。
