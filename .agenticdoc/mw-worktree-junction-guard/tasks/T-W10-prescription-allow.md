# T-W10 — 处方命令本身必须被放行（回归锚，QG F-06）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— G1 的阻断文本**只**给人两条可照抄的处方：注册 worktree 用 `mw worktree rm "<worktree>"`，其它目标用 `cmd /c rmdir "<link>"`。若将来有人扩大动词面（D-4 历史上就扩过一次：D-11），**把处方自己吃掉**是最尴尬的回归：护栏让你改用它，而它被护栏拦住。
- **结构上现在成立但无锚**：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts:653`（`notRemove`，头词不是 `git`/`rm`/`Remove-Item` 即放行）；两套文本分别在 `worktree-junction-guard.ts:544`（`reparsePointVerdict`）与 `:721`（`deletePenetrationVerdict`，逐条 `cmd /c rmdir "<link>"`，`:712`）。现有用例面（`test/suite/worktree-junction-guard-decide.test.ts`）没有任何一条断言处方命令被放行 —— 独立 QG 记为 F-06。
- 相关 spec 验收：AC-003（不误拦的反向对照面）。

## 要求

1. 在 `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts` **追加**（不新建第二个 decide 测试文件、不改其它文件）至少 4 条 allow 断言，全部要求 `block === false` 且 `basis === "not-remove"`：
   - `mw worktree rm "<fixture 的 wt 路径>"`（处方一）；
   - `cmd /c rmdir "<fixture 的链路径>"`（处方二，逐条形式）；
   - `cmd /c rmdir "<link>"` 带尾分隔符的**误拼**要不要拦：**保持现状**（先测出实际行为，在报告里如实记录，不要把实现改成你以为的样子）；
   - 一条组合形态：`cd <fixture>; mw worktree rm "<wt>"`（处方常与前导 `cd` 同现）。
2. 用**同一夹具形态**（`%TEMP%` + `cmd /c mklink /J` + 链目标在夹具内）建立断言，使"链真的存在"这一点是机器事实而非假设。
3. 不改任何生产代码；若发现处方命令**当前**会被拦（与结构判断相反），**不要改**，写进报告「残留与未验证」并给 `file:line`。
4. `npm run check` 零 error/warning/info；既有 23 例必须全绿。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W10-prescription-allow-20261013.md`：`## 结论`、`## 证据`（每条断言的实测 `block`/`basis`/`reason` 片段、夹具路径与清理命令、`npm run check` 输出）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 处方 allow 断言: <n> | CHECK: <clean|N errors>`。

## 写入允许面

- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（仅追加用例）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W10-prescription-allow-20261013.md`（新建）

## 写入禁止面

- 一切生产代码：`packages/coding-agent/src/**`（含 `worktree-junction-guard.ts`、`index.ts`、`bash-segments.ts`）、`packages/multi-workers/**`、`scripts/**`。
- 其它测试文件（含 `test/suite/worktree-junction-guard-coverage.test.ts`、`test/suite/harness.ts`）。
- 真树：禁止 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 下的 junction、禁 `npm install`。
- 夹具硬约束：链目标必须在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts
cd ../..
npm run check
```

## 改动历史

报告内逐条列 `file:line` + `git status --porcelain` 的本人改动清单（预期 = 1 改 + 1 新）。
