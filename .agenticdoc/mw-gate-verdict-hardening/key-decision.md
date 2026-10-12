# KDR: mw-gate-verdict-hardening

## R（需求）
- 技术栈: Python（packages/multi-workers/autopilot）+ TypeScript（agent-team-loop 扩展）
- 边界: 只补三条 E2Feature reflect 根因（L3 流中止指纹 / pending-gate 主动提醒 / 闸门授权范围），不重设计闸门命题体系，不抬 worker watchdog 阈值
- 关键约束: conductor.py / gates.py / status-model.ts 是 `mw-autopilot-slot-capacity` 的活跃未提交写面 ⇒ 本 key EXECUTE 必须等其提交；全部改动 fail-closed；不新增常驻调度组件（GC-1）

## A（架构）
- 三条机制（G1/G2/G3）共享同一写面（`conductor.py` / `gates.py` / `status-model.ts`）与同一批先例（timeline 事件去重 / gate 允许集 / ledger 单写者 / 已应答 gate），故合入一个 key，plan 内串行排布
- G1：谓词 = `worker.log` 尾 64 KiB 含 `stream closed before response.completed` ∧ 无任何 L3 源两节齐备；落点 `_l3_round_verdict` 状态门之前（`conductor.py:1585`）；持久面 = timeline `l3-aborted` + `data`；专用计数 `l3abort:{key}` + 共享 stem 序号（不占共享轮预算）；新配置键 `l3_abort_retry_limit`；`STALL_REASON_CODES` +1
- G2：判定只在 Python（`tick` 的 goal 检测前）、投递只在 TS（poll 循环 → `deliverPmAlert`）；计数 = `auto-decisions.jsonl` 的 `phase:"remind"` 行（timeline 200 条尾窗 20min < 60min，会被否证）；第 n 次在 `n×阈值`；新键 `gate_reminder_after_min` / `gate_reminder_max`；可见面 status `ageMs` + monitor `blockedOnHuman` + doctor 零扰动加机器字段
- G3：`authorizes` 走 gate schema v2 加性扩展（`_JSON_LIST_FIELDS` 闭集 `{retry, contract-change}`，不升 v3）；conductor 物化空行 + 人应答填值；文本身份锚 = 新 sidecar `contract-freeze.json`（内容寻址，缺失 fail-closed）；done 前检查 = 新 mw 纯模块 + `_done_transaction` 挂点 + `mw autopilot contract-guard` CLI；批准记录 = 已应答 gate
- 贯穿约束：P-018 零扰动（历史 gate / 无 freeze key / 无 abort 项目逐字节不变）；P-021 双侧同步（3 事件名 + 3 配置键 + 1 字段 + 1 真值表）
- 已知残余：PM 裸 bash 直跑 `advance_phase.py ... done` 不被 G3 拦截（外部 AgenticTask 仓库，字面全覆盖需上游独立变更）
- 范围追加 G4（2026-10-09，D-005）：`monitor-frozen-after-mw-restart`。RQ-4 证伪"`launcher-beat` 身份耦合"与"重启导致冻结"（重启不触碰 pi；唯一可致静默冻结的代码点 = `monitor.ts:828-833` 裸 catch）。判据 = 帧自证新鲜（绝对采集时刻 + 过期告警）+ 失败降级帧 + ctx 变化/session_shutdown 重臂。AC-015~AC-018。
- 串行约束（G2/G4）：两者都改 `monitor.ts:156-176`（类型区）与 `monitor.ts:386`（`readMonitorState` 的 `return`）⇒ plan 排 G2 → G4，`monitor.ts` 禁并行编辑（D-020）
- 范围追加 G5/G6（2026-10-10，D-020/D-021；IN-3 事故驱动）：G5 = 队列完整性（读侧不得静默丢行 + 行缺失 fail-closed + 单轮配额 + launcher 有界/doctor 形状判据），G6 = 派发隔离与运行身份（PM 侧作用域收窄 / 写面限定本 key + `_scratch` + `run.json` 产物自带终态 + `supersedes` 新 key）。写面新开：`worker-store.ts` / `pm-orchestrator.ts` / `launcher.py` / `ui-bridge.ts` / `autopilot/dispatch.py` / 新模块 `run-store.ts`；设计展开见 design §11（D-025~D-028 / F25–F41 / VC-024–VC-041）
- 新串行链（G5/G6）：`pm-orchestrator.ts`（T-09→T-17→T-19）、`worker-store.ts`（T-15→T-20）、`launcher.py`（T-18→T-20）、`ui-bridge.ts`（T-09→T-22）；`mw_common.py`/`mw.py` 与 T-11 同文件 ⇒ T-11 → T-18/T-19
- AC-024（2026-10-10，D-026）：**读全局 / 写限定**——`list_tasks`（`scope:"all"`/`"key"`）、`mw_status`、`mw doctor`、面板对**任意 key** 保持只读可见（隔离不得靠“看不见”实现）；写面（`dispatch_worker` 的**显式 `key`**、`advance_phase`）对 `claimState == "held-live"` 的他人 key **先拒后动**、返回固定码 `[cross-key-read-only]` + `switch_key` 指引、**零副作用**；可写面 = 自有 claim / 未认领新 key（建 key 流程）/ `_scratch`。同函数 `foreignLiveClaimRefusal` 与 `takeOverKey` 共用活性判据
- AC-021/AC-023 扩展（2026-10-10，D-028/D-029）：AC-021②③ = launcher 并发上限**永不为无界**（`None` ⇒ `launcher_max_workers`，默认 8）+ `_workers.acked` 参与（acked ∧ 行非终态 ⇒ 收敛且不 spawn；ack 不可读 = 无信息）；AC-023 写面 = **全部队列写者**（TS `upsert` + Python `update_status`/`archive_stale_entries`/`autopilot/dispatch.py`）必须槽位保留，且 doctor 三条无状态形状判据（`queue-rows-unparsable`/`queue-burst-shape`/`run-ledger-conflict`）。⇒ 写面新增 `autopilot/dispatch.py`（原设计“不改”，R17 范围变更）
- 新串行链（G5/G6）：`pm-orchestrator.ts`（T-09→T-17→T-19）、`worker-store.ts`（T-15→T-20）、`launcher.py`（T-18→T-20）；`mw_common.py`/`mw.py` 与 T-11 同文件 ⇒ T-11 → T-18/T-19
- EXECUTE 硬门禁（D-014）：隔离（AC-019/020/021）未落地前，本 key **不派发任何 worker**（含只读调研）——因为派发动作本身可能触发全项目队列重建。注：AC-023 的 Python 半边（`mw_common.update_status` 仍整表重写）未完成前同样不得解除（D-025）

## I（实施）← PM 执行中追加

- 2026-10-10（T-15/T-17/T-19/T-22，隔离先行批）：`worker-store.ts` 读侧计数 + 槽位保留；`pm-orchestrator.ts` fail-closed 判据/配额/作用域 + 告警落盘（`phase:"dispatch-alarm"`）；`ui-bridge.ts` 跨 key 写面守卫（`[cross-key-read-only]`）。证据：`evidence/runs/{t-15-t17-t19-report.md,t-22-crosskey-readonly-report.md}`；控制脚本 `evidence/scripts/{t15,t17,t22}-controls.ps1`。
- 2026-10-10（T-18，G5-C）：`launcher.py` 默认有界 + acked 收敛；`mw_common.py` 队列解析/写者槽位保留 + `read_acked` + doctor 三判据；`autopilot/dispatch.py` 改用 `upsert_worker_row`；`autopilot/config.py` + `status-model.ts` 三键（14→17）与语料 re-freeze（55→64）。证据：`evidence/runs/t-18-queue-integrity-report.md`；控制脚本 `evidence/scripts/t18-controls.ps1`（A~F 均红）；只读面实测 `_workers.parallel` 未变（252 行 / 0 非终态 ⇒ 形状判据正确静默）。
- 2026-10-10（T-20，G6-B）：`shared/run-store.ts`（新）+ `worker-mode.ts` 自写 `running`/终态/心跳 + `output.md` marker + `pm-orchestrator.ts` 的 `runVerdict` 接线与两类新告警（`out-of-scope`/`run-ledger-conflict`）+ `ui-bridge.ts` 与 `worker-store.ts` 的 `lost` 传播 + `launcher.py` 只补 `lost` + `mw_common.mark_run_lost`。证据：`evidence/runs/t-20-run-identity-report.md`；控制脚本 `evidence/scripts/t20-controls.ps1`（A~G 均红）。**卡字面偏离 3 处**：同 task_key 一律拒重跑；marker 写 harness 段首行；PM 不写 `pending`。
- 2026-10-10（T-21，用例汇总）：事故行格局夹具 `test/fixtures/in3-queue-9col-burst.txt`（250 行 × 9 列 / 27 owner）+ 生成器 `evidence/scripts/t21-make-in3-fixture.py` + Python 回放 `test_in3_queue_replay.py` + TS 回放段（`worker-store.test.ts`）+ 10 候选配额例 + 映射表 `evidence/runs/verify-g5g6-tests.md`。证据：`evidence/runs/t-21-integrity-report.md`；控制脚本 `evidence/scripts/t21-controls.ps1`（A~E 均红）。四组数字：9 列样本 **250**、旧 codec 丢弃 **250/250**、`unparsable` **0**（注入 10 列⇒**1**）、配额 **10→3**。
