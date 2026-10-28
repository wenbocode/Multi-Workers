# T-W05b — G1 补齐：`rm`/`Remove-Item` + 尾分隔符/通配形态（D-4 第 2 条，决策 D-11）

- key: `mw-worktree-junction-guard` · 卡: `T-W05b-delete-penetration` · worker: `wjg-w05b-delete-penetration` · type: coding
- 日期: 2026-10-13 · 环境: Windows `10.0.26100` / Node `v24.19.0` / git `2.53.0.windows.1` / PowerShell `5.1.26100.9168`
- 唯一写入物（证据）: 本文件。生产代码见「改动历史」。

## 结论

D-11 已落地：`decideWorktreeRemove` 在 `parseGitInvocation` 未命中时不再直接走 `notRemove()`，而是识别 **`rm`（`-r`/`-rf`/`-f`）与 PowerShell `Remove-Item`（`-Recurse`/`-Force`）** 且操作数**带尾分隔符或含 `* ? [`** 的穿透形态，命中后复用同一条流水线（插值展开 → `cd`/`Set-Location`/cwd 基准 → `scanTree` → reparse point / 目标不存在 / 枚举失败/超预算判定）。

- 新增 block 面走第二套文本，`basis=delete-penetration`：说明"该删除形态会穿透 reparse point"，列出命中的链与目标（≤3 条 + 总数），并给出可照抄的 `cmd /c rmdir "<link>"`（无 `/S`、无尾分隔符）后重试原删除。
- 目标是**已注册 worktree**（`git -C <target> worktree list --porcelain` 唯一匹配）时沿用 §4.3 模板，`basis=reparse-point`，结尾仍是 `  mw worktree rm "<worktree>"`；`hits` 语义不变（全部命中链的绝对路径）。
- 反向对照无回归：无尾分隔符/无通配的 `rm -rf <link>`、`rmdir /S /Q`、`robocopy /MIR`、`ls` 全部 allow；git 通道 16 例逐字不变。
- 单测 **23/23**（既有 16 + 新增 6 block + 5 allow 反向对照）；`npm run check` **exit 0**（零 error/warning/info）。
- 导出接口不变（`decideWorktreeRemove` / `registerWorktreeJunctionGuard`）；`index.ts` 未改。

## 证据

### 1. 测试实测（23/23）

`packages/coding-agent` 下：

```
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts
```

实测输出：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·······················

 Test Files  1 passed (1)
      Tests  23 passed (23)
   Start at  00:08:19
   Duration  5.09s (transform 44ms, setup 0ms, import 57ms, tests 4.88s, environment 0ms)
```

（既有 16 例全绿；新增用例见下表。`git status --porcelain` 里 W-05 的测试文件被本卡**原地扩展**，未新建第二个 decide 测试文件。）

### 2. 新增 6 例 block（实测 `basis`）

夹具同 W-05（`%TEMP%\wjg-w05-decision`）：`junction-wt\node_modules -> deps-real`、`plain-dir`（普通 `sub\f.txt` + `top.txt`）、真实 `git init` 仓库 + 注册 worktree `uniq-wt`（`uniq-wt\node_modules -> deps-real`）。

| # | 命令形态 | 期望 | 实测 `block` / `basis` | `target` / `hits` |
|---|---|---|---|---|
| 1 | `rm -rf "<junction-wt>/"` | block | `true` / `delete-penetration` | `junction-wt` / `[junction-wt\node_modules]` |
| 2 | `rm -rf "<junction-wt>/*"` | block | `true` / `delete-penetration` | `junction-wt` / `[junction-wt\node_modules]` |
| 3 | `Remove-Item -Recurse -Force "<junction-wt>\*"` | block | `true` / `delete-penetration` | `junction-wt` / `[junction-wt\node_modules]` |
| 4 | `Remove-Item -Recurse -Force "<junction-wt>/"` | block | `true` / `delete-penetration` | `junction-wt` / `[junction-wt\node_modules]` |
| 5 | `rm -rf "<uniq-wt>/"`（已注册 worktree） | block | `true` / `reparse-point` | `uniq-wt` / `[uniq-wt\node_modules]` |
| 6 | `rm -rf "$env:WJG_JUNCTION/"`（插值穿透形态） | block | `true` / `delete-penetration` | `junction-wt` / `[junction-wt\node_modules]` |

附加（同一 `it` 内）未知变量：`rm -rf "$env:WJG_NOPE_XYZ/"` ⇒ `block=true` / `basis=unresolved:WJG_NOPE_XYZ`（fail-closed）。

### 3. 新增 5 例 allow 反向对照（实测 `basis`）

| # | 命令 | 期望 | 实测 `block` / `basis` |
|---|---|---|---|
| 1 | `rm -rf "<junction-wt>"`（无尾分隔符、无通配，D-4 第 3 条） | allow | `false` / `not-remove` |
| 2 | `rm -rf "<clean-wt>/"`（空目录） | allow | `false` / `resolved` |
| 3 | `rm -rf "<plain-dir>/"`（仅普通目录/文件） | allow | `false` / `resolved` |
| 4 | `ls "<junction-wt>/"`（非覆盖动词） | allow | `false` / `not-remove` |
| 5 | `rmdir /S /Q "<junction-wt>"`（D-4 第 3 条不覆盖） | allow | `false` / `not-remove` |

既有用例 16 的 loop 已移除 `rm -rf "<junction-wt>/"`（该形态属 D-11 新增 block 面），其余 7 条非 git 命令仍断言 `not-remove`。

### 4. 两套 block 文本原文（单行可照抄部分逐字）

探针夹具 `%TEMP%\wjg-w05b-evidence`，`node --experimental-strip-types` 直接 import 生产模块（只读调用）：

**第二套（非 worktree 目标，`basis=delete-penetration`）** —— `rm -rf "<junction-wt>/"`：

```
[mw-worktree-guard] blocked: 该删除形态（尾分隔符或通配）会穿透 reparse point，删除链接指向的真树内容。目标 C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\junction-wt 内命中 1 个 reparse point：
  C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\junction-wt\node_modules -> C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\deps-real
请先逐条摘链（无 /S、无尾分隔符），再重试原删除命令：
  cmd /c rmdir "C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\junction-wt\node_modules"
```

**§4.3 模板（已注册 worktree 目标，`basis=reparse-point`）** —— `rm -rf "<uniq-wt>/"`：

```
[mw-worktree-guard] blocked: C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\uniq-wt 内有 1 个 reparse point（示例 C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\uniq-wt\node_modules -> C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\deps-real）；
直接执行 git worktree remove 会穿透并删除目标真树内容。请改用：
  mw worktree rm "C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w05b-evidence\uniq-wt"
```

第二套的机器判据（测试逐字断言）：`reason` 含 `穿透 reparse point`、含命中链、含 `  cmd /c rmdir "<link>"`，且**不含** `mw worktree rm`（已注册 worktree 才用后者）。

### 5. 夹具路径与清理命令

- 单测夹具根：`%TEMP%\wjg-w05-decision`（junction 目标全部在夹具内：`deps-real`；绝不指回真树）。新增 `plain-dir`（仅普通文件/目录，无链接）。
- 探针夹具根：`%TEMP%\wjg-w05b-evidence`（同构，仅用于抓取两套文本与 `basis`）。
- 清理（与硬约束一致）：
  1. 逐条 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）：`junction-wt\node_modules`、`uniq-wt\node_modules`；
  2. `cmd /c rmdir /S /Q <root>`。
  - 实测探针 `cleanup leftover exists=False`；单测 `afterAll` 同法且断言无残留。
- 未对真树 `H:\git\Multi-Workers\node_modules` 下任何 junction 做写操作；未对真仓执行任何删除/移除命令；未执行 `git checkout/reset/clean/stash`、`rm`、`npm install`。

### 6. `npm run check` 实际输出（exit 0）

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1153 files in 688ms. No fixes applied.

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

（首次运行时 biome `Fixed 2 files` = 本卡的两个写面文件；重跑 `No fixes applied`。`tsgo --noEmit` 无输出 = 通过；`check:ts-imports` 通过 ⇒ 只用可擦除语法、无内联 import。）

## 改动历史

### 生产代码 `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`

| file:line（after） | before → after |
|---|---|
| `:23-40`（模块头 doc） | before：`It does NOT widen the verb set: rm -rf <link> (no trailing separator) … out of scope`；after：D-4 + D-11 边界（`rm`/`Remove-Item` 穿透形态覆盖；无尾分隔符/无通配仍不覆盖；worktree 目标 §4.3 文本、其它目标第二套文本） |
| `:59-62`（`basis` doc） | after：取值域新增 `delete-penetration` |
| `:113-131`（主循环） | before：`if (invocation === undefined \|\| invocation.subcommand !== "worktree") continue;`；after：落入 `parseDeleteInvocation` 分支，逐操作数 `decideDeletePenetration`，有 block 即返回，否则返回首个非 block verdict（修复"非 block 判定被丢弃后落回 `notRemove()`"的中间缺陷） |
| `:267-345`（新增） | `hasPenetratingForm` / `deleteScanRoot` / `decideDeletePenetration` / `isRegisteredWorktree` / `canonicalComparePath` |
| `:506-510`（新增） | `parseDeleteInvocation`（head ∈ {`rm`,`remove-item`}；复用 `collectOperands`） |
| `:657-666`（改） | `reparsePointVerdict` 改用 `readLinkTarget`（行为/文本不变） |
| `:707-741`（新增） | `MAX_PENETRATION_LINES = 3` / `deletePenetrationVerdict` / `readLinkTarget` / `deleteGlobVerdict` |

### 测试 `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`

| file:line（after） | before → after |
|---|---|
| `:1-40`（头 doc + 夹具常量） | after：加 D-11 说明；新增 `PLAIN_DIR = path.join(ROOT, "plain-dir")` |
| `:130-140`（`beforeAll`） | after：创建 `plain-dir\sub\f.txt` + `plain-dir\top.txt`（纯普通内容） |
| `:306-322`（既有用例 16） | before：loop 含 `rm -rf "<junction-wt>/"` 断 `not-remove`；after：移除该形态（改由 D-11 block 面覆盖），其余 7 条不变 |
| `:323-388`（新增 describe） | 6 个 block `it`：`rm …/`、`rm …/*`、`Remove-Item …\*`、`Remove-Item …/`、注册 worktree `rm …/`（§4.3 文本）、插值 + 未知变量 |
| `:389-402`（新增 describe） | 1 个 allow `it`（loop 5 例反向对照） |

### 本人改动清单（`git status --porcelain`，仅列本卡写面）

```
?? packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts
?? packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W05b-delete-penetration-20261013.md
```

（两个代码文件是 W-05 的未跟踪新文件，本卡原地扩展；`index.ts`、`bash-segments.ts`、`implementation-gate.ts`、其它 evidence 均为其它 worker/本 key 其它任务的既有改动，本人未触碰。）

## 残留与未验证

1. **"含 `* ? [`"的操作数面是 fail-closed 的宽面**：`rm -rf "<dir>/sub*"` 会取 glob 前缀的父目录做 `scanTree`（`deleteScanRoot`），因此"目标目录内任意位置有 reparse point"即 block——比 RQ-1 实测的"穿透 1 层"语义更宽。这是刻意的（过拦属安全侧），但意味着 `rm -rf <repo>/*` 这类命令在含 junction 的目录上会被拦。
2. **多操作数**：`rm -rf "<a>/" "<b>/"` 逐操作数判定；有一个 block 即 block，全部非 block 时返回第一个非 block verdict。未对多操作数的 reason 做合并展示。
3. **worktree 注册表判定**：`isRegisteredWorktree` 用 `git -C <target> worktree list --porcelain` 精确匹配 `target`（规范化后、Windows 大小写不敏感、`realpathSync.native(parent)+basename` 防短名漂移）。目标不在任何 git 仓库内 ⇒ git 失败 ⇒ 视为非注册 ⇒ 第二套文本。仅 `git 2.53.0.windows.1` 实测。
4. **第二套文本的处方只列前 3 条命中链的 `cmd /c rmdir`**（`MAX_PENETRATION_LINES = 3`），超过时附"另有 N 条未列出，请对每个命中的链执行同一条 rmdir 后重试"。若目标内命中链 >3，照抄的处方不完整（需按提示对每条链各执行一次）。
5. **`rm` 不区分是否带 `-r`**：按卡片"rm（含 `-r`/`-rf`/`-f`）"实现为 head=`rm` + 操作数形态门槛；`rm `<dir>/``（无 `-r`，本身删不掉目录）在含 junction 时也会 block，属 fail-closed。
6. **未覆盖的绕过面（沿用 W-05 §5 已知）**：`sudo rm`/`bash -c "…"`/heredoc 载荷/命令别名；`commandPrefix`/`spawnHook` 在 handler 之后改写 command/cwd/env；TOCTOU 窗口；非 Windows 未测；祖先目录是 junction 未纳入判据。
7. **端到端未测**：本卡只做纯函数层；`tool_call` → 三模式 → `BashOperations` 零执行由 W-06（`worktree-junction-guard-coverage.test.ts`，非本卡写面）负责。
8. **`mw worktree rm` 可执行性**未验证（AC-002 的"可照抄"以文本契约满足）；G2 已在本 key 内落地。
9. **`[WORKTREE_GUARD]` trace** 只在 `PI_WORKER_TASK` 存在时写，未在单测断言（W-06 覆盖）。

## 上下文来源

只读引用（逐条实读并据此实现）：

| 文件 | 行/节 | 用途 |
|---|---|---|
| `.agenticdoc/mw-worktree-junction-guard/tasks/T-W05b-delete-penetration.md` | 全文 | 本卡要求、写面允许/禁止面、验收命令、交付格式 |
| `.agenticdoc/mw-worktree-junction-guard/design.md` | §3.3 规则表 / §3.5 D-4 + 2026-10-13 补充（D-11）/ §4.3 block 文本模板 | 同一流水线、动词面边界、两套文本契约 |
| `.agenticdoc/mw-worktree-junction-guard/spec.md` | §2 AC-001/002/003、§3 D-11 | 目标对齐与 D-11 决策理由（RQ-1 穿透 1 层） |
| `.agenticdoc/mw-worktree-junction-guard/evidence/T-W05-worktree-junction-guard-20261013.md` | 全文（尤其 §残留 1） | 首轮实现的现状锚点与显式残留 |
| `.agenticdoc/mw-worktree-junction-guard/plan.md` | W-05b | 写面唯一性、串行点 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts` | W-05 版 | 复用 `scanTree` / `scanVerdict` / `expandToken` / `reparsePointVerdict` / `listWorktrees` / `parseBashSegments` |
| `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts` | W-05 版 | 夹具与断言风格，原地扩展 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts` | `parseBashSegments` | 结构化分段（未改） |

目标对齐：`.agenticdoc/goal.md`「危险路径不可达」+ 事故复述（`worktree-junction-guard.ts:1`）。

TESTS: 23/23 | CHECK: clean | 新动词面: rm(-r/-rf/-f), Remove-Item(-Recurse/-Force)，且操作数带尾分隔符或含 `* ? [`
