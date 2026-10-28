# T-W17 — D-19: 删除面动词补全 + 基准面旗标/词表补全

- key: mw-worktree-junction-guard
- card: `tasks/T-W17-ps-verb-base-vocabulary.md`
- type: coding
- 结论面: `shared/worktree-junction-guard.ts` 的 `readLocationTarget` / caller / `parseDeleteInvocation`
- case 面: `test/suite/worktree-junction-guard-decide.test.ts`（新增 D-19 describe，8 个 `it`）
- coverage 面冻结未动

## 结论

按 spec §7 **D-19** 完成「只补词表/旗标，不动判定谓词」：

1. **基准面**（`readLocationTarget`）头词由 `cd | set-location` 扩为 `cd | set-location | pushd | sl | chdir`；取目标值时跳过 cmd 风格 `/d`、`/D` 与全部 `-` 前缀参数，并能从 `-Path=<dir>` / `-LiteralPath=<dir>` 的 `=` 尾部取值（`-Path <dir>` 原行为已可取到值）；无操作数的位置动词（裸 `pushd` → PS 语义回 $HOME）返回 `target: ""`，caller 置 `cwdMissing` + `effectiveCwd=undefined`，与 `cd $UNSET` 同处置 fail-closed，**不静默沿用旧 cwd**。
2. **删除面**（`parseDeleteInvocation`）头词由 `rm | remove-item` 扩为 `rm | remove-item | ri | del | erase | rd | rmdir`；递归旗标、尾分隔符/通配、`notRemove` 谓词与两套处方文本（`mw worktree rm` / `cmd /c rmdir`）**一字未动**。
3. 反向对照 13 条全部实测放行（含 `rmdir /S`、`cmd /c rmdir "<link>"` 按段首词判定）；每新词至少一条穿透形态实测拦为 `delete-penetration` + 第二套文本；`cd /d` 修复前=放行、修复后=拦，已在证据中给出前后对照。

源码文件与被测文件在本会话开始时均为未跟踪（`??`），无既有已提交基线；下文「before」= 本会话首次 `read` 到的工作树版本。

## 证据

### 1. 每个新删除动词的拦（实测断言，探针 + decide 套件）

夹具：`%TEMP%\w17-probe-<rand>\`，`wt\node_modules` 为 `cmd /c mklink /J` 指向夹具内 `deps-real` 的 junction。命令经 `decideWorktreeRemove(command, root, process.env)`：

| 命令 | block | basis | hits | 文本面 |
|---|---|---|---|---|
| `ri -r -fo "<wt>/"` | true | `delete-penetration` | 1 | 第二套（`cmd /c rmdir "<link>"`，无 `mw worktree rm`） |
| `del -Recurse "<wt>/*"` | true | `delete-penetration` | 1 | 第二套 |
| `erase -Recurse "<wt>/"` | true | `delete-penetration` | 1 | 第二套 |
| `rd -Recurse "<wt>/*"` | true | `delete-penetration` | 1 | 第二套 |
| `rmdir -Recurse "<wt>/"` | true | `delete-penetration` | 1 | 第二套 |

探针原始输出（节选，reason 首行）：

```
== penetrating delete verbs (must block, delete-penetration) ==
ri -r -fo <link>/                  block=true  basis=delete-penetration   hits=1
    reason: [mw-worktree-guard] blocked: 该删除形态（尾分隔符或通配）会穿透 reparse point，删除链接指向的真树内容。目标 ...\wt 内命中 1 个 reparse point：
del -Recurse <link>/*              block=true  basis=delete-penetration   hits=1
erase -Recurse <link>/             block=true  basis=delete-penetration   hits=1
rd -Recurse <link>/*               block=true  basis=delete-penetration   hits=1
rmdir -Recurse <link>/             block=true  basis=delete-penetration   hits=1
```

`decide` 套件 `it("blocks every new delete verb in a penetrating form with the second text")`（`worktree-junction-guard-decide.test.ts:519`）逐词额外断言：`hits == [<link>]`、`reason` 含 `  cmd /c rmdir "<link>"`、`not.toContain("mw worktree rm")`。

### 2. 反向对照（必须放行，逐条实测）

探针输出：

```
== reverse controls: separator-free/glob-free delete (must allow) ==
del <file>                         block=false basis=not-remove  hits=0
ri <file>                          block=false basis=not-remove  hits=0
erase <file>                       block=false basis=not-remove  hits=0
rd <dir> (no sep/glob)             block=false basis=not-remove  hits=0
rmdir /S <dir> (D-4)               block=false basis=not-remove  hits=0

== baseline verbs alone (must allow, not-remove) ==
sl <dir> alone                     block=false basis=not-remove  hits=0
chdir <dir> alone                  block=false basis=not-remove  hits=0
pushd <dir> alone                  block=false basis=not-remove  hits=0
cd /d <dir> alone                  block=false basis=not-remove  hits=0
bare pushd alone                   block=false basis=not-remove  hits=0

== existing prescriptions (must allow, not-remove) ==
mw worktree rm <wt>                block=false basis=not-remove  hits=0
cmd /c rmdir <link>                block=false basis=not-remove  hits=0
cmd /c rmdir <link>/               block=false basis=not-remove  hits=0
```

其中 `cmd /c rmdir "<link>"` 段首词为 `cmd`（`rmdir` 只是 `/c` 后的参数），仍是 `not-remove` —— 新词表**未**把它改判，符合「按段首词判定」。`rmdir /S "<dir>"` 的 `/S` 既非递归旗标也非穿透操作数（无尾分隔符/无通配），维持 D-4 已声明的不穿透边界。

反向对照计数：删除面 5 + 基准面单独出现 5 + 既有处方 3 = **13**。

### 3. 基准漂移：`pushd` / `sl` / `chdir` / `cd /d`（必须拦）

| 命令 | block | basis | target |
|---|---|---|---|
| `pushd "<dir>"; git worktree remove --force "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `sl "<dir>"; git worktree remove --force "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `chdir "<dir>"; git worktree remove --force "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `cd /d "<dir>"; git worktree remove --force "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `Set-Location -Path "<dir>"; …remove "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `Set-Location -Path="<dir>"; …remove "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `Set-Location -LiteralPath="<dir>"; …remove "./wt"` | true | `reparse-point` | `<dir>\wt` |
| `pushd; git worktree remove --force "./wt"`（裸） | true | `unresolved:pushd` | base 不可证 |

裸 `pushd` 的 reason：`[mw-worktree-guard] blocked: worktree 目标 ./wt 含无法解析的变量 pushd；无法证明目标树内无 reparse point。…` —— 复用 `cd $UNSET` 的同一条 `unresolvedVerdict` 路径/文本，未改判定谓词。

### 4. `cd /d` 修复前后对照（本卡要求修的点）

**修复前**（探针/套件跑在未改源码上）：

```
FAIL  test/suite/worktree-junction-guard-decide.test.ts > … > skips the cmd-style `/d` / `/D` flag and takes the real operand (`cd /d <dir>`)
AssertionError: /d: expected false to be true
- Expected: true
+ Received: false
```

即 `cd /d "<dir>"; git worktree remove --force "./uniq-wt"` 修复前 `block=false`。机制（Node 实测）：

```
{"base_before_fix":"C:\\d","target_before_fix":"C:\\d\\uniq-wt"}
```

旧 `readLocationTarget` 只跳过 `-` 前缀词，cmd 的 `/d` 被当成目标 → base 漂到 `<当前盘>:\d` → `./uniq-wt` 解到 `<当前盘>:\d\uniq-wt`（不存在）→ `target-absent` 放行，真 junction 从没被扫到。

**修复后**：`/d`/`/D` 被识别为旗标跳过，base = `<dir>`，`./uniq-wt` 解到含 junction 的真 worktree → `block=true, basis=reparse-point`（见 §3 表与套件 `:472` 用例）。

### 5. 验收命令完整输出（不 tail）

```
> cd packages/coding-agent
> node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts

 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

····································[worker] start task=wjg-w06-7Q4z7d …
··[worker] start task=wjg-w06-Q9zJct type=coding phases=-
·[worker] start task=wjg-w06-GZXJ2y type=coding phases=-
·[worker] start task=wjg-w06-EzqVDS type=coding phases=-
·[worker] start task=wjg-w06-uMFVnH type=coding phases=-
·[worker] start task=wjg-w06-Xcdl8V type=coding phases=-
·[worker] start task=wjg-w06-M0JYJB type=coding phases=-
·[worker] start task=wjg-w06-pL5UNU type=coding phases=-
··

 Test Files  2 passed (2)
      Tests  46 passed (46)
   Start at  08:36:38
   Duration  5.07s
```

拆分：decide **33 passed**（25 既有 + 8 新增），coverage **13 passed**（W-14 案例面冻结未回归）。

修复前同命令的对照：`Tests  5 failed | 28 passed (33)`（decide），失败即 §3/§1 要求拦的 5 个用例；coverage 不受影响。

```
> cd ../..; npm run check

> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1155 files in 645ms. Fixed 1 file.

> pi-monorepo@0.0.3 check:pinned-deps
> node scripts/check-pinned-deps.mjs

> pi-monorepo@0.0.3 check:ts-imports
> node scripts/check-ts-relative-imports.mjs

> pi-monorepo@0.0.3 check:shrinkwrap
packages/coding-agent/npm-shrinkwrap.json is up to date.

> pi-monorepo@0.0.3 check:install-lock:coding-agent
packages/coding-agent/install-lock is up to date.

> pi-monorepo@0.0.3 check:browser-smoke
> node scripts/check-browser-smoke.mjs
```

零 error / warning / info。`Fixed 1 file` = biome 对 `test/suite/worktree-junction-guard-decide.test.ts` 我做的一处长行做纯格式换行（`it("takes the value of …")` 内的 `decideWorktreeRemove(` 调用），无语义变化；格式化后验收套件重跑仍 46 passed（上表即重跑结果）。窗口内没有其它 `.ts` 文件被 `--write` 触碰（按 mtime 核对），未越写面。

### 6. 夹具路径与清理

- decide 套件夹具：`%TEMP%\wjg-w05-decision\`（`junction-wt\node_modules`、`broken-wt\node_modules`、`uniq-wt\node_modules` 三条 junction，目标均为夹具内 `deps-real` / `deps-gone`）。
  - `beforeAll`：先 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）清残留，再建夹具。
  - `afterAll`：逐条 `cmd /c rmdir <link>`（无 `/S`）→ `cmd /c rmdir /S /Q <ROOT>` → 兜底 `fs.rmSync`。
- 探针夹具：`%TEMP%\w17-probe-<rand>\`，同法创建/清理；探针输出末行 `cleaned fixture: … exists=false`。
- 全程未碰真树 `node_modules` 链，未跑 `git worktree add|remove|prune`（仅夹具临时 git 仓库内 `git worktree add`，decide 套件既有行为），未跑 `mw build|start|stop`，未 `rm`。

## 改动历史

`git status --porcelain`（本人改动，两项均为本会话创建的未跟踪文件）：

```
?? packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts
?? packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts
```

`file:line` before → after（该文件此前未提交，before = 本会话首次读取的工作树版本）：

- `worktree-junction-guard.ts` 顶部边界注释 `:27`（before 单段 D-4/D-11）→ after 增补 D-19：覆盖位置动词 `cd`/`Set-Location`/`pushd`/`sl`/`chdir` 与 `/d`，删除面增列 `ri`/`del`/`erase`/`rd`/`rmdir`。
- `worktree-junction-guard.ts` caller `:~111`（before `const expanded = expandToken(location, table);` 无空目标分支）→ after `:113-131`：新增 `location.target === ""` 分支（`cwdMissing = location.verb; effectiveCwd = undefined`），并将展开源改为 `location.target`。
- `worktree-junction-guard.ts` `readLocationTarget` before `~:517-525`（`head !== "cd" && head !== "set-location"`，返回 `string | undefined`，只跳 `-` 前缀）→ after `:529-556`：`LocationUpdate` 接口 + `LOCATION_VERBS`（`cd|set-location|pushd|sl|chdir`）+ `PATH_PARAMETERS`（`-path|-literalpath`），跳过 `/d`/`/D` 与所有 `-` 参数，支持 `-Path=`/`-LiteralPath=` 取值，无操作数返回 `target: ""`。
- `worktree-junction-guard.ts` D-11 注释 `:138`（before `rm`/`Remove-Item`）→ after `D-11/D-19: the covered delete verbs' …`。
- `worktree-junction-guard.ts` `parseDeleteInvocation` before `~:549-554`（`head !== "rm" && head !== "remove-item"`）→ after `:591-596`：`DELETE_VERBS`（`rm|remove-item|ri|del|erase|rd|rmdir`）；函数体只保留 `collectOperands`，递归旗标/尾分隔符/通配/`notRemove`/处方文本未动。
- `worktree-junction-guard-decide.test.ts` before `:432`（W-14 处方反例 describe 结束）→ after `:447-565`：新增 `describe("decideWorktreeRemove — PowerShell/cmd verb vocabulary (D-19)")`，8 个 `it`（`:458` 基准漂移 3 动词；`:472` `/d`/`/D`；`:485` `-Path`/`-Path=`/`-LiteralPath=`；`:504` 裸 `pushd` unresolved；`:510` 基准反向对照；`:519` 5 删除动词拦；`:538` 删除反向对照；`:554` 既有处方未改判）。

## 残留与未验证

- 裸位置动词的 `unresolved` 文本沿用 `unresolvedVerdict`（`…含无法解析的变量 <verb>…`）；对 `pushd` 读作「变量」略不精确。为严格满足 D-19「只补词表、不动判定谓词/文本」未改该共享文本，仅 basis 精确为 `unresolved:pushd`。
- `-Path:<dir>`（冒号写法）、PS `--%` 停止解析、`pushd` 无参时 cmd 语义（打印栈）与 PS 语义（回 home）的差异未单独建模：统一按「base 不可证 → fail-closed」处理，overshoot 方向安全。
- 未覆盖 D-20 边界（`\<LF>` 续行拼接、头词/子命令/动作位插值、`bash -c`/`cmd /c` 前缀解包）——不在本卡范围。
- 未跑 `mw build`/`mw build --install`/`mw start|stop`，未做真 pi 运行时部署验证（`user_bash`/`tool_call` 真实 dispatch 由冻结的 coverage 套件覆盖）。

## 上下文来源

- `tasks/T-W17-ps-verb-base-vocabulary.md`（本卡）
- `.agenticdoc/goal.md` INV-1
- `.agenticdoc/mw-worktree-junction-guard/spec.md` §7 D-19（`:145`）
- `.agenticdoc/mw-worktree-junction-guard/design.md` 2026-10-14 补充节 D-19（`:377`）
- `.agenticdoc/mw-worktree-junction-guard/evidence/delta-adversarial-audit-20261013.md` §1b A6′/A11（最强反例：`mw_common.ensure_pi_shell_path` 钉 PowerShell）
- 既有实现：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`（W-05/W-05b/W-14）
- 边界声明：`test/suite/worktree-junction-guard-decide.test.ts` D-4 rule 3 / D-11

TESTS: 33/13 | 新词: 5 动词 + 3 基准 | 反向对照: 13 | CHECK: clean
