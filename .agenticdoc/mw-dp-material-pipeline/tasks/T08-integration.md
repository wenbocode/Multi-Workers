type: coding
deps: [T01, T02, T03, T04, T05, T06, T07, T10]

# T08 离线生产链集成、回归与证据汇总

## 状态与上下文

已由 Codex PM 执行首轮隔离集成，完整验收待 T01—T07 补齐。Key mw-dp-material-pipeline；控制/目标 E:/gitlite/Multi-Workers。[36 行报告](../evidence/acceptance/v05-four-stage-comparison.md)和[证据索引](../evidence/acceptance/evidence-index.json)区分测试观测、原件回放和验收失败。

## 目标及对应AC

AC-001—013离线全链验证及AC-015—018现有v05四段范本消费校验，给AC-014提供源码证据；本卡不代T09独立复核。

## 工作项与交付

1. 用真实producer/注册工具/host读取器/替身后端/业务接回/monitor组成隔离离线链，禁止只拼最终fixture。
2. 八DP正反例、角色/状态/模型/revision、压缩/计量/引用、QG/sign/auto、并发/取消/额度/unknown传输全部覆盖，VC-001—013输出从真实断言发射。
3. 跑T01—T07各新测试及其必要TS suite，当前已有continuity/配对/来源/monitor定向回归；TS从包根、用harness/faux，不跑全量vitest。
4. 运行npm run check并完整留输出；真实环境失败与新增失败分别列，不能抄历史基线/删其它证据/放宽标准。
5. 产出evidence/acceptance/evidence-index.json，逐AC/VC绑定spec摘要、目标工作区、源码摘要、命令/目录/退出码/原始日志、结果与限制。
6. 产出evidence/acceptance/check_review.py供T09只读验收独立报告覆盖/证据链接；不能靠脚本打印pass取代host身份核对和PM阅读。
7. 消费T10现有v05范本校验，记录两cohort/原件/全部原因/PM参考语义与已知负例；check_review支持--reference-index，不依赖live样例新采集。

## 写入允许面

- 新测试packages/multi-workers/test/test_dp_material_pipeline_l2.py、必要已有定向回归/隔离fixture及对应TS集成suite。
- 本key evidence/integration/、evidence/acceptance/及本run output.md。

## 写入禁止面

生产实现文件（缺陷回原责任卡处理后重验）、全局配置/依赖/其它key、docs冻结副本。无真实API/build/install授权；不以测试发现需求为由直接派工/推进门禁。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_pipeline_l2.py"]
```

## 补充必跑

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。复跑其定向套件和两组候选反例。当前 loopback 捕获及 Windows 独审签收写入受测试环境限制，实施验收时记录实际环境与结果。源码和加载包的部署状态分别取证。

从[跨项目回执](../evidence/dp-blocked/20261122/report.md)取代表性离线场景，覆盖无效引用、文件不可达、读/预算限制、配置状态及上游异常。引用 event_id、阶段和预期未发送/传输/接回状态。回执作为附加向量，9 例四段对照仍按原合同交付。

T01—T07主/补充定向命令、当前现场选定的相关现有回归、npm run check。命令列表与结果写入evidence-index；新增测试须实际运行，不能只有py_compile/收集成功。

## 完成判据与输出

VC-001—013及VC-015—018参考消费校验齐备，证据绑定当前源码/spec。原始范本不改，PM参考不冒充历史执行；T09按当前证据独立复核，不再等待T11。

## v0.5范本引用与逐项对比（必验）

按[八个 DP 同次对账](../decision-chain-reconciliation.md)生成真实入口证据。在现有 36 行内核冻结本、同次请求/返回及原主体接回，第四段同时给出适用 writer 和回执指针。另保留八 DP 合法模型路径的当前离线见证与本地/拒绝分支的实际证据。

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。按 13 个主类组合同型问题，取案例表中可确认机制的代表做附加离线回归。事件 ID 关联预期拒绝点或成功对照。复用已修能力的现有回归，9 例四段 36 行单独验收。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例、两个cohort。汇总T01—T07实际观测，调用T10合同工具，输出v05-four-stage-comparison.json/.md的36行原件/当前对照及字段差异，纳入evidence-index；缺段/未验证不通过。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
