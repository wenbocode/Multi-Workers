type: coding
deps: [T01]

# T02 文件正文、来源追溯和超限压缩

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-002/004、design §3/4、docs详细设计§4/6。依赖T01合同完成，使用其真实接口。

## 目标及对应AC

AC-002、AC-004；必要正文真正进入材料，来源/范围/未读限制可追溯，超限不丢关键语义。

## 工作项与交付

1. 复用decision_source_scope及现有文件证据读取器，source handle不成为任意路径读取能力；核实际指向、原范围/拒绝规则与原累计读取额度。
2. 记录source_id/版本/hash/选择器、已读与未读、事实性质、时间/对象和局限，产出field_trace供投影使用。
3. 大材料按去噪、必要提取、有来源摘要顺序压缩；保留否定、反证、失败/未知、逐AC覆盖和候选判据。仍超限给具体overflow，不截尾/只给路径/刷新预算。
4. 给出压缩前后计量、明确省略项、当前语义复核状态；未读内容不得变observed。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。沿用 `evidence_refs`、精确单文件授权、现有摘录和新鲜度检查。补模型字段到必需正文/摘要的覆盖、遗漏理由和守卫内 Worker 预算交接。账本无法交接时维持现有拒绝及已授权 inline 路径。

- packages/multi-workers/decision_material_sources.py、decision_source_scope.py、decision_file_evidence.py、decision_evidence_policy.py。
- 新测试packages/multi-workers/test/test_dp_material_source_pipeline.py及必要来源定向测试。

## 写入禁止面

PM身份/全局范围策略、pi核心、凭证/依赖、其它key、docs冻结副本。不得放宽既有读写面/限额以过测试。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_source_pipeline.py"]
```

## 完成判据与输出

VC-002/004输出真实值；覆盖仅路径、越界/重解析指向、UTF-8、大小临界、摘要删失败/漏AC、未知/未读、源变化与累计预算。至少一条由真实读取器产生材料的离线用例，不能全部手写manifest。交output.md及源/变换证据，不读真实密钥/模型；未来代码交付运行npm run check。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。沿用正文注入、精确授权、来源快照和 mechanical excerpt；分别跑必要文件不可达、读范围拒绝、原字段 max-bytes、整请求 compression-required。成功对照核缩窄范围或来源摘要保留失败、未知及 AC/VC。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例，重点dp-QG、dp-sign-key及两个auto。核来源/正文/摘要→模型输入每字段；保留回包原因所需失败/未知及PM参考必要事实。交来源/变换/发送落点与差异。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
