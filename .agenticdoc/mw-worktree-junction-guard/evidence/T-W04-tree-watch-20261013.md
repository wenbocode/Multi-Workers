# T-W04 · G4 树骤降/断链采样与告警 — 证据报告

- key: `mw-worktree-junction-guard` · task: `T-W04-tree-watch` · 角色: coding (W-04 / G4)
- 日期: 2026-10-13 · 环境: Windows `10.0.26100` / PowerShell 5.1 / `git 2.53.0.windows.1` / `Python 3.14.3` / `pytest 9.0.2`
- 目标锚点: `.agenticdoc/goal.md`（共享树被破坏必须机器可发现）

## 结论

1. 新增 `packages/multi-workers/tree_watch.py`：纯逻辑实现两个判据 —— ① 骤降（`git --no-optional-locks ls-files -d`，按路径面排除 `*/dist/`，`delta >= max(20, round(1% * non_dist_tracked))` 且 `deleted_non_dist >= 20`）；② 断链（默认域 `node_modules/*` + `@scope/*` 的 junction，目标不存在即告警）。状态文件 `.mw/tree-watch.json` 走 tmp + `os.replace`。
2. `launcher.py` 只加薄挂点：`_poll_once` 尾部 7th 参数 `tree_watcher`（默认 `None`，既有 6 参数直调不受影响），每 poll 调 `TreeWatch.tick()`（默认 6 poll = 30 s，`PI_TREE_WATCH_SEC` 覆盖、`0` = 关闭且零 git 子进程），告警经既有 stderr 通道 `[launcher] [TREE-WATCH] …` 进 `.mw/launcher.log`；采样异常被吸收，`_poll_once` 永不因采样崩溃。
3. 验收命令 `python -m pytest test_tree_watch.py -q`：**19 passed**（六类用例全过）。只读真实采样冒烟：本仓 `tracked_non_dist=2822`、`deleted_non_dist=0`、`threshold=28`、14 条 junction 全部完好、**未写任何状态文件**。
4. 挂点唯一已知回归面：`test_launcher.py` 有 1 条**既有**失败（缺历史语料文件，与本次改动无关，见「残留与未验证」）；其余 99 条通过。

## 证据

### 1. 阈值推导与实测基数

判据一阈值由代码每次采样复算：

```
threshold = max(20, round_half_up(0.01 * non_dist_tracked))
```

实测（只读，命令见 §4）：

| 量 | 实测值 | 来源 |
|---|---|---|
| `tracked_total`（索引） | 5,061 | `git --no-optional-locks ls-files -z` |
| `*/dist/` tracked | 2,239 | 路径面含 `dist` 目录分量（与 design §1/§6.1 的 2,239 一致） |
| `tracked_non_dist` | 2,822 | 5,061 - 2,239 |
| `deleted_total` | 0 | `git --no-optional-locks ls-files -d -z` |
| `deleted_non_dist` | 0 | 同上，排除 dist 分量 |
| **threshold** | **28** | `max(20, floor(0.01*2822 + 0.5)) = max(20, floor(28.72)) = 28` |
| junction 清单 | 14（9 `@earendil-works/*` + 5 `pi-extension-*`），断链 0 | 默认域扫描 |

**基数漂移说明**：design 期基数 `2,756 -> 27.56 -> 28`；实施期实测 `2,822`（+66 non-dist tracked，多会话并发写入所致）。采用 **round-half-up** 而非 `ceil`，因为 `ceil(28.22)=29` 会违背卡片明确的「`>= 28` ⇒ 告警」，而 round-half-up 同时复现 design 的 `2756 -> 28` 与卡片的 `2822 -> 28`（`collapse_threshold` docstring 与 `test_collapse_threshold_formula` 固定该口径）。

**路径面口径**：`is_dist_path()` 按 `parts[:-1]` 判 `dist` 目录分量，与 `mw.py` 既有惯例同构（`_UPDATE_ENV_SKIP_DIRS` 常量 `mw.py:5273`，过滤点 `_runtime_code_files` 内 `any(part in _UPDATE_ENV_SKIP_DIRS for part in rel.parts[:-1])`）。反向对照：`dist/x.js` 也计为 dist 分量（排除），`distfile.js` 不计。

### 2. 六类测试实际输出

`cd packages/multi-workers; python -m pytest test_tree_watch.py -q` → `19 passed`。`-v` 逐条：

```
test_tree_watch.py::test_collapse_threshold_formula PASSED
test_tree_watch.py::test_dist_path_surface PASSED
test_tree_watch.py::test_collapse_triggers PASSED
test_tree_watch.py::test_single_file_edit_does_not_trigger PASSED
test_tree_watch.py::test_git_rm_does_not_trigger PASSED
test_tree_watch.py::test_dist_clean_does_not_trigger PASSED
test_tree_watch.py::test_collapse_requires_two_samples PASSED
test_tree_watch.py::test_sample_once_is_read_only PASSED
test_tree_watch.py::test_good_junction_does_not_trigger PASSED
test_tree_watch.py::test_broken_junction_triggers PASSED
test_tree_watch.py::test_real_directory_and_inventory_change PASSED
test_tree_watch.py::test_watch_disabled_by_env_zero_no_git_child PASSED
test_tree_watch.py::test_default_cadence_is_six_polls PASSED
test_tree_watch.py::test_sample_failure_logs_and_skips PASSED
test_tree_watch.py::test_poll_once_emits_tree_watch_alarms PASSED
test_tree_watch.py::test_poll_once_without_watcher_still_works PASSED
test_tree_watch.py::test_poll_once_survives_watcher_error PASSED
test_tree_watch.py::test_pi_tree_watch_sec_overrides_interval PASSED
test_tree_watch.py::test_state_roundtrip PASSED
============================= 19 passed in 12.85s =============================
```

卡片六类 ↔ 用例：

| # | 卡片类别 | 用例 | 断言要点 |
|---|---|---|---|
| 1 | 骤降触发 | `test_collapse_triggers` | 600 tracked 删 300：`deleted_non_dist=300 >= 20`、`delta=300 >= threshold=20` ⇒ `collapse=True`；索引总数仍 600（证明判据是 `-d` 不是总数） |
| 2 | 单文件编辑不触发 | `test_single_file_edit_does_not_trigger` | 改内容后 `deleted_non_dist=0`、`alarms=[]` |
| 3 | `git rm -r`/`npm run clean` 不触发（dist 排除） | `test_git_rm_does_not_trigger` + `test_dist_clean_does_not_trigger` | `git rm -r` 后 `-d=0`；只删 80 个 `dist` 文件时 `deleted_total=80` 但 `deleted_non_dist=0` |
| 4 | 断链触发 | `test_broken_junction_triggers` | `exists(link)=False`、`lexists=True`、`isjunction=True` ⇒ `broken_links=[link]` 且告警含路径 |
| 5 | 完好链不触发 | `test_good_junction_does_not_trigger`（+`test_real_directory_and_inventory_change`） | `target_exists=True`、`broken_links=[]`、`alarms=[]`；真目录不入清单 |
| 6 | `PI_TREE_WATCH_SEC=0` 完全关闭 | `test_watch_disabled_by_env_zero_no_git_child` | `interval_polls=0`、`enabled=False`；`subprocess.run` 被替换为抛错函数后 tick 20 次仍无事 ⇒ 零 git 子进程 |

额外覆盖：阈值公式固定值、`dist` 路径面、无基线（首样本）不告警、`sample_once` 只读、断链+真目录+链清单迁移、失败只记日志跳轮、默认 6 poll 节奏、poll 挂点告警/异常/6 参数兼容、`PI_TREE_WATCH_SEC` 秒→poll 换算、状态文件往返与坏文件降级。

### 3. 挂点 before→after（`file:line`，行号会漂移 ⇒ 以符号为准）

| 挂点 | before（HEAD `55be3d960`） | after（工作区） |
|---|---|---|
| 模块导入 | `launcher.py:37-38`（`import mw_common` / `from autopilot …`） | `launcher.py:37-39`，`import tree_watch` 落在 **:38** |
| `_poll_once` 定义 | `launcher.py:1706-1713`（6 形参） | `launcher.py:1707-1715`，`tree_watcher: tree_watch.TreeWatch | None = None` 落在 **:1714** |
| 采样挂点 | 无 | `launcher.py:1721-1729`（紧接 beat `:1719` 之后；`tree_watch.emit_alarms(tree_watcher.tick())` 在 **:1727**） |
| `run()` 建采样器 | 无 | `launcher.py:1886`（`tree_watcher = tree_watch.TreeWatch(project_dir, poll_interval)`） |
| 主循环调用 | `launcher.py:1905`（6 实参一行） | `launcher.py:1915-1918`（7 实参，`max_workers, tree_watcher,` 在 **:1917**） |

`launcher.py` 改动仅此 5 处，未动派发/监督/回收逻辑（`git diff` 全量见「改动历史」）。

### 4. 只读真实采样冒烟

命令原文（卡片给定接口；`sample_once` 即实际接口）：

```
cd packages/multi-workers
python -c "import tree_watch,sys; print(tree_watch.sample_once(sys.argv[1]) if hasattr(tree_watch,'sample_once') else 'n/a')" H:/git/Multi-Workers
```

该命令返回完整的单行 sample dict（含 14 条 junction 明细）；便于阅读的等价只读调用与**逐字输出**：

```
> python -c "import tree_watch,sys; s=tree_watch.sample_once(sys.argv[1]); print('tracked_total=%d tracked_non_dist=%d deleted_non_dist=%d threshold=%d links=%d broken=%d' % (s['tracked_total'], s['tracked_non_dist'], s['deleted_non_dist'], s['threshold'], len(s['links']), sum(1 for l in s['links'] if not l['target_exists'])))" H:/git/Multi-Workers
tracked_total=5061 tracked_non_dist=2822 deleted_non_dist=0 threshold=28 links=14 broken=0
```

完整 dict 的顶层字段（同一条命令）：`ts`/`iso`/`root`/`tracked_total=5061`/`tracked_non_dist=2822`/`deleted_total=0`/`deleted_non_dist=0`/`deleted_paths=[]`/`threshold=28`/`links`(14 条，每条 `path`+`link_type=Junction`+`target`+`target_key`+`target_exists=True`)。

只读性证明：冒烟命令之后 `Test-Path H:/git/Multi-Workers/.mw/tree-watch.json` = **False**（`sample_once` 不写状态）；测试 `test_sample_once_is_read_only` 同样断言。

### 5. 既有通道 / 告警形状

- 告警：`[launcher] [TREE-WATCH] collapse: deleted_non_dist=… delta=… threshold=… tracked_non_dist=… links=… paths=…` 与 `[launcher] [TREE-WATCH] broken-link: <path> -> <target> (junction target missing)` 写到 stderr，`mw serve` 捕获进 `.mw/launcher.log`（与 `[ENVELOPE-SKEW]` 同形状）。
- 落盘：`.mw/tree-watch.json`（`{version, ts, iso, tracked_*, deleted_*, deleted_paths[<=50], threshold, delta, links[], events[], alarms[]}`），tmp + `os.replace`。
- 挂点集成实测（`test_poll_once_emits_tree_watch_alarms`）：`launcher._poll_once(repo, …, 1, _FakeWatch())` 打印 `[launcher] [TREE-WATCH] collapse: delta=300`；`_BoomWatch` 抛错时仅打印 `tree watch error (continuing)`，poll 正常完成。

## 改动历史

本人本次会话改动（`git status --porcelain`）：

```
 M packages/multi-workers/launcher.py
?? packages/multi-workers/test_tree_watch.py
?? packages/multi-workers/tree_watch.py
```

- **新增** `packages/multi-workers/tree_watch.py`（478 行）：判据、junction 扫描、状态文件、`TreeWatch` 驱动、`emit_alarms`。
- **修改** `packages/multi-workers/launcher.py`（+1 导入、`_poll_once` +1 形参 +7 行挂点、`run()` +2 行采样器、主循环调用改多行）：仅挂点，见 §3 表。
- **新增** `packages/multi-workers/test_tree_watch.py`（382 行，19 用例，夹具全在 `%TEMP%\wjg-tw-*`）。
- **新增** 本报告。

未触碰：`mw.py` / `worktree_cmd.py` / `worktree_registry.py` / `mw_common.py` / `scripts/**` / `packages/coding-agent/**`。未运行任何破坏性 git/文件命令；未触碰真树 `node_modules` 下的 junction（真实采样只做 `lstat`/`readlink`/只读 git）。

## 残留与未验证

1. **既有无关失败**：`python -m pytest test_launcher.py -q` = `1 failed, 99 passed`。失败项 `TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites` 断言 `.agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md` 存在；该路径**不存在且无 git 历史**（`.agenticdoc/mw-dispatch-reliability/workers/` 目录不存在），非本次改动引入，属既有语料缺失。
2. **真实断链报告未端到端验证**：断链告警只在 `%TEMP%` 夹具验证；未在真树制造断链（禁止触碰真 `node_modules` junction），也未跑一次真实 `mw serve` 观察 launcher.log。
3. **链清单迁移**：design §6.2 判据 2（上一样本存在的链消失/换目标 ⇒ 事件）已实现并单测，但真实首次采样无基线、当前 14 条链无迁移，真实场景（如 `npm install` reify）的误报面未实测。
4. **换算口径**：`PI_TREE_WATCH_SEC` 为秒、按 `poll_interval` 换算 poll 数（`ceil`）；默认不设 = 6 poll。未验证 `--poll-interval` 非 5 s 的运行时行为（换算函数已单测）。
5. **doctor 消费**：design §6.1 提到「同窗口 link delta ⇒ 升级为 doctor issue」，该升级挂在 `mw_common`（T-W03 写域），不在本卡写面内；本卡只落 stderr 告警 + 状态文件。
6. `--no-optional-locks` 只保证采样不刷新 `.git/index`；未做「采样与其它 git 写操作不并跑」的运行时互斥（design §6.1/坑 15 只要求采样侧统一加锁规避）。

## 上下文来源

- `.agenticdoc/mw-worktree-junction-guard/workers/wjg-w04-tree-watch/task.md`（卡）与 `tasks/T-W04-tree-watch.md`（种子卡）。
- `.agenticdoc/mw-worktree-junction-guard/design.md` §6（G4 AC-010/011 判据、6 poll 节奏、状态文件、告警形状）、§5.3（判定域）、§7（未坐实项）。
- `.agenticdoc/mw-worktree-junction-guard/spec.md` §2 AC-010/011、§5（可复用资产）、§6 坑 6/7/8/9/15/16。
- 宿主挂点：`packages/multi-workers/launcher.py`（`_poll_once` :1707、beat :1719、`DEFAULT_POLL_INTERVAL` :51、主循环 `time.sleep` :1922、告警形状 `_emit_envelope_skew_alarms` :1278）。
- 路径面惯例先例：`packages/multi-workers/mw.py:5273`（`_UPDATE_ENV_SKIP_DIRS`）与 `_runtime_code_files` 的 `parts[:-1]` 过滤。
- 实测方法：`git --no-optional-locks ls-files [-d] -z`、`os.path.isjunction`/`os.readlink`、`cmd /c mklink /J`（仅夹具）。

TESTS: 19/19 | 阈值: 28 | 非dist基数: 2822
