# Task 007: Build & dist verification

## 基本信息
- Stage: 3
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: TBD
- ac_refs: [AC-013, AC-014, AC-015]
- vc_refs: [VC-013, VC-014, VC-015]

## 描述
Stage 1+2 完成后，执行：
1. `npm run check`（TypeScript 类型检查 + lint）
2. `npm run build`（重建 dist，更新 packages/ai/dist/）
3. 验证 dist 产出：`dist/providers/data/timi.json` 协议分类符合 AC-001，`dist/providers/timi.js` 含双 API 实现
4. 凭证泄漏扫描（生成模型数据不含 API key 字段）

## 输入
- 依赖: Stage 1 全部完成（TS 检查需要零错误）、Stage 2 全部完成
- AC 约束:
  > AC-013: dist/providers/data/timi.json 协议分类与 AC-001 一致；dist/providers/timi.js 含双 API 实现；pi --list-models timi --offline 显示 GPT-5.6 三个变体 thinking=yes。
  > AC-014: 所有修改测试零失败；npm run check 零错误/警告；npm run build 零错误。
  > AC-015: 凭证模式扫描和 dry-run 输出不含 API key 值；生成模型元数据不含凭证字段。

## 执行步骤

### Step 1: npm run check
从 repo 根目录：
```bash
npm run check
```
期望：零错误，可有 info。

### Step 2: npm run build
```bash
npm run build
```
期望：零错误；packages/ai/dist/ 更新。

### Step 3: 验证 dist timi.json
```bash
node -e "
const d = require('./packages/ai/dist/providers/data/timi.json');
const all = [...Object.values(d['anthropic-messages'] || {}), ...Object.values(d['openai-responses'] || {})];
const claude = all.filter(m => m.id.startsWith('claude-'));
const gpt56 = all.filter(m => ['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna'].includes(m.id));
const errors = claude.filter(m => m.api !== 'anthropic-messages').concat(
  all.filter(m => !m.id.startsWith('claude-') && m.api !== 'openai-responses')
);
const reasoningErrors = gpt56.filter(m => !m.reasoning);
console.log('[VERIFY] VC-013: models=' + all.length + ' mismatches=' + errors.length + ' gpt56_reasoning=' + (gpt56.length - reasoningErrors.length));
if (errors.length || reasoningErrors.length) process.exit(1);
"
```

### Step 4: 验证 timi.js 含双 API
```bash
node -e "
const fs = require('fs');
const js = fs.readFileSync('packages/ai/dist/providers/timi.js', 'utf8');
const hasAnthropic = js.includes('anthropicMessagesApi');
const hasResponses = js.includes('timiResponsesApi') || js.includes('openAIResponsesApi');
console.log('[VERIFY] VC-002 (dist): hasAnthropic=' + hasAnthropic + ' hasResponses=' + hasResponses);
if (!hasAnthropic || !hasResponses) process.exit(1);
"
```

### Step 5: 凭证扫描
```bash
node -e "
const fs = require('fs');
const timiJson = fs.readFileSync('packages/ai/dist/providers/data/timi.json', 'utf8');
const forbidden = ['apiKey', 'api_key', 'TIMI_API_KEY', 'ANTHROPIC_API_KEY'];
const found = forbidden.filter(k => timiJson.includes(k));
console.log('[VERIFY] VC-015: credential_leaks=' + found.length);
if (found.length) { console.error('Found:', found); process.exit(1); }
"
```

## 预期产出
- `npm run check` 零错误 ✓
- `npm run build` 零错误 ✓
- `packages/ai/dist/providers/data/timi.json` — 15 模型，Claude→anthropic-messages，其余→openai-responses，GPT-5.6×3 reasoning=true ✓
- `packages/ai/dist/providers/timi.js` — 含 anthropicMessagesApi + timiResponsesApi ✓
- 凭证扫描 zero leaks ✓
- 验证方式: 上述 node/npm 命令
- 验证等级: Level 2

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
