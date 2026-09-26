# Research: 并发/并行度上限全清单与生效链（RQ-1 / msc-rq1）

> 只读角色。本文件是本卡唯一写面（另加本人 worker 目录下的 output.md 报告）。
> 所有行号对应 2026-09-26 工作树快照（`conductor.py` 174500 B / `launcher.py` 47583 B / `mw.py` 238514 B / `mw_common.py` 144421 B）。

## 决策问题

为 spec §1.1（"slot 到底指什么"）、draft AC-001（三层上限完整清单）、§4 U-4（要提 key 层还是 worker 层）补全并**锚定** PM 已采的最小事实集（`spec-slot-framing-20260926.md`）。要回答：

- Q1 `max_parallel_keys` 的完整生效链：在哪读、gate 什么、`in_flight_keys` 如何统计（什么算"在飞"、stalled 是否占额、done/idle 是否立即释放）。
- Q2 worker 层：单 key 内并发几个？全局并发几个？**有无硬/隐式上限**（无则给反证式范围声明）。
- Q3 serve/launcher 层：主循环是否并发？几个项目几个 serve？多 serve 之间共享什么计数/端口。
- Q4 影响"同时能跑几个 worker"的全部 env 与常量，含是否落盘（P-015）。
- Q5 达到上限时的行为（跳过/排队/丢弃）与可观测痕迹（决定 RQ-3 能否量化"槽位等待"）。

**不做**：取值建议（"应该改成 N"）属 RQ-4；成因三态判定属 AC-002；吞吐实测属 RQ-3。

## 调研方法与出处

### grep 模式（逐条列出，均为只读）

1. `max_parallel_keys|in_flight_keys` over `packages/multi-workers` + `packages/coding-agent/src`
2. `max_workers|max-workers|maxWorkers` over 同上
3. `running_procs\)|len\(running_procs\)|pending_queue|Semaphore|semaphore|concurrent\.futures|ThreadPool|threading\.` over `packages/multi-workers/*.py` + `autopilot/*.py`
4. `concurren|inFlight|max_concurrent|maxConcurrent|slotLimit|Semaphore|queueDepth|maxRunning|runningCount` over `packages/coding-agent/src/extensions/agent-team-loop`
5. `PI_WORKER_[A-Z_]+` over `packages/`（含 `dist/` 与 tests）
6. `def tick|def orchestrate|def _advance_key|def execute_loop|def _verify_loop|def _is_in_flight|def _row_belongs_to|def mark_stalled|def _xkey_proposal` over `autopilot/conductor.py`
7. `_TERMINAL_STATUSES` over `packages/multi-workers`
8. `slots|slot` over `packages/multi-workers/*.py` + `autopilot/*.py`（确认 Python 侧有无 slot 概念）
9. `EFFECTIVE_KEYS|EMPTY_VALUE|def load_effective` over `autopilot/effective_config.py`
10. `def _poll_once|def run|def _spawn|def _reconcile_orphans|def _stripped_env|def _build_env|DEFAULT_POLL_INTERVAL` over `launcher.py`
11. `proxy_already_running|_port_is_bound|def cmd_serve|def cmd_start|max-workers` over `mw.py`
12. `Semaphore|ThreadingHTTPServer|daemon_threads|_request_lock|max_workers` over 外部依赖 `E:\CLI_workspace\claude-hook\timi-proxy-cli\src\timi_proxy_cli\proxy.py`
13. `def dispatchTask|dispatch_task|task_key` over `packages/coding-agent/src/extensions/agent-team-loop/pm`
14. `def startMw|def restartMw` over `shared/mw-runner.ts`
15. `def update_status|def orphan_dead_after|def pid_file|def workers_path|def lock_path|def port_is_bound|def _doctor_autopilot` over `mw_common.py`

### 读过的文件:行（read 工具，全读或标注行段）

- `autopilot/config.py`（整文件）
- `autopilot/conductor.py`：87–120、180–400、900–1040、1062–1120、1560–1600、2040–2170、2875–3050、3944–4030、4096–4156
- `autopilot/effective_config.py`（整文件）
- `autopilot/dispatch.py`：470–620
- `autopilot/xkey.py` 仅 grep 命中处
- `launcher.py`：45–118、223–280、367–378、555–632、775–980、1017–1048
- `mw.py`：105–180、202–420、5040–5048
- `mw_common.py`：150–170、1425–1560、1567–1635、1640–1700、1850–1935、2022–2065
- `proxy_multi.py`（整文件）
- `coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`：240–272、430–625
- `.../autopilot/status-model.ts`：70–150、245–305
- `.../worker/worker-mode.ts`：140–190、600–610、735–750、885–900
- `.../worker/output-writer.ts`：1–120
- `.../pm/ui-bridge.ts`：1195–1275
- `.../pm/task-dispatcher.ts`：280–300
- `.../pm/pm-orchestrator.ts`：420–500
- `.../shared/mw-runner.ts`：124–164、318–335
- `E:\...\timi_proxy_cli\proxy.py`：225–355
- 外部记忆：`.agenticdoc/_pitfalls.md`（P-015/P-018/P-019/P-022）

### 现场只读数据

- `.agenticdoc/_workers.parallel`（MW 项目，读取时刻：4 行 `running`，全部属同一个 key `mw-autopilot-slot-capacity`）
- `.agenticdoc/mw-autopilot-slot-capacity/`（无 `_roadmap.md`；MW 项目无 `.agenticdoc/_autopilot/config.json`）
- `.agenticdoc/_index.parallel` 表头

---

## 发现

### Q1 —— key 层：`max_parallel_keys` 的完整生效链

**(1) 定义与值域【事实】**
- `autopilot/config.py:16` 注释 `max_parallel_keys  int     2    (floor 2)`；`:52` 默认 `2`；`:70` `_INT_RANGES["max_parallel_keys"] = (2, None)` ⇒ **下限 2、无上限**。
- TS 镜像逐字段一致：`status-model.ts:79`（类型）、`:106`（`DEFAULT_CONFIG` = 2）、`:136`（`INT_RANGES` `[2, null]`）、`:271`（`intOf`）、`:296`（merged）、`:1050`/`:1166`（status JSON）、`:1199`（状态行文本）。
- **可配置层只有项目层**：`effective_config.py:62-65` `EFFECTIVE_KEYS = ("xkey_verify_cmd", "xkey_verify_cwd")`；`load_effective`（`:170-235`）对非 `EFFECTIVE_KEYS` 的键只判 `project` / `default`（`:214-219`）。⇒ `max_parallel_keys` **不可机器层覆盖**；机器层写了它会被 fail-soft 丢弃并产生 diagnostic（`effective_config.py:150-155` `"{key!r} is not machine-overridable (ignored)"`）。
- 文档已登记该键：`packages/multi-workers/README.md:225` `| max_parallel_keys | 2 | 同时推进的 key 上限 |`。

**(2) 读点：全仓只有一处 gate【事实】**
grep(1) 的完整命中：`config.py:16/52/70`、`conductor.py:258/287/289/292`、TS 侧 `status-model.ts:79/106/136/255/271/296/1050/1166/1199`、`monitor.ts:522`。除 conductor 的派发 gate 外全部是**读取展示/校验**。⇒ 生效链只有一条：`config.json` → `_load_effective_config` → `orchestrate()` 的派发循环。

- 读入：`conductor.py:189` `cfg = _load_effective_config(project_root)`；`conductor.py:87-106` 先铺 `config.default_config()` 再叠项目层 `config.cached_load`（每次 tick 重读，无缓存），再按 `EFFECTIVE_KEYS` 叠机器层。
- 唯一 gate：**`autopilot/conductor.py:289`**
  `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):`
  紧跟 `:290` `continue  # parallel cap — key starts on a later tick`。
- `max(1, ...)` 的 1 是防御性下限；因 `_INT_RANGES` 已限 >= 2，实际不可能低于 2（除非项目层文件绕过校验，不可能——`validate_config` fail-closed，`config.py:89-119`）。

★ `conductor.py:289` 的**判定表达式原文**（`orchestrate` 内、stage × key 双层循环里）：
```python
for stage in rm.stages:                      # :268
    if stage.status != "running": continue   # :269-270
    _stage_closure(...)                      # :274
    for entry in stage.keys:                 # :275
        key = entry.key
        if status_of.get(key) in ("done", "stalled", "closed-legacy"): continue   # :276-277
        ...
        if key in in_flight_keys: continue                       # :287-288  “wait for the in-flight worker”
        if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):  # :289
            continue  # parallel cap — key starts on a later tick          # :290
        if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):# :291
            in_flight_keys.add(key)                                    # :292
```

**(3) `in_flight_keys` 如何统计【事实】**
`autopilot/conductor.py:258-264`：
```python
in_flight_keys = {
    key
    for key in deps_of
    if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows)
}
```
- `rows` = `mw_common.parse_workers_file(.agenticdoc/_workers.parallel)`（`conductor.py:200`）；**只看 `_workers.parallel`，不看 phase、不看 key-status、不看 `_index.parallel` 的 Phase 列**。
- "在飞" 定义：`conductor.py:2131-2132`
  `def _is_in_flight(row): return row.get("status","") not in mw_common._TERMINAL_STATUSES`
  `mw_common.py:158`（同值副本 `:1654`）`_TERMINAL_STATUSES = {"done","failed","needs-clarification"}`
  ⇒ **非终态即占额**：`pending`（已派发未 spawn）、`running`，以及任何非三态的脏值（含空串）都算在飞。
- 归属判定：`conductor.py:2135-2138`
  ```python
  if str(row.get("task_key","")).startswith(f"ap-{key}-"): return True
  task_path = str(row.get("task_path","")).replace("\\","/")
  return f".agenticdoc/{key}/workers/" in task_path
  ```
  ⇒ 第二条命中**任何**把 task.md 放在该 key 的 workers 目录下的行，**包括 PM 手工 `dispatch_task` 派发的非 `ap-` 前缀行**。
- 候选键域是 `deps_of`（roadmap 里声明过的 key，`conductor.py:214-219`）⇒ 不在 roadmap 的 key（例如 `_scratch`、以及**本 MW 项目当前这个 key**，因为它没有 `_roadmap.md`）**永不计入 `in_flight_keys`**，也就永远不会被 `:289` gate 到。

**(4) 每种 key 状态是否占额【事实】**
| key 状态 | 在 `:276-277` 被跳过？ | 有非终态行时占 `in_flight_keys` 名额？ |
|---|---|---|
| `done` | 是 | 否（done worker 行是终态；但若该 key 下另有一个非终态行，仍占额——见下） |
| `stalled` | 是（不再派发） | **是**——`in_flight_keys` 与 key 状态无关；`:3944 mark_stalled` 只改 roadmap/key-status/gate/achieved.md/pattern，**不触碰 `_workers.parallel`** |
| `closed-legacy` | 是 | 同上（若有残留非终态行仍占额） |
| `running`/其他 | 否 | 是 |

⇒ **风险 1 成立且有锚点**：stalled 本身不占额，但"stalled 前遗留的未收敛 worker 行"占额，且没有任何代码因 stalled 而清理它。释放只能靠：worker 自退（超时看门狗/墙钟）→ launcher 下一 poll 置 `failed`；或 launcher 的 orphan 静默规则（`launcher.py:786-800`，无活动 ≥ `PI_WORKER_ORPHAN_DEAD_MIN`=90m 才判 failed，且要 `other_live_launcher` 为假）。

**(5) done/idle 是否"立即"释放【事实】**
- 释放是**下一 tick 重算**：`in_flight_keys` 每 tick 从文件重建（无内存状态，D-102）。
- 行的 `running → done/failed/needs-clarification` 由 launcher 在**下一 poll**（默认 5s，`launcher.py:49/880`）`p.poll()` 到子进程退出后写（`launcher.py:795-806` → `_exit_to_status` `:367-374`）。
- key 变 `done` 走的也是 conductor 自己的 `_mark_key_done`（不是这里的释放路径）。
- ⇒ 释放延迟上界 ≈ worker 退出时刻 + launcher poll 间隔（≤5s）+ conductor tick 间隔（`poll_interval_sec`，默认 4s）。**不是立即**。
- 关键：tick 的 gate 是"`len(in_flight_keys) >= cap` 就不起**新** key"，而不是"逐出超额 key"——已占额的 key 不会被中断，所以瞬时并发可以短暂大于 cap（例如 cap 从更大值下调、或 key 由别的通道派发）。

### Q2 —— worker 层：是否存在上限？

**(1) 单 key 内【事实】**
- conductor 通道：**每 key 同时最多 1 个在飞 worker**。两重保证：(a) `:287-288` 只要 key 已任一非终态行就 `continue`；(b) `_advance_key` 每次调用最多派发 1 个（`conductor.py:908-1015`：`execute_loop` / `_verify_loop` 或一次 `dispatch.dispatch`，随后 `return`）。设计陈述见 `conductor.py:1075` docstring `per-key serial (one in-flight exec task)` 与 `:1096` `return False  # per-key serial: wait for the in-flight task`。
- PM 手工通道：**无此约束**。`pm/ui-bridge.ts:1257-1260` 的 `dispatch_task` 工具只查 `taskDir` 是否已存在（`:1223-1231`），不查该 key 已有几个在飞；`pm/task-dispatcher.ts:284-297` `dispatchTask` 只做 upsert；`pm/pm-orchestrator.ts:420-486` 的后台扫描把**所有**未派发的 task 一次性全派（`:464` 循环，无计数/预算）。
- **现场实证【事实】**：读取时刻的 `.agenticdoc/_workers.parallel` 有 **4 行 `running`**（`msc-rq1-concurrency-anchors` … `msc-rq4-change-space`），全部属同一个 key `mw-autopilot-slot-capacity`，且该 key 既无 `_roadmap.md` 也无 `.agenticdoc/_autopilot/config.json`（autopilot 未启用，conductor 不在跑）。⇒ 4 个 worker 并发于一个 key，且 `4 > max_parallel_keys(2)`：**key 层 cap 完全不约束 PM 派发通道**。

**(2) 全局【事实】**
- 唯一显式全局上限：launcher 的 `--max-workers`：`launcher.py:837-840`
  ```python
  if max_workers and len(running_procs) >= max_workers:
      if not any(q["task_key"] == key for q in pending_queue):
          pending_queue.append(entry)  # AC-007
      continue
  ```
  默认 `None`（`launcher.py:1021`）⇒ **默认无上限**。serve 只在显式传了才转发（`mw.py:327-328`），`--max-workers` 是 serve CLI 参数（`mw.py:5043`），**不落盘**（见 Q4）。
- 无其他机制：`launcher._poll_once` 每轮 `for entry in entries: if status!="pending": continue ... _spawn(...)`（`launcher.py:822-840`），**没有取前 N 行**、没有 batch/head/limit；`_spawn` 是非阻塞 `subprocess.Popen`（`launcher.py:958`）后立即 `running_procs[task_key] = proc`（`:959`），**不 join、不 wait**。
- 外部 proxy：`timi_proxy_cli/proxy.py:230-231` `class _ConfiguredThreadingHTTPServer(ThreadingHTTPServer): daemon_threads = True`；`:241` `_request_lock` 仅保护 `next_request_id` 计数器（`:249-251`）。⇒ **thread-per-connection，无并发上限**。

**(3) 反证式范围声明（"本范围内不存在 worker 层上限"）【事实/范围】**
- 范围 A：`packages/multi-workers/*.py` + `autopilot/*.py` 全量 grep(3)。命中仅：`launcher.py:780/837/838/846/867/876`（本卡的 `max_workers`/`pending_queue`）、`mw.py:327/328/423/424/4495/4965/5044`（CLI 透传）、`proxy_multi.py:106` 与 `mw.py:234`/`conductor.py:4129`（`threading.Event` 用于退出信号，与并发上限无关）。**该范围内除 `max_workers` 外零并发限制原语**：无 `Semaphore`、无 `concurrent.futures`、无 `ThreadPool`、无 `asyncio`、无内存队列（`pending_queue` 只在 `max_workers` 非 None 时才可能非空）。
- 范围 B：`launcher.py` 全函数清单已核对（`_poll_once` / `run` / `_spawn` / `_reconcile_orphans` / `_drain` 逻辑），派发路径逐行读过（`775-980`）。除 `:837` 无任何计数判断。
- 范围 C：TS 侧 `packages/coding-agent/src/extensions/agent-team-loop/**` grep(4)。命中仅 `monitor.ts` 的 `slots*`/`inFlight`（**纯展示**，`:521-522`、`:503`）与 3 处"concurrent lock/rename"注释（`gate-writer.ts:137`、`pm-orchestrator.ts:629`、`ack-store.ts:12`、`rag/budget.ts:10`——均与 worker 数无关）。PM 注册的其它工具（`dispatch_task`、`pm run`、`/mw ...`）无一读取在飞计数。
- 范围 D：conductor 的**每 tick 派发数**。`orchestrate` 的 key 循环受 `:289` 限制（每 tick 最多补到 cap）；但 **xkey 提案通道绕过 cap**【事实】：`conductor.py:2875-2922 _xkey_proposal_stage` 在计算 `in_flight_keys` **之前**执行（`:243-254`），对每个 `status==approved && 无 proposal.md` 的 ticket 派 1 个 worker（`_xkey_proposal_one` `:3005-3048`，`dispatch.dispatch` 于 `:3036`），仅受 `_XKEY_PROPOSAL_MAX_ATTEMPTS = 2`（`:2872`）与 `tickets_iter` 条数约束。⇒ 在 `xkey_repair=true` 的项目里，同一 tick 可派发 **N(approved tickets)** 个 worker，`max_parallel_keys` 不参与判断。默认 `xkey_repair=false`（`config.py:58`）时不触发。
- 范围 E：`round_budget`（默认 2，`config.py:53/71`）是**轮数**预算不是并发预算：读点 `conductor.py:964`（L2 边）、`:1086`（EXECUTE 每任务尝试）、`:1593`/`:1735`（L3 修复轮）。它限制"同一 loop 重试几次"，不限制同时几个 worker。`_resume_credits`（`:2273`）与 `_budget_bonus`（`:2216`）只放宽轮数。

**结论（Q2）**：worker 层**不存在任何显式或隐式硬上限**；默认全局并发 = `_workers.parallel` 里非终态行数（由 PM 派发自由度 + autopilot 每 key ≤1 决定），opt-in 上限只有 `launcher --max-workers`。**U-4 的答案是：现状"worker 层无上限"，只有"key 层上限"是真正的闸**。

### Q3 —— serve / launcher 层

**(1) 主循环【事实】** `mw.py:353-374`：单线程 `while True` 顺序执行——检查 stop 文件 → `launcher_proc.poll()` → `proxy_proc.poll()` → `_conductor_supervise_step(...)` → `time.sleep(1)`。**serve 自己不 spawn worker**，只起/督 3 个子进程：proxy、launcher、conductor（`mw.py:270-335`；`_conductor_decision`/`_conductor_supervise_step` `mw.py:136-200`）。launcher 也是单线程 `while True: _poll_once(...); time.sleep(poll_interval)`（`launcher.py:844-880`），但它对每个 pending 行**并发地**非阻塞 spawn（见 Q2），所以"单线程"不等于"串行执行 worker"。

**(2) 一个项目几个 serve【事实】** 一个：`mw.py:209-215` 若 `.mw/mw.pid` 指向活进程则拒绝启动（`_pid_path` → `mw_common.pid_file` = `<project>/.mw/mw.pid`，`mw_common.py:1567-1568`）。多个项目 ⇒ 多个独立 serve，各带自己的 launcher + conductor + proxy。

**(3) 多 serve 之间共享什么【事实】**
- **不共享任何 worker/key 计数**：所有账本与锁都锚在各自 `<project>/.mw`、`<project>/.agenticdoc`：`_workers.parallel`（`mw_common.py:1432-1433`）、`workers.lock`（`:1440-1441`）、`mw.pid`（`:1567`）、launcher beat `launcher-beat.<pid>`（`:1860-1877`，且 `other_live_launcher` 只 glob 同一个 `.mw`）。
- **共享一个 proxy 进程（按端口）**：默认端口 `--pi-port 7001` / `--claude-port 7003`（`mw.py:5040-5041`、`proxy_multi.py:127-128`）。`mw.py:299` `proxy_already_running = _port_is_bound(args.pi_port) and _port_is_bound(args.claude_port)`；两个端口都被占时**新 serve 不启动 proxy，复用已有的**（`:305-310` 打印 `sharing existing proxy`）。`_port_is_bound` = `connect_ex(("127.0.0.1", port)) == 0`（`mw_common.py:1612-1617`）。⇒ 机器上多项目默认共用**同一个 proxy 进程**；proxy 无并发上限（Q2(2)），所以它不构成计数型共享，但它是共享的**上游连接/限流面**（外部）。
- 同项目内"多个 launcher"：进程层面允许（绕开 serve 直接跑 launcher.py），但两者**不共享 `running_procs`**，beat 协议只用于 orphan 静默规则让位（`launcher.py:786-800`、`mw_common.py:1878-1916`），**没有"谁已 spawn 此 pending 行"的互斥**：`launcher.py:825-826` 的 `if key in running_procs: continue` 只是进程内判断，`update_status`（`mw_common.py:1512-1526`）是无条件 RMW，不校验当前状态。⇒【推断】同一项目跑两个 launcher 会对同一 pending 行重复 spawn；可验证方法：临时项目写 1 行 pending，同时起 2 个 `launcher.py --poll-interval 1`，统计 `[launcher] ... model=` 打印次数 / 子进程数（预期 2 而非 1）。当前部署无此形态（serve 的 pid 守卫排除了双 serve），故未实测。

### Q4 —— env 与常量清单（影响"同时能跑几个 worker"）

**env（全部为进程 env，均不落盘）**

| 变量 | 默认 | 读取位置 | 对并发的作用 | 落盘 |
|---|---|---|---|---|
| `PI_WORKER_TASK` | 无 | 写：`launcher.py:248/266/275/298/326`；读：`coding-agent/src/extensions/agent-team-loop/index.ts:61`、`worker-mode.ts:603` | 模式开关：设了即进 Worker 模式，**worker 不注册任何工具**（`agent-team-loop.test.ts:2760` 断言）⇒ worker 无法再派 worker，无嵌套扇出 | 否（launcher 每 spawn 注入，值取自 task_path） |
| `PI_WORKER_TIMEOUT_MS` | `DEFAULT_BUDGET_MS` = 3600000（60m） | `worker-mode.ts:164-169` `resolveBudgetMs`；调用点 `:742`（RAG 预算）、`:894` | 墙钟兜底；决定单个 worker **占槽最长时间**（超时自杀→退出→launcher 置 failed→释放） | **否**（P-015：只活在 serve→launcher→worker 继承链；`/mw restart` 换窗口即丢） |
| `PI_WORKER_IDLE_MS` | `DEFAULT_IDLE_MS` = 600000（10m） | `worker-mode.ts:171-175` `resolveIdleMs`；调用点 `:895` | 活动看门狗判死阈值；直接决定槽位占用时长与 GC-4 误杀风险 | **否**（P-015 实证坑） |
| `PI_WORKER_ORPHAN_DEAD_MIN` | 90（分钟） | `mw_common.py:1918-1930` 读 `os.environ` | launcher orphan 静默窗口：非终态僵尸行多久后被判 `failed` 从而**释放槽位** | 否 |
| `PI_CODING_AGENT_DIR` | `~/.pi/agent` | `mw_common.py:1640-1645` | 扩展发现路径（间接） | 否 |
| `MW_UPSTREAM_HOST` / `MW_UPSTREAM_PORT` / `MW_UPSTREAM_BASE_PATH` | `api.timiai.woa.com` / `80` / `/ai_api_manage/llmproxy` | `proxy_multi.py:21-27` | 共享 proxy 的上游（非并发上限，但上游限流面在这里） | 否 |
| `MW_AUTOPILOT_FILE` / `MW_AUTOPILOT_HOME` | 无 | `effective_config.py:96-98/118-131` | 机器层配置文件定位；**不含 `max_parallel_keys`** | 否 |

**常量 / CLI 参数**

| 名称 | 默认 | 位置 | 作用 | 落盘 |
|---|---|---|---|---|
| `launcher --max-workers` | `None`（无上限） | `launcher.py:1021`；serve 透传 `mw.py:327-328`、`cmd_start` `:423-424`；`mw.py:5043` 定义 | **唯一 worker 层全局上限（opt-in）** | **否**（CLI 参数不进 `config.json`；`/mw restart` 走 `startMw` → `mw.py start --project=<dir>`，**不带 `--max-workers`**，`shared/mw-runner.ts:124-135`） |
| `launcher --poll-interval` / `DEFAULT_POLL_INTERVAL` | 5 s | `launcher.py:49`、`:880` | 派发/收割节拍（影响释放延迟，不影响上限） | 否（CLI default） |
| autopilot `poll_interval_sec` | 4（1..5） | `config.py:51/69`；conductor tick：`conductor.py:4149-4151` | conductor tick 节拍 = 槽位再分配节拍 | **是**（`config.json`） |
| autopilot `round_budget` | 2（>=1） | `config.py:53/71`；`conductor.py:964/1086/1593/1735` | 每 loop 轮数预算（非并发） | 是 |
| autopilot `worker_timeout_min` | 30 | `config.py:54/72` | 派发到 task.md 的 timeout 头 | 是 |
| autopilot `xkey_verify_timeout_s` | 1800 | `config.py:63` | conductor 侧子进程超时 | 是 |
| `_XKEY_PROPOSAL_MAX_ATTEMPTS` | 2 | `conductor.py:2872` | 每 ticket 提案重试次数（非并发） | 代码常量 |
| serve ports `--pi-port` / `--claude-port` | 7001 / 7003 | `mw.py:5040-5041`；`proxy_multi.py:127-128` | 机器级共享的 proxy 端口 | 否 |
| serve 监督循环 | `time.sleep(1)` | `mw.py:374` | 子进程拉起/自愈节拍 | 代码常量 |
| `DEFAULT_BUDGET_MS` | 3600000 | `worker-mode.ts:151` | `PI_WORKER_TIMEOUT_MS` 兜底 | 代码常量 |
| `DEFAULT_IDLE_MS` | 600000 | `worker-mode.ts:157` | `PI_WORKER_IDLE_MS` 兜底 | 代码常量 |
| `CHECKPOINT_ANCHOR_MS` / `CHECKPOINT_REFRESH_MS` / `STEER_MIN_MS` | 30m / 10m / 5m | `worker-mode.ts:159-161` | 收敛检查点与 deadline steer 时机（GC-4） | 代码常量 |
| `_BEAT_FRESH_SEC` / `_DEFAULT_ORPHAN_DEAD_MIN` | 30 s / 90 min | `mw_common.py:1862-1863` | 跨 launcher beat 新鲜度 / orphan 静默窗口 | 代码常量 |

⇒ **P-015 的适用面比台账写得更宽**：除 `PI_WORKER_IDLE_MS`/`PI_WORKER_TIMEOUT_MS` 外，**`--max-workers`（唯一的 worker 层上限）同样不落盘**，且它的重启丢失路径与 env 不同——env 至少可能被窗口继承，`--max-workers` 是 serve 的 argv，`startMw` 根本不带它。

### Q5 —— 达到上限时的行为与可观测痕迹

**(1) key 层（conductor）【事实】**
- 行为 = **本轮跳过、下轮再试**（`:289-290` 纯 `continue`，无队列、无丢弃、无顺序保证）。下一 tick 重新评估，所以被跳过的 key 的"等待时长"是**不定长**的（无 FIFO、无 aging，取决于哪个 key 先释放；stage/keys 的声明顺序决定同 tick 的优先）。
- **可观测痕迹：零**。`:289-290` 不写 timeline、不写 roadmap、不写任何文件。grep(6) 的 timeline 事件词表里没有 cap/slot/queue 类事件；`:276-283` 的 `skip` 事件只用于 **live foreign claim**（另一种跳过），不覆盖 cap 跳过。
- ⇒ RQ-3 只能**间接推断**【推断，附验证方法】：
  - 直接可读的只有 `beat`（每 tick 一条，`conductor.py:2056` 附近）与 `dispatch`（每次派发一条）。"因 cap 未派发的 tick 数"需要把 `beat` 序列与 `dispatch` 序列对齐后，再用**当时的** roadmap key-status / `_workers.parallel` 行状态判定"这个 tick 里有 ≥1 个 eligible 但未派发的 key"。这些中间状态**不进 timeline**；`_workers.parallel` 只保留最后状态（`update_status` 覆盖写），历史被抹掉。
  - 因此 AC-003 的"因 `max_parallel_keys` 而未派发的 tick 次数"**当前不可直接测量**；可行的替代：从 `_workers.parallel` 行的 `dispatched_at`/`updated_at` 反推每个 key 的占用区间，再与 `poll_interval_sec` 网格求"cap 饱和且存在 eligible 未派发 key"的时长（采样误差 ≥ 1 tick，且依赖行级时间戳精度）。验证方法：在测试项目里用 faux provider + cap=2 + 3 个 eligible key，跑 N tick，断言 timeline 中**不存在**任何 cap 事件（证明零痕迹），并验证上述反推算法在合成数据上的误差界。
- 唯一对外可视化是 TS monitor：`monitor.ts:521-522` `slotsUsed: busyKeys.size` / `slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`，渲染于 `:596` `slots ${a.slotsUsed}/${a.slotsMax}`；`:503` 每 key `inFlight` 数。**两处口径与 conductor 的 `in_flight_keys` 不一致**：
  - monitor 的 `busyKeys` 只统计 `entry.status === "running"` 的行（`monitor.ts:246-252` 构造 `workers` 时已过滤），conductor 的 `in_flight_keys` 把 `pending` 也算在飞 ⇒ **派发后未 spawn 的窗口内两者不同**。
  - monitor 的 owner 归属靠 `w.taskKey.startsWith("ap-${key}-")`（`:501`），非 `ap-` 前缀的行会落到 `owner ?? w.taskKey`（`:510`）⇒ PM 手工派发的行会把 `slotsUsed` 拉高到超过 `slotsMax`（可显示 `slots 4/2`）。
  - `pending` 行会让 `slotsUsed` 偏低（例如 conductor 已占满 2 槽但都还没 spawn 时显示 `0/2`）。
  - ⇒ AC-006 若要求"不新增误报（无 running worker 的项目显示 0/2 而非报错）"这一半已满足（`deriveAutopilotPanel` 全源降级，`monitor.ts:461-463` 注释），但"显示当前槽位用量的**来源**"目前缺：`mw doctor` 的 autopilot 节（`mw_common.py:2022-2061`）**完全没有 slot / max_parallel_keys 字段**（grep(8) 在 Python 侧 `slots` 零命中）。

**(2) worker 层（launcher `max_workers`）【事实】**
- 行为 = 跳过 + **进程内内存排队**：`:837-840` 把行 append 进 `pending_queue`（去重靠 `:838`，否则同一行每 poll 都会重复入队）；`:810-813` 在 reaped 一个进程后 `pending_queue.pop(0)` 立即补一个。⇒ 是"下轮/空槽再试"，不是丢弃。
- **可观测痕迹：零**。跳过分支不打印、不写 worker.log、不写 timeline（launcher 没有 timeline；`_record_reconcile`/`_record_spawn_failure` 只覆盖 reconcile/spawn 失败，`launcher.py:57-87`）。行状态保持 `pending`（`updated_at` 不变），这是唯一痕迹。
- 隐患【事实】：`pending_queue` 是内存态，`run()` 重启即清空；但行仍是 `pending` 会被重新发现，语义无损（不丢任务，只丢队列顺序）。

---

## 结论 → 决策映射

- **spec §1.1（"slot 是什么"）**：必须写死是"**key 槽**"，并补一句：它是一个**只约束 conductor 派发通道**的闸；PM 手工 `dispatch_task` / `pm run` 通道**不受它约束**（现场 4 个同 key 并发即是实证，见 Q2(1)）。monitor 面板上的 `slots used/max` 用的是第三种口径（running-only、非 `ap-` 前缀单独计数），与 conductor 的 `in_flight_keys`（pending+running、按 key 去重）**不等价**——AC-001 的"完整清单"必须把这三套口径并列，否则 spec 与实现会各说各话。
- **draft AC-001（三层清单）**：本笔记给出三层 + 两张表的完整锚点。**关键补全**（PM 已采事实集里没有的）：(a) `max_parallel_keys` **不可机器层覆盖**（`effective_config.py:62-65`）；(b) 默认**无 worker 层上限**，`launcher --max-workers` 是唯一 opt-in 上限且**不落盘**；(c) `in_flight_keys` 把 `pending` 算在飞、且 PM 手工行按 task_path 计入；(d) **stalled 不清行、残留非终态行继续占额**；(e) xkey 提案通道**绕过 cap**（`xkey_repair=true` 时同一 tick 可派 N 个）；(f) proxy 是 thread-per-connection 无限并发、且多项目默认共用同一进程。
- **§4 U-4（提 key 层还是 worker 层）**：现状事实是"key 层有 cap=2，worker 层无 cap 但每 key 由 conductor 串行化、由 PM 通道放开"。所以提高 key 层 cap 的直接收益受 `每 key 只有 1 个在飞 worker` 限制——cap=4 意味着最多 4 个 worker 同时跑；而**不改 cap、改用 PM 通道手动派发**已经能拿到任意并发（现场 4 个即如此）。U-4 的两个选项在"能同时跑几个 worker"上不等价：这是一个**结构性**选择，不是单纯调数字。
- **§4 风险 1（stalled 占槽）**：确认机制缺口——`mark_stalled`（`conductor.py:3944`）不清理队列行；释放只靠 worker 自杀/超时（`PI_WORKER_TIMEOUT_MS` 60m / `PI_WORKER_IDLE_MS` 10m）或 launcher 的 90m 静默 reconcile。**这是 AC-001 必须列入的"上限项"**（隐性、时间型）。
- **§4 风险 3（rate limit）**：代码内无任何限流/配额计数；上游限流面在共享 proxy 之后（外部），本仓不可判——见数据缺口。
- **§5 记忆前馈（P-015）**：本卡扩展了 P-015 的清单——`launcher --max-workers` 与 `PI_WORKER_IDLE_MS`/`PI_WORKER_TIMEOUT_MS` 同属"不落盘的并发/超时参数"。任何"把并行度改成 env"的方案都会继承 P-015：`/mw restart` 走 `startMw`（`mw-runner.ts:128`）只带 `--project`，**并行度参数必然回退默认**。

## 数据缺口（无法从本仓代码确认）

1. **上游/供应商并发与限流上限**：proxy 上游（`api.timiai.woa.com` / timi-proxy-cli）与各 provider 的并发/RPM/TPM 配额，本仓无描述；`timi_proxy_cli` 是外部私有包，仅确认其 HTTP server 本身不限并发（`proxy.py:230-231`）。
2. **机器资源上限**（CPU 核数 / 内存 / 磁盘 / 句柄数）：无代码表达；每个 worker 是一个完整 pi 进程，实际上限由 OS 决定。未测量。
3. **两个 launcher 同项目的重复 spawn 是否真会发**：代码形状上无互斥（Q3(3)），未实测。
4. **`_index.parallel` 的 Claim/Phase 是否参与任何并发判定**：本卡确认 conductor 的 `in_flight_keys` 不用它（Q1(3)），但 `shared/implementation-gate.ts` 的 claim liveness 会不会间接卡住 worker 的写权限（进而拖长占槽），未逐行核（越出 RQ-1 边界，属 RQ-2/实现门禁面）。
5. **历史是否曾有 worker 层上限**：未查 git log（本卡范围是现状代码事实；成因三态判定属 AC-002，建议交 RQ-2/RQ-4 查 `README.md:225` 与 `config.py` 的引入提交）。
6. **`slotsUsed` 在生产里是否真的出现过 `> slotsMax`**：属 RQ-3 的实测面（需要历史 monitor 快照或从 `_workers.parallel` 重建），本卡只给出口径差异。

## 机器行

[VERIFY] RQ-1: key_layer=conductor.py:289(max_parallel_keys default 2/floor 2/no upper bound/project-layer only) worker_layer=no-cap-by-default(launcher.py:837; opt-in --max-workers default None, not persisted) per_key_conductor=1(conductor.py:287-288,1075) per_key_pm=unbounded(ui-bridge.ts:1223-1260, pm-orchestrator.ts:464) serve_layer=single-thread-supervisor(mw.py:353-374) one-serve-per-project(mw.py:209) shared=proxy-ports-7001/7003-only(mw.py:299) cap_trace=none(conductor.py:289-290) env_count=4 PI_WORKER_* + 4 supporting
