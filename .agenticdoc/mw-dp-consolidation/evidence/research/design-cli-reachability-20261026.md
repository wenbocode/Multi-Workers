# RQ22 — 完整 CLI 运行入口与退役/签收职责补核（联合设计输入，静态）

> 性质：只读静态阅读 + 代码路径推断。未执行任何 CLI/测试/服务/provider/裁决探针，未读活配置/gate/ledger/签收文件/凭证/其他 key 运行材料。本文不构成设计、实现、AC、QG 或签收结论。
> 阅读面：`packages/multi-workers/mw.py` 全文（分段 read 至实际 EOF，见「证据 1」）；其他模块仅声明范围内引用（见「残留与未验证」）。

## 结论

1. **CLI 只有一个旧 ID 生成源，没有第二个。** 目标态八入口（dp-w-type / dp-pm-steer / dp-w-check-task / dp-QG / dp-gate-approve / dp-sign-key / dp-auto / dp-route）在 `mw.py` 中**尚不存在任何入口**；当前 CLI 全部经 `decision_points.DP_REGISTRY`（25 个旧编号 id）解析，`dp-auto`/`dp-route` 今天被 `decide run` 直接拒绝（unknown dp，exit 2，零模型零写）。
2. **旧 ID 残留分三类，迁移判据必须分开**：(a) 活跃调用面——registry 驱动的 `decide run` / `decide dp show|on|off|set|verify|apply` / `decide book new` / `decide report`；(b) **活跃字面量**——`_decide_report_metrics` 硬编码 `dp3-worker-clarify`（nc 指标）与 `dp1-dispatch-type`（PM-local 未关联指标），以及 argparse epilog 示例里的旧 id；(c) 已退役但可解释的拒绝面——`decide sign` 无 `--stdin` 时显式拒绝旧的计数签收面（exit 2、零写），配套的 `_decide_sign_preview` / `_decide_sign_summary` / `_decide_sign_verdicts` / `_decide_sign_anchor_dp` 已无生产调用者（死代码），但 `--dry-run`/`--allow-empty` 的帮助文本仍在宣称旧行为。
3. **签收面与旧权力变更面今日在结构上是分离的**，而且这种分离是安全属性：`mw decide sign`（dp25 / `dp-sign-key`）只写 `<key>/evidence/review/sign-final.md` + 持久 result 记录 + lifecycle 反馈行；`mw decide dp apply` 只改 `.mw/decide-points.json` 授权表并追加 `authority-change` 审计行（agent session 内显式拒绝、O_CREAT|O_EXCL 锁、P0 集合核验、审计行先写）。`mw.py` 里不存在从 sign 到 `_dp_apply` 的调用边。**为"统一词表"把 finalize 加进 `_DP_SIGN_CONCLUSIONS` 会真的开出漏洞**：`_dp_apply_plan` 只对 `narrow|revoke` 禁止 promote，`finalize` 会落进"自由 promote/demote"分支，而 `_dp_apply_parse` 又会忽略它不认识的行——即一份 sign-final.md 就可能被当成授权变更输入。因此 finalize 词表只能留在签收面。
4. **顺序缺陷（须由设计修，不在本轮改）**：`decide run --stdin` 的旧 id 判定发生在 replay 之后。携带已存在 `logical_id` 的旧 id 请求会先走 `_decide_replayed_payload`（exit 0、`attempts=0`、`replayed=true`），不会得到"明确拒绝"。AC-002 的"零模型零业务"仍成立，但"明确拒绝"不成立；把 registry 解析前移到 replay 之前（或在校验层先拒旧 id）即可两全。
5. **退役不得被"隐式映射"实现**：registry 一旦重命名，`_dp_registry_point`（`mw.py:2269`）与 `decision_points.get_decision_point` 是唯一拒绝漏斗，必须返回"该 id 已退役 + 目标入口名"的显式错误且零写；任何 `if old in (...): dp = new` 形式都是被禁止的别名兼容。
6. 有一批"看起来是有意功能"的旧面（`dp apply` 的 promote/demote/p0-open 路径、`decide dp refresh` 的孤儿行保留、`decide report` 的 nc/unlinked 指标、`decide sign` 旧计数面帮助）。本文只把它们列成**需用户单独批准的删除候选**，未实施、不建议顺手删。

## 证据

### 1. 阅读面与判据（可复核）

- `packages/multi-workers/mw.py`：分段 `read` 自第 1 行连续读至文件实际 EOF（末段为 `__main__` + `dispatch` 映射表，末行为 `sys.exit(dispatch[args.subcommand](args))`）。行数口径：`Get-Content | Measure-Object -Line` 报 11921（非空行计数），read 工具报 13044 总行，末段 `offset=12601, limit=500` 到 EOF，无截断提示。全文覆盖，无未读区段。
- `packages/multi-workers/decision_points.py`：**仅**完整读 540–900（`_point` 工厂 + `DP_REGISTRY` + `_validate_registry` 开头），另用 `Select-String` 取 576–860 的 25 条 `dp_id`。其余函数实现未读。
- `packages/multi-workers/decide_signoff.py`：仅 grep 符号行（`CONCLUSIONS`、`TRUE_ENGINE`、`AGENT_SESSION_ENV_VARS`、`render`/`verdict`/`write_signoff`/`collect`/`signoff_path` 定义行），未读实现。
- `packages/multi-workers/decision_signoff_result.py`：仅完整读 620–740（`validate_signoff`），另 grep `DP_ID` / `CONCLUSIONS` / `SIGNOFF_RELATIVE_PATH` / 结果读写函数签名。
- 旧研究（RQ13/17/20/21 等）未读，避免重复与污染；本文不引用它们的结论。
- 判据：只把"在本文件中可静态定点的行为"写成证据；跨文件调用链、安装内存身份、TS 侧消费者一律标未覆盖（「残留」节）。

### 2. CLI parser → dispatch 实际入口

`_parse_args` 的 subparser 集合与 `__main__` 的 `dispatch` 字典**一一对应**（多一个少一个都会 KeyError），共 24 个用户面 subcommand：

`serve / start / stop / status / stats / review-split / doctor / decide / dispatch / target / partition / model / autopilot / init / pull-agentictask / push-agentictask / setup / build / bootstrap / update-env / ue-toolchain / worktree / rag / run-detached`

另有两个**隐藏入口**（不进 argparse、不进 `--help`），只在 `__main__` 里按 `sys.argv[1]` 字符串分派：

- `_run_supervisor` → `console_run.run_supervisor_entry`
- `_decide_monitor_starter` → `_monitor_starter_entry`（`--project`，服务化 monitor）

二级/三级动作（`*_action` dest）：

| 面 | 动作 | 备注 |
|---|---|---|
| `decide` | `run / lifecycle / probe / show / set / ask / book / report / sign / dp / monitor` | `cmd_decide` 显式分派；未知动作 exit 2 |
| `decide dp` | `list / show / on / off / set / refresh / check / export / verify / apply` | `_decide_dp` handlers 字典；未知动作 exit 2 |
| `decide book` | `new / check` | `_decide_book` |
| `decide monitor` | `open`(默认) `status / stop` | `_MONITOR_ACTIONS`；根解析 fail-closed |
| `autopilot` | `gates / answer / contract-guard / contract-freeze / verify(set|show|clear)` | `answer` 是 gate 答复，**不是** decision 回执 |
| `rag` | `init / list / probe / audit / sync` | `_RAG_ACTIONS` 字典 |
| `dispatch` | `check` | 子 parser **未** `required=True`，裸 `mw dispatch` 走 action=None 分支 → stderr + exit 1 |
| `target`/`partition`/`model`/`worktree`/`ue-toolchain`/`stats`/`review-split` | 各自动作 | 与 DP 面无关；`model` 的 `set-fallback`/`clear-fallback` 用 `role` 位置参数名装 task type |

任务描述里点名的 `case / answer / receipt / auto` 在 `mw.py` 中的实际落点：

- `case`：**本文件无此入口**（属 UI/提交面，未覆盖）。
- `answer`：只有 `mw autopilot answer`（写 gate 答复，`--confirm-destructive` 才允许 reject），与决策回执无关。
- `receipt`：没有同名命令。回执语义分散在 `mw decide lifecycle --stdin`（stage = `consumed|executed|settled|signoff`，`decision_lifecycle` 唯一写面）与 `_book_receipt`（book 回执行，best-effort，失败只提示）。
- `auto`：没有 `dp-auto` 命令。`auto` 在本文件只以三种形式出现：`decision_points.MODES` 的 mode 值、`mw decide sign --auto`（把 `signoff=auto` 持久化进 `.mw/decide.json`，不签收）、`DecisionPoint.default_mode`。

### 3. 旧 ID 落点清单（分类）

以下为 `mw.py` 内全部 `dpN-...` 形状命中（`Select-String 'dp[0-9]{1,2}-[a-z-]+'`，共 26 行），逐条分类：

| 位置 | 内容 | 分类 |
|---|---|---|
| 3036–3153 | `# dpN-…: contract probe facts` 注释块（`_DP_VERIFY_STATE_VALUES` 内） | 注释；键是 state path（如 `qg.blocking`），**不是** dp id |
| 3829 | `if dp_id == "dp3-worker-clarify": nc_raw += 1 …` | **活跃字面量**：`decide report` 的 nc 指标 |
| 3833 | `dp_id == "dp1-dispatch-type"` → PM-local `unlinked` 行 | **活跃字面量**：report 的无法关联登记 |
| 12663–12664 | `decide lifecycle` epilog 示例 `dp3-worker-clarify:<id>` | 帮助文本 |
| 12752 | `decide book new dp3-worker-clarify --out …` epilog 示例 | 帮助文本 |
| 2269 `_dp_registry_point` | `get_decision_point(dp_id)` → `(None, str(exc))` | **唯一拒绝漏斗**（dp show/on/off/set/verify/apply 共用） |
| `_dp_apply_parse` | promote/demote/p0-open 每个 id 过 `_dp_registry_point` | 活跃旧 id 接受面（授权表变更） |
| `_dp_verify` | `--dp` 过滤：`unknown` → exit 2 | 活跃旧 id 接受面（只读探针） |
| `_dp_export` / `_dp_export_wiring` | 只遍历 `DP_REGISTRY`，`wiring` 按 id 取；**旧 id 的 wiring 条目会被静默丢弃** | 生成接口迁移点（无告警） |
| `_dp_refresh` | `registered` 集合来自 registry；旧行变 `orphaned` 并**保留** | 历史兼容（有意功能） |
| `_dp_list` | registry 顺序 + `orphaned_ids()` | 只读 |
| `_decide_report_metrics`/`_decide_sign_anchor_dp` | `decision_points.DP_REGISTRY[0].id` 兜底（`_dp_apply_rows` 亦然） | registry 首位=隐式默认 |
| `_decide_resolve_dp_questions` | legacy 请求（自带 `questions`）默认 label **`"dp1"`**，且**不做 registry 查找** | 旧 label 可进证据行（非 registry id） |
| 1597 `_ASK_DP = "dp-human-ask"`（用于 2158 `client.decide(..., dp=_ASK_DP)`） | 人面标签，非 registry id，走**未授权** legacy 路径 | 需在设计里显式分类 |
| `_dp_verify_state` | 以 `point["required_state_fields"]` 驱动；缺探针值时 `ValueError` → 该行 `unusable config` | 新入口必须补探针值 |

由此得出的旧 id 枚举/默认/帮助/探针事实：

- **枚举**：唯一枚举源 = `decision_points.DP_REGISTRY`（`decision_points.py:574`，25 条，id 已冻结字面量）。CLI 侧没有任何第二份白名单（`dp choices` 未硬编码）。
- **默认**：三处隐式默认——legacy 请求 label `"dp1"`；`DP_REGISTRY[0]` 作 `dp apply`/`_decide_sign_anchor_dp` 的兜底锚；`decide run` 位置参数 `dp_id` 与 `--dp` 允许只给一处（两处冲突才拒绝）。
- **帮助**：`decide sign` 的 epilog 仍在展示旧 `--dry-run` "verdicts only" 与旧计数面；`decide book`/`decide lifecycle` 的示例用旧 id；`--allow-empty` 帮助说 "conclusion=continue with N=0"（该参数在活路径中**未被读取**）。
- **探针**：`dp verify` 的每 dp 契约探针从 `decide_registry.json`（`_DP_EXPORT_NAME`，包内路径，不看 `--project`）取点，`--live` 走真实端点；旧 id 现在既是可探针集合，又是 `--dp` 过滤键。

### 4. 请求 ↔ 执行器边界；本文件内的生产 caller

- **决策面**：`decide_for`（`decision_points`）是唯一授权/预算/传输/答案校验入口。`mw.py` 只构造 `Trigger`（`from_mapping`，key/task_key/trigger_id）与 `DecisionClient`，从不直接调用 backend。
- **执行器面**：`DecisionPoint.executor` 由 `decision_points` 持有；`mw.py` **从不读取** `.executor`。registry 中 dp25 用 `_echo_conclusion_executor`（只回显结论），dp1/2/3/5/7/9/21/22/23 用 `_unwired_executor`，其余为 `None`。→ CLI 的"执行"只有两处真实写入：签收文件（`_decide_sign_finish`）与授权表（`_dp_apply`）。
- 本文件内 `mw.py` 对 `decide_for` 的生产 caller（全部）：`_decide_run_versioned`、`_decide_run`（structured 分支）、`_decide_sign_finalize`。`decide ask` 与人面 legacy 请求走 `DecisionClient.decide`（**不**过 registry/授权）。
- 本文件内对 `_dp_apply` 的 caller 只有 `_decide_dp` 的 `apply` handler（argparse 唯一入口）；对 `_dp_write_raw` 的 caller：`_dp_set_enabled`、`_dp_set`、`_dp_refresh`、`_dp_apply`（`lock=False`）。无隐藏内部调用。
- `cmd_dispatch.check` 转 `autopilot/dispatch.py:check_command`（卡/dp/book 发送权威检查）——本文件只看到 argv 转发，`dispatch.py` 内部未读。

### 5. 签收：同次判断 → result/file → 反馈

现状（静态轨迹，`_decide_sign` / `_decide_sign_finalize` / `_decide_sign_finish`）：

1. `_decide_sign_key`：`--key` 或 `<key>` 位置参数优先；否则仅当 `--project` 目录直接位于 `.agenticdoc` 下时取目录名；其余拒绝（exit 2）。
2. 门（按序）：`cfg.signoff_error` → `signoff=disable`（exit 0、零写）→ `credential_snapshot` + `known_secret_redactor` → `decide_signoff.collect`（读 archive、算 `sha256` 与 `chain_ok`）→ `assert_safe_target`（符号链接/越界拒绝）→ lifecycle store 可用性 → `--stdin`/`--retry-write` 必居其一。
3. `--retry-write <logical_id>`：读持久 result；`record.key != key` 拒绝；`record.rows_sha256 != facts.sha256` 拒绝（"archive evidence changed … issue a new judgment"）。若同时给 `--stdin`，还要求 envelope 的 `logical_id` 相同、`digest_material(material)` 的 digest/evidence 与记录一致；否则**只**核 archive hash（material 无法复核——这是精度差异，须在设计里明说）。`model_called=False`。
4. 首次判断：envelope（严格 `{material, meta}`，未知键拒绝）→ registry 取 `decision_signoff_result.DP_ID` 并二次确认 `point.id == DP_ID` → `record_start`（`decision_id=f"{point.id}:{logical_id}"`，duplicate/未 recorded → 拒绝，零模型）→ `decide_for(intent="answer")`（配置/材料/全局预算/传输/答案校验都在里面）→ 只接受 `status in (acted, suggested)` 且有 answer → `q-conclusion` 值必须 ∈ `decision_signoff_result.CONCLUSIONS`（`finalize|continue|user-confirm`）→ 传输/模型 provenance 必须可核（`transport=="none"` 或缺 model → 拒绝）→ `build_result` + `write_result`（`record_version=2`、snapshot/material/evidence/rows 四哈希；写失败只记 `record_status=failed:…`，不改判定）。
5. `_decide_sign_finish`：`finalize` → `validate_signoff`（先看已有文件；同 logical_id 但内容不匹配 → `invalid-existing` exit 2，不覆盖）→ 否则 `decide_signoff.render(...)` + `write_signoff`（原子）→ 反馈两行 `consumed`（answer=conclusion）+ `signoff`（`evidence_path="evidence/review/sign-final.md"`、`evidence_sha256=文件哈希`、`snapshot_sha256`）→ 输出 `signoff_status=written|existing`、`second_approval=0`。
6. 非 finalize（`continue`/`user-confirm`）→ `signoff_status="not-required"`、`handoff={owner:pm, kind, signoff_writes:0, instruction}`、反馈一行 `executed`（`action=conclusion`、`result="pm-handoff"`）；**零签收文件写**。

当前"有效 finalize"的判据全集（`decision_signoff_result.validate_signoff`，620–740 已读）：文件存在且路径每个既有组件非符号链接、留在 key 目录内；含 `logical_id`（否则 `legacy-no-logical-id`）；`record_version=2`；`dp == dp25-signoff-conclusion`；`conclusion ∈ {finalize, continue, user-confirm}`；四个 sha 行格式合法；`snapshot_sha256` 必须等于按 `key+dp+material+evidence+rows` 重算的值；可选 `expected_logical_id`/`expected_snapshot` 精确匹配；若存在同 logical_id 的 result 记录，必须 logical_id/snapshot/material 一致。→ **"finalize 词表"的唯一权威在 `decision_signoff_result`，不在 `decide_signoff.CONCLUSIONS`**（后者仍是旧的 `("continue","narrow","revoke")`，供 `_dp_apply_parse` 与 `decide_signoff.verdict` 使用）。

关联与实质变化（design 要点）：

- 关联键是 `logical_id`（同一 id 只判一次；`decision_id = dp:<logical_id>`），archive 以 `rows_sha256` 绑定，材料以 `material_sha256`/`evidence_sha256` 绑定，合成为 `snapshot_sha256`。
- 任一哈希变化（archive 行、材料、证据）都会拒绝复用并强制"issue a new judgment"；这正是 AC-039/AC-052 的"受影响旧签收不复用"机制。
- **重放语义**：`decide sign` 的重复 `logical_id` 不会重调模型；若已有 result 且哈希一致，则只重做写面（`record_status=existing`、`model_called=False`）——即 `--retry-write` 的合法用途。

### 6. `dp apply` / promote / demote / authority-change 与签收目标的职责区别

| 维度 | `mw decide dp apply <sign-file>` | `mw decide sign <key> --stdin` |
|---|---|---|
| 判断对象 | 授权表（哪些 dp 开/关） | 本 key 交付是否可收尾 |
| 结论词表 | `_DP_SIGN_CONCLUSIONS = ("continue","narrow","revoke")` | `("finalize","continue","user-confirm")` |
| 输入语法 | 只认 `^(conclusion|promote|demote|p0-open):` 整行；其余行**静默忽略** | 严格 `{material, meta}` JSON envelope，未知键拒绝 |
| 主产物 | `.mw/decide-points.json`（原子替换）+ `authority-change` 审计行 | `<key>/evidence/review/sign-final.md` + result 记录 |
| 安全门 | agent session 环境变量命中即拒绝（人工面）；O_CREAT\|O_EXCL 锁内重读+复查 P0 集合；审计行 `strict=True` 先写、失败即中止 | 由 PM 调用；config/signoff mode/凭据快照/chain_ok/路径安全/材料严格性/预算/准入 |
| 权限含义 | 变更"未来可自动决策的范围" | 断言"本 key 交付已满足目标与验收" |
| 失败形态 | exit 2 + "nothing was written"（唯一例外：审计行已写但表写失败，明确告知） | exit 2 + `signoff_status=failed` / `not-recorded` / 零写；或 `invalid-existing` 不覆盖 |

**不能合并的决定性理由（静态可证）**：

- `_dp_apply_plan` 只在 `conclusion in ("narrow","revoke")` 时禁止 `promote`；`finalize` 若进入该词表，会直接落进允许 promote/demote 的分支。
- `_dp_apply_parse` 对不匹配行"静默忽略"，因此 sign-final.md 的正文/机器行不会阻止解析——唯一的拦截就是 `conclusion` 词表与 `p0-open` 校验。合并词表＝移除该拦截。
- `dp apply` 在 agent session 内**必须拒绝**（人工面）；`decide sign` **必须**能被 PM agent 调用。合并会把二者变成一个既需人又要机器调用的矛盾体。
- 二者写不同对象：授权表 vs 签收证据；把 finalize 接到 `_dp_apply` 会用"交付完成"去改"未来授权"，属权限放大。

### 7. 至少两种合法适配方案（词表 + 可达性）

**方案 A（推荐）—"边界对象 + 显式拒绝"，词表不合并**

- `decision_signoff_result` 保持 `DP_ID` + `CONCLUSIONS` 为 finalize 唯一权威；`_DP_SIGN_CONCLUSIONS` 保持三词，只服务授权变更面。
- `_dp_apply_parse` 增加**产物类型拒绝**：若文件含签收机器行（`record_version:` / `material_sha256:` / `rows_sha256:` / `snapshot_sha256:`）或未知 `dp:` 行，直接 exit 2 + 明确文案"这是 key 签收文件，不是授权变更签收；用 `mw decide sign`/`decide report`"。判据基于内容，不基于路径或词表。
- 旧 id 拒绝集中在 `_dp_registry_point` 与 `get_decision_point`，消息点名目标入口，零写。
- Pros：改动最小、两侧安全属性都保留、无历史文件迁移；测试可断言"两份产物互不喂养"。Cons：两套词表共存（需在帮助/文档里显式分成两张表），读者需知道自己在看哪种文件。
- 风险：`continue` 两套都有，靠"产物类型"而非词值区分，必须写清楚。

**方案 B —"带类型头的单一产物族"**

- 在 sign-off/授权变更两类 markdown 都加 `artifact: key-signoff | authority-change`（或复用 `record_version` 命名空间），`decide sign` 与 `dp apply` 各自校验自己的类型；`finalize` 仍只在签收侧。
- Pros：检测无歧义，未来加第三类产物成本低；`validate_signoff` 已经用 `record_version` 做同类事。Cons：要改 render/写入面与校验面（含"旧文件无类型头"的只读接受规则），触及历史文件读取语义；实现面更大，容易滑向"旧运行兼容"。

**方案 C（不建议，需用户单独批准）—"退役 `dp apply` 的 promote/demote"**

- 直接移除授权变更执行器，只保留人工 `dp on/off/set --i-understand-p0`。
- Pros：消灭词表混淆来源。Cons：删除一个带审计历史、P0 确认、锁与 TOCTOU 保护的有意功能；属能力收缩，超出本 key 授权，必须由用户单独批准，且不能以"统一词表"为理由。

推荐：**方案 A**；B 作为后续可在不删功能前提下叠加的类型化改进；C 只登记，不执行。

### 8. 候选精确接口（文件 / 函数 / 帮助 / 生成物）

| # | 位置 | 候选改动 | 约束 |
|---|---|---|---|
| C1 | `packages/multi-workers/decision_points.py:574 DP_REGISTRY` | 25 → 8 目标 id；`_validate_registry` 保持唯一性/类型校验 | 需同批改 `build_state`、`required_state_fields`、`questions_version` |
| C2 | `decision_points.py` 新增只读 `RETIRED_DP_IDS`（仅用于拒绝文案与历史读取分类） | 拒绝消息用，**不得**作为可调用别名或隐式映射表 | AC-001/AC-002：别名数恒为 0 |
| C3 | `mw.py:2269 _dp_registry_point` | 唯一拒绝漏斗；旧 id → exit 2、零写、点名目标入口 | dp show/on/off/set/verify/apply 全部共用 |
| C4 | `mw.py _decide_run_versioned` / `_decide_resolve_dp_questions` | registry 解析前移到 replay 之前；legacy `questions` 分支的 `"dp1"` 默认要么移除、要么降级为"非 DP id 的记录列" | 顺序改动不得引入模型调用 |
| C5 | `mw.py _decide_report_metrics`（3829/3833） | 旧 id 字面量 → 迁移常量；或删除该指标并显式记录"已退役" | 静默归零是当前最坏失败形态 |
| C6 | `mw.py _dp_export` / `_dp_export_wiring` + `packages/multi-workers/decide_registry.json` | 重新生成；对"文件里有、registry 里没有"的 wiring id 输出 orphan 告警（对齐 `_dp_refresh` 的 orphaned 语义） | 手维 `wiring` 段必须保留 |
| C7 | `mw.py _dp_verify` + `_DP_VERIFY_STATE_VALUES` | 新入口补齐 `required_state_fields` 的探针值；旧 id 过滤 → exit 2 | 缺值现状是 `unusable config` 失败行 |
| C8 | `mw.py _DP_SIGN_CONCLUSIONS` / `_dp_apply_parse` / `_dp_apply_plan` | 保持三词；加产物类型拒绝（方案 A） | 禁止把 `finalize` 加进该集合 |
| C9 | `mw.py _decide_sign_*` + `decision_signoff_result.DP_ID/CONCLUSIONS/validate_signoff` | `DP_ID` 与 `decision_id` 前缀一次性重命名；`CONCLUSIONS` 保持 `finalize|continue|user-confirm` | 五处必须同批：registry id、`DP_ID`、`decision_id` 前缀、签收文件 `dp:` 行、`validate_signoff` 断言 |
| C10 | `mw.py _decide_lifecycle` | （设计决策）是否对 `payload["dp"]` 加 registry 校验 | 现状为自由字符串；加校验会影响历史/人工回填 |
| C11 | `mw.py _ASK_DP = "dp-human-ask"` | 显式登记为"非 registry 人面标签"，在 AC-001 盘点中单列 | 不计入"可调用 DP 集合" |
| C12 | argparse epilog/help：`decide sign`（12663 附近 `--dry-run`/`--allow-empty` 文案）、`decide book`（12752）、`decide lifecycle`（`dp3-worker-clarify` 示例） | 修示例 id；删除/实现 `--dry-run` 的旧承诺（当前不可达）；`--allow-empty` 要么接回活路径要么去掉 | 帮助不得宣称主入口会拒绝的行为 |
| C13 | 死代码：`_decide_sign_preview`、`_decide_sign_summary`、`_decide_sign_verdicts`、`_decide_sign_anchor_dp`（各仅定义+死链） | 删除或接回（需用户决定，见 §10） | 删除前确认无外部 import（本文件外未审） |
| C14 | `cmd_dispatch` → `autopilot/dispatch.py:check_command` | 旧 id 在卡/本检查里也应拒绝；`--dp` 覆盖只做 registry 探针 | `dispatch.py` 未读，属未验证 |
| C15 | 新入口 `dp-auto` / `dp-route` | 建议**不新增 subcommand**：沿用 `decide run --dp <id> --stdin`（registry 驱动、已有授权/预算/失败语义）；材料承载候选/目标入口 | 需在 registry 里定义 `required_state_fields` 与探针值（C7） |

### 9. AC 断言（正 / 反 / 非法旧 ID 零模型零业务 / 关联重放 / 失败审计）

> 全部为**静态可构造**断言草案（design 输入），未执行。

- **AC-001**：正：`decide dp export --json` 的 `points[].id` 集合精确等于 8 个目标 id；反：registry 与 `--help` 输出中 `^dp[0-9]+-` 形状 id 计数为 0（历史只读文案除外的白名单需登记）。现状反例已存在：3829/3833 两处字面量 + 两处 epilog。
- **AC-002**：正（迁移后）：任一旧 id 经 `decide run`（stdin/`--book`/位置参数）→ exit 2、无 `record-start`、无 archive 行、无 `decide_for` 调用（0 模型）、无业务写。反：**当前缺陷**——`--stdin` + 已存在 `logical_id` 会先 replay（exit 0、`attempts=0`、`replayed=true`），不返回明确拒绝；断言应写成"拒绝且 0 模型 0 业务"，故 C4 前移解析是前置条件。非法：旧 id 出现在 `--book` 的 `decision_point` → `_book_gate` 只做格式/预算/密钥检查，`_decide_resolve_dp_questions` 在构造 client 前退出 → 零 HTTP、零 book 回执。
- **AC-003**：正：旧 id 活跃调用面计数 0、字面量计数 0（C5/C12 完成）；反：`_dp_refresh` 的 orphan 保留、历史 archive 只读、拒绝文案中的旧 id 均需标注用途（三类分开统计）。断言要求"逐类计数"，不接受一个总数。
- **AC-004**：正：dp-sign-key 合法材料 → `conclusion` ∈ {finalize,continue,user-confirm}；`finalize` 写恰好 1 个签收文件 + 1 条 result + consumed/signoff 反馈；`continue`/`user-confirm` → `signoff_writes:0`、`signoff_status=not-required`、1 条 `executed`(`result=pm-handoff`)。反：`conclusion=narrow|revoke`（旧词）→ exit 2、零写；`--allow-empty` 现状被忽略 → 断言应写"参数若保留必须落到判定，否则移除"。
- **AC-009**：正（迁移后）：相位门失败材料走 dp-auto，选择结果不改写门禁判据；反：现状 dp-auto 未注册 → `decide run --dp dp-auto` exit 2、0 模型（即 AC-009 目前不可满足，是**待建设**而非已实现）。非法：旧 `dp7-gate-failure` → 拒绝且不产生 gate 推进。
- **AC-012**：正：每入口在 `available=false` 时 `acted=false`、`reason ∈ REASON_CODES`、受门控动作零副作用；`decide sign` → exit 2 + `signoff_status=failed` + `feedback_status=not-recorded` + `signoff_path=null`。反：不得出现"服务不可用→默认 approve/finalize"的分支（静态：`_decide_sign_finalize` 明确要求 status∈(acted,suggested) 且 answer 非空）。审计：失败可记录（`_decide_print` 输出 `problems`/`record_status`），但不得伪造有效裁决。
- **AC-013**：正：含旧 id 的历史行在 `decide report`（fold，只读）可见；`dp show` 旧 id 明确"退役，只读"且不发起运行。反：原始 archive 字节在读取前后 sha 不变；`_dp_refresh` 不得删除 orphan 行。断言需在**不新增旧 id 可调用别名**前提下满足。
- **AC-014**：正：sign 输出键集（`dp/key/logical_id/decision_id/conclusion/signoff_status/feedback_status/signoff_path/snapshot_sha256/count_approval=second_approval`）与 lifecycle 键集（`stage/status/recorded/error_class/event_id/duplicate/logical_id/decision_id`）可被 consumer 逐一对应；反：`_decide_lifecycle` 对未知字段直接拒绝且**不回显**（现状：`unknown` 计数后 exit 2，不打印值）；签收 payload 不含材料正文。注入/秘密：`_decide_redact_secrets` 只用于 `decide set --json`；签收面用 `known_secret_redactor` 做 capture 过滤。
- **AC-038**：正：仅 `finalize` + 有效文件 ⇒ 签收成立；`continue`/`user-confirm`/文件存在/QG pass 任一单独出现 ⇒ 不成立。断言点：`signoff_status` 只在 finalize 分支取 `written|existing`；`second_approval` 恒 0（无第二次 PM 批准字段）。
- **AC-039**：正：`validate_signoff` 拒绝 `dp != DP_ID`、`record_version != 2`、`conclusion ∉ 闭集`、snapshot 重算不符、`logical_id` 缺失（legacy 文件 → `legacy-no-logical-id`）。反：`--retry-write` 在 `rows_sha256` 或 material digest 变化时拒绝且**不覆盖**已有文件；`signoff=disable` 时零写。重命名断言：`DP_ID`、`decision_id` 前缀、文件 `dp:` 行、校验断言四处同批通过/同批失败。
- **AC-040**：正（迁移后）：dp-route 的选择值 ∈ 其余 7 个目标 id（不含自身），选择与依据可见；同一命令内不产生目标 dp 的额外模型调用（0）。反：路由答复被当作业务结论（不得出现"route→执行"边）。非法：只有事件名/无主体/无具体问题 → 拒绝。
- **AC-041**：正：固定节点直调 dev 无额外路由（`decide run --dp <fixed>` 不触发 dp-route）；复合问题拆成多次独立 `logical_id`。反：PM 调 dp-w-check-task / Worker 调 dp-pm-steer 属角色越权（现行 CLI 无角色参数 → 越权目前只能靠调用方约定，属**待设计缺口**）。
- **AC-042**：正（迁移后）：dp-auto 的 answer 值 ∈ material 提供的候选 id 集合；未准备方案出现数 0；选择不产生执行写。断言点：候选集合必须来自 material（对齐 dp3 现有 `dynamic_choices: handling_options` 机制），而非 registry 固定 choices。
- **AC-043**：正：非法/缺失材料在 `decide_for` 之前的严格解析处拒绝（sign：`_decide_envelope` 先于 `record_start`；run`--stdin`：envelope → store → registry 查找 → 才 `record_start`）；服务不可用 → 阻塞且零副作用。反：不得默认首候选/approve；不得造 `decision_id`。审计：`feedback_error_class/error_recorded` 如实反映"记录失败"，不升格为成功。
- **AC-049**：正：gate 选 steer/need_fix 后，PM 侧另起 dp-pm-steer/dp-auto 请求，拥有**自己的** `logical_id`/`decision_id`，且 gate 的选择不产生后代 `executed` 行。反：同事项重复后代请求 → 同 `logical_id` 被 replay（`attempts=0`、`record_start=duplicate`），不重复模型调用。
- **AC-050**：正：`executed`/`settled` 的 `task_after` 与 `task_before` 是两个独立来源字段；`task_after` 要求 `task_key` 非空且 stage ∈ {executed, settled}（现状已强制，`_decide_lifecycle` 明确拒绝违规组合）。反：`settled` 不得被投影成任务 done（`decide report` 的 outcome 与任务状态无耦合）；仅 consumed/选择不得写 executed。
- **AC-051**：正：`task_after` 的 `completed/remaining/blockers` 允许 null 且与 `[]` 可区分（输出原样透传）。反：dp-sign-key 的 `verification_evidence.verified/unverified`、`unfinished_impact` 必须是数组，null 不得被当作"无"；`[]` 才表示真实无。**未验证项**：Python 侧对这些路径的类型强制在 `decision_points` 的 state 校验里，本文件未读该实现（仅从工具材料 schema 观察到数组约束）。
- **AC-052**：正：同 `logical_id` 重放 → 零模型、`replayed=true`、`available=bool(linked)`；并发同 id → `start.duplicate` 走同一 replay 分支。反：`_decide_write_config`/`_dp_write_raw`/`_dp_apply` 必须持 `<path>.lock`（O_CREAT|O_EXCL），`_dp_apply` 单临界区内完成"重读→P0 复查→审计行→表写"；实质哈希变化 → 拒绝复用旧签收。纯排版变化不应触发重判（静态无法验证：无内容归一化逻辑，属**未验证**）。

### 10. 看似有意、删除须用户单独批准的功能（仅登记）

1. `mw decide dp apply` 的 promote/demote/p0-open 授权变更路径（含 `authority-change` 审计与 agent-session 拒绝）。
2. `mw decide dp refresh` 的"孤儿行保留、不删除"语义。
3. `mw decide report` 的 nc_raw/nc_human 与"无法关联"登记（旧 id 字面量正是其实现）。
4. `mw decide sign` 的 `signoff=disable` 逃生门与 `--auto/--disable` 模式持久化。
5. `decide_signoff.CONCLUSIONS` 旧三词集合（仍被 `dp apply`/`verdict` 使用，**不能**与签收词表合并删除）。
6. 死代码 `_decide_sign_preview`/`_decide_sign_summary`/`_decide_sign_verdicts`/`_decide_sign_anchor_dp`——删除属清理，但会移除"`--dry-run` 只判不写"的潜在实现，需用户确认是"实现它"还是"删掉承诺"。
7. `decide ask` 的人面未授权路径与 `dp-human-ask` 标签（关掉等于取消人面直问）。

原安全/角色/claim/锁/预算/凭证防护在这些退役或删除讨论中**不随之消失**：agent-session 拒绝、P0 二次确认、`O_CREAT|O_EXCL` 锁、credentials snapshot/redactor、chain_ok、路径安全、预算/状态门均保持。

## 残留与未验证

- **全部为静态推断**：未执行任何 CLI、未跑测试/build/install/commit，未启停服务，未调用 provider 或裁决探针，未读活 `.mw/decide.json`、`.mw/decide-points.json`、ledger、签收文件或凭证。所有"exit 2/零写/零模型"都是代码路径推断，不是实测。
- **源码 ≠ 安装内存身份**：仓库源码可能是脏树或被其他会话改动；运行中的 `mw serve`/pi bundle 实际执行的代码未核（`serve.meta`/`code_digest` 未读）。本文不代表安装态能力。
- **非全仓 caller 审计**：只核了 `mw.py` 内部调用链。TS 侧（`agent-team-loop` 工具、`ask_decision`/`decision_receipt` 工具映射的固定 dp 枚举、done gate 对 `sign-final.md` 的强制、autopilot console、monitor UI 提交面）与其他 Python 模块（`decision.py`、`decision_lifecycle.py`、`decision_book.py`、`autopilot/dispatch.py` 等）的旧 id caller **未审计**，属未覆盖线索。
- **部分读模块**：`decision_points.py` 仅 540–900 完整；`decide_signoff.py`/`decision_signoff_result.py` 仅符号与 `validate_signoff` 段。故 `record_start/record_executed/record_settled/record_signoff` 的字段级校验、`check_book` 的密钥/预算门、`decide_for` 的 policy/budget 细节、state 路径类型强制（AC-051）均未逐行核。
- **具体未验证断言**：AC-051 的数组类型强制；AC-014 的 monitor/UI 投影链；AC-041 的角色资格（CLI 无角色参数）；AC-052 的"纯排版不重判"（无归一化代码可证）；`dispatch.check` 对旧 id 的行为。
- **设计未决（需用户/PM 决定，不在本轮）**：`dp-human-ask` 是否计入"可调用 DP 集合"；`_decide_lifecycle` 的 `dp` 是否加 registry 校验（历史回填风险）；`--allow-empty`/`--dry-run` 是"实现"还是"删除承诺"；死代码清理与 §10 各项删除候选；dp-auto/dp-route 是复用 `decide run --dp` 还是新增 subcommand（本文推荐前者）。
- 本文不含任何 VERIFY、测试通过、设计批准、AC 关闭、QG 结论或签收成功声明。

## 上下文来源

- `.agenticdoc/goal.md:5`（project goal 段；本 key 对齐与 GC-1…GC-6 约束）。
- `.agenticdoc/mw-dp-consolidation/spec.md`：§0 Goal Alignment、§1.1（八入口与 19 项退出、旧编号不作为可调用别名）、§1.2（dp-sign-key/dp-w-check-task/dp-gate-approve/dp-auto/route 合同）、§2 业务约束（历史只读、硬门不消失、材料缺失即阻塞）、§3 AC-001～004/009/012～014/038～043/049～052、§4 风险与未决。
- 本卡 `.agenticdoc/mw-dp-consolidation/tasks/RQ22-design-cli-reachability.md`（要求 1–5 与交付格式）。
- 源码（唯一主要源）：`packages/multi-workers/mw.py` 全文（read 至 EOF）。
- 辅助定点（已声明部分读）：`packages/multi-workers/decision_points.py:540-900` + 576/595/615/629/637/650/658/671/707/716/724/733/742/755/768/777/786/794/802/811/820/829/842/851/860；`packages/multi-workers/decide_signoff.py`（`CONCLUSIONS:83`、`TRUE_ENGINE:85`、`AGENT_SESSION_ENV_VARS:91`、`signoff_path:162`、`collect:289`、`verdict:452`、`render:516`、`write_signoff:698`）；`packages/multi-workers/decision_signoff_result.py`（`DP_ID:69`、`CONCLUSIONS:71`、`SIGNOFF_RELATIVE_PATH:75`、`digest_material:136`、`assert_safe_target:241`、`signoff_path:314`、`build_result:384`、`write_result:475`、`read_result:561`、`validate_signoff:632-740`）。
- 未使用来源：RQ13/RQ17/RQ20/RQ21 等旧研究、`design.md`、`pm-state.md`、活配置/gate/ledger/签收/凭证、其他 key 运行材料（按卡要求回避）。

### 勘误（本轮写入后自校）

- 证据 §9 AC-014 行中出现一处笔误串 `count_approval=second_approval`；正确表述应为：签收输出键集含 `second_approval`（恒 0，表示没有第二次 PM 批准）。该行其余内容与全文其余部分不受影响，未重写整篇以避免制造第二份内容不一致的版本。
