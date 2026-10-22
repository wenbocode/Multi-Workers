# T-06 最终状态全量复审（QG 验收门 + 代码 review）

- key: mw-jev-provider-integration · task: jev-t06-qg-review-full · type: review · 2026-10-16
- **评审方式声明（诚实性前提）**：本 worker 会话工具面为只读（read/find/grep/ls + worker_file），**无 shell**。卡片「要求」节的三条命令与各 AC 的「自跑」无法在本会话执行（与上轮 T-05b M4 同因）。验证方式 = **静态核对**（逐文件读实现与测试）+ `.pytest_cache`（nodeids/lastfailed）佐证 + T-04 记录输出比对 + PM 在快修 M1/M2/M3 后的实机重跑记录（131 passed / 21 passed，见 quality-gate-report-20261016.md「PM 处置」）。本报告未伪造任何命令输出；所有「复现命令」均为 PM 可自行执行的验证命令。

## 结论

**PASS（有保留）**：**0 blockers / 0 majors / 2 minors / 8 notes**。

- 第一部分 QG（10 项）：AC-001..AC-011 逐条静态判定全部满足；三条「自跑」验收命令以「测试断言 + T-04 实机记录 + pytest 缓存」三角佐证，无任何与记录矛盾项（m2 为过程限制，非实现缺陷）。快修 M1/M2/M3 四处改动全部核实为**真修复且无回归**。
- 第二部分代码 review（5 项）：错误分类/预算/退避与 D-004 一致且不可重试类从不重试；B2 契约干净（禁带字段、box 不发请求）；TS 调用面真 kill + mw-runner 复用；反馈三层与 D-005 一致、唤醒条件正确；可维护性可接受。1 条 design 漂移 minor（B2 缺「回喂校验错误重发」步骤）。
- 判定依据：所有 findings 均不影响 AC-001..AC-012 的满足性；不构成 blocker/major。

## 证据

### 第一部分：QG 验收门（AC 层）

**1. AC-001 契约 — PASS（静态）**
- CLI = API：`mw.py::_decide_run`（mw.py:794-812）只做请求解析与打印，校验与响应构造全部走 `decision.DecisionClient.decide()`（decision.py:569），无第二份校验实现。
- 四型问题：`QUESTION_TYPES = {choice, score, noul, box}`（decision.py:105-106）；choice/score/noul 取值强制在 `_validate_answers`（decision_backends.py:383-419，enum/range/bool 强制，测试 `test_b2_score_and_noul_coercion`、`test_b2_enum_violation_is_bad_response_retryable`）；`box` 透传后端并返回 `unsupported-question-type`（`test_box_type_is_forwarded_to_backend`）。
- `confidence_source`：由后端声明（B1/B3=`api`、B2=`model-self-report`）、客户端如实传播且不虚构（decision.py:659-667，`test_confidence_source_api_is_propagated_verbatim` / `test_unknown_backend_confidence_source_is_not_fabricated`）。
- 复现：`cd packages/multi-workers && python -m pytest -q test_decide.py -k "contract or confidence or wave1 or box"`。

**2. AC-002 fail-soft — PASS（静态 + 记录佐证；自跑缺位见 m2）**
- 三条路径均有直接断言：缺 `questions` → rc 2（`test_run_request_missing_questions_exit2`，mw.py:714-716 缺字段检查）；未知问题类型 → rc 2 + stderr（`test_run_invalid_question_type_exit2`，`DecisionInputError` → mw.py:805-807）；未配置项目 `run` → rc 0 + `reason=disabled`（`test_run_unconfigured_reports_disabled_exit_zero`）。
- `available=false` 恒 rc 0（`_decide_run` 对完成态恒 return 0；`test_run_unavailable_still_exits_zero`）；唯一抛出异常是 `DecisionInputError`（decision.py 文档 + `test_backend_exception_never_escapes_even_with_buggy_str`）。
- T-04 §A-4 实机记录与上述一致（entry-unavailable → RC=0；bogus type → RC=2）。
- 复现：`python -X utf8 packages/multi-workers/mw.py decide run --project <dir>`（stdin 分别喂缺 questions / bogus type / 合法请求）。

**3. AC-003 传输抽象 — PASS（静态 + T-04 实机矩阵）**
- 三后端独立类、同一 `BackendOutcome` 协议（decision_backends.py:431/515/570）；配置 `transport` 选择（decision.py:206-208），未配置默认 B2。
- B1：默认（`entry_probe=false`）不发请求即 `entry-unavailable`（`test_b1_is_entry_unavailable_without_request` 断言 `fake.calls == []`）；probe 得 2xx 也拒绝当作成功（decision_backends.py:566-573「entry shape is unconfirmed」仍 entry-unavailable）。
- B3：无凭据 `entry-unavailable`（`test_b3_without_credential_is_entry_unavailable`）；官方形状解码有正向测试（`test_b3_decodes_official_answers`）。
- probe 矩阵 vs D-1：T-04 §A-3 实机矩阵复现 spec §4 全部锚点（jev `/v1/messages`→429、jev `/responses`→200+litellm 错误=upstream-error、`/v1/systemone`→404）；hermetic 测试锁定矩阵形状与无凭据全 entry-unavailable（`test_probe_matrix_shape_and_coverage` / `test_probe_matrix_without_credential_reports_unavailable`）。本轮未复跑真实 probe（见 m2/残留）。
- 复现：`python packages/multi-workers/mw.py decide probe --project <dir> --json`。

**4. AC-005 凭据最小面 — PASS（静态；M2 修复核实生效）**
- `set --json`：`_decide_redact_secrets`（mw.py:833-842）把 `api_key` 置 `<redacted>` 后才回显；回归用例 `test_set_redacts_api_key_in_json_echo` 断言 stdout 无明文 + echo 为 `<redacted>` + **落盘值未被误改**（第三个断言直接锁定「修复不影响写入」）。
- `show --json`：`_decide_show_payload` 对 `extras.api_key` 脱敏（mw.py:853-856，`test_show_redacts_api_key`）。
- probe：行字段封闭（target/method/path/status/verdict），`test_probe_matrix_shape_and_coverage` 断言 `TEST_KEY not in json.dumps(row)`；无凭据时零网络（`test_probe_matrix_without_credential_reports_unavailable` 用 boom 桩断言绝不触网）。
- 证据行/ledger/doctor 无 key：`test_credentials_never_reach_evidence_or_detail`（注入真实格式 key 断言不落盘不出现在响应）。
- 复现：`python -X utf8 packages/multi-workers/mw.py decide set --project %TEMP%\t --json enabled=true api_key=sk-x && mw.py decide show --project %TEMP%\t --json`。

**5. AC-007 默认关闭等价 — PASS（静态）**
- 未配置 `show` → `decide: disabled (.mw/decide.json not present)`（mw.py:889-890 字面；`test_show_disabled_when_unconfigured` + 子进程级 `test_cli_decide_show_smoke_unconfigured`）。
- 未配置 doctor → `_doctor_decide` 早退 `{"exists": False}`（mw_common.py:1664-1666），`format_doctor_text` 仅 `exists` 才渲染（mw_common.py:4590-4603）→ 无 `triage:` 行；`test_doctor_unconfigured_is_zero_perturbation` 锁定。
- 复现：`python mw.py decide show --project <unconfigured>` / `python mw.py doctor --project <unconfigured> | findstr triage`（预期无输出）。

**6. AC-009 逐字节等价断言真伪 — 真断言，非「未抛异常」**
- TS：`triage-dispatch.test.ts` 关闭态用例对 `dispatch_worker` 回执做**整串 `toBe(<含路径的字面文案>)`**、frontmatter `toBe("type: coding\n")`、`stub.calls`/`messages`/ledger 文件存在性全空断言 —— 逐字节级别。
- Python：`test_doctor_unconfigured_is_zero_perturbation` 断言带/不带 decide section 两次 `format_doctor_text` **字符串相等** —— 逐字节级别。
- 判定：两侧都是行为等价断言，不是存活断言。

**7. AC-011 测试真实性 — PASS（静态读测试 + 缓存佐证；实跑缺位见 m2）**
- 计数核对：test_decide.py 69 + test_decide_backends.py 33 + test_decide_cli.py 29 = **131**，与测试文件逐函数清点一致、与 `.pytest_cache/v/cache/nodeids`（1016-1146 行收录全量 decide 条目）一致、与 PM 快修后实机重跑「131 passed」一致；`lastfailed` **零** test_decide 条目。TS：triage-dispatch.test.ts 逐 `it()` 清点 = **21**，与 T-04 §F-2 及 PM 重跑记录一致。
- 断言质量：契约测试整字典 + 键序相等；退出码直接断言 0/2；关闭态断言 `backend.calls == []`；退避断言 `clock.sleeps == [2.0, 4.0]`；证据行逐字段 + 键序。未发现新的恒真/自证式断言（残留见 n3）。
- M3 修法核实：`test_integrates_with_decision_config_and_transport_names`（test_decide_backends.py:448-459）现在是**真不变量**——遍历 `decision.DEFAULT_BACKEND_CLASSES` 断言每个类名在 `decision_backends` 可解析（改名会红），原字面量自比较已删除。✓
- 未覆盖分支（均为 note 级）：`_classify_body_error` 的 rate-limit/timeout 标记分支无直接用例（n8）；B1 `entry_probe=true` 全路径无直接用例（n4）；真实 `runDecideMw` 全部被 seam 桩替（n5）。
- 复现：`cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py`（预期 131 passed）；`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts`（预期 21 passed）。

**8. 诚实性与上游表述 — PASS**
- 覆盖面 2/15 + 13 个 conductor 未接入点：README「### 覆盖面与数据流」（README.md:561-565）明写「本波 2/15」「conductor 的 13 个自动派发点尚未接入」；coding-agent CHANGELOG.md:83 同义英文声明；T-04 §E-1 一致。未发现任何全量覆盖宣称。
- B1 无 `available=true` 出口：`LLMProxyAnthropicBackend.decide`（decision_backends.py:515-573）7 个 return 点全部 `available=False`（disabled / 未开 probe / 无 key / timeout / 连接错 / probe 错误分类 / probe 2xx 仍 entry-unavailable）。逐行核实。
- `model-self-report` 固定标注：`confidenceSourceLabel`（triage-client.ts:319-325）对 model-self-report 固定输出「模型自报置信度（不用于门控）」；回执恒带 label + 原始 `confidence_source`（`formatTriageReceipt`）；README.md:555-559 硬规则原文；TS 侧唯一判定是 disagreement，confidence 从不参与门控；测试断言 api 来源**不带**该标注（反向锁定）。

**9. 他窗写入面 — PASS（静态）；git 状态未跑（见 m2）**
- `mw.py`：全部 decide 代码在 :667-990（cmd_decide 块）+ :7442-7472（argparse 注册）+ :7509（dispatch 表一行）；`cmd_model`（:3822）与 `_goal_gate_install`（:5288）函数体内**零** decide 引用（grep 全文核实）。
- `ui-bridge.ts`：triage 代码仅在 :188-282、:1345-1439（planDispatchFrontmatter 挂点）、:2334-2600（dispatch_worker）、:2907-3100（/worker）；`/mw model` 段（卡片写 :3302-3391，现因文件增长位于 :3419-3509）逐行读取，**零** triage/decide 引用。
- T-04 §C-3 记录的 numstat（mw.py +344/-0、mw_common +107/-0、ui-bridge +120/-3、pm-orchestrator +23/-1，TS 删除行均为 union 签名语法替换）与本轮静态定位一致。
- `git status --porcelain` 本会话无法执行 → 残留 §1；建议 PM settle 前自行执行。

**10. 快修 delta 复核（M1/M2/M3）— 全部真修复、无回归**
- M2 `_decide_redact_secrets`（mw.py:833-842）：代码 + `test_set_redacts_api_key_in_json_echo`（含落盘值不变断言）双核实。✓
- M3 `test_decide_backends.py` 断言替换：真实不变量 loop 已在位（见第 7 项）。✓
- M1 README「覆盖面与数据流」（README.md:561-570）：2/15 + 13 点 + 数据流披露（state 全文经内网 llmproxy 发往 B2、勿放敏感原文）齐备。✓
- 回归面：131 条 decide 用例计数与缓存/记录一致，lastfailed 无 decide 条目；无迹象表明三处快修引入回归。

### 第二部分：代码 review（实现质量层）

**11. Python 错误分类 — 符合 D-004**
- `_classify`（decision_backends.py:301-331）：404→entry-unavailable 不可重试（detail 带 content-type）；400/401/403/405/413/415/422→upstream-error 不可重试；429→rate-limited 可重试；408→timeout 可重试；409/425/5xx→upstream-error 可重试；2xx 非 JSON→bad-response 不可重试；2xx 带 error 体/litellm 文本→按 body 分类；其它 3xx/4xx→entry-unavailable 不可重试。与 D-004 八类处置逐条一致。
- 不可重试类从不重试：client `if not outcome.retryable or attempts > cfg.max_retries`（decision.py:648）；`test_non_retryable_outcome_is_not_retried` 锁定。退避指数 base 2、可配；`timeout_s`/`max_retries`/`max_questions`/`max_state_bytes`/`max_tokens` 全可配且有界；退避会超墙钟时立即 `budget-exhausted` 不再睡（`test_retry_is_skipped_when_backoff_exceeds_time_budget`）。
- 静默失败面评估：吞掉的只有（a）证据行写失败（D-005 best-effort 契约，response 仍带 reason）；（b）backend 异常归一为 reason（detail 不出进程，见 n2）；（c）TS ledger 写失败 console.error（沿用 recordDispatchAlarm 既有契约）。面有界，每处有机器可见 reason 或契约豁免，未发现会掩盖真实缺陷且不可诊断的路径。

**12. Python B2 契约 — 干净；1 条 design 漂移（m1）**
- 禁带字段：`build_payload`（decision_backends.py:447-473）只含 model/max_tokens/temperature/system/tools/tool_choice/messages；`test_b2_request_body_omits_forbidden_fields_and_forces_tool` 逐一断言 `response_format`/`state`/`questions`/`store` 不在请求体。
- 解析：tool_use 块优先且忽略 thinking/text（`test_b2_success_reads_tool_use_ignoring_thinking_and_text`）；text 回退（`test_b2_text_fallback_when_tool_use_block_missing`）；200 带 error 体按 body 分类（两条用例）。
- `box` 不发请求即拒：`_unsupported_types` 检查在凭据解析与 HTTP 之前（decision_backends.py:483-491），`test_b2_box_question_is_unsupported_and_never_sent` 断言 `fake.calls == []`。✓
- 漂移：D-002 解析规则含「不合格 → **回喂校验错误重发 1 次**」步骤，实现为 tool_use→text 回退→bad-response（retryable，由 client 整体重试补偿），未做带校验错误的回喂 → m1。

**13. TS 调用面 — 合格**
- 硬超时真 kill：`runDecideMw` 用 `spawnSync(..., { timeout: request.timeoutMs, windowsHide: true })`（triage-client.ts:139-146）；Node spawnSync 的 timeout 会终止子进程，`error.code === "ETIMEDOUT"` 归一为 `timedOut` → `unavailable("timeout")`。默认 20s、`timeout_s` 可覆盖（`readDecidePolicy`）。
- stdin 写法：请求 JSON 经 `input` 走 stdin；argv 只有 `--project/--dp/--json`（triage-client.ts:133-137），state 永不进 argv。
- 异常归一：JSON 解析失败→bad-response；非零退出→upstream-error；spawn 失败（error/ENOENT/mw.py 未找到）→upstream-error；runner 抛异常→upstream-error（`triageDispatch` 外层 catch）；五形态参数化测试 + throwing-runner 用例锁定。
- state 截断：`MAX_TRIAGE_STATE_BYTES=16_000`，`boundTriageState` 按字节收缩 + `[state truncated]` 后缀 ≤16KB（测试断言 ≤16_000）；低于 Python 16384 预算，不会误触 budget-exhausted。
- mw-runner 复用：`findMwPy()`（MW_PY → `.mw-py-path` sidecar → repo 相对）+ `PYTHON_EXE` + `windowsHide` + `-X utf8` 全部来自/对齐 `shared/mw-runner.ts`，无裸 spawn。✓ 残留：真实 runner 零直接测试（n5）。

**14. TS 反馈语义 — 符合 D-005 三层**
- 层 1（结构化 JSONL）：唯一写者是 Python 决策客户端；TS 侧不触碰 triage-decisions.jsonl（triage-client.ts 头注释 + 代码核实零写）。
- 层 2（回执 echo）：`appendTriageReceipt` 拼进 `dispatch_worker` 返回值（ui-bridge.ts:2597-2600）与 `/worker` notify（:3096-3099）；文案带「旁路建议，未据此改派发」+ 来源标注；不可用时恒等（`formatTriageReceipt` 空串 → 字节不变）。
- 层 3（ledger/争议唤醒）：`emitDispatchTriage`（ui-bridge.ts:258-275）——可用时恒写一条 `triage-suggestion` 五元组行；`deliverPmAlert` **仅** `disagreement && alertOnDisagreement` 时触发（配置默认 true，`points.dp1.alert_on_disagreement=false` 可静音）；测试三分支锁定（争议 1 行+1 wake / 一致 0 wake / 静音 0 wake）。
- `NOTICE_DISPATCH_ALARM_KINDS` 含 `triage-suggestion` 与 `triage-unavailable`（pm-orchestrator.ts:543-551），文案经 `describeDispatchAlarm` 且读「提示」非「已拒绝」（:563-610、:617-621）→ PM 面板可见性正确。
- 不可用零通知：默认静默（无回执、无 ledger、无 wake）；仅 `triage_notify_on_unavailable=true` 时写一条 `triage-unavailable` 行且**永不 wake**（测试两分支锁定）。

**15. 可维护性 — 可接受（3 条 note）**
- 证据行读取不重复：decision.py 只有写者（`_append_evidence`）；读侧集中在 mw_common（`decide_last_evidence` + `_doctor_decide`）与 mw.py show。`decide_evidence_path`（mw_common.py:1601-1617）是 `DecisionClient._evidence_file` 的**文档化镜像**（8 行，注释言明 mirror）——可改为委托 decision.py 的共享 helper 以防漂移（n7），现状风险低。
- 死码/未使用导出：`credential_status`（decision_backends.py:169）生产零调用、仅测试使用（n1）——设计上是可打印的诊断 API，留作 doctor 未来接入面，可接受但应知情。
- 命名与注释一致性：抽查 decision.py/decision_backends.py/mw.py decide 段/mw_common decide 段/triage-client.ts/ui-bridge.ts 挂点注释，均与实现一致；`reason` 冻结集注释解释了 budget-exhausted 与 unsupported-question-type 的来源差异，准确。

### 分级清单

**blockers**：无。

**majors**：无。

**minors**：
- **m1** B2 解析缺少 D-002 的「回喂校验错误重发 1 次」步骤。文件：packages/multi-workers/decision_backends.py:483-513（`LLMTransitionalBackend.decide` 解析段；design.md D-002 解析规则明列该步骤）。复现：读 design.md D-002 对照实现；`python -m pytest -q test_decide_backends.py -k b2`（绿，但设计步骤缺位）。影响：tool_use 校验失败时少了「带校验错误回喂模型」的一次纠错机会，直接掉到 text 回退/整体重试；无 AC 破坏，行为仍 fail-soft 且有界。建议处置：后续波补该步骤（把 `_validate_answers` 的 err 拼进重发 user content），或在 design D-002 显式记录「由 client 整体重试替代」。
- **m2** 评审过程限制（非实现缺陷）：本 worker 无 shell，卡片「要求」三条命令（pytest 三套件 / vitest 单用例 / `git status --porcelain`）与各 AC「自跑」（AC-002 三条、AC-003 probe、AC-005 set/show/probe、AC-007 show/doctor）未在本会话执行。替代验证 = 静态核对 + `.pytest_cache`（131 条 decide nodeids 全收录、lastfailed 零 decide 条目）+ T-04 实机记录 + PM 快修后实机重跑记录（131/21 全绿）。复现：无（本会话工具面事实）。影响：质量门运行时一腿由记录佐证而非本轮新跑；与上轮 M4 同性质，且 PM 已在快修后实跑过一次。建议处置：PM settle 前自行执行卡片「要求」节三条命令。

**notes**：
- **n1** `credential_status` 导出但生产零调用（仅 test_credential_status_is_boolean_only）。文件：decision_backends.py:169/890。影响：诊断 API 空挂；知情即可。
- **n2** `BackendOutcome.detail`（脱敏+截断后）在 CLI 响应与证据行中均无字段承载——后端诊断文本（HTTP 状态/body 摘要）算了但丢。符合 D-003 响应契约（无 detail 字段），但故障诊断只剩 reason 分类。文件：decision.py:727-744（构造后不入 response/evidence）。建议：后续在 `show`/doctor 的 last 记录里可选暴露脱敏 detail。
- **n3** `test_frozen_outcome_shape_is_exported` 内 `assert db.DECISION_TYPES_LOCAL in (True, False)` 对 bool 恒真（M3 主项已修；紧邻的 `bool(_DECISION_IMPORT_ERROR) is DECISION_TYPES_LOCAL` 是真一致性断言）。文件：test_decide_backends.py:377 附近。影响：无害的空断言，建议顺手删除。
- **n4** B1 `entry_probe=true` 全路径（probe 超时/连接错/2xx 仍 entry-unavailable）无直接测试用例；「B1 无 available=true 出口」目前由代码逐行核实而非测试锁定。文件：decision_backends.py:534-573。建议：补一条 entry_probe=true + 2xx 仍拒的用例。
- **n5** 真实 `runDecideMw`（findMwPy/PYTHON_EXE/stdin/timeout 映射）在全部 TS 测试中被 seam 桩替，自身零直接覆盖；「state 只走 stdin」由代码检视成立（triage-client.ts:131-153）。上轮 N5 原样延续。
- **n6** `mw decide set api_key=KEY` 仍使 key 进入进程 argv（M2 只修了 stdout 回显）。用户自致动作；README.md:517-519 已写「不推荐写盘」但未提 argv。建议：README 加一句 argv 提示，或长期改为交互/文件输入。
- **n7** `mw_common.decide_evidence_path` 与 `DecisionClient._evidence_file` 是并行实现（文档化镜像）；两处逻辑目前一致（本轮核对），改动 evidence 解析时需同步两处。文件：mw_common.py:1601-1617 vs decision.py:921-933。
- **n8** `_classify_body_error` 的 rate-limit/timeout 标记分支（2xx body 含 "rate limit"/"timeout" 文本）无直接用例；现有 200-with-error-body 用例走的是 overload/兜底分支。文件：decision_backends.py:276-297。影响小（probe 与 run 的分类兜底仍正确）；建议各补一条标记命中用例。

### 两部分小结

**QG 小结**：AC-001（契约/四型/来源）、AC-002（fail-soft 退出码）、AC-003（三后端+probe 矩阵）、AC-005（凭据零明文，M2 修复核实生效）、AC-006（预算退避）、AC-007（默认关闭等价）、AC-008（证据行+既有通道）、AC-009（逐字节真断言）、AC-010（doctor 行+文档）、AC-011（131+21 测试真实、M3 修法成立）、AC-012（D-1 显性化）逐条静态判定满足；诚实性三项（2/15、B1 无成功出口、自报置信度标注）全部如实。快修 M1/M2/M3 四处均为真修复且无回归迹象。唯一保留是运行时验证由记录佐证而非本轮新跑（m2）。

**代码 review 小结**：Python 侧错误分类/重试/预算与 D-004 一致，fail-soft 吞噬面有界且各有 machine reason；B2 契约干净（禁带字段、box 零请求、tool_use/text 解析正确），一条 design 漂移（m1 回喂步骤）。TS 侧硬超时真 kill、state 只走 stdin、异常五形态归一、mw-runner 契约复用完整；反馈三层与 D-005 完全一致，唤醒仅在类型不一致且未静音时发生，notice kind 已进面板可见集合，不可用时结构性零通知。可维护性：无重复读取实现（一处文档化镜像），一处测试专用导出（n1），命名注释与实现一致。整体实现质量与 design/spec 的贴合度高。

## 残留与未验证

1. **运行时命令未在本评审会话执行**（m2）：pytest 三套件、vitest triage-dispatch、`git status --porcelain`、真实 `mw decide run/probe/set/show/doctor`。静态核对未发现与 T-04 记录或 PM 重跑记录（131 passed / 21 passed）任何矛盾项；`.pytest_cache` nodeids/lastfailed 与「最近全绿」一致——佐证不是新跑。
2. 真实 B2 调用本轮 0 次（无 shell 且评审会话不应消耗模型调用）；以 T-04 §A-1 唯一真实记录（available=true, latency_ms=6809, 两题带 confidence=0.85, model-self-report）为准。
3. vitest 无持久缓存可查，21 用例状态由测试代码清点 + T-04 §F-2 + PM 重跑记录支撑。
4. `npm run check` / multi-workers 全量套件本轮范围外，未验证（T-04 §F-1/F-3 记录：8 条既有环境失败零新增、本 key 文件 check 清零）。
5. llmproxy 当前可用性（429 是否仍持续、B2 是否仍 200）未复测——D-1 上游状态以 T-04 时点证据为准。

## 上下文来源

- `.agenticdoc/mw-jev-provider-integration/spec.md`（§2/§3/§4，读全）、`design.md`（D-002/D-003/D-004/D-005/D-006/D-007/D-009，读全）、`plan.md`（§1 冻结协议/§2 波次，读全）
- 上一轮：`evidence/quality-gate-report-20261016.md`（读全，含「PM 处置」M1-M4 表）、`evidence/runs/verify-mw-jev-provider-integration-20261016.md`（T-04，读全）
- 实现（读全）：`decision.py`、`decision_backends.py`、`triage-client.ts`、`shared/mw-runner.ts`
- 实现（读相关段）：`mw.py:600-990`（cmd_doctor + decide 全段）、`:3822/:5288`（cmd_model/_goal_gate_install 定位）、`:7442-7512`（argparse+dispatch 表）、`mw_common.py:1599-1690`（decide 三个函数）、`:4588-4603`（doctor 渲染）、`ui-bridge.ts:180-300`（triage 段）、`:1257-1490`（planDispatchFrontmatter）、`:2324-2606`（dispatch_worker）、`:2899-3104`（/worker）、`:3419-3509`（/mw model 段）、`pm-orchestrator.ts:470-655`（kind/notice/文案/ledger）
- 测试（读全）：`test_decide.py`（69）、`test_decide_backends.py`（33）、`test_decide_cli.py`（29）、`packages/coding-agent/test/suite/triage-dispatch.test.ts`（21）
- 文档：`packages/multi-workers/README.md:486-583`（决策服务小节，含「覆盖面与数据流」）、两 CHANGELOG 本 key 条目（multi-workers:100、coding-agent:83）
- 佐证：`packages/multi-workers/.pytest_cache/v/cache/{nodeids,lastfailed}`（131 条 decide nodeids 全收录、lastfailed 零 decide 条目）

## 未覆盖面声明

按卡片要求：
- 不审 conductor 派发链与 PM 主循环的既有设计；不审 D-1 上游（llmproxy/timiai）实现；不做压测。
- 不审本轮未交付项：conductor 侧挂点（挂点 C）、`mode: async`、B3 真实链路、`box` 真实链路、TS 面板逐字同步 doctor 行。
- 不跑 `npm test` / `npm run build`；不重跑 multi-workers 全量套件（按需核对决策三套件与单个 TS 用例——本轮以静态 + 缓存佐证替代）。

本轮额外（因工具面限制）：
- 全部命令未执行（m2/残留 §1）；真实 B2 调用 0 次（卡片上限 2 次未用）。
- 运行时验证由静态核对 + pytest 缓存 + T-04/PM 记录三角佐证替代。

---

## PM 处置（2026-10-16，复审后）

| 项 | 分级 | 处置 | 证据 |
| --- | --- | --- | --- |
| m1 B2 解析缺 D-002「校验错误回喂重发 1 次」 | minor（design 漂移，无 AC 破坏） | **已修**（`jev-t07-b2-refeed-quickfix`，3m）。判定为必修为非纯文档对齐：B2 请求 `temperature: 0`（`decision_backends.py:521`），客户端对 `bad-response` 的重试会确定性复现同一份非法输出，回喂是唯一有效纠错机会。实现：`_chosen_tool_use`/`_tool_use_blocks` 提取 + `build_refeed_payload` 复用 B2 模板（禁带四字段/`temperature`/`tools`/`tool_choice` 形状不变）+ `decide()` 仅在「有 tool_use 块且校验失败」时回喂一次（单次 decide ≤2 次 POST，无循环）；只有 text 时不触发；第二次仍不合法 → 既有 text 回退 → `bad-response`（尾部行为不变）；回喂请求本身失败视为 best-effort（先对首响应 text 回退，仍失败才返回回喂的 `_classify` 结果）。 | `decision_backends.py:658`（唯一例外注释，引用 design D-002）、`:581`（`build_refeed_payload`）、`:666`；测试 (a)(b)(c)(d) + 回喂 transport 失败 fail-soft 例 |
| m2 评审会话无 shell，验收命令未实跑 | minor（环境） | **已闭合**：PM 直执重跑（含 m1 修复后）→ `python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py` = **137 passed**；`test_decide_backends.py` 单跑 = **39 passed**；TS `vitest --run test/suite/triage-dispatch.test.ts` = **21 passed**。写面核实：快修窗口内只有 `decision_backends.py`/`test_decide_backends.py` 两个文件被写（其余 key 文件 mtime 未变）。 | 本轮 PM 实机输出 |

### 复审 8 条 note 的处置（经 PM 判断）

| note | 处置 |
| --- | --- |
| `detail` 计算后丢弃、失败无可读诊断 | **接受为已知边界**：补进响应会动 design D-003 的「固定 8 键」契约，收益不足以换契约变更；`reason` 8 类已足以分类。记入 `achieved.md` 遗留 |
| `mw decide set api_key=...` 的值进 argv（进程列表可见） | **待用户裁定**：README 已写「不推荐写盘」，未写「命令行也可见」；可选改进 = 支持从 stdin 读值 |
| 真实 `runDecideMw` 零直接覆盖（测试桩替在 seam 上） | **接受**：有意避免真实子进程；记入遗留（spawn 参数错误只能人工核对） |
| B1 `entry_probe=true` 无测试 | **已修**（T-07 (d)）：真探测 404 → `entry-unavailable`；transport 失败不抛异常 |
| `decide_evidence_path` 文档化镜像（`decision.py` 与 `mw_common.py` 各一份） | **接受为已知重复**：两侧职责不同（客户端写 / doctor 读），合并会引入跨模块依赖；记入遗留 |
| 其余 3 条（detail 展示面、TS 面板逐字同步、mode: async） | 归入 `achieved.md` 遗留表 |
