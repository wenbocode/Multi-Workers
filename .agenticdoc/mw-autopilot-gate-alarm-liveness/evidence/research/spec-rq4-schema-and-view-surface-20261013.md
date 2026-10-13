# RQ-4｜gates schema 兼容面与 monitor 常驻 pending-gate 行的插入点

- Key: `mw-autopilot-gate-alarm-liveness`｜任务: T-04（RQ-4）｜日期: 2026-10-13｜阶段: SPEC｜性质: **只读取证**（唯一写面 = 本文件）
- 时间基准: 本机 `2026-10-13T11:55:30+08:00` = `2026-10-13T03:55Z`（下文"已等 N 天"按此基准）
- 所有计数均由本机命令产出；命令与原始输出逐节附上（§1、§5）。

---

## 0 结论先行

**C1 — 存量缺字段率 = 100%。** 本机共 3 个项目存在 `gates/` 目录：E2Feature 26 个、JCodingAss 8 个、Multi-Workers **0 个**（无该目录）。合计 **34** 个 gate 文件 = **v1 29 个 / v2 5 个**；`blocker_class` 在三仓（含 E2Feature 全量文件）**零命中**。
⇒ 新增 `blocker_class` 时**旧文件缺字段 = 34/34 = 100%**；其中 **29/34 = 85.3% 是 v1（连 `gate_schema` 都没有）**。
⇒ 真正 `pending` 的存量只有 **2 个**（JCodingAss `gate-0007` / `gate-0008`，**均为 v1**，已等 **25.3 天 / 17.0 天**）。**缺省 `judgment` 不是"兼容装饰"，而是这 34 个文件的唯一读法**（AC-007 的 fail-safe 是硬需求，不是优化）。

**C2 — 字段的位置被冻结序锁死。** `blocker_class` **不能**加进 `gates.FRONTMATTER_FIELDS`（冻结 40 名跨语言序）：至少 4 处测试会硬红（§2.4：`test_autopilot_gates.py:224`、`test_autopilot_gate_schema_v2.py:143`、`test_autopilot_contract_guard.py:187`、`autopilot-gate-presentation.test.ts:253`）。唯一可行路径是复刻 `authorizes`（mw-gate-verdict-hardening D-011）的"**冻结序外 + 已注册扩展字段**"先例（`_JSON_LIST_FIELDS` / `GATE_JSON_LIST_FIELDS` + parse 成员检查的第二分支）。`blocker_class` 是标量而非 JSON 数组，因此需要的是一条**平行的标量扩展名集合**（见 §2.2 / §2.3）。

**C3 — 注册漏一处 = 整条队列坏掉（不是少一行）。** 未注册字段是 **fail-closed**：Python `gates.parse` 抛 `GateFormatError`（`gates.py:507`），TS `parseGateFile` 同样抛（`status-model.ts:830`）。
⇒ 只要有**任一** gate 文件带上未被识别的 `blocker_class`：`listGates`（status-model.ts:1003）把它计入 `errors` 并从列表里剔除；`/autopilot` 每条命令尾部刷 warning；`mw doctor` 记 `parse_errors`；conductor 的 `pending_gates`（`gates.py:770`）抛错 ⇒ `_remind_pending_gates` 直接 `return`，**该 tick 的所有门禁判定全停**。
⇒ **两侧必须同一次改动同时注册**；写入端（`mark_stalled`）只能在两侧注册落地之后才开始写字段。

**C4 — 常驻行不需要新状态源。** 现有链 `scanPendingGate`（monitor.ts:234）→ `readMonitorState`（:335）→ `renderMonitorLines`（:766）**已经收齐** AC-001 要求的 id / kind / stage / key / created_at / 已等时长（`ageMs` 在 collect 时算，monitor.ts:419-434）。缺的只有两样：**key 的可解析性标记**与**抑制原因**——两者都是"每帧派生、绝不落盘"的量。渲染插入点 = `renderMonitorLines` 的 gates 段（monitor.ts:879-908），宽度上限 `MONITOR_LINE_MAX = 110`（monitor.ts:77）。

**C5 — "提醒被抑制的原因"没有任何现成字段可承载。** 两个既有机器载体——timeline 的 `gate-reminder` 事件（conductor.py:2721-2737）与 `auto-decisions.jsonl` 的 `phase:"remind"` 台账行（conductor.py:2712-2720）——**只在提醒真的发射时才写；被抑制时两侧都不写**（这正是 E1 的病）。因此该原因必须在**三个读面**各造一个**派生字段**：monitor 的 `MonitorGate`（monitor.ts:111-130）、status 的 `GateView`（status-model.ts:1333-1342）、doctor 的 `_gate_pending_entry`（mw_common.py:2900+）。cap 轴的**唯一权威输入**是 `_reminder_count`（conductor.py:2512，读台账 `phase == "remind"` 行）；TS 侧**已有等价读取器** `readGateReminders`（pm-orchestrator.ts:1289-1319），但它服务于 PM 唤醒投递，**未接入 monitor**。

---

## 1 存量 gate 的真实字段分布（命令 + 原始输出）

### 1.1 命令

```powershell
Get-ChildItem H:\git -Directory | %{ $g = Join-Path $_.FullName ".agenticdoc\_autopilot\gates"; if (Test-Path $g) { ... } }
python -c "<frontmatter 字段普查：逐文件取首个 --- 块内的 ^([A-Za-z_][A-Za-z0-9_]*): 行名，按 gate_schema 有无分 v1/v2>"
```

### 1.2 项目分布（原始输出）

```
E2Feature      exists   n=26
JCodingAss     exists   n=8
Multi-Workers  MISSING  n=0
TOTAL=34  v1=29  v2=5
```

- Multi-Workers 自己的 `.agenticdoc/` 下**没有 `_autopilot/gates/`**（递归找 `gate-*.md` 零命中）；它的 `.agenticdoc/_autopilot/` 只有 `auto-decisions.jsonl`（6 行，全部 `phase:"dispatch-alarm"`）。
- JCodingAss 是本机第三个未被卡面点名的项目，**含全部 2 个真实 pending gate**，因此纳入统计（属于"自行扩大取证"）。

### 1.3 字段出现率（34 个文件）

| 字段 | 合计 | v1 (29) | v2 (5) | 说明 |
|---|---|---|---|---|
| `id` `kind` `stage` `key` `created_at` `created_by` `question` `context_refs` `status` `answered_at` `answered_by` `note` | 34 | 29 | 5 | base 12，100% |
| `gate_schema` | 5 | 0 | 5 | **v1/v2 的分界**（缺省 = 1） |
| `default_action` | 5 | 0 | 5 | v2 |
| `expires_at` | 5 | 0 | 5 | v2（T-08 时间有效性） |
| `consumed_at` `consumed_seq` | 4 | 0 | 4 | 消费记录 |
| `reason_code` `loop` `used_rounds` `round_limit` `credits_used` | 2 | 0 | 2 | **仅 stalled 类**（gate-0022 / gate-0026） |
| `authorizes` | 2 | 0 | 2 | 冻结序外扩展字段（gate-0025 / gate-0026） |
| **`blocker_class`** | **0** | **0** | **0** | **不存在** |

补充事实（同一普查）：
- 5 个 v2 文件里**没有一个**带 `evidence_refs`（0/34）——`evidence_refs` 在存量里**从未被写过**。
- `reason_code` 的存量取值只有两个：`exec-exhausted`（gate-0022）、`l3-below`（gate-0026）。
- 34 个文件里 **25 approved / 1 rejected**（E2Feature）+ **6 approved / 2 pending**（JCodingAss）。

### 1.4 pending 存量与"已等时长"（AC-001 的真实样本）

| 项目 | 文件 | kind | schema | created_at | 已等 |
|---|---|---|---|---|---|
| JCodingAss | `gate-0007.md` | `stage-close` | **v1** | 2026-09-17T20:04:14+00:00 | **25.3 天** |
| JCodingAss | `gate-0008.md` | `stage-close` | **v1** | 2026-09-26T04:37:27+00:00 | **17.0 天** |

两者都是 **stage 级（`key:` 为空）**、都是 v1（无 `expires_at` / `default_action` / `blocker_class`）。JCodingAss 下**没有 `auto-decisions.jsonl`** ⇒ 这两个 gate 的 `remind` 计数恒为 0，**从未有过任何提醒记录**。

### 1.5 remind 台账现状（cross-check，RQ-1 主责）

`H:\git\E2Feature\.agenticdoc\_autopilot\auto-decisions.jsonl` 里 `phase:"remind"` 共 **5** 行：

| seq | gate_id | kind | key | reminder_n | reminded_at | detail |
|---|---|---|---|---|---|---|
| 1 | gate-0024 | stage-close | (空) | 1 | 2026-10-12T14:11:15Z | pending 683m >= 30m |
| 2 | gate-0024 | stage-close | (空) | 2 | 2026-10-12T14:11:19Z | pending 683m >= 60m |
| 4 | gate-0025 | stage-confirm | (空) | 1 | 2026-10-12T14:41:33Z | pending 30m >= 30m |
| 5 | gate-0025 | stage-confirm | (空) | 2 | 2026-10-12T15:11:29Z | pending 60m >= 60m |
| 6 | gate-0026 | stalled | feature-api-contract-v2 | 1 | 2026-10-13T02:13:04Z | pending 47m >= 30m |

两点对 RQ-4 直接相关：
1. `gate-0026` 是**真实的 stalled + reason_code=`l3-below` + key** 的 gate ⇒ AC-007 的"文书型/判定型"分类有真实样本，且**该行没有任何分类字段**。
2. `gate-0024` 的 n=1 与 n=2 **相隔 4 秒**（683m 同时跨过 30m 与 60m 两道阈值）⇒ cap（默认 2）在一次 tick 内被吃完，之后**永久静默**（E2 的具体形状）。

---

## 2 `blocker_class` 的兼容矩阵

### 2.1 写入端（谁写 gate 文件、哪几个调用点）

写入端只有一个原则：**conductor 是唯一 gate 创建者**（D-105）。TS 侧只改状态字段，**不创建、不合成字段**。

| # | 位置 (`path:line`) | 角色 | 与 `blocker_class` 的关系 |
|---|---|---|---|
| W1 | `packages/multi-workers/autopilot/gates.py:387` `create()` | 13 行 canonical 文件渲染 | **不改**。只能渲染 base 12 + `gate_schema`（13 键），加字段会打破 `test_autopilot_gates.py:230` / `test_autopilot_gate_schema_v2.py:211` / `test_autopilot_done_contract_guard.py:452-456` 的 13 键断言 |
| W2 | `packages/multi-workers/autopilot/conductor.py:3008` `_create_gate()` | **唯一 choke point**：拿 `.mw/gates.lock` → `gates.create` → `_stamp_gate_defaults` → `snapshot_gate_created` → timeline `gate-created` | `blocker_class` 的**正规入口**（经 `machine_fields`） |
| W3 | `conductor.py:3057` `_stamp_gate_defaults()` | `machine_fields` 合并 + `reason_code` 闭集丢弃 + `_rewrite_gate_fields` | **需要加一条闭集守卫**（`blocker_class` 属于 {paperwork, judgment}），形状照抄 `:3078-3084` 的 `reason_code` 丢弃逻辑 |
| W4 | `conductor.py:3111` `_gate_default_fields()` | `default_action` / `authorizes: []` / `expires_at` 三个默认值 | **候选：把 `blocker_class: judgment` 作为 fail-safe 默认写进每个新 gate**（与 AC-007"缺字段 ⇒ judgment"等价且更早可见）。若选此路，doctor 的 missing-fields 检测（`mw_common.py:2742/:2752`）会立刻对**所有历史 v2 文件**报缺（见 §2.5 风险 R3） |
| W5 | `conductor.py:6559` `_rewrite_gate_fields()` | 就地改写/插入具名字段（保留其他字节） | 机制已够用：名字不存在时插在 frontmatter 尾部（这正是 gate-0026 里 `reason_code` 出现在 `expires_at` 之后的原因） |
| W6 | `conductor.py:5318`（`mark_stalled`，定义在 `:5271`） | **唯一 stalled gate 创建点**，`:5307-5322` 组装 `machine_fields`（`reason_code`/`loop`/`used_rounds`/`round_limit`/`credits_used`） | **AC-007 的主写入点**：在这里按 `reason_code` 映射写入 `blocker_class` |
| W7 | `conductor.py:663` / `:729` / `:907`（stage-confirm ×2、stage-close）、`:1258`（budget-exhausted）、`:3717`（review 类）、`:4065`（xkey-authorize） | 其余 `_create_gate` 调用点 | 均为**人裁类**：缺省 `judgment` 即可，无需显式写 |
| W8 | `conductor.py:2923`（`tick` 内 goal-change 的 `gates.create` 直调点） | 第二个 creation site（不走 `_create_gate`，但走 `_stamp_gate_defaults`，见 `:2938`） | 同上，缺省即可 |
| W9 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:40`（`ANSWER_FIELDS`）、`:121` `answerGate()` | 人类答复只改写 `status/answered_at/answered_by/note/authorizes` | **不改**：`blocker_class` 不是答复字段（改写它会破坏"gate 是可核验命题"的语义） |
| W10 | `packages/multi-workers/autopilot/conductor.py:6321` `_append_auto_decision_row()` | 台账行 | 若要在事件面同步暴露分类，写进 `detail`/新增键，**不是** gate 字段 |

推荐的最小写入面 = **W6（`mark_stalled` 的 `machine_fields`）+ W3（闭集守卫）**，W4 视是否要求"新 gate 一律显式带字段"而定。

### 2.2 解析端（Python）

| # | 位置 | 现状 | 改法 |
|---|---|---|---|
| P1 | `gates.py:95` `FRONTMATTER_FIELDS`（12 base + 28 v2 = 40） | 冻结序 | **不改** |
| P2 | `gates.py:146-152` `_REQUIRED_FIELDS`（冻结 6 项 + import-time assert） | 冻结 | **不改**（`blocker_class` 必须 optional） |
| P3 | `gates.py:159` `_LIST_FIELDS` / `:160-173` `_JSON_LIST_FIELDS`（含 `authorizes`）/ `:174` `_JSON_OBJ_FIELDS` | 结构化字段注册表 | 新增标量扩展名集合，例如 `_EXTRA_SCALAR_FIELDS = frozenset({"blocker_class"})`（命名待设计定；关键是"冻结序外 + 已注册"） |
| P4 | `gates.py:507` `if name not in FRONTMATTER_FIELDS and name not in _JSON_LIST_FIELDS:` | 唯一的 parse 成员检查（fail-closed） | 加第三分支 `and name not in _EXTRA_SCALAR_FIELDS` |
| P5 | `gates.py:211` `class Gate`（dataclass，`authorizes: list[str] | None = None` 在 `:263`） | 字段载体 | 新增 `blocker_class: str | None = None`（**raw 缺省 = None**，语义缺省 `judgment` 在访问器/消费点施加；见 §2.4） |
| P6 | `gates.py:537` `_to_gate()`（`:659-660` 是 `authorizes` 的校验样板） | 类型/枚举校验 | 新增 `blocker_class` 的**闭集校验**（{paperwork, judgment}，越界抛 `GateFormatError`，与 `authorizes` 同形） |
| P7 | `gates.py:724` `parse()` / `:744` `enumerate()` / `:770` `pending_gates()` | 队列扫描 | **不改**（零改动即获得新字段） |
| P8 | `mw_common.py:60` `gate_protocol` 别名 + `:3060` `gate_protocol.parse(entry)` | doctor 复用同一 parser | 自动获得；但见 §2.5 R3（missing-fields 检测） |
| P9 | `mw_common.py:2900` `_gate_pending_entry()`（返回 dict：`id/kind/stage/key/scope/path/question/context_refs/created_at/waited_s/reason_code/evidence/...`） | doctor 的 per-gate 机器面（**现存最丰富的 gate 状态行**） | AC-007 若要"状态面可见分类"，在此加 `blocker_class` 节点（用 `:2766` `_gate_node(..., sentinel=True)` 保持 source 锚点约定） |

### 2.3 解析端（TS）

**注意：TS 侧有 3 个 gate 解析面（不是 1 个）**，漏掉任何一个都会造成"同一个文件，两个视图说法不同"。

| # | 位置 | 严格性 | 改法 |
|---|---|---|---|
| T1 | `status-model.ts:660-701` `GATE_FRONTMATTER_FIELDS`（40 名，逐字对应 Python） | 冻结 | **不改** |
| T2 | `status-model.ts:751` `GATE_LIST_FIELDS` / `:757-765` `GATE_JSON_LIST_FIELDS`（`authorizes` 在 `:764`）/ `:766` `GATE_JSON_OBJ_FIELDS` | 注册表 | 新增与 P3 同名的标量扩展集合（**这两个集合由 `autopilot-gate-presentation.test.ts:284-302` 与 Python 逐名对齐**，必须同步） |
| T3 | `status-model.ts:830` `if (!(...includes(name)) && !GATE_JSON_LIST_FIELDS.has(name))` | 唯一成员检查 | 加第三分支 |
| T4 | `status-model.ts:708-748` `interface GateRecord` | 视图载体 | 新增 `blockerClass: string | null` |
| T5 | `status-model.ts:796-1001` `parseGateFile()`（`:908-919` 是 `jsonStringList("authorizes")` 的样板） | 严格（fail-closed） | 新增标量读取 + 闭集校验 |
| T6 | `status-model.ts:1003` `listGates()` | 目录扫描 = 队列 | 不改（自动获得） |
| T7 | **`monitor.ts:234-290` `scanPendingGate()`** | **宽松行扫描（第三个解析面）**：只认白名单名字，**未知名字静默忽略、不报错** | 若常驻行要显示分类/抑制原因，必须在此**显式新增分支**；否则字段写进文件了、面板依旧看不见（**静默不一致**——正是本 key 要消灭的模式） |
| T8 | `status-model.ts:1431` `deriveStatusModel()` → `:1467-1476` `GateView` 映射 | `/autopilot status --json` 的 gate 组 | AC-001 需要 `key`/`stage`/抑制原因 ⇒ 必须扩 `GateView`（见 §3.4） |
| T9 | `console.ts:350` `renderGateCards()`（13 行卡片） | `/autopilot gates` 卡片 | 若要卡片显示分类，加一行或并入现有行；`GATE_CARD_LINE_MAX = 110`（console.ts:232） |

### 2.4 缺省语义（缺字段 ⇒ `judgment`）

| 层次 | 现状 | 建议 |
|---|---|---|
| 文件层 | 字段不存在 | **不补写**（D-105：文件是权威；历史 34 个文件不该被批量改） |
| 解析层 | `blocker_class` → `None` / `null`（"字段缺失"，与 `MISSING_FIELD_SENTINEL = "unknown (no field)"`（status-model.ts:706 / mw_common.py:2728）一致） | 保留 `None`，**不要**在 parser 里把它折成 `"judgment"`——否则"缺字段"与"显式写了 judgment"不可区分，AC-007 的"显式 paperwork ⇒ 走确定性钩子"就没法证明是显式的 |
| 判定层（唯一施加 fail-safe 的地方） | 不存在 | 一个纯函数 `blocker_class_of(gate) -> "paperwork" | "judgment"`：`gate.blocker_class == "paperwork"` ⇒ `paperwork`；**其余一切（None / 未知值 / 解析失败）⇒ `judgment`**（fail-safe：文书型钩子绝不动判定型争议） |
| 展示层 | — | 显示 `unknown (no field)` 还是 `judgment (default)`？**建议显式区分**（AC-001 要"看一眼就知道"，把"默认兜底"伪装成"文件里写了"会把 fail-safe 藏着） |

已有先例（重要）：`recompute_false_negative_class`（conductor.py:5967-6010）的 docstring 明确写着 **"Derived three-way class (NOT a gate field, so it cannot be claimed)"**——本仓已有"派生分类 ≠ gate 字段"的显式界线，`blocker_class` 是**首个真正落盘的分类字段**，这条界线必须在 design 里写明。

### 2.5 需要同步的契约守卫与测试（逐条 `path:line`）

| # | 位置 | 断言 | 影响 |
|---|---|---|---|
| S1 | `packages/multi-workers/test_autopilot_gates.py:224` + `:225-230` | `len(FRONTMATTER_FIELDS) == 40`；`create()` 输出键序 = `[id, gate_schema, *fields[1:12]]`，`len(keys) == 13` | 加进冻结序即红 |
| S2 | `packages/multi-workers/test_autopilot_gate_schema_v2.py:138-146` | `fields[12:38] == V2_FIELDS`（顺序相等）、`fields[38:40] == CONSUMED_FIELDS`、`len == 40` | 同上 |
| S3 | `packages/multi-workers/test_autopilot_gate_schema_v2.py:203-211` | 新 gate 渲染块 = 13 键 | 同上 |
| S4 | `packages/multi-workers/test_autopilot_gate_schema_v2.py:296-302`（`test_unknown_field_fails_closed_naming_the_field`） | `bogus_field` ⇒ `GateFormatError("unknown frontmatter field")` | **新增字段后必须仍红**：这条是"注册表是显式白名单"的守卫，不能被放宽（P-03） |
| S5 | `packages/multi-workers/test_autopilot_contract_guard.py:179-197` | `len(_REQUIRED_FIELDS) == 6`、`len(FRONTMATTER_FIELDS) == 40`、`"authorizes" not in FRONTMATTER_FIELDS`、`create()` 13 键、`gates.parse(p).authorizes is None` | 需**新增**一条同形的 `blocker_class` 断言（"扩展字段已注册 + 不在冻结序 + create() 不渲染 + 缺省 = None"） |
| S6 | `packages/multi-workers/test_autopilot_done_contract_guard.py:444-458` | `"\nauthorizes: []\n" in raw`；`create()` 13 键且不含 `authorizes` | 若 W4 选"新 gate 显式写 blocker_class"，需在此加对应断言 |
| S7 | `packages/multi-workers/test_autopilot_gate_schema_v2.py:155-166` | `_REQUIRED_FIELDS` 精确集合 + 长度 + `isdisjoint(V2_FIELDS)` | 若 `blocker_class` 被误列进 V2_FIELDS 序列，此测试与 S1/S2 同时红 |
| S8 | `packages/multi-workers/autopilot/contract_guard.py`（全文） | **不枚举任何 gate 字段名**；只经 `getattr(gate, "authorizes", None)`（`gate_authorizes_contract_change`）与 `gate.status`/`gate.key` 读值 | **对 `blocker_class` 零改动**。只有当 AC-007 的确定性钩子决定复用 `contract_guard.evaluate()` 的 verdict 形状时才需要动；否则明确记录"contract_guard 不参与" |
| S9 | `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:211-254` | `pyFields == [...GATE_FRONTMATTER_FIELDS]`、长度 40、`not.toContain("authorizes")` | 跨语言锁；加进冻结序即红 |
| S10 | `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts:284-302` | `[...GATE_JSON_LIST_FIELDS].sort() == py.json_list`（读 `gates._JSON_LIST_FIELDS`） | **新增标量扩展集合后，这条会要求 Python 侧暴露同名集合**（建议再加一条对称 assertion） |
| S11 | `packages/coding-agent/test/suite/autopilot-console.test.ts:364` + `:384-389` | `s.schema == "autopilot-status/1"`；`gates` 组 `toEqual([{id,kind,status,ageMs}...])` | **`toEqual` 是精确匹配** ⇒ 扩 `GateView`（T8）必然要改这里；且要决定是否升 `STATUS_SCHEMA` 版本（`status-model.ts:1307`） |
| S12 | `packages/coding-agent/test/suite/autopilot-monitor.test.ts:338` / `:507` / `:831` | `"gates: 0 pending"` 精确串；`"gate-0007 stalled pending age=30m"`；`"gates: 1 pending - gate-0002 (stage-confirm)"` | 面板行与 status 行的精确串锁 ⇒ 改行格式必须同步 |
| S13 | `packages/multi-workers/mw_common.py:2742` `_GATE_UNIVERSAL_DECISION_FIELDS` + `:2752` `_GATE_REASON_CODE_REQUIRED_KINDS` + `:2855-2869` `_gate_missing_fields` | "schema-2 pending gate 必须带 `expires_at`/`default_action`（+ stalled 的 `reason_code`）"；v1 一律不报缺 | **R3 风险**：若把 `blocker_class` 加进这个 required 集，**存量 5 个 v2 文件全部立刻报缺**（I2/I6 告警）⇒ 只有 W4（新 gate 显式默认）落地后才可加，或干脆不加（缺省即 `judgment`，无需检测） |
| S14 | `packages/multi-workers/test_doctor_gates.py:685`、`test_mwds_t08_doctor_blocked.py`（全文件） | doctor `gates` 段字段/文本契约 | 若加 doctor 字段需在此登记 |

### 2.6 冻结序外扩展字段的"三处对称"清单（AC-007 必须一次改齐）

| 语义 | Python | TS |
|---|---|---|
| 冻结 40 名序（不改） | `gates.py:95` | `status-model.ts:660` |
| 扩展名注册（新增标量集） | `gates.py:159-174`（并列新集合） | `status-model.ts:751-766`（并列新集合） |
| parse 成员检查（加第三分支） | `gates.py:507` | `status-model.ts:830` |
| 值校验（闭集） | `gates.py:537` `_to_gate` | `status-model.ts:796` `parseGateFile` |
| 跨语言锁测试 | — | `autopilot-gate-presentation.test.ts:284-302`（需扩为覆盖新集合） |

---

## 3 monitor 常驻 pending-gate 行：插入点与渲染链

### 3.1 完整链路（collect → render → 上屏）

```
gate 文件 (…/gates/gate-NNNN.md)
  └─ [1] monitor.ts:234  scanPendingGate(file)
         宽松行扫描；只保留 status==pending 且有 id/kind 的；读 id/kind/stage/key/created_at/reason_code/evidence_refs
  └─ [2] monitor.ts:335  readMonitorState(projectDir, nowMs)      ← collect（唯一算 age 的地方）
         :419-434 遍历 gatesDir → scanPendingGate → createdMs = Date.parse(createdAt)
                   gate.ageMs = max(0, nowMs - createdMs)      （:427）
                   gate.drift = gateDriftDetail(...)           （:428，mtime > created_at）
         :442      blockedOnHuman(gates.length, nonTerminalRows)  ← 项目级两轴真值表
         :452      snapshot.gates / snapshot.blockedOnHuman
  └─ [3] monitor.ts:766  renderMonitorLines(snapshot)             ← render（纯函数）
         :739      monitorHeaderLine()                           自证帧（STALE PANEL / collected / tick）
         :829-834  BLOCKED_ON_HUMAN 行（仅当 blockedOnHuman && !autopilot.tickStale）
         :879-908  gates 段  ←★ 常驻行的插入点
  └─ [4] console.ts:682 / :751   ctx.ui.setWidget(MONITOR_WIDGET_ID, lines, { placement: "belowEditor" })
         console.ts:663  cmdMonitor  /  :734  autoStartMonitor（session_start 自动开）
  └─ [5] monitor.ts:1018 startMonitor(...)：首帧同步渲染，之后每 4000ms 一帧（MONITOR_INTERVAL_MS，:65）
```

### 3.2 gates 段现有实现（monitor.ts:879-908，逐行行为）

```ts
if (s.gates.length === 0) { lines.push("gates: 0 pending"); }
else s.gates.forEach((g, index) => {
  const head = index === 0 ? `gates: ${s.gates.length} pending - ` : "  · ";
  const base = `${head}${g.id} (${g.kind})`;
  const answer = ` -> /autopilot gate ${g.id} approve|reject`;
  // tokens + 整块丢弃降级序 drop=1..4
});
```

现有行格式与约束：
- **每 1 个 pending gate = 恒 1 行**（AC-001 的"无 cap、无衰减、无去重"在结构上已经满足：gates 段是 `s.gates.forEach`，`s.gates` 来自目录扫描，无上限）。
- 已显示的字段：`id`/`kind`（monitor.ts:889）、`stage=` 或 `key=`（:892，**二选一，不并存**）、`age=`（:894-895，`formatDuration` `:720`）、`reason=`（:896-897）、`DRIFT(...)`（:898）、答复入口（:890）。
- 宽度：`MONITOR_LINE_MAX = 110`（monitor.ts:77），超宽时按 `drop` 优先级**整块丢弃**：`1 reason → 2 age → 3 scope → 4 drift`（drop 值在 :893/:895/:897/:898，丢弃循环 :900-906），保证 `id`/`kind`/答复入口**永不丢**（D3.1 设计）。
- 顺序：`gates.sort((a,b) => a.id.localeCompare(b.id))`（:434）⇒ 与 `gates.py` 的 seq 序一致（`enumerate` gates.py:744 按 seq 数字排序；面板用字符串比较，`gate-\d{4}` 定宽下等价）。
- 高度稳定性（§9 不闪）：空队列折叠成 `gates: 0 pending`（:880）。

### 3.3 "要不要新的状态源？"——**不要**

AC-001 要求的六个量，现有模型的供给情况：

| AC-001 要求 | 现有来源 | 结论 |
|---|---|---|
| `id` | `MonitorGate.id`（monitor.ts:112） | 已有 |
| `kind` | `MonitorGate.kind`（:113） | 已有 |
| `key` | `MonitorGate.key`（:117，空串 = stage 级） | 已有（**但行的 scope token 在 stage 与 key 间二选一**，:892；stage 级 + key 级同时存在时只印一个） |
| `stage` | `MonitorGate.stage`（:114） | 已有 |
| 已等时长 | `MonitorGate.ageMs`（:123）+ `formatDuration`（:720）；算法 = `nowMs - Date.parse(created_at)`（:427） | **已有，且与 Python 同源**：`gates.py` 的 `created_at` ISO 解析 + `mw_common._gate_created_epoch`（doctor 的 `waited_s`）。**唯一权威是 gate 文件自己的 `created_at`**（绝不用 `expires_at`：v1 缺该字段，`status-model.ts:1337-1340` 已把这条写成契约） |
| 是否被抑制及原因 | **无** | 需新增派生字段（§4） |

⇒ 复用现有枚举 + 现有已等时长计算即可。**不要**新造一个"pending gates 状态文件"：那会违反 P-02（状态面优先）的反面——把派生量落盘必然产生"文件与磁盘现实不一致"的第二个真相源，并且需要一个新写入方与一把新锁。

### 3.4 需要扩的字段（最小集）

| 面 | 类型 | 位置 | 新增 | 理由 |
|---|---|---|---|---|
| monitor collect | `MonitorGate` | monitor.ts:111-130 | `blockerClass?: string \| null`；`suppression?: string \| null`（或 `reminderState`） | AC-007 + AC-002/AC-004 的常驻行 |
| monitor 帧 | `MonitorSnapshot` | monitor.ts:186-224 | `suppressedReminders?: number`（可选，用于"0 提醒但 N 被抑制"的一眼判断） | 让"永久静默"可被数出来 |
| status JSON | `GateView` | status-model.ts:1333-1342 | `key`、`stage`、`blockerClass`、`suppression` | AC-001 的六元组；**注意 S11 的 `toEqual` 锁 + `STATUS_SCHEMA` 版本决策** |
| doctor | `_gate_pending_entry` 返回 dict | mw_common.py:2900+（`:2957-2989` 是返回体） | 同上 | 三个读面口径一致 |

### 3.5 渲染插入点的具体形状（不改宽度契约）

现有 gates 段的 token 降级序天然可扩：把 `suppressed=<reason>` 作为**最低优先级** token（`drop=5`，即最先被丢）插进 `tokens`（monitor.ts:891-898），或者在必保部分加一个固定后缀。约束：
- `MONITOR_LINE_MAX = 110` 不动（S12 的精确串断言存在，改行格式要同步改）。
- `id`/`kind`/答复入口的"永不丢"保证不得破坏（D3.1）。
- 现有 `drop` 循环只跑 `[1,2,3,4]`（:900），新增档位要同步扩循环范围，否则新 token 在超宽时**永远不会被丢**——反而挤掉必保部分。

---

## 4 "提醒被抑制"的原因如何表达（AC-002）

### 4.1 抑制判定的全部出口（Python 真值表，conductor.py:2526-2576）

`pending_gate_reminders` 的四条件，逐一映射到"抑制原因"：

| 条件 | 代码 | 语义 | 抑制原因标签（建议） | 备注 |
|---|---|---|---|---|
| 条件 2（**项目级**） | `conductor.py:2558` `if any(_is_in_flight(row) for row in rows): return []` | **任一 key 有在飞 worker ⇒ 所有 gate 一律不提醒** | **AC-002 要修掉这一条**，改成 gate/key 粒度：`key-in-flight` | E3 = 本 key 的根因 |
| 条件 4（stage 终止） | `conductor.py:2565-2571`，`_STAGE_STATUS_RANK` / `_STAGE_TERMINAL_RANK` | gate 归属 stage 为终态 ⇒ 不提醒 | `stage-terminal` | 设计上合理，**保留**；与 E1 叠加才是问题 |
| 条件 3（cap） | `conductor.py:2563-2564` `n > max_reminders` + `:2543` | 已达 `gate_reminder_max`（默认 2，闭区间 `[1,2]`） | `cap-reached` | AC-004：必须**在状态面显式标注**"已达打断上限，仍待处理" |
| 条件 1（未到期） | `conductor.py:2572-2574` `(now - anchor) < n * after_min * 60` | 还没到下个阈值 | `not-due`（或 `due`） | 不是抑制，是"还没到点"；展示层要能区分，否则 AC-001 的"为什么没提醒我"答不上 |
| 无法解析 key/stage | 文档串 `conductor.py:2546-2551`（"a missing record must never silence a reminder"，fail-open） | key/stage 解析不出来 | **`none`（不抑制）** | AC-002 的新规则；标签建议 `unresolved-scope`（= 明确"没抑制、也没法归因"） |
| 队列本身坏 | `conductor.py:2692-2694` `except gates.GateFormatError: return` | gate 文件损坏 ⇒ 整个提醒通道静默 | 需要**新的可见原因** `gate-queue-unreadable` | 与 C3 同源：这是"整表坏 ⇒ 连无关能力停摆"的又一实例 |

⇒ 建议的**封闭枚举**（design 阶段定稿）：`key-in-flight` / `stage-terminal` / `cap-reached` / `not-due` / `unresolved-scope` / `gate-queue-unreadable`，外加"正常发射"态（`fired`，其值可取 `reminder_n`）。

### 4.2 有无现成字段可承载？**没有。**

逐载体排查（含"为什么不行"）：

| 载体 | 位置 | 能否承载抑制原因 | 理由 |
|---|---|---|---|
| gate 文件 frontmatter | `gates/gate-*.md` | **不能** | 抑制状态**每 tick 变化**（worker 起飞/落地、cap 计数、stage 状态），而文件是"人类权威 + 可核验命题"（D-105）；写进去需要新写入方（违反 conductor 单写者）且必然引入陈旧 |
| timeline `gate-reminder` 事件 `data` | conductor.py:2721-2737（`data = {gate_id, gate_kind, gate_key, reminder_n, waited_s, after_min}`） | **不能** | 只在**发射时**写；被抑制时零事件。这正是 E1 的病 |
| `auto-decisions.jsonl` `phase:"remind"` 行 | conductor.py:2712-2720 | **不能（结构上够用，语义上缺）** | 同上：只有发射才有行。但它**是 cap 轴唯一权威输入**：`_reminder_count`（conductor.py:2512）按 `gate_id` 计数 |
| `MonitorGate` | monitor.ts:111-130 | **可以，且是最合适的位置** | 每帧从文件派生、不落盘（AC-008 纯只读），`blockedOnHuman` 的派生字段先例已在同一接口里 |
| `MonitorSnapshot.blockedOnHuman` | monitor.ts:198 / status-model.ts:1356 `blockedOnHuman(pendingGates, nonTerminalRows)` | **只能给项目级布尔，给不出原因** | 是"两轴真值表"的项目级汇总（且被 `mw doctor` 以 `_blocked_on_human`（mw_common.py:3279）镜像，S13/S14 有契约锁）。AC-002 改成 gate/key 粒度后，这个布尔**语义会变** ⇒ 两处镜像必须一起改（`mwds-t12-regression.test.ts:379-401` 就是这条 seam 的测试） |
| `GateRecord` | status-model.ts:708-748 | 可以（卡片面） | `/autopilot gates` 13 行卡片可加一行 |
| `mw_common._gate_pending_entry` | mw_common.py:2900-2990 | 可以（doctor 面） | 现存最丰富的 per-gate 机器面，已有 `_gate_node(value, source=..., sentinel=True)` 的 source 锚点约定可复用 |
| `gate_reminder_max` / `gate_reminder_after_min` 配置 | status-model.ts:125-129、config.py:57 | 只是阈值，不是原因 | — |
| PM 侧 `readGateReminders` | pm-orchestrator.ts:1289-1319 | **是现成的 TS 台账读取器**（`gate_id`/`gate_kind`/`gate_key`/`reminder_n`/`detail`/`seq`） | **尚未接入 monitor**；AC-004 的 `cap-reached` 直接由 `max(reminder_n) >= gate_reminder_max` 推出 |

### 4.3 结论与最小落地形状

- 抑制原因 = **派生值**，三面（monitor / status / doctor）各自计算，口径必须用**同一个纯函数**（Python 与 TS 各一份镜像，如 `blockedOnHuman` 现有做法），避免出现第三套语义。
- cap 轴唯一需要的**持久输入**是 `phase:"remind"` 计数值：Python 有 `_reminder_count`（conductor.py:2512）；TS 需要把 `readGateReminders`（pm-orchestrator.ts:1289）的读取逻辑提升为共享函数（或在 monitor 内新增等价读取），**这是本 RQ 里唯一"新增读取"的工作量**。
- `gate-queue-unreadable` 原因必须存在：否则 `conductor.py:2692-2694` 的静默 `return` 会把"文件坏了"伪装成"没有待办"。

---

## 5 上下文来源清单（全部按 `path:line` 索引）

### 5.1 已读全文
- `packages/multi-workers/autopilot/gates.py`（772 行，全文）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（1547 行，全文）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（1074 行，全文）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`（777 行，全文）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`（全文）
- `packages/multi-workers/autopilot/contract_guard.py`（全文）
- `packages/multi-workers/test_autopilot_gate_schema_v2.py`（全文）
- `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`、`tasks/T-04-rq4-schema-view.md`、`evidence/research/spec-bootstrap-declaration-20261013.md`

### 5.2 定点取证
- `packages/multi-workers/autopilot/conductor.py`：`:2512` `_reminder_count`、`:2526-2576` `pending_gate_reminders`（四条件，`:2558` 项目级抑制、`:2565-2571` stage 终止）、`:2643` `_gate_stage_context`、`:2683-2737` `_remind_pending_gates`（`:2712-2720` 台账行 / `:2721-2737` 事件）、`:2923` goal-change 创建点、`:3008-3055` `_create_gate`、`:3057-3109` `_stamp_gate_defaults`、`:3111-3134` `_gate_default_fields`、`:5271-5340` `mark_stalled`（`:5307-5322` machine_fields）、`:5453-5491` `STALL/PREDICATE/ENGINE_REASON_CODES` / `REASON_CODES`、`:5889-5965` `recompute_stall_cause`、`:5967-6010` `recompute_false_negative_class`、`:6076-6114` `gate_facts`、`:6321` `_append_auto_decision_row`、`:6559-6585` `_rewrite_gate_fields`
- `packages/multi-workers/mw_common.py`：`:60` `gate_protocol`、`:2728` `GATE_MISSING_SENTINEL`、`:2742` / `:2752` / `:2754` decision-field 元组、`:2766` `_gate_node`、`:2855-2869` `_gate_missing_fields`、`:2900-2990` `_gate_pending_entry`、`:3211-3305` doctor gates 段与 `_blocked_on_human`
- `packages/multi-workers/mw.py`：`:3600` gate 动作表、`:3674+` 卡片文本渲染
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`：`:467` / `:520-528` 台账路径、`:1264-1319` `GateReminder` + `readGateReminders`、`:1466-1510` 提醒投递
- 测试：`test_autopilot_gates.py:150-300`、`test_autopilot_gate_schema_v2.py`、`test_autopilot_contract_guard.py:178-208`、`test_autopilot_done_contract_guard.py:440-490`、`test_doctor_gates.py:685`、`test_mwds_t08_doctor_blocked.py`、`autopilot-gate-presentation.test.ts:195-315`、`autopilot-console.test.ts:360-450`、`autopilot-monitor.test.ts:330-345/484-545/795-835`、`autopilot-status-parity.test.ts:1-61`、`mwds-t12-regression.test.ts:360-455`

### 5.3 真实存量数据（只读）
- `H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0001..0026.md`（26 个；含 5 个 v2）
- `H:\git\E2Feature\.agenticdoc\_autopilot\auto-decisions.jsonl`（6 行：5 `remind` + 1 `dispatch-alarm`）
- `H:\git\JCodingAss\.agenticdoc\_autopilot\gates\gate-0001..0008.md`（8 个，全 v1，含 2 个 pending）
- `H:\git\Multi-Workers\.agenticdoc\_autopilot\`（无 `gates/`；`auto-decisions.jsonl` 6 行全 `dispatch-alarm`）

---

## 6 未覆盖面声明

1. **本机之外的项目未扫**：只扫了 `H:\git\*` 下的一级目录。`gates/` 路径策略是"每项目 `.agenticdoc/_autopilot/gates`"，磁盘上其他位置（例如 `%USERPROFILE%` 下的工作副本、其他盘符）未纳入 ⇒ 34 这个总数是**本机下界**，不是全域。缺字段率 100% 的结论不依赖该边界（字段根本不存在于任何代码/文件）。
2. **E2Feature 的 git 历史未追溯**：只统计了工作区当前 26 个文件，没有统计被删除/被 hand-edit 掉的历史 gate（`git log -- .agenticdoc/_autopilot/gates` 未跑）。"34 个文件 100% 缺字段"对历史同样成立（`blocker_class` 是全仓首次引入），但"历史曾出现过多少 gate"未知。
3. **Multi-Workers 自己的 key 从未产出 gate 文件**：本 key 的 4 张卡全在 SPEC 阶段，conductor 未在该仓库跑过 gate 生命周期 ⇒ 本仓库的 gate 存量是 0，所有"存量兼容"证据都来自 E2Feature / JCodingAss。
4. **AC-007 的 `paperwork` 确定性钩子入口未定位到具体函数**：本 RQ 只回答"字段兼容面 + 插入点"。钩子本身（哪个函数消费 `blocker_class == "paperwork"`）属于 design/RQ-2（`stalled` 状态机）的范围；`gate_facts`（conductor.py:6076）与 `recompute_stall_cause`（:5889）是**最可能的接入点**，但未取证其调用链。
5. **`closed-legacy ↔ stalled` 回环语义未核**：属 RQ-2；本文件只在 §2.5 S8 记录 contract_guard 不参与。
6. **AC-005/AC-006（serve.meta commit 漂移）完全不覆盖**：属 RQ-3。
7. **未跑测试**：本卡是 research 卡 + 只读，所有断言均取自测试源码的静态阅读（`path:line`），未执行 `pytest` / `vitest` 验证其当前是否真的绿。
8. **未验证 `mw doctor` 文本契约的字节级输出**：只读了 `_gates_text_alerted`（mw_common.py:3375-3398）与 `format_doctor_text`（定义在 :3666，`blocked_suffix` 段在 :3785-3786）的代码路径。
