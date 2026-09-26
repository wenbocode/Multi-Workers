# Design: gate 字段补齐路线与三层呈现契约（D6 / key `mw-autopilot-slot-capacity`，AC-026 的设计落地）

> 角色：DESIGN 期设计卡（**只读**调研 + 设计）。本文件是本卡**唯一写面**：未修改任何代码，未回答任何 gate，未写 FM/E2/JC 任何文件，未 commit。
> 代码基线：`H:/git/Multi-Workers` HEAD `191a069a4e95bdcfb2a0bac88f800a566490c1a6`。`git diff --stat 4ef71e053 191a069a4`（RQ-12/RQ-14 的基线）实测 **只有 `.agenticdoc` 文档变更、零代码差异** ⇒ RQ-12/RQ-14 的 `file:line` 在本卡逐条复核后仍成立；本卡另对全部引用锚点在本工作树上重新取值。
> 数据快照：**2026-09-26T08:33Z**。实测 gate 现状 = **34 已答 + 2 pending**（2 条 pending 均在 JC：`gate-0007` stage-close stage 2、`gate-0008` stage-close stage 1）。本文件所有"现在"均指该时刻。
> 边界：不重复 RQ-12（命题自举性 + 23 个最小附加字段）与 RQ-14（14 项最小信息集 + 呈现草案 + D1-D7）；本卡只做**设计落地**：去重后的字段清单（含真实写/读锚点）· 格式与兼容性 · 三层呈现契约 · `mw doctor` gate 段 · VC 候选。代码**怎么改不写**（不给 patch），但每一条都给到"改哪一行、谁写、谁读"的粒度。

## TL;DR

1. **合并去重后 = 12 个已有字段（底座）+ 26 个新增字段**。26 = RQ-12 的 23 条**全部保留**（无删无并）+ D6 补的 3 条（`default_action`〔承载 RQ-14 F13 的"默认动作"，RQ-12 的 23 条里只有 `expires_at`，没有默认动作载体〕、`out_of_band_actions`〔承载 F10，RQ-12 无载体〕、`gate_schema`〔版本标记，见 §D2.2〕）。逐条给**真实写点/读点**（`file:line`），已存在的字段指出**复用来源**。
2. **RQ-14 的 14 项信息集**由"26 字段 + 5 个派生量"完整承载；**3 项仍无数据源**（F9 弃置代价、F10 带外修复的机器可读化、F3 选项后果只在代码常量）——它们进**数据缺口**，不进字段清单（否则契约给出填不出的字段，直接违反 D4）。
3. **手写 YAML 子集是硬约束**（RQ-12 未覆盖）：`gates.py:38-45` 明写"无注释、无 `[]` 以外的 flow list、无嵌套"；解析器里**只有 `context_refs` 一个列表字段**（`gates.py:354-364`）。故结构化字段（`verdicts_final` / `open_items` / `goal_diff` / `blast_radius` / `roadmap_validation`）**必须编码成单行 JSON 子串**（`_render_scalar` 会自动加单引号，`gates.py:152-157`），`evidence_refs` 则需把列表字段特判从"仅 `context_refs`"泛化为具名集合（两侧同步）。
4. **兼容性 = 单侧严格、单侧宽松**：新增字段一律**可选**（不进 `_REQUIRED_FIELDS`，`gates.py:86-89`），老文件缺字段时渲染 `unknown (no field)`；**新文件被老代码读会 fail-closed**（`gates.py:345-347` / `status-model.ts:660-661`）——这是设计意图不是缺陷（conductor 是唯一写者，写新字段的代码必然已带新解析；风险只在**降级**，故加 `gate_schema`）。
5. **三层契约全部给到渲染位置与机器判据**：层 A 面板 = `monitor.ts:644-654`（现状**只有 `id (kind)`**，`MonitorGate` 无 `created_at`，`monitor.ts:89-96`）；层 B 卡片 = `console.ts:182-198`（现状 2 行/门）；层 C doctor JSON = 新增 `mw_common._doctor_gates`，紧邻 `_doctor_autopilot`（`mw_common.py:2022-2064`），注册于 `mw_common.py:2177`，issue 走 `_doctor_issues`（`:2067`，autopilot 范式 `:2099-2104`），JSON 出口 `mw.py:524-525`。
6. **发现一处 RQ-14 契约内部矛盾并给出修法**：RQ-14 的 L6/L8/L11/L12 是"≤6/≤3/≤3/≤5 行"⇒ 卡片高度可变，与 AC-026 要求的"**固定 13 行序**"冲突。本卡把每一条逻辑行**收敛为恰好 1 物理行**（列表类字段聚合成一行 + `+N more (see <path>)`），高度恒定 ⇒ 可机器断言。
7. **`mw doctor` 新增 gate 段 + 6 类告警**（解析错、pending 无 `expires_at`/`default_action`、pending 超期、证据漂移、重放门、v2 字段缺失），每条给**修复串**；并保留 AC-012 的零扰动规则（无 pending、无错、无漂移 ⇒ 不输出行、不报 issue）。
8. **VC 候选 8 条**，全部机器可判（逐字子串 / 行长 / 行数 / 哨兵字面量 / 源码级禁 LLM / 两侧字段序相等 / fail-closed 错误串 / 漂移标记）。

## 决策问题

1. **字段补齐路线**：把 RQ-12 的 23 个字段与 RQ-14 的 14 项信息集对齐成**一份去重清单**，逐字段给：字段名 / 含义 / 类型 / 写入点 `file:line`（谁写）/ 读取点（谁用）/ **是否已在磁盘上（复用来源）** / 两侧镜像需求（Python `gates.py` + TS `status-model.ts`）/ **缺失时的 fail-closed 解析行为**（对齐 `gates.py:347`、`status-model.ts:660-661` 的既有约定）。
2. **格式与兼容性**：新字段如何进入 gate 文件而不破坏既有解析；老文件缺字段的默认与告警；**是否需要 schema 版本字段**；给一个真实 gate 文件的 **before/after**。
3. **三层呈现契约落地**：面板每门 1 行 ≤110 列 / `/autopilot gates` 每门固定 13 行序 / `mw doctor` JSON。逐层给**渲染位置**、字段来源（锚点）、长度/截断规则（头/尾保留式）、以及 **D1-D7 在每层如何满足**（重点：禁 LLM 自由生成、漂移标记的机器校验）。现状对照必须写清。
4. **`mw doctor` 段落**：新 gate 段的字段与告警条件（哪些判 issue、修复串），对齐上一 key 的 `_doctor_autopilot` 范式。
5. **VC 候选**：≥4 条机器可判 VC。

**不做**：不实现代码；不判定"哪些门可自动"（AC-025 / RQ-12 的题）；不判定"哪些门可延后"（AC-027 / RQ-13 的题）；不改 FM/E2/JC 的任何文件（含不答 JC 的 2 个 pending stage-close）。

## 调研方法与出处

### 一手代码锚点（只读；行号 = HEAD `191a069a4` 工作树快照，本卡逐条打开核过）

| 面 | 位置 | 与本卡的关系 |
|---|---|---|
| gate 12 字段 schema / 顺序 / 必填集 | `autopilot/gates.py:68-81`（`FRONTMATTER_FIELDS`）、`:86-89`（`_REQUIRED_FIELDS`）、`:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:65`（`CREATED_BY`） | 字段清单的**底座**；新增字段必须在这两处 + TS 镜像同步扩 |
| gate 文件渲染（唯一写者 conductor） | `gates.py:159-200`（`_gate_file_content`，含 `context_refs` 块列表与 `[]` 特判）、`:201-207`（`_write_atomic`）、`:262-287`（`create`，`_iso_now()` 生成 `created_at` 于 `:281-283`）、`:148-150`（`_iso_now`） | 新字段的**物理写入点** |
| 建门总入口（锁 + timeline） | `conductor.py:2160-2185`（`_create_gate`；`gates.create` 于 `:2176`；`gate-created` 事件 `:2182-2184`） | 所有 kind 的统一写入路径 |
| 逐 kind 建门点（`question`/`stage`/`key`/`refs` 的真实取值点） | `stage-confirm` `conductor.py:491-496`；`stage-close` `:649-655`（dossier 写于 `:637-648`）；`stalled` `:3967-3971`（`mark_stalled` 定义 `:3944`，12 个调用点 `:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941`）；`budget-exhausted` `:994-998`；`goal-change` `:2083-2092`（`gates.create` + `goal-halt` detail `:2091`）；`xkey-authorize` `:2735-2741` | 每个新字段"谁写"的落点 |
| YAML 子集的能力边界 | `gates.py:38-45`（docstring：无嵌套、无 flow list、无注释）、`:292-309`（`_parse_scalar`）、`:311-368`（`_parse_frontmatter`：`name not in FRONTMATTER_FIELDS` → 抛错 `:345-347`；`context_refs` 是唯一列表特判 `:354-364`；重复字段 `:349-352`）、`:381-460`（`_to_gate` 类型/枚举校验；必填缺失 `:398-401`；`_check_iso` `:370-379`） | **兼容性设计的硬约束**（结构化字段不能写成嵌套 YAML） |
| TS 镜像 | `status-model.ts:561-567`（`GATE_KINDS`）、`:569`（`GATE_STATUSES`）、`:572-587`（`GATE_FRONTMATTER_FIELDS`，12 字段同序）、`:587-597`（`GateRecord`，**只有 id/kind/status/stage/key/question/createdAt/path**）、`:630-736`（`parseGateFile`；未知字段 `:660-661`）、`:739-777`（`listGates`，错误进 `errors[]`）、`:1009`（`STATUS_SCHEMA="autopilot-status/1"`） | 两侧镜像面 |
| 面板（层 A） | `monitor.ts:61`（`MONITOR_LINE_MAX=110`）、`:89-96`（`MonitorGate`：id/kind/stage/key，**无 `created_at`**）、`:150-178`（`scanPendingGate`，宽松行扫，只取 5 个名字）、`:531-533`（`trunc`：**头保留**截断）、`:604-626`（attention 行，唯一把 `(resume grants one round)` 写进面板处）、`:644-654`（gate 行渲染：多门 `gates: N pending - {id} ({kind}), … -> /autopilot gates`；单门 `gates: 1 pending - {id} ({kind}) -> /autopilot gate {id} approve\|reject`） | 层 A 的**渲染位置与现状对照** |
| `/autopilot gates`（层 B） | `console.ts:182-198`（`cmdGates`：`{id} [{kind}] {stage=}{key=} — {question} (created {iso})` + `answer:` 行，经 `ctx.ui.notify`）；`:195`（answer 串）；`:208`（usage 串） | 层 B 的渲染位置与现状 |
| gate 应答写入 | `gate-writer.ts:30-38`（`AnswerGateOptions`，含 `answeredAt?`/`answeredBy`）、`:50`（`ANSWER_FIELDS = ["status","answered_at","answered_by","note"]`）、`:101-133`（`rewriteAnswerFields`）、`:139-150`（`answerGate`） | 人写的字段（如 `constraints`/`out_of_band_actions`）只能加在这条路径上 |
| `mw doctor`（层 C） | `mw_common.py:2022-2064`（`_doctor_autopilot` 范式：`path/exists/…/origins/diagnostics/error`）、`:2067-…`（`_doctor_issues`，autopilot 块 `:2099-2104`）、`:2149-2188`（`doctor_report` 组装，`report["autopilot"]` 于 `:2177`）、`:2190+`（`format_doctor_text`；autopilot 文本行 `:2282-2287`）、`mw.py:506-532`（`cmd_doctor`；`--json` 输出 `:524-525`，文本 `:527`） | 层 C 的落点与范式 |
| 已有防伪原语（复用，不重造） | `conductor.py:1246-1248`（`_PROVENANCE_FILENAME`/`_L3_TRACE_NAME`/`_PROVENANCE_SLACK_SEC=60`）、`:1356-1449`（`_l3_provenance_record`，含 `source_mtime_ns`/`anchor_path`/`anchor_mtime_ns`/`suspect`）、`:1451-1502`（`_persist_l3_provenance`）；correction sidecar（key 级，字段 `original_sha256`/`corrected_value`/`counted_as_done`）；`_consumed_gate_ids` `:297-313`（正则 `gate-\d{4}` 于 `:310`）、`_advance_failure_streak` `:803-853` | 新字段的**数据来源**（能复用就不要新造判定） |
| 其他磁盘源 | `roadmap.py:53-68`（枚举）、`:73`（`_DOC_FIELDS = ("generated_at","goal_mtime")`；`goal_mtime` 由 roadmap-writer 的 LLM 填，实测差 1ms）、`:229`（`load_roadmap`）、`:367-425`（`validate_roadmap`，唯一调用点 `roadmap_check.py:50`）、`:463`（`stage_by_number`）、`:479-495`（`dependency_graph`）、`:505-533`（`update_key_status`，覆盖写）；`state.py:133`（`read_key_states`）、`:224-249`（`used_rounds`）；`audit_evidence.py:215-261`（`build_dossier`：`gaps[{item,rule,severity}]`）；`timeline.py:67-85`（`EVENT_TYPES` 17 类，**无超时/到期事件**）；`worker-store.ts:7-37`（`WorkerEntry` 8 列，无 writer/origin 列） | `open_items`/`roadmap_validation`/`loop/used_rounds` 的复用来源 |

### 数据（只读；本卡重新取值，未沿用 RQ-12/14 的复算结论）

| 项目 | gate 文件 | 已答 / pending | 本卡用到的真实样例 |
|---|---|---|---|
| JC `H:/git/JCodingAss` | `.agenticdoc/_autopilot/gates/gate-0001..0008.md` | 6 / **2 pending** | `gate-0008`（stage-close stage 1，`created_at 2026-09-26T04:37:27+00:00`）= before/after 与三层 worked example；dossier `stages/stage-1-close.md`（1068 B，`sha256[:12]=18e3fec0133f`，mtime `2026-09-11T20:25:02Z`）；`_roadmap.md` Stage 1 `> status: running` + 4 key 全 `=done`；4 key 的 `l3-verdict.txt` 实测 `llm-router=<无文件>`、其余 3 个 `meets` |
| FM `E:/CLI_workspace/FeatureMigrator` | `…/gates/gate-0001..0010.md` | 10 / 0 | `gate-0010`（`stalled`，`context_refs[1]` 是完整 reason 串）= "reason_code 只能由 conductor 写、不能从 prose 反解"的反例 |
| E2 `H:/git/E2Feature` | `…/gates/gate-0001..0018.md` | 18 / 0 | `stage-*-close.md` dossier；`l3-verdict.txt` / provenance / correction sidecar（RQ-12 已取样，本卡不重算，只作来源引用） |

### 方法

1. 字段清单是"**两份输入清单的并集去重**"，不新增无载体字段；D6 补的 3 条字段逐条标注"RQ-12 未列 + 承载 RQ-14 哪一项 + 若不加会怎样"。
2. 每个 `file:line` 都是本卡在本工作树上打开核过的锚点；"磁盘现状"逐条给出复用来源（已有文件/字段）或显式写"不存在"。
3. 兼容性结论由 `gates.py` / `status-model.ts` 的**解析代码行为**推出（不是规范愿望）：未知字段抛错、必填缺失抛错、可选缺失给 `None`、`context_refs` 是唯一列表。
4. 三层契约的每条"机器校验"都写成可执行的断言形式（逐字子串/长度/行数/哨兵字面量/错误串/字段序相等），便于后续直接落成测试。

## 发现

### D1 — 合并去重后的字段清单

#### D1.0 底座：已在磁盘上的 12 个字段（`gates.py:68-81` = `status-model.ts:572-587`）

| 字段 | 类型 | 写入点（谁写） | 读取点 | 磁盘现状 / 复用 | 镜像 | 缺失时行为 |
|---|---|---|---|---|---|---|
| `id` | `gate-\d+` | `gates.py:281-283`（conductor） | `gates.parse/enumerate` `:463/:483`；`scanPendingGate` `monitor.ts:150-178`；`console.ts:187-195` | 已有 | 两侧 | 解析错（必填，`gates.py:398-401`） |
| `kind` | 6 值闭集 | 同上，逐 kind 建门点见 §调研锚点 | 同上 + conductor 消费 `:316-379` | 已有 | 两侧 | 解析错（枚举，`gates.py:410-413`） |
| `stage` | `int\|None` | `conductor.py:495/654/997/…` | `monitor.ts:89-96`；conductor `_stage_closure` `:616-656` | 已有 | 两侧 | 可空（stage 级门为空） |
| `key` | `str\|None` | `conductor.py:3970/2739` | conductor `mark_stalled`/`_resume_credits` `:2273-2293`；面板 attention `monitor.ts:604-626` | 已有 | 两侧 | 可空（stage 级门为空） |
| `created_at` | ISO-8601 | `gates.py:281-283`（`_iso_now`） | **面板今天不读**（`MonitorGate` 无该字段 `monitor.ts:89-96`）；`console.ts:194` 读；本卡 F1/age/waited/drift 的基准 | 已有 | 两侧 | 解析错（必填 + ISO 校验 `gates.py:370-379`） |
| `created_by` | `"conductor"` | `gates.py:176`（`CREATED_BY`） | 目前无消费者（审计用） | 已有 | 两侧 | 解析错（必填） |
| `question` | 单行散文 | 逐 kind 建门点（§调研锚点） | `console.ts:194`；面板不读（只读 kind） | 已有 | 两侧 | 解析错（必填） |
| `context_refs` | `list[str]` | 逐 kind 建门点（`stalled` 的 `[".agenticdoc/<key>", reason]` 在 `:3970`） | 目前**唯一真消费者是 `_gate_open` 的去重匹配** `:2202-2211`；面板/doctor 均不读 | 已有 | 两侧（唯一列表字段，特判在 `gates.py:354-364`） | 缺省为 `[]`（`gates.py:433`） |
| `status` | `pending/approved/rejected` | 人：`gate-writer.ts:139-150`；conductor 只读 | conductor 消费 `:341-350`；面板 `scanPendingGate`；console `pending` 过滤 | 已有 | 两侧 | 解析错（必填 + 枚举） |
| `answered_at` | `ISO\|None` | 人（`gate-writer.ts:146`，**可被 override** `:38`） | 目前仅审计；**不得**做等待时长/TTL 的唯一来源（RQ-12 F-5 两处污染） | 已有 | 两侧 | 可空；ISO 校验在 `gates.py:442-444` |
| `answered_by` | `str\|None` | 人（`gate-writer.ts:147`），自由文本（实测 4 种写法） | 目前仅审计 | 已有 | 两侧 | 可空；**不可机器判来源**（→ 新增 `answer_source`） |
| `note` | `str\|None` | 人（`gate-writer.ts:148`） | 本卡仅在层 A/B/C 作**逐字引用**（D6），**不作派生输入** | 已有 | 两侧 | 可空 |

#### D1.1 新增字段（26 = RQ-12 的 23 条 + D6 补 3 条）

约定：**类型**列里 `json-list` / `json-obj` = 写成**单行 JSON 子串**（受 §D1.5 的 YAML 子集约束）；`list[str]` = 需要新的具名列表字段（见 §D2.1）。**写入点**列若写 `conductor <anchor>` 即"由 conductor 在既有建门点补写"。所有新增字段**一律可选**（不进 `_REQUIRED_FIELDS`，`gates.py:86-89`）。

| # | 字段 | 来源 | 含义 / 取值域 | 类型 | 写入点（谁写） | 读取点（谁用） | 磁盘现状（复用来源） | 镜像 | 缺失时 fail-closed 行为 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `reason_code` | RQ-12#1（F5） | 触发原因闭集：`advance:<class>` / `l3-below` / `l3-no-verdict` / `l3-suspect` / `exec-exhausted` / `stage:all-keys-terminal` / `goal:mtime-changed` / `budget:loop-exhausted` / `xkey:cross-key-red` | `enum` | `conductor.py:3967-3971`（`mark_stalled`；12 个调用点 `:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941` 各自传码）+ 其余 4 个建门点 | 层 A `reason_class`、层 B L5、层 C `reason_code`、`_doctor_gates` | **不存在**：现在只有 `question` 内嵌 / `context_refs[1]` 的散文串（FM `gate-0010.md:10-11` 逐字样例）；`advance` 类别可由 `_advance_failure_streak`（`:803-853`）复算 | 两侧 | 渲染 `unknown (no field)`；**禁止**从 `question`/`context_refs[1]` 反解（D4/D6） |
| 2 | `evidence_refs` | RQ-12#2（F6/F7） | 证据指针列表，每项 `<kind>:<relpath>[#sha256:12][@mtime_ns]`（`kind ∈ {gate-dossier, l3-verdict, l3-report, achieved, worker-output, trace}`） | `list[str]` | 5 个建门点（`conductor.py:495/654/3970/997/2087`） | 层 B L6、层 C `evidence[]`、漂移判定 | 部分：`context_refs[0]` 已是 `.agenticdoc/<key>`；`l3-verdict.txt`/`achieved.md`/`workers/*` 的路径模式在 RQ-14 F3 已列，但**未进门文件** | 两侧（需新增列表字段类型） | 渲染 `unknown (no field)`；doctor 记 `missing_fields`（仅 pending）；自动决策侧 → 升级给人 |
| 3 | `loop` | RQ-12#3（F5/F14） | 触发该门的回路标签（`l2:<key>:<edge>` / `l3:<key>` / `exec:<key>:<stem>`） | `str` | `conductor.py:3970`（`mark_stalled`）、`:997`（budget 已把 loop 放进 `context_refs[0]`） | 层 B L10、层 C `budget` | **已存在但位置不同**：`budget-exhausted` 的 `context_refs[0]` 就是 loop（`conductor.py:997`）；`state.used_rounds`（`state.py:224-249`）按 `task.md` 的 `loop:` 分组 ⇒ 可复用取值 | 两侧 | 渲染 `unknown (no field)` |
| 4 | `used_rounds` | RQ-12#4（F5/F14） | 该 loop 已用轮次 | `int` | 同 #3 建门点，值取 `state.used_rounds(...)`（`state.py:224`） | 层 B L10、层 C | 可复算（`{key}/workers/*/task.md` 的 `loop:`/`attempt:`）；**门字段是"门时快照"**，防后续轮次改写历史 | 两侧 | `used`/`limit` 缺一即不渲染比值 |
| 5 | `round_limit` | RQ-12#5（F14） | `config.round_budget + credits` | `int` | 同 #3，值取 `config.round_budget` + `_resume_credits`（`conductor.py:2273-2293`） | 同上 | 可复算（`config.json` + 已批 `stalled` 门计数） | 两侧 | 同上 |
| 6 | `credits_used` | RQ-12#6（F14） | 已用的人类续跑额度（= 该 key 已批 `stalled` 门数） | `int` | 同 #3，值取 `_resume_credits` | 同上 | 可复算（`_resume_credits` 每次调用重推，零私有状态） | 两侧 | 同上 |
| 7 | `observed_at` | RQ-12#7（F7） | **证据快照时刻**（≠ `created_at`） | `ISO` | 5 个建门点 | 层 B L6、层 C、漂移判定 | **不存在**（门只有 `created_at`）；复用锚法先例 = `_l3_provenance_record` 的 `source_mtime_ns` | 两侧 | 渲染 `unknown (no field)`；漂移标记降级为"不可判"并显式输出 |
| 8 | `verdicts_final` | RQ-12#8（F5/F7/F12） | 末轮裁决快照 `[{key,verdict,source,source_sha256,anchor_mtime_ns,suspect}]` | `json-list` | `conductor.py:649-655`（`_stage_closure`），值从 `l3-verdict-provenance.json`（`:1356`/`:1451`）取末轮；无 provenance 的 key 记 `suspect=true` | 层 B L6、层 C、`open_items` 的输入 | **部分**：provenance 文件（5/22 key）、correction sidecar（3/22）；`l3-verdict.txt` 是**单一派生记录且会被覆盖**（RQ-12 F-3 实测 6/22 与复算不一致）⇒ 不可作唯一源 | 两侧 | 渲染 `unknown (no field)`；`stage-close` 的自动判定直接 fail-closed 升级给人 |
| 9 | `open_items` | RQ-12#9（F12） | 未达成/遗留台账 `[{kind,key,item,disposition}]`，`kind ∈ {closed-legacy, below, verdict-none, unrecovered-needs-rerun, pending-authorization, prose-only}` | `json-list` | `conductor.py:649-655` | 层 B L12、层 C、doctor | 部分：dossier 5 列表（`conductor.py:722-750`）只给 `key/final phase/l3 verdict/l3 report/evidence`；`audit_evidence.build_dossier.gaps[{item,rule,severity}]`（`audit_evidence.py:224-261`）是 L1 面；`closed-legacy` 0 生产样本（RQ-12 缺口 5） | 两侧 | `unknown (no field)`；**禁止**把空的 `unknown` 渲染成"无遗留"（伪造达成） |
| 10 | `subject_sha256` | RQ-12#10（F6/F7） | 被审主体的 sha256（`stage-close` = dossier 文件） | `str` | `conductor.py:649-655`（dossier 在 `:637-648` 刚写完，可即算） | 层 B L6、层 C、漂移与绑定 | **不存在**；复用先例 = correction sidecar 的 `original_sha256` | 两侧 | 渲染 `unknown (no field)`；主体被改写检测降级为不可判 |
| 11 | `roadmap_validation` | RQ-12#11（F4） | `validate_roadmap` 的问题列表 | `json-list` | `conductor.py:491-496`（`_create_stage_confirm_gate`） | 层 B L4/L11、层 C | 可复算但**未被 conductor 调用**（唯一调用点 `roadmap_check.py:50`）；实测 FM Stage 2 / E2 Stage 3 当前不合法（RQ-12 F-2c）⇒ 直接搬会大量假阳，须先分类 | 两侧 | `unknown (no field)`；不阻塞渲染 |
| 12 | `proposal_sha256` | RQ-12#12（F4） | 被审提案（`_roadmap.md`）的 sha256 | `str` | `conductor.py:491-496` | 层 B L4、层 C | **不存在**（但可算） | 两侧 | `unknown (no field)` |
| 13 | `goal_sha256` | RQ-12#13（F4） | 该门所依据的 `goal.md` 的 sha256 | `str` | `conductor.py:491-496`（stage-confirm）、`:2083-2088`（goal-change） | 层 B L4、层 C | **不存在**；`_roadmap.md > goal_mtime:` 是 LLM 填的 ms 且实测差 1ms（`roadmap.py:73`）⇒ 不可复用 | 两侧 | `unknown (no field)` |
| 14 | `constraints` | RQ-12#14（F11） | 人写范围约束（结构化，替代 `note` 散文里的"不许放宽 X"） | `list[str]` | **人**：`gate-writer.ts:139-150`（需扩 `ANSWER_FIELDS` `:50`） | 层 B L11、层 C；下游消费点**当前不存在**（RQ-12 缺口 9） | 不存在（只在 `note`：FM `gate-0009.md:14` 的 7 条、E2 `gate-0008.md:14` 的 2 条） | 两侧 | 渲染 `unknown (no field)`；不得从 `note` 派生（D6） |
| 15 | `goal_sha256_before` | RQ-12#15（F4） | 变更前 `goal.md` 的 sha256 | `str` | `conductor.py:2083-2088` | 层 B L4、层 C | **不存在**（无 before-image） | 两侧 | `unknown (no field)` |
| 16 | `goal_sha256_after` | RQ-12#16（F4） | 变更后 `goal.md` 的 sha256 | `str` | `conductor.py:2083-2088` | 同上 | 不存在（可算） | 两侧 | 同上 |
| 17 | `goal_diff` | RQ-12#17（F4） | 段落级变更统计 `{sections_added,sections_removed,sections_changed,bytes_delta}` | `json-obj` | `conductor.py:2083-2088`（须先落 before-image，见数据缺口 G-D6-4） | 层 B L4、层 C | **不存在**（`goal-halt` 的 detail 只有 mtime 前后值，`conductor.py:2091`） | 两侧 | `unknown (no field)` |
| 18 | `write_scope` | RQ-12#18（F9/AC-014） | 机器可读写面声明 | `list[str]` | 建门点（`stalled`/`xkey-authorize`），**但数据源不存在**：`write_scope` 在生产代码零命中（RQ-12 F-3(f) / AC-014） | 层 B L7、层 C | **不存在**（前置项，属 AC-014） | 两侧 | `unknown (no field)`；自动决策不得据此判越界 |
| 19 | `blast_radius` | RQ-12#19（F9） | `{files:[...],sha_before:[...]}` | `json-obj` | `conductor.py:2735-2741`（xkey 建门），数据源 = ticket JSON 已有字段 `frozen_block`/`authorization_snapshot`/`target_file_sha256`（`:2641-2700` 实测存在） | 层 B L7、层 C | **部分存在但不在门文件里**：ticket JSON（生产 0 票据） | 两侧 | `unknown (no field)` |
| 20 | `answer_source` | RQ-12#20（F14/AC-018） | `human` / `auto` | `enum` | 人：`gate-writer.ts:139-150`；auto：conductor 自动决策路径（AC-018/020 尚未实现） | 层 B L13、层 C、doctor | **不存在**：`answered_by` 实测 4 种自由写法（RQ-14 F4.1）⇒ 无法区分人与机器 | 两侧 | `unknown (no field)`；审计不得用 `answered_by` 兜底 |
| 21 | `auto_policy_id` | RQ-12#21（AC-018） | 自动决策策略 id（人答时为空） | `str` | 同 #20（auto 路径） | 层 C、doctor | 不存在 | 两侧 | `unknown (no field)` |
| 22 | `expires_at` | RQ-12#22（F13/AC-019） | 到期时刻；到期后执行 `default_action` | `ISO` | 5 个建门点（默认值来自 config，待 AC-019 定策略） | 层 B L9、层 C、doctor | **不存在**（`FRONTMATTER_FIELDS` 无任何时间上界；`EVENT_TYPES` `timeline.py:67-85` 无超时事件） | 两侧 | 渲染 `unknown (no field)`（**如实空值本身即告警面**）；doctor 报 issue |
| 23 | `evidence_anchor_mtime_ns` | RQ-12#23（F7） | 证据快照锚（同轮 `trace.log` mtime，slack 60s） | `int` | 5 个建门点；复用 `_l3_provenance_record` 的锚法（`conductor.py:1399-1415`） | 层 B L6、层 C、漂移判定 | **部分**：仅 `l3-verdict-provenance.json`（`anchor_mtime_ns`，5/22 key） | 两侧 | `unknown (no field)`；漂移标记打 `DRIFT(unknown)` |
| 24 | `default_action` | **D6 补**（承载 RQ-14 **F13**；RQ-12 的 23 条只有过期时刻、没有"到期做什么"） | `auto-approve` / `halt-and-report` / `escalate-to-human` / `auto-reject`（对齐 AC-019 四态） | `enum` | 5 个建门点 + config 默认（AC-019 未定策略 ⇒ 先写 `escalate-to-human`） | 层 B L9、层 C、doctor | **不存在**；不加的后果 = F13 的"默认动作"半边永远没有载体，AC-019 的"缺省不得是隐式永久滞留"无法机器判 | 两侧 | 渲染 `unknown (no field)`；doctor 报 issue 并给修复串 |
| 25 | `out_of_band_actions` | **D6 补**（承载 RQ-14 **F10**；RQ-12 无载体） | approve 之前人/PM 做过的带外动作（改配置/重启/改模型/重写文书），每项 `<action>@<iso>` | `list[str]` | 人：`gate-writer.ts:139-150`（同 #14） | 层 B L3/L11、层 C | 不存在（只在 `note`：≥16/22 条 `stalled` approve 记录过）——**唯一可机器重算的例子**是 E2 `gate-0006` 的"进程启动时间 > 提交时间" | 两侧 | 渲染 `unknown (no field)`；**不得**从 `note` 派生计数（D6） |
| 26 | `gate_schema` | **D6 补**（§D2.2 的版本标记） | `1` / `2`；**缺省 = 1**（legacy） | `int` | `gates.py:159-200`（渲染器统一写 `2`） | 层 C `schema_versions`、doctor、渲染器的"缺失 vs 被剥掉"判别 | 不存在（现在所有文件都是事实 v1） | 两侧 | 缺省按 1 处理；值 ∉ {1,2} ⇒ 解析错（对齐枚举校验约定） |

> **26 条的来源审计**：1-23 = RQ-12 `min_fields=23` 逐条对应（顺序一致，便于与 `[VERIFY] RQ-12` 行对账）；24-26 = 本卡新增，逐条给了"承载 RQ-14 哪一项 / 不加会怎样"和写入点。**未新增任何无承载字段。**

#### D1.2 RQ-14 的 14 项信息集 → 承载映射（补齐后）

| 信息项 | 字段承载 | 派生承载（无字段，必须现算） | 补齐前可得性 | 补齐后 | 备注 |
|---|---|---|---|---|---|
| **F1** 身份与时效 | 底座 `id/kind/stage/key/created_at` + #22 `expires_at` | `age/waited = now-created_at`；**同 scope 历史门 = 门目录扫描** | 机器可读 | 机器可读 | 面板今天不读 `created_at`（`monitor.ts:89-96`）⇒ 必须加进 `MonitorGate` |
| **F2** 命题 | `question` | — | 机器可读 | 机器可读 | 已存在，不动 |
| **F3** 选项后果与可逆性 | — | `derived(options_table)`：唯一来源是代码常量（`conductor.py:2273/2295-2358/2363-2388/348-384/994-998/2083-2111/2735-2741`） | 仅散文（磁盘无字段） | 仍无字段，但有**固定派生表**（§D3.1 的 `derived` 形状，可逐字校验） | 不进字段清单（写不进门文件；进代码常量表） |
| **F4** 目标一致性 | #11-#13、#15-#17 | `_roadmap.md > goal:`；`stage-confirm` 的 `question` 已内嵌 goal | 需读多文件 | 机器可读（除变更摘要需 before-image） | `goal_mtime` 是 LLM 填的 ms，**不可复用** |
| **F5** 触发原因与计数 | #1 `reason_code`、#3-#6、#8 `verdicts_final` | `_advance_failure_streak`（`:803-853`）+ timeline `advance` 的 `class=` | 需读多文件 | 机器可读（原因/计数） | "假阴 vs 真缺陷"的定性仍不可机器判（AC-025 的题） |
| **F6** 证据指针 | #2 `evidence_refs`（含 #10 `subject_sha256`、#23 anchor） | — | 需读多文件 | 机器可读 | |
| **F7** 存在性/体量/节名/新鲜度 | #7 `observed_at`、#23 `evidence_anchor_mtime_ns` | `os.stat` + `^## ` 扫描（现在就能算） | 机器可读（但无快照） | 机器可读 + 可判漂移 | 漂移 = `mtime > created_at` |
| **F8** 影响面 | — | `derived`：`dependency_graph`（`roadmap.py:479-495`）+ `_DEP_SATISFIED`（`conductor.py:56`）/`_stage_closure`（`:616-656`）+ `> status:` | 需读多文件 | 机器可读 | 现状面板/doctor 零覆盖 |
| **F9** 弃置代价 | #18 `write_scope`、#19 `blast_radius`（均**无数据源**） | — | 仅散文 | **仍无数据源** | → 数据缺口 G-D6-2（前置 AC-014） |
| **F10** 带外修复记录 | #25 `out_of_band_actions`（人写） | 唯一可机算样例 = E2 `gate-0006` 的进程启动时间 vs 提交时间 | 仅散文 | 机器可读**当且仅当**窗口强制填写 | → 数据缺口 G-D6-3 |
| **F11** 边界与下一轮要求 | #14 `constraints` | 前序同 scope 门的 `note`（逐字引用，D6） | 仅散文 | 结构化（`constraints`）+ 逐字前序约束 | 下游消费点当前不存在（RQ-12 缺口 9） |
| **F12** 未达成台账 | #9 `open_items` | dossier 5 列表 + `achieved.md` 遗留节 | 仅散文 | 机器可读（conductor 生成） | `closed-legacy` 0 样本 |
| **F13** 默认动作与到期 | #22 `expires_at`、#24 `default_action` | — | **不存在** | 机器可读 | `default_action` 是本卡补的第 24 条 |
| **F14** 谁答/预算余量 | #3-#6、#20 `answer_source`、#21 `auto_policy_id` | `state.used_rounds`（`state.py:224-249`）；应答命令模板（`console.ts:195/208`） | 需读多文件 | 机器可读 | `answered_by` 自由文本 ⇒ 必须靠 `answer_source` |

#### D1.3 字段补齐路线（三批，按"依赖前置"排序）

- **批 P0（零 schema 改动，可先落）**：只读现有磁盘源 + 派生量 —— F1（含 `created_at` 进面板）、F2、F4 部分（`> goal:` / question 内嵌 goal）、F5 部分（timeline `advance` class + `l3-verdict.txt`）、F6 部分（`context_refs[0]` 路径模式）、F7 部分（`os.stat` + 节名）、F8、F12 部分（dossier 5 列）、F14 部分（`used_rounds` + 命令模板）。**交付物 = 三层渲染 + doctor gate 段 + 现状告警**，不含任何新字段。
- **批 P1（v2 字段，conductor 可写）**：#1 `reason_code`、#2 `evidence_refs`、#3-#6、#7 `observed_at`、#8 `verdicts_final`、#9 `open_items`、#10 `subject_sha256`、#22 `expires_at`、#23 `evidence_anchor_mtime_ns`、#24 `default_action`、#26 `gate_schema`。**前置**：#26 与 #2 需要两侧解析器扩展（见 §D2.1）；#8 需要先按 AC-029 冻取证源优先级；#24 需 AC-019 定策略（可先写 `escalate-to-human`）。
- **批 P2（依赖他人前置，不得先写）**：#18/#19（依赖 AC-014 机器可读写面）、#20/#21（依赖 AC-018/AC-020 自动决策路径）、#11-#13/#15-#17（依赖 AC-029/AC-030 快照与不可伪造来源、goal before-image）、#14/#25（依赖窗口 UI + 人填纪律）。**这批字段今天写进去只能是 `unknown (no field)`**，所以必须等数据源。

#### D1.4 fail-closed 的三层原则（对齐既有解析约定）

| 层 | 触发 | 行为 | 既有锚点 |
|---|---|---|---|
| 解析层 | 未知字段名 / 重复字段 / 坏枚举 / 坏 ISO / 必填缺失 | **抛错**（`GateFormatError`），conductor 捕获后**跳过整个 tick** 并写 timeline `config` 事件；TS `listGates` 把错误收进 `errors[]`（console 显式 warning） | `gates.py:345-347/349-352/398-401/410-413/370-379`；`status-model.ts:660-661/663/694-701`；`conductor.py:332-336` 与 `:2066-2069` |
| 呈现层 | v2 字段缺失 / 不能复算 | 渲染固定哨兵 **`unknown (no field)`**；doctor 记 `missing_fields`（**仅 pending 门**）；**绝不**用 `question`/`note` 散文或 LLM 猜测兜底 | 本卡 §D3/D4（新增）；判据源 = P-014 家族 |
| 决策层（未来自动决策） | 决策谓词所需字段缺失 / `suspect=true` / 漂移 | 谓词返回 `unknown` ⇒ **不得自动答**，升级给人（对齐 U-9=B） | AC-019/AC-025；RQ-12 的 `suspect ∧ raw=meets → below`（`conductor.py:1356-1449`）是同族先例 |

#### D1.5 手写 YAML 子集的硬约束（RQ-12/14 未覆盖）

`gates.py:38-45` 的 docstring 逐字限定：`key: value` 标量、单引号 `''` 转义、**`context_refs` 块列表或 `[]`**、**无注释、无 `[]` 以外的 flow list、无嵌套**。解析器里列表字段是**硬编码特判**（`gates.py:354-364` 的 `if name == "context_refs"`，TS 同：`status-model.ts:666`）。⇒ 设计约束：

1. **结构化字段一律"单行 JSON 子串"**（`json-list` / `json-obj`）：`_render_scalar`（`gates.py:152-157`）会把含 `{`/`"`/`,` 的值自动单引号包裹，解析回原串，再由两侧各自的 JSON 解析器解读。**不得**依赖 YAML 嵌套（会让两侧手写解析器失效）。
2. **列表字段只新增一个具名白名单**：`_LIST_FIELDS = {"context_refs", "evidence_refs"}`（两侧同步把特判从"单名"改"集合"）。其余"列表"用 `json-list` 表达。
3. 数字/ISO 字段沿用 `_check_iso`（`gates.py:370-379`）与 int 校验，不加新标量类型。
4. **不引入 pyyaml**（`gates.py:38-45` 已声明第三方 yaml 不允许）⇒ JSON 子串是唯一低成本的正交编码。

### D2 — 格式与兼容性

#### D2.1 新字段如何加入而不破坏既有解析

| 规则 | 内容 | 依据 |
|---|---|---|
| R1 只增不改 | 不改既有 12 字段的语义/取值域；不重排前 12 项；`stage`/`key` 不得复用 | P-018/P-019：语义变更牵动既有消费点（`_gate_open` 用 `context_refs` 去重、`_resume_credits` 靠 `key`、`_stage_closure` 靠 `status_of`） |
| R2 一律可选 | 新字段不进 `_REQUIRED_FIELDS`；老文件缺字段仍可 `parse()` 成功 | `gates.py:86-89`；`_to_gate` 的 `fields.get` 路径 `:426-460` |
| R3 两侧同序同集 | `FRONTMATTER_FIELDS`（`gates.py:68-81`）与 `GATE_FRONTMATTER_FIELDS`（`status-model.ts:572-587`）逐项同序；`GateRecord`（`:587-597`）按需扩字段 | 未知字段两侧都抛错（`:345-347` / `:660-661`）⇒ 漏一侧 = 一侧停摆 |
| R4 渲染顺序 | 底座 12 项原位；`gate_schema` 紧跟 `id`；v2 决策块插在 `context_refs` 之后、`status` 之前（`status/answered_at/answered_by/note` 是**回答块**，`gate-writer.ts:101-133` 按名重写，顺序不影响） | `gates.py:159-200`；`gate-writer.ts:101-133` |
| R5 老文件 = v1 | 缺 `gate_schema` ⇒ 按 1 处理；渲染器对 v1 文件**不报** missing（只报 pending 门的必须面） | 见 §D4 告警范围 |
| R6 新文件被老代码读 = 硬失败 | 老 conductor/TS 读新文件会 `GateFormatError`；TS `parseGateFile` 抛错但**面板不受影响**（`scanPendingGate` 是宽松行扫，忽略未知行，`monitor.ts:150-178`） | 设计意图：宁可响亮失败，不可静默错读 |

#### D2.2 是否需要 schema 版本字段 —— 需要，但要"文件级可选标记"而不是"强制块"

- **结论：加 `gate_schema`（#26），缺省 = 1（legacy），新文件写 2。** 理由三条：
  1. **区分"老文件"与"新文件被剥字段"**：没有版本标记时，渲染层无法判断 `reason_code` 缺失是历史文件还是被人删掉；doctor 的 `missing_fields` 会淹没在 34 个历史文件里。
  2. **让降级响亮**：老 conductor 遇到新文件本来就因未知字段抛错（R6）；`gate_schema: 2` 让这条错误**可被读取者直接归因**（"这是 v2 文件、我的 parser 只到 v1"），而不是"某个不认识的字段名"。
  3. **给 doctor 一个可枚举的迁移面**：`schema_versions: {"1": 34, "2": 0}` 是机器可读的迁移进度。
- **代价与边界**：`gate_schema` 本身对老解析器也是未知字段（失败点与其它新字段相同，不额外加成本）；**不做**"全局 schema 文件"或"重复校验块"；**不做**历史回填（34 个已答门永保 v1，见数据缺口 G-D6-1）。
- **反面方案被否**：靠"字段存在性启发式"判版本 ⇒ 无法区分剥离与历史，且 doctor 无法限定告警范围。

#### D2.3 before / after（真实文件 JC `gate-0008`，示意不落盘）

**before（逐字，真实文件 `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0008.md`，656 B）**：

```markdown
---
id: gate-0008
kind: stage-close
stage: 1
key:
created_at: 2026-09-26T04:37:27+00:00
created_by: conductor
question: 'Stage 1 全部 key 已终态，闭环 dossier 已写入 .agenticdoc/_autopilot/stages/stage-1-close.md——确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理'
context_refs:
  - stage-1
status: pending
answered_at:
answered_by:
note:
---
```

**after（示意：conductor 在 `conductor.py:649-655` 补写 v2 块；**不修改真实文件**）**：

```markdown
---
id: gate-0008
gate_schema: 2
kind: stage-close
stage: 1
key:
created_at: 2026-09-26T04:37:27+00:00
created_by: conductor
question: '……（逐字同 before，不改）……'
context_refs:
  - stage-1
reason_code: stage:all-keys-terminal
subject_sha256: 18e3fec0133fd4c6f39f24f52f795f7db080df489f8c2fdd75eec29f622b9c4f
evidence_refs: '["gate-dossier:_autopilot/stages/stage-1-close.md#18e3fec0133f@1790126702018359200", "l3-verdict:crash-analysis/l3-verdict.txt", "l3-verdict:plugin-ui/l3-verdict.txt", "l3-verdict:rag-context/l3-verdict.txt"]'
verdicts_final: '[{"key":"llm-router","verdict":"none","source":"l3-verdict.txt","suspect":true}, {"key":"crash-analysis","verdict":"meets","source":"l3-verdict.txt"}]'
open_items: '[{"kind":"verdict-none","key":"llm-router","item":"l3-verdict.txt absent","disposition":"unknown (no field)"}]'
observed_at: 2026-09-26T04:37:27+00:00
evidence_anchor_mtime_ns: 1790126702018359200
expires_at:
default_action: escalate-to-human
status: pending
answered_at:
answered_by:
note:
---
```

> **为什么这个 before/after 有价值**：JC `gate-0008` 是 **2026-09-26T04:37:27 重放**出来的门（stage 1 在 09-17 已 closed，被 `_consumed_gate_ids` 的 timeline 轮转丢失重新打开）；它的 dossier 是 **2026-09-11T20:25:02Z** 的旧文件（与 `gate-0005` 同刻），且 dossier 里 `llm-router` 的 verdict 是 `none`（该 key 无 `l3-verdict.txt`，本卡实测）。⇒ 漂移标记（D5）与 `open_items`（F12）在**这一门上是真实可触发的**：证据体 15 天前、`subject_sha256` 与 mtime 都指向旧版本。

#### D2.4 升级/降级矩阵

| 场景 | Python conductor | TS 面板 | TS `/autopilot gates` | 处置 |
|---|---|---|---|---|
| 老文件 + 新代码 | 解析成功（可选字段缺失） | 渲染成功（哨兵/省略） | 渲染成功（哨兵） | 正常；doctor 只在 pending 门报 missing |
| 新文件 + 新代码 | 正常 | 正常 | 正常 | 目标态 |
| 新文件 + **老** conductor | `GateFormatError` ⇒ timeline `config` + 跳过 tick（`:334-336`） | 面板照常（宽松扫描忽略未知行） | 报错进 `errors[]` 并 warning（`status-model.ts:739-777`、`console.ts:197`） | **响亮失败**；`gate_schema: 2` 给出归因 |
| 新文件 + 老 TS 面板 | 不受影响 | 不退化为"静默错值"（只少显示新字段） | 显式 warning | 可接受 |

### D3 — 三层呈现契约（落地设计）

#### D3.0 现状对照（逐字）

| 层 | 渲染位置 | 现在显示什么（逐字模板） | 缺什么 |
|---|---|---|---|
| A 面板 | `monitor.ts:644-654`；`MONITOR_LINE_MAX=110` `:61`；`trunc` `:531-533` | 多门：`gates: {N} pending - {id} ({kind}), … -> /autopilot gates`；单门：`gates: 1 pending - {id} ({kind}) -> /autopilot gate {id} approve\|reject` | **只有 `id (kind)`**：无 `created_at`/已等待/scope/reason/impact/默认与到期。根因在数据侧：`MonitorGate`（`:89-96`）只有 `id/kind/stage/key`，`scanPendingGate`（`:150-178`）只扫这 5 个名字 ⇒ **面板物理上无法显示等待时长** |
| B `/autopilot gates` | `console.ts:182-198`；`GateRecord` `status-model.ts:587-597`；`parseGateFile` `:630-736` | 每门 2 行：`{id} [{kind}] {stage=}{key=} — {question} (created {iso})` + `    answer: /autopilot gate {id} approve\|reject [--note <text>]  ({path})` | 无 `context_refs`/`note`/影响面/证据/后果/默认与到期；`GateRecord` **不含 `context_refs`** |
| C `mw doctor` | `mw_common.py:2022-2064`（`_doctor_autopilot`）、`:2067`（`_doctor_issues`）、`:2177`（注册）、`:2282-2287`（文本行）、`mw.py:524-525`（JSON 出口） | autopilot 段字段 = `path/exists/xkey_repair/xkey_verify_cmd/xkey_verify_timeout_s/xkey_verify_cwd/xkey_verify_argv/xkey_verify_missing/origins/diagnostics/error` | **零 gate 内容**：无 pending 数、无 id、无等待、无 parse 错误、无漂移 |

#### D3.1 层 A — 面板：每门 1 行，≤110 列

- **渲染位置**：`monitor.ts:644-654`（gate 块）；配套改动点：`MonitorGate`（`:89-96`）加 `createdAt: string|null`、`scanPendingGate`（`:150-178`）扫 `created_at`，`renderMonitorLines`（`:557+`）用新模板。
- **行模板（`|` 分隔、字段有固定序）**：
  `gates: 1 pending - {id} [{kind}] {scope} {age} {reason_class} {impact} -> /autopilot gate {id} approve|reject`
  多门时退化为**每门一行**（今天一门一行都做不到）；行首 `gates: {N} pending` 只在首行，其余行用 `  · ` 缩进（与 attention 行同风格 `:604-626`）。
- **字段来源（全部机器抽取，D1）**：

| # | 字段 | 模板 | 约束 | 来源 |
|---|---|---|---|---|
| 1 | `id` | `gate-\d+` | ≤10 字符，**不可截断** | gate 文件 `id` |
| 2 | `kind` | `[{kind}]` | 6 值闭集，≤16 | `kind`（`gates.py:54-61`） |
| 3 | `scope` | `stage=N` 或 `key=<K>` | N ≤2 位；K 超长时**尾部保留**截断至 26 字符 | `stage`/`key` |
| 4 | `age` | `{n}m` / `{n}h` / `{n}d` | ≤6 | `derived(now-created_at, created_at)`（`formatDuration` `monitor.ts:536-542`） |
| 5 | `reason_class` | 闭集 token（同 #1 的 `reason_code` 渲染形） | ≤26 | `reason_code`；**缺失时省略整个 token**，不从 `question` 反解 |
| 6 | `impact` | `blocks={n}keys` / `blocks=stage-close` / `blocks=all` | ≤22 | `derived(dependency_graph, roadmap status)` |
| 7 | 应答入口 | `-> /autopilot gate {id} approve\|reject` | 固定串，**必须完整** | TS 常量（`console.ts:195/208`） |
- **长度与截断规则（D3）**：整行 ≤ `MONITOR_LINE_MAX`（110，复用 `monitor.ts:61`）。**溢出时按整字段丢弃**，顺序 = `impact → reason_class → age → scope`（`id`/`kind`/应答入口永不丢）；仍超长时只对 `key` 做**尾部保留**截断（保文件名/尾段 + `…`），**不**用现有 `trunc`（`:531-533` 是头保留，会把 `key` 尾巴切掉）。
- **机器校验**：逐行 `len(line) ≤ 110`；`id` 与 `approve|reject` 子串必在；`age` 与 `created_at` 复算一致；`key` 截断时以 `…` 结尾且尾部等于原 `key` 的后缀。

#### D3.2 层 B — `/autopilot gates`：每门**恰好 13 行**、序固定、每行 ≤110 列

- **渲染位置**：`console.ts:182-198`（`cmdGates`，改用 `parseGateFile` 的严格结果 + 新字段；`GateRecord` 需扩字段 `status-model.ts:587-597`）；门目录扫描 `status-model.ts:739-777`。
- **与 RQ-14 的差异（本卡修正）**：RQ-14 的 L6/L8/L11/L12 是"≤6/≤3/≤3/≤5 行"⇒ **卡片高度可变**，与 AC-026 的"固定 13 行序"矛盾。本卡规定**每条逻辑行恰好 1 物理行**：列表类内容聚合成字符串（`,` 连接 + `+N more`），溢出走 D3 截断。**收益**：行数恒定 ⇒ 可直接断言 `total_lines == 1 + 13*pending_count`。
- **13 行序与来源**：

| 行 | 模板 | 上限 | 来源（锚点） |
|---|---|---|---|
| L1 | `gate-0008 [stage-close] stage=1 created=2026-09-26T04:37:27Z waited=3.9h` | 1 行 ≤110 | `id/kind/stage/key/created_at`；`waited=derived(now-created_at)` |
| L2 | `Q: {question 逐字}` | 1 行；超长头部保留 + `… (full: {path})` | `question` |
| L3 | `A: approve = {效果} (reversible: {yes/no}) \| R: reject = {效果} (reversible: {yes/no})` | 1 行（两段合一行） | **代码派生固定表**（per kind，`conductor.py:2273/2295/2363/348-384/994-998/2083-2111/2735-2741`）+ `default_action`（缺失 ⇒ `unknown (no field)`）。**唯一现成先例**：`monitor.ts:624` 的 `(resume grants one round)` |
| L4 | `goal: {stage goal 逐字} \| goal_sha256={…} \| proposal_sha256={…} \| roadmap_validation={…}` | 1 行；goal 头 100 字符 | `_roadmap.md > goal:`（`roadmap.py:256-259`）；#12/#13/#11 |
| L5 | `reason: {reason_code} count={n} src="{context_refs[1] 逐字}" \| verdict: l3={meets/below/none}` | 1 行；`src` 头 80 字符 + 锚点 | `reason_code`；`context_refs[1]`（逐字引用，D2/D6）；`l3-verdict.txt` |
| L6 | `evidence: {path} ({bytes}B, sections=[…], mtime={iso}){ DRIFT?}` ×N → 聚合成一行 + `+N more` | 1 行 ≤110 | `evidence_refs` + `os.stat` + `^## ` 扫描；`observed_at`/`anchor_mtime` |
| L7 | `impact: downstream={n} keys [{…≤5}] \| stage-close: {blocked/na} \| next-stage: {blocked/na} \| roadmap: {active/halted}` | 1 行 | `dependency_graph`（`roadmap.py:479`）+ `_stage_closure`（`conductor.py:616-656`）+ `> status:` |
| L8 | `history: {gate-id} [{kind}] {scope} {status} {answered_at}; …` | 1 行 | **门目录扫描**（按 `kind+stage` 或 `kind+key` 分组；一次 `os.listdir` + 现成 parser） |
| L9 | `default: {default_action/none} \| ttl: {expires_at/none(no field)}` | 1 行 | #24/#22；今天恒为 `none(no field)`（如实输出） |
| L10 | `budget: loop={loop} used={used_rounds}/{round_limit} credits={credits_used}` | 1 行 | #3-#6；缺 ⇒ `unknown (no field)` |
| L11 | `constraints: {constraints 逐字} \| prior: [{gate-id}] {前序 note 逐字}` | 1 行；每条 ≤80 字符 | #14（人写）；前序同 scope 门的 `note`（**逐字子串**） |
| L12 | `open-items: {open_items 逐字}` 或 `open-items: unknown (no field)` | 1 行 | #9；dossier 5 列（`conductor.py:722-750`） |
| L13 | `answer: /autopilot gate {id} approve\|reject --note <text>  expected: human` | 1 行 | TS 常量（`console.ts:195/208`）；`answer_source`（缺失 ⇒ 不可推定，显示 `expected: unknown`） |
- **截断规则**：路径类（L5/L6）**尾部保留**；散文类（L2/L4/L11）**头部保留** + `…`；两者都带完整锚点（`path` 或 `path:Lx-Ly`）；**禁止**中间省略、**禁止**跨行折行（折行破坏"恰好 13 行"）。
- **机器校验**：`lines.length == 1 + 13 * pending.length`（含 `N pending gate(s):` 头行）；每行 ≤110；对 fixture 逐字段 `assert rendered == source_value` 或 `assert value in source_text`（D2）。

#### D3.3 层 C — `mw doctor` 的 gate 段（JSON）

- **渲染位置**：新增 `mw_common._doctor_gates(project_dir)`，紧邻 `_doctor_autopilot`（`mw_common.py:2022-2064`）；在 `doctor_report` 组装处注册（仿 `:2177` 的 `report["autopilot"] = …`）；JSON 出口复用 `mw.py:524-525`。
- **形状（同字段名 + source 标注，D1/D7）**：

```json
"gates": {
  "dir": "<project>/.agenticdoc/_autopilot/gates", "exists": true,
  "total": 8, "pending_count": 2, "schema_versions": {"1": 8, "2": 0},
  "parse_errors": [{"path": "...", "error": "..."}],
  "pending": [{
    "id": "gate-0008", "kind": "stage-close", "scope": "stage=1",
    "created_at":  {"value": "...", "source": "gates/gate-0008.md:created_at"},
    "waited_s":    {"value": 14133, "formula": "now - created_at", "inputs": ["now", "gates/gate-0008.md:created_at"]},
    "reason_code": {"value": "stage:all-keys-terminal", "source": "gates/gate-0008.md:reason_code"},
    "impact":      {"value": "downstream=1 keys [e2e-validation]", "formula": "closure(depends_on, status)", "inputs": ["_roadmap.md:Keys", "_roadmap.md:status"]},
    "history":     [{"gate_id": "gate-0001", "kind": "stage-confirm", "scope": "stage=1", "status": "approved", "answered_at": "2026-09-11T06:20:38+00:00"}, {"gate_id": "gate-0005", "kind": "stage-close", "scope": "stage=1", "status": "approved", "answered_at": "2026-09-17T12:42:00+00:00"}],
    "evidence":    [{"path": "_autopilot/stages/stage-1-close.md", "bytes": 1068, "sha256": "18e3fec0133f...", "mtime": "2026-09-11T20:25:02Z", "drift": true}],
    "default_action": {"value": null, "sentinel": "unknown (no field)"},
    "expires_at":     {"value": null, "sentinel": "unknown (no field)"},
    "answer_entry":   {"value": "/autopilot gate gate-0008 approve|reject --note <text>", "source": "console.ts:195/208"}
  }],
  "missing_fields": [{"id": "gate-0008", "fields": ["reason_code", "expires_at", "default_action"]}],
  "drift": [{"id": "gate-0008", "path": "...stage-1-close.md", "mtime": "2026-09-11T20:25:02Z", "created_at": "2026-09-26T04:37:27+00:00"}],
  "replayed": [{"id": "gate-0008", "prior_gate": "gate-0005", "kind": "stage-close", "scope": "stage=1"}],
  "error": null
}
```

- **规则**：JSON 层**不做截断**（D3 的长度约束只属于文本层 A/B）；每个标量/派生量都带 `source` 或 `formula+inputs`（D1/D7）；填不出的值统一 `"value": null, "sentinel": "unknown (no field)"`（D4），**不省略键**（省略会让消费者误判"无此概念"，与"存在但为空"混淆）。
- **机器校验**：对 fixture 断言键集与 `sentinel` 字面量；`waited_s` 可用 `created_at` 复算（`|差| ≤ 1s`）。

#### D3.4 D1-D7 判据 × 三层（满足方式 + 机器校验）

| 判据 | 层 A（面板） | 层 B（卡片） | 层 C（doctor JSON） | 机器校验 |
|---|---|---|---|---|
| **D1 白名单 + 来源三元组** | 渲染器内置 `FIELD_SOURCES`（字段 → `file:field` 或 `derived(formula,inputs)`）；表外字段不渲染 | 同 A，逐行有固定来源列（本卡表格即该表） | 每个值节点自带 `source` 或 `formula+inputs` | 对 fixture 断言：渲染出的每个 token 都能在 `FIELD_SOURCES` 找到；或断言 JSON 每个叶子有 `source` XOR `formula` |
| **D2 逐字锚定** | 面板无散文值（最短面，天然满足） | `question`/goal/`note`/`constraints` 抄写处 `assert value in source_text`，失败渲染 `MISMATCH(anchor)` | 同 B，且带 `mtime`/`bytes`/`sha256[:12]` | fixture：篡改源文件后渲染必出 `MISMATCH`，不输出近似文本 |
| **D3 截断规则** | 整字段丢弃优先（顺序 impact→reason→age→scope）；`key` 尾部保留 | 路径尾部保留 / 散文头部保留，均带 `…` + 完整锚点，不折行 | 不截断 | 断言 `len(line) ≤ 110`；`key` 截断时 `rendered.endswith(key[-k:])`；反向断言无 `…` 夹在 token 中间 |
| **D4 禁 LLM 自由生成** | 渲染路径无模型调用；缺字段 ⇒ 省略或 `unknown (no field)` | 同 A；L3/L9 的固定表由代码常量生成 | 缺值统一哨兵 | 源码级：`monitor.ts` / `cmdGates` / `_doctor_gates` 不 import 任何 model/dispatch（grep 断言）；行为级：fixture 缺字段 ⇒ 输出**精确等于** `unknown (no field)` |
| **D5 漂移标记** | 面板不渲染漂移（列宽不足）——**显式声明不做**，并给 `-> /autopilot gates` 指路 | L6 追加 `DRIFT(mtime=…, gate_created=…)` | `evidence[].drift=true` + `drift[]` 汇总 | fixture：证据 mtime > `created_at` ⇒ 必出 `DRIFT(`；反向 fixture ⇒ 无 |
| **D6 `note` 不作派生输入** | 不用 `note` | `note` 只在 L11 作**逐字引用**（带 `gate-id`/`answered_at`/`bytes`） | `quote` 节点带 `verbatim=true` + `source` | 断言：`derived(...)` 的 `inputs` 永不含 `note`；计数类字段（如 `out_of_band_actions` 条数）不得由 `note` 计算 |
| **D7 数字带公式** | 文本层仅"固定模板 + 复算"（列宽不允许打印公式） | 同 A（模板固定即公式固定） | `waited_s`/`impact` 等显式 `formula+inputs` | 对 A/B：测试内按公式复算 == 渲染值；对 C：存在 `formula` 与 `inputs` 且可复算 |

> **"禁 LLM"与"漂移"的机器校验落点**（题目重点）：
> - **禁 LLM**：分两级 —— (i) **源码级**断言三个渲染模块不引用任何模型/dispatch 面（`monitor.ts` 的 import 块 `:35-46` 无 dispatch；`cmdGates` `console.ts:182-198` 无模型调用；`_doctor_gates` 只读文件）；(ii) **行为级**断言缺字段时输出**唯一哨兵字面量** `unknown (no field)`，而不是任何自然语言变体。两者一起才排除"用 LLM 兜底填得像真的"。
> - **漂移**：判据 `mtime(<evidence_refs 指向的文件>) > created_at(<门>)`（RQ-14 D5 的原式），层 C 输出 `drift=true` + 明细；层 B 在 L6 打 `DRIFT(...)`；**层 A 明确不做**（列宽物理不足），但必须有指路（`-> /autopilot gates`）与 doctor 兜底 ⇒ 三层合起来仍满足 D5 的"必须可见"。

#### D3.5 三层 worked preview（JC `gate-0008`，全部可复算）

**层 A（1 行，≤110）**：

```
gates: 1 pending - gate-0008 [stage-close] stage=1 3.9h stage:all-keys-terminal blocks=1key -> /autopilot gate gate-0008 approve|reject
```

（`3.9h = 2026-09-26T08:33Z − 04:37:27Z`；`blocks=1key` 来自 Stage 2 的 `e2e-validation` 依赖四个 key 中的全部。）

**层 B（恰好 13 行）**：

```
L1  gate-0008 [stage-close] stage=1 created=2026-09-26T04:37:27Z waited=3.9h
L2  Q: Stage 1 全部 key 已终态，闭环 dossier 已写入 .agenticdoc/_autopilot/stages/stage-1-close.md——确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理 (full: <gate path>)
L3  A: approve = stage 1 → closed，并开下一 stage 的 stage-confirm 门 (reversible: no) | R: reject = stage 1 → halted，需人工改 roadmap 才能继续 (reversible: no)
L4  goal: 一期全部本地可闭环验证，不依赖 Rider 实机… | goal_sha256=unknown (no field) | proposal_sha256=unknown (no field) | roadmap_validation=unknown (no field)
L5  reason: stage:all-keys-terminal count=4 src="stage-1" | verdict: l3=none
L6  evidence: _autopilot/stages/stage-1-close.md (1068B, sections=[Keys], mtime=2026-09-11T20:25:02Z) DRIFT(mtime=2026-09-11T20:25:02Z, gate_created=2026-09-26T04:37:27Z) +4 more
L7  impact: downstream=1 keys [e2e-validation] | stage-close: this gate | next-stage: na (stage 2 running) | roadmap: active
L8  history: gate-0001 [stage-confirm] stage=1 approved 2026-09-11T06:20:38Z; gate-0005 [stage-close] stage=1 approved 2026-09-17T12:42:00Z
L9  default: unknown (no field) | ttl: none(no field)
L10 budget: loop=unknown (no field) used=unknown (no field)/unknown (no field) credits=unknown (no field)
L11 constraints: unknown (no field) | prior: [gate-0005] 用户批准（2026-09-17）：Stage 1 一期（本地闭环验证）收官…
L12 open-items: [{"kind":"verdict-none","key":"llm-router","item":"l3-verdict.txt absent"}]
L13 answer: /autopilot gate gate-0008 approve|reject --note <text>  expected: unknown
```

> 三条**从今日面板完全看不见**的机器事实：**L8 的重放**（本门是 stage 1 的第二次收口）、**L6 的 15 天漂移 + llm-router verdict 缺失**、**L9 的"无默认动作/无到期"**。这就是 AC-026 要的"简明扼要"与 AC-019 的机器告警面。

**层 C**：见 §D3.3 的 JSON 样例（同一门的真实值）。

### D4 — `mw doctor` 的 gate 段设计（对齐 `_doctor_autopilot` 范式）

#### D4.1 段字段（`report["gates"]`）

| 字段 | 类型 | 含义 | 来源 |
|---|---|---|---|
| `dir` / `exists` | str / bool | gate 目录（**只读，绝不创建**，与 `_doctor_autopilot` `:2025-2034` 同纪律） | `gates_dir(project)`（`conductor.py:67`） |
| `total` / `pending_count` | int | 门总数 / pending 数 | 目录扫描（`gates.enumerate` 语义） |
| `schema_versions` | `{str:int}` | `gate_schema` 分布（缺失记 `"1"`） | #26 |
| `parse_errors` | `[{path,error}]` | 解析失败的门与错误串 | `gates.GateFormatError`（`gates.py:107-115`）/ TS `errors[]` |
| `pending[]` | 见 §D3.3 | 每门的渲染面同字段 + `source`/`formula` | 层 B/C 同源 |
| `missing_fields[]` | `[{id,fields}]` | **仅 pending 门**缺失的 v2 决断字段 | 本卡字段清单 |
| `drift[]` | `[{id,path,mtime,created_at}]` | 证据与门的时点异常（`subject_sha256` 不匹配也进这里） | `evidence_refs` + `os.stat` |
| `replayed[]` | `[{id,prior_gate,kind,scope}]` | 同 scope 已有已答门（重放候选） | 门目录扫描（L8 同源） |
| `error` | str / null | 段级异常（对齐 `_doctor_autopilot` 的 `error` 键 `:2030/2042-2044`） | — |

#### D4.2 告警条件与修复串（`_doctor_issues`，`mw_common.py:2067`；autopilot 范式 `:2099-2104`）

| # | 条件 | 级别 | 消息（含修复串） |
|---|---|---|---|
| I1 | `parse_errors` 非空 | **issue** | `gate file invalid: <path> (<error>) - fix the frontmatter or move the file out of _autopilot/gates`（今天只在 timeline 留 `config` 事件 `conductor.py:334-336` + console warning，doctor 静默 ⇒ 这是"零 gate 内容"缺口的第一个补面） |
| I2 | pending 门缺 `expires_at` 或 `default_action` | **issue** | `gate <id> (<kind>, <scope>) pending since <created_at> with no expires_at/default_action - set the default action or answer the gate (AC-019: no implicit permanent retention)` |
| I3 | pending 门 `waited_s > 24h`（`>72h` 升级为 issue，否则 suggestion） | suggestion / **issue** | `gate <id> pending <n>h - run '/autopilot gate <id> approve\|reject --note <text>' or '/autopilot gates' to review`（实测 JC `gate-0007` = 9.5 天） |
| I4 | `drift[]` 非空（pending 门） | suggestion | `gate <id> evidence <path> is older/newer than the gate (mtime <iso> vs <created_at>) - re-derive the evidence before answering` |
| I5 | `replayed[]` 非空 | **issue** | `gate <id> repeats (<kind>, <scope>) of answered <prior_gate> - check gate consumption (D1) before answering`（JC `gate-0008` 的真实形态） |
| I6 | `gate_schema=2` 的 pending 门缺决断字段 | suggestion（**不阻塞**可答性） | `gate <id> is schema 2 but missing <fields> - the conductor fills them on the next write; rendering shows 'unknown (no field)'` |
| I7 | 无 pending、无 `parse_errors`、无 `drift` | 无 | **不输出行、不报 issue**（零扰动，对齐 `_doctor_autopilot` 文本行 `:2282-2287` 的"仅 fail-loud 时输出"） |
| I8 | `pending_count == 0` 且 `total > 0` | 信息（仅 JSON） | 不产生 issue；`gates: 0 pending (<total> answered)` 只在 `--json` 里可见，文本层保持安静 |

文本层：`format_doctor_text` 增一行（位置仿 `:2282-2287`）——`gates: {pending} pending ({oldest} oldest, {n} parse error(s), {n} drift)`，只在 I1-I6 任一命中时输出。exit code 由 `report["summary"]["healthy"]`（`mw.py:531`）驱动，无需新机制。

### D5 — VC 候选（≥4 条，全部机器可判）

| VC | 断言（可直接落成测试） | 覆盖 |
|---|---|---|
| **VC-D6-01 面板逐字子串 + 行长** | 用 fixture 门（含 JC `gate-0008` 的真实字段值）跑 `renderMonitorLines`：① 每一行 `len ≤ 110`；② 渲染行必须包含 `gate-0008`、`stage-close`、`approve\|reject` 三个**逐字子串**；③ `age` 与 `created_at` 按公式复算一致；④ 对超长 `key`，`key` token 必须以 `…` 结尾且其前缀/后缀逐字等于原值尾部 | 层 A、D1/D2/D3/D7 |
| **VC-D6-02 卡片高度恒定 + 无字段哨兵** | `/autopilot gates` 对 N=1/3 个 pending 门输出 `1 + 13*N` 行；对"全部 v2 字段缺失"的 fixture，L9/L10/L12 行**逐字包含** `unknown (no field)`（`assert "unknown (no field)" in line`），且 `assert not re.search(r"(大概\|可能是\|推测)", line)` | 层 B、D3/D4 |
| **VC-D6-03 doctor 必报 + 修复串** | ① fixture 门文件删掉 `created_at` ⇒ `report["gates"]["parse_errors"]` 非空 **且** `summary.issues` 里存在包含 `fix the frontmatter` 的串（`mw.py` exit code 变 1）；② fixture pending 门缺 `expires_at`/`default_action` ⇒ issue 含 `no expires_at/default_action` **且**含 `AC-019`；③ 全绿项目（无 pending、无错）⇒ `report["gates"]` 存在但 `summary.healthy == true`、文本无 `gates:` 行（零扰动） | 层 C、D4、AC-012/AC-019 |
| **VC-D6-04 漂移标记** | fixture：证据文件 mtime > 门 `created_at` ⇒ 层 B L6 含 `DRIFT(`、层 C `drift[]` 含该 `id` 且 `evidence[].drift == true`；反向（mtime 早于 `created_at`）⇒ 两处都**不含** `DRIFT`/`drift` | 层 B/C、D5 |
| **VC-D6-05 禁 LLM（源码级 + 行为级）** | ① 源码断言：`monitor.ts`、`console.ts` 的 `cmdGates` 路径、`mw_common._doctor_gates` 不出现模型/dispatch 引用（grep 断言这三个渲染函数体内 `dispatch`/`model`/`provider` 零命中）；② 行为断言：缺字段渲染出的**唯一**兜底字面量为 `unknown (no field)` | 层 A/B/C、D4 |
| **VC-D6-06 两侧镜像一致** | `GATE_FRONTMATTER_FIELDS`（TS）与 `FRONTMATTER_FIELDS`（Python）**逐项相等且同序**（含 `gate_schema` 位置）；同一 fixture 门文件在 `gates.parse`（Python）与 `parseGateFile`（TS）得到相同字段值（含 `json-list` 字段的解析结果） | §D2.1 R3 |
| **VC-D6-07 未知字段 fail-closed（两侧）** | fixture 门文件加一行 `bogus_field: x` ⇒ Python `gates.parse` 抛 `GateFormatError` 且消息含 `unknown frontmatter field 'bogus_field'`；TS `parseGateFile` 抛错且消息同构；conductor 侧 `_consume_answered_gates` 捕获后 timeline 出现 `config` 事件、tick 返回 False（corrupt 门不被静默接受） | `gates.py:345-347`、`status-model.ts:660-661`、`conductor.py:332-336` |
| **VC-D6-08 重放检测** | fixture = JC 真实形态（`gate-0001` stage-confirm stage 1 approved + `gate-0005` stage-close stage 1 approved + pending `gate-0008` stage-close stage 1）⇒ 层 B L8 含 `gate-0001` 与 `gate-0005` 两个逐字 id；层 C `replayed[]` 含 `{"id":"gate-0008","prior_gate":"gate-0005"}`；doctor issue 含 `check gate consumption` | 层 B/C、F1/F6 |

## 结论 → 决策映射

| 本次交付的设计 | 支撑的 AC / 需求 |
|---|---|
| §D1 合并字段清单（12 底座 + 26 新增，逐条真实写/读锚点 + 复用来源 + 缺失行为） | **AC-026** 的"字段级呈现契约 + 每字段长度约束与来源"；为 **AC-019**（`default_action`/`expires_at`）与 **AC-018**（`answer_source`/`auto_policy_id`）提供字段落点 |
| §D1.2 的 F9/F10/F3 无数据源标注 | AC-026 的"缺口清单"；把 RQ-12 的 23 字段与 RQ-14 的 14 项**显式断链**（不硬塞字段，避免 D4 违规） |
| §D1.3 P0/P1/P2 路线 | 给 plan 期一个**可分批**的落地序：P0 零 schema 风险（先补可观测性，对应 AC-012），P1 是本 key 的自动决策输入，P2 依赖 AC-014/018/019/029/030 |
| §D2 兼容性（R1-R6 + `gate_schema` + JC `gate-0008` before/after + 升级/降级矩阵） | AC-026 的"格式与兼容性"子项；P-021（两侧镜像）+ P-018/P-019（语义变更查消费点） |
| §D3 三层契约（含行/列断言 + D1-D7 × 三层矩阵） | AC-026 的三层呈现要求 + "判据 D1-D7"；AC-012（可观测性：面板 `created_at`/impact/doctor 段）；AC-022 的**读面**（重放可见性 L8/I5，不修 D1 守卫本身） |
| §D4 doctor gate 段（9 类字段 + 6 类告警 I1-I6 + 2 条零扰动规则 I7/I8 + 修复串） | AC-012 / AC-018（面板与 doctor 可见）/ AC-019（缺省告警）；对齐上一 key 的 `_doctor_autopilot` 范式 |
| §D5 8 条 VC | 供 verify 期直接落测试；每条都可在 AC-026 的"以 34 门回放自检"之外给出**逐字/长度/哨兵**级证据 |

**给 plan 期的硬前置顺序**（自证据推出，不是偏好）：① 两侧 parser 扩字段（R3/R6，含 `_LIST_FIELDS`）→ ② P0 渲染 + doctor 段（无 schema 风险，先让 JC 的 2 个 pending 门与重放/漂移可见）→ ③ AC-029 取证源优先级冻结 → ④ P1 字段 → ⑤ P2 字段。**若先做 P2 字段**（尤其 `write_scope`/`auto_policy_id`），渲染面会长期输出 `unknown (no field)`，等于把"缺失"伪装成"已设计"。

## 数据缺口

| # | 缺口 | 性质 | 为什么重要 | 需要什么才能补 |
|---|---|---|---|---|
| G-D6-1 | **历史 34 个已答门无法回填 v2 字段**（本卡实测 34 answered + 2 pending） | 无数据源（一次性） | 回放/三层渲染在历史门上必然大量 `unknown (no field)`；若 doctor 对已答门也报 missing，会产生 34 条假阳 | 明确"只对 pending 门报 missing/告警"（本卡 §D4 I6/I7）；历史门的字段补全**不做** |
| G-D6-2 | **F9 弃置代价无数据源**：`write_scope` 生产零命中（AC-014），`blast_radius` 只在 0 票据的 ticket JSON 里 | 前置缺失 | `stalled` 门的"reject 会丢掉什么"无法机器判；契约若给该字段会长期 `unknown` | AC-014 的机器可读写面声明先落地 |
| G-D6-3 | **F10 带外修复记录**（≥16/22 条 `stalled` approve）只在 `note` 散文；唯一可机器重算的样例是 E2 `gate-0006`（进程启动时间 vs 提交时间） | 半可补 | 不补则"approve = 机器复算通过"的误读无法被机器排除（RQ-10 风险 19） | 窗口强制填写 `out_of_band_actions`（人写），或另立"可重算的带外动作"白名单命令 |
| G-D6-4 | **`goal-change` 的 before-image 不存在**（FM untracked / JC 无 `.git` / 无框架快照） | 无数据源 | `goal_sha256_before`/`goal_diff` 写不出来；本卡只能设计与其它字段一致的 `unknown (no field)` 行为 | 变更时落不可变镜像（RQ-12 的"+1 非字段改动"） |
| G-D6-5 | **`verdicts_final` 的源覆盖 < 5/22 key**（`l3-verdict-provenance.json` 只覆盖 2026-09-26 之后的轮次；correction sidecar 只覆盖 E2 3 个 key） | 半可补 | `open_items`/`subject_sha256` 的可信度取决于此；JC `gate-0008` 今天就撞上 `llm-router` 无 `l3-verdict.txt` | AC-029 的取证源优先级冻结 + provenance 覆盖面扩展 |
| G-D6-6 | **`reason_code` 的 12 个 `mark_stalled` 调用点尚未分类**（`conductor.py:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941`） | 可补（设计输入） | 没有映射表，`reason_code` 只能写成自由文本，闭集判定失效 | 逐调用点给出"传什么码"的映射表（本卡只给闭集候选与写点） |
| G-D6-7 | **本卡无 `budget-exhausted` / `xkey-authorize` 生产样本**（三项目 0 实例） | 无样本 | 这两类的 L3 选项后果文本只能从代码读（`conductor.py:994-998`/`:2735-2741`），无法用真实门校验卡片渲染 | 影子模式样本（RQ-10 建议）或标注"文本来自代码、非历史" |
| G-D6-8 | **面板/卡片/doctor 三层都没有"当时谁在等"**（`> key-status:` 覆盖写，`roadmap.py:505`） | 无数据源（同 RQ-14 G1） | F8 只能算**结构**影响面；无人值守时"先答哪个"缺时间维输入 | 每 tick 落 `(in_flight, eligible_not_dispatched, key-status)` 快照 |
| G-D6-9 | **本卡未验证"13 行在 80 列终端下的可读性"**（只有长度断言，无 UX 样本） | 未实测 | 固定 13 行可能对窄终端不友好（但 AC-026 已定契约，本卡只保证机器可判） | 用 tmux 80 列实跑 `/autopilot gates`（按 AGENTS.md 的 tmux 流程） |

```
[VERIFY] D6(gate-schema-presentation): merged_fields=26(+12 existing) rq12_kept=23/23 d6_added=3[default_action(F13), out_of_band_actions(F10), gate_schema(version)] f14_coverage=11/14 no_data_source=[F3 options-are-code-only, F9 stake, F10 machine-readable] yaml_nesting=unsupported(gates.py:38-45; only context_refs is a list field gates.py:354-364) compatibility=additive-optional + two-sided-lockstep + gate_schema-default-1 failclosed=[parse:GateFormatError gates.py:345-347/status-model.ts:660-661 + conductor.py:332-336; render:'unknown (no field)'; decide:escalate-to-human] layers=[A monitor.ts:644-654 MONITOR_LINE_MAX=110 monitor.ts:61 MonitorGate-lacks-created_at monitor.ts:89-96 trunc-is-head-preserving monitor.ts:531-533; B console.ts:182-198 exactly-13-lines/gate fixes RQ14 L6/L8/L11/L12 variable-height conflict; C new mw_common._doctor_gates next to mw_common.py:2022-2064 issues mw_common.py:2067 autopilot-block :2099-2104 JSON-out mw.py:524-525] doctor_conditions=6(parse-error, no-expires/default, overdue>24h, drift, replayed, schema2-missing)+zero-perturbation worked_example=JC gate-0008(stage-close stage1 created 2026-09-26T04:37:27Z pending 3.9h dossier sha256[:12]=18e3fec0133f 1068B mtime 2026-09-11T20:25:02Z => DRIFT 15d llm-router verdict=none replay-of-gate-0005) vcs=8 sample=34 answered + 2 pending(JC) baseline=HEAD 191a069a4(code identical to 4ef71e053) wrote=.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-gate-schema-presentation-20260926.md
```
