# Research: 越界成因判定 —— 4 条 `ap-` key 同时在飞而 cap=2（RQ-9 / msc-rq9-cap-breach-attribution）

> 角色：spec 期调研（**只读**）。本文件是本卡**唯一写面**：未改任何代码、未写 `_workers.parallel`、未答任何 gate、未 commit（探测脚本一律经 `python -` 从 stdin 运行，未落盘任何临时文件）。
> 代码基线：`H:/git/Multi-Workers` HEAD `4ef71e0539dfd7c697e552066c4784be8dc092b1`（`packages/multi-workers/autopilot/conductor.py`）。
> 数据基线：E2 = `H:/git/E2Feature`，FM = `E:/CLI_workspace/FeatureMigrator`；旁证 MW/OC/UEM/JCA/LT（见 F1.5）。
> 本卡只做**归属与成因判定**，不重复 RQ-1/RQ-5/RQ-6/RQ-7 已固化的公式与实测；对既有笔记的两处**修正**见 F6。

## TL;DR

1. **E2 4/2（2026-09-25T03:41:28Z）不是 conductor 的 cap 越界，而是两条来源不同的写入通道在同一时刻叠加**：2 条 conductor 派发行（a 类）+ 2 条 PM 手工 `dispatch_worker` 复用 `ap-` 前缀行（b 类）。cap gate 只 gate conductor 自己的派发；它在该窗口内从未派第 3 个 key。[事实]
2. E2 2026-09-26T06:55:23Z 的 3/2 是**同一机制**（2 条 a + 1 条 b，b 行 = `ap-feature-gui-time-mvp-board-unratified-disclosure`）。⇒ E2 两次越界同因，b 类各占一半。[事实]
3. FM 的两次 `>max` **都不是 conductor 口径的越界**：2026-09-26T03:05:02Z 的 3/2 = 2 条 conductor 行 + 1 条 `_scratch` 手工行（`_scratch` 不在 roadmap `deps_of` ⇒ conductor 口径 = 2 = cap）；2026-09-19T08:02:20Z 的 8/2 = 8 条 PM 手工 audit 行，当时 FM **无 roadmap、无 config.json、conductor 未运行**（FM timeline `seq=1` = 2026-09-23T09:06:44Z，比该窗口晚 4 天）⇒ 该 8/2 是**面板公式的算值**且 autopilot 未启用故**根本不渲染**（`monitor.ts:586`）。[事实]
4. 归属判定用**三条互相独立的证据链**，不靠前缀命名猜测：① 行的 `dispatched_at` **时间戳格式**（conductor 的 `mw_common.iso_now()` = `...T..:..:..+00:00` 秒精度 vs TS `new Date().toISOString()` = `...T..:..:...SSSZ` 毫秒）；② timeline 是否有对应 `dispatch` 事件 + task.md 是否有 `origin: conductor`；③ task.md 的 **mtime 与行 `dispatched_at` 的毫秒级贴合**（`dispatchTask` 先写 task.md 再写行，`task-dispatcher.ts:288-295`）。三链在全部 18 条涉事行上**结论一致、无冲突**。[事实]
5. **多 conductor 判定 = 不存在（无重叠）**：E2 的 conductor 启动次数（timeline `goal-snapshot` "startup baseline" 事件 = **9**）与 `mw.log` 的 `conductor spawned` 行数（**9**）相等，FM 为 **6/6**；同一 serve 世代内出现两条 `conductor spawned` 的三次（E2 launcher=49640；FM launcher=20700、45540）都能由"前一个 conductor 已死 → 1s 内重启"解释（`mw.py:170-174`：`pid_alive = pid 文件存活 or proc.poll() is None`，只有前者为假才 spawn）；E2 beat 网格在 2026-09-24T12:56Z → 2026-09-25T06:47Z 连续 17.8h 只有单一 4/5s 序列，无一例子秒级异常（**双 conductor 会留下双 tick 网格**）。[事实] 代码层无单例守卫（`conductor.main()` `:4125-4128` 无条件写 pid 文件、不校验已有实例），故"两个 serve 抢跑 / 手工起第二个 conductor"结构上仍可能，但**无任何证据**。[推断/无法判定残余]
6. **"旧构建导致语义不同"被排除**：`git blame` 显示 `_is_in_flight`、`_row_belongs_to`、`in_flight_keys` 推导、cap gate 全部出自 `4c7c07c43`（2026-09-10）且此后**一行未改**；磁盘上不存在第二份 `conductor.py`（Python 无打包副本，`packages/multi-workers/dist/` 只有 TS 扩展 `agent-team-loop.js`）。⇒ 该窗口的 cap 语义与今天一致；"旧版本 cap 只 gate 新 key 而不清 in_flight"这种版本**不存在**。精确到"当时跑的是哪个 checkout/工作树"**无法判定**（`serve.meta` 每世代被覆盖、`mw.log` 不记录 code_dir）。[事实/无法判定]
7. **可行路径 5 条**：C1 `dispatch_worker` 写 `ap-` 行（`ui-bridge.ts:1113/1255-1258`，**已实证**）、C2 后台扫描 `dispatchNewTasks`（`pm-orchestrator.ts:464`）、C3 `reconcile_orphans` 同 tick 回插 pending 行（`conductor.py:4021-4055`，在 `rows` 读取之前）、C4 xkey 提案通道（`conductor.py:3031`，在 cap 快照之前派发且用**陈旧 `rows`**）、C5 两个 conductor 实例（各把自己的 key 加进**本地** `in_flight_keys`）。另 3 条被证伪：launcher `update_status`、`archive_stale_entries`、`_dispatch_roadmap_writer`（SCRATCH owner，不在 `deps_of`）、`_advance_key` 内部分支（每分支 1 个 worker 且同一 key）。**已实证的只有 C1。** [事实]
8. **修正 RQ-5 F4#11**：`conductor.py:4032` 的孤儿回插锁**与** `mw_common.lock_path` **是同一把** `.mw/workers.lock`（`lock_file(root, name) = .mw/{name}.lock`，`conductor.py:116-118`）。`grep conductor-workers` 在 `packages/**` 全仓与全部 git 历史里**零命中**。⇒ spec §4 风险 8 与 RQ-5 F4#11（"两把锁实为不互斥"）应删除。[事实]
9. 对 spec 的意义：4/2 是 **(b) 逃逸口的表现**（AC-013 逃逸口 #1），**不是 cap gate 的真缺陷**；但它暴露两个**未登记的语义缺口**：(i) cap 会计通过前缀规则（`conductor.py:2136`）把"非 conductor 写的 `ap-{key}-*` 行"计入，于是 PM 通道既能**突破** cap 记账又能**消耗** conductor 配额；(ii) `_workers.parallel` 行**无 writer/origin 字段**，归属只能靠时间戳格式与 task.md 字节形状取证——这正是本卡不得不做取证的原因。修 (c)/(d) 前必须先钉死这两个语义。[事实/推断]

## 决策问题

本卡回答 RQ-9 的五问，与 RQ-7 §数据缺口 1（"E2 4/2 机制未能从留存物解释"）直接对接：

- **Q1 那 4 行分别是谁写的？** ⇒ F1（逐行归属表，含 `task_key` / `task_path` / `dispatched_at` / `updated_at` / `cli` / `provider` / 类别 / 判据），F2（四类判据定义）。
- **Q2 是否存在多个 conductor 实例？** ⇒ F3。结论：**不存在**（该窗口内只有一个 conductor 在 tick；同世代内的两次 spawn 是"死后 1s 重启"）。
- **Q3 是否曾用旧构建？** ⇒ F4。结论：**语义一致（cap 代码自 2026-09-10 未变）；精确构建无法判定**。
- **Q4 当前代码下所有能让 `len(in_flight_keys) > cap` 的可行路径？** ⇒ F5（8 条 writer：5 条可行 + 3 条证伪，逐条 `file:line` + 触发条件 + 是否已实证）。
- **Q5 真缺陷还是逃逸口的表现？对 (c)/(d) 的影响？** ⇒ §结论 → 决策映射。

**不做**：不判定"cap 该设几"（RQ-4）、不做吞吐/利用率量化（RQ-3）、不改任何代码、不写 `_workers.parallel`、不答 gate。

---

## 调研方法与出处

### 只读命令（逐条）

1. 代码（read 工具，全文或标注行段）：`conductor.py`：110-160（锁）、180-295（`orchestrate` 全量：reconcile → rows 读取 → `deps_of` → xkey 段 → `in_flight_keys` → 三重 gate）、398-520（`_stage_activation`/`_activate_pending_stage`/roadmap-writer）、520-560（`_dispatch_roadmap_writer`）、2085-2115（`goal-snapshot` 两个写入点）、2860-3060（`_xkey_proposal_stage`/`_xkey_proposal_one`）、4021-4065（`reconcile_orphans`）、4070-4163（`conductor_status`/`main`）；`mw.py`：138-207（`_conductor_decision`/`_conductor_supervise_step`/`cmd_serve` 的 pid 门禁）、203-262；`mw_common.py`：158（`_TERMINAL_STATUSES`）、161-162（`iso_now`）、1432-1445（`workers_path`/`lock_path`）、1482-1510（`acquire_lock`）、1512-1565（`update_status`/`archive_stale_entries`）；`dispatch.py`：12-14（`ap-{owner}-{stem}`）、109/126/398-410/435（`SCRATCH_OWNER`/`task_key_for`/`dispatch`）；TS：`worker-store.ts`（列序/`upsert`）、`task-dispatcher.ts`：237/278-296（`injectWorkspaceProfile`→`dispatchTask`）、`ui-bridge.ts`：1024-1097（`planDispatchFrontmatter`）、1111-1266（`dispatch_worker`）、1543-1646（`/worker`）、`pm-orchestrator.ts`：358-375/393-478（`isConductorTask`/`dispatchNewTasks`）、`monitor.ts`：246-252/497/509-522/586。
2. `git blame -L 2131,2140 / 258,264 / 287,292 -- packages/multi-workers/autopilot/conductor.py`；`git log -S "<token>" -- packages/multi-workers`（token = `in_flight_keys` / `parallel cap` / `_row_belongs_to` / `def _row_belongs_to` / `conductor-workers`）；`git log --date=iso --format="%h %ad %s" -- packages/multi-workers/autopilot/conductor.py`。
3. 现场只读数据：E2/FM 的 `.agenticdoc/_workers.parallel`、`.agenticdoc/*/workers/*/{task.md,trace.log,worker.log}`、`.agenticdoc/_autopilot/{timeline.jsonl,timeline.jsonl.1,config.json,_roadmap.md}`、`.mw/*`（`mw.log`/`serve.meta`/`mw.pid`/`conductor.pid`/`launcher-beat.*`/`dispatch.yml`）；旁证项目的 `_autopilot` 存在性扫描。
4. 未落盘的复算脚本（经 `python -` stdin）：行区间重叠扫描、`trace.log` `[END] ... elapsed=Ns` 反推开区间、timeline 事件直方图与 `goal-snapshot` 清单、beat delta 直方图与异常点、task.md 首行/`origin:`/mtime 对照。

### 三条归属证据链的机理（为什么它们各自独立且可判）

| 链 | 机理 | 出处 | 判别力 |
|---|---|---|---|
| E1 时间戳格式 | conductor 侧行由 `dispatch.dispatch` 写，`dispatched_at = mw_common.iso_now()` = `datetime.isoformat(timespec="seconds")` ⇒ 秒精度 + `+00:00`；TS 侧行由 `dispatchTask` 写，`dispatched_at = new Date().toISOString()` ⇒ 毫秒 + `Z` | `mw_common.py:161-162`、`dispatch.py:435-560`、`task-dispatcher.ts:284-296`、`worker-store.ts:67-80` | **强**（两侧格式互斥，无第三方 writer 用这些格式） |
| E2 timeline + task.md | conductor 每次派发在 `dispatch.py:597` 追加 `dispatch` 事件（detail = 完整 `task_key`）；conductor 渲染的 task.md 首行是 `---` + `type:`/`phase:`/`origin: conductor`/`loop:`/`attempt:` | `dispatch.py:597`、`dispatch.py:253-331`（`render_task_md`）、E2/FM timeline 实测 | **强**（`ap-` 行无对应事件 ⇒ 非 conductor 派发） |
| E3 task.md mtime ≈ 行 `dispatched_at` | `dispatchTask` 的顺序是 `injectWorkspaceProfile(task.md)` → `now = new Date().toISOString()` → `store.upsert`，即 **task.md 先写、行后写，同一同步调用内** | `task-dispatcher.ts:284-296` | **强**（毫秒级贴合 ⇒ 同一操作；背景扫描 `dispatchNewTasks` 只 upsert 不写 task.md ⇒ mtime 必然显著早于行时间） |

### 数据快照

| 项目 | `_workers.parallel` 行数 | conductor 格式行（`+00:00`） | TS 格式行（`.SSSZ`） | 其中 `ap-` 前缀 | config.json（mtime，UTC 近似） |
|---|---|---|---|---|---|
| E2 | 486 | 427 | 59 | **5**（L407/L413/L414/L470/L480） | 2026-09-24T02:39Z，`max_parallel_keys=2`，无 `xkey_repair` |
| FM | 232 | 128 | 104 | **0** | 2026-09-24T11:06Z，`max_parallel_keys=2`，无 `xkey_repair` |

> 说明：E2 的 427 条 `+00:00` 行**全部**是 `ap-` 前缀（逐行核对）；59 条 TS 行中有 54 条是 2026-09-21 之前的 `slicing-algorithm-spec`/`feature-clustering`/`feature-two-level-granularity` 手工卡（非 `ap-`），5 条是 `ap-` 前缀的 PM 手工行。FM 的 104 条 TS 行**无一条** `ap-` 前缀。⇒ **"PM 手工复用 `ap-` 前缀"在 E2 是 5 条、在 FM 是 0 条**，是个可穷举的小集合，不是普遍现象。

## 发现

### F1 逐行归属表（RQ-9 Q1）

#### F1.1 E2 2026-09-25T03:41:28Z — 4 条非终态行 = 4 个不同 key（a=2, b=2）

窗口与实测：4 条行的生命期区间（行时间戳）与 4 个进程的 `trace.log` 区间**互相印证**（见末列），4 路共同重叠 = **150.0s**（`[START]`/`[END]` 直接观测），行区间口径的 4 路重叠 = 155.9s（与 RQ-6 F4 的 155.9s 一致）。

| 行 | `task_key`（全名） | `task_path` | `dispatched_at` | `updated_at` | `cli`/`provider` | 类 | 判据（E1/E2/E3） | 进程区间（trace.log） |
|---|---|---|---|---|---|---|---|---|
| L411 | `ap-feature-l3-verdict-source-fallback-plan-writer-a1` | `.agenticdoc/feature-l3-verdict-source-fallback/workers/ap-feature-l3-verdict-source-fallback-plan-writer-a1/task.md` | `2026-09-25T03:31:28+00:00` | `2026-09-25T03:43:17+00:00` | pi / timi | **(a)** | E1 `+00:00` 秒精度；E2 timeline `dispatch` seq **74522** @03:31:28，detail 含全名 + `loop=gen:feature-l3-verdict-source-fallback:plan`，task.md 首行 `---` + `origin: conductor`；E3 task.md mtime 03:31:28.330（= dispatched +0.33s，`injectWorkspaceProfile` 已改写） | `[START]`≈03:31:32.969（= END−702s）→ `[END] 03:43:14.969Z exit=0` |
| L412 | `ap-feature-gui-time-mvp-board-005-services-mvp-ledger` | `.agenticdoc/feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-005-services-mvp-ledger/task.md` | `2026-09-25T03:37:37+00:00` | `2026-09-25T03:43:47+00:00` | pi / timi | **(a)** | 同上：dispatch seq **74605** @03:37:37，`loop=exec:feature-gui-time-mvp-board:005-services-mvp-ledger`，`origin: conductor` | 03:37:43.709 → `[END] 03:43:47.709Z exit=0` |
| L413 | `ap-feature-sampling-human-channel-repair-a2-achieved-terminal` | `.agenticdoc/feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-repair-a2-achieved-terminal/task.md` | `2026-09-25T03:40:03.390Z` | `2026-09-25T03:43:02+00:00` | pi / timi | **(b)** | E1 TS 毫秒格式；E2 全 timeline（97050 事件）**零命中**该 stem；task.md **无 `origin:`**、首行是裸 `type: coding`（=`planDispatchFrontmatter` 的字节形状，`ui-bridge.ts:1034-1046`）；E3 task.md mtime 03:40:03.389670 = dispatched **−0.3ms**；stem `repair-a2-achieved-terminal` 不在 conductor 词表（conductor 的 repair stem 是 `repair-a{used}`，`conductor.py:1729/1748`） | 03:40:08.794 → `[END] 03:42:57.794Z elapsed=169s` |
| L414 | `ap-feature-cigate-install-kit-repair-a3-achieved-terminal` | `.agenticdoc/feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-repair-a3-achieved-terminal/task.md` | `2026-09-25T03:40:11.098Z` | `2026-09-25T03:42:47+00:00` | pi / timi | **(b)** | 同上；E3 mtime 03:40:11.097652 = dispatched **−0.4ms**；该 key 当时**正 stalled**（`gate-0012 kind=stalled` @03:31:14，timeline `stalled` @03:31:14）⇒ 手工行被派进一个 stalled key（RQ-6 F4 同源） | 03:40:13.695 → `[END] 03:42:43.695Z elapsed=150s` |

**这一时刻的 conductor 口径（按 `conductor.py:258-264 + 2131-2138` 复算）**：4 条行的 `task_key` 都命中 `ap-{key}-` 前缀、`task_path` 也都落在各自 key 的 `workers/` 下，且 4 个 key 都在 roadmap（每个 key 在窗口前后都有 conductor `dispatch` 事件）⇒ **`in_flight_keys = {feature-cigate-install-kit, feature-gui-time-mvp-board, feature-l3-verdict-source-fallback, sampling-human-channel}` = 4 > cap=2**。cap gate 在 03:40:11 → 03:43:26 之间把所有新 key 挡在门外（下一批派发分别是 03:43:26 = L411 终态之后、03:43:48 = L412 终态之后——**两个都由 per-key 规则而非 cap 解释**）。[事实]

#### F1.2 E2 2026-09-26T06:55:23Z — 3 条非终态行 = 3 个不同 key（a=2, b=1）

| 行 | `task_key` | `task_path` | `dispatched_at` | `updated_at` | `cli`/`provider` | 类 | 判据 |
|---|---|---|---|---|---|---|---|
| L478 | `ap-feature-false-meets-remediation-l3-a5` | `.agenticdoc/feature-false-meets-remediation/workers/ap-feature-false-meets-remediation-l3-a5/task.md` | `2026-09-26T06:52:21+00:00` | `2026-09-26T07:04:48+00:00` | pi / timi | **(a)** | dispatch @06:52:21，`loop=l3:feature-false-meets-remediation attempt=5`；task.md `origin: conductor` |
| L479 | `ap-feature-gui-contract-respec-spec-writer-a1` | `.agenticdoc/feature-gui-contract-respec/workers/ap-feature-gui-contract-respec-spec-writer-a1/task.md` | `2026-09-26T06:52:25+00:00` | `2026-09-26T07:01:38+00:00` | pi / timi | **(a)** | dispatch @06:52:25，`loop=gen:feature-gui-contract-respec:spec attempt=1`；`origin: conductor` |
| L480 | `ap-feature-gui-time-mvp-board-unratified-disclosure` | `.agenticdoc/feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-unratified-disclosure/task.md` | `2026-09-26T06:52:34.032Z` | `2026-09-26T06:58:12+00:00` | pi / timi | **(b)** | TS 毫秒格式；timeline 零命中该 stem；无 `origin:`、首行裸 `type: coding`；mtime 06:52:34.032805 = dispatched **−0.0002s** |

4 路/3 路进程重叠：`trace.log` 三路共同重叠 **331.0s**（06:52:37.425 → 06:58:08.425）；conductor 口径 `in_flight_keys = 3 > 2`（3 个 key 都在 roadmap，L478/L479 的 dispatch 事件即证）。[事实]

#### F1.3 FM 2026-09-26T03:05:02Z — 3 条非终态行，但**不是 conductor 口径的越界**（a=2, b=1/`_scratch`）

| 行 | `task_key` | `task_path` | `dispatched_at` | `updated_at` | `cli`/`provider` | 类 | 判据 |
|---|---|---|---|---|---|---|---|
| L211 | `ap-gui-live-monitor-001-contract-input-harness-and-red-baseline` | `.agenticdoc/gui-live-monitor/workers/ap-gui-live-monitor-001-.../task.md` | `2026-09-26T02:50:28+00:00` | `2026-09-26T03:07:29+00:00` | pi / timi | (a) | dispatch @02:50:28（`loop=exec:gui-live-monitor:001-...`） |
| L212 | `ap-gui-run-control-hitl-001-contract-input-and-red-baseline` | `.agenticdoc/gui-run-control-hitl/workers/ap-gui-run-control-hitl-001-.../task.md` | `2026-09-26T02:54:44+00:00` | `2026-09-26T03:33:40+00:00` | pi / timi | (a) | dispatch @02:54:44 |
| L213 | `xkey-n1-hitl-groups-repair` | `.agenticdoc/**_scratch**/workers/xkey-n1-hitl-groups-repair/task.md` | `2026-09-26T03:04:01.702Z` | `2026-09-26T03:05:59+00:00` | pi / timi | **(b)** | TS 毫秒格式；timeline 零命中；无 `origin:`、首行裸 `type: coding`；mtime 03:04:01.699668 = dispatched **−2.3ms**；**且 `task_path` 在 `_scratch/`** ⇒ `_row_belongs_to` 两条规则**都不命中**任何 roadmap key ⇒ **conductor 口径 = 2 = cap，没有越界** |

⇒ RQ-7 表里的 "FM 3/2" 是**面板口径**（面板把非 `ap-` 的手工行按 `owner ?? w.taskKey` 记成**独立一个槽**，`monitor.ts:509-513`），不是 conductor 口径。进程三路重叠 = 113.0s（03:04:06.327 → 03:05:59.327）。[事实]

#### F1.4 FM 2026-09-19T08:02:20Z — 8 条非终态行，**当时无 conductor、无 roadmap、无 config**（b=8）

| 行 | `task_key` | `dispatched_at` | 类 | 判据 |
|---|---|---|---|---|
| L18 | `goal-roadmap-audit` | `2026-09-19T08:01:34.508Z` | (b) | TS 毫秒格式；非 `ap-`；task_path `.agenticdoc/goal-roadmap/workers/...` |
| L19 | `quick-defect-fixes-audit` | `2026-09-19T08:01:59.633Z` | (b) | 同上 |
| L20 | `migration-ledger-audit` | `2026-09-19T08:01:59.635Z` | (b) | 同上 |
| L21 | `gate-assertions-audit` | `2026-09-19T08:01:59.637Z` | (b) | 同上 |
| L22 | `skill-system-core-audit`（failed） | `2026-09-19T08:01:59.638Z` | (b) | 同上 |
| L23 | `plugin-scope-support-audit` | `2026-09-19T08:02:20.632Z` | (b) | 同上 |
| L24 | `scope-scripts-productization-audit` | `2026-09-19T08:02:20.633Z` | (b) | 同上 |
| L25 | `status-view-unification-audit` | `2026-09-19T08:02:20.635Z` | (b) | 同上 |

关键事实：FM timeline 的**第一条事件 `seq=1` = 2026-09-23T09:06:44Z**（`goal-snapshot` "startup baseline"），FM `_autopilot/config.json` mtime = 2026-09-24T11:06Z，FM `mw.log` 在 09-19 的两个 serve 世代（launcher=17820、20284）**都没有 `conductor spawned` 行** ⇒ 该窗口 **conductor 不存在**，`deps_of` 不存在，cap 记账不存在；`max_parallel_keys` 只是面板回退的默认值 2（`monitor.ts:522`），且 autopilot 未启用 ⇒ `slots` 行**不渲染**（`monitor.ts:586`）。⇒ "FM 8/2" 是**面板公式的算值**，连"显示分歧"都不是。[事实]

#### F1.5 非 autopilot 项目的 `>max` 值（面板口径，非越界）

| 项目 | `_autopilot` 目录 | config.json | roadmap | timeline | RQ-7 记录的峰值 | 判定 |
|---|---|---|---|---|---|---|
| MW | **不存在** | 无 | 无 | 0 文件 | 7/2（2026-08-28） | 面板公式 only；`deps_of=∅` ⇒ conductor 口径恒 0（RQ-7 F2.1 已实测 4 vs 0） |
| OC | **不存在** | 无 | 无 | 0 文件 | 6/2（2026-09-20） | 同上（PM 手工 fan-out） |
| UEM | **不存在** | 无 | 无 | 0 文件 | 9/2（2026-09-14） | 同上 |
| LT | **不存在** | 无 | 无 | 0 文件 | —— | 无 worker 行 |
| JCA | 存在 | 有 | 有 | 3 文件 | 2/2（不越界） | 唯一第二个 autopilot-enabled 项目；本卡未在其窗口发现 `>cap` |

⇒ **全部"`slotsUsed > slotsMax`"样本中，只有 E2 的两处是 conductor 口径的 `in_flight_keys > cap`**，且两处都由 b 类（PM 手工 `ap-` 行）造成。[事实]

### F2 四类判据的定义与本次仲裁（RQ-9 Q1 的判定规则）

| 类 | 定义 | 必须同时满足的判据（本次实际使用的） | 本次归属结果 |
|---|---|---|---|
| **(a) conductor 派发** | `_advance_key`/`execute_loop`/`_verify_loop` 经 `dispatch.dispatch` 写行 | ① `dispatched_at` 为 `iso_now()` 秒精度 `+00:00`；② timeline 有对应 `dispatch` 事件且 detail 含**完整 task_key**；③ task.md 首行 `---` + `origin: conductor` + `loop:` 与实际 loop 家族一致；④ trace `[END] elapsed=Ns` 反推的 `[START]` 落在 `dispatched_at + 0..6s`（launcher poll 5s，`launcher.py:49`） | a=4（E2 L411/L412/L478/L479）+ FM 2 条 = **a=6** |
| **(b) PM 手工通道复用 `ap-` 前缀** | TS `WorkerStore.upsert`（`worker-store.ts:67`）← `dispatchTask`（`task-dispatcher.ts:284`） | ① `dispatched_at` 为 `toISOString()` 毫秒 `Z`；② timeline **零命中**该 `task_key`；③ task.md **无 `origin:`** 且首行是裸 `type:`（`planDispatchFrontmatter` 形状）；④ task.md mtime 与 `dispatched_at` **差 ≤3ms**（同一次 `dispatchTask` 调用）；⑤ stem 不在 conductor 词表内（词表见下） | b=12（E2 5 条 + FM 1 条 + FM 09-19 的 8 条 - 重叠计数见 F1） |
| **(c) `reconcile_orphans` 回插 pending 行** | `conductor.py:4021-4055`，`status:"pending"`，写者=conductor 自己但**绕开 cap gate 的"新增 key"语义**（在 `rows` 读取之前追加，故同 tick 计入 `in_flight_keys`） | 判据：timeline 有 `reconcile` 事件（`detail="orphan reinserted: <task_key>"`，`:4056-4060`）+ 行 `dispatched_at` 为 `iso_now()` 秒精度 + task.md 有 `origin: conductor` | **c=0**：E2 两代 97050 事件、FM 两代 53836 beat/全量事件直方图里 **`reconcile` 事件 0 次**（同类 `skip` 也 0 次）⇒ 两个项目从未触发过该路径 |
| **(d) 其它 writer**（`archive_stale_entries`、launcher `update_status` 中间态等） | `mw_common.py:1512-1527`（只改已存在行的 `status`/`updated_at`）；`mw_common.py:1529-1563`（只**删除**行并归档） | 判据：行 `dispatched_at` 不变但 `status` 翻转；或行消失/进 `_workers.stale.parallel` | **d=0**：本卡覆盖的全部窗口里没有任何一行的 `task_key`+`dispatched_at` 是"先无行后有行"且非 (a)/(b)/(c)；`update_status` 不能新增 key，`archive_stale_entries` 只减不增（代码面证伪，见 F5 行 W3/W4） |

**conductor 的 stem 词表（用于判"这个名字 conductor 会不会起"）**：phase writer = `{phase}-writer-a{n}`（`conductor.py:935` `_next_gen_stem`）、L2 裁决 = `l2-tasks-to-execute-a{n}`/`l2-fix-tasks-to-execute-a{n}`、exec 卡 = plan 里的 `{NNN}-{slug}`、L3 = `l3-a{n}`（`:1316/1605/1641`）、repair = **`repair-a{used}`**（`:1729/1748`，**没有 `-后缀` 形式**）、roadmap = `roadmap-s{n}-a{n}`（SCRATCH owner，`:548`）、xkey = `xkey-{request_id}-proposal[-a{n}]`（`:3017/3029`）、重试统一为 `-a{n}` 追加（`_next_gen_stem`）。⇒ `repair-a3-achieved-terminal`、`repair-a2-achieved-honest`、`unratified-disclosure` 全部**不在词表**，conductor 结构上不会产生它们。[事实]

### F3 多 conductor 实例判定（RQ-9 Q2）

**结论：不存在（该窗口内只有一个 conductor 进程在 tick）；同一 serve 世代内确实出现过"先后两个 conductor 进程"，但那是死后 1s 重启，不是并发。** [事实]

证据链（四路互相独立）：

1. **启动计数对齐**：conductor 每次进入 `main()` 都无条件写一个 `goal-snapshot` "startup baseline" 事件（`conductor.py:4139`，另一个写入点 `:2109` 的 detail 是 `baseline refreshed ...`，可区分）。实测（detail 严格以 `startup baseline` 开头者）：

   | 项目 | `goal-snapshot(startup)` 次数与时刻（UTC） | `mw.log` 的 `conductor spawned` 行数 | 结论 |
   |---|---|---|---|
   | E2 | **9**：09-22T03:35:07 / 08:55:16 / 16:01:29 / 09-23T07:47:29 / 09-24T03:03:43 / **09-24T15:24:28** / 09-25T06:47:14 / 09-26T02:19:59 / 09-26T02:30:48 | **9** | 1:1；无"未记入 mw.log 的额外 conductor 启动" |
   | FM | **6**：09-23T09:06:44 / 15:23:56 / 09-24T03:07:04 / **09-24T03:08:37** / 09-25T02:36:19 / 09-26T02:30:43 | **6** | 1:1 |

   ⇒ **没有任何一次 conductor 启动是"没被 serve 记录"的**，也没有"两条 startup 事件挨在一起"的并发征兆。E2 09-25T03:40 窗口对应的 conductor 是 **09-24T15:24:28 启动的那一个**，它一直 tick 到 09-25T06:47:14 才被替换（`launcher-beat.49640` 的最后一拍 = 09-25T06:47:11Z，`goal-snapshot` = 06:47:14Z，beat delta 异常点正是 06:47:13→06:47:14 的 **1.0s**）。

2. **同一世代两条 spawn 行的解释**：E2 `launcher=49640` 世代（该 launcher 的 beat 文件最后一拍 09-25T06:47:11Z，即世代区间 ≈ 09-24T03:03→09-25T06:47）里出现 `conductor spawned (PID 12984)` 与 `conductor spawned (PID 100048)` 两行，对应上面 09-24T03:03:43 与 09-24T15:24:28 两个 startup 事件；FM 的 `launcher=20700`（→09-23T09:06:44 + 15:23:56）与 `launcher=45540`（→09-24T03:07:04 + 03:08:37）同理。serve 的重启闸门是 `pid_alive = _check_pid(conductor.pid) is not None or (proc is not None and proc.poll() is None)`（`mw.py:170-174`），即**只有当上一个 conductor 进程真的不在时**才会再 spawn，且配置为"1s 自愈"（`mw.py:140-152` 的 `_conductor_decision` docstring、`conductor.py:5-6` 模块 docstring）。⇒ 第二条 spawn 行 = 第一条已死。**第二条不是"第二个实例"。**

3. **beat 网格单序列**：E2 两代全量 beat = 83671 条，delta 直方图 = `{4s: 57583, 5s: 26056, 6s: 20, 7s: 8, 8s: 1, 2s: 1, 1s: 1}`；窗口 09-24T12:56Z → 09-25T06:47Z（含 03:40 越界点）**没有任何非 4/5s 的 delta**。两个 conductor 同时在 tick 会各写一条 `beat`（`conductor.py:2056` 起的 tick 首行），必然产生大量 0-2s delta 或倍频 —— **未观测到**。FM 同理（`{4s:28554, 5s:20895, 6-11s: ~4400, 328s:1(世代交接), 34s:1, 13s:2, 12s:1, 2s:1}`，无并发网格）。

4. **代码面无互斥（残余不确定性的来源）**：`conductor.main()` 不校验现存实例，直接 `pid_path.write_text(str(os.getpid()))`（`conductor.py:4125-4128`）；唯一的并发闸门在 **serve 层**——`cmd_serve` 启动时检查 `.mw/mw.pid`（`mw.py:210-216`），但"检查 → 写 pid"之间不是原子操作（route precheck 在写 pid 之前，`mw.py:250-262`），且手工 `python autopilot/conductor.py --project=<dir>` 完全绕过它。⇒ 结构上"两个 conductor 同时 tick"**可能**（且此时两者各把自己的 key 加进本地 `in_flight_keys`，可产生最高 `2×cap` 的瞬时口径越界，随后两者读到同一份行文件即自限），但**本卡在 E2/FM 的全部留存物里没有任何证据**。

⇒ **判定 = 不存在（无重叠实例）；"是否曾经结构性地可能" = 是（无单例守卫），但这不是本窗口越界的成因。**

### F4 是否曾用旧构建（RQ-9 Q3）

**结论：cap 语义与今天一致（"旧版本语义不同"这一候选被排除）；精确到"当时运行的是哪个 checkout / 工作树"无法判定。** [事实 + 无法判定]

1. **cap 代码自引入以来未被修改**：`git blame -L 2131,2140`（`_is_in_flight`/`_row_belongs_to`）、`-L 258,264`（`in_flight_keys` 推导）、`-L 287,292`（`key in in_flight_keys` / `len(...) >= max(1, max_parallel_keys)` / `in_flight_keys.add`）**每一行都归属 `4c7c07c43`（2026-09-10）**；`git log -S "in_flight_keys"`、`-S "parallel cap"`、`-S "def _row_belongs_to"` 均只命中该提交（`-S "_is_in_flight"` 额外命中 `181a75332` 2026-09-26，是 xkey 提交新增**调用点**，在窗口之后）。⇒ 从 2026-09-10 起，"cap = 非终态行（含 pending）∩ roadmap 候选域"就是唯一形态；不存在"cap 只 gate 新 key 而不清 in_flight"的历史版本。
2. **磁盘上不存在第二份 Python 副本**：`packages/multi-workers/dist/` 只有 `extensions/agent-team-loop.js`（TS 扩展，2026-09-26 重建），**没有** `autopilot/*.py` 的打包副本；`H:\git` 与 `E:\CLI_workspace` 递归只有 `H:\git\Multi-Workers\packages\multi-workers\autopilot\conductor.py` 一份。⇒ "跑的是别的副本"没有载体。
3. **运行位置可核（当前世代）**：E2 `.mw/serve.meta` = `{"pid": 76584, "started_at_ms": 1790389847906, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}`，与 `.mw/mw.pid`(76584)/`launcher-beat.73496` 一致 ⇒ 当前世代直接跑源码树，不是 dist。
4. **配置未变**：E2 `config.json` mtime = 2026-09-24T02:39Z（**早于** 09-25T03:40 窗口），内容 `max_parallel_keys: 2` 且**无 `xkey_repair` 键**（默认 false，`config.py`）；FM 的 mtime = 2026-09-24T11:06Z。⇒ 窗口内 cap=2、xkey 通道关闭（与 RQ-7 的声明一致，本卡独立复核）。
5. **无法判定的部分 + 所需证据**：`serve.meta` 是**每世代覆盖写**（mtime 2026-09-26T10:30Z），`mw.log` 不记录 `code_dir`/argv，`.mw/` 下无进程 argv/env 留痕 ⇒ **09-25 那次 serve 的准确 argv 与工作树 diff 不可恢复**。要判定它需要：① 当时 `serve.meta` 的副本（无）；② 进程表快照（无）；③ 工作树未提交 diff 的存档（无）。**在 git 层面可给出的最强结论**：该窗口的 conductor 必然含 `4c7c07c43` 的 cap 代码（否则连 `ap-` 行与 `origin: conductor` 都不存在），而 cap 代码此后未改 ⇒ **语义等价**。

### F5 当前代码下能让 `len(in_flight_keys) > cap` 的全部路径（RQ-9 Q4）

`in_flight_keys` 的定义（`conductor.py:258-264`）= `{k ∈ deps_of : ∃row, _is_in_flight(row) ∧ _row_belongs_to(row,k)}`，其中 `_is_in_flight` = `status ∉ {done,failed,needs-clarification}`（`:2131-2132`，**pending 计入**），`_row_belongs_to` = `task_key.startswith("ap-{k}-")` **or** `task_path` 含 `.agenticdoc/{k}/workers/`（`:2135-2139`）；gate 在 `:287-292`。⇒ 越界只有两种机制：**(i) 外部 writer 在 ≥cap 个 key 已在飞时新增一个属于 roadmap key 的非终态行；(ii) 一个 conductor 之外的第二写者/第二实例把 key 加进自己的本地集合。** 下表穷举 8 条 writer：

| # | writer | `file:line` | 能否 `>cap` | 触发条件 | 已实证？ |
|---|---|---|---|---|---|
| **C1** | TS/PM 手工通道：`dispatch_worker` 工具（PM 传入 `task_key`，可以是 `ap-{key}-...`） | `ui-bridge.ts:1113`（注册）/`:1220-1266`（taskDir 去重 → 写 task.md → `dispatchTask`）；`task-dispatcher.ts:284-296`；`worker-store.ts:67-80`（**无任何并发/上限判定**） | **能** | PM 在 watchdog 窗口里手工派卡并沿用 `ap-` 命名；两次实测（F1.1/F1.2） | **是**（E2 4/2 与 3/2 的主因；RQ-5 F2-E1、RQ-7 F1.3 同源） |
| **C2** | TS 后台扫描：`dispatchNewTasks`（PM 窗口 `agent_settled` 触发，对每个 key 的**全部**未入队 task.md 逐个 upsert） | `pm-orchestrator.ts:393-478`（`:464` 的 `for` 循环无计数；`:435` 仅跳过 `origin: conductor`） | **能** | PM 先手工写 task.md（含 `ap-` 命名的目录名），下一次 settle 被扫描入队 | 未直接实证（本卡 5 条 E2 手工行由 E3 判据**排除**了它，见 F2） |
| **C3** | `reconcile_orphans` 回插 `status:"pending"` 行 | `conductor.py:4021-4055`（锁 `.mw/workers.lock`，`:4032`）；调用点 `:200`（**在 `rows = parse_workers_file(...)` `:203` 之前**） | **能** | 存在"有 task.md（`origin: conductor`）、无队列行"的孤儿，且此时已有 ≥cap 个 key 在飞（行通常由丢更新/`archive_stale_entries` 删除造成） | 否（E2/FM timeline `reconcile` 事件 **0 次**） |
| **C4** | xkey 提案通道：`_xkey_proposal_one`（每个 `approved` 且无 `proposal.md` 的 ticket 派 1 个） | `conductor.py:3031`（`dispatch.dispatch(project_root, source_key, ...)`）；被 `:243-254` 的 `if cfg["xkey_repair"]` 段在**读取 `rows` 之后、计算 `in_flight_keys` 之前**调用 | **能** | `xkey_repair=true` 且同一 tick 有多个不同 `source_key` 的 approved ticket；新行用**陈旧 `rows`** 判 in-flight ⇒ 本 tick 完全不计入，下一 tick 才计入（此时可 > cap）。另受 `_XKEY_PROPOSAL_MAX_ATTEMPTS=2`/ticket（`:2872`）与 stem 家族判定（`:3010`）约束 | 否（E2/FM `config.json` 均无 `xkey_repair` ⇒ 默认 false） |
| **C5** | 两个 conductor 实例 | `conductor.py:4125-4128`（无条件写 pid）；`mw.py:210-216`（非原子 pid 门禁）、`:170-174`（serve 闸门） | **能（瞬时 ≤2×cap）** | 两个 `mw serve` 抢跑，或手工起第二个 conductor，或 serve 进程被复制（如 `mw start` + `mw serve` 并存） | 否（F3：启动计数 1:1、单 beat 网格） |
| **C6** | `_advance_key` / `execute_loop` / `_verify_loop` 内部分支派发 | `:936/974/1006/1111/1604/1640/1669/1706/1745/1753` | **否（负结论）** | 每个分支**只派 1 张**、key 恒为当前 loop 的 key、派发成功后由 `:292` 就地 `in_flight_keys.add(key)` ⇒ 同 tick 内计数守恒 | —— |
| **C7** | launcher `update_status`（`pending→running`、`→failed`）；`archive_stale_entries`（删行） | `mw_common.py:1512-1527`（`for entry in entries` 只改已存在行）；`:1529-1563`（`kept = [e for i,e ...]` 只减）；调用点 `launcher.py:601/788/801/833/975/981` | **否（负结论）** | 二者都不能**新增** `task_key`；`update_status` 的"中间态"只是 `pending` 窗口（RQ-7 实测 0.12–5.18s），窗口内 key 数不变 | —— |
| **C8** | `_dispatch_roadmap_writer`（无 roadmap / 提案被 reject 时） | `conductor.py:548`（`dispatch.dispatch(..., dispatch.SCRATCH_OWNER, ...)`），调用点 `:207`、`:474`（`_activate_pending_stage`，随后 `orchestrate` 立即 `return`） | **否（负结论）** | owner = `_scratch`（`dispatch.py:109/126/399-406`）⇒ task_key 形如 `ap-_scratch-roadmap-s1-a1`、`task_path` 在 `_scratch/workers/` 下 ⇒ 不命中任何 roadmap key ⇒ **永不进 `in_flight_keys`** | —— |

**计数**：可行路径 **K = 5**（C1-C5；C1/C2 是同一 TS 通道的两种入口），已实证 **1 类（C1，2 个越界时刻）**，证伪 **3 条**（C6/C7/C8）。另有**代码之外**的一条：人直接编辑 `_workers.parallel`（不在任何 writer 清单内，无证据、无留痕机制）。

### F6 对既有笔记的两处修正（本卡实证，供 spec 回改）

1. **锁名修正（RQ-5 F4 #11 / spec 风险 8）**：RQ-5 写"`conductor.py:4032` 用 `.mw/conductor-workers.lock`，与 `mw_common.py:1440` 的 `.mw/workers.lock` 不是同一把"。实测：`lock_file(project_root, name)` = `project_root/.mw/{name}.lock`（`conductor.py:116-118`），`reconcile_orphans` 调的 `acquire_conductor_lock(root, "workers", ...)` 因此就是 **`.mw/workers.lock`**；`grep -r "conductor-workers"` 在 `packages/**` **零命中**，`git log -S "conductor-workers"` **零命中**（该文件名从未存在）。⇒ 该"锁不一致"不成立，spec §4 风险 8 应删除（GC-3 的该条前置缺口不存在）。
2. **"面板 8/2 是被观测到的显示分歧"这一措辞（RQ-7 F3 表）**：FM 2026-09-19 的 8/2 发生在 **autopilot 未启用、config.json 不存在** 的时期，此时 `monitor.ts:586` 只在 `s.autopilot.enabled` 时渲染 `slots` 行 ⇒ 8/2 是**公式算值**，没有任何人从此面板看到它（与 MW 4/2 的"潜在分歧"同型，RQ-7 已对 MW 标注、对 FM 09-19 未标注）。⇒ 引用时应标"潜在/算值口径"，否则会把"PM 手工 fan-out 期"的键层计数误读成"conductor 挡住了 6 个 key"。

### F7 复算命令（自包含，只读；均在 `python -` stdin 下运行过）

```python
# 1) 越界窗口的行集合（E2 / FM：区间与窗口相交）
import pathlib, datetime
def parse(s):
    s = s.strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(s)
def window(root, lo, hi):
    p = pathlib.Path(root) / ".agenticdoc" / "_workers.parallel"
    lo, hi = parse(lo), parse(hi)
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()):
        c = [x.strip() for x in line.split("|")]
        if len(c) not in (7, 8): continue
        try: a = parse(c[5]); b = parse(c[6]) if c[6] else None
        except Exception: continue
        if (b or a) >= lo and a <= hi:
            print("L%-4d %s | %s | %s | %s | %s" % (i, c[0], c[1], c[5], c[6], c[3]))
window(r"H:\git\E2Feature", "2026-09-25T03:30:00Z", "2026-09-25T03:50:00Z")

# 2) 进程区间 = [END - elapsed, END]；再求 N 路共同重叠
import re
TSP = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"
END = re.compile(r"\[END\]\s+" + TSP + r"[^\n]*elapsed=(\d+)s")
def span(root, rel):
    txt = (pathlib.Path(root) / ".agenticdoc" / rel / "trace.log").read_text(encoding="utf-8", errors="replace")
    m = END.search(txt); end = parse(m.group(1))
    return end - datetime.timedelta(seconds=int(m.group(2))), end
# 取 F1.1 的 4 条 -> max(start), min(end) 即共同重叠（实测 150.0s）

# 3) 三类判据：时间戳格式 / timeline dispatch 事件 / task.md origin + mtime
import json, glob
MS   = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$")   # TS writer
SEC  = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")  # conductor writer
EVENTS = [json.loads(l) for f in sorted(glob.glob(root + "/.agenticdoc/_autopilot/timeline.jsonl*"))
          for l in open(f, encoding="utf-8", errors="replace") if l.strip()]
hits = [e for e in EVENTS if "<task_key>" in str(e.get("detail", ""))]  # 无命中 => 非 conductor 派发
taskmd = pathlib.Path(root) / ".agenticdoc" / "<key>/workers/<task_key>/task.md"
head = taskmd.read_text(encoding="utf-8", errors="replace").splitlines()[:5]   # 'type: coding' + '' => PM 侧
mtime = datetime.datetime.fromtimestamp(taskmd.stat().st_mtime, tz=datetime.timezone.utc)  # 与 dispatched_at 差 <=3ms

# 4) 多实例判定：conductor 启动次数 vs mw.log spawn 行数 vs beat 网格
gs   = [e["ts"] for e in EVENTS if e["ev"] == "goal-snapshot" and str(e.get("detail", "")).startswith("startup baseline")]
spawn = sum(1 for l in open(root + "/.mw/mw.log", encoding="utf-8", errors="replace") if "conductor spawned" in l)
beats = [parse(e["ts"]) for e in EVENTS if e["ev"] == "beat"]
deltas = sorted((beats[i+1] - beats[i]).total_seconds() for i in range(len(beats)-1))
# 单序列 => deltas 只有 4/5（+极少世代交接异常）；双 conductor => 大量 0-2s delta

# 5) 归属比较：conductor 口径 vs 面板口径（RQ-7 脚本 + F1 的行集合）
TERM = ("done", "failed", "needs-clarification")
belongs = lambda r, k: r[0].startswith("ap-%s-" % k) or (".agenticdoc/%s/workers/" % k) in r[4].replace("\\", "/")
```

实测输出（本卡使用的关键数字，全部由上述片段产出）：

- E2 4/2：4 条行的 `dispatched_at` = `03:31:28+00:00` / `03:37:37+00:00` / `03:40:03.390Z` / `03:40:11.098Z`；进程 4 路重叠 **150.0s**（03:40:13.695 → 03:42:43.695）。
- E2 3/2：3 条行 = `06:52:21+00:00` / `06:52:25+00:00` / `06:52:34.032Z`；3 路重叠 **331.0s**。
- FM 3/2：3 条行 = `02:50:28+00:00` / `02:54:44+00:00` / `03:04:01.702Z`（第三条 `_scratch`）；3 路重叠 **113.0s**。
- FM 8/2：8 条行全部 TS 毫秒格式、全部非 `ap-`（`dispatched_at` 08:01:34.508Z .. 08:02:20.635Z）。
- timeline 事件直方图：E2 97050 条 = `{beat 83664, config 6539, advance 6335, dispatch 427, gate-created 18, gate-answered 18, stalled 13, resume 13, l3-no-verdict 10, goal-snapshot 9, stage-close 4}`（**无 `reconcile`/`skip`**）；FM 全量无 `reconcile`。
- E2 beat delta：`{4:57583, 5:26056, 6:20, 7:8, 8:1, 2:1, 1:1}`；FM `{4:28554, 5:20895, 6-11:~4400, 12:1, 13:2, 34:1, 328:1, 2:1}`。
- E2 `goal-snapshot(startup)` = 9 = `mw.log` 的 `conductor spawned` 行数 9；FM = 6/6。

## 结论 → 决策映射

### 逐条回 RQ-9

| 问题 | 结论 | 关键锚点 |
|---|---|---|
| Q1 谁写的 | E2 4/2 = 2 条 conductor（a）+ 2 条 PM 手工复用 `ap-`（b）；E2 3/2 同型（a=2,b=1）；FM 3/2 = a=2 + 1 条 `_scratch`（b，且**不计入 conductor 口径**）；FM 8/2 = 8 条 PM 手工（b，**当时无 conductor**） | F1 逐行表 + F2 判据 + E1/E2/E3 三链 |
| Q2 多实例 | **不存在**（无并发 tick 的实例）；同世代内确有"死后 1s 重启"（E2×1、FM×2 世代） | 启动计数 9/9、6/6；`mw.py:170-174`；beat 单序列 |
| Q3 旧构建 | cap 语义**一致**（`4c7c07c43` 2026-09-10 起未改，磁盘无第二份 Python 副本）⇒ 旧构建**不能**解释 4/2；精确 checkout **无法判定** | `git blame` 三段；`dist/` 只有 TS；`serve.meta` 覆盖写 |
| Q4 可复现路径 | **K=5** 可行（C1 PM 手工 `ap-` 行【已实证】/ C2 后台扫描 / C3 `reconcile_orphans` / C4 xkey 提案 / C5 双 conductor）；C6/C7/C8 证伪 | F5 表 |
| Q5 真缺陷? | **cap gate 本身不是真缺陷**（它从未在 cap 内派第 3 个 key）；4/2 是 **(b) 逃逸口的表现**，并暴露两个未登记语义缺口：(i) 前缀归属使 PM 行**既越界又消耗** conductor 配额；(ii) 行无 writer 字段 ⇒ 归属不可机器判定 | F5 C1、`conductor.py:2136`、`worker-store.ts:22-37` |

### 支撑 AC-004（占槽判定 + 频率）

- **占槽谓词**（与 key-status 无关，与 RQ-1/RQ-6 一致，本卡独立复核）：`conductor.py:258-264` ∩ `:2131-2132`（非终态，含 `pending`）∩ `:2135-2139`（`ap-` 前缀 **或** `task_path` 命中 `.agenticdoc/{key}/workers/`）。
- **新增可交付物：越界的"谁占着槽"是可知的**，共 2 个窗口（E2），占槽明细逐行给出（F1.1/F1.2）。这对 AC-004 的"stalled / done / 在飞 三类占槽表"补上了"外部 writer 的行也占槽、且能点名"这一刻的空缺。
- **频率实测（补 RQ-6 的 stall 口径）**：E2 100h 窗口内 **2 次** conductor 口径越界（各 155.9s / 331s 的行口径重叠），**两者都由 b 类造成**；FM 0 次（其两次 `>max` 都是面板口径）。⇒ "cap 越界"在实测里**不是** conductor 的行为，而是 PM 通道的副作用。
- 注意限制：`in_flight_keys ≥ cap` 的**持续时长**可算（03:40:11→03:42:47 等），但"因 cap 而未派发的 tick 数"**仍不可重建**（历史 eligibility 被覆盖写抹掉，RQ-7 F4.2(3)），本卡未推翻该结论。

### 支撑 AC-013（逃逸口与双写源）

- **逃逸口 #1（PM 手工通道无并发判定）现在是"可穷举的 5 条实测样本"**，而非一处泛指：E2 `ap-` 手工行 = L407（03:19:11.794Z）、L413、L414、L470（2026-09-26T02:12:28.269Z）、L480；共同形状 = TS 毫秒时间戳 + timeline 零命中 + 裸 `type: coding` + `mtime≈dispatched_at`（≤3ms）+ stem 在 conductor 词表之外。**这是 AC-013 需要的"实测复算样本"的一种新形态（写者归属样本）**。
- **逃逸口 #1 的第二个面向（本卡新增）**：PM 手工行若沿用 `ap-{key}-` 命名，会被 `conductor.py:2136` 的前缀规则**计入** `in_flight_keys` ⇒ 越界记账 + **消耗 conductor 的 cap 配额**（03:40:11 起的饱和即含这 2 条外部行）。⇒ 逃逸口不是"旁观者"，它会污染主通道的准入判定。
- **修正**：spec §4 风险 8 / RQ-5 F4#11 的"两把锁"结论不成立（F6.1）⇒ AC-013/AC-014 的"锁一致性"前置缺口应删除或重写。
- 未判定项：**行提前终态化的 writer**（RQ-5 数据缺口 1）本卡未介入，仍为"无法判定"。

### 支撑 AC-012（可观测性）

- 面板/doctor 现在**无法**回答"这行是谁写的、算不算 conductor 的槽"：`_workers.parallel` 列序 `task_key|status|cli|provider|task_path|dispatched_at|updated_at|model`（`worker-store.ts:22-37`）**没有 writer/origin 字段**；本卡只能靠时间戳格式与 task.md 字节形状取证 ⇒ 建议的最小补面 = 在行上加 `writer`（`conductor|pm-manual|pm-scan|reconcile|launcher`），或（次选）把 `origin:` 的判定从 task.md 前移进行写入路径。
- 越界必须被**区分解释**：同一时刻 `slotsUsed` 与 `len(in_flight_keys)` 都可以 >cap，但成因集合不同（面板：手工行另计一槽；conductor：仅 b 类行）；面板要显示的第一个数应带口径标签（RQ-7 F5.2 已给方案），本卡补充"仍需两个数 + 占用明细的 writer 归属"。
- 不新增误报的前提不变：无 roadmap/autopilot off 时**不能**显示 `0/2`（MW/OC/UEM/LT 都是这种项目，见 F1.5）。

### 支撑 AC-002（成因三态）

- `max_parallel_keys=2` 的**执行**是 **conductor-local 准入控制**：唯一 gate 在 `:289-290`，只约束 `_advance_key` 的调用；它**不**约束 PM 通道（C1/C2）、**不**约束同 tick 的 xkey 通道（C4）、**不**约束第二个 conductor（C5）。⇒ 任何"把 cap 当作全局并发上限"的设计假设都不成立（这是 (d) 的直接推论：真实 worker 层并发 = 三条互不知情通道的并集，RQ-5 F3 已实测）。

## 数据缺口

1. **09-25 那次 serve 的 argv / code_dir / 工作树 diff 不可恢复**（`serve.meta` 每世代覆盖、`mw.log` 无该字段）⇒ "精确构建"无法判定。**所需证据**：当时 `.mw/serve.meta` 的副本、进程表快照、或 `mw.log` 增加 code_dir/argv 字段（后者是 design 期可落地的小改）。
2. **`conductor-spawned` 与 `goal-snapshot` 之间没有共享 PID**：本卡用"数量 1:1 + 次序 + beat 网格"间接绑定 PID（如 E2 的 12984/100048 ↔ 03:03:43/15:24:28）。要直接绑定，需要 `conductor.log`/`mw.log` 记录 PID 与时间戳（现在 `conductor.log` 恒 0 字节，`mw.log` 无时间戳）。**所需证据**：日志加时间戳即可闭环。
3. **`reconcile_orphans` 与 xkey 两条路径在 E2/FM 都 0 次触发**（前者无 `reconcile` 事件、后者配置默认关闭）⇒ C3/C4 的"能越界"是**代码面证明**而非实测。要实证需：① 制造"有 task.md 无行"的孤儿 + ≥cap 在飞（可复制项目目录做受控实验）；② 临时开启 `xkey_repair=true` 并造 2 个不同 `source_key` 的 approved ticket。
4. **`ap-` 手工行的具体入口（`dispatch_worker` vs 后台扫描 vs 人手写 task.md）**：本卡用 E3（mtime≈dispatched_at，差 ≤3ms）排除了后台扫描（它不写 task.md），用 `manual-<epoch>` 命名规则排除了 `/worker`（`ui-bridge.ts:1611`），但**无法区分**"`dispatch_worker` 写 task.md"与"PM 先用 `write` 工具写 task.md、又在 3ms 内触发 `dispatch_worker`"（后者不现实但形式上未排除）。**所需证据**：给 `_workers.parallel` 加 writer 字段。
5. **本卡未覆盖 JCA 的越界检查**（其 timeline 只有 3 个 generation，`seq 98074..298291`，更早事件被 rotation 剪掉）⇒ JCA 是否存在同类 b 类行未能判定。
6. **"越界是否真的损害了吞吐"未量化**：03:40:11→03:42:47 的 cap 饱和是否让某个 eligible key 延迟派发，**无法重建**（同 RQ-7 F4.2(3)）；本卡只能证明"当时存在 ≥cap 的在飞 key"与"cap 分支在该窗口持续短路"。

## 机器行

```
[VERIFY] RQ-9: rows_attributed=18(a=6,b=12,c=0,d=0) multi_conductor=no(no overlapping ticks; sequential death+1s respawn only) cap_paths=5(C1 dispatch_worker=EMPIRICAL 2 windows / C2 dispatchNewTasks / C3 reconcile_orphans / C4 xkey proposal / C5 two conductors) cap_paths_refuted=3(C6 _advance_key internal branches / C7 update_status+archive_stale_entries / C8 _dispatch_roadmap_writer) 真实缺陷=no(cap gate never dispatched a 3rd key)/yes(2 unregistered semantic gaps: prefix-ownership counts foreign ap- rows -> both breach AND consume conductor quota [conductor.py:2136]; _workers.parallel has no writer/origin column -> attribution only via timestamp-format forensics [worker-store.ts:22-37]) e2_4of2=2026-09-25T03:41:28Z rows=a2(L411 ap-feature-l3-verdict-source-fallback-plan-writer-a1 03:31:28+00:00;L412 ap-feature-gui-time-mvp-board-005-services-mvp-ledger 03:37:37+00:00)+b2(L413 ap-feature-sampling-human-channel-repair-a2-achieved-terminal 03:40:03.390Z;L414 ap-feature-cigate-install-kit-repair-a3-achieved-terminal 03:40:11.098Z) trace_4way_overlap=150.0s row_4way_overlap=155.9s e2_3of2=2026-09-26T06:52:34Z rows=a2+b1(L480 ap-feature-gui-time-mvp-board-unratified-disclosure) trace_3way=331.0s fm_3of2=2026-09-26T03:04:01.702Z rows=a2+b1(xkey-n1-hitl-groups-repair task_path=_scratch/ -> conductor caliber=2=cap, NOT a breach) fm_8of2=2026-09-19T08:02:20Z rows=b8(all PM manual, no ap-; FM timeline seq=1 is 2026-09-23T09:06:44Z -> conductor absent, autopilot disabled -> computed-only) criteria=timestamp-format(iso_now seconds +00:00 vs toISOString ms Z) AND timeline-dispatch-event AND task.md(origin:conductor + first-line ---) AND taskmd_mtime(<=3ms from dispatched_at => same dispatchTask call, excludes background scan) multi_instance_proof=goal-snapshot(startup)=9==mw.log spawn=9 (E2), 6==6 (FM); beat deltas E2 {4:57583,5:26056,+3 anomalies only} single grid; mw.py:170-174 pid_alive gate; conductor.py:4125-4128 no singleton guard old_build=excluded(cap predicate blame 4c7c07c43 2026-09-10 unchanged; no second conductor.py on disk; dist has only TS) precise_checkout=undeterminable(serve.meta overwritten per generation) correction_RQ5_F4#11=conductor.py:4032 uses .mw/workers.lock == mw_common.lock_path (lock_file:116-118); "conductor-workers.lock" has 0 hits in tree and git history
```

**数据来源时效**：本文件所有行/进程/事件数值来自 2026-09-26 本次运行的只读探测（E2 `_workers.parallel` 486 行、timeline 97050 事件；FM 232 行 / 53836 beat 等，见 §数据快照 与 F7 复算输出）。本卡**未**写任何代码文件、**未**改 E2/FM 的任何文件、**未**答任何 gate、**未** commit。