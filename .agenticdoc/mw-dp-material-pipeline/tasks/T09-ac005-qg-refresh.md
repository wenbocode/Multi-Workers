type: review

## 上下文

工作区为 E:/gitlite/Multi-Workers，当前 key 为 `mw-dp-material-pipeline`，处于 VERIFY。目标见 `.agenticdoc/goal.md`，合同见 `.agenticdoc/mw-dp-material-pipeline/spec.md:78`。本批独立 T09 的 18 组 AC/VC 结果已提交。

## 审计目标

核对本次 T09 结果和正式 QG 草稿，独立确认 AC-005 与 VC-005 的验收证据，提交供宿主绑定的终态报告。

## 要求

1. 读 `.agenticdoc/mw-dp-material-pipeline/evidence/acceptance/ac005-official/quality-gate-candidate.md` 和同目录 `review-inputs.json`，然后对照本次 `evidence/review/ac005-t09-independent.md` 的 18 组裁定、两个正常入口证据及三条 FLOW。核实列出的源码变化只涉及 VERIFY 只读复核的派发桥。
2. 若独立核验一致，完整复制 QG 草稿到本次 `report.md`，保留 `## Quality Gate Report` 及每行的工程相对路径、状态和 64 位 SHA-256。若有实质出入，按证据修正并在 `## 残留与未验证` 写明。AC-003 精确计量仍待金标准证据。
3. 使用 `worker_file(file=report.md, mode=write)` 提交原生报告并正常结束。范围限于只读复核和提交该报告。

## 未覆盖面声明

不覆盖实发 Jev 精确计量合同，保留旧 dp-auto 历史回执为空。宿主另行执行正式 sign 的校验和接回。

## 交付格式

本次 Worker 的 `report.md` 与原生终态。报告使用草稿的章节和冻结合同 39 条机器可读取记录。

## 验收命令

```json
["python", "-B", "-c", "from pathlib import Path; p=Path('.agenticdoc/mw-dp-material-pipeline/evidence/review/ac005-t09-independent.md'); assert '| AC-005 | VC-005 | met |' in p.read_text(encoding='utf-8')"]
```
