# spec 阶段调研计划与证据基线 — `mw-dispatch-settle-gates`（2026-10-10）

本 note 是 spec 阶段的**调研声明**（≥1 份 `spec-*.md` 门禁），并作为本 key 的**证据基线**：本 key 的每条缺口在立项时**已经带完整坐标**，因此调研只针对两个"设计前真正未知"的问题，其余不复研。

## 1. 证据基线（立项即已闭合，坐标经 PM 独立复现）

| 缺口 | 坐标 | 出处 |
|---|---|---|
| G-a AC-008 只交付面板半边（`mw doctor` 的 G2 面从未进卡） | design `:147`/`:386`/`:432`；`rg 'blocked_on_human\|BLOCKED_ON_HUMAN' packages/multi-workers/mw_common.py` = **0 命中**（`monitor.ts` = 10 命中） | QG-A §1/§4 行动项 1（PM 已 grep 复现） |
| G-b AC-007 无 stage 终态判据 | `gates.py:770-772`（只按 `status=="pending"`）、`conductor.py:2564`（取数）、`conductor.py:2541-2551`（三条件） | QG-B §1 #14①、§5 问题 #2（PM 已 read 复现） |
| G-c AC-024 有未守卫写面 + 文案不符 | 守卫仅 `ui-bridge.ts:1333`/`:1698`；`/worker` `:1710`（注册 `pm-orchestrator.ts:1059`）经 `:66-67` 直通，写 `:1813-1819`；文案 `:241-242` | QG-B §1 #2、§5 问题 #1（PM 已 grep/read 复现） |
| G-d AC-022 边界（D-038） | `autopilot/dispatch.py:621-633`；`rg 'run\.json' dispatch.py` = 0 命中 | QG-A §1 Q-AC-022、§4 行动项 5（PM 已 grep 复现） |
| G-e R22 派发期无可满足性校验（空转实例） | `worker-file-tool.ts::WORKER_FILE_NAME_RE`（basename 白名单 + fail-closed）；`worker-mode.ts:114-117`；实例 `mw-gate-verdict-hardening/workers/mwg-qg-review-20261010/`（`trace.log` 8 次调用/零写入、`output.md` 无 `report.md`） | 本会话现场取证（PM） |
| G-f 结算期无产物判据（`hasProductEvidence` 语义错位） | `pm-orchestrator.ts:487-492`（谓词含 `trace.log`，且 `run.json` 启动即写）；`worker-mode.ts:1345-1362`（settle 即 exitCode 0） | 本会话现场取证（PM） |
| G-g `output.md` 信息量 | `changedFiles` 全扩展唯一赋值点 `worker-mode.ts:1359` = `[]`；`output-writer.ts:9/65`；`Exit Reason` 常量 `worker-mode.ts:1361` | QG-B §1 #14③ 邻域；本会话取证（PM 对 T-10 的 127 次调用实测 `Changed Files (none)`） |
| G-h 文档一致性 | spec AC-021 措辞 / spec §2.3 vs AC-025⑤ / plan §2.5 值域 / design §0 `ac_count: 24` + §8 表止于 AC-018 / `evidence-requirement.md` 缺失 / T-18/19/20 卡头 VC 少报 / pm-state "1406 vs 1407" | QG-A §4 行动项 4/6/7/10、§6.1、§6.3 |

复审原件（不改写，只引用）：
- `mw-gate-verdict-hardening/evidence/quality-gate-report-review-a-evidence-chain-20261010.md`（131 问 / 114 ✅ / 17 ⚠️ / 0 ❌）
- `mw-gate-verdict-hardening/evidence/quality-gate-report-review-b-code-adversarial-20261010.md`（14 项 / 12 成立 / 2 反证 / 27 组对照静态全承重 / 15 个抽查测试无空洞）

## 2. 本阶段要回答的两个真问题（并行派发，各自唯一证据文件）

- **RQ-1**（`mds-rq1-stage-terminality`）→ 收录为 `evidence/research/spec-stage-terminality-20261010.md`
  问题：AC-002 的"stage 终态"到底用什么机器信号判？候选锚穷举（key 级 `- Phase:`/`Completed:`、roadmap/closure 的 key-status、`[END]`/`[DONE]`、gate frontmatter 的 stage 归属、`_index.parallel` Phase 列）+ 每候选的反例风险 + 调用面清点（提醒 vs 展示必须区分）+ 推荐落点 + 反向用例设计。
- **RQ-2**（`mds-rq2-product-contract`）→ 收录为 `evidence/research/spec-worker-product-contract-20261010.md`
  问题：AC-006/AC-007 的判据来源。只读角色交付通道实况（`mw-gate-verdict-hardening` 30 个 worker 目录中 `report.md` 有无统计、5 个无 `report.md` 的合规先例及其交付方式）、`hasProductEvidence()` 在 dispatch vs settle 两种语义下的差异、`run.json` 字段（`artifacts`）能承载的"产物事实"、`output.md` 的写入形态（append/覆盖/占位符常量）、以及**若改 settle 判据会牵动哪些既有测试**（列测试名）。

## 3. 零调研声明（其余不研）

G-a/G-b/G-c/G-d/G-g/G-h 的坐标已由两份复审给出并经 PM 复现（见上表），**不再重复调研**；本 key 不涉及平台/性能新面（沿用既有 4 s tick、只读面不建文件、零回填放行三条既有约束）。
