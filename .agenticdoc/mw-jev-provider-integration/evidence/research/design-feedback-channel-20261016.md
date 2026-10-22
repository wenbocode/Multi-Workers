# design: 决策建议的反馈通道（RQ-D4）——既有 PM 可见面盘点与推荐路径

- key: mw-jev-provider-integration · type: research · DESIGN 相位调研
- 日期: 2026-10-16 · 只读调研：未改任何源码/配置，未 git add/commit
- 上下文: goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」；DP-1（派发前分诊）产出**旁路建议 + 置信度**，不改派发行为。本调研回答：这条建议写到哪里，PM 才会自然看到。
- 行号基准: 当日本仓工作区；pm-orchestrator.ts 全文（2004 行）已通读，关键行号经 grep 二次核对。

---

## Q1 终端 readback 机制（worker 终态结果如何注入 PM 会话）

**轮询与去重骨架**

- 轮询器 `startWorkerPollLoop`（packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1538），间隔 `POLL_INTERVAL_MS = 4000`（pm-orchestrator.ts:86，< 5s per AC-001），每 tick `workerStore.readAll()` 读 `_workers.parallel` 全量队列（pm-orchestrator.ts:1600 附近循环体）。
- 打开时基线：窗口打开时已终态的行一次性记入进程内 `notified` Set（pm-orchestrator.ts:1541-1545），**永不重放**；`readbackDelivered` 是 `notified` 的已投递子集，只喂未读计数、从不抑制投递（pm-orchestrator.ts:66-102 模块注释、:1548-1550）。
- 终态判定 `isTerminal`（pm-orchestrator.ts:88-90）：done / failed / needs-clarification / lost。
- 触发条件（终端 readback 分支，pm-orchestrator.ts:1671-1731）：状态终态 ∉ notified → C3 无 watch key 时静默消费不广播（:1676-1680）→ C1 owner key ≠ watch.key 跳过且不消费（:1682-1686）→ 持有且被 watch 才记 `notified.add` + `readbackDelivered.add`（:1688-1689）。即**每 task 每会话恰好一次**。
- 处理水位另计：`AckStore`（`_workers.acked`）是 PM 的处理水位而非交付去重，ack 状态从不触发重放（pm-orchestrator.ts:66-102 注释）；未投递且未 ack 的终态行走 widget 未读计数（pm-orchestrator.ts:1638-1650、:95-102）。

**数据来源与正文**

- 正文 = `readOutputBody(taskDir)` 读 `{taskDir}/output.md` 全文（packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:517-531），上限 `OUTPUT_READBACK_MAX = 20_000`（ui-bridge.ts:514-515），超限截断并附全文路径指针。
- header 行 = `` `[${entry.taskKey}] ${entry.status}` `` + 运行统计后缀（pm-orchestrator.ts:1716）；统计来自 `heartbeatStatsSuffix`（pm-orchestrator.ts:1483-1500）：优先 trace.log `[START]`→`[END]` 精确区间，其次 ≥2 条 `[HEARTBEAT]`，最后队列行 dispatchedAt→updatedAt。
- 无 output.md 时不许静默：先取 launcher 精确 spawn 失败原因 `readSpawnFailure`（读 worker.log 尾部 `[launcher] spawn failed` 行，ui-bridge.ts:533-548），否则给「无 output.md 摘要（worker 可能崩溃/超时）」+ 日志路径；两条路径都经 `deliverWorkerResult`（pm-orchestrator.ts:1719 有正文、:1726 无正文）。

**triggerTurn 语义（唤醒）**

- `deliverWorkerResult` = `deliverPmAlert` 的别名（ui-bridge.ts:202-205）；`deliverPmAlert` 用 `pi.sendMessage(..., { triggerTurn: true })`（ui-bridge.ts:188-200）：空闲 PM **立即开一轮 LLM turn**（处理结果→按 PM_CONTINUE_HINT 继续 PM 循环），流式中的 PM 把文本并入当前 turn。对照：`displaySummary`（ui-bridge.ts:171-179）不带 triggerTurn，只进上下文不唤醒，用于 init/mw start 等 notice。
- 收尾指令 `PM_CONTINUE_HINT`（pm-orchestrator.ts:1475-1481）：按终态分支给「吸收→重试/修复/澄清→ack_worker_result→派发下一个」的固定语。
- 同族旁支（同一唤醒通道）：发散风险 escalation——运行中 worker 的 `[CHECKPOINT]` risk=mid/high 每 task 一次 `deliverPmAlert`（pm-orchestrator.ts:1646-1672，`escalated` Set 声明 :1562、`escalated.add` :1654）；门提醒 remind 行投递（pm-orchestrator.ts:1737-1795，见 Q2）。

## Q2 PM 侧告警面（dispatch-alarm 与 model-error 写到哪、行格式、谁读、何时唤醒）

**唯一 ledger 写入点**

- `recordDispatchAlarm`（pm-orchestrator.ts:623-641）：append 一行 JSON 到 `.agenticdoc/_autopilot/auto-decisions.jsonl`（常量 AUTO_DECISIONS_FILE pm-orchestrator.ts:558）。行形状固定五元组 `{ seq, phase: "dispatch-alarm", kind, count, detail }`（pm-orchestrator.ts:636）；seq = 文件非空行数 + 1（:628-634）；**best-effort**：任何 I/O 失败只 console.error，绝不破派发（:619-641 注释「losing the alarm must never break dispatch」）。
- `describeDispatchAlarm`（pm-orchestrator.ts:563-610）给每个 kind 一句人文案；`formatDispatchAlarm`（pm-orchestrator.ts:611-617）加判定词：真拒绝类 `[mw] dispatch 已拒绝：…`，notice 类 `[mw] dispatch 提示：…`（`NOTICE_DISPATCH_ALARM_KINDS` pm-orchestrator.ts:543-551：out-of-scope / orphaned-keys / orphan-repair-skipped / model-error）。

**ledger 的 phase 值全集（所有写者）**

| phase | 写者 | 位置 |
|---|---|---|
| `decide` | conductor（gate 自动决策/breaker） | packages/multi-workers/autopilot/conductor.py:8206（_build_auto_row）、:7819（breaker） |
| `revoke` | conductor（撤销） | conductor.py:7697 |
| `applied` | conductor（落地） | conductor.py:5973 |
| `remind` | conductor（门提醒） | conductor.py:3604（_REMIND_PHASE :3216） |
| `remind-suppressed` | conductor（超 cap 静默记录） | conductor.py:3570（_REMIND_SUPPRESSED_PHASE :3226） |
| `dispatch-alarm` | TS PM 窗口（recordDispatchAlarm） | pm-orchestrator.ts:636 |

- 决策消费者只过滤 `phase == "decide"`（conductor.py:7650-7660 auto_consumption_set；:7689-7693 revoke 校验；夜间配额 _night_rows :7729-7737 只认 decide+executed）。`dispatch-alarm` 行对它们不可见（pm-orchestrator.ts:617-622 注释明说这是刻意设计）。

**dispatch-alarm 的 kind 全集**（DispatchAlarmKind，pm-orchestrator.ts:479-549）

queue-rows-unparsable / queue-unreadable / dispatch-quota / out-of-scope / orphaned-keys / run-ledger-conflict / no-product / write-scope-risk / orphan-repair-skipped / write-face-refusal / model-error。

**谁读 ledger、PM 何时被唤醒（三条路径）**

1. **派发扫描告警（写入即投递）**：PM 窗口每次 agent_settled（pm-orchestrator.ts:1942）跑 `dispatchNewTasks`，扫描内聚合发射 `flushScanAlarms`（pm-orchestrator.ts:1227-1266）与配额告警（:1375、:1430），接线处 `recordDispatchAlarm(agenticdocRoot, alarm)` + `deliverPmAlert(pi, formatDispatchAlarm(alarm))`（pm-orchestrator.ts:1975-1976）——**ledger 行 + triggerTurn 唤醒同时发生**。真拒绝类每 kind 每会话一次去重（`dispatchAlarmsSeen` :1936-1940 声明、:1961-1967 判定）；per-task 写面拒绝 write-face-refusal 每 task 一行绝不去重（reportWriteFaceRefusal :767-786，onRefusal 投递 :1951）。
2. **终态感知告警（只写 ledger，不投递）**：终端转移时 `recordWriteScopeResidualRisks`（pm-orchestrator.ts:671-677，读 trace.log `[WRITE_SCOPE]` 行同时含 blocked=false 与 risk=deny-basename :657-666）与 `recordModelErrorTerminal`（pm-orchestrator.ts:738-752）都只经 recordDispatchAlarm 落行，**不调 deliverPmAlert**。model-error 判据：run.json `model_exhausted:true`（:688-705）或 Exit Reason 前缀 `model unavailable:`（MODEL_UNAVAILABLE_PREFIX :680，isModelErrorTerminal :712 起），同 key 连续 K=2（MODEL_ERROR_STREAK_K :684）才记一行；PERCEPTION ONLY 不拦重派（:731-737 注释）。**读者盘点：这两类行没有任何自动读者**——TS 侧 ledger 唯一读者只认 remind（路径 3），doctor 只解析 write-face-refusal（路径 4）；本项目实例 `.agenticdoc/_autopilot/auto-decisions.jsonl` seq=10 的 model-error 行即写后无人读。
3. **remind 行（唯一有 TS 读者的 phase）**：conductor 写 `phase:"remind"` 行 → TS `readGateReminders`（packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:1222-1256，宽容解析跳过撕裂行）→ PM 轮询循环检查（pm-orchestrator.ts:1737-1795），seq 水位 `reminderWatermark`（开窗基线 :1569-1585；投递时推进 :1777、并持久化 `GATE_REMINDER_ENTRY_TYPE` entry（声明 :1504、appendEntry :1783））保证一行只唤醒一次 → `deliverPmAlert`（pm-orchestrator.ts:1789-1793）。dropped 也有可见记录（GATE_REMINDER_DROPPED_ENTRY_TYPE :1513、recordDroppedGateReminder :1525-1547）。
4. **Python 侧读者**：conductor `auto_decision_rows`（conductor.py:7616-7635，宽容读）→ consumption/revoke/配额；`mw doctor` 的写面审计 `_doctor_write_face`（packages/multi-workers/mw.py:2556 起，读 ledger 行 :2604-2614）解析 ledger 中 `phase=="dispatch-alarm" && kind=="write-face-refusal"`（mw.py:2529-2553 `_parse_write_face_ledger_row`）+ timeline 的 `write-face-*` 事件（mw.py:2465 前缀）——**doctor 不读其它 kind 的 dispatch-alarm 行**。

## Q3 autopilot 侧的 PM 可见面盘点（.agenticdoc/** 谁被读、谁是死面）

**PM/conductor 自动读并呈现的（活面）**

- `_workers.parallel`：轮询每 4s 读（pm-orchestrator.ts:1600）→ widget renderWatchLines + 终端 readback + 派发扫描（:1190 readQueue）。
- `_workers.acked`：有终态行才读一次（pm-orchestrator.ts:1602-1606）→ 未读计数。
- `_index.parallel`：IndexStore（派发扫描内 :1277、pmActivate :1843）→ widget / claim 判定。
- `_autopilot/auto-decisions.jsonl`：**仅 remind 行**被自动读并唤醒 PM（Q2 路径 3）。
- `{key}/workers/<task>/`：task.md（派发扫描逐候选读，pm-orchestrator.ts:1303-1330 收集、:1476 读取）；output.md（readback 正文 ui-bridge.ts:517-531）；worker.log（spawn 失败尾行/needs-clarification 回退 ui-bridge.ts:533-565）；trace.log（`[START]/[END]/[HEARTBEAT]` 统计 :1483-1500、`[CHECKPOINT]` risk :1646-1656、`[WRITE_SCOPE]` residual :657-666）；run.json（runVerdict / `model_exhausted` :688-726）。
- `{key}/pm-state.md`：docs gate 取 phase（pm-orchestrator.ts:1410 StateManager.read）+ claim 镜像（syncPmStateClaimId）。
- goal.md：readGoal（nudge + worker `[GOAL_CHECK]` mtime，output-writer.ts:753）。
- 按需命令面（不自动、不唤醒）：/autopilot status|gates|gate|timeline|roadmap（packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts，stateless file-derived，读 `_autopilot/config.json`/gates/timeline/roadmap，console.ts:59-66）；`mw doctor`（人运行）。

**写了但没人自动读的（死面/半死面）**

- dispatch-alarm 行中**不经 onAlarm 现场投递**的两类：write-scope-risk、model-error（Q2 路径 2）——ledger 审计行，无 TS 读者、doctor 不解析；只能人开文件看。这就是「只有机器看得见的通道」的现成反例，DP-1 建议通道必须避开这个形态。
- 其余 dispatch-alarm 行（经 onAlarm 呈现过一次的 out-of-scope 等）：呈现后其持久行也只是审计，无再读者。
- `_autopilot/timeline.jsonl`：PM 不自动读（仅 /autopilot timeline 按需）；**单一写者纪律**——只有 conductor 写（pm-orchestrator.ts:349-353 注释「single writer (the conductor, timeline.py D-109)」），TS 侧不得写（T-16c 明确拒绝在这里写第二条 timeline）。
- trace.log 的 `[VERIFY]/[FLOW]/[WRITE_SCOPE_SUMMARY]/[MODEL_ERR]/[MODEL_RETRY]/[MODEL_FALLBACK(-SKIP)]/[IDLE_KILL]/[TIMEOUT]`：worker/launcher 状态机自用（launcher.py `_model_retry_history`/`_model_fallback_history` 推导），PM 只读其中 [CHECKPOINT]/[WRITE_SCOPE] 特定形状与 START/END。
- `gates/**`、`tickets/**`、`xkey/ledger.json`、`l3-verdict.txt`：conductor/autopilot 域基建（change-ledger.ts:353 infra 清单；xkey-gate-guard.ts:73 明说 timeline/config/auto-decisions 只由 conductor 写，agent 工具被禁写）。

## Q4 候选落点对比表（把「DP-1 建议 + 置信度」送到 PM 的最小改动路径）

| # | 候选 | 实现位置 (path:line) | 改动量 | 触发 PM 唤醒 | 与并行 key 冲突 | 失败影响 |
|---|---|---|---|---|---|---|
| A | **新增 dispatch-alarm kind（notice 类）经既有 onAlarm 通道**：recordDispatchAlarm + deliverPmAlert | pm-orchestrator.ts:479-549（+kind）、:563-617（+describe/format case）、:636 行形状不动、投递接线 :1975-1976（或 DP-1 调用点直呼 :623-641 + ui-bridge.ts:188-200） | 小：1 个 kind + 1 段文案 + 调用点各一次 emit；无新文件/新读者/新格式 | **是**（triggerTurn，派发当时即见，与刚派任务同上下文） | 低：pm-orchestrator.ts 不在任何 active key 声明写面（本 key spec §2.4 冲突清单仅 mw.py cmd_model 段 + ui-bridge.ts /mw model 段）；ledger 追加写与 conductor 共文件但 append-only、seq 自算，最坏 seq 重复为既有已知形态（pm-orchestrator.ts:628-634 同构） | recordDispatchAlarm best-effort（:625-641）丢行不破派发；deliverPmAlert 失败不破派发；DP-1 本身 fail-soft（AC-002） |
| B | 写进派发回执：`_workers.parallel` 行加列 / task.md 注入建议行 | worker-store.ts:13-31（9 列格式）、:107-110（7/8/9 列容差解析）；launcher.py/conductor.py/doctor 的队列读取全链 | 大：改共享队列格式须同步 writer/parser+launcher+conductor+doctor；改 task.md = 改派发输入 | 否（队列行不触发投递） | **高**：`_workers.parallel` 是全系统最热文件（launcher/conductor/多 PM 窗口/doctor）；task.md 有 conductor 单写者段（origin: conductor，pm-orchestrator.ts:452-476） | 格式漂移破坏列容差；改任务卡违背「不改写派发」（spec §1.1 DP-1 旁路铁律） |
| C | 写 worker trace.log 由终端 readback 带出 | orchestrator 侧 append trace（先例：ensureServiceEnvelope 写 `[ENVELOPE_FALLBACK]` pm-orchestrator.ts:1020-1026）；readback 消费 :1671-1731 | 小-中 | **时机错位**：readback 在终态才发生，DP-1 是派发前——PM 看到时任务已跑完，只能当事后审计 | 低（单任务目录内） | append 失败可忽略；「PM 自然看到」不成立 |
| D | 只进 doctor（新增 triage/decide doctor 行） | mw_common.py:4440-4500（doctor 行渲染段，`dispatch:` :4485、`dispatch_fallback:` :4490-4496 先例） | 小 | **否**（doctor 是人按需运行的运维面，PM agent 不自动看 → 死面，违背 AC-008「不新造通道」要求） | 低 | 无；作为唯一通道不满足 AC-007/008 |
| E | conductor 侧写新 phase 行 + 新增 TS 读者唤醒 | conductor.py:7638-7648（_append_auto_decision_row）+ status-model.ts 新 reader（仿 readGateReminders :1195-1256）+ 轮询接线 pm-orchestrator.ts:1737-1795 | 中-大：新 phase 值 + 新读者 + 水位管理两套 | 是（若读者接 deliverPmAlert） | 新 phase 值须避让 decide/revoke/applied/remind/remind-suppressed/dispatch-alarm 全集；改 conductor.py 与 status-model.ts 两个共享文件 | 读者 bug 会进 4s 轮询热路径（有 :1802-1812 catch 兜底）；改动面最大，仅当 DP-1 调用点被 D1 定死在 Python 侧时才值得 |

## Q5 命名与格式避让（既有标识/前缀完整清单 + confidence 落点）

**trace.log / worker.log 机器行前缀（新前缀不得撞）**

| 前缀 | 写者 | 位置 |
|---|---|---|
| `[MODEL_ERR]` | worker | worker-mode.ts:3848（文本上限 MODEL_ERR_TEXT_MAX=200 :4053） |
| `[IDLE_KILL]` | worker | worker-mode.ts:2449 |
| `[TIMEOUT]` | worker | worker-mode.ts:3288（与 IDLE_KILL 并列的既有判定记录） |
| `[CHECKPOINT]` | worker | output-writer.ts:676、worker-mode.ts:3348 |
| `[GOAL_CHECK]` | worker | output-writer.ts:753 |
| `[HEARTBEAT]` | worker | output-writer.ts:765 |
| `[WRITE_SCOPE]` | worker | worker-mode.ts:2364 |
| `[WRITE_SCOPE_SUMMARY]` | worker | worker-mode.ts:2385 |
| `[START]`/`[END]` | worker | output-writer.ts:600 / :743（readTaskProgress 消费，pm-orchestrator.ts:1483-1500） |
| `[ENVELOPE_FALLBACK]` | PM/launcher | pm-orchestrator.ts:962-963 |
| `[launcher] spawn failed` | launcher | ui-bridge.ts:541（前缀匹配读回） |
| `[MODEL_RETRY]`/`[MODEL_FALLBACK]`/`[MODEL_FALLBACK-SKIP]` | launcher | launcher.py:822-873 |

- 实测：`triage` 在 packages/multi-workers 与 coding-agent/src **零命中**；`TRIAGE|triage-suggestion|triage-unavailable` 全仓（去 dist/node_modules）零命中 → `[TRIAGE]`（或 `[DECIDE-T1]` 类）作 DP-1 证据行前缀不撞名。

**ledger phase 值**：decide / revoke / applied / remind / remind-suppressed / dispatch-alarm（Q2 表）。
**ledger 行字段**：
- decide 行（conductor 域，勿混用）：decision_id, gate_id, gate_kind, gate_stage, gate_key, mode, executed, decision, rule_id, rule_version, reason_code, refusal_code, prop_ok, decided_by, decided_at, evidence, switch, budget, gate_file_sha256_before/after, counterfactual_human, night（conductor.py:8185-8234）；权威投影 `_AUTO_AUTHORITY_KEYS`（conductor.py:7666-7673）。
- dispatch-alarm 行：seq / phase / kind / count / detail 五元组（pm-orchestrator.ts:636）；kind 全集 = Q2 的 11 个。
- 实测 `confidence` 全仓零业务命中（仅 theme.ts 的 UI 无关词）→ `confidence` / `confidence_source` 作为字段/键不撞名。

**timeline ev 值**：gate-reminder（conductor.py:3215）、gate-auto-decision（:6548）、gate-auto-revoke（:6549）、`write-face-` 事件族（mw.py:2465）、config（conductor.py:7834）。
**doctor 行前缀**：`activation:` / `pi_shell:` / `dispatch:`（:4485）/ `dispatch_fallback:`（:4490、:4496）/ `credentials:`（mw_common.py:4440-4500）。→ doctor 新行用 `triage:` 不撞。
**session entry customType**：agent-team-loop:watch（ui-bridge.ts:228）、:worker-summary（ui-bridge.ts:173-179）、:gate-reminder-seen（pm-orchestrator.ts:1504）、:gate-reminder-dropped（pm-orchestrator.ts:1513）。
**PM 文案判定词**：`[mw] dispatch 已拒绝：`/`[mw] dispatch 提示：`（pm-orchestrator.ts:611-617）、`[mw] 发散风险：`（:1661）、`[mw] 门提醒（`（:1789-1793）。

**confidence 与来源标识（api vs model-self-report）放哪最自然**

- **不进既有 ledger 行的结构化字段**：decide 行是 conductor gate 决策域（decided_by="conductor"），DP-1 是派发前分诊，语义不同源；dispatch-alarm 行保持五元组不动，mw.py:2529 的解析与未来读者零改动兼容。给 `DispatchAlarm` 接口加结构化字段 = 改共享类型 + 所有消费面，改动量与风险都不成比例。
- **两层落法**：(1) **全量结构化字段进 DP-1 自己的机器可读证据行**（AC-008 要求的 decision_point/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source），用新前缀 `[TRIAGE]` 或独立 JSONL，格式由 D2/设计定——这是 confidence 的权威载体；(2) **PM 呈现面（alarm 的 detail 字符串 + 文案）带紧凑摘要**：`detail: "task=<k> type=<t> risk=<r> confidence=<0..1> confidence_source=api|model-self-report backend=<b> attempts=<n> latency_ms=<ms>"`，文案显式标「旁路建议，未据此改派发」+ 来源标识——AC-001 的「两者不得混同呈现」在文案层用 confidence_source 直接兑现。detail 是自由文本（pm-orchestrator.ts:636），追加键值对零格式风险。

## Q6 结论：推荐通道 + 降级呈现

**首选通道（单一）：既有 dispatch-alarm ledger + deliverPmAlert 通道，新增 notice 类 kind `triage-suggestion`（备查 kind：`triage-unavailable`）。**

DP-1 在派发路径产出建议后：

1. `recordDispatchAlarm`（pm-orchestrator.ts:623-641）追加 `{"phase":"dispatch-alarm","kind":"triage-suggestion","count":<本扫描建议数>,"detail":"task=… type=… risk=… confidence=… confidence_source=… backend=… attempts=… latency_ms=…"}`——每扫描聚合一行（仿 flushScanAlarms 聚合先例 pm-orchestrator.ts:1227-1266；单扫描配额默认 3（DEFAULT_DISPATCH_MAX_PER_SCAN pm-orchestrator.ts:785）兜住噪音上限）。
2. 经既有 onAlarm 接线（pm-orchestrator.ts:1975-1976）或调用点等价直呼 `deliverPmAlert(pi, formatDispatchAlarm(alarm))`——notice 词 `dispatch 提示`（:611-617，新 kind 进 NOTICE_DISPATCH_ALARM_KINDS :543-551），`triggerTurn` 让 PM 在派发当时被唤醒，建议与它刚派的任务出现在同一上下文。

**理由**：(a) PM 自然看到——这是 PM 平日就在收、且会处理的面（与 out-of-scope/model-error 告警同通道），写入即投递，不是「只有机器看得见」的死面（对照 Q3 write-scope-risk 反例）；(b) 改动最小——一个 kind 常量 + 一段 describe 文案 + 调用点 emit，无新文件、新读者、新格式、新 phase；(c) 无并行冲突——pm-orchestrator.ts 不在 mw-model-fallback-cli（active）的声明写面（mw.py cmd_model 段 / ui-bridge.ts /mw model 段，spec §2.4）；ledger append-only 无锁竞争。
**备选通道**：若 D1（锚点调研）把 DP-1 调用点定死在 Python 侧（conductor/launcher），则用 E 的收敛版：conductor 经 `_append_auto_decision_row`（conductor.py:7638-7648）写**同一个** `phase:"dispatch-alarm", kind:"triage-suggestion"` 行（复用既有 phase，不造新 phase 值）+ doctor `triage:` 行；但 ledger 行本身不唤醒 PM（Q2），必须补一个 TS 侧读者（仿 readGateReminders）才完整——改动量变大，故仅在上游强制 Python 侧时采用。
**明确不推荐**：B（队列/任务卡——共享格式冲突 + 改派发输入之嫌）、C 作为主通道（终态才可见，时机错位；可留作可选的事后审计行）、D 作为唯一通道（死面，违背 AC-007/008）。

**降级呈现（决策不可用时，必须与「建议已产出」可区分）**：

- **ledger/证据层**：每次决策调用（含失败）都写机器行（AC-008）：可用 ⇒ 行内必有结论值 + `confidence=` + `confidence_source=`；不可用 ⇒ `available=false reason=<unconfigured|timeout|upstream-error|unparsable|429>`，**无结论值、无 confidence 值**。机器判别锚点 = `available` + `reason` 两个字段。
- **PM 呈现层（默认静默）**：不可用时不投递任何建议文案——PM 面零噪音，静默在结构上不可能被误读为「决策已生效」（这正是 spec D-4 禁止形态的反向保证）。可选配置（如 `triage_notify_on_unavailable`）开启后才投一条 `kind:"triage-unavailable"` 的 notice（同通道、每会话去重仿 dispatchAlarmsSeen :1961-1967），文案句式与建议完全不同：「决策服务未产出建议（reason=…），派发照常」——无结论值、无 confidence、明示「未产出」。
- **doctor 运维面（AC-010）**：`triage: enabled <backend> last_probe=<结论> last_suggestion=<ledger seq|none> last_unavailable=<reason|none>`——「链路不通」与「已产出建议」一条命令可对照（`dispatch_fallback:` 行 mw_common.py:4490-4496 为格式先例）。
- 三层共同保证：`triage-suggestion` 行（有结论+置信度+来源）与 `triage-unavailable` 行/静默（只有 reason）在 kind、字段、文案三处均可机判，不存在把不可用呈现成已生效的路径。

## 残留与未验证

- D1（triage anchors）尚在并行运行（workers/jev-d1-triage-anchors 当时无 output.md）：DP-1 调用点最终落 TS 还是 Python 未定，Q6 首选/备选的选择以此为切换条件；两案均已给实现锚点。
- `recordDispatchAlarm` 的 seq 自算（pm-orchestrator.ts:628-634）与 conductor 的 `_append_auto_decision_row` seq 自算（conductor.py:7642）在并发 append 时可能产生重复 seq——既有形态（dispatch-alarm 行无消费者按 seq 去重），triage 行若将来需要按 seq 水位去重须先解决；本推荐用 kind+会话内 Set 去重，不依赖 seq。
- 未实测：新 kind 经 `formatDispatchAlarm` 的完整文案在 TUI 的实际渲染（只读码推断）；对 PM 上下文成本的量化（每扫描一行 + 一条消息）未测。
- AC-008 的证据行权威格式（前缀/文件位置/字段序）属 D2+设计相位产物，本调研只锁定「PM 呈现走 alarm detail、全量字段走证据行」的分工，不锁证据行本身格式。
- mw doctor 对 write-face 之外 dispatch-alarm 行的「不解析」结论基于 mw.py:2529-2553 与全仓 grep（write-scope-risk/model-error 无其他机器读者）；若未来 key 添加读者需重查。
- `(agenticdocRoot, "_autopilot", AUTO_DECISIONS_FILE)` 的 TS/Python 双写者并发 append 无文件锁（双方都是 open-append）；现有 11 行实例未见 seq 冲突，但这是观察非证明。

## 上下文来源

- 任务卡：`.agenticdoc/mw-jev-provider-integration/tasks/D4-feedback-channel.md`
- key 规格：`.agenticdoc/mw-jev-provider-integration/spec.md`（§1.1 DP-1 旁路建议、AC-001/002/007/008/010/012、§2.4 冲突约束、§5 坑点）
- 既有调研证据：`.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-decision-surface-20261016.md`（RQ-3 决策面锚点表/反馈链清单）、`spec-jev-live-probe-20261016.md`（D-1 上游阻断背景）
- TypeScript（全文或定位段通读）：pm-orchestrator.ts（2004 行全读）、ui-bridge.ts（投递/读回函数段）、status-model.ts（readGateReminders 段）、worker-store.ts（行格式段）、worker-mode.ts / output-writer.ts（trace 前缀定位）、task-dispatcher.ts（:425-439 拒绝理由镜像段）、change-ledger.ts / xkey-gate-guard.ts（infra 写面清单）、autopilot/console.ts（命令面）
- Python：packages/multi-workers/autopilot/conductor.py（ledger 写读/decide 行构造/remind 发射）、mw.py（_doctor_write_face 段 :2461-2650）、launcher.py（fallback trace 前缀）、mw_common.py（doctor 行渲染 :4440-4500）
- 运行实例数据：`.agenticdoc/_autopilot/auto-decisions.jsonl`（11 行实读，含 model-error 死面行 seq=10）
