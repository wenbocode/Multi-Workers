# Mini-Spec: mw-phase-writer-recovery-contract

- Date: 2026-10-15
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: mw-worker-output-contract（S2 注入机制的宿主）
- 起因：E2Feature gate-0032 诊断（`H:\git\E2Feature\build-runs\tmp\pm-20261015-gate0032-diagnosis.md`，已由本仓 PM 独立核验四项框架事实全部属实）

## Problem

生产侧与判定侧口径不一致：`autopilot/dispatch.py` 的 `RECOVERY_CONTRACT_TYPES` 只含
`coding/research/review`，conductor 以 `type=phase-writer` 派发的 exec 任务卡**不注入**
「交付段契约（本角色）」四段清单；但 `worker-mode.ts` 的 `judgeRecoveryHere` 对任何
产出 report.md 产物的 write 角色照判四段（`hasReportProduct` 前置 + `judgedProductFile`
先读 report.md）。结果 phase-writer 用自由格式写 report.md → settle 判缺段 → exit=2 →
needs-clarification → 烧轮次 → stalled gate（E2Feature 实证：T-002 两次 attempt，
产物 7/7 字节级正确，纯粹死在报告段名上；剩余 16 个同型任务全部暴露）。

## Change

`packages/multi-workers/autopilot/dispatch.py`：

- `RECOVERY_CONTRACT_TYPES` += `"phase-writer"`, `"roadmap-writer"`（可写内部角色，settle
  可能产出 report.md 产物、届时必被判——注入清单对其惰性无害：不产 report.md 时
  `hasReportProduct=False` 判定根本不触发）
- 注释改写：verifier/reviewer/repair 维持豁免（裁决型/summary-settle，不产 report 产物）；
  删除「phase-writer/roadmap-writer 不产该报告」的错误声称（E2Feature 反例）

`packages/multi-workers/test_mwoc_s2_sections.py`：

- `CONTRACT_TYPES` 增加两角色；`NON_CONTRACT_TYPES` 移除二者（保留 vision/rag-research/
  verifier/reviewer/repair）；相关断言随动

`packages/multi-workers/CHANGELOG.md`：[Unreleased]/Fixed 一行。

## 验收

- `python -m pytest test_mwoc_s2_sections.py -q` 全绿（含改造后的注入/豁免参数化断言）
- `python -m pytest test_autopilot_dispatch.py test_mwds_t29_producer_signal.py -q`（受影响面）不破
- `npm run check` 通过
- 行为锚：`recovery_contract_section("phase-writer")` 非空且含四段 `## <段名>` 代码 span；
  `recovery_contract_section("verifier")` 仍为空串

## 不做

- 不改判定侧（`judgeRecoveryHere` / `output-sections.ts`）——判定行为正确，错在生产侧不告知
- 不豁免内部角色的判定（诊断方案 (b)）——会拆掉真实安全网
- 不动 E2Feature 项目侧（其 PM 已有处置方案：改卡 + approve）

## 验收结果（2026-10-15）

- test_mwoc_s2_sections.py：**17 passed**（contract 角色参数化 5/5 含 phase-writer/roadmap-writer；no_contract 参数化 5/5 含 verifier/reviewer/repair；镜像/幂等/真实任务书/TS readEnvelope 全绿）
- 行为锚：`recovery_contract_section('phase-writer')` 非空含四段；'roadmap-writer' 注入；'verifier' 仍空串
- 受影响面：test_autopilot_dispatch + test_mwds_t29/t13 + conductor + stall → 99 passed；test_mwds_t29::TestParity 1 failed = 既有环境红（子进程 GBK 解码，W-05 全量 verify 已归类），与本 diff 无关（vision 渲染路径未触及）
- npm run check：3 warnings + 2 infos 全部位于 mwoc-*.test.ts（output-contract 族；两文件工作树未改 = HEAD 既有，一文件为并行会话未提交改动）——非本 mini-spec 引入，他窗领地不追；本 key 文件零警告
- 改动：dispatch.py（RECOVERY_CONTRACT_TYPES + 注释改写）、test_mwoc_s2_sections.py（CONTRACT/NON_CONTRACT 分群）、CHANGELOG.md（Fixed 一行）
- 未提交（等用户指令）；E2Feature 运行中的 conductor 仍是旧注入清单，框架修复需框架同步后才对下游生效——其当次 gate 仍按其 PM 方案（改卡 + approve）处置
