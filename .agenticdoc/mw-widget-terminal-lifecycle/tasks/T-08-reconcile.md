# Task T-08: launcher reconcile（孤儿 running 行收敛）

## 基本信息
- Stage: 4
- 代码状态: 已完成（wtl-t08-reconcile，待 PM 验收）
- 验证状态: 验证通过（VC-009 starter 半：test_launcher.py 5 用例 + 埋点；T-09 全量回归复验 365 passed）
- 负责 Agent: wtl-t08-reconcile
- ac_refs: [AC-012, AC-013]
- vc_refs: [VC-012, VC-013]
- pattern_refs: []

## 描述
`packages/multi-workers/launcher.py`：

1. **`_reconcile_orphans(project_dir, running_procs) -> None`**（每 poll 调用，D-006/D-007/D-008）：
   - 遍历 `_parse_workers_file` 中 status==running 且 task_key ∉ running_procs 的行（own 行绝不触碰）
   - `task_dir = pathlib.Path(entry["task_path"]).parent`；`end_exit = mw_common.parse_end_exit(task_dir)`
   - **正证据**（无条件执行，不受 beat 约束）：
     - end_exit is not None → status 映射 0→done、2→needs-clarification、其他→failed；reason = `reconcile: [END] exit=<c> (orphaned row)`
     - elif `(task_dir / "output.md").exists()` → failed；reason = `reconcile: completed without END marker, status unverifiable — read output.md`
   - **静默规则**（无终态证据时）：
     - `last = max(task_dir_last_activity(task_dir), parse(entry["updated_at"]))`（UTC；解析失败回退 dispatched_at；再失败跳过该行）
     - `now - last >= orphan_dead_after(env)` 分钟：
       - `mw_common.other_live_launcher(project_dir, os.getpid())` 为 True → 跳过（stderr 记一行）
       - 否则 → failed；reason = `reconcile: presumed dead (no activity for <X>m)`
     - 窗口内 → 保持 running
   - 状态更新走 `_update_status`（持锁）；reason 行追加 worker.log：`[launcher] reconcile (<iso_now>): <reason>`（与 spawn failed 同族）
2. **_poll_once 接入**：顺序 = archive_stale → reap → discover/spawn 之前调 `_reconcile_orphans`；每 poll 先 `mw_common.launcher_beat_write(project_dir, os.getpid())`
3. 时间戳全部 UTC 解析（updated_at 兼容 `+00:00` 与 `Z` 两种后缀）

**测试**（test_launcher.py 追加）：
- 正证据三映射：伪造 task_dir（task.md + trace.log 写 `[END] ... exit=0/1/2`）→ 一次 `_reconcile_orphans` 调用后行变 done/failed/needs-clarification + worker.log 含 reconcile 行（VC-012）
- output.md-only（无 [END]）→ failed + reason 含 unverifiable
- own 行：running_procs 含该 key → 不动
- 静默：无证据 + `os.utime` 把目录文件 mtime 与行 updated_at 设为 95m 前 → failed + presumed；设为 5m 前 → 保持 running；env `PI_WORKER_ORPHAN_DEAD_MIN=1` 覆盖生效（VC-013）
- beat 退让：伪造他 pid 新鲜 beat + monkeypatch `_is_alive→True` → 静默跳过、正证据仍执行
- 输出 `[VERIFY] VC-012: map=0-done,1-failed,2-nc, own_row=untouched`、`[VERIFY] VC-013: silence_failed=1, fresh_untouched=1, beat_guard=skipped` 埋点行

## 输入
- 依赖文件: `launcher.py`（_poll_once/_update_status/_record_spawn_failure 模式）、`mw_common.py`（T-02 五函数）
- 依赖 Task: T-02
- AC 约束:
  > AC-012: 在 `_workers.parallel` 存在状态为 running 且不属于当前 launcher 进程管理（running_procs 之外）的行、其任务目录 trace.log 含 `[END]` 标记时，launcher 在 ≤1 个 poll 周期（默认 5s）内将该行更新为 `[END]` exit 码对应终态（0→done、2→needs-clarification、其他→failed）并在 worker.log 追加 reconcile 原因行；仅 output.md 存在而无 `[END]`（旧 bundle）时更新为 failed 且原因注明状态不可验证；当前 launcher 自己 spawn 的行不受 reconcile 影响
  > AC-013: 在上述孤儿行无终态证据（无 output.md 且无 `[END]`）、且任务目录全部文件 mtime 与该行 updated_at 均早于当前时间 ≥90 分钟（默认值，环境变量可调）时，launcher 将该行更新为 failed 并在 worker.log 追加 `[launcher] reconcile` 原因行；任一活动证据新鲜于该窗口（如心跳）时行保持 running；检测到另一存活 launcher 的新鲜心跳标记时跳过本规则（正证据规则不受此限制）
- 设计约束:
  > D-006: reconcile 只在 launcher，走 _update_status 单写者
  > D-007: 正证据无条件每 poll；静默 90m（env 可调）
  > D-008: beat 退让只约束静默规则
  > spec §5 坑点: UTC 时间戳口径（`+00:00` 与 `Z` 双兼容）

## 预期产出
- `packages/multi-workers/launcher.py`（_reconcile_orphans + _poll_once 接入 + beat 刷新）
- `packages/multi-workers/test_launcher.py`（追加用例 + 埋点）
- 验证方式: `python -m pytest test_launcher.py -q` 全绿；全量 `python -m pytest -q` 零回归 + 埋点
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 07:48Z | wtl-t08 launcher.py 实现 `_reconcile_orphans`（正证据 [END]→0→done/2→needs-clarification/其他→failed、output.md-only→failed unverifiable，均无条件；静默规则 last=max(task_dir_last_activity, updated_at)，Z/+00:00 双兼容、dispatched_at 回退、双失败跳行，≥ orphan_dead_after 分钟 presumed dead，beat 退让仅约束静默）+ `_record_reconcile` worker.log 行 + `_poll_once` 接入（beat 刷新 → archive_stale → reap → reconcile → discover/spawn） | 完成；状态更新走 `_update_status` 持锁，own 行（task_key ∈ running_procs）绝不触碰；reason 行 `[launcher] reconcile (<iso_now>): <reason>` 与 spawn failed 同族 |
| 2 | 2026-09-10 07:48Z | wtl-t08 追加 test_launcher.py 17 用例：[END] 0/1/2/3 四映射、output.md-only、own 行不动、静默 95m→failed/5m→running/PI_WORKER_ORPHAN_DEAD_MIN=1 覆盖、Z 后缀解析、updated_at→dispatched_at 回退、双垃圾时间戳跳行、新鲜目录 mtime 压过旧 updated_at、beat 退让（静默跳过+正证据仍执行+stderr 记录）、_poll_once 集成（beat 文件存在+reconcile/spawn 顺序） | `python -m pytest test_launcher.py -q` 69 passed；埋点 `[VERIFY] VC-012: map=0-done,1-failed,2-nc, own_row=untouched`、`[VERIFY] VC-013: silence_failed=1, fresh_untouched=1, beat_guard=skipped` |
| 3 | 2026-09-10 07:48Z | wtl-t08 全量回归 `python -m pytest -q`（不含 e2e_real/e2e_l2） | 358 passed, 6 deselected，零回归；仅改 launcher.py + test_launcher.py，未碰 mw_common.py/mw.py/TS 侧/_starter_prompt |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
