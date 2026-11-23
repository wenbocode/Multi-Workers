# mw-dp-qg-pass-preflight · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-qg-pass-preflight
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

在发送 DP-QG 请求前确认 pass 有绑定当前验收范围的独审证据。缺证据时准确告诉 PM 下一步，同时保留有资格的其他业务选项和回包后的新鲜度检查。

## 范围

本仓库 DP-QG 的共享准备、正式发送及独审证据绑定。

## 验收标准

- AC-001: 缺少当前独审时 pass 不进入可发送候选；没有其他合格候选时 preview 和正式都在发送前报告 PM 应补当前独审。
- AC-002: 有合法 fix 或 reopen 的请求仍可按有效候选处理；有当前独审的 pass 和发送后的证据漂移检查各有正反例。
- AC-003: SceneProfiler 组合用例的旧快照、撤销认领、缺独审均零发送，保持业务动作零。

## 关键决策

把现有的 scoped 独审事实交给共享准备逻辑，从业务候选里剔除未证实的分支。在回包后继续核对实际引用范围和独审快照。

## 执行与验收

Codex PM 自验 86 项通过。缺独审、独审可核、发送前变动及发送途中变动分别验收。 [交付记录](achieved.md)

## 接续须知

从 mw-dp-window-acceptance 的冻结输入和独立验收报告继续。先用本 key 的隔离回放验证，再回到窗口验收项目复验。恢复时显式运行 codex_pm.py status --project . --key mw-dp-qg-pass-preflight。
