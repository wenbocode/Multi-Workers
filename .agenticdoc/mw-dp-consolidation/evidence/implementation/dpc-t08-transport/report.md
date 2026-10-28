# T08 report — timi transport: same-call business choice + prepared-basis selection

## 结论

代码/验证状态：**done at this layer**（T08 范围内真实红测→绿测，rc=0）。唯一验收命令在隔离副本内实跑通过：`python -m pytest -p no:cacheprovider -q test_dp_consolidation_materials.py` → `73 passed`，rc=0（runs/acceptance-final）。

本层交付的能力：

- 一次请求（同一 POST）同时问业务 choice 与 PM 预备 basis（`basis_id`），模型理由只来自 PM 预备目录文本，**不读**自由 `reason`/`rationale`，**没有第二次补理由调用**；
- 缺回答、错 basis、basis 引用不存在的材料、basis 不适用于所选 choice、状态/目录超界、分支材料不成立 → 全部 fail-closed，`business_decisions=0`，不套默认首候选/approve；
- 25 个退役旧编号在 replay 查询、backend、凭证、POST 之前拒绝（`transport_attempts=0`）；调用方 replay 查询命中 → 零请求；
- attempt（backend 调用）与 transport_attempts（真实 POST）与业务决定数分列计数；
- 保留原 `POST /v1/decisions`、`model=jev-latest`、bare `Authorization`、原重试/时间预算、`box-requires-image` 零 HTTP、拒绝外来模型；
- 完整业务材料与完整 basis 目录原样传输；超预算由原有尺寸门拒绝，**不截断**。

不在本层证明：真实 `mw.py` active-before-replay/全部生产 CLI 入口（T23）、TS/PM/Worker 消费者（T11+）、完整 53VC/L2/QG/签收、TS 编译、实际部署切换。T08 卡内 AC/VC 只按“本层能力”测，不冒充全入口通过。

## 证据

全部证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/`

- `before-bytes.json`、`before-bytes/packages/multi-workers/{decision.py,decision_backends.py}`：编码前真实副本字节。`decision.py` 99249B / SHA256 `c2b6d0a6f61654f986e28649899b48a79d3fd492408e0952cffa3521ae3a29e0` / CRLF 0 / bare LF 2298；`decision_backends.py` 44577B / `f1c6e3aad81e64b746f32b4e7f37442122b9928f4ab9beb8b53659f111d5bb60` / CRLF 0 / bare LF 1123；`test_dp_consolidation_materials.py` 不存在。与 `s2-frontier-pre-dispatch-20261026/check.json` 的 before 值逐字节一致（未用原仓源码代副本）。
- `after-bytes.json`、`after-bytes/packages/multi-workers/*`：`decision.py` 116092B / `89500080e9f59c80e98b757a3a2b547b1db06985edc04a7489d068cb5f80a5e5` / 2683 行 / CRLF 0；`decision_backends.py` 48970B / `a13a8597bba7abe796022148bd50d02b26fc6a85e1d7d3b1af9f5129f0a3e22b` / 1216 行 / CRLF 0；新测试 36376B / `2ab2d758350eb0a3b714512e9a70d81e14c645459f94cc8c850b98a4638454f8` / 977 行 / CRLF 0。写后 readback 相等。
- `t08-diff/{decision.py,decision_backends.py}.diff`：本卡净增量（decision.py +385/−0，decision_backends.py +93/−0）；既有 mirror 与 git HEAD 的旧 diff 未被重置（`mirror-git-status.txt`：`M packages/multi-workers/decision.py`、` M packages/multi-workers/decision_backends.py`，为本卡之前既有 index/worktree 状态）。
- 红/绿原始日志（完整 stdout/stderr + rc）：
  - `runs/red-1/pytest.log` rc=1 `61 failed, 3 passed`；失败点 `test_dp_consolidation_materials.py:279: AttributeError: 'DecisionClient' object has no attribute 'request_prepared'`（先红测）；
  - `runs/green-1/pytest.log` rc=1 `3 failed, 61 passed`（首次实现：transport 计数未跨 client 重试累加 + 测试里过严的 issue-path 字面断言）；
  - `runs/green-2/pytest.log` rc=0 `64 passed`；
  - `runs/green-3/pytest.log` rc=0 `64 passed`（把 prepared reason 词表收紧到本地，冻结的 `decide()` `REASON_CODES` 不加新值）；
  - `runs/green-4/pytest.log` rc=0 `73 passed`（补“每个入口全部合法 choice”与 sign `[]`/null）；
  - `runs/acceptance-final/stdout-stderr.log` rc=0 `73 passed in 0.25s`，argv 与卡一致（`-p no:cacheprovider -q test_dp_consolidation_materials.py`），cwd=副本 `packages/multi-workers`，`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、HOME/USERPROFILE/TMP/TEMP 指向本卡 evidence fixture、无 `TIMI_API_KEY`。
- 原始断言定位（测试文件内）：`test_each_entry_sends_one_same_call_choice_and_basis`（同请求两问、payload/URL/headers/state 分层、材料完整、秘密不入 body/证据行）；`test_every_legal_choice_of_every_entry_is_accepted_in_one_same_call`（31 个合法 choice/候选全过，结果无 action/executed/settled 字段）；`test_invented_choice_or_out_of_catalog_basis_is_refused`（8 入口各 2 例）；`test_missing_basis_answer_...`、`test_free_form_reason_fields_are_never_read_as_the_basis`、`test_basis_not_applicable_...`、`test_catalog_referencing_absent_material_...`、`test_missing_or_empty_catalog_...`、`test_oversized_request_...`、`test_long_core_material_is_sent_complete`、`test_every_retired_id_...`×25、`test_retired_ids_are_counted_...`、`test_replay_lookup_hit_...`、`test_foreign_model_response_...`、`test_retry_budget_and_bare_authorization_are_preserved`、`test_box_question_is_still_refused_with_zero_http`、`test_missing_or_non_eligible_role_...`、`test_branch_contract_violation_...`、`test_attempt_and_business_decision_counters_are_separate`、`test_sign_key_keeps_real_empty_arrays_and_refuses_null`；`test_imports_and_http_seam_bind_the_isolated_copy` 断言 `decision`/`decision_backends`/`decision_points` 的 `__file__` 都在副本内。
- `results.json`：以上 before/after/run/计数/残留/事件的机器可读索引。
- 隔离性：唯一网络缝为 `decision_backends._http_post`（测试 monkeypatch，happy path 同时把 `urllib.request.urlopen` 毒化）；无真实 endpoint/凭证/provider/决策 CLI/服务探针；源码树内无 config/gate/ledger 写入（client 证据行写进本卡 evidence 内 tmp fixture）。

本层实测计数（与 VC 输出同形，但仅限本层）：VC-002 `rejected_old_ids=25 transport_attempts=0 business_decisions=0 valid_decisions=0`；replay `requests=0`；VC-004 `legal_choices=31 baseline_contract_violations=0`；VC-040 `routed_targets=7 route_releases=0 route_actions=0`；VC-042 `auto_free_ids=3 invented_candidates=0 invalid_basis_refs=0`；VC-043 `failed_entries=8 failure_actions=0 default_first_choice=0`；VC-051 `null_or_missing_refused=3 empty_arrays_accepted=1 invalid_sign_arrays_accepted=0`。

## 残留与未验证

- **真实全入口旧ID/replay 拒绝未证**：`mw.py` active-before-replay、book/stdin、观察提交、config/apply 等生产入口属 T23（另卡），本卡只证传输层 `request_prepared`。不得用本卡绿测替代全入口 AC-002/VC-002。
- **消费者未接线**：T11（TS 工具）、T09（book）、T10（lifecycle）、T12～T15 等尚未消费 `DecisionClient.request_prepared`；`dp-auto` 的 `dynamic_choices` 在嵌套 `{material, preparation}` state 下由 `build_prepared_questions` 渲染为显式 choice（choices/labels 来自 material），后继卡须用同一渲染器，不能回到顶层 state 动态渲染。
- **既有 Python 套件未跑**：本卡验收命令只列 `test_dp_consolidation_materials.py`；`test_decide.py`/`test_decide_backends.py` 等既有套件未执行（T31/T32 负责完整回归与 `npm run check`）。因此“无既有回归”未经本卡验证；已做的风险控制：不改 `BackendOutcome`/`_RESPONSE_FIELDS`、不向 `REASON_CODES` 加新值、`TimiDecisionsBackend` 仅新增无参 `__init__` 与计数器。
- **越面事件（需 PM 处置）**：2026-10-26T20:16:49+08:00 我用未加 `PYTHONDONTWRITEBYTECODE` 的 `python -c` 导入包，在副本内产生 `packages/multi-workers/__pycache__`（7 个 .pyc）与 `packages/multi-workers/autopilot/__pycache__`（7 个 .pyc）。它们被 .gitignore 覆盖、后两次测试运行未新增（时间戳未变），但删除被 write-scope 守卫拒绝（不在本卡 write face），需 PM 清理。除此之外副本内无其它非本卡写入（同窗 `decision_validity.py`/`decision_policy.py`/`test_dp_consolidation_concurrency.py`/`test_dp_consolidation_recovery.py` 为 T06/T07 同期合法改动，不属本卡，也不宣称独占镜像作者身份）。
- **未验证范围**：TS 编译/erasable 语法/`npm run check`、真实部署/运行身份、human/H12 资格、grant/预算/watchdog、QG/签收/阶段关闭、完整 53VC 的 producer→writer→consumer→projection 链。
- 未做：commit/push、install/build/restart、依赖或 lock 变更、活对象（config/policy/gate/brake/ledger/权限/预算/签收）读写、四旧 case 改动、删除 human ask/legacy/死 helper。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t08-transport/task.md`（card_sha256 `07a719095a33f60666fef960ec89034ff96f81066bf7bea599f303178290b1e8`），源卡 `tasks/isolated/T08-transport.md`。
- 目标/规格/设计：`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:128`（锁定 SHA `cfe737d2…d006`）；`design.md` §1.1/§4.1/§4.2/§4.6、D-002/D-003/D-009/D-012A、§7 VC、§10 定案；`design-write-scope.md`（decision.py/decision_backends.py 的限定职责）。
- 计划/依赖/写面：`plan.md`（T08 = S2/coding，deps T03,T04）、`implementation-isolated-dag.json` T08（product_write_face 三文件 + 本卡证据目录）、`implementation-isolation.md`、`isolation-approval-20261026.md`。
- 交接与基线：`evidence/implementation/s2-frontier-pre-dispatch-20261026/check.json`（T08 before bytes/SHA、单 writer 无重叠、assigned test 不存在）；`t04-r2-pm-handoff-20261026/report.md`（T03/T04 语义前置）；`evidence/implementation/isolation-baseline-20261026/`（原字节/原 diff 留存）。
- 本卡完整读取的源码：副本 `decision.py`（2298 行到 EOF）、`decision_backends.py`（1123 行到 EOF）、`decision_points.py` 中 8 入口注册（640–1000）、退役目录/`require_active_dp`（1340–1385）、动态候选与 `dynamic_choice_labels`（1608–1700）、材料/必填/允许发送字段（1940–2100、3160–3290）、8 入口校验器与 `prepared_request_issues`/`basis_*`（3817–4330）、`model_state_for`（3769–3795）；以及 T03 的 `test_dp_consolidation_registry.py`（fixture 形状参考，未 import）。

## 改动清单

仅本卡 write_face 内三个副本文件（原仓库同名文件未写）：

1. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py`（+385/−0）
   - 新增 `BASIS_QUESTION_ID="basis_id"`、`REASON_INPUT_INCOMPLETE="input-incomplete"`（复用 `decision_backends`/archive 已有词，冻结的 `REASON_CODES` 不变；prepared 结果用 `_PREPARED_REASONS`）、`_PREPARED_RESULT_FIELDS`；
   - 新增懒加载 `_protocol_module()`/`_prepared_catalog()`；
   - `DecisionClient` 新增 `request_prepared()`：active ID → replay 查询 → role/material/preparation 校验 → 同请求业务问题+basis 问题 → 单次 `decide()` → choice/basis 适用性校验 → 冻结结果（attempts/transport_attempts/business_decisions 分列，issues/detail 可见，秘密 scrub）；
   - 新增 `_prepared()` 结果构造器与 `_transport_attempts()`；`__init__` 增加 `last_detail`/`_last_backend`/`_transport_attempts_total`，`_decide()` 汇总真实 POST 数，`_emit()` 记录 scrub 后 detail。
2. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_backends.py`（+93/−0）
   - 从 `decision` 汇入 `BASIS_QUESTION_ID`（standalone 容错镜像）；新增 `PREPARED_BASIS_INSTRUCTIONS`、`build_prepared_questions()`（registry 问题 + dp-auto 动态候选转显式 choice + basis choice，完整文本不截断）；
   - `TimiDecisionsBackend` 新增 `last_transport_attempts` 计数（`decide` 复位、`_post` 每次 POST 自增，retry-after 重试计入），并补 `__all__`。传输路径/模型/鉴权/重试/box 语义未改。
3. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_materials.py`（新增，977 行）
   - 73 个测试用例：隔离绑定、8 入口同请求、31 个合法 choice、缺回答/自由 reason/错误或不适用 basis/引用不存在/缺目录/超界/不截断、25 旧 ID 与 replay 零请求、外来模型/重试/bare 鉴权/box、角色与分支合同、attempt 与业务决定分列、sign `[]`/null、秘密不外泄。
4. 证据目录 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport/**`：before/after bytes、t08 diff、红绿与验收日志、`results.json`、本 report、两个取证脚本（`scripts/capture_baseline.py` 存 before、`scripts/capture_after.py` 存 after+diff，均只写本卡证据目录）。

未改动：`decision_points.py`、`decision_book.py`、`decision_lifecycle.py`、`mw.py`、TS/框架、spec/goal/design/plan、四旧 case、任何活对象；未 commit/push。
