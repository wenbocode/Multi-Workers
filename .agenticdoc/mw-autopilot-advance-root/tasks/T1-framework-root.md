# T1: framework root 定位统一（cwd 专扫优先）

> Key: mw-autopilot-advance-root | AC-001 | 依赖：无

## 目标

`advance_phase.py` / `update_index.py` / `migrate_patterns.py` / `verify_project_memory.py` 四处在 framework 位于项目外、cwd=项目根时解析到项目自身 `.agenticdoc`；framework repo 自身即项目时仍正确。

## 改动

- 每文件内实现最小 `find_root()`：
  1. cwd 向上专扫 `.agenticdoc`（只认这一个 marker，不被 `.git` 截停）；
  2. 回退 `Path(__file__)` 向上专扫（保留现行为）。
- 无跨文件 import（脚本可能被单独拷贝）。
- `verify_project_memory.py` 的 `ROOT` 改为同一语义（返回 `.agenticdoc` 的父目录）。

## 证据

- framework `scripts/` 自带 pytest 全绿。
- 手工：framework 外 cwd=临时项目 → 返回临时项目 `.agenticdoc`；cwd=framework repo（mw）→ 返回 mw `.agenticdoc`。
