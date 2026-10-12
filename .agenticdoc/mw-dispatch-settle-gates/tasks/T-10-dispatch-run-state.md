# T-10 — AC-004：Python 派发判据首查 `run.json`（终态/running 不派，缺失放行）

- key: `mw-dispatch-settle-gates`｜AC: **AC-004**｜VC: **VC-012…VC-014**｜波次 **1**｜独立卡
- 角色: coding（Python 侧）
- **唯一允许改的路径**：① `packages/multi-workers/autopilot/dispatch.py`；② 新建 `packages/multi-workers/test_mwds_t10_dispatch_run_state.py`；③ 自身目录 `report.md`
- 上游：`design.md` DD-12；缺口 G-d（D-038 边界）；`plan.md §6`

## 现状（以符号名为准）
- 缺口证据：`rg 'run\.json' packages/multi-workers/autopilot/dispatch.py` = **0 命中** ⇒ Python 派发链完全不读 run 身份（上一 key 的 AC-022 只覆盖 TS 侧）。
- 现成读取器：`mw_common.read_run_status(task_dir)`（`mw_common.py:1747`）、终态集 `RUN_TERMINAL_STATUSES`（`:1719`，含 `lost`）。
- 队列写入段（`dispatch.py` 约 `:619-636`）已改槽位保留（`mw_common.upsert_worker_row`），本卡**不得**改动该段的写盘语义。
- 派发前判据（`dispatch_new_tasks` / 等价函数，`registry` 定义在约 `:71`）→ 需在**最早的"是否可派"判定**处插入本判据。

## 必须实现
1. 在派发判据**最早处**插入：`st = mw_common.read_run_status(task_dir)`；
   - `st in RUN_TERMINAL_STATUSES` ⇒ **不派**，返回可读原因（如 `reason="run-terminal:<status>"`），并保持既有 `DispatchResult` 字段语义（新增 reason 取值，不改字段名）；
   - `st == "running"` ⇒ **不派**（另一进程正在跑，防重复执行）；原因 `run-running`；
   - `st is None`（无 `run.json`）⇒ **放行**（零回填，与今日逐字一致）；`st` 为非终态非 running 的其它值（若未来扩展）⇒ 放行并记 debug。
2. 判定必须在**任何** mkdir / task.md 写入 / 队列入队**之前**（零副作用；断言拒绝时不产生 taskDir、不产生队列行）。
3. 复用 `mw_common` 现有读取器（不得新写 JSON 解析）；不得改 `run.json` 写入侧（launcher 的 `mark_run_lost` 不属本卡）。
4. 每次判定最多读一次 run 状态（断言读盘次数 ≤1/task）。

## 反向用例（必须真跑并贴输出）
- (a) `run.json status=done` ⇒ 不派 + 零副作用；(b) `status=needs-clarification` / `failed` / `lost` ⇒ 各自不派；(c) `status=running` ⇒ 不派；(d) 无 `run.json` ⇒ 派发（与今日一致，逐字回归）；(e) 拒绝路径：目录与队列字节**完全不变**（快照对比）。

## 对照协议（`plan.md §5`）
A 摘除 run 状态判据 ⇒ (a)(b)(c) 转红；B 反转默认（无 `run.json` 即不派）⇒ (d) 转红（证明零回填）；C 把判定挪到队列写入**之后** ⇒ (e) 转红（副作用检测）。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-012: terminal_statuses_block=4 (done,needs-clarification,failed,lost)
[VERIFY] VC-013: running_block=true
[VERIFY] VC-014: missing_run_dispatches=true zero_side_effect=true read_calls=1
```
命令：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t10_dispatch_run_state.py packages/multi-workers/test_autopilot_dispatch.py -q`（贴输出）

## 禁止
不改 `mw_common.py`（T-08 所有；本卡只读引用）、`launcher.py`（T-07）、`conductor.py`（T-09）、`gates.py`；不改 `test_common.py`；不重启任何进程；不 build；不 commit；不得新增持久化文件。
