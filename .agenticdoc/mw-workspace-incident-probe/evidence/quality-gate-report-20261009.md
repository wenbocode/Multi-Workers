# QG 独立复核报告 — mw-workspace-incident-probe（2026-10-09 双事故取证）

- 复核人：`wip-qg-review`（独立质量门，type: review，只读）
- 复核时刻：2026-10-12T08:05Z 起的本会话（run `wip-qg-review@2026-10-12T08:05:56.813Z`）
- 被核验对象：`spec.md`（AC-001..AC-008）、`achieved.md`、`evidence/in1-junction-incident-20261009.md`、`evidence/in2-file-vanish-incident-20261009.md`、`evidence/incidents-timeline-20261009.md`、`evidence/research/spec-incident-probe-plan-20261009.md`
- 方法：**不采信被审文档的转述**，全部结论回到一手证据——(a) 会话 jsonl 原始行的直接读取（toolCall `arguments.command` / toolResult 原文）；(b) 当前文件树与 `.git/**` 的直接列举、读取与计数；(c) 算术复核。
- **工具面限制（诚实声明）**：本 worker 只有 `read/find/grep/ls/worker_file`，**无 shell**。凡需执行命令才能复测的项（mtime 直方图、junction LinkType 逐条、`%TEMP%` 复现、`git fsck`、`npm config get logs-max`、IN-1 的「窗口内 70 条 toolCall」计数）一律标 **[未复测-无shell]**，不以推测补洞；这些项仅做「与一手会话记录互证」级别的核验。
- 落位说明：任务指定唯一写面为 `evidence/quality-gate-report-20261009.md`，但本 worker 无任意路径写工具；本报告落盘于 `workers/wip-qg-review/report-quality-gate-report-20261009.md`，**需 PM 复制到指定路径**。另：上一轮（2026-10-10T09:19Z run，pid 149060）曾交付同名报告，现该文件在目录列举中可见但**不可读（悬空条目，内容已丢失）**；本报告为全量独立重核，非对该轮结论的沿用。

会话文件缩写（均位于 `C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\`）：
`e335` = `2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl`；`1dab` = `...12-09-03-659Z_01a12091-1dab-7314-82c5-71734d2a761d.jsonl`；`d2f3` = `...12-07-38-995Z_01a1208f-d2f3-77c3-a241-d6c43402bece.jsonl`；`4fe7` = `...12-02-43-303Z_01a1208b-4fe7-720f-8c04-88c2447dfbdb.jsonl`；`3290` = `...12-08-03-472Z_01a12090-3290-7b15-8e94-cd962f30a352.jsonl`；`56ff` = `...12-09-18-335Z_01a12091-56ff-72b6-8c57-f5fca197a6ba.jsonl`；`4580` = `...12-05-57-248Z_01a1208e-4580-7621-a885-cc3802602817.jsonl`；`01a11fac` = `2026-10-09T07-58-49-436Z_01a11fac-045c-7902-a23d-5f918187fcb0.jsonl`；`9b17` = `...12-04-08-087Z_01a1208c-9b17-77f1-81e0-7fd4c128e085.jsonl`；`01a0d325` = `2026-09-24T11-21-05-539Z_01a0d325-cf03-7a55-b4c7-b93911508f57.jsonl`；`01a080f3` = `2026-09-08T12-16-45-828Z_01a080f3-0704-77dc-aaf8-29e1e16b4e29.jsonl`。

## 1. [VERIFY] 实测汇总（本 QG 一手）

```
[VERIFY] culprit_cmd: e335:142 ts=2026-10-09T12:32:18.452Z toolCall_id=call_01_HaTl69XPpjBFS4aVfVkL2723 name=bash
  命令原文（逐字）: cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" 2>&1 | Out-String; "RC=$LASTEXITCODE"; git worktree list | Out-String
  该行含 2 个 toolCall（read qg-review-…md + bash）——与 IN-1/IN-2 表述一致
[VERIFY] culprit_result: e335:144 ts=2026-10-09T12:32:24.444Z rc=255
  stderr 原文: git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument
  尾部: RC=255 / H:/git/Multi-Workers 10446aefb [dev/AgentTeam]（worktree 注册已消失、目录残留）
  耗时 = 24.444-18.452 = 5.992s（IN-1 记 5.99s ✓）
[VERIFY] junction_create: e335:60 ts=12:21:48.660Z（含 if(Test-Path) 守卫分支，当时 $t 不存在故未执行）
  result e335:61 ts=12:23:10.095Z: "Updating files: 100% (4590/4590)" + RC=0 + mklink 回显(qg-head\node_modules <<===>> H:\git\Multi-Workers\node_modules) + True；worktree add 耗时 81.4s
[VERIFY] cleanup: e335:145 ts=12:32:28.112Z（先 cmd /c rmdir "$t\node_modules" 再 Remove-Item -Recurse -Force）；
  result e335:146 ts=12:32:33.062Z still_exists=False
[VERIFY] e335 文件 = 149 个内容行（:150 为空尾行）；:1 session 头 id=01a1208f-e335-767d-a127-bf295f75a861 cwd=H:\git\Multi-Workers ts=2026-10-09T12:07:43.157Z
[VERIFY] 事故前树完好: e335:141 ts=12:32:14.011Z 范围限定 git status 输出 = 2 条 M（review 报告 + rag/adapter.ts）、0 条 D
[VERIFY] 事故后树破损: 1dab:179 ts=12:32:29.183Z read pm-orchestrator.ts → ENOENT；1dab:182 ts=12:32:33.691Z 列 pm\ 目录 PathNotFound + rg os error 2
  ⇒ 删除夹逼区间 = [12:32:14.011Z, 12:32:29.183Z]，元凶命令执行窗 100% 落在其中
[VERIFY] D 计数双源: d2f3:201 ts=12:35:46.314Z `git ls-files -d` = 3456；4fe7:118 ts=12:36:09.236Z porcelain TOTAL=3531 / D=3456；1dab:188 ts=12:32:54.960Z `git status --short` 计 3531
[VERIFY] 包级损坏面(12:36:09.236Z 实测原文): agent=0 ai=0 client=0 coding-agent=1(仅 node_modules) evals=0 protocol=0 server=0 tui=7 multi-workers=89
[VERIFY] 恢复链: d2f3:204 ts=12:36:04.137Z write restore.sh（脚本原文逐字核对，核心行 = git ls-files -d -z | xargs -0 -r -n 200 git checkout --）；
  d2f3:206 ts=12:36:07.381Z 执行；d2f3:207 ts=12:38:18.363Z deleted_before=3456 / checkout_batches_rc=0 / deleted_after=0；
  d2f3:209 ts=12:38:26.354Z deleted=0 / total modified=74；d2f3:208 thinking 原文承认 "the concurrent session's in-flight edits in those files ARE lost"
[VERIFY] 链接层损坏面: 01a0d325:2925 ts=12:38:50.917Z 根 node_modules\@earendil-works 仅剩 1 条 Junction（pi-tui → packages\tui）
[VERIFY] npm 恢复归属: 01a0d325:2926 ts=12:38:58.496Z PM 会话执行 `npm install --ignore-scripts`；01a0d325:2927 ts=12:39:10.147Z
  重建后 9 条 Junction + gondolin 齐全；node_modules LastWriteTime = 2026/10/9 20:32:22；lockfile git status 为空
[VERIFY] AC-007 链（全部一手）: 3290:24 ts=12:09:46.650Z grep 显示 ack.test.ts:88 = console.log；
  3290:28 ts=12:10:02.943Z edit toolCall（oldText=console.log 行 / newText=3 行注释+process.stdout.write）；
  3290:29 ts=12:10:02.951Z "Successfully replaced 1 block(s)"（附 diff：L88 → L88-91）；
  3290:31 ts=12:10:35.091Z vitest 5/5 绿且 stdout 实出 "[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes"；
  56ff:24 ts=12:10:40.752Z 独立会话 grep 回读 …ack.test.ts-91- process.stdout.write(…VC-004…)；
  4580:49 ts=12:10:46.843Z 第二个独立会话回读 ack.test.ts:91: process.stdout.write(…)；
  3290:42 ts=12:13:35.623Z 任务卡轮次2写入（卡内自报时刻 12:13:31Z，差 4.6s）；
  01a11fac:331 ts=12:40:56.066Z 事后复验：当前文件与 HEAD 均为 88: console.log
[VERIFY] mw-runner.ts: 9b17:42 ts=12:15:15.411Z WT blob = ea3079016b == HEAD blob ea3079016b32288cb8e1700dc49435d42f34fd0c；
  9b17:46 ts=12:17:01.849Z 的 git diff 75298ee4e 系与旧提交比较（非工作树 diff）；
  但 01a11fac:323 ts=12:40:27.142Z（恢复完成后 2 分钟）实测 git diff --stat HEAD -- …agent-team-loop = "mw-runner.ts | 2 +-"（1 file changed, 1+/1-），
  至 01a11fac:330 ts=12:40:55.264Z 已无 diff（"the 1-line diff I saw earlier disappeared"）
[VERIFY] reflog: .git/logs/HEAD:118 = 10446aefb @1791534619+0800（=2026-10-09 16:30:19 +0800，"close mw-autopilot-slot-capacity"）；
  :119 = 下一条 @1791615990+0800（=2026-10-10 15:06:30 +0800）⇒ 事故窗口（10-09 20:32–20:40 本地）内零 ref 变动
[VERIFY] stash 缺席: .git/refs 仅 heads/remotes/tags；.git/logs/refs 仅 heads/remotes（无 refs/stash、无 logs/refs/stash）
[VERIFY] 当前 HEAD = 6c518983…（dev/AgentTeam，已前移——树为活体）；.git/worktrees 目录不存在（10-10 11:09 时的 5 个 worktree 已全部清理，状态漂移与 IN-1 的"活树"警告一致）
[VERIFY] node_modules\@earendil-works 现有 10 个条目 = gondolin + pi-agent-core/pi-ai/pi-client/pi-coding-agent/pi-evals/pi-protocol/pi-server/pi-session-backend-sqlite-node/pi-tui
[VERIFY] npm-cache\_logs 现存 11 个文件、全部 2026-10-12T04:23–07:13Z（无 10-09/10-10 残留 ⇒ 滚动清理实证；与 achieved.md §3② 的撤回一致）
[VERIFY] 包文件计数（QG find 实数，与 IN-2 tracked_by_package 逐一相符）: evals=19、protocol=49、client=63、tui=236（dist=148 / src=37 / test=36 / native=10 / 根文件=5，五分项全对）
[VERIFY] 算术: 226+1060+63+1683+19+49+99+101=3300；3300+156=3456 == D 计数（双源）；3531−3456=75（旁证 12:38:26 实测 total modified=74）；worktree checkout 总数 4590（e335:61 原文）== IN-2 tracked_total
[VERIFY] trace.log（mvr-t16）: :229 "[START] pid=159560" 紧邻 :230 "[START] 2026-10-09T12:07:43.239Z task=mvr-t16-quality-gate-review type=research"；
  :467 "[TOOL] 2026-10-09T12:32:18.454Z bash cd H:/git/Multi-Workers; git worktree remove --force …"（与 jsonl toolCall 早 2ms）；
  :473 "[END] 2026-10-10…T12:32:43.510Z exit=0 elapsed=1500s tools=88"（12:07:43.239→12:32:43.510 = 1500.27s ✓）
[VERIFY] AC-004 清点抽核: 01a1208a-970a:107 ts=12:25:20.949Z mw-t23-wt 清理 = 先 `cmd /c rmdir "$wt\node_modules"` 再 `git worktree remove --force` + prune（thinking 原文 "remove the junction first"）；
  bf0c:107 ts=12:27:14.975Z .tmp-t13-wt 清理 = 先 rmdir 两条 junction 再 `git worktree remove`；
  01a1208f-7449:82 ts=12:23:34.229Z `git worktree remove --force .tmp-t09-wt`（无 rmdir——与"该会话未建 junction"一致）；
  01a0dcd2:878 ts=2026-10-09T03:10:32.902Z mwvis-head 清理（会话与时刻与清点吻合；命令全文因行截断未逐字展开）
[VERIFY] 元凶唯一性（QG 佐证口径）: 对全部会话 jsonl grep 执行态（toolCall 形态）的 `git worktree remove --force`：12:31:40–12:33:15Z 窗口内仅 e335:142 一条；同日其余命中均在窗口外（mw-t23-wt 12:25:20 / .tmp-t09-wt 12:23:34 / mwvis-head 03:10:32）。注：QG 的 grep 只覆盖 worktree-remove 家族，完整动词表穷举仍以 IN-2 v2 §1.5 为准（QG [未复测-无shell]）
[VERIFY] claim_id: _index.parallel:46 = "mw-vision-role | idle | DONE | WENBOZHOU-PC4:8152"（pm-state.md 现无此行）
[VERIFY] _workers.parallel:278 mvr-t16 行现为 2026-10-12T08:05:51.127Z 重派（10-09 派发行不可复原——与 IN-1 未坐实#1 一致且漂移更远）
[VERIFY] ack.test.ts 现状: :98 = verify(`[VERIFY] VC-004: …`)（10-10 15:29+0800 提交 1a214416 "fix(coding-agent): write the ack [VERIFY] marker straight to stdout" 已落地——见 .git/logs/HEAD）
[VERIFY] 2026-09-09 同机制先例: 01a080f3:539 ts=2026-09-09T09:43:19.740Z thinking 记 "failed to delete: Invalid argument"；
  01a080f3:541 ts=2026-09-09T09:44:18.454Z thinking "**DISASTER**. The `git worktree remove --force` DID delete through the junctions and beyond"；
  :543 记 "~1100+ deleted tracked files across packages/agent, ai, coding-agent"、"multi-workers SURVIVED — the junction chain didn't reach it"
[VERIFY] "98 条变更"：六份被审文档与 .agenticdoc 全树均无此字样——未找到
```

[未复测-无shell]（不以推测补洞）：mtime 直方图（IN-2 的 2512/1202/833/457、tui 80+156 新旧分布、junction 逐条 mtime、node_modules 一级条目 196/25/1）、IN-1 repro A/B 与 6 组工具对照的实际执行、IN-1「窗口内 70 条 bash toolCall」计数、`npm config get logs-max`、`git fsck`。这些项与一手会话记录互证均无矛盾。

## 2. 逐 AC 判定

| AC | 判定 | 依据（本 QG 一手） |
|---|---|---|
| **AC-001** | ✅ | 元凶命令原文、toolCall id、发出/返回时刻、L142/L144 行号、`failed to delete '…qg-head': Invalid argument`/RC=255、5.99s——**全部逐字复核成立**。前置 L60/L61（junction 建立时刻 12:21:48.660Z、mklink 回显、4590/4590、81.4s）与善后 L145/L146（still_exists=False）同样成立。文件 149 内容行无误。 |
| **AC-002** | ✅（引证源 1 处错） | session id/cwd slug（e335:1）、worker `mvr-t16-quality-gate-review`（type: research，e335:6 任务书原文 + trace.log:230 + worker 目录 task.md/progress.md/trace.log 齐备）、key `mw-vision-role`、trace.log 三段账本（:229/:230/:467/:473，elapsed=1500s ✓）、**pid=159560 坐实**（trace.log:229 `[START] pid=159560` 紧邻 12:07:43 START——IN-2 正确，IN-1 的"无法复核"过度保守）。错误：Claim-Id 引证源写 pm-state.md，实际在 `_index.parallel:46`（见 E8）。 |
| **AC-003** | ✅（机制一手；复现未重跑） | 形态学指纹一手成立：8 包 entries=0 + tui=7 + multi-workers=89（4fe7:118）⇔ @earendil-works 仅剩 pi-tui（01a0d325:2925）⇔ 8 条 junction 目标集合与重建清单一一对应（01a0d325:2927）。repro B 的错误文本与线上**同构**（`failed to delete '<wt>': Invalid argument` + rc=255 + worktree/最后一条链接残留 + 目标部分删除）。**2026-09-09 先例**（01a080f3:539/:541）独立佐证 "git worktree remove --force 穿 junction" 语义。repro A/B 与 6 组对照 QG [未复测-无shell]；无任何相反证据。 |
| **AC-004** | ✅（7 行中 5 行一手复核） | #2 mw-t23-wt（970a:107 先摘链再删，时刻 12:25:20.949Z）、#4 .tmp-t13-wt（bf0c:107 先 rmdir 两条链再删，12:27:14.975Z）、#3 .tmp-t09-wt（7449:82 12:23:34.229Z）、#5 qg-head（e335:60/142/145）逐字成立；#1 mwvis-head（01a0dcd2:878 @03:10:32.902Z）会话+时刻吻合。#6 mwvg-t5-probe 清理者与 #7 `.tmp/t13-worktree` 缺席未复核。当前 .git/worktrees 不存在（后续漂移，与报告自带的"活树"警告一致）。 |
| **AC-005** | ✅（IN-2 v2 坐实成立） | 与 IN-1 同一条命令：夹逼区间 [12:32:14.011Z, 12:32:29.183Z] 一手；D=3456 双源；执行者/会话/时刻全链一手。**v1 的"未坐实"确系扫描范围不足**（词表只匹配字面触及 `packages/**` 的命令，整类"字面删 worktree、实际穿链进真树"被漏掉）——v2 §5 已诚实披露并修正；但 timeline §5 / achieved.md 遗留仍残留 v1 的"穷举为负 ⇒ pi 之外"（见 E4，错误）。 |
| **AC-006** | ✅ | 三约束全部一手独立成立：(1) 文件级消失+恢复 = 3456→0（d2f3:204/206/207）；(2) 未提交改动被丢弃 = restore.sh 只把 `git ls-files -d` 的缺失路径按 index 写回（脚本原文一手）+ 执行者自认 "in-flight edits ARE lost"（d2f3:208）+ AC-007 具体实例；(3) HEAD 不变 = reflog 10-09T08:30:19Z → 10-10T07:06:30Z 零条目（.git/logs/HEAD:118-119）+ refs/stash 与 logs/refs/stash 均不存在。候选排除表推理成立（ref 级操作被 reflog 间隙直接排除）。npm reify 第三环归属（PM 会话 01a0d325:2926）已由 QG 一手坐实——IN-2 标"未独立复核"的项现已闭环。 |
| **AC-007** | ✅ | **可能性 (a) 坐实：改动确曾写入后被丢弃，12:13:31Z 复验行不是假声明**。8 环一手链（写入 toolCall+成功结果+重跑 stdout+两个独立会话回读@L91+任务卡+事后复验==HEAD）见 §1。IN-2 §4.3 对 mw-runner.ts 的"没有任何一手记录"表述过强（见 E10），但不影响本 AC 判定。 |
| **AC-008** | ⚠️ | 同源判定本身**成立且经 QG 独立复核**（见 §3.2）；G1..G4 建议齐备；但作为交付物一部分的 timeline §5 / achieved.md 遗留的**未坐实清单已过时且含一条错误**（3 项已被 v2 坐实仍列为未解；"穷举为负 ⇒ pi 之外"与坐实结论自相矛盾）——合并层未吸收 v2 修正（见 E1–E6）。 |

## 3. 任务书六项独立复核点

### 3.1 元凶命令是否真是 `git worktree remove --force "$env:TEMP\qg-head"`（L142/L144 是否准确）
**是，逐字准确。** e335:142（12:32:18.452Z，bash toolCall `call_01_HaTl69XPpjBFS4aVfVkL2723`，该行含 read+bash 两个 toolCall）与 e335:144（12:32:24.444Z，`git : error: failed to delete 'C:/Users/wenbozhou/AppData/Local/Temp/qg-head': Invalid argument` / RC=255 / worktree list 仅主树）均与被审文档引用一致。窗口内无第二条执行态的 worktree-remove（QG 全会话库 grep 佐证）。

### 3.2 同源判定（三点是否独立成立；"另有解释"的判断）
- **时间戳**：独立成立。夹逼 [12:32:14.011Z 0D → 12:32:29.183Z ENOENT]（e335:141 / 1dab:179）；元凶窗 [18.452, 24.444] 含于其中；node_modules 目录 mtime 20:32:22（01a0d325:2927 原文）落在执行窗内。
- **损坏边界**：独立成立。12:36:09.236Z 包级清点（4fe7:118）：8 包 entries=0（coding-agent 仅剩 node_modules）、tui=7、multi-workers=89；12:38:50.917Z 链接层清点（01a0d325:2925）：仅剩 pi-tui。8 包恰为 8 条被删 junction 的目标集合（与 01a0d325:2927 重建清单一一对应），tui 为第 9 条（pi-tui）目标且只删 156/236（3300+156=3456 与双源 D 计数吻合）。multi-workers 不是任何 junction 目标 ⇒ 未卷入。
- **恢复链**：独立成立。restore.sh 原文/执行/3456→0（d2f3:204/206/207）+ npm install 重建 9 条链（01a0d325:2926/2927）；恢复面恰为删除面的补集（一条不多、一条不少）。
- **"另有解释可同时满足三约束"的判断：不存在可信的单一替代解释。** 任何替代命令须同时满足：(i) 在夹逼窗口内已执行——窗口内可复核的破坏性 toolCall 仅 L142/L145，而 L145 先 `rmdir` 摘链（其进入 `if(Test-Path $t)` 分支这一事实本身证明 L142 未删掉链）；(ii) 产生 **git 自身的错误文本**且路径名指向 qg-head、rc=255——非 git 删除工具不会以 git 的报错格式点名 worktree 路径；(iii) 删除面精确等于 8 条 junction 目标 + 第 9 条的部分，且 @earendil-works 之后的 node_modules 条目不动；(iv) 零 ref 变动（reflog 间隙一手排除一切 ref 级操作）；(v) 事后 worktree 注册消失而目录残留（L144 的 list 仅主树 + L145 Test-Path=True）。ref 级操作死于 (iv)；npm 死于"tracked 源码被删"；直接递归删真树死于 (ii)(v) 且窗口内无可执行实例。2026-09-09 同机制先例（01a080f3:539/:541，同 EINVAL、同穿链删包、同"multi-workers 因链路未及而幸存"）进一步佐证该指纹唯一归属 `git worktree remove --force`。**结论：IN-1 与 IN-2 同源、同一命令，成立。**

### 3.3 AC-007（写入后被丢弃 vs 假声明）
**确曾写入后被丢弃，非假声明。** 8 环一手链见 §1：12:09:46 grep 见 console.log@88 → 12:10:02.943Z edit toolCall → 12:10:02.951Z "Successfully replaced 1 block(s)"（附 diff）→ 12:10:35.091Z vitest 5/5 绿且实出 [VERIFY] 行 → **两个彼此独立的会话**（56ff:24 @12:10:40.752Z、4580:49 @12:10:46.843Z）各自从磁盘回读 `process.stdout.write`@L91 → 12:13:35.623Z 任务卡轮次2 → 20:32 随树被删 → 20:36-38 被 restore.sh 按 index 写回（console.log@88）→ 12:40:56.066Z 事后复验 current==HEAD==console.log@88。时间线自洽无缺口。该修正最终于 10-10 15:29+0800 以提交 1a214416 落地（现为 verify() 助手形态）。

### 3.4 AC-005 "未坐实"是否成立（穷举是否真的为负、范围是否够）
**v1 的"未坐实"= 没查够，而非"查了且为负"。** v1 的扫描词表只匹配命令**字面**触及 `packages/**` 的文本，`git worktree remove --force "$env:TEMP\qg-head"` 字面上不触及 packages，故"穷举为负"是扫描范围不足的伪阴性；v2 §5 已诚实披露这一点并把 AC-005 升级为坐实（QG 全链一手复核成立）。**遗留问题**：v1 的"穷举会话记录为负 ⇒ 指令来自 pi 之外的进程"仍残留在 timeline §5 与 achieved.md 遗留中，与 v2 坐实结论（元凶就是 pi 会话 e335:142）及 timeline §1 自相矛盾——这是合并层错误（E4），不是证据层不诚实。

### 3.5 数字一致性（抽查 ≥3 个复算）
- **3,531 ✅**（两处一手：1dab:188 @12:32:54.960Z、4fe7:118 @12:36:09.236Z）
- **3,456 ✅**（两处一手 + restore before/after；= 3300+156 算术成立）
- **156-of-236 ✅**（tui 五分项计数 148/37/36/10/5 全对；被删 156=3456−3300；"原物幸存 80"为 mtime 口径 [未复测-无shell]，但与 12:36 的 tui entries=7 及恢复计数互补吻合）
- **10 条目 ✅**（@earendil-works 现有 10 条目）
- **3,448 ❌**（timeline/achieved 的 stale v1 值；正确值 3,456，且"8 个包整树共 3,448"连口径都错——8 包应为 3,300）
- **3,550 / 1,040 ❌**（timeline 的 stale v1 值；v2 自测为 2512/2537（含漂移）——QG [未复测-无shell]）
- **"98 条变更"：未找到**——六份被审文档与 .agenticdoc 全树均无此字样；最接近的是 timeline §1 的"97 个他人未提交改动"（同样**无一手来源**：QG 未能在会话记录中复找到 97；最近一手计数为 75（12:32–12:36）、74（d2f3:209 @12:38）、82=78M+4??（01a11fac:323 @12:40:27））

### 3.6 PM 自查的诚实性（achieved.md §3 两条纠错）
- **①「8 条消失 + pi-tui 保留」：诚实且正确。** spec §1.1 原文"9 个 workspace junction 消失（仅 pi-tui 保留）"自相矛盾（保留即非消失）；一手证据：12:38:50.917Z 仅剩 pi-tui（01a0d325:2925）+ npm 重建 8 条（01a0d325:2927，重建清单恰为 8 个 pi-* + pi-tui 原物）+ 当前 10 条目。纠错与实际证据相符。
- **②「npm-cache\_logs 不可用于排除」：诚实且正确。** 当前 _logs 11 个文件全部为 2026-10-12T04:23–07:13Z，10-09/10-10 日志已滚没；PM 自己 20:38:58 的 `npm install`（01a0d325:2926 一手坐实）同样未留日志。撤回有据；且"npm 不是元凶"的替代论证（npm 无法删除 tracked 源码）依然成立。`logs-max=10` 数值 QG [未复测-无shell]（npm 默认值亦为 10，与现存 11 个文件量级一致）。

## 4. 发现的错误 / 夸大 / 漏项

**合并层（timeline / achieved.md，根因：二者写于 10-10 02:46–03:22，早于 10-10 11:00–11:25 的 v2 重跑稿，v2 修正从未回灌）：**

- **E1** timeline §2 + achieved.md §1：**"3,448"** 为 stale v1 值（正确 3,456）；timeline §2 "8 个包整树共 3,448 个 tracked 文件消失"双重错误（8 包=3,300；3,448 连 v1 总口径都不是正确值）。
- **E2** timeline §2（20:32:24.444 行）+ achieved.md §1：**"156/236 幸存"方向颠倒**——156/236 是被删后重建的部分，原物幸存是 80/236（IN-1 §3.4 / IN-2 §2.1 的正确表述未被合并层吸收）。
- **E3** timeline §2（20:37:54 行）：恢复机制表述"**缺失 ∪ 与 HEAD 有差异**"与数字 **3,550 / 1,040** 均为 v1 残留；v2 坐实的 restore.sh 只重写 `git ls-files -d` 的**当前缺失**路径（QG 逐字核对脚本原文）。
- **E4** timeline §5 + achieved.md §4 遗留："删除工具/进程本体（**AC-005 穷举会话记录为负 ⇒ 指令来自 pi 之外的进程**）"——与 IN-2 v2 §0/§1（坐实：元凶即 pi 会话 e335:142）**及 timeline §1 自身**矛盾；v1 残留未清除。
- **E5** achieved.md §4 遗留："恢复命令具体条目"列为未解——IN-2 v2 §3.2 已坐实（restore.sh 原文/执行者/时刻/3456→0，QG 一手复核）。
- **E6** achieved.md §4 遗留："20:39 npm reify 的触发者"列为未解——IN-1 §6 已给出且 QG 一手坐实（PM 会话 01a0d325:2926，`npm install --ignore-scripts` @12:38:58.496Z）。

**证据层（轻微，引用精度）：**

- **E7** IN-2 §2.4：thinking 引用时刻标 **12:32:37.458Z**；该段 thinking（"`git worktree remove` failed because the junction…"）实际在 **12:32:28.112Z**（e335:145）；12:32:37.458Z（e335:147）是另一段"Cleaned up…"。
- **E8** IN-1 §AC-002：**Claim-Id 引证源错**——写"`.agenticdoc/mw-vision-role/pm-state.md`"，实际在 `_index.parallel:46`（值 WENBOZHOU-PC4:8152 本身真实）。
- **E9** IN-1 §7 未坐实#3 与 IN-2 §1.1 口径冲突：IN-1 记 pid"无法复核"，IN-2 记 pid=159560；实测 trace.log:229 `[START] pid=159560` 紧邻 :230 的 12:07:43 START——**IN-2 正确**，IN-1 过度保守（非事实错误）。
- **E10** IN-2 §4.3："**找不到该 diff 存在过的任何一手记录，且现有证据倾向反证**"表述过强：01a11fac:323（12:40:27.142Z，恢复完成后约 2 分钟）实测 mw-runner.ts 对 HEAD 存在 `1 file changed, 1+/1-`，且 :330（12:40:55.264Z）记录其消失——这正是 spec §1.2"1 行 diff 消失"的观测来源。12:17–12:32（事故前）窗口内确无观测，故"未坐实"结论本身成立；但"没有任何一手记录"不成立，且该消失发生在恢复完成（12:38:18）**之后**，不能归因于本次事故的恢复动作。
- **E11**（同 key 后续文档，超出六份清单但同目录）in2-recurrence-20261010 §3："mw-runner.ts 的 1 处未提交 diff **在 10-09 IN-2 中已丢失**（见 in2-…md）"——把 IN-2 的"未坐实"转述为既成事实，引用失真。
- **E12** timeline §1："当时共享树有 **97 个**他人未提交改动"——无一手来源（QG 未找到 97 的出处；最近一手计数 74/75/82，见 §3.5）。
- **E13**（漏项）timeline/IN-1/IN-2 均未提及 **2026-09-09 同机制先例**（01a080f3:539/:541：`git worktree remove --force` 穿 junction、同样 EINVAL、~1100+ tracked 文件被删、multi-workers 因链路未及而幸存）；in2-recurrence 称 10-10 为"第二次发生"，按已知记录应为**第三次**同机制事件。不影响 10-09 结论（反而强化机制判定），但"教训已被现实检验"的叙事缺了先例。
- 备注：IN-1/IN-2 记 e335"共 149 行"——实际为 149 个内容行 + 1 个空尾行（:150）；口径可用，不计为错。

## 5. 未坐实项是否被诚实标注

**证据层：诚实。** IN-1 §7（7 项）与 IN-2 §6（10 项）清单抽查成立：EINVAL 具体占用进程（确无只读证据可反推）、10-09 派发行被覆盖（QG 实测 _workers.parallel:278 已漂移到 2026-10-12 重派，更远）、12:13:31Z 自报时刻差 4.6s（3290:42 一手核实）、mw-runner 事故前窗口无观测（成立，但表述需按 E10 修正）、IN-2 明确声明未独立复核 npm 归属与复现（QG 已替其闭环前者）——无发现"把没查够伪装成查过为负"的隐瞒（v1→v2 的方法论缺陷已由 v2 自曝）。
**合并层：不诚实（陈旧而非造假）。** timeline §5 / achieved.md 遗留的清单把 3 项已坐实事实继续列为未解（E5/E6），并保留 1 条与坐实结论相反的 v1 推断（E4）。

## 6. 总体结论：**有条件 PASS**

**取证核心全部成立**：AC-001..AC-007 的结论与一手证据链经本 QG 独立复核**全部验证**（元凶命令逐字、夹逼区间、D=3456 双源、restore.sh 原文与 3456→0、AC-007 八环链含两个独立回读、reflog 间隙证明零 ref 变动、同源判定三点独立成立且无替代解释、PM 两条自查纠错属实）。QG 抽查的约 30 处 `文件:行号` 引用在证据层仅 3 处轻微失准（E7/E8/E10）。

**扣分全部在 PM 合并层**（timeline/achieved 未吸收 v2 修正）：stale 数字（3,448/3,550/1,040）、"156/236 幸存"方向颠倒、恢复机制表述过时、未坐实清单陈旧且含一条与自身结论相反的推断（E1–E6）。

**PASS 条件（修复后即可转 PASS）：**
- C1 timeline §2/§5 与 achieved.md §1/§4 吸收 v2：3,456（8 包=3,300+tui 156）；"156/236 被删后重建、80/236 原物幸存"；恢复机制="只重写当前缺失路径"；删除或改标 3,550/1,040 为 v1 口径。
- C2 删除/改写"AC-005 穷举为负 ⇒ pi 之外"残留（E4）。
- C3 遗留清单移除或标注已坐实三项：删除工具本体（=git worktree remove --force）、恢复命令（=restore.sh，d2f3:204/206/207）、npm reify 触发者（=PM 会话 01a0d325:2926）。
- C4 修 IN-2 §2.4 引用时刻（→12:32:28.112Z）与 IN-1 Claim-Id 引证源（→ _index.parallel:46）。
- C5 IN-2 §4.3 按 01a11fac:323 改写（保留 12:17–12:32 未坐实；撤回"没有任何一手记录/倾向反证"）；同步修正 in2-recurrence §3 的转述。
- C6（建议）时间线补引 2026-09-09 先例（01a080f3:539/:541），事故族计数改为"已知三次"。

## 7. 只读合规声明

- 未改任何生产文件；未执行任何 git 命令（对 `.git/**` 仅做文件读取：HEAD/refs/logs）；未建/删 worktree；未触碰 `_index.parallel`（仅读取）。
- 全部取证仅用 read/find/grep/ls 对会话 jsonl、`.git/**`、`node_modules/@earendil-works`、npm `_logs`、`.agenticdoc/**` 做只读访问。
- 唯一写入 = 本报告（`workers/wip-qg-review/report-quality-gate-report-20261009.md`）与本任务 progress.md（均经 worker_file 落于本 worker 任务目录）。任务指定的 `evidence/quality-gate-report-20261009.md` 需 PM 复制落位（本 worker 无任意路径写工具）。
