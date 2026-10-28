---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-autopilot-effects-20261026.md
---
# RQ14 — autopilot gate后果与受控恢复联合设计取证

## 上下文
目标`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:1`完整53AC已获用户确认，锁定2026-10-25T23:37:14+08:00。当前DESIGN，设计/写面/实施未批准。本RQ研究Python conductor的gate后果、H01～H12状态/授权/预算/版本/恢复隔离；其他RQ分别研究协议、PM、Worker和签收/投影，不互相代定。

## 要求
1. 全文读spec、PM毕业考勘误及所用H确认；全文读主要packages/multi-workers/autopilot/conductor.py:1（分段续读直至末尾），选用gates.py、contract_guard.py、xkey.py等也全文读，结论给具体path:line。25分钟内无法覆盖者明确文件/范围，不用搜索片段冒充全链；可引用旧研究但标未新核。
2. 分H01～H12列现有触发/条件/写入及目标差异，提出四选择approve/steer/need_fix/reject的gate-specific效果、PM note绑定/送审冻结、原因/证据/授权/版本有效性、硬门重验。H03/H04同事项不双批，H09/H10按问题用steer/auto、独立审批才加gate，reject不一律closed/halted/rework。
3. 至少比较两种“具体条件复核与行动消费”方案，给pros/cons/推荐。说明幂等/并发锁、未知队列不当空、标记受控恢复/保留失败、软轮与硬预算消耗不重置、goal/冻结契约变更失效、人工停止/撤权不可自解。实际限额/预授权值保持未设置。
4. H12专门比较恢复通道隔离的可实现方案：先停、原因消除/预授权/硬检查成立，不许熔断链自批解锁，不可用阻塞。现auto-brake不必然停止整个conductor，不能由静态事实推断活项目处于熔断/死锁。不给新能力/操作授权，不读或清刹车。
5. 列精确候选写面、与PM/RQ13/RQ17的接口需求及AC007～010、015～037、048/049/052的可观测VC建议。禁源码/配置/活gate/ledger/roadmap/状态/他key/原研究/PM文档修改；禁测试/build/install/commit、服务/额外裁决/provider探针及凭证读取。只写唯一证据，不建report.md，框架自动回执由框架维护。

## 交付格式
证据及最终回复均含`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。事实、目标要求、候选方案、未确定运行值分开；注明完整读范围与未覆盖，不宣称设计/运行/AC/QG/签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-autopilot-effects-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-autopilot-effects-20261026.md

## 写入禁止面
除上述证据外所有文件；不人工修改框架自动回执。
