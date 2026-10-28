# T-W07 — AC-013：修 `scripts/diff-model-catalog.mjs`（仓库自带的复刻路径）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**在真树执行该脚本或任何 worktree/npm 写操作；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 「常驻 mw 服务 + 多 Worker 并行开发同一项目」不允许存在"仓库自带一条命令即可复刻事故"的路径。本任务修掉这条路径（spec 的 G5 · AC-013）。
- **实证（RQ-N3 §3.2，PM 已逐行复核）**: `scripts/diff-model-catalog.mjs`（`package.json:28` 暴露为 `npm run diff:model-catalog`）默认执行三步，与 2026-10-09 事故同构：
  - `scripts/diff-model-catalog.mjs:148` —— `run("git", ["worktree", "add", "--detach", baselineWorktree, "HEAD"], { cwd: repoRoot })`；
  - `scripts/diff-model-catalog.mjs:155`（`existsSync(nodeModules)`）→ `scripts/diff-model-catalog.mjs:157` —— `symlinkSync(nodeModules, join(baselineWorktree, "node_modules"), process.platform === "win32" ? "junction" : "dir")`，把 worktree 的 `node_modules` **指回真树**；
  - `scripts/diff-model-catalog.mjs:233`（`finally`）→ `scripts/diff-model-catalog.mjs:235` —— `run("git", ["worktree", "remove", "--force", baselineWorktree], { cwd: repoRoot })`。
- **为什么 G1 管不到**: 该脚本经 node 子进程直接调 git，**不经 agent 的 bash 工具** ⇒ `tool_call` hook 天然看不见（`design.md` §3.6）。所以只能改脚本本身。
- **穿透机理与安全原语（已实测，勿重做）**: `git worktree remove --force` 会**跟随** worktree 内的 reparse point 递归删除；`cmd /c rmdir <link>`（**无 `/S`**、无尾分隔符）只摘链、不穿透（`mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md` 对照实验；两根链可穿两层）。
- 相关 spec 验收：**AC-013**（脚本在含 junction 的真树上跑完**主树零变化**）；反向对照 = **现行**脚本在夹具内必须能复刻事故。

## 要求

1. 在 `finally` 块里、调用 `git worktree remove --force` **之前**，先摘掉 `<baselineWorktree>\node_modules` 这条链：
   - Windows（`process.platform === "win32"`，即建 junction 的分支）：`execFileSync("cmd", ["/c", "rmdir", <abs link>], ...)` —— **无 `/S`**、无尾分隔符；
   - 非 Windows（建的是 `dir` symlink）：`unlinkSync(<abs link>)`（不要 `rmSync(..., {recursive:true})`）。
   - 链不存在（例如 `existsSync(nodeModules)` 为假、或上游步骤已抛错）⇒ 静默跳过，**不得**因此让清理路径失败。
2. **摘链后自检**：`lstatSync(<wt>/node_modules)` 必须抛 `ENOENT`（不存在的链要能被 `lstat` 看见并判为链，不能用 `existsSync`）；若链仍在 ⇒ **中止本次 `git worktree remove`**，打印明确错误（含可照抄的 `cmd /c rmdir "<link>"`）并保留 worktree 现场（fail-closed，照 `design.md` §4.2 的"中止保留现场"纪律）。
3. 其余语义**保持不变**：win32 仍建 junction（脚本需要 baseline worktree 里有 `node_modules`）、`rmSync(temporaryRoot, { recursive: true, force: true })` 仍在 `finally` 末尾、错误路径与退出码不变。**不要**新增 CLI 开关（尤其不要加"跳过摘链"的开关）。
4. 不要求 `export` 新函数（该脚本顶层即执行，import 会触发整个流程）——验证走夹具内**等价步骤复演**。
5. **绝不执行 `npm run diff:model-catalog`，绝不在真仓跑 `git worktree add/remove`。**

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W07-model-catalog-script-20261013.md`：`## 结论`、`## 证据`（改动 before→after 逐行、`node --check` 输出、阳性对照与阴性对照的 manifest 对照实测输出、夹具路径与清理命令）、`## 改动历史`、`## 残留与未验证`（必须写明：**完整 `npm run diff:model-catalog` 未执行**，理由 = 它会在真树复刻事故）、`## 上下文来源`。
- 报告末行 `POS: <阳性对照结果> | NEG: <阴性对照结果> | CHECK: <clean|N errors>`。

## 写入允许面

- `scripts/diff-model-catalog.mjs`
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W07-model-catalog-script-20261013.md`（新建）
- `%TEMP%` 下的夹具与临时验证脚本（**不在仓内**；不要往仓库根留临时文件）

## 写入禁止面

- 其它任何仓库文件（尤其 `scripts/generate-model-catalog.mjs`、`package.json`、`packages/**`）。
- 真树上的破坏性/写操作：`npm install`/`npm ci`、`git worktree add|remove|prune`、`git checkout|reset|clean|stash`、`rm`；禁止触碰真树 `H:\git\Multi-Workers\node_modules` 下的任何 junction。
- 夹具硬约束：夹具必须是 `%TEMP%` 内**自建**的 git 仓库（`git init`），链的目标全部在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`。

## 验收命令

夹具内两向对照（脚本自建，路径按实际命名写进报告）：

```
# 阳性对照（修复前形态，必须在夹具内复刻事故）
git -C <fix>/A ...; git -C <fix>/A worktree add --detach <fix>/B HEAD
cmd /c mklink /J <fix>\B\node_modules <fix>\A\node_modules
git -C <fix>/A worktree remove --force <fix>/B      # 断言 A 侧 tracked 文件消失（夹具成立性证明）

# 阴性对照（修复后形态）
# 重建同构夹具 → 摘链（cmd /c rmdir <fix>\B\node_modules）→ git worktree remove --force <fix>/B
# 断言 A 侧 manifest（tracked 清单 + sha256 + size + mtime）零变化

node --check scripts/diff-model-catalog.mjs
cd H:/git/Multi-Workers; npm run check
```

（`npm run check` 完整输出，不 tail。）

## 改动历史

报告内逐条列 `scripts/diff-model-catalog.mjs` 的 before→after 行号与内容 + `git status --porcelain` 的本人改动清单。
