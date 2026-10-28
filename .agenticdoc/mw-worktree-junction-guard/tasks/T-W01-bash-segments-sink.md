# T-W01 — 词法器下沉：`parseBashSegments` → `shared/bash-segments.ts`（D-3）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令（见「写入禁止面」）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 核心交付「常驻 mw 服务 + 多 Worker 并行开发同一项目」，前提是共享工作树在并发下不被破坏。本任务是 G1（执行前拦截）的**解析底座**：事故命令 `git worktree remove --force "$env:TEMP\qg-head"` 的目标**不是字面路径**，解析层必须先能原样取出 token。
- **现状（已实测，勿重做）**: 词法器在 `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts` 内**模块私有**：
  - `implementation-gate.ts:273`（`interface BashSegment`）、`implementation-gate.ts:282`（`readHeredocDelimiter`）、`implementation-gate.ts:310`（`skipHeredocBody`）、`implementation-gate.ts:330`（`BACKSLASH_ESCAPES_UNQUOTED`）、`implementation-gate.ts:352`（`BACKSLASH_ESCAPES_DOUBLE_QUOTED`）、`implementation-gate.ts:361`（`parseBashSegments`）；
  - 消费者：`implementation-gate.ts:612`（`checkBashWriteTarget`，**已导出**），在 `implementation-gate.ts:620` 调用 `parseBashSegments`；
  - `implementation-gate.ts:520`（`stripEnvAssignments`）、`implementation-gate.ts:526`（`resolveToken`）、`implementation-gate.ts:530`（`joinDestName`）、`implementation-gate.ts:539`（`verbTargets`）**不是词法器**，留在原文件。
- **决策出处**: `design.md` §3.4（决策 D-3）—— 复制一份会留下两套词法漂移（本项目 IN-3 类事故的成因，见 `spec.md` §6 坑点 12 的同源思路）。
- 相关 spec 验收：AC-001/002/003（G1 的判定全部建立在本词法器之上）。

## 要求

1. 新建 `shared/bash-segments.ts`，把**词法器组**整体搬入并 `export`：`BashSegment`（如外部需要类型）、`parseBashSegments`；heredoc 两个 helper 与两个 escape 集合按"仅被词法器引用"原则一并搬入（搬前用 grep 确认调用点，若有外部引用一并 export）。
2. `implementation-gate.ts` 改为 `import { parseBashSegments } from "./bash-segments.ts"`（按该目录既有 import 风格，注意是否带 `.ts` 后缀要与邻居一致），**除此之外不改任何判定逻辑**：`checkBashWriteTarget` / `verbTargets` / `resolveToken` 等行为逐字节不变。
3. 新建 `test/suite/agent-team-loop-bash-segments.test.ts`，至少断言（直接 import 新模块）：
   - `git worktree remove --force "$env:TEMP\qg-head"` 分段后含 `worktree`、`remove`、`--force`、`$env:TEMP\qg-head`（引号剥离、插值**不展开**）；
   - `cd H:/git/Multi-Workers; git worktree remove --force <path>` 的 `cd` 基准段与命令段分离；
   - 单引号 vs 双引号对 `$` 的处理差异；`;`/`|`/`&&` 分段；heredoc 不吞后续分段。
4. 回归证明：`npm run check` 零 error/warning/info；既有 `test/suite/agent-team-loop-implementation-gate.test.ts` 全绿（证明搬迁无行为变化）。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W01-bash-segments-20261013.md`，含：`## 结论`、`## 证据`（搬迁前后 `file:line`、grep 调用点清单、测试实际输出）、`## 残留与未验证`、`## 上下文来源`。
- 报告最后给一行 `TESTS: <通过数>/<总数> | CHECK: <clean|N errors>`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`（**只改 import 行**）
- `packages/coding-agent/test/suite/agent-team-loop-bash-segments.test.ts`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W01-bash-segments-20261013.md`（新建）

## 写入禁止面

- 其它任何仓库文件（尤其：`…/agent-team-loop/index.ts`、`shared/worktree-guard.ts`、`packages/multi-workers/**`、`scripts/**`）。
- 禁止改 `implementation-gate.ts` 的判定逻辑/常量/导出面（`WRITE_VERBS`、`checkBashWriteTarget` 等一律不动）。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove`、`rm`、`npm install`；禁止触碰真树 `H:\git\Multi-Workers\node_modules` 下的任何 junction；禁改 `.agenticdoc` 下别的 key。
- 禁止内联 import（`await import()`）与需要 JS emit 的 TS 语法（enum/namespace/参数属性）。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/agent-team-loop-bash-segments.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/agent-team-loop-implementation-gate.test.ts
cd ../..
npm run check
```

三条全绿才算完成；`npm run check` 必须给完整输出（不 tail）。

## 改动历史

报告 `## 证据` 内逐条列 `file:line` **before → after**（搬迁 = 删除位置 + 新增位置 + import 行），并附 `git status --porcelain` 的本人改动清单（证明只动了允许面内的文件）。
