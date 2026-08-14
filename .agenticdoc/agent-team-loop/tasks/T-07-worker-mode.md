# Task T-07: worker-mode.ts 主协调器

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-010, AC-011, AC-019, AC-026]
- vc_refs: [VC-016, VC-017, VC-018, VC-019, VC-027, VC-035]
- pattern_refs: []

## 描述
实现 `worker/worker-mode.ts`：Pi Extension worker mode 主协调器。

`workerModeActivate(pi)` 入口：
1. 读取 `process.env.PI_WORKER_TASK`，解析为 task.md 绝对路径
2. 读取 task.md，解析 `type` 字段，调用 `pi.setActiveTools(allowlist)` 设置工具白名单
3. 监听 `agent_settled` 事件（**不使用 `agent_end`**）
4. task.md 含 `phases` 字段 → 调用 `phase-runner.ts`（T-08）；否则单阶段执行
5. 通过 `output-writer.ts`（T-09）写 output.md，调用 `process.exit(0/1/2/130)`

AGENTS.md 规则遵守：
- 无动态 import，`workerModeActivate` 和 `pmActivate` 均为顶层 import（在 index.ts 中，见 T-10）
- 不使用 `any`（除非绝对必要）
- 只使用可擦除 TypeScript 语法（无 enum/namespace/module）

## 输入
- 依赖文件: `shared/worker-store.ts`（T-02）、`worker/phase-runner.ts`（T-08）、`worker/output-writer.ts`（T-09）
- 依赖 Task: T-02（格式定义），T-08, T-09（先 stub 后实现均可）
- AC 约束:
  > AC-010: PI_WORKER_TASK 存在时，读 task.md，调用 pi.setActiveTools(allowlist)，allowlist 外工具不出现
  > AC-011: agent_settled 事件触发后，output.md 存在且含 4 节，> 50 bytes，随后 process.exit(0)
  > AC-019: task.md 无 phases 字段 → 不创建 progress/ 目录，单阶段完成
  > AC-026: PI_WORKER_TASK 已设时加载 worker handler（顶层 import，非动态）

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
  - `export async function workerModeActivate(pi: PiApi): Promise<void>`
  - 工具白名单按 task.type 静态定义（如 `coding`: `['read_file', 'write_file', 'bash', ...]`）
- 验证方式: VC-016/017（setActiveTools spy）、VC-018/019（output.md 4 节 + size）、VC-027（无 phases 不创建 progress/）、VC-035（互斥加载）
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
- 卡住原因: Pi Extension API 中 agent_settled 事件签名待确认
- 处置: 实现前检查 Pi Extension API 文档或现有 Extension 用法
