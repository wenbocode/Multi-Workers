---
type: reviewer
envelope_producer: autopilot-conductor@0.83.0
origin: conductor
loop: l3:key-1
attempt: 1
read_scope:
  - checks.py
  - ordered_rows.py
  - anchors.json
  - .agenticdoc/key-1
---

## 上下文

autopilot 自动派发（无任务卡；以下为种子，不是探索上界）。type=reviewer，loop=l3:key-1，attempt=1。触发/失败原因：Independently verify repaired evidence for dp-QG:qg-repair-and-review-1.。证据路径：.agenticdoc/key-1/workers/ap-key-1-l3-a1/trace.log、.agenticdoc/key-1/workers/ap-key-1-l3-a1/worker.log 及任务书要求段列出的判定源；项目锚点 .agenticdoc/goal.md。

## 要求

Independently verify repaired evidence for dp-QG:qg-repair-and-review-1.

判据（可判定）：任务书列出的目标逐项满足，产物在本轮 worker 目录可核；[VERIFY] 证据与结论闭合，未满足不得声称完成。

## 交付格式

交付格式：本轮产物集中在 .agenticdoc/key-1/workers/ap-key-1-l3-a1/，报告与输出文件（report.md / output.md）按任务书列出的必备段成节（结论 / 证据（含原始命令与输出）/ 审计未及范围 / 残留与未验证 / 上下文来源清单）。

以上为种子，不是探索上界；可自行检索补充上下文。

