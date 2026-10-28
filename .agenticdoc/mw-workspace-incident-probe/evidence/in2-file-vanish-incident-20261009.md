# IN-2 取证报告（重跑·修正版）：3,531 个已跟踪文件「消失又恢复」（2026-10-09）

- key: `mw-workspace-incident-probe` · worker: `inc2-vanish-forensics`（type: research）
- 对应 AC: **AC-005 / AC-006 / AC-007**（spec `.agenticdoc/mw-workspace-incident-probe/spec.md` §1.2 / §2）
- 方法: **只读**。未执行任何 `checkout` / `reset` / `stash` / `clean` / `worktree add|remove|prune` / `rm`；未改仓库任何文件（唯一产出 = 本文件）
- 采集时刻: **2026-10-10 11:00–11:25（UTC+8）**。工作树是**活的**（并行多 key 会话在同时改文件、建/删 worktree）：本文件所有实测值都带测量时刻，跨分钟会漂移的项已标注
- 口径: `[VERIFY]` = 本次实测（附录 A 为可复算的机器输出）；标注「交叉引用 / 推断 / 算术」的**不得当实测**
- 路径记法: 会话记录根目录 = spec §3 证据源 1 所列的 pi session store（绝对路径在本文件各处按引用直接写出；同一会话文件在多处出现时以 `--H--git-Multi-Workers--\<session-file>.jsonl` 的形式给出）

---

## 0. 结论速览

| AC | 结论 | 置信度 |
|---|---|---|
| **AC-005** | **坐实**。元凶 = `git worktree remove --force "$env:TEMP\qg-head"`，由 worker `mvr-t16-quality-gate-review`（key `mw-vision-role`，pid 159560）于 **2026-10-09T12:32:18.452Z（本地 20:32:18.452）** 执行；来源 jsonl **L142**。该命令借 worktree 根下的 `node_modules` junction 穿透进真树，清空 8 个包整树 + 部分 `packages/tui`（共 **3,456** 个已跟踪文件），并在 `pi-tui` 处 EINVAL 中止（RC=255） | 高（命令原文 + 外部账本 + 中止指纹 + 兄弟 worker 复现）|
| **AC-006** | 机制 = **两段动作**：① `git worktree remove --force` 的**跟随 reparse point 的递归删除**（删文件 + 删 8 条 workspace 链接 + 部分中止）；② worker `mvr-t14-verification-closeout` 的**路径级强制 checkout**：`git ls-files -d -z | xargs -0 -r -n 200 git checkout --`（只把「当前缺失」的 3,456 条路径按 index 写回 ⇒ 恢复文件 + **静默丢弃这些路径上的未提交改动** + HEAD/reflog 不动） | 高 |
| **AC-007** | **可能性 (a) 坐实**：改动确曾被写入（`edit` toolCall **12:10:02.943Z** + 成功结果 + **两个独立会话**在 12:10:40 / 12:10:46 回读到 `process.stdout.write`@**L91**），随后 20:32 随树被删、20:37–20:38 被路径级 checkout 覆盖回 HEAD（`console.log`@**L88**）。⇒ **该 12:13:31Z 复验行不是假声明** | 高 |

一句话：**这不是 git ref 级操作**（HEAD/reflog 未动、无 stash、无残留 worktree），而是「**junction 穿透式递归删除（git worktree remove）** + **路径级强制 checkout**」的组合；两段动作分别由**两个不同的 worker 进程**执行。

---

## 1. AC-005：已执行命令原文 + 执行者会话 + 精确时刻 + 来源 jsonl

### 1.1 元凶命令（toolCall）

- 来源文件: `C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` **第 142 行**（文件共 149 行）
- 时刻: toolCall **2026-10-09T12:32:18.452Z**（本地 **2026-10-09 20:32:18.452**，UTC+8）
- 命令原文:

```powershell
cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" 2>&1 | Out-String; "RC=$LASTEXITCODE"; git worktree list | Out-String
```

- toolResult（同文件 **第 144 行**，**2026-10-09T12:32:24.444Z**，即命令耗时约 **5.99 s**）:

```
git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument
RC=255
H:/git/Multi-Workers 10446aefb [dev/AgentTeam]
```

- 执行者会话:

| 项 | 值 |
|---|---|
| session 文件 | `C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` |
| cwd slug / cwd | `--H--git-Multi-Workers--` / `H:\git\Multi-Workers` |
| session id | `01a1208f-e335-767d-a127-bf295f75a861`（session 起始 `2026-10-09T12:07:43.157Z`）|
| 进程 | 其 `trace.log` 区间 `[START] ... 2026-10-09T12:07:43.239Z` … `[END] 2026-10-09T12:32:43.510Z exit=0 elapsed=1500s tools=88`；该段前一行 `[START] pid=159560` |
| worker / key | **`mvr-t16-quality-gate-review`**（type: research）· key **`mw-vision-role`** · 卡片 `T-16-quality-gate-review` |
| 派发记录 | `.agenticdoc\_workers.parallel` 中 `mvr-t16` 行（2026-10-10T02:50:05.627Z → 2026-10-10T03:20:41+00:00 为最近一次重派；事故那次由 IN-1 报告引作 `_workers.parallel:200`）|

- **独立账本交叉验证**（不是同一份 jsonl 的转述）: `.agenticdoc\mw-vision-role\workers\mvr-t16-quality-gate-review\trace.log` **第 467 行**
  `[TOOL] 2026-10-09T12:32:18.454Z bash cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" ...`（比 jsonl toolCall 早 2 ms 记录，同一命令）。

### 1.2 前置条件：把 junction 建出来（同一会话，第 60 行）

- 时刻 **2026-10-09T12:21:48.660Z**（本地 20:21:48.660），toolResult 12:23:10.095Z（含 `Updating files: ... 4590` 的 worktree checkout 过程）
- 原文:

```powershell
cd H:/git/Multi-Workers; $t="$env:TEMP\qg-head"; if(Test-Path $t){ git worktree remove --force $t 2>$null; if(Test-Path $t){ cmd /c rmdir /s /q "$t" } }; git worktree add --detach $t HEAD 2>&1 | Out-String; "RC=$LASTEXITCODE"; cmd /c mklink /J "$t\node_modules" "H:\git\Multi-Workers\node_modules"; Test-Path "$t\node_modules\vitest"
```

`$t` 当时不存在，故 `git worktree remove` / `rmdir /s /q` 分支未执行；末尾 `mklink /J` 在 **worktree 根建了一条指回真树 `node_modules` 的 junction**。这是「对 worktree 的递归删除能进到真树」的唯一通道。

- 动机（**模型自述，非执行证据**，仅背景）: 12:21:28 附近 thinking 记为 «isolate from concurrent edits and give a trustworthy verdict for HEAD»；12:21:48 附近记为 «set up a clean detached worktree at HEAD for deterministic evidence»。

### 1.3 删除瞬间的夹逼：本地 20:32:14.011 – 20:32:29.183

| 时刻（UTC / 本地） | 观测（toolResult 原文摘要） | 来源 jsonl |
|---|---|---|
| **12:32:14.011Z** / 20:32:14.011 | `git status --porcelain -- .agenticdoc/mw-vision-role/evidence/reviews packages/coding-agent/src packages/multi-workers/mw_common.py packages/multi-workers/autopilot/dispatch.py` 输出仅 2 条 ` M`，**0 条 ` D`** ⇒ 代码树完好 | `...e335...` L140/L141 |
| **12:32:18.452Z** | 元凶命令发出 | `...e335...` L142 |
| 12:32:24.249Z | `Get-FileHash` 对 4 个 `packages/coding-agent/src/extensions/agent-team-loop/{worker/worker-file-tool.ts,worker/worker-mode.ts,worker/output-writer.ts,rag/tools.ts}` 成功返回 4 个哈希 | `...1dab...` L175/L176 |
| **12:32:24.444Z** | 元凶命令返回 `RC=255`（`Invalid argument`） | `...e335...` L144 |
| 12:32:28.112Z | 善后命令发出：`cmd /c rmdir "$t\node_modules"` + `Remove-Item -Recurse -Force $t` | `...e335...` L145 |
| **12:32:29.183Z** | `read .../pm/pm-orchestrator.ts` → `ENOENT: no such file or directory, access 'H:\git\Multi-Workers\packages\coding-agent\src\extensions\agent-team-loop\pm\pm-orchestrator.ts'` | `...1dab...` L178/L179 |
| 12:32:32.548Z | 列 `packages\coding-agent\src\...\pm\` → `PathNotFound`；`rg packages/coding-agent/src` → `os error 2` | `...1dab...` L181/L182 |
| 12:32:33.691Z | 上述 toolResult 落地 | `...1dab...` L182 |
| 12:32:54.960Z | `git status --short` 行数 = **3531** | `...1dab...` L187/L188 |

[VERIFY] **删除区间 = 2026-10-09T12:32:14.011Z – 12:32:29.183Z（本地 20:32:14.011 – 20:32:29.183）**；元凶命令的 5.99 s 执行窗 100% 落在此区间内。

**口径说明（防止过度精确）**：jsonl 里同一条 assistant 消息的多个 toolCall，其 toolResult 会共用**同一个落地时间戳**。因此 12:32:24.249Z 的 `Get-FileHash` 结果是「批次 flush 时间」（该批次 12:32:01.117Z 起跑，同批的慢命令是 96 s 的 vitest），哈希本身可能早在 12:32:02 就已完成。这不影响结论：上界可靠来自 12:32:14.011Z 的 `0 条 D`，下界可靠来自 12:32:29.183Z 的 ENOENT。

### 1.4 为什么不是同会话的 L145（善后命令）——显式判别

L145（12:32:28.112Z 起）也落在夹逼区间内，必须排除：

1. **通道先被摘掉**：L145 的第一条语句是 `cmd /c rmdir "$t\node_modules"`（**无 `/S`，只摘链接**），它在 `Remove-Item -Recurse -Force $t` **之前**顺序执行。摘掉后 `qg-head` 内不再有指回真树的入口，`Remove-Item` 无从进入真树 `node_modules`。
2. **能进入 L145 的分支这一事实本身**证明 L142 没删掉那条链接（`if(Test-Path $t)` 成立；结果 `still_exists=False`）。
3. **工具语义**：`cmd /c rmdir`（无 `/S`）与 PowerShell 5.1 `Remove-Item -Recurse -Force` 对 junction **不穿透**（来源口径见 §1.6）。
4. **中止指纹只与 git 相符**：真树留下的是「8 个包 **100%** 清空 + `packages/tui` 只删 **156/236** + `pi-tui` junction **原物保留**（mtime `2026-08-10 18:09:09`）+ 返回 `failed to delete '<worktree>': Invalid argument`（RC=255）」这一组签名。PS 递归删除不会产生该签名（要么删干净、要么报权限/占用错），也不会给出 `Invalid argument` 与「worktree 本体反而没删掉」的组合。
5. **窗口内没有第二条**具备删除语义、且作用对象可达真树的已执行命令（§1.5 穷举）。

### 1.5 唯一性核验（穷举，非抽样）

- 扫描口径: session store 下**全部** `*.jsonl`（不按文件名日期过滤，以覆盖跨日长会话）；**只取已执行命令** = `message.content[].type == "toolCall"` 且 `arguments.command` 为字符串者；模型思考/讨论文本严格排除（当日确有大量 worker 在「讨论」`git stash`，那些不是执行）。
- [VERIFY] **12:32:15Z–12:32:40Z 全量 bash toolCall**（25 s）中，命令文本触及 `node_modules` / worktree / 链接的**只有 2 条**：L142（12:32:18.452Z）与 L145（12:32:28.112Z）。其余为 pytest、文档 python 脚本、`git status`、`Start-Sleep` 等，均不触及真树 `packages/**`。
- [VERIFY] **12:20:00Z–12:46:00Z** 内命中破坏性动词表（`mklink|worktree (add|remove|prune)|Remove-Item|rmdir|rimraf|shutil.rmtree|os.remove|unlink|git clean|git checkout|git restore|git reset|git stash|git rm|robocopy|xcopy`）的已执行命令中，**作用对象落在真树 `node_modules` 或 `packages/**` 的为 0 条**；唯一的 `git worktree remove --force` 目标就是 `$env:TEMP\qg-head`。
- [VERIFY] 该窗口内**没有任何已执行的 `git stash`**（出现的全部是 `git stash list` 只读查询）；`refs/stash` 与 `logs/refs/stash` 至今不存在（§3.1）。

### 1.6 机制支撑的来源口径（重要）

硬规则禁止本 worker 执行 `worktree remove`，因此**本次未自行复现**「git 的递归删除跟随 junction」。本报告对机制的支撑分三层，**逐层标明来源**：

1. **本次实测（一手，§2.1/§2.3）**：受害面**精确等于** `node_modules\@earendil-works\` 下 8 条 junction 的目标树，且中止点恰好落在第 9 条（readdir 顺序最后）`pi-tui` —— 这是「删除沿链接遍历」的**形态学指纹**。
2. **交叉引用（兄弟 worker，同 key）**：`inc1-junction-forensics` 在 `%TEMP%\jrepro*` 内做了四工具对照复现 —— `git worktree remove --force` **穿透**（无锁时 rc=0 且清空目标；加独占句柄时复刻出**逐字相同**的 `failed to delete '<wt>': Invalid argument` + rc=255 + worktree 与最后一条链接保留 + 目标被部分删除的残留形态）；`cmd /c rmdir`、PS 5.1 `Remove-Item -Recurse` **不穿透**。见 `evidence/in1-junction-incident-20261009.md` §3.1–3.3。
3. **推断**：MSYS2 下 junction（`IO_REPARSE_TAG_MOUNT_POINT`）对 git 呈现为**普通目录**，故被 `opendir/readdir` + `unlink/rmdir` 穿透。

第 3 层是推断，第 2 层不是本 worker 的实测——两者都**不作为**「本次实测」表述。

---

## 2. 事实重建（实测）

### 2.1 损害面 = 3,456 个已跟踪文件，精确等于「8 个包整树 + `packages/tui` 的 156」

[VERIFY] `git ls-files` tracked 总数 = **4590**；按包（2026-10-10 11:1x 实测）：

| 包 | tracked | 事故中被删 |
|---|---|---|
| coding-agent | 1683 | 1683（全部）|
| ai | 1060 | 1060（全部）|
| agent | 226 | 226（全部）|
| session-backends | 101 | 101（全部）|
| server | 99 | 99（全部）|
| client | 63 | 63（全部）|
| protocol | 49 | 49（全部）|
| evals | 19 | 19（全部）|
| **8 包小计** | **3300** | **3300** |
| tui | 236 | **156**（dist 148 + 根文件 1 + native 7；`src` 37 与 `test` 36 **完好**）|
| **合计** | | **3456** |

- [VERIFY] 8 包 tracked 求和 = **3300**；3300 + 156 = **3456**，与两处**独立实测**的 ` D` 计数**恰好相等**：
  - `git status --porcelain` → `TOTAL=3531`、`---D count--- 3456`（`C:\Users\wenbozhou\.pi\agent\sessions\...12-02-43-303Z_01a1208b-4fe7-720f-8c04-88c2447dfbdb.jsonl` L117/L118，12:36:09.236Z）
  - `git ls-files -d | wc -l` = **3456**（`C:\Users\wenbozhou\.pi\agent\sessions\...12-07-38-995Z_01a1208f-d2f3-77c3-a241-d6c43402bece.jsonl` L200/L201，12:35:46.314Z）
- `3531 − 3456 = 75`（= 当时的 ` M`/`??` 条目数）。这是**算术关系**，不是单独实测；旁证：12:38:26.354Z 同一会话实测 `total modified: 74`。
- [VERIFY] `packages/tui` 细分（按 tracked 文件 mtime 归属，本次实测）:
  - `dist` **148** 个 → 全部 mtime `2026-10-09 20:38`（= 被删后重建）
  - `src` **37** + `test` **36** → 全部 mtime **`2026-08-05 18:02:56`**（= 从未被删；`packages\tui\src`、`packages\tui\test` 目录 mtime 同为该值）
  - `native` 10 个 → 3 个旧 / 7 个新；根文件 5 个 → 4 个旧 / 1 个新
  ⇒ 被删的 156 = 148 + 1 + 7（**实测**）
- [VERIFY] 包目录 mtime：`agent 20:39:02`、`ai 20:39:02`、`coding-agent`（今日被再次改动，事故后的值已不可读）、`evals 20:39:02`、`protocol/src/dist/test 20:38:02`、`server 20:38:02`、`tui/src 2026-08-05 18:02:56`、`tui/dist 20:38:13`、`session-backends` 顶层 `2026-08-05 18:02:56`（其 junction 目标是其子目录 `sqlite-node`）
- **形态学结论**：8 个目标 **100% 清空** + 最后一个目标（`packages/tui`）**只被删一部分** ⇒ 删除**在 `packages/tui` 内部中止**。这与 §2.3 的链接指纹一一对应。

### 2.2 恢复面

- 恢复脚本生成: `C:\Users\wenbozhou\.pi\agent\sessions\...12-07-38-995Z_01a1208f-d2f3-77c3-a241-d6c43402bece.jsonl` **L204**（**12:36:04.137Z**，`write` → `C:/Users/wenbozhou/AppData/Local/Temp/mwv14c/restore.sh`）
- 执行: 同文件 **L206**（**12:36:07.381Z**）`& "D:\Program Files\Git\bin\bash.exe" "C:/Users/wenbozhou/AppData/Local/Temp/mwv14c/restore.sh"`
- 结果: 同文件 **L207**（**12:38:18.363Z**）`deleted_before=3456` / `checkout_batches_rc=0` / `deleted_after=0`
- 复验: 同文件 **L208/L209**（12:38:26.354Z）`--- deleted now --- 0`；`total modified: 74`

[VERIFY] mtime 直方图（tracked 文件，本次实测两次以显示漂移）：`2026-10-09 20:36 = 1202`、`20:37 = 833`（11:1x 那次为 835）、`20:38 = 457`，其余分钟 ≤3；落在 `2026-10-09 20:xx` 的 tracked 文件合计 **2512**（11:1x 那次为 2537）。
[VERIFY] **今日 `2026-10-10` 有 1048 个 tracked 文件获得新 mtime，其中 953 个是 `packages/coding-agent/dist/**`**（今日 10:53 的一次构建/emit，`packages/coding-agent` 目录 mtime 已变为 `2026-10-10 11:10:32`）。**读 mtime 直方图时必须扣除这批，否则会把构建误判成恢复**；这也是上一版报告写下的 `3550` 与本版 `2512` 的差额来源（3550 − 953 ≈ 2597 ≈ 2512，逐分钟漂移同量级）。
[VERIFY] 未被恢复动作触碰的无关 tracked 文件保持旧 mtime：`README.md = 2026-09-15 21:22:16`、`AGENTS.md = 2026-09-21 23:22:30`、`package.json = 2026-08-05 18:02:55`、`scripts\ = 2026-08-05 18:02:56`
[VERIFY] 现在：`git ls-files -d` = **0**；`git status --porcelain` 计 ` M` = **106**、`??` = **30**、` D` = **0**（2026-10-10 11:2x；这些计数随并行会话变化）

### 2.3 workspace 链接与 node_modules 指纹（本次实测）

[VERIFY] `node_modules\@earendil-works\` 共 **10** 个条目 = **9 条 junction + 1 个真实目录**：

```
pi-agent-core, pi-ai, pi-client, pi-coding-agent, pi-evals,
pi-protocol, pi-server, pi-session-backend-sqlite-node
    → 8 条 junction，LastWriteTime 全部 = 2026-10-09 20:39:03（npm 重建）
pi-tui   → junction，LastWriteTime = 2026-08-10 18:09:09（原物，未被删/未被重建）
gondolin → 真实目录（非链接），2026-10-09 20:39:04
```

- 8 条被重建的 junction 名字与被清空的 8 个包树**一一对应**（`pi-evals ↔ evals`、`pi-session-backend-sqlite-node ↔ packages\session-backends\sqlite-node`、其余同名）。
- **`pi-tui` 保留 + 其目标 `packages\tui` 只删 156/236**，两者互相印证「中止点落在 readdir 顺序最后一条链接」。
[VERIFY] `node_modules` 一级条目 mtime 分布：`2026-08-10 = 196`、`2026-10-09 = 25`、`2026-10-10 = 1`（11:1x 那次为 196 / 34 / 1 —— 同样显示同步漂移）。⇒ 真树 `node_modules` **未被整体重装**（196 个包仍是 8/10 原物），被删/被重建的只是 `@earendil-works` 位置之前的少量条目。

### 2.4 删除过程的其它旁证

- 同会话 **12:32:28.112Z** thinking（**自述**，非执行证据；`[QG-E7]` 更正：v2 原记 12:32:37.458Z，该时刻实为另一段「Cleaned up…」）: «`git worktree remove` failed because the junction (node_modules) inside the worktree...» —— 执行者当时把失败理解为「junction 导致的删除失败」，**没有意识到删除已经部分穿透到真树**。
- 12:32:49.062Z 另一会话 thinking（`...1dab...` L187）: «`packages/coding-agent` now contains only `node_modules`! The `src` directory is GONE.» ⇒ 与 §1.3 的 ENOENT 独立互证。
- `.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md` 于 12:32:06.533Z 落盘（24592 B）、12:32:18.452Z 起被 `read` 复核 —— 这条 `read`（L142 的另一半）在 12:32:24.249Z 之前的批次内成功，说明**报告文件本身无损**（它不在被删路径上）。

---

## 3. AC-006：机制与候选命令排除表

### 3.1 三约束的必要条件分解

| 观测约束 | 本次实测证据 | 必要条件 |
|---|---|---|
| 文件级「消失 + 恢复」 | §1.3 夹逼（14.011 → 29.183）+ §2.1 计数（3456）+ §2.2 mtime 直方图 | **两段**动作：先物理删除（工作树缺文件），后按 index 写回 |
| 未提交改动被丢弃 | §4 的 ack test 一手链（写入 → 两个独立会话回读 → 被覆盖回 HEAD） | 恢复动作必须是**强制覆盖**（丢弃工作树内容），不是 apply/merge |
| HEAD 不变（`10446aefb`）| [VERIFY] `git rev-parse --short HEAD` = `10446aefb`；[VERIFY] `git reflog --date=iso` 最新一条 = `10446aefb HEAD@{2026-10-09 16:30:19 +0800}: commit: docs(agentic): close mw-autopilot-slot-capacity ...` ⇒ **20:2x–20:4x 无任何 ref 变动**；[VERIFY] `.git\refs\stash` 与 `.git\logs\refs\stash` 均**不存在**；[VERIFY] `git fsck --no-progress --no-dangling` → **rc=0、无输出**（对象完好）；[VERIFY] 现 `git ls-files -d` = 0 | 删除与恢复**都不得**移动 ref |

### 3.2 恢复动作的命令原文与时刻（第二段，已坐实）

脚本内容（`write` toolCall L204，**12:36:04.137Z**；`path = C:/Users/wenbozhou/AppData/Local/Temp/mwv14c/restore.sh`）：

```bash
#!/usr/bin/env bash
# RECOVERY: restore the 3456 tracked files deleted from packages/** in the worktree.
# Writes only paths that are currently missing (git checkout -- <deleted paths>).
set -uo pipefail
cd /h/git/Multi-Workers || exit 9
before=$(git ls-files -d | wc -l)
echo "deleted_before=$before"
git ls-files -d -z > /tmp/mwv14c-deleted.list
ls -l /tmp/mwv14c-deleted.list
# batch restore: only the exact deleted paths, never directories
git ls-files -d -z | xargs -0 -r -n 200 git checkout --
rc=$?
echo "checkout_batches_rc=$rc"
after=$(git ls-files -d | wc -l)
echo "deleted_after=$after"
```

- 执行者: session id `01a1208f-d2f3-77c3-a241-d6c43402bece`（worker `mvr-t14-verification-closeout`，key `mw-vision-role`）；执行命令 = `bash restore.sh`（12:36:07.381Z）
- 恢复动作的**类别** = 「**路径级强制 checkout**」：只把「当前缺失（`git ls-files -d`）的 tracked 路径」用 index 内容写回。这正是「无关文件 mtime 不变」（§2.2）与「被删路径上的 diff 被丢弃」（§4）的同一因。
- 12:38:18.363Z 实测 `deleted_before=3456 → deleted_after=0`：恢复**一条不多、一条不少**，恰好是删除段的补集。

### 3.3 候选命令 × 三约束（含排除依据）

| 候选命令 | 能解释「消失 + 恢复 + 丢改动 + HEAD 不变」？ | 本次排除/保留依据 |
|---|---|---|
| **① `git worktree remove --force <worktree 内含指向真树的 junction>`**（删除段） | **能**（解释文件消失 + 8 条链接消失 + `packages/tui` 部分中止） | **保留 ＝ 已坐实**：§1.1–1.5 四证齐（命令原文 / 执行会话 / 精确时刻 / 外部账本 + 唯一性穷举 + 中止指纹）|
| **② `git ls-files -d -z \| xargs -0 -r -n 200 git checkout --`**（恢复段） | **能**（解释恢复 + 这些路径上的 diff 被丢弃 + ref 不动） | **保留 ＝ 已坐实**：§3.2（命令原文 + 执行时刻 + `3456 → 0` 实测）|
| `git checkout <ref>` / `git switch <ref>` | 部分（会改 HEAD） | **排除**：HEAD 未变；reflog 在 20:2x–20:4x **无条目** |
| `git reset --hard <ref ≠ HEAD>` | 部分 | **排除**：同上（移动 ref 必写 reflog）|
| `git checkout-index -a -f` | 能恢复，但会重写**全部** tracked 文件 | **排除**：`README.md`(2026-09-15) / `AGENTS.md`(2026-09-21) / `package.json`(2026-08-05) / `scripts\`(2026-08-05) 等大量无关 tracked 文件 mtime 未变 |
| `git stash` / `stash pop|apply` | 不能（不产生 tracked 文件级消失；且会写 `refs/stash`）| **排除**：`refs/stash`、`logs/refs/stash` 均不存在；窗口内只有 `git stash list`；`git stash list` 输出恒为空 |
| `git clean -fdx` | 不能（只删未跟踪/被忽略文件）| **排除**（对 tracked 文件而言）；本事件亦未观测到配套的未跟踪文件消失 |
| `git read-tree` / `update-index` / `sparse-checkout` | 不能（不动工作树文件）| **排除**：无 sparse 配置；窗口内的 `update-index` 只做 `--refresh` |
| `git worktree remove --force`（目标树内**无** junction）| 不能 | **排除**：同日对照实例 `.tmp-t09-wt`（20:23:34，`REMOVE_EXIT=0`）真树零影响 |
| `git worktree remove --force`（先 `rmdir` 摘链再删）| 不能 | **排除**：同日对照实例 `%TEMP%\mw-t23-wt`（20:25:20，先 `cmd /c rmdir` 再 remove）、`.tmp-t13-wt`（20:27:14，先摘 **2** 条链）均零事故 |
| `git worktree remove --force`（`%TEMP%\qg-head`，未摘链）| **就是本事件** | **保留**（§1.4 判别 + §2.1/§2.3 指纹）|
| 直接递归删真树（PS 5.1 `Remove-Item -Recurse`、`rimraf`、Node `fs.rm`、`robocopy /MIR`）| 能解释删除，但**无已执行实例** | **本事件排除**：① §1.5 穷举为负（窗口内无此类命令作用于真树）；② 不产生 `Invalid argument`/RC=255 中止签名；③ PS `Remove-Item` 对 junction 不穿透（交叉引用，§1.6）。**类级风险保留**（见 §7.2）|
| `npm ci` / 全量重装 | 能删 node_modules，**不能**删 `packages/*/src` | **排除**：196 个 `node_modules` 一级条目保持 `2026-08-10` 原物（§2.3）|
| 20:38:58–20:40:26 的 `npm install` 型 reify | 只解释**链接重建**，不解释删除/恢复 | **保留**为恢复链的第三环（8 条 junction mtime = 20:39:03）|

### 3.4 机制结论（推断成分已标注）

1. **删除段**（20:32:18.452 – 20:32:24.444，本地）：`git worktree remove --force C:\Users\wenbozhou\AppData\Local\Temp\qg-head` 递归删除 worktree；worktree 根下 `node_modules` 是**指回真树**的 junction，git 的递归删除**跟随 reparse point**，因此进入真树 `node_modules`，再沿其中 8 条 `@earendil-works\pi-*` junction 进入真树 `packages\{coding-agent, ai, agent, client, evals, protocol, server, session-backends}` 并清空（3300 个 tracked 文件）；随后进入第 9 条 `pi-tui` 的目标 `packages\tui`，删到 156/236 时撞上不可删句柄，`unlink` 返回 EINVAL，git 放弃并报 `failed to delete '<worktree>': Invalid argument`（RC=255）。⇒ 链接层留下 8 条缺失、`pi-tui` 原物；文件层留下「8 包空 + `packages\tui` 半空」。
   - **属于推断的部分**：「junction 对 git 是普通目录」与「readdir 顺序里 `pi-tui` 最后」两个中间环节，本次**未自行复现**（硬规则禁执行 `worktree remove`）；依据是 §1.6 第 2 层（兄弟 worker 的 `%TEMP%` 最小复现，交叉引用）+ §2.1/§2.3 的形态学一一对应。
2. **恢复段**（20:36:07 – 20:38:18）：路径级强制 checkout 只重写「缺失的 3456 条路径」，内容对齐到 index（= HEAD）。**副作用**：这些路径上任何未提交的工作树改动被静默丢弃（ack test 为已坐实的一例，§4）。HEAD 与 reflog 完全不动（无 ref 级动作）。
3. **链接重建段**（20:38:58 – 20:40:26）：一次 `npm install --ignore-scripts` reify 重建 8 条 junction 与少量 `node_modules` 条目（8 条 junction mtime = 20:39:03），使 IN-1 观测的 `ERR_MODULE_NOT_FOUND` 消失。

---

## 4. AC-007：`agent-team-loop-ack.test.ts` 的两可能性一手证据

**判定：可能性 (a) 坐实 —— 改动确曾被写入磁盘，随后被 §3.2 的恢复动作覆盖回 HEAD。该 `2026-10-09T12:13:31Z` 复验行不是假声明。**
（口径：本节**只**覆盖该文件的这一处改动，不外推到其它 key 的其它复验行。）

### 4.1 (a) 的一手证据链

| # | 时刻（UTC / 本地） | 证据 | 来源 |
|---|---|---|---|
| 1 | 12:09:46.650Z / 20:09:46 | 读该文件，`extensions/agent-team-loop-ack.test.ts:88: console.log(...)` ⇒ 改动前 = `console.log` @L88 | `C:\Users\wenbozhou\.pi\agent\sessions\...12-08-03-472Z_01a12090-3290-7b15-8e94-cd962f30a352.jsonl` L23/L24 |
| 2 | **12:10:02.943Z** / 20:10:02 | `edit` toolCall：`oldText` = `console.log(\`[VERIFY] VC-004: acked=..., persisted=yes\`);`；`newText` = 3 行注释 + `process.stdout.write(\`[VERIFY] VC-004: acked=..., persisted=yes\n\`);` | 同上 **L28** |
| 3 | **12:10:02.951Z** | toolResult = `Successfully replaced 1 block(s) in H:\git\Multi-Workers\packages\coding-agent\test\extensions\agent-team-loop-ack.test.ts.` | 同上 **L29** |
| 4 | 12:10:35.091Z | 同一会话重跑 vitest，stdout 实出 `[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes` | 同上 L31 |
| 5 | **12:10:40.752Z** | **第二个会话**的 grep 输出含 `...agent-team-loop-ack.test.ts-91- process.stdout.write(\`[VERIFY] VC-004: ...\`);` ⇒ 文件当时确有该行，位于**第 91 行** | `C:\Users\wenbozhou\.pi\agent\sessions\...12-09-18-335Z_01a12091-56ff-72b6-8c57-f5fca197a6ba.jsonl` L24 |
| 6 | **12:10:46.843Z** | **第三个会话**的 grep 输出含 `packages\coding-agent\test\extensions\agent-team-loop-ack.test.ts:91: process.stdout.write(\`[VERIFY] VC-004: ...\`);` | `C:\Users\wenbozhou\.pi\agent\sessions\...12-05-57-248Z_01a1208e-4580-7621-a885-cc3802602817.jsonl` L49 |
| 7 | 12:13:35.623Z | 结论写入任务卡：`.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md:55` 的「轮次 2 / 2026-10-09T12:13:31Z」行（卡内**自报**时刻；实际写入时刻 12:13:35.623Z，差 4.6 s） | `...3290...` L42 |
| 8 | 12:32:14 – 12:32:29 | 该文件属于 `packages/coding-agent/test/**` ⇒ 落在被删的 3456 条路径内 | §1.3 / §2.1 |
| 9 | 20:36:07 – 20:38:18 | 恢复脚本把它按 index 写回 ⇒ 内容回到 HEAD 版本 | §3.2 |
| 10 | **12:40:56.066Z** / 20:40:56 | **事后一手复验**：`Select-String -Pattern 'stdout\.write|console\.log'` → 当前文件 `88: console.log(\`[VERIFY] VC-004: ...\`)`，且 `git show HEAD:<file>` 也是 `88: console.log(...)` ⇒ 改动已消失、内容 == HEAD（该会话 thinking 记为 «matches HEAD (no diff) but mtime 20:37:54 (just restored)»）| `C:\Users\wenbozhou\.pi\agent\sessions\...07-58-49-436Z_01a11fac-045c-7902-a23d-5f918187fcb0.jsonl` L330/L331 |
| 11 | [VERIFY] 2026-10-10 11:2x | `git rev-parse HEAD:<file>` = `fe7dddebb6042831880f96fba8170bb137828b63`（HEAD 版本 = `console.log`）；`git hash-object` 工作树 = `e5db403bb21a3766edb761de50e9e74b9c242b0f`（今日 10:59:26 被另一会话再次改成 `verify()` 助手）；`git diff --stat HEAD` = `1 file changed, 7 insertions(+), 1 deletion(-)` | 本次实测（§附录 A）|

⇒ 时间线自洽：**12:10:02 写入（L88 → L91）→ 12:10:40 / 12:10:46 两个独立会话回读证实 → 20:32 随树被删 → 20:37:54（mtime）被路径级 checkout 覆盖回 HEAD**。因此该 12:13:31Z 复验行描述的是**当时真实存在的磁盘状态**，属真声明；「改动消失」的原因是**外部恢复动作覆盖**，**不是** worker 谎报。

### 4.2 可能性 (b) 为何被否证

(b)「该复验行本身是假声明（无任何写入痕迹）」被上表第 2/3/5/6 行**直接否证**：存在执行成功并返回 `Successfully replaced 1 block(s)` 的 `edit` toolCall，且**两个彼此独立**的会话在写入后 38 s / 44 s 各自从磁盘读回了 `process.stdout.write`@L91。

### 4.3 附注（不属于 AC-007，但 PM 需要）

- 项目自己今天的记录已独立收敛到同一结论：`.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md:56`（轮次 3，`2026-10-10T03:03:50Z`）写「复验发现 HEAD 版本埋点回退为 `console.log`（round 2 修正未提交）；重新以 `process.stdout.write` + `verify()` 助手替换」。
- **PM 前置前提之一不成立 → 标为未坐实（`[QG-E10]` 改写）**：mini-spec / spec §1.2 称「`shared/mw-runner.ts` 原有 1 行 diff 现已消失」。**事后确有一手观测**：`01a11fac:323`（12:40:27.142Z，恢复完成 12:38:18 之后约 2 分钟）实测 `git diff --stat HEAD -- …agent-team-loop` = 「`mw-runner.ts | 2 +-`」（1 file changed, 1+/1-），且 `01a11fac:330`（12:40:55.264Z）记录该 diff 已消失（"the 1-line diff I saw earlier disappeared"）——这正是 spec §1.2「1 行 diff 消失」的观测来源。v2 原写「找不到该 diff 存在过的任何一手记录，且现有证据倾向反证」**过强，已撤回**（该消失发生在恢复完成**之后**，不能归因于本次事故的恢复动作）。**事故前（12:17–12:32）窗口内确无观测**，故「未坐实」结论本身仍然成立：
  - [VERIFY] `git rev-parse HEAD:packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts` = `ea3079016b32288cb8e1700dc49435d42f34fd0c`
  - [VERIFY] `git hash-object` 工作树同路径 = **同一个** `ea3079016b32288cb8e1700dc49435d42f34fd0c`
  - [VERIFY] `git diff --stat HEAD -- <该文件>` = **0 行**
  - 同会话在 **12:15:15.411Z** 实测的 worktree blob 也正是 `ea3079016b`（`git hash-object`；`...12-04-08-087Z_01a1208c-9b17-...` L41/L42）⇒ 至少在 12:15:15 与今天，该文件都与 HEAD 逐字节一致。
  - 唯一看起来像「diff」的记录是同一会话 12:16:38 的 `git diff 75298ee4e -- .../shared/mw-runner.ts`（L45/L46），它打出 `index fdd1f5e99..ea3079016 100644` 的 hunk —— 但那是**与旧提交 `75298ee4e` 比较**，**不是工作树 diff**。
  - ⇒ **「mw-runner.ts 有 1 行未提交 diff 且被丢弃」= 未坐实**（12:17–12:32 之间是否短暂存在过 diff，无一手观测；事故后 12:40:27–12:40:55 的 1 行 diff 出现又消失属另一时段，见上）。AC-006 的「未提交改动被丢弃」这一约束由 ack test 一手坐实，**不需要**依赖 mw-runner.ts。

---

## 5. 与上一版 IN-2 报告的差异（本文件为修正版）

上一版（2026-10-09 21:09 落盘的同名文件）有两处结论需要修正：

| 上一版结论 | 本版修正 | 依据 |
|---|---|---|
| AC-005「未坐实；窗口内没有任何 pi 会话执行过能删掉 `packages/**` 的命令」 | **改为坐实**：命令是 `git worktree remove --force "$env:TEMP\qg-head"`（字面删 worktree，**经 junction 穿透到真树**） | §1.1–1.5。上一版的扫描词表只看命令**字面**是否触及 `packages/**`，因此整类「字面删 worktree / 实际穿透到真树」的命令被漏掉 |
| 「`git worktree remove --force` 实测失败（RC=255）⇒ 排除」 | **改为元凶**：RC=255 是**部分删除后中止**，不是「什么都没删」 | §1.4 五条判别 + §2.1 中止指纹；`%TEMP%` 复现（§1.6 第 2 层）逐字复刻同一错误文本与残留形态 |
| AC-007 结论方向 | 维持（(a) 坐实），但补齐第 5/6 条**独立回读**证据与第 10 条**事后**观测（上一版只引用了第 5/6 条中的 1 条）| §4.1 |
| 「恢复动作无法唯一区分是哪一条命令（只能确定类别）」| 本版给出**已执行的恢复命令原文**（`restore.sh` 内的 `git ls-files -d -z \| xargs -0 -r -n 200 git checkout --`）、执行者、时刻与 `3456 → 0` 实测结果 | §3.2 |
| 「受害面 3448，与观测 3456 差 8」| 本版算得**精确等于 3456**（8 包 tracked 求和 3300 + `packages/tui` 实测被删 156），无需「差 8」的口径解释 | §2.1 |

---

## 6. 未坐实清单（不得当结论使用）

1. **删除段中间步骤的自行复现**：本次**未自行执行** `git worktree remove` 做最小复现（硬规则禁止执行该命令）。「junction 对 git 呈现为普通目录」「readdir 顺序里 `pi-tui` 最后」两条中间环节依赖兄弟 worker `inc1-junction-forensics` 的 `%TEMP%` 复现（**交叉引用，非本次实测**）。
2. **触发 `unlink` EINVAL 的具体被占用文件/进程**：未坐实（真树当时哪个句柄造成 EINVAL，无法从只读证据反推）。
3. **`packages/tui` 为何只删 156/236、`src`/`test` 完好**：只有「中止发生在 `pi-tui` 子树内」这一形态学结论 + 推断；**具体中止点与顺序未坐实**。
4. **`mw-runner.ts` 的「1 行 diff 被丢弃」**：**未坐实**（事故前 12:17–12:32 窗口无观测；`[QG-E10]` 更正——撤回「倾向反证」，恢复完成后 12:40:27Z 确曾观测到 1 行 diff、12:40:55Z 消失，见 §4.3）。
5. **20:38:58–20:40:26 的 npm reify 由谁触发**：本报告原先标「未坐实」的此项**已由独立 QG 一手闭环（`[QG-E6]`）**，本文件 PM 亦已复核：PM 会话 `01a0d325` 在 **12:38:58.496Z** 的 toolCall 执行 `npm install --ignore-scripts`（L2926），toolResult 在 **12:39:10.147Z** 显示 8 条 `pi-*` junction 重建完成、`gondolin` 齐全、lockfile/shrinkwrap 零改动（L2927）；该会话自述亦承认「These 20:41 logs are MY `npm install --ignore-scripts`」（L2943）。
6. **恢复段是否存在第二个执行者**：本报告只找到一处恢复执行（`restore.sh`）。若在 12:38:18–12:40:56 之间还有别的恢复动作，本次未发现证据。
7. **`3531 − 3456 = 75` 的构成**：只有算术关系与「12:38:26 实测 `total modified: 74`」的旁证，未逐条清点。
8. **事故当下的 20:3x 是否存在 ref 级动作被 reflog 之外的机制抹掉**：未坐实；本报告只能给出 `reflog` 无条目、`refs/stash` 不存在、`git fsck` rc=0 三条。
9. **IN-2 与 IN-1 的同源性**：本报告给出「同一条命令、同一事件」的机器证据（8 ↔ 8 junction 对应、20:32:18–24 同一窗口、`pi-tui` 中止点、`packages/tui` 半删），但**最终同源判定留给 PM**（spec AC-008）。
10. **「12:13:31Z」这一时刻本身**：任务卡里是**自报**值，实际卡内写入时刻为 12:13:35.623Z（§4.1 第 7 行）。复验内容真实，但卡上时刻不是记录时刻。

---

## 7. 建议（只建议，不在本 key 实施）

1. **工具/框架层拦截**：`git worktree remove` 的目标子树内存在 reparse point（junction/symlink）时，执行前 block，并指向唯一正规命令（先逐条 `rmdir` 摘链，再 remove）。这与 PM 的 G1/G2 一致；IN-2 侧新增的事实是「**删除段**的元凶就是这条命令」，而不是恢复段。
2. **「路径级强制 checkout」必须留痕**：`git checkout -- <paths>` / `git restore` / 同 ref `reset --hard` 在共享树上等价于「静默丢弃他人未提交改动」。本次恢复**本身是善意的抢救**，却在无人知晓的情况下把 3,456 条路径上的改动对齐回了 HEAD。建议：这类动作前把 `git ls-files -d` 命中的路径**及其丢弃前内容**（或 `git stash create` 的悬挂提交）落档，并在 `.mw` 审计日志登记「谁 / 何时 / 用哪条命令 / 覆盖了哪些路径」。
3. **给突变加机器判据（本次全程零告警）**：worker 启动与收尾各采一次 `git ls-files` 计数、`git ls-files -d` 计数、`node_modules\@earendil-works` 的 reparse point 数；任一突变超阈值即拒跑/告警。本次「3,456 个文件消失 3.5 min + 2.2 min 才恢复」不会被任何现有判据发现。
4. **口径卫生**：`git worktree list` / `node_modules` 一级条目计数 / tracked 文件 mtime 直方图在**多 key 并发**环境下会分钟级漂移（本报告两次测量即出现 2537→2512、34→25）。取证结论应绑定「测量时刻 + 命令」，不要写成无量化的绝对断言。

---

## 附录 A：[VERIFY] 本次实测输出（2026-10-10 11:00–11:25 UTC+8）

```
[VERIFY] incident_cmd_ts=2026-10-09T12:32:18.452Z local=2026-10-09 20:32:18.452 src=...12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl:142
[VERIFY] incident_cmd_text=cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" 2>&1 | Out-String; "RC=$LASTEXITCODE"; git worktree list | Out-String
[VERIFY] incident_result_ts=2026-10-09T12:32:24.444Z rc=255 err="failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument"
[VERIFY] junction_cmd_ts=2026-10-09T12:21:48.660Z src=same:L60 mklink_target="H:\git\Multi-Workers\node_modules" in_worktree="%TEMP%\qg-head"
[VERIFY] cleanup_cmd_ts=2026-10-09T12:32:28.112Z src=same:L145 cmd="cmd /c rmdir \"$t\node_modules\"; Remove-Item -Recurse -Force $t" result_still_exists=False
[VERIFY] deletion_window=2026-10-09T12:32:14.011Z..12:32:29.183Z local=20:32:14.011..20:32:29.183
[VERIFY] tree_intact_ts=2026-10-09T12:32:14.011Z git_status_porcelain_D_count=0 src=...e335....jsonl:141
[VERIFY] tree_missing_ts=2026-10-09T12:32:29.183Z ENOENT="packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts" src=...12-09-03-659Z_01a12091-1dab-7314-82c5-71734d2a761d.jsonl:179
[VERIFY] porcelain_total=3531 D_count=3456 ts=2026-10-09T12:36:09.236Z src=...12-02-43-303Z_01a1208b-4fe7-720f-8c04-88c2447dfbdb.jsonl:118
[VERIFY] ls_files_d_before_recovery=3456 ts=2026-10-09T12:35:46.314Z src=...12-07-38-995Z_01a1208f-d2f3-77c3-a241-d6c43402bece.jsonl:201
[VERIFY] recovery_cmd="git ls-files -d -z | xargs -0 -r -n 200 git checkout --" script_ts=2026-10-09T12:36:04.137Z exec_ts=2026-10-09T12:36:07.381Z src=same:L204/L206
[VERIFY] recovery_result="deleted_before=3456 / checkout_batches_rc=0 / deleted_after=0" ts=2026-10-09T12:38:18.363Z src=same:L207
[VERIFY] recovery_recheck="--- deleted now --- 0 ; total modified: 74" ts=2026-10-09T12:38:26.354Z src=same:L208/L209
[VERIFY] ack_edit_ts=2026-10-09T12:10:02.943Z old="console.log(`[VERIFY] VC-004: ...`)" new="process.stdout.write(`[VERIFY] VC-004: ...\n`)" src=...12-08-03-472Z_01a12090-3290-7b15-8e94-cd962f30a352.jsonl:28
[VERIFY] ack_edit_result_ts=2026-10-09T12:10:02.951Z text="Successfully replaced 1 block(s) in ...agent-team-loop-ack.test.ts." src=same:L29
[VERIFY] ack_readback_1_ts=2026-10-09T12:10:40.752Z line=91 "process.stdout.write(`[VERIFY] VC-004: ...`)" src=...12-09-18-335Z_01a12091-56ff-72b6-8c57-f5fca197a6ba.jsonl:24
[VERIFY] ack_readback_2_ts=2026-10-09T12:10:46.843Z line=91 "process.stdout.write(`[VERIFY] VC-004: ...`)" src=...12-05-57-248Z_01a1208e-4580-7621-a885-cc3802602817.jsonl:49
[VERIFY] ack_post_recovery_ts=2026-10-09T12:40:56.066Z current_line88="console.log(`[VERIFY] VC-004: ...`)" head_line88="console.log(`[VERIFY] VC-004: ...`)" src=...07-58-49-436Z_01a11fac-045c-7902-a23d-5f918187fcb0.jsonl:331
[VERIFY] tracked_total=4590
[VERIFY] tracked_by_package={"agent":226,"ai":1060,"client":63,"coding-agent":1683,"evals":19,"multi-workers":200,"protocol":49,"server":99,"session-backends":101,"tui":236}
[VERIFY] eight_package_tracked_sum=3300 ; tui_deleted_subset=156 ; 3300+156=3456 == D_count
[VERIFY] tui_breakdown: dist=148 all-deleted(mtime 2026-10-09 20:38) ; src=37 untouched ; test=36 untouched ; native=10 (7 deleted/3 kept) ; root-files=5 (1 deleted/4 kept)
[VERIFY] earendil_entries=10 total => 9 junctions + 1 real dir(gondolin)
[VERIFY] earendil_recreated_ts=2026-10-09 20:39:03 (8 junctions) ; kept=pi-tui mtime=2026-08-10 18:09:09
[VERIFY] node_modules_entry_mtime_days={"2026-08-10":196,"2026-10-09":25,"2026-10-10":1}   (11:1x 那次为 196/34/1)
[VERIFY] mtime_20261009_minutes={"20:36":1202,"20:37":833,"20:38":457} ; 20:xx_total=2512 (11:1x 那次 2537)
[VERIFY] mtime_20261010_total=1048 其中 packages/coding-agent/dist=953
[VERIFY] untouched_mtimes=README.md 2026-09-15 21:22:16 / AGENTS.md 2026-09-21 23:22:30 / package.json 2026-08-05 18:02:55 / scripts\ 2026-08-05 18:02:56
[VERIFY] HEAD=10446aefb
[VERIFY] reflog_top1="10446aefb HEAD@{2026-10-09 16:30:19 +0800}: commit: docs(agentic): close mw-autopilot-slot-capacity with its gold-gate evidence and leftovers"
[VERIFY] refs_stash_exists=False ; refs_logs_stash_exists=False
[VERIFY] git_fsck="rc=0 out='' err=''"
[VERIFY] ls_files_d_now=0 ; git_status_porcelain_now={ M:106, ??:30, D:0 }
[VERIFY] ack_HEAD_blob=fe7dddebb6042831880f96fba8170bb137828b63 ; ack_WT_blob=e5db403bb21a3766edb761de50e9e74b9c242b0f ; ack_diff="1 file changed, 7 insertions(+), 1 deletion(-)"
[VERIFY] mw_runner_HEAD_blob=ea3079016b32288cb8e1700dc49435d42f34fd0c ; mw_runner_WT_blob=ea3079016b32288cb8e1700dc49435d42f34fd0c ; mw_runner_diff_lines=0 ; mw_runner_WT_blob_2026-10-09T12-15-15Z=ea3079016b
[VERIFY] e335_trace_log_L467="[TOOL] 2026-10-09T12:32:18.454Z bash cd H:/git/Multi-Workers; git worktree remove --force \"$env:TEMP\qg-head\" ..."
```

**注**：上表由一份 python 只读脚本生成（`git ls-files / rev-parse / hash-object / reflog / worktree list / fsck / diff --stat` + `os.stat`），运行在 2026-10-10 11:00–11:25；因并行会话在改文件，重复运行会有量级相同的漂移（已在上表标注两处）。所有 `[VERIFY]` 行的数值均是**打印出来的**，不是推算。

---

## 附录 B：来源 jsonl 索引（均在 `C:\Users\wenbozhou\.pi\agent\sessions` 下）

| 文件 | slug | 关键行 |
|---|---|---|
| `2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` | `--H--git-Multi-Workers--` | **L60**（建 worktree + `mklink` junction）、L138/L139（报告落盘）、L140/L141（12:32:14.011Z `0 条 D`）、**L142/L144（元凶命令 + RC=255）**、L145/L146（善后）、L147–L149（worker_file/收尾）|
| `2026-10-09T12-09-03-659Z_01a12091-1dab-7314-82c5-71734d2a761d.jsonl` | `--H--git-Multi-Workers--` | L175/L176（12:32:24.249Z 4 个哈希）、**L178/L179（12:32:29.183Z ENOENT）**、L181/L182（PathNotFound + rg os error 2）、L187/L188（3531）、L192（packages 清单）|
| `2026-10-09T12-07-38-995Z_01a1208f-d2f3-77c3-a241-d6c43402bece.jsonl` | `--H--git-Multi-Workers--` | L200/L201（`git ls-files -d` = 3456）、**L204（恢复脚本源文）**、**L206/L207（执行 + 3456→0）**、L208/L209（复验 0 / modified 74）、L246（事件记录写入）|
| `2026-10-09T12-02-43-303Z_01a1208b-4fe7-720f-8c04-88c2447dfbdb.jsonl` | `--H--git-Multi-Workers--` | L117/L118（`TOTAL=3531` / `D=3456`）|
| `2026-10-09T12-03-36-535Z_01a1208c-1fd7-7343-b9e4-4429b50597b3.jsonl` | `--H--git-Multi-Workers--` | L107、L120（` D packages/coding-agent/src/**` 批量列表）|
| `2026-10-09T12-08-03-472Z_01a12090-3290-7b15-8e94-cd962f30a352.jsonl` | `--H--git-Multi-Workers--` | L23/L24（改动前 `console.log`@88）、**L28/L29（edit + 成功结果）**、L31（重跑 stdout 实出）、L42（写任务卡）、L45/L48（收尾）|
| `2026-10-09T12-09-18-335Z_01a12091-56ff-72b6-8c57-f5fca197a6ba.jsonl` | `--H--git-Multi-Workers--` | **L24（回读 `process.stdout.write`@91）** |
| `2026-10-09T12-05-57-248Z_01a1208e-4580-7621-a885-cc3802602817.jsonl` | `--H--git-Multi-Workers--` | **L49（第二个独立回读 @91）** |
| `2026-10-09T07-58-49-436Z_01a11fac-045c-7902-a23d-5f918187fcb0.jsonl` | `--H--git-Multi-Workers--` | **L330/L331（12:40:56 事后复验：当前 == HEAD == console.log@88）**、L324–L327（恢复过程观测）|
| `2026-10-09T12-04-08-087Z_01a1208c-9b17-77f1-81e0-7fd4c128e085.jsonl` | `--H--git-Multi-Workers--` | L41/L42（12:15:15 实测 `mw-runner.ts` WT blob = `ea3079016b`）、L45/L46（12:16:38 `git diff 75298ee4e` —— **与旧提交比较**，非工作树 diff）|
| `.agenticdoc\mw-vision-role\workers\mvr-t16-quality-gate-review\trace.log` | — | **L467（12:32:18.454Z 同一命令的独立账本）**、`[START]`/`[END]` 与 `pid=159560` |
| `.agenticdoc\mw-widget-terminal-lifecycle\tasks\T-01-ack-store.md` | — | L55（轮次 2 / 2026-10-09T12:13:31Z 复验行）、**L56（轮次 3 / 2026-10-10T03:03:50Z 项目自证同一结论）** |
| `.agenticdoc\mw-widget-terminal-lifecycle\workers\wtl-t01-ack-store\output.md` | — | L109/L110（今天重派 worker 的独立判断）|

---

## 附录 C：只读合规声明与复算配方

**合规声明**

- 未执行 `checkout` / `reset` / `stash` / `clean` / `worktree add|remove|prune` / `rm`；未建、未删任何 worktree；未改仓库任何文件（唯一写入 = 本文件）。
- 本次用到的全部命令：`git ls-files [-d|-z]` / `git rev-parse` / `git hash-object` / `git reflog --date=iso` / `git log` / `git show HEAD:<path>` / `git worktree list` / `git fsck --no-progress --no-dangling` / `git status --porcelain` / `git diff --stat` / `Get-Item` / `Get-FileHash` / `Select-String` / `Test-Path`，以及 python 只读解析与统计。
- 机制复现（`git worktree remove` 跟随 junction 等）**未在本 worker 内执行**，属对兄弟 worker `inc1-junction-forensics` 的**交叉引用**（其复现在 `%TEMP%\jrepro*`、真树零触碰）。
- 会话日志解析只取**已执行的 toolCall 参数与 toolResult 文本**，模型思考/讨论文本仅用于「动机」等**明确标注为非执行证据**的段落。

**复算配方（可重复）**

1. 取 `C:\Users\wenbozhou\.pi\agent\sessions` 下**全部** `*.jsonl`（不按文件名日期过滤），逐行 `json.loads`；筛 `message.role in {assistant, toolResult}`，对 assistant 取 `content[].type == "toolCall"` 的 arguments，对 toolResult 取 `content[].text`。
2. 时间窗二连查：`12:32:15Z–12:32:40Z`（全量命令列表）与 `12:20:00Z–12:46:00Z`（破坏性动词表命中）；比对命令文本是否触及 `node_modules` / `packages/**` / worktree 路径。
3. 树侧指纹：`git ls-files` + `os.stat().st_mtime` 做分钟直方图，按包分组；`node_modules\@earendil-works` 逐条目 `lstat`（`st_file_attributes & 0x400` = reparse point）取 mtime。
4. 干净度：`git rev-parse --short HEAD` + `git reflog --date=iso` + `Test-Path .git\refs\stash` + `git fsck --no-progress --no-dangling` + `git ls-files -d`。
5. AC-007：`git rev-parse HEAD:<file>` 与 `git hash-object -- <file>` 比对，再看 12:40:56 的 `Select-String` 复验输出。

（报告结束）