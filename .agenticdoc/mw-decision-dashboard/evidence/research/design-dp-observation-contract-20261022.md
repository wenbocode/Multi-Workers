# Research: 全 25 DP 业务输入契约 + 人工观察调用隔离

key: mw-decision-dashboard（D-RQ3）｜只读设计，未改任何代码/配置/档案，未发起真实模型调用
spec: AC-004/008/009/010/011/017（`.agenticdoc/mw-decision-dashboard/spec.md:1`，17 AC 锁定）

## 结论

1. 21 个 DP（dp4..dp24）的 `required_state_fields` 为空不是"文档缺字段"，而是**可执行的虚测通道**：`scaffold_book(dp4)` 只产出 `schema_version/decision_point/questions_version` 三个身份键，`check_book()` 返回 0 issue（本次实测，见下"实测"），即一本"零业务事实"的决策本能通过全部校验并送入真实模型。AC-009 当前不成立。
2. 单点修复不能只往 registry 塞字段：`_missing_required()` 是**硬门**（缺字段→`input-incomplete`，零 HTTP），而现有测试就用 `decide_for("dp4-failure-handling", {"key":"k"})` 这种身份态调用（`test_decision_points.py:1153`）。加必填字段＝改变 `decide_for` 结果，必须同时迁移调用方与生成物。
3. 推荐 **A 为主 + B 只做非决策散文**：业务事实必须是 `required_state_fields`（有类型、有 evidence、超预算拒绝发送）；现有 `context` 槽位保持"可整槽丢弃的散文"（`decision_context.fit_context` 按 `SLOT_CUT_ORDER` 整槽删），把业务事实放进 context 会让模型在**静默缺失事实**上作答。
4. A 需要新增 registry 的**可选业务字段闭集**：dp2 的生产者已经在发 `progress.writes/uniq_targets/repeat_top/trend/last_land_age_min`（`pm-orchestrator.ts:2140-2168`），而决策本闭集把它们判为 `book-state state.progress.writes: not in required_state_fields`（本次实测）。今天"可选字段"只存在于 `OPTIONAL_STATE_PATHS` 硬编码元组（`decision_points.py:1305`），registry 无第二份声明 → 单一权威被破坏。
5. 人工观察调用**不需要新链路**：`decide_for(..., intent="answer", archive=False)` 已经天然不写档案、不跑 executor（step 9 分支，`decision_points.py:2558`）。观察入口只需一个**成对强约束**的 `observation` 参数来跳过 step 2 的 `enabled` 短路并记录授权判定；推荐"decide_for 内部 seam"，不推荐应用层直连 `DecisionClient`。
6. 全局 `enabled=false` 仍必须禁止发送：它是运维的付费/流量 kill switch（`decision.py:351,854`），只应被"DP 级授权"例外（关闭/P0 DP），不应被"页面提交"例外。缺口时页面给配置方法，不自动开。
7. 独立 test record 必须以 `call_id`（每次发送唯一）为主键，**不能**复用 `decision_id`（生产按 `decision_id` 去重，`decide_archive.py:976-1021`）；每次提交前后比对授权表/decisions.jsonl/signoff/book-receipts 的 sha256，失败即标 `isolation=violated`。

## 出处（path:line，全部本次实读）

- `packages/multi-workers/decision_points.py:110` `MAX_STATE_BYTES=2000`；`:1131-1188` 只有 dp1/dp2/dp3/dp25 四条 `REQUIRED_STATE_FIELDS`；`:1305` 硬编码 `OPTIONAL_STATE_PATHS`；`:1315` `TRUNCATABLE_STATE_PATHS`。
- `decision_points.py:2278-2295` `decide_for` 签名（`archive: bool = True`, `intent="act"`）；`:2330-2347` step2 `enabled` 短路（build_state 之前返回，零网络）；`:2378-2422` step5 必填门（`_missing_required`）；`:2424-2438` step6 2000B；`:2440-2443` step7 唯一一次传输；`:2481-2519` step8 输入侧；`:2520-2557` confidence 门（仅 `api` 源）；`:2558-2597` step9 `mode=suggest or intent=="answer"` → 不执行；`:2599-2722` step10/11 executor。
- `decision_points.py:160-171` `ESCALATED_REASONS` 含 `"p0"`，但全仓无写入者：P0 只靠 `default_enabled=False`（`:382-383`）被 step2 拦；P0 行若被人为 enable，且 `executor=None`，流程会**真的发一次网络请求**再以 `over-authority` 落档（`:2599-2620`）。
- `decision_book.py:53-58` `STRUCTURAL_STATE_FIELDS` 三身份键；`:615-671` `_check_state_closed`（缺必填 + 多键双报）；`:848-888` `_check_evidence`（每个必填字段必须有 `notes.evidence[path]`，且 evidence 键只能是必填字段或允许的 context 槽）；`:703` 占位符拒绝；`:362-397` `scaffold_book`；`:139` `RECEIPTS_RELATIVE_PATH=.agenticdoc/_autopilot/book-receipts.jsonl`。
- `decision_context.py:1-30`（state 携带决策字段、context 是可选环境散文，4000B）；`:70-120` `CONTEXT_SLOTS`（5 槽，仅 dp1/dp2/dp3/dp4/dp6/dp7 有 producer）；`:197-224` `fit_context` 整槽丢弃。
- `mw.py:911-1012` `_decide_run`：`--book` → `_book_gate` → `decide_for(intent="answer")`（`archive` 默认 True）→ `_book_receipt`；`:1499-1530` `_book_gate`（先验后发，失败 exit 2 零 HTTP）；`:1631-1690` `_decide_ask`（`cfg.unconfigured` 时 `cfg.enabled = True`，CLI 人工输入即 opt-in；`enabled=false` 仍赢）。
- `decision.py:344-390` `DecisionConfig`（`enabled: bool = False`、`is_configured`）；`:518-554` `_redact`/`_scrub_detail`；`:854-870` client 侧 disabled → `REASON_DISABLED`；`decision_backends.py:169-205` `resolve_timi_api_key`/`credential_status`。
- `decide_signoff.py:287-340` `collect()`（读 decisions.jsonl + `.mw/decide-points.json`，排除 dp25 自身行，算 rows/available/engine/`rows_sha256`/`chain_ok`/`p0_open`）；`:270-286` `_p0_open`（读表，不写）。
- `decide_archive.py:39` 档案路径；`:91-130` 行字段（无原始 request/response，无 call 级 id）；`:948-1021` `append_decide`（`dedupe_decision_id`，`duplicate="raise"|"existing"`）。
- `scripts/gen_decide_registry_ts.py:1-40,105-140`：生成 `shared/decide-registry.generated.ts`（`requiredStateFields`+`contextSlots`），`--check` 字节锁 `test_decide_registry_ts_lock.py:13-27`；`test_decide_registry_export.py:1-30` 锁 `decide_registry.json` 与 hand-written wiring。
- `pm/ui-bridge.ts:463-495` `assertStateMatchesRegistry`（缺必填/顶层多键/context 槽白名单都 throw）；`:521-600` dp1 state 构造 + `task_excerpt` 余量；`pm/pm-orchestrator.ts:2140-2204` dp2 state（含可选 L1 `progress.writes/trend`）；`worker/worker-mode.ts:4935-4960` dp3（本地候选、answerable/confidence 阈值）。
- 实测（本次只读执行，未联网）：`scaffold_book(dp4..dp24)` 均 3 键、`check_book` 0 issue；`dp2` state 追加 `progress.writes` → `book-state state.progress.writes: not in required_state_fields (closed key set)`。

## 现状硬约束（设计前提，非建议）

- 生产校验权威只有两处：Python `_missing_required`（硬门，缺字段零 HTTP）与 TS `assertStateMatchesRegistry`（producer 侧 throw）；决策本侧是第三处 `_check_state_closed`（闭集更严：只认必填 ∪ 三身份）。
- 业务事实一旦进 `context` 槽：无类型校验（只校验 shape）、可被 `fit_context` 整槽丢弃、不必给 evidence、不进 `state_digest` 的必填语义 → 不能满足 AC-009 的"类型/说明/错误字段被拒绝"。
- P0 不是"永不发送"的机制，只是默认 disabled；观察页不能声称"P0 不发网络"，只能展示**按当前表算出的** would-verdict。

## 25 DP 字段矩阵（现状 → 建议最小业务输入 → 声明/影响）

约定：`s`=string `i`=integer `b`=boolean `a`=array。每个字段的 evidence 必须是 `path:line` 或命令原文（`decision_book.py:848` 已强制）；身份三键由骨架预填，不计业务字段。"待设计"= 无生产生产者（`wired=false`/`executor=none`），字段为设计推断，**未验证**。

| DP | 现状（question / 字段数） | 建议最小业务输入（类型；区分选项的判据） | 声明 / 影响 |
|---|---|---|---|
| dp1-dispatch-type | triage_type+triage_risk；13 字段 | 现有即最小：task_type/requested_type/risk/risk_source/authority_tier/task_summary/scope.write_scope/scope.file_extensions | 证实（ui-bridge.ts:521 生产者+解析）；不改 production validator/TS 镜像 |
| dp2-checkpoint-split | checkpoint_action(narrow/split/direct-exec/escalate)；14 字段 | 现有 5 个 progress 字段已够；**补可选闭集**：progress.writes(i)/uniq_targets(i)/repeat_top(a)/trend(a)/last_land_age_min(i) | 证实+缺口；影响 book 闭集与 `_fit_state` 硬编码；TS 已发，生成物需重出 |
| dp3-worker-clarify | answer_kind / answerable(noul) / candidate(动态)；13 字段 | 现有：ambiguity.kind/ambiguity.question/local_candidates | 证实（worker-mode.ts:4954 生产者）；不改 |
| dp4-failure-handling | failure_action(retry/rework/escalate)；0 | failure.kind(s:transient\|deterministic\|infra\|unknown)、failure.attempt(i)、failure.limit(i)、failure.artifact_present(b) | 待设计；新增必填→`input-incomplete` 语义变化，须迁移 `test_decision_points.py:1153,1190,1282` |
| dp5-test-triage | test_category(baseline-env/flaky/regression/unknown)；0 | test.failed_cases(a)、test.baseline_cases(a)、test.changed_paths(a)、test.repro_consistent(b) | 待设计；同上（`test_decide_dp_cli` 等引用处需迁移） |
| dp6-qg-verdict | qg_verdict(pass/fix/reopen)；0 | qg.checks_total(i)、qg.checks_failed(a)、qg.blocking(a)、qg.scope(s:impl\|spec) | 待设计；新增必填 |
| dp7-gate-failure | gate_cause(missing-evidence/stale-verdict/config/unknown)；0 | gate.name(s)、gate.missing_items(a)、gate.verdict_age_hours(i)、gate.has_config_error(b) | 待设计；新增必填 |
| dp8-scope-change | scope_decision(keep/narrow/expand)+scope_reason；0 | scope.requested_paths(a)、scope.write_scope(a)、scope.cross_key_conflicts(a)、scope.requirement_delta(s) | 待设计；新增必填；命中 write-face 守卫语义（ui-bridge.ts:2164） |
| dp9-model-select | model_class(primary/fallback/degrade)；0 | model.requested(s)、model.available(a)、model.transport_status(s:ok\|rate-limited\|unavailable) | 待设计；新增必填 |
| dp10-dependency | dependency_decision(upgrade/hold/pin)；0 | dependency.name(s)、dependency.current(s)、dependency.target(s)、dependency.breaking(b)、dependency.reviewed(b) | 待设计；新增必填 |
| dp11-credential | credential_action(isolate/rotate/deny)；0 | credential.provider(s)、credential.kind(s)、credential.exposed_to(a)、credential.scope(s)（**永不收凭据值**） | 待设计；新增必填；与 GC-3 一致（值是禁收项，不是可选） |
| dp12-destructive | destructive_action(proceed/block/ask-human)；0 | action.command(s, 脱敏)、action.targets(a)、action.reversible(b)、action.backup_available(b) | 待设计；新增必填 |
| dp13-commit-release | release_action(commit/version-bump/publish/hold)；0 | release.version_current(s)、release.version_next(s)、release.staged_paths(a)、release.changelog_ready(b)、release.ci_green(b) | 待设计；新增必填；P0/P1 复合 tier 不因字段解决 |
| dp14-rule-conflict | conflict_resolution(follow-rule/follow-instruction/ask-human)；0 | conflict.user_instruction(s)、conflict.rule_ref(s)、conflict.rule_strength(s:hard\|advisory)、conflict.irreversible(b) | 待设计；新增必填 |
| dp15-autopilot-gate | gate_decision(continue/narrow/revoke)；0 | gate.kind(s:6 类)、gate.pending_items(a)、gate.age_minutes(i)、gate.evidence_refs(a) | 待设计；新增必填 |
| dp16-goal | goal_decision(keep/amend/defer)；0 | goal.current_digest(s)、goal.proposed_delta(s)、goal.alignment(s:aligned\|drift\|conflict) | 待设计；新增必填 |
| dp17-spec-lock | spec_lock(lock/reopen/amend)；0 | spec.ac_ids(a)、spec.ac_changed(a)、spec.open_questions(a) | 待设计；新增必填 |
| dp18-claim | claim_conflict(wait/steal/new-key)；0 | claim.key(s)、claim.owner(s)、claim.heartbeat_age_min(i)、claim.owner_active(b) | 待设计；新增必填 |
| dp19-foreign-write | write_decision(allow/deny/redirect)；0 | write.target_path(s)、write.write_scope(a)、write.foreign_paths(a)、write.cross_key_owner(s)、write.allow_foreign_write(b) | 待设计；新增必填 |
| dp20-stage-close | stage_action(close/hold/rework)；0 | stage.id(s)、stage.tasks_done(i)、stage.tasks_total(i)、stage.open_blockers(a)、stage.evidence_refs(a) | 待设计；新增必填 |
| dp21-refine | refine_decision(accept/defer/reject)；0 | refine.clause(s)、refine.impact_paths(a)、refine.reversible(b) | 待设计；新增必填；`would_action` 只能是标签（executor 未接线） |
| dp22-debug-plan | debug_plan(hypothesis-first/repro-first/rollback)；0 | debug.signal(s)、debug.repro_available(b)、debug.last_green_ref(s)、debug.change_scope(a) | 待设计；新增必填 |
| dp23-snapshot | snapshot_decision(write/defer/skip)；0 | snapshot.size_bytes(i)、snapshot.delta_bytes(i)、snapshot.sections_changed(a) | 待设计；新增必填 |
| dp24-pi-trust | trust_decision(trust-once/trust-always/deny)；0 | project.path(s)、project.trust_state(s:untrusted\|trusted)、project.origin(s:user\|clone\|foreign)、project.pending_changes(b) | 待设计；新增必填 |
| dp25-signoff-conclusion | q-conclusion(continue/narrow/revoke)；5 字段 | 现有：key/rows_total/rows_available/chain_ok/p0_open | 证实（decide_signoff.collect 是生产者）；不改 |

影响面统一说明：新增必填 → `registry_snapshot()` 变 → `decide_registry.json`（`mw decide dp export --write`，`test_decide_registry_export.py` 字节锁）与 `shared/decide-registry.generated.ts`（`gen_decide_registry_ts.py`，`test_decide_registry_ts_lock.py` 字节锁）必须重出；`assertStateMatchesRegistry` 与 `_check_state_closed` 自动收紧；**唯一的行为风险**是身份态调用者（测试/脚本/未来 CLI）从"发送"变成"input-incomplete"，必须逐个迁移而不是放宽门。新增可选业务字段还需要三处配套（否则不可用）：registry 新键 → snapshot → 两处生成物；`_check_state_closed` 允许可选键；`_check_evidence` 允许"可选键的证据可给可不给"；`OPTIONAL_STATE_PATHS` 由 registry 派生（否则又是一份硬编码）。

## 两案比较：A（registry 必填+可选闭集） vs B（统一受控 context）

A｜registry 扩 `required_state_fields` + 新增 `optional_state_fields`
- pros：唯一权威（registry→两处生成物→两处校验器，已有字节锁）；业务事实有类型/说明/evidence/超预算拒绝；未知键与类型错误必然被拒（AC-009 逐字满足）；可选字段可声明上限并按声明顺序参与 `_fit_state`。
- cons：动生成物与调用方迁移；必填会让"身份态调用"变 `input-incomplete`；25 个 DP 的字段语义要长期维护；新字段在没有生产者前违反 P-005（字段必须同时有写者/读者），所以只能分批落地。

B｜把业务输入统一挪进 `context`（复用 5 槽/4000B/白名单）
- pros：零 registry 结构变更、生成物不用动、book 骨架立刻"有内容"；截断有统一 marker。
- cons：`context` 无类型校验（只 shape）、可被整槽丢弃（`fit_context` 丢的是整槽，模型看到的是**缺失而非缺失标记**）、不必给 evidence、不参与 `_missing_required` → 一个缺 `test.baseline_cases` 的调用照样成功；槽位表只有 5 个通用槽，21 个 DP 的业务事实无处安放（要么语义串味，要么扩槽表，最终仍要一份 typed 表）；AC-009 的"未知/类型错误字段被拒绝"无法实现（context 只校验槽名与 char 上限）。
- 结论：B 单独不可行；B 保留为"散文/摘录"层（现状已如此），业务事实走 A。

## 人工观察调用设计（复用真实链路，仅观察）

调用序（monitor 服务端，人工显式提交后执行一次）：
1. `decision_book.load_book(path)` + `check_book(...)`：非法本 → 列 issue、零 HTTP（复用 `mw.py:1499 _book_gate`，**不**复用 `_book_receipt`）。
2. `load_points_config(project)` 只读取 `effective(dp)`（enabled/mode/source/tier），仅记录，不改表。
3. `DecisionConfig.from_project(project)`：`cfg.is_configured == False` → 直接 `transport-unavailable`，零发送（`decision.py:854` 同源判定）。
4. `DecisionClient(cfg, project_root=project)`（不改 cfg.enabled）。
5. `decide_for(dp, trigger, project, client=client, archive=False, intent="answer", observation=Observation(observe_only=True))`。
   - 入口成对约束：`observation is not None` 时要求 `intent=="answer"` 且 `archive is False`，否则 `DecisionInputError`（fail-closed，防误配成"观察+落档"）。
   - step2：`enabled` 为假且无 observation → 现状不变（`disabled`，零网络）；有 observation → 继续，但 `authorization.bypassed=true` 与 `source/layer` 一并入记录。
   - step3-8：真实执行（mode、传输、必填、2000B、答案合法性、confidence）。
   - step9：真实（`archive=False` 不落任何行；`intent="answer"` 不跑 executor）。
   - 新增产物：`preview.would_status/would_escalated_reason/would_act/would_action_label`，由**同一模块**按生产顺序算出（关闭→escalated/disabled；mode=suggest→suggested；executor None→escalated/over-authority；unwired→escalated/over-authority；否则 acted+标签）。P0 行被人为 enable 时 would 也是"会发请求+over-authority"，不美化。
6. 写独立 test record（下方接口）；任何写失败 → 结果标 `record-failed`，绝不回写生产。

门表（**谁执行**：全部由 `decision_points`/`decision_book` 执行；monitor 只组装与渲染）：

| 门 | 观察调用 | 生产 | 说明 |
|---|---|---|---|
| G1 dp 已注册 | 真 | 真 | unknown → `DecisionInputError` |
| G2 book schema/闭集/类型/占位/evidence/预算/密钥 | 真 | 真 | 同 `check_book` |
| G3 每 DP enabled/P0 | **仅预览** | 真（step2 零网络） | 观察不短路，只记录 |
| G4 mode auto/suggest | **仅预览** | 真 | 决定 `would_act` |
| G5 全局 transport enabled/configured + 凭证 | 真 | 真 | 关闭/缺凭证 → 零发送 |
| G6 必填字段 + 2000B | 真 | 真 | 观察也拒绝虚测本 |
| G7 答案合法性 / api confidence 地板 | 真（判"这次回答是否可用"）+ 预览（是否升级） | 真 | 记录 answer 与 would 升级原因 |
| G8 executor | **永不** | 真 | dp25 echo / dp21-24 unwired raise |
| G9 生产档案/book 回执/signoff | **永不** | 真 | 由 `archive=False` 与不调用 receipt 保证 |

## 观察入口两案：decide_for 内部 seam vs 应用层直连 client

案 1（推荐）｜`decide_for(observation=...)` 内部 seam
- pros：门顺序、阈值、state 组装、size 收缩、答案合法性只有一份实现（preview 与生产不可能漂移）；`archive=False`+`intent="answer"` 已有等价语义，改动面是"一个参数+一个分支"；TS/CLI 调用方零改动（默认 None）；可直接对 25 DP 做表驱动 parity 测试。
- cons：生产函数多一个非生产参数（误用风险，用成对约束 fail-closed 兜）；`observation` 需要进入签名文档与 CLI 拒绝面（monitor 之外不得传）。

案 2｜应用层独立调用 `DecisionClient.decide()`，自己算采纳判定
- pros：生产 `decide_for` 字节不变；测试路径天然隔离，AC-008 易证。
- cons：必须复刻 G3/G4/G6/G7 的顺序与阈值，否则会出现"预览说 would-act、生产 escalated"的双口径（正是 P-018/P-019 的契约漂移）；`mw decide ask` 那种"直连 client"路径还要自己补授权与必填门；实际会逼出"把判定抽成纯函数"，与案 1 收敛但多一层。
- 结论：案 1；不采用"临时把 enabled 写 true/写临时表"（违反 AC-010 的授权表字节不变）。

## 独立 test record 接口（只定义属性与语义，不定义事件 schema；schema 归 D-RQ2）

- 落盘：`.mw/decide-test/calls.jsonl`（新文件，独立锁 + 原子发布）；**不写** `.agenticdoc/_autopilot/decisions.jsonl`、不写 `book-receipts.jsonl`、不写 signoff。
- 主键 `call_id`（ULID，每次**实际发送**唯一）；`attempt_group_id`（同一提交意图）；`retry_of`（失败重试指向上一 call_id）。`decision_id` 只作关联字段，**不得**作幂等键（生产按它去重：`decide_archive.py:976-1021`）。
- 行字段：`call_id, attempt_group_id, retry_of, dp, key, tier, questions_version, book{path,file_sha256}, state_digest, mode_effective, enabled_effective, authorization{source,layer,bypassed}, request{questions_ref,state_ref,capture_status}, response{available,reason,answers,confidence,confidence_source,model,transport,attempts,latency_ms}, preview{would_status,would_escalated_reason,would_act,would_action_label,executor_invoked:false}, outcome, isolation{...}, ts`。
- 生命周期两行：`phase=start` 在发送前落（含 call_id），`phase=finish` 落结果；读侧按 call_id 折叠 → 进程崩溃/超时也留下"确实发过"的事实。`capture_status ∈ ok|truncated|failed`（脱敏/截断必须显式，沿用 `decision._redact`）。
- `outcome ∈ ok|bad-response|transport-unavailable|credential-missing|upstream-error|timeout|rejected-zero-call|record-failed`；`rejected-zero-call` 必须附 `issues[]`（`check_book` 原文）。

### 重复点击/重试/超时

- 重复点击：同一 `attempt_group_id` + 同一 UI submit token 的第二次点击 → 零调用，记 `suppressed=duplicate-click`（UI 防抖是 UI 的事，事实必须留痕；AC-012 的调用计数与决策幂等分离）。
- 重试：失败后人工点重试 → 新 `call_id` + `retry_of`，两行都可见；`attempts` 是**传输层**重试次数（`DecisionClient.max_retries`），不产生新 call_id。
- 超时：`outcome=timeout`、`response=none`、`capture_status=failed`；不得写"成功"，不得补答案。

### disabled transport / 缺凭证

- 无 `.mw/decide.json` 或 `enabled=false`：`outcome=transport-unavailable`（reason=`disabled`），零发送、零答案、页面给配置路径与片段，**不**自动 enable（见下节）。
- 缺凭证：`credential_status()` 报 `missing` → 同类失败（`credential-missing`），零发送；凭证值永不出现在记录/页面/证据（只记 provider/kind/是否存在）。

### 签收隔离验证（AC-008）

每次提交前后各取一次 sha256+size：`.mw/decide-points.json`、`.agenticdoc/_autopilot/decisions.jsonl`、`.agenticdoc/_autopilot/book-receipts.jsonl`、目标 key 的 signoff 文件；并调用 `decide_signoff.collect(project,key)` 比对 `rows_total/rows_available/rows_sha256/chain_ok`。任一不等 → `isolation=violated` 并在页面红显；相等 → `isolation=ok`。只用 collect 的折叠值做"生产计数不变"的硬证，避免只比文件却漏掉语义。

### worker 不可用验证

- 模型/传输侧不可用：`outcome=transport-unavailable|upstream-error`，带 `attempts/latency_ms/reason`，零答案。
- 任务上下文不可用（无 worker/task dir、无 trace/日志可取证）：状态事实无法产出 → `outcome=rejected-zero-call` + `missing required state fields: ...`（与生产同一条 `_missing_required` 文案）；页面不得用 `-1/false/[]` 顶替事实（占位符会被 `check_book` 拒，但 UI 自己也不许填）。

## 全局 disabled：仍禁止发送（推荐）

- 推荐：`.mw/decide.json` 的 `enabled=false`（含缺失）**仍然零发送**，观察入口只绕过 G3（DP 级授权），不绕过 G5。理由：
  1. 它是运维写下的成本/流量 kill switch（`decision.py:351,854`）；浏览器页面能绕过它，等于开了一条不留痕的付费请求通道，与 AC-015（只有显式授权来源可发）和 GC-3 冲突。
  2. spec 的"仅观察"例外原文只针对"关闭或 P0 DP"（AC-010），没有给"全局传输开关"例外；擅自扩大例外＝范围变更。
  3. 自动 enable 会制造"页面全绿、生产全拒"的假象，正是 RQ-2 记录的"mode/available 被当成执行"的同类错误。
- 反例辨析：`mw decide ask` 在 `unconfigured` 时 `cfg.enabled=True`（`mw.py:1651-1658`）是"人工在 CLI 亲手敲命令"的先例；页面提交是本地 HTTP POST，不能自带同等权威 → 观察路径要求"已配置"，未配置时给 `.mw/decide.json` 片段由人创建。
- 若 PM 最终决定允许例外，最小形态是：仅 `unconfigured`（无文件）且记录 `authorization.transport_bypassed=true`，仍不得覆盖显式 `enabled=false`——但本报告不建议。

## 与 D-RQ2 的边界（不抢 schema）

- D-RQ2 拥有：原始请求/响应采集点、事件 schema、关联 ID 命名、脱敏字段清单、吸收/应答记录、传输边界实现。
- 本卡拥有：每 DP 的字段契约与 registry/生成物影响、观察调用的门语义与 preview 判定归属、test record 的**必备属性**（call_id 稳定、start/finish 两行、capture_status、outcome 枚举、isolation 快照）与隔离不变量。
- 交界：test record 只存 `request_ref/response_ref + capture_status`，不复制 raw；`call_id` 必须能被 D-RQ2 的传输事件反向引用（1:N）。字段名若与事件 schema 冲突，以 D-RQ2 为准并只改引用名。

## VC（后续可执行，当前未执行）

- VC-1（AC-009 正）：25 个 dp 的 `scaffold_book` 业务键 ≥3 且"全字段合法填写"的 `check_book` = 0 issue；删任一必填路径 → 恰一条 `book-state missing`。
- VC-2（AC-009 负）：dp4..dp24 身份态本 → `check_book` ≥1 issue、client 计数 0（拒绝先于发送）。
- VC-3（AC-010）：观察提交 disabled/P0 合法本 → 1 次真实调用、`bypass_observe_only=true`、`executor_invoked=false`；随后生产 `decide_for` 同 dp → `escalated/disabled` 且 client 计数 0；授权表 sha256 前后相等。
- VC-4（AC-008）：N 次测试提交后 `collect()` 的 rows_total/rows_available/rows_sha256/chain_ok 与 book-receipts 文件字节均不变。
- VC-5（AC-012）：同 submit token 两次 → 1 发送 + 1 `suppressed=duplicate-click`；强制超时后重试 → 2 个 call_id、`retry_of` 串联、计数 2。
- VC-6（AC-011）：非法本（未知键/错类型/占位符）→ 零 HTTP、`rejected-zero-call`、issues 原文；transport disabled / 缺凭证 → 零 HTTP、对应 outcome、无 `answers` 键。
- VC-7（AC-017/015）：无访问凭据的外部请求 → 零调用；提交夹带 `executor`/`on|off|set|apply` 参数 → 拒绝且零写入。
- VC-8（漂移）：registry 变更后 `gen_decide_registry_ts.py --check` 与 `mw decide dp export --write` diff 为空；`assertStateMatchesRegistry` 接受新字段 producer 态。
- VC-9（preview parity）：25 DP 表驱动，同一 state+answers 下 `preview.would_status/would_escalated_reason` == 该 dp 被 enable 后的生产 `decide_for` status/escalated_reason（FakeBackend，无网络）。

## 风险与未覆盖

1. dp4..dp24 字段是**设计推断**：无生产者、无调用点，P-005 意义上"字段无写者/读者"；未经真实 call site 验证不得标为已证实。
2. 2000B 预算与数组字段冲突：dp5/dp15/dp19/dp20 的 `a` 字段在真实规模下可能超限，`_fit_state` 只会丢硬编码 optional 路径 → 需要 per-field 上限/截断策略（本卡未设计）。
3. `optional_state_fields` 会引入第三类键（必填/可选/context），三处校验器（`_missing_required`、`_check_state_closed`、`assertStateMatchesRegistry`）必须同源，否则又是双口径。
4. 全局 disabled 若被 PM 判为可绕过，需要用户级确认（属范围变更），本报告不预置实现路径。
5. 并发隔离：其他 session 同期写 decisions.jsonl 时全文件 sha256 会变，`isolation` 需按 key/seq 归属判定或持锁比对，当前设计只给"文件级+collect 级"两层，未覆盖并发写归因。
6. P0 语义缺口：`escalated_reason="p0"` 是冻结值但无写入者；若未来有人 enable P0 行，生产会真的发送并落档——观察页会如实展示该 would，但"P0 永不自发"的假设本身未被代码保证。

## 勘误（写入后自查）

- 上文 `mw.py:1651-1658`（`mw decide ask` 的 unconfigured→enabled 先例）精确位置是 `mw.py:1660-1664`；`_book_gate` 为 `mw.py:1499-1530`，`_book_receipt` 起于 `mw.py:1531`。
- 其余锚点已按本次实读复核：`decide_for` step 号（`decision_points.py:2320/2330/2378/2424/2440/2481/2520/2558/2599`）、`decision_book.py:53/139/362/549/615/848`、`decision.py:351/383/854`、`decide_archive.py:39/91/948`、`decide_signoff.py:270/287`。
- 结论 1 需精确化：dp4..dp24 中 **dp5/dp7/dp9/dp21/dp22/dp23 六个是 P2、默认 `enabled=true`**，其"零业务事实"决策本会真的进入 step7 传输，并在 step11 因 executor 未接线以 `over-authority` 升级（`decision_points.py:427,2599-2620`）；其余 15 个（P1/P0，默认 disabled）要先被人 enable 才会发送。所以 AC-009 的虚测风险在 6 个 P2 上**当前即成立**，在另外 15 个上是"human enable 后成立"，两者都必须靠新增必填字段关闭。
