type: coding
deps: [T01, T02]

# T03 八DP投影、desc计量和定义闭包

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-003/004/005、design §4，docs详细设计§5/8与字段附录。依赖T01/T02；默认先于T04释放PM热文件。

## 目标及对应AC

AC-003、AC-004、AC-005；从有来源的材料显式构造实际请求，模型不再收到无意义内部标签或准备日志。

## 工作项与交付

1. 实现八DP专属闭合投影；本地身份/准备过程/执行actionplan/作者expected不整体透传，必要约束单独投影。
2. desc逐句绑定目标/偏差/事件/证据未知，最多 10 句。通过共同宿主入口按 `desc-local-v1` 验证本地预算 1000 放行、1001 零发送。
3. 引用/缩写/代码解释在body内闭包，AC具体正文与范围/关系一致；发现同ID错对象/冲突/悬空返回字段级诊断。
4. 每个模型字段有来源与落点。真实producer写入→投影→完整body至少一条离线生产链，不只验证手写JSON。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。复用 `model_state_for` 白名单，先从真实 PM/Worker caller 和 Python builder 抓实际 payload，查任务原文与 `state.preparation` 的现有发送落点。八 DP 逐字段完成来源和投影差异，避免只更新 TS preview 或只改 book schema。

- packages/multi-workers/decision_book.py、decision_points.py及本任务新增专属投影/计量模块。
- 实际投影接线 `packages/multi-workers/decision.py`、`decision_material_sources.py` 及 `mw.py` 的 prepared capture。保持引用解析、正式 writer 和生命周期归属，准备目录仅进本地快照。
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts、triage-client.ts的材料producer/投影适配部分。
- 新测试packages/multi-workers/test/test_dp_material_projection_v1.py；对应suite/decision-context-agent-materials.test.ts及本任务新增定向suite。

## 写入禁止面

原身份/预算/continuity语义、凭证/依赖/模型配置、pi核心、其它key和docs副本。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_projection_v1.py"]
```

## 补充验证与完成判据

涉及TS时从packages/coding-agent执行`node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-context-agent-materials.test.ts`及新增/修改suite，使用harness/faux。VC-003/004/005证据实际可见，覆盖 PM 和 Worker 的 10/11 句、1000/1001 本地预算、全八DP字段、内部元数据泄漏和冲突引用。交原始工具结果和发送次数，运行 `npm run check`。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。在真实 producer 将计划产物留在本地、明确模型必要正文与 evidence_refs。验证新投影叶子及 allowed_fields 相符，检查术语文本可用与真实凭据拦截两类。Bearing 四条回执无原命中字串，按同型保护回归。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例。逐字段对照决策本仅本地/发送、完整body、引用定义/候选与返回原因，核PM所需目标/偏差/证据；新body给版本化差异，不套旧回包。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
