# T-W05b — G1 补齐：`rm`/`Remove-Item` + 尾分隔符/通配形态（D-4 第 2 条，决策 D-11）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令；夹具只能在 `%TEMP%` 内造 junction

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— G1 的目标是「危险路径**不可达**」。首轮实现只覆盖了 `git worktree remove|rm` 通道；RQ-1 已坐实**尾分隔符/通配**形态会让"不穿透的 API"变成穿透的（`<link>/`、`<link>/*` 穿透 **1 层**，`Remove-Item … <link>\*` 同理）。
- **为什么现在补（PM 的写卡错误，不是 worker 的）**: `design.md` §3.5 的 D-4 第 2 条**本已要求**覆盖 `rm -rf`/`Remove-Item -Recurse` 的尾分隔符/通配形态；W-05 卡片把它错归入"不扩大动词集"（把第 3 条的要求错按到第 2 条上），首轮实现因此在 `parseGitInvocation` 未命中时直接走 `notRemove()`（放行）。W-05 报告已把这条显式标为残留。设计已更正并记为决策 **D-11**。
- **现状锚点（首轮实现，实测）**：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:303`（`parseGitInvocation`：git 通道识别）；
  - `worktree-junction-guard.ts:539`（`notRemove()`：一切非 git 通道的"放行"出口）；
  - 可复用件：`worktree-junction-guard.ts:190`（`scanTree`，显式栈 + 预算 + `lstat.isSymbolicLink()`）、`worktree-junction-guard.ts:232`（`scanVerdict`）、`worktree-junction-guard.ts:514`（`hasGlobOrSubstitution`）、`worktree-junction-guard.ts:518`（`hasTrailingSeparator`）、`worktree-junction-guard.ts:544`（`reparsePointVerdict`，§4.3 模板）、`worktree-junction-guard.ts:453`（`expandToken`，插值展开）。
  - 导出接口不变：`worktree-junction-guard.ts:78`（`decideWorktreeRemove(command, cwd, env)`）与 `:158`（`registerWorktreeJunctionGuard(pi)`）。
- 相关 spec 验收：AC-001/003（命中即 block / 干净目标不误拦）+ AC-002 的扩展句（决策 D-11）。

## 要求

1. **动词面只扩到有实测穿透证据的三类**：`rm`（含 `-r`/`-rf`/`-f`）与 `Remove-Item`（含 `-Recurse`/`-Force`），**且操作数带尾分隔符或含 `* ? [`**。其它动词（`rmdir /S`、`robocopy /MIR`、无尾分隔符的 `rm -rf <link>`）**保持放行**（D-4 第 3 条不变）。
2. 命中后走**同一**流水线：操作数解析（沿用 `-C`/`cd`/`Set-Location`/`cwd` 基准与 D-3 的插值展开；未知变量 ⇒ block）→ `scanTree` 扫描 → 有 reparse point ⇒ block、无 ⇒ allow、目标不存在 ⇒ allow、枚举失败/超预算 ⇒ block。
3. **两套 block 文本（AC-002 扩展）**：
   - 目标是**已注册 worktree**（`git worktree list --porcelain` 能唯一匹配）⇒ 沿用 §4.3 模板（结尾 `  mw worktree rm "<worktree>"`）；
   - **其它目标** ⇒ 第二套文本：说明"该删除形态会穿透 reparse point"，**列出命中的链与目标**（≤3 条 + 总数），并给出**可照抄**的处方 —— 逐条 `cmd /c rmdir "<link>"`（无 `/S`、无尾分隔符），然后再重试原删除。
4. 两套文本都必须保持**单行 `reason` 内可照抄**（现有 guard 的机器判据落在 `reason` 文本上），且 `basis` 取值域扩展一个可区分值（例如 `delete-penetration`），`hits` 语义不变。
5. 扩展 `test/suite/worktree-junction-guard-decide.test.ts`（同一文件，追加用例；**不要**新建第二个 decide 测试文件）：
   - `rm -rf <fixture-dir-with-junction>/` ⇒ block；`rm -rf "<dir>/*"` ⇒ block；`Remove-Item -Recurse -Force "<dir>\*"` ⇒ block；`rm -rf <worktree-with-junction>/` ⇒ block 且文本含 `mw worktree rm`；
   - 反向对照（**不得误拦**）：`rm -rf <dir>`（无尾分隔符、无通配）⇒ allow；`rm -rf <clean-dir>/` ⇒ allow；`rm -rf <dir>/` 其中 dir 只有普通目录/文件 ⇒ allow；`ls <dir>/` ⇒ allow；`rmdir /S /Q <dir>` ⇒ allow（D-4 第 3 条）；
   - 回归：既有 16 例全绿（git 通道行为逐字不变）。
6. `npm run check` 零 error/warning/info；只用可擦除 TS 语法；禁止内联 import。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W05b-delete-penetration-20261013.md`：`## 结论`、`## 证据`（新增 6 例 block + 5 例 allow 的实测输出与 `basis`、两套 block 文本原文、夹具路径与清理命令、`npm run check` 实际输出）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | CHECK: <clean|N errors> | 新动词面: <列出>`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`
- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W05b-delete-penetration-20261013.md`（新建）

## 写入禁止面

- `…/agent-team-loop/index.ts`（注册点无需改动）、`shared/bash-segments.ts`、`shared/implementation-gate.ts`、`shared/protected-config.ts`、`shared/xkey-gate-guard.ts`、`worker/**`、`test/suite/worktree-junction-guard-coverage.test.ts`（W-06 的写面）、任何 `packages/multi-workers/**`、`scripts/**`。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove`、`rm`、`npm install`；禁止触碰真树 `node_modules` 下的 junction；**禁止对真仓跑任何删除/移除命令**。
- 夹具硬约束：`cmd /c mklink /J` 的目标必须在 `%TEMP%` 夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts
cd ../..
npm run check
```

（`npm run check` 完整输出，不 tail。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
