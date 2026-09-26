# Research: 单 key 内 worker 派发的串行化点与 worker 层并发实测（RQ-5 / msc-rq5-worker-serialization）

> 卡：`msc-rq5-worker-serialization`（key `mw-autopilot-slot-capacity`，spec 期，**只读角色**）
> 唯一写面：本文件（另加本人 worker 目录 `output.md`）。未改代码、未改任何 `_workers.parallel`、未 commit。
> 行号快照：2026-09-26 工作树（`conductor.py` 174500 B / `dispatch.py` / `launcher.py` 47583 B / `mw_common.py` 144421 B / TS `agent-team-loop/**`）。
> 所有时间戳按 UTC（`trace.log` 用 `...Z`，`_workers.parallel` 用 `...+00:00`；本地 = UTC+8）。实测数字均给出复算方式（§方法与出处 4）。

## 决策问题

支撑 `spec.md` §1.1.1 的 **(d)**「`slots 2/2` 但实际在跑的 worker 很少」、draft **AC-005**、以及 **U-4′**（worker 层串行化是否可解）：

1. **派发通路全链**：一张卡从「被决定要跑」到「pi 进程起来」经过哪些环节（谁写 `_workers.parallel`、谁消费、一 poll 取几行、是否并发 spawn、写行与 spawn 之间的门禁）。
2. **单 key 内是否天然一次只跑 1 个 worker**；必须区分 **A. 硬顺序** 与 **B. 可实现但当前策略保守**。
3. **实测 worker 层同时并发数**：PM 手工派发路径（`mw-autopilot-verify-cli`）与 autopilot/conductor 路径（MW/FM/E2 的 `_autopilot/` + `workers/*/trace.log`）两侧的重叠区间统计。
4. **串行化点清单表**（点 / 位置 / 触发条件 / 硬顺序还是可并行 / 若要放开需要改什么）。
5. **风险前置**：单 key 内并发从 1 提到 N 会不会同 key 文件冲突；同 key 内两个 worker 的写面重叠**有没有机器判定**。

## 调研方法与出处

1. 读过的文件（read 工具，全读或标注行段）：`autopilot/dispatch.py`（整文件）、`autopilot/conductor.py`：183-302 / 900-1120 / 1573-1782 / 2050-2160 / 2875-3075 / 4021-4060、`launcher.py`：45-92 / 186-250 / 462-517 / 512-627 / 775-990、`mw_common.py`：1432-1560 / 1655-1695 / 1829-1852 / 1932-1952、`coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：1102-1392 / 1545-1665、`pm/pm-orchestrator.ts`：393-508 / 519-589 / 660-770、`pm/task-dispatcher.ts`：237-300、`shared/worker-store.ts`：1-90、`shared/phase-docs.ts`（整文件）、`shared/implementation-gate.ts`：665-760、`worker/read-scope.ts`：1-60、`worker/worker-mode.ts`：615-705 / 750-850 / 1070-1100。
2. grep 模式：`update_status|_write_workers_file|archive_stale`、`write_scope|writeScope|写面|overlap|conflict`（范围内零命中即缺口证据）、`dispatch.dispatch(`、`readScope|READ_TOOLS`、`workers_path|_workers\.parallel`。
3. 只读现场数据：
   - `.mw/` 运行痕迹：`H:\git\Multi-Workers\.agenticdoc\_workers.parallel`、`H:\git\E2Feature\.agenticdoc\_workers.parallel` + `.mw/{mw.log,launcher.log,launcher-beat.*}`、`H:\git\E2Feature\.agenticdoc\_autopilot\{timeline.jsonl,config.json,...}`。
   - 全部 `trace.log`：MW 166 个 session、E2Feature 485、JCodingAss 70、LearningTree 0。
4. **复算脚本（本次实测的唯一计算方式）**：脚本落在系统临时目录 `%TEMP%\rq5\*.py`（不在仓库内），核心逻辑如下（可直接复制重跑）：

```python
import re, pathlib, datetime, collections
TSP = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))'
START = re.compile(r'\[START\]\s+' + TSP + r'\s+task=')
END   = re.compile(r'\[END\]\s+' + TSP)
ANY   = re.compile(TSP)

def ts(tok):                      # 'Z' / '+00:00' -> aware datetime
    s = tok.strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    if re.search(r"[+-]\d{4}$", s): s = s[:-2] + ":" + s[-2:]
    return datetime.datetime.fromisoformat(s)

def sessions(root):               # key -> (start, end) per worker
    out = []
    for p in pathlib.Path(root).glob(".agenticdoc/*/workers/*/trace.log"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        m = START.search(txt)
        if not m: continue
        e = END.search(txt)                       # 注意：[END] 可能与上一行粘连，必须全文 re.search
        out.append((p.parents[2].name, p.parent.name, ts(m.group(1)),
                    ts(e.group(1)) if e else ts(ANY.findall(txt)[-1])))
    return out

def sweep(iv):                    # 扫描线：峰值 + 各并发档位累计墙钟
    ev = []
    for s, e in iv: ev += [(s, 1), (e, -1)]
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = peak = 0; prev = None; area = collections.Counter()
    for t, d in ev:
        if prev is not None and cur > 0: area[cur] += (t - prev).total_seconds()
        cur += d; peak = max(peak, cur); prev = t
    return peak, area
```

坑（都实际踩过，供 RQ-3 复用）：(a) `[END]` 经常与上一条 `[TOOL]` 粘在同一行（trace.log 的写入不保证行尾换行刷新），用 `^\[END\]` 锚定会漏；(b) 6 个 `design-rqd*` session 的 `[START]` 完全同秒，`<=` 判定会误加 1；(c) 没有 `[END]` 的 6 个 MW session 用最后一条时间戳兜底（`LearningTree` 全无 trace.log）。

## 发现

### F1 派发通路全链（Q1）

**A. 谁写 `_workers.parallel` 的行（5 个 writer）**

| # | writer | 入口函数 | 行写入点 | 说明 |
|---|--------|----------|----------|------|
| W1 | conductor 类型化派发（autopilot 唯一队列写者） | `dispatch.dispatch()` `autopilot/dispatch.py:409` | task.md 先写 `:528`；行在 `.mw/workers.lock` 内 upsert `:534-570`；读回校验 `:582-593` | 事务顺序 task.md → 行（D-102：崩在中间只会留「有 task.md 无行」的孤儿形状，由 W2 修复）；行状态恒为 `pending`，`dispatched_at` = conductors 的 `iso_now()` |
| W2 | conductor 孤儿回插 | `conductor.reconcile_orphans()` `conductor.py:4021` | 直接 `open("a")` 追加 `conductor.py:4038-4052` | 锁是 `.mw/conductor-workers.lock`（`lock_file(root,"workers")` `conductor.py:116-118`）——**与 W1/W3 不是同一把锁**（见 F4 #11） |
| W3 | launcher 状态转移 | `mw_common.update_status()` `mw_common.py:1512` | 锁 `.mw/workers.lock` `:1514-1524` | 调用点：`launcher.py:801`（reap 终态）、`:833`（task_path 非法→failed）、`:975`（spawn 成功→running）、`:981`（spawn 抛错→failed）、`:601`（orphan 判终态） |
| W4 | launcher 陈旧行归档 | `mw_common.archive_stale_entries()` `mw_common.py:1529` ← `launcher.py:788` | 重写文件、删除行 `:1550-1559` | 只删「非终态且 task.md 不存在」的行 |
| W5 | TS/PM 派发 | `WorkerStore.upsert()` `shared/worker-store.ts:67` ← `dispatchTask()` `pm/task-dispatcher.ts:284` | 锁 `.mw/workers.lock` `:68`；tmp+rename `:79-80` | 行状态恒为 `pending`；`dispatched_at` = `new Date().toISOString()` |

**W5 的三条触发入口（PM 通道的完整上游）**
- `dispatch_worker` 工具：注册 `pm/ui-bridge.ts:1113`；门禁顺序 = RAG 配置 `:1177` → owner key 解析 `:1181` → cli/type 校验 `:1186-1200` → **docs gate** `:1205-1219` → 同名 taskDir 去重 `:1222-1232` → model 校验 `:1239` → 写 task.md `:1255` → `dispatchTask` `:1257`。**全程没有任何「该 key 已有几个在飞」的判定**。
- `/worker` 命令：注册 `pm/ui-bridge.ts:1555`；task_key 由时间戳生成 `manual-<Date.now()>` `:1611`；docs gate `:1616`；`dispatchTask` `:1645`。
- 后台扫描（PM 窗口 `agent_settled` 事件，`:738`）：`dispatchNewTasks()` `pm/pm-orchestrator.ts:393` → 跳过 `origin: conductor`（`:435`，`isConductorTask` `:375`）→ docs gate `:446` → **对该 key 的每张未入队 task.md 依次 `dispatchTask`（`:464` 循环，无计数）**。另有 `startWorkerPollLoop`（`:519`，`POLL_INTERVAL_MS = 4000` `:48`）负责读取与通知，不派发。

**B. 谁消费这些行**
- **唯一 spawn 消费者**：`launcher._poll_once()` `launcher.py:775`（主循环 `run()` `:844`，`while True: _poll_once(...); time.sleep(poll_interval)`，默认 `DEFAULT_POLL_INTERVAL = 5s` `:49`/`:880`）。一轮顺序：beat `:781` → archive `:788` → reap `:796-801`（reap 后立刻补一个 `pending_queue` 项 `:809-812`）→ orphan reconcile `:816` → **discover `:819-825`：遍历文件全部行，凡 `status == "pending"` 且不在本进程 `running_procs` 就继续往下** → `_validate_task_path` `:829` → `max_workers` 判定 `:837` → `_spawn` `:841`。
- **一个 poll 取几行**：**不取 N，全部取**。`:820` 是 `for entry in entries:`，没有 head/batch/limit；**不按 key 分组**（`entry` 只按文件出现顺序处理）。
- **是否并发 spawn**：**是**。`_spawn` 内 `subprocess.Popen` `:966` 非阻塞，随后 `running_procs[key] = proc` `:967` 立即返回，功能上是「一个 poll 里把当轮所有 pending 行全部拉起」；`--max-workers`（`launcher.py:1021`，默认 `None`）是唯一的 opt-in 上限，超限才进 `pending_queue` 内存排队（`:837-840`），且该参数**不落盘**（`/mw restart` 不走它，`shared/mw-runner.ts:124-135` 只带 `--project`）。
- 其他行读者（只读，不 spawn）：conductor 每 tick `mw_common.parse_workers_file`（`conductor.py:200`）、monitor `monitor.ts:509-522`、`mw doctor`/`mw status`（`mw.py:1802-1811`）。

**C. 写行 → spawn 之间的门禁（按实际执行顺序）**

| 门禁 | 位置 | 触发条件 | 失败语义 |
|------|------|----------|----------|
| 位置契约 | `_validate_task_path()` `launcher.py:388`，调用 `:829` | task.md 不在 `<owner>/workers/<task>/` 形状内 | 行置 `failed`（`:833`），不 spawn |
| worker 层全局上限 | `launcher.py:837` | 仅当 `--max-workers` 显式给了才生效（默认 None） | 进内存队列（不丢弃） |
| target 配置 fail-closed | `_worker_target_config()` `launcher.py:883` ← `_spawn:920` | target.yml 形状不可用 | 抛错 → 行置 `failed`（`:981`） |
| profile 撕票检查 | `_check_config_tear()` `launcher.py:697`，调用 `:928` | task.md 内 profile 指纹 ≠ 当前 target.yml | 同上 |
| RAG 撕票检查 | `check_rag_tear()` `launcher.py:745`，调用 `:929` | rag fingerprint 失配 | 同上 |
| model 解析 | `_resolve_entry_model()` `:115` / `_effective_entry()` `:186`，调用 `:930-931` | 非法 model 前缀 / cli 不匹配 | 同上 |
| **凭证检查（spawn 前最后一道）** | `_build_env()` `:223`，调用 `:936` | 该路由的 credential 解析不出（`mw_common.resolve_credential`） | 抛错 → 行置 `failed`，**每任务隔离，不影响其他 worker** |
| 命令装配 | `_build_command()` `:462`（`--tools` 白名单在 worker 侧按 task type 施加，`worker-mode.ts:52-93`） | provider/model 组合非法 | 同上 |

**关键点：docs gate / 相位门禁 / deps / deny_globs 注入都不在「写行→spawn」之间，而在写行之前。**
- **docs gate（相位分档）**：只在 PM 通道（`ui-bridge.ts:1205`、`pm-orchestrator.ts:446`，实现 `shared/phase-docs.ts:159` → `phaseDocGaps` `:119`，档位由 `gateTierOf` `:110` 从 key 的 `- Phase:` 推）。conductor 通道**完全不读 docs gate**——它自己就是相位机。
- **deps 边**：`_deps_satisfied()` `conductor.py:2153`，调用 `:285`，在写行之前。
- **相位门禁 / 卡片选择**：`_stage_activation()` `conductor.py:217`/`:434`（stage 必须 running）+ `_phase_artifact_present()` `:933`/`:1964`（决定派 phase-writer 还是 L1/L2 裁决），在写行之前。
- **`round_budget`**：`cfg["round_budget"]`（`config.py:53`，默认 2）在 `execute_loop:1086`、`_advance_key:964`、`_verify_loop:1604/:1620` 处判定；限制**同一 loop 的总尝试数**，不是并发数。
- **deny_globs / read_scope 注入**：`_resolve_deny_globs()` + `render_task_md()`（`dispatch.py:369-375`/`:253-331`）在写 task.md 之前完成；PM 侧等价物是 `injectWorkspaceProfile()`（`task-dispatcher.ts:237`，在 `dispatchTask:288` 里、`upsert:295` 之前改写 task.md）。**spawn 时只剩撕票检查**（`:928-929`）。
- **凭证检查**：见上表最后一行——在 spawn 前，且 per-task 隔离。

### F2 单 key 内并发 = 1 是**硬顺序（A）**，只有两个逃逸口（Q2）

**判定：A. 硬顺序。** conductor 通道对「同一 key 同时只允许 1 个在飞 worker」有**三重结构性保证**，不是靠相位/预算/依赖这些"可能配置出来的"门禁：

1. `in_flight_keys` 定义（`conductor.py:258-264`）= 「该 key 名下存在任意非终态行」；`_is_in_flight` = `status not in {"done","failed","needs-clarification"}`（`:2131-2132`），`_row_belongs_to` = `task_key.startswith("ap-{key}-")` 或 task_path 落在 `.agenticdoc/{key}/workers/`（`:2135-2138`）。**`pending` 也算在飞**。
2. 派发循环里 `if key in in_flight_keys: continue  # wait for the in-flight worker`（`conductor.py:287-288`）——该 key 只要有 1 个非终态行，本轮直接跳过。
3. `_advance_key()`（`:908-1015`）的**每一个**分支都只派 1 个 worker 后立刻 `return`（phase-writer `:936-941`、L2 fix-writer `:974-979`、L2 verifier `:1006-1011`、execute `:1111`）；loop 层再各自加一次确认：`execute_loop` 的 `return False  # per-key serial: wait for the in-flight task`（`:1096`，docstring `:1075` 明写 `per-key serial (one in-flight exec task)`）、`_verify_loop` 的 `for prefix in (f"ap-{key}-l3-", f"ap-{key}-repair-"): if any(_is_in_flight(r) ...): return False`（`:1600-1601`）与 repair family 判定（`:1729-1735`）。

三重保证里 **#1+#2 就是「硬」的证据**：即使把 `max_parallel_keys` 调到 100、把 `deps`/相位/budget 全部放开，只要该 key 有 1 个非终态行，`_advance_key` 就不会被调用。**"每 key 1 个"不是策略保守，而是队列表驱动的互斥。**

**两个逃逸口（都是【事实】，且都在真实运行里发生过）：**

- **E1：PM 通道完全不受该互斥约束。** `dispatch_worker` 只查 taskDir 是否已存在（`ui-bridge.ts:1222-1232`），**不查该 key 有几个在飞**；`dispatchNewTasks` 的后台扫描对某 key 的**所有**未入队 task.md 逐个 upsert（`pm-orchestrator.ts:464` 的 `for` 循环，无计数、无预算）。⇒ 同一 key 一次 settle 可以入队 N 张卡。
- **E2：行被提前终态化 → 允许让旧 worker 还在跑时就派重试。** 硬互斥的判据是**行状态**，不是**进程存活**。实测 2 个样本（同一形态，都是前驱行终态 = `failed`、后继是 `-aN` 重试）：
  - `feature-gui-time-mvp-board`：`ap-...-repair-a3-a3` 行 `updated_at = 02:59:24Z`（终态 `failed`），`-a4` 在 `02:59:25Z` 派发，而 a3 进程的 `[END]` 在 `03:01:00Z` ⇒ **同 key、同 repair family 的 2 个 pi 进程重叠 89.2s**（`a3` 02:20:30→03:01:00，`a4` 02:59:31→03:14:15）。
  - `feature-params-service`：`ap-...-002-...-probe` 行 `updated_at = 09:01:16Z`（`failed`），`-a2` 于 `09:01:18Z` 派发，前驱 `[END]` 在 `09:01:29Z` ⇒ 重叠 6.4s。
  - 该 key 的 a3 目录里 `worker.log` **没有** `[launcher] reconcile ...` 行（`_record_reconcile` `launcher.py:72` 的落点），故「launcher 的 orphan 静默/输出存在规则」无法解释这次翻转（且 `output.md` 当时不存在、`[END]` 当时不存在、silence 规则需要 90min 而 a3 的 trace.log 每 30s 就有 `[HEARTBEAT]`）；**具体是哪个 writer 在 02:59:24Z 把该行置为 `failed`，本卡无法从现有产物判定**（见数据缺口 1）。无论 writer 是谁，结论不变：**该互斥的判据是行状态，任何提前终态化都会打开同 key 并发窗口**。
- **E3（旁路通道，默认关闭）**：`xkey_repair=true` 时 `_xkey_proposal_stage()`（`conductor.py:2875`）在计算 `in_flight_keys` **之前**执行（`:243-254` 顺序），对每个 `approved && 无 proposal.md` 的 ticket 各派 1 个（`_xkey_proposal_one` `:2983`，`dispatch` `:3031`），只受 `_XKEY_PROPOSAL_MAX_ATTEMPTS = 2`（`:2872`）与 ticket 条数约束 ⇒ 同一 tick 可派 N 个，既越过 key cap 也越过每 key 1（有独立的 stem-family in-flight 判定 `:3010`）。E2Feature 的 `config.json` 无 `xkey_repair` 键 ⇒ 默认 `false`，本卡样本未触发。

### F3 实测：worker 层同时并发数（Q3）

> 全部数字 = `trace.log` 的 `[START]`/`[END]` 区间扫描（§方法与出处 4）。「peak」= 同时活跃 session 数；「overlap_wall」= 并发档位 ≥2 的累计墙钟；「dist」= 各档位累计秒数。

**来源 1：PM 手工/队列派发路径（MW 项目，`.agenticdoc/*/workers/*/trace.log`，166 session）**

| 分组 | n | 峰值 | overlap_wall / 全程跨度 | dist（并发档位:秒） |
|------|---|------|--------------------------|----------------------|
| `mw-autopilot-verify-cli`（整 key） | 26 | **6** @06:19:31Z | 2488s / 3965s | 1:985.8, 2:575.7, 3:848.6, 4:632.5, 5:124.9, 6:306.3 |
| 同上，PM 记忆的 4 人组（t06/t01b/t02c/t08） | 4 | **4**，全员重叠 06:48:17.343Z→06:50:02.866Z = **105.5s** | — | 两两重叠：t06×t08 634.5s、t06×t01b 415.7s、t01b×t08 340.5s、其余对 105.5s |
| 整个 MW 项目 non-`ap-`（PM 通道） | 166 | **6** | — | 1:54570, 2:5607, 3:4464, 4:3239, 5:496, 6:358 |
| `mw-autopilot-slot-capacity`（本 key，进行中，PM 一次批量派 6-7 张） | 7 | **6** @07:35:02Z | 466s / 466s | 2:1.3, 3:2.4, 4:361.8, 5:48.2, 6:51.9 |

⇒ PM 记忆的「最强点 4」**复算成立且偏保守**：t06/t01b/t02c/t08 确实有 **105.5s 四人同时在跑**；而该 key 执行期内 PM 的真实峰值是 **6**（`design-rqd1..6` 在 06:19:31.070-143 同一批拉起，6 个 session 全程重叠 306.3s）。

**来源 2：autopilot/conductor 路径（E2 / FeatureMigrator，`.agenticdoc/_autopilot/` + `ap-*` session，431 个）**
- **单 key 内峰值 = 1**，无一例外；**唯二**出现 2 的都是 E2 逃逸口（F2-E2）的重试重叠：`feature-gui-time-mvp-board` 89.2s、`feature-params-service` 6.4s。
- **项目级（所有 key 合计）**：峰值 **4**，dist = 1:62720s / 2:105973s / 3:449s / 4:150s（总跨度 100.0h）。
- `2026-09-25T03:40:13Z` 那次峰值 4 的成分（可复算）：
  | key | task | origin | 区间 |
  |-----|------|--------|------|
  | feature-gui-time-mvp-board | `ap-...-005-services-mvp-ledger` | `conductor` | 03:37:43→03:43:47 |
  | feature-l3-verdict-source-fallback | `ap-...-plan-writer-a1` | `conductor` | 03:31:32→03:43:14 |
  | feature-cigate-install-kit | `ap-...-repair-a3-achieved-terminal` | **无 origin 行（PM 手工 `dispatch_worker` 写的 task.md）** | 03:40:13→03:42:43 |
  | feature-sampling-human-channel | `ap-...-repair-a2-achieved-terminal` | **同上** | 03:40:08→03:42:57 |
  ⇒ cap=2（`E2Feature/.agenticdoc/_autopilot/config.json: "max_parallel_keys": 2`）只约束了 conductor 的 2 个 key；PM 手工派发另开 2 个，**合计 4**。附带一个反例：PM 手工派发把 task_key 起成 `ap-{key}-...` 形式，因此这些行**会被 conductor 计入 `in_flight_keys`**（`_row_belongs_to` 前缀匹配 `conductor.py:2136`）——即「PM 手工派发占用 conductor 槽位但不受其限制」。
- **跨项目对照（同一份口径）**：`E2Feature` 的 non-`ap-`（PM 手工）54 个 session，项目级峰值 **3**（dist 1:32753, 2:2288, 3:397）；`JCodingAss` 70 个 session 全是手动/无 `ap-`（autopilot 卡在 gate-0001，timeline 2362 行里只有 1 个 `gate-created`、0 个 `dispatch`）；MW 项目 `ap-` session **0 个**（无 `_roadmap.md`，autopilot 未启用）。⇒ **autopilot 路径的真实样本只有 E2Feature 一个项目（431 session / 100h）**。

**同一项目（E2Feature）两侧对比（AC-005 要求的形态）**：
| 侧 | 单 key 峰值 | 项目级峰值 | 样本 |
|----|-------------|------------|------|
| autopilot/conductor（`ap-*`） | **1**（硬顺序；2 次重试重叠例外） | **2**（= `max_parallel_keys`，另有 150s 的 4） | 431 session / 100h |
| PM 手工派发（non-`ap-`） | 无上限（实测 3） | **3** | 54 session |

⇒ **瓶颈在 conductor 侧，不在 worker 层容量**：worker 层（launcher 消费）默认没有上限（F1-B），PM 通道实测能稳定拿到 3-6；autopilot 路径同时 worker 数 ≈ key 槽位数（因为每 key 恒为 1），而 key 槽位默认 2。`slots 2/2` 与实际 worker 数不一致的根因不是"worker 层有个隐藏上限"，而是**另外两条通道在同时跑**（PM 手工派发不写入 `slotsUsed`，见 RQ-1）。

### F4 串行化点清单表（Q4）

| # | 点 | 位置 file:line | 触发条件 | 硬顺序 / 可并行 | 若要放开需要改什么 |
|---|----|----------------|----------|------------------|--------------------|
| 1 | **每 key in-flight 互斥** | `conductor.py:258-264`（定义）+ `:287-288`（判定）+ `:2131-2138` | 该 key 名下存在任一非终态行（含 `pending`） | **硬顺序** | 把布尔判定换成 per-key 计数 + 每张卡的身份判定（`ap-{key}-{stem}`），并定义"同 key 可并行的单位"（tasks/*.md？phase-writer？） |
| 2 | **key 层槽位上限** | `conductor.py:289-290`；值 `config.py:52`（默认 2，`_INT_RANGES` `:70` floor 2，**不可机器层覆盖**，`effective_config.py:62-65`） | `len(in_flight_keys) >= max_parallel_keys` | 硬顺序（值可配） | 只改 `config.json` 的值即可（不改代码）；但收益上限 = 每 key 1 × cap |
| 3 | **`_advance_key` 每 tick 每 key 只派 1 个** | `conductor.py:291-292` + `:908-1015`（每分支 `return`） | 每次调用最多 1 次 `dispatch` | **硬顺序** | 需「每 key 本轮可选多张卡」的循环 + 每张卡独立的 in-flight 判定；风险集中在 #1 |
| 4 | **key 间依赖边** | `conductor.py:285` → `_deps_satisfied` `:2153` | `depends_on` 未满足 | 硬顺序（仅 key 间） | 与本目标无关（不 gate key 内） |
| 5 | **阶段/相位门禁（决定派哪张卡）** | `_stage_activation` `conductor.py:217`/`:434`；`_phase_artifact_present` `:933`/`:1964`；`_missing_plan_tasks` `:1990` | stage 非 running；相位产物缺失；plan 引用的 task 文件缺失 | 硬顺序（决定卡的类型/先后，不决定并发） | 不放开；但它是「同 key 每 tick 只有 1 张卡可派」的来源之一 |
| 6 | **round_budget / L3 budget / repair budget** | `config.py:53`（默认 2）；判定 `conductor.py:964`(L2)、`:1086`(execute)、`:1604`(L3)、`:1620`(repair)、`:1735` | 同一 loop 的尝试数用尽 → `mark_stalled` | 策略型（数量预算，非并发） | 不放开；但它是"key 卡死后继续占槽"的放大器（配合 RQ-6 的槽位释放） |
| 7 | **docs gate（相位分档）** | `ui-bridge.ts:1205`（工具）、`:1616`（`/worker`）、`pm-orchestrator.ts:446`（后台扫描）；实现 `phase-docs.ts:159`/`:119`/`:110` | key 缺 spec/design/证据/AC 等（design 档 6 项） | 硬门禁（**仅 PM 通道**，conductor 不读） | 不放开；它按 key 整体阻断，不按卡 |
| 8 | **launcher 消费方式** | `launcher.py:819-825`（全部 pending、文件序、不按 key 分组）+ `:837`（`--max-workers`，默认 None）+ `:841`/`:966`（非阻塞 Popen） | 每个 poll（默认 5s） | **可并行（已是最放开的一层）** | 无；若将来要 per-key worker cap，这里是唯一合适的落点（同时需要落盘：`--max-workers` 现在不落盘，P-015） |
| 9 | （对照）**PM 手工通道没有并发门禁** | `ui-bridge.ts:1222`/`:1257`、`pm-orchestrator.ts:464` | 无 | 完全可并行 | 若要收口（避免 4-6 并发挤同一批文件）需在此加判定 |
| 10 | 行写互斥锁（跨语言同一把） | `dispatch.py:547`（`.mw/workers.lock`）+ `worker-store.ts:68`（同路径） | 每次行写 | 串行（毫秒级） | — |
| 11 | **孤儿回插的锁与 #10 不是同一把（缺口）** | `conductor.py:4032` 用 `.mw/conductor-workers.lock`（`lock_file(root,"workers")` `:116-118`）vs `mw_common.lock_path` = `.mw/workers.lock`（`mw_common.py:1440`） | `reconcile_orphans` 时 | 应为串行，实际不互斥 | 改用同一把锁，否则 `open("a")` 追加可能与 launcher/TS 的 RMW 互相丢更新（GC-3 相关） |

**计数**：真正 gate「worker 层并发」的点 = #1、#2、#3、#5、#6、#7、#11 = **7 个**；#8/#9 是两条**不设限**的消费/派发通路。

### F5 同 key 写面风险（Q5）

**【事实】任务书里确实有写面纪律，但只是散文，且覆盖率很低。**
- `tasks/*.md` 中的 `- 写面：...` 行只在 **11/248** 个任务书里出现：`mw-autopilot-verify-cli` 10 个（T-01/T-03/T-04/T-05/T-06/T-07/T-08/T-09/T-10 + T-02 的并行声明）、`mw-dual-workspace` 1 个。复算：`python -c "import pathlib; ...; '写面' in text"`。
- 典型形状（`.agenticdoc/mw-autopilot-verify-cli/tasks/T-06-conductor-root-anchor.md` 第 3 行）：`- 写面：\`packages/multi-workers/autopilot/conductor.py\`、\`packages/multi-workers/autopilot/dispatch.py\` + **新建** \`test_autopilot_xkey_cwd.py\``；T-02 明写「与 T-03/T-04 并行，但 T-01 的…写面不重叠」⇒ **verify-cli 的 4-6 并发之所以没炸，是人在写任务书时按文件边界切好的，不是机器保证的。**
- conductor 的 exec 提示词也只把纪律写进自然语言：`只碰任务书列出的文件`（`conductor.py:1058`）。

**【事实】没有任何机器判定同 key 内两个 worker 的写面重叠。**
- 全仓 grep `写面|write_scope|writeScope|write-surface|allowGlobs` 在 `packages/multi-workers/**` 与 `packages/coding-agent/src/extensions/agent-team-loop/**` 的生产代码里 **零命中**（仅 `config-selector.ts` 的无关 `writeScope`、`worker-mode.ts` 的写计数 `writes`）。
- 现有的 containment 只覆盖**读**：`read_scope` 拦截 `read/ls/find/grep`（`worker-mode.ts:756-787` 的 tool_call 拦截 + `read-scope.ts:4` 的契约），`deny_globs` 也在同一拦截器内（`read-scope.ts:141-186`）；`write`/`edit`/`bash` **不受** `read_scope`/`deny_globs` 约束。
- `implementation-gate`（`implementation-gate.ts:686 gateDecision`）对任何 worker 直接放行：`env[PI_WORKER_TASK]` 非空 → `basis: "worker-env"`（`:716-718`），即**worker 的写操作不受 key claim 门禁约束**，更不会检查另一 worker 的写面。
- 唯一存在的"冲突"机制与本问题无关：`mw.py:2671 _partition_env_conflict`（env 名）与 `.tmp/agentic-task/scripts/migrate_patterns.py`（文件迁移重名）。

**【推断】风险量化与结论。**
- autopilot 路径当前每 key 1 个 worker ⇒ **同 key 内不可能并发写**（F2），所以"提高单 key 并发"是**净新增**的写冲突面，不是已有风险的放大。
- 但 PM 通道**已经**在同 key 放开到 4-6（F3），这些运行的写面互斥**完全依赖人工纪律**；`mw-autopilot-slot-capacity` 当前 6-7 并发同 key 亦如此（6 张 research 卡各自写自己的 `evidence/research/spec-*.md`，是任务书规定的唯一写面）。
- ⇒ **要把单 key 并发从 1 提到 N，必须先补"写面声明 → 机器可读 → 重叠拒绝"这条链**；否则违反复现的是 P-018/P-019 家族（同文件多写者 / 冻结判据被覆盖）。最小机器判据候选：把任务书的 `- 写面：` 行升级为 task.md 的一个 frontmatter 列表（如 `writes:`，与既有 `read_scope:` 同形），在 `dispatch.dispatch`（`dispatch.py:409`）与 `dispatchTask`（`task-dispatcher.ts:284`）里对同 key 的在飞行做集合交集判定——**当前两个派发入口都没有这类检查**（缺口）。

## 结论 → 决策映射

**逐条对应 draft AC-005：**
1. 「单 key 内 worker 派发的串行化点清单（每点：函数 file:line + 触发条件 + 硬顺序 / 可并行）」→ **F4 表（11 行，其中 7 行 gate 并发）**。
2. 「用同一项目的两组真实运行做对比（autopilot/conductor vs PM 手工派发）的同时 worker 数，证明瓶颈位于哪一侧」→ **F3 的 E2Feature 同项目对比表**：autopilot 单 key 峰值 1 / 项目峰值 2，PM 手工派发项目峰值 3（MW 项目 PM 通道峰值 6）。**瓶颈位于 conductor 侧**（每 key 1 × key cap 2 的乘积），**不在 worker 层**——worker 层（launcher）默认无上限、单 poll 全量并发 spawn。
3. 「实测数字可由文件内容复算」→ §方法与出处 4 的脚本 + 每条数字标注的 `trace.log` 区间。

**回答 U-4′（worker 层串行化是否可解）：可解，且不需要改 worker 层机制。**
- 「每 key 1 个 worker」不是机器容量或 launcher 的限制（launcher 默认无上限、非阻塞 Popen、单 poll 全量），而是 conductor 的一条**结构性硬顺序**（F2 的三重保证）。
- 因此可解路径是把并发来源从「key 槽位 × 1」换成「key 槽位 × 同 key 可并行卡数」，需要三件事同时具备：(a) `conductor.py:287-288` 的布尔判定改为 per-key 计数 + 卡身份判定（并对 `execute_loop:1096`、`_verify_loop:1600`、`:1729` 三处 family 判定同步放宽）；(b) 同 key 写面判定（F5 的缺口，建议复用 `writes:` frontmatter）；(c) 收敛判据 = autopilot 路径 per-key 峰值从 1 变 N 的**实测**（当前唯一实测的 per-key 重叠是两处重试逃逸 89.2s/6.4s，说明这条 1 是稳定约束而非偶然）。
- 替代路径（不改 conductor）：提高 `max_parallel_keys`（收益 = cap，成本 = PM 注意力/机器负载），或继续走 PM 手工派发（已经能拿到 3-6，但不受 docs gate 之外的任何并发/写面控制，且不占 `slotsUsed` 显示）。
- **前置条件（不是可选项）**：F2-E2 的「行提前终态化 → 同 key 重试与旧进程重叠」是**已经在生产发生的同 key 并发**（2 个样本），它同时说明：(i) 现有互斥的判据是行状态而非进程存活，提高并发前应先让它对"进程存活"敏感（或至少在派发时校验前驱进程已退出）；(ii) 否则新加的同 key 并发判定会建在同一个不可靠的地基上。

**对 (d) 的直接回答**：`slots 2/2` 而实际 worker 少，**不是 worker 层被串行化**，而是 autopilot 路径把"同时 worker 数"绑死在"key 槽位 × 每 key 1 个"上（默认 2）；同一时刻真实在跑的 worker 数由**三个互不知情的通道**叠加决定：conductor（每 key 1，上限 cap）、PM 手工派发（无上限）、xkey 提案（默认关闭，可一次 N 个）。面板只显示第一条通道的 key 计数。

**边界声明**：本卡只回答「串行化点在哪、可解性与前置条件」，不回答「N 该取几、代价多少」（属 RQ-4 改法候选与 U-3 成本问题），也不做槽位被 stalled key 占用/释放的量化（属 RQ-6）。key 层上限的完整清单与 `in_flight_keys` 的语义细节见 RQ-1（`spec-concurrency-anchors-20260926.md`），本卡与其一致、不重复，仅补三点：**(a)** 行写入共有 5 个 writer、其中孤儿回插用的锁与其余 writer 不同（F4 #11）；**(b)** `_verify_loop`/`execute_loop` 的 family 级 in-flight 判定是「每 key 1」的第二、三重保证（`conductor.py:1600-1601`、`:1096`）；**(c)** 「每 key 1」在真实运行里有 2 次被重试逃逸打破（89.2s / 6.4s）。

## 数据缺口

1. **`02:59:24Z` 把 `ap-feature-gui-time-mvp-board-repair-a3-a3` 行置为 `failed` 的 writer 无法判定。** 已排除：`[END]` 当时不存在（`parse_end_exit` `mw_common.py:1829` 只读 trace.log）、`output.md` 当时不存在（mtime 03:01:00、且只写过 1 次）、silence 规则需要 90min 而 trace.log 每 30s 有心跳、`worker.log` 无 `[launcher] reconcile`/`[LAUNCHER]` 行。剩余候选：launcher 重启（`E2Feature/.mw/mw.log` 显示 02:30:44Z 前后 serve 从 launcher 55896 换到 36348 再到 73496，a3 的 owner 已死）后的某条路径，或有仓库外的写入者。**可证伪的验证方法**：在临时项目里复现「launcher 重启 + 长跑 worker + 重试派发」，对 `.agenticdoc/_workers.parallel` 起 inotify/轮询审计（记录 status 与 updated_at 每次变化 + 写者 pid），或给 `mw_common.update_status` 加调用方标记后重放。
2. **autopilot 路径样本只有 1 个项目**（E2Feature，431 session/100h）。任务书提到的 FM 项目在磁盘上不存在（`H:\git\*` 下带 `.agenticdoc` 的只有 E2Feature / JCodingAss / LearningTree / Multi-Workers 与 `H:\git\.agenticdoc`；E2Feature 自述为「E2Feature：UE 5.5.1 fork 的 Feature 数据维护体系」，`FeatureMigrator` 只剩框架注释里的历史项目名）；JCodingAss 的 autopilot 卡在 gate（0 次派发），MW 的 autopilot 未启用（无 `_roadmap.md`、无 `config.json`）⇒ 「有/没有同 key 重叠」的结论对 autopilot 侧只有 2 个正样本（都是重试逃逸），**"没有"这一侧的样本量 = 429/431 key 恒为 1，可支持"硬顺序"判定，但不足以量化"若放开会出现多少重叠"**。
3. **当时 serve 的 env/argv 不可恢复**（`PI_WORKER_ORPHAN_DEAD_MIN`、`launcher --max-workers`、`PI_WORKER_IDLE_MS`），故无法判断逃逸口 #2 是否被某个更小的阈值触发。
4. **机器容量上限（CPU/RAM/句柄）未测量**，也不在本卡范围；F3 的"峰值 6 未失败"只是下界，不是安全上限。
5. **同 key 写面重叠无法量化**：没有机器可读的写面数据（F5），只能靠人工读任务书；因此在放开并发前无法用数据回答"冲突概率"。
6. **monitor 面板口径与 conductor 不一致**（`slotsUsed` 只数 `running`、非 `ap-` 前缀另计）导致 `slotsUsed > slotsMax` 可显示——该差异 RQ-1 已记录，本卡只确认它会让 (d) 的现象被**低估**（F3 的 4 并发里有 2 个不计入 owner key）。

## 机器行

[VERIFY] RQ-5: path=conductor.py:258-264,287-290(per-key-inflight+key-cap)->dispatch.py:409,528,534-570(task.md then row)->launcher.py:819-841,910-975(all-pending spawn) manual_overlap_max=6(mw-autopilot-verify-cli 2026-09-26T06:19:31Z rqd1..rqd6; quartet t06/t01b/t02c/t08 all-4=105.5s) autopilot_overlap_max=1(E2Feature 431 ap-* sessions; 2 retry-escapes 89.2s/6.4s) autopilot_project_max=4(2 conductor + 2 PM-manual ap-named, 2026-09-25T03:40:13Z) serialization_points=7(gating: per-key-inflight/key-cap/one-dispatch-per-call/phase-gate/budget/docs-gate/reconcile-lock-mismatch)+2(ungated: launcher-consume, pm-manual-channel) row_writers=5 spawn_consumer=1(launcher.py:819) docs_gate=pm-only(ui-bridge.ts:1205,pm-orchestrator.ts:446) same_key_write_surface_check=none(write_scope grep=0)