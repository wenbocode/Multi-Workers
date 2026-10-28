# RQ-2 decision trace

type: research

## 上下文
- 目标：`.agenticdoc/goal.md`；需求：`.agenticdoc/mw-decision-dashboard/spec.md`。
- `packages/multi-workers/decide_archive.py:1` 决策档案，`packages/multi-workers/decision_book.py:1` 决策本。

## 要求
只读调查决策档案、模型原始实际请求与返回、决策本引用、自动/人工/覆盖/settle/签收来源、吸收与应答的持久化链路。完整读相关源文件，追踪所有边界。给出已记录/未记录矩阵，历史回填可行性、关联ID、脱敏风险、未知来源如何诚实显示。可读既有样例但证据不得复制任何 secret。禁止网络真实模型调用，禁止改代码/配置/档案。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/spec-decision-trace-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/spec-decision-trace-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-rq2-trace/**`

## 写入禁止面
- 所有代码、配置、其他任务与 key 文件。

## 交付格式
问题、方法与 path:line、发现与缺口、结论到 spec 映射；output.md 摘要。只写唯一证据，不写相位文档。
