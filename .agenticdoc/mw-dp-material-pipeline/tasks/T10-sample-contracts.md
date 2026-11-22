type: coding
deps: [T01]

# T10 v0.5现有四段范本与开发校验

## 状态与上下文

planned，未派发。控制/目标E:/gitlite/Multi-Workers。读AC/VC-015—018和docs/reference-records；9个现成案例已经整理，原版/整合版各8DP。旧v2误设真实采集不再是前置。

## 目标及对应AC

AC-015—018；把已有决策本→实际输入→真实返回→当前PM参考裁定接入离线回归，而不是制造未来样例空壳或再调用模型。

## 工作项与交付

1. 消费reference-chain/index/expected-checks，校验两cohort/原版本/ID/字节/同版pair-map和全部原因，不串接旧auto响应与新输入。
2. 当前投影按字段/定义/候选/来源差异对照，已知QG缺reopen与原auto材料不足保留负例，不为过范本放宽合同。
3. PM文本核required_pm_facts/forbidden_pm_claims和参考处置，语义不要求逐字匹配；实际历史PM/派发缺失仍为空，不能把参考意见当runtime receipt。
4. 交付evidence/reference-checks/check_reference_pack.py及报告合同供T08/T09消费；工具默认离线只读，不发API/派发。

## 写入允许面

- 本key evidence/reference-checks/的未来校验工具/报告。
- 新测试packages/multi-workers/test/test_dp_v05_reference_chain.py及必要隔离fixture。

## 写入禁止面

生产权限/派发/writer、全局配置、其它key、docs冻结150原件和新增reference-records原始请求/响应；不得修写旧回包或伪造历史PM/派发结果。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_v05_reference_chain.py"]
```

## 完成判据与输出

9例完整读取、两cohort、原件/原因严格一致、PM语义判据和2个已知负例可检出；错误case/版本/原因/假executed拒绝。交output与报告。当前仅资料已整理，产品消费测试未来实施后实际运行，不新增真实模型调用。

## v0.5范本引用与逐项对比（必验）

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例、两个cohort。交只读原件校验、36行报告schema/校验器及缺段/重复/串版/原因丢失/假执行/无依据差异反例；原件回放与当前观测两模式分开，T08生成集成报告。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
