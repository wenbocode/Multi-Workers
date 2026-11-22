type: review

## 上下文

控制与目标为 E:/gitlite/Multi-Workers，key `mw-dp-material-pipeline`。目标见 `.agenticdoc/goal.md`，验收正文见 `.agenticdoc/mw-dp-material-pipeline/spec.md:67`。独立 T09 已逐项检查同批源码，报告为 `evidence/review/ac014-final-independent.md`。本任务复核其判定和将用于生产 QG 的表格字节。

## 审计目标

核对下面的 QG 原稿与独立 T09、冻结合同和当前运行证据一致，并从本次真实只读 Worker 的报告交付。前次运行的表格省略了工程根前缀且使用无效哈希，不能供机器签收。

## 要求

1. 优先读 `.agenticdoc/mw-dp-material-pipeline/evidence/acceptance/final-batch/quality-gate-candidate.md`，再对照同目录 `review-inputs.json`，以及独立 T09 的当前矩阵。QG 的 open 项已在原稿注明。核清后将原稿文件完整复制到自己的 `report.md`，保持每条证据的 `.agenticdoc/mw-dp-material-pipeline/` 工程相对前缀、64 位哈希和 `## Quality Gate Report` 原样。
2. 如独立核验有实质出入，在表外 `## 残留与未验证` 具体说明，并按实际情况决定对应状态。需要引用证据时使用清单中的有效工程相对路径及哈希。必要时检查 `prepare-full.json`、`prepare-limit.json` 和 `entry-sign-finalize-newer-reviewed-fix/normal-entry.json`。
3. 用 `worker_file(file=report.md, mode=write)` 提交本任务报告后正常结束。仅复核和报告，不执行 Gate、sign 或任何写操作。

## 未覆盖面声明

真实 Jev 的精确 Decisions 分词口径尚无证明，兼容计量证据继续单列。实际签收由既有 host writer 独立判断。

## 交付格式

本 Worker 原生 `report.md` 与框架终态。

## 验收命令

```json
["python", "-B", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/check_review.py", "--report", ".agenticdoc/mw-dp-material-pipeline/evidence/review/ac014-final-independent.md", "--spec", ".agenticdoc/mw-dp-material-pipeline/spec.md", "--evidence-index", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/final-batch/evidence-index.json", "--reference-index", ".agenticdoc/mw-dp-material-pipeline/docs/reference-records/index.json"]
```
