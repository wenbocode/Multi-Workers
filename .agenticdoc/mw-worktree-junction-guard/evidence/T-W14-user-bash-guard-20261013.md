# T-W14 user_bash guard — 用户直敲命令通道证据（mw-worktree-junction-guard G6 / AC-014，D-13，审计 N-06）

- 任务卡：`tasks/T-W14-user-bash-guard.md`（card_sha256: 527f4af8cef71d52d496b071830d922d534530c345ab9c86e8b0dd57a74a0605）
- 日期：2026-10-13
- 类型：coding
- 目标锚点：`.agenticdoc/goal.md` — INV-1「含 reparse point 的 worktree 没有任何执行通道能把它连同目标一起删掉」
- 判据链：`spec.md` §2 G6 / **AC-014**、§7 **D-13**；来源 `evidence/negative-space-audit-20261013.md` N-06

## 结论

通过。把 G1 的判定面补到 pi 的用户直敲命令通道（TUI `!`/`!!` + RPC `bash`）：

- `registerWorktreeJunctionGuard`（`shared/worktree-junction-guard.ts:201`）内新增 `pi.on("user_bash")` 挂钩（`:217`），与既有 `pi.on("tool_call")`（`:202`）并列，**同一次注册、同一套 `decideWorktreeRemove` 判定、同一套阻断文本与 `[WORKTREE_GUARD]` trace**。
- `block === true` ⇒ 返回 `{ result: BashResult }`；`block === false` ⇒ 返回 `undefined`（不干预，命令照常执行）。
- **零副作用可证**：4 条 AC-014 用例中，危险形态（字面 + `$env:` 插值）实测 `executed === []`（执行后端一次都没被调用）；反向对照干净目标实测 `executed === [command]`（确实执行）；处方命令 `mw worktree rm "<wt>"` / `cmd /c rmdir "<link>"` 实测 `intercepted === false` 且执行。
- **负对照**：临时把 `user_bash` 事件名改掉（handler 不再被派发）后复跑，危险形态 2 条用例立即失败（`2 failed | 11 passed`），证明新用例不是假绿；随后已还原（`:217` 恢复为 `pi.on("user_bash", ...)`, 见「改动历史」）。
- **未改 `index.ts`**：`registerWorktreeJunctionGuard(pi)` 早在 `index.ts:70`（W-06 引入）就在 PM/Worker 分支之前无条件调用，新增挂钩落在同一注册函数内即对所有模式生效。

验收：`decide 25/25` 无回归，`coverage 13/13`（本卡新增 4 条），`npm run check` 零 error/warning/info（退出码 0）。

## 证据

### 1. API 实测（`node_modules`，非猜测）

pi 的事件契约与本仓库同源（`node_modules/@earendil-works/pi-coding-agent` 是 workspace 软链，`dist/` 为发布产物）。以下坐标均直接来自 `node_modules`。

**(a) 事件名与负载字段** — `node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts:615`：

```ts
/** Fired when user executes a bash command via ! or !! prefix */
export interface UserBashEvent {
    type: "user_bash";
    /** The command to execute */
    command: string;
    /** True if !! prefix was used (excluded from LLM context) */
    excludeFromContext: boolean;
    /** Current working directory */
    cwd: string;
}
```

结论：事件名是 `"user_bash"`；命令串在 `event.command`；**cwd 在 `event.cwd`**（不是 `ctx.cwd`，与 `tool_call` 不同）；`excludeFromContext` 对应 `!!`。所以挂钩用 `event.command` / `event.cwd`。

**(b) 注册签名（类型层面已声明 `user_bash`，不会因事件名类型不合法而编译失败）** — 同文件 `:857`、`:893`：

```ts
export type ExtensionHandler<E, R = undefined> = (event: E, ctx: ExtensionContext) => Promise<R | void> | R | void;
...
on(event: "user_bash", handler: ExtensionHandler<UserBashEvent, UserBashEventResult>): void;
```

**(c) 返回什么算“短路执行”** — 同文件 `:783`：

```ts
/** Result from user_bash event handler */
export interface UserBashEventResult {
    /** Custom operations to use for execution */
    operations?: BashOperations;
    /** Full replacement: extension handled execution, use this result */
    result?: BashResult;
}
```

`BashResult`（`src/core/bash-executor.ts:29`，dist 同源）= `{ output, exitCode, cancelled, truncated, fullOutputPath? }`。

派发侧 `node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/runner.js:720`：

```js
async emitUserBash(event) {
    const ctx = this.createContext();
    for (const ext of this.extensions) {
        const handlers = ext.handlers.get("user_bash");
        ...
                const handlerResult = await handler(event, ctx);
                if (handlerResult) {
                    return handlerResult;
                }
```

即 handler 返回的任意真值整体返回给调用方。

消费侧（两条出口都只看 `eventResult?.result`）：
- TUI：`dist/modes/interactive/interactive-mode.js:5265` `await extensionRunner.emitUserBash({ type: "user_bash", command, excludeFromContext, cwd: this.sessionManager.getCwd() })`；`:5272` `// If extension returned a full result, use it directly` + `if (eventResult?.result) { ... this.session.recordBashResult(command, result, ...); ...; return; }`，`return` 在 `// Normal execution path` **之前**。
- RPC：`dist/modes/rpc/rpc-mode.js:439` 同一事件；`:445` `if (eventResult?.result) { session.recordBashResult(...); return success(id, "bash", eventResult.result); }`，其后才是 `session.executeBash(...)`。

结论：**返回 `{result}` 即整体替换该次执行**，命令体不会被 spawn；返回 `undefined` 走原路径。挂钩据此实现（危险 ⇒ `{result}`，干净 ⇒ `undefined`）。

**(d) `pi.on` 对未知事件名不抛错（故不需要 try/catch 兜底）** — `dist/core/extensions/loader.js:191`：

```js
on(event, handler) {
    runtime.assertActive();
    const list = extension.handlers.get(event) ?? [];
    list.push(handler);
    extension.handlers.set(event, list);
},
```

事件名只是 `Map` 的 key，无白名单校验（`ExtensionAPI` 的 `on` 重载列表含 `user_bash`；`assertActive()` 只检查扩展加载生命周期，与事件名无关）。因此注册 `user_bash` **不会**让扩展加载失败，卡片要求的 try/catch / 事件名探测**不必要**（本仓 `src/core/extensions/loader.ts:243` 与之同构）。

### 2. 三条（实为四条）用例的实测断言输出

夹具复用 `test/suite/worktree-junction-guard-coverage.test.ts` 的既有真链路夹具（`mklink /J` + `%TEMP%`，链目标在夹具内），路径：

| 路径 | 形态 |
| --- | --- |
| `<root>/real/node_modules/` | 普通目录 + `fixture-dep.txt`（链目标） |
| `<root>/wt/node_modules` | `cmd /c mklink /J` → `<root>/real/node_modules`（事故同构） |
| `<root>/clean/` | 无 reparse point 的普通目录（反向对照） |
| `<root>/task.md` | `PI_WORKER_TASK` 指向它（`type: coding`），`[WORKTREE_GUARD]` 痕迹落 `<root>/trace.log` |

`<root>` 实测形如 `C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w06-OZrYyH`。

新增派发辅助 `runUserBash()`（`coverage.test.ts:240`）：走**真实** `harness.session.extensionRunner.emitUserBash(...)`（真实注册的 handler），再按生产代码的短路判据处理 —— `if (eventResult?.result) { recordBashResult; return intercepted }` 否则 `session.executeBash(command, ..., { operations: 记录器 })`。执行后端是 `BashOperations` 记录器（`exec` 把命令 push 进 `executed[]`），故 `executed === []` 就是「命令没有真正执行」的直接证据。

| # | 用例（`coverage.test.ts`） | 形态 | intercepted | executed | `[WORKTREE_GUARD]` 行数 |
| --- | --- | --- | --- | --- | --- |
| 1 | `:439` AC-014 (literal) | `git worktree remove --force "<root>\wt"` | `true` | `[]` | `1` |
| 2 | `:456` AC-014 (interpolation) | `git worktree remove --force "$env:WJG_W14_USER_BASH_WT"`（env 指向 `<root>\wt`） | `true` | `[]` | `1` |
| 3 | `:471` AC-014 (reverse control) | `git worktree remove --force "<root>\clean"` | `false` | `[command]`（确实执行） | `0` |
| 4 | `:483` AC-014 处方 | `mw worktree rm "<root>\wt"` / `cmd /c rmdir "<root>\wt\node_modules"` | `false` / `false` | `[command]` / `[command]` | `0` |

文本断言：用例 1/2 断言 `outcome.output` 含 `[mw-worktree-guard] blocked`，用例 1/2 含可照抄的 `mw worktree rm "<root>\wt"`；用例 4 证明处方命令不被守卫自己吃掉（与 F-06 同精神）。

失败性证明（负对照）：把 `shared/worktree-junction-guard.ts:217` 的事件名临时改成 `"user_bash__negative_control"`（handler 仍注册，但 `emitUserBash` 取不到）后复跑 `coverage.test.ts`：

```
 FAIL  ... > worktree junction guard real user_bash dispatch via activate (AC-014)
        > AC-014 (literal): refuses the accident command on the ! channel, runs nothing, records the trace
 FAIL  ... > AC-014 (interpolation): refuses the accident-shape $env: target on the ! channel, runs nothing
 Test Files  1 failed (1)
      Tests  2 failed | 11 passed (13)
```

危险形态两条随即失败（拦截消失 ⇒ 命令进入执行路径），反向对照/处方两条仍通过（它们本就期望放行）——证明拦截能力确实由本挂钩提供，且放行侧不依赖它。临时改动已还原。

### 3. `[WORKTREE_GUARD]` trace 行（实测）

用一次性探针把用例 1 的 `trace.log` 原文写到 `%TEMP%\wjg-w14-trace-probe.txt` 后读回（探针已移除）：

```
[START] pid=142772
[START] 2026-10-13T23:48:05.301Z task=wjg-w06-OZrYyH type=coding phases=-
[WORKTREE_GUARD] 2026-10-13T23:48:05.304Z blocked tool=user_bash target=C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w06-OZrYyH\wt
```

与既有一致，仅 `tool=user_bash`（`tool_call` 面写 `tool=bash`），由 `recordWorktreeGuardBlockTrace("user_bash", ...)`（`:222`）产生。

### 4. 夹具路径与清理

- 夹具路径：`fs.mkdtempSync(path.join(os.tmpdir(), "wjg-w06-"))`（复用 W-06 的 `createFixture()`，未新增夹具类型）。
- 清理：新增共享 `cleanupHarnessesAndFixtures()`（`coverage.test.ts:200`，`tool_call` describe 与本卡 user_bash describe 共用）——先 `harness.cleanup()`，再 **`cmd /c rmdir <link>`（无 `/S`、无尾分隔符）**，最后 `cmd /c rmdir /S /Q <root>` + `fs.rmSync` 兜底。
- 实测清理后 `%TEMP%\wjg-w06-*` 残留目录数 = `0`（`wjg-tw-*` 属于同轮其它 worker 的 tree-watch 夹具，未触碰）。
- 未对真树执行任何 `git worktree add|remove|prune`、`rm`、`npm install`；未触碰真树 `node_modules` 下的 junction。

### 5. 验收命令实测输出

`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts`（完整输出）：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·····················[worker] start task=wjg-w06-bL8yn5 type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1 tool_errors=1
·········[worker] start task=wjg-w06-NvqbHP type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1 tool_errors=1
·[worker] start task=wjg-w06-xxn879 type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1
·[worker] start task=wjg-w06-ZyrQ1P type=coding phases=-
[worker] done exit=0 elapsed=0s tools=3
·[worker] start task=wjg-w06-bb5tGo type=coding phases=-
·[worker] start task=wjg-w06-MfQbnk type=coding phases=-
·[worker] start task=wjg-w06-5M2bpH type=coding phases=-
·[worker] start task=wjg-w06-ul8oib type=coding phases=-
··

 Test Files  2 passed (2)
      Tests  38 passed (38)
   Start at  07:48:16
   Duration  6.46s (transform 2.02s, setup 0ms, import 2.94s, tests 8.18s, environment 0ms)
```

`--reporter=verbose` 分项确认：`decide` 25 条全绿（无回归），`coverage` 13 条全绿，其中 AC-014 四条：

```
 ✓ ...worktree-junction-guard-coverage.test.ts > ... real user_bash dispatch via activate (AC-014)
     > AC-014 (literal): refuses the accident command on the ! channel, runs nothing, records the trace
     > AC-014 (interpolation): refuses the accident-shape $env: target on the ! channel, runs nothing
     > AC-014 (reverse control): a clean target on the ! channel still runs for real
     > AC-014: the prescribed replacements are not eaten by the guard itself
 Test Files  2 passed (2)
      Tests  38 passed (38)
```

`cd ../..; npm run check`（完整输出）：

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1155 files in 723ms. No fixes applied.

> pi-monorepo@0.0.3 check:pinned-deps
> node scripts/check-pinned-deps.mjs


> pi-monorepo@0.0.3 check:ts-imports
> node scripts/check-ts-relative-imports.mjs


> pi-monorepo@0.0.3 check:shrinkwrap
> node scripts/generate-coding-agent-shrinkwrap.mjs --check

packages/coding-agent/npm-shrinkwrap.json is up to date.

> pi-monorepo@0.0.3 check:install-lock:coding-agent
> node scripts/generate-coding-agent-install-lock.mjs --check

packages/coding-agent/install-lock is up to date.

> pi-monorepo@0.0.3 check:browser-smoke
> node scripts/check-browser-smoke.mjs
```

零 error / warning / info；退出码 `0`。

### 6. 为何不需要改 `index.ts`

`index.ts:70` 已在 PM/Worker 两个分支**之前**无条件调用 `registerWorktreeJunctionGuard(pi)`（W-06 引入，`git diff` 见 `index.ts:62` 的注释块）。本卡只在同一个注册函数体内追加一个 `pi.on("user_bash")`，因此所有模式（含 worker 窗口、PM 主窗口、纯交互窗口）自动获得该通道守卫。`git diff -- index.ts` 中没有任何 T-W14 改动。

## 改动历史

本人改动清单（`git status --porcelain`；前两个文件为 W-05/W-06 新建、尚未 `git add` 的未跟踪文件，本卡在其内部改动，`git diff` 不会展示）：

```
?? packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts   （W-05 建，本卡改）
?? packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts                （W-06 建，本卡改）
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W14-user-bash-guard-20261013.md        （本卡新建）
```

未触碰：`index.ts`、`test/suite/worktree-junction-guard-decide.test.ts`、`test/suite/harness.ts`、其它 `test/suite/**`、`packages/multi-workers/**`、`scripts/**`。

`file:line` before→after：

| 文件 | 位置 | before | after |
| --- | --- | --- | --- |
| `shared/worktree-junction-guard.ts` | `:35-45`（文件头注释） | 只描述 `tool_call`（bash 工具）面 | 追加 AC-014 段：`user_bash` 通道、短路语义、审计 N-06 |
| 同上 | `:186-200`（`registerWorktreeJunctionGuard` 文档） | 只描述 tool_call 面 | 说明两个挂钩并列、只差拒绝形态、`pi.on` 无事件白名单故无需 try/catch |
| 同上 | `:217-233`（函数体末尾） | 函数在 `pi.on("tool_call")` 后直接闭合 | 追加 `pi.on("user_bash", (event) => {...})`：`decideWorktreeRemove(event.command, event.cwd, process.env)` → block 时 `recordWorktreeGuardBlockTrace("user_bash", ...)` + 返回 `{result:{output,exitCode:1,cancelled:false,truncated:false}}`，否则 `undefined` |
| `test/suite/worktree-junction-guard-coverage.test.ts` | `:22-32`（文件头注释） | 两层结构（纯函数 + 真 `tool_call`） | 补第 3 层：AC-014 真 `user_bash` 派发 |
| 同上 | `:137` | — | 新增 `ENV_USER_BASH_TARGET = "WJG_W14_USER_BASH_WT"` + `savedUserBashTarget` |
| 同上 | `:193-223` | `afterEach` 内联清理 | 抽出 `cleanupHarnessesAndFixtures()`（两处 describe 共用），行为不变 |
| 同上 | `:220-262` | — | 新增 `UserBashOutcome` / `runUserBash()`（真实 `emitUserBash` + 生产短路判据 + `BashOperations` 记录器） |
| 同上 | `:307-314`（tool_call describe 的 `afterEach`） | 内联清理体 | 改为 `cleanupHarnessesAndFixtures()` |
| 同上 | `:423-492` | — | 新增 describe「real user_bash dispatch via activate (AC-014)」+ 4 条用例 |

## 残留与未验证

1. **执行后端按设计 stub**：`executed === []` 证明的是「守卫拦下后命令不进入执行路径」，而非 `git worktree remove` 的真实磁盘行为（真树删除被硬约束禁止，属 W-05/事故复现领域）。
2. **TUI/RPC 前半段未端到端驱动**：`runUserBash()` 复刻的是 `handleBashCommand`/RPC `bash` 的**派发 + 短路判据**（真实 `emitUserBash` + 生产代码同一判据 `eventResult?.result`），未实例化 TUI `InteractiveMode` 组件。语义等价性由 `dist/modes/interactive/interactive-mode.js:5265-5291` 与 `dist/modes/rpc/rpc-mode.js:439-451` 的源码坐标支撑。
3. **Windows-only**：junction 依赖 `cmd /c mklink /J`，与 W-05/W-06 同约束，未新增平台分叉。
4. **`opt` 覆盖面**：AC-014 只要求 `git worktree remove|rm` 的插值/字面形态；D-11 删除穿透面（`rm -rf <dir>/`）在 `user_bash` 上同样生效（同判定函数），但本卡未为它单独加 `user_bash` 用例（`tool_call` 面已覆盖，且判定函数单测已覆盖）。若 PM 要求，可后续在 describe 内补一条。
5. **CHANGELOG 未改**：本卡写入允许面不含 `packages/coding-agent/CHANGELOG.md`，且 W-06 亦未记；如需 `[Unreleased]` 条目请 PM/`/cl` 统一处理。
6. 未发现生产代码 bug，无需交回 PM 的 `file:line` 缺陷项。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w14-user-bash-guard/task.md`
- 目标：`.agenticdoc/goal.md`（INV-1）
- 规格：`.agenticdoc/mw-worktree-junction-guard/spec.md` §2 G6（AC-014）、§7 D-13
- 审计：`.agenticdoc/mw-worktree-junction-guard/evidence/negative-space-audit-20261013.md` N-06
- 复用件：`shared/worktree-junction-guard.ts:92` `decideWorktreeRemove`、`:807` `recordWorktreeGuardBlockTrace`、`:201` `registerWorktreeJunctionGuard`；`test/suite/worktree-junction-guard-coverage.test.ts` 的 `createFixture()`/`createGuardHarness()`/`unlinkJunction()`
- API 实测：`node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts:615,783,857,893`；同包 `dist/core/extensions/runner.js:720-746`、`dist/core/extensions/loader.js:191-197`、`dist/modes/interactive/interactive-mode.js:5265-5291`、`dist/modes/rpc/rpc-mode.js:439-451`
- 注册点：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:70`

TESTS: 25/13 | user_bash 用例: 4 | 零副作用证明: 是 | CHECK: clean
