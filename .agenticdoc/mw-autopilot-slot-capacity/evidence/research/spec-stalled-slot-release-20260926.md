# Research: stalled key 与槽位释放语义（RQ-6 / key `mw-autopilot-slot-capacity`）

> 角色：spec 期调研（**只读**）。本文件是本次调研唯一写入的文件。
> 代码基线：`H:/git/Multi-Workers` HEAD `4ef71e053`，`packages/multi-workers/autopilot/conductor.py` sha256 `a284dc00478e9c80`。
> 数据基线：三项目 `pm-state.md`/`_index.parallel`/`_workers.parallel`/`_autopilot/timeline.jsonl*`/`_autopilot/gates/*`（FM=`E:/CLI_workspace/FeatureMigrator`，E2=`H:/git/E2Feature`，JC=`H:/git/JCodingAss`）。

## TL;DR

1. **stalled key 不占槽（正常路径）**：`conductor.py:289` 的 `in_flight_keys` **只**看 `_workers.parallel` 行的 `status`（`pending/running` 等非终态）与行归属（`ap-{key}-` 前缀或 `.agenticdoc/{key}/workers/` 路径），**从不读 key-status**。而 stalled key 在 `orchestrate` 的 per-key 循环里被 `:274` 直接 `continue` 跳过，且所有 stall 触发点都在 in-flight 检查之后 ⇒ 正常 conductor 路径**结构上不可能**出现 "stalled 且占槽"。
2. **实测占槽 ≈ 0**：FM 70.6h 窗口内 stalled×in-flight 重叠 = **0.00h**；E2 100.1h 窗口内 = **0.04h（155.9s，2.6min，占窗口 0.04%）**。那 2.6 分钟还是一次 **PM 手工 `/worker` 派发**（task.md 无 `origin: conductor`）复用 `ap-{key}-` 前缀造成的，不是 conductor 派发。E2 还实测到 **3 个 key 同时 stalled 而 `max_parallel_keys=2`**（11h 窗口）——反证 stalled key 不在 cap 记账内。
3. **真正的 (c) 成本不是槽，是"无门禁超时"**：stalled key 会阻塞 `_stage_closure`（`:616`，全部 key 必须 `done|closed-legacy`）与依赖方（`_DEP_SATISFIED` `:56`），且**没有任何 gate 超时/TTL/自动应答**；无人值守 = 永久停在原地（心跳照常，面板"看起来在跑"）。实测 20 个 stalled gate **全部由人工批准**，等待 0.19h..17.40h；不答 gate 就永远不动。
4. 因此 **M1/M2（"先释放 stalled 槽位"）在 (c) 上收益 ≈ 0**；有效杠杆是"释放 **key**"（有界自动关闭/自动续跑）或"消除 stall 成因（自愈）"，以及可观测性上把"stage 被 N 个 stalled key 卡住"讲清楚。
5. 可观测性：TS 面板**能**看到 stalled key（`:603-627` attention 行 + gate id），但看不到"哪个 key 占着槽"，也没有"stage 被 stalled 卡住"这一行；`mw doctor` 的 autopilot 段（`mw_common.py:2022`）**完全没有** stall/slot 内容；`_index.parallel`/`pm-state.md` 都不携带 `stalled`（唯一载体是 `_roadmap.md` 的 `key-status:` 行）。

## 决策问题

本笔记只回答 RQ-6 的 (c) 侧（stalled key 与槽位释放语义），边界如下：

1. **stalled 的定义与生命周期**：谁能置 stalled（哪条路径、什么阈值）、stalled 之后 conductor 每 tick 做什么、什么能解除；每条给函数名 + `file:line`。
2. **核心判定**：stalled key 是否计入 `conductor.py:289` 的 `in_flight_keys`（占槽）——统计口径（按什么字段过滤）+ 明确结论。这是 M1/M2 有无收益的前提。
3. **实测占槽时长**：真实数据里"槽位被 stalled key 占用的时间占比"，含样本量、时间窗、复算方式；引用 FM 洪泛/9-key 记录的锚点。
4. **无人值守（夜跑）路径**：无人答 gate 时 stalled key 会怎样；有无"无人值守专用"释放机制/env。
5. **变更面与反作用**：若要"stalled key 不占槽（或超时释放）"改哪里；以及反作用（注意力掩盖、与 `advance_stall_ticks` 跳过规则冲突、夜间"无限换 key"）。
6. **可观测性缺口**：能否从面板/doctor 看出"这个槽被 stalled key 占着"。

不回答：key 层/worker 层上限数据、worker 层串行化点（属 RQ-1/RQ-5）、`max_parallel_keys` 取值应该改多少（属 design）。

## 调研方法与出处

### 代码（只读）

- 直接通读 `packages/multi-workers/autopilot/conductor.py`（4163 行，全文）、`autopilot/gates.py`、`autopilot/config.py`、`autopilot/timeline.py`、`launcher.py`（reconcile 段）、`mw_common.py`（queue/doctor 段）、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/{monitor,status-model}.ts`。
- 命令原样：`rg -n "stall|in_flight_keys|_is_in_flight|_row_belongs_to|mark_stalled|max_parallel_keys" packages/multi-workers packages/coding-agent/src`。
- 关键行号在「发现」逐条给出。

### 数据（只读复算）

每个项目的复算口径：

1. **timeline**：合并全部 generation（`timeline.jsonl.1`/`.2` 是 rotation，older→newer 按 `seq` 升序），用 `ev=="stalled"` / `resume` 重建每个 key 的 stalled 区间；`gate-created`/`gate-answered` 关联 gate kind。
2. **worker 行**：`_workers.parallel` 每行 `task_key | status | cli | provider | task_path | dispatched_at | updated_at | model`；行的在途区间 = `[dispatched_at, updated_at or now]`；key 归属 = `task_key.startswith("ap-"+key+"-")` 或 `"/.agenticdoc/"+key+"/workers/" in task_path`（与 `_row_belongs_to` `conductor.py:2135` 同口径）。
3. **占槽重叠**：`overlap(stalled 区间, 本 key 所有行区间)` 求和；**cap 打满率**：把所有行区间端点做扫描线，统计"同时在途 distinct key 数"的时长直方图（只用 `ap-` 行）。
4. **gate 等待时长**：每个 `stalled` gate 文件（`_autopilot/gates/gate-*.md`，含 YAML 头 `kind/status/key/created_at/answered_at/answered_by`）的 `created_at → answered_at`。

复算脚本（最小版，`python -` 运行）：

```python
import json, glob, datetime
def dt(s): return datetime.datetime.fromisoformat(s)
def load(root):
    evs = []
    for f in sorted(glob.glob(root + "/.agenticdoc/_autopilot/timeline.jsonl*")):
        for l in open(f, encoding="utf-8"):
            if l.strip(): evs.append(json.loads(l))
    return sorted(evs, key=lambda e: e["seq"])

def stalled_intervals(evs):                       # 合并 flood：连续 stalled 只算一次进入
    out, open_ = {}, {}
    for e in evs:
        k = e["key"]
        if e["ev"] == "stalled" and "closed-legacy" not in e["detail"]:
            open_.setdefault(k, dt(e["ts"]))
        elif e["ev"] == "resume" and k in open_:
            out.setdefault(k, []).append((open_.pop(k), dt(e["ts"])))
    for k, a in open_.items(): out.setdefault(k, []).append((a, dt(evs[-1]["ts"])))
    return out

def rows(root):
    r = []
    for l in open(root + "/.agenticdoc/_workers.parallel", encoding="utf-8"):
        c = [x.strip() for x in l.rstrip("\n").split("|")]
        if len(c) >= 7 and c[0].startswith("ap-"):
            r.append(dict(k=c[0], st=c[1], p=c[4],
                          a=datetime.datetime.fromisoformat(c[5].replace("Z", "+00:00")),
                          b=datetime.datetime.fromisoformat(c[6].replace("Z", "+00:00")) if c[6] else None))
    return r

# 对每个 key：sum(overlap(stalled 区间, 本 key 行区间)) —— 结果见「发现 F3」
```

直接可复现的计数（本次实测值）：FM timeline `stalled 6691 / resume 6691 / gate-created 6696`，E2 `stalled 13 / resume 13 / gate-created 18`，JC `stalled 0`。

## 发现

### 【事实】

#### F1 — stalled 的定义与生命周期（问题 1）

**谁能置 stalled：** 全仓唯一写入者是 `mark_stalled(project_root, st, key, reason)` @ `conductor.py:3944`。它落四件产物（幂等：已是 stalled 直接 return，`:3956-3959`）：

1. `_roadmap.md` 的 `key-status: <key>=stalled`（`:3961-3967`，roadmap 锁内写）；
2. 一个 `kind=stalled` 的 gate（`_create_gate` @ `:3969-3972`，问句含 key/原因）；
3. `<key>/achieved.md` 的 `## 遗留问题（stalled 草稿）` 段（`:3984-3993`）；
4. `.agenticdoc/patterns/<key>/stall-lesson.md`（`:3995-4014`）；
5. timeline `stalled` 事件（`:4015`）。

**12 个调用点与阈值**（全部 `file:line`）：

| 触发路径 | 位置 | 阈值/条件 |
|---|---|---|
| advance 连续同边失败 | `_record_advance_result` `:868` → `mark_stalled` `:900` | `advance_stall_ticks`（默认 5，范围 1..50；`config.py:21/57/75`；读取 `_advance_stall_ticks` `:794-797`）连续同 `(key, edge)` 失败 |
| L2 budget gate 被 reject | `:986` | `_budget_gate_rejected` |
| L2 bonus 轮耗尽 | `:991` | `used >= limit + 1`（`limit = round_budget + _resume_credits`） |
| L2 dispatch 被拒 | `:1014` | `dispatch.dispatch(...).ok == False` |
| EXECUTE task 尝试耗尽 | `execute_loop` `:1062` → `:1099` | `used >= round_budget + credits` |
| EXECUTE dispatch 被拒 | `:1117` | 同上 |
| L3 无裁决（worker 崩/无输出）达上限 | `_verify_loop` `:1573` → `:1635` | `used >= l3_limit` |
| L3 判定源取证可疑达上限 | `:1664` | 同上 |
| closure reprompt 耗尽 | `:1690` | `used >= l3_limit`（判定保持 `meets`） |
| L3 below 达 `l3_limit` 轮 | `:1723` | `l3_limit = round_budget + _resume_credits`（`:1589-1600`） |
| repair 耗尽 | `:1737` | `repair_used >= round_budget + credits` |
| done 后 index phase 仍失配 | `_done_transaction` → `:1941` | set-phase 重跑后 Phase 仍非 DONE |

**stalled 之后每 tick 做什么（事实：跳过 + 保留）**：

- `orchestrate` `:274`：`if status_of.get(key) in ("done", "stalled", "closed-legacy"): continue` —— 不派发、不重试、不再进任何 stall 路径；timeline 不再新增该 key 的事件（除 gate 消费）。
- 不释放任何东西：key 仍在 `deps_of` 里；`:289` 的 cap 记账不含它（见 F2）。
- 阻塞面：`_deps_satisfied` `:2153` 用 `_DEP_SATISFIED = {"done", "closed-legacy"}`（`:56`）⇒ 依赖方等待；`_stage_closure` `:616-626` `terminal = ("done","closed-legacy")`，任一 key 非终态即 return（docstring 明写 "a stalled key with a pending gate blocks closure — AC-024"）⇒ **stage 永不闭环**。

**解除路径（只有三条）**：

1. `stalled` gate **approve** → `_apply_stalled_approvals` @ `:2295`（由 `orchestrate:235` 每 tick 调用）：roadmap key-status `stalled→running`、追加 `gate-answered` + `resume` 事件、原地改 `status_of` 使同 tick 即可跑；**消费持久化**靠 `_consumed_gate_ids` @ `:297`（从 timeline 的 `gate-answered` 解析 `gate-NNNN`，`4e874f5cc` 修复）。
2. `stalled` gate **reject** → `_apply_stalled_rejections` @ `:2363`（`orchestrate:238`）：key-status → `closed-legacy`，追加 `gate-answered` + `stalled`（detail `... closed-legacy (stalled gate rejected)`）。
3. 人在 conductor 之外直接改 `_roadmap.md` 的 `key-status:` 行（**无 timeline 事件**；E2 的"9 key 人工关单"属此类，见 F3）。

**解除后的"一轮信用"**：`_resume_credits` @ `:2273` = 该 key 已批准 stalled gate 数；每个 cap 回路各得一轮，且**不可复用**（`used` 由 append-only 的 dispatch 行单调推出）。

**没有超时/自动应答**（问题 4 的前提）：`gates.py` 的 gate 字段集无 `expires/ttl`（`gates.py:24-45`）；在 `autopilot/*.py` 与 autopilot 的 TS 内 `rg "auto.?answer|timeout|expire|ttl"` 对 gate 无命中（`worker_timeout_min`、`xkey_verify_timeout_s` 是 worker/子进程时钟，与 gate 无关）。无人值守下 stalled key **永久滞留**。

#### F2 — 核心判定：stalled key 是否计入 in-flight（问题 2）

`conductor.py:258-263`：

```python
in_flight_keys = {
    key
    for key in deps_of
    if any(
        _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
    )
}
```

- `rows` 来自 `orchestrate:203` `mw_common.parse_workers_file(mw_common.workers_path(project_root))`，即 `.agenticdoc/_workers.parallel`。
- `_is_in_flight(row)` @ `:2131`：`row.get("status","") not in mw_common._TERMINAL_STATUSES`；`_TERMINAL_STATUSES = {"done","failed","needs-clarification"}`（`mw_common.py:158`，同字面量重复在 `:1654`）⇒ **`pending`/`running`/任何其它状态都算在途**。
- `_row_belongs_to(row,key)` @ `:2135`：`task_key.startswith(f"ap-{key}-")` **或** `task_path` 含 `.agenticdoc/{key}/workers/`。
- 唯一的 cap 判定 @ `:289`：`if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])): continue`；派发成功后 `:292` `in_flight_keys.add(key)`。

**结论（明确）**：`in_flight_keys` 的谓词**只依赖 worker 行的 `status` 字段与行归属**，**完全不查 key-status**。因此：

> **stalled key 的归属 = 取决于 `row.status`（以及是否有匹配的 `ap-{key}-` 行）。** 若该 key 有非终态行 ⇒ 计入；若没有（正常路径）⇒ 不计入。**"stalled" 这个状态本身对计账零影响。**

正常路径为什么结构上不会有"stalled + 在途"：`:274` 先跳过 stalled key；所有 stall 触发点要么在 `any(_is_in_flight(r) for r in ...)` 早退之后（`execute_loop:1092`、`_verify_loop:1596-1598`、`:1729`），要么与 worker 行无关（`_record_advance_result`）。**唯一例外**：外部写入者复用 `ap-{key}-` 前缀（或 `reconcile_orphans` @ `:4021` 以 `status: "pending"` 重插 conductor 孤儿行）时，stalled key 会被计入——实测见 F3/F4。

**面板侧镜像（不是同一个数）**：`monitor.ts:246-252` 只收 `entry.status === "running"` 的行；`snapshot.slotsUsed = busyKeys.size`（`:521`）、`slotsMax = max_parallel_keys`（`:522`）。⇒ 面板 `slots` 是"有 running worker 的 key 数"，**不含 pending 行**；而 conductor 的 cap 含 pending。两者在 launcher 背压（pending 滞留）时会不一致。

#### F3 — 实测占槽时长（问题 3）

样本与时间窗：

| 项目 | timeline 窗口 | 窗口 | seq | `ap-` 行 | stalled gate | stalled key（distinct） |
|---|---|---|---|---|---|---|
| FM `E:/CLI_workspace/FeatureMigrator` | 2026-09-23T09:06:44Z → 2026-09-26T07:40:05Z | 70.6h | 1..91693 | 128 | 7 | 6 |
| E2 `H:/git/E2Feature` | 2026-09-22T03:35:07Z → 2026-09-26T07:40:03Z | 100.1h | 1..96912 | 432 | 13 | 8 |
| JC `H:/git/JCodingAss` | 2026-09-15T20:04:11Z → 2026-09-26T07:40:05Z | 251.6h | 98074..298291 | 17 | 2 | 0（事件已被 rotation 剪掉） |

**占槽重叠（stalled 区间 × 本 key 行区间）**：

| 项目 | Σ stalled 时长 | 与在途行重叠 | 占比 |
|---|---|---|---|
| FM | 54.30h | **0.00h** | 0.00% |
| E2 | 91.41h | **0.04h = 155.9s** | 0.04%（占 100.1h 窗口） |

**cap 打满率（只用 `ap-` 行，cap=2）**：

| 项目 | 同时在途 distinct key 时长直方图 | ≥2 key 时长 | 其中含 stalled key |
|---|---|---|---|
| FM | `{0: 49.6h, 1: 6.6h, 2: 14.3h}` | 14.3h（20.2%） | **0.00h** |
| E2 | `{0: 52.8h, 1: 17.1h, 2: 30.0h, 3: 0.1h, 4: 0.0h}` | 30.1h（30.1%） | **0.04h** |

**反证（stalled 不在 cap 记账内）**：E2 实测 **3 个 key 同时 stalled**：2026-09-24T15:53:08Z → 2026-09-25T02:55:00Z（11.0h），key = `feature-inline-marker-patchkit` / `feature-cigate-install-kit` / `feature-gui-time-mvp-board`，而 `max_parallel_keys = 2`（E2 `config.json`）。若 stalled key 占槽，cap 会被突破 ⇒ 结构上它们不在记账内。FM 同时最多 2 个 stalled（2026-09-23T11:48:31Z → 15:26:00Z）。

**"卡住的注意力"时长（gate 等待，全部人工批准）**：

| 项目 | 总等待 | 最长一条 | 有 ≥1 个 stalled key 的时间 |
|---|---|---|---|
| FM | 43.5h / 7 gates | 15.19h `cli-run-state-and-events` | 38.5h = 54.6% 窗口 |
| E2 | 91.0h / 13 gates | 17.40h `feature-gui-time-mvp-board` | 46.6h = 46.6% 窗口 |

即：**槽位基本没被 stalled key 占，但近半壁墙钟时间至少有 1 个 key 处于 stalled（阻塞 stage/deps）**——"跑不完"的真实形态。

**FM 洪泛样本（"9 个卡死 key"锚点）**：

- 实测 FM timeline：`gate-created 6696 / gate-answered 6694 / stalled 6691 / resume 6691`，其中 `gui-contract-surface` 5588 对、`gui-shell-spike` 1098 对；洪泛窗 2026-09-23T15:24:16Z → 2026-09-24T03:01:32Z（≈11.6h，约 9s/tick）。同期只有 11 次 dispatch ⇒ **洪泛不放大执行量**。
- FM 侧记忆锚点：`.agenticdoc/_pitfalls.md` §42.4（`gates/` 6687 个文件、6685 次 `stalled+gate-answered+resume`）；`.agenticdoc/_autopilot/reflect/stalled-gate-replay.md`（A-04，含"洪泛门全是 `pending`…`_resume_credits` 一直只算 1 ⇒ 纯'文件+事件'洪泛，**不放大执行量**；但它把 monitor 变成'一直在跑、什么都没干'，且掩盖了真实的 stalled 信号"）；归档目录 `.agenticdoc/_autopilot/_gates-flood-20260924/`（6684 文件）；框架侧注释 `conductor.py:2320-2331`（"Measured: 6684 pending stalled gates + 6685 stalled/gate-answered/resume events in ~12 h"）；修复提交 `4e874f5cc`（2026-09-24，"consume approved stalled gates exactly once"）。
- **"9 个卡死 key"的锚点原文**：`.agenticdoc/mw-done-closure-repair/achieved.md`（遗留节）"FeatureMigrator 侧需 `/mw restart` 重启 serve 后，其 **9 个卡死 key** 才能吃到本修复（Stage 2/3 的 9×人工关单消除）"；`.agenticdoc/mw-l3-fail-marker-forms/achieved.md`（遗留节）"FM 侧 **9 个卡死 key** 的 `/mw restart` 自愈同样吃到本修复"；FM `.agenticdoc/_autopilot/handoff-done-closure-vocab-20260924.md`（`hit_keys` 行）"Stage 1 的 4 个已达 key **100% 命中**；Stage 2/3 尚有 **9 个 key 待跑**"。

**与 RQ-3 的独立口径对照（交叉核对用，不修改其笔记）**：`spec-slot-utilization-20260926.md` 的 cap=2 桶为 FM **14.11h** / E2 **29.41h**（即"恰好 2 个 key 在飞"），本笔记同口径桶为 FM **14.3h** / E2 **30.0h**（差 0.19h / 0.59h）；观察窗终点差 07:34/07:36 vs 07:40（≤6min）不足以解释全部差额，最可能的差异源是终止态行区间的取法（本笔记对 `done/failed` 行一律用 `updated_at` 作闭区间右端并做端点扫描；RQ-3 若按 `active` 子集或合并 generation 口径会略小）。**两者在结论上一致**（2-key 打满率 ≈20%/≈30%，stalled 占槽 ≈0）；差额不改变任何决策映射，交 spec 期的交叉核对笔记裁决哪个口径为准。

#### F4 — 唯一那次 2.6min 重叠的根因（事实）

E2 唯一重叠项：key `feature-cigate-install-kit` 第 2 段 stalled（2026-09-25T03:31:14Z → 06:48:30Z）与行 `ap-feature-cigate-install-kit-repair-a3-achieved-terminal`（`done`，`2026-09-25T03:40:11.098Z → 03:42:47Z`）重叠 155.9s。

- 该行**没有**任何 `dispatch` timeline 事件；
- 其 `task.md` **没有 `origin:` 行**（同目录 conductor 派发的兄弟 `ap-feature-cigate-install-kit-repair-a2-a2/task.md` 有 `origin: conductor`）；文件开头是 `type: coding` + 中文任务书（PM 写的"重写 achieved.md 为终局结案版本"）；
- 行时间戳用 `...098Z`（TS/PM 侧写法），conductor 行用 `+00:00`。

⇒ **它是 PM 手工 `/worker` 派发、复用了 `ap-{key}-` 命名**，因此被 `_row_belongs_to` 的**前缀**规则算进该 key 的 in-flight。正常 conductor 派发路径不会产生这种组合。

#### F5 — 无人值守（夜跑）路径（问题 4）

- **无专用释放机制**：resume 需要人 approve、终结需要人 reject；没有 gate TTL/超时/自动应答（F1 末）。无人值守 ⇒ stalled key 永久滞留、`_stage_closure` 永久拒绝、依赖方永久等待。
- **心跳正常但零推进**：E2 100.1h 窗口内最大 beat 间隔 8s（poll 4s）；FM 最大 328s（2026-09-24T03:01:36→03:07:04，与 serve 重启/洪泛终止对齐）。⇒ 面板上"有事件、在跑"，与 FM `_pitfalls.md` §42.6 的"看起来在跑但没进展"同型。
- **实测所有 stalled gate 都靠人工**：FM 7/7 `answered_by=user-via-pm-window`；E2 13/13 人工（`wenbozhou` / `human-pm-window`）。
- **唯一存在的"无人值守释放"是 worker 行级、不是 key 级**：`launcher.py::_reconcile_orphans` @ `launcher.py:555-600` 把 `status==running` 但不在 `running_procs` 的孤儿行收敛为终态；无任何终态证据时按静默规则在 `PI_WORKER_ORPHAN_DEAD_MIN`（默认 90 分钟；`mw_common.py:1860-1861`，`orphan_dead_after` @ `:1917`）后判 `failed`。它释放的是**槽**（非终态行消失），对 stalled key 无作用。
- 另有一个**不推进只掩盖**的反面样本：FM 洪泛（F3/F6）——无人值守下"一直在跑、什么都没干"，且"掩盖了真实的 stalled 信号"（FM `_pitfalls.md` §42.4 原文）。

#### F6 — 变更面与反作用（问题 5）

**"stalled key 不占槽" 没有可改的东西**：`:258-263` 已经不查 key-status；显式加 `and status_of.get(key) != "stalled"` 在正常路径是**语义空操作**，只会把 F4/`reconcile_orphans` 这类边界偷偷变成"不占槽"。**收益 ≈ 0**（F3）。

**真正改变 (c) 的改动面 = 释放 key（而非槽）**，候选落点（给 design）：

1. 新增每 tick sweeper（在 `orchestrate:234` 的 `_apply_stalled_*` 之前）：对 `gate.kind=="stalled"` 且 `now - created_at > T` 的 pending gate 自动 `reject`（→ `closed-legacy`）或 `approve`（→ 续跑）。触碰 `gates.py`（需新增 expiry 字段或纯时间判定）、`_apply_stalled_approvals/_rejections`、配置文件（新键，如 `stalled_gate_timeout_min`，fail-closed 加进 `config.py` + TS 镜像 `status-model.ts`）。
2. 不动 gate，改 stall 成因（自愈）：本仓库已在做的事（readcap 注入 `6254783b6`、L3 判定源 fallback `a0c36fcc`、closure reprompt `d20a270d5`、xkey 通道 `181a75332`）——这类"消除 stalled 本身"对 (c) 的正收益大于任何槽位算术。

**反作用（实测/代码依据）**：

1. **`closed-legacy` 被当作"完成"**：`_DEP_SATISFIED = {"done","closed-legacy"}`（`:56`）⇒ 自动关闭一个 stalled key **会像 done 一样解锁依赖方并允许 `_stage_closure` 收口**（`:629`）。风险：stage 带着未验证的 key 闭环；唯一残留是 `achieved.md` 的遗留草稿 + `patterns/<key>/stall-lesson.md`。若走 auto-approve 则相反（不终结、但续跑）。
2. **与 `_resume_credits` 相乘 = 无界重试**：`_resume_credits`（`:2273`）把每个已批准 stalled gate 折算成 `round_budget` 之外的额外一轮，且它在每个 cap 回路各生效一次、每次 gate 目录重算。**无条件 auto-approve ⇒ `limit = round_budget + credits` 无上界 ⇒ 夜间"无限换 key / 无限烧 token"**。这是本 RQ 第 5 问点名的最危险反作用，与 FM 洪泛同源（§42.4 规则②"先修'不可推进'的根因，再批准重试"）。
3. **与 `advance_stall_ticks` 跳过规则**：无直接冲突——stalled key 被 `:274` 跳过，streak 冻结（这正是"有界失败"的设计）。但 auto-release 把它翻回 `running` 后，同一 `(key, edge)` 会再次失败并再次 stalled（FM 洪泛的 `stalled↔running` 振荡即此形态）⇒ auto-release **必须**保持 `_consumed_gate_ids` 的消费持久化，且必须有"每 key/每 stage 自动处置次数上限"。
4. **注意力掩盖**：因为 stalled 不占槽，"释放槽位"本身不改变任何可见量；而 auto-approve 会让面板 `stalled 0` 而 stage 仍被 dependencies 卡住 ⇒ **可观测性反而更差**（FM §42.4 "掩盖真实的 stalled 信号"是既有先例）。
5. **`max_parallel_keys` 语义**：不用改。cap 只数行；stalled key 天然在 cap 之外（F3 的 3>2 反证）⇒ 提高上限对 (c) 完全无收益（对 (d) 的影响属 RQ-5）。

#### F7 — 可观测性缺口（问题 6）

- **有的一半**：`monitor.ts::deriveAutopilotPanel`（`:463`）header 行（`:596-599`）输出 `slots ${used}/${max} | keys N (running, stalled, done) | stall-ticks`；attention 行（`:603-627`）对每个 `status==="stalled"` 的 key 打印 `phase/status`、`advance <count>x <class> <age> ago`、以及 `-> /autopilot gate <id> approve|reject (resume grants one round)`。⇒ **操作者能从面板看到"哪些 key 是 stalled"**。
- **缺口 (a)**：`slots` 是 `busyKeys.size`（`:521`，由 `:509-513` 用 `owner ?? w.taskKey` 聚合），面板**不打印占槽的是哪些 key**；且它与 conductor 的 cap 记账口径不同（面板只收 `running`，conductor 含 `pending`）。
- **缺口 (b)**：面板**没有**"stage 被 stalled key 卡住"这一行，也没有"槽被 stalled 占着"这一表达——后者在正常路径下不存在（F2/F3），但前者是 (c) 的真实症状，当前只能靠人自己把 `stalled N` 和 stage 状态拼起来。
- **缺口 (c)**：`mw doctor` 的 autopilot 段 `mw_common.py::_doctor_autopilot` @ `:2022` **只**报告 xkey verify 配置（`xkey_repair`/argv/cwd/missing），**零 stall/slot 内容**；`_doctor_queue` @ `:1954` 只列非终态行（`task_key/status/cli/task_md_exists`）+ stale 计数，不与 key/cap 关联。⇒ CLI 侧对 (c) 完全不可观测，只有 TS 面板有。
- **缺口 (d)**：`_index.parallel`（`Key|Status|Phase|ClaimId|Deps|Desc|Updated`）与 `<key>/pm-state.md` **都不携带 `stalled`**；唯一载体是 `_roadmap.md` 的 `key-status:` 行（TS 侧 `readRoadmap`，`status-model.ts:483/521/538`，`monitor.ts:471-476` 用它填 `statusByKey`）。实测：E2/FM 的 stalled key 在 `_index.parallel` 里只显示 `idle|DONE`（事后值），任何只读 `_index.parallel` 的视图（含 `mw status` 的 phase 面）看不到 stall。

### 【推断】

- **I1**：M1/M2 若定义为"释放 stalled key 占用的 `max_parallel_keys` 槽位"，**收益 ≈ 0**（F2 结构 + F3 实测）。要改善 (c) 必须释放 **key 本身**（有界自动处置）或消除 stall 成因（自愈）。
- **I2**：用户观察到的"槽位被卡死的 key 占着"最可能是以下三者之一，本 RQ 的实测无法完全区分（见数据缺口 4）：
  (i) **挂死/死亡 worker 行**占槽——launcher 的 90 分钟孤儿窗口（F5）内它是非终态行，面板显示 `slots 2/2` 而零推进（这不是 key-status stalled）；
  (ii) **stalled key 阻塞 deps/stage**、槽位其实是空的（F1/F3）；
  (iii) FM 式**洪泛**让面板"看起来在跑"（F6）。
- **I3**：任何 0 人工应答的夜跑策略都无法完成 roadmap——stalled 是**有意的**人工决策点（done 词表/预算耗尽/无法裁决）。改 (c) 是"自主性 vs 验证强度"的策略取舍，不是容量取舍。
- **I4**：本仓库对 (c) 的主要治理方向已经押在"消除 stall 成因（自愈）"上（F6 候选 2），而不是槽位释放；RQ-6 的结论（占槽 ≈ 0）与该方向一致。

## 结论 → 决策映射

**支撑 AC-004（(c) 的直接证据）**：

| AC-004 要求 | 结论 |
|---|---|
| stalled key 是否计入 in-flight（代码锚点） | **正常路径：不计入**。`in_flight_keys` 谓词 = `row.status ∉ {done,failed,needs-clarification}` ∧ 行归属 key（`conductor.py:258-263` + `:2131` + `:2135`）；**key-status 不在谓词内**。stalled key 被 `:274` 跳过且所有 stall 触发点在 in-flight 检查之后。边界：外部 `ap-{key}-` 行或 `reconcile_orphans`（`:4021`，`status:"pending"`）会把它计入。 |
| 实测"槽位被 stalled key 占用的时间占比" | **FM 0.00h / 70.6h = 0.00%；E2 0.04h / 100.1h = 0.04%**（那 0.04h 是 PM 手工 `/worker` 复用 `ap-` 前缀所致，非 conductor 派发）。反证：E2 曾 3 个 key 同时 stalled 而 cap=2。 |
| 数据不足以实测时的诚实声明 + 方法 | 不需要声明"无法实测"；但**"无人值守永久滞留的时长"无法从历史上界**（没有反例：所有 stalled gate 都被人在 0.19~17.40h 内批准）。要实测"无人工应答"需一条专门实验（见数据缺口 3）。 |

**回答 U-4′ 的 (c) 侧**：

- **"槽位释放语义"不是 (c) 的杠杆**：stalled key 已经不占槽；M1/M2 若只改 `in_flight_keys`/`max_parallel_keys` 语义，(c) 吞吐收益 ≈ 0（且"提高上限"对 (c) 完全无效）。
- **(c) 的真实杠杆有三条**：
  1. **有界自动处置（策略变更）**：对超时未答的 `stalled` gate 自动 `reject→closed-legacy`（一元、可预测，但会把 key 当 done 解锁依赖并允许 stage 收口——需 design 明确 goal 完整性语义）或**有次数上限**的 `approve`（注意 `_resume_credits` 的无界风险，反作用 2）。
  2. **消除 stall 成因（已在做）**：本仓库近 5 个 key 的修复（readcap 注入、L3 判定源 fallback、closure reprompt、verdict provenance、xkey）都是这一类；它同时减少"夜间人工关单"需求，是 (c) 收益最大且无槽位语义风险的方向。
  3. **可观测性补齐**：面板加"stage 被 N 个 stalled key 卡住 + 占槽行清单"，doctor 加 autopilot stall 段；这样"看起来在跑但没进展"能 10 秒内判定（FM §42.6 的鉴别法应进 doctor）。
- **建议给 spec 的措辞**：把 AC-004 的 (c) 侧从"stalled key 是否占槽"改写为"**stalled key 不消耗 `max_parallel_keys` 槽（已实测 ≈0），但会无限期阻塞 stage 收口与依赖；无人值守下没有任何自动处置机制 ⇒ (c) 的决策点是'是否引入有界的无人值守 stalled 处置策略'，而非'如何让 stalled key 不占槽'**"。

## 数据缺口

1. **没有 key-status 历史序列**：stalled 区间由 timeline `stalled`/`resume` 事件重建；人在 conductor 之外直接改 `_roadmap.md`（如 E2 的人工关单）不留事件 ⇒ 区间可能被低估。本样本里 FM/E2 每条 stalled 都有对应 `resume`（13/13、6691/6691），所以误差有界；JC 同理但事件已被剪。
2. **JC 不可用于 (c)**：其 timeline 只保留 3 个 generation（seq 98074..298291），`plugin-ui` 的 2 个 stalled gate 对应的 `stalled`/`resume` 事件已随更早 generation 被剪掉 ⇒ JC 只有 gate 文件级证据（2 个 gate、共 0.3h），无法做占槽重叠。
3. **"无人工应答"路径无历史反例**：所有 20 个 stalled gate 都被人答了。要量化"无人值守下永久滞留造成多少损失"，需要一条受控实验（例：复制 FM 的 `_autopilot/` 到临时目录、屏蔽 gate 应答、观察 24h 内 stage 是否停滞且无自动处置），本次只读任务不做。
4. **挂死 worker 行（问题 I2-(i)）未实测**：本次只统计了"非终态行"，没有把非终态行与"当前是否有活 pid/心跳"交叉。若要判别"I2-(i) 才是用户看到的现象"，复算方法 = 在每个采样时刻列 `_doctor_queue` 的 `non_terminal` 行并检查 `task_dir` 是否有新鲜活动（`_row_last_activity`），统计"非终态但无活动 > 90min"的行占槽时长；这是接下来最值得补的一条测量。
5. **"9 个卡死 key 自愈"是记忆/推算而非实测**：FM 实测为 6 key / 7 gate；"9"出自 `handoff-done-closure-vocab-20260924.md` 的"Stage 2/3 尚有 9 个 key 待跑"（推算），以及两个 key 的 achieved.md 转述。**design 期不得把"9 keys self-healed"当实测值引用**。
6. **token/成本未测**：stalled 期间零 dispatch（除洪泛窗 11 次），推断 token 花费 ≈ 0；但没有逐 worker 的 token 账本可核，属推断。

[VERIFY] RQ-6: stalled_holds_slot=no(normal-path)/partial(external `ap-{key}-` row or orphan reinsert) in_flight_rule=row.status not in {done,failed,needs-clarification} AND (task_key startswith `ap-{key}-` OR task_path contains `.agenticdoc/{key}/workers/`), key-status never consulted [conductor.py:258-263,2131-2137,289] stalled_slot_pct=0.04% (E2 155.9s/100.1h) / 0.00% (FM 0/70.6h) cap_proof=3 simultaneous stalled keys with max_parallel_keys=2 (E2, 2026-09-24T15:53:08Z..2026-09-25T02:55:00Z) unattended_policy=none(no gate TTL/auto-answer; release only via human approve->resume or reject->closed-legacy; worker-row orphans freed by launcher after PI_WORKER_ORPHAN_DEAD_MIN=90min) stalls_wall_clock=E2 91.0h/13 gates/8 keys, FM 43.5h/7 gates/6 keys (100% human-approved) stage_blocked=yes (_stage_closure:616 requires all keys done|closed-legacy; _deps_satisfied:2153 via _DEP_SATISFIED:56) observability=panel shows stalled keys + gate hint (monitor.ts:603-627) but not slot holders; doctor autopilot section has no stall/slot content (mw_common.py:2022); _index.parallel/pm-state carry no stalled state (roadmap key-status is the only carrier)
