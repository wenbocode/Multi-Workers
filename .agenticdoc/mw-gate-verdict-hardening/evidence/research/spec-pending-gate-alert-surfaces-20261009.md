# Research: pending gate 静默的提醒面与可见面（spec / RQ-2）

> Key: mw-gate-verdict-hardening ｜ 角色: research worker（只读）｜ 快照: 2026-10-09
> HEAD: `10446aefb`（`mw-autopilot-slot-capacity` 已提交；`packages/multi-workers/autopilot/**` 与 `packages/coding-agent/src/extensions/agent-team-loop/**` 上 `git status` 干净，本次工作树唯一脏源码是 `packages/multi-workers/test_common.py`；本文所有 `file:line` 锚已按 `HEAD:10446aefb` 提交内容复核）
> 决策问题: G2「pending 超阈值主动提醒（同一 gate ≤2 次）+ 监视面可见挂了多久 / `BLOCKED_ON_HUMAN`」应挂在哪一层、复用哪条通道、缺口行到底在哪。
> 边界: 只读调研；本文是本轮唯一写面，未改任何代码或其它文件。

## 调研方法与出处

- 只读 read/grep：`packages/multi-workers/autopilot/{conductor,gates,config,effective_config,timeline}.py`、`packages/multi-workers/{mw_common,mw}.py`、`packages/coding-agent/src/extensions/agent-team-loop/{autopilot/{monitor,console,status-model,gate-writer}.ts, pm/{ui-bridge,pm-orchestrator}.ts}`。
- 只读计数：`BLOCKED_ON_HUMAN`、`sendMessage|write_to_pm|pm_inbox`、`remind|nudge` 在 88 个 py + 237 个 ts(src) 文件上的命中数。
- 实测（只读）：`python mw.py autopilot gates --json --project H:\git\E2Feature`、`python mw.py doctor --project H:\git\E2Feature`、E2Feature 21 个 gate 文件的 `created_at`/`answered_at` 差值。
- 只读参考：`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\pm-gate-idle-no-alert.md`。

## 发现

### F1 conductor tick 结构与现有时间驱动挂点（RQ-2.1）

- tick 契约：`conductor.py:2330` `def tick`；每 tick 第一件事是 `st.timeline.append("beat")`（`conductor.py:2336`），随后 `enabled/paused` 早退（`:2338-2341`），再 `orchestrate(project_root, st)`（`:2406`）。`tick` 永不抛（`:2408` 捕获成 config 事件）。
- `orchestrate`（`conductor.py:204`）顺序：自动决策 `auto_decide_gates`（`:218`，def `:6411`）→ 消费已答 gate `_consume_answered_gates`（`:222`，def `:487`）→ … → 每个 running stage 调 `_process_deferred_reviews`（`:308`，def `:2973`）→ `_stage_closure` → per-key dispatch。**这是唯一每 tick 执行的主干**，提醒挂点应落在此。
- 周期：默认 4s，闭区间 1..5s —— `config.py:58` `"poll_interval_sec": 4`（`DEFAULT_CONFIG` 块起 `:55`），`config.py:80` `_INT_RANGES["poll_interval_sec"]=(1,5)`；主循环 `conductor.py:6617 def main`，act-then-sleep，`:6655` 每轮重读 `poll_interval_sec`（改配置即生效）。
- T-08 的 48h `expires_at` 常量与算法：`conductor.py:2838 GATE_DEFAULT_TTL_SEC = 48*3600`、`:2839 REVIEW_DEADLINE_SEC = GATE_DEFAULT_TTL_SEC`、`:2841 GATE_DEFAULT_ACTION = "escalate-to-human"`；判定函数 `_review_deadline`（`:2844`）：`expires_at` 优先（`:2863-2866`，返回 source `"expires_at"`）→ 否则 `created_at + 48h`（`:2867-2872`）→ 两者都缺返回 `(None,"unknown")`（fail-closed，`:2873-2874`）。`review-escalated` 落点 `_review_escalate`（`:2901`），由 `_process_deferred_reviews` 的 deadline 分支（`:2997-3002`）与 closure 分支（`:3004-3012`）触发。
- `_timeline_has_event`（`conductor.py:1817`）签名 `(project_root, ev, key, detail) -> bool`；语义 = 读 `timeline.tail_events(..., limit=200)`（`:1822-1826`）后对 `ev`/`key`/`detail` **全等**匹配。**它是有界尾部去重（布尔），不是计数**；timeline 到 10MB 会轮转且只留 2 代（`timeline.py` 模块文档 + `ROTATE_THRESHOLD_BYTES`/`ROTATE_GENERATIONS`），所以它不能承载「已提醒 N 次」。
- ⇒ G2 的「pending 超 N 分钟」应作为 `_process_deferred_reviews`/`orchestrate` 主干里的一个纯函数判定（读 gate 文件 + now），复用 `_timeline_has_event` 做事件去重；不新增常驻组件（GC-1）。

### F2 「推到 PM 主窗口」的通道（RQ-2.2）

- **conductor 侧没有推送原语**：`packages/multi-workers/autopilot/conductor.py` 上 `sendMessage|write_to_pm|pm_inbox|hook` 命中数 = 1，且该唯一命中是注释（`:5531` "sidecar hooks"）。即 conductor 建门只写文件 + timeline（`gate-created`，`_create_gate` 尾部 `conductor.py:2491-2493`）。
- `trigger_subject` **不是**推送通道，是自动决策规则字段：`AutoRule` 定义 `conductor.py:5128-5137`，六条规则 `:5151/:5165/:5179/:5198/:5213/:5227`；产出只写 gate 文件 + `auto-decisions.jsonl` + timeline（`_record_auto_decision` `:6210`）。
- PM 唤醒通道只在 extension 侧，且已有先例：`ui-bridge.ts:131 export function deliverPmAlert`，内部 `:139 { triggerTurn: true }`（docstring `:125-130` 明确"无 triggerTurn 空闲 PM 不醒"）；`ui-bridge.ts:145 deliverWorkerResult` 复用同一通道。调用点 `deliverPmAlert(` 共 3 处 = 1 处定义 + 2 处调用：`pm-orchestrator.ts:584`（mid/high checkpoint 发散升级）与 `ui-bridge.ts:146`（终态回读）。
- **但 extension 的 poll 循环不读 gate**：`pm-orchestrator.ts:519 startWorkerPollLoop`，循环体只 `workerStore.readAll()`（`:558`），全仓 gate 读取只出现在 `autopilot/{console,monitor,status-model}.ts`（`listGates|gatesDir` 命中：console.ts 57/59/447/476/490、monitor.ts 45/368、status-model.ts 48/922-923/1347 = 0 处在 `pm/`）。
- 现有 gate 可见面全是**人主动敲**：`/autopilot gates`（`console.ts:118`、`cmdGates :446`）、`/autopilot gate`（`console.ts:121`、`cmdGate :455`）、`/autopilot status`（`console.ts:179`）；`autopilot-seen` watermark 只在人跑 status/timeline 时写（`console.ts:75`、`:188`、`:515`）。
- **结论**：G2 若要求"无人提问也收到提醒"，只能在 extension 侧新增一个 gate 消费者（复用 `deliverPmAlert`/`triggerTurn`），conductor 侧只负责产生机器可读事件；若只做 timeline 事件（不加 extension 消费者），则只有人下次跑命令/PM 下次自然醒来时才可见 —— 不能达成 AC-005，须在 design 明确取舍。

### F3 当前 pending gate 可见面与确切缺口（RQ-2.3）

- monitor 面板（`monitor.ts`）：`interface MonitorGate` `:95`，**已带** `createdAt?: string|null` `:105` 与 `ageMs?: number|null` `:107`；`scanPendingGate` `:186` 只收 `status: pending`（`:245`）；collect 处算 age/drift `:373-376`；render 的 gates 段 `:765-798`，头行 `:774` `gates: N pending - `，每条 token 含 ` age=<formatDuration>` `:781`。**⇒ "挂了多久"在 monitor 面板已可见**。
- `/autopilot gates` 13 行卡（`console.ts`）：`renderGateCards :348`；L1 `:394` `created=<iso> waited=<45s|3m|3.9h|15d>`，`formatWaited :241`。**⇒ 卡片已可见**。
- `mw doctor` / `mw autopilot gates --json`（`mw_common.py`）：段 `_doctor_gates :2689`，pending 条目 `_gate_pending_entry :2443`，`waited_s` 计算 `:2450-2452`、节点 `:2503`（`formula: now - created_at`）；`mw autopilot gates --json` = 直接打印该段（`mw.py:3780-3790`）。段字段（实测）：`dir/exists/total/pending_count/schema_versions/parse_errors/pending/missing_fields/drift/replayed/roadmap_validation/crosskey_prose/error`。文本行 `mw_common.py:3097-3113`，`_gates_text_alerted :2764` 只在 I1-I6/I9 命中时才输出。
- **缺口 1（推送面）**：`BLOCKED_ON_HUMAN` 在 88 py + 237 ts(src) 上 **0 命中**；也没有任何 gate 提醒键（`gate-reminder|pending_reminder|gate_reminder` = 0 命中；`remind|nudge` 的命中全是无关项，如 `pm-orchestrator.ts:174 nudgeGoalUnestablished`、`ui-bridge.ts:1940/2019/2067` 的模型 remind）。
- **缺口 2（`/autopilot status`）**：`GateView` 只有 `{id,kind,status}` —— `status-model.ts:1238-1242` 定义、`:1349` 映射（**丢弃 `createdAt`**）；文本渲染 `:1396-1398` 只打 `gates: N total, M pending` + 逐行 `  <id> <kind> <status>`。**这是"看不出挂了多久"的确切行**（monitor/console/doctor 都有 age，唯独 status 面没有）。
- **缺口 3（时间阈值过高 + 文本静默）**：`_doctor_issues :2780` 的 gate 段只在 `waited > 72h` 出 issue（`mw_common.py:2847`）、`waited > 24h` 出 suggestion（`:2849`）；`_gates_text_alerted` 同阈 24h（`:2775`）。⇒ 一个 pending 30min–24h 的门在 `mw doctor` 文本里**一字不出**（I7 零扰动），且 24h/72h 只影响下一次人工 doctor，不产生主动推送。
- **缺口 4（无置顶指示）**：monitor 的 attention 行（`monitor.ts:724-749`）只对 `status=="stalled"` / 有 in-flight / `blockedBy` 的 key 给提示；当 `workers: 0 running` + 1 个新 pending 门时，面板不会把"等人"置顶，需要用户自己把两段拼起来。
- `I1–I9` 的真相：**只是注释级标签，没有同名常量**。相关注释在 `mw_common.py:2400/2405`（I2/I7）、`:2765-2766`（I1-I6、I9）、`:2818`（I1-I6、I7/I8）、`:3097-3098`（I7）。具体 issue 家族在 `_doctor_issues` `:2818-2871`：队列不可读、`parse_errors`、缺 `expires_at/default_action`、`waited>72h`/`>24h`、额外缺字段、drift、replayed、crosskey prose；`roadmap_validation` 走 suggestion（`:2886-2896`）。

### F4 gate 状态与时间的读取面（RQ-2.4）

- 读取 API：`gates.py:682 parse`、`:702 enumerate`（目录扫描即队列）、`:728 pending_gates`（只留 `status == "pending"`）。`Gate` dataclass `:193`，时间字段 `created_at :210`、`answered_at :215`、`expires_at :241`、`default_action :243`。
- 状态/类型闭集：`GATE_STATUSES :74` = pending/approved/rejected；`GATE_KINDS :65-72`（6 种，与 TS `status-model.ts` 镜像 fail-closed 双校验）。
- schema 规模（实测 import）：`FRONTMATTER_FIELDS` = **40**（12 base + 28 optional v2，`gates.py:87-136`）；`_REQUIRED_FIELDS` 冻结 **6** 且 import 期 assert（`:138-145`，`len==6` 实测）。缺可选字段退化为 None/[]，v1 文件照旧 parse（`mw_common.py:2398 _gate_missing_fields` 对 v1 返回 `[]`）。28 个 v2 字段含 `reason_code/evidence_refs/…/expires_at/default_action/out_of_band_actions/gate_schema/consumed_at/consumed_seq`。
- `expires_at`/`default_action` **已有写者**（P-023 grep 证明）：
  - 唯一生成函数 `_gate_default_fields`（`conductor.py:2553`）：`fields = {"default_action": GATE_DEFAULT_ACTION}`（`:2562`）、`fields["expires_at"] = created + 48h`（`:2569`，从文件自己的 `created_at` 推，二者不可能互相矛盾）。
  - 落盘经 `_stamp_gate_defaults`（`:2499`，`:2527` 调 `_rewrite_gate_fields :5967`），**生产调用点恰 2 处**：`_create_gate`（`:2485`，唯一 choke point）与 `tick` 的 goal-change 直建点（`:2380`）。
  - 写入顺序有硬约束：必须在 `snapshot_gate_created`（`:5581`）之前，否则 T-06 replay 绑定（`gate_file.sha256`，`:5635`）破。
  - 读侧：`_review_deadline` 读 `gate.expires_at`（`:2863-2866`）；doctor 把二者列为 pending gate 的通用必填（`mw_common.py:2285 _GATE_UNIVERSAL_DECISION_FIELDS`，检查器 `:2398`）。
  - 回答侧只改 4 字段：`gate-writer.ts:50 ANSWER_FIELDS = ["status","answered_at","answered_by","note"]`（写点 `:121`、`:146`）；消费侧另写 `consumed_at/consumed_seq`（`_rewrite_gate_consumed conductor.py:407`，由 `_mark_gate_consumed :449` 调用）。
  - **关键风险**：只有 conductor 新建的门带这两个字段。E2Feature 实测 `schema_versions={"1":21}`（21 个门全是 v1，`expires_at` 全缺），所以任何"以 `expires_at` 为键"的提醒对历史门**永不触发**。提醒的时间锚必须用 base required 字段 `created_at`。

### F5 配置键模式与阈值应放哪层（RQ-2.5）

- autopilot 键注册在 `autopilot/config.py`：`DEFAULT_CONFIG :55`（实测 **14** 键）、类型校验表 `_BOOL_FIELDS :73`、`_LIST_FIELDS :74`、`_STRING_FIELDS :75`、`_ENUM_FIELDS :76`、`_INT_RANGES :79`；load `:147` / validate `:100` / save `:169`（未知键、错类型、越界一律 `ConfigError`，fail-closed）。键在文件层缺席时不得用 `[]` 读（`config.py:157-166`）。
- `mw_common._DEFAULT_CONFIG`（`mw_common.py:71`）**不是** autopilot 阈值表，它是 `providers.json` 缺失时的 credentials/providers 回退镜像 —— 阈值不应放这里。
- TS 镜像必须同步：`status-model.ts:108 DEFAULT_CONFIG`、`:132 BOOL_FIELDS`、`:135 LIST_FIELDS`、`:138 STR_FIELDS`、`:142 ENUM_FIELDS`、`:147 INT_RANGES`；跨语言冻结夹具 `test/fixtures/autopilot-config-corpus.json`，其 sha/count 被 `test_autopilot_config_parity.py:60-61`（`FROZEN_CORPUS_SHA256` / `FROZEN_CORPUS_COUNT=55`）与 `:310` `test_p4_corpus_integrity` 锁死，TS 侧对应用例 `packages/coding-agent/test/suite/autopilot-config-parity.test.ts`。新增键 = 两侧注册 + 语料加边界用例 + 刻意重冻 sha。
- 分层：`effective_config.EFFECTIVE_KEYS` 只有 `xkey_verify_cmd`/`xkey_verify_cwd`（`effective_config.py:62-65`），机器层（`~/.agents/autopilot-defaults.json`）只能覆盖这两个；`auto_gate_mode` 是"**故意**不被机器层覆盖"的现成先例（`config.py:31-37`、`status-model.ts:100-106`）。⇒ 提醒阈值/次数应放 **project 层 autopilot config**，不入 `EFFECTIVE_KEYS`。
- 同类 int 键参照（可直接照抄形状）：`poll_interval_sec` (1..5, `config.py:80`)、`advance_stall_ticks` (1..50, `config.py:86`)、`round_budget` (>=1, `config.py:82`)、`xkey_verify_timeout_s` (>=1, `config.py:87`)。
- 文档漂移（顺带记录）：`effective_config.py:8/207/212` 写 "13-key view"（`config.py:154` 已按 14 键更新），实测 `DEFAULT_CONFIG` 为 14 键（2019 年新增 `auto_gate_mode` 后未改文案）。

### F6 过密噪音防护先例与"answered 即停"字段（RQ-2.6）

- 事件去重/限次先例（按强度排序）：
  1. **持久 ledger（可承载"次数"）**：`auto-decisions.jsonl` —— 路径 `conductor.py:4943-4947`，单写者 append `_append_auto_decision_row :5729`、读 `auto_decision_rows :5707`；拉出 once-per-gate 语义的判据 `_effective_auto_decision :6033`、`_escalate_recorded :6055`、`_shadow_decision_recorded :6065`、`_defer_recorded :6076`（后三者注释明确"防每 tick 洪泛"）。
  2. **有界尾部去重（只给 1 次语义）**：`_timeline_has_event` `conductor.py:1817`（限 200 条窗口）。
  3. **按对象去重的 detail 编码**：`_review_escalate :2901`，detail 带 `[gate_id]`（`:2916`），去重键 = (key, trigger, gate id)（`:2917`）→ "同门同因只升一次，新门可再升"。
  4. **自造 dedup_key**：`_xkey_escalate :3517`，`dedup_key = f"escalated::{source_key}::{rnd}"`（`:3530`）。
  5. **进程内 Set**：`pm-orchestrator.ts:532 notified`（per taskKey）、`:540 escalated`（per taskKey，风险升级 once-per-task）。
  6. **内存抑制重复事件**：`ConductorState.skipped_claims`（`conductor.py:183`、`:192`，per (key, claim_id)）。
  7. **pull 面零扰动**：`_gates_text_alerted` `mw_common.py:2764`（健康项目文本逐字节不变）。
- ⇒ 要满足 AC-005 的"同一 gate ≤2 次"，仅靠 timeline 去重不够（它只能表达"存在/不存在"）；可选：(a) 把序号编码进 `detail`（如 `gate-0007 pending 45m (reminder 1/2)`）后逐条匹配；(b) 复用 ledger 同族（`auto-decisions.jsonl` 的单写者 append 形状）持久化计数。此选择留给 design。
- **"answered 即停"读 `status`**：`status ∈ {pending, approved, rejected}`（`gates.py:74`）；`pending_gates()`（`:728`）就是 `status == "pending"` 过滤；`_consume_answered_gates` 也在 `gate.status == "pending"` 处提前 `continue`（`conductor.py:487-489`）。不要用 `answered_at` 作为权威位（可为空；`gates.py:202-203` 明确不跨字段强一致）。提醒循环每 tick 从文件重算（零私有状态，D-102），门一答即自然零残留（对齐 AC-006）。

### F7 非 gate 静默 vs 真 pending gate 的机械区分（RQ-2.7）

三轴（全部用现有字段，纯读）：

| 轴 | 字段/函数 | 位置 | "等人"取值 |
|---|---|---|---|
| 有 pending gate | `gates.pending_gates(dir)`；TS `listGates().gates.filter(status=="pending")` | `gates.py:728`；`status-model.ts:922`/`:1396`；`monitor.ts:245` | 非空 |
| 无在飞 worker | `mw_common.parse_workers_file(...)` 中 `status ∉ _TERMINAL_STATUSES` 的行数 | `mw_common.py:1566`、`:162`；TS 侧 `monitor.ts:355-357` 只收 `status==="running"` → `workers[]` 长度 | == 0 |
| conductor 仍在 tick | 最近 `beat` 的 age ≤ `max(30s, 5×poll_interval_sec)` | `BEAT_EV` `status-model.ts:992`；`monitor.ts:599-610`、`:635 tickStale` | `!tickStale` |

- 判据组合 `pending_gates > 0 ∧ running_rows == 0 ∧ !tickStale` = **BLOCKED_ON_HUMAN**（真等人）。
- EXECUTE 期"事件稀疏" = `running_rows > 0`（有在飞 worker，哪怕 timeline 只剩 beat）⇒ 不得提醒（AC-007）。
- 第三态（conductor 死）由 `!tickStale` 单独排除（`monitor.ts:635`；服务侧 `getMwStatus` `monitor.ts:289`）。
- 时间锚 `now - gate.created_at` 全门可用：doctor `waited_s`（`mw_common.py:2450`）、monitor `ageMs`（`monitor.ts:375`）、console `waited`（`console.ts:358/394`）；`created_at` 是 base required 字段（`gates.py:210`、`:93`、`:139`），历史 v1 门也有。
- `goal-change` 门不需要特例：它本身就是 pending gate（`open_goal_change_gate` `conductor.py:195`）；`st.goal_halted`（`:189`）只决定 orchestrate 是否运行，不改变"等人在答门"的事实。

## 结论 → 决策映射

- 支撑 AC-005（主动提醒）：挂点在 `orchestrate` 主干（`conductor.py:204`，与 `_process_deferred_reviews :2973` 同层）；时间锚用 `created_at`（不能用 `expires_at`，F4 证明历史 v1 门全缺）；去重先用 `_timeline_has_event`（F6-2），≤2 次需 detail 序号或 ledger（F6 结论）。
- 支撑 AC-006（answered 即停）：每 tick 由 `pending_gates()`（`gates.py:728`）重算，`status` 是唯一权威位（F6）。
- 支撑 AC-007（只对 pending 生效）：F7 三轴组合，EXECUTE 稀疏因 `running_rows > 0` 天然排除。
- 支撑 AC-008（监视面）：monitor（`monitor.ts:781`）、console（`console.ts:394`）、doctor（`mw_common.py:2503`/`mw_common.py:3108`）已有 age；**待补**的是 `/autopilot status` 的 `GateView`（`status-model.ts:1238-1242`/`:1349`）与全仓缺失的 `BLOCKED_ON_HUMAN` 置顶（F3 缺口 2/4）；doctor 阈值 24h/72h（`:2847`/`:2849`）与 spec 的 30min 不一致，需在 design 决定是否统一。
- 支撑 spec §4 R2（提醒过密）：实测 E2Feature 语料显示 30min 周期无上限会产生 774 次提醒，加"同门 ≤2"后降到 26 次（见 [VERIFY]）。
- 对 PM 推送通道的取舍（spec §4 待确认项）：conductor 无 `sendMessage`（F2），AC-005 的"主动"若要落地，必须在 design 里明确"extension 侧新增 gate 消费者（复用 `deliverPmAlert`/`triggerTurn`）"还是"仅 timeline 事件"；前者才满足"无人提问也收到"。

## 数据缺口

- 无法观测"改后"数字（本 key 尚在 SPEC）。
- E2Feature 现在 `pending_count=0`（21 门全 answered，实测），故所有 pending 时长是**历史 wait 时长**（`answered_at - created_at`），不是实时快照；`gate-0006`/`0009`/`0010`/`0011` 与 reflect 记录的 5.2h / 10.8h 量级一致（见 [VERIFY]）。
- E2Feature timeline 只保留 2 代（10MB×2），`gate-created`/`gate-answered` 事件已被轮转丢弃（grep 三代 JSONL 无 gate-0006..0011 的 created 事件），历史推算只能取自 gate 文件本身。
- 「`I1–I9` 编号→具体条目的完整映射」无权威表（只有散落注释），若要写进 design 需 PM 确认口径。

[VERIFY] RQ-2: blocked_on_human_hits=0(scanned_py=88,ts_src=237) gate_reminder_keys=0 gate_readers_in_pm_loop=0 conductor_pm_push=0 deliverPmAlert_sites=3(def+2calls) tick_default_s=4(range=1..5) expires_ttl_h=48 review_gate_kinds=2 monitor_gate_age=yes(status-model_GateView_age=no) doctor_text_threshold=24h/72h timeline_dedup_window=200 auto_decisions_ledger=present(vs_timeline_bool) default_config_keys=14 frontmatter_fields=40 required_fields=6 E2_gates=21 E2_schema_versions=1:21 E2_pending_now=0 waited>30min=13 waited_30min_to_24h=12 waited>24h=1 waited>72h=1 max_wait_h=293 uncapped_30min_reminders=774 capped2_reminders=26
