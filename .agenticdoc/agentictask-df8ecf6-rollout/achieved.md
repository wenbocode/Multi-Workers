# AgenticTask df8ecf6 全项目安装

## 系统行为变化

已安装到 Multi-Workers、Bearing、Overcode、AssetsGate、Gaze、RenderPerformance、SceneProfiler、UEPerformanceFlow，共八个现存 AgenticTask 项目。八个 skill 的实际 HEAD 与 Claude 安装记录均为 df8ecf6。

Multi-Workers 保留原有开发克隆和 junction，六个文件的未提交实质改动、原始文件字节与暂存状态均核对完整。另三个 plan_closure.py 的原有换行字节差异也保留。其他七个项目安装干净 skill 克隆；八个项目的 Claude 四目录全部匹配干净安装源。

## 验收证据

逐项检查全框架文件、SKILL.md 散列、HEAD、安装记录、Claude 目录、原始备份和开发差异。结果保存在 [安装报告](evidence/installed.json)，正式验收覆盖 AC-001 至 AC-003。 [验收命令](evidence/codex-pm/self/1795520805258569200-_ywdght1/command.log)

干净源的无调研证据推进、规模提示、Goal Alignment 和 AC 下限相关定向测试共五项通过。Review list 已写入安装状态。

## 遗留

原适配器和安装记录位于每个项目的 `.mw/agentictask-df8ecf6-rollout/`。七个普通项目的旧 skill 完整保存在其中的 `skill-before/`，包括 SceneProfiler 和 UEPerformanceFlow 的本地修改。Multi-Workers 开发修改继续留在开发克隆中，Claude 使用干净提交。已有会话需重开或重载后刷新技能。
