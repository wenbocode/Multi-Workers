# T-01-e2feature-site-repair

状态: done · 覆盖: AC-001 · 依赖: -

## 目标

现场止损，让 E2Feature autopilot 从 2h35m 的无界重试里脱出：修正 `feature-params-service/pm-state.md` 的 Phase 行（接口漂移），并修正 `.mw/dispatch.yml` 的 reviewer 模型 id 笔误（L3 worker 启动即 403 的根因）。

## 输入

- `H:\git\E2Feature\.agenticdoc\feature-params-service\pm-state.md`（第 5 行含括注的 Phase 值）
- `H:\git\E2Feature\.mw\dispatch.yml`（`review: timi/gpt-5.6.sol`）

## 步骤

1. `repair_phase_line.py`：bytes 级读入，正则定位 `^- Phase:`，取阶段 token 的大写形式（`EXECUTE`），其余字节（含 CRLF）保持原样写回。
2. `fix_review_model_id.py`：bytes 级替换 `timi/gpt-5.6.sol` → `timi/gpt-5.6-sol`，断言仅该 token 变化。
3. 观察 timeline：`execute->verify exit=0`，随后 L3 派发。

## 验证

- `pm-state.md` 行变更：14396 B → 14334 B，`rest unchanged: True`。
- `dispatch.yml`：145 B → 145 B，`only this token changed: True`。
- timeline `2026-09-22T13:35:41+00:00 seq 21475 ev=advance detail="execute->verify exit=0"`（此前 2242 次 exit=1）。

## 执行记录

- 2026-09-22 21:35:32 本地：`repair_phase_line.py` 执行，输出如上验证块。
- 2026-09-22 23:44 本地：`fix_review_model_id.py` 执行，输出如上验证块。
- 脚本：`workers/t1-e2feature-unblock/{repair_phase_line,fix_review_model_id}.py`。
- 后续阻塞（L3 预算耗尽 + stalled approve 无实现）由 T-04/T-09 走正式路径解决。
