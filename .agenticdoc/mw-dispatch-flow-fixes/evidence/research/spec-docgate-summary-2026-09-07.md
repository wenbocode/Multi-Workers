# Research: docs-gate 噪音与播报通道（spec）

## 决策问题

§1.1 缺陷④、AC-010/011：docs gate 为何对全终态 key 每 session 重复告警；"每窗口最多一条 worker summary"在 pi ExtensionAPI 约束下如何成立。

## 调研方法与出处

- 代码：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:311-360`（dispatchNewTasks：docs gate 评估在 `dispatched.has(taskKey)` 判定之前）、`:463-476`（docGateWarned 为 pmActivate 闭包内 Set，每 session 重置）、`ui-bridge.ts:21-28`（displaySummary → sendMessage customType "agent-team-loop:worker-summary"）
- API：`packages/coding-agent/src/core/extensions/types.ts:1289-1300`（sendMessage / appendEntry，无消息更新/替换接口）、`:142,169-171`（ui.notify / ui.setWidget——setWidget 同 key 原位更新）
- 语义：`packages/coding-agent/src/core/session-manager.ts:92-141`（CustomEntry 不参与 LLM 上下文；CustomMessageEntry——sendMessage 的产物——参与 LLM 上下文）
- 现状数据：`.agenticdoc/agent-team-loop/`（spec 17KB/design 27KB 在，evidence/ 仅 runs/，根有 evidence-requirement.md）、`.agenticdoc/mw-dispatch-reliability/`（evidence/ 仅 runs/）；两者 workers/ 下任务全部已在 `_workers.parallel` 且终态
- 先例：`ui-bridge.ts:245-248` setWatchWidget（belowEditor widget 原位更新，轮询刷新）
- 用户决策：2026-09-07 需求澄清第二轮（决策 6/7）

## 发现

1. **gate 评估顺序缺陷**：dispatchNewTasks 对每个有 workers/ 目录的 key 先做 docs gate（缺 spec/design/research 即告警一次）再逐任务查 `dispatched`——全终态 key 也告警。warnedKeys 是 session 内存态，新窗口必重触发（用户观察"新 pi 窗口都触发这两个"的根因）
2. **两 key 的 gate 缺口是 research note 位置**：spec.md/design.md 均达标（≥500B），缺 `evidence/research/spec-*.md` 与 `design-*.md`——其证据存于 evidence/runs/ 与根 evidence-requirement.md（早于 research 目录约定的历史布局）
3. **播报通道 API 约束**：sendMessage append-only（无更新接口）；CustomMessageEntry 参与 LLM 上下文（PM agent 感知 worker 终态依赖此通道）；ui.setWidget 同 key 原位更新（watch widget 先例）但纯 UI、不入 LLM 上下文
4. displaySummary 的调用点：worker 终态摘要（每任务一条）、docs-gate 告警（每 key 每 session 一条）、mw 服务启动播报——同一 customType 并列出现

## 结论 → 决策映射

- 发现 1 + 用户决策 6 → AC-010：gate 仅对"存在 ≥1 未入队任务"的 key 评估告警
- 发现 3/4 + 用户决策 7 → 播报作用域收敛（AC-011）：终态摘要固化现有 watch.key 过滤；扫描 gate 告警仅在本窗口认领该 key 时播报。弃用早先"单一可更新播报面"方案——作用域过滤后每窗口播报量天然有界（gate 告警每认领 key 每 session 至多一条 + 终态摘要每任务一条），且避开 sendMessage append-only 约束；dispatch_worker 同步 blocked 工具反馈（ui-bridge.ts）不受作用域影响
- 发现 2 → 数据维护：为两个旧 key 补 evidence/research/{spec,design}-*.md 零调研声明（指向其真实证据位置），使其即使未来派发新任务也过 gate——本轮已随澄清执行

## 修订记录

- 2026-09-07 第三轮澄清：用户决策 7 由"每窗口单一可更新播报面（合并/更新）"修订为"播报仅覆盖本窗口认领 key 的相关 worker"；本文相应更新结论映射，代码事实（发现 1-4）不变
