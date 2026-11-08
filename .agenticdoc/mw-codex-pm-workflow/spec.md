# Codex PM 开发与验证

## §0 Goal Alignment

本任务服务于项目的多 worker 并行开发目标。GC-1 沿用文件协调和 MW 原有派发、launcher 边界。预期收益是用户关闭 Codex 对话后能从另一个进程读取同一 key、任务卡、worker 产物和独立验收结果。

## 用户流程

Codex 依 AgenticTask 准备 spec、design、plan 和自包含的卡。通过控制工作区显式派发已认领 key 下的一张卡，在后台服务处理后重新打开该 key，检查产物，并用 PM 运行的验收命令生成证据。Codex 根据证据进行返工或通过现有 phase gate 结案。研究依据见 evidence/research/spec-workflow.md。

## 验收标准

- AC-001 已注册且处于执行阶段的 key 可以向现有 MW 派发一张开发卡。重试同一任务时不能产生双份工作，非法路径或不完整卡被拒绝。
- AC-002 新的 CLI 进程按 key 恢复阶段、任务、worker 终态与产物位置。区分 worker 完成和 PM 验证通过。
- AC-003 PM 针对已完成任务独立执行验收命令，保留命令、退出码和输出。失败或缺失产物不能报通过，重新验证可追溯。
- AC-004 文档给出从建 key 到验收、结案的路径。以真实派发和 launcher 进程、可重复执行的隔离 worker 验证正常及失败路径。

### 可复用资产

复用 AgenticTask 阶段脚本、PM 的 dispatch_worker、共享队列和 launcher。由现有写者维护各自状态。

### 需规避坑点

P-001 要求明确 UTF-8 读写。每个 worker 的运行身份与所属 key 一并校验。进程退出、队列状态和测试结果分别记录，避免将 worker 自述解释为验收通过。
