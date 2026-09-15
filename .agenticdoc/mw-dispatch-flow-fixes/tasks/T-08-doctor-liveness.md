# Task T-08: mw doctor worker_liveness 节

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-004]
- vc_refs: [VC-006]
- pattern_refs: []

## 描述
`packages/multi-workers/mw_common.py` + `mw.py`（design D-004）：
1. `mw_common.py` 新增 `worker_liveness(project_dir, stale_after_sec=90) -> list[dict]`：读 `_workers.parallel` status=running 行 → 各 task 目录 trace.log 最后一条 `[HEARTBEAT]` → verdict：age ≤ stale_after → `alive`；> → `stale`；无 [HEARTBEAT] 行 → `no-heartbeat`（旧 bundle 兼容）。输出 `{task_key, last_heartbeat, age_s, verdict}`
2. `doctor_report` 集成：新增 `worker_liveness` 节（信息性——不影响 healthy/issues 退出码语义，kill 属 GC-4 看门狗）；`mw.py cmd_doctor` 增加 `--stale-after <sec>` 参数透传（默认 90）
3. pytest（packages/multi-workers/test_serve_doctor.py 或 test_common.py）：
   - running 行 + 新鲜 heartbeat（ts=now-10s）→ alive
   - ts=now-300s → stale（默认 90）
   - 无 heartbeat 行 → no-heartbeat
   - `--stale-after 60` 覆盖：ts=now-100s → stale（默认 90 下为 alive 的边界翻转）
   - doctor_report JSON 含该节且退出码不变
4. 阈值与 TS 侧 `HEARTBEAT_STALE_MS = 90_000` 同步（默认值双处一致，注释互指）

## 输入
- 依赖文件: mw_common.py（doctor_report）、mw.py（cmd_doctor）、test_serve_doctor.py
- 依赖 Task: T-04（[HEARTBEAT] 行格式）
- AC 约束:
  > AC-004: 提供从结构化日志计算活性判定的机制：最后一条条目距今超过阈值（默认 90s，可配置）时输出 stale 判定，未超时输出 alive

## 预期产出
- worker_liveness 节 + --stale-after + pytest 用例
- 验证方式: `python -m pytest test_serve_doctor.py -q`（packages/multi-workers 下）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:26 | mw_common： _last_heartbeat + worker_liveness（alive/stale/no-heartbeat，fromisoformat 容错）+ doctor_report 集成（信息性，不动 healthy/issues）+ format_doctor_text workers 行；mw.py --stale-after 透传；pytest 4 新用例（三判定/阈值覆盖/信息性退出码/CLI 透传） | PASS: 11/11（含既有 7 例回归） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
