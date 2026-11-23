## 典型回执与 v0.5 四段

四段分别核决策本、实际模型输入、原始模型返回、PM 接回。生产回执只填写能从原件证实的阶段，其余标为未知。右栏链接到同类 DP 的 v0.5 完整范本，范本是独立的设计验证记录。点击事件 ID 可打开筛选页中的对应回执。

| 案例 | 决策本和实际材料证据 | 模型输入 | 原始返回 | PM 接回证据 | v0.5 参照与验收差额 |
| --- | --- | --- | --- | --- | --- |
| 1 · UEPerformanceFlow QG [字段超限](#event-896ec525-cf6f-4d4e-ab5d-f6dd5f747074) | `ueperf-platform`，`review_evidence[0]` 报 `max-bytes`。完整决策本未关联。 | 工具执行入口拒绝，未见已发 body。 | 未发分支无模型回包。 | 回执只记录阻塞。 | [QG](../../../docs/reference-records/dp-QG.md) 的 payload 直接提供 AC/VC、F1/F2 与来源。验收覆盖字段超限时的精确原因、合规摘录及必要事实保留。 |
| 2 · UEPerformanceFlow QG [选项绑定](#event-b97cb967-a92d-4d7c-adb7-7bf1a3bcb907) | 同一 key 的 `basis_catalog[1].applies_to` 校验失败。回执缺原值，无法确定填了哪个选项。 | 工具执行入口拒绝。实际 wire 候选未知。 | 未见原始回包。 | 回执只记录阻塞。 | [QG](../../../docs/reference-records/dp-QG.md) 的历史实际候选 `passA/fixA/fixB`，`fixB→fix+F1/F2`。范本缺 reopen 与本次绑定失败分别校验。 |
| 3 · UEPerformanceFlow w-type [路径未解析](#event-c95485d7-59b8-45fc-a807-850e5d4d9096) | `material.task_goal` 含路径。3 项 `evidence-file-unresolved`，另有 1 项读范围拒绝。 | 证据准备标 `not-sent`。没有最终请求。 | 无。 | 回执没有后继执行。 | [w-type](../../../docs/reference-records/dp-w-type.md) 发代码/测试判据和约束，回 `codingA` 后 PM 参考准备 coding 任务。将目标正文、待产物和有范围的来源明确分开。 |
| 4 · RenderPerformance steer [绑定路径无效](#event-6c17a1c6-9884-446d-bd75-08ba5d537693) | `evidence_refs[0].field` 无效，回执列出可用绑定落点。 | `not-sent`。 | 无。 | 回执只记录阻塞。 | [steer](../../../docs/reference-records/dp-pm-steer.md) 的模型材料给 W1/W2、约束和预算判据，回 `splitA`，PM 复核预算后规划分拆。检查新投影的实际叶子路径和提示一致。 |
| 5 · UEPerformanceFlow steer [保护最小项超预算](#event-f0170bb5-37d8-4e42-b897-76fc19244185) | `evidence_sources` 返回 `compression-required`，核心材料和保护内容仍超预算。 | `not-sent`。缩窄行范围或准备有来源摘要后，才能重新组装。 | 无。 | 未见继续执行或追加额度。 | [steer](../../../docs/reference-records/dp-pm-steer.md) 保留真正影响分拆的来源和预算。验收验证临界值、原额度及受保护事实不丢。 |
| 6 · Bearing steer [凭据扫描](#event-b2ab3612-2d7c-4263-8e91-acf94fe4af37) | `work-memory` 材料凭据检查拒绝，未保留命中字串。 | 回执明确未发送。 | 无。 | 未见接回结果。 | [steer](../../../docs/reference-records/dp-pm-steer.md) 的术语区说明缩写。对照已有术语例外及真实凭据拦截。该事件是否误判待绑定原输入及加载版本后判断。 |
| 7 · Gaze w-type [禁用](#event-1360d8d6-d6af-444b-86ee-7ba597a84343) | 只有事项引用和窗口拒绝状态，未见决定材料。 | pre-transport 阻塞。 | 无。 | 实际接回未关联。 | [w-type](../../../docs/reference-records/dp-w-type.md) 是模型启用时的参考。禁用时核原 PM 有界分类和业务动作的单独证据。 |
| 8 · SceneProfiler w-type [DNS](#event-97b212a2-33e4-468d-be16-b8f79d9720cb) | 记录了请求标识，完整决策本未关联。 | 到传输阶段，是否有可读冻结 body 需关联 wire。 | 无模型回包证据，错误为 `getaddrinfo failed`。 | 未关联。 | [w-type](../../../docs/reference-records/dp-w-type.md) 返回模型选择。此例验收传输失败分类，以及与已发结果未知不同的处置。 |
| 9 · UEPerformanceFlow w-type [接回绑定](#event-0d83d716-8c5b-4888-a099-f7e51506aa2c) | 事后审计记录原 ask 无 `task_key`。 | 原 body 未关联。 | 原返回未关联。 | 审计记载补填 `task_after` 被拒。原 host 生命周期收据未关联。 | [w-type](../../../docs/reference-records/dp-w-type.md) 把选型参考和真实派工分开。验证正常/错绑回收，未知任务不靠模型或事后填值补造。 |
| 10 · Gaze sign [签收准备失败](#event-38f7d52e-3205-4a6c-acf3-6b861928fac9) | sign 路径报告文件证据准备失败，具体字段未记录。 | 明确未发送。 | 无签收结论。 | 回执未给签收写入证据。 | [sign](../../../docs/reference-records/dp-sign-key.md) 的 `continueA` 来自带目标、偏差、当前 QG 的实际请求，参考处置是补证后复核。验收核源准备/refusal 与 writer 状态分别入记录。 |

原 `ueperf-platform` 共四条 QG：两条 `max-bytes`、两条 `applies_to`。其余两条可在图表按 key 筛选。当前随附 QG 样例只有 `fixA` 是独立源码观测。回执既没有记录这个候选集，也没有证明四条事件因单候选阻塞。

## 当前代码覆盖与任务更新

状态按当前仓库源码和可追溯回归判断。项目进程的部署版本及历史事件复跑仍需各自取证。配对、文件、来源新鲜度和授权策略定向回归为 101 通过、2 跳过。以下把现有能力、诊断改进与剩余工作分别落到责任卡。

| 合并原因 | 条数 | 现在已覆盖或已修复的部分 | 还要补的验收或行为 |
| --- | ---: | --- | --- |
| 文件证据准备失败 | 98 | `5af9b8529` 正文注入、稳定快照和来源新鲜度，`19203773e` 精确读授权，`eaefe72d9` 结构化字段及 `allowed_fields`。最新仍有文件不可达、绑定错误等拒绝。 | AC-002/004/005 · T02/T03/T04。区分必要引用和计划产物，真实 producer 用新投影的可绑定路径，测试读范围和已授权正文。合并视图保留多个诊断代码。 |
| 单字段超限 / 材料超预算 | 4 / 2 | `5af9b8529` 在整请求预算内做机械摘录，保护最小项仍超限时明确返回 `compression-required`。 | AC-002/003/004 · T02/T03。区分原始字段限额和 hydration 后请求限额。保留失败、未知、AC/VC 和判据，验证窄范围或有来源摘要的成功对照。 |
| 依据与选项 / 材料字段绑定 | 23 / 1 | `6bbed2f2d`、`bda661a3b` 修正引用提示与缺项/非法分类，`901846b97` 提前展示注册表选项及具体绑定错误。新版提示能处理同型输入。 | AC-001/004/010 · T01/T03/T05/T06。复用诊断，验收 Python 最终合法业务选项覆盖与固定集合、同版原因反解。TS preview 的允许值只是输入词汇。 |
| 凭据扫描拒绝 | 4 | 明确有保护性拒绝。`94183b11f` 已修特定 Bearer 术语误命中。 | AC-004/005 · T03。回归术语和真实凭据正反例。四条原阻塞的命中原因仍待原输入证据，尤其保留修复提交之后的 Bearing 回执。 |
| 禁用 / 未配置 / 上游 DNS | 39 / 11 / 3 | `e1737950e` 有窗口控制，`18d478fa4` 有原 PM 分类，continuity 已有原预算和角色接回。DNS 记录已有具体底层错误。 | AC-011/012/013 · T06/T07。分别观测拒绝阶段、真实尝试数和接回/执行。在原额度内验证，不因 reload 或修材料清零。 |
| 接回绑定 / 未认领 | 2 / 1 | 已有无绑定 `task_key` 时拒绝 `task_after` 的检查，`68e52f89a` 补充认领拒绝解释。 | AC-012/013 · T06/T07。将同一次请求和原主体接回联结，区分历史审计与实际 writer 证据。准备权限和正式认领分开检查。 |
| 签收材料准备失败 | 1 | 已有来源准备拒绝与独审签收复用入口。 | AC-006/012 · T05/T07。引用实际 QG 对象/版本，按阶段保存来源错误、未发、无结论及 writer 状态。签收写入的 Windows 环境限制另查。 |
| 仅知前置检查失败 | 4 | 原回执没有字段或 detail。现有诊断入口提供补充采样点。 | AC-012/017 · T07/T08。保留未知，后续仅按确定阶段与信息完整度验收。 |

实施验收保留 v0.5 九例四段的 36 行。跨项目回执合并后取典型场景补充回归，以事件 ID、实际阶段和字段证据为锚点。T08 复用已有回归，T09 对照拒绝点、业务影响和证据来源。完整条目仍可在图表筛选。
