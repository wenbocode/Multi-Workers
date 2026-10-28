# RQ3 只读研究：退役 DP 的历史只读、观察面与回归边界

Key: mw-dp-consolidation | Kind: research（只读）| Date: 2026-10-24
Scope: `packages/multi-workers`（decision_history / decision_playground / decision_dashboard.js / decision_monitor / 相关测试），`packages/coding-agent` 生成物消费面。
未执行：测试、真实模型请求、共享服务/monitor/sign/build/install/commit、ask_decision；未改源码、registry、配置、历史、其他 RQ 证据或 phase。

## 结论

1. 历史投影的**身份**不依赖当前 registry：`dp` 来自记录的 `decision_id` 前缀与归档行（`decision_history.py:3383` `dp = decision_id.split(":", 1)[0]`、`:3386` `builder.archive_base["dp"]`），`questions_version` 只回显记录值（`:2788`、`:2832`），facets 由全量记录算出（`:728` `_facets`、`:745` `dps.add(record.dp)`）。删除活跃注册后旧记录仍可列、可看，字节不变。
2. 唯一的注册表耦合是**问题定义文案**：`_question_table()`（`:2168`）→ `decision_points.registry_snapshot()`（`decision_points.py:1039`）只喂 `question_summary`（`:2201` `_question_summary`、`:2682`）；退役 dp 得到 `None`，`question_summary_source` 自然为 `None`（`:2791`），UI 走"未记录/缺失"分支（`decision_dashboard.js:494`）。故"历史只读"的最小办法 = 读者不动 + 接受定义缺失 + 显式 retired 标注；禁止用当前 `load_points_config`、当前任务状态或新 schema 回填旧记录。
3. 真正会因删注册而**硬失败**的是活跃契约点：`decision_points.py:191 EXPECTED_DP_COUNT = 25` 与 `:899-902` `_validate_registry`（导入期 ValueError）。必须同步收敛计数/集合，再由生成器重出 `decide_registry.json` 与 `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（`registry_snapshot` `:1039`，`generated_from: decision_points.DP_REGISTRY`）。
4. 退役 dp 目前落在"未知 dp"拒绝路径（`decision_monitor.py:2036-2043`、`decision_playground.py:1200`；`scaffold` `:602` 抛 `DecisionInputError` 由路由先挡），语义必须改成可区分的 `retired`（只读历史、不可发起）vs `unregistered`，否则 AC-002/AC-013 不可判定。
5. 观察面不受退役结构性破坏：十节点 DAG 来自记录事实（`decision_history.py:2263 _node`、`:2653 _workbench_for`），旧记录 `nodes=[]`（`decision_dashboard.js:390-393`）；退役只改变 dp 下拉来源（`/api/dps` → `js:2482 loadPlayground`）与问题列文案。
6. 样例面无需迁移：`decide_cases/` 只有 `dp1.json`/`dp2.json`/`dp3.json`/`dp25.json`，与 17 个退役 id 零交集。"下拉仅 prefill 缺陷"与 monitor 重启属独立问题，不并入本 key。

## 证据

### 1. 历史依赖表（reader → 依赖 → 退役后 → 最小办法）

| # | 读取点（路径:行号 + 符号） | 依赖对象 | 退役后行为 | 最小办法（不得回填） |
|---|---|---|---|---|
| D1 | `decision_history.py:2168 _question_table` → `decision_points.py:1039 registry_snapshot` | 当前注册表的 `questions[0].instructions` | 退役 dp 无条目 | 保持 `None`；不改缓存键；**不**用归档/文档文本反填 |
| D2 | `decision_history.py:2201 _question_summary`（用于 `:2682`） | D1 表 + 短形式前缀匹配（`table[dp]` 或唯一 `dp + "-"`） | 短形式（如 `dp3`）匹配集变小；`dp1` 与 `dp15` 并存时本就需唯一匹配 | 匹配失败返回 `None`，禁止猜测；记录里有完整 id 时优先用记录值 |
| D3 | `decision_history.py:2788,2791`（`dp` 节点 detail） | 记录 `decision-end.questions_version` | 不变（只读回显） | 不改；`question_summary_source` 保持"仅当有定义时" |
| D4 | `decision_history.py:2828-2849`（`input` 节点 detail） | 记录 `questions_version`/`state_digest`/`book_ref` | 不变 | 不改 |
| D5 | `decision_history.py:3383`、`:3386` `_finalize` | 记录 `decision_id` 前缀 / `archive_base.dp` | 不变，退役 dp 仍出现 | 不改（这是 identity，不是配置） |
| D6 | `decision_history.py:728-748 _facets` | 全量记录 `record.dp` | 退役 dp 仍作为下拉值出现 | 不改；不得按当前注册表过滤历史 facets |
| D7 | `decision_points.py:191 EXPECTED_DP_COUNT` + `:899-902 _validate_registry` | 活跃注册表长度/唯一性 | 收敛到 8 会导入期失败 | 改成 8（或"必须包含冻结保留集合 + id 唯一"），并在同一提交内重生成两份产物 |
| D8 | `decision_points.py:908 get_decision_point`（调用方 `decision_playground.py:602,643,812,1200`、`decision_monitor.py:2036`） | 活跃注册表 | 抛错 → 现有"not a registered decision point" | 加 `retired` 分支：scaffold/validate/submit 一律 `rejected, zero_call, not-recorded`，文案区分 retired |
| D9 | `decision_monitor.py:380 CaseError("case-invalid")`（case 命名未注册 dp） | 活跃注册表 | 仅 dp1/2/3/25 有 case，无影响 | 不改 |
| D10 | `decision_history.py:3715 load_history`、`:1415 _read_archive_rows`、`:1449 _read_ledger` | 归档行 + ledger 字节（只读） | 不变，写 0 | 不改；新增断言锁"读不写" |

### 2. 观察/样例受影响面（只读历史元数据 vs 可执行活跃入口）

| 面 | 准确路径 | 退役后 | 归类 |
|---|---|---|---|
| 列表行 | `decision_dashboard.js:461-500`（`question_summary` 缺失分支 `:494`，dp 取值 `:496` 用 `workbench.dp_id` 否则 `record.dp`） | 问题列显示"未记录"，dp 仍显示真实退役 id | 只读历史 |
| dp 下拉 | `js:2482 loadPlayground` → `/api/dps`（`decision_monitor.py:1501` → `:1849 registry_snapshot`） | 仅剩 8 项；历史记录不补下拉项 | 活跃入口（收窄） |
| scaffold | `decision_playground.py:596-631 scaffold`（`scaffold_book`、`questions_map`、`questions_version`、`load_points_config`） | 退役 dp 不应可 scaffold | 可执行 |
| preview/validate | `decision_playground.py:779 validate`、`:831 _request_preview`、`:634 _review` | 退役 dp 在 `:1200` 前即拒；预览零模型调用 | 可执行 |
| submit | `decision_playground.py:889-1070 submit`（`_start` 锁去重 `:1220`） | 退役 dp 零模型、零新记录 | 可执行（最高风险） |
| poll | `decision_playground.py:1103 submission`；`js:1796 startSubmissionPoll`、`:1804-1807` | 纯读提交记录，退役无影响 | 只读 |
| 十节点 DAG | `decision_history.py:2263 _node`、`:2653 _workbench_for`、`:2263` 固定 order；`js:1503 renderDagGraph`、`:1672 renderDag`、`:1246-1260` 详情节点 | 节点来源是记录；v2 才有节点，旧记录 `nodes=[]`（`js:390-393`） | 只读历史 |
| 实际处理/结算 | `decision_history.py:2380 _settlement`、`:2404 _selection`、`:2293 _signoff_fact` | 不变；consumed≠completed | 只读历史 |
| 前后状态 | `decision_history.py:2279 _task_state_fact`、`decision_task_state.py:20 validate_task_state`、`:45 validate_observation_order`；`js:1246-1260` | 不变；无快照就是"未记录"，不推断 | 只读历史 |
| case 选择 | `/api/test/cases`（`decision_monitor.py:1920`、路由 `:1503`），`decide_cases/{dp1,dp2,dp3,dp25}.json` | 零交集，无需迁移 | 活跃入口（不变） |

### 3. 测试迁移清单（只给名字与用途，不运行、不修旧失败）

**删除/改写（活跃退役 DP 断言）**
- `test_decide_dp_cli.py`：`test_dp_on_p2_needs_no_flag_and_is_idempotent`、`test_dp_off_disables_and_keeps_the_other_columns`、`test_dp_on_refuses_to_clobber_an_unparsable_table`、`test_dp_set_updates_the_whitelisted_columns`、`test_dp_set_refuses_unknown_keys_and_bad_values`、`test_dp_refresh_adds_missing_rows_and_preserves_existing_ones`、`test_dp_apply_valid_signoff_writes_the_table_and_audits`、`test_dp_apply_requires_a_valid_conclusion`、`test_dp_apply_rejects_bad_dp_id_lists`、`test_dp_check_orphan_and_tier_conflict_are_warnings_exit_1`、`test_dp_check_bad_row_is_an_error_exit_2`（均以退役 id 作夹具 → 改用 dp1/2/3/25 或改为 retired 拒绝）。
- `test_decision_points.py`：`test_layer_l2_non_object_row_disables_only_that_dp`、`test_layer_l4_illegal_tier_keeps_registry_tier`、`test_step2_disabled_p1_returns_before_state_or_backend`、`test_pre_transport_escalations_write_no_archive_row`、`test_conflict_free_off_path_is_zero_spawn`、`test_unknown_intent_is_an_input_error`（夹具 id 迁移）。
- `test_decision_dashboard_contracts.py`：`test_dp17_covers_17_acs_and_uses_the_wide_array_cap`、`test_dp23_delta_bytes_is_a_signed_integer`、`test_dp11_never_takes_a_credential_value`、`test_unknown_business_key_is_refused`、`test_wrong_array_element_type_is_refused`、`test_illegal_enum_value_is_refused`、`test_over_limit_array_is_refused`、`test_over_long_element_and_string_are_refused`、`test_cross_field_facts_are_validated`、`test_total_budget_stays_independent_of_the_field_limits`、`test_invalid_business_book_sends_nothing_via_cli`（dp11/17/23/5/4 字段合同随 DP 退役而失效；若字段仍被保留 DP 复用则保留但换 dp）。
- `test_decision_history.py`：`test_history_reads_only_the_control_root`、`test_filters_are_exact_and_pagination_is_lossless`、`test_production_and_test_statistics_are_split`、`test_out_of_root_gate_and_test_ledger_are_refused`（夹具里出现退役 id，保留断言、迁移夹具或改为"退役 id 历史只读"用例）。
- `test_decide_registry_export.py`：`test_export_holds_all_25_points_in_registry_order`（25 → 8）、`test_wired_set_is_the_three_documented_call_sites`（dp8/dp9 等 wired 项消失）。
- `test_decide_registry_contract.py`：`test_every_point_has_a_well_formed_question_set`、`test_python_and_ts_required_fields_agree_per_dp`（夹具 id）。
- `test_decision_playground.py`：`test_a_p0_dp_observation_sends_while_its_production_path_is_disabled`（dp16 退役 → 改为"退役 dp 不可观察/零模型"）。
- `test_decision_context_contract.py`：`test_dp1_one_question_with_three_user_defined_types` 等四 DP 用例**保留**；同文件内 `test_unknown_business_key_is_refused` 类退役字段断言按 D8 规则迁移。

**必须保留（历史只读/安全/拒绝/跨语言/四 DP 业务）**
- 历史只读与投影：`test_decision_context_history.py` 的 `test_v2_record_exposes_the_fixed_ten_node_workbench`、`test_detail_carries_the_stored_capture_and_the_list_does_not`、`test_legacy_record_is_legacy_with_no_nodes`、`test_facets_cover_the_whole_snapshot_not_the_page`、`test_consumed_alone_is_processing`、`test_settled_outcome_decides_completed_or_failed`、`test_retry_gets_its_own_record_and_keeps_the_previous_bytes`、`test_ambiguous_decision_link_is_not_attributed`、`test_workbench_is_additive_and_the_read_writes_nothing`、`test_test_scope_workbench_stays_out_of_the_production_page`。
- 安全/过滤：`test_decision_context_history.py:test_without_a_redactor_node_free_text_is_withheld`、`test_known_secret_is_absent_from_workbench_and_facets`、`test_decision_history_basis_ui.py:test_unknown_basis_is_not_guessed_and_xss_stays_text`、`test_decision_history_feedback.py:test_default_monitor_history_withholds_stored_free_text_without_loading_credentials`、`test_new_reason_projection_remains_secret_safe_and_read_only`、`test_injected_redactor_http_history_includes_real_selection_and_receipt`、`test_decision_redactor_contract.py`、`test_decision_coverage_safety.py`、`test_decision_monitor_history_redactor.py`。
- 拒绝/零副作用：`test_decision_required_refusal.py`（`:403 test_required_refusal_stores_no_snapshot_and_keeps_the_decision_end_fact`、`:430`、`:451`）、`test_dispatch_decide_prepare.py:test_unknown_dp_is_refused`、`test_decision_input_contract_migration.py`（`:491 test_typed_refusal_writes_no_snapshot_with_a_real_scope`、`:517`、`:688`、`:701`）。
- 前后状态：`test_decision_task_state.py` 全部 13 例（尤其 `test_no_snapshot_is_not_inferred_from_ok_or_rework`、`test_after_observation_cannot_precede_before_observation`、`test_reader_does_not_attribute_another_tasks_after_snapshot`、`test_duplicate_after_write_does_not_replace_first_snapshot`）、`test_decision_task_state_ui.py`。
- 跨语言契约：`test_decide_registry_export.py:test_export_is_byte_identical_to_a_regeneration`、`:148 test_questions_version_and_required_state_fields_follow_the_registry`、`test_decide_registry_ts_lock.py:test_generated_registry_matches_a_fresh_render`、`:25 test_generator_check_mode_is_clean`、`:56 test_rendered_context_slots_match_the_slot_table`。
- 四 DP 业务（不得因退役改动）：`test_decision_context_contract.py`（`test_dp2_question_is_unchanged_from_the_design_revision`、`test_dp3_has_one_native_dynamic_choice`、`test_dp25_choices_are_finalize_continue_user_confirm`、`test_dp2_missing_pm_background_is_refused_with_zero_send`、`test_dp3_refuses_unusable_candidates_with_zero_send`、`test_dp25_sends_four_parts_with_verified_and_unverified_split`）、`test_decision_input_contract_migration.py`、`test_decision_dp25_empty_value.py`、`test_decision_context_signoff_cli.py`、`test_decide_signoff.py`、`test_decide_sign_auto.py`、`test_decision_context_workbench.py`、`test_decision_dashboard_playground.py`。

**建议新增（本 key）**
1. `test_retired_dp_history_stays_readable`（`test_decision_history.py`）：含退役 dp 的归档记录 → 列表/详情可读、`nodes` 齐全、`dp` 原样、`question_summary is None` 且 `question_summary_source is None`、历史文件 bytes/sha256 前后相同。
2. `test_retired_dp_has_no_active_entry`（`test_decide_registry_contract.py`）：`/api/dps` 与 registry 只含 8 项；`get_decision_point(retired)` 抛出的错误码为 `retired` 而非 `unregistered`。
3. `test_retired_dp_submit_and_scaffold_refuse_before_the_model`（`test_decision_playground.py`）：scaffold/validate/submit 三个入口对退役 dp 返回 `rejected / zero_call / not-recorded`，模型调用计数 0、新 ledger 行 0。
4. `test_retired_dp_case_and_dp_cli_are_refused`（`test_decide_dp_cli.py`）：`dp set/on/refresh` 对退役 id 拒绝且不改表。
5. `test_retired_marking_comes_from_the_frozen_list_not_the_live_registry`：retired 标记读取冻结清单；删空活跃注册项后标记不变（防"当前配置回填历史"）。
6. `test_retired_dp_question_summary_is_not_backfilled_from_archive_or_docs`：archive/book 里有问题文本时仍不填 `question_summary`。

### 4. 建议回归断言（集成链，producer → writer → consumer → projection → DOM）

- **producer→writer**：真实 CLI/observe 提交一次 dp1/dp2/dp3/dp25 → ledger 出现 `record-start` + `decision-end`（`decision_lifecycle` 写路径），`questions_version` 等于**当时**注册值；随后把该 dp 从活跃注册移除，重读历史仍显示旧 `questions_version`（不可重算）。
- **writer→consumer**：`decision_history.load_history` 对退役 dp 记录的 `dp` 取自 `decision_id` 前缀（`decision_history.py:3383`），不查注册表。
- **consumer→projection**：`workbench.nodes` 固定十节点顺序 `key,role,dp,input,decide,request,model,response,receipt,action`；只有 `record_version=2` 且显式 `logical_id` 关联才有节点；无快照 → `task_state` 为"未记录"而非 `ok`；`withheld`（redaction/`filters_withheld`）与"未记录"必须不同 code（`decision_history.py:1090 _scrub_output`、`:1205 _Sanitizer`）。
- **projection→DOM**：`decision_dashboard.js:494` 显示"未记录"而非空/伪造；`:1503 renderDagGraph` 十节点顺序与状态来自后端；`:1246-1260` 详情不补造；退役 dp 详情页明确显示"已退役，仅历史"。
- **安全**：真实秘密（已知集合）在 workbench/facets/DOM 文本中 0 次明文；注入脚本以纯文本呈现（`test_decision_history_basis_ui.py:85` 已锁 XSS 文本化，新增用例沿用同一 harness）。
- **关联与时序**：两个 `logical_id` 抢同一 `decision_id` → `workbench-association-ambiguous` 且不归属；`after.observed_at < before.observed_at` 必须拒绝（`decision_task_state.py:45`）；重复 `after` 写入不替换第一次快照。
- **零写入**：历史 GET 与 poll 前后 `_ledger`/归档/`task` 快照字节不变（`test_decision_context_history.py:1234` 已有基础，扩展为退役 fixture）。

### 5. 当前文档与历史保留边界

- **必须同步（当前事实）**：`packages/multi-workers/decide_registry.json` + `decide_points.py` 保留集合与 `EXPECTED_DP_COUNT`；生成物 `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`；`decision-tool.ts`（`isRegisteredDp` `:351`、`missingDecisionStateFields` `:421`、`isPmOnlyDp` `:485`、`validateDecisionMaterial` `:625` 均按生成表收窄，不做硬编码兜底）；`decision-tool.ts` 的 dp 枚举注释（`:7`）；`CHANGELOG.md` Unreleased 段（新增/移除各一条）。
- **不需改**：`README.md`、`packages/multi-workers/docs/*`、`UPDATE.md`、`dispatch-table.md`、`decide_book_template.json` 均无退役 id 硬引用（本 RQ 扫描 0 命中；`CHANGELOG.md` 仅 1 处历史条目）。
- **历史保留边界**：`.agenticdoc/mw-decision-context/**`、旧 key 的 evidence/design/plan、`CHANGELOG` 已发布段、`decide_cases/*.json` 原样保留；不以"零搜索命中"为由删除历史段落；历史归档不用当前 registry/任务状态回填（spec §2）。
- **明确排除**：case 仅下拉 prefill 缺陷、monitor 重启（`test_decision_monitor_auto_restart*.py`）不在本 key 修复范围。

## 残留与未验证

- 未运行任何测试；上述"删除/改写"清单只按源码引用判定，未执行确认失败面（P-025：不接受完成声明当证据）。
- 未验证 `decision_points.registry_snapshot()` 之外是否还有隐藏注册表读者（本次按 `questions_version|DP_REGISTRY|registry` 扫 `decision_history.py` 与 `decision_playground.py`；`mw.py`/`decision_book.py`/`decide_archive.py`/TS 全量读者未逐一读全）。
- `retired` 标记的存储位置未定：候选（a）`decide_registry.json` 增加 `retired: true` 只读条目（会与 AC-001 的"可调用数 0"冲突，需区分 `enabled/retired`），（b）冻结清单文件（如 `decide_retired.json`），（c）不标记、仅靠"当前注册表缺失"。本 RQ 只给约束（不得回填、不得恢复调用），选择属联合设计（RQ2/design）。
- `EXPECTED_DP_COUNT` 收敛方式（常数 8 vs 冻结保留集合校验）未定，涉及生成器 `decide_registry.json` 重生成流程与 `test_decide_registry_export.py:78` 字节一致断言。
- `decision_playground.py:602 scaffold` 的拒绝目前依赖 monitor 路由先挡（`decision_monitor.py:2036`）；若 provider 被直接调用，退役 dp 仍会抛 `DecisionInputError`（非结构化拒绝），属待修边界但不在本只读研究内改。
- 未覆盖：`decision_wire.py`/`decision_monitor.py` 中退役 dp 名的历史注释与 redactor 名单；`usage.py`/`stats` 里按 dp 聚合的历史统计口径（可能需按退役 dp 保留原值）。

## 上下文来源

- `.agenticdoc/goal.md:5`（目标锚点）、`.agenticdoc/mw-dp-consolidation/spec.md` §1.1/§1.3/§2/§3 AC-002·AC-003·AC-013·AC-014、`.agenticdoc/mw-dp-consolidation/key-decision.md`、`.agenticdoc/mw-dp-consolidation/evidence/parallel-analysis.md`。
- 源码：`packages/multi-workers/decision_history.py`（`:124-158` 投影契约、`:2168`、`:2201`、`:2263`、`:2653`、`:3383`、`:728`、`:3715`）、`decision_playground.py`（`:596`、`:634`、`:779`、`:831`、`:889`、`:1103`、`:1200`）、`decision_dashboard.js`（`:390`、`:461`、`:494`、`:496`、`:544`、`:1246`、`:1503`、`:1672`、`:1796`、`:2482`）、`decision_monitor.py`（`:1501-1510`、`:1849`、`:1920`、`:2036-2043`）、`decision_points.py`（`:191`、`:899-902`、`:908`、`:1039`）、`decision_task_state.py`（`:20`、`:45`）。
- TS 消费面：`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:351/421/485/625`、`shared/decide-registry.generated.ts`。
- 任务卡：`.agenticdoc/mw-dp-consolidation/tasks/RQ3-history-regression.md`（card_sha256 `ebd8d43f…9df0`）。

### 勘误（覆盖上文两处表述）

- 第 5 节：`packages/multi-workers/CHANGELOG.md` 的唯一 id 命中在 `:208`，内容是 dp3（保留 DP），不是退役 id；结论不变——当前文档无退役 id 硬引用，只需在 Unreleased 增补移除/保留条目。
- 第 3 节：`test_unknown_business_key_is_refused` 实际位于 `test_decision_dashboard_contracts.py:514`（非 `test_decision_context_contract.py`）；四 DP 业务回归以 `test_dp1/…/test_dp25_*` 各例为准。
