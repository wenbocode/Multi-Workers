# RQ-3 dashboard and real playground

type: research

## 上下文
- 目标：`.agenticdoc/goal.md`；需求：`.agenticdoc/mw-decision-dashboard/spec.md`。
- `packages/multi-workers/decision_backends.py:1` 真实模型 backend。
- `packages/multi-workers/mw.py:2779` dp verify，`:4067` decide 命令。
- `packages/multi-workers/usage.py:1` stats 看板资产。

## 要求
只读调查现有 HTML/TUI 看板、服务接口和 DP 测试能力：选 DP + 填决策本如何复用内部真实调用。完整读相关源文件与文档，明确决策本校验/组装/state/questions/实际 payload/backend/结果/执行器边界。比较只发真实 Jev但不执行业务动作与真实执行风险，推荐最小复用方案，列需用户确认事项。不能真实模型调用、不能起服务/重启、不能改代码/配置。涉及 pi API 时完整读取官方相关 docs 与交叉引用。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/spec-dashboard-playground-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/spec-dashboard-playground-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-rq3-playground/**`

## 写入禁止面
- 所有代码、配置、其他任务与 key 文件。

## 交付格式
问题、出处 path:line、发现、复用资产、限制与安全边界、spec 决策映射；output.md 摘要。只写唯一证据，不写相位文档。
