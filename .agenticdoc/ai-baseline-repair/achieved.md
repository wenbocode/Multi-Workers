# Achieved: ai-baseline-repair

> 结案: 2026-09-10 | commit 锚: `04bc69616`（代码）+ AGENTS.md Windows 基线注记（文档，随 key 收尾提交） | 质量: QG 38/38 PASS，review LGTM（0 S1/S2）

## 做了什么

**第一层（必修，全部达成）**：packages/ai 基线漂移修复——tsgo 26 错 → 0、`npm run check` 全链绿、ai 套件 8 failed → 838 passed / 0 failed。核心根修 = 镜像上游 generator 的 workers-ai→gateway 镜像块（+37 行，对冲 models.dev 增删）+ cloudflare api map 钉死三 API + 过时 model ID 全量重定向 + cross-api 类型面修复 + 运行时断言对齐（上游已修则镜像、fork 特有则对齐本地目录）。

**第二层（归因交付物，AC-007）**：agent 13 + coding-agent 76 = 89 败的 worktree×2 实证归因——**B=58（Windows 缺口，上游同款）/ A'=26（上游 09 月已修，同步可解）/ A=0（本 fork 栈零引入）**。上游同机 95 败（含字面 Windows 命名测试）为 B 类铁证。

**预防层（AC-008）**：README「Model Catalog and Test Hygiene」三规则（fork 特有测试禁硬编码易逝 ID / 共享测试镜像上游 hunk / gateway 两个 safeguard 勿动）+ AGENTS.md Windows 开发机 89 败基线注记。

## 用户决策留痕（attribution §6）

- B 类 58：暂不修 + 文档化（已执行）
- A' 类 26：规划一次上游 forward-port（独立 key，待 12 提交栈推送合并后）
- 89 败基线写入 AGENTS.md（已执行）

## 遗留移交

1. **上游 forward-port key**（时机：dev/AgentTeam 推送合并后）：一次性同步上游 09 月修复面，顺带清掉 A' 26 个 + 降低未来漂移速率。
2. **B 类 58 个 Windows 缺口**：长期项。若未来引入 Windows CI（新增 matrix）需先修这批。
3. timi fork 特有面（`timi-models`/`timi-dispatch` 测试）对 models.dev timi 目录仍敏感，下次目录变更按 README 卫生节规则处理。

## 可复用资产

- worktree×2 同机对照归因法（HEAD vs upstream/main，npm ci+build+hydrate 全链对齐，逐测试名精确匹配 + 文件历史定位上游修复提交）——任何「上游 fork 漂移」问题可复用。
- canonical 指纹管道的 PowerShell 陷阱清单（UTF-16 重定向、grep 缺失、逐行尾换行语义、GBK 控制台）。

## 目标收益达成

- 单 Agent 无法并行的基线修复 + 归因在同一 PM 窗口内完成（轻量 key 模式：无 worker 派发，5 任务全直执）。
- 「栈从未整体过 check」的悬念消除：tsgo/check/套件三绿，且证明栈零引入性破坏。
