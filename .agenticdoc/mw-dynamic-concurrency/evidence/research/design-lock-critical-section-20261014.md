# RQ-D3 证据：在飞判定进锁的临界区设计（含重复派发对拍方案）

> key: `mw-dynamic-concurrency` / phase: DESIGN / 类型: research / 角色: **只读**
> 卡片: `tasks/T-C-D3-lock-critical-section.md`（`card_sha256: 11bb81daeef29724b13930a696f037822350b380e373f46904dc4cb963c093ce`）
> 唯一证据文件: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-lock-critical-section-20261014.md`
> 复现脚本（临时，可删）: `.agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/`
> 日期: 2026-10-14

## 0 结论先行

1. **窗口已复现（两条通道 + 真数值）**。两进程各自"先读快照判在飞、后调 `dispatch.dispatch`"，两边都通过判定、都 `ok=True`、都写盘：队列里该 `task_key` **恰好 1 行**、timeline **2 条 `dispatch` 事件**、两个调用方**都** `row_verified=True`（模型列只剩后写者的值，先写者的派发在行里不可见）。走 conductor 真入口（两个 `conductor.tick` 并发）同样复现：**2 条 dispatch 事件 + 1 行**。
2. **临界区最小形状**：把"读队列 → 判同 `task_key` 是否在飞 → 建 task.md → append 行"四步放进 `dispatch()` **已有的那一次** `mw_common.acquire_lock(lock)`（`dispatch.py:1156`）之内。**持锁者是 dispatch 内部（写方）**，不是调用方。
3. **调用方持锁不可行**：`dispatch()` 自己会再取同一把锁，调用方先持锁 = 嵌套 `O_CREAT|O_EXCL` 必然失败；`acquire_lock` 的 20 次指数退避累计 ≈ 52428.75 s（约 14.6 h）后才抛 `RuntimeError`（`mw_common.py:2114-2126`）。要么 dispatch 内部持锁，要么把 dispatch 拆成 prepare/commit 两段（改动大得多，见 §2.7 选项 C）。
4. **必须共用一把 `.mw/workers.lock`，不能"每 key 一把锁"**：`_workers.parallel` 是**整文件读-改-写**（`upsert_worker_row`：全量 `_scan_worker_lines` → 单行替换/追加 → tmp + `os.replace`，`mw_common.py:2152-2172`），per-key 锁下两个写者会各自整文件重写而互相丢行。两侧本来就共用同一路径（Python `mw_common.lock_path` = `<root>/.mw/workers.lock`；TS `WorkerStore.lockPath` = `<agenticdocRoot>/../.mw/workers.lock`，`agenticdocRoot = <projectDir>/.agenticdoc`），已验证同文件。
5. **PM 侧 `WorkerStore.upsert` 不满足**：它只在文件 RMW 期间持锁，**判定在锁外**——`pm-orchestrator.ts:1012` 的 `dispatched` 集合来自扫描起点的 `readQueue()` 快照，`ui-bridge.ts:2343` 用 `fs.existsSync(taskDir)` 当幂等令牌（TOCTOU）。
6. **`task.md` 移到锁内，牵动面很小**：`dispatch_card()` 只读 `<key>/tasks/<stem>.md`，不依赖 task_dir 存在；`card_path:`/`card_sha256:` 是已渲染进 `content` 的字符串，与建目录的先后无关。真正受影响的是 `DispatchResult.task_md` 在 `lock-unavailable` 路径上的取值、以及"孤儿 shape 由 reconciliation 自愈"这条注释/契约（§3）。
7. **可证伪判据不是"行数"**：今天 `upsert_worker_row` 的覆盖语义保证同 `task_key` 恒 1 行（"no duplicate-key rows ever appear"，`dispatch.py:1134-1137`），所以**行数单独不构成判据**。可证伪判据是 **`ok=True` 的调用数 == 1** 与 **timeline `dispatch` 事件数 == 1**（§4.3）。
8. **锁内新增工作量可接受**：426 行真实队列实测——整文件 upsert 1.18 ms；"锁内多一次 parse（dup 检查）+ upsert" 1.94 ms（边际 +0.76 ms），launcher poll 间隔 5 s（`launcher.py:51`）。
9. **三处只读消费者保持快照判定**（`_stage_closure` / `pending_gate_reminders` / `_defer_declined_gate`）：它们不创建队列行，失败方向有界且偏保守；把它们也搬进 `.mw/workers.lock` 会把 roadmap / gates / timeline / `.mw/index.lock` 一并拖进临界区，制造锁序与 30 s stale-steal 风险（§6）。

## 1 现状事实（逐条复看确认；`文件:行号` + 原文片段）

### 1.1 判定读快照：tick 起点读一次，在飞集合随后算出

`packages/multi-workers/autopilot/conductor.py:620`
```python
    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))
```

`packages/multi-workers/autopilot/conductor.py:698-704`
```python
    in_flight_keys = {
        key
        for key in deps_of
        if any(
            _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
        )
    }
```

`packages/multi-workers/autopilot/conductor.py:740-747`
```python
            if not _deps_satisfied(entry.depends_on, status_of):
                continue
            if key in in_flight_keys:
                continue  # wait for the in-flight worker
            if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):
                continue  # parallel cap — key starts on a later tick
            if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):
                in_flight_keys.add(key)
```

谓词本体（单源；`_is_in_flight` 用 `mw_common` 的终态集）：

`packages/multi-workers/autopilot/conductor.py:3539-3540`
```python
def _is_in_flight(row: dict) -> bool:
    return row.get("status", "") not in mw_common._TERMINAL_STATUSES  # noqa: SLF001 — same-package private (state.py precedent)
```

`packages/multi-workers/mw_common.py:168`（另见 §7 残留：同值常量在 `:2342` 重复定义）
```python
_TERMINAL_STATUSES = {"done", "failed", "needs-clarification", "lost"}
```

**关键**：`rows` 是 `orchestrate()` 开头的快照，`in_flight_keys` 是它的纯函数；判定与写行的**全部间隔**都在锁外（写行在 `_advance_key -> execute_loop -> dispatch.dispatch`）。第二个进程只要在第一个进程写行之前读完 `rows`，就会得到同一个"key 不在飞"的结论。

### 1.2 写队列的锁与覆盖语义

`packages/multi-workers/autopilot/dispatch.py:1155-1184`（关键行）
```python
    try:
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:
        return DispatchResult(
            ok=False,
            reason=f"lock-unavailable: {exc}",
            task_key=task_key,
            task_md=task_md,
            row_verified=False,
        )
    try:
        wpath.parent.mkdir(parents=True, exist_ok=True)
        ...
        mw_common.upsert_worker_row(wpath, row)
    except OSError as exc:
        return DispatchResult(
            ok=False,
            reason=f"queue-write-failed: {exc}",
            task_key=task_key,
            task_md=task_md,
            row_verified=False,
        )
    finally:
        mw_common.release_lock(lock)
```

`packages/multi-workers/autopilot/dispatch.py:1133-1137`（覆盖语义被写成"设计"）
```python
    # 2. queue row under workers.lock — upsert by task_key: replace the
    #    first existing row (a retry requeues the same identity; matches the
    #    TS-side WorkerStore.upsert, so no duplicate-key rows ever appear)
    #    or append when the key is new.
```

`packages/multi-workers/mw_common.py:2152-2172`
```python
def upsert_worker_row(path: pathlib.Path, row: dict[str, str]) -> None:
    """Insert/replace ONE row by task_key, every other line verbatim
    (AC-023) — the Python mirror of the TS ``upsert``.

    The caller owns the lock (``autopilot/dispatch.py`` takes
    ``.mw/workers.lock`` itself). An existing row is rewritten inside its own
    slot, a new one is appended; either way unparsable and legacy lines keep
    their slots, so a dispatcher write can never make a queue *look* empty.
    """
    task_key = row["task_key"]
    out: list[str] = []
    replaced = False
    for line, existing in _scan_worker_lines(path):
        if existing is not None and existing["task_key"] == task_key and not replaced:
            out.append(serialize_entry(row))
            replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(serialize_entry(row))
    _write_workers_file(path, out)
```

**结论**：锁只覆盖单次写；"是否已有在飞的同 key"没有任何一处在锁内被读过。覆盖语义把第二次写变成"第二次派发在队列里不可见"。

### 1.3 `task.md` 早于锁创建

`packages/multi-workers/autopilot/dispatch.py:1126-1132`
```python
    # 1. task.md (before the queue row — the crash gap is the orphan shape
    #    that reconciliation heals; see module docstring / D-102).
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(content, encoding="utf-8", newline="\n")
```

取锁在 `dispatch.py:1156`。即 `task_dir.mkdir`/`task_md.write_text` 与队列写**不在同一临界区**，而且比取锁早 24 行（1130/1132 vs 1156）。

### 1.4 读回校验被掩盖（实测）

`packages/multi-workers/autopilot/dispatch.py:1186-1198`
```python
    # 3. read-back verification: exactly one row with the right identity.
    row_verified = False
    matches = 0
    for queued in mw_common.parse_workers_file(wpath):
        if queued["task_key"] == task_key:
            matches += 1
            row_verified = (
                queued["task_path"] == str(task_md)
                and queued["cli"] == entry.cli
                and queued["status"] == "pending"
                and queued.get("origin") == mw_common.WORKER_ORIGIN_CONDUCTOR
            )
    row_verified = row_verified and matches == 1
```

读回发生在 `finally: release_lock` **之后**（`dispatch.py:1184` 之后）。判据只看 `task_path`/`cli`/`status`/`origin` 与 `matches == 1`，**不看 `model`，也不看写入者身份**。实测两个并发派发**都** `row_verified=True`（§4.4）。

### 1.5 PM 侧同形（判定在锁外）

`packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:153` + `190-217`（锁内只有文件 RMW）
```ts
		this.lockPath = path.join(agenticdocRoot, "..", ".mw", "workers.lock");
```
```ts
	async upsert(entry: WorkerEntry): Promise<void> {
		const release = await acquireLock(this.lockPath);
		try {
			const raw = this.readRawLines();
			const replacement = serializeWorkerLine(entry);
			const idx = raw.findIndex((line) => {
				if (line.trim() === "" || line.trimStart().startsWith("#")) return false;
				const parsed = parseWorkerLine(line);
				return parsed.ok && parsed.entry.taskKey === entry.taskKey;
			});
			let lines: string[];
			if (idx >= 0) {
				lines = raw.map((line, i) => (i === idx ? replacement : line));
			} else if (raw.length === 0) {
				lines = [QUEUE_HEADER_V2, replacement];
			} else {
				lines = [...raw, replacement];
			}
			...
		} finally {
			release();
		}
	}
```

判定在调用方：

`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1003-1015`（快照建立）
```ts
	const queue = workerStore.readQueue();
	...
	const dispatched = new Set(queue.rows.map((e) => e.taskKey));
	...
	const queueIsEmpty = queue.rows.length === 0;
```

`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1107` + `1243`
```ts
			if (dispatched.has(taskKey)) continue;
```
```ts
				await dispatchTask(
```
（`dispatchTask` -> `store.upsert`，`pm/task-dispatcher.ts:288-300`）

`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2342-2343`（`/worker` 的幂等令牌是目录存在性）
```ts
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
			if (fs.existsSync(taskDir)) {
```

`ui-bridge.ts:2178-2179`（`writeDispatchTaskMd` 内 mkdir）与 `ui-bridge.ts:2440`（之后才 `dispatchTask`）说明 PM 通道**同样是"先建 task.md、后进队列锁"**。

### 1.6 锁的身份：同一文件

`packages/multi-workers/mw_common.py:1731-1732`
```python
def lock_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / "workers.lock"
```

`packages/coding-agent/src/extensions/agent-team-loop/shared/paths.ts:22-24` + `worker-store.ts:153`
```ts
export function agenticdocRoot(projectDir: string): string {
	return path.join(projectDir, AGENTICDOC_DIR);
}
```
=> TS `lockPath = <projectDir>/.agenticdoc/../.mw/workers.lock` = `<projectDir>/.mw/workers.lock`，与 Python 同文件。

同文件上其实有**两套协议**：

`packages/multi-workers/autopilot/conductor.py:165-166`
```python
def lock_file(project_root: pathlib.Path, name: str) -> pathlib.Path:
    """Named conductor lock: workers / gates / roadmap / key-{key}."""
    return pathlib.Path(project_root) / ".mw" / f"{name}.lock"
```
即 `lock_file(root, "workers")` = `.mw/workers.lock`，被 `reconcile_orphans` 用（`conductor.py:6146` `acquire_conductor_lock(project_root, "workers", st.timeline)`）。该协议带 stale steal：

`packages/multi-workers/autopilot/conductor.py:109`
```python
STALE_LOCK_AGE_SEC = 30.0
```
`packages/multi-workers/autopilot/conductor.py:170-183`
```python
def acquire_conductor_lock(
    project_root: pathlib.Path,
    name: str,
    tl: timeline.Timeline,
    *,
    stale_after: float = STALE_LOCK_AGE_SEC,
) -> None:
    """Acquire ``.mw/{name}.lock`` with stale steal (D-113).

    Fast acquire first; on exhaustion the lock file's age decides: older than
    ``stale_after`` — the holder is dead (conductor holds are milliseconds) —
    steal it (unlink + re-acquire) and record a timeline ``config`` event;
    younger — :class:`ConductorLockHeld` (a live holder — defer, never
    clobber). ...
```

而 `mw_common.acquire_lock` **没有** stale steal（`mw_common.py:2114-2128`）：
```python
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
```
`sum(0.05 * 2**k for k in range(20)) = 52428.75` 秒 ≈ 14.6 小时。

### 1.7 在飞谓词的全部落点（同一谓词，共 12 处调用，1 处定义）

命令：`Select-String -Path packages/multi-workers/autopilot/conductor.py -Pattern "_is_in_flight\("`
```
702: _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
1189: r["task_key"] == info.task_key and _is_in_flight(r) for r in rows
1289: _is_in_flight(row) and _row_belongs_to(row, e.key)
1770: if any(_is_in_flight(r) for r in fam):
2366: if any(_is_in_flight(r) for r in rows if r["task_key"].startswith(prefix)):
2556: if any(_is_in_flight(r) for r in fam):
3001: if key and any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):
3539: def _is_in_flight(row: dict) -> bool:
4109: if not any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows)
4995: pat.match(str(row.get("task_key", ""))) and _is_in_flight(row)
6990: _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
7988: if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):
```

其中与 RQ-D3 直接相关的是写路径上的一处（`742`，由 §1.1 覆盖）与三处只读消费者（`1289`/`3001`/`7988`，§6）。

## 2 临界区边界设计（RQ-D3 #1）

### 2.1 谁持锁：**dispatch 内部（写方）**，不是调用方

先给"调用方持锁"的反证。`dispatch()` 内部无条件取同一把锁（`dispatch.py:1156`）。若调用方（`orchestrate` 的 key 循环）先取 `.mw/workers.lock` 再调用 `dispatch.dispatch`，则内层 `os.open(..., O_CREAT|O_EXCL)` 抛 `FileExistsError`，进入 20 次指数退避：`0.05 * 2**0 .. 0.05 * 2**19`，累计 `52428.75` s ≈ **14.6 小时**，然后 `RuntimeError("Could not acquire lock ... after 20 retries")`（`mw_common.py:2114-2126`）。即调用方持锁在当前实现下就是**确定性死等**，不是"慢一点"。

再把"谁最该持锁"落到最小改动面：14 个 conductor 派发点全部经由一个函数。

命令：`Select-String -Path packages/multi-workers/autopilot/conductor.py -Pattern 'dispatch\.dispatch\(' -Context 0,1`（输出行号）
```
1196:    result = dispatch.dispatch(
1605:        result = dispatch.dispatch(
1643:        result = dispatch.dispatch(
1679:    result = dispatch.dispatch(
1788:        result = dispatch.dispatch(
2369:        result = dispatch.dispatch(
2419:            result = dispatch.dispatch(
2454:        result = dispatch.dispatch(
2486:            result = dispatch.dispatch(
2526:                result = dispatch.dispatch(
2571:        result = dispatch.dispatch(
2579:    result = dispatch.dispatch(
5098:    result = dispatch.dispatch(
```
（`Select-String` 计 13 行命中；加 `_roadmap_writer` 之外另有 `dispatch.dispatch` 在 `dispatch.py` 自身的入口——**入口唯一**这一结论不受影响：所有 13 处都调 `dispatch.dispatch`。）

**结论**：把判定放进 `dispatch()` 已有临界区，等于一次改动覆盖全部 13 个派发点；调用方无需取锁、无需传锁、无需 reentrancy。调用方现有的 `if key in in_flight_keys: continue`（`conductor.py:742`）保留为**廉价预筛**（读快照，允许假通过），权威判定只发生在锁内。

### 2.2 最小改动形状（伪码级）

```python
def dispatch(project_root, owner, stem, ...) -> DispatchResult:
    # ---- 锁前：全部纯计算 + 全部拒绝路径（保持现状，零副作用）----
    task_key = task_key_for(owner, stem)
    task_dir = project_root / ".agenticdoc" / owner / "workers" / task_key
    run_status = mw_common.read_run_status(task_dir)            # AC-004
    ... entry/scope/config/profile/rag/card/content 全部门禁与渲染 ...
    row = {..., "task_path": str(task_dir / "task.md"), "origin": WORKER_ORIGIN_CONDUCTOR}
    wpath = mw_common.workers_path(project_root)
    lock = mw_common.lock_path(project_root)

    # ---- 临界区（唯一一次取锁）----
    try:
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:
        return DispatchResult(ok=False, reason=f"lock-unavailable: {exc}",
                              task_key=task_key, task_md=None, row_verified=False)
    try:
        # (1) 锁内读：与写共用同一份行视图
        rows = mw_common.parse_workers_file(wpath)
        # (2) 锁内判：同 identity 且非终态 == 已有在飞
        if any(r["task_key"] == task_key
               and r.get("status", "") not in mw_common._TERMINAL_STATUSES
               for r in rows):
            return DispatchResult(ok=False,
                                  reason=f"already-in-flight:{task_key}",
                                  task_key=task_key, task_md=None, row_verified=False)
        # (3) 判定通过后才产生副作用
        task_dir.mkdir(parents=True, exist_ok=True)
        task_md = task_dir / "task.md"
        task_md.write_text(content, encoding="utf-8", newline="\n")
        row["dispatched_at"] = row["updated_at"] = mw_common.iso_now()
        wpath.parent.mkdir(parents=True, exist_ok=True)
        mw_common.upsert_worker_row(wpath, row)
    except OSError as exc:
        return DispatchResult(ok=False, reason=f"queue-write-failed: {exc}",
                              task_key=task_key, task_md=None, row_verified=False)
    finally:
        mw_common.release_lock(lock)

    # ---- 锁后：读回校验（可保留；见 §2.6）----
    ...
```

要点：
- 临界区里只多了 **一次整文件读**（0.39 ms / 426 行，实测 §5）。
- 判定谓词建议抽到 `mw_common`（新函数，例如 `task_in_flight(rows, task_key) -> bool`），让 Python 侧只有一处"非终态"定义；`conductor._is_in_flight`（`conductor.py:3539`）保持对 `mw_common` 的委托风格不变。
- **不要**在锁内重算 `in_flight_keys` 集合（那是 key 级策略，见 §2.5、§5）。
- 读回校验仍在锁外（`dispatch.py:1184` 之后）。若把"读"放进锁内，就可以顺带把读回也变成"同一次锁的同一份视图"，但这不是重复派发防护的必要条件；建议只在 EXECUTE 阶段做（可少一次整文件读）。

### 2.3 共用一把锁，而不是"每 key 一把锁"

理由（按强度排序）：
1. **保护对象是整文件**：`_workers.parallel` 的每次写都是"全量读行 → 改一行/追加一行 → 整文件 tmp+replace"（`mw_common.py:2152-2172`、`_write_workers_file`）。per-key 锁下两个写者会**同时**全量重写，最后落盘者丢掉另一个 key 的行——正是 AC-023/IN-3 要防的"队列看起来空了一截"。
2. **锁已经存在且已经共用**：Python `mw_common.lock_path`（`mw_common.py:1731-1732`）与 TS `WorkerStore.lockPath`（`worker-store.ts:153`）解析到同一个 `.mw/workers.lock`；`reconcile_orphans` 也在这条路径上（`conductor.py:6146` 经 `lock_file(root,"workers")`，`conductor.py:165-166`）。引入第二把锁只会制造两个互不协调的互斥域。
3. **跨通道协调是目的本身**：PM（`manual` origin）与 conductor（`conductor` origin）写**同一个任务命名空间**；用同一把锁才能让"手动已排队的同 task_key"拦住 conductor 的重复派发。per-key 锁虽然同 key 也能互斥，但理由 1 已经否掉它。

### 2.4 PM 侧 `WorkerStore.upsert` 是否已经满足：**否**

它满足的部分：文件 RMW 在 `acquireLock(this.lockPath)` 内（`worker-store.ts:190-191`），且 lock 路径与 Python 同文件（`worker-store.ts:153`）。
它不满足的部分：**没有任何"在飞"判定在锁内**。判定分别在：
- `pm-orchestrator.ts:1012`（`dispatched` 集合来自扫描起点 `readQueue()`，`1003`）→ 扫描期间的并发派发不可见；
- `ui-bridge.ts:2342-2343`（`fs.existsSync(taskDir)`）→ 纯 TOCTOU，两进程可同时通过；
- `ui-bridge.ts:2178-2179` / `2440`（先 mkdir+write，后 upsert）→ 判定与写在锁的两侧。

最小改法（两处即可）：给 `WorkerStore` 增加一个"锁内判定 + 锁内产生 task.md"的入队方法，`upsert` 保持原语义不动（避免动 AC-023 的既有测试）：

```ts
export type EnqueueResult = { ok: true } | { ok: false; reason: string };

async enqueue(entry: WorkerEntry, produce: () => string): Promise<EnqueueResult> {
  const release = await acquireLock(this.lockPath);
  try {
    const raw = this.readRawLines();
    const dup = raw.some((line) => {
      const parsed = parseWorkerLine(line);
      return parsed.ok && parsed.entry.taskKey === entry.taskKey
        && !TERMINAL_WORKER_STATUSES.has(parsed.entry.status);
    });
    if (dup) return { ok: false, reason: `already-in-flight:${entry.taskKey}` };
    const taskPath = produce();           // mkdir + task.md，锁内、判定之后
    entry.taskPath = taskPath;
    ... existing read-modify-write of `lines` ...
    return { ok: true };
  } finally { release(); }
}
```
调用点收敛为 3 处：`pm-orchestrator.ts:1243`（后台扫描）、`ui-bridge.ts:2440`（`dispatch_worker` 工具）、`ui-bridge.ts:2935`（`/worker` 命令）；同时把 `ui-bridge.ts:2343` 的 `fs.existsSync(taskDir)` 判定收进 `produce`（或删除，由队列判定取代）。

### 2.5 谓词语义：identity 级（同 `task_key`），不是 key 级

- 锁内判据必须是 **`r["task_key"] == task_key` 且 `status` 非终态**。这是"同一件事不派两次"的充要条件。
- **不能**把 key 级在飞计数（今天的 `in_flight_keys`/per-key serial）搬进锁内：设计 D-102 要放开"同 key 多 worker"（新键 `max_workers_per_key`，`design.md` D-102），锁内若按 key 拦，就把要放开的并发自己关死了。
- key 级计数继续用调用方快照：多算 = 少起一个（保守，只会延后）；少算 = 多起一个**不同 task_key** 的 worker（正是 D-102 想要的），而"同 task_key 双写"由 identity 级判据兜住。
- 拒绝原因用稳定前缀 `already-in-flight:<task_key>`，便于调用方与测试做**可证伪断言**（§2.6）。

### 2.6 调用方必须配合（否则修复会变成误伤）

今天有两个 `ok=False -> mark_stalled` 的分支：
- `conductor.py:1686-1693`（L2 verifier 派发失败 → `reason_code="l2-dispatch-refused"`）
- `conductor.py:1793-1800`（exec 派发失败 → `reason_code="exec-dispatch-refused"`）

修复后，**抢输锁的进程**会拿到 `ok=False, reason="already-in-flight:..."`；若按现状处理，这次"正常抢输"会被升级成 key stalled（人审 gate），代价远大于少派一次。最小配合（二选一）：
- (a) 这两处先判 `result.reason.startswith("already-in-flight:")` → 只写一条 trace（或 `skip` 事件）并 `return False`：不吃 round、不 stall；
- (b) 给 `DispatchResult` 增加布尔字段 `duplicate: bool`，调用方按字段分流（更清晰，但要改 5 处构造点与冻结契约测试）。

其余 11 个派发点对 `ok=False` 的反应是 trace / `return result.ok`，不升级（例如 `conductor.py:1204-1208`、`1610`、`2376`、`2426`），无需逐个改。

### 2.7 选项 C（调用方持锁 / prepare-commit 拆分）与选项 A 的取舍

选项 A（本设计）：dispatch 内部持锁，锁内多做"读 + 判"。改动面 = `dispatch.py` 一个函数 + `mw_common` 一个谓词；13 个调用点零改动（除 §2.6 的两处拒绝分流）。

选项 C：把 `dispatch()` 拆成 `prepare()`（纯函数：门禁 + 渲染 + `row`，不写盘）与 `commit()`（假设调用方已持锁：mkdir/write_text/upsert），调用方 `orchestrate` 变成"取 `.mw/workers.lock` → 锁内重读队列 → 锁内重算在飞集合 → 对候选 key 逐个 prepare+commit → 释放"。否掉理由：

1. 临界区从"单次派发"变成"整个 key 循环"，含多条 prepare（渲染 + RAG block + 配置读）与 timeline 写；426 行实测单次 upsert 已 1.18 ms，一个 key 循环会把锁持有时间放大一个数量级以上，逼近 §5.3 的 stale-steal 余量讨论区。
2. 要保持"per-key serial + cap"语义就必须在锁内重算 `in_flight_keys`（key 级，0.85 ms / 35 key × 426 行），把 key 级策略拖进临界区——§2.5 明确反对。
3. `prepare()` 含 `dispatch()` 现存的全部文件 IO 门禁（`mw_common.read_run_status`、`load_target_config`、`load_rag_config`），进锁等于让一把队列锁承担配置/产品状态的读延迟。
4. 拆分要重定义 `DispatchResult`/`task_md` 的"prepare 失败 vs commit 失败"语义，选项 A 不需要。

结论：选 A（dispatch 内部持锁）。
## 3 `task.md` 先于锁创建：牵动面与最小改法（RQ-D3 #2）

### 3.1 今天的事实

`dispatch.py:1126-1132` 的 mkdir/write_text 位于取锁（`1156`）之前；`task_dir` 本身在函数开头就算出（`dispatch.py:995`，注释明说"creating it still happens after every rejection below"）。

### 3.2 牵动清单

| # | 受影响点 | 是否牵动 | 依据 / 最小改法 |
|---|---|---|---|
| 1 | `dispatch_card()` 返回值 | **否** | `dispatch.py:556-587` 只读 `<key>/tasks/<stem>.md`（`card_file = pathlib.Path(project_root) / ".agenticdoc" / owner / card_path`），不读 task_dir；`extras`/`worker_dir` 都是字符串 |
| 2 | `card_path:` / `card_sha256:` 记录 | **否** | 两者是 `render_task_md` 写进 `content` 的头部行（`dispatch.py:826-830`），`content` 在锁前已算好；锁内只多一次 `write_text` |
| 3 | `row["task_path"]` | **否** | 路径是确定式（`task_dir = project_root/.agenticdoc/<owner>/workers/<task_key>`，`dispatch.py:995`） |
| 4 | `DispatchResult.task_md` | **是** | 今天 `lock-unavailable` 返回已建的 `task_md`，docstring 明说"leaves the orphan shape on purpose"（`dispatch.py:934-951`）；移进锁后该路径只能返回 `None` → 同步改 docstring（`934-951`）与该路径的断言 |
| 5 | 孤儿 reconcile | **语义不变** | 自愈的是"task.md 在、行不在"：`state.find_orphans`（docstring: "Conductor-origin task.md files with no live queue row"）+ `conductor.reconcile_orphans`（`6132-6179`，含 `:6146` 取 `workers` 锁）。移进锁后窗口变小、形状不变；dup 拒绝路径**不产生**孤儿（副作用在判定之后） |
| 6 | PM 侧 `ui-bridge` taskDir 创建 | **是（必须同波）** | `ui-bridge.ts:2178-2179` mkdir + `2424` writeDispatchTaskMd + `2440` dispatchTask；见 §2.4 的 `enqueue(produce)` |
| 7 | taskDir 当幂等令牌 | **是（改善）** | `ui-bridge.ts:2342-2347`：被拒绝的派发不再留下目录，误报"already exists"消失 |

### 3.3 最小改法：拒绝路径零副作用

1. 把 `1128-1132`（注释 + mkdir + write_text）**整块**剪到锁内、dup 判定**之后**、`upsert_worker_row` **之前**。
2. `lock-unavailable`（`1157-1164`）与 `queue-write-failed`（`1175-1182`）的 `task_md=task_md` 改为 `task_md=None`；`DispatchResult` docstring（`934-951`）同步改写为"拒绝路径零副作用；锁内崩溃留下的孤儿由 reconcile 自愈"。
3. 调用方无需改：13 处 `dispatch.dispatch` 调用点**无一处**读 `result.task_md`（命令：`Select-String -Path packages/multi-workers/autopilot/*.py -Pattern '\.task_md'` 只命中 `dispatch.py` 自身 `1003/1163/1181/1187/1192/1198/1207`）。
4. 测试面：`test_autopilot_dispatch.py` 的 `assert result.task_md is not None` 只出现在成功路径（`165/370/402/447/475/504/514/537`），不受影响；需新增"**被拒绝时不建目录**"断言（见 §4.6）。
5. "零副作用"的边界要说清：新路径下，`run-terminal`/`unknown-type`/`read-scope`/`target-config-unusable` 与新增的 `already-in-flight` **都不创建目录**；只有 `lock-unavailable` 之后的失败（`queue-write-failed`）与"写 task.md 后进程被杀"会产生孤儿，交给 reconcile——与今天同形。

## 4 重复派发防护的可证伪对拍（RQ-D3 #3）

### 4.1 先修正判据：**行数不是判据**

今天 `upsert_worker_row` 是"按 `task_key` 覆盖"（§1.2），所以无论派发多少次，队列里该 key **恒为 1 行**。因此"同 task_key 只 append 一行"不能被字面地当作可观测判据。可证伪的判据必须落在**调用结果**与**审计事件**上：

| 判据 | 观测点 | 今天（bug） | 修后（目标） |
|---|---|---|---|
| **J1** 唯一授权 | `DispatchResult.ok is True` 的并发调用数 | **2** | **1** |
| **J2** 唯一审计 | timeline `dispatch` 事件数（`dispatch.py:1200-1205` 只在成功时写） | **2** | **1** |
| **J3** 队列守卫 | 同 `task_key` 行数 | 1（今天也 1 → 单独无判别力，仅作守卫） | 1 |
| **J4** 归属一致 | 存活行的 `model` 是否等于唯一 `ok=True` 调用的 model | 否（行里是**后写者**，先写者的派发不可见） | 是 |
| **J5** 读回校验 | `row_verified` | 两个并发调用**都 True**（§1.4 的被掩盖证据） | 唯一授权者 True |

### 4.2 方案 A：双进程 direct 对拍（本机可跑，已跑）

脚本：`.agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/mw-race.py`（`direct` 模式）

```
两个 python 子进程，每个执行：
  1. snapshot = [r.task_key for r in parse_workers_file(_workers.parallel)
                 if _is_in_flight(r) and _row_belongs_to(r, "k1")]   # 调用方的判定（锁外）
  2. rendezvous（各自写 race/<tag>.ready，等对方也 ready）          # 保证两个判定都发生在任何写之前
  3. dispatch.dispatch(project_root, "k1", "T-01-first", "phase-writer", prompt,
                       loop="exec:k1:T-01-first", attempt=1,
                       model="race-model-A"|"race-model-B",
                       timeline=Timeline(...))
  4. print(json.dumps({ok, reason, model, row_verified}))
driver 统计：J1/J2/J3/J4
```

命令：
```bash
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/mw-race.py direct
```

### 4.3 方案 B：双进程 `conductor.tick` 对拍（走真入口，已跑）

脚本同一文件的 `tick` 模式：

```
两个 python 子进程，每个执行：
  1. monkeypatch dispatch.dispatch 为 slow（真实调用前 sleep 1.5s）  # 把"判定与写入"的窗口拉大
  2. rendezvous
  3. conductor.tick(project_root, ConductorState(...))               # 真 orchestrate 路径
driver 统计：tick 返回值 / dispatch 事件数 / 行数
```

命令：
```bash
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/mw-race.py tick
```

### 4.4 今天实测（复现成功）

方案 A（3 连跑，结论一致）：
```
MODE: direct
  stdout: {"tag": "A", "mode": "direct", "snapshot": [], "ok": true, "reason": "", "model": "race-model-A", "row_verified": true, ...}
  stdout: {"tag": "B", "mode": "direct", "snapshot": [], "ok": true, "reason": "", "model": "race-model-B", "row_verified": true, ...}
tally: {"queue_rows_for_key": 1, "row_models": ["race-model-A"], "rows_total": 1, "dispatch_events": 2, "task_md_exists": true}
```
- `snapshot: []` 两边都为真 → 两个进程都"合法地"判定该 task 不在飞。
- J1=2（两个 `ok=true`）、J2=2、J3=1、J4 失败（存活行只有一个 model）、J5=2（两个都 `row_verified=true`）。

方案 B（真入口）：
```
MODE: tick
  stdout: {"tag": "A", "mode": "tick", "tick": "ok", "model": "race-model-A"}
  stdout: {"tag": "B", "mode": "tick", "tick": "ok", "model": "race-model-B"}
tally: {"queue_rows_for_key": 1, "row_models": [""], "rows_total": 1, "dispatch_events": 2, "task_md_exists": true}
```
- 两个 `conductor.tick` 各自 dispatch 了同一个 `ap-k1-T-01-first`：timeline 2 条 `dispatch`、队列 1 行。
- 这就是 issue 主句的"两个进程可同时通过判定 → 同一 task_key 双写，且覆盖语义把第二次写掩盖"的**直接复现**。

顺序形态（无并发，最简回归锁）：
```
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/seq.py
{"results": [{"call": "A", "ok": true, "reason": "", "model": "race-model-A"},
             {"call": "B", "ok": true, "reason": "", "model": "race-model-B"}],
 "queue_rows_for_key": 1, "row_models": ["race-model-B"], "dispatch_events": 2}
```
同一个 `(owner, stem)` 连派两次，今天**两次都成功**（第二次把第一次的行覆盖掉）。

### 4.5 修后期望（临界区形状**原型**实测）

只读角色不能改生产代码，因此做了一个形状原型（`_scratch-rq-d3-race/fixed.py`）：同样的 rendezvous，但每个子进程自己做"(取 `.mw/workers.lock` → 锁内 `parse_workers_file` → 判同 key 非终态 → 拒绝 / 否则 mkdir+task.md+`upsert_worker_row`) → 释放"。**这是形状原型，不是补丁验证**；补丁验证属 EXECUTE（VC-106）。

5 连跑：
```
tally: {"grants": 1, "refusals": 1, "queue_rows_for_key": 1, "row_models": ["race-model-B"], "rows_total": 1}
```
（5 次全部 `grants:1 / refusals:1 / rows:1`；被拒者 `reason="already-in-flight:ap-k1-T-01-first"`。）

对照：方案 A（判定在锁外）→ `grants:2 / rows:1`；原型（判定在锁内）→ `grants:1 / rows:1`。**唯一变量就是判定相对锁的位置**。

### 4.6 CI 友好的测试形状（无 sleep、无多进程）

1. **顺序回归（必加，最小）**：同一 `(owner, stem)` 连调 `dispatch.dispatch` 两次 → 第二次必须 `ok is False` 且 `reason.startswith("already-in-flight:")`；断言 `len(rows)==1`、`dispatch` 事件 ==1。今天该断言**必然失败**（§4.4 的 seq 实测两条都 ok），修后必过。
2. **真并发（建议加）**：`subprocess`/`multiprocessing` 两个进程 + 文件 rendezvous（不要在测试里 `sleep`）；断言 J1/J2/J3；加一个反向断言"若把 dup 判定挪到锁外，J1 变 2"（可用 monkeypatch 一个 `_outside_lock_check` 变体做对照，或直接以本条 §4.4 输出作为 bug 存在性证据）。
3. **锁内原子性（可选，白盒）**：monkeypatch `mw_common.parse_workers_file` 让第一次调用在返回前写入 `threading.Event` 并等待另一个线程的 Event（把窗口拉出来），验证第二个调用在被阻塞期间无法通过判定——比 `sleep` 确定。
4. 落点建议：`packages/multi-workers/test_autopilot_dispatch.py` 新增顺序回归；并发对拍放 `test_autopilot_dispatch_race.py`（或复用本 RQ 的脚本骨架）。测试必须用最小 fixture 树（`_autopilot/config.json` + `_index.parallel` + `_roadmap.md` + `tasks/<stem>.md`，见 §9），不要碰真项目 `.agenticdoc/`。

### 4.7 边界用例（必须与主判据一起锁住）

| 用例 | 期望 | 依据 |
|---|---|---|
| 同 key，行已终态（`failed`） | **允许**（今天 retry 语义） | `_TERMINAL_STATUSES`（`mw_common.py:168`） |
| 同 key，行 `origin: manual` 且在飞 | **拒绝**（跨通道防重；origin 不参与本判据） | §2.3 理由 3 |
| 同 key，行 `pending` 但 worker 已死 | **拒绝**（fail-closed；由 launcher reap / `_reconcile_orphans` 收敛，不由第二轮派发绕过） | `launcher.py:1805-1810`（按 status==pending 取行）、`launcher.py:2017`（spawn 后置 running）、`launcher.py:1451`（_reconcile_orphans） |
| 同 key 不同 attempt（`-a2`） | **允许**（identity 不同） | `conductor.py:1787`（`stem_arg`） |
| L3 reprompt 的**同 key** 重派 | 前一轮行须为终态；仍是 `pending/running` 时 `conductor.py:2556` 的 `fam` 检查先返回 | `conductor.py:2549-2571` |
| 同 key 有不可解析行（10 列） | 今天无判据；建议判据用与 conductor 同源 reader，`unparsable` 盲区记入残留（§7） | `WORKER_COLS_MAX = 9`（`mw_common.py:1739`） |

## 5 锁粒度与吞吐（RQ-D3 #4）

### 5.1 实测（本机；真实 426 行队列，只读复制到 scratch 后计时）

`python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/bench.py` / `bench2.py`

| 量 | 实测（中位） | 说明 |
|---|---|---|
| 队列行数 / 文件行数 | **426 / 426** | `.agenticdoc/_workers.parallel`（无注释、无不可解析行） |
| 队列 owner key 数 | **35** | 供 key 级重算合成 `deps_of`（真项目无 `_roadmap.md`，见 §7） |
| `mw_common.parse_workers_file` | **0.3941 ms** | 整文件解析（锁内新增的那一次读） |
| `mw_common._scan_worker_lines` | **0.3734 ms** | upsert 内部的行槽扫描 |
| `in_flight_keys` 全量重算（35 key × 426 行，全部非终态即最坏、不短路） | **0.8498 ms** | key 级策略，**建议不进锁** |
| `upsert_worker_row`（426 行；今天就已在锁内） | **1.1833 ms** | 读+改+tmp+`os.replace` |
| 锁内 dup 检查 + upsert（新形状） | **1.9442 ms** | 边际 **+0.76 ms** |
| `serialize_entry` | **0.0003 ms** | 单行 |

`launcher.py:51`：`DEFAULT_POLL_INTERVAL: int = 5`。launcher 的每次 `update_status`（`mw_common.py:2175`）本来就整文件读+写并已持同一把锁，`archive_stale_entries`（`mw_common.py:2213`）也是。把 **+0.76 ms** 加到同一条锁上，在 5 s 周期、默认 8 worker 的规模下无实质影响（占空比 < 0.02%）。

**结论：可接受**，前提是锁内只做"**同 `task_key` 单趟判定**"（O(rows) 单次 pass，≈0.39 ms），**不要**在锁内重算 `in_flight_keys`。

### 5.2 若不可接受时的更小临界区（本 RQ 已选择的就是最小形状）

1. **锁内只留精确判定**（本设计）：锁内 = `parse_workers_file` + 单 key 判定 + `upsert_worker_row`；key 级计数留在调用方快照。复杂度 O(rows)，无二次项。
2. 若队列再涨一个数量级（例：4000 行 / 400 key），最坏 O(rows) 变成 ~4 ms，仍可接受；此时若要再省，可把"读"改为 `read_workers_file_lines` + 单行 `parse_worker_line` 的短路扫描（找到同 key 非终态即停），避免全量 dict 构造。
3. **明确否掉**"把整 tick 放进锁"：那会把 `_stage_closure` 的 roadmap/evidence 读、`advance.advance()` 子进程、timeline 写、以及 `defer_key_to_review` 的 `.mw/index.lock`（`index_parallel.py:66-68`、`198`）全都卷进 `.mw/workers.lock`，既是吞吐灾难，也引入两把锁的锁序问题。

### 5.3 两条硬约束

1. **临界区必须远小于 `STALE_LOCK_AGE_SEC = 30.0` s**（`conductor.py:109`）：`acquire_conductor_lock` 在同一个 `.mw/workers.lock` 上做 stale steal（`conductor.py:170-183`），临界区一旦超过 30 s 就会被"偷锁"，互斥失效。毫秒级设计有 4 个数量级余量。
2. **`mw_common.acquire_lock` 没有 stale 恢复**（`mw_common.py:2114-2128`）：持锁进程在临界区内崩溃会留下 `.mw/workers.lock`，之后所有写者退避累计 ≈14.6 h 才报 `RuntimeError`。这是**既有**缺陷，不是本改动引入；但临界区变长会把崩溃窗口放大。建议单独立项（pid+age 判活 steal），本 RQ 不引入新锁协议。

## 6 与 stage 关闭 / 提醒抑制的交互（RQ-D3 #5）

### 6.1 三处落点与原文

`_stage_closure` 定义 `conductor.py:1264`，判定在 `1288-1293`：
```python
    if rows is not None and any(
        _is_in_flight(row) and _row_belongs_to(row, e.key)
        for row in rows
        for e in stage.keys
    ):
        return  # an in-flight worker still owns a key of this stage
```

`pending_gate_reminders` 定义 `conductor.py:2950`，判定在 `3001-3004`：
```python
        if key and any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):
            if silenced is not None:
                silenced.append((gate, n, _SUPPRESS_KEY_IN_FLIGHT))
            continue
```

`_defer_declined_gate` 定义 `conductor.py:7940`，判定在 `7983-7988`：
```python
            rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))
        except OSError:
            rows = []
        if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows):
            return None  # a live worker still owns the key: case 3 this tick
```
注意 `_defer_declined_gate` **自己原地重读**队列（`7984`），但这次读同样在**任何锁之外**。

### 6.2 结论：三处保持读快照判定，不进 `.mw/workers.lock`

1. **它们不创建队列行**，因此不可能是"重复派发"的成因。锁要保护的不变量是"判定 → 创建行"的原子性；给只读判定加锁是防护错位。
2. **失败方向有界，且偏保守**：
   - `_stage_closure`：快照"多读"→ 推迟关 stage（保守）；快照"漏读刚派发的行"→ 提前关 stage。但能走到闭包判据的前提是该 stage 所有 key 在 `status_of` 里已终态，而派发器对终态 key 直接跳过（`conductor.py:731-733` 的 `_DISPATCH_SKIP_STATUSES` 闸，先于在飞判定）——所以"终态 key + 在飞 worker"是本就不该出现的组合，不是本窗口新引入的。
   - `pending_gate_reminders`：漏读 → 多提醒一次；提醒有 `max_reminders` 上限（`conductor.py:3005-3008`），且它只是通知，不改状态。
   - `_defer_declined_gate`：唯一带写动作的（见 6.3）。
3. **进锁的代价远大于收益**：这三处嵌在 `auto_decide_gates` / stage 循环 / reminder 计算里；进锁会把 roadmap 读、gates 枚举、timeline 写、以及 `defer_key_to_review -> index_parallel._mutate` 的 `.mw/index.lock`（`index_parallel.py:185-198`）一起卷进 `.mw/workers.lock`，同时产生 **workers.lock → index.lock** 的锁序，并放大 §5.3 的 30 s stale-steal 风险。

### 6.3 `_defer_declined_gate` 的例外讨论（建议：不改，只写注脚）

它今天在锁外自读队列（`7983-7988`）后走 `defer_key_to_review`（`7996`）→ `.mw/index.lock` 内改 key-status。它引入的不是"任务重复执行"，而是**"worker 在跑、key 被标 pending-review"的状态竞争**。两个选项：
- **保持快照（本 RQ 建议）**：窗口毫秒级；`defer_key_to_review` 自身有 `already_parked` 幂等分支（`7993-7994`）与写后回读（`7997-8002`），后续 `_apply_review_decisions` / stalled 流程会纠偏。风险 low。
- 若要收紧：在 `defer_key_to_review` 的 `.mw/index.lock` 临界区**内**重读队列并重判（只持 index.lock，不嵌套 workers.lock）。
建议落进 `design.md §3.3`：**唯一进锁点是写路径（dispatch）；其余消费者保持快照**，理由如上。

## 7 残留与未验证

1. **同值常量重复定义**：`_TERMINAL_STATUSES` 在 `mw_common.py:168` 与 `mw_common.py:2342` 各定义一次（值相同）。模块执行后 `mw_common._TERMINAL_STATUSES` 取的是 `:2342`；`conductor._is_in_flight`（`conductor.py:3539`）用它。建议合并为单源，否则未来改一处会让"在飞"口径分叉（D-106 明确要求单源）。
2. **本机无真 roadmap**：仓库根的 `.agenticdoc` 下没有 roadmap 文件（`roadmap.load_roadmap` 抛 `RoadmapError: roadmap file not found`，命令与输出见 §9），因此 §5 的 `in_flight_keys` 用队列 owner key 合成 `deps_of`（35 key）。这只影响该条的耗时估计量级，不影响结论；如需真实数据，EXECUTE 可在有 roadmap 的项目上复测。
3. **补丁未落地**：只读角色不允许改 `dispatch.py`，所以"修后 J1=1 / J2=1"来自 **形状原型**（§4.5），不是生产补丁的验证。生产补丁的断言必须由 EXECUTE 的 VC-106 补上（顺序回归 §4.6-1 必过、并发对拍 §4.6-2 必过）。
4. **PM 侧接口只是草案**：`enqueue(produce)` 未编译、未跑 TS 测试；TS 侧今天**没有** worker 终态集（`worker-store.ts` 的 `WorkerStatus` 是字符串联合，未导出 Python `_TERMINAL_STATUSES` 的镜像），落地时要新增单源常量并与 Python 做 parity。
5. **"同 key 覆盖 = retry 语义"的假设**：`dispatch.py:1133-1137` 把覆盖写成 retry 设计。逐点复查 13 个调用点（§2.1 命令）后，**未找到**任何依赖"同 `(owner, stem)` 覆盖"且同 identity 重复派发的调用点——stem 都随 attempt/round 变化（`-a2`、`l3-a{n}`、`repair-a{n}`）。唯一同 key 重派是 L3 reprompt（`conductor.py:2526`），其前置 `fam` 在飞检查（`conductor.py:2556`）已保证前一轮终态。若 EXECUTE 引入"同 identity 重试"，需显式放行（例如 `allow_replace=True`）。
6. **未跑既有测试**：只读角色 + "禁止跑测试写快照"的约束下没有执行 pytest。因此"锁内拒绝不会打破既有 dispatch/conductor 测试"只是逐条静态复查（`test_autopilot_dispatch.py` 的 `task_md is not None` 断言命中的都是成功路径），未执行验证。命令：`Select-String -Path packages/multi-workers/test_autopilot_dispatch.py -Pattern 'task_md is not None'`（命中 165/370/402/447/475/504/514/537 行）。
7. **launcher 二次 spawn 未实地复现**：机制可读——launcher 按 `status == "pending"` 取行（`launcher.py:1805-1810`），spawn 后置 `running`（`launcher.py:2017`）；若第二次派发把行覆写回 `pending`，该行在进程 reap 后（`running_procs` 已弹出）可被再次 spawn。本 RQ 没有起真 launcher 复现该 amplify 路径（复现成本高、且 J1/J2 已经是同一根因的直接证据）。
8. **文件锁的平台语义未验证**：`O_CREAT|O_EXCL` 在 NFS/SMB 上的原子性依赖服务端；本机是 Windows + 本地盘。跨机场景未覆盖。

## 8 未覆盖面声明

- **不改生产文件**：本 RQ 全程只读（新增文件仅 2 类：本证据文件 + `evidence/_scratch-rq-d3-race/` 下的临时脚本与 scratch 项目）。
- **未覆盖**：`packages/coding-agent` TS 侧的编译/测试；`enqueue(produce)` 只是接口草案。
- **未覆盖**：`.mw/workers.lock` 的 stale-steal 协议统一（§5.3 的既有缺陷，明确排除在本 key 外）。
- **未覆盖**：跨主机/跨机共享文件系统；本 RQ 只覆盖同机多进程。
- **未覆盖**：`max_workers_per_key`（D-102）落地后的 per-key 槽位语义；本 RQ 只声明"锁内判据必须是 identity 级"，不设计 key 级计数。
- **未覆盖**：`advance.advance()` 的 tick stall 量化（D-107/RQ-D5）。

## 9 复现命令与产物

```bash
# 1) 双进程 direct 对拍（判定在锁外；今天 = 双授权）
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/mw-race.py direct

# 2) 双进程 conductor.tick 对拍（真入口；今天 = 2 条 dispatch 事件 + 1 行）
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/mw-race.py tick

# 3) 顺序双派发（无并发；今天 = 两次都 ok）
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/seq.py

# 4) 临界区形状原型（判定在锁内；期望 grants=1/refusals=1/rows=1）
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/fixed.py

# 5) 真实队列耗时
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/bench.py
python .agenticdoc/mw-dynamic-concurrency/evidence/_scratch-rq-d3-race/bench2.py
```

复现产物（脚本与 scratch 项目树）在本证据文件交付前已按 AGENTS.md 的临时脚本纪律（"remove when done"）整体删除，因此本 RQ 在仓库里**只新增了本证据文件**，没有留下任何临时路径。要重跑，按上面 5 条命令的逻辑重建脚本即可：§4.2/§4.3 给了两个对拍的完整步骤（快照 → rendezvous → 派发 / `tick`），§4.5 给了形状原型的判定顺序，§5.1 给了计时口径；[VERIFY] 的数值就是这些脚本在本机的实测打印。

`[VERIFY]`（数值均为本机实测打印，非推算）
- `[VERIFY] queue_rows=426`（`.agenticdoc/_workers.parallel`，`bench.py` 输出 `queue_rows= 426`、`queue_line_count= 426`）
- `[VERIFY] queue_owner_keys=35`（`bench.py`：`deps_of_source=synthesized-from-queue-owner-keys` 后 `roadmap_keys= 35`）
- `[VERIFY] parse_workers_file_ms=0.3941`（`bench.py`，中位，n=200）
- `[VERIFY] scan_worker_lines_ms=0.3734`（`bench.py`，中位，n=200）
- `[VERIFY] in_flight_keys_ms=0.8498`（`bench.py`，35 key × 426 行最坏不短路，中位 n=50）
- `[VERIFY] upsert_worker_row_ms=1.1833`（`bench2.py`，426 行真实队列副本，中位 n=50）
- `[VERIFY] lock_plus_dupcheck_plus_upsert_ms=1.9442`（`bench2.py`，边际 +0.76 ms）
- `[VERIFY] today_direct_grants=2`（`mw-race.py direct`：两个子进程均 `"ok": true`、`snapshot: []`、`row_verified: true`）
- `[VERIFY] today_direct_dispatch_events=2 queue_rows_for_key=1`（`mw-race.py direct` tally）
- `[VERIFY] today_tick_dispatch_events=2 queue_rows_for_key=1`（`mw-race.py tick` tally；两个 `tick: "ok"`）
- `[VERIFY] today_seq_grants=2 dispatch_events=2 rows=1`（`seq.py`：`[{"call":"A","ok":true},{"call":"B","ok":true}]`）
- `[VERIFY] shape_proto_grants=1 refusals=1 rows=1`（`fixed.py`，5 连跑一致；refusal `reason="already-in-flight:ap-k1-T-01-first"`）
- `[VERIFY] stale_lock_age_sec=30.0`（`conductor.py:109`）
- `[VERIFY] acquire_lock_worst_wait_sec=52428.75`（`sum(0.05*2**k for k in range(20))`）
- `[VERIFY] launcher_poll_interval_sec=5`（`launcher.py:51`）
- `[VERIFY] lock_path=H:\\git\\Multi-Workers\\.mw\\workers.lock`（`bench.py` 输出；`lock_exists= False`，即当前无残留锁）
