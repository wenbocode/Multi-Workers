# T-W06 guard coverage — 端到端覆盖证据（mw-worktree-junction-guard G1）

- 任务卡：`tasks/T-W06-guard-coverage.md`（card_sha256: da09ff424292e0b200203b43878969d7674b53664104febc24e64587ccde6184）
- 日期：2026-10-13
- 类型：coding
- 目标锚点：`.agenticdoc/goal.md`；判据链：`design.md` §3.4 P-002（纯判定函数全绿而注册断掉的已知失效模式）

## 结论

通过。新建 `packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`，两层结构成立：

1. 纯函数层：`decideWorktreeRemove` 在 `%TEMP%` 夹具上命中 `reparse-point` / `delete-penetration` / `resolved` / `not-remove` 四条判据。
2. 真链路层：faux provider → Agent loop → `ExtensionRunner.emitToolCall` → **真实 `activate(pi)`（`index.ts:70`）注册的 handler** → `{block, reason}` → 工具体不执行。工具体用 `BashOperations` 记录器 stub，不真执行。

P-002 的靶心成立：断言走 `activate(pi)` 而不是直接调 `registerWorktreeJunctionGuard(pi)`；若 `index.ts` 中的注册点被删除，block 用例会因工具被执行而失败（`executedBashCommands` 非空 + `isError === false`），不会假绿。

六组用例全部通过，block 组 `executedBashCommands` 全为 0（零副作用），reverse-control 组工具确实执行（`executed=1` / `executed=3`）。守卫在 worker 模式与 PM/交互模式两种注册分支下都生效。

## 证据

### 夹具（全部位于 `%TEMP%`，junction 目标在夹具内）

| 路径 | 形态 |
| --- | --- |
| `<root>/real/node_modules/` | 普通目录 + `fixture-dep.txt`（链目标） |
| `<root>/wt/node_modules` | `cmd /c mklink /J` → `<root>/real/node_modules`（事故同构） |
| `<root>/clean/` | 无 reparse point 的普通目录（反向对照） |
| `<root>/task.md` | `PI_WORKER_TASK` 指向它，`type: coding`（拒绝痕迹落此目录） |
| `<root>/trace.log` | 守卫 `[WORKTREE_GUARD]` 痕迹；worker 模式另有 `[START]/[HEADER]/[TOOL]` 行 |

`<root>` = `fs.mkdtempSync(path.join(os.tmpdir(), "wjg-w06-"))`，实测形如 `C:\Users\<user>\AppData\Local\Temp\wjg-w06-XXXXXX`。

清理（`afterEach`，顺序固定）：

```
cmd /c rmdir <root>\wt\node_modules        # 摘链：无 /S、无尾分隔符
cmd /c rmdir /S /Q <root>                  # 再删夹具根
harness.cleanup()                          # 每个 harness 均调用
```

实测清理后 `%TEMP%\wjg-w06-*` 残留目录数 = 0。

### 六组用例实测输出

用临时插桩（仅打印 `isError` / `executedBashCommands.length` / `[WORKTREE_GUARD]` 行数，断言不变）跑出的实测值；插桩已移除，最终文件以标准断言复跑通过。

| 组 | 用例 | isError | executedBashCommands | trace `[WORKTREE_GUARD]` 行数 |
| --- | --- | --- | --- | --- |
| (a) | worker 模式 `git worktree remove --force "<root>/wt"` | `true` | `0`（工具体未跑） | `1` |
| (b) | PM/交互模式（`PI_WORKER_TASK` 未设）同一命令 | `true` | `0` | 不适用（无 task 上下文，痕迹函数 no-op） |
| (c) | `rm -rf "<root>/wt/"`（D-11 删除穿透形态） | `true` | `0` | `1` |
| (d) | 反向对照 `git worktree remove --force "<root>/clean"` | `false` | `1`（恰为该命令） | `0` |
| (e) | 只读/无关 `git worktree list`、`ls "<root>/wt"`、`cat "<root>/real/node_modules/fixture-dep.txt"` | `false,false,false` | `3`（三条均执行） | `0` |
| (f) | 痕迹（AC-004）：block 后 `trace.log` 含 `[WORKTREE_GUARD]`（组 (a)/(c)）；放行时无该记录（组 (d)/(e)） | — | — | 见上 |

文本断言（防“拦了但不是这个守卫”）：

- (a)/(b)：结果文本含 `[mw-worktree-guard] blocked`，且 (a) 含可照抄的 `mw worktree rm "<root>/wt"`。
- (c)：结果文本含 `穿透 reparse point` 与 `cmd /c rmdir "<root>/wt\node_modules"`（D-11 第二套文本）。
- (a) 额外断言 `trace.log` 含 `[WORKTREE_GUARD]` 与 `blocked tool=bash`。

插桩 run 的实测原始行：

```
WJG_W06_EVIDENCE a-worker-accident isError=true executed=0 traceLines=1
WJG_W06_EVIDENCE b-pm-accident isError=true executed=0
WJG_W06_EVIDENCE c-rm-penetration isError=true executed=0 traceLines=1
WJG_W06_EVIDENCE d-clean-allow isError=false executed=1 traceLines=0
WJG_W06_EVIDENCE e-readonly-allow isError=false,false,false executed=3 traceLines=0
```

### 验收命令实测输出

`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-coverage.test.ts`（最终文件，无插桩）：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

····[worker] start task=wjg-w06-cYC2it type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1 tool_errors=1
·[worker] start task=wjg-w06-9IJv10 type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1 tool_errors=1
·[worker] start task=wjg-w06-CGZZgG type=coding phases=-
[worker] done exit=0 elapsed=0s tools=1
·[worker] start task=wjg-w06-9rrZP5 type=coding phases=-
[worker] done exit=0 elapsed=0s tools=3
··

 Test Files  1 passed (1)
      Tests  9 passed (9)
   Start at  00:15:33
   Duration  4.18s (transform 1.80s, setup 0ms, import 2.63s, tests 1.45s, environment 0ms)
```

（9 = 4 条纯函数 + 5 条真链路；`tools=N tool_errors=M` 的 worker 日志逐条对应 block/allow，block 组 tool_errors=1。）

`cd ../.. && npm run check`（完整输出，未 tail）：

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1154 files in 672ms. No fixes applied.

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

零 error / warning / info。

## 改动历史

本人改动清单（`git status --porcelain`）：

```
?? packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W06-guard-coverage-20261013.md
```

只有两个新文件，未触碰任何生产代码、其它测试文件或既有文件。

关键位置（`packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`）：

| file:line | 内容 |
| --- | --- |
| `test/suite/worktree-junction-guard-coverage.test.ts:77` | `createFixture()`：`<root>/real/node_modules` + `<root>/wt` + `<root>/clean` + `<root>/task.md` |
| `…:92` | `cmd /c mklink /J` 建 `<root>/wt/node_modules` → `<root>/real/node_modules`（失败即抛） |
| `…:120` | `unlinkJunction()`：`cmd /c rmdir`（无 `/S`、无尾分隔符） |
| `…:129` | `createGuardHarness()`：`BashOperations` 记录器 + `process.chdir(fixture.root)` + `PI_WORKER_TASK` 开关 |
| `…:161` | `extensionFactories: [(pi) => activate(pi)]` —— 真实注册面（P-002 靶心） |
| `…:186` | 第①层 describe：`decideWorktreeRemove` 纯函数断言 |
| `…:228` | 第②层 describe：真实 `tool_call` 链路 |
| `…:254` | (a)(f) worker 模式事故命令：block + `executedBashCommands===[]` + `trace.log` `[WORKTREE_GUARD]` |
| `…:279` | (b) PM/交互模式（`PI_WORKER_TASK` 未设）：仍 block |
| `…:297` | (c) `rm -rf "<root>/wt/"`：block + `cmd /c rmdir` 文本 + 零执行 |
| `…:318` | (d) 反向对照：`isError===false` 且 `executedBashCommands===[command]` |
| `…:336` | (e) 只读/无关命令：全部执行且无痕迹 |

未触碰（写入禁止面）：`packages/coding-agent/src/**`（含 `index.ts`、`shared/worktree-junction-guard.ts`）、`packages/multi-workers/**`、`scripts/**`、`test/suite/worktree-junction-guard-decide.test.ts`、`test/suite/harness.ts`。

## 残留与未验证

1. **Windows-only 夹具**：junction 依赖 `cmd /c mklink /J`，与 W-05 的 `worktree-junction-guard-decide.test.ts` 同构；在非 Windows CI 上会失败。本仓既有 W-05 已有同样约束，未新增平台分叉。
2. **只验证了两支注册分支**：`activate()` 只有 `pmActivate`（含纯交互窗口）与 `workerModeActivate` 两支；卡片的“三种模式”在代码里就是这两支（交互与 PM 共用 `pmActivate`）。真正的三段式差别（`PI_WORKER_TASK`）已覆盖。
3. **bash 后端按设计 stub**：真链路证明的是“handler 返回 block，工具体不执行”，不是 `git worktree remove` 的真实磁盘行为（那正是 W-05/事故复现的领域，且被硬约束禁止在真仓执行）。
4. **PM 激活副作用（测试夹具层，非生产 bug）**：`pmActivate` 的 worker 轮询 `setInterval` 未 `unref()`，而 `harness.cleanup()` 走 `AgentSession.dispose()`，后者不触发 `session_shutdown`，故轮询在 vitest worker 退出前可能继续心跳。测试通过 `process.chdir(fixture.root)` 把其协调根限在夹具内（无 `.agenticdoc`，全部读为空），未写任何真仓文件；实测 `git status` 与 `%TEMP%` 均无越界残留。属测试夹具行为，不改生产代码。
5. 未发现生产代码 bug，无需交回 PM 的 `file:line` 缺陷项。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w06-guard-coverage/task.md`
- 目标：`.agenticdoc/goal.md`（G1）
- 设计/判据：`.agenticdoc/mw-worktree-junction-guard/design.md` §3.4 P-002、AC-001/002/003/004、D-11
- 模板：`packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`
- 复用件：`packages/coding-agent/test/suite/harness.ts:101`（`createHarness`）、`:34`（`getMessageText`）
- 被测面：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:70`（`registerWorktreeJunctionGuard(pi)` 注册点）、`shared/worktree-junction-guard.ts:179`（注册）、`:83`（`decideWorktreeRemove`）、`:652`（`notRemove`）、`:709`（`deletePenetrationVerdict`）、`:764`（`recordWorktreeGuardBlockTrace`）
  （卡片给的 61/158/78/653/721 是改动前的行号；以上为本次实测行号。）
- 既有姊妹测试：`packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（W-05/W-05b 纯函数矩阵）

TESTS: 9/9 | executedBashCommands(block)=0 | CHECK: clean
