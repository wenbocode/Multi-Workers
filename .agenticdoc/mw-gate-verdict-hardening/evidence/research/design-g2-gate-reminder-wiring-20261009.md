# Research: G2 pending-gate 提醒接线与可见面（design / DRQ-2）

> Key: mw-gate-verdict-hardening ｜ 角色: research worker（只读，DESIGN 阶段）｜ 快照: 2026-10-10
> HEAD: `10446aefb`（与 RQ-2 同基线；`packages/multi-workers/autopilot/**` 与 `packages/coding-agent/src/extensions/agent-team-loop/**` 本工作树无本 key 脏改动）
> 前置：`evidence/research/spec-pending-gate-alert-surfaces-20261009.md`（RQ-2 现状普查，F1–F7）——本任务**不重复**现状，只做实现接线与取舍
> 决策问题（DRQ-2）：G2「pending 超阈主动提醒 + 可见面」的**可落地方案**——谁判定、挂哪个 tick 点、计数载体、配置键、可见面改哪几行。
> 边界：只读调研；本文是本轮唯一写面，未改任何代码或其它文件。
> 三次执行（2026-10-10T02:59Z，mgh-drq2-reminder-wiring 第三次重跑）：全部 `file:line` 在 HEAD `10446aefb` 工作树上逐条 grep/read 复核（首轮 2026-10-09T~12:00Z 的锚点 22h 后全部仍成立；仅 2 处微调，见文末「复核」）；E2Feature 数值独立重测（tail200 由 195 beat/1294 s 变为 199 beat/1378 s，结论「尾窗 ≪ 60 min」不变）。DESIGN 已按本 note 落定 D-005..D-010，文末「给 DESIGN 的待决」已标注落定结果。

## 调研方法与出处

- 只读 read/grep：`packages/multi-workers/autopilot/{conductor,gates,config,effective_config,timeline}.py`、`packages/multi-workers/{mw_common,mw}.py`、`packages/coding-agent/src/extensions/agent-team-loop/{autopilot/{monitor,console,status-model,gate-writer}.ts, pm/{ui-bridge,pm-orchestrator}.ts}`、`packages/coding-agent/src/core/{extensions/types.ts,session-manager.ts}`。
- 只读实测（E2Feature 语料，只读，未写任何文件）：21 个 gate 文件、`timeline.jsonl` 尾窗、`_autopilot/config.json`、`auto-decisions.jsonl` 存在性；用本仓 `autopilot.gates/timeline` 模块直接调用（脚本落在系统 TEMP，运行后不在仓库留痕）。
- 只读对照测试：`test/extensions/agent-team-loop.test.ts`（poll 循环夹具）、`suite/autopilot-{monitor,console,gate-presentation,event-parity,status-parity}.test.ts`、`test_autopilot_{conductor,config,config_parity,effective_config,doctor_gates}.py`。
- 三次执行都未运行任何会写 E2Feature 的 `mw` 子命令（只用 import 的纯读函数 + gate 文件文本读取）。

---

## 发现

### F1 PM 推送通道的落地形状（DRQ-2.1，本 RQ 核心）

**F1.1 extension 侧唯一推送原语 = `deliverPmAlert`，且它本身零幂等。**

- 定义 `ui-bridge.ts:131` `export function deliverPmAlert(pi: ExtensionAPI, text: string): void`；函数体是 `pi.sendMessage({customType:"agent-team-loop:worker-summary", content, display:true, details}, { triggerTurn: true })`（`ui-bridge.ts:132-141`，`:139` 是 `triggerTurn: true`）。docstring `:125-130` 明确：无 `triggerTurn` 时**空闲 PM 不会被唤醒**。
- `deliverWorkerResult`（`ui-bridge.ts:145`）就是 `deliverPmAlert` 的别名（`:146`）。全仓对该原语的引用：定义 `ui-bridge.ts:131`、别名体 `:146`、唯一外部调用 `pm-orchestrator.ts:584`（发散升级，import 在 `pm-orchestrator.ts:23`）；`deliverWorkerResult` 另有 2 处调用 `pm-orchestrator.ts:611/:618`（终态回读）。
- **`deliverPmAlert` 不做任何去重**：同一文本调用 N 次 = N 条消息 + N 个 PM turn。≤2 与"不刷屏"**必须由调用方**（tick 判定 + 计数载体 + 消费侧 Set）保证。

**F1.2 poll 循环体就是要新增的 gate 消费者位置，它现在完全不读 gate。**

- `pm-orchestrator.ts:519` `export function startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui, pollIntervalMs = POLL_INTERVAL_MS)`；`POLL_INTERVAL_MS = 4000`（`pm-orchestrator.ts:48`）。
- 循环体 `setInterval(...)` `:543`；每 tick 只做三件事：watch widget、`const entries = workerStore.readAll()`（`:558`）、running 升级（`:571-586`）+ 终态回读（`:587-625`）。**全仓 `pm/` 目录对 `listGates|gatesDir` 命中 = 0**（gate 读取只在 `autopilot/{console,monitor,status-model}.ts`）。
- 该循环拿到的 `agenticdocRoot` = `<project>/.agenticdoc`（`shared/paths.ts:22 agenticdocRoot`），所以 `projectDir = path.dirname(agenticdocRoot)`，**不需要新参数**。
- 现成读取器：`status-model.ts:922` `export function listGates(projectDir: string): { gates: GateRecord[]; errors: string[] }`（`readdir` + 逐文件 `parseGateFile`，按 seq 排序；缺目录 = 空队列；坏文件进 `errors` 不进 `gates`）；`GateRecord.createdAt: string`（`status-model.ts:654`）、`status/kind/id`（`status-model.ts:646-650`）。timeline 读取器：`monitor.ts:396` `readTimelineTail(file, {maxBytes=512*1024, limit=400})`；`status-model.ts:1105` `queryTimeline(path, watermark, evFilter)`。

**F1.3 两条路对比（判定位置 + 消费位置）**

| 维度 | 路 A：extension 每 tick 读 gate 文件自行判定 | 路 B（推荐）：conductor 判定 → 写 timeline `gate-reminder` + 计数 ledger，extension 消费 |
|---|---|---|
| 判定源 | TS `listGates` + 自算年龄 + 自算三轴 | Python `tick` 一处判定（RQ-2 F7 三轴，`gates.pending_gates:728` 等） |
| 计数载体 | TS 侧无法安全持久化（见 F3）⇒ 仍要读 Python ledger，等于 A+B 两套判定 | Python 单写者 append（F3） |
| 跨语言口径 | TS 与 Python 各自判"超阈"，时钟/tick 相位/`running` 定义都可能背离（P-021） | 只有一条判据；TS 只做"读到提醒 → 推送"的搬运，无阈值判断 |
| 重复提醒风险 | 两个窗/两侧各推一次；extension 重启后 Set 丢 → 重复 | ledger 计数为唯一权威，重启不复活（F3） |
| 每 tick 成本（E2：21 门） | `listGates` 全量 readdir+read+parse 40 字段 × 1/4s（PM 窗口） | 读小 ledger（E2 为 0 行）；或读 timeline 尾窗 512KB（更贵） |
| GC-1 | 不新增常驻组件，但把"判定"复制到 TS | 不新增常驻组件；判定已在唯一每 tick 主干 |
| 失败模式 | TS 读不到 gate（半写/坏文件）→ 静默漏报或误报 | conductor 判定失败只影响自身 tick（`tick` 外层 `except` 已兜底，`conductor.py:2408-2410`） |

- 路 A 的**致命缺陷**不是成本而是"两个独立阈值判官"：AC-007 的 `running_rows==0` 在 Py/TS 两侧本来就是不同口径（F6），再叠加时钟漂移与 tick 相位，必然出现"一侧提醒、另一侧不提醒/重复提醒"。P-021（跨语言镜像陈旧断言）正是指这类。
- 路 B 的**已知代价**：extension 必须新增一个 ledger 读取；重启后尾窗重放需要消费侧去重（有现成机制，见 F1.4）。`deliverPmAlert` 的 `triggerTurn` 会花 PM turn，所以 B 的计数必须决定"第 2 次"的时机（F3.3）。

**F1.4 防刷屏的既有先例（可按强度复用）**

1. **进程内 `Set`（per window）**：`pm-orchestrator.ts:532` `const notified = new Set(...)`——用**窗口开启时的终态快照**播种，只报"本会话观察到的状态翻转"；`:540` `const escalated`（per taskKey，只在首个 mid/high checkpoint 升级一次，`:577 escalated.add(...)`）；`:738 docGateWarned`（per key）；`:758 evidenceReviewNotified`（per (key, phase)）。
2. **会话持久 watermark（跨 restart/resume 存活）**：`console.ts:75` `AUTOPILOT_SEEN_ENTRY_TYPE = "agent-team-loop:autopilot-seen"`；写 `console.ts:188` `pi.appendEntry(... {seq, ts})`、读 `console.ts:153-176` `ctx.sessionManager.getEntries()` 倒序找最后一条。**poll 循环可用**：`ui.ctx` 是 `ExtensionContext`，带 `sessionManager: ReadonlySessionManager`（`core/extensions/types.ts:317`），后者含 `getEntries`（`core/session-manager.ts:1301`，interface 声明 `:203`）；`pi.appendEntry` 在 `ExtensionAPI` 上（`core/extensions/types.ts:1312`），不依赖 ctx。⇒ 消费侧可用 session entry 记录"已投递 (gate_id, n)"，重启不重放。
3. **文件事实去重**：`_timeline_has_event`（`conductor.py:1817`，有界布尔，`tail_events(limit=200)`）、`_review_escalate`（`conductor.py:2901-2920`，detail 内嵌 `[gate_id]` 做 (key,trigger,gate) 去重，`:2916`/`:2917`）、`_defer_recorded` 家族（`conductor.py:6076`）。

**F1.5 推荐**：路 B，且 extension 的投递读取用 **ledger** 而非 timeline 全文——因为计数本来就要落 ledger（F3），event 只是 AC-005 要求的可见审计面。消费侧去重 = 进程内 `Set<(gate_id,n)>`（F1.4-1 形状）+ session entry（F1.4-2）跨重启（DESIGN D-010 已落定为 session entry 去重，见文末）。**不要**只在 extension 里判阈值（路 A）。

---

### F2 conductor 侧判定函数的形状（DRQ-2.2）

**F2.0 挂点：不能只挂 `orchestrate`——`goal-change` gate 会整段漏掉（本 RQ 最重要的实现结论）。**

- `orchestrate`（`conductor.py:204`）主干：`auto_decide_gates`（`:218`）→ `if not _consume_answered_gates(...): return`（`:222`）→ `reconcile_orphans`（`:227`）→ `rows = parse_workers_file(...)`（`:229`）→ 无 roadmap 直接 return（`:230-233`）→ roadmap 坏 return（`:236-239`）→ `_stage_activation` false 就 return（`:242-244`）→ … → 每个 running stage 里 `_process_deferred_reviews`（`:308`）→ `_stage_closure`（`:311`）。
- **但 `tick` 在到达 `orchestrate` 之前就会为 `goal-change` 早退**：`conductor.py:2330 def tick`；`:2336` beat；`:2339` `cfg = _load_effective_config(...)`；`:2340-2341` enabled/paused → `idle`；`:2343` `current = goal_mtime_ns(...)`；`:2346` `gate_open = open_goal_change_gate(...)`；`goal-change` 门建于点 `:2361-2384`（含 `_stamp_gate_defaults` + `snapshot_gate_created`）；**:2392-2395 `if gate_open or st.goal_halted: ... return "halted-goal-change"`**；`:2406` 才是 `orchestrate(...)`；`:2408-2410` 外层 `except`。
- 现成测试钉死该行为：`test_autopilot_conductor.py:122` / `:131-132` / `:134`——重复 tick 恒返回 `"halted-goal-change"`，永不二次建门；`:142-151` 重启/应答后的行为。⇒ 一个**未答的 goal-change 门会让 conductor 停在 orchestrate 之外**，任何挂在 `orchestrate` 里的提醒对此门**永不触发**。而 goal-change 正是"无人值守静默"最危险的一类（全项目 halt）。
- **推荐挂点**：`tick` 的 `cfg = _load_effective_config(...)`（`:2339`）与 `enabled/paused` 早退（`:2340-2341`）之后、goal 检测（`:2343`）之前，插一行 `_remind_pending_gates(project_root, st, cfg)`。这样：覆盖 `orchestrate` 的所有早退分支；新门在下一次 tick（~4s 后）进入判定窗口（阈值为 30min，无影响）。DESIGN D-007 已按此落定。
- 与 `_process_deferred_reviews`（`:2973`）的先后：两者**不重叠**。`_process_deferred_reviews` 是 "pending-review 批次的 48h 升级"（`:3002 "deadline"` / `:3012 "closure"`，事件 `review-escalated`），只在 running stage 内跑；G2 提醒是"所有 pending 门超阈"（含 stalled / budget-exhausted / stage-close / stage-confirm / goal-change / xkey-authorize）。语义上 `_process_deferred_reviews` 是**升级**（escalate-to-human），G2 是**提醒**（remind），两事件名不同、互不消费。若把 G2 也塞进 `_process_deferred_reviews`，就同时漏掉 goal-change 与"无 running stage"的项目。

**F2.1 判定形状：纯函数 + 薄 IO 壳**

```python
# 纯函数（无 IO、无 state；单测直接喂列表）
def pending_gate_reminders(
    pending: list[gates.Gate],      # gates.pending_gates(gates_dir) 的结果
    rows: list[dict],               # mw_common.parse_workers_file(...)
    reminder_counts: dict[str, int],# gate_id -> 已提醒次数（来自 ledger）
    now: datetime.datetime,
    cfg: dict,
) -> list[tuple[gates.Gate, int]]:  # [(gate, n)]，n = 本次要发的序号
```
IO 壳 `_remind_pending_gates(project_root, st, cfg)`：`gates.pending_gates(gates_dir)`（`gates.py:728`）→ 坏文件用 `except gates.GateFormatError: return`（同 `orchestrate:222` 的 skip 策略；`tick` 后面 `:2346` 自己会记 config 事件）→ `parse_workers_file`（`mw_common.py:1566`）→ 读 ledger 计数 → 对每个 `(gate, n)`：append ledger 行 + append timeline `gate-reminder` 事件。

- 该壳每 tick 多一次 `_workers.parallel` 读取（非 halted 路径上 `orchestrate:229` 会再读一次）。E2 单文件、4s 周期，成本可忽略；若 PM 在意，可在 `tick` 里把 rows 传入 `orchestrate` 复用（但会动 `orchestrate` 签名）。
- **timeline 事件名**：新增 `gate-reminder` 必须同改两侧词汇表——`timeline.py:67 EVENT_TYPES`（frozenset）与 `status-model.ts:962 EVENT_TYPES`（`Set`）。`autopilot-event-parity.test.ts:73-84` 判 **set 相等（两个差集都为空，`:81-82`）**，漏一侧即红。

**F2.2 时间锚 = `created_at`（不能用 `expires_at`）**

- 字段：`gates.py:210 created_at`（base required，`gates.py:93` 在 `_REQUIRED_FIELDS`（`:138-142` 6 名断言），`:202-203` answered_at 可空的语义注释）；`expires_at: gates.py:241`（v2 optional）。
- 实测：E2Feature 21 个门 `gate_schema` 全 = 1，`missing_expires=21`（见 [VERIFY]）⇒ 以 `expires_at` 为键对历史门**永不触发**。写侧 `_gate_default_fields`（`conductor.py:2553`，`expires_at = created_at + 48h`，`:2569`）只覆盖 conductor 新建的门。
- 纯函数用 `now - _gate_created_epoch(gate.created_at)`；`_gate_created_epoch` 已存在（`mw_common.py:2358`），doctor 的 `waited_s` 用的就是它（`mw_common.py:2450-2452`）。TS 侧同口径：`monitor.ts:373-375` `ageMs = nowMs - Date.parse(created_at)`。

**F2.3 `BLOCKED_ON_HUMAN` 三轴取值点 + `tickStale` 的 Python 等价面**

| 轴 | Python 面（conductor 内） | TS 面（monitor） |
|---|---|---|
| pending_gates > 0 | `gates.pending_gates(gates_dir(project_root))`（`gates.py:728`） | `monitor.ts:186 scanPendingGate`（非 pending 返回 null 在 `:245`）→ `snapshot.gates` |
| 无在飞 worker | `parse_workers_file`（`mw_common.py:1566`）后按状态过滤 | `monitor.ts:355-357`（只收 `status==="running"`）→ `snapshot.workers` |
| conductor 仍在 tick | **不存在**（见下） | `monitor.ts:600-609`：取 timeline 尾窗最后一条 `beat`（`BEAT_EV` `status-model.ts:992`）的 age（`:602`/`:605`）；`staleAfterMs = max(30_000, poll_ms*5)`（`:609`）；`tickStale = ageMs > staleAfterMs`（`:635`） |

- **`tickStale` 没有 Python 等价面**：全仓 grep `tick_stale|tickStale` 在 `.py` 侧 0 命中（唯一相关的是 `mw_common.worker_liveness` 的 **worker heartbeat** 90s，`mw_common.py:1983`，与 conductor tick 无关）。Python 侧若真要复刻，唯一原料是 `timeline.tail_events(...)` 里最后一条 `beat` 的 ts——但**G2 判定发生在 conductor 自己的 tick 内部，conductor 正在 tick 是构造事实**，不需要也不应该自评 `tickStale`。⇒ 三轴中前两轴 Python 算，第三轴 Python 恒 true；TS 面板必须要第三轴（它是外部观察者），这不是 P-021 的"镜像陈旧"，而是两侧**职责不同**（见 F6）。
- 实测 beat 节奏（E2）：尾 200 事件里 199 条 beat，跨度 1378s ⇒ 统计上的 beat 间隔 ~6.9s（配置 `poll_interval_sec` 默认 4，`config.py:55`）。

**F2.4 纯函数判据（推荐）**

```
for gate in pending:
    n = reminder_counts.get(gate.id, 0) + 1
    if n > cfg["gate_reminder_max"]: continue
    if (now - created_at) < n * cfg["gate_reminder_after_min"] * 60: continue
    if any(row["status"] not in _TERMINAL_STATUSES for row in rows): continue   # 见 F6
    emit(gate, n)
```
- 时间锚 `created_at`；第 n 次提醒的触发时刻 = `n × after_min`（第 1 次 30min，第 2 次 60min）。这就地解决"否则第 1、2 次会在相邻 tick 内 4s 连发"的问题（F3.3），且**只用一个阈值键**。
- DESIGN D-007 原文即此（`design.md` "G2（每 tick）" 伪码）。
---

### F3 ≤2 次计数载体（DRQ-2.3）

**F3.1 方案 (a)「detail 序号 + `_timeline_has_event`」被实测否证。**

- `_timeline_has_event`（`conductor.py:1817-1830`）语义 = 读 `timeline.tail_events(path, limit=200)`（`:1822-1826`）后对 `(ev,key,detail)` **全等**匹配，返回 bool。**它是布尔，不是计数**。
- 窗口大小实测：`tail_events` 只读**当前文件**尾 512KB（`timeline.py:457-503`，`max_bytes=512*1024`、默认 `limit=400`；docstring 明写"Rotated generations are deliberately not consulted"），`_timeline_has_event` 再砍到 200 条。E2 实测 `tail200` 里 199 beat + 1 其它事件，时间跨度 **1378s ≈ 23.0min**（本轮；首轮 1198s、二次 1294s，随实时增长）；纯 idle 4s 节奏下 200 条 ≈ 800s ≈ **13.3min**。
- 结论：第 1 次提醒（`reminder 1/2`，t=30min）事件在 t≈53min 就滚出 200 条窗口；第 2 次触发时刻是 60min（n×threshold）⇒ 判定时"看不到第 1 条"→ 会**把 1/2 再发一遍**（计数器复活）。方案 (a) 在 30min 周期下**结构性不成立**，与 `_review_escalate` 的"只发一次"用途不同（那个不需要计数）。timeline 轮转（`timeline.py:104-105`，10MB × 2 代）只会让窗口更短，不可能撑住 ≥2。

**F3.2 方案 (b)「复用 `auto-decisions.jsonl` 单写者 append」形状审计：对既有判据全部不可见。**

- 载体：`auto_decisions_path`（`conductor.py:4943-4947`，`.agenticdoc/_autopilot/auto-decisions.jsonl`，docstring 自述 "append-only authority ledger (outlives the 2-generation timeline)"）；写 `_append_auto_decision_row`（`:5729-5740`，`path.parent.mkdir` + `open("a")`，`seq = len(rows)+1`）；读 `auto_decision_rows`（`:5707-5727`）。
- 现有消费者**全部**以 `phase == "decide"` 为入口，新增 `phase:"remind"` 行逐条核对：
  - `_effective_auto_decision`（`:6033-6052`）：`if row.get("phase") != "decide": continue` ⇒ 不可见。
  - `_escalate_recorded`（`:6055`）/`_shadow_decision_recorded`（`:6065`）/`_defer_recorded`（`:6076`）：都要求 `phase=="decide"` ⇒ 不可见。
  - `_night_rows`（`:5813-5824`）：要求 `phase=="decide" and executed is True` ⇒ 不计配额。
  - `_auto_breaker_signal`（`:5853-5883`）：`executed = [row for row in rows if row.get("phase")=="decide" and row.get("executed")]` ⇒ 不触发 burst/repeat 断路器。
  - `auto_consumption_set`（`:5741`）：只取 `phase in {"decide","revoke"}` ⇒ 不可见。
  - `shadow_prerequisites`（`:5934` 起）：`mode=="shadow" and phase=="decide"` ⇒ 不可见。
- 唯一被影响的是**计数/诊断**：`seq = len(rows)+1` 会被提醒行抬高（无害）；`len(auto_decision_rows(project))` 型诊断（如 `test_autopilot_auto_decision.py:412`）会把提醒算进总数。E2 实测该 ledger **不存在**（`auto_gate_mode` 未开），提醒行会成为其首行——语义上把"自动决策账本"扩成"自动决策 + 提醒账本"。
- **反例/替代**：若 PM 认为台账语义不该混，用同形状的兄弟文件 `gate-reminders.jsonl`（同样 conductor 单写者 append + 同样的 `_reminder_count` 读函数）污染严格更小；代价是多一对读写函数与一个文件名常量。**两者都必须避免往 gate 文件写计数**：`_stamp_gate_defaults`（`:2499`）必须在 `snapshot_gate_created`（`:5581`）之前，改门文件会破 T-06 的 `gate_file.sha256` replay 绑定（RQ-2 F4）。也不要只靠 pi session entry 存计数（新会话重置 → 可能 >2 次）。
- **推荐**：方案 (b)，行形状固定为 `{"phase":"remind","gate_id","gate_kind","gate_key","reminder_n","reminded_at","detail"}`，**不得**带 `executed` / `decision` / `mode`（那三个字段是 decide 行的语义位）；读侧新增 `_reminder_count(rows, gate_id)`（只数 `phase=="remind"`）与 `_reminder_recorded(rows, gate_id, n)`，与 `_defer_recorded` 同族。DESIGN D-006 已落定方案 (b) + 该行形状（`design.md` §2.3）。

**F3.3 触发规则与 AC-006 的自然成立**

- 规则：第 n 次提醒在 `age ≥ n × gate_reminder_after_min` 时发（F2.4）；`max=2` ⇒ 30min / 60min 两次。这样 2 次提醒天然相隔 30min，不会因"每 tick 都满足阈值"而 4s 连发两 turn。
- **AC-006（answered 即停）零额外状态**：循环的输入永远是 `gates.pending_gates`（`gates.py:728`，`status == "pending"` 过滤）；门被答后不在集合内，既不再发事件也不再读它的计数。ledger 里的历史 `remind` 行保留但不被消费。`status` 是唯一权威位（`gates.py:74 GATE_STATUSES`）；不要用 `answered_at`（可空，`gates.py:201-203`）。
- 参考量级（E2 历史 wait 语料）：不加 cap 的 30min 周期提醒数 774；cap 2 后 26（见 [VERIFY]）。这是 R2 噪音风险的具体收敛值。

---

### F4 配置键（DRQ-2.4）

**F4.1 建议两个键都注册**（任务默认：`gate_reminder_after_min=30`、`gate_reminder_max=2`）：

- `gate_reminder_after_min`：AC-005 明写"默认 30 min，可配置" ⇒ 必须注册。
- `gate_reminder_max`：AC-005 锁定"最多 2 次"，但它同时是 R2 的缓解旋钮（想更静音时可设 1）。为不破坏 AC-005，范围必须闭在 `(1, 2)`——即该键只能**降低**不能抬高上限。若 PM 决定"AC 锁死、不要旋钮"，则可只注册 `after_min`，实现里 `max` 用模块常量 `GATE_REMINDER_MAX = 2`。**DESIGN D-010 已落定：保留该键，值域 1..2。**
- 范围建议：`gate_reminder_after_min = (1, 1440)`、`gate_reminder_max = (1, 2)`。1440 的理由见 F4.4（阈值的上界必须 ≤ 24h，否则"主动通道"会晚于 doctor 的被动文本通道，语义倒置）。

**F4.2 注册步骤（照抄现有 int 键路径）**：

1. `autopilot/config.py:55 DEFAULT_CONFIG` 加两键（并更新模块 docstring `:26-52` 的字段表；当前 14 键）。
2. `autopilot/config.py:79 _INT_RANGES` 加两条范围（校验器 `:100 validate_config` 自动生效，越界/错类型 fail-closed）。
3. TS 镜像 `autopilot/status-model.ts`：`AutopilotConfig` interface（`auto_gate_mode` 在 `:105`）、`DEFAULT_CONFIG`（`:108-122`）、`INT_RANGES`（`:147-156`）。`BOOL/LIST/STR/ENUM` 不需动。
4. 冻结语料：`test/fixtures/autopilot-config-corpus.json` 追加"单键 payload"（`test_autopilot_config_parity.py:298 _single_key_cases`）+ 边界用例，然后**刻意重冻** `FROZEN_CORPUS_SHA256`（`:60`）与 `FROZEN_CORPUS_COUNT`（`:61`，当前 55）；`test_p4_corpus_integrity`（`:310`）会挡下未重冻的漂移。`test_p6_partial_single_key`（`:384` def、`:434` `assert covered == expected_keys`）要求**每个键**都有单键用例，否则 `covered == expected_keys` 红。
5. 计数断言 14 → 16 的既有硬编码（必须同步改，别让下一个 key 踩 P-021）：
   - `test_autopilot_config.py:114`（`len(DEFAULT_CONFIG)==14`）、`:138`、`:139`；
   - `test_autopilot_effective_config.py:73`、`:207`（`len(eff.values)==14`）；
   - `test_autopilot_config_parity.py:423`、`:426`（`== 14`）；
   - 文档字符串里的 "14-key"（`config.py:154`、`status-model.ts:19`、`test_autopilot_config_parity.py:23/166/392`）。
6. **不入 `EFFECTIVE_KEYS`**（`effective_config.py:62-65` 只有 `xkey_verify_cmd`/`xkey_verify_cwd`）：提醒阈值是项目层语义，机器层不得覆盖（`auto_gate_mode` 是同类先例，`config.py:39-42`）。
7. 读取必须走 `_load_effective_config`（`conductor.py:108`，返回完整视图）。E2 实测项目文件只有 8 键（见 [VERIFY]）⇒ 提醒壳里**不能**对 `load_config` 的原始 dict 下标 `cfg["gate_reminder_after_min"]`（`config.py:157-166` 的"缺失键不得用 `[]` 读"规则）；用 `cfg.get(...)` 或 effective 视图。

**F4.4 与 doctor 24h/72h 的一致性**：

- doctor 文本的 gate 时间是 `waited > 72h` → issue、`> 24h` → suggestion（`mw_common.py:2847-2849`），文本行只在 I1-I6/I9 命中时打印（`_gates_text_alerted :2764-2778`，同阈 24h 在 `:2775`；输出点 `mw_common.py:3100`/`:3108`）。
- 30min < 24h，二者**不冲突但也不重叠**：30min–24h 区间在 doctor 文本里一字不出（I7 零扰动），正是 G2 要用新提醒补的空白。⇒ 只需保证阈值可配范围不越过 24h（上界 1440 即此意），无需改 doctor 阈值。

---

### F5 可见面（DRQ-2.5）

**(a) `/autopilot status` 的 `GateView`：加 `ageMs` 足够；`BLOCKED_ON_HUMAN` 不该做成 per-gate 字段。**

- 现状：`status-model.ts:1238-1242` `interface GateView { id; kind; status }`；映射 `:1349`（**丢弃了 `GateRecord.createdAt:654`**）；文本 `:1397-1398` 只打 `gates: N total, M pending` + 每行 `<id> <kind> <status>`。
- 确切改动：`GateView` 加 `ageMs: number | null`；`:1349` 改为在 map 里算 `Date.parse(g.createdAt)`（`GateRecord.createdAt: string` 是 base required，v1 门也有）→ `Math.max(0, Date.now()-t)`，不可解析 = `null`；`renderStatusText` 在每条门后按 `g.ageMs` 追加 ` age=<coarse>`。
- 若 PM 坚持 status 面也要 `BLOCKED_ON_HUMAN`：它**不是 gate 的属性**（依赖"全项目 running 行数 = 0"与 `tickStale`），应做成 `AutopilotStatus` 的**顶层**字段（如 `blockedOnHuman: boolean`）。代价：`deriveStatusModel` 当前不读 `_workers.parallel`（`status-model.ts` 只 import `IndexStore`，`:36`），也不算 tick 新鲜度（只取 timeline head `:1351`）。AC-008 的原文只点名 **monitor 面板与 `mw doctor`**，所以建议 status 面只补 age（DESIGN D-009 已按此落定）。
- **会红的既有测试**：`autopilot-console.test.ts:379-383` 对 `s.gates` 做**精确 `toEqual`**（`{id,kind,status}`）⇒ 加 `ageMs` 必须同步改该断言；`:412-413` 用的是 `toContain`，加后缀不破坏。`autopilot-gate-presentation.test.ts:205-241`（describe `:205`、it `:206`、`toEqual` `:222`、`slice(0,12)` `:225`）锁的是 `GATE_FRONTMATTER_FIELDS`（40 名、逐项同序）与其 Python 子进程镜像，**不锁 `GateView`**；`autopilot-status-parity.test.ts` 锁的是 `KEY_STATUSES`/`_DEP_SATISFIED`，也不锁 `GateView`。

**(b) monitor 面板：新增一条 snapshot 级 `BLOCKED_ON_HUMAN` 行，而不是塞进 per-key attention。**

- 现状 attention（`monitor.ts:724-745`）按 key 过滤：`status==="stalled" || inFlight>0 || blockedBy.length>0 || stallByKey.has(key)`（`:724-726`）。stage 级门（`key==""`）或没有对应 roadmap key 的门根本进不了 attention；`workers: 0 running` + 1 个 pending 门时面板不会提示"在等人"（RQ-2 缺口 4）。
- 判据（三轴，F6）：`snapshot.gates.length > 0 && nonTerminalRows === 0 && !snapshot.autopilot.tickStale`。
- 确切落点：`MonitorAutopilot`（`:156-168`）或 `MonitorSnapshot`（`:170-176`）加 `blockedOnHuman: boolean`（推荐 snapshot 顶层，因为三个输入正好是 snapshot 级）。compute 位置：`readMonitorState`（`:287`）尾部、`return`（`:386`）之前。渲染：在 `if (s.autopilot.enabled)` 段里（`:707` 起）、attention 循环（`:724`）**之前**插一行，`trunc` 到 `MONITOR_LINE_MAX`（`:61`）。DESIGN D-009/D-020 已把该字段与渲染锁在 `:156-176`/`:707-727`。
- 注意 `workers[]` 只含 `running`（`:356`），所以 `nonTerminalRows` 要在同一次 `WorkerStore(...).readAll()`（`:355`）循环里另算（见 F6 口径分歧）。
- 既有测试会红：`autopilot-monitor.test.ts:146` 直接构造 `MonitorAutopilot` 字面量（`stubAutopilot`）、`:911-912`/`:995-996` 断言 `tickAgeMs/tickStale` ⇒ 加字段需同步。

**(c) `mw doctor`：推荐保持 24h/72h 文本阈值零扰动，另加机械 `blocked_on_human` 字段 + 条件文本。**

- `_doctor_gates`（`mw_common.py:2689`）已经算了每个 pending 门的 `waited_s`（`_gate_pending_entry :2443`，`:2450-2452`，`formula: "now - created_at"`，节点 `:2503-2505`）⇒ `mw doctor --json`/`mw autopilot gates --json`（`mw.py` `_ap_gates`，工作树 `:3781` / HEAD `:3775`——该文件被并行会话改过，按符号名重锚）本来就有 pending 时长，"显示挂了多久"已在机器面成立。
- 槽点在 `mw_common._doctor_gates` 里加 `blocked_on_human`（三轴，F6；需一次 `parse_workers_file`，`mw_common.py:1566` 同模块）+ `gate_reminder_after_min` 取值（可用 `_doctor_autopilot` 的 effective 视图口径，`mw_common.py:2222`）。
- 文本：`format_doctor_text` 的 gate 行（条件 `mw_common.py:3100`、行体 `:3108`）只在 `_gates_text_alerted`（`:2764`）为真时打印。推荐**不改 24h/72h**，只让 `blocked_on_human == True` 也进入"该行打印"的条件集，并在这条已存在的 `gates:` 行尾追加 `BLOCKED_ON_HUMAN` 标记。这样：健康项目逐字节不变（I7 的既有测试 `test_doctor_gates.py` 仍绿）；只在真等人时多出可见标记。
- **不推荐**把 24h/72h 拉低到 30min：E2 历史语料里 30min–24h 的门有 12 个（[VERIFY] `answered_waited_over30min=13` 含 1 个 >24h），拉低会把"一个门挂了 40 分钟"从静默变成 doctor issue/suggestion，破坏 I7 零扰动契约且制造噪音——主动提醒通道（ledger + 推送）才是 30min 级别的正确表达。
---

### F6 AC-007 的机械区分：两侧各怎么算、要不要逐字一致（DRQ-2.6）

**F6.1 真 pending gate vs EXECUTE 期事件稀疏**：都是"timeline 静默"，唯一机械区分是**有没有在飞 worker**：
- EXECUTE 稀疏 = `running_rows > 0`（哪怕 timeline 只剩 beat，conductor 正常每 tick append beat，`conductor.py:2336`）。
- BLOCKED_ON_HUMAN = `pending_gates > 0 ∧ 无在飞行 ∧ conductor 仍在 tick`。

**F6.2 Python（conductor）侧**：
- 门：`gates.pending_gates`（`gates.py:728`）。
- 行：`mw_common.parse_workers_file(mw_common.workers_path(root))`（`mw_common.py:1566`/`:1554`）。**口径选择**：conductor 自己的 `_is_in_flight`（`conductor.py:2423-2424`）用 `status not in mw_common._TERMINAL_STATUSES`（`mw_common.py:162 = {done, failed, needs-clarification}`，同值在 `:1854` 二次定义），**含 `pending`**；TS monitor 的 `workers[]` 只收 `status==="running"`（`monitor.ts:356`）。两者是**不同集合**（pending 队列行）。
- tick：不需要（tick 内恒真，F2.3）。

**F6.3 TS（monitor/poll 循环）侧**：
- 门：`readMonitorState` 的 `snapshot.gates`（只含 pending）或 `listGates(...).gates.filter(status==="pending")`。
- 行：monitor 的 `workers` 只有 running ⇒ 必须另算 `nonTerminalRows`（同一次 `readAll` 里 `!isTerminal(status)`）。
- tick：`autopilot.tickStale`（`monitor.ts:635`）。

**F6.4 要不要逐字一致（P-021）**：
- 建议**判据定义逐字一致，轴的实现各自本地化**：
  1. "无在飞 worker"**两侧统一取非终态**（`status ∉ {done,failed,needs-clarification}`），而不是 `status=="running"`。理由：`pending` 行意味着 conductor 下个 tick 就会启动它，此时提醒人属误报；`pending` 长期不启动是另一类故障，不该混进 "BLOCKED_ON_HUMAN"。⇒ monitor 要改 `workers.length===0` 这个直觉写法。TS 终态谓词现成有两份重复实现（`pm-orchestrator.ts:50`、`ui-bridge.ts:439`），实现时不要造第三份分叉。
  2. "conductor 仍在 tick"只在 TS 面有意义（Python 面恒真）；**不要**为了"对称"在 conductor 里造 `tickStale` 自评。
  3. 阈值与状态闭集这类**跨语言契约**必须逐字一致，并由 parity 测试锁死（先例：`autopilot-event-parity.test.ts:73-84`、`autopilot-status-parity.test.ts`）。建议给 G2 的 `blocked_on_human` 判据加跨语言对拍（DESIGN D-008 定为"两侧统一非终态口径，tick 轴只在 TS 面"）。
- 结论：**两侧不要"逐字一致地实现全部三轴"**（Python 无 tick 概念）；要一致的是**布尔判据的真值表**，由共享夹具 + 对拍测试锁住。

---

### F7 测试矩阵（DRQ-2.7）

**既有夹具风格（照抄，不造新风格）**：
- Python（pytest，`packages/multi-workers/`）：`test_autopilot_conductor.py:34 _project(enabled=...)` + `:45 _state(project)` + `conductor.tick(project, st)` 直调；事件用 `_events(...)`（`:50`，内部 `timeline.query_events`）。`_verify(tag, **kv)` 打印 `[VERIFY]`（`:24`）。门夹具直接 `gate_file.write_text(...replace("status: pending","status: approved"))`（`:144`）。配置夹具 `config.default_config()` + `config.save_config`（`:75-78`）。
- 计数/ledger 夹具：`test_autopilot_auto_decision.py:85` 直接 `conductor._append_auto_decision_row(project, {...})` 造行、`conductor.auto_decision_rows(project)` 读回（`:244`）。
- vitest：poll 循环用 `test/extensions/agent-team-loop.test.ts:1838 fakePi()`（describe `:1837`；捕获 `sendMessage` 的 `content` 与 `opts.triggerTurn`）+ `vi.useFakeTimers()` + `vi.advanceTimersByTime(500)`（`:1911-1912` 起多处）；monitor 用 `suite/autopilot-monitor.test.ts`；status 用 `suite/autopilot-console.test.ts`。

**G2 用例清单（每条给"正向 + AC-014 非空洞对照"）**：

| # | 用例 | 正向断言 | 对照（摘掉/反转判据 ⇒ 转红） |
|---|---|---|---|
| 1 | pending 超阈触发一次 | 30min 前 + pending 门 + 0 行 → tick 后 ledger 有 `remind n=1` + timeline 一条 `gate-reminder` | 摘除年龄条件 → 门建立即发 ⇒ 用例 6 红 |
| 2 | 同门第 3 次不触发 | 预置 2 行 `remind` + age=120min → ledger 仍 2 行、无新 event | 去掉 `n > max` → 出现 n=3 行 ⇒ 红 |
| 3 | answered 后零残留 | 门 `status: approved` → tick 后无 `remind` 行/事件 | 改成遍历 `gates.enumerate` 而非 `pending_gates` → approved 门被提醒 ⇒ 红 |
| 4 | running_rows>0 不触发（AC-007） | `_workers.parallel` 放一条 `running` 行 + 超阈 pending 门 → 无提醒 | 摘掉行状态过滤 → 提醒发出 ⇒ 红 |
| 5 | tickStale 不触发（TS 面） | monitor 夹具：pending 门 + 0 running + 最后 beat 600s 前 → `blockedOnHuman===false` 且渲染无该行 | 摘掉 `!tickStale` → 渲染出现 ⇒ 红（对照点紧邻 `autopilot-monitor.test.ts:995-996`） |
| 6 | 30min 内不触发 | age=29min → 无提醒 | 阈值设 0 / 反转比较 → 触发 ⇒ 红 |
| 7 | 第 2 次在 60min（不同 tick） | age=59min → 仍 1 行；age=61min → 2 行 | 条件写成 `age >= after_min`（忽略 n）→ 第 2 行在 4s 后的 tick 出现 ⇒ 红 |
| 8 | goal-change 门也会提醒（F2.0 回归） | goal 改动 → `tick` 返回 `halted-goal-change`；再过 30min 的 tick 后 ledger 有该门 `remind` | 只挂 `orchestrate` → 永不提醒 ⇒ 红 |
| 9 | 计数跨 timeline 轮转不复活 | 造 >200 条 beat 让 reminder event 滚出 `tail_events(200)`，再在 60min 触发 → 仍是第 2 次而非重复第 1 次 | 若改用 `_timeline_has_event` 方案 → 出现两条 `n=1` ⇒ 红 |
| 10 | 非空洞对照：判据存在性 | 断言每个正例都读到真实 `remind` 行/事件（不是断言函数返回 `None`） | — |
| 11 | 跨语言 parity：`blocked_on_human` 真值表 | Python 子进程 + TS `readMonitorState` 在同一夹具四组（0 行/pending 门/新鲜 beat；1 running 行；tickStale；无门）上取值相等 | 任一侧口径漂移（TS 用 `workers.length`、Python 用非终态）⇒ 红 |
| 12 | 配置键注册与冻结语料 | `len(DEFAULT_CONFIG)==16`（两侧）、单键 payload 通过、`after_min=0`/`max=3` fail-closed | 少改一侧 `INT_RANGES` → parity 红；不重冻 sha → `test_p4` 红 |
| 13 | EV 词汇表 | `gate-reminder ∈` 两侧 `EVENT_TYPES` | 只加 Python → `autopilot-event-parity.test.ts:81-82` 差集非空 ⇒ 红 |
| 14 | status/doctor 可见面 | `renderStatusText` 含 `age=`；doctor `blocked_on_human==True` 时文本含标记、健康项目文本逐字节不变 | 摘掉 age 渲染 → `autopilot-console.test.ts` 新增断言红 |

- 归属建议：Python 判定/ledger/挂点/配置 → 新文件 `test_autopilot_gate_reminder.py`（风格对齐 `test_autopilot_pending_review.py`）；monitor/status 可见面 → 扩展 `suite/autopilot-monitor.test.ts` / `suite/autopilot-console.test.ts`；推送消费 → `test/extensions/agent-team-loop.test.ts` 的 `startWorkerPollLoop` describe；跨语言 → `suite/autopilot-gate-reminder-parity.test.ts`（参考 `autopilot-event-parity.test.ts` 的 Python 子进程 dump 写法）。
- AC-014 要求"所有 `[VERIFY]` 行数值来自实测"⇒ 用例里的 30/60min 断言要么给纯函数注入 `now`（F2.1 签名已带），要么用 monkeypatch/直接改门文件的 `created_at` 造 age（现成做法）。

---

## 结论 → 决策映射

- **F2.0 是硬结论**：提醒判定必须挂 `tick`（`conductor.py:2339` 之后、`:2343` goal 检测之前），不能只挂 `orchestrate:204`，否则 goal-change 门（`:2392-2395` 早退）永不提醒；用例 8 固化。DESIGN D-007。
- **判定在 Python，投递在 extension**（F1.5）：conductor 写 `gate-reminder` timeline 事件 + `auto-decisions.jsonl` 的 `phase:"remind"` 行；`startWorkerPollLoop`（`pm-orchestrator.ts:519`）读 ledger 后 `deliverPmAlert`（`ui-bridge.ts:131`，`:139 triggerTurn`）。extension 侧去重用进程内 `Set` + session entry（`console.ts:75` 先例）。DESIGN D-005/D-010。
- **计数载体 = ledger**（F3）：方案 (a) 被 200 条尾窗（实测 23.0min / 纯 4s 节奏 13.3min，均 < 60min）否证。DESIGN D-006。
- **AC-005/006/007**：AC-006 由 `pending_gates`（`gates.py:728`）每 tick 重算自然成立；AC-007 由"非终态行数 == 0"承担（F6）；goal-change 门也是 pending 门，不需特例。
- **AC-008**：monitor 加 `blockedOnHuman` 行（F5b）；status 加 `GateView.ageMs`（F5a，同步 `autopilot-console.test.ts:379-383`）；doctor 加 `blocked_on_human` 机器字段 + 条件文本，**保持 24h/72h 与 I7 零扰动**（F5c）。DESIGN D-009。
- **配置**：`gate_reminder_after_min=30`（range 1..1440）+ `gate_reminder_max=2`（range 1..2，否则 AC-005 被配置破坏）；两侧注册 + 语料重冻 + 14→16 计数断言（F4.2）。DESIGN D-007/D-010。
- **给 DESIGN 的待决（三次执行时状态：已在 design.md 落定）**：(1) `gate_reminder_max` 保留为键、值域 1..2 ⇒ **D-010 落定**；(2) 多 PM 窗口时同一提醒按 `watch.key == gate.key` 作用域、stage 级/`key==""` 门例外，并把投递去重存到 session entry ⇒ **D-010 落定**；(3) `phase:"remind"` 放进 `auto-decisions.jsonl`（非兄弟文件）⇒ **D-006 落定**。

## 数据缺口

- "改后"数字不可观测（本 key 仍在 DESIGN/PLAN）；所有量级（774/26、~23min 窗口、21 门）都是 E2Feature **历史**语料或静态文件事实。
- E2 现在 `pending_count=0`，无法现场观察"提醒真的被 PM 窗口消费"；端到端（conductor 写 → extension 推 → PM turn）需 EXECUTE 期夹具或 L2 测试，本文只给到接线位置与单测方案。
- 多 PM 窗口推送作用域无现成先例（`notified` 是 per-window、worker 回读按 owner key 作用域），DESIGN 用 session entry 去重（D-010）补上。

## 锚点快照与并行写面（2026-10-10T02:59Z 三次执行复核）

- 本 note 的所有行号本轮在 HEAD `10446aefb` 工作树上逐条复核，且引用文件此时**工作树 = HEAD（干净）**：`autopilot/{conductor,gates,config,timeline}.py`、`mw_common.py`、`autopilot/{monitor,status-model,console,gate-writer}.ts`、`pm/{pm-orchestrator,ui-bridge}.ts`、`core/{extensions/types.ts,session-manager.ts}`、`shared/paths.ts`、全部测试文件。首轮/二次执行时注记的"并行会话改动 conductor.py（`_gate_default_fields` 行号漂移）"已消失（本轮曾短暂观测到 conductor.py 被并行会话标脏一次，复核时已回到 HEAD，`:1817/:2330/:2392/:2553/:5729` 锚点不变）——本轮 `_gate_default_fields` 就在 `:2553`（HEAD 值），T-20 写侧闭集 guard 也已回归 HEAD。
- 仍被**并行会话**改动的只有两个本 note 的低频引用文件（非本 key 写面）：`packages/multi-workers/autopilot/effective_config.py`（文案，未提交）与 `packages/multi-workers/mw.py`（`_ap_gates` 工作树 `:3781` / HEAD `:3775`，未提交）。⇒ 引用这两处时**按符号名重锚**（`grep -n 'def _ap_gates'`），其余行号可直接依赖。

## 复核（2026-10-10T02:59Z 三次执行）

- 独立重测（E2Feature 实时语料，21 门，`auto-decisions.jsonl` 仍不存在）：`gate_files=21`、`enumerate=21`、`schema_versions={1:21}`、`missing_expires=21`、`pending_now=0`；应答等待 >30min 13 个、>24h 1 个、>72h 1 个、最长 293.01h（`gate-0019` stage-close）；无 cap 30min 提醒 774 次 / cap 2 = 26 次；`_autopilot/config.json` 8 键；tail200 = 200 事件（199 beat，跨度 1378 s ≈ 23.0 min）。与首轮（195 beat/1294 s）逐项一致，仅 tail 窗口随实时增长（结论"窗口 ≪ 60 min"不变）。
- grep-0 复核：`pm/` 目录 `listGates|gatesDir` = 0；Python 侧 `tick_stale|tickStale` = 0；Python 侧 `sendMessage` = 0；全仓 `blocked_on_human|BLOCKED_ON_HUMAN|blockedOnHuman` = 0；`gate_reminder|gate-reminder` = 0。`deliverPmAlert` 站点 = 定义 `ui-bridge.ts:131` + 别名 `:146` + 唯一外部调用 `pm-orchestrator.ts:584`。
- 行号修正（二次执行 → 三次实测）：`autopilot-console.test.ts` 的 gates 精确 `toEqual` `:374-378` → **`:379-383`**；`autopilot-monitor.test.ts` 的 `stubAutopilot` `:151` → **`:146`**；`monitor.ts` beat 窗口 `:596-609` → **`:600-609`**；`mw_common.py` doctor gate 文本 `:3100-3112` → **`:3100`/`:3108`**；`_timeline_has_event` `:1817-1829` → **`:1817-1830`**；`_process_deferred_reviews` deadline 分支 `:2997-3002` → **`:3002`**；`_review_escalate` `:2901-2918` → **`:2901-2920`**。
- 所有结论/推荐不变：路 B（判定在 Python、投递在 TS）；挂点 `tick`（`conductor.py:2339` 之后、`:2343` 之前）；计数 = `auto-decisions.jsonl` 的 `phase:"remind"` 行；两键配置（`max` 值域 1..2）；可见面 = monitor `blockedOnHuman` + status `GateView.ageMs` + doctor 零扰动加机器字段；AC-007 两侧统一"非终态"口径、tick 轴只在 TS 面。

[VERIFY] DRQ-2: head=10446aefb e2_gate_files=21 e2_enumerate=21 e2_schema_versions=1:21 e2_missing_expires=21 e2_pending_now=0 e2_answered_total=21 e2_answered_waited_over30min=13 e2_answered_waited_over24h=1 e2_answered_waited_over72h=1 e2_max_answered_wait_h=293.01(gate-0019 stage-close) e2_config_keys=8 e2_autodecisions_ledger=absent tail200_events=200 tail200_beats=199 tail200_span_s=1378 tail200_span_min=23.0 pure_4s_window_min=13.3 uncapped_30min_reminders=774 capped2_reminders=26 pm_push_sites=deliverPmAlert(ui-bridge.ts:131)+alias(:146)+1_call(pm-orchestrator.ts:584) deliverPmAlert_idempotent=no triggerTurn_line=ui-bridge.ts:139 poll_interval_ms=4000(pm-orchestrator.ts:48) gates_pending_api=gates.py:728 tickstale_python_axis=0_grep_hits blocked_on_human_hits=0 gate_reminder_hits=0 goal_gate_early_return=conductor.py:2392-2395 doc_gate_pending_api=mw_common.py:2443 doctor_text_threshold=24h/72h(mw_common.py:2847-2849) timeline_rotate=10MBx2(timeline.py:104-105) default_config_keys=14(config.py:55) corpus_count=55(test_autopilot_config_parity.py:61) frontmatter_fields=40 required_fields=6 measured_at=2026-10-10T02:59Z