# mw-dp-material-semantics · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-material-semantics
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

让 PM 能如实表达零 finding、历史范围变更及当前验证条件。让每项正式结论只由适用、可追溯的证据支持，服务项目目标中的独立执行与验收。

## 范围

控制与目标工作区均为本仓库。负责 QG 候选、判据引用、术语和合同解析。Python 负责材料语义，窗口工具对齐材料结构与诊断。复用 `mw-dp-prepared-preview` 的草稿和提交。

## 验收标准

- AC-001: 零、单个、多个未解决 finding 各有正常输入。显式 reasons 空对象可直接提交 pass 与 reopen 判据。非空时每个可执行 fix 只选真实 finding，宿主推导互斥且完整的剩余集合。实际结论仍检查适用条件和独立证据。
- AC-002: 审查清单严格绑定当前 key、合同版本和判据正文。已有替换映射的旧编号与普通日志中的提及保留来源；无法绑定的现行验收、伪造替换和跨 key 借用不能支持结论。用 UE 的旧 AC-203 → 现 AC-304 验证两个方向。
- AC-003: 从 Render 原设计解析全部六条 VC，包括多层 Layer。损坏的合同项给出来源位置；同版冻结与正式准备按同一身份核对。越界行号返回文件长度及范围，PM 可重选证据。
- AC-004: 普通文件名和实例标识在原上下文中无需虚构定义；确实影响判断且缺定义的领域术语给出原句、字段或证据位置。同一符号在不同用途上的正反例均有覆盖。
- AC-005: 用额外编号和组合材料验证用途规则。日志中出现的未知编号保留原文，写入现行审查清单时须绑定当前合同。材料准备结论在同一快照的 preview 和正式入口一致，拒绝时零发送，草稿局部修正后只发送一次。

## 关键决策

引用是否参与验收由所在字段、来源和用途决定。已有替换映射提供历史出处。QG 只声明一次当前 finding，每个修复选项引用选中的 finding，宿主推导剩余项。

## 执行与验收

由 Codex PM 实施和自验。已核对 Gaze、UE、Render 的材料输入和陌生编号组合。正式请求接隔离后端，保留发送次数和请求材料证据。验收和遗留见 [achieved.md](achieved.md)。

## 接续须知

无前置 key。输入在 `E:/MWWS/Gaze/.agenticdoc/gaze-insights-evidence/evidence/framework-qg-retry-20261123-1811.md`、`E:/MWWS/UEPerformanceFlow/.agenticdoc/ueperf-t43/spec.md`、`E:/MWWS/RenderPerformance/.agenticdoc/m0-context-capture/design.md`。与预览 key 可并行设计，按函数划分共享 Python 文件。

恢复时先运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-dp-material-semantics` 核对认领与阶段。
