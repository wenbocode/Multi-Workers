# T-03 回执：三个 timeline 事件名（`l3-aborted` / `gate-reminder` / `contract-refused`）

- Key: `mw-gate-verdict-hardening`（phase=EXECUTE）· 波次 0 · 卡：`tasks/T-03-event-names.md`
- 基线：`git rev-parse --short HEAD` = **776b82d7f**；开工前 `git status --porcelain -- packages/multi-workers/autopilot/timeline.py` = **空**（干净）
- 状态：**完成（Python 半边）**。VERIFY 1 绿；VERIFY 2 **按卡预期的唯一红行 = 计数锁（`len == 23`），归 T-14**；15 passed。
- **TS 半边 = T-05**（`status-model.ts` 的 `EVENT_TYPES`）。本卡落地后 TS 侧尚未镜像，故跨语言集合相等断言（VC-011/VC-019）在 T-05 落地前**预期为红**（P-021），本卡不触碰任何 TS 文件。

## 1. 改动（唯一写面）

`packages/multi-workers/autopilot/timeline.py` — 仅 `frozenset` 字面量追加，行号：

- `packages/multi-workers/autopilot/timeline.py:94-104` — 追加 3 个名字 + 注释块；插入点紧随既有 pre-admitted 段（`evidence-reconciliation`/`stage-reopen-refused`，`:92-93`）。
- `timeline.py:102` = `"l3-aborted",` · `:103` = `"gate-reminder",` · `:104` = `"contract-refused",`（逐字，无改写、无前缀）。

```diff
@@ -93,6 +93,17 @@ EVENT_TYPES: frozenset[str] = frozenset({
     "review-escalated",
     "evidence-reconciliation",
     "stage-reopen-refused",
+    # Gate verdict hardening (mw-gate-verdict-hardening, T-03, design D-002/
+    # D-016): vocabulary first, producers later — the same pre-admission
+    # precedent as the block above (producers land in T-01/T-07/T-10, the TS
+    # mirror in T-05). Names are verbatim; the cross-language parity test
+    # (`autopilot-event-parity.test.ts`) asserts set equality against the TS
+    # half, so neither side may rename or prefix them. Adding unused
+    # vocabulary is safe: EVENT_TYPES is an include-set for filtering, not a
+    # rejection gate (Timeline.append's "never raises" contract is untouched).
+    "l3-aborted",
+    "gate-reminder",
+    "contract-refused",
 })
```

`git diff --stat`：`1 file changed, 11 insertions(+)`（无删除、无其它语义改动；`Timeline.append` "Never raises" 未动、未发射/未消费）。

## 2. [VERIFY] 原文与输出

### VERIFY 1（绿）

```console
PS> cd packages/multi-workers && python -X utf8 -c "from autopilot import timeline; t=set(timeline.EVENT_TYPES); assert {'l3-aborted','gate-reminder','contract-refused'} <= t; print(len(t), sorted({'l3-aborted','gate-reminder','contract-refused'}))"
```

```text
26 ['contract-refused', 'gate-reminder', 'l3-aborted']
```

`len(EVENT_TYPES)` 23 → **26**（+3，与 plan §2.1「Python 计数测试 23 → 26」一致）。

### VERIFY 2（预期红在计数锁）

```console
PS> cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_timeline.py -q -p no:randomly
```

```text
F...............                                                         [100%]
================================== FAILURES ===================================
___________________ test_append_line_schema_all_event_types ___________________

    def test_append_line_schema_all_event_types(tmp_path: pathlib.Path) -> None:
        path = tmp_path / "timeline.jsonl"
        writer = tl.Timeline(path)
        for ev in sorted(tl.EVENT_TYPES):
            assert writer.append(ev, key=f"key-{ev}", stage=1, detail=f"detail for {ev}") is not None
>       assert len(tl.EVENT_TYPES) == 23  # enum locked by D-109; +target-config-rejected (mw-dual-workspace D-005 fail-closed dispatch); +resume, +l3-no-verdict (mw-autopilot-stall-feedback AC-004/AC-012); +6 gate-redesign names (mw-autopilot-slot-capacity D-005/D-006/D-009, two-side parity)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 26 == 23
E        +  where 26 = len(frozenset({'advance', 'beat', 'config', 'contract-refused', 'dispatch', 'evidence-reconciliation', ...}))
E        +    where frozenset({'advance', 'beat', 'config', 'contract-refused', 'dispatch', 'evidence-reconciliation', ...}) = tl.EVENT_TYPES

test_autopilot_timeline.py:48: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_timeline.py::test_append_line_schema_all_event_types - ...
1 failed, 15 passed in 0.16s
```

**红行 = `test_autopilot_timeline.py:48` 的 `len(tl.EVENT_TYPES) == 23` 计数锁**，是本卡预期的唯一红行，**未修改**（属 T-14 统一刷新，避免与 T-05 抢同一条锁）。除该计数锁外**零语义失败**：`15 passed`（含 `:46` 逐名 append schema 遍历、LF/UTF-8 对称、seq/回放/轮转/§9 容错）。计数锁之外无其他断言被本卡改动触发。

## 3. 非空洞对照（真跑贴红）

### 3.1 摘名 ⇒ `test_autopilot_timeline.py` 转红（实际执行）

临时从 `EVENT_TYPES` 摘掉 `"contract-refused"`（脚本 `workers/mwg-t03-event-names/_mutate.py`，仅用于对照；随后用 `git checkout -- <file>` 复原并重放本卡 diff）：

```text
removed contract-refused
count = 25
contract-refused present = False
        for ev in sorted(tl.EVENT_TYPES):
            assert writer.append(ev, key=f"key-{ev}", stage=1, detail=f"detail for {ev}") is not None
>       assert len(tl.EVENT_TYPES) == 23  # enum locked by D-109; ...
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: assert 25 == 23
test_autopilot_timeline.py:48: AssertionError
=========================== short test summary info ============================
FAILED test_autopilot_timeline.py::test_append_line_schema_all_event_types - ...
1 failed, 15 passed in 0.16s
```

⇒ 断言**确实读这张表**（26→绿/25→红），非空洞。复原后复跑 VERIFY 1/2，输出即上文 §2（26；同一条计数锁红行），复原后的 diff 与 §1 逐字相同，`git status --porcelain -- timeline.py` 只为本卡一处 ` M`。

### 3.2 集合断言（真·跨语言集合相等）的落点与红/绿

`test_autopilot_timeline.py` 只有**计数锁**，没有集合断言；本 key 的「集合相等断言」在 TS 侧
`packages/coding-agent/test/suite/autopilot-event-parity.test.ts:76-87`：`pyOnly == [] ∧ tsOnly == []`（`EVENT_TYPES` 集合相等，非计数）。
该断言读的正是本卡修改的 `timeline.EVENT_TYPES`（`PY_DUMP_EVENT_TYPES` 真跑子进程 dump，`:46-53`）。按该断言语义做对照演算（Python 侧真实 dump，TS 侧 = 23 基线镜像，T-05 未落地）：

```text
WITH names   -> pyOnly ['contract-refused', 'gate-reminder', 'l3-aborted'] tsOnly []
DROP one name-> pyOnly ['gate-reminder', 'l3-aborted'] tsOnly []
assertion reads table = True
```

- 本卡前：`pyOnly == []` ⇒ 断言绿；
- 本卡后（T-05 未落地）：`pyOnly == [3 名]` ⇒ 断言**红**，这是 P-021 预期的「两侧必须同批」窗口；
- `DROP one name` ⇒ 差异集非空 ⇒ 断言**必然转红**，证明断言真读该表。

T-05 在 `status-model.ts:988+` 逐字镜像这 3 名后，`pyOnly`/`tsOnly` 同时归零，断言转绿；**该绿由 T-05 回执承载，本卡不跑 TS/vitest**（卡硬规则 3）。

## 4. 契约核对

| 契约 | 结果 |
|---|---|
| 逐字名字，无改写/前缀 | ✅ `:102-104` 三行逐字 |
| 只加名：不发射、不消费 | ✅ diff 仅 `EVENT_TYPES`；无新 append/query 调用点 |
| 不动 `Timeline.append` "Never raises" | ✅ `Timeline.append`/`_write_line`/异常语义零改动 |
| 不动 Python 计数测试 | ✅ `test_autopilot_timeline.py` 未改（红行交 T-14） |
| 追加处注释引 pre-admission 先例 | ✅ 注释点名既有 pre-admitted 段与 T-01/T-07/T-10/T-05 分工 |
| TS 半边 = T-05 | ✅ 未触碰任何 TS 文件；集合相等断言 T-05 落地后全绿 |

## 5. 硬规则遵守

- 只改 `packages/multi-workers/autopilot/timeline.py`；未 commit；未 `git add -A/.`；未 `git checkout .`（仅对**本卡独占文件**做过一次 `git checkout -- <timeline.py>` 以复原对照变异，随后重放本卡 diff）；未 stash/reset/clean。
- 未碰任何队列文件（`_workers.parallel`/`_workers.acked`），未 kill 进程。
- 未跑 `npm run build` / `npm test` / 全量 vitest；Python 仅 `python -X utf8 -m pytest test_autopilot_timeline.py -q -p no:randomly`。
- 未改 `config.py`（T-02）/`gates.py`（T-04）/`conductor.py`（T-01/T-07/T-10）/**任何 TS 文件**（T-05）。同目录 `config.py`/`dispatch.py` 的 ` M` 非本会话产物（开工前已存在）。
- 临时对照脚本 `workers/mwg-t03-event-names/_mutate.py` 与备份 `timeline.py.mutated.bak` 已删除。

## 6. 交接

- T-14：把 `test_autopilot_timeline.py:48` 计数锁 23 → **26**（红行、唯一可见红）。同函数内派生锁需同步（当前被 `:48` 失败遮住、修复后即暴露）：`:53` `len(events) == 23` → `26`，`:54` `list(range(1, 24))` → `range(1, 27)`。
- T-05：`status-model.ts` `EVENT_TYPES` 逐字镜像 3 名，方可闭合 `autopilot-event-parity.test.ts` 集合相等。
