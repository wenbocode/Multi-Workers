# PM State: mw-autopilot-advance-root

## 1. Snapshot
- Key: mw-autopilot-advance-root
- Phase: DONE
- Next Action: —
- Started: 2026-09-22 16:30
- Updated: 2026-09-22 16:38
- Completed: 2026-09-22 16:38

## 2. Task Status
- T1 framework root 定位统一: done（advance_phase/update_index/migrate_patterns/verify_project_memory）
- T2 detect_root PROJECT_ROOT cwd 优先: done（CLI prefer_cwd_project）
- T3 mirror 同步 + 上游 push + 副本同步: done（d7004d0 pushed；E2Feature + mw 同步；diff-installed clean）
- T4 mw 候选一致性校验 + `-X utf8`: done
- T5 pi 扩展 `-X utf8`: done
- T6 e2e hermetic + 回归收尾: done

## 3. Evidence Ledger
- 2026-09-22 16:29 **PASS** 根因链实测（`evidence/research/spec-root-cause-2026-09-22.md`）：detect_root PROJECT_ROOT 错报 mw 仓库；find_root 命中 mw `.agenticdoc`；三副本 sha256 同源；子进程 stdio=gbk。
- 2026-09-22 16:44 **PASS** framework 脚本测试：test_detect_root 8 OK（含 3 新用例）、test_advance_phase/update_index/migrate_patterns/audit_phase/install/sync_framework 全 exit 0。
- 2026-09-22 16:44 **PASS** `npm run check` exit 0（0 error / 0 warning / 0 info）；`evidence/check-output.txt`。
- 2026-09-22 16:35 **PASS** vitest agent-team-loop 168 passed。
- 2026-09-22 16:36 **PASS** mw pytest 726 passed / 9 deselected。
- 2026-09-22 16:40 **PASS** e2e `test_autopilot_advance_e2e.py`：项目外 framework 下 advance spec→design exit 0，framework 仓库无新 key 目录。
- 2026-09-22 16:45 **PASS** 同步核验：framework HEAD d7004d0 pushed；E2Feature marker/droid/.claude 三副本 hash 9427ABE2…；diff-installed.py clean。

## 4. Hypothesis Queue
- H1（已证）: advance exit=1 主因是 root 错位，不是门禁条件不满足。
- H2（已证）: 一致性校验不会误拒合规项目——平台锚定仍指向项目的项目内副本也通过；实跑 E2Feature 采纳最新 marker clone。

## 5. Decisions
- 2026-09-22 主修 framework cwd 优先 + mw 候选一致性校验 + `-X utf8`；不重排候选优先级。理由与实测定案见 design.md / `evidence/research/design-framework-sync-2026-09-22.md`。
- 2026-09-22 detect_root 的 cwd 优先只放在 CLI 出口（`prefer_cwd_project`），library `detect_project_root` 语义不变——避免破坏既有 platform-anchored 单测（先例：`test_detect_root.py`）。
- 2026-09-22 发布顺序：framework 先发 + E2Feature 同步，再上 mw fail-loud（已执行）。
- 2026-09-22 用户批准跨仓修改 AgenticTask 并授权动手。

## 6. Turn End Records
*(empty)*

## 7. Process Log
- 2026-09-22 建 key → SPEC→DESIGN→PLAN→TASKS→EXECUTE 均经 `advance_phase` 门禁；T1..T6 由 PM 本窗口直接实施（精确 cross-repo 改动，不宜派 worker）。

