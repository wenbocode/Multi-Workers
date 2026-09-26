# Design: gate 命题重设计（D1 / key `mw-autopilot-slot-capacity` / AC-025 核心）

> 角色：DESIGN 期设计（**只读 + 本文件唯一写面**）。本卡未改任何代码、未答任何 gate、未写 FM/E2/JC 任何文件、未 commit（`git status --porcelain` 与开工时逐字一致，见文末）。
> 代码基线：`H:/git/Multi-Workers` HEAD `4ef71e053`（与 RQ-12/RQ-14 同基线）。本文件所有 `file:line` 为**该工作树实测**（本卡逐条 `Select-String` 复核，非转抄）。
> 输入：RQ-12（`spec-gate-selfverifiable-20260926.md`，命题选层诊断 + 4 个 `stage-close` 反例 + 6/22 verdict 分歧）、RQ-14（`spec-gate-review-material-20260926.md`，14 项最小信息集 + 3/5/6 可得性 + 24/34 证据漂移）、RQ-8（`spec-unattended-stage-closure-20260926.md`，门清单/阻塞面/等待分布）、PM 自采 `spec-gate-proposition-kinds-20260926.md`（xkey case-1 原型 + 命题两分）。
> 边界：**不重做** RQ-12 的"命题选层"分析（本卡把它当既定前提：现状命题=触发条件本身 ⇒ 恒真零信息量）。本卡只做**设计**：把 6 类门的命题**重写**为可机器判定且**有信息量**（可为假）的新命题，并给出证据锚点、自举判定、三分映射、落地成本、VC 候选。
> 数据快照：沿用 RQ-12 `2026-09-26T08:14Z` / RQ-14 `08:2xZ` / RQ-8 `07:43Z` 的只读复算结果，本卡**不重算**这些数字（命题设计不需要新统计；引用的每个数字都标了出处笔记）。

## TL;DR

1. **设计主线：把每类门的命题劈成"事实面"与"政策面"两层**，并只对**事实面**做自动化判定（对齐 PM 自采 F2 / spec AC-025 的"命题两分"）。事实面命题写成"某可证伪的陈述句"，政策面命题（授权/取舍）一律落 case 3。
2. **四判据**（每个事实面命题必须全过）：**F1 可证伪**（给出 disk witness：trigger 真而命题假）、**F2 有信息量**（`trigger ⊬ P`，即命题**不**被建门条件蕴含——这是 AC-025 的"恒真自检"）、**F3 可独立复算**（第三方只读文件能重算，不读 `gate.note`、不读 `answered_*`）、**F4 防伪**（绑 `sha256 + mtime_ns` 快照 + 取证源优先级 + 来源闭集）。
3. **6 门现状命题全部是触发条件的同义反复或散文**（`stage-close` 最硬：命题主语"全部 key 已终态"＝ `conductor.py:629-631` 的建门条件本身；`stalled`/`goal-change`/`xkey-authorize` 的决策核心都不在盘上）。**重写后的最低要求命题**（每条都能为假、都能从盘上判出）：
   - `stage-confirm`：`structural_validation == []` **∧** `goal_sha256 == 当前 goal.md sha`（不是"该不该开 stage"）。
   - `stage-close`：`verdicts_final` 中**每个** key 的最终裁决（按冻结优先级）∈ {meets} 或 key-status ∈ {closed-legacy} **∧** `open_items == []`（不是"全部 key 已终态"）。
   - `stalled`：`reason_code == 复算 cause_class` **∧** `cause_counts` 三项与盘上计数逐字相等 **∧** `false_negative_class != undecidable`（不是"key 已 stalled"）。
   - `budget-exhausted`：`used_rounds == round_limit + credits_used` **∧** L1 `blocking` gaps 非空 **∧** `loop` 未被拒绝/未花凭据。
   - `goal-change`：`goal_sha256_before != goal_sha256_after` **∧** `goal_diff.normative_changed == true`（"mtime 变了"不充分，也不是命题）。
   - `xkey-authorize`：`verify.red_after == 0 ∧ returncode == 0 ∧ ¬timed_out` **∧** `verify.test_id == gate.test_id`（S4 已有）**∧** `blast_radius.files ⊆ write_scope`（后者数据不存在）。
4. **4 个 `stage-close` 反例在"重写后"全部变成可机判的假**（RQ-12 C1–C4）：E2 Stage 2（correction `corrected_value=below`+`counted_as_done=false` ⇒ `verdicts_final != meets`）、FM Stage 1（`C-09`/`NRR-1/2` ⇒ `open_items != []`，但当前散文 ⇒ 需结构化台账）、JC Stage 2（`实机段未做` ⇒ `open_items` 缺数据源）、FM `gui-contract-mock-tests`（文件 `meets`/复算 `below` ⇒ 必须用冻结优先级，否则命题正反两向都可错）。
5. **三分映射结论**（事实面）：`budget-exhausted` = case 1（效果有界：+1 轮后必 stall，`conductor.py:989-994`）；`stalled` 的 `proven-false-negative` 窄子类 = case 1，其余事实面 = case 2（延后，需补偿，对齐 RQ-13）；`stage-close`/`stage-confirm` 的事实面当前只够当**守卫**（case 3 前置），因为取证源优先级未冻结、provenance 覆盖 <5/22；`goal-change` 的"仅规范面变更才起门"= case 1（且这不是"回答门"，不撞黑名单）；`xkey-authorize` 的 S4 校验 = case 1（已实现），blast radius = case 3（`write_scope` 生产零命中）。**政策面全部 case 3**（含 U-8 黑名单）。
6. **落地成本骨架**：新增字段只落在 `gates.py:68` `FRONTMATTER_FIELDS` 与 `status-model.ts:572` `GATE_FRONTMATTER_FIELDS` 的同一波；**不加进 `gates.py:86` `_REQUIRED_FIELDS`**，故既有 34 个 gate 文件**逐字不变地照旧解析**（新字段默认 `None` ⇒ 自动判定资格缺失 ⇒ case 3）；两侧解析器都 fail-closed（`gates.py:347` / `status-model.ts:660`），所以**任何写者先于两侧注册发新字段都会让门被跳过**（P-021 硬耦合，AC-010）。
7. **前置顺序（硬）**：AC-022 的 D1（`gate-\d{4}` 静默失效，`conductor.py:310`，FM 已 `gate-6687`）→ AC-029/AC-030 的取证快照与防伪字段 → 才谈 case 1。否则新命题会在 `gate-10000+` 上重演"重复消费"（RQ-12 F-5 / RQ-14 新事实：JC `gate-0008` 重放）。

## 决策问题

RQ-12 已判定"根因是命题选层，不是字段缺失"，并给出三分初判。本卡回答**设计侧**的 6 个问题（每门一套）：

1. **现状命题原文**是什么、从哪读出来的（代码模板 `file:line` + 实例 gate 文件）？
2. **真命题**（该门真正要判定的事）能不能写成**可以为假**的陈述句？逐条给**构造性反例**（什么情况下为假 + 如何只读磁盘判出）。
3. 判该命题需要哪些**字段/事实**、每项落点 `file:line`+字段名、**谁在什么时候写**？
4. **自举判定**：可自举 / 部分可自举（指明不可判的部分）/ 不可自举；对后两类给出**为什么机器拿不到**——是**数据不存在**，还是需要**因果/意图判断**？
5. **三分映射**：重写后该门落 case (1) 可自举自动 / (2) 非阻塞延后 / (3) 必须人审 的哪一类？**事实面与政策面分别标注**。
6. **落地成本**：新增哪些字段、改哪些写入点（`file:line`）、Python `gates.py` 与 TS `status-model.ts` 两侧镜像同步什么、既有 gate 文件如何向后兼容解析。

**硬要求**：命题可证伪（附反例构造）；证据字段真实锚点（未确认的写"未确认 + 如何确认"）；每门一条可机判 VC 候选（格式 `当 <触发条件> 时，<字段> 必须等于 <精确值>`）。

## 调研方法与出处

- **代码（只读）**：`packages/multi-workers/autopilot/{gates,conductor,roadmap,state,config,audit_evidence}.py`、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/{status-model,gate-writer,monitor,console}.ts`。本卡对所有引用的 `file:line` 做了一次 `Select-String` 定位复核（结果见正文）；未逐字重读全部函数体，**未复核**的锚点一律标注。
- **数据（只读，引用不重算）**：RQ-12 的 34 门字段/reason 串/22 key verdict/4 correction sidecar/4 provenance；RQ-14 的 14 项信息集/31-34 回放/24-34 漂移；RQ-8 的门清单/等待分布/阻塞面。本卡的"反例"全部复用这三份笔记的实测样本（C1–C5 编号沿用 RQ-12）。
- **设计判据**：`spec-gate-proposition-kinds-20260926.md` 的 F2（命题两分）与 F4（fail-closed 术语基线 `cannot prove green` / `never close on doubt`），以及 spec §3 AC-025 的"命题两分 + 恒真自检"要求。
- **本卡自定**（用于消歧，不引入新事实）：
  - **`trigger(kind)`** = conductor 建该门时执行的判定条件（源码原文）。命题 **P 有信息量** ⟺ `trigger ⊬ P`，即存在盘上状态使 `trigger ∧ ¬P`。
  - **恒真自检**：对每个事实面命题给出一个 **witness**（`trigger ∧ ¬P` 的真实样本或可构造样本），并标注是 `[实测]` 还是 `[构造]`。
  - **取证源优先级**（采用 RQ-12 I2，作为 D-002 提案）：`l3-verdict-provenance.json` > correction sidecar > 末轮 `output.md`/`report.md` 复算 > `l3-verdict.txt` > gate 散文；不一致时 fail-closed 取 `below`（沿用 `conductor.py:1415` 的 `suspect ∧ raw=meets → verdict=below`）。

---

## 发现

### 0. 现状 schema 与写入点（所有门的共同底座）

| 面 | 锚点（实测） | 说明 |
|---|---|---|
| 门品类闭集 | `gates.py:54-61` `GATE_KINDS`；TS `status-model.ts:561` `GATE_KINDS` | 6 类 |
| 门状态闭集 | `gates.py:63` `GATE_STATUSES`；TS `:565` | `pending/approved/rejected` |
| frontmatter 12 字段 | `gates.py:68-81` `FRONTMATTER_FIELDS`；TS `status-model.ts:572-585` `GATE_FRONTMATTER_FIELDS` | **无任何时间上界、无默认动作、无证据哈希字段**（RQ-14 F13） |
| 必填集 | `gates.py:86-88` `_REQUIRED_FIELDS` | 6 个，**新增字段不得进这个集**（否则旧文件解析失败） |
| 未知字段 fail-closed | `gates.py:347`；TS `status-model.ts:660-661` | 两侧都拒绝未注册字段 |
| 建门唯一入口 | `conductor.py:2159-2184` `_create_gate`（锁内 `gates.create` + `gate-created` 事件 `:2183`） | 写者=conductor |
| 建门 API | `gates.py:262` `create` → `_gate_file_content:159` | 渲染顺序即契约 |
| 应答写入 | `gate-writer.ts:139` `answerGate`，只重写 `ANSWER_FIELDS`（`:50` = status/answered_at/answered_by/note）；`answeredAt?` override `:38` | **应答者可写**，不可作防伪来源（AC-030） |
| 消费 | `conductor.py:297` `_consumed_gate_ids`（正则 `gate-\d{4}` 在 `:310`）；`:316` `_consume_answered_gates` | D1 缺陷所在 |
| 展示面 | `monitor.ts:89` `MonitorGate`（只有 id/kind/stage/key）、`:150` `scanPendingGate`（5 字段）、`:645-653` gate 行；`console.ts:180-198` `/autopilot gates` | **物理上看不到 `created_at`**（RQ-14 F4.1） |

**结论**：重写后的每个命题都必须回答"它的**证据字段**从哪来"；12 字段里现成可用的只有 `id/kind/stage/key/created_at/context_refs/status`，其余全靠落盘产物。

---

### 1. `stage-confirm`

#### 1.1 现状命题（原文）

- 模板（代码）：`Stage {N}（{K} 个 key，目标：{goal}）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案`，建门点 `conductor.py:489-497` `_create_stage_confirm_gate`；变体（stage 关闭后自动开下一阶段）`:427-429`（`_ensure_next_stage_gate:409`）。
- 实例：`E2/gates/gate-0001.md:8`、`FM/gates/gate-0009.md:8`、`JC/gates/gate-0001.md:8`（RQ-12 F-1）。
- 建门 `trigger`：下一 stage `> status: pending` 且本 tick 允许激活（`_stage_activation:434` / `_activate_pending_stage`）。命题"提案已写入" **被 trigger 蕴含**（`trigger ⊬ P` 不成立）。

#### 1.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（结构）** | `structural_validation == []`：`_roadmap.md` 可解析、每 stage ≥1 key、`goal` 非空、Keys 表 `depends_on` 指向存在且不在本 stage 之后的 key。 | 提案含指向不存在 key 的依赖、或空 key 集、或不可解析 ⇒ 命题假。判据：`roadmap.validate_roadmap`（`roadmap.py:367-425`）过滤掉**运行期**规则后的 `list[str] != []`。 | `[构造]` 未实测；当前 FM/E2 的 validator 输出只有"缺 key-status"这类**运行期**问题（RQ-12 I3），故 P1 必须**先**把结构性规则与运行期规则分开，否则 witness 会落错层。 |
| **事实 P2（goal 绑定）** | `goal_sha256 == sha256(当前 goal.md)`：`stage-confirm` 被应答时，提案所绑定的 goal 版本＝当前 goal 版本。 | `[实测]` **JC**：`gate-0001`（stage 1 confirm，`created_at 2026-09-11T03:33:17Z`）在 `goal.md` 改动（`gate-0002` goal-change `created_at 06:17:06Z`）**之后**被应答（`answered_at 06:20:38Z`），且 `goal-change` 门当时仍 pending ⇒ 该 stage 提案**未经新 goal 重新校准**。判据：`gate.created_at < goal 变更时刻 < gate.answered_at`，或同 scope 存在 pending `goal-change` 门（RQ-14 表 F1-a 第 1/2 行）。 | `[实测]` JC gate-0001/0002 时序 |
| **政策 P3** | "该现在开这个 stage / 这个 key 集与范围是可接受的" | 不可机器判：这是规划取舍（`FM gate-0009` 的 7 条约束、`E2 gate-0008` 的 2 条拒绝都加在这一层，RQ-14 F4）。 | —（政策题，不适用） |

**设计要点**：把"approve 启动 stage"从命题中**拿掉**——启动是政策动作；机器只判 P1/P2，且**只作为守卫**（P1∧P2 假 ⇒ 不允许任何自动放行，必须人审）。

#### 1.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者（何时） | 现状 |
|---|---|---|---|
| stage goal / Keys 表 / depends_on | `_roadmap.md` `## Stage N:` `> goal:`、`### Keys`；解析 `roadmap.py:229` `load_roadmap`、依赖图 `roadmap.py:479` `dependency_graph` | roadmap-writer（LLM，`conductor.py:520-560` 派发） | 有 |
| 结构校验结果 | **无字段**；函数 `roadmap.py:367` `validate_roadmap`，调用点仅 `roadmap_check.py:50`（conductor 不调用） | 无 | 缺 |
| goal 版本 | 提案侧：`_roadmap.md` 头 `> goal_mtime:`（**LLM 填的 ms 整数**，模板 `conductor.py:597`，解析 `roadmap.py:73`）；实际侧：`goal.md` mtime | roadmap-writer（LLM） | 不可信（且 `> goal_mtime` 与真实 mtime_ns 有 1ms 级差，RQ-12 F-2c） |
| goal 路径 | `conductor.py:76-83` `goal_mtime_ns`；`goal_path`（`conductor.py:2085` refs 用） | conductor | 有 |
| `stage-confirm` 门实例 | `E2/gates/gate-0001.md:8`；`FM/gates/gate-0009.md:8` | conductor `_create_gate` | 有 |

#### 1.4 自举判定

- P1、P2 **部分可自举**：数据在盘上，但 P1 需先把 `validate_roadmap` 的**结构性**规则与**运行期**规则（"stage 起跑时初始化所有 key-status"，docstring `roadmap.py:509-512`）分开——现状 FM Stage 2 / E2 Stage 3 实测不合法（RQ-12 I3），直接搬会得到大量假阳。P2 可自举（hash 比对）。
- P3 **不可自举**：需要因果/意图判断（规划取舍），且人加的约束只存在于 `gate.note` 散文（RQ-14 F11，33 个原子/22 门）。

#### 1.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（结构性校验） | **(1) 可自举自动**（仅作守卫，不产生"放行"） | 机器可复算；但**不得**用 P1 真来推出"可以开 stage" |
| 事实 P2（goal 绑定） | **(1) 可自举自动**（作守卫 + 发现 stale 提案时**阻塞并提示**） | hash 可复算 |
| 政策 P3（该不该开/范围） | **(3) 必须人审** | RQ-10 风险 18：`stage-confirm` 若自动化，会与 `stage-close` 串成 `auto-close → auto-confirm → auto-dispatch` |

#### 1.6 落地成本

- 新增字段：`structural_validation: list[str]`（只放结构性规则）、`proposal_sha256: str`、`goal_sha256: str`。
- 写入点：`conductor.py:489-497` `_create_stage_confirm_gate`（conductor 算 sha / 跑结构校验），`:650`（非本门）。`_roadmap.md` 头的 `goal_mtime` 由 LLM 填 → 不改它，改由门自己绑 `goal_sha256`（不去信任 LLM 写的 roadmap 头）。
- 两侧镜像：`gates.py:68` `FRONTMATTER_FIELDS` + `status-model.ts:572` `GATE_FRONTMATTER_FIELDS` + `GateRecord`（`status-model.ts:587`）同波；解析默认值在 `gates.py:381` `_to_gate` / TS `parseGateFile`。写入器无需改（`gate-writer.ts:50` 仍只写 4 个应答字段）。
- 向后兼容：旧 gate 文件缺新字段 ⇒ 解析为 `None` ⇒ **自动资格缺失** ⇒ case 3，不报错（新字段不进 `gates.py:86`）。**风险**：新字段必须先注册进两侧 `FRONTMATTER_FIELDS` 再允许任何写者发出，否则解释性读取会 fail-closed 并让门被整 tick 跳过（`gates.py:347` / TS `:660`）。

#### 1.7 VC 候选

> **当 `gate.kind == "stage-confirm"` 时，`gate.structural_validation` 必须等于 `[]` 且 `gate.goal_sha256` 必须等于 `sha256(<project>/.agenticdoc/goal.md)`。**

---

### 2. `stage-close`

#### 2.1 现状命题（原文）

- 模板（代码）：`Stage {N} 全部 key 已终态，闭环 dossier 已写入 .agenticdoc/_autopilot/stages/stage-{N}-close.md——确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理`，建门点 `conductor.py:650-654`。
- 实例：`FM/gates/gate-0008.md:8`、`E2/gates/gate-0003.md:8`、`JC/gates/gate-0007.md:8`、`JC/gates/gate-0008.md:8`。
- 建门 `trigger`（`conductor.py:616-656` `_stage_closure`）：`terminal = ("done","closed-legacy")`（`:629-630`）；`any(status_of.get(e.key) not in terminal ...) → return`（`:631`）；`_gate_open` 去重（`:632-633`）；写 dossier（`:640-646`）后 `_create_gate`（`:650-654`）。**命题主语"全部 key 已终态"＝ `:631` 的判定条件本身，且 dossier 刚在本函数内写好** ⇒ 机器复算恒真、零信息量（RQ-12 风险 26）。

#### 2.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（最终裁决）** | 对 stage 内**每个** key：`final_verdict(key) == "meets"` 或 `key_status(key) == "closed-legacy"`；`final_verdict` 按**冻结取证源优先级**（D-002）计算，而非直读 `l3-verdict.txt`。 | `[实测]` **C1 E2 Stage 2**：`feature-l3-readcap-injection` 的 `l3-verdict-correction-fm-136c65a70b2b.json` 写 `"corrected_value":"below"`、`"counted_as_done": false`，而 `l3-verdict.txt=meets`、roadmap `key-status=done`、stage 已 `closed` ⇒ 按优先级算 `final_verdict=below` 且非 closed-legacy ⇒ **P1 假**。判据：correction sidecar 存在且 `counted_as_done == false`，或 correction `corrected_value != l3-verdict.txt`。`[实测]` **C4 FM `gui-contract-mock-tests`**：文件 `meets` / 复算 `below`（失败行 `PASS ... 0 FAIL —` 被 `_L3_FAIL_PROSE_RE` 误命中，`conductor.py:1218`）⇒ 若按文件判 P1 真、按复算判 P1 假 —— **同一前置正反两向都能错**，故必须冻结优先级。 | `[实测]` C1 / C4 |
| **事实 P2（未达成台账）** | `open_items == []`，其中 `open_items` 覆盖：`closed-legacy` 的 key、`final_verdict == below` 的 key、`counted_as_done == false` 的项、`pending-authorization` 项、带 `needs-rerun` 的项。 | `[实测]` **C2 FM Stage 1**：stage 已 `closed`，而人工 note 登记 `C-09`（stage goal 里"可发布桌面壳/打包分发"元素未闭）与 `NRR-1/NRR-2` 两条条件性 needs-rerun（RQ-12 C2）⇒ 若台账结构化则 `open_items != []` ⇒ **P2 假**；**但当前这些只在 `gate.note` 散文，机器读不到** ⇒ 现状下 P2 **恒真（空洞）**。`[实测]` E2 `gate-0003.md:14` note 明写"approve 不表示其完成"（RQ-14 F12）。 | `[实测]` C2（假，但需先结构化才可机判） |
| **事实 P3（goal 达成）** | "stage goal 的每条验收项都已由机器可读证据背书" | `[实测]` **C3 JC Stage 2**：唯一 key `done`/`meets`/无 closed-legacy，但 stage goal 要求 Rider **实机人工验收**（`JC/gates/gate-0006.md:14`），`gate-0007` pending 9.5 天 ⇒ "目标达成"为假/不可判。判据：stage goal 文本含"人工/实机/验收"类词且无对应结构化证据 —— **语义判断 + 无数据源（验收台账不存在）**。 | `[实测]` C3 |
| **政策 P4** | "approve 后开放的下一 stage 是应该开的" | 取舍；且 reject 会把 stage 置 `halted`（`conductor.py:359-378` 的 rejected 分支，`_stage_activation:443-444` 之后永不再开工）。 | — |

**设计要点**：P1/P2 **不是触发条件的同义反复**——`trigger` 只要求 `key-status ∈ {done, closed-legacy}`，而 P1 额外要求**最终裁决**达标（一个 key 可以 `done` 而 `final_verdict=below`，C1 就是实例），P2 额外要求**台账为空**（C2）。这两条都可以为假。

#### 2.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者（何时） | 现状 |
|---|---|---|---|
| key-status 终态 | `_roadmap.md` `> key-status:`；写 `roadmap.py:505` `update_key_status`；读 `roadmap.py:229` | `_mark_key_done`（`conductor.py:2242-2272`，done 交易）、`_apply_stalled_rejections`（`:2363-2420`，closed-legacy） | 有；`closed-legacy` 生产 0 实例（RQ-12 数据缺口 5） |
| 最终裁决 | `{key}/l3-verdict.txt`（读 `conductor.py:659-671` `_l3_verdict`，写 `:675-717` `_persist_l3_verdict`） | conductor（done/stall 交易） | 有；6/22 与复算不一致 |
| 带锚溯源 | `{key}/l3-verdict-provenance.json`（`_persist_l3_provenance:1451`；字段 `source_mtime_ns/anchor_path/anchor_mtime_ns/suspect/raw_verdict/verdict`，构造 `_l3_provenance_record:1356-1449`；`_L3_TRACE_NAME:1247`、slack `_PROVENANCE_SLACK_SEC:1248`） | conductor（`_l3_provenance_record`） | 覆盖 <5/22（RQ-12 数据缺口 2） |
| 项目侧纠正账本 | `{key}/*-correction-*.json`（`original_value/original_sha256/corrected_value/counted_as_done`） | 项目 key 工具链（**非框架**，E2 3 个） | 有 3 个；非框架契约 |
| 末轮判定源 | `{key}/workers/ap-{key}-l3-a{N}/{output.md,report.md}`；解析规则 `_L3_FAIL_RE:1214`、`_L3_FAIL_ZERO_RE:1220`、`_L3_FAIL_PROSE_RE:1218`（**版本敏感**） | L3 reviewer worker | 有 |
| dossier | `_autopilot/stages/stage-{N}-close.md`（5 列 `key/final phase/l3 verdict/l3 report/evidence`，`_closure_dossier_md:722-750`） | conductor `_stage_closure:640-646` | 有；`l3 verdict` 列直读 `l3-verdict.txt` ⇒ 陈旧 |
| 未达成台账 | `{key}/achieved.md` `## 遗留问题` 段（`mark_stalled:3996-4011` 写草稿）；门 `note` 散文 | conductor（草稿）/人（note） | 无结构化字段 |

#### 2.4 自举判定

- P1 **部分可自举**：需要**冻结取证源优先级 + 把 provenance 覆盖扩到全量**（数据存在但不全，<5/22 不可回填）；不冻结则同一命题正反两向都错（C4）。
- P2 **部分可自举**：台账数据**大部分不存在**（只在 note 散文 / `achieved.md` 遗留节），必须先结构化；结构化后可自举。
- P3 **不可自举**：需要**语义/意图判断**（"实机段算不算没做"），且验收台账不存在（双重原因）。
- P4 **不可自举**：政策。

#### 2.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（最终裁决） | **(1) 可自举自动**——**仅当** D-002 优先级冻结 + 该 stage 所有 key 有 provenance/correction 覆盖；否则 **(3) 必须人审** | 当前覆盖 <5/22，故历史 stage 一律 case 3；冻结后新 stage 可 case 1 |
| 事实 P2（open_items 空） | **(1)** 台账结构化后；否则 **(3)** | 现在台账不存在 ⇒ 空洞真 ⇒ 不能放行 |
| 事实 P3（goal 达成） | **(3)** | 语义 + 无数据源 |
| 政策 P4 | **(3)** | 且受 RQ-10 风险 18 组合约束（`stage-confirm` 不自动时才安全） |

#### 2.6 落地成本

- 新增字段：`verdicts_final: list[{key, verdict, source, source_sha256, anchor_mtime_ns, suspect}]`、`open_items: list[{kind, key, item, disposition}]`、`subject_sha256: str`（被引 dossier 的 sha256）。
- 写入点：`conductor.py:650-654` `_stage_closure`（conductor 从冻结优先级 + correction/provenance + `achieved.md` 结构节汇总）；扩展 `_l3_provenance_record:1356` 的覆盖面（全轮次）；`_closure_dossier_md:722` 增"未达成"列或独立台账。
- 两侧镜像：同 §1.6 的 `FRONTMATTER_FIELDS` + `GateRecord` 同步；**注意 `context_refs` 之外还要读新字段的只有 gate 卡渲染（RQ-14 层 2 L12）**，`monitor.ts:150` `scanPendingGate` 不需要新字段（面板不解 auto）。
- 向后兼容：旧门缺字段 ⇒ `None` ⇒ case 3；历史 stage（FM Stage1/2、E2 Stage1/2/3、JC Stage1/2）**不可回填**（provenance 覆盖不足、correction 只有 E2 3 个）⇒ 明确声明"只能对冻结时刻之后的 stage 生效"。

#### 2.7 VC 候选

> **当 `gate.kind == "stage-close"` 时，`gate.open_items` 必须等于 `[]`，且 `gate.verdicts_final` 中每个元素的 `verdict` 必须等于 `"meets"` 或该 `key` 的 key-status 必须等于 `"closed-legacy"`。**
> （若 `open_items` 非空或任一 `verdict == "below"` ⇒ 该门**不得**被自动应答。）

---

### 3. `stalled`

#### 3.1 现状命题（原文）

- 模板（代码）：`key {K} 已 stalled（{reason}）——遗留关闭（closed-legacy），还是人工介入后重试？`，建门点 `conductor.py:3971-3973`；refs `[".agenticdoc/{key}", reason]`（`:3974`）。
- 实例：`FM/gates/gate-0002.md:8`、`E2/gates/gate-0014.md:8`、`JC/gates/gate-0003.md:8`（RQ-12 F-1）。
- 建门 `trigger`：`mark_stalled` 刚把 key-status 写成 `stalled`（`:3955-3962`）并带着 `reason` 建门。命题"K 已 stalled"**被 trigger 蕴含**；`reason` 是**散文**，且随 conductor 版本漂移（RQ-12 C5：JC `gate-0004` 写 `2/2`，按现行为应 `3/3`；3 种格式）。

#### 3.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（原因一致）** | `reason_code == recomputed_cause_class`，`cause_class ∈ {advance-class, l3-below, l3-no-verdict, l3-suspect, exec-exhausted}`（闭集）；且 `cause_counts.used_rounds == state.used_rounds(loop)`、`cause_counts.round_limit == round_budget + credits`、`cause_counts.credits_used == _resume_credits(key)`。 | `[实测]` **C4/C5 同族**：`FM/gui-shell-spike` 的 `l3-verdict.txt=below`（陈旧，mtime 09-23 11:48）而末轮 `l3-a3` 复算 `meets` ⇒ 若门的 `reason_code=l3-below`，按冻结优先级复算 cause=`meets` ⇒ **P1 假**（该 stall 是机械假阴）。判据：`_l3_resolve_source`（`conductor.py:1274`）+ 冻结优先级。`[实测]` **C5 文本漂移**：`JC/gate-0004.md:8` 的 `2/2` 对比 `3/3`（credits=1，`_resume_credits:2273`）。 | `[实测]` FM `gui-shell-spike`（陈旧）+ JC gate-0004（计数漂移） |
| **事实 P2（三类判定）** | `false_negative_class ∈ {proven-false-negative, proven-real-defect, undecidable}`，且 `proven-*` 必须给 `fn_basis{rule, source, source_sha256}`。`proven-false-negative` ⟺ 判定源的 FAIL 计数在**冻结解析器版本**下复算为 0（或失败行命中已知"描述性/散文"模式）。 | `[实测]` **C4 FM `gui-contract-mock-tests`**：失败行 `PASS (re-review attempt 2): 18/18 VC-GCM assertions PASS with 0 FAIL — repair round closed all 4 pr…` 被 `_L3_FAIL_PROSE_RE`（`conductor.py:1218`）误判 ⇒ 可机判为 `proven-false-negative`。`[实测]` **C2 型真缺陷**：`E2 gate-0014` note "37 PASS / 5 FAIL，失败项为真实缺陷"（RQ-14 F5）⇒ `proven-real-defect`。**"真缺陷 vs 假阴"整体不可判**（需读 `l3-report.md` 散文）⇒ `undecidable` 是合法值。 | `[实测]` C4（proven-fn）与 E2 gate-0014（proven-defect） |
| **政策 P3** | "要不要继续给这个 key 投钱 / 那次带外修复是否已到位 / closed-legacy 的弃置代价是否可接受" | `[实测]` **≥16/22** 条 `stalled` approve 的 note 记录了 approve **之前**的带外修复，**0/22 是裸 y/n**（RQ-10 F1f / RQ-14 F10）⇒ 机器无法证明"修复已做"。 | — |
| **政策 P4（边界）** | "再给一轮必须满足的边界（不放宽判据 / 不得记为达成）" | `[实测]` `NEXT/BOUNDARY` 原子覆盖 22/34 门（RQ-14 F11），只在 note 散文。 | — |

#### 3.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者（何时） | 现状 |
|---|---|---|---|
| key-status=stalled | `_roadmap.md` `> key-status:`；写 `roadmap.py:505` | conductor `mark_stalled:3955-3962` | 有 |
| reason 散文 | gate `context_refs[1]`（`mark_stalled:3974`），渲染到 gate 文件 `:10-11`；`_one_line` 截断在 `conductor.py:908-912` 等处 | conductor | 有；3 种格式 |
| 轮次计数 | `{key}/workers/*/task.md` 的 `loop:`/`attempt:`；读 `state.py:224-249` `used_rounds`（`_task_info:191`） | dispatch/launcher 写 task.md | 有 |
| limit / credits | `config.json` `round_budget`（`config.py:53`，默认 2）；`_resume_credits(key)`（`conductor.py:2273-2296`，= approved stalled gate 数） | conductor | 有 |
| advance 连续失败 | `_advance_failure_streak`（`conductor.py:803`）、`_record_advance_result:868`、timeline `advance` detail `class=`、`advance_stall_ticks`（`config.py:57` 默认 5） | conductor | 有 |
| L3 裁决 + 溯源 | 见 §2.3（`l3-verdict.txt` / provenance / correction / 末轮 output.md） | conductor / reviewer | 有 |
| worker 退出形状 | `{key}/workers/*/trace.log` 末行 `[END] … exit=N elapsed=Ns tools=M`；`worker.log` 末行 | launcher/worker | 有（RQ-14 F5） |
| achieved.md 草稿 + pattern | `mark_stalled:3996-4030` | conductor | 有；散文 |

#### 3.4 自举判定

- P1 **可自举**（数据全在盘上；需冻结优先级与解析器版本）。
- P2 **部分可自举**：`proven-false-negative` / `proven-real-defect` 可机判（有实测两类样本）；**语义层面的"真缺陷 vs 假阴"不可判**（需读散文，因果/性质判断）。
- P3 **不可自举**：带外修复记录只存在于 `gate.note`（数据存在但**只在应答者可控的散文里**，且写在应答之后）⇒ 双重不可用。P4 同上。

#### 3.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（原因一致） | **(1) 可自举自动**（作守卫 + 发现不一致时**不得自动**） | 计数可复算 |
| 事实 P2 的 `proven-false-negative` | **(1) 可自举自动**（自动 resume 一轮） | 目标有界（`_resume_credits` 每 loop 只 +1，`conductor.py:2273-2296`），且假阴已证 |
| 事实 P2 的 `proven-real-defect` / `undecidable` | **(2) 非阻塞延后**（RQ-13：stalled 是最干净的延后候选，但需补偿控制）或 **(3)** | 需要带外修复/人工判断 |
| 政策 P3/P4 | **(3) 必须人审** | U-8 黑名单外的取舍题；带外修复不可机证 |

#### 3.6 落地成本

- 新增字段：`reason_code: enum{advance-class,l3-below,l3-no-verdict,l3-suspect,exec-exhausted}`、`cause_counts{loop,used_rounds,round_limit,credits_used}`、`false_negative_class: enum{proven-false-negative,proven-real-defect,undecidable}`、`fn_basis{rule,source,source_sha256}`、`evidence_snapshot`（通用）。
- 写入点：`conductor.py:3971-3974` `mark_stalled`（12 个调用点各自传码，替换散文 `reason`；调用点 RQ-12 列出 `:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941`，**未逐个复核**，见数据缺口 G14）；`fn_basis` 由 `_l3_resolve_source:1274` 派生。
- 两侧镜像：同 §1.6；`reason` 散文**保留**（人读），`reason_code` 是新增的机器键。
- 向后兼容：旧门无 `reason_code` ⇒ 不参与自动（case 3）；旧 `context_refs[1]` 散文不解析（D6：`note`/散文不得作派生输入）。

#### 3.7 VC 候选

> **当 `gate.kind == "stalled"` 时，`gate.reason_code` 必须等于按冻结取证源优先级复算的 `cause_class`（闭集 5 值之一），且 `gate.cause_counts.used_rounds` 必须等于 `state.used_rounds(gate.cause_counts.loop)`。**

---

### 4. `budget-exhausted`

#### 4.1 现状命题（原文）

- 模板（代码）：`L2 回路 {loop} 已达 {limit} 轮上限且仍有缺口——追加一轮修复，还是标记 stalled？`，建门点 `conductor.py:996-999`；refs `[loop]`。
- 实例：**生产 0 实例**（FM/E2/JC 均无；RQ-8 F4 / RQ-12 数据缺口 1）。最近似在盘样本：`E2/feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l2-tasks-to-execute-a1/task.md` 的 `loop: l2:feature-gui-time-mvp-board:tasks-to-execute | attempt: 1`（used=1 < limit=2）。
- 建门 `trigger`（`conductor.py:989-1000`）：`not allowed`（轮次用尽）且未被 reject、未花 bonus、无同 loop pending 门 ⇒ 建门。命题"已达 limit 且仍有缺口"**部分被 trigger 蕴含**（"达 limit"是 trigger；"仍有缺口"是 `blocking` 条件）。

#### 4.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（计数一致）** | `used_rounds(loop) == round_limit + credits_used` 且门文本里的 `{limit}` 与复算相等。 | `[实测同族]` **C5 文本漂移**：`JC/gate-0004.md:8` 写 `2/2`，按现行为（credits=1）应为 `3/3` ⇒ 若该门是 budget-exhausted 而非 stalled，则 P1 假。判据：`state.used_rounds`（`state.py:224`）+ `config.py:53` `round_budget` + `_resume_credits`（`conductor.py:2273`）。 | `[构造]`（0 生产样本；用 JC gate-0004 的同型计数漂移作类比实测） |
| **事实 P2（缺口存在）** | L1 dossier 的 `gaps` 中存在 `severity == "blocking"` 的项。 | 若轮次用尽但 `blocking` gaps 已空（例如上一轮已修复、只剩 `non-blocking`）⇒ P2 假 ⇒ 不该给 bonus 轮，应直接推进。判据：`audit_evidence.build_dossier`（`audit_evidence.py:215`）的 `gaps[{item,rule,severity}]`（schema `:10`，rules `:226-252`）。 | `[构造]`（0 生产样本） |
| **事实 P3（效果有界）** | approve 的效果恰为"该 loop 多一轮，且第二次用尽后直接 stall"。 | `[代码]` `conductor.py:989-994`：`bonus and used >= limit + 1 → mark_stalled`；`_budget_bonus:2216` 只对 approved 同 loop 生效。反例：若同 loop 另有 pending 门或 gate 被重放（D1）⇒ 效果不止一轮 ⇒ P3 假。判据：`_budget_bonus` + `_budget_gate_rejected` + `_consumed_gate_ids`（`:297`）。 | `[构造]` |
| **政策 P4** | "这个 key 还值不值得再投一轮" | 取舍。 | — |

#### 4.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者 | 现状 |
|---|---|---|---|
| loop 标签 | gate `context_refs[0]` = `l2:{key}:{edge}`；task.md `loop:` | conductor `_create_gate`（`:996`） | 有（0 样本） |
| used | `state.py:224-249` `used_rounds` | 派生 | 有 |
| limit / 预算键 | `config.py:53` `round_budget`（默认 2）、`:52` `max_parallel_keys` | 项目/机器层配置 | 有 |
| credits | `conductor.py:2273` `_resume_credits` | 派生 | 有 |
| 缺口 | `audit_evidence.py:215` `build_dossier` → `gaps[{item,rule,severity}]`（`:10`），rules `:226-252` | conductor（L1 audit） | 有；当前未落进门字段 |
| approve/reject 效果 | `conductor.py:2216` `_budget_bonus` / `:2228` `_budget_gate_rejected` / `:989-994` | conductor | 有 |

#### 4.4 自举判定

- P1/P2/P3 **可自举**（命题面完全可复算；这是 RQ-12 判定的唯一"命题面可自举"门）。
- P4 **不可自举**（政策），但**效果有界**（+1 轮后必 stall），所以政策空间很小。
- **保留意见**：0 生产样本 ⇒ 结论是**纯代码推理**（RQ-12 数据缺口 1）；上线前必须有影子模式样本（AC-024）。

#### 4.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（计数一致） | **(1) 可自举自动**（守卫） | 可复算 |
| 事实 P2（blocking gaps 非空） | **(1) 可自举自动** | `audit_evidence` 可复算 |
| 事实 P3（效果有界） | **(1) 可自举自动** | 代码常量 + 计数 |
| 政策 P4 | **(3)-lite 必须人审（可配置上限）** | 但选择的效果有界（+1 轮）⇒ 是最适合先上 case 1 的门；仍需影子模式（AC-024） |

#### 4.6 落地成本

- 新增字段：`cause_counts{loop,used_rounds,round_limit,credits_used}`、`gap_items: list[{item,rule,severity}]`（或只存 `blocking_gap_count: int` + 指针）、`reason_code="budget-exhausted"`。
- 写入点：`conductor.py:996-1000`（`_advance_key` 的 exhausted 分支）——把 `audit_evidence.build_dossier` 的 `gaps` 直接落进门。
- 两侧镜像：同 §1.6。
- 向后兼容：0 生产样本 ⇒ 无历史文件要兼容；但**未来**旧版本 conductor 读到含新字段的门会 fail-closed（P-021 两侧同波）。

#### 4.7 VC 候选

> **当 `gate.kind == "budget-exhausted"` 时，`gate.cause_counts.used_rounds` 必须等于 `gate.cause_counts.round_limit + gate.cause_counts.credits_used`，且 `gate.blocking_gap_count` 必须 `> 0`。**

---

### 5. `goal-change`

#### 5.1 现状命题（原文）

- 模板（代码）：`goal.md changed while autopilot is active — review the new goal and approve resuming, or reject to stay halted.`，建门点 `conductor.py:2085-2090`（`tick`，create-once）；refs `[str(goal_path)]`。
- 实例：`JC/gates/gate-0002.md:8`（`context_refs[0]` = `H:\git\JCodingAss\.agenticdoc\goal.md`）。
- 建门 `trigger`（`conductor.py:2062-2097`）：`goal_mtime_ns != st.goal_baseline`（`goal_mtime_ns:76`）+ `not open_goal_change_gate` + `not st.goal_halted`。恢复（`:2100-2111`）：`gate_open or st.goal_halted` ⇒ pending 则 `return "halted-goal-change"`；否则刷新 baseline。**reject 与 approve 走同一分支 ⇒ reject 是 no-op**（RQ-12 I4）。命题"goal.md 变了"= mtime 不等，**被 trigger 蕴含**；"变成什么"**磁盘上不存在**。

#### 5.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（内容变更）** | `sha256(goal.md@before) != sha256(goal.md@after)`（**不是 mtime 不等**）。 | `[构造]` mtime 因 `touch`/checkout/编辑器保存而变、内容不变 ⇒ mtime 触发而 sha 相等 ⇒ **P1 假**：现状会 halt 整个 roadmap（`tick:2101-2103`）而实际无事。判据：`goal_sha256_before == goal_sha256_after`。 | `[构造]`（无实测样本：三项目均无 mtime-only 变更） |
| **事实 P2（规范面变更）** | `goal_diff.normative_changed == true`，`normative` = `Goal` / `Context` / `Key Constraints` 三节的 sha 变化。 | `[实测]` **JC gate-0002**：人工 note 逐字"the user removing the stale 2026-09-10 Roadmap snapshot section … **core Goal/Context/Key Constraints verified intact**" ⇒ 只有非规范面变更 ⇒ **P2 假**，本不该起门（或起门时应给"无需重规划"的机器结论）。判据：分段 sha（3 节 + 其余）。 | `[实测]` JC gate-0002 |
| **事实 P3（计划一致性）** | "roadmap 的 stage goal / key 集合是否引用了被删除或改写的规范面内容" —— 段落级可判的部分 | 语义部分不可判；段落引用可判。 | `[构造]` |
| **政策 P4** | "新 goal 是否推翻现有计划 / 是否 resume" | **不可自举**：before-image 磁盘上不存在（FM `goal.md` untracked、JC 无 `.git`、无框架快照；RQ-12 F-2e），且需要意图判断。 | — |

**设计要点（重要）**：`goal-change` 的**事实面**改进不是"让机器答这个门"，而是**决定"要不要起门"**：只有 `P1 ∧ P2` 才起门；否则记 `goal-refresh`（刷新 baseline）不打扰人。这**不是"回答门"**，所以不撞 U-8 的 `goal-change` 黑名单。

#### 5.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者（何时） | 现状 |
|---|---|---|---|
| baseline | 内存 `st.goal_baseline` + timeline `goal-snapshot` detail（`conductor.py:4138-4139` 启动、`:2109-2110` 刷新） | conductor | **只在内存/detail，可被 timeline 轮转剪掉**（JC goal 类事件 0 条） |
| 变更事件 | timeline `goal-halt` detail `goal.md mtime_ns {before} -> {after}`（`conductor.py:2093-2094`） | conductor | 有；**不含 diff** |
| roadmap 头 goal 版本 | `_roadmap.md` `> goal_mtime:`（LLM 填） | roadmap-writer | 不可信 |
| **变更前内容** | —— | —— | **不存在**（无 before-image 快照） |
| goal 路径 | `conductor.py:76-83` `goal_mtime_ns` / `goal_path` | conductor | 有 |

#### 5.4 自举判定

- P1 **可自举**——**前提是落 before-image**（现在没有 ⇒ 结构性缺口）。
- P2 **可自举**（段落 sha 可分），同样依赖 before-image。
- P3 **部分可自举**（段落引用可判，语义对齐不可判）。
- P4 **不可自举**：**数据不存在（before-image）＋ 意图判断**，双重原因；且现状 reject 是 no-op，两个答案等价。

#### 5.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（内容是否真变） | **(1) 可自举自动**（用于**抑制误起的门**） | 防 mtime-only 假 halt |
| 事实 P2（是否规范面变更） | **(1) 可自举自动**（用于**决定是否起门**） | 段落 sha 可判 |
| 事实 P3（计划一致性） | **(3)** 或部分 **(2)** | 语义对齐需人 |
| 政策 P4（resume / 改计划） | **(3) 必须人审**（U-8 黑名单） | 授权/取舍；且需先修 reject 语义（否则"等于没答"） |

#### 5.6 落地成本

- 新增字段：`goal_sha256_before: str`、`goal_sha256_after: str`、`goal_diff{sections_added,sections_removed,sections_changed,normative_changed: bool}`；
- **非字段改动**：conductor 在检测到变更时把变更前 `goal.md` 落一份**不可变镜像**（新目录，如 `_autopilot/goal-history/goal-<mtime_ns>.md`，只增不改）。
- 写入点：`conductor.py:2085-2090`（起门时带 sha/diff）、`:4138-4139`（启动 baseline 应存 **sha** 而非只存 mtime）、`:2100-2111`（**修 reject 语义**：approve → 刷新 baseline 继续；reject → 保持 halted，与门文本一致）。
- 两侧镜像：新字段同波；`goal_diff` 可只给 conductor 消费（TS 仅展示）。
- 向后兼容：旧门缺字段 ⇒ case 3；历史 `goal-change` 无法回填（before-image 全项目不可得）。

#### 5.7 VC 候选

> **当 `gate.kind == "goal-change"` 时，`gate.goal_sha256_before` 必须不等于 `gate.goal_sha256_after`，且 `gate.goal_diff.normative_changed` 必须等于 `true`（否则该门不应存在）。**

---

### 6. `xkey-authorize`

#### 6.1 现状命题（原文）

- 模板（代码）：`跨 key 红 {file}::{test_id}（owner {owner_key}）请求解冻授权：追认后由框架执行受限修复，拒绝则留账本。`，建门点 `conductor.py:2739-2744` `_xkey_ensure_gate`；refs `[request_id, ticket_rel]`。
- 实例：**生产 0 实例**（`xkey_repair` 三项目均未开；RQ-8 F1 / RQ-12 F-2f）。生产上唯一真实发生过的跨 key 授权**没有走这个门**，而是散文 `_autopilot/evidence/cross-key-repair-request-*.md` + 手写 `decision:` 行（RQ-12 I5）。

#### 6.2 真命题（重写后）

| 层 | 命题（可证伪陈述句） | 构造性反例（何时为假 + 盘上判据） | 恒真自检 witness |
|---|---|---|---|
| **事实 P1（修复是否真绿）** | `red_after == 0 ∧ returncode == 0 ∧ ¬timed_out`（**已实现**，`conductor.py:3647`）。 | `[代码]` fail-closed 路径：cwd 不可用（`:3617-3625` "must never fall back to a guessed root"）、`xkey_verify_cmd` 空（`:3626-3631` "cannot prove green"）、异常（`:3637-3642` "never close on doubt"）、非 green（`:3647-3657`）⇒ 全部不放行。反例（构造）：`red_after==0` 但验证命令其实**没跑那条红**（`test_id` 不在 stdout）⇒ 假绿。 | `[代码]` 已实现 |
| **事实 P2（验证确实针对该红）** | `verify.test_id == gate.test_id` 且 `red_before >= 1` 且 stdout 含该 `test_id`。 | `[构造]` ticket 的 `verification.argv` 展开后跑的是另一条测试 ⇒ 假绿。判据：`ticket.verification`（`conductor.py:2696-2706`）+ 验证产物 `stdout_path`/`stdout_sha256`（`_xkey_run_verify` 落 ticket.verify，`:3658-3672`）。 | `[构造]`（0 票据） |
| **事实 P3（写面越界）** | `blast_radius.files ⊆ write_scope`。 | `[构造]` 应用补丁触到 owner key 写面之外的文件 ⇒ 越界。判据：`blast_radius{files, sha_before}` vs `write_scope`。 | `[构造]`；**`write_scope` 生产代码零命中**（RQ-10 AC-014 / RQ-12 F-2f）⇒ 数据不存在 |
| **事实 P4（无绕门）** | "该 request 没有走门外的散文授权路径"。 | `[实测]` `FM/.agenticdoc/_autopilot/evidence/cross-key-repair-request-20260925-n1.md:57` 手写 `**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**`；另一份 `cross-key-repair-request-20260926-h1.md:6` = `status : pending-user-decision` ⇒ 存在**未经 schema 的授权**。判据：扫描 `_autopilot/evidence/cross-key-repair-request-*.md` 的 `decision:` 行。 | `[实测]` FM 20260925-n1 |
| **政策 P5** | "允许不允许对这个 owner key 的写面动手（blast radius 可否接受）" | `[实测]` 不可自举：政策授权（PM 自采 F2；U-8 黑名单）。 | — |

#### 6.3 证据与写入点

| 事实 | 落点（`file:line` + 字段） | 写者 | 现状 |
|---|---|---|---|
| request 身份 | `context_refs[0]=request_id`（`"XKEY-"+sha1(dedup_key)[:12]`，`conductor.py:2656-2658`）；ticket `{file,test_id,owner_key,source_key,dedup_key,request_id}`（`:2663-2700`） | conductor | 有（0 票据） |
| 冻结块 / 授权快照 | ticket `frozen_block` / `authorization_snapshot`（整文件 sha256）/ `target_file_sha256`（`:2652-2653`、`:2691-2698`） | conductor | 有 |
| 验证 | ticket.verify `{red_before,red_after,returncode,timed_out,stdout_path,stdout_sha256,verify_cmd,verified_at}`（`_xkey_run_verify:3595-3672`） | conductor | 有 |
| 放行闭合 | `_xkey_write_evidence:3684` → `_xkey_close:3730`（green 后才闭合） | conductor | 有 |
| 写面声明 | —— | —— | **不存在**（`write_scope` 零命中） |
| 绕门散文 | `_autopilot/evidence/cross-key-repair-request-*.md` 的 `decision:` 行 | 人 | 有（无 schema） |

#### 6.4 自举判定

- P1/P2 **可自举**（已实现；P2 需补 `test_id` 绑定）。
- P3 **不可自举**：**数据不存在**（`write_scope` 零命中），非语义问题；前置是 AC-014 的机器可读写面声明（本 key 范围外）。
- P4 **部分可自举**：散文路径可被扫描检测（存在性可判），但"那次授权是否等价于门"不可判。
- P5 **不可自举**：政策。

#### 6.5 三分映射

| 面 | 类别 | 理由 |
|---|---|---|
| 事实 P1（是否真绿） | **(1) 可自举自动** | 已是 xkey S4 原型：`_xkey_run_verify` → `_xkey_close`（PM 自采 F1） |
| 事实 P2（验证针对该红） | **(1) 可自举自动**（守卫） | 可复算 |
| 事实 P3（写面越界） | **(3) 必须人审**（**缺数据源**，非"不想自动"） | `write_scope` 不存在 |
| 事实 P4（绕门检测） | **(2)/(3)**：检测到即告警 / 视为未授权（fail-closed） | 散文路径无 schema |
| 政策 P5（授权） | **(3) 必须人审**（U-8 黑名单） | 授权题 |

#### 6.6 落地成本

- 新增字段：`write_scope: list[str]`（或引用 owner key 的声明文件路径）、`blast_radius{files: list[str], sha_before: list[str]}`、`authorization_snapshot: str`（提升 ticket 字段为门字段）、`verify{test_id,red_before,red_after,returncode,timed_out,stdout_sha256}`。
- 写入点：`conductor.py:2739-2744` `_xkey_ensure_gate`（带 ticket 的 sha/写面）；数据源同 ticket（`:2663-2706`）。
- 两侧镜像：同 §1.6；TS 侧无需新逻辑（展示层可选）。
- 向后兼容：旧门（0 个）缺字段 ⇒ case 3；绕门散文路径**无 schema**，只能存在性检测（需新增只读扫描，不改散文文件）。

#### 6.7 VC 候选

> **当 `gate.kind == "xkey-authorize"` 时，`gate.authorization_snapshot` 必须等于 `sha256(<owner key 的冻结块文件>)`（即 ticket 的 `authorization_snapshot`），且 `gate.verify.red_after` 必须等于 `0`、`gate.verify.returncode` 必须等于 `0`。**

---

### 7. 汇总

#### 7.1 命题重写前后对照（信息量）

| 门 | 现状命题是否可假 | 现状"恒真"程度 | 重写后的事实面命题 | 反例性质 |
|---|---|---|---|---|
| `stage-confirm` | 否（"提案已写入"被 trigger 蕴含） | 恒真 | `structural_validation==[]` ∧ `goal_sha256` 匹配 | 1 实测（JC 时序）+ 2 构造 |
| `stage-close` | 否（"全部 key 已终态"＝ `:631`） | **恒真（零信息量）** | `verdicts_final` 达标 ∧ `open_items==[]` | **4 实测（C1–C4）** |
| `stalled` | 否（"K 已 stalled"＝ `mark_stalled` 刚写） | 恒真 | `reason_code` 一致 ∧ 计数一致 ∧ `false_negative_class` | 3 实测（陈旧/漂移/假阴）+ 真缺陷 |
| `budget-exhausted` | 部分（"达 limit"是 trigger） | 半恒真 | `used==limit+credits` ∧ `blocking gaps` 非空 | 0 实测（构造 + JC 类比） |
| `goal-change` | 否（"mtime 变了"＝ trigger） | 恒真 | `sha` 不等 ∧ `normative_changed` | 1 实测（JC）+ 1 构造 |
| `xkey-authorize` | 否（"请求授权"＝ trigger） | 恒真 | `red_after==0` ∧ `test_id` 绑定 ∧ `blast_radius⊆write_scope` | 2 构造 + 1 实测（绕门） |

#### 7.2 三分处置总表（事实面 / 政策面 分列）

| 门 | 事实面 | 政策面 | 事实面三分 | 政策面三分 | 前置 |
|---|---|---|---|---|---|
| `stage-confirm` | 结构校验 + goal 绑定 | 该不该开/范围 | (1) 守卫 | (3) | `validate_roadmap` 规则分类 |
| `stage-close` | 最终裁决 + 台账 | 目标达成/开放下一 stage | (1) 仅当优先级冻结+台账结构化；否则 (3) | (3) | D-002；provenance 全覆盖 |
| `stalled` | 原因一致 + 三类判定 | 继续投入/带外修复 | (1) 仅 `proven-false-negative`；否则 (2)/(3) | (3) | 解析器版本冻结 |
| `budget-exhausted` | 计数 + gaps + 效果有界 | 上限值 | (1) | (3)-lite | 影子模式（AC-024） |
| `goal-change` | 内容变更 + 规范面 | resume/改计划 | (1) 仅"不起门" | (3)（黑名单） | before-image + 修 reject 语义 |
| `xkey-authorize` | S4 绿 + 写面 | 授权 | (1) 仅 S4；写面 (3) | (3)（黑名单） | `write_scope`（AC-014） |

**顺序约束**：AC-022（D1 `gate-\d{4}`）→ AC-029/AC-030（证据快照/防伪）→ 本卡的新命题上线 → AC-017/AC-018（护栏/审计）→ case 1。**不满足则 case 1 会重演"重复消费"与"自动盖章"**。

#### 7.3 字段清单（新增；两侧同波）

| 门 | 新增字段（`: type`） |
|---|---|
| 通用 6 类 | `schema_version: int`（默认 1）、`evidence_snapshot: list[{path,sha256,mtime_ns}]`、`observed_at: iso8601`、`answer_source: enum{human,auto}`（**仅留痕、不可信**，见 AC-030）、`auto_policy_id: str`；可选 `default_action` / `expires_at`（AC-019） |
| `stage-confirm` | `structural_validation: list[str]`、`proposal_sha256: str`、`goal_sha256: str` |
| `stage-close` | `verdicts_final: list[{key,verdict,source,source_sha256,anchor_mtime_ns,suspect}]`、`open_items: list[{kind,key,item,disposition}]`、`subject_sha256: str` |
| `stalled` | `reason_code: enum`、`cause_counts{loop,used_rounds,round_limit,credits_used}`、`false_negative_class: enum`、`fn_basis{rule,source,source_sha256}` |
| `budget-exhausted` | `cause_counts{...}`、`gap_items: list[{item,rule,severity}]`（或 `blocking_gap_count: int`） |
| `goal-change` | `goal_sha256_before: str`、`goal_sha256_after: str`、`goal_diff{sections_added,sections_removed,sections_changed,normative_changed}` |
| `xkey-authorize` | `write_scope: list[str]`、`blast_radius{files,sha_before}`、`authorization_snapshot: str`、`verify{test_id,red_before,red_after,returncode,timed_out,stdout_sha256}` |

字段名去重后 = `schema_version, evidence_snapshot, observed_at, answer_source, auto_policy_id, structural_validation, proposal_sha256, goal_sha256, verdicts_final, open_items, subject_sha256, reason_code, cause_counts, false_negative_class, fn_basis, gap_items, goal_sha256_before, goal_sha256_after, goal_diff, write_scope, blast_radius, authorization_snapshot, verify`（+ 可选 `default_action`/`expires_at`）+ 1 项非字段（goal before-image 镜像）。

#### 7.4 两侧镜像与向后兼容（统一）

- **Python**：`gates.py:68-81` `FRONTMATTER_FIELDS` 追加；`Gate` dataclass（`gates.py:~110`）加字段；`_gate_file_content:159` 渲染新键；`_to_gate:381` 解析新键（缺省 `None`）；`create:262` 形参可选。**`_REQUIRED_FIELDS:86` 不动**。
- **TS**：`status-model.ts:572-585` `GATE_FRONTMATTER_FIELDS` 追加；`GateRecord:587` 加字段（可选）；`parseGateFile` 解析。`gate-writer.ts:50` `ANSWER_FIELDS` **保持 4 个**（自动决策是 conductor 路径，不走 `answerGate`）。
- **同波硬约束**：两侧解析器 fail-closed（`gates.py:347` / `status-model.ts:660`）⇒ 任何写者先发新字段会让旧侧**整 tick 跳过该门 / 面板看不见该门**。必须同一波合并（AC-010 / P-021）。
- **向后兼容**：既有 34 个 gate 文件缺新字段 ⇒ `None` ⇒ **自动资格缺失** ⇒ case 3，不报错、不需迁移。历史数据不可回填（provenance <5/22、correction 3 个、goal before-image 0）⇒ 明确"只对冻结时刻之后生效"。
- **审计不可信边界**：`answer_source`/`answered_by`/`answered_at` 都是应答者可写（`gate-writer.ts:139`；实测 E2 `gate-0007` 早 4.1h），**机器审计以 timeline（conductor 写）为准**（AC-030），门文件字段只作展示。

---

## 结论 → 决策映射

### 支撑 AC-025（逐 gate 类型的三分判定 + 命题选层）

| AC-025 子要求 | 本卡交付 |
|---|---|
| 每门**重写后的命题**（机器可判且有信息量） | §1.2–§6.2 的"事实面 P"列；每门至少一条 `trigger ⊬ P` 的 witness |
| 命题的**证据字段**（`file:line` + 字段名） | §1.3–§6.3 表 + §7.3 字段清单 |
| 机器能否**独立复算** | §1.4–§6.4 自举判定 + §7.2 |
| **反例**（证据存在但命题不成立） | §1.2–§6.2 的"构造性反例"列；沿用 RQ-12 C1–C5，其中 C1–C4 全部是 `stage-close` 的假 |
| **恒真自检判据** | §7.1（现状全部恒真/半恒真；重写后每门有 witness）+ §7.4 的"自动资格缺失即 case 3" |
| **命题两分**（事实 vs 政策） | §7.2；case 1 只给事实面 |
| 不得按历史答案分布判定 | 全卡未使用答案分布；白名单判据=命题可复算且可为假（U-8） |

### 决策候选（PM 在 `design.md` 分配 D-00x 号）

| 候选 ID | 决策 | 依据 |
|---|---|---|
| D-00x-1 | **命题两分**：每门事实面（可自举）+ 政策面（人）；case 1 只给事实面 | §0–§7.2；PM 自采 F2 |
| D-00x-2 | **冻结取证源优先级**（provenance > correction > 末轮复算 > `l3-verdict.txt` > 散文）+ 不一致 fail-closed 取 `below` | §2.2 C1/C4；RQ-12 I2；`conductor.py:1415` |
| D-00x-3 | **逐门三分表**（§7.2）：case 1 = `budget-exhausted` 全域 + `stalled`/`xkey` 的窄子集 + `goal-change` 的"不起门" | §7.2；RQ-12/RQ-10/RQ-13 |
| D-00x-4 | **gate schema v2**（§7.3 字段）+ 两侧同波 + 旧文件默认 `None`（不进必填集） | §7.4；AC-010 |
| D-00x-5 | `goal-change` 改为**仅规范面变更才起门**（mtime-only / 非规范面 ⇒ `goal-refresh` 不打扰人）+ 修 reject 语义 | §5.2–§5.6；JC gate-0002 |
| D-00x-6 | `stalled` 增 `false_negative_class`；仅 `proven-false-negative` 走 case 1，`real-defect`/`undecidable` 走 (2)/(3) | §3.2–§3.5；C4/E2 gate-0014 |
| D-00x-7 | `stage-close` 的 `verdicts_final`/`open_items` 是 case 1 的**硬前置**，缺失即 case 3 | §2.2–§2.6；C1–C4 |
| D-00x-8 | 顺序：AC-022(D1) → AC-029/AC-030（快照/防伪）→ 本卡命题 → 护栏 | TL;DR 7；`conductor.py:310` |

### 与其它卡/AC 的边界（不越界）

- **不答**"哪些门可自动"的最终白名单（AC-016 的题）；本卡给的是**命题与判据**，可自动化资格取决于 D-002 是否冻结及数据覆盖。
- **不做**呈现契约（AC-026 / RQ-14 的题）；本卡只指出新字段需被 layer-2 卡片渲染（RQ-14 L12）。
- **不做**护栏/审计机制（AC-017/AC-018 / D5 卡的题）；本卡只给"审计以 timeline 为准"的边界。
- **不做**延后机制实现（AC-027 / D2 卡的题）；本卡只把 `stalled`/`budget-exhausted` 映射到 case 2 并援引 RQ-13。

## 数据缺口

| # | 缺口 | 性质 | 影响 | 补法 |
|---|---|---|---|---|
| G1 | `budget-exhausted` / `xkey-authorize` 生产 **0 样本** | 无样本 | 两门的 case 1 是**纯代码推理** | 影子模式（AC-024） |
| G2 | `l3-verdict-provenance.json` 覆盖 **<5/22** | 数据不全、**不可回填** | `stage-close` P1 只能对新 stage 生效 | 扩 `_l3_provenance_record:1356` 到全轮次 |
| G3 | correction sidecar 只覆盖 E2 **3** key，且**非框架契约** | 项目级产物 | 依赖它等于依赖非框架契约（P-021/P-022） | 把 `counted_as_done` 升为框架字段 |
| G4 | `goal.md` before-image **全项目不可得** | 无数据源 | `goal-change` P1/P2 无法历史验证 | conductor 落不可变镜像（§5.6） |
| G5 | `write_scope` 生产代码**零命中** | 无数据源 | `xkey` P3 不可判 | AC-014 前置（本 key 范围外） |
| G6 | `open_items` 结构化台账**不存在**（只在 note/`achieved.md` 散文） | 无数据源 | `stage-close` P2 现状**空洞恒真** | 新增 `open_items` 字段（§2.6） |
| G7 | `validate_roadmap` **未被 conductor 调用**，且 FM/E2 当前不合法 | 半可补 | `stage-confirm` P1 会大量假阳 | 先做结构/运行期规则分类 |
| G8 | 带外修复记录（≥16/22）**只在 note**，且写在应答后 | 无可用数据源 | `stalled` 的 case 1 不能覆盖"需修复"样本 | 结构化的 `prior_fix` 字段或 timeline 事件（须非应答者写） |
| G9 | 证据漂移 **24/34**（应答后改写） | 可补 | 任何复算判的是"现在的文件" | `evidence_snapshot`（sha+mtime）绑定（AC-029） |
| G10 | `answered_at`/`answered_by` **应答者可写** | 可补 | 自动决策审计不可信 | 以 timeline 为准 + 写者身份字段（AC-030） |
| G11 | 绕门散文授权路径 `cross-key-repair-request-*.md` **无 schema** | 无数据源 | `xkey-authorize` 门可能被绕过 | 只读扫描 + fail-closed 视为未授权（AC-031） |
| G12 | `_consumed_gate_ids` 的 `gate-\d{4}` 在 `gate-10000+` **静默失效** | 缺陷 | case 1 会重演重复消费 | AC-022 D1（**硬前置**） |
| G13 | `stage-confirm` 的人填约束只在 note 散文 | 无数据源 | P3 不可机读 | 结构化 `constraints`（AC-026 范围） |
| G14 | 未复核项：`mark_stalled` 的 12 个调用点行号（RQ-12 给出，本卡只复核了 `:3944/3971/3974`） | 方法留痕 | 影响 `reason_code` 传参的改动面估算 | `grep -n "mark_stalled(" conductor.py` 逐点确认 |

## [VERIFY]

```
[VERIFY] D1-gate-propositions: gates=6 rewritten=[stage-confirm,stage-close,stalled,budget-exhausted,goal-change,xkey-authorize]
current_propositions_tautological=6/6 (stage-close worst: question subject == conductor.py:629-631 trigger)
new_fact_propositions=[stage-confirm: structural_validation==[] AND goal_sha256 match; stage-close: verdicts_final all meets|closed-legacy AND open_items==[]; stalled: reason_code==recomputed cause AND cause_counts match AND false_negative_class!=undecidable; budget-exhausted: used==limit+credits AND blocking gaps nonempty; goal-change: sha_before!=sha_after AND normative_changed; xkey-authorize: red_after==0 AND rc==0 AND test_id bound AND blast_radius subset write_scope]
counterexamples_real=[C1 E2 stage2 correction below+counted_as_done=false while l3-verdict.txt=meets and stage closed, C2 FM stage1 C-09/NRR-1/2 prose-only, C4 FM gui-contract-mock-tests file=meets vs recompute=below, C5 JC gate-0004 2/2 vs 3/3, JC gate-0002 non-normative-only, JC gate-0001 confirmed after goal change] counterexamples_constructive=[mtime-only goal change, budget credit drift, xkey false-green, stage-confirm structural violation]
selfbootstrap=[budget-exhausted=full(proposition face, 0 samples), stage-confirm=partial(structural needs rule split; goal_sha full), stage-close=partial(P1 needs frozen priority+provenance coverage <5/22; P2 needs structured ledger; P3 semantic), stalled=partial(P1 full; P2 only proven-fn/defect, semantic undecidable; P3 prose-only), xkey-authorize=partial(P1/P2 full; P3 data absent write_scope zero hits; P4 prose path), goal-change=partial_only_with_before-image(P1/P2 need mirror; P4 structurally absent + reject no-op)]
three_way_mapping=[case1: budget-exhausted(all), stalled(false-negative subset), xkey(S4), goal-change(do-not-raise-gate only), stage-confirm/close(guards only); case2: stalled(real-defect/undecidable), budget-exhausted; case3: all policy faces + stage-close P3 + goal-change P4 + xkey P3/P5]
field_names_new=23 (+optional default_action,expires_at) +1 non-field(goal before-image mirror)
mirror=[gates.py:68 FRONTMATTER_FIELDS, gates.py:86 _REQUIRED_FIELDS unchanged, gates.py:159 render, gates.py:381 _to_gate; status-model.ts:572 GATE_FRONTMATTER_FIELDS, :587 GateRecord, parseGateFile; gate-writer.ts:50 ANSWER_FIELDS unchanged]
backward_compat=old gate files omit new fields => None => ineligible for auto (case 3), no migration; new fields must be registered both sides before any writer emits them (gates.py:347 / status-model.ts:660 fail-closed)
precedence=AC-022(D1 gate-\d{4} conductor.py:310) -> AC-029/AC-030 (evidence snapshot/anti-forge) -> new propositions -> AC-017/AC-018 guardrails
data_gaps=14 (G1 0-sample budget/xkey; G2 provenance <5/22; G3 correction 3 non-framework; G4 goal before-image absent; G5 write_scope zero hits; G6 open_items unstructured; G7 validate_roadmap uncalled; G8 out-of-band fix prose-only; G9 drift 24/34; G10 answered_* answerer-writable; G11 off-gate prose authorization; G12 5-digit id regex; G13 constraints in note; G14 mark_stalled caller line numbers unreviewed)
wrote_only=evidence/research/design-gate-propositions-20260926.md (+ workers/msc-d1-gate-propositions/output.md)
```

**写入通道说明**：本会话**没有** `write`/`edit` 工具（只读 research 角色），故设计正文先落到本卡自己的任务目录 `report-gate-propositions.md`，再由 PM/编排侧复制到卡片指定路径；本卡未触碰任何其他文件（不改代码、不答 gate、未碰 FM/E2/JC、未 commit）。
