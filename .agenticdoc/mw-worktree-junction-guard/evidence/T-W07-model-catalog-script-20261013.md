# T-W07 — AC-013：`scripts/diff-model-catalog.mjs` 摘链后再 remove

- key: `mw-worktree-junction-guard` · worker: `wjg-w07-model-catalog-script` · type: coding · 日期: 2026-10-13
- 卡片: `tasks/T-W07-model-catalog-script.md`（card_sha256 `45a6e88ce66f54d56262168ba040bcb24c7a9b002a4f5c3b2d08e560dab7dba2`）
- 目标锚点: `.agenticdoc/goal.md`（G5 · AC-013）；spec: `spec.md`；design: `design.md` §3.6 / §4.2 / §9
- 变更文件: `scripts/diff-model-catalog.mjs`（HEAD blob `e00563f7633bce0710d29893dcff27658d489c1a` → 工作树 sha256 `03D30B42B75220049EF11D9DA2FE113020AC7AB1229C9376305A0FA97D35ABF2`，211 行 → 305 行）

## 结论

AC-013 已完成。`scripts/diff-model-catalog.mjs` 的 `finally` 现在在调用 `git worktree remove --force` 之前，先用与 G2 步 3 相同的原语摘掉 `<baselineWorktree>\node_modules` 这条指回真树的链：

- Windows：`execFileSync("cmd", ["/c", "rmdir", <abs link>])` —— **无 `/S`、无尾分隔符**；
- 非 Windows：`unlinkSync(<abs link>)`（非 `rmSync(..., {recursive:true})`）；
- 链不存在（`lstatSync` 抛 `ENOENT`，含断链以外的"无条目"情形）⇒ 静默跳过，不影响清理路径。

摘链后用 `lstatSync(link)` 做 fail-closed 自检：**必须抛 `ENOENT`**；否则抛错 ⇒ `finally` 捕获后**中止本次 `git worktree remove`**、打印含可照抄 `cmd /c rmdir "<link>"` 的错误、保留 worktree 现场（跳过 `rmSync(temporaryRoot, ...)`）并置 `process.exitCode = 1`。正常路径（无链 / 摘链成功）行为与退出码不变；win32 仍建 junction，`rmSync(temporaryRoot, ...)` 仍是 `finally` 末尾语句；未新增任何 CLI 开关。

夹具内两向对照：**阳性对照**用修复前形态（worktree add → `mklink /J` 两层链 → `git worktree remove --force`）在同一夹具内复刻事故（A 侧 tracked 文件消失）；**阴性对照**用修复后形态（同一摘链原语 → remove）主树 manifest（tracked + sha256 + size + mtime）零变化。`node --check` 通过；`npm run check` 除一条来自**另一并发会话**新文件的 biome warning 外全部通过（详见「证据 §5」，该文件不在本任务写面内）。

## 证据

### 1. 改动 before→after 逐行（`scripts/diff-model-catalog.mjs`）

| HEAD 行 | before | 工作树行 | after |
|---|---|---|---|
| 3 | `import { copyFileSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";` | 3–14 | 展开为多行 import，新增 `lstatSync`（第 6 行）与 `unlinkSync`（第 12 行） |
| 6 | `import { spawnSync } from "node:child_process";` | 17 | `import { execFileSync, spawnSync } from "node:child_process";` |
| （无） | — | 158–160 | 说明注释：`git worktree remove --force` 会跟随 reparse point 删除链目标，故必须先摘链 |
| （无） | — | 161–187 | 新函数 `detachBaselineNodeModulesLink(baselineWorktree)`：`lstatSync` 判链（`ENOENT` ⇒ 静默返回；非链 ⇒ 返回）→ win32 `execFileSync("cmd", ["/c", "rmdir", link], {stdio:"inherit"})` / 非 win32 `unlinkSync(link)` → 自检 `lstatSync(link)` 必须抛 `ENOENT`，否则 `throw new Error("<link> still exists after detaching the link")` |
| （无） | — | 189–194 | 新函数 `printManualDetachHint`：打印 `cmd /c rmdir "<link>"`（win32）/ `rm "<link>"`（非 win32）与手工清理提示 |
| 232–241 | `} finally {` / `if (worktreeAdded) { try { run("git", ["worktree","remove","--force", baselineWorktree], {cwd: repoRoot}) } catch {...} }` / `rmSync(temporaryRoot, {recursive:true, force:true});` / `}` | 281–305 | `finally` 内先 `detachBaselineNodeModulesLink(baselineWorktree)`（285）；失败 ⇒ `worktreeSitePreserved = true`、`process.exitCode = 1`、打印错误 + 手工摘链提示（287–292）；仅在未保留现场时调用 `run("git", ["worktree","remove","--force", ...])`（294–300）与 `rmSync(temporaryRoot, ...)`（302–304） |

不变项（逐条核对）：win32 建 junction 未动（工作树 204–207：`const nodeModules = join(repoRoot, "node_modules")` → `if (existsSync(nodeModules)) symlinkSync(nodeModules, join(baselineWorktree, "node_modules"), process.platform === "win32" ? "junction" : "dir")`）；`git worktree add` 未动（199）；无新 CLI 开关；未 `export` 任何新函数。

### 2. `node --check`

```
$ cd H:/git/Multi-Workers; node --check scripts/diff-model-catalog.mjs
NODE_CHECK_EXIT=0
```

### 3. 夹具两向对照（卡片要求的"夹具内等价步骤复演"）

夹具全部在 `%TEMP%` 内自建，链目标全部在夹具内，**未触碰真树**。

- 夹具根: `C:\Users\wenbozhou\AppData\Local\Temp\wjg-w07`（`%TEMP%\wjg-w07`；POS/NEG/ABORT 分别为其下 `AC013-pos` / `AC013-neg` / `AC013-abort`）
- 复演脚本: `%TEMP%\wjg-w07\replay.mjs`（每个模式自建夹具、跑对照、清理）
- 夹具结构（每个模式独立重建）：
  - `A/` = 假真树（`git init` + commit）：tracked `packages/x/f1.txt`、`packages/x/f2.txt`、`packages/y/g1.txt`、`.gitignore`（`node_modules/`）
  - 层 1 链（在 A 内）：`cmd /c mklink /J A\node_modules\@scope\x A\packages\x`
  - `B/` = `git -C A worktree add --detach B HEAD`
  - 层 2 链（worktree 指回"真树"）：`cmd /c mklink /J B\node_modules A\node_modules`
- manifest 原语：`git -C A ls-files -z` 得 tracked 清单，逐条记录 `size` / `mtimeMs` / `sha256`，缺文件记为 `missing`；对照键 = `removed/added/content_changed/mtime_changed/missing_after`
- 清理（每个模式结束即做，卡片规定的形态）：先逐条 `cmd /c rmdir <link>`（**无 `/S`、无尾分隔符**：`A\node_modules\@scope\x`、`B\node_modules`）→ `cmd /c rd /S /Q <fixture root>`

命令（每个模式）：

```
node "%TEMP%\wjg-w07\replay.mjs" pos | neg | abort
```

**阳性对照**（修复前形态，必须复刻事故）实测输出：

```
=== POS (no detach: incident reproduction) ===
{
  "fixture": "C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w07\\AC013-pos",
  "A_tracked_before": 4,
  "missing_after": [
    "packages/x/f1.txt",
    "packages/x/f2.txt"
  ],
  "removed": [],
  "content_changed": [],
  "A_packages_x_f1_exists": false,
  "A_packages_x_files_on_disk": [],
  "incident_reproduced": true
}
```

⇒ 夹具成立：`git worktree remove --force` 穿透两层 junction（`B/node_modules` → `A/node_modules` → `@scope/x` → `A/packages/x`），A 侧 tracked 文件在磁盘上消失。

**阴性对照**（修复后形态：摘链 → remove）实测输出（摘链用的是从脚本内**原样抽取**的 `detachBaselineNodeModulesLink` 源码，经 `new Function` 绑定真实 `lstatSync/execFileSync/join/unlinkSync`，避免复演漂移）：

```
=== NEG (detach then remove) ===
{
  "fixture": "C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w07\\AC013-neg",
  "link_lstat_after_detach": "ENOENT",
  "A_packages_x_files_on_disk": [
    "f1.txt",
    "f2.txt"
  ],
  "manifest": {
    "removed": [],
    "added": [],
    "content_changed": [],
    "mtime_changed": [],
    "missing_after": [],
    "clean": true
  }
}
```

⇒ 摘链后 `lstatSync(<wt>/node_modules)` 抛 `ENOENT`；`git worktree remove --force` 后主树 manifest 零变化。

**fail-closed 中止分支复演**（超出卡片最低要求，用于覆盖要求 2）：把同一抽取函数绑定到抛错的 `execFileSync`（模拟 `rmdir` 失败），复演 `finally` 的"仅在摘链函数正常返回后才 remove"决策：

```
=== ABORT (failing rmdir must skip git worktree remove and preserve the site) ===
{
  "fixture": "C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w07\\AC013-abort",
  "helper_threw": "simulated rmdir failure",
  "remove_called_in_replica": false,
  "site_preserved": true,
  "B_exists": true,
  "junction_still_present": true,
  "A_packages_x_files_on_disk": [
    "f1.txt",
    "f2.txt"
  ],
  "manifest_clean": true
}
```

**辅助探测 `rmSync` 与 junction 的关系**（判定"中止时跳过 `rmSync`"是否必要，脚本 `%TEMP%\wjg-w07\probe-rm.mjs`）：同构夹具（A + worktree B + `B\node_modules -> A\node_modules` + `A\node_modules\@scope\x -> A\packages\x`）上执行 `rmSync(<B 的父目录>, {recursive:true, force:true})`，实测 `A/packages/x` 的 `f1.txt`/`f2.txt` 与 `A/node_modules`、`A/node_modules\@scope` 均**完好**（本机 Node v24.19.0 的 `rmSync` 不跟随 junction）。

### 4. 真树只读核验（证明未触碰真树）

```
$ git -C H:/git/Multi-Workers worktree list
H:/git/Multi-Workers 55be3d960 [dev/AgentTeam]          # 仅主 worktree，本次未 add/remove/prune

$ (Get-ChildItem H:\git\Multi-Workers\node_modules -Force | Where-Object { $_.Attributes -match 'ReparsePoint' }).Count
5                                                       # 顶层 pi-extension-* 链
$ (Get-ChildItem H:\git\Multi-Workers\node_modules\@earendil-works -Force | Where-Object { $_.Attributes -match 'ReparsePoint' }).Count
9                                                       # 嵌套 @earendil-works\* 链
# 5 + 9 = 14，与 design §1 记载的 14 条（9 条 @earendil-works/* + 5 条 pi-extension-*）完全一致，未改动
```

未执行：`npm install`/`npm ci`、真仓 `git worktree add|remove|prune`、`git checkout|reset|clean|stash`、真仓 `rm`、`npm run diff:model-catalog`。

### 5. `npm run check`（完整输出不 tail）

**Run #1（主改动完成后、仅最后一行提示文案微调之前）**：退出码 0。

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1151 files in 674ms. No fixes applied.

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

CHECK_EXIT=0
```

**Run #2 / #3（最终代码）**：退出码 1，唯一的 warning 来自**另一并发会话**正在写的新文件 `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（本任务写面之外；biome 配置忽略 `scripts/`，本次检查未处理本文件）。Run #2 报在 `:158`，Run #3（几分钟后重跑）同一条报在 `:172` —— 行号漂移证明该文件仍在被另一会话编辑：

```
packages\coding-agent\test\suite\worktree-junction-guard-decide.test.ts:172:46 lint/suspicious/noTemplateCurlyInString ━━

  ! Unexpected template string placeholder.

    171 │ 	it("allows a resolvable interpolation pointing at a clean worktree (reverse control)", () => {
  > 172 │ 		for (const token of ['"$env:WJG_CLEAN"', '"${WJG_CLEAN}"', '"%WJG_CLEAN%"', "$WJG_CLEAN"]) {
        │ 		                                           ^^^^^^^^^^^^
    173 │ 			const verdict = decideWorktreeRemove(`git worktree remove --force ${token}`, os.tmpdir(), BASE_ENV);
    174 │ 			expect(verdict.block, token).toBe(false);

  i Turn the string into a template string.

Checked 1153 files in 679ms. No fixes applied.
Found 1 warning.
```

为证明该失败与本改动无关，逐段复跑 `npm run check` 的其余各级（退出码 0）：

```
$ npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap \
    && npm run check:install-lock:coding-agent && npx tsgo --noEmit && npm run check:browser-smoke
... check:shrinkwrap -> packages/coding-agent/npm-shrinkwrap.json is up to date.
... check:install-lock:coding-agent -> packages/coding-agent/install-lock is up to date.
... tsgo --noEmit -> (无输出)
... check:browser-smoke -> (无输出)
REST_EXIT=0
```

（Run #1 与 Run #2 之间工作树新增 `worktree-junction-guard-decide.test.ts` 等另一会话产物，故文件数 1151 → 1153。）

## 改动历史

| 文件 | 状态 | 说明 |
|---|---|---|
| `scripts/diff-model-catalog.mjs` | ` M`（`git status --porcelain` 实测：` M scripts/diff-model-catalog.mjs`） | 本任务唯一代码改动，见「证据 §1」 |
| `.agenticdoc/mw-worktree-junction-guard/evidence/T-W07-model-catalog-script-20261013.md` | `??`（新建） | 本报告 |

按 `git status --porcelain` 核对：本会话只动上述两个文件；仓库内其余 ` M`/`??` 条目（`packages/multi-workers/*`、`packages/coding-agent/src/extensions/agent-team-loop/*`、其它 evidence 等）均来自同期其它 worker，未由本会话写入（本会话对其只读）。

注：卡片要求的 `npm run check` 首步是仓库级 `biome check --write .`；Run #2 报告 `Fixed 2 files`，均为同期其它会话新写入、格式化未完成的文件（本会话写入的 `scripts/diff-model-catalog.mjs` 被 biome 配置忽略，未被处理）。本会话未对这些文件做任何显式编辑。

## 残留与未验证

1. **完整 `npm run diff:model-catalog` 未执行**。理由：它会在真仓 `H:\git\Multi-Workers` 上 `git worktree add`，在 `%TEMP%` 的 worktree 内建 `node_modules` junction 指回**真树** `H:\git\Multi-Workers\node_modules`（含 5 条顶层 + 9 条 `@earendil-works\*` 嵌套 reparse point），随即跑被测逻辑 —— 修复前形态即 2026-10-09 事故的完整复刻路径；即便修复后形态在本机应安全，在真树执行仍违反卡片「写入禁止面」。故按卡片要求走**夹具内等价步骤复演**（证据 §3）。
2. **中止分支为复演而非整脚本执行**：`detachBaselineNodeModulesLink` 是脚本内**原样抽取**的真实源码；`finally` 的"拒绝 remove"决策用同构 replica（相同的 `worktreeSitePreserved` 条件 + 记录是否调用）复演。未在 `mkdtemp` 不可预测路径上制造**真实** `cmd /c rmdir` 失败来驱动真实 `finally`（需在竞态窗口对 junction 持有 deny-delete 句柄）。
3. **非 Windows 未实测**：宿主为 win32，`unlinkSync` 分支为静态实现，仅有 `node --check` 覆盖。
4. **`baselineWorktree/node_modules` 为真实目录（非 reparse point）的分支未夹具验证**：该形态下 helper 返回"无链可摘"，随后 `git worktree remove` 照常执行。只可能由被 tracked 的 `node_modules` 触发，而仓库 `.gitignore` 排除之，故不在脚本可达路径上。
5. **对卡片要求 3 的显式偏离（已判定为必要）**：`rmSync(temporaryRoot, ...)` 现在由 `!worktreeSitePreserved` 保护。正常路径完全不变（仍是 `finally` 的最后一条语句）；仅中止分支跳过，以满足要求 2 的"**保留 worktree 现场**"。本机实测 `rmSync` 并不穿透 junction（证据 §3 辅助探测），故跳过是"保留现场"纪律所需，而非防止穿透 —— 但若不加该保护，中止路径会把现场连同 worktree 一起删掉，与要求 2 冲突。
6. 中止路径新引入 `process.exitCode = 1`（现有错误路径与退出码未变）。这是 fail-closed 的显式信号，设计依据 `design.md` §4.2「中止 = 逐级 return 1」；若评审认为中止也应保持 0，仅需删掉工作树 288 行。
7. `npm run check` 在 Run #2 因外部并发文件失败（见证据 §5），非本改动引入；该文件属 W-05 写面，本会话不可修改。

## 上下文来源

- 卡片：`.agenticdoc/mw-worktree-junction-guard/tasks/T-W07-model-catalog-script.md`；spec `spec.md` §G5/AC-013；design `design.md` §3.6（G1 覆盖不到的触发面）、§4.2（六步事务/中止保留现场）、§9（AC-013 验证行）
- 事故实测：`.agenticdoc/mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`（`git worktree remove --force` 穿透 reparse point；`cmd /c rmdir` 无 `/S` 只摘链；两根链可穿两层）
- 触发面复核：`design-necessity-rq3-live-surface-20261013.md`（仓库自带触发脚本）
- 代码：`scripts/diff-model-catalog.mjs`（HEAD `1ae064099`，blob `e00563f7633bce0710d29893dcff27658d489c1a`）；`package.json:28`（`npm run diff:model-catalog`）
- 环境：Windows `10.0.26100` / PowerShell `5.1.26100.9168` / `git 2.53.0.windows.1` / `node v24.19.0`

POS: reproduced (pre-fix form: A-side packages/x/f1.txt + f2.txt missing after `git worktree remove --force`, fixture `%TEMP%\wjg-w07\AC013-pos`) | NEG: clean (detach then remove: link `lstat` = ENOENT; removed/added/content_changed/mtime_changed/missing_after all 0; fixture `%TEMP%\wjg-w07\AC013-neg`) | CHECK: 1 error (external: `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts:172` lint/suspicious/noTemplateCurlyInString, another concurrent session's in-flight file outside this task's write face; all other stages exit 0)
