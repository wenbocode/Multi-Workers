# mw-dp-call-policy · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-call-policy
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

收敛 PM 常规流程的模型调用。先用可确定的本地事实选择下一入口、派发类型和签收路径，降低重复准备材料的开销，沿用项目的责任归属、权限与证据边界。交付边界是三项调用策略。

## 范围

控制与目标工作区均为 E:/gitlite/Multi-Workers。改动候选为 PM 常规流程中的路由调用点、派发类型选择调用点、Done 的现有证据签收接线，以及对应定向测试。先读真实入口，确认哪些行为已存在，仅补缺口。共享文件涉及其它 active key 时先确定写面。

本 key 采用既有 gate、派发校验、独审及签收 writer。八 DP 的注册、候选、材料、配对、回放格式和 [v0.5 四段验收](../mw-dp-material-pipeline/reference-comparison-contract.md) 由原 key 维护。材料压缩、prepare Worker、卡点后 dp-auto 范本及其验收留在 [原计划](../mw-dp-material-pipeline/plan.md)。

## 验收标准

- AC-001: 触发来源、阶段或现有 gate 能明确入口时，常规 PM 流程以本地事实路由，dp-route 模型调用为 0。无法判定时反馈具体缺口；显式 dp-route 查询仍可返回原协议结果，实际 gate 的权限由原入口核验。
- AC-002: 任务卡类型明确且现有能力、写面、模型和派发检查全部满足时，常规派发采用本地类型，dp-w-type 模型调用为 0，并可追溯到卡片和本地判据。冲突或硬检查失败保留拒绝；确有多个合理类型且材料合格时，原 dp-w-type 仍可参与选择。
- AC-003: 当前独审、合同、产物和现有签收条件齐备时，常规 Done 经既有 `mw decide sign --for-done` 本地证据路径，dp-sign-key 模型调用为 0。证据漂移、独审缺失或审批未完成时保留正式拒绝或继续补证。具备有效材料且确需交付语义取舍时，原 dp-sign-key 入口继续可用。
- AC-004: 从常规 PM 入口留存三路实际调用计数、本地判据、原具名 writer 或原拒绝结果。以定向离线正反例复验显式模型路径和原权限。注册、材料及原 v0.5 九例四段（36 项）保持同一合同。

## 关键决策

- 一个 PM 负责这三项共同的调用层策略，可依次交付。它们共享入口和证据边界，进一步拆 key 会增加责任移交。
- 已知可复用入口包括 [gate 路由](../../packages/coding-agent/src/extensions/agent-team-loop/pm/gate-route.ts)、[持有认领的 PM 类型接回](../../packages/coding-agent/src/extensions/agent-team-loop/pm/type-fallback.ts)和 [独审证据 Done preflight](../../packages/multi-workers/decision_signoff_result.py#L1459)。当前代码已经采用的行为用定向回归确认。缺证的签收不得用模型补作授权或独审。
- 无须等材料链路全部实现即可独立验收本 key。原 key 的标准同样由自身的证据链验收。若两边共写同一文件，按调用策略先写、移交实际源码及验证证据、原 key 再接续的顺序处理。

## 执行与验收

计划先定位并验证常规路由，再核类型，最后核签收。每一路用现有公开入口和隔离替身验证一个本地成功、一处硬检查拒绝和一个原模型入口回归。真实正例须由原生产入口产生本地证据和处置，测试不手写其应生产的回执。首次实现只处理这三项策略。

AC-004 使用[八个 DP 同次对账](../mw-dp-material-pipeline/decision-chain-reconciliation.md)中的本地路径。按实际判据和已发生的 writer 回执对账，明确零模型尝试和空回包。交付证据引用原 key 的同一次记录要求。

2026-11-22 已实现调用策略并完成定向自验。常规路由复用现有 gate 读取；普通派发采用已钉住的合法卡片类型，派发产物记录来源与零调用；Done 复用现有独审证据签收及其拒绝逻辑。见 [achieved.md](achieved.md) 和该页的命令证据。

## 接续须知

恢复时用 `codex_pm.py status --project E:/gitlite/Multi-Workers --key mw-dp-call-policy` 查权威索引及证据。材料链路由原 key 接续，保留八 DP 显式模型路径，使用各自已有消费者与 writer 对账。

## 合并发布

调用策略与 [材料链路](../mw-dp-material-pipeline/README.md) 已共同进入主工作树。见 [合并发布验收](evidence/integrated-release/summary.md)。
