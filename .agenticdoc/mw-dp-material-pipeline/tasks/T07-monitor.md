type: coding
deps: [T06]

# T07 四段回放与原始API返回直接可见

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-012、design §6/7、docs详细设计§13与已有图表。依赖T06捕获/检查合同稳定。

## 目标及对应AC

AC-012；用户能直接看到真实完整返回，并区分本地准备、实际入模和业务执行状态。

## 工作项与交付

1. 分开展示本地决策本、完整冻结body/单选、原始返回/反解、PM接回决策/当前业务检查，不把准备报告冒充jev响应。
2. 默认结果摘要有原始返回入口，完整response包含model/answers/confidence/probabilities/usage/id；不能只埋在长payload后面。
3. 每字段是否发送、来源/未知/缺口及多原因恢复可查看；历史输入/回包不套新版本。
4. 明确not-executed/transport-unknown、关闭/不可用和当前/历史身份；显示层不改变真实业务事实或泄露认证值。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。使用现有 book/wire/lifecycle 及 handoff/执行证据的共同绑定串联四段。完整无敏感离线向量核原字节，真实捕获核 hash 与脱敏/截断/缺失状态。以独立来源标记 PM 参考和实际接回。

- packages/multi-workers/decision_monitor.py、decision_history.py、decision_dashboard.html、decision_dashboard.js、decision_dashboard.css。
- 新测试packages/multi-workers/test/test_dp_material_monitor_v1.py及相关现有dashboard/monitor定向测试。

## 写入禁止面

发送/预算/候选业务逻辑、凭证脱敏规则放宽、其它key、docs冻结副本；禁止为截图伪造API响应或把预计结果写成真实返回。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_monitor_v1.py"]
```

## 补充验证与完成判据

VC-012必须包含离线生产捕获→monitor的链路，逐字段与原件对照；本地浏览器检查默认入口、八DP切换、长页底部和窄屏，实际查看截图并交付。使用既有捕获/本地替身，不调用真实API。交output.md、截图和未执行状态证据；未来代码交付运行npm run check。

## v0.5范本引用与逐项对比（必验）

按[八个 DP 同次对账](../decision-chain-reconciliation.md)展示同一次冻结本、传输尝试、反解及第四段接回/实际回执。原主体可以从回执反查其对应调用或本地判据。缺失、未发送和安全副本完整度分别标记。

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。从 event_id 串联已有 book/wire/lifecycle 与原主体接回证据。未发送回包为空，DNS 保存原传输原因，只有前置状态时保留未知。按记录来源区分 PM 事后审计与 host writer 实录。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例。四段分别可见并对应范本，含完整body、原文response与PM接回/执行状态；历史参考与当前运行分开，每字段发送/来源可查。保存四段可见及长页/窄屏截图。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
