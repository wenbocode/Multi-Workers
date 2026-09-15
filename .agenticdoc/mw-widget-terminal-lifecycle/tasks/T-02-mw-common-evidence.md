# Task T-02: mw_common 终态证据与 beat 协议

## 基本信息
- Stage: 1
- 代码状态: 已完成（wtl-t02-mw-common，待 PM 验收）
- 验证状态: 验证通过（VC-012/013 证据层：test_common.py 26 用例全绿 + 埋点；T-09 全量回归复验 365 passed）
- 负责 Agent: wtl-t02-mw-common
- ac_refs: [AC-012, AC-013]
- vc_refs: [VC-012, VC-013]
- pattern_refs: []

## 描述
`packages/multi-workers/mw_common.py` 新增纯函数（无 I/O 副作用除读文件；全部 UTC 口径）：

1. **`parse_end_exit(task_dir: pathlib.Path) -> int | None`**：读 `task_dir/trace.log` 尾部（最后 64KB，文件可不存在→None），匹配 `^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$`（镜像 TS heartbeat.ts END_LINE_RE），返回 exit int；无 [END] 行→None
2. **`launcher_beat_write(project_dir: pathlib.Path, pid: int) -> None`**：写 `.mw/launcher-beat.<pid>`（内容单行 `ts=<iso>`；每 poll 覆写，无锁小文件）
3. **`other_live_launcher(project_dir: pathlib.Path, self_pid: int) -> bool`**：glob `.mw/launcher-beat.*`；跳过自身 pid 的文件；其余文件 ts 新鲜（<30s）且 pid 存活（复用 `_is_alive`）→ True；文件缺失/过期/全死→False
4. **`orphan_dead_after(env: Mapping[str, str] | None = None) -> int`**：env `PI_WORKER_ORPHAN_DEAD_MIN`（分钟，int，≥1），默认 90
5. **`task_dir_last_activity(task_dir: pathlib.Path) -> float | None`**：任务目录全部文件 mtime 最大值；目录/文件缺失→None

**测试**（`packages/multi-workers/test_common.py` 追加 describe；不碰 test_launcher.py）：
- parse_end_exit：正常行→0/1/2；无 [END]/缺文件→None；[END] 在 64KB 尾窗内可被尾部读取命中
- beat：写后 other_live_launcher(self_pid) False（自身跳过）；伪造他 pid + 新鲜 ts + monkeypatch `_is_alive→True` → True；ts 过期 → False
- orphan_dead_after：默认 90；env 覆盖；非法值（0/负/非数字）→ 90
- task_dir_last_activity：多文件取 max；空/缺目录 → None
- 输出 `[VERIFY] VC-012: parse_end_exit=<0|1|2|None>`、`[VERIFY] VC-013: beat_guard=<bool>, window=<min>` 埋点行

## 输入
- 依赖文件: `mw_common.py`（`_is_alive`、`iso_now`）
- 依赖 Task: 无
- AC 约束:
  > AC-012: …其任务目录 trace.log 含 `[END]` 标记时，launcher 在 ≤1 个 poll 周期（默认 5s）内将该行更新为 `[END]` exit 码对应终态（0→done、2→needs-clarification、其他→failed）…（本 Task 提供 parse_end_exit 证据解析半；映射与接入在 T-08）
  > AC-013: …且任务目录全部文件 mtime 与该行 updated_at 均早于当前时间 ≥90 分钟（默认值，环境变量可调）…检测到另一存活 launcher 的新鲜心跳标记时跳过本规则…（本 Task 提供 window/beat/活动探测半）
- 设计约束:
  > D-007: ORPHAN_DEAD_AFTER 默认 90 分钟，env PI_WORKER_ORPHAN_DEAD_MIN 可调
  > D-008: beat 协议（30s 新鲜阈，静默规则退让用）
  > spec §2.1: 时间戳统一 UTC

## 预期产出
- `packages/multi-workers/mw_common.py`（新增 5 个函数）
- `packages/multi-workers/test_common.py`（追加测试）
- 验证方式: `python -m pytest test_common.py -q`（packages/multi-workers 下）全绿 + 埋点行；全量 `python -m pytest -q` 零回归
- 验证等级: Level 1

## 约束（worker 派发适用）
- 只碰 mw_common.py + test_common.py；禁改 launcher.py / mw.py（T-04/T-08 在飞或后续）
- 显式路径参数；[VERIFY] 埋点
- 完成后更新本文件执行记录

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 07:27Z | wtl-t02 实现 mw_common.py 5 函数（parse_end_exit / launcher_beat_write / other_live_launcher / orphan_dead_after / task_dir_last_activity，+131 行，置于 worker_liveness 后） | 完成；END 行镜像 TS END_LINE_RE 且 64KB 尾读，beat 单行 ts=<iso> 覆写，window 默认 90 分钟非法回退，mtime 取目录文件 max |
| 2 | 2026-09-10 07:27Z | wtl-t02 追加 test_common.py 4 个 describe（26 用例：END 0/1/2/None/畸形/尾窗内命中/窗外不读、beat 自身跳过/他 pid 新鲜+存活/过期/死 pid/畸形、window 默认/覆盖/非法、mtime max/子目录忽略/空/缺） | `python -m pytest test_common.py -q` 61 passed；埋点 [VERIFY] VC-012: parse_end_exit=0/1/2/None、[VERIFY] VC-013: beat_guard=True, window=90 |
| 3 | 2026-09-10 07:27Z | wtl-t02 全量回归 `python -m pytest -q`（不含 e2e_real） | 341 passed, 1 deselected；中途一次 test_integration Windows 共享冲突 PermissionError 复跑即过（launcher 写 _workers.parallel 与测试读并发，与本 Task 无关，隔离重跑 pass，末次全量绿） |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
