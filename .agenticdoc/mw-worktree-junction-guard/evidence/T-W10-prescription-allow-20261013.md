# T-W10 — 处方命令本身必须被放行（回归锚，QG F-06）

- key: mw-worktree-junction-guard
- card: `.agenticdoc/mw-worktree-junction-guard/tasks/T-W10-prescription-allow.md`
- date: 2026-10-13
- 角色: coding（只追加测试 + 本报告）

## 结论

F-06 已闭环：`worktree-junction-guard-decide.test.ts` 追加了一个 describe（`:406-447`），在**同一夹具形态**下用
`fs.lstatSync(...).isSymbolicLink() === true` + `realpath` 指向夹具内目标 + `git worktree remove`
确实 `reparse-point` block 作为机器事实，然后断言 G1 的两条处方命令逐条 `block === false` /
`basis === "not-remove"`：

1. `mw worktree rm "<JUNCTION_WT>"` —— §4.3 处方一；
2. `cmd /c rmdir "<JUNCTION_LINK>"` —— D-11 处方二（逐条、无 `/S`、无尾分隔符）；
3. `cd "<ROOT>"; mw worktree rm "<JUNCTION_WT>"` —— 处方一 + 前导 `cd`；
4. `cmd /c rmdir "<JUNCTION_LINK>/"` 与 `cmd /c rmdir "<JUNCTION_LINK>\"` —— 尾分隔符**误拼**，按卡片要求
   **保持现状**，实测仍为 `block === false` / `basis === "not-remove"`（头词是 `cmd`，`notRemove()` 在
   `src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:652-654`）。

未改任何生产代码。既有 23 例 + 新增 2 例 = 25 例全绿；`npm run check` exit 0 / clean。

## 证据

### 每条断言的实测 block / basis / reason

用与测试夹具同构的探针（`%TEMP%` + `cmd /c mklink /J` + 链目标在夹具内）先实测，再把同一命令移入正式用例；
两者结果一致。`not-remove` 走 `notRemove()`（`worktree-junction-guard.ts:652-654`），**按构造不产出 `reason`**，
因此 allow 行 `reason` 实测为 `undefined`；block 锚点行给出实测 `reason` 片段。

| 用例（测试文件行） | 命令 | 实测 block | 实测 basis | 实测 reason |
|---|---|---|---|---|
| 锚点，`:411-414` | `git worktree remove --force "<JUNCTION_WT>"` | `true` | `reparse-point` | `[mw-worktree-guard] blocked: <WT> 内有 1 个 reparse point（示例 <LINK> -> <DEPS_REAL>）；…请改用：\n  mw worktree rm "<WT>"` |
| 处方一，`:418` | `mw worktree rm "<JUNCTION_WT>"` | `false` | `not-remove` | `undefined`（`hits: []`） |
| 处方二，`:420` | `cmd /c rmdir "<JUNCTION_LINK>"` | `false` | `not-remove` | `undefined`（`hits: []`） |
| 处方一 + `cd`，`:422` | `cd "<ROOT>"; mw worktree rm "<JUNCTION_WT>"` | `false` | `not-remove` | `undefined`（`hits: []`） |
| 尾斜杠误拼，`:438` | `cmd /c rmdir "<JUNCTION_LINK>/"` | `false` | `not-remove` | `undefined` |
| 尾反斜杠误拼，`:439` | `cmd /c rmdir "<JUNCTION_LINK>\"` | `false` | `not-remove` | `undefined` |

探针原始输出（tsx，2026-10-13，脚本运行后已删除）：

```
fixture ROOT=C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w10-probe
lstat isSymbolicLink=true
--- hazard: git worktree remove --force "<ROOT>\wt"
block=true basis=reparse-point hits=["<ROOT>\\wt\\node_modules"]
reason="[mw-worktree-guard] blocked: <ROOT>\\wt 内有 1 个 reparse point（示例 <ROOT>\\wt\\node_modules -> <ROOT>\\deps）；\n直接执行 git worktree remove 会穿透并删除目标真树内容。请改用：\n  mw worktree rm \"<ROOT>\\wt\""
--- rx1: mw worktree rm "<ROOT>\wt"
block=false basis=not-remove hits=[]
reason=undefined
--- rx2: cmd /c rmdir "<ROOT>\wt\node_modules"
block=false basis=not-remove hits=[]
reason=undefined
--- rx2-fwdslash: cmd /c rmdir "<ROOT>\wt\node_modules/"
block=false basis=not-remove hits=[]
reason=undefined
--- rx2-backslash: cmd /c rmdir "<ROOT>\wt\node_modules\"
block=false basis=not-remove hits=[]
reason=undefined
--- combo: cd "<ROOT>"; mw worktree rm "<ROOT>\wt"
block=false basis=not-remove hits=[]
reason=undefined
cleanup done
```

### 夹具与机器事实

复用既有 decide 夹具（未新建第二个 decide 文件、未新建链）：

- `ROOT = %TEMP%\wjg-w05-decision`（本机为 `C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05-decision`）
- `JUNCTION_WT = <ROOT>\junction-wt`，`JUNCTION_LINK = <ROOT>\junction-wt\node_modules`
- 链目标 `DEPS_REAL = <ROOT>\deps-real`，**在夹具内**（`beforeAll` 建 `deps-real/sub/f.txt`）
- 建链：`cmd /c mklink /J "<JUNCTION_LINK>" "<DEPS_REAL>"`（`test/suite/worktree-junction-guard-decide.test.ts` `mklink()`）
- 机器事实断言（`:410-414`）：`fs.lstatSync(JUNCTION_LINK).isSymbolicLink() === true`、
  `canonicalPath(fs.realpathSync.native(JUNCTION_LINK)) === canonicalPath(DEPS_REAL)`、且
  `git worktree remove --force "<JUNCTION_WT>"` 实测 `block=true / reparse-point` —— 使 allow 断言非空转。
- 清理（`afterAll`，卡片硬约束）：对每个链 `cmd /c rmdir "<link>"`（无 `/S`、无尾分隔符）→
  `cmd /c rmdir /S /Q "<ROOT>"`，再 `fs.rmSync(ROOT, {recursive:true, force:true})` 兜底。
- 运行后核验：`Test-Path %TEMP%\wjg-w05-decision` = `False`（无残留）。

### 测试运行

```
$ cd packages/coding-agent
$ node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·························

 Test Files  1 passed (1)
      Tests  25 passed (25)
   Start at  00:53:14
   Duration  4.63s (transform 46ms, setup 0ms, import 59ms, tests 4.45s, environment 0ms)
```

基线（追加前）实测 `Tests 23 passed (23)`，追加后 25（+2 个 `it`，5 条 allow 命令断言）。

### npm run check（repo 根，完整输出）

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1154 files in 634ms. No fixes applied.

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

`EXIT=0`（`npm run check *> log; $LASTEXITCODE`），`tsgo --noEmit` 无输出、biome 无 error/warning/info。

## 改动历史

本人本次改动清单（`git status --porcelain`）：

```
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W10-prescription-allow-20261013.md
?? packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts
```

- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts:406-447`（+42 行，追加一个
  describe / 2 个 `it`；未改既有 23 例一行）。
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W10-prescription-allow-20261013.md`（新建，本报告）。
- 探针脚本写在 `%LOCALAPPDATA%\Temp\wjg-w10-probe.ts`，运行后已删除。

**与卡片「预期 = 1 改 + 1 新」的偏差（如实记录）**：decide 测试文件本身在 git 里是**未跟踪**的
（`??`，W-05b 会话产出后未提交），所以 porcelain 显示为「1 个未跟踪测试文件 + 1 个未跟踪证据文件」，
而不是「M + ??」；`git diff --stat -- <test file>` 为空。本人只在其尾部追加，未动既有内容。

## 残留与未验证

1. **尾分隔符误拼保持现状**：`cmd /c rmdir "<link>/"` 与 `cmd /c rmdir "<link>\"` 实测
   `block=false / not-remove`。`cmd` 头词不在护栏覆盖面（`worktree-junction-guard.ts:83-171` 只处理
   `git worktree remove|rm` 与 `rm`/`Remove-Item` 穿透形态），按卡片要求**未改实现**，仅把实际行为
   pin 进用例，不隐含「应当拦」的诉求。
2. **未验证项**：本用例只断言 guard 的 `decideWorktreeRemove` allow 面；`mw worktree rm` 作为 Python CLI
   真实执行路径（`packages/multi-workers/mw.py`）未在本任务验证——不在写入面，属 T-W02/W-11 面。
3. 本次未新建链、未改夹具、未动生产代码；既有 23 例在追加前后均全绿。

## 上下文来源

- `.agenticdoc/mw-worktree-junction-guard/workers/wjg-w10-prescription-allow/task.md`（dispatch card）
- `.agenticdoc/mw-worktree-junction-guard/tasks/T-W10-prescription-allow.md`
- `.agenticdoc/mw-worktree-junction-guard/spec.md` AC-002 / AC-003
- `.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md` F-06
- `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`
  `:83-171`（decide 主循环）、`:652-654`（`notRemove`）、`:657-664`（`reparsePointVerdict` 处方一 `:663`）、
  `:709-722`（`deletePenetrationVerdict` 处方二 `:712`）
- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（夹具 `beforeAll`/`afterAll`）

TESTS: 25/25 | 处方 allow 断言: 5 | CHECK: clean
