# T09 report — book 与 stdin 准备器采用八入口完整合同

## 结论

本层状态：**T09 范围内的代码/验证 done at this layer**（真实红测 → 实现 → 绿测，rc=0）。唯一验收命令在隔离副本内实跑：`python -B -m pytest -p no:cacheprovider -q test_decision_context_contract.py` → **109 passed, rc=0**（evidence/implementation/dpc-t09-books/acceptance-final）。

本层交付的能力（每项都有对应断言，见「证据」）：

- 决策本改为 material / preparation / meta 三层（schema_version 3）：`material` 只装业务事实，`preparation` 是 PM 预备的 basis_catalog + prepared_at，`meta` 是本地 key/task/trigger/真实角色/logical_id（永不发送）；旧 `state` 形状与自带 `questions` 的书一律拒绝，不升级、不绕 active gate。
- 所有判定委托单源：`decision_points.entry_material_issues` / `preparation_issues` / `role_issues` / 退役表与 `decision_context` 槽位表。book 不再自带旧 dp 槽位/限制兜底表（T04 交接指出的 T09 fallback 旧债已清除）。
- 退役编号先拒绝：25 个旧编号在 material/preparation/replay/backend 之前被拒，措辞只给 disposition，不给别名；同一次 request_prepared 的 attempts/transport_attempts/business_decisions 全 0。
- 非法状态先拒绝：业务材料不合法时不再评判依据（依据无法对含缺陷材料作真实引用判断），第一个缺陷就是真实缺陷；八入口各有一条非法材料 → prepared=None 的实测（VC-043 failed_entries=8）。
- 保留签收四部与三数组（`[]` 是真实无，null/缺失拒绝）；dp-w-type 只携带真实 `images_required` 事实；dp-gate-approve 的 PM note 与模型 basis 独立；dp-auto 候选为 PM 提供的自由 ID（无旧 cN/2..5 限制，≥2、唯一、六字段）；dp-route 只有七个目标且无业务效果。
- 新增 stdin 准备器 `prepare_stdin_request`（一份请求；bundle/坏 JSON 明确拒绝）和 `prepare_request`（path/对象 → 只有零 issue 才给出 `(material, preparation)`），并由 `append_book_receipt` 生产 writer 在隔离 fixture 写回执（material/preparation 摘要 + book path + sha + evidence，不复制业务正文）。

不冒充：这不是完整 53VC/L2/QG/签收/stage 完成，也不是 CLI/观察实链、真实权限或部署验证；这些属 T23/T28/T29/T22/T25/T31/T32/T36。

## 证据

全部证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/`。

**编码前基线（副本，不是原仓源码）** —— `before-bytes.json` + `before-bytes/…`：

| exact file | bytes | sha256 | EOL | lines |
|---|---|---|---|---|
| packages/multi-workers/decision_book.py | 54796 | fc6d74a31abbddfa2c4a246f7a55cc23ba4c4844a41ed10d6547b2fc006b129f | LF 1338 / CRLF 0 | 1338 |
| packages/multi-workers/test_decision_context_contract.py | 35858 | ea6429088c285382736f634a3233b7c94659c2a381e60b0ad9380a0157b8e7cf | LF 961 / CRLF 0 | 961 |

两 before 值与 t09-pre-dispatch-20261027/check.json 完全一致；副本与 live 同名文件字节相等但 non-samefile（`before-bytes.json.live_compare`）。单 writer 依据：implementation-isolated-dag.json 中这两个 exact path 只出现在 T09 的 product_write_face；`git status` 仅显示这两个副本文件为 `??`（副本不在其 git 索引）。

**编码后** —— `after-bytes.json` + `after-bytes/…`（写后 readback 相等）：

| exact file | bytes | sha256 | EOL | lines |
|---|---|---|---|---|
| packages/multi-workers/decision_book.py | 59531 | dbe2329aa0b84ae10c484f526e812cae36545590c17d857bbfde040f302d32a0 | LF 1559 / CRLF 0 | 1559 |
| packages/multi-workers/test_decision_context_contract.py | 51264 | 9bbf89d6e03a6b6d60dd511d37509cc632d61e6c4ea9f3ae7c821da079ff2176 | LF 1348 / CRLF 0 | 1348 |

**增量 diff**（before copy → after copy，未含任何外来 diff）：`diffs/decision_book.py.diff`（27 hunks，+756/−535）、`diffs/test_decision_context_contract.py.diff`（4 hunks，+1293/−906）。

**边界对账**：`mirror-net-changes.json` 以 t09-pre-dispatch-20261027/mirror-inventory.json 为基线逐文件 sha256 对比：1883 → 1883 个文件，added=[]、removed=[]、modified 恰为本卡两个 exact 文件、outside_write_face=[]。14 个既有 `.pyc` 未变（未清理，未授权）；副本内无 `.pytest_cache`；测试临时目录全部落在本卡 `fixture/tmp`。

**红/绿原始日志（完整 stdout/stderr/rc）**：

- `baseline-pytest.stdout/.stderr/.rc`：旧测试文件对已迁移八入口注册表的真实基线 —— 46 failed, 2 passed, rc=1（失败点是旧 dp1/dp3/dp25 id 与旧四入口表，不是导入/收集错误）。
- `red-1.stdout/.stderr`：新契约测试先红 —— 103 failed, 5 passed（`assert 2 == 3`、`KeyError: 'preparation'`、缺 `book-preparation` 等真实断言失败）。
- `green-1…green-7`：逐轮实现/修正；green-4/5/6/7 均 rc=0。`green-1` 的 16 个失败均为测试侧口径/实现侧路径前缀问题，逐条修后收敛（0 个靠放宽判定消掉：`preparation.preparation` 双前缀与 `notes` 封闭键是代码修复，`issues==[]` 与 dp-auto 占位形状是测试口径修复）。
- `acceptance-final/`：argv=python -B -m pytest -p no:cacheprovider -q test_decision_context_contract.py，cwd=副本 packages/multi-workers，HOME/USERPROFILE/TEMP/TMP 指向本卡 fixture，PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、PYTHONPATH 空；stdout `109 passed in 1.22s`，stderr 0 行，rc=0。

**VC 形计数（counts.py → counts.json，复用测试 fixture 实跑，非声明）**：

- VC-002 `rejected_old_ids=25 retired_book_refusals=25 model_calls=0 business_actions=0 valid_decisions=0`
- VC-004 `legal_entries_accepted=8 legal_same_call_requests=8 baseline_contract_violations=0`
- VC-043 `failed_entries=8`（八个入口逐个给出 `material.<首个必填路径>`，prepared=None）、`failure_actions=0 fabricated_approvals=0`
- VC-040 `routed_targets=7`（dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto）、`route_releases=0 route_actions=0 route_book_issues=0`
- VC-042 `prepared_candidate_ids=[act-now, hold-for-user]`、`five_candidate_book_issues=0`、bounds `{min:2,max:null,id_scheme:free}`、`invented_candidates=0 invalid_basis_refs=0`
- VC-051 `empty_arrays_accepted=true`，三条 null 逐项 refused=true，`invalid_sign_arrays_accepted=0`
- legacy `{state_book_refused:true, questions_book_refused:true, book_schema_version:3}`

**原始断言定位（test_decision_context_contract.py）**：`test_book_covers_exactly_the_eight_active_entries`、`test_the_book_is_layered_as_material_meta_and_preparation`、`test_every_required_material_path_reaches_the_model_projection`、`test_route_targets_and_auto_candidates_come_from_the_single_source`、`test_issue_codes_keep_the_original_seven_and_add_the_new_layers`、`test_book_accepts_legal_material_for_every_entry`、`test_sign_key_keeps_the_four_parts_and_three_arrays`、`test_null_or_missing_sign_arrays_are_refused_with_the_material_path`、`test_gate_note_and_the_model_basis_stay_separate_business_inputs`、`test_auto_accepts_free_candidate_ids_and_any_count_above_one`、`test_route_is_material_only_and_cannot_carry_a_target_business_fact`、`test_vision_material_carries_only_the_real_image_fact`、`test_w_check_task_investigation_plan_is_optional_material`、`test_scaffold_is_loadable_but_never_sendable`、`test_every_entry_refuses_illegal_material_before_the_preparation`、`test_every_entry_refuses_unknown_material_keys`、`test_identity_and_association_facts_belong_to_meta_not_to_material`、`test_preparation_is_required_and_its_defects_are_named`、`test_a_failure_reason_or_probability_is_not_a_prepared_basis`、`test_basis_must_reference_real_material_and_a_legal_choice`、`test_auto_basis_applies_only_to_the_prepared_candidate_ids`、`test_every_retired_id_is_refused_before_any_material_or_preparation`（25 参数化）、`test_retired_ids_are_refused_before_the_replay_lookup`（replay_check 爆炸探针）、`test_the_legacy_state_book_is_refused_not_upgraded`、`test_a_book_may_not_bring_its_own_question_set`、`test_every_required_material_path_needs_real_evidence`、`test_evidence_must_be_a_path_line_or_a_command`、`test_meta_is_local_and_role_eligibility_is_checked`、`test_context_is_only_the_entry_s_own_slots_with_a_source`、`test_the_book_never_reads_the_live_transport_config`、`test_over_budget_material_is_refused_never_truncated`、`test_known_secrets_are_refused_without_echoing_them`、`test_prepared_request_consumes_exactly_the_book_layers`、`test_an_illegal_book_never_reaches_the_transport`、`test_stdin_preparer_reads_one_request_and_refuses_a_bundle`、`test_check_book_file_reports_each_book_separately`、`test_the_book_receipt_writer_records_the_real_layers`、`test_the_observation_seam_refuses_a_book_without_the_book_layers`、`test_book_state_merges_only_the_used_context_slots`、`test_imports_bind_the_isolated_copy`。

**额外只读冒烟**：`python -B -c "import decision_book …"` rc=0；`python -B -c "import autopilot.dispatch …"` rc=0（`_decision_registry_points()` 仍返回 8 项，W8 的只读 registry 视图未被删 API 打断）。

**隔离性**：唯一 backend 为 `decision.FakeBackend`；无真实 HTTP/provider/决策 CLI/服务探针；manifest 中项目内不存在 `.mw/decide.json` 依赖（另有测试证明 live config 不改变 book 判定）；生产 writer（append_book_receipt）只写本卡 fixture 内的隔离 project。

## 改动清单

产品文件（唯二，均在批准写面内；原仓库同名文件未写，live 未写）：

- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py`
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py`

decision_book.py 的实质变化：

- schema 3：`BOOK_TOP_LEVEL_KEYS` 改 material/preparation/meta/context/notes；`LEGACY_TOP_LEVEL_KEYS=("state",)` 明确拒绝；`META_KEYS`、`NOTES_KEYS` 闭集；`ISSUE_CODES` 保留原七码并新增 `book-preparation`/`book-meta`。
- 单源校验：`_check_material` → `entry_material_issues` + 身份/关联键分层封闭；`_check_preparation` → `preparation_issues`；`_check_meta` → `role_issues`；`context_slots`/`context_slot_spec` 只读 `decision_context`（删除旧 dp 槽位兜底表 `DP_CONTEXT_SLOTS`/`CONTEXT_SLOT_LIMITS`）。
- 拒绝顺序：schema/退役 → meta → material →（material 有缺陷即返回）→ preparation → 占位符 → context → evidence → budget → secrets。
- 新增 `PreparedRequest`、`prepare_request`、`prepare_stdin_request`、`book_material`、`book_preparation`、`book_meta_dict`；`book_state` 改为 material + 已用 context 槽位（嵌套在 `context` 键下）；`append_book_receipt` 增 `preparation` 参数与 `material_digest`/`preparation_digest`（保留 `state_digest`）。
- 保留并仍导出：`scaffold_book/scaffold_material/scaffold_preparation/scaffold_context`、`load_book/load_books`、`check_book/check_book_file/BookReport/BookError/Issue`、`required_state_paths/optional_state_paths/required_fields/optional_fields/field_type`、`registry_points`（dispatch 只读视图）、`is_placeholder/type_matches`、`book_sha256/book_meta`、`state_digest`、`resolve_repo_root`、`observation_book_issues`（并在 import 时 `register_book_validator`）。

test_decision_context_contract.py：整文件从旧四入口契约改为八入口 book 契约（109 个用例/参数化实例），含 25 退役 ID、八入口非法材料、sign 三数组 null/[]、dp-auto 自由候选、dp-route 七目标、依据独立、证据/预算/秘密、stdin 准备器、回执 writer、观察 validator、隔离 import 断言。

本卡证据目录新增（仅证据，不是产品）：`before-bytes.json`、`before-bytes/…`、`after-bytes.json`、`after-bytes/…`、`diffs/*.diff`、`mirror-net-changes.json`、`baseline-pytest.*`、`red-1.*`、`green-1…7.*`、`acceptance-final/{argv.txt,env.txt,stdout.log,stderr.log,rc.txt}`、`counts.json`、`counts.py`、`counts.stdout/.stderr`、`capture_baseline.py`、`capture_after.py`、`dump_fields.py`、`dump_q.py`、`fields.txt`、`questions.txt`、`_grep*.txt`、`fixture/**`、`report.md`。

未改动：decision_points.py / decision.py / decision_backends.py / decision_context.py / mw.py / decision_playground.py / TS / 生成器 / JSON / 四旧 case / 任何活 config·policy·gate·brake·ledger·凭证·预算·签收 / goal·spec·design·plan / 其他 key；未 delete human ask/legacy 显示/dead helper；未 install/build/restart/commit/push。

## 残留与未验证

1. **CLI/stdin 生产入口未接线**：`mw.py` 仍用旧 `{material, meta}`（sign）与 `--book`→`state` 组合；`prepare_stdin_request`/`prepare_request` 只是库面，真实 active-before-replay、`--book` 与 stdin 拒绝链、config/apply 等属 T23（另卡）。本卡只证 book 层，不替代 AC-002 的全入口结论。
2. **观察实链 fail-closed**：`decision_points._observation_book_issues` 仍读 `book["state"]`（不在本卡写面），因此新 schema 的书在观察 seam 会被拒绝（安全的 fail-closed，但功能上待迁移）。`decision_playground.py`/`decision_monitor.py`/dashboard（T28/T29/T27）也仍按旧 book 形状投影，必须随八入口迁移；本卡未改、未声称其可用。
3. **旧独立 key 的 book 测试未迁移**：`test_decision_book.py`、`test_decision_book_known_secrets.py`、`test_decision_cli_config_snapshot.py` 等按旧 `state` 形状建书，现会失败（旧合同按卡要求是历史/拒绝回归，不是可发送路径）。这些文件不在任何 T09 写面，也未运行；如需保留其 26AC 正向断言，须另开 history/rejection 迁移任务，不能在 T09 内改写。
4. **未跑的既有套件**：本卡只跑 `test_decision_context_contract.py`；其余 Python 套件、TS 编译/`npm run check`（T32 保护副本）、完整 vitest 均未跑，因此“无既有回归”未经本卡证明。风险控制：只改两个文件、未动 backend/registry/CLI 行为；`autopilot.dispatch` 只读 registry 视图已冒烟。
5. **context 投影缺口**：book 对 dp-QG/dp-auto 的 `error_excerpt` 槽位按 `decision_context` 单源校验，但八个入口的 `model_state_for` 白名单不含 `context`，prepared 请求实际不会把它带给模型。本卡只证“book 判定与槽位来源正确”，未修 `decision_points`（非本卡写面）；是否/如何投影属 T04/T10 接线。
6. **分支级规则由上层消费**：vision 图像能力硬门（T14）、dp-QG pass/reopen 的 `basis_issue` 分支（answer 期由 `entry_choice_issues` 判定，本卡只证 book 接受合法材料并拒绝未知键）、gate reject 的“无授权遗留不关闭”（T18）、签收硬门（T22/T25）、task 快照 null/[]（T10/T16）都未在本层验证。
7. **AUTO 之外的权威**：本层只用 faux backend；`request_prepared` 的可用性/预算/凭证语义由 T08 证明，本卡只证明 book 层与它的衔接面。真实 provider、human/H12 资格、部署身份、观察 DOM 安全均未证。
8. **预算口径**：book 校验不读 `.mw/decide.json`（离线条），使用默认闸 + 显式 limits；运行期预算仍由 transport 自己的尺寸门拒绝（不截断）。这是本卡的选择，已由测试固定，若后续要求 book 跟随 live 预算需另改。
9. 14 个既有 `.pyc` 原样保留（未清理）；未做 `cp`/重拷覆盖副本；未回移 live。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t09-books/task.md`（card_sha256 b1c49e8a66ea44dc841bda5445cebc6e39a8fc69a9c133f6a975ebbfbc6d7b2b），源卡 `tasks/isolated/T09-books.md`，原卡 `evidence/implementation/t09-pre-dispatch-20261027/original-card/T09-books.md`。
- 目标/规格/设计：`.agenticdoc/goal.md`；`.agenticdoc/mw-dp-consolidation/spec.md`（§1.1 八入口、§1.2 职责、§1.5 路由/auto、AC-002/004/007/012/014/040/042/043/051、AC-041/046/047/053 对照）；`design.md` §1（D-002A 材料/身份分层、D-003A 固定/动态/路由、D-008、D-009A 退役目录、D-012A 同次依据、§4.1 八入口材料表、§4.2 validate_request、§4.6 历史/上下文）与 `design.md:201` 已批模块表；`design-write-scope.md`（decision_book.py = M01/M03「八入口 book 准备/严格校验及独立依据、禁止 legacy 绕行」）。
- 计划/依赖/隔离：`plan.md`（T09 S2/coding，deps T03,T04,T08）、`implementation-isolated-dag.json` T09、`implementation-isolation.md`、`evidence/implementation/isolation-approval-20261026.md`、`evidence/implementation/isolation-baseline-20261026/`。
- 依赖交接：`evidence/implementation/t03-pm-handoff-20261026/report.md`、`t04-r2-pm-handoff-20261026/report.md`（含 "T09 fallback" 旧债与 T05 依赖）、`dpc-t08-transport/report.md`（request_prepared、同次 basis、25 退役、动态候选渲染）、`evidence/implementation/t08-r2-pm-handoff-20261026/pm-disposition-20261027.md`、`evidence/implementation/t09-pre-dispatch-20261027/check.json`（两 before、fresh 110、旧证据保护）。
- 本卡完整读取的源码（副本，读到实际 EOF 或所引区块）：`decision_book.py`（1338 行 before 全文）、`test_decision_context_contract.py`（961 行 before 全文）、`decision_points.py` 的八入口注册/退役/必填与可选字段/字段描述/校验器（640–1000、1340–1385、1940–2120、3162–3300、3378–3660、3800–4340、5960–6300、6340–6800）、`decision_context.py` 全文、`decision.py` 的 prepared request/凭证与 encode 面（1400–2100）、`mw.py` 的 book gate/sign stdin 消费点（1320–1420、1880–2100、4537–4700）、`autopilot/dispatch.py` 的 registry 视图调用点（250–300）、`decision_playground.py` 的 book 消费点（600–740）。
- 未使用：原仓同名源码代副本、旧 case 字节、任何 live 对象、真实凭证/provider。
