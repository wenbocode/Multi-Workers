# T-W04 — G4：树骤降/断链采样与告警（AC-010/011）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令（见「写入禁止面」）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 「Worker 崩溃不影响其他 Worker」的另一面：**共享树被破坏时必须有人/机器发现**。2026-10-09 事故约 5.5 分钟无人报警，本任务补上机器发现。
- **设计契约**: `design.md` §6（AC-010/011）与决策 D-7：采样挂在常驻服务主循环里，`git ls-files -d` 为判据，按路径面排除 dist，阈值 `max(20, 1% * 2756) = 28`；断链判据用 Python 侧 `lstat`/`isjunction`。
- **已实测的坑（必须规避，出处见 `spec.md` §6）**:
  - 坑 6：`git ls-files` 只读索引，磁盘删除后计数不变（实测 6→6、5001→5001）⇒ 必须用 `git ls-files -d`（或 `git status --porcelain` 的 ` D` 行）；切分支会让总数变（180↔200）而 `-d` 不变。
  - 坑 7：本仓 **2,239** 个 tracked 在 `*/dist/`（占 `packages/` 58.5%），`npm run clean --workspaces` 会让"总 D"飙到 ~2,170 ⇒ 判据必须排除 dist（照 `mw.py` 既有惯例）。
  - 坑 8：`existsSync`/`stat` 看不见断裂 junction（断链 `exists=False`），必须 `lstat`/`os.path.lexists`/`isjunction`；判目标完好要判 `<target>` 而非 `<link>`。
  - 坑 9：`os.readlink` 对 junction 带 `\\?\` 前缀，Windows 短名（`WENBROZ~1`）与长名混用 ⇒ 剥前缀 + `normcase`+`normpath` 后做前缀比较。
  - 坑 15：采样命令可能刷新 `.git/index` ⇒ 统一 `--no-optional-locks`（或 `GIT_OPTIONAL_LOCKS=0`），不与其它 git 写操作并跑。
- **宿主挂点（已实测，行号会漂移 ⇒ grep 符号）**: `packages/multi-workers/launcher.py:1706`（`_poll_once`，内部 `launcher.py:1717` 有 `mw_common.launcher_beat_write` 的 beat 调用）、`launcher.py:50`（`DEFAULT_POLL_INTERVAL = 5`，故"每 6 poll = 30 s"）、主循环 `launcher.py:1905`（`time.sleep(poll_interval)`）、`launcher.py:2045`（`--poll-interval` 参数）；告警形状与日志落盘照同文件既有 helper。
- 相关 spec 验收：AC-010（骤降触发 / 正常波动不触发）、AC-011（断链触发 / 完好链不触发）。

## 要求

1. 新建 `tree_watch.py`：纯逻辑（判据 + 状态文件 + 输出结构），**不得**把采样逻辑内联进 `launcher.py`（`launcher.py` 只加薄挂点）。
2. 采样节奏：默认每 **6 poll**（30 s，`DEFAULT_POLL_INTERVAL=5`）一次；`PI_TREE_WATCH_SEC` 可覆盖；`0` = 关闭（不得触发任何 git 子进程）。
3. 判据一（骤降）：`git --no-optional-locks ls-files -d`，按路径面**排除 `*/dist/`** 后计数；`>= 28` ⇒ 告警（阈值由代码计算为 `max(20, 1% * non_dist_tracked)`，两次采样间要能复算；把实测的非 dist tracked 基数写进报告）。
4. 判据二（断链）：扫描默认域内的 junction，目标不存在 ⇒ 告警并给路径；完好链与真目录**不**触发。
5. 状态文件放 `.mw/`（沿用既有命名习惯），写入走 tmp + 原子替换；异常（git 失败/权限）不得让 `_poll_once` 崩溃 —— 采样失败只记日志并跳过本轮。
6. 告警与 trace 走 `launcher.py` 既有通道（形状与既有告警一致，便于 `mw status`/日志消费）。
7. 测试 `test_tree_watch.py`（`pytest`）：骤降触发、单文件编辑不触发、`git rm -r`/`npm run clean` 类变更不触发（dist 排除生效）、断链触发、完好链不触发、`PI_TREE_WATCH_SEC=0` 完全关闭。夹具全部在 `%TEMP%`。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W04-tree-watch-20261013.md`：`## 结论`、`## 证据`（阈值推导 + 实测基数、六类测试实际输出、挂点 before→after `file:line`）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 阈值: <值> | 非dist基数: <值>`。

## 写入允许面

- `packages/multi-workers/tree_watch.py`（新建）
- `packages/multi-workers/launcher.py`（只加挂点 + 告警/日志调用，**不动**派发/监督逻辑）
- `packages/multi-workers/test_tree_watch.py`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W04-tree-watch-20261013.md`（新建）

## 写入禁止面

- `packages/multi-workers/mw.py`、`worktree_cmd.py`、`worktree_registry.py`（T-W02 写域）、`mw_common.py`（T-W03 写域）、`scripts/**`、任何 `packages/coding-agent/**`。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove`、`rm`、`npm install`；禁止触碰真树 `node_modules` 下的 junction。
- 禁止内联 import；不引入新第三方依赖。

## 验收命令

```
cd packages/multi-workers
python -m pytest test_tree_watch.py -q
```

外加一条**只读**真实采样冒烟（不得触发任何写操作）：

```
python -c "import tree_watch,sys; print(tree_watch.sample_once(sys.argv[1]) if hasattr(tree_watch,'sample_once') else 'n/a')" H:/git/Multi-Workers
```

（若最终接口名不同，按实际接口写一条只读调用，并在报告中给出命令原文与输出。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
