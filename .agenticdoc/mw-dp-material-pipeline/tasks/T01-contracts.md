type: coding
deps: []

# T01 合同、注册表与完整合法候选

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标工作区E:/gitlite/Multi-Workers。读spec AC-001/010、design §3/4/7、docs详细设计§5/7/8。QG历史例缺reopen，不能改原件遮盖。

## 目标及对应AC

AC-001、AC-010；输出可被两语言消费的闭合材料/配对合同和显式版本处理，固定候选完整、auto为2..5。

## 工作项与交付

1. 完整读取当前注册源/生成脚本/消费者，列谁写谁读；先复用已有实现，不平行建第二张权限表。
2. 定义八DP字段、候选/配对/准备状态/结果/错误版本；固定候选不按推荐依据裁剪，QG包含reopen条件判据。
3. wire唯一映射choice/basis/全部原因与剩余项；区分多个fix配对与单一业务结论。
4. 用真实生成/消费链验证两语言一致；给新测试和合同说明，旧捕获只读。

## 依赖与已有证据

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。复用现有 Python renderer 和冻结反解。从实际发送的 wire 反查覆盖的业务结论，增加 QG 随附样例仅 `fixA`、多个 fix wire 同结论、sign 缺 finalize、预览与发送差异的断言。QG 分支条件与 T05 联合核对，保留具体缺项诊断。

无实施依赖。docs字段/请求附录和captures为输入样例，不是生产验收；复制hash见evidence/planning/docs-manifest.json。

## 写入允许面

- packages/multi-workers/decide_registry.json、decide_book_template.json、scripts/gen_decide_registry_ts.py。
- packages/coding-agent/src/extensions/agent-team-loop/shared/decide-policy.ts及由注册源正确生成的shared/decide-registry.generated.ts。
- 新测试packages/multi-workers/test/test_dp_material_schema_v1.py，必要对应定向schema测试。

## 写入禁止面

PM发送/预算/业务writer、pi核心、全局配置、依赖锁、其它key和本key docs冻结副本。若生成器真实路径不在面内，先由PM补卡，禁止直接手改生成TS。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_schema_v1.py"]
```

## 完成判据与输出

VC-001/010证据实际出现；覆盖QG缺reopen/单项、auto 1/2/5/6、未知wire、多原因恢复与TS/Python parity。所有新/改测试实际运行，output.md说明版本处理/生成来源，不以旧HTTP200当通过。未来代码交付依仓库要求运行npm run check；不构建/安装/调用模型。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。复用 preview 对非法 applies_to 和 material_refs 的校验。用 ueperf-platform 回执的同型错误核预览提示与 Python 最终候选的一致性，分别覆盖缺固定项、同一业务结论形成多个 wire、非法绑定。保留零发送断言。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例，重点dp-QG、dp-route。核决策本pair_map、完整单选候选与criteria、原回包wire到全部原因及PM参考结论；QG缺reopen作负例。交字段/版本差异证据。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
