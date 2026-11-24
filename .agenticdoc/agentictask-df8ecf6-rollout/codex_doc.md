# agentictask-df8ecf6-rollout · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: agentictask-df8ecf6-rollout
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

把 AgenticTask df8ecf6 安装到本次涉及的所有项目，并核对 skill 与 Claude 适配器实际版本。

## 范围

控制工作区 E:/gitlite/Multi-Workers，目标为 Multi-Workers、Bearing、Overcode、AssetsGate、Gaze、RenderPerformance、SceneProfiler、UEPerformanceFlow。使用独立干净的 df8ecf6 安装源，保留开发克隆的未提交改动及 junction。盘点 E:/gitlite 和 E:/MWWS 下已安装框架的项目共八个。

## 验收标准

- AC-001: 八个项目 skill 的 HEAD 为 df8ecf6，适配器文件逐项核对符合该提交；开发克隆的未提交文件、暂存状态和 junction 保持完整并记录差异。
- AC-002: 八个项目 Claude 四个目录的框架文件和安装记录匹配干净提交，原副本已备份。
- AC-003: 验证报告记录项目路径、实际 HEAD、文件散列、安装源和开发克隆例外，review list 更新安装状态。

## 关键决策

用户明确授权跨项目安装与保留开发克隆未提交改动。开发克隆以 HEAD 加原有工作区修改保留，Claude 使用干净提交内容。SceneProfiler 和 UEPerformanceFlow 的旧框架有本地修改，Overcode 的 skill 为项目内副本。更新前备份全部旧 skill 和 Claude 目录，除开发克隆外安装干净的指定提交。

## 执行与验收

八个项目安装并核验完成，skill HEAD 与 Claude 版本均为 df8ecf6。Multi-Workers 开发克隆原始文件、暂存区、diff 及 junction 均与安装前一致。七个普通项目的 skill 全文件匹配干净源，Claude 四目录在八个项目均匹配。验证见 evidence/installed.json 及 evidence/codex-pm/self/1795520805258569200-_ywdght1/result.json。干净源的 5 项阶段推进定向测试通过。Review list 已更新。

## 接续须知

恢复命令 python packages/multi-workers/codex_pm.py status --project . --key agentictask-df8ecf6-rollout。当前无在途 Worker。安装源位于 .mw/agentictask-df8ecf6，各项目备份位于 .mw/agentictask-df8ecf6-rollout。旧会话重开或重载后读取更新后的技能。
