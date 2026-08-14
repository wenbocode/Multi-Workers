# Task 002: Timi retry boundary + normalization tests

## 基本信息
- Stage: 1
- 代码状态: 完成
- 验证状态: 已验证
- 负责 Agent: claude-sonnet-4-6
- ac_refs: [AC-004, AC-005]
- vc_refs: [VC-004, VC-005]

## 描述
timi-responses.ts 当前已有 payload 归一化（删除 store、工具描述补全），但缺少：
1. 流事件包装 — 追踪 `start` 事件，在 pre-start terminal error 上追加 `provider_retry_boundary` 诊断
2. retry.ts 中尚无 PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC 常量，isRetryableAssistantError 未对该诊断 opt-out

需要补全这两处，并写 timi-responses.test.ts 覆盖归一化 + 重试边界两组用例。

## 输入
- 依赖文件:
  - `packages/ai/src/utils/retry.ts`（isRetryableAssistantError）
  - `packages/ai/src/api/timi-responses.ts`（timiResponsesApi + wrapOptions）
  - `packages/ai/src/utils/diagnostics.ts`（appendAssistantMessageDiagnostic, createAssistantMessageDiagnostic）
  - `packages/ai/src/utils/event-stream.ts`（AssistantMessageEventStream）
- AC 约束:
  > AC-004: 归一化删除顶层 store，递归处理 tools 数组，仅改空白 string 描述，保留非空/非 string/缺失描述，运行在 caller onPayload 之后，不修改 caller 的 payload 对象。
  > AC-005: 默认 maxRetries=8，显式值（含 0）保留，pre-start terminal error 有 provider_retry_boundary.outerRetryEligible=false，post-start error 保持 outer-retry-eligible。

## 实现步骤

### retry.ts 修改
在 `isRetryableAssistantError` 函数前加常量：
```typescript
export const PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC = "provider_retry_boundary";
```
在函数体开头加 opt-out 判断：
```typescript
const boundary = message.diagnostics?.find(
    (d) => d.type === PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC && d.details?.outerRetryEligible === false,
);
if (boundary) return false;
```

### timi-responses.ts 修改
`timiResponsesApi()` 新增流包装：追踪 `start` 事件；当 terminal `error` 事件到来且 `start` 未发射时，在 error 消息上追加 `provider_retry_boundary` 诊断（outerRetryEligible: false）后再转发：
```typescript
function wrapStream(innerStream: AssistantMessageEventStream): AssistantMessageEventStream {
    const outer = new EventStream<AssistantMessageEvent, AssistantMessage>(
        (e) => e.type === "error" || (e.type === "toolcall_start" && false), // use proper isComplete
        (e) => (e as { error: AssistantMessage }).error
    );
    // ... 迭代 innerStream，追踪 start，追加诊断
}
```

实际上使用 `async function* wrapEvents` 模式更简单：直接 yield 每个事件，遇到 pre-start error 时修改后 yield。

### 暴露 delegate 参数（测试 seam）
```typescript
export function timiResponsesApi(delegate = openAIResponsesApi()): ProviderStreams { ... }
```

## 预期产出
- 修改 `packages/ai/src/utils/retry.ts`
- 修改 `packages/ai/src/api/timi-responses.ts`
- 新建 `packages/ai/test/timi-responses.test.ts` 覆盖：
  - 归一化：顶层/嵌套 store 删除、空白描述补全、非空保留、source 不变
  - caller mutation 和 replacement 组合
  - maxRetries 默认 8、显式 0 保留
  - pre-start error 有 boundary 诊断
  - post-start error 无 boundary 诊断
- 验证方式: `node ../../node_modules/vitest/dist/cli.js --run test/timi-responses.test.ts`
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
