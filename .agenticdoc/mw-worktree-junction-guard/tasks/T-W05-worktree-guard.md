# T-W05 — G1：`git worktree remove` 执行前拦截（AC-001/002/003）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令；夹具只能在 `%TEMP%` 内造 junction

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 「常驻 mw 服务 + 多 Worker 并行开发同一项目」的前提是共享工作树不被破坏。本任务把「危险路径不可达」做成**第一道机械保证**：执行前拦截，不依赖 agent 自觉。
- **事故命令原文（2026-10-09，事故族已坐实）**: `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"` —— 目标**不是字面路径**（环境变量插值），删掉 3,456 个已跟踪文件。出处 `mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` v3 §1/§2。
- **设计契约（唯一事实源，实现前通读）**: `design.md` §3.1 落点、§3.2 接口、§3.3 判定流水线与规则表 + 扫描约束 6 条、§3.5 边界（D-4）、§4.3 block 文案模板、§9 的 AC-003 矩阵。**逐字实现，不要自行发挥。**
- **已落地的解析底座（W-01 完成，直接 import）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts:106`（`parseBashSegments`，已导出；`BashSegment` 在 `bash-segments.ts:18`）。已实测：把引号剥掉、**插值不展开**取回 `$env:TEMP\qg-head` 原样 token。
- **可复用资产（禁止重新发明）**:
  - 注册点与形状：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:42`/`:49`/`:59`（三个既有 guard 的注册位置，双加载 flag 之后、PM/Worker 分支之前 ⇒ 三种模式全覆盖）；`shared/protected-config.ts:249` 的 handler 形状与 `protected-config.ts:224` 的审计写法；
  - hook 能力（已复核）：`event.input.command` 是**原字符串**（`core/tools/bash.ts` schema 无 transform）；`ctx.cwd` 可用（`core/extensions/types.ts:307`、`core/extensions/runner.ts:309`）；handler 内**同步** fs 无超时包装（`core/extensions/runner.ts:940`）⇒ 必须自带 entry 预算；`{block:true,reason}` ⇒ 工具不执行（`packages/agent/src/agent-loop.ts:619`）；handler 抛异常同样不执行（`core/extensions/runner.ts:932`）；
  - 已有先例可抄：`shared/xkey-gate-guard.ts:255`（同类文本判定 guard 的完整骨架）。
- 相关 spec 验收：AC-001（命中即 block，以零副作用证明）、AC-002（报错文本含链接路径 + 目标 + 可照抄的 `mw worktree rm <path>`）、AC-003（干净 worktree 零副作用放行 + 反向对照）。

## 要求

1. 新建 `shared/worktree-junction-guard.ts`，导出 `design.md` §3.2 的三个符号（`WorktreeGuardVerdict` / `decideWorktreeRemove(command, cwd, env)` / `registerWorktreeJunctionGuard(pi)`），`basis` 取值域照设计固定（`resolved | unresolved:<var> | glob | bare-name-ambiguous | reparse-point | target-absent | scan-error:<code> | not-remove`）。
2. 判定流水线照 §3.3 实现**全部四条规则**：(a) 字面路径 `resolve` 后扫描；(b) 插值 `$env:N`/`${N}`/`$N`/`%N%` 全拼写展开（大小写不敏感）+ 命令内前置赋值，**任一变量查不到 ⇒ block**；(c) 含通配 `* ? [`、命令替换或**尾分隔符** ⇒ block（尾分隔符形态是真实穿透通道）；(d) 裸名必须查 `git worktree list --porcelain` 唯一匹配，无匹配 ⇒ allow、歧义/不可读 ⇒ block。基准目录 = `-C` 参数 > 命令内 `cd`/`Set-Location` > `ctx.cwd`。
3. 扫描器严格照 §3.3 的 6 条约束：`readdirSync(dir,{withFileTypes:true})` + 显式栈（**禁** `recursive:true`）；`lstatSync(...).isSymbolicLink()` 命中判定（断裂链也算）；entry 预算 20 万条超限 ⇒ block；顶层目标不存在 ⇒ allow；权限/竞态/枚举失败 ⇒ block；命中 reparse point 后**不下钻**。
4. **禁止**复用 `extractBashWriteCandidates`（`worker/worker-mode.ts:1044` 只认 4 个路径参数且对非字面路径 fail-open）；**禁止**扩展 `checkBashWriteTarget` / `WRITE_VERBS`（§3.5 第 4 条）；判定必须建立在 `parseBashSegments` 的**结构化分段**上，不按词表宽匹配（§3.3 第 6 条的 `dd` 误拦反例）。
5. **边界照 D-4**：覆盖 `git worktree remove|rm`（含 `--force`/`-C`/`cd` 基准）与**同一目标树**上的 `<path>/`、`<path>/*` 穿透形态；**不**扩大动词集（`rm -rf <link>` 无尾分隔符、`rmdir /S`、`robocopy /MIR` 明确不覆盖）。
6. 注册到 `index.ts` 的既有 guard 位置（三种模式全覆盖）；block 文案**逐字照** `design.md` §4.3 模板（含 `<worktree>`、reparse point 数量与示例 `<link> -> <target>`、结尾 `  mw worktree rm "<worktree>"` 一行）；审计/trace 照 `shared/protected-config.ts:224`。
7. 新建 `test/suite/worktree-junction-guard-decide.test.ts`（纯函数矩阵，`%TEMP%` 夹具）：事故形态（插值 + 命中 junction）⇒ block；干净字面路径 worktree ⇒ allow；可解析插值 + 干净 ⇒ allow；未知变量 ⇒ block；通配/尾分隔符 ⇒ block；裸名歧义 ⇒ block；目标不存在 ⇒ allow；非 `worktree remove` 命令 ⇒ allow。夹具 junction 用 `cmd /c mklink /J <link> <target>`（**目标必须在夹具内**）。
8. `npm run check` 必须零 error/warning/info；只用可擦除 TS 语法；禁止内联 import。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W05-worktree-junction-guard-20261013.md`：`## 结论`、`## 证据`（判定矩阵实测输出、事故命令的 `basis` 与 `hits`、夹具路径与清理命令、`npm run check` 实际输出）、`## 改动历史`、`## 残留与未验证`（含 entry 预算实测取值）、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | CHECK: <clean|N errors> | 预算: <实测 entry 数>`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`（只加注册调用）
- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W05-worktree-junction-guard-20261013.md`（新建）

## 写入禁止面

- `shared/bash-segments.ts`、`shared/implementation-gate.ts`（W-01 已落地，冻结）、`shared/protected-config.ts`、`shared/xkey-gate-guard.ts`、`shared/pm-state-guard.ts`、`worker/**`、`packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`（W-06 的写面）、任何 `packages/multi-workers/**`、`scripts/**`。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove`、`rm`、`npm install`；禁止触碰真树 `H:\git\Multi-Workers\node_modules` 下的任何 junction；**禁止对真仓跑 `git worktree remove`**。
- 夹具硬约束：`mklink /J` 的目标必须在 `%TEMP%` 夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）后 `rmdir /S /Q <root>`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts
cd ../..
npm run check
```

（`npm run check` 要完整输出，不 tail。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单（证明只动允许面内文件）。
