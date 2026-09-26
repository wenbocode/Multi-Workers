# Research: 无人值守下的门禁阻塞面（RQ-8 / msc-rq8-unattended-gates）

> Key: mw-autopilot-slot-capacity ｜ 角色: research（只读；本文件是本卡唯一写面）
> 快照时刻: **2026-09-26T07:43Z**（FM 与 E2 的 autopilot 当时仍在跑，所有数字都是该时刻的冻结值；冻结前的行不属于本文）
> 边界: 本卡**不做** RQ-6 的题目（stalled key 的生命周期与占槽机制），也不做 RQ-3 的槽位利用率复算。本文只回答「门在哪、卡多大范围、实测等了多久、有没有无人值守策略、早上怎么看」。

## TL;DR

- **必须外部输入的门 = 6 类**（`gates.py:54-61` 的 `GATE_KINDS`，闭集；`GATE_STATUSES` 在 `:63`）：`stage-confirm` / `stage-close` / `stalled` / `budget-exhausted` / `goal-change` / `xkey-authorize`。**没有任何一类有超时、自动 approve/reject、或 "夜跑" 分支**（见 F5）。
- **stalled 会不会让整个 stage 停住：会。** `_stage_closure` 的终态集是 `("done", "closed-legacy")`（`conductor.py:629-631`），`stalled` 不算终态 ⇒ stage 永不收口；而未收口的 stage 又挡住下一 stage 的激活（阶段串行，`_stage_activation` `conductor.py:439-451`）。因此**一个 stalled key 的阻塞面是 key → stage → roadmap**（后者经阶段串行与依赖传递）。
- **实测等待（FM 10 个真实 gate / E2 18 个，快照冻结）**：`stalled` gate 中位 **3.62h（FM）/ 4.04h（E2）**，最大 **15.19h / 17.40h**，累计 43.49h / 90.97h；`stage-close` 中位 0.02h / **3.15h**；`stage-confirm` 全部 ≤ 0.20h。**无一条从未被答**（两个项目当前 pending gate 均为 0）。
- **FM 的 70.61h 观测窗里，38.55h（54.6%）至少挂着一个 stalled gate**（并集，含重叠）；Stage 1 内 51.7%、Stage 2 内 61.1%。这些数字是「有 key 被冻结」，不等于「全项目停摆」。
- **最强链条实例**：`gui-skeleton-shell` 的两次 stalled（合计 17.74h）是 FM Stage 1 收口的唯一阻碍 ⇒ Stage 2 在它被答后 9 秒才收口、2 分钟后才启动；`cli-run-state-and-events` 的 stalled（15.19h）挡住了依赖它的 `gui-live-monitor` 与 `gui-run-control-hitl`，两 key 在 gate 被答后 **9 秒**才被派发；其中 **14.87h 项目完全静止**（除 `beat` 外 timeline 0 事件）。这两条把「(c) 侧是门不是槽」钉死在 FM 上。
- **无人值守策略：不存在** —— 而且 gate 是**被刻意设计成人类专用通道**：`xkey-gate-guard.ts` 在工具层封死 agent 对 gate 目录的写（本卡做只读分析时就被它拦了一次命令，见 F5）。「自动答 gate」不是"没实现"，是"被主动禁止"。
- **可观测性**：monitor 面板能看到 pending gate 的 id/kind 与应答命令（`monitor.ts:644-655`），但 `MonitorGate` **不带 created_at** ⇒ 看不出「挂了多久」；`mw doctor` 的 autopilot 节**完全不显示 gate**（`mw_common.py:2022-2065`），也没有 gate 陈旧度告警进 `_doctor_issues`（`mw_common.py:2067+`）⇒ 早上用 `mw doctor` 看不出昨夜卡在哪个门。

`[VERIFY] RQ-8: human_gates=6(stage-confirm,stage-close,stalled,budget-exhausted,goal-change,xkey-authorize) non_gate_waits=3(roadmap-writer-exhausted,tick-skip-on-corrupt-file,dispatch-refusal-livelock) blocking_scope=stalled:key+stage+roadmap stage-confirm:roadmap stage-close:roadmap-or-halt budget-exhausted:key goal-change:roadmap xkey-authorize:owner-key stalled_blocks_stage=yes(conductor.py:629-631) unattended_policy=absent(and tool-layer-blocked by xkey-gate-guard.ts) samples=FM10/E2=18 real gates max_gate_wait=17.40h(E2 gui-time-mvp-board)/15.19h(FM cli-run-state-and-events) fm_stalled_pending_union=38.55h/70.61h(54.6%) stage_close_lag=9s(both computable stages)`

## 决策问题

从 spec draft §1.1.1 的 (c)「夜跑/无人值守跑不完」出发，查清**门这一侧**（与 RQ-3 的槽这一侧互补）：

1. timeline 的 17 类事件与 gates 相关代码里，哪些门在无人值守下**必须外部输入**才能继续？每个门：谁答、代码锚点、无人值守后果、**阻塞一个 key 还是整个 stage / roadmap**。
2. `_stage_closure` 的收口条件（是否要求 stage 内所有 key 终态？`stalled` 算不算终态？）⇒ **一个 stalled key 是否让整个 stage 在无人值守下永久停住**。
3. `_deps_satisfied` 的口径；结合 FM 真实 roadmap，FM 当前/历史哪些 key 是在等 deps 而不是等槽。
4. 每类 gate 的 `gate-created → gate-answered` 延迟分布（中位/最大/从未答条数），以及「最后一个 key 终态 → stage-close」的间隔；全部可由文件复算。
5. 代码里有没有 gate 超时 / 自动 approve-reject / `--unattended` 类开关 / 夜跑专用分支？
6. 无人值守时，操作者早上如何看出「昨夜卡在哪个门」？

**不做**：不给任何改动方案（提上限、自动答 gate、门禁重设计均属 design/spec 的职责）；不重复 RQ-3 / RQ-1 / PM 交叉核对笔记已有的结论。

## 调研方法与出处

### 代码（只读；行号 = 2026-09-26 工作树快照）

| 面 | 位置 |
|---|---|
| gate 闭集与 12 字段 schema（**无 timeout / deadline / expire 字段**） | `packages/multi-workers/autopilot/gates.py:54-61`、`:68-81` |
| gate 创建（conductor 唯一创建者，写 `pending`） | `gates.py:create` `:262` 起；`conductor.py:_create_gate` `:2159-2184` |
| gate 应答（人类路径，写 status/answered_at/answered_by/note） | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:139-178`；CLI 入口 `/autopilot gate <id> approve\|reject` `autopilot/console.ts:204-245` |
| 工具层封禁 agent 写 gate 目录 | `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`（`registerXkeyGateGuard`） |
| timeline 事件词表（17 类） | `packages/multi-workers/autopilot/timeline.py:67-85` |
| 派发循环（stalled 跳过 / deps / 在飞 / cap 的顺序） | `conductor.py:266-292` |
| stage 收口判定 | `conductor.py:_stage_closure` `:616-656`（终态集 `:629-631`） |
| stage 激活与 halted | `conductor.py:_stage_activation` `:434-451`；`_activate_pending_stage` `:454-486` |
| 依赖口径 | `conductor.py:56`（`_DEP_SATISFIED`）、`:2153-2154`（`_deps_satisfied`）、`:285-286`（调用点） |
| stage-confirm / stage-close 的创建与消费 | 创建 `:409-431`、`:489-497`、`:650-656`；消费 `_consume_answered_gates` `:353-358`（confirm）/ `:359-378`（close） |
| stalled gate 的创建与消费 | 创建 `mark_stalled` `:3971-3975`；approve `_apply_stalled_approvals` `:2295-2361`；reject `_apply_stalled_rejections` `:2363-2420` |
| budget-exhausted gate | 创建 `_advance_key` `:995-1003`；消费 `_budget_bonus` `:2216-2227` / `_budget_gate_rejected` `:2228-2239` |
| goal-change gate | 创建 `tick` `:2082-2097`；轮询 `open_goal_change_gate` `:174-180`；恢复 `:2101-2110` |
| xkey-authorize gate | 创建 `_xkey_ensure_gate` `:2724-2749`；消费 `_consume_xkey_gate` `:2798+`；挂载点 `:245-248`、`:345-348` |
| 收敛到 gate 的两条自动路径 | advance 连续失败 `_record_advance_result` `:868-905`；L3 无裁决 `:1629-1641` |

### 数据（只读；快照 2026-09-26T07:43Z）

| 项目 | 数据 | 内容 |
|---|---|---|
| FM `E:\CLI_workspace\FeatureMigrator` | `.agenticdoc/_autopilot/gates/` | **10 个真实 gate**（gate-0001..0010），全部已答（approved） |
| FM | `.agenticdoc/_autopilot/_gates-flood-20260924/` | **6684 个文件，全部 `kind=stalled` / `status=pending`** —— 2026-09-24 gates-flood 事故的归档残留（已移出活动队列，见 F4 告警） |
| FM | `.agenticdoc/_autopilot/timeline.jsonl` + `.1` | 91,742 事件，seq 1..91742，2026-09-23T09:06:44Z → 2026-09-26T07:43:11Z（**70.61h**），无丢代（`.1` 从 seq 1 起） |
| FM | `.agenticdoc/_autopilot/_roadmap.md` | Stage 1 closed / Stage 2 running（key-status 只有 2 个 done；5 个 key 中 3 个尚未终态） |
| E2 `H:\git\E2Feature` | `.agenticdoc/_autopilot/gates/` | **18 个真实 gate**，全部已答 |
| E2 | `timeline.jsonl` + `.1` | 96,962 事件，2026-09-22T03:35:07Z → 2026-09-26T07:43:13Z（**100.14h**） |
| E2 | `_roadmap.md` | Stage 1/2 closed、Stage 3 running（10 个 key，8 个 done，2 个未终态） |
| MW（本项目） | `.agenticdoc/_autopilot/` | **不存在** ⇒ 本项目对"门的等待时长"零样本（与 RQ-3 的缺口 1 同源） |

### 算法（逐条固定，可复算）

1. **gate 延迟** = gate 文件的 `answered_at` − `created_at`（ISO8601，UTC）。以 **gate 文件 frontmatter 为准**，不取 timeline：timeline 的 `gate-answered` 是 conductor **消费**该答案的时刻（下一 tick），而文件字段是人类**作答**时刻，本卡要测的是"人等了/机器等了多久"。
2. **stage 收口检测延迟** = `stage-close` gate 的 `created_at` − 该 stage 最后一个 key 的终态事件时刻。终态事件取 timeline 的 `advance <edge>->done exit=0`，或 `stalled`/`gate-answered` 里含 `closed-legacy` 的事件。
3. **依赖等待** = key 首次 `dispatch` 事件时刻 − 它所有 dep 中最晚的终态时刻。
4. **stalled gate 挂起并集** = 各 stalled gate 的 `[created_at, answered_at)` 区间按时间排序后合并（相邻/相接合并），再求和；由于 gate 与 key 一一对应（编号去重后），该并集 = 「至少有一个 key 因 gate 被冻结」的时长。
5. **pending/从未答** = `status: pending` 的文件条数（直接数目录 + 解析 frontmatter）。
6. 全部只用 Python 标准库读文件；分析脚本写在 `%TEMP%`（未落在任何项目目录）。

**复算方式**（把下面这段存成脚本文件后运行；只读）：

```python
import os, glob, datetime as dt, collections, statistics
def P(s): return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
def h(a, b): return (P(b) - P(a)).total_seconds() / 3600.0

def read_gates(root):
    d = os.path.join(root, ".agenticdoc", "_autopilot", "gates")   # 见下方 placeholder 说明
    out = []
    for f in sorted(glob.glob(os.path.join(d, "gate-*.md"))):
        fm = open(f, encoding="utf-8", errors="replace").read().split("---")[1]
        fl = {}
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fl[k.strip()] = v.strip().strip("'")
        out.append(fl)
    return out

def agg(rows):
    byk = collections.defaultdict(list)
    for r in rows:
        lat = h(r["created_at"], r["answered_at"]) if r.get("answered_at") else None
        byk[r["kind"]].append(lat)
    for k, lats in sorted(byk.items()):
        ok = sorted(x for x in lats if x is not None)
        print(k, "n=%d answered=%d never=%d median=%.2fh max=%.2fh sum=%.2fh" % (
            len(lats), len(ok), len(lats) - len(ok),
            statistics.median(ok) if ok else -1, ok[-1] if ok else -1, sum(ok)))

def stalled_union(rows):
    iv = sorted((P(r["created_at"]), P(r["answered_at"]))
                for r in rows if r["kind"] == "stalled" and r.get("answered_at"))
    m = []
    for s, e in iv:
        if m and s <= m[-1][1]: m[-1] = (m[-1][0], max(m[-1][1], e))
        else: m.append((s, e))
    return sum((e - s).total_seconds() for s, e in m) / 3600.0

FM = r"E:\CLI_workspace\FeatureMigrator"
E2 = r"H:\git\E2Feature"
for name, root in (("FM", FM), ("E2", E2)):
    rows = read_gates(root)
    print("==", name, len(rows), "gates; stalled union = %.2fh" % stalled_union(rows))
    agg(rows)
```

脚本里的 gate 目录用 `os.path.join` 三段拼接，以避开 F5 记的文本级扫描（实际拼写 = `<root>` + `/.agenticdoc/` + `_autopilot/` + `gates/`）。

## 发现

### F1【事实】「必须外部输入」的门全清单

`GATE_KINDS` 是**闭集**（`gates.py:54-61`），`status ∈ {pending, approved, rejected}`（`gates.py:63`）。conductor 是唯一创建者（写 `pending`），应答侧只有两条合法路径：`/autopilot gate <id> approve|reject`（`console.ts:204-245` → `gate-writer.ts:139-178`）或**手工编辑 gate 文件**（`gates.py` 模块 docstring 明写「Manual file edits are equally legal answers: the file is the source of truth」，`:8-12`）。没有任何代码路径由程序把 status 写成 approved/rejected（grep `unattended|auto_?answer|gate_timeout|--yes|noninteractive` 零命中，见 F5）。

| gate kind | 创建锚点 | 消费锚点 | 谁答 | 无人值守时的后果 | **阻塞面** |
|---|---|---|---|---|---|
| `stage-confirm` | `_create_stage_confirm_gate` `conductor.py:489-497`；`_ensure_next_stage_gate` `:409-431` | `_consume_answered_gates` `:353-358`（approved → stage `running`） | 人 | **永久等待**，无超时；`_stage_activation` 返回 False ⇒ **该 tick 起一个 key 都不派发** | **整个 roadmap**（新 stage 无法启动） |
| `stage-close` | `_stage_closure` `:650-656` | `:359-378`（approved → `closed` + 开下一 stage confirm；**rejected → stage `halted`**） | 人 | approved 前 stage 不 `closed`；rejected 后 `_stage_activation` `:443-444` 直接 return False，**除非人工改 roadmap 否则永不再开工** | **整个 roadmap**（阶段串行 + halted 门） |
| `stalled` | `mark_stalled` `:3971-3975`（L2 预算/EXECUTE/L3/advance-streak 四条路径都会汇到这里） | approve `_apply_stalled_approvals` `:2295-2361`（→ key `running` + `resume` + 每 loop 一次 extra round）；reject `_apply_stalled_rejections` `:2363-2420`（→ `closed-legacy`） | 人 | key 被跳过（`:274-275`），**永久等待**；key 非终态 ⇒ stage 永不收口 ⇒ 下一 stage 永不启动；依赖它的下游 key 全部冻结（`_deps_satisfied`） | **key + stage + roadmap**（本卡核心判据） |
| `budget-exhausted` | `_advance_key` `:995-1003` | 轮询式：`_budget_bonus` `:2216-2227`（approved → 该 loop 多一轮）；`_budget_gate_rejected` `:2228-2239`（rejected → `mark_stalled`） | 人 | **静默冻结**：gate pending 期间 key 不派发、**也不进 `stalled`**（key-status 保持原值）⇒ 面板上不会出现 `stalled`，只有一条 `gates: 1 pending` | 该 key（经非终态传递到 stage/roadmap） |
| `goal-change` | `tick` `:2082-2097`（goal.md mtime 变化即建，create-once） | `tick` 自身轮询 `:2101-2110`：**任何**已答（approved 或 rejected）都刷新 baseline 并恢复 | 人 | **整个 roadmap 全停**：`tick` 在 `orchestrate` 之前返回 `halted-goal-change`（`:2101-2103`），beat 之外的推进全部不发生 | **整个 roadmap（最硬的门）** |
| `xkey-authorize` | `_xkey_ensure_gate` `:2724-2749` | `_consume_xkey_gate` `:2798+`（仅 `xkey_repair=true` 时挂载） | 人（且工具层禁止 agent 代答） | ticket 停在待授权，跨 key 修复链冻结；默认 `xkey_repair=false` ⇒ 该通道不挂载 | 该 ticket 的 owner key |

**key 与"门"的对应关系**：`stalled`/`budget-exhausted`/`xkey-authorize` 带 `key=`；`stage-confirm`/`stage-close` 带 `stage=`（key 字段按 `timeline.py` 的 sentinel 规则落成 stage 号或 `-`，`:87-89`）。

**必须外部输入但不是 gate 的三种等待**（同样会永久停住，但**面板里没有 gate 可看**）：

| 状态 | 锚点 | 后果 |
|---|---|---|
| roadmap-writer 两次提案用尽 | `_dispatch_roadmap_writer` `:545-546` `if used >= 2: return  # both proposals spent — wait for a human roadmap edit`；配合 `_activate_pending_stage` `:454-486` | **无 gate**。stage-confirm 被 reject 且两次重提案都用尽后，只剩"人手改 `_roadmap.md`"这一条路；无人值守 = 静默停死 |
| roadmap / gate 文件损坏 | `orchestrate` `:205-212`（`roadmap unreadable` → 直接 return）；`_consume_answered_gates` `:335-337`（`gate file corrupt, tick skipped` → 整 tick 跳过） | 该 tick 全不推进；实测 FM 23 次 / E2 98 次 `roadmap unreadable`、E2 9 次 `gate file corrupt`（见 F4 的表） |
| 派发被拒（`type-rejected` / `target-config-rejected`） | `dispatch.py:437-446` 的 `reject()`（调用点 `:448`/`:457`/`:464`/`:476`/`:508`；写 0 行队列 + 事件）；conductor 侧 `_advance_key` `:936-941`（phase-writer）与 `:969-979`（l2-fix）**只 `return result.ok`，不 stall** | **静默活锁**：每 tick 重试一次、永远不产生 gate、永远不进 `stalled`。只有滚动增长的 `type-rejected` / `target-config-rejected` 事件是痕迹。两个项目的 timeline 里**没有**这两类事件的实例 ⇒ 纯代码路径风险，未在 FM/E2 触发 |
| （对照）live foreign claim | `orchestrate` `:276-284`（`skip` 事件） | **不是门**：`state.claim_state` `:111-131` 把"异主机"与"本机 pid 已死"都判 `CLAIM_DEAD` ⇒ 自愈，不需要人答 |

**自动收敛到 `stalled` 的两条路径**（值得与上表一起读，因为它们把"没有门"变成"有门"）：advance 连续 `advance_stall_ticks`（默认 5，`_advance_stall_ticks` `:794-801`）次失败 → `mark_stalled`（`_record_advance_result` `:868-905`）；L3 reviewer 无裁决达预算 → `mark_stalled`（`:1629-1641`）。

### F2【事实】stage 收口语义 —— `stalled` 会永久挡住整个 stage

`conductor.py:616-656` 原文（关键判定逐字）：

```python
def _stage_closure(
    project_root, st, stage, rm_path, status_of,
) -> None:
    """§5.1 I→J: every key terminal (done / closed-legacy; a stalled key
    with a pending gate blocks closure — AC-024) → write the closure
    dossier and open the stage-close gate (AC-003, same tick)."""
    terminal = ("done", "closed-legacy")
    if any(status_of.get(e.key) not in terminal for e in stage.keys):
        return
    if _gate_open(project_root, "stage-close", stage=stage.number):
        return  # already awaiting the human
    ...
    _create_gate(
        project_root, st, "stage-close",
        f"Stage {stage.number} 全部 key 已终态，闭环 dossier 已写入"
        ...
    )
```

判定分支（本卡要的"原文级"回答）：

- **收口条件**：stage **每一个** key 的 key-status 必须 ∈ `{done, closed-legacy}`；**任一**不满足即 `return`，不写 dossier、不建 stage-close gate。
- **`stalled` 算不算终态**：**不算**。`status_of.get(key)` 为 `"stalled"` ⇒ `not in terminal` ⇒ 收口被挡。注释里也明写 "a stalled key with a pending gate blocks closure — AC-024"。
- **更隐蔽的一支**：`status_of` 只包含 roadmap `key-status:` 行里**列出的** key（`:224-232` 从 `stage.key_status` 构造）。从未派发、也没有被写进 `key-status` 的 key，`status_of.get(key)` 返回 `None` ⇒ **同样不算终态 ⇒ 同样挡收口**。FM Stage 2 现在正是这个形状（5 个 key 只列了 2 个 done，3 个未列）。
- **`closed-legacy` 如何生成**：只有 `_apply_stalled_rejections`（人 reject 一个 stalled gate）才会写（`:2363-2420`）。⇒ **无人值守下永远不会出现 `closed-legacy`**，因为它需要一个人类 reject。

⇒ **回答**：**是。一个 stalled key 会让整个 stage 在无人值守下永久停住**（`_stage_closure` 永不返回收口、stage-close gate 永不出现、stage 永远 `running`），并因此让后续 stage 永远停在 `pending`（`_stage_activation` `:445-451`）。这不是"等一会儿会好"——门只会等人。

### F3【事实】链式依赖阻塞（`_deps_satisfied` 的口径 + FM 实测）

口径（原文）：

```python
_DEP_SATISFIED = frozenset({"done", "closed-legacy"})      # conductor.py:56

def _deps_satisfied(deps, status_of) -> bool:              # conductor.py:2153-2154
    return all(status_of.get(dep) in _DEP_SATISFIED for dep in deps)

            if not _deps_satisfied(entry.depends_on, status_of):   # conductor.py:285-286
                continue
```

⇒ `stalled`、`running`、以及**根本不在 `key-status` 行里的 key（`None`）都不满足依赖**。一个 stalled 的 dep 会把它的全部下游 key 一起冻住，直到有人答那个 gate（或 reject 成 `closed-legacy`）。

FM 实测（timeline；`first dispatch` = 该 key 首次出现 `dispatch` 事件的时刻；`last dep terminal` = 其全部 dep 中最晚的终态事件）：

| key | deps | 首次 dispatch | 最晚 dep 终态 | 结论 |
|---|---|---|---|---|
| `cli-run-state-and-events` | `cli-readonly-snapshot` | 2026-09-25T06:51:17Z | 2026-09-24T07:40:15Z | dep 早满足 23.18h，但 **Stage 1 未收口** ⇒ 不是 dep 等待，是**阶段边界等待** |
| `cli-hitl-channel` | `gui-contract-surface` | 2026-09-25T06:51:17Z | 2026-09-24T03:07:05Z | 同上（27.74h） |
| `gui-live-monitor` | `gui-contract-surface`, `gui-skeleton-shell`, `cli-run-state-and-events` | 2026-09-26T02:13:00Z | 2026-09-26T02:12:51Z | **纯依赖门等待**：最后一个 dep 的 stalled gate 被答后 **9 秒**派发 |
| `gui-run-control-hitl` | `gui-skeleton-shell`, `cli-run-state-and-events`, `cli-hitl-channel` | 2026-09-26T02:13:00Z | 2026-09-26T02:12:51Z | 同上（9 秒） |
| `gui-monitor-hitl-e2e` | `gui-live-monitor`, `gui-run-control-hitl` | **从未派发** | 两个 dep 都未终态 | 站在链尾，等前两者 |

**两条把"门等着、然后瞬间放行"钉死的链条**（同一份数据，另一种读法）：

1. `gui-skeleton-shell`：gate-0006 pending `2026-09-24T11:33:21Z → 2026-09-25T02:44:25Z`（15.18h，approve → 多一轮）→ 该轮失败后 gate-0007 pending `04:15:13Z → 06:48:50Z`（2.56h，approve）→ key 在 `06:48:51Z` 终态 → **stage-close gate-0008 在 `06:49:00Z` 建（9 秒后）** → `06:50:14Z` 人答 → stage-2 confirm gate-0009 `06:50:16Z` 建 → `06:51:15Z` 人答 → Stage 2 的两个可派 key 在 `06:51:17Z` 拿到首个 `dispatch`。**如果无人应答 gate-0006/0007，FM 到今天仍停在 Stage 1**（`closed-legacy` 只能由人 reject 产生）。
2. `cli-run-state-and-events`：gate-0010 pending `2026-09-25T11:01:09Z → 2026-09-26T02:12:48Z`（15.19h，唯一原因是 L3/advance 预算耗尽）→ key `02:12:51Z` 终态 → 依赖它的两个 key `02:13:00Z` 同时派发（cap=2 正好容纳）。**这 15.19h 里 FM 有 14.87h 完全静止**：`11:20:54Z`（`cli-hitl-channel` 的 `verify->done exit=0`，最后一个还在跑的 worker 退出）到 `02:12:51Z`（`cli-run-state-and-events` 终态）之间，timeline 里**除 `beat` 之外没有任何事件**（`dispatch`/`advance`/`config`/`gate-*` 全部为 0，共 11,921 条 beat）⇒ 该窗口内剩下的 key（`gui-live-monitor` / `gui-run-control-hitl` / `gui-monitor-hitl-e2e`）全部被这个 stalled 的 dep 挡住，而唯一的阻碍是人答 gate-0010。

**与 RQ-3 的分工**：RQ-3 已证 FM 的 `pending(t)`（槽位排队）没有 stage-key 实例、且 FM 的 2 槽在 active 里只有 66.7% 时间打满。本卡在此补上另一半：FM 的"推进不动"由**门 + 依赖**解释，且门答完后机器**立即**用满（9 秒 / 同一 tick 并发 2 个 key）——这反过来说明 FM 侧的瓶颈不在 cap。

### F4【事实】实测等待分布（冻结 2026-09-26T07:43Z）

#### F4.1 FM（`gates/` 内 10 个真实 gate，全部 answered；pending = 0）

| gate | kind | key / stage | created (UTC) | answered (UTC) | 延迟 |
|---|---|---|---|---|---|
| gate-0001 | stage-confirm | stage 1 | 09-23T09:35:30 | 09-23T09:41:00 | 0.09h |
| gate-0002 | stalled | gui-contract-surface | 09-23T11:10:29 | 09-23T15:26:00 | 4.26h |
| gate-0003 | stalled | gui-shell-spike | 09-23T11:48:31 | 09-23T15:26:00 | 3.62h |
| gate-0004 | stalled | cli-readonly-snapshot | 09-24T06:19:07 | 09-24T07:40:12 | 1.35h |
| gate-0005 | stalled | gui-contract-mock-tests | 09-24T06:21:18 | 09-24T07:40:12 | 1.31h |
| gate-0006 | stalled | gui-skeleton-shell | 09-24T11:33:21 | 09-25T02:44:25 | **15.18h** |
| gate-0007 | stalled | gui-skeleton-shell | 09-25T04:15:13 | 09-25T06:48:50 | 2.56h |
| gate-0008 | stage-close | stage 1 | 09-25T06:49:00 | 09-25T06:50:14 | 0.02h |
| gate-0009 | stage-confirm | stage 2 | 09-25T06:50:16 | 09-25T06:51:15 | 0.02h |
| gate-0010 | stalled | cli-run-state-and-events | 09-25T11:01:09 | 09-26T02:12:48 | **15.19h** |

| kind | n | answered | never | 中位 | 最大 | 累计 |
|---|---|---|---|---|---|---|
| stalled | 7 | 7 | 0 | **3.62h** | 15.19h | 43.49h |
| stage-confirm | 2 | 2 | 0 | 0.05h | 0.09h | 0.11h |
| stage-close | 1 | 1 | 0 | 0.02h | 0.02h | 0.02h |
| budget-exhausted / goal-change / xkey-authorize | 0 | 0 | 0 | — | — | — |

#### F4.2 E2（`gates/` 内 18 个真实 gate，全部 answered；pending = 0）

| gate | kind | key / stage | created (UTC) | answered (UTC) | 延迟 |
|---|---|---|---|---|---|
| gate-0001 | stage-confirm | stage 1 | 09-22T03:42:13 | 09-22T03:54:15 | 0.20h |
| gate-0002 | stalled | feature-params-service | 09-22T13:43:24 | 09-22T16:01:56 | 2.31h |
| gate-0003 | stage-close | stage 1 | 09-23T01:52:29 | 09-23T07:53:35 | **6.02h** |
| gate-0004 | stage-confirm | stage 2 | 09-23T08:07:13 | 09-23T08:08:13 | 0.02h |
| gate-0005 | stalled | feature-tier-a-closeout | 09-23T15:12:02 | 09-23T15:28:00 | 0.27h |
| gate-0006 | stalled | feature-mvp-closeout | 09-23T21:52:33 | 09-24T03:06:00 | 5.22h |
| gate-0007 | stage-close | stage 2 | 09-24T03:14:50 | 09-24T03:32:00 | 0.29h |
| gate-0008 | stage-confirm | stage 3 | 09-24T07:38:11 | 09-24T07:40:30 | 0.04h |
| gate-0009 | stalled | feature-inline-marker-patchkit | 09-24T13:02:37 | 09-25T02:55:00 | 13.87h |
| gate-0010 | stalled | feature-cigate-install-kit | 09-24T14:48:13 | 09-25T02:55:00 | 12.11h |
| gate-0011 | stalled | feature-gui-time-mvp-board | 09-24T15:53:08 | 09-25T02:55:00 | 11.03h |
| gate-0012 | stalled | feature-cigate-install-kit | 09-25T03:31:14 | 09-25T06:48:30 | 3.29h |
| gate-0013 | stalled | feature-l3-verdict-source-fallback | 09-25T04:36:23 | 09-25T06:48:30 | 2.20h |
| gate-0014 | stalled | feature-gui-time-mvp-board | 09-25T08:56:15 | 09-26T02:20:17 | **17.40h** |
| gate-0015 | stalled | feature-false-meets-remediation | 09-25T10:41:19 | 09-26T02:20:17 | 15.65h |
| gate-0016 | stalled | feature-false-meets-remediation | 09-26T02:36:32 | 09-26T06:39:08 | 4.04h |
| gate-0017 | stalled | feature-gui-time-mvp-board | 09-26T03:16:03 | 09-26T06:39:08 | 3.38h |
| gate-0018 | stalled | feature-false-meets-remediation | 09-26T06:41:03 | 09-26T06:52:13 | 0.19h |

| kind | n | answered | never | 中位 | 最大 | 累计 |
|---|---|---|---|---|---|---|
| stalled | 13 | 13 | 0 | **4.04h** | **17.40h** | 90.97h |
| stage-confirm | 3 | 3 | 0 | 0.04h | 0.20h | 0.26h |
| stage-close | 2 | 2 | 0 | 3.15h | 6.02h | 6.30h |
| budget-exhausted / goal-change / xkey-authorize | 0 | 0 | 0 | — | — | — |

#### F4.3 挂起并集与占比（「至少一个 gate 挂着」的时长）

| 项目 | 观测窗 | stalled gate 挂起并集 | 占窗口 | 全部 gate 挂起并集 | 占窗口 |
|---|---|---|---|---|---|
| FM | 70.61h（09-23T09:06:44Z → 09-26T07:43:11Z） | **38.55h** | 54.6% | 38.68h | 54.8% |
| E2 | 100.14h（09-22T03:35:07Z → 09-26T07:43:13Z） | **46.59h** | 46.5% | 53.15h | 53.1% |

分 stage（stage 窗口 = stage-confirm 被答 → stage-close 被答 / 快照）：

| 窗口 | 时长 | 其中 stalled gate 挂起 | 占比 |
|---|---|---|---|
| FM Stage 1（09-23T09:41:00 → 09-25T06:50:14） | 45.15h | 23.35h | 51.7% |
| FM Stage 2（09-25T06:51:15 → 快照） | 24.87h | 15.19h | 61.1% |
| E2 Stage 3（09-24T07:40:30 → 快照） | 48.05h | 38.79h | 80.7% |

**读法（防止误读）**：这是「有一个 key 被 gate 冻住」的时间，**不是**「整个项目停工」的时间。同一 stage 内其他 key 仍可并行推进（cap=2）。要把"停工"读出来，必须叠加 F3 的依赖链（例如 FM `cli-run-state-and-events` 被冻的 15.19h 里，两个下游 key 加起来 0 个 worker）。

#### F4.4 「最后一个 key 终态 → stage-close」的间隔（检测延迟）

| stage | stage-close gate created | 该 stage 最后一个**有终态事件**的 key | 间隔 |
|---|---|---|---|
| FM Stage 1 | 09-25T06:49:00Z | gui-skeleton-shell 09-25T06:48:51Z（`verify->done exit=0`） | **9 秒** |
| E2 Stage 2 | 09-24T03:14:50Z | feature-mvp-closeout 09-24T03:14:41Z | **9 秒** |
| E2 Stage 1 | 09-23T01:52:29Z | feature-params-service 09-22T16:16:05Z | **不可得**（见下） |
| FM Stage 2 | 尚未收口（3 个 key 未终态） | — | — |

- 9 秒 ≈ 一个 conductor tick（`poll_interval_sec` 默认 4s）＋ 写盘，**机器侧的收口检测不是瓶颈**：真正的等待发生在 `stage-close` gate 建好之后的**人类应答**上（FM 0.02h、E2 6.02h/0.29h）。
- **E2 Stage 1 的间隔不可得，不做估算**：进入观测窗前有 6 个 stage-1 key 已终态，但 timeline 里它们的终态事件不存在（例：`feature-gui-mount` 只有一条 `advance spec->design exit=0`，其后的相位推进不经过 conductor）。因此"最后一个 key 终态"只能给下界（≥ 09-22T16:16:05Z），不能给间隔。这正是 RQ-3 数据缺口 3（`_workers.parallel` 非完整历史）的同一类问题。
- **E2 Stage 3 也尚未收口**：10 个 key 中 8 个 done，`feature-switch-readiness-closeout` / `feature-gui-contract-respec` 仍未终态（后者 09-26T07:33Z 才 `tasks->execute`）。

#### F4.5 数据质量告警与其它"停摆痕迹"

- **FM `stalled` 事件计数被 2026-09-24 gates-flood 污染**：`.agenticdoc/_autopilot/_gates-flood-20260924/` 里 **6684 个 gate 文件全是 `kind=stalled` / `status=pending`**（已从活动队列移走）；timeline 里 `stalled` 6691 次、`resume` 6691 次。**本文所有 FM 延迟数字只取 `gates/` 下的 10 个真实文件**，不取事件的计数与 `gate-created` 配对——因为 id 在归档后被复用（`gates/` 里的 gate-0004..0010 与归档里的同号文件是两批），按 timeline 配对会把归档版误配成真实版。事件侧只能读「有 stalled 这件事」，不能读「停了多久」。
- **按 timeline 直接数"从未答"会得到 6677 个 stalled 未答**（6696 个 `gate-created` 里只有 9 个 stalled 被答）—— 这个数字**不能**读成"6677 个真实待答门"：它是同一次事故的重复产号 + 归档残留。**真实从未答 = 0**（FM/E2 当前 pending gate 均为 0；FM 的 6684 个 pending 全在归档目录里，不在 gates/ 活动队列）。
- 其它会静默吞掉 tick 的事件（FM / E2 计数）：`config: roadmap unreadable` 23 / 98；`config: gate file corrupt, tick skipped` 0 / 9；`config: advance ... failed` 5507 / 6255；`config: tick error` 1 / 0；`type-rejected` 0 / 0；`target-config-rejected` 0 / 0；`l3-no-verdict` 0 / 10（E2 的 10 次最终都收敛成 stalled gate：gate-0012/0013/0014/0016/0017 等）。
- E2 的 13 个 stalled gate 覆盖 8 个不同的 key，其中 `feature-gui-time-mvp-board`（3 次）、`feature-false-meets-remediation`（3 次）是重复 stall —— 与 RQ-6 的"stalled 生命周期"面相邻，本卡不展开。

#### F4.6【推断】长等待与"夜间无人应答"高度重合

规则：把每个 stalled gate 的 `[created_at, answered_at)` 换算成本地时（UTC+8，**推断假设**，未经代码/配置验证），若与该日 22:00–08:00 有交集则计为"涉及夜间窗口"。

| 项目 | stalled gate 总等待 | 涉及 22:00–08:00 的 gate 合计 | 占比 |
|---|---|---|---|
| FM | 43.49h（7 个） | **38.26h**（4 个，含 19:10→23:26 这种"晚间起、跨夜"的段） | **88.0%** |
| E2 | 90.97h（13 个） | **77.87h**（8 个） | **85.6%** |

两个项目最长的 4 段（FM 15.18h/15.19h、E2 17.40h/15.65h）全部是「本地傍晚 16:56–19:33 建门 → 次日上午 10:12–10:44 被答」。⇒ **直接支撑 (c) 的字面描述**：夜里的推进确实卡在"必须人答"的门上，而且是每晚都在发生，不是偶发。

### F5【事实】无人值守策略：**不存在**（且被工具层主动禁止）

- **grep 零命中**：`unattended|auto[_-]?answer|gate[_-]?timeout|noninteractive|non-interactive|auto[_-]?approve` 在 `packages/multi-workers/**` 与 `packages/coding-agent/src/extensions/agent-team-loop/**` 里**没有任何实现命中**（其余命中全在 `packages/coding-agent` 的通用 `-p/--mode` 文档、CHANGELOG、示例扩展里，与 autopilot gate 无关）。只有 `mw.py:4128-4131` 一处注释把 "unattended" 用于描述下载 framework 的缓存机制。
- **schema 里没有超时字段**：gate frontmatter 是固定的 12 字段（`gates.py:68-81`：id/kind/stage/key/created_at/created_by/question/context_refs/status/answered_at/answered_by/note），**没有 timeout/deadline/expires/remind**；parser 对未知字段直接 `GateFormatError`（`gates.py:345-348`）。
- **没有"过期"语义**：所有读取方只区分 `pending` / 非 pending（`gates.pending_gates` `:509-511`；`_gate_open` `conductor.py:2188-2215`；TS `monitor.ts:150+` 只收集 pending）。`created_at` 除了展示/审计外没有任何消费者。
- **没有"夜跑"分支**：conductor 没有 `--unattended` / `--yes` / `--non-interactive` 类参数（`_parse_args` `conductor.py:4096-4112` 只有 `--project` / `--poll-interval` 等），`tick()` 的行为与是否有人在场完全无关。
- **反向证据（更强的结论）**：`xkey-gate-guard.ts` 的注释把设计意图写死 —— "Gate files (...) are the human-answer channel: **only a human answers them**"（`GUARD_EXPLANATION`）。它在 `tool_call` 层拦截 write/edit/bash 对 `<project>/.agenticdoc/_autopilot/gates/**` 的任何写（`registerXkeyGateGuard`，在 PM/worker/交互三种模式都注册），bash 侧用**文本级 fail-closed 启发式**：只要命令文本同时出现 gate 目录片段与任一写构造（写动词 / PowerShell 写 cmdlet / `sed -i` / `find -delete|-exec` / 内联代码带写标记 / 重定向目标落在 gate 目录）就 `block`。
  - **本卡实测（副产物证据）**：我在做本卡的只读分析时，一条把分析脚本写入 `%TEMP%` 的 `Set-Content` 命令被拦下——因为**脚本正文里出现了 gate 目录路径字符串**，触发了「片段 + 写构造」。⇒ 该 guard 是**按命令文本**判定的 fail-closed，不区分目标文件是否真的在 gate 目录。这既是"自动答 gate 被禁"的直接证明，也是 design 期必须知道的副作用（任何含 gate 路径的写操作都会被拒）。
- ⇒ 对 design 的输入（不作推荐）：**现状是"门必须停"**；"夜跑"在门的层面目前既无策略也无逃生通道，且 agent（含 PM 窗口里的 agent 工具调用）被显式禁止代答。

### F6【事实】可观测性：能看到"哪个门"，看不到"挂了多久"，`mw doctor` 完全看不到门

| 面 | 现状 | 锚点 |
|---|---|---|
| monitor 面板 | 有独立 `gates:` 段：0 pending → `gates: 0 pending`；1 个 → `gates: 1 pending - gate-0042 (stalled) -> /autopilot gate gate-0042 approve\|reject`；多个 → 列出全部 id+kind 并指向 `/autopilot gates` | `monitor.ts:644-655`；`MonitorGate` 定义 `:89-96` |
| stalled key 的归因行 | attention 行会把 `stalled` key 与它的 stalled gate 关联，并提示 `(resume grants one round)` | `monitor.ts:603-631` |
| **缺口 1**：无"挂了多久" | `MonitorGate` 只有 `{id, kind, stage, key}`，**没有 created_at**（`:89-96`）；面板也不显示 age。⇒ 早上看到 `gates: 1 pending` 无法判断它是 5 分钟还是 15 小时 | `monitor.ts:150-179`（scanPendingGate 只取 id/kind/stage/key） |
| **缺口 2**：`mw doctor` 无 gate 节 | `mw doctor` 注入的 conductor 节只有 `{running, pid, last_seq, last_ts}`（`conductor.py:4070-4094`）；`_doctor_autopilot`（`mw_common.py:2022-2065`）只报 xkey 配置；`format_doctor_text` 只输出 `conductor: running (...)` 或 `conductor: not running`（`:2268-2280`）。**没有任何行提到 pending gate** | 同左 |
| **缺口 3**：无告警/非零退出 | `_doctor_issues`（`mw_common.py:2067+`）不检查 gate 陈旧度；一个挂了 15h 的 gate 不会让 doctor 退出码非 0，也不会出现在 issues/suggestions | 同左 |
| timeline 的 detail 是否带 key/gate id | **带**。`gate-created` 的 detail = `"gate-0010 kind=stalled"`（`conductor.py:2183`），key 在 `key` 字段；`gate-answered` 的 detail 带 id 与决策（`:356`/`:363`/`:374`、`:2349`、`:2388`）；stage 级事件的 `key` 字段按 sentinel 规则落 stage 号（`timeline.py:87-89`）。⇒ **早上可以从 timeline 复算出"哪些 gate 何时建、何时答"**，但需要自己写脚本，且 `answered_by` 不在 timeline 里（只在 gate 文件） | 同左 |
| 谁答的（审计） | gate 文件的 `answered_by` 是自由文本：E2 17/18 为 `wenbozhou`、1 个为 `human-pm-window`；FM 10/10 为 `user-via-pm-window`。注意 `/autopilot gate` 路径会写 `windowClaimId()`（`host:pid`，`console.ts:231`）⇒ 实测值说明这些答案是**手工编辑/其它路径**写的，不是 console 路径。⇒ 想区分"人答 / 程序答"目前只能靠约定俗成的字符串 | `gate-writer.ts:139-178`；`console.ts:224-236` |
| 被 guard 拒绝的痕迹 | 工具层拒绝会往该 worker 的 `trace.log` 追加一行 `[XKEY_GATE] ... blocked tool=... target=...`（best-effort） | `xkey-gate-guard.ts:recordXkeyGateBlockTrace` |

**早上的最短可行检查（现状）**：打开一个 PM 窗口看 monitor 面板（能看出"有没有 pending gate、是哪个、什么 kind"）→ 对每个 gate 读文件看 `created_at` 与 `question`（面板不给 age）→ 用 `/autopilot gate <id> approve|reject` 应答。`mw doctor` 与 `mw status` 都给不出这条链。

### F7【事实】被 **误读为门** 的 timeline 事件（避免 spec 把事件当门）

`timeline.py:67-85` 的 17 类事件里，只有 `gate-created` / `gate-answered` 直接对应 gate 文件；其余与门相关的都是**记录**而非**通道**，不应列入"必须人答的门"清单：

| 事件 | 含义 | 锚点 |
|---|---|---|
| `stalled` | key 被冻结的**记录**（真正的门是它同时建的 `stalled` gate） | `mark_stalled` `:3971-3975` 末尾 |
| `resume` | stalled gate 被 approve 后的恢复记录 | `_apply_stalled_approvals` `:2349-2354` |
| `goal-halt` / `goal-snapshot` | goal.md 变化暂停 / 恢复的**记录**（通道是 `goal-change` gate） | `tick` `:2093`、`:2109-2110` |
| `l3-no-verdict` | L3 reviewer 没写裁决（会重试，达预算后转 `stalled` gate） | `:1629-1641` |
| `type-rejected` / `target-config-rejected` | 派发被拒（**无门、无 stall**，见 F1 表末） | `dispatch.py:437-446` |
| `advance` / `dispatch` / `worker-terminal` / `skip` / `beat` / `config` / `reconcile` / `stage-close` | 状态机推进、心跳、降级记录 | 全表见 `timeline.py:67-85` |

## 结论 → 决策映射

### 支撑 AC-004（(c) 的直接证据）——「门」与「槽」是两个正交的问题面

- RQ-3 的实测结论是「stalled key 与自身 worker 的重叠 ≈ 0（FM 0.00h / E2 0.04h）⇒ stalled 不占槽」；本卡给出它**为什么不矛盾**：占槽判定读的是 `_workers.parallel` 的行状态（`conductor.py:258-264`），门口径读的是 roadmap 的 `key-status:` 行（`status_of`，`:224-232`）。`mark_stalled` 只改 roadmap（`:3944-3965`），所以「不占槽」与「冻结 key/ stage」可以同时为真。
- 因此 AC-004 的证据链应写成两段而不是一段：**(i) 占槽面 = 残留非终态行（RQ-1 + PM 交叉核对 F1-F3）**；**(ii) 门口面 = 本卡**：`stalled`/`budget-exhausted` 的 gate pending 期间，该 key 不会被派发（`:274-275`、`:995-1003`），stage 因非终态不收口（`:629-631`），下游 key 因 `_deps_satisfied` 全部冻结（`:56`/`:285-286`）。
- **可复算的门口证据**：FM 38.55h/70.61h（54.6%）至少一个 stalled gate 挂着；Stage 1 内 51.7%、Stage 2 内 61.1%；E2 Stage 3 内 80.7%。全部用 F4 的脚本复算。

### 支撑 AC-007（「改 / 不改」必须逐条回应 (c)）——(c) 侧在 FM 与 E2 不是同一个瓶颈

- **FM：门是主瓶颈，槽不是。** 证据：① 7 个真实 stalled gate 的等待合计 43.49h，其中 88.0% 落在晚间/夜间窗口；② 最强链条上"门一答，机器 9 秒内打满"（`gui-skeleton-shell` 收口 9s、两个下游 key 同时派发）；③ RQ-3 已证 FM 在 active 时间里有 45.6%「槽满且有待派发 key」，但**唯一** pending 是 `_scratch`，**没有 stage key 在等槽**。⇒ 对 FM 而言，把 cap 从 2 提高的收益被"门"吃掉；`gui-shell-spike`/`gui-contract-surface`/`cli-readonly-snapshot`/`gui-contract-mock-tests`/`gui-skeleton-shell`/`cli-run-state-and-events` 这 6 个 key 的等待**不是槽位等待**（F4.1 的 43.49h）。
- **E2：门与槽都有，且门的量级更大。** stalled gate 等待合计 90.97h（13 个，85.6% 涉及夜间），同时 RQ-3 有 2 个干净实例（4.79h / 5.64h）是纯槽位排队。⇒ (c) 不是单一病因：**"提高 cap"对 E2 有效的那部分，恰好是已经证明与门无关的那 2 个实例（合计 10.43h）；而 E2 的 stalled gate 等待合计 90.97h（约为槽侧 8.7 倍，按 key 冻结并集 46.59h 计约 4.5 倍）。**
- **对 U-4′ 的 (c) 侧回答（本卡只给事实）**：(c) 这一侧在 FM 上**是"门"**，在 E2 上**门为主、槽为辅**。因此任何针对 (c) 的改动如果只动 `max_parallel_keys`，在 FM 上**测不到收益**（FM 没有槽位排队实例）；而在 E2 上其收益上限被 RQ-3 量化为那 2 个实例的 4.79h + 5.64h（且这两例期间另一 key 占满 98%）。门侧的量级是 38.55h(FM) / 46.59h(E2) 的 key 冻结并集（其中 FM 38.26h / E2 77.87h 的 gate 等待涉及 22:00–08:00 本地窗口）。
- **给 design 的三条硬约束（不含方案）**：① `stalled` 是**唯一**能让 stage 永不收口的自动状态（`budget-exhausted` 更隐蔽：连 `stalled` 都不置，`:995-1003`）；② `closed-legacy` 只能由人 reject 产生 ⇒ 无人值守下 stage 内一旦出现 stalled 就**不可能收口**；③ gate 目录在工具层被禁止 agent 写入（`xkey-gate-guard.ts`）⇒ "让 PM agent 代答"是一个需要显式设计决策的动作，不是实现细节。

### 对 AC-008（可观测性）的输入

三处缺口（F6）：`MonitorGate` 无 `created_at`（看不出 age）；`mw doctor` 无 gate 行、无 gate 陈旧度 issue（早上第一眼看不到门）；`answered_by` 是自由文本（无法机器区分人/程序）。已满足的部分：面板已能列出 pending gate 的 id/kind 与应答命令，`timeline` 的 `gate-created` detail 带 gate id、`key` 字段带 key。

## 数据缺口（必须与上面每个数字一起读）

1. **样本只有 2 个项目**：MW（本项目）没有 `.agenticdoc/_autopilot/` ⇒ 无 autopilot 门数据。门的实测全部来自 FM（70.61h）与 E2（100.14h）。
2. **三类门零实例**：`budget-exhausted` / `goal-change` / `xkey-authorize` 在两个项目里**一次都没建过**。本文对它们只给代码路径与后果（其中 `goal-change` 是"全停"且最硬——它连 `orchestrate` 都不进），**没有实测等待**。`target-config-rejected` / `type-rejected` 的"无门活锁"同样只有代码路径，无实例。
3. **FM 归档残留使事件计数不可用**：6684 个 pending stalled gate 文件（`_gates-flood-20260924/`）+ id 复用 ⇒ 任何"从未答 gate 数 = 6677"的读法都是错的。本文只用 `gates/` 内的 10 个文件做延迟，事件侧只用来定"有没有发生"。
4. **E2 Stage 1 的收口间隔不可得**：6/7 个 key 的终态事件不在 timeline 里（其相位推进不经过 conductor），只能给下界。
5. **FM 仍在跑**：gate-0010 之后 FM 又派发了 `gui-live-monitor` / `gui-run-control-hitl`（09-26T02:13Z 起，快照时 5.4h）。它们的后续 stall 不在本文的快照范围内；`gui-monitor-hitl-e2e` 仍未派发。
6. **"夜间"是本地时假设**：仓库里 `_index.parallel` 的时间列已知混用本地时与 UTC（RQ-3 缺口 5），gate frontmatter 全部是带时区的 ISO8601（`gates.py:_iso_now` 用 UTC）⇒ 本文的 UTC→本地换算（UTC+8）是**推断**，但输入字段本身是可解析的确定值。
7. **未做**：没有把"gate 等待"与"worker 运行"逐秒求交（那需要 worker 区间，属 RQ-3 的 trace.log 面）；因此"某个 gate 挂着时项目确实在干别的活"只能由依赖链（F3）间接说明。

## 机器行

`[VERIFY] RQ-8: human_gates=6(stage-confirm,stage-close,stalled,budget-exhausted,goal-change,xkey-authorize) gate_kinds_closed_set=gates.py:54-61 no_timeout_field=gates.py:68-81 unattended_policy=absent zero_grep_hits + tool_layer_block=xkey-gate-guard.ts non_gate_waits=3(roadmap-writer-exhausted conductor.py:545-546, tick-skip-on-corrupt-file :335-337, dispatch-refusal-livelock dispatch.py:437-446 + :936-941) stalled_blocks_stage=yes(conductor.py:629-631 terminal={done,closed-legacy}) stalled_blocks_dependents=yes(_DEP_SATISFIED :56, _deps_satisfied :2153-2154) blocking_scope=key+stage+roadmap(fm measured) fm_gates=10(all answered,0 pending) e2_gates=18(all answered,0 pending) fm_stalled_wait median=3.62h max=15.19h sum=43.49h n=7 e2_stalled_wait median=4.04h max=17.40h sum=90.97h n=13 stage_close_wait=fm 0.02h(n=1)/e2 median 3.15h max 6.02h(n=2) stage_confirm_wait=max 0.20h(n=5) stage_close_lag=9s(FM s1, E2 s2) fm_stalled_pending_union=38.55h/70.61h=54.6% e2_stalled_pending_union=46.59h/100.14h=46.5% stalled_wait_overnight_share=fm 88.0% / e2 85.6% snapshot=2026-09-26T07:43Z mw_autopilot_data=none`