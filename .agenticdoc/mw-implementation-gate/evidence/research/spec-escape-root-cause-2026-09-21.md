# Research: 逃逸根因与方案选型（spec）

## 决策问题
spec §1.1（为什么需要机械门禁）/ §1.4（做什么不做什么）——从 advisory 升级为 enforcement 的依据与方案组合。

## 调研方法与出处
- 本会话实证：两轮野生实施（update-env、ue-toolchain）——第二者为完整案例：需求讨论（映射表确认）→ 主窗口直做 6 任务 → 事后补登记 key mw-ue-toolchain（其 key-decision.md「I（实施）」与 quality-gate-report「流程偏差」节为留底）。
- 对照 SKILL.md 门禁文字：`.agents/skills/agentic-task/SKILL.md`「Implementation Entry Gate」节——门禁存在但为文字约束。
- 对照 skill 触发机制：pi 的 available_skills 中 agentic-task 的 description 为 "Use when working with the AgenticTask /agentic project workflow, including /agentic, pm run..."——不含"即将实施新功能"场景词，未触发加载。
- 对照 P-002 先例：`.agenticdoc/_pitfalls.md` P-002（2026-09-15，mw-protected-config-guard 前置警戒）——同类问题（会话乱改）曾用前置守卫解决，实现方式待 W2 调研。

## 发现
- 三层归因（详见对话留档）：① 规模误判+惯性（把 ~500 行交付当小改动；连续两轮直做后局部规范漂移）；② 门禁是 advisory——write/edit 工具无 key 检查，逃逸路径零摩擦；③ 事后补登记不构成威慑（并行收益不可逆损失，且逃逸当下无任何记录）。
- 文字门禁（SKILL.md）对"会话中途插入需求"场景无例程触发——Turn Start 例程只在轮次开始跑。
- 仓级注入（AGENTS.md）每轮可见但不具拦截力；真拦截需工具层。

## 结论 → 决策映射
- ①②③ → 三层组合方案（spec §1.1）：pi 扩展 before-tool 硬拦截（本 key 主交付）+ SKILL.md 触发词扩面（AC-005）+ AGENTS.md 仓级规则（已先行落地，不属本 key 交付，见 key-decision）。
- 拦截能力存在性未知 → W1 调研前置（spec §4 风险第一条），design 形态由调研结论决定。
- 守卫模式复用 → W2 调研 P-002 先例（spec §5 可复用资产）。
