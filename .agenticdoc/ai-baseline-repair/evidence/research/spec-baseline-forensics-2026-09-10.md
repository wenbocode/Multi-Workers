# 调研留底：packages/ai 基线漂移取证（spec 阶段，2026-09-10）

> Key: ai-baseline-repair
> 来源：mw-widget-terminal-lifecycle T-09 全量回归时的基线取证（evidence/runs/regression-2026-09-10.md §4）+ 本日补测

## 1. 错误清单（`npx tsgo --noEmit`，repo root，HEAD = fceae6eaf）

**26 错全在 packages/ai**：src 1 + test 25。

### src 域（1 错）

| 文件 | 错误 | 性质 |
|------|------|------|
| `src/providers/cloudflare-ai-gateway.ts:19` | TS2353 `"openai-completions"` 不在 `Partial<Record<"anthropic-messages" | ...>>` | **已推送文件（07-14, 9993c9690，在 origin/main 上）被本地未推送的类型面演进弄坏**（ProviderStreams/compat 类型 union 变化） |

### test 域（25 错，按文件）

| 文件 | 数量 | 错误性质 |
|------|------|---------|
| `test/cross-api-thinking-history.test.ts` | 8 | 类型面陈旧集群：TS2741 Model fixture 缺 `baseUrl`；TS2322 `"end_turn"` 已非 StopReason；TS2367/TS2339 流事件 union 演进；TS2352×4 `ResponseInputItem` cast 不成立 |
| `test/openai-completions-empty-tools.test.ts` | 3 | TS2345 过时 model ID |
| `test/tool-call-id-normalization.test.ts` | 2 | TS2345 `gpt-5.2-codex` 等 |
| `test/stream.test.ts` / `total-tokens.test.ts` | 2+2 | TS2345 `workers-ai/@cf/moonshotai/kimi-k2.6`、`gemini-2.0-flash` |
| 其余 7 文件各 1 | 9 | TS2345 为主 + `tool-choice.test.ts` TS2339 `maxTokensField` 已不在 compat 类型 + `timi-dispatch.test.ts` TS1294 非可擦语法（erasableSyntaxOnly） |

**按错误码**：TS2345×15 / TS2352×4 / TS2339×2 / TS1294、TS2353、TS2367、TS2741、TS2322 各 1。

## 2. 关键归因事实（本日新证据，修正「上游漂移」假设）

1. **HEAD 领先 origin/main 12 个未推送提交**（`git rev-list --count origin/main..HEAD` = 12），栈底即 8806e2be8「提供第一版 pi 功能」（08-14，pi 代码批量导入）
2. `cross-api-thinking-history.test.ts` 最后触碰 = 8806e2be8（**不在 origin/main**）——过时测试全部来自未推送导入
3. `cloudflare-ai-gateway.ts` 最后触碰 = 9993c9690（07-14，**在 origin/main**）——它是被未推送栈内的类型演进（如 9993c9690 后的 model runtime/provider 重构）破坏的
4. **结论：漂移 = 本 fork 未推送 WIP 栈内部不一致，非上游漂移**。origin/main（导入前）大概率自洽绿；「预存基线红」实为「12 提交栈从未整体过过 check」（旁证：mw-worker-timeout-convergence 记录过当时 check 580 错，f6cea320c 已修过一批 agent 测试）
5. `npm run generate-models` 重生成零 diff → models.generated.ts 现行；错误全在代码/测试侧
6. tsgo 7.0.0-dev.20260120.1 与 lockfile 一致，非工具链问题

## 3. CI 语境（第二层归因输入）

- `.github/workflows/ci.yml`：仅 `ubuntu-latest` 单 OS，push main / PR 触发，步骤 = build → `npm run check` → `npm test`
- 含义：① tsgo 26 错与 OS 无关 → 若推 HEAD 必红 Check 步；② agent 2 + coding-agent 85 的 Windows 签名失败 CI 永远看不见（无 Windows job）→「CI 绿」也不能证明这些失败不存在，只能证明 Linux 上没有
- 本机无 gh CLI、GitHub API 403（私有仓无 token）→ CI 历史状态无法直接取证；替代方案：git worktree 检出 origin/main 本地复现 build+check+test（Linux 语义近似，Windows 上跑仍有 OS 差异，需在报告中标注置信度），或用户提供 token/截图
- packages/ai 运行时 8 失败（test.sh，Linux 语义 Git Bash 下取得）：model registry 断言漂移，与 TS2345 同根

## 4. 修复面预估

- **机械替换**（~15 处 TS2345）：建旧→新 model ID 映射，换成 ModelId union 现存 ID；保持测试意图不变
- **类型面修复**（cross-api 8 处 + tool-choice 1 + cloudflare 1）：需读当前 StopReason/流事件/compat/ProviderStreams 定义逐一修正；cloudflare 属 src 域须谨慎（不得删 openai-completions 功能路由，AGENTS.md 禁止降级）
- **TS1294**（timi-dispatch.test.ts）：非可擦语法改写（enum/namespace → 等价可擦写法）
- **运行时 8 失败**：与 tsgo 修复合并验证，部分可能同根自愈
- **预防层**：测试对 model ID/类型面的引用方式需要约定（fixture 常量模块 or 从 registry 生成），否则下次 catalog/类型演进再漂

## 5. 第二层（agent 2 + coding-agent 85）归因方案

1. worktree 检出 origin/main → `npm ci --ignore-scripts` + build + check + test → 判定导入前基线绿/红
2. worktree 检出 HEAD → 同流程 → 与本机（Windows 原生）结果对照，把 87 失败分类：A=未推送栈引入（Linux 语义也失败）/ B=Windows 环境缺口（Linux 过 Windows 败）/ C=叠加
3. A 类 → 纳入本 key 或续 key 修复建议；B 类 → 记录为已知 Windows 缺口（CI 无 Windows job，修复收益需用户决策）；输出修/不修建议表 + 用户决策留痕
