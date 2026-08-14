# Task T-10: index.ts Extension 入口（PM/Worker 互斥加载）

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-026]
- vc_refs: [VC-035]
- pattern_refs: []

## 描述
实现 `index.ts`：Pi Extension 统一入口，在 `activate()` 中按 `PI_WORKER_TASK` 环境变量路由到 PM 或 Worker mode。

```typescript
// 顶层 import（AGENTS.md 规则：禁止 await import()）
import { workerModeActivate } from './worker/worker-mode';
import { pmActivate } from './pm/pm-orchestrator';

export async function activate(pi: PiApi): Promise<void> {
  if (process.env['PI_WORKER_TASK']) {
    await workerModeActivate(pi);
  } else {
    await pmActivate(pi);
  }
}
```

两者**均为顶层 import**，activate() 只做分支调用，不使用动态 import。

## 输入
- 依赖文件: `worker/worker-mode.ts`（T-07）、`pm/pm-orchestrator.ts`（T-13）
- 依赖 Task: T-07, T-13（可先 stub 导出）
- AC 约束:
  > AC-026: PI_WORKER_TASK 未设时加载 PM handler；已设时加载 Worker handler；两者互斥，均为顶层 import（不使用动态 await import()）

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`
  - 顶层 import workerModeActivate + pmActivate
  - `export async function activate(pi: PiApi): Promise<void>`
- 验证方式: VC-035（PM/Worker 互斥，spy 测试）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
