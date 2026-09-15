# Research: 门禁语义与回合预算——用户决策记录（spec）

## 决策问题

人工门禁的判定机制、分层判断结构、token 控制原则（支撑 spec §1.1 / §2.2 / §3 AC-007~011 / AC-018）。

## 调研方法与出处

- 本 key（goal-autopilot）4 轮讨论记录，用户明确表态：
  1. B+C 组合可行（否决 A：无头 PM 可观测性差、断点重做成本高，需要监控台）
  2. 混合门禁 + 分层判断补充：L1 脚本兜底（证据齐全性、结论/决策点支撑度）输出结构化简化上下文；L2 基于 L1 关键上下文反馈；L1↔L2 多轮但上限保守为 2；L3 在 quality gate 后 review，不达预期结合前序证据判断 key 能否正常结束，最多两轮收敛，解决不了移入遗留问题 + 生成 pattern 待人工决策；token 不失控——每个发散回合最多两轮
  3. 批量拆 key：stage 内 key 的 roadmap 作用、相互依赖、闭环后阶段目标由人工确认，然后自动循环做完整个阶段
  4. autopilot 不得影响手动驱动工作流；测试边界清晰；不同项目适合不同开发方式，可混合使用；console 断点重开要有明确流程
- 交叉验证：pm-mind.md「Phase 4.5 分层降级验证」（L0/L1/L2 与本设计同构：确定性优先、降级有出口）；pm-mind.md Hook 3（遗留问题必须有去向）与 U9（pattern 提炼触发条件）；dispatch-table.md「Phase 推进」强门禁（advance_phase.py 唯一推进通道）

## 发现

- 用户的分层设计与 pm-mind 既有哲学一致：L1=零 token 确定性检查（对应 L0 静态验证的扩展）、L2=有界判断、L3=终局裁决；每层失败出口都是升级而非重试
- 「每个发散回合最多两轮」是全局原则，覆盖四类回路：L1↔L2、L3 收敛、task retry、（后续 design 可能新增的 replan）
- stage 门禁确认内容三要素（key 作用/依赖/阶段目标）即 roadmap 文件每 stage 节的必填结构
- 手动/自动共存的关键事实：AgenticTask 全部状态在文件（pm-state/phase/tasks/evidence），模式互换天然无缝——这是框架「不依赖对话记忆」设计的直接收益

## 结论 → 决策映射

- 门禁矩阵（硬地板=stage 确认/stage 闭环/stalled/goal 变更/预算耗尽；key 内 phase 边界=分层自动）→ spec §3 AC-001~003、AC-006、AC-008、AC-011
- L1 dossier 同时作为 L2 与人工的输入（人机同尺度）→ spec §3 AC-007、AC-009
- 全局回合预算单处配置 → spec §3 AC-011、AC-018
- additive 共存与测试边界 → spec §1.4、§3 AC-012~014、§4 风险
- console 无状态 + 时间线回放 → spec §3 AC-015~017
