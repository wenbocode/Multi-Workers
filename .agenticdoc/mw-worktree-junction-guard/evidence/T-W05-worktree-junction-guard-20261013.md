# T-W05 — G1 `git worktree remove` 执行前拦截（AC-001/002/003）

- key: `mw-worktree-junction-guard` · 卡: `T-W05-worktree-guard` · worker: `wjg-w05-worktree-guard` · type: coding
- 日期: 2026-10-13 · 环境: Windows `10.0.26100` / Node `v24.19.0` / `git 2.53.0.windows.1` / PowerShell `5.1.26100.9168`
- 唯一写入物（证据）: 本文件。生产代码见「改动历史」。

## 结论

G1 拦截已按 `design.md` §3.1/§3.2/§3.3/§3.5/§4.3 落地并注册进三种模式：

- 新 `shared/worktree-junction-guard.ts` 导出 `WorktreeGuardVerdict` / `decideWorktreeRemove(command, cwd, env)` / `registerWorktreeJunctionGuard(pi)`；判定基于已下沉的 `parseBashSegments`（W-01），未触碰 `extractBashWriteCandidates` / `checkBashWriteTarget` / `WRITE_VERBS`。
- 事故形态（插值 + 命中 junction）实测 **block**，`basis=reparse-point`，`hits=[<worktree>\node_modules]`，`reason` 逐字命中 §4.3 模板并以可照抄的 `  mw worktree rm "<worktree>"` 结尾。
- 干净字面/可解析插值、目标不存在、非 `git worktree remove` 四类反向对照 **allow**；未知变量/通配/尾分隔符/裸名歧义 **block**。
- 单测 16/16 通过；`npm run check` 全链路 exit 0（零 error/warning/info）。
- entry 预算常量 = **200000**；实造 200001 条目目录实测命中 `scan-error:entry-budget`（扫描 1954 ms）。

## 证据

### 1. 判定矩阵（`decideWorktreeRemove` 纯函数，实测 16/16）

验收命令原文（`packages/coding-agent` 下）：

```
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts
```

实测输出：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

················

 Test Files  1 passed (1)
      Tests  16 passed (16)
   Start at  23:57:45
   Duration  4.78s (transform 40ms, setup 0ms, import 53ms, tests 4.55s, environment 0ms)
```

16 个用例与期望判定（全部通过）：

| # | 用例 | 命令/环境 | block | basis |
|---|---|---|---|---|
| 1 | 事故形态：`cd <repo>; git worktree remove --force "$env:TEMP\junction-wt"`（`TEMP` 指向夹具根） | 插值 + 命中 junction | **true** | `reparse-point`（`hits=[junction-wt\node_modules]`，reason 含 `1 个 reparse point` / `<link> -> <target>` / `  mw worktree rm "<junction-wt>"`） |
| 2 | 字面路径命中 junction | `git worktree remove --force "<junction-wt>"` | **true** | `reparse-point` |
| 3 | 断裂 junction（`mklink /J` 后删目标） | 字面路径 | **true** | `reparse-point`（`lstatSync().isSymbolicLink()=true`，`stat`/`existsSync` 不可见） |
| 4 | 干净字面 worktree（反向对照） | 字面路径 | false | `resolved` |
| 5 | 可解析插值 + 干净（反向对照） | `$env:N` / `${N}` / `%N%` / `$N` 四种拼写 | false | `resolved` |
| 6 | 命令内前置赋值 | `$t = "$env:WJG_JUNCTION"; git worktree remove --force $t` | **true** | `reparse-point` |
| 7 | 未知变量 | `"$env:WJG_NOPE_XYZ"` | **true** | `unresolved:WJG_NOPE_XYZ` |
| 8 | 通配 / 尾分隔符 / 命令替换 | `<clean>/*`、`<clean>/`、`"$(mktemp -d)/wt"` | **true** | `glob`（三例） |
| 9 | 相对操作数按 cwd 解析 | `"./junction-wt"` cwd=夹具根 | **true** | `reparse-point` |
| 10 | 前置 `cd` 作为基准 | `cd "<root>"; ... "./junction-wt"` | **true** | `reparse-point` |
| 11 | `Set-Location` 基准 + `-C` 覆盖 cwd | `Set-Location "<root>"; ...`、`cd <tmp>; git -C "<root>" ... "./junction-wt"` | **true** | `reparse-point` |
| 12 | 裸名唯一匹配（真实 git 注册表）指向 junction | `git -C <repo> worktree remove --force uniq-wt` | **true** | `reparse-point` |
| 13 | 裸名歧义（两个 worktree basename 相同） | `git -C <repo> worktree remove --force same` | **true** | `bare-name-ambiguous` |
| 14 | 裸名无匹配（反向对照，git 自 rc=128） | `... no-such-worktree-xyz` | false | `target-absent` |
| 15 | 目标不存在（反向对照，git no-op） | `<root>/does-not-exist` | false | `target-absent` |
| 16 | 非 `worktree remove`（反向对照，D-4：不扩大动词集） | `rm -rf <junction>`、`rm -rf <junction>/`、`rmdir /S /Q <junction>`、`Remove-Item -Recurse -Force <junction>`、`robocopy ... /MIR`、`git worktree list`、`git worktree add`、`git status` | false | `not-remove`（全部） |

### 2. 事故命令的 `basis` 与 `hits`

`%TEMP%` 探针（`file:///` 直接 import 生产模块，只读调用）：

- 原样事故命令（今日重放，`%TEMP%\qg-head` 已不存在）：

  ```
  A accident-verbatim => {"block":false,"basis":"target-absent","target":"C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\qg-head","hits":[]}
  ```

  ⇒ 与 `design.md` §3.3 / RQ-D1 `incident-verbatim-qg-head`（allow）一致：目标不存在时 git 自身 rc=128、零副作用。

- 复刻事故形态（夹具 `junction-wt\node_modules -> deps-real`）：

  ```
  B accident-shape   => {"block":true,"basis":"reparse-point","target":"C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w05-evidence\\fixture\\junction-wt","hits":["C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w05-evidence\\fixture\\junction-wt\\node_modules"]}
  ```

- block 文案实测（逐字，含 §4.3 三段与结尾可照抄命令）：

  ```
  [mw-worktree-guard] blocked: C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05-evidence\fixture\junction-wt 内有 1 个 reparse point（示例 C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05-evidence\fixture\junction-wt\node_modules -> C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05-evidence\fixture\deps-real）；
  直接执行 git worktree remove 会穿透并删除目标真树内容。请改用：
    mw worktree rm "C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05-evidence\fixture\junction-wt"
  ```

### 3. 夹具路径与清理命令

- 单测夹具根：`%TEMP%\wjg-w05-decision`（`junction-wt\node_modules -> deps-real`、`broken-wt\node_modules -> deps-gone`(已删)、真实 `git init` 仓库 + worktrees `p1\same`/`p2\same`/`uniq-wt`；`uniq-wt\node_modules -> deps-real`）。**所有链接目标都在夹具内，绝不指回真树**；junction 全部由 `cmd /c mklink /J` 创建。
- 清理（`afterAll`，与硬约束一致）：
  1. 逐条 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）：`junction-wt\node_modules`、`broken-wt\node_modules`、`uniq-wt\node_modules`；
  2. `cmd /c rmdir /S /Q %TEMP%\wjg-w05-decision`。
  - 实测 `Test-Path` 为 `False`，无残留。
- 探针夹具根：`%TEMP%\wjg-w05-evidence`，同法清理（`cleanup leftover => false`）。
- 未对真树 `H:\git\Multi-Workers\node_modules` 下的任何 junction 做写操作；未对真仓执行任何 `git worktree remove`；未执行 `git checkout/reset/clean/stash`、`rm`、`npm install`。

### 4. entry 预算实测

- 常量：`MAX_SCAN_ENTRIES = 200_000`（`worktree-junction-guard.ts` 模块常量）。
- 实测（`%TEMP%\wjg-w05-evidence\big` 造 200001 个文件后调用 `decideWorktreeRemove`）：

  ```
  C entry-budget     => {"block":true,"basis":"scan-error:entry-budget","entries":200001,"createMs":37233,"scanMs":1954}
  ```

  ⇒ 预算确实在超限时 fail-closed；200k 条目同步扫描 ≈ **1.95 s**（≈ 102k 条目/s）。handler 无超时包装（`runner.ts` 只 `await`），故上限即最坏阻塞时间。

### 5. `npm run check` 实际输出（exit 0）

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1153 files in 677ms. No fixes applied.

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

EXITCODE=0
```

（`tsgo --noEmit` 无输出 = 通过；只有可擦除 TS 语法，无内联 import —— `check:ts-imports` 通过。）

## 改动历史

### 生产代码

| file:line | before → after |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts` | 新建（0 → 630 行）：`WorktreeGuardVerdict` / `decideWorktreeRemove` / `registerWorktreeJunctionGuard` + 显式栈扫描器 + 插值展开 + 裸名注册表解析 + `[WORKTREE_GUARD]` trace。 |
| `packages/coding-agent/src/extensions/agent-team-loop/index.ts:5` | `import { registerXkeyGateGuard }…` 之前 **新增** `import { registerWorktreeJunctionGuard } from "./shared/worktree-junction-guard.ts";` |
| `packages/coding-agent/src/extensions/agent-team-loop/index.ts:62-70` | `registerImplementationGate(pi);` 与 `if (process.env.PI_WORKER_TASK)` 之间 **新增** 注释块 + `registerWorktreeJunctionGuard(pi);`（双加载 flag 之后、PM/Worker 分支之前 ⇒ three-mode 全覆盖） |

### 测试

| file:line | before → after |
|---|---|
| `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts` | 新建（0 → 311 行）：16 例纯函数矩阵，`%TEMP%` 夹具 + `cmd /c mklink /J` + `cmd /c rmdir` 清理。 |

### 本人改动清单（`git status --porcelain`）

```
 M packages/coding-agent/src/extensions/agent-team-loop/index.ts
?? packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts
?? packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W05-worktree-junction-guard-20261013.md
```

（`shared/implementation-gate.ts`、`dispatch-recovery-terminal.test.ts`、`mwds-t2x.test.ts`、`bash-segments.ts`、其它 evidence 均为其它 worker/本 key 其它任务的既有改动，本人未触碰。写面严格限于卡片「写入允许面」四行。）

## 残留与未验证

1. **D-4 第 2 条与卡片「不扩大动词集」的张力（已按卡片执行，需评审确认）**：`design.md` §3.5 D-4 第 2 条字面写「覆盖同一目标树上的 `<path>/`、`<path>/*`，**无论动词是 `rm -rf` 还是 `Remove-Item -Recurse`**」；但本卡要求 5 明写「**不**扩大动词集」，要求 7 明写「非 `worktree remove` 命令 ⇒ allow」。本实现按卡片执行：`rm -rf <junction>/`、`Remove-Item -Recurse -Force <junction>\*`、`rmdir /S /Q <junction>\`（RQ-1 已坐实穿透 1 层）**不在覆盖范围**，测试用例 16 将其固定为 `not-remove`。若评审要按 D-4 第 2 条补齐，需另开卡（会引入新的动词识别与误拦面）。
2. **尾分隔符/通配仅对 `git worktree remove|rm` 生效**：`git worktree remove "<wt>/"`、`"<wt>/*"` 判 `glob` block（卡片要求 2/5/7）；这与 `design.md` §3.3 规则表 (c)「尾分隔符剥掉后按 (a)」的字面不一致，但与同文件流水线图 P3「通配或尾分隔符 ⇒ block」及卡片一致。按卡片取 block（fail-closed）。
3. **entry 预算**：常量 `200000`（实测命中值 = 第 200001 条，`scan-error:entry-budget`，用时 1954 ms）。未在真树/真实规模 worktree 上测；未验证 200k 上限对最坏真实工作树是否够宽（design §5.2 全仓剪枝遍历实测 43,412 条，故 200k ≈ 4.6× 余量）。预算参数未外露（无 env 覆盖），如需调参需改常量。
4. **裸名匹配契约**：按 basename 匹配（`git worktree list --porcelain` 的路径尾段）。同名 basename 有两个 worktree（git id 会派生 `same`/`same1`）时判 `bare-name-ambiguous` block，属有意 fail-closed；仅在 `git 2.53.0.windows.1` 实测。`git worktree list` 返回长路径而 `os.tmpdir()` 可能是 8.3 短名，测试用 `realpathSync.native(parent)+basename` 归一比较。
5. **未覆盖的绕过面（design §7 已知）**：`bash -c "…"` / heredoc 载荷不被 `parseBashSegments` 展开；`commandPrefix`/`spawnHook` 在 handler 之后才改写 command/cwd/env；TOCTOU 窗口；`sl`/`Push-Location` 别名未跟踪（仅 `cd`/`Set-Location`）；单引号内不插值的语义未区分（统一展开）；非 Windows 未测；祖先目录是 junction 未纳入判据。
6. **注册/端到端**：本卡只做纯函数层验证；「真 `tool_call` → 三种模式覆盖 → `BashOperations` 零执行」由 W-06（`test/suite/worktree-guard-coverage.test.ts`，非本卡写面）负责，本卡未跑。
7. **`mw worktree rm` 可执行性**：`reason` 文案指向 G2 命令；G2（W-02）已在本 key 内落地，但本卡未验证该命令在目标机器上可执行（AC-002 的「可照抄」以文本契约满足）。
8. **trace 审计**：`[WORKTREE_GUARD]` 只在 `PI_WORKER_TASK` 存在时写 `<task>/trace.log`（照 `protected-config.ts`），未在单测中断言（无 W-06 覆盖）。

## 上下文来源

只读引用（均逐条实读并据此实现）：

| 文件 | 行/节 | 用途 |
|---|---|---|
| `.agenticdoc/mw-worktree-junction-guard/design.md` | §3.1/§3.2/§3.3/§3.5/§4.3/§9 | 落点、三符号接口、判定流水线 + 规则表 + 扫描 6 约束、D-4 边界、block 文案模板、AC-003 矩阵 |
| `.agenticdoc/mw-worktree-junction-guard/spec.md` | §0/§2（AC-001..003）/§3 | 目标对齐、验收标准、约束 |
| `.agenticdoc/mw-worktree-junction-guard/plan.md` | W-05 / §1 / §3 | 写面唯一性、串行点、W-05 交付定义 |
| `.agenticdoc/mw-worktree-junction-guard/tasks/T-W05-worktree-guard.md` | 全文 | 本卡要求与写面允许/禁止面 |
| `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-guard-path-resolution-20261013.md` | 事实组 1..4、D1-1..D1-5 | hook 能力、17 例原型矩阵、junction 原语、git 行为（`-C` 基准、裸名注册表、rc=128） |
| `.agenticdoc/mw-worktree-junction-guard/evidence/research/spec-junction-semantics-20261009.md` | §2.1 穿透矩阵 | 哪些形态穿透（`<link>/`、`<link>/*`、`rmdir /S /Q <link>\`）、哪些默认不穿透 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts` | `parseBashSegments` | 结构化分段（W-01 已落地，直接 import，未改） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | 全文 | 同类 guard 骨架（注册形状、handler、`~` 展开） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts` | `:224-243`、`:247-274` | trace 审计写法与注册形状 |
| `packages/coding-agent/src/extensions/agent-team-loop/index.ts` | `:42/:49/:59/:62/:64` | 注册位置（双加载 flag 后、PM/Worker 分支前） |
| `packages/coding-agent/src/core/extensions/types.ts` | `:307`、`:853-861`、`:1071-1075`、`:1188` | `ctx.cwd`、`ToolCallEvent`、`ToolCallEventResult`、handler 签名 |
| `packages/coding-agent/src/core/extensions/runner.ts` | `:309`、`:932-950` | `runner.cwd`、handler 无超时包装、首个 block 短路 |
| `packages/coding-agent/test/suite/agent-team-loop-bash-segments.test.ts` | 全文 | 纯函数测试与夹具风格 |
| `.agenticdoc/goal.md` | 目标/约束 | 「共享工作树不被破坏」是本 guard 的目标锚点（`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:1` 的头注释即引用该锚点与 2026-10-09 事故） |

目标对齐：`.agenticdoc/goal.md`「Worker 共享同一工作树」+ `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:8`（`git worktree remove --force` 穿透 junction 的事故复述）。

TESTS: 16/16 | CHECK: clean | 预算: 200000
