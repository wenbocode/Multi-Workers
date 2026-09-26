# Research: 交叉核对 —— 槽位占用判定（PM 独立裁定）

## 决策问题

spec draft **AC-001** 要求"另有一份笔记做**独立交叉核对**并报告差异"。本笔记裁定两份 spec 期笔记在 (c) 的**前提事实**上的**直接矛盾**，并以 PM 亲读代码 + 现场实测固化为判据：

- RQ-1（`spec-concurrency-anchors-20260926.md`）结论：`stalled_row_keeps_slot = true`。
- RQ-4（`spec-slot-change-space-20260926.md`）结论：`key-status=stalled` 的 key **不占槽**。

两者不可能同时为真（除非 stalled key 恰好没有残留行）。这是 (c) 是否值得修的前提，必须在 spec 锁定前裁定。

## 调研方法与出处

1. **PM 直接读取代码**（非二手转述）：
   - `packages/multi-workers/autopilot/conductor.py:224-229`（`deps_of` 构造）
   - `packages/multi-workers/autopilot/conductor.py:258-264`（`in_flight_keys` 构造）
   - `packages/multi-workers/autopilot/conductor.py:274`、`:284-290`（派发循环的跳过与 cap 判定）
   - `packages/multi-workers/autopilot/conductor.py:2131-2138`（`_is_in_flight` / `_row_belongs_to`）
2. **现场实测**：运行 `.tmp/msc-slot-occupancy-check.py`（格式按 `mw_common.parse_workers_file`，`:1444-1465`；按 key 去重口径复刻 `_row_belongs_to`），于 2026-09-26 读取 MW/FM/E2 三个项目的 `_workers.parallel` 与 `_autopilot/config.json`。

## 发现

### F1【事实】`in_flight_keys` **没有任何 key-status 过滤** —— 它只看队列行

代码原文（`conductor.py:224-229`）：

```python
    deps_of: dict[str, tuple[str, ...]] = {}
    status_of: dict[str, str] = {}
    stage_of: dict[str, int] = {}
    for stage in rm.stages:
        for entry in stage.keys:
            deps_of[entry.key] = entry.depends_on      # ← 所有 stage 的所有 key
```

⇒ `deps_of` 覆盖 roadmap 里的**每一个** key，与 key-status 无关。

代码原文（`conductor.py:258-264`）：

```python
    in_flight_keys = {
        key
        for key in deps_of
        if any(
            _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
        )
    }
```

⇒ 集合成员判定 = 「该 key 存在任一非终态行」；**没有** `status_of` 参与。

代码原文（`conductor.py:2131-2132`）：

```python
def _is_in_flight(row: dict) -> bool:
    return row.get("status", "") not in mw_common._TERMINAL_STATUSES
```

⇒ 非终态 = `status not in {done, failed, needs-clarification}` ⇒ **`pending` 也算**（与 RQ-1 一致）。

### F2【事实】`:274` 的 stalled 跳过发生在 cap 计数**之后**，只影响"是否给这个 key 派新活"

代码原文（`conductor.py:274` 与 `:284-290`，同一循环内，按出现顺序）：

```python
            if status_of.get(key) in ("done", "stalled", "closed-legacy"):
                continue                                   # ← 只是跳过派发
            ...
            if key in in_flight_keys:
                continue  # wait for the in-flight worker
            if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):
                continue  # parallel cap — key starts on a later tick   # ← cap 已把该 key 数在内
```

⇒ 一个 key-status 为 `stalled` **且**有非终态行的 key：不会被派发（`:274`），但**已经**被计入 `in_flight_keys`（`:258-264`），因此**占用 cap 名额**（`:289`）。

### F3【事实】裁定：RQ-1 正确，RQ-4 的该项结论错误

- RQ-4 的推理链是"`:274` 跳过 stalled ⇒ stalled 不占槽"。该推理遗漏了**执行顺序**（`:274` 在 `:258-264` 之后）与**无状态过滤**这一事实（F1）。
- RQ-4 的另一半是对的且重要：**"进程已死但行仍非终态"**这种情形下，key **不会**被标成 stalled（`_advance_key` 见 in-flight 直接 return，早于 `mark_stalled` 调用点），所以它也不会走 `:274` 的跳过分支——它占着槽且不被任何机制标记。RQ-4 观察到的**现象**与 RQ-1/RQ-5 的**机制**并不冲突。
- **精确规则（比两份笔记都强）**：**cap 只看 `_workers.parallel` 的行状态，与 key-status 完全无关**。由此推出三态占槽：

| key-status | 是否被派发新活 | 有非终态行时是否占槽 |
|---|---|---|
| `stalled` / `closed-legacy` | 否（`:274`） | **是**（RQ-1 正确） |
| `done` | 否（`:274`） | **是**（两份笔记均未指出，本笔记补充） |
| 正常在飞 | 否（`:285`，等行终态） | 是（本来就应该） |

- 去重：`in_flight_keys` 按 **key** 去重 ⇒ 一个 key 无论 1 行还是 6 行只吃 **1** 个槽（现场实测 F4 的 MW 行即证）。

### F4【事实】现场实测（2026-09-26，`.tmp/msc-slot-occupancy-check.py`）

| 项目 | `max_parallel_keys` | 行总数 | 非终态行 | `in_flight_keys`（去重） | 实况 |
|---|---|---|---|---|---|
| FM `E:\CLI_workspace\FeatureMigrator` | 2（config.json **显式**） | 232 | 2 | **2** | 两行均 `running`，`updated` 1 / 3 分钟前 ⇒ 活进程，cap 打满，各属不同 key |
| E2 `H:\git\E2Feature` | 2（显式） | 485 | 1 | 1 | 1 行 `running`，4 分钟前 |
| MW `H:\git\Multi-Workers` | 缺键 ⇒ 默认 2 | 179 | **5** | **1** | 5 行全属 `mw-autopilot-slot-capacity`（本 key 的 5 张 research 卡） |

复算方式：`python -X utf8 .tmp/msc-slot-occupancy-check.py`（只读；格式 = `mw_common.parse_workers_file` 的管道分隔 7/8 列）。

**结论（容量论据）**：该时刻本机同时运行 **8** 个 worker 进程（FM 2 + E2 1 + MW 5），无任何容量告警 ⇒ **(d) 不是机器容量问题**（与 RQ-1 的反证范围、本 key 的 6 张并行 research 卡互为独立证据）。同时：MW 侧 5 行同 key 只吃 1 个槽 ⇒ **面板的 `slotsUsed`（数行）与 cap 的 `in_flight_keys`（数 key）口径不同**，见 RQ-7。

### F5【推断】等待时长上界（由 F1+F2 推出，待 RQ-6 实测）

一个"进程已死 + 行仍非终态"的 key 会持续占槽，直到下列之一发生：worker 墙钟超时（`PI_WORKER_TIMEOUT_MS`，默认 60 分钟）、活动看门狗（`PI_WORKER_IDLE_MS`，默认 10 分钟，需进程仍活着才能触发）、或 launcher 孤儿静默窗（`PI_WORKER_ORPHAN_DEAD_MIN`，默认 **90 分钟**）。每条的具体生效条件与代码锚点属 RQ-6 的取证范围，本笔记不重复。

### F6【事实】频率修正（RQ-3 数据回填，2026-09-26）

F3 的规则是**代码路径**结论；RQ-3 的实测（`spec-slot-utilization-20260926.md`）给出了**频率**：stalled key 与"它自己的 worker"的时间重叠 **FM 0.00h / E2 0.04h（2.5 min）**，窗口 70.47h / 100.00h ⇒ **stalled key 实际几乎从不持有非终态行**。

两者不矛盾，而是互补：

- 代码允许"stalled + 残留非终态行 ⇒ 占槽"（F1/F2，路径可达）；
- 但 stall 的成因路径使它几乎不可能发生：stall 由"连续 advance 失败"触发，而 `_advance_key` 在发现同 key 有 in-flight 行时**直接 return**（不计失败）⇒ 被标 stalled 的 key 在那一刻通常**本来就没有**非终态行。

⇒ **对 §4 风险 1 的措辞修正**：占槽的真实残余风险是「**孤儿行**」（进程已死、行仍非终态、最多 90 分钟静默窗），**不是**「stalled key 占槽」。合并口径：

1. **占槽判定 = 存在非终态行（与 key-status 无关）**（F1）；
2. **该判定被 stalled 状态触发的频率 ≈ 0**（RQ-3）；
3. 尚有实际影响的是死进程残留行（待 RQ-6 量化）。

RQ-1 的 `stalled_row_keeps_slot=true` 是**路径可达性**结论，RQ-3 的 `stalled_slot_pct≈0` 是**频率**结论；两者都对，**不能只引一个**。

## 结论 → 决策映射

1. **spec AC-004 的措辞必须改**：原文写"stalled key 是否计入 in-flight"。路径判定已给出「是」但频率 ≈ 0（F6）⇒ 判据应改为「占槽规则的代码锚点（按行状态、与 key-status 无关）+ 三类状态（stalled / done / 在飞）占槽表 + **频率实测**（stalled 占槽占比、孤儿行占槽占比）」——只写路径会**高估** (c) 的槽位收益。
2. **spec §4 风险 1 重新命名**：不是"stalled key 占槽"，而是「**孤儿行占槽**」（主）与「残留非终态行占槽」（一般规则，含 done/stalled）。
3. **对 RQ-4 的 M1/M2 收益判断有影响**：(c) 的**槽位侧**修法不是"提 cap"（把 cap 提到 4 只是把"1 个孤儿行吃掉 1/2 槽"稀释成"1/4"）；**缩短孤儿静默窗 / 让 conductor 参与行存活判定**更对口（RQ-4 §5 同向）。但 RQ-3 数据进一步表明 (c) 的主因可能**不在槽位**：FM 的阻塞是"stalled 等人工 gate + 链式依赖"（不占槽，但阻塞 key 队列与 stage 收口），E2 才是真缺槽（第 3 个 key 排队 4.79h / 5.64h，最大队列深度 4）⇒ 见 RQ-8。
4. **对 AC-008 的输入**：现场已证实"行数（面板口径）≠ 槽数（cap 口径）"（F4 的 MW 行），因此面板必须**同时**显示这两个量，否则操作者会像本 key 开头那样误判"`slots 2/2` 却没几个 worker 在跑"。
