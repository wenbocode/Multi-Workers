# T-W11 — AC-013 常驻回归测试：摘链原语抽成可测模块（QG F-05）

- key: `mw-worktree-junction-guard` · worker: `wjg-w11-detach-module-test` · type: coding · 日期: 2026-10-13
- 卡片: `tasks/T-W11-detach-module-test.md`（card_sha256 `62be974c5784f16aded0fd0330f42a9445bfa6be77b1255462df62cb598ff5ea`）
- 目标锚点: `.agenticdoc/goal.md`（G5 · AC-013）；spec: `spec.md`；design: `design.md` §3.6 / §4.2 / §9
- 上游: W-07 `evidence/T-W07-model-catalog-script-20261013.md`（AC-013 修复 + 一次性夹具证据）；独立 QG 记为 F-05（无入库测试）

## 结论

F-05 已闭环。摘链原语从顶层脚本移入**无顶层副作用**的新模块 `scripts/detach-node-modules-link.mjs`，`scripts/diff-model-catalog.mjs` 只改为 import + 消费结构化结果，**行为不变**（正常/跳过/中止三条路径的打印与退出码逐字保持，见证据 §5 的三处 before→after 对照）。新增 `scripts/detach-node-modules-link.test.mjs`：**7 条用例全绿**，四个必需场景（NEG-1 / NEG-2 / POS-1 / ABORT-1）全覆盖，另加 NEG-3（普通文件）与 ABORT-2（自检兜底）、ABORT-3（win32 真实 `cmd /c rmdir` 失败，非注入）。`npm run test:scripts` 8/8（含既有 `sync-versions.test.mjs` 无回归，exit 0）；`npm run check` exit 0、零 error/warning/info。

模块对外的唯一扩展是测试接缝 `options.removeLink`（默认仍走平台删除：win32 `cmd /c rmdir`（无 `/S`）/ 非 win32 `unlinkSync`）；生产调用方 `diff-model-catalog.mjs` 不传该选项，默认行为逐字未变。未运行 `npm run diff:model-catalog`，未对真树做 `git worktree add|remove|prune`，未触碰真树 `node_modules` 下的 junction。

## 证据

### 1. 抽出的原语（`scripts/detach-node-modules-link.mjs`，新建）

- `removeNodeModulesLink(link)`（:7–14）= W-07 `detachBaselineNodeModulesLink` 内的删除分支**逐字搬运**：win32 `execFileSync("cmd", ["/c", "rmdir", link], { stdio: "inherit" })`（无 `/S`、无尾分隔符）/ 非 win32 `unlinkSync(link)`。
- `detachNodeModulesLink(worktreePath, options = {})`（:27–57，`export`）= 同函数主体逐字搬运 + 结构化返回：
  - `lstatSync(link)` 抛 `ENOENT` ⇒ `{status:"skipped", link, reason:"link not present"}`（:36）；
  - `!stats.isSymbolicLink()` ⇒ `{status:"skipped", link, reason:"not a link"}`（:40）；
  - 删除抛错 ⇒ `{status:"failed", link, reason:<error.message>}`（:45）；
  - 自检 `lstatSync(link)` 抛 `ENOENT` ⇒ `{status:"detached", link, reason:"link removed"}`（:52）；
  - 自检仍命中 ⇒ `{status:"failed", link, reason:<link> still exists after detaching the link}`（:56）。
- `link = join(worktreePath, "node_modules")`，与 W-07 的 `join(baselineWorktree, "node_modules")` 同值。
- 无顶层副作用：仅 import `node:child_process`/`node:fs`/`node:path` 并定义两个函数；不读 `process.argv`、不跑 git、不建临时目录。可被 `node --test` 安全 import。
- 唯一行为扩展：`options.removeLink ?? removeNodeModulesLink`（:28）测试接缝；省略时即默认删除函数。

### 2. 用例执行（`node --test scripts/detach-node-modules-link.test.mjs`，实测输出）

```
✔ NEG-1: a missing node_modules entry is skipped and changes nothing (3.5832ms)
✔ NEG-2: a plain non-empty node_modules directory is skipped and keeps its content (1.9489ms)
✔ NEG-3: a plain node_modules file is skipped and keeps its content (1.2982ms)
✔ POS-1: a real directory link is detached without touching its target (376.3383ms)
✔ ABORT-1: a throwing removal reports failed and preserves both the link and its target (39.3962ms)
✔ ABORT-2: a removal that leaves the link behind is reported as failed by the self-check (39.5406ms)
✔ ABORT-3: a real cmd rmdir failure (link path outside cmd quoting) reports failed (62.8058ms)
```

逐条断言（`scripts/detach-node-modules-link.test.mjs`）：

| 用例 | 行 | 夹具 | 实测 status | 断言 |
|---|---|---|---|---|
| NEG-1 | 89 | `worktree/tracked.txt`，无 `node_modules` | `skipped` | `result.link === join(worktree,"node_modules")`；`snapshotDirectory(worktree)` 前后 `deepEqual`（含文件内容、size、mtimeMs） |
| NEG-2 | 107 | `worktree/node_modules` = 非空普通目录（`keep.txt`） | `skipped` | 目标目录内容快照前后 `deepEqual`；`lstatSync(existing).isDirectory() === true`（**判定依据**：实现先 `lstat` 再 `isSymbolicLink()` 早退，普通目录不进入删除分支 ⇒ 语义为 `skipped`，不是 `failed`） |
| NEG-3 | 126 | `worktree/node_modules` = 普通文件 | `skipped` | 文件内容仍为 `"not a link\n"`；`lstatSync(existing).isFile() === true` |
| POS-1 | 144 | `target/{a.txt,nested/b.txt}` + `worktree/node_modules` → junction/symlink 指向 `target` | `detached` | `assert.throws(() => lstatSync(link), { code: "ENOENT" })`；`snapshotDirectory(target)` 前后 `deepEqual`（内容 + size + mtimeMs 全等）；`lstatSync(target).isDirectory() === true` |
| ABORT-1 | 160 | 同上 + 注入抛错删除函数 | `failed` | `reason` 匹配 `/simulated rmdir failure/`；目标快照零变化；`lstatSync(link).isSymbolicLink() === true`（现场保留） |
| ABORT-2 | 180 | 同上 + 注入 no-op 删除函数 | `failed` | `reason` 匹配 `/still exists after detaching the link/`（自检兜底）；目标快照零变化；链仍在 |
| ABORT-3 | 196 | 同上，junction 建好后把 worktree 目录 `renameSync` 成 `worktree&dir` | `failed` | `reason` 匹配 `/Command failed: cmd \/c rmdir/`（真实 `cmd` 非零退出）；目标快照零变化；链仍在 |

（本机 Node v24.19.0 / win32；ABORT-3 以 `{skip: isWindows ? false : "..."}` 在非 win32 跳过，其余 6 条跨平台可跑。）

### 3. ABORT 注入手法与理由

- **ABORT-1（主手法，跨平台确定）**：对模块注入 `removeLink: () => { throw new Error("simulated rmdir failure"); }`，让"删除"这一步必然失败，验证 `{status:"failed"}`、现场保留（链 + 目标零变化）。选它是因为它跨 win32/Linux 确定复现，且不依赖任何 OS 权限/路径怪癖。
- **ABORT-2（自检兜底，跨平台确定）**：注入 `removeLink: () => {}`（no-op，不抛）。删除"成功"但 `lstatSync(link)` 仍命中 ⇒ 走 W-07 的 fail-closed 自检分支，返回 `failed` 而非误报 `detached`。这条直接覆盖 W-07 证据里的"自检必须 ENOENT"。
- **ABORT-3（真实删除失败，非注入，win32-only）**：先用普通路径建 junction，再 `renameSync(worktree, "worktree&dir")`。模块默认删除走 `execFileSync("cmd", ["/c", "rmdir", link])`；Node 的 Windows 参数拼装**不引用** `&`，于是 `cmd` 在 `&` 处切分命令行，`rmdir <root>\worktree` 找不到文件、后续 `dir\node_modules` 又把退出码洗成 0 —— 实测 `rmdir` 一侧失败、`execFileSync` 抛 `Command failed: cmd /c rmdir C:\...\worktree&dir\node_modules`（先前的独立探针复现，见「残留」第 3 条）。这条证明**默认删除函数本身**（不是桩）的失败也会被结构化上报为 `failed`。
- **为什么不用"非空普通目录"做 ABORT**：实测该形态被实现的 `!stats.isSymbolicLink()` 早退判为 `skipped`（见 NEG-2 判定依据），不是 `failed`；卡片允许"具体手法由你实测选定"。
- 为什么需要接缝：跨平台确定失败无法仅靠 OS 构造（win32 的 `&` 手法在 Linux 上路径合法、`unlinkSync` 会成功 ⇒ 实测为 `detached`）。接缝只在测试传参时生效，`diff-model-catalog.mjs` 不传，默认行为不变。

### 4. 夹具路径与清理

- 夹具根：`mkdtempSync(join(tmpdir(), "pi-detach-node-modules-link-"))` ⇒ `%TEMP%\pi-detach-node-modules-link-<random>`（本机 `%TEMP%` = `C:\Users\wenbozhou\AppData\Local\Temp`）。链目标一律建在夹具根内（`<root>\target`），不指向真树。
- 建链：win32 `cmd /c mklink /J <link> <target>`；非 win32 `symlinkSync(target, link, "dir")`。
- 清理（每条用例 `finally`，`cleanupFixture`，测试文件 :48–59）：先逐条 `cmd /c rmdir <link>`（**无 `/S`**；非 win32 `unlinkSync`）→ 再删夹具根（win32 卡片的 `rd /S /Q <root>` 由等价且不穿透 reparse point 的 `rmSync(root, {recursive:true, force:true})` 承担，异常路径用 `try/catch` 兜底）。
- 跑完实测残留夹具数 = 0：

```
$ (Get-ChildItem $env:TEMP -Directory -Filter "pi-detach-node-modules-link-*").Count
0
```

### 5. `scripts/diff-model-catalog.mjs` 行为未变：三处 before→after

| 处 | W-07 工作树（before） | 本次（after） | 等价性 |
|---|---|---|---|
| 摘链 | `detachBaselineNodeModulesLink(baselineWorktree)`（:161–187），成功返回 `undefined`，失败 `throw`；内部 win32 `cmd /c rmdir` / 非 win32 `unlinkSync` | `const detachResult = detachNodeModulesLink(baselineWorktree)`（:252）；删除原语逐字搬入模块 :7–15 | 同一路径、同一删除命令（含 `stdio:"inherit"`）；无链/非链 ⇒ `skipped`（原为静默 return） |
| 自检 | `lstatSync(link)` 仍命中 ⇒ `throw new Error(`${link} still exists after detaching the link`)` | 返回 `{status:"failed", reason:"<link> still exists after detaching the link"}` | 字符串逐字相同；调用方打印同一句 |
| abort | `try { detach } catch (error) { worktreeSitePreserved = true; process.exitCode = 1; console.error("... Refusing ...: " + error.message); printManualDetachHint(...) }`（:285–292） | `if (detachResult.status === "failed") { ...同上四步... }`（:253–259） | 同样的 `worktreeSitePreserved=true` / `process.exitCode=1` / 同一格式错误行 / 同一 `printManualDetachHint`；随后 `!worktreeSitePreserved` 才 `git worktree remove --force`（:261）与 `rmSync(temporaryRoot)`（:269） |
| 未预期 lstat 错误（非 ENOENT） | helper rethrow → 调用方 catch → 打印 `error.message` | 模块返回 `failed, reason=error.message` | 调用方输出逐字相同 |

接线 diff（`git diff` 摘要，HEAD→工作树已含 W-07 改动；本任务相对 W-07 的净变化）：

- import：移除 `lstatSync`/`unlinkSync`/`execFileSync`，新增 `import { detachNodeModulesLink } from "./detach-node-modules-link.mjs";`（:16）。
- 删除脚本内 `detachBaselineNodeModulesLink` 整体；`printManualDetachHint` 保持在脚本内（未动）。
- `finally` 由 `try/catch` 改为消费 `detachResult.status`（:249–272），`worktreeSitePreserved` 的挡 remove / 挡 `rmSync` 语义不变。
- `node --check scripts/diff-model-catalog.mjs` exit 0。

### 6. `npm run test:scripts`（完整输出，exit 0）

```
> pi-monorepo@0.0.3 test:scripts
> node --test scripts/*.test.mjs

✔ NEG-1: a missing node_modules entry is skipped and changes nothing (3.5832ms)
✔ NEG-2: a plain non-empty node_modules directory is skipped and keeps its content (1.9489ms)
✔ NEG-3: a plain node_modules file is skipped and keeps its content (1.2982ms)
✔ POS-1: a real directory link is detached without touching its target (376.3383ms)
✔ ABORT-1: a throwing removal reports failed and preserves both the link and its target (39.3962ms)
✔ ABORT-2: a removal that leaves the link behind is reported as failed by the self-check (39.5406ms)
✔ ABORT-3: a real cmd rmdir failure (link path outside cmd quoting) reports failed (62.8058ms)
✔ synchronizes private dependencies without touching registry aliases, generated manifests, or published lockstep (422.8469ms)
ℹ tests 8
ℹ suites 0
ℹ pass 8
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 597.5468

TEST_SCRIPTS_EXIT=0
```

（第二次复跑同样 exit 0、8/8。既有 `sync-versions.test.mjs` 未回归。）

### 7. `npm run check`（完整输出，不 tail，exit 0）

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1154 files in 750ms. No fixes applied.

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

零 error / warning / info。`biome.json` 的 `files.includes` 只覆盖 `packages/*/{src,test}` 等 TS 路径，`scripts/**` 不在其内（W-07 报告已记同一事实）；三个新/改脚本另经 `node --check` 各 exit 0。

### 8. 真树只读核验（证明未触碰）

```
$ git worktree list
H:/git/Multi-Workers 55be3d960 [dev/AgentTeam]      # 仅主 worktree，未 add/remove/prune

$ (Get-ChildItem H:\git\Multi-Workers\node_modules -Force | Where-Object { $_.Attributes -match 'ReparsePoint' }).Count
5
$ (Get-ChildItem H:\git\Multi-Workers\node_modules\@earendil-works -Force | Where-Object { $_.Attributes -match 'ReparsePoint' }).Count
9
# 5 + 9 = 14，与 design §1 记载一致，未改动
```

未执行：`npm run diff:model-catalog`、真仓 `git worktree add|remove|prune`、`git checkout|reset|clean|stash`、仓库内 `rm`、`npm install`；未 import 顶层脚本本体。

## 改动历史

| 文件 | 状态（`git status --porcelain -- scripts/`） | 说明 |
|---|---|---|
| `scripts/detach-node-modules-link.mjs` | `??`（新建） | 摘链原语宿主；`removeNodeModulesLink` :7–15（逐字搬运）、`detachNodeModulesLink` :27–57（结构化 `{status,link,reason}` + `options.removeLink` 接缝） |
| `scripts/diff-model-catalog.mjs` | ` M` | 仅接线：:16 import 模块；删除脚本内原语函数；`finally` :249–272 改消费 `detachResult.status`，打印/退出码/现场保留语义不变（见证据 §5） |
| `scripts/detach-node-modules-link.test.mjs` | `??`（新建） | 7 条用例（NEG-1/2/3、POS-1、ABORT-1/2/3）+ 夹具/清理/快照辅助 |
| `.agenticdoc/mw-worktree-junction-guard/evidence/T-W11-detach-module-test-20261013.md` | `??`（新建） | 本报告 |

`git status --porcelain -- scripts/` 本会话条目 = ` M scripts/diff-model-catalog.mjs` + `?? scripts/detach-node-modules-link.mjs` + `?? scripts/detach-node-modules-link.test.mjs`，与卡片预期（1 新模块 + 1 改 + 1 新测试）一致。仓库内其余 ` M`/`??`（`packages/**`、`.agenticdoc/**` 其它文件）均来自同期其它 worker，本会话只读。

## 残留与未验证

1. **未做整脚本端到端执行**：`scripts/diff-model-catalog.mjs` 的 `finally` 仍无法在不碰真树的前提下整脚本运行（顶层 `git worktree add`）。本次只验证"模块语义 + 调用方接线"；调用方三处决策的等价性以代码级 before→after 对照 + `node --check` 支撑（证据 §5），未在真实 `finally` 上跑通。
2. **非 win32 只做静态/分支推断**：宿主为 win32，`unlinkSync` 分支未在 Linux 实跑；ABORT-3 在非 win32 显式跳过。CI（`ubuntu-latest`）会跑 NEG-1/2/3、POS-1、ABORT-1/2 六条。
3. **ABORT-3 依赖 Node 的 Windows 参数拼装不引用 `&`**：本机 Node v24.19.0 实测成立（独立探针，见下），并已按 `win32` 门控。若未来 Node 改为引用该参数，该用例会在 win32 上转为 `detached` 而失败——它不是生产逻辑缺陷，只是测试对 Node/cmd 行为的依赖。
4. **ABORT-3 会产生 `cmd` 的继承 stderr 输出**（模块默认 `stdio:"inherit"` 是 W-07 既有行为，为保持逐字不变未改）：`npm run test:scripts` 顶部会出现 `系统找不到指定的文件。/ ... H:\ 的目录` 噪声，随后正常打印 7 条 ✔。可用 `--test-reporter` 过滤，但未改默认删除函数。
5. **一次性探针**：为选定 ABORT-3 手法，曾在 `%TEMP%\wjg-w11-probe.mjs` 跑过独立探针（构造 `weird&dir\node_modules` junction，确认 `cmd /c rmdir` 抛 `Command failed: cmd /c rmdir ...`）；该文件已删除，其夹具目录由脚本自清理。
6. `scripts/**` 不在 biome `files.includes` 内，故 `npm run check` 的 biome 阶段实际不检查本次三个脚本；"零 warning"不代表 biome 已审阅它们（`node --check` 已过）。若评审要求，可另行把 `scripts/**` 纳入 biome includes——超出本卡片写面。
7. 本报告未新增 AC 级行为；`options.removeLink` 是唯一 API 面扩展，未被生产调用方使用。

## 上下文来源

- 卡片：`.agenticdoc/mw-worktree-junction-guard/tasks/T-W11-detach-module-test.md`；spec `spec.md` §G5/AC-013；design `design.md` §3.6 / §4.2 / §9
- 上游修复与一次性证据：`.agenticdoc/mw-worktree-junction-guard/evidence/T-W07-model-catalog-script-20261013.md`（摘链原语、自检 fail-closed、abort 保留现场、`rmSync` 不穿透 junction 的实测）
- QG 发现 F-05：`.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`
- 事故实测：`.agenticdoc/mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`
- 代码：`scripts/diff-model-catalog.mjs`（HEAD blob `e00563f7633bce0710d29893dcff27658d489c1a` → W-07 工作树 305 行 → 本次 272 行）；`package.json:34`（`test:scripts` = `node --test scripts/*.test.mjs`）；`scripts/sync-versions.test.mjs`（同类测试参照形态）
- 环境：Windows `10.0.26100` / PowerShell `5.1.26100.9168` / `git 2.53.0.windows.1` / `node v24.19.0`

TESTS: 8/8 (new file 7/7 + existing `sync-versions.test.mjs` 1/1) | status 覆盖: skipped/detached/failed | CHECK: clean
