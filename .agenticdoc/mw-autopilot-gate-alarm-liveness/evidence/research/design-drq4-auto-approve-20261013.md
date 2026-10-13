# DRQ-4｜阻塞-派发因果链 与「小 gate 自动收证 approve」

- Key: `mw-autopilot-gate-alarm-liveness`｜Phase: DESIGN｜类型: research（只读）
- 卡面: `.agenticdoc/mw-autopilot-gate-alarm-liveness/tasks/T-08-drq4-auto-approve.md`（card_sha256 `900d23acaf5552dcd1c412611d0eb2cc462839f05886fab8c7ad545605fba830`）
- 测量基线: git HEAD `cc9a46a1a`（工作区 dirty，仅 `packages/multi-workers` 与 `.agenticdoc`）
- 唯一证据文件: `.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq4-auto-approve-20261013.md`（本文件）
- 行号口径: 全部在 HEAD `cc9a46a1a` 上实测（`grep -n` 锚符号）。卡面种子给出的行号与本修订相差 0~45 行（例：卡面 `_remind_pending_gates:2688-2735`，实测 `def` 在 `:2683`；卡面 `_apply_stalled_approvals/rejections:3313/:3319`，实测 `def` 在 `:3244/:3313`，`orchestrate` 调用点在 `:265/:268`）。**引用一律以本文件实测行号为准。**

---

## 结论

**一句话**：阻塞→停派发的因果链与"有没有人 watch"无关（派发是纯状态机驱动的），watch 只决定"人能否看见"；56 个存量 gate 里只有 `stage-close` 满足"证据可确定性机器收集 + 非 policy + 判据不放宽"三个条件，是唯一值得自动 approve 的小 gate 种类；而现有自动裁决机器**在生产环境里一次都没跑通过**（全机 `phase:"decide"` 行数 = 0），且 6 条规则中有 5 条的 fact-plane 字段**没有任何生产者**。

### 结论 1｜阻塞-派发因果链（逐跳）

派发由 **conductor（Python，`mw serve` 的第三子进程）** 决定，**launcher 只做队列→进程的搬运**（`launcher.py:1899 while True: _poll_once(...)`，只看 `_workers.parallel` 里 `status == "pending"` 的行；`launcher.py:1763-1796` 无任何 gate 输入）。

逐跳（`packages/multi-workers/autopilot/conductor.py`）：

1. `tick()` `:2880` → 每 tick 先写 `beat`（`:2886`），再 `_remind_pending_gates`（`:2895` 调用；`def :2683`），再 goal-change 闸门（`:2904`），最后 `orchestrate()`（`:2964`）。
2. `open_goal_change_gate()` 为真 → `tick` 在 `:2953` 早退 `"halted-goal-change"` ⇒ **全项目零派发**（`orchestrate` 根本没进）。
3. `orchestrate()` `:204`：`auto_decide_gates` `:218` → `_consume_answered_gates` `:222`（`def :491`）。
4. `_consume_answered_gates` 跳过 `status == "pending"` 的 gate（`:518`）⇒ **未答的 gate 不产生任何状态迁移**。
5. `_stage_activation` `:671`：只要存在 `status == "running"` 的 stage 才 `return True`（`:682-683`），否则做激活工作后 `return False`（`:688`）⇒ **per-key 派发循环（`:317-334`）根本不会被执行**。stage-confirm gate 未答 ⇒ stage 停在 `pending/approved`（rank 0，`_STAGE_STATUS_RANK :561`）⇒ 该 stage 一个 key 都不派发。
6. 有 running stage 时，per-key 循环用 `_DISPATCH_SKIP_STATUSES = ("done","stalled","closed-legacy","pending-review")`（`:70`）在 `:318` 跳过 key ⇒ **key 级 gate（stalled / budget-exhausted / pending-review）直接冻结该 key 的派发**。
7. `_stage_closure` `:853`：`if _gate_open(project_root, "stage-close", stage=stage.number): return`（`:889`）⇒ 未答的 stage-close 让该 stage 永不 `closed`，`_ensure_next_stage_gate`（`:646`）永不执行 ⇒ **后续 stage 永不激活**（又回到第 5 跳）。
8. `_advance_key` `:1166` 的 L2 预算分支：`_budget_bonus` `:1225` / `_budget_gate_rejected` `:1243`（→`mark_stalled`）/ `_gate_open(..., "budget-exhausted", loop=loop)` `:1257` ⇒ 未答的 budget gate 让该 loop 既不继续派 verifier 也不 stall，key 原地停。
9. `mark_stalled` `:5271` 写 key-status=stalled + 建 stalled gate ⇒ 下一 tick 第 6 跳生效。

**"有人 watch"出现的唯一位置是通知面，不是派发面**：`dispatch.dispatch()`（`autopilot/dispatch.py`）与 launcher 都不读任何 watch 状态；watch 只存在于 TS 侧（`pm-orchestrator.ts` 的 `watch.key`）。

### 结论 2｜无人 watch 时静默不发生的动作（AC-014 靶子清单）

逐条给出 `path:line`（TS 路径根 = `packages/coding-agent/src/extensions/agent-team-loop/`）：

| # | 静默不发生的动作 | 判据位置 |
|---|---|---|
| T-1 | **pending-gate 提醒永不送达 PM**（`gate-reminder` 事件被丢弃） | `pm/pm-orchestrator.ts:1489` `if (!watch.key) continue;` |
| T-2 | key 级提醒只发给 watch 该 key 的窗口 | `pm/pm-orchestrator.ts:1490` |
| T-3 | **新窗口把"窗口打开前已存在的提醒行"整体当历史**（水位基线 = 打开时的 ledger 高水位） | `pm/pm-orchestrator.ts:1364-1367`（初始化）、`:1495`（`reminder.seq <= reminderWatermark → continue`）、`:1478-1483`（resume 路径） |
| T-4 | **worker 终态回读 ⇒ PM 永不被唤醒补派下一批** | `pm/pm-orchestrator.ts:1426` `if (!watch.key \|\| ownerKeyOf(...) !== watch.key) continue;` |
| T-5 | 发散风险升级（checkpoint risk=mid/high）不推送 | `pm/pm-orchestrator.ts:1402` |
| T-6 | **自动扫描并派发 key 目录下的新 task.md 不执行**（`inScope` 要求 `owner.name === opts.watchedKey`） | `pm/pm-orchestrator.ts:1054`（`inScope`）、`:1649`（`watchedKey: watch.key`） |
| T-7 | 未注册 key 且尚有未派发工作的越界提示不产生 | `pm/pm-orchestrator.ts:1115` `opts.watchedKey !== undefined && ...` |
| T-8 | **monitor 常驻面板不存在**（无 TUI 或非 session_start 路径） | `autopilot/console.ts:735` `if (!ctx.hasUI) return false;`、`:669`（`/autopilot monitor` 同判据）、`pm/pm-orchestrator.ts:1733`（唯一自动起点） |
| T-9 | **gate 队列不可读被伪装成"0 pending"** | `autopilot/status-model.ts:1003-1013`（`readdirSync` catch → `return { gates: [], errors: [] }`）、`autopilot/monitor.ts:422-434`（`catch { /* gates dir missing — empty queue */ }`）、`conductor.py:2692-2694`（`except gates.GateFormatError: return`，提醒静默跳过） |
| T-10 | **cap 用尽后永久沉默**（计数持久化在 ledger，任何只改事件面的修复无效） | `conductor.py:2562-2563` + `config.py:103/:134`（默认 2、闭区间 `[1,2]`）、TS 镜像 `status-model.ts:152/:191` |
| T-11 | **全项目级在飞抑制**：任意 key 有在飞 worker ⇒ 所有 gate（含该 key 无在飞的）都不提醒 | `conductor.py:2558-2559` |
| T-12 | stage 终止抑制：gate 自带的 stage 或 gate.key 所属 stage 已终态 ⇒ 不提醒 | `conductor.py:2564-2570`（`_STAGE_TERMINAL_RANK :569`） |
| T-13 | **提醒通道无 stderr**：只写 ledger（`:2708`）+ timeline（`:2717`），异常/抑制在 `.mw/conductor.log` 里完全无痕 | `_remind_pending_gates` 函数体 `:2683-2740` 无 `print`；对照 roadmap 告警确有 stderr `:2617`/`:2637` |
| T-14 | **`pending-review` 延后出口在默认配置下不可用**：`defer_key_to_review` 唯一调用者是 `_defer_declined_gate`（`:6882`），而后者的唯一入口是 `auto_decide_gates`（`:7010`）的 `shadow/live` 分支 ⇒ `auto_gate_mode="off"`（真实 4 个项目的现状）时 stalled 只有 approve/reject 两条人工出口 | `conductor.py:3667`（def）、`:6882`、`:7016-7017` |

**现场实例（无人 watch 的完整形状）**：`H:\git\JCodingAss` 的 conductor 仍在 beat（timeline 末三条 `2026-10-13T06:49:42/46/51Z`，seq 613605-613607），但两个 stage-close gate（`gate-0007` 25.45 天 / `gate-0008` 17.09 天）无人应答；`_stage_closure` 每 tick 在 `:889` 直接返回，两个 stage 永远是 `running`，per-key 循环每个 key 都是 `done` ⇒ **每 tick 只写一行 beat，零派发**；`.agenticdoc/_autopilot/auto-decisions.jsonl` **不存在** ⇒ 零提醒记录（`_remind_pending_gates` 写了也无人读；此处连写都没写，因为 `_remind_pending_gates` 只在 `cfg["enabled"] and not paused` 后调用 `:2891-2895`，本项目 config `enabled: true`，但 `pending_gate_reminders` 的 due 判据要求 `created_at + n*30min`，两个 gate 早已满足。**根因已实测**：本项目 serve 启动于 `2026-09-11T07:28:27Z`（`serve.meta.started_at_ms=1789111707393`），比 `gate-reminder` 的生产代码 `ab546bb64`（2026-10-11 18:12 +0800）**早 30 天** ⇒ 运行中的 conductor 里根本没有提醒代码（Python 只在启动时 import），ledger 从未被创建；且 `_workers.parallel` 72 行全部 done/failed、非终态 0 行，排除 killer #1 的抑制解释。当前 timeline 21,035 事件中 `gate-reminder` = 0、`gate-auto-decision` = 0、`beat` = 21,034。（对照组：E2Feature serve 启动于 `2026-10-12T14:06:14Z`，晚于该 feature，真实写下了那 5 条 `remind` 行 —— 见 §2.7。）

> 注：T-1..T-7 是"事件/推送"面的静默；T-8..T-13 是"状态面"的静默。第一性目标 ② 要求的"无 watch 与有 watch 行为等价"**只需要 T-1..T-7 不依赖 `watch.key`**；派发本身（结论 1）本来就不依赖。

### 结论 3｜56 个存量 gate 的 kind 普查与"可自动收证"分级

**普查（实测，4 个项目根全枚举）**：`H:\git\E2Feature` 26 / `H:\git\JCodingAss` 8 / `E:\CLI_workspace\FeatureMigrator` 22 / `H:\git\Multi-Workers` 0（目录不存在）= **56**。

| kind | 个数 | v1/v2 | approved | rejected | pending |
|---|---|---|---|---|---|
| stalled | 31 | 29/2 | 30 | 1 | 1 |
| stage-close | 14 | 12/2 | 12 | 0 | 2 |
| stage-confirm | 10 | 9/1 | 10 | 0 | 0 |
| goal-change | 1 | 1/0 | 1 | 0 | 0 |
| budget-exhausted | 0 | - | - | - | - |
| xkey-authorize | 0 | - | - | - | - |
| **合计** | **56** | **51/5** | **52** | **1** | **3** |

**真实 pending 3 个（全部 v1，零 machine 字段）**：

| gate | kind | stage | key | created_at | 已等 | 判定它需要什么证据 | 可确定性收集？ | destructive | 结论 |
|---|---|---|---|---|---|---|---|---|---|
| JCodingAss `gate-0007` | stage-close | 2 | *(空)* | 2026-09-17T20:04:14Z | 25.45 d | stage 全部 key 终态 + 每 key L3 终局 verdict(l3-verdict.txt) + open_items 空 + dossier 已写 + 无在飞 row + reconciliation 无 dispute | **是**（五件套全齐：见 §2.4，本 gate 今天可过判据） | 不可逆（stage rank 0→2 吸收，`_STAGE_STATUS_RANK :561-569`）；不删数据 | **可自动 approve** |
| JCodingAss `gate-0008` | stage-close | 1 | *(空)* | 2026-09-26T04:37:27Z | 17.09 d | 同上 | **否**（`llm-router` 缺 `l3-verdict.txt` 与 `l3-report.md`，30 天前也无 L3 产物） | 同上 | **回落人工**（状态面须显示 `missing: llm-router l3-verdict/l3-report`） |
| FeatureMigrator `gate-0022` | stalled | *(空)* | `gui-release-hardening` | 2026-10-12T09:54:03Z | 0.87 d | reason_code == 复算 cause_class；used == limit+credits；false_negative_class ≠ undecidable；子类 paperwork = `.mw-achieved-baddraft.json` 存在且 sha256 等于当前 achieved.md 且 failures 含 `NO MATCH: achieved.md missing pattern` | **判据是**（marker 实测存在：`failures[0]` = `NO MATCH: achieved.md missing pattern '系统行为变化' …`）；**动作不是**（见 §3 `splice_achieved` 不存在） | approve=可逆（resume 一轮）；reject=不可逆（closed-legacy） | **只能 auto-classify**（判据确定但确定性动作缺失） |

**其余 kind 的分级（结论性）**：

| kind | 证据面 | 能否确定性收集（判据/命令） | destructive | 结论 |
|---|---|---|---|---|
| **stage-close** | 全 key 终态 + 每 key L3 终局 verdict + open_items 空 + dossier | 是：`_closure_dossier_md :979` 已逐 key 现算 `(final phase, _l3_verdict, l3-report, achieved.md)`；`_done_credentials_present :1853` 已是确定性五件套；命令面 `mw doctor --json` 的 `gates.pending[]`（`mw_common.py:2900+`）+ `python autopilot/roadmap_check.py --project <root>` | 不可逆但不破坏数据 | **可自动 approve**（唯一推荐） |
| stage-confirm | roadmap 结构有效性 + goal sha 绑定 | 是（`proposition_stage_confirm :5539`），但 `roadmap_validation`/`goal_sha256` **无生产者** | 不可逆（stage pending→running，rank 单调） | **只能 auto-classify**（approve = 授权开始花钱派发，不属"文书型完成"） |
| stalled | reason_code/cause_class 复算 + 计数一致性 + false-negative 分类 | 是（`recompute_stall_cause :5913`、`recompute_false_negative_class :5967`） | approve 可逆 / reject 不可逆 | **既有规则可自动 approve，但仅 `proven-false-negative`**（`:5752-5756`）；paperwork 子类需新动作 |
| budget-exhausted | used == limit+credits 且 blocking_gap_count > 0 | 判据可算（`_blocking_gap_count :6028`），但 **gate 创建时未带 counts**（`:1257-1260` 无 `machine_fields`） | approve=+1 轮（近可逆）；reject=key stalled | **需先补生产者**；补齐后可自动 approve |
| goal-change | goal sha before/after + normative 段变化 | 否（`goal_sha256_before/after/goal_diff` 无生产者，`:2904-2925` 只 stamp defaults；"是否 normative"需语义判定） | approve 恢复编排 / reject 永久 halt | **必须人工**（policy） |
| xkey-authorize | red_after==0 且 rc==0 且 test_id 绑定 且 blast_radius ⊆ write_scope | 部分（ticket verify 记录可读，但 `blast_radius`/`write_scope` 无生产者，`:4065-4070`；`_xkey_verify_facts :6050` 不提供这两个字段） | approve=授权跨 key 写（contract-change 范畴） | **必须人工**（policy）；可先补 producer 使其可 auto-classify |

### 结论 4｜复用面：现在能自动决定什么、缺口在哪

**决定性事实（实测）**：全机 4 个项目根下的 `auto-decisions.jsonl` 里 `phase == "decide"` 的行数 = **0**（E2Feature 6 行 = 5 `remind` + 1 `dispatch-alarm`；Multi-Workers 6 行 = 全 `dispatch-alarm`；JCodingAss / FeatureMigrator **文件不存在**）⇒ **自动裁决机器从未在真实项目里做出过一次决定**。

原因（可验证）：6 条规则里只有 `stalled` 的 fact-plane 字段有生产者。

| 复用件 | 位置 | 现在能自动决定什么 | 缺口 |
|---|---|---|---|
| `auto_gate_mode` | `config.py:103/:134`（off\|shadow\|live，默认 off）、TS 镜像 `status-model.ts:152/:191` | `off` = 今天行为；`shadow` 只记 ledger；`live` 才写答案 | ① 项目层 only（不在 `effective_config` EFFECTIVE_KEYS，防机器层静默开启）；② `shadow_gate_allows :6549` 要求 **≥5 夜 + ≥20 条 shadow decision + 该 rule 有 counterexample** 才允许 live ⇒ 新规则首次上线必须 shadow 预热 |
| `auto_decision_for_rule` | `:5831` | 纯逻辑：tautology→escalate；命题假→escalate；`auto_action=="guard"`→`None`；否则 approve（可叠加 `approve_extra`） | **只需接线**：给目标 kind 改 `auto_action` + 保证 facts 可得 |
| `_apply_stalled_approvals` / `_apply_stalled_rejections` | `:3244` / `:3313`（调用 `:265/:268`） | 已实现"gate 被答 ⇒ 状态迁移（stalled→running / closed-legacy）"的**幂等消费**（`_consumed_gate_ids`、`consumed_at` 落盘） | **零改动可复用**：只要自动答案落进 gate 文件（`answer_gate_auto :6589` 已做），下一 tick step F 走同一条人工答案路径 |
| `gate_facts` | `:6065` | 6 个 kind 的 facts 组装 + 所有 IO | 5 个 kind 的字段**无生产者**（见结论 3）；stage-close 的 fact 应从 `_closure_dossier_md`/`_done_credentials_present` 现算而非读 gate 字段 |
| `splice_achieved` | **全仓不存在**（`grep -rn splice_achieved` 仅命中本 key 的 spec/卡/报告，0 处代码） | — | **需新写**。真实对应物是 `closure.overwrite_authorized`（`closure.py:155`）+ `compose_reprompt_prompt`（`closure.py:88`）+ `_done_transaction` 的 achieved 写入路径（`:2306-2360`） |
| 文书型确定性判据（存在） | `.mw-achieved-baddraft.json`：`closure.read_bad_draft_marker :105`、`has_achieved_failure :84`、`overwrite_authorized :155`；失败行前缀 `FAILURE_LINE_PREFIX "   - "`；`advance_phase.py:227` 生成 `NO MATCH: achieved.md missing pattern '<pat>' — <rule>` | **判据已确定性**，可用于 auto-classify | **确定性动作缺失**：现有唯一动作是 reprompt（`:2117` `compose_reprompt_prompt`），预算耗尽即 `mark_stalled(l3-reprompt-exhausted)`（`:2098-2106`）。历史上有 2 例人工做了这件事：FeatureMigrator `gate-0020` 的 note 原文记录"PM 逐字转录本 key 自己的收口证据 §11/§12 … 原文件另存 evidence/runs/achieved-before-pm-closeout-…，未写 PASS" |
| 幂等/消费 | `_effective_auto_decision :6625`、`_consumed_gate_ids :361`、`_shadow_decision_recorded :6657`、`_defer_recorded :6668`、`_mark_gate_consumed :450` | 每 gate 一条有效决定直到被 revoke；gate 字段 `consumed_at` 为持久载体 | 无需新写 |
| 引擎拒绝（回落） | `ENGINE_REASON_CODES :5505-5510`、`gate_evidence_state :6211`、`:6970-6976` | `not-bound` / `shadow-gate-not-met` / `night-quota-exhausted` / `key-quota-exhausted` 全部退化为 `escalate` | 无需新写；缺的是**可见性**（见结论 5） |

### 结论 5｜自动 approve 的安全边界与留痕

- **`answered_by` 取值**：沿用既有 `conductor-auto:<rule_id>`（`conductor.py:6608`）。实测历史 56 个 gate 的 `answered_by` 全部是人工身份（`user-via-pm-window` ×21、`wenbozhou` ×20、`human-via-pi` ×6、`WENBOZHOU-PC4:140664` ×3、`WENBOZHOU-PC4:34196` ×2、`human-pm-window` ×1、空 ×3），**没有一个 `conductor-auto:*`**。
- **依据字段（零新字段可行）**：可行。`answer_source` 与 `auto_policy_id` 是冻结 40 名序内的已注册字段（`gates.py:129-130` 声明、`:257-258` 数据类、`:711-712` 解析），**全仓当前无任何生产者**（只被 parser/TS 读）；gate 卡已渲染 `answer_source`（`console.ts:440-448` `expected: ${g.answerSource ?? sentinel}`）。权威依据另有既有承载：ledger 行 `_AUTO_AUTHORITY_KEYS`（`:6346-6351`：`decision_id/gate_id/gate_kind/mode/executed/decision/rule_id/rule_version/reason_code/decided_by/decided_at/evidence/switch/budget/gate_file_sha256_before|after`），`evidence` 元素携带 `{path, sha256, mtime_ns}`（`:6786-6790`）。
- **幂等性**：三层已有——① `_effective_auto_decision`（每 gate 一条有效 live 决定，revoke 才失效）；② gate 文件 `consumed_at` + `_consumed_gate_ids`（跨重启、抗 timeline 轮转）；③ `answer_gate_auto` 只重写 4 个字段（`_rewrite_gate_fields :6559`），不重排不合成。**残余**：`answer_gate_auto` 不校验 `status == "pending"`，人工可在自动答案之后覆写 `status`（`gate-writer.ts:answerGate` 同样不校验），而已消费的 gate 不会再被 `_apply_stalled_*` 消费 ⇒ 人工覆写一个已自动批准且已消费的 gate 是"看起来生效、实际无效"。
- **审计面（事件名复用）**：直接复用 `gate-auto-decision`（`conductor.py:5448`，Python `timeline.py:90`、TS `status-model.ts:1065` 双侧已注册；`autopilot-event-parity.test.ts` 断言两侧集合相等）+ ledger `phase:"decide"`。**若**要新增一个"收证失败"事件名，必须同批改 `timeline.py:EVENT_TYPES` 与 `status-model.ts:EVENT_TYPES`，否则 parity 测试红。
- **失败回落判据（收集失败 ⇒ 人工 gate，且状态面显示为何回落）**：机制已存在（predicate fail → `escalate` + `reason_code`；engine refusal → `escalate` + `refusal_code`）。**可见性有三处缺口**：① monitor 的 `reason` token `drop: 1`（`monitor.ts:897`）在溢出时**最先被丢**（与 AC-001"原因恒可见"直接冲突，spec §5 坑点 9 已记录）；② `scanPendingGate`（`monitor.ts:222-290`）**不读** `answer_source`/`default_action`/`auto_*`，面板无法表达"为什么回落"；③ TS 的 `GateRecord`（`status-model.ts:964-995`）**不读 `auto_policy_id`**（仅在 `FRONTMATTER_FIELDS :692-693` 名单里），该字段在 TS 侧静默消失。

### 结论 6｜可度量：改动前后的期望变化与运行期验收数字

**改动前基线（实测，53 个已答 gate）**：

| 指标 | 值 |
|---|---|
| 总 gate | 56（E2Feature 26 / JCodingAss 8 / FeatureMigrator 22 / MW 0） |
| 由人应答的 gate | 53/56 = **95%**（另 3 个 pending 全在等人） |
| **自动批准占比** | `phase == "decide" and executed == true` 的行数 = **0** ⇒ **0%** |
| 等待时长 中位 / 均值 / 最大 | **2.56 h** / **20.28 h** / **300.57 h（12.5 天）** |
| ≥30 min | 34/53 = **64%** |
| ≥24 h / ≥48 h | 6 / 4 |
| stage-close（12 已答） | 中位 4.39 h、均值 47.62 h、最大 293.0 h；**+2 个 pending 610.8 h / 410.2 h** |
| stage-confirm（10 已答） | 中位 0.08 h、均值 0.61 h |
| stalled（30 已答） | 中位 3.50 h、均值 16.58 h、最大 300.57 h；+1 个 pending 20.9 h |
| goal-change（1 已答） | 0.12 h |

**改动后的期望变化**：
1. "必须等人工应答"的 **kind 数**：6/6 → 5/6（`stage-close` 得到条件式自动出口；`goal-change`/`xkey-authorize` 仍必须人工；`stage-confirm`/`stalled`/`budget-exhausted` 视接线结果）。
2. 真实 pending 3 个：**1 个可自动 approve**（JCodingAss `gate-0007`）、**2 个回落人工并显示缺失项**（`gate-0008` 缺 `llm-router` 的 l3-verdict/l3-report；FeatureMigrator `gate-0022` 是 paperwork 但确定性动作缺失）。
3. 历史快照（用今天磁盘上的派生物复算 14 个 stage-close）：4 个（E2Feature `gate-0023`/`gate-0024`、FeatureMigrator `gate-0018`/`gate-0021`）满足严格五件套判据 ⇒ 若历史重放，**最多约 4/12 = 33% 的 stage-close 可自动**（其余缺 `l3-verdict.txt`/`l3-report.md` ⇒ 正确回落）。

**运行期可观测的验收数字（全部可从磁盘复算，零新增埋点）**：
- 自动批准占比 = `auto-decisions.jsonl` 中 `phase=="decide" && executed==true` 的行数 ÷ 该窗口内新增的已答 gate 数（分子从 0 起，首次 ≠0 即"跑通一次"）。
- 回落原因分布 = `gate-auto-decision` 事件的 `reason_code`/`refusal_code` 直方图（`engine` 拒绝码本就在 `ENGINE_REASON_CODES :5505`）。
- 等待时长 = `mw doctor --json` 的 `gates.pending[].waited_s`（`mw_common.py:2900+`，`formula: now - created_at`）逐 gate 统计中位/最大；"必须等人响应"的 gate 数 = `gates.pending_count` 减去"已被自动处理"的 gate 数。
- 提醒面 = `phase:"remind"` 行的 `gate_id` 去重数 应等于 pending 数（今天的现实是 5 行 remind 覆盖 3 个 gate，而 pending 3 个 gate 覆盖 0 行 —— 提醒与 pending 完全脱节）。

---

## 证据

### §2.1 56 个 gate 的完整等待时间与应答者（逐 gate 实测）

以 `autopilot.gates.enumerate()` 解析 4 个根，`answered_at - created_at` / `now - created_at`：

```
root             gate       kind            st       schema  wait_h    answered_by
E2Feature        gate-0001  stage-confirm   approved s1        0.2    wenbozhou
E2Feature        gate-0002  stalled         approved s1        2.3    human-pm-window
E2Feature        gate-0003  stage-close     approved s1        6.0    wenbozhou
E2Feature        gate-0004  stage-confirm   approved s1        0.0    wenbozhou
E2Feature        gate-0005  stalled         approved s1        0.3    wenbozhou
E2Feature        gate-0006  stalled         approved s1        5.2    wenbozhou
E2Feature        gate-0007  stage-close     approved s1        0.3    wenbozhou
E2Feature        gate-0008  stage-confirm   approved s1        0.0    wenbozhou
E2Feature        gate-0009  stalled         approved s1       13.9    wenbozhou
E2Feature        gate-0010  stalled         approved s1       12.1    wenbozhou
E2Feature        gate-0011  stalled         approved s1       11.0    wenbozhou
E2Feature        gate-0012  stalled         approved s1        3.3    wenbozhou
E2Feature        gate-0013  stalled         approved s1        2.2    wenbozhou
E2Feature        gate-0014  stalled         approved s1       17.4    wenbozhou
E2Feature        gate-0015  stalled         approved s1       15.6    wenbozhou
E2Feature        gate-0016  stalled         approved s1        4.0    wenbozhou
E2Feature        gate-0017  stalled         approved s1        3.4    wenbozhou
E2Feature        gate-0018  stalled         approved s1        0.2    wenbozhou
E2Feature        gate-0019  stage-close     approved s1      293.0    wenbozhou
E2Feature        gate-0020  stage-close     approved s1        0.0    wenbozhou
E2Feature        gate-0021  stage-confirm   approved s1        0.2    wenbozhou
E2Feature        gate-0022  stalled         approved s2        4.0    WENBOZHOU-PC4:34196
E2Feature        gate-0023  stage-close     approved s2       38.0    WENBOZHOU-PC4:34196
E2Feature        gate-0024  stage-close     approved s2       14.0    WENBOZHOU-PC4:140664
E2Feature        gate-0025  stage-confirm   approved s2        2.6    WENBOZHOU-PC4:140664
E2Feature        gate-0026  stalled         rejected s2        1.0    WENBOZHOU-PC4:140664
JCodingAss       gate-0001  stage-confirm   approved s1        2.8    human-via-pi
JCodingAss       gate-0002  goal-change     approved s1        0.1    human-via-pi
JCodingAss       gate-0003  stalled         approved s1        0.2    human-via-pi
JCodingAss       gate-0004  stalled         approved s1        0.1    human-via-pi
JCodingAss       gate-0005  stage-close     approved s1      136.3    human-via-pi
JCodingAss       gate-0006  stage-confirm   approved s1        0.1    human-via-pi
JCodingAss       gate-0007  stage-close     pending  s1      610.8    (none)
JCodingAss       gate-0008  stage-close     pending  s1      410.2    (none)
FeatureMigrator  gate-0001  stage-confirm   approved s1        0.1    user-via-pm-window
FeatureMigrator  gate-0002  stalled         approved s1        4.3    user-via-pm-window
FeatureMigrator  gate-0003  stalled         approved s1        3.6    user-via-pm-window
FeatureMigrator  gate-0004  stalled         approved s1        1.4    user-via-pm-window
FeatureMigrator  gate-0005  stalled         approved s1        1.3    user-via-pm-window
FeatureMigrator  gate-0006  stalled         approved s1       15.2    user-via-pm-window
FeatureMigrator  gate-0007  stalled         approved s1        2.6    user-via-pm-window
FeatureMigrator  gate-0008  stage-close     approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0009  stage-confirm   approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0010  stalled         approved s1       15.2    user-via-pm-window
FeatureMigrator  gate-0011  stalled         approved s1        0.8    user-via-pm-window
FeatureMigrator  gate-0012  stalled         approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0013  stalled         approved s1      300.6    user-via-pm-window
FeatureMigrator  gate-0014  stage-close     approved s1       78.4    user-via-pm-window
FeatureMigrator  gate-0015  stage-close     approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0016  stalled         approved s1       19.0    user-via-pm-window
FeatureMigrator  gate-0017  stalled         approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0018  stage-close     approved s1        2.8    user-via-pm-window
FeatureMigrator  gate-0019  stage-confirm   approved s1        0.0    user-via-pm-window
FeatureMigrator  gate-0020  stalled         approved s1       37.1    user-via-pm-window
FeatureMigrator  gate-0021  stage-close     approved s1        2.6    user-via-pm-window
FeatureMigrator  gate-0022  stalled         pending  s1       20.9    (none)
```

### §2.2 自动裁决账本（`auto-decisions.jsonl`）全量

```
E2Feature        6 行: phase = remind ×5, dispatch-alarm ×1
   {"seq":1,"phase":"remind","gate_id":"gate-0024","gate_kind":"stage-close","gate_key":"","reminder_n":1,"detail":"pending 683m >= 30m","reminded_at":"2026-10-12T14:11:15Z"}
   {"seq":2,"phase":"remind","gate_id":"gate-0024","gate_kind":"stage-close","gate_key":"","reminder_n":2,"detail":"pending 683m >= 60m","reminded_at":"2026-10-12T14:11:19Z"}
   {"seq":3,"phase":"dispatch-alarm","kind":"out-of-scope","count":35, ...}
   {"seq":4,"phase":"remind","gate_id":"gate-0025","gate_kind":"stage-confirm","gate_key":"","reminder_n":1,"detail":"pending 30m >= 30m"}
   {"seq":5,"phase":"remind","gate_id":"gate-0025","gate_kind":"stage-confirm","gate_key":"","reminder_n":2,"detail":"pending 60m >= 60m"}
   {"seq":6,"phase":"remind","gate_id":"gate-0026","gate_kind":"stalled","gate_key":"feature-api-contract-v2","reminder_n":1,"detail":"pending 47m >= 30m"}
Multi-Workers    6 行: phase = dispatch-alarm ×6
JCodingAss       LEDGER MISSING
FeatureMigrator  LEDGER MISSING
⇒ phase == "decide" 的全机总数 = 0
```

两条可读出的结论：① 提醒数字 n=1/n=2 相隔 4 秒（`gate-0024`：`14:11:15Z` → `14:11:19Z`）——cap 在一个 tick 内吃完，之后永久沉默（chicken 到 `14:11` 已是 pending 683 min，即 11.4 h 才第一次提醒，且两次只差 4 s）；② 3 个被提醒的 gate 的 `gate_key` 分别是 `""`、`""`、`feature-api-contract-v2`，而 TS 消费面在 `!watch.key` 时对**全部**这三行都 `continue`（`pm-orchestrator.ts:1489`）。

### §2.3 生产环境 fact-plane 生产者缺口（逐 kind 实测）

| kind | 创建点 | 是否传 `machine_fields` | `gate_facts` 读的字段 | 生产实况 |
|---|---|---|---|---|
| stalled | `mark_stalled :5271`（`_create_gate` 调用 `:5330` 邻域） | **是**（`reason_code/loop/used_rounds/round_limit/credits_used`，`:5309-5316`） | reason_code/cause_class/used/limit/credits/false_negative_class（`:6081-6088`） | **唯一可达** |
| budget-exhausted | `:1257-1260` | **否**（只有 `key`/`refs`） | used/limit/credits/blocking_gap_count（`:6092-6097`） | 全 None ⇒ `budget-count-drift` ⇒ escalate |
| stage-confirm | `:721-729` / `:663-668` | **否** | roadmap_validation/goal_sha256（`:6071-6075`） | 全 None ⇒ `stage-confirm-structural`/`goal-confirm-goal-drift` ⇒ escalate |
| stage-close | `:889-907` | **否** | verdicts_final/open_items（`:6077-6081`） | 全 None ⇒ `stage-close-verdict` ⇒ escalate。实测 E2Feature `gate-0024`（v2）frontmatter 只有 `default_action`/`expires_at`，无 verdicts/open_items |
| goal-change | `tick :2904-2925` | **否**（只 `_stamp_gate_defaults`） | goal_sha256_before/after/normative_changed（`:6099-6106`） | 全 None ⇒ `goal-sha-unchanged` ⇒ escalate |
| xkey-authorize | `:4065-4070` | **否** | blast_radius/write_scope + ticket verify（`:6108-6118`） | `blast_radius`/`write_scope` = None（`_xkey_verify_facts :6050` 不提供）⇒ `xkey-blast-radius` ⇒ escalate |

### §2.4 stage-close 的确定性收证面（已存在、可直接复用）

- `_closure_dossier_md :979`：对 stage 每个 key 现算 `final phase`（`state.read_key_states`）、`_l3_verdict :916`（读 `l3-verdict.txt` → `meets|below|none`）、`l3-report.md` 指针、`achieved.md` 指针 ⇒ **dossier 本身就是 stage-close 的证据包**。
- `_done_credentials_present :1853`：五件套 = `l3-verdict.txt==meets` + `l3-report.md` 非空 + `evidence/quality-gate-report-*.md` 存在 + `achieved.md ≥200B` + `pm-state.md` 含 `PASS` ⇒ 现成的确定性判据（`_mark_key_done :3189` 已用它拒绝）。
- `_stage_closure :853` 已有的前置：全 key 终态（`_STAGE_TERMINAL_STATUSES :74`）+ 无在飞 row（`:878-882`）+ `evidence_reconciliation_blocks :7156`（T-07 屏障）。
- 实测复算（今天磁盘状态；**是快照，不是建 gate 时的状态**）：

```
E2Feature        gate-0003 s1 all_creds_ok=False（6 个 key 全缺 l3-verdict/l3-report）
E2Feature        gate-0007 s2 false（3 个 key 缺）
E2Feature        gate-0019 s3 false（2 个 key 缺）
E2Feature        gate-0020 s3 false
E2Feature        gate-0023 s4 all_creds_ok=True
E2Feature        gate-0024 s4 all_creds_ok=True
JCodingAss       gate-0005 s1 false（llm-router 缺 l3-verdict/l3-report）
JCodingAss       gate-0007 s2 all_creds_ok=True      ← pending，可自动 approve
JCodingAss       gate-0008 s1 false（llm-router 缺）  ← pending，必须回落
FeatureMigrator  gate-0008/0014/0015 s1 false（gui-shell-spike、gui-contract-surface 缺 l3-verdict）
FeatureMigrator  gate-0018/0021 s2 all_creds_ok=True
```

派生事实（可复核）：`H:\git\JCodingAss\.agenticdoc\llm-router\` 目录下**没有** `l3-verdict.txt`（目录清单：`achieved.md design.md evidence key-decision.md patterns plan.md pm-state.md spec.md tasks`）；同项目 `plugin-ui/crash-analysis/rag-context/e2e-validation` 四者都有 `l3-verdict.txt` = `meets`。

### §2.5 dispatch 侧不依赖 watch（反证）

- `launcher.py`：`run() :1856` → `while True: _poll_once(...) :1899-1901`；pending 行收集 `:1763-1796`；`_poll_once` 无 gate/watch 入参（`:1711` 签名里只有 `project_dir, config, running_procs, log_handles, pending_queue, max_workers`）。全文 `grep gate` 只命中 **dispatch envelope gate**（`launcher.py:515-...`，任务卡信封校验），与 autopilot 门禁无关。
- `conductor.py`：`dispatch.dispatch(...)` 共 11 处调用（`:785/:1194/:1232/:1268/:1377/:1958/:2008/:2043/:2075/:2115/:2160/:2168/:4358`），无一处读 watch（watch 是 TS 概念）。
- `pm-orchestrator.ts`：`watch.key` 的全部出现点 `:251/:256/:301/:343/:1375/:1378/:1398/:1402/:1411/:1426/:1489/:1490/:1562/:1568/:1649/:1675` —— 全在**展示/通知**路径或 `dispatchNewTasks` 的 scope 判定（`:1054`/`:1115`），无一在 `dispatch_worker` 工具里（工具默认 owner key 回退链见 `ui-bridge.ts` 的 `key` 参数说明："this window's claimed key → active key → `_scratch`"）。

### §2.6 状态面的三处 `blocked_on_human`（项目级轴，需同批改）

| 实现 | 位置 | 判据 |
|---|---|---|
| monitor 面板 | `monitor.ts:442` + 渲染 `:829-833` | `blockedOnHuman(gates.length, nonTerminalRows)` 且 `!a.tickStale` |
| status-model | `status-model.ts:1356` `pendingGates - 0 > 0 && nonTerminalRows === 0` | 文件面两轴 |
| doctor | `mw_common.py:3279-3301`（`_blocked_on_human`），调用 `:3349` | 三轴（外加 `_conductor_tick_fresh :3269`，30 s 新鲜度） |

三处都是**项目级**轴（任意 pending gate 且全项目零在飞 ⇒ true），与 AC-002 的 per-key 抑制语义互相矛盾（spec §5 坑点 8）。

### §2.7 提醒面静默的归因分离：部署漂移 vs 抑制 vs 无人消费（三项目对照）

| 项目 | `serve.meta.started_at_ms` | serve 启动（UTC） | 相对 `ab546bb64`(2026-10-11T10:12Z) | ledger | 当前 timeline `gate-reminder` | 归因 |
|---|---|---|---|---|---|---|
| JCodingAss | 1789111707393 | 2026-09-11T07:28:27Z | **早 30.1 天** | 不存在 | 0 / 21,035 事件（beat 21,034） | **部署漂移**：运行中进程无提醒代码；非终态 row = 0（`_workers.parallel` 72 行全 done/failed）⇒ 排除 killer #1 |
| FeatureMigrator | 1790389843021 | 2026-09-26T02:30:43Z | **早 15.4 天** | 不存在 | 见上游 E7（已量化 16.98 天漂移） | **部署漂移** |
| E2Feature | 1791813974011 | 2026-10-12T14:06:14Z | 晚 1.2 天 | 6 行（5 remind） | 5 条 remind 已写入 ledger 与 timeline | **通道可用但无人消费**：`gate_key` 在 TS 侧被 `!watch.key` 丢弃（`pm-orchestrator.ts:1489`），且 cap=2 在一个 tick 内吃完 |

⇒ 三种静默必须分开修：漂移归 AC-005/DRQ-3；整体抑制归 AC-002；无人 watch 的消费面归 AC-010/AC-014。三者叠加时症状完全相同（什么都没发生），这正是第一性目标 ① 说的问题。

---

## 残留与未验证

- **R-1｜`splice_achieved` 不存在（seed 纠错）**：卡面把它列为"既有文书型确定性钩子"，实测全仓 0 处代码（只在本 key 的 spec/卡/T-05 报告里被引用）。真实对应物是 `closure.overwrite_authorized` + `REPROMPT_INSTRUCTION` + `_done_transaction` 的 achieved 写入。结论 3 因此把 stalled-paperwork 定为"只能 auto-classify"。**若 design 决定要"自动收证 approve"，需要新写一个确定性 splice（或决定用 approve+1 轮），这属于本卡未定的实现选择。**
- **R-2｜历史 stage-close 判据无法回放**：§2.4 的 `all_creds_ok` 是**今天磁盘状态**的快照，不是 gate 创建时的状态；历史阶段的 `l3-verdict.txt`/`l3-report.md` 可能被后续清理或从未生成。因此"33% 可自动"是**上界**，不是历史真值。要得到真值需要 gate 创建时的证据快照（`auto_gate_mode≠off` 才写 sidecar，实测从未开启 ⇒ 无快照可查）。
- **R-3｜JCodingAss / FeatureMigrator 的 serve 版本未核**：本卡只读 gate/ledger/timeline/roadmap 文件，未核这两个项目运行中 serve 进程的代码版本（上游已证 FeatureMigrator 漂移 16.98 天）。"ledger 不存在"因此有两种解释（从未提醒 vs. 旧代码无提醒能力），本文件不裁决；`_remind_pending_gates` 只在 `auto_gate_mode` 之外无开关，故两者对结论 1/2/4 无影响（结论 4 的"0 条 decide"不依赖提醒能力，只依赖规则与账本格式，而账本格式与 `gate-reminder` 同期引入）。
- **R-4｜未跑任何测试**：research 只读，未执行 `pytest`/`vitest`。本文所有"既有测试会锁死"的断言来自读测试源码（`test_autopilot_auto_decision.py:492 test_live_approves_budget_gate_once_shadow_gate_is_met`、`:161 test_stage_confirm_guard_fails_on_goal_drift_and_structural_error`、`:330 test_all_mark_stalled_call_sites_pass_a_reason_code`、`:299 test_reason_code_closed_set_is_closed`；`test_autopilot_gate_reminder.py` 13 个用例；`test_autopilot_gate_schema_v2.py:61-62/:187/:240-241/:273-274` 锁 `answer_source`/`auto_policy_id` 缺省；`autopilot-event-parity.test.ts`、`autopilot-config-parity.test.ts`、`autopilot-status-parity.test.ts`），**未运行验证**。Windows 89 例环境失败基线也未核。
- **R-5｜"automated approve 会不会被 shadow 门槛卡住"只按源码推断**：`shadow_gate_allows :6549` 要求 ≥5 夜 + ≥20 条 shadow decision + 该 rule 有 counterexample（`:6526-6547 shadow_prerequisites`）。真机从未有 shadow 记录 ⇒ 首次开启 `live` 必然先被 `shadow-gate-not-met` 拒绝。**未实测该路径**。
- **R-6｜自动答案与人工答案的竞态只做代码推断**：`answer_gate_auto :6589` 与 `gate-writer.ts:answerGate` 都取 `.mw/gates.lock`，但两者都不校验 `status == "pending"`（后者源码已读，前者见 `:6560-6610`）。"人工覆写已消费的自动答案 ⇒ 看起来生效实际无效"这一残余风险**未构造实测**。
- **R-7｜未枚举本机之外的项目根**：本卡只扫 4 个根（沿用 E9 的枚举）。上游 RQ-4 曾因只扫 `H:\git\*` 少算 22 个 gate；本次按 spec 教训把 `E:\CLI_workspace\FeatureMigrator` 纳入，但**不保证没有第 5 个项目根**（例如 `E:\CLI_workspace` 下其他目录）。结论 3 的分布数字以这 4 个根为限。
- **R-8｜`xfail`/漂移类旁证未复现**：spec 记录的 `gate-0024` 被 stage 终止抑制 6.78 h、`fail-open`(roadmap 不可读才发出提醒) 等，本卡未重跑复现（只核了 `:2564-2570` 的判据与 ledger 中 `gate-0024` 的两条 remind 事实与时间差）。

---

## 上下文来源

**卡面与 key 文档**
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/tasks/T-08-drq4-auto-approve.md`（card_sha256 `900d23ac…fba830`）
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`（117 行，本卡引用其 E1-E10 / AC-001..AC-015 / P-01..P-08 / §5 坑点 1-11）
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/pm-state.md`（Phase: DESIGN，baseline `cc9a46a1a`）
- `.agenticdoc/goal.md`（项目级目标锚点：无人值守并行开发）

**同 key 既有证据（交叉引用，未重新验证）**
- `evidence/research/spec-rq1-reminder-chain-20261013.md`（提醒链 14 条永久静默路径 P1-P14）
- `evidence/research/spec-rq2-stalled-state-machine-20261013.md`（stalled 入口/出口）
- `evidence/research/spec-rq4-schema-and-view-surface-20261013.md`（56 gate 普查下界）
- `evidence/research/design-drq1-field-registration-20261013.md`（冻结 40 名序 / `authorizes` 序外注册先例）
- `evidence/research/design-drq2-monitor-state-surface-20261013.md`（monitor 插入点、drop 序、队列不可读静默）
- `evidence/research/design-drq3-drift-selfcheck-20261013.md`（code_digest 判据、新鲜进程侧入口）

**代码（HEAD `cc9a46a1a`，全部完整读取或逐行引用）**
- `packages/multi-workers/autopilot/conductor.py`（7270 行；引用段：`:70`、`:204-334`、`:380-580`、`:644-925`、`:979-1000`、`:1166-1310`、`:1853-1900`、`:2040-2130`、`:2296-2380`、`:2508-2740`、`:2880-2940`、`:3008-3200`、`:3244-3400`、`:3667-3720`、`:4055-4075`、`:5271-5380`、`:5446-5520`、`:5539-5830`、`:5831-6010`、`:6028-6120`、`:6160-6250`、`:6299-6360`、`:6559-6620`、`:6625-6900`、`:6897-7030`、`:7156`）
- `packages/multi-workers/autopilot/gates.py`（全文；`GATE_KINDS :44`、`FRONTMATTER_FIELDS 40 名序 :95-139`、`_JSON_LIST_FIELDS :158-173`、`Gate` 数据类 `:232-268`、`_to_gate` 解析 `:600-730`、`pending_gates :760`）
- `packages/multi-workers/autopilot/closure.py`（全文；`FAILURE_LINE_PREFIX :53`、`has_achieved_failure :84`、`compose_reprompt_prompt :88`、`read_bad_draft_marker :105`、`write_bad_draft_marker :123`、`overwrite_authorized :155`）
- `packages/multi-workers/autopilot/config.py`（`DEFAULT_CONFIG :77-104`、`_ENUM_FIELDS :115-117`、`_INT_RANGES :133-134`）
- `packages/multi-workers/autopilot/timeline.py`（`EVENT_TYPES :67-113`、`ROTATE_THRESHOLD_BYTES/ROTATE_GENERATIONS :115-118`）
- `packages/multi-workers/autopilot/roadmap.py`、`dispatch.py`、`state.py`、`evidence.py`（被引用处）
- `packages/multi-workers/mw_common.py`（`_gate_pending_entry :2900`、`_gate_missing_fields :2855`、`_gate_drift :2872`、`_blocked_on_human :3279`、`_doctor_gates :3320`、`_gates_text_alerted :3380`、`_conductor_tick_fresh :3269`）
- `packages/multi-workers/mw.py`（`serve` 子进程编排 `:140-198/:319-407`、`_git_head_short :5188`、gate 队列 CLI `:5704`、`:3625-3675` gate 卡渲染）
- `packages/multi-workers/launcher.py`（`run :1856`、`_poll_once :~1700-1855`、envelope gate `:515+`）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（1792 行；`startWorkerPollLoop :1325-1520`、`inScope :1054`、`:1115`、`autoStartMonitor` 调用 `:1733`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（1074 行；`scanPendingGate :222`、`readMonitorState :335`、gates 读 `:419-437`、`blockedOnHuman` `:442`、`renderMonitorLines` `:766-910`、`startMonitor :1020`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（1547 行；`DEFAULT_CONFIG :147-165`、`INT_RANGES :185-192`、`GATE_FRONTMATTER_FIELDS :660-701`、`parseGateFile :~900-1000`、`listGates :1003`、`GateView :1333`、`blockedOnHuman :1356`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`（全文 224 行；`ANSWER_FIELDS :63`、`answerGate :163`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`（`cmdGates :448`、`cmdGate :457`、gate 卡渲染 `:~380-445`、`cmdMonitor :663`、`autoStartMonitor :734`）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（`windowClaimId :220`、`registerWorkerTools :2148`、`dispatch_worker` 的 `key` 参数说明 `:~2218`）

**测试（只读，用于判定"既有断言会锁死什么"）**
- `packages/multi-workers/test_autopilot_auto_decision.py`（`:161/:176/:208/:255/:299/:330/:401/:421/:492/:631/:695/:799/:824`）
- `packages/multi-workers/test_autopilot_gate_reminder.py`（13 个用例）
- `packages/multi-workers/test_autopilot_gate_schema_v2.py`（`:61-62/:187/:240-241/:273-274`）
- `packages/multi-workers/test_autopilot_gates.py`（`:224` 40 名序锁）、`test_autopilot_contract_guard.py:187`、`test_autopilot_gate_consumption.py`、`test_autopilot_pending_review.py`、`test_autopilot_stall.py`
- `packages/coding-agent/test/suite/autopilot-event-parity.test.ts`、`autopilot-config-parity.test.ts`、`autopilot-status-parity.test.ts`、`autopilot-console.test.ts:384-389`、`autopilot-monitor.test.ts`

**实测数据源（只读，机器现场）**
- gates 目录：`H:\git\E2Feature\.agenticdoc\_autopilot\gates\`（26）、`H:\git\JCodingAss\.agenticdoc\_autopilot\gates\`（8）、`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\gates\`（22）、`H:\git\Multi-Workers\.agenticdoc\_autopilot\gates\`（不存在）
- `_roadmap.md`：`H:\git\JCodingAss\.agenticdoc\_autopilot\_roadmap.md`（Stage 1 status=running 4 key done；Stage 2 status=running 1 key done）、`E:\CLI_workspace\FeatureMigrator\...`、`H:\git\E2Feature\...`
- `stage-N-close.md`：`H:\git\JCodingAss\.agenticdoc\_autopilot\stages\stage-1-close.md`（1068 B）、`stage-2-close.md`（537 B）
- key 派生物：`H:\git\JCodingAss\.agenticdoc\{plugin-ui,llm-router,crash-analysis,rag-context,e2e-validation}\`、`E:\CLI_workspace\FeatureMigrator\.agenticdoc\gui-release-hardening\{.mw-achieved-baddraft.json,l3-verdict.txt,l3-verdict-provenance.json,achieved.md,pm-state.md,evidence/quality-gate-report-20261012-175403.md}`
- `auto-decisions.jsonl`：E2Feature（1117 B / 6 行）、Multi-Workers（1168 B / 6 行）、JCodingAss（missing）、FeatureMigrator（missing）
- `config.json`：JCodingAss（无 `auto_gate_mode` ⇒ off）、E2Feature（同）、FeatureMigrator（同）
- timeline：`H:\git\JCodingAss\.agenticdoc\_autopilot\timeline.jsonl`（末条 beat seq 613607 @ `2026-10-13T06:49:51+00:00`；`.1` 10 MiB / `.2` 10 MiB 轮转）

**上游（spec 引用，本卡未重读）**
- `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md`
- `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\reflect\stale-serve-silent-stall.md`
- `.agenticdoc/mw-dispatch-card-gate/achieved.md`（同族反模式）

**复核命令（可原样重跑；注意本次环境为 Windows PowerShell + git bash，`>` 会被 worker 写面守卫拦截，故下述命令均无重定向）**
```
python - <<'PYEOF'
import sys, os, collections
sys.path.insert(0, 'H:/git/Multi-Workers/packages/multi-workers')
from autopilot import gates
roots = ['H:/git/E2Feature', 'H:/git/JCodingAss', 'E:/CLI_workspace/FeatureMigrator', 'H:/git/Multi-Workers']
for r in roots:
    d = os.path.join(r, '.agenticdoc', '_autopilot', 'gates')
    gs = gates.enumerate(d) if os.path.isdir(d) else []
    print(r, len(gs), collections.Counter((g.kind, g.status) for g in gs))
PYEOF
```
