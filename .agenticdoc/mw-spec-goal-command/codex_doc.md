# mw-spec-goal-command · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-spec-goal-command
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

让 pi PM 窗口为当前旧 key 拟定并由人确认 `spec_goal`，补上项目目标对齐提示。确认后的文字写入现行规格，后续在同一 key 的请求中沿用。

## 范围

控制及目标工作区为本仓库。涉及 MW PM 命令注册、现有 key 目标读取及回归测试。命令面向持有真实认领的完整 SDD key。

## 验收标准

- AC-001: pi PM 命令对当前唯一认领的 SDD key 发一次无工具模型请求，输入仅含现行规格与项目目标，草稿进入交互编辑器。
- AC-002: 用户确认后只补当前规格的目标段。旧规格有无 §0 都能被原有 prompt 读取。已有目标保留，其他合同原文保留。
- AC-003: 取消、模型失败、未认领、已存在目标、规格变化或认领切换时没有目标写入。用户在确认前可修改草稿。

## 关键决策

注册 `/mw-spec-goal`。使用窗口当前模型和现有凭证解析，沿用原有目标注入。批准时重新核对认领和规格快照。

## 执行与验收

<!-- 按需要列出工作项、执行者、进度及 evidence 中的验证路径。区分自验与独立复核。 -->

## 接续须知

恢复命令为 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-spec-goal-command`。
