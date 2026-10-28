# T-C1 证据：conductor 派发链与 per-key 串行点（RQ-C1）

- 卡：`.agenticdoc/mw-dynamic-concurrency/tasks/T-C1-dispatch-chain.md`（key `mw-dynamic-concurrency`；角色 research，只读）
- 唯一写面：本文件
- 行号快照：工作树 git `55be3d960`（工作树含其它 key 的并发改动）。字节数：conductor.py 356681 / launcher.py 99184 / mw_common.py 222593 / autopilot/dispatch.py 55879 / autopilot/config.py 11863 / shared/worker-store.ts 8779 / pm/pm-orchestrator.ts 85888 / pm/ui-bridge.ts 150517 / autopilot/monitor.ts 65630
- 时间：2026-10-14（本地 UTC+8）；下称 `conductor.py` = `packages/multi-workers/autopilot/conductor.py`，`launcher.py` = `packages/multi-workers/launcher.py`，`mw_common.py` = `packages/multi-workers/mw_common.py`，TS 路径以 `agent-team-loop/` 为根
- 方法：只读（read/grep/ls + `python -B` 只读复算，不写仓库、不跑测试、不 install）。所有判定均为工作树静态判定复看；未找到的写"未找到（命令 + 输出）"，不做推测补齐。

## 结论先行（TL;DR）

1. **每 tick 派发链是单进程、单线程、串行的**：`mw serve` 拉起的 conductor 进程 `while not stop.is_set(): tick(...)`（conductor.py:8370-8371），每 tick 调一次 `orchestrate`（conductor.py:3516）。派发决策只用 tick 开始时的 `_workers.parallel` 快照（conductor.py:620），tick 内不再刷新。
2. **"本轮最多派 N 个"只有 4 处**：roadmap-writer ≤1（:630 / 经 :644 的 activation 路径）、xkey 提案 `≤approved ticket 数`（:695，**不受 key cap 约束且发生在 in_flight_keys 计算之前**）、key 层 cap（:744）、以及每个 key 每次 `_advance_key` 调用 ≤1 次 `dispatch.dispatch`（:746→:1605/:1643/:1679/:1788/:2369/:2419/:2454/:2486/:2526/:2571/:2579）。
3. **per-key 串行 = 硬顺序（结构性），不是策略保守**：核心是 `if key in in_flight_keys: continue`（:742）与 `in_flight_keys` 的布尔定义（:698-704）——该 key 只要有 **1** 个非终态 conductor 行，本轮 `_advance_key` 不会被调用；`execute_loop` / `_verify_loop` 再各自加了一次 family 级 in-flight 判定（:1770、:2365、:2556）。共列 **17 个判定点**（见 §B），其中 11 个是硬 gate、3 个是"每次调用至多 1 派"的结构点、3 个是策略/延迟类。
4. **派发卡里"PM 手工派发行被 conductor 计入 key 在飞"这条已不成立**（本轮必须纠正的种子）：`_row_belongs_to` 现在委托 `mw_common.row_belongs_to`（:3543-3546），后者 **origin 先决**：`if not worker_is_conductor(row): return False`（mw_common.py:2034-2035）。实测本仓队列 419 行、`origin=conductor` **0 行** → 手工行在飞的 key 数 = **0**（若按 task_path 判则是 3 个 key）。这条结论在上个 key 的研究文档里是反的（`spec-worker-serialization-20260926.md` F2-E2/F3："PM 手工派发占用 conductor 槽位"），那是 D-019/T-12 之前的旧判定，已被取代。
5. **两条通道真正共享的是"同一队列文件 + 同一把锁 + 同一个 spawn 消费者（launcher）"**，而不是"同一套在飞计数"。因此当前的实际并发 = launcher 层（默认 `launcher_max_workers=8`）对"conductor 行 + 手工行"一起放行，而 conductor 只按自己的行数算 cap（默认 2）。放开 per-key/key 层必须同时决定"哪一层的计数是权威"。
6. **放开点共 11 项**（§D），其中 3 项是前置阻塞：任务级依赖载体不存在（只有 plan 出现顺序）、同 key 写面集合不存在机器可读载体、以及 in-flight 判定位于 `.mw/workers.lock` 之外（check-then-act 窗口）。

---

## §A `orchestrate` 每 tick 的派发链（逐段 file:line + 判定原文）

入口链：`tick()` → enabled 门 → `orchestrate()` → stage 门 → key 循环 → `_advance_key()`。

| # | 段 | file:line | 判定原文（逐字） | 本轮最多派 N |
|---|----|-----------|------------------|--------------|
| A0 | 主循环 | conductor.py:8370-8371 | `while not stop.is_set():` / `tick(project_root, st)  # act-then-sleep: first tick before any wait` | 每 poll 1 tick |
| A1 | tick 入口 | conductor.py:3432-3447 | `cfg = _load_effective_config(project_root)` / `if not cfg["enabled"] or cfg["paused"]:` / `return "idle"` | 0（未启用/暂停即 0） |
| A2 | 调 orchestrate | conductor.py:3516 | `orchestrate(project_root, st)` | — |
| A3 | 配置 | conductor.py:604 | `cfg = _load_effective_config(project_root)` | — |
| A4 | 自动决策 | conductor.py:609 | `auto_decide_gates(project_root, st, cfg)` | 0（只回答 gate） |
| A5 | 消费已答 gate | conductor.py:613-614 | `if not _consume_answered_gates(project_root, st, cfg):` / `return` | 0（整 tick 提前返回） |
| A6 | 孤儿回插 | conductor.py:617 | `reconcile_orphans(project_root, st)` | 0（不派 worker，但会回插 pending 行 → 交给 launcher spawn） |
| A7 | 队列快照 | conductor.py:620 | `rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))` | —（tick 内唯一的 in-flight 事实源，**不刷新**） |
| A8 | 合成 claim | conductor.py:626 | `synthetic_claim_self_id = maintain_synthetic_claims(project_root, st, rows)` | 0 |
| A9 | 无 roadmap | conductor.py:628-631 | `if not rm_path.is_file():` / `_dispatch_roadmap_writer(project_root, st, rows, stage_number=1)` / `return` | **≤1** |
| A10 | roadmap 不可读 | conductor.py:632-639 | `except roadmap.RoadmapError as exc:` … `return` | 0 |
| A11 | stage 门 | conductor.py:644-645 | `if not _stage_activation(project_root, st, rm, rows):` / `return` | running stage → 继续；无 running stage → `_activate_pending_stage`（:1102）里的 roadmap-writer **≤1** |
| A12 | key 状态/轮次 | conductor.py:647-648 | `key_states = state.read_key_states(project_root, self_id=synthetic_claim_self_id)` / `rounds = state.used_rounds(_all_workers_dirs(project_root))` | — |
| A13 | 跨 key 视图 | conductor.py:650-659 | `deps_of[entry.key] = entry.depends_on` / `status_of[k] = s` | — |
| A14 | gate 消费者 | conductor.py:662-678 | `_apply_stalled_approvals(...)` / `_apply_stalled_rejections(...)` / `_apply_review_decisions(...)` / `_apply_reattests(...)` | 0 |
| A15 | xkey 通道（`xkey_repair` 默认 false） | conductor.py:687-696 | `if cfg.get("xkey_repair", False):` / `_xkey_aggregate(...)` / `_xkey_proposal_stage(project_root, st, rows, cfg)` / `_xkey_apply_stage(...)` | **≤ approved 且无 proposal.md 的 ticket 数**（每 ticket ≤1，见 :5053-5118；**无 key cap**） |
| A16 | in-flight 集合 | conductor.py:698-704 | `in_flight_keys = {` / `key` / `for key in deps_of` / `if any(` / `_is_in_flight(row) and _row_belongs_to(row, key) for row in rows` / `)` / `}` | —（只数 `origin=conductor` 的行） |
| A17 | stage 循环 | conductor.py:706-708 | `for stage in rm.stages:` / `if stage.status != "running":` / `continue` | — |
| A18 | 延迟评审 | conductor.py:715 | `_process_deferred_reviews(project_root, st, stage, status_of, rows)` | 0（升 gate，不派 worker） |
| A19 | stage 关闭 | conductor.py:718 | `_stage_closure(project_root, st, stage, rm_path, status_of, rows)` | 0 |
| A20 | key 循环 + 状态跳过 | conductor.py:719-722 | `for entry in stage.keys:` / `if status_of.get(key) in _DISPATCH_SKIP_STATUSES:` / `continue` | — |
| A21 | 人类 claim 门 | conductor.py:726-732 | `if claim == state.CLAIM_LIVE:` … `continue` | 0（该 key 交给窗口） |
| A22 | 外机合成 claim 门 | conductor.py:733-739 | `if _foreign_synthetic_claim(claim_id):` … `continue` | 0 |
| A23 | 依赖门 | conductor.py:740-741 | `if not _deps_satisfied(entry.depends_on, status_of):` / `continue` | — |
| A24 | **per-key 在飞门** | conductor.py:742-743 | `if key in in_flight_keys:` / `continue  # wait for the in-flight worker` | **0**（该 key 本轮不再派） |
| A25 | **key 层 cap** | conductor.py:744-745 | `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` / `continue  # parallel cap — key starts on a later tick` | 新派 key ≤ `cap − len(in_flight_keys)`（default cap=2） |
| A26 | 派发 | conductor.py:746-747 | `if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):` / `in_flight_keys.add(key)` | **每 key 每次调用 ≤1**（见 §B B5） |

### A 的小结

- **本轮最多派 N 的 4 个点**：A9/A11（roadmap-writer，≤1）、A15（xkey 提案，无 cap）、A25（key 层 cap）、A26（每 key ≤1）。
- A25 是**唯一**用配置值截断"新派 key 数"的地方；它同时把**已在飞的 key**（A16）计入 `len(in_flight_keys)`，所以 cap 是"key 层总在飞上限"。
- A16 的 `rows` 是 A7 的快照：tick 内新派出的行不在 `rows` 里，只在 `in_flight_keys` 里（A26）。这一点在放开 per-key 并发时是第一个会出错的地方（见 §D D1/D3）。
- 未找到任何其它"派 worker"的入口：`dispatch.dispatch(` 在 conductor.py 共 13 个调用点：1196（roadmap-writer）、1605/1643/1679（`_advance_key`）、1788（`execute_loop`）、2369/2419/2454/2486/2526/2571/2579（`_verify_loop`）、5098（`_xkey_proposal_one`），全部落在 A 表的这些段内（无其它派 worker 入口；worker 进程只由 launcher spawn）。

---

## §B per-key 串行点穷举（同一 key 同一时刻只有一个在飞 worker）

判定原文逐字引用；"硬顺序"= 结构性互斥，"结构"= 每次调用至多 1 派的形状，"策略"= 延迟/预算类，不构成并发互斥。

| # | 点 | file:line | 判定原文 | 触发条件 | 性质 |
|---|----|-----------|----------|----------|------|
| B1 | `in_flight_keys` 布尔定义 | conductor.py:698-704 | `in_flight_keys = {` / `key` / `for key in deps_of` / `if any(` / `_is_in_flight(row) and _row_belongs_to(row, key) for row in rows` / `)` / `}` | deps_of 中的 key 名下存在任一非终态 conductor 行 | **硬顺序** |
| B2 | key 级在飞门 | conductor.py:742-743 | `if key in in_flight_keys:` / `continue  # wait for the in-flight worker` | B1 命中 | **硬顺序**（第一重保证） |
| B3 | key 层 cap | conductor.py:744-745 | `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` / `continue  # parallel cap — key starts on a later tick` | 在飞 key 数 ≥ cap（default 2） | 硬（值可配；floor=2，见 D2） |
| B4 | `_is_in_flight`：pending 也算在飞 | conductor.py:3539-3540 | `def _is_in_flight(row: dict) -> bool:` / `return row.get("status", "") not in mw_common._TERMINAL_STATUSES` | status ∉ {done, failed, needs-clarification, lost}（mw_common.py:168） | **硬顺序**（判据是行状态，不是进程存活） |
| B5 | `_row_belongs_to` → origin 先决 | conductor.py:3543-3546 / mw_common.py:2026-2036 | `return mw_common.row_belongs_to(row, key)` / `if not worker_is_conductor(row):` / `return False` / `return worker_owner_key(row) == key` | 行 `origin != conductor`（含 legacy 无列）→ 不占槽 | 硬（**仅约束 conductor 通道**） |
| B6 | `_advance_key` 每调用 ≤1 派 | conductor.py:1577,1602-1610,1639-1648,1678-1693 | `"""Run one key one step of the phase machine. Returns True when a worker was dispatched"""`；每分支 `result = dispatch.dispatch(...)` 后 `return result.ok` | 每次调用 | **结构**（每 tick 每 key 1 张卡） |
| B7 | `execute_loop` per-key serial | conductor.py:1770-1771 | `if any(_is_in_flight(r) for r in fam):` / `return False  # per-key serial: wait for the in-flight task` | 同 stem family（`ap-{key}-{stem}` 及其 `-aN`）有非终态行 | **硬顺序**（第二重保证；docstring :1750 `per-key serial (one in-flight exec task)`） |
| B8 | `execute_loop` 任务串行循环 | conductor.py:1765-1800 | `for stem in _plan_task_order([f.stem for f in files], plan):` … `return result.ok` | 首个未 done 的 stem 派 1 个后立即返回 | **硬顺序**（key 内任务**全串行**，与依赖无关） |
| B9 | `_verify_loop` L3/repair 前缀在飞 | conductor.py:2365-2367 | `for prefix in (f"ap-{key}-l3-", f"ap-{key}-repair-"):` / `if any(_is_in_flight(r) for r in rows if r["task_key"].startswith(prefix)):` / `return False  # wait for the in-flight review/repair` | 前缀命中且任一非终态 | **硬顺序**（第三重保证） |
| B10 | `_verify_loop` repair family | conductor.py:2554-2557 | `if not any(r["status"] == "done" for r in fam):` / `if any(_is_in_flight(r) for r in fam):` / `return False` | repair family 在飞 | **硬顺序** |
| B11 | `_verify_loop` 首轮单派 | conductor.py:2368-2376 | `if round_no == 0:` / `result = dispatch.dispatch(project_root, key, "l3-a1", "reviewer", ...)` / `return result.ok` | round_no==0 | **结构**（一轮一 reviewer） |
| B12 | `_phase_artifact_present` 分支 | conductor.py:2822-2829 + 1602-1610 | `if phase in ("spec","design","plan"): return (key_dir / f"{phase}.md").is_file()` / `if phase == "tasks": return any((key_dir / "tasks").glob("*.md"))` / `if phase == "verify": return (key_dir / "achieved.md").is_file()` / `return True  # execute (T-12 loop) / done (terminal)`；调用点 `if not _phase_artifact_present(key_dir, phase):` → phase-writer（≤1），否则 L1 审计 → `if not blocking:` 推进（0）或 L2（≤1，:1679） | phase ∈ {spec,design,plan,tasks,verify}；execute/done 恒 True | **结构**（决定这一 tick 派哪一类卡，不决定并发；是"每 key 每 tick 1 张卡"的来源之一） |
| B13 | `_stage_closure` 阶段级在飞屏障 | conductor.py:1288-1292 | `if rows is not None and any(` / `_is_in_flight(row) and _row_belongs_to(row, e.key)` / `for row in rows` / `for e in stage.keys` / `):` | stage 的任一 key 有非终态 conductor 行 | **硬顺序**（阻止 stage 关闭；不阻止派发） |
| B14 | `review_batch` 资格 | conductor.py:4106-4110 | `eligible = [` / `key` / `for key in pending` / `if not any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows)` / `]` | pending-review key 且有在飞行 → 不eligible | **策略**（延迟评审推送，不构成派发互斥） |
| B15 | `pending_gate_reminders` 抑制 | conductor.py:3001-3004 | `if key and any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):` / `silenced.append((gate, n, _SUPPRESS_KEY_IN_FLIGHT))` / `continue` | gate 的 key 有在飞 conductor 行 | **策略**（抑制提醒） |
| B16 | `_defer_declined_gate` case 3 | conductor.py:7986-7990 | `if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):` / `return None  # a live worker still owns the key: case 3 this tick` | 同上 | **策略**（本 tick 不转 pending-review） |
| B17 | `_xkey_proposal_in_flight` | conductor.py:4990-4996 / 5082-5084 | `return any(pat.match(str(row.get("task_key", ""))) and _is_in_flight(row) for row in rows)`；调用点 `if _xkey_proposal_in_flight(rows, source_key, base_stem):` / `return  # a live dispatch in this stem family is never duplicated` | xkey 通道，同 stem family 在飞 | **硬**（仅 xkey 通道；不判 origin） |

### B 的小结

- **硬顺序 gate（11）**：B1、B2、B3、B4、B5、B7、B8、B9、B10、B13、B17。
- **结构点（3）**：B6、B11、B12。
- **策略/延迟（3）**：B14、B15、B16。
- 结论：把 `max_parallel_keys` 调到 100、deps/相位/budget 全放开，只要该 key 有 1 个非终态 **conductor** 行，B2 就拦住 `_advance_key`；即便绕过 B2，B7/B9/B10 还会各自拦住同 family 的第二个 worker。**"per-key 1" 是四重结构性判定，不是策略保守。**
- 反向：**PM 手工行不受 B1-B10 任何一条约束**（B5 origin 先决）；PM 通道的并发门禁只有 `dispatch_max_per_scan`（TS 侧，见 §C）与 launcher 的全局 cap。

---

## §C 两条通道共享的证据（队列 / 消费者 / 在飞归属）

"两条通道" = conductor 通道（`dispatch.dispatch` → Python 写行）与 PM 手工通道（`dispatch_worker` / `/worker` / 后台扫描 → `WorkerStore.upsert` 写行）。

### C1 同一文件、同一把锁（逐行）

| 事实 | 证据 |
|------|------|
| Python 写的路径 | mw_common.py:1716-1717 `def workers_path(project_dir: pathlib.Path) -> pathlib.Path:` / `return pathlib.Path(project_dir) / ".agenticdoc" / "_workers.parallel"` |
| TS 写的路径 | `agent-team-loop/shared/worker-store.ts:151-153` `this.filePath = path.join(agenticdocRoot, "_workers.parallel");` / `this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");` |
| Python 锁路径 | mw_common.py:1731-1732 `return pathlib.Path(project_dir) / ".mw" / "workers.lock"` |
| conductor 写行（origin=conductor） | autopilot/dispatch.py:1140-1154 `row = {` … `"status": "pending",` … `"origin": mw_common.WORKER_ORIGIN_CONDUCTOR,` |
| conductor 取锁 + 写 | autopilot/dispatch.py:1155-1156 `mw_common.acquire_lock(lock)`；写经 `mw_common.upsert_worker_row`（mw_common.py:2152，调用点 dispatch.py:1172） |
| TS 写行（origin 恒 manual） | worker-store.ts:130-144 `serializeWorkerLine` 末列 `workerOrigin(entry)`；`workerOrigin` 默认 `manual`（:42-43 `=== "conductor" ? "conductor" : "manual"`） |
| TS 取锁 + 原子写 | worker-store.ts:190-214 `async upsert(entry: WorkerEntry): Promise<void> { const release = await acquireLock(this.lockPath);` … `fs.writeFileSync(tmpPath, ...)` / `fs.renameSync(tmpPath, this.filePath)` |
| 列宽镜像 | mw_common.py:1738-1739 `WORKER_COLS_MIN = 7` / `WORKER_COLS_MAX = 9` vs worker-store.ts:31-32（`WORKER_COLS_MIN`/`WORKER_COLS_MAX`） |

### C2 唯一 spawn 消费者 = launcher（逐行）

| 段 | file:line | 判定原文 |
|----|-----------|----------|
| 主循环 | launcher.py:1901-1908 | `while True:` / `_poll_once(project_dir, config, running_procs, log_handles, pending_queue,` / `max_workers, tree_watcher,)` |
| 队列上限 | launcher.py:1735 | `limit = max_workers if max_workers is not None else mw_common.launcher_max_workers(project_dir)` |
| 读队列 | launcher.py:1776 | `entries = _parse_workers_file(_workers_path(project_dir))` |
| discover 循环（不按 key 分组、不分批） | launcher.py:1805-1813 | `for entry in entries:` / `if entry["status"] != "pending":` / `continue` / `if key in running_procs:` / `continue  # AC-008: no duplicate spawn` / `if key in acked:` / `continue  # AC-023: acked tasks are never re-spawned` |
| 全局 cap → 内存排队 | launcher.py:1854-1857 | `if len(running_procs) >= limit:` / `if not any(q["task_key"] == key for q in pending_queue):` / `pending_queue.append(entry)  # AC-007` / `continue` |
| spawn（非阻塞） | launcher.py:1858 → :2008 | `_spawn(entry, project_dir, config, running_procs, log_handles)` → `proc = subprocess.Popen(cmd, **spawn_kwargs)` |
| 空闲名额只在 reap 时释放 | launcher.py:1750-1764 | `# Reap finished processes` / `finished = [k for k, p in running_procs.items() if p.poll() is not None]` |

全仓 `subprocess.Popen` 的 worker 派发点只有 launcher.py:2008（`mw.py:376/393` 拉起的是 proxy/launcher/conductor 进程，不是 worker）。因此：**两张通道写同一队列，唯一的 spawn 消费者是 launcher，`launcher_max_workers`（default 8，config.py:98）是全局真实并发上限。**

### C3 关键纠正：PM 手工行**不被** conductor 计入 key 在飞（逐行）

| 层 | file:line | 逐行内容 |
|----|-----------|----------|
| 调用 | conductor.py:698-704 | `if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows)` |
| `_is_in_flight` | conductor.py:3539-3540 | `return row.get("status", "") not in mw_common._TERMINAL_STATUSES` |
| `_row_belongs_to` | conductor.py:3543-3546 | `return mw_common.row_belongs_to(row, key)`（docstring：`Single canonical owner predicate (T-12/AC-021): delegate to mw_common.row_belongs_to; no local prefix/path rule may exist here.`） |
| 归属判定 | mw_common.py:2026-2036 | `if not worker_is_conductor(row):` / `return False` / `return worker_owner_key(row) == key` |
| `worker_is_conductor` | mw_common.py:2022-2024 | `return worker_origin(row) == WORKER_ORIGIN_CONDUCTOR` |
| `worker_origin` 归一 | mw_common.py:1989-1997 | `raw = str(row.get("origin", "") or "").strip().lower()` / `return WORKER_ORIGIN_CONDUCTOR if raw == WORKER_ORIGIN_CONDUCTOR else WORKER_ORIGIN_MANUAL` |
| 常量 | mw_common.py:1980-1982 | `WORKER_ORIGIN_CONDUCTOR = "conductor"` / `WORKER_ORIGIN_MANUAL = "manual"` |

**实测（本仓 `.agenticdoc/_workers.parallel`，2026-10-14）**：

```
parsed_rows = 419          nonterminal_rows = 7
origins = {manual: 419}   distinct_owner_keys(task_path) = 35
keys_with_conductor_inflight = 0        keys_with_PATH_inflight(忽略 origin) = 3
index_keys(_index.parallel) = 57        claim verdicts = {dead:41, free:9, live:4, stale:3}
```

合成行对拍（`python -B`，同一谓词）：

```
manual_row_belongs_to_k  = False
legacy_row_belongs_to_k  = False
conductor_row_belongs_to = True
```

⇒ **"PM 手工派发行被 conductor 计入 key 在飞"为假**。旁证（仓库内既有测试断言）：`packages/multi-workers/test_autopilot_attribution.py::test_six_prefix_rows_are_manual_and_consume_no_slot`（:195-223，注释："PM-hand-started `ap-`-prefixed rows with no `origin: conductor` (E2 project) … no key is owned"），以及 docstring :7-23。

### C4 反向：PM 扫描不接管 conductor 行

| 判定 | file:line | 原文 |
|------|-----------|------|
| 后台扫描跳过 conductor 任务 | pm/pm-orchestrator.ts:433-438 | `function isConductorTask(taskMdPath: string): boolean {` / `return readTaskOrigin(fs.readFileSync(taskMdPath, "utf8")) === "conductor";` |
| 调用点 | pm/pm-orchestrator.ts:1116-1120 区域（`if (isConductorTask(taskMdPath)) continue;`，注释 `D-104: conductor-owned tasks ... never enter the TS dispatch path`） | 见 :1113-1120 |
| PM 侧归属谓词（与 Python 镜像） | shared/worker-store.ts:65-67 | `return workerOrigin(entry) === "conductor" && workerOwnerKey(entry) === key;` |

### C5 PM 手工通道的门禁（与 conductor 完全不同）

| 门禁 | file:line | 原文 | 语义 |
|------|-----------|------|------|
| 工具入口 | pm/ui-bridge.ts:2202-2203 | `pi.registerTool({` / `name: "dispatch_worker",` | 单卡派发 |
| 命令入口 | pm/ui-bridge.ts:2764 | `pi.registerCommand("worker", {` | 单卡派发 |
| 入队 | pm/ui-bridge.ts:2440 / :2935 | `await dispatchTask(` / `await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);` | 直接 upsert，**无任何"该 key 已有几个在飞"判定** |
| 入队实现 | pm/task-dispatcher.ts:288-299 | `export async function dispatchTask(` … `await store.upsert(full);` | — |
| 后台扫描配额（唯一的数量上界） | pm/pm-orchestrator.ts:1230-1238 | `for (const { taskKey, taskMdPath } of undispatched) {` / `// AC-021: one scan may queue at most maxPerScan rows.` / `if (queued >= maxPerScan) {` … `return;` | 每次扫描 ≤ `dispatch_max_per_scan`（default 3，config.py:99）**新增行**，不是并发上限 |
| 配额读取 | pm/pm-orchestrator.ts:631-638 | `export function readDispatchMaxPerScan(agenticdocRoot: string): number {` … `return DEFAULT_DISPATCH_MAX_PER_SCAN;`（:621 `DEFAULT_DISPATCH_MAX_PER_SCAN = 3`） | 与 Python 镜像 |

### C6 计数口径分叉（放开并发前必须先定权威）

| 口径 | 位置 | 计数集合 | 与 conductor 一致？ |
|------|------|----------|---------------------|
| conductor 派发容量 | conductor.py:698-704 + :3539 | 非终态 **且 origin=conductor** 的行，**pending 也算** | 基准 |
| monitor `slotsUsed` | monitor.ts:917-932（`for (const w of workers) { ... if (owner !== "" && allKeys.includes(owner) && workerBelongsToKey(w, owner)) busyKeys.add(owner); }`；`workers` 仅含 `status === "running"`，见 :499-505） | 只数 **running** 的 conductor 行 | **否**（pending 不计 → 面板低估） |
| monitor `nonTerminalByKey` | monitor.ts:492-501（`const owner = workerOwnerKey(entry);`，origin 无关） | 非终态行按 path 归 key，**含 manual** | **否**（手工行计入 → gate 提醒轴口径不同） |
| TS `blockedOnHuman` | status-model.ts:1563-1590 | 用 `nonTerminalByKey`（path 口径） | 否（设计如此，D-008/F6） |
| gate facts / proposition | conductor.py:6986-6992（`facts["in_flight_keys"] = [...]`）→ :6403-6407（`if facts.get("in_flight_keys"):` / `return _prop_fail("stage-close-in-flight", ...)`） | 与 conductor 同口径 | 是 |

---

## §D 放开点清单（要改的确切函数）

每项：当前判定原文 / 改后需要的输入 / 并发安全性（是否需持锁）/ 首个失败模式。

| # | 目标 | 要改的确切函数 | 当前判定原文 | 改后需要的输入（前沿 / 写面） | 并发安全性 | 首个失败模式 |
|---|------|----------------|--------------|-------------------------------|------------|--------------|
| D1 | key 层：固定 cap → 依赖前沿 | `conductor.orchestrate` conductor.py:698-747（`in_flight_keys` 定义 + key 循环 `for entry in stage.keys:`） | `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` / `continue  # parallel cap — key starts on a later tick` | key 前沿 = `{k : _deps_satisfied(deps_of[k], status_of)}`（已存在，:740）+ 非终态 + claim free；`in_flight_keys` 从"布尔集合"改为"每 key 在飞计数" | **需要**：`in_flight_keys` 现在是 tick 内本地变量（:698），单 conductor 进程内无竞争；但 `dispatch.dispatch` 的队列 RMW 在 `.mw/workers.lock` 内（dispatch.py:1155-1156），而**判定在锁外**（`rows` 快照 :620）→ 想真正安全必须在锁内复查（见 D8） | 同一 tick 内两个 key 各自 `_advance_key` 派出的行都不在 `rows` 里；若把判定改成基于 `rows` 的计数（而非本地 `in_flight_keys`），会出现"同 tick 重复派同一 key" |
| D2 | 配置语义：cap 作为上界 + 允许 1（kill switch） | `autopilot/config.py:122`（`"max_parallel_keys": (2, None),`）+ TS 镜像 `autopilot/status-model.ts:196`（`max_parallel_keys: [2, null],`） | Python：`_INT_RANGES["max_parallel_keys"] = (2, None)` → 值 1 被拒（`must be >= 2`）；运行期 `max(1, int(cfg["max_parallel_keys"]))`（conductor.py:744） | 允许 `(1, None)`（AC-006 回退到串行）；两侧同波改，parity 语料重冻 | 不需要锁（纯校验） | AC-006（配置改 1 即全串行）当前**无法通过配置达成**：`config.json` 写 1 会被 `validate_config` 拒绝并 fail-closed 抛 `ConfigError` |
| D3 | per-key：布尔在飞 → 计数/卡身份 | `conductor.orchestrate` :742-743 + `conductor._row_belongs_to` :3543-3546（或 `mw_common.row_belongs_to`） | `if key in in_flight_keys:` / `continue  # wait for the in-flight worker` | 每 key 在飞 worker 数 + **卡身份**（`dispatch.task_key_for(key, stem)`，dispatch.py:952）；per-key 上界配置键（不存在，需新增） | 需要（同 D1/D8） | 一旦改成计数，`_is_in_flight` / `_row_belongs_to` 这对谓词被 11 处调用点共享（`_is_in_flight(` 调用点：conductor.py:702/1189/1289/1770/2366/2556/3001/4109/4995/6990/7988；其中 `_row_belongs_to` 只有 5 个：702/1289/4109/6990/7988）→ 只改 `orchestrate` 会让"在飞"在派发链与 gate/closure/提醒之间语义漂移（reminder 抑制、stage 关闭被绕过） |
| D4 | 每 key 每 tick 多派 | `conductor._advance_key` conductor.py:1577-1693 | `"""Run one key one step of the phase machine. Returns True when a worker was dispatched (the key is now in flight)."""`；每分支 `return result.ok`（1610/1648/1693） | 该 key 的任务前沿（见 D6）+ 每卡写面（见 D7）；返回从 `bool` 改为派发集合 | 需要（同 D1/D8） | 同一 tick 第二次派发仍用 A7 的 `rows` 快照 → `_row_exists`（:1640）与 `_missing_plan_tasks`（:1618）看到的是旧世界，会重复派同一 `task_key`；`upsert_worker_row` 按 task_key 覆盖（mw_common.py:2161-2171）→ 第一条行被重置为 `pending`，而它的进程已 spawn（launcher 记在 `running_procs`，:2010），第二个进程被 spawn → 同 key 同卡双写 |
| D5 | key 内任务并行 | `conductor.execute_loop` conductor.py:1765-1800 | `for stem in _plan_task_order([f.stem for f in files], plan):` / `if any(_is_in_flight(r) for r in fam):` / `return False  # per-key serial: wait for the in-flight task` / `return result.ok` | 任务级依赖（D6）+ 任务级写面（D7）+ 在飞并发数 | 需要（同 D1/D8） | `_plan_task_order` 只有 plan 出现顺序（:1717-1727，`mentioned = [(plan.find(s), s) for s in stems if s in plan]`）；无依赖数据时并行化=盲派，两个 worker 写同一文件（spec §3/§5 的前置 key `mw-write-face-guard` 正是为此） |
| D6 | 任务级依赖载体（**前置阻塞**） | `conductor._plan_task_order` :1717-1727 的输入侧；TS 镜像不存在 | `mentioned = [(plan.find(s), s) for s in stems if s in plan]` / `orphans = sorted(s for s in stems if s not in plan)` / `return [s for _, s in mentioned] + orphans` | 需要任务级 `depends_on`（`tasks/*.md` frontmatter 或 plan 机器可读表）；现状：全仓 `depends_on` 只存在于 roadmap key 级（`autopilot/roadmap.py:128 depends_on: tuple[str, ...]`、:483 `_parse_depends_on`） | 不需要锁（读取） | fail-open 会放大并发（spec §2.3 要求不可解析即回退串行）；若误把"未声明"当"无依赖"，就是默认放大 |
| D7 | 写面输入（**前置阻塞**） | `autopilot/dispatch.dispatch` :964-1196 与 `pm/task-dispatcher.ts:288` 的入队前判定 | 现状只有"派发时的卡片可满足性"：`WRITE_SURFACE_MARKER = "<!-- mw-write-surface: v1 -->"`（ui-bridge.ts:1394）+ worker 侧 bash 写面守卫（worker-mode.ts:717+） | 需要"同 key 在飞集合的写面"的机器可读数据（当前没有任何消费者做交集判定；`write_scope` 字段只出现在 gate schema：`autopilot/gates.py:136/175/291/790` 与 `conductor.py:7091`） | 需要（判定必须与入队同一临界区） | 两个 worker 写同一文件（P-018/P-019）：无写面数据时静默并行，只在事后由证据冲突暴露 |
| D8 | check-then-act 窗口收敛 | `autopilot/dispatch.dispatch` :1139-1156（取锁位置）vs 判定位置（调用方在锁外读 `rows`） | `lock = mw_common.lock_path(project_root)` / `mw_common.acquire_lock(lock)`；判定发生在 orchestrate（:698-747，未持锁） | 把"该 key 在飞数 / 卡身份"复查移入 `.mw/workers.lock` 临界区（读行 → 判定 → append 行），或引入每 key 的独立锁 | **需要** | 两个 conductor 实例（serve 重启重叠、`--once` 与常驻并存）或 conductor + PM 同时通过判定 → 同 `task_key` 双写；`upsert_worker_row` 覆盖语义掩盖第二次写（读回校验只查"恰好 1 行"，dispatch.py:1185-1196） |
| D9 | 计数口径统一（面板/抑制轴） | `autopilot/monitor.ts` :499-505 + :917-932；`autopilot/status-model.ts:1563-1590`；`conductor.py:6986-6992` | monitor：`if (!TERMINAL_WORKER_STATUSES.has(entry.status))`（path 口径）与 `workers` 只含 running；conductor：`_is_in_flight(row) and _row_belongs_to(row, key)` | 三处同口径的"在飞"定义（建议单一导出谓词 + pending 语义显式） | 不需要锁（只读呈现） | 放开后 `slotsUsed`（只数 running 的 conductor 行）会系统性低于 conductor 的实际在飞 key 数，"effective cap" 与面板不一致（AC-005/AC-007 的镜像要求） |
| D10 | gate facts / 自动决策同步 | `conductor.gate_facts` :6986-6992、`conductor.proposition_stage_close` :6403-6407 | `facts["in_flight_keys"] = [...]` / `if facts.get("in_flight_keys"):` / `return _prop_fail("stage-close-in-flight", ...)` | 与 D1 同一谓词（计数或身份） | 不需要锁 | 只改派发而不同步 facts → stage-close 自动决策与派发对"在飞"判断不一致（一个允许关、一个还在派） |
| D11 | 下游消费者同步（closure/review/提醒/defer） | `_stage_closure` :1288-1292、`review_batch` :4106-4110、`pending_gate_reminders` :3001-3004、`_defer_declined_gate` :7986-7990、`_dispatch_roadmap_writer` :1188-1190、`_xkey_proposal_in_flight` :4990-4996 | 见表 §B B13/B14/B15/B16/B17 | 同 D1/D3 的谓词 | 不需要锁（读） | 语义漂移：例如 `_stage_closure` 用旧布尔谓词时，per-key N>1 的 key 只要还有 1 个在飞就阻止关闭（保守，安全），但 `_defer_declined_gate` 会把"N 个在飞"当成"仍有活干"而延迟 pending-review（方向相反，需逐点定标） |

---

## §E 残留与未验证

1. **本仓未启用 autopilot**：`.agenticdoc/_autopilot/_roadmap.md` 不存在（`Test-Path` = False），`_autopilot/config.json` 不存在（只有 `timeline.jsonl` 505 B、`auto-decisions.jsonl` 1523 B）。因此本卡**没有在本仓跑真实 conductor 派发链**；§A/§B 全部是工作树静态判定复看，§C 的行计数是真实文件读取，真实并发实测只能引用上个 key 的 E2Feature 历史样本（`spec-worker-serialization-20260926.md` F3，未在本卡重算）。
2. **上个 key 文档的过期结论**：`spec-worker-serialization-20260926.md` 的 F2-E2/F3 断言"PM 手工派发把 task_key 起成 `ap-{key}-...` → 这些行会被 conductor 计入 `in_flight_keys`（`_row_belongs_to` 前缀匹配）"。当前工作树该行为已被 D-019/T-12 取代（§C3）。该文档的行号也已整体漂移（例如它引用的 `_deps_satisfied:2153`、`_is_in_flight:2131` 现在分别是 :3560、:3539）。**未验证**：D-019 落地前是否存在该前缀行为的历史运行样本对拍。
3. **xkey 通道（§A A15 / §B B17 / §D D11）未实测**：默认 `xkey_repair=false`（config.py:94），本仓无 config 文件。其"不受 key cap 约束、且在 in_flight_keys 计算之前派发"是**代码顺序判定**（conductor.py:687-696 早于 :698），不是运行实测。
4. **`advance.advance()` 阻塞 tick 未实测**：它是同步 `subprocess.run`（autopilot/advance.py:181-188，`timeout=_ADVANCE_TIMEOUT_SEC` = 120s，常量 :36），在 conductor 的 3 个点被调用：`_advance_key`（:1621）、`execute_loop`（:1801）、`_done_transaction`（:2749，经 `_verify_loop`） → 会阻塞整个 tick。放开 per-key 并行后这是 N 倍 tick 延迟的候选瓶颈，本卡未量化。
5. **launcher `pending_queue` 的跨 poll 行为未实测**：它只在本进程内存（launcher.py:1901），且只在 `for key in finished:`（:1754）内 drain；进程重启后靠 discover 重建。未做真实运行验证。
6. **未验证**：`_workers.parallel` 当前 7 行 `running` 是否对应真实存活进程（本卡只做文件读取，未查 pid 存活）。故"本仓真实并发 = 7"这个数字不可引用。
7. **未找到**（命令 + 输出）：任务级依赖载体。
   `grep -n "depends_on" packages/multi-workers/autopilot/*.py` 的非测试命中只有 `roadmap.py:128`（`depends_on: tuple[str, ...]`）、`:483`（`_parse_depends_on`）、`:557`、`:654`，全部是 roadmap key 级；`conductor.py` 中 `entry.depends_on` 只出现在 orchestrate 视图（:656）与 `_deps_satisfied`（:740/3560）。⇒ 任务级 `depends_on` **未找到**。

## §F 未覆盖面声明

- 不回答：key 前沿的排序/优先级、per-key 上界取值、写面重叠算法（属 design/其它卡）。
- 不覆盖：stage 状态机与 gate 生命周期语义（只覆盖它们作为派发门禁的部分）、`_index.parallel` 写入协议、`_workers.acked` 收敛路径、worker 看门狗/超时语义。
- 不覆盖：launcher 的 spawn 环境/凭证/target profile 撕票链（属其它 key）；`mw.py` CLI 与 doctor 面。
- 不覆盖：TS 面板渲染细节（只覆盖与"在飞计数口径"直接相关的 `slotsUsed` / `nonTerminalByKey`）。
- 未做：任何代码修改、任何测试执行、任何真实运行实验、任何 `npm install` / 快照写入。写面仅本文件。

---

[VERIFY] T-C1: ticket=mw-dynamic-concurrency/T-C1 rev=55be3d960 dispatch_chain_steps=27(A0 main-loop tick 8370-8371 + A1..A26, orchestrate 595-747; max-dispatch points=4: roadmap-writer<=1@630/644, xkey-proposal<=approved-tickets@695, key-cap@744, per-key<=1@746) per_key_serial_points=17(gate=11:B1,B2,B3,B4,B5,B7,B8,B9,B10,B13,B17; structural=3:B6,B11,B12; policy=3:B14,B15,B16) two_channel_share=queue-file+lock+launcher-spawn-only(launcher.py:1776,1805-1813,1854-1858,2008; lock .mw/workers.lock) pm_manual_rows_counted_as_key_inflight=false(conductor.py:3543-3546 -> mw_common.py:2026-2036 origin-first; measured: queue_rows=419 origin_conductor=0 nonterminal_rows=7 keys_conductor_inflight=0 keys_path_inflight=3) synthetic_probe: manual=False legacy=False conductor=True release_points=11(D1-D11; blockers=3: task-level deps absent, write-face set absent, in-flight check outside workers.lock) config: max_parallel_keys default=2 floor=(2,None) launcher_max_workers default=8 machine_overridable=(xkey_verify_cmd,xkey_verify_cwd) index_keys=57 claims={dead:41,free:9,live:4,stale:3} tests_asserting_no_slot=test_autopilot_attribution.py::test_six_prefix_rows_are_manual_and_consume_no_slot
