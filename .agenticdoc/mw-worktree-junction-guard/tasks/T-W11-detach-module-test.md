# T-W11 — AC-013 常驻回归测试：把摘链原语抽成可测模块（QG F-05）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；**禁止运行 `npm run diff:model-catalog`**；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— AC-013 修的是「一条 npm 命令即可复刻事故」的口子（`scripts/diff-model-catalog.mjs` 在 `git worktree remove --force` 前必须摘掉 `<wt>/node_modules` 链）。W-07 已修好并有**两向夹具对照**的证据（`evidence/T-W07-model-catalog-script-20261013.md`），但**没有入库的测试**：脚本的复演与验证输出只存在于证据文件里（独立 QG 记为 F-05）。
- **为什么不能直接 import 现有脚本做测试**: `scripts/diff-model-catalog.mjs` 是**顶层脚本**（无 `export`，主体是顶层语句：`scripts/diff-model-catalog.mjs:55` 读 `process.argv`、`scripts/diff-model-catalog.mjs:67` `git rev-parse --show-toplevel` 定 `repoRoot`、`scripts/diff-model-catalog.mjs:197` `git worktree add`）。任何 `import` 都会**执行整个脚本**，即对真仓做 worktree add/remove —— 这正是不能做的事。
- **现成约定**: 仓库已有 `scripts/*.test.mjs` 约定，由 `npm run test:scripts`（= `node --test scripts/*.test.mjs`）执行，现存 `scripts/sync-versions.test.mjs`。
- **W-07 已落地的原语（实测坐标，先读代码确认）**: `scripts/diff-model-catalog.mjs:161`（`detachBaselineNodeModulesLink`：`lstatSync` 探测，非 win32 `unlinkSync` / win32 `cmd /c rmdir`，失败后自检 `lstatSync` 必须 ENOENT）；调用点在 `finally` 内、`git worktree remove --force` **之前**（`scripts/diff-model-catalog.mjs:285`）；`worktreeSitePreserved` 同时挡住 remove 与 `rmSync`（`scripts/diff-model-catalog.mjs:288` / `scripts/diff-model-catalog.mjs:303`）；顶层副作用点：`scripts/diff-model-catalog.mjs:55`（`process.argv`）、`scripts/diff-model-catalog.mjs:67`（`git rev-parse --show-toplevel`）、`scripts/diff-model-catalog.mjs:197`（`git worktree add`）。
- 相关 spec 验收：AC-013（摘链后再 remove；反向对照 = 现行脚本在夹具内能复刻事故）。验收入口约定：`scripts/sync-versions.test.mjs:1` 是同类测试的参照形态（由 `npm run test:scripts` = `node --test scripts/*.test.mjs` 执行，脚本定义在 `package.json:41`）。

## 要求

1. **抽出可测模块**：把摘链原语移到一个**无顶层副作用**的新模块 `scripts/detach-node-modules-link.mjs`（函数体**逐字**搬运，不改行为），返回结构化结果（例如 `{status: "skipped" | "detached" | "failed", link, reason}`），由调用方决定打印/退出码/是否保留现场。
2. **`scripts/diff-model-catalog.mjs` 只做最小接线**：改为 import 该模块；**行为逐字不变** —— 正常路径（无链 ⇒ 静默跳过；有链 ⇒ 摘掉后继续 remove）、失败路径（自检未过 ⇒ `process.exitCode = 1`、**跳过** `git worktree remove --force` 与 `rmSync(temporaryRoot)`、打印手工 `cmd /c rmdir "<link>"` 提示）都必须与 W-07 的证据描述一致；不要顺手重构其它部分。
3. **新建 `scripts/detach-node-modules-link.test.mjs`**（`node --test`，夹具全在 `%TEMP%`，链目标必须在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`），至少覆盖：
   - **NEG-1**：路径不存在 ⇒ `status === "skipped"`，不抛、不改任何东西；
   - **NEG-2**：路径存在但**不是** reparse point（普通目录/文件）⇒ 结果必须与实现语义一致（先读代码判定它应 `skipped` 还是 `failed`），并断言**目标内容零变化**；
   - **POS-1**：真 junction（`cmd /c mklink /J`，目标在夹具内且含文件）⇒ `status === "detached"`，链消失（`lstatSync` 抛 ENOENT）、**目标内容与 mtime 不变**、目标目录仍在；
   - **ABORT-1**：注入失败（例如把"链路径"指向一个**非空普通目录**，或让 `cmd /c rmdir` 必然失败的最简构造；**具体手法由你实测选定并在报告里写明**）⇒ `status === "failed"`，且**目标内容零变化**（现场保留）。若无法在不 mock 的前提下构造稳定失败，允许对模块注入可替换的删除函数（模块需支持注入点），但不要为了测试而改变默认行为。
4. **不做**的事：不运行 `npm run diff:model-catalog`（会产生真仓 worktree）；不 import 顶层脚本本体；不改 `packages/multi-workers/**`。
5. 验收：`npm run test:scripts` 全绿（含新增文件）；`npm run check` 零 error/warning/info（biome 管 `scripts/**`）。既有 `scripts/sync-versions.test.mjs` 不得回归。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W11-detach-module-test-20261013.md`：`## 结论`、`## 证据`（4+ 条用例的实测 `status`/断言输出、ABORT 注入手法与理由、夹具路径与清理命令、`npm run test:scripts` 与 `npm run check` 的实际输出、**脚本行为未变**的对照说明：摘链/自检/abort 三处 before-after）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | status 覆盖: skipped/detached/failed | CHECK: <clean|N errors>`。

## 写入允许面

- `scripts/detach-node-modules-link.mjs`（新建，原语宿主）
- `scripts/diff-model-catalog.mjs`（仅换成 import + 保持行为）
- `scripts/detach-node-modules-link.test.mjs`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W11-detach-module-test-20261013.md`（新建）

## 写入禁止面

- `packages/**`（任何包内源码/测试）、其它 `scripts/*.mjs`（含 `sync-versions.test.mjs`、`generate-*.mjs`、`check-*.mjs`）。
- 真树：**禁止运行 `npm run diff:model-catalog`**；禁止 `git worktree add|remove|prune`、`git checkout|reset|clean|stash`、`rm`、`npm install`；禁止碰真树 `node_modules` 下的 junction。

## 验收命令

```
npm run test:scripts
npm run check
```

（`npm run check` 完整输出，不 tail。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单（预期 = 1 新模块 + 1 改 + 1 新测试）。
