# Design: ai-baseline-repair

> Key: ai-baseline-repair
> 模式: 轻量 key（用户 2026-09-10 拍板）——design 一页化、任务 PM 直执不派 worker、一次 quality gate
> 输入: spec.md (AC-001~008) + evidence/research/spec-baseline-forensics-2026-09-10.md + 本日补证（upstream 比对、models.dev 实时查询）

## 0. 归因修正（对 spec 取证的两点深化）与替代方案比较

| 方案 | 描述 | 采纳 | 理由 |
|---|---|---|---|
| A. 整体同步 upstream packages/ai | 54 文件分歧一次性拉齐 | 否 | 超出 GC-A4 修复面；未评估的上游行为变更；应作独立 key |
| B. 选择性 hunk 镜像（D-002） | 只取上游 ID 修正，跳过依赖缺失 provider 的 hunk | 是 | 上游为权威意图参照；零新依赖；逐 hunk 注记成本低 |
| C. fixture 常量模块重写测试 ID | 集中 fixture 取 ID | 否（fork 特有测试的预防约定保留此思想） | 共享文件重写后与上游 diff 恶化；fork 特有文件适用 |
| D. 删除过时测试 | 删失败/过时用例 | 否 | 禁止为修类型删功能（GC-A2/A3） |
| E. 放宽检查绕门禁 | 跳过 tsgo 继续开发 | 否 | 门禁是并行开发流提交前提；掩盖而非修复 |

1. **上游 pi-mono 可达且在持续维护模型目录**（`upstream/main` 已 fetch，remote 已添加）：10/11 个出错共享测试文件在上游晚于我们的导入更新过（08-19/09-07/09-10）。上游的修复 = 权威意图参照。
2. **models.dev 实时数据（2026-09-10 查证）：cloudflare-ai-gateway provider 下 workers-ai 条目为 0**。我们本地再生成零 diff ⇒ 我们的目录是真实态；「gateway + workers-ai 模型」这一组合在当前 catalog 下不存在。上游测试仍引用 `getModel("cloudflare-ai-gateway", "workers-ai/...")` 是因为他们新一代 generator（与我们有 485+/443- 分歧）会另行合成；直接照抄上游测试行在我们的 generator 下仍类型错误。**结论：共享文件采取「选择性镜像」，非整文件 checkout。**

## 1. 修复决策（D-001~D-008）

### D-001 cloudflare-ai-gateway.ts TS2353（AC-001）

镜像上游修法（upstream/main 758a0ee9b 起）：提取 `type CloudflareAIGatewayApi = "anthropic-messages" | "openai-completions" | "openai-responses"`，调用改为 `createProvider<CloudflareAIGatewayApi>({...})`，附上游同款注释（gateway catalog 会随时间增删 workers-ai 条目，api map 钉死三 API 是刻意的）。功能零变化（GC-A2：openai-completions 路由保留）。

### D-002 共享测试文件 model ID 重定向（AC-002，15 处 TS2345）

三种模式，逐点映射表（执行时以 tsgo 逐行核对）：

| 模式 | 旧 | 新 | 理由 |
|---|---|---|---|
| M1 上游镜像 | `("anthropic","claude-opus-4-1-20250805")` | `claude-sonnet-4-6` | 上游 08-19 已改，意图=thinking abort 测试 |
| M1 上游镜像 | `("google","gemini-2.0-flash")` ×2 | `gemini-2.5-flash` | 上游已改 |
| M1 上游镜像 | `("github-copilot","gpt-5.2-codex")` ×2 | `gpt-5.5` | 上游 09-07 已改；我们目录已含 gpt-5.5 |
| M2 点号 id | `("cloudflare-ai-gateway","claude-sonnet-4-5")` | `claude-sonnet-4.5` | gateway 目录用点号命名；anthropic 直连才用连字符 |
| M3 gateway+workers-ai 重定向 | `("cloudflare-ai-gateway","workers-ai/@cf/moonshotai/kimi-k2.6")` ×8 | `("cloudflare-workers-ai","@cf/moonshotai/kimi-k2.6")` | models.dev 已无 gateway workers-ai 条目；同模型同 api（openai-completions/compat），仅传输从 gateway 换直连；文件内已有同款先例（empty:310 等）。describe 标题同步改 "Cloudflare AI Gateway → ..." 为 "Cloudflare Workers AI ..."。文件内因此与既有 workers-ai 块近似重复的（empty/tokens/total-tokens/unicode），按「保留块、改标题」处理（不删块，避免功能移除争议；冗余在验收注记中说明） |
| （跳过）上游新增 qwen-token-plan-individual 块 | — | — | 该 provider 在我们 generator 输出中不存在，超出 GC-A4 修复面 |

涉及文件：abort / context-overflow / empty / openai-completions-empty-tools / stream / tokens / tool-call-id-normalization / tool-call-without-result / total-tokens / unicode-surrogate（共 10 个）。

### D-003 cross-api-thinking-history.test.ts 8 处（AC-003，fork 特有，无上游参照）

按当前类型面逐一修：① fixture Model 补 `baseUrl`（及其他新增必填字段）；② `"end_turn"` → 当前 StopReason 值（`"stop"`/`"toolUse"` 按断言语境）；③ 流终止事件 `type === "stop"` → `type === "done"`（payload 字段相应改 `.message`）；④ 4 处 `ResponseInputItem → Record<string,unknown>` 强转 → 先经 `unknown` 或按 union 正当窄化。断言语义不删（GC-A3）。

### D-004 timi-dispatch.test.ts TS1294（AC-004）

`constructor(readonly captured: unknown)` 参数属性 → 显式字段 + 赋值（erasableSyntaxOnly 合规）。

### D-005 openai-completions-tool-choice.test.ts TS2339（AC-004）

`model.compat?.maxTokensField` 在 `OpenAICompletionsCompat | OpenAIResponsesCompat` union 上直取 → 先窄化（`"maxTokensField" in compat` 或按 `model.api` 判别）再断言。断言不变。

### D-006 预防约定落文档（AC-008）

两层：① **fork 特有测试**（cross-api-*、timi-*）禁止硬编码带版本号 model ID——从 catalog 派生或集中 fixture；② **共享 pi 测试**保持贴近 upstream，catalog 变更引发的测试同步以 upstream 为参照（选择性 hunk 镜像）。落点：`packages/ai/README.md` 新增小节（或文件头注释，若 README 不存在）。

### D-007 第二层归因（AC-007）

`git worktree add` 独立目录 ×2（origin/main、HEAD）→ `npm ci --ignore-scripts` + build + check + test → 三分类：A=未过 CI 栈引入（Linux 语义也败）/ B=Windows 环境缺口 / C=叠加。产出 `evidence/runs/attribution-2026-09-10.md`：分类清单+计数+修/不修建议表+用户决策区（决策前不扩范围修第二层）。置信度注记：Windows 上跑 Linux 语义测试的偏差（路径/超时/信号）。

### D-008 验证链

tsgo 26→0 → `npm run check` 全链 → packages/ai 套件（`./test.sh` 或包内 vitest）零败 → biome 触碰文件零告警 → 修复面 diff 范围核对（GC-A4）。

## 2. 验证标准（VC，精简到关键断言）

| VC | 断言 | 对应 AC | 证据形态 |
|---|---|---|---|
| VC-001 | `npx tsgo --noEmit` 零错误 | AC-005 | 命令输出 |
| VC-002 | `npm run check` exit 0 | AC-005 | 命令输出 |
| VC-003 | packages/ai 测试零失败（8 个预存失败清零或留痕同根自愈） | AC-005, AC-006 | vitest 输出 + 逐个说明 |
| VC-004 | cloudflare provider 仍注册三 API（含 openai-completions） | AC-001 | 结构断言/grep |
| VC-005 | 映射表全部新 ID 存在于 `src/providers/data/*.json` | AC-002 | 核对脚本输出 |
| VC-006 | cross-api 修复无断言删除（diff 审阅：仅类型面适配） | AC-003 | diff 注记 |
| VC-007 | attribution 报告含 A/B/C 分类、计数、建议表、用户决策区 | AC-007 | 文档存在性+内容审阅 |
| VC-008 | 预防约定已落 packages/ai 文档 | AC-008 | 文档 diff |
| VC-009 | 触碰文件 biome 零告警；diff 范围=声明面（无顺手重构） | GC-A4 | biome 输出 + diff 范围核对 |

## 3. 任务拆分（PM 直执，5 个）

| Task | 内容 | AC 覆盖 |
|---|---|---|
| T-01 | D-001 + D-004 + D-005（src 修 + 两处单点类型修） | AC-001/004 |
| T-02 | D-002 映射表全量执行（10 文件）+ VC-005 核对 | AC-002 |
| T-03 | D-003 cross-api 8 处 | AC-003 |
| T-04 | D-006 预防文档 + D-008 验证链全跑 + 运行时失败逐个留痕 | AC-005/006/008 |
| T-05 | D-007 归因取证 + 报告 + 用户决策点 | AC-007 |

依赖：T-01/02/03 可乱序；T-04 依赖全部；T-05 与 T-01~04 无耦合可并行（但同窗口串行执行）。

## 4. 风险与注记

- **R-1** gateway+workers-ai 块重定向后与既有 workers-ai 块近似重复（4 文件）——按 D-002 保留不删；若用户偏好合并，后续一行删块即可
- **R-2** 上游选择性镜像的判定成本：跳过的 hunk 必须逐一注记原因（provider 缺失），防止未来误同步
- **R-3** `upstream` remote 为本次新增（git config 变更，留作后续同步用；不改任何工作区文件）
- **R-4** packages/ai 运行时 8 失败的具体清单需 T-04 重取（早前会话归因为 registry 断言漂移）；若与 TS2345 不同根且修复超出声明面，升级用户决策
