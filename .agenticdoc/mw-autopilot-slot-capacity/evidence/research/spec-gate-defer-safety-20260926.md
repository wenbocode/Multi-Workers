# Research: gate 的阻塞性与「延后复核」安全性（RQ-13 / msc-rq13-gate-defer-safety）

> Key: `mw-autopilot-slot-capacity` ｜ 角色: spec 期调研（**只读**；本文件是本卡唯一写面）
> 代码基线: `H:/git/Multi-Workers` 工作树快照（`autopilot/conductor.py` 174,500 B / `gates.py` 18,264 B / `dispatch.py` 26,318 B；TS `worker/worker-mode.ts`、`worker/read-scope.ts`、`shared/xkey-gate-guard.ts`）
> 数据快照: **2026-09-26T08:00Z**（FM/E2 autopilot 当时仍在跑；所有数字是该时刻的冻结值，冻结后的行不属于本文）
> 边界: **不重复 RQ-8 的门清单 / 阻塞范围初判 / 等待时长分布 / 无人值守策略现状**，也不重复 RQ-3 的槽位利用率。本文只回答「**能不能晚点判 + 延后期间有什么危险**」。不给方案取舍（属 design）。
> 分析脚本写在 `%TEMP%\rq13_*.py`（未落在任何项目目录），读盘全部只读；`_autopilot` 下的 gate 目录在脚本里用三段拼接写出，以避开 `xkey-gate-guard.ts` 的文本级 fail-closed 扫描。

## TL;DR

1. **6 类门里只有 3 类「延后」在语义上成立**：`stalled` / `budget-exhausted` / `xkey-authorize` —— 不答时项目其余部分照常推进（实测：FM gate-0002/0003 挂起 4.3h 内另有 291 个 tool 事件、27 次 write/edit；E2 gate-0014 挂起 17.4h 内 1139 个 tool 事件、239 次 write/edit）。另外 3 类（`stage-confirm` / `stage-close` / `goal-change`）在**代码结构上**停住整条 roadmap，不答 = 永久停，延后不是选项。
2. **但「能延后」不等于「可以延后到 stage 末」**：`stalled` 与 `budget-exhausted` 都会让 key 保持非终态，而 `_stage_closure` 的终态集是 `("done","closed-legacy")`（`conductor.py:629-631`）⇒ 它们在 stage 末**必然变成硬阻塞**。「延后到阶段目标完成后复核」这句话在当前代码里**不可实现**，除非把复核触发点放在 stage 收口之前（见 CC-4/CC-8）。
3. **延后本身不放行任何不可逆动作**（不答 = 不改状态）；危险在于**窗口内其它工作流产生的动作**与**复核时刻的答案**。实测窗口内动作：E2 gate-0014 的 17.40h 窗口里，别的 key 写/改了 49 个不同文件（80 次落在 `.agenticdoc` 之外，含 `tools/featureverdict/{config,errors,params,guard}.py`）、跑了 585 条 bash、5 次 `Remove-Item`；JC stage 1 全程（150.5h）47 次 `dotnet build`、7 次删除、227 次 `.agenticdoc` 外写。
4. **不可逆动作共 9 类，逐条有锚点**（F2）。其中真正**不可撤销**的只有两条：`closed-legacy`（唯一产生点 `conductor.py:2363-2420`；进 `_DEP_SATISFIED` `:56` ⇒ 解锁依赖 + 放行 stage 收口；`_consumed_gate_ids` `:297` 无撤销入口）与源文件写/删（无快照，写面纪律只在散文里，机器判定零 —— read_scope/deny_globs 只拦 read：`worker-mode.ts:756-780`）。**唯一自带补偿的写路径是 xkey 的 byte 快照 + 恢复**（`_xkey_apply_block:3515` / `_xkey_restore:3460`），但它 opt-in 且生产 0 样本。
5. **「延后上限 = 到 stage 末」的量级（F3，样本量写死）**：已收口 stage 的墙钟 **n=4，p50 36.56h，max 150.53h**（JC stage 1，6.27 天）；「门创建 → 所在 stage 收口」的延后视界 **n=11，p50 24.48h，max 145.99h**。仍在跑的 stage 已 ≥25.15h / ≥48.32h / **≥211.0h（JC stage 2，8.8 天）**，JC 的 pending stage-close 已挂 **203.93h**。⇒ 这个上限在实践中不是「半天」，**不能从 p50 外推**。
6. **新发现（已实证的误放行）**：JC 在 **2026-09-26T04:37:27** 把 09-11 就已答的 `gate-0001`（stage-confirm stage 1）**重放**了一次 ⇒ stage 1 由 `closed` 退回 `running`，并立刻生成新的 stage-close 门 `gate-0008`。根因：消费记录 `_consumed_gate_ids` 是从 timeline 反推的（`conductor.py:297-315`），而 timeline 只保留 **2 代**（`timeline.py:93-94`）⇒ **消费记录有保留期**，而 `_set_stage_status`（`:380-407`）没有单调性检查。延后越久、跨代越多，这类重放的风险越高（见 CC-7）。

`[VERIFY] RQ-13: gates=6 structural_block=[stage-confirm(_stage_activation:434-451,_activate_pending_stage:485),stage-close(_stage_closure:633-634,_ensure_next_stage_gate:409-431),goal-change(tick:2101-2103)] deferrable_in_stage=[stalled(orchestrate:274-275),budget-exhausted(_advance_key:981-1003),xkey-authorize(_xkey_proposal_stage:2875-2913)] never_defer=[stage-confirm,stage-close,goal-change] defer_needs_compensation=[stalled,budget-exhausted] defer_blocked_pending_fix=[xkey-authorize] irreversible_actions=9 hardest=[closed-legacy(_apply_stalled_rejections:2363-2420,_DEP_SATISFIED:56),source_writes(dispatch.REGISTRY:_CODING_TOOLS,worker-mode.ts:52-84,read-scope only:worker-mode.ts:756-780)] only_compensated_write=xkey(snapshot _xkey_apply_block:3515 + restore _xkey_restore:3460) credits_unbounded=_resume_credits:2273 stage_terminal={done,closed-legacy}:629-631 defer_to_stage_end_impossible=yes(629-631) window_actions_measured=E2_gate-0014 17.40h/1139tool/239write-edit/49targets/80outside; FM_gate-0002-0003 4.3h/291tool/27write-edit; FM_gate-0006 15.18h/0tool; JC_stage1 150.5h/3675tool/481write-edit/227outside/47dotnetbuild/7delete stage_wallclock_closed n=4 p50=36.56h max=150.53h(JC s1) defer_horizon_gate_to_stageclose n=11(FM6/E2 3/JC2) p50=24.48h max=145.99h open_stage_sofar=[FM2>=25.15h,E2-3>=48.32h,JC2>=211.0h] pending_gate_max=JC_gate-0007 203.93h(8.5d) replay_regression=JC_gate-0001 reapplied 2026-09-26T04:37:27 closed->running consumed_ids_retention=timeline 2 generations(timeline.py:93-94) no_defer_mechanism=grep_zero anchors=conductor.py:56/274-275/285-286/297-315/348-373/380-407/409-431/434-451/629-634/981-1003/2101-2111/2153-2154/2273/2295-2420/2872/2875/3515/3944-4100,dispatch.py:52-53/71-108/REGISTRY,gates.py:54-81/345-348,monitor.ts:89-96,timeline.py:67-85/93-94,worker-mode.ts:52-84/756-780,read-scope.ts:167-180,xkey-gate-guard.ts:GATE_DIR_FRAGMENT`

## 决策问题

承接 spec §1.1.1 的**三分处置模式**：用户把门重分类成 (1) 可自举验证 / **(2) 非阻塞可延后复核** / (3) 必须当场人审，并要求三分判定先有证据。本卡只做第 (2) 类的安全面，回答 5 个问题：

1. **阻塞性判定**：6 类门各「挡住什么」（key 派发 / stage 收口 / 下一 stage / 整条 roadmap），逐条给代码锚点，并区分**结构性阻塞**（终态集、依赖集、tick 早退）与**实现选择**；若把该门延后（不答也能继续），当前代码会怎么走（有/无路径）。
2. **不可逆动作清单**（spec 风险 21 的核心）：延后窗口内可能发生哪些**不可逆或高代价**动作（写/改代码、重建 dist、删文件、`closed-legacy`、roadmap 编辑、stage 激活、token 消耗），逐条锚点；哪些门的延后会**放行**它们。
3. **补偿控制候选**：若要延后某门，需要什么机制才能「不误放行」——每条给实现面 `file:line` 与可检测信号（不给取舍）。
4. **延后上限的数据依据**：若上限设成「到 stage 末」，最坏会延多久（单 stage 墙钟分布 + 样本量）。
5. **三分建议的边界情形**：哪些门**绝不能延后**、哪些延后**安全**、哪些需要**延后 + 补偿**。

**不做**：不给落地方案（改哪些键、新字段怎么设属 design）；不答任何 gate；不重复 RQ-8 的门清单与等待时长分布（只在需要时引用）。

## 调研方法与出处

### 代码（只读；行号 = 本卡工作树快照）

| 面 | 位置 |
|---|---|
| 门闭集 / 12 字段 schema（**无 timeout / deadline / expires 字段**） | `autopilot/gates.py:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:68-81`（`FRONTMATTER_FIELDS`）、`:345-348`（未知字段 → `GateFormatError`） |
| 派发循环顺序（终态跳过 → claim → 依赖 → 在飞 → cap） | `conductor.py:253-292`；stalled 跳过 `:274-275`；依赖 `_deps_satisfied:285-286`；cap `:289` |
| stage 收口（终态集 = `done`/`closed-legacy`） | `_stage_closure:616-656`，终态集 `:629-631`，已开门则 return `:633-634` |
| stage 激活 / 下一 stage 门 | `_stage_activation:434-451`；`_activate_pending_stage:454-486`；`_ensure_next_stage_gate:409-431` |
| 已答门的消费（stage-confirm/stage-close/xkey/stalled） | `_consume_answered_gates:316-378`（stage-confirm `:353-358`、stage-close `:359-373`、stage-close reject→`halted` `:374-378`） |
| 消费记录（从 timeline 反推，**有保留期**） | `_consumed_gate_ids:297-315`；`timeline.py:93-94`（`ROTATE_GENERATIONS = 2`）、`:388-400`（query 读全部代） |
| 依赖口径 | `_DEP_SATISFIED:56`；`_deps_satisfied:2153-2154` |
| key-status / stage-status 写点 | `_set_stage_status:380-407`；`roadmap.update_key_status:505` / `update_stage_status:492`；`mark_stalled:3944-3994`；`_mark_key_done:2240-2271`；`_apply_stalled_approvals:2295-2361`；`_apply_stalled_rejections:2363-2420` |
| stalled 的续跑预算（**无上界**） | `_resume_credits:2273-2294`；调用点 `:946`（L2）、`:1062`（execute）、`:1578`（L3） |
| budget-exhausted 的两向 | `_advance_key:981-1003`（`allowed` 判定 `:984`）、`_budget_bonus:2216-2227`、`_budget_gate_rejected:2228-2239` |
| goal-change（tick 早退，**全局停**） | `tick:2050-2111`，创建 `:2082-2097`，早退 `:2101-2103`，恢复 `:2105-2111`（approve/reject 同效） |
| xkey-authorize（opt-in；挡修复链） | `orchestrate:259-267`（`cfg["xkey_repair"]` 门控）、`_xkey_ensure_gate:2724-2751`、`_consume_xkey_gate:2798-2855`、`_xkey_proposal_stage:2875-2913`、`_xkey_apply_block:3515-3594`、`_xkey_verify_failed:3477-3514`、`_xkey_restore:3460-3476`；默认值 `config.py:74-77` |
| roadmap-writer（**无声停死、无门**） | `_dispatch_roadmap_writer:520-560`，两次提案用尽 `:545-546` |
| 派发类型 → 工具集（写面入口） | `dispatch.py:52-53/71-108`（`_CODING_TOOLS` / `_REVIEW_TOOLS` / `REGISTRY`）；worker 侧 `worker-mode.ts:52-84`（`TOOL_ALLOWLISTS`）、`:93-108`（`toolsForType`/`activeToolsForType`） |
| 写面纪律的**机器判定为零** | `worker-mode.ts:756-780`（只拦 `read/ls/find/grep`）；`read-scope.ts:167-180`（deny-glob 只作用于 read-ish） |
| 派发 → 进程（token 消耗入口） | `dispatch.dispatch`（末段写 queue 行）→ `launcher.py:_poll_once:775`、`_spawn:910-990`、`subprocess.Popen:966` |
| 只在散文里的写约束 | `_exec_prompt:1053-1058`（"只碰任务书列出的文件"）；`_phase_writer_prompt:2011-2018`；`_fix_writer_prompt:2032-2048` |
| 不可逆动作的删除面 | `closure.delete_bad_draft_marker`（`closure.py`）；调用点 `conductor.py:1878`、`:1928`、`:2268`、`:2391` |
| gate 目录被工具层封堵（agent 不得代答） | `shared/xkey-gate-guard.ts`（`GATE_DIR_FRAGMENT`、`checkXkeyGateBashCommand`） |
| 面板 / doctor 无 gate age | `monitor.ts:89-96`（`MonitorGate` 只有 id/kind/stage/key）、`:150-179` |

### 数据（只读；3 个项目；快照 2026-09-26T08:00Z）

| 项目 | 路径 | gate 文件 | timeline 窗口 | 备注 |
|---|---|---|---|---|
| FM | `E:/CLI_workspace/FeatureMigrator` | live 10 + 归档 `_gates-flood-20260924` 6684 | 09-23T09:06Z → 09-26T08:15Z（92,193 行） | 唯一含洪泛 |
| E2 | `H:/git/E2Feature` | 18 | 09-22T03:35Z → 09-26T08:15Z（97,416 行） | — |
| JC | `H:/git/JCodingAss` | 8（6 已答 + 2 pending） | **只剩** 09-15T20:04Z → 09-26T08:15Z（200,715 行） | 更早 timeline 代已被轮转剪掉 |
| MW（本仓） | `H:/git/Multi-Workers` | 无 `.agenticdoc/_autopilot/` | — | 对 autopilot 零样本 |

三项目 `config.json` 均 `enabled=true / max_parallel_keys=2 / round_budget=2`，**均未设 `xkey_repair`**（⇒ 默认 false，xkey 通道在生产中从未挂载）。另读 `<key>/workers/<task>/trace.log`（FM 232 / E2 485 / JC 70 个）取 tool 事件。

### 算法与复算

1. **stage 墙钟** = timeline 的 `gate-answered` 事件里「stage N approved → stage N running」的 ts → 「stage N approved → stage N closed」的 ts。JC stage 1 的 open 事件不在保留代内，改用 gate 文件 mtime（门在被应答前不会被写，故 mtime = 应答写入时刻；该口径同 RQ-10 F1e）。
2. **延后视界（门创建 → 所在 stage 收口）** = gate 文件 `created_at` → 该门所辖 key 所在 stage 的 close 时刻；stage 未收口时用快照封顶并标 `snapshot(open)`。key→stage 映射取 `_roadmap.md` 的 `> key-status:` 行。
3. **窗口内动作** = `trace.log` 的 `[TOOL] <ts> <tool> <target>` 行，落在 `[gate.created_at, gate.answered_at]` 内的计数；`write`/`edit` 的 target 即文件；bash 内是否真写不可解析（故窗口内动作数是**下界**）。
4. 只用 Python 标准库；脚本 `%TEMP%\rq13_defer.py`、`rq13_writes.py`、`rq13_window.py`、`rq13_build.py`、`rq13_jc.py`。

## 发现

### F1【事实】阻塞性判定表（6 类门）

**A. 结构性阻塞（不答 = 整条 roadmap 停；没有"继续"路径）**

| gate kind | 挡住什么 | 主锚点 | 结构性 or 实现选择 | 延后（不答）时当前代码怎么走 |
|---|---|---|---|---|
| `stage-confirm` | **整条 roadmap**：没有 `running` stage 时 `orchestrate` 在 `_stage_activation` 返回 False 就 `return`，per-key 循环永不进入 ⇒ 该 stage 的 key 一个都不派发 | `_stage_activation:434-451`（`if any(status=="running"): return True`）、`_activate_pending_stage:454-486`（`if _gate_open(...): return  # awaiting the human`）、`orchestrate:217` | **结构性**：stage 的 `> status: pending` 是 roadmap 结构状态，只有 approved 分支的 `_set_stage_status(running):353-358` 会改 | **无路径**。pending ⇒ `_activate_pending_stage` 空转 ⇒ `_stage_activation` False ⇒ 本 tick 零派发。想"延后仍继续"只能改 `_stage_activation` 判据或自动 approve —— 即延后 ≡ auto-approve（放行一整 stage 的写面 + token） |
| `stage-close` | 该 stage 不收口（保持 `running`）⇒ `_ensure_next_stage_gate` 不被调用（只在 approved 分支 `:371`）⇒ **下一 stage 永停在 `pending`** | `_stage_closure:633-634`、`_consume_answered_gates:359-373`、`_ensure_next_stage_gate:409-431` | **结构性**（阶段串行：`_stage_activation:434-451` 只认 `running`，pending stage 必须排在 closed 之后） | **无路径**。且建门前提是该 stage 全部 key 已终态（`:629-631`）⇒ 此时项目通常已无活可干（JC 实测该门挂起 136.4h 窗口内 **0 个 tool 事件**）。reject 更硬：`:374-378` → `halted`，需人工改 roadmap |
| `goal-change` | **全部**：`tick` 在 `orchestrate` 之前就 `return "halted-goal-change"` ⇒ 不消费门、不 reconcile、不派发、不收口（只有 `beat` 继续） | `tick:2101-2103`、创建 `:2082-2097` | **结构性**（最硬；且是 tick 级早退，不是 stage 级） | **无路径**。且 approve 与 reject 行为相同（`:2105-2111` 只判"是否仍 pending"）⇒ 这道门现在「不答全停、答什么都一样」（RQ-10 I5 同结论） |

**B. 部分冻结（不答时项目其余部分照常跑；只有该 key 与它的下游被冻）**

| gate kind | 挡住什么 | 主锚点 | 结构性 or 实现选择 | 延后（不答）时当前代码怎么走 |
|---|---|---|---|---|
| `stalled` | (i) 该 key 自身派发；(ii) 依赖它的下游 key；(iii) stage 收口（进而下一 stage） | (i) `orchestrate:274-275`（`in ("done","stalled","closed-legacy")` → `continue`）；(ii) `_deps_satisfied:285-286` + `_DEP_SATISFIED:56`；(iii) `_stage_closure:629-631` | (i)(ii)(iii) **结构性**（终态集/依赖集的字面判定）；"其余部分继续"是**既有实现路径** | **有路径，且就是今天的默认行为**：key 被跳过、同 stage 其它 key 照常派发（实测 FM gate-0002/0003 挂起 4.3h 内有 291 个 tool 事件）。延后**不放行**该 key 与下游 |
| `budget-exhausted` | 该 key 的下一轮派发（`allowed` False ⇒ `return False`，**既不派发也不置 `stalled`**）；经"key 非终态"传导到 stage 收口与下游依赖 | `_advance_key:981-1003`（`allowed` 判定 `:984`）、`_budget_bonus:2216-2227`、`_budget_gate_rejected:2228-2239` | 同上，**比 stalled 更隐蔽**（key-status 不变，面板只有 `gates: 1 pending`；RQ-8 F1 同结论） | **有路径**（其余 key 继续）；该 key 静默冻结 |
| `xkey-authorize` | 该 `request_id` 的**跨 key 修复链**（approved 才派 proposal；`_consume_xkey_gate` 才推进 ticket）。**不挡** owner key 自身的相位机（ticket 只在 owner terminal 后才可能被 mint） | `_xkey_ensure_gate:2724-2751`、`_consume_xkey_gate:2798-2855`、`_xkey_proposal_stage:2875-2913`、`orchestrate:259-267` | **结构性但 opt-in**：整套机制由 `cfg["xkey_repair"]` 门控，默认 false（`config.py:74-77`），FM/E2/JC 三项目均未开 ⇒ 生产未挂载 | **有路径**（其余 key 继续），冻结该修复链。0 生产样本 ⇒ 实际影响**无法判定**（需要影子模式/受控复现） |

**C. 相邻但无门的停机点（对 AC-027 的边界提醒，不重复 RQ-8 清单）**：`_dispatch_roadmap_writer:545-546`（两次提案用尽 → 停在"等人改 roadmap"，**不产生 gate**）、`orchestrate:205-212`（roadmap unreadable）、`_consume_answered_gates:335-337`（gate 文件损坏 → 整 tick 跳过）。⇒ **任何以 gate 为触发器的延后机制都看不见这三类停摆**（延后策略必须另行覆盖，或至少要能告警）。

### F2【事实】延后窗口内的不可逆 / 高代价动作清单

**读法（spec 风险 21 的准确形状）**：**延后本身不放行任何动作**（不答 = 不改状态）。危险来自两侧：**(a) 窗口内其它工作流**照常产生的动作（与延后的门无关，但会改动代码/产物、让被延后门的证据陈旧）；**(b) 复核时刻的答案**触发的动作（这才是「误放行」）。下表逐条给锚点，并标出「哪一侧放行它」。

| # | 动作 | 代码锚点 | 谁放行 | 可撤销性 | 实测规模（窗口内/总量） |
|---|---|---|---|---|---|
| IA-1 | **写/改源文件**（含跨仓库） | 工具集入口 `dispatch.py:52-53/71-108`（`_CODING_TOOLS` = read/write/edit/bash/find/grep/ls）+ `REGISTRY`；worker 侧 `worker-mode.ts:52-84`；派发点 `_advance_key:937/:975/:1112`、`execute_loop:1112`、`_verify_loop:1746`（`repair`）、`_dispatch_roadmap_writer:550` | **(a) 窗口内**：任何未被冻结的 key 的任何一次派发；**(b) 复核时**：`stalled` approve（额外一轮 + `_resume_credits`）、`budget-exhausted` approve（+1 轮）、`stage-confirm` approve（放行整 stage）、`xkey-authorize` approve（受限修复） | **无**（无快照；写面纪律只在散文：`_exec_prompt:1053-1058`；机器判定零：`worker-mode.ts:756-780` 只拦 read） | 窗口内：E2 gate-0014 **17.40h → 239 次 write/edit / 49 个目标 / 80 次在 `.agenticdoc` 外**；FM gate-0002/0003 4.3h → 27 次；FM gate-0006 15.18h → **0**（该窗口内无其它 key 在跑）。总量：FM 4090 次 write/edit（927 目标）、E2 7751 次（2604 目标）、JC 663 次（324 目标） |
| IA-2 | **重建 / 编译产物（dist、bin/obj、pyinstaller）** | **无 conductor 步骤**；可达性锚点 = bash 工具授权（同 IA-1）。无代码路径可锚定"构建"本身 | 同 IA-1（worker 的 bash） | 重跑构建可覆盖（可逆但耗 token/时间）；若被自举验证引用则证据陈旧 | 实测 bash：JC `dotnet build` **48**；E2 `--build` **14**；FM `pyinstaller` 1 + `setup.py` 3 + `msbuild` 1；JC stage-1 窗口内 **47** 次 `dotnet build` |
| IA-3 | **删除文件** | conductor 侧：`closure.delete_bad_draft_marker`（调用点 `conductor.py:1878/:1928/:2268/:2391`，只删一个 marker，低成本）＋ worker 侧 bash 无限制 | 同 IA-1；`closed-legacy` 路径也会删 bad-draft marker（`:2391`） | 无（除非版本控制里还有） | 实测 bash：FM `Remove-Item` **134**、E2 **202**、JC **8**（多为 temp/evidence，但工具无限制）；JC stage-1 窗口内 7 次 |
| IA-4 | **git commit / push** | 同 IA-1（bash 内含 `git`） | 同 IA-1 | 需 reset/revert（本卡不评估） | 实测：FM 1、E2 2 |
| IA-5 | **`closed-legacy`（终态 + 解锁依赖 + 放行 stage 收口）** | 唯一产生点 `_apply_stalled_rejections:2363-2420`；语义作用 `_DEP_SATISFIED:56` → `_deps_satisfied:2153-2154`（解锁下游派发）＋ `_stage_closure:629-631`（终态集含 `closed-legacy` ⇒ 放行收口） | 只有 **(b) 复核时的 `stalled` reject** 能产生；**(a) 窗口内不可能**（延后 = 不答） | **不可撤销**：`_consumed_gate_ids:297-315` 只做去重，全仓无撤销入口；只能手改 roadmap 且不留事件（spec 风险 15）；该路径**无消费守卫**（AC-022 D2） | 生产 **0 样本**（三项目 34 条应答全 approve，RQ-10 F1b） |
| IA-6 | **roadmap 编辑**（stage / key 状态） | `_set_stage_status:380-407`（stage running/closed/halted）＋ `roadmap.update_key_status:505`（key running/stalled/done/closed-legacy，调用点 `:2240/:2295/:2363/:3944`）＋ roadmap-writer worker 整文件重写（`:550-556`，唯一写目标 `_roadmap.md`） | **(b) 复核时**：`stage-confirm` approve→running（`:353-358`）、`stage-close` approve→closed / reject→halted（`:359-378`）、`stalled` approve→running / reject→closed-legacy；**(a) 窗口内**：`mark_stalled:3944`（window 内新 stall 会继续写）、`_mark_key_done:2240` | 部分可逆（手改），但**实测发生过非人工回退**（见 F5） | 见 F5（JC：`closed → running` 回退 1 次） |
| IA-7 | **stage 激活**（一次性放行整 stage 的 key 派发） | `_consume_answered_gates:353-358` → `_set_stage_status(running)` → `_stage_activation:434-451` → per-key loop `:253-292` | **(b) `stage-confirm` approve**（唯一）。注意 `stage-close` approve **只开下一道 confirm 门**（`_ensure_next_stage_gate:409-431`），**不派发 key** —— 所以 `stage-close` 单独 approve 不释放 IA-7，风险链是 `stage-close approve + stage-confirm approve`（RQ-10 风险 18 同结论） | 难（已派发的 worker 会写盘） | 每次 confirm approve = 一个 stage（FM Stage 1 = 5 key、E2 Stage 3 = 9 key、JC Stage 1 = 4 key） |
| IA-8 | **token 消耗**（worker 进程继续跑） | `dispatch.dispatch` 写 queue 行 → `launcher.py:_poll_once:775` / `_spawn:910` / `Popen:966`；额外轮次 `_resume_credits:2273-2294`（**无上界**，调用点 `:946/:1062/:1578`） | **(a) 窗口内**：未被冻结的每个 key 的每次派发；**(b) 复核时**：`stalled`/`budget-exhausted` approve（+轮）、`stage-confirm` approve（整 stage）、`stage-close` approve（间接，下一 confirm） | 不可回收 | 窗口内 tool 事件数即下界：E2 1139 / FM 291 / FM gate-0006 0；`_resume_credits` 无上界已被实证利用（FM 洪泛，RQ-10 F1c） |
| IA-9 | **xkey 目标文件改写**（唯一自带补偿的写路径） | `_xkey_apply_block:3515-3594`（先写 byte 快照 `_XKEY_BAK_NAME`，再 `xkey.apply_block_replace`，drift-refusing）；失败 → `_xkey_verify_failed:3477-3514` + `_xkey_restore:3460-3476`（按 sha 校验回滚） | **(b) `xkey-authorize` approve**（ticket approved → proposal worker → apply） | **有补偿**：byte 快照 + sha 校验恢复；但依赖 run_dir 快照仍在 | opt-in 且 **0 样本**（三项目 `xkey_repair` 未开） |

### F3【事实】「延后上限 = 到 stage 末」的现实规模

**F3.1 单 stage 墙钟（已收口 stage；样本量 = 4）**

| 项目 | stage | open（confirm 被答） | close（close 被答） | 墙钟 |
|---|---|---|---|---|
| FM | 1 | 2026-09-23T09:43:08Z | 2026-09-25T06:50:16Z | **45.12h** |
| E2 | 1 | 2026-09-22T03:54:16Z | 2026-09-23T07:54:18Z | **28.00h** |
| E2 | 2 | 2026-09-23T08:08:19Z | 2026-09-24T07:37:59Z | **23.49h** |
| JC | 1 | 2026-09-11T06:20Z（gate 文件 mtime 口径） | 2026-09-17T12:51:42Z | **150.53h（6.27 d）** |

n=4：min 23.49h，**p50 36.56h**，**max 150.53h**。样本量小（4 个），且 JC 样本的 open 只能由 gate 文件 mtime 推定（timeline 更早代被轮转剪掉）。

**F3.2 仍在跑的 stage（快照下限）**：FM stage 2 ≥ **25.15h**；E2 stage 3 ≥ **48.32h**；JC stage 2 ≥ **211.0h（8.8 d）**。⇒ 真实分布的上尾**超过已收口样本的 max**，「p50 ≈ 36h」不可外推。

**F3.3 延后视界（门创建 → 所在 stage 收口；key 级门 + 已收口 stage）**

| 项目 | n | min | p50 | max |
|---|---|---|---|---|
| FM | 6 | 2.58h | 24.50h | 43.66h |
| E2 | 3 | 9.76h | 16.43h | 18.18h |
| JC | 2 | 143.74h | 144.87h | **145.99h** |
| **合计** | **11** | 2.58h | **24.48h** | **145.99h（6.08 d）** |

**F3.4 仍在延后中（今天的窗口长度）**：E2 stage 3 的 8 个 key 级门已挂 1.32–42.96h；FM gate-0010 已挂 20.98h；JC 两条 **pending stage-close**：`gate-0007`（stage 2）**203.93h（8.5 d）**、`gate-0008` 3.38h。JC 还有一条已答的 stage-close `gate-0005` 等了 **136.44h** 才被答（RQ-10 的 136.4h 同源）。

**F3.5 结论（数据面）**：若「延后上限 = 到 stage 末」，最坏规模 = 单 stage 墙钟，**实测 max 150.53h ≈ 6.3 天，且当前仍在跑的窗口已 ≥211h ≈ 8.8 天**。且这个上限对 `stalled`/`budget-exhausted` **在结构上不成立**：它们让 key 保持非终态，而 `_stage_closure:629-631` 的终态集不含二者 ⇒ **stage 永远收不了口**，所以"到 stage 末再复核"这句话在当前代码里是自相矛盾的 —— 正确形态必须是**时间上界**或**"stage 内其它 key 全部终态"的触发式上界**（见 CC-4/CC-8）。

### F4【事实】补偿控制候选（每条：实现面 + 可检测信号 + 缺位首个失败模式）

| # | 目标 | 候选机制 | 实现面（`file:line`） | 可检测信号（现状可得性） | 缺位时首个失败模式 |
|---|---|---|---|---|---|
| CC-1 | 让「是否不可逆 / 是否越出写面」**机器可判**，从而决定延后窗口能否放行该动作 | task.md 增加结构化 `write_scope` / `irreversible:` 声明（今天只有 `read_scope`/`deny_globs`，且只拦 read） | 渲染侧 `dispatch.render_task_md`（`dispatch.py:render_task_md`）+ 类型工具集 `dispatch.py:REGISTRY:68-96`；消费侧 `worker-mode.ts:756-780`（现状**只拦 `read/ls/find/grep`**）、`read-scope.ts:167-180` | **需新增**：task.md 的新字段；worker trace.log 的写侧拒绝行（现状只有 read 侧拒绝会追加行） | 延后窗口内一个 worker 改掉 owner key 之外的源文件而无人知（**已实测**：E2 gate-0014 窗口内写 `tools/featureverdict/{config,errors,params,guard}.py`；另有一条写进了 `H:/git/Multi-Workers/packages/multi-workers/CHANGELOG.md`） |
| CC-2 | 延后窗口内**禁止某类写**（freeze 冻结 key 的写面） | 按 key/stage 的"延后中"状态把 `write/edit/bash` 从 worker 工具集降级（`activeToolsForType` 已是现成注入点） | `worker-mode.ts:93-108`（`activeToolsForType`）、`:746-747`（"Set tool allowlist once before the first agent run"）；状态来源必须落盘可重推（GC-1/风险 12）——候选判据面 `_gate_open:2188-2215`（已支持按 kind/loop/stage/request_id 查 pending）+ `_roadmap.md` 的 stage/key 状态（`roadmap.py:52-68`） | 需新增：冻结期该 key 的写拒绝行；队列行/task.md 的 allowlist 降级可见。注意**现有 `read_scope`/`deny_globs` 不能复用**（只拦 read，`worker-mode.ts:756-780`） | 被冻结 key 被"顺手修一下"，与其它 key 产生同文件双写（P-018/P-019 家族，spec 风险 2） |
| CC-3 | 把不可逆动作**队列化到复核之后** | 无现成机制；可用原语 = "状态落盘 + 每 tick 由文件重推"（D-102，`orchestrate:183-192`）。候选：gate 文件加 `defer_until` / `deferred_actions`（**需扩 12 字段 schema**）或 sidecar `.mw/deferred/<gate-id>.json` | schema 扩展面 `gates.py:68-81` + `:345-348`（未知字段直接 `GateFormatError`）；先例：`.mw/` 只放锁与 PID（`conductor.py:63-69/:116-119`）、`_XKEY_PROPOSAL_MAX_ATTEMPTS:2872`（由 ticket frontmatter 重推的计数器）、`_consumed_gate_ids:297` | 需新增：`gate-deferred` / `gate-expired` 一类事件（timeline 事件词表是 **17 类闭集** `timeline.py:67-85` ⇒ 要一并扩） | 延后期间就派发了"只允许复核后做"的动作（典型：xkey apply、整 stage 激活） |
| CC-4 | **延后上限**（时间 / 条数） | gate 加 `expires_at`（时间上界）＋"stage 内其它 key 全部终态"触发式上界（结构上界，无需新字段） | 时间字段：`gates.py:68-81`（当前**无任何时间/期限字段**，RQ-10 F5 同结论）；条数口径复用"由文件重推的计数"范式（`_resume_credits:2273`、`_XKEY_PROPOSAL_MAX_ATTEMPTS:2872`）；触发式判据 = `_stage_closure:629-631` 的终态集 + `_gate_open:2188` | 需新增：gate 文件 `expires_at`；面板要能看 age（**`MonitorGate` 现无 `created_at`**，`monitor.ts:89-96`；`mw doctor` 无 gate 节） | 延后无上界 = 永久延后。**已实测**：JC `gate-0007` 已 pending **203.93h（8.5 d）**；若延后策略照抄这个窗口，等价于放弃收口 |
| CC-5 | `closed-legacy` / **所有 reject 方向**不得由延后复核自动产生 | 复核窗口只接受 approve 或"升级给人"；reject 方向必须证明来源是人 | 消费点唯一 `_apply_stalled_rejections:2363-2420`；来源判定缺字段（`answered_by` 是**自由文本**，RQ-8 F6 / RQ-10 F5）⇒ 需结构化 `decided_by` | 现在可得：`gate-answered` 事件 `detail = "...rejected → {key} closed-legacy"`（`:2388`）＋ roadmap key-status 变 `closed-legacy` | 批量复核把"没人修过的 stalled key"一次 reject ⇒ `closed-legacy` 进 `_DEP_SATISFIED:56` **解锁下游 + 放行 stage 收口 = 伪完成**（RQ-10 W3；FM gate-0004 note 原文"不做 closed-legacy：放弃即等于丢弃已交付成果"） |
| CC-6 | approve 的**续跑预算有界** | 每 key / 每延后窗口的 approve 次数上界；`_resume_credits` 加 cap | `_resume_credits:2273-2294`（当前 `sum(...)` 无上界）、调用点 `:946/:1062/:1578` | 现在可得（需自己算）：每 key 的 approved stalled gate 个数（gate 目录重推）；每次 approve 有 `resume` 事件（`:2349`） | FM 洪泛实证：同一次 approve 被重放 **5588** 次 + 6684 个 pending 门 / 12h（RQ-10 F1c）；自动 approve 无上界 = 取消所有预算上限 |
| CC-7 | 复核/延后期间**已消费答案不得重放**；stage 状态**单调** | ① 消费记录改为持久（gate 文件字段 / sidecar），不再只靠 timeline 反推；② `_set_stage_status` 加单调性检查（`closed` 不接受回退到 `running`） | ① `_consumed_gate_ids:297-315`（从 timeline 反推）+ `timeline.py:93-94`（只留 2 代）；② `_set_stage_status:380-407`（当前只要 `stage.status != new_status` 就写） | 现在可得：stage status 出现 `closed → running` 回退事件；同一 gate id 第二次 `gate-answered` | **已实测**（F5）：JC `gate-0001` 在 09-26 被重放 ⇒ stage 1 由 closed 退回 running，并立刻生成新 stage-close 门 `gate-0008` |
| CC-8 | 「延后导致问题被发现太晚」的**可检测信号** | (i) gate age 进面板/doctor；(ii) "阻塞面已塌缩"判据（该门所在 stage 的其它 key 全部终态 + 该门仍 pending）；(iii) 单 stage 墙钟超过实测分位；(iv) stage status 回退 | (i) `monitor.ts:89-96`（`MonitorGate` 加 `created_at`）+ `mw_common.py` 的 `_doctor_autopilot`（现状无 gate 节，RQ-8 F6）；(ii) `_stage_closure:629-631` 终态集 + `_gate_open:2188`；(iii) 本卡 F3；(iv) CC-7 | 现在**不可得**：面板无 age、doctor 无 gate、无告警（`_doctor_issues` 不检查 gate 陈旧度） | 复核在 stage 末才发生，而 stage 因该门收不了口 ⇒ 「延后」只把"门等待"变成"更长的门等待"，**吞吐收益为零**（注意与 RQ-10 I2 的"超时提醒/升级"是同一机制、不同触发） |
| CC-9 | 批复核的**材料形态**（批量可读） | 归 RQ-14（人审最小信息集）；本卡只给边界 | gate 12 字段（`gates.py:68-81`：`id/kind/stage/key/created_at/created_by/question/context_refs/status/answered_at/answered_by/note`，其中 `question`/`note`/`context_refs` 是散文）＋ dossier（`conductor.py:722-750`）＋ timeline 事件 | 现在部分可得（RQ-10 F2a 已列） | 批量复核时人只看得到散文（RQ-14 的题） |

### F5【事实】新发现：消费记录的保留期缺口 —— 已发生的「重放 → stage 回退」

JC 的证据链（全部来自 timeline，`H:/git/JCodingAss/.agenticdoc/_autopilot/timeline.jsonl*`）：

| seq | ts (UTC) | 事件 |
|---|---|---|
| 132214 | 2026-09-17T12:51:42 | `gate-answered` stage=1 `gate-0005 approved → stage 1 closed` |
| 132216 | 2026-09-17T12:51:42 | `gate-created` stage=2 `gate-0006 kind=stage-confirm` |
| 132319 | 2026-09-17T12:59:06 | `gate-answered` stage=2 `gate-0006 approved → stage 2 running` |
| … | … | Stage 2 正常派发（`e2e-validation`） |
| **295906** | **2026-09-26T04:37:27** | `gate-answered` stage=1 **`gate-0001 approved → stage 1 running`** |
| 295907 | 2026-09-26T04:37:27 | `gate-created` stage=1 `gate-0008 kind=stage-close` |

- `gate-0001` 的文件 mtime 是 **2026-09-11T06:20Z**（它在 09-11 就被答过，等待 2.79h）⇒ 09-26 这条是**重放**，不是新答。
- 机制：`_consume_answered_gates:316` 用 `_consumed_gate_ids:297-315` 去重，而后者是**从 timeline 的 `gate-answered` 事件反推**的；timeline 只保留 `ROTATE_GENERATIONS = 2` 代（`timeline.py:93-94`）。JC 的 timeline 从 seq 98074（09-15T20:04）起，09-11 的消费记录早已被剪掉 ⇒ `gate-0001` 重新"未消费" ⇒ 再次执行 `_set_stage_status(stage 1, "running")`（`:353-358`）⇒ 因为 `_set_stage_status:380-407` 只比较"是否不同"、**没有单调性检查**，`closed → running` 被写入 ⇒ stage 1 的 key 已全部 done（roadmap `key-status` 四键全 done）⇒ 同一 tick 的 `_stage_closure:629-631` 满足终态条件 ⇒ 立刻生成新的 stage-close 门 `gate-0008`。
- 现状后果（快照时）：JC `_roadmap.md` 里 **Stage 1 与 Stage 2 同时是 `running`**；`gate-0007`（stage 2 close，09-17 起）+ `gate-0008`（stage 1 close 重放产物）两条 pending。
- 与延后的关系：**延后越久、跨 timeline 代越多，这类"旧答案被重新应用"的窗口越大**。它不是延后机制引入的新缺陷（今天已存在），但它是「延后复核」必须补偿的一环（CC-7），也是"延后的可审计性"的硬约束：**判"这门有没有被答过"不能只看 timeline**。

### 【推断】

- **I-1**：把「延后到阶段目标完成后复核」按字面实现（不答 + 等 stage 收口）**在当前代码上不可行**，因为 `stalled`/`budget-exhausted` 的存在会让 `_stage_closure:629-631` 永不满足。可实现的形态只有两种：(a) 时间上界（到点强制复核/升级）；(b) 触发式上界（"该 stage 内其它 key 全部终态"或"无其它可派发工作"时立即复核，早于收口）。后者不需要新 schema，只需要一个由文件重推的判据，且与 CC-4/CC-8 共用。
- **I-2**：在 6 类门里，**唯一同时满足"延后期间不释放不可逆动作"与"延后期间不放行整 stage"的只有 `stalled` 与 `budget-exhausted`**；`xkey-authorize` 结构上也只冻修复链，但复核所需的写面判据**不存在**（AC-014：写面纪律 11/248 份散文、`write_scope` 生产零命中）⇒ 当前不具备"延后 + 自动复核"的落地条件。
- **I-3**：`stage-close` 的延后**没有代价也没有收益**：它的 pending 窗口内通常无任何工作（JC 实测 136.4h 窗口内 0 个 tool 事件），而它挡住下一 stage ⇒ 延后 = 纯损。这与 RQ-10「`stage-close` 是可自动化的那一类」互补：它该被**尽快答**，不该被延后。
- **I-4**：延后机制若只以 gate 为触发器，会漏掉三类**无门停摆**（roadmap-writer 用尽 `:545-546`、roadmap/gate 文件损坏 `:205-212`/`:335-337`）——这些在夜里同样永久停住，且面板上没有门可看（RQ-8 F1 表末）。

## 结论 → 决策映射

### 支撑 AC-025 第 (2) 类「非阻塞可延后复核」

判据应为**三项合取**，缺一不可：

1. **延后期间不挡任何正在工作的 key**（否则不是"延后"，是"停机"）；
2. **延后期间不释放任何不可逆动作**（延后 = 不答 = 不改状态；危险只在窗口内其它工作流与复核时刻的答案）；
3. **延后不会在 stage 末变成硬阻塞**（否则"延后到 stage 末"自相矛盾）。

按此判据逐门落位：

| gate kind | 满足 1 | 满足 2 | 满足 3 | 结论 |
|---|---|---|---|---|
| `stalled` | ✅（其余 key 继续，实测 291/1139 个 tool 事件） | ✅（延后不放行；但**复核时的 approve** 会放行"额外一轮 + 写代码 + token"，reject 会放行 `closed-legacy`） | ❌（key 非终态 ⇒ `_stage_closure:629-631` 挡收口） | **需 `延后 + 补偿`**（CC-4/CC-5/CC-6/CC-8；且复核必须人答，因为 approve 语义 = "人已带外修复"，RQ-10 F1f） |
| `budget-exhausted` | ✅ | ✅（`allowed` 两向都有界：`:990` 第二次直接 stall，`:2228-2239` reject 只转 stalled） | ❌（同 `stalled`，且**更隐蔽**：不写 key-status） | **最干净的延后候选**，但仍需 CC-4/CC-8（时间上界 + age 可见） |
| `xkey-authorize` | ✅（只冻修复链） | ✅（延后阻断写） | ⚠️（不直接影响 stage 收口，除非 source key 因此停滞） | **`延后 + 硬补偿`**，且**前置 = AC-014 的写面机器判定**；0 样本 ⇒ 只能影子模式 |
| `stage-confirm` | ❌（整条 roadmap 停） | — | — | **绝不能延后**（延后 ≡ auto-approve 整 stage） |
| `stage-close` | ❌（下一 stage 永停） | — | — | **绝不能延后**（应尽快答；窗口内无收益） |
| `goal-change` | ❌（全停） | — | — | **绝不能延后**（且 reject 是 no-op，`:2105-2111`） |

### 支撑 AC-027「非阻塞延后复核机制」的四项

- **补偿控制** = F4 的 CC-1 … CC-8（每条有实现面与可检测信号）。最小集：CC-4（上界）+ CC-5（reject/`closed-legacy` 不自动）+ CC-6（credits 上界）+ CC-7（消费记录持久 + stage 单调）+ CC-8（age/塌缩信号）。
- **批量形态** = 归 RQ-14；边界：gate 12 字段 + dossier + timeline（`gates.py:68-81`、`conductor.py:722-750`、`timeline.py:67-85`）。
- **延后上限** = 时间上界（`expires_at`，需扩 schema `gates.py:68-81`）**或** 触发式上界（"该 stage 内其它 key 全部终态" → 立即复核）。数据依据：F3 —— 已收口 stage 墙钟 n=4 / p50 36.56h / max 150.53h；门→stage 收口视界 n=11 / p50 24.48h / max 145.99h；仍在跑的 stage ≥211h；JC pending stage-close 203.93h。**上限不能取自 p50，必须显式取上界并配 age 告警**（CC-8）。
- **可检测信号** = CC-8 四项（age 进面板/doctor；"阻塞面已塌缩"；单 stage 墙钟分位；stage status 回退）。

### 逐条回答决策问题 5（三分边界）

- **绝不能延后**：`stage-confirm`、`stage-close`、`goal-change`。理由：三者都是**结构性全局阻塞**（`_stage_activation:434-451` / `_stage_closure:633-634` + `_ensure_next_stage_gate:409-431` / `tick:2101-2103`），不答就是永久停；其中前者与 `goal-change` 的"延后"在代码上等价于自动应答（`stage-confirm` 放行整 stage 的写面与 token，`goal-change` 的 reject 还是 no-op）。
- **延后本身安全的（相对）**：`stalled`、`budget-exhausted`、`xkey-authorize` —— 仅就"延后这一动作"而言（不答不改变任何状态、不放行任何动作）；**没有任何一类门可以无条件延后**。关键限定：`stalled`/`budget-exhausted` 的**复核答案**会放行 IA-1/5/6/7/8，所以"延后安全"≠"复核安全"。
- **需要「延后 + 补偿」**：`stalled`（CC-5 禁 reject 自动、CC-6 credits 上界、CC-8 age/塌缩信号，且复核必须人答）、`budget-exhausted`（CC-4 时间上界、CC-8，它是最干净的候选）、`xkey-authorize`（CC-1 写面声明、CC-3 动作队列化，前置 AC-014）。

## 数据缺口

1. **样本只有 3 个项目、1 个快照**：MW 无 autopilot 数据；FM/E2/JC 的窗口都在同一批夜跑节奏上。单 stage 墙钟只有 **n=4** 个已收口样本，不能当分布用。
2. **JC 的 stage 边界被重放污染**：`gate-0001` 被重放导致 stage 1 由 `closed` 退回 `running`（F5）⇒ JC 的 stage 时长/阶段边界数字必须随该污染一起读；JC stage 1 的 open 时刻只能由 gate 文件 mtime 推定（更早 timeline 代已剪）。
3. **三类门 0 样本**：`budget-exhausted` / `xkey-authorize` / `goal-change`（后者 JC 仅 1 条）⇒ 它们的"延后 + 补偿"无法用生产数据验证；`reject` 路径 34 条里 0 条，`closed-legacy` 的收益/风险都无历史可估（RQ-10 缺口 3/4 同源）。
4. **窗口内动作数是下界**：`trace.log` 只记录 tool 调用；`bash` 内的真实写面不可解析（`python -c`/`node -e` 里的写、`Remove-Item` 之外的重定向写都看不出来）。F2 的窗口内数字因此是**下界**。
5. **没有"窗口内被延后门的证据文件是否被改"的直接测量**：本卡只测到"窗口内有大量写/构建/删除"，没有逐文件把改动对齐到被延后门的证据（需要逐文件 mtime + `/VERIFY` 行级绑定）。
6. **`xkey-authorize` 的延后是否真的拖慢 source key 推进：无法判定**。需要什么证据：影子模式（`xkey_repair=true` 的受控项目）下记录"ticket pending 时长 × source key 的 advance 失败次数/停滞"；或一个可复现的最小 cross-key 红场景。
7. **`answered_by` 不可机器判**（自由文本）、**`MonitorGate` 无 `created_at`**（`monitor.ts:89-96`）、**`mw doctor` 无 gate 节** ⇒ TTL 与"人答 vs 机器答"当前都无结构化载体（RQ-8 F6 / RQ-10 F5 同结论）。
8. **未做**：没有把"延后窗口内其它 key 的写"与"被延后 key 的证据新鲜度"做因果绑定（需要一个"证据绑定 sha"字段，当前不存在）。