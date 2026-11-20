# mw-dp-input-diagnostics · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-input-diagnostics
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

落实 [DP 输入诊断与文件引用设计](../mw-dp-material-pipeline/design-input-diagnostics.md)，减少无法定位原因的本地拒绝，并可靠绑定实际提交的证据与发布身份。

<!-- 写明预期交付，以及它如何对应 .agenticdoc/goal.md。 -->

## 范围

控制工作区 Multi-Workers。目标为以当前已安装合并包为基线的新隔离发布目录。既有连续性任务占用共享开发面，本次不改其工作区源码和任务状态。允许候选源码、测试、文档、打包及验收通过后的全局扩展和 CLI 入口安装。正在运行的窗口与后端留待安全点重载。

<!-- 写明工作区、可改文件和本次交付边界。 -->

## 验收标准

- AC-001: 无发送的证据准备拒绝返回安全结构化诊断，覆盖 Bearing、Gaze、UEPerformanceFlow 的历史失败形态及重复调用。
- AC-002: PM、Worker、CLI 与决策本接入显式文件引用，正文不触发读取，行范围和现有权限规则生效，旧请求维持原语义。
- AC-003: 发布包保留合并基线的 gate 路由、Dual Engine 写入规则和 Python bearer 修复，执行仓库检查及定向回归。
- AC-004: 安装后在新 Pi 进程验证实际加载的扩展哈希、选用的 Python 入口、协议能力和本地错误回传。

<!-- 每条标准使用 - AC-001: ... 格式，并写明可观察的结果。 -->

## 关键决策

- 将诊断回传和显式引用分开验证，合并到一次全局安装。以已安装的 gate-route 包为基线，避免带入活跃工作目录中的其它改动。
- 在独立发布目录保存实现，在本任务证据下保存基于发布基线的补丁。续接主工作树时需按当前依赖和活跃任务写面重新合并。

<!-- 只记影响实现或交接的决定与理由。 -->

## 执行与验收

- AC-001 到 AC-003 的候选验收通过。见 `evidence/codex-pm/self/1795191162917273800-mnau7msq/result.json`。
- AC-004 的全局新进程验收通过。见 `evidence/codex-pm/self/1795191233676253400-2ctfl8p2/result.json`。
- 旧决策工具和决策本套件与安装前基线逐项比较，失败项分别为 20 和 69，集合一致。见 `evidence/legacy-suite-comparison.json`。

<!-- 按需要列出工作项、执行者、进度及 evidence 中的验证路径。区分自验与独立复核。 -->

## 接续须知

安装和新进程验证完成。没有在途 Worker。现有窗口需在安全点 reload，使用 `/mw runtime` 核对实际加载版本。

<!-- 写明当前进度、在途 Worker、阻塞、恢复命令和下一步。结案时记录 achieved.md 与遗留去向。 -->
