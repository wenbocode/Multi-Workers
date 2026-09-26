# RQ-D4 证据：并发写 lost-update 防护（CLI vs 窗口 `/autopilot`）与跨语言锁设计

- key：`mw-autopilot-verify-cli`（design 期 · RQ-D4）
- 日期：2026-09-26 · 执行者：worker `design-rqd4-write-lock`
- 性质：只读调研；唯一写面 = 本文档
- 环境：Windows NTFS · Python 3.14.3 · Node v24.19.0 · 工作树 `b0a30bc12`（HEAD）
- 关联 AC：AC-011（主）、AC-005/AC-008/AC-012（边界）
- 复现：§7（脚本在 `%TEMP%\mw-rqd4\`，原始 JSON 报告在 `%TEMP%\mw-rqd4\work*\exp*_report.json`）

## 0. 结论速览

| # | 问题 | 结论 | 决定性依据 |
|---|---|---|---|
| 1 | 既有锁原语语义 | `mw_common.acquire_lock` = `O_CREAT\|O_EXCL` + 指数退避；**无 stale 判定、无 owner 元数据、无锁内容、无 wall-clock 超时**。默认 `retries=20, base_delay=0.05` 的最坏等待实测 **52428.8 s ≈ 14.56 h** ⇒ 若照默认复用，"锁不可得即报错"会退化成 14 小时挂起 | `mw_common.py:1438,1480-1492,1495-1499`；实测 A1/A2/A3/A4 |
| 2 | TS 侧能否加同一把锁 | **能，且现成**：`shared/file-lock.ts:12 acquireLock` 用 `fs.openSync(path,"wx")`（`O_CREAT\|O_EXCL` 等价物），协议/退避与 Python 同构；已被 `worker-store`/`index-store`/`ack-store`/`pm/state-manager`/`autopilot/gate-writer` 使用。实测 TS 与 Python 争同一把锁能正确串行（CLI 等 0.302 s，两侧改动都保留） | `file-lock.ts:12-40`；`worker-store.ts:58`；`gate-writer.ts:153`；实测 D3 |
| 3 | 只加 CLI 侧锁够不够 | **不够**（明确结论）。CLI 持锁只能排除"也来拿这把锁的人"；不加锁的 console 可以在 CLI 临界区**之前**读、**之后**写，把 CLI 的改动整份回滚。实测 30 轮、两侧各 30 ms 读→写窗口：CLI 更新丢 1 次、console 更新丢 28 次、console 另有 2 次硬失败 | 实测 D2/E2/G1；`console.ts:287,339` → `status-model.ts:234` |
| 4 | 既有测试可复用形状 | 最贴近的模板是 TS 的"持锁 ⇒ 拒绝 + 目标字节不变 + 释放后重试成功"（`packages/coding-agent/test/suite/autopilot-console.test.ts:611-644`）；Python 并发形状在 `test_integration.py:275-312`；**`test_autopilot_config.py` 与 `test_dispatch_models.py` 均无任何锁/并发用例** | §4 表 |
| 5 | 推荐方案 | 专用锁 `<root>/.mw/autopilot-config.lock`（不共用 `workers.lock`）+ 两侧显式 `retries=6/base_delay=0.02`（最坏 1.26 s，实测 1.348 s）+ 失败 `[mw autopilot verify set] Error: ...` + `return 1` 且**不覆盖**；**TS 侧必须同步加锁**；AC-011 用"持锁拒绝"+"读在锁内"两个确定性断言判定，真竞态只作慢速压测 | §5 |
| 6 | 锁的边界 | `set`/`clear` 需锁（都是整份重写的 RMW）；`show`/`doctor`/conductor 只读**不需锁**，且不得创建 `.mw/`（会破坏"文件缺失 = 从未启用"的零足迹语义）。锁落 `<root>/.mw/`：`.gitignore:53`（`.mw/`）已忽略；`.agenticdoc/**/*.lock` 在 `:69` 亦已忽略 ⇒ 任务书"核实 `.gitignore:69`"**成立**，但既定约定是根 `.mw/` | 实测 A1（`acquire_lock` 建父目录）；`.gitignore:53,68,69` |

## 1. 既有锁原语完整语义（`mw_common`）

### 1.1 源码即语义

```python
# mw_common.py:1438-1439
def lock_path(project_dir):
    return pathlib.Path(project_dir) / ".mw" / "workers.lock"

# mw_common.py:1480-1492
def acquire_lock(lock_file, retries=20, base_delay=0.05):
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

# mw_common.py:1495-1499
def release_lock(lock_file):
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass
```

| 语义维度 | 事实 | 位置 |
|---|---|---|
| 命名与位置 | 路径由调用方给；`lock_path()` 固定返回 `<project>/.mw/workers.lock`（`.mw` 是"锁与 PID"目录，见 `autopilot/config.py:5-6` 文档） | `:1438-1439` |
| 获取方式 | `os.open(..., O_CREAT\|O_EXCL\|O_WRONLY)` + 立即 `close` ⇒ **零字节空文件即"已持有"** | `:1485-1486` |
| 父目录副作用 | `mkdir(parents=True, exist_ok=True)` ⇒ **调用一次就创建 `.mw/`**（只读路径绝不能调用） | `:1482` |
| 超时/重试 | 无 wall-clock 超时；仅 `retries+1` 次尝试，第 `attempt` 次失败后 sleep `base_delay * 2**attempt`；穷尽后抛 `RuntimeError` | `:1483-1492` |
| stale 判定 | **无**。文件存在 = 被持有，与年龄、进程存活无关；`acquire_lock` 从不删别人的锁 | `:1488-1490` |
| owner 元数据 | **无**（不写 pid/host/时间戳/资源名）⇒ 不能从锁文件内容判断持锁者，也不能安全地"确认过期后抢占" | `:1485` |
| 释放语义 | `unlink()`；`FileNotFoundError` 静默吞掉（幂等，重复 release 不报错） | `:1495-1499` |
| 异常路径残锁 | 原语自身不留残锁；残锁只出现在**持锁进程未跑 finally 就死亡**（`os._exit`/SIGKILL/断电）时，此后永久拒绝（无 stale 判定） | 实测 A4/A6 |
| 可重入/公平 | 无。同一进程/线程重复 acquire 会和自己死锁；无排队、无 FIFO 公平性 | 代码即证 |

### 1.2 实测

| 编号 | 场景 | 命令/形状 | 实测结果 |
|---|---|---|---|
| A1 | 锁被占用，`retries=3, base_delay=0.01` | 真实 sleep | `RuntimeError`，elapsed **0.071 s**（理论退避和 0.07 s）；锁文件**保持存在**（原语不清理） |
| A2 | 默认 `retries=20, base_delay=0.05` 的最坏等待 | monkeypatch `time.sleep` 记录 20 次 sleep | 退避序列和 **52428.8 s = 14.56 h**（首次 0.05 s，末次 26214.4 s）⇒ 默认参数下"锁不可得"不是快速失败而是 14 小时挂起 |
| A3 | stale 锁（`os.utime` 设为 1 h 前） | `retries=2` | **仍拒绝**（`after 2 retries`），锁文件 mtime 不参与判定 ⇒ 崩溃残锁永久卡死 |
| A4 | 持锁进程 `os._exit(9)`（模拟崩溃） | 子进程 | 残锁存在 = True；下一次 acquire 拒绝 ⇒ 必须人工删除 |
| A5a | conductor 侧同路径 `.mw/workers.lock` 且新鲜 | `acquire_conductor_lock(root,"workers")` | `ConductorLockHeld: workers.lock held by a live holder (age 0s)` |
| A5b | 同锁 aged 90 s（> `STALE_LOCK_AGE_SEC=30`） | 同上 | **抢占成功**，timeline 追加 `stale workers.lock stolen (age 90s > 30s)` |
| A6 | 临界区内抛异常 + `finally: release` | — | 无残锁 ⇒ 唯一正确用法是 try/finally |
| A7 | 8 个真实进程争锁做"读-改-写追加"（各持 50 ms） | `retries=8, base_delay=0.02` | **8/8 行全在，0 丢失**；最慢一个子进程等 **5.104 s**（= 0.02*(2^8-1) 退避和）；无残锁 |
| A8 | 同 A7 但**完全不加锁** × 10 轮 | 8 进程 | 10 轮共丢 **67/80** 行（每轮丢 6~7 行）⇒ 无锁 RMW 的基线缺陷 |

（A5b 说明 conductor 的 `acquire_conductor_lock`（`conductor.py:98-133`）是**另一层**语义：30 s 年龄阈值 + 抢占 + timeline 事件；`mw_common.acquire_lock` 本身没有 stale 能力。设计时不要把两者混为一谈。）

### 1.3 可直接复用的调用形状（Python 侧）

```python
# 建议：专用锁路径（见 §5），不是 lock_path() 的 workers.lock
RETRIES, BASE_DELAY = 6, 0.02          # 最坏 1.26 s；见 §5.1 理由

lock = ap_config.config_lock_path(project_dir)      # <root>/.mw/autopilot-config.lock
mw_common.acquire_lock(lock, retries=RETRIES, base_delay=BASE_DELAY)   # 失败抛 RuntimeError
try:
    cfg = ap_config.load_config(project_dir)        # 必须"锁内重读"（§3.4）
    cfg["xkey_verify_cmd"] = argv
    ap_config.save_config(project_dir, cfg)         # 原子替换，锁内
finally:
    mw_common.release_lock(lock)
```

异常形状（CLI 层）：

```python
except RuntimeError as exc:                         # 锁不可得
    print(f"[mw autopilot verify set] Error: {exc}", file=sys.stderr)
    return 1                                        # 不覆盖（AC-011）
```

### 1.4 现有 `acquire_lock` 调用点（任务书问"谁在用"）

| 资源 | 锁路径 | 调用点 | 说明 |
|---|---|---|---|
| `_workers.parallel`（launcher 侧状态更新） | `.mw/workers.lock` | `mw_common.py:1513-1524`（`update_status`） | 锁内 read-merge-write |
| `_workers.parallel`（归档清理） | `.mw/workers.lock` | `mw_common.py:1537-1560`（`archive_stale_entries`） | 锁内写 `_workers.stale.parallel` |
| `_workers.parallel`（conductor 派单 upsert） | `.mw/workers.lock` | `autopilot/dispatch.py:525,537,570` | 锁内 read + `_write_workers_file`；失败返回 `lock-unavailable`（**fail-closed 先例**） |
| `_workers.parallel`（conductor 孤儿回填） | `.mw/workers.lock` | `conductor.py:3856`（`acquire_conductor_lock(..., "workers")` / 释放 `:3888`） | 带 30 s stale 抢占 |
| `_workers.parallel`（TS 侧） | `.mw/workers.lock` | `shared/worker-store.ts:58,68`；`shared/ack-store.ts:21,55` | 与 Python 同一把锁、同一协议 |
| `_index.parallel` | `.mw/index.lock` | `shared/index-store.ts:60,70,98`（TS）；`conductor.py:379/2243/...`（`lock_file(root,"roadmap")` 等） | — |
| xkey ledger | `.mw/xkey-ledger.lock` | `autopilot/xkey.py:102,165-166,558-581` | 锁内 read-merge-write（**与本次要做的形状最像**） |
| gates / roadmap / key-`<k>` | `.mw/{gates,roadmap,key-k}.lock` | `conductor.py:375,1748,1840,1881,1900,2056,2149,2239,2320,2360,3786` | 均走 `acquire_conductor_lock` |
| gate 答复（人工/TS） | `.mw/gates.lock` | `status-model.ts:61-63`；`gate-writer.ts:153` | 跨语言同锁先例 |
| 测试/e2e | 同上 | `test_integration.py:284-301`、`test_autopilot_e2e.py:823,843` | 可照抄的手工持锁形状 |

## 2. TS 侧能否加同一把锁

### 2.1 已有实现：`shared/file-lock.ts`（探到即结论）

```ts
// packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts:12-40
export async function acquireLock(lockPath: string, opts: LockOptions = {}): Promise<() => void> {
	const retries = opts.retries ?? 10;
	const baseDelayMs = opts.baseDelayMs ?? 50;
	const dir = path.dirname(lockPath);
	if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
	for (let attempt = 0; attempt <= retries; attempt++) {
		try {
			const fd = fs.openSync(lockPath, "wx");     // O_CREAT|O_EXCL 等价物
			fs.closeSync(fd);
			return () => { try { fs.unlinkSync(lockPath); } catch { /* 幂等 */ } };
		} catch (err) {
			const isExist = err instanceof Error && "code" in err && err.code === "EEXIST";
			if (!isExist) throw err;
			if (attempt === retries) throw new Error(`Could not acquire lock at ${lockPath} after ${retries} retries`);
			await sleep(baseDelayMs * 2 ** attempt);
		}
	}
}
```

| 维度 | TS `acquireLock` | Python `mw_common.acquire_lock` | 结论 |
|---|---|---|---|
| 互斥原语 | `fs.openSync(path,"wx")` | `os.open(..., O_CREAT\|O_EXCL\|O_WRONLY)` | **同一把锁可以互斥**（实测 D3） |
| 退避 | `baseDelayMs * 2**attempt` | `base_delay * 2**attempt` | 同构 |
| 默认预算 | `retries=10, baseDelayMs=50` ⇒ 最坏 sleep 和 **51.15 s** | `retries=20, base_delay=0.05` ⇒ **52428.8 s (14.56 h)** | **两侧都必须显式传预算**，否则失败语义不成立 |
| stale | 无 | 无 | 残锁都要靠人工/调用方处理 |
| 同步/异步 | `async`，返回 release 闭包 | 同步，配 `release_lock` | CLI 是同步的，无需 await |
| 父目录 | `mkdirSync(recursive)` | `mkdir(parents=True)` | 都会建 `.mw/`（只读路径别调用） |

现有使用者（全部是"锁内 read-modify-write"或"锁内追加"）：`shared/worker-store.ts:58,68`、`shared/ack-store.ts:21,55`、`shared/index-store.ts:60,70,98`、`pm/state-manager.ts:67-68`、`pm/ui-bridge.ts:842`、`autopilot/gate-writer.ts:150-175`。**没有针对 file-lock 本身的独立测试文件**（grep 全仓 `test/**` 无 `file-lock` 命中），协议只被上述调用方间接覆盖。

### 2.2 实测：TS 与 Python 争同一把锁能正确串行

D3（真并发，不是模拟）：`node` 侧用 dist 的 `acquireLock` 持 `.mw/autopilot-config.lock`，读→`sleep(400ms)`→写 `round_budget=7`；150 ms 后 Python 侧用 `mw_common.acquire_lock` 争同一路径写 `xkey_verify_timeout_s=1902`：

```
console: console held-then-wrote value=7
cli    : lock_wait=0.302s -> py ok value=1902
final  : (1902, 7)          # 两侧改动都在
```

⇒ **跨语言锁是可行的、被实测验证的**：Python 的 `lock_wait=0.302 s` 正是等 TS 释放（400 ms 窗口的一部分）。

### 2.3 可照抄的最小实现形状（TS 侧）

原则：**不改 `saveConfig` 的字节形状**（AC-006 的 Python/TS 字节一致判据依赖它），新增一个加锁包装，并把两个调用点（`console.ts:287,339`）切过去。

```ts
import { acquireLock, type LockOptions } from "../shared/file-lock.ts";

// status-model.ts 旁边新增（与 gatesLockPath:61-63 同风格）
export function configLockPath(projectDir: string): string {
	return path.join(projectDir, ".mw", "autopilot-config.lock");
}

// 加锁版：锁内读取 + 锁内保存；失败返回错误（不写、不抛）
export async function saveConfigLocked(
	projectDir: string,
	mutate: (cfg: AutopilotConfig) => AutopilotConfig,
	lockOpts: LockOptions = { retries: 6, baseDelayMs: 20 },   // 最坏 1.26 s
): Promise<{ ok: true } | { ok: false; error: string }> {
	let release: () => void;
	try {
		release = await acquireLock(configLockPath(projectDir), lockOpts);
	} catch (err) {
		return { ok: false, error: err instanceof Error ? err.message : String(err) };
	}
	try {
		const cur = readConfig(projectDir);            // 锁内重读（关键）
		if (!cur.ok) return { ok: false, error: cur.error };
		return saveConfig(projectDir, mutate(cur.config));
	} finally {
		release();
	}
}
```

调用点改造（`console.ts:282-291` / `334-343` 的 `readConfig` + `saveConfig` 两步合并为一步）：

```ts
const saved = await saveConfigLocked(projectDir, (cfg) => ({ ...cfg, enabled }));
if (!saved.ok) { ctx.ui.notify(`[autopilot] ${saved.error}`, "error"); return; }
```

已有错误出口可直接复用（`console.ts:288-291`、`340-343` 的 `ctx.ui.notify(..., "error")`），所以 TS 侧改动量约 20 行 + 2 个调用点 + 1 个测试。注意 `cmdSetPaused`（`console.ts:333`）当前是**同步**函数，需改成 `async`（`cmdSetEnabled` 已是 async）。

### 2.4 崩溃残锁的清理策略

- 两侧都用 try/finally（实测 A6 / D7 `lock_residue=false`）⇒ 正常路径零残留。
- 硬崩溃（`os._exit`/SIGKILL/断电）会留残锁，且 `acquire_lock` 无 stale 判定 ⇒ 之后永远拒绝（实测 A4）。三种可选策略：
  1. **失败即报错 + 提示人工清理（推荐给 CLI）**：错误信息里带上锁路径与"若无其他写者请删除后重试"。代价 = 误拒时用户重跑一次；收益 = 不会出现"两个写者同时认为拿到了锁"。符合 AC-011"报错 `return 1` 且不覆盖"。
  2. 加 N 秒 stale 抢占（照 `acquire_conductor_lock` 的 30 s，`conductor.py:98-133`）：能自愈，但会引入"持锁进程被 SIGSTOP/挂起 > N 秒 ⇒ 双写"的窗口。本资源的临界区实测 **0.708~1.153 ms**（median 0.814 ms），所以 N 取 ≥ 60 s 时误抢概率极低；若要自愈，建议只在 CLI 侧做、且必须写 timeline/日志留痕。
  3. 两侧都写 owner 元数据（pid+时间）再判活——**不推荐**：`acquire_lock` 是空文件协议，改内容会破坏与既有 `file-lock.ts` 的字节零依赖契约，收益不抵复杂度。
- 不建议在 `show`/`doctor`/serve 启动时"顺手清理"任何 `.lock`：那会把"只读路径"变成写路径（见 §6）。

## 3. 实际并发面评估与方案正确性对比

### 3.1 写者与真正需要防的交错

写者（`_autopilot/config.json`）：

| 写者 | 入口 | 形状 | 现状 |
|---|---|---|---|
| TS console（生产唯一写者） | `/autopilot enable\|disable` → `console.ts:287`；`pause\|resume` → `console.ts:339` | `readConfig` → `saveConfig`（整份 12 键，`status-model.ts:234-259`） | 无锁 |
| TS console（另一窗口） | 同上 | 同上 | 无锁 ⇒ **TS vs TS 现在就已经能丢更新**（实测 F1） |
| Python CLI（本 key 新增） | `mw autopilot verify set` → `config.save_config`（`config.py:136-146`） | `load_config` → 改键 → `save_config` | 待实现，按 AC-011 加锁 |
| 人手工编辑 | 文档明确允许（`config.py:1-6`） | 任意 | 锁不能约束（边界，见 §6） |

单个写者 = `R`（读）→ `W`（整份原子替换）。两个写者 A/B 的合法交错只有 4 种（每人 `R` 必在 `W` 前）：

| 交错 | 结果 |
|---|---|
| `R_A W_A R_B W_B` | 安全（B 读到 A 的结果） |
| `R_B W_B R_A W_A` | 安全 |
| `R_A R_B W_A W_B` | **A 的改动被 B 回滚**（B 用的是 stale 快照） |
| `R_A R_B W_B W_A` | **B 的改动被 A 回滚** |
| `R_B R_A W_A W_B` | **B 的改动被 A 回滚** |
| `R_B R_A W_B W_A` | **A 的改动被 B 回滚** |

⇒ 需要防的正是任务书点名的 **`read→read→write→write`**：两次读都发生在对方写之前。因为两侧都写**整份 12 键**，丢失的不只是"自己那个键"——任何一次交错都会把对方的键一起回滚（实测：CLI 写 `xkey_verify_cmd` 时把 console 刚写的 `paused/enabled` 回滚，反之亦然）。

**第三种失败模式（实测新发现）**：两侧都用**同名 tmp**（`config.py:143` `f"{path}.tmp"`；`status-model.ts:254` `${file}.tmp`）。两个不加锁的写者会争同一个 tmp 文件，在 Windows 上直接抛 `PermissionError: [Errno 13] ... config.json.tmp`（Python，实测 F2/E3）或 TS 侧写失败（实测 F1）。即"不加锁"不只是静默丢更新，还会**硬失败**。

### 3.2 实测矩阵

| 编号 | 场景（真进程，非 mock；Python 用 `autopilot/config.py`，TS 用 `packages/coding-agent/dist/.../status-model.js` 的 `readConfig/saveConfig`） | 结果 |
|---|---|---|
| D1 | 确定性交错、两侧都不加锁：console 读快照 → CLI 写 `xkey_verify_timeout_s=1900` → console 写回 stale 快照 | 最终 `(1800, 5)`：**CLI 改动被静默回滚** |
| D2 | 确定性交错、**只有 CLI 持锁**（console 不加锁，模拟现状 TS） | 最终 `(1800, 6)`：**CLI 改动仍被静默回滚** ⇒ 回答"只加 CLI 侧锁不够" |
| G1 | CLI 持锁 + 在临界区窗口内让不加锁的 console 写入 | console 的写被 CLI 的整份写**静默回滚**（`round_budget` 9 → 2），CLI 报成功 |
| G2 | 同上，但 CLI 加"写前重读校验"（§3.4） | CLI **中止并报错**（rc=2，`config.json changed under us`），console 的写保住了 |
| E1 | 30 轮 storm，**两侧都加锁**（Python `mw_common` + TS `file-lock` 争同一路径，读→写间插 30 ms 窗口） | **30/30 干净，两侧 0 丢失**，无残锁，无 tmp 残留 |
| E2 | 30 轮 storm，**CLI 加锁 / console 不加锁** | CLI 丢 **1/30**；console 丢 **28/30**；console 另有 **2** 次进程级失败 ⇒ CLI-only 锁在生产形状下依然丢更新 |
| E3 | 30 轮 storm，两侧都不加锁 | Python 侧直接 `PermissionError ... config.json.tmp`（共享 tmp 相撞） |
| F1 | TS console vs TS console（两个窗口），无锁，各 30 ms 窗口，30 轮 | **4/30 轮硬失败**（`saveConfig` 报错），其余轮次双向回滚 ⇒ **缺陷先于本 key 存在** |
| F2 | Python CLI vs Python CLI，无锁，30 轮 | **2/30 轮 `PermissionError`**（同一 `config.json.tmp`） |
| F3 | TS console vs TS console，**两侧都加锁**，30 轮 | **0 失败** |

### 3.3 明确回答：只加 CLI 侧锁是否足够

**不够。** 依据三条：

1. 锁是"自愿协议"，只排除来拿同一把锁的人。console 不拿锁 ⇒ 它的 `R`/`W` 可以完整跨过 CLI 的整个临界区（D2 的 `R_console` 在 CLI 加锁之前，`W_console` 在 CLI 释放之后），CLI 的改动被整份回滚，且**没有任何一方报错**。
2. 定量：E2（30 ms 窗口，30 轮）CLI 丢 1 次、console 丢 28 次，另有 2 次硬失败。即使把 CLI 的锁做对，生产链路仍然是"静默丢更新"。
3. 反方向的安全性质也不成立：CLI 持锁**不能**保护"console 的写"不被 CLI 的整份写回滚（G1）；而 CLI 的写**不能**保护自己不被 console 的 stale 写回滚（D2）。两侧必须同锁。

### 3.4 "锁 + 写前重读校验" vs "仅锁"

"重读校验" = 锁内读到版本快照（内容 sha256/mtime+size），改完在 `rename` 之前再读一次，若变化则**中止不写**。

| 方案 | 实测 | 能防什么 | 不能防什么 |
|---|---|---|---|
| 仅锁（两侧都锁） | E1/E3/D3：0 丢失 | 所有**锁参与者**之间的 `R-R-W-W` 交错（锁使 `R` 与 `W` 对他人原子） | 不拿锁的写者（D2/G1）；手工编辑 |
| 仅锁（只有 CLI 锁） | D2/E2：仍丢 | 无（相对"都不锁"只减少了 CLI 作为被回滚方的一小部分窗口） | 同上，且 console 之间仍互相丢 |
| 锁 + 重读校验 | G2：CLI 中止、对方写保住 | **单向**：防止"别人的写"被**我的** `rename` 覆盖（在窗口内被检出） | 反向（别人 stale 快照回滚我的写，D2 方向）无法检出；且校验与 `rename` 之间仍有 TOCTOU 微窗口（文件系统无 CAS 原语），只能把窗口缩小、不能归零 |

**结论**：正确性来自"锁"，重读校验只能作为**对不守锁写者的单向兜底**。不要把重读校验当作替代品写进 AC；若要加，代价约 3 行且不破坏字节契约（实测 G2 行为可断言：rc=非 0 + 文件保留对方字节）。

### 3.5 真实并发概率

- 触发条件：两个写者的读→写窗口重叠（§3.1 的 2 种危险交错）。单次 RMW 窗口实测 **median 0.814 ms，max 1.153 ms**（60 次采样，`xkey_verify_timeout_s` 改写 + 全量 `save_config`）。
- 两侧都是人工触发（一条 CLI 命令 / 一次窗口命令），概率很低；但：
  1. 失败是**静默**的，而且恰好把 `xkey_verify_cmd` 回滚掉——正是 AC-008 要防的"工单全卡 `verify_failed`"，事后从 config 内容完全看不出发生过回滚；
  2. 已有自动化来源：worker/agent 可以跑 `mw autopilot verify set`，脚本可批量部署多项目；
  3. **TS vs TS 现在就已暴露**（两个 pi 窗口 = F1 的 4/30 硬失败），CLI 只是第三个写者；
  4. 修复成本 ≈ Python 5 行 + TS 20 行 + 1 组测试，而漏修的代价是"机制在真实窗口下会丢配置"。
  ⇒ 不因概率低而免修；但可以据此把 AC-011 的判定做成**确定性断言**而不是真竞态压测（§5.3）。

## 4. 既有测试盘点（可照抄的形状）

| 文件:行 | 现有内容 | 与 AC-011 的关系 / 可复用形状 |
|---|---|---|
| `packages/multi-workers/test_autopilot_config.py:91-102` | `test_roundtrip_and_atomic_write`：写后 `raw.endswith("\n")` + `not list(path.parent.glob("*.tmp"))` + `load_config == modified` | 锁测试应长在这一个文件里；"无 .tmp 残留"断言可直接复用 |
| `packages/multi-workers/test_autopilot_config.py:105-108` | `test_save_rejects_invalid`：非法 ⇒ 抛 `ConfigError` 且 `not config_path.exists()` | "拒绝写 = 目标不出现/不变化"的断言形状，直接搬到"锁不可得不覆盖" |
| `packages/multi-workers/test_autopilot_config.py:113-144` | mtime 缓存失效/一致性 | 与锁无关；提醒 CLI 用 `load_config`（非 `cached_load`） |
| `packages/multi-workers/test_dispatch_models.py:422-465` | `TestModelCli`：`argparse.Namespace(...)` 直调 `mw.cmd_model` + `capsys` | **`mw autopilot verify set` 的 CLI 测试激活形状**（无需子进程） |
| `packages/multi-workers/test_dispatch_models.py:448-452` | `test_set_refuses_broken_existing`：`assert mw.cmd_model(...) == 1` + `assert "broken" in path.read_text()` | "拒绝写 + 原文件字节不变"的直接模板 |
| `packages/multi-workers/test_dispatch_models.py:470-485` | `TestDoctorDispatch`：`doctor_report` + `format_doctor_text` | AC-008 需要时用；与锁无关 |
| `packages/multi-workers/test_integration.py:275-312` | `TestConcurrentWrites.test_eight_concurrent_upserts_survive_launcher_rewrites`：8 线程各自 `acquire_lock` → RMW → `release`；断言 `{f"c{i}"} <= keys`（**:311**） | **Python 侧"锁内并发不丢"的现成写法**（进程内线程版）；锁的 try/finally 形状也在这里 |
| `packages/multi-workers/test_autopilot_conductor.py:192-206` | `test_stale_lock_stolen_and_recorded`：造锁 → `os.utime` 老化 → `acquire_conductor_lock` 抢到 + timeline 事件 | stale 语义只能引用 conductor 层，别指望 `acquire_lock` |
| `packages/multi-workers/test_autopilot_conductor.py:209-216` | `test_fresh_lock_not_stolen`：`pytest.raises(ConductorLockHeld)` + `assert lock.exists()`（**锁没被动过**） | 复用 `assert lock.exists()`：CLI 失败时**不得删除/抢占**别人的锁 |
| `packages/multi-workers/test_autopilot_dispatch.py:135,141-146` | `assert not mw_common.lock_path(tmp_path).exists()` + `[VERIFY] ... lock_cleaned=...` | "成功路径锁被释放"的断言 + `[VERIFY]` 机器判据行惯例 |
| `packages/multi-workers/test_autopilot_e2e.py:788-880` | `test_concurrent_write_stress`（`@_e2e_l2` 门禁）：人工写线程 0.2 s 一轮，持 `.mw/workers.lock` / `.mw/index.lock`（**:823,838,843,857**） | 慢速压测模板；**不要**用它做 AC-011 的判定（耗时/环境敏感） |
| `packages/multi-workers/test_serve_doctor.py:646-675` | claim 后 `assert not (tmp_path/".mw"/"index.lock").exists()` | 锁释放断言（另一处先例） |
| `packages/multi-workers/test_serve_meta.py:65` | `assert mw_common.lock_path(tmp_path) == tmp_path/".mw"/"workers.lock"` | **锁路径跨侧一致性断言**的形状（AC-011 的 T4 照此写） |
| `packages/coding-agent/test/suite/autopilot-console.test.ts:611-644` | `AC-016: answering is mutually exclusive with a held .mw/gates.lock`：手写锁文件 → `answerGate` 返回 `ok:false` 且 error 含 `lock` → `assert fs.readFileSync(gateFile) === before` → `unlinkSync(lockFile)` 后重试成功。**并用 `lockOpts: { retries: 1, baseDelayMs: 1 }` 把重试预算注入成 1 ms** | **AC-011 最贴近的模板**：Python 版 = "手写 `.mw/autopilot-config.lock` → 跑 CLI → 断言 rc=1 + 字节不变 + 锁文件仍在 → 删锁重跑成功"。同时示范了"预算必须可注入"（否则测试要等 1.26 s×N） |
| `packages/coding-agent/test/suite/autopilot-console.test.ts:543-586` | 其余行逐字节保留 | 与锁无关（但说明 TS 侧已有"持锁 + 拒绝 + 字节不变"的测试文化） |
| 全仓 | **没有** `file-lock.ts` 的直接测试 | 若要给 TS 侧锁加单测，本次是第一次 |

`test_autopilot_config.py` 与 `test_dispatch_models.py` 中 **0** 个 `lock` 相关用例（grep 全文件确认）⇒ AC-011 的测试是纯新增。

## 5. 推荐方案

### 5.1 决策表（含"为什么"）

| 决策点 | 推荐 | 依据 / 代价 |
|---|---|---|
| 锁文件路径 | **`<root>/.mw/autopilot-config.lock`**，两侧各加一个 helper：Python `autopilot/config.py::config_lock_path(root)`、TS `status-model.ts::configLockPath(projectDir)`（紧邻 `gatesLockPath:61`） | 与既有约定一致（`.mw/gates.lock`、`.mw/workers.lock`、`.mw/index.lock`、`.mw/xkey-ledger.lock`）；`.gitignore:53` 已忽略 `.mw/`。**不推荐** `.agenticdoc/_autopilot/config.json.lock`：虽然 `.gitignore:69` 也覆盖（核实成立），但它打破"锁都在 `.mw/`"的既有约定，TS 侧还要多一个概念 |
| 是否复用 `.mw/workers.lock` | **不复用**（用专用锁）；若 PM 坚持 spec §2.3 的字面"`lock_path`"，也**能**满足 AC-011——代价是配置写会与派单/launcher 的 worker 表写互相串行（当前持锁时长都是毫秒级：`dispatch.py:537-570`、`mw_common.py:1513-1524`、`conductor.py:3856-3888`），属于"正确但耦合" | 专用锁在两侧的改动量完全相同（都要新增一个路径常量 + 加锁），所以没有理由耦合两个不相干的资源域。**请 PM 在 design 期定一个（见 §8 U-7）** |
| 获取预算 | Python：`mw_common.acquire_lock(lock, retries=6, base_delay=0.02)` ⇒ 最坏退避和 **1.26 s**（实测 D7 全流程 1.348 s）。TS：`acquireLock(path, { retries: 6, baseDelayMs: 20 })` ⇒ 同量级 | **绝不能用两侧默认值**（Python 14.56 h、TS 51.15 s）——那会让 AC-011 的"报错 `return 1`"变成挂起。1.26 s ≫ 临界区实测 max 1.15 ms（≈1000 倍余量），足够吸收正常争用；也够短到用户不会以为卡死 |
| 失败语义（CLI） | 捕获 `RuntimeError`/`OSError` → `print("[mw autopilot verify set] Error: ...", file=sys.stderr)` → `return 1`；**不写文件**；**不删/不抢占别人的锁**；错误文本里带上锁路径与"若无其他写者，请删除该文件后重试" | AC-011 原文；`mw model set` 的 `Error:` + `return 1` 先例（`mw.py:3139-3144`）；`dispatch.py:537-543` 的 `lock-unavailable` fail-closed 先例 |
| 失败语义（TS console） | `saveConfigLocked` 返回 `{ok:false,error}` → 走既有 `ctx.ui.notify(..., "error")`（`console.ts:288-291,340-343`）；console 写失败时不改变其它行为（`enable` 路径也**不要**在这种情况下继续 `ensureMwRunning`，因为配置没写成功） | 与 `answerGate` 的失败形状一致（`gate-writer.ts:150-155`） |
| 持有范围 | **锁内 `load_config`（重读）→ 改键 → `save_config` → finally 释放**。解析/校验/参数错误在**加锁之前**返回（避免无谓地建 `.mw/` 与等待） | "锁内重读"是本 AC 的实质：若在锁外读，锁只保护写、不保护读，D1/D2 的丢失依旧。用 `load_config` 而**不是** `cached_load`（缓存是进程内单例，一次性的 CLI 无收益且增加"读到旧值"的可能） |
| TS 是否必须同步加锁 | **必须**。否则 CLI 侧的锁是装饰品（D2/E2/G1），而且 AC-011 若用"守锁的桩 console"来判定，会出现"AC 绿、生产仍丢更新"的空心测试（E2 已量化） | §3.3 |
| tmp 命名（`config.json.tmp`） | **保持现状不改**（两侧同名）。锁到位后 tmp 冲突消失（E1/F3：30/30 干净）；改 tmp 命名对"丢更新"零收益，且会动到两侧字节契约的邻近代码 | G1/F1/F2 只在"不加锁"时出现；如果 PM 最终决定**不加 TS 锁**，则必须把 tmp 改成唯一名（否则保留 `PermissionError` 硬失败）——这是"不加锁"路线的附加代价 |
| stale 处理 | CLI/console 都**不自动抢占**；残锁 ⇒ 报错 + 提示人工删除。可选：锁 mtime > 60 s 时在错误文本/timeline 里标注"疑似残留"（只提示，不抢占） | §2.4；临界区 0.8 ms，30 s 自愈的收益远小于"双写"风险 |
| 只读路径 | `show`/`doctor`/conductor/serve `cached_load` **不加锁、不创建 `.mw/`** | §6 |
| 预算可注入 | Python：模块常量 `_CONFIG_LOCK_RETRIES = 6` / `_CONFIG_LOCK_BASE_DELAY = 0.02`（测试 monkeypatch）；TS：`lockOpts` 参数（照 `AnswerGateOptions.lockOpts:40`） | 否则"持锁拒绝"用例要真等 1.26 s；TS 侧已有先例（`autopilot-console.test.ts:625`） |

### 5.2 Python CLI 实现顺序（防呆）

1. argparse 解析 + `--` 语义校验（AC-001）；错误 → `return 1`（不碰文件、不建 `.mw/`）。
2. `load_config`：文件缺失 ⇒ 用 `default_config()` 补全；文件存在但非法 ⇒ 照 `mw model set` 拒绝（`mw.py:3160-3167`），`return 1`，**不覆盖既有配置**。
   （注意：此处读到的值只用于"能否写"的判断，真正的写必须锁内重读，见第 4 步。）
3. `acquire_lock(config_lock_path(project), retries=..., base_delay=...)`；异常 → `[mw autopilot verify set] Error: ...` + `return 1`。
4. `try:` 锁内 `load_config`（重读；partial 文件在这层补全全 12 键）→ 改 `xkey_verify_cmd`/`xkey_verify_timeout_s`(/cwd) → `save_config`。
5. `finally: release_lock(...)`；成功打印 `[mw autopilot verify set] ... -> <path>`（照 `mw.py:3171` 的措辞）。

`clear` 同形状（锁内重读 → 删键 → 保存；键不存在时 `nothing configured` 且**不写、不加锁**——AC-005 要求"不写文件"，此时连 `.mw/` 都不该建）。

### 5.3 AC-011 的可判定测试设计（确定性优先）

> 原则：**真竞态不作判据**（F1/E3 已证明无锁竞态会硬失败/丢更新，但出现时机不可复现）。判据用"持锁 ⇒ 拒绝"与"读在锁内"两个必然事件。

- **T1 持锁拒绝（决定性，照 `autopilot-console.test.ts:611-644`）**
  1. `config.save_config(root, full_cfg)` 播种；`before = config_path.read_bytes()`。
  2. 手写锁：`lock = ap_config.config_lock_path(root)`；`lock.parent.mkdir(parents=True, exist_ok=True)`；`lock.write_text("")`（模拟并发写者）。
  3. `assert mw.cmd_autopilot(_ap_verify_set_args(root, ["python", "-m", "pytest"])) == 1`（Namespace 直调，照 `test_dispatch_models.py:422-425`）。
  4. `assert config_path.read_bytes() == before`（**字节不变**，照 `test_dispatch_models.py:452` 与 TS `:629`）。
  5. `assert "lock" in captured.err` + `assert lock.exists()`（**CLI 不得删除/抢占他人的锁**，照 `test_autopilot_conductor.py:216`）。
  6. `lock.unlink()`；重跑同一命令 ⇒ `== 0` 且 `load_config(root)["xkey_verify_cmd"] == ["python","-m","pytest"]`（照 TS `:631-640`）。
  7. 预算注入：测试里 `monkeypatch.setattr(mw, "_CONFIG_LOCK_RETRIES", 1)` / `_CONFIG_LOCK_BASE_DELAY 0.001`，把用例耗时压到毫秒级。
- **T2 "读在锁内"（决定性，纯断言顺序，无竞态）**
  - `monkeypatch` 一个 spy 包装 `mw_common.acquire_lock`：置 `state["holding"]=True`；包装 `ap_config.load_config`：断言 `state["holding"] is True`（即 CLI 的配置读发生**在拿锁之后**）；包装 `save_config`：同样断言在持锁中。
  - 再加一条真并发（可保留为普通用例）：线程 A 持锁 → `load_config` → `sleep(50ms)` → 写 `enabled=True` → 释放；主线程调用 CLI `set`；断言最终文件同时含 `enabled=True` 与 `xkey_verify_cmd`（形状照 `test_integration.py:282-311`）。这条在实现正确时 100% 稳定（CLI 必须等 A 的 50 ms），比"两边都抢占"的压测稳。
- **T3 释放与零残留**
  - 成功路径：`assert not lock.exists()`（照 `test_autopilot_dispatch.py:135`）。
  - 失败路径（锁不可得）：`assert lock.exists()`（别人的锁不能被动）。
  - 校验失败路径（未知 xkey 键/空 argv）：`assert config_path.read_bytes() == before` 且 `assert not lock.exists()`。
  - 无 tmp 残留：`assert not list(config_path.parent.glob("*.tmp"))`（照 `test_autopilot_config.py:100`）。
  - `[VERIFY] VC-xxx: lock_cleaned=true_str(...)` 机器判据行（照 `test_autopilot_dispatch.py:141-146`）。
- **T4 跨侧锁路径一致（防"各锁各的"）**
  - 读 TS 常量做比对：Python 侧断言 `ap_config.config_lock_path(root)` 的末两段 == `(".mw", "autopilot-config.lock")`，并在 TS 侧 `autopilot-console.test.ts` 断言 `configLockPath(root)` 与 Python 完全同名（形状照 `test_serve_meta.py:65`）。**这是防空心测试的关键**：两侧路径写错一个字符，所有锁断言都会"通过"却毫无互斥。
- **T5 TS 侧对应用例（必须存在，否则 AC-011 只算半绿）**
  - `autopilot-console.test.ts` 新增：写死 `.mw/autopilot-config.lock` → 调 `saveConfigLocked`（或改造后的 `cmdSetEnabled` 路径）→ 断言 `ok:false` + `config.json` 字节不变 + 锁文件仍在 → 删锁重试成功。
  - 断言 TS 的 console 写**也**走锁：spy `acquireLock` 被调用（形状照 `auth-storage.test.ts:76-97` 的 `vi.spyOn(lockfile,"lock")`）。
- **T6（可选，慢速，不作判据）** 两进程 storm（Python CLI ↔ 桩 TS console，各 30 ms 窗口，30 轮，两侧都锁）⇒ 断言两侧 0 丢失；本文件 E1 已验证该形状可行（30/30 干净，最大等待 62 ms）。若要纳入，放 `test_autopilot_e2e.py` 的 `_e2e_l2` 门禁后端。

**AC-011 措辞建议（避免空心）**：把"模拟锁占用 + 并发两写者（CLI vs 桩 console 写）后断言两处改动都在或明确失败"细化为：
- (a) CLI 侧 T1/T2/T3；
- (b) **TS console 侧同样持锁且锁路径相同（T4/T5）**，桩必须复刻"修好后的 console 行为"（持锁 RMW），而不是"现在的 console 行为"（无锁 RMW）；
- (c) 明确声明 **TS 侧改动属于本 key 范围**（否则 AC-011 可以全绿而生产仍在丢更新）。

## 6. 锁的边界

| 命令 / 路径 | 是否加锁 | 依据 |
|---|---|---|
| `mw autopilot verify set` | **要**（r+w 整份 RMW） | AC-011；D1/D2 实测 |
| `mw autopilot verify clear` | **要**（同为整份 RMW：删键后 `save_config` 全量重写） | 不加锁时会把并发写者刚写的 `enabled/paused/xkey_verify_cmd` 一起回滚（与 set 同机制）。例外：键不存在时"`nothing configured` + 不写"（AC-005）⇒ 这条路径**不应加锁也不应建 `.mw/`**，先读判空、再决定是否进临界区（读判空本身有竞态，但"没键可删"下重读一次仍无键 ⇒ 幂等无害；保守写法：进锁后重读判空） |
| `mw autopilot verify show` | **不加锁** | 只读；且 `acquire_lock` 会 `mkdir` 出 `.mw/`（实测 A1；`mw_common.py:1482`），违反 AC-005/AC-012 的零足迹语义 |
| `mw doctor`（AC-008 段） | **不加锁** | 只读；doctor 可能在任何时刻跑（包括写者持锁期间），阻塞在配置锁上会让诊断工具卡住；`mw_common._doctor_issues`/`doctor_report` 只读 `config`，无写点 |
| conductor / `mw serve` | **不加锁** | 全部走 `config.cached_load`（`conductor.py:169,1874,2036,3975`；`mw.py:161`），只读；写者持锁期间 conductor 可能读到旧值，这是"读到旧值"而非"丢更新"（后者由 AC-003 的缓存判据负责） |
| 人手工编辑 `config.json` | **不受约束** | 文件是 human-editable（`config.py:1-6`）；锁只在"守锁的写者"之间成立。AC-011 的保证必须写成"**在锁参与者之间**不得静默丢失"，不要写成绝对保证 |
| `mw model set/clear`（`mw.py:3116-3126` `_model_write`） | 现状**不加锁** | 相关发现：这是本 key 要照抄的 CLI 先例之一，但它本身也是无锁 RMW（同一缺陷）；本 key 不要继承这个坏味道（超出本 AC 范围，登记为旁证） |

**锁目录落点与 gitignore（逐条核实）**

```
$ git check-ignore -v .mw/autopilot-config.lock
.gitignore:53:.mw/	.mw/autopilot-config.lock
$ git check-ignore -v .agenticdoc/_autopilot/config.json.lock
.gitignore:69:.agenticdoc/**/*.lock	.agenticdoc/_autopilot/config.json.lock
```

- `.gitignore:53` `.mw/`：覆盖 `<root>/.mw/autopilot-config.lock`（**推荐落点**，与 `.mw/gates.lock`/`.mw/workers.lock`/`.mw/index.lock`/`.mw/xkey-ledger.lock` 一致）。
- `.gitignore:69` `.agenticdoc/**/*.lock`：任务书要求核实的这一条**成立**（另有 `:68` `.agenticdoc/.mw/`）——但它对应的是"把锁放在配置旁边"这一非既定方案。
- **清理约定：仓库里没有**。grep 全仓：`mw.py` 对 `.mw/*.lock` 零处理（无启动清理、无 doctor 项、无 `--fix` 路径）；`mw_common.py` 只在 `:1438-1439` 定义路径。唯一的 stale 处理是 conductor 的按需抢占（`conductor.py:98-133`，仅限它自己的 `roadmap/gates/key-*/workers` 锁）。⇒ 新锁的残锁清理**要么写进错误提示（人工），要么按 §2.4 选项 2 显式实现"只提示不抢占"**；不要指望既有机制兜底。
- 锁文件是**空文件**：不会带凭证、不会进 git、不进任何 doctor 输出（`mw_common.py` 无锁的 doctor 段）⇒ 无安全/展示面。

## 7. 复现方式（脚本在 `%TEMP%\mw-rqd4\`）

| 脚本 | 覆盖 |
|---|---|
| `exp1_lock.py` | A1~A4、A6~A8（原语语义、默认退避 14.56 h、stale、崩溃残锁、8 进程互斥/无锁基线） |
| `exp1b_lock.py` | A5（conductor 30 s stale 抢占 + timeline 事件，走真实 `.mw/<name>.lock` 路径） |
| `exp2_lost_update.py` | D1（无锁交错）、D2（**CLI-only 锁仍丢**）、D3（跨语言同锁串行）、D7（持锁 ⇒ rc=1 + 字节不变） |
| `exp3_storm.py` / `exp3b_storm.py` | E1/E2/E3（30 轮 storm：双锁 0 丢失、CLI-only 丢、无锁 PermissionError） |
| `exp4_tmp_collision.py` | F1（TS-TS 无锁 4/30 硬失败）、F2（Py-Py 无锁 PermissionError）、F3（TS-TS 双锁 0 失败） |
| `exp5_windows.py` | RMW 窗口 60 次采样（median 0.814 ms）+ 各预算退避和 |
| `exp6_recheck.py` | G1（仅锁 ⇒ 静默回滚）、G2（锁+写前校验 ⇒ 中止并保住对方写） |
| 辅助 | `py_cli.py`（Python 侧写者，`locked/unlocked/locked-failfast`）、`py_cli_recheck.py`、`node_console.mjs`（**用 `packages/coding-agent/dist/.../status-model.js` 的真 `readConfig/saveConfig` + `shared/file-lock.js` 的真 `acquireLock`**） |

关键形状（可直接搬进测试）：

```python
# Python 侧（CLI）
cfg["xkey_verify_cmd"] = argv
mw_common.acquire_lock(lock, retries=6, base_delay=0.02)
try:
    cfg = ap_config.load_config(root)      # 锁内重读
    cfg["xkey_verify_cmd"] = argv
    ap_config.save_config(root, cfg)
finally:
    mw_common.release_lock(lock)
```

```js
// TS 侧（console）：dist 的真实 API 组合
const release = await acquireLock(configLockPath(root), { retries: 6, baseDelayMs: 20 });
try {
	const r = readConfig(root);            // 锁内重读
	saveConfig(root, { ...r.config, enabled });
} finally { release(); }
```

注意：TS 的实验是用**已构建的 dist**（`packages/coding-agent/dist/extensions/agent-team-loop/...`，Node v24 可直接 `import()`）验证的，未改动源码；Python 直接 import `packages/multi-workers/autopilot/config.py`。

## 8. 待 PM/用户定稿的决策（design 期）

| 编号 | 决策 | 建议 | 不选的后果 |
|---|---|---|---|
| U-7 | 锁路径：专用 `.mw/autopilot-config.lock` vs spec §2.3 字面的 `lock_path`（=`workers.lock`） | **专用**（两侧同名 helper，见 §5.1） | 用 `workers.lock` 也满足 AC-011，但让配置写与派单/worker 表写互相串行（错失无关资源），且 `mw_common.lock_path()` 的语义（"workers"）被滥用 |
| U-8 | TS 侧改动是否属本 key 范围 | **属**（`status-model.ts` 加 `configLockPath`/`saveConfigLocked`，`console.ts:287,339` 切过去，`cmdSetPaused` 改 async） | AC-011 可用"守锁的桩 console"判绿，而生产仍是 D2/E2 的丢更新 —— 空心测试 |
| U-9 | 残锁策略 | 不自动抢占 + 错误提示人工删除；可选"锁龄 > 60 s 时提示疑似残留"（不抢占） | 崩溃后需人工删；或引入双写风险（若选自动抢占） |
| U-10 | 是否加"写前重读校验"兜底 | **不加为 AC 判据**；若要加，作为 CLI 的额外防御（G2 形状可断言：rc≠0 + 不写） | 无（仅少一层对"不守锁写者"的单向兜底） |
| U-11 | 重试预算是否做成可注入常量 | **做成模块常量 + 测试 monkeypatch**（TS 用 `lockOpts`） | 用例每次真等 1.26 s；或为图快把预算写成 0 重试（正常争用下会误报失败） |
| U-12 | AC-011 措辞 | 按 §5.3 的三段式细化（CLI 断言 + TS 断言 + 明确 TS 改动在范围内） | 判据与生产行为脱钩（见 U-8） |

旁证（不在本 AC 范围，登记备查）：`mw model set/clear` 的 `_model_write`（`mw.py:3116-3126`）同样是无锁 RMW ⇒ 若将来有第二个写者（例如窗口内改 dispatch.yml），会遇到同一类问题。
