# T-W03 · G3 `mw doctor` worktree_links 段（AC-009）— 证据报告

- 日期：2026-10-13
- key：`mw-worktree-junction-guard`
- 任务卡：`tasks/T-W03-worktree-doctor.md`（`card_sha256: ea4cc5b14b2616fb19a8a843832e4bedb28f73e43a42e596b5922bf5eeed076b`）
- 决策：D-2（判定域）+ D-10（判据修正：仓内顶层链 = 减 `package-lock.json` 的 `"link": true` 期望集）

## 结论

按 D-2/D-10 落地三域判定，挂载点照 design §5.2：新检查在 `mw_common.doctor_report`
内部装配为 `report["worktree_links"]`，`_doctor_issues` 逐条产出 issue（可翻转退出码），
`format_doctor_text` 仅在非空时打印。注册表 = `worktree_registry.read_registry`（单一事实源），
链接枚举 + `\\?\` 剥离 = `tree_watch.scan_links` / `resolve_link_target`（未重写）。
循环导入用 `doctor_report` 内**唯一一处**函数内 import 打破，`python -c "import mw_common"`
通过。反向对照成立：本仓 14 期望 == 14 磁盘 ⇒ `worktree_links.count == 0`、文本零行、
`summary.issues` 无 worktree 项；本仓 `mw doctor` 退出码与改动前一致（rc=1，来自
无关的 `serve code` STALE CODE），不由本段翻转。正向对照（%TEMP% 夹具）证明 issue 与文本行
确实翻 rc：干净夹具 rc=0、加一条未登记仓内链后 rc=1。

发现并修复了一个真实路径陷阱（已实测）：`mw.py` 会 `resolve()` `--project`（8.3 短名
`WENBOZ~1` → 长名 `wenbozhou`），而 junction 的 `os.readlink` 目标保持创建时拼写；本机
`%TEMP%` 就是短名 ⇒ 不做 realpath 归一化时，`%TEMP%` 下的所有链都会被误判为"目标在仓外"。
`worktree_doctor._is_within` 已对两侧做 `os.path.realpath` 归一化，并加了回归测试。

## 证据

### 1. 本仓 `mw doctor`（只读反向对照）

改动前基线（`python mw.py doctor --project H:/git/Multi-Workers`）：

```
RC=1
...
summary: ISSUES: STALE CODE (content changed): ... drift_age=6m ... fix: /mw restart
```

改动后（同命令）：

```
RC=1
worktree_links: 0 lines
```

`summary.issues` 仍只有无关的 `serve code` STALE CODE；`worktree_links` 段：

```
[repo] worktree_links count = 0
[repo] domains = {'registry': 0, 'repo_local': 14, 'scan_roots': 0}
[repo] scanned = {'roots': [], 'budget': 200000, 'entries_visited': 0, 'truncated': False,
                  'elapsed_ms': 6.521, 'expected_links': 14, 'repo_local_links': 14,
                  'registry_error': None}
[repo] expected-set size = 14 | disk links = 14
```

磁盘 14 条（`tree_watch.scan_links`，全部 `Junction`，目标全部落在 `H:\git\Multi-Workers` 内）：
9 条 `node_modules\@earendil-works\*` + 5 条 `node_modules\pi-extension-*`；
lockfile 期望集 14 条逐条同名同目标 ⇒ 减法后 `count == 0`。

> 验收命令原文 `python mw.py doctor` 在 CLI 上缺 `--project`（argparse 必填，rc=2），
> 实际执行 `python mw.py doctor --project H:/git/Multi-Workers`；未改 `mw doctor` 的
> 参数必填语义。

### 2. 域 (a) 注册表域（默认开）实测

```
[domain-a] link+worktree present -> count = 0
[domain-a] worktree gone -> count = 1 | leftover = [{"path": "...\\links\\node_modules",
    "target": "...\\A\\node_modules", "kind": "registry-leftover", "worktree": "...\\wt"}]
[domain-a] link gone -> stale_entries = [{"path": "...\\links\\node_modules",
    "target": "...\\A\\node_modules", "kind": "registry-stale", "worktree": "...\\wt"}]
```

### 3. 域 (b) 仓内顶层链域（默认开，减期望集）实测

```
[domain-b] raw readlink = '\\\\?\\C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\wjg-w03-evidence-tul78iyu\\A\\packages\\ai'
[domain-b] expected=1 on-disk=2 -> count = 1 | leftover = [{"path": "...\\A\\node_modules\\leftover-pkg",
    "target": "...\\A\\packages\\ai", "kind": "repo-local-leftover", "worktree": null}]
[domain-b] expected=2 on-disk=2 -> count = 0
```

`raw readlink` 带 `\\?\` 前缀，条目 `target` 已剥前缀且被判为仓内（前缀回归）；
把链名写进 lockfile 的 `"link": true` 后同一链静默（期望集减法生效）。

### 4. 域 (c) 全域猎捕（`--worktree-scan-roots`，默认关）实测

```
[domain-c] default off -> count = 0
[domain-c] scan roots on -> count = 1 | domains = {'registry': 0, 'repo_local': 2, 'scan_roots': 2}
    | scanned = {'roots': ['...\\temp-root'], 'entries_visited': 2, 'truncated': False, 'budget': 200000}
[domain-c] leftover = [{"path": "...\\temp-root\\mwvg-t5\\node_modules",
    "target": "...\\A\\node_modules", "kind": "scan-root-leftover", "worktree": "...\\temp-root\\mwvg-t5"}]
```

`<root>\<wt>\node_modules` → 夹具真仓为 live landmine；不给开关时不报；指向仓外的
`other-wt\node_modules` 不报（`entries_visited=2`，只有真仓那条命中）。

### 5. CLI 级正/反向对照（issue + 文本行 + rc）

```
[cli] clean fixture rc = 0
[cli] clean fixture worktree_links line? False
[cli] leftover fixture rc = 1
[cli] worktree_links text lines:
    worktree_links: LEFTOVER (repo-local-leftover) ...\A\node_modules\leftover-pkg -> ...\A\packages\ai
[cli] worktree issues: ["worktree-leftover (repo-local-leftover): ... - a junction pointing into this repo survived its worktree; clear it with 'mw worktree rm <worktree>' before it is reused or removed (AC-009)"]
```

### 6. 夹具路径与清理命令

- 域 a/b/c 证据夹具根：`C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w03-evidence-tul78iyu`（已清理）
- CLI 对照夹具根：`C:\Users\WENBOZ~1\AppData\Local\Temp\wjg-w03-cli-83m5lvwc`（已清理）
- pytest 夹具：`tempfile.mkdtemp(prefix="wjg-w03-")` / pytest `tmp_path`（pytest 自清理）
- 清理形态：每个 junction `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）→ `shutil.rmtree`
  跳过 reparse point / `rmdir /S /Q <root>`；脚本内 `finally` 保证执行。
- 运行后复查 `%TEMP%\wjg-w03*`、`%TEMP%\wjg-rp*`、`%TEMP%\wjg-dbg*`：全部为空。
- 链目标全部在夹具内，真树只执行 `scandir`/`lstat`/`readlink`/`mw doctor`（只读）；
  未跑任何 `git checkout|reset|clean|stash|worktree add|remove|prune`、`rm`、`npm install`。

### 7. pytest 实际输出

```
$ cd packages/multi-workers && python -m pytest test_worktree_doctor.py -q
............                                                             [100%]
12 passed in 9.61s

$ python -m pytest test_doctor_gates.py test_serve_doctor.py -q
.................................................................        [100%]
65 passed in 35.56s

$ python -c "import mw_common; print('cycle-ok')"
cycle-ok

$ python mw.py doctor --project H:/git/Multi-Workers
rc=1 | worktree_links: 0 lines
```

`test_worktree_doctor.py` 12 例覆盖卡片六类：域 (a) 两态、域 (b) 减法两态、
`\\?\` 前缀回归、短名/长名别名回归、域 (c) 开关开/关 + 预算截断、干净夹具
`count==0`/零行/rc 两向相等、循环回归、本仓只读反向对照。

补充回归（所有直接调 `doctor_report` / `format_doctor_text` 的既有文件，非卡片必跑）：

```
$ python -m pytest test_doctor_autopilot.py test_mwds_t08_doctor_blocked.py test_dispatch_models.py \
    test_in3_queue_replay.py test_autopilot_pending_review.py test_worker_queue_python_integrity.py -q
137 passed in 36.46s
```

## 改动历史（本人本次会话）

`git status --porcelain`（本人改动）：

```
 M packages/multi-workers/mw.py
 M packages/multi-workers/mw_common.py
?? packages/multi-workers/test_worktree_doctor.py
?? packages/multi-workers/worktree_doctor.py
```

> `mw.py` 在我改动前已被 W-02 做过 `worktree` 子命令改动（同一工作区未提交），
> 其中只有下面两处是本人本次新增；其余 `mw.py` diff 不属于本任务。
> `mw_common.py` 改动前为 clean，diff 全部为本人本次三处。

| 文件 | 位置（before → after） | 改动 |
|---|---|---|
| `packages/multi-workers/worktree_doctor.py` | 新文件 | `build_section(project_root, scan_roots=None, entry_budget=200000)`；`_registry_domain` / `_repo_local_domain` / `_scan_roots_domain`；`expected_link_keys`；`_real_key`/`_is_within`。复用 `tree_watch.scan_links`/`resolve_link_target`/`_is_reparse_point` 与 `worktree_registry.read_registry`/`registry_path` |
| `packages/multi-workers/mw_common.py` | `_doctor_issues`（原 `:3525`，现 issue 块 `:3745-3762`） | `leftover` / `stale_entries` 非空 ⇒ 每条一个 `issues.append(...)`，含 `kind` + `path` + `target` |
| `packages/multi-workers/mw_common.py` | `doctor_report` 签名（原 `:3748`，现 `:3766-3772`） | 新增 `worktree_scan_roots: list[str] \| None = None` |
| `packages/multi-workers/mw_common.py` | `doctor_report` 内部（现 `:3804-3812`） | 唯一一处函数内 `import worktree_doctor`（注释说明循环）+ 装配 `report["worktree_links"]` |
| `packages/multi-workers/mw_common.py` | `format_doctor_text`（原 `:3790`，现 `:3946-3957`） | 仅 `count` 非空时逐条打印 `worktree_links:` 行 |
| `packages/multi-workers/mw.py` | `cmd_doctor`（现 `:599-611`） | 解析 `--worktree-scan-roots`（`dir1;dir2`）并透传；`getattr(..., None)` 兼容既有测试的 `Namespace` |
| `packages/multi-workers/mw.py` | doctor 子命令注册（现 `:6328-6332`） | 新增 `--worktree-scan-roots`（默认 `None`/关）；未触碰其它 doctor 行为与退出码逻辑 |
| `packages/multi-workers/test_worktree_doctor.py` | 新文件 | 12 例 pytest，夹具全部 `%TEMP%` |
| `.agenticdoc/mw-worktree-junction-guard/evidence/T-W03-worktree-doctor-20261013.md` | 新文件 | 本报告 |

未写：`worktree_cmd.py` / `worktree_registry.py` / `test_worktree_cmd.py` / `tree_watch.py` /
`launcher.py` / `test_tree_watch.py` / `scripts/**` / `packages/coding-agent/**`。

## 残留与未验证

1. **注册表损坏只进 JSON 不翻 rc**：`worktree_registry.read_registry` 对坏文件 fail-closed
   抛 `WorktreeRegistryError`，`build_section` 捕获后写入 `scanned.registry_error`，但按卡片
   写面限制，`_doctor_issues` 只对 `leftover`/`stale_entries` 报 issue ⇒ 损坏注册表不会让
   `mw doctor` 变红（只在 `--json` 可见）。这是卡片允许面的取舍，已在代码注释标注；如需
   fail-closed 翻转需扩写面（未做）。
2. 域 (c) 只覆盖 `<root>\<wt>\node_modules` depth-1 形态；更深的链、`<root>\<wt>` 本身为
   reparse point 的形态不覆盖。entry 预算 200,000（常数），未在 20 万级真实 `%TEMP%` 上做
   端到端计时（仅 2 entry 夹具 + 常数参数化）。
3. 域 (b) 期望集只认 `package-lock.json` 顶层 `packages[*].link === true`；pnpm/yarn
   形态、嵌套 lockfile、`node_modules` 下非 workspace 的合法仓内链会被报为 leftover
   （保守方向，未做白名单扩展）。
4. 短名/长名归一化用 `os.path.realpath`；非 Windows 平台未实测该分支（junction 语义本身
   也是 Windows-only，相关测试已 skip）。
5. 单文件阈值/输出文案未与其它段做逐字冻结（新段本来只为"有残留才出现"，干净路径零行）。

## 上下文来源

- `packages/multi-workers/worktree_registry.py`（W-02，注册表 API 与字段）
- `packages/multi-workers/tree_watch.py:178/215`（`resolve_link_target` / `scan_links`）
- `packages/multi-workers/mw_common.py`：`doctor_report` / `_doctor_issues` / `format_doctor_text`
- `packages/multi-workers/mw.py`：`cmd_doctor` + doctor 子命令注册
- `.agenticdoc/mw-worktree-junction-guard/design.md` §5.2/§5.3/§9、`spec.md` AC-009（D-2/D-10）
- `.agenticdoc/mw-worktree-junction-guard/tasks/T-W03-worktree-doctor.md`
- 本机实测：`node_modules` 14 条 junction；`package-lock.json` `"link": true` 14 条；
  `os.readlink` 返回 `\\?\` 前缀 + 8.3 短名（`WENBOZ~1`）

TESTS: 77/77 | 本仓 worktree_links: 0 | rc: 1
