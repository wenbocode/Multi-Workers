# T2: detect_root.py PROJECT_ROOT cwd 专扫优先

> Key: mw-autopilot-advance-root | AC-002 | 依赖：无

## 目标

`detect_root.py --json` 在 framework 位于项目外、cwd=项目根时返回该 cwd 所属项目（`PROJECT_ROOT`/`AGENTICDOC_ROOT`），`method` 反映 cwd 专扫。

## 改动

- `detect_project_root(platform_dir)`：把「cwd 向上专扫 `.agenticdoc`」提到第 1 步，`method = agenticdoc:cwd`。
- 保留后续链：platform_dir 专扫 → 本地 marker 扫描 → IDE → 通用 marker → CI → fallback。
- `detect_platform_dir()` 不动。

## 证据

- `scripts/test_detect_root.py` 新增 cwd 优先用例通过。
- 实跑：cwd=E2Feature 时 `PROJECT_ROOT` 从 `H:\git\Multi-Workers` 变为 `H:\git\E2Feature`。
