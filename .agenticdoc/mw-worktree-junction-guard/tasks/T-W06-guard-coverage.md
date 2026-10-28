# T-W06 — G1 端到端覆盖：真实 `tool_call` 链路上的拦截（AC-001/003/004 的注册面）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令；夹具只能在 `%TEMP%` 内造 junction

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— G1 的验收不能停在纯函数层。`design.md` §3.4 的 P-002 判据：**纯判定函数全绿而注册断掉**是已知失效模式，所以必须有一条"真链路"测试。
- **模板（照它写，实测已成熟）**: `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts:1` —— 两层结构：① 纯函数断言；② 真实 `tool_call`：faux provider → Agent loop → `ExtensionRunner.emitToolCall` → 生产 `registerXkeyGateGuard` 注册的 handler → `{block, reason}` → **工具体不执行**（只 stub bash 后端 `BashOperations` 以保 CI 安全）。夹具经 `PI_WORKER_TASK` 指向夹具 `task.md`，使拒绝痕迹落在夹具而非真仓。
- **可复用件**: `packages/coding-agent/test/suite/harness.ts:101`（`createHarness`）、`harness.ts:77`（`Harness` 接口）、`harness.ts:34`（`getMessageText`）。
- **被测面**: `packages/coding-agent/src/extensions/agent-team-loop/index.ts:61`（`activate()` 内 `registerWorktreeJunctionGuard(pi)` 的注册点 —— 在双加载 flag 之后、PM/Worker 分支之前）、`shared/worktree-junction-guard.ts:158`（`registerWorktreeJunctionGuard`）、`worktree-junction-guard.ts:78`（`decideWorktreeRemove`）、`worktree-junction-guard.ts:653`（`notRemove`）、`worktree-junction-guard.ts:721`（`deletePenetrationVerdict`）。
- **注册面的关键要求**: 测试必须走**真实** `activate(pi)`（`index.ts`），**不要**直接调 `registerWorktreeJunctionGuard(pi)` —— 只有走 `activate` 才能证明"注册没断"（直接调用会让测试在注册被删掉时依然全绿）。
- 相关 spec 验收：AC-001（命中即 block）、AC-003（干净目标不误拦）、AC-004（拒绝可观测）。

## 要求

1. 新建 `packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`（vitest + `test/suite/harness.ts` + faux provider；**禁止**真实 provider/key/token）。
2. 夹具（全部 `%TEMP%`，junction 目标必须在夹具内）：
   - `<root>/real/node_modules/`（普通目录 + 一个文件，链目标）；
   - `<root>/wt/node_modules` → `cmd /c mklink /J` 指向 `<root>/real/node_modules`（事故同构：worktree 里有一条指向真树的 junction）；
   - `<root>/clean/`（**无** reparse point 的普通目录，反向对照用）；
   - `<root>/task.md`（`PI_WORKER_TASK` 指向它，用于断言拒绝痕迹）。
3. bash 后端用 `BashOperations` 记录器（照 `xkey-gate-guard-coverage.test.ts` 的 `createGuardHarness`）：记录命令、回 `exitCode 0`、**不真执行**。核心断言 = **`executedBashCommands` 为空**（工具体根本没跑 = 零副作用，这是最强证据）。
4. 用例矩阵（每条都要有 `isError` 与 `executedBashCommands` 双断言）：
   - (a) **事故命令**: faux `bash` 工具调用 `git worktree remove --force "<root>/wt"` ⇒ 结果 `isError === true`，文本含 block 原因与可照抄的 `mw worktree rm "<root>/wt"`，`executedBashCommands` 为空；
   - (b) **两种模式都拦**: 用**同一个** `activate` 注册面，分别测 `PI_WORKER_TASK` 已设（worker 模式）与未设（交互/PM 模式）各一次，都必须 block（这是"三种模式都注册"里能端到端断言的两支）；
   - (c) **删除穿透形态也拦**: `rm -rf "<root>/wt/"` ⇒ block 且 `executedBashCommands` 为空，文本含 `cmd /c rmdir`（D-11 第二套文本）；
   - (d) **反向对照（不得误拦）**: `git worktree remove --force "<root>/clean"` ⇒ `isError === false` 且 `executedBashCommands` 恰为该命令（证明护栏放行时工具确实执行）；
   - (e) **只读/无关命令不拦**: `git worktree list`、`ls "<root>/wt"`、`cat "<root>/real/node_modules/<file>"` ⇒ 均 `isError === false` 且被执行；
   - (f) **痕迹**: block 后 `task.md` 同目录的 `trace.log` 含 `[WORKTREE_GUARD]` 记录（AC-004 可观测）；放行时无该记录。
5. 结束时回收：先 `cmd /c rmdir <link>`（**无 `/S`**）摘链，再 `rmdir /S /Q <root>`；`afterEach` 里 `harness.cleanup()`。
6. `npm run check` 零 error/warning/info；只用可擦除 TS 语法；禁止内联 import。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W06-guard-coverage-20261013.md`：`## 结论`、`## 证据`（六组用例的实测输出：`isError` / `executedBashCommands` / trace 行数、夹具路径与清理命令、`npm run check` 实际输出）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | executedBashCommands(block)=0 | CHECK: <clean|N errors>`。

## 写入允许面

- `packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W06-guard-coverage-20261013.md`（新建）

## 写入禁止面

- **一切生产代码**：`packages/coding-agent/src/**`（含 `shared/worktree-junction-guard.ts`、`index.ts`）、`packages/multi-workers/**`、`scripts/**`。
- 其它测试文件：`test/suite/worktree-junction-guard-decide.test.ts`（W-05/W-05b 的写面）、`test/suite/harness.ts` 及任何既有测试。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove|add|prune`、`rm`、`npm install`；禁止触碰真树 `node_modules` 下的 junction；**禁止对真仓跑任何删除命令**。
- 若发现生产代码有 bug：**不要改**，在报告的「残留与未验证」里写清现象 + `file:line`，交回 PM。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-coverage.test.ts
cd ../..
npm run check
```

（`npm run check` 完整输出，不 tail。）

## 改动历史

报告内逐条列 `file:line` + `git status --porcelain` 的本人改动清单（预期只有两个新文件）。
