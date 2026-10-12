# SPEC 阶段调研 RQ-5（G5）：`_workers.parallel` 被整体重建、已 acked 终态任务被重跑的根因锚定

> 本卡为**只读**调研：未改任何代码，唯一写面 = 本文件。
> 行号以本卡执行时刻的工作树为准（HEAD `10446aefb`，`git rev-parse --short HEAD` 实测）。
> 口径：「实测」= 本机当场测出并记下命令；「推断」= 由实测约束推出的结论，必须显式标注。
> 时间：UTC。本机时区 UTC+8（`2026-10-09T12:01:47Z` = 本地 20:01:47）。

---

## 0. 结论速览

| 项 | 结论 | 置信度 |
|---|---|---|
| 谁重建 | **不是 launcher**。是 **PM 窗口的 `agent_settled` 扫描** `dispatchNewTasks` 把磁盘上每个 task 目录重新 upsert 成 `pending`，并**整文件重写** `_workers.parallel`（`pm-orchestrator.ts:393/428/462-476` → `task-dispatcher.ts:284-296` → `worker-store.ts:123-139`） | 高（实测 + 唯一写者 grep） |
| 「registered_at」是什么 | 实际是第 6 列 **`dispatched_at`**（TS `dispatchedAt`），由 `new Date().toISOString()` 逐任务取（`task-dispatcher.ts:289-292`）。全部行同一时刻 = 一次扫描循环逐行写 | 高 |
| 重排判据 | 只有一条：**该 task 目录名是否已是队列行的 `task_key`**（`pm-orchestrator.ts:402` + `:428`）。**不看 status、不看终态、不看结果文件、不看 `_workers.acked`**（ack 在本路径 0 命中） | 高 |
| 根因（决定性） | **两代 bundle 的 worker-store 行解析器不兼容**：旧产物只接受 7/8 列（`WORKER_COLS = 8`），把 **9 列行整行丢弃**；新产物接受 7/8/9 列。旧解析器 `readAll()` 返回 `[]` ⇒ `dispatched` 空 ⇒ **磁盘上全部任务被重排**；旧序列化器再把整文件写回 8 列 | 高（产物级实测 + 现场列数指纹） |
| 触发者 | 进程自启动时缓存扩展工厂（`loader.ts:146-167/407-439`）⇒ **长驻窗口持有旧解析器**。实测：`2026-09-24` 那个窗口（单 `session` 头、进程常驻）在 `2026-10-09T12:01:47.501Z` 与 `2026-10-10T02:50:05.214Z` 各结束一个 turn，两次紧随其后就是全量重排 | 高 |
| acked 是否参与 | **完全不参与**。Python 侧对 `_workers.acked` 0 命中；TS 侧 ack 只在面板/ack 工具读写，不参与派发判据 | 高（grep 实测） |
| 缺口性质 | 修复点唯一咽喉 = `pm-orchestrator.ts:428` 的 skip 判据（grep 唯一），其次是写侧 `WorkerStore.upsert`（拒绝把终态行降级为 pending） | 高 |

**一句话**：不是「launcher 重启重排了任务」，而是「**一个加载了旧版 worker-store 的长驻 PM 窗口，把 9 列的队列文件读成了空队列，于是把磁盘上每个 task 目录都当成未派发任务重新入队**」。已 acked 与否无关——它们只是「磁盘上有目录、且读不到对应行」。

---

## 1. 调研方法与出处

1. 全文读 `packages/multi-workers/{launcher.py,mw_common.py}`（`_workers` 全部写点）、`autopilot/{dispatch,conductor,state}.py`（另两条 Python 写者）。
2. 全文读 `packages/coding-agent/src/extensions/agent-team-loop/{shared/worker-store.ts,shared/ack-store.ts,shared/file-lock.ts,pm/task-dispatcher.ts,pm/pm-orchestrator.ts,pm/ui-bridge.ts,autopilot/monitor.ts,shared/paths.ts}`。
3. 宿主侧：`packages/coding-agent/src/core/extensions/loader.ts`（扩展工厂缓存语义）。
4. 产物级：`git show <rev>:packages/multi-workers/dist/extensions/agent-team-loop.js`（旧/新两代 bundle 的解析器规则）、`git show HEAD:packages/coding-agent/dist/extensions/agent-team-loop/shared/worker-store.js`。
5. 只读现场证据：`.agenticdoc/_workers.parallel`（列数/时间戳/顺序快照，取两次）、`.agenticdoc/_workers.acked`、`.agenticdoc/**/workers/*/{trace.log,worker.log}`（`[START]`/`[END]` 全量抽取）、`.mw/{mw.log,launcher.log,launcher-beat.*}`、`git log/status/show`。
6. 会话证据：`<pi-agent-root>\sessions\--H--git-Multi-Workers--\*.jsonl`（1102 个文件的按名/按 mtime 过滤 + 定点全文检索；`2026-09-24T11-21-05-539Z_01a0d325-...jsonl`、`2026-10-09T07-58-49-436Z_01a11fac-...jsonl` 为两个长驻 PM 窗口）。
7. 机械复核：用 node 直接跑面板同一条读路径（`_workers.parallel` 逐行 7..9 列判定），实测当前文件 `parsed_rows=252 unparsed_nonblank=0`。
8. 复算命令见 §5；全部数值均出自本机实测。

---

## 2. 发现（F1..F12，均带 `文件:行号`）

### F1 `_workers.parallel` 的全部写者（Python 侧 3 条 + TS 侧 1 条），没有任何一条是 launcher 启动时「重建」

**Python（唯一整文件写函数 `mw_common._write_workers_file`）**

| 位置 | 作用 | 是否整体重写 | 行集合如何产生 |
|---|---|---|---|
| `mw_common.py:1554-1555` | `workers_path()` = `<project>/.agenticdoc/_workers.parallel` | — | — |
| `mw_common.py:1566-1597` | `parse_workers_file()`：`len(parts) in (7,8,9)`，否则**整行跳过** | — | — |
| `mw_common.py:1599-1622` | `serialize_entry()`：8 列固定 + `origin` **仅在非空时**追加 | — | — |
| `mw_common.py:1704-1710` | `_write_workers_file()`：`tmp` 写入 + `Path.replace`（原子，不截断） | 是 | 调用方传入 |
| `mw_common.py:1712-1727` | `update_status()`：读全部行 → 改一行 status/updated_at → 写回 | **是（行集合=读到的全部行）** | `parse_workers_file()` |
| `mw_common.py:1729-1761` | `archive_stale_entries()`：只把「status 非终态 **且** task.md 不存在」的行移入 `_workers.stale.parallel` | 是 | 同上，**条件极窄** |
| `autopilot/dispatch.py:592-633` | conductor 派发：追加/替换一行（`origin: conductor`） | 是 | 已有行 + 新行 |
| `autopilot/conductor.py:4816-4850` | `reconcile_orphans()`：**只追加**缺失的 conductor 孤儿行（`"a"` 模式） | 否 | — |

**TS（`WorkerStore`，唯一的整文件重写者）**

- `worker-store.ts:112-115` 构造：`filePath = <agenticdocRoot>/_workers.parallel`，`lockPath = <agenticdocRoot>/../.mw/workers.lock`。
- `worker-store.ts:117-121` `readAll()`：`existsSync` → 按 `\n` 切 → `parseWorkerLine` → 过滤。
- `worker-store.ts:123-139` `upsert()`：**读全部行 → 替换同 key 或追加 → `existing.map(serializeWorkerLine).join("\n")` → tmp + `renameSync`**（整文件重写；顺序=读到的顺序+追加）。
- `worker-store.ts:91-105` `serializeWorkerLine()`：**恒定 9 列**（`origin` 总是输出，缺失归一为 `manual`）。
- `worker-store.ts:73` `parseWorkerLine()`：`parts.length < 7 || > 9 → return undefined`（**整行丢弃，不报错**）。
- 调用 `upsert` 的**全部**位置（grep 唯一，3 处）：`pm/pm-orchestrator.ts:464`（扫描循环）、`pm/ui-bridge.ts:1345`（`dispatch_worker` 工具）、`pm/ui-bridge.ts:1742`（`/worker` 命令）。前两者经 `task-dispatcher.ts:284-296`。

**launcher 侧（`launcher.py`）没有重建路径**：`_poll_once` 每轮只做四件事——写自己的 beat（`:775-790`）、`archive_stale_entries`（`:788`）、reap→`_update_status`（`:796-817`）、`_reconcile_orphans`（`:816`）、按 `status == "pending"` 发现并 spawn（`:819-836`）。它**从不创建行、从不改 key 集合**，只改一行的 status/updated_at（`update_status` 转调 `_write_workers_file`，行集合来自读到的全部行）。spawn 判据只有 `entry["status"] != "pending" → continue`（`launcher.py:817-818`）+ `key in running_procs`（`:819-820`，AC-008 去重）。

**结论**：`_workers.parallel` 的行集合只有两个来源会「凭空出现」——(a) TS 扫描把磁盘 task 目录入队（F2），(b) conductor 孤儿补行（`conductor.py:4816-4850`，只补 conductor 行）。本仓库当前**没有 conductor 在跑**（`.agenticdoc/*/.autopilot/` 不存在、无 `timeline.jsonl`、`.mw/conductor.log` 0 字节），故 (a)。

### F2 「启动时重建」的真实路径 = `agent_settled` 扫描 `dispatchNewTasks`，逐行如下

`pm/pm-orchestrator.ts`：

| 行 | 代码语义 |
|---|---|
| `:739-746` | `pi.on("agent_settled", () => dispatchNewTasks(workerStore, agenticdocRoot, {...}).catch(() => {}))` —— **每个 agent turn 结束都扫描一次**（不是启动时，也不是定时器） |
| `:393-395` | 函数入口；`agenticdocRoot` 来自 `pmActivate` 的 `projectDir = process.cwd()`（`:664` → `paths.ts` `agenticdocRoot() = path.join(projectDir, ".agenticdoc")`） |
| `:402` | **`const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey))`** ← 唯一的「已派发集合」 |
| `:406-425` | 遍历 `<agenticdocRoot>/*/workers/*/task.md`（`readdirSync`；跳过 `.` 前缀目录） |
| `:428` | **`if (dispatched.has(taskKey)) continue;`** ← 唯一 skip 判据 |
| `:429-431` | `task.md` 不存在 → 跳过 |
| `:435` | `if (isConductorTask(taskMdPath)) continue;`（`origin: conductor` 任务留给 conductor；`:359-379`） |
| `:436-455` | docs gate（phase 分级）；命中则整 key `continue`（**只抑制，不排**） |
| `:462-476` | `await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath }, workerStore)` |
| `pm/task-dispatcher.ts:284-296` | `injectWorkspaceProfile()` → `const now = new Date().toISOString()` → `{ ...entry, dispatchedAt: now, updatedAt: now }` → `store.upsert(full)` |
| `shared/worker-store.ts:123-139` | 整文件重写（9 列） |

**因此「启动时重建」这条路径逐行讲清 = F2 表中 `:402 → :428 → :462-476 → task-dispatcher:289-296 → worker-store:123-139`。** 触发它的不是 launcher 启动，而是**任何一个加载了该扩展的 PM 窗口结束一个 turn**；`agent_settled` 在会话首轮之后即会触发，因此「窗口刚恢复/刚跑完一轮」在观感上等价于「重启后重建」。

### F3 判据里没有任何「终态 / acked / 结果文件」分支（grep 为负证据）

- `rg -n "acked" packages/multi-workers -g '*.py'` → **0 命中**（`_workers.acked` 在 Python 侧完全不存在）。
- `dispatchNewTasks` 全文（`:393-478`）**不出现** `status`、`isTerminal`、`acked`、`AckStore`、`output.md`、`[END]` 任一符号；`:428` 只看 key 集合。
- `AckStore` 的全部读点：`ui-bridge.ts:463`（`/mw ack all` 展开）、`:526`（`renderWatchLines` 面板）、`:1424`（`list_tasks` 工具）；构造点 `pm-orchestrator.ts:665`。写点唯一：`shared/ack-store.ts:42-68`（经 `ui-bridge.ts:495`、`:468`）。
- 因此：**一个任务即使 `done` + 已 acked + 有 output.md + trace.log 有 `[END]`，只要它的 taskKey 不在 `readAll()` 的返回里，就会被重新入队并重跑。**（本轮 7 个 mgh 任务、以及其它 key 的数百个终态任务，就是这样被重跑的。）

### F4 行格式、列语义、终态集合（含第 6 列真名）

**格式（两侧锁定一致）**：`mw_common.py:1566-1596`（Python 读）/`worker-store.ts:24-33`（TS 读注释）：

```
task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin
   1         2        3       4           5              6             7         8       9
```

- 兼容 7 列（无 model）、8 列（无 origin）、9 列（当前）；`parse_workers_file` 与 `parseWorkerLine` 都是「列数不合规 → **静默丢行**」（`mw_common.py:1583-1584`、`worker-store.ts:73`）。
- 第 6 列 = **`dispatched_at`**（TS 字段 `dispatchedAt`，`worker-store.ts:19`）；**任务里说的「registered_at」就是它**，格式 `2026-10-09T12:01:47.506Z`（`Date.toISOString()`）。第 7 列由 Python `iso_now()` 写，形如 `2026-10-09T12:11:37+00:00`（无毫秒）——两种后缀并存正是「TS 建行、Python 更新」的指纹。
- `origin` 列：Python **仅非空时输出**（`mw_common.py:1616-1621`），TS **恒定输出**（`worker-store.ts:91-105`）。⇒ **列数本身可当写者指纹用**（见 F6）。

**status 取值集合与终态**：

- 全集：`pending | running | done | failed | needs-clarification`（`worker-store.ts:5`）。
- 终态：`{done, failed, needs-clarification}`（三处同义：`mw_common.py:162` 与 `:1854`、`pm-orchestrator.ts:50`、`ui-bridge.ts:439`）。
- 非终态：`pending`、`running`；`archive_stale_entries()` 只对非终态 + task.md 缺失行生效（`mw_common.py:1745-1748`）。
- status 写入者：`pending` 只有扫描/派发（F2）；`running` 只有 `launcher.py:975`（spawn 成功）；终态只有 `launcher.py:367-373` `_exit_to_status()`（0→done / 2→needs-clarification / 其他→failed）与 `launcher.py:801/833`。

**被重建出来的行与既有行在列上是否一致？** 实测**不一致，而且这是关键证据**：本轮重排（`2026-10-10T02:50:05Z`）之后，全文件 252 行**全部是 8 列**（`task_key..model`，origin 整列消失）；重排之前同一文件 250 行**全部是 9 列**（每行以 `| manual` 结尾）。详见 F6。

### F5 TS/extension 侧对「重启后重排/重跑」的假设

- `pm/pm-orchestrator.ts:369-371` 的注释**明确**把「launcher restart」列为要关闭的重排通道之一 → **该注释被 F1/F9 实测证伪**：launcher 重启不重排，真正的通道是「队列读空」。
- `pm/pm-orchestrator.ts:532-538`：窗口打开时把已终态行塞进 `notified` 基线（历史不重播）。重排把行从 `done`→`pending`→`running`→`done`，但 key 已在 `notified` 里 ⇒ **同一窗口不会二次回读**；新窗口才会。⇒ 重排对「提醒面」的可见性取决于窗口生命周期（与 G2/G4 相关，见 F12）。
- `monitor.ts:351-361`：面板只取 `status === "running"` 的行，`elapsedMs = now - Date.parse(dispatchedAt)`，**不可解析则整行丢弃**。⇒ 重排刷新 `dispatchedAt` 会让所有行「从头计时」（本轮实测：02:50 起 70 行 0 分钟）。
- `pm/ui-bridge.ts:606-615`：`newestFirst` 按 `updatedAt` 排序；`history = status==="done" ∪ acked`，`live = running ∪ pending`，且 **live 段永不折叠**（`:612`）。⇒ 一次 250 行重排会把 250 行从 history 拽进 live（`pending`），面板瞬间被填满。
- `pm/pm-orchestrator.ts:259-330` `restoreWatch()`：只恢复「本窗口 watch 的 key + claim」，**不做任何重排/重派**。
- `shared/ack-store.ts:26-68`：ack 读写只依赖 key + 自己的时间戳，**不依赖行序、不依赖 `dispatched_at`**。
- 未发现任何代码依赖「行序」；依赖 `dispatched_at` 的只有 `monitor.ts:357`（elapsed）与 `pm-orchestrator.ts:514`（终态时长回退链）。
### F6 **根因（决定性）：两代 bundle 的 worker-store 解析器不兼容 → 9 列队列被旧解析器读成空队列**

**(a) 旧产物只接受 7/8 列** —— `git show aafaa378b:packages/multi-workers/dist/extensions/agent-team-loop.js`：

```
20788: var WORKER_COLS = 8;
20791: if (parts.length !== WORKER_COLS && parts.length !== WORKER_COLS - 1) return void 0;
```

（源码同形：`git show aafaa378b:.../shared/worker-store.ts:19,24`。）⇒ **9 列行 = 无法解析 = 整行丢弃 = `readAll()` 返回 `[]`。**

**(b) 新产物接受 7/8/9 列** —— `worker-store.ts:32-33`（`WORKER_COLS_MIN = 7 / MAX = 9`）、`:73`；产物 `packages/multi-workers/dist/extensions/agent-team-loop.js:20980,20997`（HEAD 版本，本机实测行号）。

**(c) 该改动落地的时刻**：`git log` 实测 `b8bc115ff`（加入 origin 列，`worker-store.ts` 首次出现 `WORKER_COLS_MIN/MAX`）= `2026-10-09 16:27:22 +0800` = **`2026-10-09T08:27:22Z`**；紧随的产物重建 `27e3c927e` = 本地 16:27:23（**08:27:23Z**）。⇒ **08:27:23Z 之前启动的 pi 进程，其内存里的 worker-store 解析器只认 7/8 列。**

**(d) 长驻进程不会自动换解析器**：`core/extensions/loader.ts:146-167`（`extensionCache` / `extensionCacheCwd` / `extensionCacheGeneration`）、`:407-439`（命中缓存直接返回 `cachedFactory`；`moduleCache:false`（`:421`）只影响模板编译，**工厂本身被缓存**，`:437` `extensionCache.set(extensionPath, factory)`）。⇒ 窗口加载的 bundle 代码在**进程存活期内固定**。

**(e) 现场列数指纹（实测，双向）**：

| 时刻（本地） | 文件状态（实测） | 说明 |
|---|---|---|
| 10:48（= 02:48Z，重排前） | `_workers.parallel` 52287 B / **250 行全 9 列**（每行以 `manual` 收尾）；247 行 `dispatched_at = 2026-10-09T12:01:47.5xxZ` | 上一次重排后又被「9 列写者」整文件重写过（同 key、时间戳不变） |
| 02:50:05Z 之后 | 同一文件 **252 行全 8 列**（无 origin 列），全部行 `dispatched_at = 2026-10-10T02:50:05.2xx-.7xxZ` | 重排写者 = **origin 之前的序列化器** |

⇒ 「重排 + 列数从 9 掉到 8」只能由「旧解析器（读空）→ 旧序列化器（写 8 列）」这一条链解释；**新写者不可能把 origin 列删掉**（`worker-store.ts:91-105` 恒输出 origin）。这是本卡的**决定性指纹**。

**(f) 触发窗口（实测）**：`--H--git-Multi-Workers--` 下 `2026-09-24T11-21-05-539Z_01a0d325-cf03-7a55-b4c7-b93911508f57.jsonl` —— 只有 **1 个** `session` 类型头（起始 `2026-09-24T11:21:05.539Z`，cwd = 本仓库）⇒ 进程自 2026-09-24 常驻，扩展在启动时加载（远早于 08:27:22Z 的 origin 改动）⇒ **该窗口持有旧解析器**。该文件实测含 `dispatch_worker` 调用 14+ 次、`switch_key` 调用，且其 message 时间戳为 `2026-10-09T12:01:47.501Z`（重排前 5 ms 的 turn 末）与 `2026-10-10T02:50:05.214Z`（重排前 6 ms 的 turn 末）——正是 `agent_settled` 的两个触发点。

**(g) 为什么「acked 终态任务」全中**：判据只有 key 集合（F3）。旧解析器读空的瞬间，**磁盘上每个 task 目录**（250 个）都被视为未派发 ⇒ 全量 `pending`。

### F7 `_workers.acked` 的全部读写点（确认 launcher 路径完全不碰）

| 方向 | 位置 | 说明 |
|---|---|---|
| 写 | `shared/ack-store.ts:42-68` | `ack()`：workers.lock + tmp + rename；行格式 `taskKey | ackedAtIso`（`:77-88`） |
| 写（调用者） | `pm/ui-bridge.ts:468`（`ackTasks(..., "all")`）、`:495`（逐 key） | 两者又被 `/mw ack`（`ui-bridge.ts:2347-2366`）与 `ack_worker_result` 工具（`ui-bridge.ts:1370-1395`）共用 |
| 读 | `ui-bridge.ts:463`（all 的排除集）、`:526`（面板 acked 徽标/unhandled 段）、`:1424`（`list_tasks` 徽标） | 全部是**观测/交互面** |
| 读（构造） | `pm-orchestrator.ts:665` | 只被传进 `renderWatchLines` 与 `registerWorkerTools` |
| Python | **无**（`rg -n "acked" packages/multi-workers -g '*.py'` = 0 命中） | launcher / conductor / dispatch 0 引用 |

⇒ **launcher 路径完全不碰 `_workers.acked`；派发判据（F2）也不碰**。缺口不是「没查 ack」，而是「**判据只看 key 集合，读空即全量重排**」。

### F8 可达性：本轮实测的三次「同型全量重排」

| 突发 | 窗口（实测 `[START]`） | 队列侧实测 | trace.log 侧实测（有前置 `[END]` 的重跑） |
|---|---|---|---|
| A | 2026-10-09T07:06-07:11Z | 未留存（当时解析器只有 8 列这一代，见 F6(c) ⇒ 触发机制与本轮不同） | `starts=205`（116 条有前置 `[END]`，89 条首跑） |
| B | 2026-10-09T12:00-12:57Z | **247 行** `dispatched_at = 2026-10-09T12:01:47.5xxZ`（快照实测；状态 243 done / 6 failed / 1 running） | `starts=315`（**309 条有前置 `[END]`**，跨 24 个 key；206 个不同任务） |
| C | 2026-10-10T02:48-03:20Z | **250 行** `dispatched_at = 2026-10-10T02:50:05.2xx-.7xxZ`（快照实测；**252 行全 8 列**） | `starts=236`（**230 条有前置 `[END]`**，跨 25 个 key；211 个不同任务） |

单个任务的三次执行（`mgh-rq1-l3-abort` trace.log 实测）：`08:41:41→08:52:21`（639 s，168 tools）→ **`12:02:01→12:43:30`（2489 s，193 tools）** → **`02:50:28→02:59:12`（524 s，44 tools）**。该 key 7 个调研任务的 ack 时间：6 个在重排前（`08:49:38`、`08:49:52`、`09:00:33`、`09:04:02`、`09:05:54`、`09:30:13`），`mgh-rq1-l3-abort` 在重跑后才 ack（`12:43:39.326Z`）——**证明 ack 状态对重排毫无约束力**。

证据文件被重跑版覆写：`evidence/research/` 内 6 份 `spec-*`/`*-wiring-*` 于本地 20:17-20:30 被改写（`git status` 实测多处 ` M`），其中 `design-g2-gate-reminder-wiring-20261009.md:8` 自标「二次执行（2026-10-09T12:15Z，mgh-drq2-reminder-wiring 重跑）」；`spec-l3-abort-taxonomy-20261009.md` 今天 10:57:30 又被第三次执行覆写（`.first-run.md` 备份在 `_orig/`）。**C 轮此刻仍在进行**（`_workers.parallel` 的 `updated_at` 直方图实测覆盖 02:50-03:06Z）。

### F9 「launcher 重启」被实测证伪（负对照）

- `.mw/mw.log`（serve 侧 `"a"` 模式追加，`mw.py:222`）最后一段：`[mw serve] started (PID 93716) - proxy=disabled launcher=96968` … `[mw serve] stopped`；`.mw/launcher-beat.96968` 的 **CreationTime = 2026-10-09 14:51:40 本地 = 06:51:40Z**（beat 每次 poll 覆写但**创建时间不变**）。
- ⇒ launcher 96968 **横跨 B（12:01:47Z）与 C（02:50:05Z）两次重排，未重启**（`mw.py:227` 每次 serve 都以 `"w"` 截断 `launcher.log`，其 749 行 spawn 记录正是这段常驻期的产物）。
- 更强的负对照：**`2026-10-10T03:07:31Z` 该 serve 真的停止**（`mw.log` 末行 `[mw serve] stopped`；`.mw/mw.pid` 与 `.mw/serve.meta` 消失；进程表内 Multi-Workers 的 `mw.py serve`/`launcher.py` 均不存在）。停止后 `_workers.parallel` **没有发生任何重排**（截止 03:1x，252 行的 `dispatched_at` 仍全是 `02:50:05`，`wjg-*` 新行仍是各自派发时刻）。
- ⇒ 「launcher 重启/恢复到启动时重建队列」这一假设**不成立**；观感来源是 F2 的 `agent_settled` 扫描。

### F10 修复点候选（Q6）

**唯一咽喉点（grep 证明唯一性）**：`rg -n "dispatched\.has|readAll\(\)\.map\(\(e\) => e\.taskKey\)" packages/coding-agent/src/extensions/agent-team-loop/` → **2 命中，同一函数**：`pm-orchestrator.ts:402`（建集合）与 `:428`（用集合）。全仓没有第二处「task 目录 → 是否需要入队」的判定。

| 候选 | 判据 | fail-closed 方向 | 误判后果 |
|---|---|---|---|
| **C1（推荐）** 在 `:402` 加「读回自检」：若 `readAll()` 返回 0 行 **但** 磁盘上存在 >=1 个带 `task.md` 的 task 目录 ⇒ **拒绝本轮扫描**并记一条机读告警（可选：把当前列数/首行样例落到日志） | 「队列读空 + 磁盘有任务」= 结构性矛盾，必是解析/IO 故障 | 方向正确：**宁可少派不可重派**；代价 = 真正的「全新项目 + 恰好 0 行 + 已有 task 目录」这一种合法态（首次派发）会被推迟一轮 | 首轮派发延迟 <=1 turn；可用「文件不存在」与「文件存在但解析 0 行」区分，把误判压到「文件存在却解析 0 行」 |
| **C2** 在 `:428` 把判据扩为「key 存在 **或** acked」：`dispatched.has(key) || ackStore.readAll().has(key)` | acked 即「已处理完」的显式名单（精确、语义最弱） | 若队列行丢失但 acked 还在 ⇒ **不重跑**（正好是本缺口）；若 acked 也丢 ⇒ 照旧重跑 | 被 ack 过的任务若确实需要重派，必须新 task_key（现状也是 `manual-*`/`-2` 命名）；语义上把 ack 变成「派发门禁」，需 PM 明确 |
| **C3** 在 `:428` 扩为「终态集合」：`dispatched.has(key) || statusByKey.get(key) 属于终态` | 同 C2 但来自队列行本身 | 若行集合读空则**无行可看** ⇒ **对本次缺口完全无效** | 无效（应记为组合里的次要件，不是主判据） |
| **C4（写侧）** `worker-store.ts:123-139` `upsert()` 拒绝把既有**终态**行降级为 `pending`（除显式 force） | 写侧不变式：终态只能由 launcher 改，TS 只允许 pending/running | 与派发语义正交，能挡住「扫描重排」这一具体写序列 | 需要一条显式重跑通道（`force`/新 key）；对「队列行被删 + 目录仍在」的孤儿恢复不再自动生效 |
| **C5（读侧兼容）** 让解析器**不再静默丢行**（列数超范围 → 抛错/显式告警而不是 `return undefined`） | 直接消掉「读空」的成因（F6） | 旧产物已在用户机器上，改源码只影响未来部署；不能治已装载的旧窗口 | 无（这是根治，不是补丁） |

**组合建议**：C1（本轮缺口的直接 fail-closed 闸）+ C5（根治静默丢行）+ C4（写侧不变式，可选）。若只允许改一处，选 **C1**（唯一咽喉点）。

### F11 风险面：钉死当前行为的测试，与改动会红的用例（Q7）

| 测试 | 位置 | 钉住的行为 |
|---|---|---|
| `dispatchNewTasks keyed workers scan` | `packages/coding-agent/test/extensions/agent-team-loop.test.ts:1319-1439` | `:1328-1345` 目录->pending 入队；`:1347-1361` 根目录/裸 key 不入队；**:1363-1375「does not re-dispatch a task key already in the queue」**（= C1/C2 会触碰的核心不变式）；`:1398-1438` VC-013/VC-014 |
| `dispatchNewTasks origin skip (D-104 / VC-023)` | `packages/coding-agent/test/suite/autopilot-protocol.test.ts:104-170` | conductor 任务永不入队/不 upsert |
| worker-store 列语义 | `packages/coding-agent/test/suite/worker-store.test.ts:65-117` | 9 列解析/序列化、origin 归一、legacy 7/8 列容错（**改解析器需同步**） |
| launcher 列兼容 + status 写 | `packages/multi-workers/test_launcher.py:513-564` | 7/8/9 列布局、`_update_status` |
| `archive_stale_entries` / `update_status` | `packages/multi-workers/test_common.py:310-395` | 只归档「非终态 + task.md 缺失」；整文件重写保行 |
| 面板/ack | `packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`、`test/suite/autopilot-monitor.test.ts` | ack 只接受终态行、面板 history=done∪acked（C2 若把 ack 变门禁需同步） |
| e2e 真起 serve 的用例 | `packages/multi-workers/test_autopilot_e2e.py`（`@_e2e_l2`：`:559 test_full_chain_single_key`、`:719 test_parallel_dispatch`、`:931 test_serve_enable_chain`、`:1006 test_conductor_kill_respawn`、`:1104 test_multi_project_isolation`）；`test_e2e_real.py`（`e2e_real`）；`test_launcher.py`（进程级 spawn 用 `_FakeProc`，不起真 serve） | 默认 `pytest.ini addopts = -m "not e2e_real and not e2e_l2"` 不跑；`-m e2e_l2` 才会起真 serve/conductor，**但都是 tmp 项目**，**没有一个用例覆盖「旧解析器读新列数」** |

⇒ **当前没有测试钉住 F6（跨版本列兼容）**，这正是缺口能连发生三次的原因；C1/C5 落地时应新增：①旧列数 x 新文件的解析拒绝用例（单元级，可用 `git show aafaa378b:` 的解析逻辑做语料对照）；②`dispatchNewTasks` 在「0 行 + 磁盘有 task 目录」时必须拒绝派发（红->绿）。

### F12 与已锁 AC 的关系（Q9：AC-008 观测面 <=1 tick、G2/G4 面板）

- **AC-008**（`spec.md:101`）：判据对象是 **pending gate 的时长/`BLOCKED_ON_HUMAN` 指示**，数据源是 gates 目录，不是 `_workers.parallel`（`monitor.ts:363-380`）。⇒ 重排**不直接移动** AC-008 的读数。
- 但重排会污染**同一次 tick 内的 worker/autopilot 段**：`monitor.ts:351-361` 只取 running 行并把 `dispatchedAt` 当计时起点 ⇒ 重排后所有行「从 0 计时」、`workers: N running` 从 0 跳到 ~250（本轮实测：02:50 分钟内 70 行转 running，02:51-03:06 收敛）。**AC-016（G4：数据面变化后 <=2 周期 8 s 内跟随）会在这段窗口内因「N 突然变大/归零」而出现无意义的红/绿摆动**——被测的其实是重排，而不是面板。
- **G2 提醒面**的风险更具体：`pm-orchestrator.ts:532-538` 的 `notified` 基线按「窗口打开时的终态行」建立，重排把行重新经过 `pending->running->done`，**同一窗口不会二次回读**（key 已在 `notified`），**新窗口才会** ⇒ 同一批终态结果可能被两个窗口各回读一次；同时 `ui-bridge.ts:612` 的 live 段永不折叠 ⇒ 面板会被 200+ 行 `pending` 灌满，`workers: 0 running` 语义在重排瞬间失真（与 G4 事故的 `workers: 0 running` 症状**表面同型**，归因必须靠 F6 的列数指纹区分，不能用症状相似度）。
- **结论**：G5 的修复（C1）与 G2/G4 **不冲突、且互为前置**——重排会让 AC-016 的「跟随」判据测到噪声，建议 G5 先落 fail-closed 闸，再跑 G4 的 8 s 跟随合成夹具。

---

## 3. 语料 / 实测表

### 3.1 `_workers.parallel` 快照（两次，本卡执行中）

| 项 | 02:48Z（重排前） | 03:1xZ（重排后） |
|---|---|---|
| 字节 | 52287 | 50939 -> 50742（随 launcher 更新波动） |
| 行数 | 250 | 252（新增 `wjg-rq1/rq2`） |
| 列数 | **250/250 = 9** | **252/252 = 8** |
| `origin` 列 | 全部 `manual` | **整列消失** |
| `dispatched_at` 直方图 | 247 x `2026-10-09T12:01:47.5xxZ`；`inc1/inc2` x `12:58:3x`；`mgh-rq5` x `2026-10-10T02:48:01` | **252 x `2026-10-10T02:50:05.2xx-.7xxZ`**（唯一） |
| 状态直方图 | 243 done / 6 failed / 1 running | 收敛中（`updated_at` 覆盖 02:50-03:06Z） |
| owner key 数 | 未留存 | 28（252 行，实测；重排批次按 trace 侧 25 个 key） |

### 3.2 trace.log 突发统计（`[START]` 全量抽取 1010 条）

| 窗口 | `[START]` 行数 | 有前置 `[END]`（=重跑） | 不同任务（重跑） | 涉及 key（重跑） |
|---|---|---|---|---|
| 2026-10-09T07:06-07:11Z | 205 | 116 | 116 | 23 |
| 2026-10-09T12:00-12:57Z | 315 | 309 | 206 | 24 |
| 2026-10-10T02:48-03:20Z | 236 | 230 | 211 | 25 |

### 3.3 其它 key 的一手证据（同批被重跑）

- `mgh-rq1-l3-abort`：3 次执行（F8）。
- `evidence/research/design-g2-gate-reminder-wiring-20261009.md:8`：自标「二次执行（2026-10-09T12:15Z…重跑）」。
- `.agenticdoc/goal-autopilot/tasks/{T-03-roadmap-check,T-04-timeline,T-05-gates,T-08-audit-evidence,T-13-worker-read-scope,T-15-autopilot-console}.md` 等 `git status` 实测被改（重跑 worker 追加复验行）。

---

## 4. 决策问题逐条回答

**Q1（谁写、何时写、是否整体重写、registered_at 来源；讲清「启动时重建」路径）**
写者只有两类：TS `WorkerStore.upsert`（`worker-store.ts:123-139`，**整文件重写**；经 `task-dispatcher.ts:284-296`，调用点 `pm-orchestrator.ts:464` / `ui-bridge.ts:1345` / `ui-bridge.ts:1742`）与 Python `_write_workers_file`（`mw_common.py:1704-1710`；经 `update_status`/`archive_stale_entries`/`dispatch.py`/`conductor.reconcile_orphans`，均为整文件重写或纯追加）。**launcher 启动路径不写行集合**（`launcher.py:775-836` 只 beat/archive/reap/reconcile/spawn）。「registered_at」= 第 6 列 `dispatched_at`，来源 `task-dispatcher.ts:289` 的 `new Date().toISOString()`（逐任务取 ⇒ 同批时间戳递增 ~1-3 ms）。所谓「启动时重建」= PM 窗口 `agent_settled` -> `dispatchNewTasks`（`pm-orchestrator.ts:739-746 -> :393-478`）：**它对每个磁盘 task 目录做 upsert，从而在文件层面表现为「整体重建」**；launcher 只是随后按 `pending` 全部 spawn（`:817-836`）。实测：本轮 C 的 252 行时间戳全部落在 `02:50:05.220Z-.726Z`（约 500 ms 内、按 readdir 顺序单调递增）。

**Q2（启动时决定「哪些任务要(重)执行」的确切谓词；读了什么；有没有分支读 `_workers.acked`）**
谓词只有一个：**「该 task 目录名 不在 `workerStore.readAll()` 的 taskKey 集合里」**（`:402` 建集合，`:428` 判定；另 `:430` task.md 存在性、`:435` conductor-origin 跳过、`:438-455` docs gate 抑制）。**不读** task.md 内容（除 conductor 标记与 type/model）、**不读** status、**不读** 终态、**不读** 结果文件（output.md/trace.log）、**完全不读** `_workers.acked`（全路径 0 命中；Python 侧 0 命中）。⇒ 「行集合读空」= 「全部任务都算未派发」。

**Q3（`_workers.acked` 全部读写点；launcher 是否完全不碰）**
写：`ack-store.ts:42-68`（唯一），调用者 `ui-bridge.ts:468/:495`（`/mw ack` `:2347-2366`、`ack_worker_result` `:1370-1395`）。读：`ui-bridge.ts:463/:526/:1424`（+`pm-orchestrator.ts:665` 构造、`:522-528` 传入面板/工具）。**Python 侧 0 命中 ⇒ launcher/conductor/dispatch 完全不碰**。本缺口的性质不是「没查 ack」，而是「判据里根本没有终态/acked 任何一维」。

**Q4（行格式/列语义/末尾列/终态表示/被重建行是否与既有行列一致）**
9 列 `task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin`（`mw_common.py:1566-1596`、`worker-store.ts:24-33`）；兼容 7/8 列。**末尾列 = `origin`（`conductor|manual`，`worker-store.ts:11-14`、`mw_common.py:1624-1636`）**；第 8 列为可选 `model`（=「model-override」的载体，`launcher.py:135-160` 的 `model-override` 行读它/task.md）。status 全集 5 值，终态 `{done, failed, needs-clarification}`（三处定义见 F4）。**列一致性：不一致，且是根因证据**——重排把 9 列文件整体写成 8 列（origin 丢失），因为写者是 origin 之前的序列化器（F6(e)）。

**Q5（TS 侧是否有「重启后重排/重跑」假设；是否有代码依赖 `registered_at` 或行序）**
有假设但方向相反：`pm-orchestrator.ts:369-371` 认为 launcher restart 会开重排通道（**实测证伪**，F9）。依赖 `dispatched_at` 的有：`monitor.ts:357`（running 行 elapsed；不可解析丢行）、`pm-orchestrator.ts:514`（终态时长回退）。**没有代码依赖行序**（`upsert` 保留读到的顺序；面板按 `updatedAt` 排序 `ui-bridge.ts:606`；ack 完全与行序无关）。`restoreWatch` 只恢复 watch/claim，不重排。

**Q6（最小修复点候选；fail-closed 方向与误判后果；唯一咽喉点 grep 证明）**
见 F10。唯一咽喉点 = `pm-orchestrator.ts:402/428`（grep 唯一 2 命中、同一函数）；推荐 C1（「0 行 + 磁盘有 task 目录 ⇒ 拒绝本轮扫描」）为直接闸，C5（解析器不静默丢行）为根治，C4（写侧拒绝终态行降级）为不变式加固，C2/C3（acked/终态参与判据）语义变强、对「读空」这类故障**无效**（C3）或需要 PM 明确把 ack 变成派发门禁（C2）。

**Q7（哪些测试钉死当前行为；改动会红谁；有没有 e2e 真重启 launcher）**
见 F11：`agent-team-loop.test.ts:1319-1439`（尤其 `:1363-1375`）、`autopilot-protocol.test.ts:104-170`、`worker-store.test.ts:65-117`、`test_launcher.py:513-564`、`test_common.py:310-395`、`agent-team-loop-ack.test.ts`、`autopilot-monitor.test.ts`。真起 serve 的 e2e 在 `test_autopilot_e2e.py`（`-m e2e_l2`，`:559/:719/:931/:1006/:1104`）与 `test_e2e_real.py`（`-m e2e_real`），**默认 pytest.ini 排除**，且全部用 tmp 项目，**没有任何用例覆盖跨版本列兼容**。

**Q8（可达性实测：12:0x-12:4xZ 被重跑的任务数/key 数；复算命令）**
队列侧：**247 行**被重排（`dispatched_at = 2026-10-09T12:01:47.5xxZ`；快照口径）。trace 侧：`12:00-12:57Z` 共 **315** 条 `[START]`，其中 **309 条有前置 `[END]`**（真重跑），覆盖 **206** 个任务、**24** 个 key；同口径下本轮 C（`02:48-03:20Z`）为 **230/211/25**，A（`07:06-07:11Z`）为 **116/116/23**。命令见 §5。

**Q9（与 AC-008 / G2 / G4 的关系）**
见 F12：AC-008 读数源是 gates，不受重排直接影响；但重排会在一到两个 tick 内把 worker 段（`workers: N running`、`dispatchedAt` 计时）与面板 live/history 分区整体打乱 ⇒ **AC-016（G4 <=2 周期跟随）在该窗口内测到的是重排噪声**；G2 的提醒去重基线与面板 live 段也会被同批重排扰动（`pm-orchestrator.ts:532-538`、`ui-bridge.ts:606-615`）。⇒ G5 应先落 C1，再跑 G4/G2 的合成夹具，避免把重排当成面板缺陷。

---

## 5. 可复算命令（全部只读）

```powershell
# 0) HEAD
git rev-parse --short HEAD

# 1) 队列时间戳/列数/状态快照（重排指纹）
$r = Get-Content .agenticdoc\_workers.parallel
$r.Count
$r | %{ ($_ -split '\|')[5].Trim() } | Group-Object | Sort-Object Name   # dispatched_at 直方图
$r | %{ ($_ -split '\|').Count }        | Group-Object                  # 列数（9=新写者 / 8=旧写者）
$r | %{ ($_ -split '\|')[1].Trim() }    | Group-Object                  # 状态直方图
$r | %{ $_ -replace '.*\.agenticdoc\\([^\\]+)\\workers\\.*','$1' } | Group-Object | Sort-Object Count -Descending

# 2) 同一读路径的解析自检（node，只读）
node -e "const fs=require('fs');const L=fs.readFileSync('.agenticdoc/_workers.parallel','utf8').split('\n');let ok=0,bad=0;for(const l of L){const n=l.split('|').length;if(n>=7&&n<=9)ok++;else if(l.trim())bad++}console.log({ok,bad})"

# 3) 旧/新两代解析器（产物级证据）
git show aafaa378b:packages/multi-workers/dist/extensions/agent-team-loop.js | rg -n "WORKER_COLS"
git show HEAD:packages/multi-workers/dist/extensions/agent-team-loop.js | rg -n "WORKER_COLS_MIN|WORKER_COLS_MAX"
git log --format="%h %ad %s" --date=iso -3 -- packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts

# 4) 突发统计（trace.log 的 [START]/[END] 全量抽取；重跑 = 前置有 [END]）
rg -N --with-filename -uu '^\[START\] 20' .agenticdoc -g trace.log > "$env:TEMP\starts.txt"
# 再对 ts 落在窗口内、且前置存在 [END] 的 START 计数（本卡脚本 $env:TEMP\mw-rq5-bursts.ps1）
# 单任务三次执行可直接看：
Get-Content .agenticdoc\mw-gate-verdict-hardening\workers\mgh-rq1-l3-abort\trace.log | Select-String 'START|END'

# 5) launcher 世代（证伪「重启」）
Select-String -Path .mw\mw.log -Pattern 'started \(PID|stopped' | %{ $_.Line }
Get-Item .mw\launcher-beat.96968 | fl CreationTime,LastWriteTime
Get-ChildItem .mw\launcher.log | fl Length,LastWriteTime ; (Get-Content .mw\launcher.log).Count

# 6) 判据唯一性 / ack 不参与
rg -n "dispatched\.has|readAll\(\)\.map\(\(e\) => e\.taskKey\)" packages/coding-agent/src/extensions/agent-team-loop/
rg -n "acked" packages/multi-workers -g '*.py'          # 期望 0 命中
Get-Content .agenticdoc\_workers.acked | Select-String '^mgh-'

# 7) 触发窗口（长驻 PM 会话；<pi-agent-root> = pi 的 agent 存档根目录，只读）
$S = "<pi-agent-root>\sessions\--H--git-Multi-Workers--"
$f = "$S\2026-09-24T11-21-05-539Z_01a0d325-cf03-7a55-b4c7-b93911508f57.jsonl"
Select-String -Path $f -Pattern '"type":"session"' -SimpleMatch | Measure-Object   # 1 => 单进程常驻
```

---

## 6. 未决 / 不可回答项

1. **突发 A（2026-10-09T07:06-07:11Z）的触发机制未坐实**。它发生在 origin 列（08:27:22Z）之前，当时所有进程持有的都是 8 列解析器，F6 的「列不兼容」链**不可能**解释它；其签名（205 条 `[START]`、116 条重跑、单批 191 条）与 B/C 同型，但成因待另立证据（候选：文件被外部删除/置空；`.agenticdoc` 曾随一次「递归删除」受损，见 `.agenticdoc/mw-workspace-incident-probe/evidence/in2-file-vanish-incident-20261009.md`）。**不作为结论使用。**
2. **B（12:01:47Z）重排前的 9 列状态是谁写的，未坐实**。已证：B 的写者是旧序列化器（因为 C 轮把文件落成 8 列，且 `worker-store.ts:91-105` 恒输出 origin，新写者不可能删列）；`08:27:23Z` 到 `12:01:47Z` 之间未发现新启动的 PM 窗口（只筛到 3 个 worker 会话：`08:41:41`、`08:53:17`、`09:13:33`），因此「谁先把文件写成 9 列」缺一手证据。**处置**：G5 修复不应依赖「谁写的 9 列」，只依赖「旧解析器读 9 列 = 读空」这一可机制化复现的条件。
3. **C（02:50:05Z）的 9 列来源同理未坐实到具体写入者**（已证 `12:58Z` 的 `inc1/inc2` 行以 `origin=manual` 存在 ⇒ 至少存在一个 origin-aware 写者；但无法定位其进程）。
4. **launcher 侧为何在 C 轮之后仍写 8 列**：Python `serialize_entry` 保留读到的列数（origin 空 ⇒ 8 列），故 launcher 会把 8 列态**冻结**下来。⇒ 跨版本兼容是**单向**的（新读旧 OK，旧读新丢行），这点已实测，但其对其它共用同一全局 bundle 的项目（如 `H:\git\E2Feature`）的传播面**未测**。
5. **本卡的两次快照受现场活动影响**：调研期间（03:07:31Z）Multi-Workers 的 `mw serve` 真的被停止（F9），且 C 轮 worker 仍在跑；`_workers.parallel` 行数与字节在两次快照之间有波动（250->252 行）。所有数值均带快照时刻，未做跨时刻求平均。
6. **`_workers.acked` 的 2026-10-09 记录中，`mgh-rq1-l3-abort` 的 `12:43:39` 是重跑后补 ack**（实测）；其余 key 是否也存在「重跑后补 ack」没有逐个核对（只核了 mgh-* 与 inc*）。

---

## 7. 一句话给 design/plan 的锚

G5 的规范对象不是「launcher 重启」，而是「**PM 扫描的入队判据在『队列行集合读空』时会全量重排**」；缺口面 = `pm-orchestrator.ts:402/428`（唯一咽喉）+ `worker-store.ts:73`（静默丢行）；acked 名单是**可选的**第二道闸，不是主判据。

[VERIFY] RQ-5: snapshot=2026-10-10T02:48Z(pre)+03:1xZ(post) HEAD=10446aefb queue_pre=250rows/9cols/247x2026-10-09T12:01:47.5xxZ queue_post=252rows/8cols/252x2026-10-10T02:50:05.2xx-.7xxZ parser_old=aafaa378b:dist/extensions/agent-team-loop.js:20788 WORKER_COLS=8(accepts 7/8) parser_new=HEAD:dist/extensions/agent-team-loop.js:20980-20997 MIN=7/MAX=9 origin_col_commit=b8bc115ff@2026-10-09T08:27:22Z dist_rebuilt=27e3c927e@08:27:23Z launcher_pid=96968 alive 2026-10-09T06:51:40Z..2026-10-10T03:07:31Z(no restart in either requeue window) bursts(trace [START]; requeue=has prior [END])=A 2026-10-09T07:06-07:11Z starts=205 requeue=116 tasks=116 keys=23 | B 12:00-12:57Z starts=315 requeue=309 tasks=206 keys=24 | C 2026-10-10T02:48-03:20Z starts=236 requeue=230 tasks=211 keys=25 mgh_rq1_runs=3(08:41:41-08:52:21 639s/168tools; 12:02:01-12:43:30 2489s/193tools; 02:50:28-02:59:12 524s/44tools) ack_refs_in_python=0 ack_refs_in_dispatch_path=0 scan_predicate_sites=2(pm-orchestrator.ts:402,428) upsert_callers=3 terminal_statuses=3(done,failed,needs-clarification) row_cols=9(legacy 7/8) rows_parsed_by_current_parser=252/252