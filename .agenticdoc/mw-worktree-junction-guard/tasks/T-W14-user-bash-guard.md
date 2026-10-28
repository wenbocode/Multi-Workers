# T-W14 — G1 判定面补到 pi 的 `user_bash`（`!`/`!!`）通道（AC-014 / N-06）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；禁 `npm install`/`npm ci`；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— INV-1「含 reparse point 的 worktree **没有任何执行通道**能把它连同目标一起删掉」。这条不变量目前在一个通道上不成立。
- **来源**: 独立负空间审计 `.agenticdoc/mw-worktree-junction-guard/evidence/negative-space-audit-20261013.md` 的 N-06（PM 已复验：`.on("user_bash")` 全仓 **0** 处，`emitUserBash` 有 **13** 处出口）。spec 已据此新增 **AC-014**（`spec.md` §2 G6、§7 D-13）。
- **缺口形态**: pi 的用户直敲命令（TUI `!`/`!!` 前缀、RPC 同事件）走 `emitUserBash`（`packages/coding-agent/src/extensions/agent-team-loop/runner.ts:955-985`；出口见 `interactive-mode.ts:6270-6278`、`rpc-mode.ts:562`），**不经 bash 工具、不触发 `tool_call`**。G1 只挂 `tool_call`（`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:180`）⇒ `! git worktree remove --force <含链 wt>` 与事故命令完全同构却不经任何守卫。
- **现成能力（必须复用）**: `decideWorktreeRemove(command, cwd, env)`（`shared/worktree-junction-guard.ts:78`）、`scanTree`/`reparsePointVerdict`/`deletePentration`/处方文本（`:544-741`）、`[WORKTREE_GUARD]` trace 与 `notRemove` 前置（`:539`）。**不要**另写一套判定。
- **API 事实必须实测**: `pi.on("user_bash", handler)` 的事件名、事件负载字段（命令串 / cwd 从哪来）、以及"返回什么才算拦截（短路执行）"**必须**从 `node_modules` 的类型定义与实现中确认（AGENTS：外部 API 不许猜）。审计给出的线索：`runner.ts:955-985` 的 emitUserBash 契约「handler 返回 result 即短路执行」。若 `pi.on` 对未知事件名会抛错，注册必须**不得**让扩展加载失败（try/catch 或事件名探测，并把结论写进证据）。

## 要求

1. **注册面**：在 `registerWorktreeJunctionGuard`（`shared/worktree-junction-guard.ts:158`）内新增 `user_bash` 挂钩，与既有 `tool_call` 挂钩**并列**（同一注册函数、同一套判定与文本）。若能不改 `index.ts` 就不要改（改了必须在证据里说明原因与坐标）。
2. **判定复用**：对 `user_bash` 到达的整条命令串走 `decideWorktreeRemove(command, cwd, process.env)`；`block === true` ⇒ 返回可让执行短路的 result（内容含现有阻断文本：可照抄处方 + 链接路径与目标）；`block === false` ⇒ **不干预**（返回 undefined/不返回，让命令照常执行）。
3. **零副作用可证**：测试必须证明"被拦时命令没有真正执行"，而不是只断言返回值。至少 3 条用例：
   - 危险形态（`git worktree remove --force <含链 wt>`，含插值形态至少一条）⇒ 拦截，且**执行记录为空**；
   - **反向对照**：干净目标（无链 worktree）的 `!` 命令 ⇒ 不拦截且**确实执行**；
   - 处方命令 `! mw worktree rm "<wt>"` / `! cmd /c rmdir "<link>"` ⇒ 不拦截（处方不得被自己吃掉，与 F-06 同精神）。
   现有真链路夹具（`test/suite/worktree-junction-guard-coverage.test.ts` 的 `mklink /J` + `%TEMP%` 形态）优先复用；若 harness 无法发出 `user_bash` 事件，则用一个**最小假 pi**（捕获 `pi.on` 注册的 handler 并直接调用）在注册边界做断言 —— 但必须同时给出"该 handler 就是真实注册产物"的证据（例如断言捕获到的 handler 数量与 `user_bash` 事件名，且危险命令断言 `block` 后执行记录为空）。
4. **fail-closed 与不误拦**：与 G1 同口径（未知变量、命令替换、尾分隔符/通配形态按 D-4/D-11 处置）；干净命令不得误拦。
5. **可观测**：拦截时输出/记录 `[WORKTREE_GUARD]` trace 一行（与既有形态一致），并断言该行存在。
6. **验收**：`node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts`（decide 25 例**不得回归**，coverage 在本卡后应增加）；`npm run check` 零 error/warning/info。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W14-user-bash-guard-20261013.md`：`## 结论`、`## 证据`（API 实测：事件名/负载字段/短路语义的 `node_modules` 类型坐标与片段；三条用例的实测断言输出；`[WORKTREE_GUARD]` trace 行；夹具路径与清理；vitest 与 check 输出；**说明为何不需要改 `index.ts`**（或改了的理由））、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <decide>/<coverage> | user_bash 用例: <n> | 零副作用证明: <是|否> | CHECK: <clean|N errors>`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`
- `packages/coding-agent/test/suite/worktree-junction-guard-coverage.test.ts`
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W14-user-bash-guard-20261013.md`（新建）
- （仅在严格必要时）`packages/coding-agent/src/extensions/agent-team-loop/index.ts`，且必须在证据里说明理由

## 写入禁止面

- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（W-10 的写面，冻结）、`test/suite/harness.ts`、`test/suite/xkey-gate-guard-coverage.test.ts`、其它 `test/suite/**`。
- `packages/multi-workers/**`（同轮 W-13 在改 doctor 面）、`scripts/**`。
- **禁止执行部署**：不得跑 `mw build` / `mw build --install` / `mw start|stop`（PM 负责）。
- 真树：禁 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 下的 junction、禁 `npm install`/`npm ci`；夹具链目标必须在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts
cd ../..
npm run check
```

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
