# Research: design 期证据位置声明（零调研声明）

## 决策问题

docs gate 要求本 key 具备 `evidence/research/design-*.md`；本声明说明历史证据的实际位置。

## 调研方法与出处

- design 期验证证据存于 `.agenticdoc/mw-dispatch-reliability/evidence/runs/`（doctor-before/after.txt、l2-claude-isolation-rerun.txt、l2-summary.md）；design 决策记录内嵌于 design.md（22KB，D-001~D-007）

## 发现

- design.md 齐备；L1/L2 运行证据存在但位于 `evidence/runs/`（早于 research 目录约定的历史布局）

## 结论 → 决策映射

- 本文件为 gate 语义下的零调研声明，指向真实证据位置；本 key 后续新增调研按约定写入 `evidence/research/design-*.md`
- 声明补写时间：2026-09-07（mw-dispatch-flow-fixes 需求澄清轮）
