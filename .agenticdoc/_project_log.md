# Project Log — FeatureMigrator

> 追加型 / 不可变时间线。由 advance_phase.py done 追加。

| Completed | Commit | Key | 核心问题 | Supersedes |
|-----------|--------|-----|---------|------------|
| 2026-09-09 16:59 | 6273b27f9 | mw-worker-timeout-convergence | Worker watchdog redo: activity idle detection + per-task budget + convergence checkpoint with PM escalation + deadline steer; 87/87 tests, live smoke x2, quality gate PASS | — |
| 2026-09-09 23:53 | 357296d89 | mw-dispatch-flow-fixes | — | — |
| 2026-09-10 19:27 | fceae6eaf | mw-widget-terminal-lifecycle | Widget 三区渲染 + ack 通道/sidecar + 终态 detail 取源 + TL;DR 双保险 + 孤儿行 reconcile；TS 121/121 + Python 365 + bundle 冒烟 + 38/38 质检（review S1~S3 已修复） | — |
| 2026-09-10 19:32 | 5e8ecf39d | goal-autopilot | T-18 wrap-up: QG PASS (72/72), 18/18 tasks done | — |
| 2026-09-11 00:19 | 04bc69616 | ai-baseline-repair | AI baseline drift repair: tsgo 26->0 + check green + ai suite 838 passed (root fix = upstream generator mirror block); attribution B=58/A'=26/A=0 with user decisions recorded; prevention docs in README+AGENTS.md; QG 38/38 PASS | — |
| 2026-09-11 17:19 | 5fa74a900 | autopilot-monitor | — | — |
| 2026-09-17 17:00 | 477d8ace4 | mw-dual-workspace | 质检 PASS（用户确认接受 4 项 ⚠️ 欠债）；quality-gate-report-2026-09-11.md + achieved.md 落盘；check 0/0/0、回归基线 new-failures=0、audit_phase PASS | — |
