# T-W01 证据报告：bash 词法器下沉到 shared/bash-segments.ts

- 任务卡：`tasks/T-W01-bash-segments-sink.md`（card_sha256 `00d2870a…b9160`）
- Key：`mw-worktree-junction-guard`
- 日期：2026-10-13

## 结论

`implementation-gate.ts` 内模块私有的 bash 词法器组已整体下沉到新建的
`shared/bash-segments.ts` 并导出 `BashSegment` / `parseBashSegments`；
heredoc 两个 helper 与两个 escape 集合随词法器一并搬入（搬前 grep 确认无外部引用，
故不额外 export）。`implementation-gate.ts` 只新增一行 import、删除已搬走的 251 行，
判定逻辑与导出面逐字节不变。新测试直接 import 新模块，覆盖事故命令 token 原样取出、
`cd` 分段、单/双引号对 `$` 的差异、`;`/`|`/`&&`/`||` 分段、heredoc 不吞后续分段。
三条验收命令全绿。

## 证据

### 搬迁前后 file:line

| 符号 | before（HEAD `implementation-gate.ts`） | after（`bash-segments.ts`） |
| --- | --- | --- |
| `BashSegment` | 273（`interface`，未导出） | 18（`export interface`） |
| `readHeredocDelimiter` | 282（私有） | 27（私有） |
| `skipHeredocBody` | 310（私有） | 55（私有） |
| `BACKSLASH_ESCAPES_UNQUOTED` | 330（私有） | 75（私有） |
| `BACKSLASH_ESCAPES_DOUBLE_QUOTED` | 352（私有） | 97（私有） |
| `parseBashSegments` | 361（私有） | 106（`export function`） |
| 唯一调用点 | 620（`checkBashWriteTarget` 内） | 370（同函数，改为导入符号） |
| import | — | `implementation-gate.ts:5` `import { parseBashSegments } from "./bash-segments.ts";` |

删除位置：`implementation-gate.ts` 原 269–518 行（节头注释 + `BashSegment` 到
`parseBashSegments` 结束），共 251 行。新增位置：`bash-segments.ts` 18–247 行。
紧邻的 `stripEnvAssignments`（after 270）及之后全部未动。

`checkBashWriteTarget` / `verbTargets` / `resolveToken` / `stripEnvAssignments`
（非词法器，卡片要求留在原文件）保持原位，仅因上方 251 行删除而整体上移。

### grep 调用点清单（搬前，HEAD）

```
git grep -n "parseBashSegments\|BashSegment\|readHeredocDelimiter\|skipHeredocBody\|BACKSLASH_ESCAPES" HEAD -- "packages/**/*.ts"
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:273:interface BashSegment {
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:282:function readHeredocDelimiter(...)
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:310:function skipHeredocBody(...)
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:330:const BACKSLASH_ESCAPES_UNQUOTED = new Set([
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:352:const BACKSLASH_ESCAPES_DOUBLE_QUOTED = ...
HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:361:function parseBashSegments(...)
HEAD:...:362/363/398/428/448/489  （词法器内部自引用）
HEAD:...:620:  for (const segment of parseBashSegments(command)) {
```

结论：所有引用都在 `implementation-gate.ts` 单文件内，无跨模块引用 → 外部只需
`BashSegment`（`parseBashSegments` 的返回类型）与 `parseBashSegments` 两个导出；
heredoc helper 与 escape 集合仍仅被词法器引用，按卡片「仅被词法器引用」原则保持私有。

搬后 grep 确认无遗留旧符号引用：

```
packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts:18: export interface BashSegment
packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts:106: export function parseBashSegments
implementation-gate.ts:5: import { parseBashSegments } from "./bash-segments.ts";
implementation-gate.ts:370: for (const segment of parseBashSegments(command)) {
```

### 逐字节等价性校验

用脚本从 `git show HEAD:…implementation-gate.ts` 取原 273–518 行，与
`bash-segments.ts` 的正文（去掉两处 `export` 前缀、去掉新文件头注释）做字符串比较：

```
orig lines: 246 body lines: 247
IDENTICAL: true
```

（差 1 行是新文件头注释；正文逐字节相同。）

### 测试实际输出

新建测试：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

······

 Test Files  1 passed (1)
      Tests  6 passed (6)
```

既有 implementation-gate 回归：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

·········

 Test Files  1 passed (1)
      Tests  9 passed (9)
```

两条合并复跑（`npm run check` 的 biome `--write` 格式化测试文件之后）：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

···············

 Test Files  2 passed (2)
      Tests  15 passed (15)
```

### `npm run check` 完整输出

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1151 files in 673ms. Fixed 1 file.

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

零 error/warning/info（`Fixed 1 file` 是 biome 对新测试文件的一次性格式化；
之后 `npx biome check` 三个文件复检 “No fixes applied”）。

## 改动历史

`file:line` before → after：

1. 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts`
   （文件头注释 + HEAD 原 273–518 行的词法器正文，`BashSegment` / `parseBashSegments`
   改为 export）。新文件 1–252 行。
2. `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`
   - `+5`：`import { parseBashSegments } from "./bash-segments.ts";`
   - `-269..518`（251 行）：词法器节头注释 + `BashSegment` → `parseBashSegments` 整体删除。
   - 其余行号仅整体上移，内容不变。
3. 新增 `packages/coding-agent/test/suite/agent-team-loop-bash-segments.test.ts`（6 个用例）。
4. 新增本报告。

本人改动清单（`git status --porcelain`，仅允许面内路径）：

```
 M packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts
?? packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts
?? packages/coding-agent/test/suite/agent-team-loop-bash-segments.test.ts
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W01-bash-segments-20261013.md
```

工作树中其它 `M`/`??` 条目（`packages/multi-workers/*`、`packages/coding-agent/test/suite/mwds-*`、
其它 `.agenticdoc/*` key 等）是并行会话的改动，本任务未触碰。

diff 形态（`git --no-pager diff -- implementation-gate.ts`）：`1 insertion(+), 251 deletions(-)`。

## 残留与未验证

- 未做：worktree/junction guard 本身（G1 拦截层）不在本任务范围，本任务只交付其解析底座。
- 未验证：新导出 `parseBashSegments` 目前只有测试消费者；下一个任务（guard）接入时才会出现
  第二个生产消费者，届时才是「单一词法器被两处共用」的真正验证点。本任务的防漂移证据是
  「逐字节等价 + 原调用点行为回归全绿」。
- 未验证：词法器不含 `$`/反引号展开（设计如此），事故命令 token 以原始拼写（含
  `$env:TEMP\qg-head`）传给解析层；把该 token 解析成真实路径属于下游 guard 的职责，此处不测。
- 环境：本机为 win32，`npm run check` 的 `check:browser-smoke` 等为仓库既有基线；未运行全量
  vitest，仅按要求跑两条验收测试。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w01-bash-segments/task.md`
  （引用 `tasks/T-W01-bash-segments-sink.md`，`design.md` §3.4 决策 D-3，`spec.md` §6 坑点 12）。
- 目标锚点：`.agenticdoc/goal.md`（共享工作树并发安全）。
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`
  （HEAD 与工作树），新建 `…/shared/bash-segments.ts`。
- 测试参照：`packages/coding-agent/test/suite/agent-team-loop-implementation-gate.test.ts`、
  `packages/coding-agent/test/suite/task-frontmatter.test.ts`（纯单测风格）。
- 命令：`git grep`、`git --no-pager diff`、`git status --porcelain`、
  `node ../../node_modules/vitest/dist/cli.js --run …`、`npm run check`。

TESTS: 15/15 | CHECK: clean
