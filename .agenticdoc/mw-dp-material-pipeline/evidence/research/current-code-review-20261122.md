# 2026-11-22 DP 目标与当前源码核对

当前目标仍是为八类 DP 提供足够且可追溯的材料、可比较的单选、完整反解以及原主体接回。建议先补候选和材料投影，再把现有来源、接回、签收和捕获接进同一条验收链。设计基线仍为 [v0.5 范本](../../docs/reference-records/index.md)，验收仍使用 [9 例 × 四段](../../reference-comparison-contract.md)。

检查基线为 HEAD `76a300ee3` 及 2026-11-22 当前工作区。多个 PM/Worker 源文件有未提交改动，`decision-handoff.ts` 和 `local-selection-store.ts` 等属于当前工作区源码。下列结论区分已提交能力与工作区能力，未核部署包是否同步。

| 目标 / 任务 | 源码当前能做什么 | 本 key 剩余工作 |
| --- | --- | --- |
| 固定候选与配对，AC-001/010 · T01/T06 | 单题配对已接入八 DP，按冻结材料和依据反解业务结论及 `basis_id`，无配对才拒绝。QG 仍按当前材料过滤不适用分支，随附样例只生成 `fixA`。TS preview 展示注册表候选和引用绑定，实际线上候选由 Python 渲染。 | 从 Python 最终候选和涵盖的业务结论判定可发性，预览说明两者差异。两个 fix wire 仍只有一个业务结论。QG 要明确分支适用条件与缺失诊断，满足 AC-001 后才发送，不补造 reopen 依据。冻结结构化原因/剩余项以及同版映射。[配对与反解](../../../../packages/multi-workers/decision_backends.py#L779) · [分支约束](../../../../packages/multi-workers/decision_points.py#L4081) · [预览](../../../../packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts#L874) |
| 文件材料，AC-002/004 · T02 | `evidence_refs` 已走范围校验、UTF-8 正文、hash、来源字段和摘录。精确文件授权可通过 `.mw/decision-evidence.yml`，缓存和签收已有来源新鲜度校验。Worker 有累计读守卫时，CLI 因无法扣同一账本而拒绝隐式读。 | 复用原读取器和拒绝行为，补必要正文与模型字段之间的覆盖断言。完善可追溯的语义摘要及受守卫 Worker 已授权正文或预算交接；摘录只证明实际保留的行。[现有 prepared 请求说明](../../../../packages/multi-workers/docs/prepared-decisions.md) |
| 投影与术语，AC-003/004/005 · T03 | `model_state_for` 已按注册表投影；注册表仍要求 w-type/steer 等传任务原文，steer 仍有 `pm_decision_background` 和 `worker_execution`。prepared 请求另把 `basis_catalog` 和 `prepared_at` 放进实际 state。 | 继续做八种专属投影、短 desc 与精确计量、AC/VC 正文和术语闭包、逐字段来源。保留现有模型字段白名单机制，改变其中业务内容及准备层落点。[投影](../../../../packages/multi-workers/decision_points.py#L3816) · [发送组装](../../../../packages/multi-workers/decision.py#L1985) · [注册表](../../../../packages/multi-workers/decide_registry.json#L113) |
| Prepare，AC-007 · T04 | 有本地 preview、prepared book 检查、证据读取和现有 host 接回接口。按拟议工具名查找，源码未见专用 prepare 发布/吸收链。 | 单独比较实际需要委托的复杂场景，沿用简单路径。在既有工具注册、读取和预算接口上补专用 profile、模型选择、revision、原子发布/吸收和隔离验收。 |
| QG/sign 与 auto，AC-006/008/009 · T05 | 当前已有适用门禁路由、本地 QG 独审绑定和独审证据签收复用。后两块分别涉及工作区本地 QG 和已提交 `f809b5ef7`、`76a300ee3` 的签收路径。auto 已有至少两项和字段/名称校验。 | 将当前独审及同对象版本证据接入模型材料，再核逐适用 AC/VC、目标/偏差、当前 QG。auto 补 2–5、有实质区分的两两比较和有界条件后继。路由适用性和签收来源选择留在现有 host 路径。[门禁路由](../../../../packages/coding-agent/src/extensions/agent-team-loop/pm/gate-route.ts) · [本地 QG](../../../../packages/coding-agent/src/extensions/agent-team-loop/pm/local-qg-consumer.ts#L192) · [独审签收](../../../../packages/multi-workers/decision_signoff_result.py#L1294) |
| 连续性，AC-011/013 · T06 | 已有 `logical_id` 回放、来源变更旧结果失效、工作区 handoff/执行记录、小额固定划拨及离线接回。continuity key 已登记 DONE，隔离闭环证据与本 key 验收分别保留。客户端发送仍有按 retryable 重试的通用循环。 | 沿用原主体、预算、停止和签收写者。验收补 prepared_at 变动、并发同语义、确认已发但结果未知、两层重试计数，以及来源漂移、Gate route 和手工控制路径。区分明确未送达、服务明确拒绝与提交状态未知。[当前回放入口](../../../../packages/multi-workers/decision.py#L1874) · [重试循环](../../../../packages/multi-workers/decision.py#L2437) · [continuity 实际交付](../../../mw-pm-dp-continuity/achieved.md) |
| 回放，AC-012 · T07 | 已有 book、wire、lifecycle 和 monitor 展示，捕获明确标脱敏/截断。工作区 PM handoff/执行记录另存 `decision-handoffs`。 | 采用同一决策/事项或接回绑定串联四段。展示原始返回可见性、捕获完整度和实际 PM 接回/执行；缺证按缺证展示。干净离线范本做字节对比，生产保留现有脱敏与截断边界及相应状态。[捕获](../../../../packages/multi-workers/decision_wire.py#L1600) · [显示标记](../../../../packages/multi-workers/decision_dashboard.js#L646) · [接回存储](../../../../packages/coding-agent/src/extensions/agent-team-loop/shared/local-selection-store.ts#L72) |
| 验收，AC-014—018 · T08/T09/T10 | 已有旧范本和局部回归，配对套件的八 DP 测试验证单题与反解，QG 用例明确接受这个按分支过滤后的候选集。 | 接入当前生产入口的离线观测，完成 36 项对照与独立复核。沿用旧范本原件，新增的投影和候选用对应版本的 faux 回包。 |

## 本轮核验

- 直接运行 Python 生产候选渲染器读取项目随附样例，未发送请求。QG 为 `[fixA]`，sign 为 `[continueA, user-confirmA]`。其余样例 wire 数为 w-type 4、steer 4、w-check 3、gate 4、auto 3、route 7。该结果是当前代码的样例行为，可与实际监控记录分别核对。
- 用 auto 候选校验器输入 1、2、5、6 项。为候选设不同 ID 和标签，保持内容相同。1 项被拒绝，2、5、6 项均通过，显示 5 项上限和实质可区分性尚未落实。
- 在 `packages/multi-workers` 运行 `python -m pytest -q -p no:cacheprovider --basetemp <独立短目录> test_prepared_pair_selection.py test_decision_material_sources.py test_prepared_file_freshness.py test_decision_evidence_policy.py`，101 passed、2 skipped。
- 扩展检查中的 loopback wire 用例遇到 `WinError 10013`。独审签收回归中 4 个正例遇到 Windows 临时写入/替换错误，短路径复测仍有 `WinError 5`，其余 8 个用例通过。这些结果记录为当前环境未验证，尚不足以给生产路径判回归或通过。

## 规划调整

T01/T03/T05 优先补候选与达意材料，T02/T06/T07 复用已有底座补验收连接。T04 保留在计划内，专职承担复杂材料准备的隔离和吸收。下一次实施前，以届时的源码和加载版本重验本表中涉及未提交文件及运行环境限制的项目。

同日收集到 6 个项目的 193 条阻塞事件，其中 137 条为 `input-incomplete`。98 条明确记录文件证据准备失败且未发送。T02/T03 应优先用这些真实输入形态核引用解析和诊断，T06/T07 应把材料、窗口模式、上游和接回阶段分别归类。回执仅记录阻塞，候选收缩结论来自单独运行的源码样例。见[跨项目回执](../dp-blocked/20261122/report.md)。
