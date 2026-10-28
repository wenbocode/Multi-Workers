# T-C-M02 · conductor tick 消费前沿 + roadmap 校验 + advance 打点（MDC B1）

- type: coding
- key: mw-dynamic-concurrency

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— conductor 的并发必须**由依赖推导**、动态最大化，而不是写死；本卡只改**前沿消费**（判面已由前置 key `mw-write-face-guard` DONE 落地，见 D-018）。
- **spec AC**: AC-001（实起 key 数 = `min(上界, |前沿|)`，≥3 组构造语料复算恒等）、AC-002（单 key 实起 worker 数 = `min(per-key 上界, |可并行任务前沿|)` 且不与在飞写面重叠）、AC-003（依赖/写面数据缺失或不可解析 ⇒ **该层回退串行实起 1** + 审计行，不得默认放大）、AC-006（上界=1 时两层都串行，无需重启 serve）、AC-010（key 层依赖图语义校验在 **tick 内**执行 + timeline 审计，且不改变 fail-closed 不派发）、AC-012（在飞口径单源，不得让覆盖点静默滞后）、AC-013（`advance.advance()` 不得成为并发瓶颈，或给出实测量化）。
- **design**: D-101..D-110（尤其 D-102 per-key 上界默认 4；D-105 锁内 identity 复查；D-107 先量化 advance 阻塞；D-110 区间写法判 Unsupported）。
- **计划**: `.agenticdoc/mw-dynamic-concurrency/plan.md` §2 M-02（本卡就是它）+ §3 串行点 + §5 风险。
- **前置已交付（只读复用，不得复制其实现）**: `packages/multi-workers/autopilot/task_graph.py`（M-01：`parse_card_deps` / V1–V7 校验 / `frontier(deps, terminal_ids)`；其单测 `test_task_graph.py` 已绿）+ `.agenticdoc/mw-write-face-guard/` 的写面判定结果。
- **定位锚点（本文件行号以 symbol 为准，实现前先 grep）**: `autopilot/conductor.py:1717` `_plan_task_order(stems, plan)`；`:1737` `execute_loop`；`:1765` 其调用点；`:1770-1771` **"见在飞即 return"（本卡要改的就是这里）**；`:744` key 层上界判定 `len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"]))`；`:698-704`/`:742` 在飞集合计算；`:1577` `_advance_key`；`:1536` `_record_advance_result`（`:1555`/`:1558` 写 `advance` timeline 事件的 `detail`）；`:3438` `st.timeline.append("beat")`（**beat 无载荷**）；`:6217` 一带**冻结的 reason/事件词汇表**。

## 写入允许面

- `packages/multi-workers/autopilot/conductor.py`（**唯一写者**）

## 写入禁止面

其余一切路径。特别地：`autopilot/dispatch.py`（M-04 独占，且必须晚于 WFG 的 W-03）、`autopilot/config.py` + `packages/coding-agent/src/extensions/agent-team-loop/autopilot/{status-model,monitor}.ts` + `test/fixtures/autopilot-config-corpus.json`（**M-03 正在并行改，别碰**）、`autopilot/task_graph.py`（M-01 成果，只读）、`packages/multi-workers/test_task_graph.py`、`mw_common.py`（其它 session 活动写面）、`packages/coding-agent/**`。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **前沿消费（AC-001/002）**：`_plan_task_order` 增加 `deps_by_stem` 形参（或等价入参），用 `autopilot.task_graph` 计算**可并行任务前沿**；`execute_loop`（`:1737`，调用点 `:1765`）把"见在飞即 return"（`:1770-1771`）改成**只在 `在飞数 >= min(per-key 上界, |前沿|)` 时才等**。per-key 上界**从配置读**，写法必须是 `int(cfg.get("max_workers_per_key", 4))`（D-102 默认 4；M-03 会把这个键正式写进 `config.py`——**你没有它也要能跑**，缺键时用 4，且不得把 4 硬编码成别的语义）+ 下限 1 保护。
2. **串行回退（AC-003/AC-010）**：任务图校验出任何 problem（悬空/自依赖/环/跨 key/重复/区间写法，见 D-110 与 task_graph 的 V1–V7）⇒ **该 key 整层回退串行（实起 1）**并写 timeline 审计事件；**同一 problem 每个 stage 只写一次**（去重，避免每 tick 抖动刷屏）。tick 内还要调用 key 层的 roadmap 语义校验（AC-010：今天只有 CLI/doctor 会跑；函数名先 grep 确认），悬空/环/前向 stage 写审计事件，**不得改变** fail-closed 不派发的既有行为。
3. **`advance` 打点（AC-013）**：用**墙钟**量化 `advance.advance()`（`:1621`）的阻塞：在 `advance` 事件既有的 `detail` 里追加耗时（如 `ms=<n>`；`_record_advance_result:1555/1558` 是唯一写入点之一），并提供一个只读复算 `window_share = Σ advance_ms / Σ tick 墙钟` 的口径（写进 evidence，不必新增 CLI 子命令）。**不得新增 timeline 事件名**：`:6217` 一带是**冻结词汇表**，新名会被既有断言打死；用既有 `advance`/`config` 事件承载。
4. **在飞口径不动（AC-012）**：`_is_in_flight` / `_row_belongs_to` 的意义**只从原处导出**，本卡不得改其判据，也不得在别处复制一份"在飞"判断；`pending` 算不算、`manual` 行算不算槽位这两个子问题**按现状**（若你的改动会让某个覆盖点口径滞后，必须显式说明并给出同快照复算）。
5. **上界=1 回退（AC-006）**：`max_parallel_keys=1` 与 `max_workers_per_key=1` 时两层实起 ≤1，**不重启 serve**（读配置的地方本来就每 tick 重新读，确认这一点并在 evidence 里给复算）。
6. **不回归**：`packages/multi-workers` 全量 pytest 必须绿（你是 `conductor.py` 唯一写者，红了就是你改的）。

## 交付格式

`output.md` 五段齐全。`证据` 段必须给**可复跑原始命令 + 原始输出**：① `_plan_task_order` / `execute_loop` 的 **before→after 行号与代码片段**；② 用 ≥3 组构造语料复算 `min(上界, |前沿|)` 的恒等（含 |前沿|=0/1/N 与上界 1/N 组合）；③ V-problem 回退串行时的 timeline 事件**原始样例**（含"同 stage 只写一次"的去重证明）；④ `advance` 耗时的实测量化（`window_share` 或 N 倍 tick 延迟的原始数）；⑤ 全量 pytest 条数与退出码。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，说明它来自 `worker/output-writer.ts`，不影响判定。唯一证据文件：`.agenticdoc/mw-dynamic-concurrency/evidence/M-02-conductor-frontier.md`（把上面原始输出同时落这份证据）。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q
python -m pytest test_task_graph.py -q
```

（`conductor.py` 的既有相邻套件尤其要看：`test_autopilot_conductor*.py`、`test_autopilot_stall*.py`、`test_mwgal_t12_stage_close_auto.py`、`test_mwgal_t15_reattest_confirm.py`。）

## 改动历史

- 2026-10-14 WFG DONE（`_index.parallel` 已置 DONE）：写面判定 + dispatch 期拒绝落地，MDC 的"先判面再放开"前置满足 ⇒ 本卡开跑。
- 2026-10-14 M-01（`mdc-i01-task-graph`）已交付 `autopilot/task_graph.py` + `test_task_graph.py`（纯函数、无 I/O、不放开任何上界）。
- 本卡是 `conductor.py` 的**唯一写者**；M-03 同时在改配置/面板面，两者文件集不相交。

## 硬约束

- 只改 `conductor.py`；不得动 `dispatch.py`/`config.py`/TS 文件（并行卡与前置卡的面）。
- 不得新增 timeline 事件名（冻结词汇表 `:6217` 一带）；不得改 `_is_in_flight` 判据语义。
- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- 缺 `max_workers_per_key` 配置键时必须优雅退化（默认 4、下限 1），不得因缺键报错或串行化全系统。
