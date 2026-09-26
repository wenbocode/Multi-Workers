# Research: 面板口径 vs conductor 口径的实测分歧（RQ-7 / msc-rq7-panel-divergence）

> 只读角色。本文件是本卡**唯一写面**：未修改任何代码、未写 `_workers.parallel`、未 commit、未写其它任何文件（探测脚本只落在 `%TEMP%`，不属于项目）。
> 行号对应 2026-09-26 工作树快照：`conductor.py` 174500 B、`launcher.py` 47583 B、`mw_common.py` 144421 B、`monitor.ts`、`status-model.ts`、`timeline.py`。
> **不重复 RQ-1 的结论**（`evidence/research/spec-concurrency-anchors-20260926.md` 已给出三层上限清单与"两个口径不等价"的代码面）。本卡只做**实测与对齐面**：把两个口径的公式逐字摘出、在"现在这一刻"各算一遍、找历史可见性、量化 cap 阻塞的可见性缺口、给出设计期输入。
> 交叉核对对象：`evidence/research/spec-slot-framing-20260926.md`（PM 自采）、`spec-concurrency-anchors-20260926.md`（RQ-1）。与两者**无冲突**；新增的是实测数字与对齐建议。

## TL;DR

**【事实】**

1. 两个口径互不等价，且**在第三个维度上也不等价**：面板 `slotsUsed` 的 owner 判定**只看 `ap-<key>-` 前缀，不看 `task_path`**（`monitor.ts:511`）；conductor 的归属判定**前缀 OR `task_path`**（`conductor.py:2135-2138`）。于是同一条 PM 手工派发行（`task_path` 落在某 key 的 `workers/` 下、但名字不是 `ap-`）在 conductor 侧**算 1 个 key**、在面板侧**算 1 个独立槽**。这是 RQ-1 未点出的那一半差异。
2. 面板还**结构性丢掉了 `taskPath`**：`readMonitorState` 只把 `{taskKey, elapsedMs}` 传给 `deriveAutopilotPanel`（`monitor.ts:251`、`:466`），所以面板**物理上无法**复刻 conductor 的 `task_path` 归属规则。
3. 实测（本地 15:40 / UTC 07:40 快照）：
   - **MW**（无 `.agenticdoc/_autopilot/config.json`，autopilot 未启用）：4 条 `running` 行全属同一 key `mw-autopilot-slot-capacity`；面板口径算出 `slotsUsed=4`、`slotsMax=2`（走默认值）⇒ **4/2**；conductor 口径算出 `in_flight_keys=0`（该 key 不在 roadmap 里，候选域 `deps_of` 为空）⇒ 两个口径差 4。注意 MW 面板**不渲染** slots 行（`monitor.ts:586` 仅在 `autopilot.enabled` 时渲染，MW 无 config ⇒ 渲染 `autopilot: not enabled`），所以这个 4/2 是**潜在**分歧而非显示分歧。
   - **FM**（autopilot enabled，`max_parallel_keys=2`）：2 条 `ap-` running 行 ⇒ 面板 **2/2**，conductor **2/2**，**此刻一致**。
   - **E2**（autopilot enabled，`max_parallel_keys=2`）：1 条 `ap-` running 行 ⇒ 面板 **1/2**，conductor **1/2**，**此刻一致**。
   - 三个项目此刻 `pending` 行均为 **0**；但"已派发未 spawn"的窗口真实存在：同一批 running 行的 `dispatched_at → updated_at`（= pending→running 的驻留）实测 **0.12 s / 0.18 s / 0.34 s / 2.0 s / 4.0 s / 5.18 s**。窗口内 conductor 已占额、面板算 0。
4. **历史可见性（可复算）：面板的 `slotsUsed` 在真实运行中确实出现过 > `slotsMax`。**
   - FM 2026-09-19T08:02:20Z：**8/2**（8 条 PM 手工 audit 行，非 `ap-`；当时 FM 尚无 roadmap）。
   - FM 2026-09-26T03:04:02Z–03:05:59Z：**3/2**（autopilot 已启用；2 条 `ap-` 行 + 1 条 `_scratch` 手工行 `xkey-n1-hitl-groups-repair`）。
   - E2 2026-09-25T03:40:07Z–03:42:54Z：**3/2 → 4/2**（全部为 `ap-` 行、4 个不同 key；机制**未能从留存物解释**，见 §"数据缺口"）。
   - MW 2026-08-28T13:00:51Z 峰值 **7/2**；OC 峰值 **6/2**；UEM 峰值 **9/2**（后两者均为手工 fan-out）。
   - 重建方法：`_workers.parallel` 保留了全部历史行（终态不裁剪），用 `[dispatched_at, updated_at)` 近似每个 worker 的生命期做扫描。**这是推断而非原样观测**（误差上界 ≈ launcher poll 5 s，`launcher.py:49`）。
5. **同一 key 同时 ≥2 条 running 行**：当前快照即有一例（MW 本 key 4 条并发）；历史真实并发 MW `mw-autopilot-verify-cli` **6 条**（2026-09-26T06:19:28Z）、`mw-rag-integration` 5 条、`xkey-repair-mechanism` 4 条。**但 FM/E2 的 `ap-` 行从未观测到真实同 key 并发**（conductor 的 per-key serial 成立；早先扫出的"重叠"经半开区间复核全是 `end==start` 的接缝假象）。
6. **cap 阻塞零痕迹确认**（与 RQ-1 一致并补强）：`conductor.py:289-290` 是纯 `continue`；`timeline.py:67-85` 的 17 个事件类型**没有** cap/slot 类；`mw_common.py` 全文 `slot` **零命中**；`mw doctor` 的 autopilot 节（`mw_common.py:2022-2061`）**没有任何** slot/`max_parallel_keys` 字段。FM 两代 timeline（91786 行）与 E2 两代（96995 行）的实测事件直方图只出现 `EVENT_TYPES` 里的类型，**没有任何** cap/slot 事件（复算命令见下）。

**【推断】**：FM 此刻 `2/2` 且 `gate_hit=True`，但**并没有任何 key 被 cap 挡住**（Stage 2 里只有这 2 个 key 的 deps 满足，第 3 个 `gui-monitor-hitl-e2e` 仍被 deps 阻塞）。⇒ "cap 打满"不等于"cap 造成了等待"；只看数字会误判。

## 决策问题

对齐 spec **AC-008**（并行度可观测性：能区分并显示「槽位（key 层）」与「实际同时运行的 worker 数」，能指出哪些 key 占着槽、其中哪些 stalled，且不新增误报）。具体回答五问：

- Q1 两个口径的**逐字公式**分别是什么（含 `busyKeys` 构造、`ap-` 前缀判定、`owner ?? w.taskKey` 的用途、`slotsMax` 回退、conductor 的 `in_flight_keys` 构造与归属判定）。
- Q2 **现在这一刻**两侧各算一遍是多少，哪几行被哪个口径计入；并说明"只在 running 计数"的后果（pending 窗口）。
- Q3 历史上**面板 `slotsUsed` 是否真的 > `slotsMax`**，同一 key 是否出现过 ≥2 条 running 行——要可复算证据，没有就明说"未观测到"。
- Q4 cap 阻塞是否**零痕迹**；若是，有哪些**替代信号**可用；若要新增一条 cap 事件，**最小改动面**是什么（只给方案，不改代码）。
- Q5 "操作者到底想知道什么"与两个口径各能回答什么，据此给出**面板应显示几个数**的最小建议。

**不做**：不判定"上限 2 该不该改"（RQ-4）、不做吞吐量化（RQ-3）、不改任何代码、不写 `_workers.parallel`。

## 调研方法与出处

### 只读命令（逐条）

1. 读代码（全文或标注行段）：`monitor.ts`（1-160、240-260、426-620、630-660）、`worker-store.ts`（1-80）、`status-model.ts:79/106/136/255/271/296`、`conductor.py:183-295`、`:2120-2160`、`:2870-2935`、`mw_common.py:154-170`、`:1430-1530`、`:1640-1660`、`:2010-2070`、`launcher.py:775-1010`、`dispatch.py:396-560`、`timeline.py:60-100`、`test_autopilot_timeline.py:38-60`。
2. `grep -n 'slotsUsed|busyKeys|slotsMax|allKeys|inFlight'` over `packages/coding-agent/src` + `packages/multi-workers`（确认三处口径与无第四处）。
3. `grep -n 'if len(in_flight_keys) >= '` over `autopilot/conductor.py`（确认唯一 gate）。
4. `grep EVENT_TYPES` over `packages/multi-workers`（确认事件词表与锁定测试）。
5. `grep 'slot'`（大小写不敏感）over `mw_common.py`（零命中）与 `autopilot/*.py`（仅 `max_parallel_keys` 与 xkey 的同名局部变量）。
6. 现场只读数据：`H:\git\Multi-Workers\.agenticdoc\{_workers.parallel,_index.parallel}`、`E:\CLI_workspace\FeatureMigrator\.agenticdoc\{_workers.parallel,_index.parallel,_autopilot\config.json,_autopilot\_roadmap.md,_autopilot\timeline.jsonl}`、`H:\git\E2Feature\.agenticdoc\{同上}`。另扫 `H:\git\JCodingAss`、`E:\CLI_workspace\OverCode`、`E:\UEMigrator` 作为对照。
7. 事件直方图：`python -c` 逐行读 `timeline.jsonl` 与 `timeline.jsonl.1` 统计 `ev`（FM 两代 91786 行 / E2 两代 96995 行；E2 `.1` 时间跨度 `2026-09-22T03:35:07Z .. 2026-09-25T10:36:31Z`，FM `.1` `2026-09-23T09:06:44Z .. 2026-09-24T16:19:27Z`）。

### 数据快照（本卡实测所依据的"这一刻"）

| 项目 | `_workers.parallel` mtime（本地） | 行数 | running | pending | `max_parallel_keys` | 面板 slotsUsed | conductor in_flight_keys |
|---|---|---|---|---|---|---|---|
| MW | 2026-09-26 15:39:31 | 180 | 4 | 0 | 2（**默认值**，无 config.json） | **4** | **0** |
| FM | 2026-09-26 15:36:05 | 232 | 2 | 0 | 2（config.json） | **2** | **2** |
| E2 | 2026-09-26 15:38:55 | 486 | 1 | 0 | 2（config.json） | **1** | **1** |

> 快照漂移声明：本次调查期间 MW 该 key 的 running 行在数分钟内从 6 → 5 → 4 条变化（`msc-rq1/rq2/rq3/rq4` 相继终止，`msc-rq8-unattended-gates` 新派发）。表中为 **本地 2026-09-26 15:40:04** 的钉住值；数值随文件变化，复算时以文件为准。

### 复算命令（自包含，只读）

```python
# python rq7.py <project_root>
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); ad = root / ".agenticdoc"
rows = []
for line in (ad / "_workers.parallel").read_text(encoding="utf-8").splitlines():
    p = [x.strip() for x in line.strip().split("|")]
    if len(p) in (7, 8): rows.append(p)
def _keys(path):                      # _index.parallel 与 roadmap 的 key 提取
    out = set()
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "role" in s: continue
        p = [x.strip() for x in s.strip("|").split("|")]
        if len(p) >= 3 and p[0] not in ("Key", "") and set(p[0]) != {"-"}: out.add(p[0])
    return out
idx, rm = _keys(ad / "_index.parallel"), _keys(ad / "_autopilot" / "_roadmap.md")
allk = sorted(idx | rm)
cfg = ad / "_autopilot" / "config.json"
slots_max = (json.loads(cfg.read_text(encoding="utf-8")).get("max_parallel_keys") or 2) if cfg.exists() else 2
run = [r for r in rows if r[1] == "running"]
owners = {next((k for k in allk if r[0].startswith("ap-%s-" % k)), r[0]) for r in run}
TERM = ("done", "failed", "needs-clarification")
belongs = lambda r, k: r[0].startswith("ap-%s-" % k) or (".agenticdoc/%s/workers/" % k) in r[4].replace("\\", "/")
in_flight = {k for k in rm if any(r[1] not in TERM and belongs(r, k) for r in rows)}
print("PANEL slotsUsed=%d/%d %s" % (len(owners), slots_max, sorted(owners)))
print("CONDUCTOR in_flight_keys=%d %s cap_hit=%s" % (len(in_flight), sorted(in_flight), len(in_flight) >= max(1, slots_max)))
```

实测输出（与 §数据快照 一致）：

```
PANEL slotsUsed=4/2 ['msc-rq5-worker-serialization','msc-rq6-stalled-slot-release','msc-rq7-panel-divergence','msc-rq8-unattended-gates']
CONDUCTOR in_flight_keys=0 [] cap_hit=False
PANEL slotsUsed=2/2 ['gui-live-monitor','gui-run-control-hitl']
CONDUCTOR in_flight_keys=2 ['gui-live-monitor','gui-run-control-hitl'] cap_hit=True
PANEL slotsUsed=1/2 ['feature-gui-contract-respec']
CONDUCTOR in_flight_keys=1 ['feature-gui-contract-respec'] cap_hit=False
```

历史重建（`[dispatched_at, updated_at)` 扫描 + 半开区间）复算片段：

```python
# python sweep.py <project_root>  —— 需要带偏移的 ISO 解析；本机全部为 +00:00
from datetime import datetime
import pathlib, sys
parse = lambda s: datetime.strptime(s.strip(), "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
rows = []
for line in (pathlib.Path(sys.argv[1]) / ".agenticdoc" / "_workers.parallel").read_text(encoding="utf-8").splitlines():
    p = [x.strip() for x in line.strip().split("|")]
    if len(p) not in (7, 8) or p[1] == "pending": continue
    try: rows.append((p[0], parse(p[5]), parse(p[6])))
    except ValueError: pass
pts = sorted({r[1] for r in rows} | {r[2] for r in rows})
mx = 0
for i in range(len(pts) - 1):
    t = pts[i] + (pts[i + 1] - pts[i]) / 2
    mx = max(mx, len({r[0] for r in rows if r[1] <= t < r[2]}))
print("peak distinct owners =", mx)
```
（`%Y-%m-%dT%H:%M:%S%z` 覆盖本机全部行；少数行带毫秒 `.SSSZ`，需回退格式 —— 见复算注记。）
---

## 发现

### F1 两个口径的逐字公式

#### F1.1 面板 `slotsUsed` / `slotsMax`（TypeScript）

**(a) 输入行集合：只取 `running`，且丢掉 `taskPath`【事实】** —— `monitor.ts:246-252`

```ts
	const workers: MonitorWorker[] = [];
	for (const entry of new WorkerStore(path.join(projectDir, ".agenticdoc")).readAll()) {
		if (entry.status !== "running") continue;
		const dispatched = Date.parse(entry.dispatchedAt);
		if (Number.isNaN(dispatched)) continue;
		workers.push({ taskKey: entry.taskKey, elapsedMs: Math.max(0, nowMs - dispatched) });
	}
```

- `WorkerStore.readAll()` 读 `<project>/.agenticdoc/_workers.parallel`（`worker-store.ts:57`、`:61-65`），列序 `task_key|status|cli|provider|task_path|dispatched_at|updated_at|model`（`worker-store.ts:22-37`，容忍 7 列 legacy）。
- 三处丢信息：① `status !== "running"` **丢掉 pending**；② `dispatchedAt` 解析失败的行**整行丢掉**；③ `MonitorWorker` 只带 `{taskKey, elapsedMs}`（`monitor.ts:92-95`），**`taskPath` 没有传下去**。

**(b) 候选 key 域：roadmap key-status ∪ `_index.parallel` key 列【事实】** —— `monitor.ts:472-497`

```ts
	const statusByKey = new Map<string, string>();      // :472  roadmap 的 key-status
	...
			for (const [key, status] of Object.entries(stage.keyStatus)) statusByKey.set(key, status);  // :476
	...
	const phaseByKey = (deps?.readIndexPhases ?? defaultIndexPhases)(projectDir);   // :480  _index.parallel 的 Key 列
	...
	const allKeys = [...new Set([...statusByKey.keys(), ...phaseByKey.keys()])].sort();   // :497
```

**(c) `busyKeys` 构造与 `owner ?? w.taskKey` 的用途【事实】** —— `monitor.ts:509-513`

```ts
	const busyKeys = new Set<string>();
	for (const w of workers) {
		const owner = allKeys.find((key) => w.taskKey.startsWith(`ap-${key}-`));
		busyKeys.add(owner ?? w.taskKey);
	}
```

- `owner` 只认 `ap-<key>-` 前缀（与 conductor 的第一条同）；**找不到 owner 时不是跳过、也不是按 `task_path` 回溯，而是把该行的 `taskKey` 本身当成一个"key"计入** ⇒ PM 手工行（如 `msc-rq7-panel-divergence`、`xkey-n1-hitl-groups-repair`）各自**独占一个槽**。
- 该回退值的用途仅此一处：让 `busyKeys.size` 至少反映"有一批叫这个名字的 worker 在跑"，而不是静默忽略它们。

**(d) 两个数字与回退【事实】** —— `monitor.ts:521-522`

```ts
		slotsUsed: busyKeys.size,
		slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys,
```

- `config` 来源：`const config = configResult.ok ? configResult.config : null;`（`monitor.ts:470`）。⇒ **config.json 缺失或不可解析时不是报错，而是回退默认值 2**（`DEFAULT_CONFIG.max_parallel_keys = 2`，`status-model.ts:106`）。这正是 AC-008"无 running worker 的项目显示 0 而非报错"已满足的一半。
- 渲染：`monitor.ts:586` `if (s.autopilot.enabled)` 内才渲染 `slots ${used}/${max}`（`:596`）；否则走 `:632-635` 的 `autopilot: not enabled` / `disabled` 分支。⇒ **`slotsUsed` 总是被计算，但不总是被显示**（MW 即如此）。
- 姊妹字段（同源、同样是 `ap-` 前缀口径）：`monitor.ts:503` `inFlight: workers.filter((w) => w.taskKey.startsWith(\`ap-${key}-\`)).length`。⇒ 面板其实**已经有两套 key 归因**（`keys[].inFlight` 与 `busyKeys`），且都与 conductor 的 `task_path` 口径不同。

#### F1.2 conductor `in_flight_keys` + cap gate（Python）【事实】

**(a) 输入行集合与候选域** —— `conductor.py:200`、`:224-233`

```python
    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))     # :200
...
    deps_of: dict[str, tuple[str, ...]] = {}                                      # :224
    for stage in rm.stages:
        for entry in stage.keys:
            deps_of[entry.key] = entry.depends_on                                 # :229
```

- 候选域**只有 roadmap 的 `### Keys` 表里声明过的 key**；`_index.parallel` 里有、但 roadmap 里没有的 key **永不计入**。`_index.parallel` 的 phase/status/claim **完全不参与**这条判定。
- 行字段来自 `mw_common.parse_workers_file`（`mw_common.py:1456-1465`）：`task_key/status/cli/provider/task_path/dispatched_at/updated_at/model`。

**(b) `in_flight_keys` 公式** —— `conductor.py:258-264`

```python
    in_flight_keys = {
        key
        for key in deps_of
        if any(
            _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
        )
    }
```

**(c) "在飞"与"归属"的逐字定义** —— `conductor.py:2131-2138`

```python
def _is_in_flight(row: dict) -> bool:
    return row.get("status", "") not in mw_common._TERMINAL_STATUSES  # noqa: SLF001 — same-package private (state.py precedent)


def _row_belongs_to(row: dict, key: str) -> bool:
    if str(row.get("task_key", "")).startswith(f"ap-{key}-"):
        return True
    task_path = str(row.get("task_path", "")).replace("\\", "/")
    return f".agenticdoc/{key}/workers/" in task_path
```

- `mw_common._TERMINAL_STATUSES = {"done", "failed", "needs-clarification"}`（`mw_common.py:158`）⇒ **`pending` 与非三态脏值都算在飞**。
- 归属第二条把 `task_path` 归一化为正斜杠后做**子串包含**，不校验路径真实性。

**(d) cap gate** —— `conductor.py:287-292`

```python
            if key in in_flight_keys:
                continue  # wait for the in-flight worker
            if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):
                continue  # parallel cap — key starts on a later tick
            if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):
                in_flight_keys.add(key)
```

- 全仓唯一 gate（`_advance_key` 只在 `:291` 被调用；`dispatch.dispatch` 的其它调用点都在 `_advance_key` 内部）。`max(1, ...)` 是防御下限（`config.py:70` 已把值域压到 `(2, None)`）。

**(e) 面板看不到的第三处差异：pending 由谁写、何时变 running【事实】**
- dispatcher 先写 `status: "pending"` + `dispatched_at = iso_now()`（`dispatch.py:537-543`）；
- launcher 下一 poll 才 `_update_status(..., "running")`（`launcher.py:975`；`DEFAULT_POLL_INTERVAL = 5` s，`launcher.py:49`；`update_status` 同时刷新 `updated_at`，`mw_common.py:1519-1523`）⇒ 对仍在 running 的行，`updated_at - dispatched_at` **就是 pending 驻留窗口**（launcher 不给 running 行心跳）。

#### F1.3 两条归属规则的分歧表

| 行的形状 | conductor（前缀 OR task_path） | 面板（前缀 ELSE 自身 taskKey） |
|---|---|---|
| `ap-<key>-<stem>`，路径在 `<key>/workers/` 下 | 计入 `<key>` | 计入 `<key>` |
| 名字非 `ap-`，路径在 `<key>/workers/` 下（PM 手工） | **计入 `<key>`** | **计入该行自己的 taskKey**（多算槽） |
| 名字非 `ap-`，路径在 `_scratch/workers/` 下 | 不计入（不在 `deps_of` 且无匹配路径） | **计入自身 taskKey**（多算槽） |
| 名字嵌了别的 key 前缀的脏行 | 前缀命中即计入 | 前缀命中即计入 |
| `status="pending"` 的行 | **计入** | 不计入（被 `:248` 过滤） |
| key 在 roadmap 里缺失（如本 MW key） | **永不纳入候选域**，恒 0 | 若路径/前缀命中则正常计入 |

### F2 现在这一刻的实测（两侧各算一遍）

快照：本地 `2026-09-26 15:40:04`（内容 UTC 约 `07:40Z`）。

**F2.1 MW —— 同一 key 的 4 条手工 research 行（面板潜在 4/2，conductor 0）**

| `_workers.parallel` 行 | status | 面板归因（`owner ?? taskKey`） | conductor 判定 |
|---|---|---|---|
| `msc-rq5-worker-serialization` | running | `msc-rq5-worker-serialization`（新槽） | `_row_belongs_to` = **True**（task_path 命中本 key） |
| `msc-rq6-stalled-slot-release` | running | `msc-rq6-stalled-slot-release`（新槽） | 同上 True |
| `msc-rq7-panel-divergence` | running | `msc-rq7-panel-divergence`（新槽） | 同上 True |
| `msc-rq8-unattended-gates` | running | `msc-rq8-unattended-gates`（新槽） | 同上 True |
| `msc-rq1..rq4`（已 done） | done | 不计（`status!=="running"`） | 不计（终态） |

- 面板：`busyKeys = {msc-rq5…, msc-rq6…, msc-rq7…, msc-rq8…}` ⇒ `slotsUsed = 4`；无 `config.json` ⇒ `slotsMax = 2` ⇒ **4/2**（但 MW 未启用 autopilot ⇒ `monitor.ts:586` 不渲染该行）。
- conductor：`deps_of = ∅`（`.agenticdoc/_autopilot/_roadmap.md` 不存在，`roadmap.py:122-124` 的路径确认过）⇒ **`in_flight_keys = 0`，cap gate 恒不命中**。⇒ **同一个事实（4 个 worker 在跑、属同一个 key）在两侧被读成 4 和 0。**
- 若把候选域改成"所有 `_index.parallel` key"（假设性对照），conductor 口径会得到 `1`（`mw-autopilot-slot-capacity`）—— 与面板的 4 仍然不等。

**F2.2 FM —— 两侧此刻一致（2/2）**

| 行 | status | 面板 owner | conductor |
|---|---|---|---|
| `ap-gui-run-control-hitl-007-perf-zero-write-freeze-and-closeout-pack-a2` | running | `gui-run-control-hitl` | 计入（前缀 + 路径双命中） |
| `ap-gui-live-monitor-repair-a1-a2` | running | `gui-live-monitor` | 计入 |

- 面板 2/2；conductor `in_flight_keys = {gui-live-monitor, gui-run-control-hitl}`，`cap_hit = True`。
- **但 cap 并未造成任何等待**【推断】：Stage 2 的 5 个 key 中，`cli-run-state-and-events`/`cli-hitl-channel` 已 done，`gui-monitor-hitl-e2e` 的 deps（`gui-live-monitor`, `gui-run-control-hitl`）都还没 done ⇒ 此刻**只有 2 个 key 有资格被派发**。⇒ "2/2 + gate_hit" 与"cap 挡住了谁"是两件事。

**F2.3 E2 —— 两侧此刻一致（1/2）**

| 行 | status | 面板 owner | conductor |
|---|---|---|---|
| `ap-feature-gui-contract-respec-002-params-yaml-zero-dep` | running | `feature-gui-contract-respec` | 计入 |

**F2.4 pending 行的后果（"只在 running 计数"）**

| 项目 | 快照时刻 pending 行数 | 从本批 running 行测得的 pending 驻留（`updated_at − dispatched_at`） |
|---|---|---|
| MW | 0 | 0.34 / 0.34 / 0.18 / 5.18 s |
| FM | 0 | 2.0 / 4.0 s |
| E2 | 0 | 1.0 s |

- 【事实】快照时刻**没有** pending 行 ⇒ 此刻两个口径的差异**不**来自 pending，而完全来自 F1.3 的归属规则。
- 【事实】但 pending 窗口真实存在（0.12–5.18 s，上界与 launcher poll 5 s 吻合）。窗口内：conductor 已经把该 key 计入 `in_flight_keys` 并据此 gate 其它 key；面板的 `workers` 数组里**根本没有这行**，`slotsUsed` 仍为 0（或偏小）。⇒ 面板会显示"还有余量"而 conductor 已在阻塞。
- 【推断】反方向也成立：若 launcher 未在跑（或 spawn 失败后行被置 failed 前），一条 pending 行可以让 conductor 的一个槽**无限期**被占，而面板永远不显示它 —— 这正是"面板说有余量、conductor 已阻塞"的最坏形态；本卡**未在留存数据中捕获到该形态**（见数据缺口）。

### F3 历史可见性：面板 `slotsUsed` 是否真的 > `slotsMax`

**【事实】是。** 用 `_workers.parallel` 的留存历史行（终态不裁剪：MW 180 行回溯到 2026-08-28、FM 232 行、E2 486 行）以 `[dispatched_at, updated_at)` 半开区间重建"某时刻在跑的 owner 集合"，峰值与超限窗口如下：

| 项目 | 峰值 `slotsUsed` | `slotsMax` | 峰值时刻（UTC） | 是否 > max | 该峰值的 owner 性质 |
|---|---|---|---|---|---|
| MW | **7** | 2 | 2026-08-28T13:00:51Z | **是** | 全为 PM 手工行（`mw-dr-*`） |
| FM | **8** | 2 | 2026-09-19T08:02:20Z | **是** | 全为 PM 手工 audit 行（非 `ap-`；当时 FM 尚无 roadmap） |
| FM | **3** | 2 | 2026-09-26T03:04:02Z–03:05:59Z | **是** | 2 条 `ap-` 行 + 1 条 `_scratch` 手工行 |
| E2 | **4** | 2 | 2026-09-25T03:40:07Z–03:42:54Z | **是** | **全部为 `ap-` 行、4 个不同 key** |
| E2 | 3 | 2 | 2026-09-26T06:55:23Z | **是** | 3 条 `ap-` 行、3 个 key |
| OC | **6** | 2 | 2026-09-20T07:03:21Z | **是** | PM 手工行 |
| UEM | **9** | 2 | 2026-09-14T07:57:29Z | **是** | PM 手工行 |
| JCA | 2 | 2 | 2026-09-11T03:26:39Z | 否 | —— |

超限样本计数（半开区间、中点采样）：MW 65/352、FM 48/453、E2 6/933、OC 64/349、UEM 14/52、JCA 0/141。

**同一 key 同时 ≥2 条 running 行**【事实】：

- **当前快照即有一例**：MW `mw-autopilot-slot-capacity` 4 条并发（F2.1）。
- 历史真实并发（严格重叠，非接缝）：MW `mw-autopilot-verify-cli` **6** 条 @2026-09-26T06:19:28Z（`design-rqd1..rqd6`）、`mw-rag-integration` **5** @2026-09-22T09:19:25Z、`xkey-repair-mechanism` **4** @2026-09-26T03:49:38Z、`goal-autopilot` 4、`mw-widget-terminal-lifecycle` 4、`mw-worker-progress-persist` 4；OC `collection-expansion` 6、`collection-expansion-b4` 6；UEM `diagram-dual-view` 3；E2 `feature-clustering` 3。
- **反之，FM/E2 的 `ap-` 行从未观测到真实同 key 并发**（严格重叠为 0）。早先用闭区间扫出的 `end == start` "重叠"（例如 FM `gui-live-monitor` 006 结束与 007 开始同为 04:28:03）在半开区间下全部消失 ⇒ conductor 的 per-key serial（`conductor.py:287-288`、`:1075`）在数据上成立。

**复算注记（重要）**：`updated_at` 对 running/done 行是状态转换时刻（`mw_common.py:1519-1523`），所以 `[dispatched_at, updated_at)` 是**生命期近似**，误差上界 ≈ launcher poll 5 s（`launcher.py:49`）；闭区间扫描会把"上一行结束==下一行开始"误判为重叠，必须用半开区间。上表中所有"分钟级"超限窗口（FM 09-19 约 14 min、FM 09-26 约 2 min、E2 09-25 约 2.5 min）**远超 5 s 误差**，不是重建假象。
### F3.1 trace.log 交叉核对（**直接观测**，强于 F3 的行生命期重建）

每个 worker 目录的 `trace.log` 由 worker 自己写 `[START] <iso>` / `[END] <iso> exit=N elapsed=Ns`（例：`E:\...\FeatureMigrator\.agenticdoc\_scratch\workers\xkey-n1-hitl-groups-repair\trace.log` 末行 `[END] 2026-09-26T03:05:59.327Z exit=0 elapsed=113s tools=26`）。覆盖率：FM 230/232、E2 485/486、MW 162/173（`*/workers/*/trace.log`）。以 `[START]..[END]` 为生命期、半开区间扫描，复现 F3：

| 项目 | trace 区间数 | 面板口径峰值（owner 去重后） | 峰值时刻（UTC） | 同 key 真实并发峰值 | 同 key 峰值所属 key |
|---|---|---|---|---|---|
| MW | 162 | **6** | 2026-09-26T06:22:04Z | **6** | `mw-autopilot-verify-cli`（`design-rqd1..rqd6`，PM 手工） |
| FM | 230 | **8** | 2026-09-19T08:04:14Z | **6** | `audit-remediation`（PM 手工） |
| E2 | 485 | **4** | 2026-09-25T03:41:28Z | **3** | `feature-clustering`（PM 手工） |

- 峰值与 F3 的行生命期重建一致（MW 6、FM 8、E2 4）；两法的峰值时刻相差 0–2 min（行生命期用行时间戳网格、trace 用进程起止网格），指的是同一批 worker。MW 行重建的 7/2 峰值（08-28）在 trace 中只到 6 —— 该批 `mw-dr-*` 有若干目录无 trace.log（覆盖率 162/173 的残差）。
- **E2 4/2 升级为直接观测**【事实】：`2026-09-25T03:41:28Z` 同时存在 4 个**不同 key**的 worker 进程（`feature-cigate-install-kit`、`feature-gui-time-mvp-board`、`feature-l3-verdict-source-fallback`、`feature-sampling-human-channel`），各自的 trace 区间互相重叠约 2 分钟（03:40:11 → 03:42:47/03:43:47）。该窗口 `max_parallel_keys=2`、`xkey_repair` 未启用、`ap-` 前缀按 `dispatch.py:12-14` 是 conductor 专属 ⇒ **key 层 cap 与"实际在飞的 key 数"在该窗口不相等**（机制见"数据缺口"）。
- **FM 3/2 也是直接观测**【事实】：`2026-09-26T03:05:02Z` 三个 owner = `gui-live-monitor`（`ap-` 行）+ `gui-run-control-hitl`（`ap-` 行）+ `xkey-n1-hitl-groups-repair`（`_scratch` 手工行）。⇒ 面板会显示 `slots 3/2`，而 conductor 的 `in_flight_keys` 只有 2（手工行不计入任何 key 的 `deps_of` 候选域，因为 `task_path` 在 `_scratch/` 下）。
- **同 key 真实并发只在 PM 手工通道出现**【事实】：上表三个"同 key 峰值"全部是手工 task（`design-rqd*`、`audit-remediation-*`、`t0xx-*`），**没有一例是 `ap-` 行**。

### F4 cap 阻塞的可见性缺口

**F4.1 零痕迹确认**【事实】（与 RQ-1 Q5(1) 一致，本卡补上实测直方图）

- `conductor.py:289-290` 只有 `continue`（无日志、无事件、无文件写）。
- `timeline.py:67-85` 的 `EVENT_TYPES` 共 17 个：`beat / dispatch / worker-terminal / advance / gate-created / gate-answered / stalled / skip / stage-close / config / goal-halt / goal-snapshot / type-rejected / target-config-rejected / reconcile / resume / l3-no-verdict`，**无 cap/slot 类**。
- 实测事件直方图（复算：逐行 `json.loads` 后 `Counter(ev)`）：
  - FM `timeline.jsonl`：`{beat:31627, dispatch:60, advance:32, config:14, gate-answered:5, gate-created:4, resume:3, stalled:2, stage-close:2, goal-snapshot:2}`；`timeline.jsonl.1`（60035 行，2026-09-23T09:06Z–2026-09-24T16:19Z）：`{beat:22159, dispatch:68, advance:5525, config:5521, gate-created:6692, gate-answered:6689, stalled:6689, resume:6688, goal-snapshot:4}`。
  - E2 `timeline.jsonl`：`{beat:16695, dispatch:15, config:10, gate-answered:5, resume:5, l3-no-verdict:6, advance:6, gate-created:4, stalled:4, goal-snapshot:2}`；`timeline.jsonl.1`（80243 行，2026-09-22T03:35Z–2026-09-25T10:36Z）：`{beat:66914, advance:6329, config:6529, dispatch:412, gate-created:14, gate-answered:13, stalled:9, resume:8, goal-snapshot:7, stage-close:4, l3-no-verdict:4}`。
  - ⇒ 两代全量合并后，FM 91786 行 / E2 96995 行的事件词表**恰好等于** `EVENT_TYPES`，**没有任何** cap/slot 事件。
- `grep -i 'slot'` over `mw_common.py` = **零命中**；`mw doctor` 的 autopilot 节（`_doctor_autopilot`，`mw_common.py:2022-2061`）字段集合为 `{path, exists, xkey_repair, xkey_verify_cmd, xkey_verify_timeout_s, xkey_verify_cwd, xkey_verify_argv, xkey_verify_missing, origins, diagnostics, error}`，**无 slot / 无 `max_parallel_keys` / 无 in-flight 数**。
- `skip` 事件（`conductor.py:280-282`）只覆盖 **live foreign claim** 这一种跳过，**不覆盖 cap 跳过**。

**F4.2 可用的替代信号（都不足以量化 cap 阻塞）**【事实/推断】

1. **`beat` + `dispatch` 序列对齐**：`orchestrate` 每 tick 首行 `st.timeline.append("beat")`（`conductor.py:2056`）；每次派发由 `dispatch.py:597` 追加 `dispatch`（detail = `ap-<key>-<stem> type=... loop=... attempt=N`）。**能**得到"每 tick 是否派发、派发给了谁"；**不能**得到"这一 tick 有哪些 key 有资格但没被派发"，因为资格取决于**当时的** key-status/deps/claim（见下）。
2. **`_index.parallel` 的 `Updated` 列**：只在 phase 变化时写（FM `gui-live-monitor` 当前 `Updated=2026-09-26 14:26`（本地），正是它 `execute->verify` 的 `advance` 时刻 `06:26:15Z`）。⇒ 一个"Updated 很旧"的 key 可能是 cap 阻塞、也可能是 deps 阻塞/claim 冲突/stalled/长 worker 在跑。**且列格式不统一**（同一个文件里既有 `2026-09-26T07:28:26.450Z` 也有本地 `2026-09-26 15:28`），机器 diff 需先做格式归一。
3. **`_workers.parallel` 行时间戳 + beat 网格**：可以把"cap 饱和"的时段算出来（F3/F3.1 的方法），但**不能**判定该时段是否存在"有资格但未派发"的 key —— `_workers.parallel` 的 `update_status` 是**覆盖写**（`mw_common.py:1524`），`_index.parallel`/roadmap key-status 也只保留最后状态，所以**历史 tick 的 eligibility 已被抹掉**。⇒ "因 cap 而未派发的 tick 次数"**当前不可直接测量**（与 RQ-1 结论一致，本卡确认重建也无解）。
4. **`mw doctor`**：零字段，无替代。

**F4.3 若新增一条 cap 事件：最小改动面（只给方案，不改代码）**

| 项 | 建议 |
|---|---|
| 函数 / 文件 | `packages/multi-workers/autopilot/conductor.py` → `orchestrate()`（`:183` 起），改点就是 cap 分支 `:289-290` |
| 写哪里 | `.agenticdoc/_autopilot/timeline.jsonl`，唯一写者 `st.timeline.append(...)`（`timeline.py:282-328`，append-only + 失败不抛出） |
| 事件名 | `cap-blocked`（语义："本 tick 有 ≥1 个 eligible key 因 cap 未派发"）；备选 `slot-blocked` |
| 字段 | `key=<被挡住的 key>`、`stage=<stage.number>`、`detail="in_flight=a,b cap=2"`（显式 key 优先，满足 key sentinel 规则 `timeline.py:296-305`） |
| 变体 A（diff 最小，1 行） | 在 `:289-290` 直接 `st.timeline.append("cap-blocked", key=key, stage=stage.number, detail=f"in_flight={','.join(sorted(in_flight_keys))} cap={cap}")` —— 代价：**每 tick × 每个被挡 key 一行**。以 FM 现状（tick 4 s、单 worker 10–60 min）估算 ≈ 450–900 行/被挡 key/小时（`beat` 已 1 行/tick，量级相当但会随被挡 key 数放大）。 |
| 变体 B（推荐，代价可控） | 在 key 循环里把被挡 key 收进局部列表，循环结束后 `if blocked: st.timeline.append("cap-blocked", stage=..., detail=...)`，**每 tick 至多 1 行**，detail 内列 key。conductor 无私有状态（D-102），所以跨 tick 去重只能读 timeline 尾部（可用 `_timeline_has_event` 同款手法，`conductor.py:1553`（定义）/`:2250`（用例）），或干脆不去重（beat 已经每 tick 一行，可接受）。 |
| 连带面 | ① `timeline.py:67` 的 `EVENT_TYPES` 加 `cap-blocked`（不加也能写——`timeline.py:66` 明确"unknown ev values append fine"，但那样不可发现、过滤/文档都漏）；② `test_autopilot_timeline.py:48` 硬锁 `len(EVENT_TYPES) == 17`（`:48`）、`:55` `len(events)==17`、`:56` `range(1,18)` —— 加词表必须同步改这三处；③ `README.md:225-236` 是事件词表与面板说明的落点（`:235` 就是上一批新增 `resume`/`l3-no-verdict` 的登记位置）；④ TS 侧无影响：面板只按 `BEAT_EV` 取 tick、按 `advance` 派生停滞（`monitor.ts:487`、`deriveAdvanceStalls`），新事件类型天然惰性。 |
| 无替代方案吗 | 有且只有 timeline 能忠实记录这件事。`_workers.parallel` 无法表达"被挡住"（被挡的 key 不写任何行）；`_index.parallel` 表达的是 key 自身状态而非调度决策。 |

### F5 对齐建议的事实基础

**F5.1 操作者的问题 vs 两个口径能回答什么**

| 操作者真正想问的 | 正确口径 | 现状面板能回答吗 |
|---|---|---|
| "还有余量吗 / 能不能再起一个 key？" | **conductor 口径**：`cap − len(in_flight_keys)`（pending+running、roadmap 候选域、`ap-` 前缀 OR `task_path`） | **不能**。面板的 `slots used/max` 是第三种口径：对手工行会多算（MW 4 vs 真实 1 个 key）、对 pending 会少算（最多 5.18 s 窗口）、roadmap 缺 key 时会与 conductor 完全无关（MW 0 候选域）。 |
| "这台机器现在真在跑几个 worker？" | **worker 行计数**：`count(status=="running")` | **能**，且已经显示：`workers: N running (all keys)` + 每行 `taskKey  时间`（`monitor.ts:636-641`）。 |
| "哪些 key 占着槽？其中哪些 stalled？" | conductor `in_flight_keys` ∩ roadmap key-status | **近似能**：attention 行按 key 给 `inFlight`（仅 `ap-` 口径，`monitor.ts:503`）与 `status`（含 `stalled` + 门禁处置提示，`monitor.ts:604-626`）；但**手工行会以自身 taskKey 出现**，不是它真正占用的 key。 |
| "为什么没起新 key —— cap 还是 deps 还是 claim 还是 stall？" | 需要 cap 事件 + 现有 `skip`/`blockedBy`/stalled | **cap 那一支零信息**；`blockedBy`（roadmap deps）与 stalled 门禁提示已有（`monitor.ts:504-507`、`:619-625`）。 |

**F5.2 面板应显示几个数（最小建议，design 期输入）**

1. **显示两个数、并把口径写进标签**，不要用一个数回答两个问题：
   - `key slots: {used}/{cap}` —— 用 **conductor 口径**实现（pending+running、roadmap 候选域、`ap-` 前缀 OR `task_path`）；
   - `workers: {N} running` —— 保留现状（`monitor.ts:638`）。
2. **现在的 `slots ${used}/${max}` 必须改名或改口径**，否则第三种语义会继续被读成 conductor 口径（FM 手工 fan-out 期的 `8/2` 会被误读成"conductor 挡住 6 个 key"）。
3. 面板侧实现 conductor 口径需要补两件**已被丢掉**的输入：① `readMonitorState` 的 `workers` 数组当前先过滤 `status!=="running"`（`monitor.ts:248`）——需要改为携带 `status`（否则 pending 口径不可能复刻）；② `MonitorWorker` 需要 `taskPath`（`monitor.ts:251`、接口 `:92-95`），否则 `task_path` 归属规则无法复刻。
4. **占用明细**：在 `key slots` 行下逐 key 列 `key phase status`（stalled 的复用既有门禁提示），即 AC-008 的"能指出哪些 key 占着槽、其中哪些是 stalled"；实现上是"`in_flight_keys` 的 join"，不是新数据源。
5. **`mw doctor` 增一个只读节**（`_doctor_autopilot`，`mw_common.py:2022`）暴露同样两个数 + `max_parallel_keys` + `origins`（该函数已经有 `origins`/`diagnostics` 的现成机制），当前是零字段。
6. **不新增误报的三条护栏**：① 无 running 行 ⇒ `0/{cap}`（现状已满足）；② 无 config.json ⇒ 用默认 2 并标注 `default`（现状 `??` 回退已满足）；③ **无 roadmap / autopilot 未启用** ⇒ 不能显示 `0/2`（会被读成"有余量"），要显示 `n/a (autopilot off)` —— MW 正是这种项目，当前它的 slots 行根本不渲染（`monitor.ts:586`），改成"总是显示两个数"时必须同步保留这个语义。

## 结论 → 决策映射

- **AC-008（可观测性）** ⇒ 本卡给出实现所需的确切口径与两处结构性缺口：`slotsUsed` 现在是"第三种语义"（running-only + `ap-` 前缀 ELSE 自身 taskKey），既不等于 key 层也不等于 worker 层。必须显式定义两个数（`key slots` = conductor 口径、`workers running` = 行计数），并把 `monitor.ts:248`（先过滤 running）与 `MonitorWorker`（缺 `taskPath`）列为实现的必要前置改动。**AC-008 的另一半"不新增误报"现状已满足**（`config` 缺失回退默认 2、无行显示 0、`deriveAutopilotPanel` 全源降级，`monitor.ts:461-465`）。
- **AC-008 的"哪些 key 占着槽、其中哪些 stalled"** ⇒ 数据 join 已经齐全（`in_flight_keys` 由 `_workers.parallel` + `deps_of` 派生；status 来自 roadmap），**不需要新数据源**，只需要面板按 conductor 口径重算一次。注意 stalled key 的残留非终态行**仍然占额**（RQ-1 结论，本卡实测未推翻）。
- **AC-003 / RQ-3（槽位利用率实测）** ⇒ 本卡交付可直接复用的测量法：`[dispatched_at, updated_at)` 半开区间（偏差上界 5 s）或 `trace.log` 的 `[START]/[END]`（直接观测，覆盖率 ≥99%），两者在 FM/E2/MW 上互相印证。**必须用半开区间**：闭区间会把"上一行结束 == 下一行开始"的接缝算成重叠（FM `gui-live-monitor` 006/007 是典型假阳性）。
- **AC-004 / RQ-6（stalled 占槽）** ⇒ 面板当前**无法**指出"这个占槽的 key 是 stalled 的"——它能指出 stalled，也能数槽，但两者的槽口径不同源。按 F5.2(4) 的 join 即可闭合。
- **§1.1.1 现象 (d)**（"`slots 2/2` 时实际在跑的 worker 很少"）⇒ 本卡确认 (d) 的核心是**口径语义**而非数字：`slots 2/2` 只保证"2 个不同 owner 有 running 行"，而 owner 在 `ap-` 场景等于 key、在手工场景等于 taskKey。真正回答 (d) 的是 `workers: N running` 那一行 —— 它已经存在，只是与 `slots` 并排显示时没有区分两种语义。
- **§1.1.1 现象 (c)**（槽位被卡死的 key 占着）⇒ 本卡的增量是：**cap 阻塞没有任何留痕**（F4.1），所以 (c) 的量在现状下只能靠 F3/F3.1 的生命期重建近似，且**永远无法回答"有多少次是 cap 造成的"**；设计期若要让 (c) 可度量，F4.3 的事件是前置条件。
- **U-4 / 设计期输入** ⇒ 在修好口径之前，"并行度够不够"的任何面板读数都是**坏仪表**：MW 这种无 roadmap 的项目面板与 conductor 差 4，FM 手工期差 6（8/2）。建议把"面板双口径 + cap 事件"作为任何 `max_parallel_keys` 取值变更的**前置依赖**，而不是可选优化。
- **P-015 / 记忆前馈** ⇒ 面板读的是 `config.json` 的 `max_parallel_keys`，而该键**不可机器层覆盖**（RQ-1）；面板显示 `slots X/2` 时并不校验 `X` 与 conductor 实算口径一致，所以**跨层配置漂移会直接体现为面板数字**（此处无新事实，仅登记风险）。

## 数据缺口

1. **E2 `4/2`（2026-09-25T03:41:28Z，4 个 `ap-` key）的机制未能从留存物解释**。已知约束：`max_parallel_keys=2`（`config.json` mtime 2026-09-24T02:39，早于该窗口）、`xkey_repair` 未启用（同文件无该键）、`ap-` 前缀为 conductor 专属（`dispatch.py:12-14`）、`_advance_key` 只在带的 cap gate 的 `:291` 被调用、FM 的 `_dispatch_roadmap_writer`/`_xkey_proposal_one` 两条绕 cap 的通道在本例都不适用。候选原因（**均为推断，未验证**）：① E2 跑的 conductor/launcher 是从**打包产物**启动的较早构建，该构建的 cap 行为与当前工作树不一致（工作树 mtime 2026-09-26，晚于该窗口）；② 同项目存在第二个 conductor/launcher 实例（RQ-1 Q3(3)：进程层面允许，beat 协议不互斥派发）；③ roadmap 在窗口期内被人工编辑，导致 `deps_of` 与行集合短暂不一致。**验证所需数据**：该窗口 E2 的 `serve.meta`/`mw.pid` 世代、`.mw/launcher-beat.*` 文件、以及当时安装包版本。⇒ 建议交 RQ-6 或 design 期跟进；本卡只声明"实测观测到 >cap 的 key 并发，且当前代码路径解释不了它"。
2. **历史 tick 的 eligibility 不可重建** ⇒ "因 cap 而未派发的 tick 次数/时长"**无法从现状数据测量**（F4.2(3)）。需要 F4.3 的事件，或一个记录每 tick `(in_flight, eligible_not_dispatched)` 的新文件。
3. **同一 key 同时 ≥2 条 running 行的"是否被 conductor 允许"**：本卡观测到的同 key 并发**全部**来自 PM 手工通道；conductor 通道（`ap-` 行）**未观测到**。但 `_workers.parallel` 里 `ap-` 行的生成路径还有 `_dispatch_roadmap_writer`（`conductor.py:548`）与 xkey 提案（`:3031`）两条**不经过 cap gate** 的通道；本卡未逐一实测这两条通道在同 key 上能否与主循环 worker 并发（`xkey_repair` 默认 false，未激活）。
4. **`slotsUsed` 的"0 而非报错"边界**：本卡只覆盖"无 config / 无 running 行 / 无 roadmap"三态（MW、JCA、OC、UEM 均是 0 行项目）；未覆盖"config.json 存在但字段类型非法/被锁"的解析失败分支（`monitor.ts:470` 的 `configResult.ok` 为假时回退默认 2，逻辑上安全，未实测）。
5. RQ-1 的上游/provider 并发限制缺口不变（本卡不涉及）。

## 机器行

```
[VERIFY] RQ-7: slotsUsed_formula=monitor.ts:246-252(running-only)+509-513(owner=ap-<key>- prefix else own taskKey; size) slotsMax=monitor.ts:522(config?.max_parallel_keys ?? DEFAULT 2; status-model.ts:106) conductor_formula=conductor.py:258-264+2131-2138(non-terminal incl pending; belongs=ap-prefix OR .agenticdoc/<key>/workers/ in task_path; candidate=roadmap deps_of only) observed_used=MW-4/FM-2/E2-1 observed_over_max=yes(FM 2026-09-26T03:05:02Z 3/2; FM 2026-09-19T08:04:14Z 8/2; E2 2026-09-25T03:41:28Z 4/2; MW 2026-08-28T13:00:51Z 7/2; peak same-key concurrency MW=6(pm-manual)/FM=6(pm-manual)/E2=3(pm-manual)) pending_windows_s=0.12-5.18 cap_event_surface=none(conductor.py:289-290; timeline.py:67-85 17 ev types; mw_common.py slot=0 hits; doctor autopilot section has no slot field) minimal_event=cap-blocked in orchestrate() -> timeline via st.timeline.append
```

**数据来源时效**：本文件所有"这一刻"数值对应本地 `2026-09-26 15:40:04`（UTC 约 `07:40Z`）；`_workers.parallel` 持续变化（本次调查期内 MW 该 key 的 running 行 6→5→4）。
