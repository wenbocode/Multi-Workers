# IN-1 取证：workspace junction 消失（2026-10-09）

- key: `mw-workspace-incident-probe` · worker: `inc1-junction-forensics` · type: research
- 采集时刻: **2026-10-10 10:59-11:25 (UTC+8) / 2026-10-10T02:59-03:25Z**（本文件）· 对照首轮采集: 2026-10-09 20:59-21:25 (UTC+8)
- 本文件性质：`inc1-junction-forensics` 的**第二次独立执行**。首轮（2026-10-09 21:10 落盘）结论被本轮逐条复算，结论一致；本轮新增：(a) 首轮未给出的一手 `[VERIFY]` 数值（工件级 mtime 普查），(b) 我自己在 `%TEMP%` 重跑的 A/B 两组复现与 5 组对照，(c) 事故后状态漂移的标注。
- 方法: 只读。主证 = 会话 jsonl 的**已执行 toolCall 参数**（`name=bash` -> `arguments.command`）与对应 toolResult；旁证 = 只读 git、文件系统 mtime/lstat、`%LOCALAPPDATA%\npm-cache\_logs`；机制 = 在 `%TEMP%` 内最小复现（**真树零触碰**）。
- git: `git version 2.53.0.windows.1`（`D:\Program Files\Git\cmd\git.exe`）；宿主 shell = Windows PowerShell **5.1.26100.9168**（与当日会话同一个）。
- 本文件是本 worker 唯一写入物。

## TL;DR

1. **元凶命令（AC-001）**：`git worktree remove --force "$env:TEMP\qg-head"`，发出于**本地 2026-10-09 20:32:18.452 / UTC 12:32:18.452Z**，返回于**本地 20:32:24.444 / UTC 12:32:24.444Z（rc=255，耗时 5.99 s）**；来源 `--H--git-Multi-Workers--\2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` **第 142 行**（该行含 2 个 toolCall，其中 bash 的 `id=call_01_HaTl69XPpjBFS4aVfVkL2723`），toolResult 在同文件 **第 144 行**。
2. **机制（AC-003）**：`git worktree remove` 的递归删除**穿透（follow）junction**，而 `cmd rmdir` / PS 5.1 `Remove-Item -Recurse` / MSYS `rm -rf` / node `fs.rmSync(recursive)` / python `shutil.rmtree` **全部不穿透**（6 组全部本轮实测）。`qg-head\node_modules` 是指回真树的 junction，因此删除沿 `qg-head\node_modules`（junction）-> 真 `node_modules` -> `@earendil-works\pi-*`（8 条 workspace junction）-> 真 `packages\*` 逐层下钻；在 `@earendil-works` 的最后一条 `pi-tui` 处撞到无法删除的文件（EINVAL）后中止，故 **`pi-tui` 链接保留、`@earendil-works` 之后的 node_modules 条目全部幸免**。
3. **「只删链接、包目录完好」是错觉**：同一条命令删了两类东西 —— 9 条 workspace 链接中的 8 条，**以及这些链接目标 `packages\*` 的文件内容**。恢复分两步（20:36-20:38 `git checkout -- <3456 paths>`；20:38:58 `npm install --ignore-scripts`）才造成「包完好」的观感。**工件级证据**：`packages/*` 已跟踪文件 mtime 普查显示 8 个包 **100% 落在 2026-10-09**（重写=删除后重建），只有 `tui` 是 **80 个 2026-08-05 + 156 个 2026-10-09** 的混合态（中止点），而唯一不是 junction 目标的 `packages/multi-workers` **几乎未动**（200 个文件中仅 8 个 mtime 为 2026-10-09，且来自当日其它 key 的正常编辑）。
4. **与 IN-2 同源**：IN-1 是「链接层」观测，IN-2 是「目标文件层」观测，两者时间戳（20:32:22-24）、损坏边界（9 个 workspace 包）、恢复链（`git checkout` + `npm install`）三点互证。
5. **PM 的 npm 排除证据不可用**：`%LOCALAPPDATA%\npm-cache\_logs` 现存 **11 个文件、最早 mtime 2026-10-10 11:07:28**，且 `npm config get logs-max` = **10** —— 该目录按设计只保留最近 N 条，**不能**用来断言「10-09 17:00-20:41 npm 0 次调用」。但「npm 不是本事故元凶」仍成立（npm 无法删除已跟踪源码文件，而 3456 个 tracked 文件确实消失）。
6. **状态漂移警告（本轮新增）**：事故后真树仍在被并发会话改动。本轮采集期间观察到 **2026-10-10 11:21 有一次 `npm install`** 重写了 `node_modules/.bin`、`.package-lock.json`、`@anthropic-ai`、`@aws*`、`@babel`、`@bcoe`、`@biomejs`、`@typescript`、`@earendil-works/pi-ai|pi-coding-agent|gondolin` 等条目的 mtime；`git worktree list` 也从「仅主树」变成 5 项。因此下文凡涉及 mtime/条目数，均标注采集时刻。

## [VERIFY]（本次实测打印；采集时刻 2026-10-10 11:00-11:25 本地，除注明外）

```
[VERIFY] git_version=git version 2.53.0.windows.1
[VERIFY] powershell_host=5.1.26100.9168
[VERIFY] incident_cmd_ts=2026-10-09T12:32:18.452Z local=2026-10-09 20:32:18.452 src=2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl:142 toolCall_id=call_01_HaTl69XPpjBFS4aVfVkL2723
[VERIFY] incident_result_ts=2026-10-09T12:32:24.444Z local=2026-10-09 20:32:24.444 rc=255 elapsed=5.99s err="git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument" src=same-file:144
[VERIFY] junction_created_ts=2026-10-09T12:21:48.660Z src=same-file:60 cmd="cmd /c mklink /J \"$t\\node_modules\" \"H:\\git\\Multi-Workers\\node_modules\"" result=same-file:61 tail="qg-head\\node_modules <<===>> H:\\git\\Multi-Workers\\node_modules created / True"
[VERIFY] cleanup_cmd_ts=2026-10-09T12:32:28.112Z src=same-file:145 ; cleanup_result_ts=2026-10-09T12:32:33.062Z still_exists=False src=same-file:146
[VERIFY] window_12:31:40Z-12:33:15Z executed_bash_toolcalls=70 destructive_verb_hits=2 (L142 culprit, L145 cleanup) other_hits=0
[VERIFY] trace_log_corroboration=[TOOL] 2026-10-09T12:32:18.454Z bash cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" ... (mvr-t16/trace.log; [START] 2026-10-09T12:07:43.239Z ; [END] 2026-10-09T12:32:43.510Z exit=0 elapsed=1500s tools=88)
[VERIFY] packages_tracked_mtime_census(@2026-10-10 11:1x): agent 226/226 on 2026-10-09 | ai 1060/1060 | client 63/63 | coding-agent 1683 = 716 on 2026-10-09 + 967 on 2026-10-10 | evals 19/19 | protocol 49/49 | server 99/99 | session-backends 101/101 | tui 236 = 80 on 2026-08-05 + 156 on 2026-10-09 | multi-workers 200 (only 8 on 2026-10-09, rest older)
[VERIFY] @earendil-works_junctions=9 ; pi-tui mtime=2026-08-10 18:09:09.985639 (never deleted) ; 8 others mtime=2026-10-09 20:39:03 (npm recreated) ; gondolin = real dir (not a junction)
[VERIFY] node_modules_children(@2026-10-10 11:22:55)=230 ; NTFS-upper-order children <= "@earendil-works" = 11 (.bin .package-lock.json @anthropic-ai @aws @aws-crypto @aws-sdk @babel @bcoe @biomejs @cto.af @earendil-works) ; children after = 219
[VERIFY] npm_logs(@2026-10-10 11:08): files=11 earliest_mtime=2026-10-10 11:07:28 ; npm_config_logs_max=10 (npm prunes older logs; so this dir cannot prove absence of npm calls on 10-09)
[VERIFY] repro_A(git worktree remove --force, junction at wt/node_modules): mklink_rc=0 LinkType=Junction RC=0 wt_exists=False real_nm_exists=True real_nm_scope_entries=(empty) real_plainpkg_files=0 pkgA=0 pkgB=0 pkgC=0 git_status=" D packages/pkgA/a1.txt ..." (target wiped, no error)
[VERIFY] repro_B(same + exclusive lock on one target file): RC=255 err="git : error: failed to delete '.../jrepro-in1d/wt': Invalid argument" wt_exists=True junction_link_exists=True scope_entries=linkC(only last) pkgA=(empty) pkgB=(empty) pkgC=c4.txt,c5.txt,c6.txt -> error text byte-identical to online; shape matches "pi-tui kept + packages/tui 156/236"
[VERIFY] control_cmd_rmdir_junction: rc=0 target_alive=True linkA_alive=True pkgA=1 pkgB=1 plainpkg=1 victim_alive=True (link removed, target intact)
[VERIFY] control_ps5_RemoveItem_Recurse(parent containing junction): target_alive=True linkA_alive=True pkgA=1 pkgB=1 plainpkg=1 victim_alive=False
[VERIFY] control_msys_bash_rm_rf(parent containing junction): rc=0 target_alive=True linkA_alive=True pkgA=1 pkgB=1 plainpkg=1 victim_alive=False
[VERIFY] control_node_fs_rmSync_recursive: target_alive=True linkA_alive=True pkgA=1 pkgB=1 plainpkg=1 victim_alive=False
[VERIFY] control_python_shutil_rmtree: target_alive=True linkA_alive=True pkgA=1 pkgB=1 plainpkg=1 victim_alive=False
[VERIFY] live_junctions_into_real_tree(@2026-10-10 11:20): %TEMP%/mwvg-t5/node_modules -> H:/git/Multi-Workers/node_modules (mtime 2026-09-23 18:58) ; %TEMP%/qg2-head/node_modules -> H:/git/Multi-Workers/node_modules (mtime 2026-10-10 11:07:51)
[VERIFY] git_worktree_list(@2026-10-10 11:09)= H:/git/Multi-Workers 10446aefb [dev/AgentTeam] | %TEMP%/mwbase-head 10446aefb (detached) | %TEMP%/qg2-head 10446aefb (detached) | H:/tmp/fmr76b 76d5d612e (detached) | H:/tmp/t23wt-mine 10446aefb (detached) ; HEAD=10446aefb69c1ccf2505cf1e3d8cfa7edc39d48b ; (2026-10-09 EOD state was "main only" per first run -> now drifted)
[VERIFY] qg-head/mw-t23-wt/.tmp-t09-wt/.tmp-t13-wt/.tmp/t13-worktree all absent (@2026-10-10 11:20)
```

## AC-001：删掉真实 junction 的已执行命令原文 + 精确时刻 + 来源 jsonl

**元凶（toolCall，来源 jsonl 第 142 行，`2026-10-09T12:32:18.452Z`）**

```powershell
cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" 2>&1 | Out-String; "RC=$LASTEXITCODE"; git worktree list | Out-String
```

**toolResult（同文件第 144 行，`2026-10-09T12:32:24.444Z`；stderr 原文）**

```
git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument
RC=255
H:/git/Multi-Workers 10446aefb [dev/AgentTeam]
```

**前置（把 junction 造出来；同文件第 60 行，`2026-10-09T12:21:48.660Z`）**

```powershell
cd H:/git/Multi-Workers; $t="$env:TEMP\qg-head"; if(Test-Path $t){ git worktree remove --force $t 2>$null; if(Test-Path $t){ cmd /c rmdir /s /q "$t" } }; git worktree add --detach $t HEAD 2>&1 | Out-String; "RC=$LASTEXITCODE"; cmd /c mklink /J "$t\node_modules" "H:\git\Multi-Workers\node_modules"; Test-Path "$t\node_modules\vitest"
```

回显（第 61 行，`2026-10-09T12:23:10.095Z`；`worktree add` 耗时约 81 s）：`HEAD is now at 10446aefb ...` / `RC=0` / `<...>qg-head\node_modules <<===>> H:\git\Multi-Workers\node_modules 已创建` / `True`。即 **junction 确实指向真树**；且 `$t` 首次不存在，故 `if(Test-Path $t)` 分支（含 `rmdir /s /q`）未执行。

**善后（同文件第 145 行，`2026-10-09T12:32:28.112Z`）** —— 因为 git 没能删掉该 junction，才需要再 `rmdir` 一次：

```powershell
$t="$env:TEMP\qg-head"; if(Test-Path $t){ cmd /c rmdir "$t\node_modules" 2>&1 | Out-String; Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue; }; "still_exists=" + (Test-Path $t); cd H:/git/Multi-Workers; git worktree prune; git worktree list
```

结果（第 146 行，`2026-10-09T12:32:33.062Z`）：`still_exists=False`。

**精确时刻表**

| 项 | 本地 (UTC+8) | UTC | 证据 |
|---|---|---|---|
| 元凶命令发出 | 2026-10-09 20:32:18.452 | 12:32:18.452Z | jsonl:142 toolCall |
| 元凶命令返回 rc=255 | 2026-10-09 20:32:24.444 | 12:32:24.444Z | jsonl:144 toolResult |
| 真树 `node_modules` 目录 mtime | 20:32:22 | — | PM 在 20:38:58 实测 `Get-Item node_modules` = `2026/10/9 20:32:22`（session `01a0d325` jsonl 第 2927 行，本轮已复核） |
| 真树 `packages/coding-agent` 目录 mtime | 20:32:24 | — | 首轮报告引用 worker `01a1208f-d2f3` 实测；**本轮未复算该行** |
| junction 建立 | 20:21:48.660 | 12:21:48.660Z | jsonl:60/61 |
| 善后命令 | 20:32:28.112 | 12:32:28.112Z | jsonl:145 |

**来源 jsonl 绝对路径**：`C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl`（共 **149** 行；引用行 60/61/142/144/145/146）。session 头（第 1 行）：`{"type":"session","version":3,"id":"01a1208f-e335-767d-a127-bf295f75a861","timestamp":"2026-10-09T12:07:43.157Z","cwd":"H:\\git\\Multi-Workers"}`。

**「唯一性」核验（本轮独立重跑）**：对**全部**会话 jsonl（不限文件名，按 `timestamp` 过滤）取 `2026-10-09T12:31:40Z-12:33:15Z` 窗口（95 s）：命中窗口的**已执行 bash toolCall 共 70 条**；命令文本含 `worktree remove/prune`、`Remove-Item`、`rmdir`、`rimraf`、`git clean/checkout/reset/restore/stash`、`mklink`、`del /`、`rd /s` 任一者**只有 2 条**，且两条同属本会话（L142 元凶、L145 善后）。**窗口内没有第三条候选命令。**（首轮报告写「90 条」，差异来自计数口径：首轮计所有 toolCall，本轮只计 `name=bash` 且带 `command` 者。）

## AC-002：执行者会话 + 所属 key/窗口

| 项 | 值 | 证据 |
|---|---|---|
| session 文件 | `C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` | 文件第 1 行 session 头 |
| cwd slug / cwd | `--H--git-Multi-Workers--` / `H:\git\Multi-Workers` | session 头 `"cwd"` 字段 |
| session id | `01a1208f-e335-767d-a127-bf295f75a861`（起于 `2026-10-09T12:07:43.157Z`） | session 头 |
| worker / 卡片 | worker `mvr-t16-quality-gate-review`（`type: research`）· 卡片 `T-16-quality-gate-review` | `.agenticdoc/mw-vision-role/workers/mvr-t16-quality-gate-review/{task.md,progress.md,trace.log}` |
| key / 窗口 | key **`mw-vision-role`** · `Claim-Id: WENBOZHOU-PC4:8152` | `.agenticdoc/mw-vision-role/pm-state.md` |
| 执行进程账本（旁证） | `trace.log`：`[START] 2026-10-09T12:07:43.239Z task=mvr-t16-quality-gate-review`；`[TOOL] 2026-10-09T12:32:18.454Z bash cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" ...`；`[END] 2026-10-09T12:32:43.510Z exit=0 elapsed=1500s tools=88` | 同一 trace.log（本轮 grep 命中；行号随该文件被后续运行追加而漂移，故不引行号） |
| worker 自述 | `progress.md` 的 `## T-16 re-run (2026-10-09 wall clock; HEAD 10446aefb)` 段：「detached HEAD worktree in `$TEMP` (now removed)」 | 同上目录 |

**结论**：元凶命令的执行者不是 PM 主窗口，而是 key `mw-vision-role` 派出的 **worker 进程 `mvr-t16-quality-gate-review`**；该 worker 在 `%TEMP%\qg-head` 做隔离复验，复验完毕清理时直接 `git worktree remove --force`，未先摘 `node_modules` junction。

**[未坐实]**
1. **10-09 的派发行已不存在**：`.agenticdoc/_workers.parallel` 当前 `mvr-t16-quality-gate-review` 行是 **2026-10-10 的重派**（`... | done | pi | timi | ... | 2026-10-10T02:50:05.627Z | 2026-10-10T03:20:41+00:00`），10-09 行已被覆盖，无法从该文件复核首轮报告引用的「12:01:47.837Z 派发 / 12:32:45Z 完成」。
2. **触发本次重派的具体 PM 窗口/命令**：12:00-12:08Z 的已执行 toolCall 中找不到 `dispatch_worker` / `mw dispatch` 记录（重派由 mw launcher 消费队列完成）。首轮报告同判 [未坐实]。
3. **进程 pid**：首轮报告给出 `pid=159560`；本轮的 trace.log 中 10-09 `[START]` 行**不含 pid**，无法复核，记为 [未坐实]。

## AC-003：机制 —— 工具对 junction 的语义（穿透 vs 不穿透）+ 最小复现

### 3.1 六种工具/命令的语义（**本轮全部实测**；fixture 位于 `%TEMP%\jrepro-in1c`、`%TEMP%\jrepro-in1d`、`%TEMP%\jctl1..jctl5`；**真树零触碰**）

| 工具 / 命令 | 对 junction 的语义 | 本轮实测结果 |
|---|---|---|
| `git worktree remove --force <wt>`（git 2.53.0.windows.1） | **穿透（follow）** | 进入 junction 目标并删除其内容；可继续穿透第二层 junction；完整删除时 **rc=0 且无任何报错**；撞到不可删文件时 **rc=255 + `failed to delete '<wt>': Invalid argument`** |
| `cmd /c rmdir <junction>` | **不穿透** | `rc=0`；只摘链接；目标 `node_modules` 及其内 `linkA`、各 1 个文件全部原样 |
| PowerShell **5.1** `Remove-Item -Recurse -Force <含 junction 的父目录>` | **不穿透** | 父目录连同 junction 一起被删；目标 `node_modules`、`linkA`、pkgA/pkgB/plainpkg 文件全部幸存 |
| MSYS/Git-Bash `rm -rf <含 junction 的父目录>` | **不穿透** | `rc=0`；目标全部幸存 |
| node `fs.rmSync(dir, {recursive:true, force:true})` | **不穿透** | 目标全部幸存 |
| python `shutil.rmtree(dir)` | **不穿透** | 目标全部幸存 |

**为什么 git 是唯一的穿透者（推断，未读 git 源码坐实）**：git 自己的 `remove_dir_recursively` 用 `lstat` 判定条目类型；Windows junction（`IO_REPARSE_TAG_MOUNT_POINT` + `FILE_ATTRIBUTE_DIRECTORY`）不是 `S_ISLNK`，于是被当作**普通目录** -> `opendir/readdir` 进入目标树、逐项 `unlink`/`rmdir`（= 穿透），删除完目标内容后再 `rmdir` 掉 junction 自身。其余工具都识别重解析点，只摘链接。**实测事实是上半张表；「为什么」这一句是机制推断，标注为推断。**

### 3.2 复现 A：完整穿透（`%TEMP%\jrepro-in1c`，rc=0）

fixture（**关键点：`node_modules` 必须在 `.gitignore` 中，否则 `git worktree add` 会把 `node_modules` 当已跟踪文件签出成真目录、junction 建不起来**）：

```
real\                                   (git 仓库，含 .gitignore: node_modules/)
  packages\pkgA|pkgB|pkgC\              (各 3/3/6 个文件，已提交)
  node_modules\plainpkg\p1.txt
  node_modules\@scope\linkA -> real\packages\pkgA   (Junction)
  node_modules\@scope\linkB -> real\packages\pkgB   (Junction)
  node_modules\@scope\linkC -> real\packages\pkgC   (Junction)
wt\                                     (git worktree add --detach HEAD)
  node_modules -> real\node_modules     (Junction, 实测 LinkType=Junction)
```

执行 `git -C real worktree remove --force wt`：

```
RC=0
wt_exists=False
real_nm_exists=True
scope_entries=            (linkA/linkB/linkC 全被删)
plainpkg_files=0
pkgA=0  pkgB=0  pkgC=0    (三处 junction 目标内容被清空)
git status --porcelain:   D packages/pkgA/a1.txt ... (12 条 deleted)
```

-> **junction 被穿透，真树 `node_modules` 与其内部一层、两层链接的目标一起被清空，且 git 返回 0（静默）。** 这也解释了 PM 事后必须用 `npm install --ignore-scripts` 重建链接。

### 3.3 复现 B：加一把独占锁 -> 逐字复刻线上的「部分删除 + rc=255 + worktree 与 junction 都留下」（`%TEMP%\jrepro-in1d`）

fixture 同上但 `pkgC` 有 c1..c6；执行前对 `real\packages\pkgC\c4.txt` 持独占句柄：

```
git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/jrepro-in1d/wt': Invalid argument
RC=255
wt_exists=True                       <- worktree 未被删（= 线上 qg-head 形态）
wt_nm_link_exists=True               <- junction 仍在（故 20:32:28 还需再 rmdir 一次）
real_nm_children=@scope,plainpkg     <- 位于中止点之后的条目幸存
scope_entries=linkC                  <- linkA/linkB 已删，最后一条 linkC 保留
plainpkg_files=1                     <- 未到达
pkgA=(空) pkgB=(空)                   <- 已删目标被清空
pkgC=c4.txt,c5.txt,c6.txt            <- 最后一条链接的目标只删了一部分（c1..c3 已删，c4 被锁 -> 中止）
```

**错误文本与线上逐字相同**（`failed to delete '<worktree>': Invalid argument`，rc=255），中止后的残留形态与真树观测**一一对应**：

| 复现 B 现象 | 真树对应观测 |
|---|---|
| worktree 与 junction 都留下 | jsonl:145 还需再 `cmd /c rmdir "$t\node_modules"`；`Test-Path $t` 为 True |
| 最后一条 junction 的**链接**保留、其目标只删一部分 | `pi-tui` junction 保留（mtime 仍 2026-08-10），`packages/tui` 只删 156/236 |
| 中止点之后的条目全部幸存 | `@earendil-works` 之后的 219 个 `node_modules` 条目全部未动 |

**本轮踩坑记录（供复核者复算）**：第一次搭建 fixture 时忘了 `.gitignore` `node_modules/`，`git add -A` 把 `node_modules` 提交进仓库，导致 `git worktree add` 把它签出为**真目录**，`mklink` 报「文件已存在」失败，于是 `git worktree remove` 变成「无 junction」场景、得到「不穿透」的**错误结论**。修正 fixture 后立刻复现穿透。**若有人得到「git 不穿透 junction」的结论，先检查这一点。**

### 3.4 真树自洽证据（工件级；本轮新增，采集于 2026-10-10 11:1x）

| 观测 | 本轮实测值 | 与机制的对应 |
|---|---|---|
| `packages/agent` 已跟踪文件 mtime | 226/226 = **2026-10-09** | 全部被删后由 `git checkout --` 重建 |
| `packages/ai` | 1060/1060 = 2026-10-09 | 同上 |
| `packages/client` | 63/63 = 2026-10-09 | 同上 |
| `packages/evals` | 19/19 = 2026-10-09 | 同上 |
| `packages/protocol` | 49/49 = 2026-10-09 | 同上 |
| `packages/server` | 99/99 = 2026-10-09 | 同上 |
| `packages/session-backends` | 101/101 = 2026-10-09 | 同上 |
| `packages/coding-agent` | 1683 = 716（2026-10-09，事故重建）+ 967（2026-10-10，事后又被其它 key 编辑而刷新 mtime） | 与首轮「destroyed 1683/1683」一致；当前 mtime 分布已被后续编辑叠加 |
| **`packages/tui`** | 236 = **80（2026-08-05）+ 156（2026-10-09）** | **中止点**：156 个被删后重建，80 个从未被删 |
| **`packages/multi-workers`** | 200 个文件中仅 **8** 个为 2026-10-09（其余为 8 月-9 月旧 mtime） | **它不是任何 workspace junction 的目标**，故完全未被卷入 -> 反证「删除是沿 junction 目标传播」 |
| `node_modules\@earendil-works` | 9 条 junction；`pi-tui` mtime **2026-08-10 18:09:09**（从未被删）；其余 8 条 mtime 2026-10-09 20:39:03（npm 重建）；`gondolin` 是真目录 | 中止发生在枚举顺序最后一条 `pi-tui` |
| `node_modules` 直接子项（2026-10-10 11:22:55） | 共 **230**；按 NTFS 大写序 `<= "@earendil-works"` 的条目 = **11**（`.bin` `.package-lock.json` `@anthropic-ai` `@aws` `@aws-crypto` `@aws-sdk` `@babel` `@bcoe` `@biomejs` `@cto.af` `@earendil-works`）；其后 = **219** | 删除在 `@earendil-works` 处中止，边界口径与首轮一致（11 + 219 = 230） |
| 恢复链 | 首轮报告实测 `git ls-files -d -z | xargs -0 -r -n 200 git checkout --`：`deleted_before=3456` -> `deleted_after=0`（20:36:07-20:38:18）| 与上表被删文件数一致 |

**口径修正（对 PM 的「9 条 junction」）**：`node_modules\@earendil-works` 下共 **9 条 junction**（8 条 `pi-*` 包 + `pi-tui`），另有真目录 `gondolin`。事故中消失的是 **8 条**（pi-agent-core / pi-ai / pi-client / pi-coding-agent / pi-evals / pi-protocol / pi-server / pi-session-backend-sqlite-node），`pi-tui` 是原物保留。

### 3.5 为什么会产生「只删链接、包目录完好」的错觉

那条命令其实删了两类东西：**8 条 workspace junction（链接）** 与 **其目标 `packages\*` 的文件内容**。恢复分两步且都很快：

1. key `mw-vision-role` 的 worker `mvr-t14-verification-closeout`（session `01a1208f-d2f3`）在 20:36:07-20:38:18 执行 `git ls-files -d -z | xargs -0 -r -n 200 git checkout --` -> `deleted_before=3456`、`deleted_after=0`。
   **副作用**：`git checkout -- <path>` 把命中路径重置为 HEAD，于是这批文件上的**未提交改动被丢弃**（= IN-2 的症状）。
2. PM 在 20:38:58 执行 `npm install --ignore-scripts` -> 重建 8 条 junction（mtime 20:39:03）与被删的 `node_modules` 条目；lockfile/shrinkwrap 零改动。

所以 PM 事后看到的「230 包完好、最老 mtime 8/10」是**恢复后**的状态；`pi-tui` 的 `8/10` mtime 恰好是**从未被删**（中止点）的一手证据。

## AC-004：同日全部 worktree 清点（谁建、谁清、是否用 junction 指回真树）

时间均为本地 UTC+8（括号内 UTC）。执行者写作 `sid 前 8 位 / worker / key`。来源 = **全部**会话 jsonl 中 timestamp 落在 2026-10-09 的已执行 toolCall（按 `worktree add|remove|prune` 与 `mklink|Junction|SymbolicLink` 两条独立扫描交叉得出）。

| # | 路径 | 建立 | 建者会话（job） | junction -> 真树？ | 清理 | 结果 |
|---|---|---|---|---|---|---|
| 1 | `%TEMP%\mwvis-head` | 11:08:59.294 (03:08:59Z) | `01a0dcd2` / mw-vision-role PM 窗口 | **无**（当日无任何 junction 创建命令命中该会话） | `git worktree remove --force` 11:10:32.902 (03:10:32Z)，同会话 | 干净；真树无损 |
| 2 | `%TEMP%\mw-t23-wt` | 20:17:10.516 (12:17:10.516Z) | `01a1208a-970a` / `msc-t23-status-parity-lock` / mw-autopilot-slot-capacity | **有**：`cmd /c mklink /J "<wt>\node_modules" "H:\git\Multi-Workers\node_modules"`（L87） | 12:25:20.949Z **先** `cmd /c rmdir "$wt\node_modules"`，**后** `git worktree remove --force` + `prune`（L107） | 干净；真树无损（正确做法） |
| 3 | `H:\git\Multi-Workers\.tmp-t09-wt`（仓内） | 12:20:45.511Z（L64） | `01a1208f-7449` / `mvr-t09-worker-image-cap-backstop` / mw-vision-role | **无**：该会话用**真树的绝对路径** `H:/git/Multi-Workers/node_modules/vitest/dist/cli.js` 跑测试，未建 junction | `git worktree remove --force` 12:23:34.229Z（L82），同会话 | 干净；真树无损 |
| 4 | `H:\git\Multi-Workers\.tmp-t13-wt`（仓内） | 12:22:28.534Z（L72） | `01a1208f-bf0c` / `mvr-t13-pm-awareness-texts` / mw-vision-role | **有 2 条**：`<wt>\node_modules` 与 `<wt>\packages\coding-agent\node_modules` -> 真树同名目录（`New-Item -ItemType Junction`） | 12:27:14.975Z **先** `cmd /c rmdir` 两条 junction，**后** `git worktree remove`（L107） | 干净；真树无损（正确做法） |
| 5 | `%TEMP%\qg-head` | 12:21:48.660Z（L60） | `01a1208f-e335` / `mvr-t16-quality-gate-review` / **mw-vision-role** | **有**：`cmd /c mklink /J "<wt>\node_modules" "H:\git\Multi-Workers\node_modules"`（L60/L61 回显已坐实） | 12:32:18.452Z **直接** `git worktree remove --force`（**未先摘 junction**）-> **本次事故**；12:32:28.112Z 补救 `rmdir` + `Remove-Item -Recurse` | worktree 最终消失，**真树被破坏** |
| 6 | `%TEMP%\mwvg-t5-probe`（非 worktree 的探针工程） | 12:26:08.833Z（L143） | `01a12091-b135` / `mwvg-t5-verify` / mw-worker-visibility-gate | **有**：`if (-not (Test-Path $p)) { New-Item -ItemType Junction -Path "$env:TEMP\mwvg-t5-probe\node_modules" -Target "H:\git\Multi-Workers\node_modules" }` | 当日扫描未发现其清理命令 | 该 `<probe>\node_modules` 现已不存在（本轮实测），但目录本身仍在；首轮报告记「未清理」，本轮记为 **已消失/清理者不明** |
| 7 | `.tmp/t13-worktree`（spec 提及） | — | — | — | — | **未找到**：2026-10-09 全部已执行 toolCall 中无此路径；当日仓内 worktree 只有 `.tmp-t09-wt` 与 `.tmp-t13-wt`。记为 [未坐实] |

**当前仍指向真树的 junction（本轮实测，2026-10-10 11:20）—— 同类事故的「活雷」**

| 路径 | 目标 | junction mtime |
|---|---|---|
| `%TEMP%\mwvg-t5\node_modules` | `H:\git\Multi-Workers\node_modules` | 2026-09-23 18:58:38（旧雷，非 10-09 事故） |
| `%TEMP%\qg2-head\node_modules` | `H:\git\Multi-Workers\node_modules` | 2026-10-10 11:07:51（**事故后新埋**；`qg2-head` 是 10-10 新建的 worktree） |

**状态漂移说明**：首轮报告记「`git worktree list` = 仅主树；`.git/worktrees` 为空」。**本轮实测已不同**（2026-10-10 11:09）：`git worktree list` 有 5 项 —— 主树 `H:/git/Multi-Workers 10446aefb [dev/AgentTeam]`、`%TEMP%/mwbase-head`、`%TEMP%/qg2-head`、`H:/tmp/fmr76b`、`H:/tmp/t23wt-mine`。`qg-head`、`mw-t23-wt`、`.tmp-t09-wt`、`.tmp-t13-wt` 均已不存在。故 AC-004 的「现状」一栏必须以采集时刻为准。

**可迁移的教训（对照）**：当日 4 次「worktree 内带 junction 指回真树」的操作中，**先 `rmdir` 摘链接再删 worktree** 的 2 次（#2、#4）零事故；**直接 `git worktree remove --force`** 的 1 次（#5）造成事故；#6 与 10-10 的 `qg2-head` 是同一类未拆的雷。**根因是「用会穿透 junction 的删除工具删一个含 junction 的目录」，而不是「worktree 本身危险」。**

## 5. 排除项复核 / 失效证据 / caveat

1. **PM 的「npm 未被调用」判据失效（本轮实测反例）**：`%LOCALAPPDATA%\npm-cache\_logs` 现存 **11 个文件、最早 mtime 2026-10-10 11:07:28**；`npm config get logs-max` = **10** —— npm 按设计只保留最近 N 条日志，因此该目录**在结构上就不可能**留存 2026-10-09 的记录。PM 自己在 20:38:58 执行的 `npm install --ignore-scripts` 也没留下可查记录。=> 该来源不能支持「17:00-20:41 npm 0 次调用」。**但「npm 不是本事故元凶」仍成立**：npm 不会删除已跟踪源码文件，而 3456 个 tracked 文件确实消失。
2. **「node_modules 未整体重装」需修正**：事故点之前的 11 个直接子项（`.bin`、`.package-lock.json`、`@anthropic-ai`、`@aws*`、`@babel`、`@bcoe`、`@biomejs`、`@cto.af`、`@earendil-works`）与 `@earendil-works` 内 8 条 junction 都是 20:38:58 的 `npm install` **重建**的；「最老 mtime 8/10 的 230 包完好」只适用于 `@earendil-works` 之后的条目。
3. **删除工具的排除是「互相独立」的两条线**：§3.1 的 6 组实测说明只有 `git worktree remove --force` 能造成本现象；§AC-001 的窗口扫描说明 20:32:10-35 内**唯一**被执行且带删除语义的命令就是它。两条独立证据指向同一条。
4. **mtime 证据是「会漂移的活体」**：本轮采集期间（2026-10-10 11:21）观察到一次并发 `npm install` 重写了 `node_modules/.bin`、`.package-lock.json`、`@anthropic-ai`、`@aws*`、`@babel`、`@bcoe`、`@biomejs`、`@typescript`、`@earendil-works/pi-ai|pi-coding-agent|gondolin` 等条目的 mtime（`@biomejs` 一度显示 2026-10-10 11:18）。**任何基于 `node_modules` 条目 mtime 的结论都必须带采集时刻**；`packages/*` 的 tracked 文件 mtime 相对稳定（8 个包 100% 落在 2026-10-09），是本报告最可靠的一手证据。
5. **首轮与次轮的可复算差异**：首轮 `[VERIFY] nm_entries_before_@earendil-works=11 all_mtime=2026-10-09T20:39:0x` 在本轮已无法逐条复算（其中 9 条被 10-10 11:21 的 npm 运行改写 mtime）。本轮的等价结论改用 NTFS 枚举顺序的**条目集合**（11 个名字）表述，不依赖其 mtime。
6. **`Remove-Item -Recurse -Force $t`（jsonl:145）本身不穿透**（§3.1 实测）：它在线上发生在 `cmd /c rmdir "$t\node_modules"` 之后，且此时即使 rmdir 静默失败，PowerShell 5.1 的 `Remove-Item -Recurse` 也不穿透 junction —— 故它不是（也不可能是）元凶。
7. **[未坐实]**：导致真树 `packages\tui` 内 `unlink` 失败（EINVAL）的**具体被占用文件/进程**。已复现「同类失败 -> 逐字相同的错误文本 + 相同中止/残留形态」，但真树当时是哪个句柄造成 EINVAL，无法从只读证据反推。

## 6. 与 IN-2 的交叉引用（供 PM 做同源判定）

| 时刻（本地） | 事件 | 证据 |
|---|---|---|
| 20:21:48 | 建 `%TEMP%\qg-head` + `node_modules` junction -> 真树 | jsonl:60/61 |
| **20:32:18.452 - 20:32:24.444** | `git worktree remove --force qg-head`（**穿透 junction**）-> 8 条 workspace 链接消失 + 3456 个已跟踪文件消失 + 11 个 `node_modules` 子项消失；rc=255 中止 | jsonl:142/144；`node_modules` 目录 mtime 20:32:22 |
| 20:32:28 | 补救删掉残留 worktree | jsonl:145/146 |
| 20:36:07-20:38:18 | worker `mvr-t14-verification-closeout` 执行 `git checkout -- <3456 paths>`：`deleted_before=3456` -> `deleted_after=0`（副作用：丢弃这批文件上的未提交改动） | session `01a1208f-d2f3`（IN-2 主证） |
| 20:38:49 | PM 首次观测「只剩 `pi-tui`」 | session `01a0d325` jsonl 第 2925 行（本轮已复核：`LinkType=Junction Name=pi-tui` 为唯一一条） |
| 20:38:58 | PM 执行 `npm install --ignore-scripts` -> 重建 8 条 junction（20:39:03）与被删 `node_modules` 条目 | session `01a0d325` jsonl 第 2926/2927 行 |

**本 worker 的判定**：IN-1 与 IN-2 **同源、同一命令、同一事件** —— IN-1 是「链接层」观测，IN-2 是「目标文件层」观测；两者在时间戳（20:32:22-24）、损坏边界（9 个 workspace 包，`tui` 部分）、恢复链（`git checkout` + `npm install`）三点互证。IN-2 的 AC-005 应指向 **jsonl:142 同一条命令**；AC-006 的候选清单里 `worktree remove --force` 应由「候选」升为**已坐实**（机制支撑见 §3）。

## 7. 未坐实清单（合并首轮 + 本轮）

1. 触发 12:01:47Z/10-09 重派 `mvr-t16` 的具体 PM 窗口/命令（10-09 的 `_workers.parallel` 行已被 10-10 重派覆盖）。
2. 真树 `packages\tui` 内造成 EINVAL 的具体被占用文件/进程。
3. `.tmp/t13-worktree` 路径（spec 提及，2026-10-09 全量 toolCall 检索未命中）。
4. 10-09 worker 进程 pid（首轮报 `159560`，本轮 trace.log 10-09 `[START]` 行不含 pid）。
5. `%TEMP%\mwvg-t5-probe\node_modules` junction 的清理者（本轮确认已不存在，但未找到清理命令）。
6. 首轮 `[VERIFY] nm_entries_before_@earendil-works=11` 的逐条 mtime（已被 10-10 11:21 的 npm 运行改写；集合口径仍成立）。
7. `packages/coding-agent` 目录 mtime = 20:32:24 的自采数据（首轮引用 worker 实测，本轮未复算）。

## 8. 只读合规声明

- 未执行 `checkout` / `reset` / `stash` / `clean` / `worktree remove` / `worktree add`；未建或删任何 worktree；未修改仓库任何文件（`.agenticdoc/**` 其它 key 与代码均未触碰）。
- 机制复现全部发生在 `%TEMP%\jrepro-in1*`、`%TEMP%\jctl1..5`（临时目录内自建 git 仓库）；**未触碰 `H:\git\Multi-Workers` 的任何 junction、junction 目标或受管文件**（已用「fixture 内不含 Multi-Workers 路径」断言复核）。
- 唯一写入物 = `H:\git\Multi-Workers\.agenticdoc\mw-workspace-incident-probe\evidence\in1-junction-incident-20261009.md`（本文件）。
- 对 `C:\Users\wenbozhou\.pi\agent\sessions` 仅做读取（os.walk 遍历 jsonl）；对 npm `_logs` 仅 `Get-ChildItem`。