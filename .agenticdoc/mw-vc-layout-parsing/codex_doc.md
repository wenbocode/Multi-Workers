# mw-vc-layout-parsing · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-vc-layout-parsing
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

同一个 VC 的内容在常见单行和分行写法下都能被识别，以相同的验收身份用于材料准备。格式错误可定位到条目、文件和行号。

## 范围

本仓库合同的 VC 解析和材料诊断，复用原始 Gaze 和 RenderPerformance 证据。

## 验收标准

- AC-001: Gaze 八条原始单行 VC 可解析；RenderPerformance 的多行与多层 VC 按原语义解析。
- AC-002: 等价单行和多行产生相同身份；缺字段、重复 ID 保持明确拒绝，材料回执带可定位的诊断。

## 关键决策

复用现有 VC 字段抽取边界，单行仅识别明确的 Layer、Output、Source 标记，身份仍由断言和三个字段计算。

## 执行与验收

Codex PM 自验 67 项通过，含原始 Gaze 和 Render 文档、等价身份和可定位的负例。 [交付记录](achieved.md)

## 接续须知

从 mw-dp-window-acceptance 的冻结输入和独立验收报告继续。先用本 key 的隔离回放验证，再回到窗口验收项目复验。恢复时显式运行 codex_pm.py status --project . --key mw-vc-layout-parsing。
