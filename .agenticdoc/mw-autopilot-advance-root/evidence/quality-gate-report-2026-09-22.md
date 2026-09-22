# Quality Gate Report: mw-autopilot-advance-root

> 日期：2026-09-22
> 范围：spec.md AC-001..AC-008
> 证据：`evidence/runs/validation-2026-09-22.md`、`evidence/check-output.txt`、`evidence/research/*`

## 判定：PASS（8/8 AC）

| AC | 判定 | 证据 |
|----|------|------|
| AC-001 framework 四脚本 root 定位 cwd 优先 / `__file__` 回退 | PASS | 代码：`advance_phase.find_root`、`update_index.find_root`、`migrate_patterns.find_root`、`verify_project_memory._find_agenticdoc` 均为 cwd 专扫优先；`test_advance_phase.py::FindRootCwdFirstTest` 实跑通过；framework 自带 4 套脚本测试 exit 0 |
| AC-002 `detect_root.py` PROJECT_ROOT cwd 优先 | PASS | `detect_root.prefer_cwd_project` + `main()` 应用；实跑 cwd=E2Feature 得 `PROJECT_ROOT=H:\git\E2Feature, method=agenticdoc:cwd`；`PreferCwdProjectTests` 3/3 |
| AC-003 mw 候选一致性校验 + fail-loud | PASS | `autopilot/advance.py::locate_platform_dir` 逐候选 `_probe_detect_root`，要求 PROJECT_ROOT == project_root；实跑 E2Feature 采纳 marker clone；`test_inconsistent_marker_candidate_falls_back_to_consistent_layout` + `test_no_consistent_candidate_fails_loud` 通过（AdvanceError 含 "resolves to this project's root"） |
| AC-004 `-X utf8`（mw 两处 + pi 扩展） | PASS | `test_python_utf8_flag_passed_to_children` 断言两次子进程 argv[1:3]==["-X","utf8"]；`agent-scripts.ts` 的 spawnSync argv 已加；vitest 168/168 |
| AC-005 e2e 项目外 framework 推进且不污染其它 `.agenticdoc` | PASS | `test_autopilot_advance_e2e.py`：exit 0、`- Phase: DESIGN`、framework 仓库无新 key 目录 |
| AC-006 负路径 fail-loud 且消息可读 | PASS | `test_no_consistent_candidate_fails_loud`：`advance()` 返回 (1, "", "[advance] ...")，断言无 `?` |
| AC-007 framework push + 项目副本同步 + diff clean | PASS | framework HEAD d7004d0 已 push origin/master；`install.py` 同步 E2Feature（marker commit=d7004d0、clone HEAD=d7004d0、`.claude/scripts` 三副本同 hash 9427ABE2…）与 mw 本仓 `.claude`/marker；`diff-installed.py` 见 §残留检查 |
| AC-008 回归绿、无新增失败 | PASS | mw pytest 726 passed / 9 deselected；framework 脚本测试全 exit 0；vitest 168 passed；`npm run check` exit 0 |

## 残留检查

- `diff-installed.py H:/git/Multi-Workers`：framework clone HEAD 与源一致，`.claude` 与 clone 的 `claude/` 一致（install.py 刚同步）；无本地未提交改动（clone 工作区 clean）。
- 已知遗留（不阻断）：
  1. pi 扩展 `dist` bundle 未重建（AGENTS.md 禁未请求的 build）：`agent-scripts.ts` 的 `-X utf8` 在下次正常 bundle 构建/发布后对既有窗口生效。mw 侧（关键修复）无需 bundle，无需重启即生效。
  2. 其它项目（JCodingAss / LearningTree 等）的项目内 framework 副本未同步；按 D-107 应在各自下次 `install.py`/update 时同步。未同步项目仍可 advance（其项目内副本为 platform-anchored 一致候选），不会被 fail-loud 误拒。

## 未决项

无。
