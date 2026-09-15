# Task T-13: smoke_test.sh T5 假阳性修复

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-014]
- vc_refs: [VC-015]
- pattern_refs: []

## 描述
修复 `packages/multi-workers/smoke_test.sh` T5（任务检测）：
1. 删除 else 分支的 `_pass "AC-001: launcher poll interval verified (task detection may need pi binary)"` 假阳性路径——未检测到时必须 `_fail` 且最终脚本退出码 1
2. 检测等待从 7s 提到 15s（poll-interval 5s + spawn 余量；脚本启动参数同步 `--poll-interval` 可考虑传 1 加速）
3. 核对 smoke 手写的 `_workers.parallel` 行与新 schema/launcher 解析兼容（7/8 列容忍逻辑不变则无需改）
4. 验证：静态断言（脚本不含"检测不到仍 PASS"的 else 分支）+ 手动构造检测失败场景跑一次确认 exit 1

## 输入
- 依赖文件: smoke_test.sh
- 依赖 Task: 无
- AC 约束:
  > AC-014: smoke_test.sh 的任务检测断言在任务未被检测到时判 FAIL（删除现有 else 假阳性分支），修复后脚本在该失败场景下退出码为 1

## 预期产出
- smoke_test.sh 修复
- 验证方式: VC-015（静态断言 + 失败场景实跑）
- 验证等级: Level 0

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
