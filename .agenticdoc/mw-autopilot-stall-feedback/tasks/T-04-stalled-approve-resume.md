# T-04-stalled-approve-resume

状态: done · 覆盖: AC-004, AC-013 · 依赖: T-03

## 目标

实现 `stalled` 门禁问句承诺的「人工介入后重试」：approve → key-status 复位 `running` + 恢复**恰好一轮**额度；reject 保持既有 closed-legacy 语义。

## 步骤

1. `_resume_credits(project_root, key) -> int`：`gates.enumerate` 中 `kind == "stalled"` 且 `status == "approved"` 且 `key` 命中的门禁数（design D-6）。
2. `_apply_stalled_approvals(project_root, st, status_of, stage_of)`：对称于 `_apply_stalled_rejections`，在 `_consume_answered_gates` 之后调用；动作 = roadmap `stalled` → `running`（roadmap 锁内）+ timeline `gate-answered`（`"{gate.id} approved → {key} running"`，保证 `_consumed_gate_ids` 消费协议一致）+ `resume` 事件 + 就地更新 `status_of`。
3. 四个预算点加 `credits`（design D-6）：L2 `allowed`、EXECUTE `used >= budget + credits`、L3 `used >= l3_budget + credits`、repair `repair_used >= budget + credits`。
4. `timeline.EVENT_TYPES` 若 T-02 未加 `resume`，此处补齐。

## 验证

- 行为单测：
  - key 已 stalled 且门禁被人工改为 approved → 下一 tick key-status 回 `running`、roommap 行更新、timeline 有 `gate-answered` + `resume`；
  - 恢复后 L3 恰好再派一轮（`used == budget` 时 `used < budget + credits`）；该轮再失败 → 再次 `mark_stalled`；
  - 无 approved 门禁（credits = 0）→ 全部预算判定与改动前一致（逐分支断言）；
  - 重复 approve / 重复 tick 不重复复位（幂等）；
  - rejected 门禁仍走 `closed-legacy`（既有用例不改仍绿）。
- `pytest test_autopilot_conductor.py test_autopilot_conductor_exec.py test_autopilot_conductor_stage.py test_autopilot_gates.py` 全绿。

## 执行记录

- 2026-09-23 00:05 完成。
- `_resume_credits(project_root, key)`（已批准 stalled 门禁计数，零私有状态）；`_apply_stalled_approvals`（roadmap `stalled`→`running` + `gate-answered` 消费记录 + `resume` 事件，就地更新 `status_of`，幂等）；四个预算点加 credits（L2 `allowed`、EXECUTE、L3、repair）。
- 证据：`test_approved_stalled_gate_resumes_key`（复位 + resume 事件 + 本 tick 内重试 + 额度只买一个窗口：再次达阈值即再升级，生成第二个 gate）、`test_resume_credit_lifts_execute_retry_limit`、`test_resume_credit_lifts_l2_and_l3_limits`（L2 第 2 轮 verifier）、`test_resume_credit_lifts_l3_and_repair_limits`（L3 repair-a1 与 repair-a1-a2）、`test_rejected_stalled_gate_still_closes_legacy`（reject 语义不变、无 credit）。
- 全量回归：223 passed。
