# M-04 · 派发层 identity 级去重（`dispatch.py` 独占写面）— 证据

卡片：`.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M04-dispatch-identity-dedup.md`
key：`mw-dynamic-concurrency`，批次 B2
本文件是本次唯一证据文件。

结论：**DONE（带 1 处需 PM 授权的既有断言翻动，见 §6.3）**。`dispatch()` 已持有
`workers.lock` 的临界区内、`_write_face_verdict` 之后、`mkdir`/`task.md`/`upsert`
之前，加入 identity 级去重：同一 `task_key` 存在**非终态**行 ⇒ 零副作用拒绝，`reason`
前缀固定 `duplicate-dispatch:`；旧行终态时仍可重派。`conductor._WRITE_FACE_WAIT_REFUSALS`
追加 `"duplicate-dispatch"`，使该拒绝落进"等待下一 tick"族而非 `mark_stalled`。

关键判据（5 连跑，双进程 + conductor dispatch-loop 入口）：

- `direct dispatch()`（双进程同 key 对拍）：`grants=1 refusals=1 rows=1 dispatch_events=1`
- `conductor.execute_loop`（stale snapshot，:2077 调用点）：`grants=1 refusals=1 rows=1
  dispatch_events=1 stalled_events=0 roadmap_key_status=running`
- 改动前同场景基线：`grants=2 refusals=0 rows=1 dispatch_events=2`（row 数恒为 1，证明
  判据是 identity 不是行数）
- 终态重派正例：`first_ok=True second_ok=True`
- 全量 `python -m pytest -q`：`7 failed, 2216 passed`（基线 `6 failed, 2206 passed`；
  唯一新增失败 `test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable`
  是既有断言直接编码了本卡要修的"非终态同 identity 覆盖重派"行为，且该文件不在本卡写入允许面，
  需 PM 授权最小对齐，见 §6.3）

文件 SHA256（工作树，改动后）：

| file | sha256 |
|---|---|
| `packages/multi-workers/autopilot/dispatch.py` | `89640846CB088D34DA964AAB9A42AC49BB585BD9CA1FF39509AE99FC0BFC983F` |
| `packages/multi-workers/autopilot/conductor.py` | `6FAF52682D50571199F1B0A593C622AA49774835766FD230872F35D92CA0168F` |
| `packages/multi-workers/test/test_write_face_dispatch.py` | `D66021FA6796AE00B8A75C1213E25260C4D85714B9AEC3C9BDE5D9F9D06F14AD` |
| `packages/multi-workers/mdc_m04_probe.py`（临时，已删除） | `E8F3ABC8739659DE43D6BE153AF7E6494B0B7FD755F6A8B9394972EED79F869F` |

---

## 1. before→after

### 1.1 `autopilot/dispatch.py`

#### (a) `git show HEAD:`（**pre-WFG**；仅作对照，不是 M-04 的真实 before）

本 key 前置 WFG（mw-write-face-guard）产物在 HEAD 尚未提交，因此 HEAD 版本的
`dispatch()` 里**没有** `_write_face_verdict`，`task.md` 也尚未移入锁内。HEAD 修正点附近：

```text
HEAD:packages/multi-workers/autopilot/dispatch.py:1151
1151:     try:
1152:         mw_common.acquire_lock(lock)
...
1161:     try:
1162:         wpath.parent.mkdir(parents=True, exist_ok=True)
...
1170:         mw_common.upsert_worker_row(wpath, row)
1178:         )
1179:     finally:
1180:         mw_common.release_lock(lock)
```

对照：`def dispatch(` 在 HEAD `:961`，工作树 after `:1234`（行号差来自未提交的 WFG 变更）。
结论：HEAD 不能作为本卡的 before 基线；真实 before 取"探针启动时保存的改动前工作树"
（`dispatch.before.py`，含 WFG、无 identity 判定）。下面的隔离 diff 才是本卡改动。

#### (b) 真实 before（改动前工作树）→ after：隔离 diff 仅含本卡插入

```diff
--- dispatch.before.py
+++ dispatch.py
@@ -1265,6 +1265,11 @@ def dispatch(
         an undeclared face that must stay serial-only (`write-face-undeclared`)
         - AC-014: the judgement, the task.md write and the row write share one
         `workers.lock` critical section, so a refusal cannot leave a task dir.
+      - the same `task_key` already has a non-terminal row in the live queue
+        (`duplicate-dispatch:`, MDC M-04): identity-level, judged inside the
+        same critical section, and zero-side-effect like the write-face
+        refusal. A terminal old row (done/failed/...) still re-dispatches
+        through the upsert, so a retry of the same identity is not sealed off.
@@ -1456,6 +1461,51 @@ def dispatch(
         if refusal is not None:
             return refusal  # zero side effects: no taskDir, no task.md, no row
 
+        # MDC M-04: identity-level duplicate-dispatch guard, INSIDE the same
+        # `workers.lock` critical section (and after the write-face gate) so
+        # the judgement, the task.md write and the row write stay one atomic
+        # step. `upsert_worker_row` replaces a row by `task_key` without ever
+        # asking whether the old row is still in flight: a second dispatch of
+        # a live identity would overwrite the in-flight row with a fresh
+        # `pending` one and rewrite its task.md - the mechanism behind the
+        # RF-1..RF-4 duplicate activation (same identity, two worker
+        # instances, one shared `output.md`).
+        #
+        # The criterion is identity, never row count: under upsert semantics
+        # the row count is always 1, so only "is this task_key already
+        # non-terminal" can tell a duplicate from a requeue. The terminal set
+        # is the single `mw_common._TERMINAL_STATUSES` (the one source already
+        # used by `_write_face_verdict` above and by the conductor's
+        # `_is_in_flight`) - never a local set. A terminal old row still
+        # re-dispatches through upsert (a retry reuses the same identity), so
+        # the retry path is not sealed off.
+        #
+        # Zero side effects, exactly like the write-face refusal above: no
+        # taskDir, no task.md, no queue row, and no second `dispatch` timeline
+        # event (the event vocabulary is frozen; the refusal is observable as
+        # the missing `dispatch` event plus the `duplicate-dispatch:` reason).
+        # No lock is acquired here - nesting `acquire_lock` while holding it
+        # backs off for 14.6h and then raises (RQ-D3).
+        duplicate = next(
+            (
+                row for row in mw_common.parse_workers_file(wpath)
+                if str(row.get("task_key", "")) == task_key
+                and str(row.get("status", "")) not in mw_common._TERMINAL_STATUSES  # noqa: SLF001
+            ),
+            None,
+        )
+        if duplicate is not None:
+            return DispatchResult(
+                ok=False,
+                reason=(
+                    f"duplicate-dispatch: {task_key} already in flight "
+                    f"({duplicate.get('status', '')})"
+                ),
+                task_key=task_key,
+                task_md=None,
+                row_verified=False,
+            )
+
         # 1a. task.md (before the queue row - the crash gap is the orphan
```

after 工作树精确行号（`packages/multi-workers/autopilot/dispatch.py`）：

```text
1234: def dispatch(
1435:         mw_common.acquire_lock(lock)                # 临界区起点
1452:         refusal = _write_face_verdict(              # 既有 WFG 判定（未改语义）
1456:         if refusal is not None: return refusal      # 零副作用
1459:         # MDC M-04: identity-level duplicate-dispatch guard  ← 本卡插入点
1484:         duplicate = next((
1486:                 row for row in mw_common.parse_workers_file(wpath)
1488:                 and str(row.get("status", "")) not in mw_common._TERMINAL_STATUSES
1492:         if duplicate is not None: return DispatchResult(ok=False, ...)
1504:         task_dir.mkdir(parents=True, exist_ok=True) # 判定通过后才 mkdir
1523:         mw_common.upsert_worker_row(wpath, row)
1533:         mw_common.release_lock(lock)                # 临界区终点
```

要求对照：

- 要求 1（锁内 identity 判定 + 零副作用 + 拒绝文案稳定）：`parse_workers_file(wpath)` 读实时队列，
  逐行比对 `task_key`，`status not in mw_common._TERMINAL_STATUSES` ⇒ 返回
  `DispatchResult(ok=False, reason="duplicate-dispatch: <task_key> already in flight (<status>)",
  task_md=None, row_verified=False)`。判定在 `_write_face_verdict` 之后、任何写之前，故不
  `mkdir`、不写 `task.md`、不写行、不产生第二个 `dispatch` 事件。✔
- 要求 2（终态可重派）：只看非终态；终态行落到原 `upsert` 行为。✔（§4）
- 要求 3（不得嵌套加锁）：判定体内无 `acquire_lock`，仅在已持锁临界区读文件。✔
- 要求 4（事件词表冻结）：不新增事件名、也不复用写面审计事件；拒绝不可见为事件，仅表现为
  缺失的 `dispatch` 事件 + `reason`。见 §7。✔
- 要求 5（`_write_face_verdict` 未改）：§1.1(b) 的隔离 diff 不含 `_write_face_verdict` 函数体任何
  字符；拒绝文案未动。✔
- 要求 6（不清理他人行）：判定只读队列、只拒绝自身派发，不重写/清理已存在的行。✔

### 1.2 `autopilot/conductor.py`（仅要求 3b 的两处：注释 + 元组）

before（改动前工作树，`conductor.before.py:1849-1855`）：

```python
#: Dispatch refusals that mean "serial-only right now", not "author error":
#: the write-face gate (mw-write-face-guard W-03, `dispatch._write_face_verdict`)
#: refused because a same-owner worker is in flight. `execute_loop` waits for
#: the next tick instead of stalling the key; the parse-time write-face
#: refusals (`write-face-empty` / `-invalid-entry` / `-escape` /
#: `-outside-base`) stay author errors and keep the historical stall path.
_WRITE_FACE_WAIT_REFUSALS = ("write-face-overlap", "write-face-undeclared")
```

after（`packages/multi-workers/autopilot/conductor.py:1849-1859`）：

```python
#: Dispatch refusals that mean "wait for the next tick", not "author error":
#: these are the **dispatch-wait class** refusals. Two sources feed it: the
#: write-face gate's serial-only / overlap limiter (mw-write-face-guard W-03,
#: `dispatch._write_face_verdict`), which refuses because a same-owner worker is
#: in flight, and the identity-level duplicate-dispatch guard (MDC M-04,
#: `dispatch.dispatch`), which refuses because this `task_key` already has a
#: non-terminal row. `execute_loop` waits for the next tick instead of stalling
#: the key; the parse-time write-face refusals (`write-face-empty` /
#: `-invalid-entry` / `-escape` / `-outside-base`) stay author errors and keep
#: the historical stall path.
_WRITE_FACE_WAIT_REFUSALS = ("write-face-overlap", "write-face-undeclared", "duplicate-dispatch")
```

边界证明：`git diff --no-index conductor.before.py conductor.py` = `1 file changed, 11
insertions(+), 7 deletions(-)`，全部落在 `:1849-1859`；`_write_face_wait_reason` 函数
（`:1866-1869`）与 `:2077` 调用点**零字符改动**（常量名/函数名/语义不变）。`conductor.py`
其它字符未动。

### 1.3 测试对齐（`test/test_write_face_dispatch.py`，本卡允许面）

两处既有断言因 identity 判定翻动，做最小对齐（收紧，非放宽）：

```diff
-def test_same_task_key_is_not_self_refused(tmp_path):
-    """Requirement 3 excludes the dispatch's own task_key, so an idempotent
-    requeue of the same identity does not overlap with itself."""
+def test_same_task_key_is_not_self_refused_by_the_write_face_gate(tmp_path):
+    """Requirement 3 excludes the dispatch's own task_key, so an in-flight
+    same identity is never refused as `write-face-overlap`; the identity-level
+    duplicate-dispatch guard (MDC M-04) is the refusal that fires instead, and
+    it is zero-side-effect (no new task dir, no second row)."""
     first = _dispatch(tmp_path, OWNER, "same", tl)
     second = _dispatch(tmp_path, OWNER, "same", tl)
-    assert first.ok and second.ok, second.reason
+    assert first.ok, first.reason
+    assert not second.ok, second.reason
+    assert second.reason.startswith("duplicate-dispatch:"), second.reason
+    assert second.task_md is None
     assert [r["task_key"] for r in _rows(tmp_path)] == ["ap-wfk-same"]
```

```diff
-def test_race_same_task_key_is_an_idempotent_requeue(tmp_path):
-    """... both grant and the upsert keeps exactly one row."""
+def test_race_same_task_key_exactly_one_grant(tmp_path):
     results, events = _race(tmp_path, OWNER, ["a1", "a1"])
-    assert all(r["ok"] for r in results), results
-    assert [e["ev"] for e in events].count("dispatch") == 2, events
+    grants = [r for r in results if r["ok"]]
+    refusals = [r for r in results if not r["ok"]]
+    assert len(grants) == 1, results
+    assert len(refusals) == 1, results
+    assert refusals[0]["reason"].startswith("duplicate-dispatch:"), results
+    assert [e["ev"] for e in events].count("dispatch") == 1, events
     assert len(_rows(tmp_path)) == 1
```

新增回归（钉住要求 3b 的等待类集合，不重实现判定）：

```python
def test_duplicate_dispatch_refusal_is_a_wait_class_refusal():
    assert conductor._WRITE_FACE_WAIT_REFUSALS == (
        "write-face-overlap", "write-face-undeclared", "duplicate-dispatch"
    )
    assert conductor._write_face_wait_reason(
        "duplicate-dispatch: ap-wfk-same already in flight (pending)"
    )
    assert conductor._write_face_wait_reason("write-face-overlap: overlap-with:x")
    assert conductor._write_face_wait_reason("write-face-undeclared: serial-only (1)")
    assert not conductor._write_face_wait_reason("write-face-empty: no entries")
```

未删除、未 skip、未放宽任何既有断言；`test/test_write_face_dispatch.py`：`30 passed`（原 29）。

---

## 2. 双进程/双入口对拍（改动后，5 连跑）— 原始输出

运行位置：`packages/multi-workers/`（探针用 `__file__` 推导 module root，必须在原位置运行）。
探针脚本见 §附录 A。

`python mdc_m04_probe.py`（module root = 工作树）原始输出：

```text
[VERIFY] M-04 module_root=H:\git\Multi-Workers\packages\multi-workers
[VERIFY] M-04 task_key=ap-k1-T-01-x iterations=5
[VERIFY] M-04 direct-entry iter=1 grants=1 refusals=1 rows=1 dispatch_events=1 reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-entry iter=1 grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-tick iter=1 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 direct-entry iter=2 grants=1 refusals=1 rows=1 dispatch_events=1 reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-entry iter=2 grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-tick iter=2 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 direct-entry iter=3 grants=1 refusals=1 rows=1 dispatch_events=1 reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-entry iter=3 grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-tick iter=3 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 direct-entry iter=4 grants=1 refusals=1 rows=1 dispatch_events=1 reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-entry iter=4 grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-tick iter=4 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 direct-entry iter=5 grants=1 refusals=1 rows=1 dispatch_events=1 reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-entry iter=5 grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running reason=duplicate-dispatch: ap-k1-T-01-x already in flight (pending)
[VERIFY] M-04 conductor-tick iter=5 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 terminal-redispatch first_ok=True second_ok=True rows=1 dispatch_events=2 reason=
[VERIFY] M-04 SUMMARY {"module_root": "H:\\git\\Multi-Workers\\packages\\multi-workers", "task_key": "ap-k1-T-01-x", "direct_entry": [{"rows": 1, "dispatch_events": 1, "grants": 1, "refusals": 1, ...}], "conductor_entry": [{..., "stalled_events": 0, "roadmap_key_status": "running"} x5], "conductor_tick": [{"dispatch_events": 1, ...} x5], "terminal_redispatch": {"first_ok": true, "second_ok": true, "rows": 1, "dispatch_events": 2}}
```

- direct entry = **两个真实进程**经文件 barrier 同时 `dispatch()` 同一 `task_key`
  `ap-k1-T-01-x`（同 WFG 测试的 `_race` 形态，锁不 mock）。
- conductor entry = `conductor.execute_loop`（`conductor.tick` 内 :2075 的唯一 dispatch 调用点）
  对同一 stale `rows` snapshot 连跑两次 —— 即 tick 读队列与 dispatch 在锁内重读之间的窗口。
- `conductor-tick` = 两次真实 `conductor.tick`；因 tick 每次重读队列、其自带 in-flight 前置判定
  会先短路第二次派发（`dispatch_calls=1 refusals=0`），作为正常路径对照，同样 `stalled_events=0`。

---

## 3. 基线对照（改动前，同场景）— 原始输出

基线 module root：`%TEMP%\mdc_m04\base_pkg`（复制 `mw_common.py` + `autopilot/`，仅用
改动前 `dispatch.py` 覆盖；`duplicate-dispatch` 出现次数 = 0）。运行：

```text
python mdc_m04_probe.py --module-root %TEMP%\mdc_m04\base_pkg
```

原始输出（前 8 行；5 轮其余输出同形）：

```text
[VERIFY] M-04 module_root=C:\Users\wenbozhou\AppData\Local\Temp\mdc_m04\base_pkg
[VERIFY] M-04 task_key=ap-k1-T-01-x iterations=5
[VERIFY] M-04 direct-entry iter=1 grants=2 refusals=0 rows=1 dispatch_events=2 reason=
[VERIFY] M-04 conductor-entry iter=1 grants=2 refusals=0 rows=1 dispatch_events=2 stalled_events=0 roadmap_key_status=running reason=
[VERIFY] M-04 conductor-tick iter=1 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
[VERIFY] M-04 direct-entry iter=2 grants=2 refusals=0 rows=1 dispatch_events=2 reason=
[VERIFY] M-04 conductor-entry iter=2 grants=2 refusals=0 rows=1 dispatch_events=2 stalled_events=0 roadmap_key_status=running reason=
[VERIFY] M-04 conductor-tick iter=2 statuses=['ok', 'ok'] dispatch_calls=1 grants=1 refusals=0 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
```

判据证明：改动前 `dispatch` 事件数 = **2**，但 `rows` = **1**（`upsert` 按 `task_key` 覆盖，
行数恒为 1）。⇒ 行数无法区分重复派发；只有 identity（同 `task_key` 是否非终态）能做判据。
这正是 `.agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` 的
RF-1..RF-4 重复激活（两个 worker 实例、共写一份 `output.md`）的机制面，本卡为其根修。

---

## 4. 终态重派正例（要求 2）

探针 `terminal-redispatch` 段：先派发 `ap-k1-T-01-x`，把该行 status 置 `done`，再对同一
identity 派发；原始输出：

```text
[VERIFY] M-04 terminal-redispatch first_ok=True second_ok=True rows=1 dispatch_events=2 reason=
```

第二次 `ok=True`、`row_verified` 走原 upsert 路径（retry 复用同一 identity），重试路径未被堵死。

---

## 5. `duplicate-dispatch` 拒绝不触发 `mark_stalled`（要求 3b）

§2 的 `conductor-entry` 每轮直接观测：

```text
grants=1 refusals=1 rows=1 dispatch_events=1 stalled_events=0 roadmap_key_status=running
```

即：`execute_loop` 收到 `ok=False` 且 `reason` 前缀 `duplicate-dispatch:` 时，命中
`_write_face_wait_reason`（`conductor.py:2081`）⇒ `return dispatched_any`（等待下一 tick），
不发生 `mark_stalled`（无 `stalled` timeline 事件、roadmap `key-status` 仍 `running`、无
stalled gate）。若把 `"duplicate-dispatch"` 从 `_WRITE_FACE_WAIT_REFUSALS` 移除，
`execute_loop` 会走 `mark_stalled(... reason_code="exec-dispatch-refused")`，与本卡
"不要造永久 stall"的判面冲突 —— 该反事实由 §1.3 新增单测锚定等待类集合间接覆盖。

（`conductor-tick` 正常路径同样 `stalled_events=0`。）

---

## 6. 验收命令与全量 pytest

### 6.1 `python -m pytest -q`（工作树，改动后）

原始 tail：

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable
FAILED test_task_type_parity.py::test_bom_historical_books - AssertionError: ...
7 failed, 2216 passed, 10 deselected, 2 warnings in 415.96s (0:06:55)
```

退出码：`EXIT=1`。

改动前基线（同一工作树，仅本卡改动前；`python -m pytest -q`）：

```text
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_task_type_parity.py::test_bom_historical_books - AssertionError: ...
6 failed, 2206 passed, 10 deselected, 2 warnings in 314.32s (0:05:14)
```

退出码：`EXIT=1`。

失败集对比：基线 6 条全部复现（与 M-02 记录的基线一致）；**新增 1 条**：
`test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable`（§6.3）。
`passed` 从 2206 → 2216：+1 为本卡新增单测，+9 为并行 session 在本卡运行期间新增的测试
（本卡未触碰其文件）。

### 6.2 卡片验收命令原文

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q
python -m pytest test_write_face_dispatch.py -q
```

- 第一条：见 §6.1。
- 第二条（卡片给的路径）**在当前工作树不存在**，原文输出：

```text
ERROR: file or directory not found: test_write_face_dispatch.py
no tests ran in 0.00s
EXIT=4
```

实际文件在 `test/test_write_face_dispatch.py`（卡片路径少了 `test/`；文件头的 Run 行也是
`python -m pytest test/test_write_face_dispatch.py -q`）。用实际路径：

```text
python -m pytest test/test_write_face_dispatch.py -q
.............................                                             [100%]
30 passed in 0.59s
EXIT=0
```

### 6.3 需 PM 授权的新增失败（不在本卡写入允许面）

`test_rag_launcher.py::TestDispatchRagBlock::test_dispatch_end_to_end_is_stable` 第 383-388 行
对同 identity 连续 `dispatch()` 两次，断言第二次 `ok=True` 且 task.md 字节相同：

```python
second = dispatch_mod.dispatch(
    self.root, "k1", "t07", "repair", "Do the RAG work.",
    loop="L", attempt=1,
)
self.assertTrue(second.ok)
```

第一次派发后该行 status = `pending`（非终态），故 identity 去重必须拒绝第二次 —— 这与本卡
要求 1 完全一致；该断言正是 RF-1..RF-4"非终态同 identity 覆盖重派"的既有编码。该文件
**不在**本卡写入允许面（卡片只列 `test_write_face_dispatch.py`），故本卡未修改它，仅上报。
最小对齐建议（需 PM 授权，二选一，均不放宽）：

1. 两次派发之间把该行置终态（`_set_row` 风格），再断言第二次 `ok=True`；或
2. 断言第二次 `not second.ok` 且 `second.reason.startswith("duplicate-dispatch:")`，保留
   "首次 task.md RAG 块渲染稳定"的原意（该测试真正要验的是渲染字节稳定，不是重派语义）。

已知该文件属 mw-rag 面、由其它 session 维护；本卡不越界。

---

## 7. 事件词表冻结（要求 4）

- 未新增任何 timeline 事件名。
- `duplicate-dispatch` 拒绝 **不写** timeline 事件（也未复用 WFG 的
  `write-face-overlap` / `-undeclared` / `-rejected` 审计事件 —— 复用会把 identity 拒绝误标为写面
  审计）。拒绝的可观测面 = 缺失的 `dispatch` 事件 + `DispatchResult.reason` 前缀。
- 复用审计行的对齐由调用方承担：`conductor.execute_loop` 对等待类拒绝本就 `return`（§5），
  不额外写事件。

---

## 8. 残留与未验证

- `conductor.tick` 连续两次不会触发 `duplicate-dispatch`：tick 每轮重读队列，`execute_loop`
  的 `inflight_stems` 前置判定会先短路（§2 `conductor-tick` 行）。因此要求 3b 的判面用
  `execute_loop`（tick 的唯一 dispatch 调用点，`conductor.py:2075`）对 stale snapshot 复现；
  这是"tick 读队列 ↔ dispatch 锁内重读"之间真实存在的窗口，非构造巧合。
- 其它 dispatch 调用点（`_advance_key` 的 L2 verifier/fix、L3、roadmap、repair、phase-writer）
  未逐个接 `duplicate-dispatch` 到"等待"分支；本卡按卡片 3b 只改 `_WRITE_FACE_WAIT_REFUSALS`
  这一处。若这些调用点在 stale snapshot 下被 identity 拒绝，仍走各自的既有失败路径（与
  WFG 写面拒绝在这些点的处理同形，非本卡引入的新语义面）。
- `test_rag_launcher.py` 新增 1 红，需 PM 授权最小对齐（§6.3）。
- 全量 pytest 期间有并行 session 增删测试文件，`passed` 总量（2216）含其漂移；
  失败集对比已按逐条 diff 核对。
- 未运行：`npm run check`（P-017）、无文件参数 vitest（P-032）、任何 git 写操作。
- 未触碰：`mw_common.py` / `mw.py` / `launcher.py`（只读）、`config.py` / `task_graph.py`、
  `conductor.py` 除 §1.2 两处外的字符、`packages/coding-agent/**`。

---

## 9. 上下文来源

- `.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M04-dispatch-identity-dedup.md`（本卡）
- `.agenticdoc/mw-dynamic-concurrency/workers/mdc-m04-dispatch-dedup/task.md`（派发任务书）
- `.agenticdoc/goal.md`（项目级目标锚点）
- `.agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md`（RF-1..RF-4 重复激活）
- `packages/multi-workers/autopilot/dispatch.py`（WFG 写面闸 + 本卡插入点）
- `packages/multi-workers/autopilot/conductor.py`（`execute_loop` / `_write_face_wait_reason`）
- `packages/multi-workers/mw_common.py`（`_TERMINAL_STATUSES` / `parse_workers_file` /
  `upsert_worker_row`，只读）
- `packages/multi-workers/test/test_write_face_dispatch.py`（WFG 既有测试，最小对齐）
- `packages/multi-workers/test_autopilot_conductor_exec.py`（conductor 探针 harness 形态参考）

---

## 附录 A · 可复跑探针脚本（运行位置：`packages/multi-workers/`；跑完已删除）

```python
"""M-04 dispatch identity dedup probe (TEMPORARY; delete after the run).

Card: `.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M04-dispatch-identity-dedup.md`

Run from `packages/multi-workers/` (the probe derives its module root from
`__file__`; a `--module-root` override lets the SAME probe also drive the
pre-change module tree for the baseline comparison):

    python mdc_m04_probe.py
    python mdc_m04_probe.py --module-root <dir-with-mw_common+autopilot>

Output is one `[VERIFY] ...` line per observation plus a JSON summary, so the
raw text is the evidence for cards M-04 deliverables 2/3/4.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

_p = argparse.ArgumentParser()
_p.add_argument("--module-root", default=None)
_p.add_argument("--iterations", type=int, default=5)
_args, _unknown = _p.parse_known_args()

PKG_DIR = pathlib.Path(__file__).resolve().parent
MOD_ROOT = pathlib.Path(_args.module_root).resolve() if _args.module_root else PKG_DIR
sys.path.insert(0, str(MOD_ROOT))

import mw_common  # noqa: E402
from autopilot import conductor, config, dispatch, timeline  # noqa: E402

ITERS = _args.iterations
OWNER = "k1"
STEM = "T-01-x"
TASK_KEY = dispatch.task_key_for(OWNER, STEM)

_CARD = (
    "# T-01-x\n"
    "\n"
    "## 上下文\n"
    "\n"
    "Probe card.\n"
    "\n"
    "## 要求\n"
    "\n"
    "Do the work.\n"
    "\n"
    "## 写入允许面\n"
    "\n"
    "- `packages/x/**`\n"
)


def _write_card(project: pathlib.Path) -> None:
    card_dir = project / ".agenticdoc" / OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{STEM}.md").write_text(_CARD, encoding="utf-8", newline="\n")


def _bare_project(project: pathlib.Path) -> pathlib.Path:
    (project / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    _write_card(project)
    return project


def _conductor_project(project: pathlib.Path) -> pathlib.Path:
    """The conductor harness shape (mirrors test_autopilot_conductor_exec.py)."""
    ap = project / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (project / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(project, cfg)
    (ap / "_roadmap.md").write_text(
        "# Roadmap\n"
        "> generated_at: t\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        "> status: running\n"
        f"> key-status: {OWNER}=running\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"| {OWNER} | worker | - |\n",
        encoding="utf-8",
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(
        f"| {OWNER} | active | EXECUTE | \u2014 | - | d | 2026-09-10T00:00:00 |\n",
        encoding="utf-8",
    )
    _write_card(project)
    return project


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(
        project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    ).events


def _rows(project: pathlib.Path) -> list[dict]:
    return mw_common.parse_workers_file(mw_common.workers_path(project))


def _stalled_events(project: pathlib.Path) -> int:
    return sum(1 for e in _events(project) if e.get("ev") == "stalled")


def _roadmap_key_status(project: pathlib.Path) -> str:
    text = (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("> key-status:"):
            body = line.split(":", 1)[1]
            for pair in body.split(","):
                k, _, v = pair.strip().partition("=")
                if k == OWNER:
                    return v
    return "<missing>"


# ── entry 1: direct dispatch(), two real processes racing one identity ────────

_CHILD = r"""
import json, os, pathlib, sys, time
mod_root, root, owner, stem, barrier = sys.argv[1:6]
sys.path.insert(0, mod_root)
from autopilot import dispatch, timeline as tl_mod
root = pathlib.Path(root); barrier = pathlib.Path(barrier)
(barrier / ("ready-" + str(os.getpid()))).write_text("1", encoding="utf-8")
deadline = time.time() + 60
while not (barrier / "start").exists():
    if time.time() > deadline:
        raise SystemExit("barrier timeout")
    time.sleep(0.005)
tl = tl_mod.Timeline(root / ".agenticdoc" / "_autopilot" / "timeline.jsonl")
r = dispatch.dispatch(
    root, owner, stem, "phase-writer", "Do the work.",
    loop="exec:" + owner + ":" + stem, attempt=1, timeline=tl,
)
print(json.dumps({"ok": r.ok, "reason": r.reason}))
"""


def race_direct(project: pathlib.Path) -> list[dict]:
    barrier = project / "_barrier"
    barrier.mkdir()
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(MOD_ROOT), str(project), OWNER, STEM, str(barrier)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    deadline = time.time() + 60
    while len(list(barrier.glob("ready-*"))) < 2:
        if time.time() > deadline:
            break
        time.sleep(0.005)
    (barrier / "start").write_text("go", encoding="utf-8")
    results: list[dict] = []
    for proc in procs:
        out, err = proc.communicate(timeout=180)
        assert proc.returncode == 0, (proc.returncode, err)
        results.append(json.loads([ln for ln in out.splitlines() if ln.strip()][-1]))
    return results


# ── entry 2: conductor dispatch-loop (execute_loop, the tick's call site) ────

def conductor_entry(project: pathlib.Path) -> dict:
    """Drive the conductor's dispatch-loop entry twice with the SAME stale
    ``rows`` snapshot — the exact window between the tick's row read and
    ``dispatch``'s lock re-read. The second call must reach ``dispatch`` and be
    refused by the identity guard, and ``execute_loop`` must treat it as a
    wait (no ``mark_stalled``).

    ``dispatch.dispatch`` is spied on so grants/refusals are measured from the
    real return values, never assumed."""
    st = conductor.ConductorState(
        timeline.Timeline(project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"),
        conductor.goal_mtime_ns(project),
    )
    cfg = conductor._load_effective_config(project)  # noqa: SLF001 - probe seam
    stale_rows = _rows(project)  # empty: the snapshot taken before either write
    rounds: dict[str, int] = {}
    results: list[dict] = []
    real = dispatch.dispatch

    def spy(*a, **k):
        r = real(*a, **k)
        results.append({"ok": r.ok, "reason": r.reason})
        return r

    dispatch.dispatch = spy
    try:
        first = conductor.execute_loop(project, st, OWNER, cfg, stale_rows, rounds)
        second = conductor.execute_loop(project, st, OWNER, cfg, stale_rows, rounds)
    finally:
        dispatch.dispatch = real
    return {"first": first, "second": second, "results": results}


def conductor_tick_entry(project: pathlib.Path) -> dict:
    """Two literal ``conductor.tick`` calls. The tick re-reads the queue each
    time, so its own in-flight pre-check short-circuits the second dispatch
    before ``dispatch()`` is even called; this records that normal-path
    observation (still no ``mark_stalled``)."""
    st = conductor.ConductorState(
        timeline.Timeline(project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"),
        conductor.goal_mtime_ns(project),
    )
    results: list[dict] = []
    real = dispatch.dispatch

    def spy(*a, **k):
        r = real(*a, **k)
        results.append({"ok": r.ok, "reason": r.reason})
        return r

    dispatch.dispatch = spy
    try:
        statuses = [conductor.tick(project, st), conductor.tick(project, st)]
    finally:
        dispatch.dispatch = real
    return {"statuses": statuses, "results": results}


def summarise(project: pathlib.Path, results: list[dict] | None) -> dict:
    rows = _rows(project)
    events = [e.get("ev") for e in _events(project)]
    grants = (sum(1 for r in results if r["ok"]) if results is not None else None)
    refusals = (sum(1 for r in results if not r["ok"]) if results is not None else None)
    reasons = [r["reason"] for r in results or [] if not r["ok"]]
    return {
        "rows": len(rows),
        "dispatch_events": events.count("dispatch"),
        "grants": grants,
        "refusals": refusals,
        "refusal_reasons": reasons,
    }


def main() -> int:
    print(f"[VERIFY] M-04 module_root={MOD_ROOT}")
    print(f"[VERIFY] M-04 task_key={TASK_KEY} iterations={ITERS}")

    import tempfile

    direct_outcomes: list[dict] = []
    conductor_outcomes: list[dict] = []
    tick_outcomes: list[dict] = []

    for it in range(1, ITERS + 1):
        with tempfile.TemporaryDirectory(prefix="m04-direct-") as tmp:
            project = _bare_project(pathlib.Path(tmp))
            results = race_direct(project)
            s = summarise(project, results)
            direct_outcomes.append(s)
            note = s["refusal_reasons"][0] if s["refusal_reasons"] else ""
            print(
                f"[VERIFY] M-04 direct-entry iter={it} grants={s['grants']} "
                f"refusals={s['refusals']} rows={s['rows']} "
                f"dispatch_events={s['dispatch_events']} reason={note}"
            )

        with tempfile.TemporaryDirectory(prefix="m04-conductor-") as tmp:
            project = _conductor_project(pathlib.Path(tmp))
            run = conductor_entry(project)
            s = summarise(project, run["results"])
            s["stalled_events"] = _stalled_events(project)
            s["roadmap_key_status"] = _roadmap_key_status(project)
            conductor_outcomes.append(s)
            note = s["refusal_reasons"][0] if s["refusal_reasons"] else ""
            print(
                f"[VERIFY] M-04 conductor-entry iter={it} grants={s['grants']} "
                f"refusals={s['refusals']} rows={s['rows']} "
                f"dispatch_events={s['dispatch_events']} "
                f"stalled_events={s['stalled_events']} "
                f"roadmap_key_status={s['roadmap_key_status']} reason={note}"
            )

        with tempfile.TemporaryDirectory(prefix="m04-tick-") as tmp:
            project = _conductor_project(pathlib.Path(tmp))
            run = conductor_tick_entry(project)
            s = summarise(project, run["results"])
            s["stalled_events"] = _stalled_events(project)
            s["roadmap_key_status"] = _roadmap_key_status(project)
            tick_outcomes.append(s)
            print(
                f"[VERIFY] M-04 conductor-tick iter={it} statuses={run['statuses']} "
                f"dispatch_calls={len(run['results'])} grants={s['grants']} "
                f"refusals={s['refusals']} rows={s['rows']} "
                f"dispatch_events={s['dispatch_events']} "
                f"stalled_events={s['stalled_events']} "
                f"roadmap_key_status={s['roadmap_key_status']}"
            )

    # terminal-row re-dispatch positive case (requirement 2).
    with tempfile.TemporaryDirectory(prefix="m04-retry-") as tmp:
        project = _bare_project(pathlib.Path(tmp))
        tl = timeline.Timeline(project / ".agenticdoc" / "_autopilot" / "timeline.jsonl")
        first = dispatch.dispatch(
            project, OWNER, STEM, "phase-writer", "Do the work.",
            loop=f"exec:{OWNER}:{STEM}", attempt=1, timeline=tl,
        )
        wpath = mw_common.workers_path(project)
        entries = mw_common.parse_workers_file(wpath)
        for e in entries:
            if e["task_key"] == TASK_KEY:
                e["status"] = "done"
        wpath.write_text(
            "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        second = dispatch.dispatch(
            project, OWNER, STEM, "phase-writer", "Do the work.",
            loop=f"exec:{OWNER}:{STEM}", attempt=1, timeline=tl,
        )
        redo = {
            "first_ok": first.ok,
            "second_ok": second.ok,
            "second_reason": second.reason,
            "rows": len(_rows(project)),
            "dispatch_events": [e.get("ev") for e in _events(project)].count("dispatch"),
        }
        print(
            f"[VERIFY] M-04 terminal-redispatch first_ok={redo['first_ok']} "
            f"second_ok={redo['second_ok']} rows={redo['rows']} "
            f"dispatch_events={redo['dispatch_events']} reason={redo['second_reason']}"
        )

    summary = {
        "module_root": str(MOD_ROOT),
        "task_key": TASK_KEY,
        "direct_entry": direct_outcomes,
        "conductor_entry": conductor_outcomes,
        "conductor_tick": tick_outcomes,
        "terminal_redispatch": redo,
    }
    print("[VERIFY] M-04 SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

```
