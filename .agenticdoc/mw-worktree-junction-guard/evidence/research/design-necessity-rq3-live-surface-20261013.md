# RQ-N3 调研报告：事故面与工作流现状（必要性调研，design 期）

- key: `mw-worktree-junction-guard` · 卡: `tasks/T-N3-live-surface.md` · type: research · 采集日期: 2026-10-13
- 方法: **真树只读**（`lstat`/`readlink`/`scandir`/`git ls-files`/`git worktree list`/`git status`），未跑 `npm install`/`npm ci`、未建/删任何 worktree 或 junction、未 `checkout`/`reset`/`clean`/`stash`；唯一写入 = 本文件；探测脚本写在 `%TEMP%\rq3-n3\`
- 环境（实测）: Windows 10.0.26100 / PowerShell 5.1.26100.9168 / git 2.53.0.windows.1 / node v24.19.0 / Python 3.14.3；repo HEAD `55be3d960bb8402a262fb3fcccdcc27fda3f2ed9`（分支 `dev/AgentTeam`）

## 0. 结论先行

**判定：事故面仍然存在（且比 2026-10-09 事故当夜更"制度化"了）。**

| 维度 | 今天（2026-10-13）的实测状态 | 与事故当夜相比 |
|---|---|---|
| 仓库内"弹药"（指回 `packages/**` 的 junction） | `node_modules` 全深度剪枝扫描 = **14 条 reparse point，全部 Junction，目标全部存在且全部落在仓库内** | 同（14 条，构成未变） |
| 仓库外"活雷"（指回本仓的 junction） | `%TEMP%` 全深度扫描 = **1 条**：`%TEMP%\mwvg-t5\node_modules -> H:\git\Multi-Workers\node_modules`（目标存在） | 事故当夜的 `qg-head` 已消失，但 `mwvg-t5` 这条旧雷**原样未动** |
| 产生条件（`npm install`/`npm ci` 会不会重建链） | **仍然成立**：`package.json:9-15` 的 7 组 `workspaces` + `package-lock.json` 里 **恰好 14 条 `"link": true` 条目**，与今天的 14 条链 1:1。10-09 与 10-10 两次事故都是 `npm install --ignore-scripts` 把被删的 9 条 `@earendil-works/*` 重建回来的（实测记录） | 同（结构性） |
| 使用面（谁会去删 worktree） | **仍然活跃**：全部会话已执行的 `worktree remove|add|prune` bash toolCall = **151 条**（remove 84 / add 65 / prune 2），最近一次 add/remove = **2026-10-13T09:01Z（本地 17:01）对真仓建/删 `%TEMP%\mw-head-check`**；更关键：仓库自带脚本 `scripts/diff-model-catalog.mjs:148/157/235` **默认就建 junction + `git worktree remove --force`** | **新增**：事故当夜是 agent 临时起意，今天是"一条 `npm run diff:model-catalog` 就能复刻" |
| 是否已复发 | **已复发**：2026-10-10 11:28（本地）第三次同机制事件，删 **3456** 个已跟踪文件 + 再次静默丢弃他人未提交改动 | — |
| 是否出现"新变体" | **不成立**：事故方自述"`Remove-Item -Recurse -Force` 跟随了 junction"，但命令序与错误签名都指向**同一台 `git worktree remove --force`**（详见 §4.2）。受控实验（`spec-junction-semantics-20261009.md` §2.1）实测 `Remove-Item -Recurse` 默认不穿透 | — |

**如果今天什么都不做，最坏会发生什么**：任何人（agent 或人类）执行 `npm run diff:model-catalog`（或再次像 10-09/10-10 那样在 `%TEMP%` 建 worktree + `mklink /J node_modules`），`git worktree remove --force` 会沿 `worktree\node_modules -> 真树 node_modules -> @earendil-works\pi-* -> packages\*` **两层穿透**，再次删掉约 **3456** 个已跟踪文件（8 个包整树 + `packages/tui` 部分），并**静默丢弃当时所有会话的未提交改动**；`%TEMP%\mwvg-t5\node_modules` 这条活雷今天仍然指回真树，一旦有人对 `%TEMP%\mwvg-t5` 执行 `git worktree remove`/递归删除，同样即触。前三次事件都是"删除后数分钟内无人报警、靠另一个 worker 撞见"，G4 缺失即等于无告警。

---

## 1. 事故面全量盘点（今天）

### 1.1 仓库内 `node_modules` 全部 reparse point（深度遍历、命中不下钻、不跟进链接）

命令（只读；脚本 `%TEMP%\rq3-n3\linkinv.py`，显式栈 + 命中 reparse point 即不再下钻）：

```
python %TEMP%\rq3-n3\linkinv.py
```

原始输出（逐条，已按路径排序）：

```
[rq3] linkscan root=H:\git\Multi-Workers\node_modules dirs=1988 entries=24290 links=14 errors=0 ms=137.1
[rq3] link type=Junction tag=2684354563 exists=True inside_repo=True
            path=H:\git\Multi-Workers\node_modules\@earendil-works\pi-agent-core
            target=h:\git\multi-workers\packages\agent
... (pi-ai->packages\ai, pi-client->packages\client, pi-coding-agent->packages\coding-agent,
     pi-evals->packages\evals, pi-protocol->packages\protocol, pi-server->packages\server,
     pi-session-backend-sqlite-node->packages\session-backends\sqlite-node, pi-tui->packages\tui)
[rq3] link type=Junction tag=2684354563 exists=True inside_repo=True
            path=H:\git\Multi-Workers\node_modules\pi-extension-custom-provider-anthropic
            target=h:\git\multi-workers\packages\coding-agent\examples\extensions\custom-provider-anthropic
... (pi-extension-custom-provider-gitlab-duo, pi-extension-gondolin, pi-extension-sandbox, pi-extension-with-deps)
[rq3] top_level_links=5 nested_links=9
[rq3] all_targets_exist=True
[rq3] all_targets_inside_repo=True
```

判据与计数：

| 项 | 值 |
|---|---|
| reparse point 总数 | **14**（9 条 `@earendil-works/*` 嵌套 + 5 条 `pi-extension-*` 顶层） |
| reparse tag | 全部 `2684354563` = `IO_REPARSE_TAG_MOUNT_POINT`（Junction），**无 SymbolicLink** |
| 目标存在性 | `all_targets_exist=True`（14/14 目标可解析） |
| 目标是否在仓库内 | `all_targets_inside_repo=True`（14/14 指向 `packages/**`） |
| 扫描规模/耗时 | dirs=1988 · entries=24290 · **ms=137.1** · errors=0 |
| `node_modules` 顶层条目 | 229；`@earendil-works` 条目 10（9 junction + `gondolin` 真目录） |

与 `design-observability-and-verification-20261013.md` §F4 的 14 条**逐条同名同目标**（独立复核成立）。

### 1.2 仓库外：指向本仓的链接（活雷形态）

命令（脚本 `%TEMP%\rq3-n3\extscan2.py`，显式栈剪枝、命中链接不下钻、全深度）：

```
python %TEMP%\rq3-n3\extscan2.py
```

原始输出：

```
[rq3] ext_scan root=C:\Users\WENBOZ~1\AppData\Local\Temp max_depth=64 label=TEMP-full dirs=172469 entries=524794 links=5774 errors=0 ms=16701.9 repo_pointing=1
[rq3] ext_link path=C:\Users\WENBOZ~1\AppData\Local\Temp\mwvg-t5\node_modules
            target=h:\git\multi-workers\node_modules exists=True
[rq3] ext_scan root=H:\ max_depth=2 label=H-root-depth2 dirs=76 entries=1035 links=0 errors=1 ms=11.3 repo_pointing=0
[rq3] ext_scan root=C:\Users\wenbozhou\AppData\Local max_depth=2 label=LOCALAPPDATA-depth2 dirs=39295 entries=106268 links=107 errors=2 ms=2618.6 repo_pointing=1
```

| 扫描域（时刻 2026-10-13 23:2x 本地） | max_depth | 条目数 | 链接条目 | **指向本仓** | 耗时 |
|---|---|---|---|---|---|
| `%TEMP%`（全深度） | 64 | 524,794 | 5,774 | **1** | 16.7 s |
| `%TEMP%`（depth 2，快速对账用） | 2 | 151,986 | 5,693 | **1** | 3.3 s |
| `H:\`（深度 2） | 2 | 1,035 | 0 | 0 | 11 ms |
| `H:\git`（深度 3，含本仓） | 3 | 12,321 | 14 | 14（全在仓内，§1.1 那 14 条） | 229 ms |
| `H:\tmp`（全深度；`fmr76b`/`t23wt-mine` 旧 worktree 落点） | 6 | 136 | 0 | 0 | 0.7 ms |
| `<repo>\.tmp`（全深度） | 4 | 878 | 0 | 0 | 2.2 ms |
| `%LOCALAPPDATA%`（深度 2） | 2 | 106,268 | 107 | 1（同上那条） | 2.6 s |

**唯一活雷**：`%TEMP%\mwvg-t5\node_modules` = `Junction -> H:\git\Multi-Workers\node_modules`（目标存在）。同目录下还有 `final-*.log`、`probe-*.mjs` 等 2026-09-2x 的残留文件 ⇒ `mwvg-t5` 是 2026-09-23 遗留下来的 worktree 残骸，**未登记、无人清理**。事故当夜的两条雷 `%TEMP%\qg-head`、`%TEMP%\qg2-head` 均已不存在（实测 `Test-Path=False`）。

`H:\tmp` 只剩普通文本/目录（`fmr76b`、`fmr76b9db`、`t23wt-mine`、`mwv19c`、`rq6` 等已消失），**0 条链接**。

### 1.3 worktree 注册与未登记孤儿目录

```
$ git worktree list --porcelain
worktree H:/git/Multi-Workers
HEAD 55be3d960bb8402a262fb3fcccdcc27fda3f2ed9
branch refs/heads/dev/AgentTeam

$ Test-Path .git/worktrees
False

$ Get-Item .git  ->  Hidden, Directory   （主树正常，非 linked worktree）
```

| 检查项 | 结果 |
|---|---|
| `git worktree list --porcelain` | **1 项**（只有主树）——无遗留注册 |
| `.git/worktrees/` | **不存在** |
| 未登记的孤儿 worktree 目录 | 仓库内 `.tmp\*` 5 个目录（`msc-t08-verify`/`msc-t23-verify`/`mvr-t12`/`pi-agent-t13`/`rq3c-fake`）**全部无 `.git` 文件**、无 `node_modules` ⇒ 不是 worktree，只是普通残渣目录；`H:\tmp` 0 个 |
| `%TEMP%` 里的 `.git` 文件（16 个） | gitdir 全部指向**各自 `%TEMP%` 内的临时仓**（`footer-data-provider-*\repo\.git\worktrees\src`、`pm_sc_*\repo\.git\worktrees\wt`、`e2feature-*\engine\.git\worktrees\Engine`），**无一指向本仓** ⇒ 不构成对本仓的 worktree 注册 |

**结论**：注册面今天是干净的（只有主树）。但这**不代表安全**——事故的通道从来不需要注册面：`git worktree remove --force <path>` 对**已注销但目录仍在**（`qg-head` 在 10-09 就是这样）或**从未注册的普通目录**同样穿透。真正需要盯的是 §1.1/§1.2 的链接，而它们 14+1 条全部健在。

---
## 2. 产生条件是否仍在：再跑一次 `npm install`/`npm ci` 会不会必然重建这些链

（真树禁跑 npm，本节全部为**只读证据**，逐条标注实测/推断。）

### 2.1 workspaces 声明（实测）

`package.json:9-15`：

```json
"workspaces": [
  "packages/*",
  "packages/session-backends/*",
  "packages/coding-agent/examples/extensions/with-deps",
  "packages/coding-agent/examples/extensions/custom-provider-anthropic",
  "packages/coding-agent/examples/extensions/custom-provider-gitlab-duo",
  "packages/coding-agent/examples/extensions/sandbox",
  "packages/coding-agent/examples/extensions/gondolin"
]
```

### 2.2 lockfile 里的 link 条目（实测）

```
$ python %TEMP%\rq3-n3\lock.py
[rq3] lockfileVersion= 3 lockfile_name= pi-monorepo packages_entries= 426
[rq3] link entries in lockfile = 14
    node_modules/@earendil-works/pi-agent-core -> packages/agent
    node_modules/@earendil-works/pi-ai -> packages/ai
    node_modules/@earendil-works/pi-client -> packages/client
    node_modules/@earendil-works/pi-coding-agent -> packages/coding-agent
    node_modules/@earendil-works/pi-evals -> packages/evals
    node_modules/@earendil-works/pi-protocol -> packages/protocol
    node_modules/@earendil-works/pi-server -> packages/server
    node_modules/@earendil-works/pi-session-backend-sqlite-node -> packages/session-backends/sqlite-node
    node_modules/@earendil-works/pi-tui -> packages/tui
    node_modules/pi-extension-custom-provider-anthropic -> packages/coding-agent/examples/extensions/custom-provider-anthropic
    node_modules/pi-extension-custom-provider-gitlab-duo -> packages/coding-agent/examples/extensions/custom-provider-gitlab-duo
    node_modules/pi-extension-gondolin -> packages/coding-agent/examples/extensions/gondolin
    node_modules/pi-extension-sandbox -> packages/coding-agent/examples/extensions/sandbox
    node_modules/pi-extension-with-deps -> packages/coding-agent/examples/extensions/with-deps
```

**14 条 `"link": true` 与今天磁盘上的 14 条 junction 逐条同名同目标。** 也就是说：链不是"某次操作留下的意外副产物"，而是 **npm workspace 协议的声明式产物**——lockfile 就是这样写的，`npm install`/`npm ci` 的 reify 阶段就会按它落链接。

### 2.3 观测到的"重建"实例（实测）

| 时刻（本地） | 事件 | 出处 |
|---|---|---|
| 2026-10-09 20:38:58 | `npm install --ignore-scripts` 把被事故删掉的 8 条 `@earendil-works/*` 链重建（`@earendil-works` 恢复 10 条目 = 9 junction + `gondolin`），lockfile 零改动 | `incidents-timeline-20261009.md` §2 |
| 2026-10-10 11:30:47 | 同一次事故的恢复：`@earendil-works` 被删空后，`npm install --ignore-scripts` 执行，`NPM_RC=0`、`lock_before==lock_after==BE2A414A80E2D774`、`@earendil-works entries: 10` | 会话 `2026-10-10T02-57-22-520Z_01a123be-6458-….jsonl` L217-L219 |
| 2026-10-13（今天） | 14 条链全部在位、目标全部存在 | 本报告 §1.1 |
| 会话级统计 | 全部会话里**已执行**的 `npm install`/`npm ci` bash toolCall = **43 条**（最近一次真实执行 2026-10-10T03:30Z） | 本报告 §3.1 的会话扫描脚本 |

### 2.4 结论（区分实测与推断）

- **实测**：workspaces 声明存在；lockfile 有 14 条 link；10-09、10-10 两次都由 `npm install --ignore-scripts` 成功重建链；今天的 14 条链与 lockfile 的 14 条 1:1。
- **推断（高置信，非本期实测）**：在本仓跑 `npm install` 或 `npm ci --ignore-scripts` 会**重建**这 14 条链。依据是 npm workspace reify 的语义 + 上面 43 条 npm 调用的既往结果；本期**按任务约束未在真树跑 npm**，故未做"删一条链再 install 看是否回来"的破坏性验证。
- **边界**：`npm ci` 在**仓库外的 worktree** 里跑时，产物是"指回该 worktree 自己 `packages/*`"的自指链（`design.md` §4.4 的推断，未实测）；与本仓无关，不改变本节结论。

> 因此 §1.1 里那 14 条链不是"存量遗留"，而是**每次 hydrate 都会重新长出来的常驻面**——这也解释了为什么 10-09 删掉后 20:39 就回来了。

---

## 3. 使用面是否还在：今天还有谁/什么会去删 worktree

### 3.1 会话级实测（已执行，不是"提到"）

命令（脚本 `%TEMP%\rq3-n3\sessionscan3.py` + `npmscan.py`：解析 `~/.pi/agent/sessions/--H--git-Multi-Workers--/*.jsonl`，只取 `role=assistant` 的 `toolCall.name == "bash"` 且 command 命中 `worktree (remove|add|prune|list)`）：

```
[rq3] sessions=1253 lines_scanned=152377
[rq3] executed worktree bash toolCalls total=209
[rq3] verb=add    count=65  first=2026-08-28T11:57:58.748Z last=2026-10-13T15:30:57.360Z
[rq3] verb=remove count=84  first=2026-08-28T12:03:38.277Z last=2026-10-13T15:30:56.505Z
[rq3] verb=prune  count=2   first=2026-09-10T15:20:12.752Z last=2026-10-09T12:32:28.112Z
[rq3] verb=list   count=58  first=2026-09-10T14:47:58.154Z last=2026-10-13T15:26:56.340Z
```

| 口径 | 计数 | 最近一次时间戳 |
|---|---|---|
| `worktree remove`（删除动作，事故动词） | **84** | 2026-10-13T15:30:56Z（夹具）/ 真仓最近一次 = 2026-10-13T09:01:28Z |
| `worktree add` | **65** | 2026-10-13T15:30:57Z（夹具）/ 真仓最近一次 = 2026-10-13T09:01:12Z |
| `worktree prune` | **2** | 2026-10-09T12:32:28Z（善后） |
| `worktree list`（只读） | 58 | 2026-10-13T15:26:56Z |
| **合计** | **209** | — |

真仓（非夹具）最近一次实测：

```
2026-10-13T09:01:12Z  add    :: cd H:/git/Multi-Workers; git worktree add --detach C:/Users/wenbozhou/AppData/Local/Temp/mw-head-check HEAD
2026-10-13T09:01:28Z  remove :: cd H:/git/Multi-Workers; git worktree remove --force C:/Users/wenbozhou/AppData/Local/Temp/mw-head-check
```

⇒ **今天（10-13，4 小时前）就有人对真仓建了 worktree 又 `remove --force` 删掉**；这次侥幸没有在 worktree 内放 junction（未建链），所以零后果。**使用面毫无衰减。**

### 3.2 仓库内自动化：`scripts/diff-model-catalog.mjs`（本期最重要的新发现）

`scripts\diff-model-catalog.mjs`（`package.json:28` 的 `npm run diff:model-catalog` 目标）**默认就复刻了事故的三段式**：

```
L52-53   const temporaryRoot = mkdtempSync(join(tmpdir(), "pi-model-catalog-diff-"));
         const baselineWorktree = join(temporaryRoot, "baseline-worktree");
L148     run("git", ["worktree", "add", "--detach", baselineWorktree, "HEAD"], { cwd: repoRoot });
L153-158 const nodeModules = join(repoRoot, "node_modules");
         if (existsSync(nodeModules)) {
             symlinkSync(nodeModules, join(baselineWorktree, "node_modules"),
                         process.platform === "win32" ? "junction" : "dir");
         }
L233-236 if (worktreeAdded) {
             try { run("git", ["worktree", "remove", "--force", baselineWorktree], { cwd: repoRoot }); }
             ... }
```

即：**worktree（`%TEMP%\pi-model-catalog-diff-*\baseline-worktree`）+ `node_modules` junction 指回真仓 + `git worktree remove --force`**，与 10-09 的 `%TEMP%\qg-head` 形态**完全同构**（连"借主树 node_modules 省一次 install"的动机都一样）。第 3 段的 `remove --force` 走的就是已被两次事故坐实的穿透路径 ⇒ **执行一次这个脚本 = 执行一次事故**。

补充实测：会话库里 `diff:model-catalog`/`diff-model-catalog` 的**已执行**记录 = **0 条**（只有本期这次 grep 命中）⇒ 这条枪**至今没被扣过扳机**，但它是 1 条命令、在正常发版流程里（`package.json` 脚本表）随时可触发。

### 3.3 测试夹具（会建 worktree，但只在 `%TEMP%` 内）

| 位置 | 行为 | 风险 |
|---|---|---|
| `packages\coding-agent\test\footer-data-provider.test.ts:61`（`createReftableWorktree`） | 在 `mkdtemp` 内手工拼 `worktrees\src` + `gitdir:` 文件 | 无（不碰真仓、无 junction） |
| `packages\coding-agent\test\resource-loader.test.ts:938-1034` | 在临时目录内搭 linked-worktree 骨架做去重测试 | 无（无 junction） |
| `packages\multi-workers\test_autopilot_readcap_injection.py:915` | 只是把 `render_task_md` 的参数名写成 `worktree_params` 变量名 | 无 |

`%TEMP%` 里现存的 16 个 `.git` 文件（`footer-data-provider-*`、`pm_sc_*`、`e2feature-*`）都是这些测试/他项目留下的**临时仓**，gitdir 指向自身，不构成对本仓的注册（§1.3）。

### 3.4 文档/仓库文本计数

```
$ rg -c "worktree\s+(remove|add|prune)" .agenticdoc -g '*.md'   | 求和
TOTAL_MATCHES_IN_agenticdoc_MD=217
```

（217 条集中在 `mw-worktree-junction-guard` 本 key 的 spec/design/证据与 `mw-workspace-incident-probe` 的证据里；`scripts/`+`packages/` 内除 `diff-model-catalog.mjs` 与上述测试外，只有 `resource-loader.ts` 的注释提及。）

### 3.5 `.mw/` 日志痕迹

```
$ rg "worktree" .mw   ->   0 命中
$ .mw/launcher.log    ->   44 字节，只有本轮派发的 4 行（max_workers=8 + 3 个 wjg-* 任务）
$ .mw/conductor.log   ->   0 字节
```

⇒ 调度侧**没有** worktree 相关流程或日志；worktree 完全由**agent 临时决定**（这正是风险点：无流程可管、无日志可查）。

---

## 4. 是否已复发 / 是否有新变体

### 4.1 已知事件族（共 3 次，口径与 `incidents-timeline-20261009.md` §4.4 一致）

| # | 时刻 | 受害面 | 机制 | 证据 |
|---|---|---|---|---|
| 1 | 2026-09-09 09:43–09:46Z | ~1100+ tracked（agent/ai/coding-agent） | `git worktree remove --force` 穿 junction | 会话 `2026-09-08T12-16-45-828Z_01a080f3-….jsonl` L539/L541/L543 |
| 2 | 2026-10-09 12:32:18Z | **3456**（8 包 3300 + `packages/tui` 156） | 同上（`%TEMP%\qg-head`） | `in1/in2/timeline` |
| 3 | 2026-10-10 03:28Z（本地 11:28） | **3456** + 再次丢弃未提交改动 | **同一条命令**（`%TEMP%\qg2-head`） | 见 §4.2（本期一手） |

### 4.2 第 3 次事件的**一手复原**（本期新证据，修正既有记录的归因）

卡给的线索只到 `in2-recurrence-20261010-uncommitted-wipe.md`（它把触发命令列为"未坐实"）。本期从会话库把**执行原文**取到了：

```
$ python %TEMP%\rq3-n3\dump6458.py
--- L202 2026-10-10T03:28:06.641Z role=assistant
  TEXT Report written. Now cleaning up the temporary worktree.
  CALL bash {"command": "cd H:/git/Multi-Workers; git worktree list; Write-Output \"=== removing ===\";
        git worktree remove --force \"$env:TEMP\\qg2-head\"; Write-Output \"rc=$LASTEXITCODE\";
        Remove-Item -Recurse -Force \"$env:TEMP\\qg2-head\" -ErrorAction SilentlyContinue;
        git worktree prune; ..."}
--- L203 2026-10-10T03:28:15.626Z role=toolResult
  C:/Users/wenbozhou/AppData/Local/Temp/qg2-head 10446aefb (detached HEAD)
  === removing ===
  error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg2-head': Invalid argument
  rc=255
--- L205 (03:28:22)  temp worktree exists: False / main node_modules entries: 220
--- L208-L209 (03:28:40)
  === deleted tracked files count ===  3456
  packages/coding-agent/dist 953 / packages/ai/dist 736 / packages/coding-agent/test 302 /
  packages/coding-agent/src 246 / packages/ai/src 175 / packages/agent/dist 160 / packages/tui/dist 148 / ...
  packages/ai/src/providers  ->  False（整目录没了）
--- L210-L211 (03:28:53-03:30:20)  git checkout -- <3456 paths, 每批 200>  => deleted_after=0
--- L230-L231 (03:31:43)  CLEAN(was modified?) rag/adapter.ts / dispatch.py / rag-block.golden.md / ui-bridge.js / pm-orchestrator.js
                          => 他人未提交改动再次被静默丢弃
--- L217-L219 (03:30:47)  npm install --ignore-scripts => NPM_RC=0, lock 不变, @earendil-works 回到 10 条目
```

**归因判定（本期结论，与事故方自述相反）**：元凶是 `git worktree remove --force "$env:TEMP\qg2-head"`，**不是** `Remove-Item`。三条理由：

1. **命令序**：`git worktree remove --force` 先执行，并且返回了 `error: failed to delete ...: Invalid argument` + `rc=255`——这正是 `git` 沿 junction 递归删除、撞到锁句柄后中止的**逐字签名**（10-09 事故同签名，`in1` §3.1 的受控复现也复刻了它）。此时破坏已经发生（10-09 时同签名对应 3300 个包文件已被删）。
2. **受害面形状**：L209 的分布含 `packages/ai/src 175`、`packages/ai/src/providers` **整目录消失**——这与"沿 `@earendil-works/pi-ai -> packages/ai` 整树穿透"一致；而 `qg2-head` 里指回真树的第二条链是 `...\packages\ai\src\providers\data`（只指向 `data` 一个目录），单独的 `Remove-Item` 无法解释整个 `providers` 子树消失。
3. **受控实验反证**：`spec-junction-semantics-20261009.md` §2.1（同期实测，21 例矩阵）**明确坐实 PS 5.1 `Remove-Item -Recurse -Force <link 或父>` 不穿透**，只有 `<link>\*` / 尾分隔符形态才穿透一层——本案的命令形态（无通配、无尾分隔符）不在穿透集内。

⇒ **不存在"新变体"**。事故方在紧张恢复过程中把自己的清理动作误当成元凶（其 §7 自述"PowerShell 的递归删除跟随了 junction"与上述三条硬证据冲突），属**误归因**。这反而暴露一个二阶风险：**现场人对机制的直觉是错的**，而 `design.md` 的 D-4 边界（不覆盖 `Remove-Item -Recurse <path>`）正是建立在这条实测语义上的，不应被这条自述推翻。

**第 3 次事件的记录残留位置（重要）**：承载 §7 自述的 `qg-review-mw-vision-role-20260926.md` 已在 2026-10-10 15:19 被整体回退到 HEAD（当前文件只有 335 行、到 §6 结束，`git log` = `5c1149f1b`），**自述原文只剩在** `.agenticdoc\_incidents\in3-queue-reenqueue-20261010\rewrites-81-20261010.patch:15067`（`+` 行）。也就是说这份"第二次/第三次"的关键证据目前**没有任何在树文件承载**，只有回退前打出的 patch。

### 4.3 2026-10-09 之后是否还有其它事件

对 `.agenticdoc/**` 全量检索（`junction` / `ls-files -d` / 消失类关键词）与 1196 个 10-11 以后的改动文件逐个过滤：

- **2026-10-11 ~ 10-13 无第二/第三次新事件**：命中全部落在事故复盘文档、本 key 的调研文档与本 key 的 design（都被 `ls-files -d` 作为**判据/夹具**引用，不是新事故现场）。
- 10-12 的 `_incidents\dispatch-card-omission-20261012\` 是**派发卡缺失**事故（非 junction/文件消失），与本案无关。
- 唯一的"复发"就是 §4.2 的 2026-10-10 一次。

**与首次事故的关系**：三次是**同一根因族**（"用会穿透 reparse point 的删除工具删一个含 junction 的目录 / 对含 junction 的 worktree 执行 `git worktree remove --force`"），不是三个独立缺陷。10-09 与 10-10 甚至由**同一张卡（`mvr-t16-quality-gate-review`，key `mw-vision-role`）的两个 run** 造成。

---

## 5. 判定

**事故面仍然存在。**

- **产生条件**：结构性（npm workspaces + lockfile 14 条 link）⇒ 任何 `npm install`/`npm ci` 都会重建这 14 条链。
- **弹药**：14 条仓内 junction（全部指向 `packages/**`，全部存活）+ 1 条仓外活雷（`%TEMP%\mwvg-t5\node_modules -> 真树 node_modules`，目标存在）。
- **使用面**：会话级 209 条已执行 worktree 命令（最长 4 小时前还在真仓 `add` + `remove --force`）；`.mw/` 无任何流程或日志覆盖它。
- **新增触发面**：仓库自带脚本 `scripts/diff-model-catalog.mjs` 默认就建 junction 并 `git worktree remove --force`（一条 `npm run diff:model-catalog` 即可复刻事故）。
- **已复发**：2026-10-10 第三次，3456 文件 + 未提交改动静默丢失，且"现场自述的元凶"是错的。
- **未发现新机制**；未发现 10-11 之后的新事件；未发现遗留 worktree 注册。

**如果今天什么都不做，最坏会发生什么**：下一次 `npm run diff:model-catalog`，或下一个像 `mvr-t16` 那样"为出可信结论在 `%TEMP%` 建 worktree + 借主树 node_modules"的 worker，会再次用 `git worktree remove --force` 把真仓 `packages/**` 的 **~3456 个已跟踪文件**删掉（8 包整树 + `packages/tui` 部分），并**静默丢弃当时全部会话的未提交改动**；由于 `.mw` 无采样、无告警，损失大概率仍要靠"另一个 worker 撞见"才发现（前三次的发现时延分别是分钟级到十几分钟级）。G1..G4 的四条护栏今天**一条都不存在**（`packages/multi-workers/mw.py` grep `worktree` = 0 命中，`mw worktree` 子命令不存在，guard 未注册，doctor 无 `worktree_links` 段）。

---

## 6. 残留与未验证

1. **未实测 `npm install` 重建链**（任务硬约束禁真树 npm）——§2 的"必然重建"是**高置信推断**，依据是 lockfile 的 14 条 link + 两次历史重建。建议实现期在 `%TEMP%` 夹具或 AC-012 端到端夹具里顺带坐实。
2. **`%TEMP%\mwvg-t5\node_modules` 的清理者与创建者未坐实**（残骸 mtime 2026-09-23；本 key 只读，未删）。它今天仍是活雷。
3. **`Remove-Item` 是否在极端形态下（通配/尾分隔符/PS 7）会穿透**：`spec-junction-semantics` 已实测常规形态不穿透；本期**未重跑**该实验（属 RQ-N2/T-N2 的 reachability 范围）。本报告只断言"10-10 那次不是它"。
4. **`scripts/diff-model-catalog.mjs` 的实际爆炸半径未实测**（未执行，避免真树损伤）。推断其与 10-09 同构（同样的双层链 + `remove --force`）；严格说属"应当会删 3456 文件"的机制演绎，不是本期观测到的删除。
5. **10-09/10-10 事故当日的 per-package dist/non-dist 拆分**未从一手反推；本报告的对照用今日构成（tracked 5061 / dist 2239）。
6. **measurement drift**：本报告所有计数绑定采集时刻 2026-10-13 23:2x~23:3x 本地；多 key 并发下 `git status` 计数会分钟级漂移（本期就观察到 tracked 从 4995 长到 5061、status 27 行）。

## 7. 未覆盖面声明

- 未扫 `C:\` 全盘、`E:\`、`D:\` 等其它盘符（只扫了 `%TEMP%`、`%LOCALAPPDATA%`、`H:\`、`H:\git`、`H:\tmp`、`<repo>\.tmp`）；若存在第三处 worktree 落点，本报告的"活雷 = 1 条"会低估。
- 未扫描 `%TEMP%` 之外的 `C:\Users\wenbozhou\AppData\Roaming` 等用户目录；未扫网络盘。
- 未解析 `%TEMP%` 5,774 条链接的**全部目标**（只判定目标是否落在本仓 `repo_root` 下）；若某条链指向本仓的**子路径但大小写/短名不同**，可能漏判（本期用 `normcase`+`normpath`+剥 `\\?\` 前缀，已尽量覆盖）。
- 会话级统计只覆盖 `~/.pi/agent/sessions/--H--git-Multi-Workers--` 一个 slug 目录（1,253 个 jsonl）；**其它 CLI（claude/codex）的会话、以及非本 slug 的会话未纳入**，故 §3.1 的 209 是下界。
- 未评估 `commandPrefix`/`spawnHook`、嵌套 shell、非 Windows 平台在这条通道上的差异（属 G1 的 design 边界）。
---

## 判定（全文收束，一句话）

**事故面仍然存在**（不是"已自然消失"）。最坏情况：下一次 `npm run diff:model-catalog`（或下一个仿 10-09/10-10 那样借主树 `node_modules` 的 `%TEMP%` worktree 清理）会再次用 `git worktree remove --force` 穿透 junction，删掉真仓约 **3456** 个已跟踪文件并**静默丢弃全部未提交改动**，而 `.mw` 侧今天没有任何采样或告警能在事中报警——G1..G4 四条护栏一条都还不存在。

## 上下文来源

（PM 补录：worker 交付内容完整；本节按证据语料规范补齐来源清单。清单取自本文件各节实际引用，不改动任何上文原文。）

| 文件 / 位置 | 行 | 用途 |
|---|---|---|
| `package.json` | `:9-15`、`:28` | 7 组 workspaces（链的产生源）；`"diff:model-catalog": "node scripts/diff-model-catalog.mjs"` |
| `package-lock.json` | `"link": true` 全量计数 | 实测 **14** 条，与磁盘 14 条链逐条同名同目标 |
| `scripts/diff-model-catalog.mjs` | `:58`、`:63`、`:148`、`:155-157`、`:161-169`、`:233-235` | **本轮最重要的新触发面**：`git worktree add --detach <临时>/baseline-worktree HEAD` → `symlinkSync(repoRoot/node_modules, <wt>/node_modules, "junction")` → 收尾 `git worktree remove --force <wt>` |
| `H:\git\Multi-Workers\node_modules\**` | 全深度剪枝扫描 | 1988 目录 / 24,290 条目 / **14** 条 Junction（tag 2684354563），目标全部存在且在仓内 |
| `node_modules/@earendil-works/*` / `node_modules/pi-extension-*` | 逐条 | 9 条 → `packages/*`；5 条 → `packages/coding-agent/examples/extensions/*` |
| `%TEMP%`（全深度）、`%LOCALAPPDATA%`、`H:\`、`H:\git`、`H:\tmp`、repo `.tmp` | — | 仓外活雷盘点：`%TEMP%` 172,469 目录 / 524,794 条目 / 5,774 链接 / 16.7 s → 指向本仓的 **1** 条；其余域 0 条；`qg-head`/`qg2-head` 已消失 |
| `git worktree list --porcelain`、`.git/worktrees/` | — | 注册面：仅主树、无遗留注册、无孤儿 |
| 会话库（`~/.pi/agent/sessions/**/*.jsonl`，1,253 个） | 全量 grep | 已执行 worktree bash toolCall **209**（`remove` 84 / `add` 65 / `prune` 2 / `list` 58）；真仓最近一次 **2026-10-13T09:01Z** `add` + `remove --force` |
| `.mw/`（`launcher.log`/`conductor.log`/`mw.log` 等） | — | 0 命中（worktree 使用痕迹不在服务日志里） |
| `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` | §4.4、§2 | 事故族（含"已知三次"）与 10-09 时间线 |
| `.agenticdoc/mw-workspace-incident-probe/evidence/in2-recurrence-20261010-uncommitted-wipe.md` | 全文 | 10-10 第二次事件的既有记录 |
| `.agenticdoc/_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch` | `:15067` | 事故方 §7 自述的唯一存留处（本轮据穿透签名更正其归因） |
| 本 key 前序证据 | — | `design-observability-and-verification-20261013.md` §F4（14 条链逐条）、`spec-junction-semantics-20261009.md`（穿透矩阵） |

PM 复核（2026-10-13，一手复看）：仓内 14 条 Junction 我独立枚举过（9 + 5，全部指向 `packages/**`）；`%TEMP%\mwvg-t5\node_modules` → `H:\git\Multi-Workers\node_modules` 确为 Junction 且目标可解析；`package-lock.json` 的 `"link": true` 确为 **14** 条；`scripts/diff-model-catalog.mjs` 的三处关键行我逐行读过 —— `:148` `git worktree add --detach <temp>/baseline-worktree HEAD`、`:155-157` `symlinkSync(repoRoot/node_modules, <wt>/node_modules, "junction")`、`:235` `git worktree remove --force <wt>`（即：**仓库自带一条与 10-09 事故同构、默认执行的路径**）；`package.json:28` 确有该 npm script。以下为 worker 实测、PM **未**独立复算：会话库统计（1,253 jsonl / 209 toolCall / 84 `remove`）——PM 的复算命令被 `protected-config` 拦下（trigger 是日期格式 `yyyy-MM-dd` 里的 `\bdd\b`，见 RQ-N1 证据的 PM 附注），故该统计目前只有单一来源；另未复算：`%TEMP%` 全深度扫描的 16.7 s 与计数、10-10 第三次事件的穿透签名比对。

## 残留与未验证

（PM 补录，与上文 `## 6. 未坐实 / 未验证`、`## 7. 未覆盖面声明` 同源，只做"对 design/规格的处置"归并。）

| 未坐实项 | 对 design / 规格的处置 |
|---|---|
| "再跑一次 `npm install`/`npm ci` 必然重建这 14 条链"是**高置信推断**（未做破坏性验证） | 结构性证据已足够（`package.json:9-15` 7 组 workspaces + lockfile 14 条 `link:true` 与磁盘逐条一致）；design 不依赖该推断做判据，仅用于"事故面持续存在"的论证 |
| `scripts/diff-model-catalog.mjs` 的执行记录为 0（会话库里没有跑过） | **这是本 key 现有 AC 覆盖不到的新面**：它不经 agent 的 bash 工具（脚本内 `run("git", ...)` 起子进程）⇒ **G1 的 tool_call hook 天然看不见**，只能靠改脚本本身（例如摘链后再 remove，或复用 G2）⇒ 建议升为规格级新增项（PM 已列入决策 D-9） |
| 会话库统计只有单一来源（PM 因 guarded 路径未能复算） | 在 design 的引用里标注"单一来源、未交叉验证"；数值只作强度证据，不作判据 |
| 10-10 第三次事件的归因更正（`git worktree remove --force "$env:TEMP\qg2-head"`，非 `Remove-Item`） | 与 `mw-workspace-incident-probe` 的 **v3 timeline 已收口、QG 已复核**冲突 ⇒ **不修改已复核文本**，改为在该 key 追加一份带日期的 amendment 证据文件（PM 待办） |
| `%TEMP%`/`%LOCALAPPDATA%` 的扫描是单时点快照 | design 的 AC-009 域决策（D-2）已按此设计：注册表域 + 仓库内域默认开，全域扫描走显式开关 |
| 未覆盖面：非 Windows 平台、其它磁盘根、云占位符类 reparse tag、`diff:model-catalog` 的真实执行 | 已逐条列在本文件 §7；其中"未真实执行该脚本"是刻意的（它会复刻事故） |
