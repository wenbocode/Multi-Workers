# T-03-advance-stall-freeze

状态: done · 覆盖: AC-003, AC-005 · 依赖: T-02

## 目标

非瞬时 advance 失败有界化：同一 (key, edge) 连续失败达 `advance_stall_ticks` → `mark_stalled`（四件套），key 随即被既有 skip 规则冻结。

## 步骤

1. `conductor.py` 新增 `_advance_retry_allowed(project_root, key, edge, cfg) -> bool`（或等价内联）：
   - `count, hist, last_err = _advance_failure_streak(...)`；
   - `count + 1 >= threshold` → `mark_stalled(project_root, st, key, reason)`，其中 reason 单行：`advance {edge} 连续 {n} 次失败（class={主分类} {分布}）: {最近错误摘要}`；
   - 返回 False（本 tick 不再调用 advance）。
2. 接入三个 advance 调用点：`execute_loop` 的 `execute->verify`、`_advance_key` 的 L1 直推、`_done_transaction` 的 `verify->done` 高级路径（后者仅在 `code != 0` 的既有分支内判定）。
3. 未达阈值：行为与现状完全一致（照旧重试并记事件）。

## 验证

- 行为单测（复用 `test_autopilot_conductor_exec.py` 的 `_key_project` / `_fake_advance_factory`）：
  - 阈值 2 且连续 2 次 advance 失败 → key-status 变 `stalled`、生成 `stalled` 门禁、`achieved.md` 出现遗留草稿、`patterns/<key>/stall-lesson.md` 存在；
  - 冻结后同一 key 不再追加 `advance` 事件（比对该 key 的事件序列）；
  - 阈值未达（第 1 次失败）→ 无门禁、无 stalled；
  - 失败之间插入一次成功 advance → 计数清零。

## 执行记录

- 2026-09-22 23:55 完成，与 T-02 同一批次落地（`_record_advance_result` 内含升级）。
- 行为：同一 (key, edge) 连续失败达 `advance_stall_ticks` → `mark_stalled`（四件套）；`mark_stalled` 幂等；升级后 key 被 `orchestrate` skip 规则冻结，不再调用 `advance_phase.py`。
- 证据（`test_repeated_advance_failure_stalls_instead_of_spinning`）：阈值 3 时前两次仍 `running`，第三次 → key-status `stalled` + `achieved.md` 含「## 遗留问题」+ `patterns/k1/stall-lesson.md` + `stalled` 门禁（question 含 `interface-drift` 与「连续 3 次失败」，单行）；随后 4 个 tick 的 `advance` 事件数不增（冻结）；全部失败事件带 `class=interface-drift`。
