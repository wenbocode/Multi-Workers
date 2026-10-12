"""Align the T-02/T-05 config-key counts with T-18's early landing (17 -> 20)."""

from __future__ import annotations

import pathlib

BASE = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")

EDITS: list[tuple[str, str, str]] = [
    (
        "plan.md",
        "| `packages/multi-workers/autopilot/config.py` | T-02 | `DEFAULT_CONFIG`（14→17）+ `_INT_RANGES`（3 键） |",
        "| `packages/multi-workers/autopilot/config.py` | T-02 | `DEFAULT_CONFIG`（17→20；T-18 三键已把 14→17 提前落地）+ `_INT_RANGES`（3 键） |",
    ),
    (
        "plan.md",
        "- 配置键：`DEFAULT_CONFIG` **14 → 17**（`l3_abort_retry_limit` 0..10 默认 1；`gate_reminder_after_min` 1..1440 默认 30；`gate_reminder_max` **1..2** 默认 2），`_INT_RANGES` 三键齐备；**不进** `EFFECTIVE_KEYS`；`status-model.ts` 镜像同步。",
        "- 配置键：`DEFAULT_CONFIG` **17 → 20**（`l3_abort_retry_limit` 0..10 默认 1；`gate_reminder_after_min` 1..1440 默认 30；`gate_reminder_max` **1..2** 默认 2；T-18 的 G5/G6 三键已把基线从 14 推到 17，见 §2.5），`_INT_RANGES` 三键齐备；**不进** `EFFECTIVE_KEYS`；`status-model.ts` 镜像同步。",
    ),
    (
        "plan.md",
        "| T-02 | 三个配置键注册 | 0 | AC-003, AC-005 | VC-019 | `DEFAULT_CONFIG` 14→17 + `_INT_RANGES`（含 `gate_reminder_max` 封 1..2） |",
        "| T-02 | 三个配置键注册 | 0 | AC-003, AC-005 | VC-019 | `DEFAULT_CONFIG` 17→20（T-18 三键已占 14→17）+ `_INT_RANGES`（含 `gate_reminder_max` 封 1..2） |",
    ),
    (
        "tasks/T-02-config-keys.md",
        "- `DEFAULT_CONFIG` 14 → **17** 键；`_INT_RANGES` 三键齐备（`(0,10)` / `(1,1440)` / `(1,2)`）。",
        "- `DEFAULT_CONFIG` **17 → 20** 键（T-18 的 `launcher_max_workers` / `dispatch_max_per_scan` / `queue_alarm_delta` 已把 14 → 17 提前落地；本卡只追加这三个 G1/G2 键，不得改动 T-18 三键的默认值与值域）；`_INT_RANGES` 三键齐备（`(0,10)` / `(1,1440)` / `(1,2)`）。",
    ),
    (
        "tasks/T-05-ts-mirror.md",
        "3. **配置镜像**：`DEFAULT_CONFIG` 镜像 14 → 17 键，取值与值域逐项同 `T-02`（含 `gate_reminder_max` 的 1..2）。",
        "3. **配置镜像**：`DEFAULT_CONFIG` 镜像 **17 → 20** 键（T-18 三键 14→17 已落地；本卡另加 T-02 的三键），取值与值域逐项同 `T-02`（含 `gate_reminder_max` 的 1..2）。",
    ),
]

for rel, old, new in EDITS:
    p = BASE / rel
    t = p.read_text(encoding="utf-8")
    if t.count(old) != 1:
        raise SystemExit(f"{rel}: anchor count {t.count(old)} for {old[:60]}")
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", rel, "->", new[:70])
