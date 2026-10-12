# T-07 回执：G2 pending-gate 提醒判定（Python 侧唯一判据 + ledger 计数）

- Key: `mw-gate-verdict-hardening`（phase=EXECUTE）｜ 卡: `tasks/T-07-gate-reminder.md`
- 基线: HEAD `776b82d7f`（任务书指定；卡面写 `10446aefb`，实际开工 HEAD 已推进，T-01/T-02 改动在工作树内）
- 依赖已确认: T-01 已落（`STALL_REASON_CODES` 含 `l3-aborted`，13 个 `mark_stalled` 调用点、`git diff` 可见）；T-02 已落（`config.DEFAULT_CONFIG` 20 键、`gate_reminder_after_min=(1,1440)` 默认 30、`gate_reminder_max=(1,2)` 默认 2）
- 写面（独占，未越界）:
  - `packages/multi-workers/autopilot/conductor.py` —— 只加 `tick` 段（新增 helper + `tick` 内一行调用），未碰 T-01 的 `_l3_*`/`l3abort:` 段与 T-10 的 `done` 段
  - `packages/multi-workers/test_autopilot_gate_reminder.py` —— **新建**

## 1. 交付要点逐条落点（`file:line`）

| 卡面交付点 | 落点 |
|---|---|
| 挂点：`tick` 内、`enabled/paused` 之后、goal 检测之前 | `conductor.py:2577` 调用 `_remind_pending_gates(project_root, st, cfg)`；紧跟 `:2580` 的 goal 检测（`current = goal_mtime_ns(...)`） |
| 事件名常量（T-03 已定义） | `conductor.py:2457` `GATE_REMINDER_EVENT = "gate-reminder"`（`timeline.py:105` 词表已在） |
| 纯判据（三条件同时成立） | `conductor.py:2475` `def pending_gate_reminders(...)` |
| 条件① 时间锚 = 门的 `created_at`，第 n 次在 `n × after_min` | `conductor.py:2497-2498`：`n = counts.get(gate.id,0)+1`；`anchor = mw_common._gate_created_epoch(gate.created_at)`；`(now-anchor) < n*after_min*60 -> skip`（**不用** `expires_at`） |
| 条件② 非终态行数 == 0（不是 `running` 口径） | `conductor.py:2494`：`if any(_is_in_flight(row) for row in rows): return []`；`_is_in_flight` 用 `mw_common._TERMINAL_STATUSES`（`conductor.py:2542`） |
| 条件③ 未 answered / 未达上限 | 输入即 `gates.pending_gates`（只含 `status=="pending"`）；`:2496` `if n > max_reminders: continue` |
| 计数载体：`auto-decisions.jsonl` 的 `phase:"remind"` 行 | `conductor.py:2533-2541`（写侧复用 `_append_auto_decision_row`）；读侧 `conductor.py:2461 def _reminder_count` 只数 `phase=="remind"` |
| 发 `gate-reminder` 事件，`data` 带门 id/key/年龄/第几次 | `conductor.py:2543-2560`：`data={gate_id, gate_kind, gate_key, reminder_n, waited_s, after_min}` |
| answered 即停（每 tick 重算，零残留） | `_reminder_count` 只从 ledger 读；输入门集来自 `pending_gates`，门一答即不在集合内（测试 `test_answered_gate_leaves_zero_residual`） |
| 不新增常驻组件/额外循环 | 只在既有 `tick` 主干插入一次函数调用，无新线程/循环/timer |
| 不改 doctor 阈值 | 未触碰 `mw_common.py`（24h/72h 零扰动） |

### 判定函数形状（纯判据 + 薄 IO 壳）

- 纯判据 `pending_gate_reminders(pending, rows, reminder_counts, now, after_min, max_reminders) -> [(gate, n)]`：无 IO、`now` 可注入（单测直接喂 epoch）。
- IO 壳 `_remind_pending_gates(project_root, st, cfg)`：`gates.pending_gates` → `parse_workers_file` → 读 ledger 计数 → 对每个 `(gate, n)` 追加 ledger 行 + timeline 事件。坏门队列 `except gates.GateFormatError: return`（与 `orchestrate` 同 skip 策略，`tick` 后面自己的 goal 检测会记 `config` 事件）。
- 配置读取用 `cfg.get("gate_reminder_after_min", 30)` / `cfg.get("gate_reminder_max", 2)`，且 `_load_effective_config` 已返回完整 20 键视图（`conductor.py:108`）。

## 2. [VERIFY]（命令原文 + 真实输出）

### ① `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_reminder.py -q -p no:randomly`

```
............                                                             [100%]
12 passed in 0.33s
```

（`-s` 时的机器可读输出：`[VERIFY] VC-007 pure_decision=ok cap_enforced=true non_terminal_only=true` / `[VERIFY] VC-007 ledger=1 event=1 reminder_n=1` / `[VERIFY] VC-008 rows=2 blocked_third=true` / `[VERIFY] VC-009 residual=0` / `[VERIFY] VC-010 in_flight_silent=true` / `[VERIFY] VC-010 blocked_only_on_human_silent=true` / `[VERIFY] VC-007 goal_change_reminder=1`）

### ② `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py test_doctor_gates.py -q -p no:randomly`

```
FAILED test_autopilot_auto_decision.py::test_reason_code_closed_set_is_closed
FAILED test_autopilot_auto_decision.py::test_all_twelve_mark_stalled_call_sites_pass_a_reason_code
2 failed, 84 passed, 56 warnings in 24.41s
```

**与开工前基线逐字一致**（改前同命令 = `2 failed, 84 passed, 56 warnings in 25.03s`，两条红同为 `== 12` 计数锁）⇒ 本卡零回归。两条红归 T-14（`STALL_REASON_CODES` 12→13），未去改。

### 附：卡面提到的 timeline 计数锁现状（归属 T-14）

`python -X utf8 -m pytest test_autopilot_timeline.py -q -p no:randomly` →

```
E       AssertionError: assert 26 == 23
E        +  where 26 = len(frozenset({... 'contract-refused' ... 'gate-reminder' ...}))
1 failed, 15 passed in 0.21s
```

`26 == 23` 正是 T-03/T-05 加 3 个事件名后的冻结计数（`gate-reminder`/`l3-aborted`/`contract-refused`），归 T-14；未改。

### 附：相邻套件回归

- `python -X utf8 -m pytest test_autopilot_conductor_stage.py -q -p no:randomly` → `11 passed`
- `python -X utf8 -m pytest test_autopilot_pending_review.py -q -p no:randomly` → `28 passed`

## 3. 非空洞对照（三组，真跑，红/绿实贴）

### 对照 1：改用 timeline 尾窗作计数载体 ⇒ 第 3 次提醒用例转红

把 `_remind_pending_gates` 的计数从 `_reminder_count(ledger)` 改为 `timeline.tail_events(limit=200)` 里按 `gate_id` 数 `gate-reminder` 事件（即 `_timeline_has_event` 的朴素前身）：

命令 `python -X utf8 -m pytest test_autopilot_gate_reminder.py -q -p no:randomly` →

```
FAILED test_autopilot_gate_reminder.py::test_second_reminder_at_two_times_threshold
FAILED test_autopilot_gate_reminder.py::test_third_reminder_blocked
FAILED test_autopilot_gate_reminder.py::test_third_reminder_blocked_after_timeline_tail_eviction
3 failed, 9 passed in 0.40s
```

其中专项对照 `test_third_reminder_blocked_after_timeline_tail_eviction` 的红：

```
E       AssertionError: assert 3 == 2
E        +  where 3 = len([... {'detail': 'seed', ...}, ... {'detail': 'pending 120m >= 30m', ...}])
```

证明：制造 >200 条 beat 让 n=1/n=2 的 `gate-reminder` 事件滚出 `tail_events(200)` 后，尾窗计数“复活”成 0，重复发第 1 次；ledger 方案不复活。**ledger 计数载体是必要的**。

### 对照 2：把挂点从 `tick` 移到 `orchestrate` ⇒ goal-change 门用例转红

把 `:2577` 的调用移到 `orchestrate` 顶部（`cfg` 加载之后）：

```
FAILED test_autopilot_gate_reminder.py::test_goal_change_gate_reminds_while_halted
E       assert (0 == 1)
E        +  where 0 = len([])
1 failed, 11 passed in 0.31s
```

只有 goal-change 用例转红：`tick` 在 `orchestrate` 之前就 `return "halted-goal-change"`（`conductor.py:2628-2631`），挂在 `orchestrate` 的提醒对未答 goal-change 门永不触发。**挂点必须在 `tick`。**

### 对照 3：条件② 从“非终态行数 == 0”改成“`running` == 0” ⇒ 有非终态（pending）行的用例转红

把 `pending_gate_reminders` 的 `any(_is_in_flight(row) ...)` 改成 `any(row["status"]=="running" ...)`：

```
FAILED test_autopilot_gate_reminder.py::test_pure_decision_three_conditions
FAILED test_autopilot_gate_reminder.py::test_pending_row_also_suppresses_reminder
E       AssertionError: assert [{'detail': '...talled', ...}] == []
2 failed, 10 passed in 0.46s
```

判据口径的分水岭是 `pending` 行（非终态、非 `running`）：正确实现抑制提醒，`running`-only 实现误报。`test_running_row_suppresses_reminder` 在两种实现下都绿（不是判别项），`pending` 行用例才是——与 design D-008「两侧统一非终态口径」一致。

（三组对照均已在跑完后**立即还原**；`grep COUNTERFACTUAL conductor.py` = 0 命中；最终 `conductor.py` diff = `276 insertions(+), 26 deletions(-)`，其中 26 deletions / 158 insertions 为 T-01 既有改动。）

## 4. 契约与边界核对

- **时间锚**：只用 `gate.created_at`（`mw_common._gate_created_epoch`，doctor 同源）。测试 `test_pending_past_threshold_reminds_once` 断言该门 `expires_at is None`（历史 v1 形状）仍然触发 ⇒ 满足「禁用 `expires_at`」。
- **计数载体审计**：新增 `test_remind_rows_are_invisible_to_decide_consumers` 直接断言 `_effective_auto_decision`/`_escalate_recorded`/`_shadow_decision_recorded`/`_defer_recorded`/`auto_consumption_set` 对 `phase:"remind"` 行全部不可见（对齐 D-006 的 8 处消费者审计）。
- **第二写者核查**：全仓 grep `auto-decisions.jsonl` / `auto_decisions_path` 后确认只有 `conductor._append_auto_decision_row`（`conductor.py:5861`）一个 append 写者（`dist/` 为构建产物）。**未发现第二写者**，无需回报。
- **多窗口推送作用域（卡面第 4 点）**：`notified`/`escalated` Set 与「按 `gate.key` 作用域、stage 级门只推一次」是 `pm-orchestrator.ts` 的 T-09 写面（T-09 卡原文）。T-07 在 Python 侧的职责边界是：计数按 `gate.id` 保证「同一门 ≤2 次」，并把 `gate_key` 放进事件 `data`，供 T-09 做 `watch.key == gate_key` 作用域化与 session 水位去重。未在 conductor 里造第二套 TS 去重。
- **GC-1**：未新增常驻组件/线程/timer；只在既有 `tick`（唯一每-tick 主干）多一次纯文件读 + 零到两次 append。
- **doctor 零扰动**：`mw_common.py` 未出现在本卡 diff 中；24h/72h 阈值未动。
- **敏感数据**：测试全部在 `tmp_path` 下运行，未触碰 `.agenticdoc/_workers.parallel` / `_workers.acked` / `_autopilot/auto-decisions.jsonl` 等真实运行数据；未 kill 任何进程。

## 5. AC / VC 映射

| AC / VC | 证据 |
|---|---|
| AC-005（超阈产生提醒，同门 ≤2） | `test_pending_past_threshold_reminds_once`（VC-007）+ `test_second_reminder_at_two_times_threshold` + `test_third_reminder_blocked`（VC-008）+ 对照 1 |
| AC-006（answered 即停，零残留） | `test_answered_gate_leaves_zero_residual`（VC-009） |
| AC-007（只对 pending 生效；EXECUTE 稀疏不触发） | `test_running_row_suppresses_reminder` + `test_pending_row_also_suppresses_reminder`（VC-010）+ `test_terminal_rows_do_not_suppress` + 对照 3 |
| VC-007/VC-008/VC-009/VC-010 | 见上；`-s` 输出含 `[VERIFY]` 行 |
| goal-change 早退覆盖（DRQ-2 F2.0 硬结论） | `test_goal_change_gate_reminds_while_halted` + 对照 2 |

## 6. 未决 / 移交

- T-09（PM 侧消费者）：读 `auto-decisions.jsonl` 的 `phase=="remind"` 行 → `deliverPmAlert`，并实现 `gate.key` 作用域 + 会话水位去重（本卡只保证事件 `data.gate_key` 与每门 ≤2 的计数）。
- T-14（计数锁）：`test_autopilot_auto_decision.py` 的 `== 12`（2 红）与 `test_autopilot_timeline.py` 的 `== 23→26`（1 红）按预期红，不在本卡写面。
- 并发告警（照实记录）：开工期间 T-04 在改 `autopilot/gates.py`、T-06 在跑 T-01 对照；本卡未触及这些文件，未观察到与本题相关的瞬时失败。
