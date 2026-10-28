# T10 交接补核（只读静态审计，2026-10-27）

角色 type=research；只写本证据文件；未运行测试/产品导入/生成器/CLI/服务/HTTP/模型/浏览器。

## 结论

**代码事实成立，交接资格仍不完整。** 五产品/测试在 worktree 镜像内的字节与 PM 保护的五 SHA
（`evidence/implementation/t05-r2-envelope-pre-dispatch-20261027/T10-products-protection.json`）
逐字节相同；live 仓库同名五文件仍是 before 字节（T10 未切换）。原 37 个生命周期测试函数与 22 个
task-state 测试函数零丢失、零改写：五个 diff 里 `decision_lifecycle.py` / `decision_wire.py` /
`test_decision_context_lifecycle.py` 是**纯追加**（删除行 0），`decision_task_state.py` 只有 1 个函数
（`validate_observation_order`）的 4 行被等价重构，`test_decision_task_state.py` 只有 9 处
`backend.DP1` → `DP` 常量替换（落在 7 个函数里），无断言削弱、无新增 skip/xfail，且这 6 个被改的
测试正好就是 baseline 里 6 个失败项——迁移面等于失败面。

链核结论（静态）：三类新事实与 creation fact 的 `key`/`task_key`/`logical_id` 关联成立
（`decision_lifecycle.py:347 _ledger_facts`）；before 只能逐字段等值复述（`:378 _check_before` +
`decision_task_state.py:68 same_snapshot`）；父后继引用必须已记录且同 key（`:403 _check_parent_ref`）；
依据复用 `decision_points.preparation_issues` 单源复核（`:534`），`prepared_at` 必须等于 preparation
自己的戳、`basis_text` 必须等于被选 catalog item 的 text（`:566-580`）；PM note 仅 `initiator_role=="pm"`
且独立成行（`:1272`、`:1300 note_event`）；terminal 需要真实 `task_after`，且不得早于 creation before 与
同 `logical_id` 已记录的任一 after（`:1464-1470`）；`executed`/`settled` 仍只核 before（`:1018` 内存
meta before + `:1027` 账本已存 before），不核已记录 after —— 与 `report.md` 的表述一致。null 与 `[]` 在
`validate_task_state`/`same_snapshot`/`_sanitize_metadata` 三层都保持区分。

但有 9 处静态可证的关联/校验缺口，全部方向为"fail-closed 或信息丢失"，无一产生伪造审批/伪造完成；
最值得 PM 用 fake probe 复现的三个：(S1) `request` 的确定性 `event_id` 只按
`(logical_id, dp, parent_ref)` 去重，"先拒绝后真实选择"会被吞成 `duplicate` 且 `recorded=True`；
(S2) 同一 `logical_id` 可以挂不同 `decision_id`，AC-050 的"同 key/task/logical_id"链没有绑定
decision_id；(S3) 写者不跑 `entry_material_issues`，且 `dp-auto` 的 legal choice 空集时
`applies_to` 不校验，非法 choice 可入账。

测试 sink：`decision_wire` 的 test scope 谓词（`:540`/`:555`/`:625`）**不**允许 key evidence 内任何
普通目录（任何 `.agenticdoc` 组件都被拒），所以"唯一合法 sink"在 key 内不存在；外部 OS 目录的人工许可
仍然缺（T05 PM handoff `check.json: T10_external_sink_permission_not_granted_or_used=true`）。
本卡只给出最小验证计划，不执行、不创建/复用任何 OS 目录。

过程与产品分开：`116 passed` 只是两文件局部绿；`done/acked` 是流程状态，都不是交接资格，也不是正式
QG/签收。

## 证据

### 1. 五源码/测试 EOF 真范围

worktree 根：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/`。
全部五文件本轮分段读到实际 EOF（最后一行之后无剩余内容；文件以单个 LF 结束，无 CRLF）：

| 文件 | 行数 | bytes | SHA256 | EOL/末字节 | 本卡读取范围 |
|---|---|---|---|---|---|
| `decision_lifecycle.py` | 1548 | 60811 | `0c0f7fff…dc8e4` | LF / `0x0A` | 1..1548（EOF） |
| `decision_wire.py` | 2263 | 79832 | `8863e534…5a5e6` | LF / `0x0A` | 1..2263（EOF） |
| `decision_task_state.py` | 82 | 3871 | `b01e08b0…5836d` | LF / `0x0A` | 1..82（EOF） |
| `test_decision_context_lifecycle.py` | 1401 | 50338 | `bdedfd43…11d1a` | LF / `0x0A` | 1..1401（EOF） |
| `test_decision_task_state.py` | 278 | 15480 | `30c6e4dd…9dc23f` | LF / `0x0A` | 1..278（EOF） |

四个 SHA 与 `after.json.files.*.after.sha256`、`check.json.products.*.after_sha256`、以及 PM 的
`T10-products-protection.json` 三处同时相等，说明 PM 保护的五 SHA 之后本卡面未再漂移。

live 仓库 `packages/multi-workers/` 同名五文件仍等于 **before**（`decision_lifecycle.py` 34814B
`e4ea5183…d33248`、`decision_wire.py` 73650B `076fd3de…911579`、`decision_task_state.py` 2452B
`e82fc6b9…7e35e9`、两个测试 26028B/13537B），即 T10 只在隔离镜像里，live 未接线也未切换。

关联材料（明确范围读取，不作为 EOF 声明）：`decision_points.py` 3832-3881（`resolve_entry_choices`）、
4100-4310（`basis_catalog_issues` / `basis_selection_issues` / `preparation_issues` /
`prepared_request_issues`）、1356-1385（`require_active_dp`）；`decision.py` 140-213
（`REASON_CODES` / `REASON_INPUT_INCOMPLETE` / `_PREPARED_REASONS` / `_PREPARED_RESULT_FIELDS`）；
`decision_history.py` 3900-4010（kind 白名单与 fold 入口）。

未覆盖面：`decision_history` 其余投影逻辑、`decision_book.py`、`mw.py` 全文、其它产品文件未读；
PM 的 `pm-state.md`、DAG、gate/ledger/config/凭证、其它 key 未读。

### 2. 完整五 diff 结构（before → after）

统一 diff 全部为 `before/<file>` → `after/<file>`。逐 hunk 统计删除行/新增行（排除 `---`/`+++`）：

| 文件 | hunks | 删除行 | 新增行 | 性质 |
|---|---|---|---|---|
| `decision_wire.py` | 5 | **0** | 187 | 纯追加：docstring、3 个 kind 字段元组、3 个 free-text 声明、NOTE/BASIS 上限、3 个 builder |
| `decision_lifecycle.py` | 5 | **0** | 597 | 纯追加：import、常量块、`_check_timestamp`/`_bounded_text`/`_ledger_facts`/`_check_before`/`_check_parent_ref`/`_count`/`_request_fields`/`_preparation_provenance`、`record_note`/`record_request`/`record_terminal` |
| `decision_task_state.py` | 2 | 4 | 38 | docstring 扩写 + `validate_observation_order` 改用 `observation_time`，新增 `observation_time`/`same_snapshot` |
| `test_decision_context_lifecycle.py` | 2 | **0** | 686 | `import hashlib` + 尾部 688 行追加 |
| `test_decision_task_state.py` | 8 | 9 | 44 | 9 处 `backend.DP1` → `DP`、`DP` 常量与 `decision_task_state` import、2 个新测试 |

"删除行 0 + 只追加"是可核的强证据：原文件的每一行都还在（这比函数计数更能证明未削弱）。唯一的实质
产品改动是 `validate_observation_order`（旧 4 行 → 新 1 行 + 两个新函数），行为等价（都用
`fromisoformat(stamp.replace("Z","+00:00"))` 比较 `after`/`before`），新增的是 `tzinfo is None` 拒绝。

### 3. 原断言与 7 个 fixture ID 迁移

**`test_decision_context_lifecycle.py`：37/37 保留。** 旧行号 47..672（live/before）与当前行号
48..673 一一对应，全部恰好 +1（唯一插入的 `import hashlib` 在旧 27 行后），逐行相同。锚点：

| 函数 | old `packages/multi-workers/…:line` | current worktree `…:line` |
|---|---|---|
| `test_meta_is_record_version_two_and_model_excluded` | 83 | 84 |
| `test_stages_share_one_logical_id_and_stay_distinct` | 226 | 227 |
| `test_long_secret_tail_is_never_persisted_by_a_clip` | 528 | 529 |
| `test_failed_write_is_reported_and_the_failure_sidecar_is_separate` | 565 | 566 |
| `test_writer_reads_no_credential_files_outside_the_synthetic_home` | 672 | 673 |

新增 27 个（7 helper + 20 test）：`_state` 738、`_material` 749、`_preparation` 757、`_result` 777、
`_started` 796、`_decision_id` 802、`_row` 806；首个新测试 812，最后一个 1354。断言差异 = 无（旧断言
全部原样，新增断言全部在追加段）。

**`test_decision_task_state.py`：22/22 保留，7 个函数只改 fixture 常量。** 旧 21..277，当前 28..266。

| 函数 | old line | current line | 实质变化 |
|---|---|---|---|
| `_record` | 33 | 40 | `_append_archive(...,dp=backend.DP1,...)` → `dp=DP` |
| `test_consumed_cannot_record_an_after_state` | 84 | 91 | `backend.DP1+":task-state"` → `DP+":task-state"` |
| `test_real_cli_freezes_before_locally_and_passes_only_material_to_decision_boundary` | 109 | 116 | `SimpleNamespace(dp_id=backend.DP1,…)` → `dp_id=DP` |
| `test_after_observation_cannot_precede_before_observation` | 131 | 138 | `backend.DP1+":out-of-order"` → `DP+":out-of-order"` |
| `test_after_requires_the_same_tasks_creation_fact` | 139 | 146 | 2 处：`":bound"`（start 与 settled） |
| `test_duplicate_after_write_does_not_replace_first_snapshot` | 166 | 173 | `backend.DP1+":snapshot-dedupe"` → `DP+":snapshot-dedupe"` |
| `test_production_filter_writes_the_six_field_snapshot_unchanged` | 195 | 202 | `backend.DP1+":production"` → `DP+":production"` |

9 处删除行全部是上述 `backend.DP1` 表达式；同一 hunk 内其余行是上下文，断言文本未变（例如
`assert not store.sink.exists()`、`assert store.sink.read_bytes()==original`、`raw=sink.read_bytes()` 等
原样保留）。新增 2 个测试：`test_snapshot_equality_keeps_null_and_empty_distinct_and_order_sensitive`
(255)、`test_an_agent_report_snapshot_never_creates_the_action_or_terminal_fact` (266)。

**迁移合法性**：`DP="dp-gate-approve"` 是 active 八入口之一
（`decision_points.py:671` ACTIVE_DP_IDS、`:697` role=pm、`:719` choices=`approve/steer/need_fix/reject`），
不是 retired id；`_append_archive` 用 `dpts.get_decision_point(dp).questions_version`
（`test_decision_context_readable_backend.py:274`）→ `require_active_dp` 对 retired id 直接抛
`DecisionInputError`，这正是 6 个 baseline 失败的唯一原因。被迁移的 6 个测试 = baseline 的 6 个失败项
（`check.json.baseline_worktree_red_6`），迁移面与失败面完全重合，既没顺手改别的测试，也没放宽断言。
`skip` 只有旧的符号链接平台跳过（`test_decision_context_lifecycle.py:557`），新增段无 `skip`/`xfail`/
新 marker。

### 4. 链核（静态，逐条给 path:line）

**(a) creation / 同 key·task·logical_id。** `_ledger_facts`（`decision_lifecycle.py:347-377`）读全账本，
damaged（bad_json/bad_utf8/unknown_schema/oversized/incomplete_tail）即拒；要求恰好 1 条同
`logical_id` 的 `record-start` 且 `key`/`task_key` 相等。note/request/terminal 三处都在写前调用
（`:1278`、`:1368`、`:1461`）。行上的 `key`/`task_key` 来自同一 `meta` 构造的 scope，因此三类事实与
creation fact 同 key/task/logical_id。

**(b) before 只能是 creation 快照的等值复述。** `_check_before`（`:378-401`）先两边
`validate_task_state`，再 `same_snapshot`；无 before 参数时返回 None（不推断）。`same_snapshot`
（`decision_task_state.py:68-81`）对 `FIELDS` 六字段全等比较，`None` 只等 `None`、列表顺序敏感。
`DecisionMeta.__post_init__` 拒绝"有 `task_before` 却无 `task_key`"（`:625-628`）。

**(c) 依据单源 + 合法 choice/applies_to/material refs。** `_request_fields`（`:436-515`）把
`available`/`attempts`/`transport_attempts`/`replayed` 与 `business_decisions`/`choice`/`basis_*` 分离：
`business_decisions>1` 拒；`==0` 时禁止带 choice/basis，`replayed` 要求 `reason is None` 且尝试数 0，
非 replayed 必须有冻结 `reason`；`==1` 时要求 `available`、非 replayed、`attempts>=1`、无 reason、
`choice`/`basis_id` 为 token、`basis_text` 非空、`basis_source=="pm-prepared"`。
`REQUEST_REASONS` = `decision.REASON_CODES | {REASON_INPUT_INCOMPLETE}`，与 producer 的
`decision._PREPARED_REASONS`（`decision.py:176`）集合相同。业务分支下 `_preparation_provenance`
（`:517-580`）调用 `decision_points.preparation_issues(dp, preparation, material, choice, basis_id)`
→ `basis_catalog_issues` 校验每项 `{id,text,material_refs,applies_to}`：material_refs 必须落在
`material`（含扁平化 state）里，applies_to 必须是该入口的 legal choice；`basis_selection_issues`
校验 `basis_id` 存在且 `choice in applies_to`。随后写者再核
`preparation["prepared_at"] == result["prepared_at"]` 与 `selected["text"] == result["basis_text"]`，
并对 canonical JSON 取 `basis_catalog_sha256`。`require_active_dp`（`:1348`）拒 retired id，
`decision_id` 必须以其 dp 为前缀（`:1351`）。

**(d) PM note。** `record_note`（`:1250-1313`）：`initiator_role != "pm"` 拒（`:1272`）；
`pm_note` 经 `_bounded_text(..., decision_wire.NOTE_TEXT_BYTES=16384)`（红字后超限即拒、不截断）；
`prepared_at` 必填且带时区（`_check_timestamp`）；行内写 `note_source="pm-prepared"`，**不含**
`choice`/`basis_id`/`basis_text`（`_KIND_FIELDS["note"]` 无这些字段，`decision_wire.py:295-301`），
因此 note 与模型依据不可能共用一行。note 的 before 同样只允许等值复述。

**(e) terminal。** `record_terminal`（`:1422-1510`）：`terminal ∈ {completed,incomplete,blocked}`
（`:1431`），必须有 `task_key`（`:1433`），`reason` 必填且 ≤ REASON_LIMIT，`evidence` 可选且
≤ METADATA_TEXT_LIMIT，`task_after` 必填（`:1448-1450`），然后
`validate_observation_order(stored_before, after)` 并对同 `logical_id` 的**每一行**已记录
`task_after` 做非递减检查（`:1464-1470`）；`event_id` 缺省时按 `(logical_id, terminal)` 生成
（`:1477`）。terminal 不产生 key/phase/签收语义，`settled` 单独存在不会派生 terminal。

**(f) executed/settled 的时序范围。** `record_lifecycle`（`:1013-1029`）：`task_after` 只允许
executed/settled 且有 task_key；先对**内存** `meta.task_before` 校验顺序（`:1018`），再读账本找到
creation fact、用**已存 before** 再校验一次（`:1027`）；不遍历已记录 after。故"executed/settled 只核
before、terminal 核 before+全部 after"的原表述由源码直接确认。

**(g) null vs []。** `validate_task_state` 对三轴保留 `None`（未记录）或列表副本；`same_snapshot`
区分；`build_event` 对 `task_before`/`task_after` 走 `_sanitize_free_text` →
`_sanitize_metadata`（`decision_wire.py:1115`），`None` 原样、`[]` 仍是 `[]`。断言层面
`test_null_and_empty_progress_axes_stay_distinct_in_the_new_facts`（1323）明确断言
`request.task_before.completed==[] & remaining is None`、`terminal.task_after.completed is None &
remaining==[]`。

**(h) 秘密边界。** 结构值 `_guard_secret`（`:271`）用注入 redactor 的 `hits` 拒写且不回显；自由文本
`_bounded_text` 先红字再判上限；`_preparation_provenance` 只在 redactor 命中时隐藏 authority 给出的
`rule` 文本（`:544-548`）；`lifecycle-error` 侧车 `detail` 也走 wire 的自由文本路径。

**(i) 失败不冒充 recorded。** `_append`（`:868`）把 `append_event` 的 `written/duplicate/failed`
原样映射；`failed` 时 `recorded=False` 并尝试独立 `lifecycle-error` 侧车（`error_recorded` 三态）。
`dedupe_event_id=True` 的去重发生在 append 锁内（`decision_wire.py:1991`），按 `event_id` 精确字节匹配。

### 5. 具体 counterexample（PM 下一轮 fake probe 材料；本卡未运行、未伪造已发生）

| ID | 输入形状 | 触发点 | 预测行为 | 严重性 | 原 T10 面修复建议 |
|---|---|---|---|---|---|
| S1 | `record_start`；`record_request(result=拒绝: business_decisions=0, reason="bad-response", transport_attempts=2, attempts=1)`；再对同一 `decision_id` `record_request(result=真实业务决定: business_decisions=1, choice/basis 齐全)` | `_stable_event_id("rq", logical_id, dp, parent_ref or "-")`（`:1374-1376`）+ `append_event(dedupe_event_id=True)` | 第二次返回 `status="duplicate"`、`recorded=True`，账本只留拒绝行；真实业务依据/choice 永久丢失，`available` 仍为 True 但 `business_decisions=0` | 中（fail-safe 方向，但业务事实丢失且 `recorded` 语义误导） | 在 `decision_lifecycle` 面把 `event_id` 纳入 `business_decisions`/`choice`/`reason` 或对"拒绝→业务决定"显式允许第二行；或让 `_append` 在 duplicate 且内容不一致时返回 `failed`(error_class="conflict") |
| S2 | 同一 `meta`：`record_start(decision_id="dp-pm-steer:L")`，再 `record_note(decision_id="dp-gate-approve:L")` | `_ledger_facts` 只核 key/task_key（`:347-377`）；行级只校验自身 dp 前缀（`:1351`） | 同一 logical_id 下出现两个 decision_id；history 的 `logical_to_decision` 会映射到两个 id，AC-050 的"同键链"名不副实 | 中 | T10 面可加"同一 logical_id 的 decision_id 唯一"校验（读账本已有行比较）；需 PM 确认是否允许改派决策点 |
| S3 | `dp-auto`（dynamic-candidates）+ `material={"task_goal":"x"}`（缺 `handling_options`）+ catalog item `applies_to=["c-999"]` + `choice="c-999"` | `basis_catalog_issues` 里 `legal` 为空集时跳过 applies_to 校验；`record_request` 不调用 `entry_material_issues`/`prepared_request_issues`（`:534` 只调 `preparation_issues`） | 非该入口合法 choice 的选择被写为 `business_decisions=1` | 中 | 在 `record_request` 业务分支增调 `decision_points.entry_material_issues`（或在 preparation 复核里要求 `legal` 非空） |
| S4 | Windows 路径变体：test sink `C:\…\.AgenticDoc\_autopilot\decision-lifecycle.jsonl`、或 8.3 短名 `AGENTI~1` | `_is_inside_agenticdoc` 按 `part == ".agenticdoc"` 大小写敏感比较（`decision_wire.py:555`）；`realpath` 不规范化大小写/不展开 8.3 | test scope 不拒，写穿到生产账本 | 中（安全网被绕过，非当前产品逻辑错误） | 在 `_refuse_production_paths` 对 given/canonical 做 `os.path.normcase` + 组件小写比较，必要时 `GetLongPathName`；属 `decision_wire` 面 |
| S5 | `record_settled(task_after=after@12:00)`；随后 `record_executed(task_after=after@11:00)` | `record_lifecycle` 不遍历已记录 after（`:1013-1029`） | 被接受；账本出现 after 时间回退（terminal 会拒同样输入） | 低-中（AC-050 "非递减观察时间"在 executed/settled 未成立） | 把 terminal 的"遍历同 logical_id 已记录 after"抽成共用 helper，executed/settled 也调用 |
| S6 | 同一 logical_id：`record_terminal(terminal="completed", reason=A)`，再 `record_terminal(terminal="completed", reason=B, task_after 更晚)`；或 `incomplete` 后再 `completed` | `_stable_event_id("tm", logical_id, terminal)`（`:1477`） | 同值 terminal 第二次 `duplicate`（reason B 丢失）；不同值两条终态并存，无单一终态不变量 | 低 | 明确"每 logical_id 至多一条终态"或允许修订时用显式 supersedes；属 `decision_lifecycle` 面 |
| S7 | `meta.task_before.completed=[SECRET]`：`record_start` 后，用同一未脱敏 before 调 `record_note/record_request(task_before=...)` | `_check_before` 拿**已脱敏**的已存 before 与调用方原文比较（`:395 same_snapshot`） | 永远不等 → 拒绝（"cannot be backfilled"），调用方只能传 None | 低（fail-closed，但"复述已记录 before"在含密文本下不可满足） | 比较时对两侧都过同一 redactor，或记录 `task_before` 的原文摘要用于比较（不改存储明文） |
| S8 | 任何调用方直接 `decision_wire.request_event(business_decisions=1, choice=None, …)` | `request_event`/`note_event`/`terminal_event` 不做 writer 级不变量（docstring 只声明"唯一 production caller 是 writer"） | 写出自相矛盾的 request 行；读者无从分辨 | 低（纪律约束，无强制） | 在 builder 内加最小形状断言，或把 builder 私有化 |
| S9 | producer 侧改名/删除 `_PREPARED_RESULT_FIELDS` 中任一字段 | `decision_lifecycle.REQUEST_RESULT_FIELDS`（`:145-160`）是 producer 冻结元组的**第二份副本** | 合法的冻结结果会被 writer 拒（缺字段）；双份常量有漂移风险 | 低 | 理想是 `decision.py` 导出公共元组由 writer import（**不在 T10 五面内**，属未列面，需 PM 另批）；T10 面内只能加一致性自检测试 |

补充观察（不计缺陷）：`_check_parent_ref`（`:403-428`）只要求"同 key"，不要求同 `task_key`，跨 task 的
父子链在同一 key 内是允许的；`_preparation_provenance` 的 `rule` 文本可能包含调用方给出的 preparation
键名，仅在 redactor 命中时隐藏（`:544-548`）。

### 6. test-scope guard 谓词、key 内合法 sink、外部许可

- 谓词一：`_is_production_ledger`（`decision_wire.py:540-542`）只比最后三段是否恰为
  `(".agenticdoc","_autopilot","decisions-wire.jsonl")` 或 `("…","decision-lifecycle.jsonl")`。
- 谓词二：`_is_inside_agenticdoc`（`:555-556`）`any(part == ".agenticdoc" for part in path.parts)`。
- 入口：`WireScope.__post_init__` 只在 `scope_kind=="test"` 时对 `sink` 与 `evidence_path` 调
  `_refuse_production_paths`（`:605-607`）；`LifecycleStore.__post_init__` 在 `scope_kind=="test"` 时同样
  调（`decision_lifecycle.py:740`）；`LifecycleStore.test` 的 sink 是
  `<test_root>/lifecycle.jsonl`（`decision_wire.py:755-757`），因此 **test root 落在 `.agenticdoc` 内即拒**。
- `_refuse_production_paths`（`:625-645`）对 given 与 `canonical_path`（`realpath(abspath(...))`）两者都判，
  相对路径也先经 `abspath`（cwd 在 `.agenticdoc` 内也会暴露 `.agenticdoc` 组件），不存在"相对路径逃逸"。
- **结论**：key evidence 内的任意合法普通目录
  （例：`.agenticdoc/mw-dp-consolidation/evidence/implementation/<run>/tmp/lifecycle.jsonl`）都被谓词二拒绝，
  所以"在 key 内找一个内置 test sink"**不存在**。两个残余 Windows 变体（大小写 `…/.AgenticDoc/…`、8.3 短名）
  才是真正的绕过面（见 S4），不属于合法 sink。
- 不绕 guard 的现实选项只有 `.agenticdoc` 之外的目录：OS 私有临时目录或仓外目录。二者都是"外部 sink"，
  按本卡仍**未授权**（`t05-r2-envelope-pm-handoff-20261027/check.json` 的
  `T10_external_sink_permission_not_granted_or_used=true`；T10 原卡又要求 "fixture project/home/TEMP 限本卡
  evidence"）：这两条规则互斥，必须由 PM 明确裁定"外部具体目录 + 只本次使用"，不能靠 fixture 名、预算、
  token 或 role 反推授权，也不能把 OS 路径描述成"面内"。
- 另需知道：`LifecycleStore.production(root)`（scope_kind="production"）**不过** guard。T10 首轮把 TEMP 放
  在 evidence 内时，生产型 fixture 真的在 evidence 内写了 4 个
  `proj/.agenticdoc/_autopilot/decision-lifecycle.jsonl`（见 §7），即"test scope 被拒"与"fixture 用 production
  scope 写假项目根"同时存在。这不是合法 sink，也不能反过来当作 guard 的授权通道。

**最小安全 PM 验证计划（仅计划；前置条件未满足前不执行）**

0. 前置：PM 书面给出**一个具体外部目录**（`.agenticdoc` 之外，建议 `%TEMP%\t10-pm-rerun-<UTC>`），并声明
   "本次唯一运行、运行后保留不清理"；未给出则不跑。禁复用 `…\Temp\dpc-t10-lifecycle-state\`（既有 OS 对象）。
1. 只跑两个指定 suite：`test_decision_context_lifecycle.py test_decision_task_state.py`，cwd 必须是
   `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`。
2. import 定位：运行前用同一解释器打印 5 个模块 `__file__`，断言全部落在
   `implementation-worktree/packages/multi-workers/` 内（参照 `after.json.imports`），并记下 `sys.path[0]`。
3. 前后 hash：五产品 SHA256（应等于本文件 §1 表）+ 14 个受保护 pyc + `decide_cases/dp{1,2,3,25}.json`
   与 `decide_registry.json`/dashboard 三件；运行后逐一比对，任何变化即 abort。
4. 网络/子进程：`test_decision_context_readable_backend._hermetic` 已删 provider 凭证 env 并替换
   `_auth_json_path`、清 points cache、并在 teardown 断言生产 case/asset 树字节不变；本 suite 的 CLI 用例
   已把 `DecisionClient`/`decide_for`/`_decide_run_payload` 换成 fake。若 PM 还要求"硬拒绝 socket"，
   需要额外写一个仓外 `sitecustomize`/插件文件——那是**另一份 OS 写面**，须单独许可，不能借本计划默认。
5. 最小 env：仅 `HOME`/`USERPROFILE`（指向许可目录下的私有 home）、`TEMP`/`TMP`（= 许可目录）、
   `PYTHONPYCACHEPREFIX`、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、
   `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`SYSTEMROOT`/`WINDIR`/`PATH`；删除所有 provider/worker/
   项目配置类 env（不继承）。
6. 命令：`python -B -m pytest -p no:cacheprovider -q --basetemp <许可目录>/<唯一label>/pytest-basetemp
   test_decision_context_lifecycle.py test_decision_task_state.py`。
7. 唯一 run label：`t10-pm-rerun-<UTC 时间戳>`，写入**新的**证据目录；不得与
   `baseline-green/final-green/exact-acceptance` 同名（同名覆盖正是本卡 40 setup 日志丢失的原因）。
8. 日志：完整 stdout+stderr+rc+argv+cwd+env 键名清单落盘，**先落盘再解析**；失败用例逐个抄名。
9. 预期：`116 passed, rc=0`（两文件当前共 116 个 item）；若数字不是 116，说明收集面变了（新增/跳过），
   按失败处理而不是"通过"。
10. 运行后再做一次 worktree 快照差分（对照 §3 hash 清单），确认除许可 sink 外无新增/修改文件；随后
    由 PM 写结论，worker 不写 PASS、不签收。

### 7. 时间线、缓存线索、失日志与 pyc

- 时间线（UTC，证据文件 mtime）：`baseline.json 13:01:51` → `fixture/temp 13:02:35`（唯一一次
  evidence 内 TEMP 运行；4 个 production 账本写入 13:02:42-44）→ `baseline-green 13:03:57`
  （6 failed/78 passed）→ `live-repo-baseline 13:04:05`（84 passed）→ 多次 green-1..8 →
  `final-green 13:15:41`、`final-green-2 13:15:45`（116 passed）→ `red-prefix 13:15:56`
  （31 failed/85 passed）→ `after.json 13:15:57` → `exact-acceptance 13:17:38`（116 passed）→
  `check.json 13:17:48` → `report.md 13:17:53`。
- 失日志：首轮"40 setup `WireScopeError`"的 stdout 被同名 `baseline-green` 覆盖，只剩
  `fixture/temp/pytest-of-unknown/pytest-0/`：69 个编号 basetemp + 43 个 `…current` 链接、8 个文件
  （4 个 production scope `decision-lifecycle.jsonl` 505/1414/1753/2151B + `lifecycle.jsonl` 1063B/0B +
  `elsewhere.jsonl` 0B + 合成 `auth.json` 39B）。因此：(i) "发生过一次 evidence 内全量运行且确有账本写入"
  可核；(ii) 具体"40 个 setup 错误"**不可复核**（无日志）；(iii) 原报告"仅 pytest 临时目录，无账本、
  无产品写入"**不准确**——那 4 个 production 账本就是产品 writer 在 evidence 内写出的真实行。
- 缓存线索：14 个受保护 pyc 仍在且与 `after.json.pyc` 逐个 SHA 相同（`decision.cpython-314.pyc`
  `b95f933d…cb280`）；其中 13 个 mtime 是 `2026-10-26T12:16:49Z`，只有 `decision.cpython-314.pyc` 是
  `2026-10-27T12:57:43Z`（早于本卡首个 python 进程 13:01:38）。`decision_wire.pyc`/`decision_task_state.pyc`
  仍停留在 10-26 且**不包含** 10-27 的新源码 → 独立佐证本打卡所有 python 运行都是 `-B` +
  `PYTHONDONTWRITEBYTECODE=1`，没有重写 pyc。但漂移那 1 个 pyc 无法归属（并行 T05 或其它进程都可能）。
- 使用限制：`decision.cpython-314.pyc` 的漂移**禁止清理/复原/重新取基线**来"抹平"偏差；本卡只做只读
  hash，未改动任何 pyc。
- 净 hash 的证明上限：运行前后文件 hash 相同只能说明"两端一致"，**不能**证明期间没有写后回滚/写后截断；
  mtime+sha 也不能证明独占作者（多 session 同 cwd 时无法区分写入者）。因此"五 SHA 未变"只能当"本卡未
  留下可观测改动"的证据，不等于"期间绝对无写"。
- 过程与产品分开：首轮 evidence 内 TEMP 与 production-scope 假项目根写，已超原卡"TEMP 限本卡 evidence"
  的表述且发生在 `.agenticdoc` 内（虽在 evidence 临时目录），是**已披露的规则冲突/过程偏差**，需 PM 裁定
  追认与否；它**不**说明产品当前实现错误。`116 passed` 与 `done/acked` 同样只是局部/流程状态。

### 8. 消费者与接线（静态）

`record_request`/`record_note`/`record_terminal` 在 worktree 内除定义（`decision_lifecycle.py:1315/1250/1422`）
外**只被测试调用**（`test_decision_context_lifecycle.py` 多处）；`mw.py`/CLI/Worker 工具均无调用点，
`decision.DecisionClient.request_prepared`（`decision.py:1775`）也还没有把结果交给 writer。即
producer→writer→consumer 链仍缺中间两段，本卡不对此作任何"已接线"结论。

## 改动清单

| 文件 | 说明 |
|---|---|
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-handoff-audit-20261027.md` | 本卡唯一新增证据（worker_file 写入）；无其它文件创建/修改/删除 |

未写：五产品、原卡、T10 原证据、PM 证据、state/DAG/其他 key、任何 OS 目录/脚本/fixture/cache；
未清理/复原 pyc，未重取基线。

## 残留与未验证

- 本卡**未运行**任何测试/产品导入/generator/CLI/服务/HTTP/决策/模型/浏览器；§4 的链核全部是源代码
  静态推导，§5 的 S1-S9 全部是**预测**，需要在 PM 许可的 fake probe 里现实验证。
- 两 suite 的 116 passed、red-prefix 31 failed、baseline 6 failed 均为原 worker 的运行记录，本卡只做了
  算术一致性与 diff/AST 层面的交叉核对，没有复跑；无留存日志的首轮"40 setup 错误"不可复核。
- `decision_history` 对新 kind 的投影仍未核（只静态确认 kind 白名单
  `decision_history.py:3926` 直接读 `decision_wire.EVENT_KINDS`，故 `unknown_kind=0` 成立的条件具备），
  note/basis/request/terminal 是否成为独立节点、`unlinked_events=0`/`foreign_rows=0` 只在测试断言里。
- 消费者未接线（§8），所以"真实 producer→writer→consumer→projection"链未证；AC-049/VC-049 的后继真实
  请求、AC-052/VC-052 的并发/重放均无运行证据。
- 外部 OS 测试 sink 许可仍缺；本卡未创建/复用任何 OS 对象，也未把既有 `…\Temp\dpc-t10-lifecycle-state\`
  当授权。
- T10 只在 worktree 镜像，live 仓库仍是 before；未做切换、未做 live 基线重取。
- 未核：完整 `npm run check`/T32、generate 脚本 `--check`、TS 侧、human/H12 资格、gate/policy/brake/
  签收/key 关闭、镜像漂移全量（只核了五文件与 pyc）。
- 本卡不是正式 QG/评审/签收，不产生 PASS、receipt 或任务完成结论。

## 上下文来源

- 派发卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t10-handoff-audit/task.md`（frontmatter
  card_sha256=9e1b6df7…e43989b、write_face、五节交付契约）。
- 源卡：`.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md`（AC/VC 摘录 004/012/014/
  049/050/051/052、TEMP/fixture 约束、验收命令）。
- 原交接：`evidence/implementation/dpc-t10-lifecycle-state/{report.md,baseline.json,after.json,check.json,
  diff-*.diff,baseline-green.stdout,baseline-green.meta.json,final-green*.{meta.json,stdout},
  exact-acceptance.*,red-prefix.*,fixture/temp/…}`。
- PM 证据：`evidence/implementation/t05-r2-envelope-pre-dispatch-20261027/{T10-products-protection.json,
  T10-evidence-protection.json,pyc-protection-current.json}`、
  `evidence/implementation/t05-r2-envelope-pm-handoff-20261027/check.json`。
- 产品源码（worktree，全文到 EOF）：`decision_lifecycle.py`、`decision_wire.py`、`decision_task_state.py`、
  `test_decision_context_lifecycle.py`、`test_decision_task_state.py`。
- 关联范围：`decision_points.py:1356-1385,3832-3881,4100-4310`、`decision.py:140-213,1775`、
  `decision_history.py:3900-4010`、`test_decision_context_readable_backend.py:50-170,240-300`。
- live 对照（只 hash/函数行）：`packages/multi-workers/` 同名五文件 = before 字节。
