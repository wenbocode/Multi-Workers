# T-05b 对抗评审报告（质量门，收窄版）

- key: mw-jev-provider-integration · task: jev-t05b-qg-review · type: review · 2026-10-16
- **评审方式声明（诚实性前提）**：本 worker 会话工具面为只读（read/find/grep/ls + worker_file），**无 shell**。卡片的三条验收命令与「重跑 2 条 AC」无法在本会话执行。抽查改为**静态证据核对**：逐条把 T-04 记录输出与当前代码/测试断言比对，并以 `.pytest_cache`（nodeids/lastfailed）佐证最近一次套件状态。本报告未伪造任何命令输出；所有「复现命令」均为 PM 可自行执行的验证命令。

## 结论

**PASS（有保留）**：**0 blockers / 0 majors / 4 minors / 5 notes**。

- 审计 4 项全部达标：(1) 敏感内容外发风险 **LOW**（双重字节上限 + 与既有 worker 流量同通道）；(2) 测试真实（hermetic、断言真实、失败路径覆盖充分，1 处自证式断言）；(3) 默认关闭等价性在 TS/Python 两侧都被**真断言**（零 spawn、零写、零 notify、回执逐字节相等）；(4) 诚实性与凭据声明如实（2/15 覆盖、B1 恒 entry-unavailable、model-self-report 标注不用于门控；凭据无环境性泄漏，1 处用户自致的 stdout 回显不一致）。
- 抽查（默认关闭等价性 + fail-soft 退出码）：静态核对**未发现任何与 T-04 证据不一致项** → 按卡片标准不构成 blocker；但运行时一腿缺位（M4），PM settle 前建议自行复跑两条套件（命令见 §残留，合计约 1-2 分钟）。

## 证据

### 审计 1 — 敏感内容外发（独立判断）

**结论：风险 LOW；裁剪存在且有界；最小缓解 = README 补一句数据流披露（并入 M1）。**

事实链（自行核对，非照抄实现说法）：
- TS 侧 state 构成：`buildTriageState`（triage-client.ts:201-214）= `requested_type` + `cli` + `owner_phase` + **description 全文**；上限 `MAX_TRIAGE_STATE_BYTES=16_000`（triage-client.ts:44；`boundTriageState`:216 按字节精确截断并追加 `[state truncated]`）。测试 `state is bounded and questions are the DP-1 choice set` 断言出站 payload ≤16,000 字节。
- Python 侧二次预算：`max_state_bytes=16384`（decision.py `DecisionConfig` 默认）；超限 attempts=0 + `budget-exhausted`，不发请求（test_state_byte_budget_returns_budget_exhausted 断言 `backend.calls == []`）。
- 出站去向：B2 把 state 原文嵌入 `/v1/messages` user content（decision_backends.py `LLMTransitionalBackend.build_payload`），发往 `http://api.timiai.woa.com/ai_api_manage/llmproxy` 的 `glm-5.3-flashx`，Bearer=`TIMI_API_KEY`。**无内容级脱敏**：路径、内部标识、用户原文原样出站；凭据形字符串只在*响应侧* scrub，不影响出站 state。

独立评估：
- 基线对照：pi 派发的 worker 本就把整卡正文发给同一网关、同一凭据下的模型——分诊调用对这类派发**不新增任何披露通道**，只是同一通道多一次 ≤16KB 请求。用户原文/路径对 timi 网关不是新信息。
- 增量暴露：仅 `cli=claude/codex` 派发时，description 因分诊多了一个 timi 收件方（原本只去各自 provider）；但这些 CLI 本也会把 description 发往各自外部 provider，内容并非原本不出机器。净增量 = "多一个内网收件方"。
- 通道性质：网关为内网域明文 HTTP——整个 timi provider 链的既有属性，非本 key 引入（N4）。
- 可关断：`enabled=false` / `points.dp1.enabled=false` 全局与单点开关齐备，默认关闭。
- 定级 **LOW**。内容级脱敏（如路径打码）在此基线下是安全剧场，不建议本轮做代码改动。
- 最小缓解（建议采纳）：README §决策服务补一句「state 由派发描述全文 + type/cli/phase 组成（≤16KB），随请求发送到配置传输后端的承载模型（默认 timi 内网网关 glm-5.3-flashx）」。现状 README 示例写 `"<一句派发场景描述>"`（README.md:537），与实现（全文、16KB 上限）有措辞差——并入 M1 修。

### 审计 2 — 测试真实性

**结论：真实、hermetic；1 处自证式/恒真断言（M3）；非 happy-path-only。**

- Python（130 用例，计数与 CHANGELOG/T-04 一致：69+33+28；pytest nodeids 1016-1145 收录佐证）：
  - hermetic 成立：三套件 autouse fixture 删凭据 env（test_decide.py:52-59 / test_decide_cli.py:37-41）；test_decide.py 另将 `_imported_backend_factory`/`DEFAULT_BACKEND_FACTORY` 置空（结构上不可能构建真实网络后端）；test_decide_backends.py 全量 monkeypatch `_http_post`（FakeHTTP 记录调用并回放）+ `_auth_json_path` 重定向 tmp_path；CLI 子进程测试（test_decide_cli.py `_run_cli`）剥离凭据 env 并重定向 HOME/USERPROFILE → 无凭据可解析 → `entry-unavailable`，不发网络请求（测试正是这么断言的）。
  - 断言真实：契约测试做**整字典相等 + 键序相等**（`test_success_response_has_exact_contract_fields`）；退出码直接断言 0/2；关闭态断言 `backend.calls == []`；退避断言 `clock.sleeps == [2.0, 4.0]`；证据行断言逐字段与键序。未发现"仅未抛异常"式存活断言。
  - 失败面覆盖：连接/超时/429/5xx/非 JSON/上游错误体/坏 `__str__` 异常/不可编码 state/sleep 失败/证据写失败/坏配置全有对应用例。
- TS（21 用例，计数与 T-04 §F-2 一致）：spawn 在 `DecideRunner` seam 桩替——生产装配点（pm-orchestrator.ts:1890/1892）省略 `triageRun` → 生产走真实 `runDecideMw`；测试一律注入 stub（triage-dispatch.test.ts `stubRunner`），关闭态用例断言 `stub.calls` 恒空。派发测试走**真代码路径** + tmp 目录（真实写 task.md/_workers.parallel/ledger），fakePi/fakeCtx 只做输出捕获，不存在「断言自己写的 mock」。套件含 harness.ts + faux provider 的 CI 安检用例（`createHarness`/`registerFauxProvider`）。测试进程内无真实派发（dispatch 只写队列行；无 mw serve 监听 tmp 根）。
- 反例（→ M3）：test_decide_backends.py:448-456 注释宣称验证 `decision.DEFAULT_BACKEND_CLASSES` 映射，但断言是把字面量 dict 与同一 dict 经 getattr 重建后比较（恒真、自证式）；该映射的 B1/B3 类名条目（decision.py:484-488）实际零测试覆盖（唯一相关测试 `test_default_resolver_maps_transport_to_backend_class` 只注入覆盖 llm-transitional 的伪模块）。另 test_decide_backends.py:377 `assert db.DECISION_TYPES_LOCAL in (True, False)` 对 bool 恒真（紧邻的 `_DECISION_IMPORT_ERROR` 一致性断言是真的）。`test_model_self_report_is_never_presented_as_api` 第二个断言（`!= "api"`）被第一个蕴含，偏弱但无害。

### 审计 3 — 默认关闭等价性

**结论：成立，且两侧都是真断言（行为等价断言，非存活断言）。**

- TS：`computeDispatchTriage`（ui-bridge.ts:235-252）在 `readDecidePolicy` 判 disabled 后**先于任何 spawn** 返回 null → `emitDispatchTriage(null)` 即返（ui-bridge.ts:258-259）→ `appendTriageReceipt` 恒等（ui-bridge.ts:279-282）。triage-dispatch.test.ts:325-373 关闭态 3 用例断言：`stub.calls` 恒空（两处独立用例）、`dispatch_worker` 回执**整串相等**（含 task.md 路径与字面文案）、`auto-decisions.jsonl` 不存在、`messages` 恒空、frontmatter `"type: coding\n"` 逐字节；`enabled=false` 与 `points.dp1.enabled=false` 同批覆盖。
- Python：`mw decide run` 未配置 → rc=0 + `reason=disabled`（`test_run_unconfigured_reports_disabled_exit_zero` 直接断言 rc 与 reason）。doctor 未配置 → section 恒 `{"exists": False}`（mw_common.py:1599 `_doctor_decide` 早退）→ `format_doctor_text` 不发 `triage:` 行（mw_common.py:4590-4603 仅 `exists` 才渲染）；zero-perturbation 由 `test_doctor_unconfigured_is_zero_perturbation` 锁定为**逐字节相等**（带/不带 decide section 两次渲染比较）；坏配置不翻 healthy 由 `test_doctor_broken_config_is_informational_only` 断言（issues/healthy 与未配置完全相同）。
- 语义澄清（N2）：「零文件写入」的范围是**派发路径**（成立）；**显式**调用 `mw decide run` 时即使未配置也会按 D-005「每次调用一行」追加一条 `available=false, reason=disabled` 证据行（decision.py:651 → `_emit` → `_append_evidence`:940）。这是新子命令的显式调用行为，与 AC-009「框架行为不变」不冲突，但严格读者应知道这一区分。
- 新增性读：每次派发多一次 `.mw/decide.json` 读（`readDecidePolicy`）——只读，无 spawn/写/网络，量级可忽略（记录为事实，不列为问题）。

### 审计 4 — 诚实性与凭据

**结论：如实。1 处文档完备性缺口（M1）与 1 处凭据回显不一致（M2）为 minor。**

- 覆盖面声明：packages/coding-agent/CHANGELOG.md:83 明写 "Coverage is the two PM-initiated dispatch entries (2/15 dispatch sites, structural); the conductor's automatic dispatch points are out of scope for this wave"；证据 §E-1 同；design D-006 定档一致。**未发现任何「全量覆盖」式宣称**。缺口：multi-workers README §决策服务（README.md:486-571）通篇未提 2/15 与 conductor 13 点未覆盖——只读 README 的读者无法得知覆盖边界（→ M1）。
- B1 恒 entry-unavailable：三条路径全堵死——`entry_probe` 未开（默认）不发请求即 entry-unavailable；无 key → entry-unavailable；probe 得 2xx 也**拒绝当作成功**（"entry shape is unconfirmed" 仍 entry-unavailable，decision_backends.py `LLMProxyAnthropicBackend.decide`）。B1 无任何 available=true 出口。README.md:510 / 两处 CHANGELOG 均如实写「不得静默当作成功」。`test_b1_is_entry_unavailable_without_request` 断言零请求。
- model-self-report 不用于门控：README.md:555-559 写明硬规则（`confidence_source != "api"` 不得用于门控）；呈现层 `confidenceSourceLabel`（triage-client.ts:319-325）对 model-self-report 固定带「模型自报置信度（不用于门控）」；TS 侧唯一「门控」是 disagreement（类型不一致才唤醒 PM），confidence 从不参与判定；Python 侧 `_aggregate_confidence` 注释明示 "Never used for gating"。未发现把自报置信度当判据的代码或文案。
- 凭据面逐出口核查：
  - 证据行（triage-decisions.jsonl）：字段封闭；transport/model 经 `_redact`（env 凭据形值替换 `<redacted>`）；answers 经 enum/int/bool 校验，key 字符串无法通过。`test_credentials_never_reach_evidence_or_detail` 注入真实格式 key 断言不落盘、不出现在响应。
  - ledger detail（TS）：`formatTriageLedgerDetail` 只含 dp/triage_type/triage_risk/dispatched_type/disagreement/confidence_source。
  - doctor / show：`_decide_show_payload` 对 `extras.api_key` 回显 `<redacted>`（mw.py:833-840；`test_show_redacts_api_key` 断言）；doctor section 不含 extras。
  - 错误文本：BackendOutcome.detail 经 `_sanitize`（key 替换）+ `_scrub_detail`（bearer/sk- 形态 + 截断 200）；且 **detail 根本不进 CLI 响应**（响应字段集无 detail，`_decide_run` 只打印 response）——scrubbed detail 实际不出进程。`DecisionInputError` 文案只回显调用方自己的入参。probe 行只有 target/method/path/status/verdict（测试断言 `TEST_KEY not in json.dumps(row)`）。
  - **例外（M2）**：`mw decide set --json` 把写入的 raw 配置**原样回显 stdout**（mw.py:947），含 `api_key` 明文——与 show 的 `<redacted>` 模式不一致；且 `KEY=VALUE` 形态使 key 进入进程 argv。均为用户自致动作（README 已写「不推荐写盘」），无环境性泄漏，但模式不一致值得修。

### 抽查结果（2 条 AC：静态核对 + 缓存佐证）

先声明：本会话无 shell，无法真跑（→ M4）。做法 = T-04 记录输出 ↔ 当前代码/测试断言逐条比对 + `.pytest_cache` 佐证（nodeids 1016-1145 收录全部 130 条 decide 用例；lastfailed **无任何** test_decide 条目——与「最近一次全绿」一致，但不等于新跑）。

**AC 默认关闭等价性（AC-007 关闭态 / AC-009）——一致**：
- T-04 记未配置 `mw decide show` 输出 `decide: disabled (.mw/decide.json not present)` ↔ mw.py:878 字面一致。
- T-04 记 doctor 未配置无 `triage:` 行 ↔ mw_common.py:4590-4603 条件渲染 + `_doctor_decide` 早退；zero-perturbation 测试存在且断言逐字节相等（nodeid 1125 在缓存中，lastfailed 无记录）。
- T-04 记关闭态 `triage=null, frontmatter="type: coding\n", spawn 调用 0, ledger 0 行, sendMessage 0 次` ↔ triage-dispatch.test.ts:325-373 三用例逐条断言这些量。
- 未发现任何与 T-04 记录矛盾之处。

**AC fail-soft 退出码（AC-002）——一致**：
- T-04 记 B1 `entry-unavailable` → RC=0 ↔ `_decide_run`（mw.py:794-812）对完成态（含 available=false）恒 return 0；`test_run_unavailable_still_exits_zero` 断言 rc==0 且 reason 正确。
- T-04 记未知问题类型 stderr `[mw decide run] question 'q1' has unknown type 'bogus'` → RC=2、stdout 无响应体 ↔ `DecisionInputError` → stderr + return 2（mw.py:805-807）；`test_run_invalid_question_type_exit2` / `test_run_request_missing_questions_exit2` 直接断言 2；子进程级 `test_cli_decide_set_then_run_stdin_smoke` 断言配置后无凭据 → available=false + rc 0。
- 失败矩阵归一化（不可达/超时/429/5xx/非 JSON/上游错误体）由 `test_backend_failure_matrix_is_normalized` 参数化覆盖（nodeids item0-item4 与 T-04 所列一致）。
- 未发现矛盾。

**抽查判定：无「与 T-04 证据不一致」项 → 按卡片标准不构成 blocker**；运行时确认缺位见 M4。

### 分级清单

**blockers**：无。

**majors**：无。

**minors**：
- **M1** 文档完备性/数据流披露：README §决策服务未声明 DP-1 覆盖面（2/15、conductor 13 点未覆盖），且请求示例写「<一句派发场景描述>」而实现为全文 ≤16KB。文件：packages/multi-workers/README.md:486-571（示例 :537）。复现：`grep -n "2/15\|conductor" packages/multi-workers/README.md`（无命中）对照 packages/coding-agent/CHANGELOG.md:83（有）。影响：README-only 读者无法得知覆盖边界与真实出站数据面；一句话可修（覆盖面声明 + 审计 1 的数据流披露句）。
- **M2** 凭据回显不一致：`mw decide set --json` 将含 `api_key` 的 raw 配置明文回显 stdout；`KEY=VALUE` 形态又使 key 进进程 argv。文件：packages/multi-workers/mw.py:947（对照 show 的脱敏 mw.py:833-840）。复现：`python packages/multi-workers/mw.py decide set --project X --json api_key=sk-testvalue123` → stdout 含明文；`python packages/multi-workers/mw.py decide show --project X --json` → `<redacted>`。影响：用户自致、无环境性泄漏（证据/ledger/doctor/日志均无 key）；但与自家「回显面不落明文 key」模式不一致。建议 set --json 同样脱敏，或 README 加 argv 警告。
- **M3** 自证式断言：test_decide_backends.py:448-456 宣称验证 `decision.DEFAULT_BACKEND_CLASSES` 实为恒真比较（字面量 dict == 自身 getattr 重建），B1/B3 类名条目（decision.py:484-488）零真实覆盖；另 test_decide_backends.py:377 `DECISION_TYPES_LOCAL in (True, False)` 恒真。复现：`cd packages/multi-workers && python -m pytest -q test_decide_backends.py::test_integrates_with_decision_config_and_transport_names`（绿，但覆盖为虚）。影响：极小（映射拼错时 B1/B3 仍以 entry-unavailable 呈现，reason 不变，detail 不出进程），但制造虚假覆盖信心；建议改为直接断言 `decision.DEFAULT_BACKEND_CLASSES` 值域或删该注释。
- **M4** 评审过程限制（非实现缺陷）：本 worker 无 shell，卡片三条验收命令与运行时重跑未执行；抽查以静态核对 + pytest 缓存佐证替代。复现：无（本会话工具面事实，trace.log 可证）。影响：质量门运行时一腿缺位——PM settle 前建议自行执行：
  - `cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py`（预期 130 passed）
  - `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts`（预期 21 passed）
  - `cd H:/git/Multi-Workers && git status --porcelain`

**notes**：
- **N1** 审计 1 落点：出站 state = description 全文 + type/cli/phase，双重上限（TS 16,000B / Python 预算 16,384B），去向 = 配置传输后端的承载模型（默认内网网关 glm-5.3-flashx）；对 pi 派发不新增披露通道，对 claude/codex 派发多一个内网收件方；风险 LOW，不建议代码级脱敏，采纳 M1 披露句即可。
- **N2** 显式 `mw decide run`（含未配置项目）按 D-005 每调用追加一条 `reason=disabled` 证据行（decision.py:651/940）；「零文件写入」承诺范围为派发路径。
- **N3** `emitDispatchTriage` 在 task.md 写入/入队之前调用（ui-bridge.ts:2560）：若后续 write-face 拒绝或入队失败，triage-suggestion ledger 行（争议时含 PM 唤醒）已落，而对应派发从未发生。advisory 语义下无碍，但 ledger 消费者不应从 triage 行推断「派发已落地」。
- **N4** 网关为明文 HTTP（`http://api.timiai.woa.com/...`），bearer key 与载荷网线上不加密——整个 timi provider 链的既有属性，非本 key 引入，仅记录。
- **N5** 真实 `runDecideMw`（findMwPy/PYTHON_EXE 解析、`-X utf8`、stdin 管道、timeout 映射）在全部 TS 测试中被 seam 桩替，自身零测试覆盖；「state 只走 stdin 不进 argv」由代码检视成立（triage-client.ts:131-153），无测试锁定。

## 残留与未验证

1. **运行时重跑缺位**（M4）：两条验收套件与 `git status --porcelain` 未在本会话执行；静态核对未发现与 T-04 矛盾，`.pytest_cache`（nodeids 全量收录 130 条、lastfailed 零 test_decide 条目）与「上次全绿」一致——这是佐证不是重跑。
2. vitest 无持久缓存可查，21 用例状态仅由 T-04 §F-2 记录 + 测试代码检视支撑。
3. `npm run check` / multi-workers 全量套件 / T-04 §F-4 他窗 biome findings：本轮范围外，未验证。
4. B2 真实链路（llmproxy 当前可用性）未做真实调用验证——评审会话不应消耗模型调用；以 T-04 §A-1 真实证据 + hermetic 测试为准。

## 上下文来源

- `.agenticdoc/mw-jev-provider-integration/spec.md` §2/§3/§4、`design.md` D-002/D-004/D-005/D-006/D-007（读全）
- `evidence/runs/verify-mw-jev-provider-integration-20261016.md`（T-04，读全）
- 实现：`decision.py`（读全）、`decision_backends.py`（读全）、`mw.py:607-990`（decide 段）、`mw_common.py:1599-1686`（_doctor_decide）与 `:4348-4378`、`:4588-4603`（doctor 装配/渲染）、`triage-client.ts`（读全）、`ui-bridge.ts:188-282 / 1257-1480 / 2400-2603 / 2899-3102`、`pm-orchestrator.ts:470-657`
- 测试（读全）：`test_decide.py`、`test_decide_backends.py`、`test_decide_cli.py`、`packages/coding-agent/test/suite/triage-dispatch.test.ts`、`test/suite/harness.ts`（头部）
- 文档：`packages/multi-workers/README.md:486-575`、两个 CHANGELOG 的本 key 条目（multi-workers CHANGELOG.md:100、coding-agent CHANGELOG.md:83）
- 佐证：`packages/multi-workers/.pytest_cache/v/cache/{nodeids,lastfailed}`、本任务 trace.log/run.json

## 未覆盖面声明

按卡片要求：
- 不审 conductor 派发链与 PM 主循环本身的既有设计；
- 不审 D-1 上游（llmproxy/timiai）实现；
- 不做压测；不审本轮未交付项（conductor 侧挂点、`mode: async`、B3 真实链路、`box` 问题类型、TS 面板逐字同步 doctor 行）；
- 不重跑 multi-workers 全量套件。

本轮额外（因工具面限制）：
- 不跑任何真实模型调用；不执行 npm run check / git 状态检查；
- 运行时重跑由静态核对 + pytest 缓存佐证替代（M4，残留 §1）。

---

## PM 处置（2026-10-16，收尾阶段追加）

| 项 | 分级 | 处置 | 证据 |
| --- | --- | --- | --- |
| M1 README 缺覆盖面/数据流披露 | minor | **已修**：`packages/multi-workers/README.md` 新增「### 覆盖面与数据流」节（2/15 明确声明 + 13 个 conductor 派发点未接入 + `state` 经内网 llmproxy 发往 B2 的数据流与"勿放敏感原文"提示） | README「决策服务（mw decide）」小节 |
| M2 `set --json` 回显 api_key 明文 | minor | **已修**：新增 `_decide_redact_secrets`（`mw.py`，与 `show` 的 `<redacted>` 模式一致），`set --json` 走该函数；落盘值不变（操作员显式要求写入）。新增回归用例 `test_set_redacts_api_key_in_json_echo` | `mw.py` 的 `_decide_redact_secrets`；`test_decide_cli.py` |
| M3 `test_decide_backends.py` 自证式断言 | minor | **已修**：把两个相同字面量比较替换为真实不变量——遍历 `decision.DEFAULT_BACKEND_CLASSES` 断言每个类名在 `decision_backends` 中可解析（防改名后静默降级为 `entry-unavailable`） | `test_decide_backends.py` |
| M4 评审会话无 shell，验收命令未执行 | minor | **已闭合**：PM 直执重跑——`python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py` → **131 passed**；`vitest --run test/suite/triage-dispatch.test.ts` → **21 passed**（与评审预期一致） | 本轮 PM 实机输出 |

### 未处置（保留为 note，不影响 PASS）

- notes 1–5（评审原文）：留待后续波次或作为已知边界接受；其中"conductor 侧 13 个派发点未接入"已作为明确遗留写入 `achieved.md`。
