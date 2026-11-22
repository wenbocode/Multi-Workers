type: coding
deps: [T08]

# T09R 修复后正式独立复核

目标锚点 `.agenticdoc/goal.md:3`。验收锚点 `.agenticdoc/mw-dp-material-pipeline/spec.md:70`。代码锚点 `packages/multi-workers/decision_model_context.py:115`。使用本次独立 Worker 身份。首次独审在全包测试时超时，本次只核 T09 修复与同次回执。

## 上下文

Key mw-dp-material-pipeline。控制与目标工作区 E:/gitlite/Multi-Workers。先写报告骨架并逐项写结论，报告唯一交付路径为 `.agenticdoc/mw-dp-material-pipeline/evidence/review/t09-focused-mw-review.md`。沿用 T09 的 spec、design、原件和四段验收。禁止修改产品、源证据和旧回包。本次不跑全包测试，不请求外部决策服务。

## 要求

1. 阅读 `evidence/review/normal-entry/verified-fixed-entry-summary.json` 和相关原始记录。核固定候选缺失、待解释缩写含文件正文、dp-auto 超预算及循环、Worker 按行读取。核 Gate 同一次正式 CLI 的选项、原返回、反解、consumed 和 settled(pending)。
2. 对照 `evidence/acceptance/v05-four-stage-comparison.json` 的 36 行，检查旧 dp-auto 正式历史接回仍 unverified。分开记录当前保护 Gate 无真实执行与本次原例的隔离 CLI 接回。读 `evidence/review/t09-independent-rework/index.md`、现有逐条复核 `evidence/review/t09-v05-row-review.json` 和首次独审的 `evidence/review/t09-mw-worker-rows.json` 后取原始文件复核。
3. 只运行两个定向命令，先 `python -B .agenticdoc/mw-dp-material-pipeline/evidence/review/normal-entry/audit.py --t09-fixes` 的读回逻辑并保持原证据文件字节（建议直接 import audit 方法在临时目录或用 param pytest；不要写已有摘要），并跑 `python -B -m pytest packages/multi-workers/test/test_dp_material_pipeline_l2.py -q -p no:cacheprovider`。无需尝试其它测试，遇阻直接标记。先完成证据报告再做命令上的附加复核。
4. 主报告先结论和缺口，按四项与 Gate、36 项核对，并给 AC-001—018/VC-001—018 的 met/not-met/unverified 结论。沿用实际证据和作用域，范围不够处明确未验，不推测生产 Gate 或历史 PM 事实。正文控制在 120 行内。最终回复引用报告，框架代写同次 output.md。

## 交付格式

提交上述独立报告。输出摘要须说明实际检查、验收结论和遗留，是否有外部模型发送，及本次报告路径。普通 Codex PM 验收元件可以因历史回执留空返回不通过，报告仍按时交付。

## 写入允许面

write_face: .agenticdoc/mw-dp-material-pipeline/evidence/review/**

## 写入禁止面

框架源码、旧证据、决策原件、其它 key 及索引均为只读。

## 验收命令

```json
["python", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/check_review.py", "--report", ".agenticdoc/mw-dp-material-pipeline/evidence/review/t09-focused-mw-review.md", "--spec", ".agenticdoc/mw-dp-material-pipeline/spec.md", "--evidence-index", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/evidence-index.json", "--reference-index", ".agenticdoc/mw-dp-material-pipeline/docs/reference-records/index.json"]
```

## 改动历史

- 2026-11-22 从 T09 恢复，限定为四个修复、Gate 同次接回和原 36 项对照。
