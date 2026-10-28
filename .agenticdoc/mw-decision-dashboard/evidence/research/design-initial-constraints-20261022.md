# Research: Initial design constraints

## 决策问题
设计派发前明确已证实输入与未决技术选型，不冒充完成设计研究。

## 调研方法与出处
- `.agenticdoc/mw-decision-dashboard/spec.md:1` 已完整读取，17 AC，用户选择独立浏览器窗口、非常规端口、独立测试记录、全 DP 输入与人工观察。
- `evidence/research/spec-command-entry-20261022.md:1` 完整回读：窗口只 show/sign，透传授权写入有守卫风险。
- `evidence/research/spec-decision-trace-20261022.md:1` 完整回读：原始请求/返回不落盘，调用与决策幂等粒度不同。
- `evidence/research/spec-dashboard-playground-20261022.md:1` 完整回读：静态 HTML 无提交服务，默认 run 存档影响生产签收；21 DP 未声明业务字段。
- `python .agents/skills/agentic-task/scripts/audit_phase.py mw-decision-dashboard` 当前 DESIGN 审计 PASS。

## 发现
需新增本地交互接口但无需引入新的调度器；测试必须隔离生产授权与签收；真实调用记录必须在传输边界采集。
RQ-3 的 settle 无生产写者声称与 RQ-2 的明确 TS 调用位置冲突，设计必须复核；不能原样接受。

## 结论 → 决策映射
design D-001..003 提出两种生命周期/记录方案和观察调用边界，均未最终选择。
D-RQ1..3 分别验证生命周期/安全、调用记录/生产写者、输入契约/观察隔离，PM 串行合并，不写代码。
