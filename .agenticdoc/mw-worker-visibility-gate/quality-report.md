# Quality Report: mw-worker-visibility-gate

> 日期: 2026-09-23 | Phase: VERIFY → DONE
> 结论: ✅ 通过（13/13 AC 有证据，0 无证据，1 项交叉项为已记录的用户决策项）

## 1. 交付面

| # | 文件 | 类型 | 规模 |
|---|------|------|------|
| 1 | `packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts` | 改 | +43 / -11（`GateTier` + `gateTierOf` + tier 化 `phaseDocGaps` + `dispatchDocGaps(root,key,phase?)`） |
| 2 | `packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-claim.ts` | 新 | `syncPmStateClaimId`（单行替换 / D-111 插行 / 换行守卫 / 原子写） |
| 3 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | 改 | +140/-（三处门禁传相位、`renderWatchLines` 可选第六参数 + 跨 key 聚合行、`TakeoverResult.claimSync` + `claimSyncWarningText` + 四个展示点） |
| 4 | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | 改 | +37/-（后台扫描传目标 key 相位、会话恢复 re-claim 同步、三处面板调用传 `dispatchedTaskKeys`） |
| 5 | `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 改 | 单一 hunk：`:1516` gaps 断言 5→3 + 注释（D-110 后果） |
| 6 | `packages/coding-agent/test/extensions/agent-team-loop-phase-docs-gate.test.ts` | 新 | 11 用例 |
| 7 | `packages/coding-agent/test/extensions/agent-team-loop-pm-state-claim.test.ts` | 新 | 8 用例 |
| 8 | `packages/coding-agent/test/extensions/agent-team-loop-watch-aggregate.test.ts` | 新 | 7 用例 |
| 9 | `packages/coding-agent/test/extensions/agent-team-loop-pm-state-sync.test.ts` | 新 | 5 用例（含 2 个接线反例） |
| 10 | `packages/coding-agent/CHANGELOG.md` | 改 | `[Unreleased]`：`### Added` ×3 + `### Fixed` ×1（CRLF 保留） |
| 11 | `.agenticdoc/_pitfalls.md` | 改 | 新增 P-011（claim 身份双写分叉；三处口径齐全） |

不含 `dist/**`（未构建）、不含任何 Python。

## 2. AC 勾销表

| AC | 结论 | 关键证据 |
|----|------|----------|
| AC-001 | PASS | `VC-001: spec_phase_pass=true task_md=true`（工具入口） |
| AC-002 | PASS | `VC-002: blocked=true design_gap=1 task_dir=false` |
| AC-003 | PASS | `VC-003: blocked=true design_evidence_gap=1` |
| AC-004 | PASS | `VC-004: tier=spec design_gaps=0 variants=4` |
| AC-005 | PASS | `VC-005: spec_gaps=4 design_gaps=0` |
| AC-006 | PASS | `VC-006: agg_lines=1 owner_in_line=true count_in_line=true max_len≤110` |
| AC-007 | PASS | `VC-007: agg_lines=0 identical_baseline=true`（对 `git show HEAD:` 面板逐行比对） |
| AC-008 | PASS | `VC-008: agg_lines=1 terminal_counted=1` |
| AC-009 | PASS | `VC-009: risk_marker=risk=high:1`（trace.log `[CHECKPOINT]` 源） |
| AC-010 | PASS | `VC-010: claim_ids_equal=true headings=7 updated_lines=1 crlf=27->27`（+ restoreWatch 路径） |
| AC-011 | PASS（REVISED） | `VC-011: inserted=true ok=true outside_identical=true` / `no_key_line ok=false untouched=true` |
| AC-012 | PASS | `VC-012: coding_at_spec_allowed=true` + DESIGN 反例 |
| AC-013 | PASS（措辞修订后） | P-011 三处口径连续命中：索引行 / 两处同值 / liveness |

## 3. 相位与任务

| Task | 执行者 | 结果 |
|------|--------|------|
| T-1 门禁分层 | worker `mwvg-t1-phase-docs-gate` | done（9m/40 tools） |
| T-2 claim 同步写入器 | worker `mwvg-t2-pm-state-claim` | done（9m/59 tools） |
| T-3 接线 | worker `mwvg-t3-wiring` | done（33m/92 tools） |
| T-4 文档 + 记忆登记 | PM 直执 | done |
| T-6 D-111 插行分支 | worker `mwvg-t6-claim-insert` | done（12m/52 tools） |
| T-5 独立验证 | worker `mwvg-t5-verify` | done（17m/91 tools，13/13 VC，0 FAIL） |

## 4. 与 spec/design 的偏差（全部已登记）

1. `phaseDocGaps` 的 `tier` 为可选缺省 `design`（design §4.1 原写必填）——为保住既有 9 处单参调用；生产路径恒显式传 tier。
2. 门禁调用点由 2 处修正为 3 处（D-110，含 `pm-orchestrator.ts:429`）。
3. AC-011 语义修订为"缺 Claim-Id 行时插行"（D-111，依据：本仓四个 key 的 pm-state 均无该行）。
4. T-5 的 VC-009 夹具写 trace.log `[CHECKPOINT]` 行（`readTaskProgress` 的真实解析源），而非 `progress.md` 的 `[machine]` 行。
5. 新用例落点：`test/extensions/`（4 个新文件），未按 design 期建议新建 `test/suite/` 文件（包内单一 vitest 配置，功能等价；既有 suite 文件保持零改动，除 1 处断言）。

## 5. 独立验证与反例

- 独立验证：T-5（另一 worker，独立夹具/独立探针/独立重做三处入口），`evidence/verify-independent-2026-09-23.md`。
- 变异反例：M-1（tier 归一化）、M-2（risk 标记）、M-3（claim 同步短路）全部"改坏即红 + sha256 逐字节复原"。
- PM 复核：读全部源码 diff、复跑 204/204、复跑 T-6 专项 13/13、`audit_phase` PASS、`test/extensions-runner` 失败隔离取证（零引用本 key 模块）。

## 6. 遗留（去向明确）

| ID | 内容 | 去向 |
|----|------|------|
| R-1 | 框架仓库：claim 桩缺 `- Updated:`/`- Next Action:` → **非缺陷**（`advance_phase.py` 有显式桩升级路径）；索引 Phase `—`/`SPEC` 与 pm-state 桩 `init` 的 pending 等价性 | ✅ 已闭合（框架仓库 `d0834ae`：VC-030 + AG-008 + 文档，已推送） |
| R-2 | 新 key 首次 claim（pm-state 尚未创建）仍回一条 `pm-state.md missing` warning | 接受不处理（下次 claim/takeover 收敛） |
| R-3 | `phaseDocGaps` 的 tier 缺省为 `design`（新调用点遗忘传参会静默回到六项全查） | 记入 `_pitfalls.md` 待办式建议；既有单参调用清零后改必填 |
| R-4 | `test/extensions-runner.test.ts` 4 个 hook 超时 | 归入 Windows 环境基线，不在本 key 处理 |
| Q-X-006 | 跨 key risk 升级投递未做（面板已可见 risk 标记） | 用户决策项（spec §4 未决 Q-1） |
| — | 未 `mw build --install`（全局 bundle 仍为旧版） | 需用户决定；本 key 不代做（AGENTS.md 构建纪律） |
