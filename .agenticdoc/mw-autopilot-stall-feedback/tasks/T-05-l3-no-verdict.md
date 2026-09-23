# T-05-l3-no-verdict

状态: done · 覆盖: AC-012 · 依赖: T-04

## 目标

区分「reviewer 真裁决 below」与「L3 worker 崩溃导致无裁决」：后者不派 repair、直接重派 L3，且停滞原因上报真实失败原因（现场 403 案例）。

## 步骤

1. `_l3_round_verdict(rows, key_dir, key, attempt) -> str`（`meets` / `below` / `no-verdict`）：
   - 该轮 row（`dispatch.task_key_for(key, f"l3-a{attempt}")`）终态失败（`failed` / `needs-clarification`）→ `no-verdict`（附状态）；
   - output.md 不存在且该轮 row 已终态 → `no-verdict`；
   - 其余沿用 `_parse_l3_output`。
2. `_verify_loop`：`no-verdict` → 不进入 repair 分支，直接派 `l3-a{used+1}`；追加 timeline `l3-no-verdict`（key / attempt / worker status / task_key）。
3. 预算耗尽时的 `mark_stalled` reason 区分：`L3 无裁决（worker {status}: {task_key}）` vs 既有 `L3 below {n} rounds`。

## 验证

- 行为单测：
  - `l3-a1` row = failed 且无 output → 下一 tick 派 `l3-a2`，且**没有** repair 派发；timeline 有 `l3-no-verdict`；
  - 崩溃轮耗尽预算 → `stalled` 门禁 reason 含 `worker failed` 与 task_key（断言字符串）；
  - 真 `below`（output 有 FAIL 行）→ 仍走 repair（既有用例不改仍绿）。

## 执行记录

- 2026-09-23 00:05 完成。
- `_l3_round_verdict(project_root, rows, key, attempt) -> (verdict, worker_status)`：output.md 存在即权威（沿用 `_parse_l3_output`）；无 output → `no-verdict` + 该轮队列表状态。
- `_verify_loop`：`no-verdict` 不派 repair，直接派下一轮 L3；记 `l3-no-verdict` 事件；预算耗尽时 reason = `L3 无裁决（worker {status}: {task_key}）达 {used}/{limit} 轮`。
- 证据：`test_l3_worker_failure_is_no_verdict`（failed 轮 → 无 repair、派 l3-a2、事件含 `status=failed`；round 2 meets 仍可正常 done）、`test_l3_no_verdict_stall_reason_names_worker`（门禁 question 含「L3 无裁决」「worker failed」「ap-k1-l3-a1」）。
- 既有 `below` 路径不受影响（原有用例全绿）。
