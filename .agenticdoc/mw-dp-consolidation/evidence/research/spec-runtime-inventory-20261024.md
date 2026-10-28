# RQ1 运行能力盘点：25DP 运行可达性、消费者与删除面

> Key: mw-dp-consolidation · 类型: research（只读盘点，未改任何文件）
> 目标锚点: `.agenticdoc/goal.md:5` · 范围: `.agenticdoc/mw-dp-consolidation/spec.md` §1.1（保留8/退役17）
> 本文件只做运行盘点和删除范围取证，不做 RQ2 四门业务设计，不做 RQ3 历史迁移审计。

## 结论

- C1 **真实代码自动触发只有 3 个 DP**：dp1（派发前 triage，`ui-bridge.ts:603` 由 `:1872` 调用）、dp3（worker settle 钩子 `worker-mode.ts:4156` → `:5654`，且必须有 agent 材料否则零 spawn 升级）、dp25（`mw decide sign` → `decide_signoff.py:423` 调 `decide_for`）。dp2 在代码里**没有自动 producer**，只有常量与 worker 侧 steer 消费。
- C2 **dp4–dp24 全部没有生产 producer**：退役 17 项之外，保留的 dp6/dp7/dp15/dp20 同样只在注册表/生成物/文档里存在（`decide_registry.json:344/419/1000/1354`，`decision_points.py:650/658/768/811`），`wired=false` 且 `trigger=None`。
- C3 **唯一能让模型"显式调用任意 DP"的活入口是 `ask_decision` 工具的 TypeBox 枚举**（`decision-tool.ts:132-157` 的 25 个 id，schema 在 `:1642-1648`，PM 与 worker 两种模式都注册：`index.ts:92`/`:102`）。这是删除退役 DP 时最关键的一处运行入口。
- C4 但该入口对 21 个 legacy DP **拿不到有效裁决**：`buildDecisionState` 只填 `schema_version`/`decision_point`/`key`/`task_key`/`task_summary`（`decision-tool.ts:389-400`），而 Python 的 `decide_for` 第 5 步强制 `REQUIRED_STATE_FIELDS`（`decision_points.py:5250-5266`），dp4–dp24 都带身份路径 + 业务事实字段 ⇒ 子进程返回 `input-incomplete`。即：**可调用但不产生模型裁决**（零 POST）。
- C5 另有 CLI 面 `mw decide run --dp <任意注册 id>`（`mw.py:12610`，`--dp` 合法集合来自 `DP_REGISTRY`）与 `mw decide dp verify --live`（`mw.py:3336`/`:3370`）可对任意 DP 发起真实调用；这两处是"显式可调用"的第二、第三入口，属于工具/开发调试面而非生产自动链。
- C6 **dp15 与 autopilot 的六类人工门没有任何接线**：六类 gate 由 autopilot 自己的 `autopilot/gates.py:82 GATE_KINDS` + `conductor.py:7003 AUTO_RULE_BY_KIND` / `:8467 auto_decide_gates` / `:6654-6860 proposition_*` 机械裁决。因此删 dp15 注册**不会**删掉六门规则；反之六门规则也不是 dp15 的接线证据。spec 风险项"不能仅看生成 registry 推断"在此得到确认。
- C7 **registry 的 wired/trigger 是手填声明，不是可达性证明**：`mw.py:2860 _dp_export_wiring_entry` 从 `decide_registry.json` 原样读回四个 wiring 字段，`mw.py:2934 _dp_export_doc` 在导出时合并，而 `decision_points.registry_snapshot()` 自身只写 `UNWIRED_SNAPSHOT_WIRING`（`:964`/`:1071`）。实测手填行号已漂移：dp1 声称 `ui-bridge.ts:1730`（实际是 `resolveDispatchType` 的参数行，真正 producer 在 `:603/:1872`）；dp2 声称 `pm-orchestrator.ts:2602`（该行是 evidence-review 分支 return）；dp3 声称 `worker-mode.ts:3903`（该行是 `appendCheckpoint`）。⇒ **三处 trigger 行号全部不指向真实 decide 调用**。
- C8 executor 只有 dp25 是 `wired`（`_echo_conclusion_executor`，`decision_points.py:514`，只回显不动手）；其余为 `unwired` 占位（dp1/dp2/dp3/dp5/dp7/dp9/dp21/dp22/dp23，`:496`）或 `none`（dp4/dp6/dp8/dp10–dp20/dp24）。`mode=auto` + unwired 在第 11 步落到 `over-authority` 升级（预览同构 `:3900-3903`），不会产生动作。
- C9 **安全守卫与被删 DP 解耦**：dp25 签收文件写面守卫在 `xkey-gate-guard.ts:302-314/461/494`（禁 bash 伪造 sign-final）；六门规则在 `gates.py`/`conductor.py`；claim/写面/凭证脱敏在 `autopilot/write_face.py`、`xkey.py`、`decision.py` 的 known-secret 通道。删 DP 入口不涉及这些规则，须显式保留。

## 证据

### 25DP 分类表

图例：`auto`=代码自动触发；`tool`=ask_decision 可调用（枚举内）；`cli`=mw decide run/verify 可调用；`exec`=executor 类别。

| DP | 归类 | auto | tool | cli | exec | 关键证据 |
|---|---|---|---|---|---|---|
| dp1-dispatch-type | 保留 | 是（建议型） | 是 | 是 | unwired | `ui-bridge.ts:603,1872`；`triage-client.ts:77`；`decision_points.py:576` |
| dp2-checkpoint-split | 保留 | 否 | 是（PM only） | 是 | unwired | `pm-orchestrator.ts:1947,1950`；`decision_points.py:595`；worker 消费 `worker-mode.ts:4927-4958` |
| dp3-worker-clarify | 保留 | 是（需 agent 材料） | 是 | 是 | unwired | `worker-mode.ts:4156,5654,5677-5679`；`decision_points.py:615` |
| dp25-signoff-conclusion | 保留 | 是（decide sign） | 是（PM only） | 是 | wired(echo) | `decide_signoff.py:98,423,698`；`decision_points.py:860`；`xkey-gate-guard.ts:302` |
| dp6-qg-verdict | 保留（待联合设计） | 否 | 是 | 是 | none | `decide_registry.json:344`；`decision_points.py:650,2496`；`decision_book.py:116`；`decision_context.py:110` |
| dp7-gate-failure | 保留（待联合设计） | 否 | 是 | 是 | unwired | `decide_registry.json:419`；`decision_points.py:658,668`；`decision_book.py:117` |
| dp15-autopilot-gate | 保留（待联合设计） | 否 | 是 | 是 | none | `decide_registry.json:1000`；`decision_points.py:768`；六门实为 `gates.py:82`+`conductor.py:7003/8467` |
| dp20-stage-close | 保留（待联合设计） | 否 | 是 | 是 | none | `decide_registry.json:1354`；`decision_points.py:811,2506`；autopilot 走 `conductor.py:6680/7269 _stage_close_facts` |
| dp4-failure-handling | 退役 | 否 | 是 | 是 | none | `decision_points.py:629`；`decision_context.py:110` |
| dp5-test-triage | 退役 | 否 | 是 | 是 | unwired | `decision_points.py:637` |
| dp8-scope-change | 退役 | 否 | 是 | 是 | none | `decision_points.py:671` |
| dp9-model-select | 退役 | 否 | 是 | 是 | unwired | `decision_points.py:707` |
| dp10-dependency | 退役 | 否 | 是 | 是 | none | `decision_points.py:716` |
| dp11-credential | 退役 | 否 | 是 | 是 | none | `decision_points.py:724` |
| dp12-destructive | 退役 | 否 | 是 | 是 | none | `decision_points.py:733` |
| dp13-commit-release | 退役 | 否 | 是 | 是 | none | `decision_points.py:742`；`triage-client.ts:430` |
| dp14-rule-conflict | 退役 | 否 | 是 | 是 | none | `decision_points.py:755` |
| dp16-goal | 退役 | 否 | 是 | 是 | none | `decision_points.py:777` |
| dp17-spec-lock | 退役 | 否 | 是 | 是 | none | `decision_points.py:786` |
| dp18-claim | 退役 | 否 | 是 | 是 | none | `decision_points.py:794` |
| dp19-foreign-write | 退役 | 否 | 是 | 是 | none | `decision_points.py:802` |
| dp21-refine | 退役 | 否 | 是 | 是 | unwired | `decision_points.py:820` |
| dp22-debug-plan | 退役 | 否 | 是 | 是 | unwired | `decision_points.py:829` |
| dp23-snapshot | 退役 | 否 | 是 | 是 | unwired | `decision_points.py:842` |
| dp24-pi-trust | 退役 | 否 | 是 | 是 | none | `decision_points.py:851` |

（`decision_points.py` 行号为本轮读取的注册条目首行 `dp_id=`；registry 条目区 576–880。）

### 运行入口与消费者（路径:行号 + 符号）

1. Python 权威注册：`decision_points.py:574 DP_REGISTRY`；校验 `_validate_registry:892`（`EXPECTED_DP_COUNT` 硬约束 `:902`）；解析 `get_decision_point:908`、`questions_map:916`。
2. 生成器：`decision_points.registry_snapshot:1039` → `mw.py:2934 _dp_export_doc`（合并手填 wiring，`:2860 _dp_export_wiring_entry`、`:2893 _dp_export_wiring`）→ `mw.py:2945 _dp_export`（`mw decide dp export --write`）→ `packages/multi-workers/decide_registry.json`；TS 侧 `scripts/gen_decide_registry_ts.py:174 render` → `shared/decide-registry.generated.ts`（仅 state 契约，无 wiring）。
3. 唯一决策执行权威：`decision_points.decide_for:4958`（步骤序 1–11），CLI 面 `mw.py:1282`（`_dp_run`）/`mw.py:1095`（`--stdin`）。
4. TS producer：
   - dp1：`ui-bridge.ts:603 computeDispatchTriage`（policy 门 `:613`，material 构造与 skip 原因 trace `:652-666`）→ `:674 emitDispatchTriage`（ledger + PM 告警）。
   - dp3：`worker-mode.ts:5654 decideDp3WorkerClarify`（`runDecideMw` `:5700`）；唯一真实 producer 是 `ask_decision`（`:5677-5679` 明确注释）。
   - dp25：`decision-tool.ts:1238 → runSignoffAskDecision:1385`；CLI 权威 `decide_signoff.py:423`；写盘 `write_signoff:698`。
   - dp2：只有 `pm-orchestrator.ts:1947/1950/1976`（id/问题/questions_version），无 producer。
5. 工具入口：`decision-tool.ts:1219 runAskDecision`（`:1224` 未注册即拒、`:1228` PM-only 角色拒、`:1238` dp25 分叉、`:1239` 材质 DP、`:1240` legacy）；注册 `:1808 registerAskDecisionTool`，`index.ts:82-103` 双模式注册 + `:2064-2068` active-set 追加。
6. 观测/投影（只读消费者，需保留）：`decision_monitor.py`（dp1/dp2/dp3/dp25）、`decision_dashboard.js`（同上）、`decision_history.py`、`decision_lifecycle.py`（feedback 账本）。
7. 上下文槽位表（会随退役 DP 变小的下游）：`decision_book.py:111 DP_CONTEXT_SLOTS`、`decision_context.py:106-113`（`error_excerpt.producers` 指名 dp4/dp6/dp7）、`triage-client.ts:427-430 REQUIRED_FIELDS_BY_DP`（dp4/dp5/dp6/dp13）。
8. autopilot 侧（与被删 DP 无接线，需保留）：`autopilot/gates.py:82 GATE_KINDS`、`conductor.py:7003 AUTO_RULE_BY_KIND`、`:8467 auto_decide_gates`、`:6654-6860 proposition_*`、`:7269 _stage_close_facts`。

### 删除候选路径（候选，未改动）

- R1 注册源：`packages/multi-workers/decision_points.py` — 17 条 `DP_REGISTRY` 条目（576–880 条目区）及其字段表 `REQUIRED_STATE_FIELDS:1522`、`STATE_FIELD_DESCRIPTIONS:1710`、`OPTIONAL_STATE_FIELDS:2424`、`MODEL_STATE_FIELDS:2437`、`STATE_FIELD_CROSS_CHECKS:2491`（dp6/dp20 交叉校验），以及 `EXPECTED_DP_COUNT` 断言（`:902`）。
- R2 生成物（重生成，不手改）：`packages/multi-workers/decide_registry.json`（`mw decide dp export --write`，保留 dp1/dp2/dp3 的手填 wiring）；`packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（`python scripts/gen_decide_registry_ts.py`）。
- R3 TS 工具面：`pm/decision-tool.ts:132-157 ASK_DECISION_DP_IDS`（枚举即运行入口）；`:214 ASK_DECISION_PM_ONLY_DP_IDS`、`:218-224 ASK_DECISION_MATERIAL_DP_IDS`、`:169-175 ASK_DECISION_ENFORCED_STATE_DP_IDS` 的 4DP 集合不扩不缩。
- R4 CLI/诊断面：`mw.py:3005-3145 _DP_VERIFY_STATE_VALUES`（逐 DP 合约探针事实）、`:3336 _dp_verify_live_point`、`:3370 _dp_verify`、`:2389 _dp_list`；`mw.py:12610 --dp` 的合法集合来自 registry，无独立名单但测试会随之变化。
- R5 下游表：`decision_book.py:111-118`、`decision_context.py:106-113`、`triage-client.ts:427-430`。
- R6 夹具/文档：`packages/multi-workers/decide_cases/`、`decide_book_template.json`（dp6 用例）、`docs/decision-points.md`、`docs/decision-substitution.md`（两份全量 25 DP 表）。
- R7 测试面（须按 spec §1.1 保留"退役拒绝 + 历史只读"）：当前提及退役 DP 的测试文件数（粗计）dp4≈37、dp5≈21、dp8≈15、dp13≈4、dp17≈6、dp20≈6、dp24≈3；dp1≈57、dp2≈37、dp3≈69、dp25≈41 属保留面，不作删除基数。

### 授权风险（需另行授权的精确路径）

- A1 构建产物镜像：`packages/multi-workers/dist/extensions/agent-team-loop.js`（`build-extension.sh:13`）与全局安装镜像 `<PI_CODING_AGENT_DIR|~/.pi/agent>/extensions/agent-team-loop.js`（`mw_common.py:3384`、`:2945`）。改这两处需 build/install 授权，且会外溢到其他会话的运行时。
- A2 项目级活配置：`.mw/decide-points.json`（`decision_points.py:151`、`load_points_config:3480`）与 `.mw/decide.json`（TS `readDecidePolicy`）。本 key 只读，不改默认值/策略表。
- A3 生产账本与历史：`.agenticdoc/*/evidence/…`、归档 case、`decision_lifecycle` 反馈行。删除 DP 不得改写历史字节。
- A4 pi 核心：`packages/coding-agent/src/core/**` 与 tool/extension API 禁止修改；`ask_decision` 只能作为扩展层工具存在。
- A5 安全守卫（不属于删除面）：`xkey-gate-guard.ts`（sign-final 写面）、`autopilot/gates.py`+`conductor.py`（六门与 deferrable 规则）、`decision.py` known-secret/凭证快照、`autopilot/write_face.py`+`xkey.py`。

## 残留与未验证

- U1 **无动态验证**：本轮未运行测试、未执行 `mw decide dp list/verify(--live)`、未起 mw serve/monitor（任务卡禁止）。C1–C5 全部来自符号定点读取，不构成运行观测证据。
- U2 未扫描构建产物 `packages/multi-workers/dist/extensions/agent-team-loop.js` 与 `packages/coding-agent/dist/**`（按约束排除 build 输出）；若存在旧 bundle，其中的 25-DP 枚举会与源码不同步——这正是 A1 需单独授权的原因。
- U3 `mw.py` 只定点读取 export/list/verify/run 相关符号（其余部分未通读）；`decision_wire.py`、`decision_lifecycle.py`、`decision_history.py`、`decision_dashboard.js`、`decision_monitor.py`、`decision_playground.py` 仅按 dp id 文本扫描，未逐函数确认投影语义。
- U4 dp6/dp7/dp15/dp20 的"保留"只表示**注册面存在**，其四门职责、问题、选项、动作映射属 RQ2 设计，本文件不主张已接线或已可用。
- U5 `ask_decision` 对 legacy DP 返回 `input-incomplete`（C4）基于 `buildDecisionState`+`REQUIRED_STATE_FIELDS` 静态推理；book/`--stdin` 传完整业务状态时能否真拿到裁决，未做真调用验证。
- U6 测试文件提及数为正则粗计（存在后缀误匹配，如 `dp4-…z`），只用于量级，不作精确删除清单。

## 上下文来源

- `.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md`（§1.1/§2/§4）；`.agenticdoc/mw-dp-consolidation/key-decision.md`；`.agenticdoc/mw-dp-consolidation/evidence/research/spec-confirmed-intent-20261024.md`
- 源码定点读取：`packages/multi-workers/{decision_points.py, mw.py, decision_book.py, decision_context.py, decide_signoff.py, autopilot/gates.py, autopilot/conductor.py, scripts/gen_decide_registry_ts.py, build-extension.sh, mw_common.py}`
- TS：`packages/coding-agent/src/extensions/agent-team-loop/{index.ts, pm/decision-tool.ts, pm/ui-bridge.ts, pm/pm-orchestrator.ts, pm/triage-client.ts, worker/worker-mode.ts, shared/decide-registry.generated.ts, shared/xkey-gate-guard.ts}`
- 生成物：`packages/multi-workers/decide_registry.json`；文档：`docs/decision-points.md`、`docs/decision-substitution.md`

## 勘误（本轮自检发现，仅命名，不改变结论）

- `## 证据` 第 3 条中的 CLI 符号应为 `mw.py:1281 _decide_run`（`:1282` 是该函数的 docstring 首行，函数名不是 `_dp_run`）；`mw.py:12610 --dp` 与 `mw.py:3336/3370` 的引用不受影响。
- 其余行号已按 `grep -n`/定点读取复核：`decision_points.py` 条目首行 576–880、`mw.py` 的 `_dp_export_wiring_entry:2860`/`_dp_export_wiring:2893`/`_dp_export_doc:2934`/`_dp_export:2945`/`_dp_list:2389`/`_dp_verify_live_point:3336`/`_dp_verify:3370`、`_validate_registry:892`/`get_decision_point:908`/`questions_map:916`。
