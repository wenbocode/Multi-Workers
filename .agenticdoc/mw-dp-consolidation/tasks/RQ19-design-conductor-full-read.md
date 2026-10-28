---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-conductor-full-read-20261026.md
---
# RQ19 — 补核conductor条件化消费与恢复隔离

## 上下文
`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:98`，53AC已锁、H01～H13已确认，当前DESIGN。用户要求继续，联合设计及实施写面未批准。RQ14未完整读conductor的EXECUTE/VERIFY/L3、advance、xkey apply及部分预算/队列来源；不得将原报告的局部观察当全仓不存在证明。

## 要求
1. 时间盒25分钟。全文读 `packages/multi-workers/autopilot/conductor.py:1`、`config.py:1`、`xkey.py:1`，分段到实际EOF；所采用的其他主要文件也全文读或明确未覆盖范围。重点补原RQ14未读的advance/EXECUTE/VERIFY/L3、xkey apply、预算及队列状态来源。可复用RQ14对gates/contract_guard的观察，但标注未新核。
2. 基于锁定SPEC按H01～H12列触发、条件复核、决定、PM后继请求、实际效果、消耗、异常及重放。三状态gate队列与四业务选择是否正交须提出候选结构，不把四选项强制压成旧approve/reject。steer/need_fix由PM在材料/角色/授权满足且无在途请求时发起对应DP，选择不等于调用/执行。reject不统一关闭/halted/rework；goal仅有效approve采用指定版本。
3. 至少比较两种合法技术方案：显式条件化效果适配层复用原消费者，或各消费者保留完整事项条件/效果。列pros/cons/推荐与精确候选函数/文件；不冻结旧40字段，不默认保留旧运行兼容。目标、授权、契约、实质证据版本失效和无关变化复用应有机械可核边界。
4. H04/H09/H10补核预算来源、真实pending/running/未知状态、尝试/标记/旧提案保留、有界恢复。未找到字段不能写全仓没有计量；授权数值未设置。H11人工停止/撤权不可自解；H12至少两种受控恢复隔离方案，明确发起者/预授权证明/原因消除/检查位置/刹车读取与受限写入/失败出口/观察和再熔断。仅新增kind或未列AUTO_RULE_BY_KIND不足以证明隔离；熔断链不得自批，服务不可用不得偷换通道。
5. 给AC007～010、015～037、048/049/052的正反、重放、并发、未知队列断言及授权/锁边界。禁运行测试/CLI裁决/provider或服务探针，不读活配置/gate/ledger/roadmap/刹车/凭证、其他key运行材料，不改源码、预算授权、状态、旧研究或PM文档。只做静态设计输入，不恢复任何真实对象。

## 交付格式
先worker_file写证据并read回核文件。证据与最终回复分别用独立 `## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`，不要只用加粗内联标题。最终证据节引用完整路径 `.agenticdoc/mw-dp-consolidation/evidence/research/design-conductor-full-read-20261026.md` 及key内 `evidence/research/design-conductor-full-read-20261026.md`。陈述完整读取范围、未核调用链/安装身份，不造VERIFY/运行通过，不宣称设计/AC/QG/签收批准。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-conductor-full-read-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-conductor-full-read-20261026.md

## 写入禁止面
除此证据外全部文件。框架自动回执不人工修改；不建report.md。源码用read完整读取；PowerShell命令不使用&&。禁测试/build/install/commit/服务起停。
