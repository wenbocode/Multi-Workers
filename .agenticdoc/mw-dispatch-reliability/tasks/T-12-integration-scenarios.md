# Task T-12: L1 集成测试——隔离/预检/归档/doctor/配置扩展场景

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-006, AC-008, AC-017]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-007, VC-009, VC-018]
- pattern_refs: []

## 描述
基于 T-11 框架补齐调度可靠性核心场景（每个用例独立 tmp project）：
1. **VC-001/002 混合队列隔离**：pending claude 任务（预检 env 未设）+ pending pi/timi 任务（凭证注入可用）→ claude 行 status=failed 且其 worker.log 含缺失 env var 名；pi/timi 任务 done；launcher 进程全程存活（用例结束时仍运行）
2. **VC-003 全缺 fail fast**：env 全清起 mw serve（子进程或直接调 cmd_serve 于 tmp project）→ 退出非零 + mw.log 含每路由缺失清单 + PID 文件不存在
3. **VC-004 部分缺预检**：只设 timi → mw.log 逐路由 available/missing 行数 = 路由数
4. **VC-005 stale 归档**：pending 条目 task.md 删除后起 launcher → ≤10s 行从 `_workers.parallel` 消失、出现于 `_workers.stale.parallel`（含 archived_at + reason）
5. **VC-007/009 doctor**：`mw.py doctor --project=<tmp> --json` → ≥7 节、healthy/issues 退出码、耗时 <5s；`--fix`（预置 stale 条目 + 陈旧 PID 文件）→ 修复清单含归档与 PID 清理，bundle/orphan 仅建议
6. **VC-018 配置零代码扩展**：tmp providers.json 增 dummy 路由（env 源 TEST_DUMMY_KEY）→ route_precheck/doctor 输出含该路由；launcher.py/mw.py/mw_common.py 无代码改动（git diff 断言为空）

## 输入
- 依赖文件: launcher.py / mw.py / mw_common.py（Stage 1-3 全部就绪）
- 依赖 Task: T-06, T-07, T-11
- AC 约束:（AC-001~004/006/008/017 原文见 spec.md §3）

## 预期产出
- test_integration.py 增 6 组用例
- 验证方式: VC-001~005, VC-007, VC-009, VC-018
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 20:10 | 执行完成（详见 evidence/runs/l2-summary.md） | PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
