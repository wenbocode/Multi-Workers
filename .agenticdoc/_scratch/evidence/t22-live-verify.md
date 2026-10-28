# T22 实机验收：新决策记录的任务前后快照

- 验收对象：`task_key = t22-live-verify-20261025`（owner key `_scratch`），type research
- 账本（只读）：`.agenticdoc/_autopilot/decision-lifecycle.jsonl` — 47 行 / 32615 B / sha256 `731E89EF0270C9BE824C977CA81EF0FFC2CCA5641D94D7C8BADC822A0BA5F5DD` / LastWriteTimeUtc `2026-10-25T02:13:12Z`
- 本任务派发时刻：`2026-10-25T06:59:40.980Z`（本 worker `trace.log` 的 `[START]` 行）；读数时刻约 `2026-10-25T07:00Z`
- 方法：只读解析全部 47 行 JSON，按 `task_key` 精确等于本任务 key 筛选；未写、未改任何账本行

## 结论

1. **(a) 决策前快照是否存在：否 — 不存在/未记录。** 账本中 `task_key == "t22-live-verify-20261025"` 的行数为 **0**，没有 `record-start` 行，因此 `task_before` 及其 `status / source / observed_at / completed / remaining / blockers` 六个字段全部**未记录**（无原值可给，不做推断、不用任务当前状态补填）。
2. **(b) 实际处理后的快照是否存在：否 — 不存在/未记录。** 同一筛选下没有任何 `lifecycle` 行（consumed / executed / settled 三个都没有），`task_after` **未记录**。
3. **(c) 时间序与归属一致性：无法判定（前置事实缺失）。** 不存在 before/after 对，`after.observed_at >= before.observed_at`、以及 after 行与 record-start 的 `logical_id / key / task_key` 是否一致，均**无从比对**。
4. **总结论：T22 重打包后的实机验收未通过。** 本任务自身的 dp1 派发（`trace.log` 记为 `[DECISION] dp1 state=material`）没有在 lifecycle 账本留下任何一行，前后快照都不存在。不声称整 key 验收通过、也不声称采集代码可用或不可用。

## 证据

### E1 筛选结果（精确匹配）
- 解析 47/47 行，JSON 全部合法；`task_key` 含子串 `t22` 的行 **0**。
- 子串 `live-verify` 在 `.agenticdoc/_autopilot/` 下 6 个 `*.jsonl`（auto-decisions / decision-lifecycle / decisions-wire / decisions / timeline / triage-decisions）中命中数均为 **0**。
- 账本 key 分布：`mw-decision-context` 11 / `mw-monitor-auto-restart` 9 / `mw-dp-consolidation` 27；**不含 key `_scratch`**。distinct task_key 共 11 个，均非本任务。

### E2 账本字段面统计（并非本任务行，作为字段是否真的带值的旁证）
- `record-start` 共 12 行，带 `task_before` 字段的 **7** 行，这 7 行值**均为 JSON `null`**（非对象）。
- `lifecycle` 共 35 行（consumed 9 / executed 17 / settled 9），带 `task_after` 字段的 **20** 行，这 20 行值**均为 JSON `null`**（非对象）；其余 15 行连字段都不存在（更早 schema）。
- `capture_status` 在全部 47 行**均为 `null`**。

### E3 原值摘录（原文，未改动一个字）
- 第 21 行 `record-start`（key=mw-dp-consolidation, task_key=dpc-rq1-runtime-inventory, ts=2026-10-24T14:50:11.469+00:00）：
  `...,"capture_status":null,"logical_id":"45d4d6e4-ecf6-4bcf-bfec-11490075ee5d","record_version":2,"initiator_role":"pm","retry_of":null,"task_before":null}`
- 第 47 行 `record-start`（key=mw-dp-consolidation, task_key=dpc-rq6-autopilot-human-pm-framework, ts=2026-10-25T02:13:12.404+00:00）：
  `...,"logical_id":"231a7018-7701-40de-8dd1-ac227b9b639a","record_version":2,"initiator_role":"pm","retry_of":null,"task_before":null}`
- 第 22 行 `lifecycle=executed`（同一 logical_id 45d4d6e4…, ts=2026-10-24T14:50:12.391+00:00）：
  `...,"action":"record","outcome":null,"reason":null,...,"evidence_sha256":null,"snapshot_sha256":null,"task_after":null}`
- 第 3 行 `lifecycle=executed`（ts=2026-10-23T08:17:41.965+00:00）**没有** `task_after` 键，行尾为 `...,"evidence_path":null,"evidence_sha256":null,"snapshot_sha256":null}`（对比第 22 行多出 `,"task_after":null`）。
- 本任务：无行可摘录 —— 0 行。

### E4 时间线交叉（判定依据）
- 账本最后一行（第 47 行）`ts = 2026-10-25T02:13:12.404+00:00`；文件 `LastWriteTimeUtc = 2026-10-25T02:13:12Z`，两者一致。
- 本任务 `task.md` 写入 `2026-10-25T06:59:31Z`，派发 `[START] 2026-10-25T06:59:40.980Z`，`run.json` `2026-10-25T07:00:10Z`。
- `.agenticdoc/_autopilot/*.jsonl` 中最新的 `LastWriteTimeUtc` 是 `decisions.jsonl = 2026-10-25T02:16:13Z`：**派发时刻（06:59:40Z）之后没有任何一个 autopilot 账本被写过**（差约 4h43m）。这与 (a)(b) 均为"不存在"的结论一致。
- 行序判据未使用到：因为筛不出本任务行，(c) 不存在可比较的行序对。

## 残留与未验证

- **根因未定位**：为何本次 dp1 派发（`[DECISION] dp1 state=material`）没有产生 `record-start` / `lifecycle` 行。本报告只记录可观察事实（派发窗口内 autopilot 账本零写入），不推断机制；`ui-bridge.ts` 与 `decision_lifecycle.py` 仅作只读线索，未运行、未插桩、未跑测试。
- **E2 的 null 值未被解释**：既有 7 条 `task_before` / 20 条 `task_after` 为 `null`，究竟是"写入时值即空"、"客户端未送"还是"下游丢弃"，未验证。其中 7 条 `record-start` 均属更早的 `mw-dp-consolidation` 批次；且 `dpc-rq6` 出现两次 `record-start`（第 40、47 行，logical_id 分别为 3267234f… 与 231a7018…），本任务未去核实其重复派发语义。
- **覆盖面**：只实机验证了 1 次派发（本任务自身），其他 key 的新派发未实机复验；未覆盖其他账本（decisions-wire / decisions / triage-decisions）的逐行内容，只做了子串命中计数 = 0。
- **未验证**：`captureDecisionTaskState` 的返回值是否真的送达 python 写入口（需要插桩或运行期日志，本任务禁跑）；`record-start` 的 `_start_event_id` 去重/落盘链路是否在本次调用中被执行。
- 未运行：测试、真实模型请求、mw serve、monitor、sign、build、install、commit、ask_decision；未修改任何账本或源码。

## 上下文来源

- 本任务卡：`.agenticdoc/_scratch/tasks/t22-live-verify.md:1`（派发卡 `card_sha256 385503bdc3e9…a27e6`）
- 账本（只读）：`.agenticdoc/_autopilot/decision-lifecycle.jsonl`
- 源码线索（只读）：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3350`（派发前 `captureDecisionTaskState`）、`:3433`（派发后 `taskAfter`）、`:485` 起 `writeDp1DispatchFeedback`；`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-task-state.ts:1`（快照 shape / `isTaskStateSnapshot`）；`packages/multi-workers/decision_lifecycle.py:485` 起（record-start / lifecycle 写入口）；`packages/multi-workers/decision_wire.py:270,684`（sink 路径 = `.agenticdoc/_autopilot/decision-lifecycle.jsonl`）
- 运行证据：`.agenticdoc/_scratch/workers/t22-live-verify-20261025/trace.log`（`[START] 2026-10-25T06:59:40.980Z task=t22-live-verify-20261025 type=research`）
- 目标锚点：`.agenticdoc/goal.md:5`
