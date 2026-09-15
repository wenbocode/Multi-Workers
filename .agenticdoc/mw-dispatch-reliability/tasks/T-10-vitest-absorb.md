# Task T-10: vitest 收编 test-l1-full.ts

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-015]
- vc_refs: [VC-016]
- pattern_refs: []

## 描述
1. 新建 `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（vitest），迁移 `packages/multi-workers/test-l1-full.ts` 全部断言场景，按 describe/it 组织：
   - WorkerStore 两条目 upsert/readAll（VC-038 等价）
   - `_workers.parallel` 列格式（7/8 列兼容由 Python 侧负责；TS 侧断言 WorkerStore 序列化列数）
   - StateManager 非法 phase 拒绝
   - writeOutput 四节（exit 0）+ exit 1/2/130 分支 + >50 字节
   - appendTrace `[FLOW]` / appendGoalCheck `[GOAL_CHECK]`
   - runPhases phase-1.md 产出 + goalMtime 类型
   - IndexStore 列格式
   - dispatchTask ISO 8601 时间戳
   - 增补 T-08 的 waitForMwStart 稳定窗用例（如未放此处）
2. import 路径改为仓库相对（`../../src/extensions/agent-team-loop/...`），遵守根仓 tsconfig 的 erasable-syntax 与相对导入检查（`check:ts-imports`）
3. 删除 `packages/multi-workers/test-l1-full.ts`
4. `./test.sh` 全量通过（无 e2e env 时跳过 LLM 相关）

## 输入
- 依赖文件: test-l1-full.ts（断言来源）、agent-team-loop 源码
- 依赖 Task: T-08（waitForMwStart 用例可能同文件）
- AC 约束:
  > AC-015: 原 test-l1-full.ts 的全部断言并入 `packages/coding-agent/test/` 下正式 vitest 文件，`./test.sh` 运行通过，且游离脚本被删除

## 预期产出
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`
- 删除 `packages/multi-workers/test-l1-full.ts`
- 验证方式: VC-016
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
