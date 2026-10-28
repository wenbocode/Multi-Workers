# T-W09 · design §6.1 动作 (3)：骤降 + 同窗口链清单 delta 升级为 doctor issue — 证据报告

- key: `mw-worktree-junction-guard` · task: `T-W09-tree-watch-doctor` · 角色: coding (W-09 / F-02)
- 日期: 2026-10-13 · 环境: Windows `10.0.26100` / PowerShell 5.1 / `Python 3.14.3` / `pytest 9.0.2`
- 目标锚点: `.agenticdoc/goal.md` —— INV-4「同类事故可被机器发现」

## 结论

1. **补上唯一未实现的设计动作**：`design.md:295`（§6.1 AC-010 动作 (3)）「同窗口 `link_inventory` 也有 delta ⇒ 升级为 issue，`mw doctor` rc=1」现已落地。此前 G4 的告警只进 `.mw/launcher.log`，不看日志、只跑 `mw doctor` 的人看不到；现在会进 `summary.issues` 并翻转 rc。
2. **采样侧（`tree_watch.py`）**：`evaluate` 的 `collapse` 事件新增 `link_delta: {"removed", "changed", "added"}` 字段（并补 `ts`，即该样本的 `sample["ts"]`）。计数来自**同一趟** `prev_links`/`current_links` 比较——就是既有 inventory-migration 事件（`link-removed`/`link-retargeted`）用的那一趟，没有第二套清单比较。字段经 `write_state` 原样落盘到 `<root>/.mw/tree-watch.json` 的 `events[]`。
3. **消费侧（`mw_common._doctor_issues`）**：新增常量 `TREE_WATCH_ISSUE_WINDOW_SEC = 3600`；在既有 `worktree_links` 块之后追加消费点——读 `<project>/.mw/tree-watch.json`（project 由相邻 `worktree_links.registry_path` 反推，`<project>/.mw/...`）。**新鲜**（`0 <= now-ts <= 3600`）且 `kind == "collapse"` 且同窗口链 delta 非零 ⇒ `issues.append("tree-watch-collapse: ...")`（文本含 `ts` / `deleted_non_dist` / `delta` / `removed/changed/added`）。缺失 / 损坏 / 类型异常一律**静默跳过、绝不 raise**（fail-open-to-verdict）；过期事件不升级但仍在状态文件里可回溯。既有 issue 项顺序、条数不变，新项只追加在末尾。
4. **验收全绿**：`python -m pytest test_tree_watch_doctor.py -q` ⇒ **23 passed**；`python -m pytest test_tree_watch.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_doctor_gates.py test_serve_doctor.py -q` ⇒ **138 passed**；`python -c "import mw_common; print('cycle-ok')"` ⇒ `cycle-ok`；本仓 `python mw.py doctor --project H:/git/Multi-Workers` ⇒ 仓库 `.mw/tree-watch.json` 不存在 ⇒ **零 `tree-watch-collapse` 行**，rc 只由既有 `STALE CODE` issue 驱动（改动前后一致）。
5. 写入面严格落在卡片允许的 4 个文件内；`launcher.py` / `worktree_*.py` / `mw.py` / 冻结测试零改动。

## 证据

### 1. 窗口常量取值与理由

```python
# mw_common.py:3525-3532
TREE_WATCH_ISSUE_WINDOW_SEC = 3600
```

- **取值 3600 s（1 h）**。理由：
  - 状态文件 `<root>/.mw/tree-watch.json` 每次采样（默认 30 s，`PI_TREE_WATCH_SEC` 可覆盖）**整体重写**（tmp + `os.replace`），所以 `events[]` 只承载**最近一次采样**的事件——它本身就是「新鲜」的同义词。1 h 是对「launcher 停过一段时间 / 用户隔一阵才跑 doctor」的宽容带，而不是判据本身。
  - 反例面：若**不设窗口**，一个已修好的历史 collapse 会让之后每一次 `mw doctor` 永远 rc=1——这是设计没有要求的新误报面。过期事件**不**从状态文件删除，仍在 `events[]` 里可回溯，符合 design §6.1「事件落盘（自清后仍可回溯）」。
  - 边界：`age = now - ts`；`age < 0`（时钟回拨 / 未来戳）不当作新鲜证据，跳过。
  - 该常量可被测试直接引用（`test_stale_collapse_with_link_delta_does_not_upgrade` 用 `WINDOW_SEC ± 60` 构造正反两向）。

### 2. 事件字段与状态文件样例

`tree_watch.evaluate` 的 `collapse` 事件（`write_state` 落盘后原样读出）：

```json
{
  "kind": "collapse",
  "ts": 1791910600.5241401,
  "deleted_non_dist": 300,
  "delta": 300,
  "threshold": 20,
  "tracked_non_dist": 400,
  "paths": ["a"],
  "link_delta": {"removed": 1, "changed": 0, "added": 0}
}
```

`link_delta` 由 `evaluate` 里那一趟 `prev_links`/`current_links` 比较产出：`removed` = 上样本有、本样本无；`changed` = `target_key` 变化；`added` = 本样本有、上样本无。首样本（无 baseline）全 0——「对空基线谈 added」不是迁移。

### 3. 四类升级/不升级用例实测输出

下列输出由一次性脚本（`%TEMP%\wjg-w09-evidence-*`，跑完 `shutil.rmtree` 清理，脚本已删除）打印，直接调用 `mw_common._doctor_issues`：

```
WINDOW_SEC: 3600

[CASE 1] fresh collapse + link delta -> ISSUES
["tree-watch-collapse: tracked-file collapse (ts=1791910598.5154197, deleted_non_dist=300, delta=300) with a same-window junction-inventory change (removed/changed/added=1/0/0) - the AC-010 incident fingerprint (teardown + reify); inspect C:\\...\\fresh-with-delta\\.mw\\tree-watch.json and clear leftovers with 'mw worktree rm'"]

[CASE 2a] fresh collapse + zero link delta -> ISSUES
[]
[CASE 2b] fresh collapse + absent link_delta -> ISSUES
[]

[CASE 3] stale collapse + link delta -> ISSUES
[]

[CASE 4a] no state file -> ISSUES
[]
[CASE 4b] payload='{not json' -> ISSUES
[]
[CASE 4b] payload='{"events": "nope"}' -> ISSUES
[]
[CASE 4b] payload='{"events": [{"kind": "collapse", "ts": 1.0, "link_delta": "nope"}]}' -> ISSUES
[]

[CASE 5] pre-existing issue + tree-watch issue -> ISSUES
['mw service not running (workers will not be dispatched)', "tree-watch-collapse: tracked-file collapse (ts=..., deleted_non_dist=300, delta=300) with a same-window junction-inventory change (removed/changed/added=1/0/0) - ..."]

[STATE FILE SAMPLE] (collapse event verbatim):
{"kind": "collapse", "ts": 1791910600.5241401, "deleted_non_dist": 300, "delta": 300, "threshold": 20, "tracked_non_dist": 400, "paths": ["a"], "link_delta": {"removed": 1, "changed": 0, "added": 0}}
[CASE 6] written-by-evaluate -> ISSUES
["tree-watch-collapse: tracked-file collapse (ts=1791910600.5241401, deleted_non_dist=300, delta=300) with a same-window junction-inventory change (removed/changed/added=1/0/0) - ..."]
```

- CASE 1 / 5 / 6 = 升级（含 `evaluate`+`write_state` 全链路，证明字段确实落盘并被消费）。
- CASE 2a/2b = design 的「**且**」反向对照（只删文件不动链，或旧状态无字段）。
- CASE 3 = 过期反向对照（`ts = now - (3600+60)`）。
- CASE 4a/4b = 缺失 / 损坏 JSON / 类型异常 ⇒ 零 issue、不 raise。
- CASE 5 同时证明既有 issue 不被吞并、顺序为「先既有、后 tree-watch」。

`_doctor_issues` 原文（`mw_common.py:3773-3839`，新增段）：

```python
    # design §6.1 AC-010 action (3) (mw-worktree-junction-guard T-W09): the
    # resident watch already alarms on a tracked-file collapse, but the alarm
    # only reaches `.mw/launcher.log`. When the same sampling window also moved
    # the junction inventory (the incident fingerprint: teardown + reify), the
    # event is upgraded here so a `mw doctor` reader sees it and rc flips.
    # Fail-open-to-verdict, like the registry read above: a missing / corrupt /
    # wrong-typed state file or event is silently skipped, never raised - the
    # doctor must always produce a verdict. The project root is derived from
    # the adjacent `worktree_links.registry_path` (`<project>/.mw/...`); the
    # local `import tree_watch` follows the `import worktree_doctor` precedent
    # in `doctor_report` and keeps this consumption point self-contained.
    try:
        import tree_watch
    except ImportError:  # pragma: no cover - same-dir module, mirrors doctor_report
        tree_watch = None
    registry_path = worktree_links.get("registry_path")
    watched_project = (
        pathlib.Path(registry_path).parent.parent
        if isinstance(registry_path, str) and registry_path
        else None
    )
    state: dict = {}
    if tree_watch is not None and watched_project is not None:
        try:
            loaded = json.loads(
                tree_watch.state_path(watched_project).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            state = loaded
    raw_events = state.get("events")
    if tree_watch is not None and watched_project is not None and isinstance(raw_events, list):
        now = time.time()
        for event in raw_events:
            if not isinstance(event, dict) or event.get("kind") != "collapse":
                continue
            ts = event.get("ts")
            if ts is None:
                # Older events carry no per-event stamp; the state file's
                # top-level `ts` is that sample's sampling time.
                ts = state.get("ts")
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                continue
            age = now - float(ts)
            if age < 0 or age > TREE_WATCH_ISSUE_WINDOW_SEC:
                continue
            raw_delta = event.get("link_delta")
            if not isinstance(raw_delta, dict):
                continue
            counts = {
                key: raw_delta.get(key, 0) for key in ("removed", "changed", "added")
            }
            if any(isinstance(value, bool) or not isinstance(value, int) for value in counts.values()):
                continue
            if sum(counts.values()) <= 0:
                continue
            issues.append(
                f"tree-watch-collapse: tracked-file collapse (ts={ts}, "
                f"deleted_non_dist={event.get('deleted_non_dist')}, "
                f"delta={event.get('delta')}) with a same-window junction-inventory "
                f"change (removed/changed/added="
                f"{counts['removed']}/{counts['changed']}/{counts['added']}) - "
                "the AC-010 incident fingerprint (teardown + reify); inspect "
                f"{tree_watch.state_path(watched_project)} and clear leftovers with "
                "'mw worktree rm'"
            )
    return issues, suggestions
```

### 4. 本仓只读反向对照（`mw doctor`）

本仓当前**无** `.mw/tree-watch.json`（`ABSENT`）。命令与结果：

```
> python mw.py doctor --project H:/git/Multi-Workers
rc=1
> 输出中 "tree-watch-collapse" 命中数：0
> summary: ISSUES: STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers ...
```

- rc=1 由**既有** `STALE CODE` issue 驱动（serve 进程代码 mtime 落后），与本次改动无关。
- 无状态文件 ⇒ 新消费点直接 `state = {}` ⇒ 零新增 `tree-watch-collapse` 行，rc 与改动前一致。
- 注：`launcher_log` 一行里出现 `wjg-w09-tree-watch-doctor` 是本 worker 的**任务名**，不是新 issue。

### 5. 夹具路径与清理

| 测试文件 | 夹具 | 清理 |
|---|---|---|
| `test_tree_watch_doctor.py` | `tempfile.mkdtemp(prefix="wjg-w09-")` → `<base>/repo`（纯 JSON 状态文件，无 junction、无 git） | `shutil.rmtree(base, ignore_errors=True)`（fixture finally） |
| `test_tree_watch.py`（追加例） | 复用既有 `repo` fixture（`%TEMP%\wjg-tw-*`），`cmd /c mklink /J` 在 `<repo>/node_modules/pkg` 建 junction，目标 `<repo>/targets/pkg`（**夹具内**） | 链 `os.rmdir` 单删（无 `/S`，等价 `cmd /c rmdir <link>`）；根由既有 `_cleanup`（先摘 reparse point 再 `shutil.rmtree`） |
| 证据脚本（已删除） | `%TEMP%\wjg-w09-evidence-*` | `shutil.rmtree(base)`，输出末尾打印 `CLEANUP: rmtree(...) done` |

真树只读：未执行 `git worktree add\|remove\|prune`、未 `rm`、未触碰真树 `node_modules` 下的 junction、未 `npm install`/`ci`。

### 6. pytest 输出

```
> python -m pytest test_tree_watch_doctor.py -q
23 passed in 0.19s

> python -m pytest test_tree_watch.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_doctor_gates.py test_serve_doctor.py -q
........................................................................ [ 52%]
..................................................................       [100%]
138 passed in 97.12s (0:01:37)

> python -c "import mw_common; print('cycle-ok')"
cycle-ok
```

`test_tree_watch_doctor.py -v` 逐条（23 条 = 3 升级 + 6 反向对照，其中 `test_corrupt_or_wrong_typed_state_is_silent` 参数化展开为 13 条 + 2 共存/多条）：

```
test_fresh_collapse_with_link_delta_upgrades_and_flips_rc PASSED
test_changed_and_added_counts_upgrade_too PASSED
test_evaluate_persists_link_delta_through_write_state PASSED
test_collapse_without_link_delta_does_not_upgrade PASSED
test_stale_collapse_with_link_delta_does_not_upgrade PASSED
test_missing_state_file_is_silent PASSED
test_corrupt_or_wrong_typed_state_is_silent[... 10 params ...] PASSED
test_state_path_is_a_directory_is_silent PASSED
test_report_without_worktree_section_is_silent PASSED
test_coexists_with_existing_issues_preserves_order_and_count PASSED
test_two_fresh_collapse_events_yield_two_issues PASSED
```

`test_tree_watch.py` 追加例：`test_collapse_event_carries_same_window_link_delta PASSED`（正反两向：链被摘 ⇒ `{"removed":1,...}`；链完好 ⇒ 全 0）。

## 改动历史

本 session 只写卡片允许面；逐条 `file:line`（当前行号）before → after：

1. `packages/multi-workers/tree_watch.py`
   - `evaluate`：`delta` 计算之后（before 直接进入 `collapse = (...)`）新增链清单比较块 → `:279-318` 新增 `link_delta` 初始化 + `prev_links`/`current_links` 单趟比较（`removed`/`changed`/`added` 计数，产出 `inventory_events`/`inventory_alarms`）。
   - `collapse` 事件字典：before `{kind, deleted_non_dist, delta, threshold, tracked_non_dist, paths}` → after 增加 `"ts": sample.get("ts")`（`:330`）与 `"link_delta": dict(link_delta)`（`:334`）。
   - 原底部独立的 `prev_links` 比较块（before 直接向 `events`/`alarms` append）→ 删除，改由 `:361-362` 在断链事件之后 `events.extend(inventory_events)` / `alarms.extend(inventory_alarms)`（事件顺序不变：collapse → broken-link → dangling-symlink → inventory）。
2. `packages/multi-workers/mw_common.py`
   - `:3525-3532`（before：`_gates_text_alerted` 的 `return False` 与空行后直接 `def _doctor_issues`）→ 新增 `TREE_WATCH_ISSUE_WINDOW_SEC = 3600` 常量 + 理由注释。
   - `_doctor_issues`：既有 `worktree_links` stale-entry 循环之后、`return issues, suggestions` 之前（before 紧邻 return）→ `:3773-3839` 新增 tree-watch 消费点。既有 `worktree_links` 块与其它段未动。
3. `packages/multi-workers/test_tree_watch.py`
   - `:149-185`（before：`test_collapse_triggers` 断言结尾 `after["tracked_non_dist"] == 600` 后直接进入 `test_single_file_edit_does_not_trigger`）→ 追加 1 例 `test_collapse_event_carries_same_window_link_delta`。
4. `packages/multi-workers/test_tree_watch_doctor.py`（新建，294 行）。
5. `.agenticdoc/mw-worktree-junction-guard/evidence/T-W09-tree-watch-doctor-20261013.md`（新建，本文件）。

`git status --porcelain`（仅列本人本次涉及路径；仓内其它 `M`/`??` 为其它并行 session 的改动）：

```
 M packages/multi-workers/mw_common.py          (本人 T-W09 增量 + W-03 未提交增量共存)
?? packages/multi-workers/tree_watch.py         (W-04 新建，未提交；本人增量在内)
?? packages/multi-workers/test_tree_watch.py    (W-04 新建，未提交；本人增量在内)
?? packages/multi-workers/test_tree_watch_doctor.py  (本人新建)
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W09-tree-watch-doctor-20261013.md  (本人新建)
```

说明：`tree_watch.py` / `test_tree_watch.py` 尚未提交（W-04 产物），故 `git diff` 无输出；本人增量按上表行号定位。`mw_common.py` 的 `git diff` 同时含 W-03 的 `worktree_links`/`doctor_report`/`format_doctor_text` 未提交增量，本报告只认领第 2 条列出的 T-W09 两处。

## 残留与未验证

1. **消费点定位使用 `worktree_links.registry_path` 反推 project root**。这是为了把改动严格限制在 `_doctor_issues` 内（卡片写面约束），未改 `doctor_report` 加 `project_dir` 字段。生产路径 `doctor_report` 无条件构造 `worktree_links`，因此始终可用；但若未来有人用不含该字段的局部 `report` 直接调 `_doctor_issues`，tree-watch 消费会被静默跳过。已由 `test_report_without_worktree_section_is_silent` 固定该行为（fail-open），未验证「脱离 doctor_report 的其它调用方」——目前除 `doctor_report` 外无调用方（grep 只有定义与 `mw_common.py:3813`）。
2. **`PI_TREE_WATCH_SEC=0`（watch 关闭）** 时不会产生新状态文件；若历史状态文件仍在且事件新鲜，doctor 仍会升级。未新增「watch 关闭就不升级」逻辑（设计未要求，且关闭采样不等于事故没发生）。
3. **未做真机端到端**：未构造「launcher 实际采样写出新鲜 collapse + 链 delta」再跑 `mw doctor` 的整链（需要真树删除/恢复，违反只读约束）。本报告用 `evaluate` + `write_state`（CASE 6）覆盖同一落盘路径，`launcher.TreeWatch` 侧未改。
4. **`added` 计数没有独立升级用例**（只有 `changed`/`added` 混合的正向用例 `test_changed_and_added_counts_upgrade_too` 与 `evaluate` 单测覆盖）；`added` 只在有 baseline 时可能非零。
5. 未运行 `packages/coding-agent` TS 侧 `npm run check`（本任务为 Python 写面，未触碰 `.ts`/`.mjs`）。
6. 真树 `.mw/tree-watch.json` 当前不存在；若日后 launcher 写出一个**新鲜**的 collapse+delta 事件，`mw doctor` 会（按设计）变为 rc=1——这是预期行为，不是回归。

## 上下文来源

- 卡片：`.agenticdoc/mw-worktree-junction-guard/tasks/T-W09-tree-watch-doctor.md`、worker 卡 `.agenticdoc/mw-worktree-junction-guard/workers/wjg-w09-tree-watch-doctor/task.md`
- 设计：`.agenticdoc/mw-worktree-junction-guard/design.md:277-311`（§6.1 AC-010，动作 (3) 在 `:295`；事件语义段要求落盘「采样时刻」）
- 规格/计划：`.agenticdoc/mw-worktree-junction-guard/spec.md`（AC-010/AC-004）、`.agenticdoc/mw-worktree-junction-guard/plan.md`（W-03/W-04 写面边界）
- 既有原语：`packages/multi-workers/tree_watch.py`（`STATE_FILE_NAME`、`state_path`、`read_state`/`write_state`、`evaluate`）、`packages/multi-workers/mw_common.py:3525`（`_doctor_issues` 挂载点）、`packages/multi-workers/worktree_doctor.py:321`（`registry_path` 形状）
- 既有测试范式：`packages/multi-workers/test_tree_watch.py`、`packages/multi-workers/test_worktree_doctor.py`
- 独立 QG 发现 F-02：`.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`

TESTS: 138/138 | 升级用例: 5 | 反向对照: 7 | WINDOW_SEC: 3600
