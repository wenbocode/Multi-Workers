# Design: 「待复核」状态与合法重开（D2 / msc-d2-deferred-review-state）

> Key: `mw-autopilot-slot-capacity` ｜ 角色: **DESIGN 期调研（只读）**；本文件是本卡唯一写面
> 代码基线: `H:/git/Multi-Workers` 工作树快照（`packages/multi-workers/autopilot/conductor.py` 174,500 B / `roadmap.py` 23,583 B / `gates.py` 18,264 B；TS `autopilot/status-model.ts` / `autopilot/monitor.ts` / `autopilot/console.ts` / `worker/worker-mode.ts`）
> 前置证据: RQ-13 `spec-gate-defer-safety-20260926.md`（F1 阻塞性表 / F2 不可逆动作 9 类 / F3 延后规模 / F4 CC-1..CC-9 / F5 重放回归）、RQ-9 `spec-cap-breach-attribution-20260926.md`（占槽谓词与 writer 归属）、spec §1.1.1 / AC-027 / 风险 21/23/24/26/27
> 决策已锁（2026-09-26 用户）：case 2 = **(1)「待复核」状态 + 触发式复核时机 + 时间兜底**；红线 = **待复核 key 不得进入 `_DEP_SATISFIED`（不解锁依赖）**。
> 边界: **不给实现代码**，只给设计面与判据；**不改代码、不答 gate、不碰 FM/E2/JC、不 commit**。本卡**不重复** RQ-13 的门阻塞性/不可逆动作清单，也不重复 RQ-12 的命题重写（属 D1）。

## TL;DR

1. **消费者穷举（F1，本卡最重要的一条）**：生产代码里读 key-status 的点共 **27 个（Python 17 + TS 10）**、**写点 6 个**——Python：`roadmap.py` 5（enum/parse/校验/写帮手/重复行）+ `conductor.py` 11 + `roadmap_check.py` 1；TS：`status-model.ts` 4 + `monitor.ts` 5 + `console.ts` 1（纯渲染）。`mw doctor`（`mw_common.py:2022-2065`）与 `advance.py`/`advance_phase.py` **零读点**（负结论附范围声明，F1.3）。
2. **最危险的一处**：`conductor.py:274` 的派发跳过集是**字面量元组** `("done","stalled","closed-legacy")`。新增状态值若不同步加进这个元组，**待复核 key 会被继续派发**（继续烧 token、继续写源文件）——这就是本 key 的头号失败模式，比"被当成 done"更常见。
3. **状态载体推荐 = 方案 A**：新 key-status 值写在 `_roadmap.md` 的 `> key-status:` 行（单一真相面、roadmap 锁内原子写、面板/console 免费可见），旁挂文件只承载**载荷**（证据快照 / deadline / 决定记录），**不承载状态**。方案 B（纯旁挂）无法单独成状态（key-status 仍须取旧值 ⇒ 两平面可能不一致，而 `_stage_closure`/`_DEP_SATISFIED`/monitor 继续读旧平面）；方案 C（复用 `stalled`+标记位）语义混淆（`stalled` 在今天等于"人已带外修复 + 可 resume 一轮"，与"还没判"不可分）。
4. **stage 收口语义**：待复核**不算终态**，`_stage_closure:629-631` 的终态集保持不变（`("done","closed-legacy")`）；触发式复核是**收口前置**，不是收口替代（RQ-13 I-1）。反例：若待复核算终态 ⇒ `stage-close` 的命题"全部 key 已终态"为假（RQ-12 的恒真/假命题族），且 `_ensure_next_stage_gate:409-431` 会放行下一 stage，把"未复核"封进 closed stage ⇒ 事后打回必须回退已 closed 的 stage（D4/AC-028 事故）。
5. **依赖红线判据**：`_DEP_SATISFIED`（`conductor.py:56`）**不含** `pending-review`；机器判据 = 静态式 `"pending-review" not in _DEP_SATISFIED` + 行为式（k2 依赖 k1、k1 待复核 ⇒ 该 tick 无 `ap-k2-*` 派发行）+ 负对照（k1=done 必须有派发）。反证：若加入，则打回后依赖已解锁、下游可能已写盘（不可逆），且 `closed-legacy ∈ _DEP_SATISFIED` 已证这类解锁无撤销入口（`_consumed_gate_ids:297`）。
6. **触发时机**：判据 = 同 stage 内**除待复核 key 外的所有 key 都在终态集**（复用 `_stage_closure` 的终态谓词），位置 = `conductor.py:266-271` 的 stage 循环内、`_stage_closure` 调用之前；多个待复核 key 同 tick 批量复核（即 AC-027 要的"批量形态"）。**时间兜底不能取自 p50**：实测门→收口视界 n=11 / p50 24.48h / max 145.99h、单 stage 墙钟 n=4 / p50 36.56h / max 150.53h、仍在跑 ≥211h ⇒ 兜底 = 到点**升级给人**（U-9 的 B），**不是**到点自动裁决。
7. **合法重开**：待复核失败 ⇒ key-status 回 `running` + 新事件 `review-decided{outcome=rework}`；**stage 状态不变**（因为待复核挡住了收口，失败恰好发生在 stage 仍 `running` 时，所以根本不需要回退 stage）。conductor **永不允许** `closed → running`：`_set_stage_status:380-407` 加单调性 rank + 无 `reopen_of` 即拒绝并留痕。与 JC `gate-0008` 的差异见 F6.3 检测表（重放签名 = 同一 `gate-\d{4}` 出现第二次 `gate-answered`；合法签名 = `review-decided` + `reopen_of`）。
8. **补偿控制红线 2 条**（RQ-13 风险 24）：`closed-legacy` 与**源文件写/删**在延后窗口内**禁止**（前者唯一产生点 `conductor.py:2363-2420`，后者机器判定为零：`worker-mode.ts:761-790` 只拦 read-ish）。10 项动作清单 + 可检测信号 + 首个失败模式见 F7。
9. **VC 候选 12 条**（F8）：含 2 条负对照（prove-the-test-has-teeth），1 条跨语言 parity（P-021/AC-010），1 条 fail-closed 回归（未枚举值仍让 tick 跳过）。

## 决策问题

承接 AC-027 的 case 2 路径 (1)。本卡只回答**设计面**的 7 问：

1. 状态载体怎么选（≥2 方案 + pros/cons + 推荐），逐方案给写入点/读取点/两侧镜像面/已有消费者影响面。
2. 待复核如何参与 `_stage_closure`（终态？分母？），判据 + 反例。
3. 依赖解锁红线的机器判据 + 反证方式。
4. 触发式复核时机的判定口径与 `file:line`；时间兜底上限的实测依据。
5. 合法重开路径（显式/留痕/单调），与 D4/AC-028 的意外重开如何检测区分。
6. 延后窗口内禁止/允许的动作清单（可检测信号 + 首个失败模式）。
7. 每个关键断言的 VC 候选。

**不做**：不写实现代码、不改两侧镜像、不新增配置键的具体值（只给取值域与缺口）、不答任何 gate、不评估影子模式/白名单（属 D5）、不重写门命题（属 D1）。

## 调研方法与出处

### 只读代码基点（行号 = 本卡工作树快照）

| 面 | 位置 |
|---|---|
| key-status 枚举（Python，fail-closed） | `roadmap.py:63-68`（`KEY_STATUSES = ("running","done","stalled","closed-legacy")`） |
| key-status 解析（未知值 → `RoadmapError`） | `roadmap.py:336-361`（`:352` 判 enum）；`roadmap.py:269-274`（重复 `> key-status:` 行报错） |
| key-status 校验（只查 key 集覆盖，不查值） | `roadmap.py:409-422` |
| key-status 写帮手（enum 检查 + 单行重写） | `roadmap.py:505-530` |
| 独立校验 CLI（**未被 conductor 调用**，AC-031） | `roadmap_check.py:43-57` |
| roadmap 不可读 ⇒ 整 tick 跳过 | `conductor.py:210-212` |
| tick 期 `status_of` 构建（唯一来源） | `conductor.py:225-232` |
| 派发跳过集（**字面量元组**） | `conductor.py:274` |
| 依赖解锁集 | `_DEP_SATISFIED:56` → `_deps_satisfied:2153-2154` |
| stage 收口终态集 | `_stage_closure:616-656`，终态 `629-631`，已开门 return `633-634` |
| stage 激活 / 下一 stage 门 | `_stage_activation:434-451`、`_activate_pending_stage:454-486`、`_ensure_next_stage_gate:409-431` |
| 已答门消费（stage-confirm/stage-close） | `_consume_answered_gates:316-378`（`:353-358` / `:359-378`） |
| 消费记录（timeline 反推，2 代保留） | `_consumed_gate_ids:297-315`；`timeline.py:93-94` |
| stage 状态写（**无单调性**） | `_set_stage_status:380-407` |
| key-status 的 4 个写点 | `_mark_key_done:2240-2271`（`done`）、`_apply_stalled_approvals:2295-2361`（`running`）、`_apply_stalled_rejections:2363-2420`（`closed-legacy`）、`mark_stalled:3944-3994`（`stalled`） |
| stalled 消费的 key-status 前置 | `:2332`（approved）、`:2376`（rejected） |
| xkey 的 owner 终态判定 | `:2622`（`status_of.get(owner_key) not in _DEP_SATISFIED`） |
| roadmap-writer（整文件重写 `_roadmap.md`） | `_dispatch_roadmap_writer:520-560`（两次提案用尽 `:545-546`）、`_roadmap_writer_prompt:562-612`（键格式说明 `:601`） |
| 占槽谓词（与 key-status 无关） | `_is_in_flight:2131-2132`（`mw_common._TERMINAL_STATUSES = {done,failed,needs-clarification}`，`mw_common.py:158`）、`_row_belongs_to:2135-2139` |
| 锁 | `lock_file:116-118` = `.mw/{name}.lock`（roadmap 写全程 `_set_stage_status:397`/`_mark_key_done:2264`/stall 路径同款） |
| 时间线事件词表（过滤器，**非拒绝集**） | `timeline.py:66-85`（17 类） |
| gate schema（12 字段，无 timeout/deadline） | `gates.py:54-61`（kinds）、`:63`（statuses）、`:68-81`（fields）、`:345-348`（未知字段 → `GateFormatError`） |
| TS view 侧枚举 + 宽松解析 | `status-model.ts:322`（`KEY_STATUSES`）、`:521-541`（未知值 ⇒ warning，不丢） |
| TS `/autopilot status` 读点 | `status-model.ts:1136-1138`（`state`）、`renderStatusText:1183` |
| TS 面板读点 | `monitor.ts:472-476`（`statusByKey`）、`:502`（status）、`:505`（**依赖终态字面量镜像**）、`:597`（计数）、`:603-624`（attention） |
| TS `/autopilot roadmap` 渲染 | `console.ts:488` |
| 面板 gate 结构（无 age） | `monitor.ts:89-96` |
| worker 写面拦截（**只拦 read**） | `worker-mode.ts:761-790`（非 read/ls/find/grep 一律 `return undefined`） |
| 工具白名单注入点 | `worker-mode.ts:52-84`（`TOOL_ALLOWLISTS`）、`:92-103`（`toolsForType`/`activeToolsForType`）、`:748-753`（`before_agent_start` 只设一次） |
| `_index.parallel` 相位（**与 key-status 独立的另一平面**） | `state.py:133-142`（`phase`） |

### 只读命令（逐条）

```text
read  packages/multi-workers/autopilot/roadmap.py            (全量)
read  packages/multi-workers/autopilot/conductor.py          40-120 / 180-480 / 612-672 / 900-1020 / 2145-2420 / 2600-2670 / 3940-4000 / 4070-4130
read  packages/multi-workers/autopilot/gates.py              48-98
read  packages/multi-workers/autopilot/timeline.py           60-105
read  packages/multi-workers/mw_common.py                    150-165 / 1432-1445 / 2022-2065
read  packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts   300-420 / 550-640 / 1090-1210
read  packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts        85-110 / 463-560 / 585-645
read  packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts        440-500
read  packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts       52-105 / 742-792
grep  key_status|keyStatus|status_of|statusByKey|KEY_STATUSES|closed-legacy|_DEP_SATISFIED
      over packages/multi-workers/** 与 packages/coding-agent/src/**（排除 test_*/*.test.ts/dist/node_modules）
grep  readRoadmap|parseRoadmapText|load_roadmap|roadmap\.   （找间接读者）
grep  _doctor_autopilot|deriveAutopilotPanel                  （确认 doctor/面板的读点归属）
```

**负结论的范围声明（AC-001 要求的反证式声明）**：本卡的"无消费者"结论只覆盖 `packages/multi-workers/**`（`autopilot/*.py`、`mw.py`、`mw_common.py`、`launcher.py`）与 `packages/coding-agent/src/extensions/agent-team-loop/**`（`autopilot/*.ts`、`pm/*.ts`、`worker/*.ts`、`shared/*.ts`）两个根；排除了 `test_*`/`*.test.ts`、`dist/`、`node_modules/`、`.agenticdoc/`（历史留档）与 `xkey.py`（其 `XKEY_STATUSES:72` 是 ticket 状态，与 key-status 无关）。**未覆盖**外部项目（FM/E2/JC）里可能存在的自定义脚本（本卡未扫描它们的非框架文件）；这也是一条数据缺口。

### 数据来源

本卡**未新增任何实测**。所有量级数字（24.48h / 36.56h / 150.53h / 145.99h / 211.0h / 203.93h / 1139 tool / 239 write-edit / 49 targets）全部引自 RQ-13 F2/F3 与其 `[VERIFY]` 行，样本量与口径随引（n 写死，不跨用 p50 外推）。

## 发现

### F1 现有消费者穷举（key-status / `status_of` 的全部读点）

#### F1.1 生产代码一览（27 个读点/enum 点 + 6 个写点）

| # | 侧 | 读点 `file:line` | 读什么 | 待复核若不处理会怎样 |
|---|---|---|---|---|
| P1 | Python | `roadmap.py:63-68` | `KEY_STATUSES` 枚举（解析期） | 新值未入枚举 ⇒ `roadmap.py:352` 抛 `RoadmapError` ⇒ `conductor.py:210-212` **整 tick 跳过**（fail-closed，响亮） |
| P2 | Python | `roadmap.py:336-361` | `_parse_key_status`（每 tick 解析 roadmap 时） | 同上 |
| P3 | Python | `roadmap.py:409-422` | `validate_roadmap` 的 key **集**覆盖（不查值） | 无影响（值层面无校验）——**这是缺陷**：`update_key_status` 之外没有值校验的第二道闸 |
| P4 | Python | `roadmap.py:505-530` | `update_key_status` 写帮手（enum 检查） | 新值未入枚举 ⇒ `RoadmapError`（写路径 fail-closed） |
| P5 | Python | `roadmap.py:269-274` | 重复 `> key-status:` 行检测 | 无影响 |
| P6 | Python | `conductor.py:225-232` | **构建 tick 期唯一的 `status_of`** | 新状态原样进入所有下游判据（必须先定好下游语义） |
| P7 | Python | `conductor.py:274` | 派发跳过集 `("done","stalled","closed-legacy")` | **待复核 key 被继续派发**（烧 token + 写源文件）— 本 key 头号事故 |
| P8 | Python | `conductor.py:285` → `_deps_satisfied:2153-2154` → `_DEP_SATISFIED:56` | 依赖解锁 | **待复核被当成 done 的变体**（解锁依赖）— 红线 |
| P9 | Python | `conductor.py:271` → `_stage_closure:629-631` | stage 收口终态集（分母 = `stage.keys` 全部） | 若把待复核算终态 ⇒ 未复核工作被收进 closed stage |
| P10 | Python | `conductor.py:2332` | `_apply_stalled_approvals` 前置 `status_of.get(key) != "stalled"` | 待复核 key 的**已在案 stalled 门**被答后会把它 resume（语义错位） |
| P11 | Python | `conductor.py:2376` | `_apply_stalled_rejections` 前置同上 | 同上，且 reject 路径会产出 `closed-legacy`（红线） |
| P12 | Python | `conductor.py:2622` | xkey 聚合的 owner 终态判定（`_DEP_SATISFIED`） | 与 P8 同源；owner 待复核 ⇒ 不发 ticket（若误算终态则反向） |
| P13 | Python | `conductor.py:2256` | `_mark_key_done` 幂等守卫 `stage.key_status.get(key) == "done"` | 无影响（只挡重复写 done） |
| P14 | Python | `conductor.py:3958` | `mark_stalled` 幂等守卫 `== "stalled"` | 待复核 key 若被 stall 会把状态覆盖成 `stalled`（丢失"待复核"） |
| P15 | Python | `conductor.py:3909` | `_xkey_apply_stage` 形参 `status_of`（`del status_of`，只保留挂载签名） | 无影响 |
| P16 | Python | `roadmap_check.py:43-57` | 独立校验器（`load_roadmap` + `validate_roadmap`） | 新值未入枚举 ⇒ 校验器报 parse error（**独立的第二道 fail-closed**） |
| P17 | Python | `conductor.py:601`（`_roadmap_writer_prompt`） | 提示里给出的键格式 `<key>=<running\|done\|stalled\|closed-legacy>` | 词表漂移：roadmap-writer LLM 可能写出未枚举值（且 `validate_roadmap` 未被 conductor 调用，AC-031） |
| P18 | TS | `status-model.ts:322` | `KEY_STATUSES`（view 枚举） | 新值未入 ⇒ `:533` 只发 warning，值仍原样进 `keyStatus`（宽松，不会崩） |
| P19 | TS | `status-model.ts:521-541` | `parseRoadmapText` 的 key-status 解析 | 同 P18 |
| P20 | TS | `status-model.ts:1136-1138` | `deriveStatusModel` → `state`（缺省 `running`） | `/autopilot status` 显示新值原文；若未枚举则 warning 噪音 |
| P21 | TS | `status-model.ts:1183` | `renderStatusText` 渲染 `state` | 纯显示 |
| P22 | TS | `monitor.ts:472-476` | `statusByKey` | 新值原样进入面板 |
| P23 | TS | `monitor.ts:502` | `status: statusByKey.get(key) ?? "unknown"` | 面板显示原文（若 enum 未扩，无 warning 通道） |
| P24 | TS | `monitor.ts:505` | `blockedBy`：硬编码 `!["done","closed-legacy"].includes(...)` | **依赖判定的 TS 镜像**（与 `_DEP_SATISFIED` 是两份独立字面量 ⇒ P-021 漂移面） |
| P25 | TS | `monitor.ts:597` | `keys N (running …, stalled …, done …)` 计数 | **待复核在这个计数里消失**（既不 stalled 也不 done）⇒ 面板上"看起来没毛病"（与 RQ-8 `budget-exhausted` 同型风险 13） |
| P26 | TS | `monitor.ts:603-624` | attention 过滤 `k.status === "stalled"` + stalled 门提示 | 待复核 key **不进 attention**、不给恢复提示 ⇒ 夜间无人看见 |
| P27 | TS | `console.ts:488` | `/autopilot roadmap` 渲染 `key=status` | 纯显示（唯一"免费可见"的读点） |
| W1 | Python | `conductor.py:2259` | 写 `done` | 合法重开的出口之一 |
| W2 | Python | `conductor.py:2340` | 写 `running`（stalled approve） | 复核 `resume` 的复用点 |
| W3 | Python | `conductor.py:2381` | 写 `closed-legacy`（stalled reject） | **红线动作，复核路径不得触达** |
| W4 | Python | `conductor.py:3961` | 写 `stalled` | 复核 `escalate` 的复用点 |
| W5（外部） | Python/LLM | `conductor.py:520-560` roadmap-writer 整文件重写 `_roadmap.md` | 可写出任意 key-status 值（只受提示与 `validate_roadmap` 约束，而后者的值校验在 `roadmap.py:352` 的 parse 里） | 新值词表漂移 / 丢行 |
| W6（人工） | — | 人手工编辑 `_roadmap.md`（AC-028 JC 实例） | 任意 | 无事件留痕（需检测器） |

#### F1.2 面板/doctor 的读点归属（RQ-8 的"doctor 零 gate 内容"复核）

- **面板**：`deriveAutopilotPanel`（`monitor.ts:463-524`）读 `_roadmap.md`（`:471`）+ `_index.parallel` 相位（`:487`）+ timeline beat（`:489-495`）。⇒ key-status 的**唯一面板读点**就是 P22-P26。
- **`/autopilot status`**：P20/P21（`deriveStatusModel`）。
- **`/autopilot roadmap`**：P27。
- **`mw doctor`**：`_doctor_autopilot`（`mw_common.py:2022-2065`）只读 `config.json` 的 effective values + `xkey_verify_*`；`_doctor_issues:2067+` 不检查 gate/key-status 陈旧度。⇒ **doctor 零读点**（已复核，与 RQ-8 F6 一致）。
- **`advance_phase.py`（AgenticTask 框架）**：`advance.py:170-191` 只以 `(key, phase, project_root, summary)` 调子进程；相位真相在 `_index.parallel`（`state.py:133-142`），**不读 `_roadmap.md`**。⇒ 零读点。

#### F1.3 负结论（反证式）

- "doctor 不读 key-status"：读过 `mw_common.py:2022-2065` 全文与 `:2067-2190`（issues 汇总）两处，除 `xkey_*` 与 `config` 外无 roadmap/gate 访问；`grep key_status|key-status` 在 `mw.py`/`mw_common.py` **零命中**。
- "`advance_phase.py` 不读 key-status"：`advance.py` 全文 + `state.py:133-152`；`grep key_status` 在整个 `packages/multi-workers/**` 只命中 `roadmap.py` / `conductor.py` / `roadmap_check.py`。
- "`xkey.py` 不读 key-status"：`xkey.py:72` 的 `XKEY_STATUSES` 是 ticket 生命周期（`detected/ticketed/pending-auth/approved/…`），与 key-status 无交集；`conductor.py:3909` 显式 `del status_of`。

### F2 状态载体选型

#### 方案对比

| 维度 | **A. 新 key-status 值 `pending-review`（key-status 行）** | **B. 旁挂文件**（如 `.agenticdoc/<key>/.review-pending.json` 或 `.agenticdoc/_autopilot/deferred/<key>.json`） | **C. 复用 `stalled` + 标记位**（`stalled` + 旁挂 `review_pending=true`，或专用 self-loop gate） |
|---|---|---|---|
| 写入点 | `roadmap.update_key_status`（`roadmap.py:505`）+ 新增 conductor 调用点（建议 `mark_stalled` 的兄弟函数，紧邻 `conductor.py:3944-3994` 的锁+重写范式）；enum 扩 `roadmap.py:63-68` | 新 writer（无先例：`.mw/` 只放锁与 PID，`conductor.py:63-69`/`:116-119`；`_roadmap.md` 是 roadmap-writer 唯一写目标 `:550-556`）⇒ 新共享写面（GC-3 成本） | 不动 key-status；`mark_stalled` 后追加标记（旁挂或 gate `note`） |
| 写入原子性 | ✅ 复用 `.mw/roadmap.lock`（`conductor.py:116-118`、写路径 `:2264`） | ❌ 需自造锁/原子写 | ✅ 复用（状态行）+ ❌ 标记位仍需第二写面 |
| 读取点 | 27 个现存读点**全部自动生效**（值原样流过）⇒ 必须逐个定语义（F1.1 表） | 0 个现存读点自动生效 ⇒ 读点**全部需要新增 join**，否则状态不可见 | `stalled` 的读点全部生效（P7 已跳过、P9 已挡收口、P8 已不解锁）——看似省事 |
| 两侧镜像面 | Python：`roadmap.py:63-68`（enum）+ `conductor.py:274`（跳过集）+ `:601`（提示词表）；TS：`status-model.ts:322`（enum）+ `monitor.ts:597`（计数）+ `:603-624`（attention）；`console.ts:488` 原文可见。**不得改**：`_DEP_SATISFIED:56`、`_stage_closure:629-631`、`monitor.ts:505` | 5 处 TS 读点全需新增 join；`status-model.ts` 无 spot | `status-model.ts:564`/`monitor.ts:786`（`advanceStallTicks` 域的 `stalled` 常量）无关；但面板会把它当 stalled 渲染（误提示"resume grants one round"，`monitor.ts:618-624`） |
| 失败语义 | 未同步的任一侧：Python **fail-closed 整 tick 跳过**（响）；TS 只 warning（静默） | 静默：状态写在旁边，主平面照旧 ⇒ **"待复核被当成 running/done"** | 静默：`stalled` 语义被顶替，人答一个"resume"就把待复核 key 放回派发 |
| pros | 单一真相面；免费可观测（面板/console/status 全显示）；与 `_index.parallel` 相位平面解耦；GC-3 零新写面；P-021 parity 面清晰（就一个 enum） | 不动 enum ⇒ 无 fail-closed 迁移风险；载荷字段自由（deadline、证据 sha、批量清单） | 零枚举改动；"非终态/挡收口/不解锁"三条语义**已实测**存在 |
| cons | enum 是**跨语言 fail-closed 契约**：两侧必须同步上线（P-021），否则混跑会整 tick 跳过 | **无法单独承载状态**（key-status 仍须取旧四值之一 ⇒ 与主平面可矛盾）；读点需 join；无锁先例；新写面 | 语义不可分：`stalled` 今天 == "人已带外修复 + 可 resume 一轮"（`_resume_credits:2273-2294`、gate 文案 `:3973`）；且不回答 F3 的收口语义 |
| 推荐 | ✅ **状态用 A** | 仅作**载荷容器**（证据快照/deadline/决定记录），**任何决策都不得读它** | ❌ 不采用 |

#### 推荐形态（A + 最小旁挂）

- **状态**：`> key-status: <key>=pending-review`（新增第 5 个枚举值）。语义三条钉死：**非终态**（不过收口）、**不解锁依赖**（不进 `_DEP_SATISFIED`）、**不派发**（进 `conductor.py:274` 跳过集）。
- **载荷**（可选、非决策输入）：`<key>.review-pending.json`（或 `.agenticdoc/_autopilot/reviews/<key>.json`），含 `deferred_at` / `gate_kind`（`stalled`|`budget-exhausted`）/ `deadline` / `evidence_snapshot{path→sha256,mtime}` / `trigger`（`stage-others-terminal`|`deadline`）。写入点与状态写入**同锁同时刻**；读取只由复核材料渲染（RQ-14 的形态）使用。
- **枚举的两侧改动清单**（P-021，必须同 wave）：
  - Python：`roadmap.py:63-68`（枚举）、`conductor.py:274`（跳过集）、`conductor.py:601`（提示词表）。
  - TS：`status-model.ts:322`（枚举）、`monitor.ts:597`（计数加 `pending-review`）、`monitor.ts:603-624`（attention 条件加 `pending-review`）、`console.ts`（无改动，自动显示）。
  - **不得改动**：`_DEP_SATISFIED:56`、`_stage_closure:629-631`。`monitor.ts:505` 也不用改（它只是 `_DEP_SATISFIED` 的镜像，本就排除一切非 done/closed-legacy）。
- **迁移风险（必须显式处理）**：任何时刻磁盘上出现 `pending-review` 而某一侧未升级 ⇒ Python 侧 `roadmap.py:352` 抛错 ⇒ `conductor.py:210-212` 跳过整 tick（**fail-closed，不静默**，是特性不是缺陷）；TS 侧仅 warning（P18）但面板会显示原文。⇒ **两侧同 wave 是硬约束**（与 AC-010 同一条）。

### F3 stage 收口语义

#### 判据（推荐）

`_stage_closure` 的终态集**不变**：`terminal = ("done","closed-legacy")`（`conductor.py:629-631`），分母仍是 `stage.keys` 全部 key。**待复核算非终态**，因此：

```text
stage 收口 ⟺ ∀k ∈ stage.keys: status_of[k] ∈ {done, closed-legacy}
待复核存在 ⇒ 该 stage 永不收口 ⇒ 必须在收口之前触发复核（前置，不是替代）
```

- **位置**：`conductor.py:266-271` 的 `for stage in rm.stages:` 循环内、`_stage_closure(...)` 调用（`:271`）**之前**，紧跟在同一 `status_of` 视图上（该视图已在 `:235/:238` 吸收本 tick 的 stalled approve/reject）。
- **触发式判据**（F5.1）在收口前置执行；复核结论落盘后**同一 tick** 的 `_stage_closure` 立刻看到新状态：
  - 结论 `resume` ⇒ key-status → `running` ⇒ 仍非终态 ⇒ 不收口（正确：有待办）；
  - 结论 `escalate` ⇒ key-status → `stalled` ⇒ 仍非终态 ⇒ 不收口（正确：等人）；
  - **没有任何复核结论直接把 key 变成 `done`**：`done` 只经既有 `_mark_key_done`（`:2240`，要求 done credentials）由相位机驱动 ⇒ 复核不会成为"绕过凭证的终态入口"（这是防伪/AC-030 需要的性质，也避免"复核 = 自动盖章"）；
  - 任何**不得**出现 `closed-legacy`（红线，见 F4/F7）。

#### 反例（为什么不能算终态）

1. **命题失真**：`stage-close` 的问题文案是"全部 key 已终态"（`conductor.py:650-656`）。若待复核算终态，则该命题为真但**语义为假**（有人还没复核），落入 RQ-12 风险 26 的"命题恒真/无信息量"族 ⇒ 门变成自动盖章。
2. **封存未复核工作**：`stage-close` approved ⇒ `_set_stage_status(closed)` + `_ensure_next_stage_gate(stage+1)`（`:359-373`、`:409-431`）⇒ 下一 stage 的 `stage-confirm` 门立刻可放行（IA-7，RQ-13 F2）。此时若复核打回，就必须把**已 closed 的 stage 回退**——正是 D4/AC-028 的 JC `gate-0008` 事故形状（`closed → running`），且 `_set_stage_status:380-407` 今天没有单调性检查。
3. **全待复核 stage 的极端例**：一个 stage 的 3 个 key 全 `pending-review`。若算终态 ⇒ `stage-close` 门会被建并（若 `stage-close` 在自动白名单里，AC-016/RQ-10）被自动过 ⇒ **零人工、零复核**地 close 一个完全未经审的 stage；这与"待复核 = 非阻塞但必须有人看"的决策正面冲突。⇒ **全待复核的 stage 不得建 stage-close 门**；它应当建的是**批量复核材料**（RQ-14 的形态），复核完成后再自然进入收口。

#### "算多数的分母"？

不建议引入"多数"概念。`_stage_closure` 的 `any(... not in terminal)` 已经是全称量词，任何"多数终态即可收口"的 weakening 都会在 stage 内留下未终态 key（今天已有 `stalled` 挡收口的先例，`conductor.py:623-624` 注释）。⇒ 分母 = `stage.keys` 全体，无语义特例。

### F4 依赖解锁红线（机器判据 + 反证）

#### 红线

`_DEP_SATISFIED = frozenset({"done","closed-legacy"})`（`conductor.py:56`）**不含** `pending-review`。两个消费点自动继承：`_deps_satisfied:2153-2154`（派发准入 `:285`）与 `_xkey_aggregate:2622`（owner 终态）。TS 镜像 `monitor.ts:505` 同样是 `["done","closed-legacy"]`，**无需改动**（它本就排除其他值）——但要在测试里显式断言它以锁住 parity。

#### 机器可判的判据（三层 + 负对照）

| 层 | 判据 | 通过条件 |
|---|---|---|
| 静态 | `"pending-review" not in conductor._DEP_SATISFIED` | 恒真 |
| 行为 | fixture：stage 1 两个 key `k1`/`k2`，`k2.depends_on=[k1]`；`k1=pending-review`；跑一 tick ⇒ 断言 ①`_deps_satisfied(("k1",), status_of) is False` ②`_workers.parallel` 无 `ap-k2-*` 行 ③无 `dispatch` timeline 事件含 `k2` | 三条全真 |
| 镜像 | 同 fixture 下 `deriveAutopilotPanel(...).keys` 中 `k2.blockedBy` 含 `"k1"`（`monitor.ts:505`） | 恒真 |
| 负对照 | 同 fixture 把 `k1` 换 `done` ⇒ 必须有 `ap-k2-*` 派发行（否则测试无牙） | 必须有派发 |

#### 反证方式（把待复核加进 `_DEP_SATISFIED` 会怎样）

1. **解锁先于判决**：`_deps_satisfied` 在同一个 tick 的 `:285` 立刻放行下游 key 的派发。下游 worker 会写源文件（RQ-13 IA-1；实测 E2 gate-0014 窗口内 239 次 write/edit、80 次在 `.agenticdoc` 外）⇒ 若复核随后打回，下游已基于未复核结论落盘。
2. **不可撤销**：`closed-legacy ∈ _DEP_SATISFIED` 已是既有反例——它像 done 一样解锁（RQ-13 F2 IA-5），而 `_consumed_gate_ids:297-315` 只做去重、全仓无撤销入口，回滚只能手改 `_roadmap.md` 且不留事件（spec 风险 15）。把 `pending-review` 加进去是**严格更坏**：`closed-legacy` 至少是"已裁决（放弃）"，而待复核是"尚未裁决"。
3. **stage 收口连锁**：解锁依赖对 stage 收口没有直接影响（`:629-631` 读 key-status），但**若同时**把待复核加进终态集（F3 反例），则"解锁 + 放行收口 + 开下一 stage"三件事同 tick 发生 ⇒ 单个错误值引发 IA-5+IA-7 的复合放行。
4. **可检测**：加进去后行为式判据第 ① 条立即变红；负对照仍绿 ⇒ 测试能定位到具体集合而不是"某处行为变了"。

### F5 触发式复核时机 + 时间兜底

#### F5.1 "stage 内其它 key 全部终态"的判定

```text
输入: stage.status == "running"; status_of（conductor.py:225-232 的 tick 视图，已吸收 stalled approve/reject）
候选集 C = {k ∈ stage.keys : status_of[k] == "pending-review"}
触发 ⟺ C ≠ ∅ 且 ∀o ∈ stage.keys \ C : status_of[o] ∈ {"done","closed-legacy"}
       且 ∀k ∈ C : 无 in-flight 行（_is_in_flight:2131 ∧ _row_belongs_to:2135 对 k 为真者为 0）
```

- **口径说明**：判据用的终态集**刻意与 `_stage_closure:629-631` 相同**——这样"触发"与"能收口"只差待复核这一项，不需要第二套终态定义（避免 P-021 家族漂移）。
- **位置**：`conductor.py:266-271` 的 `for stage in rm.stages:` 循环内、`_stage_closure(...)`（`:271`）之前；结论在同一 tick 落盘后 `_stage_closure` 立即看到。
- **批量**：多个待复核 key 同 tick 一起复核（`C` 即批量清单），正是 AC-027 要的"复核材料的批量形态"。材料形态归 RQ-14/D6。
- **不做**："无其它可派发工作"的更宽判据（例如把"无 in-flight 且无 pending 门"也算 quiet）暂不引入：它会把 `budget-exhausted` 的静默冻结（RQ-8 风险 13）也卷进来，语义面变大；本卡只给最小判据。
- **边界**：如果 stage 内另一个 key 是 `running` 但本 tick 无 in-flight 行（轮次间隙），触发**不**发生（正确：还有活要派）。

#### F5.2 时间兜底（上限取值与实测依据）

| 依据 | 值（RQ-13 F3，样本量随引） |
|---|---|
| 单 stage 墙钟（已收口） | n=4；min 23.49h，**p50 36.56h**，**max 150.53h**（JC stage 1，6.27d） |
| 门创建 → 所在 stage 收口（延后视界） | n=11（FM 6 / E2 3 / JC 2）；min 2.58h，**p50 24.48h**，**max 145.99h**（6.08d） |
| 仍在跑的 stage（快照下限） | FM ≥25.15h、E2 ≥48.32h、JC ≥211.0h（8.8d） |
| 当前最长 pending 门 | JC `gate-0007`（stage-close）**203.93h（8.5d）** |

**取值**：

- 主路径 = 触发式（F5.1）——它把复核放在"最后一个其它 key 终态"的时刻，实测分布的中位落在 24.48h 量级，但**上尾不可外推**。
- 兜底 `deadline = deferred_at + T`，`T` 的取值域与推荐：
  - `T=24h`（≈ p50 24.48h）：只兜住一半样本；仅在"触发式为主、Deadline 只是异常网"时可用，且**必须**同时有 age 告警（否则最坏情况仍可挂 145h+）。
  - `T=48h`（≈2×p50，仍 < max 150.53h）：**推荐默认值**。理由：覆盖 p50 的 2 倍裕度，能兜住 FM/E2 的绝大多数（FM p50 24.50h / max 43.66h；E2 p50 16.43h / max 18.18h——见 RQ-13 F3.3 的分项），且不把 JC 类长尾当成常态。
  - `T≥150.53h`（实测 max）等价于"没有兜底"，**不得**作为默认。
- **到点动作 = 升级给人，不自动裁决**（U-9 决策 B；RQ-13 CC-4/CC-5）：写 `review-escalated` 事件 + 面板/doctor age 告警 + key 保持 `pending-review`（不写 `done`、不写 `closed-legacy`）。理由：兜底一旦自动裁决，`closed-legacy` 就会在无人值守时被批量产出（红线），或把未复核工作判成 done（风险 21 的"隐性欠债"变"虚假完成"）。
- **配置面缺口**：若把 `T` 做成新 int 配置键，会撞"机器层 int 空值即未决定无哨兵"的语义缺口（AC-010 / spec 风险 5）⇒ 必须落到**项目层 `config.json` 且显式材料化**（同 FM/E2 现有 13 键的做法），否则是静默空操作。备选（零新键）：由既有 `advance_stall_ticks × poll_interval_sec` 推导——但默认值（20×5s=100s）量级完全不符，**不可用**；本卡不推荐为省一个键而扭曲语义。

### F6 合法重开路径

#### F6.1 设计（显式、留痕、单调）

| 环节 | 设计 | 锚点 |
|---|---|---|
| 进入待复核 | 一个可延后门（`stalled` / `budget-exhausted`）本该被创建时，改为写 `pending-review` + 载荷 + `review-deferred` 事件（**不建门**，或建门则门只作材料锚点，其 pending 不驱动任何裁决） | 复用 `mark_stalled:3944-3994` 的锁+重写真范式；`_advance_key:981-1003` 的 `budget-exhausted` 分支为另一入口（今天它连 key-status 都不写 ⇒ 顺带修掉风险 13） |
| 复核结论（三态，机器可判，**无 `closed-legacy`**） | `resume`（通过：批准继续，等价今天的 stalled approve，+1 轮）/ `rework`（打回：要求补证或重做，+1 轮并把缺口写进下一轮）/ `escalate`（无法机器裁决 / 需要放弃 / 到点兜底 ⇒ 转 `stalled` 给人）；**无 `done` 出口** | 新事件 `review-decided`：`key` / `stage` / `outcome` / `reopen_of`（仅 `resume`/`rework` 时指向被重开的延后记录 id，供"显式重开"检测）/ `detail=f"{ref} reviewed → {outcome}"` / 结构化 `decided_by`（AC-030：不得依赖应答者可写的 `answered_by` 散文） |
| `resume` | key-status `pending-review → running`；复用 `_resume_credits` 语义（一轮/每个封顶 loop） | 落点同 `_apply_stalled_approvals:2340` |
| `rework`（= 打回/重开） | key-status `pending-review → running`；同样 +1 轮，并把复核缺口注入下一轮 prompt；**stage 状态不变** | 同上 |
| `escalate` | key-status `pending-review → stalled`；建 `stalled` 门（人答） | 落点同 `mark_stalled:3961` + `_create_gate` |
| **禁止** | `rejected → closed-legacy` 由复核自动产生；`closed` stage 回退 | `_apply_stalled_rejections:2363-2420` 是唯一产生点，复核路径**不得**调用 |
| 单调性 | `_set_stage_status:380-407` 加 rank 表：`pending(0) < approved(1) < running(2) < closed/closed-human(3)`；`halted` 为侧态（只允许人工经 roadmap 编辑离开）。`rank(new) < rank(cur)` ⇒ **拒绝写** + 追加 `stage-reopen-refused` 事件 + 返回 False（保持"未变更即 False"的既有契约） | `_set_stage_status:380-407` 唯一写点；调用点仅 `:353/:359/:371`（stage-confirm / stage-close） |
| 人类重开 | 允许，但**必须**是显式的人工操作：手改 `_roadmap.md`（今天唯一的回退路径）或后续经 roadmap-writer 提案；两者都必须留下可检测信号（F6.3），且**不得**经 conductor 自动完成 | `_dispatch_roadmap_writer:520-560`（唯一整文件写者）、`_roadmap_writer_prompt:562-612` |

**关键结构性结论**：因为待复核**挡住收口**（F3），复核失败时 stage 仍处于 `running` ⇒ **合法重开永远不需要回退 stage 状态**。这把"重开"问题从"stage 状态机单调性"降级为"key-status 的一步转换"，是路径 (1) 相对 AC-027 路径 (c) 的最大好处。

**窗口不存在性断言**：`stage-close` 门只在收口条件满足时创建（`_stage_closure:633-656`），而待复核使其不满足 ⇒ **不存在"stage-close 门已 pending 而 stage 内仍有 pending-review key"的窗口**。因此不需要 gate 撤回机制（避免扩 gate 状态枚举 `gates.py:63`）。这一条要写成 VC（F8 VC-D2-06）。

#### F6.2 是否允许回退已 `closed` 的 stage？

**不允许由 conductor 执行。** 理由链：

1. `closed` 是阶段串行的护栏（`_stage_activation:434-451` 只认 `running`；pending stage 必须排在 closed 之后，`:454-486`）；
2. 回退会让 next-stage 的 `stage-confirm` 门与已放行的 key 并存 ⇒ 同一 stage 图两处 `running`（JC 现状实测：stage 1 与 stage 2 同时 `running`，RQ-13 F5）；
3. 回退是不可逆动作的触发器（IA-6/IA-7），且 `closed-legacy`/done 的成果不可撤销。

⇒ 只允许**人工**显式回退（手改或 roadmap-writer），并要求机器把它检测出来（F6.3）。

#### F6.3 与 JC `gate-0008` 意外重开的检测差异

| 维度 | JC 意外重开（RQ-13 F5） | 本设计的合法重开 |
|---|---|---|
| 触发 | `gate-0001`（09-11 已答）在 2026-09-26T04:37 **第二次** `gate-answered` | `review-decided{outcome=resume\|rework}` |
| 直接原因 | `_consumed_gate_ids:297-315` 从 timeline 反推，而 timeline 只留 2 代（`timeline.py:93-94`）⇒ 旧 id 从消费集合消失 | 显式复核结论 |
| stage 状态 | `closed → running`（回退） | **不变**（仍 `running`） |
| 副作用 | 立刻生成新 `stage-close` 门 `gate-0008`（`_ensure_next_stage_gate`） | 无新 stage 门；只写 key-status + 决定记录 |
| 检测规则（机器可判） | ① 同一 `gate-\d{4}` 在 `gate-answered` 出现 ≥2 次；② 任一 stage status `closed\|closed-human → running` 且同 tick 无 `reopen_of` 记录；③ stage status 写入无对应 `gate-answered`/`review-decided` | ① 有 `review-decided`（含 `reopen_of` 引用）且 outcome ∈ {resume,rework,escalate}；② key-status 一步转换，无 stage 转换 |
| 违规判定 | 出现 ①/②/③ 任一 ⇒ 违规事件（`stage-reopen-refused` 或新的 `stage-status-unexpected`） | 无 |

⇒ `_set_stage_status` 的单调性 guard（F6.1）+ 消费记录持久化（AC-028/CC-7）是**双重防线**：前者让重放从"静默生效"变"显式拒绝"，后者让重放不再发生。

### F7 延后窗口内的动作清单（补偿控制）

窗口定义：**per key**，从 `review-deferred` 到 `review-decided`（或 `review-escalated`）。红线 = RQ-13 风险 24 的两类：`closed-legacy` 与源文件写/删。

| # | 动作 | 窗口内 | 实现面 `file:line` | 可检测信号（机器可判） | 首个失败模式 |
|---|---|---|---|---|---|
| AC-1 | 该 key 的 worker 派发 | **禁止** | 落点 = `conductor.py:274` 跳过集加 `pending-review`；准入链 `:285-290` | 无 `ap-{key}-*` 非终态行（`_is_in_flight:2131` ∧ `_row_belongs_to:2135`）；无含该 key 的 `dispatch` 事件 | key 在"已宣布完成"后继续烧 token 并写盘 ⇒ 与其它 key 同文件双写（P-018/P-019） |
| AC-2 | 该 key worker 的源文件写/删 | **禁止** | 机器强制今天不存在：`worker-mode.ts:761-790` 只拦 read-ish；可选杠杆 `activeToolsForType:101` + `TOOL_ALLOWLISTS:52-84` | 部分可得：`trace.log` 的 `[TOOL] write\|edit\|bash <target>`（RQ-13 F2 的窗口计数法）；不可得：`bash` 内的真实写面 | "顺手修一下"改掉他 key 文件而无人知（实测：E2 gate-0014 窗口 49 个目标 / 80 次在 `.agenticdoc` 外） |
| AC-3 | 产出 `closed-legacy` | **禁止（自动）** | 唯一产生点 `_apply_stalled_rejections:2363-2420`（复核路径不得触达）；写入 `roadmap.update_key_status(..., "closed-legacy")` `:2381` | 无 `gate-answered` detail 含 `"rejected → {key} closed-legacy"`（`:2388`）；roadmap 该 key 无 `closed-legacy` | 批量复核 reject 未修复 key ⇒ 伪完成 + **解锁依赖**（`_DEP_SATISFIED:56`）+ 放行 stage 收口（不可撤销） |
| AC-4 | stage 收口 / 下一 stage 激活 | **禁止** | `_stage_closure:629-631`（待复核非终态即天然禁止）；`_ensure_next_stage_gate:409-431` | 窗口内该 stage 无 `stage-close` 门（`_gate_open(kind="stage-close")` 为假）；无 `stage-close` timeline 事件 | 未复核工作被封进 closed stage ⇒ 打回必须回退 closed stage（D4 形状） |
| AC-5 | 同 stage 其它 key 继续工作 | **允许**（这是设计目的） | 既有派发链 `:266-292` 不变 | 正常 `dispatch`/`beat` 活动 | 反向失败：若通道被一并冻住 ⇒ 吞吐收益归零（RQ-13 I-3 的 stage-close 教训） |
| AC-6 | 复核材料采集（只读） | **允许** | 材料面归 RQ-14/D6；快照写入载荷（F2） | 材料文件存在；其 sha256/mtime 已记入 `review-pending` 载荷 | 复核读取的是"现在的证据"而非"决定时刻的证据"（AC-029/风险 27：实测 24/34 门证据晚于应答，E2 `gate-0010` 晚 13 分钟） |
| AC-7 | `_resume_credits` 授予 | **禁止自动** | `_resume_credits:2273-2294`（无上界）；调用点 `:946/:1062/:1578` | 每 key 的 `resume` 事件计数（`:2349`）；`_resume_credits` 返回值增长 | FM 洪泛实证：同一次 approve 被重放 5588 次 + 6684 pending 门 / 12h（RQ-10 F1c） |
| AC-8 | 手改被延后 key 的 key-status | **禁止（除非是裁决本身）** | 人工编辑 `_roadmap.md`（AC-028 JC 实例，无事件） | key-status 变化且无对应 `review-decided`/`gate-answered`/`stage-close` 事件（需要基线快照，见数据缺口 2） | 无声状态漂移；复核结论覆盖人的编辑（或反之） |
| AC-9 | 已消费答案重放 | **禁止** | `_consumed_gate_ids:297-315` + `timeline.py:93-94`；单调 guard 落点 `_set_stage_status:380-407` | 同一 `gate-\d{4}` 出现 ≥2 次 `gate-answered`；任一 stage status 回退 | JC `gate-0008`：closed → running + 立刻生成新 stage-close 门（已实测） |
| AC-10 | 待复核进入 `_DEP_SATISFIED` | **禁止（红线）** | `conductor.py:56` | F4 的三层判据（静态/行为/镜像/负对照） | 未裁决即解锁依赖 ⇒ 下游写盘后无法回滚 |

### F8 VC 候选（每个关键断言一条机器可判 VC）

| VC | 断言 | 判定方法 | 负对照（测试有牙） |
|---|---|---|---|
| VC-D2-01 | 待复核**不**解锁依赖（静态） | `assert "pending-review" not in conductor._DEP_SATISFIED` | — |
| VC-D2-02 | 待复核**不**解锁依赖（行为） | k2 依赖 k1；k1=`pending-review`；跑一 tick ⇒ `_deps_satisfied` 为假 + 无 `ap-k2-*` 行 + 无 k2 的 `dispatch` 事件 | k1=`done` ⇒ **必须**有 `ap-k2-*` 派发行 |
| VC-D2-03 | 待复核 key **不**被派发 | 同 fixture 连跑 N tick ⇒ 无新增 `ap-k1-*` 非终态行、无 k1 的 `dispatch` 事件 | k1=`running` ⇒ 有派发（且受 cap 约束） |
| VC-D2-04 | 待复核**挡** stage 收口且**不建** stage-close 门 | 3 key stage，2 `done` + 1 `pending-review` ⇒ 该 tick 无 `stage-close` 门（`_gate_open` 假）、无 `stage-close` 事件 | 3 key 全 `done` ⇒ 必须在同 tick 建门 + 写 dossier |
| VC-D2-05 | 全待复核 stage 不建收口门、但产出批量复核材料 | 3 key 全 `pending-review` ⇒ 无 `stage-close` 门；`C`（批量清单）=3 | 全 `done` ⇒ 建门 |
| VC-D2-06 | **窗口不存在性**：stage-close 门 pending 时不得有 `pending-review` key | 扫全量 timeline/roadmap：不存在 (stage-close pending) ∧ (同 stage 有 pending-review key) | — |
| VC-D2-07 | 触发式时机 | stage 内除待复核外全终态 ⇒ 该 tick 出现复核对（`review-decided` 或 `review-escalated`） | 另有一 key `running`（无 in-flight）⇒ 不出现复核事件 |
| VC-D2-08 | 时间兜底 = 升级而非自动裁决 | 强制 `deadline` 过期 ⇒ 出现 `review-escalated`；key-status **仍为** `pending-review`；无 `done`/`closed-legacy` 写入 | 未过期 ⇒ 无 `review-escalated` |
| VC-D2-09 | 合法重开显式且单调 | 复核 `rework` ⇒ key-status 回 `running`，stage status 无变化；且 `_set_stage_status(stage,"closed→running")` 返回 False 并追加 `stage-reopen-refused` | 合法前进转换（`running→closed`）仍返回 True |
| VC-D2-10 | 与 D4 的检测差异 | 重放 fixture（同 gate id 二次 `gate-answered`）⇒ 违规检测为真；合法 fixture（`review-decided`）⇒ 违规检测为假 | 合法 fixture 不得误报 |
| VC-D2-11 | 红线：复核路径永不产出 `closed-legacy` | 跑全部复核 outcome（resume/rework/escalate）⇒ roadmap 无 `closed-legacy`、timeline 无 `closed-legacy` detail | 走 `_apply_stalled_rejections` 的既有路径 ⇒ 必须产出（证明检测能看见它） |
| VC-D2-12 | 跨语言 parity + fail-closed | `set(roadmap.KEY_STATUSES) == set(status_model.KEY_STATUSES)`；`roadmap_check.py` 对含 `pending-review` 的 roadmap 退出 0；**未枚举值**（如 `pending-review2`）仍使 conductor 跳过整 tick（`roadmap.py:352` → `conductor.py:210-212`） | — |

## 结论 → 决策映射

### 对 AC-027（case 2 路径 (1)）

| AC-027 要求 | 本卡交付 |
|---|---|
| 延后期间的**补偿控制** | F7 的 AC-1..AC-10（每项：实现面 + 可检测信号 + 首个失败模式）；最小集 = AC-1（不派发）+ AC-3（禁 `closed-legacy`）+ AC-4（禁收口/放行）+ AC-9（禁重放）+ AC-10（红线） |
| 复核材料的**批量形态** | F5.1 的 `C` 集合（同 stage 全部待复核 key 同 tick）；材料字段面归 RQ-14 / D6；本卡新增"快照绑定"要求（AC-6，对齐 AC-029/风险 27） |
| "延后导致问题被发现太晚"的可检测信号 | F5.2 的 age 告警 + `review-escalated`；F6.3 的 stage 回退检测；数据依据 = RQ-13 F3 四项（p50 24.48h / max 145.99h / ≥211h / 203.93h） |
| 数据依据 | RQ-13 F3.1–F3.4（随引样本量）；本卡不新增实测 |
| "按字面不可实现"的部分 | **已确认**：待复核**不**算终态 ⇒ "延后到阶段末再复核"仍不可实现；实现形态 = **收口前触发式复核 + 时间兜底（升级而非裁决）** |

### 对 spec 红线与其它 AC

- **红线（待复核不进 `_DEP_SATISFIED`）** ⇒ F4 三层判据 + VC-D2-01/02/12。
- **AC-010 / P-021（两侧逐字段一致）** ⇒ F2 的"枚举改动清单"（Python 3 处 + TS 3 处）+ VC-D2-12；`monitor.ts:505` 与 `_DEP_SATISFIED` 是两份独立字面量，必须用 parity VC 锁。
- **AC-016/017/018（白名单 / 防护 / 审计）**：本卡只给它需要的**状态载体**；白名单与 kill switch 归 D5。但 F5.2 明确"兜底不得自动裁决"、F6.1 明确"复核三态无 `closed-legacy`"，这两条是 D5 白名单的输入约束。
- **AC-019（默认动作显式声明）**：待复核的默认动作 = `escalate`（到点升级给人），**不是**隐式永久滞留；缺省行为与今天的 `stalled` 不同（今天无人值守 = 永久 pending）。
- **AC-022 D2（`_apply_stalled_rejections` 无消费守卫）**：本卡**不动**该路径，但把"复核不得触达 reject/closed-legacy"写成约束（VC-D2-11）⇒ 与 D2 修法不冲突。
- **AC-028 / D4（消费记录持久化 + stage 单调性）**：F6.1 的 rank guard 是 D4 修法的**必需组件**（无单调性则合法重开与意外重开无法区分）；本卡只给设计面，不改 `_consumed_gate_ids`。
- **AC-031（`validate_roadmap` 未被调用）**：F1.1 P3/P17 指出值是**单闸**（只有 parse 期 enum），roadmap-writer（W5）与人工（W6）都能写出未枚举值；本卡的建议是"新值必须同时进两侧 enum + `roadmap_check.py`"，**不**顺带把 `validate_roadmap` 接进 conductor（那是 D6/AC-031 的面）。

### 与其它 design 卡的接口

| 卡 | 本卡给它的输入 | 它给本卡的输入 |
|---|---|---|
| D1（门命题） | 待复核的三态 outcome 名（resume/rework/escalate）与"复核不得产出 `closed-legacy` / 不得写 `done`"约束 | 复核的实际判据（哪些命题可机器复算 ⇒ resume/rework） |
| D3（消费记录） | F6.3 的检测规则与"消费记录必须有保留期"的硬约束 | 持久化形态（决定复核引用如何防重放） |
| D4（证据 provenance） | AC-6 的"决定时刻快照"字段需求 | 证据源优先级（决定复核材料读哪一份） |
| D5（自动决策控制） | F5.2/F6.1 的两条约束（兜底只升级；复核无 `closed-legacy`/`done` 出口） | 白名单 / kill switch / 影子模式 |
| D6（gate schema 与呈现） | F7 的可检测信号清单 + 面板需要 `pending-review` 的计数与 attention 位 | 材料最小信息集 / 面板渲染 |

## 数据缺口

1. **未扫外部项目的自定义脚本**：FM/E2/JC 里可能有非框架脚本直接读 `_roadmap.md` 的 key-status（本卡只扫了两个包根）。⇒ 方法：在目标项目跑 `grep -rn "key-status"`（排除 `node_modules`/`.git`）后再核对一遍消费者清单。
2. **"手改 key-status" 无基线**：AC-8 的检测需要"conductor 上次写入的值"作为对照；今天 roadmap 文件不带写入者/序列（无 `last_writer`/`seq`）。⇒ 需要什么证据：在 `_roadmap.md` 头部加第三个 machine 字段（写者+seq），或完全依赖 timeline 的 `review-decided`/`gate-answered` 事件做对账。
3. **源文件写的机器判定为零**（AC-2 的强制面）：`worker-mode.ts:761-790` 只拦 read；`write/edit` 没有 scope 拦截，`bash` 内的写不可解析（RQ-13 数据缺口 4）。⇒ AC-2 目前只能"事后检测"（trace 窗口计数，且是下界），不能"事前禁止"。
4. **时间兜底 `T` 无实测最优值**：只有 n=4 / n=11 的分布与几条仍在跑的样本，`T=48h` 是**基于分布的设计选择**而非实测最优（标注 `[推断]`）。⇒ 需要影子期数据（D5）来定 `T`。
5. **`budget-exhausted` 走待复核的收益不可量化**：今天它连 key-status 都不写（风险 13），提升为 `pending-review` 会新增可观测量，但生产 0 样本 ⇒ 只能由影子模式验证。
6. **载荷文件的位置未定**：`.agenticdoc/<key>/` 下（随 key 走，与 achieved.md 同域）vs `.agenticdoc/_autopilot/` 下（随协调面走）。本卡只给约束（同锁同刻写、无决策读点），位置归 D6/plan。
7. **单调 rank 表的完整枚举**：本卡只给核心四态与 `halted` 的侧态处理；`approved` 是否可回退 `pending`、`closed-human` 与 `closed` 是否同 rank 需要 D4/AC-028 的完整状态机确认。
8. **门枚举未扩**：本卡不给"复核决定"的 gate 形态（新 gate kind vs 无门 + 事件）。若选新 gate kind，需要 `gates.py:54-61` + TS `GATE_KINDS` + `EVENT_TYPES`（`timeline.py:67-85`）三处同步；本卡把它留为 D6 的决策点，只要求"复核决定的记录必须机器可判且不可由被审方伪造"（AC-030）。

## 机器行

```
[VERIFY] D2: carrier=A(key-status value `pending-review` in _roadmap.md)+minimal sidecar(payload only, no decision reads) rejected=B(sidecar-as-state: cannot be sole carrier, key-status keeps an old value -> two planes can disagree; read points need joins)/C(reuse `stalled`+marker: `stalled` today means "human already repaired, resume grants one round" per _resume_credits:2273-2294 + gate text :3973 -> indistinguishable from "not yet judged") consumers=27(P1 roadmap.py:63-68 enum / P2 roadmap.py:336-361 parse / P3 roadmap.py:409-422 key-set only / P4 roadmap.py:505-530 update helper / P5 roadmap.py:269-274 dup-line / P6 conductor.py:225-232 status_of / P7 conductor.py:274 dispatch-skip literal tuple / P8 conductor.py:285->_deps_satisfied:2153-2154->_DEP_SATISFIED:56 / P9 conductor.py:271->_stage_closure:629-631 / P10 conductor.py:2332 / P11 conductor.py:2376 / P12 conductor.py:2622 / P13 conductor.py:2256 / P14 conductor.py:3958 / P15 conductor.py:3909 / P16 roadmap_check.py:43-57 / P17 conductor.py:601 roadmap-writer prompt / P18 status-model.ts:322 / P19 status-model.ts:521-541 / P20 status-model.ts:1136-1138 / P21 status-model.ts:1183 / P22 monitor.ts:472-476 / P23 monitor.ts:502 / P24 monitor.ts:505 / P25 monitor.ts:597 / P26 monitor.ts:603-624 / P27 console.ts:488) read_points=27(python=17,ts=10) writers=6(W1 :2259 done / W2 :2340 running / W3 :2381 closed-legacy / W4 :3961 stalled / W5 roadmap-writer :520-560 / W6 human edit) doctor_and_advance_phase=zero_reads(negative, scope=packages/multi-workers+mw.py+mw_common.py+agent-team-loop src) top_hazard=conductor.py:274 literal skip tuple ("done","stalled","closed-legacy") -> unhandled pending-review key keeps being dispatched stage_closure={done,closed-legacy} unchanged:629-631 pending_review_is_terminal=NO(denominator=stage.keys, no "majority") trigger=∀o in stage.keys\C: status_of[o] in {done,closed-legacy} AND no in-flight row for the deferred key(s); placed at conductor.py:266-271 before _stage_closure(:271); batch=all deferred keys same tick dep_redline=_DEP_SATISFIED:56 excludes pending-review; VC=static+behavioral(no ap-k2-* row)+mirror(monitor.ts:505 blockedBy)+negative control(k1=done must dispatch) deadline=T=48h default (~2x p50 24.48h, < max 150.53h) sources: stage wall-clock n=4 p50 36.56h max 150.53h(JC s1); gate->stageclose n=11 p50 24.48h max 145.99h; open stages >=211.0h; JC pending stage-close 203.93h on_expiry=escalate-to-human(U-9 B), never auto-decide reopen=review-decided{outcome in resume|rework|escalate} (resume/rework -> key-status running; escalate -> stalled; NO done exit, NO closed-legacy); stage status NEVER regresses (pending-review blocks closure so failure happens while stage is still running); _set_stage_status:380-407 gains rank(pending<approved<running<closed/closed-human) + refuses rank-decrease without reopen_of + emits stage-reopen-refused D4_diff=JC gate-0008 signature: same gate-\d{4} twice in gate-answered + closed->running with no reopen record; legal signature: review-decided with outcome, no stage transition redlines=closed-legacy(_apply_stalled_rejections:2363-2420 only producer; :2388 detail) + source write/delete(machine enforcement zero: worker-mode.ts:761-790 blocks read-ish only; lever activeToolsForType:101) compensation_table=10 rows(AC-1..AC-10 each with detectable signal + first failure mode) vc_candidates=12(incl. 2 negative controls, 1 cross-language parity+enum fail-closed, 1 window-nonexistence) no_new_measured_data=yes(all magnitudes cited from RQ-13 F2/F3) files_written=1(evidence/research/design-deferred-review-state-20260926.md)
```

**数据来源时效**：本文件所有代码锚点来自 2026-09-26 本次运行的只读读取（工作树快照）；所有量级数字引自 RQ-13（2026-09-26 快照，样本量随引）。本卡**未**改任何代码文件、**未**改 E2/FM/JC 的任何文件、**未**答任何 gate、**未** commit。