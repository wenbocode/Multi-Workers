# spec-pm-perception-path — worker 终态到 PM 的感知链路 / 告警全表 / 重派回路 / 插桩点

- 任务 key：mw-model-error-perception / trq3-pm-perception（type: research）
- 日期：2026-10-15
- 证据基线：本仓工作区代码（未运行时行为，静态核验；行号以当前工作区为准）
- 唯一证据文件：本文件

---

## 1. 感知链路图（worker 终态 → PM）

### 1.1 实际链路（静态核验）

```
worker pi 进程（PI_WORKER_TASK，headless `pi -p`，launcher.py:1391-1407 _build_command）
  │  写自己任务目录的产物（worker 是唯一写者，run-store.ts:1-40 契约）：
  │    run.json         终态 status ∈ {done, failed, needs-clarification}（worker-mode.ts:2655 markOutcome → run-store.ts writeRunState）
  │                     exit 0=done / 2=needs-clarification / 其他=failed
  │    output.md        ## Exit Reason 等 section（output-writer.ts:519-530）
  │    trace.log        [START]/[HEARTBEAT]/[CHECKPOINT]/[END] exit=N（mw_common.py:2520-2523 END_LINE_RE；worker-mode.ts:3156 recordEnd）
  │    worker.log       launcher 捕获的 stdout+stderr（launcher.py:1994 open(_worker_log_path) → 2011-2016 句柄存到 reap）
  │                       pi -p 的报错原文（如 stream closed before response.completed）落在这里
  │  崩溃兜底：process.on("exit") 写最小 failed output + run.json failed（worker-mode.ts:2739-2768）
  ▼
launcher.py（常驻轮询，_poll_once :1712-1720）
  │  spawn：_spawn :1973-2024 → worker.log 打开 :1994 → _update_status(key,"running") :2017
  │  spawn 失败：_record_spawn_failure 写 "[launcher] spawn failed (<iso>): <msg>" 进 worker.log :59-73 + 队列行 failed :2021-2023
  │  reap：进程退出 → _reap_status :418-454（product-first：run.json 终态 > 退出码；_exit_to_status :409-415 0=done/2=nc/其他=failed）
  │        → _update_status 写 _workers.parallel 队列行（mw_common.py:2175-2214，.mw/workers.lock 行级改写）
  │  孤儿收敛：_reconcile_orphans :1458-1533（run.json 终态收敛行 / mark_run_lost 写 lost，mw_common.py:1925+）
  │  （tree_watch.TreeWatch.tick 只产 [TREE-WATCH] 树坍缩/断链告警 → .mw/launcher.log，与 worker 终态无关，见 1.2）
  ▼
_workers.parallel 队列行（status 列是 PM 的"事实源"）
  │
  ├─▶ PM 窗口 widget（ui-bridge.ts renderWatchLines :710-890）
  │     轮询：startWorkerPollLoop 每 4s（pm-orchestrator.ts:85 POLL_INTERVAL_MS=4000 → :1502 readAll → :1506 renderWatchLines）
  │     只渲染 watched key 的行（ownerKeyOf 过滤 :731）+ 本窗口跨 key 派发的聚合尾行
  │     状态字形 STATUS_GLYPH :452-459：pending "." running ">" done "+" failed "x" nc "?" lost "!"
  │     failed/nc/lost 行进"未处理区"，直到 /mw ack（isUnhandledStatus :638-640；ackTasks :646；history=done ∪ acked :813）
  │     终态行 detail（readTerminalDetail :598-630）：
  │       failed   = [launcher] spawn failed 行（≤64KB 才读，:533-553）?? `## Exit Reason` 首行 ?? 空
  │       nc       = `## Questions` 首行 ?? worker.log 尾行（≤256KB，:556-571）?? "no output.md"
  │       lost     = Exit Reason 首行 ?? worker.log 尾行 ?? 固定提示
  │       done     = 最后一个非占位 `## TL;DR`/`## Summary` 首行
  │     行宽截断 WATCH_LINE_MAX=110（:450）；running 行带 heartbeat/checkpoint 风险徽标（:780-805）
  │
  ├─▶ PM 会话内终态回读（pm-orchestrator.ts 轮询循环 :1579-1631）
  │     基线快照 :1453-1459（开窗时已终态的行永不重放）；每行至多一次（notified :1609）
  │     仅 ownerKeyOf==watch.key 的行播报（:1612），他 key 静默消费（:1603-1605 注释 C1/C3）
  │     有 output.md → deliverWorkerResult(整份 body ≤20KB + PM_CONTINUE_HINT :1384-1388)
  │     无 output.md → readSpawnFailure 优先（spawn 失败原文）→ 否则"无 output.md 摘要（worker 可能崩溃/超时）。日志：<path>"（:1615-1628）
  │     通道：deliverPmAlert = sendMessage + triggerTurn（ui-bridge.ts:188-205）——会唤醒空闲 PM 起一个 LLM turn
  │     PM_CONTINUE_HINT 给出 failed 的处置策略文本（读 worker.log/trace 排查→重试或修复；wall 超时双倍预算重派一次）
  │
  ├─▶ autopilot conductor（Python 独立 tick，不受 widget/回读影响）
  │     execute_loop（conductor.py:1953-2118）：失败行消耗 loop 预算 → 重试或 mark_stalled(:6367)
  │     _verify_loop（:2626-2880）：L3 复评/修复/l3-abort 重掷；预算耗尽 mark_stalled(reason_code=…)
  │     stalled → stalled gate（人工/auto 应答，approve=+1 resume credit，conductor.py:4124-4140）
  │
  └─▶ autopilot monitor 面板（monitor.ts:1269-1342）：keys running/stalled 计数、stall reason_code、resume 提示
        mw doctor（mw.py）：launcher_log 错误行计数、queue 统计、worker 活性（stale/无心跳点名）
```

### 1.2 卡片假设核对：tree_watch.py 不在 worker 终态链路上

`tree_watch.py` 是共享树健康采样器（git 坍缩 AC-010 / 断 junction AC-011），输出 `[TREE-WATCH] collapse/broken-link/...` 行到 launcher 的 stderr 通道（`.mw/launcher.log`，tree_watch.py:412-424 emit_alarms → launcher.py:1725-1729）。它与 worker 终态/run.json 无任何读写关系。worker 终态的"watch 行生成"实际上是 **launcher reap 写队列行 + PM widget 每 4s 轮询渲染**（1.1 前两级）。卡片把两者并列为链路一环，特此更正：tree-watch 是旁路健康信号，PM 窗口今天不读它（只有 `mw doctor` 的 launcher_log 错误计数间接可见）。

### 1.3 "模型错误"今天在链路上的可见/不可见点

| 模型错误形态 | worker 侧落地 | PM 可见物 | 缺口 |
|---|---|---|---|
| 流中断但 pi 内部重试成功 | 无痕（pi session retry，settings 默认 maxRetries=3，settings-manager.ts:821） | 无 | 重试成本不可见 |
| 重试耗尽后 settle（stopReason="error"） | agent_settled → finishSuccess（worker-mode.ts:3535-3644）：lastAssistantText 为空 → summary="Task completed."；writeless 角色 → exit 2 + `## Questions: no-product: <channel>` + recordDispatchAlarm(no-product)；write 角色 → 按 gaps 判 0/2 | 回读头 `[task] needs-clarification` + Questions 文本；**错误原文只在 worker.log** | Exit Reason 不含 errorMessage；write 角色可能按机械 gaps 判 done（错误被吞） |
| 挂死型连接失败（无任何事件） | idle watchdog 10min（DEFAULT_IDLE_MS，worker-mode.ts:241, :3448-3461）→ exit 1 `idle timeout` | failed 行 + Exit Reason=idle timeout… | 无法与"真挂死"区分（正是 idle 设计语义） |
| 进程硬崩 / provider 403 后 harness 写占位 output | crash 兜底 failed（:2739-2768）；或 P-007 场景：worker.log `done exit=0` + `stream closed`，output.md 只有模板 | failed 行 + Exit Reason（模板首行，误导） | 详见 P-007/P-028 pitfall |
| spawn 失败（凭证缺失等） | launcher 写 `[launcher] spawn failed ...` :59-73 | failed 行 detail 直接显示该行（:533-553） | 唯一有专用通道的失败类 |

结论：**今天没有任何一处把"模型错误"作为机器信号**。错误原文只存在于 worker.log 自由文本；唯一的模型错误感知机制在 conductor L3 复评：`_l3_stream_aborted` 指纹（conductor.py:2264-2300，substring `stream closed before response.completed` + 无合格 L3 source → verdict `aborted` → 限额重掷 → `l3-aborted` stall）。它是 review 专用、marker 硬编码、不覆盖 exec/L2/repair。

---

## 2. recordDispatchAlarm kind 全表

通道：`recordDispatchAlarm`（pm-orchestrator.ts:607-628）——向 `.agenticdoc/_autopilot/auto-decisions.jsonl` 追加一行 `{seq, phase:"dispatch-alarm", kind, count, detail}`（best-effort，永不抛）。行 shape 与 Python 单写者对齐；conductor 的决策消费方只读 `phase=="decide"`，所以 dispatch-alarm 行对机器决策**不可见**（:596-605 注释）。

kind 集合（`DispatchAlarmKind`，pm-orchestrator.ts:478-523）：

| kind | 触发点 | 语义 | 去重 | 消费方 |
|---|---|---|---|---|
| `queue-rows-unparsable` | pm-orchestrator.ts:1109（扫描） | 队列有不可解析行 | 每.kind 每会话一次（refusal 类） | live: formatDispatchAlarm→deliverPmAlert（:1870-1871）；ledger: 仅审计 |
| `queue-unreadable` | :1312 | 队列文件读不了 | 同上 | 同上 |
| `dispatch-quota` | :1286, :1341 | 单扫描配额（默认 3，:696）触发后停止 | 同上 | 同上 |
| `out-of-scope`（notice） | :1141 | 有活但无 owner 记录的未注册 key | 每.key 每会话（unregisteredWarned :1833） | 同上 |
| `orphaned-keys`（notice） | :1148 | 已注册 key 有活、无 claim 无 live run → claim-free 修复 | 每.key 每会话（orphanedWarned :1828） | 同上 |
| `orphan-repair-skipped`（notice） | :1159 | owner 证据过期，跳过修复 | 每.kind 每会话 | 同上 |
| `run-ledger-conflict` | :1174 | 队列无行但 run.json 已终态 | 每.kind 每会话 | 同上 |
| `no-product` | **worker-mode.ts:3626-3631（worker 进程自写）** | 只读 run 无交付 → needs-clarification | 无（worker 侧每 run 一行） | **无任何程序读方**（见下） |
| `write-scope-risk` | :655-659（recordWriteScopeResidualRisks），轮询循环 :1603 调用 | 写守卫残余风险（blocked=false + risk=deny-basename 的 [WRITE_SCOPE] 行） | notified 限定每 task 每会话一次（:1594-1597） | live alert + ledger |
| `write-face-refusal` | :683-690（reportWriteFaceRefusal，扫描 onRefusal :1840） | PM 侧 write-face 拒绝（每任务一行，从不 dedup） | 无 | live alert + ledger；**mw doctor 读它**（mw.py:2529-2548 `_parse_write_face_ledger_row`，只认 kind==write-face-refusal） |

关键事实：

1. **live 通道与 ledger 是两条路**。PM 窗口的实时告警来自 `onAlarm` 回调（:1862-1872）里的 `deliverPmAlert`；worker 进程自写的行（no-product）**只进 ledger，没有任何 live 通知**——PM 对 no-product 的感知实际来自终态回读（needs-clarification + Questions 文本），不来自告警行。
2. **没有任何阈值/熔断/计数读方**。`dispatch-alarm` 行写后无人聚合（TS 侧零读方；doctor 只过滤 write-face-refusal 一种）。conductor 决策面看不见它。
3. 告警措辞分两类：`NOTICE_DISPATCH_ALARM_KINDS`（:534-538）出 `[mw] dispatch 提示：…`，其余出 `[mw] dispatch 已拒绝：…`（formatDispatchAlarm :591-600）。`describeDispatchAlarm`（:550-589）的 switch **没有 default**——新增 kind 忘加 case 会渲染出 "undefined" 文案（TS 不查穷尽）。
4. 新增 kind（如 `model-error`）需要动的全部位置：
   - pm-orchestrator.ts:478-523 union 加成员 + 注释（判 notice 或 refusal）；
   - :550-589 `describeDispatchAlarm` 加 case（必须，否则 undefined）；
   - :534-538 若按提示措辞则加入 NOTICE 集合；
   - 发射点：worker 侧（仿 no-product :3626-3631，注意用 `meta.trueAgenticdocRoot` 而非 `<key>/workers` 根）或 PM 轮询循环（仿 write-scope-risk :1603，能拿到 live deliverPmAlert 通道——推荐，见 §4）；
   - 测试：worker-dispatch-guard.test.ts:342（行 shape）、mwds-t04-deliverable.test.ts:422（no-product 行）、write-face-pm-gate.test.ts:605；
   - 若 doctor 要读：mw.py:2529-2548 加一个 `_parse_*` 分支（可选）；
   - 若要配阈值旋钮：config.py DEFAULT_CONFIG + TS parity（readDispatchMaxPerScan :706 先例）；
   - 重建 `packages/multi-workers/dist/extensions/agent-team-loop.js`（生成物，含旧拷贝 :20946/:28626 等）。

---

## 3. failed 终态的 PM 可见物 + 自动重派回路盘点

### 3.1 status=failed + Exit Reason X 时 PM 窗口的确切可见物

1. **widget 未处理区**（4s 刷新）：header 计数 `N failed / M unhandled`（:766-775）；行 `  x <taskKey>[ model] — <detail>`，detail = spawn-failure 行 ?? Exit Reason 首行 ?? 空（:598-606）。不 ack 永远挂着（:786, :813）；ack 工具 `ack_worker_result` / `/mw ack all`（:2506-2508）。
2. **终态回读**（本会话至多一次，仅 watched key）：`[<taskKey>] failed (<时长>)` + 整份 output.md（≤20KB）+ PM_CONTINUE_HINT；无 output.md 时用 spawn-failure 原文或"无 output.md 摘要…日志：<path>"（:1612-1628）。deliverWorkerResult 会 triggerTurn 唤醒 PM。
3. **不需要 ack 才能继续**：回读即达；ack 只是把 widget 行从未处理区挪进 history。
4. **autopilot 不因 failed 行暂停**：widget/回读是纯显示+PM 会话通道；conductor 只看队列行与自己的 loop 预算。failed 的 autopilot 后果是**消耗该 loop 一轮预算**，预算尽 → mark_stalled → key 冻结（orchestrate 跳过 stalled，conductor.py:71 `_DISPATCH_SKIP_STATUSES`）+ 创建 stalled gate 等人工/auto 应答。monitor 面板显示 `key phase/stalled | advance Nx <reason_code>`（monitor.ts:1309-1335）。

### 3.2 谁会在 failed 后再次派发同一 key 的新 worker

| # | 重派方 | 机制 | 频率限制 | 模型错误感知 |
|---|---|---|---|---|
| 1 | conductor execute_loop（"L1" exec，conductor.py:1953-2118） | 失败耗预算 → 新 stem `ap-{key}-{stem}-a{used+1}`（新 task dir，绕开 run-terminal 门，dispatch.py:1345-1371 只挡同 dir 终态） | `round_budget`(默认 2) + `_resume_credits`（每个 approved stalled gate +1，全部 loop 共享） | 无（失败一律按预算重试） |
| 2 | conductor `_advance_key`（"L2" verifier，:1619-1741） | 同上，`l2-{phase}-to-{nxt}-a{N}` | round_budget + credits；耗尽 stalled(l2-budget-rejected 等) | 无 |
| 3 | conductor `_verify_loop`（"L3" review，:2626-2880） | no-verdict → re-review；aborted（stream-closed 指纹）→ 专用重掷 | l3_limit = round_budget + credits；**l3_abort_retry_limit 默认 1（0..10，config.py:99/:133）**，独立 loop `l3abort:{key}`；重掷耗尽 → verdict=below + stalled(l3-aborted) | **唯一有**：`_l3_stream_aborted`（:2291-2300）worker.log 尾 64KB substring 匹配 |
| 4 | conductor repair loop（:2852-2881） | L3 below → repair worker | round_budget + credits；耗尽 stalled(l3-repair-exhausted) | 无 |
| 5 | PM 手动/LLM 决策 | PM_CONTINUE_HINT 文本策略（:1384-1388）：failed→排查后重试或修复；wall 超时→双倍 timeout 重派一次再失败转直执 | 无硬限制——`/mw dispatch`（ui-bridge.ts:2925-2999）直接 upsert 队列行；**直派路径不做 run.json 终态检查**（evaluateRunIdentity 只接在扫描 runVerdict :1846-1859 上）；写面 gate 只挡并发重叠 | 无（LLM 读 worker.log 自由文本猜） |
| 6 | PM 扫描 orphan 修复（dispatchNewTasks，:826+） | 只修"有活无队列行"的孤儿；failed 行不是孤儿，不会走这里 | dispatch_max_per_scan=3 | 无 |
| 7 | launcher | **从不自动重派**（只 spawn pending 行；reap 后行即终态） | — | — |
| 8 | auto-gate（shadow/live，opt-in） | stalled gate 的自动应答 → 间接给 #1-#4 续一轮 | AUTO_NIGHT_CAP=6/晚、AUTO_KEY_CAP=2/key/晚、burst 上限、auto-brake.md 熔断（conductor.py:6592-6598）；blocker_class 必须 paperwork（:6604-6609） | 无（判据是 paperwork 分类，不是失败原因） |

"连续 12 次失败重派"事故的机理：#1-#4 每轮失败耗 1 预算 → stalled gate →（人工/auto）approve → +1 credit → 再失败 → 再 gate……**approve 次数就是重派次数上限的唯一来源**；auto 应答有每晚配额，人工应答无配额。PM 侧对这条链的全部可见物是：widget 的 failed 行流水、monitor 的 `advance Nx` 与 stalled gate 行、auto-decisions/timeline 事件——没有任何一处说"这 N 次失败是同一种模型错误"。P-028（伪 failed 块）还证明 PM 若按 failed 自动重派会丢整轮工作——重派判据今天只能靠人读 worker.log。

---

## 4. 插桩点建议（结论→决策映射）

### 4.1 worker 侧：新增机器信号（零 schema 变更）

- **W1 `[MODEL_ERROR]` trace 行**：worker-mode.ts:3139 `pi.on("agent_end")` 已拿到 `event.messages`；AssistantMessage 带 `stopReason`（"error"/"aborted"）与 `errorMessage`（packages/ai/src/types.ts:388, :420-422；ai/src/utils/retry.ts:230 `isRetryableAssistantError` 可直接复用做分类）。在 finishSuccess/finish 路径检测最后一次 assistant message：`stopReason==="error"` → `appendError` 同款追加 `[MODEL_ERROR] <ts> retryable=<bool> <errorMessage 首行 160 截断>`（output-writer.ts:705-711 先例）+ `writeWorkerLogLine("[worker] model-error ...")`。零新文件、零协议变更，grep 可见。
- **W2 Exit Reason 约定**：同一检测把 Exit Reason 拼上机器 token `model-error: <首行>`（writeOutputGuarded 的 exitReason 参数）。这样 D-004 现有阶梯（readTerminalDetail :599-605）让 widget failed 行**直接显示错误类**，widget 零改动；回读正文与 run.json status 不变（failed/nc 语义不动，run.json 冻结契约不碰——mw_common.read_run_status 只读 status，加字段无读方）。
- **W3**（可选）：把 idle-watchdog 判据里"最后事件是 model-error 而非静默"写进 `[IDLE_KILL]` detail（:2435+），区分"连接挂死"与"agent 挂死"。

### 4.2 PM 侧：「同 key 连续 N 次 model-error 终结即熔断升级人工」最小侵入挂点

**挂点 = 轮询循环的终态分支，紧跟 `recordWriteScopeResidualRisks`（pm-orchestrator.ts:1603）。** 理由：这里是唯一同时具备 (a) 每个终态迁移恰好经过一次（notified 去重）、(b) owner 归属（ownerKeyOf）、(c) 现成 ledger 通道与 live 唤醒通道（recordDispatchAlarm + deliverPmAlert）、(d) 会话级去重基建（dispatchAlarmsSeen）的位置。侵入面 ≈ write-scope-risk 的接线量（一个函数 + 一行调用）。

形态：
- 新 kind `model-error`（§2 清单的 9 处）；
- `countModelErrors(taskDir)`：读 trace.log 尾 64KB 数 `[MODEL_ERROR]` 行（mw_common.parse_end_exit 的 tail-read 先例，Python 侧 `_L3_ABORT_TAIL_BYTES` 同款），或匹配 Exit Reason 的 `model-error` token（W2 之后两条互证）；
- 轮询循环持有 `modelErrorStreak: Map<ownerKey, {count, lastTaskKey}>`：终态行带 model-error 证据 → count++；done → 清零；count≥N（建议常量起步，如 3，后续可进 config.json 走 readDispatchMaxPerScan 同款 parity 路径）→ `recordDispatchAlarm({kind:"model-error", count, detail:"owner=<key> tasks=..."})` + deliverPmAlert 熔断文案（停止对该 key 派发、升级人工——由 PM agent 执行，天然覆盖手动派发与 conductor 派发的 worker，因为所有 worker 终态都过队列行）；
- 去重沿用 once-per-(owner,streak-epoch) 语义，避免每 4s 重响。

**conductor 侧（挡住 autopilot 烧预算）**：把 `_l3_stream_aborted`（conductor.py:2291，review 专用、marker 硬编码）泛化为 `_worker_stream_aborted(task_dir)` 通用指纹，在 execute_loop 重试分支（:2060-2086）与 `_verify_loop` no-verdict 分支（:2736-2756）派发重试前检查该 loop 家族最近一行的 worker.log：命中 → 不再发新 attempt，直接 `mark_stalled(reason_code="model-error-loop")`，走现成 stalled-gate 升级人工（approve=+1 credit 的既有语义保留，人看到 reason_code 就知道该换模型/查网关而不是放行）。L3-aborted 路径（:2685-2729）已经演示了"指纹→限额重掷→stall 带因"的完整样板，这里是照抄结构，不是新机制。注意 STALL_REASON_CODES 是冻结 14 项集合（:6581-6596），加 code 要同步 auto-gate 映射表与 TS parity（monitor/console 的 reason 显示是透传，无需改）。

### 4.3 顺带修正的两个缺口（低成本，同挂点）

- `describeDispatchAlarm` 加 case 时补 default 或 exhaustiveness 断言（现结构漏 case 出 "undefined"）。
- no-product 行今天无任何读方（§2 事实 1）；若 model-error 走 worker 自写路线会复刻同一盲区——这也是推荐 PM 轮询侧发射（4.2）而非 worker 侧发射的原因。

---

## 5. 残留与未验证

1. 未运行时验证：worker.log 中 pi -p 对 terminal model error 的实际打印格式（推断为错误文本/stderr，未实测）；`[MODEL_ERROR]` 的分类阈值需实测样本校准（P-007 实测：review 型 12 次里 8 次无结论，4 次 stream closed）。
2. "连续 12 次失败重派"事故未在本仓档案中找到原始记录（_pitfalls.md 无对应条目；最接近的是 P-028 伪 failed 块与 :340 的 envelope 双 failed）；机理系由 resume-credit + stalled-gate 语义反推，事故窗口的具体 loop 归属（exec 还是 L3）未定。
3. `pi.on("agent_end")` 的 messages 是否总含 stopReason="error" 的收尾消息：agent-session.ts:683-694 `_willRetryAfterAgentEnd` 同样读最后一条 assistant message 判重试，链路成立；但 abort/崩溃路径不产生该事件（由 crash 兜底覆盖）——`[MODEL_ERROR]` 覆盖不了硬崩，需在报告中如实标注。
4. dist bundle（packages/multi-workers/dist/extensions/agent-team-loop.js）是否随发版重建、worker 是否加载 dist 版：本次未核验构建脚本（build-extension.sh），新增 kind 落地时须确认双份同步。
5. auto-gate 是否曾被配置为 live 并实际自动应答过 stalled gate（影响 12 连派归因）：本仓 `.agenticdoc/_autopilot/` 当前状态未检查（研究任务无写面、只读代码）。

## 6. 上下文来源

- 代码：packages/multi-workers/launcher.py、tree_watch.py、mw_common.py、mw.py、autopilot/conductor.py、autopilot/config.py、autopilot/dispatch.py；packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts、pm/ui-bridge.ts、pm/task-dispatcher.ts、worker/worker-mode.ts、worker/output-writer.ts、shared/run-store.ts、autopilot/monitor.ts、autopilot/status-model.ts、autopilot/console.ts；packages/ai/src/types.ts、packages/ai/src/utils/retry.ts；packages/coding-agent/src/core/agent-session.ts、core/settings-manager.ts、core/extensions/types.ts。
- 项目档案：.agenticdoc/goal.md（框架约束）；.agenticdoc/_pitfalls.md P-007（review 流中断 4/12）、P-028（伪 failed 块与重派禁令）、:340-352（envelope 拒绝的双 failed 与 ack 要求）。
- 任务卡：tasks/TRQ3-pm-perception.md（经 workers/trq3-pm-perception/task.md 信封下发）。
