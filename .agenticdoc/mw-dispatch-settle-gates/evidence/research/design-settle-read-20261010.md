# DRQ-2：结算期产物判据的写侧与读侧落点

- key：`mw-dispatch-settle-gates`；覆盖 AC-006 + AC-010 + AC-007
- 性质：只读调研（`read`/`find`/`grep`/`ls`/`bash`）。**本报告未修改任何仓库文件**；唯一写入 = 本目录 `report.md`。

---

## 0. 读取时刻与锚点声明

### 0.1 时刻 / 树状态

| 项 | 值 |
|---|---|
| 读取时刻 | `2026-10-10T21:27:12+08:00` |
| `HEAD` | `776b82d7f`（`chore: ignore the local .tmp scratch dir`） |
| `git status --porcelain` | **72** 行（其它 session 并发改动；与 RQ-2 报告测得的 72 一致） |
| 被本报告高频引用的脏文件 | `pm-orchestrator.ts +412`、`ui-bridge.ts +103`、`worker-mode.ts +84`、`output-writer.ts +9`（4 files, 585 insertions(+), 23 deletions(-)） |

**行号纪律**：本报告每一条 `文件:行号` 都在上述时刻用 `rg -n '<锚名>' <file>` 现读确认，**不沿用 RQ-2 报告（2026-10-10 早前）的行号**。锚点一律以"锚名 + 行号"成对给出；实现阶段按锚名重 grep，不要直接跳行号。读取用命令模式：`rg -n 'finishSuccess|markOutcome|...' <file>`。

### 0.2 关键锚点速查（本报告现读）

| 锚 | 位置 |
|---|---|
| `hasProductEvidence()` 定义 | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:487-492` |
| 其唯一调用 | `pm-orchestrator.ts:653` |
| `DispatchAlarmKind` 值域 | `pm-orchestrator.ts:387-397` |
| `DispatchAlarm` 接口 | `pm-orchestrator.ts:399-403` |
| `describeDispatchAlarm()` | `pm-orchestrator.ts:409-435` |
| `recordDispatchAlarm()` | `pm-orchestrator.ts:439-458`（ledger 路径常量 `:406`；row 形状 `:452`） |
| PM 侧 alarm 接线（once/kind/session） | `pm-orchestrator.ts:1114` + `:1136-1139` |
| `writeOutputGuarded` / `markOutcome` / `finishRun` | `worker/worker-mode.ts:774-780` / `:785-788` / `:796-802` |
| `let outputWritten`（per-process） | `worker-mode.ts:856`；唯一读者 = `process.on("exit")` `:870` |
| exit 安全网 | `worker-mode.ts:857-887` |
| `hasWriteTools` | `worker-mode.ts:910` |
| `recordEnd(exitCode: 0\|1)` | `worker-mode.ts:1075-1086` |
| `let taskDone` | `worker-mode.ts:1111`（只在 watchdog 定时器里被读：`:1224`/`:1233`/`:1246`/`:1305`） |
| `finishSuccess()` | `worker-mode.ts:1350-1377` |
| `pi.on("agent_settled")` | `worker-mode.ts:1379-1440` |
| `parseTaskMd` 的两种 root | `worker-mode.ts:391-393`（`agenticdocRoot` = `<key>/workers`；`trueAgenticdocRoot` = `.agenticdoc`） |
| `runMarker()` | `shared/run-store.ts:113` |
| `writeOutput` 合并点 | `worker/output-writer.ts:52-96`（合并点 `:95`） |
| `RUN_TERMINAL_STATUSES` / `RunStatus` | `shared/run-store.ts:34` / `:29` |
| `collectArtifacts()` | `shared/run-store.ts:119-138` |
| `isTerminalRunStatus()` | `shared/run-store.ts:96-98` |
| `readOutputSection` / `readOutputSummary` / `readTerminalDetail` / `readOutputBody` | `pm/ui-bridge.ts:344-354` / `:359-361` / `:450-481` / `:370-384` |
| `readTerminalDetail` 的 src 调用者 | `ui-bridge.ts:652`（`renderWatchLines`） |
| `_exit_to_status` | `packages/multi-workers/launcher.py:367-373` |
| reap 只看退出码 | `launcher.py:838-844`（`:842` `_exit_to_status(code)`，`:843` `_update_status`） |
| `_reconcile_orphans` 的 product-first 阶梯 | `launcher.py:555-640`（读 run.json `:583-587`） |
| ack 收敛的 product-first | `launcher.py:868-880`（`:874-875`） |
| `RUN_TERMINAL_STATUSES` / `read_run_status` / `mark_run_lost` / `update_status` | `mw_common.py:1719` / `:1747-1764` / `:1768-1806` / `:1943+` |
| `_TERMINAL_STATUSES`（queue 归档 / doctor 两处） | `mw_common.py:167` / `:2110` |
| 唯一 TS 队列行写入者 | `pm/task-dispatcher.ts:295`（`store.upsert(full)`，写 `pending`） |

### 0.3 语料复核（本报告独立复现，含对任务书措辞的一处更正）

语料 = `.agenticdoc/mw-gate-verdict-hardening/workers/`，30 个目录。逐目录统计 `## TL;DR` 块数 vs `[START] pid=` 次数 vs `[END]` 次数：

| 目录 | blocks | starts | ends |
|---|---|---|---|
| `mgh-rq1-l3-abort` | 3 | 3 | 3 |
| `mgh-rq2-gate-alert` | 3 | 4 | 2 |
| `mwg-t11-g3-cli-doctor` | **9** | **9** | 1 |
| `mwg-t16-docs-closure` | **3** | **3** | 1 |
| 其余多块目录（drq1/drq2/drq3/rq3/rq4/rq5） | 2 | 2~3 | 2 |

**更正**：任务书把"T-11 出现 9 段、T-16 出现 3 段"归到"同进程二次 settle"。实测 **blocks == starts**（T-11 9=9，T-16 3=3）⇒ 这两个目录的多块是**跨 run 追加**（每段来自一次独立 spawn；T-11 9 次 spawn 只有 1 次写出 `[END]`，其 `output.md` 实测 9 块中 8 块是崩溃占位符 = 16 行 `^(worker exited without writing output)$`）。"同进程二次 settle"是**代码层真实存在但语料不可分离**的第二成因（无守卫，见 §4）。这条更正直接影响 §4 的守卫落点：跨 run 多块不可在进程内消除，只能靠读侧选择；进程内幂等只解决同进程那一类。

---

## 1. `hasProductEvidence()` 调用面与兼容性

### 1.1 定义与唯一调用（现读行号）

```ts
// pm-orchestrator.ts:485-492
/** Product evidence for {@link dispatchNewTasks}'s empty-queue guard (AC-020):
 * files the worker itself writes into its own directory. A task dir holding
 * only `task.md` has never run — that is a fresh project, not a lost queue. */
function hasProductEvidence(taskDir: string): boolean {
	for (const name of ["output.md", "report.md", "run.json", "trace.log"]) {
		if (fs.existsSync(path.join(taskDir, name))) return true;
	}
	return false;
}
```

唯一调用 = `pm-orchestrator.ts:653`：

```ts
// pm-orchestrator.ts:645-657（per-owner 循环内，收集完 undispatched、docs gate 之前）
// AC-020: an empty queue plus product evidence in the very tasks we are
// about to queue is the IN-3 shape — the queue lost its rows while the
// work had already run. Refuse the whole scan instead of re-running
// history; a real fresh project has no such evidence and dispatches.
if (queueIsEmpty && undispatched.some((t) => hasProductEvidence(path.dirname(t.taskMdPath)))) {
	flushScanAlarms();
	opts.onAlarm?.({ kind: "queue-unreadable", count: undispatched.length, detail: owner.name });
	return;           // ← 中止整轮 scan（不是跳过这个 owner）
}
```

### 1.2 完整语义（这个调到底在判什么）

判据链（`dispatchNewTasks`，`pm-orchestrator.ts:527+`）：

1. `queueIsEmpty` = 本轮 `workerStore.readQueue()` 的 `rows.length === 0`（`pm-orchestrator.ts:551`）——**全项目队列无行**。
2. `undispatched` = `{owner}/workers/<taskKey>/` 里有 `task.md`、队列里没有对应行、且非 conductor 任务（`:627-648`）的候选。
3. 只要**本 owner** 的任一候选目录里存在 `output.md|report.md|run.json|trace.log` ⇒ 发 `queue-unreadable` 告警并 `return`，**中止整轮 scan**（连其它 owner 也不再看）。

⇒ 语义 = **"这批候选里有的目录已经被跑过（有运行痕迹），但队列却是空的"**，即 IN-3 形状（队列丢行 + 历史已跑）。它的目的是**防止把历史整体重跑一遍**。注意判据是"**跑过**"，不是"**产出过**"：`trace.log`/`run.json` 是 spawn 即写（`worker-mode.ts:708` `appendStartPidLine`；`:734` `writeRunState`），两者都在第一 turn 之前、任何产物之前。这正是 RQ-2 §2.1/§2.2 证的"该谓词 ≈ 该目录曾 spawn 过 worker"。

### 1.3 收窄成 AC-006 三级通道后，**会**改变该处行为（方向是变弱/危险）

收窄谓词（AC-006 三级通道）与现谓词的关系：**收窄为真 ⇒ 现谓词必为真**（通道 1 要求 `report.md` 非空、通道 2/3 要求 `output.md` 存在）。故收窄只会让 `some(...)` **更少**为真 ⇒ 更少触发 `queue-unreadable` ⇒ **更多候选进入派发**，即往 IN-3 的方向（多派发）退化。两个具体反例（都会由"拒绝 scan"翻成"重跑历史"）：

| # | 候选目录内容 | 现判据（`existsSync`） | 收窄到 AC-006 三级通道 | 后果 |
|---|---|---|---|---|
| C1 | 只有 `output.md`，内容是崩溃占位块 `(worker exited without writing output)` | **真 ⇒ 拒绝 scan** | 假（占位符-only 非产物） | 该已跑过的任务被重新入队 ⇒ 重跑历史 |
| C2 | 只有 `trace.log` + `run.json`（硬杀，第一产物之前死） | **真 ⇒ 拒绝 scan** | 假（无 `output.md`/`report.md`） | 同上 |
| C3 | `output.md` 内容 `"already ran\n"`（现行测试 23 的 fixture） | 真 ⇒ 拒绝 scan | 假（无 `## TL;DR`/`## Summary` 块） | 同上（测试 23 直接转红） |

**结论（权责建议）**：`pm-orchestrator.ts:653` 处**不得**改用 AC-006 谓词。两个判据回答两个不同问题，必须并存：

- `hasProductEvidence()`（现名，建议改名为 `hasRunEvidence()` / `hasDispatchHistory()` 以消除"产物"歧义）= **"这个目录跑过没有"** —— 供派发期"队列是否丢行"判断（AC-020），刻意包含 spawn 即写文件。
- 新的 `isDeliveredProduct(dir, {kind})` = **"这次只读 run 交付了没有"** —— 只在结算期用（AC-006）。它是 `hasRunEvidence` 的**严格子集**，不可回流到派发守卫。

> 注：spec G-f 说 `hasProductEvidence` "语义是'这个目录跑过'（含 trace.log / 启动即写的 run.json）而非'这次跑出了产物'"——这句话恰恰说明它在**派发守卫**里是**正确**的（IN-3 就是要判"跑过"），只是不能拿来当 AC-006 的判据。RQ-2 的 "AC-006 若复用 `hasProductEvidence` 会全程误判" 与本节不矛盾：错在复用，不在谓词本身。

### 1.4 若收窄就必须补的测试（判别性、非空洞）

放 `packages/coding-agent/test/suite/worker-dispatch-guard.test.ts`（现 `:240` 的 "empty queue plus product evidence" 用例内加分支，或新 `it`）：

- **T-DRQ2-1（判别器）**：空队列 + 候选目录**只有 `trace.log`**（无 `output.md`/`report.md`）⇒ 仍发 `queue-unreadable`、`store.readAll()` 为空。反向：摘掉 `trace.log` ⇒ 正常派发 `pending`。
- **T-DRQ2-2（判别器）**：空队列 + 候选目录 `output.md` 内容为占位块 `## TL;DR\n\n(worker exited without writing output)\n\n## Summary\n\n(worker exited without writing output)\n` ⇒ 仍发 `queue-unreadable`、零队列行。反向：同目录追加 `report.md` 非空 ⇒ 仍拒绝（现行为，通道 1 也拒绝）。

这两条的作用 = **锁死"派发守卫用 run-occurrence、结算用 product-content"的边界**：任何把 `:653` 换成 AC-006 谓词的改动都会让它们转红，而现行测试 23（`output.md` 内容 `"already ran\n"`）**不足以**捕获（若只加"非占位符"要求，测试 23 仍绿——RQ-2 已指出）。

---

## 2. 结算写侧落点与权责

### 2.1 TS 收尾链（现读行号，逐跳）

`workerModeActivate` 内的收尾链，按数据流顺序：

| # | 锚（`worker-mode.ts`） | 作用 |
|---|---|---|
| 1 | `:708` `appendStartPidLine` | spawn 即写 `trace.log [START] pid=` |
| 2 | `:719-734` 构造 `RunState` + `writeRunState` | spawn 即写 `run.json status="running"`（`artifacts: []`，`:730`） |
| 3 | `:739-757` `dispatchRefusal` 分支 | 启动 fail-closed：`markOutcome(1)` + `writeOutput(exitCode:1)` + `finishRun("failed",1)` + `exit(1)` |
| 4 | `:774-780` `writeOutputGuarded(opts)` | **唯一产物写出口**：`markOutcome(opts.exitCode)` → `writeOutput({...opts, runMarker: runMarker(runState)})` → `appendReadScopeRejectionsSection(...)` |
| 5 | `:785-788` `markOutcome(exitCode)` | `runState.status = exitCode === 0 ? "done" : "failed"`（**1 处映射；无 2 分支**） |
| 6 | `:796-802` `finishRun(status, exit?)` | 写终态 `status`/`ended_at`/`exit`，重收 `artifacts = collectArtifacts(taskDir)`（`:800`），`writeRunState`（`:801`） |
| 7 | `:856` `let outputWritten` | **per-process** 标志；唯一读者 = `:870` 的 `process.on("exit")` |
| 8 | `:857-887` `process.on("exit")` | `:870 if (outputWritten) return;` → `:872-878` 写崩溃占位块（`(worker exited without writing output)`）→ `:886 if (!isTerminalRunStatus(runState.status)) finishRun("failed",1)` |
| 9 | `:1075-1086` `recordEnd(exitCode: 0\|1)` | `appendEnd`（`[END] exit=`）+ `finishRun(exitCode===0?"done":"failed", exitCode)`（`:1083`）+ worker.log 行 |
| 10 | `:1133-1160` `timeoutExit` | `writeOutputGuarded(exitCode:1)` → `recordEnd(1)` → `outputWritten = true`（`:1152`）→ `exit(1)` |
| 11 | `:1350-1377` `finishSuccess()` | `taskDone = true`（`:1351`）→ `writeOutputGuarded({exitCode:0, summary: buildSummary(), changedFiles: [], verificationSteps: "See task output for details.", exitReason: "Agent settled after N tool call(s)."})`（`:1354-1362`）→ RAG marker（`:1364-1374`）→ `recordEnd(0)`（`:1375`）→ `outputWritten = true`（`:1376`） |
| 12 | `:1379-1440` `pi.on("agent_settled")` | 无 phase / phase 走完 ⇒ `finishSuccess()`（`:1392`、`:1423`）；异常 ⇒ `:1425-1439` 写 `"Task failed during output writing."` + `recordEnd(1)` + `exit(1)` |

终态状态机：**`markOutcome` 只有 0→done / 非0→failed 两态**（`:786`），`finishRun` 接受任意 `RunStatus`。`run-store.ts:34` 的 `RUN_TERMINAL_STATUSES = {done, failed, needs-clarification, lost}` 与 `run-store.ts:29` 的 `RunStatus` 已把 `needs-clarification` 列为终态 ⇒ **不需要改终态集，只需要让 TS 能产出它**。

### 2.2 AC-006 判定应加在哪一步（具体落点）

**落点：`finishSuccess()` 内、`writeOutputGuarded` 之前**（`worker-mode.ts:1350-1354` 之间插入判定），理由是它同时解决三件事：

1. `writeOutputGuarded` → `markOutcome(exitCode)` → `runMarker(runState)` 三处都读同一个 `exitCode`；在写之前定好 `exitCode`，则 **output.md 首行 marker、`## Questions`/`## Exit Reason` 段、run.json.status 三者一致**（现在 `:1354` 用 0、`:1362` 写 marker，若写后再改状态，marker 会说 `status=done` 而 run.json 说 `needs-clarification` —— 违反代码自述的"the row and the product tell the same story"，见 `worker-mode.ts:749-753` 注释与 `run-store.ts` 的 D-023）。
2. 判定输入在此时**已经全部可用**：`report.md`/`report-<slug>.md` 是 worker 在 run 内用 `worker_file` 写的（磁盘）；agent 最终回复在 `lastAssistantText`（`buildSummary()` `:1338-1342` 的数据源，即将成为 `## Summary`/`## TL;DR`）；`collectArtifacts(taskDir)`（`run-store.ts:119-138`）此刻可预收一次用于 `artifacts` 通道与 `writes=`。
3. 只需把判定结果折进 `exitCode`：`delivered ? 0 : 2`，复用 output-writer **早已存在的 exit-2 分支**（`output-writer.ts:71-72` 写 `## Questions`）。

配套的最小改动（3 处）：

- `markOutcome`（`:786`）：`0 → done`，`2 → needs-clarification`，其余 → `failed`。抽成单一 `exitToRunStatus(exitCode)` 并让 `recordEnd` 复用。
- `recordEnd` 签名（`:1075`）：`(exitCode: 0 | 1)` → `(exitCode: 0 | 1 | 2)`；`:1083` 改用 `exitToRunStatus`。
- `finishSuccess`（`:1354-1362`）：判定为 NC 时传 `exitCode: 2` + `questions: <reason>`（例如 `no-product: report.md missing and output.md carries no machine line / inline [VERIFY] / existing referenced evidence/**`），summary 仍为 `buildSummary()`。

不落点（明确排除）：

- **不落 `writeOutput` 之后**（会追加第二块，见 §4）。
- **不落 `recordEnd` 内**（那时 output.md 已按 exit 0 成形）。
- **不落 `process.on("exit")`**（`:857-887` 是兜底，只处理"什么都没写"）。
- **不落失败/拒绝/超时/异常路径**（`:742-757` 启动拒绝、`:823-835` image-cap、`:1144-1159` 超时、`:1429-1439` settle 异常）：这些已写 `markOutcome(1)`/`finishRun("failed",…)`，AC-006 若在此改判成 NC 会覆盖真实失败原因、并可能把崩溃占位符路径反转（测试 13/14 的护栏）。`finishSuccess` 是唯一的"成功 settle 边界"，天然与这些路径互斥。

### 2.3 `needs-clarification`：worker 自报还是框架改判？

**现状事实**：TS worker **从不**产出 `exitCode=2`。`writeOutput` 支持（`output-writer.ts:71-72`），`launcher._exit_to_status` 支持（`launcher.py:372`），但 `worker-mode.ts` 的 6 个 `writeOutput` 调用点只传 0/1：`:746`(1)、`:827`(1)、`:875`(1)、`:1147`(1)、`:1357`(0)、`:1432`(1)。`run.json` 侧同理：`markOutcome` 只产出 done/failed，`needs-clarification` 在 `RunStatus` 里存在但**无 TS 写者**；Python 只补 `lost`（`mw_common.mark_run_lost` `:1768-1806`）。⇒ **`exitCode=2` 是一条"契约已备、无生产者"的路径**（`test_launcher.py:735` 直接单测映射；`test_integration.py:250` 用假 exit 2 造 NC）。

**AC-006 引入生产者，且必须是"框架改判"而非"worker 自报"**：worker 已经 settle（`agent_settled` 触发、exit 0），是**框架**在读产物后改判。同时把 `exitCode` 折成 2（§2.2），使 OS 退出码、`[END] exit=`、`run.json.exit`、marker 全部自洽 —— 这样 `_exit_to_status(2)` 这条既有 Python 路径**零改动**就能把队列行写成 NC（前提是进程真以 2 退出，见 §2.4）。

**两条路径不重复/不互相覆盖的规则**：

1. **单点判定**：AC-006 判定只在 `finishSuccess` 里算一次，结果折进 `exitCode`。不存在第二处重复判定。
2. **路径互斥**：失败/拒绝/超时/异常路径不会到达 `finishSuccess`；`finishSuccess` 不会在非 success 路径被调。所以"自报 NC（exit 2）"与"框架改判 NC"不会同时发生。
3. **不许降级**：框架判定只能把 `done → needs-clarification`，**不得**把 `failed` 改成 `done`（`finishRun` 的 `:797` 直接赋值 status；AC-006 不碰非 0/2 分支）。
4. **幂等**：`finishSuccess` 入口加 `taskDone` 守卫（§4），保证"框架改判"只发生一次，二次 settle 不再写第二块、也不再次触发告警。

### 2.4 Python 侧要不要做同样的产物判定？——**不做**（权责结论）

现状权责（现读）：

| 环节 | 现写者 | 锚 |
|---|---|---|
| `run.json` 的 `running`/所有终态 | **worker（TS）** | `worker-mode.ts:734` / `:801`；`run-store.ts:14-23` 注释明写"worker is the only writer of running and terminal states" |
| `run.json` 的 `lost` | **launcher（Python，唯一允许的追加）** | `mw_common.py:1768-1806` |
| 队列行（`_workers.parallel`）的 `pending` | **TS `WorkerStore.upsert`** | `pm/task-dispatcher.ts:295` |
| 队列行的**终态** | **launcher `update_status`（reap / reconcile / ack 收敛）** | `launcher.py:843` / `:637` / `:877`；`mw_common.py:1943+` |

⇒ **队列行的 `done` 由 launcher 写**（reap 路径，`launcher.py:838-844`）。而 reap 现在**只看退出码**（`:842` `_exit_to_status(code)`），**不读 `run.json`**。这就是"事故仍记成 done"的直接成因，也是 AC-006 若只改 TS 会被立刻覆盖的原因：

- 若 TS 只把 `run.json` 写成 `needs-clarification` 而 pi 以 0 退出 ⇒ reap 写 `done`，`done` 覆盖 NC。
- 若 TS 同时让进程以 2 退出（`process.exitCode = 2`）⇒ `_exit_to_status(2) = "needs-clarification"`，reap 写 NC，**无需改 Python**。但 pi 的 print-mode 路径（`main.ts:918-929`）只在返回非 0 时 `process.exitCode = exitCode`，0 时不动 `process.exitCode`，故 worker 在 `finishSuccess` 里置 `process.exitCode = 2` 会被自然退出带走（不 `process.exit`，stdout flush 不受影响，`:1345-1349` 的注释前提仍成立）。这是**能跑但不该独占**的机制：它把结论绑在 pi 的退出码语义上。

**建议（双保险，但权威在 run.json）**：

1. **权威**：`launcher.py` reap 改为 **product-first**，与 `_reconcile_orphans`（`:583-587`）和 ack 收敛（`:874-875`）同形：

   ```
   run_status = mw_common.read_run_status(task_dir)
   status = run_status if run_status in mw_common.RUN_TERMINAL_STATUSES else _exit_to_status(code)
   ```
   `:841-843` 三行内改完。零回填语义不变：无 `run.json` ⇒ 走 `_exit_to_status(code)`（历史行为逐字不变）；`run.json` 是 `running`/未知 ⇒ 也走退出码（不 fab 终态）。理由 = D-022 已经确立的"product 是真相、队列行是缓存"（`run-store.ts:14-23`；`launcher.py:568-571` 注释）。
2. **加固**：`finishSuccess` 的 NC 分支同时置 `process.exitCode = 2`，使 `[END] exit=2`、`run.json.exit=2`、OS 退出码与 `_exit_to_status` 一致；即使 Python 侧未升级也正确。
3. **Python 不做产物判定**：不在 `launcher.py`/`mw_common.py` 里解析 `report.md`/`output.md` 内容。理由：① 会造第二真相源（AC-006 谓词必须与 TS 单一实现一致，跨语言复刻必然漂移）；② RQ-2 的谓词含"引用交付物路径存在""内联 `[VERIFY]`"等启发式，Python 复刻成本高、假阳性风险大；③ Python 侧现有职责是**传播**（`read_run_status`），不是**判定**。`mark_run_lost` 是"进程没了、结果未知"的**唯一允许追加**，与"跑完了但没产物"是两回事（D3 已定 NC 而非 lost）。
4. **PM 不写终态队列行**：`pm-orchestrator.ts` 全文无 `workerStore.upsert(status≠pending)`；唯一 TS 写点是 `task-dispatcher.ts:295`（pending）。保持。

### 2.5 alarm 落点：`kind="no-product"`

**现状**：

- 定义域：TS 联合类型 `DispatchAlarmKind`，`pm-orchestrator.ts:387-397`（现有 5 值：`queue-rows-unparsable` / `queue-unreadable` / `dispatch-quota` / `out-of-scope` / `run-ledger-conflict`）。**py 侧无 kind 枚举**——`recordDispatchAlarm`（`:439-458`）只写 JSON，Python 不读 `dispatch-alarm` 行。
- 写入函数：`recordDispatchAlarm(agenticdocRoot, alarm)`，`pm-orchestrator.ts:439-458`；row = `{seq, phase:"dispatch-alarm", kind, count, detail}`（`:452`），ledger = `<agenticdocRoot>/_autopilot/auto-decisions.jsonl`（`:441`）。
- 人类文本：`describeDispatchAlarm(alarm)`，`:409-435`（**exhaustive switch，无 default**）。
- PM 接线：`pm-orchestrator.ts:1114` `dispatchAlarmsSeen: Set<DispatchAlarmKind>` + `:1136-1139`（**once per kind per session**，随后 `deliverPmAlert`）。此 dedup 是为"每轮 scan 重复告警"设的，**不适用于逐 run 的 no-product**。

**`kind="no-product"` 需要改什么**：

1. `DispatchAlarmKind`（`:387-397`）加 `| "no-product"`。
2. `describeDispatchAlarm`（`:409-435`）加 `case "no-product"`：否则新增值会落到无 case 的路径（运行时返回 `undefined`）。文案建议：`"${count} read-only run(s) settled without a product — needs-clarification + human review: ${detail}"`。
3. 调用点：**在 worker 的 NC 分支里**（§2.2 的 `finishSuccess`），因为那里是唯一同时知道 `run_id` / `task_key` / `kind` / 判定原因的地方，且天然**每 run 一次**（配 §4 幂等后不会重复）。`count=1`，`detail=<task_key>`（可选 `:<type>`）。
   - 传参 root 必须用 **`meta.trueAgenticdocRoot`**（`worker-mode.ts:393`），不是 `meta.agenticdocRoot`（后者是 `<key>/workers`，会把 ledger 写到 `<key>/workers/_autopilot/` —— 实测语料 0/30 有该目录）。这是本键最容易踩的一个坑。
4. 模块边界：`recordDispatchAlarm` 现在住在 `pm/pm-orchestrator.ts`；`worker/worker-mode.ts` 目前只 import `shared/*`、`rag/*`、`worker/*`（现读 `:1-59`），**没有 `worker → pm` 的边**。建议把 `DispatchAlarmKind`/`DispatchAlarm`/`describeDispatchAlarm`/`recordDispatchAlarm` 原样下沉到 `shared/dispatch-alarm.ts`，`pm-orchestrator.ts` 再 `export { … }`（保持现有 import 路径与测试不破）；worker 从 shared 导入。若不接受该重构，则退而求其次由 PM 在终态回读里发（`pm-orchestrator.ts:905-922` 段），但那样 dedup 必须改成 **per `run_id`**（现 `dispatchAlarmsSeen` 是 per kind/session，会吞掉第二次 no-product）。
5. 测试：`test/suite/worker-dispatch-guard.test.ts:335-357` 的 `alarms` 字面数组加 `{ kind: "no-product", count: 1, detail: "t-1" }`（并断言 `describeDispatchAlarm` 含 count 文本）。
6. `phase: "dispatch-alarm"` 已使该行对 `phase == "decide"` 消费者不可见（`:434` 注释），无需改消费侧。

---

## 3. 读侧 `readOutputSection` 的全部调用者与最小改动

### 3.1 调用面总表（现读，`rg -n` 结果）

| # | 调用者（文件:行号） | 用途 | 依赖"首匹配"？ |
|---|---|---|---|
| 1 | `pm/ui-bridge.ts:360`（`readOutputSummary` 内） | `## Summary` body（legacy 详情源） | **是（contract）**，见测试 3 |
| 2 | `pm/ui-bridge.ts:457`（`readTerminalDetail(failed)`） | `## Exit Reason` 首行 ?? "" | 现状是首匹配，**但换"末个非占位"更正确**（多 run 目录会取到早期崩溃占位） |
| 3 | `pm/ui-bridge.ts:460`（`readTerminalDetail(needs-clarification)`） | `## Questions` 首行 ?? `readWorkerLogTail` ?? `"no output.md"` | 同上（换末个更正确） |
| 4 | `pm/ui-bridge.ts:464`（`readTerminalDetail(lost)`） | `## Exit Reason` 首行 ?? log tail ?? lost 文案 | 同上 |
| 5 | `pm/ui-bridge.ts:470`（`readTerminalDetail(done)`） | `## TL;DR` 首行（AC-010 的直接受害点） | 首匹配即**缺陷**（T-11/T-16/`mgh-rq2` 首块是占位符） |
| 6 | `pm/ui-bridge.ts:472`（`readTerminalDetail(done)`） | 经 `readOutputSummary` 取 `## Summary` 首行 | 同 #5（fallback 也会命中占位符） |
| 7 | `pm/ui-bridge.ts:652`（`renderWatchLines`） | watch widget 终端行的 detail | 经 `readTerminalDetail`，见 #2-#6 |
| 8 | `pm/pm-orchestrator.ts:922`（`readOutputBody`，**不同函数**） | 终态回读整份 output.md 注入 PM 会话 | 否——它读**整文件**，多块全在，不存在遮蔽 |
| 9 | 测试：`test/extensions/agent-team-loop.test.ts:2625,2626,2627,2628` | 直接断言 `readOutputSection` 首匹配 + 缺文件 undefined | **是（contract 锁）** |
| 10 | 测试：`test/extensions/agent-team-loop.test.ts:2637,2638,2639` | 正则转义（section 字面量含 `.+()`） | 否（转义语义，非首/末） |
| 11 | 测试：`test/extensions/agent-team-loop.test.ts:2649,2655,2661,2669,2676,2682,2690,2696,2701,2706` | `readTerminalDetail` 四条 fallback 链 | 单块 fixture，首==末 |
| 12 | 测试：`test/extensions/agent-team-loop.test.ts:2713` | `renderWatchLines` 接线 | 单块 fixture |
| 13 | 测试：`test/extensions/agent-team-loop-output.test.ts:97,127` | `readOutputSummary` 兼容 + `(no summary)` | **是（contract 锁）** |

计数：**readers = 4**（`readOutputSection`/`readOutputSummary`/`readTerminalDetail`/`readOutputBody`），**src 调用点 = 8**（5×`readOutputSection` + 1×`readOutputSummary` + 1×`readTerminalDetail` + 1×`readOutputBody`），测试断言点 21。

**Python 侧并行的首匹配（边界，明确不属 AC-010）**：`autopilot/conductor.py:1396-1408` `_md_section` 也是 `next(...)` 首匹配，服务 L3 的 `## Quality Gate Report`/`## Achieved`（`_l3_qualifies` `:1544-1550`）。它对崩溃占位符天然免疫（占位块没有这两节 ⇒ 不 qualify），多块陈旧问题由 `feature-l3-verdict-provenance/freshness` 的 mtime 取证单独拥有（`conductor.py:1639-1660` 注释与 `_l3_stream_aborted`）。AC-010 **不得**动 `_md_section`（frozen anchors，`test_autopilot_verdict_provenance_guard` 有 region-SHA 锁）。

### 3.2 兼容性判断

- **依赖首匹配"作为契约"的只有两处**：#9（`readOutputSection` 直接单测）与 #1/#13（`readOutputSummary` 的 legacy 语义，测试 3 断言空 summary ⇒ `(no summary)`）。**二者都不该被 AC-010 改动**——它们没有被遮蔽问题（#1 的调用方是"取 Summary 原文"，不是"取产物结论"）。
- **#2-#7 是缺陷方**：`readTerminalDetail` 的四条链在"首块占位 + 末块真报告"时给出占位符（RQ-2 实测 3/27 目录：`mgh-rq2-gate-alert`、`mwg-t11-g3-cli-doctor`、`mwg-t16-docs-closure`，且三者实际都交付了）。
- **#8 不受影响**：整文件回读会把所有块（含占位符）交给 PM；PM 自己看到完整历史，不存在"遮蔽"。**不改**。
- **`/mw` 命令面**：仓库内没有任何 `mw` 命令/`status-model.ts`/`monitor.ts` 直接调 `readOutputSection`（`rg -n 'readOutputSection|readOutputSummary|readTerminalDetail' packages/coding-agent/src` 只命中 `ui-bridge.ts`，现读）。`status-model.ts` 不从 output.md 抽小节。⇒ `/mw` 命令面**零影响**。

**结论**：不存在"业务上依赖首匹配"的调用者；首匹配只被两个测试当契约钉住。因此"取末个非占位块"应作为**新增读取函数**引入，而不是改 `readOutputSection` 本身。

### 3.3 最小改动方案

**方案 A（推荐）**：不改 `readOutputSection`/`readOutputSummary`；新增共享读取函数，只把 `readTerminalDetail` 的 4 处读点切过去。

1. 新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/output-sections.ts`：
   - `readOutputSections(content, section): {section, body}[]` —— 用全局 regex（`g` flag）取**全部**块，替代 `ui-bridge.ts:350-352` 的单次 `match`。
   - `isPlaceholderSection(section, body): boolean` —— 见 §3.4 的全集。
   - `readLastProductSection(taskDir, ...sections): string | undefined` —— 取最后一个**非占位**块（按给定 section 优先级；用于 done 的 `["TL;DR","Summary"]`）。
   - `readDeliveredProduct(dir, {kind})` / `evaluateReadOnlyDelivery(input)` —— AC-006 谓词（§5/§6 用）。
2. `ui-bridge.ts` 只改 4 行：`:457`/`:460`/`:464`/`:470` 改调 `readLastProductSection`；`done` 分支（`:470-473`）写成 `readLastProductSection(taskDir, "TL;DR", "Summary") ?? ""`，**不再**经 `readOutputSummary`（否则 fallback 又回首匹配）。
3. 保留 `readOutputSection`/`readOutputSummary` 原样（exported，测试与外部兼容）。

**方案 B（不推荐）**：直接把 `readOutputSection` 改成"末个非占位"。代价：① 测试 #9 必须改（首匹配契约消失）；② `readOutputSummary` 的空 summary 语义被吞（测试 #3 红）；③ "末个非占位"对 `## Exit Reason` 这类**每块都合法**的 section 语义不清（占位符判定必须按 section 特化）。收益不抵成本。

**谁该用哪个**：`readTerminalDetail`（及其 `renderWatchLines`/widget 消费者）用 `readLastProductSection`；`readOutputSummary` 保留首匹配；PM 回读（`readOutputBody`）读整文件；`readOutputSection` 作为通用 primitive 留给测试/未来。

### 3.4 占位符常量全集（写侧现读，15 个 distinct 串）

**A. `worker/output-writer.ts`（harness 段）**

| 常量原文 | 行号 | 出现在 section | exit |
|---|---|---|---|
| `(no conclusion)` | `:49`（`headline()` 空输入） | `## TL;DR` | 任意 |
| `(no summary)` | `:62` | `## Summary` body | 任意 |
| `(none)` | `:65`（`changedFiles?.join() ?? "(none)"`，**实测不可达**：`[]` 非 nullish，`[].join()===""`） | `## Changed Files` | 0 |
| `(none)` | `:67` | `## Verification Steps` body | 0 |
| `Task completed successfully.` | `:68` | `## Exit Reason` 缺省 | 0 |
| `Task failed.` | `:70` | `## Exit Reason` 缺省 | 1 |
| `(no questions provided)` | `:72` | `## Questions` 缺省 | 2 |
| `Task was cancelled (exit 130).` | `:74` | `## Exit Reason` | 130 |

**B. `worker/worker-mode.ts`（按退出路径传入的 summary/exitReason/verificationSteps）**

| 常量原文 | 行号 | 出现在 section | 路径 |
|---|---|---|---|
| `(worker exited without writing output)` | `:876`（summary） | `## TL;DR` + `## Summary` | `process.on("exit")` 兜底 |
| `Process exited before output.md was written (crash or unexpected exit).` | `:877`（exitReason） | `## Exit Reason` | 同上（exit 1 分支） |
| `Task refused at startup (fail-closed).` | `:747` | `## TL;DR`/`## Summary` | 启动 fail-closed |
| `Task refused (image capability).` | `:828` | `## TL;DR`/`## Summary` | image-cap 拒绝 |
| `Worker timed out (idle\|wall).` | `:1148` | `## TL;DR`/`## Summary` | 看门狗 |
| `Task failed during output writing.` | `:1433` | `## TL;DR`/`## Summary` | settle 异常 |
| `Task completed.` | `:1339`（`buildSummary()` 无 assistant text 的 fallback） | `## TL;DR`/`## Summary` | 0 |
| `See task output for details.` | `:1360`（`verificationSteps`） | `## Verification Steps` | 0 |

合计 **15 个 distinct 占位/默认串**（`(none)` 出现两次，去重后 15）。

**读侧兜底文案（不是文件里的占位符，别混入谓词）**：`ui-bridge.ts:460` 的 `"no output.md"`；`ui-bridge.ts:467-469` 的 `"run lost: process gone..."`；`pm-orchestrator.ts:936` 的"无 output.md 摘要（worker 可能崩溃/超时）"。这些是**读取器找不到文件时的合成文案**，谓词必须用"文件缺失 ⇒ 非产物"分支，而不是把它们当占位符匹配。

### 3.5 "非占位"判定函数签名建议

```ts
// shared/output-sections.ts（新增；ui-bridge 与 worker-mode 共用，避免两侧占位符集漂移）

export interface OutputSectionBlock { section: string; body: string; start: number; }

/** 全部同名块，按出现顺序。 */
export function readOutputSections(content: string, section: string): OutputSectionBlock[];

/** section 特化的占位符判定：同一 body 在 TL;DR 下可能是产物、在 Exit Reason 下是默认语。 */
export function isPlaceholderSection(section: string, body: string): boolean;

/** 最后一个"非占位"块（按 sections 优先级取，空串/缺失 => undefined）。 */
export function readLastProductSection(taskDir: string, ...sections: string[]): string | undefined;

/** 一个 block 是否整体为占位（其 TL;DR 与 Summary 都是占位）——用于 §5 的"全占位则非交付"。 */
export function isPlaceholderBlock(block: string): boolean;

/** AC-006 谓词的纯输入版（worker settle 时在写 output.md 之前可调）。 */
export function evaluateReadOnlyDelivery(input: {
  kind: string;               // task.md type:（isReadOnly = !toolsForType(kind).includes("write")）
  reply: string;              // lastAssistantText（即将写成 ## Summary）
  existingOutput?: string;    // D-117 合并前已有的 output.md 内容
  artifacts: string[];        // collectArtifacts(taskDir)
  keyRoot: string;            // meta.trueAgenticdocRoot（evidence/** 存在性基准）
  startedAtMs?: number;       // run.json.started_at（无则退化为只判存在性）
}): { delivered: boolean; channel?: "report" | "artifacts" | "machine-line" | "inline-verify" | "referenced-evidence"; reason: string };

/** 文件版薄包装（读侧/测试/历史语料回放用）。 */
export function readDeliveredProduct(taskDir: string, kind: string): ReturnType<typeof evaluateReadOnlyDelivery>;
```

`isReadOnly` 判据必须复用 **`worker-mode.ts:57-95` 的 `TOOL_ALLOWLISTS` + `:100-102` `toolsForType`**（与 `:910` 的 `hasWriteTools` 完全同形），不得再开第二份角色表（spec §6 "不得引入第二真相源"）。`reportFileNonEmpty` 必须同时接受 `report.md` 与 `report-<slug>.md`（白名单 `worker/worker-file-tool.ts:41` `WORKER_FILE_NAME_RE`；而 `run-store.ts:121` 的 `collectArtifacts` 只认 `report.md`，两者口径不同——谓词以白名单为准，见 §6 风险 R3）。

---

## 4. settle 幂等：成因与守卫落点

### 4.1 现有守卫：`outputWritten` 是 **per-process**，且只管 exit 兜底

- 声明：`worker-mode.ts:856` `let outputWritten = false;`（局部于 `workerModeActivate` 一次调用 = 一个 worker 进程）。
- 写入点：`:832`（image-cap 拒绝）、`:1152`（timeoutExit）、`:1376`（finishSuccess）、`:1437`（settle 异常）。
- **唯一读取点**：`:870` `if (outputWritten) return;`——在 `process.on("exit")` 里（`:857`）。
- ⇒ `outputWritten` **不守卫 settle 路径**。`output-writer.ts:87` 注释"worker-mode guarantees one writeOutput call per process (outputWritten guard), so the merge cannot compound"是**对 settle 路径不成立的**（RQ-2 §4.1 已指出，本报告复核确认）。

### 4.2 "同进程二次 settle 追加第二块"的行号级成因

`pi.on("agent_settled")`（`worker-mode.ts:1379-1440`）**入口没有 `taskDone` 守卫**。`taskDone`（声明 `:1111`）只在 watchdog 定时器里被读（`:1224`/`:1233`/`:1246`/`:1305`）；`finishSuccess`（`:1350`）也**没有**入口守卫（`:1351 taskDone = true;` 只赋值不检查）。于是：

1. 第一次 settle：`initialSettled === false`（`:1382`）→ 置 `true`；**无 phase** ⇒ `finishSuccess()`（`:1392`，`return`）；**有 phase 且走完** ⇒ `:1423 finishSuccess()`。
2. `finishSuccess`：`:1354-1362 writeOutputGuarded({exitCode:0, ...})` → `output-writer.ts:89-95` 读到 `existing` 非空 → 走 `:95` 的 `${existing.trimEnd()}\n\n---\n\n${body}` ⇒ **追加第二块 harness**（含第二个 `## TL;DR`）。`:1364-1374` 的 RAG marker 有去重（`emitRagRequiredMissing` 的 `appendEvidenceOnce`/`markOutputRagUnused`），所以 `## RAG` 只有一次——**这正是 `rag-required.test.ts:323` 双 settle 却只断言 RAG 计数、不断言块数的原因**。
3. 第二次 settle：`initialSettled === true`；`phases` 为空（无 phase 任务）⇒ 直接 `:1423 finishSuccess()` 再走一遍（对 phased 任务，若已 `completedPhaseIdx === phases.length`，`:1421` 的 `if (nextPhaseIdx < phases.length)` 不成立，也落到 `:1423`）。`taskDone === true` **不阻止**它。
4. 第二次 `writeOutputGuarded`：`markOutcome(0)` 再置 `done`；`writeOutput` 再追加一块；`recordEnd(0)` 再写一条 `[END]`；`outputWritten = true` 再置。

⇒ **同进程二次 settle 的一条可执行复现**就是 `suite/rag-required.test.ts:323`（两次 `emit("agent_settled")`，行 `:332`/`:341`），今天它绿是因为只数 `RAG 未生效` 的出现次数，不数 `## TL;DR` 块数。

### 4.3 语料里的 9 段/3 段 = **跨 run**，不是同进程（本报告更正）

见 §0.3：`mwg-t11-g3-cli-doctor` blocks=9 / starts=9；`mwg-t16-docs-closure` blocks=3 / starts=3。**blocks 恒等于 starts** ⇒ 每段来自独立 spawn（跨 run 追加，`output-writer.ts:95` 的 D-117 合并是主因，spec §3.2 一致）。语料里**没有** blocks > starts 的目录，即同进程重复未在语料中留下可分离证据。

这条更正有两个直接后果：

1. **跨 run 多块不能在进程内消除**（每个新 run 合法地产生自己的块；D-117 的追加语义是 spec 明确要保留的）。读侧"取末个非占位块"（§3）是跨 run 多块的**唯一**解法。
2. **AC-010 ② 的"settle 幂等"只承诺进程内**（spec 字面："同进程二次 settle 不得追加第二块"），实现为进程内守卫即可；不要把"跨 run 只留一块"写进 AC（那会与 D-117 冲突）。

### 4.4 幂等守卫落点（写侧为主 + 读侧兜底）

**写侧（必须）**：

- **主守卫（per-process）**：`finishSuccess()` 入口（`worker-mode.ts:1350-1351`）改为
  ```ts
  function finishSuccess(): void {
    if (taskDone) return;      // AC-010②: same-process second settle is a no-op
    taskDone = true;
    ...
  ```
  以及 `pi.on("agent_settled")` 入口（`:1379-1380`）加同样的 `if (taskDone) return;`——这一层还顺带阻止"第二次 settle 重复写 phase 文件 / 重复 `appendGoalCheck` / `completedPhaseIdx` 越界"（`:1397-1420` 的 phase 分支在 `taskDone===false` 期间必须照常工作，故守卫只能判 `taskDone`，不能判 `initialSettled`）。
  - 已验证不误伤：`worker-tree-kill.test.ts:170`（AC-003）的第二次 settle 发生在 phased 任务**尚未 finishSuccess** 时（`taskDone===false`）⇒ 守卫放行，catch 路径照常触发。
- **加固（per-run，跨 re-entrant 写）**：`writeOutput`（`output-writer.ts:52-96`）在 `:89` 读到 `existing` 后，先判 `opts.runMarker && existing.includes(opts.runMarker)` ⇒ 本 run 已写过 harness 块，`return`（不改字节）。run marker 已由 `finishSuccess` 传 `runMarker(runState)`（`:1359`→`run-store.ts:113`），且是块内首行（`output-writer.ts:94`）。这条比 `taskDone` 更强：它对"同 run 的任何重复写"都幂等，且不会误伤 exit 兜底（兜底路径 `outputWritten` 已守卫）。
- **不做**：不改 `output-writer.ts:95` 的"空则覆写/非空则追加"（D-117 契约）；不清理历史块。

**读侧（必须，且与写侧互补）**：`readLastProductSection`（§3.3）保证即使是**历史**的 9 段文件、或写侧守卫上线前产生的 3 段文件，widget/详情仍给出真报告。spec §3.2 的表述正是"只补'读侧取末个非占位块' + 写侧幂等"，两者不是二选一。

**为什么不能只做读侧**：AC-010 ② 是写侧不变式（"settle 幂等"），只改读侧会让 `output.md` 继续无限增长、`readOutputBody`（PM 回读整文件，`pm-orchestrator.ts:922`）把占位块一起灌进 PM 上下文；**为什么不能只做写侧**：历史 10/27 目录已经是多块，写侧守卫只能阻止新增。

---

## 5. 28 条回归面重锚表（新口径）

口径：row = `packages/coding-agent/test/**` 中断言 `exitReason`/`changedFiles`/`## Changed Files`/`## TL;DR`/`output.md` 形态/`readOutputSection`/`readTerminalDetail`/`run.json.artifacts`/`hasProductEvidence` 的测试用例。全部行号本报告现读复核，与 RQ-2 §5 的 28 行一致（脏树未漂）。"必须同步改" = 按新口径必须改断言或调用签名；其余是"不该被误伤"的护栏（护栏行另需**新增反向用例**，见备注）。

| # | 测试 文件:行号 | 现断言 | 新口径下的期望断言 | 必须同步改 |
|---|---|---|---|---|
| 1 | `test/extensions/agent-team-loop-output.test.ts:75` | exit 0/1/2 的 `## TL;DR` 恒为首段、`## Summary` 逐字；fixture 传 `changedFiles:["src/a.ts"]`（`:85`） | TL;DR 顺序/Summary 逐字**不变**；若 AC-007 把选项 `changedFiles` 改名 `deliverables`，本行 fixture 须改（编译期红）；追加：exit-2 块 = NC 自报格式 | 是（仅当重命名选项） |
| 2 | `...output.test.ts:102` | TL;DR ≤100 字符、无 markdown 前缀 | 不变（`headline()` 不动） | 否 |
| 3 | `...output.test.ts:121` | 空 summary ⇒ `(no conclusion)`；`:127` `readOutputSummary` = `(no summary)` | **不变**（这是 `readOutputSummary` 保持首匹配/原文的契约；AC-010 不得经它做"末个非占位"） | 否 |
| 4 | `test/extensions/agent-team-loop.test.ts:389` | exit 0 写四段，含 `## Changed Files`（`:398 changedFiles:["x.ts"]`，`:403` 断言段名） | 有 artifacts ⇒ `## Deliverables`（排除 `output.md`/`progress.md`）；无 artifacts ⇒ **整段省略**；`(none)` 分支删除 | **是** |
| 5 | `...test.ts:410` | exit 1 写 `## Exit Reason` | 不变 | 否 |
| 6 | `...test.ts:419` | exit 2 写 `## Questions` | 不变；追加：框架改判 NC 也走 exit 2 + `## Questions`（正文为 reason，非 `(no questions provided)`） | 否（新增） |
| 7 | `...test.ts:428` | exit 130 仍写文件 | 不变 | 否 |
| 8 | `...test.ts:437` | D-117 合并：agent body 在 `---` 上、harness 在下（`:457` 断言 `\n---\n\n## TL;DR`） | 不变（D-117 保留） | 否 |
| 9 | `...test.ts:465` | 空白-only 文件 ⇒ harness-only、不含 `---\n\n## TL;DR` | 不变 | 否 |
| 10 | `...test.ts:2621` | `readOutputSection` **首匹配** + 缺文件 undefined | `readOutputSection` 保持首匹配（契约冻结）；**新增兄弟用例**断言 `readLastProductSection` 在"首块占位+末块真报告"下返回末块 | 是（新增，既有断言不放宽） |
| 11 | `...test.ts:2694` | done 详情 = 首个 `## TL;DR` ?? Summary 首行 | done 详情 = **末个非占位** `## TL;DR`/`## Summary`；单块 fixture 字符串逐字不变 | 是（新增多块用例） |
| 12 | `...test.ts:2713` | `renderWatchLines` 接线 `readTerminalDetail` | 不变 | 否 |
| 13 | `test/extensions/agent-team-loop-image-cap.test.ts:118` | 拒绝路径 output.md **不得**含崩溃占位符（`:149`） | 不变（护栏：AC-006 不得在拒绝路径写占位符/NC） | 否 |
| 14 | `test/extensions/agent-team-loop-worker-tree-kill.test.ts:205` | exit 兜底**必须**写 `(worker exited without writing output)`（`:224`） | 不变（护栏：AC-006 不得抑制兜底占位） | 否 |
| 15 | `test/suite/worker-run-identity.test.ts:77` | spawn 即写 run.json `running` + pid/heartbeat | 不变 | 否 |
| 16 | `...run-identity.test.ts:98` | 干净 settle（`type: coding`）⇒ `status=done`、`exit=0`、`artifacts` 含 `output.md`、marker `status=done`（`:110-113`） | 不变（编码角色不受 AC-006 影响）；**新增** read-only 无产物兄弟用例 ⇒ `status=needs-clarification`、`exit=2`、marker `status=needs-clarification` | 否（新增） |
| 17 | `...run-identity.test.ts:116` | D-117：agent 机器行仍首行、marker 在 `---` 后 | 不变 | 否 |
| 18 | `test/suite/run-store.test.ts:143` | `collectArtifacts` 排序等值 `["output.md","phase-1-impl.md","progress.md"]`（`:149`） | **不变**（护栏：AC-007 不得扩 `collectArtifacts`；过滤 `output.md`/`progress.md` 在 writer 侧做） | 否 |
| 19 | `test/suite/rag-required.test.ts:323` | 二次 settle 后 `RAG 未生效` 恰 1 次、`## RAG` 存在（`:334-343`） | 不变；**追加**块数断言：二次 settle 后 `## TL;DR` 恰 1 块（锁 AC-010②） | 是（新增断言） |
| 20 | `test/suite/autopilot-protocol.test.ts:272` | 未注册 conductor type：exit 1 + 理由落 output.md（`:279`） | 不变（拒绝路径仍是 `failed`，AC-006 不覆盖） | 否 |
| 21 | `...autopilot-protocol.test.ts:294` | `type: fallback` 同样 fail-closed（`:300`） | 不变 | 否 |
| 22 | `...autopilot-protocol.test.ts:310` | 无/空 `read_scope` 的 verifier fail-closed（`:318`/`:332`） | 不变 | 否 |
| 23 | `test/suite/worker-dispatch-guard.test.ts:240` | 空队列 + `output.md`（内容 `"already ran\n"`）⇒ `queue-unreadable` + 零行；只有 `task.md` ⇒ 正常派发（helper `:57-64`） | **不变**（`hasProductEvidence` 保持 run-occurrence 语义，§1）；**新增判别用例**：`trace.log`-only 与占位块-only 仍拒绝 | 否（新增判别用例） |
| 24 | `...worker-dispatch-guard.test.ts:297` | 自身 run 终态 ⇒ 拒绝派发（AC-022） | 不变 | 否 |
| 25 | `...worker-dispatch-guard.test.ts:319` | 活 run ⇒ 拒绝（无第二写者） | 不变 | 否 |
| 26 | `...worker-dispatch-guard.test.ts:449` | 终态 run 不再入队且给理由（保留队列行） | 不变 | 否 |
| 27 | `...worker-dispatch-guard.test.ts:496` | `supersedes` 替换放行、旧目录不动 | 不变 | 否 |
| 28 | `test/suite/dual-root-worker.test.ts:115`（+ `test/suite/cross-drive-worker.test.ts:210`） | settle 后 `output.md` 必须存在，且只落 control root | 不变（护栏：AC-006 不得在崩坏/拒绝/NC 路径停止写 `output.md`） | 否 |

**必须同步改（写侧口径）**：**#4**（段名/选项）、**#10/#11**（新增读块用例，既有断言不放宽）、**#19**（新增块数断言）。**护栏但需新增反向对照**：**#13/#14**（占位符语义不得反转）、**#20-#22**（拒绝路径不得被 NC 覆盖）、**#18**（`collectArtifacts` 不扩）、**#16/#28**（编码/双根写入不受影响）。**#23** 是本键最容易误改的一行：**必须保持绿**，其判别由新增的 `trace.log`-only / 占位块-only 用例承担。

**Python 侧回归面（不在 28 行内，但受 §2.4 影响）**：`test_launcher.py:735`（`_exit_to_status` 映射表，含 `(2,"needs-clarification")`）、`test_launcher.py:1265-1390`（run.json reconcile 阶梯，`needs-clarification` 保留用例在 `:1312-1322`）、`test_run_identity.py`（`mark_run_lost`，`:19` 的 `TS_TERMINAL_STATUSES` 与 TS 对锁）。reap 改 product-first 后：`test_integration.py:250`（exit 2 ⇒ NC）不变；需**新增** reap 用例：run.json=`needs-clarification` + 进程 exit 0 ⇒ 队列行 NC（反向：无 run.json + exit 0 ⇒ done）。

---

## 6. 反向用例设计（≥5；每条含"命中"与"不得误伤"两侧）

放置建议：TS 侧 `test/suite/`（用 `harness.ts` + faux provider，禁止真实 provider）；谓词纯函数级用例放 `test/suite/worker-delivery-product.test.ts`（新）；读侧放 `test/extensions/agent-team-loop.test.ts`（接 #10/#11）；Python 侧放 `test_launcher.py`。

### T1 通道①：`report.md` 非空 ⇒ delivered
- 正：`type: research`，settle 前用 `worker_file file="report.md"` 写 100 B ⇒ `run.json.status="done"`、`exit=0`、marker `status=done`、零 `no-product` 行。
- 反（控制）：同任务不写 `report.md`、reply 为 `"Let me organize my work:"`、不引用任何 `evidence/**` ⇒ `needs-clarification` + alarm。**同 run 两分支只差一个文件**，锁死"通道①是判据不是巧合"。
- 变体：`report-<slug>.md`（`report-final.md`）也必须算（白名单 `worker-file-tool.ts:41`；`collectArtifacts` `run-store.ts:121` **不认**它 ⇒ 谓词必须独立于 artifacts，见风险 R3）。

### T2 通道②：机器行 / 内联 `[VERIFY]` ⇒ delivered
- 正：reply 含内联 `… 见 [VERIFY] VC-1: x=1 …`（**非行首**，复现语料 `mgh-rq1-l3-abort` 形态）⇒ delivered。
- 正（行首）：`output.md` 首行 `[VERIFY] VC-001: …` 或 `VERDICT=pass` ⇒ delivered。
- 反：reply 含 `[VERIFY]` **但** TL;DR/Summary 全为占位块（`(worker exited without writing output)`）⇒ **NC**（谓词要求"非占位块 ∧ 机器行"同时成立；这条锁死"占位符-only 不是产物"）。

### T3 通道③：引用 `evidence/**.md` 实存 ⇒ delivered
- 正：reply 内联 `evidence/research/spec-x-20261010.md`，文件实存且 `mtime >= run.started_at` ⇒ delivered。
- 反（事故复现）：reply 引用 `evidence/quality-gate-report-review-20261010.md`，**文件不存在** ⇒ **NC + alarm**（`mwg-qg-review-20261010` 形状）。
- 反（防伪造）：引用的是**本 worker 目录内**的文件（`workers/<task>/report.md`）⇒ 不算通道③（通道③只认 key root 下、非本目录的 `evidence/**`）；引用一个**只读过**的既有路径时，`mtime < run.started_at` ⇒ 不算。

### T4 全不命中 ⇒ NC + alarm + 队列行 NC（权责端到端）
- 正：只读 run，settle 时三通道全不命中 ⇒ ① `run.json.status="needs-clarification"`、`exit=2`；② `output.md` marker `status=needs-clarification` 且 `## Questions` 正文为 reason（非 `(no questions provided)`）；③ `.agenticdoc/_autopilot/auto-decisions.jsonl` 追加一行 `{phase:"dispatch-alarm", kind:"no-product", count:1, detail:"<task_key>"}`（**恰好一行**）；④ 模拟 launcher reap：run.json=NC + 进程 exit 0 ⇒ `_workers.parallel` 行 = `needs-clarification`。
- 反（零回填）：无 `run.json` + 进程 exit 0 ⇒ 队列行 `done`（历史行为逐字不变）；无 `run.json` + exit 1 ⇒ `failed`。
- 反（不得静默 done）：任何路径下只读 run 无产物都不得出现 `status=done`（探针 = 断言 run.json 与队列行都不是 done）。

### T5 首块占位 + 末块真报告 ⇒ 读侧给真报告
- fixture：`output.md` = 8 个崩溃占位块 + 末块 `## TL;DR\n\nPASS — T-11 done\n\n## Summary\n\n…`（`mwg-t11` 形状）。
- 断言：`readTerminalDetail(dir, "done") === "PASS — T-11 done"`；`readLastProductSection(dir,"TL;DR","Summary")` 返回末块；`readOutputSection(dir,"TL;DR")` **仍返回首块占位符**（首匹配契约冻结，锁 #10）。
- 反：9/9 块全是占位符 ⇒ `readLastProductSection` 返回 `undefined`（widget 走空 detail，不回退展示占位符）；同一 fixture 下模板谓词 ⇒ NC。
- 反（单块不变）：单块正常文件 ⇒ 详情字符串与今天逐字相同。

### T6 编码角色不受影响
- `type: coding`（`toolsForType("coding").includes("write") === true`，`worker-mode.ts:58/100-102`）干净 settle、`output.md` 只有 harness 段 ⇒ `status="done"`、`exit=0`、零 `no-product` 行、`## Changed Files` 按 AC-007 省略（不伪造改动列表）。
- 反：`type: review`（`toolsForType("review")` 无 `write`）同输入 ⇒ NC。同一输入两 type 结果相反 ⇒ 锁死"角色筛选来自 `TOOL_ALLOWLISTS` 单一真相源"。

### T7 `exitCode=2` 的既有 NC 路径不变（self-report 不被覆盖）
- `writeOutput({exitCode:2, questions:"Which DB?"})` ⇒ 文件含 `## Questions\n\nWhich DB?`（`agent-team-loop.test.ts:419` 现状不变）；`launcher._exit_to_status(2) === "needs-clarification"`（`launcher.py:372`，`test_launcher.py:735` 现状不变）。
- 反（不重复判定/不互相覆盖）：worker 已自报 exit 2 时，框架判定**不得**把它改成 done；框架改判 NC 时也**不得**写第二块（T8）。实现上靠"单点判定在 `finishSuccess` + 失败/拒绝路径不进 `finishSuccess`"（§2.3）。

### T8 幂等与拒绝路径护栏（AC-010② + 不得误伤）
- 幂等：同一 `agent_settled` 连发两次（`rag-required.test.ts:323` 同款）⇒ `output.md` 中 `## TL;DR` **恰 1 块**、`## RAG` 恰 1 次、`[END]` 恰 1 条、`no-product` 行恰 1 条（若该 run 是 NC）。
- 反（兜底保留）：`process.on("exit")` 硬崩溃兜底仍写 `(worker exited without writing output)`（`worker-tree-kill.test.ts:224` 不变）。
- 反（拒绝路径保留）：image-cap 拒绝（`agent-team-loop-image-cap.test.ts:149`）、启动 fail-closed、verifier 缺 `read_scope` ⇒ `output.md` 仍只含拒绝理由，**不得**被 crash 占位符或 NC 文案覆盖；`status` 仍 `failed`。
- 反（双根保留）：`dual-root-worker.test.ts:115`/`cross-drive-worker.test.ts:210` 的 `output.md` 仍落在 control root。

### 风险清单（谓词实现时必须处理）
- **R1 `referencedDeliverableExists` 可被"只读过就引用"假过**：缓解 = 只认 key root 下、非本 worker 目录的 `evidence/**.md`，并加 `mtime >= run.json.started_at`（无 run.json 时退化为存在性 + 路径前缀）。语料三个合规例的引用都在 `evidence/research/`；事故例引用不存在 ⇒ 仍 NC。
- **R2 内联 `[VERIFY]` 可能只是抄任务书措辞**：缓解 = 置于 artifacts/referenced-evidence 之后作二级通道，且必须与"存在非占位块"同时成立。
- **R3 `report-<slug>.md` 与 `collectArtifacts` 口径不一致**：白名单 `worker-file-tool.ts:41` 允许它，但 `run-store.ts:121` 只收 `report.md` ⇒ 谓词必须以白名单为准，artifacts 通道只作前向辅助。本键语料 `report-*.md` = 0（前向风险）。
- **R4 必须扫全部块（占位符-only 判据用 all，不用 first/last）**：`mwg-t11` 8/9 块是占位符但整体 delivered；`mwg-rq2`/`mwg-t16` 首块占位末块真。规则 = "存在任一非占位块 ∧ 至少一条交付信号 ⇒ delivered"，而非"全部块非占位"。
- **R5 NC 不得动摇既有输出契约**：不得抑制 exit 兜底占位（#14）、不得覆盖拒绝路径 output.md（#13、#20-#22）、不得改 `finishRun`/`collectArtifacts` 口径（#16、#18）、不得让二次 settle 变成不追加（#19 的 RAG 计数）。

---

[VERIFY] DRQ2: readers=4 callers=8 placeholders=15 parity_tests=6 regression_rows=28 verdict=READY(settle=worker/finishSuccess+exit2; reads=shared readLastProductSection via readTerminalDetail; ownership=worker writes run.json terminal, launcher propagates to queue row, PM never writes terminal rows)


---

## PM 现场复核（2026-10-10 22:05，`mw-dispatch-settle-gates` PM）

正文逐字收录；关键点确认（AC-009）。

| worker 结论 | PM 复核 |
|---|---|
| 结算判定落点 = `worker-mode.ts::finishSuccess()` `:1350`，`writeOutputGuarded` `:1354` 之前，结果折进 `exitCode`（delivered ? 0 : 2） | **采纳**（四者自洽：output.md marker / `## Questions` / `run.json.status` / `[END] exit=`；失败/超时/拒绝路径不经 `finishSuccess` ⇒ 无重复判定） |
| 配套：`markOutcome` `:786` 加 `2 → needs-clarification`；`recordEnd` `:1075` 放宽 `0\|1\|2` | **采纳** |
| TS 目前**无** `exitCode=2` 生产者 ⇒ AC-006 是第一个；`RUN_TERMINAL_STATUSES` 已含 NC ⇒ 不改终态集 | **采纳** |
| alarm 走 `pm-orchestrator.ts:439 recordDispatchAlarm`，`kind` 值域 `:387-397` 加 `"no-product"`、`describeDispatchAlarm` `:409-435`；**必须用 `meta.trueAgenticdocRoot`**（`agenticdocRoot` 是 `<key>/workers`） | **采纳**（这是一个真实的容易踩的坑） |
| 读侧**不改** `readOutputSection`/`readOutputSummary`；新增 `shared/output-sections.ts`（`readOutputSections`/`isPlaceholderSection`/`readLastProductSection`），只切 `readTerminalDetail` 的 4 处读点 `ui-bridge.ts:457/460/464/470` | **采纳**（首匹配契约被既有测试钉住，硬改会破坏 `/mw` 命令面） |
| **权责**：队列行终态由 launcher reap 写（`launcher.py:838-844`），worker 只写 `run.json` 终态 + `pending` 行 ⇒ AC-006 判定在 TS worker 侧产生，launcher reap 改 **product-first**（先读 run 状态，退出码仅 fallback），Python 不判产物内容，PM 永不写终态行 | **采纳为 AC-006 的实现约束** |
| **收窄 `hasProductEvidence` 会削弱 IN-3 守卫**（`trace.log`-only / 占位块-only 会从"拒绝扫描"翻成"重跑历史"）⇒ 必须**并存而非替换** | **采纳**（写成 AC-006 的硬约束；这正是一年前那次事故的守卫，不能为了新判据削弱它） |
| §4 更正：语料 `blocks == starts`（T-11 9=9、T-16 3=3）⇒ 多块主因是**跨 run 追加**，同进程二次 settle 为代码层真实但语料不可分离的第二成因 | **采纳**（PM 复现：多段 `## TL;DR` 目录 10 个，最多 9 段） |
| §5 28 条重锚表：必须同步改 #4、#10/#11、#19；**#23 必须保持绿** | **采纳** |
