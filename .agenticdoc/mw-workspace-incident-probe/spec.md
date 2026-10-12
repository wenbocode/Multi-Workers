# spec — mw-workspace-incident-probe

## 0. Goal Alignment（goal.md）

**对齐**：`.agenticdoc/goal.md` 的核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」；其可行性前提是**共享工作树/依赖环境在并发下不被破坏**。本 key 调查的两起事故（workspace junction 消失、3,531 个已跟踪文件消失又恢复）恰恰是这一前提的反例：多窗口并发时，一个窗口的动作可以让其他窗口无法启动 pi、并静默丢弃他人未提交的改动。**不查清机制，框架的并行承诺就是不可信的。**

**预期收益**：
1. 拿到两起事故的**可复算根因**（命令原文 + 时刻 + 执行者会话），把"大概是并发"变成"就是这条命令"。
2. 为后续（**不在本 key 实施**）的防护规则提供事实依据：worktree/junction 的删除语义、ref 级强制操作对共享树的影响面。
3. 给受影响 key 的 PM 一份**可复核的损失清单**（哪些未提交改动被丢弃 / 哪些"复验行"可能是假声明）。

## 1. 范围

只调查、**零改动**。唯一允许写入的是本 key 的 `evidence/**`。不修改代码、文档、配置、`_index.parallel`、`_autopilot/**`；不建/删 worktree；不执行任何破坏性 git 命令。

### 1.1 IN-1 workspace junction 消失（约本地 20:14–20:40）
根 `node_modules/@earendil-works/` 下 9 个 workspace junction 消失（仅 `pi-tui` 保留，mtime 仍 8/10），`pi` 启动报 `ERR_MODULE_NOT_FOUND: @earendil-works/pi-ai`。
**已排除**：npm 未被调用（`npm-cache\_logs` 17:00–20:41 为 0 条）；node_modules 未整体重装（230 包完好，mtime 8/10）；mw 源码无删链代码（`is_junction` 仅在 `mw.py:4561`/`mw_common.py:3220` docstring）。

### 1.2 IN-2 3,531 个已跟踪文件消失又恢复（约本地 20:32:22–20:38）
9 个包下 3,531 个已跟踪文件先消失后全部恢复；`HEAD` 未变（`10446aefb`），对象完好；期间**未提交改动被丢弃**（`shared/mw-runner.ts` 的 1 行 diff 消失；`agent-team-loop-ack.test.ts` 实测 `console.log`×1、`process.stdout.write`×0，而某 key 的 12:13:31Z 复验行声称已改）。

## 2. 验收标准

- **AC-001** IN-1：给出**删掉真实 junction 的那条已执行命令原文**（toolCall `arguments.command`），并附精确时刻（本地+UTC）与来源 jsonl 文件名+行号。
- **AC-002** IN-1：识别执行者会话（session 文件名 + cwd slug）及所属 key/窗口。
- **AC-003** IN-1：解释机制 —— 为何「只删链接、包目录完好」，说明所用删除工具对 junction 的语义（穿透 vs 不穿透），并给出可复现的最小验证（可在临时目录做，不得碰真树）。
- **AC-004** IN-1：清点同日全部 worktree（`%TEMP%\mw-t23-wt`、`qg-head`、`.tmp-t09-wt`、`.tmp/t13-worktree` 等）：谁建、谁清、是否用 junction 指回真树。
- **AC-005** IN-2：给出造成「已跟踪文件消失」的**已执行命令原文** + 执行者会话 + 精确时刻。
- **AC-006** IN-2：解释机制 —— 为何同时满足「文件级消失+恢复」「未提交改动被丢弃」「HEAD 不变」三个约束；并列出现在能解释该组合的候选命令及排除依据。
- **AC-007** IN-2：对 `agent-team-loop-ack.test.ts` 给出**两可能性的一手证据**：(a) 改动确曾被写入后被丢弃（找当时的写入 toolCall/输出），(b) 该复验行本身是假声明（无写入痕迹）。**不得替它定性**，证据不足就写"未坐实"。
- **AC-008** 汇总：判定两起事故是否同源（同一会话/同一命令族）；每起事故列出**未坐实项清单**；给出防护建议（**只建议不实施**）。

## 3. 证据源（只读）

1. `C:\Users\wenbozhou\.pi\agent\sessions\<cwd-slug>\*2026-10-09*.jsonl` —— **只取已执行的 toolCall 参数**，与思考文本严格区分。
2. `.tmp/**` 脚本/日志 mtime；`%LOCALAPPDATA%\npm-cache\_logs\*`。
3. `git worktree list` / `git reflog` / `git log -g` / `git fsck`（只读）。
4. 各 key 的 `pm-state.md` / `workers/**/{trace.log,report.md}`；当前工作树状态。

## 4. 约束

- 只读；不执行 `checkout`/`reset`/`stash`/`clean`/`worktree remove`。
- 命令级结论必须给"原文 + 时刻 + 会话文件"；推算值不得当实测；未坐实项显式列出。
- 两个 worker 各写唯一一个 evidence 文件，互不重叠（无文件冲突）。

## 5. 交付物

`evidence/in1-junction-incident-20261009.md`、`evidence/in2-file-vanish-incident-20261009.md`、`evidence/incidents-timeline-20261009.md`（PM 汇总：合并时间线 + 同源性判定 + 未坐实清单 + 建议）。
