---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-observation-server-20261026.md
---
# RQ21 — 补核观察服务与离线提交生产边界

## 上下文
`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:34`，53AC锁定、当前DESIGN。RQ20已完成UI读码，明确未读Python monitor/playground；用户要求继续联合设计。只补该缺口，不重做旧dropdown或monitor重启8AC，不授权实现或部署。

## 要求
1. 25分钟只读。全文read `packages/multi-workers/decision_monitor.py:1` 和 `packages/multi-workers/decision_playground.py:1`，分段至实际EOF；其他主要源若采用则全文读或声明具体未覆盖。不读活gate/ledger/配置/签收/凭证、其他key运行材料，不启动服务/浏览器，不跑测试/CLI决策/provider探针。
2. 核 `/api/dps`、history、test cases/scaffold/validate/submit、观察令牌与角色、scope=test/observe_only、实际写入路径、typed校验/失败审计与业务执行的边界。结合RQ20原证据，校正“两个UI面互不相通/全部无承载/窗口上下文不落盘”等绝对断言；raw文本/日志可展示不等于有独立业务语义组件，不因为不直接注入窗口就推定不能关联生命周期。
3. 至少两种合法技术方案并给pros/cons/推荐：生成协议+既有只读投影与语义组件，或显式组件消费统一协议/投影。活动注册精确八名，退役解释另列，不把retired项混进活动枚举后只禁按钮。旧ID各提交面明确拒绝，模型/业务成功0，允许真实安全失败审计。不以UI字段或ui.status授运行资格/权。
4. gate note/模型理由/后继未发起、调用失败、返回选择和真实动作分别呈现；route不是业务审批、consumed/settled不代执行/done；原历史只读，不回填，null与[]区分。签收只认原适用范围有效finalize与对应证据，dp apply旧权限配置职责不被扩张。
5. 给精确候选文件/接口及AC001～003、007、012～014、038～043、049～053的正反/秘密与注入/重放/字节不变断言。源码存在!=当前部署身份；未覆盖CLI/完整caller或实际DOM明确标出。

## 交付格式
先worker_file写唯一证据，再read回核。证据和最终回复分别使用独立 `## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源` 标题；最终证据节写完整路径 `.agenticdoc/mw-dp-consolidation/evidence/research/design-observation-server-20261026.md` 及key内 `evidence/research/design-observation-server-20261026.md`。不只写basename，不造VERIFY/测试或设计/AC/QG/签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-observation-server-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-observation-server-20261026.md

## 写入禁止面
除此证据外所有文件，框架回执不人工改，不建report.md；禁源码/配置/UI/服务/预算或旧报告改动。源码用read，PowerShell不用&&；禁测试/build/install/commit。
