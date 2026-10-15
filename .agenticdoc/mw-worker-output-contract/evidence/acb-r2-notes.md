# ACB-R2 探针证据

- `formatMachineCheckpoint` 定义于 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:688`，配套 `MachineCheckpointOpts`（同文件 671-679），产出单行、无尾换行的机器收敛行。
- 机器行字段：`CKPT <n>m`（elapsedMs 取整分钟）+ `ts=`（ISO-8601 时间戳）+ `reads=` + `writes=` + `phases=`（分阶段任务为 `<done>/<total>`，否则 `-`）+ `repeat_top=` + `risk=`（low|mid|high）。
- 调用点在 `worker/worker-mode.ts:3336-3348`：仅当角色无写工具时经 `appendProgressLine` 追加到该 worker 的 `progress.md`；`[machine]` 标记用于与 agent 自评 CKPT 行区分（AC-002/AC-003，D-104/D-105）。
- 机器行是 progress.md 记录，`shared/heartbeat.ts:95` 的 `CHECKPOINT_LINE_RE` 仅匹配 `[CHECKPOINT]` 前缀，不解析该行（本次只读核验，2026-09-10）。
