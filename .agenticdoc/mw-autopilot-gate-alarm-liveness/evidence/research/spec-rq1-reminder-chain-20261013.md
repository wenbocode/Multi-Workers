# RQ-1｜gate reminder 的判据与调用链全景（T-01 / mw-autopilot-gate-alarm-liveness）

- 唯一证据文件（交付物）：`.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq1-reminder-chain-20261013.md`（本文件即其内容）
- 日期：2026-10-13｜类型：**只读取证**（未修改任何被取证文件）
- 取证范围：`H:\git\Multi-Workers`（HEAD `cc9a46a1a`；`packages/multi-workers/autopilot/conductor.py` 工作区 == HEAD，`git status` 无该文件改动）+ `H:\git\E2Feature`（生产实例，只读）
- **行号约定**：全部 `path:line` 用 `git grep -n` / `Select-String` 计法（把孤立 `\r` 也当行界）。同一文件用 `Get-Content` 索引读出的行号会比它小 ≤3（该文件含 3 处孤立 `\r`），故每条引用同时给出**代码原文**，与行号约定无关。
- 时间基准：E2Feature 主机时区 UTC+8。文中 `Z`/`+00:00` 一律为 UTC；括号内为本地时间（+8h）。`_autopilot` 各文件的 Windows `LastWriteTime` 是**本地时间**。

---

## 0. 结论先行（6 条）

1. **提醒链路是单向 push，且没有任何"状态面"出口。** conductor 每 tick 判一次 → 写台账 `.agenticdoc/_autopilot/auto-decisions.jsonl`（`phase:"remind"`）→ 写 timeline `gate-reminder` 事件。`_remind_pending_gates`（`conductor.py:2683-2738`）函数体内**没有 `print`、没有 `sys.stderr`、没有面板、没有 notification**；全仓 `gate-reminder` / `phase:"remind"` 的消费者只有 TS 的 PM poll loop（`pm-orchestrator.ts:1289-1330`、`:1466-1513`）。⇒ 提醒的**唯一**人可见形式是"一个正在运行、且正在 watch 该 gate 所属 key 的 PM 窗口被 `triggerTurn` 唤醒"。
2. **四条件里"无在飞行"是项目级整体抑制。** `if any(_is_in_flight(row) for row in rows): return []`（`conductor.py:2558`）读的是**整个** `_workers.parallel`；任意 key（含 conductor 自己派的 `_scratch-*`）有非终态行 ⇒ **所有** gate 的提醒一律不发。判据与 gate 的 `key` 无关。
3. **cap 是永久封顶，不是节流。** `gate_reminder_max` 默认 2 且 schema 闭区间 `[1,2]`（`config.py:103`/`:134`、`status-model.ts:152`/`:191`）⇒ 第 3 次提醒**配置层面不可能存在**；计数落在 append-only 台账里（`_reminder_count`，`conductor.py:2512-2520`）⇒ 进程重启也不会重置。E2Feature 实证：gate-0024 的两次提醒**相隔 4 秒**（`14:11:15Z`/`14:11:19Z`）就全部用尽，随后静默 **158.3 分钟**直到被答。
4. **历史总量很小，覆盖很窄。** E2Feature 台账 `phase:"remind"` 行 = **5**（timeline `gate-reminder` 事件同样 = 5，一一对应），只涉及 3 个 gate；而同一批 gate 里 `pending ≥ 30 min` 的有 **18** 个，其中 **15** 个零提醒（其中 15 个全部创建于提醒功能提交之前）。
5. **最长静默 12 天 5 小时（17,581 分钟）零提醒**：gate-0019（stage-close，`2026-09-27T01:57:28Z` → `2026-10-09T06:58:22Z`）。同型第二长 gate-0023 = **38.04 h**（`2026-10-10T12:45:38Z` → `2026-10-12T02:47:55Z`）。
6. **本次取证唯一能"归因到某一条件"的静默是条件 4（stage 终止抑制）：gate-0024 被条件 4 静默压制了 6.78 小时（`2026-10-12T07:24:33Z` → `14:11:15Z`）。** 它能发出那两条提醒，唯一原因是那 3 个 tick（`14:11:15Z`/`:20Z`/`:24Z`）roadmap **恰好读不出来** ⇒ `_gate_stage_context` 返回 `(None, None)` ⇒ 条件 4 fail-open 被关掉。**即：提醒是靠 roadmap 故障侥幸逃脱静默的，并且在 4 秒内烧光了全部配额。** 条件 4 的反向证据也齐备：那段窗口里 `_workers.parallel` **零非终态行**（条件 2 不成立）、`_reminder_count("gate-0024")` **=0**（条件 3 不成立）、年龄 4.6–11.3 h ≫ 60 min（条件 1 不成立）⇒ 只有条件 4 能解释。

> 附带判定（对 spec 有直接影响）：**"进程活着但跑的是哪版代码"不可查，且已真实发生。** E2Feature 的 conductor 进程（启动 `2026-10-12T14:06:14Z`）写出的 stderr 行与 timeline 事件**逐字**等于 commit `b65380d1b`（`2026-10-13T03:19:28Z` 提交，含 roadmap 告警去重 `_ROADMAP_ALARM_SEEN`/`_emit_roadmap_failure`）的**父提交**实现，而 serve 侧没有任何字段记录它跑的是哪版（`.mw/serve.meta` 只有 `pid`/`started_at_ms`/`code_dir`）。详见 §3 P3 与 §2.3。

---

## 1. 完整链路（逐节点 `path:line`）

### 1.1 生产者：谁创建 gate

唯一的创建者是 conductor（`gates.py:10-15` 角色声明；`CREATED_BY = "conductor"` `gates.py:84`）。**单一 choke point** = `_create_gate`（`conductor.py:3008-3051`）：取 `.mw/gates.lock` → `gates.create` → `_stamp_gate_defaults`（`expires_at = created_at+48h`、`default_action: escalate-to-human`）→ `snapshot_gate_created` → timeline `gate-created`。

| kind（闭合集 `GATE_KINDS` `gates.py:73-80`） | 生产点 |
|---|---|
| `stage-confirm` | `conductor.py:728-733`（`_create_stage_confirm_gate`）、`:662-667`（`_ensure_next_stage_gate` 分支） |
| `stage-close` | `conductor.py:906-912`（dossier 写完后） |
| `stalled` | `conductor.py:5311-5316`（`mark_stalled`，`conductor.py:5271`） |
| `budget-exhausted` | `conductor.py:1256-1260` |
| `goal-change` | `conductor.py:2919-2925`（`tick` 内**直连** `gates.create`，绕过 `_create_gate`，所以自己调 `_stamp_gate_defaults`） |
| `xkey-authorize` | `conductor.py:4058-4064` |
| review 类（`kind` 由调用方给） | `conductor.py:3710-3713` |

去重守卫是 `_gate_open`（`conductor.py:3137-3155`：`gate.kind != kind or gate.status != "pending"` ⇒ 只认 `pending`）——**被答但尚未被消费**的 gate 不算"已开"，这是 gate-0024 重复件的直接成因（§3 P9）。

### 1.2 判据：四个条件（纯函数，可注入 `now`）

`pending_gate_reminders`（`conductor.py:2526-2576`），docstring 自述 "Four conditions must hold together"（`:2535-2548`）：

```python
2558:    if any(_is_in_flight(row) for row in rows):      # 条件2：项目级整体抑制
2559:        return []
...
2560:        if n > max_reminders:                        # 条件3：cap
2561:            continue
...
2570:            if rank is not None and rank >= _STAGE_TERMINAL_RANK:   # 条件4
2571:                continue
2573:        if anchor is None or (now - anchor) < n * after_min * 60:  # 条件1：年龄
2574:            continue
2575:        due.append((gate, n))
2576:    return due
```

- 条件 1 锚点是 **gate 自己的 `created_at`**（不是 `expires_at`）：`:2569` `anchor = mw_common._gate_created_epoch(gate.created_at)`；`after_min` 默认 30 min（`conductor.py:2702`）。
- 条件 2：`_is_in_flight(row) = row.get("status","") not in mw_common._TERMINAL_STATUSES`（`conductor.py:2981-2982`），`_TERMINAL_STATUSES = {"done","failed","needs-clarification","lost"}`（`mw_common.py:168`）。
- 条件 3：`n = reminder_counts.get(gate.id, 0) + 1`（`:2559`）；`max_reminders = max(1, int(cfg.get("gate_reminder_max", 2)))`（`:2703`）。
- 条件 4：两级解析 —— `gate.stage` 优先，否则 `stage_of_key[gate.key]`（`:2565-2568`）；rank 表 `_STAGE_STATUS_RANK`（`:561-569`，`closed`/`closed-human`/`halted` = 2）、`_STAGE_TERMINAL_RANK = 2`（`:569`）。`stage_status`/`stage_of_key` 缺省 ⇒ 条件 4 **永不触发**（fail-open，`:2549-2558` docstring + 实装 `:2688-2695`）。
- 计数真值在台账不在 timeline：`_reminder_count`（`:2512-2520`）只数 `phase == "remind"` 且 `gate_id` 匹配的行；理由写在 `:2500-2506`（timeline 200 事件尾窗 ≈20 min ≪ 第二次提醒的 60 min 间隔，D-006）。
- 输入 `pending` 来自 `gates.pending_gates`（`gates.py:770-772`：`status == "pending"`）⇒ 被答的 gate 下一 tick 自动退出，零残留状态。

### 1.3 写入面（IO shell，只有两处）

`_remind_pending_gates`（`conductor.py:2683-2738`）：

```python
2687:    try:
2688:        pending = gates.pending_gates(gates_dir(project_root))
2689:    except gates.GateFormatError:
2690:        return                                        # ← 整个 gate 队列的提醒一起消失
2691:    if not pending:
2692:        return
2693:    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))
2694:    ledger = auto_decision_rows(project_root)
2695:    counts = {gate.id: _reminder_count(ledger, gate.id) for gate in pending}
2696:    stage_status, stage_of_key = _gate_stage_context(project_root, st)
...
2708:        _append_auto_decision_row(project_root, {          # 写入面 A：台账
2709:            "phase": _REMIND_PHASE, ...
2717:        st.timeline.append(                                 # 写入面 B：timeline
2718:            GATE_REMINDER_EVENT, ...
```

- 写入面 A：`.agenticdoc/_autopilot/auto-decisions.jsonl`，单写者 conductor（`conductor.py:6299-6331`）。
- 写入面 B：`.agenticdoc/_autopilot/timeline.jsonl`，事件名 `GATE_REMINDER_EVENT = "gate-reminder"`（`conductor.py:2508`），并在 `timeline.py:105` 的允许事件集里登记。
- **stderr：无。** 对比同文件的 roadmap 告警确有 stderr（`conductor.py:2617`），提醒没有 —— 这是 E1 的直接证据。

### 1.4 调用点（tick 步序）

`tick`（`conductor.py:2880-2966`）：
```
2886:    st.timeline.append("beat")                      # 1 先打点（liveness，disabled 也打）
2888:    cfg = _load_effective_config(project_root)
2890:    if not cfg["enabled"] or cfg["paused"]:
2891:        return "idle"                               # ← 2a：早退，2b 永不执行
2895:    _remind_pending_gates(project_root, st, cfg)    # 2b 提醒（放在 goal 检测之前）
2899:    _freeze_contract_first_sight(project_root, st, cfg)
...

2909:        st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}")
```

### 1.5 消费面（TS 侧，只读投递，不重判）

- `readGateReminders`（`pm-orchestrator.ts:1289-1330`）：整文件读台账，逐行 `JSON.parse`（torn 行跳过），只保留 `phase === "remind"` 且 `gate_id !== ""` 且 `reminder_n > 0` 的行（`:1305-1315`），映射为 `{seq, gateId, gateKind, gateKey, reminderN, detail}`。
- 投递（`:1466-1513`）：会话水位 `reminderWatermark`（`:1364`/`:1482`）按台账 `seq` 去重（`:1495-1496`），交付记录写进 session entry（`GATE_REMINDER_ENTRY_TYPE = "agent-team-loop:gate-reminder-seen"`，`:1283`/`:1502`），最后 `deliverPmAlert`（`ui-bridge.ts:172-182`，`pi.sendMessage(..., {triggerTurn:true})`）唤醒 PM。
- **两条静默丢弃**：`:1489 if (!watch.key) continue;` 与 `:1490-1491`（keyed gate 只投给 watch 该 key 的窗口）。
- TS 侧同时保留一个**独立重算的同一判据**用于面板：`blockedOnHuman(pendingGates, nonTerminalRows) = pendingGates > 0 && nonTerminalRows === 0`（`status-model.ts:1356-1357`），`monitor.ts:442` 调用、`:829` 渲染 `BLOCKED_ON_HUMAN`。

### 1.6 人对它的可见面（全清单）

| 面 | 位置 | 是否常驻/是否依赖事件 |
|---|---|---|
| PM 窗口 alert（`triggerTurn`） | `pm-orchestrator.ts:1508` | push，且要求有一个 watch 该 key 的活窗口（`:1489`） |
| `/autopilot timeline` | `console.ts:510-543` | 有界尾窗重放（beat 以外的事件），~15–20 min 后事件被挤出 |
| `BLOCKED_ON_HUMAN` 面板行 | `monitor.ts:829` | 仅 `blockedOnHuman && !tickStale`；`blockedOnHuman` 要求 `nonTerminalRows === 0` |
| `mw doctor` gates 段 `blocked_on_human` | `mw_common.py:3279`、文本行 `:3786` | pull；三轴（pending>0 ∧ 无在飞 ∧ tick 新鲜），tick 过期即不显示 |
| `mw doctor` 文本 `>24h` 提示 / `>72h` issue | `mw_common.py:3396`、`:3497-3499` | pull，阈值 24h/72h，晚于提醒的 30min/60min |
| `/autopilot gates` 卡片（13 行/gate，含 waited） | `console.ts:350-380` | pull，需人主动敲命令 |
| `mw autopilot gates [--json]` | `mw.py:3762` | pull |
| stderr `.mw/conductor.log` | — | **提醒不写**（只有 roadmap 告警写） |

⇒ 除"PM 窗口 push"外，全部是人主动拉取；**没有任何"现在有哪些门禁在等人、等了多久"的常驻行**（这正是 AC-001 要补的缺口）。

---

## 2. 历史证据（命令 + 原始输出 + 计数）

数据面：`H:\git\E2Feature\.agenticdoc\_autopilot\`（`auto-decisions.jsonl`、`timeline.jsonl` + `.1`/`.2`、`gates/gate-0001..0026.md`、`_roadmap.md`）+ `H:\git\E2Feature\.mw\`（`conductor.log`、`mw.log`、`serve.meta`、`launcher-beat.*`）。该项目的 mw 代码来自 `H:\git\Multi-Workers\packages\multi-workers`（`.mw/serve.meta` 的 `code_dir`）。

### 2.1 提醒总量与覆盖（命令 + 原文）

```powershell
Get-Content H:\git\E2Feature\.agenticdoc\_autopilot\auto-decisions.jsonl
```
原始输出（6 行；为排版把第 3 行截断）：
```
{"detail": "pending 683m >= 30m", "gate_id": "gate-0024", "gate_key": "", "gate_kind": "stage-close", "phase": "remind", "reminded_at": "2026-10-12T14:11:15Z", "reminder_n": 1, "seq": 1}
{"detail": "pending 683m >= 60m", "gate_id": "gate-0024", "gate_key": "", "gate_kind": "stage-close", "phase": "remind", "reminded_at": "2026-10-12T14:11:19Z", "reminder_n": 2, "seq": 2}
{"seq":3,"phase":"dispatch-alarm","kind":"out-of-scope","count":35,"detail":"feature-authorization-intake,..."}
{"detail": "pending 30m >= 30m", "gate_id": "gate-0025", "gate_key": "", "gate_kind": "stage-confirm", "phase": "remind", "reminded_at": "2026-10-12T14:41:33Z", "reminder_n": 1, "seq": 4}
{"detail": "pending 60m >= 60m", "gate_id": "gate-0025", "gate_key": "", "gate_kind": "stage-confirm", "phase": "remind", "reminded_at": "2026-10-12T15:11:29Z", "reminder_n": 2, "seq": 5}
{"detail": "pending 47m >= 30m", "gate_id": "gate-0026", "gate_key": "feature-api-contract-v2", "gate_kind": "stalled", "phase": "remind", "reminded_at": "2026-10-13T02:13:04Z", "reminder_n": 1, "seq": 6}
```
计数：**`phase:"remind"` 行 = 5**，涉及 gate-0024 / gate-0025 / gate-0026；另外 1 行是 `dispatch-alarm`。（注意 `seq` 是所有 phase 共用计数器，`remind` 行占了 seq 1,2,4,5,6。）

```powershell
Select-String -Path H:\git\E2Feature\.agenticdoc\_autopilot\timeline.jsonl -Pattern 'gate-reminder'
```
输出 5 行，与台账一一对应：
```
85070: 2026-10-12T14:11:15+00:00 seq=363139 gate-reminder key=4 stage=4 ... "gate-0024 stage-close pending 683m (reminder 1/2)" data{reminder_n:1, waited_s:40998, after_min:30}
85073: 2026-10-12T14:11:19+00:00 seq=363142 gate-reminder key=4 stage=4 ... reminder 2/2  data{reminder_n:2, waited_s:41002}
85458: 2026-10-12T14:41:33+00:00 seq=363527 gate-reminder key=5 stage=5 ... reminder 1/2  data{reminder_n:1, waited_s:1804}
85831: 2026-10-12T15:11:29+00:00 seq=363900 gate-reminder key=5 stage=5 ... reminder 2/2  data{reminder_n:2, waited_s:3600}
91663: 2026-10-13T02:13:04+00:00 seq=369732 gate-reminder key=feature-api-contract-v2 stage=null ... reminder 1/2 data{reminder_n:1, waited_s:2861}
```
当前 timeline 文件事件计数（同一命令族）：`gate-reminder` = 5、`gate-created` = 7、`gate-answered` = 12、`beat` = 92,056，文件跨度 `2026-10-06T21:00:32Z` → `2026-10-13T03:47:07Z`（9.85 MB，另有 `timeline.jsonl.1` 10,485,838 B / `timeline.jsonl.2` 10,485,775 B ⇒ **已轮转 2 次**）。

覆盖缺口（26 个 gate 逐一解析 `created_at`/`answered_at` 后排序）：`pending ≥ 30 min` 的 gate = **18** 个；其中**零 `remind` 行**的 = **15** 个（gate-0002/0003/0006/0009/0010/0011/0012/0013/0014/0015/0016/0017/0019/0022/0023）。前 10 长：

| gate | kind | pending 分钟 | remind 行 |
|---|---|---|---|
| gate-0019 | stage-close | 17,581（12 d 5 h） | 0 |
| gate-0023 | stage-close | 2,282（38.04 h） | 0 |
| gate-0014 | stalled | 1,044 | 0 |
| gate-0015 | stalled | 939 | 0 |
| gate-0024 | stage-close | 842（14.03 h） | 2 |
| gate-0009 | stalled | 832 | 0 |
| gate-0010 | stalled | 727 | 0 |
| gate-0011 | stalled | 662 | 0 |
| gate-0003 | stage-close | 361 | 0 |
| gate-0006 | stalled | 313 | 0 |

**关键限定**：提醒功能是 commit `ab546bb64`（`fix(coding-agent,agent): harden gate verdicts...`，**2026-10-11 18:12:00 +0800 = 2026-10-11T10:12:00Z**）引入的（`git log -S 'GATE_REMINDER_EVENT' -- packages/multi-workers/autopilot/conductor.py` 唯一命中）。E2Feature 在 4 个 conductor 会话里跑过（见 §2.3），其中**启动晚于该 commit 的只有两个**（`10-12T07:24:33Z`、`10-12T14:06:14Z`）。这两个会话内 pending 的 gate **只有 gate-0024 / gate-0025 / gate-0026**，且三个都有提醒行。⇒ **其余 15 个 gate 的零提醒不能归因于四条件**（功能尚不存在 / 进程未重启），RQ-1 的历史样本因此**只够给条件 3、4 的实例，给不出条件 1、2 的实例**。

### 2.2 四条件逐一

**(1) 年龄锚点 `created_at`，阈值 `n × after_min`**
- 正向：gate-0025 n=1 的 `waited_s=1804`（30.07 min）≈ 阈值 `30×60=1800`，触发点比阈值晚 4 s（tick 间隔）。
- 异常（重要）：gate-0024 的 n=1/n=2 间隔 **4 秒**（`waited_s` 40998 → 41002），因为 683 min 已同时越过 30 min 与 60 min 两条线 ⇒ "提醒节奏"完全丧失，配额在同一个分钟里烧光。
- 静默路径：`created_at` 不可解析 ⇒ `anchor is None` ⇒ `continue`，**无任何日志**（`conductor.py:2569-2571`）。
- 历史静默实例：0（条件 1 只造成延迟，不造成沉默）。

**(2) 无在飞行（项目级整体抑制）`conductor.py:2558`**
- 代码 + 单测证据完备：`test_autopilot_gate_reminder.py:284-320`（VC-010：`running` 抑制、`pending` 也抑制、`done/failed` 不抑制）。
- **生产可归因实例 = 0。** 我们做了反向验证：台账/`_workers.parallel` 现在有 749 行，其中非终态只有 1 行 `ap-feature-domain-skeleton-003-attribution-coverage-domain-table | running | ... disp=2026-10-13T03:42:56Z`；而**所有** `disp < 2026-10-12T16:49:32Z` 的行，其 `updated_at` 最大值是 `2026-10-10T12:45:16Z`（`ap-feature-phaseb-closeout-l3-a1 | done`）⇒ 自 `10-10T12:45:16Z` 起到 `10-12T16:49:32Z` 之间既无新派发（timeline 无 `dispatch` 事件）也无未终态行 ⇒ **条件 2 在那 52 小时里不成立**。也就是说：gate-0023 / gate-0024 的长时间静默**不是**条件 2 造成的。（命令：解析 `_workers.parallel` 的 `[status, dispatched, updated]` 三列后排序取极值。）
- ⇒ 条件 2 目前只有代码级与单测级证据，**没有生产实例**（`_workers.parallel` 是就地覆盖的状态面，不保留历史，无法回放）。

**(3) cap 用尽 ⇒ 永久沉默**
- gate-0026：只有 n=1（`02:13:04Z`，47 min），14.2 min 后被 reject（`02:27:14Z`），从未到 n=2。
- gate-0024：n=1/n=2 在 4 秒内用尽 ⇒ 之后静默 **158.3 min**（`14:11:19Z` → `16:49:36Z` 被答）。
- gate-0025：n=1/n=2 间隔 29.9 min ⇒ 之后静默 **98.0 min**（`15:11:29Z` → `16:49:29Z` 被答）。
- 闭区间硬证据：
```powershell
git grep -n 'gate_reminder_max' -- packages/multi-workers/autopilot/config.py packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts
packages/multi-workers/autopilot/config.py:57:    gate_reminder_max   int    2    (1..2; ... Bounded at 2 by design D-007 so a config can
packages/multi-workers/autopilot/config.py:103:    "gate_reminder_max": 2,
packages/multi-workers/autopilot/config.py:134:    "gate_reminder_max": (1, 2),
packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:152:	gate_reminder_max: 2,
packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:191:	gate_reminder_max: [1, 2],
```
  另有镜像一致性测试 `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` 与 Python 侧 `test_autopilot_config.py:167/:197/:225/:240`（区间闭包断言 `== (1, 2)`），以及文档 `packages/multi-workers/README.md:234`（"每门最多提醒次数（1..2）"）。
- 语义强化：计数落在台账 ⇒ 重启进程也**不会**重置 cap（`_reminder_count` 读 append-only 台账）。

**(4) stage 终止抑制 —— 唯一可归因的生产实例**
- 事实链（全部可复核）：
  1. `gate-0023`（stage-close，stage=4）与 `gate-0024`（stage-close，stage=4）的 `question` **逐字相同**；`gate-0023` 的 `answered_at = 2026-10-12T02:47:55Z`、`consumed_at = 02:48:01Z`；`gate-0024.answered_at = 2026-10-12T16:49:36Z`。
  2. timeline 原文：`02:47:57Z gate-created gate-0024 kind=stage-close` → `02:48:01Z gate-answered gate-0023 approved → stage 4 closed` → `02:48:01Z stage-close stage 4 closed (gate-0023 approved)`。
  3. `_roadmap.md` 当前 Stage 4 段（第 53 行起）带 `status: closed`；`_STAGE_STATUS_RANK["closed"] = 2 = _STAGE_TERMINAL_RANK` ⇒ 对 `stage=4` 的 gate-0024，条件 4 自 `02:48:01Z` 起恒为真。
  4. 然而 gate-0024 的提醒发生在 `14:11:15Z`/`14:11:19Z`（**之后**）—— 唯一可能是 `stage_status` 为 `None`：同一 tick 的 timeline 里有 `14:11:15Z config ... "roadmap unreadable: line 87 (stage 5): keys table row must have 3 columns ... got 4: [...]"`，stderr 有 `[conductor] gate reminders: roadmap unavailable, stage-terminal suppression disabled this tick: line 87 (stage 5): ...`。两处都是 fail-open 分支（`conductor.py:2688-2695` 返回 `(None, None)`）。
  5. **07:24:33Z 会话内 6.78 h 零提醒的归因闭合**：条件 2 不成立（步骤见上，队列零非终态行）、条件 3 不成立（count=0）、条件 1 不成立（4.6–11.3 h ≫ 60 min）⇒ 只可能条件 4。且 roadmap 在那段时间必须**可读**（否则运行中的旧版实现在该路径上每 tick 都会 print + append，见 P3；实际上只有 3 条）。
- 计数：**条件 4 的确认实例 = 1（gate-0024，6.78 h）**；由于 cap 先被烧光，条件 4 的**持续**压制无法在台账上与条件 3 区分（这正是"cap 掩盖"效应：两个封顶机制叠加时，只有先到的那个留痕）。

### 2.3 会话/部署时间线（"旧代码继续跑"与"最长静默"的对照）

`goal-snapshot` 事件 = conductor 进程启动时写一次（`conductor.py:7242`）。当前 timeline 里共 4 条：
```
2026-10-09T07:21:13Z seq=318799   (本地 10-09 15:21:13)
2026-10-10T06:27:54Z seq=331519   (本地 10-10 14:27:54)
2026-10-12T07:24:33Z seq=358157   (本地 10-12 15:24:33)
2026-10-12T14:06:14Z seq=363074   (本地 10-12 22:06:14)  ← 当前进程
```
与 `.mw/launcher-beat.<pid>` 的 `CreationTime` 一一对应（`Get-ChildItem .mw/launcher-beat.* | Sort CreationTime`：`126800`=10-10 14:27:54、`163304`=10-12 15:24:33、`162008`=10-12 22:06:14、`88924`=10-12 22:06:14 起持续心跳）。`git log -1 --format='%ai' ab546bb64` = `2026-10-11 18:12:00 +0800`。

⇒ `gate-0023` 的 38.04 h 静默（`10-10T12:45:38Z → 10-12T02:47:55Z`）**整段落在** `10-10T06:27:54Z` 启动的会话内，而该会话启动早于功能提交 `10-11T10:12:00Z` 21.2 h ⇒ 结构上不可能产生提醒。这是 **P-04「Python 侧改动需重启 serve 才生效」造成静默的直接实例**。

对照：即使进程在 功能提交之后启动（`07:24:33Z` 会话），`gate-0024` 仍零提醒 6.78 h ⇒ 归因于条件 4（§2.2(4)）；`14:06:14Z` 会话启动后 **5.0 min** 才发出第一条提醒（`14:06:14Z → 14:11:15Z`），那 5 分钟里 roadmap 可读、条件 4 有效。

### 2.4 tick 存活性（"tick 停摆"路径的实测）

```powershell
# 逐 beat 求相邻间隔
$lines = Get-Content H:\git\E2Feature\.agenticdoc\_autopilot\timeline.jsonl
... '"ev": "beat"' -> parse '"ts": "([^"]+)"' -> 差值统计
beats: 92061 ; gaps>180s: 0 ; gaps>1800s: 0 ; max gap = 19s (2026-10-10T11:08:03→11:08:22 本地)
```
⇒ 在当前 timeline 覆盖的 6.6 天里，**tick 从未停摆超过 19 秒**，4 次 serve 重启都只造成秒级间隙。⇒ 本 key 的历史事故**不是** tick 停摆造成的，而是"tick 正常跑 + 判断结果沉默"。

---

## 3. 会让提醒"永久静默"的路径（穷举）

> 标注：【已实测发生】/【代码可证，历史未见实例】

- **P1 tick 停摆 / conductor 进程死亡**【代码可证】提醒只在 `tick` 的 step 2b（`conductor.py:2895`）执行；没有 tick 就没有提醒，也没有任何"我活着但没在提醒"的自证字段。当前窗口未发生（§2.4）。`mw doctor` 的第三轴（`mw_common.py:3279-3300`，`_conductor_tick_fresh`）能事后发现，但需要人主动跑。
- **P2 `enabled=false` / `paused=true`**【代码可证，不可事后归因】`tick` step 2 在 2b **之前** return `"idle"`（`conductor.py:2890-2891`），且 **enable/pause 切换不写任何事件**（全仓无对应 timeline 事件类型）。⇒ 一旦出现，事后无法从记录区分"被 pause"与"被条件 2/4 抑制"。本项目 `config.json`（mtime 本地 10-09 15:18:28）为 `enabled:true, paused:false`，且机器层只允许覆盖两个 `xkey_verify_*` 键（`effective_config.py:30-39`、`:61-67`）⇒ 本实例可排除，但该路径本身的不可归因性成立。
- **P3 进程活着但跑旧代码**【**已实测发生**】。证据：E2Feature 的 stderr 原文 `[conductor] gate reminders: roadmap unavailable, stage-terminal suppression disabled this tick: line 87 (stage 5): ...`（`.mw/conductor.log`，3 行，mtime 本地 10-12 22:11:24）与 timeline 原文 `config ... "roadmap unreadable: line 87 (stage 5): ..."`（3 条）**逐字**等于 `b65380d1b^` 的实现：`git show b65380d1b^:packages/multi-workers/autopilot/conductor.py` 中 `_gate_stage_context` 的 `print("[conductor] gate reminders: roadmap unavailable, ...")`（父版 2587-2592）与 `orchestrate` 的 `st.timeline.append("config", detail=f"roadmap unreadable: {exc}")`（父版 237）。而 `b65380d1b`（引入 `_ROADMAP_ALARM_SEEN` 去重 + `_emit_roadmap_failure` 双通道，`conductor.py:2591-2637`）提交于 **2026-10-13T03:19:28Z**，晚于该进程启动（`2026-10-12T14:06:14Z`）13.1 h。**两侧都没有任何字段记录进程实际运行的 commit**（`.mw/serve.meta = {"pid":..., "started_at_ms":..., "code_dir":...}`；`.mw/mw.log` 只记 `conductor spawned (PID ...)`）⇒ "旧代码继续跑"这类故障在记录里不可见、不可自证。
- **P4 条件 2 项目级整体抑制**【代码+单测可证】`conductor.py:2558`。任意 key 的任意非终态行（含 conductor 自己的 `_scratch-*` 行）会静音**所有** gate，包括与该 key 无关的 gate。长任务是常态（本项目 `_workers.parallel` 749 行、713 done / 34 failed / 1 pending / 1 needs-clarification）。
- **P5 条件 3 cap**【**已实测发生**】`conductor.py:2563` + `config.py:134` 闭区间 `[1,2]` ⇒ 第 3 次不可能。实测 gate-0024 用 4 秒烧光后静默 158.3 min；gate-0025 静默 98.0 min。**配置只能调小不能调大**（`_INT_RANGES`），且计数在 append-only 台账 ⇒ 重启无效。
- **P6 条件 4 stage 终止抑制**【**已实测发生**】`conductor.py:2570`。gate 所属 stage 一旦落 `closed/closed-human/halted`，该 gate 永久不再提醒（stage 不可回归，rank 2 是吸收态）。实测 gate-0024 被压制 6.78 h；其成因是重复 stage-close 件（见 P9）。
- **P7 条件 1 的锚点坏**【代码可证】`created_at` 不可解析或为未来时间 ⇒ `continue`，**无日志、无事件**（`conductor.py:2569-2571`，`:2573-2574`）。这是纯静默失败（不是"降级可见"）。
- **P8 gate 队列任一文件损坏 ⇒ 全部提醒一起消失**【代码可证】`gates.enumerate` 只要有一个 gate 文件解析失败就抛 `GateFormatError`（`gates.py:744-767`，含 id/文件名不一致），`pending_gates` 透传（`:770-772`），`_remind_pending_gates` 静默 `return`（`conductor.py:2687-2690`）。同时 `_gate_open`（`:3137`）与 `gates.enumerate` 的所有消费者一起失效。附带效应：`orchestrate` 的 `_consume_answered_gates` 失败会提前 return（父版 `:221-222`），使同 tick 的后续逻辑（含 stage 状态推进）一并跳过。
- **P9 "已答未消费"竞态 ⇒ 重复 gate ⇒ 永久孤儿**【**已实测发生**】`_gate_open` 只认 `status == "pending"`（`conductor.py:3137-3155`）。人把 `status` 改成 `approved` 后、`orchestrate` 消费前的窗口内，`_stage_close` 的守卫（`:888-889`）判为"无开 Gate"，于是又建一个同 stage 同 kind 的 gate。E2Feature 实证：`gate-0023` 被答 `02:47:55Z` → 2 秒后建 `gate-0024` → 4 秒后才消费 `gate-0023`（stage 4 closed）。重复件 `gate-0024` 因 stage 已终态而被条件 4 永久静音，且**人永远不会主动去答**它（它挂了 14.03 h，直到人顺手批掉）。同一型事故在 `reflect/gate-replay-after-timeline-rotation.md` 有另一实例（gate-0019/0020，timeline 轮转导致已答 gate 的消费记录丢失）。
- **P10 台账 `seq` 由"可解析行数 + 1"导出 ⇒ 水位去重可被永久破坏**【代码可证】`_append_auto_decision_row`（`conductor.py:6321-6331`）：`rows = auto_decision_rows(...)`（`:6299-6311`，**跳过**不可解析行与非 dict 行）→ `payload.setdefault("seq", len(rows) + 1)`。一行 torn/损坏 ⇒ 后续 `seq` 重复或回退。TS 侧投递水位就是 `seq`（`pm-orchestrator.ts:1495-1496`：`if (reminder.seq <= reminderWatermark) continue;`）⇒ 重复/回退的 `seq` 会让后续真实提醒被永久判为"已投递"。
- **P11 消费端静默丢弃**【代码可证】`pm-orchestrator.ts:1489 if (!watch.key) continue;` + `:1490`（keyed gate 只投给 watch 该 key 的窗口）⇒ 没有任何窗口 watch 时，提醒**只进台账、不达任何人**。`deliverPmAlert` 还需要一个活着的 pi 窗口（`ui-bridge.ts:172-182`，`triggerTurn` 只对已存在的会话有效）。本项目 5 条提醒全部是**无 key 的 stage 级 gate**（`gate_key: ""`），正好落在需要水位而非 key 匹配的分支。
- **P12 timeline 是 10 MB × 3 的有界环 ⇒ 事件会被挤出**【**已实测发生轮转**】`ROTATE_THRESHOLD_BYTES = 10*1024*1024`、`ROTATE_GENERATIONS = 2`（`timeline.py:119-120`；实证 `timeline.jsonl.1` = 10,485,838 B、`.2` = 10,485,775 B）。读取端一律有界：`tail_events(limit=400, max_bytes=512*1024)`（`timeline.py:472-476`）、`conductor._timeline_has_event(limit=200)`（`conductor.py:1906-1908`）、TS `readTimelineTail(maxBytes=512KB, limit=400)`（`monitor.ts:461-476`）。beat 间隔 ~4.5 s ⇒ **200 事件 ≈ 15 min**。⇒ `gate-reminder` 事件在 ~15–20 min 后从所有有界读法里消失（台账行仍在；投递读台账所以不受影响，受影响的正是"事后回看事件/人肉核对"）。同时轮转本身会破坏依赖 timeline 的消费凭据（见 P9 的 gate-0019/0020 实例）。
- **P13 可见面本身有同一盲区**【代码可证】`BLOCKED_ON_HUMAN` 行只在 `s.blockedOnHuman && !a.tickStale` 时渲染（`monitor.ts:829`），而 `blockedOnHuman` 要求 `nonTerminalRows === 0`（`status-model.ts:1356-1357`）⇒ **有 worker 在飞时，pending gate 在面板上也看不见**（与 P4 同源）；tick 一停，该行也消失（观测面与事件面同生共死）。`mw doctor` 的三轴 `blocked_on_human`（`mw_common.py:3279-3300`）同样要求 tick 新鲜，且必须人主动跑。
- **P14 任何"事件面"修复都会被 P5 吃掉**【结构性结论】cap 计数是持久的、判据是纯的、发射是不可逆的：一旦 `max_reminders` 次发射发生，该 gate 在其剩余生命周期内**不可能**再产生任何提醒事件（无论进程重启、roadmap 修复、worker 全部退出）。⇒ 修复必须落在**状态读取**上（AC-001），不能只在事件面加退避/重试。

---

## 4. 上下文来源清单（读过哪些文件的哪些行）

**A. `H:\git\Multi-Workers`（HEAD `cc9a46a1a`）**
- `packages/multi-workers/autopilot/conductor.py`：`:183-198`(ConductorState/open_goal_change_gate)、`:204-250`(orchestrate 入口)、`:561-583`(stage rank)、`:662-667`/`:725-733`(stage-confirm 生产)、`:888-912`(stage-close 生产)、`:1256-1260`(budget-exhausted)、`:2270-2290`? 无、`:2500-2576`(G2 声明 + `_reminder_count` + `pending_gate_reminders` 全文)、`:2576-2637`(roadmap 告警封装 `_ROADMAP_ALARM_SEEN`/`_emit_roadmap_failure`/`_emit_roadmap_warnings`)、`:2643-2676`(`_gate_stage_context`)、`:2683-2738`(`_remind_pending_gates` 全文)、`:2880-2966`(`tick` 全文)、`:2981`(`_is_in_flight`)、`:3008-3051`(`_create_gate` 全文)、`:3137-3155`(`_gate_open` 全文)、`:3396-3428`(48h 默认 TTL / `_review_deadline`)、`:3710-3713`(review gate)、`:4058-4064`(xkey-authorize)、`:5271-5316`(`mark_stalled`)、`:6299-6331`(`auto_decision_rows` / `_append_auto_decision_row`)、`:7242`(goal-snapshot 启动事件)
- `packages/multi-workers/autopilot/gates.py`：`:1-60`(角色/schema 文档)、`:73-90`(GATE_KINDS/GATE_STATUSES/schema 版本)、`:141-153`(frozen 6 字段)、`:744-772`(enumerate/pending_gates)
- `packages/multi-workers/autopilot/config.py`：`:45-59`(docstring)、`:95-134`(DEFAULT_CONFIG 与 `_INT_RANGES`)
- `packages/multi-workers/autopilot/timeline.py`：`:14-28`(rotation 契约)、`:105`(允许事件集)、`:119-120`(10MB × 3)、`:290-419`(append/rotate/_ensure_tail_terminated)、`:422-520`(query_events/tail_events)
- `packages/multi-workers/autopilot/effective_config.py`：`:1-39`、`:61-73`(机器层只可覆盖两个键)
- `packages/multi-workers/mw_common.py`：`:168`/`:1876`/`:2267`(`_TERMINAL_STATUSES`)、`:3211-3300`(C8 三轴 `blocked_on_human` + `_conductor_tick_fresh`)、`:3340-3380`(gates section 组装)、`:3383-3400`(`_gates_text_alerted`)、`:3484-3501`(缺字段/等待时长告警)、`:3786-3792`(`gates:` 文本行)
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`：`:125`/`:129`/`:151-152`/`:190-191`/`:322-323`/`:348-349`/`:380-381`(config 镜像)、`:638-640`+`:930-931`(GATE_KINDS 校验)、`:1077`(事件白名单)、`:1347`(TERMINAL_WORKER_STATUSES)、`:1356-1357`(blockedOnHuman)
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`：`:436-455`(gates 采集 + `blockedOnHuman` 计算)、`:461-476`(readTimelineTail 有界读)、`:818-835`(BLOCKED_ON_HUMAN 渲染)
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`：`:340-380`(`/autopilot gates` 卡片)、`:505-543`(`/autopilot timeline`)
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`：`:1258-1330`(GateReminder 类型 + `GATE_REMINDER_ENTRY_TYPE` + `readGateReminders`)、`:1352-1367`(水位初始化)、`:1466-1513`(投递分支全文)、`:1562`(无 key 窗口的行为)
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：`:166-187`(`deliverPmAlert`/`deliverWorkerResult`)
- `packages/multi-workers/test_autopilot_gate_reminder.py`（全文，340 行）：四条件单测 + VC-007..VC-010 + `test_third_reminder_blocked_after_timeline_tail_eviction`（`:245-272`，260 个 beat 挤出 200 事件尾窗）
- `packages/multi-workers/test_autopilot_config.py`：`:116-132`、`:166-167`、`:187-197`、`:219-249`（区间闭包断言）
- `packages/coding-agent/test/suite/autopilot-config-parity.test.ts`（存在性 + 用途）、`packages/coding-agent/test/suite/autopilot-console.test.ts:910-950`/`:1266-1270`（20 键与镜像）
- `packages/multi-workers/README.md:233-234`（配置表）、`packages/multi-workers/CHANGELOG.md:69`/`:74`（提醒功能与 20 键的落地记录）
- git 考古：`git log -S 'GATE_REMINDER_EVENT'`（→ `ab546bb64`，`2026-10-11 18:12:00 +0800`）、`git log -S '_ROADMAP_ALARM_SEEN'` / `-S 'def _emit_roadmap_failure'`（→ `b65380d1b`，`2026-10-13 11:19:28 +0800`）、`git show b65380d1b^:packages/multi-workers/autopilot/conductor.py`（父版 237、2587-2592）、`git log --oneline -- conductor.py`、`git status --porcelain`

**B. `H:\git\E2Feature`（只读）**
- `.agenticdoc/_autopilot/auto-decisions.jsonl`（6 行全文）、`timeline.jsonl`（92,400 行；全部非 beat 事件逐条读完，含 seq 278070-370505 的窗口）及 `.1`/`.2` 的大小与 mtime
- `.agenticdoc/_autopilot/gates/gate-0001..0026.md`（26 个文件的 frontmatter 全字段解析；逐字读了 gate-0023.md、gate-0024.md）
- `.agenticdoc/_autopilot/config.json`、`_roadmap.md`（Stage 1-5 段与 Stage 4 的 `status: closed`；当前共 83 行）
- `.agenticdoc/_workers.parallel`（749 行，解析 status/dispatched/updated 三列做时间窗与在飞判定）、`.agenticdoc/_workers.acked`（存在性）
- `.mw/conductor.log`（3 行，逐字比对父版实现）、`.mw/mw.log`（serve/conductor spawn 记录）、`.mw/serve.meta`、`.mw/conductor.pid`、`.mw/launcher-beat.*`（15 个文件的 CreationTime/LastWriteTime）、`.mw/launcher.log`
- `.agenticdoc/_autopilot/reflect/pm-gate-idle-no-alert.md`（**提醒功能的原始动因文档**：gate-0006 静默 5.2 h、gate-0009/0010/0011 静默 ~10.8 h、累计 ~14 h；明确要求"同一 gate 最多提醒 2 次"——即 cap=2 的来源）、`reflect/gate-replay-after-timeline-rotation.md`（gate-0019 12 天 pending + timeline 轮转导致消费记录丢失 + gate-0019/0020 重复件）、`reflect/monitor-frozen-after-mw-restart.md`（观测面冻结撒谎）、`reflect/README.md`、`reflect/` 目录清单

**C. 工具侧观察（供 spec 参考）**：本项目存在 agent 侧写面守卫 `xkey-gate-guard`，会拦截"write 构造 + `.agenticdoc/_autopilot/**` 路径"同现的 bash 调用（本次取证中被误伤一次，命令目标其实是临时目录）；另有 worker 级 `write-scope` 守卫。⇒ 自动化代理**不能**写 autopilot 状态面，这一点与 P-01/AC-003 的"只用既有通道"一致。

---

## 5. 未覆盖面声明

1. **条件 1 / 条件 2 没有生产实例，且无法补足。** 原因：提醒功能 2026-10-11T10:12Z 才提交，而"能被功能覆盖"的 pending 窗口里只有 3 个 gate（都有提醒）；更早的 15 个零提醒 gate 属"功能未部署"，不能算条件 1/2/4 的实例。且 `_workers.parallel` 与 `_roadmap.md` 都是**就地覆盖**的状态面，不保留历史 ⇒ 无法回放"某 tick 是否被抑制"。本报告对条件 2 的判定是**反向排除**（证明那 52 小时里队列零非终态行），不是正向实例。
2. **07:24:33Z 会话内 6.78 h 静默的归因是推理链，不是直读。** 依赖两个已验证前提（a）运行版本 == `b65380d1b^`（逐字比对）（b）父版在这条路径上没有去重 ⇒ roadmap 当时可读。若未来发现该进程实际是另一版中间态实现，则该归因需重审；本报告已把两个前提的行号/原文全部给出，便于复核。
3. **`_roadmap.md` 在 `14:11:15Z`–`14:11:24Z` 变坏、并在 `14:11:29Z` 前恢复的具体写入方没有查到**（无 audit：roadmap 修复不写事件，写者可能是人类/另一个 pi 会话/PM）。我只验证了时序（前一 tick 可读 → 3 个 tick 不可读 → 恢复）与现状（83 行、无 line 87）。
4. **`_roadmap.md` 历史内容不可回溯**：`H:\git\E2Feature` 的 `.agenticdoc/_autopilot/_roadmap.md` 是否被 git 跟踪/其历史版本未核（本次未做 `git log -- _roadmap.md`），因此"line 87 的 4 列行何时被删除"无法定论。
5. **未覆盖 `H:\git\Multi-Workers` 自身的 `_autopilot` 数据面**：该仓库 `.agenticdoc/_autopilot/` 只有 `auto-decisions.jsonl`（5 行，全部 `dispatch-alarm`，无 `remind` 行）且**没有 `gates/` 目录**（`Test-Path` = False）⇒ 本项目从未产生 gate，无历史提醒可考。其 `.mw/conductor.log` = 0 字节。
6. **未做代码执行验证**（不写测试、不跑 conductor）。四条件的语义结论来自源码 + 既有单测（`test_autopilot_gate_reminder.py`）的交叉印证，未新增运行证据。
7. **未覆盖其他项目实例**：除 `H:\git\E2Feature` 外未搜索机器上其他 mw 项目的 `.agenticdoc/_autopilot`（时间盒内只取了一个有长期运行史的实例）。
8. **PM 侧投递的"实际是否送达人"未核**：`grep` 确认了代码路径，但 5 条提醒是否真的触发了 PM 窗口 alert / 用户是否看到，没有会话侧证据（`pi` session entry 不在本任务可读面内）。
9. **行号约定差异**：`conductor.py` 含 3 处孤立 `\r`，`Get-Content` 索引法给出的行号比 `git grep`/`Select-String` 少 ≤3。本报告统一用后者（与任务卡种子的 `:2558` 一致）。
