# design 证据 — G2/G3 的 Python 侧接缝（卡 T-D2 / RQ-D2）

- **key**: mw-worktree-junction-guard（design 期）
- **口径**: HEAD = `cc9a46a1a`（2026-10-13 11:21 +0800），`dev/AgentTeam`；本机 Windows 10.0.26100.9168 / PowerShell 5.1 / python 3.14.3 / git 2.53.0.windows.1 / node v24.19.0
- **性质**: 只读取证 + `%TEMP%` 临时 fixture 实测。**零生产写入**（本文件是唯一写面）；对真树只做 `scandir`/`lstat`/`readlink`/`os.walk` 读操作，未创建、未删除、未改动任何真树 junction 或 `node_modules` 条目。
- **回答范围**: (1) `mw worktree rm|add` 落点与骨架（含六步分工与"中止不降级"控制流）；(2) 注册表位置/格式/读写 API + 可复用 O_CREAT|O_EXCL 锁原语；(3) `mw doctor` 新检查的挂载点与输出字段（AC-009）+ 实测成本；(4) `mw worktree add` 与既有 npm bootstrap 的关系。

---

## TL;DR

1. **行号必须重取**：卡（与 spec 期证据）引用的 `mw.py:5324-5659`、`mw_common.py:2957-2996`/`:2780`/`:2999` 是 **2026-10-09 的旧修订**。当前 HEAD 上分别漂移到 `mw.py:5603`（`_parse_args`）、`mw_common.py:3624-3664`（`doctor_report`）、`:3401`（`_doctor_issues`）、`:3666`（`format_doctor_text`）；`mw.py:624-628`（错误约定）漂移 +1 → `:625-629`。设计文档若照抄卡里的行号会指向错误代码。详见 §0。
2. **`mw worktree` 完全不存在**，TS 侧也没有任何 worktree 代码（`packages/**` grep `worktree` 仅 1 处注释命中）⇒ G2/G3 是纯新建；最贴近的可照抄先例是 `_RAG_ACTIONS`（`mw.py:2251`）+ `cmd_autopilot`（`:3557`）的二级动作分发，`_toolchain_run`（`:966`）的「前置快照 → 动作 → 后置快照 → drift 判定 → 打印对照 → `0 if ok else 1`」是六步第 4/6 步的现成范式。
3. **`mw worktree rm` 六步必须全部在同一个进程、同一次调用内完成**：第 2 步的判定必须先于任何摘链（plan-then-apply，范式 = `_cmd_rag_init:2212-2216`「先收集 refusal，一条都不写」），第 4 步的"主树链接未变"必须与第 3 步的摘链共享同一份 before 快照，第 5 步只认第 4 步的判定。中止用逐级 `return _abort(step, ...)` 表达，**不允许** `continue`/兜底 `finally` 里的补偿写入。
4. **注册表落点建议 `.mw/worktrees.json` + 锁 `.mw/worktrees.lock`**（`.gitignore:53` 整目录忽略，零额外 ignore 规则；`.mw/` 里已有 `dispatch.yml`/`toolchain.json`/`window-model` 等配置型文件，"`.mw/` 只放锁和 PID" 只是 `autopilot/config.py:4` 的自我描述、已被 `dispatch.yml` 打破）。写入 API 照 `autopilot/config.py:save_config`（校验 → tmp+replace）+ `mw_common.acquire_lock/release_lock`（`:2039`/`:2054`）。
5. **可复用锁原语已存在**：Python = `mw_common.acquire_lock`（`:2039-2052`，`O_CREAT|O_EXCL`，指数退避 20 次）+ `release_lock`（`:2054-2058`）；TS = `shared/file-lock.ts:12`（`fs.openSync(lockPath, "wx")`）。调用样例 = `mw_common.update_status:2110-2135`、`autopilot/dispatch.py:1153-1184`、`autopilot/conductor.py:137-183`（带 stale steal）。
6. **doctor 新检查要能"报出"（翻转 exit code），就必须挂在 `mw_common.doctor_report`（`:3624-3664`）内部，不能走 `mw.py cmd_doctor:522-526` 的注入段** —— 注入段是在 `_doctor_issues(report)`（`:3662`）**之后**执行的，永远无法产生 issue（这正是 conductor/rag 两段的"informational"语义来源）。这是本 RQ 最容易被做错的一点。
7. **成本已实测**：枚举 `node_modules/@earendil-works/*`（10 条）≈ **0.05 ms**（仅 `isjunction`）/ **0.95 ms**（含 `lstat`+`readlink`+仓库内判定，min of 30）；`node_modules/*` 顶层（229 条，实际覆盖全部 14 条 workspace 链）≈ **1.97 ms**；全仓（显式剪枝、不跟随 reparse point）43,412 条目 / 4,162 目录 ≈ **0.28 s**。**naive `os.walk` 会下钻 junction**（实测，即使 `followlinks=False`）⇒ 任何全仓扫描必须显式剪枝。
8. **AC-009 的阳性样本当前存在（活雷）**：`C:\Users\<user>\AppData\Local\Temp\mwvg-t5\node_modules` → `\\?\H:\git\Multi-Workers\node_modules`（junction 存在、目标存在、`listdir` 直穿真树 `node_modules`）。这就是事故前的链路形态；spec 期证据只核过 `mwvg-t5-probe`（已不存在），漏了 `mwvg-t5`。
9. **一个必须先决的设计矛盾**：AC-006「链接目标在仓库外 ⇒ 拒绝」若按字面实现，会把**在仓库外创建的 worktree 跑 `npm ci` 后产生的自指链**（`<wt>/node_modules/@earendil-works/x` → `<wt>/packages/x`，目标在仓库外但完全无害）一并拒掉；而 G1 又会拦截 `git worktree remove` ⇒ 形成"G1 拦 + G2 拒"的死锁。判定规则需要区分「目标指向本仓库真树」（= 危险但有解，摘链+复核）／「目标在本 worktree 子树内」（= 无害，摘链即可）／「其它」（= fail-closed 拒绝）。详见 §D-rm 与"未坐实/caveat"。

---

## 事实（逐条 [VERIFY]：原文 + 文件:行号 + 实测输出；先读 §0 行号漂移）

### 0. 行号漂移（先读：卡里的行号已过期）

`mw.py` 现 5,969 行、`mw_common.py` 现 4,964 行。2026-10-09 之后 `mw.py` 有 5 个 commit、`mw_common.py` 有 4 个 commit 触及它们（`git rev-list --count --since=2026-10-09 HEAD -- <path>`），行号随之漂移。

| 锚点 | 卡/spec 期行号 | **当前 HEAD 实测** | Δ |
|---|---|---|---|
| `_parse_args()` 定义 | `mw.py:5324` | **`mw.py:5603`** | +279 |
| `dispatch` dict / `sys.exit(dispatch[...])` | `mw.py:5639-5659` | **`mw.py:5949-5969`** | +310 |
| 错误约定样例（`_target_set`） | `mw.py:624-628` | **`mw.py:625-629`**（`def` 625，`print(..., file=sys.stderr)` 628，`return 1` 629） | +1 |
| `cmd_doctor` 注入段 | `mw.py:522-532` | **`mw.py:522-532`（未漂移）** | 0 |
| `doctor_report` | `mw_common.py:2957-2996` | **`mw_common.py:3624-3664`** | +667 |
| `_doctor_issues` | `mw_common.py:2780` | **`mw_common.py:3401`** | +621 |
| `format_doctor_text` | `mw_common.py:2999` | **`mw_common.py:3666`** | +667 |

> 结论：design/plan/task 卡里凡引用行号处，一律以本文件的行号为准；实现者动手前再 `grep` 一次函数名（`def _doctor_issues` 等）而不是照抄数字。

---

### 1. `mw worktree rm|add` 的落点与骨架

#### 1.1 一级子命令注册（照抄点）

```python
# mw.py:5603-5605
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers service manager")
    sub = parser.add_subparsers(dest="subcommand", required=True)
```

现有 17 个一级子命令的注册位置（实测）：`serve/start`（`:5607-5608`）、`stop/status`（`:5610-5612`）、`doctor`（`:5614`）、`target`（`:5627`）、`partition`（`:5646`）、`model`（`:5673`）、`autopilot`（`:5693`）、`init`（`:5735`）、`pull-agentictask`/`push-agentictask`（`:5745`/`:5755`）、`setup`（`:5762`）、`bootstrap`（`:5773`）、`build`（`:5793`）、`update-env`（`:5804`）、`ue-toolchain`（`:5853`）、`rag`（`:5887`）。
**新 `worktree_p = sub.add_parser("worktree", ...)` 插入点建议**：`:5853` 前（`ue-toolchain` 之前）或 `:5887` 前（`rag` 之前），保持"功能块追加在尾部"的既有顺序。

#### 1.2 二级动作范式（两选一，都是先例）

- **`_RAG_ACTIONS` dict**（`mw.py:2247-2257`，原文）：
  ```python
  def cmd_rag(args: argparse.Namespace) -> int:
      return _RAG_ACTIONS[args.rag_action](args)


  _RAG_ACTIONS = {
      "init": _cmd_rag_init,
      "list": _cmd_rag_list,
      "probe": _cmd_rag_probe,
      "audit": _cmd_rag_audit,
      "sync": _cmd_rag_sync,
  }
  ```
  subparser 侧：`target_sub = target_p.add_subparsers(dest="target_action", required=True)`（`mw.py:5631`）、`rag_sub = rag_p.add_subparsers(dest="rag_action", required=True)`（`mw.py:5892`）。
- **`cmd_autopilot` if-chain**（`mw.py:3557-3580`）：`if args.autopilot_action == "gates": return ...`；未知动作 `print(f"[mw autopilot] Error: unknown action {args.autopilot_action!r}", file=sys.stderr); return 1`。**同段 docstring 明写了本 key 要遵守的约定**：`Errors print ``[mw autopilot <action>] Error: ...`` to stderr and return 1; only ... write (both under the dedicated lock); ... are read-only machine exits.`

⇒ **建议 `mw worktree` 用 if-chain（不是 dict）**，因为 `add`/`rm` 之外还会有一个只读动作（例如 `list` 供 doctor/trace 复用），且 `rm` 的错误文本需要带"第几步"的上下文，if-chain 更容易逐级返回。

#### 1.3 参数解析与退出码约定

- 退出码：所有 `cmd_*` 返回 `int`，`sys.exit(dispatch[args.subcommand](args))`（`mw.py:5969`）；**0 = 成功，1 = 失败/有 issue**（`cmd_doctor:533`、`_toolchain_run:1058`、`_cmd_rag_init`）。
- 错误必须走 stderr（`mw.py:625-629`，原文）：
  ```python
  def _target_set(project_dir: pathlib.Path, args: argparse.Namespace) -> int:
      game = pathlib.Path(args.game).resolve()
      if not game.is_dir():
          print(f"[mw target set] Error: game root not found: {game}", file=sys.stderr)
          return 1
  ```
- 机器出口用 `--json`（`doctor`、`autopilot gates`、`rag list` 都有），**`mw worktree rm` 建议加 `--json`** 输出六步的前后对照（供 G4 测试断言；文本出口同时保留）。
- 参数命名先例：`--project` 一律 `required=True`；路径位置参数用 `metavar` 大写（`tc_run_p.add_argument("name", metavar="NAME", ...)` `mw.py:5866`）。

#### 1.4 可直接照抄的"前置快照 → 动作 → 后置快照 → 判定"范式

`_toolchain_run`（`mw.py:966-1058`）是仓库内唯一成形的同类先例，六步的第 4/6 步应当照它写：

```python
# mw.py:1003-1010（before 快照）
    watched: list[dict] = []
    for w in args.watch or []:
        ...
        watched.append({"path": str(p),
                        "before": mw_common.sha256_eol_normalized(p) if p.is_file() else None,
                        "after": None})
# mw.py:1028-1034（after 快照 + drift + 全判据 AND）
    for entry in watched:
        p = pathlib.Path(entry["path"])
        entry["after"] = mw_common.sha256_eol_normalized(p) if p.is_file() else None
        entry["drift"] = entry["after"] != entry["before"]
    drift = [e for e in watched if e["drift"]]

    ok = proc.returncode == 0 and not error_lines and not drift
# mw.py:1053-1058（打印对照 + 机器出口）
    print(f"[mw ue-toolchain] exit={proc.returncode} seconds={seconds:.1f} "
          f"error_lines={len(error_lines)} watched_drift={len(drift)}/{len(watched)} "
          f"— {'OK' if ok else 'ATTENTION'}")
    ...
    return 0 if ok else 1
```

`_cmd_rag_init`（`mw.py:2205-2216`）是"**先全量判定、一条都不写**"的范式（第 2 步必须先于第 3 步，且失败时零副作用）：

```python
    if args.dry_run:
        print("[mw rag init] dry-run — no files written")
        ...
        return 0

    if refusals:
        for path, reason in refusals:
            print(f"[mw rag init] Error: refusing to write {path}: {reason}", file=sys.stderr)
        print("[mw rag init] nothing written. Edit by hand or re-run with --force.", file=sys.stderr)
        return 1
```

#### 1.5 六步在 Python 侧的分工（哪几步必须同一进程/同一次调用）

| 步 | 动作（G2 原文） | Python 实现要点 | 必须同进程的理由 |
|---|---|---|---|
| 1 | 枚举 reparse point | 显式栈遍历 worktree，命中 reparse point 即记录且**不下钻**；同时取**主树 before 快照** | before 快照必须早于任何变更 |
| 2 | 校验目标在仓库内 | 对**全部**条目先算 `inside_repo`；有任一不满足 ⇒ 立即中止，**一条链都不摘** | 与第 3 步共享同一份链接列表；跨进程会把"A 通过检查、B 被摘"拆开 |
| 3 | 只摘链（`rmdir`，禁 `/S`） | `os.rmdir(link)`（实测只摘链不穿透，见 §5.3）或 `cmd /c rmdir <link>` | 第 2 步判定与第 3 步执行之间不允许有其它进程介入 |
| 4 | 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变 | 与第 1 步 before 快照**逐条比较**（规范化后的 `(link, target)` 集合相等） | 必须与第 1 步是同一份内存快照；落盘再读会引入"进程死在摘链与复核之间"的窗口 |
| 5 | 才 `git worktree remove --force` | `_git(["worktree", "remove", "--force", str(target)], cwd=repo_root)`（`_git` 在 `mw.py:4097-4103`） | 只认第 4 步的判定；第 4 步失败绝不执行 |
| 6 | 打印前后对照 | 打印 before/after 链接表 + 已摘链条目 + 退出码语义 | 对照的 before 必须来自第 1 步（本进程） |

⇒ **六步 = 一次 CLI 调用、一个进程、线性序列**。仓库里没有任何"分两次调用做同一事务"的先例（`dispatch.py:1186+` 的 read-back 验证同样在同一函数内完成）。

#### 1.6 "中止、不降级继续"的控制流草案

与 `mw.py` 既有风格一致（`_target_set` 的 print+return 1 / `_cmd_rag_init` 的 refusal 段 / `_toolchain_run` 的 AND 判定）：

```python
def _cmd_worktree_rm(args: argparse.Namespace) -> int:
    """G2 唯一正规命令：六步固定顺序，任一步失败即中止并保留现场（AC-004/006/007）。

    六步共处一个进程：第 2 步判定必须先于第 3 步摘链；第 4 步复核用的 before
    快照来自第 1 步；第 5 步只认第 4 步的判定。失败路径一律 return _abort(...)，
    没有 continue、没有兜底补偿写 —— "不降级继续"就是控制流的形状本身。
    """
    repo_root = _repo_root()                      # mw.py:4350-4351
    target = pathlib.Path(args.path).resolve()    # 规范化后再比较，避免 .. 与短名
    unlinked: list[dict] = []

    def abort(step_no: int, message: str) -> int:
        print(f"[mw worktree rm] ABORT at step {step_no}/6: {message}", file=sys.stderr)
        print("[mw worktree rm] 未降级继续：现场保留，git worktree remove 未执行；"
              "已摘链条目见下（其余链接一律保持原样）", file=sys.stderr)
        for item in unlinked:
            print(f"[mw worktree rm]   unlinked: {item['path']}", file=sys.stderr)
        return 1

    # 步 0（前置，非六步之一）：目标必须是本仓已登记的 worktree（git 自己的视图）
    proc = _git(["worktree", "list", "--porcelain"], cwd=repo_root)
    if proc.returncode != 0 or str(target) not in _porcelain_worktrees(proc.stdout):
        print(f"[mw worktree rm] Error: not a git worktree of {repo_root}: {target}", file=sys.stderr)
        return 1

    baseline = _reparse_snapshot(repo_root)        # 步 1b：主树 before 快照（含 @earendil-works/*）
    links = _enumerate_reparse_points(target)      # 步 1a：worktree 内枚举，命中的不下钻

    # 步 2：全量校验，任一条不合格 ⇒ 一条都不摘（fail-closed, AC-006）
    bad = [l for l in links if l["verdict"] == "foreign"]
    if bad:
        for l in bad:
            print(f"[mw worktree rm] Error: link target outside both the repo and this worktree: "
                  f"{l['path']} -> {l['target']}", file=sys.stderr)
        return abort(2, f"{len(bad)} link(s) failed the target check")

    for l in links:                                # 步 3：只摘链（禁 /S），逐条失败即中止
        try:
            os.rmdir(l["path"])                    # RemoveDirectoryW：摘链不穿透（§5.3 实测）
        except OSError as exc:
            return abort(3, f"unlink failed for {l['path']}: {exc}")
        unlinked.append(l)

    after = _reparse_snapshot(repo_root)           # 步 4：主树链接逐条未变
    if after != baseline:
        return abort(4, f"main-tree link set changed: {_snapshot_diff(baseline, after)}")

    proc = _git(["worktree", "remove", "--force", str(target)], cwd=repo_root)   # 步 5
    if proc.returncode != 0:
        return abort(5, f"git worktree remove --force failed (rc={proc.returncode}): "
                        f"{(proc.stderr or '').strip()[:200]}")

    _print_link_diff(baseline, after, unlinked)    # 步 6：前后对照
    return 0
```

控制流纪律（三条，写进 design 的约束节）：

1. **没有 `try/finally` 补偿**：唯一的 `except` 是 `except OSError as exc: ... return 1`（照 `_cmd_rag_init:2224-2226`）。任何"失败了也把剩下的链摘完"的写法都违反 AC-007。
2. **没有 `--force`/`--continue` 开关**：`mw worktree rm` 不接受任何"跳过某一步"的开关；确实需要手工介入时，输出里给的是可照抄的 `cmd /c rmdir "<link>"`（禁 `/S`）而不是一个降级开关。
3. **步 2 与步 3 之间零写入**：`links` 是步 1 冻结的列表，步 2 只读它。

---

### 2. 注册表（G3）与文件锁

#### 2.1 mw 现有"状态/注册表文件"约定的实测全貌

`<project>/.mw/`（`.gitignore:53` 整目录忽略）实测存在（本仓 2026-10-13 快照）：`conductor.log`、`dispatch.yml`、`launcher-beat.<pid>` ×20、`launcher.log`、`mw.log`、`mw.pid`、`proxy.log`、`serve-console.log`、`serve.meta`、`window-model`。

| 文件 | 定义（文件:行号） | 格式样例（实测） |
|---|---|---|
| `.mw/dispatch.yml` | `mw_common.py:216-217` | `models:` + 4 个 role 行 |
| `.mw/window-model` | `mw_common.py:220-221` | `timi/deepseek-v4.1-flash`（单行纯文本） |
| `.mw/serve.meta` | `mw.py:114-119` / `mw-runner.ts:204` | `{"pid": 168160, "started_at_ms": 1791860276020, "code_dir": "H:\\git\\Multi-Workers\\packages\\multi-workers"}` |
| `.mw/mw.pid` | `mw_common.py:2181` | 裸 PID |
| `.mw/mw.stop` | `mw.py:98` | 空文件（stop 请求哨兵） |
| `.mw/workers.lock` | `mw_common.py:1731-1732` | 空锁文件（O_CREAT\|O_EXCL） |
| `.mw/index.lock` | `index-store.ts:335` | 空锁文件 |
| `.mw/gates.lock` / `.mw/autopilot-config.lock` | `status-model.ts:62-63` / `:70-71` | 空锁文件 |
| `.mw/{name}.lock` | `conductor.py:137-139`（`workers`/`gates`/`roadmap`/`key-{key}`） | 空锁文件 |
| `.mw/conductor.pid` | `conductor.py:85` | 裸 PID |
| `.mw/launcher-beat.<pid>` | `mw_common.py:2478-2480` | `ts=<iso>` 单行 |
| `.mw/toolchain.json` | `mw_common.py:4723-4725` | 工具链探测缓存（JSON） |
| `.mw/toolchain-runs/<name>-<ts>/` | `mw.py:945` | `cmd.txt`/`run.log`/`exit.txt`/`errors.txt`/`meta.json` |
| `.mw/rag-servers.yml`, `.mw/rag-roots.json` | `mw_common.py:524` / `mw.py:2094` | YAML / JSON |
| `.agenticdoc/_workers.parallel` | `mw_common.py:1716-1717` | 管道 7..9 列（`parse_worker_line:1746-1770`）：`task_key \| status \| cli \| provider \| task_path \| dispatched_at \| updated_at \| model \| origin` |
| `.agenticdoc/_workers.stale.parallel` | `mw_common.py:1720-1721` | 归档行（原文 + `archived_at` + reason） |
| `.agenticdoc/_workers.acked` | `mw_common.py:1727-1728` | ack 表 |
| .agenticdoc/_autopilot/config.json | `autopilot/config.py:config_path()` | JSON（本仓当前不存在 = autopilot 未启用；**未被 .gitignore 忽略**） |
| `.agenticdoc/_index.parallel` | `autopilot/state.py:100`；`index-store.ts:333` | `\| key \| status \| phase \| claimId \| deps \| desc \| updated \|` |
| .agenticdoc/.mw/ | 仅 `.gitignore:71` 提及；**代码中无任何读写点**（实测空目录、`git ls-files` 无内容） | 保留位，不可作新约定依据 |

`_workers.parallel` 真实样例行（实测，本仓）：

```
t01-monitor-module | done | pi | timi | H:\git\Multi-Workers\.agenticdoc\autopilot-monitor\workers\t01-monitor-module\task.md | 2026-10-12T08:05:50.466Z | 2026-10-12T08:05:54+00:00 |
ga-spec-design-review-2 | done | pi | timi | ...\goal-autopilot\workers\...\task.md | ... | ... | gpt-5.6-sol
```

第 8/9 列（`model`、`origin`）正是"**谁写的**"（`dispatch.py:1149-1152` 注释：`D-019/AC-021: the producer records who owns the row`）⇒ 注册表要的 `created_by` 有现成语义先例。

#### 2.2 注册表落点与格式（草案）

**落点建议：`<project>/.mw/worktrees.json` + 锁 `<project>/.mw/worktrees.lock`。** 理由：

- 条目装的是**机器本地绝对路径**（`C:\Users\...\AppData\Local\Temp\qg-head`），提交进 git 无意义且会误导他机 ⇒ `.mw/`（`.gitignore:53` 整目录忽略）是唯一零额外规则的落点。
- `.mw/` 已经放了 `dispatch.yml` / `window-model` / `toolchain.json` / `rag-roots.json` 等配置型状态（见 §2.1），"`.mw/` 只放锁和 PID" 只是 `autopilot/config.py:4-5` 的自我描述，不是仓库事实。
- 若选 `.agenticdoc/_worktree-links.json`（照 .agenticdoc/_autopilot/config.json 的"人类可见"先例），需要新增 `.gitignore` 一行，且和 `_workers*` 通配的名词空间容易混淆（`.gitignore:70`）。

**格式（JSON，version 字段留升级位）**：

```json
{
  "version": 1,
  "entries": [
    {
      "link": "C:\\Users\\me\\AppData\\Local\\Temp\\qg-head\\node_modules",
      "target": "H:\\git\\Multi-Workers\\node_modules",
      "worktree": "C:\\Users\\me\\AppData\\Local\\Temp\\qg-head",
      "repo_root": "H:\\git\\Multi-Workers",
      "created_at": "2026-10-13T11:00:00+08:00",
      "created_by": "mw worktree add --link-deps (pid 1234, user wenbozhou)"
    }
  ]
}
```

字段与 AC-008 的对应：`target`（目标）、`created_at`（创建时刻）、`created_by`（创建者）是 AC 点名的三个；`link`/`worktree`/`repo_root` 是 doctor 与 `rm` 的判定输入（删除时用来定位 registry 条目）。

**读写 API 草案**（照 `autopilot/config.py` 的 load/validate/save + `mw_common.update_status` 的锁纪律）：

```python
def worktree_registry_path(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".mw" / "worktrees.json"


def worktree_registry_lock(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".mw" / "worktrees.lock"


def read_worktree_registry(project_root: pathlib.Path) -> list[dict]:
    """Missing file -> []（零足迹，不建目录）；存在但不可解析 -> 抛 RegistryError
    （fail-closed：registry 坏了绝不静默当空表 —— 空表 = 没有遗留链，是假阴性）。"""


def register_worktree_link(project_root: pathlib.Path, entry: dict) -> pathlib.Path:
    """校验 entry -> acquire_lock(worktree_registry_lock) -> read -> 按 link 去重
    upsert -> tmp + os.replace（照 _write_workers_file:2063-2075 / config.save_config）
    -> 读回验证 -> finally release_lock。锁是唯一的并发控制。"""


def unregister_worktree_link(project_root: pathlib.Path, link: str) -> bool:
    """幂等；mw worktree rm 第 5 步成功后调用（失败 ⇒ 返回 False，doctor 报 leftover）。"""
```

写入必须 tmp + `os.replace`（`mw_common._write_workers_file:2063-2075` 与 `config.save_config` 都是这个形状；`dispatch.py:1168-1172` 的注释给了解释：`open("w")` 先截断，序列化异常会把文件写空）。

#### 2.3 可复用的 O_CREAT|O_EXCL 锁原语（goal.md 约束）

```python
# packages/multi-workers/mw_common.py:2039-2058（原文）
def acquire_lock(lock_file: pathlib.Path, retries: int = 20, base_delay: float = 0.05) -> None:
    """Exclusive lock via O_CREAT|O_EXCL. Same protocol as the TS side."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if attempt == retries:
                raise RuntimeError(f"Could not acquire lock at {lock_file} after {retries} retries")
            import time
            time.sleep(base_delay * (2 ** attempt))


def release_lock(lock_file: pathlib.Path) -> None:
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass
```

调用样例（全部实测存在）：

```python
# mw_common.py:2110-2135（update_status：锁 + try/finally 释放）
    lock = lock_path(project_dir)          # .mw/workers.lock（:1731-1732）
    acquire_lock(lock)
    try:
        ...
        _write_workers_file(wpath, out)
    finally:
        release_lock(lock)
```

```python
# autopilot/dispatch.py:1153-1184（锁 + 失败即返回结构化 reason + 读回验证）
    try:
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:
        return DispatchResult(ok=False, reason=f"lock-unavailable: {exc}", ...)
    try:
        mw_common.upsert_worker_row(wpath, row)
    except OSError as exc:
        return DispatchResult(ok=False, reason=f"queue-write-failed: {exc}", ...)
    finally:
        mw_common.release_lock(lock)
    # 3. read-back verification: exactly one row with the right identity.
```

```python
# autopilot/conductor.py:137-183（命名锁 + stale steal，专治"持有者已死"）
def lock_file(project_root: pathlib.Path, name: str) -> pathlib.Path:
    """Named conductor lock: workers / gates / roadmap / key-{key}."""
    return pathlib.Path(project_root) / ".mw" / f"{name}.lock"
...
    mw_common.acquire_lock(path, retries=4, base_delay=0.02)   # 先快试
    ...  # 失败后按 mtime 判 stale，> STALE_LOCK_AGE_SEC 则 unlink 后重取，否则 ConductorLockHeld
```

其它调用点：`mw.py:3389/3428`、`mw.py:3529/3552`、`autopilot/xkey.py:559/581`、`test_autopilot_e2e.py:843/857`（`project / ".mw" / "index.lock"`）。
TS 侧同协议：`shared/file-lock.ts:12-43`（`fs.openSync(lockPath, "wx")`，`retries ?? 10`，`baseDelayMs ?? 50`，指数退避；返回 release 闭包）。

⇒ **注册表直接复用 `mw_common.acquire_lock`/`release_lock` + `conductor.lock_file` 的命名规则**（新锁名 `worktrees`）；不要新写锁实现（两套协议的偏差正是 IN-3 类事故的温床）。

---

### 3. `mw doctor` 新检查（AC-009）

#### 3.1 现有 `_doctor_*` 如何注册

```python
# mw_common.py:3624-3664（doctor_report，节选实测行号）
    report: dict = {}
    if fix:
        report["fix"] = {"applied": doctor_fix(project_dir)}
    report["service"] = _doctor_service(project_dir)                       # :3642
    report["proxy"] = _doctor_proxy(config)                                # :3643
    report["proxy_log"] = _doctor_proxy_log(project_dir)                   # :3644
    report["orphan_proxy"] = _doctor_orphan(report["service"], report["proxy"])  # :3645
    report["launcher_log"] = _doctor_launcher_log(project_dir)             # :3646
    report["queue"] = _doctor_queue(project_dir)                           # :3647
    report["worker_liveness"] = worker_liveness(project_dir, stale_after_sec)  # :3648
    report["credentials"] = route_precheck(config, os.environ)              # :3649
    report["bundle"] = _doctor_bundle()                                    # :3650
    report["target"] = _doctor_target(project_dir)                         # :3651
    report["autopilot"] = _doctor_autopilot(project_dir)                             # :3652
    report["gates"] = _doctor_gates(project_dir)                            # :3653
    report["dispatch"] = _doctor_dispatch(project_dir)                      # :3654
    report["pi_shell"] = ensure_pi_shell_path(env=os.environ, fix=fix)      # :3655
    ...
    issues, suggestions = _doctor_issues(report)                            # :3662
    report["summary"] = {"healthy": not issues, "issues": issues, "suggestions": suggestions}  # :3663
    return report                                                           # :3664
```

```python
# mw_common.py:3401-3402（issue 唯一汇聚点）
def _doctor_issues(report: dict) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    suggestions: list[str] = []
```
`issues` 翻转 `summary.healthy`（`:3663`）⇒ 决定 `mw doctor` 的退出码（`mw.py:533`）。

产出 issue 的原文范式（`mw_common.py:3413-3441`，队列形状三条判据）：

```python
    if not report["service"]["running"]:
        issues.append("mw service not running (workers will not be dispatched)")
    ...
    unparsable_count = int(queue_section.get("unparsable_count") or 0)
    if unparsable_count:
        first = (queue_section.get("unparsable") or [{}])[0]
        issues.append(
            f"queue-rows-unparsable: {unparsable_count} row(s) in _workers.parallel cannot be "
            f"read (first: line {first.get('line', '?')}, {first.get('cols', '?')} columns) - "
            "dispatch is refused while any row is unreadable (AC-020/AC-023); fix or delete "
            "the bad row, never rewrite the file from a parsed view"
        )
    ...
    if rows_total > alarm_delta and non_terminal_count / rows_total > 0.9:
        issues.append(f"queue-burst-shape: {rows_total} rows of which ... ")
```

文本渲染（`mw_common.py:3666+`）用"**条件成立才追加行**"的零扰动范式，例如 gates 行由 `_gates_text_alerted`（`:3375`）守卫、`dispatch` 行只在 `exists` 时出现（`:3808`）、`autopilot` 行只在 `xkey_verify_missing` 时出现（`:3769`）。

#### 3.2 关键结构事实：`cmd_doctor` 注入段**不能**产生 issue

```python
# mw.py:508-533（cmd_doctor，原文节选）
    report = mw_common.doctor_report(project_dir, fix=args.fix, config=config, stale_after_sec=args.stale_after)
    # Conductor section (D-101): informational like worker_liveness — a not
    # running conductor (autopilot disabled) is not an issue.
    report["conductor"] = _ap_conductor.conductor_status(project_dir)       # :523
    # RAG section (mw-rag-integration D-010): informational — a broken config
    # or an unreachable server never flips the healthy verdict.
    report["rag"] = _doctor_rag(project_dir)                                # :526
    if args.json:
        print(json.dumps(report, indent=2, default=str))                    # :528
    else:
        print(mw_common.format_doctor_text(report))
        rag = report.get("rag") or {}
        if rag.get("exists") or rag.get("enabled"):
            print(_format_rag_doctor_line(rag))                             # :532
    return 0 if report["summary"]["healthy"] else 1                         # :533
```

`report` 在 `:522` 就返回了，`_doctor_issues` 已在 `mw_common.py:3662` 跑完 ⇒ `:523`/`:526` 注入的段在 `_doctor_issues` 的视野之外，**注定**只能 informational（JSON 里可见，但永不翻转退出码）。

⇒ **AC-009 若要求"报出"并影响 `mw doctor` 的失败语义，新检查必须写进 `mw_common.doctor_report`（挂载点 (a)，`:3642-3655` 那一段），不能照 spec 期 RQ-2 建议的"最小侵入注入段"。** 若评审决定 AC-009 只要求"可见、不改退出码"，则走注入段（照 rag）也可以，但 design 必须显式写明这个取舍。

#### 3.3 检查函数草案

```python
# mw_common.py（新段，注册在 doctor_report 的 :3654 与 :3655 之间）
def _doctor_worktree_links(project_dir: pathlib.Path) -> dict:
    """G3/AC-009：遗留的"指向真树"的 junction + 注册表登记项的存活核对。

    只读、零写入：
      - 廉价域（默认）：<project>/node_modules/* 顶层 reparse point（实测 229 条
        / 1.97 ms），校验每条链接目标规范化后是否落在 repo_root 内；
      - 注册表域：<project>/.mw/worktrees.json 的每条登记项：
          目标仍存在                -> registered
          link 仍在但 worktree 已不在 -> leftover（AC-009 的"遗留"定义）
          link 已不在               -> stale-entry（登记项过期，建议 unregister）
      - 可选 --deep：全仓剪枝遍历（43,412 条目 / 0.28 s）。
    无遗留时 count=0，文本层不打印任何行（AC-009 反向对照不误报）。
    """
    section = {"scope": "node_modules/*", "entries": [], "registered": [],
               "leftover": [], "count": 0, "seconds": 0.0, "error": None}
    ...
    return section
```

输出字段（对齐 AC-009 + 与 `_doctor_gates` 的段形状一致）：

```json
{
  "scope": "node_modules/*",
  "entries": [{"link": "...", "target": "...", "kind": "junction|symlink",
               "target_exists": true, "target_inside_repo": true}],
  "registered": [{"link": "...", "worktree": "...", "created_at": "...", "created_by": "..."}],
  "leftover": [{"link": "...", "target": "...", "worktree": "...",
                "created_at": "...", "created_by": "...",
                "reason": "worktree-gone|target-missing|unregistered"}],
  "count": 1,
  "seconds": 0.002,
  "error": null
}
```

issue 文本草案（放进 `_doctor_issues`，与既有格式同构）：

```python
    wt = report.get("worktree_links") or {}
    for item in wt.get("leftover") or []:
        issues.append(
            f"worktree-link-leftover: {item['link']} -> {item['target']} "
            f"({item['reason']}; registered {item['created_at']} by {item['created_by']}) - "
            "the link chains into the real tree; remove the link only: "
            f'cmd /c rmdir "{item["link"]}"  (never /S, never git worktree remove on the '
            "parent dir while the link exists)"
        )
```

文本行（`format_doctor_text`，条件成立才打印）：

```python
    wt = report.get("worktree_links")
    if wt is not None and wt.get("count"):
        lines.append(f"worktree_links: {wt['count']} leftover link(s) -> "
                     + ", ".join(i["link"] for i in wt["leftover"]))
```

#### 3.4 成本：`@earendil-works/*` vs 全仓扫描（全部实测，min-of-N）

| 域 | 规模（本仓实测） | 耗时 | 覆盖 | 备注 |
|---|---|---|---|---|
| `node_modules/@earendil-works/*` | 10 条（9 junction + `gondolin` 真目录） | **0.000048 s**（仅 `isjunction`，min of 50）/ **0.000952 s**（`lstat`+`islink`+`readlink`+仓库内判定，min of 30） | 事故的 9 条 workspace 链 | **漏 `pi-extension-*` 5 条**（同在 `node_modules` 顶层、同为 workspace 链，见下） |
| `node_modules/*` 顶层 | 229 条（14 reparse） | **0.00197 s**（min of 20） | 全部 14 条 workspace 链 | 推荐默认域 |
| 全仓剪枝遍历（显式栈，不跟随 reparse point） | 43,412 条目 / 4,162 目录 / 14 reparse | **0.28 s** | 仓库内任意位置 | 必须剪枝：`os.walk` **会**下钻 junction（实测 `[wt, wt\node_modules]` 两个 dirpath，`followlinks=False` 亦然）⇒ 用 `os.walk` 写全仓扫描 = 重复遍历 `packages/**`，病态情况下可成环 |
| `packages/**` 剪枝 | 5,732 条目 / 498 目录 / **0 reparse** | 0.03 s | 源码树 | 佐证：本仓 reparse point 全部在 `node_modules` 下 |
| `%TEMP%` 顶层（活雷猎捕域） | 72,548 条顶层条目 / 38,538 目录 | `<dir>/node_modules` 定点扫 **1.19 s**；depth-1 全子项扫 **5.39 s** | 找到 1 条真雷 | 域无上界，**不建议**进 `mw doctor` 默认路径 |

`node_modules` 顶层实测就是全仓 reparse point 的全部 14 条，其中 9 条是 `@earendil-works/*`，另 5 条是 `node_modules/pi-extension-{custom-provider-anthropic,custom-provider-gitlab-duo,gondolin,sandbox,with-deps}` → `packages/coding-agent/examples/extensions/*`（对应 `package.json:9-14` 的 workspaces）。**只扫 `@earendil-works/*` 会漏掉这 5 条同等危险的链**。

---

### 4. `mw worktree add` 与既有 npm bootstrap 的关系

#### 4.1 既有 npm 引导路径（原文 + 行号）

```python
# mw.py:4963-4968（cmd_bootstrap 步 2，原文）
    # 2. node_modules
    if args.fast:
        skip(2, "--fast")
    else:
        step(2, "npm ci/install --ignore-scripts")
        install_cmd = [npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]
        if not _run_stream(install_cmd, cwd=repo_root):
            return fail("npm install failed — see the output above")
```

- `node_modules = repo_root / "node_modules"`（`mw.py:4863`）；`npm`/`node`/`git` 由 `shutil.which` 解析（`mw.py:4906-4910`）。
- `_run_stream(cmd, *, cwd)`（`mw.py:4791-4796`）：继承 stdio 的长子进程，`cmd[0]` 必须是已解析的绝对可执行文件（docstring 明写：`Windows Popen does not apply PATHEXT resolution`）。
- `_run_capture(cmd, *, timeout=60.0)`（`mw.py:4799-4807`）：短探针，返回 stdout 或 None。
- **没有**任何被抽出来的 npm 引导函数/开关：`install_cmd` 只出现在 `cmd_bootstrap` 内（grep `install_cmd` = 1 命中）。
- 与 `add` 相关的其它 bootstrap 步骤：步 3 `npm run build`（`:4972-4978`）、步 4 `npm link packages/coding-agent`（`:4981-4982`）、`_bootstrap_dirty_guard`（`:4535`）。三者都与"建不建链"无关。

⇒ **`mw worktree add` 没有可复用的 bootstrap 函数**，只有可复用的 `_run_stream` + `shutil.which`。两种处理：

- **(A) 抽一个 `_npm_hydrate(target_root: pathlib.Path) -> bool`** 放在 `_run_stream` 旁（`mw.py:4791` 之前），把 `install_cmd` 那 3 行搬进去，`cmd_bootstrap` 步 2 与 `_cmd_worktree_add` 双向调用。步 2 的 `step()/fail()` 打印留在 `cmd_bootstrap`，保持既有输出文本逐字节不变（既有 doctor/update-env 的"零扰动"精神）。
- **(B) 在 `_cmd_worktree_add` 内重写 3 行**（发现-即-复制），代价是两处 `install`/`ci` 分支判定会漂移。

⇒ 建议 (A)。

#### 4.2 默认不建链时应走哪条分支

- 新 worktree 是**干净检出**，其根下没有 `node_modules` ⇒ 走 `node_modules.is_dir()` 为假的分支 = **`npm ci --ignore-scripts`**。
- 与主树不同：主树用 `install`（增量、已存在）；worktree 用 `ci`（按 lockfile 全量、可复现）。这也正是 `spec.md` G3 原文「默认不建链（`npm ci` 或真实复制）」的落点。
- `--ignore-scripts` 是仓库硬约定（AGENTS.md "Don't run lifecycle scripts unless the user asks"；`packages/coding-agent/npm-shrinkwrap.json` 由 `scripts/generate-coding-agent-shrinkwrap.mjs` 生成，新依赖的生命周期脚本必须显式 allowlist）⇒ worktree 引导必须带 `--ignore-scripts`。
- `--link-deps`（显式建链）**与 npm 无关**：它是在 worktree 根下把 `node_modules` 指到主树（`mklink /J <wt>\node_modules <repo>\node_modules`）。`cmd /c` 与 `mklink` 在本仓 0 命中 ⇒ 新建；Python 无 junction 创建 API，`os.symlink` 只能建 symlink。建链后必须 `register_worktree_link(...)`（§2.2）。

#### 4.3 `npm ci` 之后 worktree 里会自动出现什么（设计必读）

主树 `node_modules/@earendil-works/*` 是 npm workspace reify 产物，不是手工建链（事故时间线 §2 里 20:38:58 的 `npm install --ignore-scripts` 重建了 8 条链）。因此 **worktree 里跑 `npm ci` 会在该 worktree 自己的 `node_modules/@earendil-works/*` 下建 9 条 junction，目标是 `<worktree>/packages/*`**（若 worktree 在仓库根下，则目标仍在仓库内）——**这与"指回主树"是两回事，但 AC-006 的字面表述无法区分**（见 TL;DR 9 与 §D-rm）。

---

### 5. 支撑 AC-004/005/006/007 的关键实测（Python 侧原语）

#### 5.1 reparse point 判定（Python 3.14.3，实测）

| 原语 | 结果 |
|---|---|
| `os.path.isjunction(link)` | junction=True；symlink=False；**断链 junction=True** |
| `os.path.islink(link)` | junction=**False**（不能用来判 junction） |
| `os.lstat(link).st_reparse_tag` | junction=`2684354563`(0xA0000003)；symlink=`2684354572`(0xA000000C)；真目录=0 |
| `os.lstat(link).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`（1024） | junction=True |
| `os.readlink(link)` | `\\?\H:\git\Multi-Workers\packages\ai` 形态（`\\?\` 前缀需剥掉再做前缀比较） |
| `os.path.exists(link)`（断链） | **False** ← 断链检测必须用 `os.path.lexists`/`isjunction`，用 `exists` 会看不见链接 |
| `os.path.realpath(link)` | 跟随解析到目标（断链时返回目标路径字符串） |

#### 5.2 "目标在仓库内"判定（AC-006 原语）

```python
def _inside(target: str, root: pathlib.Path) -> bool:
    t = target[4:] if target.startswith("\\\\?\\") else target      # junction readlink 带 \\?\ 前缀
    t = os.path.normcase(os.path.normpath(t))
    r = os.path.normcase(os.path.normpath(str(root)))
    return t == r or t.startswith(r + os.sep)
```
实测：`@earendil-works/*` 9 条全部 `inside_repo=True`（目标 `H:\git\Multi-Workers\packages\*`）；`%TEMP%\mwvg-t5\node_modules` 的目标 `\\?\H:\git\Multi-Workers\node_modules` 也 `inside_repo=True`。（注意 `normcase` 是必需的：Windows 下 `C:\Users\...` 与 `C:\Users\WENBOZ~1\...` 短名混用。）

#### 5.3 "只摘链"原语（AC-005，`%TEMP%` fixture 实测，目标 = 2 文件 + 1 子目录，逐次重建后单测）

| 操作 | 结果 | 目标是否完好 |
|---|---|---|
| `os.rmdir(link)` | ok | ✔（`['keep.txt','sub']` 不变） |
| `os.unlink(link)` | ok | ✔ |
| `os.remove(link)` | ok | ✔ |
| `pathlib.Path.rmdir()` | ok | ✔ |
| `os.rmdir(link + os.sep)` | ok | ✔ |
| `os.replace(link, other)` | ok | ✔ |
| `cmd /c rmdir <link>`（无 `/S`） | ok | ✔ |
| `shutil.rmtree(link)` | **拒绝**：`OSError: Cannot call rmtree on a symbolic link` | ✔（本 Python 版本不会穿透） |
| `os.rmdir(断链 junction)` | ok（摘链成功） | — |

⇒ 第 3 步可直接用 `os.rmdir(link)`（Windows `RemoveDirectoryW`：只摘 reparse point，不递归目标），无需 subprocess；与 spec 期证据的 `cmd /c rmdir <link>`（禁 `/S`）语义等价。若 design 要求与 spec 文本字面一致，用 `subprocess.run(["cmd", "/c", "rmdir", str(link)])` 也可（实测同样安全），代价是每条链多一次进程。

#### 5.4 事故链路形态（当前活雷，只读复核）

```
C:\Users\<user>\AppData\Local\Temp\mwvg-t5\node_modules   (junction, tag 0xA0000003)
  -> \\?\H:\git\Multi-Workers\node_modules
H:\git\Multi-Workers\node_modules\@earendil-works\pi-ai   (junction)
  -> \\?\H:\git\Multi-Workers\packages\ai
```
`os.listdir(%TEMP%\mwvg-t5\node_modules)` 直穿真树 `node_modules`（实测返回 `['.bin','.cache','.package-lock.json','@anthropic-ai','@aws',...]`）。这就是双层链（`incidents-timeline` §3）的活样本。同级 `%TEMP%\qg-head`、`%TEMP%\qg2-head` 已不存在；`%TEMP%\mwvg-t5-probe` 目录在但无 `node_modules`。

#### 5.5 git 侧现状（只读）

```
$ git worktree list --porcelain
worktree H:/git/Multi-Workers
HEAD cc9a46a1ad1ebb35eb1b5d96d8101c46cd3b78ad
branch refs/heads/dev/AgentTeam
```
`.git/worktrees` 为空 ⇒ 当前无遗留 worktree 注册。`git --version` = 2.53.0.windows.1。

---

## 对 design 的直接含义（可写进 design.md）

### D-cli：`mw worktree` 子命令接口

```
mw worktree add <path> [--project DIR] [--ref REF] [--link-deps] [--dry-run] [--json]
mw worktree rm  <path> [--project DIR] [--json]
mw worktree list [--project DIR] [--json]          # 只读：注册表 + git worktree list 合并视图
```
- 注册：`worktree_p = sub.add_parser("worktree", help=...)` + `worktree_sub = worktree_p.add_subparsers(dest="worktree_action", required=True)`（插入点 `mw.py:5853` 或 `:5887` 前）；`cmd_worktree` 走 if-chain（照 `cmd_autopilot:3557`）。
- 退出码：0/1；错误一律 `[mw worktree <action>] Error: ...` 到 stderr；`--json` 输出六步的机器可读记录（供 G4/AC-004~007 断言）。
- `add` 默认路径 = `npm ci --ignore-scripts`（复用的抽出函数 `_npm_hydrate`，见 D-add）；`--link-deps` 才建链并登记注册表（AC-008）。

### D-rm：六步事务

见 §1.5/§1.6。写进 design 的三条硬约束：(i) 六步同进程线性；(ii) 步 2 全量判定先于步 3 任何摘链（plan-then-apply，范式 `_cmd_rag_init:2212-2216`）；(iii) 中止 = 逐级 `return 1` + "未降级继续"打印，无补偿写入、无跳过开关。

**必须由 design 决策的矛盾点（AC-006 字面 vs 可用性）**：判定规则建议改成三分类

| 链接目标 | 语义 | 动作 |
|---|---|---|
| 落在 `repo_root` 内（= 指回真树，事故形态） | 危险但有解 | 摘链 → 步 4 复核主树链接逐条未变 → 才 remove |
| 落在被删 worktree 子树内（= `npm ci` 自指链） | 无害 | 摘链即可（与 worktree 一起消失，不影响主树） |
| 其它（仓库外、worktree 外） | 不可归类 | **fail-closed 拒绝，一条链都不摘**（AC-006 的本意） |

若坚持 AC-006 字面（只接受 `repo_root` 内），则"仓库外 worktree + `npm ci`"组合会被 G2 拒绝而 G1 又拦截裸 `git worktree remove` ⇒ 死锁。**这是本 RQ 发现的唯一会让规格自相矛盾的点，建议 QC/评审在 design 期拍板。**

### D-registry：注册表接口

```python
# 新增（建议放 mw_common.py，与 workers_path/lock_path 同段 :1716-1732 之后）
worktree_registry_path(project_root) -> Path        # <root>/.mw/worktrees.json
worktree_registry_lock(project_root) -> Path        # <root>/.mw/worktrees.lock
read_worktree_registry(project_root) -> list[dict]  # missing -> []；坏文件 -> RegistryError（fail-closed）
register_worktree_link(project_root, entry) -> Path # 锁 + 校验 + upsert + tmp/replace + 读回验证
unregister_worktree_link(project_root, link) -> bool
```
- 锁：复用 `mw_common.acquire_lock/release_lock`（`:2039`/`:2054`）+ `conductor.lock_file` 的命名规则（`conductor.py:137-139`）。
- 写入：tmp + `os.replace`（`_write_workers_file:2063-2075`、`config.save_config`）。
- 字段：`link`/`target`/`worktree`/`repo_root`/`created_at`/`created_by`（AC-008 点名的三项在此）。
- `mw worktree rm` 第 5 步成功后 `unregister_worktree_link`；`--link-deps` 建链成功后 `register_worktree_link`。

### D-doctor：新段

- **挂载点**：`mw_common._doctor_worktree_links(project_dir)`，在 `doctor_report`（`:3642-3655`）内注册为 `report["worktree_links"]`；issue 进 `_doctor_issues`（`:3401`，格式同 `queue-burst-shape`）；文本行进 `format_doctor_text`（`:3666`，条件成立才打印）。
- **不要**走 `cmd_doctor:522-526` 注入段（`:3662` 之后注入 = 永远不产生 issue，见 §3.2）；若评审决定 AC-009 只要"可见"不要"失败语义"，才可用注入段，并需在 design 里写明这个降级。
- **域**：默认 `node_modules/*` 顶层（1.97 ms，覆盖全部 14 条 workspace 链）；`--deep` 再走全仓剪枝遍历（0.28 s）；`%TEMP%` 全域扫描（1.19-5.39 s、无上界）**不入默认路径**，只作为 `mw doctor --deep-temp` 之类的显式开关或留在测试里。
- **反向对照（AC-009）**：`count == 0` 时不打印任何行、不产生 issue；现有活雷 `%TEMP%\mwvg-t5\node_modules` 是现成阳性样本（但它在 `%TEMP%`，默认域看不见 —— design 需明确"遗留"的判定域到底覆盖哪里：注册表域 + 仓库内域，还是也要扫 `%TEMP%`）。

### D-add：与 bootstrap 的关系

- 抽出 `_npm_hydrate(target_root)`（把 `mw.py:4966` 那 3 行搬走），`cmd_bootstrap` 步 2 与 `_cmd_worktree_add` 共用；新 worktree 走 `npm ci --ignore-scripts`。
- `add` **不**跑 `npm run build`、**不**跑 `npm link`、**不**动 `mw setup`（那些是 bootstrap 的机器级动作，不是 worktree 级的）。
- `--link-deps` 的建链原语要新写（`cmd /c mklink /J` 或 `os.symlink`；本仓 0 先例），并立即登记注册表。

---

## 未坐实 / caveat

1. **AC-006 与"仓库外 worktree + `npm ci`"的矛盾未定**（§D-rm）。本报告只给出三分类方案，未获规格拍板；若 design 照字面实现 AC-006，会出现"G1 拦 + G2 拒"的死锁。这是必须由人拍的决策，不是可实测的事实。
2. **AC-009 的"遗留"判定域未定**：AC 原文说"指向仓库内的 junction"并给"路径"，但事故的真雷在 `%TEMP%`（仓库外）。本报告给出"仓库内 `node_modules/*` + 注册表"两个域与各自成本，哪个是 AC-009 的验收域需评审确认。
3. **`npm ci` 在 worktree 里的实际产物未实测**：本任务禁止真树写入，也未在临时目录里跑 `npm ci`（数 GB、网络、耗时）。"worktree 的 `node_modules/@earendil-works/*` 指向该 worktree 自己的 `packages/*`" 是从主树观测形态 + `package.json:6-14` workspaces 推出的**推断**（高置信，未坐实）。
4. **`os.rmdir` 对 junction 的"只摘链"行为只在 python 3.14.3 + 本机 NTFS 上实测**；真实事故的穿透是 git 自己的递归删除器行为，两者机制不同已由 spec 期证据分开坐实，但本报告未复测 git 2.53.0 之外的版本。
5. **`os.symlink` 在本机可用**（reparse tag 0xA000000C），但 Windows 上目录 symlink 需要开发者模式/特权；`--link-deps` 若改用 symlink（更抗 git 穿透）会在无特权的机器上失败。**未验证**低特权环境，也未验证 symlink 形态在 `os.rmdir` 下是否同样安全可用（junction 已测）。
6. **未测 OneDrive/cloud 占位符等其它 reparse tag**（本仓相关域内 0 命中；`%TEMP%` 顶层 29 条 reparse 全是 `jb.station.*.sock`/`socket_*` 类非 junction 条目）。
7. **未测 `--link-deps` 的目标选择**（指主树 `node_modules` vs 逐包链 vs 直接复制）：AC-008 只要求"建链则登记"，形式待 design。
8. **未测多 worktree 并发 `mw worktree rm`**（两个 worktree 同时摘链 + 复核同一份主树快照）；按设计各自独立，但并发写入注册表依赖 `.mw/worktrees.lock`，未做竞态实测。
9. **`%TEMP%` 的 72,548 顶层条目数量是本机当前状态**，随使用变化；`1.19 s`/`5.39 s` 只代表这一时点。
10. 本报告未覆盖 G1（TS guard）与 G4（可观测）——那分别是 T-D1 / T-D3 的 RQ 范围。

---

## [VERIFY] 汇总（本次实测打印，可复算）

```
[VERIFY] env: python=3.14.3 git=2.53.0.windows.1 node=v24.19.0 os=10.0.26100.9168 HEAD=cc9a46a1a
[VERIFY] line_drift: mw.py:5324->_parse_args=5603 (+279); mw.py:5639-5659->dispatch=5949-5969 (+310);
          mw.py:624-628->_target_set=625-629 (+1); mw.py:522-532->cmd_doctor injection=522-532 (0);
          mw_common.py:2957-2996->doctor_report=3624-3664 (+667); mw_common.py:2780->_doctor_issues=3401 (+621);
          mw_common.py:2999->format_doctor_text=3666 (+667)
[VERIFY] commits_since_2026-10-09: mw.py=5 mw_common.py=4
[VERIFY] mw_worktree_subcommand=absent; ts_worktree_hits=1 (comment only, change-ledger.ts:127)
[VERIFY] cmd_doctor injects AFTER _doctor_issues -> injected sections can never produce issues
          (mw.py:522 doctor_report returns; mw.py:523/526 inject; mw_common.py:3662 issues)
[VERIFY] earendil_scope_entries=10 junctions=9 gondolin_real_dir=1
          all_target_inside_repo=True all_target_exists=True
[VERIFY] repo_reparse_total=14 = 9 @earendil-works/* + 5 node_modules/pi-extension-* (all -> repo/packages/*)
[VERIFY] cost: @earendil-works isjunction-only min=0.000048s(n=50) mean=0.000053s max=0.000117s
          @earendil-works lstat+readlink+inside min=0.000952s(n=30)
          node_modules/* top-level 229 entries 14 reparse min=0.00197s(n=20)
          repo pruned walk entries=43412 dirs=4162 reparse=14 seconds=0.28
          node_modules pruned walk entries=24285 dirs=1987 reparse=14 seconds=0.13
          packages pruned walk entries=5732 dirs=498 reparse=0 seconds=0.03
          TEMP top-level entries=72548 dirs=38538 reparse=29; <dir>/node_modules sweep=1.193s;
          TEMP depth-1 sweep scanned_children=30719 seconds=5.39
[VERIFY] naive os.walk DOES descend into a junction (followlinks=False): yielded [wt, wt\node_modules]
[VERIFY] live_landmine: %TEMP%\mwvg-t5\node_modules isjunction=True
          readlink=\\?\H:\git\Multi-Workers\node_modules target_exists=True;
          %TEMP%\qg-head, %TEMP%\qg2-head absent
[VERIFY] junction_unlink (target 2 files + 1 subdir; target_list unchanged each time):
          os.rmdir=ok os.unlink=ok os.remove=ok Path.rmdir=ok os.rmdir(link+sep)=ok
          os.replace=ok cmd/c rmdir=ok shutil.rmtree=refused(OSError Cannot call rmtree on a symbolic link)
          os.rmdir(broken junction)=ok
[VERIFY] broken_junction: exists=False lexists=True isjunction=True readlink=<target> target_exists=False
[VERIFY] symlink: os.symlink(dir) ok tag=2684354572 islink=True isjunction=False; mklink /J rc=0
[VERIFY] git worktree list --porcelain => 1 worktree (H:/git/Multi-Workers, dev/AgentTeam); .git/worktrees empty
[VERIFY] lock_primitives: mw_common.acquire_lock=2039 release_lock=2054 O_CREAT|O_EXCL=2044;
          callers: mw_common.py:2111/2135, mw.py:3389/3428, mw.py:3529/3552, dispatch.py:1156/1184,
          xkey.py:559/581, conductor.py:137-183; TS file-lock.ts:12-43 openSync(wx)
[VERIFY] registry_conventions: .mw/ 15 distinct filenames observed in-tree; the reserved
          .agenticdoc dot-mw dir is empty and referenced only by .gitignore:71; .gitignore:53 ignores .mw/;
          :70 ignores .agenticdoc/**/_workers*
[VERIFY] npm_bootstrap: mw.py:4966 install_cmd=[npm, "install" if node_modules.is_dir() else "ci",
          "--ignore-scripts"]; no extracted helper (install_cmd grep=1); _run_stream=4791 _run_capture=4799
          _git=4097 _repo_root=4350
```

## 结论

（PM 补录：worker 交付内容完整，但缺本节规范标题；以下为**逐条摘录**自本文件 TL;DR / §1-§4 与 §D-* 的答案，不改动原文。）

1. **落点**：`mw worktree` 目前完全不存在（`mw.py` grep `worktree` 0 命中，PM 已独立复核；TS 侧仅 `change-ledger.ts:127` 一处注释命中）⇒ G2/G3 是纯新建。一级注册点 = `mw.py:5603` 的 `_parse_args` 内（建议插在 `:5853` 或 `:5887` 之前），二级动作走 if-chain（照 `cmd_autopilot:3557`），错误约定照 `_target_set:625-629`。
2. **六步必须同进程**：步 2 全量判定先于步 3 任何摘链（plan-then-apply，范式 `_cmd_rag_init:2212-2216`）；步 4 复核与步 1 before 快照同内存；步 5 只认步 4 的判定；中止 = 逐级 `return 1` + "未降级继续"打印，无 `try/finally` 补偿、无跳过开关。
3. **注册表**：`.mw/worktrees.json` + `.mw/worktrees.lock`（`.gitignore:53`）；字段 `link/target/worktree/repo_root/created_at/created_by`；写入 tmp + `os.replace` + 读回验证；锁**直接复用** `mw_common.acquire_lock:2039` / `release_lock:2054`（`O_CREAT|O_EXCL` @ `:2044`）与 `conductor.lock_file:137-139` 的命名规则，不新写锁实现。
4. **doctor**：新检查必须挂 `mw_common.doctor_report`（`:3624-3664`）**内部**才能产生 issue —— `mw.py:522-526` 的注入段在 `_doctor_issues`（`:3662`）之后执行，注定只能 informational（这正是 conductor/rag 两段的语义来源）。默认域 = `<root>/node_modules/*` 顶层（1.97 ms，覆盖全部 14 条 workspace 链）；`--deep` 全仓 0.28 s；`%TEMP%` 全域 5.39 s 不入默认路径。
5. **成本**：`@earendil-works/*` 10 条 0.05/0.95 ms；`node_modules/*` 顶层 229 条 1.97 ms；全仓剪枝 43,412 条目 0.28 s；`%TEMP%` 定点 1.19 s / depth-1 5.39 s。
6. **`add`**：既有 `install_cmd`（`mw.py:4966`）**无抽出的可复用函数**（grep 仅 1 命中）⇒ 建议抽 `_npm_hydrate(target_root)` 放 `_run_stream:4791` 旁；新 worktree 走 `npm ci --ignore-scripts`；`--link-deps` 的建链原语仓内 0 先例，需新写。
7. **两项待拍板**（本卡只给方案，未获规格授权）：(a) AC-006 字面「目标在仓库外即拒绝」会把"仓库外 worktree + `npm ci` 自指链"与 G1 的死锁做实，建议三分类（`repo_root` 内 = 摘链+复核 / worktree 子树内 = 摘链 / 其它 = fail-closed）；(b) AC-009 的"遗留"判定域（仓库内 + 注册表 vs 也扫 `%TEMP%`）。
8. **行号漂移**：卡与 spec 期证据的行号已过期（`_parse_args` 5324→5603、`doctor_report` 2957→3624、`_doctor_issues` 2780→3401、`format_doctor_text` 2999→3666、`_target_set` 624→625），实现前必须 grep 函数名。
9. **现成活雷（PM 已独立复核）**：`%TEMP%\mwvg-t5\node_modules` 是 `Junction`、目标 `H:\git\Multi-Workers\node_modules` 存在且可解析 ⇒ 事故前夜的链路形态今天仍在（本卡只读观测，未触碰）。

## 上下文来源

（PM 补录；清单取自本文件各节实际引用的 `文件:行号`。）

| 文件 | 行 | 用途 |
|---|---|---|
| `packages/multi-workers/mw.py` | `:5603`、`:5949-5969`、`:625-629`、`:508-533`、`:966-1058`、`:2205-2216`、`:2247-2257`、`:3557-3580`、`:4097`、`:4350`、`:4503-4507`、`:4791-4807`、`:4863`、`:4906-4910`、`:4963-4982`、`:5175`、`:5192`、`:5853`、`:5887`、`:353`、`:376` | 子命令先例、错误约定、医生注入段、六步范式、`_RAG_ACTIONS`、`cmd_autopilot`、`_git`/`_repo_root`、路径面惯例、`_run_stream`、bootstrap 的 `install_cmd`、rag/toolchain 插入点 |
| `packages/multi-workers/mw_common.py` | `:2039-2058`、`:2063-2075`、`:2110-2135`、`:3401-3441`、`:3624-3664`、`:3666`、`:1716-1732`、`:216-221`、`:4723-4725`、`:524`、`:2181`、`:2477-2480` | 锁原语、原子写、调用样例、issue 汇聚点、doctor 段注册、文本渲染、注册表/锁路径惯例 |
| `packages/multi-workers/autopilot/config.py` | `:4-5`、`:86` | `.mw/` 自我描述、conductor tick 默认 4 s |
| `packages/multi-workers/autopilot/conductor.py` | `:85`、`:137-183` | 命名锁 + stale steal 范式 |
| `packages/multi-workers/autopilot/dispatch.py` | `:1149-1152`、`:1153-1184`、`:1168-1172` | "谁写的"语义先例、锁 + 结构化 reason + 读回验证、`open("w")` 截断风险注释 |
| `packages/multi-workers/launcher.py` | `:50`、`:1706`、`:1717`、`:1899-1905`、`:1277`、`:1612` | poll 频率、采样挂载点、beat、告警与 trace 通道 |
| `packages/multi-workers/mw_runner.ts` / `autopilot/state.py` / `index-store.ts` / `status-model.ts` / `shared/file-lock.ts` | `mw_runner.ts:204`、`state.py:100`、`index-store.ts:333/335`、`status-model.ts:62-63/:70-71`、`file-lock.ts:12-43` | `.mw/` 与 `.agenticdoc/` 的既有状态文件形状、TS 锁对端 |
| `.gitignore` | `:53`、`:70`、`:71` | `.mw/` 整目录忽略、`_workers*` 通配、`.agenticdoc/.mw` 保留位 |
| `package.json` / `packages/coding-agent/package.json` | `package.json:9-14` | workspaces 列表（解释 5 条 `pi-extension-*` 链） |
| `.mw/` 目录实测清单、`.agenticdoc/_workers.parallel` 样例行 | — | 既有状态文件全貌、第 8/9 列（`model`/`origin`）语义先例 |
| 本 key 前序证据 | — | `spec-junction-semantics-20261009.md`、`spec-guard-and-mw-seams-20261009.md`、`incidents-timeline-20261009.md` |
| `%TEMP%\mwvg-t5\node_modules`、`%TEMP%\mwvg-t5-probe`、`%TEMP%\qg-head`、`%TEMP%\qg2-head` | — | 活雷/已消失样本的只读观测 |

PM 复核（2026-10-13，一手复看）：`_parse_args`=5603、`cmd_doctor`=508、`doctor_report`=3624、`_doctor_issues`=3401、`acquire_lock`=2039/`release_lock`=2054、`.gitignore:53`、`mw.py:4966` 的 `install_cmd` 原文、`%TEMP%\mwvg-t5\node_modules` 是 Junction 且目标存在、`mw.py` grep `worktree` 0 命中。以下为 worker 实测、PM 未复算：0.05/0.95/1.97 ms/0.28 s/1.19 s/5.39 s 的耗时矩阵、`os.rmdir` 等 7 种原语与 `shutil.rmtree` 的行为、`os.walk` 下钻 junction。

## 残留与未验证

（PM 补录，与上文 `## 未坐实 / caveat` 十条一一对应，只做"对 design 的处置"归并。）

| 原编号 | 未坐实项 | 处置（design 已落） |
|---|---|---|
| 1 | AC-006 与"仓库外 worktree + `npm ci`"矛盾 | design §4.4 决策 D-1（三分类，**待用户确认**） |
| 2 | AC-009 的"遗留"判定域未定 | design §5.3 决策 D-2（注册表域 + 仓库内域默认开，`%TEMP%` 显式开关，**待用户确认**） |
| 3 | worktree 内 `npm ci` 产物是推断 | design §7 第 2 条：按三分类容纳，实现期可选实跑 |
| 4 | `os.rmdir` 摘链仅单版本/单文件系统实测 | design §7 第 5 条：优先 junction，参数化 |
| 5 | `os.symlink` 需特权、symlink 形态未测安全 | 同上（`--link-deps` 目标选择待实现期定） |
| 6 | 其它 reparse tag（云占位符）未测 | design §10 未覆盖面声明 |
| 7 | `--link-deps` 目标选择未定 | design §8（G3 写面）待实现期决策，不阻塞 design |
| 8 | 多 worktree 并发 `rm` 未实测竞态 | design §7 第 6 条：以 `.mw/worktrees.lock` 串行 |
| 9 | `%TEMP%` 条目数/耗时是单时点 | design §5.2 表内标注 |
| 10 | G1/G4 不在本卡范围 | 已分别由 T-D1/T-D3 覆盖 |

未覆盖面声明（本卡明确没做的）：未改任何生产文件（零写入）；未在真树建/删 worktree 或 junction；未跑 `npm ci`（数 GB/网络）；未测非 Windows 平台与 Python 3.14.3 之外的版本；未查 git 上游文档（裸名匹配规则属 T-D1 范围）。
