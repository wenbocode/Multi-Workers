# Task T-15: 现场实战修复 + 全量回归

## 基本信息
- Stage: 6
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-001, AC-009, AC-013, AC-015]（现场版汇总）
- vc_refs: [VC-010, VC-014, VC-016]
- pattern_refs: []

## 描述
本仓库现场（`H:/git/Multi-Workers`）修复 2026-08-28 诊断出的崩溃循环并全量回归：
1. **诊断留档**：`python mw.py doctor --project=.` 输出存 `evidence/runs/doctor-before.txt`（当前应报：mw not running + stale 条目 review-s1-verification + 凭证缺失路由 + bundle 过期）
2. **归档 stale**：验证 T-04 自动归档（起 mw 后 ≤10s `review-s1-verification` 移入 `_workers.stale.parallel`）或 doctor --fix
3. **重建 bundle**：`/mw build`（或 `python mw.py build --install`）使 8/25 的 pm-orchestrator/ui-bridge 源码改动生效；doctor 复验 bundle 节转绿
4. **崩溃循环消除验证（AC-001 现场版）**：mw start → 存活 ≥60s（PID 稳定）→ 派发一个真实 pi/timi 小任务（"Say exactly: ok"）→ done + output.md；期间队列如再混入缺凭证任务（可人为造一个 claude pending 行验证隔离）不影响服务存活
5. **全量回归**：`python -m pytest test_launcher.py test_common.py test_integration.py`（全绿）+ `python -m pytest test_e2e_real.py -m e2e_real`（真实链路）+ 根仓 `./test.sh`（vitest 含新 agent-team-loop.test.ts）+ `npm run check`（TS 改动过 biome/tsgo 门禁）
6. **证据落盘**：`evidence/runs/l2-summary.md`（doctor-before/after、调度时序、全量回归输出摘要）

## 输入
- 依赖文件: 全部 Stage 1-5 产出
- 依赖 Task: T-01 ~ T-14
- AC 约束:（AC-001/009/013/015 原文见 spec.md §3；本 task 为现场版验证 + 汇总）

## 预期产出
- 现场修复完成（mw 稳定运行、stale 归档、bundle 最新）
- `evidence/runs/doctor-before.txt`、`evidence/runs/l2-summary.md`
- 全量回归绿
- 验证方式: VC-010/VC-014/VC-016 + 现场证据
- 验证等级: Level 2

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
