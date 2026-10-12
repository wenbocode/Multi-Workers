# mini-spec — mw-workspace-incident-probe

## 目标（只调查，不改动任何东西）

查清 **2026-10-09 同一天、同一共享工作树（`H:\git\Multi-Workers`）上发生的两起独立事故**的根因、执行者与机制，产出可复算的取证记录。**本 key 不产生任何生产代码/文档改动**（唯一允许写的是本 key 自己的 `evidence/**`）。

## 两起事故（各自独立调查）

### IN-1 — workspace junction 消失（约本地 20:14–20:40）
- 现象：根 `node_modules/@earendil-works/` 下 9 个 workspace junction 消失，仅 `pi-tui` 保留（其 mtime 仍是 8/10）；`npm install --ignore-scripts` 后恢复，lockfile 未变；`pi` 启动报 `ERR_MODULE_NOT_FOUND: @earendil-works/pi-ai`。
- 已排除：**不是 npm**（`%LOCALAPPDATA%\npm-cache\_logs` 在 17:00–20:41 为 0 条）；**不是整树重装**（230 个包完好，mtime 8/10）；**不是 mw 源码**（`is_junction` 仅出现在 `mw.py:4561`、`mw_common.py:3220` 的 docstring）。
- 已知线索：20:16–20:17 有会话在 `%TEMP%\mw-t23-wt` 建 worktree 并 `cmd /c mklink /J "$wt\node_modules" "H:\git\Multi-Workers\node_modules"`；`git worktree list` 现在只剩主树 ⇒ worktree 已被清理。
- 待答：**哪一条清理命令穿透了 junction**、由哪个会话在什么时刻执行、为何只删掉链接而未删掉包目录。

### IN-2 — 3,531 个已跟踪文件消失又恢复（约本地 20:32:22–20:38）
- 现象（另一窗口观测，只读 `git status`/`git diff`）：9 个包下 `3,531` 个已跟踪文件先消失、后全部恢复；`HEAD` 未变（`10446aefb`），git 对象完好。
- 副作用：**该时段共享树上的未提交改动被丢弃** —— `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts` 原有 1 行 diff 现已消失；`packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts` 仍是 `console.log`（实测 `console.log`×1、`process.stdout.write`×0），而某 key 的 `12:13:31Z` 复验行声称已改为 `process.stdout.write`。
- 已知线索：`mw.py` 的 `--force` 路径会执行 `git reset --hard`（help 文本："git reset --hard to the remote branch, or replace a non-git cache"）。
- 待答：**是哪一条已执行的命令**（`checkout -f` / `switch` / `reset --hard <ref>` / `worktree remove --force` / 其他）造成"文件级消失再恢复 + 丢弃未提交改动 + HEAD 不变"；执行者会话与时刻；以及 `ack.test.ts` 那处**到底是"改动被丢弃"还是"该复验行本身是假声明"**（两者都必须给出证据，不得替它定性）。

## 证据源（只读）

1. pi 会话记录：`C:\Users\wenbozhou\.pi\agent\sessions\<cwd-slug>\*.jsonl` —— **必须只取已执行的 toolCall 参数**（`name=bash` 的 `arguments.command`），与"思考/讨论"文本严格区分。
2. `.tmp/**` 脚本与日志的 mtime（现场时间线）。
3. `%LOCALAPPDATA%\npm-cache\_logs\*`（npm 调用史）。
4. `git worktree list` / `git reflog` / `git fsck`（对象完好性）/ `git log -g`。
5. 各 key 的 `pm-state.md` / `workers/**/trace.log` / `report.md`。
6. 当前工作树残留状态（`git status --porcelain`、关键文件内容）。

## 约束

- **只读**：不改任何代码、文档、配置、`_index.parallel`、`_autopilot/**`；不建/删 worktree；不执行任何破坏性 git 命令（含 `checkout`/`reset`/`stash`/`clean`）。
- 结论**必须**给到：命令原文 + 精确时刻 + 会话文件名；**不得把推算值当实测**。
- 未坐实的部分必须**显式列为未坐实**，禁止用"大概/应该是"补洞。
- 两个 worker 各写**唯一一个** evidence 文件，互不重叠。

## 产出

| 文件 | 内容 |
|---|---|
| `evidence/in1-junction-incident-<date>.md` | IN-1 的时间线（时刻/会话/命令原文/后果）+ 机制解释 + 未坐实清单 |
| `evidence/in2-file-vanish-incident-<date>.md` | IN-2 同上 |
| `evidence/incidents-timeline-<date>.md` | PM 汇总：两起事件合并时间线 + 交叉影响（是否同一会话/同一命令族）+ 结论与建议（**只建议不实施**） |

## 完成判据

每起事故都要回答：(a) 直接动作原文 (b) 执行者会话 (c) 时刻 (d) 机制（为何产生这个后果）(e) 未坐实项显式列表。两起都答全 ⇒ 本 key 可收口（无代码改动，故不涉 dist/changelog）。
