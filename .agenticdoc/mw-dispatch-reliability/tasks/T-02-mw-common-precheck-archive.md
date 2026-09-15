# Task T-02: mw_common.py 路由预检 + stale 归档

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-002, AC-003, AC-004]
- vc_refs: [VC-003, VC-004, VC-005]
- pattern_refs: []

## 描述
在 `mw_common.py` 增两个无副作用核心函数：
1. `route_precheck(config, env) -> list[RouteStatus]`：每路由一条 `{route, cli, available, source, missing}`；available = resolve_credential 成功（source 记 env 名或 file 路径）；附 `all_missing` 汇总判定
2. `archive_stale_entries(project_dir) -> list[str]`：读 `_workers.parallel`，taskPath 不存在的条目持锁（`.mw/workers.lock`，O_CREAT|O_EXCL，与 launcher._update_status 同一路径与协议）移出队列，追加到 `.agenticdoc/_workers.stale.parallel`，归档行 = 原行 + ` | <archived_at ISO> | task.md not found`；追加式不清空；无 stale 时不动文件（幂等）；pending 与 running 状态的缺失条目均归档

test_common.py 覆盖：预检各路由组合（全缺/部分/全有）、归档（单条/多条/幂等/无 stale 不改文件/锁竞争下安全）。

## 输入
- 依赖文件: mw_common.py（T-01 的 load/resolve）
- 依赖 Task: T-01
- AC 约束:
  > AC-002: 在所有已配置路由凭证均缺失的条件下，mw serve 启动在 10s 内以非零退出码退出，mw.log 列出每个路由缺失的凭证来源清单
  > AC-003: 在至少一条路由凭证可用的条件下，mw serve 启动后 mw.log 记录全部路由的预检结果，每路由 1 行 available/missing 标记
  > AC-004: 在 `_workers.parallel` 存在 task.md 已不存在的 pending 条目的条件下，mw serve 运行中该条目在 ≤ 10s 内从队列移入归档文件

## 预期产出
- `mw_common.py` 增 route_precheck / archive_stale_entries
- `test_common.py` 增对应用例
- 验证方式: VC-003/VC-004（数据级）、VC-005（单元级；集成级在 T-12）
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
