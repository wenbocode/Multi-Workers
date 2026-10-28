# T-W16 — AC-015 悬空链裂缝 + AC-016 多标记（D-17/D-18）

- key: mw-worktree-junction-guard（W-16）
- 角色: coding worker
- 日期: 2026-10-14
- 写面: `packages/multi-workers/worktree_registry.py`、`packages/multi-workers/mw_common.py`、`packages/multi-workers/test_worktree_doctor.py`、`packages/multi-workers/test_doctor_activation.py`、本文件

## 结论

1. **D-17（AC-015 裂缝）已补**：`worktree_registry.read_registry` 的存在性门由 `path.exists()` 改为 `os.path.lexists(str(path))`（只改这一处门；缺文件仍返回 `[]`）。悬空链接形态经测试自证（`lexists is True` 且 `exists() is False`，否则 skip）：`read_registry` 抛 `WorktreeRegistryError`，`worktree_doctor` 折入 `registry_error`，doctor 产出 `worktree-registry-error:` issue + `worktree_links: REGISTRY-ERROR <path>: …` 行 + rc=1。**悬空链 = 可见**。缺文件与健康注册表两条反向对照零新增行、rc 不变。
2. **D-18（AC-016 多标记）已补**：判据由单标记升级为 `ACTIVATION_MARKERS = ("reparse-point", "user_bash")`。逐标记独立判定（`entry["markers"]`），`has_marker` = 全部存在，`entry["missing_markers"]` 记录缺失项；任一缺失 ⇒ `guard-not-deployed` issue 与 `activation: MARKER-ABSENT '<marker>' …` 行都**指明缺失的标记名**。不可读/缺文件/编码异常照旧 fail-open-to-verdict（`None` ≠ 已激活，文本 `UNVERIFIABLE`），读取失败不 raise；适用域 scope gate 不变。
3. **文案修正（W-15 §3 C9）已做**：`entry["role"]` 区分两份副本。`packages/multi-workers/dist/extensions/agent-team-loop.js` = 构建产物/暂存（pi 不直接加载）⇒ 缺失含义「未 `mw build`」，修复提示 `mw build`；`<pi agent dir>/extensions/agent-team-loop.js` = pi 实际加载位 ⇒ 「未 `--install`」，修复提示 `mw build --install`。
4. **测试**：8 文件套件 **179 passed**（基线 172 + 本卡 7：`test_worktree_doctor.py` +2、`test_doctor_activation.py` +5），0 回归；两份目标测试文件 **32 passed**；`import mw_common` cycle-ok。
5. **真实仓只读复跑**：`activation` 命中 **0**、无 `REGISTRY-ERROR` 行、rc = **1**（既有 serve `STALE CODE`）。未部署、未放宽判据。

## 证据

### 1. 悬空链形态自证（免管理员，Windows junction）

探针（`%TEMP%\wjg-w16-probe.py`，已删除）：

```
base: C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w16-probe-tvwsp35w
mklink rc: 0 out: 为 ...\.mw\worktree-registry.json <<===>> ...\nonexistent-target 创建的联接
lexists: True
exists: False
isjunction: True
read_text raised: PermissionError [Errno 13] Permission denied: '...\.mw\worktree-registry.json'
after rmdir lexists: False
cleaned: True
```

命令形态：`cmd /c mklink /J "<夹具>/.mw/worktree-registry.json" "<夹具>/nonexistent-target"`。`read_text` 抛的是 `PermissionError`（`OSError` 子类），被 `read_registry` 的 `except (OSError, ValueError)` 捕获 ⇒ `WorktreeRegistryError`。

### 2. 悬空链用例输出

```
$ python -m pytest test_worktree_doctor.py::test_dangling_registry_link_is_visible \
    test_worktree_doctor.py::test_registry_missing_and_healthy_are_silent_reverse_controls -v
test_worktree_doctor.py::test_dangling_registry_link_is_visible PASSED   [ 50%]
test_worktree_doctor.py::test_registry_missing_and_healthy_are_silent_reverse_controls PASSED [100%]
============================== 2 passed in 2.33s ==============================
```

用例断言：`os.path.lexists(registry) is True`；若 `registry.exists()` 则 `pytest.skip`（不假绿）；否则断言 `exists() is False`；`pytest.raises(WorktreeRegistryError)`；`section["registry_error"]` 非空；issue 唯一且含路径；`worktree_links: REGISTRY-ERROR` 行含路径；`mw.cmd_doctor` 返回 1。反向对照：缺文件与 `{"version":1,"entries":[]}` 健康表均零 `REGISTRY-ERROR` 行、零 `worktree_links` 行、rc 相等（=0，夹具内有 live PID）。

### 3. 四类标记用例 + 角色文案用例输出

```
$ python -m pytest test_doctor_activation.py::test_only_user_bash_missing_names_that_marker \
    test_doctor_activation.py::test_only_reparse_point_missing_names_that_marker \
    test_doctor_activation.py::test_both_markers_missing_names_both \
    test_doctor_activation.py::test_both_markers_present_reverse_control_rc_unchanged \
    test_doctor_activation.py::test_dist_and_installed_copies_carry_role_specific_wording -v
test_doctor_activation.py::test_only_user_bash_missing_names_that_marker PASSED   [ 20%]
test_doctor_activation.py::test_only_reparse_point_missing_names_that_marker PASSED [ 40%]
test_doctor_activation.py::test_both_markers_missing_names_both PASSED   [ 60%]
test_doctor_activation.py::test_both_markers_present_reverse_control_rc_unchanged PASSED [ 80%]
test_doctor_activation.py::test_dist_and_installed_copies_carry_role_specific_wording PASSED [100%]
============================== 5 passed in 3.83s ==============================
```

- 仅缺 `user_bash`（留 `reparse-point`）：issue 含 `'user_bash'`、不含 `'reparse-point'`；文本 `activation: MARKER-ABSENT 'user_bash' <path> - run 'mw build --install'`，无 `MARKER-ABSENT 'reparse-point'`。
- 仅缺 `reparse-point`（留 `user_bash`）：对称成立。
- 两个都缺：issue 同时含两个名字；文本两行 `MARKER-ABSENT '<m>' …`。
- 两个都在：`has_marker is True`、`missing_markers == []`、`markers` 全 `True`、零 activation issue、rc=0、文本无 `activation:`。
- 角色文案：dist 路径 issue 含 `build artifact` / `pi does not load this copy` / `run 'mw build'`，且**不含** `run 'mw build --install'`；installed 路径含 `installed bundle pi actually loads` / `run 'mw build --install'`。

### 4. 真实仓 doctor 前后对照与 rc

**改前**（我的会话首跑，代码未改）：

```
summary: ISSUES: STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers ... serve_pid=49540 ... digest=c1efb81468f5 fix: /mw restart
serve code: STALE CODE (content changed): ... expected commit=604a95b5... actual commit=55be3d96... version=0.83.0 digest=c1efb81468f5 fix: /mw restart
RC=1
（无 activation 行、无 REGISTRY-ERROR 行）
```

**改后**（`python mw.py doctor --project H:/git/Multi-Workers`，只读）：

```
summary: ISSUES: STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers schema=1/1 serve_pid=49540 started=2026-10-13T14:18:19Z code newest mtime=2026-10-14T00:36:51Z (base=2026-10-13T13:47:36Z) expected commit=604a95b5... actual commit=55be3d96... drift_age=3m dirty_at_start=49/8 version=0.83.0 digest=3b52b308f289 fix: /mw restart
serve code: STALE CODE (content changed): ... digest=3b52b308f289 fix: /mw restart
RC=1
（activation 命中 0、无 REGISTRY-ERROR 行）
```

差异说明：`code newest mtime` 与 digest 变化来自本卡对 `mw_common.py` 的编辑（属于 serve 代码树），仍判 `STALE CODE`；`expected/actual commit` 未变。rc 保持 1，未为变绿放宽判据。

**真实 bundle 直接探测**（`%TEMP%\wjg-w16-markers.py`，已删除）：

```
H:\git\Multi-Workers\packages\multi-workers\dist\extensions\agent-team-loop.js
  size = 1136749
  'reparse-point' count = 1
  'user_bash' count = 2
  lexists = True exists = True
C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js
  size = 1136749
  'reparse-point' count = 1
  'user_bash' count = 2
  lexists = True exists = True
scan ok = True missing = []
  entry dist      ... has_marker = True missing_markers = []
  entry installed ... has_marker = True missing_markers = []
```

⇒ 真实仓 activation 命中 **0**（两份 bundle 两标记齐全）。

### 5. pytest 输出

```
$ cd packages/multi-workers
$ python -m pytest test_doctor_activation.py test_worktree_doctor.py -q
32 passed in 21.82s

$ python -m pytest test_doctor_activation.py test_worktree_doctor.py test_worktree_cmd.py \
    test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py \
    test_serve_doctor.py -q
179 passed in 77.24s (0:01:17)

$ python -c "import mw_common; print('cycle-ok')"
cycle-ok
```

基线（改前同命令）= **172 passed**；改后 179 = 172 + 7 新增（2 + 5），无回归。

### 6. 夹具路径与清理

- `test_worktree_doctor.py`：`tempfile.mkdtemp(prefix="wjg-w03-")`（`%TEMP%`），`_cleanup` 先逐条剥 reparse point 再 `rmtree`。跑后 `wjg-w03-*` 目录数 **0**。
- `test_doctor_activation.py`：pytest `tmp_path`（`%TEMP%` 下 per-test 目录，pytest 自动清理）。
- 探针脚本 `%TEMP%\wjg-w16-{probe,markers}.py` 与 doctor 输出 `%TEMP%\wjg-w16-doctor-after.txt` 均已删除。
- `%TEMP%` 中现存 `wjg-tw-*`（188 个）来自冻结的 `test_tree_watch.py`（`prefix="wjg-tw-"`），非本卡夹具，未触碰。

## 改动历史

本人改动清单（`git status --porcelain`）：

```
 M packages/multi-workers/mw_common.py
?? packages/multi-workers/test_doctor_activation.py
?? packages/multi-workers/test_worktree_doctor.py
?? packages/multi-workers/worktree_registry.py
```

说明：`worktree_registry.py` / 两份测试文件在 HEAD 未跟踪（W-03/W-13 的未提交产物），故无法用 `git diff` 隔离本卡改动；下表为相对本卡开工时的工作区状态（before→after）。

| file:line (after) | before | after |
|---|---|---|
| `worktree_registry.py:88-92` | `if not path.exists():` （before 第 86 行） | `if not os.path.lexists(str(path)):` + 4 行 D-17 注释 |
| `mw_common.py:2750` | `ACTIVATION_MARKER = "reparse-point"` | `ACTIVATION_MARKERS: tuple[str, ...] = ("reparse-point", "user_bash")` + 重写注释 |
| `mw_common.py:2780-2798` | 不存在 | 新增 `_activation_copy_role()`（dist/installed 角色）+ `_activation_fix()` |
| `mw_common.py:2800-2856` | `_activation_scan` 单标记：`entry = {path, exists, has_marker, error}`；`entry["has_marker"] = ACTIVATION_MARKER in text`；返回 `"marker"` | 多标记：`role` + `markers` + `missing_markers`；逐标记判定；返回 `"markers"` 列表 |
| `mw_common.py:2858-2872` | `_doctor_activation` not-applicable 返回 `"marker": ACTIVATION_MARKER` | 返回 `"markers": list(ACTIVATION_MARKERS)` |
| `mw_common.py:3933-3968` | activation issue：`detail = f"capability marker '{activation.get('marker')}' absent"`；固定 `mw build --install` | 缺失标记名单 `capability marker(s) absent: '…'`；按 `role` 区分 `dist`（`mw build`）/`installed`（`mw build --install`）含义与提示 |
| `mw_common.py:4245-4268` | 文本：`detail = f"MARKER-ABSENT '{activation.get('marker')}'"`；固定 `mw build --install` | 逐缺失标记一行 `MARKER-ABSENT '<marker>'`；按 `role` 取 `mw build` / `mw build --install` |
| `test_worktree_doctor.py:545-622` | 无 | 新增 `test_dangling_registry_link_is_visible`、`test_registry_missing_and_healthy_are_silent_reverse_controls` |
| `test_doctor_activation.py`（395 行，重写 15 例） | 10 例单标记 | 10 例适配多标记 + 新增 `test_only_user_bash_missing_names_that_marker` / `test_only_reparse_point_missing_names_that_marker` / `test_both_markers_missing_names_both` / `test_both_markers_present_reverse_control_rc_unchanged` / `test_dist_and_installed_copies_carry_role_specific_wording` |
| `.agenticdoc/.../evidence/T-W16-ac015-crack-ac016-markers-20261013.md` | 不存在 | 本文件 |

未触碰：`worktree_doctor.py`（`registry_error` 折叠位无需改动，既有 `except WorktreeRegistryError` 直接覆盖悬空链）、`mw.py`、`test_worktree_cmd.py`/`test_worktree_e2e.py`/`test_tree_watch*.py`/`test_serve_doctor.py`/`test_doctor_gates.py`、`packages/coding-agent/**`、`scripts/**`、任何 `.ts`/`.mjs`。未跑 `mw build` / `mw start|stop`。

## 残留与未验证

1. **真实 bundle 体积中途变化**：开工首测 1,136,103 B → 复跑 1,136,749 B，两份 bundle mtime 均为 2026-10-14 08:38:48，`git status` 显示 `M packages/multi-workers/dist/extensions/agent-team-loop.js`。这是同轮其它 worker（W-17 改 guard）触发的重建，非本卡改动；两标记计数不变（`reparse-point`=1、`user_bash`=2），本卡判据不受影响。
2. **角色判定的路径启发式**：`_activation_copy_role` 以路径含 `multi-workers/dist/extensions` 判 `dist`，否则判 `installed`。scope gate 当前只对拥有 `packages/coding-agent/src/extensions/agent-team-loop` 的检出生效，该检出下两份路径形态固定，故实际覆盖；若未来重命名 dist 相对路径，会退化为 installed 文案。
3. **POSIX 未实跑**：悬空链接在 POSIX 由 `_make_link` 的 `os.symlink` 分支构造、逻辑同为 `lexists` 真 / `exists` 假，但本机为 Windows，未在 POSIX 上运行该用例。
4. **未部署**：只读复跑，未验证「把某一份 bundle 标记删掉后真实仓 doctor 变红」的端到端（那需要动真实 bundle，属禁部署面）；标记灵敏度由 `%TEMP%` 夹具的 `_inject` 用例覆盖。
5. `%TEMP%` 现存 188 个 `wjg-tw-*` 目录来自冻结的 `test_tree_watch.py`，非本卡；未清理（不在写面，且可能是其它会话的夹具）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w16-ac015-crack-markers/task.md`、`tasks/T-W16-ac015-crack-ac016-markers.md`
- 定稿决策：`spec.md` §7（D-17/D-18）、`design.md` 附录「2026-10-14 对抗性审计派生补充」
- 审计来源：`evidence/delta-adversarial-audit-20261013.md` §2（`path.exists()` 唯一静默形态）、§3 C4②（删 `user_bash` 挂钩假绿）、C9（dist 与全局副本角色区分）
- 实现坐标：`worktree_registry.py`（`read_registry`）、`mw_common.py`（activation 段、`_doctor_issues`、`format_doctor_text`）、`worktree_doctor.py`（`_registry_domain`）
- 既有测试：`test_doctor_activation.py`（W-13 10 例）、`test_worktree_doctor.py`（AC-015 用例）

TESTS: 179/179 | 悬空链: 可见 | 标记: reparse-point+user_bash | 真实仓 activation 命中: 0 | CHECK: n/a(python)
