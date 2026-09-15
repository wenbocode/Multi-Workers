# Research: 心跳挂点、活性判定与 gate 收敛设计（design）

## 决策问题

D-003/D-004/D-006（AC-003~005、AC-010/011）：心跳写入的挂点与事件循环可行性；活性判定的载体；docs gate 评估顺序与播报作用域的接线点。

## 调研方法与出处

- `worker/worker-mode.ts:96-131`：worker 进程内已有 `setTimeout` 看门狗（30min，`unref()`）依赖"事件循环存活则定时器可触发"；`tool_execution_start` 钩子写 `appendTrace`
- `worker/output-writer.ts:49-54`：`appendTrace` 行格式 `[FLOW] <ISO-ts> <line>`，`fs.appendFileSync`，单写者（worker 进程）无锁追加；`appendGoalCheck` 独立行类型先例
- `worker/worker-mode.ts:27-31`（parseTaskMd）：`meta.agenticdocRoot` 实为 `{owner}/workers` 目录（命名误导但与 outputDir 约定自洽）——新写入函数沿用同一约定
- `pm/pm-orchestrator.ts:311-360`：dispatchNewTasks 的 gate 评估在 `dispatched.has()` 过滤**之前**（每 owner 一次）；`:463-476` pmActivate 接线 `onDocGate` 无条件 displaySummary；`:405-425` worker 终态摘要已按 `watch.key` 过滤（`ownerKeyOf(entry) !== watch.key` 即跳过）
- `packages/multi-workers/mw_common.py`（mw-dispatch-reliability 交付）：`doctor_report` 已读队列（queue 节）、7+ 诊断节、`--json` 输出；`mw.py cmd_doctor` 薄壳
- pi 事件模型：扩展 JS 与 agent 流式生成共存于同一 Node 事件循环；`await` 流式 SDK 不阻塞循环，定时器在 chunk 间隙触发（看门狗同一假设）

## 发现

1. 心跳可行挂点 = worker-mode 内 `setInterval`（30s，`unref()`），与既有看门狗同一存活模型；网络挂起时定时器仍触发（事件循环未阻塞），心跳**不会**误报 stale
2. 心跳的真正价值是外部可观测：若事件循环被同步代码阻塞 >30min，**进程内看门狗同样无法触发**（GC-4 场景的盲区）——心跳把内部活性落到文件，doctor 从外部判定
3. trace.log 为 worker 单进程独占追加，无需文件锁（与现状一致，GC-2）；新行类型 `[HEARTBEAT]` 独立于 `[FLOW]`/`[GOAL_CHECK]`（AC-005 additive）
4. gate 收敛 = 把"未入队任务过滤"提到 gate 评估之前；既有测试（undoc-key 用例）语义不变（有未入队任务才评估）
5. 播报作用域过滤的最佳接线点 = pmActivate 的 `onDocGate` 回调（watch 闭包可及），dispatchNewTasks 本体保持无状态（gate 阻塞语义全局不变，仅告警播报按 watch 过滤）
6. 活性判定载体选 mw doctor 新节：复用其队列读取与 JSON 出口，CLI 与 `/mw doctor` 双入口同源（mw-dispatch-reliability D-005 纪律）

## 结论 → 决策映射

- 发现 1/2/3 → D-003：`appendHeartbeat`（行格式 `[HEARTBEAT] <ISO-ts> task=<key> phase=<i>/<n|->`）+ worker-mode 30s `setInterval`（unref，exit 路径清理）
- 发现 6 → D-004：`mw_common.doctor_report` 增 `worker_liveness` 节（running 行 → 最后 [HEARTBEAT] 距今 vs 阈值，默认 90s，`--stale-after` 可配；verdict ∈ alive/stale/no-heartbeat；信息性不改退出码——GC-4 看门狗保留 kill 语义）
- 发现 4/5 → D-006：dispatchNewTasks 重排（先过滤后 gate）+ onDocGate 接线处 watch 作用域过滤

## 追加（2026-09-07 设计审核轮：心跳消费面，D-008）

- 新增事实出处：`pm-orchestrator.ts:34`（POLL_INTERVAL_MS = 4000，每 tick 重绘 watch widget）、`:373-428`（startWorkerPollLoop 内 applyWatchWidget(renderWatchLines(...))）、`ui-bridge.ts:187-240`（renderWatchLines 已列 running 任务行、终态行带 summary 细节）
- 新增发现：widget 是唯一可原位更新且已有 4s 刷新周期的用户可见面；worker-summary 消息（sendMessage）append-only 不能活更新；终态摘要处理处已可拿到 taskDir（可读 trace 统计）
- 结论 → D-008：活 monitor = renderWatchLines running 行追加 `ph i/n hb <age>`（>90s 标 STALE，无心跳 no-hb 占位）；summary 落地为终态统计 `(7m32s, ph 3/3)`；AC-012/013 追加入 spec（编号顺延）
