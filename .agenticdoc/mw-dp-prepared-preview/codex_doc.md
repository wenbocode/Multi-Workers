# mw-dp-prepared-preview · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-prepared-preview
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

同一事项使用同一份材料完成窗口预览和正式提交。让 PM、Worker 在调用 DP 前得到可信的准备结果，减少无效往返，支撑项目目标中的多角色协作。

## 范围

控制与目标工作区均为本仓库。负责窗口 preview、正式准备入口及准备结果的传递。主要入口为 `pm/decision-tool.ts` 的 `previewDecisionInput` 和 `decision_points.py` 的 `prepared_model_request`。具体材料规则由 `mw-dp-material-semantics` 维护，反馈后的业务动作由 `mw-dp-repair-loop` 维护。

## 验收标准

- AC-001: 八个 DP 分别经适用的 PM 或 Worker 公开入口验证正负输入。同一 key、材料、证据字节、合同、规则及准备配置快照下，预览与正式准备的材料结论一致；ready 后新增材料错误数为零。
- AC-002: preview 在宿主权限内读取实际证据、构造模型材料，返回全部可独立确定的字段缺口，标明因前置错误尚未检查的项。预览产生的模型请求、业务裁决和正式尝试扣减均为零。
- AC-003: ready 提供可提交的准备引用，绑定当前事项和材料快照。正常提交消费同版材料，直接提交入口也走同一准备函数。跨事项复用或依赖漂移时给出具体原因，零发送。
- AC-004: 预览后撤销认领、取消父事项、耗尽预算或撤回必要授权，正式入口按当前事实拒绝对应动作。相同请求重复提交沿用现有去重和未知结果核对。

- AC-005: 首次有效材料一次调用完成正式发送；材料拒绝返回已持久化草稿和可定位修正项。PM 仅提交修正值，未改材料完整保留。异字段更新自动合并，同值操作幂等，同字段冲突给出复核提示；文件变化触发复核。恢复后仍检查归属。以引用范围和术语两项交错修正验证一次发送、零误阻塞。

## 关键决策

宿主用同一材料准备入口处理预览和正式提交。首次可直接提交；显式预览及可修正的材料拒绝保存本机草稿。草稿引用绑定 DP、key、任务、触发事项与实际所有者。修正标识记录字段原值及父容器变化；提交者只传标识和值。正式发送前再核对证据快照和现行授权。

## 执行与验收

实现与验收由 Codex PM 执行，无在途 Worker。八入口正负材料使用实际 CLI 和隔离后端核对。窗口回放使用本机 HTTP 服务记录 POST 次数、请求中的术语与证据。Gaze 原材料中同一文件和字段有三个引用区间，修正须能区分具体行段。复核现有认领、父事项、预算、授权以及重复提交。命令及结果见 evidence/codex-pm/self。

## 接续须知

无前置 key。首读 `.agenticdoc/mw-dp-contract-preflight/achieved.md` 和 `packages/multi-workers/decision_points.py`。交给循环与跨窗口验收的接口是准备状态、诊断、快照身份及可提交引用。

恢复时先运行 `python -B packages/multi-workers/codex_pm.py status --project . --key mw-dp-prepared-preview` 核对认领与阶段。
