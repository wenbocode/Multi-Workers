# v0.5四段记录范本与开发对比

用户澄清后的v3规约。范本入口：[docs/reference-records/index.md](docs/reference-records/index.md)；原v0.5图表增加“按DP四段范本”。不是未来真实采集计划。

## 四段分别是什么

1. 发送前冻结的完整本地决策本，保留来源/准备/约束/本地expected等，不整体入模。
2. 实际Request.data完整body与所有单选判据，字节原件/hash明确。
3. 已有真实jev响应原文及官方解码、同版pair-map全部原因/剩余项和原host未执行状态。
4. 当前PM对上述材料和回包补写的参考接回：采纳或退回、理由、后续安排、保留原因、真实host待核条件、禁止错误声明。不是历史生产采纳/派发回执。

## 版本与校验

原版8DP包含auto confidence=0.16；整合版用优化auto confidence=1.0，原schema v0.6-draft不改，两cohort共9个唯一案例。优化输入增加事实/目标，不能作同事实confidence提升证明。

每例reference-chain.json贯通四段，expected-checks.json供实现校验wire/basis/全部原因及PM语义。QG缺reopen、原auto缺优先级/完整路径保留为负例；新实现不复刻旧缺陷，不把旧响应套新body，不把未执行当已执行。

当前原历史生产PM记录不存在，字段仍为null；新增PM参考意见有明确record_kind/作者/日期。不为这个交付新派Worker/调用jev。上轮真实8/8采集要求和T11已撤回，旧规约在evidence/planning/revisions/v2-before-v05-clarification留存。

## 逐项复核补充（2026-11-19）

直接采用[v0.5范本索引](docs/reference-records/index.json)及[四段逐项对比合同](reference-comparison-contract.md)。T01—T10全部直接引用同一套资产；T01—T07交职责内字段证据，T10定义原件回放及报告校验，T08交9例×4段共36行JSON/Markdown对照与原始观测，T09逐行复核。原件回放、当前实现差异、负例拒绝和PM语义分别核实；缺段/串版/无依据差异/未验证不通过。T11继续撤回，产品测试/实施仍not-run。
