# Spec: ai-baseline-repair

> Key: ai-baseline-repair
> 创建时间: 2026-09-10
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active，存量三段式）

- 对齐：本 spec 不直接产出 Agent Team 框架功能，而是恢复 goal.md 所述「PM + 多 Worker 并行开发」工作流的**提交门禁可用性**——AGENTS.md 规定每次代码改动后 `npm run check` 必须全绿才能提交，当前 tsgo 步骤因 packages/ai 26 错常红，所有并行 key 的收口都受阻（mw-widget-terminal-lifecycle T-09 已实证被阻塞）。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-A1: 不修改 `packages/ai/src/models.generated.ts`；只允许改 `scripts/generate-models.ts` 后重生成（AGENTS.md）
  - GC-A2: 不得为修类型错误移除/降级功能代码（AGENTS.md：never remove or downgrade code to fix type errors）；cloudflare-ai-gateway 的 openai-completions 路由语义必须保留
  - GC-A3: 测试修复保持原测试意图（换 model ID 不换断言语义；类型面修复不删断言）
  - GC-A4: 修复面最小化：只动 26 错 + 8 运行时失败涉及的文件 + 预防约定文档；不顺手重构
  - GC-A5: Windows 环境约束：无 gh CLI / GitHub API token；CI 取证用本地 worktree 复现替代，报告中标注置信度
- 冲突：无（不触碰 agent-team-loop 扩展域与 mw Python 域的 GC-1~4 约束范围）
- 预期收益：
  - `npm run check` 恢复全绿（判定：tsgo 步骤 26→0 错，后续步骤不被本 key 引入的新错阻塞）
  - packages/ai 测试套件零失败（判定：`test.sh` 或包内 vitest 全绿）
  - 87 个第二层失败有明确归属（判定：归因报告给每类失败标注 A=栈引入 / B=Windows 缺口 / C=叠加 + 修/不修建议 + 用户决策留痕）

## §1 功能概述

### 1.1 目标

本 fork 的 12 个未推送提交栈（8806e2be8「提供第一版 pi 功能」→ fceae6eaf）从未整体通过 `npm run check`：packages/ai 域 26 个 tsgo 错误（src 1 + test 25）+ 8 个运行时测试失败，另有 packages/agent 2 + packages/coding-agent core 85 个失败未归属（Windows 环境签名为主，未做过 Linux 语义对照）。

本 key 交付：

1. **packages/ai 修复（第一层，必须修）**：26 tsgo + 8 运行时失败清零，`npm run check` 全链路通过。
2. **第二层归因（必须做，修不修由报告+用户定）**：origin/main 真基线取证 + 87 失败三分类（A/B/C）+ 修/不修建议表。
3. **预防约定**：测试引用 model ID / 类型面的稳定化约定落文档，阻断下一轮 catalog/类型演进再漂。

### 1.2 技术栈 / 语言

TypeScript（packages/ai：src/providers/cloudflare-ai-gateway.ts + ~13 test 文件）+ shell（worktree 取证脚本）。

### 1.3 核心用户场景

1. 任意 key 的 worker/PM 完成代码改动后执行 `npm run check`：当前因 ai 域 26 错红，无法判断自己的改动是否引入新错 → 修复后 check 恢复「绿 = 可提交」语义。
2. 用户决策第二层 87 失败的处置：依据归因报告判断哪些值得修（A 类，栈内真实回归）、哪些接受为 Windows 已知缺口（B 类，CI 无 Windows job）。
3. 下次 model catalog 或 provider 类型面演进：测试不再硬编码易逝 ID/形状，check 提前红并指向明确修复点，而不是静默漂移数周。

## §3 业务约束

| 编号 | 约束 | 来源 |
|------|------|------|
| C-1 | models.generated.ts 禁直改 | AGENTS.md + GC-A1 |
| C-2 | 禁删功能修类型（cloudflare openai-completions 路由保留） | AGENTS.md + GC-A2 |
| C-3 | 测试意图不变（ID 换现存值、断言语义不动） | GC-A3 |
| C-4 | 修复面最小化 | GC-A4 |
| C-5 | tsgo/biome/其余 check 链步骤修复后全绿 | AGENTS.md |
| C-6 | 归因取证不得切走主 worktree（用 git worktree add 独立目录） | AGENTS.md git 纪律 |
| C-7 | npm install/ci 一律 `--ignore-scripts` | AGENTS.md |
| C-8 | 测试运行走 `./test.sh`（Git Bash）或包内 vitest，不跑全量 e2e | AGENTS.md |

## §4 可复用资产

本 key 产出的可复用资产：

1. **model ID 迁移映射表**（design D-002）：旧→新 ID 逐点映射 + 三种模式（上游镜像/点号 id/gateway 重定向），后续 catalog 演进可直接套用模式判定
2. **选择性镜像流程**：上游 pi-mono 作为共享测试文件修复参照的操作步骤（fetch upstream → 逐 hunk 判定 → 跳过依赖缺失 provider 的 hunk 并注记）
3. **归因报告模板**（AC-007）：A/B/C 三分类 + 置信度注记 + 用户决策区，后续任何基线漂移均可复用
4. **预防约定文档**（AC-008）：fork 特有测试的 ID 引用规范 + 共享文件同步约定
5. **坑点沉淀**：本 key 踩坑记入 `.agenticdoc/_pitfalls.md`（见 §5）

## §5 需规避坑点

- **上游整体 checkout 陷阱**：共享测试文件直接取 upstream 版会引入我们目录不存在的 provider（qwen-token-plan-individual）与 54 文件 src 分歧依赖——必须选择性 hunk 镜像
- **models.dev 目录波动**：gateway 的 workers-ai 条目随时间增删，再生成零 diff 不代表语义未变；测试不得依赖「gateway 会一直有某类模型」
- **`data/*.json` 是 gitignore 生成物**：比对 fork 与上游目录时不能用 git diff（一侧不在版本库），须直接查 models.dev 实时 API
- **控制台 GBK 乱码误读**：框架脚本中文输出在 PowerShell 控制台为乱码，禁止凭乱码猜内容——一律写临时文件用 UTF-8 读（本 key 曾因猜错门禁关键词返工）
- **edit 工具 JSON 转义**：代码字符串中的 `\n` 须写 `\n` 否则写入真实换行；pm-state 接口行不可手改（含锚定接口行的 edit 也被拦）

## §6 验收标准

- **AC-001**: `packages/ai/src/providers/cloudflare-ai-gateway.ts` 的 TS2353 修复：openai-completions 路由按当前 ProviderStreams/compat 类型面正确接入，功能语义不删不减（GC-A2）；该文件 tsgo 零错
- **AC-002**: test 域 15 处 TS2345（过时 model ID，~8 文件）替换为 ModelId union 现存 ID，映射关系在 evidence 留底；断言语义不变（GC-A3）
- **AC-003**: `cross-api-thinking-history.test.ts` 8 处类型面陈旧修复（StopReason 值、流事件 union、ResponseInputItem cast、Model fixture baseUrl）
- **AC-004**: `openai-completions-tool-choice.test.ts`（maxTokensField）与 `timi-dispatch.test.ts`（TS1294 非可擦语法改写）修复
- **AC-005**: repo root `npx tsgo --noEmit` 零错误（26→0），`npm run check` 全链路 exit 0
- **AC-006**: packages/ai 测试套件零失败（既有 8 失败修复或证明与 AC-002/003 同根自愈，逐个留痕）
- **AC-007**: 第二层归因报告落盘（evidence/runs/）：① origin/main worktree 取证结果（build/check/test 绿红 + Windows 上跑 Linux 语义的置信度标注）；② 87 失败三分类（A=未推送栈引入 / B=Windows 环境缺口 / C=叠加）逐类清单与计数；③ 修/不修建议表 + 用户决策留痕（决策前本 key 不擅自扩范围修第二层）
- **AC-008**: 预防约定落文档：测试引用 model ID/类型面的稳定化方式（design 阶段定形：fixture 常量模块 / registry 派生 / 约定条款），写入对应包 docs 或 CHANGELOG 附注，下轮演进可循

> 指纹（quality-gate canonical 管道）：AC-001~008 → `sha1(排序去重 AC 列表)` 前 12 位，锁定于 evidence-requirement.md
