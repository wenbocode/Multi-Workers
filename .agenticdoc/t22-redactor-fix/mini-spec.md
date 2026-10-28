# Mini-spec（快速路径记录）: T22 生产写链路修复

> 说明：本轮占用 implementation-gate 的 mini-spec 快速路径，因为 claim 检查在此仓库失效：
> `.agenticdoc/_index.parallel` 没有表头行（第 1 行是 `# Index Parallel`，第 2 行就是数据），
> 而 `implementation-gate.parseIndexRows()` 要求表头含 `key`/`status`/`claimid` 列，
> 解析失败即"无 claim"，所以 `switch_key` 写下的 `status=active` 行永远不会被识别。
> 正式规格见同目录 `spec.md`。

## 范围（用户已确认 A+B+C，并追加界面要求 D）

A. `packages/multi-workers/mw.py::_decide_lifecycle_store` 改用
   `decision.credential_redactor()`；返回 `None` 时抛 `LifecycleInputError` 明确拒绝。

B. `packages/multi-workers/decision_wire.py`：`_sanitize_metadata_key` 的尾部清理加
   4 字符下限（`METADATA_KEY_MIN_SCRUB`），保住 `observed_at`/`completed` 等 schema 字段名。

C. `packages/multi-workers/test_decision_task_state.py`：4 条回归（生产过滤器契约、
   真实写出六字段快照、键的短尾巴不清理、`_scratch` 显式拒绝）。

D. `decision_dashboard.js` / `decision_dashboard.css`：`task_before`/`task_after`
   结构化展示（状态徽标 + 来源/时间 + 已完成/待处理/阻塞分项列表）。

## 验收

- 新增回归修复前 RED、修复后 GREEN；`test_decision_task_state_ui.py` 全绿。
- `mw decide run` 带 `task_before` 的 envelope：exit 0，账本出现六字段完整的 record-start。
- 既有基线失败（coverage_safety 6 + known_set_snapshot 4）不新增。
