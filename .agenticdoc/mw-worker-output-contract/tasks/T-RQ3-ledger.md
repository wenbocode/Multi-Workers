# T-RQ3: 变更账本与 `[WRITE_FILE]` 的全部消费者（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「PM 编排 + Worker 执行」）。
- 本 key 的 spec：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.5 P4、§1.6 S5、§3 AC-008，以及 §1.7 第 4 条（FW-007 的修法依赖本条先修）。
- 已知起点坐标（**只是起点**）：`packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:116`（`return \`${WRITE_FILE_EVENT} path=${filePath}\``）、`:123`（`appendWriteFileEvent`）、`:135`（`WRITE_FILE_LINE_RE = /^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$/`）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2368-2388`（`tool_execution_end` 里对 `pendingWriteTargets` 与 `pendingBashWrites` 逐条记账）。
- 背景事实（已复核，不要再重复发现）：账本**双向失真**——(a) 误报：`wfg-rq2-enforcement` 落 `path=` + 反引号 + `:1175`、`…:1184`，`wfg-rq3-safety` 落 `, .agenticdoc/_aut + opilot)`（各 2 行），来源是多行 PowerShell here-string（`$py = @' … '@` + `$code | python -`）命令的**正文片段**；(b) 漏报：`wfg-rq1-write-face-sources` 实际写了 50,544 B 的 `evidence/research/*.md`，`[WRITE_FILE]` **0** 行。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。

## 要求

1. **壳层写目标抽取器的实现位置与完整规则**：找到把 bash 命令变成「写目标」的代码，逐条列出**所有** pattern 名与其实际判定（重定向、`tee`、`Set-Content`、`Out-File`、`dd`、`copy`、heredoc… 以代码为准），以及 `verbatim` 标志的计算方式。逐条 `文件:行号` + 原文片段。
2. **伪行的确切产生路径**：用 `wfg-rq2-enforcement` / `wfg-rq3-safety` 的真实命令文本（证据见 `.agenticdoc/mw-write-face-guard/workers/<task>/trace.log` 的 `[TOOL]` / `[WRITE_SCOPE]` / `[WRITE_FILE]` 行）解释为什么会产生 `:1175` 与 `, .agenticdoc/_aut + opilot)` 这类值；若能，给出**最小可复现输入**（命令行或单元级输入字符串）与推导过程。
3. **`[WRITE_FILE]` 与 `unjudgeable` 的全部消费者**：谁解析 trace 的这行（PR 侧 declaration gap / change-ledger 判据 / PM 校验 / doctor / 其他），各自的语义与失败行为（例如「trace 无 `[WRITE_FILE]` 时判 unjudgeable」的判定点在何处）。逐条 `文件:行号`。
4. **`unjudgeable` 的现状语义**：框架里已经存在的 `unjudgeable` 概念（如 `worker-mode.ts:2758` 附近）与 `[WRITE_FILE]` 的关系；如果要新增「解释器写入（python/node heredoc）落 `unjudgeable` 事件」，列出需要改的位置与现有测试是否需要同步。
5. **现有测试清单**：与 change-ledger / `[WRITE_FILE]` / 壳层写面 / 声明缺口相关的测试文件 + 用例名 + 断言要点（vitest 与 pytest 都查）。
6. **形状校验的现实约束**：统计仓库内真实存在的、会被形状校验误伤的路径形态（含空格、`+`、中文、`@`、`~` 等），给出代表性实例（`文件:行号` 或实际路径），供「校验过严」风险的对照使用。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq3-ledger-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。

## 交付格式

- `## 0. 结论先行`（≤6 条）→ `## 1…N` 逐问作答（第 2 问必须给出可复现输入或明确写「无法最小化，理由」）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；未找到写「未找到（命令 + 输出）」；**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`；声明工具与方法边界。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
