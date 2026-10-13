# RQ-2｜`stalled` 状态机的全部出口与可逆性

- Key: `mw-autopilot-gate-alarm-liveness`｜执行卡: `tasks/T-02-rq2-stalled-state-machine.md`（`card_sha256: 8dca631e81409b751f44aeef70e1cd90807d93eb08b4318b61764c6be04149a9`）
- 日期: 2026-10-13｜性质: **只读取证**；唯一写入 = 本文件（代码/config/roadmap/gate 一律未改，其他 key 未写，未 commit）
- 代码基线: `H:/git/Multi-Workers` `cc9a46a1ad1ebb35eb1a5d96d8101c46cd3b78ad`（工作树；下列行号 = 该快照）
- 数据基线: `H:/git/E2Feature`（主）、`E:/CLI_workspace/FeatureMigrator`（FM）、`H:/git/JCodingAss`（JC），全部只读

---

## §0 结论先行（含"回环是否存在"的 yes/no）

1. **回环 yes，但方向是 `closed-legacy → stalled`（不是 stalled → closed-legacy 的回环），且当前没有任何 conductor 内部路径能触发它。** `:3326` 的注释（`conductor.py:3325-3327`）陈述的是**代码级开放性**：`mark_stalled` 的唯一前置守卫是 `key_status == "stalled"` 短路（`conductor.py:5294`），所以 closed-legacy 的 key 一旦再次进入 `mark_stalled` 就会被改回 `stalled`。但 `mark_stalled` 的 14 个调用点**全部**位于 per-key 机器内（`_record_advance_result` / `_advance_key` / `execute_loop` / `_verify_loop` / `_done_transaction`），而该机器只在 `orchestrate` 的派发循环里被调用，入口被 `_DISPATCH_SKIP_STATUSES`（`conductor.py:70`，含 `closed-legacy`）挡住（`conductor.py:318`）。⇒ **可达性来源只有 out-of-band 的 `_roadmap.md` 写者**：人工只手改 key-status（`roadmap.update_key_status` 对 key-status **没有**单调性判据，`roadmap.py:673`），或 roadmap-writer LLM 重写整表（`conductor.py:765-798`、prompt `:799+`）。既有回归测试正是用手改来构造这个回环（`test_autopilot_gate_guards.py:154-167`，改状态在 `:163`）。真实数据里**零实例**（见 §5）。
   - 历史真凶不是这个方向：2026-09-26 的前置研究把可达性归给两条路——(i) D4 的 stage 重放（stage 回退 ⇒ key 重新派发 ⇒ 再次失败 ⇒ `mark_stalled` 写 `stalled`），(ii) 人工改 roadmap。**D4（stage 单调性守卫，`conductor.py:572-619`）已落地**，路径 (i) 关闭（`design-consumption-record-20260926.md:203`、`:253`）。今天只剩路径 (ii)。
   - **真实观测到的回环是 approve 方向**：`stalled → running → stalled`，FM 2026-09-24 事故（6691 `stalled` / 6691 `resume` 事件，归档 `_gates-flood-20260924/` 6684 个 pending stalled 门），已由 `:3268-3279` 的持久消费守卫修掉。E2 也有同形态的小样本（`feature-false-meets-remediation` 3 轮）。

2. **`stalled` 有 2 个入口 + 3 类出口（+1 类越权出口）**：
   - 入口 I-1 = `mark_stalled`（`conductor.py:5271`，14 个触发点，reason_code 闭集 `STALL_REASON_CODES:5453-5468`）；I-2 = `apply_review_decision(..., "escalate")`（`:3601`，映射 `:3382`）——**声明了但没有生产调用者**。
   - 出口 X-1 = approve → `running`（`_apply_stalled_approvals:3244`）；X-2 = reject → `closed-legacy`（`_apply_stalled_rejections:3313`，`:3340` 是**全仓唯一**写 `closed-legacy` 的地方）；X-3 = 延后复核 → `pending-review`（**答门之前**由 `_defer_declined_gate:6826` → `defer_key_to_review:3667` 写入 `:3701`，仅 `auto_gate_mode ∈ {shadow,live}` 且 kind ∈ `DEFERRABLE_GATE_KINDS:3396` 时生效）；X-4 = out-of-band 改 `_roadmap.md`（人工/LLM，无代码判据）。
   - `stalled` 本身**不是终态**：它不在 `_STAGE_TERMINAL_STATUSES`（`:77`），会阻塞 stage 闭环（`_stage_closure:874-876`），并阻塞下游依赖（`_DEP_SATISFIED:63` 不含 `stalled`）。

3. **reject 在状态机内不可逆 = yes；"选错就废掉一个 key" 的措辞不成立（高估）**。精确描述：错 reject ⇒ 该 key 被**状态机内永久关闭**（无任何 in-band 恢复入口；`_DISPATCH_SKIP_STATUSES` 永久跳过；grep `re-attest|reattest` 代码零命中），但**资产全保留**（gate 文件 + consumed 记录 + `.agenticdoc/<key>/` + achieved.md 遗留草稿），恢复路径 = **人工改 `_roadmap.md` 一行**（若 stage 已 closed 再改一行 stage 状态；conductor 自己永不重开 stage，`:618-620`、`_stage_activation:671-683`）。代价：无审计痕迹 + **已耗轮次不退还**（`used_rounds` 从 append-only 派发行推导；`_resume_credits:3222-3243` 只数 **approved** 的 stalled 门，reject 不产生 credit）+ 每次恢复后要**重新 stall 一次再 approve** 才能拿新一轮 + 剩余缺口通常被推给下游 key（E2 `gate-0026` 的 note 正是这么做的）。另有现成的**非破坏性替代**：`pending-review` 的 reject = `rework → running`（`:3637-3638`、`_REVIEW_STATUS_BY_OUTCOME:3379-3383`），永不产生 `closed-legacy`（`design-deferred-review-state-20260926.md:274/:313/:336` 的 VC-D2-11）——但只在 `auto_gate_mode` 打开时才有。
   ⇒ AC-009 应表述为"reject 是**不可逆的状态机终局 + 只能人工越权修复**"，而不是"废掉一个 key"；二次确认的必要性来自"无审计恢复 + 轮次沉没"，不是"资料丢失"。

4. **re-attest 最自然落点 = 新建 gate + 关联原 gate id（B1：放在 `context_refs`，零 schema 成本）**，配套一个**不依赖 `status=="stalled"` 的独立消费者**（照 `_apply_review_decisions:3624` 的成例）。理由：A"重开原 gate"在机制上不可行（见 §6.2：`_consumed_gate_ids` 的 `(id, created_at)` timeline 回退使清 `consumed_at` 无效，`conductor.py:361-409`）；C"给 stalled gate 加第三个 status"blast radius 最大（`gates.py:82` + `status-model.ts:646` + `gate-writer.ts` 的 `decision: "approve"|"reject"` + console + ≥30 处 `.status` 读点）。对 `gates.py` schema 的影响可以是 **0**（`context_refs` 已承担 `loop` / `request_id` 去重维度，`_gate_open:3137-3156`）；若要机器可读的结构化关联，走 `authorizes` 的先例（**冻结 40 名之外**承认一个字段，`gates.py:159-180 / 659-676 / 717`）。台账与 AC 锁协议影响见 §6.4。

---

## §1 `stalled` 状态机全图

```
                        ┌─────────────────────────────────────────────────────────────┐
                        │  I-1 mark_stalled  conductor.py:5271                        │
   running/done/        │      14 触发点（全部在 per-key 机器内，§2）                  │
   pending-review/ ────►│      守卫 = 仅 `!= "stalled"`（:5294）⇒ 不校验前值            │
   closed-legacy        │      写 key-status=stalled（:5297）+ 新建 pending stalled 门  │
                        │      （:5319-5322）+ achieved.md 草稿 + pattern 文件          │
                        └───────────────┬─────────────────────────────────────────────┘
                                        ▼
   (I-2 apply_review_decision("escalate") :3601  ──►  pending-review ─►  stalled)
                                        │
                                    [ stalled ]
                     ┌──────────────────┼──────────────────────┬────────────────────┐
                     │ X-1 approve      │ X-2 reject           │ X-3 延后（答门前）   │ X-4 out-of-band
                     ▼                  ▼                      ▼                    ▼
                 running            closed-legacy          pending-review      （任意值）
               (:3289, +1 credit    (:3340, 终态)          (:3701)             人工改
                per capped loop)         │                     │                _roadmap.md
                     │                   │         ┌───────────┼───────────┐    (:673 无判据)
                     │                   │         │approve    │reject     │escalate
                     │                   │         ▼           ▼           ▼
                     │                   │      running     running     stalled
                     │                   │      (resume)    (rework)    (:3382, 无生产调用者)
                     └───────────────────┴──► 再 stall 时 mark_stalled 新建下一个门
```

关键既成事实（`path:line`）：

| 事实 | 落点 |
|---|---|
| `closed-legacy` 计入依赖饱和（reject 解锁下游） | `conductor.py:63`（`_DEP_SATISFIED`）、`_deps_satisfied` 调用点 `:330` |
| `closed-legacy` / `stalled` / `pending-review` 一律不派发 | `conductor.py:70`、判定 `:318` |
| `closed-legacy` 是 stage 终态；`stalled` / `pending-review` 阻塞闭环 | `conductor.py:77`、`_stage_closure:874-876` |
| key-status 词表（Python） / TS 镜像 | `roadmap.py:79`、`status-model.ts:398`（identity 锁：`autopilot-status-parity.test.ts`） |
| key-status 写入器（唯一） | `roadmap.py:673` `update_key_status`（对 key-status **无**单调性判据；stage 有：`conductor.py:572-619`） |
| gate kind 闭集 / status 闭集 | `gates.py:73`（6 类）/ `gates.py:82`（`pending|approved|rejected`）；TS 镜像 `status-model.ts:638/:646` |
| gate 答案写者只认 approve/reject | `gate-writer.ts:29`（`decision: "approve" \| "reject"`）、`ANSWER_FIELDS:63`、`console.ts:490` |
| gate id 分配 = `max(现存)+1` | `gates.py:371-385`、渲染 `:461`；**跨归档会重用 id**（FM 实例：现存 max=10，归档含 `gate-0004..6687`） |
| 时间线只留 2 代（10MB 轮转） ⇒ 事件是下界证据，gate 文件才是主记录 | `timeline.py:119-120`、`conductor.py:361-409` |

---

## §2 入口清单（谁把 key 置成 `stalled`）

### I-1 `mark_stalled`（`conductor.py:5271`）

| 项 | 值 |
|---|---|
| 前置守卫 | 只短路 `stage.key_status.get(key) == "stalled"`（`:5294-5295`）⇒ **前值可以是 `running` / `done` / `closed-legacy` / `pending-review` 中任意非 `stalled` 值** |
| key 不在 roadmap | 静默 return（`:5289-5291`） |
| 写 | key-status → `stalled`（`:5297`，roadmap 锁内 `:5298-5302`） |
| 副作用 | 新建 **pending** `stalled` gate（`:5319-5322`，id 递增）+ `.agenticdoc/<key>/achieved.md` 遗留草稿（`:5327-5340`）+ `.agenticdoc/patterns/<key>/stall-lesson.md`（`:5342-5360`）+ timeline `stalled` 事件（`:5364`） |
| 幂等性 | 仅靠 key-status；不查 `_gate_open` ⇒ 每次"重新进入非 stalled"后再 stall 都会**新建一个门**（FM 6684 门的成因） |

14 个触发点（全部在 per-key 机器内部）：

| # | `path:line` | 所在函数（定义行） | reason_code | 触发条件 |
|---|---|---|---|---|
| 1 | `conductor.py:1157` | `_record_advance_result:1125` | `advance-class` | 同一 `(key, edge)` 连续失败 `advance_stall_ticks` 次（`:1149-1160`） |
| 2 | `conductor.py:1244` | `_advance_key:1166` | `l2-budget-rejected` | L2 上限命中且 budget 门已被 reject（`:1236-1243`） |
| 3 | `conductor.py:1251` | `_advance_key:1166` | `l2-bonus-exhausted` | 已花 bonus 轮仍超限（`:1249-1250`） |
| 4 | `conductor.py:1276` | `_advance_key:1166` | `l2-dispatch-refused` | L2 verifier 派发失败（`:1271-1276`） |
| 5 | `conductor.py:1363` | `execute_loop:1326` | `exec-exhausted` | 同 loop 尝试数 `>= budget+credits`（`:1360-1363`） |
| 6 | `conductor.py:1383` | `execute_loop:1326` | `exec-dispatch-refused` | exec 派发失败（`:1378-1383`） |
| 7 | `conductor.py:2017` | `_verify_loop:1919` | `l3-no-verdict` | reviewer 未产出判定 |
| 8 | `conductor.py:2035` | `_verify_loop:1919` | `l3-suspect` | 证据来源可疑（provenance） |
| 9 | `conductor.py:2067` | `_verify_loop:1919` | `l3-reprompt-exhausted` | 证据草稿重提示预算耗尽 |
| 10 | `conductor.py:2096` | `_verify_loop:1919` | `l3-below` | L3 轮次预算内仍 below |
| 11 | `conductor.py:2132` | `_verify_loop:1919` | `l3-repair-exhausted` | repair 预算耗尽 |
| 12 | `conductor.py:2149` | `_verify_loop:1919` | `l3-aborted` | stream abort 重掷预算耗尽 |
| 13 | `conductor.py:2265` | `_done_transaction:2225` | `contract-unauthorized` | AC/VC 生效文本被未授权改写（`:2259-2265`） |
| 14 | `conductor.py:2387` | `_done_transaction:2225` | `index-phase-mismatch` | advance 后 phase 列重跑仍失配（`:2380-2387`） |

调用链封闭性（"无 in-band 回环"的判据）：
`orchestrate:303-336` 派发循环 →（`:318` 跳过 `_DISPATCH_SKIP_STATUSES`）→ `_advance_key:1166` → `execute_loop:1186` / `_verify_loop:1188` / `_record_advance_result` → `_done_transaction`（仅由 `_verify_loop:2087` 调用）。全仓 grep：`mark_stalled(` 生产调用点只有这 14 处，无 CLI/其他模块入口。

### I-2 `apply_review_decision(outcome="escalate")`（`conductor.py:3578`，写 `:3601`）

- 映射：`_REVIEW_STATUS_BY_OUTCOME:3379-3383`（`"escalate": "stalled"`），枚举 `REVIEW_OUTCOMES:3377`。
- 前置：调用方需自己保证 key 是 `pending-review`（函数本身不校验）；写失败降级为 `config` 事件（`:3609-3612`）。
- **无生产调用者**：全仓唯一调用点是 `_apply_review_decisions:3654`，outcome 只可能是 `resume`（approve）/`rework`（reject）（`:3651-3653`）；其余出现在测试（`test_autopilot_pending_review.py:454/:461/:463`，其中 `:463` 断言 `closed-legacy` outcome 抛错）。
  ⇒ `pending-review → stalled` 这条边**声明存在、无生产者**（同类还有 `revoke_auto_decision:6366`，也无生产调用者）。

---

## §3 出口清单（stalled 去哪里）

### X-1 approve → `running`（`_apply_stalled_approvals:3244`）

- 守卫：`kind=="stalled" && status=="approved"`（`:3266`）→ `gate.id in consumed` 跳过（`:3268`）→ `status_of[key]=="stalled"`（`:3281`）→ `stage_of` 可解析（`:3283-3285`）。
- 写：`roadmap.update_key_status(..., "running")`（`:3289`）；事件 `gate-answered`（`:3297`）+ `resume`（`:3300`）；`status_of[key]="running"` 同 tick 生效（`:3307`）；`_mark_gate_consumed`（`:3308`）。
- 附带效果：**每次 approve 给每个受上限约束的 loop +1 轮**（`_resume_credits:3222-3243`，从 gate 目录重算、零私有状态 ⇒ 重启不漂移；reject 不给）。
- 同 tick 内 approve 优先于 reject（`orchestrate:265` 先于 `:268`，两者都就地改 `status_of`）。

### X-2 reject → `closed-legacy`（`_apply_stalled_rejections:3313`）

- 守卫：`:3330`（kind/status）、`:3332`（consumed）、`:3335`（key 且 `status_of[key]=="stalled"`）。
- 写：`update_key_status(..., "closed-legacy")`（`:3340`，**全仓唯一 closed-legacy 写入点**；grep `update_key_status(` 命中 `:3208 done / :3289 running / :3340 closed-legacy / :3601 review / :3701 pending-review / :5297 stalled`）。
- 事件：`gate-answered`（`:3347`）+ `stalled` 明细 `"closed-legacy (stalled gate rejected)"`（`:3348`）；删除 bad-draft marker（`:3350`）；`status_of[key]="closed-legacy"`（`:3351`）；`_mark_gate_consumed`（`:3352`）。
- 终局效果：不再派发（`:70`）、解锁下游依赖（`:63`）、使 stage 可闭环（`:77`）；**没有任何反向写者**。

### X-3 答门之前的延后 → `pending-review`（`_defer_declined_gate:6826` → `defer_key_to_review:3667`）

- 触发：自动决策 pass 遇到 **pending** 且 kind ∈ `DEFERRABLE_GATE_KINDS:3396` 的门，且 `_auto_mode_active`（`cfg.auto_gate_mode ∈ {shadow,live}`）；key 有在飞 worker ⇒ 本轮不延后（case 3，`:6864-6870`）。
- 写：key-status → `pending-review`（`:3701`）；再建 review 门（kind 沿用原 kind，`:3720-3723`）。
- `pending-review` 的三个出口（`_apply_review_decisions:3624`）：approve→`resume`→running、reject→`rework`→running（`:3651-3653`，**永不 closed-legacy**，注释 `:3637-3638`）；`escalate`→stalled（无生产者）。
- 48h 期限只发 `review-escalated` 事件、**不改 key 状态**（`_review_escalate:3463-3496`、`_process_deferred_reviews:3540+`）。

### X-4 out-of-band：改 `_roadmap.md`

- 人工只手改 key-status（`roadmap.py:673` 无单调性判据）；stage 状态的合法重开同样"只由人工改 roadmap 授权"（`conductor.py:618-620` 注释、`_stage_activation:671-683` 对 `halted` 的 "pause until a human edits the roadmap"）。
- 代码内部没有任何 key-status 单调性 guard（对比 stage：`_stage_transition_allowed:572-608` + `stage-reopen-refused` 去重留痕 `:583-606`）。这是 §0-1 与 §5 的机制基础。

---

## §4 `:3326` 回环语义核实（逐条判据）

**问题**：`closed-legacy` 能否回到 `stalled`（或反之）？**答**：`→` 有门（X-2），`←` 无门。

1. `stalled → closed-legacy` = 正常出口 X-2，实例见 §5（E2 `gate-0026`），**单向且终局**。
2. `closed-legacy → stalled`：
   - 代码级：`mark_stalled` 只短路 `== "stalled"`（`conductor.py:5294`），**不阻止**前值为 `closed-legacy`；写入 `:5297` 不校验前值。注释 `:3325-3327` 陈述准确。
   - 但**没有 conductor 内部可达路径**：14 个调用点全在 per-key 机器内（§2），机器入口 `conductor.py:318` 用 `_DISPATCH_SKIP_STATUSES`（`:70`）跳过 `closed-legacy`；stage 也必须是 `running`（`:304`）。`_apply_stalled_rejections` 自己把 `status_of[key]` 就地改成 `closed-legacy`（`:3351`），同一 tick 的派发循环看不到它。
   - 可达性来源（全部 out-of-band）：(a) 人工改 key-status；(b) roadmap-writer LLM 重写整表（`conductor.py:765-798`，只在无 running stage 时派发，但写的是**整份** `_roadmap.md`）；(c) 外部写者/多实例竞态（`status_of` 是 tick 起点快照，`mark_stalled` 重读磁盘，`:5288`）。
   - 既有测试用 (a) 构造：`test_autopilot_gate_guards.py:154-167`，`_set_key_status(project,"k1",1,"stalled")` 在 `:163`，随后断言 "replay was refused"（`:166-171`）。测试头注释 `:9-11` 明说可达性来自 "`mark_stalled` only short-circuits `== \"stalled\"`"。
   - 2026-09-26 前置研究的两条可达性路径：(i) **D4 的 stage 重放**（"D4 重放把 stage 重开 ⇒ key 重新派发 ⇒ 再次失败 ⇒ `mark_stalled` 写 `stalled`"，`design-consumption-record-20260926.md:203`），D4 已落地（`:253`、`conductor.py:572-619`）⇒ 关闭；(ii) 人工改 `_roadmap.md`（`:203` 同段）⇒ 仍在。
   - **真实数据 0 实例**（§5）：三个项目全历史里 `closed-legacy` 只出现 1 次，其后无 `stalled`；FM/JC 无 `closed-legacy`。

**结论**：`:3326` 的守卫（`:3332-3333`）是面向"越权写者"的纵深防御，不是面向 conductor 自身状态机的必要修复。它的价值在 (a) 手改 roadmap 后不让一条旧 reject 再次生效，(b) 消费记录丢失/归档后的重放。两者都真实存在（FM id 重用 + 2 代时间线轮转），所以守卫应保留；但 AC-009 不应把它当作"回环在日常运行中会发生"的证据。

---

## §5 reject 是否真的不可逆？"选错就废掉一个 key" 是否成立？

**不可逆性 = yes（状态机内）；"废掉一个 key" = no（高估）。**

in-band（有代码路径）恢复入口清点：

| 候选 | 结论 | 判据 |
|---|---|---|
| approve/reject 重放 | 不可用 | 旧 reject 门已 `consumed_at`（`:3352`）⇒ `_apply_stalled_rejections` 跳过（`:3332`）；即便清字段，timeline `gate-answered` 回退也判其已消费（`:399-405`） |
| 新 `stalled` 门 | 不可用（对 closed-legacy key） | 两个 applier 都要求 `status_of[key]=="stalled"`（`:3281` / `:3335`）；closed-legacy 不派发 ⇒ 不会 stall（`:70`、`:318`） |
| `pending-review` 路线 | 不可用 | `defer_key_to_review:3701` 只在自动决策 pass 对 **pending deferrable 门**调用；closed-legacy key 不会再有 pending 门 |
| `_mark_key_done` | 不可用 | 只由 `_advance_key` 的 `phase=="done"` 分支调用（`:3189`、`:1181-1183`），closed-legacy 被跳过 |
| re-attest | **不存在** | 全仓 grep `re-attest|reattest|re_attest` 生产代码零命中 |
| `blocker_class` | 不存在（与本卡正交，RQ-4 负责） | 全仓 grep 仅命中本 key 的 `.agenticdoc` 文本 |

out-of-band 恢复：**人工改 `_roadmap.md`**（`roadmap.py:673` 接受任意 `KEY_STATUSES` 到任意值，无单调性判据）。
- 成本 1：无审计痕迹（覆盖写，无历史；`design-consumption-record-20260926.md:203` 同结论）。
- 成本 2：**已耗轮次不退还**：L2/EXEC/L3 的 `used` 从 append-only 派发行推导；reject 不产生 credit（`_resume_credits:3222-3243` 只数 approved stalled 门）⇒ 恢复后 key 立即再次触顶，需要"再次 stall + 再 approve"才拿到 1 轮（E2 的 3×/2× 循环实例见 §5 后段）。
- 成本 3：若 stage 已 closed，还需再手改 stage 状态；conductor 自身**永不**重开 stage（`conductor.py:618-620`；T-01 D4 守卫 `:572-619`）。
- 成本 4：reject 已按设计解锁下游（`:63`）并让 stage 可闭环（`:77`）——回退后下游可能已开工/已完成，需要人工判断一致性。

**准确风险描述（供 AC-009 采用）**：
> `rejected` 会使该 key 在状态机内进入不可逆终局（`closed-legacy`）：不再派发、解锁下游、允许 stage 闭环，且无任何 in-band 恢复入口。恢复只能由人工改 `_roadmap.md`（必要时连同 stage 状态）——无审计留痕、不退还已耗轮次、需重新走一次 stall→approve 才得到新一轮，且剩余交付缺口通常要转交下游 key。因此 destructive 动作需要二次确认；但"选错就废掉一个 key"不成立——交付物、证据、achieved.md 草稿与门的判定记录全部保留。

**真实数据（三项目全量只读）**：

| 项目 | stalled 门（现存量） | 答复分布 | `closed-legacy` 实例 |
|---|---|---|---|
| E2Feature `gates/` | 15（`gate-0002/0005/0006/0009..0018/0022/0026`） | **14 approved + 1 rejected** | 1（`feature-api-contract-v2`） |
| FeatureMigrator `gates/` | 14 | **13 approved + 1 pending** | 0 |
| FeatureMigrator `_gates-flood-20260924/` | 6684 | 6684 pending（从未答复） | 0 |
| JCodingAss `gates/` | 2（`gate-0003/0004`，key `plugin-ui`） | **2 approved** | 0 |

⇒ 全部真实答复 30 次 = **29 approve + 1 reject**；`closed-legacy` 出现 1 次；`closed-legacy → stalled` **0 次**。（E2/FM/JC 的 roadmap `key-status` 逐行看过：E2 `_roadmap.md:77` 是唯一 `closed-legacy`；FM 现状含 `gui-release-hardening=stalled`、无 `closed-legacy`；JC 全 `done`。）

单实例细节（E2 `gate-0026`，可复查）：

```
created   2026-10-13T01:25:23+00:00   kind=stalled  key=feature-api-contract-v2
reason_code=l3-below  loop=l3:feature-api-contract-v2  used_rounds=2 round_limit=2 credits_used=0
status=rejected  answered_at=2026-10-13T02:27:14Z  answered_by=WENBOZHOU-PC4:140664
consumed_at=2026-10-13T02:27:16Z  consumed_seq=369860
note: 遗留关闭，作用域修正（VC-515/VC-519 改为按本 key own-diff 归因）交 feature-stage5-closeout 登记
```

timeline 证据链（`H:/git/E2Feature/.agenticdoc/_autopilot/timeline.jsonl`）：`seq 369340` `ev=stalled` → `seq 369860` `gate-answered "gate-0026 rejected → feature-api-contract-v2 closed-legacy"` → `seq 369861` `ev=stalled "closed-legacy (stalled gate rejected)"`；此后该 key 无 `stalled`/`resume`（= 无回环）。提醒侧：`auto-decisions.jsonl` 第 6 行 `gate-0026 phase=remind reminder_n=1 at 2026-10-13T02:13:04Z`（47 分钟后拉到人，约 14 分钟后被答复）。

approve 循环实例（E2）：`feature-false-meets-remediation` 3 次 `stalled` / 3 次 `resume`（`gate-0015`/`0016`/`0018`，2026-09-25~26）、`feature-gui-time-mvp-board` 2 次（`gate-0014`/`0017`）、`feature-phaseb-closeout` 1 次（`gate-0022`，`consumed_at=2026-10-10T07:30:51Z`）。⇒ approve 每次只买该 capped loop 的 1 轮，弹尽后再 stall（与 `_resume_credits` docstring 一致）。
FM 6684 门事故：`_gates-flood-20260924/` 6684 个文件**全部 `kind=stalled` + `status=pending`**；`design-consumption-record-20260926.md:67-72` 记录 FM `gate-answered=6694`、`gate-created=6696`、`stalled=6691`、`resume=6691`——approve 被无限重放（stalled↔running 每 tick 翻转）产生的门洪；修法即今天的 `:3268-3279` + `:3332-3333`。

---

## §6 re-attest 最自然落点

### §6.1 候选与影响面

| 方案 | 语义 | `gates.py` schema | 台账 | AC 锁协议 | 判定 |
|---|---|---|---|---|---|
| **A 重开原 gate**（status→pending、清 `consumed_at/consumed_seq`） | 同一张门重评 | 0（但违反消费记录语义） | 需要"反消费" | 覆盖原判定 ⇒ 与 `[OBSOLETE]` 保留原记录的锁协议同源禁忌 | **不可行**（§6.2） |
| **B 新建 gate + 关联原 id** | 新判定，原判定留痕 | **B1 = 0**（关联放 `context_refs`）；B2 = +1 字段（走 `authorizes` 先例，**不入** 40 名冻结序） | 全新 `gate-created`/`gate-answered`/`consumed_at`；原门字节不变 | 0 | **推荐** |
| **C stalled gate 加第三个 status**（如 `reattest`） | 同一门第三个出口 | `gates.py:82` 闭集 + `status-model.ts:646` + `gate-writer.ts:29` 的 `decision: "approve"\|"reject"` | 同一门第二次状态变更 ⇒ 与 `consumed_at`"答案已应用"语义冲突（`:361-409`） | 判定被原地改写 | **不取** |
| **D 复用 `authorizes` 授权形态**（既有原型） | 用一张新门记录"重新授权" | 0（`authorizes` 已在 schema 内） | 同 B | 0 | **可作 B 的载体** |

### §6.2 为什么 A 不可行（可执行判据）

1. 消费判据 = `gate.consumed_at is not None` **∪** timeline `gate-answered` 回退（`conductor.py:361-409`）。回退用 `(id, created_at)` 复合键：只要 `ts >= created_at` 就判已消费（`:399-405`）。两个 applier 都先查这个集合（`:3268`/`:3332`）。
   ⇒ 清掉 `consumed_at` **不能**解除消费：必须轮转/篡改 timeline（破坏 append-only，D-004 的载体选择理由，`design-consumption-record-20260926.md:12-13`），或改 `created_at`（那是身份锚）。
2. 台账 append-only：`gate-answered` 一旦写入，`_mark_gate_consumed` 的 `consumed_seq`（`:453-489`）已引用它；"撤回并重答"会让同一 `(id, created_at)` 出现两条答案记录——正是 FM 6684 事故的形态。
3. gate id 跨归档重用（`gates.py:371-385`；FM 现存 max=10 而归档含 0004..6687）⇒ 任何"按 id 就地重开"的方案都会把新答案绑到旧身份上。
4. AC 锁协议类比：AC 被取代时用 `AC-0NN [OBSOLETE @ date]` **保留**原条目 + 说明被谁取代（`.agenticdoc/mw-target-partition/spec.md:143-144`、`.agenticdoc/mw-vision-role/spec.md:113`）；门的判定是同一性质的不可覆盖记录。

### §6.3 B 的落点（建议实现面）

1. **关联载体**：
   - B1（零 schema 成本，首选）：新门的 `context_refs` 里写 `reattest-of:gate-0026`。既有先例：`_gate_open:3137-3156` 已把 `loop` / `request_id` 当作 `context_refs` 内的去重维度（子串匹配），并有单测（`test_autopilot_auto_decision.py:556` 附近 "archived gate's sidecar must not bind to a reused id"）。`gates.create` 接受任意非空单行字符串（`_validate_new_gate:357-369`）。
   - B2（结构化，必要时）：新增一个**在冻结 40 名之外**被承认的字段，完全照 `authorizes` 的成例：`gates.py:159-160`（声明集合）、`:503-507`（parse 面成员检查）、`:659-676` + `:717`（校验 + 装填）、`Gate` dataclass；TS 侧若需展示另加读面。**不要**塞进 `FRONTMATTER_FIELDS`：那是冻结 40 名、与 TS 逐项 identity 锁（`gates.py:95`、`status-model.ts:660`、`test_autopilot_gate_presentation.test.ts:211-254`、`test_autopilot_gates.py:224`、`test_autopilot_contract_guard.py:187`）。
2. **key 状态如何离开 closed-legacy**：需要**一个独立消费者**，不能复用 `_apply_stalled_*`（两者都硬要求 `status=="stalled"`，`:3281`/`:3335`）。照 T-08 的成例：`_apply_review_decisions:3624` 就是"另一种 key 状态（pending-review）的独立答案消费者"（注释 `:3633-3638` 明说不复用 stalled 兄弟）。因此 re-attest 消费者应凭 `reattest-of:<id>`（或新字段）识别答案，把 key-status 写回 `stalled`（再由已有 approve 路径给 credit）或直接 `running`，并留 `gate-answered` + 新事件（时间线词表已预准入，"vocabulary first" 先例 `timeline.py:67-104`）。
3. **去重**：用 `_gate_open(kind="stalled", ...)` 或 `reattest-of` 子串判据防重复开门（`_gate_open:3137-3156`）。
4. **与既有原型的呼应**：仓库里已有"证据/事实变更 ⇒ 重新授权 ⇒ 不同消费者读取"的形态——`contract_guard.authorizing_gates:334-347`，注释明说 **"`kind` is not bound (the E2 incident carrier was a `stalled` gate)"**：一张 approved 的 stalled 门带 `authorizes: ["contract-change"]` 就是一次重新授权记录，由 contract 检查（而非 stalled 状态机）消费。另一个原型是 `revoke_auto_decision:6366`（auto 决策的 append-only 撤销，使门可被重新自动判定；当前无生产调用者）。

### §6.4 台账 / AC 锁协议结论（一句话版）

- B：原门文件**字节不变**（`gate-writer.ts:99-131` 只重写 5 个答案字段、其余逐行保留）；新门独立 id / `created_at` / `consumed_at` / `consumed_seq`；AC 编号不复用、原判定不被覆盖 ⇒ **对 AC 锁协议影响 0，对台账纯追加**。
- 注意点：`_resume_credits` 按"该 key 的 approved stalled 门数量"计 credit（`conductor.py:3241-3243`），所以每张新 re-attest 门被 approve 后**天然**成为一次"再给一轮"的记账单位——与既有语义一致，无需新账。

---

## §7 上下文来源清单

**代码（只读，全文件通读 + 定点复核）**

| 面 | 锚点 |
|---|---|
| key 状态词表 / 派生集 | `autopilot/conductor.py:63/:70/:77`；`autopilot/roadmap.py:63/:79/:673` |
| 编排顺序 | `conductor.py:206-336`（stalled 处理 `:265/:268`，review 处理 `:275`，派发循环 `:303-336`，跳过 `:318`） |
| 消费记录 | `conductor.py:361-409`（`_consumed_gate_ids`，回退 `:399-405`）、`:453-489`（`_mark_gate_consumed` + `_rewrite_gate_consumed`） |
| 门消费（stage 级） | `conductor.py:491-556` |
| stage 单调性 | `conductor.py:560-620` |
| stage 激活与重开声明 | `conductor.py:655-700`、`:701-798` |
| stage 闭环 / 终态判据 | `conductor.py:853-876` |
| per-key 机器与 14 个 stall 触发点 | `conductor.py:1125/:1157`、`:1166/:1244/:1251/:1276`、`:1326/:1363/:1383`、`:1919/:2017/:2035/:2067/:2096/:2132/:2149`、`:2225/:2265/:2387` |
| 门创建与去重 | `conductor.py:3008-3136`、`:3137-3156` |
| stalled 状态机核心 | `conductor.py:3222-3243`（credit）、`:3244-3310`（approve）、`:3313-3354`（reject；注释 `:3325-3327`）、`:5271-5364`（`mark_stalled`） |
| T-08 deferred review | `conductor.py:3357-3404`、`:3463-3576`、`:3578-3622`、`:3624-3665`、`:3667-3723` |
| 自动决策 / 延后 producer | `conductor.py:6826-6895`、`:6897-7000` |
| auto 撤销 + 证据对账原型 | `conductor.py:6333-6385`、`:7156-7187` |
| gate schema | `autopilot/gates.py:73/:82/:95/:146/:159/:180/:371/:387/:537/:609-618/:678-721/:724/:744` |
| 时间线词表与轮转 | `autopilot/timeline.py:67-104/:119-120/:422/:472` |
| contract 授权读取 | `autopilot/contract_guard.py:322-354/:384+` |
| TS 答案写入面 | `gate-writer.ts:22-71/:99-131/:169-235`、`console.ts:490` |
| TS 读面镜像 | `status-model.ts:398/:638/:646/:660/:1043` |
| 既有回归测试（可达性判据） | `packages/multi-workers/test_autopilot_gate_guards.py:1-11/:129-171`；`test_autopilot_pending_review.py:441-500`；`test_autopilot_gates.py:203/:224`；`coding-agent/test/suite/autopilot-gate-presentation.test.ts:211-254`；`autopilot-status-parity.test.ts:1-60`；`autopilot-event-parity.test.ts` |

**真实数据（只读）**

- `H:/git/E2Feature/.agenticdoc/_autopilot/`：`gates/gate-0001..0026.md`（逐文件读 frontmatter）、`_roadmap.md`（stage 状态行 `:7/:22/:36/:57/:76`，key-status 行 `:8/:23/:37/:58/:77`）、`timeline.jsonl{,.1,.2}`（290,265 事件；窗口 2026-09-25T10:36→2026-10-13T03:47）、`auto-decisions.jsonl`（6 行）、`config.json`（`auto_gate_mode` 未设置 ⇒ off）、`stages/stage-{1..4}-close.md`、`reflect/*.md`
- `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/`：`gates/`（22 个）、`_gates-flood-20260924/`（6684 个）、`_roadmap.md`
- `H:/git/JCodingAss/.agenticdoc/_autopilot/`：`gates/gate-0001..0008.md`、`_roadmap.md`
- 前置研究（本仓只读）：`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-consumption-record-20260926.md`（FM 数据表 `:63-74`、D2 可达性 `:188-203/:253/:305/:314/:375`）、`design-deferred-review-state-20260926.md`（`:55/:110/:133/:270-274/:313/:336/:357`）、`design-auto-decision-controls-20260926.md`、`spec-auto-gate-boundary-20260926.md:127`、`design-gate-propositions-20260926.md:148/:190/:200`；本 key：`spec.md`（E5/E6、AC-008/009）、`tasks/T-02-rq2-stalled-state-machine.md`、`evidence/research/spec-bootstrap-declaration-20261013.md`
- 上游：`E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/handoff-serve-drift-and-silent-stall-20261013.md`、`handoff-timeline-rotation-gate-replay-20261009.md`

**复现命令**（只读；PowerShell 5 默认 ANSI，中文文件请先 `$env:PYTHONIOENCODING='utf-8'` 再用 python 读）

```powershell
# 1) stalled 门分布（三项目）：逐 gate-*.md 抽 kind/status/key/created_at/answered_at/consumed_at
#    ，按 (kind,status) 计数
# 2) 状态机事件序列（E2）：逐 timeline.jsonl* 抽 ev ∈ {stalled,resume,review-decided} 按 key 排序
# 3) 全仓 grep：blocker_class|re-attest|reattest 生产代码零命中
# 4) 唯一 closed-legacy 写入点：Select-String -Path packages/multi-workers/autopilot/*.py
#    -Pattern 'update_key_status\('   ->  6 处，closed-legacy 仅 :3340
```

---

## §8 未覆盖面声明

1. **时间线只留 2 代**（`timeline.py:119-120`；E2 现存窗口 2026-09-25T10:36 起）⇒ 用 timeline 统计的 stalled/resume 计数是**下界**；本报告的门答复计数以 **gate 文件**为准（gate 文件不轮转）。
2. **未运行任何测试/未改任何代码**（本卡只读）。§4 的"内部不可达"结论 = 全仓静态调用图 + `_DISPATCH_SKIP_STATUSES` 门控 + 既有测试构造方式，三项合证；**没有**新造运行期反证。竞态路径 (c)（tick 起点快照 vs 磁盘重读，`conductor.py:5288`）只做代码级论证，未做并发实验。
3. **FM 6684 事故的原始 key/门对未复原**：`_gates-flood-20260924/` 的 6684 个门只有 `kind/status=pending`，无 `answered_by`；"two approved gates"（`conductor.py:3276`）无法用现存数据指名，本报告只引用前置研究的计数。
4. **未评估 TS 面板对新增 kind/字段的渲染成本**（`monitor.ts:820-860` 的 stalled 渲染、`/autopilot gate` 交互）——属 RQ-4 的 schema/view 兼容矩阵。
5. **`blocker_class` 与 `re-attest` 的同族影响面**（gates 存量字段分布、v1/v2 兼容）由 RQ-4 负责；本卡只确认生产代码零命中。
6. **`pending-review` 的 48h 期限语义**只做到注释/代码级核实，真实数据**零覆盖**：三项目 `auto_gate_mode` 均未开启，`review-decided`/`review-escalated` 事件数为 0；`escalate→stalled` 边同样零覆盖。
7. `mw_common.py:2750` 注释写 "the 12 `mark_stalled` call sites"，与代码的 14 个触发点（`STALL_REASON_CODES:5453-5468` 也是 14）不一致——**文档漂移**，不影响本报告结论，但建议随本 key 的改动一并订正。
