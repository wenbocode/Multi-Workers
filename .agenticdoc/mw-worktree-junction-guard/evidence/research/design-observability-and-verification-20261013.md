# RQ-D3 调研报告：G4 可观测判据的数据源/代价 + AC-012 端到端验证夹具（design 期）

- key: `mw-worktree-junction-guard` · worker: `wjg-d3-observability-r2` · type: research（T-D3）
- 采集时刻: 2026-10-13（UTC+8）
- 环境（实测）: Windows `10.0.26100.0`; PowerShell `5.1.26100.9168`; `git 2.53.0.windows.1`; `node v24.19.0`; `Python 3.14.3`
- **只读合规**：真树 `H:\git\Multi-Workers` 零写入 —— 未改任何生产文件、未在真树建/删 worktree、未创建或删除真树的任何 junction、未对真树执行 `checkout`/`reset`/`clean`/`rm`。全部 fixture 位于 `%TEMP%\wjg-d3\**`，且所有链接目标同样在该目录内。清理一律"先 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）摘链，再 `cmd /c rmdir /S /Q <root>`"（与 `spec-junction-semantics-20261009.md:484` 同款不穿透做法）。
- 本文件是该 worker 唯一写入物。

---

## TL;DR

1. **AC-010 的正确数据源不是 `git ls-files`。** `git ls-files` 只列索引条目，磁盘文件被删后计数**不变**（实测 6→6；合成 5000 文件仓 5001→5001）。正确原语是 `git ls-files -d`（= 索引里有、磁盘上没有）或 `git status --porcelain` 的 ` D` 行。本仓实测 `git ls-files -d` = **66–88 ms / 0 行 / 0 字节**；合成 5000 文件仓删 3000 个后 **159–180 ms / 3000 行 / 79,890 字节**。
2. **误报面已被实测锁定，且必须排除 `dist`**：单文件编辑、一次 commit、切分支、`git rm -r <pkg>` 的 ΔD **全为 0**；但本仓有 **2,239** 个 tracked 文件在 `*/dist/` 下（占 `packages/` 3,825 的 58.5%），而 root `package.json:15` 的 `"clean": "npm run clean --workspaces"` + 每包 `"clean": "shx rm -rf dist"` 会让"总 D"飙到 **~2,170**（= 事故 3,456 的 63%）。排除 `dist` 后本仓 non-dist tracked = **2,756**；事故 9 包 non-dist ≈ **1,363**（今日构成推算）仍远超任何合理阈值。
3. **AC-011 数据源实测极便宜**：`node_modules/@earendil-works/*` 全量链接状态扫描 = **0.5 ms / 9 条 / 全部 `Junction` / 目标全部存在**；整个根 `node_modules` 显式栈递归（命中 reparse point 不下钻）= 1988 目录 / **14 条链接** / **185–195 ms**。
4. **TS 侧无法区分 junction 与 symlink**：Node `lstatSync` 对 junction 报 `isSymbolicLink()=true`、`isDirectory()=false`，且 `Stats` 上**没有** `fileAttributes`/`reparseTag`（`undefined`）。Python 侧 `os.path.isjunction=True` / `islink=False` / `st_reparse_tag=2684354563`；PowerShell 侧 `LinkType=Junction`。⇒ AC-011 的权威实现放 Python；TS 若要判 `LinkType` 必须 shell-out（PowerShell/`fsutil`）或走原生调用。
5. **mw 侧可挂钩的周期采样点已定位（文件:行号 + 现频率）**：`mw serve` 1 Hz（`mw.py:353` `while True` / `:376` `time.sleep(1)`）、launcher 5 s poll（`launcher.py:1899/:1901/:1905`，`DEFAULT_POLL_INTERVAL` `launcher.py:50`，每 poll 已写 beat `launcher.py:1717`）、conductor tick 默认 4 s（`conductor.py:7256` + `config.py:86`）。**建议挂 launcher 的 `_poll_once`（`launcher.py:1706`）**，每 N 次 poll（默认 6 ⇒ 30 s）采样一次。
6. **AC-012 夹具已双向跑通**：`%TEMP%` 内"假真树 A（git 仓库 + `packages/*` + `node_modules/@scope/*` junction）→ worktree B + `B\node_modules` → `A\node_modules`"双层链。unsafe 对照：`git worktree remove --force` rc=0/70 ms，A 的 tracked 5/6 消失、`@scope` 3 条链清零；safe 对照：枚举 1 条 → `rmdir`（无 `/S`）rc=0 → A 的 3 条链完好 → `remove` rc=0/113 ms → **manifest 零变化**。
7. **manifest 判据实测**：`git ls-files -z` + 逐文件 `sha256` + `mtimeMs` + `size`。真树 4,995 文件 / 60,288,001 字节：`ls_ms=48–102`、`hash_ms=368–744`、`total=418–850 ms`；等价的 `git ls-files | git hash-object --stdin-paths` = **1024 ms / 204,794 字符**。positive 对照 `missing_after=5 content_changed=5 mtime_changed=5`；negative 对照**全 0**。
8. **仓内没有现成的 junction / before-after 夹具**（`mklink|isjunction|ReparsePoint|IO_REPARSE` 在 `packages/**` 生产源码 0 命中）。可照抄的最贴近件：`mw.py:5192 _claude_adapter_drift`（rel-path 并集 + `read_bytes()` 逐文件比对）、`mw.py:4507 _git_dirty_paths` + `mw.py:4503/:4504` 的**按路径面** git status 惯例（`packages/*/src/**`，天然排除 `dist`）、`mw.py:5175 _git_dirty`、TS `test/footer-data-provider.test.ts:61`、`test/resource-loader.test.ts:943`。

---

## 事实

### F1 环境与真树基线（`[VERIFY] env`）

```
[VERIFY] env os=10.0.26100.0 ps=5.1.26100.9168 git=2.53.0.windows.1 node=v24.19.0 python=Python 3.14.3
[VERIFY] real_config core.fscache=true (D:/Program Files/Git/etc/gitconfig) core.ignorecase=true (.git/config)
        （core.untrackedCache / core.fsmonitor 均未设置 —— rc=1）
[VERIFY] real_counts tracked=4995 dist_tracked=2239 non_dist_tracked=2756 deleted=0
```

`dist` 分布（实测，全部 2,239 条都在 `packages/` 下）：

```
[VERIFY] real_dist_by_top packages=2239 ; packages/*/dist/** = 2170
```

### F2 AC-010 候选数据源的实测代价（本仓 `H:\git\Multi-Workers`，每条 3 次）

命令原文与实测：

```
[VERIFY] real_ms git ls-files                        = 130/72/70   items=4995 chars=280957
[VERIFY] real_ms git ls-files -z                     = 47/55/62    chars=280958
[VERIFY] real_ms git ls-files -d                     = 66/654/77   items=0    chars=0
[VERIFY] real_ms git status --porcelain              = 63/64/73    items=15   chars=899
[VERIFY] real_ms git status --porcelain -uno         = 57/57/60    items=11   chars=677
[VERIFY] real_ms git --no-optional-locks status --porcelain = 66/72/67 items=15 chars=899
```

（`git status --porcelain` 的行数/字节数会随其它并发会话的未提交改动浮动：复测时见到 16 行 / 1004 字节。`git ls-files` 家族字节数稳定。）

**为什么 `git ls-files` 不能当骤降判据** —— 在 `%TEMP%` 夹具中构造 6 个 tracked 文件后删掉 5 个（见 F5）：

```
[VERIFY] ls_files_after_deletion tracked=6 (与删除前一致)  deleted=5
[VERIFY] git ls-files -d -> 5 lines ; git status --porcelain -> 5 lines (" D …")
```

合成仓（5,001 tracked）删除 3,000 个 tracked 文件前后：

```
[VERIFY] scale_clean    git ls-files      ms=140/151/226 items=5001 chars=133901   (0 删除)
[VERIFY] scale_clean    git ls-files -d   ms=560/175/434 items=0    chars=0
[VERIFY] scale_clean    git status --porcelain ms=344/354/693 items=0 chars=0
[VERIFY] scale_damaged  git ls-files      ms=89/80/79    items=5001 chars=133901   ← 计数不变
[VERIFY] scale_damaged  git ls-files -d   ms=180/159/170 items=3000 chars=79890
[VERIFY] scale_damaged  git status --porcelain ms=74/77/80 items=3000 chars=88890
[VERIFY] scale_damaged  git status --porcelain -z ms=79/77/88 items=3000 chars=88890
[VERIFY] scale_damaged  git --no-optional-locks status --porcelain ms=75/72/70 items=3000 chars=88890
[VERIFY] scale_damaged  git ls-files -z   ms=60/59/58    items=5001 chars=133901
```

⇒ 代价结论：`git ls-files -d` 与 `git status --porcelain` 同量级（几十至几百 ms），但前者**只输出问题路径**、语义唯一（索引 vs 磁盘），且输出量随损坏面增长（3,000 行 / 79 KB），是本仓规模下可承受的周期采样原语。

### F3 「正常波动」实测：哪些操作会让 D 变化（阴性对照的数据基础）

小型夹具（200 tracked）逐操作采样 `tracked / present / deleted / status_lines / " D" / "M "`：

```
[VERIFY] fluct baseline                  tracked=200 present=200 deleted=0 status=0  D=0 M=0
[VERIFY] fluct single_edit               tracked=200 present=200 deleted=0 status=1  D=0 M=1
[VERIFY] fluct after_commit              tracked=200 present=200 deleted=0 status=0  D=0 M=0
[VERIFY] fluct legit_git_rm_one_pkg(10)  tracked=190 present=190 deleted=0 status=10 D=0 M=0
[VERIFY] fluct untracked_file_added      tracked=190 present=190 deleted=0 status=11 D=0 M=0
```

分支切换（`git checkout` 到少 20 个文件的提交再切回）：

```
[VERIFY] fluct2 start                    tracked=190 deleted=0 status=11 D_worktree=0 D_staged=10
[VERIFY] fluct2 on_b2_after_git_rm_commit tracked=180 deleted=0 D_worktree=0
[VERIFY] fluct2 back_on_default          tracked=200 deleted=0 D_worktree=0
[VERIFY] fluct2 on_b2_again              tracked=180 deleted=0 D_worktree=0
[VERIFY] fluct2 back_again               tracked=200 deleted=0 D_worktree=0
```

⇒ 关键区分：**`git rm`（同步索引）与 `checkout`（换索引）都不会产生 `-d`/` D`**；只有"索引未变而磁盘文件消失"才产生。这正是事故签名。反过来，任何用"tracked 总数/present 数"做判据的方案会**误报**切分支（180↔200）——这是必须用 `-d` 的硬理由。

### F4 AC-011 的数据源与代价（链接状态枚举）

`node_modules/@earendil-works` 浅层（depth 1）扫描（`[VERIFY] linkscan root=… dirs=1 visited=1 links=9 ms=0.5`），逐条：

```
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\node_modules\@earendil-works\pi-agent-core target=…\packages\agent
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-ai        target=…\packages\ai
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-client    target=…\packages\client
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-coding-agent target=…\packages\coding-agent
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-evals     target=…\packages\evals
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-protocol  target=…\packages\protocol
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-server    target=…\packages\server
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-session-backend-sqlite-node target=…\packages\session-backends\sqlite-node
[VERIFY] linkscan_row link_type=Junction target_exists=True path=…\pi-tui       target=…\packages\tui
```

整个根 `node_modules`（显式栈、命中 reparse point 不下钻，`--depth 64`）：

```
[VERIFY] linkscan root=H:\git\Multi-Workers\node_modules dirs=1987 visited=1988 links=14 ms=185.1（复测 194.9）
```

14 条 = 上面 9 条 + 5 条 `pi-extension-*`（同样全部 `Junction`、目标全部存在、目标全部在仓库内）：

```
[VERIFY] nm_extra_link path=…\node_modules\pi-extension-custom-provider-anthropic   target=…\packages\coding-agent\examples\extensions\custom-provider-anthropic
[VERIFY] nm_extra_link path=…\node_modules\pi-extension-custom-provider-gitlab-duo  target=…\packages\coding-agent\examples\extensions\custom-provider-gitlab-duo
[VERIFY] nm_extra_link path=…\node_modules\pi-extension-gondolin                    target=…\packages\coding-agent\examples\extensions\gondolin
[VERIFY] nm_extra_link path=…\node_modules\pi-extension-sandbox                     target=…\packages\coding-agent\examples\extensions\sandbox
[VERIFY] nm_extra_link path=…\node_modules\pi-extension-with-deps                   target=…\packages\coding-agent\examples\extensions\with-deps
```

**三类对象的区分实测**（`%TEMP%\wjg-d3\brokenlink2`；`bad_tgt` 已删、`good_tgt` 存在）：

```
[VERIFY] link_probe name=goodlink   TestPath=True LinkType=Junction Target=…\good_tgt TargetExists=True
[VERIFY] link_probe name=brokenlink TestPath=True LinkType=Junction Target=…\bad_tgt  TargetExists=False
[VERIFY] link_probe name=realdir    TestPath=True LinkType=          Target=           TargetExists=n/a
```

⇒ 与 `spec-junction-semantics-20261009.md:396`（§7.3）一致：`Test-Path <link>` 对链接本身恒为 `True`，**不能**当"目标完好"；`LinkType` 可区分链接与真目录；`Test-Path <Target>`（或 Python `os.path.exists(target)`）为 `False` 才是目标丢失。

**跨语言能力差异实测**（同一条 junction `…\@earendil-works\pi-ai`）：

```
[VERIFY] node_stats isSymbolicLink=true isDirectory=false
[VERIFY] node_stats fileAttributes=undefined typeof=undefined reparseTag=undefined typeof=undefined
[VERIFY] node_stats keys=dev,mode,nlink,uid,gid,rdev,blksize,ino,size,blocks,atimeMs,mtimeMs,ctimeMs,birthtimeMs
[VERIFY] py_stats   isjunction=True islink=False st_file_attributes=1040 (REPARSE=1024)
[VERIFY] py_stats   st_reparse_tag=2684354563 MOUNT_POINT=2684354563 SYMLINK=2684354572
[VERIFY] py_stats   readlink=\\?\H:\git\Multi-Workers\packages\ai   （Node readlink 无 \\?\ 前缀）
```

⇒ Python 可稳定判 `Junction` vs `SymbolicLink`；`os.readlink` 返回值带 `\\?\` 前缀须剥；Node 只能判"是链接"，**判不出哪一类**（spec §4 明确要求区分，否则要么漏 junction 要么过度拦截 symlink）。

### F5 AC-012 夹具：`%TEMP%` 内安全复现

**"假真树"替代方案（与 spec §1:20/§1:32 同构）**：不指回真树，而是在 `%TEMP%` 内另建一个 git 仓库 A 作为"真树"：

```
<root>\
  A\                                   <- 假真树（git init + 1 commit）
    .gitignore                          <- "node_modules/"
    packages\pkgA\a.txt  pkgB\b.txt  pkgC\c1.txt,c2.txt,c3.txt   <- tracked（共 6 含 .gitignore）
    node_modules\@scope\link{A,B,C}     <- junction -> A\packages\pkg{A,B,C}   （第 2 层）
    node_modules\plainpkg\p.txt         <- 真目录（阴性对照）
  B\                                   <- git worktree add --detach B HEAD
    node_modules                        <- junction -> A\node_modules          （第 1 层）
```

复现的是**同一伤害面 / 同一 API 穿透行为**，与目标是否在真树无关（穿透由 git `mingw_lstat` 把 `IO_REPARSE_TAG_MOUNT_POINT` 当目录决定，`spec-junction-semantics-20261009.md:226` §4）。实测：

**阳性对照（unsafe：直接 `git worktree remove --force`）**

```
CMD> git -C A worktree remove --force B
RC=0 elapsed_ms=70（复测 59）
AFTER B_exists=False A_pkgA=False A_pkgC_files=0 A_scope_exists=False
AFTER A tracked=6 status_lines=5 ls_files_d=5
[VERIFY] link_inventory_delta before=3 after=0 delta=3
[VERIFY] manifest_diff a_count=6 b_count=6 removed=0 added=0 content_changed=5 mtime_changed=5 missing_after=5
[VERIFY] content_changed_list=packages/pkgA/a.txt,packages/pkgB/b.txt,packages/pkgC/c1.txt,packages/pkgC/c2.txt,packages/pkgC/c3.txt
[VERIFY] zero_change(content)=false
```

（A 的 `packages/pkgC` 从 3 文件清零、`node_modules/@scope` 整目录连同 3 条 junction 消失 —— 与线上"链接消失 + 目标树文件消失"同构。恢复验证：`git -C A checkout -- .` ⇒ `deleted 5→0`、`status 0`，即 AC-010 信号会随恢复自清，佐证告警必须**落盘成事件**而非只报当前状态。）

**阴性对照（safe：六步顺序的前 5 步）**

```
CMD> 枚举 B 内 reparse point → 逐条 cmd /c rmdir（无 /S、无尾分隔符）→ 复核 A 链接 → git worktree remove --force B
  enumerated=1
  rmdir rc=0 path=…\B\node_modules type=Junction target=…\A\node_modules target_after=True
  A_link_recheck count=3 types=Junction,Junction,Junction exist=True,True,True
RC=0 elapsed_ms=113
AFTER B_exists=False A_pkgA=True A_pkgC_files=3 A_scope_exists=True
AFTER A tracked=6 status_lines=0 ls_files_d=0
[VERIFY] manifest_diff a_count=6 b_count=6 removed=0 added=0 content_changed=0 mtime_changed=0 missing_after=0
[VERIFY] zero_change(content)=true
```

**manifest 判据（"主树 mtime 与内容零变化"的机器对照）**

枚举 `git -C A ls-files -z`，逐路径取 `sha256(content)` + `size` + `mtimeMs`（可执行片段 = `%TEMP%\wjg-d3\manifest.mjs` / `compare.mjs`，核心 12 行）：

```js
const raw = execFileSync("git", ["-C", root, "ls-files", "-z"]).toString("utf8");
for (const p of raw.split("\0").filter(Boolean)) {
  const st = statSync(join(root, p));
  const sha = createHash("sha256").update(readFileSync(join(root, p))).digest("hex"); // ENOENT -> "ERR:ENOENT", missing++
  entries.push({ p, size: st.size, mtimeMs: Math.floor(st.mtimeMs), sha });
}
// compare: removed / added / content_changed(sha) / mtime_changed / missing_after
```

真树规模实测：

```
[VERIFY] manifest root=H:\git\Multi-Workers files=4995 bytes=60288001 missing=0 ls_ms=48–102 hash_ms=368–744 total_ms=418–850
[VERIFY] hash_object_variant: git ls-files | git hash-object --stdin-paths -> items=4995 chars=204794 ms=1024
```

⇒ 骨架判据 = **`removed==0 && added==0 && content_changed==0 && missing_after==0`**（内容维度），`mtime_changed==0` 作为二级/诊断维度（内容相同但被 touch 时只报 mtime）。规模上真树全量 ~0.4–0.9 s 可接受；夹具（6 文件）~60–200 ms。若只要"删/丢"而不比对内容，`git ls-files -d`（F2）即可，代价低一个数量级。

**PowerShell 实现坑（本次踩到，写进 design 防止复现）**：`FileSystemInfo.Target` 是**惰性解析**的；对链接先 `cmd /c rmdir` 再读 `.Target` 会得到空串（`Test-Path ""` 直接抛 `ParameterArgumentValidationErrorEmptyStringNotAllowed`）。必须在删除前把 `Path/LinkType/Target` 落到普通对象上。

### F6 mw 侧周期采样点（文件:行号 + 现频率）

| 位置 | 文件:行号 | 现频率 | 性质 |
|---|---|---|---|
| `mw serve` 主循环 | `packages/multi-workers/mw.py:353`（`while True:`）、`:376`（`time.sleep(1)`）；`cmd_serve` 起于 `:204` | **1 Hz** | 常驻；循环体内已有 `_conductor_supervise_step` 等托管动作 |
| launcher poll | `packages/multi-workers/launcher.py:1856`（`run`）、`:1899`（`while True:`）、`:1901`（`_poll_once`）、`:1905`（`time.sleep(poll_interval)`）；`DEFAULT_POLL_INTERVAL` = `:50` | **5 s**（`--poll-interval`，默认 5） | 每 poll 已写 beat：`launcher.py:1717` → `mw_common.launcher_beat_write`（`mw_common.py:2477`） |
| conductor tick | `packages/multi-workers/autopilot/conductor.py:7256-7257`；间隔默认 `config.py:86` `poll_interval_sec = 4` | **4 s**（1..5） | autopilot 专用 |
| `mw status` | `mw.py:486` | 按需（一次性） | 只报 service/conductor |
| `mw doctor` | `mw.py:508` → `mw_common.doctor_report`（`mw_common.py:3624`，段赋值 `:3642-3655`，`_doctor_issues` `:3401`，`format_doctor_text` `:3666`） | 按需（一次性） | 只有被调用才有信号 |

既有告警通道可照抄：`launcher.py:1277 _emit_envelope_skew_alarms` —— 一行聚合写 stderr（`mw serve` 捕获进 `.mw/launcher.log`，doctor 可读），并 `_record_trace_line`（`launcher.py:1612`）落 trace.log。状态目录 `.mw/` 既有文件形态：`mw.pid` / `serve.meta` / `launcher-beat.<pid>` / `workers.lock` / `dispatch.yml`。

### F7 仓内可复用的探测/比对件（可照抄）

- `packages/multi-workers/mw.py:4097 _git(...)`：统一 git 子进程封装。
- `packages/multi-workers/mw.py:4507 _git_dirty_paths(repo, paths)` + `mw.py:4503 _BUILD_DIRTY_PATHS = ["packages/coding-agent/src"]` + `mw.py:4504 _BOOTSTRAP_DIRTY_PATHS = ["packages/*/src/**"]`：**按路径面**跑 `git status --porcelain --untracked-files=all -- <paths>` 的既有惯例；其注释（`:4500-4502`）明确"`git diff --quiet` 不够（漏 staged/untracked）"。这是 AC-010 **排除 dist 面**的仓内先例。
- `packages/multi-workers/mw.py:5175 _git_dirty`：`git status --porcelain` 解析 + tracked/untracked 分类的现成实现。
- `packages/multi-workers/mw.py:5192 _claude_adapter_drift`：rel-path 并集 + `read_bytes()` 逐文件比对的现成"两树内容对照"骨架。
- TS 侧：`packages/coding-agent/test/suite/harness.ts`（`createHarness` + faux provider）、`test/suite/xkey-gate-guard-coverage.test.ts:124`（`BashOperations` 记录器）、`:131`（`createHarness`）、`:121-131`（env test hook 范式）；worktree 骨架夹具 `test/footer-data-provider.test.ts:42/61`（`createReftableWorktree`）、`test/resource-loader.test.ts:943/956`（`linkWorktree` / `setupNestedWorktree`，无需 git 二进制）。
- Python 测试范式：`packages/multi-workers/test_doctor_gates.py`（doctor 段 + `capsys` + 退出码）、`test_rag_cli.py`（`subprocess` 真 CLI 退出码）。
- **没有**任何现成的 `mklink`/junction/reparse 夹具或助手（`packages/**` 生产源码 0 命中，与 `spec-guard-and-mw-seams-20261009.md:386` §5.1 一致）。

### F8 告警自清与"事件"语义（为什么不能只看当前状态）

- 事故时间线：08:32:18.452Z 起删 → 08:32:22–24 穿透完成 → 08:36:07–20:38:18 恢复（`incidents-timeline-20261009.md` §2）。
- 夹具实测：`git checkout -- .` 后 `deleted 5→0`、`status 0` ⇒ **AC-010 当前的 `-d` 计数会随恢复归零**。
- 但恢复**不会**复原"已发生的事故"：`npm install` reify 重建的 8 条 junction 是**新链接**（`incidents-timeline-20261009.md` 20:38:58 行），链清单基线会看到"路径相同、目标相同"从而不可区分。⇒ 判据必须持久化"采样时刻 + 观测值 + 迁移"，不能只留最新快照。

---

## 对 design 的直接含义（可直接写进 design.md 的判据/夹具接口草案）

### D1 · AC-010「已跟踪文件数骤降」判据草案

```
原语      : git -C <root> --no-optional-locks ls-files -d -z      # 索引有、磁盘无
范围面    : 排除 dist 面（照 mw.py:4504 的 glob 惯例；实测 dist 占 packages/ 58.5%）
采样点    : launcher._poll_once（launcher.py:1706），每 SAMPLE_EVERY 次 poll 取一次
            默认 SAMPLE_EVERY=6（poll 5s ⇒ 窗口 30s）；PI_TREE_WATCH_SEC 可覆盖，0=关闭
状态      : <root>/.mw/tree-watch.json = {ts, tracked, deleted_non_dist, deleted_paths[<=50], link_inventory}
判据(窗口): ΔD = deleted_non_dist(t) - deleted_non_dist(t-1) >= max(20, 1% * tracked_non_dist(t))
            且 deleted_non_dist(t) >= 20
本仓取值  : tracked_non_dist = 2756 ⇒ 阈值 = max(20, 28) = 28
事故取值  : 9 包 non-dist ≈ 1363（今日构成推算）⇒ 约为阈值的 49 倍；总口径 3456 ⇒ 123 倍
动作      : 命中 ⇒ (1) stderr 一行 [TREE-WATCH]（照 launcher.py:1277 形状，进 .mw/launcher.log）
                   (2) 事件落盘 tree-watch.json + .mw/alarm.log（自清后仍可回溯）
                   (3) 若同一窗口 link_inventory 有 delta ⇒ 升级为 issue（mw_common.py:3401 _doctor_issues）
                       使 mw doctor rc=1，并在 format_doctor_text（mw_common.py:3666）加一行
不误报的理由: 单文件编辑 ΔD=0；一次 commit ΔD=0；切分支 ΔD=0（tracked 变、-d 不变）；
              git rm -r <pkg> ΔD=0（索引同步）；新增 untracked ΔD=0；
              排除 dist 后 "npm run clean --workspaces" ΔD=0（dist=2239 条全在排除面内）
残留误报面: 不经 git rm 直接 rm -rf 非 dist 的 tracked 源文件（见「未坐实」2）
```

### D2 · AC-011「junction 目标丢失」判据草案

```
数据源    : Python 扫描 <root>/node_modules/@earendil-works/*（1 层，不递归进链接）
            每条输出 {path, link_type, target, target_exists}
            可选加扫 <root>/node_modules 的直接子项（实测多出 5 条 pi-extension-*，同为仓库内 junction）
判据(断链): link_type == "Junction" and not target_exists            ⇒ 触发（给出 path + target）
判据(清单): 上一样本存在的 link 在本样本消失，或 target 变化        ⇒ 触发（覆盖 v2 漏报面："只剩 1 条链无人报警"）
挂载位置  : 双挂 —— (a) doctor 段：结构报告，按 mw.py:523-534 的注入范式挂 cmd_doctor，
            或在 mw_common._doctor_issues（:3401）出 issue；(b) 同一 launcher 采样点（D1）
理由      : (a) doctor 只有被调用才有信号 —— 事故 5.5 分钟内无人调用；
            (b) @earendil-works 扫描实测 0.5 ms、整根 node_modules 185–195 ms ⇒ 自动采样近零成本
区分规则  : Junction（tag 0xa0000003）触发；SymbolicLink（0xa000000c）单独标记但默认不触发
            （spec §8 补注：git 不穿 symlink，尾分隔符/通配形态才穿一层）；
            真目录（LinkType 空）忽略；仓库外目标 → fail-closed 单独报警（AC-006 同源判据）
语言选择  : 必须 Python（Node Stats 无 reparseTag，实测 undefined）；TS 侧若需要，shell-out
```

### D3 · AC-012 端到端夹具草案（可执行）

```
夹具根    : %TEMP%\mwvg-<key>-<n>\{A,B}      （A=假真树，B=worktree）
A 构建    : git init; packages/pkgA|pkgB|pkgC; node_modules/@scope/link{A,B,C} -> packages/pkg*;
            node_modules 写入 .gitignore; 1 commit
B 构建    : git -C A worktree add --detach B HEAD; cmd /c mklink /J B\node_modules A\node_modules
可选反例  : A\node_modules\plainpkg（真目录）；B\node_modules_out -> %TEMP% 外部（AC-006 fail-closed）
阳性对照  : git -C A worktree remove --force B        ⇒ 期望 A 侧 tracked 缺失 + 链清单 delta>0
阴性对照  : 枚举 B 内 reparse point → cmd /c rmdir <link>（无 /S、无尾分隔符）→ 复核 A 链逐条未变
            → git -C A worktree remove --force B      ⇒ 期望 manifest 零变化
机器判据  : manifest(A) before/after = {removed==0, added==0, content_changed==0, missing_after==0}
            二级：mtime_changed==0；链接清单 before/after 逐条 (path, link_type, target) 相等
            理由：只比 mtime 会把"内容相同但被 touch"误判，只比 status 会漏掉 untracked/ignored 面
guard 断言: 对带链 worktree 直接下 `git worktree remove --force` 必须在执行前被 block（G1，TS suite 侧）
清理      : 先逐条 cmd /c rmdir <link>，再 cmd /c rmdir /S /Q <root>（spec §11:484 同款）
```

### D4 · 采样状态与告警通道

- 状态文件 `<root>/.mw/tree-watch.json`（与 `dispatch.yml`/`window-model`/`workers.lock` 同惯例）；首次运行只有快照，第 2 次采样起才有 delta（AC-011 链清单同）。
- 告警形状照 `launcher.py:1277`：一行聚合 `[TREE-WATCH] deleted=… non_dist=… delta=… links=…` 写 stderr（→ `.mw/launcher.log`）+ `_record_trace_line`（`launcher.py:1612`）。
- `mw doctor` 读同一状态文件出 issue（`mw_common.py:3401`）→ 退出码 1（`mw.py:534 return 0 if report["summary"]["healthy"] else 1`）。

---

## 未坐实 / caveat

1. **采样窗口内的"删-恢复"闭合会漏报**：AC-010 是瞬时判据。事故窗口（删除 ~2–4 s、恢复 4–6 min 后）在 30 s 采样下必然命中；但若删除与恢复落在同一间隔内，只能靠"事件落盘 + 事后 diff"（F8 提出，未在真机事件上验证）。
2. **残留误报面**：不经 `git rm` 直接 `rm -rf` 掉非 dist 的 tracked 源文件（例如误删 `packages/*/src`）会命中 AC-010 阈值。缓解方向（未实现、未验证）：用 AC-011 链清单 delta / guard block trace 佐证后分级为 WARN，而不是直接 ALARM。
3. **"主树零变化"在真树上的可测性未坐实**：真树是多会话共享树，AC-012 的 manifest 零变化只在**无人并发写**的窗口成立；夹具内可保证，真树端到端需要静默窗口或按链接目标子树逐文件归因（spec AC-005 的 8 包清单）。本次未在真树跑任何 before/after 清单。
4. **`.git/index` 是否被采样命令改写未观察到变化**：实测 `git status --porcelain`、`git --no-optional-locks status --porcelain`、`git ls-files -d` 在连跑（含改动已跟踪文件内容后）均未改 `.git/index` mtime。但 git 文档允许 `status` 刷新索引（届时会取 `.git/index.lock`）⇒ 仍建议采样统一用 `--no-optional-locks`/`GIT_OPTIONAL_LOCKS=0`，避免与其它 worker 的 git 操作争锁。**"争锁"本身未实测。**
5. **事故当时的包构成是推算**：本报告 non-dist 阈值与事故量级对比用的是**今日** per-package 构成（9 包：tracked 3601 / non-dist 1363）；事故当时 8 包 3,300 + tui 156 = 3,456 的 dist/non-dist 拆分未从一手证据反推。标注为推算。
6. **`npm run clean --workspaces` 未实跑**：只做了 tracked 账目推算（dist=2,239 全在排除面内 ⇒ ΔD 应为 0）。实跑代价为一次全仓 clean，未在本卡执行（避免碰真树产物）。
7. **Node 侧 junction 判定只证伪了 Node 24.19.0 的 `fs.Stats`**：未测 `fs.statfs`、原生 addon、`fs.opendir` 的 `Dirent` 扩展属性等是否提供 reparse tag。TS 侧结论限本次环境。
8. **AC-011 的"应有链接基线"来源未定**：事故当时没有链接注册表，首次采样只能记快照；若要 "expected set"（AC-008 的注册表）作基线，依赖 G2 的 `--link-deps` 登记实现，本卡不涉及。
9. **仅测 junction 与目录 symlink 两类 reparse point**：与 `spec-junction-semantics-20261009.md:430` 的同款边界（云占位符、卷挂载点、文件链接未测）。
10. **未测更大规模的 `git ls-files -d` 退化**：合成仓只到 5,000 tracked / 3,000 deleted；真树（4,995 tracked）当前 deleted=0，损坏态的真树代价未实测（按合成仓线性外推 ~100–200 ms，标注为推算）。
11. **采样点频率的最终选择未定**：本卡给出 1 Hz/5 s/4 s 三个候选与其代价，未做"多久采样一次最合适"的实机占空比验证（按 0.5 ms–200 ms / 30 s 推算占空比 < 0.7%，标注为推算）。

## 上下文来源

（PM 补录：worker 交付内容完整，但缺本节规范标题；清单取自本文件各节实际引用的 `文件:行号`，不改动任何上文原文。）

| 文件 | 行 | 用途 |
|---|---|---|
| `packages/multi-workers/mw.py` | `:204`、`:353`、`:376`、`:486`、`:508`、`:4503`、`:4504`、`:4507`、`:5175`、`:5192` | `mw serve` 1 Hz 主循环（采样点候选）、`mw status`、`doctor` 入口、路径面 glob 惯例（`_BUILD_DIRTY_PATHS`/`_BOOTSTRAP_DIRTY_PATHS`，天然排除 dist）、`_git_dirty_paths`、`_git_dirty`、`_claude_adapter_drift`（两树对照骨架） |
| `packages/multi-workers/mw_common.py` | `:2477`、`:3401`、`:3624`、`:3642-3655`、`:3666` | `launcher_beat_write`、issue 汇聚点、`doctor_report` 与段注册位置、文本渲染 |
| `packages/multi-workers/launcher.py` | `:50`、`:1277`、`:1612`、`:1706`、`:1717`、`:1856`、`:1899-1905` | `DEFAULT_POLL_INTERVAL`=5 s、告警形状（`_emit_envelope_skew_alarms`）、`_record_trace_line`、`_poll_once`（推荐采样挂载点）、每 poll 写 beat、run 循环 |
| `packages/multi-workers/autopilot/conductor.py` / `autopilot/config.py` | `conductor.py:7256-7257`、`config.py:86` | conductor tick 默认 4 s |
| `packages/multi-workers/mw.py` 医生退出码 | `:534` | `return 0 if report["summary"]["healthy"] else 1` |
| `package.json` | `:9-14` | workspaces 列表（解释 5 条 `pi-extension-*` 链的来源） |
| `packages/coding-agent/test/suite/harness.ts` / `test/suite/xkey-gate-guard-coverage.test.ts` | `harness.ts`（`createHarness` + faux provider）、`xkey…:121-131`（env test hook、`BashOperations` 记录器、`createHarness`） | TS 端到端"命令未执行"断言范式 |
| `packages/coding-agent/test/footer-data-provider.test.ts` / `test/resource-loader.test.ts` | `footer…:42/61`（`createReftableWorktree`）、`resource-loader…:943/956`（`linkWorktree`/`setupNestedWorktree`） | 仓内最贴近的 worktree/链接夹具骨架（无需 git 二进制） |
| `packages/multi-workers/test_doctor_gates.py` / `test_rag_cli.py` | 全文 | doctor 段 + `capsys` + 退出码、真 CLI `subprocess` 退出码范式 |
| `packages/**` 生产源码 | grep `mklink\|isjunction\|ReparsePoint\|IO_REPARSE` = 0 命中 | 佐证"仓内无现成 junction 夹具/助手" |
| 本 key 前序证据 | — | `spec-junction-semantics-20261009.md`（`:226` §4、`:396` §7.3、`:430`、`:484`、`§8`）、`incidents-timeline-20261009.md`（§2 时间线、20:38:58 reify 行）、`spec-guard-and-mw-seams-20261009.md:386`、`design-guard-path-resolution-20261013.md`（RQ-D1） |
| `%TEMP%\wjg-d3\**` | — | 本卡全部夹具（A=假真树 / B=worktree / 断裂链三类），结束时已清理 |

PM 复核（2026-10-13，一手复看）：`tracked=4995`、`dist_tracked=2239`、`non_dist_tracked=2756`、`deleted=0`（四条与我自己的 `git ls-files` 统计逐项一致）；`mw.py:353/:376` 是 serve 主循环与 1 Hz sleep；`launcher.py:1706` 是 `_poll_once`、`:1899` 是 `while True`；`launcher.py:1277` 是 `_emit_envelope_skew_alarms`；`conductor.py:7256` 是 tick deadline 行、`config.py:86` 是 `poll_interval_sec = 4`；`footer-data-provider.test.ts:61` 是 `createReftableWorktree`；`mw.py:4507/:5175/:5192` 分别是 `_git_dirty_paths`/`_git_dirty`/`_claude_adapter_drift`。以下为 worker 实测、PM 未复算：所有 ms 级耗时矩阵（`git ls-files -d`/`git status`/link scan/manifest）、合成仓 5,000/3,000 规模实验、Node `Stats` 无 `reparseTag` 的实测、junction 三类对象与 `os.rmdir` 行为、阳性/阴性对照夹具的 manifest 输出。

## 残留与未验证

（PM 补录，与上文 `## 未坐实 / caveat` 十一条一一对应，只做"对 design 的处置"归并。）

| 原编号 | 未坐实项 | 处置（design 已落） |
|---|---|---|
| 1 | 采样窗口内"删-恢复"闭合会漏报 | design §6.1 的"事件语义"：告警必须落盘成事件 + 事后 diff，不能只看当前状态（AC-010 的判据与证据同时保留） |
| 2 | 残留误报面：不经 `git rm` 直接 `rm -rf` 非 dist 的 tracked 源文件会命中阈值 | design §6.1 的阈值与动作表；缓解方向（用 AC-011 链清单 delta / guard block trace 佐证后分级）留待实现期与 AC-010 测试一起定 |
| 3 | "主树零变化"在真树上的可测性未坐实（多会话共享树） | design §9 AC-012 只承诺**夹具内**零变化；真树端到端需静默窗口，已写进 §10 未覆盖面声明 |
| 4 | `.git/index` 是否被采样命令改写未观测到变化、争锁未实测 | design §7 第 6 条：采样统一 `--no-optional-locks` |
| 5 | 事故当时 per-package dist/non-dist 是推算 | design 已在 §1 标注"今日构成推算"，阈值公式不依赖事故数值 |
| 6 | `npm run clean --workspaces` 未实跑 | design §6.1 只用其账目推算（dist=2,239 全在排除面内），测试里用合成仓覆盖"排除 dist 后 ΔD=0" |
| 7 | Node 侧只证伪了 24.19.0 的 `fs.Stats` | design 决策 D-8：权威实现放 Python |
| 8 | AC-011 的"应有链接基线"来源未定 | design §5.1 + §6.2：基线取自 G3 注册表 + 首次采样快照 |
| 9 | 仅测 junction 与目录 symlink | design §10 未覆盖面声明 |
| 10 | 更大规模 `git ls-files -d` 退化未实跑 | design §7 第 4 条：实现期在 AC-012 夹具顺带计时，阈值参数化 |
| 11 | 采样频率的最终选择未定 | design 决策 D-7：`launcher._poll_once` 每 6 次 poll（30 s），`PI_TREE_WATCH_SEC` 可覆盖、0=关闭 |

未覆盖面声明（本卡明确没做的）：真树 `H:\git\Multi-Workers` 零写入（未改文件、未建/删 worktree 或 junction、未跑 `checkout`/`reset`/`clean`/`rm`）；未在真树跑 before/after 清单；未碰 `node_modules` 与既有 14 条链接；所有 fixture 在 `%TEMP%\wjg-d3\**` 且链接目标全部在夹具内，清理走"先逐条 `cmd /c rmdir`（无 `/S`）再 `rmdir /S /Q`"；未覆盖 G1（T-D1）与 G2/G3（T-D2）范围。
