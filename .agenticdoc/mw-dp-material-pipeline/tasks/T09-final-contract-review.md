type: review

## 上下文

控制与目标工作区为 E:/gitlite/Multi-Workers。任务属于 `mw-dp-material-pipeline`，目标见 `.agenticdoc/goal.md`，正文见 `.agenticdoc/mw-dp-material-pipeline/spec.md:67`、`design.md` 和 `evidence/contract-freeze.json`。本次基于 `evidence/acceptance/final-batch/` 的 T08 实际运行证据和 36 行对账。此前签收、回包和未执行事实均保留原样。

## 审计目标

逐项独立判断 AC-001 至 AC-018 和 VC-001 至 VC-018 的充分性，并核 design 中 FLOW-001 至 FLOW-003 的对应路径。重点检查 AC-003 精确计量、AC-006 正式 QG→sign 的阻断、AC-014 全部覆盖和 AC-017 同次接回。以当前源码、当前冻结合同和实际命令结果为依据。

## 要求

- 读 `evidence/acceptance/final-batch/review-inputs.json` 查当前证据版本。至少抽查请求、原始回包和同次回执的反查，以及旧 `dp-auto` 零发送和本次原 PM 接回。AC-003 的 Timi 证据仅证明兼容计量接口可用，精确边界待证。AC-014 的整体验收须反映所有未关闭项。逐项按你核到的证据判定。
- `## Quality Gate Report` 需要一张表，列为 `ID | Result | Evidence`，为 18 条 AC、18 条 VC 和 3 条 FLOW 各写一行。结果只用 `PASS`、`FAIL`、`NOT-RUN`、`UNKNOWN`。`PASS` 和 `FAIL` 的第三列用清单中的 `项目相对路径@sha256`，各证据可复核。`NOT-RUN` 和 `UNKNOWN` 用短证据缺口说明。使用原始 ASCII 竖线分隔表格。另写 `## Achieved`，如实说明本轮结果和未结项。
- 用 `worker_file` 的 `file=report.md`、`mode=write` 落盘，再正常结束。将 `结论`、`证据`、`残留与未验证`、`上下文来源`、`未覆盖面声明` 各写为独立的 `##` 段落。生产处理、签收、认领、写源码或改验收标准由各自正式入口执行。

## 未覆盖面声明

隔离回环用于产品工具入口和业务逻辑。未取得目标模型精确分词合同。历史旧 dp-auto 的生产 PM 回执继续为空。审核本身只读，不推进阶段。

## 交付格式

当前正式 Worker 的 `report.md` 和框架终态。报告正文用中文，保留标准的标题与结果值。

## 验收命令

```json
["python", "-B", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/check_review.py", "--report", ".agenticdoc/mw-dp-material-pipeline/evidence/review/ac014-final-independent.md", "--spec", ".agenticdoc/mw-dp-material-pipeline/spec.md", "--evidence-index", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/final-batch/evidence-index.json", "--reference-index", ".agenticdoc/mw-dp-material-pipeline/docs/reference-records/index.json"]
```
