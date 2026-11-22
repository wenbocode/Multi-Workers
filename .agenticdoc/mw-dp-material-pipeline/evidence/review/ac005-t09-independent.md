# T09 独立复核 · AC-005 引用修正

复核于 2026-11-23 完成。复核者独立于实现与主验收取证。18 组 AC/VC 中 16 组满足，AC-003 待证，AC-014 因此未满足。AC-005 的合法引用、悬空编号、错对象和冻结正文冲突均有独立核验。 [本批索引](../acceptance/ac005-rework/evidence-index.json) · [36 项对账](../acceptance/ac005-rework/v05-four-stage-comparison.md)

## AC-005 正常入口

| 入口 | 合法引用 | 悬空或错对象 |
| --- | --- | --- |
| PM 的 `dp-w-type` | 一次回环 POST。实际 `desc` 引用 AC-005，文件正文独立引用 VC-005。payload 中两段正文与本 key 的 spec/design 完全一致，VC-005 还声明来源 AC-005。原始候选 `codingA` 反解为 `coding` 并签收。 | 五条实际预检拒绝，发送均为 0。 [正常工具记录](../acceptance/ac005-rework/final-dp-w-type/normal-entry.json) · [请求和原始回包](../acceptance/ac005-rework/final-dp-w-type/loopback-transcript.json) |
| Worker 的 `dp-w-check-task` | 同样一次正常回环 POST，带完整 AC-005、VC-005 原文及水合来源。原始候选 `continueA` 反解为 `continue` 并签收，宿主 run 进入 `done`。 | 同样五条实际拒绝，发送均为 0。 [正常工具记录](../acceptance/ac005-rework/final-dp-w-check-task/normal-entry.json) · [请求和原始回包](../acceptance/ac005-rework/final-dp-w-check-task/loopback-transcript.json) |

两种角色各自覆盖 `desc` 的悬空 AC-999、文件正文的悬空 VC-999、`desc` 和水合正文中的显式跨 key 限定，以及直接读取另一个 key 的同号证据。每组五份原始阻塞记录中，2 项为 `criterion-reference-unresolved`，3 项为 `criterion-reference-other-object`。诊断保留 `state.desc[0]` 或 `state.evidence_sources[i].text`，请求状态均为 `not-sent`。这次 Worker 水合采用普通卡片。带 read scope 的 Worker 仍走原宿主准备或有权限的内联正文，原读取授权继续生效。 [PM 阻塞原件](../acceptance/ac005-rework/final-dp-w-type/dp-blocked) · [Worker 阻塞原件](../acceptance/ac005-rework/final-dp-w-check-task/dp-blocked)

另行探测只改本 key 的临时 spec 正文、保留其冻结哈希，框架拒绝 AC-005 的正文漂移。冲突的 AC/VC 自定义词义也被拒绝。合法 `./spec.md#AC-005` 与本 key 正文一致，跨 key 小写锚点仍被拒绝。八个 DP 的共同准备函数逐个有定向用例，校验将 `desc` 与压缩前所选水合正文的编号绑定到当前合同，并保留相关来源快照。 [覆盖用例](../../../../packages/multi-workers/test/test_dp_material_pipeline_l2.py) · [冻结合同](../contract-freeze.json)

## 同版对账

- 核对 24 个当前源码 SHA-256。spec SHA-256 为 `8b3e042d27ea553c40b9aea596d71eb3099f8f2bd170adf39c232c0fef58dcbb`，36 行对账 SHA-256 为 `992352051656d3c3a6ebc36cb0281045c5db387ee52a17625045241b862a8fa6`。 [证据索引](../acceptance/ac005-rework/evidence-index.json)
- 九例各四段，36 份参考字节及摘要一致。八个有发送的案例按 call ID 和 decision ID 反查同版决策本、原始请求、原始返回、业务反解及回执，核过原始捕获摘要与同版配对。32 行差异有据，4 行符合预期拒绝。旧 dp-auto 的本次 PM 接回和发送前拒绝同次绑定，0 POST，历史 PM 回执仍为空。 [对账 JSON](../acceptance/ac005-rework/v05-four-stage-comparison.json) · [旧 auto 当前接回](../acceptance/ac005-rework/dp-auto-current-pm-handoff.json)
- 独立复跑 L2、受限准备、配对、材料水合及 Monitor 定向用例，170 项通过，1 项平台跳过。当前 T08 运行记录另显示 114 项通过。传输均为隔离回放。 [T08 日志](../acceptance/ac005-rework/integration.log)
- 正式结构验收器确认 36 行参考匹配、32 项 AC/VC 条目独审通过，对应 16 组。门禁退出码为 `2`，与 AC-003 待证及 AC-014 未满足一致。 [验收器](../acceptance/check_review.py)

## 18 组 AC/VC 判定

| AC | VC | 结果 | 证据与界限 |
| --- | --- | --- | --- |
| AC-001 | VC-001 | met | 本批实际发送保留单道单选及合法候选，QG 旧缺 reopen 材料在发送前拒绝。 [负例](../acceptance/ac005-rework/qg-historical-menu-negative.json) · [对账](../acceptance/ac005-rework/v05-four-stage-comparison.md) |
| AC-002 | VC-002 | met | 实际请求引用位置带正文。独立材料套件核行号、截取、失败和约束保留，超限仍走拒绝。 [材料用例](../../../../packages/multi-workers/test_decision_material_sources.py) |
| AC-003 | VC-003 | unverified | 八个发送例保持 `exact_count=null`、`exact_limit_passed=null`。已有 Timi 兼容计量只能确认消息计数，精确边界和验收口径继续待证。 [计量回放](ac014-remaining-and-jev.md) |
| AC-004 | VC-004 | met | 同版决策本、请求和候选来源可反查，正文、原始回包与独立回执仍分离。 [本批对账](../acceptance/ac005-rework/v05-four-stage-comparison.md) |
| AC-005 | VC-005 | met | 两个实际角色入口各 1 条合法发送、5 条零发送负例，八 DP 同一校验。冻结漂移和冲突定义具体拒绝。 [PM](../acceptance/ac005-rework/final-dp-w-type/normal-entry.json) · [Worker](../acceptance/ac005-rework/final-dp-w-check-task/normal-entry.json) |
| AC-006 | VC-006 | met | 同源码隔离 QG 修复、独审、同次正式 writer 及 sign 当前报告保留正反证据。历史本 key 的正式拒签仍与本轮隔离复跑分开。 [本批索引](../acceptance/ac005-rework/evidence-index.json) · [前次本 key 正式回执](../acceptance/final-batch/official-sign-result.json) |
| AC-007 | VC-007 | met | 本轮同源复跑受限 Prepare，权限不增长，原预算与发布、吸收 revision 约束保留。 [定向用例](../../../../packages/multi-workers/test/test_dp_prepare_profile_v1.py) |
| AC-008 | VC-008 | met | 当前同版保留路径及比较资料，旧例缺优先规则拒发。各候选对检查依据先前独立正反验收，AC-005 改动未更改路径比较校验。 [本批路径样例](../acceptance/ac005-rework/runs-v05-lineage/dp-auto-optimized/manifest.json) · [前次独审](ac014-final-independent.md) |
| AC-009 | VC-009 | met | 本批有界路径正例和循环、重复额度、超预算拒发向量通过。 [本批定向测试](../acceptance/ac005-rework/integration.log) |
| AC-010 | VC-010 | met | 八个有发送样例均用本次冻结配对反查 choice、basis、全部 finding 及 remaining 项，定向配对套件复跑。 [同版配对用例](../../../../packages/multi-workers/test_prepared_pair_selection.py) · [本批对账](../acceptance/ac005-rework/v05-four-stage-comparison.json) |
| AC-011 | VC-011 | met | 去重和结果未知沿用原连续性实现。当前旧 auto 同次接回保持 0 POST 和原额度，本轮源变更位于 HTTP 发送前的材料路径。 [前次并发与未知传输](../acceptance/final-batch/summary.md) · [本次 PM 接回](../acceptance/ac005-rework/dp-auto-current-pm-handoff.json) |
| AC-012 | VC-012 | met | 八组请求/原始返回按原字节和捕获摘要一致，独立 Monitor 定向套件通过。 [原件索引](../acceptance/ac005-rework/evidence-index.json) · [Monitor 用例](../../../../packages/multi-workers/test_decision_monitor.py) |
| AC-013 | VC-013 | met | 正常 PM 和 Worker 的拒绝由原主体接回，当前旧 auto 明确保留只读、五分钟总额与最多一次重试。取消/超时/终止沿用已有回放。 [本次接回](../acceptance/ac005-rework/dp-auto-current-pm-handoff.json) · [连续性回放](continuity-normal-entry-report.md) |
| AC-014 | VC-014 | not-met | AC-003 精确计量仍缺目标模型合同与边界证据，整体门禁继续开放。 [验收器](../acceptance/check_review.py) |
| AC-015 | VC-015 | met | 八 DP、九份案例、36 段原字节及原哈希齐全。 [冻结参考](../../docs/reference-records/index.json) |
| AC-016 | VC-016 | met | 两份 cohort 与冻结参考一致，历史模型和用量及 PM 参考裁定分开，每案仍用自己的回包和配对。 [参考合同](../../reference-comparison-contract.md) |
| AC-017 | VC-017 | met | 同源独立复算九例四段，旧 auto 的 4 条符合预期拒绝，历史接回为空。 [本次 36 行](../acceptance/ac005-rework/v05-four-stage-comparison.json) |
| AC-018 | VC-018 | met | 历史传输、当前 PM 参考与当前隔离接回保持各自来源，缺历史真实执行的仍保留 null。 [冻结参考](../../docs/reference-records/index.json) · [当前接回](../acceptance/ac005-rework/dp-auto-current-pm-handoff.json) |
