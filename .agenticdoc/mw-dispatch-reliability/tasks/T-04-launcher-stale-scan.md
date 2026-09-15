# Task T-04: launcher poll 内 stale 扫描归档

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-004]
- vc_refs: [VC-005]
- pattern_refs: []

## 描述
在 `launcher.py::run()` 主循环接入归档（design D-004）：
- 每轮 poll 先 `mw_common.archive_stale_entries(project_dir)`（在读取 entries 之前，保证后续 spawn 不会撞到死条目；归档自身持锁）
- 与 `_update_status` 使用同一锁路径 `.mw/workers.lock`，锁协议不变（O_CREAT|O_EXCL + 指数退避）
- 单测：pending/running 条目 task.md 缺失 → 调用后 ≤1 轮归档；正常条目不受影响；归档后同轮循环内不重复处理该 key

## 输入
- 依赖文件: launcher.py（run 主循环）、mw_common.py（T-02 archive_stale_entries）
- 依赖 Task: T-02
- AC 约束:
  > AC-004: 在 `_workers.parallel` 存在 task.md 已不存在的 pending 条目的条件下，mw serve 运行中该条目在 ≤ 10s 内从队列移入归档文件（`.agenticdoc/_workers.stale.parallel`），归档行含原行内容 + 归档时间 + 原因

## 预期产出
- launcher.py 主循环改造
- test_launcher.py 用例
- 验证方式: VC-005（单元级轮询验证；集成级 ≤10s 断言在 T-12）
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
