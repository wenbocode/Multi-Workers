# 决策点（dp）说明与 jev 上下文

> 状态：mw-decision-substitution（用户版说明文档）· 2026-10-21
> 机器可读的同源配置：[`packages/multi-workers/decide_registry.json`](../packages/multi-workers/decide_registry.json)
> （由 `decision_points.registry_snapshot()` 生成 + 手工 `wiring` 节，漂移由
> `test_decide_registry_export.py` 锁死）。本文的 dp 总表就是从这份配置渲染的，不要手改表格，改配置再重新生成。
> 决策服务的传输/凭据见 [`packages/multi-workers/README.md`「决策服务（mw decide）」](../packages/multi-workers/README.md)；
> 决策替换的动机与边界见 [`docs/decision-substitution.md`](./decision-substitution.md)。

## 0. 三十秒版

| 事实 | 值 |
| --- | --- |
| 注册的决策点 | 25 个（`dp1`..`dp25`），全部 noul / choice 型，**没有任何 dp 使用 score** |
| 真正接进流程的 | **3 个**：`dp1-dispatch-type`（派发旁路建议）、`dp2-checkpoint-split`（长任务收敛检查点）、`dp3-worker-clarify`（worker 澄清替换） |
| 只注册未接线的 | 21 个：可被 `mw decide run` / worker `ask_decision` 手工问询，只留痕（`acted=false`），不会自动触发 |
| 唯一传输 / 模型 | `POST {TIMI_BASE}/v1/decisions`，model `jev-latest`，`Authorization: <裸 timi key>`；无 fallback |
| state 预算（dp 管线） | 结构化 state 序列化后 > 2000 B 时：先丢可选字段，再把必填字段减半，仍超 → `input-oversize`（零 HTTP） |
| token 上限（客户端） | `state` + 最长单个问题 ≤ **32768** tokens；整份请求 ≤ **65536** tokens；超限 → `budget-exhausted`（零 HTTP）。估算 `_estimate_tokens`：非 ASCII 每字 1 token、ASCII 每 4 字符 1 token |
| 生效闸 | 只有 `confidence_source=api` 的置信度算判据；聚合取各题 `min`；低于阈值 → `escalated_reason=low-confidence`，`acted=false` |
| 授权来源 | `.mw/decide-points.json`（每行 `tier/enabled/mode/note`，**人写，机器禁写**；唯一例外是 `mw decide dp refresh`——注册表→表单向合并，只补缺失行、永不改已有 `enabled`/`mode`）；P0 开启需 `--i-understand-p0`；P1/P0 默认关，**dp25 例外：P2 默认开，签收默认走 jev** |

## 1. 契约层：`DecisionClient.decide`

`packages/multi-workers/decision.py:735`

```python
def decide(
    self,
    state: DecisionState,                       # Mapping[str, object] | str | Sequence[str]（最优：JSON object）
    questions: Mapping[str, QuestionSpec],      # NoulSpec | ChoiceSpec | ScoreSpec | BoxSpec
    *,
    dp: str = "unspecified",
) -> dict
```

`QuestionSpec` 是 TypedDict 联合（`decision.py:145-183`）：`NoulSpec{type:"noul", instructions?, criteria?}`、
`ChoiceSpec{type:"choice", instructions?, choices? , dynamic_choices?, labels?}`、
`ScoreSpec{type:"score", min, max, instructions?, criteria?}`、`BoxSpec{type:"box"}`。
`state` **故意不窄化成 mapping**：端点接受 text / object / array 三种形态（`decision_backends.py:391 _state_payload`）。

### 返回的 8 个字段（恒存在）

| 字段 | 含义 | 典型值 |
| --- | --- | --- |
| `available` | 是否拿到可用答案 | `true/false` |
| `transport` | 后端名 | `timi-decisions`（其它值 → `entry-unavailable`，零 HTTP） |
| `model` | 响应体回填的模型 | `jev-latest`（与请求不一致 → `bad-response`） |
| `confidence_source` | 置信来源 | `api`（唯一可当判据）/ `model-self-report` / `unknown` |
| `attempts` | 尝试次数（含重试） | `1`..`max_retries+1` |
| `latency_ms` | 总耗时（含退避） | 约 1000-1300 |
| `answers` | `{qid: {value, confidence}}`，失败恒 `null` | 机器面**不含** `probabilities`/`legend` |
| `reason` | 失败码，成功恒 `null` | 见 §7 |

### 九步执行顺序（每步都可能提前返回）

1. 入参校验（唯一会抛 `DecisionInputError` 的地方）：`state` 非 None、`questions` 1..`max_questions(8)`、每题 `type` 合法、
   `choice` 必须 `choices` 与 `dynamic_choices` 二选一（同时给 → 拒）、`score` 整数 `min ≤ max`、
   `noul.criteria` 若给必须恰好 `{true,false}` 且两值非空（FIX-R）。
2. 配置闸：`enabled=false` → `disabled`（detail 区分 missing / disabled by config / 解析错误）。
3. 体积闸：字节闸仅在 `max_state_bytes > 0` 时生效（缺省 `0` = 关闭）；随后 `state` + 最长单题 ≤ `max_state_plus_question_tokens(32768)`、整份请求 ≤ `max_total_tokens(65536)`，超限 → `budget-exhausted`（不发出请求，detail 带实际数字）。
4. 解析后端：`transport=timi-decisions` → `TimiDecisionsBackend`；失败 → `entry-unavailable`。
5. 总时间预算：`deadline = start + timeout_s(20s)`，跨所有重试共享。
6. 调后端：后端异常一律分类成失败码，绝不上抛。
7. 声称 `available` 却给不出可归一化答案 → `bad-response`。
8. 失败重试：仅 `retryable` 且 `attempts ≤ max_retries(2)`，退避 2s/4s；下一次等待会越过 deadline 时立刻 `budget-exhausted`。
9. 归一化 + 落证据 + 返回：只保留问过的 qid、`value` 必须存在、`confidence` 钳到 `[0,1]`。

### 两个面

| 面 | 入口 | 答案宽度 |
| --- | --- | --- |
| 机器面 | `DecisionClient.decide` | 只有 `{value, confidence}`；`probabilities`/`legend` 丢弃，失败 detail 不返回 |
| 人用面 | `mw decide ask`（`_AskDecisionClient`，`mw.py:1280`） | 额外带回 `probabilities`/`legend` 与失败 detail |

### token 估算

`decision.py:523 _estimate_tokens(text)`：非 ASCII 字符每个 1 token、ASCII 每 4 字符 1 token（向上取整）。
这是**保守估计**（CJK 1 字 ≈ 1 token，ASCII 略偏高），仓库没有引入 tokenizer 依赖；因此上限是安全阀，不是计费口径。

### 上下文槽位（`state.context`，可选）

把"模型判断需要、但推导不出来"的工程现场文本传进去。**线上仍只有 `{model,state,questions}` 三键**，context 嵌在 state 内。

| 槽位 | 类型 | 上限 | 生产者 | 内容 |
| --- | --- | --- | --- | --- |
| `task_excerpt` | string | 1200 字符 | dp1 | 派发卡 `## 上下文`/`## 要求` 摘录 |
| `change_summary` | string | 800 字符 | dp2、dp3 | 自上次检查点以来的改动摘要 |
| `candidate_snippets` | array | 5 条 × 200 字符 | dp3 | 候选命中行原文 + `source: <path>:<line>` |
| `artifact_status` | array | 24 条 | dp2 | `{path, exists, bytes}` 交付物状态 |
| `error_excerpt` | string | 1500 字符 | dp4、dp6、dp7（**尚无 caller**） | 门禁/测试失败输出尾部 |

规则：

- 每槽带 `source`，进 `state_digest`；无来源不得外发。
- 超长截断 = **头 60% + 尾 40%** + `…truncated N chars…`（报错关键行在尾部）。
- 总长 ≤ 4000 字符，超出按 `error_excerpt > candidate_snippets > change_summary > task_excerpt > artifact_status` 依次整槽淘汰。
- 脱敏复用 `decision._redact`，`candidate_snippets` 另做 200 字符裁剪。
- 缺失不影响决策（不判 `input-incomplete`），但 `dp verify` 会报告每个 dp 哪些槽为空。

### 证据行

每次调用（含失败）追加一行到 `.agenticdoc/_autopilot/triage-decisions.jsonl`（best-effort，写失败不阻断）：
`ts/dp/transport/model/attempts/latency_ms/available/reason/answers/confidence(min)/confidence_source`。
这行**没有 `key`**，按 key 归集要用权威档案 `.agenticdoc/_autopilot/decisions.jsonl`（hash 链 + `decision_id`）。

## 2. 传给 jev 的上下文

### 请求体（只有三个键）

```json
{
  "model": "jev-latest",
  "state": { "...": "dp 的结构化上下文，或人类直接给的一段文本" },
  "questions": {
    "urgent":  {"type": "noul",   "instructions": "...", "criteria": {"true": "...", "false": "..."}},
    "dept":    {"type": "choice", "instructions": "...", "criteria": {"billing": "...", "infra": "..."}},
    "cand":    {"type": "choice", "instructions": "...", "criteria": {"c1": "...", "c2": "..."}},
    "emotion": {"type": "score",  "instructions": "...", "criteria": ["平静", "不满", "非常愤怒"]}
  }
}
```

- `instructions` 缺省由 `_question_instructions` 生成（`decision_backends.py:398`）；注册表里的题都写了真文本。
- `choice` 的 `criteria` 三种来源，优先级从高到低：调用方给了 `spec["criteria"]` → 逐字透传；动态候选
  （`dynamic_choices` 从 state 渲染）→ 用渲染出的标签覆盖；否则用 `choices` + `labels` 构造。
- `noul` 的 `criteria` 只接受 `{true,false}`；`score` 的 `criteria` 是档位文本数组（低→高），`min/max` 由 `_score_criteria` 推出。
- `box`（图像定位）在 `decide` 里被直接拒（`unsupported-question-type` / `box-requires-image`），不会进请求。

### state 的三种形态与固定键

| 形态 | 谁产生 | 说明 |
| --- | --- | --- |
| JSON object（推荐） | 机器路径（worker/PM） | 结构化 state，正常路径**不做文本化**；`_encode_state` 只用于算预算、token 估算与 `state_digest` |
| 字符串 | 人用路径 `mw decide ask --state/--state-file` | 原样发送 |
| 字符串数组（`Sequence[str]`） | 端点允许 | 框架目前不构造 |

所有 dp 的 state 都有这几个固定键（泛型 builder `decision_points.py:349`）：

| 键 | 含义 |
| --- | --- |
| `schema_version` | state schema 版本，当前恒 `2` |
| `decision_point` | 决策点 id，与触发它的注册表条目一致 |
| `key` | AgenticTask key |
| `task_key` | worker 任务 key（PM 侧决策可缺） |
| `questions_version` | 题面版本（只 hash `id/type/choices/dynamic_choices`，改文案不动版本） |

### 每个 dp 有固定格式吗

**只有 4 个 dp 有强制的必填字段**（`decision_points.py` 的 `REQUIRED_STATE_FIELDS`），缺任意一个 → `input-incomplete`
（零 HTTP，直接上抛给人）；其余 21 个只走泛型 builder，**没有必填字段**，也就是说格式自由、也没有格式保护。

| dp | 必填 state 路径 |
| --- | --- |
| `dp1-dispatch-type` | `schema_version, decision_point, key, phase, task_type, requested_type, risk, risk_source, authority_tier, task_summary, questions_version, scope.write_scope, scope.file_extensions` |
| `dp2-checkpoint-split` | `schema_version, decision_point, key, phase, task_type, risk, risk_source, authority_tier, questions_version, progress.elapsed_minutes, progress.budget_minutes, progress.phases_done, progress.phases_total, progress.artifact_present` |
| `dp3-worker-clarify` | `schema_version, decision_point, key, phase, task_type, risk, risk_source, authority_tier, task_summary, questions_version, ambiguity.kind, ambiguity.question, local_candidates` |
| `dp25-signoff-conclusion` | `key, rows_total, rows_available, chain_ok, p0_open`（签收事实，由 `decide_signoff.collect()` 组装，任意 key） |
| 其余 21 个 | （无） |

补充规则：

- **两段截断**：超 2000 B 时先丢 `OPTIONAL_STATE_PATHS`（`history`、`scope.images_required`、`progress.writes`、
  `progress.uniq_targets`、`progress.repeat_top`、`progress.last_land_age_min`），再把 `task_summary` / `ambiguity.question`
  减半，仍超 → `input-oversize`。
- **动态键**：`dp3` 额外带 `ambiguity{kind,question}`、`local_candidates[]`（≤5 条，每条 `id/label/path?/line?`），
  以及可选的 `rendered`（后端渲染的候选标签，用于覆盖 `criteria`）。`local_candidates` 同时决定 `candidate` 题的可选集合。
- **脱敏**：state 与 detail 在落证据前过 `_redact`/`_scrub_detail`（凭据值、token 形态），错误详情对外只留脱敏文本。
- **答案形状**：`noul` → `{value: 0..1}`（无独立 confidence）；`choice` → `{value: <选项id>, confidence}`（值必须在枚举内，
  否则 `bad-response`）；`score` → `{value: 浮点档位, confidence, legend}`；`probabilities`/`legend` 只在人用面可见。

## 3. 25 个决策点总表（由 `decide_registry.json` 渲染）

<!-- DP-TABLE:START -->
| dp | tier | 默认 enabled/mode | 题面（type） | 已接入 | 触发点 | executor | 版本 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dp1-dispatch-type` | P2 | true/auto | triage_type(choice) + triage_risk(choice) | yes | `ui-bridge.ts:1730` | unwired | `q-09d3aad3` |
| `dp2-checkpoint-split` | P2 | true/auto | checkpoint_action(choice) | yes | `pm-orchestrator.ts:2602` | unwired | `q-ba8e970f` |
| `dp3-worker-clarify` | P2 | true/auto | answer_kind(choice) + answerable(noul) + candidate(choice) | yes | `worker-mode.ts:3903` | unwired | `q-fcbd3847` |
| `dp4-failure-handling` | P1 | false/auto | failure_action(choice) | no | - | none | `q-b93176a8` |
| `dp5-test-triage` | P2 | true/auto | test_category(choice) | no | - | unwired | `q-cc104f59` |
| `dp6-qg-verdict` | P1 | false/auto | qg_verdict(choice) | no | - | none | `q-16b4bb5c` |
| `dp7-gate-failure` | P2 | true/auto | gate_cause(choice) | no | - | unwired | `q-c8e23cc7` |
| `dp8-scope-change` | P0 | false/auto | scope_decision(choice) + scope_reason(choice) | no | - | none | `q-e5d928e8` |
| `dp9-model-select` | P2 | true/auto | model_class(choice) | no | - | unwired | `q-bc7918b9` |
| `dp10-dependency` | P1 | false/auto | dependency_decision(choice) | no | - | none | `q-3bbd9e44` |
| `dp11-credential` | P0 | false/auto | credential_action(choice) | no | - | none | `q-080722b1` |
| `dp12-destructive` | P0 | false/auto | destructive_action(choice) | no | - | none | `q-02f737ab` |
| `dp13-commit-release` | P0 | false/auto | release_action(choice) | no | - | none | `q-6d26173d` |
| `dp14-rule-conflict` | P0 | false/auto | conflict_resolution(choice) | no | - | none | `q-b667b8d3` |
| `dp15-autopilot-gate` | P0 | false/auto | gate_decision(choice) | no | - | none | `q-09e25bec` |
| `dp16-goal` | P0 | false/auto | goal_decision(choice) | no | - | none | `q-ba34304c` |
| `dp17-spec-lock` | P1 | false/auto | spec_lock(choice) | no | - | none | `q-f81bd06d` |
| `dp18-claim` | P1 | false/auto | claim_conflict(choice) | no | - | none | `q-094db8cc` |
| `dp19-foreign-write` | P0 | false/auto | write_decision(choice) | no | - | none | `q-df9c727d` |
| `dp20-stage-close` | P0 | false/auto | stage_action(choice) | no | - | none | `q-30afd59f` |
| `dp21-refine` | P2 | true/auto | refine_decision(choice) | no | - | unwired | `q-ddd23fe2` |
| `dp22-debug-plan` | P2 | true/auto | debug_plan(choice) | no | - | unwired | `q-a1ed6dbc` |
| `dp23-snapshot` | P2 | true/auto | snapshot_decision(choice) | no | - | unwired | `q-f5cecffb` |
| `dp24-pi-trust` | P0 | false/auto | trust_decision(choice) | no | - | none | `q-20850ffa` |
| `dp25-signoff-conclusion` | P2 | true/auto | q-conclusion(choice) | no | - | wired | `q-cad37e2a` |

共 25 个：**已接入 3 个**（`wired: true` 且带 `trigger`/`adopted_at`），其余 22 个只注册、只能手工问询。`executor` 是 Python 侧执行器状态（`wired` 1 / `unwired` 9 / `none` 15）：三个已接入 dp 的真实动作都在 TS 侧，dp25 的 executor 只是回显结论（`signoff:<conclusion>`，不写文件），所以这里显示 `wired` 并不与"已接入 no"矛盾，见 §5 的说明。

**dp25 例外：P2 默认开，签收默认走 jev**（W11 把它从 P1 改为 P2；P1/P0 仍是默认关，只有 P2 默认开）。

**dp25 对任意 key 通用**：它不是一个 key 的专属收尾，任何 AgenticTask key 都走同一条链路——`mw decide sign --key <key>`（或 `--project .agenticdoc/<key>`）；state 里的 `key` 由调用方传入，只统计该 key 的档案行。注册表默认值与表行是两回事：`refresh` 之后 `.mw/decide-points.json` 已有 `dp25-signoff-conclusion` 真实一行（`tier=P2`、`enabled=true`、`mode=auto`、`source=config`），不再只靠注册表默认值隐身生效。

未接入 dp 的替代机制写在配置的 `wiring_note` 里（例如 dp19 → write-face 守卫、dp20 → autopilot gate、dp24 → pi core project-trust）。`dp25-signoff-conclusion` 是 `mw decide sign` 的即时调用点（签署自动流程，state 由 `decide_signoff.collect()` 组装），没有 TS 调用点，因此 `wired: false`。
<!-- DP-TABLE:END -->

## 4. 已接线的三个（自动触发）

### dp1-dispatch-type —— 派发旁路建议

- 触发：PM 每次派发在 `planDispatchFrontmatter` 内调用（`pm/ui-bridge.ts:1730`，门在 `pm/triage-client.ts:820`）。
- 输入：任务卡 frontmatter + 请求的 type/risk + `scope.write_scope`/`scope.ext`。
- 题面：`triage_type`（coding/research/review，带 labels）、`triage_risk`（low/mid/high，带 labels）。
- 采纳：**只建议，不改派发**（AC-014：派发的 type 永不被 jev 改写）。类型一致时写 `decision:` 头行留痕
  （`ui-bridge.ts:281`）；分歧时唤醒 PM（`ui-bridge.ts:541`）。Python 侧恒 `acted=false`。
- 现网表现：`[triage] 旁路建议，未据此改派发：triage_type=coding（conf=1.00）, triage_risk=mid（conf=0.83）；confidence_source=api`。

### dp2-checkpoint-split —— 长任务收敛检查点

- 触发：PM 轮询 loop（`pm/pm-orchestrator.ts:2602`），条件 `risk=mid|high`（`:2592`），**每任务一次**。
- 输入：`progress.{elapsed_min,budget_min,phases_done,phases_total,artifact_present}`。
- 题面：`checkpoint_action`（continue/narrow/stop，带 labels）。
- 采纳：**只有 `narrow` 是机器可执行动作**——写 `steer-dp2.md`（`:2620`）+ trace `acted=1`（`:2399`），worker 在
  `worker-mode.ts:2929/3825` 消费；其它动作回落人工 alert（`:2641`）。
- 闸：`acted = mode=auto && action=narrow`，且置信需 `api` 来源。

### dp3-worker-clarify —— worker 澄清替换

- 触发：worker settle 出口 `exitCode===2`（needs-clarification）的唯一插入点（`worker/worker-mode.ts:3903`；门 `:3699`，
  每进程一次预算 `:3706`）。
- 输入：`task_summary` + `ambiguity{kind,question}` + `local_candidates[]`（≤5 条，来自本次工作区真实命中的文件/行）。
- 题面：`answer_kind`（fact/intent/reuse）、`answerable`（noul，带 `{true,false}` criteria）、
  `candidate`（choice，`dynamic_choices` 渲染候选，**无 labels**）。
- 采纳：`answerable ≥ DP3_ANSWERABLE_MIN(0.5)` 且置信聚合 ≥ `DP3_MIN_CONFIDENCE(0.7)` 才动作；答案文本**不采信模型自由文本**——
  用本地文件命中行（≤200 字符，带 `(rel:line)`）+ 候选 id，以 followUp 注入 `[mw dp3-answer]`（`:3753`），
  并记 `[DECISION] dp3 acted=1 decision_id=…`。
- 回落：`3b`（intent）、`mode=suggest`、置信不足、候选未命中（`DP3_MIN_MATCH_SCORE=0.75`）→ 走原人工路径（`:3782`）。

阈值常量（源码写死，目前不可配）：`DP3_MIN_MATCH_SCORE=0.75`、`DP3_MIN_CONFIDENCE=0.7`、`DP3_ANSWERABLE_MIN=0.5`
（`worker-mode.ts:4434/4440/4444`）。

## 5. 只注册未接线的 22 个

- **能做什么**：`mw decide run --project . --dp <id> --request-file <json>` 手工问询，或 worker 的 `ask_decision` 工具；
  答案进权威档案（`acted=false`），只有当次调用方读得到。
- **不能做什么**：没有任何代码在特定条件下自动触发它们；`intent=act` 在生产零调用点，
  有占位执行器的（dp5/dp7/dp9/dp21/dp22/dp23）会 `over-authority`，没有执行器的（executor=none）直接 `no executor` 上抛。
- **语义替代**：它们想解决的场景现在由其他机制承担，例如 `dp19-foreign-write` → write-face 守卫，
  `dp20-stage-close` → autopilot gate，`dp24-pi-trust` → pi core 的 project-trust，`dp12-destructive` → pi 核心确认。

> 注意 `executor`（Python 侧）与 `wiring.wired`（真实接线）是两个维度：今天只有一个 dp 有 `wired` 的 Python executor——
> dp25 的回显执行器，它只返回 `signoff:<conclusion>`，不写文件、不联网、不改配置；其余 dp 的 Python executor 都是
> `unwired`/`none`，三个已接线 dp 的真实动作全部发生在 TS 侧（`decide_registry.json` 的 `wiring` 节记录 trigger/adopted 行号）。

## 6. 配置面（哪些能配、哪些不能）

| 层 | 文件/位置 | 可配字段 |
| --- | --- | --- |
| 全局 | `.mw/decide.json`（`mw decide set/show` 可读写） | `enabled`、`transport`、`model`、`timeout_s`、`max_retries`、`max_questions`、`max_total_tokens`(65536)、`max_state_plus_question_tokens`(32768)、`max_state_bytes`(0=关闭)、`max_tokens`、`backoff_base_s`、`evidence_path`、`triage_notify_on_unavailable`、`signoff`(`auto`\|`disable`，签收模式，由 `mw decide sign --auto`/`--disable` 写；非法值只设 `signoff_error` 不让 dp 掉线) |
| 逐 dp（授权表） | `.mw/decide-points.json` | **只有** `tier`、`enabled`、`mode`(`auto`\|`suggest`)、`note` —— 由人来写（`mw decide dp set`），机器禁写 |
| 注册表快照 | `packages/multi-workers/decide_registry.json` | 生成段只读；每个 dp 自带 `wired/trigger/adopted_at/wiring_note` 手工维护；`mw decide dp export --write` 重生成并保留这四项；`required_state_fields` 的语义来自 `STATE_FIELD_DESCRIPTIONS` |
| 代码常量 | `worker-mode.ts:4434/4440/4444`、`decision_points.MAX_STATE_BYTES=2000` | 阈值与预算，**不可配** |

字段语义：配置里每个必填 state 路径都带 `{name,type,description}`，`description` 取自 `decision_points.STATE_FIELD_DESCRIPTIONS`（覆盖 `REQUIRED_STATE_FIELDS` 的每个路径，漏一条生成即 fail loud）。

**还没有的**（用户已知悉）：per-dp 的 `model` / `transport` / `min_confidence` / 题面覆盖。今天 transport 与 model 是仓级单值，
阈值是源码常量。要加，最小改动面是给授权表行增加可选列（`_DP_ROW_KEYS`+`_DP_SET_SPEC`）+ 消费侧
`row.min_confidence ?? DP3_MIN_CONFIDENCE`。

## 7. 失败码 ↔ 现象 ↔ 处置

| `reason` | 现象 | 处置 |
| --- | --- | --- |
| `disabled` | 根本没发请求 | 看 `.mw/decide.json` 的 `enabled` 与该 dp 行 `enabled` |
| `entry-unavailable` | 凭据缺失/transport 值不认识/后端解析失败 | `mw decide doctor`；确认 `transport=timi-decisions` |
| `timeout` / `budget-exhausted` | 网关慢或退避吃掉预算 | 查 `timeout_s`，别靠重试 |
| `rate-limited` | 429 | 等 `retry-after`；人用通道不要连发 |
| `upstream-error` | 5xx/连不上 | 看 `mw.log` 里的脱敏 detail |
| `bad-response` | 200 但不可用：`body.error`、缺 answers、模型被偷换、值不在枚举 | 不要重试掩盖；抓 `request/response` 原文对契约 |
| `unsupported-question-type` | 传了 `box` | 该类题需要图像资产，文本决策通道不支持 |
| `input-incomplete` | 少了 `REQUIRED_STATE_FIELDS` 里的必填路径 | 补齐调用方 state（dp1/dp2/dp3 才有此闸） |
| `input-oversize` | state > 2000 B 且截断后仍超 | 精简 state，别塞整篇文档 |
| `low-confidence` | 答案置信 < 阈值 | 设计内行为：上抛给人，不是故障 |
| `over-authority` | `intent=act` 但 dp 没有真执行器 | 只有 3 个已接线 dp 有真动作；其余只能 `intent=answer` |

## 8. 一个命令验完 25 个 dp

```
mw decide dp verify            # 离线：每个 dp 的注册表配置能否解析成 decide 参数
mw decide dp verify --live     # 真机：同一份最小 state 真发给 jev，逐 dp 打印 available/model/latency
```

机制：按该 dp 自己的 `required_state_fields` 造一份**最小合法 state**（`schema_version=2`、`decision_point`、`phase`、
`task_type`、`risk`、`risk_source`、`authority_tier`、`task_summary`、`questions_version`，以及 dp 需要的
`scope.*`/`progress.*`/`ambiguity.*`/`local_candidates`），然后：

1. 离线：`DecisionClient` + 假后端，断言不抛 `DecisionInputError`、`available=true`、答案 id 集合 == 题面 id 集合、
   `TimiDecisionsBackend.build_payload` 产出的 body 只有 `{model,state,questions}` 且每题类型/`instructions`/`criteria` 合法；
2. `--live`：同一份请求真发给 `jev-latest`，任一 dp `available=false` 退出码 1。

2026-10-21 真机结果（`evidence/runs/jev-live-20261021/dp-verify-live.txt`）：**24 ok / 0 fail**，
全部 `available=true`、`model=jev-latest`、0.77-1.36 s，每个 dp 的题面 id 都被回答。

> 注意：只有 dp1/dp2/dp3/dp25 定义了 `required_state_fields`，其余 21 个的探针 state 是 `{}`——
> 这证明"配置能被正确解析并送到 jev"，**不证明**调用方会给对字段（它们没有必填约束）。

## 9. 决策本：配置生成骨架，`book check` 验收

dp 的要求在 `decide_registry.json`；决策本是 `decide` 的输入；PM/worker 的职责是**按配置填字段内容**，不是决定有哪些字段。

```
mw decide book new dp3-worker-clarify --out book.json    # 骨架：键与顺序 == 注册表必填字段
# 填值（每个值来自真实证据，notes.evidence 给 path:line）
mw decide book check book.json                           # 七类失败码，全过才 exit 0
mw decide run --book book.json --dp dp3-worker-clarify   # 先验后发；不过则零 HTTP
```

骨架长这样（dp3，节选）：

```json
{ "schema_version": 2, "decision_point": "dp3-worker-clarify",
  "state": { "schema_version": 2, "decision_point": "dp3-worker-clarify",
             "key": "<string: AgenticTask key, e.g. mw-decision-substitution.>",
             "phase": "<string: Current AgenticTask phase, e.g. EXECUTE.>",
             "...": "...", "questions_version": "q-fcbd3847",
             "local_candidates": [] },
  "context": { "change_summary": "", "candidate_snippets": [] },
  "notes": { "evidence": { "key": "<待填: path:line 或命令原文>", "...": "..." } } }
```

失败码：

| 码 | 触发 |
| --- | --- |
| `book-schema` | JSON 不可解析、顶层键非法、`schema_version != 2`、dp 不在注册表 |
| `book-state` | 必填缺失、类型不符、**多出注册表没有的键**（封闭集合） |
| `book-placeholder` | 占位符未替换、`TBD`/`TODO`/`待填`、必填空串 |
| `book-context` | 未知槽位、超单槽上限、`notes.evidence` 缺同名条目 |
| `book-evidence` | `path:line` 不存在、行号越界、路径在仓库外 |
| `book-budget` | 超 32k（state+最长单题）/ 64k（整份请求） |
| `book-secret` | 命中凭据正则 |

`check` 只报告不修；`--book` 失败即零 HTTP。成功的请求会把 `book_path` + `file_sha256` 写进档案与回执。

**谁来写这本：`type: decision` 的 worker**（mw-decision-substitution W8）。
「读配置 → 收证据 → 填本 → 过检 → 交回」不再由 PM 临场推理，而是一个只读 worker 角色：
词表 `TASK_TYPE_TO_ROLE["decision"] = "decision"`，工具只有 read/find/grep/ls/bash（bash 收窄到
`mw decide book check` / `book new`（`--out` 限 books 目录）/ `git diff --stat` / `rg` / `cat`），
写入面只到 `<key>/evidence/books/**`，`ask_decision` 保持可用。卡片必须声明 `- dp:`、
`- 证据来源:`、`- 分支后果:`、`- allow-send:`；`allow-send: no`（缺省）时 worker 只跑
`book check`，发送归 PM。派发前可用 `python -m autopilot.dispatch check --card <card>` 离线判同一套
标准（exit 0 干净 / 2 拒绝）。角色细节见
[`packages/multi-workers/README.md`](../packages/multi-workers/README.md) 的「派 decision worker 写决策本」一节。

## 10. 维护约定

- 改注册表（`decision_points.py`）→ 跑 `python mw.py decide dp export --write`（在 `packages/multi-workers` 下）→
  `python -m pytest -q test_decide_registry_export.py`。忘了重新生成，漂移测试会失败。
- 新接线一个 dp → 同时更新 `decide_registry.json` 的 `wiring` 节与测试里的 `WIRED_DP_IDS` 常量（人工两处，故意不自动）。
- 本文的 §3 总表由配置渲染；要改表先改配置。
