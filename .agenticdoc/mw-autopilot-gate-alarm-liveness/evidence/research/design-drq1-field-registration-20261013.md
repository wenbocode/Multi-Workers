# DRQ-1｜字段注册与三读面贯通（冻结 40 名序 / `authorizes` 序外注册先例 / fail-closed 专项测试）

- Key: `mw-autopilot-gate-alarm-liveness`｜任务: T-05（DRQ-1）｜阶段: design｜性质: **只读取证**
- 唯一写入 = 本文件。所有计数/行号均为本机命令 + 逐行阅读产出（Python 3 / PowerShell / Node 侧为源码静态阅读，未跑 pytest/vitest，见末段）。
- 时间基准: 本机会话 2026-10-13（UTC+08），与 RQ-4 同批。

## 结论

**C1 — 冻结名序的精确边界**：唯一权威 = `packages/multi-workers/autopilot/gates.py:95-139` 的 `FRONTMATTER_FIELDS`（**40 名整** = 12 base `:97-108` + 26 v2 `:110-135` + 2 consumed `:137-138`），TS 逐字镜像 = `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:660-701` 的 `GATE_FRONTMATTER_FIELDS`。`blocker_class` **不得进这个元组**。硬红断言实际是 **4 个测试函数 / 5 条断言**（RQ-4 说的"4 处"）：`test_autopilot_gates.py:224`（+`:226-230` 键序与 `len(keys)==13`）、`test_autopilot_gate_schema_v2.py:143`（同函数 `:140-144` 还有 `fields[12:38]==V2_FIELDS`）、`test_autopilot_contract_guard.py:187`（+`:188` + `:194-196`）、`autopilot-gate-presentation.test.ts:227-228`（跨语言逐名相等）与 `:253`（`toHaveLength(40)`）。进序 = 至少这 4 个测试同时红。

**C2 — `authorizes` 先例 = 7 个代码登记点 + 3 个测试锁 + 1 个 materialize 写点**（Python 4 / TS 3）。`blocker_class` 是**标量**，**不能**塞进 `_JSON_LIST_FIELDS`：该集合的每个成员都会被 `optional_json()`（`gates.py:573-601`）/`jsonField()`（`status-model.ts:890-903`）按 JSON 解码，标量会直接抛 `GateFormatError`。必须新开一条**平行的标量扩展名集合**（Python `gates.py:159-174` 旁 + TS `status-model.ts:751-766` 旁），并在两处 parse 成员检查（`gates.py:507` / `status-model.ts:830`）各加**第三分支**。

**C3 — 漏注册一处的 blast radius 是"整条门禁队列"，不是"少读一个字段"**。任一 gate 文件带未注册名 ⇒ Python `gates.parse` 抛 `GateFormatError`（`gates.py:507`）⇒ `gates.enumerate`（`:744`）/`pending_gates`（`:770`）**整体抛**，conductor 的 `_remind_pending_gates`（`conductor.py:2692-2694`）与 `_apply_pending_decisions`（`conductor.py:509-512`）catch 后 `return`，`open_goal_change_gate` 路径（`conductor.py:2905-2908`）记 `config` 后返回 `"ok"` ⇒ **该 tick 的提醒 + 阶段跃迁 + stalled 审批全部停摆**；TS `listGates`（`status-model.ts:1003-1035`）把该 gate 从队列剔除并写 `errors`，console 每条命令尾部刷 warning，`mw doctor` 记 parse 错。**两侧必须同一次落地**：只改一边 = 同一文件两种说法（一侧报错、一侧静默通过）。

**C4 — 三读面改动清单（最小面）**：Python 写入端 **2 处**（`conductor.py:5307-5322` `mark_stalled.machine_fields`；`conductor.py:3072-3081` `_stamp_gate_defaults` 照 `reason_code` 抄一条闭集守卫）；Python 解析端 **4 处**（`gates.py:159-174` 新标量集、`:507` 第三分支、`:211-266` `Gate` 新字段默认 `None`、`:537-560` `_to_gate` 闭集校验 + `:638-676` 赋值）；TS **5 处**（`status-model.ts:751-766` 新集合、`:830` 第三分支、`:708-748` `GateRecord`、`:796-1000` `parseGateFile` 读取/校验、`:1333-1339` `GateView` 扩展）；monitor **3 处**（`monitor.ts:111-130` `MonitorGate`、`:234-290` `scanPendingGate` **必须显式加 `else if` 分支**、`:879-908` 渲染 token）。**零改动**：`gates.create()`（13 键渲染）、`gate-writer.ts:62 ANSWER_FIELDS`、`contract_guard.py`（只 `getattr(gate,"authorizes")`，不枚举名）。

**C5 — 缺省语义只能落"两段"**：**parser 保留 `None`**（Python `gates.py:546-552` 的 `optional()` 已满足；TS `status-model.ts:873-876` 的 `optional()` 返回 `null`；载体 = `Gate` 默认值 `:211-266` / `GateRecord` `:708-748`）；**判定层才折 `judgment`**：Python 落点 = `gate_facts` 的 `stalled` 分支（`conductor.py:6083-6091`）新增一个纯函数 `blocker_class_of(gate) -> "paperwork" | "judgment"`（`gate.blocker_class == "paperwork"` ⇒ paperwork，其余一切 ⇒ judgment），消费方 = `_auto_decide_one`（`conductor.py:6913`）→ `auto_decision_for_rule`（`conductor.py:5831`）；TS 落点 = 派生层而非解析层（`deriveStatusModel` 的 GateView 映射 `status-model.ts:1467-1475`、monitor collect `monitor.ts:419-435`）。**不能在解析层折**：折叠会消灭"文件里没写"与"显式写了 judgment"的唯一区分，而 AC-007 要求"显式 paperwork 才走确定性钩子"，这个"显式"必须可证；同时 `MISSING_FIELD_SENTINEL`（`status-model.ts:706` / `mw_common.py:2728`）的展示语义会被伪造，parser 又会把决策语义泄漏给 doctor/console 两个只读消费面。

**C6 — 存量普查修正 RQ-4 的 `34` 上界**：RQ-4 只扫了 `H:\git\*`（34）。把卡面点名的 `E:\CLI_workspace\FeatureMigrator` 纳入后，本机合计 **56**（E2Feature 26 / JCodingAss 8 / **FeatureMigrator 22**）= **v1 51 / v2 5**，`blocker_class` **0/56**；真实 `pending` 从 2 变 **3**（新增 `FeatureMigrator/gate-0022`，`kind=stalled`，**v1**，即本 key 背景里卡了 12h 的那个）。缺字段率仍 **100%**，结论不变、样本更大。

## 证据

### 1 冻结 40 名序：定义点、名单、硬红测试

命令（取定义块逐行）：

```powershell
(Get-Content packages\multi-workers\autopilot\gates.py)[94..143] | % -Begin {$i=95} -Process { "$i`t$_"; $i++ }
```

原始输出（节选，全块见卡面"证据"落盘命令）：

```text
95	FRONTMATTER_FIELDS: tuple[str, ...] = (
96	    # base (design 4.1)
97	    "id"
98	    "kind"
...
108	    "note"
109	    # v2 (design D1.1 1..26)
110	    "reason_code"
...
135	    "gate_schema"
136	    # consumption record (design D-004, outside the D1.1 26)
137	    "consumed_at"
138	    "consumed_seq"
139	)
```

- **名序定义**：`packages/multi-workers/autopilot/gates.py:95-139`（40 名 = base 12 (`id,kind,stage,key,created_at,created_by,question,context_refs,status,answered_at,answered_by,note`) + v2 26 (`reason_code,evidence_refs,loop,used_rounds,round_limit,credits_used,observed_at,verdicts_final,open_items,subject_sha256,roadmap_validation,proposal_sha256,goal_sha256,constraints,goal_sha256_before,goal_sha256_after,goal_diff,write_scope,blast_radius,answer_source,auto_policy_id,expires_at,evidence_anchor_mtime_ns,default_action,out_of_band_actions,gate_schema`) + consumed 2 (`consumed_at,consumed_seq`)）。
- **冻结 6 项必填**：`gates.py:146-152`（`_REQUIRED_FIELDS` + import-time assert，v2/扩展字段一律 optional）。
- **TS 镜像**：`status-model.ts:660-701`（`GATE_FRONTMATTER_FIELDS`，注释 `:655-659` 明说"item-for-item in the Python order"）。

4 个测试函数 / 5 条硬断言（逐行核实）：

| 文件:行 | 断言形态 |
|---|---|
| `packages/multi-workers/test_autopilot_gates.py:214`（函数）`:224` | `assert len(gates.FRONTMATTER_FIELDS) == 40`；`:226-229` `keys == [fields[0], "gate_schema", *fields[1:12]]`；`:230` `len(keys) == 13` |
| `packages/multi-workers/test_autopilot_gate_schema_v2.py:138`（函数）`:140`/`:141`/`:142`/`:143`/`:144` | `fields[:12]==BASE_FIELDS`；`fields[12:38]==V2_FIELDS`；`fields[38:40]==CONSUMED_FIELDS`；**`:143` `len(fields)==40`**；`:144` `len(set(fields))==40` |
| `packages/multi-workers/test_autopilot_contract_guard.py:185`（函数）`:186-196` | `:186` `len(_REQUIRED_FIELDS)==6`；`:187` `len(FRONTMATTER_FIELDS)==40`；`:188` `"authorizes" not in FRONTMATTER_FIELDS`；`:194` `len(keys)==13`；`:195-196` create() 不渲染 + `parse().authorizes is None` |
| `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:211`（用例）`:227-228` | `expect(pyFields).toEqual([...GATE_FRONTMATTER_FIELDS])`（子进程 dump Python 真值）；`expect(pyFields).toHaveLength(40)` |
| `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:249`（用例）`:253-255` | **`:253` `expect(GATE_FRONTMATTER_FIELDS).toHaveLength(40)`**；`:254` `not.toContain("authorizes")`；`:255` `GATE_JSON_LIST_FIELDS.has("authorizes")===true` |

⇒ 任何把 `blocker_class` 写进 `FRONTMATTER_FIELDS`/`GATE_FRONTMATTER_FIELDS` 的改动：上表 4 个测试函数同时红（长度、切片、键序、跨语言相等至少各命中一条）。

### 2 `authorizes` 序外注册先例：完整登记点与遗漏后果

命令：

```powershell
Select-String -Path packages\multi-workers\autopilot\gates.py -Pattern '^_JSON_LIST_FIELDS|^AUTHORIZES_ACTIONS|name not in FRONTMATTER_FIELDS|authorizes'
Select-String -Path packages\coding-agent\src\extensions\agent-team-loop\autopilot\status-model.ts -Pattern 'authorizes|GATE_JSON_LIST_FIELDS|includes\(name\)'
```

原始输出（关键行）：

```text
gates.py:160 _JSON_LIST_FIELDS = frozenset(
gates.py:168     # Recognized contract field outside FRONTMATTER_FIELDS (D-011); the
gates.py:180 AUTHORIZES_ACTIONS: frozenset[str] = frozenset({"retry", "contract-change"})
gates.py:263     authorizes: list[str] | None = None
gates.py:507     if name not in FRONTMATTER_FIELDS and name not in _JSON_LIST_FIELDS:
gates.py:660     authorizes_raw = optional_json("authorizes")
gates.py:669     {action for action in authorizes_raw if action not in AUTHORIZES_ACTIONS}
status-model.ts:652 export const AUTHORIZES_ACTIONS = ["contract-change", "retry"] as const;
status-model.ts:740     authorizes: string[];
status-model.ts:757 export const GATE_JSON_LIST_FIELDS = new Set([... "authorizes"])
status-model.ts:830 if (!(GATE_FRONTMATTER_FIELDS ... includes(name)) && !GATE_JSON_LIST_FIELDS.has(name)) {
status-model.ts:917 const authorizes = jsonStringList("authorizes");
status-model.ts:991 authorizes,
```

**`authorizes` 的 11 个登记/消费点（`blocker_class` 的逐项类比清单）**：

| # | 位置 (`path:line`) | 角色 | 漏了会怎样 |
|---|---|---|---|
| R1 | `gates.py:160-173` `_JSON_LIST_FIELDS` 含 `"authorizes"` | Python 结构化字段注册表（唯一声明名） | `parse` 成员检查（R3）失去许可 ⇒ 一切带该字段的文件 fail-closed |
| R2 | `gates.py:180` `AUTHORIZES_ACTIONS` | 值闭集 | 值不校验 ⇒ 任意 action 通过（语义漏洞，非 fail-closed） |
| R3 | `gates.py:507` `... and name not in _JSON_LIST_FIELDS` | **parse 成员检查（fail-closed 闸门）** | `unknown frontmatter field 'authorizes'` ⇒ 队列整体抛 |
| R4 | `gates.py:263` `Gate.authorizes` 默认 `None` | 载体 + 缺省语义 | `AttributeError`/无字段 |
| R5 | `gates.py:660-676` `_to_gate` 校验并赋值 | 类型 + 闭集校验 | 值可能越界；属性缺失 |
| R6 | `status-model.ts:652` `AUTHORIZES_ACTIONS` | TS 值闭集（Python 镜像） | 同上 |
| R7 | `status-model.ts:740` `GateRecord.authorizes` | TS 视图载体 | 视图拿不到 |
| R8 | `status-model.ts:757-765` `GATE_JSON_LIST_FIELDS` | TS 注册表 | 同 R1 |
| R9 | `status-model.ts:830` `&& !GATE_JSON_LIST_FIELDS.has(name)` | **TS parse 成员检查** | 同 R3（`parseGateFile` 抛，`listGates` 记 errors 并剔除） |
| R10 | `status-model.ts:917-924` `jsonStringList` + 闭集 | 值校验 | 同 R2/R6 |
| R11 | `status-model.ts:991` 返回 `authorizes` | 结果接线 | 解析通过但值为空 |

**测试锁（3 个）**：

| 文件:行 | 断言 |
|---|---|
| `packages/multi-workers/test_autopilot_contract_guard.py:101-127` | `assert "authorizes" in gates._JSON_LIST_FIELDS`（`:102`）；闭集 2 值；越界抛 |
| `packages/multi-workers/test_autopilot_contract_guard.py:130-139` `test_vc012_array_value_requires_json_list_registration` | **"注册是承重的"反事实锚**：docstring 逐字 "removing it from `_JSON_LIST_FIELDS` turns this red"；`:136` 再断言成员资格 |
| `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:284-302` | **跨语言锁**：子进程 dump `gates._JSON_LIST_FIELDS` 与 `AUTHORIZES_ACTIONS`，`:300-301` `toEqual` 双向相等 |

**materialize 写点（不在 `create()`）**：`conductor.py:3111-3130` `_gate_default_fields` 返回 `{"default_action": ..., "authorizes": "[]"}`，由 `_stamp_gate_defaults`（`conductor.py:3072-3081`）经 `_rewrite_gate_fields`（`conductor.py:6559-6585`）落盘；测试 = `test_autopilot_done_contract_guard.py:443-469`（`:451` `"\nauthorizes: []\n" in raw`，`:459` 13 键且不含 authorizes）。`create()` 的 13 键渲染（`gates.py:283-315`，测试 `test_autopilot_gates.py:230`）与 `gate-writer.ts:62 ANSWER_FIELDS` 都不含 `authorizes` 生成逻辑。

**`blocker_class` 的类比差异**：`authorizes` 是 JSON 数组 ⇒ 复用 `_JSON_LIST_FIELDS`；`blocker_class` 是**标量闭集** ⇒ 需要 **R1′/R8′ 新集合**（如 `_SCALAR_EXTENSION_FIELDS = frozenset({"blocker_class"})` / `GATE_SCALAR_EXTENSION_FIELDS`），**R2′** = `BLOCKER_CLASSES = ("paperwork","judgment")`（Python+TS 各一），**R3′/R9′** 加第三分支，**R4′-R5′/R7′-R11′** 按标量 `optional()` 造型。**不得**复用 `_JSON_LIST_FIELDS`（会被 JSON 解码）。
### 3 三读面改动清单（逐条 `path:line`）

命令（定位每个面的行号）：

```powershell
Select-String -Path packages\multi-workers\autopilot\conductor.py -Pattern '^def _create_gate|^def _stamp_gate_defaults|^def _gate_default_fields|^def _rewrite_gate_fields|^def mark_stalled|^def gate_facts|^def auto_decision_for_rule|^def recompute_stall_cause|^def recompute_false_negative_class|^def _reminder_count|^def pending_gate_reminders'
Select-String -Path packages\coding-agent\src\extensions\agent-team-loop\autopilot\monitor.ts -Pattern '^function scanPendingGate|^export function readMonitorState|^export function renderMonitorLines|^export interface MonitorGate|^const MONITOR_LINE_MAX'
Select-String -Path packages\coding-agent\src\extensions\agent-team-loop\autopilot\status-model.ts -Pattern 'export function parseGateFile|export interface GateRecord|export interface GateView|GATE_JSON_LIST_FIELDS|includes\(name\)'
```

原始输出（关键行）：

```text
conductor.py:2512 def _reminder_count
conductor.py:2526 def pending_gate_reminders
conductor.py:3008 def _create_gate
conductor.py:3057 def _stamp_gate_defaults
conductor.py:3111 def _gate_default_fields
conductor.py:5271 def mark_stalled
conductor.py:6065 def gate_facts
conductor.py:5831 def auto_decision_for_rule
conductor.py:5889 def recompute_stall_cause
conductor.py:5967 def recompute_false_negative_class
monitor.ts:77  const MONITOR_LINE_MAX = 110;
monitor.ts:111 export interface MonitorGate {
monitor.ts:234 function scanPendingGate(file: string): MonitorGate | null {
monitor.ts:335 export function readMonitorState(...)
monitor.ts:766 export function renderMonitorLines(...)
status-model.ts:708  export interface GateRecord {
status-model.ts:796  export function parseGateFile(text: string, file: string): GateRecord {
status-model.ts:1333 export interface GateView {
```

**A. Python 写入端（conductor.py，唯一 gate 创建者 D-105）**

| 位置 | 现状 | 改动 |
|---|---|---|
| `conductor.py:5307-5322`（`mark_stalled` 内 `machine_fields` 组装） | 按 `reason_code` 决定是否带 `loop/used_rounds/round_limit/credits_used` | **主写入点**：按 `reason_code` 映射写 `machine_fields["blocker_class"]`（paperwork 判据 = `.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern`） |
| `conductor.py:3072-3081`（`_stamp_gate_defaults`） | 仅对 `reason_code` 做闭集丢弃（`:3076-3079`） | 照抄一条 `blocker_class not in BLOCKER_CLASSES ⇒ dropped + del`，并入 `_log_dropped_gate_fields`（`:3085-3100`）的 detail |
| `conductor.py:3111-3130`（`_gate_default_fields`） | 返回 `{default_action, authorizes:"[]"}`（+ `expires_at`） | **可选**：是否给所有新 gate 写 `blocker_class: judgment`（在 `:3112` 附近）。写了 = doctor 可检测；不写 = 缺省语义（AC-007 只要 fail-safe，不要求落盘）。**注意 R3**：一旦写进 `_GATE_UNIVERSAL_DECISION_FIELDS`（`mw_common.py:2742`）会让存量 5 个 v2 文件立刻报缺 |
| `conductor.py:6559-6585`（`_rewrite_gate_fields`） | 就地改写/插入具名字段 | **不改**（机制已足够，名字不存在时插在 frontmatter 尾部，正是 gate-0025/0026 里 `reason_code` 出现在 `expires_at` 之后的原因） |

**B. Python 解析端（gates.py）**

| 位置 | 现状 | 改动 |
|---|---|---|
| `gates.py:95-139` `FRONTMATTER_FIELDS` | 冻结 40 名序 | **不改** |
| `gates.py:146-152` `_REQUIRED_FIELDS` | 冻结 6 项 + import assert | **不改**（`blocker_class` 必须 optional） |
| `gates.py:159-174` `_LIST_FIELDS`/`_JSON_LIST_FIELDS`/`_JSON_OBJ_FIELDS` | 结构化注册表 | **新增平行标量集合**，如 `_SCALAR_EXTENSION_FIELDS = frozenset({"blocker_class"})` |
| `gates.py:507` `if name not in FRONTMATTER_FIELDS and name not in _JSON_LIST_FIELDS:` | 唯一 parse 成员检查 | 加 `and name not in _SCALAR_EXTENSION_FIELDS`（第三分支） |
| `gates.py:211-266` `class Gate` | 载体（`authorizes: list[str] | None = None` 在 `:263`） | 新增 `blocker_class: str | None = None`（**raw 缺省 = None**） |
| `gates.py:537-560` `_to_gate` 的 `optional()`（`:546-552`） | 标量读取 | 用 `optional("blocker_class")`；**闭集校验**照 `authorizes` 样板（`:660-676`）改标量形态：越界抛 `GateFormatError` |
| `gates.py:638-676` `_to_gate` 构造 `Gate(...)` | 字段接线 | 新增 `blocker_class=blocker_class` |
| `gates.py:744-772` `enumerate`/`pending_gates` | 队列扫描 | **不改**（零改动获得新字段） |

**C. Python 读面复用（doctor）**

| 位置 | 现状 | 改动 |
|---|---|---|
| `mw_common.py:60` `gate_protocol` 别名 + `:3060` `gate_protocol.parse(entry)` | doctor 复用同一 parser | 自动获得新字段；**但 `_gate_missing_fields`（`:2855-2869`）不要加 `blocker_class`**（否则存量 v2 全报缺） |
| `mw_common.py:2900-2990` `_gate_pending_entry` 返回 dict | 现存最丰富的 per-gate 机器面 | 若要状态面显示分类：按 `:2965-2989` 的 `_gate_node(value, source=..., sentinel=True)` 约定加一个 `blocker_class` 节点（`_gate_node` 定义 `:2757-2766`，sentinel 字面量 `GATE_MISSING_SENTINEL` `:2728`） |

**D. TS 状态模型（status-model.ts）**

| 位置 | 现状 | 改动 |
|---|---|---|
| `status-model.ts:660-701` `GATE_FRONTMATTER_FIELDS` | 冻结 40 名 | **不改** |
| `status-model.ts:751-766` `GATE_LIST_FIELDS`/`GATE_JSON_LIST_FIELDS`/`GATE_JSON_OBJ_FIELDS` | 注册表 | 新增 `GATE_SCALAR_EXTENSION_FIELDS`（与 Python B-3 同名同成员） |
| `status-model.ts:830` `if (!(...).includes(name) && !GATE_JSON_LIST_FIELDS.has(name))` | 唯一成员检查 | 加第三分支 `&& !GATE_SCALAR_EXTENSION_FIELDS.has(name)` |
| `status-model.ts:708-748` `interface GateRecord` | 视图载体（`authorizes: string[]` 在 `:740`） | 新增 `blockerClass: string | null` |
| `status-model.ts:796-1000` `parseGateFile` | 严格 fail-closed | 用 `optional("blocker_class")`（`:873-876`）读标量 + 闭集校验（照 `:917-924` 的 `authorizes` 样板改标量） |
| `status-model.ts:952-953` `for (const name of GATE_JSON_LIST_FIELDS) jsonField(...)` | 所有 JSON 字段统一校验 | **不需要**覆盖标量集；标量走 `optional()` 即可 |
| `status-model.ts:1003-1035` `listGates` | 目录扫描 = 队列 | **不改**（自动获得） |
| `status-model.ts:1307` `STATUS_SCHEMA = "autopilot-status/1"` + `:1333-1339` `GateView` | `{id,kind,status,ageMs}` | 扩展 `GateView`（加 `blockerClass`/`key`/`stage`/`suppression`）⇒ **必须同步 `autopilot-console.test.ts:386-390` 的 `toEqual` 精确锁**，并决定是否升 schema 版本 |
| `status-model.ts:1431` `deriveStatusModel` → `:1467-1475` GateView 映射 | 派生层 | 新字段在此派生（**判定层折 `judgment` 的 TS 落点**） |

**E. TS monitor（第三个解析面，宽松）**

| 位置 | 现状 | 改动 |
|---|---|---|
| `monitor.ts:111-130` `interface MonitorGate` | `{id,kind,stage,key,createdAt,ageMs,reasonCode,evidenceRefs,drift}` | 新增 `blockerClass?: string | null`（+ 抑制原因，归 DRQ-2） |
| `monitor.ts:234-290` `scanPendingGate` | **白名单行扫描；未知名静默忽略、不报错** | **必须显式加 `else if (name === "blocker_class") blockerClass = value` 分支**；漏了 = 字段写进文件面板看不见（AC-012 明令禁止的静默不一致） |
| `monitor.ts:335-452` `readMonitorState`（age 在 `:427`） | collect | 不改派生逻辑（新字段由 `scanPendingGate` 带上） |
| `monitor.ts:766-910` `renderMonitorLines` gates 段（`:879-908`，宽 `MONITOR_LINE_MAX=110` `:77`） | token 降级序 `1 reason → 2 age → 3 scope → 4 drift`（`:891-906`） | 若要显示分类/抑制：把 token 加进 `:891-898` 的 `tokens` 并**同步扩 `:900` 的 `for (const drop of [1,2,3,4])` 循环范围**，否则新 token 永远不会被丢、会挤掉必保部分 |

**F. 明确零改动**

| 位置 | 理由 |
|---|---|
| `gates.py:283-315` `create()` / `_gate_file_content()` | 13 键渲染被 `test_autopilot_gates.py:230`、`test_autopilot_gate_schema_v2.py:206-211`、`test_autopilot_contract_guard.py:194`、`test_autopilot_done_contract_guard.py:459` 锁死 |
| `packages/coding-agent/.../gate-writer.ts:62` `ANSWER_FIELDS` | `blocker_class` 不是答复字段；改写它会破坏"gate 是可核验命题" |
| `packages/multi-workers/autopilot/contract_guard.py` 全文 | 只 `getattr(gate, "authorizes", None)`（`:328`）与 `gate.status`/`gate.key`（`:344-346`），**不枚举字段名** ⇒ 对 `blocker_class` 零改动 |

### 4 fail-closed 专项测试：形态设计

目标：证明"漏注册一处 ⇒ 队列 fail-closed"，而不只是"未知名会抛"（后者已有 `test_autopilot_gate_schema_v2.py:296-302`）。设计 5 个测试，2 个是**反事实承重证明**：

**T-A（Python，注册 + 缺省 + 闭集）** — 放 `test_autopilot_gate_schema_v2.py`（仿 `:217-282` 的 roundtrip 形态）：

```python
def test_blocker_class_is_registered_optional_and_closed_set(tmp_path):
    assert "blocker_class" in gates._SCALAR_EXTENSION_FIELDS   # 注册存在
    assert "blocker_class" not in gates.FRONTMATTER_FIELDS     # 不进冻结序
    assert "blocker_class" not in gates._REQUIRED_FIELDS       # 保持 optional
    assert set(gates.BLOCKER_CLASSES) == {"paperwork", "judgment"}
    p = _write(tmp_path, _base_lines(extra=["blocker_class: paperwork"]))
    assert gates.parse(p).blocker_class == "paperwork"
    assert gates.parse(_write(tmp_path, _base_lines())).blocker_class is None   # 缺省 = None
    with pytest.raises(gates.GateFormatError):
        gates.parse(_write(tmp_path, _base_lines(extra=["blocker_class: bogus"])))
```

**T-B（Python，反事实：漏注册 ⇒ 整队列 fail-closed）** — 这是要的"专项证明"（仿 `test_autopilot_contract_guard.py:130-139` 的反事实锚，但用 monkeypatch 真删）：

```python
def test_missing_blocker_class_registration_fails_closed_for_the_whole_queue(tmp_path, monkeypatch):
    d = tmp_path / "gates"
    gates.create(d, "stalled", "clean", [], key="k1")                 # gate-0001，干净
    carrier = _write(tmp_path, _base_lines(extra=["blocker_class: paperwork"],
                                           id="gate-0002"))           # gate-0002，带新字段
    assert gates.parse(carrier).blocker_class == "paperwork"          # 已注册时通过
    monkeypatch.setattr(gates, "_SCALAR_EXTENSION_FIELDS", frozenset())  # 模拟"漏注册"
    with pytest.raises(gates.GateFormatError) as ei:
        gates.parse(carrier)
    assert "unknown frontmatter field 'blocker_class'" in str(ei.value)
    with pytest.raises(gates.GateFormatError):                         # blast radius：整队列
        gates.pending_gates(d)                                         # 干净 gate-0001 也一起读不到
```

**T-C（TS，反事实：`parseGateFile` 漏注册 ⇒ 抛 + 队列只记 errors）** — 放 `autopilot-gate-presentation.test.ts`：

```ts
it("blocker_class: registration is load-bearing (counterfactual)", () => {
  const root = mkdtemp("ap-blocker-class-");
  const file = writeGate(root, { id: "gate-0001", kind: "stalled", stage: 1, blockerClass: "paperwork" });
  const text = fs.readFileSync(file, "utf8");
  expect(parseGateFile(text, file).blockerClass).toBe("paperwork");
  GATE_SCALAR_EXTENSION_FIELDS.delete("blocker_class");            // 模拟"漏注册"
  try {
    expect(() => parseGateFile(text, file)).toThrow(/unknown frontmatter field 'blocker_class'/);
    const scan = listGates(root);                                   // listGates 只记 errors、剔除该 gate
    expect(scan.gates).toHaveLength(0);
    expect(scan.errors.join("\n")).toContain("blocker_class");
  } finally {
    GATE_SCALAR_EXTENSION_FIELDS.add("blocker_class");
  }
});
```

（`GATE_SCALAR_EXTENSION_FIELDS` 若是 `Set` 可直接 `.delete/.add`；若是 `ReadonlySet` 则改为导出一个可变内部 set + 只读视图，或在该测试内 `vi.spyOn`。）

**T-D（跨语言锁，防单边注册）** — 扩 `autopilot-gate-presentation.test.ts:284-302` 的既有权：子进程 dump `sorted(gates._SCALAR_EXTENSION_FIELDS)` 与 `sorted(gates.BLOCKER_CLASSES)`，两侧 `toEqual`。漏改一侧 ⇒ 红。

**T-E（monitor 静默面，防"字段写了但看不见"）** — 放 `autopilot-monitor.test.ts`（仿 `:507` 的精确串断言行）：写一个带 `blocker_class: paperwork` 的 pending gate，断言 `readMonitorState(...).gates[0].blockerClass === "paperwork"` 且渲染行含该 token。**漏加 `scanPendingGate` 分支 ⇒ 这条红**（否则会静默消失）。

**判据（照 P-03）**：旧夹具改数据不改判据；T-B/T-C 的反事实必须**真的**移除注册（不是断言成员资格就完事），否则证明的是"白名单存在"而不是"白名单承重"。

### 5 缺省语义落点（parser 保留 `None` / 判定层折 `judgment`）

**parser 保留 `None`（不折）——落点**：

- Python：`gates.py:546-552` `_to_gate.optional()` 原样返回 `None`（空值/`~`/`null` 都归 `None`）；载体默认值在 `gates.py:211-266`（新字段 `blocker_class: str | None = None`）。**不要**用 `or "judgment"` 之类。
- TS：`status-model.ts:873-876` `optional()` 返回 `string | null`；载体 `GateRecord`（`:708-748`）新字段 `blockerClass: string | null`。`status-model.ts:952` 的 JSON 校验循环**不覆盖**标量。
- 这是仓库既有语义：`MISSING_FIELD_SENTINEL = "unknown (no field)"`（`status-model.ts:706` / `mw_common.py:2728`）就是"字段缺失"的展示字面量；`GateView.ageMs` 也刻意保留 `null`（`status-model.ts:1334-1339`）。

**判定层折 `judgment`——落点（唯一施加点）**：

- 新增纯函数 `blocker_class_of(gate)`：`gate.blocker_class == "paperwork"` ⇒ `"paperwork"`；`None` / 未知值 / 解析失败 ⇒ `"judgment"`（fail-safe：文书型钩子绝不动判定型争议）。
- **Python 判定层**：`conductor.py:6083-6091` `gate_facts` 的 `stalled` 分支返回 dict 里新增 `"blocker_class": blocker_class_of(gate)`（与 `cause_class`/`false_negative_class` 并列）；消费者 = `_auto_decide_one`（`conductor.py:6896`，取 facts 于 `:6913`）→ `auto_decision_for_rule`（`conductor.py:5831-5848`）→ `RULES` 里的 `stalled-false-negative` 规则（`conductor.py:5739-5758`）。
- **TS 判定/展示层**：`deriveStatusModel` 的 GateView 映射（`status-model.ts:1467-1475`）与 monitor collect（`monitor.ts:419-435`）各自调用 TS 镜像 `blockerClassOf(record)`。
- 两处是**镜像**（照 `blockedOnHuman` 现有做法：`status-model.ts:1353-1356` 与 `monitor.ts:442` 共享同一纯函数），保证三读面同一口径。

**为何不能在解析层折**（三条硬理由）：

1. **可证伪性**：AC-007 要求"显式 `paperwork` ⇒ 走确定性钩子"。解析层折叠后 `gate.blocker_class` 永远是 `judgment`，`显式 paperwork` 与 `显式 judgment` 都变成"不是 paperwork"，唯一能证明"显式"的证据（文件里那一行）在解析后消失。这也正是 `recompute_false_negative_class`（`conductor.py:5967-5975`）docstring 立下的界线：**"Derived ... class (NOT a gate field, so it cannot be claimed)"**——派生分类与 gate 字段必须可区分。
2. **单语义**：parser 是 Python/TS/doctor/console 共用的纯格式层（`mw_common.py:60,3060`）。让它携带"决策默认值"= 把 fail-safe 语义复制到 4 个消费面，且没有一处是"判定"发生的真实位置（判定发生在 `auto_decision_for_rule`）。
3. **展示语义**：`MISSING_FIELD_SENTINEL` 的存在就是为了区分"文件里没有"与"文件里有值"。降级后 DRQ-2 要做的"看一眼就知道原因"（AC-001）会失去唯一可信输入——把默认兜底伪装成"文件里写了"正好是 E1/E5 那类静默病。
### 6 存量 gate 普查（独立复看 + 扩面修正 RQ-4 的 34）

命令（跨项目，含 `E:\CLI_workspace`）：

```powershell
python - <<census>>   # 逐文件读首个 --- 块，按 gate_schema 有无分 v1/v2，并统计 ^blocker_class:
```

原始输出：

```text
proj {'H:\\git\\E2Feature': 26, 'H:\\git\\JCodingAss': 8, 'E:\\CLI_workspace\\FeatureMigrator': 22}
TOTAL 56 v1 51 v2 5 blocker_class 0
```

逐文件 pending/v1 明细（原始输出节选）：

```text
== H:\git\E2Feature
  gate-0022.md schema=v1 status=approved kind=stalled key='feature-phaseb-closeout' reason_code='exec-exhausted'
  ... (v2 5 个见下)
== H:\git\JCodingAss
  gate-0007.md schema=v1 status=pending kind=stage-close key='' authorizes=False
  gate-0008.md schema=v1 status=pending kind=stage-close key='' authorizes=False
== E:\CLI_workspace\FeatureMigrator
  gate-0022.md schema=v1 status=pending kind=stalled key='gui-release-hardening' authorizes=False
```

E2Feature 的 5 个 v2 文件（字段名单，原始输出）：

```text
gate-0022.md ... fields: [..., 'default_action','expires_at','reason_code','loop','used_rounds','round_limit','credits_used','consumed_at','consumed_seq']
gate-0023.md ... fields: [..., 'default_action','expires_at','consumed_at','consumed_seq']
gate-0024.md ... fields: [..., 'default_action','expires_at']
gate-0025.md ... fields: [..., 'default_action','authorizes','expires_at','consumed_at','consumed_seq']
gate-0026.md ... fields: [..., 'default_action','authorizes','expires_at','reason_code','loop','used_rounds','round_limit','credits_used','consumed_at','consumed_seq']
```

核对结论：

| 事实 | RQ-4 | 本次实测 | 说明 |
|---|---|---|---|
| gate 文件总数 | 34（仅 `H:\git`） | **56**（+ `E:\CLI_workspace\FeatureMigrator` 22） | RQ-4 自己声明过"本机下界"，非错误，是边界 |
| v1 / v2 | 29 / 5 | **51 / 5** | FeatureMigrator 22 个全 v1 |
| `blocker_class` 命中 | 0/34 | **0/56** | 缺字段率仍 100% |
| 真实 pending | 2（JCodingAss gate-0007/0008） | **3**（+ FeatureMigrator gate-0022） | 新增的第三个正是本 key 的触发样本 |
| `authorizes` 命中 | 2（E2Feature gate-0025/0026） | 2 | 一致 |
| `reason_code` 取值 | `exec-exhausted` / `l3-below` | 同 | 一致 |

⇒ `blocker_class` 引入时旧文件缺字段 = **56/56 = 100%**，其中 v1 = 51/56 = 91.1%。**AC-007 的"缺省 `judgment`"是这 56 个文件的唯一读法**。

### 7 漏注册的 blast radius：原始代码证据

```text
conductor.py:2683 def _remind_pending_gates(
conductor.py:2692         pending = gates.pending_gates(gates_dir(project_root))
conductor.py:2693     except gates.GateFormatError:
conductor.py:2694         return
conductor.py:2905         except gates.GateFormatError as exc:
conductor.py:2906             st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}")
conductor.py:2907             return "ok"
conductor.py:509         all_gates = gates.enumerate(gates_dir(project_root))
conductor.py:510     except gates.GateFormatError as exc:
conductor.py:511         st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}")
conductor.py:512         return False
gates.py:507         if name not in FRONTMATTER_FIELDS and name not in _JSON_LIST_FIELDS:
gates.py:744 def enumerate(...)   # 无 try：任一文件坏 => 整体抛
gates.py:770 def pending_gates(...)  # = [g for g in enumerate(...) if pending]
```

- `conductor.py` 里 `gates.enumerate(` 的调用点至少 **13 个**（`:200, :380, :509, :742, :3152, :3167, :3179, :3239, :3265, :3329, :3449, :3642, :7031`），`gates.parse(` 2 个（`:3126, :6184`）。只有部分带 `except gates.GateFormatError`（`:380-381, :509-512, :2905-2908, :3126-3127`）；未捕获的点会向上冒到 `tick` 的 `except`（`tick` docstring 声明 "Never raises"）。
- ⇒ 一个未注册名 = **该 tick 的提醒（2692）+ 阶段跃迁（509）+ goal-change 闸门（2905）全部停摆**，只留一行 `config` timeline；TS 侧 `listGates`（`status-model.ts:1003-1035`）把 gate 剔除进 `errors`，`/autopilot` 每条命令刷 warning，`mw doctor` 记 parse 错（`mw_common.py:3060-3061, :3338-3339`）。

### 8 零改动面：`contract_guard.py` 与 `create()`

```text
contract_guard.py:322 def gate_authorizes_contract_change(gate: object) -> bool:
contract_guard.py:328     actions = getattr(gate, "authorizes", None)
contract_guard.py:344         if getattr(gate, "status", None) == "approved"
contract_guard.py:345         and gate_authorizes_contract_change(gate)
contract_guard.py:346         and getattr(gate, "key", None) == key
```

全文件 `blocker_class` 零命中，字段名零硬编码（`Select-String -Path contract_guard.py -Pattern 'blocker_class'` 空）⇒ AC-007 的"`contract_guard.py` 零改动"成立。`create()`/`_gate_file_content()`（`gates.py:283-315`）渲染 13 键，`blocker_class` 若要落盘只能经 `_rewrite_gate_fields`（`conductor.py:6559`），与冻结渲染解耦。

## 残留与未验证

1. **未跑测试**：本卡是 research + 只读，所有"会红"的判断来自测试源码逐行阅读（`path:line`），**未执行** `pytest` / `vitest`。T-B/T-C/T-D/T-E 的形态是设计，不是验证结果。风险：若 `_to_gate` 的闭集校验被写成 `optional()`（无枚举校验），T-A 的第 4 条断言会失效——需在实现时补。
2. **未定位 `paperwork` 确定性钩子的具体函数**：AC-007 的判据 `.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern` + 幂等 `splice_achieved` 的消费入口属 RQ-2（`stalled` 状态机）。本卡只给出"判定层落点"（`gate_facts` / `auto_decision_for_rule` / `RULES[stalled]`）与行号，未取证 `splice_achieved` 的调用链。风险：钩子若落在 `mark_stalled` 之前（写入端）而非 `auto_decision_for_rule`（判定端），则"显式 paperwork"的判定点会前移，需与 RQ-2 对齐。
3. **`blocker_class` 的最终命名未定**：本卡用 `_SCALAR_EXTENSION_FIELDS`/`GATE_SCALAR_EXTENSION_FIELDS`/`BLOCKER_CLASSES`/`blockerClass` 作为占位，design 定稿时须统一（跨语言锁测试依赖同名）。
4. **`_EXTRA_SCALAR_FIELDS` 是否需要 doctor 的 missing-fields 检测未定**：若加进 `mw_common.py:2742` 的 `_GATE_UNIVERSAL_DECISION_FIELDS`，存量 5 个 v2 文件立刻全报缺（I2/I6 告警）；本卡建议**不加**（缺省即 `judgment`，无需检测）。
5. **TS 反事实测试的可实施性未验证**：T-C 假设 `GATE_SCALAR_EXTENSION_FIELDS` 是可变 `Set`。若实现选择 `ReadonlySet`/冻结对象，需改用内部可变 set + 只读视图，或在测试内替换模块级常量；未先跑通。
6. **未扫本机之外的项目**：`H:\` / `E:\` / `C:\Users` 深度 3 的扫描（见 §6 第一命令）已覆盖三个有 gate 的目录；其他盘符/位置的副本未纳入，**56 是本机下界**。缺字段率 100% 的结论不依赖该边界。
7. **`baseline 89 环境失败`未考虑**：本次未跑测试，未核对上述新增/修改测试在 Windows 下的基线噪声。
8. **未核 `autopilot-status-parity.test.ts` 是否需要新增 gate 字段锁**：本卡只确认 `GateView` 被 `autopilot-console.test.ts:386-390` 锁死、`STATUS_SCHEMA` 在 `status-model.ts:1307`；schema 版本是否升为 `/2` 属 DRQ-2 决策。

## 上下文来源

### 已读全文（本机相对路径）
- `packages/multi-workers/autopilot/gates.py`（772 行，全文，重点 `:95-266`、`:283-315`、`:480-772`）
- `packages/multi-workers/autopilot/conductor.py` 定点段：`:500-530`、`:2880-2915`、`:3000-3140`、`:5260-5360`、`:5440-5510`、`:5700-5850`、`:5880-6110`、`:6555-6600`、`:6890-6925`
- `packages/multi-workers/autopilot/contract_guard.py`（grep 全文件，`:322-350` 精读）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`：`:645-1000`、`:1300-1500`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`：`:100-320`、`:415-445`、`:877-912`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`：`:40-90`
- 测试：`packages/multi-workers/test_autopilot_gates.py:180-300`、`test_autopilot_gate_schema_v2.py:120-330`、`test_autopilot_contract_guard.py:98-200`、`test_autopilot_done_contract_guard.py:440-470`、`packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:205-305`、`autopilot-console.test.ts:380-400`、`autopilot-status-parity.test.ts:1-70`
- `packages/multi-workers/mw_common.py`：`:2720-2780`、`:2850-2900`、`:2900-2995`
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`（全文，AC-007 / P-03 / P-05 / 坑点 1-2、6）
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq4-schema-and-view-surface-20261013.md`（全文，作对照与修正对象）

### 命令（原始输出已内联）
- `python` 普查脚本：`H:\git` + `E:\CLI_workspace`（§6）；深度 3 递归扫描 `H:\` / `E:\` / `C:\Users`
- `Select-String` 定位行号：`gates.py`、`conductor.py`、`status-model.ts`、`monitor.ts`、`contract_guard.py`、`mw_common.py` 的字段名与函数定义
- `Get-Content ... | % -Begin {$i=N}` 取定义块逐行（§1、§2、§3）

### 真实存量数据（只读）
- `H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0001..0026.md`（26；5 个 v2）
- `H:\git\JCodingAss\.agenticdoc\_autopilot\gates\gate-0001..0008.md`（8；全 v1；2 pending）
- `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\gates\gate-0001..0022.md`（22；全 v1；1 pending = gate-0022）