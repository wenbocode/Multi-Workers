# 调研声明 — spec 期（零新增外部调研）

- **日期**：2026-10-09
- **key**：mw-workspace-incident-probe

## 声明

本 key 为**事故取证**（只调查、零改动），不再引入外部文献调研。事实基线全部来自**本地一手证据**，且其中相当一部分已由 PM 在本轮实测：

| 已实测事实 | 取证方式 | 结果 |
|---|---|---|
| npm 未被调用 | `%LOCALAPPDATA%\npm-cache\_logs` 按 mtime 过滤 17:00–20:41 | **0 条** |
| node_modules 未整体重装 | 目录数 + 最老 mtime | 230 个包；最老 mtime 2026/8/10 |
| 仅链接消失 | 对比 `pi-tui`（存，mtime 8/10）与其余 9 个（缺） | 差异确凿 |
| mw 源码无删链代码 | `Select-String is_junction\|is_symlink` | 仅 2 处 docstring（`mw.py:4561`、`mw_common.py:3220`） |
| worktree+junction 曾被建立 | 会话 jsonl 的 toolCall 原文 + `mklink /J` 回显 | junction → `H:\git\Multi-Workers\node_modules` |
| worktree 现已被清理 | `git worktree list` | 只剩主树 |
| IN-2 副作用真实存在 | `ack.test.ts` 内容计数、`mw-runner.ts` diff | `console.log`×1 / `process.stdout.write`×0；无 diff |

## 未解的调研问题（交给本 key 的 worker）

- **RQ-1**（对应 AC-001..AC-004）：删掉真实 junction 的**已执行命令**是哪一条？由哪个会话、什么时刻？
- **RQ-2**（对应 AC-005..AC-007）：造成 3,531 个已跟踪文件消失又恢复的**已执行命令**是哪一条？`ack.test.ts` 是"丢弃"还是"假声明"？

两问的证据源均为 `C:\Users\wenbozhou\.pi\agent\sessions\**\*2026-10-09*.jsonl` 的**已执行 toolCall 参数**（须与思考文本严格区分），辅以 `.tmp/**` mtime、npm 日志、只读 git 命令。
