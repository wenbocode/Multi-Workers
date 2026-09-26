# Design: 门消费记录持久化与 stage 状态单调性（D3 / key `mw-autopilot-slot-capacity`）

> 角色：DESIGN 期设计卡（**只读代码 / 只写本文件**）。服务 AC-022（D1/D2/D3）与 AC-028（D4）。
> 代码基线：`H:/git/Multi-Workers` HEAD `191a069a4e95bdcfb2a0bac88f800a566490c1a6`（行号 = 该工作树快照）。
> 数据快照：2026-09-26（FM `E:/CLI_workspace/FeatureMigrator`、E2 `H:/git/E2Feature`、JC `H:/git/JCodingAss`），**只读**。
> 写面：`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-consumption-record-20260926.md`（唯一）。未改任何代码/config、未答任何 gate、未写 FM/E2/JC、未 commit。
> 前置诊断（**不重复其内容**，只引用结论）：`spec-auto-gate-guardrails-20260926.md` F6（D1/D2/D3）、`spec-gate-defer-safety-20260926.md` F4-CC-7 / F5（D4 的 JC `gate-0008` 实证）、`spec-gate-review-material-20260926.md` F4.4（同一实例的最小人审面）。
> 本卡**只做设计**：给方案、`file:line` 锚点、反证构造、两侧镜像面、顺序约束与 VC 候选；**不给完整实现代码**。

## TL;DR

1. **根因是一条链，不是四个孤立缺陷**：消费记录 `_consumed_gate_ids`（`conductor.py:297-312`）**从 append-only 但只留 2 代的 timeline 反推**（`timeline.py:93-94`；本机实测 FM/E2 各 2 个文件、JC 3 个），且正则 `(gate-\d{4})\b`（`conductor.py:310`）只认 4 位 id；于是「记录会丢」（D1 的 4 位溢出 + timeline 轮转）与「丢了也没人拦」（`_set_stage_status:380-406` 无单调性、`_apply_stalled_rejections:2363-2394` 无消费守卫）叠加，产生 JC 2026-09-26T04:37 的 `closed → running` 回退 + `gate-0008` 重放门。
2. **载体选型（本卡核心决策面）**：对比 4 个方案（独立 ledger / roadmap 侧栏 / 扩大 timeline 保留代数 / **gate 文件新增消费字段**）。判据四维：跨轮转持久 / 抗 gate id 重用 / 抗被审方伪造（AC-030）/ 读取代价。**推荐 = 方案 D（gate 文件 `consumed_at`+`consumed_seq`）**，理由：它是唯一同时满足四维且不需要新锁的载体（gate 目录已被 `xkey-gate-guard.ts` 工具层封堵；`gates.enumerate` 每 tick 已读全部 gate 文件）。**若 D-105「12 字段」schema 在本 key 内冻结不可动**（`gates.py:68-84` + `status-model.ts:572-591` + `test_autopilot_gates.py:220-221` 的 `len(keys)==12`），则退到方案 A（ledger），但必须带三项前置：**复合键 `(id, created_at)`**、**guard 扩展封堵 ledger 路径**、**compaction 专属锁**（`.mw/gate-consumption.lock`，无命名冲突）。
3. **id 单调性**：`gates._next_seq:246-259` = `max(现存 gate-(\d+).md)+1`，`create:280` 渲染 `f"gate-{seq:04d}"` ⇒ **同一 gates 目录内严格单调、不回绕**；但**跨归档/删除会重用**（实测 FM：`gates/` 现存 max=10，而 `_gates-flood-20260924/` 含 6684 个 `gate-0004..gate-6687` ⇒ 下一次 create 得到 **`gate-0011`，一个已被用过的 id**）。这使「按 id 索引、且永不剪枝」的 ledger 必须用复合键，而 gate 文件字段天然免疫（记录随文件存亡）。
4. **D1 修法**：`re.match(r"(gate-\d{4})\b", ...)` → **`re.match(r"(gate-\d+)\b", ...)`**（精确替换串）；`\d+` 贪婪吞掉全部位数、其后 `\b` 因"数字=word char / 后续是空格或串尾"而成立；`\d{4}` 无法回退是因为两个数字之间不构成 word boundary。反证：`'gate-10000 approved → k running'` 修复前 → `None`、修复后 → `gate-10000`（本卡实测，见 F3）。
5. **D2 修法**：给 `_apply_stalled_rejections` 补上与 approve 完全对称的消费守卫（`conductor.py:2315/2319` 的对照面），并在 `gate-answered` 写入前统一走新载体。反证：构造"已消费的 reject 门 + key 又被置回 `stalled`"⇒ 修复前重复写 roadmap 并追加第二条 `gate-answered`，修复后零写入零事件。注意 `mark_stalled:3944-3958` 只对 `== "stalled"` 短路，**允许 `closed-legacy → stalled`** ⇒ D2 与 D4 可复合触发。
6. **D3 修法**：TS `EVENT_TYPES`（`status-model.ts:779-796`，16 类）补 `"target-config-rejected"`，与 Python `timeline.py:67-84`（17 类）逐项对齐；判据 = 集合相等（`py_only==∅ and ts_only==∅`）。影响面已定位：`console.ts:261` 用 `nonBeatFilter()` 作 include-set，缺项会让 `/autopilot timeline` 默认视图**静默吞掉**该事件（`--all` 可见）。三项目实测该事件生产样本 **0**（latent）。
7. **D4 修法（最重要）**：在 `_set_stage_status` 加**单调性判据**，把 stage 状态转换收窄为 `pending/approved → running → closed|closed-human|halted` 的偏序上升；**终态（`closed`/`closed-human`/`halted`）→ 非终态禁止**，且被拒时**必须留痕**（新增拒绝事件，属 EVENT_TYPES 扩展 ⇒ 依赖 D3 的两侧对齐）。**合法重开只由人工改 `_roadmap.md` 授权**（现有唯一解除路径，`_stage_activation:442-443` 已声明）；conductor 侧永不重开。反证：JC 式构造（stage 1 = `closed` + 已答 `gate-0001 stage-confirm approved` + 消费记录缺失）⇒ 修复前回退到 `running` 并开门 `gate-0008`，修复后 stage 仍 `closed`、无 `gate-0008`、有且仅有一条拒绝事件。
8. **顺序约束**：**D3 + D1（无依赖，立即）→ 载体 + D4 + D2（同一波，载体先定）→ 自动决策 / 影子模式 → 延后复核**。AC-022/风险 22 的硬要求映射为"D1 必须先于任何自动决策上线"；补充：**D4 必须先于任何可能导致重放/重开的能力**（延后复核、拉长保留窗、批量复核）。
9. **迁移**：现有项目**不需要全量回填**即可安全：消费判据改为 `gate 字段（新）∪ timeline 反推（旧，含 D1 修正）`。可选一次性 backfill：对每个非 pending gate，若"目标状态 ≤ 当前状态的单调序"（即 transition 会是一次降级）⇒ 记为已消费/已被取代。**JC `gate-0001` 正是这一类**（target=`running` < current=`closed`）⇒ 迁移即可消除重放，无需 D4 也安全；D4 作为第二道防线覆盖"字段写入崩溃 + 人工删字段 + 人工改 roadmap"。
10. **VC 候选 5 条**（D1/D2/D3/D4 + 载体持久性），逐条给**字段级断言**（见 F8）。全部可机器判、可复算；D3 按 P-021 要求两侧都跑。

## 决策问题

1. **消费记录载体选型**：独立 append-only ledger / roadmap 侧栏 / 扩大 timeline 保留代数 / （本卡新增）gate 文件字段——逐方案给：写入点 `file:line`、读取点、原子性与锁（复用 `mw_common.acquire_lock`，注明锁名冲突）、崩溃恢复语义、迁移（既有项目如何回填已消费 id）。
2. **D1 修法**：`gate-\d{4}` 正则的精确替换串与成立理由；`gate-10000` 的反证构造；并回答 id 生成是否保证单调递增（`gates.py` 生成处 `file:line`）以及 id 重用/回绕对影响面的改变。
3. **D2 修法**：approve（`conductor.py:2315-2319`）与 reject（`:2363-2394`）不对称的对称化设计 + "重复应用 reject" 的反证。
4. **D3 修法**：TS/Python 事件集合对齐设计 + 跨语言一致性判据（P-021）。
5. **D4 修法**：stage 状态单调性——哪些转换合法、哪些需要显式事件才能回退、`file:line` + 判据 + 反证（重放已答门后 stage 不得回退）；与 D2 的关系（"合法重开"由谁授权、留什么事件）。
6. **顺序约束**：哪个修复必须先于自动决策上线的依赖顺序图 + 各修复之间的耦合。
7. **VC 候选**：每个缺陷一条机器可判 VC，给字段级断言。

**硬要求**：所有修法给现状锚点 `file:line`；反证是可执行的最小构造（输入/操作/期望观测）；两侧镜像面必须点明；**不给完整实现代码，只给设计面**。

## 调研方法与出处

**代码（只读通读 + 定点复核）**

| 面 | 锚点 | 与 D1–D4 的关系 |
|---|---|---|
| 消费记录反推 | `autopilot/conductor.py:297-312`（`_consumed_gate_ids`，正则 `:310`） | D1 的唯一失效点；D2/D4 的共同底座 |
| 消费应用（stage 级） | `conductor.py:316-376`（`_consume_answered_gates`）：读消耗 `:341`、xkey 分支 `:344-347`、跳过 `:350-351`、stage-confirm `:352-357`、stage-close approved `:358-369`、rejected `:370-375` | 6 个 `gate-answered` 写入点中的 3 个 |
| 消费应用（key 级） | `conductor.py:2295-2360`（`_apply_stalled_approvals`：consumed `:2315`、守卫 `:2319`、写 roadmap `:2345-2347`、事件 `:2349`） / `:2363-2394`（`_apply_stalled_rejections`：**无 consumed**、写 roadmap `:2385-2387`、事件 `:2388`） | D2 的不对称面 |
| 消费应用（xkey） | `conductor.py:2798-2850`（`_consume_xkey_gate`，事件 `:2848-2850`） | 第 6 个写入点；载体变更必须覆盖 |
| stage 状态写 | `conductor.py:379-405`（`_set_stage_status`：仅比较"是否不同" `:392`，无单调判据） | D4 的唯一写入点 |
| stage 激活/收口 | `conductor.py:434-451`（`_stage_activation`：`halted` 即停、无 running 才激活）、`:616-656`（`_stage_closure`，终态集 `:629`）、`:408-431`（`_ensure_next_stage_gate`） | D4 的后果面（重开会连带开门/派发） |
| key 置 stalled | `conductor.py:3944-3994`（`mark_stalled`；`:3958` 只短路 `== "stalled"`；`:3971` 每次新建 stalled 门） | D2 反证的可达性来源（`closed-legacy → stalled` 允许） |
| 依赖饱和 | `conductor.py:56`（`_DEP_SATISFIED = {"done","closed-legacy"}`）、`:2153-2154`（`_deps_satisfied`） | `closed-legacy` 的不可逆后果（reject 方向的代价） |
| gate id 生成 | `autopilot/gates.py:246-259`（`_next_seq`）、`:262-284`（`create`，`:280` `f"gate-{seq:04d}"`）、`:90-91`（`GATE_ID_RE`/`GATE_FILE_RE` = `^gate-(\d+)$` / `^gate-(\d+)\.md$`） | 单调性结论的出处；id 重用的机制 |
| gate schema / 校验 | `gates.py:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:68-84`（`FRONTMATTER_FIELDS` 12 字段）、`:86-88`（必填集）、`:201-206`（`_write_atomic` tmp+replace） | 方案 D 的 schema 成本；方案 A 的无关性 |
| gate 写者协议 | `gates.py:1-20`（"create = conductor only；本模块不取锁，caller 组 `.mw/gates.lock`"）；TS `gate-writer.ts:50`（`ANSWER_FIELDS`）、`:99-131`（`rewriteAnswerFields` 只重写 4 行、**其余行逐字保留**，含 `\r`） | 方案 D 的 TS 兼容性证据：新增字段不会被 `answerGate` 丢弃 |
| timeline | `autopilot/timeline.py:67-84`（`EVENT_TYPES` 17 类）、`:93-94`（`ROTATE_THRESHOLD_BYTES=10MB` / `ROTATE_GENERATIONS=2`）、`:388-430`（`query_events`） | D3 的对齐面；D1 的失效环境 |
| TS 事件词表消费 | `status-model.ts:779-796`（`EVENT_TYPES` 16 类）、`:801-806`（`nonBeatFilter`）、`console.ts:261`（默认视图用 `nonBeatFilter()`） | D3 的影响面 |
| TS gate schema 镜像 | `status-model.ts:571-591`（`GATE_FRONTMATTER_FIELDS` + `GateRecord`）、`:630-679`（`parseGateFile`，`:660` 未知字段 fail-closed） | 方案 D 的两侧成本 |
| 状态词表镜像 | `roadmap.py:53-61`（`STAGE_STATUSES`）/ `:63-70`（`KEY_STATUSES`） vs `status-model.ts:321-322` | D4 的镜像面（若新增状态则必须两侧改） |
| 工具层封堵 | `shared/xkey-gate-guard.ts:46-51/125-133/216-241`（只封 `<root>/.agenticdoc/_autopilot/gates/**`；`_autopilot/xkey/` 与 `_autopilot/evidence/**` 有意不封） | 载体"抗被审方伪造"（AC-030）的判据来源 |
| 锁面 | `mw_common.py:1482-1496`（`acquire_lock`，`O_CREAT\|O_EXCL`）、`:1440-1441`（`lock_path` = `.mw/workers.lock`）；`conductor.py:116-118`（`lock_file`）、`:121-159`（`acquire_conductor_lock`，30s stale steal） | 新载体的锁设计与命名冲突检查 |
| 现有锁名实测 | `.mw/workers.lock`、`.mw/roadmap.lock`、`.mw/gates.lock`、`.mw/key-{key}.lock`、`.mw/conductor.pid`、`.mw/xkey-ledger.lock`（`xkey.py:102`）、`.mw/autopilot-config.lock`（`mw.py:3246`）、`.mw/index.lock`（测试） | `.mw/gate-consumption.lock` **无冲突**（实测全仓 grep） |
| 冻结断言面 | `test_autopilot_gates.py:203/220-221`（`roundtrip_fields={len(FRONTMATTER_FIELDS)}`、`assert len(keys) == 12`）、`gates.py:1/68` 文档串"12 fields" | 方案 D 的回归成本（1 行断言 + VC 行 + 文档串） |

**数据（只读复算，脚本落在 `%TEMP%` 并已删除）**

| 量 | FM | E2 | JC | 口径 |
|---|---|---|---|---|
| timeline 文件 | `timeline.jsonl` + `.1`（2 个） | 同（2 个） | `.jsonl` + `.1` + `.2`（3 个） | `glob("timeline.jsonl*")` |
| seq 范围 | 1–92405 | 1–97627 | 98074–298999 | 逐行 `json` 解析 |
| `gate-answered` | 6694 | 18 | 3 | 事件计数 |
| `gate-created` | 6696 | 18 | 3 | 事件计数 |
| `stalled` / `resume` | 6691 / 6691 | 13 / 13 | 无 | 事件计数 |
| `target-config-rejected` | **None（0）** | **0** | **0** | 事件计数（D3 生产样本 = 0） |
| 现存 `gates/` id | `0001..0010`（n=10） | `0001..0018`（n=18） | `0001..0008`（n=8） | 文件名正则 |
| 归档目录 | `_gates-flood-20260924/` **n=6684**，id `0004..6687` | 无 | 无 | 目录实测 |
| 4 位正则反推的已消费集合 | 10 个（全 4 位） | 18 个 | 3 个 | `re.match(r"(gate-\d{4})\b", detail)` |
| `\d+` 反推的已消费集合 | 10 个（与上同） | 18 个 | 3 个 | 同上，`\d+` |
| 二者差集 | ∅ | ∅ | ∅ | ⇒ **D1 在生产上尚未触发**（最大 id 6687，且已归档） |

**方法边界**：不做代码修改、不跑被测代码（除 F3 的纯正则反证，一条 `python -c`）；不答 gate；所有数字可由上表口径复算（脚本：读 `timeline.jsonl*` 逐行 `json.loads`；读 `gates/gate-*.md` 文件名正则）。生产未触发项一律标 `[latent]` 并给可达性论证，不写"已发生"。

## 发现

### F0 【事实】消费链路现状：6 个写入点、3 个读取点、1 个失效点

| # | 转换 | 函数 | roadmap 写入 | 消费记录写入 | 读消费记录 |
|---|---|---|---|---|---|
| 1 | `stage-confirm` approved → stage `running` | `_consume_answered_gates:352-357` | `_set_stage_status:398-402`（`.mw/roadmap.lock`） | `:354-357` `gate-answered` | `:341` |
| 2 | `stage-close` approved → stage `closed` | `:358-369` | 同上 | `:361-364` + `stage-close` `:365-368` | `:341` |
| 3 | `stage-close` rejected → stage `halted` | `:370-375` | 同上 | `:372-375` | `:341` |
| 4 | `stalled` approved → key `running` | `_apply_stalled_approvals:2295-2360` | `:2345-2347`（`.mw/roadmap.lock`） | `:2349` + `resume` `:2350-2355` | `:2315`（守卫 `:2319`） |
| 5 | `stalled` rejected → key `closed-legacy` | `_apply_stalled_rejections:2363-2394` | `:2385-2387`（`.mw/roadmap.lock`） | `:2388` + `stalled` `:2389` | **无**（D2） |
| 6 | `xkey-authorize` answered → ticket/ledger | `_consume_xkey_gate:2798-2850` | ticket 文件（`.mw/xkey-ledger.lock`） | `:2848-2850` | 调用方 `:345` |

- **读取点 3 个**：`:341`（`_consume_answered_gates`）、`:2315`（approve）、`:345`（xkey 分支）。
- **唯一失效点**：`:310` 的正则（D1）。**唯一无守卫点**：`:2363-2394`（D2）。**唯一无单调判据点**：`:392`（D4）。
- **事件 detail 形状**（决定 D1 的修复安全边界，逐点核对）：6 处全部以 `f"{gate.id} ..."` 起头（`:356`/`:363`/`:374`/`:2349`/`:2388`/`:2849`）⇒ `re.match` 的 pos-0 锚定语义**在现状下成立**；这是"只改位数、不改锚定"的依据。

### F1 载体选型（≥2 方案 + pros/cons + 推荐）

#### F1.1 方案对比表

| 维度 | **A. 独立 ledger** | **B. roadmap 侧栏** | **C. 扩大 timeline 保留** | **D. gate 文件字段（推荐）** |
|---|---|---|---|---|
| 载体/路径 | `<root>/.agenticdoc/_autopilot/gate-consumption.jsonl`（或 `<root>/.mw/gate-consumption.jsonl`） | `_roadmap.md` 头部新行 `> consumed-gates:` | 不改载体（`timeline.jsonl*`） | `gates/gate-NNNN.md` frontmatter 新字段 `consumed_at` / `consumed_seq` |
| 写入点 `file:line` | 新 helper（如 `_record_gate_consumption`）在 F0 表 6 个点各调一次：`conductor.py:353-357`、`:358-369`、`:370-375`、`:2349-2355`、`:2385-2391`、`:2848-2850` 之后 | `roadmap.py` 新 `update_consumed_gates(text, ids)`；调用点与写入点在**同一文件同一锁内**（`:398-401` / `:2345-2347` / `:2385-2387`）⇒ 转换与记录**原子同时落盘** | 无（记录已存在） | 新 helper（如 `_mark_gate_consumed(project_root, st, gate, outcome)`）在同样 6 个点各调一次；字段文本重写需新的"只重写目标行"纯函数（对照 `gate-writer.ts:99-131` 的语义） |
| 读取点 | `_consumed_gate_ids:297-312` 改读 ledger（union timeline 回退）；调用点不变（`:341`/`:2315`/`:345`） | 同左，读 roadmap 头 | `:297-312` 不变 | `gates.Gate` 增字段；`_consume_answered_gates:341` 与 `_apply_stalled_approvals:2315` 改判 `gate.consumed_at is not None`（timeline 反推保留为回退） |
| 原子性 | 单文件 append（`open(a, newline="\n")`），单写者=conductor，**无需锁**（照抄 timeline 的"单写者 append-only"协议）；compaction/backfill 才需 `.mw/gate-consumption.lock` | **最强**：与转换同文件同锁（`.mw/roadmap.lock`，`conductor.py:397-401`）⇒ 一次 `write_text` | 不适用 | 与转换**不同文件不同锁**（roadmap.lock 先、gates.lock 后，**不嵌套**，无死锁）⇒ 无跨文件原子性 |
| 锁名冲突 | `.mw/gate-consumption.lock` 实测无冲突（现有：workers/roadmap/gates/key-*/xkey-ledger/autopilot-config/index） | 复用 `.mw/roadmap.lock`（无新锁） | 无新锁 | 复用 `.mw/gates.lock`（`:2097`/`:2181` 已在用；`_create_gate:2159-2187` 也是它） |
| 崩溃恢复语义 | 撕裂尾行按 timeline 同法跳过（`timeline.py:_read_events` 范式）；**记录先于/后于转换**决定"重复应用"还是"丢答案"。正确序：**转换落盘后**再 append（记录丢失 ⇒ 重放 ⇒ 幂等；记录抢先 ⇒ 答案永久丢失） | **天然正确**：同一次写盘里同时生效，不存在窗口 | 不适用 | 同 A：转换后写字段。**额外**：字段缺失 = 未消费 ⇒ 自动重试，行为与今天一致 |
| 跨轮转持久 | ✅（文件不随 timeline 轮转） | ✅ | ❌ **不解决已有丢失**（JC 09-11 记录已剪掉）；且要覆盖实测 stage 寿命（`max 150.53h`，仍在跑 `≥211h`）需要保留约 100MB 级日志（10MB × 2 代 ≈ 32h 观测窗） | ✅ |
| 抗 gate id 重用 | ❌ 需**复合键**（id 会被重用：FM 归档 6684 个后 `max=10` ⇒ 下次 create = `gate-0011`）；否则持久 ledger 会永久毒化新门（答案被静默丢弃） | ❌ 同 A | ⚠️ 时间窗内缓解 | ✅ **天然免疫**：记录随文件存亡，新文件无字段 |
| 抗被审方伪造（AC-030） | ❌ 路径 `.agenticdoc/_autopilot/gate-consumption.jsonl` **不在** guard 覆盖内（guard 只封 `.../gates/**`，`xkey-gate-guard.ts:46-51`）⇒ worker 可用 `write`/`bash` 追加伪造记录**抑制人工答案** | ❌ **最差**：roadmap-writer worker 的唯一写目标就是 `_roadmap.md`（RQ-13 F2 IA-6 `:550-556`）⇒ 被审方可以直接重写记录载体 | ✅（只读） | ✅ gate 目录已被 guard 封堵（`isXkeyGatePath` → `.../gates/**`，`:125-133`/`:216-241`） |
| 读取代价 | +1 文件全量扫描，且**随已消费数无界增长**（需 compaction） | 0（roadmap 每 tick 已解析） | `query_events` 读取量随代数线性增长（现 2 代） | 0（`gates.enumerate` 每 tick 已读全部 gate 文件；`_consumed_gate_ids` 的整份 timeline 扫描**可删**，是性能净收益） |
| 迁移/回填 | 需 seed：从 timeline 反推 + 单调谓词（F7） | 同 A，且 roadmap 被 roadmap-writer 整体重写时会丢失记录（额外一次回填） | 无（不可回填已剪记录） | 同 A，且无"记录载体被重写"风险 |
| schema/回归成本 | 0（不碰 gate schema） | 需扩展 `_DOC_FIELDS`（`roadmap.py` 文档头闭集 `generated_at`/`goal_mtime`）+ TS roadmap 解析 | 0（只改 2 个常量） | 需扩 12→13 字段：`gates.py:68-84`、`status-model.ts:571-591`、`test_autopilot_gates.py:220-221`（`len(keys)==12`）、`[VERIFY] VC-005 roundtrip_fields` 行、文档串"12 fields" |
| GC-1/GC-3 | 合规（每 tick 由文件重推；append-only，无内存态）；GC-3 需声明压缩锁 | 合规（无新落盘状态）；复用现锁 | 合规（无新状态） | 合规（每 tick 由 gate 目录重推）；复用现锁 |

#### F1.2 逐项排除

- **B（roadmap 侧栏）排除**：记录载体 = roadmap-writer 的**唯一写目标**，一次提案重写即全丢；且它把"已消费"绑在"当前提案版本"上，语义错位（消费是 gate 的属性，不是 roadmap 的属性）。唯一优点（与转换原子同落盘）被 D 的"转换后写字段 + 幂等转换"替代。
- **C（扩大保留代数）不足以作为修法，只作补充加固**：它**无法恢复已剪记录**（JC 的 09-11 `gate-0001` 事件不在任何现存代里），因此对 `closed → running` 回退**零作用**；且"保留多久"无法用字节数表达（要覆盖 `max 150.53h` 的 stage 寿命，需按事件率估算约 100MB 级；轮转本身仍在剪）。可作为"提高 timeline 保留上限"的独立加固项，但**不得**当作 AC-028 的修法。
- **A（ledger）可行但需三项前置**：复合键、guard 扩展、compaction 锁。若 D-105 schema 冻结不可动，A 是首选退路。
- **D 的唯一硬成本**是 12→13 字段的跨语言 schema 扩展 + 一条冻结断言。核对结论：**扩展是安全的**——
  - Python 侧：`_to_gate` 对未知字段 fail-closed，但新字段入 `FRONTMATTER_FIELDS` 后合法；`_REQUIRED_FIELDS:86-88` 不动（新字段可选，缺省 None）。
  - TS 侧：`GATE_FRONTMATTER_FIELDS`（`status-model.ts:571-591`）同表修改即可；`parseGateFile:660` 即恢复接受。
  - 写者兼容：`gate-writer.ts:99-131` 只重写 `ANSWER_FIELDS` 4 行，**其余行逐字保留**（含 `\r`）⇒ 人工/TS 应答不会抹掉 conductor 写的字段。
  - 反向兼容：旧 gate 文件无该字段 ⇒ 解析为 None ⇒ 未消费 ⇒ 走 timeline 回退，行为与今天一致。

#### F1.3 推荐

**主选 = D（gate 文件字段 `consumed_at`/`consumed_seq`）+ timeline 反推作为只读回退（union）**，并保留 D1 的正则修正给回退路径。理由（按判据排序）：
1. 四维判据唯一全过（跨轮转持久 / 抗 id 重用 / 抗被审方伪造 / 零新增读取代价）；
2. 它把消费记录放回**被消费对象本身**，使"这个答案被应用过了吗"成为单文件局部查询，与 RQ-14 F4.4 的 L8「同 scope 历史已答门（重放检测）」共用同一数据面；
3. 顺带删除每 tick 两份 20MB 级 timeline 全量扫描（性能净收益）；
4. schema 成本可控且有实测证据（TS 保留未知行、Python/TS 闭集各一处）。

**退路 = A（ledger）**：仅当 P-018/P-019 消费点检查判定 D-105「12 字段」在本 key 内不可动。此时 A 必须同时带：`(id, created_at)` 复合键、`xkey-gate-guard.ts` 增加 ledger 路径封堵（或把 ledger 放进 `gates/` 内以复用现有封堵，如 `gates/.consumed.jsonl`——注意 `gates.enumerate` 用 `GATE_FILE_RE` 过滤，非 gate 文件被忽略，但需确认无其他工具把目录内额外文件视为损坏）、`.mw/gate-consumption.lock` 下做 compaction。

### F2 【latent】D1 修法：`gate-\d{4}` → `gate-\d+`

**现状锚点**：`conductor.py:310`：
```python
m = re.match(r"(gate-\d{4})\b", str(ev.get("detail", "")))
```

**精确替换串**：
```python
m = re.match(r"(gate-\d+)\b", str(ev.get("detail", "")))
```
（等价的更强形式：`re.match(r"(gate-\d+)(?=\s|$)", ...)`；两者在本卡的 6 个 detail 形状上等价。**不改 `re.match` 的 pos-0 锚定**——F0 逐点核对证明 6 处 detail 均以 gate id 起头。）

**为什么能覆盖 5/6 位**：
- `\d+` 贪婪匹配**全部连续数字**（10000、100000 均可）；其后的 `\b` 是 word/non-word 边界：数字是 word 字符，紧随的 ` `（detail 里是空格）或串尾均为 non-word ⇒ 边界成立。
- `\d{4}` 覆盖不了 5 位**不是"匹配太少然后回退失败"这么简单**：`\d{4}` 先吞 `1000`，随后要求 `\b`，而下一个字符是数字 `0`——两个 word 字符之间**不存在** boundary；引擎回退也无其他位数可选（固定 4）⇒ 整体失败。这就是"静默失效"的机制。

**反证（可执行最小构造，本卡已实测）**：
| 输入 detail | 修复前 `(gate-\d{4})\b` | 修复后 `(gate-\d+)\b` |
|---|---|---|
| `gate-0001 approved → k running` | `gate-0001` | `gate-0001` |
| `gate-9999 approved → k running` | `gate-9999` | `gate-9999` |
| **`gate-10000 approved → k running`** | **`None`** | **`gate-10000`** |
| `gate-100000 approved → k running` | `None` | `gate-100000` |
| `gate-6687 approved → k running` | `gate-6687` | `gate-6687` |

命令（与 RQ-11 F6-D1 同源，可在 verify 期直接复跑）：
```
python -c "import re;print(re.match(r'(gate-\d{4})\b','gate-10000 X'));print(re.match(r'(gate-\d+)\b','gate-10000 X'))"
```
期望：第一行 `None`，第二行 `match='gate-10000'`。**还原缺陷（把 `\d+` 改回 `\d{4}`）⇒ VC-D1 变红**。

**id 生成是否保证单调递增**：
- `gates._next_seq:246-259`：`max(现存 GATE_FILE_RE 命中的 id) + 1`，每次调用**重新扫目录**，无内存计数器 ⇒ **同一 `gates/` 目录内严格单调、永不回绕**（即使 conductor 重启）。
- `gates.create:280`：`gate_id = f"gate-{seq:04d}"`。`:04d` 只做**左补零到 4 位**，不截断 ⇒ `seq=10000` 渲染为 `gate-10000`，且 `GATE_ID_RE`/`GATE_FILE_RE:90-91` 均为 `(\d+)` ⇒ 5/6 位 id **被 schema 接受**（D1 的失效不是 schema 拒绝，而是**消费反推静默漏读**）。
- **可重用/回绕的真实条件**：任何把 gate 文件移出/移删 `gates/` 的操作都会降低 `_next_seq`。实测 FM：`gates/` 现存 max=10，`_gates-flood-20260924/` 含 `0004..6687` ⇒ 下一次 create = **`gate-0011`（已被用过的 id）**。

**id 重用对影响面的改变（关键，决定载体必须抗重用）**：
| 场景 | 修复前（`\d{4}`） | 修复后（`\d+`） |
|---|---|---|
| 5/6 位 id 首次出现 | 消费集合漏掉该 id ⇒ **fail-open：可重放**（重复应用同一个人工答案） | 正确记录 ⇒ 不重放 |
| 旧 id 被重用且旧 id **曾入消费集合** | 若旧 id 是 4 位：新门被静默跳过 ⇒ **fail-closed：答案永久丢弃**（今天就存在） | 同左（正则扩大反而让 5 位 id 也进入这个风险面） |
| 旧 id 被重用但旧门从未被应答 | 无影响（FM 洪泛门全 `pending` ⇒ 今天"侥幸安全"） | 同左 |

⇒ 结论：D1 只改位数**不足以**闭环；它把"漏读导致重放"换掉，但会（配合 id 重用）暴露"按 id 索引的持久集合导致丢答案"。**抗 id 重用必须由载体解决**：D（字段随文件）免疫；A（ledger）必须复合键 `(id, created_at)`。这是把 D1 与 F1 绑在同一波的理由。

**两侧镜像面**：Python 单侧（`conductor.py:310`），无 TS 逻辑镜像。但若采用方案 D，则两组镜像面随之出现：`gates.py:68-84` ↔ `status-model.ts:571-591`（字段表）、`gates.py` 字段重写纯函数 ↔ `gate-writer.ts:99-131`（行保留语义）。

### F3 【latent】D2 修法：reject 路径的消费守卫对称化

**现状锚点**：
- approve：`_apply_stalled_approvals:2315`（`consumed = _consumed_gate_ids(...)`）、`:2319`（`if gate.id in consumed: continue`），注释 `:2320-2329` 记录 FM 6684 洪泛事故。
- reject：`_apply_stalled_rejections:2363-2394` —— **既无 `consumed` 读取，也无 `gate.id in consumed` 判断**；唯一去重是 `status_of.get(key) != "stalled"`（`:2376`）。

**对称化设计**（设计面，不含实现）：
1. 在 `:2371`（进入循环体 `:2372` 之前）取一次消费集合——**与新载体一致**：方案 D 下改为"读 `gate.consumed_at is not None`"；方案 A 下读 ledger ∪ timeline。
2. 在 `:2376` 之前插入与 `:2319` 同形的守卫：`if <consumed(gate)>: continue`，并保留现注释风格说明"重复应用会重复写 roadmap、重复删 bad-draft marker、重复追加事件"。
3. 在 `gate-answered`（`:2388`）与 `stalled`（`:2389`）之后，按 F0 的 6 点协议**写消费记录**（D：字段；A：append）。
4. **顺序**：先写 roadmap（`:2385-2387`）→ 再写消费记录 → 再追加 timeline 事件。理由：roadmap 是效果、消费记录是去重、timeline 是审计；三者非原子，任一步崩溃都要求"效果先于记录"以保住"记录丢失 ⇒ 重放 ⇒ 幂等"的性质（反向会把答案丢成永久未应用）。

**反证（可执行最小构造）——"重复应用 reject"**：
- **输入**：临时项目根 `R`；`_roadmap.md` stage 1 含 key `k1`，`> key-status: k1=stalled`；`gates/gate-0001.md` = `kind: stalled`、`status: rejected`、`key: k1`、`answered_at` 非空；timeline 里**已存在**一条 `gate-answered detail="gate-0001 rejected → k1 closed-legacy"`（模拟"已消费但 key 又被置回 stalled"）。
- **操作**：`conductor._apply_stalled_rejections(R, st, {"k1": "stalled"}, {"k1": 1})`。
- **期望观测**：
  - 修复前：`_roadmap.md` 被改写为 `k1=closed-legacy`（`roadmap.update_key_status:2385` 返回差异文本），timeline **新增**第 2 条 `gate-answered`（同 id 第二次），并再次调用 `closure.delete_bad_draft_marker`（`:2391`）⇒ 断言"roadmap 字节不变"与"事件增量 == 0"均**失败**。
  - 修复后：函数体在 `:2376` 前 `continue` ⇒ `roadmap` 字节不变、`st.timeline` 无新事件、`status_of` 不变 ⇒ 断言通过。
- **可达性论证**（为什么不是纯理论）：`mark_stalled:3944-3994` 只对 `key_status == "stalled"` 短路（`:3958`），**不禁止 `closed-legacy → stalled`**；因此"reject 已应用 → key 变 closed-legacy → 之后又被置回 stalled"这条路径在代码上开放。触发它的现实入口有两个：**(i)** D4 类重放把 stage 重开、key 被重新派发并再次失败 ⇒ `mark_stalled` 写回 `stalled`；**(ii)** 人工改 `_roadmap.md` key-status（这是唯一既有解除路径）。修复前该组合会让**一个已消费的人工 reject 第二次生效**（且无声）——正是 AC-022 D2 要拦的形状。

**与 D4 的关系**：D2 的守卫只防"同一 gate 被消费两次"；若消费记录本身丢失（D1/轮转），D2 也拦不住。因此 D2 必须建在新载体之上，且需 D4 的单调性防止 key 无端回到 `stalled`。三者是"载体（记录）+ 守卫（读记录）+ 单调（不许回退）"的组合。

**两侧镜像面**：Python 单侧（`conductor.py:2363-2394`）。若走方案 D，附带 `gates.py`↔`status-model.ts` 的字段镜像（同 F2 尾注）。

### F4 【latent】D3 修法：TS `EVENT_TYPES` 与 `timeline.py` 逐项对齐

**现状锚点**：
- Python：`timeline.py:67-84`，`EVENT_TYPES` = 17 类（含 `"target-config-rejected"`，`:81`）。
- TS：`status-model.ts:779-796`，`EVENT_TYPES` = 16 类（**缺 `"target-config-rejected"`**）。
- 影响面：`console.ts:261` 以 `nonBeatFilter()`（`status-model.ts:801-806` = `EVENT_TYPES - {beat}`）作为 `queryTimeline` 的 include-set（`:921` `evFilter.has(e.ev)`）⇒ 默认 `/autopilot timeline` **静默隐藏** `target-config-rejected`；`--all`（filter `undefined`）显示。Python 侧当前无 `ev_filter` 调用点（全仓 grep 零命中），故只有 TS 读面漂移。
- 生产样本：FM/E2/JC 三项目 `target-config-rejected` 事件数 **0 / 0 / 0**（F0 数据表）⇒ `[latent]`：这是**代码级漂移**，尚未产生可观测错误。

**修法（设计面）**：在 `status-model.ts:779-796` 的集合中、按与 `timeline.py:67-84` 相同的相对位置补 `"target-config-rejected"`（即 `"type-rejected"` 之后）。不新增其他能力。

**跨语言一致性判据（P-021）**：
1. **静态集合相等**（机器判、无需跑 TS 运行时）：Python 测试读取 `status-model.ts` 文本，用与 `EVENT_TYPES = new Set([...])` 匹配的解析（同 `test_autopilot_config_parity.py:57` 的既有"读 TS 源做对比"范式），断言 `set(py) == set(ts)`，失败时输出 `py_only` / `ts_only` 两个差集。
2. **运行时两侧都跑**（P-021 原文要求）：verify 期同时跑 Python 侧 `test_autopilot_timeline.py` 与 TS 侧 extension 测试；并把 `[VERIFY] ts_mirror_drift=no` 作为门禁项。
3. **反向用例**：构造符合 Python 事件的 timeline 行（`{"ev":"target-config-rejected",...}`），断言 TS `nonBeatFilter().has("target-config-rejected") === true`，且默认 `queryTimeline(path, 0, nonBeatFilter())` 能返回该事件。**还原缺陷（删掉该条目）⇒ 该断言变红**。

**两侧镜像面（明确）**：一个语义面 = `timeline.EVENT_TYPES`（`timeline.py:67-84`）↔ `EVENT_TYPES`（`status-model.ts:779-796`）；谁新增事件类型都必须两侧同改。**这条判据在 D4 之后会立刻被用到**：D4 的"拒绝降级"留痕若采用新事件类型（如 `stage-reopen-refused`），必须走同一套对齐；因此 D3 的 parity VC 是 D4 留痕的**前置**。

### F5 D4 修法：stage 状态单调性

**现状锚点**：`conductor.py:379-405`（`_set_stage_status`）。唯一判据是 `:392` `if stage is None or stage.status == new_status: return False`——**"不同就写"**，没有方向。实证（RQ-13 F5）：JC 2026-09-26T04:37:27 因消费记录丢失重放 `gate-0001`，`:353` 调 `_set_stage_status(1, "running")`，把 09-17 已 `closed` 的 stage 1 改回 `running`；同 tick `_stage_closure:629` 因 key 全 `done` 再次满足 ⇒ 生成 `gate-0008`。

**F5.1 合法转换表（设计判据）**

状态词表：`roadmap.STAGE_STATUSES:53-61` = `pending / approved / running / closed / closed-human / halted`（TS 镜像 `status-model.ts:321`）。

| 从 → 到 | 合法性 | 由谁触发 | 判据 |
|---|---|---|---|
| `pending → approved` | ❌（conductor 从不写该值；现全仓无写入点） | — | 保持不可达 |
| `pending/approved → running` | ✅ | `_consume_answered_gates:352-357`（stage-confirm approved） | 目标状态**严格高于**当前状态 |
| `running → closed` | ✅ | `:358-369`（stage-close approved） | 严格上升 |
| `running → halted` | ✅ | `:370-375`（stage-close rejected） | 严格上升（进入终态族） |
| `X → X` | ⚪ no-op | 任意 | 现状已处理（`:392`） |
| `closed/closed-human/halted → running` | ❌ **禁止**（除非显式人工授权） | — | 目标状态**不高于**当前状态 ⇒ 拒绝 + 留痕 |
| `closed/closed-human/halted → closed/closed-human/halted`（互转） | ❌ 禁止 | — | 终态族内互转一律拒绝（避免 reject 把已 closed 的 stage 变 halted 之类的语义漂移） |
| `running → pending/approved` | ❌ 禁止 | — | 降级 |

实现形态（设计面）：`_set_stage_status` 增加一个**纯函数判据**（如 `_stage_transition_allowed(current, new) -> bool`），内部用单调序 `pending=0 < approved=1 < running=2 < closed=closed-human=halted=3（终态族）`；判据 = `rank(new) > rank(current)` 且**不是同族终态互转**。判据必须**纯、可单测**（输入两个字符串、输出 bool），以便两侧/多处复用；**不引入新 stage 状态值**（避免 `STAGE_STATUSES` 两侧扩展，见镜像面）。新增状态值会牵动 `roadmap.py:53-61` ↔ `status-model.ts:321` 两侧 + `update_stage_status` 校验，故设计上**不改词表**。

**F5.2 合法重开：由谁授权、留什么事件**

- **授权者 = 人**。现有唯一解除路径就是人工改 `_roadmap.md`（`_stage_activation:442-443` 对 `halted` 明确写了"pause until a human edits the roadmap"）。设计上**conductor 永不主动重开**：`_set_stage_status` 的调用点只有 4 处（`:353`/`:360`/`:371` + 无其它），全部来自门应答；单调判据让"重放旧答案"不再构成授权。
- **人工重开的记录方式**：
  - 最小形态（推荐，零新 schema）：人在 `_roadmap.md` 里把 `> status:` 从 `closed` 改回 `running`（或 `pending`）。此时 conductor 观测到 `stage.status != new_status` 的语义已由人完成，`_set_stage_status` 不再介入；**但这条人工改动当前不留任何时间线痕迹**（`roadmap.update_*` 是覆盖写，`generated_at` 之外无可回读历史——RQ-14 已记录该缺口）。
  - 可观测化（推荐同时做）：conductor 在**拒绝一次降级**时留痕（见 F5.3），这样"有人试图重开 / 有重放"在 timeline 上可见；至于"人改了 roadmap 使其前进"，可用既有的 `config` 分支（`:404`）风格记录一次检测事件（读到的 stage 状态与上一 tick 视图不一致时）。**若为此引入新事件类型，必须先完成 D3 的两侧对齐。**
- **与 D2 的关系**："合法重开"授权的是 **stage**；D2 授权的是 **key**（`closed-legacy → stalled` 由人工改 roadmap 或 D4 类重开间接产生）。两者共用同一原则：**允许人工、禁止机器重放**。D4 拦 stage 层回退，D2 拦 key 层重复应用；组合起来才闭合"旧答案不得二次生效"。

**F5.3 反证（可执行最小构造）——"重放已答门后 stage 不得回退"**

- **输入（JC 式最小复现）**：临时项目根 `R`；`_roadmap.md`：`## Stage 1` + `> status: closed` + `### Keys` 表含 `k1`、`> key-status: k1=done`；`gates/gate-0001.md` = `kind: stage-confirm`、`stage: 1`、`status: approved`、`answered_at` 非空；timeline **不含**该 gate 的 `gate-answered`（模拟轮转剪掉）；stage 2 不存在。
- **操作**：`conductor._consume_answered_gates(R, st)`（或 `tick(R, st)` 的 §5.1 F 步）。
- **期望观测**：
  | 观测点 | 修复前（现状） | 修复后（D4） |
  |---|---|---|
  | `_roadmap.md` stage 1 `> status:` | **`running`**（`_set_stage_status` 写入） | **`closed`**（拒绝降级） |
  | timeline 新增事件 | 1 条 `gate-answered`（`"gate-0001 approved → stage 1 running"`） | 1 条**拒绝**事件（点名 `gate-0001`、`closed→running`），**无** `gate-answered` |
  | 同 tick 后 `_gate_open(R,"stage-close",stage=1)` | **True**（`_stage_closure:629` 满足 → 新门） | **False** |
  | `R/gates/` 文件数变化 | +1（`gate-0002` stage-close） | 0 |
- **正向对照（防"一刀切禁写"）**：同一 fixture 里把 stage 1 设为 `running`、放一个 `stage-close approved` 门 ⇒ 期望 stage 变 `closed` 且发出 `gate-answered` + `stage-close`（证明合法上升未被误伤）。
- **耐久性对照（针对根因）**：先用合法路径应用一次答案（stage `pending → running`），**删除整个 `timeline.jsonl*`**（模拟轮转/清空），再跑一次 ⇒ 修复后仍不得回退/重放；这测的是**载体**（F1）而不是单调判据，两条 VC 分开跑。

**F5.4 副作用与边界（设计必须声明）**
- `_set_stage_status` 返回 `False` 会连带**抑制** `gate-answered`（`:353`/`:360`/`:371` 的 `if` 条件）与 `_ensure_next_stage_gate`（`:369`）——这正是我们要的（重放不产生副作用），但必须同时保证**不再每 tick 重试同一件事而产生噪声**：拒绝事件是"重试仍被拒"的可观测替代，且消费记录（载体）一旦落盘就不再重试。若载体记录也丢了（极端：字段被人工删除），则该 gate 会每 tick 被拒一次 ⇒ **拒绝事件必须去重**（同一 `(gate.id, current, new)` 只在首次拒绝时写），否则会把"cap 阻塞零痕迹"换成"拒绝洪泛"。这是 D4 的**必须**设计约束。
- 单调判据只约束 conductor；**人工改 roadmap 仍可任意回退**（有意保留的逃逸口）。判据的实现必须放在 conductor 的写入路径（`_set_stage_status`），**不得**放进 `gates`/`roadmap` 的纯文本层（那里无状态语义）。

**两侧镜像面**：
- `roadmap.py:53-61`（`STAGE_STATUSES`）↔ `status-model.ts:321`（`STAGE_STATUSES`）：**若设计选择"不加新状态值"，此镜像无需改动**（本卡推荐）；
- `roadmap.py:492-503`（`update_stage_status` 的值域校验）↔ TS 侧 roadmap 解析 `status-model.ts:493`（枚举校验）：**迁移合法性**属于 conductor 语义，TS 只做枚举校验 ⇒ 无需镜像；但若将来 TS 面板要显示"为何没有回退"，需要读新事件（依赖 D3）。
- 若采用"拒绝即写新事件类型"：`timeline.py:67-84` ↔ `status-model.ts:779-796` 必须同改（**D3 前置**）。

### F6 顺序约束与耦合

**依赖顺序图（文字）**

```
（第 0 波：无依赖、可立即）
  D3  EVENT_TYPES 两侧对齐 + parity VC   ──┐（任何新事件类型的硬前置）
  D1  gate-\d+ 正则修正（回退路径）        │
                                          │
（第 1 波：载体决定 → 一次做完）           │
  载体选型（F1：D 或退路 A）              │
    ├── D2  reject 侧消费守卫（读新载体）  │
    └── D4  stage 单调判据 + 拒绝留痕 ◄────┘（留痕事件需 D3 已对齐）
                                          │
（第 2 波：只在前两波落地后才可开）        │
  自动决策 / 影子模式（AC-016/024/025）◄──┘  ← AC-022 顺序硬要求：D1 先于自动决策
      │
  延后复核（AC-027）+ 批量复核            ← AC-028 含义：D4 先于任何"可跨轮转重放"的能力
      │
  （可独立并行）C 类加固：提高 timeline 保留代数（仅加固，不替代修法）
```

**逐条依赖理由**
1. **D1 必须先于自动决策**（spec 风险 22 / AC-022 硬要求）：自动决策会把 gate 产出速率从"人工节奏"提升到"tick 节奏"（实测洪泛 `585.8 门/h`），一旦越过 4 位，消费反推静默失效 ⇒ 自动决策会重演 FM 洪泛。D1 是**最便宜、最先**的一步。
2. **载体必须先于 D2/D4**：D2 的守卫与 D4 的"已消费"判据都读同一份记录；载体变更会同时改写这两处读取点（`:341`、`:2315`、`:2367` 附近）。若先做 D2/D4 再换载体，等于把三处读取逻辑写两遍。
3. **D3 必须先于**任何引入新事件类型的设计（D4 的拒绝留痕、AC-018 的 auto 审计事件、AC-030 的来源字段）：`EVENT_TYPES` 是**闭集之外的 include-set**，缺项会导致新事件在默认视图**静默消失**——正是 AC-018「新机制必须留痕」会被反向破坏的地方。
4. **D4 必须先于"延后复核 / 拉长保留窗 / 批量复核"**：这三类能力都在扩大"旧答案被重新应用"的窗口（RQ-13 F5 原文："延后越久、跨 timeline 代越多，这类窗口越大"）。D4 是窗口的安全阀。
5. **D2 与 D4 无先后，但必须同波**：单独 D2 不能防"消费记录丢失"（记录没了就没有 `gate.id in consumed` 可查）；单独 D4 不能防 key 层重复应用（`closed-legacy → stalled` 是 key 层，不经过 `_set_stage_status`）。二者组合才闭合。

**耦合矩阵**

| 变更 | D1 | D2 | D3 | D4 | 载体 |
|---|---|---|---|---|---|
| 载体（F1）变更读取点 | 影响 D1 回退路径的去留 | **直接改写 D2 的守卫读取** | 无 | **直接改写 D4 的"已消费"判据** | — |
| D1 正则 | — | 共享 `_consumed_gate_ids` | 无 | 共享 | 若选 D：D1 变成"回退路径修正"，仍需保留 |
| D3 pariry | 无 | 无 | — | **D4 留痕的前置** | 若选 D 且新增字段事件，也需 |
| D4 单调 | 无（不同层） | **复合可达**（`mark_stalled` 允许 `closed-legacy→stalled`） | 若加拒绝事件则强耦合 | — | 读载体的"已消费" |

### F7 迁移方案（既有项目如何回填已消费 id）

**原则：不回填也能安全运行（fail-soft 并存），回填是"消除残余重放面"的加固。**

1. **共存读取（必做，零迁移）**：新的消费判据 = `载体记录（新）∪ _consumed_gate_ids 的 timeline 反推（旧，含 D1 修正）`。效果：
   - 新应用的门 ⇒ 立刻落进新载体 ⇒ 不受轮转影响；
   - 旧门 ⇒ 仍可由**现存 timeline 代**反推（FM/E2/JC 现存代覆盖最近窗口，见 F0 数据表）；
   - 已被剪掉记录的旧门 ⇒ 既不在新载体也不在 timeline ⇒ 仍需 D4 单调判据兜底（JC `gate-0001` 就是这一类）。
2. **一次性 backfill（可选，建议做）**：对 `gates.enumerate()` 的每个 `status != pending` 的 gate，按"转换是否已被当前文件状态吸收"判定：
   - **key 级**（`stalled` approve/reject）：若当前 `key-status` ∉ `{stalled}` ⇒ 已消费（这就是现状 `:2321`/`:2376` 的幂等判据本身）。
   - **stage 级**：用 D4 的单调序做"已被取代"判定——若 `new_status` 不严格高于当前 `status`（例如 stage-confirm approved 目标=`running` 而当前=`closed`）⇒ 记为已消费（**JC `gate-0001` 命中此条**）。
   - **xkey**：若 ticket 状态已越过 `approved/pending-auth`（或 ledger 已有该 `request_id` 记录）⇒ 已消费。
   - 写入必须：`acquire_conductor_lock(project_root, "gates")`（方案 D）或 `"gate-consumption"`（方案 A），且**幂等**（已记录则跳过），并在完成时追加一条 `config` 事件（`backfill consumed N gates`）作为一次性动作的审计痕迹。
   - 执行入口：`mw autopilot` 的一个一次性子命令（与 `mw autopilot verify set|show|clear` 的既有范式一致，`mw.py:3514+`），**不在 tick 里隐式跑**（避免每 tick 变慢与不确定写入）。
3. **残余面（必须如实声明）**：**"key 曾 stalled → 旧 approve 已消费 → 记录被剪 → key 又 stalled"** 这一形态（FM 洪泛的根因形态）在磁盘上**不存在可判定证据**（gate 文件是 `answered/approved`，但 key 也确实是 `stalled`，二者不可区分"已应用后又停滞"与"未应用"）。⇒ 回填**无法覆盖**，只能靠":2321"判据 + 新载体的时间边界（迁移后新发生的都能覆盖）。这与 RQ-11 的"数据缺口 7"一致：需要对 auto 决策做重放必须先有留痕。
4. **回滚**：方案 D 的字段可整体剥离（写回空值）→ 回退到 timeline 反推；方案 A 的 ledger 文件删除即回退。**D4 的单调判据不建议提供运行时开关**（配置键会触发两侧镜像 + 语料重冻，见风险 16）；若确需，退路是人工改 `_roadmap.md`（本就在判据之外）。

### F8 VC 候选（每条：字段级断言 + 反证）

> 命名按仓库惯例：Python 侧放 `packages/multi-workers/test_autopilot_gate_consumption.py`（新文件）；D3 的静态 parity 可并入该文件或 `test_autopilot_config_parity.py` 同风格。verify 期 D3 必须**两侧都跑**（P-021）。

**VC-D1（gate id 位数）**
- 构造：临时 timeline.jsonl 写入 4 条 `gate-answered`，detail 分别为 `gate-0001` / `gate-9999` / `gate-10000` / `gate-100000` 起头。
- 操作：`conductor._consumed_gate_ids(root)`。
- 字段级断言：返回值 `== {"gate-0001","gate-9999","gate-10000","gate-100000"}`；且差集 `expected - actual == set()`、`actual - expected == set()`。
- 附加断言（防回退）：`re.search(r"gate-\\d\{4\}", inspect.getsource(conductor))` 为 `None`（源码级锚定）。
- 还原缺陷 ⇒ `gate-10000`/`gate-100000` 缺失 ⇒ 变红。

**VC-D2（reject 侧消费守卫）**
- 构造/操作：见 F3 反证。
- 字段级断言：`rm_path.read_text() == before`（字节相等）；`len(st.timeline events) == 0` 增量（或 `[e for e in new_events if e["ev"]=="gate-answered"] == []`）；`closure.delete_bad_draft_marker` 未被调用（monkeypatch 计数 == 0）。
- 还原缺陷 ⇒ `status_of[k1] == "closed-legacy"` 且事件增量 ≥ 1 ⇒ 变红。

**VC-D3（跨语言事件词表 parity）**
- 构造：读 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` 文本，解析 `EVENT_TYPES = new Set([...])`。
- 字段级断言：`py_only = set(timeline.EVENT_TYPES) - set(ts) == set()`；`ts_only == set()`；`type("target-config-rejected") in ts`。
- 运行时断言（两侧）：TS 侧 `nonBeatFilter().has("target-config-rejected") === true`，且对含该事件的 fixture 调 `queryTimeline(path, 0, nonBeatFilter())` 返回长度 1。
- 还原缺陷 ⇒ `ts_only` 或运行时断言为假 ⇒ 变红。

**VC-D4（stage 单调性 + 拒绝留痕）**
- 构造/操作：见 F5.3。
- 字段级断言（主）：`roadmap.parse_roadmap(after).stages[0].status == "closed"`；`_gate_open(root,"stage-close",stage=1) is False`；`[e for e in events if e["ev"]=="gate-answered" and "gate-0001" in e["detail"]] == []`。
- 字段级断言（留痕）：`[e for e in events if e["ev"]=="<refusal-ev>"]` 长度 == 1，且其 `detail` 含 `gate-0001`、`closed→running`（逐字）。
- 字段级断言（正向对照）：另一 fixture 中 `running` + `stage-close approved` ⇒ `status == "closed"` 且存在 `gate-answered`。
- 字段级断言（去重）：连续跑 3 次 tick ⇒ 拒绝事件数恒为 1（防"拒绝洪泛"）。
- 还原缺陷（删掉单调判据）⇒ 主断言中的 `status` 变 `running`、`_gate_open` 变 True ⇒ 变红。

**VC-D0（载体持久性，针对 AC-028 根因；方案 D 版）**
- 构造：合法应用一次 stage-confirm 应答（`pending → running`），随后**删除全部 `timeline.jsonl*`**。
- 操作：再跑一次 `_consume_answered_gates`。
- 字段级断言：`gate-0001.md` 文本中 `consumed_at:` 非空且 `consumed_seq:` 为整数；`_roadmap.md` stage 1 `> status:` 仍为 `running`；无第二条 `gate-answered`。
- 方案 A 版：ledger 中存在 `(gate_id="gate-0001", created_at="<原值>")` 一行；删除 timeline 后 `_consumed_gate_ids` 仍含 `gate-0001`。
- 还原缺陷（消费判据只读 timeline）⇒ 删 timeline 后出现第二条 `gate-answered` ⇒ 变红。

## 结论 → 决策映射

| AC / 缺陷 | 结论 |
|---|---|
| **AC-022 D1** | 修法面 `conductor.py:310`：`(gate-\d{4})\b` → `(gate-\d+)\b`。判据 = VC-D1（字段级集合相等 + 源码无 `\d{4}`）。反证已实测（`gate-10000` 修复前 `None`）。**id 单调性**：`gates.py:246-259`/`:280` 保证同目录严格单调，但**跨归档重用**（FM 归档 id 实测见 F2）⇒ 载体必须抗重用。顺序：**D1 先于任何自动决策**（风险 22）。 |
| **AC-022 D2** | 修法面 `conductor.py:2363-2394`：在 `:2376` 前补与 `:2319` 对称的消费守卫，并按 F0 协议在转换后写消费记录。判据 = VC-D2；反证构造见 F3（可达性由 `mark_stalled:3958` 不禁止 `closed-legacy→stalled` 提供）。 |
| **AC-022 D3** | 修法面 `status-model.ts:779-796` 补 `"target-config-rejected"`；判据 = VC-D3（`py_only==ts_only==∅`）+ P-021 两侧运行。影响面 = `console.ts:261` 默认过滤静默隐藏；生产样本 0 ⇒ `[latent]`。 |
| **AC-028 D4** | 修法面 `conductor.py:379-405`：加纯函数单调判据（`pending<approved<running<{closed,closed-human,halted}`，终态族禁止回退/互转，禁止降级），拒绝时留痕（需 D3 先行）且去重；**conductor 永不主动重开**，重开只由人工改 `_roadmap.md`。判据 = VC-D4（字段级 `status=="closed"` + 无 `gate-0008` + 拒绝事件恰 1 条）。与 D2 的关系：D4 管 stage 层回退，D2 管 key 层重复应用，共享"人工可、机器不可"原则。 |
| **AC-028（载体）** | 推荐方案 D（gate 字段 `consumed_at`/`consumed_seq` + timeline 只读回退）；退路 A（ledger + 复合键 + guard 扩展 + compaction 锁）。判据 = VC-D0；方案对比与排除见 F1。 |
| **顺序约束** | 第 0 波 D3 + D1；第 1 波 载体 + D2 + D4；第 2 波 自动决策 → 延后复核。耦合矩阵见 F6。 |
| **迁移** | 共存读取（零迁移即安全）+ 可选一次性 backfill（单调谓词可覆盖 JC `gate-0001`）；残余面（key 曾 stalled 的旧 approve）**不可判定**，如实声明。 |
| **AC-030 交叉** | 方案 D 的字段天然"抗被审方伪造"（gate 目录被 `xkey-gate-guard.ts:46-51` 封堵）；方案 A **不满足**，必须扩展 guard。这是本卡推荐 D 的独立理由。 |
| **AC-027 交叉** | 延后复核的安全阀 = D4（+载体的"可审计"）。RQ-13 的 CC-7 与本卡 D4 同源，本卡给出其合法转换表与 VC。 |
| **P-018/P-019 交叉（冻结判据检查）** | 本卡要动的消费点是：`_consumed_gate_ids`（3 处读取）、`_set_stage_status`（4 处调用）、`_apply_stalled_rejections`。方案 D 额外动 gate schema 与 TS gate 解析（`status-model.ts:571-591`）——**这是本卡最大的跨模块面**，必须在 design 评审时与 D6（gate schema 呈现）卡对齐，避免两卡同时改 `FRONTMATTER_FIELDS` 的冻结断言（`test_autopilot_gates.py:220-221`）。 |

## 数据缺口

1. **D1 无生产触发样本**：三项目最大 gate id = 6687（且已归档到 `_gates-flood-20260924/`），现存 `gates/` max=10/18/8 ⇒ 5 位 id 从未出现。可达性论证（洪泛 `585.8 门/h` 下 4 位到 5 位约 17h）成立，但"实际后果"无实测。需要：受控构造（临时 root 造 `gate-10000`）或一次演练。
2. **D3 无生产样本**：`target-config-rejected` 事件在 FM/E2/JC 均为 0 ⇒ 只有代码级影响（默认视图过滤），无"人因此误判"的实例。需要：造一条事件后用 `/autopilot timeline` 默认视图对比 `--all` 的差异截图/输出。
3. **D4 重放实例 n=1**（JC `gate-0001`）⇒ 频率未知。需要：在 FM/E2 的 timeline 里做"消费记录回放"批量检测（判据：同一 gate id 出现第二条 `gate-answered`，或 stage status 出现降级）——本卡未做全量扫描（超出只读复算范围），建议 verify 期补。
4. **id 重用未产生已观测事故**：FM 的归档门全 `pending`（从未进入消费集合）⇒ "重用 id 撞已消费集合"是模型推理，非实测。需要：构造"旧门已消费 → 归档 → 新门得到同一 id"的临时用例（VC-D0 的扩展）。
5. **方案 D 的迁移工程量未测**：12→13 字段会改 `test_autopilot_gates.py:203/220-221` 的冻结断言与 `[VERIFY] VC-005` 行；是否存在其他消费 12 字段数的文档/测试未穷举（本卡只查了 `test_*.py` 与两个源码文件）。需要：全仓 grep `12 fields` / `roundtrip_fields` / `len(keys) == 12` 的完整清单。
6. **`_consumed_gate_ids` 是否有 TS 侧等价物未确认**：本卡只确认 TS 不做消费（只看 timeline 渲染）；若 TS 有隐含消费判据，方案变更需同步。需要：在 TS 全仓 grep `gate-answered`（非仅 autopilot 目录）。
7. **backfill 的一次性入口落在哪个 CLI 子命令**（`mw autopilot ...`）需要与 AC-018/AC-026 的 CLI 面设计对齐；本卡只给形态，不给命令名。
8. **拒绝事件的去重键与 `advance_stall_ticks` 类既有原语的关系**未展开：本卡建议"同一 `(gate.id, current, new)` 只记一次"，但是否应复用 `_XKEY_PROPOSAL_MAX_ATTEMPTS` 的"计数 + exhausted 标记"范式（`conductor.py:2872`）需在 plan 期定。

[VERIFY] D3: consumed_carrier_recommend=gate-field(consumed_at/consumed_seq)+timeline-readonly-fallback, fallback=ledger(id,created_at composite; requires xkey-gate-guard extension + .mw/gate-consumption.lock) id_generation=gates.py:_next_seq:246-259 max+1 rescan, create:280 f"gate-{seq:04d}" -> strictly monotone within gates dir, NOT across archival (FM gates/ max=10 vs archive gate-0004..6687 -> next create reuses gate-0011) d1_regex_fix=conductor.py:310 r"(gate-\d+)\b" (was \d{4}); \d{4} fails because two digits are not a word boundary; counterexample gate-10000 -> None before, match after d2_guard_missing=conductor.py:2363-2394 vs approve guard :2315/:2319; reachable because mark_stalled:3958 only short-circuits key_status=="stalled" (allows closed-legacy->stalled) d3_ts_drift=status-model.ts:779-796 16 types vs timeline.py:67-84 17 types (missing target-config-rejected); impact=console.ts:261 nonBeatFilter include-set hides it in default timeline view; production samples=0/0/0 d4_anchor=conductor.py:379-405 _set_stage_status only checks "differs" (:391); legal=pending/approved->running->closed|closed-human|halted, terminal family may not retreat or inter-convert; reopen=human roadmap edit only; refusal must leave one deduplicated event (needs D3 parity first) consumption_write_points=6(conductor.py:353-357,358-369,370-375,2349-2355,2385-2391,2848-2850) consumption_read_points=3(conductor.py:341,2315,345) order=D3+D1 first; then carrier+D2+D4; then auto-decision; then deferred review id_reuse_measured=FM archive n=6684 (gate-0004..6687) current dir n=10 timeline_generations_observed=FM 2 files, E2 2, JC 3 (ROTATE_GENERATIONS=2 timeline.py:93-94) vc_candidates=5(D0 carrier durability, D1 regex set-equality, D2 reject guard byte-equality, D3 crosslang set equality, D4 monotonicity+refusal) migration=union read (no migration needed) + optional one-shot backfill via monotone predicate (covers JC gate-0001: target running < current closed); residual= "key re-stalled after applied approve" undecidable on disk scope=design-only,no code changed
