# Research: 底部 widget 终态行生命周期与摘要质量取证（spec）

> 日期：2026-09-10
> 来源：用户在 OverCode 项目（key certify-parsed-reuse）的现场反馈 + 本仓库源码取证（2026-09-09 timeout forensics 的后续现象）。

## 决策问题

- §1 范围：终态 worker 行是否需要「已处理（ack）」生命周期与折叠区（用户 2026-09-10 指令：不用时间兜底，跑动中/待处理常驻，处理完或已完成超 5 个折叠 more...）
- §1 范围：终态行摘要的信息密度要求（用户：当前摘要不是状态及卡点，混入文件路径等无效信息）
- §4 风险：ack 若移除队列行会导致重复派发（见发现 5）

## 调研方法与出处

- 读 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（renderWatchLines / WATCH_MAX_TASK_LINES / readOutputSummary）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（dispatchNewTasks / PM_CONTINUE_HINT / startWorkerPollLoop）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（buildSummary / finishSuccess）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（writeOutput 分节规则）
- 读 `packages/multi-workers/launcher.py`（_poll_once reap 路径）与 `packages/multi-workers/mw_common.py`（parse_workers_file 列数容忍）
- 读 `tmp/atl-esm.js:5095`（OverCode 项目安装的旧 bundle 反编译留底）
- 现场样本：`.agenticdoc/goal-autopilot/workers/t03-roadmap/output.md`、`ga-spec-design-review-2/output.md`

## 发现

1. **终态行永不过期**：`renderWatchLines`（ui-bridge.ts:289-330）按 running(0)→pending(1)→终态(2) 排序，`WATCH_MAX_TASK_LINES=6` 截断（ui-bridge.ts:181,294,330）。终态（done/failed/needs-clarification）无任何「已吸收/已处理」概念，也无 TTL；只能被更新的任务挤出。OverCode 现场：4 个超时 failed + 2 个 done 永久占满 6 行（用户反馈原文）。
2. **终态行 detail 是冻结的 Summary 首行**：ui-bridge.ts:322 `detail = readOutputSummary(taskDir) ?? readSpawnFailure(taskDir)`，readOutputSummary（ui-bridge.ts:204）取 output.md `## Summary` 节首行。而 Summary 内容 = worker 最后一条 assistant 消息原文（worker-mode.ts:507 buildSummary），首行常为：markdown 标题（`## Task 002 执行完毕…`）、纯前导句（`任务完成。最终汇报：`）、或文件路径列表。超时行为旧文案 `Worker timed out waiting for agent_settled.`（旧 bundle，tmp/atl-esm.js:5095；现行文案为 `Worker timed out (idle|wall).`）。用户判定：不是状态及卡点，信息密度不足。
3. **机器原因已存在但未被展示**：output-writer.ts writeOutput 对 exitCode=1 写 `## Exit Reason`（worker-mode timeoutExit 写入 kind+detail+checkpoint 证据）；对 exitCode=2 只写 `## Questions`（无 Exit Reason 节）；对 exitCode=0 写 `Agent settled after N tool call(s).`（无信息量）。即 failed 行的卡点信息（超时类型/无活动时长/checkpoint 风险）已在 output.md 里，widget 没有取用。
4. **无 ack 通道**：全仓 rg 无 ack/acked/acknowledge 概念（TS 扩展与 Python 侧均无）。PM 收到终态 readback（deliverWorkerResult）后没有任何手段标记「已处理」。
5. **ack 不能删除队列行**：pm-orchestrator.ts:333 `dispatchNewTasks` 的 dispatched 集合只来自 `_workers.parallel` 现存行。若 ack = 移除行，则 task.md 仍在磁盘上的已处理任务会在下一次 agent_settled 扫描时被当作未派发任务重新入队（pending）→ launcher 重复 spawn。故 ack 必须是旁路记录（sidecar），队列行原样保留。
6. **队列行格式不能加列**：TS `parseWorkerLine`（worker-store.ts）与 Python `parse_workers_file`（mw_common.py:342-365）都只容忍 7/8 列，9 列行会被双侧静默丢弃。ack 状态写入第 9 列不可行，sidecar 文件（如 `.agenticdoc/_workers.acked`）是安全路径。
7. **孤儿 running 行（潜在故障模式，未列入用户本次需求）**：launcher.py:281 只有 spawn 该 worker 的 launcher 实例在 reap 时更新行状态；mw serve 停止/被杀时在飞 worker 的行无人更新。2026-09-10 曾误判本仓库 t03-t08 为僵尸行，实为 UTC 时间戳误读本地时间（t03 实际 29 分钟正常完成）。该模式真实存在但本次未发生。

## 结论 → 决策映射

- 发现 1+4 → 终态行需要显式 ack 生命周期（命令 + agent 工具双通道），处理完/已完成行进折叠区（上限 5 行 + more...），不用 TTL（用户指令）。
- 发现 2+3 → 终态 detail 按状态取源：failed → Exit Reason 首行；needs-clarification → Questions 首行；done → 单行结论（worker 侧归一化 + 旧文件容错回退）。
- 发现 5+6 → ack 持久化为 sidecar（`.agenticdoc/_workers.acked`，workers lock 保护），不改 `_workers.parallel` 行与列格式。
- 发现 7 → 孤儿 running reconcile 列入 spec §4 待确认项，由用户决定是否纳入本 key。
