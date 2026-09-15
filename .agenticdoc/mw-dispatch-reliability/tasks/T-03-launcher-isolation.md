# Task T-03: launcher _spawn 隔离降级（移除 FATAL 连坐）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-001]
- vc_refs: [VC-001, VC-002]
- pattern_refs: []

## 描述
改造 `launcher.py::_spawn`（design D-001）：
1. `_build_env` / `_build_command` 抛出的缺凭证 RuntimeError 不再升级为 `_FatalLauncherError`——删除该升级分支（`_FatalLauncherError` 类与 `run()` 的 re-raise 一并移除）
2. per-task 失败路径：标 status=failed（`_update_status`），并把原因写入该任务 `worker.log`（追加一行 `[launcher] spawn failed (<ISO>): <msg>`，含缺失 env var 名；CLI 未运行，日志原本为空，必须由 launcher 主动落盘以满足可观测性）
3. 其它 RuntimeError（bad provider、task.md not found）同样走 per-task failed + worker.log 落盘
4. `test_launcher.py` 更新：`TestSpawnFatalError::test_missing_timi_key_raises_fatal_launcher_error` 改写为隔离语义断言（status=failed + worker.log 含 TIMI_API_KEY + 不抛异常）

注意：task.md not found 的 pending 条目实际会先被 T-04 的 stale 扫描归档；spawn 期兜底保留。

## 输入
- 依赖文件: launcher.py（_spawn / _update_status / _FatalLauncherError）
- 依赖 Task: 无（可与 T-01/T-02 并行）
- AC 约束:
  > AC-001: 在队列含 1 个缺 ANTHROPIC_AUTH_TOKEN 的 pending claude 任务与 1 个凭证可用的 pending pi/timi 任务的条件下，launcher 处理后，claude 任务状态为 failed 且其 worker 侧产物注明缺失的 env var 名，pi/timi 任务状态进入 running 或 done，且 launcher 与 mw serve 进程持续存活 ≥ 60s

## 预期产出
- launcher.py 改造
- test_launcher.py 用例更新
- 验证方式: VC-001/VC-002（单元级；集成级在 T-12，现场版在 T-15）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 18:11 | 实现并通过单测（见下） | PASS: 相关 pytest 用例全绿 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
