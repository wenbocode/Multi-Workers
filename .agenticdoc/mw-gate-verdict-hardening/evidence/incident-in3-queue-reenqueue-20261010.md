# IN-3 复盘：worker 队列被整表重建，200+ 历史任务重跑

- **key**：mw-gate-verdict-hardening（本 key 的 G5 = "重启不得重排已 ack 的任务"；本文是该缺口的新证据输入）
- **日期**：2026-10-10（本地 UTC+8；机器值给 Z）
- **性质**：只读取证 + 一次运维刹车（kill launcher）。**本 key 未改动任何生产代码**
- **状态**：直接机制与根因**已坐实**；"把队列整表变成 9 列的那次改写由谁执行"**未坐实**（见 §10）
- **兄弟事故**：IN-1（junction 消失）/ IN-2（3,448 tracked 文件消失）由 key `mw-workspace-incident-probe` 负责，证据在 `.agenticdoc/mw-workspace-incident-probe/evidence/`。本文 §6 给出 IN-3 → IN-1/IN-2 的**上游因果连接**，并解答该 key 文档 §5 的未坐实项之一。

---

## 0. 摘要

| 问题 | 答案 |
|---|---|
| 发生了什么 | 项目级队列 `.agenticdoc/_workers.parallel` 被**整表重建**，把历史上每个 `{key}/workers/{task}/task.md` 都当成"从未派发过"重新入列 |
| 何时 | 至少 2 次全量重建：**10-09 20:01:47**、**10-10 10:50:05**（均由同一机制产生） |
| 规模 | 第 2 次：**252 行全量重建**（28 个 owner key），launcher 无上限 spawn，峰值 **66 个并发 worker**，11:26 仍有 **32 个存活** |
| 直接机制（坐实） | PM 扩展 `dispatchNewTasks()` 的判据是"队列里**有没有**这个 task_key 的行"——**不是**"任务是否已终态"。行一旦读不到，就被当成新任务重新派发 |
| 根因（坐实证据链） | 队列行格局从 **8 列漂移到 9 列**（新增 `origin` 列）。长驻 pi 窗口内存里加载的是**旧 bundle**，其解析器只接受 7~8 列且**静默丢弃**其余行（`return undefined`）→ `readAll()` 返回空/残缺 → 全量重新派发；`upsert` 回写时又把这些行**永久删除** |
| 放大器 | ① `launcher.py` 默认 `max_workers=None`（**无并发上限**）② 派发判据不看终态/ack ③ `_workers.acked` 从不参与 ④ 丢行完全静默、无"队列骤降"告警 ⑤ 长驻窗口无 bundle 版本校验 |
| 下游后果 | 第 1 次重建派出的 `mvr-t16-quality-gate-review` 重跑，于 10-09 20:32:18 执行 `git worktree remove --force` **穿透 junction**→ 直接造成 IN-1/IN-2（3,448 tracked 文件消失） |
| 现状 | 队列已排空（243 done / 8 failed / 1 running / **0 pending**）；服务已被他方于 11:20:32 重启；**复发引擎仍在 armed 状态**（见 §8） |

---

## 1. 事故定义

**IN-3 = "队列整表重建导致历史任务重跑"**。它与 IN-1/IN-2 的区别与关系：

```
IN-3（本事故）  队列读侧容差漂移 → 行被静默丢弃 → 全量重新派发
   └─ 派出的 worker 重跑历史任务
         └─ 其中一个（mvr-t16，review 型）为"取得可信判定"建 worktree + junction
               └─ git worktree remove --force 穿透 junction
                     ├─ IN-1：8 条 junction 消失
                     └─ IN-2：8 个包 3,448 个 tracked 文件消失
```

IN-3 是**上游**。IN-1/IN-2 是它的**后果**，而且是**最坏的那种后果**：随机挑一个历史任务重跑，等于在活的工作树里重放一条数月前的、当时安全的命令。

---

## 2. 时间线（本地 UTC+8，括号内为机器值）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 10-09 16:27:22 | `b8bc115ff` 落地：TS 源引入 `origin` 列（9 列）与 **7..9 容差** | `git log -1 b8bc115ff` |
| 10-09 16:27:30 | `27e3c927e` "rebuild dist artifacts"：dist bundle 同步为 7..9 | `git log -- packages/multi-workers/dist/extensions/agent-team-loop.js` |
| 10-09 16:27 之后 | **安装副本未同步**：`~/.pi/agent/extensions/agent-team-loop.js` 直到 10-10 10:53:02 才被刷新 ⇒ 期间启动的所有 pi 窗口跑**旧 8 列 codec** | 安装副本 mtime = 10-10 10:53:02 |
| 10-09 20:01:47 (12:01:47Z) | **IN-3 第 1 次**全量重建：文件内**每一行**的 `dispatched_at` 都被写成 `12:01:47.xxxZ` | 本 key 当时观测（pm-state D-008）；另有跨 key 佐证：`.agenticdoc/**` 大量产物出现 `轮次 2 \| 2026-10-09T12:13:31Z` |
| 10-09 20:17–20:43 | 本 key 7 个已 done+acked 的调研任务被重跑，6 份证据被覆盖，RQ-1 重跑 2489 s / 193 工具调用 | `evidence/research/*` mtime；`.agenticdoc/mw-gate-verdict-hardening/tasks/` |
| 10-09 20:07:43 (12:07:43Z) | 重跑 worker `mvr-t16-quality-gate-review` 的会话开始 | `~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-09T12-07-43-157Z_*.jsonl` |
| 10-09 20:32:18.452 | 该 worker 执行 `git worktree remove --force` → **IN-1/IN-2**（20:37:54 才恢复） | 同上 jsonl L142/L144；`mw-workspace-incident-probe` 两份证据 |
| 10-09 21:11:24 | `_workers.acked` 最后一次写入（此后**再无** ack 记录 = 没有任何机制让队列"记住"历史终态） | `Get-Item .agenticdoc/_workers.acked` |
| 10-10 10:43 前后 | 本 key 派发 `mgh-rq5-launcher-requeue`（唯一一次正常派发） | `.agenticdoc/mw-gate-verdict-hardening/workers/mgh-rq5-launcher-requeue/` |
| 10-10 10:48–10:50 | 该任务正常 spawn（node pid 148012，10:48:02） | `Get-CimInstance Win32_Process` |
| **10-10 10:50:05.220–.637** (02:50:05Z) | **IN-3 第 2 次**全量重建：252 行在**同一秒内**按目录扫描顺序被重新派发 | §3.2 |
| 10-10 10:50:05–10:50:41 | launcher 大爆发 spawn（worker.log mtime 序列密集） | `.agenticdoc/*/workers/*/worker.log` mtime |
| 10-10 10:53:02 / 10:54:38 | 全局扩展副本与 `.mw-py-path` 被刷新（此时才带上 7..9 容差） | `~/.pi/agent/extensions/` |
| 10-10 11:04:59 | 仓库 dist bundle 被重写（内容等于 HEAD） | `Get-Item packages/multi-workers/dist/extensions/agent-team-loop.js` |
| 10-10 11:07:28 (03:07:28Z) | **PM 刹车**：kill launcher pid 96968（用户选"轻刹"） | beat 停止；`_workers.parallel` 冻结于该时刻 |
| 10-10 11:07:31 | `mw serve` pid 93716 **级联退出**（"[mw serve] stopped"）⇒ 轻刹实际等于停服务 | `.mw/mw.log` tail |
| 10-10 11:20:32 / 11:20:35 | **他方**重启 `mw serve`（pid 37452 / launcher 132268）；此时队列已排空（0 pending）⇒ 未再爆发 | `.mw/mw.log`；fresh `launcher-beat.132268` |
| 10-10 11:26 | 仍有 **32** 个 worker 进程存活、16 份跨 key 证据在被重写 | `Get-CimInstance`；`.agenticdoc/**` mtime |

---

## 3. 直接机制（坐实）

### 3.1 判据：`dispatchNewTasks()` 只看"有没有行"

`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`

```
393  export async function dispatchNewTasks(workerStore, agenticdocRoot, opts = {}) {
402      const dispatched = new Set(workerStore.readAll().map((e) => e.taskKey));
         //  ↑ 唯一的"已派发"判据：任务键在文件里出现过一次就算
406      owners = fs.readdirSync(agenticdocRoot, { withFileTypes: true });   // 字母序
416          taskDirs = fs.readdirSync(workersDir, { withFileTypes: true }); // 字母序
428              if (dispatched.has(taskKey)) continue;      // ← 唯一的跳过条件
435              if (isConductorTask(taskMdPath)) continue;  // 只看 task.md 标签，与队列状态无关
466                  status: "pending",
```

触发点（每个 pi 窗口、**每轮 agent 结束**都会跑一次）：

```
730  pi.on("session_shutdown", () => clearInterval(pollHandle));
737  pi.on("agent_settled", () => { dispatchNewTasks(workerStore, agenticdocRoot, {...}) });
```

⇒ **任何一次 `readAll()` 读不到的行，都会在下一个 `agent_settled` 被重新派发**；没有任何"已终态就不该再跑"的判断，也没有"这次是不是一次反常的大批量"的自检。

### 3.2 证据：252 行是"同一秒、按扫描顺序、全新追加"

| 观测 | 数值 | 排除的解释 |
|---|---|---|
| `dispatched_at` 分布 | **252 行全部落在 `2026-10-10T02:50:05.220Z … .637Z`**（同秒，毫秒级递增） | 不是"历史上逐步派发累积"，是**一次遍历**写的 |
| 行顺序 | 按 owner key 严格字母序分组（28 个 owner、28 次切换、**零交错**），owner 内 task key 亦严格字母序（`msc-d1..d7, msc-qg, msc-rq1, msc-rq10..rq14, msc-rq2…` = ASCII 序） | `upsert` 命中同一 taskKey 是**原地替换**；只有"全新追加"才会得到纯扫描序 ⇒ 重建前该文件里**没有可读行** |
| 列数 | **252 行全部恰好 8 域**（`task_key\|status\|cli\|provider\|task_path\|dispatched_at\|updated_at\|model`），第 8 域仅 17 行非空 | §4：8 域 = **旧 codec 的写者**；新 codec 恒写 9 域并带 `manual`/`conductor` |
| 时间戳格式 | `dispatched_at` = `.220Z`（TS `toISOString`），`updated_at` = `+00:00`（Python `iso_now`） | 前者的写者只能是 TS 侧（Python 的 `iso_now` 是秒精度 `+00:00`） |
| 派发对象 | 252 行 = 28 个 key 下所有 `workers/*/task.md`（排除 `ap-*` conductor 任务：队列中 `ap-` 行数 = **0**，与 `:435` 的 conductor 过滤一致）；**0 行**的 task 目录缺失 | 完全符合"扫目录 → 逐个补派"的形状 |
| 触发时间点 | 10:50:05 恰好落在另一 key `mw-worktree-junction-guard` 写 `spec.md`（10:50:01）后 4 秒、本 key 写 T-07 任务卡（10:50:02）后 3 秒——即**多个窗口当时都在结束一轮 agent**（`agent_settled` 高频触发） | 与"某个窗口 settle 时扫描"一致 |

### 3.3 spawn 放大（坐实）

`packages/multi-workers/launcher.py`

```
822      if entry["status"] != "pending": continue      # 只跑 pending
837      if max_workers and len(running_procs) >= max_workers:   # ← max_workers=None 时该分支不生效
847  def run(..., max_workers: int | None = None...)
```

`max_workers` 只能来自 CLI（`mw.py:328-329` / `:424-425`，且仅在 `args.max_workers` 为真时才传），配置里**没有该键**（`grep max_workers mw_common.py` = 0 命中）⇒ 常态即 `None` ⇒ **无并发上限**。

结果：252 个 pending 行被尽可能并行 spawn。实测峰值 **66 个并发 node worker 进程**，10:50:09–10:50:41 的 `worker.log` mtime 序列即为 spawn 序列。

### 3.4 复现路径（代码级最小复现）

```
1. 让 _workers.parallel 对某个窗口的 readAll() 不可见
      （文件缺失 / 空 / 或全部行不满足该窗口解析器的列数约束）
2. 该窗口任意一轮 agent 结束 → agent_settled → dispatchNewTasks
3. dispatched = ∅ ⇒ 目录下每个 task.md 都被 upsert(pending) 追加
4. launcher 下一轮 poll（4 s）读到 N 个 pending → 无上限 spawn
```

---

## 4. 根因：队列行格局（codec）容差漂移

### 4.1 两个解析器，两种容差

| 版本 | 位置 | 列数规则 | 越界行的处置 | 写者输出 |
|---|---|---|---|---|
| **旧**（`b8bc115ff^`） | `shared/worker-store.ts:19,24` | `WORKER_COLS = 8`；`if (parts.length !== 8 && parts.length !== 7) return undefined;` | **静默丢弃** | **8 列**（无 `origin`） |
| **新**（HEAD） | `shared/worker-store.ts:81-104` | `WORKER_COLS_MIN = 7; WORKER_COLS_MAX = 9` | 7~9 全收 | **9 列**（`origin` 恒输出，legacy 归一为 `manual`） |
| 旧 dist bundle（`b8bc115ff:`） | `dist/extensions/agent-team-loop.js:20788-20791` | `var WORKER_COLS = 8;` | 静默丢弃 | 8 列 |
| HEAD dist bundle | `:20980-20997` | `MIN=7 / MAX=9` | 全收 | 9 列 |
| Python（两侧） | `mw_common.py:1567-1596`（读，7/8/9 全收）、`:1599-1615`（写，`origin` 有值才追加） | 容差 | —— | 8 或 9 列 |

### 4.2 漂移如何制造"读不到"

1. `b8bc115ff`（10-09 16:27）让**写侧**开始产出 9 列行（TS 新 codec 恒写 `origin`；Python 的 conductor 派发 `dispatch.py:606-616` 也写 `origin: conductor`）。
2. **读侧没有同时升级**：`~/.pi/agent/extensions/agent-team-loop.js` 直到 **10-10 10:53:02** 才被 `mw build/install`（`mw.py:4202` / `:4388-4456`）刷新。
3. 于是所有**在那个安装副本之前启动**的 pi 窗口（实测大量长驻窗口：pid 23868/62672 起于 8/28、80740 起于 9/10、25704 起于 9/19、50032/95236 起于 9/23、10604/30656/18200 起于 9/24、117296 起于 10/9 15:58、136660 起于 10/9 20:40）在内存里跑着 **7..8 列**的解析器：
   - 读到 9 列行 → **丢弃**（不报错、不告警）；
   - 一旦本窗口自己派发任何东西 → `upsert` 用 **8 列**写者**整表回写** ⇒ 之前被丢弃的 9 列行**永久消失**。
4. 对称地，任何**新 codec** 窗口（repo dist / 10:53 之后的安装副本）派发一次 → 用 9 列写者**整表回写** ⇒ 全表变 9 列。
5. 此刻轮到**旧窗口**扫描：`readAll()` 对全表返回 **∅** ⇒ `dispatched = ∅` ⇒ **整表重新派发**（§3.2 的 252 行）。

> 这解释了为什么每一次"整表重建"都发生在**同一秒内、按扫描序、由 8 列写者产出**：它必定是旧 codec 窗口的一次 `agent_settled`。

### 4.3 与第一次事故（10-09 20:01:47）的一致性

第 1 次重建发生在 `origin` 列落地后 3.5 小时，形状完全相同（全表同秒时间戳）。当时最可能的 9 列化写者是 repo dist 窗口（dist 与源同步于 16:27:30，而安装副本滞后）——即"新 codec 窗口派发一次 → 全表 9 列 → 旧窗口整表重派"。**两次事故是同一个引擎的两次点火。**

### 4.4 为什么列数漂移必然复发

只要同时存在两种 codec 的写者（旧安装副本窗口 / 新副本窗口 / Python 侧），任一方的"整表回写"都会把文件翻到自己的格局，另一方在下一次 `agent_settled` 就可能看到空/残缺。**没有版本头、没有容错告警、没有 writer 兼容协商**——这是一条自激振荡回路（§8）。

---

## 5. 放大因子（本次让"小 bug"变成"大事故"的每一层）

| # | 因子 | 证据 | 后果 |
|---|---|---|---|
| F1 | `launcher` 默认无并发上限 | `launcher.py:837,847`、`mw.py:328/424` | 252 个 pending 一次性铺开，峰值 66 并发 |
| F2 | 派发判据不看终态 | `pm-orchestrator.ts:402/428` | "done/acked 的历史任务"与"全新任务"无法区分 |
| F3 | `_workers.acked` 完全不参与 | `launcher.py` 全文无 `acked`；`grep` 0 命中；`_workers.acked` mtime 停在 10-09 21:11:24 | 258 条 ack 记录对"该不该再跑"零影响（= 本 key G5 原案） |
| F4 | 丢行**静默** | `worker-store.ts:81` `return undefined`；`readAll()` 只 filter | 无任何日志/告警；`upsert` 回写等于**静默删行** |
| F5 | 无"队列骤降/骤增"观测 | `mw doctor` / monitor 都只看行状态，不看**行数变化率** | 全表消失 0 报警；252 行新增 0 报警 |
| F6 | 长驻窗口无 bundle 版本校验 | 窗口从命令行启动即加载全局副本；新旧窗口长期共存 | 漂移可无限期潜伏 |
| F7 | Python/TS 两侧共用同一个 `.tmp` + `os.replace` | `mw_common.py:1704-1710`；实测 `[launcher] spawn failed for 'mwvg-t1-phase-docs-gate': [WinError 5] ... _workers.parallel.tmp -> _workers.parallel` | Windows 上原子替换会失败（**不丢数据，但会让更新静默丢失**），属同类脆弱面的邻居缺陷 |
| F8 | `mw serve` 不托管 launcher 退出 | 11:07:28 kill launcher → 11:07:31 `[mw serve] stopped` | 运维刹车没有"只停 spawn"的档位；一次 kill 等于停全服务（见 §9 运维项） |

---

## 6. 与 IN-1/IN-2 的因果连接（解答兄弟 key 的未坐实项）

`mw-workspace-incident-probe` 的 `incidents-timeline-20261009.md` §5 列了一条未坐实项：

> 触发 `mvr-t16` 重派的窗口（launcher 队列派发，无 `dispatch_worker` 记录）

本文给出的答案：**`mvr-t16-quality-gate-review` 的重派不是 launcher 自主决定，也不是任何 PM 手工 `dispatch_worker`，而是 IN-3 第 1 次全量重建（10-09 20:01:47）的产物**：

- 该任务在旧 key `mw-vision-role` 下早已 done+acked；
- 20:01:47 的全表重建把它的 `task.md` 重新入列 → launcher spawn（会话文件 `2026-10-09T12-07-43-157Z_*.jsonl` 记录了它 20:07:43 的启动）；
- 它在"为 key 出可信 QG 判定"的动机（其自述 12:21:28/12:21:48）下建 `%TEMP%\qg-head` worktree + junction，20:32:18 执行 `git worktree remove --force` → IN-1/IN-2。

⇒ **IN-1/IN-2 的"触发窗口"= IN-3。** 修 IN-3 不等于修 junction 穿透（那是另一条独立缺陷，仍须 `mw-worktree-junction-guard` 的 G1..G4），但**堵住 IN-3 会消除"随机重放历史命令"这一整类风险**。

---

## 7. 影响面（实测数字）

| 项 | 数值 |
|---|---|
| 全量重建次数（可确认） | 2（10-09 20:01:47；10-10 10:50:05） |
| 第 2 次重建行数 / owner key 数 | 252 行 / 28 key |
| 11:07 刹车时刻队列构成 | 250 行 = 220 `running` + 30 `pending` |
| 峰值并发 worker 进程 | 66 |
| 11:26 仍存活 worker | 32（覆盖 20+ 个 key） |
| 被重跑的**编码型**历史任务（示例） | `msc-t01-conductor-guards`、`msc-t14-docs-dist-regression`、`mavc-t03-mw-common`、`mwtp-s3-cli`、`wtl-t02-mw-common`、`mw-rag-fix-t16-py-role-unreachable`、`mvr-t19-evidence-refresh` … |
| 工作树被写入的文件（10:50 之后，`packages/**`，排除 `dist/`、`.tmp/`、`__pycache__`） | ≥ 30 个，含 `mw_common.py`(11:16)、`conductor.py`(11:21)、`status-model.ts`(11:16)、`ui-bridge.ts`(11:18)、`worker-mode.ts`(11:19)、`roadmap.py`(11:16)、`phase-docs.ts`(11:16)、`mw.py` …（**归属未逐一坐实**：同时有 20+ 个正当 live key 在正常编码） |
| `git status` 规模 | 刹车前 78 M + 4 ?? → 11:26 时 **106 M + 8 ??** |
| 被覆写的证据文档 | 16+ 份跨 key `evidence/research/*` 在同一分钟被重写（`mw-autopilot-slot-capacity`、`mw-autopilot-verify-cli`、`xkey-repair-mechanism`、`mw-vision-role`、`mw-done-closure-repair`、`mw-worker-progress-persist` …） |
| 本 key 自身损失 | `mgh-rq5-launcher-requeue` 被这轮重跑搞死（0 tool calls，无产出）；2 份证据被覆盖（`spec-l3-abort-taxonomy`、`design-g2-gate-reminder-wiring`） |

---

## 8. 复发条件与当前风险

**复发引擎仍 armed**，条件（任一满足即点火）：

1. 任意一个**新 codec** 写者（10:53 之后启动的窗口 / repo dist 窗口 / 后续安装刷新）对队列做一次 `upsert` ⇒ 全表翻成 9 列；
2. 任意一个**旧 codec** 窗口（10:50:05 之前启动、仍在运行的 10+ 个长驻窗口）在下一次 `agent_settled` 扫描 ⇒ `readAll() = ∅` ⇒ **再来一次全量重派**；
3. 若此时 launcher 在跑（现已重启，pid 132268）⇒ 无上限 spawn 全量重跑。

当前状态（11:26）：队列 0 pending、252 行已收敛为 243 done / 8 failed / 1 running ⇒ **此刻没有在爆发**；但只要 ①+② 组合出现，下一次爆发与本次同规模。

**风险不对等**：重跑的任务里既有只读 research/review，也有**会改源码的 coding 任务**，还包括**会执行破坏性 shell 的历史任务**（IN-1/IN-2 已证明最坏情形是整包源码被删）。

---

## 9. 建议（按"立即 / 结构性 / 观测 / 测试 / 归属"分层）

### 9.1 立即（运维，低风险，今天可做）

- **A1** 重启所有长驻 pi 窗口（让内存里的 bundle 与 `~/.pi/agent/extensions/agent-team-loop.js` 一致）。**在重启前不要再启动 launcher 之外的写入**；重启后确认无旧 codec 窗口存活。
- **A2** 队列留档：把当前 252 行复制到 `.agenticdoc/_workers.parallel.before-IN3-fix`（**未做**，需要授权——它是我 G5 修复的回归基线）。
- **A3** 记录运维教训：`mw serve` 不托管 launcher 退出 ⇒ "只停 spawn"的刹车不存在。若需要刹车档位，用 `mw stop`（影响面等价）或在修复中给 launcher 加"暂停 drain"开关。

### 9.2 结构性修复（本 key G5 应覆盖）

- **B1 派发判据改为终态判据**：`dispatched` 集合不能是唯一依据。改为三分歧：① 行存在且终态（done/failed/cancelled）⇒ 永不重派；② 行存在且非终态 ⇒ 交给 launcher/reconcile；③ **行不存在** ⇒ 默认**不重派**，除非显式 `--force-requeue`（fail-closed）。G5 原案（`_workers.acked` 参与判据）是这一条的子集。
- **B2 单轮派发配额 + 突变告警**：一次 `dispatchNewTasks` 新增 > N 行（默认 3）时**拒绝并广播**，而不是静默铺开。
- **B3 读侧不得静默丢行**：`readAll()` 保留"无法解析行"的计数；>0 时**抑制本轮派发**并告警；`upsert` 不得因解析失败而删除整行（当前行为 = 静默数据丢失）。
- **B4 队列格式版本化**：首行版本头（如 `# mw-queue v2`）或每行版本列，使旧读侧**显式拒绝并停止**，而不是"部分可读"→ 半盲派发。
- **B5 launcher 默认上限**：`max_workers` 缺省从 `None` 改为有限值（如 8），无界时启动打印告警。
- **B6 `_workers.acked` 参与**：本 key G5 原案，与 B1 合并实现。

### 9.3 观测（建议另立 key 或并入 G5 的 doctor 项）

- **C1** `mw doctor`：队列行数相对上一轮的**变化率**告警（骤降 > 20% 或骤增 > 3 行）；解析失败行数；`_workers.acked` 与队列终态行数是否一致。
- **C2** `mw doctor` / 窗口启动：全局装副本 bundle hash vs 仓库 dist hash vs **本窗口内存版本**（启动时自检，不一致则拒绝进入 PM 模式并提示重启）。
- **C3** monitor 面板：本 tick 新增派发计数 / 队列规模（与本 key G4 的"帧自证新鲜"同源）。

### 9.4 测试

- **D1** 回归：队列含"不可解析行"时，`dispatchNewTasks` **不派发任何行**且产生告警。
- **D2** 回归：队列**完全为空**（模拟 IN-3）时，`dispatchNewTasks` 不整表重派（fail-closed）。
- **D3** 回归：9 列行 / 8 列行 / 7 列行混合时，两侧解析器都不丢行；丢行时必有告警。
- **D4** 回归：launcher 默认上限生效（无 `--max-workers` 时不超过默认值）。

### 9.5 归属建议

| 项 | 归属 |
|---|---|
| B1、B6、D1、D2 | **本 key `mw-gate-verdict-hardening` G5**（须改写 G5 的 spec/design：原案只盯 acked，现须盯"行缺失即重派"这条判据本身） |
| B2、B3、B4、B5 | 建议新 key（例：`mw-queue-integrity`），因为写面横跨 TS store + Python 双解析器 |
| C1、C2、C3 | 同上；C3 与本 key G4 面板改造同面 |
| A1、A3 | 运维/文档（可并入新 key 的 docs 任务） |
| junction 穿透本身 | 兄弟 key `mw-worktree-junction-guard`（其 mini-spec 已定形） |

---

## 10. 未坐实项与证据缺口（诚实清单）

1. **"把队列整表变成 9 列的那一次改写由谁执行"未坐实**。候选：repo dist 窗口（`packages/multi-workers/dist` 自 10-09 16:27:30 即为 7..9）、或早于 10:53:02 的某次安装刷新。**但"存在 9 列写者"是必然推论**：否则无法解释旧 codec 窗口在 02:50:05 看到空队列。
2. **第 2 次重建的触发窗口身份未坐实**。仅有时间相关性（10:50:01 / 10:50:02 其他窗口在写文件 ⇒ 多个窗口正在 settle）。要坐实需要 pi 会话 jsonl（`~/.pi/agent/sessions/**`）里 `agent_settled` 的精确时刻；本轮未做（会话体量过大）。
3. **第一次重建（20:01:47）时文件当时的形态未留档**（现文件已被第 2 次重建覆盖）。证据只来自本 key 当时的观测记录（pm-state D-008）。
4. **`packages/**` 中 11:16–11:21 的源码写入归属未逐一坐实**（20+ 个正当 live key 同时在编码，无法与重跑 worker 区分）。要坐实需比对各 worker `trace.log` 的 write/edit 调用。
5. **`worker-store.ts` 早期版本是否曾接受 7 列（更早的安装副本）**未追溯；若存在更早的 7 列只认版本，则漂移面更大（会丢 8 列行）。可按 `git log -p -- shared/worker-store.ts` 继续追溯。
6. **`.agenticdoc/_workers.parallel` 在 02:50:05 之前是否片刻缺失**无法确证（Windows 上 tmp+replace 使 CreationTime 失去意义：当前文件 CreationTime = LastWriteTime = 11:07:28）。§4 的漂移解释是**更简约**的假设，但不是唯一可能。
7. **app 内 `.pi/agent/sessions` 不存在**（会话实际在 `~/.pi/agent/sessions`），本文未对会话内容做取证。

---

## 11. 证据清单（可复现命令）

```powershell
# 队列形状 / 时间戳 / 顺序（§3.2）
Get-Item .agenticdoc/_workers.parallel | Select-Object CreationTime,LastWriteTime,Length
(Get-Content .agenticdoc/_workers.parallel).Count
Get-Content .agenticdoc/_workers.parallel | ForEach-Object { ($_ -split '\|')[5].Trim() } | Group-Object { $_.Substring(0,19) } | Sort-Object Name
Get-Content .agenticdoc/_workers.parallel -TotalCount 5 | ForEach-Object { "fields=$(($_ -split '\|').Count) :: $_" }
Get-Content .agenticdoc/_workers.parallel | ForEach-Object { if (($_ -split '\|')[4] -match '\\\.agenticdoc\\([^\\]+)\\workers\\') { $matches[1] } }

# 代码级判据与容差
Select-String -Path packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts -Pattern 'dispatched|agent_settled|status: "pending"'
Select-String -Path packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts -Pattern 'WORKER_COLS|parts.length|origin'
git show 'b8bc115ff^:packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts' | Select-String 'WORKER_COLS|parts.length'
git show 'HEAD:packages/multi-workers/dist/extensions/agent-team-loop.js' | Select-String 'WORKER_COLS'
git log --format='%h %ci %s' -5 -- packages/multi-workers/dist/extensions/agent-team-loop.js

# launcher 上限与级联
Select-String -Path packages/multi-workers/launcher.py -Pattern 'max_workers|!= "pending"'
Get-Content .mw/mw.log -Tail 6
Get-ChildItem .mw/launcher-beat.* | Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-3) }

# 安装副本 vs 仓库 dist
Get-ChildItem "$env:USERPROFILE\.pi\agent\extensions" | Select-Object Name,LastWriteTime
Select-String -Path "$env:USERPROFILE\.pi\agent\extensions\agent-team-loop.js" -Pattern 'WORKER_COLS'

# 存活 worker 与它们重跑的任务
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match '\.agenticdoc\\' -and $_.CommandLine -match 'workers' } |
  ForEach-Object { if ($_.CommandLine -match '\.agenticdoc\\([^\\]+)\\workers\\([^\\]+)\\') { "$($matches[1])::$($matches[2])" } }
```

**交叉引用**：`.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md`（IN-1/IN-2）、`.agenticdoc/mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`、`in2-file-vanish-incident-20261009.md`。
