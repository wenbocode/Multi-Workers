# Task 003: Model resolver default + pm-orchestrator provider + dispatch test

## 基本信息
- Stage: 1
- 代码状态: 完成
- 验证状态: 已验证
- 负责 Agent: claude-sonnet-4-6
- ac_refs: [AC-002, AC-003]
- vc_refs: [VC-002, VC-003]

## 描述
三个独立但小的修改：
1. `model-resolver.ts`：timi 默认模型从 `claude-sonnet-4.6` 改为 `gpt-5.6-sol`
2. `pm-orchestrator.ts`：`pickCli` 返回 `pi` 时，设置 `provider: "timi"` 而不是 `""`
3. timi provider dispatch 测试：验证 Claude 模型走 anthropic-messages、GPT 模型走 openai-responses

## 输入
- 依赖文件:
  - `packages/coding-agent/src/core/model-resolver.ts`（第 23 行：`"timi": "claude-sonnet-4.6"`）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（第 53 行：`provider: ""`）
  - `packages/coding-agent/test/model-resolver.test.ts`
- AC 约束:
  > AC-002: timiProvider() 的 API 实现映射包含 anthropic-messages 和 openai-responses，各调用一个 family 的模型不报 missing-implementation。
  > AC-003: 无显式模型时 Pi 对 timi provider 选择 gpt-5.6-sol。

## 实现步骤

### model-resolver.ts
```typescript
"timi": "gpt-5.6-sol",
```

### pm-orchestrator.ts
`pickCli` 返回 `"pi"` 时，设置 `provider: "timi"`：
```typescript
function pickWorkerRoute(taskContent: string): { cli: string; provider: string } {
    if (/^type:\s*(review|research)/im.test(taskContent)) return { cli: "claude", provider: "" };
    return { cli: "pi", provider: "timi" };
}
```
在 `dispatchNewTasks` 中调用：
```typescript
const { cli, provider } = pickWorkerRoute(taskContent);
await dispatchTask({ taskKey, status: "pending", cli, provider, taskPath: taskMdPath }, workerStore);
```

### model-resolver.test.ts 追加测试
在现有测试文件末尾追加：
```typescript
it("defaults to gpt-5.6-sol for timi provider", () => {
    expect(defaultModelPerProvider["timi"]).toBe("gpt-5.6-sol");
});
```
VC-003 output: `[VERIFY] VC-003: default_model=gpt-5.6-sol`

### timi dispatch test (VC-002)
新建或在 `packages/ai/test/timi-dispatch.test.ts`，使用 fake fetch transport：
- 创建 `timiProvider()`，选 claude-sonnet-4.6（anthropic-messages family）和 gpt-5.6-sol（openai-responses family）
- 各自通过 `onPayload` 捕获协议特征（Anthropic payload 有 `messages` 字段；Responses 有 `input` 字段）
- 断言两者都不报 missing-implementation 且到达正确实现
- VC-002 output: `[VERIFY] VC-002: dispatch_families=2 failures=0`

## 预期产出
- 修改 `packages/coding-agent/src/core/model-resolver.ts`（1 行）
- 修改 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- 追加 `packages/coding-agent/test/model-resolver.test.ts`（timi 默认模型断言）
- 新建 `packages/ai/test/timi-dispatch.test.ts`（或追加到 providers.test.ts）
- 验证方式:
  - `node ../../node_modules/vitest/dist/cli.js --run test/timi-dispatch.test.ts`（packages/ai）
  - `node ../../node_modules/vitest/dist/cli.js --run test/model-resolver.test.ts -t "timi"`（packages/coding-agent）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本 | 状态 |
|----|------|---------|---------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
