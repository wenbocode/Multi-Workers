# RQ-1 command entry

type: research

## 上下文
- 目标：`.agenticdoc/goal.md`；需求：`.agenticdoc/mw-decision-dashboard/spec.md`。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4474` 是 DECIDE_USAGE，`:4502` 是 unknown sub。
- `packages/multi-workers/mw.py:4019` 是 Python dp 分发。

## 要求
只读调研窗口 /mw decide dp list 与 Python CLI 差异，确认报错根因、支持范围、stale serve 与扩展 reload 的区别。阅读相关函数完整上下文及测试；允许只读列表/help/测试现有用例，不做真实模型调用、不改代码、不改配置、不重启服务。提出需求范围与验证建议。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/spec-command-entry-20261022.md

## 交付格式
证据包含问题、方法/出处 path:line、发现、根因与不确定性、结论到 spec 映射；output.md 摘要并引用证据。只写唯一证据，不写相位文档。
