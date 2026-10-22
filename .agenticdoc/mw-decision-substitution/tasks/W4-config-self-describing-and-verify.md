# W4：配置自描述（接入状态 + 字段语义）+ 24 个 dp 的契约自检与真机探针

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户看 `packages/multi-workers/decide_registry.json` 后提出两点：

1. **配置里看不出哪些 dp 已接入**：`wiring` 现在是文件末尾的一个平行节，打开某个 dp 的条目看不到它有没有接线；
2. **`required_state_fields` 语义不明**：只有路径字符串（`schema_version`、`scope.file_extensions`…），没有类型和含义；
3. 要求**每一个 dp 配置都能正确解析成 `decide` 的参数，并正确传入 jev** —— 需要可执行的验证，不是纸面承诺。

前置：W2（Python）/W3（TS）已把 state 字段改成非缩写名（`schema_version`/`decision_point`/`scope.file_extensions`/
`progress.elapsed_minutes`/`progress.budget_minutes`，`schema_version=2`）；W1 已把 `DecisionClient` 的 state 类型改成
`Mapping[str, object] | str | Sequence[str]` 并加了 64k/32k token 闸。本卡在这之上做配置与验证。

现状锚点：

- `decision_points.registry_snapshot()`（`decision_points.py:832` 附近）、`registry_snapshot_text()`、`_executor_kind()`
- `mw.py:2131 _dp_export()`、`:2087 _dp_export_wiring()`、`:3189` handler、`:9916` argparse
- `decide_registry.json`（24 points + `wiring` 平行节）、`test_decide_registry_export.py`（31 例）
- 传输装配：`decision_backends.TimiDecisionsBackend.build_questions()/build_payload()`（`decision_backends.py:578/612`）

## 要求

### 1. 每个 dp 条目自带接入状态与字段语义

`registry_snapshot()` 的每个 point 增加（**删掉文件顶层的 `wiring` 平行节**，内容并入各 point）：

```json
{
  "id": "dp3-worker-clarify",
  "tier": "P2",
  "default_enabled": true,
  "default_mode": "auto",
  "description": "…",
  "questions_version": "q-fcbd3847",
  "wired": true,
  "trigger": "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3903",
  "adopted_at": "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3753",
  "wiring_note": "settle exitCode===2 唯一插入点；答案本地生成后 followUp 注入",
  "executor": "unwired",
  "required_state_fields": [
    {"name": "schema_version", "type": "integer", "description": "State schema version (currently 2)."},
    {"name": "decision_point", "type": "string", "description": "Decision point id this state was built for."},
    {"name": "key", "type": "string", "description": "AgenticTask key, e.g. mw-decision-substitution."},
    {"name": "phase", "type": "string", "description": "Current AgenticTask phase, e.g. EXECUTE."},
    {"name": "task_type", "type": "string", "description": "Task type of the work being decided, e.g. coding|research|review."},
    {"name": "risk", "type": "string", "description": "Risk tier of the task: low|mid|high."},
    {"name": "risk_source", "type": "string", "description": "Who assigned the risk: machine|human."},
    {"name": "authority_tier", "type": "string", "description": "Decision authority tier: P0|P1|P2."},
    {"name": "task_summary", "type": "string", "description": "One-line summary of the task being decided."},
    {"name": "questions_version", "type": "string", "description": "Registry question-set version, e.g. q-fcbd3847."},
    {"name": "ambiguity.kind", "type": "string", "description": "Kind of the ambiguity: scope|fact|intent."},
    {"name": "ambiguity.question", "type": "string", "description": "The clarifying question the worker could not answer."},
    {"name": "local_candidates", "type": "array", "description": "Candidate answers found locally: [{id, label, path?, line?}], max 5."}
  ],
  "questions": [ … 不变 … ]
}
```

- 语义表集中在一个新常量 `STATE_FIELD_DESCRIPTIONS: Mapping[str, dict]`（`decision_points.py`，与 `REQUIRED_STATE_FIELDS` 并列），
  值为 `{"type": ..., "description": ...}`；`registry_snapshot()` 按 `REQUIRED_STATE_FIELDS` 顺序渲染。
- `--write` 重新生成时仍要**保留手写 wiring**（现在按 point 的 `wired/trigger/adopted_at/wiring_note` 四字段保留；
  旧格式的顶层 `wiring` 节要能迁移一次，迁移后不再写顶层节）。
- 顶层保留 `schema`/`generated_from`/`question_types`；`schema` 由 1 升到 `2`。

### 2. 契约自检（离线，不联网）：`mw decide dp verify`

新命令：

```
mw decide dp verify [--project DIR] [--json] [--live] [--dp ID ...]
```

- 对每个 dp 构造一份符合 `required_state_fields` 的**最小合法 state**（`schema_version=2`、`decision_point=<id>`、
  `phase=EXECUTE`、`task_type=coding`、`risk=low`、`risk_source=machine`、`authority_tier=`该 dp 的 tier、
  `task_summary="<id> contract probe"`、`questions_version=`该 dp 的版本、`scope.write_scope=["packages/"]`、
  `scope.file_extensions=[".py"]`、`progress.elapsed_minutes=1`/`budget_minutes=30`/`phases_done=1`/`phases_total=3`/`artifact_present=true`、
  `ambiguity.kind="scope"`/`ambiguity.question="<id> probe"`、`local_candidates=[{"id":"c1","label":"candidate one"}]`）——
  只填该 dp `required_state_fields` 里出现的路径，**不塞多余字段**。
- 用 `DecisionClient(cfg, backend=FakeBackend(available=True, answers=每题的合法占位答案))` 跑 offline 自检，断言：
  1. 不抛 `DecisionInputError`（说明配置能被 `decide` 正确解析）；
  2. `available=true` 且 `set(answers) == set(question ids)`（说明每个题都能被归一化）；
  3. `TimiDecisionsBackend.build_payload(state, questions, cfg)` 产出的 body 只有 `{model,state,questions}` 三键，
     每题都有 `type` 与 `instructions`，`choice` 有 `criteria`，`score` 有 `criteria`（数组），`noul` 有 `criteria`（若配置里有）；
  4. 该 dp 的 `questions_version` 与快照一致。
- `--live`：同样构造，但用真实后端（真 HTTP，`jev-latest`）并发限制 1、逐 dp 打印
  `id | available | model | latency_ms | reason | answer ids`；任一 dp 失败（`available=false`）退出码 1，方便 PM 一键验。
  该模式只在 PM 机器上跑，worker 自测**不要**跑 `--live`。
- 默认（无 `--json`）打印一屏：每 dp 一行 `id  ok/fail  questions=N  wired=yes/no`，末尾汇总 `24 ok / 0 fail`。

### 3. 测试 `packages/multi-workers/test_decide_registry_contract.py`（新建）

1. 24 个 dp 的 offline 自检全部通过（直接调上面的纯函数，不 spawn CLI）。
2. `STATE_FIELD_DESCRIPTIONS` 覆盖 `REQUIRED_STATE_FIELDS` 里出现的**每一个**路径（并集），且 `type` 在
   `{object,string,integer,number,boolean,array}` 内。
3. `decide_registry.json` 的每个 point 都有 `wired`（bool）、`trigger`/`adopted_at`（`wired=true` 时为 `path:line` 且文件存在、
   行号 ≤ 行数；`wired=false` 时为 null）、`wiring_note`（非空）。
4. 顶层不再有 `wiring` 节；`schema == 2`。
5. 每个 point 的 `questions` 至少 1 题，每题 `id` 唯一、`type` 合法。

（`test_decide_registry_export.py` 的漂移断言同步更新到新结构，别删掉逐字节一致那条。）

### 4. 文档

- `packages/multi-workers/README.md` 的 dp 指令行追加 `verify`。
- `packages/multi-workers/CHANGELOG.md` `[Unreleased]/### Added` 追加一条（英文：配置自描述 + dp verify + 顶层 wiring 合并）。

### 5. 配置读写面认识新键（W1 残留）

`decision.py` 的 `DecisionConfig` 现在有 `max_total_tokens` / `max_state_plus_question_tokens`，但 `mw decide show`
与 `mw decide set` 还不认识它们（W1 的写面外）。本卡补：

- `mw decide set --project . <key>=<value>` 的白名单加入 `max_total_tokens`、`max_state_plus_question_tokens`、
  `max_state_bytes`（整数、必须 > 0；`max_state_bytes` 允许 0 表示关闭），非法值 exit 2 且不写文件；
- `mw decide show` 打印这三个键的当前值（缺省也打印）；
- 测试：`test_decide_cli.py` 里加 3 例（set 合法写入、非法值拒绝、show 带出这些键）。

### 6. 跨语言必填字段一致性（W3 残留）

W3 发现 TS 侧 dp3 的 pre-gate 必填清单缺 `local_candidates`（Python 权威里有），且全仓没有字段名一致性锁。
本卡补：

- 在 `test_decide_registry_contract.py` 加一条 parity 测试：用正则在 `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
  里抽取 TS 版必填字段清单（W3 已经把它改成 `schema_version`/`decision_point`/…，形如 `"dp3-worker-clarify": [...]`），
  与 Python `REQUIRED_STATE_FIELDS` 逐 dp 比较，必须逐字一致；
- 为让它通过，把 `local_candidates` 补进 TS 侧的 dp3 清单（`triage-client.ts`）。若补上会让现有 TS 测试失败，
  改测试夹具补 `local_candidates`（不要弱化断言），并在报告里说明。

## 验收命令

```bash
cd packages/multi-workers
python mw.py decide dp export --write
python -m pytest -q test_decide_registry_export.py test_decide_registry_contract.py test_decide_dp_cli.py
python mw.py decide dp verify
python mw.py decide show --project .
cd ../coding-agent && npx tsgo --noEmit
```

（最后一条应打印 24 行 ok + 汇总 `24 ok / 0 fail`，退出码 0。**不要**跑 `--live`。）

## 写入允许面

- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_registry.json`
- `packages/multi-workers/test_decide_registry_export.py`
- `packages/multi-workers/test_decide_registry_contract.py`（新建）
- `packages/multi-workers/README.md`、`packages/multi-workers/CHANGELOG.md`
- `packages/multi-workers/test_decide_cli.py`（§5 的三个用例）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（§6 的 `local_candidates` 一行 + 必要夹具）
- `packages/coding-agent/test/suite/triage-client-state.test.ts`（§6 若需补夹具）

## 写入禁止面

- `decision.py`、`decision_backends.py`、`decide_signoff.py`、其它 `test_decide_*.py`
- `packages/coding-agent/**`、`packages/ai/**`、`docs/**`（PM 统一改）、`.agenticdoc/**`、`.agents/**`、`.mw/**`
- 禁止 `git` 写、`npm run check`、`npm run build`、`mw build --install`、全量 pytest、**任何真实网络调用**、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 三条验收原文 / 24 个 dp 的 offline 自检结果（失败则逐条给原因）/ 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 已接线事实（写进配置的 `wired/trigger/adopted_at`）：dp1 `ui-bridge.ts:1730`/`:281`；dp2 `pm-orchestrator.ts:2602`/`:2620`；
  dp3 `worker-mode.ts:3903`/`:3753`；其余 21 个 `wired=false` + note 写替代机制
- `FakeBackend` 在 `decision.py:578`，用法见 `test_decide.py`
- 占位答案形状：`noul → {"value": 0.9}`；`choice → {"value": <第一个 choices 或 c1>, "confidence": 0.9}`；
  `score → {"value": 1, "confidence": 0.9}`（归一化只要求 `value`）

## 改动历史

- 2026-10-21 建卡：用户要求配置自描述（接入状态 + 字段语义）且每个 dp 都能被 `decide` 正确解析并传到 jev。
