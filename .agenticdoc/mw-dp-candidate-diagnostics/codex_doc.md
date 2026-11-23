# mw-dp-candidate-diagnostics · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-candidate-diagnostics
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

共享材料校验对同一个缺候选问题生成一条可以修正的诊断。Preview 和正式提交展示同一组材料问题，PM 能沿用原草稿继续推进。

## 范围

本仓库 DP 材料准备、诊断合并及隔离验收。

## 验收标准

- AC-001: SceneProfiler 两份原材料返回同一组结构化诊断，缺候选只出现一次，字段为 preparation.basis_catalog。
- AC-002: 同时存在证据越界时保留独立的候选与证据诊断，两条入口均零发送。

## 关键决策

在产生候选覆盖诊断时统一字段路径，复用共享诊断的代码和候选数据。用冻结的双样本与并存证据错误做回归。

## 执行与验收

Codex PM 自验 9 项通过。两个原始 SceneProfiler 用例和混合错误用例均通过。 [交付记录](achieved.md)

## 接续须知

从 mw-dp-window-acceptance 的冻结输入和独立验收报告继续。先用本 key 的隔离回放验证，再回到窗口验收项目复验。恢复时显式运行 codex_pm.py status --project . --key mw-dp-candidate-diagnostics。
