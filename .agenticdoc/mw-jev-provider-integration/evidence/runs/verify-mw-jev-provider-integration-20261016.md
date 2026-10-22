# 验收证据 — mw-jev-provider-integration (T-04)

- 日期: 2026-10-16
- key: `mw-jev-provider-integration` · 角色: coding (W4/T-04 证据收口)
- goal 对齐: goal.md ① jev 跑通能用起来（收敛为"决策调用链路可用"）② 接口友好、框架决策时刻能正确调用并有效反馈
- 环境: Windows · Python 3.14 · repo `H:\git\Multi-Workers`
- 真实链路临时项目: `%TEMP%\mw-jev-t04\proj`（本仓根目录 `.mw/decide.json` **不存在**，未配置状态见 §C）
- 凭据卫生: 全程只使用既有 `TIMI_API_KEY`（env 已存在）；本文件与所有输出**无任何 key 明文**

---

## §A 真实链路端到端（核心证据）

### A-1 真实 `mw decide run`（call 1/1，B2 过渡后端）

命令（请求 JSON 走 stdin，未用 argv 传 state；`<tmp> = %TEMP%\mw-jev-t04\proj`）：

```bash
python -X utf8 packages/multi-workers/mw.py decide run --project <tmp> --dp dp1 --json <<'REQ'
{"state": "Dispatch scenario: a PM window is about to dispatch one worker card whose body asks to add a retry wrapper around an HTTP client and cover it with unit tests. The owning phase is phase-2. Classify the task type and risk.",
 "questions": {"triage_type": {"type": "choice", "choices": ["coding", "research", "review"]},
               "triage_risk": {"type": "choice", "choices": ["low", "mid", "high"]}}}
REQ
```

`.mw/decide.json`（临时项目，BOM-less utf-8）：

```json
{"enabled": true, "transport": "llm-transitional", "model": "glm-5.3-flashx", "timeout_s": 20}
```

关键输出（退出码 + 响应元数据）：

```text
RC=0
available=true  reason=null  transport=llm-transitional  model=glm-5.3-flashx
attempts=1  latency_ms=6809  confidence_source=model-self-report
answers={"triage_type": {"value": "coding", "confidence": 0.85},
         "triage_risk": {"value": "low", "confidence": 0.85}}
KEY_ORDER=['available','transport','model','confidence_source','attempts','latency_ms','answers','reason']
```

结论：**真实链路跑通**。一次调用（`attempts=1`）拿到两道题的类型化 `answers` 与逐项 `confidence`，
`confidence_source=model-self-report`（过渡后端 = 模型自报，未经校准）。

### A-2 机器可读证据行（AC-008）

调用后追加到 `<tmp>/.agenticdoc/_autopilot/triage-decisions.jsonl`（append-only，1 行；无 key 明文）：

```json
{"ts": "2026-10-16T10:09:40+00:00", "dp": "dp1", "transport": "llm-transitional", "model": "glm-5.3-flashx", "attempts": 1, "latency_ms": 6809, "available": true, "reason": null, "answers": {"triage_type": {"value": "coding", "confidence": 0.85}, "triage_risk": {"value": "low", "confidence": 0.85}}, "confidence": 0.85, "confidence_source": "model-self-report"}
```

### A-3 `mw decide probe --json`（D-1 现状可复现锚点）

```bash
python packages/multi-workers/mw.py decide probe --project <tmp> --json
```

关键输出（6 行矩阵，节选关键 4 行）：

```text
llm-transitional:glm-5.3-flashx      POST /v1/messages          -> 200 ok
llmproxy-anthropic:jev-latest        POST /v1/messages          -> 429 rate-limited
llmproxy-anthropic:jev-latest        POST /responses            -> 200 upstream-error
direct-systemone:glm-5.3-flashx      POST /v1/systemone         -> 404 entry-unavailable
```

### A-4 两条 fail-soft 真实路径（不消耗模型调用）

```text
# B1 被选中但上游入口未暴露：available=false 且 exit 0
{"available": false, "transport": "llmproxy-anthropic", "model": "jev-latest",
 "confidence_source": "api", "attempts": 1, "latency_ms": 0, "answers": null,
 "reason": "entry-unavailable"}
RC=0

# 参数非法（未知问题类型）：exit 2，stdout 无响应体
[mw decide run] question 'q1' has unknown type 'bogus'
RC=2
```

---

## §B AC-001..AC-012 逐条

每条格式：**结论** + 命令 + 关键输出（≤5 行）+ 证据位置。

### AC-001 决策入口契约（CLI = API，四型问题，`confidence_source` 区分来源）

**结论：满足。** CLI JSON 进 JSON 出（A-1）；响应字段与顺序 = 设计 D-003；四型问题 `choice/score/noul/box`
在契约层全部接受（`box` 透传后端并返回 `unsupported-question-type`）；CLI 与 Python API 共用
`DecisionClient.decide()`（`mw.py::_decide_run` 只有解析/打印，无第二份校验）；`confidence_source`
区分 `api` / `model-self-report`，且 `model-self-report` 不会被呈现成 `api`。

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py
```

```text
130 passed
test_decide.py::test_success_response_has_exact_contract_fields
test_decide.py::test_all_wave1_question_types_accepted
test_decide.py::test_box_type_is_forwarded_to_backend
test_decide.py::test_confidence_source_api_is_propagated_verbatim
test_decide.py::test_model_self_report_is_never_presented_as_api
```

证据: 本文件 §A-1（真实调用字段）· `packages/multi-workers/test_decide.py`（契约/四型/来源）、
`packages/multi-workers/test_decide_backends.py`（B2 取值强制 + `box` 拒发）、
`packages/multi-workers/test_decide_cli.py`（CLI 同一实现）。

### AC-002 fail-soft（失败一律 `available=false` + `reason`，exit 0；仅参数非法 exit 2；不抛异常）

**结论：满足。** 真实证据：B1 `entry-unavailable` exit 0（§A-4）；非法问题类型 exit 2（§A-4）。
hermetic 失败矩阵覆盖连接不可达/超时/429/5xx/非 JSON/上游错误体。

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py -k "failure or normalization or exit"
```

```text
test_backend_failure_matrix_is_normalized[item4-timeout-3-True]  PASS
test_unknown_backend_reason_is_normalized_to_frozen_value        PASS
test_backend_exception_never_escapes_even_with_buggy_str         PASS
test_run_unavailable_still_exits_zero                            PASS
test_run_invalid_question_type_exit2                             PASS
```

证据: 本文件 §A-4 · `test_decide.py`（fail-soft 矩阵 + 异常不外泄）· `test_decide_cli.py`
（`test_run_available_writes_evidence_and_exits_zero` / `test_run_unavailable_still_exits_zero` /
`test_run_unconfigured_reports_disabled_exit_zero` / `test_run_request_missing_questions_exit2` /
`test_run_invalid_question_type_exit2`）。

### AC-003 传输抽象（B1/B2/B3 可切换；B1 显式 `entry-unavailable`；B2 默认；B3 保留位）

**结论：满足。** `decision_backends.py` 实现三后端；配置 `transport` 选择；B1 未触发真实请求即返回
`entry-unavailable`（§A-4）；B2 为默认并真实可用（§A-1）；B3 无凭据时 `entry-unavailable`
（`test_b3_without_credential_is_entry_unavailable`）。调用方接口不感知后端差异（同一 `BackendOutcome`）。

```bash
cd packages/multi-workers && python -m pytest -q test_decide_backends.py
# 33 passed in ...
```

```text
test_b1_is_entry_unavailable_without_request          PASS
test_b3_without_credential_is_entry_unavailable       PASS
test_b2_success_reads_tool_use_ignoring_thinking_and_text PASS
test_integrates_with_decision_config_and_transport_names  PASS
```

证据: `packages/multi-workers/decision_backends.py` · `test_decide_backends.py` · 本文件 §A-3/§A-4。

### AC-004 诊断探针（矩阵 + 429 / unmapped 锚点可复现）

**结论：满足。** 真实 `probe --json` 复现 D-1 两个锚点：jev 在 `/v1/messages` = **429**；
jev 在 `/responses` = HTTP 200 但体含 litellm 错误（verdict `upstream-error`，即
`Unmapped LLM provider for this endpoint`）。矩阵 6 行覆盖 4 条路径/4 个目标。

```bash
python packages/multi-workers/mw.py decide probe --project <tmp> --json
```

```text
llmproxy-anthropic:jev-latest POST /v1/messages  -> 429 rate-limited
llmproxy-anthropic:jev-latest POST /responses    -> 200 upstream-error
openai-chat:glm-5.3-flashx    POST /v1/chat/completions -> 404 entry-unavailable
direct-systemone:glm-5.3-flashx POST /v1/systemone -> 404 entry-unavailable
```

证据: 本文件 §A-3（完整 6 行矩阵）· `spec.md` §4 D-1（同一锚点）·
`decision_backends.py::probe_matrix` · `test_decide_backends.py::test_probe_matrix_shape_and_coverage`。

### AC-005 凭据最小面（仅 `TIMI_API_KEY` 可用；无 key 明文）

**结论：满足。** A-1 真实调用在环境中仅存在 `TIMI_API_KEY`（其它 provider 凭据未参与）时成功；
`decision_backends` 只从 env `TIMI_API_KEY` → `~/.pi/agent/auth.json` 的 `timi.key` 解析；
本证据文件与所有记录均无 key 明文；`show --json` 将 `api_key` 回显为 `<redacted>`。

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py -k "credential or scrub" test_decide_cli.py::test_show_redacts_api_key
```

```text
test_credentials_never_reach_evidence_or_detail  PASS
test_scrub_detail_truncates_and_redacts          PASS
test_show_redacts_api_key                        PASS
```

证据: 本文件 §A（无 key 明文）· `test_decide.py`（env 注入真实格式 key 断言不落盘/不出现在返回）·
`test_decide_cli.py::test_show_redacts_api_key`。

### AC-006 预算与退避（可配 + 默认值 + 超预算立即 fail-soft）

**结论：满足。** 默认 `timeout_s=20` / `max_retries=2` / `max_questions=8` / `max_state_bytes=16384` /
`max_tokens=1024` / `backoff_base_s=2.0`，全部可经 `.mw/decide.json` 配置；state 超字节预算
attempts=0 + 后端零调用；退避超墙钟即 `budget-exhausted`。

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py -k "budget or retries or backoff or deadline"
```

```text
test_state_byte_budget_returns_budget_exhausted  PASS
test_max_questions_budget_is_input_error         PASS
test_max_retries_bounds_attempts                 PASS
test_retry_backoff_is_exponential_base_2         PASS
test_retry_is_skipped_when_backoff_exceeds_time_budget  PASS
```

证据: `packages/multi-workers/decision.py`（`DecisionConfig` 默认值与校验）· `test_decide.py` ·
`mw decide show` 输出（§C-1 打印默认预算）。

### AC-007 DP-1 派发前分诊（默认关闭；旁路建议；readback；不可用等价）

**结论：满足（覆盖 PM 发起的 2 个派发入口；覆盖面 2/15 见 §E）。** 默认关闭逐字节等价；
建议不改写 `type`/角色/模型；建议经派发回执 + 既有 `recordDispatchAlarm` ledger 通道呈现 PM；
不可用/超时/错误时 `triage=null`，派发照常。

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
# Test Files 1 passed (1) / Tests 21 passed (21)
```

```text
关闭态：triage=null, frontmatter="type: coding\n", spawn 调用 0, ledger 0 行, sendMessage 0 次
可用态：回执含 "[triage] 旁路建议，未据此改派发" + triage_type=/triage_risk= + "模型自报置信度（不用于门控）"
争议：不一致 -> 恰 1 行 triage-suggestion(disagreement=yes) + 恰 1 次 triggerTurn
fail-soft：timeout/bad JSON/非零退出/available=false -> 无 [triage]、无 ledger、无唤醒
```

证据: `packages/coding-agent/test/suite/triage-dispatch.test.ts`（21 用例）·
`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts` ·
`pm/ui-bridge.ts`（`planDispatchFrontmatter` 挂点 + 回执）· `pm/pm-orchestrator.ts`（notice kind + 文案）·
`design.md` D-005/D-006。

### AC-008 有效反馈（每次调用一条机器可读证据行；经既有 readback/ledger 通道）

**结论：满足。** 真实调用落盘 1 行证据（§A-2），字段 = `ts/dp/transport/model/attempts/latency_ms/
available/reason/answers/confidence/confidence_source`；DP-1 结论经既有派发回执与
`recordDispatchAlarm`（五元组形状不变）呈现；不新造通道。

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py -k evidence
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
```

```text
test_evidence_line_written_on_success            PASS
test_evidence_appends_one_line_per_call          PASS
test_evidence_write_failure_is_swallowed         PASS
关闭态无 auto-decisions.jsonl / triage-decisions.jsonl 写入
```

证据: 本文件 §A-2 · `test_decide.py`（证据行）· `triage-dispatch.test.ts`（ledger 行 + 回执）·
`design.md` D-005。

### AC-009 默认零行为变化（未配置项目）

**结论：满足。** 未配置项目：`mw decide show` → `disabled`；`mw doctor` 无 `triage:` 行；
`format_doctor_text` 与"移除 decide section"逐字节相等（zero-perturbation）；TS 侧无 spawn/无 ledger/无
网络调用。派发路径的 frontmatter 与回执关闭态逐字节等于改动前基线。

```bash
python packages/multi-workers/mw.py decide show --project <unconfigured>
# decide: disabled (.mw/decide.json not present)
python packages/multi-workers/mw.py doctor --project <unconfigured> | Select-String triage
# (无输出)
cd packages/multi-workers && python -m pytest -q test_decide_cli.py -k "zero_perturbation or disabled"
```

```text
test_doctor_unconfigured_is_zero_perturbation  PASS
test_show_disabled_when_unconfigured           PASS
test_run_unconfigured_reports_disabled_exit_zero PASS
```

证据: 本文件 §C（完整输出）· `test_decide_cli.py::test_doctor_unconfigured_is_zero_perturbation` ·
`triage-dispatch.test.ts` 关闭态用例。

### AC-010 可运维性（doctor 行 + README/CHANGELOG）

**结论：满足。** `mw doctor` 增信息行（enabled/disabled/ERROR 三态，不进 `_doctor_issues`、
不翻转 healthy），`--json` 同步 `decide` section；README 新增「决策服务（mw decide）」小节；
两个 CHANGELOG 在 `[Unreleased] > ### Added` 追加条目。

```bash
python packages/multi-workers/mw.py doctor --project <configured> | Select-String triage
# triage: enabled llm-transitional last_suggestion=1 last_unavailable=none
python packages/multi-workers/mw.py doctor --project <configured> --json
# {"exists": true, "enabled": true, "transport": "llm-transitional", "last_suggestion": 1, "last_unavailable": null}
```

证据: 本文件 §C-2 · `packages/multi-workers/README.md`（新增小节）·
`packages/multi-workers/CHANGELOG.md`（`[Unreleased] > ### Added`）·
`packages/coding-agent/CHANGELOG.md`（`[Unreleased] > ### Added`）· `test_decide_cli.py`
（doctor 三态与 `--json` section）。

### AC-011 测试（fake transport 覆盖；真实链路以 probe 证据呈现；既有红列零新增）

**结论：满足（见 §F 回归明细）。** fake transport 覆盖 AC-001/002/003/006/007/008；
真实链路以 §A 证据呈现而非 CI 断言；新增测试全绿；既有环境红列零新增。

```bash
cd packages/multi-workers && python -m pytest -q
# 见 §F（相对 8 条环境失败基线：0 新增）
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
# Test Files 1 passed (1) / Tests 21 passed (21)
```

证据: §F 回归明细 · `test_decide*.py` · `triage-dispatch.test.ts` · 本文件 §A（真实链路证据）。

### AC-012 上游依赖显性化（D-1 记录 + 缓解；D-1 未决仍可完整验收）

**结论：满足。** `spec.md` §4 记录 D-1（llmproxy 未暴露决策入口）与给维护方的 5 条问题单；
`design.md` 记 OPEN 与 D-1 阻塞的隔离（入口形状只在 B1 内）；本文件 §A-3 复现锚点；
D-1 未决时交付物仍按 AC-001..011 以 fake transport + B2 真实链路完整验收（§A-1）。

```bash
python packages/multi-workers/mw.py decide probe --project <tmp> --json
# jev @ /v1/messages -> 429 ; jev @ /responses -> 200 upstream-error
```

证据: `spec.md` §4 D-1/D-2/D-4 · `design.md` §1 OPEN + D-002 · 本文件 §A-3/§D。

---

## §C 默认关闭等价性（专项）

### C-1 未配置项目：`mw decide show`

```text
decide: disabled (.mw/decide.json not present)
config: <unconfigured>\.mw\decide.json
transport: llm-transitional
model: glm-5.3-flashx
timeout_s: 20 max_retries: 2 max_questions: 8 max_state_bytes: 16384 max_tokens: 1024
```

`--json` 显示 `"exists": false, "enabled": false, "error": null`。

### C-2 未配置项目：doctor 无 `triage:` 行；已配置项目有

```text
# unconfigured: python mw.py doctor --project <unconfigured> | Select-String triage
(无输出)

# configured: python mw.py doctor --project <configured> | Select-String triage
triage: enabled llm-transitional last_suggestion=1 last_unavailable=none
```

`mw doctor --json`（configured）的 `decide` section：

```json
{"exists": true, "enabled": true, "transport": "llm-transitional", "model": "glm-5.3-flashx",
 "points": {}, "triage_notify_on_unavailable": false, "last_seq": 1,
 "last_suggestion": 1, "last_unavailable": null}
```

zero-perturbation 由 `test_decide_cli.py::test_doctor_unconfigured_is_zero_perturbation` 锁定：
未配置项目 `format_doctor_text(report)` 与 `format_doctor_text(report - decide section)` 逐字节相等；
`test_doctor_broken_config_is_informational_only` 断言坏配置下 `summary.issues`/`summary.healthy`
与未配置完全相同。

### C-3 派发路径未被改写（`git diff` + 关闭态逐字节基线）

本仓根 `.mw/decide.json` 不存在（`Test-Path` = False），即本 key 交付的 WorkTree 自身处于关闭态。
对派发路径的改动全是**新增的、以配置为前件的代码**：

```text
git diff --numstat -- packages/.../pm/ui-bridge.ts packages/.../pm/pm-orchestrator.ts \
                        packages/multi-workers/mw.py packages/multi-workers/mw_common.py
23	1	packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
120	3	packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
344	0	packages/multi-workers/mw.py
107	0	packages/multi-workers/mw_common.py
```

- `mw.py` / `mw_common.py` 为**纯新增、0 删除**（未配置时新代码不可达）。
- TS 两文件的少量删除行是 union 成员/签名的语法替换（`| "model-error";` → `| "model-error" | ...`），
  非派发逻辑改写；默认关闭时 `planDispatchFrontmatter` 的 frontmatter 与回执逐字节等于改动前基线
  （`triage-dispatch.test.ts` 关闭态用例断言）。
- `ui-bridge.ts:3302-3391`（`/mw model` 段）与 `mw.py` 的 `_goal_gate_install`/`cmd_model` 段
  无本 key 改动（并行 key 写入面，未触碰）。

---

## §D D-1 现状与缓解

**现状（可复现锚点，§A-3）**：timiai/llmproxy **未暴露**承载 `state`/`questions` 决策语义的入口：

- `POST /v1/messages` + `jev-latest`（聊天形状）→ **429**（无 retry-after）。
- `POST /responses` + `jev-latest` → HTTP 200 但体含 litellm 错误（`Unmapped LLM provider for this
  endpoint`）→ probe verdict `upstream-error`。
- 自定义决策形状路径（`/v1/systemone` 等）→ **404**。
- 官方契约（`spec-typesafe-api-20261016.md`）是 `POST https://api.typesafe.ai/v1/systemone`，与
  llmproxy 上的入口不对应。

**缓解**：`transport=llm-transitional`（B2）以 timiai 可用模型 `glm-5.3-flashx` 承载**同一
`state/questions` 契约**，强制结构化 JSON 输出并标 `confidence_source=model-self-report`；
B1（jev 正式目标）保持显式 `entry-unavailable`，不静默降级；D-1 解除后 `mw decide probe` 单命令复跑
即可切换（不需改代码，见 `spec.md` D-2）。问题单文本见 `spec.md` §4。

---

## §E 未覆盖 / 未验证

1. **conductor 的 13 个自动派发点未接入**（覆盖面 2/15，结构性）：`conductor.py` 对
   `dispatch.py::dispatch` 的调用（roadmap-writer / phase-writer / verifier / reviewer / repair）
   绕过 `planDispatchFrontmatter`；需后续波挂点 C（`dispatch.py:1427-1470`，REGISTRY 校验后、
   `workers.lock` 临界区之前）。两条孤儿重派路径无分诊时刻、不需覆盖（`design.md` D-006）。
2. **B1 / B3 未实机**：B1 受 D-1 阻塞（未发真实请求即 `entry-unavailable`）；B3 未交付凭据，
   未对真实 `api.typesafe.ai` 验证，仅按官方形状实现。
3. **`box` 问题类型未在真实链路上跑**：契约层接受并透传，B2 返回 `unsupported-question-type`
   （hermetic 测试 `test_b2_box_question_is_unsupported_and_never_sent`）；本次未做真实 `box` 调用。
4. **TS 面板未逐字同步 doctor 行**：`/mw doctor` 的 TS 面板当前不逐字渲染 `triage:` 行
   （Python `mw doctor` 文本/JSON 有该行）；如需逐字同步，先例在 `ui-bridge.ts:2990-3105`。
5. **`triage_risk` 是新语义**：模型基于卡片文本 + phase 的建议，与运行期 `computeRisk`
   （checkpoint 收敛风险，`src=checkpoint`）不是同一量，证据行以 `src=dispatch` 区分；
   本波为旁路建议，未据此改写派发策略。
6. **`state` 输入面较薄**：TS 侧 state 只含 description 全文 + cli + requested type + ownerPhase
   （+ 截断），卡片 `sections` 与 index 行 Deps 未入 state（`planDispatchFrontmatter` 拿不到）。
7. **`.mw/decide.json` 损坏（非 JSON）的 TS 侧行为**只从代码判定（`readDecidePolicy` 返回 disabled
   等价），未单独 TS 用例覆盖（Python 侧有 `test_corrupt_config_returns_error_string`）。
8. **真实调用次数**：本次真实链路只跑了 1 次 `mw decide run`（A-1）+ 1 次 `probe`（A-3）；
   B1/参数非法两条路径（A-4）不消耗模型调用。

---

## §F 回归明细（AC-011）

### F-1 `packages/multi-workers` pytest（对比 8 条环境失败基线）

命令（**直接运行**，不经 `mw run-detached`）：`cd packages/multi-workers && python -m pytest -q`

```text
8 failed, 2488 passed, 10 deselected, 2 warnings in 479.03s (0:07:59)
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
FAILED test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites
FAILED test_mwds_t10_dispatch_run_state.py::test_missing_run_json_dispatches_byte_identically
FAILED test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge
FAILED test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge
FAILED test_mwgal_t13_drift_identity.py::test_process_start_ms_probe
FAILED test_task_type_parity.py::test_bom_historical_books
```

**结论：与 T-02 记录的 8 条既有环境失败基线逐条相同，零新增。** 决策相关
`test_decide.py` / `test_decide_backends.py` / `test_decide_cli.py` 共 130 条全绿。

> 探测副产品（非本 key 缺陷，记录备查）：若用 `mw run-detached` 跑 pytest，会多出 1 条失败
> `test_mw_console_guard.py::test_isolation_parent_process_subprocess_unpatched`（9 failed / 2487 passed）。
> 原因：`mw run-detached` 会为子进程注入 `MW_CONSOLE_GUARD=1` + `PYTHONPATH=<mw_console_guard dir>`，
> 于是 sitecustomize 在解释器启动时就把 `subprocess.Popen.__init__` 包成 `patched`，该测试断言父进程未被
> 污染故失败。单独直跑该测试通过（`1 passed`），直接跑全量也通过（回到 8 failed）。属运行器环境副作用，
> 与 `mw-jev-provider-integration` 无关。

### F-2 `triage-dispatch.test.ts`

```text
RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
 Test Files  1 passed (1)
      Tests  21 passed (21)
```

### F-3 仓库根 `npm run check`

命令：`cd H:/git/Multi-Workers && npm run check`（全量输出保存在 `%TEMP%\mw-jev-t04\check.log`；链为
`biome check --write --error-on-warnings . && check:pinned-deps && check:ts-imports && check:shrinkwrap &&
check:install-lock:coding-agent && tsgo --noEmit && check:browser-smoke`）

```text
Found 3 warnings.
Found 2 infos.
Checked 1175 files in 867ms. No fixes applied.
check <exit 1>
```

**结论：`npm run check` exit 1，但 5 条 finding 全部落在 `mwoc-*` 他窗在飞文件；本 key 文件
error/warning/info 清零。** biome 以 `--error-on-warnings` 在 warning 处中止，故后续阶段单独补跑，
全部通过：

```text
check:pinned-deps              -> 0
check:ts-imports               -> 0
check:shrinkwrap               -> 0 (packages/coding-agent/npm-shrinkwrap.json is up to date)
check:install-lock:coding-agent-> 0 (packages/coding-agent/install-lock is up to date)
npx tsgo --noEmit              -> 0 (无 error TS)
check:browser-smoke            -> 0
```

### F-4 他窗在飞（非本 key，只记录不修）

`npm run check` 的 biome 5 条 finding（3 warning + 2 info），全部是 `mwoc-*`（`test/suite/` 下他 key
文件），本 key 未触碰、按卡片只记录不修：

```text
packages\coding-agent\test\suite\mwoc-matrix-t07.test.ts:45:2   lint/correctness/noUnusedImports  FIXABLE
packages\coding-agent\test\suite\mwoc-matrix-t07.test.ts:120:6  lint/style/useTemplate            FIXABLE
packages\coding-agent\test\suite\mwoc-matrix-t07.test.ts:606:4  lint/complexity/useOptionalChain  FIXABLE
packages\coding-agent\test\suite\mwoc-w2-contract-judgment.test.ts:130:6 lint/style/useTemplate  FIXABLE
packages\coding-agent\test\suite\mwoc-w3-ledger-extractor.test.ts:216:3  lint/complexity/useOptionalChain FIXABLE
```

卡片点名的 `mwoc-matrix-t07.test.ts` 在列；另两条 `.agenticdoc` 变体（`goal.ts` / `mw.py`
`_goal_gate_install` 段）本次 `npm run check` 未报（本 key 也未触碰这些写入面）。
