type: review

## 上下文

控制与目标 E:/gitlite/Multi-Workers，key `mw-dp-material-pipeline`，VERIFY。目标见 `.agenticdoc/goal.md`，AC-003 见 `.agenticdoc/mw-dp-material-pipeline/spec.md:76`。用户将 AC-003 改为本地预算，正式签收前需要独立核对本批 T08、T09 和同版冻结合同。

## 审计目标

独立核对当前源码、AC-003/VC-003、18 组验收条目及 3 条流程，提交机器可读取的终态 QG。

## 要求

1. 先读 `.agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/review-inputs.json` 及 `.agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/quality-gate-candidate.md`，再看本批 PM/Worker `normal-entry.json` 中的四组观察、`loopback-transcript.json`、`t08-pytest.log`、`v05-four-stage-comparison.md` 及本轮实现。1000/1001 由 999 个非 ASCII 码点与 LF 加 3/4 个 ASCII 码点构成。逐条核对候选表所指证据与结论。原独审剩余 AC-014 是否可关闭取决于全部验收证据，FLOW-003 的同范围 writer 正例见本批隔离 QG 签收结果。
2. 独立认可后，用 `worker_file(file=report.md, mode=write)` 完整提交候选文本。保留 `## Achieved`、18 组含 `met` 的行与 `## Quality Gate Report` 的工程相对路径及 64 位 SHA-256。若有实质差异，按证据修正表格状态和残留，不填不实 PASS。
3. 仅复核和写自己的报告，不执行正式 QG、sign 或改源码。报告提交后正常结束。

## 未覆盖面声明

本轮为固定本地预算。正例真实 POST 到本机回环，环境没有调用外部模型做 token 计量。

## 交付格式

本 Worker 原生 `report.md` 与终态。保留 QG 39 项及 AC/VC 18 组可读取记录。

## 验收命令

```json
["python", "-B", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/check_review.py", "--report", ".agenticdoc/mw-dp-material-pipeline/workers/cx-ee474fbc353feb7aba95/report.md", "--spec", ".agenticdoc/mw-dp-material-pipeline/spec.md", "--evidence-index", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/evidence-index.json", "--reference-index", ".agenticdoc/mw-dp-material-pipeline/docs/reference-records/index.json"]
```
