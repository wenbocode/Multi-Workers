# execute 波提交清单（机器生成，供 git add 使用）

- 源码/测试: **48** · 文档: **23** · dist 产物: **34**
- 排除: 19

## 第 1 个提交（源码 + 测试 + 本 key 文档）

    .agenticdoc/_pitfalls.md
    .agenticdoc/mw-autopilot-slot-capacity/achieved.md
    .agenticdoc/mw-autopilot-slot-capacity/evidence-requirement.md
    .agenticdoc/mw-autopilot-slot-capacity/evidence/baseline/
    .agenticdoc/mw-autopilot-slot-capacity/evidence/execute-wave-commit-attribution.md
    .agenticdoc/mw-autopilot-slot-capacity/evidence/quality-gate-report-20260926-194528.md
    .agenticdoc/mw-autopilot-slot-capacity/evidence/runs/
    .agenticdoc/mw-autopilot-slot-capacity/plan.md
    .agenticdoc/mw-autopilot-slot-capacity/pm-state.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-07-auto-decision-core.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-08-pending-review.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-11-parity-corpus.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-15-count-locks.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-16-attribution-delegation.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-17-ts-count-locks.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-18-gate-default-bypass.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-19-case2-producer.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-20-reason-code-scope.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-21-defer-ledger.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-22-evidence-line-audit.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-23-status-parity-lock.md
    .agenticdoc/mw-autopilot-slot-capacity/tasks/T-24-crosskey-prose.md
    packages/coding-agent/CHANGELOG.md
    packages/coding-agent/src/core/tools/bash.ts
    packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts
    packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts
    packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts
    packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts
    packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts
    packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts
    packages/coding-agent/test/extensions/agent-team-loop.test.ts
    packages/coding-agent/test/suite/autopilot-config-parity.test.ts
    packages/coding-agent/test/suite/autopilot-config-sync.test.ts
    packages/coding-agent/test/suite/autopilot-console.test.ts
    packages/coding-agent/test/suite/autopilot-event-parity.test.ts
    packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts
    packages/coding-agent/test/suite/autopilot-monitor.test.ts
    packages/coding-agent/test/suite/autopilot-status-parity.test.ts
    packages/coding-agent/test/suite/worker-idle-heartbeat.test.ts
    packages/coding-agent/test/suite/worker-store.test.ts
    packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts
    packages/multi-workers/CHANGELOG.md
    packages/multi-workers/UPDATE.md
    packages/multi-workers/autopilot/conductor.py
    packages/multi-workers/autopilot/config.py
    packages/multi-workers/autopilot/dispatch.py
    packages/multi-workers/autopilot/evidence.py
    packages/multi-workers/autopilot/gates.py
    packages/multi-workers/autopilot/roadmap.py
    packages/multi-workers/autopilot/timeline.py
    packages/multi-workers/mw.py
    packages/multi-workers/mw_common.py
    packages/multi-workers/test/fixtures/autopilot-config-corpus.json
    packages/multi-workers/test_autopilot_attribution.py
    packages/multi-workers/test_autopilot_auto_decision.py
    packages/multi-workers/test_autopilot_config.py
    packages/multi-workers/test_autopilot_config_parity.py
    packages/multi-workers/test_autopilot_crosskey_prose.py
    packages/multi-workers/test_autopilot_dispatch.py
    packages/multi-workers/test_autopilot_e2e.py
    packages/multi-workers/test_autopilot_effective_config.py
    packages/multi-workers/test_autopilot_evidence.py
    packages/multi-workers/test_autopilot_gate_consumption.py
    packages/multi-workers/test_autopilot_gate_guards.py
    packages/multi-workers/test_autopilot_gate_schema_v2.py
    packages/multi-workers/test_autopilot_gates.py
    packages/multi-workers/test_autopilot_pending_review.py
    packages/multi-workers/test_autopilot_timeline.py
    packages/multi-workers/test_doctor_gates.py
    packages/multi-workers/test_mw_autopilot_cli.py
    packages/multi-workers/test_rag_research.py

## 第 2 个提交（dist 产物，单独提交 —— 沿用前一个 key 的惯例）

    packages/coding-agent/dist/core/tools/bash.d.ts.map
    packages/coding-agent/dist/core/tools/bash.js
    packages/coding-agent/dist/core/tools/bash.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/console.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/monitor.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js
    packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/shared/mw-runner.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js
    packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js
    packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js.map
    packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts
    packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.d.ts.map
    packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js
    packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js.map
    packages/multi-workers/dist/extensions/agent-team-loop.js

## 排除清单（不进本 key 提交）

- `.agenticdoc/_index.parallel` —— 固定排除（他 key 残留/噪声/共享状态）
- `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` —— 非 packages 且非本 key 文档
- `.agenticdoc/mw-vision-role/achieved.md` —— 固定排除（他 key 残留/噪声/共享状态）
- `.agenticdoc/mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md` —— 固定排除（他 key 残留/噪声/共享状态）
- `.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md` —— 固定排除（他 key 残留/噪声/共享状态）
- `.agenticdoc/mw-vision-role/handover.md` —— 固定排除（他 key 残留/噪声/共享状态）
- `.agenticdoc/mw-vision-role/pm-state.md` —— 固定排除（他 key 残留/噪声/共享状态）
- `.tmp/` —— 固定排除（他 key 残留/噪声/共享状态）
- `hello-world.txt` —— 固定排除（他 key 残留/噪声/共享状态）
- `packages/coding-agent/Python/` —— 固定排除（他 key 残留/噪声/共享状态）
- `packages/coding-agent/dist/extensions/agent-team-loop/pm/pm-orchestrator.js` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.d.ts.map` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js.map` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.d.ts.map` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js` —— 含 vision 特征且无本 key 特征
- `packages/coding-agent/dist/extensions/agent-team-loop/shared/dispatch-models.js.map` —— 含 vision 特征且无本 key 特征
- `packages/multi-workers/test_common.py` —— 固定排除（他 key 残留/噪声/共享状态）
