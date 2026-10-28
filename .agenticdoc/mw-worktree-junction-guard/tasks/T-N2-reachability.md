# T-N2 — 必要性调研 RQ-N2：危险路径今天是否仍可达（端到端）

- type: research
- key: mw-worktree-junction-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq2-reachability-20261013.md`
- 角色约束: 只读（对真树）。允许 read/find/grep/ls/bash 与在 `%TEMP%` 内建夹具；**禁止**碰真树 `H:\git\Multi-Workers` 的 junction/`node_modules`、禁止在真树建/删 worktree、禁止 `checkout`/`reset`/`clean`/`stash`、禁止对真树跑 `git worktree remove`。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`。
- 要回答的总问题：**今天用当前 HEAD 的守卫栈，一个 agent（PM 或 worker 模式）执行 `git worktree remove --force <含 reparse point 的 worktree>` 还能不能得手**；若已被拦，是谁拦的（这直接决定 G1 是否需要做）。
- 已坐实事实（可引用，但必须自己复看确认）：
  - guard 拦截语义：`core/extensions/runner.ts:932-950` 多 handler 顺序 `await`，首个 `block` 立即 return；`packages/agent/src/agent-loop.ts:619-645` `block` ⇒ `kind:"immediate"`（工具不执行）。
  - 现有写动词集不含 `git worktree remove`：`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:79`。
  - TS 端到端范式（faux provider + `BashOperations` 记录器）：`packages/coding-agent/test/suite/harness.ts`、`packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts:121-131`。
  - 穿刺仍成立（本机 git 2.53.0.windows.1）：`…/evidence/research/design-observability-and-verification-20261013.md` 的 AC-012 阳性对照（`git worktree remove --force` 删掉假真树的 5/6 tracked 与 3 条链）。
- 允许并鼓励自行扩大取证范围；夹具**只能**建在 `%TEMP%` 下且链接目标必须**在夹具内**。

## 要求

1. **阳性对照（穿刺是否仍在）**：`%TEMP%` 内建"假真树 A + worktree B + `B\node_modules -> A\node_modules` 链"，直接用 git 执行 `git -C A worktree remove --force B`，给出 rc/耗时/A 侧 tracked 与链清单的 before-after。**只在夹具里做**。
2. **守卫栈可达性（关键）**：用当前 HEAD 的代码路径判断/实测「agent 通过 bash 工具执行同一命令」会不会被拦：
   - 至少覆盖：`implementation-gate`（`gateDecision`）、`protected-config`、worker 模式 write-scope、以及 `mw` 侧 launcher 的 `write_scope` 检查；
   - 给出每条门的输入（toolName/args/cwd）与判定结果，注明是**实测**（跑 harness/脚本，脚本写在 `%TEMP%`）还是**静态推导**（读代码给 `文件:行号`）；
   - 若实测：给出命令原文与原始输出；结论必须明确写成"今天**能**得手 / 今天**不能**得手（被 X 拦下，`文件:行号`）"。
3. **其它删除通道的现状**：对同一夹具，`rm -rf <B>`、`Remove-Item -Recurse -Force <B>`、`cmd /c rmdir /S /Q <B>`、`rm -rf <B>/`（尾分隔符）是否仍穿透（RQ-1 期的结论今天是否仍成立）——这一项决定 G1 的边界（design 决策 D-4）。
4. 只读真树；唯一允许写入的是本卡声明的证据文件（脚本/夹具只放 `%TEMP%`，收尾删除）。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq2-reachability-20261013.md`（结论先行 + 原始命令/输出片段 + 计数 + 上下文来源 + 残留与未验证 + 未覆盖面声明）
- 必须给"今天可达性"的一句话判定，并与"G1 是否仍需要做"的结论挂钩。
