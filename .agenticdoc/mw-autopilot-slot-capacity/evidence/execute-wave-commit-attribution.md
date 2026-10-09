# execute 波提交归属判定（逐文件逐 hunk）

本文件由 `.tmp/msc-commit-attribution.py` 机器生成：对工作树中每个有改动的**已跟踪**文件，
按 `git diff -U0` 取 hunk，按关键词族投票判定归属 —— 「本 key」= `mw-autopilot-slot-capacity`，
「vision key」= `mw-vision-role`（另一窗口，phase DONE 但未提交）。

**注意**：关键词投票只是**线索**，不是判决。混合 hunk 与无签名 hunk 必须人工看 diff。

- 有改动的文件数: 90 · hunk 总数: 661
- 本 key hunk: 198 · vision hunk: 27 · 混合/无签名: 436

| 文件 | hunk# | 归属 | +行数 | 本 key 命中 | vision 命中 |
|---|---|---|---|---|---|
| `.agenticdoc/_index.parallel` | 1 | 无签名（人工判） | 0 | 0 | 0 |
| `.agenticdoc/_index.parallel` | 2 | **混合（人工判）** | 2 | 1 | 4 |
| `.agenticdoc/_pitfalls.md` | 1 | 本 key | 22 | 16 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 1 | 无签名（人工判） | 4 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 3 | 无签名（人工判） | 3 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 6 | 无签名（人工判） | 9 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 7 | 无签名（人工判） | 25 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 8 | 无签名（人工判） | 27 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 9 | 无签名（人工判） | 15 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 10 | 无签名（人工判） | 7 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 11 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 12 | 无签名（人工判） | 9 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 13 | 无签名（人工判） | 4 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 16 | 无签名（人工判） | 6 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence-requirement.md` | 1 | 本 key | 1 | 1 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 1 | 本 key | 8 | 2 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 2 | 本 key | 2 | 7 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 3 | 本 key | 3 | 7 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 4 | 本 key | 8 | 10 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 6 | 本 key | 15 | 1 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/plan.md` | 7 | 无签名（人工判） | 3 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/pm-state.md` | 1 | 无签名（人工判） | 2 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/pm-state.md` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-07-auto-decision-core.md` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-07-auto-decision-core.md` | 2 | 本 key | 1 | 3 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-07-auto-decision-core.md` | 3 | 无签名（人工判） | 13 | 0 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-08-pending-review.md` | 1 | 本 key | 23 | 10 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-11-parity-corpus.md` | 1 | 本 key | 1 | 1 | 0 |
| `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-11-parity-corpus.md` | 2 | 本 key | 1 | 1 | 0 |
| `.agenticdoc/mw-vision-role/achieved.md` | 1 | vision key | 21 | 0 | 12 |
| `.agenticdoc/mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md` | 1 | vision key | 5 | 0 | 12 |
| `.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md` | 1 | vision key | 241 | 0 | 80 |
| `.agenticdoc/mw-vision-role/handover.md` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `.agenticdoc/mw-vision-role/handover.md` | 2 | vision key | 19 | 0 | 14 |
| `.agenticdoc/mw-vision-role/pm-state.md` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/CHANGELOG.md` | 1 | 本 key | 12 | 24 | 0 |
| `packages/coding-agent/CHANGELOG.md` | 2 | 本 key | 2 | 2 | 0 |
| `packages/coding-agent/dist/core/tools/bash.d.ts.map` | 1 | 本 key | 1 | 8 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js` | 1 | 本 key | 6 | 1 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js` | 3 | 本 key | 23 | 1 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js` | 4 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js` | 5 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/core/tools/bash.js.map` | 1 | 本 key | 1 | 8 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.d.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.d.ts` | 2 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.d.ts.map` | 1 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js` | 3 | 无签名（人工判） | 91 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js` | 4 | 无签名（人工判） | 19 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js` | 5 | 无签名（人工判） | 110 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js.map` | 1 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 2 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 3 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 4 | 本 key | 12 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 5 | 本 key | 4 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts` | 6 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts.map` | 1 | 本 key | 1 | 6 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 2 | 本 key | 17 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 3 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 4 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 5 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 6 | 无签名（人工判） | 10 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 7 | 本 key | 26 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 8 | 无签名（人工判） | 39 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 9 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 10 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 11 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 12 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 13 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 14 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 18 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 19 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 20 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js` | 21 | 无签名（人工判） | 30 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js.map` | 1 | 本 key | 1 | 6 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 2 | 本 key | 6 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 3 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 4 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 5 | 本 key | 2 | 3 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 6 | 本 key | 10 | 7 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 7 | 无签名（人工判） | 25 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts` | 8 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts.map` | 1 | 本 key | 1 | 41 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 2 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 3 | 本 key | 5 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 4 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 5 | 本 key | 1 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 6 | 本 key | 1 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 7 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 8 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 9 | 本 key | 28 | 6 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 10 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 11 | 无签名（人工判） | 12 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 12 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 13 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 15 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 18 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 19 | 无签名（人工判） | 15 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 20 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 21 | 无签名（人工判） | 43 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 22 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 23 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 24 | 本 key | 15 | 5 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 25 | 本 key | 23 | 4 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 26 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 27 | 本 key | 10 | 7 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 28 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` | 29 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js.map` | 1 | 本 key | 1 | 41 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.d.ts.map` | 1 | **混合（人工判）** | 1 | 11 | 4 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.js` | 1 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.js.map` | 1 | **混合（人工判）** | 1 | 11 | 4 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.d.ts` | 1 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.d.ts` | 2 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.d.ts.map` | 1 | vision key | 1 | 0 | 36 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 3 | 无签名（人工判） | 19 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 5 | vision key | 48 | 0 | 28 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 7 | vision key | 4 | 0 | 4 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 8 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 9 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 10 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 11 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 12 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 13 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` | 16 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js.map` | 1 | vision key | 1 | 0 | 36 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts` | 1 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts` | 2 | 无签名（人工判） | 30 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts.map` | 1 | vision key | 1 | 0 | 6 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js` | 1 | vision key | 1 | 0 | 4 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js` | 2 | vision key | 1 | 0 | 2 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js` | 3 | 无签名（人工判） | 73 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js.map` | 1 | vision key | 1 | 0 | 6 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.d.ts` | 1 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.d.ts.map` | 1 | 本 key | 1 | 5 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.js.map` | 1 | 本 key | 1 | 5 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts` | 1 | 本 key | 5 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts` | 2 | 本 key | 3 | 4 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts` | 3 | 本 key | 18 | 7 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts.map` | 1 | 本 key | 1 | 26 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 1 | 本 key | 35 | 9 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 2 | 本 key | 3 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 3 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 4 | 本 key | 1 | 5 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 5 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js` | 6 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js.map` | 1 | 本 key | 1 | 26 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts` | 1 | 无签名（人工判） | 10 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts` | 3 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts` | 4 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts.map` | 1 | 本 key | 1 | 3 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 1 | 本 key | 7 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 2 | 无签名（人工判） | 18 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 3 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 4 | 本 key | 13 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 5 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 6 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 7 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 8 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 9 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 10 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 11 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 12 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 13 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` | 15 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js.map` | 1 | 本 key | 1 | 3 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts` | 1 | 无签名（人工判） | 18 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts` | 2 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts` | 3 | 本 key | 25 | 1 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts.map` | 1 | **混合（人工判）** | 1 | 20 | 8 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 1 | vision key | 3 | 0 | 8 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 2 | 无签名（人工判） | 20 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 4 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 6 | 本 key | 20 | 2 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 7 | 无签名（人工判） | 26 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 8 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 9 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 10 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 11 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 12 | 无签名（人工判） | 15 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 13 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 15 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 16 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 17 | 无签名（人工判） | 26 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` | 18 | 无签名（人工判） | 18 | 0 | 0 |
| `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js.map` | 1 | **混合（人工判）** | 1 | 20 | 8 |
| `packages/coding-agent/src/core/tools/bash.ts` | 1 | 本 key | 6 | 1 | 0 |
| `packages/coding-agent/src/core/tools/bash.ts` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/core/tools/bash.ts` | 3 | 本 key | 23 | 1 | 0 |
| `packages/coding-agent/src/core/tools/bash.ts` | 4 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/core/tools/bash.ts` | 5 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 2 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 7 | 无签名（人工判） | 146 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` | 8 | 无签名（人工判） | 107 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 2 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 3 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 4 | 本 key | 28 | 3 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 5 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 6 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 7 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 8 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 9 | 本 key | 19 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 10 | 无签名（人工判） | 34 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 11 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 12 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 13 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 14 | 无签名（人工判） | 6 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 16 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 18 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 19 | 无签名（人工判） | 6 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 20 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 21 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 22 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts` | 23 | 无签名（人工判） | 27 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 2 | 本 key | 6 | 2 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 3 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 4 | 本 key | 6 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 5 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 6 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 7 | 本 key | 1 | 2 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 8 | 本 key | 1 | 2 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 9 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 10 | 本 key | 2 | 3 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 11 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 12 | 本 key | 28 | 6 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 13 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 14 | 无签名（人工判） | 25 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 15 | 无签名（人工判） | 12 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 16 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 18 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 19 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 20 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 21 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 22 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 23 | 无签名（人工判） | 15 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 24 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 25 | 无签名（人工判） | 39 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 26 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 27 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 28 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 29 | 本 key | 12 | 5 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 30 | 本 key | 23 | 4 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 31 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 32 | 本 key | 10 | 7 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 33 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 34 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 35 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 1 | 本 key | 6 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 2 | 本 key | 21 | 9 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 3 | 本 key | 22 | 6 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 4 | 本 key | 6 | 3 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 5 | 本 key | 1 | 5 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 6 | 本 key | 3 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | 7 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 1 | 本 key | 7 | 2 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 2 | 无签名（人工判） | 18 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 3 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 4 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 5 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 6 | 本 key | 6 | 1 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 7 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 8 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 9 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 10 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 11 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 12 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 13 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 14 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 17 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 1 | 无签名（人工判） | 22 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 2 | 本 key | 44 | 2 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 3 | 无签名（人工判） | 12 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 4 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 7 | 无签名（人工判） | 14 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 8 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 9 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 10 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 11 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 12 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | 13 | 无签名（人工判） | 47 | 0 | 0 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 1 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 5 | 无签名（人工判） | 10 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | 7 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 1 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 3 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 7 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 8 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-config-sync.test.ts` | 9 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/coding-agent/test/suite/autopilot-console.test.ts` | 1 | 本 key | 16 | 9 | 0 |
| `packages/coding-agent/test/suite/autopilot-console.test.ts` | 2 | 本 key | 1 | 2 | 0 |
| `packages/coding-agent/test/suite/autopilot-console.test.ts` | 3 | 本 key | 1 | 1 | 0 |
| `packages/coding-agent/test/suite/autopilot-console.test.ts` | 4 | 本 key | 2 | 2 | 0 |
| `packages/coding-agent/test/suite/autopilot-monitor.test.ts` | 1 | 本 key | 8 | 3 | 0 |
| `packages/coding-agent/test/suite/autopilot-monitor.test.ts` | 2 | 本 key | 7 | 1 | 0 |
| `packages/coding-agent/test/suite/autopilot-monitor.test.ts` | 3 | 本 key | 14 | 1 | 0 |
| `packages/coding-agent/test/suite/autopilot-monitor.test.ts` | 4 | 本 key | 4 | 2 | 0 |
| `packages/coding-agent/test/suite/autopilot-monitor.test.ts` | 5 | 本 key | 43 | 8 | 0 |
| `packages/multi-workers/CHANGELOG.md` | 1 | 本 key | 12 | 50 | 0 |
| `packages/multi-workers/CHANGELOG.md` | 2 | 本 key | 2 | 3 | 0 |
| `packages/multi-workers/CHANGELOG.md` | 3 | 本 key | 8 | 18 | 0 |
| `packages/multi-workers/UPDATE.md` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/UPDATE.md` | 2 | 本 key | 34 | 11 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 1 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 3 | 本 key | 5 | 2 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 4 | 本 key | 14 | 6 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 5 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 6 | 本 key | 7 | 3 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 7 | 本 key | 7 | 4 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 8 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 9 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 10 | 无签名（人工判） | 20 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 11 | 本 key | 15 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 12 | 本 key | 9 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 13 | 无签名（人工判） | 14 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 14 | 本 key | 80 | 12 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 18 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 19 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 20 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 21 | 本 key | 51 | 5 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 22 | 本 key | 4 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 23 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 24 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 25 | 本 key | 9 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 26 | 本 key | 12 | 2 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 27 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 28 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 29 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 30 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 31 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 32 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 33 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 34 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 35 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 36 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 37 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 38 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 39 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 40 | 本 key | 12 | 3 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 41 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 42 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 43 | 本 key | 14 | 4 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 44 | 本 key | 4 | 2 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 45 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 46 | 本 key | 76 | 16 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 47 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 48 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 49 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 50 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 51 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 52 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 53 | 本 key | 366 | 56 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 54 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 55 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 56 | 本 key | 10 | 1 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 57 | 本 key | 11 | 3 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 58 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 59 | 本 key | 6 | 4 | 0 |
| `packages/multi-workers/autopilot/conductor.py` | 60 | 本 key | 1712 | 127 | 0 |
| `packages/multi-workers/autopilot/config.py` | 1 | 本 key | 7 | 1 | 0 |
| `packages/multi-workers/autopilot/config.py` | 2 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/autopilot/config.py` | 3 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/autopilot/config.py` | 4 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/multi-workers/autopilot/config.py` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 1 | 本 key | 31 | 1 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 3 | 本 key | 6 | 1 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 4 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 7 | 本 key | 5 | 3 | 0 |
| `packages/multi-workers/autopilot/dispatch.py` | 8 | 本 key | 1 | 3 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 1 | 本 key | 13 | 7 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 3 | 本 key | 9 | 7 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 5 | 本 key | 30 | 6 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 6 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 7 | 无签名（人工判） | 22 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 8 | 本 key | 5 | 1 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 9 | 本 key | 29 | 7 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 10 | 本 key | 1 | 2 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 11 | 无签名（人工判） | 32 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 12 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 13 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 18 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 19 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 20 | 无签名（人工判） | 43 | 0 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 21 | 本 key | 15 | 10 | 0 |
| `packages/multi-workers/autopilot/gates.py` | 22 | 本 key | 28 | 12 | 0 |
| `packages/multi-workers/autopilot/roadmap.py` | 1 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/autopilot/roadmap.py` | 2 | 本 key | 6 | 2 | 0 |
| `packages/multi-workers/autopilot/roadmap.py` | 3 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/autopilot/timeline.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/timeline.py` | 2 | 本 key | 11 | 7 | 0 |
| `packages/multi-workers/autopilot/timeline.py` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/autopilot/timeline.py` | 4 | 本 key | 7 | 1 | 0 |
| `packages/multi-workers/autopilot/timeline.py` | 5 | 无签名（人工判） | 11 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 5 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 7 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 8 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 9 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 10 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 11 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 12 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 13 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 14 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 15 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 16 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 17 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 18 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 19 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 20 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 21 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 22 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 23 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 24 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 25 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 26 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 27 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 28 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 29 | vision key | 2 | 0 | 4 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 30 | vision key | 1 | 0 | 2 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 31 | 无签名（人工判） | 34 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 32 | vision key | 3 | 0 | 8 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 33 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 34 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 35 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 36 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 37 | 本 key | 13 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 38 | 无签名（人工判） | 23 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 39 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 40 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 41 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 42 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 43 | 无签名（人工判） | 14 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 44 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 45 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 46 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 47 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 48 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 49 | 无签名（人工判） | 37 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 50 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 51 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 52 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 53 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 54 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 55 | 无签名（人工判） | 6 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 56 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 57 | vision key | 30 | 0 | 22 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 58 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 59 | vision key | 6 | 0 | 4 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 60 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 61 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 62 | vision key | 1 | 0 | 2 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 63 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 64 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 65 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 66 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 67 | vision key | 1 | 0 | 2 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 68 | 本 key | 15 | 4 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 69 | 本 key | 4 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 70 | 本 key | 2 | 5 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 71 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 72 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 73 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 74 | 无签名（人工判） | 7 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 75 | 本 key | 2 | 2 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 76 | 本 key | 2 | 2 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 77 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 78 | 本 key | 29 | 6 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 79 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 80 | 无签名（人工判） | 10 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 81 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 82 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 83 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 84 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 85 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 86 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 87 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 88 | 无签名（人工判） | 14 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 89 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 90 | 无签名（人工判） | 41 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 91 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 92 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 93 | 本 key | 10 | 5 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 94 | 本 key | 24 | 4 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 95 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 96 | 本 key | 11 | 7 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 97 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 98 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 99 | 本 key | 11 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 100 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 101 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 102 | 本 key | 17 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 103 | 无签名（人工判） | 25 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 104 | 无签名（人工判） | 8 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 105 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 106 | 无签名（人工判） | 6 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 107 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 108 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 109 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 110 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 111 | 无签名（人工判） | 6 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 112 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 113 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 114 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 115 | 无签名（人工判） | 19 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 116 | 无签名（人工判） | 82 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 117 | 无签名（人工判） | 113 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 118 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 119 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 120 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 121 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 122 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 123 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 124 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 125 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 126 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 127 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 128 | vision key | 2 | 0 | 2 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 129 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 130 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 131 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 132 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 133 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 134 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 135 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 136 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 137 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 138 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 139 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 140 | 本 key | 3 | 1 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 141 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 142 | 无签名（人工判） | 5 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 143 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 144 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 145 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 146 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 147 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 148 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw.py` | 3 | 无签名（人工判） | 3 | 0 | 0 |
| `packages/multi-workers/mw.py` | 4 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/mw.py` | 5 | 本 key | 224 | 3 | 0 |
| `packages/multi-workers/mw.py` | 6 | 无签名（人工判） | 9 | 0 | 0 |
| `packages/multi-workers/mw_common.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw_common.py` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/mw_common.py` | 3 | 本 key | 8 | 3 | 0 |
| `packages/multi-workers/mw_common.py` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw_common.py` | 5 | 本 key | 2 | 1 | 0 |
| `packages/multi-workers/mw_common.py` | 6 | 本 key | 6 | 1 | 0 |
| `packages/multi-workers/mw_common.py` | 7 | 本 key | 66 | 35 | 0 |
| `packages/multi-workers/mw_common.py` | 8 | 本 key | 354 | 27 | 0 |
| `packages/multi-workers/mw_common.py` | 9 | 本 key | 62 | 6 | 0 |
| `packages/multi-workers/mw_common.py` | 10 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/mw_common.py` | 11 | 无签名（人工判） | 12 | 0 | 0 |
| `packages/multi-workers/test/fixtures/autopilot-config-corpus.json` | 1 | 本 key | 13 | 2 | 0 |
| `packages/multi-workers/test/fixtures/autopilot-config-corpus.json` | 2 | 本 key | 11 | 2 | 0 |
| `packages/multi-workers/test_autopilot_config.py` | 1 | 本 key | 7 | 4 | 0 |
| `packages/multi-workers/test_autopilot_config.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config.py` | 3 | 本 key | 4 | 2 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 5 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 6 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/test_autopilot_config_parity.py` | 7 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_dispatch.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_e2e.py` | 1 | 本 key | 1 | 2 | 0 |
| `packages/multi-workers/test_autopilot_e2e.py` | 2 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 1 | 本 key | 2 | 2 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 2 | 本 key | 1 | 3 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 3 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 4 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 5 | 本 key | 2 | 2 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 6 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 7 | 本 key | 1 | 1 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 8 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_autopilot_effective_config.py` | 9 | 本 key | 12 | 5 | 0 |
| `packages/multi-workers/test_autopilot_gates.py` | 1 | 本 key | 10 | 4 | 0 |
| `packages/multi-workers/test_autopilot_timeline.py` | 1 | 本 key | 1 | 2 | 0 |
| `packages/multi-workers/test_autopilot_timeline.py` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/test_common.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_common.py` | 2 | 无签名（人工判） | 2 | 0 | 0 |
| `packages/multi-workers/test_common.py` | 3 | **混合（人工判）** | 121 | 1 | 16 |
| `packages/multi-workers/test_mw_autopilot_cli.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_mw_autopilot_cli.py` | 2 | 本 key | 2 | 2 | 0 |
| `packages/multi-workers/test_rag_research.py` | 1 | 无签名（人工判） | 1 | 0 | 0 |
| `packages/multi-workers/test_rag_research.py` | 2 | 无签名（人工判） | 0 | 0 | 0 |
| `packages/multi-workers/test_rag_research.py` | 3 | **混合（人工判）** | 11 | 1 | 4 |
| `packages/multi-workers/test_rag_research.py` | 4 | 无签名（人工判） | 4 | 0 | 0 |
| `packages/multi-workers/test_rag_research.py` | 5 | 本 key | 1 | 1 | 0 |

## 重叠文件（同一文件内两类改动都有）

- `.agenticdoc/_index.parallel`: **混合（人工判）**, 无签名（人工判）
- `.agenticdoc/mw-autopilot-slot-capacity/plan.md`: 无签名（人工判）, 本 key
- `.agenticdoc/mw-autopilot-slot-capacity/tasks/T-07-auto-decision-core.md`: 无签名（人工判）, 本 key
- `.agenticdoc/mw-vision-role/handover.md`: vision key, 无签名（人工判）
- `packages/coding-agent/dist/core/tools/bash.js`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js`: vision key, 无签名（人工判）
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts`: vision key, 无签名（人工判）
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js`: vision key, 无签名（人工判）
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js`: vision key, 无签名（人工判）, 本 key
- `packages/coding-agent/src/core/tools/bash.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`: 无签名（人工判）, 本 key
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`: 无签名（人工判）, 本 key
- `packages/multi-workers/UPDATE.md`: 无签名（人工判）, 本 key
- `packages/multi-workers/autopilot/conductor.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/autopilot/config.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/autopilot/dispatch.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/autopilot/gates.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/autopilot/timeline.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/dist/extensions/agent-team-loop.js`: vision key, 无签名（人工判）, 本 key
- `packages/multi-workers/mw.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/mw_common.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_autopilot_config.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_autopilot_e2e.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_autopilot_effective_config.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_autopilot_timeline.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_common.py`: **混合（人工判）**, 无签名（人工判）
- `packages/multi-workers/test_mw_autopilot_cli.py`: 无签名（人工判）, 本 key
- `packages/multi-workers/test_rag_research.py`: **混合（人工判）**, 无签名（人工判）, 本 key
