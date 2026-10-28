# RQ-1 编排面勘察：扇出/汇合今天能挂在哪

- Key: `claim-driven-review-orchestration`
- 类型：research（只读勘察，2026-10-22）
- 唯一证据文件：本文件
- 目标锚点：`.agenticdoc/goal.md`（「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」）

本文件先给结论表，再按 RQ-1 的六个要求分节展开（每节带 `path:line`），最后两节声明残留与未覆盖面。
行号以当前工作树的 `rg -n` 为准；与派发卡里引用的行号有偏差的地方（`claimsGaps` 实为 987、`claimSettlementGaps` 实为 1056、`isSameOrUnder` 实为 89）在正文标注，不按卡片行号硬凑。

## 结论

| # | 问题 | 结论 | 证据锚点 |
|---|---|---|---|
| 1 | 派发入口有几条通道 | 实际是 **两条写通道 + 一个服务层复查点**：`dispatch_worker`/`/worker`（TS，写 task.md + 队列行）、conductor `dispatch()`（Python，写 task.md + 队列行）、以及 launcher `_poll_once` 的 G-3 复查（只判不写，不合规就 `failed`）。两条写通道**共用**同一个 9 列队列格式、同一把 `.mw/workers.lock`、同一个 spawner | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3086`, `:3839`；`packages/multi-workers/autopilot/dispatch.py:1917`；`packages/multi-workers/launcher.py:2531`, `:2676`, `:2797` |
| 2 | 两条通道的字段级差异 | 队列行字段完全同构（`task_key|status|cli|provider|task_path|dispatched_at|updated_at|model|origin`），差异只在**谁判断、谁定价、谁命名**：TS 侧跑 `claimsGaps` 判据（advisory 警告/enforce 拒绝），Python 侧**只用 claims 定 caps，不跑任何 claims 判据**；任务身份 `ap-<owner>-<stem>` vs 调用方给定；`origin` 列 `conductor` vs `manual` | `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:32`, `:130`；`packages/multi-workers/mw_common.py:2012`, `:2119`；`dispatch.py:1659`, `:2171`；`ui-bridge.ts:2905`；`dispatch.py:2095` |
| 3 | 一个 task 能否扇出 N 个兄弟 task | **队列层允许，没有任何模式改动**：一行 = 一个 worker 进程，`task_key` 唯一即可；没有「逻辑任务/父任务」列，同一个卡片可以被多行引用。**手工通道没有 join**（PM 自己排队等）；**conductor 通道已经有 fanout + join**（卡片头 `deps:` → frontier → done 才就绪） | `worker-store.ts:26-34`；`packages/multi-workers/autopilot/task_graph.py:317`, `:489`, `:595`；`packages/multi-workers/autopilot/conductor.py:2010`, `:2031`, `:2036` |
| 4 | 现成的汇合/join 语义 | conductor 的 `deps:` + `frontier` 就是 join（前置全部 `done` 才进 frontier，宽度 `min(max_workers_per_key,|frontier|)`）。`_workers.acked` 是「PM 已消费」侧车（防重 spawn / 把行收敛成终态），**不是 join**；`_workers.stale.parallel` 是「task.md 不存在 → 归档」的垃圾回收，**不是 join，也不是失败裁决** | `conductor.py:2010`, `:2031-2055`；`mw_common.py:2153`（acked）、`:2512`（stale）；`launcher.py:2627-2658` |
| 5 | `claims > 5` 门禁落点 | 落在 `claimsGaps` 的 advisory 数组（`claimBudgetCaps` 之前），新增 token `claims:count:<n>>5`。**与 `CLAIM_BUDGET_SUM_MAX=40` 不打架**（一个是取数预算重量、一个是计数），但会让 budget-sum 作为「拆分信号」变冗余（非 manual 卡要到 41 条才触发）；`n>5` 恰好是「每 claim 6 次取数不再被 fileCap 兜住」的第一个整数（n=5 → 30/5=6，n=6 → 30/6=5） | `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:987`, `:817`, `:1022`, `:1042`；`dispatch.py:718` |
| 6 | 20 条卡今天的实际命运 | **照派，不拒也不拆**。`Σ预算=20`（全非 manual）不触 40；`fileCap=min(30,6×20)=30` → 每 claim **1.5** 次取数；`byteCap=393216` 饱和；收尾大面积 `unverified: budget` + ② `unverified-ratio>40%` gap。没有任何一条判据在这条路径上拒绝它 | `dispatch-card.ts:1022-1023`, `:1042-1049`；`worker-mode.ts:1086-1098`；`ui-bridge.ts:2905-2926` |
| 7 | merge 单元能否只放 `workers/<task>-u*/report.md` | **能，必须逐文件枚举**：`isSameOrUnder` 是「等值或 prefix+分隔符」的文件级判定，`read_scope: <report.md>` 就是精确放行这一个文件。但通配符**不做 glob 展开**（`workers/<task>-u*/report.md` 是字面路径，永不命中）；且必须额外放行 merge 自己的 `task.md`（worker 靠 read 工具读它）与 `l2_read_file_cap ≥ k+2` | `worker/read-scope.ts:89-93`, `:100-116`, `:118-121`, `:167-214`, `:31-32`；`launcher.py:2109`；`worker-mode.ts:3015`（扩展自己读，不计费） |
| 8 | `worker_file` 与 read 白名单差异 | 两套完全独立：`worker_file` 只允许「本任务目录下的 `progress.md|report.md|report-<slug>.md`」+「`<key>/evidence/**`（两种基址）」，再被 `write_scope:` 收窄；read/ls/find/grep 由 `read_scope:`（任意路径）+ `deny_globs` 控制，没有文件名白名单。**两套都不允许 merge 写兄弟单元的 report.md**（这正是 AC-008 需要的只读语义） | `shared/write-surface.ts:353-390`, `:54`, `:429`；`worker/worker-file-tool.ts:88-125`；`read-scope.ts:167-214` |
| 9 | 可复用物 / 空白 | 可复用：`parseClaimsBlock`/`claimsGaps`/`claimBudgetCaps`、`readDispatchCard`、`writeDispatchTaskMd`、`claimReadScope`、`_read_scope_caps`、`task_graph`+`execute_loop` frontier、`card_audit`。空白（确实不存在）：拆卡函数、merge 卡模板、子卡 id 重映射、`[SPLIT]` 行与 `split:*`/`merge:*` 判据、Python 侧 claims 判据 | 见 §5 表 |
| 10 | 主要风险 | ① 未声明 `write_face` 的 review 子卡会被**同 key serial-only 守卫**挡成串行（实测断言）；② 子卡 stem 若共用数字核心（`T-02-u1`/`T-02-u2` 同为 `02`）→ task_graph ambiguous → **整 key 退化为串行**；③ 母卡留在 `tasks/` 会被当独立单元派发；④ 子/母卡 `card_sha256` 之间**没有链**；⑤ k 个单元 = k 份固定开销（各一份看门狗/启动/读卡） | `pm/task-dispatcher.ts:447-459`；`test/suite/write-face-pm-gate.test.ts:422-435`；`task_graph.py:340-353`, `:547-556`；`conductor.py:2047-2055`；`worker-mode.ts:396-404` |

## 证据

### 0. 一张总图

```
                ┌───────────────────────────────┐
PM/agent ──►    │ dispatch_worker  (TS tool)     │──► writeDispatchTaskMd  → {key}/workers/<task_key>/task.md
                │ /worker          (TS command)  │──► dispatchTask → WorkerStore.upsertWithinLock →
                └───────────────────────────────┘        .agenticdoc/_workers.parallel  (origin=manual)
                                                                        │
conductor ──►   dispatch.dispatch()  (Python) ──► render_task_md → task.md (origin: conductor)
   execute_loop                                   upsert_worker_row → _workers.parallel (origin=conductor)
                                                                        │
everyone ──►    launcher._poll_once  ──► 读 _workers.parallel 的 pending 行 ──► G-3 复查 ──► _spawn(cli)
```

- TS 侧唯一写点：`ui-bridge.ts:2996 writeDispatchTaskMd`；两条 TS 入口都走它（工具 `:3315`、命令 `:3839`）。
- Python 侧唯一写点：`dispatch.py:1434 render_task_md` + `:1917 dispatch()`；队列行在 `:2158` 组装、`:2262` 落盘。
- 唯一的消费者：`launcher.py:2531 _poll_once`（pending → `_spawn` at `:2703`），两条通道的行在 spawn 阶段没有区别。

### 1. 派发入口全图（要求 1）

#### 1.1 `dispatch_worker` 工具通道（TS）

工具注册在 `ui-bridge.ts:3086-3089`（`/worker` 命令是同一实现的第二入口，`:3675` 起）。`execute` 的判据顺序（全部在任何写盘之前）：

1. RAG 配置门 `:3175`；
2. owner key 解析 `:3179` + 跨 key 写守卫 `:3185`（`foreignLiveClaimRefusal`, `:807`）；
3. cli 白名单 `:3188`、`type` 解析 `:3199`（`resolveDispatchType`, `:1691`）；
4. 阶段文档门 `:3210`（`dispatchDocGaps`）；
5. 任务目录已存在即拒 `:3228`（`taskDir` 由 `:3227` 的 `workerTaskDir` 算出——**这就是「一个 task_key 只能一个任务目录」的硬边界**）；
6. writeless 角色的写入意图判定 `:3251`（`judgeWriteIntent`, `:2165`）；
7. **卡片门** `:3281` → `readDispatchCard`（`:2864`）：envelope + 每类型 extras + seed 最小项 + claims 判据；
8. 模型计划 `:3293`、DP-1 旁路建议 `:3313`；
9. 写 task.md `:3315`（含 read_scope/caps、card_path/card_sha256/envelope_producer/write_face）；
10. 入队 `:3341` → `dispatchTask`（`pm/task-dispatcher.ts:291`）→ `.mw/workers.lock`（`:311`）→ write-face 判据（`:320`）→ `upsertWithinLock`（`:324`）；
11. 入队失败回滚 task 目录 `:3346`（`cleanupRefusedTaskDir`, `:2755`）；
12. 回执 + claims 回执行 `:3359-3364`（`claimsReceiptLine`, `:2979`）。

产物（一份 task.md + 一行队列）：

- task.md 头：`type/phase/images/model`（`planDispatchFrontmatter`, `:1733`）、`card_path`/`card_sha256`（`mergeCardHeader`, `:2738`）、`envelope_producer: agent-team-loop-pm@<VERSION>`（`:2655`, `:2668`）、`write_face`（`cardWriteFaceEntries` `:2689` → `:2738`）、`read_scope` + `l2_read_file_cap`/`l2_read_byte_cap`（`mergeReadScope`, `:2249`）、`decision`（`mergeDecisionHeader`, `:2308`）、`write_scope`（shell writeless 角色，`:2203`）。
- 队列行：`worker-store.ts:130-143` 序列化 9 列，`origin` 恒为 `manual`（`normalizeWorkerOrigin`, `:48-50`）。

**claims 判据在 TS 侧是会拒绝的**：`readDispatchCard` 用 `claimsGaps(..., enforce:true)` 跑一次（`ui-bridge.ts:2905`），enforce 模式下并进 `missing` 并返回 `dispatch-claims`（`:2906-2920`）；advisory（默认，`dispatch-card.ts:565` `CLAIM_GATE_DEFAULT`）只把同一批 token 放进 `warnings`（`:2909`），照派。

#### 1.2 conductor 通道（Python）

`dispatch.py:1917 dispatch()` 的判据顺序（同样零副作用，`reject()` `:1961`）：

1. `run.json` 终态/在跑 `:1981-2000`；
2. 类型注册表 `:2003-2014`（`REGISTRY`，conductor 不可派的类型也在此拒 `:2013`）；
3. verifier 必须有 `read_scope` `:2020-2023`；
4. `decide_prepare` 的卡片四项 `:2029-2036`；
5. target.yml/profile `:2042`, `:2069`；
6. `worker_timeout_min` `:2081`；
7. 读卡 `:2088`（`dispatch_card`, `:1138`：卡片身份固定为 `<key>/tasks/<stem>.md`，`:1163`）；
8. **claims 只用来定价**：`:2095-2098`（`card_claims` → `claim_gate()` 仅打印 diagnostic → `_read_scope_caps`）；
9. 渲染 task.md `:2138`（`render_task_md`, `:1434`）；
10. 队列行组装 `:2158`，`origin: conductor` `:2171`；
11. 拿锁 `:2174`（`mw_common.acquire_lock`, `mw_common.py:2388`）→ write-face 判据 `:2191`（`_write_face_verdict`, `:1797`）→ duplicate-dispatch 身份守卫 `:2223-2247` → 写 task.md `:2245-2246` → `upsert_worker_row` `:2262`；
12. 读回校验 `:2275-2286`。

**关键不对称（对 RQ-1 的结论 5 有直接影响）**：`dispatch.py` 里没有 `claimsGaps` 的对应物——grep 全文件只有 `parse_claims_block` / `claim_budget_caps` / `claim_gate`（`:661`, `:718`, `:743`），没有任何 structural/advisory 判据，也没有 `claims:budget-sum` / `claims:manual-overflow` 这些 token。服务层 `launcher.py` 的 G-3 复查（`:1889 classify_envelope_refusal`）也只判 envelope，不认 claims（全文件无 `claim` 字样）。所以**今天 claims 判据只存在于 TS 通道**；把 `n>5` 加进 `claimsGaps` 不会自动让 conductor 通道生效。

#### 1.3 字段级差异表

| 维度 | `dispatch_worker` / `/worker`（TS） | conductor `dispatch()`（Python） |
|---|---|---|
| 入口 | `ui-bridge.ts:3086`（工具）/ `:3675`（命令） | `dispatch.py:1917`，由 `conductor.py:2075` 的 execute_loop 调用 |
| 任务身份 | 调用方给的 `task_key`（`:3093`），目录 `{key}/workers/<task_key>`（`:3227`） | `ap-<owner>-<stem>`（`:1659`），stem = `tasks/<stem>.md`（`:1163`） |
| 卡片来源 | 参数 `card_path`（必填，`:3098`） | 由 stem 推导 `<key>/tasks/<stem>.md`（`:1163`），缺卡则 synthesized（`:1359`） |
| 卡片判据 | envelope+extras+seed（`:2898`）+ claims（`:2905`） | 无（envelope 判据在服务层 launcher G-3 `:2676`） |
| claims 用途 | 判据（advisory/enforce）+ caps（`:2905`, `:2908`） | **只有 caps**（`:2095-2098`） |
| caps 来源 | 只由 claims 推导 `claimBudgetCaps`（`:1042`） | 项目配置优先，再 claims 兜底（`_read_scope_caps` `:813`） |
| `read_scope` | 由 claims locator 推导（`claimReadScope` `:2359`） | 调用方传入（`dispatch()` 签名 `:1926`），再做 dual/partition 扩写（`_expand_read_scope` `:1587`） |
| `write_face` | 卡片 `## 写入允许面` → `mergeCardHeader`（`:2689`, `:2738`） | 同源 `render_write_face_line`（`:1738`） |
| `envelope_producer` | `agent-team-loop-pm@<VERSION>`（`:2655`, `:2668`） | `autopilot-conductor@<version>`（`:857-890`） |
| task.md 写点 | `writeDispatchTaskMd`（`:2996`） | `render_task_md`（`:1434`）+ `:2246` 写盘 |
| 队列行写点 | `dispatchTask` → `upsertWithinLock`（`task-dispatcher.ts:291/324`） | `upsert_worker_row`（`dispatch.py:2262`） |
| 锁 | `{agenticdocRoot}/../.mw/workers.lock`（`worker-store.ts:153`） | `lock_path()` → `.mw/workers.lock`（`mw_common.py:2005`） |
| `origin` 列 | `manual`（`worker-store.ts:48-50`） | `conductor`（`dispatch.py:2171`） |
| 重试身份 | 无内建（新 task_key + `supersedes:`，`run-store.ts:171`） | `<task_key>-a<N>` 家族行（`conductor.py:1742`） |
| spawn 者 | 同一个 launcher（`launcher.py:2531`, `:2703`） | 同左 |

**谁把行推进 `_workers.parallel`**：TS 是 `WorkerStore.upsertWithinLock`（`worker-store.ts:225`，tmp+rename、按 task_key 替换、保留不可解析行）；Python 是 `mw_common.upsert_worker_row`（`mw_common.py:2451`，同样按行槽位保留）。launcher 只**改状态**（`update_status`, `mw_common.py:2474`）、归档 stale（`:2512`），不新增行。

### 2. 一个 task 能否扇出 N 个兄弟 task（要求 2）

#### 2.1 队列格式：允许，但没有「逻辑任务」这个概念

行格式（9 列，7/8 列兼容）：`task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin`
（`worker-store.ts:32-34`, `:100-143`；Python 镜像 `mw_common.py:2012`, `:2021`, `:2119`）。

- 行的唯一性是 `task_key`（upsert by task_key，`worker-store.ts:225-247`；`mw_common.upsert_worker_row` 同规则）。
- **没有任何列表达「父任务 / 组 / 批次」**；`task_path` 也可以被多行指向（无去重），但 `dispatch_worker` 用 `taskDir exists`（`ui-bridge.ts:3228`）+ 目录名 = task_key，实际把「一行 = 一个独立目录」固定下来。
- 因此「一个逻辑审查任务 = N 个兄弟单元」在**队列层是合法的**：写 N 个 task_key（`<task>-u1..uN`）+ 1 个 `<task>-merge`，就是 N+1 行；今天缺的不是 schema，而是**生成器**和**汇合**。

#### 2.2 手工通道没有汇合

- `dispatch_worker` 不认任何依赖：参数表里没有 `deps`/`depends_on`（`:3093-3160`）；`execute` 里也没有任何「等其它 task 状态」的分支。
- PM 侧只有 `list_tasks`（`:3405-3410`）能看到兄弟行状态；要 merge 必须 PM 自己轮询 + 再派一次。这就是「手工 join」。
- `supersedes:` 不能借用：它是「替换一个已终态 run」的回滚链（`shared/run-store.ts:171-200`；`pm-orchestrator.ts:1125-1145` 在 settle 时按它写 decision rollback）。拿它表达「子卡属于母卡」会误触发 rollback 语义。

#### 2.3 conductor 通道已经有 fanout + join（这是最重要的可复用面）

`conductor.py:1996-2055`：

- 读全部卡片文本 → `task_graph.validate_task_graph`（`:1999`，`task_graph.py:489`）；
- 卡片头 `deps:`/`依赖:` 由 `task_graph.parse_card_deps`（`:317`）解析，数字核心 join（`join_deps` `:361`）；
- `done_stems`（`:2010-2016`）来自队列 family 行的 `done`；
- `ready = frontier(deps_by_stem, done_stems)`（`:2031`，`task_graph.py:595`）——**前置全部 done 才就绪 = join**；
- `frontier`（`:2036-2040`）再剔除 in-flight；
- 宽度 `limit = min(cap_used, len(frontier))`（`:2055`），`cap_used = max_workers_per_key`（`:1993`）；
- 未声明 `write_face` 的卡不进并行 frontier（`:2047-2054`），全都没声明就 `cap_used=1`（串行）。

所以 AC-002 的「⌈n/5⌉ 个取证单元 + 1 个 merge」在 conductor 通道**只需要写卡片**：子卡 `deps:` 空，merge 卡 `deps: <u1>, <u2>, ...`。不需要新调度器（符合 goal.md GC-5「不引入中心化调度器」）。

#### 2.4 `_workers.acked` / `_workers.stale.parallel` 不是 join

- `_workers.acked`（`mw_common.py:1998-2175`）：`taskKey | ackedAtIso` 侧车，由 TS `AckStore`（`shared/ack-store.ts:19-70`）写。launcher 的用途只有两条：把「已 ack 但行还是非终态」的行收敛成终态（`launcher.py:2627-2645`）、以及**永不重 spawn**（`:2657-2658`）。它是「PM 已消费」的标记，粒度为单 task_key，没有任何「全部兄弟到齐」的聚合。
- `_workers.stale.parallel`（`mw_common.py:1994`, `:2512-2547`）：把 `task.md` 已不存在且非终态的行追加归档并从队列删除（保留原行 + 归档时间 + 原因），由 `_poll_once` 每轮触发（`launcher.py:2564`）。它是垃圾回收，不是 join，也不产生失败裁决。

结论：**join 只有 `deps:`/frontier 一处**；如果想在 TS 手工通道也拿到 join，最小做法是让 merge 卡走 conductor 的 execute_loop（同一 key 的 `tasks/` 里放 merge 卡），而不是给 `dispatch_worker` 加等待逻辑。

### 3. `claims > 5` 门禁的落点（要求 3）

#### 3.1 `claimsGaps` 现在判什么

`dispatch-card.ts:987 claimsGaps`（派发卡引用 `:985` 是 doc 注释区，函数在 987）：

- 结构项（两种模式都报）：`claim:<id>:type|statement|falsifier|locator|judgement|budget`（`:1000-1012`）；
- 软项（只在 `enforce:true` 时返回）：`type-prefix`、`cmd-locator`、`locator-unresolved`、`locator-range`、`tautology`、`claims:budget-sum:Σ>40`（`:1022`）、`claims:manual-overflow:<m>/<n>`（`:1023`）；
- `Σ预算` 口径：非 manual 记 1、manual 记 2（`:996`）；`manualCap = min(4, ceil(n/3))`（`:1023`）。

#### 3.2 与 `CLAIM_BUDGET_SUM_MAX` 会不会打架：不会，但 budget-sum 会失去「拆分信号」作用

| n（全非 manual） | Σ预算 | 触 budget-sum(>40)? | fileCap=min(30,6n) | 每 claim 取数 | byteCap |
|---|---|---|---|---|---|
| 5 | 5 | 否 | 30 | **6.0** | 327680 |
| 6 | 6 | 否 | 30 | 5.0 | 393216 |
| 10 | 10 | 否 | 30 | 3.0 | 393216 |
| 20 | 20 | 否 | 30 | **1.5** | 393216 |
| 41 | 41 | **是** | 30 | 0.73 | 393216 |

（fileCap/byteCap 公式：`:1042-1049`；常量：`:575-581` `perClaim=6, callCap=30, claimByteCap=65536, byteCapMax=393216`。）

三点结论：

1. **不同轴，不冲突**：`Σ预算` 是「这张卡值多少 PM 注意力/计划重量」，`n` 是「要结算多少个可证伪单元」。加 `claims:count:<n>>5` 不改变 `Σ预算` 的语义，也不会让既有卡从「不拒」变「拒」（advisory 默认，`dispatch-card.ts:565`；`ui-bridge.ts:2905-2909`）。
2. **`n>5` 恰是取数模型断点**：`perClaim=6`（D-014）只有在 `6n ≤ 30`（n ≤ 5）时被完整兑现；n=6 起 fileCap 开始削每 claim 的取数。这给「n>5 需拆分」一个数值依据，而不是拍脑袋阈值。
3. **冗余与共发**：非 manual 卡要 41 条才触 budget-sum，而 count 规则在 6 就触发 → budget-sum 以后不再是拆分信号（保留为成本上限即可）；manual 重的卡会与 `claims:manual-overflow` 共发（全 manual 时 n≥3 即 overflow，因为 `manualCap=min(4,ceil(n/3))`），所以 AC-001 要求 count 用**独立 token** 是对的，不要复用这两个。

#### 3.3 20 条卡今天的实际命运（逐步）

1. TS 通道：`readDispatchCard` 通过 → `warnings` 里最多是 locator/tautology 之类（`:2905-2909`），`caps={fileCap:30, byteCap:393216}`（`:2908`）；`claimReadScope` 生成 `.agenticdoc/<key>` + `.agenticdoc/goal.md` + ≤20 个 locator 文件（`:2359-2380`）。
2. task.md 落盘 → 队列行 `pending` → launcher 照常 spawn（`launcher.py:2703`）。
3. worker 读拦截器按 30 次/393216B 放行（`worker-mode.ts:3360-3395`，每 read/ls/find/grep 一次计 1，`:3389-3392`）。
4. 20 条 claim 只有 1.5 次取数预算 → 收尾 `claims:unverified-ratio:u/20>40%` 一旦 u≥9 就触发（`worker-mode.ts:1086-1088`），单条则是 `unverified: budget`；③ `claims:fetches:sum>30` 只拦「多报」（`:1096-1098`）。
5. 墙钟 60m 共享给 20 条（`worker-mode.ts:396`, `:409`），30m checkpoint（`:404`, `:448`）。

**没有任何一步拒绝或拆分它**——这与 spec §1「今天一张 20-claim 卡会被照派」一致，只是补上了账：真正先撞墙的是 fileCap=`30`，`Σ预算` 根本不会响。

#### 3.4 落点建议（只回答「挂在哪」，不设计判据细节——那是 RQ-2）

- 代码落点：`claimsGaps` 的 `advisory` 数组（`dispatch-card.ts:1016-1023` 之间），在循环结束后用 `block.claims.length` 判定，和 `budgetSum`/`manualCount` 同一位置；
- 模式落点：沿用 D-006 灰发（advisory 进 `warnings`，enforce 进 `missing`），无需新开关（`ui-bridge.ts:2905-2920`；`claimGateMode` `:2343`）；
- **必须同时决定 Python 侧怎么办**：`dispatch.py` 没有 claims 判据（见 §1.2），只加 TS 会让 conductor 通道继续无门。要么在 `dispatch()` 的 `:2095-2098` 补一个镜像判据，要么明确「conductor 通道本轮不设门」并记录为已知不对称（RQ-2 待决）。

### 4. merge 单元的读面（要求 4）

#### 4.1 `isSameOrUnder` 的文件级语义：支持

`worker/read-scope.ts:89-93`：

```ts
c === a || c.startsWith(`${a}${path.sep}`)
```

`isWithinScope`（`:118-121`）对每个 entry 做同样判定，`checkReadScopeCall` 的 containment 分支在 `:184-193`。因此：

- `read_scope: .agenticdoc/<key>/workers/<task>-u1/report.md` 精确放行这一个文件；同目录的 `output.md`、`trace.log`、以及父目录 `.../u1` 本身都不命中（后者不满足 prefix+sep）。
- 路径归一化会剥 symlink/junction 并把不存在的尾段拼回最近的已存在祖先（`normalizeForCompare` `:100-116`），所以「report.md 还没生成」也不会误判。

**两个硬限制**：

1. **没有通配符**：entry 是字面路径（`:100` 只有 `path.resolve`/`realpath`，没有 minimatch）；`workers/<task>-u*/report.md` 里的 `*` 是普通字符 → 永不命中。必须把 k 个文件逐个枚举进 `read_scope`。
2. **`ls`/`find`/`grep` 也受同一 containment**：拦的是搜索根（`worker-mode.ts:3360-3394`）。merge 不能 `ls workers/` 去发现单元，只能按卡片里写死的 k 去读。

#### 4.2 还必须放自己的 task.md，并抬 fileCap

- worker 的 agent 是通过 read 工具读 `task.md` 的：launcher 只把绝对路径塞进 starter（`launcher.py:2109-2128`），扩展自己那次 `fs.readFileSync`（`worker-mode.ts:3015`）不计费，但 agent 的 read **计费且受 containment**。
- 所以 merge 的 `read_scope` 最小集 = `{merge 自己的 task.md（或其 worker 目录）, .agenticdoc/goal.md, k 个 report.md}`；`l2_read_file_cap` 默认 8（`read-scope.ts:31`），k=5 时 7 ≤ 8 刚好，k≥7 就会被 `cap-file` 挡（`:194-204`）。**必须显式渲染 `l2_read_file_cap ≥ k+2`**。
- `claimReadScope` **不能直接复用**给 merge：它会先把整个 `.agenticdoc/<key>` 加进 scope（`:2360`），把「只读 k 份 report」放大成「读整个 key」。需要新的 renderer（空白，见 §5）。

#### 4.3 `worker_file` 与 read 的白名单差异

| 面 | 允许 | 拒绝 | 锚点 |
|---|---|---|---|
| `worker_file`（写） | 本 taskDir 下的 `progress.md` / `report.md` / `report-<slug>.md`；`<key>/evidence/**`（项目根相对 + keyDir 相对两种基址）；再被 `write_scope:` 收窄 | 任何带目录分隔符且不落在上述两面的路径（含兄弟单元目录）；内容 >64KiB | `shared/write-surface.ts:353-390`, `:54`, `:429`；`worker/worker-file-tool.ts:88-125`, `:60` |
| read/ls/find/grep | `read_scope` 任一 entry 的等值/子树；`deny_globs` 先拦 | scope 外、超 fileCap/byteCap、deny glob | `read-scope.ts:167-214` |

对 merge 的直接含义：

- **读**兄弟 report 走 read 工具（受 `read_scope` 逐文件枚举）；
- **写**自己的汇总只能进自己的 taskDir（`worker_file` 面），**不可能**改写兄弟 report —— 这正是 AC-008「裁决搬运、不许重判」需要的物理隔离；
- merge 的 `review` 角色工具集 = `read/find/grep/ls` + `worker_file`（无 bash/write/edit）：`worker-mode.ts:118`, `:186-192`。

### 5. 可复用物与空白（要求 5）

| 项 | 结论 | 锚点 |
|---|---|---|
| claims 解析 | 可复用（TS+Python 双份，语义已锁） | `shared/dispatch-card.ts:724`；`dispatch.py:661` |
| claims 判据 | 可复用（TS）；**Python 空白** | `dispatch-card.ts:987`；`dispatch.py` 无对应函数 |
| caps 推导 | 可复用 | `dispatch-card.ts:1042`；`dispatch.py:718` |
| 卡片门 | 可复用（envelope+extras+seed+claims 一次判完） | `ui-bridge.ts:2864` |
| task.md 单写点 | 可复用（参数含 taskKey/readScope/caps/card/decision） | `ui-bridge.ts:2996` |
| claims 读面生成 | 单元子卡可复用；**merge 需新写（不能整 key 放行）** | `ui-bridge.ts:2359` |
| 项目配置 caps 读取 | 可复用（配置优先、claims 兜底） | `dispatch.py:813` |
| 扇出+汇合 | conductor 通道可复用（`deps:` → frontier → done） | `task_graph.py:317/489/595`；`conductor.py:1999/2010/2031/2036/2055` |
| 卡片溯源审计 | 可复用，但**子卡必须在 `<key>/tasks/` 下**（`list_cards` 只列 `tasks/*.md`，否则进 `missing_cards` 红） | `card_audit.py:102-110`, `:283`, `:315-333` |
| triage 分类器 | 可复用但**只有 type/risk 两问**，没有「是否拆分」问句；且 advisory 永不改派发 | `triage-client.ts:93-96`, `:863`；`ui-bridge.ts:593/1835` |
| 卡片 seed 注入（claims 块随 task.md 落地） | 可复用（子卡自带 claims 块会被原样注入 task.md） | `ui-bridge.ts:2597`, `:2624`；`extractClaimsBlockText` `:2431` |
| **拆卡函数**（母卡 → k+1 子卡） | **空白**（全仓无 fanout/split 实现；grep `fanout|fan-out|depends_on|wait_for` 无命中） | — |
| **merge 卡模板** | **空白** | — |
| **子卡 id 重映射** | **空白**，且与 `numeric_core` 冲突（见 §6.5） | `task_graph.py:340-353` |
| **`[SPLIT]` 机器行 / `split:*` / `merge:*` 判据** | **空白**（全仓无这些 token） | — |
| merge 裁决搬运判据（AC-008） | **空白**；最近的可复用件是逐 run 的 `claimCoverage`/`claimSettlementGaps`，没有跨 run 比对 | `worker/output-sections.ts:628`；`worker-mode.ts:1056` |
| 拆分决策点 | 只有 **checkpoint 的** `dp2-checkpoint-split`（含 `split` 选项），且执行器未接（`over-authority` 上抛人）；**没有派发期拆分 DP** | `packages/multi-workers/decision_points.py:576-593`, `:466-474` |

### 6. 风险点（要求 6）

#### 6.1 并行写同一 `_workers.parallel` 的锁

- 两边都用 `.mw/workers.lock`（`worker-store.ts:153`；`mw_common.py:2005`），语义 `O_CREAT|O_EXCL`（`shared/file-lock.ts:9-12`；`mw_common.py:2388-2394`）。
- **不能嵌套加锁**：持锁后再 `acquireLock` 会退避很久再抛（`worker-store.ts:169-175`；`dispatch.py:2170-2173`；`task-dispatcher.ts:303-310`）。所以 k+1 个子卡必须**串行派发**（每次 `dispatch_worker` 各自加锁/释放），不能在一个持锁区间里批量写。
- 次生风险：k+1 次派发 = k+1 个临界区；若 PM 并发调用（同一进程内 await 交错）也安全（锁是文件锁），但任何「批量写队列」的新实现都必须走 `upsertWithinLock`（`worker-store.ts:225`）或 `upsert_worker_row`（`mw_common.py:2451`），不得自己 `writeFileSync` 整文件。

#### 6.2 同 key 的 serial-only 守卫：**这是扇出最大的现实拦路虎**

- `dispatchTask` 在锁内跑 `writeFaceVerdict`（`task-dispatcher.ts:320`, `:395`）；卡片带 `card_path:`（所有卡片派发都带，`ui-bridge.ts:2746`）且任务未声明 `write_face:` → `kind === "undeclared"`（`shared/write-face.ts` 的 `parseWriteFace`，只认 `write_face:` 头）→ 只要同 owner key 有非终态行就**拒绝**（`task-dispatcher.ts:447-459`）。
- 实测断言已存在：第二个同 key 派发被拒，reason `write-face-undeclared: serial-only (1 same-owner worker(s) in flight)`（`test/suite/write-face-pm-gate.test.ts:422-435`）。
- conductor 侧同一判据（`dispatch.py:1797` 定义，`Undeclared` 串行分支 `:1855-1875`），且把这类拒绝归为「这一 tick 等，不是作者错误」（`conductor.py:1861`, `_WRITE_FACE_WAIT_REFUSALS`）。
- **对 AC-002 的含义**：5 个 review 子卡如果都不声明 `## 写入允许面`，第 2 个起会被挡到第 1 个终态为止 → 「并行」退化成串行，墙钟 = 求和。要真并行，每张子卡必须声明**互不重叠**的 `write_face`（例如各自的 `workers/<task>-u<k>` 目录）。
- **附带的诚实性缺口**：writeless 角色的运行时写面**不看 `write_face`**（`worker-mode.ts:3422` 只在 `roleClass === "writable"` 时解析），仍按 `write_scope:`/默认面（own taskDir + `<key>/evidence/**`）。所以「声明成每单元目录」时门禁判的是声明，运行时放的是 key evidence —— 声明必须与真实产出目录一致，否则门禁放行的并行在运行时仍可能撞同一批 evidence 文件。

#### 6.3 子卡与母卡的 `card_sha256` 关系：**没有链**

- task.md 只记自己的 `card_path` + `card_sha256`（`ui-bridge.ts:2746`；`dispatch.py:1537-1539`）。
- 审计按「每份 task.md 的 card 是否存在于 `tasks/` + sha 是否仍等值」判红（`card_audit.py:283-333`）。
- 因此：子卡只能证明「我是从这张子卡生成的」，**无法证明「子卡集合仍等于母卡」**；母卡被改（claims 增删）时，全部子卡 + 全部 sha 依然全绿。AC-004/005/007 的守恒判据必须另找锚点（例如把母卡 sha 写进子卡头，或把母卡 claim 集快照进 merge 卡），现有 header 里没有这个字段（`card_path/card_sha256/envelope_producer/write_face/read_scope/l2_*/decision`）。
- 另一条约束：子卡若不放 `<key>/tasks/`，`list_cards`（`card_audit.py:102-110`）不认 → `missing_cards` 恒红（`:315-318`）。子卡必须落 `tasks/`。

#### 6.4 看门狗在 5 个小单元上的叠加

- 每单元独立进程：墙钟默认 60m（`worker-mode.ts:396`，`resolveBudgetMs` `:409`，task.md `timeout:` 优先），活动看门狗 10m（`:402`, `:417`），checkpoint 锚点 30m 或预算一半（`:404`, `:448`）。
- 并行时墙钟 ≈ max(单单元) 而非 sum；但**固定开销 × k**：每单元一次 CLI 启动、一次 task.md 读、一次 goal/卡重建、一次 settle 写（`worker-mode.ts:3015`, `:3118`；`launcher.py:2185-2207`）。这正好是 spec §4 的「拆分成本倒挂」风险，需要 RQ-3 的度量来判。
- 串行兜底情形（§6.2 未声明 write_face）下墙钟 = Σ + k×固定开销；30m checkpoint 会对每个单元各触发一次，PM 侧会收到 k 倍 checkpoint/steer 噪声（`worker-mode.ts:3843-3865`）。

#### 6.5 另外三个必须写进设计的风险

1. **子卡 id 撞数字核心 → 整 key 退化串行**：`numeric_core` 只取前 1-3 位数字（`task_graph.py:340-353`，正则 `:129-131`），`T-02-u1` 与 `T-02-u2` 都是 core `02`。如果 `deps:` 写成 `T-02`（非精确 stem），`join_deps` 得到 ≥2 候选 → `deps-ambiguous`（`:547-556`）→ `plan_is_serializable=False` → `conductor.py:2010-2012` **整 key 按 plan 顺序串行**。所以子卡必须重映射到互不冲突的数字核心（并在 merge 卡里用**精确 stem** 写 `deps:`，因为精确命中优先于核心 join，`:406-410`）。
2. **母卡留在 `tasks/` 会被当成一个独立单元派发**：execute_loop 的 `stems` = `tasks/*.md` 全量（`conductor.py:1986`），frontier 只剔除 `done`/in-flight（`:2031-2040`）。母卡（20 条）与它的 5 个子卡会同时进 frontier。要么母卡先被标记 done/移出 `tasks/`，要么给母卡一个「容器不可派发」的判定——今天没有这种标记（空白）。
3. **merge 单元的就绪依赖「done」而非「report.md 存在」**：`done_stems` 取队列行 `done`（`conductor.py:2010-2016`）。worker 可以在 `failed` 之前写出部分 report（`worker/output-writer.ts:186` 落 `report.md`），此时 merge 不会被放行；反过来若某单元 exit=0 但 report 缺失，merge 会拿到空输入。merge 卡需要自己的前置校验（AC-008 的输入校验），今天空白。

## 残留与未验证

1. **没有跑任何派发/并发实跑**：本 RQ 是只读勘察，§6.2 的「serial-only 会 hold」用的是既有测试断言（`write-face-pm-gate.test.ts:422-435`）+ 代码路径，不是本轮新实测。
2. **`Σ预算`/`fileCap` 的 20 条推算是静态算术**：`unverified: budget` 的「大面积」是按 30/20=1.5 次/claim 推导的必然结论，未跑一张真 20 条卡验证收尾 gap 的具体分布。上游 `claim-driven-review` 的 T-07 只跑过 5 条。
3. **launcher 的 `max_workers_per_key` / `launcher_max_workers` 实际取值未读**（只看了解析函数 `mw_common.py:2233` 与 config 默认 4 的注释 `conductor.py:1993`），所以 k=5 是否会被并发上限截断取决于项目配置；仅确认「上限是硬上限，`None` 不表示无限」（`launcher.py:2559`）。
4. **`/worker` 命令的 `manual-<timestamp>` task_key 与 fanout 的命名关系未展开**：`ui-bridge.ts:3750` 固定 `manual-${Date.now()}`，子卡若走命令通道无法得到 `<task>-u<k>` 名字。
5. **claim 读面的字节预算**：`byteCap` 在 n≥6 就饱和到 393216，k 个 report 的体积累加是否够用未测（report 大小取决于 RQ-3 语料）。

## 上下文来源

- `.agenticdoc/goal.md`（项目目标锚点，GC-5 不引入中心化调度器）
- `.agenticdoc/claim-driven-review-orchestration/spec.md`（§1 现状、§3 AC-001..012）
- `.agenticdoc/claim-driven-review-orchestration/tasks/RQ-1-orchestration-seams.md`（本 RQ 卡片）
- 上游交付：`.agenticdoc/claim-driven-review/evidence/t07-e2e-results-20261022.md`（5 claims / 13 次放行取数，经 spec 转述）
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/{shared/dispatch-card.ts, shared/worker-store.ts, shared/write-face.ts, shared/write-surface.ts, shared/file-lock.ts, shared/run-store.ts, pm/ui-bridge.ts, pm/task-dispatcher.ts, pm/triage-client.ts, worker/read-scope.ts, worker/worker-mode.ts, worker/worker-file-tool.ts, worker/output-sections.ts, worker/output-writer.ts}`
- 源码：`packages/multi-workers/{mw_common.py, launcher.py, autopilot/dispatch.py, autopilot/conductor.py, autopilot/task_graph.py, autopilot/card_audit.py, decision_points.py}`
- 测试：`packages/coding-agent/test/suite/write-face-pm-gate.test.ts`
- 派发卡契约：本任务 `task.md` 的 `<!-- mw-dispatch-card: v1 -->` 段

## 未覆盖面

- **未读**：`packages/multi-workers/autopilot/gates.py`、`state.py`、`closure.py`、`evidence.py`、`roadmap.py`（与扇出/汇合的关系只在 execute_loop，未逐行走读）；`pm/pm-orchestrator.ts` 全量（只读了 `supersedes` rollback 与 settle 相关片段）；`autopilot/monitor.ts`、`autopilot/status-model.ts`（PM 面板如何渲染多行/多单元未核对）；`worker/output-writer.ts` 全文（只读了 report/output 落盘位置）。
- **未读**：`decision_points.py` 的完整 dp 注册表（只核了 dp1/dp2 与 `_unwired_executor`）；`decision.py` / `decide_*` 系列（拆分授权路径未勘察）。
- **未验证**：任何真实项目的 `.mw/dispatch.yml` / `_autopilot/config.json` 里 `max_workers_per_key`、`launcher_max_workers`、`l2_read_*` 的现值（只用代码默认与注释）。
- **未覆盖的运行面**：`mw serve` / `mw.py run-detached` 实际并发行为；Windows 路径大小写/`\\?\` 前缀对 `read_scope` 文件级条目的实测；`_workers.parallel` 在多 launcher 进程下的竞争者行为（只读了锁实现）。
- **未覆盖的判据面**（明确属于 RQ-2/RQ-3，不在本 RQ 结论内）：`split:*` / `merge:*` token 的具体判据、阈值、负例；`tokens_per_closed_claim` 的分母口径。
