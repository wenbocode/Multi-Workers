# RQ21 — /api/dps、观察提交/骨架/校验/历史、令牌角色与失败审计边界（Python monitor/playground 全文只读）

> key `mw-dp-consolidation`（DESIGN；实施未批准）。type research，images=no，时间盒 25 分钟，唯一证据文件。
> 只做静态读码：未运行测试/build/install/CLI，未起停 monitor 或浏览器，未调用 provider/决策服务，未读活配置（`.mw/decide.json`/`decide-points.json`）、gate/ledger/签收/凭证，未改源码/UI/回执，未签收。
> 证据等级沿用 RQ17：**L0** 行级静态事实。本文全部为 L0；不宣称 AC/QG/设计/运行/签收通过。

## 结论

1. **覆盖面**：`packages/multi-workers/decision_monitor.py`（2750 行）与 `packages/multi-workers/decision_playground.py`（1775 行）**全文读完至 EOF**（分段 700/700/650/全部）。Python 观察链的现状是"进程级服务 + 注入式 provider"，本次补齐了 RQ20 明确未读的那一半。

2. **`/api/dps` 不是注册表文档，而是再投影**（`_act_dps` L1845-1884）：只取 `registry_snapshot()` 的 12 个字段（id/tier/default_enabled/default_mode/questions_version/enabled/mode/config_source/executor/wired/required_state_fields/optional_state_fields/questions），丢弃 `description`/`p0_consequences`/`trigger`/`adopted_at`/`wiring_note`/`model_state_fields`；并叠加**活配置**的 `effective.enabled/mode/source`。且 `wired` 在 `registry_snapshot()` 里恒为 `UNWIRED_SNAPSHOT_WIRING`（全 25 行同一个常量，`decision_points.py:961-972`）。因此：AC-001 的三处 id 集合核对可以做，**`/api/dps` 与 `decide_registry.json` 的字节比对不可能成立**（RQ20 的"直出注册表"措辞需收紧）。

3. **"退役"在整个 Python 观察面不存在**：monitor、playground、注册表快照均无 `retired/status/successor` 概念（全仓非测试代码 0 命中，仅测试命名有 retired 字样）。旧编号在 Python 侧的实际可提交面有三处，且退役后**没有一处给出"已退役 + 继任者"的明确拒绝**：
   - `/api/dps` → 25 行全量投影（`registry_snapshot()` 无过滤）；
   - `/api/test/cases` 的 `CASE_IDS` 硬编码 `dp1/dp2/dp3/dp25`（monitor L208-213）+ 随包 `decide_cases/{dp1,dp2,dp3,dp25}.json`；
   - 观察提交 `observe_only` **只绕过 per-DP `enabled` 门**（`decision_points.decide_for` 文档与 L5102-5106），所以若只把旧 DP 的 `enabled` 设为 false，旧 id 仍可被观察提交并**真实消耗 1 次模型调用**——`enabled` 不是退役判据。

4. **拒绝路径的现状不对称（这是可判定的设计缺口）**：同一退役 id 在四个提交面得到四种结果——`/api/test/submit` → 400 `invalid-field`（"not a registered decision point"，L2036-2044，provider 0 次）；`/api/test/validate` → HTTP 200 且 `ok:false` + `book-schema/decision_point "unknown decision point"`（playground `_review` L651-665）；`/api/test/scaffold` → HTTP 502 `playground-error`（provider 抛 `DecisionInputError` 被 `_provider_call` L1906 包住）；`/api/test/cases` 不带 `dp` 参数 → 整体 503 `case-invalid`（四例中任一例校验失败即抛，`_act_test_cases` L1920-1960，**列表面不是"变空"**）。四者都无法区分"退役"与"拼错"，也没有继任者提示。

5. **"模型成功"与"业务执行"在代码里已被硬性分开，词汇容易被误读**：观察提交走 `decide_for(intent="answer", archive=False, observation=...)`，命中 step 9 分支返回 `status="suggested"`、`acted=false`、detail "answer only, nothing acted on"（`decision_points.py:5556-5590`），executor 不可达；playground `_classify` 把 `suggested` 映射为提交态 **`succeeded`**（L1311-1330）——这里的 "succeeded" 只表示"决策链给出了合法回答（可能已花 1 次模型调用）"，与业务执行/放行无关。UI/设计文案必须沿用"回答成功 ≠ 业务成功"，不得把 `state=succeeded` 当作业务成功证据（AC-050）。

6. **三处 RQ20 绝对断言需校正**（详见 §B8）：(a)"两个 UI 面互不相通"→ 二者共用同一 Python 决策链、同一 `check_book` 门与同一注册表；不同的是传输封套与决策意图（HTTP/observe_only/intent=answer/scope=test vs 工具/CLI 的生产 act 路径），真正"不相通"的只是**第二份可提交选项副本**（手写 25 id 枚举）与**两套投影**（`/api/dps` 非注册表文档；`/api/history` 不传 `test_roots`）。(b)"窗口上下文不落盘"→ 观察路径**确实落盘** book 快照、捕获的 request/response 文本与 answer 投影（`.mw/decide-test/` 下），只是不进生产历史投影。(c)"退役后仅 UI 静默放宽校验"→ Python 侧同缺 retired，且退化形态更硬（503/502、白花一次模型调用）。

7. **推荐方案 A（注册表内显式 `status=active|retired` + `successor` + 只读 `ui` 块，只由服务端判定资格）**：`/api/dps` 增 `lifecycle`（只读），四个提交面统一 `retired-dp` 错误码 + 继任者，cases 列表按 status 过滤并允许 `include_retired=1` 只读；生成链只导出 active 集合到可调用枚举，retired 另表只做历史解释。备选方案 B（物理删除 + 独立退役对照表 + 各 throw 点兜底）也合法但把区分责任散到调用点，且不可逆。两者都**不得**用 UI 字段或 `ui.status` 授予运行资格/权——资格仍来自注册表 + 服务端判定。

8. **"源码存在 ≠ 部署身份"在 Python 侧有精确证据**：`CODE_FINGERPRINT`（monitor L421-442）的输入只有 `decision_monitor.py` + 三个 dashboard 资产（html/css/js），**不含 `decision_playground.py`/`decision_points.py`/`decide_registry.json`/`decide_cases/*`**。`identity_matches`/compatible-reuse（L2845 附近）因此无法发现"provider 或注册表已被替换"的实例。设计需增补 payload 侧指纹（注册表快照字节 + playground 源字节），否则"源码里存在退役实现"与"当前进程加载的身份"不能互相证明。

## 证据

### A. 覆盖面（全文读，逐段至 EOF）

| 文件 | 行数 | 覆盖方式 |
|---|---|---|
| `packages/multi-workers/decision_monitor.py` | 2750 | 全文（1-700、701-1400、1401-2100、2101-2800 含尾部 2801-2750 段共 4 次读取至 EOF） |
| `packages/multi-workers/decision_playground.py` | 1775 | 全文（1-650、651-1300、1301-1775 至 EOF） |
| `.agenticdoc/mw-dp-consolidation/spec.md` | 108 行（53AC 锁稿） | 全文读（§1.1-1.6、§3 AC 全表、§4/§5） |
| `.agenticdoc/goal.md` | 18 | 读 Goal/Context（目标锚点行） |
| `evidence/research/design-ui-submission-chain-20261026.md`（RQ20） | 全文 | 作为"待校正断言"与 UI 侧事实来源（今日**未**复读 dashboard.js） |

**定点读（明确非全文）**：`decision_points.py` 的 `registry_snapshot()`(1039-1094)、`UNWIRED_SNAPSHOT_WIRING`(961-972)、`GATE_KIND_ENUM`(1506-1512)、`DP_REGISTRY` id 清单与 dp3/dp6/dp15/dp16-dp19 局部(615-850)、`dp15` 行(768-775)、`decide_for` 文档与 L4995-5045/L5550-5590（observation 仅绕过 per-DP 门 + `intent="answer"` 走 step 9）；`decision_wire.py:687-706`（test sink 名）；`decision_history.py:3715-3740`（`load_history(test_roots=...)`）、`page(scope=...)`(760-780) 与 `SCOPE_KINDS`(203)。
**未读（明确声明）**：`decision_points.py` 其余约 5000 行（含 `_decide_for` 全部步骤、policy/gate 细节、字段描述表全表）、`decision_wire.py`/`decision_history.py`/`decision_book.py`/`decision.py` 全文、`mw.py` CLI、`pm/ui-bridge.ts`、`pm/decision-tool.ts`、`decision_dashboard.js/html/css`（今日未复读，沿用 RQ20 L0）、`decide_cases/*.json` 内容（只核文件名与装载逻辑，未读文件正文）。

### B. 现状事实（Python 观察面）

**B1 路由、令牌与角色（服务端解析，无 per-DP 角色矩阵）**
- 精确路由 12 条 + 前缀 2 条（`_ROUTES` L1495-1513、`_PREFIX_ROUTES` L1508-1513）：`health`(control)、`window`(control POST)、`shutdown`(control POST)、`bootstrap`(public POST)、`history`(page GET)、`dps`(page GET)、`test/scaffold`(page POST)、`test/cases`(page GET)、`test/validate`(page POST)、`test/submit`(page POST)、`test/history`(page GET)、`history/{opaque}`、`test/submissions/{id}`。无文件路径路由、无 DELETE/PUT 业务动作（`_match_route` L1514；405 明确）。
- 两种令牌角色：`TokenStore.role_for`（L635-650）先 `hmac.compare_digest` 比 control token（来自 `.mw/decide-monitor.secret`），再线性比内存 page token；**二者都无 per-DP 资格含义**。page token 只能由 `POST /api/bootstrap` 用一次性 60s boot code 换取（L1752），boot code 只出现在 URL fragment（`window_url` L2983 `#boot=`），不进 argv/日志（`log_message` 关闭访问日志）。
- Role 与资格分离：`_dispatch`（L1621）只做 `role_required != role` 的 403 `wrong-role`；**没有任何"该角色可调用哪些 DP"的映射**。观察提交里也没有 role 字段；`Observation.actor_kind` 在 provider 侧硬写为 `("human","user-explicit")`（playground L107 `SUBMIT_ACTOR`）。
- HTTP 边界（L1644-1660、`_CSP` L124、`BODY_LIMIT_BYTES` L96）：精确 Host、POST 精确 Origin、`Sec-Fetch-Site ∈ {same-origin,none}`、256 KiB body、无 CORS/cookie、CSP `default-src 'none'`、`no-store`。

**B2 `/api/dps`（再投影 + 活配置叠加）**
- 字段见结论 2。`enabled/mode/config_source` 来自 `load_points_config(control_root).effective(...)`（L1853），即**活配置**（本任务未读其内容；`_CONFIG_CACHE` 以 `(st_mtime_ns,st_size)` 为键，`decision_points.py:3189`）。
- 额外下发 `budget.max_state_bytes = decision_points.MAX_STATE_BYTES`(8192)、`observe_only: true`、`transport.{state,detail}`、`config.{layer,warnings}`。
- 响应统一 `_redact_payload`（L1276 前后）：所有字符串叶经过注入的 redactor；无 redactor 时字符串变 `<unavailable>`（fail-closed）。`_act_dps` 不因无 redactor 而 503（只有 playground 路由会）。

**B3 历史面（生产 scope 默认；test scope 不可见于该路由）**
- `_act_history`（L1779-1827）允许 query `key/dp/source/status/scope/limit/offset`，未知参数 400；`scope` 默认 `"production"`；`page(scope=...)` 只接受 `("production","test")`（`decision_history.py:760-780`）。
- 但 monitor 调 `decision_history.load_history(control_root, redact=...)`（`MonitorDeps.load_history`）**未传 `test_roots`**（签名 `decision_history.py:3715-3722`，默认 `()`），故 `scope=test` 会得到空页且 `stats.test_records=0`；测试记录只能经 `GET /api/test/history`（provider 的 `history()`）。
- 只读与不补造：`facets` 缺省为 `null`（`_facets_payload` 只在缺失时返回 None，不重算）；`warnings` 截 20 条；`detail` 用 opaque id（`OPAQUE_ID_PATTERN`），未知 handle 404，不接受原始 decision_id 或路径。
- 记录字节：读取路径无写操作（`load_history` 文档"read-only, no writes anywhere"）；本任务未运行前后 sha256 对比（见 §残留 2）。

**B4 四个提交面（typed 校验位置与失败形态）**

| 路由 | 客户端契约（monitor 层） | 注册表/typed 校验位置 | 零模型调用保证 | 退役/未知 id 现状 |
|---|---|---|---|---|
| `POST /api/test/cases`（GET） | 只允许 query `dp`，且必须是 `CASE_IDS` 之一 | `load_case` → `_validate_case` → `decision_points.question_override_issues`（monitor L300-330） | 读固定文件，无 credential/transport | 未注册 → `case-invalid` → **503**；不带 dp → 整表 503 |
| `POST /api/test/scaffold` | `_closed_json(allowed={"dp"})` | **monitor 不校验注册**，直接 `playground.scaffold(dp)` | `scaffold` 文档："no model call, no write" | `get_decision_point` 抛 → `_provider_call` 包成 **502 playground-error** |
| `POST /api/test/validate` | allowed `{dp,book,questions}`；book 必须是对象；questions 仅结构扫描 | provider `_review`（`check_book` + free-subtree 扫描 + registry state 门 + budget） | `validate` 无 client、无 wire scope（`_client(credentials,None)`） | `_review` 捕获 `DecisionInputError` → **200 + ok:false + book-schema** |
| `POST /api/test/submit` | `_closed_json(SUBMIT_KEYS, FORBIDDEN_KEYS)`，必填 `dp/book/submit_id`，`observe_only must be true`，`submit_id` 形态 | monitor 先 `get_decision_point`(L2036)，再 provider `_request_refusal` + `_review` | 唯一能到 provider/model 的路由（docstring） | **400 invalid-field**（provider 0 次） |
- `_smuggled_book_paths`（L1453-1490）是**注册表感知**的纵深扫描：被 dp 声明为 `object` 的子树整体跳过（dp1 `history` 等），故合法业务数据不会被拦；provider 侧 `object_smuggle_paths` 再对这些自由子树做同词表深度扫描（playground L380-450）。
- `FORBIDDEN_KEYS`（L137-158）与 provider `EXECUTION_KEYS`（L117-136）**同一词表**（playground 注释明写由测试锁住 parity）：`act/acted/action/apply/args/archive/authority/authorization/authorize/executor/exec/project/project_id/actor/write_path/book_path/command`。
- body 上限 256 KiB；`MAX_STATE_BYTES=8192` 只约束**发送状态**（`_review` 用 `decision._encode_state` 量字节后判超），book 本身更大是合法的（context 不下发：`context_sent:false` + `context_slots`）。

**B5 实际写入路径（全部在隔离 test 根内）**
- `TEST_ROOT_RELATIVE_PATH = .mw/decide-test`（playground L85）；`_scope` 用 `decision_wire.test_scope(...)`，其 `WireScope._refuse_production_paths`（`decision_wire.py:569-585`）在写入前拒绝解析到 `.agenticdoc/**` 或生产 ledger 的路径。
- 记录：`.mw/decide-test/wire.jsonl`（`test_wire_sink`）、evidence 侧文件（`test_evidence_sink`，均在同根）；提交锁 `.mw/decide-test/submissions.lock`；结果投影 `.mw/decide-test/submission-results/<submit_id>.json`（`RESULTS_DIR_NAME` L168 + `_persist_projection` L1374，原子 `os.replace`，内容整体 redact+clip 后写入，含 `projection_sha256`）。
- monitor 自己的写面仅 `.mw/decide-monitor.json`（身份，无 token）与 `.mw/decide-monitor.secret`（control token，0600 on POSIX）+ start lock；无业务账本、无 archive、无签收文件、无授权文件写入（模块 docstring + `_remove_own_files`/`publish_*`）。
- **不落盘**：请求体原文（`_submission_records` 只保存 provider 解析出的字段与捕获文本）、凭证值、窗口对话。**落盘**：book（`book-snapshot` 事件 + `book_ref`）、每次 attempt 的 request/response（redact+clip）、answer 投影（`answer`/`answer_present`）。列表视图用 `output_omitted` 标记把捕获正文省略（`history()` L1112-1150），详情 `submission()` 才带正文。

**B6 typed 校验与业务执行的边界**
- `decide_for(observation=...)` 是"配对契约"：必须 `intent="answer"` + `archive=False` + 隔离 test scope + 显式 evidence_path，否则参数级拒绝（`_validate_observation`）；它**只绕过 step 2（per-DP enabled/P0 门）**，全局传输开关、凭证、typed 输入门、预算、答案检查、置信门全部照常，executor 永不到达（`decision_points.py:4995-5015` 文档，L5102-5106 实现）。
- 结果语义：`status ∈ {suggested, escalated, acted}`；answer 路径恒 `suggested` + `acted=False`；playground `_classify` 把 `suggested/acted` → 提交态 `succeeded`，`input-incomplete/input-oversize` → `rejected`，`unavailable`+无 call → `unavailable`，其余 `failed`。
- `zero_call` 由 `outcome.call_id is None` 推出（`_finish` 调用点），即"未发生任何模型 HTTP 尝试"；`http_attempts` 来自 `client.last_wire_attempts`。
- 结论：**观察提交不是"业务执行"通道**；它也**不是**"零调用"通道（成功提交会花 1 次模型调用）。这两点必须在 UI 与设计里分列，`state=succeeded` 只表达"回答成功"。

**B7 失败审计的精度（哪些拒绝留痕）**
- **留痕**：`submission-start` 先写（锁内去重），此后一切退出都补 `submission-end`（或 `record-failed`），`issues`/`zero_call`/`book_ref`/`capture_status` 落行；book 被拒也落 `outcome=rejected, zero_call=true`。`_finish` 若 `record_event` 未写成，payload 变 `record-failed` 且消息明说"不是已记录的测试事实"。
- **不留痕**：`_request_refusal`（未知字段/缺字段/`observe_only!=true`/未知 dp/`retry_of` 形态）→ 返回 `state=rejected, zero_call=true, record_status="not-recorded"` 且 **monitor 以 HTTP 200 返回**；`busy` → monitor 转 **409**（附 provider 事实，`nothing queued, no model call`）；duplicate `submit_id` → 返回**原记录**（`duplicate=true`，零新行）；`invalid-retry`/锁超时 → `rejected`/`record-failed`，零行。
- 因此"允许真实安全失败审计"目前只覆盖**已进入 start 之后的失败**；纯请求契约拒绝只有 HTTP 响应，没有 ledger 行（设计若要"安全拒绝审计"独立可核，需新增只读审计位，且仍不得伪造成功裁决）。

**B8 与 RQ20 的三处绝对断言校正**
- (a) "两个 UI 面互不相通" → **部分不成立**。相通处：同一 Python 决策链（`decision_points.decide_for`）、同一 `check_book`/`state_field_issues` 门、同一注册表 id 空间、同一个 page token 权限模型。真正不相通处：传输封套（HTTP JSON vs 工具/CLI）、决策意图与 scope（`observe_only/intent=answer/archive=False/test` vs 生产 act）、以及**两份独立副本**——手写 25 id 枚举（RQ20/`pm/decision-tool.ts:132-158`）与 `/api/dps` 的再投影（本任务 §B2）。设计问题因此是"消除第二份副本 + 单一投影"，不是"架桥连通两个孤岛"。
- (b) "窗口上下文不落盘" → **不成立（观察路径）**。book、捕获的 request/response、answer 投影都落盘于 `.mw/decide-test/`（§B5）。仍然成立的部分：窗口对话、工具返回文本、watch key 不落盘；且这些记录不进 `/api/history`（monitor 未传 `test_roots`，§B3），只能经 `/api/test/history|submissions/*` 读取。故 AC-014 的跨语言段要写成"观察路径有落盘、有独立投影，但没有生产历史投影"。
- (c) "退役后仅 UI 静默放宽校验" → **方向对、形态需改**。Python 侧同样无 retired；更硬的退化是 §结论 4 的四种不一致返回 + cases 整表 503 + `enabled=false` 仍可观察消耗模型调用。即"退役不彻底"的成本主要在服务端可达性与拒绝可读性，而非仅 UI 校验放宽。
- 另修正 RQ20 "`/api/dps` 直出注册表"：见结论 2（是再投影，且 `wired` 恒 false）。RQ20 关于 dashboard.js 的其余事实（`DESIGN_FIELDS`/dp3 分支/`renderSubmissionDetail`/`processing_state=legacy`）本文**未复读源码**，按"RQ20 L0，待复读"引用。

### C. 两个合法技术方案（均可独立于本次授权落地设计）

**方案 A（推荐）：注册表内显式生命周期 + 只读投影，资格只由服务端判定**
- 做法：`DecisionPoint` 增 `status: "active"|"retired"`、`successor: str|None`、`retired_reason: str|None`；`registry_snapshot()` 增只读 `lifecycle{status,successor}`（不新增业务材料字段）；新增 `get_active_decision_point()`（active 集合）与 `get_decision_point()`（含 retired，供历史解释）；`decide_for`/`submit`/`validate`/`scaffold` 对 retired 抛带 `successor` 的专用异常；monitor 四面对应 `400 retired-dp`（`submit`/`validate`/`scaffold`）+ `cases` 默认过滤（`include_retired=1` 只读列表）；生成链只把 active 导出到可调用枚举，retired 另表只做历史解释与拒绝文案。
- pros：①单一事实源（注册表），AC-001/002/003 可用"id 集合 + 状态"机械核对；②AC-013 的"明确退役且不可发起"与 AC-002 的"明确拒绝"共用一份映射，拒绝可区分 retired/typo 并给继任者；③历史字节零改动（只读字段新增，不改旧记录）；④对 RQ20 的 UI 只需删字面分支 + 渲染 `lifecycle`，不需要 UI 判资格。
- cons：①`retired` 行仍留在注册表 → **必须**加一道机械检查"生成的可调用枚举 ∩ retired = ∅"，否则等于把 retired 混进活动枚举（本任务禁止）；②新跨语言契约需要生成链与字节锁（`decide_registry.json` 漂移检查已存在，需扩字段）；③`get_decision_point` 双语义易误用，需命名区分并加调用点审计。

**方案 B：物理删除旧注册 + 独立退役对照表 + 各面兜底拒绝**
- 做法：`DP_REGISTRY` 只留八行；新增 `retired_decision_points.py`（旧 id → 新入口/处置/证据，纯只读常量）；monitor 所有 dp 入口先查该表 → `400 retired-dp` + 继任者；`CASE_IDS` 移除四旧 case 或替换为八新 case；`/api/dps` 天然只有八行。
- pros：①"可调用集合=八"由结构保证，无 retired 混入枚举的风险；②UI 下拉/工具枚举自动收敛，零额外过滤逻辑；③无第二套生命周期状态机。
- cons：①区分"退役 vs 拼错"完全依赖每个 throw 点主动查表，漏一处就退化回 `DecisionInputError`（现状四种不一致返回正是这类漏）；②注册表 + cases + 生成枚举需原子切换，回归面大且不可逆；③历史"退役徽标"仍需表驱动，等于把 A 的表挪到另一文件，但失去"注册行自带状态"的自描述性。

**不推荐**：把 `enabled=false` 或 UI 禁用按钮当作退役（§结论 3：observe_only 绕过该门，仍会真实调用模型）；把 `ui.status` 当资格来源（UI 字段可被篡改，资格必须服务端判定）。

### D. 活动注册精确八名 vs 退役解释（分列，不混入同一枚举）

**活动八名（唯一可调用集合，AC-001）**：`dp-w-type`、`dp-pm-steer`、`dp-w-check-task`、`dp-QG`、`dp-gate-approve`、`dp-sign-key`、`dp-auto`、`dp-route`。
- 六迁移：`dp-w-type`←dp1、`dp-pm-steer`←dp2、`dp-w-check-task`←dp3、`dp-QG`←dp6、`dp-gate-approve`←dp15（并承接 dp20 阶段关闭）、`dp-sign-key`←dp25；两新增：`dp-auto`（承接 dp7 处置）、`dp-route`（路由其余七入口）。

**退役 19 项独立职责（只读解释 + 显式拒绝，不进入活动枚举）**：dp4、dp5、dp7、dp8、dp9、dp10、dp11、dp12、dp13、dp14、dp16、dp17、dp18、dp19、dp20、dp21、dp22、dp23、dp24。
- 纪律：`/api/dps` 的 `points` 可含 retired（带 `lifecycle`），但 `decide_registry.json` 导出的**可调用枚举**与 `ask_decision` dp 枚举只含八名；`retired ∩ 可提交选项 = ∅` 由生成链机械断言；UI 可出现"已退役"徽标，但**不因此禁用/启用任何服务端资格**。

### E. 候选文件/接口（仅定位，未授权修改）

| # | 文件 | 候选改动 |
|---|---|---|
| 1 | `packages/multi-workers/decision_points.py` | `DecisionPoint.status/successor/retired_reason`；`get_active_decision_point()`；`registry_snapshot()` 增只读 `lifecycle`；retired 专用异常（含 successor）；`decide_for` 入口判定 |
| 2 | `packages/multi-workers/decide_registry.json` + `scripts/gen_decide_registry_ts.py` + `shared/decide-registry.generated.ts` | active-only 可调用枚举；retired 另表；漂移检查扩 `lifecycle` |
| 3 | `packages/multi-workers/decision_monitor.py` | `_act_dps` 携带 `lifecycle`；`_act_submit`/`_act_validate`/`_act_scaffold` 统一 `retired-dp`（400）+ successor；`_act_test_cases` 默认 active-only、`include_retired=1` 只读；`_compute_code_fingerprint` 增 payload 指纹（playground 源 + 注册表快照字节 + cases 目录） |
| 4 | `packages/multi-workers/decision_playground.py` | `_request_refusal`/`_review` 区分 `dp-retired` 与未知；`_base_payload` 增只读 `dp_lifecycle`；`scaffold` 前置 active 检查（避免 502 泛错）；`REQUEST_KEYS`/`EXECUTION_KEYS` 词表不动 |
| 5 | `packages/multi-workers/decision_dashboard.js` + `.html` | 渲染 `lifecycle` 徽标/只读；删除 `DESIGN_FIELDS`/dp 字面分支（RQ20 已定位）；禁止据 `ui.status` 判资格 |
| 6 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | `DECIDE_CONCLUSIONS` 读注册表 success 集合（不硬写 continue/narrow/revoke）；`/mw decide sign` 不接受结论位参（现状已正确） |
| 7 | `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` | dp 枚举改为生成（active-only），删除手写 25 条 |
| 8 | `packages/multi-workers/test_decision_dashboard_playground.py` / `test_decision_monitor.py` / `test_decision_points.py` / `test_decide_registry_contract.py` | 下方 F 节断言的隔离测试承载体（faux provider，不触真实凭证/服务） |

### F. 候选断言（正反 / 秘密注入 / 重放 / 字节不变；设计骨架，非通过声明）

| AC | 正向（可机械核） | 反向/失败 | 秘密与注入 | 历史/重放/字节 |
|---|---|---|---|---|
| 001/003 | `registry_snapshot()` 的 active 集合、`decide_registry.json` 可调用枚举、工具 dp 枚举三者 id 集合相等且=八名；`retired ∩ 可提交 = ∅` | 任一处多/少一个 id → 生成漂移检查失败；retired 行缺 successor → 拒绝发布快照 | snapshot/枚举不含任何材料值 | 生成字节稳定（`registry_snapshot_text` 单序列化器）；旧注册行原文不写入历史 |
| 002 | 旧 id 在四提交面统一 `retired-dp` + successor，模型调用 0、业务执行 0、新有效决策 0 | 未注册拼错 → 仍为 `unknown-dp`（两种 code 不能合并）；`/api/test/cases` 不带 dp 不得整表 503 | 拒绝文案只回显 id 与 successor（`_safe_names` 纪律），不回显请求体 | 旧历史行仍可只读；拒绝不产生业务 ledger 行，只产生可选只读审计 |
| 007 | gate 面板四选项 + PM note 与模型理由**两块分列**，来源徽标可区分 | 缺/非法 note、未知选项值 → 阻塞且 0 放行；steer/need_fix 不渲染为已放行 | note/reason 含 `<img onerror>`/`</script>`/`sk-` → 只作文本（`textContent`；monitor `_redact_payload` 二次兜底） | 旧 dp15 记录（continue/narrow/revoke）只作历史解释，不当作目标选项集 |
| 012 | 任一入口不可用/材料非法/无有效裁决 → 具体 code+reason+阻塞徽标（`playground-unavailable`/`playground-redactor-unavailable`/`history-unavailable`/`invalid-field`/`retired-dp`） | 不默认放行、不偷换入口（unavailable ≠ 业务选项）、不造 decision_id（`zero_call`/`record_status=not-recorded` 明示） | 失败文案不含材料/凭证；`internal-error` 只给异常类名 | 一次只读 GET 前后 `.mw/decide-test/*` 与生产 ledger sha256 不变 |
| 013 | 历史列表/详情只读，retired 行显式徽标 + "不可发起新运行" + 原 id | 无 retired 标记 → 断言失败；legacy（无 v2 workbench）与 retired 两标记互不替代（RQ20 `processing_state=legacy` 仍保留） | 历史文本经 redactor；无 redactor 时 fail-closed 省略并计数 | 载入后原始历史文件 sha256 不变；`null`（未记录）与 `[]`（明确无）分开渲染 |
| 014 | producer→writer→consumer→projection 四段在隔离项目可复现：`submission-start/end`(wire) → `submission-results/<id>.json`(projection) → `GET /api/test/submissions/<id>`；字段含 dp/submit_id/decision_id/state/call_id/zero_call | 任一环缺失 → `projection_status=missing`/`record-failed`，不得推断执行；`/api/history?scope=test` 返回空且不伪造 | 三次 redact 腿（known-secret + capture + 最终整文档）后 `sk-`/Bearer 出现次数 0；页面无 `innerHTML`/`eval`（dashboard 侧 RQ20 已核） | `submission_id` 去重（重放同 id → `duplicate=true`，零新行）；投影 sha256 校验失败 → 读回 None，不猜 |
| 038/039 | 仅有效 `finalize` + 对应证据 + logical_id/snapshot 绑定显示为已签收；`continue`/`user-confirm` 显示 0 文件 + "不代表完成" | 换同 key 旧 finalize → 判据不过；`signoff: disable` → 显示跳过原因而非通过 | `finalize` 通道材料含秘密 → 不显示明文 | 历史显示层可解释 finalize（只读），不回写历史；**不把 finalize 接进 `dp apply` 旧 promote/demote/revoke**（`mw.py:2233/3485/3611`、`decide_archive._CHANGE_BY`），不扩其职责 |
| 040/041 | route 面板只列其余七入口 + 依据；固定节点直调无额外路由步骤 | 复合问题未拆 → 拒绝；PM 发起 Worker 专属/Worker 发起 PM 专属 → `role-forbidden`（服务端），执行 0 | 路由依据按文本渲染 | route 选择无 `executed/settled` 业务动作；同事项重放不新增 route 行 |
| 042 | dp-auto 选项 ⊆ PM 已准备候选；未准备方案出现数 0 | 候选为空/不可区分/缺后果 → 阻塞，不默认首候选；`DYNAMIC_CHOICES_MAX=5` 与 dp-route 七目标的冲突单独解决（不得靠 UI） | 候选文本渲染 | 选择不代执行；`attempts` 与 `outcome` 分列 |
| 043 | 八入口各自可观测"非法材料/不可用/缺选择"三种失败，业务动作 0 | 不得默认 approve/首候选；不得把 409 busy 当成功（`accepted:false`）；不得把 HTTP 200 + `record_status=not-recorded` 当已记录测试 | 失败审计只记 code/reason | 原失败保留；真实安全/失败审计可记录，但不伪造成功裁决 |
| 049 | gate 选 steer/need_fix 后 four-state 条：未发起 / 调用失败 / 返回选择 / 实际整改，各有独立事实 | 后继未发起或失败 → 不推断完成；重复请求去重 0；本 gate 因此放行 0 | 后继 reason 文本渲染 | before/after 快照保留来源与时间非递减 |
| 050 | 真实执行的动作证据可与 executed 关联（同 key/task/logical_id，时间非递减） | `consumed`/选择/`settled` 不得当 executed/done；未执行或失败回合不得伪造成功 | 证据文本经 redactor | 不以当前状态回填旧 before；`state=succeeded`（观察回答成功）不得渲染为业务完成 |
| 051/052/053 | dp-sign-key 三数组（verified/unverified/unfinished_impact）`[]`=真实无；`null`=未记录 | 三数组缺项不得改 null 造有效材料；数组非数组 → 材料拒绝 | 秘密明文出现次数 0 | 同事项同证据版本重放 → 不新增审批/不重复动作；实质变化 → 旧批准不放行并留痕；QG pass/fix/reopen 与"后续实际处理"分列，QG 通过不显示为签收/stage 关闭 |

## 残留与未验证

1. 未运行任何测试/CLI/服务/浏览器；全部为读码推断（L0）。未做真实 HTTP 往返、未做真实 DOM、未做前后 sha256 实测。
2. "历史读取不写字节"引用的是 `load_history` 文档与其调用链；未实测一次 `GET /api/history` 前后的文件哈希（本任务禁起服务）。
3. 未读活配置（`.mw/decide.json`、`.mw/decide-points.json`）：因此 `/api/dps` 的 `enabled/mode/config_source` 实际取值、`config.warnings`、以及"当前部署里旧 id 是否已被 enabled=false"均未知。
4. 未读 `mw.py` CLI（`decide monitor`/`decide dp export`/`dp apply` 写面）、`pm/ui-bridge.ts`、`pm/decision-tool.ts`、`decision_dashboard.js/html` 全文；RQ20 的 UI 事实按"未复读"引用，未独立复核。
5. 未读 `decision_points.py` 其余约 5000 行（`_decide_for` 全步骤、policy/预算细节、字段描述全表）；未读 `decision_wire.py`/`decision_history.py`/`decision_book.py`/`decision.py` 全文。`check_book` 的具体校验项集合只按其 issue code 常量与调用点推断，未逐条核。
6. 未核 `decide_cases/*.json` 正文（只核文件名与装载逻辑），故"四 case 是否与目标八入口的材料结构一致"未知；也未核 `decide_cases` 是否随安装包分发一致。
7. 未核部署/安装镜像：`CODE_FINGERPRINT` 不含 playground/注册表/cases（§结论 8），因此"源码存在"不能证明"当前进程加载的身份"；本任务未取任何运行实例的 health 文档。
8. 方案 A/B 的 schema 细节（`status` 枚举命名、`successor` 是否可为多值、retired 是否保留 questions、cases 是否保留四例只读）未冻结；§E 仅是候选位，不构成接口承诺。
9. gate note/理由/后继四态的**精确字段与状态转换**未设计、未授权；本文只给呈现位与断言方向。

## 上下文来源

- 任务书：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq21-design-server-chain/task.md`（卡片 `tasks/RQ21-design-observation-server.md`，`card_sha256: b188901f…`）。
- 目标锚点：`.agenticdoc/goal.md`（Goal/Context）；`.agenticdoc/mw-dp-consolidation/spec.md` §1.1（八目标入口/19 项退出）、§1.2（各入口职责）、§1.5（dp-auto/dp-route）、§3 AC-001～053、§4（未决项与 monitor 8AC 遗留）。
- 全文读主源码：`packages/multi-workers/decision_monitor.py`（2750 行）、`packages/multi-workers/decision_playground.py`（1775 行）。
- 定点读：`decision_points.py:961-972/1039-1094/1506-1512/615-850/5556-5590`、`decision_wire.py:687-706/569-585`、`decision_history.py:203/760-780/3715-3740`、`packages/multi-workers/decide_cases/` 文件清单。
- 同 key 既有取证（仅作校正对象与归属引用，不重复其结论）：`evidence/research/design-ui-submission-chain-20261026.md`（RQ20）、`evidence/research/design-signoff-observation-20261026.md`（RQ17）、`evidence/research/design-entry-contracts-20261026.md`（RQ13）。
- 本文唯一证据文件：`.agenticdoc/mw-dp-consolidation/evidence/research/design-observation-server-20261026.md`（key 内路径 `evidence/research/design-observation-server-20261026.md`）。
- 未读（按任务书禁读）：活配置 `.mw/decide.json`/`.mw/decide-points.json`、任何 gate/ledger/签收/凭证、其他 key 运行材料、图片；未起停服务/浏览器，未跑测试或决策探针。

- 勘误（写入后自核修正）：§A 中 `decision_monitor.py` 的覆盖说明应为"5 次读取至 EOF（1-700、701-1400、1401-2100、2101-2800、2801-2750）"，`decision_playground.py` 为"3 次读取至 EOF（1-650、651-1300、1301-1775）"；原文"分段 700/700/650/全部"与"4 次读取"表述不准，事实（全文读至 EOF）不变。本证据文件为本任务唯一写面，无其他文件改动。
