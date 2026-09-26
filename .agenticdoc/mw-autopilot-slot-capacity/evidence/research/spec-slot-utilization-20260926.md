# Research: 槽位利用率与槽位等待的实测（RQ-3 / spec 期，只读）

> Key: mw-autopilot-slot-capacity ｜ 角色: research（只读，未改任何项目数据）
> 快照时间: 2026-09-26T07:36Z（FM/E2 的 autopilot 仍在跑，见"数据缺口"的时间冻结说明）

## TL;DR

- **可用样本只有 2 个项目（FM、E2）**：MW 的 `.agenticdoc/` 下**没有** `_autopilot/`、也**没有**任何 `ap-*` worker —— MW 从未跑过 autopilot，任务给的三个项目实际只有两个可用。
- **打满率**：在"至少 1 个 key 在飞"的时间里，两个项目有 **62.9%（E2）/ 66.7%（FM）** 的时间是 2 个 key 同时在飞（= `max_parallel_keys`=2 打满）。按整个观测窗算是 29.6% / 20.0%。
- **直接证据：没有。** 代码里 cap 命中是**静默 `continue`**（`conductor.py:289`），timeline 的 17 种事件类型里没有任何"因槽位满而未派发"的事件；对 188,534 条事件做 `cap|parallel|slot|defer|skip` 全量扫描，没有任何一条在讲槽位。这一条是"无直接证据"，不能靠日志证伪。
- **间接证据：E2 有，FM 没有单个实例。** E2 在两个槽都被占满的采样时刻里，有 **194 个采样点**同时存在 ≥1 个"非终态、无 worker、下一轮还会被派发"的 key（最多 4 个）；有 2 个可复算的具体实例（各 4.8h / 5.6h 的纯等待，期间其他 key 占满两槽 98%/98%）。FM 的同类采样只有 86 个，且唯一"空闲待派发"的 key 是 `_scratch`（roadmap-writer，不是 stage key），**没有 stage key 排队等槽的实例**。
- **stalled 占槽 ≈ 0**：stalled key 与"它自己的 worker"重叠时间 **FM 0.00h / E2 0.04h（2.5 分钟）**。stalled key 是**被跳过**的（`conductor.py:274`），不占槽；"提高上限只让更多 key 一起卡住"这个假设**在槽位口径上不成立**（挡的是 key 队列，不是槽）。
- **并发没有让 worker 变慢、也没有让失败率升高**（可测的证据方向相反或无关）：worker 墙钟中位数 conc=1 → 656s（FM）/520s（E2），conc=2 → 672s/532s；失败率 conc=1 → 3.90%/1.94%，conc=2 → 4.13%/4.64%（E2 Fisher 单边 p=0.11，n=18，不显著）。全部失败都是**看门狗超时**（idle 600s / wall 3600s），**零** rate-limit/429 证据。
- **机器层不紧张**：FM+E2 重叠的 70.49h 里，两台项目同时有 key 在飞只有 13.42h（19.0%）；机器层"4 槽"（2 项目 × 2）打满只有 **4.30h（占 active 10.8%）**。真正紧的是**单项目内**的 2 槽。

`[VERIFY] RQ-3: projects=2 usable (FM,E2) + 1 gap (MW: no _autopilot) window=2026-09-22T03:35Z..2026-09-26T07:36Z max_overlap=3 (autopilot; 4 transient, PM-manual) saturation=62.9%(E2)/66.7%(FM) of active stalled_slot_pct=0.00%(FM)/0.02%(E2) cap_skip_evidence=no-direct / yes-indirect(E2)`

## 决策问题

支撑 spec **draft AC-003**（"实测吞吐证据：槽位利用率 + 槽位等待"，样本量与时间窗）与 **§4 U-2**（"并行度不够的具体现象是什么"）、并给 **§4 风险 1**（槽位被 stalled key 占住）一个可复算的判定：

1. 槽位真的不够吗？——用历史运行数据算"打满率"与"等待"。
2. 打满时有没有 key 在排队？（直接事件 / 间接实例）
3. 槽位被 stalled 的 key 占了多少时间？（决定"提高上限有没有收益"）
4. 高并发时 worker 更慢 / 更容易失败吗？

**边界**：本笔记只做测量与判定，不给方案（RQ-4）。**未修改任何被观测项目的数据**；唯一写入是本文件。

## 调研方法与出处

### 数据文件清单（路径 + 大小 + 行数 + 时间窗，均为只读读取）

| 项目 | 文件 | 大小 B | 行数 | 时间窗（UTC） |
|---|---|---|---|---|
| FM | `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\timeline.jsonl` | 3,335,639 | 31,619 | 2026-09-24T16:19:31 → 2026-09-26T07:34:51 |
| FM | `...\_autopilot\timeline.jsonl.1`（轮转代，seq 1..60035，完整未丢） | 10,485,844 | 60,035 | 2026-09-23T09:06:44 → 2026-09-24T16:19:27 |
| FM | `...\_autopilot\config.json` | 227 | 11 | `max_parallel_keys: 2` |
| FM | `...\_workers.parallel` | 55,387 | 231 | 2026-09-17T03:48 → 2026-09-26T06:35（仅保留近期行，见缺口） |
| FM | `...\_index.parallel` / `_autopilot\_roadmap.md` | 3,684 / 5,056 | 45 / 40 | 当前态 |
| FM | `...\<key>\workers\<task>\trace.log` | — | **232** 个文件 | 2026-09-17T03:48:28 → 2026-09-26T07:36:00 |
| E2 | `H:\git\E2Feature\.agenticdoc\_autopilot\timeline.jsonl` | 1,751,954 | 16,631 | 2026-09-25T10:36:36 → 2026-09-26T07:34:50 |
| E2 | `...\_autopilot\timeline.jsonl.1`（seq 1..80243，完整未丢） | 10,485,792 | 80,243 | 2026-09-22T03:35:07 → 2026-09-25T10:36:31 |
| E2 | `...\_autopilot\config.json` | 200 | 10 | `max_parallel_keys: 2` |
| E2 | `...\_workers.parallel` | 127,215 | 485 | 2026-09-20T08:04 → 2026-09-26T06:52 |
| E2 | `...\_index.parallel` / `_autopilot\_roadmap.md` | 3,003 / 19,853 | 29 / 50 | 当前态 |
| E2 | `...\<key>\workers\<task>\trace.log` | — | **485** 个文件 | 2026-09-20T08:04:23 → 2026-09-26T07:35:51 |
| MW | `.agenticdoc\_autopilot\` | **不存在** | — | — |
| MW | `.agenticdoc\_workers.parallel` | 34,611 | 176 | 2026-08-28T13:00 → 2026-09-26T15:29（**无 `ap-*` 行**） |
| MW | `...\<key>\workers\<task>\trace.log` | — | 169 个文件，**0 个 `ap-*`** | 2026-09-09T04:23 → 2026-09-26T07:34 |
| JC（额外发现，非任务指定） | `H:\git\JCodingAss\.agenticdoc\_autopilot\timeline.jsonl` | 249,069 | 2,349 | 2026-09-26T04:37:26 → 2026-09-26T07:32（几乎全是 `beat`：`gate-created`×1 / `gate-answered`×1 / `config`×0，worker 全在窗口之外 ⇒ 不可用） |

**观测窗定义**：FM = timeline 首行 ts → 快照时最后一个 trace 行 ts = **2026-09-23T09:06:44Z → 2026-09-26T07:34:51Z（70.47h）**；E2 = **2026-09-22T03:35:07Z → 2026-09-26T07:34:50Z（100.00h）**。之所以用 timeline 窗而不是 `_workers.parallel` 窗，是因为后者会保留少量 autopilot 之前的行（FM 最早 09-17、E2 最早 09-20），会把"没开 autopilot 的手工期"混进打满率。

### 算法（定义逐条固定，任何人可复算）

以 **worker 为单位的时间区间**作为唯一原始量，key 由**目录归属**给出（`<root>\.agenticdoc\<key>\workers\<task_key>\trace.log` ⇒ key = `<key>` 段；这也与 conductor 的"owner key"口径一致）：

1. **worker 区间** = trace.log 里 `[START] <ISO> task=... type=...` 的 ts → `[END] <ISO> exit=N elapsed=Ns` 的 ts。无 `[END]`（截断/崩溃）时取该文件最后一条带时间戳的行（本次快照 FM 1 个、E2 1 个仍在跑，已标注为 censored）。
2. **t 时刻在飞 key 集合** `ic(t)` = { key : 存在 worker 区间 [a,b) 使 a ≤ t < b }。
3. **打满率** = `Σ dt{ |ic(t)| ≥ max_parallel_keys }` ÷ 分母。分母给两个：`window`（观测窗总时长）与 `active`（`|ic(t)| ≥ 1` 的时长）。
4. **等待 key** `pending(t)` = { key : 有区间结束于 ≤ t，有区间开始于 > t，且 t 时刻没有区间覆盖 }（即"非终态、当前没有 worker、之后还会再派发"）。
5. **打满且有待派发** = `|ic(t)| ≥ 2 且 pending(t) ≠ ∅` 的时长。
6. **stalled 区间** = timeline 的 `stalled` 事件 → 其后第一个同 key 的 `resume` 事件（无 resume 则到窗末），同 key 相邻区间合并；跨 key 取**并集**。`stalled 占槽` = stalled 区间与**该 key 自己**的 worker 区间的重叠（只有这种重叠才是"槽被 stalled key 占着"）。
7. **cap 越界** = `|ic(t)| > 2` 的区间（合并相邻）。
8. **失败** = `[END] exit ≠ 0`（另计 `[TIMEOUT]` 行的类型：`idle:` = 活动看门狗、`wall:` = 墙钟兜底）；**失败率 vs 并发**按失败 worker 的 `[START]` 时刻的 `|ic|` 分桶。
9. **key 吞吐**（EXECUTE→DONE）= 该 key 最早一条 `ap-<key>-0NN-*` worker 的 `[START]` → timeline 中该 key 的 `advance verify->done exit=0` 事件 ts。

### 复算脚本（关键片段，Windows PowerShell + Python 3.14；脚本写在 `%TEMP%`，未落在任何项目目录）

```python
import os, re, datetime as dt, collections
def P(s): return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
START_RE=re.compile(r"^\[START\]\s+(\S+)\s+task=(\S+)\s+type=(\S+)")
END_RE  =re.compile(r"^\[END\]\s+(\S+)\s+exit=(-?\d+)\s+elapsed=(\d+)s")
TS_RE   =re.compile(r"^\[\w+\]\s+(\d{4}-\d\d-\d\dT\S+)")

def scan(root):                      # key -> 目录归属；返回 worker 区间
    out=[]
    for key in sorted(os.listdir(root)):
        w=os.path.join(root,key,"workers")
        if not os.path.isdir(w): continue
        for sub in sorted(os.listdir(w)):
            fp=os.path.join(w,sub,"trace.log")
            if not os.path.isfile(fp): continue
            st=en=last=None; ex=None
            for line in open(fp,encoding="utf-8",errors="replace"):
                m=TS_RE.match(line)
                if m:
                    try: t=P(m.group(1))
                    except Exception: t=None
                    if t and (last is None or t>last): last=t
                m=START_RE.match(line)
                if m: st=P(m.group(1))
                m=END_RE.match(line)
                if m: en=P(m.group(1)); ex=int(m.group(2))
            if st: out.append((key,st,en or last or st,ex))   # ex=None => censored
    return out

def sweep(rows, W0, W1, cap=2):      # 用区间端点做扫描线
    byk=collections.defaultdict(list)
    for k,a,b,ex in rows: byk[k].append((a,b))
    pts=sorted({W0,W1} | {max(a,W0) for k,a,b,ex in rows if W0<a<W1}
                     | {min(b,W1) for k,a,b,ex in rows if W0<b<W1})
    tot=act=sat=satpend=0.0; ksum=0.0
    for i in range(len(pts)-1):
        a,b=pts[i],pts[i+1]
        if b<=a: continue
        d=(b-a).total_seconds()
        ic={k for k,v in byk.items() if any(x<=a<y for x,y in v)}
        pend=[k for k,v in byk.items() if k not in ic
              and any(y<=a for x,y in v) and any(x>a for x,y in v)]
        tot+=d; ksum+=len(ic)*d
        if ic: act+=d
        if len(ic)>=cap:
            sat+=d
            if pend: satpend+=d
    return dict(window_h=tot/3600, active_h=act/3600, sat_h=sat/3600,
                sat_pend_h=satpend/3600, sat_pct_window=100*sat/tot,
                sat_pct_active=100*sat/act, mean_keys=ksum/tot,
                mean_keys_active=ksum/act, max_keys=max(len({k for k,v in byk.items()
                    if any(x<=a<y for x,y in v)}) for a in pts))
```

直接跑：`python "%TEMP%\rq3_sum.py"`（本次结果 JSON 与 `rq3_merged.py`/`rq3_pairs.py`/`rq3_stall.py` 同目录）。stalled 区间用 timeline 的 `stalled`/`resume` 配对（见上 §算法 6），一行版：

```python
# 全窗口 stalled 并集（FM 例；E2 换路径即可）
import json, datetime as dt
P = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
ev = [json.loads(l) for f in ("timeline.jsonl.1", "timeline.jsonl")
      for l in open(f, encoding="utf-8", errors="replace")]
ev.sort(key=lambda o: o["seq"])
W1 = P(ev[-1]["ts"])
S = {}; R = {}
for o in ev:
    if o["ev"] == "stalled": S.setdefault(o["key"], []).append(P(o["ts"]))
    elif o["ev"] == "resume": R.setdefault(o["key"], []).append(P(o["ts"]))
iv = []
for k, ss in S.items():
    for s in sorted(ss):
        e = next((r for r in sorted(R.get(k, [])) if r > s), W1)
        iv.append((s, e))
iv.sort(); m = []
for s, e in iv:                       # 相邻/相接区间合并
    if m and s <= m[-1][1]: m[-1] = (m[-1][0], max(m[-1][1], e))
    else: m.append((s, e))
print("stalled union h =", sum((e - s).total_seconds() for s, e in m) / 3600)
```


## 发现

### 指标 1：槽位利用率（key 层，cap=2）

| 视图 | 窗口 | max_parallel_keys | 窗口 h | active h | 平均 key 数(窗口) | 平均 key 数(active) | max key 数 | 打满 h(≥2) | 打满/窗口 | 打满/active |
|---|---|---|---|---|---|---|---|---|---|---|
| **FM** | 09-23T09:06 → 09-26T07:34 | 2（`_autopilot/config.json`） | 70.47 | 21.14 | 0.501 | **1.669** | 3（仅 2.4 min） | 14.11 | 20.0% | **66.7%** |
| **E2** | 09-22T03:35 → 09-26T07:34 | 2 | 100.00 | 46.99 | 0.768 | **1.634** | 4（仅 10.0 min） | 29.58 | 29.6% | **62.9%** |
| **合并（FM+E2 重叠窗）** | 09-23T09:06 → 09-26T07:36 | 机器层 = 2×2 | 70.49 | 39.79（56.5%） | 1.146 | **2.03** | 5 | 4.30（两项目都满 4 槽） | 6.1% | 10.8% |
| MW | 09-09T04:23 → 09-26T07:34（手工期） | 无 autopilot | 411.19 | 19.06 | 0.046 | 1.000 | **1** | 0.00 | 0.0% | 0.0% |

key 数直方图（小时，FM / E2）：`0 → 49.33 / 53.00`；`1 → 7.03 / 17.35`；`2 → 14.00 / 29.41`；`3 → 0.04 / 0.12`；`4 → 0 / 0.04`。合并视图：`0 → 30.70`；`1 → 6.42`；`2 → 20.14`；`3 → 8.92`；`4 → 4.16`；`5 → 0.14`。

**读法**：两个项目的 autopilot 在"有活干"的时候，**平均只有 1.63–1.67 个 key 在飞（上限 2）**，2 个槽同时被占的时间占 active 的 2/3。也就是说"打满"是**常态**而非偶发；但"打满"不等于"有 key 在排队"（见指标 2）。

**越界（cap > 2）合计极小且可解释**：FM 2 段共 2.4 min、E2 3 段共 10.0 min（含 1 段 3.3 min 的 4-key）。逐段核对后，越界段里多出来的那个 key 的 task.md 是 **`type: coding` 且没有 `origin: conductor`**（例：`H:\git\E2Feature\.agenticdoc\feature-cigate-install-kit\workers\ap-feature-cigate-install-kit-repair-a3-achieved-terminal\task.md`），即 **PM 主窗口手工派发**，不经过 conductor 的 cap 判定 —— 不是 cap 漏判。

**最强的时间结构证据是"固定配对"**：两槽长时间被**同两个 key** 占据 —— FM `gui-live-monitor × gui-run-control-hitl` 4.32h、`cli-hitl-channel × cli-run-state-and-events` 4.08h；E2 `feature-tier-a-closeout × feature-trend-two-points` 5.87h、`feature-cigate-install-kit × feature-inline-marker-patchkit` 4.93h。这正是"硬上限 2 + 按 roadmap 顺序放行"的特征形态。
（复算：`python "%TEMP%\rq3_pairs.py"`。）

### 指标 2：槽位等待

**（a）直接证据：无。**
- 尝试的四个取证面全部为空：① timeline 17 种事件类型（`packages/multi-workers/autopilot/timeline.py:67-84`）**没有任何**"槽位满/defer"事件；② 代码里 cap 命中是**静默** `continue`：`packages/multi-workers/autopilot/conductor.py:289` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])): continue  # parallel cap — key starts on a later tick`；③ 对 FM+E2 共 188,534 条 timeline 事件做 `cap|parallel|slot|defer|skip` 全量扫描：命中 6,691（FM）+ 33（E2）条，逐条看**没有一条在讲槽位** —— 全是 `resume <key> resumed by gate-NNNN (one extra round per capped loop)`、`gate file corrupt, tick skipped`，以及任务名自带 `caps` 的 dispatch 行（`inject-caps-*` / `readcap-*`）；④ FM/E2 的 `_autopilot/` 下无 conductor 日志文件（`grep -i "parallel cap"` 零命中）。
  ⇒ **"因槽位满而未派发"没有任何一条直接记录**，只能靠"当时有没有别的 key 在等"来推断。

**（b）间接证据（可复算的实例）—— E2 有，FM 无 stage-key 实例。**

采样口径：`|ic(t)| ≥ 2 且 pending(t) ≠ ∅` 的区间数（pending 定义见 §算法 4，已排除终态 key）。**FM 86 个采样点（唯一 pending key 是 `_scratch`，即 roadmap-writer，不占 stage key 的槽）**；**E2 194 个采样点**，最大 pending=4。

| 实例 | key | 等待区间（UTC） | 时长 | 该区间内被占满的时间 | 该 key 在区间内的事件 | 前一个 worker | 后一个 worker（锚点） |
|---|---|---|---|---|---|---|---|
| E2-① | `feature-sampling-human-channel` | 09-24T08:02:20 → 09-24T12:49:37 | **4.79h** | 282/288 min = **98%**（另两个 key：cigate-install-kit、inline-marker-patchkit） | **0 条**（无 gate / stalled / resume / advance / skip） | `...spec-writer-a1` `[END] exit=1`（idle 看门狗，840s） | `ap-feature-sampling-human-channel-spec-writer-a2`，`timeline.jsonl.1:62484`（`2026-09-24T12:49:37Z seq=62484`） |
| E2-② | `feature-completeness-four-dim` | 09-23T08:30:54 → 09-23T14:09:05 | **5.64h** | **98%**（其他 key ≥2 在飞） | 1 条：`advance spec->design exit=0`（`timeline.jsonl.1:38204`）——即该 key 已**合法进入下一相位、只等派 design-writer** | `...spec-writer-a1`（dispatch `timeline.jsonl.1:38060`） | `ap-feature-completeness-four-dim-design-writer-a1`，`timeline.jsonl.1:43123` |
| E2-③（最大排队深度） | pending=4 @ `2026-09-24T13:29:53Z` | — | — | 2 槽满（cigate-install-kit、l3-verdict-freshness） | pending = gui-time-mvp-board / inline-marker-patchkit / l3-readcap-injection / sampling-human-channel | — | 4 个 key 的后续 dispatch 分别在 `timeline.jsonl.1:63270`（13:44:59）、`timeline.jsonl.1:63131`（13:35:16 采样）、`timeline.jsonl.1:63478`（13:59:46）等 |

**为什么这是"槽位等待"而不是别的**：E2-① 的 4.79h 里该 key **一条事件都没有**（不是等门禁、不是等人工、不是 claim 冲突——后者会写 `skip` 事件，`conductor.py:281`），同时另外两个 key 占满两槽 98% 的时间；E2-② 同理，唯一事件是"相位已推进、等待下一相位 worker"，即 **ready-to-dispatch 但没抢到槽**。二者都满足"非终态 + 无自身 worker + 其他 key 占满 + 无任何非槽位原因"。

**口径盲区（必须声明）**：`pending(t)` 只认「已经跑过至少一次 worker」的 key；**从未被派发过的 key（等上游依赖、或一直在排队等第一次派发）完全不可见**。例如 FM 的 `gui-monitor-hitl-e2e`（依赖 `gui-live-monitor` + `gui-run-control-hitl`）在窗口内一次都没启动，它既不在 `pending` 里、也不能算作「槽位等待」。所以下表的时长是**只看「已启动过的 key」的下界**，它对「E2 真槽位等待」有效，对「FM 依赖串行」无效。

**量化下界（不是上界）**：`|ic| ≥ 2 且 pending ≠ ∅` 的时长 = **FM 9.63h（窗口 13.7% / active 45.6%）**、**E2 19.60h（窗口 19.6% / active 41.7%）**。注意这里有**两种混杂**：(i) 真槽位等待（如上两例）；(ii) 还处在"等上一步 verify/gate 完成"的 key 也会被算成 pending。所以它**不能**直接读成"cap 白等了 19.6h"；可信的只有逐实例核对过的那 2 例（E2）。

### 指标 3：槽位被 stalled 的 key 占用的比例

| 项目 | 有 stalled key 的时间（并集） | 占窗口 | stalled key ∩ 它自己的 worker | 说明 |
|---|---|---|---|---|
| FM | **47.64h** | **67.6%** | **0.00h** | 6 个 key：gui-skeleton-shell 17.75h、cli-run-state-and-events 15.20h、gui-contract-surface 13.19h、gui-shell-spike 5.51h、cli-readonly-snapshot 1.35h、gui-contract-mock-tests 1.32h |
| E2 | **46.79h** | **46.8%** | **0.04h（2.5 min，1 段）** | 8 个 key：gui-time-mvp-board 31.94h、false-meets-remediation 19.89h、cigate-install-kit 15.52h、inline-marker-patchkit 13.99h、mvp-closeout 5.20h、params-service 2.31h、l3-verdict-source-fallback 2.20h、tier-a-closeout 0.37h |

**结论（这是本 RQ 最关键的一条）**：stalled key **不占槽**。`mark_stalled` 把 key-status 写 `stalled`（`conductor.py:3944-3965`），而派发循环在 `conductor.py:274` 直接 `continue` 跳过 stalled key；同时 `in_flight_keys` 只来自"有在飞 worker 行"的 key（`conductor.py:258-263`）。数据完全吻合：**stalled key 与它自己的 worker 的重叠时间 ≈ 0**（FM 0，E2 2.5 min）。因此 **spec §4 风险 1 的字面表述（"提高上限只是让更多 key 一起卡住"）在"槽位"口径上不成立**；stalled 的代价是**占着 key 队列/阶段推进权，而不是占着槽**（这些时间的槽位其实是空着或给了别的 key）。

**数据质量告警（必须随结论一起读）**：FM 的 stalled 统计被 **2026-09-24 的 gates-flood 事故**污染——`gui-contract-surface` 有 **5,588** 次 `stalled` 事件（合并后仅 2 段：09-23T11:10→15:24、09-23T15:37→09-24T03:07）、`gui-shell-spike` 有 **1,098** 次（每次 ~18s）。即"同一 key 每 tick stalled→running→stalled"的抖动（`conductor.py:2320-2330` 的注释正是这场 FeatureMigrator 事故）。上表的**区间合并后**的时长是可信的，但**事件计数不可当作"独立停滞次数"**。E2 的 13 次 stalled 事件没有这个问题，逐条可读。

### 指标 4：吞吐与并发

**(a) 每 key 的 EXECUTE→DONE 墙钟（口径：最早 `ap-<key>-0NN-*` worker START → `advance verify->done exit=0`）**

| 项目 | 样本 n | 中位数 | 最大 | 最小 | 明细（key: 时长） |
|---|---|---|---|---|---|
| FM | 7 | **16.77h** | 22.50h | 3.75h | gui-shell-spike 16.77 / gui-contract-surface 16.93 / cli-readonly-snapshot 3.92 / gui-contract-mock-tests 3.75 / gui-skeleton-shell 22.50 / cli-hitl-channel 3.91 / cli-run-state-and-events 18.51 |
| E2 | 11 | **7.54h** | 39.21h | 0.88h | params-service 7.54 / tier-a-closeout 7.09 / l3-readcap-injection 0.90 / mvp-closeout 7.95 / l3-verdict-freshness 0.88 / sampling-human-channel 3.36 / inline-marker-patchkit 18.81 / cigate-install-kit 21.90 / l3-verdict-source-fallback 2.97 / gui-time-mvp-board 39.21 / false-meets-remediation 21.92 |

**重要限定**：这个时长**包含等人工门禁的时间**（例：`feature-gui-time-mvp-board` 的 39.21h 里有 31.94h 是 stalled 等人批 gate）。所以它**不是纯工时吞吐**，不能直接用来论证"槽位多就能更快"；能说的只是"key 端到端的墙钟分布"，且 n=7/11 太小。

**(b) 并发度 vs worker 墙钟（`[END] elapsed`，按 [START] 时刻的 worker 并发分桶）**

| 项目 | conc@start=1 | =2 | ≥3 |
|---|---|---|---|
| FM | n=77 中位 656s / 均值 799s | n=121 中位 672s / 均值 908s | n=32 中位 507s / 均值 536s |
| E2 | n=155 中位 520s / 均值 629s | n=323 中位 532s / 均值 665s | n=6 中位 293s / 均值 450s |

**读法**：中位数在 conc=1 与 conc=2 之间几乎没有差别（FM +16s / E2 +12s，+2%），conc≥3 反而更短（样本 32/6，且短任务本来就容易与别的任务重叠，属选择偏差）。**没有观察到"高并发更慢"**。

### 指标 5：失败与并发的相关性

| 项目 | worker 总数 | 失败（`exit≠0`） | 总失败率 | conc=1 | conc=2 | conc≥3 | 失败构成 |
|---|---|---|---|---|---|---|---|
| FM | 232 | 9 | 3.9% | 3/77 = 3.90% | 5/121 = 4.13% | 1/32 = 3.13% | 全部 `[TIMEOUT]`（idle 5 / wall 4；elapsed 660–3600s） |
| E2 | 485 | 18 | 3.7% | 3/155 = 1.94% | 15/323 = 4.64% | 0/6 = 0% | 全部 `[TIMEOUT]`（idle 14 / wall 4；elapsed 660–3600s） |

- **E2 是唯一看起来"相关"的**：conc=2 的失败率是 conc=1 的 2.4 倍。但 Fisher 精确检验（单边）**p = 0.11**（15/323 vs 3/155），n=18 太小，**不显著**；FM 的方向则完全反了（4.13% vs 3.90%，p≈0.83）。**不给相关性结论。**
- **所有 27 次失败都是看门狗超时**（活动看门狗 600s 无 token/工具增量，或墙钟 3600s 兜底），即 **GC-4 的时间判据**，不是资源/Load 类错误。E2 里 14 次 idle 超时的 `[TIMEOUT]` 原文都是 `idle: no activity for 60X s`，说明是"模型/工具静默"，与并发无关的证据方向更自然。
- **rate limit / 429：零证据。** 对 FM 752 / E2 1,494 个 worker 产物文件（`worker.log`/`output.md`/`progress.md`/`report.md`/`task.md`/`trace.log`）做严格正则扫描（`rate[ _-]?limit` / `too many requests` / `HTTP 429` / `status 429` / `\b429\b` 非毫秒）得到 **FM 0 行**、**E2 0 行**（E2 的 6 处命中全是 `7,429,564 B`、`18,429 B` 之类数字/哈希）。⇒ spec §4 风险 3（"rate limit 才是真瓶颈"）**在现有数据里没有证据**。

## 数据缺口（必须与上面每个数字一起读）

1. **MW 完全没有 autopilot 数据（最主要缺口）**：`H:\git\Multi-Workers\.agenticdoc\` 下没有 `_autopilot/`；169 个 worker 目录里 **0 个 `ap-*`**；`_workers.parallel` 176 行里没有 `ap-*`。MW 的并行是 PM 手工派发（任务名如 `mw-dr-*`、`mw-*`），**从不受 `max_parallel_keys` 约束**，因此它在"槽位是否不足"这个问题上**零信息量**。任务指定"三项目" ⇒ 实际可用 2 个项目。
2. **JCodingAss（额外第 4 个项目）** 的 `_autopilot/timeline.jsonl` 只有 2.9h、2,349 行、其中 2,289 行是 `beat`，worker 全在窗口外 ⇒ 不可用，未纳入统计。
3. **`_workers.parallel` 不是完整历史**：FM 只剩 231 行（最早 09-17），而 timeline 里 09-23 之后的 dispatch 就有 126 次；E2 485 行。所以本文**没有**用 `_workers.parallel` 作为区间来源，改用 worker 目录里的 `trace.log`（FM 232 / E2 485 个，覆盖各自窗口内全部 worker）。这也意味着**没有第二套独立数据源交叉验证** trace 区间，唯一交叉点是指标 4 的 `advance verify->done` 与 `_index.parallel` 相位数（口径自洽但非独立）。
4. **快照是活的**：分析期间 FM 从 230 → 232 个 trace（E2 484 → 485）。快照时刻 **2026-09-26T07:36Z**；当时 **FM 1 个、E2 1 个** worker 无 `[END]`（`ap-gui-run-control-hitl-007-...`、`ap-feature-gui-contract-respec-001-...`），已按"最后一个 trace 行 ts"做右截断（censored），不参与 `[END]` 统计但参与在飞区间（可能**低估**最后几分钟的并发）。
5. **`_index.parallel` 的时间列混用本地时与 UTC**（FM 里有 `2026-09-24 15:40`（= 07:40Z 本地时）也有 `2026-09-24T11:07:00.123Z`）。本文因此**没有**用 `_index.parallel` 的 Updated 做时长，只用 phase 做口径核对。
6. **timeline 有 2 代轮转**（`ROTATE_GENERATIONS = 2`，10MB/代）。本次两项目的 `.1` 都从 `seq=1` 开始（FM 60,035 行 / E2 80,243 行），**没有丢代**；但再往前（FM 09-23T09:06 之前、E2 09-22T03:35 之前）已经不存在，**不能外推**。
7. **FM 的 stalled 事件数被 09-24 gates-flood 污染**（见指标 3 的告警）。
8. **`_scratch` 不是 stage key**：FM 的 pending 采样里只有它，是 roadmap-writer 的临时 key，不能算"key 排队"。
9. **未做的测量**：没有把 key 等待精确拆成「等槽 vs 等门禁/等上游」，因为 roadmap 的 `key-status` 只有当前值、没有历史（历史只在 `stalled`/`resume`/`gate-*` 事件里，覆盖不全）。所以指标 2 的量化下界（FM 9.63h / E2 19.60h）含混杂，只有逐实例核对过的 E2 两例是干净的。另外 `pending` 口径**看不见从未启动过的 key**（见指标 2 的口径盲区），这意味着「待派发深度」只会被低估：两项目当前 stage 的 key 总数本来就远大于 2（FM Stage 2 = 5、Stage 3 = 4；E2 Stage 3 = 9），其中相当一部分是**依赖未满足**而非槽位不足。

## 结论 → 决策映射

### 对 U-2（"并行度不够的具体现象是什么"）的直接回答

**现象是"单项目内第 3 个及以后的 key 排队"，而不是"worker 变慢/失败变多"，也不是"机器扛不住"：**

1. **有（间接）证据表明 E2 的槽位不足。** 两个可复算实例：`feature-sampling-human-channel` 在 09-24T08:02:20→12:49:37 完全就绪（前一 worker 已退出、非终态、零 gate/stall/skip 事件）却等了 **4.79h**，同期另两个 key 占满两槽 **98%**（`timeline.jsonl.1:62484` / `58226`）；`feature-completeness-four-dim` 在 `advance spec->design exit=0`（`timeline.jsonl.1:38204`）之后等了 **5.64h** 才拿到 design-writer（`timeline.jsonl.1:43123`）。E2 还有 194 个采样点处于"槽满 + 有 key 空闲待派发"，最大排队深度 4。
2. **FM 没有同类实例。** FM 打满 66.7% 的 active 时间，但期间唯一"空闲待派发"的 key 是 `_scratch`（roadmap-writer）；FM 的 key 消耗主要卡在 **stalled（等人工 gate）与上游依赖**（`_autopilot/_roadmap.md` Stage 2 有 5 个 key 且是链式依赖：`cli-run-state-and-events←cli-readonly-snapshot`、`cli-hitl-channel←gui-contract-surface`、`gui-live-monitor←{gui-contract-surface,gui-skeleton-shell,cli-run-state-and-events}`、`gui-run-control-hitl←{gui-skeleton-shell,cli-run-state-and-events,cli-hitl-channel}`、`gui-monitor-hitl-e2e←{gui-live-monitor,gui-run-control-hitl}`；Stage 3 的 4 个 key 同样互相依赖）⇒ **FM 的吞吐瓶颈在门禁/依赖，不在槽位**。这一点必须写进 spec，否则"三分之二的 active 时间打满"会被误读成"FM 也缺槽"。
3. **打满率本身高但不等价于缺槽**：active 内 62.9%（E2）/66.7%（FM）；然而"打满且有待派发 key"只占 active 的 41.7%（E2）/45.6%（FM），且其中大部分混杂了"等门禁"的 key。
4. **不是 worker 层问题**：并发 2 时 worker 中位墙钟与并发 1 无实质差别（+2%），失败率无显著差异（p=0.11，n=18），且全部失败是看门狗（时间判据），零 rate-limit。⇒ 现状**没有**"提高上限会先坏在 rate limit / 变慢 / 更易失败"的实测征兆（但也没有任何"提高上限"的实测，本次全部数据都来自 cap=2 的既有运行）。
5. **机器层不是瓶颈**：两项目重叠 70.49h 内，机器层 4 槽打满只有 4.30h（active 的 10.8%），两项目同时有 key 在飞只有 19.0% 的时间。
6. **风险 1（stalled 占槽）被数据否掉**：stalled key 与自身 worker 的重叠 ≈ 0（FM 0h / E2 2.5min）。stalled 的真实代价是**冻结 key 队列**，不是**占用槽位**；因此"先修 stalled 释放机制，再谈提高上限"与"提高上限没有收益"这两条推论都**不成立**（前者不必要，后者需要对 E2 那 2 个实例负责）。

### 对 AC-003 的支撑

- 给出**样本量与时间窗**：FM 70.47h（09-23T09:06Z 起，232 worker / 38 key）、E2 100.00h（09-22T03:35Z 起，485 worker / 26 key）；MW 无数据（已在缺口 1 明确声明）。
- 给出**槽位利用率**：均值 1.669（FM）/1.634（E2）个 key 在飞（cap=2），打满率 62.9%–66.7%（占 active）、20.0%–29.6%（占窗口），并列出了 key 数直方图与"固定配对占据两槽"的形态。
- 给出**槽位等待**：**直接证据 = 无**（并给出"为什么无"的三个取证面 + `conductor.py:289` 的代码行）；**间接证据 = E2 有 2 个逐条可复算的实例 + 194 个采样点，FM 无 stage-key 实例**，并明确标注量化下界的混杂性。
- 所有数字都可由 `trace.log` 的 `[START]/[END]` + timeline 的 `stalled/resume/dispatch/advance` 复算，脚本片段与命令已在 §调研方法 给出。

### 边界声明

本笔记**不**给出任何改动方案（提 key 层还是 worker 层、新默认值、生效层、首个失败模式、可逆性均属 RQ-4/spec 的职责）。本笔记也**没有**修改任何被观测项目的文件（仅只读打开；分析脚本写在 `%TEMP%`）。