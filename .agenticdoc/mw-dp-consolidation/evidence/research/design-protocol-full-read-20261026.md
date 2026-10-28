# RQ18 全链协议补核：注册 → 材料/投影 → 候选 → 发送/校验 → 结果/回执（八入口联合设计输入）

> 性质：只读设计研究。未运行测试、未调用 CLI 决策、未做 provider/服务探针、未读活配置/gate/ledger/签收/凭证、未改任何源码/配置/框架脚本/旧报告/PM 相位文档。
> 标注约定：`[F]` 源码事实（附 path:line）、`[T]` 目标要求（本 key spec/AC，非实现）、`[S]` 本报告建议（未批准、未实现）、`[U]` 未验证/未知。

## 结论

1. 按卡要求的三个主文件已**全文续读到实际 EOF**，无未读区间：`packages/multi-workers/decision_points.py`（5769 行，1-5769 全部读）、`packages/multi-workers/decision_backends.py`（1123 行，1-1123 全部读）、`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（2072 行，1-2072 全部读）。为把「注册→材料→候选→发送→结果/回执」接到真实入口，另读了 `packages/multi-workers/mw.py` 的 870-1290 段（`_decide_run` 载荷、`{material, meta}` 信封、`--stdin` 版本化路径）以及生成器/漂移锁测试的头部与函数清单；**mw.py 其余 11700+ 行、decision.py / decision_lifecycle.py / decision_wire.py / decision_signoff_result.py 正文未读**，因此本报告不宣称对这四项完成全链审计（见「残留与未验证」）。`[F]`
2. 现行调用链事实（摘要）：注册是 Python 单源 `DP_REGISTRY`（25 条，`decision_points.py:574`，计数锁 `:191`，导入期校验 `:892`），TS 侧只有**生成**的 `decide-registry.generated.ts`（生成器 `packages/multi-workers/scripts/gen_decide_registry_ts.py`，漂移锁 `test_decide_registry_ts_lock.py:15/25`）与**硬编码的 25 个 dp id 列表**（`decision-tool.ts:132`，仅部分 dp 集合由测试对 Python 锁定）。材料面分两条真实路径：四材料 dp（dp1/dp2/dp3/dp25）走 `{material, meta}` + `--stdin`（`decision-tool.ts:1294/1385`，`mw.py:988-1000/1108-1144`），其余 21 个 dp 保持 `{state}` + `--request-file` 旧路（`decision-tool.ts:1500`，`buildDecideArgv`）。校验是双层的：TS 侧 `validateDecisionMaterial`（`:625`，闭集键 + 逐字段规则，来源 `DECIDE_REGISTRY`）与 Python 侧 `REQUIRED_STATE_FIELDS`（`:1522`）/`state_field_issues`（`:2683`）/`state_unknown_key_issues`（`:2778`）/`_missing_required`（`:3013`）再判一次，答案侧还有 `_value_fits`（`:4411`）与置信度门（`:5513`），无任何「默认首项 / 默认 approve」路径。`[F]`
3. 八入口目标（`dp-w-type`/`dp-pm-steer`/`dp-w-check-task`/`dp-QG`/`dp-gate-approve`/`dp-sign-key`/`dp-auto`/`dp-route`）目前**没有任何一条存在于运行注册**：registry 仍为 25 个旧编号（`decision_points.py:574-890`），`dp-route`/`dp-auto` 在三个主文件中零命中，`vision` 在 `decision-tool.ts` 零命中（只在 `STATE_FIELD_DESCRIPTIONS.task_type` 描述里作为既有框架类型出现，`decision_points.py:1730`）。因此这些是 `[T]` 目标要求，不是现状。`[F]/[T]`
4. 推荐技术方案（设计候选，未批准）：**方案 A —— 保持 Python 注册为唯一权威，扩展现有生成器输出「按入口判别的契约」**（`kind: fixed | dynamic-candidates | route-targets`、每入口 material 字段 + 选项枚举/来源 + 失败词汇），TS 与文档/JSON 全部由同一 `registry_snapshot()` 派生，沿用既有字节级漂移锁。理由：现有代码已经证明这条生成链可行且有真实漂移保护（`test_decide_registry_ts_lock.py`、`test_decide_registry_export.py:78`），而方案 B（另立共享纯协议描述再反喂注册/工具）会引入第三份权威、需要自己的漂移锁，且运行时仍由 Python registry 决定，净收益低于风险。`[S]`
5. 必须与旧业务限制解耦的点（直接影响八入口能否合法落地）：dp3 的「2..5 个候选、id 必须 `c1..cN`、label ≤ 80」是**旧动态业务的限制**，写在两处（Python `dynamic_choices_value_error`，`decision_points.py:1117-1145`；TS `checkHandlingOptions`，`decision-tool.ts:553-613`），并由交叉检查 `dynamic_candidates` 施加（`decision_points.py:2512`、`:2633-2650`）。目标侧 dp-auto 的候选由 PM 现场准备、不预置菜单（AC-042），dp-w-check-task 是三个固定选项（AC-046），两者都不应继承 2..5/`cN` 的业务限制；真正应继承的只是**传输/资源边界**（`MAX_STATE_BYTES=8192`，`:175`；单状态问题数 ≤ `DecisionConfig.max_questions`，`:453-454`；后端可答类型 `choice/score/noul`，`decision_backends.py:153`）。`[F]/[T]/[S]`
6. 失败语义可直接复用：服务失败是**数据**（`{available:false, unavailable, action:"blocked-ask-human"}` + 固定「不要自行猜测」指令，`decision-tool.ts:1147-1165`），7 值升级词汇（`decision_points.py:229-247`）与 8 值传输词汇（`decision-tool.ts:190-199`）并存不互相折叠；禁用/缺材料/超预算/低置信/越权都归到「阻塞」而非「默认放行」。这与 AC-012/AC-043 一致：**零业务执行 ≠ 禁止真实失败审计**，失败事实应可记录（现成先例：`record-start-failed` 仍返回结构化行，`mw.py:1155-1185`）。`[F]/[T]`
7. 本报告所有 schema/字段/文件名均为设计候选，**未实现、未测试、未通过任何 AC/QG/签收/相位门**；AC-001..004、012..014、040..044、050..053 的测试断言只给接口与隔离写法，不声明通过。

## 证据

### 1. 阅读范围与文件事实（可复核）

| 文件 | 行数 | 读取方式 | 覆盖 |
|---|---|---|---|
| `packages/multi-workers/decision_points.py` | 5769 | 分段续读 1-700 / 701-1400 / 1401-2100 / 2101-2800 / 2801-3500 / 3501-4200 / 4201-4900 / 4901-5600 / 5601-EOF | 全文 |
| `packages/multi-workers/decision_backends.py` | 1123 | 1-500 / 501-1000 / 1001-EOF | 全文 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` | 2072 | 1-700 / 701-1400 / 1401-EOF | 全文 |
| `packages/multi-workers/mw.py` | 13043 | 只读 870-1290（`_decide_run` / 信封 / `--stdin` 版本化路径）+ 2870-2960 附近的 `_dp_export` 符号清单 | **部分**，其余未读 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts` | 930 | 读头部 1-120（生成头、`DecideRegistryEntry` 形状） | 部分 |
| `packages/multi-workers/decide_registry.json` | 1771 | 只确认存在与生成测试引用 | 未逐行读 |
| `test_decide_registry_ts_lock.py` | 63 | 全文 | 全文 |
| `test_decide_registry_export.py` | 269 | 只读函数清单 + 关键行 | 部分 |

未读/未打开：`decision.py`、`decision_lifecycle.py`、`decision_wire.py`、`decision_signoff_result.py`、`triage-client.ts`、`index.ts`（extension 注册）、dashboard/UI 与 case 文件、全部测试正文（除上表）。

### 2. 现状调用链（逐段，含 path:line）

#### 2.1 注册（唯一权威与派生）

- `[F]` 注册表本体：`DP_REGISTRY: tuple[DecisionPoint, ...]`，25 条，`decision_points.py:574`；计数常量 `EXPECTED_DP_COUNT = 25`，`:191`；导入期 `_validate_registry` 校验重复 id/数量，`:892-912`；未知 id 走 `get_decision_point` 抛 `DecisionInputError`（`~:900-910`）。
- `[F]` 每条 `DecisionPoint` 字段（id/tier/default_enabled/default_mode/questions/build_state/executor/questions_version/p0_consequences/description），`__post_init__` 强约束：P2 必须有 executor、P0 必须有 `p0_consequences`、问题数量 ≤ `decision.DecisionConfig.max_questions`，`:404-470`。
- `[F]` 问题集合校验 `_validate_question`（`:323-402`）：`choice` 必须 `choices` 或 `dynamic_choices` 二选一；`dynamic_choices` 必须是 state 键；`labels` 键集必须等于 `choices`；`noul` criteria 只能 `true/false`。`questions_version` 只对 `id/type/choices/dynamic_choices` 做内容哈希（`VERSIONED_QUESTION_KEYS`，`:317`；`_questions_version`，`:404-419`），改文案不改版本——这条对「版本/关联层」很关键。
- `[F]` 导出：`registry_snapshot()`（`:1039-1091`）产出 `{schema: 3, question_types, points[{id,tier,default_enabled,default_mode,description,questions_version,p0_consequences,wired/trigger/adopted_at/wiring_note,executor,required_state_fields,optional_state_fields,model_state_fields?,questions}]}`；`registry_snapshot_text()`（`:1094-1100`）是唯一序列化器（`ensure_ascii=False, indent=2` + 结尾 `\n`）。`SNAPSHOT_SCHEMA = 3`，`:957`。
- `[F]` 两个真实产物/锁：`packages/multi-workers/decide_registry.json`（`mw decide dp export --write`，`mw.py:2870/2948/2959`；字节一致断言 `test_decide_registry_export.py:78`）；`packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（头注释声明 `@generated by packages/multi-workers/scripts/gen_decide_registry_ts.py`；字节渲染断言与 `--check` 断言 `test_decide_registry_ts_lock.py:15-34`；形状/顺序锁 `:36-62`）。
- `[F]` TS 侧独立硬编码：`ASK_DECISION_DP_IDS`（25 个 id）`decision-tool.ts:132-160`；`ASK_DECISION_ENFORCED_STATE_DP_IDS`（dp1/dp2/dp3/dp25）`:169-175`；`ASK_DECISION_PM_ONLY_DP_IDS = ["dp2-checkpoint-split","dp25-signoff-conclusion"]` `:214`；`ASK_DECISION_MATERIAL_DP_IDS = [dp2,dp3,dp25]` `:219-223`。这些集合由测试「pinned to the Python source」（注释 `:129-131`、`:168`）——但**部分集合不是生成物**，是第二处人工维护点。
- `[S]` 八入口若沿用现方案，必须把上述四个 TS 常量全部改为从生成物读取（含 `kind`、选项枚举、目标入口枚举），否则 AC-001/AC-002 的「可调用集合精确等于八项、旧编号别名数 0」将无法由单一权威保证。

#### 2.2 材料闭集与模型投影

- `[F]` 闭集权威三张表：`REQUIRED_STATE_FIELDS`（`:1522-1706`）、`OPTIONAL_STATE_FIELDS`（`:2424-2434`，当前只有 `dp2-checkpoint-split: ("worker_execution",)`）、`MODEL_STATE_FIELDS`（`:2437-2470`，只有 dp1/dp2/dp3/dp25 四个 allowlist；缺省=不过滤）。`AUDIT_STATE_PATHS = ("key","task_key","trigger_id")`，`:2472`，用于把本地关联事实从模型可见面剥掉。
- `[F]` 字段语义表 `STATE_FIELD_DESCRIPTIONS`（`:1710-2400+`）：每字段 `{type, description}` + 可选约束 `enum/max_items/item_type/max_bytes/item_max_bytes/signed/min_value/empty_is_value`（`STATE_FIELD_CONSTRAINT_KEYS`，`:1487-1496`）。导入期 `_validate_state_field_contract`（`:2838-2975`）拒绝：未声明路径、未知约束键、非数组上的 `max_items`、非整数的 `signed/min_value`、`MODEL_STATE_FIELDS` 里出现 identity/audit 路径、required/optional 不一致等。
- `[F]` 五道运行时校验，顺序在 `_decide_for` 中：
  1. Step 5 必填缺失 → `input-incomplete`（`:5228-5266`，`_missing_required` `:3013`）；
  2. Step 5b 类型/枚举/数组上限/跨字段 + 闭集键 + 身份一致性（`:5267-5345`；`state_field_issues` `:2683`、`state_identity_issues` `~:2801-2836`、`state_unknown_key_issues` `:2778-2836`；跨字段规则 `STATE_FIELD_CROSS_CHECKS` `:2491-2515`）；
  3. Step 6 模型投影 + 预算（`:5350-5372`，`send_state` `:1438` → `model_state_for` `:2980` → `_fit_state` `:3072`）；
  4. Step 7 发送（`:5400-5470`）；
  5. Step 8 答案合法性/置信度（`:5473-5551`）。
- `[F]` 预算：`MAX_STATE_BYTES = 8192`（`:175`，注释说明测量依据与「拒绝整份、绝不截断」）；`_fit_state` 先裁可选 L1、再对 `task_summary/ambiguity.question` 减半，仍超即 `input-oversize`（`:5372-5379`）；`send_state` 是「预览/发送同源」的单点（`:1438-1445`）。
- `[F]` 投影规则：`model_state_for` 对四 DP 只按 allowlist 取路径（深拷贝），identity（`schema_version/decision_point/questions_version`）与 audit（`key/task_key/trigger_id`）永不出现；其余 21 DP 仅浅拷贝并剔除 audit 键（`:2980-3011`）。
- `[F]` 空数组语义已在契约内：`verification_evidence.verified`、`verification_evidence.unverified`、`unfinished_impact` 三条都显式 `empty_is_value: True`（`:1812-1830`），校验器只允许 array/object 声明它（`:2898-2905`）。**这把「[] = 真实无」写进了权威表，而不是靠提示词约定**。

#### 2.3 候选构造（动态枚举）

- `[F]` 问句侧：dp3 问句为 `{"id":"handling","type":"choice","dynamic_choices":"handling_options"}`（`:622-626`），即候选不在注册表里，而在 state 的 `handling_options`。
- `[F]` 候选合法性：`DYNAMIC_CHOICES_MAX = 5`（`:1110`）、`DYNAMIC_CHOICE_LABEL_MAX = 80`（`:1112` 附近）、id 正则 `^c[1-9]$` 且必须连续（`:1117-1145`）。`dynamic_choice_labels`（`:1152-1172`）渲染 `{qid: {cN: label}}`，任何一条不可渲染就整份 `None`（调用方据此零 HTTP 拒绝）。
- `[F]` 发送侧：后端 `build_questions`（`decision_backends.py:810-842`）把 `noul/choice/score` 三型转成 wire 形状；`choice` 的 criteria 来自 `_choice_criteria`（`:646-674`，caller `criteria` > 渲染候选 > `labels`）；未知/`box` 类型永不进入请求。`_dynamic_choice_problem`（`:719-742`）在凭据读取**之前**把不可渲染的候选判成 `input-incomplete`，零请求。
- `[F]` 答案解码：`_decode_answers`（`:859-980`）要求答复 `model` 等于请求 `model`（禁模型回退）、每问必须有同类型答案、`choice` 值必须落在渲染/静态枚举内，否则 `bad-response`。Python 侧还有第二道 `_value_fits`（`decision_points.py:4411-4437`）对 `choice` 用渲染枚举（`dynamic_ids`）再判一次。
- `[F]` 旧业务限制的两处落地：Python 交叉规则 `{"kind":"dynamic_candidates","array":"handling_options"}`（`:2512`）+ `_cross_field_issues`（`:2633-2650`，≥2 个候选、label 唯一、description 非空）；TS `checkHandlingOptions`（`decision-tool.ts:553-613`，2..5、`cN` 连续、≤80、单行、label 唯一、未知键拒绝）与常量 `:227-229`。
- `[T]` 目标侧：dp-auto 由 PM 现场准备候选（AC-042），dp-w-check-task 固定三项（AC-046），二者都不允许「默认首项」（AC-043）。`[S]` 结论：**候选机制应改为「每入口声明的候选来源」**（`static-enum` / `pm-supplied` / `route-targets`），2..5 与 `cN` 只作为 dp-w-check-task 之外的旧兼容说明保留在历史解释，不迁移到 dp-auto。

#### 2.4 发送、答案校验与失败词汇

- `[F]` `decide_for` 11 步（`:4958-5062` 文档 + 实现）：Step 2 禁用/未启用 → `escalated/disabled` 且在任何 state/编码/后端解析之前返回（`:5082-5112`）；Step 3 mode；Step 4 传输不可用 → `escalated/unavailable`（`:5117-5166`）；Step 4b 每 DP 策略；Step 4c 唯一凭据快照（`:5176-5227`）；Step 5/5b 材料；Step 6 预算；Step 6b 观察本；Step 7 传输；Step 8 答案/置信；Step 9 suggest 或 `intent=answer` → `acted=false`（`:5552-5593`）；Step 10/11 执行器。
- `[F]` 升级词汇固定 7 值：`disabled/unavailable/input-incomplete/input-oversize/low-confidence/over-authority/p0`（`:229-247`）；`_outcome` 对集合外值直接 `ValueError`（`:4520-4530` 附近）。传输词汇固定 8 值：`disabled/entry-unavailable/timeout/rate-limited/upstream-error/bad-response/unsupported-question-type/budget-exhausted`（`decision-tool.ts:190-199`）。
- `[F]` `mw decide run` 的 JSON 载荷：旧键（`available/answers/reason/confidence_source/latency_ms/transport/model/attempts`）+ 权威键（`decision_id/mode/acted/escalated_reason/state_digest`），`mw.py:887-915`；`available` 仅在 `status in ("acted","suggested")` 为真（同处），即 `escalated` 永不被包装成可用。
- `[F]` 版本化入口：`mw decide run <dp> --stdin` 只收 `{material, meta}` 两个键（多余键拒绝，`mw.py:988-996`）；`meta` 未知键拒绝、`initiator_role` 归一化且未知→`unknown`（不默认 pm）、空 `task_key/retry_of` → `None`（`mw.py:1010-1050`）；同一 `logical_id` 已有 start 行则**不重发**，返回关联行（`mw.py:1146-1160`）；`material` 先变成 `Trigger.from_mapping(...)` 的 data 再进 `decide_for(intent="answer")`（`mw.py:1200-1230`）。

#### 2.5 工具结果与回执（TS 消费面）

- `[F]` 工具入参 schema（`ASK_DECISION_PARAMETERS`，`decision-tool.ts:1715-1758`）：`dp` 枚举（`:132` 常量）、`trigger`（1..256，禁空白与冒号）、`question`（≤64）、`note`（≤800）、可选 `material`（宽松对象，闭集由 `validateDecisionMaterial` 判，`:1628-1706`）、`key`/`task_before`/`task_key`；`additionalProperties:false`。
- `[F]` 角色是结构性的：`runAskDecision` 先从注册窗口取 `initiatorRole`（默认 `"unknown"`），PM-only dp 且在非 pm 角色直接零 spawn 拒绝 `role-forbidden`（`:1228`）；角色来源 `initiatorRoleFromWorkerTask`（`:715-726`）读 worker 卡 frontmatter `type:`，仅 `coding/research/review` 合法，否则 `unknown`——`unknown` **不会**被升级成 pm。
- `[F]` key/task 关联：`execute` 里显式比较 `params.key` 与窗口 ownerKey、`params.task_key` 与 worker task，若不一致即拒绝 `input-incomplete` + `missing_fields:["meta.key"|"meta.task_key"]`，不把模型参数当成关联事实（`decision-tool.ts:1885-1905` 附近）。
- `[F]` 材料路径 `runMaterialAskDecision`（`:1294-1384`）：验证 material（`:625-676`）→ 必填 `meta.key` → `buildDecisionToolMeta`（新 `logical_id`、`record_version=2`、真实 task_key/role/retry_of）`:678-702` → stdin 发送 → 校验 `decision_id/mode/acted` 三键（缺一即 `bad-response`）→ 把答案解析回「PM 写入的候选」（dp3 用 `resolveHandlingSelection` `:728-742`，其它取首问的字符串值 `buildSelection` `:744-757`；答案集不属于本契约即 `bad-response`，不硬映射）→ 自动写 `consumed` 回执（`:1370-1380`）。
- `[F]` 回执面 `decision_receipt`：只认本窗口 `asked` map 里的 `decision_id`（未知名 → `unknown-decision`，不写行）；`executed` 的 action 必须属于 10 值闭集（`DECISION_EXECUTED_ACTIONS`，`:778-789`），`settled` 的 outcome 必须属于 5 值闭集（`:791-792`）；未知动作只「未记录」（`:2015-2020`）；`task_after` 只有在 `meta.task_key` 非 null 且快照结构合法时才接受（`:1995-2002`）。写失败被如实报告为 `status:"failed"`（`:889-930`），不推断成功。
- `[F]` dp25 签名路径 `runSignoffAskDecision`（`:1385-1499`）：只调 `mw decide sign <key> --stdin`，把 CLI 回执 1:1 映射为 `signoff{status,second_approval,record_status,model_called,feedback_stages,handoff}`；`finalize` 由 CLI 在同一次判断内写签收文件，工具侧不再批准/再判；`continue`/`user-confirm` 零签收写入并回具体下一步；无 mode 就**不填** mode（不伪造权威）。
- `[F]` 防重试：`ASK_DECISION_MAX_BLOCKED_PER_TURN = 2`（`:117`），按 dp 计数、`turn_start` 清零，达到上限给 `terminate:true` + 终止指令（`:2035-2065`）；每次阻塞/回答写一行 trace。

#### 2.6 八入口现状核对结论

| 目标入口 | 运行注册 | 材料契约 | 选项/候选 | 现状定性 |
|---|---|---|---|---|
| dp-w-type | 否（旧 dp1，`decision_points.py:583` 三选项） | 需新增（目标/要求/交付物） | 目标四值 coding/research/review/vision（AC-044） | `[T]` |
| dp-pm-steer | 否（旧 dp2，`:602` 附近四选项） | 需新增（目标/真实执行/约束） | 目标 narrow/split/direct-exec/escalate（AC-045） | `[T]` |
| dp-w-check-task | 否（旧 dp3 动态候选） | 需新增（问题+四背景+候选） | 目标三固定项（AC-046） | `[T]` |
| dp-QG | 否（旧 dp6 pass/fix/reopen，`:654`） | 需新增（审核材料） | 三值可沿用语义 | `[T]` |
| dp-gate-approve | 否（旧 dp15 continue/narrow/revoke，`:700+`） | 需新增（gate 背景 + PM 预拟 note） | 目标 approve/steer/need_fix/reject（AC-007） | `[T]` |
| dp-sign-key | 否（旧 dp25 `q-conclusion`，`:869-890`） | **已有四部分材料契约** | 三值 finalize/continue/user-confirm | `[T]`（材料可复用） |
| dp-auto | 否（零命中） | 需新增（PM 现场问题/候选/依据） | PM 提供，不预置 | `[T]` |
| dp-route | 否（零命中） | 需新增（主体/对象/具体问题） | 七目标静态枚举 | `[T]` |

### 3. 八入口统一协议字段候选（分层，`[S]`）

目标：把「业务材料 / 本地关联 / PM 预拟 note / 模型理由 / 实际执行与结算 / 版本与关联」分成互不冒充的层，且每层有唯一校验点。

| 层 | 字段（候选） | 谁能写 | 模型可见 | 唯一校验点 | 备注 |
|---|---|---|---|---|---|
| A 业务 material | 每入口生成的 `material` 对象（闭集键见 §4） | 发起者（PM/Worker）按合同逐字写 | 是（经 allowlist 投影） | TS `validateDecisionMaterial`（生成契约）+ Python `REQUIRED_STATE_FIELDS`/`state_field_issues`/`state_unknown_key_issues` | 不接受截断，超预算整份拒绝 |
| B 本地 identity/association | `record_version/logical_id/key/task_key/initiator_role/retry_of`（+ 可选 `task_before`） | 工具/窗口（结构性），不接受模型自报 | 否（`AUDIT_STATE_PATHS` + `meta` 永不下发） | `buildDecisionToolMeta`（`decision-tool.ts:678`）+ `mw.py:_decide_meta_from_payload`（`:1010-1050`） | `unknown` 不升级；task_key 空即 null |
| C PM 预拟 note | `pm_note{subject, planned_action, basis{goal,evidence,budget,authority}}`（gate/pending-review 专用；其余入口可空） | 仅 PM | 是，但**独立字段**进入投递材料 | 生成契约的 `pm_note` 子对象 + 分列存储 | 与 D 层分开保存（AC-007） |
| D 模型理由 | `rationale{choice, reason, key_basis[]}` | 决策服务（模型） | 是（工具结果/记录） | 服务答案结构校验（`_decode_answers` + `_value_fits`） | 不得覆盖 C；不得作为执行证据 |
| E 实际执行/结算 | `executed{action,result}`、`settled{outcome,reason}`、`signoff{}` | 真实执行者/消费者 | 否（进生命周期账本） | `decision_receipt`（`decision-tool.ts:1760/1980-2040`）+ `decision_lifecycle` 闭集 | 选择 ≠ 执行；settled ≠ 任务完成 |
| F 版本/关联 | `entry_schema_version/questions_version/material_sha256/logical_id/decision_id/retry_of/observed_at` | 生成契约 + 工具 + CLI | 部分（questions_version/material 摘要） | `questions_version` 哈希（`decision_points.py:404`）、`decision_id = <dp>:<logical_id>`（`mw.py:1190`）、`retry_of` 链 | 同事项重放靠 F 层判定，不靠文本相似 |

候选判别字段（放在生成的 registry entry 上，`[S]`）：

```
kind: "fixed" | "dynamic-candidates" | "route-targets"
material_fields: DecideRegistryField[]      # A 层闭集（必填 + 可选）
question_set: [{id, type, choices? | source_field?}]
candidate_source: "static-enum" | "pm-supplied:<field>" | "entry-targets"
candidate_bounds: {min?: int, max?: int, id_scheme?: "contiguous-cN" | "free"}   # 业务侧显式声明，缺省 = 无旧限制
target_entries?: string[]                   # 仅 route
role_scope: "pm" | "worker" | "both"
failure_vocabulary: {...}                   # 引用既有两组固定词汇，不新建同义词
```

`[S]` 关键约束：`candidate_bounds` 必须**按入口显式声明**，没有声明的入口不继承 dp3 的 2..5/`cN`；`target_entries` 由生成器与注册表对比，禁止包含自身与旧编号；`role_scope` 只表达「谁有资格发起」，不授予任何新工具权限。

### 4. 逐入口材料/问题/选择校验候选（`[T]` 目标 + `[S]` 候选 schema）

| 入口 | 材料候选（A 层） | 问题/选项 | 选择校验候选 | 失败候选 |
|---|---|---|---|---|
| dp-w-type | `task_goal/task_requirements/task_deliverables`（复用现有三字段语义，`decision_points.py:1525-1537`） | 单选，静态 4 值 `coding/research/review/vision` | 值 ∈ 四值；`vision` 另需「图像能力已核实」事实（见 §4.1）；`type` 字段与选项一致；不得用 `unknown` 换资格 | 缺材料 → `input-incomplete`；无图像能力 → 阻塞（非回退 coding） |
| dp-pm-steer | `task_goal/task_requirements/task_deliverables/pm_decision_background` + 可选 `worker_execution`（现 dp2 契约） | 单选 4 值 `narrow/split/direct-exec/escalate` | 值 ∈ 四值；`narrow` 不得改变已确认目标（材料里目标原文是判据）；`escalate` 必须能指向具体问题（材料校验只保证字段非空，语义留人工/评审） | 缺材料/缺目标原文 → 阻塞 |
| dp-w-check-task | `question` + `background{task_goal,current_state,decision_reason,constraints_impact}` + `evidence_plan{unknown,source,authority,stop_criterion}`（补证分支专用） | 单选 3 固定值 `continue / stop-with-conclusion / continue-with-evidence`（目标措辞按 AC-046；技术 id 待设计） | 值 ∈ 三值；选 `continue-with-evidence` 时 `evidence_plan` 四字段必填且 `stop_criterion` 非空；选 `stop-with-conclusion` 时结论/证据引用非空 | 缺 plan 字段 → 阻塞；**不再接受 2..5 动态候选、不产生 `cN`** |
| dp-QG | 审核对象/要求/证据/覆盖面（目标材料待细化，AC-005/AC-053） | 单选 3 值 `pass/fix/reopen` | 值 ∈ 三值；`pass` 不得在「机器硬门失败/证据缺失」时被判有效（由上游材料字段 + 硬门事实共同约束，需在生成契约里声明 `blocking_facts`） | 缺证据 → 业务放行 0（AC-006） |
| dp-gate-approve | gate 背景/当前状态 + `pm_note{subject,planned_action,basis{goal,evidence,budget,authority}}` | 单选 4 值 `approve/steer/need_fix/reject` | 值 ∈ 四值；`pm_note` 四要素必填；C/D 分列存储；`steer`→后继 dp-pm-steer、`need_fix`→后继 dp-auto 作为**后继请求**记录，不由 gate 选项推断已整改 | 缺 note 要素 → 阻塞，不默认 approve |
| dp-sign-key | `delivery_goal/actual_completion/verification_evidence{verified,unverified}/unfinished_impact`（现有四部分，`decision_points.py:1694-1701`） | 单选 3 值 `finalize/continue/user-confirm` | **三数组必须是 array，`[]` 是真实值，`null`/缺项不得当合法材料**；`verified` 与 `unverified` 分列；不得用任务数/完成声明替代证据；`finalize` 才写签收文件 | 数组为 null/缺项 → 阻塞；`continue/user-confirm` 零签收写入 |
| dp-auto | PM 现场问题、目标/真实状态/已尝试/未知事实、权限约束 + `handling_options[]`（PM 提供） | 单选，候选来源 = `pm-supplied:handling_options` | ≥2 个**可区分**候选；id 只要求在本请求内唯一（不要求 `c1..cN`）；label/description 非空；**不得出现材料之外的候选**（选择值必须命中 PM 提供的 id 集合） | 候选 <2 或越集 → 阻塞；缺理由/依据 → 记录不完整，不默认首项 |
| dp-route | 决策主体/判断对象/具体待决问题（多个独立判断先拆） | 单选，静态 7 值 = 其余七入口 id | 值 ∈ 七目标且 **`dp-route` 自身不在枚举**；路由答案只解释「进入哪个入口」，不携带业务结论；进入后必须按所选入口的重材料/问题合同另发一次决策 | 非法/缺失 → 阻塞；不得把 route 答案当业务放行 |

#### 4.1 三条特别核对结论

1. `[F]` **dp-sign-key `[]≠null`**：契约层已用 `empty_is_value: True` 把「空数组 = 真实无」写入三字段（`decision_points.py:1812-1830`），提示词也写明「[] 表示真实无该项」（`decision-tool.ts:770-775`）。`[S]` 迁移时必须保留：`null` 与缺项都不能被接受为合法材料；`required` 判定用「键存在且是 array」，不是「非空」；TS `pushFieldIssue`（`:519-551`）当前对 `array` 只检查 `Array.isArray`，不会把 `[]` 判空——与目标一致，需保留该语义并加断言。
2. `[F]` **dp-w-check-task 三固定选项**：现状是 dp3 动态候选（`decision_points.py:622`），候选由 PM 现场给且受 2..5/`cN` 限制。`[T]` 目标改为三项固定语义（AC-046），`[S]` 实现候选：`question_set` 用 `static-enum`，`candidate_bounds` 不声明；**旧动态限制只保留在历史解释与本报告，不迁移到新入口**，也不作为 dp-auto 的限制。
3. `[F]` **dp-auto 候选来源与理由依据**：AC-042 要求「仅从 PM 准备候选选择，理由与关键依据可核，未准备新方案出现数 0」。`[S]` 校验最小集：`handling_options` 数组 ≥2、id 唯一、description 非空；发送时把候选渲染成动态枚举（复用 `_dynamic_choice_labels` 机制但**替换其业务上限**）；答案必须命中该集合；`rationale.key_basis` 必须引用材料中出现的字段/事实名（弱校验：非空 + 至少一项可在材料键集中找到），强语义判断留评审。`[U]` 「依据可核」的机器判据尚未有权威定义。
4. `[F]` **gate note 分列**：现状 dp15 仅有 `continue/narrow/revoke` 与 L0/L1 state，无 PM note 结构（`decision_points.py:700+`）。`[S]` C 层必须是独立字段（`pm_note`），并在归档/账本分列保存；D 层模型理由不得覆盖 C。`[U]` 现有 `decision_archive`/`decision_lifecycle` 是否有分列槽位未读，需后续核实。
5. `[F]` **route 不代业务结论**：三文件中无 route 实现；现有工具输出结构（`AskDecisionAvailable{mode,acted,answers,selection}`，`decision-tool.ts:262-292`）会把 `acted` 传给调用方。`[S]` route 的合法结果必须固定为 `acted=false`（或直接不设 executor），且 `selection` 只允许 `question:"entry", id:<七目标之一>`；调用方必须用新 `logical_id` 再发一次业务决策，路由决策与业务决策在账本中是两条不同记录。
6. `[T]` **失败不默认**：AC-012/AC-043 明确「不默认首候选/approve、不偷换通道、不造有效选择」；`[F]` 现有代码已满足机制（枚举闭集、`_value_fits`、置信度门、`available:false` 即阻塞），迁移时不得新增「取第一个候选」或「answer 缺失时视为 approve」的兜底。`[S]` 安全/失败审计行允许存在（`available:false, acted:false, escalated_reason` 非空），且不得被计入「新增有效业务决策」。

### 5. 两种合法技术方案的比较（`[S]`）

#### 方案 A：现有 Python 注册单源 + 生成 TS 判别契约（推荐）

做法：扩展 `decision_points.py` 的注册数据结构（`kind/material_fields/candidate_source/candidate_bounds/target_entries/role_scope/failure_vocabulary`），`registry_snapshot()` 导出；`scripts/gen_decide_registry_ts.py` 生成 `decide-registry.generated.ts` 的判别联合类型 + 每入口常量；`decision-tool.ts` 的四个硬编码集合（`:132/:169/:214/:219`）改为从生成物读取；`mw decide dp export --write` 的 JSON 同步扩展。校验逻辑仍分两层：TS 生成契约做形状/闭集，Python `decide_for` 做权威判定（现状分工不变）。

- Pros：
  - 单权威、单序列化器、现有两把字节级漂移锁可直接覆盖（`test_decide_registry_ts_lock.py:15-34`，`test_decide_registry_export.py:78`）；AC-001「可调用集合精确等于八项」有机器判据。
  - 复用已验证机制：闭集键、`state_field_issues`、`model_state_for` 投影、`questions_version` 哈希、`audit` 路径剥离。
  - TS 侧获得**判别类型**（`kind` 收窄 material 形状），模型/工具参数在编译期与运行期同时受限；`dp-route` 七目标枚举可生成，不会与八入口集合漂移。
  - 迁移可分批：先注册表 + 生成物，再工具/CLI 消费者，最后退役旧编号；每步都有现成锁测试。
- Cons：
  - 需要改 Python `DecisionPoint` 的 frozen 形状与 import-time 校验（`:404-470`、`:2838`），牵动 25 条注册与快照 schema 版本（`SNAPSHOT_SCHEMA=3`，`:957`）；旧 key 的 registry 快照字节会变，需要明确下游认领（P-018/P-019）。
  - `mw.py` 的 `dp export`/case/UI 消费者需同步；`test_decide_registry_export.py` 的 wired 表也要改。
  - 判别联合让生成器复杂度上升（每入口字段不同），生成器自身需要单测（渲染顺序、类型收窄）。

#### 方案 B：共享纯协议描述（语言中立的 protocol 文档/JSON）由现有注册与工具共同消费

做法：新建一份与语言无关的协议描述（如 `packages/multi-workers/protocol/decision-entries.v1.json` + 生成或手写 schema），Python registry 与 TS 工具都从它读取/校验；注册表只保留 tier/执行器等运行事实。

- Pros：
  - 语言中立，UI/文档/测试可共用；不依赖 Python 导入即可校验 TS 侧。
  - 便于把「八入口 + 七目标路由」作为数据审查，而非散落在代码常量里。
- Cons：
  - 引入**第三份权威**：运行时仍由 Python registry 决定行为，协议文件若与 registry 不一致，需要额外漂移锁与双向校验，风险高于方案 A。
  - 现有生成链（`gen_decide_registry_ts.py` + 两把锁）已解决同一问题；方案 B 等于重造一条并行链，短期净收益低。
  - 手写 schema 容易与 `STATE_FIELD_DESCRIPTIONS` 约束（`empty_is_value/max_items/enum`）重复定义，重演「两个契约漂移」的老问题。

#### 推荐

采用 **A 为主、B 为派生**：Python 注册是唯一权威 → 生成 TS 判别契约 + 导出 JSON/协议视图（协议文档由快照渲染，不手写）。这样既满足语言中立展示，又不产生第二权威。`[S]`

#### 八行活动表与只读退役（候选说明，`[S]`）

| 入口 | 触发 | 生产者 | 写入者 | 消费者 | 退役旧职责 |
|---|---|---|---|---|---|
| dp-w-type | 派发前 | PM | `mw decide run --stdin` | 派发接线 | dp1（读侧解释保留） |
| dp-pm-steer | checkpoint 收敛 | PM | 同上 | PM 编排 | dp2 |
| dp-w-check-task | Worker 自主判断 | Worker | 同上（worker 角色） | Worker 终态 | dp3（动态候选不迁移） |
| dp-QG | 正式质量审核 | PM/审核者 | 同上 | QG 结论消费 | dp6 |
| dp-gate-approve | gate 送审 | PM | 同上 + `pm_note` 分列 | gate 状态转换 | dp15 + dp20 关闭职责 |
| dp-sign-key | key 收尾 | PM | `mw decide sign --stdin`（同次写签收） | 签收硬门 | dp25（材料契约复用） |
| dp-auto | PM 现场问题 | PM | `mw decide run --stdin` | PM 行动执行 | dp7 门失败处置 |
| dp-route | 临时问题先路由 | PM | 同上（`acted=false`） | 入口选择→再发业务决策 | 无旧对应 |

退役解释（`[T]` AC-002/AC-013）：旧编号在解析层直接拒绝（复用 `get_decision_point` 的未知 id 路径即可，`decision_points.py:~900-910`），**不保留可调用别名**、不保留「旧 dp3 运行兼容」；历史记录只读展示「已退役、不可发起」；拒绝必须产生可审计事实（request 数、业务执行数、有效业务决策数均为 0），且安全/失败审计行与「新增成功裁决」在记录上可区分。

### 6. 旧业务限制与传输/资源边界分离（`[F]` + `[S]`）

| 类别 | 现值/出处 | 迁移处置候选 |
|---|---|---|
| 传输/资源：状态字节 | `MAX_STATE_BYTES = 8192`（`decision_points.py:175`），超限整份拒绝（`:5372`） | 保留为全局边界，所有入口共用 |
| 传输/资源：问题数 | `DecisionConfig.max_questions` 默认 8，注册期校验（`:453-454`、`:202`） | 保留；八入口每入口问题数 ≤ 该值 |
| 传输/资源：可答类型 | `choice/score/noul`（`decision_backends.py:153`）；`box` 需图像通道（`decision_backends.py:157-164` 常量） | 保留 |
| 传输/资源：模型/端点 | 单一 timi `/v1/decisions`，`jev-latest`，无回退（`decision_backends.py:1-40`） | 不改 |
| 业务：2..5 候选 | `DYNAMIC_CHOICES_MAX=5`（`:1110`）+ 交叉检查（`:2512`）+ TS `:227-229` | **不迁移到 dp-auto/dp-w-check-task**；仅作历史解释 |
| 业务：`cN` 连续 id | `_DYNAMIC_CHOICE_ID_RE`/`dynamic_choices_value_error`（`:1114-1145`） | 同上；新入口的候选 id 只要求请求内唯一 |
| 业务：label ≤80/单行/唯一 | `:1136-1145`、TS `:588-608` | 可保留为**候选质量规则**（若产品确认），但不与「2..5」绑定 |
| 业务：note ≤600B / key ≤48B | TS `NOTE_MAX_BYTES=600`、`TASK_KEY_MAX_BYTES=48`（`decision-tool.ts:126-130`） | 保留为本地 meta/提示词限制 |

### 7. 候选文件 / 生成器 / 测试接口（只设计，不实现）

#### 7.1 候选文件与改动面（`[S]`）

- `packages/multi-workers/decision_points.py`：`DP_REGISTRY` 八条新 entry；`REQUIRED_STATE_FIELDS`/`OPTIONAL_STATE_FIELDS`/`STATE_FIELD_DESCRIPTIONS`/`MODEL_STATE_FIELDS` 每入口声明；`STATE_FIELD_CROSS_CHECKS` 增加 per-entry 候选规则（替换 `dynamic_candidates` 的全局 dp3 绑定点，`:2512`）；新增 `ENTRY_KINDS`/`RETIRED_DP_IDS`（只读解释用）。
- `packages/multi-workers/scripts/gen_decide_registry_ts.py`：渲染判别联合（`EntryKind`、`MaterialByEntry`）、`ROUTE_TARGETS`、`RETIRED_DP_IDS`；沿用现有 header/格式与 `--check`。
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`：生成物（不手改）。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`：`:132/:169/:214/:219` 改读生成物；`:553-613` 的 dp3 专用校验器改为 `validateCandidates(entry, value)`（按 `candidate_source/bounds` 分派）；`:744-757` 的 selection 解析按入口合同分派。
- 新增候选：`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-protocol.ts`（信封分层常量/类型，纯函数，无 I/O）；`packages/multi-workers/decision_protocol.py`（可选，若 Python 侧也需要同一层名）。
- `packages/multi-workers/mw.py`：`_dp_export`（`:2870-2960` 符号）与 `--stdin` 路径（`:1108-1290`）适配八入口 `kind`；`dp export` 的 wired 表更新。
- 文档/视图：`packages/multi-workers/docs/decision-protocol.md`（由快照渲染或人工同步，但需漂移检查）。

#### 7.2 测试接口与隔离断言（映射 AC）

隔离方式（全部 `[S]`）：临时目录 + 临时 `.agenticdoc`，faux/monkeypatch 后端（不触网、不读 `~/.pi/agent/auth.json`），`decision_points.ARCHIVE_WRITER` 注入记录器（`:4275` 附近 DI seam），`mw.py` 侧用 `tmp_path` 与注入 store；不读活 `.mw/decide-points.json` 的真实内容，测试自建 fixture。

| AC | 测试文件（候选） | 断言（隔离、可失败） |
|---|---|---|
| AC-001 | `packages/multi-workers/test_decision_entries_registry.py` | `registry_snapshot()["points"]` 的 id 集合 == 八目标；`len(points)==8`；每个 `kind/candidate_source` 合法；旧 25 编号不在集合内；`gen_decide_registry_ts.render()` 字节相等 |
| AC-002 | `test_decision_legacy_alias_refusal.py` + `pm/decision-tool.test.ts` | 对每个旧编号调用 `runAskDecision`/`decide_for`：`available=false`，`spawned=false`（TS）/零后端调用（Python），记录器收到 `unknown-decision`/`DecisionInputError`；业务执行行数 0；审计行存在且 `acted=false` |
| AC-003 | `test_decision_retired_inventory.py` | 仓库内 `ASK_DECISION_DP_IDS`、case/UI 提交项、prompt 中旧编号命中数为 0；历史解释/拒绝测试文件带 `retired` 标记；不出现旧编号可调用别名 |
| AC-004 | `test_decision_entry_materials.py` + `decision-tool.test.ts` | 八入口各自「合法材料 → 可发送」「缺一字段 → `missing_fields` 精确」「增权/降目标/冒充执行字段 → 闭集拒绝」；dp-sign-key 四部分语义、dp-w-type 四候选、dp-pm-steer 四选项、dp-w-check-task 三固定项各一组正反例 |
| AC-012 | `test_decision_failure_no_default.py` + TS 单测 | 后端 `available:false`（每类 reason）→ 工具载荷 `available:false`、`action=blocked-ask-human`、业务执行 0、无默认首候选/approve；`disabled` 明确不等于放行 |
| AC-013 | `test_decision_retired_history_readonly.py` | 历史行（含旧 id）可读：`detail`/列表渲染不抛错、标注 retired；文件字节哈希前后相等；按当前注册补造字段数为 0 |
| AC-014 | `test_decision_chain_attribution.py` | producer→writer→consumer 三段 `logical_id/decision_id` 可 join；`consumed/executed/settled` 分列；`available:true` 不代表 executed；秘密明文扫描 0；注入脚本执行 0 |
| AC-040 | `test_decision_route_entries.py` + TS 单测 | `dp-route` 合法答案 ∈ 七目标且不含自身；`acted=false`；路由后未发业务决策时业务放行/执行行数 0；非法/缺失 → 阻塞 |
| AC-041 | `test_decision_route_role.py` | 固定节点可不经 route 直调（额外 route 调用数 0）；PM 用 route 选 Worker 入口后仍按 Worker 角色资格判定（`role-forbidden` 如适用）；同事项重复审批 0 |
| AC-042 | `test_decision_auto_candidates.py` | dp-auto 候选来自 PM material；答案越集 → 拒绝；只给 1 个候选 → 阻塞；不出现未准备候选（断言 `selection.id ∈ material ids`）；`c1..cN`/2..5 限制不生效（构造 6 个/非 cN id 的合法用例） |
| AC-043 | `test_decision_all_entries_failure_matrix.py` | 八入口 × {非法材料, 缺材料, 服务不可用, 选择不匹配} → 具体阻塞原因可见、受门控业务动作 0、无默认首项/approve、失败审计行可记录且 `acted=false` |
| AC-044 | `test_decision_dispatch_type.py` | dp-w-type 候选精确 4 值；`vision` 在「图像能力已核实」时合法；能力未知 → 启动数 0（不回退 coding）；既有 rag-research 等框架类型不被移除（注册外类型仍可用） |
| AC-050 | `test_decision_lifecycle_linkage.py` | `executed` 必须带真实 action；未执行时写 executed → 拒绝/未记录；`settled` 不把任务标 done；`task_before` 不被当前状态回填；observation time 非递减 |
| AC-051 | `test_decision_null_vs_empty.py` | dp-sign-key 三数组：`[]` 合法；`null`/缺项 → `missing_fields`；不得把 `null` 归一化为 `[]`；`verified/unverified` 分列；历史字节不变 |
| AC-052 | `test_decision_replay_idempotence.py` | 同 `logical_id` 重放不产生第二次模型调用（复用 `mw.py:1146` 的 start 行语义）；并发两写只一行生效；实质材料变化 → `material_sha256` 不同 → 需新 `logical_id`（带 `retry_of`） |
| AC-053 | `test_decision_qg_verdict.py` | dp-QG 三值语义；硬门失败/证据缺失时 `pass` 不被接受为有效放行；`reopen` 不授修改权；QG 结论不代签收/审批 |

生成器/契约锁（不新增权威，只加断言）：`test_decide_registry_ts_lock.py` 增加「八入口 id 集合 + `kind` 与 `target_entries` 一致性」；`test_decide_registry_export.py` 增加「`RETIRED_DP_IDS` 与旧 25 编号互补」；`test_decision_dp_cli.py`（已存在）增加「旧编号 CLI 拒绝」。

## 残留与未验证

1. `[U]` **未读范围**：`decision.py`、`decision_lifecycle.py`、`decision_wire.py`、`decision_signoff_result.py` 正文、`triage-client.ts`、extension `index.ts`、dashboard/UI 与 case 文件、`decide_archive.py`。因此「producer→writer→consumer→projection 全链」只在 TS 工具 + `mw.py` 片段 + `decision_points` 范围内核实；归档/生命周期/PII 过滤的细节未审计。
2. `[U]` AC 状态：本报告**不声称**任何 AC 通过、不声称 QG/签收/相位门通过；§7.2 只是测试接口候选，未运行、未落地。
3. `[U]` dp-w-type 的 `vision` 图像能力门禁实现位置未知：三文件零命中 `vision`；`decision_points.py:1730` 只是 `task_type` 描述枚举。能力核实主体、失败措辞与落点需设计。
4. `[U]` `pm_note` 分列存储：现有 `decision_lifecycle`/归档是否有独立槽位未核实；AC-007「PM note 与模型理由分别保存」的机器实现尚无法断言。
5. `[U]` 旧编号退役的完整强度：`decide_archive` 是否对 dp id 做集合校验、case/UI 是否存在可提交旧 id、prompt 是否残留旧 id 均未逐项盘点；AC-002/AC-003 的「0」需要一次真实 inventory（含 `packages/multi-workers/decide_cases/`、`docs/`、dashboard assets）。
6. `[U]` dp-auto「理由依据可核」的机器判据未定义；本报告只给弱校验候选（非空 + 引用材料键），强语义判断需评审。
7. `[U]` `SNAPSHOT_SCHEMA` 从 3 升级到 4 的下游影响未评估：`decide_registry.json` 消费方（dashboard/CLI/文档）、`test_decide_registry_export.py` 的 wired 表、`test_decision_pin_contract.py` 等未读。
8. `[U]` `decision.DecisionConfig` 的 token 预算（注释提到的 `max_state_plus_question_tokens=32768`）只从 `decision_points.py:175` 注释得知，未在 `decision.py` 正文核实。
9. `[S]` 时间盒：本次为单次只读研究，阅读+落盘在 25 分钟窗口内完成（无测试/CLI/探针耗时）；未做第二轮交叉核验。
10. `[S]` 明确禁止项复核：未读 `.mw/decide-points.json`、`.mw/decide.json`、任何 ledger/签收/凭证文件；未写证据文件之外的任何路径；未运行 build/test/install/commit；未起停服务。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq18-design-protocol-full/task.md`（要求 1-5 与交付段契约）。
- 目标：`.agenticdoc/goal.md`（项目级目标锚点，任务卡引用 `:5`）。
- 目标要求与 AC：`.agenticdoc/mw-dp-consolidation/spec.md` §1.1（八入口目标表）、§1.2（各入口职责/选项确认）、§1.5（dp-auto/dp-route/固定节点/临时问题）、§2（业务约束）、§3（AC-001～004、012～014、040～044、050～053 正文）、§4（未决项/写面未批准）、§5（前馈与坑点）。
- 源码事实（本报告主要证据）：
  - `packages/multi-workers/decision_points.py`（5769 行，全文）
  - `packages/multi-workers/decision_backends.py`（1123 行，全文）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（2072 行，全文）
  - `packages/multi-workers/mw.py:870-1290`（`_decide_run` / 信封 / `--stdin`）与 `:2870-2960` 符号清单（部分）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts:1-120`（生成头/形状）
  - `packages/multi-workers/scripts/gen_decide_registry_ts.py`（经测试引用确认生成关系，未全文读）
  - `packages/multi-workers/test_decide_registry_ts_lock.py`（全文）、`test_decide_registry_export.py`（函数清单/关键行）
- 旧研究说明：任务卡要求「旧研究作为问题线索，不当独立证据」；本报告未引用任何旧报告作为事实来源，全部 `[F]` 均落到上述源码行。
- 证据文件（本文件）：`.agenticdoc/mw-dp-consolidation/evidence/research/design-protocol-full-read-20261026.md`；key 内相对路径 `evidence/research/design-protocol-full-read-20261026.md`。
