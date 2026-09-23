# PM State: mw-worker-visibility-gate

## 1. Snapshot
- Key: mw-worker-visibility-gate
- Phase: DONE
- Next Action: 结案：等待用户决定是否 mw build --install 与 R-5（跨 key risk 升级投递）
- Started: 2026-09-23 17:42
- Updated: 2026-09-23 19:25
- Completed: 2026-09-23 19:25

## 2. Task Status

| Task | 内容 | 状态 | 证据 |
|------|------|------|------|
| T-1 | 派发门禁按相位分层（`shared/phase-docs.ts`） | done | worker `mwvg-t1-phase-docs-gate`（9m/40 tools/exit=0）；新测试 11/11；PM 复跑 18/18（含 T-2） |
| T-2 | `shared/pm-state-claim.ts` 同步写入器 | done | worker `mwvg-t2-pm-state-claim`（9m/59 tools/exit=0）；新测试 7/7；字节级：CRLF 27->27、headings 7->7、行外逐字节相等 |
| T-3 | 接线（门禁三处调用点 + 面板聚合行 + claim 同步调用点） | done | worker `mwvg-t3-wiring`（33m/92 tools/exit=0）；新测试 12/12；5 文件 203 passed/0 failed（PM 复跑）；既有 `agent-team-loop.test.ts:1516` 断言窄改 5->3 |
| T-4 | CHANGELOG + `_pitfalls.md` P-011 | done | PM 直执；CRLF 保留（LF-only=0）；三处口径齐全 |
| T-5 | 独立验证（VC-001..013 + 3 变异反例） | running | worker `mwvg-t5-verify` |
| T-6 | pm-state 缺 Claim-Id 行时插行（D-111 语义修订） | done | worker `mwvg-t6-claim-insert`（12m/52 tools/exit=0）；专项 13/13；回归三件套 191/191；字节级 `crlf=26->27 lf_only=0 headings=7->7 updated_lines=1->1 bytes=571->597`；PM 复跑 13/13 |

## 3. Evidence Ledger

| 日期 | 类型 | 内容 | 状态 |
|------|------|------|------|
| 2026-09-23 | research | `evidence/research/spec-dispatch-gate-visibility-baseline-2026-09-23.md`：门禁脱钩/面板口径分叉/claim 双写三处基线（file:line） | PASS |
| 2026-09-23 | research | `evidence/research/design-gate-panel-claim-interfaces-2026-09-23.md`：接口约束 F1~F4 + F3b（本仓四 key 的 pm-state 全部无 Claim-Id 行） | PASS |
| 2026-09-23 | doc | `design.md` mermaid 门禁 `check_mermaid.py` → PASS 0 error | PASS |
| 2026-09-23 | code | `phase-docs.ts`：`gateTierOf` + tier 化 `phaseDocGaps` + `dispatchDocGaps(root,key,phase?)` | PASS |
| 2026-09-23 | test | `agent-team-loop-phase-docs-gate.test.ts` 11/11；`agent-team-loop-pm-state-claim.test.ts` 7/7；PM 复跑 18/18 | PASS |
| 2026-09-23 | test | 既有 `agent-team-loop.test.ts` 172 passed / 1 failed（`dispatchNewTasks` 扫描 gaps 5->3，D-110 待 T-3 修） | OPEN |
| 2026-09-23 | doc | `_pitfalls.md` P-011（claim 双写分叉，索引行权威/liveness 只在索引行判定）；`packages/coding-agent/CHANGELOG.md` 三条 [Unreleased] 条目 | PASS |

## 4. Hypothesis Queue
*(empty)*

| 2026-09-23 | code | `shared/pm-state-claim.ts`：单行替换 + D-111 插行 + 换行守卫 + 原子写（CRLF 27->27 / 26->27，headings 7->7） | PASS |
| 2026-09-23 | code | `pm/ui-bridge.ts` + `pm/pm-orchestrator.ts`：三处门禁传相位、面板跨 key 聚合行、claim 同步两个调用点 | PASS |
| 2026-09-23 | test | 5 文件 204 passed / 0 failed（PM 与 T-5 各自复跑）；新测试 11+8+7+5 = 31 用例 | PASS |
| 2026-09-23 | test | 变异反例 M-1/M-2/M-3：改坏即红 + 复原后 sha256 逐字节相等（`evidence/verify-independent-2026-09-23.md`） | PASS |
| 2026-09-23 | gate | `evidence/quality-gate-report-2026-09-23.md`：31 充分 / 1 有条件（Q-X-006 跨 key risk 升级投递，用户决策项）/ 0 无证据 → 结论 ✅ 通过 | PASS |
| 2026-09-23 | build | `npm run check` EXIT=0（biome 1092 files / pinned-deps / ts-imports / shrinkwrap / install-lock / tsgo / browser-smoke） | PASS |
| 2026-09-23 | regr | `test/extensions` 537 passed / 4 failed，失败全在 `extensions-runner.test.ts`（hook 超时，零引用本 key 模块）→ 环境基线 | PASS-with-note |

## 5. Decisions

- D-101/D-101b/D-102：门禁分层写在 `shared/phase-docs.ts`；新增相位参数可选（缺省 = spec 层）；占位/未知相位一律按 spec 层。
- D-103/D-104：不加任务类型门禁（保住 P-007 口径）；`_scratch` 短路不变。
- D-105/D-106：面板聚合行经可选第六参数注入，单行、末尾、含 owner/计数/`risk=high:K`、≤110 字符。
- D-107/D-108：claim 同步单行原地替换 + 换行守卫 + 原子写；两处 TS claim 调用点（takeOverKey、会话恢复 re-claim）同步，失败只回 warning。
- D-109：拒绝文案与 `DOC_GATE_HINT` 不变，无旁路参数。
- D-110（T-1 实测补充）：门禁调用点实为**三处**（含 `pm-orchestrator.ts:429` 后台扫描），必须同改。
- D-111（T-1 实测补充）：pm-state 缺 `- Claim-Id:` 行时改为在 `- Key:` 后插行（本仓四个 key 的 pm-state 均无该行）；AC-011 按 [REVISED @ 2026-09-23] 修订。

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-09-23 17:42 key 建立（`switch_key`，claim `WENBOZHOU-PC4:93144`，索引相位 SPEC）→ spec.md + key-decision.md + spec 调研笔记 → `advance_phase spec`。
- 2026-09-23 17:45 design.md（D-101~D-109、VC-001~013、Coverage F1~F6）+ design 调研笔记 + evidence-requirement.md；`check_mermaid.py` PASS → `advance_phase design` → plan.md（含并行性分析）→ tasks/T-1..T-5 → `advance_phase plan|tasks|execute`。
- 2026-09-23 17:46 波形 1 派发：T-1（phase-docs.ts）与 T-2（pm-state-claim.ts）并行（文件面不相交）。
- 2026-09-23 17:55 波形 1 双双 done（T-1 9m/40 tools、T-2 9m/59 tools，均 exit=0）；PM 复跑新测试 18/18；既有 `agent-team-loop.test.ts` 172/173（1 failed = gaps 断言 5->3）→ 吸收为 D-110，T-3 任务书补充第三处调用点与窄改授权。
- 2026-09-23 17:56 PM 直执 T-4（CHANGELOG ×3 条 + `_pitfalls.md` P-011，CRLF 保留）。
- 2026-09-23 18:00 派发 T-3（波形 2 接线）。
- 2026-09-23 19:05 T-6 done（12m）→ PM 复跑专项 13/13 + 落实 D-111 后派发 T-5 独立验证（17m）→ 13/13 VC、0 FAIL、三变异红→复原。
- 2026-09-23 19:12 PM 复核：读全部源码 diff、复跑 5 文件 204/204、`test/extensions-runner` 失败隔离（零引用）→ 质检门禁报告（31 充分 / 1 有条件 / 0 无证据）→ 修订 P-011 措辞满足 AC-013 字面口径。
