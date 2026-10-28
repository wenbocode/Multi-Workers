type: coding
key: mw-dynamic-concurrency
batch: B2
card: T-C-M04-dispatch-identity-dedup
phase: execute
goal: .agenticdoc/goal.md

# T-C-M04 · 派发层 identity 级去重（`dispatch.py` 独占写面）

## 上下文

- 目标（本 key）：把 autopilot 的并发从"静态上限 2 的 key 层"改成"依赖前沿驱动、按前沿动态最大化"，并且**先有写面判定再放开并发**（D-018）。前置 key `mw-write-face-guard` 已 DONE（写面判定 + 拒绝审计 + 单写者临界区）。
- 本卡是 MDC 的 **B2**：只做**派发层的 identity 级去重**，不碰前沿、不碰配置、不碰面板。
- 关键人物/事实（PM 已实测，行号以当前工作树为准）：
  - `packages/multi-workers/autopilot/dispatch.py:1238` `def dispatch(...)` —— 唯一派发入口；`:1428` `mw_common.acquire_lock(lock)`；`:1444` 写面判定 `_write_face_verdict(...)`（**已在锁内**，AC-014）；`:1453-1454` `task_dir.mkdir` + `task_md.write_text`；`:1478` `mw_common.upsert_worker_row(wpath, row)`；`:1481` `release_lock`。
  - `upsert_worker_row` 的语义是"**按 `task_key` 替换首行**，无则追加"（见 `dispatch.py:1468-1478` 注释；TS 侧 `WorkerStore.upsert` 同义）。**它不区分旧行是否仍在飞** ⇒ 同一 `task_key` 的第二次派发会把在飞行覆盖成新的 `pending` 行、并重写 `task.md`。
  - 这就是 `.agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` 记录的 **RF-1..RF-4 重复激活缺陷**的机制面：同一 `task_key` 出现多个 worker 实例、共写一份 `output.md`。该缺陷此前未定位到 spawner；本卡的 identity 判定是**它的根修候选**。
  - 判据必须是 **identity 级**（"同一 `task_key` 是否已非终态"），**不是行数**：`upsert` 覆盖语义下行数恒为 1。验收判据 = **`ok=True` 次数 == 1** 且 **timeline `dispatch` 事件数 == 1**。
  - **禁止嵌套加锁**：`acquire_lock` 在已持锁时退避 14.6 h 后抛 `RuntimeError`（RQ-D3 实测，见 `dispatch.py:1440-1443` 注释）。
  - 终态集合的唯一来源是 `mw_common._TERMINAL_STATUSES`（`dispatch.py:1160` 已在用，`conductor.py` 的 `_is_in_flight` 同源）——**不得自建状态集**。
  - 写面判定与审计（WFG 产物，只读复用）：`_card_write_face_entries` `:1022`、`render_write_face_line` `:1059`、`_write_face_audit` `:1089`、`_write_face_verdict` `:1118`；拒绝码 `WRITE_FACE_AUDIT_*` `:1000-1002`。

## 要求

1. 在 `dispatch()` **已持有的** `workers.lock` 临界区内（`acquire_lock` 之后、`upsert_worker_row` 之前），加入 **identity 级去重判定**：
   - 读实时队列（`mw_common.parse_workers_file(wpath)`），找出与本次 `task_key` 相同的行；
   - 若其中存在 **非终态**（`str(row.get("status","")) not in mw_common._TERMINAL_STATUSES`）的行 ⇒ **拒绝本次派发**并返回 `DispatchResult(ok=False, reason=...)`：`reason` 需自解释（沿用既有 reason 前缀风格，如 `duplicate-dispatch: <task_key> already in flight (<status>)`，具体文案由你定，但必须是稳定可断言的字符串）；
   - **拒绝必须零副作用**：不得 `mkdir`、不得写 `task.md`、不得写队列行、不得产生第二次 `dispatch` timeline 事件（与 `:1447` 的写面拒绝同形）。
2. **终态行必须仍可重派**：同一 `task_key` 的旧行已终态（`done/failed/...`）时，沿用现有 `upsert` 行为（retry 复用同一 identity），**不得**把重试路径一起堵死。
3. **不得嵌套加锁**：判定必须发生在已持锁的临界区内，不得再 `acquire_lock`。
3b. **拒绝必须落在"等待下一 tick"族里，否则会造出永久 stall**（PM 已定的判面，必须实现）：`conductor.py` 的 `execute_loop` 对 `ok=False` 只放行 `_write_face_wait_reason(...)`（`:2077`）命中者，其余一律 `mark_stalled`。因此本卡包含一处**有界**的 `conductor.py` 改动：
   - 把拒绝 `reason` 的前缀**固定**为 `duplicate-dispatch:`（形如 `duplicate-dispatch: <task_key> already in flight (<status>)`）；
   - 在 `conductor.py:1857` 的 `_WRITE_FACE_WAIT_REFUSALS = ("write-face-overlap", "write-face-undeclared")` 元组内追加 `"duplicate-dispatch"`，并把 `:1851-1856` 的注释改为说明"该元组现在是**派发等待类**拒绝：写面 serial-only/overlap（WFG W-03）+ identity 级重复派发守卫（MDC M-04）"；
   - **常量名与 `_write_face_wait_reason` 函数名保持不变**（不改名、不移动、不改语义；仅注释 + 元组元素）。`conductor.py` 内**只准**改这两处（`:1851-1857` 注释与元组、以及必要时的 `reasons` 相关注释），**不得**改动 `conductor.py` 的任何其它字符。
   - 证据里必须包含：`duplicate-dispatch` 拒绝时**不发生** `mark_stalled` 的观测（例如该 key 状态仍为 `running`、`stalls` 计数不变）。
4. **事件词表冻结**：不得新增 timeline 事件名。若需要审计行，复用既有事件（`dispatch` / `config` / 既有写面审计事件），并说明复用的是哪一个。
5. 不得改动 `_write_face_verdict` 的判定语义与拒绝文案（WFG 已冻结的 AC；本卡只在其**之后**加一层 identity 判定）。
6. 若发现同一 `task_key` 的非终态行**本不该存在**（例如 PM/TS 侧手工插入），你的行为仍必须是"拒绝 Python 侧再派发"，不得清理/改写他人行。

## 交付格式

- 只写一个证据文件：`.agenticdoc/mw-dynamic-concurrency/evidence/M-04-dispatch-dedup.md`（唯一证据文件），必须含：
  1. **before→after**：`dispatch.py` 修改点的 `file:line` + 代码片段（before 取 `git show HEAD:`，after 取工作树）；
  2. **双进程/双入口对拍原始输出**：`direct dispatch()` 与 `conductor.tick` 两个入口对同一 `task_key` 各跑一遍，5 连跑，输出 `grants=1 refusals=1 rows=1`；
  3. **基线对照**：改动前同场景的 `dispatch` 事件数 = 2 / 行数 = 1（证明判据不是行数）；
  4. **终态重派正例**：旧行终态时仍能 `ok=True`；
  5. 全量 `python -m pytest -q` 的原始 tail + 退出码；
  6. 可复跑的探针脚本（附录，放在 `packages/multi-workers/` 下运行，跑完删除；或在 `_scratch` 下但需在证据里注明运行位置——注意探针若用 `__file__` 推导仓库路径，必须在原位置运行）。
- `output.md` 按五段契约写（`[VERIFY]` 行 + 改动清单 + 残留与未验证 + 上下文来源）。

## 写入允许面

- `packages/multi-workers/autopilot/dispatch.py`（**唯一写者**）
- `packages/multi-workers/autopilot/conductor.py`（**仅限**要求 3b 列出的 `_WRITE_FACE_WAIT_REFUSALS` 元组 + 其上方注释；其它字符一律不得改）
- 新建探针脚本（临时，`packages/multi-workers/` 下，跑完删除）
- `.agenticdoc/mw-dynamic-concurrency/evidence/M-04-dispatch-dedup.md`（唯一证据文件）
- 测试文件**仅当你需要**：`packages/multi-workers/test_write_face_dispatch.py`（既有，若断言因 identity 判定翻动，做最小对齐，不得放宽）

## 写入禁止面

- `packages/multi-workers/mw_common.py`、`mw.py`、`launcher.py`（**另一 session 的活跃写面，只读**）
- `packages/multi-workers/autopilot/config.py`、`task_graph.py`（他人写面）；`conductor.py` 除要求 3b 列出的两处外**一律禁改**
- 所有 `packages/coding-agent/**`（TS 侧、`dist/**`、语料 `test/fixtures/*.json`）——本卡纯 Python
- 任何 `git` 写操作（`add`/`commit`/`checkout`/`stash`）、`npm run check`（P-017）、无文件参数的 vitest（P-032）
- 不得删除/跳过/放宽任何既有断言

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q
python -m pytest test_write_face_dispatch.py -q
```

## 改动历史

- `packages/multi-workers/autopilot/dispatch.py:1238` `def dispatch(` —— 派发入口（本次插入点所在函数）
- `packages/multi-workers/autopilot/dispatch.py:1428` `mw_common.acquire_lock(lock)` —— 临界区起点
- `packages/multi-workers/autopilot/dispatch.py:1444` `_write_face_verdict(...)` —— 既有锁内判定（写面，AC-014），本卡的 identity 判定插在其后
- `packages/multi-workers/autopilot/dispatch.py:1453-1454` `task_dir.mkdir` / `task_md.write_text` —— 必须在 identity 判定通过后才执行
- `packages/multi-workers/autopilot/dispatch.py:1478` `mw_common.upsert_worker_row(wpath, row)` —— 按 `task_key` 替换首行（不区分在飞）
- `packages/multi-workers/autopilot/dispatch.py:1481` `mw_common.release_lock(lock)` —— 临界区终点
- `packages/multi-workers/autopilot/conductor.py:1857` `_WRITE_FACE_WAIT_REFUSALS = ("write-face-overlap", "write-face-undeclared")` —— 等待类拒绝前缀集（本卡追加 `"duplicate-dispatch"`，并更新其上方 `:1851-1856` 注释）
- `packages/multi-workers/autopilot/conductor.py:1867` `return str(reason).startswith(_WRITE_FACE_WAIT_REFUSALS)` —— 判定本体（不改）
- `packages/multi-workers/autopilot/conductor.py:2077` `if _write_face_wait_reason(result.reason): … return dispatched_any` —— 等待而非 stall 的调用点（不改）
