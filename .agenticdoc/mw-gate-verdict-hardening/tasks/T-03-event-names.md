# T-03: 三个 timeline 事件名（`l3-aborted` / `gate-reminder` / `contract-refused`）

- 波次: **0** · 依赖: —
- 写面（独占）:
  - `packages/multi-workers/autopilot/timeline.py`（`EVENT_TYPES`）
- AC: AC-001, AC-005, AC-011 · VC: VC-001, VC-007
- 基线: `10446aefb`

## 目标

把三个新事件名登记进时间线词汇表，使 `T-01`/`T-07`/`T-10` 发射它们、`T-05` 能镜像、`T-14` 能锁集合相等。

## 交付物

- `EVENT_TYPES` 增 **3** 个名字：`l3-aborted`、`gate-reminder`、`contract-refused`（Python 侧半边）。
- 追加处带注释，说明"先接词汇、后接生产者"是既有先例（`timeline.py` 的 pre-admitted 注释段）。

## 契约（不得重定义）

- 事件名**逐字**为本卡三个，不得改写、不得加前缀（`T-05`/`T-14` 以逐字相等断言）。
- `Timeline.append` 的 "Never raises" 语义不动：写入侧不校验，读取侧 include-set 过滤。
- 本卡**只加名**，不发射、不消费、不改 Python 计数测试（计数锁由 `T-14` 统一刷新，避免与 `T-05` 抢同一条锁）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -c "from autopilot import timeline; t=set(timeline.EVENT_TYPES); assert {'l3-aborted','gate-reminder','contract-refused'} <= t; print(len(t), sorted({'l3-aborted','gate-reminder','contract-refused'}))"`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_timeline.py -q`（本卡预期**红在计数锁**上；把红行原文贴进回执，交由 T-14 收口）

## 非空洞对照（必须附在回执里）

- 从 `EVENT_TYPES` 摘掉其中一个名字 ⇒ `test_autopilot_timeline.py` 的集合断言必须转红（证明该断言真的读这张表）。

## 风险与注意

- 与 `T-05`（TS 侧 `EVENT_TYPES`）必须**同批**落地，否则两侧集合相等断言会红（P-021）。本卡只承担 Python 半边并在回执里点明"TS 半边 = T-05"。
- 若既有 Python 计数测试的窗口在 `T-14` 之前被其它会话改动，以 `git diff` 为准并回报。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-03-event-names/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
