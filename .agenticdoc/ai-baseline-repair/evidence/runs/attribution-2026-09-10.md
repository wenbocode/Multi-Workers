# 第二层归因报告：packages/agent + coding-agent 运行时失败（2026-09-10）

> Key: ai-baseline-repair / T-05 / AC-007 / D-007
> 方法：git worktree ×2（`mw-attr-head` @ 04bc69616 含 ai 修复；`mw-attr-upstream` @ upstream/main 08dc60bc5），各自 `npm ci --ignore-scripts` + 完整 build + hydrate 后同机同环境跑 vitest，逐测试名精确比对 + 文件历史取证。

## 0. 基线口径修正

- 原始记录「87 处（agent 2 + coding-agent 85）」单位混杂：agent 的 2 实为**失败文件数**（13 个测试）。
- ai 修复（04bc69616）后 HEAD 严谨口径：**agent 13 败 + coding-agent 76 败 = 89 败**（85 → 76 = ai 修复连带修好 9 个 catalog 依赖测试；agent 无变化）。
- 超时类测试有 flaky 成分，单次运行 ±2~3 属正常波动。

## 1. 总分类（89 败）

| 类别 | 定义 | agent | coding-agent | 合计 | 占比 |
|---|---|---|---|---|---|
| **B：Windows 环境缺口** | HEAD 与 upstream/main 在 Windows 上**同名同败**；上游 ubuntu CI 绿（见 §4 置信度） | 12 | 46 | **58** | 65% |
| **A'：上游已修（栈滞后）** | HEAD 败而 upstream/main 在 Windows 上过；文件历史证实上游在导入（08-14）后改过对应测试或 src | 1 | 25 | **26** | 29% |
| **A：纯栈引入** | 我方栈自己弄坏（上游无此败且未修过） | 0 | 0 | **0** | 0% |
| 波动/待复核 | 超时类单次运行归属不稳 | — | — | ~5（含于上） | — |

**核心结论：漂移不是本 fork 的提交弄坏的——是「导入快照滞后于上游」+「上游从不跑 Windows CI」两个独立因素叠加。**

## 2. B 类明细（58，Windows 缺口）

agent（12）：`harness/nodejs-env.test.ts` 6（shell env/退出码/进程清理语义）+ `harness/tools.test.ts` bash 6（stdout 合流/超时上报/前缀等）。
coding-agent（46，按文件）：config 7、tools 9、model-registry 6、package-command-paths 3、external-editor 3、resolve-config-value 3、sdk-session-manager 3、interactive-mode-suspend 2、package-manager 2、trust-selector 2、agent-session-dynamic-tools / auth-storage / footer-width / resource-loader / trust-manager / 2791-fswatch 各 1。
典型签名：`expected ['powershell'] to deeply equal ['bash']`（默认 shell 语义）、路径分隔符、fswatch、外部编辑器。

**关键证据**：upstream/main 在同一台 Windows 上跑出 95 败（28 文件），其中含 `bash-close-hang-windows.test.ts`（一个字面命名 Windows 的测试在 Windows 上失败）——上游自己的 Windows 缺口比我们更大，只是 ubuntu CI 永远看不见。

## 3. A' 类明细（26，上游已修）

| 文件（HEAD-only 败数） | 上游修复提交 | 内容 |
|---|---|---|
| model-registry（1） | 744a94d7d 09-04 | use current Copilot model in registry test（同我在 ai 包做的 gpt-4.1→现役修复） |
| agent-session-concurrent（1） | 6160683a4 09-08 | await queue operations in concurrent tests（正是我们的 30s 超时） |
| extensions-runner（8） | acaa253cc 09-09 | validate extension tool parameter schemas |
| suite/agent-session-runtime（6） | 1a773c8e7 09-03 | avoid overwriting imported sessions（套件更新） |
| trust-selector（1） | f2a622789 09-01 | TUI thinking-mode 选择调整 |
| 3592-no-builtin-tools（1） | 80e62761f 08-24 | add optional PowerShell tool #8512（Windows shell 语义） |
| 3302-find-path-glob（1） | aa23e784c 09-07 及更早 | 路径 glob 修复 |
| agent-session-auto-compaction-queue（3）+ 5109-exclude-tools（2） | （测试文件与上游**逐字节相同**） | 上游修在 **src**：快照 src 满足不了相同测试（栈滞后于上游 src 演进） |
| nodejs-env「streams stdout and stderr chunks」（agent 1） | nodejs-env 上游演进 | 同上 |

**修法判断**：逐个镜像这 26 个 = 重复劳动（上游 09-01~09-10 的测试/src 修复面远大于 26 个测试）。**正解是一次性 forward-port 上游**，但栈有 12 个未推送提交 + fork 定制（agent-team-loop 等），同步是独立大动作。

## 4. 置信度注记（Windows 跑 Linux 语义的偏差）

1. 「上游 ubuntu CI 绿」为**高置信假设**（无 gh/token 不可直查）：这些是核心套件，上游 main 长红 62~95 个测试不可信。
2. 同名测试跨树内容可能已漂移（上游改过部分 both-fail 文件）；签名抽查与 Windows 语义一致，未见反例。
3. 超时类（hook 10s / test 30s）在满载 Windows 上本就不稳；本报告单次运行，未做重复采样。
4. worktree 与主工作区共享 HOME（~/.pi 全局扩展等），两树条件一致，横向对比有效。

## 5. 建议表（修/不修）

| 类别 | 建议 | 理由 |
|---|---|---|
| B（58） | **暂不修 + 基线文档化**；仅挑阻塞日常开发的项目单点修 | CI 只跑 ubuntu，修复无 gate 回报；一次性修 58 个 Windows 语义是大工程且随时被上游演进冲掉 |
| A'（26） | **不逐个镜像；规划一次上游 forward-port**（独立 key） | 同步上游顺带修掉这 26 + 未来漂移；镜像成本 > 同步成本 |
| A（0） | 无需动作 | — |

## 6. 用户决策区（已决策，2026-09-10）

- [x] B 类处置：**暂不修 + 基线文档化**（写入 AGENTS.md Commands 节，与测试命令并列）
- [x] A' 类处置：**规划一次上游 forward-port**（独立 key；时机 = 当前 12 提交栈推送合并后；不逐个镜像 26 个）
- [x] 接受「Windows 开发机 89 败（agent 13 + coding-agent 76）」作为基线写入文档

决策依据：B 类 58 个无 gate 回报（CI 只跑 ubuntu）且上游同款缺口会持续冲掉修复；A' 类 26 个的上游修复面远大于镜像面，同步是唯一经济解。
