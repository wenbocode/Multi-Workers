# T-09 — AC-002：门提醒加 stage 终态判据（两级解析 + fail-open）

- key: `mw-dispatch-settle-gates`｜AC: **AC-002**｜VC: **VC-004…VC-008**｜波次 **1**｜独立卡
- 角色: coding（Python 侧）
- **唯一允许改的路径**：① `packages/multi-workers/autopilot/conductor.py`；② 新建 `packages/multi-workers/test_mwds_t09_gate_stage_terminal.py`；③ 自身目录 `report.md`
- 上游：`design.md` DD-11；证据 `evidence/research/spec-stage-terminality-20261010.md`（RQ-1 全锚点）；缺口 G-b

## 现状（以符号名为准）
- 判定链：tick（约 `:2761` 使能/暂停、`:2764` 一拍、`:2777`+ 提醒）→ `_remind_pending_gates`（约 `:2555-2585`，`:2564` 读 gates 目录）→ `pending_gate_reminders`（约 `:2522-2553`，条件在 `:2533-2551`）。
- stage 终态族已存在：`_STAGE_STATUS_RANK`（约 `:557-564`，`pending`/`approved`=0、`running`=1、`closed`/`closed-human`/`halted`=2）、`_STAGE_TERMINAL_RANK = 2`（约 `:565`）；唯一写者 `_set_stage_status`（约 `:605-639`，单调守卫 `_stage_transition_allowed` 约 `:568`）。
- roadmap 解析：`roadmap.stage_of_key`（`roadmap.py` 约 `:477-483`）。
- 8 个 gate 创建点中只有 4 个带 `stage=`（约 `:659`/`:725`/`:903`/`:3586`；`:1254`/`:2792`/`:3934`/`:5187` 不带）⇒ **两级解析必需**。
- 既有 12 条提醒测试 fixture **无 `_roadmap.md`** ⇒ **必须 fail-open**（否则既有测试全红）。
- 口径分歧（须显式取 conductor 口径）：`halted` 在面板侧有另一套口径（`status-model.ts` 约 `:1393-1399`）；本卡只处理 conductor 侧提醒。

## 必须实现
1. `pending_gate_reminders(gates, now, ..., stage_status=None, stage_of_key=None)`：**新增两个可选参数**（关键词形式，缺省 ⇒ 不做抑制）；第 4 条件 = "该门的 stage 若解析到且处于终态（rank ≥ `_STAGE_TERMINAL_RANK`）⇒ 不提醒"。
2. **两级解析**：`gate.stage` 优先；缺失 ⇒ `stage_of_key(key)`；都解析不到 ⇒ **不抑制**（fail-open）。
3. `_remind_pending_gates` 每拍读 **一次** roadmap 并注入 `stage_status` + `stage_of_key`（不得 N 次读盘）；roadmap 文件缺失/损坏 ⇒ 传 `None` ⇒ 不抑制 + 一条 `conductor.log` 诊断（不得抛错、不得静默）。
4. 终态族必须消费 `_STAGE_TERMINAL_RANK`（单一真相源，不得内联复制 `{"closed","closed-human","halted"}`）。
5. 不得改动 `gates.py`（`pending_gates` 语义不变）；不得改变提醒文本与节流语义。
6. 幂等/性能：每拍最多读一次 roadmap（断言读盘次数）。

## 反向用例（必须真跑并贴输出）
- (a) stage=`closed` + pending 门 ⇒ **零提醒**；(b) stage=`halted` ⇒ 零提醒；(c) 无 `gate.stage` 但 `stage_of_key` 解析到 `closed` ⇒ 零提醒（两级解析）；(d) 无 `_roadmap.md`（既有 12 条测试形态）⇒ **照旧提醒**（fail-open，逐字通过）；(e) stage=`running` + pending ⇒ 照旧提醒（不误伤）；(f) roadmap 损坏（非法 JSON）⇒ 照旧提醒 + 诊断行；(g) 每拍 roadmap 读取次数 = 1。

## 对照协议（`plan.md §5`）
A 摘除第 4 条件 ⇒ (a)(b)(c) 转红；B 反转默认（解析不到即抑制）⇒ (d)(f) 转红；C 把终态族内联复制并删掉 `halted` ⇒ (b) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-004: consumes=_STAGE_TERMINAL_RANK inline_copy=0
[VERIFY] VC-005: no_gate_stage_resolved=3/4 call_sites
[VERIFY] VC-006: no_roadmap_reminders=12/12 unchanged
[VERIFY] VC-007: halted_reminders=0 panel_unchanged=true
[VERIFY] VC-008: running_stage_reminders=1
```
命令：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t09_gate_stage_terminal.py packages/multi-workers/test_autopilot_gate_reminder.py -q`（贴输出）

## 禁止
不改 `autopilot/gates.py` / `autopilot/roadmap.py` / `autopilot/monitor.ts`；不改 `test_common.py`；不重启任何进程；不 build；不 commit；不得新增持久化文件。
