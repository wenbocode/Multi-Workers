# Task T-09: output-writer.ts（全 exit code 语义）

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-011, AC-012, AC-033]
- vc_refs: [VC-018, VC-019, VC-020, VC-042, VC-043, VC-044]
- pattern_refs: []

## 描述
实现 `worker/output-writer.ts`：按 exit code 写入 output.md 和 trace.log。

**output.md 节结构（按 exit code）**：
- exit 0（成功）：`## Summary` + `## Changed Files` + `## Verification Steps` + `## Exit Reason`，总 > 50 bytes
- exit 1（失败）：`## Summary`（部分）+ `## Exit Reason`（说明失败原因，内容非空）
- exit 2（需澄清）：`## Summary`（部分）+ `## Questions`（替代 Verification Steps，内容非空）
- exit 130（取消）：各节可部分填充，文件存在即可

**trace.log**：每次工具调用追加 `[FLOW] <timestamp> <action>`，供 VC-020 验证。

## 输入
- 依赖文件: task.md（读取 taskKey 和路径）
- 依赖 Task: 无（独立实现）
- AC 约束:
  > AC-011: agent_settled 后 output.md 含 Summary/Changed Files/Verification Steps/Exit Reason 四节，> 50 bytes，exit 0
  > AC-012: 至少一次工具调用时，trace.log 含 >= 1 行 [FLOW] 开头记录
  > AC-033: exit 1 → output.md 含 Exit Reason 节（非空）；exit 2 → 含 Questions 节；exit 130 → output.md 存在

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
  - `export function writeOutput(opts: WriteOutputOpts): void`
  - `WriteOutputOpts`: `{taskKey, agenticdocRoot, summary, changedFiles, verificationOrQuestions, exitReason, exitCode}`
  - `export function appendTrace(taskKey: string, agenticdocRoot: string, line: string): void`
- 验证方式: VC-018/019（4 节 + size，exit 0）、VC-020（trace [FLOW]）、VC-042/043/044（exit 1/2/130）
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
