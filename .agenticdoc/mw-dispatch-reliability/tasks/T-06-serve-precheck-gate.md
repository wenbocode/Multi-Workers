# Task T-06: mw serve 预检门禁 + PID 时序

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-002, AC-003]
- vc_refs: [VC-003, VC-004]
- pattern_refs: []

## 描述
改造 `mw.py::cmd_serve`（design D-002）：
1. PID 文件写入移到预检通过之后（当前是进函数即写）——"PID 存在 ≈ 服务存活"成立，是 AC-005 稳定窗语义的前提
2. 预检：`mw_common.route_precheck(config, os.environ)`（providers 来自 --providers 或默认）
   - 全缺：每路由缺失清单逐行写 mw.log（`[mw serve] route unavailable: <route> missing <来源清单>`）+ stderr 摘要，清理 stop request，return 1（不写 PID，不 spawn 任何子进程）
   - 部分缺：逐路由 available/missing 行写 mw.log 后正常继续
3. `cmd_start`（后台 start）透传预检失败：mw serve 退出码 1 即整体失败（现有 detach 模式下由 mw.log 承载证据；不额外改 start 逻辑）
4. 测试（pytest）：monkeypatch env 全清 → cmd_serve 返回 1 + PID 文件不存在 + mw.log 含各路由行；部分可用 → 返回正常路径（子进程 mock）+ mw.log 逐路由行

## 输入
- 依赖文件: mw.py（cmd_serve）、mw_common.py（T-02 route_precheck）
- 依赖 Task: T-02
- AC 约束:
  > AC-002: 在所有已配置路由凭证均缺失的条件下，mw serve 启动在 10s 内以非零退出码退出，mw.log 列出每个路由缺失的凭证来源清单
  > AC-003: 在至少一条路由凭证可用的条件下，mw serve 启动后 mw.log 记录全部路由的预检结果，每路由 1 行 available/missing 标记

## 预期产出
- mw.py cmd_serve 改造
- test 用例（可入 test_common.py 或新 test_serve.py）
- 验证方式: VC-003/VC-004
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
