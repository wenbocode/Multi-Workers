# IN-3 受损产品清单（tracked 改动，按风险分级）

- 生成时间：2026-10-10 11:45（本地）　来源：`git status --porcelain` + `git diff --numstat` + mtime
- 分级口径：**L1 = 产品即判定**（quality-gate / verify / reviews / achieved）；**L2 = research 证据**（可为修订稿，需比对 anchor）；**L3 = 任务卡/其它**
- 本清单**不主张**这些改动全部由事故产生：其中混有各 key 合法的在写工作；判定方法见 `02-impact-assessment.md`

## L1（18 份）

| 路径 | 窗口内 mtime | diff |
|---|---|---|
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md` | 10-10 11:07:31 | 133	129	.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-10-qg.md |
| `.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-11-qg.md` | 10-09 20:11:44 | 116	107	.agenticdoc/goal-autopilot/evidence/quality-gate-report-2026-09-11-qg.md |
| `.agenticdoc/mw-crosskey-risk-escalation/evidence/verify-independent-2026-09-23.md` | 10-10 11:15:55 | 181	196	.agenticdoc/mw-crosskey-risk-escalation/evidence/verify-independent-2026-09-23.md |
| `.agenticdoc/mw-partition-parent-extended/evidence/quality-gate-report-2026-09-20-worker.md` | 10-10 11:33:51 | 72	58	.agenticdoc/mw-partition-parent-extended/evidence/quality-gate-report-2026-09-20-worker.md |
| `.agenticdoc/mw-rag-config-guide/evidence/verify-run-2026-09-22.md` | 10-10 11:33:41 | 192	180	.agenticdoc/mw-rag-config-guide/evidence/verify-run-2026-09-22.md |
| `.agenticdoc/mw-rag-integration/evidence/quality-gate-review-2026-09-22.md` | 10-10 11:13:41 | 165	170	.agenticdoc/mw-rag-integration/evidence/quality-gate-review-2026-09-22.md |
| `.agenticdoc/mw-rag-integration-fix/evidence/verify-run-2026-09-22.md` | 10-10 11:38:25 | 171	159	.agenticdoc/mw-rag-integration-fix/evidence/verify-run-2026-09-22.md |
| `.agenticdoc/mw-rag-window-parity/evidence/quality-gate-report-2026-09-23.md` | 10-10 11:24:13 | 187	146	.agenticdoc/mw-rag-window-parity/evidence/quality-gate-report-2026-09-23.md |
| `.agenticdoc/mw-rag-window-parity/evidence/verify-run-2026-09-23.md` | 10-10 11:38:12 | 124	151	.agenticdoc/mw-rag-window-parity/evidence/verify-run-2026-09-23.md |
| `.agenticdoc/mw-rag-window-parity/evidence/verify-run-delta-2026-09-23.md` | 10-10 11:36:23 | 79	67	.agenticdoc/mw-rag-window-parity/evidence/verify-run-delta-2026-09-23.md |
| `.agenticdoc/mw-target-partition/evidence/verify-run-2026-09-19.md` | 10-09 20:44:08 | 129	99	.agenticdoc/mw-target-partition/evidence/verify-run-2026-09-19.md |
| `.agenticdoc/mw-vision-role/achieved.md` | 10-09 15:01:56 | 21	0	.agenticdoc/mw-vision-role/achieved.md |
| `.agenticdoc/mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md` | 10-09 15:01:56 | 5	3	.agenticdoc/mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md |
| `.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md` | 10-10 11:33:16 | 239	219	.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md` | 10-10 11:36:19 | 1707	0	.agenticdoc/mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md |
| `.agenticdoc/mw-worker-progress-persist/evidence/verify-independent-2026-09-23.md` | 10-10 11:23:47 | 244	236	.agenticdoc/mw-worker-progress-persist/evidence/verify-independent-2026-09-23.md |
| `.agenticdoc/mw-worker-progress-persist/evidence/verify-run-2026-09-23.md` | 10-10 11:11:37 | 146	142	.agenticdoc/mw-worker-progress-persist/evidence/verify-run-2026-09-23.md |
| `.agenticdoc/mw-worker-visibility-gate/evidence/verify-independent-2026-09-23.md` | 10-10 11:24:37 | 267	114	.agenticdoc/mw-worker-visibility-gate/evidence/verify-independent-2026-09-23.md |

## L2（48 份）

| 路径 | 窗口内 mtime | diff |
|---|---|---|
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-gate-schema-presentation-20260926.md` | 10-10 10:55:20 | 82	0	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-gate-schema-presentation-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-auto-gate-boundary-20260926.md` | 10-10 11:12:53 | 103	1	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-auto-gate-boundary-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-auto-gate-guardrails-20260926.md` | 10-10 11:12:58 | 219	208	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-auto-gate-guardrails-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-capacity-constraints-20260926.md` | 10-10 11:15:05 | 271	140	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-capacity-constraints-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-cap-breach-attribution-20260926.md` | 10-10 11:13:37 | 156	32	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-cap-breach-attribution-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-concurrency-anchors-20260926.md` | 10-10 11:13:30 | 446	0	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-concurrency-anchors-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-gate-review-material-20260926.md` | 10-10 11:14:45 | 66	14	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-gate-review-material-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-gate-selfverifiable-20260926.md` | 10-10 11:20:53 | 55	0	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-gate-selfverifiable-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-panel-semantics-divergence-20260926.md` | 10-10 10:57:59 | 138	0	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-panel-semantics-divergence-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-slot-utilization-20260926.md` | 10-10 11:14:58 | 334	203	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-slot-utilization-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-stalled-slot-release-20260926.md` | 10-10 11:07:55 | 137	217	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-stalled-slot-release-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-unattended-stage-closure-20260926.md` | 10-10 11:04:16 | 105	1	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-unattended-stage-closure-20260926.md |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md` | 10-10 11:16:33 | 239	206	.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-cache-pickup-20260926.md` | 10-10 11:20:38 | 313	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-cache-pickup-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-crosslang-consistency-20260926.md` | 10-10 11:13:58 | 277	235	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-crosslang-consistency-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-cwd-root-anchor-20260926.md` | 10-10 11:05:00 | 88	0	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-cwd-root-anchor-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-dist-anchor-guard-20260926.md` | 10-10 11:16:55 | 138	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-dist-anchor-guard-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-machine-layer-20260926.md` | 10-10 10:55:49 | 72	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-machine-layer-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-write-lock-20260926.md` | 10-10 11:05:30 | 109	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-write-lock-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-cli-patterns-20260926.md` | 10-10 11:10:38 | 413	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-cli-patterns-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-config-write-contract-20260926.md` | 10-10 11:16:52 | 231	1	.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-config-write-contract-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-dist-rebuild-20260926.md` | 10-10 11:03:39 | 192	171	.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-dist-rebuild-20260926.md |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-verify-cmd-portability-20260926.md` | 10-10 11:03:02 | 243	254	.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-verify-cmd-portability-20260926.md |
| `.agenticdoc/mw-done-closure-repair/evidence/research/design-marker-mechanics-20260925.md` | 10-10 11:13:24 | 110	99	.agenticdoc/mw-done-closure-repair/evidence/research/design-marker-mechanics-20260925.md |
| `.agenticdoc/mw-done-closure-repair/evidence/research/design-reprompt-loop-20260925.md` | 10-10 11:18:13 | 93	64	.agenticdoc/mw-done-closure-repair/evidence/research/design-reprompt-loop-20260925.md |
| `.agenticdoc/mw-done-closure-repair/evidence/research/design-return-path-20260925.md` | 10-10 11:11:33 | 117	73	.agenticdoc/mw-done-closure-repair/evidence/research/design-return-path-20260925.md |
| `.agenticdoc/mw-implementation-gate/evidence/research/w1-pi-extension-interception.md` | 10-10 11:12:04 | 113	59	.agenticdoc/mw-implementation-gate/evidence/research/w1-pi-extension-interception.md |
| `.agenticdoc/mw-implementation-gate/evidence/research/w2-p002-guard-precedent.md` | 10-10 11:09:59 | 61	48	.agenticdoc/mw-implementation-gate/evidence/research/w2-p002-guard-precedent.md |
| `.agenticdoc/mw-l3-fail-marker-forms/evidence/research/design-corpus-negative-20260925.md` | 10-10 11:08:25 | 165	0	.agenticdoc/mw-l3-fail-marker-forms/evidence/research/design-corpus-negative-20260925.md |
| `.agenticdoc/mw-l3-fail-marker-forms/evidence/research/design-corpus-positive-20260925.md` | 10-10 11:04:55 | 250	0	.agenticdoc/mw-l3-fail-marker-forms/evidence/research/design-corpus-positive-20260925.md |
| `.agenticdoc/mw-vision-role/evidence/research/design-doctor-show-output-contract-20260926.md` | 10-10 11:23:20 | 52	62	.agenticdoc/mw-vision-role/evidence/research/design-doctor-show-output-contract-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/design-images-header-writer-python-20260926.md` | 10-10 11:15:56 | 61	59	.agenticdoc/mw-vision-role/evidence/research/design-images-header-writer-python-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/design-python-probe-contract-20260926.md` | 10-10 11:08:32 | 64	77	.agenticdoc/mw-vision-role/evidence/research/design-python-probe-contract-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/design-ts-gate-autoroute-interface-20260926.md` | 10-09 20:20:01 | 81	87	.agenticdoc/mw-vision-role/evidence/research/design-ts-gate-autoroute-interface-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/design-verification-feasibility-20260926.md` | 10-10 11:09:50 | 91	80	.agenticdoc/mw-vision-role/evidence/research/design-verification-feasibility-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/spec-capability-gate-hooks-20260926.md` | 10-10 11:03:36 | 63	59	.agenticdoc/mw-vision-role/evidence/research/spec-capability-gate-hooks-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/spec-framework-awareness-surface-20260926.md` | 10-10 11:17:32 | 43	4	.agenticdoc/mw-vision-role/evidence/research/spec-framework-awareness-surface-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/spec-images-header-contract-20260926.md` | 10-09 20:18:23 | 74	77	.agenticdoc/mw-vision-role/evidence/research/spec-images-header-contract-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/spec-role-type-plumbing-20260926.md` | 10-10 11:13:33 | 61	77	.agenticdoc/mw-vision-role/evidence/research/spec-role-type-plumbing-20260926.md |
| `.agenticdoc/mw-vision-role/evidence/research/spec-vision-io-and-candidates-20260926.md` | 10-10 11:10:02 | 54	55	.agenticdoc/mw-vision-role/evidence/research/spec-vision-io-and-candidates-20260926.md |
| `.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-collection-parity-2026-09-23.md` | 10-10 11:14:57 | 109	95	.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-collection-parity-2026-09-23.md |
| `.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-test-harness-2026-09-23.md` | 10-10 11:15:52 | 182	128	.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-test-harness-2026-09-23.md |
| `.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-tool-contract-2026-09-23.md` | 10-10 11:09:03 | 103	100	.agenticdoc/mw-worker-progress-persist/evidence/research/design-verify-tool-contract-2026-09-23.md |
| `.agenticdoc/xkey-repair-mechanism/evidence/research/design-boundary-apply-20260926.md` | 10-10 11:17:36 | 181	0	.agenticdoc/xkey-repair-mechanism/evidence/research/design-boundary-apply-20260926.md |
| `.agenticdoc/xkey-repair-mechanism/evidence/research/design-human-only-answer-20260926.md` | 10-10 11:11:06 | 54	0	.agenticdoc/xkey-repair-mechanism/evidence/research/design-human-only-answer-20260926.md |
| `.agenticdoc/xkey-repair-mechanism/evidence/research/design-ledger-ticket-shapes-20260926.md` | 10-10 11:14:55 | 110	0	.agenticdoc/xkey-repair-mechanism/evidence/research/design-ledger-ticket-shapes-20260926.md |
| `.agenticdoc/xkey-repair-mechanism/evidence/research/spec-code-facts-20260926.md` | 10-10 11:22:51 | 155	134	.agenticdoc/xkey-repair-mechanism/evidence/research/spec-code-facts-20260926.md |
| `.agenticdoc/xkey-repair-mechanism/evidence/research/spec-incident-corpus-20260926.md` | 10-10 11:15:00 | 174	51	.agenticdoc/xkey-repair-mechanism/evidence/research/spec-incident-corpus-20260926.md |

## L3（16 份）

| 路径 | 窗口内 mtime | diff |
|---|---|---|
| `.agenticdoc/_index.parallel` | 10-10 10:53:10 | 5	2	.agenticdoc/_index.parallel |
| `.agenticdoc/autopilot-monitor/evidence/runs/t02-verification.md` | 10-10 10:57:28 | 254	0	.agenticdoc/autopilot-monitor/evidence/runs/t02-verification.md |
| `.agenticdoc/goal-autopilot/tasks/T-03-roadmap-check.md` | 10-10 10:58:58 | 2	0	.agenticdoc/goal-autopilot/tasks/T-03-roadmap-check.md |
| `.agenticdoc/goal-autopilot/tasks/T-04-timeline.md` | 10-10 10:52:47 | 2	0	.agenticdoc/goal-autopilot/tasks/T-04-timeline.md |
| `.agenticdoc/goal-autopilot/tasks/T-05-gates.md` | 10-10 10:53:15 | 2	0	.agenticdoc/goal-autopilot/tasks/T-05-gates.md |
| `.agenticdoc/goal-autopilot/tasks/T-08-audit-evidence.md` | 10-10 10:52:04 | 36	0	.agenticdoc/goal-autopilot/tasks/T-08-audit-evidence.md |
| `.agenticdoc/goal-autopilot/tasks/T-13-worker-read-scope.md` | 10-10 10:58:58 | 4	0	.agenticdoc/goal-autopilot/tasks/T-13-worker-read-scope.md |
| `.agenticdoc/goal-autopilot/tasks/T-15-autopilot-console.md` | 10-10 11:12:35 | 4	1	.agenticdoc/goal-autopilot/tasks/T-15-autopilot-console.md |
| `.agenticdoc/mw-target-partition/evidence/e2e-spawn-2026-09-19.md` | 10-10 11:10:57 | 266	0	.agenticdoc/mw-target-partition/evidence/e2e-spawn-2026-09-19.md |
| `.agenticdoc/mw-vision-role/handover.md` | 10-09 15:01:56 | 20	1	.agenticdoc/mw-vision-role/handover.md |
| `.agenticdoc/mw-vision-role/pm-state.md` | 10-09 14:53:00 | 1	0	.agenticdoc/mw-vision-role/pm-state.md |
| `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md` | 10-10 11:03:54 | 2	0	.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md |
| `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-02-mw-common-evidence.md` | 10-10 11:33:42 | 2	0	.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-02-mw-common-evidence.md |
| `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-03-tldr-normalization.md` | 10-10 11:07:14 | 2	0	.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-03-tldr-normalization.md |
| `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-04-starter-conclusion.md` | 10-10 11:28:24 | 2	0	.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-04-starter-conclusion.md |
| `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-08-reconcile.md` | 10-10 11:28:17 | 4	0	.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-08-reconcile.md |

