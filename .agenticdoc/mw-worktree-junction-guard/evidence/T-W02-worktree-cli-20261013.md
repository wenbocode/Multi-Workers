# T-W02 — G2：`mw worktree add|rm|list` 六步事务 + 注册表模块

- key: `mw-worktree-junction-guard` · worker: `wjg-w02-worktree-cli` · card: `tasks/T-W02-worktree-cli.md`
- 日期: 2026-10-13 · 环境: Windows 10.0.26100 / PowerShell 5.1 / Python 3.14.3 / git 2.53.0.windows.1
- 写面: `packages/multi-workers/{mw.py,worktree_cmd.py,worktree_registry.py,test_worktree_cmd.py}` + 本报告

## 结论

G2 已实现并自测通过（37/37）。`mw worktree` 二级子命令（add/rm/list）按 `design.md` §4.3 契约落地；`rm` 为同一进程内线性六步（枚举 → 三分类校验 → 只摘链 → 复核主树 → `git worktree remove --force` → 前后对照），任一步失败即 `ABORT at step N/6` + 明确打印「未降级继续」+ 非 0 退出 + 保留现场，无跳步开关、无补偿写、步 2 与步 3 之间零写入。摘链原语为 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符），非 Windows 拒绝。三分类 D-1 实现为纯函数 `classify_link_target`。注册表 `worktree_registry.py` 落 `.mw/worktree-registry.json`，`acquire_lock` + tmp + `os.replace` + 读回验证。`_npm_hydrate` 已从 `cmd_bootstrap` 步 2 抽出，install_cmd 向量逐字节不变（单测断言）。

一条实测修复（超出种子范围但在验收面内）：`%TEMP%` 使用 8.3 短名（`WENBOZ~1`），而 junction 的 `readlink` 可能存短名、`Path.resolve()` 给长名；`normcase` 不等价两者，最初导致真实 junction 被判成 `foreign`。已改为 `_norm` 内先剥 `\\?\` 再 `os.path.realpath` 规范化（spec §6 坑点 9），并加了回归用例。

## 证据

### 1. 六步与步序实测输出（`%TEMP%` 夹具，双层链：`B\node_modules -> A\node_modules`，`A\node_modules\@earendil-works\pi-ai -> A\packages\ai`）

成功路径（`remove_worktree(..., log=print)`，真实 `git worktree remove --force`）：

```
[mw worktree rm] step 1/6: enumerated 1 reparse point(s) under C:\Users\wenbozhou\...\B; main-tree @earendil-works snapshot: 1
[mw worktree rm] step 2/6: validated 1 link(s) (repo=1, worktree=0, foreign=0)
[mw worktree rm] step 3/6: unlinked 1 reparse point(s) (cmd /c rmdir, no /S)
[mw worktree rm] step 4/6: main-tree @earendil-works links unchanged (1)
[mw worktree rm] step 5/6: git worktree remove --force rc=0
[mw worktree rm] step 6/6: before/after main-tree @earendil-works links (before=1, after=1)
[mw worktree rm]   before: pi-ai (Junction) -> \\?\C:\Users\WENBOZ~1\...\A\packages\ai
[mw worktree rm]   after: pi-ai (Junction) -> \\?\C:\Users\WENBOZ~1\...\A\packages\ai
[mw worktree rm]   unlinked: ...\B\node_modules (Junction -> \\?\C:\Users\WENBOZ~1\...\A\node_modules, classification=repo)
[mw worktree rm] step 6/6: before=1 after=1 unlinked=1 registry_unregistered=0
rc = 0
```

- 主树零损伤（AC-005）：`A\packages\ai\f.txt` 内容仍为 `keep\n`；`A\node_modules\@earendil-works\pi-ai` junction 仍在；工作树 manifest（排除 `.git`，逐文件 sha256 + 链接目标）before==after。
- 步序由 `result["steps"]` 断言：`[1,2,3,4,5,6]` / `["enumerate","validate","unlink","recheck","remove","report"]`。
- 步 6 打印 before/after 链接表 + 已摘链条目（`_emit_link_table`）；同一内容也在 `--json` 的 `main_tree_before`/`main_tree_after`/`unlinked` 里。
- 步 2 先于步 3：`links[]` 在步 2 冻结并打上 `classification`；步 3 只消费同一份列表。

失败路径（步 2：一个 foreign 链 + 一个会让位的 repo 链）：

```
[mw worktree rm] step 1/6: enumerated 2 reparse point(s) under ...\C; main-tree @earendil-works snapshot: 1
[mw worktree rm] Error: link target outside both the repo and this worktree: ...\C\foreign -> ...\outside
[mw worktree rm] ABORT at step 2/6: 1 link(s) failed the fail-closed target check; zero link(s) unlinked
[mw worktree rm] 未降级继续 (no degraded continuation): scene preserved; git worktree remove NOT executed; every remaining link stays where it is
[mw worktree rm]   manual: cmd /c rmdir "...\C\node_modules" (never /S, never a trailing separator)
[mw worktree rm]   manual: cmd /c rmdir "...\C\foreign" (never /S, never a trailing separator)
rc = 1
abort_step = 2 unlinked = 0
```

零摘链：`result["unlinked"] == []`，两链 `os.path.isjunction` 仍为 True，`git` 记录器证明 `remove` 从未被调用。

其余中止路径（注入）单测覆盖：步 3 摘链失败（`abort_step=3`，`unlinked=[]`）、步 4 复核不等（`abort_step=4`，`git remove` 未调用、工作树保留、不补偿回写已摘链）、步 5 `git` rc≠0（`abort_step=5`，工作树保留）。

### 2. 三分类判定纯函数（D-1，供 W-05/W-06 对齐）

```python
def classify_link_target(
    target: object, *, repo_root: pathlib.Path, worktree_root: pathlib.Path
) -> str:
    """Purified D-1 classification of one link target.

    Order matters: the worktree subtree wins over the repo.
    Return values / meaning:
      "worktree"  target inside the to-be-deleted worktree subtree
                  (npm-ci self-link; harmless) -> unlink only
      "repo"      target inside repo_root but outside the worktree
                  (the incident shape)          -> unlink -> recheck -> remove
      "foreign"   anything else                 -> fail-closed, zero unlinks
    """
```

`_norm(path)`：剥 `\\?\` 前缀 → `os.path.realpath`（展开 8.3 短名并解析别名）→ `os.path.normcase` + `os.path.normpath`；`_is_within` 用 `norm == parent or norm.startswith(parent + os.sep)`。三分类三例的具名用例在 `test_worktree_cmd.py::TestClassification`（`repo` / `worktree` / `foreign` 各一，含 worktree 嵌套于 repo、worktree 在 repo 外、短名/长名与 junction 别名）。

### 3. `--json` 样例

`rm` 成功（字段：`action,target,repo_root,project,ok,abort_step,error,steps[{step,name,ok,detail}],links[{path,link_type,target,target_normalized,classification,unlinked}],unlinked,main_tree_before,main_tree_after,registry_unregistered]`）：

```json
{
  "action": "rm",
  "target": "C:\\Users\\wenbozhou\\...\\wjg-w02-evidence-...\\B",
  "repo_root": "C:\\Users\\wenbozhou\\...\\wjg-w02-evidence-...\\A",
  "ok": true,
  "abort_step": null,
  "error": null,
  "steps": [
    {"step": 1, "name": "enumerate", "ok": true, "detail": "enumerated 1 reparse point(s) ...; main-tree @earendil-works snapshot: 1 entry(ies)"},
    {"step": 2, "name": "validate", "ok": true, "detail": "validated 1 link(s): repo=1 worktree=0 foreign=0"},
    {"step": 3, "name": "unlink", "ok": true, "detail": "1 reparse point(s) unlinked (cmd /c rmdir, no /S, no trailing separator)"},
    {"step": 4, "name": "recheck", "ok": true, "detail": "main-tree @earendil-works links unchanged (1)"},
    {"step": 5, "name": "remove", "ok": true, "detail": "git worktree remove --force rc=0"},
    {"step": 6, "name": "report", "ok": true, "detail": "before=1 after=1 unlinked=1 registry_unregistered=0"}
  ],
  "links": [{"path": "...\\B\\node_modules", "link_type": "Junction",
             "target": "\\\\?\\C:\\Users\\WENBOZ~1\\...\\A\\node_modules",
             "target_normalized": "c:\\users\\wenbozhou\\...\\a\\node_modules",
             "classification": "repo", "unlinked": true}],
  "unlinked": ["<同上>"],
  "main_tree_before": [{"name": "pi-ai", "path": "...\\A\\node_modules\\@earendil-works\\pi-ai", "link_type": "Junction", "target": "\\\\?\\C:\\Users\\WENBOZ~1\\...\\A\\packages\\ai", "target_normalized": "...\\a\\packages\\ai"}],
  "main_tree_after":  ["<与 before 逐条相等>"],
  "registry_unregistered": []
}
```

`--json` 模式下人类进度走 stderr，stdout 保持单一可解析 JSON（单测断言）。

`list --json`（真仓只读，未执行 add/rm）：

```json
{
  "action": "list",
  "repo_root": "H:\\git\\Multi-Workers",
  "project": "H:\\git\\Multi-Workers",
  "registry_path": "H:\\git\\Multi-Workers\\.mw\\worktree-registry.json",
  "registry": [],
  "worktrees": [{"path": "H:/git/Multi-Workers", "head": "55be3d960bb8402a262fb3fcccdcc27fda3f2ed9",
                 "branch": "refs/heads/dev/AgentTeam", "detached": false, "bare": false, "prunable": false}],
  "count": 0, "worktree_count": 1, "ok": true, "error": null
}
```

### 4. 注册表文件样例（读写往返）

```json
{
  "version": 1,
  "entries": [
    {
      "link": "C:\\Temp\\wt\\node_modules",
      "target": "H:\\git\\Multi-Workers\\node_modules",
      "worktree": "C:\\Temp\\wt",
      "repo_root": "H:\\git\\Multi-Workers",
      "created_at": "2026-10-13T23:53:41+08:00",
      "created_by": "mw worktree add --link-deps (pid 1234, user wenbozhou)"
    }
  ]
}
```

### 5. 正向对照（夹具成立性，AC-012 语义）

`%TEMP%` 内直接执行 `git worktree remove --force <wt>`（不摘链）：

```
victim before: True
remove rc: 0
victim after: False      # A\packages\ai\f.txt 被穿透删除 —— 夹具确实复刻事故
repo node_modules exists: True
wt exists: False
```

单测 `test_positive_control_unsafe_remove_penetrates` 固化该判定；六步路径的反向对照见 §1（before==after，victim 存活）。

### 6. pytest 实际输出

```
$ python -m pytest test_worktree_cmd.py -q
.....................................                                    [100%]
37 passed in 14.95s
```

覆盖：分类 6 例（含短名/junction 别名回归）、注册表 7 例（往返/upsert/幂等/缺失空/坏文件 fail-closed/空字段拒绝/created_by）、`_npm_hydrate` 5 例（`ci` 向量 / `install` 向量 / 失败传播 / npm 缺失 / bootstrap 委托且无重复 `install_cmd`）、六步与中止 9 例、正向对照 1 例、add 4 例（dry-run 零落盘 / 默认 hydrate 不建链 / `--link-deps` 建链+登记+rm 注销 / 已存在路径拒绝）、CLI+JSON 5 例（list 字段 / rm 六步报告 / rm abort 报告 / parser 契约 / rm 无 `--force|--continue|--dry-run`）。

### 7. 真仓只读验收

```
$ python mw.py worktree --help        # rc=0，三个二级动作 + 无跳步开关
$ python mw.py worktree list --json   # rc=0，registry=[]，worktree_count=1（仅主树）
```

真仓状态：`git worktree list` 仅 `H:/git/Multi-Workers`；`.mw/worktree-registry.json` 不存在；`node_modules/@earendil-works/*` 9 条 junction 全部 `os.path.isjunction=True`（未触碰）。

## 改动历史

`git status --porcelain`（本人改动，均为写面允许项）：

```
 M packages/multi-workers/mw.py
?? packages/multi-workers/test_worktree_cmd.py
?? packages/multi-workers/worktree_cmd.py
?? packages/multi-workers/worktree_registry.py
?? .agenticdoc/mw-worktree-junction-guard/evidence/T-W02-worktree-cli-20261013.md
```

| 文件:行 | before | after |
|---|---|---|
| `packages/multi-workers/mw.py:37` | 无 | `import worktree_cmd` |
| `packages/multi-workers/mw.py:4939-4958` | 无（无 `_npm_hydrate`） | `_npm_hydrate(target_root)`：`[npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]` + `_run_stream(..., cwd=target_root)` |
| `packages/multi-workers/mw.py:5128` | `5105-5106`：`install_cmd = [...]` / `if not _run_stream(install_cmd, cwd=repo_root):` | `if not _npm_hydrate(repo_root):`（向量逐字节不变，单测断言） |
| `packages/multi-workers/mw.py:6271-6279` | 无 | `cmd_worktree(args)` 注入 `_repo_root/_git/_npm_hydrate` |
| `packages/multi-workers/mw.py:6564-6600` | 无 | `worktree` 一级 parser + add/rm/list 二级 parser（既有 `_parse_args` 内） |
| `packages/multi-workers/mw.py:6717` | 无 | dispatch `"worktree": cmd_worktree` |
| `packages/multi-workers/worktree_cmd.py`（新建，727 行） | 无 | 六步事务 + `classify_link_target` + add/list/JSON dispatch |
| `packages/multi-workers/worktree_registry.py`（新建，191 行） | 无 | `.mw/worktree-registry.json` 读写（锁 + tmp + `os.replace` + 读回） |
| `packages/multi-workers/test_worktree_cmd.py`（新建，685 行） | 无 | 37 例 pytest |

## 残留与未验证

1. **非 Windows 语义**：摘链原语在非 win32 直接 `WorktreeCommandError`（不静默降级）。若目标内**没有** reparse point，`rm` 不会调用原语，六步中的 1–2/4–6 步（含 POSIX 上不穿透 symlink 的 `git worktree remove`）仍会执行。即「有链才拒绝」，未做「非 Windows 一律拒绝 rm」的更宽行为——本次只坐实 Windows，非 Windows 未实测。
2. **`--link-deps` 建链目标**：固定为 `<path>/node_modules -> <repo_root>/node_modules`（设计 §8 待实现期定的项，取最贴近事故形态的一种）。逐包链/直接复制的变体未实现。
3. **`--ref` 语义**：`add` 一律 `git worktree add --detach <path> <ref>`（默认 `HEAD`），不创建分支；`--ref` 是 commit-ish 而非新分支名。设计契约未规定分支语义。
4. **并发 rm 竞态**：注册表写由 `.mw/worktree-registry.lock` 串行（复用既有锁协议），但两个并发 `rm` 同一主树快照的竞态未实测（设计 §7 第 6 条已声明未坐实）。
5. **`os.path.realpath` 依赖**：`_norm` 的短名展开依赖目标路径存在（`realpath` 对不存在的目标只做规范化）。断裂 junction 的目标为不存在的仓库内路径时，若其前缀含 8.3 短名，规范化可能不完整——本次未构造该组合。
6. **`mw doctor` worktree_links 段**：属 T-W03 写面（`mw_common.py`），本任务未实现；本模块只提供注册表 API 供其消费。
7. **G1 侧 block 文本**：属 T-W01/W-05 写域；本任务的契约（`mw worktree rm "<path>"`）已按 `design.md` §4.3 逐字落地，可直接被引用。
8. **`_npm_hydrate` 在 `add` 默认路径会真实执行 npm**：单测全部用 `--dry-run`/`--link-deps`/注入，未真跑 `npm ci`（真树与夹具均禁止）；`add` 的非 dry-run 默认路径未在夹具实测（需数 GB 下载）。

## 上下文来源

- `.agenticdoc/mw-worktree-junction-guard/design.md` §4.1 落点 / §4.2 六步 / §4.3 CLI 契约 / §4.4 三分类 D-1 / §5.1 注册表 / §6 D-6 `_npm_hydrate` / §8 写面。
- `.agenticdoc/mw-worktree-junction-guard/spec.md` AC-004..008、§5 可复用资产、§6 坑点 3/4/5/8/9/10/11/12/14/16。
- `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-registry-and-worktree-cli-20261013.md` §0 行号漂移 / §1.4 `_toolchain_run` 范式 / §1.5 六步分工 / §1.6 控制流草案 / §2 注册表与锁 / §4 npm 引导 / §5.1-5.3 原语实测。
- `packages/multi-workers/mw.py`：`_toolchain_run`（snapshot→action→recheck→退出码）、`_git`、`_repo_root`、`_run_stream`、`cmd_bootstrap` 步 2 的 `install_cmd`、`_parse_args`/dispatch 先例、`_target_set` 错误约定。
- `packages/multi-workers/mw_common.py`：`acquire_lock`/`release_lock`（`O_CREAT|O_EXCL`）、`_write_workers_file`（tmp + replace）。
- `packages/multi-workers/mw.py:4195` `_rmtree_robust`（测试清理，Windows 只读文件）。
- 事故面一手证据：`mw-workspace-incident-probe/evidence/{in1-junction-incident-20261009.md,incidents-timeline-20261009.md}`（穿透/不穿透对照）。

TESTS: 37/37 | 夹具位置: %TEMP%\pytest-of-wenbozhou\pytest-*（临时夹具 `%TEMP%\wjg-w02-evidence-*` 已在证据采集后清理）
