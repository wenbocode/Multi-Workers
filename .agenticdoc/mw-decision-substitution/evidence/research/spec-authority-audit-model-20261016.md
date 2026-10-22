# RQ-3：授权状态机 + 决策档案 schema + review 判据（SPEC 调研证据）

Key: `mw-decision-substitution` · 相位: SPEC · RQ-3 · 日期: 2026-10-16
唯一交付文件: `.agenticdoc/mw-decision-substitution/evidence/research/spec-authority-audit-model-20261016.md`
定位: 为 spec.md §6（留痕与 review）/ §7（度量与授权演进）/ AC-002/005/006/007/008/009 提供可实现的定稿建议。每条结论附 `文件:行号`。

## 0. 前提与已有底座盘点（复用，不另造）

已裁定不再论证（pm-state.md §5 DS-1..DS-4，`.agenticdoc/mw-decision-substitution/pm-state.md:33-40`）：

- 授权三档 `disable`（全关，行为与未配置逐字节等价）/ `enable`（默认，仅 P2 可 binding）/ `advance`（P1+P2 可 binding）；P0 永久人工。
- phase 末自动报告 + key 收尾强制签收（`continue|narrow|revoke` 写回配置）。
- 失败/低置信/超授权面 → 一律上抛人，无默认动作分支（spec.md §3 DS-4）。

可直接复用的底座（全部已存在、已测试）：

| 底座 | 位置 | 复用点 |
| --- | --- | --- |
| 决策客户端 + 证据行 | `packages/multi-workers/decision.py:74`（`EVIDENCE_RELATIVE_PATH`）、`decision.py:121-134`（11 字段 `_EVIDENCE_FIELDS`）、`decision.py:88-99`（8 类 `REASON_CODES`）、`decision.py:940-968`（`_append_evidence` best-effort 追加） | 传输层留痕、失败原因枚举、追加写协议 |
| 决策配置 | `decision.py:73`（`.mw/decide.json`）、`decision.py:231-253`（`DecisionConfig` 默认值，`max_state_bytes=16384` 在 `decision.py:244`）、`decision.py:302-316`（未知键收进 `extras`）、`decision.py:261`（`from_dict` 严格校验） | 配置解析/校验/原子写先例 |
| 配置 CLI 白名单 | `packages/multi-workers/mw.py:672-688`（`_DECIDE_SET_KEYS`）、`mw.py:690`（`_DECIDE_POINT_KEYS` 只认 `enabled/alert_on_disagreement`）、`mw.py:745-764`（未知键 exit 2 拒绝）、`mw.py:772-792`（`_decide_write_config`：锁 + tmp + `os.replace` 原子写） | 签收写回的写入协议 |
| show/doctor 读侧 | `mw.py:845-878`（`_decide_show_payload`，只报 `last_seq/last`，`mw.py:875-876`）、`mw_common.py:1620-1642`（`decide_last_evidence` 只读最后一条非空行）、`mw_common.py:1645-1686`（`_doctor_decide`；`decision.py:73` 缺失时节恰好 `{"exists": false}` 的零扰动规则在 `mw_common.py:1648-1651`） | Q5 读侧合并的现状边界 |
| DP-1 旁路 | `pm/triage-client.ts:47`（`DP1_ID`）、`triage-client.ts:55-58`（问题集：`triage_type ∈ coding/research/review`、`triage_risk ∈ low/mid/high`）、`triage-client.ts:39,44`（20s 超时、16KB state 上限）、`triage-client.ts:132`（`readDecidePolicy`）、`pm/ui-bridge.ts:235-252`（`computeDispatchTriage`）、`pm/ui-bridge.ts:258-275`（`emitDispatchTriage` → ledger） | 决策点接入模板（Q1 的 dp1 升级基线） |
| ledger | `pm/pm-orchestrator.ts:645-664`（`recordDispatchAlarm`：`{seq, phase:"dispatch-alarm", kind, count, detail}` 追加到 `.agenticdoc/_autopilot/auto-decisions.jsonl`，文件名常量在 `pm-orchestrator.ts:572`）、kind 白名单在 `pm-orchestrator.ts:538,542`、`NOTICE_DISPATCH_ALARM_KINDS` 在 `pm-orchestrator.ts:553-564`；Python 侧单写者 `autopilot/conductor.py:7638-7647`（`_append_auto_decision_row`） | Q2/Q5 追加行协议先例 |
| append-only 决策账本（最强先例） | `autopilot/conductor.py:6622-6627`（`auto_decisions_path`）、`conductor.py:8186-8235`（`_build_auto_row`：`decision_id=f"{gate.id}@{decided_at}"` 在 `conductor.py:8205`，含 `executed/decision/reason_code/rule_version/evidence[]/switch/budget/gate_file_sha256_before/after`）、`conductor.py:7683-7703`（`revoke_auto_decision` 追加负行）、`conductor.py:7650-7664`（读侧 `auto_consumption_set = answered − revoked`） | Q2 id 规则、Q5 负行合并模式 |
| 影子→实跑门禁（晋升先例） | `conductor.py:6618-6619`（`SHADOW_MIN_NIGHTS=5`、`SHADOW_MIN_DECISIONS=20`）、`conductor.py:7843-7863`（`shadow_prerequisites`：≥5 夜 AND ≥20 影子决策 AND 每条 rule ≥1 个证伪反例）、`conductor.py:7866-7871`（`shadow_gate_allows` 按 rule 逐条放行 live） | Q1 晋升判据同构 |
| 熔断先例（降级先例） | `conductor.py:7762-7789`（`_auto_breaker_signal`：60s 突发 ≥17、1h ≥100、同签名重复 ≥2）、`conductor.py:7792-7838`（`_trip_auto_breaker` 落盘 brake 文件，`auto_gate_mode` 实质失效直到人工清除）、`conductor.py:7742-7759`（重启后仍生效的持久状态） | Q1 自动降级 + 冷却同构 |
| 结果关联素材 | `shared/run-store.ts:26-56`（`run.json`：`task_key/run_id/kind/status/artifacts/supersedes`；`run_id=<task_key>@<iso>` 生成在 `run-store.ts:106-108`；终态集合在 `run-store.ts:29-34`）、`run-store.ts:113-115`（output.md 首行 `<!-- mw-run: ... -->` 标记）、`run-store.ts:168-172`（task.md 头部行约定 `supersedes:`/`origin:`/`type:`）、`worker/output-writer.ts:28-34`（marker 位置契约）、`worker/output-writer.ts:572-578`（`[FLOW]` trace 行）、`output-writer.ts:666-680`（`[CHECKPOINT] ... risk=`）、`output-writer.ts:738-747`（`[END] exit=...`）、`output-writer.ts:749-754`（`[GOAL_CHECK] phase=N goal_mtime=ms`）、`pm/ui-bridge.ts:2819-2873`（done 需非空 summary 写 `_project_log.md`） | Q3 关联机制 |
| 门禁 | `.agents/skills/agentic-task/core/scripts/advance_phase.py:25`（PHASES）、`advance_phase.py:41-96`（GATES 表）、`advance_phase.py:191-289`（`check_gate` 纯读校验，`content_match` 处理在 `advance_phase.py:220-227`）、`advance_phase.py:292-396`（`update_pm_state`，`- Phase:` 机器行在 `advance_phase.py:345-351`） | Q4 报告时机与签收门禁 |

---

## Q1 授权状态机

### Q1.1 两级模型：项目档位 × 决策点状态

授权不是单值，是两级：

1. **项目档位** `level ∈ {disable, enable, advance}`（DS-1）：只决定**资格上限**——`disable`：无任何决策点被咨询（行为与未配置等价，沿用底座默认关语义 `decision.py:238` `enabled=False` 与 `triage-client.ts:14` 的 complete-bypass 契约）；`enable`：P2 点可 binding；`advance`：P1+P2 可 binding。
2. **点级状态** `points[dp].state ∈ {human, advisory, binding, suspended, revoked}`：决定**实际执行面**。最终执行档 `authority(dp) = min(level 上限, points[dp].state)`，且 `risk=P0` 的点无论两级取什么值恒为 `human`（引擎硬拒，对应 spec AC-002；P0 定义见 spec.md §3 DS-1）。

关键推导（回答"enable 是否等于 P2 全部自动 binding"）：`enable` 档下 P2 点的**初始状态就是 `binding`**（DS-1 的"仅 P2 可 binding"按字面执行，保证"人工轮次降 0"目标可直接兑现），P1 点初始状态恒为 `advisory`；`advance` 只是把 P1 的资格上限打开，P1 从 `advisory` 到 `binding` **必须逐点晋升**（见 Q1.4），不存在"切到 advance 就 P1 全开"的一刀切。

### Q1.2 状态枚举与迁移表

| from | to | 触发条件 | 执行者 | 留痕 |
| --- | --- | --- | --- | --- |
| —（新点注册） | `binding`（P2）/ `advisory`（P1）/ `human`（P0） | 注册表初值；P0 硬编码 | 代码 | authority-change 行 |
| `advisory` | `binding` | 晋升判据满足（Q1.3）且不在冷却期 | 报告器建议 + 签收确认（MVP 先人工确认） | authority-change 行 |
| `binding` | `suspended` | 滑窗指标恶化（Q1.5 触发 1/3）或连续 2 次同类人工 override | 自动 | authority-change 行 + 报告高亮 |
| `suspended` | `advisory` | 冷却期满（Q1.6）且无新恶化 | 定时（报告器惰性判定） | authority-change 行 |
| `binding`/`advisory` | `revoked` | key 收尾签收 `revoke` | 人（签收门禁写回，Q4.4） | authority-change 行（`by: signoff`） |
| `binding` | `advisory` | 签收 `narrow`（或缩窄到子类） | 人 | authority-change 行 |
| `revoked` | `binding`/`advisory` | 仅人工显式重新授权（无自动路径） | 人 | authority-change 行 |
| 任意 | 任意 | P0 点：所有非 `human` 迁移被引擎拒绝 | 代码（`authority()` 解析时硬拒） | 拒绝事件走 ledger（`recordDispatchAlarm`，`pm-orchestrator.ts:645-664`） |

### Q1.3 晋升指标与判据（advisory → binding）

- **主指标：一致率** = 结算行中 `outcome=ok` 且无 `kind=override` 行的比例，分母为已结算且非 `inconclusive` 的决策（字段定义见 Q2/Q3）。
- **反指标：人工推翻率**（override 行占已结算比例）、**回滚率**（`outcome=rollback` 占已结算比例）。
- **小样本防护——不用裸比率，用置信下界**：对一致率 p 取 Wilson 95% 置信下界 `p_lower`，晋升要求 `N ≥ 20 且 p_lower ≥ 0.90（P2）/ ≥ 0.95（P1）`。样本不足时下界自动变低 → 天然"数据不足不晋升"，无需单独的"最少样本"分支。数值终稿归 RQ-5（spec.md §9 RQ-5 行），本节给出的是结构与缺省值。
- **同构先例**：conductor 影子→实跑门禁即"最小样本 + 最小跨度 + 必须见过反例"三件套（`SHADOW_MIN_NIGHTS=5`、`SHADOW_MIN_DECISIONS=20`、每条 rule ≥1 证伪反例，`conductor.py:6618-6619` 与 `conductor.py:7843-7871`）。建议沿用其"必须见过至少 1 个反例仍被收回/纠正后恢复"的稳健性思想：晋升前该点至少经历过 1 次 `advisory` 建议被人推翻的样本（说明系统知道错长什么样）。
- **晋升检查时机**：只在 phase 末报告时评估（Q4），不做逐条实时晋升——天然节流 + 与签收节奏对齐（DS-2）。

### Q1.4 `advance` 档下 P1 逐类授权（回答：是，逐点/逐类，不一刀切）

- `advance` 只解除 P1 的资格上限；每个 P1 点独立从 `advisory` 出发走 Q1.3 判据。理由：P1 决策点失败代价差异大（spec.md §4 表：#4 失败处置、#6 QG 处置、#10 依赖升级、#13 发布时机不可同权），一刀切会让最差的那类决定整个档位的命运。
- "逐类"粒度 = 决策点 id（spec.md §4 的 14 行，一行一个 id），必要时细到 `dp + 子类`（如 dp4 内 `redispatch/model-switch/give-up`），存为 `points` 下的独立键——与 `.mw/decide.json` 已有的 per-point 键结构同构（`points.dp1.enabled`，`triage-client.ts:64-67`、`mw.py:690`）。

### Q1.5 降级触发（自动，不需要人提醒）

沿用 conductor 熔断的"信号 → 持久制动 → 人工清除"三段式（`conductor.py:7762-7838`），但阈值用决策质量而非突发量：

1. 滑动窗口（最近 30 条已结算，按 decision_id 去重后）：`override_rate > 0.15` 或 `rollback_rate > 0.10` → 该点 `suspended`；
2. 连续 ≥3 条 `outcome=rework` 且其间无 `ok` → `suspended`；
3. 同一决策点在 24h 内被人工 override ≥2 次且答案方向一致 → 立即 `suspended`（人已经在教它了）；
4. key 收尾签收 `narrow`/`revoke`（Q4.4）→ `advisory`/`revoked`。

不降级的情况（显式排除，避免误伤）：`outcome=inconclusive`（模型层故障，Q3.3）不进任何比率分母；决策服务不可用走 DS-4 上抛路径，本来就不产生 binding 行为，不触发降级。

### Q1.6 冷却期

- 任何自动降级（→`suspended`）写入 `cooldown_until = now + 7d`；冷却期内 Q1.3 判据即使达标也不晋升。目的：防抖动（flapping）。
- 与先例的差异说明：conductor 的 brake 文件要求人工清除（`conductor.py:7805-7812` `action: escalate-to-human ... until a human clears this file`）；本状态机的 `suspended` 是**点级、可定时恢复**的轻制动，`revoked` 才是需要人工解除的重制动——两级制动分别对应"指标变差"与"人否决"两种严重度。

### Q1.7 状态存哪 + 与 `_DECIDE_SET_KEYS` 白名单的兼容

**结论：独立文件 `.mw/decide-authority.json`，不塞进 `.mw/decide.json`。** 依据：

1. `mw decide set` 只接受 `_DECIDE_SET_KEYS` 白名单键（`mw.py:672-688`），`points.` 子键只认 `enabled/alert_on_disagreement`（`mw.py:690`），其余一律 exit 2 拒绝（`mw.py:763-764`）。要把 `state/cooldown_until/last_review` 塞进去就必须扩白名单，等于改冻结的 D-007 配置面。
2. `DecisionConfig.from_dict` 把未知键收进 `extras`（`decision.py:302-316`）——读侧虽拿得到，但 `from_dict` 对 `extras` 不做任何校验，且每次 `mw decide set` 的重写（`mw.py:914-967`，先 `DecisionConfig.from_dict` 验证再原子替换）会**无感知地保留或依赖**这些键，授权状态与传输配置的生命周期被绑死。
3. 签收写回（DS-2）要求"结论可机器执行地写回授权档"，写路径、锁、审计都应独立于 `mw decide set`（后者面向人手敲 KV）。

建议 schema（v1）：

```json
{
  "version": 1,
  "level": "enable",
  "updated_at": "2026-10-16T12:00:00Z",
  "updated_by": "signoff:continue@mw-decision-substitution | auto:suspend | human",
  "cooldown_until": null,
  "points": {
    "dp2-checkpoint-split": { "risk": "P2", "state": "binding",  "since": "...", "last_review": "..." },
    "dp4-failure-handling": { "risk": "P1", "state": "advisory", "since": "...", "last_review": "..." }
  }
}
```

- 写协议复用 `_decide_write_config` 的锁 + tmp + `os.replace`（`mw.py:772-792`，锁协议 `mw_common.acquire_lock` 在 `mw_common.py:2369-2384`）。
- **不变式**：本文件是"当前生效快照"，**不是审计记录**；每次变更必须同时向决策档案追加一条 `kind=authority-change` 行（Q2），审计不可篡改性由档案承担（Q5）。读取方（binding 引擎、报告器）只信快照 + 档案交叉校验（快照里的 `updated_by` 必须能在档案找到对应 authority-change 行，否则 doctor 报 warning）。
- `disable` 档实现为：`level=disable` 时 binding 引擎短路返回"上抛人"，且不咨询模型（与 `triage-client.ts:14` "complete bypass = zero spawn zero write" 语义一致），保证 AC-001 的逐字节等价可测。

---

## Q2 决策档案 schema（decision record 字段表）

一行一事件，`kind` 区分四种行：`decide`（决策发生）/ `override`（人推翻）/ `settle`（结果结算）/ `authority-change`（授权变更）。读侧按 `decision_id` 合并（Q5.2）。文件建议 `.agenticdoc/_autopilot/decisions.jsonl`（与 `auto-decisions.jsonl`、`triage-decisions.jsonl` 并列，均在 `decision.py:74`、`pm-orchestrator.ts:572`、`conductor.py:6622-6627` 所确立的目录约定下）。

### Q2.1 字段表

| 字段 | 类型 | 来源 | 可缺 | 说明 |
| --- | --- | --- | --- | --- |
| `seq` | int | 写侧读行数+1 | 否 | 先例：`pm-orchestrator.ts:648-657`、`conductor.py:7644`；非严格并发安全，靠单一写者 + 文件锁约定 |
| `prev_sha` | str16 | 上一行规范化 JSON 的 sha256 前 16 hex | 否（首行 `"0"*16`） | 哈希链，Q5.1 |
| `kind` | enum | 写侧 | 否 | `decide/override/settle/authority-change` |
| `decision_id` | str | 规则见 Q2.2 | 否 | 全档案主键（组内多行） |
| `ts` | str ISO-UTC | 时钟 | 否 | 先例 `decision.py:946`（`isoformat(timespec="seconds")`） |
| `dp` | str | 决策点注册表（spec.md §4） | 否 | 如 `dp1-dispatch-type`；沿用 `dp` 字段名（`decision.py:122`、`mw.py:872`） |
| `key` | str | owner key | 否 | 空串=项目级/PM 本地 |
| `task_key` | str | worker 任务 | 是（PM 本地决策为 null） | 与 `run.json.task_key` 同名同义（`run-store.ts:38`），可直连 |
| `phase` | str | pm-state Phase | 是 | 取 `advance_phase.py:25` PHASES 枚举值 |
| `state_digest` | str16 | `sha256(_encode_state(state))[:16]` | 否 | 不存原文；编码复用传输层同一函数 `decision.py:402-417`（JSON `sort_keys` 规范化），上限同 `max_state_bytes=16384`（`decision.py:244`） |
| `questions_version` | str | 问题集常量内容的 sha 短码（如 `q-3f2a11c0`） | 否 | 问题集即 `DP1_QUESTIONS` 类常量（`triage-client.ts:55-58`）；文本一变版本即变 |
| `prompt_version` | str | 决策服务后端 prompt 模板版本 | 是（未知填 `"unknown"`） | 底座 D-004 未暴露该元数据（响应字段冻结于 `decision.py:111-119`），MVP 允许缺省 |
| `model` / `transport` | str | 后端 | 否 | 抄自响应（`decision.py:948-950`），过 `_redact` |
| `attempts` / `latency_ms` | int | 响应 | 否 | 同上（`decision.py:951-952`） |
| `available` / `reason` | bool/str | 响应 | 否 | `reason ∈ REASON_CODES`（`decision.py:88-99`） |
| `answer` | object | `_normalize_answers` 产物 `{qid:{value,confidence}}` | `available=false` 时 null | `decision.py:873-893` |
| `confidence` | float | min-of-answers | 是 | 聚合规则 `decision.py:419-435`；`confidence_source != api` 时该值不参与任何门控（底座硬规则，`triage-client.ts:33-36` 注释） |
| `confidence_source` | str | 后端透传 | 否 | `api | model-self-report | unknown`（`decision.py:101-103`） |
| `authority` | enum | 状态机解析（Q1） | 否 | `advisory | binding | human`；`human` 行=本来就要问人 |
| `escalated_reason` | enum | 写侧 | `authority=human` 时必填 | `unavailable | low-confidence | over-authority | p0 | input-invalid`（DS-4 四条失败路径 + P0，对应 AC-004） |
| `acted` | bool | 执行面 | 否 | binding 且绑定执行成功才 true；advisory/human 恒 false |
| `actual_action` | str | 执行面 | `acted=true` 时必填 | 一行实际动作，如 `dispatch type=coding` / `split → <new-task-key>` |
| `outcome` | enum | 结算行回填 | decide 行恒 `pending` | `pending | ok | rework | rollback | inconclusive`（仅 settle 行携带终值） |
| `human_override` / `override_by` / `override_reason` | bool/str/str | override 行 | 仅 override 行 | 不回写 decide 行，另起一行（Q5） |
| `cost_tokens` | int | 后端（未上报则 null） | 是 | MVP 可缺 |
| `note` | str | 写侧 | 是 | 复合归因、model-error 不可归因等标记（Q3.3） |

### Q2.2 `decision_id` 生成规则（可幂等 + 可反查）

- **格式**：`decision_id = "<dp>:<trigger_id>"`。`trigger_id` 是触发该决策的事件天然唯一键：
  - dp1 派发类：`<task_key>`（"a task_key identifies ONE run"，`run-store.ts:18-19`）；
  - dp2 检查点类：`<task_key>#ckpt<N>`（N 为该 run 内检查点序号，可从 trace.log `[CHECKPOINT]` 行序数导出，`output-writer.ts:666-680`）;
  - 无任务上下文类：`<iso-ts>`（此时 id 不幂等，登记为可接受，见 Q3.4 清单）。
- **幂等性**：同一 `trigger_id` 重试/重放只允许存在一行 `kind=decide`（写侧先查重；冲突即 fail 到上抛人，不静默覆盖）——重试语义与底座一致（`decision.py:680-728` 的 retry/backoff 只发生在传输层预算内，对外仍是一次决策）。
- **可反查**：id 同时出现在 (a) 档案行、(b) task.md 头部 `decision:` 行（Q3.2）、(c) 结算行、(d) 可选 ledger detail 字段。全链路 `grep` 可达。参考既有 id 风格：`f"{gate.id}@{decided_at}"`（`conductor.py:8205`）——本规则把 ts 从 id 中去掉，因为 ts 在重试中会变，而幂等键必须稳定；ts 已在行内有独立字段。

### Q2.3 `state_digest` 细则

- 算法：`sha256(hex)[:16]`，输入 bytes = `_encode_state(state)`（`decision.py:402-417`）——与传输层完全同一份规范化（dict → JSON `sort_keys=True`，失败降级 `str()`），保证"日志里同一决策的 digest 与发送内容一一对应"。
- 截断 16 hex（64 bit）：档案用途是"对账 + 反查"而非密码学承诺，16 hex 碰撞概率在每项目 ≤10^5 行量级下可忽略；完整原文按 D-003 本来就不落盘（state 只走 stdin，`triage-client.ts:22-23`）。
- 不可用行（`available=false`）同样记录 digest：失败样本也要能和后续人工决策对照。

### Q2.4 结果如何回填（append-only 前提下）

- decide 行的 `outcome` 写死 `pending`，**永不原地改**；结算另起一行 `kind=settle`，携带 `decision_id + outcome + settled_by + settled_at + evidence_ref`（指向 run.json/output.md 的路径与 run_id）。读侧合并取该组最后一条 settle 行（Q5.2）。
- `settled_by ∈ {pm-auto, human}`：PM 自动结算（run.json 终态映射，Q3.3）或人工标注（无法关联类，Q3.4）。
- 这与底座最强的先例完全同构：`auto_consumption_set = (phase=decide 且 executed) − (phase=revoke)`，即"正向行 + 负行，读侧做集合运算"（`conductor.py:7650-7664`）；`revoke_auto_decision` 只追加 `{decision_id, phase:"revoke", revoked_by, revoked_at}` 四字段负行（`conductor.py:7683-7703`）。

---

## Q3 结果关联机制（关键）

### Q3.1 现有可关联证据盘点

| 证据 | 关联键 | 内容 | 位置 |
| --- | --- | --- | --- |
| `workers/<task>/run.json` | `task_key`（主）、`run_id=<task_key>@<iso>` | `status ∈ pending/running/done/failed/needs-clarification/lost`、`exit`、`artifacts`、`supersedes` | `run-store.ts:29-56`；终态集合 `run-store.ts:29-34`；worker 唯一写者、launcher 只能加 `lost`（`run-store.ts:15-19`） |
| `workers/<task>/output.md` | 首行 run marker `<!-- mw-run: <run_id> status=<s> -->` | `## Exit Reason` / `## Questions`（第一行供 PM 读回）/ `## Deliverables` | marker：`run-store.ts:113-115` + `output-writer.ts:28-34`；段落：`output-writer.ts:505-528` |
| `workers/<task>/trace.log` | 文件名即 task_key | `[FLOW]`（`output-writer.ts:572-578`）、`[CHECKPOINT] ... risk=low|mid|high`（`output-writer.ts:666-680`）、`[END] exit=c elapsed=... phases=d/t`（`output-writer.ts:738-747`）、`[GOAL_CHECK] phase=N goal_mtime=ms`（`output-writer.ts:749-754`）、`[HEARTBEAT]`（`output-writer.ts:760-766`）、`[WRITE_SCOPE]` 行（`pm-orchestrator.ts:666-687` 的过滤器） | 生命周期全留痕 |
| `_project_log.md` | key + 时间行 | done 时的跨 key 汇总行（非空 summary 强制，`pm/ui-bridge.ts:2819-2873`） | 粒度过粗，只做辅助 |
| `pm-state.md` §7 Process Log | key | 人/PM 追加的叙事行（模板 `advance_phase.py:339-340`） | 非机器字段，不参与自动结算 |
| `.agenticdoc/_autopilot/auto-decisions.jsonl` | `detail` 字符串、`seq` | TS 侧五元组 `{seq, phase:"dispatch-alarm", kind, count, detail}`（`pm-orchestrator.ts:658`）；kind 白名单 `pm-orchestrator.ts:538,542`；Python 侧 `_append_auto_decision_row`（`conductor.py:7638-7647`） | 事件流，可反查"决策发生时刻附近发生了什么" |
| `.agenticdoc/_autopilot/triage-decisions.jsonl` | 行序（无 id） | 11 字段传输证据（`decision.py:121-134`） | 有 `dp` 无 `decision_id`——这正是 Q2 要补的洞 |

### Q3.2 推荐机制：`decision_id` 注入 + PM 终态结算（可落地，改动点最小）

1. **注入（派发时）**：dp1 类 binding 决策生效时，PM 把 `decision: <decision_id>` 写进 task.md 头部（与既有 `type:`/`phase:`/`images:`/`supersedes:`/`origin:` 同一头部行约定；头部行组装点在 `pm/ui-bridge.ts:1376-1379`，头部解析先例 `run-store.ts:168-172`）。worker 对此行零感知也能工作（它只是头部一行文本）。
2. **传导（worker 侧零改动）**：worker 照常写 run.json / output.md / trace.log；`run_id` marker（`run-store.ts:113-115`）已保证 output.md 可反查 run。
3. **结算（PM 侧，worker 终态时）**：PM 在回收 worker 终态处（现有 readback 面：`run.json` 状态判定 `run-store.ts:70-104`；kind 白名单扫描 `pm-orchestrator.ts:538,542`）读 task.md 头的 `decision:` 行 + run.json 终态，追加 settle 行。映射表见 Q3.3。
4. **兜底（回查）**：头部行丢失时，用 `(key, task_key)` 二元组反查档案（decide 行的 `task_key` 字段，Q2.1）——两者是冗余关联键，任一即可。

### Q3.3 终态 → outcome 结算映射（AC-006 的"自动关联"主通道）

| worker 终态（`run-store.ts:29-34`） | outcome | 理由与备注 |
| --- | --- | --- |
| `done`（exit 0，`[END] exit=0`，`output-writer.ts:738-747`） | `ok` | 产品存在且契约段齐全（`output-writer.ts:442-500` 的 gaps 判定） |
| `done` 但 PM 后续人工回滚（git revert / supersedes 重派，`run-store.ts:49-50`） | 补一行 settle `rollback` | 回滚是显式动作，不猜 |
| `failed`（exit 1） | `rework` | 计入返工率；**不计入推翻率**（失败≠决策错） |
| `failed` 且 exit 3 / `model_exhausted`（`pm-orchestrator.ts:525-532` kind=model-error 注释、`worker/worker-mode.ts:3290`） | `inconclusive` + `note=model-error` | 模型层故障不反映决策质量，从一致率分母剔除 |
| `needs-clarification`（exit 2） | 保持 `pending`，转人工；人工裁决后由 override 行或 settle 行收敛 | DS-4：上抛人，禁止默认动作 |
| `lost`（launcher 标记，`run-store.ts:17`） | 保持 `pending` + `note=lost` | 结果不可知，不结论 |

### Q3.4 无法可靠关联清单（显式登记，"只能人工标注"）

1. **PM 本地决策（`task_key=null`）**：如 dp9 模型选择——没有 run.json 可挂。`decision_id` 仍会生成，但结算行只能 `settled_by=human`（或时间窗启发式，报告中降置信标注）。
2. **长时延结果**：决策后数小时/次日才显现的后果（如 dp10 依赖升级）——超出任何自动结算窗口，只能人工标注。
3. **复合归因**：一次失败同时受 dp1（派发类型）与 dp2（拆分粒度）影响——自动归因取"最后一个 binding 决策"，settle 行 `note=composite`，报告标注不可单因。
4. **worker 内部细粒度动作**：trace.log 的 `tool_call` 行（`worker/worker-mode.ts:3151`）无语义标签，不参与归因。
5. **跨 key 外溢**：A key 的决策影响 B key 的结果——不自动关联，报告按 key 切面分列。

---

## Q4 review 报告结构与判据

### Q4.1 报告骨架（phase 末自动生成）

路径与命名：`<key>/evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`。命名对齐既有门禁先例（`evidence/quality-gate-report-*.md`，`advance_phase.py:89-94`；`evidence/research/spec-*.md`，`advance_phase.py:50-51`）。

```markdown
# Decision Review — <key> @ <phase>（<起>–<止>）
## 1. 概览
total=N  binding=n  advisory=m  escalated_to_human=k  unresolvable=u
## 2. 判据表（Q4.2）
| 指标 | 值 | 阈值 | 判定 |
## 3. 逐决策清单
| decision_id | dp | answer | authority | acted | outcome | override |
## 4. 无法关联项（Q3.4 清单）
## 5. 授权建议（机器可读一行）
suggestion: <continue|narrow|revoke> <dp...>   # 数据不足时: suggestion: insufficient-data
```

### Q4.2 判据表（阈值建议 + 数据不足规则）

| 指标 | 计算（基于 Q2 字段） | 通过阈值 | 未通过动作 |
| --- | --- | --- | --- |
| 已结算样本 N | settle 行数（去重 decision_id，剔除 `inconclusive`） | **N ≥ 5** 才允许下结论 | `N < 5` → 报告必须写"数据不足，不结论"，`suggestion: insufficient-data`（AC-007） |
| 一致率 | `ok / N` | ≥ 0.90（P2）/ ≥ 0.95（P1） | 不达标 → 建议降级候选 |
| 人工推翻率 | override 行数 / N | ≤ 0.15 | 超 → 建议 `narrow` |
| 回滚率 | settle `rollback` 数 / N | ≤ 0.10 | 超 → 建议 `narrow` |
| 不可用率 | decide 行 `available=false` / 全部 decide 行 | 仅报告，不门控（DS-4 已保证失败上抛） | — |
| 成本 | `latency_ms` 分位 + `cost_tokens` 合计 | 仅报告 | — |

- 晋升/降级判据的统计口径（Wilson 下界、窗口长度）终稿归 RQ-5（spec.md §7 指明"置信下界，RQ-5 定稿"）；本表是报告层的**呈现判据**，两者共用同一批 settle 行，不会打架。
- `inconclusive` 一律不进分母（Q3.3），报告单列。

### Q4.3 生成时机

- PM 侧结算器在回收 worker 终态时检查 owner key 的 phase：发现 `pm-state.md` 的 `- Phase:` 行（`advance_phase.py:345-351`）已推进到新 phase，且上一 phase 尚无对应报告 → 生成。纯读触发，不阻塞推进。
- 报告写入走 worker_file/write-face 白名单（PM 对 `<key>/evidence/**` 本就有写面，本任务自己的 write_face 即此模式，见任务头 `write_face:` 字段）。

### Q4.4 key 收尾强制签收（门禁）与结论写回

1. **门禁**：在 `GATES["done"]`（`advance_phase.py:69-95`）追加两条规则，全部用现成 check_type，零新机制：
   - `("evidence/review/sign-*.md", "glob_has_files", 1, "收尾前必须有决策签收记录")`
   - `("evidence/review/sign-*.md", "content_match", r"conclusion:\s*(continue|narrow|revoke)", "签收必须包含机器可读 conclusion 行")`
   - `check_gate` 是纯读校验（`advance_phase.py:191-289`），`content_match` 处理器现成（`advance_phase.py:220-227`）；done 门禁已有 `content_match` 先例（`pm-state.md` PASS 证据，`advance_phase.py:88`）。
2. **签收文件**：`<key>/evidence/review/sign-<yyyymmdd>.md`，由人（或人逐字确认的 PM 会话）写入；正文引用对应 phase 报告。门禁只验存在与格式，不验"人真的看过"——这条边界要在设计里写明（防"PM 自己替人签"需靠 write-face + review 抽查，登记为残留风险）。
3. **结论写回授权档（可机器执行）**：
   - `continue` → 仅更新快照 `points[dp].last_review`；
   - `narrow` → `points[dp].state = advisory`（或删除子类授权键）；
   - `revoke` → `points[dp].state = revoked`（重制动，恢复仅人工，Q1.2）。
   - 写入协议：复用锁 + tmp + `os.replace`（`mw.py:772-792`）；同时向决策档案追加 `kind=authority-change` 行（`decision_id = "signoff@<key>@<ts>"`，字段 `conclusion / dps / by`），满足 DS-2"写回配置并留痕"。快照与档案的互证规则见 Q1.7。
   - 报告的 `suggestion:` 行是**建议**，签收文件的 `conclusion:` 行才是**生效指令**——两者分离，保证 AC-008 断言的是"签收语义变化"而非"报告措辞"。

---

## Q5 不可篡改（append-only 与读侧合并）

### Q5.1 append-only 保证（四层）

1. **无 update 路径**：写侧只提供 append 函数；decide/override/settle/authority-change 全部是新行。先例：`_append_evidence` 只 `open("a")` 追加（`decision.py:962-968`）、`_append_auto_decision_row` 只追加（`conductor.py:7646-7647`）、`recordDispatchAlarm` 只 `appendFileSync`（`pm-orchestrator.ts:660`）。
2. **哈希链**：每行 `prev_sha` = 上一行规范化 JSON 的 sha256 前 16 hex（首行 `"0"*16`）。读侧（doctor）校验断链即告警。注意：链校验使"改历史任意一行"必然断链，配合"追加永远写文件尾"，篡改面收敛为"重写整个文件"——对本地开发约定足够（与 `auto-decisions.jsonl` 现状同级，后者连链都没有）。
3. **并发安全**：多进程追加统一走 `mw_common.acquire_lock`/`release_lock`（`mw_common.py:2369-2384`，O_CREAT|O_EXCL 重试协议），同 `_decide_write_config` 的用法（`mw.py:772-792`）。单一写者优先：Python 客户端写 triage 证据、TS 只读（`triage-client.ts:25-28` single-writer 契约）的模式照搬到 decisions.jsonl（写侧收敛到一个进程内模块）。
4. **负行而非回滚**：撤销/推翻/降级都是追加负行或新状态行（`revoke_auto_decision` 先例，`conductor.py:7683-7703`）。

### Q5.2 读侧合并规则（结算行 × 原始行）

- **现状边界**：`mw decide show` 与 doctor 只消费"最后一行"——`decide_last_evidence` 从尾扫描返回 `(行号, record)`，坏行/非 dict 返回 None（`mw_common.py:1620-1642`）；`_decide_show_payload` 输出 `last_seq/last`（`mw.py:845-878`，字段在 `mw.py:875-876`）；`_decide_show` 人读面打印 `last: seq=...`（`mw.py:880-912`）；`_doctor_decide` 派生 `last_suggestion/last_unavailable`（`mw_common.py:1676-1685`）。零扰动规则：未配置项目的 doctor 输出逐字节不变（`mw_common.py:1648-1651`）。
- **扩展后**：
  - `decide_last_evidence` 语义**保持不变**（它回答"最近一次传输调用结果"，11 字段行视图）。
  - 新增 `fold_decisions(rows) -> map[decision_id, folded]`：按 `decision_id` 分组、组内按 `(seq)` 排序，折叠规则：
    - `outcome` = 最后一条 settle 行的值（无 settle 行 = `pending`）；
    - `human_override` = 存在 override 行即 true，附最后一条 override 的 `override_by/reason`；
    - `authority` 当前值 = 快照文件（Q1.7）为准，档案 authority-change 行用于审计追溯；
    - `answer/model/confidence/...` = decide 行原值（不可变）。
  - 坏行策略：跳过 + 计数，报告"unparsable_lines=N"（沿用 `decide_last_evidence` 对坏行返回 None 的容错精神，`mw_common.py:1637-1641`），不炸整个视图。
  - 展出面：`mw decide show --decisions`（或新子命令）输出折叠视图；doctor 增加独立 section，不动既有 triage section 的字节（保零扰动承诺）。

---

## Q6 与既有格式（11 字段证据行）的兼容

**结论：并存，不升级。** 11 字段行保留为**传输层证据**，新档案为**决策语义层**，两者一行对一个决策时的分工：

- 11 字段行（`decision.py:121-134`：`ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source`）继续由 `DecisionClient._append_evidence` 写入 `triage-decisions.jsonl`（`decision.py:74`），路径与格式被 D-005 冻结；现有消费者 `mw decide show`/`doctor`（`mw.py:845-878`、`mw_common.py:1645-1686`）零改动。
- 新档案行**冗余携带**这 11 个字段的值（Q2.1 已含全部），因此：
  1. 只 grep 字段名的旧工具/人在新档案里也能命中（透明共存）；
  2. 若将来决定"升级"而非"并存"，读侧按**字段超集**兼容：11 键是 `dict.fromkeys(_EVIDENCE_FIELDS)` 固定生成的（`decision.py:945`），新行包含全部 11 键 + 新增键，旧解析器用 `row.get(k)` 读新行不会崩（多出的键被忽略），新解析器用 `row.get("decision_id")` 是否存在区分新旧行（旧行走旧解析，行为与今天逐字节一致）。
- 不升级的硬理由：向 11 字段行加字段 = 改 `_EVIDENCE_FIELDS` = 破坏 `_decide_show_payload`/doctor 的"最后一行"视图契约（`mw.py:875-876` 的 `last` 字段直接承载整行 record，字段膨胀直接改变机器与人类输出）与 D-003 响应字段冻结面（`decision.py:111-119`）；且 11 字段行无 `decision_id`，结果关联回填（Q3）没有挂点，硬塞会把它变成"半个档案"，两头不靠。
- 风险与对账：并存意味着同一决策有两行（传输行 + 档案行）。对账键 = `(ts, dp)` + `state_digest`（档案行独有，传输行没有 digest 时用 `(ts,dp,available,reason)` 近似对账）。报告器只以档案行为准，传输行仅用于失败原因细分（8 类 REASON_CODES，`decision.py:88-99`）。

---

## 最小可用版本（MVP）建议

先做这几条就够 review 闭环（其余全部推后）：

1. **授权快照文件**：`.mw/decide-authority.json`（`level` + `points[dp].state` + `cooldown_until`），读侧解析 + P0 硬拒（Q1.7；对应 AC-001/AC-002）。`advance` 档先只做"档位记录 + 报告提示 P1 候选"，P1 自动晋升推后（先由签收人工驱动，Q1.4 的机制保留在 schema 里）。
2. **决策档案最小字段集**（Q2.1 裁剪）：`seq / prev_sha / kind / decision_id / ts / dp / key / task_key / state_digest / questions_version / available / reason / answer / authority / escalated_reason / acted / actual_action / outcome`。`prompt_version/cost_tokens/note` 可缺省；`human_override` 用 `kind=override` 行表达，不占 decide 行字段。
3. **关联只做一条通道**：dp1（派发）binding 决策 → task.md 头 `decision:` 行（`ui-bridge.ts:1376-1379` 处加一行）→ run.json 终态结算行（Q3.3 映射表全量实现，含 `inconclusive` 剔除）。其余决策点的结算先落 `settled_by=human`。
4. **phase 末报告 + done 签收门禁**：报告骨架按 Q4.1（含"数据不足不结论"硬规则）；`GATES["done"]` 加 Q4.4 的两条现成规则；签收结论写回走 Q4.4 第 3 步。
5. **降级只做两条自动规则**：30 条滑窗 `override_rate>0.15` 或 `rollback_rate>0.10` → `suspended` + 7 天冷却（Q1.5/1.6）；熔断式突发制动等真实数据说话后再定阈值。

推后项（显式登记）：哈希链的 doctor 告警面化、P1 逐类晋升自动化、`inconclusive` 的自动归因细化、dp2+ 决策点的注入与结算、与 `auto-decisions.jsonl` 的跨文件对账视图。

## 参考索引（本文件引用汇总）

- `packages/multi-workers/decision.py`：73, 74, 88-99, 101-103, 105, 111-119, 121-134, 135, 231-253, 244, 261, 302-316, 402-417, 419-435, 680-728, 873-893, 895-938, 940-968, 945-961
- `packages/multi-workers/mw.py`：672-688, 690, 745-764, 772-792, 794-813, 845-878, 880-912, 914-967, 969-987
- `packages/multi-workers/mw_common.py`：1601-1617, 1620-1642, 1645-1686, 2369-2384
- `packages/multi-workers/autopilot/conductor.py`：3569-3580, 3603-3611, 6612-6619, 6622-6627, 7616-7635, 7638-7647, 7650-7664, 7683-7703, 7742-7759, 7762-7789, 7792-7838, 7843-7863, 7866-7871, 8186-8235
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`：14, 22-28, 33-36, 39, 44, 47, 55-58, 64-67, 132, 263-276
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：235-252, 258-275, 1376-1379, 2819-2873
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`：525-532, 538-542, 553-564, 572, 645-664, 666-687, 832
- `packages/coding-agent/src/extensions/agent-team-loop/shared/run-store.ts`：15-19, 26-56, 58-60, 70-104, 106-108, 113-115, 168-172, 194
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`：28-34, 442-500, 505-528, 572-578, 666-680, 712-716, 738-747, 749-754, 760-766
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`：3151, 3290, 3702-3707
- `.agents/skills/agentic-task/core/scripts/advance_phase.py`：25, 41-96, 88, 191-289, 220-227, 292-396, 339-340, 345-351
- `.agenticdoc/mw-decision-substitution/spec.md`：§3 DS-1/DS-4、§4 决策点表、§6、§7、§9 RQ-5
- `.agenticdoc/mw-decision-substitution/pm-state.md`：§5 DS-1..DS-5
