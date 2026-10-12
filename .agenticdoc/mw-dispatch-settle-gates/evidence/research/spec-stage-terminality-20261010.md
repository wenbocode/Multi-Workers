# RQ-1: "stage 终态"的机器可读锚 — `mw-dispatch-settle-gates` / AC-002

> 调研范围：`packages/multi-workers/autopilot/*`（Python）与其 TS 镜像
> `packages/coding-agent/src/extensions/agent-team-loop/autopilot/*`。
> 只读调研；未修改任何文件（唯一写入 = 本 `report.md`）。

## 0. 口径与边界

### 0.1 先分开两层："stage" vs "key/phase"

本项目里 `stage` 与 `key`/`phase` **不是同一层**（任务书要求的"请明说"）：

- **autopilot roadmap stage** = `.agenticdoc/_autopilot/_roadmap.md` 里的
  `## Stage N: <title>` 段，段内 `> status:` 是 stage 生命周期
  （`roadmap.py:53-60` `STAGE_STATUSES`）。一个 stage **包含多个 key**
  （`### Keys` 表，`roadmap.py:102-115`），stage 关闭的前提是它**所有 key**
  都终态（`conductor.py:870-878` `_stage_closure` 前置条件）。
- **AgenticTask key phase** = `pm-state.md` 的 `- Phase:` / `_index.parallel`
  的 Phase 列 / `_project_log.md` 的 Completed 行，逐 **单个 key** 的阶段
  （`advance_phase.py:25` `PHASES = [spec…done]`）。

AC-002 的"stage 终态"只能指前者（多 key 容器）；后者是 key 级，不构成
stage 终态锚。逐 key 证据：`roadmap.py:416-429`（key-status 的 key 集必须
与 `### Keys` 表双向一致）、`conductor.py:870-878`（stage 关门的全 key
终态前置条件）。

结论前置：**本项目存在一等 stage 实体**（不是"没有独立 stage 概念"），
所以 AC-002 的判据粒度应写成 **stage 级**（roadmap `> status:` 的终态族），
而不是 key 级完成。

### 0.2 数据可得性（"真实数据"的口径）

本仓库 checkout **没有 live autopilot 数据**：

```
Get-ChildItem -Recurse -Filter "gate-*.md"   -> Count 0
Get-ChildItem -Recurse -Filter "_roadmap.md" -> Count 0
```

（autopilot 跑在另一个控制工作区/目标项目上，本仓库只含框架代码与
`.agenticdoc` 的 AgenticTask 侧数据。）因此：

- roadmap / gate / stage 的"真实数据示例"取自**测试夹具与设计文档**，每条给行号；
- pm-state / `_index.parallel` / `_project_log.md` 侧取自 **live `.agenticdoc`**。

### 0.3 判据落点的既有约束（沿用上一 key）

- 提醒"纯判据只在 Python"（`conductor.py:2492-2499` D-005/D-006 注释；TS 只
  转发 `gate-reminder` 事件，不重判）。
- "缺失 ⇒ 放行"（spec §6 坑点，引 `mw-gate-verdict-hardening` D-015）：
  roadmap 缺失/不可读必须**不抑制**提醒。
- fail-closed 只用于"有记录且冲突"，不用于"无记录"。

## 1. 候选锚清单

> 粒度列：stage=多 key 容器；key=单 key；gate→stage/key=门自身携带的归属；
> run=worker 单次运行；证据=产物文件。反例风险编号见 §1.2。

| # | 候选 | 机器可读形态 | `文件:行号` | 真实数据示例（路径:行） | 粒度 | 反例风险 |
|---|---|---|---|---|---|---|
| C1 | **roadmap stage status**（主锚） | `## Stage N` 段内 `> status: pending\|approved\|running\|closed\|closed-human\|halted`；终态族 = rank 2 | `roadmap.py:53-60`（enum）、`conductor.py:553-564`（`_STAGE_STATUS_RANK` :556-563 + `_STAGE_TERMINAL_RANK` :564）、`conductor.py:849-908`（`_stage_closure`）| `test_autopilot_roadmap.py:72-84`（`> status: running` / `> status: pending`）；终态表 `test_autopilot_gate_guards.py:189`（`running→closed-human` 允许）、`:195-197`（`closed`/`closed-human`/`halted` 互不迁移）| stage | R4, R10, R11 |
| C2 | roadmap key-status | `> key-status: k=done, ...` | `roadmap.py:63-71`（`KEY_STATUSES`）、`:343-372`（parse）、`:477-483`（`stage_of_key`）| `test_autopilot_roadmap.py:75`（`k1=done, k2=running`）；`test_autopilot_conductor_stage.py:70` | key | R1, R3 |
| C3 | `pm-state.md` `- Phase:` / `- Completed:` | `- Phase: <UPPER>`；`done` 时才有 `- Completed: <ts>` | `advance_phase.py:345-351`（Phase 重写）、`:375-395`（仅 target=done 写 Completed）；读侧 `audit_evidence.py:62`/`:206-212`、`dispatch.py:117-145` | `.agenticdoc/mw-gate-verdict-hardening/pm-state.md:5`（`- Phase: DONE`）、`:8`（`- Completed: 2026-10-10 19:22`）；active key `.agenticdoc/mw-dispatch-settle-gates/pm-state.md:5`（`- Phase: SPEC`）| key | R1, R8 |
| C4 | `_index.parallel` Phase/Status 列 | `\| key \| active\|idle \| PHASE \| ... \|` | `update_index.py:4-12`（schema/enum）、`state.py:75-95`（`_parse_index_row`）、`state.py:97-103`（`read_index`）| `.agenticdoc/_index.parallel:47`（`\| mw-gate-verdict-hardening \| idle \| DONE \| ...`）、`:51`（`\| mw-dispatch-settle-gates \| active \| SPEC \| ...`）| key | R2, R8 |
| C5 | `_project_log.md` Completed 表 | `\| Completed \| Commit \| Key \| ... \|`，仅 done 追加 | `advance_phase.py:451-453`（append）、`:610-613`（done 才调）| `.agenticdoc/_project_log.md:5`（表头）、`:38`（`\| 2026-10-10 19:22 \| 776b82d7f \| mw-gate-verdict-hardening \| ...`）| key | R2, R8 |
| C6 | gate frontmatter 的 `stage` / `key` 归属 | 40 名冻结字段里的 base 项 `stage`(int\|None) / `key`(str\|None)；必填仅 6 | 字段序 `gates.py:95-108`（base 12，`stage` :99、`key` :100）、`:110-138`（v2 28）；字段类型 `gates.py:226-227`；必填集 `gates.py:146-153`（`_REQUIRED_FIELDS`，import 期 assert 冻结）；**无 `phase` 字段** | 无 live gate（`gate-*.md` 计数 0）；夹具 `test_autopilot_gate_reminder.py:103-130`（`stage=None,key="k1"`）、`test_autopilot_gates.py:147`（`stage=2`）、`:187`（`stage=2,key="k3"`）| gate→stage/key | R5 |
| C7 | `[END]` / `[DONE]` 标记 | `[END] <ts> exit=... elapsed=...s tools=... phases=...` | `mw_common.py:2281`（`_END_LINE_RE`）、写侧 `output-writer.ts:263-269`；`[DONE]` = **不存在**（仅 `packages/ai` 的 SSE 协议：`openai-codex-responses.ts:798`、`pi-messages.ts:310`）| `test_common.py:428`、`test_launcher.py:699`（`[END] …` 夹具）| run | R9 |
| C8 | closure dossier `stage-N-close.md` | 文件存在 | `conductor.py:887-905`（写 dossier）、`evidence.py:141`（`_DOSSIER_RE = ^stage-\d+-close\.md$`）| 无 live；`evidence.py:141` | 证据（stage 级） | R9 |
| C9 | `_index.md` 的 `active:` | `active: <key>` | `.agenticdoc/_index.md:1`（本仓库为 `active: xkey-repair-mechanism`，已 stale）| 同上；与 `.agenticdoc/_index.parallel:51`（`mw-dispatch-settle-gates active`）冲突 | key | R2 |
| C10 | conductor timeline 事件（`stage-close` / `gate-answered`） | 事件词 | `timeline.py:76`（`stage-close`）、`:95`（`stage-reopen-refused`）；追加点 `conductor.py:537-540`（stage-close）、`:533-536`（gate-answered）| `test_autopilot_conductor_stage.py`（`stage-close` 事件断言）| stage（事件）| R9 |

候选数 = **10**（C1…C10）。

### 1.2 反例风险台账（9 条）

- **R1（key 级完成当 stage 终态）**：若用 `pm-state.md - Phase: DONE` /
  `_index.parallel Phase=DONE` 让"该 key 的所有门"不提醒，则一个 key done
  但**同 stage 其它 key 仍在跑/仍有 pending 门**的场景被误伤。证据：一个 key
  的 `- Phase: DONE`（`.agenticdoc/mw-gate-verdict-hardening/pm-state.md:5`）
  与该 key 所属 stage 的 `> status:` 是两条独立的写路径
  （`advance_phase.py:345-351` vs `conductor.py:604-638`）。
- **R2（第二真相源漂移）**：C3/C4/C5/C9 与 roadmap `> status:` 各自独立维护；
  本仓库就存在 `_index.md:1`（`active: xkey-repair-mechanism`）与
  `_index.parallel:51`（`mw-dispatch-settle-gates active`）不一致的实例。
  用它们判 stage 终态会把"索引漂移"变成"提醒漂移"。
- **R3（命名误导）**：`_STAGE_TERMINAL_STATUSES`（`conductor.py:77`）
  名字像 stage 终态集，**实际是 key-status 终态集** `("done", "closed-legacy")`
  （对比 `roadmap.py:63-71` `KEY_STATUSES`），只被 `_stage_closure` 的
  **前置条件**用（`conductor.py:870`）。若 design 直接复用这个名字，会把 key
  终态当 stage 终态（= R1 的代码级成因）。stage 终态集在同文件另一处：
  `_STAGE_STATUS_RANK` rank 2（`conductor.py:556-564`）。
- **R4（`halted` 两侧口径不一致）**：conductor 把 `halted` 记为 rank-2 终态
  （`conductor.py:562`），且 `halted` 时 `_stage_activation` 直接不活动
  （`conductor.py:700-702`）；但面板 `currentStage` 把 `halted` 当"未关闭"
  继续显示（`status-model.ts:1393-1399`，只排除 `closed`/`closed-human`）。
  实现方若照抄面板口径，halted stage 的门会继续提醒（漏 AC-002）。
- **R5（多数生产门 `stage=None`）**：只按 `gate.stage` 过滤会半实现 AC-002。
  生产创建面：带 `stage` 的只有 stage-confirm（`conductor.py:659`/`:725`，
  stage 参数 :663/:729）、stage-close（`:903`，stage 参数 :908）、defer
  review gate（`:3586`，`key+stage` :3588）；**key 级的 stalled
  （`conductor.py:5181`，`key=key` :5190）、budget-exhausted（`:1252`，
  `key=key` :1257）、xkey-authorize（`:3928`，`key=owner_key` :3938）与全局
  goal-change（`:2789-2791`，走 `gates.create`）都不带 stage**。仅 4/8 个
  创建点带 stage ⇒ 必须做 key→stage 反查（`roadmap.py:477-483`）。
- **R6（fail-closed 误伤全部提醒）**：roadmap 缺失/解析失败时若选择"不确定
  即抑制"，会把所有提醒静默（违反 D-015 "缺失⇒放行"），并让现有 12 个
  reminder 测试（`test_autopilot_gate_reminder.py:133-354`）全红——它们的
  fixture 项目 **没有** `_roadmap.md`（`_project` `:41-48` 只建
  `.agenticdoc/_autopilot/`）。
- **R7（协议函数语义收窄）**：把过滤塞进 `gates.pending_gates`
  （`gates.py:770-772`，docstring `Only gates still awaiting an answer`）会让
  "pending = 未答"变成"pending = 未答且 stage 活动"，且该语义依赖 roadmap
  可读性；未来展示消费者再取历史未答门时会被迫二次实现。
- **R8（key→stage 映射悬空）**：`gate.key` 对应的 key 可能不在当前 roadmap
  （`_scratch`、历史 key、roadmap 重排/删 stage 后）。映射缺失必须放行；
  若当作"无 stage ⇒ 不提醒"会静默。
- **R9（把 run/证据/事件当 stage 状态）**：`[END]` 是 worker **单次运行**的
  终态（`mw_common.py:2281`）；`stage-N-close.md` 是关门**证据**——它在
  stage-close 门**待答窗口**里就已写出（`conductor.py:887-905`，门在 :903
  才创建）；timeline 只有 200 事件 tail、明确短于第二提醒间隔
  （`conductor.py:2492-2499`）。三者都不能作为可回读的 stage 状态锚。
- （R10/R11 见 C1 列：R10 = `closed-human` 无 conductor 写入点，只由人工
  编辑产生（全仓搜 `closed-human` 只有 enum/测试/注释命中：
  `roadmap.py:58`、`conductor.py:561`、`status-model.ts:396`、
  `test_autopilot_gate_guards.py:189/195`），因此不能只实现"conductor 写过
  的 closed"；R11 = `gate.stage` 是创建时快照，roadmap 重排/删 stage 后
  悬空，需按 R8 放行。）

## 2. 调用面清点

### 2.1 两个判据函数的全部调用点

| 函数 | 定义 | 生产调用点 | 测试调用点 |
|---|---|---|---|
| `gates.pending_gates` | `gates.py:770-772` | **1 处**：`conductor.py:2564`（`_remind_pending_gates`）| `test_autopilot_gates.py:264`、`:278`、`:444`、`:460` |
| `conductor.pending_gate_reminders` | `conductor.py:2522-2560` | **1 处**：`conductor.py:2575`（`_remind_pending_gates`）| `test_autopilot_gate_reminder.py:138,139,142,147,150,154,156,159,164,171`（10 处） |

搜证命令（无 `dist/`、`node_modules/`、`__pycache__/`、`.tmp/`）：

```
Get-ChildItem -Recurse -Include *.py,*.ts | Select-String -Pattern "pending_gates|pending_gate_reminders"
```

⇒ `gates.pending_gates` 在 Python 生产代码里**只有一个消费者**（提醒取数），
`pending_gate_reminders` 只在提醒壳里被调。

> 该命令会多出 7 处**非调用**命中（不计入上表）：
> `.agenticdoc/mw-gate-verdict-hardening/evidence/scripts/t23-qga-corrections.py`
> （2）与 `t23-qgb-corrections.py`（4）、`t23-quality-gate-report.py`（1）
> —— 历史证据脚本，非生产代码；`gates.py:16` —— docstring 里提及
> `pending_gates()`（另有 :770 定义行本身）；`test_doctor_gates.py:530` ——
> 测试函数名 `test_missing_fields_only_reported_for_pending_gates` 含子串，
> 但函数体不调用 `pending_gates`。

### 2.2 pending 门的全部读取路径（提醒 vs 展示 vs doctor）

| # | 调用点 | 消费目的 | 加 stage 终态过滤后的影响 | 建议 |
|---|---|---|---|---|
| S1 | `conductor.py:2564` `gates.pending_gates(gates_dir(...))` | **提醒**（取数）| 直接改变提醒集合（这正是 AC-002 要的效果）| 过滤放在下游纯判据（见 §3），此处仅多传一个 stage 事实 |
| S2 | `conductor.py:2575` `pending_gate_reminders(...)`（纯判据）| **提醒**（判据）| 新增第 4 条件（stage 非终态）| **推荐落点**：签名加 `stage_status_of` / `terminal_stages`，保持无 IO、可注入 |
| S3 | `conductor.py:2764` `_remind_pending_gates(project_root, st, cfg)` | **提醒**（tick step 2b 唯一入口）| 无（不再加过滤）| 不动 |
| S4 | `mw_common.py:3054` `_doctor_gates`（自带 `pending = [g for g in parsed_gates if g.status == "pending"]` at `:3105`，entry 构造 `:3110`）| **doctor/展示** | **不受影响**（不经过 `gates.pending_gates`；独立用 `gates.enumerate`）| 保留显示历史未答门；如需区分可加 `stage_terminal: true` 标记而非隐藏 |
| S5 | `mw_common.py:3235-3246` `_doctor_issues`（读 `gates_section["pending"]`）| **doctor 告警** | 不受影响（同 S4 数据源）| 同 S4 |
| S6 | `monitor.ts:234` `scanPendingGate` + 扫描 `:416-435` + `blockedOnHuman` `:442` | **面板展示** | 不受影响（独立 TS 扫描，只按 `status: pending`）| 保留（历史门仍应可见）|
| S7 | `console.ts:349-356` `renderGateCards`（pending filter `:351`）、`:448` `cmdGates`、`:506` | **`/autopilot gates` 展示** | 不受影响（`status-model.ts:1002 listGates` 独立）| 保留 |
| S8 | `status-model.ts:1002` `listGates` + GateView map `:1464` + status 文本 `:1529-1532` | **`/autopilot status` 展示** | 不受影响 | 保留 |
| S9 | `conductor.py:195` `open_goal_change_gate` / `:487-550` `_consume_answered_gates` | 状态机（非提醒）| 不受影响 | 不动 |

生产读取路径合计 = **7**（S1/S2 提醒 + S4/S5 doctor + S6/S7/S8 展示；
S3 是 S1/S2 的入口，S9 不是读取面）。

**区分结论**：提醒面（S1/S2）**只有 Python 一处**，展示面（S4–S8）与提醒
面在代码上**完全解耦**（doctor 用 `gates.enumerate`+自过滤；TS 全部自带
解析器）。因此把 stage 终态过滤加在提醒侧，展示面可原样保留历史未答门，
不需要任何 TS 改动。

## 3. 推荐方案与理由

### 3.1 推荐锚

**roadmap stage status 的终态族**（C1）：

- 终态判定单一真相源 = `conductor.py:556-564`
  （`_STAGE_STATUS_RANK` rank 2 = `{closed, closed-human, halted}` +
  `_STAGE_TERMINAL_RANK = 2`），与 stage 状态写的单调迁移守卫
  （`_stage_transition_allowed` `conductor.py:567-583`）**同源**。
- gate→stage 解析（两级，缺失即放行）：
  1. `gate.stage is not None` → 用该 stage 号（`gates.py:226`）；
  2. 否则 `gate.key` 非空 → `roadmap.stage_of_key(rm).get(gate.key)`
     （`roadmap.py:477-483`，first-declaration-wins）；
  3. 都解析不到（全局 `goal-change`、`_scratch`、key 不在 roadmap）→ **不抑制**。
- roadmap 文件缺失或 `RoadmapError` → **不抑制**（fail-open，D-015）。

### 3.2 落点

**`pending_gate_reminders`（纯判据，`conductor.py:2522-2560`）新增第 4 条件**，
取数在 `_remind_pending_gates`（`:2555-2593`）：

- `_remind_pending_gates` 在 `pending = gates.pending_gates(...)`（`:2564`）
  之后、调用纯判据（`:2575`）之前，读一次 roadmap（`roadmap.load_roadmap`
  `roadmap.py:236`），构造 `stage_status: dict[int,str]` 与
  `stage_of_key: dict[str,int]` 注入纯函数；
- 纯函数对每个 due gate 解析 stage 号，命中终态族则 `continue`；
- 建议把终态谓词提为 `roadmap.py` 的一个具名 helper（紧邻
  `STAGE_STATUSES` `roadmap.py:53-60`），避免调用方各自拼
  `{closed, closed-human, halted}`。

不建议落 `gates.pending_gates`（`gates.py:770-772`），理由见 R7 / §3.3。
不建议新增快照文件（违反"只读面不建文件"与本 key 的"判据机械化"方向）。

### 3.3 为何不误伤 AC-005 / AC-006

- **AC-005（活动 stage 照旧提醒）**：活动 stage 的 `> status:` ∈
  {pending, approved, running} ⇒ rank < 2（`conductor.py:557-559`），不命中
  终态族。key 级门（stalled/budget）经 `stage_of_key` 映射到**包含该 key 的
  stage**；活动 stage 包含它 ⇒ 照旧提醒。反向证明：`_project`
  （`test_autopilot_gate_reminder.py:41-48`）的 fixture 项目**没有 roadmap**
  ⇒ 走 fail-open 分支 ⇒ 现有 12 个 reminder 测试（`:133-354`）行为逐字不变。
- **AC-006（已答门零残留）**：过滤的是"未答门集合"。已答门本来就由
  `status == "pending"` 排除（`gates.py:770-772`），两个判据正交；被抑制的
  gate **不写任何文件**（`_reminder_count` 仍按 `gate_id` 读账本，
  `conductor.py:2505-2516`），因此若人工把 stage 改回 `running`，提醒从当前
  计数继续、不会重复也不会丢失——无残留状态。
- **不引第二真相源**：不读 `pm-state.md`/`_index.parallel`/`_project_log.md`
  （C3/C4/C5），只用 roadmap；roadmap 的 stage 状态本来就由 conductor 在
  `_set_stage_status`（`conductor.py:604-638`）写，是唯一写者。

### 3.4 需 design 明确的一个口径分叉（`halted`）

`halted` 在 conductor 是 rank-2 终态（`conductor.py:562`）且 stage 不活动
（`:700-702`），但面板把它当"当前未关闭 stage"显示
（`status-model.ts:1393-1399`）。推荐**采 conductor 口径**（`halted` ⇒
不提醒），理由：提醒语义是"有人在等一个活动 stage 的门"，halted 时框架已
暂停派发，提醒应由 stage-close 门被 reject 时的那条路径承载。若 PM 认为
"halted 后仍需要人答门才能恢复"，则终态集退为 `{closed, closed-human}`——
这是 design 阶段的单点决策，需显式记 D-xxx。

## 4. 反向用例设计

（输入 → 期望 → 防哪种误伤；均可用 `test_autopilot_gate_reminder.py` 现有
夹具 + `test_autopilot_conductor_stage.py:59-84` 的 `_two_stage_roadmap`）

**U1 终态 stage + 未答门 ⇒ 零提醒（主判据）**
- 输入：`_two_stage_roadmap(stage1_status="closed", k1_status="done")`
  （`test_autopilot_conductor_stage.py:59-84`）；gate 带 `stage=1`
  （`gates.create(..., "stage-confirm", q, stage=1)`，参考
  `test_autopilot_gates.py:123`/`:147`），`_age_gate(gate_file, 31)`
  （`test_autopilot_gate_reminder.py:76-99`）；`_workers.parallel` 缺失或全终态。
- 期望：`conductor.tick` 后 `_remind_rows == []` 且
  `_events(project,"gate-reminder") == []`；roadmap 与 gate 文件字节不变。
- 防：AC-002 主判据（stage 级路径）。
- **非空洞对照**：把 `stage1_status` 改回 `"running"` ⇒ 同输入产出 1 行
  1 事件（证明用例确实被"终态"维度驱动，而非被别的前置条件吞掉）。

**U2 活动 stage + key 级 pending 门 + 无非终态行 ⇒ 照旧提醒**
- 输入：`_two_stage_roadmap(stage1_status="running", k1_status="stalled")`；
  key 级 gate（`stage=None, key="k1"`，`test_autopilot_gate_reminder.py:103-130`
  的 `_gate_at`）；31min；队列只有终态行。
- 期望：1 条 `phase:"remind"` 账本行 + 1 个 `gate-reminder` 事件，`gate_key="k1"`。
- 防：R5（key→stage 映射不能把活动 stage 误判终态）/ AC-005 误伤。
- **非空洞对照**：stage1_status 改 `"closed"` ⇒ 同 gate 归零（双向）。

**U3 roadmap 缺失 ⇒ fail-open 照旧提醒**
- 输入：不写 `_roadmap.md`；pending gate（`stage=None, key="k1"`）31min；
  空队列（= 现有 `test_pending_past_threshold_reminds_once`
  `test_autopilot_gate_reminder.py:177-199` 的环境）。
- 期望：1 行 1 事件（与今日逐字一致）。
- 防：R6（把"无 roadmap"当"stage 终态"而静默全部提醒）。

**U4 全局 goal-change 门不被 stage 纬度吞掉**
- 输入：roadmap 存在且**所有 stage 都 closed**；改动 `goal.md` 产生
  goal-change 门（`stage=None,key=None`，`conductor.py:2789-2791`），31min。
- 期望：照旧 1 行 1 事件（沿用
  `test_goal_change_gate_reminds_while_halted`
  `test_autopilot_gate_reminder.py:327-352` 的形态）。
- 防：R5 边界（无归属门不得被"所有 stage 终态"整体吞掉）。

**U5（口径锁定）halted stage 的门 ⇒ 零提醒**
- 输入：`_two_stage_roadmap(stage1_status="halted")` + 未答 stage-1 门。
- 期望：零提醒（`halted` 是 rank-2 终态族 `conductor.py:562`，且
  `_stage_activation` 在 halted 时 return `conductor.py:700-702`）。
- 防：R4（显式锁 conductor 口径；面板仍显示 halted stage 属**故意**
  差异，此用例把口径差异钉在测试里）。

## 5. 附：搜证命令（可复现）

```powershell
# 1. 判据函数调用点（含测试），排除 dist/node_modules/__pycache__/.tmp
Get-ChildItem -Recurse -Include *.py,*.ts -File |
  Where-Object { $_.FullName -notmatch "node_modules|\\dist\\|__pycache__|\\.tmp\\" } |
  Select-String -Pattern "pending_gates|pending_gate_reminders" |
  Select-Object Path,LineNumber,Line

# 2. stage 终态族唯一真相源
Select-String -Path packages\multi-workers\autopilot\conductor.py -Pattern "_STAGE_STATUS_RANK|_STAGE_TERMINAL_RANK|_stage_transition_allowed"

# 3. gate 创建点的 stage/key 携带情况
Select-String -Path packages\multi-workers\autopilot\conductor.py -Pattern "_create_gate\(|gates\.create\("

# 4. 无 live autopilot 数据
Get-ChildItem -Recurse -Filter "gate-*.md" | Measure-Object | Select-Object Count
Get-ChildItem -Recurse -Filter "_roadmap.md" | Measure-Object | Select-Object Count

# 5. [DONE] 在 stage 语义中不存在
Get-ChildItem -Recurse -Include *.py,*.ts -File |
  Where-Object { $_.FullName -notmatch "node_modules|\\dist\\|__pycache__|\\.tmp\\" } |
  Select-String -Pattern "\[DONE\]"
```

`[VERIFY] RQ1: candidates=10 recommended=roadmap_stage_status call_sites=7 counterexample_risks=9`


---

## PM 现场复核（2026-10-10 21:35，`mw-dispatch-settle-gates` PM）

本文件 = worker `mds-rq1-stage-terminality` 的 `report.md` **逐字收录**（22,649 B / 310 行），正文未改写；
以下为 PM 独立复核（AC-009 证据标准：锚点必须对最终工作区成立）。

### 确认（我逐行看过）

| worker 结论 | 复核 | 证据 |
|---|---|---|
| 推荐锚 = roadmap stage status 终态族 | **成立** | `conductor.py:557-564` `_STAGE_STATUS_RANK`：`pending`/`approved`=0、`running`=1、`closed`/`closed-human`/`halted`=2；`:565` `_STAGE_TERMINAL_RANK = 2`（**worker 未把这条常量列为单一真相源，它比 dict 更适合作锚**） |
| 唯一写者 | **成立** | `_set_stage_status` `conductor.py:605-639`：roadmap 锁 + `_stage_transition_allowed`（`:568`）单调守卫 + `stage-reopen-refused` 事件（`:602`） |
| 提醒面只有 Python 一处 | **成立** | tick `:2764` → `_remind_pending_gates` `:2555`（取数 `:2564` = `gates.pending_gates`） → 纯判据 `pending_gate_reminders` `:2522` |
| 展示/doctor 面解耦 | **成立** | doctor 自读 gates 目录（`mw_common.py:3064`/`:3086`），不经 `pending_gate_reminders` |
| gate→stage 两级解析必要（R5） | **成立（关键）** | 8 个 gate 创建点中**带 `stage=` 的 4 个**：`:659`/`:725`（stage-confirm）、`:903`（stage-close）、`:3586`（defer review，`stage=stage_number`）；**不带 stage 的 4 个**：`:1254`（budget，仅 `key`/`refs`）、`:2792`（goal-change，`gates.create`，无 key 无 stage）、`:3934`（xkey，仅 `key`/`refs`）、`:5187`（stalled，仅 `key`/`refs`）⇒ 只按 `gate.stage` 过滤 = 半实现（上一 key 的复发形态） |
| R6：roadmap 缺失须 fail-open | **成立** | `test_autopilot_gate_reminder.py` 零 `_roadmap` 命中 ⇒ 现有 reminder 测试 fixture 无 roadmap |

### 更正（±1 锚点漂移 / 路径目录名，正文未改）

| worker 原文 | 实际（PM 实测） |
|---|---|
| 「单一真相源 = `conductor.py:556-564`」「`_STAGE_STATUS_RANK` :556-563 + `_STAGE_TERMINAL_RANK` :564」 | dict = **`:557-564`**，常量 = **`:565`**（整体 +1） |
| 「`_set_stage_status`（`conductor.py:604-638`）」 | **`:605-639`**（整体 +1） |
| 面板文件写作 `pm/monitor.ts` | 实际在 **`autopilot/monitor.ts`**（`pm/` 下无此文件） |
| 尾行 `[VERIFY]` | 存在但被**反引号包裹**（`` `[VERIFY] RQ1: …` ``）⇒ 按机器行口径（行首）读不到；PM 已用等价判据核到 `candidates=10 recommended=roadmap_stage_status call_sites=7 counterexample_risks=9` |

### PM 采纳（写入 spec）

- AC-002 判据来源**采用**该锚：终态族 = `_STAGE_TERMINAL_RANK`（`:565`）+ 两级解析（`gate.stage` 优先，否则 `roadmap.stage_of_key`，`roadmap.py:477-483`）+ **解析不到/roadmap 缺失 ⇒ 不抑制（fail-open）**；落点 = `pending_gate_reminders` 第 4 条件，**不放** `gates.pending_gates`（展示面须继续显示历史未答门）。
- `halted` 口径：取 conductor 侧（不提醒），design 显式记 D。
- **数据点（R22 有效性）**：给只读角色注入「唯一写入 = `worker_file report.md`」契约句后，本次交付 22,649 B / 310 行报告；对照同类任务（无契约句、被要求写 `evidence/…`）产出 0 字节 ⇒ L1 任务书纪律是可控变量。
