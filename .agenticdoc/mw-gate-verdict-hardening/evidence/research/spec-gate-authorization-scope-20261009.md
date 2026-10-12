# Research: 闸门授权范围的框架侧现状（RQ-3 / G3）

> Key: mw-gate-verdict-hardening ｜ 角色: RQ-3（只读调研，SPEC 阶段） ｜ 快照: 2026-10-09
> 决策问题：G3「闸门 note 自由文本被当成授权改写 AC/VC 生效文本」要修成「`authorizes:` 显式授权字段（闭集动作类型）+ worker 提示词硬约束 + `advance *->done` 前 AC/VC 文本变更的机械授权检查（fail-closed）」，本文查清框架侧现状与既有可复用载体。
> 说明：全部事实带 `文件:行号`；工作树 = 2026-10-09，`HEAD=10446aefb`（`mw-autopilot-slot-capacity` 已 DONE）。跨项目只读引用 `H:\git\E2Feature`（冻结时刻见 §F7）。本文只做只读调研，未改任何代码，唯一写面 = 本文件。

## 调研方法与出处

- 只读 `read`/`grep`：`packages/multi-workers/{autopilot/*.py,*.py}`、`packages/coding-agent/src/extensions/agent-team-loop/**/*.ts`、`.agents/skills/agentic-task/{scripts,core,claude}/**`。
- 只读跨项目：`H:\git\E2Feature\.agenticdoc\feature-gui-time-mvp-board\{design.md,evidence/repair-a3-verdict-20260926.md}`、`.agenticdoc/_autopilot/gates/gate-0014.md`、`.agenticdoc/_autopilot/reflect/gate-note-authorization-scope.md`、`build-runs/gui/respec/{contract_sync.json,decisions.jsonl}`、`tools/featurecontract/**`。
- 实测：`python -X utf8 -c` 导入 `autopilot.gates` 取字段集长度/成员；`Get-FileHash` 取框架脚本副本哈希；`git log` 取 HEAD。行号以 `read` 工具 / Python 行号为准（PowerShell `Get-Content` 对多字节行计数不可靠，本文不采用其行号）。

## 发现

### F1 gate frontmatter 现状：v2 是纯可选加性扩展，`authorizes:` 走 v2 即可，无需 v3

**允许集与三类形状**（`packages/multi-workers/autopilot/gates.py`）：

| 常量 | 行 | 值 / 语义 |
|---|---|---|
| `GATE_KINDS` | `gates.py:65-72` | 6 类闭集，含 `xkey-authorize` |
| `GATE_STATUSES` | `gates.py:74` | `{pending, approved, rejected}` |
| `FRONTMATTER_FIELDS` | `gates.py:87-131` | **40** 名 = 前 12 冻结 base（`id..note`）+ 后 28 可选 v2；顺序冻结（`gates.py:85-86` 注释「never reordered, never repurposed」） |
| `_REQUIRED_FIELDS` | `gates.py:138-144` | 恰 6 个 `{id,kind,created_at,created_by,question,status}`；含 import 期 assert，把「v2 字段必须保持可选」变成可执行约束（`gates.py:141-144`） |
| `_LIST_FIELDS` | `gates.py:151` | 2 个 `{context_refs, evidence_refs}`（YAML 块列表） |
| `_JSON_LIST_FIELDS` | `gates.py:152-161` | 6 个 `{verdicts_final, open_items, roadmap_validation, constraints, write_scope, out_of_band_actions}`（单行 JSON 数组） |
| `_JSON_OBJ_FIELDS` | `gates.py:162` | 2 个 `{goal_diff, blast_radius}`（单行 JSON 对象） |
| `gate_schema` 枚举 | `gates.py:80-82` + 校验 `gates.py:629-634` | 冻结 `{1,2}`；缺省=1（legacy），其它值 fail-closed |

实测（import `autopilot.gates`）：`len(FRONTMATTER_FIELDS)=40`，`[:12]` = base，`len(_REQUIRED_FIELDS)=6`，`_LIST_FIELDS=2`，`_JSON_LIST_FIELDS=6`，`_JSON_OBJ_FIELDS=2`，`_GATE_SCHEMA_VALUES={1,2}`。

**新增字段的解析路径是加性、fail-closed 的**：
- 未知字段名 → `GateFormatError`（`gates.py:484-487`）；缺必需字段 → 同样抛错（`gates.py:574-578`）；缺可选字段 → `optional()/optional_json()` 取 `None`/`[]`（`gates.py:514-678`）。
- `create()` 只渲染 base 12 + `gate_schema: 2`（`gates.py:264-305`，`gate_schema` 在 `gates.py:277`，共 13 键）；其它 v2 字段由 `_rewrite_gate_fields` 在 `create()` 之后原地补写（`conductor.py:5967-5991`），这正是 `_stamp_gate_defaults` 盖 `expires_at`/`default_action` 的通道（`conductor.py:2499-2551`，默认常量 `GATE_DEFAULT_TTL_SEC` `conductor.py:2838` / `GATE_DEFAULT_ACTION` `conductor.py:2841`）。
- ⇒ **`authorizes:` 只需追加进 `FRONTMATTER_FIELDS` 末尾（索引 40）**：可选、缺省即未授权、v1 文件照旧 parse。不需要 v3：`gate_schema` 是「文件形态版本标记」而非「字段集哈希」，v2 自述纯加性（`gates.py:25-27`、`gates.py:85-86`）。只有把字段做成**必填**才会撞上 `_REQUIRED_FIELDS` 冻结 assert（那才需要新版本标记）。

**与授权/范围相关的 5 个 v2 字段：语义 + 当前写者（grep 证明，P-023）**：

| 字段 | 语义（读面） | 生产写者 | 证据（file:line） |
|---|---|---|---|
| `write_scope`（JSON list） | xkey 自动裁决命题的「允许写集合」 | **0** —— 命题读 `conductor.py:5112-5113`，值恒 `None` ⇒ 命题必 `xkey-blast-radius` 失败（`auto_action="guard"`） | `gates.py:119,158,668`；`conductor.py:5099,5113,5115,5120,5519` |
| `blast_radius`（JSON obj） | 同上「实际改动集合」 | **0** | `gates.py:120,162,669`；`conductor.py:5112,5518` |
| `out_of_band_actions`（JSON list） | 带外动作登记 | **0**（连读点都没有，只有 parse + TS 镜像） | `gates.py:126,159,675`；`status-model.ts:636,695,910` |
| `answer_source`（scalar） | 「谁答的」机器标记 | **0**（自动应答实际写 `answered_by="conductor-auto:<rule_id>"`；读点仅 doctor JSON 与卡片） | `gates.py:33,121,239,670`；`mw_common.py:2525`；`mw.py:3775` |
| `auto_policy_id`（scalar） | 自动策略 id | **0**（无任何读点） | `gates.py:33,122,240,671`；`status-model.ts:632` |

对照组（**有**生产写者的 v2 字段，证明「字段声明 ≠ 已有写者」是本仓既有形态、不是解析缺陷）：
`expires_at`/`default_action` 由 `_stamp_gate_defaults`（`conductor.py:2499-2551`）盖章；`reason_code`/`loop`/`used_rounds`/`round_limit`/`credits_used` 由 `mark_stalled`（`conductor.py:4709-4760`）经 `_create_gate(machine_fields=…)`（`conductor.py:2450-2497`）盖章；`consumed_at`/`consumed_seq` 由 `_rewrite_gate_consumed`（`conductor.py:407-431`）写。其余 `goal_sha256*/goal_diff/verdicts_final/roadmap_validation/observed_at/subject_sha256/proposal_sha256/evidence_anchor_mtime_ns` 全仓**只有读点或仅 parse**，无生产写者 —— 与 `write_scope` 同族。
写侧闭集护栏先例：`REASON_CODES`（`conductor.py:4891-4926`）在 `_stamp_gate_defaults` 里对越界值「丢弃 + 记 config 事件」（`conductor.py:2519-2527`、`conductor.py:2530-2551`）。

### F2 TS 镜像：新字段两侧必须同步的**确切位置**

Python 侧（源）：
1. `gates.py:87-131` `FRONTMATTER_FIELDS`（追加末尾；顺序冻结）
2. 形状登记：标量闭集 → 仿 `gate_schema` 的枚举校验（`gates.py:629-634`）；列表 → `gates.py:152-161` `_JSON_LIST_FIELDS`
3. `gates.py:193-247` `Gate` dataclass 字段
4. `gates.py:514-678` `_to_gate()` 校验 + 构造（`gates.py:657-678` 逐个 `optional*`）
5. `gates.py:264-305` `_gate_file_content`（仅当 `create()` 要就地渲染时）
6. `mw_common.py:2442-2532` `_gate_pending_entry`（doctor/JSON 投影）+ `mw.py` 卡片（投影字段，非 schema）

TypeScript 侧（镜像）：
1. `status-model.ts:599-643` `GATE_FRONTMATTER_FIELDS`（40 名同序；跨语言锁 = `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:205-242`，起 Python 子进程逐项比对，`expect(pyFields).toHaveLength(40)` 在 `:223` —— 加字段必须同步改此断言）
2. `status-model.ts:647-684` `GateRecord` 接口（presentation 投影）
3. `status-model.ts:687-697` `GATE_LIST_FIELDS / GATE_JSON_LIST_FIELDS / GATE_JSON_OBJ_FIELDS`
4. `status-model.ts:727-920` `parseGateFile()`（未知字段 fail-closed `:758-759`；JSON 字段强制校验 `:872-873`）
5. `gate-writer.ts:24-50` `AnswerGateOptions` + `ANSWER_FIELDS = ["status","answered_at","answered_by","note"]`（`gate-writer.ts:50`）。**若 `authorizes:` 要由人在应答时填写**，必须扩 `ANSWER_FIELDS` + options + `answerGate()`（`gate-writer.ts:139-235`）；若由 conductor 创建时盖章，则此处不动（推荐盖章路径，见 F1）。

应答契约与封堵面：
- `gate-writer.ts` 只重写那 4 个字段、其它行逐字节保留（`gate-writer.ts:88-136`）；`rewriteAnswerFields` 对未在白名单的字段直接跳过（`gate-writer.ts:121`）。
- `xkey-gate-guard.ts`（在 `shared/`，非 `autopilot/`）阻止 agent 的 `write`/`edit`/`bash` 触碰 `<project>/.agenticdoc/_autopilot/**`（除 `_autopilot/xkey/**` 子树）：规则与自述 `shared/xkey-gate-guard.ts:7-45`，路径判定 `isXkeyGatePath` `:157-162`，bash 判定 `checkXkeyGateBashCommand` `:196-235`，注册 `registerXkeyGateGuard` `:250-276`，在每种模式都注册（`index.ts:5,49`，与 `:42` `:59` 并列）。⇒ worker **不能**通过工具通道伪造 `authorizes:`；残余风险是同 uid 带外进程（`xkey-gate-guard.ts:29-36` 自述）。

### F3 worker 提示词现状：**没有任何**「不得改已锁 AC/VC 生效文本」约束

提示词构造点全在 Python conductor（TS 只提供 `TOOL_ALLOWLISTS`，`worker-mode.ts:52-65`，不构造提示词）：

| 函数 | 行 | 指向 worker 的确切措辞（要点） | 是否含 G3 授权/AC-VC 约束 |
|---|---|---|---|
| `_roadmap_writer_prompt` | `conductor.py:795-859` | 「唯一写入目标：`.agenticdoc/_autopilot/_roadmap.md`（整个文件重写）。读取仅限 .agenticdoc 下」（`conductor.py:852-854`） | 否 |
| `_exec_prompt` | `conductor.py:1313-1319` | 「按任务书执行…只碰任务书列出的文件」（`:1318`） | 否 |
| `_l3_prompt` | `conductor.py:1433-1452` | 「你的 output.md 必含两节…判定按 output.md → report.md」（`:1439-1443`） | 否 |
| `_repair_prompt` | `conductor.py:1453-1468` | 「逐项修复并补充 [VERIFY] 证据到 evidence/；不重写无关 artifact」「只读约束：workers/*-l3-*/ 下的 output.md 与 report.md 属 reviewer 本轮产物（L3 判定源）」（`:1465-1467`） | 否（只保护 reviewer 产物，**不保护 spec/design 的 AC/VC 条文**） |
| `_phase_writer_prompt` | `conductor.py:2291-2297` | 「为 key {key} 生成 {phase} 阶段 artifact…产出到 `.agenticdoc/{key}/` 下对应文件」（`:2293-2296`） | 否（**最危险**：直接授权写 spec/design） |
| `_verifier_prompt` | `conductor.py:2300-2309` | 「L1 机械审计报告缺口…结论与证据指针写入你的 output.md」 | 否 |
| `_fix_writer_prompt` | `conductor.py:2312-2327` | 「生成/补齐证据文件使机械审计可闭合，不改动无关 artifact」（`:2326`） | 否 |
| `_xkey_proposal_prompt` | `conductor.py:3824-3927` | 唯一写入目标 `_autopilot/xkey/evidence/<request_id>/proposal.md`；「除下方唯一写入目标外，不得修改任何其它文件」（`:3887`）「不得修改目标文件的断言主体 / 测试逻辑」「不得修改任何其它文件（含测试文件、其它 key 的产物、conductor/框架文件）」（`:3910-3911`） | 部分（针对 xkey 冻结块，非 AC/VC）—— **唯一的硬约束先例** |

派发调用点：roadmap `conductor.py:784`；phase-writer `conductor.py:1192`；verifier `conductor.py:1266`；fix-writer `conductor.py:1230`；exec `conductor.py:1375`；L3 `conductor.py:1870,1909,1941,1982,2034`；repair `conductor.py:2026`。
全仓 grep `不得修改|授权源|生效文本|已锁定|AC/VC` 在 `packages/multi-workers` **仅命中 `conductor.py:3887,3910-3911`**（xkey 提案），无 G3 约束。
⇒ 要加硬约束的位置 = `_repair_prompt`（1453） + `_phase_writer_prompt`（2291） + `_fix_writer_prompt`（2312），三者都能触及 spec/design。**「tasks-writer 提示词」在本仓不存在**：全仓 `tasks-writer` **0 命中**；`dispatch.py` 的 roles 注册表（`dispatch.py:72-113`）只有 `roadmap-writer/phase-writer/verifier/reviewer/repair/rag-research/vision`。

### F4 AC/VC 生效文本的载体与身份：**没有**文本级冻结，只有 id 级指纹 + 纯文档约定

- **spec.md §3 AC 表**：唯一机器解析器是 `audit_evidence.py:108-124` `extract_ac_list`，**只取 `| AC-NNN |` 行的 id**（正则 `_AC_ID_RE` `audit_evidence.py:58`），不取描述文本。
- **design.md VC 断言**：全仓**无 VC 文本解析器**。`audit_evidence.py:127-151` `_extract_decisions` 只解析 `### D-NNN` 决策节 + 决策表首列（`_DECISION_HEADER_RE` `:60`），完全不碰 VC 断言。
- **`_md_section` 不解析 spec/design**：定义 `conductor.py:1396-1407`；全部调用点（`conductor.py:1424-1425,1533-1534,1700-1701,2109-2110`）都在读 worker 的 `output.md`/`report.md`。
- **`evidence-requirement.md` 的冻结是指纹级、且只覆盖 id**：示例 `.agenticdoc/mw-autopilot-slot-capacity/evidence-requirement.md:9` `ac_fingerprint=b623c94027ae`、`:11 ac_ids`、`:13 vc_ids`；生成器 `.tmp/msc-gen-evidence-req.py:101` 明写 `fingerprint = hashlib.sha1(("\n".join(ids) + "\n").encode()).hexdigest()[:12]`。⇒ **改 AC-001 的正文不改指纹**（文本无身份）。历史佐证：`.agenticdoc/mw-vision-role/evidence-requirement.md:10` 曾同时保留「spec §3 区块文本归一化 sha1」旧口径，并注明该口径**对文本编辑敏感**、故弃用，改用 id-set 口径。
- **AC 锁定只是文档约定**：`.agents/skills/agentic-task/core/workflows/requirements.md:378-393` 规定「Step 5 用户确认 spec → AC 编号+内容锁定」并追加 `> 🔒 AC Locked at {ISO-8601}，编号永不回收`；全仓脚本无任何读取（`AC Locked`/`🔒` 在 `.agents` 下**只命中该 workflow 文档的 3 个副本** `core/workflows/requirements.md:294,381`、`references/workflow-requirements.md:294,381`、`claude/skills/workflow-requirements/SKILL.md:294,381`；代码里唯一出现是测试 fixture `test_autopilot_audit.py:38` 的样例行，不解析）。
- **`advance <key> done` 拿不到「本轮 diff」**：`.agents/skills/agentic-task/scripts/advance_phase.py` 的 done 规则（`advance_phase.py:69-95`）是 5 条纯文件检查（`achieved.md ≥200B`、含「系统行为变化」、含「遗留」、`pm-state.md` 含 `PASS`、`evidence/quality-gate-report-*.md ≥1`）；`check_gate()`（`advance_phase.py:191-289`）只支持 8 类检查（`file_min_bytes/dir_has_files/content_match/spec_goal_alignment/spec_ac_numbered/glob_has_files/mermaid_valid/memory_feedforward`），**无 diff 检查**。脚本能起 git 子进程（`_git_short_head` `:426-441`）但只用于 `_project_log.md` 的 commit 列（`append_project_log` `:443`，调用 `:611-612`）。conductor 侧包装器 `packages/multi-workers/autopilot/advance.py:164-203` 只透传 `key/phase/--summary`。⇒ 要拿 diff，必须新增机制（`git diff` + 冻结锚点），现有接口无此信息。
- **框架脚本多副本**：`advance_phase.py` 在 `.agents/skills/agentic-task/{scripts,core/scripts,claude/scripts}/` 与 `.claude/scripts/` 四份 **sha256 短值全等 `9427ABE2ECC0`**（实测）；另有 3 份陈旧副本在 `packages/multi-workers/.tmp/agentic-task/*`（`4111BFF403BC`）。改门禁必须四份同步。
- **本仓无 `contract_sync` / `decisions.jsonl` 实现**：`packages/` 下精确串 `contract_sync` **0 命中**；`decisions.jsonl` 仅命中 `auto-decisions.jsonl`（`conductor.py:4944`，是**自动决策账本**，不是用户批准记录）。二者均只作为跨项目先例出现在 `.agenticdoc/*` 文档中。

### F5 既有「批准记录」载体：本仓唯一机器载体 = **已应答的 `xkey-authorize` gate**

- **`xkey-authorize` gate（T-24 已接机器判定）**：
  - kind 闭集成员（`gates.py:65-72`）；创建（去重 + 写 `context_refs`）：`conductor.py:3488-3512` `_xkey_ensure_gate`，`refs=[request_id, ticket_rel]`；去重维度 `_gate_open(request_id=…)` 匹配 `context_refs`（`conductor.py:2575-2600`）。
  - **只认「已应答」**：`mw_common.py:2590-2612` `_crosskey_machine_carriers`（`kind=="xkey-authorize" and status!="pending"`，取 `context_refs[0] → gate id`）；`mw_common.py:2593` 明写「A pending gate is not a carrier: only the answer authorizes」。
  - 判定/应答契约：`/autopilot gate <id> approve|reject --note <text>`（应答写入面 `gate-writer.ts:1-18,139-235`；卡片提示串 `mw_common.py:2526`、`mw_common.py:2843`）。注意：**当前授权只由「答了」这一事实表达，`note` 是自由文本**（`gate-writer.ts:32-34`），这正是 G3 的缺口。
- **字段形状（若要显式化）**：`authorizes:` 建议走 `_JSON_LIST_FIELDS`（闭集动作类型数组，如 `["retry"]` / `["contract-change"]`），或标量闭集枚举 + 写侧闭集护栏（先例 `conductor.py:4891-4927` + `conductor.py:2519-2527`）。两种都是 v2 可选扩展（见 F1）。
- **跨项目先例（可参考形状、本仓无实现）**：E2Feature `build-runs/gui/respec/contract_sync.json#authorization = {"decision_id":"D-2"}`（文件实测），由 `tools/featurecontract/decisions.py:441-454` `authorization_source_problems` 机械校验（旧授权源/缺失/非 approved ⇒ `UNAUTHORIZED_DECISION`）。决策行 schema = `ROW_KEYS`（`decisions.py:49-58`：`decision_id/author/decided_at/chosen_options/authorization_text/scope_notes/status/supersedes`）。授权判定 `decisions.py:358-385` `authorization_problems`（机器作者/空 `authorization_text`/`decided_at` 早于矩阵生成 ⇒ `UNAUTHORIZED_DECISION`）；解析 `resolve_authorization` `decisions.py:410-428`。CLI：`cli.py:2123+` `run_decide`（参数面 `--decision-id/--authorization-text/--scope-notes` 在 `cli.py:147,156,158`）。参数源 `contract-params.yaml:22-40`（`legacy_authorization_source: _autopilot/gates/gate-0014.md` 在 `:33`，显式降级为历史引用）。
- **复用裁定**：本仓内**复用已应答 gate 载体**（`_crosskey_machine_carriers` 的既有协议 + `_gate_open`），不新造 ledger；跨 key 之外的「contract-change」授权若落在 `stalled`/`stage-close` 门上，用 F1 的 `authorizes:` 闭集字段扩展该门即可。E2Feature 的 `decisions.jsonl`/`contract_sync.json` 是**项目侧**机制，本仓不存在，不应作为框架门禁的依赖（否则逼本仓新造一套）。

### F6 「散文不当授权」判据（T-24）与 issue code 现状

- `mw_common._crosskey_prose_scan`（`mw_common.py:2614-2688`）：输入 = `<project>/.agenticdoc/_autopilot/evidence/cross-key-repair-request-*.md`（`mw_common.py:2544-2545`）；输出每条 = `{path,request_id,status,machine_authorized,carrier_gate,prose_decision,authorization∈{machine,prose,none,unreadable},treated_as_authorized}`，`treated_as_authorized = (authorization=="machine")`（`mw_common.py:2675-2679`）——**fail-closed**。
- 收敛判据 `_crosskey_prose_decision`（`mw_common.py:2559-2578`），正则 `_CROSSKEY_DECISION_RE`（`mw_common.py:2552-2557`：`^\s*\*{0,2}\s*decision\s*:\s*(approved|rejected)… by <who> at <ts>`）；载体判定 `_crosskey_machine_carriers`（`mw_common.py:2590-2612`）。
- issue 输出：`_doctor_issues` 的 `mw_common.py:2869-2884`，实测文案起始行 `mw_common.py:2880`（串含 `treated as unauthorized (VC-048)` 在 `:2883`）；文本层门 `_gates_text_alerted`（`mw_common.py:2764-2777`，`:2766` 注释点名 I9/T-24）；CLI 出口 `mw.py:3795-3803`。
- **既有 issue code 集（结论：没有机器常量，只有注释标签）**：`_doctor_issues`（`mw_common.py:2780-2956`）全部是 `issues.append("…")` / `suggestions.append("…")` 自由文本串（该函数体内实测 **28** 个 append 调用；`I1..I9` 只出现在注释/设计档，`\bI\d{1,2}\s*=` 常量定义 **0**）。语义锚点：
  - I1 解析错 → `mw_common.py:2828`；I2 pending 缺 `expires_at`/`default_action` → `:2834-2841`；I3 等待 >24h/>72h → `:2842-2849`；I4 漂移 → `:2854-2859`；I5 重放 → `:2860-2866`；I6 schema2 缺决断字段 → `:2850-2853`；I7 零扰动文本层 → `_gates_text_alerted`（`mw_common.py:2764-2777`）；I9/T-24 散文授权 → `:2869-2884`。
- ⇒ **G3 无法「共用同一 issue code」**（本仓根本没有 code 常量可共用）。可复用的是**机制**：`_crosskey_prose_decision` 式谓词 + `_doctor_gates` 段字段 + `_doctor_issues` 的 fail-closed issue 串。标签层面建议**新增一个**（如 I10 / 对应新 key 的 VC 号），因为直接复用 VC-048 的串会把对象说错（VC-048 文案点名 `cross-key repair request` 与 `xkey-authorize gate`，`mw_common.py:2880-2884`）。

### F7 反向用例真实样本（跨项目只读）

事故样本（`H:\git\E2Feature`，冻结 2026-10-09）：
- `gate-0014.md:2 id: gate-0014` / `:3 kind: stalled` / `:12 status: approved` / `:13 answered_at: 2026-09-26T02:20:17+00:00` / `:14 answered_by: wenbozhou` / `:15 note: 方案 A 人工介入后重试。…**放宽的是验证方式与文档同步，属可修范围**；若下一轮仍同 5 项，则转 closed-legacy 加四态登记。`（note 由 **PM** 撰写，用户只对「A」这个选项作答）。
- `design.md:1048`「> **授权链（可复核）**：」+ `:1052` 第 2 环逐字引用 `gate-0014.md`（`status: approved`/`answered_by: wenbozhou`/`answered_at`）→ `:1055-1060` §7/§11 五条 VC 生效口径 + 四处同步；`design.md:1048-1060` 是**被单边改写的生效文本本体**。
- `evidence/repair-a3-verdict-20260926.md:19`：「因此本轮走**正式变更**路线，授权 = 用户裁决 `_autopilot/gates/gate-0014.md`」；同文 `:114` 把 gate-0014 列为 `contract_sync` 的授权链。
- 后经正式通道 `decisions.jsonl` 的 `D-2`（`build-runs/gui/respec/decisions.jsonl` 第 2 行，`status: approved` / `author: wenbozhou` / `authorization_text` 非空）+ `contract_sync.json#authorization.decision_id = "D-2"` 追认；`contract-params.yaml:33` 把 gate-0014 降级为 `legacy_authorization_source`（只作历史引用）。
- 反思记录（背景只读）：`.agenticdoc/_autopilot/reflect/gate-note-authorization-scope.md`（根因 1 = 「闸门 note 的授权范围未显式化」；长期修复三项与本 RQ 完全对齐）。

**G3 的最小可复现输入**（机械判据输入形状，反向用例）：
1. 一个 answered gate 文件：`kind: stalled`（或 `stage-close`），`status: approved`，`note: '<自由文本含「属可修范围」类措辞>'`，且 **`authorizes:` 缺省或 `[]`**；
2. 同 key 的 `spec.md` §3 AC 行文本或 `design.md` VC 断言文本相对冻结锚点发生变化；
3. 不存在「带 `authorizes: ["contract-change"]` 的已应答 gate」或其它批准记录；
4. 执行 `advance <key> done` ⇒ 必须**拒绝**（fail-closed）并留 machine-readable 留痕。
反向对照（把 1 换成 `authorizes: ["contract-change"]` 的已应答 gate）⇒ 放行，证明判据非空洞（P-016）。

## 结论 → 决策映射

1. **`authorizes:` 走 v2 可选扩展，不升 v3**（F1）：`_REQUIRED_FIELDS` 冻结 6 格、v2 自述纯加性、缺省即未授权。若把它做成必填才需新版本标记。
2. **两侧同步清单已枚举**（F2）：Python 6 处 + TS 5 处 + 锁测试（`test_autopilot_gate_schema_v2.py:138-149`、`test_autopilot_gate_schema_v2.py:155-160`、`autopilot-gate-presentation.test.ts:205-242`）。**并必须决定** `authorizes:` 是创建时盖章（conductor，走 `_rewrite_gate_fields`）还是应答时填写（则须扩 `gate-writer.ts:50 ANSWER_FIELDS` + options）。
3. **worker 硬约束落点**（F3）：`_repair_prompt:1453` / `_phase_writer_prompt:2291` / `_fix_writer_prompt:2312`（可先例 `_xkey_proposal_prompt` 的「不得修改…」串 `conductor.py:3887,3910-3911`）；「tasks-writer」不存在，不必找。
4. **done 前检查没有现成 diff 通道**（F4）：`advance_phase.py:69-95` 是纯文件检查（5 条规则 / 8 类检查），四份副本需同步；要机械 diff 必须新增「AC/VC 文本冻结锚点 + git diff」——现有 `evidence-requirement.md` 指纹只覆盖 id。
5. **批准记录复用已应答 gate 载体**（F5）：复用 `_crosskey_machine_carriers`（`mw_common.py:2590-2612`）+ `_gate_open`（`conductor.py:2575-2600`）+ 「答了才算」语义；不新造 ledger。E2Feature 的 `decisions.jsonl` 形状可借鉴但本仓无此机制。
6. **issue code 无常量可共用**（F6）：I1–I9 只是注释标签；G3 新增一个 fail-closed issue（复用 `_doctor_gates`/`_doctor_issues` 机制），不要复用 VC-048 的文案对象。
7. **反向用例可直接用 E2Feature 真实语料**（F7）：`gate-0014.md:15` note + `design.md:1048-1060` 改写 + `repair-a3-verdict-20260926.md:19` 的「授权源」引述，构成最小输入。

## 数据缺口

- `authorizes:` 的字段形状（闭集动作枚举）与「创建时盖章 vs 应答时填写」未定 —— 属 design 决策，不在本调研范围。
- AC/VC 文本冻结锚点的载体未定（新增 sidecar / 复用 `subject_sha256` 字段 / 扩 `evidence-requirement.md`）—— 本调研只证明现状为空。
- E2Feature 语料为只读快照，冻结时刻 2026-10-09；其 `contract_sync.json`/`decisions.jsonl` 不进本仓。

`[VERIFY] RQ-3: py_fields=40 base=12 required=6 list_fields=2 json_list=6 json_obj=2 schema_values={1,2} ts_fields=40 ts_parity_lock=autopilot-gate-presentation.test.ts:205-242(toHaveLength(40)@223) authorizes_field_hits=0(py+ts,non-dist) authz_v2_fields=5(write_scope,blast_radius,out_of_band_actions,answer_source,auto_policy_id) authz_v2_production_writers=0 prompt_builders=8 g3_prompt_constraints=0(xkey-only@conductor.py:3887,3910-3911) tasks_writer_hits=0 ac_vc_text_parser=0(ids-only@audit_evidence.py:108-124) ac_fingerprint_scope=ids-only(msc-gen-evidence-req.py:101) advance_done_rules=5 advance_check_types=8 diff_checks=0 advance_phase_copies=4(sha256=9427ABE2ECC0)+3-stale(4111BFF403BC) crosskey_prose_issue=mw_common.py:2880 issue_code_constants=0 issue_append_calls=28 contract_sync_code_hits=0 decisions_jsonl_code_hits=0(only auto-decisions.jsonl) reverse_sample=gate-0014.md:15+design.md:1048-1060+repair-a3-verdict-20260926.md:19 HEAD=10446aefb`