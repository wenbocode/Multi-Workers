# RQ19 静态设计输入：conductor/config/xkey 全文读 + H01～H12 条件化消费、预算/真实队列、版本失效与 H12 受控隔离

> 角色：research（只读）。用途：联合设计的静态输入。**不是**设计批准、实现、验收、签收或运行验收。
> 写面：本文件是唯一证据载体。未修改源码/配置/预算授权/状态/旧研究/PM 文档；未运行测试、CLI 裁决、provider/服务探针；未读活配置/gate/ledger/roadmap/刹车/凭证/其他 key 运行材料；未恢复任何真实对象。

## 结论

1. **读取完成**：`packages/multi-workers/autopilot/conductor.py`（8727 行 / 371529B）、`xkey.py`（1435 行 / 52458B）、`config.py`（264 行 / 12276B）均分段读到实际 EOF（conductor 8 段、xkey 2 段、config 1 段）。另全文读 `advance.py`、`effective_config.py`；定向读 `gates.py`（常量/FRONTMATTER_FIELDS/authorizes 解析）、`state.py`（read_index/claim_state/used_rounds）、`mw_common.py`（parse_workers_file/parse_workers_queue/read_run_status/_TERMINAL_STATUSES）。未全文读的文件见「残留与未验证」。
2. **运行面与目标集差距是结构性的**：今天可运行集合只有 6 个 gate kind（`stage-confirm, stage-close, stalled, budget-exhausted, goal-change, xkey-authorize`）× 3 个状态（`pending, approved, rejected`）+ `consumed_at/consumed_seq` 消费记录。`dp-auto`/`dp-route`/`dp-pm-steer`/`dp-gate-approve` 等目标入口在 conductor 中**不存在**；四业务选项也没有承载字段。
3. **三状态队列与四业务选项不正交，且现状已把「reject」压成 5 种互不相同效果**：stage-close reject→stage `halted`；stage-confirm reject→重新提案（≤2 次）；stalled reject→`closed-legacy`；budget-exhausted reject→stalled；deferred-review reject→`rework`(running)。这五种都由「rejected」一个状态触发，无法在文件中区分，故 SPEC「reject 不统一关闭/halted、仅获授权遗留方案才收尾」今天不可核。候选结构见 E2（结论：推荐「传输轴 pending/answered + 业务轴 answer_kind 四值 + 独立 disposition 记录」，不把四选项压回 approved/rejected）。
4. **H06 已被现有代码破坏（不是未实现，而是反向实现）**：`tick()` 只用「是否存在 pending goal-change gate」判定 halt；任何已答 goal-change（approved 或 rejected）都会刷新 `st.goal_baseline` 并恢复运行，从不读 `gate.status`。goal 版本只有 `mtime_ns` 进 timeline detail，没有 sha/版本绑定 → AC-024 的「仅有效 approve 才采用指定版本、reject 不刷新 baseline」当前不可能成立。
5. **H11 halted 没有任何在带内（in-band）恢复通道**：`halted` 在 `_STAGE_STATUS_RANK` 属 terminal rank，`_stage_transition_allowed` 拒绝从 terminal 写任何新状态；`_stage_activation` 见到任一 `halted` stage 直接 `return False`。唯一恢复 = 人工改 `_roadmap.md`（代码注释亦如此声明），没有 gate/DP/授权链 → AC-034/035 需要的「恢复记录或新版本关联」今天不可观测。
6. **40 个冻结 frontmatter 字段中只有约 10 个有生产者**，其余是解析即可、无人写：`subject_sha256, proposal_sha256, observed_at, evidence_refs, constraints, evidence_anchor_mtime_ns, out_of_band_actions, gate_schema` 在 conductor 中出现 0 次（无写无读）；`goal_sha256, goal_sha256_before/after, goal_diff, roadmap_validation, verdicts_final` 有读无写 → `proposition_goal_change`/`proposition_stage_confirm`/旧 `proposition_stage_close` 的事实面恒缺，永远只能拒绝（guard 永假）。**因此不得冻结旧 40 字段**；应按 Material 版本对象只保留有生产者/有消费者的字段（清单见 E4）。
7. **`authorizes` 只有一个消费者**：闭集 `{retry, contract-change}`，`contract_guard.gate_authorizes_contract_change` 读 `contract-change`；`retry` 无任何消费者，`_resume_credits` 只看「stalled 且 approved」而不看 `authorizes`；新建 gate 一律物化 `authorizes: []`。⇒ 授权证明（H07/H08/H11/H12 都需要）今天既无统一载体也无统一消费点。
8. **H04 的「硬预算」没有数值来源**：config 无金额/token/attempt 硬预算字段，只有 `round_budget`（每 loop 轮数）、`max_parallel_keys`/`max_workers_per_key`（并发）、`AUTO_NIGHT_CAP=6`/`AUTO_KEY_CAP=2`/`AUTO_BURST_60S=17`/`AUTO_BURST_1H=100`（自动决策配额）、`gate_reminder_*`、`l3_abort_retry_limit`、`xkey_verify_timeout_s`、`worker_timeout_min`。`budget-exhausted` 的 approve 只给**一轮** bonus（`_budget_bonus`），reject 直接 stall。故「提高硬预算须具体人工授权」在测量与载体上都还没有落点；SPEC 的「未设置具体预算」与代码一致，不得由本设计代设值。
9. **真实队列状态并不等价于「空」**：gates 侧区分 unknown（`GateQueueUnreadable` → tick `error`；单文件损坏 → 整 tick skip），`_workers.parallel` 侧 conductor 用的是 `parse_workers_file`（**丢弃不可解析行**），而 `parse_workers_queue` 才返回 `{rows, unparsable, version}`；`_index.parallel` 缺失 = `[]`（unknown 当空）；`run.json` 的 `read_run_status` 返 `None` = 「无信息」。⇒ H09「未知不当空队列重派」在 `_workers.parallel`/`_index.parallel` 上今天不成立（一个坏行/缺失文件即可让 key 看起来空闲）。
10. **H12 熔断只有「刹车 + 一次性升级」，没有受控恢复**：`auto-brake.md` create-once（`_trip_auto_breaker`），`auto_breaker_state` 每次从文件重derive；`auto_decide_gates` 在 active 时**在任何 gate 枚举之前** return；除 `_trip_auto_breaker` 外无写入者，恢复 = 人工删文件（无记录、无原因消除证据、无观察窗口）。`revoke_auto_decision` 只追加 `phase:"revoke"` 行把 decision 移出 `auto_consumption_set`，**不回滚 gate 文件/roadmap/索引的既有效果** ⇒ 「撤权」今天不是撤销，只是不再重复消费。`AUTO_RULE_BY_KIND` 已覆盖全部 6 kind ⇒ 「新增 kind」或「未列规则」都不构成隔离证明（新 kind 若落在 `AUTO_RULE_BY_KIND` 里仍会被同一 auto pass 评审）。
11. **两方案结论**：推荐方案 A「显式条件化效果适配层」（新增 `autopilot/gate_effects.py`：Material + Disposition + EffectPlan + 单一 commit），复用现有 6 个消费者函数不改语义；方案 B「各消费者自带完整事项条件与效果」仅作为 xkey S4 这类「必须在提交时现场计算事实」的局部回退（详见 E3）。
12. 以上全部为静态读码结论；**未**验证安装身份、cross-language 镜像、TS 侧消费、运行行为，**未**宣称设计/AC/QG/签收通过。

## 证据

### E0 读取范围（实际到 EOF / 定向）

全文读（read 工具，分段至 EOF）：
- `packages/multi-workers/autopilot/conductor.py`：1–8727（含 `tick`, `orchestrate`, `_consume_answered_gates`, `_apply_stalled_approvals`, `_apply_stalled_rejections`, `_apply_review_decisions`, `_apply_reattests`, `_consume_xkey_gate`, `_xkey_aggregate`, `_xkey_proposal_stage`, `_xkey_apply_stage`, `execute_loop`, `_verify_loop`, `_done_transaction`, `mark_stalled`, `auto_decide_gates`, 全部事实面谓词与 RULES、`auto_breaker_state`/`_trip_auto_breaker`, `answer_gate_auto`, `answer_gate_confirmed`, `reattest_gate`, `main`）。
- `packages/multi-workers/autopilot/xkey.py`：1–1435（`parse_registration`, `collect_registrations`, `ledger_append`, `ticket_write/load/tickets_iter`, `locate_frozen_block`, `check_boundary`, `apply_block_replace`, `run_verification`, `evidence_bundle_write`）。
- `packages/multi-workers/autopilot/config.py`：1–264（`DEFAULT_CONFIG`, `validate_config`, `load_config`, `cached_load`, `envelope_fallback_enabled`）。
- `packages/multi-workers/autopilot/advance.py`：全文（`locate_platform_dir`, `advance`, 120s 超时）。
- `packages/multi-workers/autopilot/effective_config.py`：全文（`EFFECTIVE_KEYS = {xkey_verify_cmd, xkey_verify_cwd}`, `load_effective`）。

定向读（只取所需段，非全文）：
- `gates.py`：`GATE_KINDS`, `GATE_STATUSES`, `FRONTMATTER_FIELDS`（12 base + 28 v2 = 40）, `AUTHORIZES_ACTIONS`, `_SCALAR_EXTENSION_FIELDS`, `BLOCKER_CLASSES`, `authorizes` 解析段, `enumerate/pending_gates` 契约注释。
- `state.py`：`read_index`, `claim_state`, `read_key_states`, `used_rounds`。
- `mw_common.py`：`_TERMINAL_STATUSES = {done, failed, needs-clarification, lost}`, `parse_workers_file`, `parse_workers_queue`, `read_run_status`, `row_belongs_to`, lock helpers。
- `contract_guard.py`：仅经 grep 观察 `gate_authorizes_contract_change` 与 `CONTRACT_CHANGE_ACTION`（**未全文新核**，沿用 RQ14 对 gates/contract_guard 的观察）。

未覆盖（明确声明）：`dispatch.py`（106KB，只做定向 grep：`authorizes` 1 次、v2 字段 0 次）、`roadmap.py`, `evidence.py`, `ops/timeline.py`, `write_face.py`, `task_graph.py`, `closure.py`, `audit_evidence.py`, `index_parallel.py`, `card_audit.py`, `review_split.py`, 框架 `advance_phase.py` 本体、TS 扩展全部、安装镜像/服务进程身份。

### E1 现状：6 kind × 3 状态 × 消费点 × 效果 × 消耗 × 异常 × 重放（H01～H12 对照）

格式：触发 | 条件复核（现状） | 决定 | PM 后继请求 | 实际效果 | 消耗 | 异常 | 重放

- **H01 stage 启动**（kind `stage-confirm`）| 上一 stage 关闭 / roadmap 提案写入后存在 pending stage 且无 running stage | `_activate_pending_stage`：rejection 与 roadmap mtime 比较、`_gate_open` 去重 | 今天仅 approve/reject | 无（目标为 dp-gate-approve）| approve→`_set_stage_status(running)`+派发；reject→再派 roadmap-writer（≤2，`used_rounds` 计数）后等人工 | 轮数=proposal 尝试；无预算 | dispatch 拒绝→`config` 事件；锁占→下 tick | `consumed_at` + `(id, created_at)` timeline 回退
- **H02 stage 关闭**（`stage-close`）| 全 key 终态 + 无在途行 + reconciliation 不阻断 | `_stage_closure` 前置 5 条 + `evidence_reconciliation_blocks` | 无 | approve→`closed`+开下一 stage gate；reject→**`halted`** | 无轮数消耗 | 锁占→下 tick；dossier 写失败→`config` 且不开 gate | `consumed_at`；monotonic guard 拒 terminal 回归
- **H03 stalled 处置**（`stalled`）| 连续失败达阈值/预算耗尽/无裁决/可疑证据 | `_advance_failure_streak`, `_record_advance_result`, `_stall_blocker_class`(paperwork/judgment) | 无 | approve→`running`+每 loop 1 credit；reject→**`closed-legacy`（全仓唯一写入者，需 `confirm=True`）** | credit 单向、`used_rounds` 单调 | 锁占→下 tick；gate 写失败→config | `consumed_at`；`_consumed_gate_ids` 防重放（2026-09-24 6684 gate 事故来源）
- **H04 软轮次追加**（`budget-exhausted`）| `used >= limit` 且仍有 blocking gaps | `proposition_budget_exhausted`（used==limit+credits 且 gaps>0）| 无 | approve→恰 1 轮 bonus（`_budget_bonus` 只看存在 approved gate）；reject→`mark_stalled` | 1 轮/loop；无硬预算 | gaps 不可测→`budget-count-drift` 拒绝 | gate 永久 approved 但 `used_rounds` 单调 → 不重复发放
- **H05 pending-review 复核**（`stalled`/`budget-exhausted` 作答 + `pending-review` 状态）| 48h deadline（`expires_at` 优先，否则 `created_at+48h`）或 stage 其余 key 全终态 | `review_batch`, `_review_deadline`, `_process_deferred_reviews` | 无 | approve→`resume`(running)；reject→`rework`(running)；**不会产生 done/closed-legacy** | 无轮数 | deadline 不可读→`unknown` 不造值 | `gate-answered`+`consumed_at`；`_apply_review_decisions` 幂等
- **H06 goal 采用**（`goal-change`）| goal.md mtime 变 | `open_goal_change_gate` + `gates.create`；**不读 status** | 无 | **任何已答 → 刷新 baseline 并恢复**（approved 与 rejected 等价）| 无 | gate 队列损坏→tick skip | 每 mtime 变 1 gate；`goal_baseline` 内存态（重启从当前 mtime 起）
- **H07 跨 key 受限修复**（`xkey-authorize`）| below 轮登记可解析 + owner 终态 | `_xkey_aggregate`（dedup_key、owner 终态、locate_frozen_block、request_id 去重）| 无 | approve→ticket `approved`→同 tick S1–S6；reject→ticket `rejected`+ledger | proposal ≤2 次（`proposal_exhausted_at`，人工清字段才重试）| 边界违例→零写入 + `boundary_violation`；verify 非绿→字节回滚 + `verify_failed`（terminal，无重试路径）| 每 request_id 1 gate；ledger `dedup_key`；`_xkey_replay_run` 防崩溃重放
- **H08 冻结 AC/VC 变更**（无专用 kind；`authorizes:["contract-change"]`）| design/plan 首见冻结（`_freeze_contract_first_sight`）| `contract_guard.evaluate`（freeze sha/ids + gate 授权）| 无 | 未授权改写→`contract-refused`+`mark_stalled(contract-unauthorized)`；授权 gate 存在→放行 advance | 无 | freeze 写失败→`contract-frozen` 降级事件 | freeze 首次写一次，非空不重写
- **H09 proposal 耗尽恢复**（无专用 kind）| 派发拒绝/连续失败 | `_write_face_wait_reason` 区分等待类 vs 作者错误；`_advance_failure_streak` | 目标 dp-pm-steer/dp-auto | dispatch 拒绝→`mark_stalled(reason_code=...)`；等待类→下 tick | `used_rounds`（含在途，`task.md` 一存在即计数）| 坏行被 `parse_workers_file` 丢弃→可能误判空闲 | `_consumed_gate_ids`；`reason_code` 闭集（越界被丢弃并记 config）
- **H10 roadmap 重规划**| roadmap 缺失/被 reject | `_latest_rejected_confirm` + **mtime 比较**（`rm_newer`）| 目标 dp-pm-steer/dp-auto | 重派 roadmap-writer（整文件重写）；两提案用尽→等人工改 roadmap | 2 提案硬编码（`used >= 2`）| 无版本/sha 记录 → 旧提案仅存于 rejection gate note 与 timeline | 依赖 mtime；同一 mtime 粒度下可误判
- **H11 halted 恢复**（无 kind）| stage 变 halted（仅 stage-close reject 一条路径）| 无 | 无 | **无**：terminal rank 拒写；`_stage_activation` 直接 return False | 无 | 只能人工改 `_roadmap.md`，无审计 | 无（无恢复对象）
- **H12 自动熔断恢复**（无 kind）| `_auto_breaker_signal`：60s≥17 / 1h≥100 / 同签名重复≥2（生命周期内） | `auto_breaker_state` 每次重derive | 无 | `auto-brake.md` create-once；active 时 auto pass 直接 return（在枚举 gate 之前）| 无 | 写失败→config 事件；文件在=永久 active | 已 tripped 不重复写/不重复行（`_effective_auto_decision` 只对 decide 行去重；breaker 行 `executed=False`）

### E2 三状态 gate 队列 × 四业务选择：候选正交结构（不压回 approve/reject）

现状事实：`GATE_STATUSES = (pending, approved, rejected)`；业务效果完全由 status 推导（见 E1 的 H01–H07）；`answer_source`/`auto_policy_id` 只记录「谁答/哪条规则」，`authorizes` 默认 `[]` 且只有 `contract-change` 有消费者。

- **候选结构 S1（推荐）——传输轴 + 业务轴分离，两层都落盘**
  - 传输轴（队列/提醒/升级仍可用三态）：`pending` → `answered`；`answered` 是队列终态（不再提醒、不再被 `_gate_open` 视为 pending）。
  - 业务轴（一个版本化 `Disposition` 记录，独立于 gate 文件）：`answer_kind ∈ {approve, steer, need_fix, reject}`；派生 `released = (answer_kind == "approve")`，**只有 approve 允许产生状态变更效果**。
  - 兼容：读侧把旧 `approved` 映射为 `answer_kind=approve`、旧 `rejected` 映射为 `reject`（只读解释，不写回历史字节）。
  - 后继请求：`steer → next_request{dp: dp-pm-steer, ...}`、`need_fix → next_request{dp: dp-auto, ...}`；二者 `released=false`，只能通过「PM 另一次真实请求 + 其自身合同」推进（AC-049）。
  - `reject` 不携带任何隐含关闭：可选 `legacy_close` 描述符（`plan_ref` + 授权证明 + 范围）才会产生 `closed-legacy`/遗留收尾，否则只记「拒绝本方案」。
  - pros：三态队列保持 UI/提醒/锁协议不变；四选项第一次可核；`released` 单一派生点消除「reject 五种效果」歧义。cons：新增一层记录与读侧映射；gate 文件与 disposition 需原子配对（同一 gates lock 内写，先 disposition 后 status，崩溃时以 disposition 为准重放）。
- **候选结构 S2——保留三态，效果用旁路文件承载**
  - gate 文件仍只写 3 值；四选项写 `_autopilot/dispositions/<gate_id>.md`；`steer/need_fix` 时 gate 保持 `pending` 但写 `consumed_at` 并让提醒器读 disposition 抑制。
  - pros：不动 `GATE_STATUSES`/TS 镜像；cons：`pending + consumed_at` 是自相矛盾态，提醒/升级/`_gate_open` 三处都要加例外，回放语义更脆（旧消费者会把 `pending` 当未答而重新创建 gate）。
- **不建议**：把四选项塞进 `approved/rejected`（现状）。理由：reject 已承载 5 种互斥效果；`steer/need_fix` 若写 `rejected` 会被 `_apply_stalled_rejections`/stage-close 消费为 `closed-legacy`/`halted`，直接违反「steer/need_fix 不是放行也不是已整改」。

正交不变量（供 AC 断言）：
I1 `released` 仅由 `answer_kind=approve` 派生；`steer/need_fix/reject` 的效果集合不含任何 `stage running/closed`、`key running/done`、`bonus round`、`xkey apply`。
I2 每个 `(kind, answer_kind)` 至多 1 个效果描述符；无描述符 = 记录型（no-op + 后继请求）。
I3 三态 status 不得用于推断业务；业务只读 disposition（或旧文件只读映射）。
I4 `reject` 只有携带 `legacy_close`（授权证明 + 范围）才产生关单；否则零状态写入。

### E3 两种合法技术方案（精确候选文件/函数、pros/cons、推荐）

**方案 A（推荐）：显式条件化效果适配层，复用原消费者**
- 新文件候选：`packages/multi-workers/autopilot/gate_effects.py`（不并入 conductor，避免继续膨胀 371KB）。
- 候选接口（精确到函数）：
  - `@dataclass(frozen=True) class Material`: `kind, key, stage, loop, pointer_set: tuple[(rel, sha256)], counts{used,limit,credits}, authorization{proof_kind, proof_id, scope}, request_ids, expires_at, unknown: dict`
  - `@dataclass(frozen=True) class Disposition`: `gate_id, answer_kind, released: bool, next_request: dict|None, legacy_close: dict|None, scope, decided_by, decided_at, evidence_version: tuple[(rel, sha256)], source ∈ {human, auto, reattach}`
  - `def build_material(project_root, gate, status_of) -> Material`（唯一读盘处，复用 `_stage_close_facts`/`gate_evidence_state`/`_done_credentials_present`/`xkey.ticket_load`）
  - `def adapt(material, disposition) -> EffectPlan`（纯函数；`EffectPlan.effect ∈ {stage_run, stage_close, stage_halt, key_reopen, key_closed_legacy, key_stall, grant_round, review_resume, review_rework, xkey_apply, record_only, none}`）
  - `def commit(project_root, st, plan) -> str`（幂等，按 effect 调**现有**函数：`_set_stage_status`, `_ensure_next_stage_gate`, `apply_review_decision`, `_apply_reattests` reopen 分支, `_xkey_apply_stage`, `mark_stalled`；`grant_round` 改为从 disposition 计数而非 `_budget_bonus` 扫 gate）
  - `def record_next_request(project_root, st, disposition) -> str|None`（只写「请求已发起/待发起」记录，不写业务结论；供 AC-049 可核调用）
  - `EFFECT_BY_ANSWER: dict[tuple[kind, answer_kind], EffectKind]`（一张表，I1/I2 的机器落点）
- pros：条件复核只写一次（`build_material`）；效果只写一次（`commit`）；四选项/三状态解耦；旧消费者语义不改 → 回归面小；dead 字段可只在新对象里保留所需项；重放/版本校验集中。cons：多一层映射，Material 与 Disposition 可能不同步，必须坚持「Material 每次从盘重算、Disposition 不可变追加」；`xkey` 的 S4 需要提交时现场事实，`adapt` 不能完全纯函数（用 `EffectPlan.precondition` 回调在锁内求值）。
- 具体改造点（最小侵入）：`_consume_answered_gates` 内对 `xkey-authorize` 之外的分支改为「取 disposition → adapt → commit」；`_apply_stalled_approvals/_rejections`、`_apply_review_decisions`、`_apply_reattests` 保留但由 `commit` 调用（先不改其内部）；`tick()` 的 goal 分支改为读 disposition（修 H06）。

**方案 B：各消费者保留完整事项条件与效果**
- 改动点：`_consume_answered_gates`（stage-confirm/stage-close）、`_apply_stalled_approvals`、`_apply_stalled_rejections`、`_apply_review_decisions`、`_apply_reattests`、`_consume_xkey_gate`、`_budget_bonus`/`_resume_credits` 各自实现「4 选项 × 自身条件 × 版本校验 × 重放」。
- pros：无新间接层；每个 kind 的条件与效果就地可见；不需要新模块。cons：6 个消费者 × 4 选项 = 24 条分支重复实现版本/重放/授权检查（drift 风险）；`reject` 的五种效果继续分散；后续 AC 断言要在 6 处分别证明「steer 未放行」；与 SPEC「同一事项唯一审批归属」难以机械核。
- 适用回退：仅 `xkey` S4 现场验证与 `contract_guard`（授权 gate + freeze 比对）保留在各自模块内，由 A 的 `commit` 调用，不复制其判定。

推荐：**A + B 的两处例外**（xkey 现场事实、contract_guard 冻结判定）。不冻结旧 40 字段：Material/Disposition 只列生产/消费闭环字段（E4）。

### E4 目标/授权/契约/证据版本的机械失效边界（含 40 字段生产清单）

- 生产清单（conductor 内计数，0 = 无写无读）：有生产者 = `reason_code, loop, used_rounds, round_limit, credits_used, blocker_class, default_action, authorizes(默认[]), expires_at`（`_stamp_gate_defaults`/`machine_fields`）；`answer_source, auto_policy_id`（`answer_gate_auto`）；`consumed_at, consumed_seq`（`_mark_gate_consumed`）；`status/answered_at/answered_by/note`（人答/自答）。**无写者**：`goal_sha256, goal_sha256_before, goal_sha256_after, goal_diff, roadmap_validation, verdicts_final, evidence_refs, subject_sha256, proposal_sha256, observed_at, constraints, evidence_anchor_mtime_ns, out_of_band_actions, gate_schema`。⇒ 这些必须显式标「无生产者」而不是「已满足」。
- 机械失效边界候选（sha256 集合，按 kind 冻结 pointer set，不按文件 mtime）：
  - 目标：`goal.md` 全文 sha256（替代 mtime；mtime 只作触发）。
  - 契约：`spec.md` AC 表 / `design.md` VC 块的 `contract_guard.build_freeze` ids+sha（已有）。
  - 授权：`authorizes` + `legacy_close.plan_ref` + 证明对象 sha（gate 文件 sha 已由 `evidence.gate_file_record` 记录）。
  - 实质证据：每 kind 的 terminal 指针集（`l3-verdict.txt`, `l3-report.md`, `achieved.md`, `quality-gate-report-*.md`, close dossier, xkey `dedup_key`+`old_block_sha256`+`stdout.txt` sha）。
  - 复用规则：`Material.pointer_set == Disposition.evidence_version` → 复用；不等 → 拒绝提交（`config` 事件 + gate 回 `pending`，不静默放行）。
  - 无关变化：不在 pointer set 内，或 EOL 归一后字节相等（`sha256_eol_normalized`）→ 不重开审批。
  - 并发：提交在既有 lock 内（gates/roadmap/key-{key}/xkey-ledger）；`xkey` 目标文件当前**无锁**（`apply_block_replace` 仅 `os.replace`），须补「目标文件所属 claim/独占面检查 + 目标文件锁」。

### E5 H04/H09/H10：预算来源、真实 pending/running/未知、尝试/标记/旧提案、有界恢复

- 预算来源（已核）：`config.DEFAULT_CONFIG` 无硬预算/金额/token 字段；`round_budget=2` 是每 loop 上限；`_resume_credits` = 「同 key 已 approved 的 stalled gate 数」；`_budget_bonus` = 「同 loop 存在 approved budget-exhausted」；`AUTO_NIGHT_CAP/AUTO_KEY_CAP` 只约束自动决策。未知：`worker_timeout_min` 是否被 conductor 消费（本次未追到调用点，**不写全仓无**）。
- 真实状态：
  - gates：`pending/approved/rejected` + `consumed_at`；`GateQueueUnreadable`/`GateFormatError` 区分「队列不可读」与「空」。
  - `_workers.parallel`：`_TERMINAL_STATUSES={done,failed,needs-clarification,lost}`；其余（含未知状态）一律 `_is_in_flight`；但 conductor 用 `parse_workers_file`（丢坏行）⇒ 坏行 = 隐形空闲。**建议**读侧改用 `parse_workers_queue()["unparsable"]`，把未知行当 `unknown`（阻塞 + 可核记录），而不是当空。
  - `_index.parallel`：缺失 = `[]`；claim ∈ `free/live/dead/stale`（`claim_state`）；⇒ 缺失与「全部空闲」不可区分（H09 缺口）。
  - `run.json`：`None` = 无信息（不是 idle/terminal）。
- 尝试/标记/旧提案：
  - 轮数 = worker 目录 `task.md` 的 loop/attempt 标签，**在途即计数**（`used_rounds`）；单调、重启安全。
  - 标记：`closure.write_bad_draft_marker`/`delete_bad_draft_marker`（成功或修复后清）；`xkey.proposal_exhausted_at`（人工清字段）；不存在「清标记的通用授权机制」。
  - 旧提案：roadmap-writer **整文件重写**，仅靠 rejection gate note + mtime 判新旧 → 旧提案/失败版本无不可变留存（H10/AC-033 缺口）。xkey 提案有 `proposal_attempts`+`proposal_task_key` 但旧提案被同一路径覆盖（`proposal.md`），仅 ticket 记录最后尝试。
- 有界恢复建议：恢复动作必须携 `(原因证据 sha, 动作范围, 结束判据, 预算增量=0 或显式授权 id)`；未知状态先落 `unknown` 记录再决定，不允许「未知 → 重派」。

### E6 H11/H12 受控恢复（至少两种隔离方案；明确发起者/预授权证明/原因消除/检查位置/刹车读取与受限写入/失败出口/观察与再熔断）

H11 事实：`halted` terminal rank + `_stage_activation` early return ⇒ 只能人工改 roadmap，无恢复记录、无新版本关联。H12 事实：单文件刹车、create-once、无恢复通道、`revoke` 不回滚、`AUTO_RULE_BY_KIND` 已覆盖全部 6 kind。

- **隔离方案 R1（推荐）：独立「恢复请求」生产者 + 独立消费者，物理上不在 auto pass 内**
  - 发起者：人类/PM 通过 CLI（`mw decide` 类）写 `_autopilot/recovery/<id>.md`（append-only，含 `reason_evidence_sha`, `preauth{scope, budget_delta, expires_at}`, `initiator identity`, `stop_reason_ref`）。
  - 预授权证明：项目配置**显式**的 `recovery.preauthorized: true` + 人类身份 + gate 之外的独立签名/记录（不得由 conductor 自己写）；缺 → 阻塞（fail-closed），不默认批准。
  - 原因消除：恢复文件必须引用「原因消除证据」的新 sha（例如 `auto-brake.md` 的 reason_code + 触发行的修复提交/配置 sha），并与 trip 记录比对；无对比 → 拒绝。
  - 检查位置：`tick()` 顶部、`auto_decide_gates` **之前**的独立函数 `recovery_pass()`（不是 gate kind），只读 recovery 目录与刹车文件；`auto_decide_gates` 在 active 时仍在枚举 gate 前 return（保持现状）。
  - 刹车读取与受限写入：`recovery_pass` 读 `auto_brake_path`；**唯一**允许清除 = 写 `auto-brake.clear.md`（含 recovery id + 批准记录 sha）并由 `auto_breaker_state` 识别「已清除但保留 trip 历史」；禁止 `unlink` 原始刹车（保留熔断事实）。写入范围仅 `recovery/` 与 `auto-brake.clear.md`。
  - 失败出口：清除写入失败/校验不符 → 保持 active + `config` 事件 + 一条 `escalate` ledger 行（不 bootstrap 通道）。
  - 观察与再熔断：清除后进入 `observation`（`observation_until` + `max_decisions`/`max_failures`）；窗口内再触发任一 `_auto_breaker_signal` → 写第二份刹车（`auto-brake.<n>.md`，不覆盖）并永久要求人工第二次恢复（不得同一 recovery 复用）。
- **隔离方案 R2：双钥匙 + 隔离进程（文件锁 + 独立账本）**
  - 发起者：两个独立主体（例如人 + 另一台 host 的 conductor/PM CLI）各写一份 `brake-release.<id>.key`；单份不足以解锁。
  - 预授权：项目级 `recovery_policy`（仅人工可写）声明「需 2 份、各自有效期、最大解除次数」；不设默认值（未知 → 阻塞）。
  - 检查位置：独立 `brake_recovery.py` 作为 `mw` 子命令运行（不在 conductor 进程），conductor 只在 `auto_decide_gates` 前读其结果文件；结果文件带两把 key 的 sha 与时间。
  - 受限写入：只写 `auto-brake.clear.md`；不触碰 trip 文件与 ledger 历史；`auto_decisions.jsonl` 只追加 `phase:"recovery"` 行。
  - 失败出口：key 缺失/过期/两把相同主体 → 拒绝并留 `rejected_recovery` 行。
  - 观察与再熔断：`observation` 同 R1，但再熔断需 2 把新 key（不复用旧 key）。
- **不足以证明隔离**（必须写进 AC 反例）：
  - 只给 gate 加 `brake-recovery` kind：`AUTO_RULE_BY_KIND` 若补规则，同一 `auto_decide_gates` 在 active 时先 return（不可达），解除后又会自动评审 → 等于自批；若故意不列规则，`AUTO_RULE_BY_KIND` 缺失只是「今天不评审」，不是隔离证明。
  - 只让 `revoke_auto_decision` 充当恢复：它不回滚 gate/roadmap，不改刹车，无原因消除证据。
  - 服务不可用时改用 `answer_gate_confirmed` 或直接改 gate 文件：`decision unavailable` 必须保持阻塞（AC-012/043），不得偷换通道。

### E7 AC 正向/反向/重放/并发/未知队列/授权与锁断言（AC-007～010、015～037、048/049/052）

| AC | 正向（唯一效果） | 反向/失败 | 重放 | 并发/锁 | 未知队列/授权 |
|---|---|---|---|---|---|
| 007 | approve 才 `released`；note 与理由分开存；steer/need_fix 只落 disposition+next_request | reject 无 `legacy_close` → 零状态写入；steer/need_fix 出现任何放行 = 0 | 同 gate 同 disposition 第二次 → `consumed_at` 不变、新增效果 = 0 | disposition+status 同 gates lock 内写；只读派生不持私有状态 | `authorizes` 必须被消费（retry/contract-change 各自唯一消费点）；空 = 无授权 |
| 008 | 硬检查失败 → 无有效 `released` | 缺授权/授权过期 → 0 副作用；工程取证仍受原授权 | 失败记录不消费答案（gate 仍 pending） | 读取授权失败按 fail-closed（不默认） | `not-bound`/`corrupt-sidecar`/`replay-misbound` 三态必须可区分 |
| 009 | 相位门失败 → dp-auto 处置记录 + 未解决项保留 | 未重过硬门而相位推进 = 0 | 同门失败同证据 → 同事项不双批 | 处置记录与 advance 结果分离 | 门判据不被改写（compare sha） |
| 010 | stage close 只在 5 条事实齐 + 授权内 approve | done 计数/key 签收代证 → 0；未披露未完成 → 0 | 关闭后 replay 不再开下一 gate | `roadmap` lock + monotonic guard | 必需 key 缺签收/凭证 → 关闭 0 |
| 015–019 | 首个/后续 stage 同规则 1 次判断；缺工程证据补证后再判；授权内不逐 stage 找人 | 缺意图/越权 → 0 启动；硬检查失败 → 0；goal/stage/授权实质变化 → 旧批准不放行 | 同事项同证据版本重复 → 0 额外审批 | gates lock + create-once | 缺 goal 授权 → 具体问人（不推断） |
| 020/021 | 有授权 + 真进展 + 结束判据 → 恰 1 轮；硬预算内 | 无授权/无依据 → 0；硬预算余量不自动批准；越界投入 = 0 | bonus 只发放一次（attempt 记录） | disposition 计数替代 `_budget_bonus` 扫 gate | 预算/授权未设置 → 显式 unknown，不代设值 |
| 022/023 | 到期/事件只触发复核；条件满足才 approve 恢复 | 触发≠恢复；reject 不映射返工 | 复核事件去重（gate+trigger） | 状态写在 roadmap lock | 无依据恢复 = 0；复用有效质量证据 |
| 024/025 | 仅 disposition=approve 且 goal sha=指定版本才采用 | reject/steer/need_fix 不采用、不刷 baseline；纯文件变化 = 0 采用 | 同 goal 版本重放不重复采用 | goal 只读 + 记录版本 | 受影响 key/验收/授权 → 旧批准失效（sha 集合不等） |
| 026/027 | 限定 key/文件/动作 + 授权有效 → 单执行者 | 越权/开放范围 = 0；DP 不抢 claim | 同 request 重放 → 0 重复写 | claim + 独占面 + 目标文件锁 | 项目写面≠跨 key 写权；未声明 → 拒绝 |
| 028/029 | 限定 AC/VC 变更 + 受影响重验 | 未授权删减/伪造完成 = 0；QG reopen 不授改权 | 同 freeze 版本重放不重复批准 | freeze 写一次；gates lock | 旧要求/失败历史保留（字节不变） |
| 030/031 | 核实 pending/running/未知/尝试/产物/预算后受控重派 | 未知/冲突在途时重派 = 0；清标记绕限 = 0 | 重派有界（attempt/loop 记录） | workers/roadmap lock | `parse_workers_queue` 的 `unparsable` 必须进入判断（不能当空） |
| 032/033 | 实质修订 + 预算/结束判据内重规划 | 无限相似提案 = 0；越权 = 0；重规划不授新权/不启新 stage | 旧提案/拒绝/失败保留版本（不可变） | 提案版本 append-only | 缺目标/优先级/权限 → 具体问人 |
| 034/035 | 有原因消除证据 + 授权 + 硬检查 → 限定恢复 | 抹历史/重置消耗 = 0；人工停止未授权 → 0 解除；其他选项不冒充已恢复 | 恢复记录关联原停止（不删文件） | 恢复写入与 roadmap 写分离、各自 lock | 授权证明缺失 → 阻塞；硬保护不可绕过 |
| 036/037 | R1/R2 隔离通道 + 预授权 + 观察窗口 → 限定恢复 | 熔断链自批 = 0；`decision unavailable` 默认批准 = 0；越能力/预算恢复 = 0 | 同一 recovery 不可复用于第二次熔断 | 刹车只经受限写入清除，trip 文件不删 | 无预授权 → 具体问人；reject 不关项目 |
| 048 | stalled 送审含原因/真实状态/尝试/产物/余预算/下一方案/结束判据 | 缺证据放行 = 0；预算剩余单独放行 = 0 | 同停滞状态重复送审 → 1 次 | gate+disposition 分离 | 预算 unknown 显式化，不当 0 |
| 049 | steer/need_fix 后 PM 在材料/角色/授权齐且无在途时发起对应请求，调用证据可核 | 未发起/调用失败/返回选择 → 不得推断整改；重复请求 = 0；本 gate 因此放行 = 0 | 同事项后继请求去重 | 请求记录与业务结论分离 | 角色越权（Worker 调 PM 专属） = 0 |
| 052 | 同事项同证据版本 → 复用，不重复动作 | 实质变化 → 旧批准不放行 + 重验；纯排版/无关材料 → 0 重复审批 | `(kind, subject key, evidence_version)` 幂等键 | 双 Worker 同文件/绕锁写 = 0（含 xkey 目标文件） | 版本不可计算 → 拒绝（不是放行） |

### E8 越界与禁止声明

- 未运行测试/CLI 裁决/provider/服务探针；未起停服务；未读活 config/gate/ledger/roadmap/刹车/凭证/其他 key 运行材料；未改源码、配置、预算授权、状态、旧研究或 PM 文档；未恢复任何真实对象。
- 结论全部来自本次静态读；RQ14 对 `gates.py`/`contract_guard.py` 的观察只作沿用（本次仅定向复核 gates 常量/authorizes 解析，contract_guard 仅 grep），已标注「未新核」。

## 残留与未验证

- 未全文读：`dispatch.py`(106KB)、`roadmap.py`、`evidence.py`、`timeline.py`、`write_face.py`、`task_graph.py`、`closure.py`、`audit_evidence.py`、`index_parallel.py`、`review_split.py`、`card_audit.py`；未读 AgenticTask 框架 `advance_phase.py` 本体；未读 TS 扩展（gate-writer/status-model/pm 面板）与 cross-language 40 名镜像测试。
- 未验证安装身份/服务进程/真实 project 的 config、gate 队列、ledger、roadmap、刹车文件、凭证；未验证运行行为与任何 AC；未验证 `worker_timeout_min` 是否被 conductor 或 dispatch 消费（本次 0 命中，按「未找到字段」处理，不写「全仓没有」）。
- 未确定项：S1/S2 结构选择、A/B 方案批准、Material/Disposition 字段表、pointer set 精确清单、恢复预授权数值与观察窗口、`authorizes.retry` 的消费语义 —— 均待联合设计与用户授权；本文件不构成批准，也不冻结旧 40 字段。
- 未处理：`_workers.parallel` 坏行改读 `parse_workers_queue` 的兼容影响、`_index.parallel` 缺失与空目录区分、xkey 目标文件锁与 claim 检查的精确落点。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/tasks/RQ19-design-conductor-full-read.md`
- 锁定 SPEC：`.agenticdoc/mw-dp-consolidation/spec.md`（§1.2 H01–H13、§1.6 映射、§3 AC-001～053）
- 项目目标：`.agenticdoc/goal.md:5`
- 本次全文读源码：`packages/multi-workers/autopilot/conductor.py`（1–8727）、`xkey.py`（1–1435）、`config.py`（1–264）、`advance.py`、`effective_config.py`
- 定向读：`packages/multi-workers/autopilot/gates.py`（GATE_KINDS/GATE_STATUSES/FRONTMATTER_FIELDS/AUTHORIZES_ACTIONS/authorizes 解析）、`state.py`（read_index/claim_state/used_rounds）、`packages/multi-workers/mw_common.py`（_TERMINAL_STATUSES/parse_workers_file/parse_workers_queue/read_run_status）
- 沿用未新核：`packages/multi-workers/autopilot/contract_guard.py`（grep：`gate_authorizes_contract_change`、`CONTRACT_CHANGE_ACTION`）；RQ14 报告 `.agenticdoc/mw-dp-consolidation/evidence/research/design-autopilot-effects-20261026.md` 的 gates/contract_guard 观察
- 本证据完整路径：`.agenticdoc/mw-dp-consolidation/evidence/research/design-conductor-full-read-20261026.md`（key 内等价路径 `evidence/research/design-conductor-full-read-20261026.md`）
