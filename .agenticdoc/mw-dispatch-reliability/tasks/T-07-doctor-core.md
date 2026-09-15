# Task T-07: doctor 核心 + mw.py doctor 子命令

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-006, AC-008]
- vc_refs: [VC-007, VC-009]
- pattern_refs: []

## 描述
1. `mw_common.py` 增 `doctor_report(project_dir, config=None) -> dict`，≥7 诊断节（全本地检查，无网络）：
   - `service`：mw.pid 存在性 + 进程存活（复用 mw.py `_check_pid` 逻辑，迁 mw_common）
   - `proxy`：7001/7003(/7004) 端口监听状态（`_port_is_bound` 迁入）
   - `orphan_proxy`：端口被占但 mw 未运行 → 报告 PID（netstat 解析）
   - `launcher_log`：launcher.log 尾部 10 行 + FATAL/error 行计数
   - `queue`：_workers.parallel 非终态任务列表 + 每条 task.md 存在性 + stale 计数（_workers.stale.parallel 行数）
   - `credentials`：route_precheck 结果（注明"以 mw 进程 env 为准"）
   - `bundle`：全局 bundle（`~/.pi/agent/extensions/agent-team-loop.js`）mtime vs 源码目录（mw.py 同仓 `packages/coding-agent/src/extensions/agent-team-loop`）最新 mtime；源码不存在则标注不可比
   - `summary`：整体 healthy/issues + 建议动作
2. `doctor_fix(project_dir) -> dict`：可自动修复项执行——归档 stale（archive_stale_entries）、清除陈旧 mw.pid（PID 文件存在但进程死）；不可修复项（bundle 过期、孤儿 proxy）仅输出建议
3. `mw.py` 增 `cmd_doctor`：`--project` 必填，`--json` 输出 JSON，`--fix` 先 fix 后 report；healthy 退出 0 / issues 退出 1
4. 输出所有值经 `_mask_env_value` 类规则（无明文凭证）
5. pytest：结构断言（≥7 节、每节非空）、fix 行为、退出码、执行耗时 <5s

## 输入
- 依赖文件: mw.py、mw_common.py（T-01/T-02 全部函数）
- 依赖 Task: T-01, T-02
- AC 约束:
  > AC-006: 在任意项目目录运行 `python mw.py doctor --project=<dir>` 的条件下，命令在 5s 内完成并输出 ≥ 7 项诊断，每项 1 行结论，健康时退出码 0、异常时退出码 1
  > AC-008: 在 doctor 以修复模式运行的条件下，可自动修复项被执行并输出修复清单，不可自动修复项仅输出建议不动手

## 预期产出
- mw_common.py 增 doctor_report / doctor_fix
- mw.py 增 cmd_doctor + argparse 注册
- test 用例
- 验证方式: VC-007/VC-009
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
