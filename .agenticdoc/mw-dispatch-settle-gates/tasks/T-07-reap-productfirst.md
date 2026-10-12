# T-07 — AC-006：launcher reap 改 product-first（先读 `run.json`，退出码仅兜底）

- key: `mw-dispatch-settle-gates`｜AC: **AC-006**｜VC: **VC-030**｜波次 **1**｜独立卡
- 角色: coding（Python 侧）
- **唯一允许改的路径**：① `packages/multi-workers/launcher.py`；② 测试：`packages/multi-workers/test_launcher.py` 或新建 `packages/multi-workers/test_mwds_t07_reap_productfirst.py`（**优先新建**，避免与他人重叠）；③ 自身目录 `report.md`
- 上游：`design.md` DD-06/DD-11；`plan.md §6`（`launcher.py` 被 14 个项目共用 ⇒ 只做向后兼容新增）

## 现状（以符号名为准）
- 队列终态行由 launcher reap 写入（约 `:838-844`），**只看退出码**：`_exit_to_status`（约 `:367-373`）。
- `mw_common.read_run_status(task_dir)`（`mw_common.py:1747`）与 `RUN_TERMINAL_STATUSES`（`:1719`）**已存在**；launcher 的 stale reconcile 已在用同样的读法（约 `:2449-2457` 同文件另一处 / `mw_common.ts` 对应）⇒ 本卡应复用同一读取器（单一真相源）。
- 缺口：exit 0 但无产物时，队列行仍被写成 `done`（缺口 G-f 的 Python 半）。

## 必须实现
1. reap 路径 **product-first**：先 `mw_common.read_run_status(<task_dir>)`；
   - 命中 `RUN_TERMINAL_STATUSES` ⇒ **以 run 状态为准**写队列行（`done`/`failed`/`needs-clarification`/`lost`）；
   - `run.json` 缺失或状态非终态 ⇒ **退回** `_exit_to_status(exit_code)` 既有行为（零回填，逐字同今日）；
   - 退出码 2 ⇒ `needs-clarification`（与 T-04 的 TS 侧折码对齐）。
2. 冲突记录：run 状态与退出码**不一致**时（如 run=needs-clarification / exit=0，或 run=done / exit≠0）写一条 `launcher.log` 行（含 taskKey、两个值、采用值），便于 PM 事后核对；不得静默。
3. **向后兼容**：`read_run_status` 已在用，不得改其签名/语义；不得向 stdout 打印（`mw doctor` JSON 契约）；不改 `test_common.py`。
4. 不引入新概念/新文件（不新增状态名，不新增配置键）。

## 反向用例（必须真跑并贴输出）
- (a) `run.json status=needs-clarification` + `exit=0` ⇒ 队列行 = `needs-clarification`（不是 `done`）；
- (b) `run.json status=done` + `exit=0` ⇒ `done`（不回归）；
- (c) `run.json` 缺失 + `exit=1` ⇒ `failed`（与今日逐字一致）；
- (d) `run.json status=lost` ⇒ `lost`（T-20 语义保持）；
- (e) 不一致场景 ⇒ `launcher.log` 出现冲突行且含两个值。

## 对照协议（`plan.md §5`）
A 摘除 run 状态优先分支（改回只看退出码）⇒ (a) 转红；B 反转默认（无 run.json 即写终态）⇒ (c) 转红；C 删掉冲突日志行 ⇒ (e) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-030: nc_exit0_row=needs-clarification done_exit0=done missing_run_exit1=failed lost=lost conflict_logged=true
```
命令：`cd H:/git/Multi-Workers && python -X utf8 -m pytest packages/multi-workers/test_mwds_t07_reap_productfirst.py -q`（跑完并贴输出）

## 禁止
不改 `mw_common.py`（T-08 所有；本卡只读引用）；不改 `autopilot/*`；不改 `test_common.py`；不重启任何 serve/launcher 进程（**不得** kill PID 122476/142424 或任何他项目进程）；不 build；不 commit；不写远端队列文件（测试用 tmp 目录）。
