# T4: mw 候选一致性校验 + -X utf8

> Key: mw-autopilot-advance-root | AC-003, AC-004, AC-006 | 依赖：T3

## 目标

`packages/multi-workers/autopilot/advance.py`：

1. `locate_platform_dir()` 逐候选跑 `detect_root.py --json`，只采用 `PROJECT_ROOT == project_root`（resolve 归一）的候选；全部不符 → `AdvanceError`（列出每个候选的实测 PROJECT_ROOT）。
2. detect_root 调用与 `advance()` 脚本调用 argv 加 `-X utf8`。

## 约束

- 保持 `AdvanceError` → `advance()` 返回 `(1, "", "[advance] ...")` 的既有契约。
- 不重排候选（D-105），顺序只决定命中哪个合格候选。

## 证据

- `test_autopilot_conductor.py` 新增：相符候选被选 / 全不符 raise / argv 含 `-X utf8`。
- 实跑 E2Feature：`locate_platform_dir` 返回 marker clone 且 PROJECT_ROOT 一致。
