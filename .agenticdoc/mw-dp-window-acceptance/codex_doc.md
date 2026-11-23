# mw-dp-window-acceptance · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-window-acceptance
- Phase: VERIFY
- Claim-Id: codex
- Status: active

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

验证新窗口遇到此前未见的材料问题时，能从正常入口恢复提交或准确交接，保持项目中多窗口 PM/Worker 协作的连续性。

## 范围

控制与目标工作区均为本仓库。本 key 持有跨 key 的隔离回放、留出样本、证据和独立验收报告。复用 `mw-dp-material-pipeline` 既有请求、回执和对账方法。产品缺陷归属对应实现 key。

## 验收标准

- AC-001: 将 Gaze、UEPerformanceFlow、RenderPerformance 的原始输入及引用文件固定到隔离回放，记录来源与摘要。覆盖空 finding、旧新 AC 映射、证据越界、多层 VC、术语和真实独审／预算边界。
- AC-002: 覆盖八个 DP 的适用角色与正负入口。先冻结至少一个开发回放未使用的其他窗口样本及独立预期，再组合文件漂移、历史引用或授权变化；留出样本首次运行结果和后续修复分别记录。
- AC-003: 同一快照 ready 后新增正式材料错误为零；可修材料实际补证并提交，或在预算／三次失败上限处准确交接。合法业务拒绝、资源不足和框架矛盾均有正确的责任人和可核实的下一步。
- AC-004: 分别统计预览结果、正式准备拒绝、模型发送数、错误升级人工数、实际业务效果和未验证项。已发未知结果、缺独审及缺预算的负例没有重复或越权动作。由另一执行者按相同输入复核。

## 关键决策

验收以正常注册工具、真实文件读取和现有 writer 为准，隔离传输可用回环替身。留出样本在其首次验收前由验收方保管。评估对象是窗口行为，无需重发三个生产事项。

## 执行与验收

已冻结四个窗口的原始两次调用及可得来源。SceneProfiler 的预期先写入，再启动首次运行。隔离回放和运行版本核对已记录。UEPerformanceFlow 的最小修正可以进入正式单次发送。独立执行者复现 8 通过、3 失败，核实 Gaze 和 SceneProfiler 的框架缺口。当前保留 VERIFY。 [验收报告](evidence/acceptance-report.md) [独立复核](evidence/independent-replay.md)

三个缺口分别走 mw-dp-candidate-diagnostics、mw-dp-qg-pass-preflight、mw-vc-layout-parsing。最终隔离验收独立复跑 21 项全部通过，保留原始失败记录。真实窗口验证继续保留 VERIFY。 [修复后复验](evidence/post-fix-replay.md)

## 接续须知

依赖 `mw-dp-prepared-preview`、`mw-dp-material-semantics`、`mw-dp-repair-loop`。目标常驻与缓存归 `mw-key-spec-goal`。修复后隔离复验已记录。实窗需核对运行版本，再按同一验收口径观测裁决与写入。

恢复时先运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-dp-window-acceptance` 核对认领与阶段。
