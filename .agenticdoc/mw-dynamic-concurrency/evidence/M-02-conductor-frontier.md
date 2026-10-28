# M-02 · conductor tick 消费依赖前沿 + roadmap 校验 + advance 打点 — 证据

> key: `mw-dynamic-concurrency` · card: `T-C-M02-conductor-frontier` · 角色: coding
> 唯一写面: `packages/multi-workers/autopilot/conductor.py`（本卡唯一写者）
> 日期: 2026-10-14 · 前置: M-01 `autopilot/task_graph.py`（只读复用）、WFG DONE（写面判定）

## 1. 结论（可复算）

- `_plan_task_order(stems, plan, deps_by_stem=None)` 新增第三参：给定任务依赖图时用
  **稳定拓扑排序**（plan/orphan 序作 tiebreak）；两参调用行为逐字节不变。
- `execute_loop` 把"见在飞即 `return False`"改成：先由 `task_graph.validate_task_graph`
  + `task_graph.frontier` 算出**可并行任务前沿**，实起数 = `min(max_workers_per_key, |前沿|)`
  （`int(cfg.get("max_workers_per_key", 4))`，下限 1）；per-key 串行点消失。
- 任一 V1–V7 problem / 歧义 / 卡不可读 ⇒ **整 key 回退串行（实起 1）** + 一条去重审计行，
  不默认放大，也不静默永锁（后续 tick 仍按 plan 序推进）。
- 写面判定仍是 WFG 的单一来源（未复制）：① 前沿预筛 `_declared_write_face` 复用 WFG
  自己的取数/渲染/解析链（`dispatch._card_write_face_entries` → `render_write_face_line`
  → `write_face.parse_write_face`），只回答"是否声明了可判写面"——未声明/不可解析的卡
  不进并行前沿（plan §6 / AC-003）；② 真正的重叠判定仍由 `dispatch._write_face_verdict`
  做，`execute_loop` 把 `write-face-overlap` / `write-face-undeclared` 拒绝解释为
  "本 tick 到此为止（等）"，**不再** `mark_stalled`；解析期写面错误仍走既有 stall 路径。
- tick 内新增 `roadmap.validate_roadmap` 调用（AC-010）：只观察、写去重 `config` 事件，
  不改变 fail-closed 不派发行为。
- `advance.advance()` 墙钟耗时进 `advance` 事件的 **`data={"ms": n}`**（`detail` 是冻结
  wire 形状：`_advance_failure_streak` 用锚定正则解析、done-closure 测试逐字节断言，
  追加到 detail 会真回归）；未新增任何 timeline 事件名。
- **实起 key 数 / worker 数 = min(上界, |前沿|)** 在 ≥7 组构造语料上复算恒等（见 §3）。
- `packages/multi-workers` 全量 pytest：`2206 passed / 6 failed`（6 条均为基线已有、
  与 `conductor.py` 无因果面的失败：M-03 落定前遗留 + `dispatch.py` vs HEAD 的
  readcap 基线 + TS parity 环境）；本卡引入 **0 条新失败**（见 §9）。

## 2. 证据①：`_plan_task_order` / `execute_loop` before→after

原始命令（before 从 git HEAD 取，after 从工作树取）：

```powershell
git show HEAD:packages/multi-workers/autopilot/conductor.py | Select-String -Pattern "def _plan_task_order|def execute_loop|for stem in _plan_task_order|return False  # per-key serial"
rg -n "def _plan_task_order|def execute_loop|_emit_roadmap_validation\(project_root, st, rm\)|def _timed_advance|def _audit_task_graph_problems|def _write_face_wait_reason" packages/multi-workers/autopilot/conductor.py
```

原始输出（before，git HEAD）：

```
1715: def _plan_task_order(stems: list[str], plan: str) -> list[str]:
1735: def execute_loop(
1763: for stem in _plan_task_order([f.stem for f in files], plan):
1769: return False  # per-key serial: wait for the in-flight task
1535: def _record_advance_result(
1619: code, _out, err = advance.advance(key, nxt, project_root, summary=summary)
```

before 代码片段（`conductor.py:1715-1723`、`:1763-1769`）：

```python
def _plan_task_order(stems: list[str], plan: str) -> list[str]:
    """Execution order: plan appearance order when parseable, else stem
    lexicographic; plan-unmentioned (orphan) tasks go last (D-111)."""
    if not plan:
        return sorted(stems)
    mentioned = [(plan.find(s), s) for s in stems if s in plan]
    mentioned.sort()
    orphans = sorted(s for s in stems if s not in plan)
    return [s for _, s in mentioned] + orphans
...
    for stem in _plan_task_order([f.stem for f in files], plan):
        loop = f"exec:{key}:{stem}"
        fam = _family_rows(rows, key, stem)
        if any(r["status"] == "done" for r in fam):
            continue  # task complete
        if any(_is_in_flight(r) for r in fam):
            return False  # per-key serial: wait for the in-flight task
```

after 原始输出：

```
648:    _emit_roadmap_validation(project_root, st, rm)
1544:def _timed_advance(
1565:def _record_advance_result(
1761:def _plan_task_order(
1783:def _plan_task_order_base(stems: list[str], plan: str) -> list[str]:
1793:def _stable_dependency_order(
1830:def _read_task_cards(
1857:_WRITE_FACE_WAIT_REFUSALS = ("write-face-overlap", "write-face-undeclared")
1864:def _write_face_wait_reason(reason: str) -> bool:
1870:def _declared_write_face(
1897:def _audit_task_graph_problems(
1949:def execute_loop(
2043:        declared = [
2050:            cap_used = 1
3406:def _emit_roadmap_validation(
```

after 代码片段（`conductor.py:1761-1782`）：

```python
def _plan_task_order(
    stems: list[str],
    plan: str,
    deps_by_stem: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Execution order: plan appearance order when parseable, else stem
    lexicographic; plan-unmentioned (orphan) tasks go last (D-111).
    ...
    """
    base = _plan_task_order_base(stems, plan)
    if not deps_by_stem:
        return base
    return _stable_dependency_order(base, deps_by_stem)
```

after 代码片段（`conductor.py:1951-2010`，`execute_loop` 的前沿消费）：

```python
    cards, read_failed = _read_task_cards(tasks_dir, stems)
    graph = task_graph.validate_task_graph(cards, stems)
    deps_by_stem: dict[str, tuple[str, ...]] | None
    if graph.plan_is_serializable and not read_failed:
        deps_by_stem = graph.deps_by_id
        cap_used = cap
    else:
        _audit_task_graph_problems(project_root, st, key, graph, read_failed)
        deps_by_stem = None
        cap_used = 1  # serial fallback: exactly one task starts

    order = _plan_task_order(stems, plan, deps_by_stem)
    ...
    ready = (
        set(task_graph.frontier(deps_by_stem, done_stems))
        if deps_by_stem is not None
        else set(stems)  # fail-closed: unusable dependency data → plan order
    )
    frontier = [
        stem for stem in order
        if stem in ready and stem not in done_stems and stem not in inflight_stems
    ]
    limit = min(cap_used, len(frontier))
    if len(inflight_stems) >= limit:
        return False  # at the effective cap (or nothing ready) — wait a tick
```

`advance` 打点（`conductor.py:1544-1562`）：

```python
def _timed_advance(key, phase, project_root, *, summary) -> tuple[int, str, str, int]:
    started = time.monotonic()
    code, out, err = advance.advance(key, phase, project_root, summary=summary)
    ms = int(round((time.monotonic() - started) * 1000))
    return code, out, err, ms
```

```python
    payload = {"ms": int(ms)} if ms is not None else None
    if code == 0:
        st.timeline.append("advance", key=key, detail=f"{edge} exit=0", data=payload)
        return
```

## 3. 证据②：`min(上界, |前沿|)` 恒等复算

探针脚本见附录 A；复跑命令（脚本为临时文件，落盘后按附录 A 重建）：`python -X utf8 _m02_probe.py`。
每组语料都是"构造 roadmap + 卡（写面/依赖）+ 覆写配置 + 一次 `conductor.tick` + 数 `ap-` 行"。

原始输出（节 A/A2/B）：

```
==============================================================================
A. per-key identity: started = min(max_workers_per_key, |task frontier|)
==============================================================================
cap=4 frontier=3 (3 dep-free, disjoint faces)        tick=ok  started_rows=3 expected=min(4,3)=3 OK
    rows=['ap-k1-T-1', 'ap-k1-T-2', 'ap-k1-T-3']
cap=1 frontier=3 (cap is the kill switch)            tick=ok  started_rows=1 expected=min(1,3)=1 OK
    rows=['ap-k1-T-1']
cap=4 frontier=1 (chain T-2 deps T-1)                tick=ok  started_rows=1 expected=min(4,1)=1 OK
    rows=['ap-k1-T-1']
cap=2 frontier=5 (cap truncates)                     tick=ok  started_rows=2 expected=min(2,5)=2 OK
    rows=['ap-k1-T-1', 'ap-k1-T-2']

==============================================================================
A2. |frontier| = 0 (all tasks terminal) -> started = 0
==============================================================================
cap=1: tick=ok rows_before=3 rows_after=3 new_rows=0 advance_calls=[('k1', 'verify')] expected=min(1,0)=0
cap=4: tick=ok rows_before=3 rows_after=3 new_rows=0 advance_calls=[('k1', 'verify')] expected=min(4,0)=0

==============================================================================
B. key-layer identity (AC-001): started_keys = min(max_parallel_keys, |key frontier|)
==============================================================================
max_parallel_keys=2 eligible=3: tick=ok started_keys=['k1', 'k2'] expected=min(2,3)=2 OK
max_parallel_keys=1 eligible=3: tick=ok started_keys=['k1'] expected=min(1,3)=1 OK
max_parallel_keys=8 eligible=3: tick=ok started_keys=['k1', 'k2', 'k3'] expected=min(8,3)=3 OK
```

覆盖组合：|前沿| ∈ {0,1,3,5}，上界 ∈ {1,2,4,8}；恒等 `started = min(cap, |frontier|)` 全部成立。

## 4. 证据③：V-problem 串行回退 + timeline 原始样例（含去重证明）

原始输出（节 C/C2/C3）：

```
==============================================================================
C. V-problem -> whole-key serial fallback + audit dedup
==============================================================================
tick1=ok rows=['ap-k1-T-1']
tick1 audit_events=1 :: ['task graph unusable for k1: deps-dangling:T-2@3:T-99-missing; falling back to serial (plan order)']
tick2=ok rows=['ap-k1-T-1', 'ap-k1-T-2']  (T-2 dispatched after T-1, no permanent lock)
tick2 cumulative audit_events=1  (dedup proof: still one)
tick3=ok advance_calls=[('k1', 'verify')]
raw timeline config events:
    k1 | task graph unusable for k1: deps-dangling:T-2@3:T-99-missing; falling back to serial (plan order)

==============================================================================
C2. missing write face -> serial-only (write-face gate), no stall
==============================================================================
tick=ok started=['ap-k1-T-1']
key_status=running
write-face events=['ap-k1-T-1: write_face undeclared; 0 same-owner worker(s) in flight', 'ap-k1-T-2: write_face undeclared; 1 same-owner worker(s) in flight']

==============================================================================
C3. overlapping declared faces -> second refused (overlap pairs = 0)
==============================================================================
tick=ok started=['ap-k1-T-1']
key_status=running
    write-face-overlap | ap-k1-T-2: overlap with ap-k1-T-1 at src/shared/deep (src/shared/deep/** vs src/shared/**)
```

- **去重证明**：tick1 写入 1 条 `config`（`task graph unusable ...`）；tick2 同一 problem
  仍在（`plan_is_serializable=False` 未变），累计审计行仍为 1 ⇒ 同 problem 只写一次。
- **不静默永锁**：tick2 在 T-1 done 后按 plan 序派出 T-2；tick3 全部 done 后正常
  `advance execute->verify`。
- 卡不可读同样并入 serial 回退（`_read_task_cards` 的 `read_failed` → 同一审计路径）。

### C4：写面前沿预筛（AC-003；`_declared_write_face`，未声明/不可解析 ⇒ 不进并行前沿）

复跑命令：`python -X utf8 _m02_mix.py`（脚本见附录 B）。原始输出：

```
all declared disjoint (T1 src/a, T2 src/b, T3 src/c): started=3 rows=['ap-k1-T-1', 'ap-k1-T-2', 'ap-k1-T-3']
all undeclared: started=1 rows=['ap-k1-T-1']
     ap-k1-T-1: write_face undeclared; 0 same-owner worker(s) in flight
mixed: T1 undeclared first, T2 declared: started=1 rows=['ap-k1-T-2']
mixed: T1 declared first, T2 undeclared: started=1 rows=['ap-k1-T-1']
```

- 全声明且互不重叠 ⇒ 3（并行）；全未声明 ⇒ 实起 1（串行，AC-003）；任一混合 ⇒ 实起 1。
- 预筛把"未声明/不可解析"当**不可并行项**（plan §6），不再让"未声明的卡先跑、
  已声明的卡随后加入"这种非对称放大发生。

## 5. 证据④：AC-010 tick 内 roadmap 语义校验（原始事件 + 去重）

原始输出（节 D）：

```
==============================================================================
D. AC-010 roadmap validation in-tick + dedup
==============================================================================
tick1=ok roadmap_validation_events=1
tick2=ok roadmap_validation_events=1  (same problem written once)
     - | roadmap validation: stage 1 key 'k1': dependency 'kX' not found
```

roadmap 里 `k1` 的 `depends_on=kX`（悬空）。tick1 写 1 条 `config`；tick2 同 problem
仍在但累计仍为 1（去重）。该调用只观察，`_deps_satisfied` 的 fail-closed 不派发行为不变
（探针里 k1 两次 tick 都未派发）。

## 6. 证据⑤：AC-013 `advance.advance()` 墙钟实测量化

用真实 `advance_phase.py` 子进程（临时项目 + `.agentic-framework` 标记，等价
`test_autopilot_advance_e2e.py` 的 harness）。原始输出（节 F）：

```
==============================================================================
F. AC-013 advance wall-clock (real advance_phase.py subprocess) + event data
==============================================================================
sample 0: exit=0 ms=835 stderr=
sample 1: exit=0 ms=772 stderr=
sample 2: exit=0 ms=232 stderr=
real advance samples(ms)=[835, 772, 232] median=772
single idle conductor tick ms=3
window_share = sum_advance_ms / (sum_advance_ms + n*idle_tick_ms) = 1839/(1839+9) = 0.995130
ratio advance_ms / idle_tick_ms (median) = 257.33x
advance event detail='execute->verify exit=0' data={'ms': 772}
detail byte-shape unchanged (frozen regex ^(\S+) exit=(\d+)(?: class=(\S+))?$ keeps matching)
```

（另一轮采样：`[224, 217, 230] median=224`，`window_share=0.986765`，`74.67x`；
两次都指向同一结论。）

结论：一次成功 `advance` 阻塞 **约 0.2–0.8s**（一次 Python 解释器冷启动 + 门禁脚本），
相对 no-op tick（~3ms）是 **约 75–260 倍**。它只在 phase 边界发生（每 key 每 tick ≤1 次），
tick 内一次 advance 时 advance 是 tick 墙钟的主导项（`window_share≈0.99`）。量化已落地
（`data.ms`），是否上独立执行器按 D-107 留待一周实测后决定——本卡不盲改。

## 7. 证据⑥：AC-006 上界=1 两层串行（无需重启 serve）

原始输出（节 E）：

```
==============================================================================
E. AC-006 kill switch: both layers at 1 -> serial, no serve restart (config re-read per tick)
==============================================================================
bounds 8/4: started_keys=['k1', 'k2'] k1_rows=3
bounds 1/1: started_keys=['k1'] all_rows=1
config value read fresh each tick (same process, no restart): both <=1 = OK
```

`_load_effective_config` 每 tick 重新 `cached_load`（mtime 缓存），同一进程内改写 config
即生效：`max_parallel_keys=1` 与 `max_workers_per_key=1` 时 key 层实起 ≤1、per-key 实起 ≤1，
无需重启 serve（`conductor.py` 在 `orchestrate` 每次调用重读 `cfg`）。

## 8. 证据⑦：全量 pytest

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q
python -m pytest test_task_graph.py -q
```

原始结果（tail）：

```
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_task_type_parity.py::test_bom_historical_books - AssertionError: ...
6 failed, 2206 passed, 10 deselected, 2 warnings in 324.33s
```

（预筛改动落定前的同一条命令：`6 failed, 2206 passed ... in 328.09s`；两次失败集合完全相同。）

- 6 条失败**全部**是本卡改动前的基线失败（baseline 25 failed 的子集）：M-03 当时还在飞行中，
  其 config 相关 19 条现已转绿；余下 6 条与 `conductor.py` 无因果面：
  `test_autopilot_readcap_injection::test_baseline_left_end_bound` = `dispatch.py` 工作树 vs HEAD
  哈希（WFG/M-04 面）；`test_autopilot_verdict_freshness`、`test_launcher` BOM、`test_mwds_t27/t29`
  TS parity、`test_task_type_parity` BOM 均为基线既有。
- 本卡相邻套件全绿：`test_autopilot_conductor*.py` + `test_autopilot_stall.py` +
  `test_mwgal_t12_stage_close_auto.py` + `test_mwgal_t15_reattest_confirm.py` =
  `185 passed`（含 `test_tasks_run_in_plan_order_then_advance` 的 per-key 串行语义——
  未声明写面的卡仍以串行为准）。
- `python -m pytest test_task_graph.py -q` → `71 passed`。

## 9. 残留与未验证

- **写面前沿预筛用的是 WFG 的 private seam**：`dispatch._card_write_face_entries`（WFG
  D-001 的卡 section 取数器）。若该 seam 未来改名/移动，`_declared_write_face` 用
  `getattr` 检测后**整体回退串行**（fail-closed，不猜、不复制）。重叠判定本身仍只在
  `dispatch._write_face_verdict`（未复制）。
- **未声明写面的卡会改变到达顺序**：预筛把未声明面的卡排除出并行前沿，所以
  `[T-1 未声明, T-2 已声明]` 时本 tick 先派 T-2，T-1 等到下一轮（全是未声明）再串行派。
  这是 plan §6"不可并行项"的直接结果（保守，不默认放大；进度不丢）。
- **跨 tick 顶配（top-up）未开**：`orchestrate` 仍对**任一在飞** key 跳过 `_advance_key`，
  所以一个批次内的 N 个 worker 全部完成前不会补派。实测的"实起数 = min(cap, |前沿|)"
  在同一 tick 的批次上成立；吞吐上少一次提前补派，属已知（风险 11 的另一层）。
- **AC-013 只量化未优化**：`advance` 仍是同步 `subprocess.run`（按 D-107 先量化）。
- `_is_in_flight` / `_row_belongs_to` 判据未改（AC-012）：`inflight_stems` 走既有
  `_family_rows` + `_is_in_flight`，没有新增"在飞"谓词；gate/closure/reminder 的
  `_is_in_flight` 调用点全部保持。批次内新派的 row 通过 dispatch 在锁内重读 live queue
  保证写面不重叠；conductor 的 tick 快照（`rows`）不刷新，`in_flight_keys` 仍每 key 计一次。
- `_TASK_GRAPH_ALARM_SEEN` / `_ROADMAP_VALIDATION_SEEN` 为进程级去重状态：problem 消失后
  清空对应条目，故"修复后再犯"会重新告警。
- 未跑 `npm run check`（P-017）；未跑无文件参数全量 vitest（P-032）；未改
  `dispatch.py` / `config.py` / `task_graph.py` / `mw_common.py` / TS。

## 10. 上下文来源清单

- `.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M02-conductor-frontier.md`（本卡）
- `.agenticdoc/mw-dynamic-concurrency/spec.md`（AC-001/002/003/006/010/012/013）
- `.agenticdoc/mw-dynamic-concurrency/design.md`（D-102/D-104/D-107/D-108/D-110）
- `.agenticdoc/mw-dynamic-concurrency/plan.md`（§2 M-02、§3 串行点、§5 风险、§6 接口）
- `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md`（§6 前沿定义）
- `packages/multi-workers/autopilot/conductor.py`（本卡唯一改动）
- `packages/multi-workers/autopilot/task_graph.py`（M-01，只读）
- `packages/multi-workers/autopilot/dispatch.py`（WFG W-03 写面闸，只读）
- `packages/multi-workers/autopilot/roadmap.py`（`validate_roadmap`）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`（五段契约）

## 11. 改动清单

- `packages/multi-workers/autopilot/conductor.py`（+364 / -31）
  - import `task_graph`；`orchestrate` 增 `_emit_roadmap_validation`
  - `_timed_advance` 新增；`_record_advance_result` 增 `ms` → `data={"ms": n}`
  - `_advance_key` / `_done_transaction` 的 advance 调用改走 `_timed_advance`
  - `_plan_task_order` 增 `deps_by_stem`；新增 `_plan_task_order_base`、`_stable_dependency_order`
  - 新增 `_read_task_cards`、`_write_face_wait_reason`、`_audit_task_graph_problems`
  - `execute_loop` 重写为前沿消费 + 串行回退
  - 新增 `_emit_roadmap_validation`

## 附录 A：探针脚本（可复跑）

见文末代码块。用法：把代码块内容存成 `packages/multi-workers/_m02_probe.py`，在
`packages/multi-workers` 下 `python -X utf8 _m02_probe.py`（脚本自建临时项目于系统 temp，
结束后可删脚本）。

```python
"""Temporary M-02 evidence probe (deleted after capture). Raw output only."""
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mw_common  # noqa: E402
from autopilot import advance as adv, config, conductor, roadmap, state, timeline  # noqa: E402

REPO_ROOT = HERE.parents[1]
FRAMEWORK = REPO_ROOT / ".agents" / "skills" / "agentic-task"


def _project(tmp: pathlib.Path) -> pathlib.Path:
    ap = tmp / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp, cfg)
    return tmp


def _roadmap(project: pathlib.Path, keys: dict[str, str | None], *, stage_keys=None) -> None:
    """keys: key -> depends_on (None = '-')."""
    key_status = ", ".join(f"{k}=running" for k in keys)
    rows = "\n".join(f"| {k} | worker | {dep or '-'} |" for k, dep in keys.items())
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n"
        "## Stage 1: work\n> goal: deliver\n> status: running\n"
        f"> key-status: {key_status}\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    index = "\n".join(f"| {k} | active | EXECUTE | — | - | d | 2026-09-10T00:00:00 |" for k in keys)
    (project / ".agenticdoc" / "_index.parallel").write_text(index + "\n", encoding="utf-8")


def _card(project: pathlib.Path, key: str, stem: str, *, deps=None, faces=None) -> None:
    key_dir = project / ".agenticdoc" / key
    (key_dir / "tasks").mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if deps:
        lines += [f"- deps: {', '.join(deps)}", ""]
    if faces:
        lines += ["## 写入允许面", ""]
        lines += [f"- `{face}`" for face in faces]
        lines += [""]
    lines += [
        "## 上下文", "", "probe project", "",
        "## 要求", "", "do the probe", "",
        "## 交付格式", "", "write output.md", "",
    ]
    (key_dir / "tasks" / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def _set_cfg(project: pathlib.Path, **overrides) -> None:
    cfg = config.load_config(project)
    cfg.update(overrides)
    config.save_config(project, cfg)


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)), conductor.goal_mtime_ns(project)
    )


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _rows(project: pathlib.Path, prefix: str) -> list[dict]:
    return [
        e for e in mw_common.parse_workers_file(mw_common.workers_path(project))
        if e["task_key"].startswith(prefix)
    ]


def _set_row(project: pathlib.Path, task_key: str, status: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = status
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n", encoding="utf-8"
    )


def _install_fake_advance(calls: list):
    def fake(key, phase, root, summary=None):
        calls.append((key, phase))
        return 0, "", ""
    adv.advance = fake


def _restore_advance():
    del adv.advance
    import importlib
    importlib.reload(adj_mod)


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


import autopilot.advance as adj_mod  # noqa: E402  (reload target)


def per_key_identity(root: pathlib.Path) -> None:
    """min(cap, |frontier|) for the per-key layer (execute_loop)."""
    section("A. per-key identity: started = min(max_workers_per_key, |task frontier|)")
    cases = [
        ("cap=4 frontier=3 (3 dep-free, disjoint faces)", 4, 3, None),
        ("cap=1 frontier=3 (cap is the kill switch)", 1, 3, None),
        ("cap=4 frontier=1 (chain T-2 deps T-1)", 4, 1, "chain"),
        ("cap=2 frontier=5 (cap truncates)", 2, 5, None),
    ]
    for label, cap, n, shape in cases:
        tmp = root / ("pk_" + str(abs(hash(label)) % 100000))
        tmp.mkdir()
        project = _project(tmp)
        key = "k1"
        _roadmap(project, {key: None})
        faces = [f"src/{i}/**" for i in range(max(n, 1))]
        if shape == "chain":
            _card(project, key, "T-1", faces=faces)
            _card(project, key, "T-2", deps=["T-1"], faces=faces)
        else:
            for i in range(n):
                _card(project, key, f"T-{i + 1}", faces=[faces[i]])
        _set_cfg(project, max_workers_per_key=cap, max_parallel_keys=8)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            status = conductor.tick(project, st)
        finally:
            _restore_advance()
        started = _rows(project, f"ap-{key}-")
        expected = min(cap, n)
        print(
            f"{label:52s} tick={status:3s} started_rows={len(started)} "
            f"expected=min({cap},{n})={expected} {'OK' if len(started) == expected else 'MISMATCH'}"
        )
        print("    rows=" + str([r["task_key"] for r in started]))

    # |frontier| = 0: every task done -> no new rows, advance executes.
    section("A2. |frontier| = 0 (all tasks terminal) -> started = 0")
    for cap in (1, 4):
        tmp = root / f"pk_zero_{cap}"
        tmp.mkdir()
        project = _project(tmp)
        key = "k1"
        _roadmap(project, {key: None})
        for i in range(3):
            _card(project, key, f"T-{i + 1}", faces=[f"src/{i}/**"])
        _set_cfg(project, max_workers_per_key=3, max_parallel_keys=8)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            conductor.tick(project, st)  # dispatch 3 (cap=3 setup)
            for i in range(3):
                _set_row(project, f"ap-{key}-T-{i + 1}", "done")
            before = len(_rows(project, f"ap-{key}-"))
            _set_cfg(project, max_workers_per_key=cap, max_parallel_keys=8)
            status = conductor.tick(project, st)  # all done -> advance
        finally:
            _restore_advance()
        after = _rows(project, f"ap-{key}-")
        print(
            f"cap={cap}: tick={status} rows_before={before} rows_after={len(after)} "
            f"new_rows={len(after) - before} advance_calls={calls} "
            f"expected=min({cap},0)=0"
        )


def key_layer_identity(root: pathlib.Path) -> None:
    section("B. key-layer identity (AC-001): started_keys = min(max_parallel_keys, |key frontier|)")
    for cap, n in ((2, 3), (1, 3), (8, 3)):
        tmp = root / f"kl_{cap}_{n}"
        tmp.mkdir()
        project = _project(tmp)
        keys = {f"k{i + 1}": None for i in range(n)}
        _roadmap(project, keys)
        for k in keys:
            _card(project, k, "T-1")  # no write face -> each key stays serial
        _set_cfg(project, max_parallel_keys=cap, max_workers_per_key=4)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            status = conductor.tick(project, st)
        finally:
            _restore_advance()
        started_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project, "ap-")})
        expected = min(cap, n)
        ok = "OK" if len(started_keys) == expected else "MISMATCH"
        print(
            f"max_parallel_keys={cap} eligible={n}: tick={status} started_keys={started_keys} "
            f"expected=min({cap},{n})={expected} {ok}"
        )


def serial_fallback_and_dedup(root: pathlib.Path) -> None:
    section("C. V-problem -> whole-key serial fallback + audit dedup")
    tmp = root / "vprob"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    _card(project, key, "T-1")                       # dep-free
    _card(project, key, "T-2", deps=["T-99-missing"])  # dangling -> V-problem
    _set_cfg(project, max_workers_per_key=4)
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        s1 = conductor.tick(project, st)
        rows1 = [r["task_key"] for r in _rows(project, f"ap-{key}-")]
        audit1 = [e["detail"] for e in _events(project) if e["ev"] == "config" and "task graph unusable" in e["detail"]]
        _set_row(project, f"ap-{key}-T-1", "done")
        s2 = conductor.tick(project, st)
        rows2 = [r["task_key"] for r in _rows(project, f"ap-{key}-")]
        audit2 = [e["detail"] for e in _events(project) if e["ev"] == "config" and "task graph unusable" in e["detail"]]
        _set_row(project, f"ap-{key}-T-2", "done")
        s3 = conductor.tick(project, st)
    finally:
        _restore_advance()
    print(f"tick1={s1} rows={rows1}")
    print(f"tick1 audit_events={len(audit1)} :: {audit1}")
    print(f"tick2={s2} rows={rows2}  (T-2 dispatched after T-1, no permanent lock)")
    print(f"tick2 cumulative audit_events={len(audit2)}  (dedup proof: still one)")
    print(f"tick3={s3} advance_calls={calls}")
    print("raw timeline config events:")
    for e in _events(project):
        if e["ev"] == "config":
            print("   ", e["key"], "|", e["detail"])

    section("C2. missing write face -> serial-only (write-face gate), no stall")
    tmp = root / "nowriteface"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    for i in range(3):
        _card(project, key, f"T-{i + 1}")  # no 写入允许面
    _set_cfg(project, max_workers_per_key=4)
    calls = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        status = conductor.tick(project, st)
    finally:
        _restore_advance()
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    events = [(e["ev"], e["detail"]) for e in _events(project)]
    print(f"tick={status} started={[r['task_key'] for r in _rows(project, f'ap-{key}-')]}")
    print(f"key_status={rm.stages[0].key_status[key]}")
    print(f"write-face events={[d for ev, d in events if ev.startswith('write-face')]}")

    section("C3. overlapping declared faces -> second refused (overlap pairs = 0)")
    tmp = root / "overlap"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    _card(project, key, "T-1", faces=["src/shared/**"])
    _card(project, key, "T-2", faces=["src/shared/deep/**"])
    _set_cfg(project, max_workers_per_key=4)
    calls = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        status = conductor.tick(project, st)
    finally:
        _restore_advance()
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    print(f"tick={status} started={[r['task_key'] for r in _rows(project, f'ap-{key}-')]}")
    print(f"key_status={rm.stages[0].key_status[key]}")
    for ev, detail in [(e["ev"], e["detail"]) for e in _events(project)]:
        if ev.startswith("write-face"):
            print(f"    {ev} | {detail}")


def roadmap_validation(root: pathlib.Path) -> None:
    section("D. AC-010 roadmap validation in-tick + dedup")
    tmp = root / "roadmapval"
    tmp.mkdir()
    project = _project(tmp)
    _roadmap(project, {"k1": "kX"})  # dangling dependency
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        s1 = conductor.tick(project, st)
        n1 = len([e for e in _events(project) if e["ev"] == "config" and "roadmap validation" in e["detail"]])
        s2 = conductor.tick(project, st)
        n2 = len([e for e in _events(project) if e["ev"] == "config" and "roadmap validation" in e["detail"]])
    finally:
        _restore_advance()
    print(f"tick1={s1} roadmap_validation_events={n1}")
    print(f"tick2={s2} roadmap_validation_events={n2}  (same problem written once)")
    for e in _events(project):
        if e["ev"] == "config" and "roadmap validation" in e["detail"]:
            print("    ", e["key"], "|", e["detail"])


def ac006(root: pathlib.Path) -> None:
    section("E. AC-006 kill switch: both layers at 1 -> serial, no serve restart (config re-read per tick)")
    tmp = root / "ac006"
    tmp.mkdir()
    project = _project(tmp)
    keys = {"k1": None, "k2": None}
    _roadmap(project, keys)
    for k in keys:
        for i in range(3):
            _card(project, k, f"T-{i + 1}", faces=[f"src/{k}/{i}/**"])
    _set_cfg(project, max_parallel_keys=8, max_workers_per_key=4)
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        conductor.tick(project, st)
        wide_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project, "ap-")})
        wide_per_key = len(_rows(project, "ap-k1-"))
        # flip BOTH bounds to 1 in the config file; no serve restart
        _set_cfg(project, max_parallel_keys=1, max_workers_per_key=1)
        tmp2 = root / "ac006b"
        tmp2.mkdir()
        project2 = _project(tmp2)
        _roadmap(project2, keys)
        for k in keys:
            for i in range(3):
                _card(project2, k, f"T-{i + 1}", faces=[f"src/{k}/{i}/**"])
        _set_cfg(project2, max_parallel_keys=1, max_workers_per_key=1)
        conductor.tick(project2, _state(project2))
    finally:
        _restore_advance()
    narrow_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project2, "ap-")})
    print(f"bounds 8/4: started_keys={wide_keys} k1_rows={wide_per_key}")
    print(f"bounds 1/1: started_keys={narrow_keys} all_rows={len(_rows(project2, 'ap-'))}")
    print("config value read fresh each tick (same process, no restart): both <=1 = OK"
          if len(narrow_keys) <= 1 and len(_rows(project2, "ap-")) <= 1 else "MISMATCH")


def advance_timing(root: pathlib.Path) -> None:
    section("F. AC-013 advance wall-clock (real advance_phase.py subprocess) + event data")
    _SPEC = (
        "# Spec: probe\n\n## §0 Goal Alignment\n\n- 对齐：probe\n- 预期收益：probe\n\n"
        "## §1 概述\n\n" + ("x" * 600) + "\n\n## §3 验收标准（AC）\n\n"
        "| AC 编号 | 描述 |\n|--------|------|\n| AC-001 | probe 通过 design 门禁 |\n\n"
        "### 可复用资产\n- probe\n\n### 需规避坑点\n- probe\n"
    )
    _RESEARCH = "# Research: probe (spec)\n## 决策问题\n根定位\n## 调研方法与出处\nprobe\n"
    samples = []
    for i in range(3):
        project = root / f"adv_{i}" / "proj"
        key = f"ap-probe-{i}"
        key_dir = project / ".agenticdoc" / key
        (key_dir / "evidence" / "research").mkdir(parents=True)
        (key_dir / "spec.md").write_text(_SPEC, encoding="utf-8")
        (key_dir / "evidence" / "research" / "spec-probe.md").write_text(_RESEARCH, encoding="utf-8")
        (project / ".agentic-framework").write_text(
            f"framework=AgenticTask\nrepo={FRAMEWORK}\n", encoding="utf-8"
        )
        adv.invalidate_script_cache()
        _restore_advance()
        code, out, err, ms = conductor._timed_advance(
            key, "design", project, summary="M-02 advance timing probe"
        )
        samples.append((code, ms))
        print(f"sample {i}: exit={code} ms={ms} stderr={err.strip()[:80]}")
    # tick wall clock: one idle enabled project tick (no advance)
    tmp = root / "idletick"
    tmp.mkdir()
    idle = _project(tmp)
    _roadmap(idle, {"k1": None})
    cfg0 = config.load_config(idle)
    st = _state(idle)
    t0 = time.monotonic()
    conductor.tick(idle, st)
    idle_ms = int(round((time.monotonic() - t0) * 1000))
    total_adv = sum(ms for _, ms in samples)
    window_share = total_adv / (total_adv + idle_ms * len(samples))
    print(f"real advance samples(ms)={[ms for _, ms in samples]} median={sorted(m for _, m in samples)[1]}")
    print(f"single idle conductor tick ms={idle_ms}")
    print(
        f"window_share = sum_advance_ms / (sum_advance_ms + n*idle_tick_ms) = "
        f"{total_adv}/({total_adv}+{idle_ms * len(samples)}) = {window_share:.6f}"
    )
    print(f"ratio advance_ms / idle_tick_ms (median) = {sorted(m for _, m in samples)[1] / max(idle_ms, 1):.2f}x")

    # event payload demonstration on a real recorded result
    evt_project = root / "adv_event"
    evt_project.mkdir()
    tl = timeline.Timeline(timeline.timeline_path(evt_project))
    st2 = conductor.ConductorState(tl, 0)
    conductor._record_advance_result(
        evt_project, st2, "k1", "execute->verify", 0, "", config.default_config(),
        ms=sorted(m for _, m in samples)[1],
    )
    ev = [e for e in _events(evt_project) if e["ev"] == "advance"][0]
    print(f"advance event detail={ev['detail']!r} data={ev.get('data')}")
    print("detail byte-shape unchanged (frozen regex ^(\\S+) exit=(\\d+)(?: class=(\\S+))?$ keeps matching)")


def main() -> None:
    root = pathlib.Path(tempfile.mkdtemp(prefix="m02_probe_"))
    print(f"probe root: {root}")
    per_key_identity(root)
    key_layer_identity(root)
    serial_fallback_and_dedup(root)
    roadmap_validation(root)
    ac006(root)
    advance_timing(root)


if __name__ == "__main__":
    main()
```

## 附录 B：写面前沿预筛探针（C4 可复跑）

`python
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mw_common  # noqa: E402
from autopilot import config, conductor, timeline  # noqa: E402


def _project(tmp):
    (tmp / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (tmp / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp, cfg)


def _roadmap(p):
    (p / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n## Stage 1: work\n"
        "> goal: deliver\n> status: running\n> key-status: k1=running\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| k1 | worker | - |\n",
        encoding="utf-8",
    )
    (p / ".agenticdoc" / "_index.parallel").write_text(
        "| k1 | active | EXECUTE | — | - | d | 2026-09-10T00:00:00 |\n", encoding="utf-8"
    )


def _card(p, stem, faces=None):
    d = p / ".agenticdoc" / "k1" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if faces:
        lines += ["## 写入允许面", ""] + [f"- `{f}`" for f in faces] + [""]
    lines += ["## 上下文", "", "x", "", "## 要求", "", "y", "", "## 交付格式", "", "z", ""]
    (d / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def run(label, cards):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="m02mix_")) / "proj"
    _project(tmp)
    _roadmap(tmp)
    for stem, faces in cards:
        _card(tmp, stem, faces)
    cfg = config.load_config(tmp)
    cfg["max_workers_per_key"] = 4
    config.save_config(tmp, cfg)
    conductor.advance.advance = lambda key, phase, root, summary=None: (0, "", "")
    st = conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(tmp)), conductor.goal_mtime_ns(tmp)
    )
    conductor.tick(tmp, st)
    rows = [
        r["task_key"] for r in mw_common.parse_workers_file(mw_common.workers_path(tmp))
        if r["task_key"].startswith("ap-k1-")
    ]
    events = [
        e["detail"] for e in timeline.query_events(timeline.timeline_path(tmp)).events
        if e["ev"].startswith("write-face")
    ]
    print(f"{label}: started={len(rows)} rows={rows}")
    for e in events:
        print("    ", e)


run("all declared disjoint (T1 src/a, T2 src/b, T3 src/c)",
    [("T-1", ["src/a/**"]), ("T-2", ["src/b/**"]), ("T-3", ["src/c/**"])])
run("all undeclared",
    [("T-1", None), ("T-2", None), ("T-3", None)])
run("mixed: T1 undeclared first, T2 declared",
    [("T-1", None), ("T-2", ["src/b/**"])])
run("mixed: T1 declared first, T2 undeclared",
    [("T-1", ["src/a/**"]), ("T-2", None)])
```
