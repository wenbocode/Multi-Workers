# T3: mirror 同步 + 上游 push + 项目副本同步

> Key: mw-autopilot-advance-root | AC-007 | 依赖：T1, T2

## 目标

framework 修复进入 `scripts/` canonical 与两份 mirror，push 上游，并同步 E2Feature 的项目内副本。

## 步骤

1. `python install.py H:/git/E2Feature`（或先 `sync_script_mirrors` 单独触发）→ 刷新 `claude/scripts`、`core/scripts`，pull E2Feature clone，写 marker。
2. framework repo `git add` 改动文件 + `git commit` + `git push origin HEAD`。
3. 校验：`diff-installed.py H:/git/Multi-Workers` clean；三副本 hash 一致。

## 证据

- `git log -1` + push 输出。
- `diff-installed.py` 输出。
- hash 对比表。
