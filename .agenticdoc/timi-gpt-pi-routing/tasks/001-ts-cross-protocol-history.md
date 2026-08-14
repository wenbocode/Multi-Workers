# Task 001: Cross-protocol thinking history

## 基本信息
- Stage: 1
- 代码状态: 完成
- 验证状态: 已验证
- 负责 Agent: claude-sonnet-4-6
- ac_refs: [AC-006]
- vc_refs: [VC-006]

## 描述
当对话历史跨越 anthropic-messages / openai-responses 两种协议时，目标协议序列化必须过滤掉来自源协议的 thinking/reasoning 签名，同时保留用户内容、最终文本、工具调用和工具结果。同协议历史继续回放有效签名。

当前状态：
- `openai-responses-shared.ts` 约第 220 行：thinking block 回放未检查 `assistantMsg.api === model.api`
- `anthropic-messages.ts` 约第 1178 行：thinking block / redacted block 回放未检查历史消息的 `.api` 字段

## 输入
- 依赖文件:
  - `packages/ai/src/api/openai-responses-shared.ts`（约第 208-230 行）
  - `packages/ai/src/api/anthropic-messages.ts`（约第 1168-1220 行，`convertMessages` 函数中）
- AC 约束:
  > AC-006: 跨协议历史保留用户内容、最终助手文本、图像、工具调用和工具结果，同时省略源协议 thinking/reasoning 签名；同协议历史继续回放有效签名。

## 实现步骤

### openai-responses-shared.ts 修复
在 `thinking` block 处理（约第 220 行）添加 API 守卫：
```typescript
if (block.type === "thinking") {
    if (block.thinkingSignature && assistantMsg.api === model.api) {
        const reasoningItem = JSON.parse(block.thinkingSignature) as ResponseReasoningItem;
        output.push(reasoningItem);
    }
    // 跨协议：omit（不推送任何内容，等效于跳过该 thinking block）
}
```

### anthropic-messages.ts 修复
在 `convertMessages` 函数的 `assistant` 分支开头（约第 1168 行）获取 AssistantMessage 并判断 API：
```typescript
} else if (msg.role === "assistant") {
    const assistantMsg = msg as AssistantMessage;
    const isSameApi = assistantMsg.api === "anthropic-messages";
    const blocks: ContentBlockParam[] = [];

    for (const block of msg.content) {
        if (block.type === "thinking") {
            if (!isSameApi) continue; // 外来 reasoning 签名，跳过
            // ... 保留现有逻辑
        }
```

## 预期产出
- `packages/ai/test/cross-api-thinking-history.test.ts`（新建）
  - 测试 1: Anthropic→Responses 方向：anthropic 历史的 thinking block 不出现在 Responses 序列化
  - 测试 2: Responses→Anthropic 方向：openai-responses 历史的 thinking block 不出现在 Anthropic 序列化
  - 测试 3: 同协议 Anthropic 历史：有效签名正常回放
  - 测试 4: 同协议 Responses 历史：reasoning item 正常回放
- 修改 `packages/ai/src/api/openai-responses-shared.ts`
- 修改 `packages/ai/src/api/anthropic-messages.ts`
- 验证方式: 直接运行测试文件，全部通过
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-14 | 实现 openai-responses-shared.ts + anthropic-messages.ts + 测试 | 4/4 pass |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本 | 状态 |
|----|------|---------|---------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
