# DRQ-2｜状态面设计（monitor 常驻行 / 抑制原因六值枚举 / 无 watch 丢弃痕迹 / `GateView` 扩展）

- Key: `mw-autopilot-gate-alarm-liveness`｜任务: T-06（DRQ-2）｜阶段: design｜性质: **只读取证**
- 唯一写入 = 本文件。所有数字为「本机命令输出」或「逐行源码阅读」产出；**未跑 pytest/vitest**（见 `## 残留与未验证`）。
- 行号纪律：本文所有 `path:line` 用 **`\n` 分行的规范行号**（Python `split("\n")` / 本仓 grep 工具）。PowerShell `Get-Content` 对同文件会给出偏移行号（实测 `monitor.ts` 偏 −1、`conductor.py` 偏 −3~−4、`pm-orchestrator.ts` 偏 −4），**不得作为引用来源**。
- 时间基准: 2026-10-13（UTC+08），与 RQ-1..RQ-4 / DRQ-1 同批。

## 结论

**C1 — 常驻行需要的派生字段共 6 个新增 + 6 个已有，全部可在派生层算出、零落盘。** 新增：`reason`（六值枚举）、`reminders {n,max}`、`nextDueMs`、`scopeResolved`、`queueState`、`inFlightForKey`（已存在于 monitor 的 keys 段，只是没接到 gate 行）。已有：`id/kind/stage/key/createdAt/ageMs/drift`（`monitor.ts:419-435`）。归属：**判定面**（Python 漏斗，`conductor.py:2555-2573`）与**展示面**（TS `monitor.ts`、TS `status-model.ts:1467-1473`、Python doctor `mw_common.py:2900-2990`）各自派生，互不写盘；`reminders` 的唯一权威输入是台账 `phase=="remind"` 行（`conductor.py:2509-2520`），TS 已有等价读取器 `readGateReminders`（`pm-orchestrator.ts:1289-1322`）但**未接入 monitor**。**每 tick 新增读放大 = 1 个台账文件**（本机实测 `E2Feature` 1,117 B、`FeatureMigrator` 无该文件、JCodingAss 无 `gates/`），相对已有的 timeline 尾窗读（`monitor.ts:465-467`，默认 512 KiB / 400 条 / 4 s）可忽略；护栏：台账 >1 MiB 时按尾窗读并置 `remindersTruncated=true`，禁止静默显示 `0`。

**C2 — 六值枚举的判定输入全部已有（唯一缺口是「队列不可读」与「scope 不可解析」没有任何字段承载）。** 逐值：`key-in-flight` = gate.key + 非终态 worker 行（删掉 `conductor.py:2558` 的项目级提前 return，改 `any(_is_in_flight(r) and _row_belongs_to(r, gate.key) for r in rows)`，成例 `:299 / :878 / :3530 / :6874`）；`stage-terminal` = `gate.stage ?? stage_of_key[gate.key]` + rank 表 `conductor.py:561-569` 阈值 2（`TS` 侧**只有闭集** `status-model.ts:397`，**没有 rank 镜像**，须新增）；`cap-reached` = `_reminder_count` vs `gate_reminder_max`（`config.py:103`，闭区间 `[1,2]` 见 `:134`）；`not-due` = `_gate_created_epoch(created_at)` + `n*after_min*60`（`conductor.py:2573`，`after_min` = `config.py:102`）；`unresolved-scope` = key 不在 roadmap / stage 悬空 / stage 状态不在 rank 表 / `created_at` 不可解析 / key 为空且无 stage（`conductor.py:2565-2567`、`:2569-2570`、`:2573` 三处 fail-open 分支）；`gate-queue-unreadable` = **三读面全部缺承载**（见 C2.3）。**优先级 = 代码漏斗序**：`gate-queue-unreadable > key-in-flight > cap-reached > stage-terminal > not-due`；`unresolved-scope` 是**与抑制正交的兜底标记**（AC-002 要求它一律不抑制），必须作为独立 token 与 `reason` 并列显示，不参与原因竞争。**六值不是全集**：真正"本轮到期/已发射"的 gate 无抑制原因，行内必须显式 `reason=-`（或 `due`），否则会撒谎。

**C3 — 现行 drop 序在事故形状下会先丢 `reason`、再丢 `age`，而 44 列的 `-> /autopilot gate <id> approve|reject` 被完整保留 ⇒ AC-001 的三项（reason/age/scope）里有两项在最需要时不可见。** 算例（`monitor.ts:888-907`）：`gate-0022 (stalled)` + `key=gui-release-hardening` 的 base+answer = 38+44，加 scope/age/reason 后 141 列 → 丢 reason(101 at 120) 后仍超 → 再丢 age 才 109。修复 = ①动作串先降级（` -> /autopilot gates`，20 列；每 gate 的完整命令仍在 `/autopilot gates` 卡片 `console.ts:349-...`）；②有界化 `kind` ≤14 / `key=` 体 ≤16（省略号）；③丢序改为 `drift → scope → age → reminders → reason`（`reason` 最后丢，且全丢仍超长时用 `reason=?` 而不是静默省略）。有界化后 stage 类 gate 的 AC-001 全集 = 19+10+15+8+11+14+25 = 102 ≤ 110，**永不丢**。

**C4 — `GateView` 两方案都不动 `GateView` 本身，因此 `autopilot-console.test.ts:384-389` 的 `toEqual` 零风险。** 方案 A：新增旁挂视图 `GateStateView[]`（`AutopilotStatus` 增可选字段），与 `gates` 同源同一次 `gateScan` 派生；风险 = 版本化 schema（`status-model.ts:1307`）增字段需同步文档/严格校验器，且必须写死"gateStates 不得混入 gates"。方案 B（**推荐**）：只扩 `MonitorGate`（monitor 私有、非版本化）+ 把 `readGateReminders` 提升到 `status-model.ts` 供 monitor 复用；`GateView`/`--json` 零改动；风险 = `--json` 仍答不了"为什么没提醒"、reason 的 TS/Python 双实现是漂移面（需六值字符串 + 漏斗序 parity 测试）。

**C5 — "无 watch 丢弃"的可见痕迹：主落点是状态面本身（panel 行与 watch 无关），字面 drop 记录用既有 pi entry 机制另开一个 entry type，且必须不碰 `reminderWatermark`。** 丢弃点仅 3 处：`pm-orchestrator.ts:1489`（`!watch.key`）、`:1490`（key 不匹配）、`:1511-1513`（catch 静默吞读错）；窗口 watch 状态是进程内存（`:251/:256/:301`），**磁盘不可见**，所以"被丢弃"必须由丢弃者自己留痕。反例（必须写进设计）：若把 drop 记成与投递同类型的 `GATE_REMINDER_ENTRY_TYPE` 且带 `seq`，恢复路径 `:1468-1482` 会把 `reminderWatermark` 推进到 drop 的 seq，之后**真正投递被永久抑制**。

**C6 — 「重启后 pending 门禁未被新自动裁决意外改写」可做成三条纯只读、零新通道的机器判据。** 起点成例：`main` 启动即写 `goal-snapshot`（`conductor.py:7240-7242`）。输入 = 启动普查（`ConductorState` 内存 `{gate.id: sha256}` + `started_at`，不落盘）与盘上既有证据（ledger decide 行的 `gate_file_sha256_before/after` + `executed` + `decided_at`，`conductor.py:6795-6796`、`:6802-6811`；gate 文件 `status/answered_at/consumed_at`；timeline `gate-answered`）。判据：R1「重启后 executed 的自动裁决，其 `before` sha 等于启动普查 sha」→ 改写；R2「executed 行记录 `after=H` 而盘上 sha≠H」→ 答案未落盘/被改写；R3「status=pending 却带 `consumed_at`/`answered_at`」→ 越权重写痕迹。出口 = 复用 T-20 双通道（stderr + timeline `config`）与会话级去重 `_ROADMAP_ALARM_SEEN`（`conductor.py:2594`、`_emit_roadmap_failure:2603`），**不新造事件名**（新名要跨语言 `EVENT_TYPES` parity）。

**C7 — AC-002 有一条最易漏的连带面：`blocked_on_human` 在三处都是"项目级非终态行数"。** `monitor.ts:442`、`status-model.ts:1354-1356`、`mw_common.py:3279-3291`（doctor 用 `_doctor_queue().non_terminal_count`）。发射判据改 per-key 后，三处会与发射器不一致（别 key 在飞 ⇒ 面板不显示 `BLOCKED_ON_HUMAN`，而该 gate 的提醒照发）。必须同批改为 per-gate 或把两轴分开显示。

## 证据

### 1 渲染链与常驻行落点（逐行核实）

| 环节 | 位置 | 事实 |
|---|---|---|
| 队列扫描 | `monitor.ts:234-290` `scanPendingGate` | 手写 frontmatter 行扫描，**只收** `id/kind/status/key/stage/created_at/reason_code/evidence_refs`；`status!=pending \|\| id=="" \|\| kind==""` → null（`:293`）。**未收** `consumed_at`/`answered_at`（C6-R3 需要）。 |
| 目录扫描 | `monitor.ts:419-434` | `fs.readdirSync` 抛错被 `catch{}` 吞 → 与"空队列"无差别（注释写的就是"gates dir missing — empty queue"）。单文件读失败 = `scanPendingGate` 返回 null（`:235-240`）→ **该 gate 从面板消失**。 |
| 年龄/漂移 | `monitor.ts:426-431` | `createdMs = Date.parse(createdAt)`；`ageMs = max(0, now-created)`；`drift = gateDriftDetail(...)`（`:311-333`）。 |
| 真值表 | `monitor.ts:442`；`status-model.ts:1354-1356`；`mw_common.py:3279-3291` | 三处同为 `pending>0 && nonTerminalRows==0`（项目级）。 |
| 面板 | `monitor.ts:766-911` | `MONITOR_LINE_MAX = 110`（`:77`）；`BLOCKED_ON_HUMAN` 行 `:829-834`；gates 段 `:878-908`。 |
| token/丢序 | `monitor.ts:891-907` | scope(`:892`, drop 3)、age(`:893-894`, drop 2)、`reason_code`(`:895-896`, **drop 1**)、drift(`:897`, drop 4)；循环 `for (const drop of [1,2,3,4])` 保留 `t.drop > drop`；兜底 `trunc(line, 110)`（`:907`）。 |
| 台账读 | `pm-orchestrator.ts:1289-1322` `readGateReminders`（私有、只被 `:1366/:1466` 用）；`conductor.py:2509-2520` `_reminder_count`（由 `:2699` 调用） | TS 侧等价物存在但 monitor 未接。 |
| 宽度常量 | `monitor.ts:77`；`console.ts:231` `GATE_CARD_LINE_MAX = 110` | 两处独立常量、同值。 |

### 2 六值枚举：逐值判定输入与计算位置

| 值 | 判定输入 | Python 计算位置 | TS 计算位置 | 现状缺口 |
|---|---|---|---|---|
| `gate-queue-unreadable` | gates 目录/文件扫描失败 | `gates.pending_gates`→`gates.enumerate`（`gates.py:744-767`，抛点 `:762`）在 `conductor.py:2692-2694` 被 `except gates.GateFormatError: return` **吞掉且零记录**；同 tick `open_goal_change_gate`（`:2900`）再抛一次并在 `:2909` 写 `config`（⇒ Python 有痕迹，但**每 tick 一条、无去重**、与"队列正常"混在同一 detail 文案里）；doctor 是唯一区分者（`mw_common.py:3329-3331` `section["error"]`、`:3339` `parse_errors`） | `monitor.ts:421-434`（readdir 失败→空）、`scanPendingGate`（单文件失败→null）；`status-model.ts:1007-1011` `catch { return {gates:[],errors:[]} }` | **三读面全缺**；面板会把"读不到"显示成 `gates: 0 pending` |
| `key-in-flight` | `gate.key` + `_workers.parallel` 非终态行 | 现为**项目级**：`conductor.py:2558 if any(_is_in_flight(row) for row in rows): return []`（AC-002 要求改 per-key）；谓词 `_is_in_flight:2981`、`_row_belongs_to:2985`→`mw_common.row_belongs_to:2026`；per-key 成例 `:299/:878/:3530/:6874` | `monitor.ts:687 inFlight: workers.filter((w) => workerBelongsToKey(w, key)).length`（已有，未接到 gate 行） | key 为空时无法归属 ⇒ 一律不抑制（fail-open） |
| `stage-terminal` | `gate.stage ?? stage_of_key[gate.key]` → rank ≥ 2 | `conductor.py:2565-2567`（两级解析）+ rank 表 `:561-568` + 阈值 `:569 _STAGE_TERMINAL_RANK = 2` | **无 rank 镜像**：`status-model.ts:397 STAGE_STATUSES` 只有闭集；`roadmap` 解析只在 `:570` 做集合校验 | TS 必须新增 rank 表 + parity 测试（否则同 gate 两侧不同标签） |
| `cap-reached` | `_reminder_count(rows, gate.id) + 1 > gate_reminder_max` | `conductor.py:2509-2520`（计数）→ `:2562-2563`（判定）；`max` 见 `config.py:103` + 闭区间 `:134` | `pm-orchestrator.ts:1289-1322`（按 `gate_id` 配对 `reminder_n` 的行计数）+ `status-model.ts:152/:191`（config 镜像） | 必须与 Python **同口径按行计数**（不能按 distinct n 计） |
| `not-due` | `now - anchor < n * after_min * 60` | `conductor.py:2573`；`anchor = mw_common._gate_created_epoch(created_at)`（`mw_common.py:2815-2825`，不可解析→None）；`after_min` = `config.py:102`（`[1,1440]` `:133`） | `monitor.ts:426-428` 已有 `createdMs`/`ageMs`；`after_min` 从 config 读 | `anchor is None` 与 not-due 共用同一个 `or`（`:2573`）⇒ 显示层不得把"年龄未知"说成 not-due |
| `unresolved-scope` | 判定所需事实缺失（key 不在 roadmap / stage 悬空 / status 不在 rank 表 / `created_at` 不可解析 / key 为空且无 stage） | `:2565-2567` + `:2569-2570` + `:2573` 三处 fail-open 分支；文档承诺见 `:2549` | `monitor.ts:647-670`（`deriveAutopilotPanel` 读 roadmap → `statusByKey`/`depsByKey`） | 是"无法判定"标记、不是抑制原因；AC-002 要求它**不抑制** |

补充事实（判断优先级时必需）：`pending_gate_reminders` 的判据顺序**就是** `:2558 → :2563 → :2569 → :2573`；`gate-reminder` 事件/台账行**只在发射时写**（`conductor.py:2708-2733`：先 append 台账行 `:2712-2720`，再 append 事件 `:2721-2733`），被抑制时**零写入** ⇒ 抑制原因无任何现成字段承载（与卡面 RQ-4 结论一致）。

### 3 优先级：为什么必须是漏斗序

- 一个 gate 可同时命中多个抑制者（例：已 cap 满 + stage 已 closed；或本 key 在飞 + cap 满）。判据之间对**发射结果**是幂等的（都是"不发"），但对**归因**不是 ⇒ 显示"第一个真正让本次不发射的条件"才不会撒谎。
- 三处抑制分支的顺序在代码里是固定的（`:2558`→`:2563`→`:2569`→`:2573`），AC-002 只把 `:2558` 从项目级改成 per-key，**不改变相对顺序**，因此"优先级 = 漏斗序"是零额外语义成本的。
- 与抑制正交的事实必须并列显示、不得被 reason 掩盖：`reminders=n/max`（cap 证据）、`scopeResolved`（AC-001 明确单列的"scope 可解析性"）、`nextDueMs`（`not-due` 的量化）。设计规则：`reason` 只回答"为什么现在没提醒"，其余事实一律独立 token。
- 兜底：`gate-queue-unreadable` 不是 per-gate 行，而是**段级**渲染（`gates: unreadable (...) -> fix`），因此它不参与 per-gate 竞争，但优先级最高（此时 per-gate 行本身不可信）。

### 4 宽度算例（`MONITOR_LINE_MAX = 110`）

`monitor.ts:888-907` 的现行构成（列数按字符计）：

```text
head   "gates: 1 pending - "                        19
base   head + id + " (" + kind + ")"                + id + kind + 3
answer " -> /autopilot gate " + id + " approve|reject"   18 + len(id) + 16 = 34 + len(id)
tokens scope(" stage=N" | " key=<key>") / age / reason_code / drift
```

实测四种形状（`id=gate-0022`(9)、`kind=stalled`(7)）：

| 形状 | scope | age | reason | answer | 合计 | 实际渲染（drop 序 reason→age→scope→drift） |
|---|---|---|---|---|---|---|
| stage gate，无 reason_code | 8 | 11 | — | 44 | 38+8+11+44 = 101 | 全保留 |
| keyed gate，无 reason_code | 27 | 11 | — | 44 | 120 | 丢 age→109（**age 不可见**） |
| stage gate，有 reason_code | 8 | 11 | 21 | 44 | 122 | 丢 reason→101（**reason 不可见**） |
| keyed gate，有 reason_code（**事故形状**） | 27 | 11 | 21 | 44 | 141 | 丢 reason→120 →丢 age→109（**reason+age 双丢**） |

⇒ 现行设计的隐含假设是"`reason` 是可有可无的附注"，与 AC-001/AC-003 把 reason 提升为交付物直接冲突；且 `answer` 串吃掉 44/110 = 40% 的宽度。

建议（C3）：动作串降级顺序 `full -> " -> /autopilot gates" -> (丢)`，事实丢序 `drift(1) → scope(2) → age(3) → reminders(4) → reason(5)`，有界化 `kind ≤ 14`、`key=` 体 `≤ 16`。有界化后最坏：
`19(head) + 10(id) + 15(" (budget-exh…)") + 8(" stage=4") + 11(" age=12d 5h") + 14(" reminders=2/2") + 25(" reason=unresolved-scope") = 102`；keyed 版把 8 换成 `19(" key=gui-release…")` → 113，先降级动作串（113−44+20=89）后仍在限内。**结论：110 列装得下 AC-001 全集，前提是动作串让位 + 两个长字段有界化。**

### 5 `GateView` 锁死断言与两个候选方案

锁死事实（逐行核实）：`autopilot-console.test.ts:384-389`

```ts
expect(s.gates).toEqual([
  { id: "gate-0001", kind: "stage-confirm", status: "approved", ageMs: 3_600_000 },
  { id: "gate-0002", kind: "stalled", status: "pending", ageMs: 3_600_000 },
  { id: "gate-0003", kind: "budget-exhausted", status: "pending", ageMs: 3_600_000 },
]);
```

`toEqual` 是**精确深比较**（含自有可枚举键）⇒ 往 `GateView`（`status-model.ts:1331-1340`）加**任何被填充的字段**都会红，即使字段"可选"。同一用例还锁 `s.schema=="autopilot-status/1"`（`:364`）、`s.stage`（`:366`）、`s.timeline`（`:392`）、`s.config`（`:394`）、`warnings==[]`（`:397`）；`:447-469` 是**两次派生结果相等**（新增字段在两份里同时出现 ⇒ 不受影响）；`:1076-1085` 只查 `parsed.schema`。全仓 `autopilot-status/1` 仅 3 处引用（`status-model.ts:1307` + 上述 2 个测试点）。

**方案 A：旁挂视图（sibling array）**
- 改动面：`status-model.ts` 新增 `export interface GateStateView { id; key: string|null; stage: number|null; reason: GateReason; reminders: number; reminderMax: number; scopeResolved: boolean; queueState: "ok"|"unreadable"|"partial" }` + 在 `deriveStatusModel` 的**同一** `gateScan`（`:1463`）旁派生（join key = id）；`AutopilotStatus`（`:1374-1381`）增 `gateStates?: GateStateView[]`；`renderStatusText` 的 gate 行（`:1530-1536`）追加 `reason=`；`console.ts:191` 的 `--json` 自动带上；`monitor.ts` 渲染 token 可选用 status 数据（也可继续自派）。
- 风险：① 版本化 schema 增字段而不改版本号（`status-model.ts:1307`）⇒ 需同步文档/外部严格校验器，并写死"`gateStates` 不得混入 `gates`"；② 两个数组必须**同一次 gateScan** 派生，否则"id 集合对不上"是新的静默错误面；③ 仍要改 monitor 渲染，未减少改动量。

**方案 B：monitor 私有派生 + 共享 helper（推荐）**
- 改动面：`monitor.ts:111-130` `MonitorGate` 增可选字段（`reason?/reminders?/reminderMax?/scopeResolved?/nextDueMs?/queueState?`，**可选**以免既有手搓 snapshot 测试红，见 `autopilot-monitor.test.ts:743/756/775/803/885`）；`monitor.ts:419-434` 后追加派生段（roadmap/config/workers 已在同 tick 内读过：`:647-670`、`:687`）；把 `readGateReminders`（`pm-orchestrator.ts:1289-1322`）**提升**到 `status-model.ts`（`pm-orchestrator.ts:6` 已 import 该模块，无环）供 monitor 复用；`console.ts:349 renderGateCards` 若要显示原因，调同一 helper（roadmap 已在 `:352` 读过）。`GateView` / `AutopilotStatus` / `--json` **零改动**。
- 风险：① `/autopilot status --json` 仍答不了"为什么没提醒"（脚本化消费延后）；② reason 在 TS 与 Python 各一份实现 ⇒ 漂移面，必须有 parity 测试锁"六值字符串 + 漏斗序 + cap 口径"（照 `status-model.ts` `EVENT_TYPES` 与 `autopilot-config-parity.test.ts` 成例）；③ 每 tick 多读 1 个文件（台账）。
- 两方案共同点：都不改 `GateView` 本体 ⇒ AC-012「扩展而非破坏」成立；把 `key/stage` 带上 gate 行不需要动 `GateView`（`MonitorGate` 早已有 `key/stage`，只是 `:892` 的 scope token 二选一，key 只在 stage 为空时显示）。

### 6 "无 watch 丢弃"：链路、反例与最小落点

链路（逐行核实，`pm-orchestrator.ts`）：`setInterval`（`:1371`, `POLL_INTERVAL_MS = 4000` 见 `:66`）→ 读台账（`:1466`）→ 首次读取时从 session entries 恢复 watermark（`:1467-1482`，`:1482 if (delivered > 0) reminderWatermark = delivered`）→ 遍历 reminders（`:1484`）→**丢弃点**：`:1489 if (!watch.key) continue;`、`:1490 if (reminder.gateKey !== "" && reminder.gateKey !== watch.key) continue;`、`:1491-1495`（seq ≤ watermark / 去重）→ 投递前先落 entry（`:1502-1506`）→ `deliverPmAlert`（`:1508-1509`，唯一 push）→ 整段被 `catch {}` 包住（`:1511-1513`，**读错即静默**）。

关键事实：窗口 watch 状态只在进程内存（`:251/:256/:301`），磁盘无痕 ⇒ "本 tick 有没有被丢弃"**不可能**从文件派生；因此可见痕迹只有两条路（不新造通道）：

1. **P1 状态面（主）**：panel 的 gate 行（AC-001）与 `BLOCKED_ON_HUMAN` 行（`monitor.ts:829-834`）与 watch 无关（monitor 是 key-agnostic：workers 段文案 `all keys`）。事件被丢弃的**后果**（gate 仍 pending、`age=` 增长、`reason=`/`reminders=n/max` 可见）在任何窗口 4 s 内可见。这是 §0「状态面优先于事件面」的直接落地，且零写入。
2. **P2 字面 drop 记录（可测）**：在 `:1489/:1490` 的 `continue` 前用既有 pi entry 机制写**独立** entry type（如 `agent-team-loop:gate-reminder-dropped`）`{gateId, n, reason: "no-watch" | "other-key" | "read-error"}`，去重键复用 `${gateId}:${n}`；`:1511-1513` 的 catch 用同型记录（`reason:"read-error"`）。
   **硬约束（反例）**：绝不能复用 `GATE_REMINDER_ENTRY_TYPE`（`pm-orchestrator.ts:1283`）且带 `seq` —— `:1472-1477` 的恢复路径读的是 `e.data?.seq`，drop 记录一旦被计入，`reminderWatermark` 会被推到 drop 的 seq，之后**真实投递被永久抑制**（`：1495`）。
3. **拒绝的候选**：`ui.notify` 瞬时 toast（不是"记录"，重启即消失）；TS 侧写 stderr/timeline（新通道，违反 P-01）。

### 7 重启复核检查点（输入 / 比对 / 告警出口）

- **落点**：`main`（`conductor.py:7216`）在 `:7240-7242` 建 `Timeline`/`ConductorState` 并**已写** `goal-snapshot` 启动事件（成例）。新增：`ConductorState`（`:183`）加 `started_at: float` 与 `pending_census: dict[str,str]`（内存，零落盘）；启动时用 `gates.enumerate`（`gates.py:744`）筛 `status=="pending"` + `_gate_file_sha256`（`conductor.py:6227`）。
- **输入（全部已在盘上，无需新文件）**：① ledger `phase=="decide"` 行：`executed`、`decision`、`rule_id`、`reason_code`、`decided_at`、`gate_file_sha256_before/after`（构造点 `conductor.py:6795-6796`，写入点 `:6802-6811`，同刻写 timeline `GATE_AUTO_DECISION_EVENT` —— 常量 `:5448`，`:6520` / `:6807`）；② gate 文件自身 `status/answered_at/answered_by/consumed_at`（`consumed_at` 字段 `gates.py:265`，写点 `_mark_gate_consumed:453`）；③ timeline `gate-answered`（`conductor.py:530/:538/:550`）。
- **比对（每 tick，纯只读；成本 = gates 枚举 + 1 次 ledger 读，均已在本 tick 内发生）**：
  - **R1（核心）**：∃ ledger 行满足 `phase=="decide" ∧ executed==true ∧ decided_at >= st.started_at` 且 `gate.id ∈ st.pending_census` 且 `gate_file_sha256_before == pending_census[gate.id]` ⇒ **重启后新自动裁决改写了一个启动前就 pending 的 gate**。这是 AC-005 尾句的机器判据，也正好命中"进程跑旧代码"事故的反向风险（重启后新代码首次生效）。
  - **R2**：∃ `executed==true` 行 with `after=H`，而该 gate 仍 `pending` 且当前 sha `!= H`（且 `== before`）⇒ 记录的答案未落盘/被改写（审计分歧）。
  - **R3**：`status=="pending"` 而文件带 `consumed_at` 或 `answered_at` ⇒ 越权重写痕迹（幂等消费记录 `:453-490` 与 pending 自相矛盾）。
- **告警出口**：复用 T-20 双通道 —— `print(f"[conductor] {detail}", file=sys.stderr)` + `st.timeline.append("config", detail=...)`，会话级去重照 `_ROADMAP_ALARM_SEEN`（`conductor.py:2594`）与 `_emit_roadmap_failure`（`:2603-2621`）的 `(file, kind)` 键；detail 必须含"gate id + before/after sha + rule_id + reason_code + 修法（`/autopilot gates` 复核、必要时人工重开）"。**不新造事件名**（新名要跨语言 `EVENT_TYPES` parity，`status-model.ts` `EVENT_TYPES`）。
- **可选加固（需 PM 决策）**：`live` 模式下前 N tick 拒绝自动应答"启动普查中已存在的 pending gate"（grace 窗），把 R1 从"事后告警"升级为"事前不发生"。风险 = 把重启后本应自动处置的 gate 压回人工，而人工恰好是当前失效的那一环 ⇒ 默认只做告警。

### 8 读放大与成本实测

| 输入 | 每 tick 读法 | 本机实测 | 现状 |
|---|---|---|---|
| `_autopilot/auto-decisions.jsonl` | 全量 `readFileSync`（`pm-orchestrator.ts:1292`；Python `auto_decision_rows:6299-6319`） | `E2Feature` 1,117 B；`FeatureMigrator` 文件不存在（0 B）；JCodingAss 无 `gates/` | 已由 pm poll loop 每 4 s 读一次；monitor 接入后变每 4 s 两次（panel 4 s 见 `monitor.ts:65`） |
| `timeline.jsonl` 尾窗 | `readTimelineTail` 512 KiB / 400 条（`monitor.ts:465-467`） | `E2Feature` 9.87 MB、`FeatureMigrator` 1.69 MB（另有 2 代轮转 10 MB×2） | 已是主项 |
| gates 目录 | 每 gate 一文件（行扫描） | `FeatureMigrator` 22 个（1 pending）、`E2Feature` 26 个（0 pending） | 已在读 |
| roadmap / workers / config / pid | 已在本 tick 内读（`monitor.ts:647-670`、`:419`、`:335` 段） | — | 已在读 |

⇒ C1 的"每 tick 新增 1 个台账读"量级 = 0~1.1 KB（相对 timeline 尾窗 ≤ 512 KiB 约 0.2%）。护栏（必须写进实现）：台账 > 1 MiB 时只读尾部并置 `remindersTruncated=true`；另外台账并非"Python 单写方"——TS 也追加 `phase:"dispatch-alarm"` 行（`pm-orchestrator.ts:526-541`，`seq = 行数+1`），两侧都在独立算 `seq` ⇒ 计数只按 `phase=="remind"` 过滤（现有两侧都这么做），任何依赖 `seq` 唯一/单调的新逻辑都必须先修这个竞争。

### 9 可复用资产与成例

- 启动即写事件：`conductor.py:7242`（`goal-snapshot`）。
- 双通道去重告警：`conductor.py:2594` + `:2603-2660`（`_ROADMAP_ALARM_SEEN` / `_emit_roadmap_failure` / `_emit_roadmap_warnings`）。
- 已解析的行归属谓词：`mw_common.row_belongs_to:2026`（`conductor._row_belongs_to:2985` 只做委托）、TS `workerBelongsToKey`（`monitor.ts:687` 用法）。
- session entry 幂等去重与 watermark 恢复：`pm-orchestrator.ts:1283/:1467-1502`。
- 机读字段带 `source`/`formula` 的 doctor 面：`mw_common.py:2900-2990`（`waited_s` 的 `{value, formula, inputs}` 形状，正好是 `reason`/`reminders` 该照抄的形态）。
- 宽度有界化先例：`console.ts:233-235 cardClamp`。

## 残留与未验证

1. **未跑任何测试**：本文所有断言来自源码逐行阅读 + 文件统计；`autopilot-monitor.test.ts`/`autopilot-console.test.ts` 未执行（只读取证，禁写 repo）。C3 的"改后测试是否变绿/变红"未验证；`monitor.ts:906` 的 `trunc` 兜底在极长 key 下的实际输出未实测。
2. **行号权威性**：PowerShell `Get-Content` 与 `\n` 规范行号在同一文件上偏移 −1~−4（本次实测），本文一律用规范行号；若后续以 `read` 工具（其 offset 语义未与规范行号核对）复核个别行，请以 grep/`findstr /N` 为准。
3. **`reminders` 的 TS 口径未定稿**：Python 按 ledger 行数计（`conductor.py:2515-2520`），TS `readGateReminders` 产出的是行数组（`pm-orchestrator.ts:1309-1321` 过滤 `phase=="remind"` 且 `reminder_n>0`）——按 `gate_id` 分组计数即等价，但"同一 gate 重复 `reminder_n` 的畸形行"如何处理未与 PM 确认（建议沿用 Python 行数口径）。
4. **`gate-queue-unreadable` 的粒度**：目录不可读（`readdir` OSError）与单文件不可读（`readFile` OSError）与"某文件 frontmatter 非法"（Python `GateFormatError`）在现有三面上是三种不同处理（doctor 记录 `error`/`parse_errors`，TS 静默）。本文建议统一为 `queueState`，但"`partial` 时其余行是否照常显示"需要 PM 拍板（安全性：显示部分队列可能掩盖丢失的行）。
5. **`not-due` 与"年龄未知"的折叠**：本文建议把 `anchor is None` 归入 `unresolved-scope` 而非 `not-due`（`:2573` 现把两者写在同一个 `or` 里）；这会使六值枚举在"`created_at` 损坏"时显示 `unresolved-scope`，与"key/stage 不可解析"共用一词 —— AC-003 只定了六个字符串，未定义该折叠，需要 QG 认可。
6. **`gate_reminder_max` 语义变更（AC-004）**：本文的 `cap-reached` 文案按"已达打断上限，仍待处理"设计，但 `gate_reminder_max` 的 schema 闭区间 `[1,2]`（`config.py:134`）与 TS 镜像（`status-model.ts:191`）不改；若 AC-004 只改文案不改区间，则"打断上限"上限恒为 2，与"限频只防刷屏"的表述有张力，未决。
7. **R1 判据的时间基准**：`st.started_at` 是进程启动时刻，而 `decided_at` 由 `_iso_now()`（UTC ISO）产生；跨时区/时钟回拨下的比较未验证（建议统一 epoch 比较并在实现里用 `_iso_ts` 解析）。
8. **`_remind_pending_gates` docstring 的自我声明**：`:2685-2686` 称"A corrupt gate queue is skipped here; `tick`'s own goal check records the accompanying config event"，本次核实为**部分成立**：`tick` 路径确实会在 `:2909` 记一条 `config`（因为 `open_goal_change_gate` 会再抛），但该记录**每 tick 一条、无去重**，且 `_remind_pending_gates` 自身在 `:2693-2694` 是零记录的（若未来 `open_goal_change_gate` 被挪走/重构，这条痕迹会消失）。未验证该 `config` 事件在下游（`/autopilot timeline`、panel）是否真的可见（`config` 在 `EVENT_TYPES` 内，`status-model.ts`）。
9. **`GateView` 方案 A 的 schema 版本策略未决**：新增可选字段是否算 breaking（是否需要 `autopilot-status/2`）未与 PM 确认；本文按"可选字段 = 非 breaking"处理，但全仓只有 3 处引用该字符串，证据不足以代表外部消费方。
10. **未测 C6 三条判据的假阳性面**：`consumed_at` 存在 + `status=pending` 是否可能由合法路径产生（例如人工把 gate 改回 pending 继续讨论）——RCoding/RQ-2 的 `pending-review` 前延后门路径（`conductor.py:3701/3667`）是否会产生该形状未验证；若会，R3 需降级为"提示"而非"告警"。
11. **C7 未量化影响面**：把 `blocked_on_human` 改成 per-gate 需要同时改 Python doctor / TS status / TS monitor 三处，本文只给位置，未评估既有 doctor 快照测试与 `mwds-t12-regression` 脚本（`mwds-t12-regression.test.ts:364` 读 `blocked_on_human`）的连带红。
12. **未做的取证**：未读 `packages/multi-workers/test_*` 的 gate/reminder 相关测试以确认 `reason` 文案是否有既有断言锁死；未读 `docs/` 是否已把 `autopilot-status/1` 的 `gates` 字段写成契约（全仓 grep 该字符串仅 3 处，但文档可能用自然语言描述）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-autopilot-gate-alarm-liveness/tasks/T-06-drq2-monitor-state-surface.md`（唯一证据文件指定为本文件）；分派卡 `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t06-drq2-monitor-state/task.md`。
- 本 key 规格：`.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`（§0 状态面优先、AC-001/002/003/004/005/010/012、§5 坑点 3/4/5/6）；项目锚点 `.agenticdoc/goal.md`。
- 同批证据：`evidence/research/design-drq1-field-registration-20261013.md`（三读面清单 C4、冻结 40 名序、`authorizes` 序外注册）；`spec-rq1-reminder-chain-20261013.md`（渲染链、14 条永久静默路径）；`spec-rq4-schema-and-view-surface-20261013.md`（`MonitorGate`/`GateView`/doctor 三读面与 `autopilot-console.test.ts:384-389` 锁死结论）。
- 源码（全文或指定段逐行读）：
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（全文 1075 行）
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（gate 区 630-1040、view 区 1300-1545）
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`（150-260、340-520）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（460-545、1240-1520）
  - `packages/multi-workers/autopilot/conductor.py`（183-260、360-570、2500-2740、2880-2990、5360-5520、6220-6360、6580-6820、6890-7060、7216-7265）
  - `packages/multi-workers/autopilot/gates.py`（73-140、199-280、417-620、740-775）
  - `packages/multi-workers/autopilot/config.py`（40-140）
  - `packages/multi-workers/mw_common.py`（2020-2045、2810-2830、2900-2995、3270-3370）
  - `packages/coding-agent/test/suite/autopilot-console.test.ts`（350-500、1070-1120）、`autopilot-monitor.test.ts`（100-140、250-345、490-520、730-840、1170-1185）
- 本机命令（只读）：`grep`/`findstr /N` 逐符号取行号；`Get-ChildItem`/`Get-Item` 统计 `FeatureMigrator`（gates=22、pending=1、ledger 不存在）与 `E2Feature`（gates=26、pending=0、ledger=1,117 B）；`python -c` 校验 `\n` 规范行号（`monitor.ts` 1075 行 / `conductor.py` 7271 行 / `pm-orchestrator.ts` 1793 行）。
- 未使用任何写 API（除本文件）；未运行 pytest/vitest；未改动任何仓库文件。
