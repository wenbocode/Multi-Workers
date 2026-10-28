---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-signoff-observation-20261026.md
---
# RQ17 — 签收硬门、历史与观测VC设计取证

## 上下文
目标`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:1`完整53AC已获用户确认，锁定2026-10-25T23:37:14+08:00，本key DESIGN，联合设计/精确写面/实施未获批。本RQ只研究签收硬门、历史与安全投影/观测；不替协议、gate状态、PM、Worker其他RQ定约。

## 要求
1. 全文读spec、H13确认/毕业考勘误，全文读采用的主要源码：.agents/skills/agentic-task/scripts/advance_phase.py:1、packages/multi-workers/decision_history.py、decision_lifecycle.py、decision_task_state.py；按需全文读相关UI/测试、签收writer与sign CLI所用文件，未全文读只标定位/未覆盖。不能凭writer文件存在证明部署/内存接线，不读活配置/gate/ledger/凭证或其他key运行材料。
2. 针对旧硬门词表与finalize错配，比较至少两种正确识别同次判断+证据/适用范围的方案，给pros/cons/推荐。需签收key仅有效finalize，不第二次PM批准，不用旧标签/disable绕门、不扩强制范围；QG≠签收≠done≠stage关闭，受影响实质版本变更不复用旧签收。任何框架/镜像候选写面都只提建议，未授权修改/安装。
3. 设计原历史编号只读与新八入口投影/提交层区分、材料/身份meta/原因保密、真实producer/writer/consumer/projection关联、before来源/after链接/时间不倒退，保留null未知与[]明确无项；签收verified/unverified/unfinished_impact仍数组。失败/拒绝可有真实安全审计，无动作不能伪executed/decision_id，settled不等于完成，不造第二套ledger/历史回填。
4. 给精确候选文件与接口、L0/L1/L2证据建议，重点AC005/006/013/014/038/039/043/050～053；观测建议必须覆盖正向和异常/重放/并发、秘密与注入，不靠文本[VERIFY]声明代真实证据。不可把旧独立key的26AC/十节点DAG随意洗成已验收或冻结新映射不容更改。
5. 25分钟有界研究，报告建议<=220行。禁源码/框架脚本/registry/配置/活gate/ledger/签收/他key/原报告/PM文档修改；禁测试/build/install/commit/服务操作/额外ask_decision/provider探针；只写唯一证据，不建report.md，框架自动run/output由框架维护。

## 交付格式
证据及最终回复都有`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`，分现有事实/目标要求/候选方案/未验证，列完整读范围与未覆盖，不宣称设计/运行/AC/QG/签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-signoff-observation-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-signoff-observation-20261026.md

## 写入禁止面
除上述证据外所有文件；不人工修改框架自动回执。
