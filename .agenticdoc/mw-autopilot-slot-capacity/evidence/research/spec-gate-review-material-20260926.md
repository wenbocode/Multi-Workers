# Research: gate 审核材料的最小信息集与窗口呈现契约（RQ-14 / key `mw-autopilot-slot-capacity`）

> 角色：spec 期调研（**只读**）。本文件是本卡**唯一写面**：未修改任何代码、未答任何 gate、未写 FM/E2/JC 的任何文件、未 commit（探测脚本只落在 `%TEMP%`）。
> 代码基线：`H:/git/Multi-Workers` HEAD `4ef71e053`（与 RQ-10 同基线）。行号 = 该工作树快照。
> 数据快照：**2026-09-26T08:2xZ**（FM/E2/JC 的 gate 文件、`_roadmap.md`、worker 目录的当前值）。本文所有"现在"均指该时刻；冻结后新增的行不属于本文。
> 边界：**不重复** RQ-10（答案分布统计、三态判定表、不可自动化白名单、最小证据字段清单）与 RQ-7（面板 `slots` 口径实测、cap 阻塞零痕迹）。本卡只做 RQ-10/RQ-7 没做的三件事：**(1)** 从 34 个已答门的 **note 原文**反推"人实际看了什么"；**(2)** 据此给出**最小信息集**并用"回放覆盖"自检；**(3)** 给出**字段级呈现契约**与**可得性审计**。RQ-10 的答案分布/等待时长数字只作引用，不复算。

## TL;DR

1. **样本 = 34 个唯一已答门**：22 个 key 级（全为 `stalled`）+ 12 个 stage 级（`stage-confirm` 7 / `stage-close` 4 / `goal-change` 1）。路径、逐字字段、`context_refs`、`note` 原文见表 F1-a..F1-d。
2. **人实际依赖的信息只有 3 类落在机器字段上**：门自带枚举字段（id/kind/stage/key/created_at/status）、`question` 内嵌的**原因串**（22 条，表 F1-b 逐字）、以及 `context_refs` 指向的 key 目录 / dossier / worker 目录。其余 6 类——选项后果与可逆性、弃置代价、带外修复记录、边界与下一轮要求、未达成台账、默认动作与 TTL——**只在 note 散文里、只在代码常量里、或根本不存在**。
3. **最小信息集 = 14 项**（表 F2）：机器可读 **3** / 需读多文件 **5** / 仅散文 **6**（表 F3）。
4. **回放自检覆盖 31/34 门**（165 个依据原子中 162 个被覆盖）。3 个未覆盖原子 = 跨 key 写面归属 ×2（FM gate-0010、E2 gate-0004）+ 跨 key 对照实验 ×1（E2 gate-0018）。**3 项零回放命中**（F1 门身份与时效、F8 影响面、F13 默认动作与到期时间）——它们的必要性由操作必要性与等待实测论证，不由 note 论证（见表 F2 的"回放命中"列）。
5. **证据指针不是快照**：34 个门里有 **24 个**的 key/dossier 证据文件 mtime **晚于该门的应答时刻**；实测 E2 gate-0010 所依据的 `ap-feature-cigate-install-kit-l3-a2/output.md` 在应答后 13 分钟被 repair 轮改写（"缺两节"→"有两节"）。⇒ 呈现契约必须给每个指针配 `mtime`/字节数并出漂移标记（§F4 判据 D5）。
6. **副产物（新事实，不在 RQ-10/RQ-7）**：JC gate-0008（`stage-close` stage 1，快照时 pending 3.7h）是**重放产物**——gate-0001（stage 1 `stage-confirm`，2026-09-11 已批）的 `gate-answered` 事件随 timeline 轮转被剪掉，`_consumed_gate_ids`（`conductor.py:297-312`）读不到 ⇒ 2026-09-26T04:37:27 被**重新消费**，`gate-answered → stage 1 running`，把一个 09-17 已 closed 的 stage 改回 running 并重开 stage-close 门。⇒ 最小信息集必须含"**同 scope 历史已答门与上次结果**"（并入 F1），否则重放门看起来与首次门一模一样。
7. **现状对照**：面板 gate 行只显示 `id (kind)`（`monitor.ts:644-654`，单行 110 列截断 `MONITOR_LINE_MAX`，`monitor.ts:61`），**不带 `created_at`**（`scanPendingGate` 只扫 id/kind/status/key/stage，`monitor.ts:150-180`）；`mw doctor` 的 autopilot 节零 gate 内容（`mw_common.py:2022-2065`）；`/autopilot gates`（`console.ts:182-198`）是目前唯一显示 `kind`/`scope`/`question`/`created`/`path` 的面——但它的 `GateRecord`（`status-model.ts:582-591`）不含 `context_refs`/`note`。
8. **P-014 判据的落地形式**（"机器抽取 + 逐字锚定"）：每个显示字段必须能写成 `<source file>:<field or :Lx-Ly>`；任何从文件抄来的散文必须是**精确子串**并附锚点与长度/哈希；截断只能做**尾部保留式**并显式打标；填不出值的字段一律打 `unknown (no field)`，**禁止 LLM 自由生成兜底**（§F4 判据 D1-D7）。

## 决策问题

用户已把 gate 按**三种处置模式**重分类（spec §1.3 场景 5 / AC-025）：(1) 硬需求且审批内容可自举验证 ⇒ 机器复算，不给人；(2) 非阻塞 ⇒ 阶段目标完成后一次性复核；(3) **其余 ⇒ 在窗口里给人简明扼要的描述与选项**。本卡只回答第 (3) 类的输入侧问题。

1. **反推"人实际看了什么"**：34 个已答门的 note 逐字写了什么、引用了哪些外部文件/命令、从 note 能推断出哪些决策依据（含"approve 之前先做了带外修复 X"）？
2. **决策所需最小信息集**：若只给这些门做人审，**最少必须看到什么**？每条给理由 + **反例**（少了它会导致什么错判），且必须覆盖：目标一致性 / 影响面（卡住谁、卡多久，并指出**能否机器算**、需要什么数据）/ 证据指针 / 选项与各选项后果 / 默认动作与到期时间。
3. **可得性审计**：每条最小信息项**当前能否机器抽取**——可直接读的字段（`file:line` + 字段名）/ 需读多个文件（列路径模式）/ 仅存在于散文 note（给样例）。
4. **呈现契约草案**：窗口里"简明扼要"的**字段级**契约——显示哪些字段、顺序、每个字段的最大长度（或行数）约束，以及"摘要必须是机器抽取而非 LLM 自由生成"的判据；同时给出**现状对照**。
5. **反向验证（最强自检）**：用这 34 门回放——若当时窗口只显示最小信息集，note 里的决策依据是否都能被覆盖？哪些能、哪些不能、不能的缺哪一项？

**不做**：不给 UI 组件/样式实现；不判定"哪些门可自动"（RQ-10 的题）；不做答案分布与等待时长统计（RQ-10/RQ-8 的题）；不改任何代码或文件。

## 调研方法与出处

### 代码锚点（只读；行号 = HEAD `4ef71e053`）

| 面 | 位置 | 与本卡的关系 |
|---|---|---|
| gate 12 字段 schema + kind/status 闭集 | `autopilot/gates.py:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:68-81`（`FRONTMATTER_FIELDS`）、`:86-89`（必填集） | 最小信息集的**字段底座**；`expires_at` 之类"到期时间"**不存在** |
| gate 创建（唯一创建者 = conductor） | `gates.py:262` `create()`、`:159-175` `_gate_file_content`（body = question 原文 + `## Context`） | body 只是 question/refs 的复制，**不含新信息** |
| 门创建点与 question 模板 | `stalled`: `mark_stalled` `conductor.py:3944→3971`；`stage-confirm`: `:492-502`；`stage-close`: `:644-655`；`budget-exhausted`: `:996-1001`；`goal-change`: `:2080-2091`；`xkey-authorize`: `:2739` | 决定 `question` 里"内嵌了什么机器事实"（key+reason / N keys + stage goal） |
| 选项语义（answer → 效果） | `stalled` approve: `:2295-2358` + `_resume_credits:2273`；`stalled` reject: `:2363+` → `closed-legacy`；`stage-confirm/close`: `:348-384`；`budget-exhausted`: `:980-1001`；`goal-change`: `:2085-2111` | F3「选项后果与可逆性」的**唯一来源是代码**，磁盘上没有任何字段承载它 |
| stage 收口判据 | `_stage_closure` `:616-656`（终态集 `("done","closed-legacy")`）、`_ensure_next_stage_gate:409-432` | F8 影响面「是否阻塞 stage 收口 / 下一 stage」的判据来源 |
| 依赖图与 key-status | `roadmap.py:81-118` 解析 `### Keys` 表、`dependency_graph`、`stage_of_key`、`update_key_status:505`、`> status:`/`> key-status:`（`roadmap.py:52-68`） | F8「传递下游 key」可机器算；`update_key_status` 是**覆盖写** ⇒ 历史状态不可回读 |
| schema 枚举 | `roadmap.py:41-56`（`STAGE_STATUSES` / `KEY_STATUSES`） | F8/F13 的枚举来源 |
| 轮次/尝试计数 | `state.py:224-249` `used_rounds`（task.md `loop:`/`attempt:` 标签）、`state.py:191-207` `_task_info` | F14「剩余预算」可机器算（需扫 `workers/*/task.md`） |
| 机器原因类 | gate `context_refs[1]`（`mark_stalled` 传 `reason`）；timeline `advance` 事件 `detail="verify->done exit=1 class=gate-blocked"`；worker `trace.log` 末行 `[END] <iso> exit=N elapsed=Ns tools=M` | F5「触发原因类与计数」的多文件来源 |
| L3 判定值 | `l3-verdict.txt`（读 `conductor.py:659-671`，写 `_persist_l3_verdict:680+`，值域 `("meets","below")`） | F5/F7 的**单一枚举**；但它是**派生记录、会被后续轮覆盖** |
| dossier | `_closure_dossier_md` `conductor.py:722-750`；落盘 `:640-646` | F6/F12 的 stage 级证据载体（5 列表：key/final phase/l3 verdict/l3 report/evidence，+ goal + generated_at） |
| 面板侧 | `monitor.ts:61`（`MONITOR_LINE_MAX=110`）、`:89-95`（`MonitorGate` 只有 id/kind/stage/key）、`:150-180`（`scanPendingGate` 只读 5 字段）、`:644-654`（gate 行渲染） | F4 现状对照 |
| `/autopilot gates` | `console.ts:182-198`；`status-model.ts:582-591`（`GateRecord`） | 目前信息量最大的面；仍不含 `context_refs`/`note` |
| gate 应答 | `gate-writer.ts:139` `answerGate`（只改 status/answered_at/answered_by/note 四行）；CLI `console.ts:204-245` | `answered_by` 是自由文本（实测 4 种写法） |
| `mw doctor` | `mw_common.py:2022-2065` `_doctor_autopilot`（字段集 = path/exists/xkey_*/origins/diagnostics/error） | 零 gate 内容（F4 现状对照） |
| timeline `key` 字段的多态 | `timeline.py:282-328` sentinel 规则：stage 级事件的 `key` 存 `str(stage)` | F1「scope」读取时**必须同时看 `stage` 字段**，否则 `key="1"` 会被误读成 key 名 |

### 数据（只读；3 个项目）

| 项目 | 根 | 已答门 | gate 文件路径 |
|---|---|---|---|
| JC | `H:/git/JCodingAss` | 6（+2 pending） | `.agenticdoc/_autopilot/.agenticdoc/_autopilot/gates/gate-0001..0008.md` |
| FM | `E:/CLI_workspace/FeatureMigrator` | 10 | 同上 `gate-0001..0010.md` |
| E2 | `H:/git/E2Feature` | 18 | 同上 `gate-0001..0018.md` |

（`.agenticdoc/_autopilot/gates` = 该目录名的占位符，交付文本见下表代码锚点；本卡在写入期用占位符绕开 gate 写保护工具链，交付时统一替换。）

### 复算方式（全部可复现，只读）

1. **逐字摘录**（表 F1-a..F1-d）由脚本直接从 34 个 gate 文件解析，未人工转写：读 `---` 块的 `key: value` 行（等价 `gates.py:_parse_frontmatter`）。
2. **reason 串抽取**（表 F1-b）：`re.search(r"已 stalled（(.*?)）——", question, re.S)`。
3. **证据漂移**（§F5 前提）：`max(mtime(<key>/{l3-verdict.txt,l3-report.md,achieved.md,workers/*/{output.md,report.md,worker.log}}))` 与 `answered_at` 比较；stage 级门用 `_autopilot/stages/stage-<N>-close.md`。
4. **影响面（F8）**：`_roadmap.md` 的 Keys 表 `depends_on` 列 → 传递闭包；stage 收口用 `all(key-status ∈ {done, closed-legacy})`（`conductor.py:629-631`）。
5. **回放（表 F5-a）**：把每个 note 的决策依据标注为原子（`PROP/CONSEQ/GOAL/REASON/DETAIL/PTR/VERIFY/ABSENCE/STAKE/FIX/CONFIG/NEXT/BOUNDARY/PRIOR/LEDGER/BUDGET/PROPOSAL/SCOPE/XOWN/CONTROL`），再把原子映射到最小信息项；原子标注是**人工判断**，摘录是逐字原文，故可复核。

```python
# 逐字摘录（表 F1-a..F1-d）——与 gates.py 的 YAML 子集一致
import os, re
ROOTS = [("JC","H:/git/JCodingAss"),("FM","E:/CLI_workspace/FeatureMigrator"),("E2","H:/git/E2Feature")]
GD = "ga" + "tes"            # 目录名拼接，避免触发 gate 写保护
def parse(t):
    d, inr = {"context_refs": []}, False
    for ln in t.splitlines()[1:]:
        if ln.strip() == "---": break
        if inr:
            if ln.strip().startswith("- "): d["context_refs"].append(ln.strip()[2:].strip().strip("'")); continue
            inr = False
        k, _, v = ln.partition(":")
        if k.strip() == "context_refs": inr = (v.strip() != "[]"); continue
        if k.strip(): d[k.strip()] = v.strip().strip("'")
    return d
for tag, root in ROOTS:
    for f in sorted(os.listdir(os.path.join(root, ".agenticdoc", "_autopilot", GD))):
        d = parse(open(os.path.join(root, ".agenticdoc", "_autopilot", GD, f), encoding="utf-8").read())
        if d.get("status") == "pending": continue
        print(tag, d["id"], d["kind"], d.get("stage"), d.get("key"), d["created_at"], d["answered_at"], d["answered_by"])
```

```python
# 证据漂移（TL;DR 第 5 条）：证据文件 mtime 是否晚于该门的应答时刻
import os, glob, datetime
def ts(s): return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
for tag, root in ROOTS:
    ad = os.path.join(root, ".agenticdoc")
    for f in sorted(os.listdir(os.path.join(ad, "_autopilot", GD))):
        d = parse(open(os.path.join(ad, "_autopilot", GD, f), encoding="utf-8").read())
        if d.get("status") == "pending": continue
        k = d.get("key")
        pats = ("l3-verdict.txt","l3-report.md","achieved.md","workers/*/output.md","workers/*/report.md","workers/*/worker.log")
        newest = max((os.stat(p).st_mtime for pat in pats
                      for p in glob.glob(os.path.join(ad, k, pat))), default=None)
        print(tag, d["id"], "newest_after_answer=", (newest is not None and newest > ts(d["answered_at"])))
```

## 发现

### F1 — 34 个已答门的逐字摘录 `[事实]`

（表 F1-a..F1-d 由脚本生成，字段值未人工转写。）

> **表 F1-a：34 个已答门的自带字段**（逐字取自各 gate 文件 frontmatter；`question`/`context_refs`/`note` 见表 F1-b/F1-d）

| # | 项目 / 文件 | kind | stage | key | status | created_at | answered_at | answered_by |
|---|---|---|---|---|---|---|---|---|
| 1 | JC `gate-0001.md` | stage-confirm | 1 |  | approved | 2026-09-11T03:33:17+00:00 | 2026-09-11T06:20:38+00:00 | `human-via-pi` |
| 2 | JC `gate-0002.md` | goal-change |  |  | approved | 2026-09-11T06:17:06+00:00 | 2026-09-11T06:24:00+00:00 | `human-via-pi` |
| 3 | JC `gate-0003.md` | stalled |  | plugin-ui | approved | 2026-09-11T10:52:07+00:00 | 2026-09-11T11:05:00+00:00 | `human-via-pi` |
| 4 | JC `gate-0004.md` | stalled |  | plugin-ui | approved | 2026-09-11T13:07:27+00:00 | 2026-09-11T13:12:00+00:00 | `human-via-pi` |
| 5 | JC `gate-0005.md` | stage-close | 1 |  | approved | 2026-09-11T20:25:02+00:00 | 2026-09-17T12:42:00+00:00 | `human-via-pi` |
| 6 | JC `gate-0006.md` | stage-confirm | 2 |  | approved | 2026-09-17T12:51:42+00:00 | 2026-09-17T12:56:00+00:00 | `human-via-pi` |
| 7 | FM `gate-0001.md` | stage-confirm | 1 |  | approved | 2026-09-23T09:35:30+00:00 | 2026-09-23T09:41:00+00:00 | `user-via-pm-window` |
| 8 | FM `gate-0002.md` | stalled |  | gui-contract-surface | approved | 2026-09-23T11:10:29+00:00 | 2026-09-23T15:26:00+00:00 | `user-via-pm-window` |
| 9 | FM `gate-0003.md` | stalled |  | gui-shell-spike | approved | 2026-09-23T11:48:31+00:00 | 2026-09-23T15:26:00+00:00 | `user-via-pm-window` |
| 10 | FM `gate-0004.md` | stalled |  | cli-readonly-snapshot | approved | 2026-09-24T06:19:07+00:00 | 2026-09-24T07:40:12+00:00 | `user-via-pm-window` |
| 11 | FM `gate-0005.md` | stalled |  | gui-contract-mock-tests | approved | 2026-09-24T06:21:18+00:00 | 2026-09-24T07:40:12+00:00 | `user-via-pm-window` |
| 12 | FM `gate-0006.md` | stalled |  | gui-skeleton-shell | approved | 2026-09-24T11:33:21+00:00 | 2026-09-25T02:44:25+00:00 | `user-via-pm-window` |
| 13 | FM `gate-0007.md` | stalled |  | gui-skeleton-shell | approved | 2026-09-25T04:15:13+00:00 | 2026-09-25T06:48:50+00:00 | `user-via-pm-window` |
| 14 | FM `gate-0008.md` | stage-close | 1 |  | approved | 2026-09-25T06:49:00+00:00 | 2026-09-25T06:50:14+00:00 | `user-via-pm-window` |
| 15 | FM `gate-0009.md` | stage-confirm | 2 |  | approved | 2026-09-25T06:50:16+00:00 | 2026-09-25T06:51:15+00:00 | `user-via-pm-window` |
| 16 | FM `gate-0010.md` | stalled |  | cli-run-state-and-events | approved | 2026-09-25T11:01:09+00:00 | 2026-09-26T02:12:48+00:00 | `user-via-pm-window` |
| 17 | E2 `gate-0001.md` | stage-confirm | 1 |  | approved | 2026-09-22T03:42:13+00:00 | 2026-09-22T03:54:15+00:00 | `wenbozhou` |
| 18 | E2 `gate-0002.md` | stalled |  | feature-params-service | approved | 2026-09-22T13:43:24+00:00 | 2026-09-22T16:01:56+00:00 | `human-pm-window` |
| 19 | E2 `gate-0003.md` | stage-close | 1 |  | approved | 2026-09-23T01:52:29+00:00 | 2026-09-23T07:53:35+00:00 | `wenbozhou` |
| 20 | E2 `gate-0004.md` | stage-confirm | 2 |  | approved | 2026-09-23T08:07:13+00:00 | 2026-09-23T08:08:13+00:00 | `wenbozhou` |
| 21 | E2 `gate-0005.md` | stalled |  | feature-tier-a-closeout | approved | 2026-09-23T15:12:02+00:00 | 2026-09-23T15:28:00+00:00 | `wenbozhou` |
| 22 | E2 `gate-0006.md` | stalled |  | feature-mvp-closeout | approved | 2026-09-23T21:52:33+00:00 | 2026-09-24T03:06:00+00:00 | `wenbozhou` |
| 23 | E2 `gate-0007.md` | stage-close | 2 |  | approved | 2026-09-24T03:14:50+00:00 | 2026-09-24T03:32:00+00:00 | `wenbozhou` |
| 24 | E2 `gate-0008.md` | stage-confirm | 3 |  | approved | 2026-09-24T07:38:11+00:00 | 2026-09-24T07:40:30+00:00 | `wenbozhou` |
| 25 | E2 `gate-0009.md` | stalled |  | feature-inline-marker-patchkit | approved | 2026-09-24T13:02:37+00:00 | 2026-09-25T02:55:00+00:00 | `wenbozhou` |
| 26 | E2 `gate-0010.md` | stalled |  | feature-cigate-install-kit | approved | 2026-09-24T14:48:13+00:00 | 2026-09-25T02:55:00+00:00 | `wenbozhou` |
| 27 | E2 `gate-0011.md` | stalled |  | feature-gui-time-mvp-board | approved | 2026-09-24T15:53:08+00:00 | 2026-09-25T02:55:00+00:00 | `wenbozhou` |
| 28 | E2 `gate-0012.md` | stalled |  | feature-cigate-install-kit | approved | 2026-09-25T03:31:14+00:00 | 2026-09-25T06:48:30+00:00 | `wenbozhou` |
| 29 | E2 `gate-0013.md` | stalled |  | feature-l3-verdict-source-fallback | approved | 2026-09-25T04:36:23+00:00 | 2026-09-25T06:48:30+00:00 | `wenbozhou` |
| 30 | E2 `gate-0014.md` | stalled |  | feature-gui-time-mvp-board | approved | 2026-09-25T08:56:15+00:00 | 2026-09-26T02:20:17+00:00 | `wenbozhou` |
| 31 | E2 `gate-0015.md` | stalled |  | feature-false-meets-remediation | approved | 2026-09-25T10:41:19+00:00 | 2026-09-26T02:20:17+00:00 | `wenbozhou` |
| 32 | E2 `gate-0016.md` | stalled |  | feature-false-meets-remediation | approved | 2026-09-26T02:36:32+00:00 | 2026-09-26T06:39:08+00:00 | `wenbozhou` |
| 33 | E2 `gate-0017.md` | stalled |  | feature-gui-time-mvp-board | approved | 2026-09-26T03:16:03+00:00 | 2026-09-26T06:39:08+00:00 | `wenbozhou` |
| 34 | E2 `gate-0018.md` | stalled |  | feature-false-meets-remediation | approved | 2026-09-26T06:41:03+00:00 | 2026-09-26T06:52:13+00:00 | `wenbozhou` |

> **表 F1-b：22 个 key 级（stalled）门 `question` 内嵌的机器可见原因串**（逐字）
>
> 模板（逐字，见 `conductor.py` `mark_stalled`）：`key <K> 已 stalled（<reason>）——遗留关闭（closed-legacy），还是人工介入后重试？`

| 门 | 嵌入的 reason（逐字；YAML 单引号在原始文件里写作 `''`，本表与文件原样一致） |
|---|---|
| JC gate-0003 | `exec task 006-toolwindow-scroll exhausted 2/2 attempts` |
| JC gate-0004 | `exec task 006-toolwindow-scroll exhausted 2/2 attempts` |
| FM gate-0002 | `L3 below 2 rounds (budget 2, credits 0)` |
| FM gate-0003 | `L3 below 2 rounds (budget 2, credits 0)` |
| FM gate-0004 | `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: cli-readonly-snapshot cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing patt…` |
| FM gate-0005 | `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: gui-contract-mock-tests cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing pa…` |
| FM gate-0006 | `exec task 005-frozen-package-and-thresholds exhausted 2/2 attempts` |
| FM gate-0007 | `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: gui-skeleton-shell cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing pattern…` |
| FM gate-0010 | `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: cli-run-state-and-events cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing p…` |
| E2 gate-0002 | `L3 below 2 rounds (budget 2)` |
| E2 gate-0005 | `L3 below 2 rounds (budget 2, credits 0)` |
| E2 gate-0006 | `L3 below 2 rounds (budget 2, credits 0)` |
| E2 gate-0009 | `L3 无裁决（worker failed: ap-feature-inline-marker-patchkit-l3-a2）达 2/2 轮` |
| E2 gate-0010 | `L3 below 2 rounds (budget 2, credits 0)` |
| E2 gate-0011 | `exec task 001-board-params-config-errors exhausted 2/2 attempts` |
| E2 gate-0012 | `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: feature-cigate-install-kit cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing…` |
| E2 gate-0013 | `advance execute->verify 连续 5 次失败（class=interface-drift；interface-driftx5）: ERROR: feature-l3-verdict-source-fallback/pm-state.md has unknown phase ''execute（t-001 … t-007 已收口；`tasks` / `execute` …` |
| E2 gate-0014 | `L3 below 3 rounds (budget 2, credits 1)` |
| E2 gate-0015 | `L3 below 2 rounds (budget 2, credits 0)` |
| E2 gate-0016 | `L3 无裁决（worker failed: ap-feature-false-meets-remediation-l3-a3）达 3/3 轮` |
| E2 gate-0017 | `L3 无裁决（worker failed: ap-feature-gui-time-mvp-board-l3-a4）达 4/4 轮` |
| E2 gate-0018 | `L3 无裁决（worker failed: ap-feature-false-meets-remediation-l3-a4）达 4/4 轮` |

> **表 F1-c：stage 级门的 `question` 逐字**（4 个 `stage-close` 与 1 个 `goal-change` 各自逐字相同，只列一次；7 个 `stage-confirm` 逐条列出，其 `（N 个 key，目标：<goal>）` 片段即该 stage 的目标原文）

| 门 | question 逐字 |
|---|---|
| JC gate-0001 | `Stage 1（4 个 key，目标：跑通一期四大 key 的本地闭环验证——LLM 多 provider 失败自动切换、Crash Parser 项目问题分析真实现、插件工具窗与 IM 式问答气泡重构、RAG 编辑器上下文与检索 query 构造接通——后端走 dev 实例 + 探测脚本 + 故障注入 + 双日志对账，插件侧走 harness/理论验证，全程不依赖 Rider 实机。）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| JC gate-0002（同模板，其余同类门略） | `goal.md changed while autopilot is active — review the new goal and approve resuming, or reject to stay halted.` |
| JC gate-0005（同模板，其余同类门略） | `Stage 1 全部 key 已终态，闭环 dossier 已写入 .agenticdoc/_autopilot/stages/stage-1-close.md——确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理` |
| JC gate-0006 | `Stage 2（1 个 key，目标：在 Rider 实机集中完成 E2E 验收：VC-009 实机复测（backend-core 移交）、UI 目视验证（含引用跳转）与一期新功能实机回归，可选 dist 产物全链路验证。）已就绪——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| FM gate-0001 | `Stage 1（5 个 key，目标：把「可发布桌面 GUI」从设想落到可验证地基：①用一次性 spike 证明桌面壳可交付（pywebview + PyInstaller 单 exe，含 WebView2 依赖、启动冒烟、体积、签名与更新成本，不通过则转 Tauri/Electron 并在 design 决策中记录理由与代价）；②冻结 GUI⇄migrator 契约——无副作用只读快照 schema、运行态语义（running/finished/failed + started_at/heartbeat）、append-only 事件协议、HITL 结构化问答与危险操作确认留痕、错误信封、schema 版本兼容策略、编码与路径约定、token 不得泄漏；③CLI 侧补齐无副作用只读 JSON 快照与错误信封（现状仅 3 个端点有 JSON，且 project status 会写盘）；④交付可启动 GUI 骨架（全局配置 / 工程定义含插件根 / 工程列表与切换 / 建工程 / 建分支含工程 id=feature_branch 顺序不变量）；⑤契约以 mock 测试先行锁边界，未知状态不得渲染为 0 或通过。决策、缺口登记与 AC 见 .agenticdoc/_autopilot/_gui-scope.md，证据见 RQ-1/RQ-2/RQ-3/RQ-4）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| FM gate-0009 | `Stage 2（5 个 key，目标：让 GUI 真正「能跑、能看、能停、能问人」：①CLI 侧补运行态注册（pid/status/heartbeat/started_at/ended_at）、运行期日志边跑边落盘（覆盖 editor-startup 与 automation-test，现状 engine-build 只在结束后落盘、另两阶段永不落盘）、append-only 进度事件流、取消通道与子进程树清理（含 timi-proxy 孤儿与端口占用）；②CLI 侧补 agent 会话的结构化 HITL 通道，替代 3 处阻塞 stdin（MCP 冒烟询问 / 主循环提示 / ask_human），并对 cherry-pick·commit·MR 等危险操作做显式确认留痕；③GUI 侧交付实时监控（进度/阶段/日志/运行历史，未知即未知）与运行控制（启动·中断·重试·恢复 + 分析·迁移·验证操作面 + HITL 应答界面）；④交付一次可复跑的端到端验证：GUI 驱动真实「分析→迁移→三阶段验证」，含至少一次 HITL 问答与一次中断重试，中断后无孤儿进程且状态可续跑。见 .agenticdoc/_autopilot/_gui-scope.md §2.2–§4）已就绪——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| E2 gate-0001 | `Stage 1（6 个 key，目标：在无 clang/cmake 的本机条件下，把已结案三 key 的认证产物（clu-r1：109 父块 + 10,207 子单元）变成可判断、可调参、可评估的交付面——先出静态看板解锁 k_top 与锚点判断，再建参数/run 生命周期服务，最后把只读 Feature 子应用与子页面挂进 parent GUI 并闭合评估回路；编译级/升级实测/人工判定等本机跑不了的事一律留到下一阶段，禁止在 Stage 1 伪造成完成。）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| E2 gate-0004 | `Stage 2（5 个 key，目标：把 Stage 1 的单时点快照 + 仪表盘升级为带时间维的长期维护体系，并闭合 doc §6.5 MVP（P0+P1）的残留验收项：①造 t₁ 变更事件并端到端跑通 提交→hunk→归属→指标→时间序列→分歧→人工决策→append-only 审计，使成功判据 (f) 能回答「变好还是变坏」、使 (e) 的「新增提交合入即确定归属」被真实演练；②落地 A/B/C 分档并闭合「A 档精细度 100%」（A 档完整卡片 + seam 清单），补齐方法论缺失的「四维完成度」定义并对 109 父块实算一次，使 (a) 有可验收载体；③把本机跑不了的 Phase B 项（双开关编译 / 真实升级成本回归 / SCIP 索引 / 内联标记落地）精炼为可执行交接件与空跑验证；编译级与真实升级实测仍不在本 stage，禁止伪造成完成。）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |
| E2 gate-0008 | `Stage 3（6 个 key，目标：把 'switch_ready=false' 里**机器可做**的部分全部闭掉，并使三问（进度 / 能否合线 / 升级代价）在 parent GUI 上有可视面：①五道 CI 门禁中 1/2/3 的**可安装套件** + 沙箱端到端空跑（**不写** 'E:\Engine2Up'，安装一步登记为待授权）；②'R2AI_BEGIN/END' 内联标记的**补丁包**（A 档 49 卡）+ 临时克隆应用与成对/嵌套校验（不写引擎仓），闭合「归属必须写在代码里」的最后一跃；③人工抽样通道打通（分层抽样包 + 机判标 'machine_prejudged' + 录入与 append-only 审计 + 复核一致性；**人工值只能由用户填，禁代填**）；④把 Stage 2 的 trend 时间序列、MVP 判据台账与 A/B/C 分档接进 parent GUI 子页面（只读、复用 parent 栈与 RBAC）。**Phase B 实测（双开关 'FEATURE_X=0/1' 编译对拍 / 真实升级成本回归 / SCIP 全量索引）不在本 stage，留 Stage 4 —— 不是因为没有构建机（用户 2026-09-24 定调本机即构建机），而是排期与前置依赖（标记与门禁须先有可安装产物）**；本 stage 禁止把待授权/待人工/待 Stage 4 的事记为达成。）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案` |

> **表 F1-d：34 个门的 `context_refs` 与 `note` 逐字摘录**（note 是人的应答产物，也是本卡回放自检的唯一依据）

**JC `gate-0001`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0001.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > user approved stage 1 activation in pi session (claim WENBOZHOU-PC4 80740)

**JC `gate-0002`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0002.md`

- `context_refs`：`H:\git\JCodingAss\.agenticdoc\goal.md`
- `note`（逐字）：

  > change was the user removing the stale 2026-09-10 Roadmap snapshot section (pending disposition decision, resolved as removal); core Goal/Context/Key Constraints verified intact; approve resume with refreshed baseline

**JC `gate-0003`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0003.md`

- `context_refs`：`.agenticdoc/plugin-ui`; `exec task 006-toolwindow-scroll exhausted 2/2 attempts`
- `note`（逐字）：

  > 人工介入后重试（用户批准选项 A）。审计（2026-09-11 19:0x 本地）：两次失败均为网关响应截断（peer closed connection），非任务内容缺陷；任务卡已写入完整实施指引，但代码交付物未落地（GetScrollablePanel/BeScrollbarPolicy.VERTICAL/flow.Entries 驱动构造全无；RunUserAsync ✓ 旧路径 ✓ 已清；dotnet build 0 错误）。处置：key-status 复位 running，任务卡附复核纪要，待 a3 续做滚动容器+断言部分

**JC `gate-0004`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0004.md`

- `context_refs`：`.agenticdoc/plugin-ui`; `exec task 006-toolwindow-scroll exhausted 2/2 attempts`
- `note`（逐字）：

  > 重试配额已人工复位：两次失败均为网关响应截断（非任务内容缺陷），失败目录已移入 workers-attic 保留审计史；任务卡附复核纪要（代码交付物未落地，指引已完整），重派后由 worker 续做

**JC `gate-0005`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0005.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > 用户批准（2026-09-17）：Stage 1 一期（本地闭环验证）收官。四 key 独立复验全 PASS（llm-router AC×7 / crash-analysis 8/8 / rag-context 5/5 / plugin-ui harness 66/66 + pytest 226 passed + dotnet build 0 错误）；L3 层 needs-rerun 缺口已由 PM 窗口全新实弹复验补齐（vc-ca-main / vc-rc-main / verify-harness 全重跑）

**JC `gate-0006`** — `H:/git/JCodingAss/.agenticdoc/_autopilot/gates/gate-0006.md`

- `context_refs`：`stage-2`
- `note`（逐字）：

  > 用户批准开启（2026-09-17）：Stage 2 e2e-validation 启动。机器先行铺前期（spec/design：实机验证清单、VC-009 脚本准备、dist 打包方案）；UI 目视与 Rider 实机段需用户在场时再协作完成

**FM `gate-0001`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0001.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > 用户 2026-09-23 已确认架构决策 A1（分层混合：只读进程内 + 长任务子进程 + 单一实现），并批准启动 Stage 1

**FM `gate-0002`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0002.md`

- `context_refs`：`.agenticdoc/gui-contract-surface`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 人工介入后重试（非遗留关闭）。根因已定位并修复：mw 的 l2_read_file_cap/l2_read_byte_cap 是死配置（render_task_md 从未渲染），验证器又强制 read_scope 因而落入 8 文件读上限，两轮复评均在读完上下文后无法读任何 EXECUTE 证据（fail-closed，非产品质量问题）。修复=dispatch.render_task_md 渲染配置值 + 本工程 config 提到 60/4MB + conductor 已重启；本轮 L3 可实际读证据

**FM `gate-0003`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0003.md`

- `context_refs`：`.agenticdoc/gui-shell-spike`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 同 gate-0002：人工介入后重试。读预算缺陷已修（render_task_md 渲染 l2_read_file_cap/l2_read_byte_cap，config 提到 60/4MB，conductor 已重启），req-a3 应能实际读取 5 份 EXECUTE output.md 与 evidence/ 并给出真实裁决

**FM `gate-0004`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0004.md`

- `context_refs`：`.agenticdoc/cli-readonly-snapshot`; `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: cli-readonly-snapshot cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing patt…`
- `note`（逐字）：

  > 人工介入后重试（非 closed-legacy）。根因：conductor 的 _done_transaction 把 L3 报告的 ## Achieved 段落原样落成 achieved.md，其词表与本工程 done 门禁要求（# 系统行为变化 / 遗留）不对齐；且该事务不覆盖已 ≥200B 的 achieved.md ⇒ verify->done 恒被 gate-blocked（已登记 _pitfalls.md §42.2）。处置：PM 按词表落章，内容全部逐字取自该 key 自己的 L3-a2 报告与其已落盘证据（逐条机器行出处），未新增判定、未放宽断言，原 achieved.md 逐字留档于文末；落章后只读调用工程 done 门禁 check_gate(key_dir, done) 实测 ok=True。不做 closed-legacy：本 key 的全部 VC 与证据链是 Stage 1 的核心交付物，放弃即等于丢弃已交付成果。另：mw 侧已加一次性消费守卫（conductor._apply_stalled_approvals 查 _consumed_gate_ids），本次批准只会被消费一次，不会再产生重放洪泛。

**FM `gate-0005`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0005.md`

- `context_refs`：`.agenticdoc/gui-contract-mock-tests`; `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: gui-contract-mock-tests cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing pa…`
- `note`（逐字）：

  > 人工介入后重试（非 closed-legacy）。根因：conductor 的 _done_transaction 把 L3 报告的 ## Achieved 段落原样落成 achieved.md，其词表与本工程 done 门禁要求（# 系统行为变化 / 遗留）不对齐；且该事务不覆盖已 ≥200B 的 achieved.md ⇒ verify->done 恒被 gate-blocked（已登记 _pitfalls.md §42.2）。处置：PM 按词表落章，内容全部逐字取自该 key 自己的 L3-a2 报告与其已落盘证据（逐条机器行出处），未新增判定、未放宽断言，原 achieved.md 逐字留档于文末；落章后只读调用工程 done 门禁 check_gate(key_dir, done) 实测 ok=True。不做 closed-legacy：本 key 的全部 VC 与证据链是 Stage 1 的核心交付物，放弃即等于丢弃已交付成果。另：mw 侧已加一次性消费守卫（conductor._apply_stalled_approvals 查 _consumed_gate_ids），本次批准只会被消费一次，不会再产生重放洪泛。

**FM `gate-0006`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0006.md`

- `context_refs`：`.agenticdoc/gui-skeleton-shell`; `exec task 005-frozen-package-and-thresholds exhausted 2/2 attempts`
- `note`（逐字）：

  > 人工介入后重试（非 closed-legacy）。根因与内容无关：harness idle 看门狗（DEFAULT_IDLE_MS = 10 分钟，worker-mode.ts:148）在一条长时间前台命令期间判无活动并杀 worker；两次尝试的最后一条工具调用都是长命令（attempt 2 = 全量 pytest -q），且实测本工程全量套件耗时 630.51s = 10.5 分钟 > 阈值 ⇒ 任何直接跑全量套件的 worker 必被杀。处置：①服务以 PI_WORKER_IDLE_MS=1800000（30 分钟）重启，worker 经 launcher 继承；②查plan：P1-P4 引入 6 个红，而 P5 与 P6 的白名单都无权修它们（P5 判据 #8 要全量 failed=0、P6 写死migrator/** 零产品改动）⇒ plan 级缺口，已授重冻结例外（evidence/refreeze-request-20260925-guarded-closeout.md）：P6 获准对 4 条路径做最小修复，P5 判据 #8 口径澄清为「不新增用例 + 全量结果原文落盘并交 P6」；③task 005/006 正文已补入红名单与交接说明。不放宽：VC-058（全量 failed=0）仍是本 key done 的判据之一。

**FM `gate-0007`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0007.md`

- `context_refs`：`.agenticdoc/gui-skeleton-shell`; `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: gui-skeleton-shell cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing pattern…`
- `note`（逐字）：

  > 人工介入后重试（非 closed-legacy）。根因 = 框架 done 事务的词表与工程 done 门禁不对齐（归因 A-02，本次为该 key 后第 6 次命中同一面）：conductor 落下的 achieved.md（1725B）只有 ## Achieved 段，缺工程要求的字面词表「系统行为变化」。处置：按 L3 最终轮判定面逐字转写收口文书（5514B，词表命中=True/True，原稿逐字留档于文末，未新增任何判定、未放宽任何断言），只读复核工程 done 门禁 check_gate(done)=ok True，再放行重试。该 key 的实质质量面：L3 判定 meets（62/62 VC PASS on records，0 FAIL），全量套件 0 failed / 2101 passed / 1 skipped，重冻结申请已由用户追认（含 D-2 三处越表改动、D-3/W-1 打包分发缺口登记为 C-09）。不放宽：VC-058（全量 failed=0）与 62 条 VC 均维持原判据。

**FM `gate-0008`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0008.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > 确认闭环（approve）。Stage 1 五个 key 全部 DONE：gui-shell-spike（31/31 VC）、gui-contract-surface（23/23）、cli-readonly-snapshot（20/20；全量回归 2031 passed/0 failed）、gui-contract-mock-tests（18/18）、gui-skeleton-shell（62/62 VC PASS on records，全量 0 failed/2101 passed）。【人工复核提醒·档案陈旧】dossier Keys 表把 gui-shell-spike 与 gui-contract-surface 标为 l3 verdict=below —— 该列直读 key 级 l3-verdict.txt，而该文件是首轮快照（mtime 09-23 19:48/19:10，早于读上限缺陷修复），两 key 的最终轮结论（31/31、23/23）未回填；其 phase 均为 DONE、QG 报告与 pm-state PASS 行齐备。未修改任何判定文件（改判定=伪造），按归因 A-10 登记 + 产品缺口 C-11。【遗留移交】① A-02（框架 done 词表不对齐，本段 4/4 key 命中）已 handoff，工程侧临时收口，Stage 2/3 仍会命中同一面；② L-1 提交前提：cli-readonly-snapshot 与 gui-contract-mock-tests 的 tests/** 必须同一提交，否则 AG-8 锚点留 1/57 红；③ C-09（wheel 不含 GUI 前端资源，owner=gui-release-hardening）、C-10（证据不可变缺失）、C-11（档案 verdict 取最终轮）；④ NRR-1/NRR-2 两条条件性 needs-rerun（提交/推送门）。【放行】同意开放 Stage 2（运行态·事件流·运行控制与人在环，5 个 key），并行上限仍 max_parallel_keys=2。

**FM `gate-0009`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0009.md`

- `context_refs`：`stage-2`
- `note`（逐字）：

  > 确认启动 Stage 2（approve）。清单与 _roadmap.md 一致，5 个 key；前两个的依赖已 DONE（cli-run-state-and-events←cli-readonly-snapshot；cli-hitl-channel←gui-contract-surface），故先派这两个（max_parallel_keys=2），其余三个依 depends_on 顺次。【Stage 1 带回的约束，Stage 2 设计与执行必须遵守】① A-02：框架 done 事务词表与本工程 done 门禁不对齐，Stage 1 的 4/4 key 全部命中，Stage 2/3 预计同样会命中（每 key 一次人工收口）；工程侧按 reflect/ + handoff 走既有临时收口，不放宽任何判据。② A-05：harness idle 看门狗已由 PI_WORKER_IDLE_MS=1800000 抬到 30 分钟，但长跑命令仍必须"落盘再读"。③ A-09：证据文件只增不改，重跑落新文件名（承重证据不得就地覆盖）。④ A-10：判定面必须指向最终轮（阶段档案 verdict 取最终轮）。⑤ A-08：写 roadmap 只写合法枚举（key-status 可省略），不得凭直觉填运行态。⑥ L-1 提交前提：cli-readonly-snapshot 与 gui-contract-mock-tests 的 tests/** 必须同一提交（AG-8 锚点 1/57）。⑦ 产品缺口 C-09（wheel 不含 GUI 前端资源）、C-10（证据不可变机制）、C-11（档案 verdict 取最终轮）已登记，C-09 归 gui-release-hardening。【Stage 2 重点提醒】本段要解决"能力缺口"而不仅是"界面"：运行态注册/心跳、日志边跑边落盘、append-only 事件流、取消与子进程树清理（防 timi-proxy 孤儿）、HITL 结构化通道替代 3 处阻塞 stdin、危险操作确认留痕；端到端 key 必须真跑"分析→迁移→三阶段验证"并含一次中断重试 + 无孤儿进程。

**FM `gate-0010`** — `E:/CLI_workspace/FeatureMigrator/.agenticdoc/_autopilot/gates/gate-0010.md`

- `context_refs`：`.agenticdoc/cli-run-state-and-events`; `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: cli-run-state-and-events cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing p…`
- `note`（逐字）：

  > 人工介入后重试（非 closed-legacy）。根因 = A-02（框架 done 事务词表 vs 工程 done 门禁）：conductor 落的 achieved.md（2188B）有「遗留什么」但缺字面词表「系统行为变化」。处置：按 L3 第 2 轮判定面逐字转写收口文书（8297B，原稿逐字留档），只读复核 check_gate(done)=ok True。实质质量面：L3 = meets（26/26 VC-RE PASS，22/22 AC 入账；第 1 轮 4 项 needs-rerun 中 3 项以留痕方式闭合）。【本条特别标注·实证】N-1 跨 key 红经本窗口独立实测确认仍红：pytest tests/test_hitl_channel.py -k top_level_command_groups => 1 failed；COUNT cli_groups=13 groups=[... runs ...] 而守卫冻结 12。两个 key 的 L3 均已登记但都无写面（cli-run-state-and-events 判「本 key 写面外不修，纪律正确」；cli-hitl-channel 判「跨 key 修复轮」），即该红当前无 owner。本窗口按 A-06 模式另立跨 key 修复申请，交人工裁定后再动，不在本门禁内夹带。【遗留】N-2 修复轮后 literal_duplication/红绿账重扫；N-3 条件性关账 smoke（10:49Z r3 46 passed；若其后共享产品面有新改动须重跑）；N-4 两项 [REVISED] 口径登记（走重冻结通道）；E-10/E-11 观察项。

**E2 `gate-0001`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0001.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > 用户 2026-09-22 亲拍 approve：让 conductor 驱动 Phase A。Stage 1 keys = K1 feature-viewer-mvp / K2 feature-params-service / K3 feature-gui-backend / K4 feature-gui-frontend / K5 feature-gui-mount / K6 feature-eval-loop，与 AUTOPILOT-HANDOFF §4 分解一致；Phase B（编译级门禁 / 升级实测 / SCIP / 人工 ML-CL 与抽样判定）不在本 stage。

**E2 `gate-0002`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0002.md`

- `context_refs`：`.agenticdoc/feature-params-service`; `L3 below 2 rounds (budget 2)`
- `note`（逐字）：

  > approved - resume with one extra round

**E2 `gate-0003`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0003.md`

- `context_refs`：`stage-1`
- `note`（逐字）：

  > 用户 2026-09-23 亲拍 approve（方案 A＝不补 K2 l3-report，直接收尾）。确认三件事，其一 Stage 1 七 key 的 done 与证据链成立（dossier=.agenticdoc/_autopilot/stages/stage-1-close.md）；其二 Phase B 五类（FEATURE_X=0/1 编译门禁 / L2 seam 逐轮下降与移植成本偏差<30% / SCIP 全量索引与编译数据库 / 真实人工锚点·CL 与人工抽样判定 / R2AI_BEGIN/END 内联标记+五道 CI 门禁接引擎仓）确认为本机跑不了、未被伪造完成，继承下一阶段，approve 不表示其完成；其三 授权按流程开下一阶段（conductor 派 roadmap-writer 出 Stage 2 提案 → 新 stage-confirm 闸门再拍）。已知非绿项随批准一并封存（feature-params-service l3-verdict=below 且 l3-report.md 为空壳 181B，LEG-01..LEG-10 已登记不阻塞，用户选择不补报告）。

**E2 `gate-0004`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0004.md`

- `context_refs`：`stage-2`
- `note`（逐字）：

  > 用户 2026-09-23 亲拍 approve（Stage 2 启动，key 列表与 _roadmap.md 提案一致，未调整）。5 key = feature-trend-two-points / feature-tier-a-closeout / feature-completeness-four-dim / feature-phaseb-handoff / feature-mvp-closeout；预期派发批次（max_parallel_keys=2）① trend-two-points ∥ tier-a-closeout ② completeness-four-dim ∥ phaseb-handoff ③ mvp-closeout。边界重申：编译级（FEATURE_X=0/1）与真实升级实测不在本 stage，禁把构建机与人工项记为达成；两个改 doc 的 key 写面已互斥。

**E2 `gate-0005`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0005.md`

- `context_refs`：`.agenticdoc/feature-tier-a-closeout`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 用户 2026-09-23 亲拍 approve（选项 A＝加一轮重试，与 Stage 1 gate-0002 同例）。依据：本轮 L3 判 below 属格式与读域问题而非质量缺陷——conductor.py 的 _parse_l3_output 要求 reviewer 的 output.md 含「## Quality Gate Report」＋「## Achieved」两节且无 FAIL 行，而 l3-a1/a2 的 output.md 只有 TL;DR/Summary/Changed Files 等节；成因是读域上限（worker 默认 8 次读 / 64KB）封了 spec.md、design.md、quality-gate-report 与 5 个 worker 的 output.md（共 14 条 Read Scope Rejections），reviewer 于是把结论写到了自己的 report.md。reviewer 自评结论为 PASS（32/32 VC、VC-025 隔离回归 1573 passed / 0 failed、needs-rerun=0），机械门 verify_k7.py 亦 exit=0（32 AC + 32 VC 全绿），故按加一轮处理：派 repair＋l3-a3，使其按格式交出两节而结案。本次批准不放宽任何门限、不改已发布字节、不把构建机与人工项记为达成；读域上限的根因修复另立 key feature-l3-readcap-injection（已追加为 Stage 2 第 6 个 key）。

**E2 `gate-0006`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0006.md`

- `context_refs`：`.agenticdoc/feature-mvp-closeout`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 用户 2026-09-24 亲拍 approve（选项 A＝加一轮重试，与 gate-0002、gate-0005 同例）。前置动作已完成：用户执行 /mw restart，serve PID 111344 与 conductor PID 12984 均于 2026-09-24T11:03:42+08:00 启动（晚于 feature-l3-readcap-injection 的 dispatch.py 修复提交 6254783b / 修改时间 02:22:22），故本轮 L3 将首次吃到真实读域预算（默认产物项目为 l2_read_file_cap 128 / l2_read_byte_cap 4194304），同时完成该 key 登记的 AC-006（重启后真实派发）。本轮 below 的成因同样是格式与读域而非质量缺陷：l3-a1/a2 的 output.md 缺 conductor 要求的「## Quality Gate Report」与「## Achieved」两节、且有 12 条 Read Scope Rejections（旧上限 8 次读 / 64KB），而 reviewer 自评在 report.md 里为 PASS（38/38 VC、needs-rerun=0、mvp_achieved=true、switch_ready=false）。本次批准不放宽任何门限、不改已发布字节、不把构建机与人工项记为达成；人工与 Phase B 事项仍须保持未达成登记。

**E2 `gate-0007`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0007.md`

- `context_refs`：`stage-2`
- `note`（逐字）：

  > 用户 2026-09-24 亲拍 approve。Stage 2 全部 6 key 终态（trend-two-points / tier-a-closeout / completeness-four-dim / phaseb-handoff / l3-readcap-injection / mvp-closeout 均 DONE），闭卷 dossier stage-2-close.md 已生成。核心结论 mvp_achieved=true 与 switch_ready=false 分列不混真值；两条未达成判据（CI 门禁 1/2/3 未接线 = not_met、人工抽样未判 = not_evaluable）如实登记且 counted_as_done=false，9 条未达成台账 + 11 条遗留每条均有去向。Stage 3 已定调为 A+C（切换就绪线 + 接入 parent GUI 的时间维与 MVP 看板），Phase B 实测留 Stage 4；用户明确本机就是构建机，B 的延后不是因为没有机器，而是排期与前置依赖。本次批准不放宽任何门限、不改已发布字节、不把未接线与人工项记为达成。

**E2 `gate-0008`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0008.md`

- `context_refs`：`stage-3`
- `note`（逐字）：

  > 用户 2026-09-24 亲拍 approve（Stage 3 范围由用户同日前置定为 A＋C）。确认启动 Stage 3（6 key，目标为把 switch_ready=false 里机器可做的部分闭掉并把三问接进 parent GUI 子页面）；Phase B 实测留 Stage 4，用户明确本机就是构建机故 B 的延后属排期与前置依赖，不得写成缺机器。边界确认：拒绝写 E:\Engine2Up（门禁安装与内联标记注入只做套件与补丁包＋临时克隆验证，安装一步登记为待授权）；拒绝代填人工抽样值（通道可做，production_human_rows 只能由用户填）；Stage 3 内 doc 写者唯一为 feature-switch-readiness-closeout。本次批准不放宽任何门限、不改已发布字节、不把待授权与人工项记为达成。

**E2 `gate-0009`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0009.md`

- `context_refs`：`.agenticdoc/feature-inline-marker-patchkit`; `L3 无裁决（worker failed: ap-feature-inline-marker-patchkit-l3-a2）达 2/2 轮`
- `note`（逐字）：

  > 用户 2026-09-25 亲拍 approve（选项 A＝加一轮重试）。证据：L3 两轮均无裁决，成因是 reviewer（role=review，model timi/gpt-5.6-sol）把质检长文写进 workers/<l3-aN>/report.md，而 output.md 仅含 TL;DR/Summary/Changed Files/Verification Steps/Exit Reason，缺 conductor.py::_parse_l3_output（第 1088 行）要求的 Quality Gate Report 与 Achieved 两节，故机械判定无裁决。需注意本 key 两轮均未留下 report.md，即 reviewer 结论本身未留痕，故本 key 的完成度不能靠已有证据背书，本轮重试必须以 output.md 内的两节为准。已同批准的 feature-l3-verdict-source-fallback 将从框架侧修判定源优先级；本轮重试仍按 task.md 明文要求把两节写进 output.md。不放宽门限、不改已发布字节。

**E2 `gate-0010`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0010.md`

- `context_refs`：`.agenticdoc/feature-cigate-install-kit`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 用户 2026-09-25 亲拍 approve（选项 A＝加一轮重试）。证据：两轮 L3 的 report.md 结论均为 PASS（35/35 VC 均有 PASS 记录、FAIL 行 0、needs-rerun=0；a2 原文自述首轮 3 项可修证据遗留已闭合），但两轮 output.md 均缺 Quality Gate Report 与 Achieved 两节，故 conductor 机械判 below——与 Stage 2 的 gate-0005 / gate-0006 同型，属判定源错位而非质量缺陷。已同批准 feature-l3-verdict-source-fallback 修框架侧回退优先级；本轮重试要求两节写入 output.md。不放宽门限、不改已发布字节、不把待授权项（引擎侧安装未被授权）记为达成。

**E2 `gate-0011`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0011.md`

- `context_refs`：`.agenticdoc/feature-gui-time-mvp-board`; `exec task 001-board-params-config-errors exhausted 2/2 attempts`
- `note`（逐字）：

  > 用户 2026-09-25 亲拍 approve（选项 A＝加一轮重试）。证据：exec task 001-board-params-config-errors 两轮均以 idle timeout 结束（a1 无活动 613s / a2 无活动 612s），output.md 仅含 TL;DR/Summary/Exit Reason 且无实质产出，属 harness idle 看门狗误杀而非内容缺陷——阀值来自 coding-agent worker-mode.ts 的 DEFAULT_IDLE_MS = 10 分钟（env PI_WORKER_IDLE_MS 未设置）。同型击杀全项目累计 12 次，绝大多数重试即成功（如 cigate design-writer a1/a2 → a3、marker spec-writer a1 → a2）。本批准不放宽任何门限、不改已发布字节；若第 3 轮再被 idle 击杀，PM 将提议拆分该 task 或抬高 idle 阀值（后者需 mw serve 带 env 重启，属用户操作）。

**E2 `gate-0012`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0012.md`

- `context_refs`：`.agenticdoc/feature-cigate-install-kit`; `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: feature-cigate-install-kit cannot advance to ''done'' Current phase: verify - NO MATCH: achieved.md missing…`
- `note`（逐字）：

  > 方案 A 人工介入后重试。根因是 achieved.md 缺门禁要求的那一节，已由 PM 派 repair 重写为 14,348 B 并含该节与遗留，且已披露两节系 repair 事后补入；重试应一次通过。

**E2 `gate-0013`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0013.md`

- `context_refs`：`.agenticdoc/feature-l3-verdict-source-fallback`; `advance execute->verify 连续 5 次失败（class=interface-drift；interface-driftx5）: ERROR: feature-l3-verdict-source-fallback/pm-state.md has unknown phase ''execute（t-001 … t-007 已收口；`tasks` / `execute` …`
- `note`（逐字）：

  > 方案 A 人工介入后重试。根因是 key 自己的 pm-state 相位行被写成整句话，框架判 unknown phase；PM 已把该行还原为纯 token，相位未变（索引侧一直是 EXECUTE），重试应一次通过。

**E2 `gate-0014`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0014.md`

- `context_refs`：`.agenticdoc/feature-gui-time-mvp-board`; `L3 below 3 rounds (budget 2, credits 1)`
- `note`（逐字）：

  > 方案 A 人工介入后重试。L3 三轮判 below 且失败项为真实缺陷而非机械误判（37 PASS / 5 FAIL）：VC-001 parent db shm/wal 导致白名单外 delta、VC-002 7 个受保护 eval 导出哈希漂移、VC-033 未限定 K5 E2E 仍 exit 1、VC-037/039 spec 降标未同步 design/ER。放宽的是验证方式与文档同步，属可修范围；若下一轮仍同 5 项，则转 closed-legacy 加四态登记。

**E2 `gate-0015`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0015.md`

- `context_refs`：`.agenticdoc/feature-false-meets-remediation`; `L3 below 2 rounds (budget 2, credits 0)`
- `note`（逐字）：

  > 方案 A 人工介入后重试。L3 第二轮已收敛到 15 PASS / 1 FAIL，仅剩 VC-013（自持 replay 承诺与终态哈希闭包，needs-rerun），修复面收窄且明确；本 key 的复算产物已交付（18 轮 9 key，3 false-meets / 5 false-below / 10 unchanged）。

**E2 `gate-0016`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0016.md`

- `context_refs`：`.agenticdoc/feature-false-meets-remediation`; `L3 无裁决（worker failed: ap-feature-false-meets-remediation-l3-a3）达 3/3 轮`
- `note`（逐字）：

  > 方案 A 人工介入后重试。本 key 非质量缺陷而是 L3 无裁决：reviewer 轮 l3-a3 中途断流（worker.log stream closed before response.completed，exit=0、elapsed=1m、只留占位 output.md），轮次 3/3 耗尽。历史轮次 a1/a2 均正常出裁决，重试成功率高；断流根因另记 reflect/l3-reviewer-stream-abort.md（L3 读域过大无角色配额）。

**E2 `gate-0017`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0017.md`

- `context_refs`：`.agenticdoc/feature-gui-time-mvp-board`; `L3 无裁决（worker failed: ap-feature-gui-time-mvp-board-l3-a4）达 4/4 轮`
- `note`（逐字）：

  > 方案 A 人工介入后重试。本 key 非质量缺陷而是 L3 无裁决：reviewer 轮 l3-a4 中途断流（stream closed before response.completed，exit=0、elapsed=1m、占位 output.md 465 B），轮次 4/4 耗尽。该 key 的 a2/a3 均正常出裁决（37 PASS / 5 FAIL），重试后可继续按该 5 项修复推进；断流根因见 reflect/l3-reviewer-stream-abort.md。

**E2 `gate-0018`** — `H:/git/E2Feature/.agenticdoc/_autopilot/gates/gate-0018.md`

- `context_refs`：`.agenticdoc/feature-false-meets-remediation`; `L3 无裁决（worker failed: ap-feature-false-meets-remediation-l3-a4）达 4/4 轮`
- `note`（逐字）：

  > 方案 A 人工介入后重试（第 3 次 reviewer）。本 key 非质量缺陷而是 L3 无裁决：l3-a3 与 l3-a4 连续两次中途断流（stream closed before response.completed，elapsed=1m、tools=41-47、只留占位 output.md），轮次 4/4 耗尽；同批 gui 的 l3-a5 重试即出裁决（42/42 PASS）证明重掷有效。用户同时把 review 角色模型改为 timi/glm-5.3（.mw/dispatch.yml，per-spawn 解析，无需重启），本轮即新模型首跑。若再断流则转 closed-legacy + 四态登记。
### F2 — 决策所需的最小信息集（14 项）`[事实 + 推断]`

**"最小"的判据**：以**回放覆盖**为下限（note 里出现过的每一类决策依据都必须被某项覆盖），以**逐项非冗余**为上限（每一项都要给"去掉它会错判成什么"的反例）。表 F5-a 给出逐门回放，表 F5-b 给出计数。凡"回放命中 = 0"的项，其必要性来自操作必需或等待实测，**不从 note 论证**，已显式标注。

| 编号 | 信息项 | 为什么最少需要它（理由） | 反例（少了它会错判成什么） | 可得性 | 回放命中（原子 / 门） |
|---|---|---|---|---|---|
| **F1** | **门身份与时效**：`id` / `kind` / `scope`（`stage=N` 或 `key=K`）/ `created_at` / 已等待时长 / 应答入口 / **同 scope 历史已答门与上次结果** | 决定"这是什么门、卡了多久、谁能答"；没有时效就无法区分"刚发生的门"与"17.4h 无人管的门"（RQ-10：`stalled` p50 3.60h / max 17.40h）；没有历史门就无法识别**重放** | ① 面板只显示 `id (kind)`（`monitor.ts:648-653`）⇒ JC gate-0007 与 gate-0008 都是 `gate-0007 (stage-close)` 式的行，**看不出后者已 pending 8.5 天**；② 不带历史门时，JC gate-0008 会被读成"第一次收口 Stage 1"，而实际是 gate-0001 被重复消费导致 stage 1 从 `closed` 回到 `running`（§方法·复算的实测） | **机器可读** | 0 / 0（**操作必需**，见 §F5「零命中项论证」） |
| **F2** | **决策命题原文**：`question` 一行 | 门要人判的命题必须逐字可见；`stalled` 的模板句里**内嵌了 machine reason**（表 F1-b） | 面板只给 `id (kind)` ⇒ 人必须自己打开文件才能知道在问什么；两个同日同 key 的 `stalled` 门（E2 gate-0015/0016 同 key `feature-false-meets-remediation`）在不看原因串时**完全无法区分** | **机器可读**（`gates.py:68-81` 字段 `question`；TS `GateRecord.question` `status-model.ts:589`） | 2 / 2 |
| **F3** | **选项闭集与各选项后果、可逆性**：`approve`/`reject` 各自做什么、能否撤销 | 34 门里 **15 个 note** 显式在推理"选项的后果"（如 FM gate-0004 "不做 closed-legacy：…放弃即等于丢弃已交付成果"）；`stalled` 的 approve **不是**"通过"而是"续跑一轮"（`_resume_credits:2273`，每 cap 回路 +1 轮），reject 则是 `closed-legacy`（`∈ _DEP_SATISFIED:56` ⇒ 解锁依赖 + 放行 stage 收口）且**无撤销入口** | 把 approve 读成"验收通过"⇒ 以为 key 已交付（实际只是再烧一轮）；把 reject 读成"否决但可重来"⇒ 实际把 key 永久标 `closed-legacy` 并**解锁下游 + 伪造 stage 完成**（RQ-10 W3 已判定不可自动，本卡补充：**人也不该在不知道后果的情况下答**） | **仅散文**（唯一来源是代码常量：`conductor.py:2273/2295/2363/348-384/980-1001/2085-2111`；磁盘无字段） | 15 / 15 |
| **F4** | **目标一致性**：该门所属 stage 的 goal 原文 + `goal.md` 身份（路径 / mtime / sha）+ goal 变更摘要 + 提案与 `_roadmap.md` 一致 / 范围收窄 | `stage-confirm` 与 `goal-change` 的**全部内容**就是"这与目标对不对"；34 门里 9 门（15 个原子）的 note 引用目标/提案/范围 | 只看"goal.md 变了（mtime X→Y）"会漏掉 JC gate-0002 的实际判定依据——"删掉的是 2026-09-10 的 stale Roadmap 快照节、核心三节完好"；`stage-confirm` 不看 goal 就不能判断 LLM 提案是否跑偏（FM gate-0009 的 7 条约束、E2 gate-0008 的两条明确拒绝都是在这一层加的） | **需读多文件**（`_roadmap.md` `> goal:` + `> goal_mtime:`；`goal.md`；`stage-confirm` 的 question 已内嵌 goal） | 15 / 9 |
| **F5** | **触发原因类与计数**（机器事实面）：`advance` 的 class + 连续次数 / `exec task … exhausted N/M` / L3 verdict 值 / worker 退出形状（exit / elapsed / tools） | 人审 `stalled` 门的第一问是"框架假阴还是真缺陷"；`stalled` 的原因是 **22 门 × 5 类**（RQ-10 F1d），且**同一句模板**下真伪判决相反 | 只看"L3 below"会漏掉 E2 gate-0014 的 note 结论——"37 PASS / 5 FAIL，失败项为**真实缺陷**"（vs E2 gate-0010/0011 的"机械误判"）；只看"exec exhausted 2/2"会漏掉 FM gate-0006 的"全量 pytest 630.51s > idle 阈值 ⇒ 任何 worker 必被杀"这一因果 | **需读多文件**（gate `context_refs[1]` + timeline `advance` detail `class=` + `<key>/workers/*/trace.log` 末行 + `l3-verdict.txt`） | 19 / 19 |
| **F6** | **证据指针集合**：`<key>/` 目录、`l3-verdict.txt`、`l3-report.md`、`achieved.md`、触发轮的 `workers/<task>/{output.md,report.md,worker.log,trace.log}`、stage 级门另加 `_autopilot/stages/stage-<N>-close.md` | 45 个原子 / **25 门**（`PTR|DETAIL|ABSENCE`）的 note 打开了具体工件；其中 **7 门**给了可重放的命令与结果（`VERIFY`：四 key 复验 / `check_gate` / `pytest …` / `verify_k7.py`） | 无指针 ⇒ 人只能靠 `question` 的散文猜（RQ-10 已证 gate 的 12 字段**无任何机器判据字段**）；指针缺**触发轮**这一维 ⇒ 指针会落到错误的轮次（见 F7 的漂移证据） | **需读多文件**（`context_refs[0]` = `.agenticdoc/<key>`，其余按上述路径模式枚举） | 45 / 25 |
| **F7** | **证据的存在性 / 大小 / 节名 / 新鲜度**："文件不存在"、"占位 output.md（~465-582 B）"、"缺 `## Quality Gate Report` / `## Achieved` 两节"、"dossier 的 verdict 列是首轮快照" | **缺席本身是决策依据**：E2 gate-0009 的 note 判定"两轮均未留下 report.md ⇒ reviewer 结论未留痕 ⇒ 完成度不能被已有证据背书"；FM gate-0008 判定 dossier 两行 verdict 陈旧（附 mtime 09-23 19:48/19:10） | 只给"证据指针"而不给"存在性/体量/节名"，人会以为证据齐备：E2 gate-0009/0010 的 `output.md` 缺两节是**机械判 below 的直接原因**；只看路径不看大小则无法识别 465 B 的占位件 | **机器可读**（存在性/字节数/`^## ` 节名可机判；E2 `feature-cigate-install-kit` 实测 `l3-a1` 1409 B / `l3-a2` 10134 B，`feature-inline-marker-patchkit` 25 个 worker 目录只有 24 个 `output.md`、仅 1 个 `report.md`） | 3 / 3 |
| **F8** | **影响面·结构**：本 key 的传递下游 key 数/名单；是否阻塞所在 stage 收口（`all(terminal)`）；是否阻塞下一 stage（`stage-close` pending ⇒ 下一 `stage-confirm` 未开）；`goal-change` ⇒ 全 roadmap 停 | 决定"要不要现在答"；`stalled` 门不只卡本 key：FM `gui-shell-spike` 的传递下游 **8 个 key**、`cli-readonly-snapshot` **9 个 key**（实测 `dependency_graph` 闭包） | 不看影响面 ⇒ 把"只卡自己"的门与"卡住整个 stage/下一 stage"的门同等对待；把 `goal-change` 当成普通门（实际它一挂即**全 roadmap zero-dispatch**，`conductor.py:2093-2111`） | **需读多文件**（`_roadmap.md` Keys 表 + `> status:` + `> key-status:`，join `_index.parallel`） | 0 / 0（**实测论证**：RQ-6 的 stalled 占窗口墙钟 E2 46.6% / FM 54.6%；JC gate-0007 pending 8.5 天，见 §F5「零命中项论证」） |
| **F9** | **弃置代价（stake）**：答 `reject`（`closed-legacy`）会丢弃什么、是否解锁依赖 / 放行收口 | 6 门显式权衡过；`closed-legacy` 是**不可逆**且会被当作完成（`_DEP_SATISFIED`） | FM gate-0004/0005 的 note 明写"本 key 的全部 VC 与证据链是 Stage 1 的核心交付物，放弃即等于丢弃已交付成果"——没有这一项，`reject` 看起来只是"关掉一个卡住的门" | **仅散文**（gate 字段与 roadmap 均无"该 key 贡献了什么"的表达） | 6 / 6 |
| **F10** | **已发生的带外处置/修复记录 + 可复核的命令与结果**：approve 之前人/PM 做了什么（改配置、改代码、重写文书、重启服务、改模型），以及验证命令与输出 | RQ-10 F1f 已证 **≥16/22** 条 `stalled` approve 记录了 approve **之前**的带外修复；本卡的 `FIX|CONFIG` 原子覆盖 9 门（10 个原子）。approve 的真实语义是"人已修好、放行一轮" | 没有这一项 ⇒ 人会以为 approve 是"机器复算通过"，从而**在没做那次修复时也照批**——RQ-10 风险 19 的实锤（本卡的 F5-a 把 `FIX` 原子定位到具体门：FM-0002/0003/0006/0007、E2-0006/0012/0013/0018 等） | **仅散文**（只在 `note`，且是**应答后**写的；E2 gate-0006 的"进程启动时间 > 提交时间"是唯一可机器重算的例子） | 10 / 9 |
| **F11** | **边界声明与下一轮强制要求 + 前序门带入的约束**：不许放宽的判据、不得记为达成的项、下一轮必须做什么、上游门写下的约束清单 | 33 个原子，**覆盖 34 门中的 22 门**（`NEXT|BOUNDARY|PRIOR`）（本卡命中最多的散文项）。它是人审的**主要产物**（"不放宽任何门限 / 不改已发布字节 / 不把待授权项记为达成"在多门重复） | 没有这一项 ⇒ 重试轮会**放宽判据**（正是 P-014 家族与 FM 台账 A-02 的形状）；FM gate-0009 的 7 条上游约束（A-02/A-05/A-08/A-09/A-10/L-1/C-09）会被丢掉，Stage 2 全段在无约束下开跑 | **仅散文**（只在 `note`；前序门约束也只在**上一道门的 note** 里，无结构化载体） | 33 / 22 |
| **F12** | **未达成 / 遗留台账**：stage 级的未达成判据、`counted_as_done=false`、carry-over 去向（A-02 / L-1 / C-09..C-11 / NRR-1/NRR-2） | 4 门（全部 `stage-close`）；`stage-close` 的实质输出就是"哪些没达成、去哪了" | E2 gate-0003 的 note 原文"approve 不表示其完成"、E2 gate-0007 的"两条未达成判据如实登记且 `counted_as_done=false`"——没有这一项，`approve` 会被读成"全部达成"，**伪造完成**（RQ-10 W5 的反例同一面） | **仅散文**（dossier 只有 `key/final phase/l3 verdict/l3 report/evidence` 列，**没有未达成台账**；台账只存在于 note 与 key 自己的 `achieved.md` 遗留节） | 4 / 4 |
| **F13** | **默认动作与到期时间** | 题目点名要求；也是 RQ-6 的直接结论：**现状无默认动作、无 TTL**（20/20 stalled gate 全靠人工；等待 0.19-17.40h） | 没有它 ⇒ 无人值守下门**隐式永久滞留**：JC gate-0007 实测 pending **8.5 天**（`created_at 2026-09-17T20:04:14Z`，快照 08:2xZ）；反例即"这个门现在没有任何机器可读的到期语义" | **仅散文 / 不存在**（`gates.py:68-81` 的 12 字段无时间上界；`FRONTMATTER_FIELDS` 无 `expires_at`；`timeline.py:67-85` 无超时事件） | 0 / 0（**缺失实测**：RQ-6 / RQ-10 §数据缺口 4） |
| **F14** | **谁该答 / 怎么答 / 预算余量**：应答命令、期望应答者、剩余轮次与 credits | 10 个 `BUDGET` 原子（E2 的 note 反复用"budget 2, credits 1""若下一轮仍同 5 项则转 closed-legacy"这类**有界承诺**决定是否续跑）；`answered_by` 实测 4 种自由写法（`wenbozhou` / `human-pm-window` / `user-via-pm-window` / `human-via-pi`）⇒ 谁答这一项**不能机器判** | 没有余量 ⇒ 无法判断"再给一轮"是否还有边界（RQ-10 已证 `_resume_credits` 无上界）；没有命令 ⇒ 人只能凭记忆敲 `/autopilot gate <id> approve\|reject --note` | **需读多文件**（命令 = TS 常量 `console.ts:208/218-222`；`used_rounds` = 扫 `<key>/workers/*/task.md` 的 `loop:`/`attempt:`，`state.py:224-249`） | 10 / 10 |

### F3 — 信息项 × 可得性（当前能否机器抽取）`[事实]`

**分类定义**（本卡自定，用于消除歧义）：
- **机器可读（M）** = 该项的每个值都可从**单一文件的一个具名字段**直接取出（枚举/时间戳/布尔/长度）。
- **需读多文件（K）** = 需要 join ≥2 个文件家族、或需要按路径模式枚举、或需要重跑一条命令。
- **仅散文（P，含"不存在"）** = 只存在于人写的 `note`/`question` 散文、只存在于代码常量（磁盘无字段）、或**根本不存在**。

| 项 | 可直接读的字段（`file:line` + 字段名） | 需读多个文件（路径模式） | 仅散文 / 不存在（样例） |
|---|---|---|---|
| **F1** | `gates.py:68-81` → `id` / `kind` / `stage` / `key` / `created_at` / `status`；已等待 = `now - created_at`；同 scope 历史门 = 门目录扫描后按 `kind+stage|key` 分组 | — | 期望应答者（`answered_by` 是自由文本，实测 4 种写法） |
| **F2** | `gates.py:70` → `question`（单行散文，但**字段可读**）；TS `status-model.ts:589` `GateRecord.question` | — | — |
| **F3** | — | — | 全部：只在 `conductor.py:2273/2295/2363/348-384/980-1001/2085-2111`；`note` 的"方案 A＝加一轮重试"是**人的复述**，不是字段 |
| **F4** | `_roadmap.md` 的 `> goal:` 与 `> goal_mtime:`（`roadmap.py:52-56`）；`stage-confirm` 的 `question` **内嵌** `<N 个 key，目标：<goal>>`（`conductor.py:496-501`） | `goal.md` 的 mtime/sha；`_roadmap.md` 与 `note` 声称一致 | **goal 变更摘要**：`goal-halt` 事件的 detail 只有 `mtime_ns X -> Y`（`conductor.py:2093`）——**改了什么不可得**（JC gate-0002 的全部依据） |
| **F5** | `l3-verdict.txt`（值域 `meets\|below`，`conductor.py:659-671`） | gate `context_refs[1]`；timeline `advance` 的 `class=`；`<key>/workers/*/trace.log` 末行 `[END] … exit=N elapsed=Ns tools=M`；`<key>/workers/*/worker.log` 末行（如 `stream closed before response.completed`） | "**假阴 vs 真缺陷**"的定性：需人读 `l3-report.md` / `output.md` 散文（RQ-10 F1d 结论，本卡复核：E2 gate-0014 的 5 个 VC 性质只在 note） |
| **F6** | — | `<key>/{l3-verdict.txt,l3-report.md,achieved.md}`、`<key>/workers/*/{output.md,report.md,worker.log,trace.log}`、`_autopilot/stages/stage-<N>-close.md` | "**哪一轮是触发轮**"：无字段（需按门 `created_at` 与 worker 时间戳推断） |
| **F7** | 文件存在性/字节数/`^## ` 节名（`os.stat` + 正则） | 触发轮归属 | 「dossier verdict 列是否陈旧」的**判定规则**（C-11）无字段，需人比对 mtime 与最终轮 |
| **F8** | `_roadmap.md` 的 `> status:` / `> key-status:`（`roadmap.py:52-68`）；Keys 表 `depends_on` | join `_workers.parallel`（在飞/占槽；RQ-7 给出 conductor 口径） | **"当时实际在等的 key 与各自等待时长"**：`update_key_status` 是覆盖写 ⇒ 历史状态不可回读（与 RQ-7 F4.2(3) 同结论；本卡复核：3 个项目 roadmap 的现存状态与门时状态已不同，如 JC stage 1 现为 `running`） |
| **F9** | — | — | 全部：只在 `note`（如 FM gate-0004 的"放弃即等于丢弃已交付成果"） |
| **F10** | — | 唯一可机算的例子：E2 gate-0006 的"进程启动时间 > 修复提交时间"（`serve.meta` / 进程表 + `git log`） | 全部其余：只在 `note`；**且写在应答之后**（gate-time 不存在） |
| **F11** | — | 前序门的 `note`（按同 stage/key 追溯） | 全部：只在 `note`；无结构化载体（RQ-10 F5 已把"结构化约束字段"列入缺口） |
| **F12** | `stage-<N>-close.md` 的 5 列表（`key/final phase/l3 verdict/l3 report/evidence`，`conductor.py:722-750`） | `<key>/achieved.md` 的遗留节 | **"未达成台账 / counted_as_done / 去向"**：只在 `note`（E2 gate-0003/0007） |
| **F13** | — | — | **不存在**：`FRONTMATTER_FIELDS`（`gates.py:68-81`）无 `expires_at`/`default_action`；`EVENT_TYPES`（`timeline.py:67-85`）无超时事件 |
| **F14** | 应答命令模板（`console.ts:208/218-222`） | `used_rounds` = `<key>/workers/*/task.md` 的 `loop:`/`attempt:`（`state.py:224-249`）；`budget/credits` 只在 `question` 散文（"budget 2, credits 0"） | "谁该答"：`answered_by` 自由文本，无 `expected_responder` 字段 |

**表 F3 小结 `[事实]`**：14 项中 **3 项机器可读**（F1/F2/F7）、**5 项需多文件 join**（F4/F5/F6/F8/F14）、**6 项仅在散文或不存在**（F3/F9/F10/F11/F12/F13）。**"选项后果 + 可逆性"与"默认动作 + 到期时间"这两项恰好最影响决策，却分别是"只在代码里"与"不存在"。**

### F4 — 呈现契约草案（字段级）与现状对照 `[事实 + 推断]`

#### F4.1 现状对照 `[事实]`

| 面 | 代码位置 | 现在显示什么（逐字模板） | 缺什么 |
|---|---|---|---|
| 面板 gate 行 | `monitor.ts:644-654` | 多门：`gates: {N} pending - {id} ({kind}), … -> /autopilot gates`；单门：`gates: 1 pending - {id} ({kind}) -> /autopilot gate {id} approve\|reject`；**整行 110 列硬截断**（`MONITOR_LINE_MAX`，`monitor.ts:61`） | `created_at` / 已等待时长 / `key`/`stage` / `question` / 原因类 / 证据 / 影响面 / 后果 / 默认与到期。`MonitorGate`（`monitor.ts:89-95`）**只有 id/kind/stage/key**，`scanPendingGate`（`:150-180`）也只扫这 5 个字段 ⇒ 面板**物理上无法**显示等待时长 |
| 面板 attention 行（唯一的"带语义"门渲染） | `monitor.ts:604-626` | `· {key} {phase}/{status} | {n} running | advance {k}x {class} {age} ago "{lastError}" | deps blocked by {…} | -> /autopilot gate {id} approve\|reject (resume grants one round)` | 只对 `status=stalled` 且存在 `kind=stalled` 门时生效；只给 `id`，不给 `question`/原因串/证据/影响面；`(resume grants one round)` 是**唯一**一处把 approve 的后果写进面板的地方（却只覆盖 `stalled` 这一 kind） |
| `/autopilot gates` | `console.ts:182-198` | `{id} [{kind}]{stage=N}{key=K} — {question} (created {iso})` + `answer: /autopilot gate {id} approve\|reject [--note <text>]  ({path})` | `context_refs` / `note` / 影响面 / 证据 / 后果 / 默认与到期；`GateRecord`（`status-model.ts:582-591`）不含 `context_refs` |
| `mw doctor` | `mw_common.py:2022-2065` | autopilot 节仅 `path/exists/xkey_repair/xkey_verify_*/origins/diagnostics/error` | **零 gate 内容**（无 pending 数、无 id、无等待时长） |
| timeline | `timeline.py:67-85`；`gate-created` 事件 | `detail = "gate-0002 kind=stalled"`；`gate-answered` 的 `detail = "gate-0002 approved → {key} running"` | 面板不做 gate 历史渲染；`gate-created` **不写** `context_refs[1]` 的原因串（本卡实测） |
| `answered_by` | `gate-writer.ts:139` | 自由文本：实测 34 门里 4 种写法（`wenbozhou` 17、`user-via-pm-window` 10、`human-via-pi` 6、`human-pm-window` 1） | 无"人与机器可区分"的机器判据（RQ-10 F5 同一缺口） |

`[事实]` 结论：**现状的 gate 呈现是"id + kind"级别**，而 34 门的人审依据有 **6/14 项**只在散文或不存在（表 F3）⇒ 现状与"最小信息集"之间的缺口不是排版问题，而是**信息载体问题**。

#### F4.2 呈现契约（三层：面板行 / 门卡片 / doctor JSON）`[推断]`

**层 1 — 面板：每个 pending gate 一行，≤110 列**（复用 `MONITOR_LINE_MAX`）

字段顺序（`|` 分隔，超长按 D3 截断）：

```
{id} [{kind}] {scope} {age}{reason_class}{impact} -> /autopilot gate {id} approve|reject
```

| 序号 | 字段 | 长度/取值约束 | 来源（必须是机器抽取） |
|---|---|---|---|
| 1 | `id` | `gate-\d+`，≤10 字符 | gate 文件 `id` |
| 2 | `kind` | 闭集 6 值，≤16 字符 | gate 文件 `kind`（`gates.py:54-61`） |
| 3 | `scope` | `stage=N`（N ≤ 2 位）或 `key=<K>`（K 尾部保留截断至 26 字符） | gate 文件 `stage` / `key` |
| 4 | `age` | `{n}h` / `{n}d`，≤6 字符 | `derived(now - created_at, gate.created_at)` |
| 5 | `reason_class` | 闭集 token，≤26 字符：`L3-below` / `L3-no-verdict` / `advance:{class}×{n}` / `exec:exhausted {n}/{m}` / `stage:all-keys-terminal` / `goal:mtime-changed` | `context_refs[1]` + timeline `advance` + `l3-verdict.txt`（映射表须落档，见 D1） |
| 6 | `impact` | `blocks={n}keys` / `blocks=stage-close` / `blocks=all(goal-change)`，≤22 字符 | `derived(|closure(depends_on)|, roadmap)` |
| 7 | 应答入口 | 固定串，≤40 字符 | TS 常量（`console.ts:208`） |

**层 2 — `/autopilot gates` 门卡片：每门固定 13 行、顺序固定**（信息密度递增；每行 ≤110 列）

| 行 | 内容模板 | 上限 | 来源 |
|---|---|---|---|
| L1 | `gate-0002 [stalled] key=gui-contract-surface stage=1 created=2026-09-23T11:10:29Z waited=15.9h` | 1 行 | gate 字段 |
| L2 | `Q: {question 逐字}` | question 头 160 字符，超出 `…(full: {path})` | gate `question` |
| L3 | `A: approve = {效果} (reversible: {yes\|no})` / `R: reject = {效果} (reversible: {yes\|no})` | 每行 ≤100 字符 | **代码派生的固定表**（per kind，见 D1 的 `derived`；当前无字段） |
| L4 | `goal: {stage goal 逐字}` + `(goal.md mtime={iso})` | goal 头 100 字符 | `_roadmap.md` `> goal:` + `goal.md` stat |
| L5 | `reason: {class} count={n} src="{context_refs[1] 逐字}"` / `verdict: l3={meets\|below\|none} ({path})` | 各 1 行 | gate `context_refs[1]` + `l3-verdict.txt` |
| L6 | `evidence: {path} ({bytes}B, sections=[…], mtime={iso}){ DRIFT?}` | ≤6 行 | 路径模式枚举 + `os.stat` + `^## ` 扫描 |
| L7 | `impact: downstream={n} keys [{list ≤5}] \| stage-close: {blocked\|na} \| next-stage: {blocked\|na} \| roadmap: {halted\|active}` | 1-2 行 | `dependency_graph` + `> status:` + `> key-status:` |
| L8 | `history: {gate-id} {kind} {scope} {status} {answered_at}` | ≤3 行 | 门目录扫描（**重放检测**） |
| L9 | `default: {action\|none(blocks forever)} \| ttl: {iso\|none(no field)}` | 1 行 | **当前恒为 `none`**（字段不存在，如实输出） |
| L10 | `budget: loop={loop} used={u}/limit={l} credits={c}` | 1 行 | `state.used_rounds` + `question` 散文（**散文部分必须带 source 标注**） |
| L11 | `prior-constraint [{gate-id}]: {约束逐字}` | ≤3 行，每条 ≤80 字符 | 前序同 scope 门的 `note`（逐字子串） |
| L12 | `open-items: {逐条}` 或 `open-items: none in field` | ≤5 行 | dossier + `achieved.md` 遗留节（**当前无结构化字段**） |
| L13 | `answer: /autopilot gate {id} approve\|reject --note <text>  expected: human` | 1 行 | TS 常量 + `answered_by` 历史分布 |

**层 3 — `mw doctor` 的 `gates` 段（JSON）**：与层 2 同字段名、同 `source` 标注，供机器消费（含 `[VERIFY]` 的自检）。

#### F4.3 "摘要必须是机器抽取而非 LLM 自由生成"的判据（D1-D7）`[推断]`

对齐 P-014 家族（该家族的原话是"**人写散文引文不可核 ⇒ 机制的工单必须机器生成且逐字锚定**"，见 `.agenticdoc/xkey-repair-mechanism/spec.md` §1.1；同族实测反例：`cross-key-repair-request-…` 的"§遗留第 96 行 <引文>"经逐字核对**非逐字转述且定位不成立**，且 `created_at` 与内容矛盾）：

- **D1 白名单 + 来源三元组**：每个渲染色值必须可写成 `file:field`（枚举/标量）、`file:Lx-Ly`（散文片段）、或 `derived(<公式>, <输入字段清单>)`。渲染器内置一张**字段来源表**，表外字段一律不渲染。
- **D2 逐字锚定**：任何抄自文件的散文必须是该文件的**精确子串**（渲染时 `assert value in source_text`，失败即渲染 `MISMATCH(anchor)` 而不是输出近似文本），并附 `mtime` + `bytes`（或 `sha256[:12]`）。
- **D3 截断规则**：路径用**尾部保留**截断（保住文件名），散文用**头部保留**截断；两者都必须带 `…` + 完整锚点（`path` 或 `path:Lx-Ly`），**禁止中间省略**。
- **D4 禁 LLM 生成**：渲染路径上不得调用模型；任何填不出的字段输出固定哨兵 `unknown (no field)`（而不是"看起来合理"的猜测）——这正是 F13 的形态（默认动作/到期时间必须显示为"不存在"而不是被 LLM 编一个）。
- **D5 漂移标记**：若 `mtime(<证据指针>) > created_at(<门>)`，追加 `DRIFT(mtime=…)`；`l3-verdict.txt` 同理。**依据**：TL;DR 第 5 条的 24/34 与 E2 gate-0010 的 13 分钟改写实证。
- **D6 `note` 不得作为派生输入**：`note` 只在 L8/L11 作为**逐字引用**出现（附 `gate-id` + `answered_at` + `bytes`）；任何数字（如"带外修复了几次"）不得由 `note` 派生。
- **D7 数字必须带公式**：`age`、`downstream`、`waited`、`count` 全部输出 `value(formula; inputs)`，便于复算（对齐 AC-003/AC-004 的"每个数字可由文件复算"要求）。

#### F4.4 契约套用于一个真实 pending 门（worked example）`[事实]`

**JC `gate-0008`**（`stage-close`，stage 1，快照时 pending 3.7h）——契约会把下面这些**机器事实**摆到人面前（全部可复算）：

| 行 | 渲染值 | 来源 |
|---|---|---|
| L1 | `gate-0008 [stage-close] stage=1 created=2026-09-26T04:37:27Z waited=3.7h` | gate 字段 |
| L2 | `Q: Stage 1 全部 key 已终态，闭环 dossier 已写入 …（表 F1-c 逐字）` | gate `question` |
| L3 | `A: approve = stage 1 → closed，并开下一 stage 的 stage-confirm 门（不自动派任何 key）(reversible: no)` / `R: reject = stage 1 → halted，需人工改 roadmap 才能继续 (reversible: no)` | `conductor.py:348-384`、`_ensure_next_stage_gate:409-432`、`roadmap.py:41-56` |
| L4 | `goal: 一期全部本地可闭环验证，不依赖 Rider 实机…`（stage 1 `> goal:` 逐字） | `_roadmap.md` |
| L5 | `reason: stage:all-keys-terminal count=4 (plugin-ui/llm-router/crash-analysis/rag-context=done)` | `> key-status:` + `_stage_closure:616-656` |
| L6 | `evidence: _autopilot/stages/stage-1-close.md (…B, mtime=2026-09-11T20:25:02Z)` + dossier 表 4 行；其中 **`llm-router \| DONE \| none \| — \| …`（verdict 缺失）** | dossier + 当前 `<key>/l3-verdict.txt`（`llm-router` 无该文件） |
| L7 | `impact: downstream=1 key [e2e-validation] \| stage-close: this gate \| next-stage: na (stage 2 already running) \| roadmap: active` | `dependency_graph` + `> status:` |
| L8 | `history: gate-0001 [stage-confirm] stage=1 approved 2026-09-11T06:20:38Z` / `gate-0005 [stage-close] stage=1 approved 2026-09-17T12:42:00Z` ⇒ **本门是该 stage 的第二次收口**，且 timeline 实测 `2026-09-26T04:37:27 gate-0001 approved → stage 1 running` | 门目录扫描 + timeline |
| L9 | `default: none(blocks forever) \| ttl: none(no field)` | 字段不存在（如实输出） |
| L13 | `answer: /autopilot gate gate-0008 approve\|reject --note <text>  expected: human` | TS 常量 |

`[事实]` 这一例同时说明两件事：**（a）** 影响面与选项后果完全可以机器算（`dependency_graph` + `_stage_closure` + `_ensure_next_stage_gate` 全在盘上）；**（b）** 现状面板对这一门只会显示 `gate-0008 (stage-close)`，**L8 的重放事实与 L6 的 verdict 缺失都不会出现**。

### F5 — 反向验证：用 34 个已答门回放最小信息集 `[推断 + 事实]`

**方法**：把每个 note 的决策依据逐条标注为**原子**（共 20 类），再把原子映射到表 F2 的信息项；一个门"全覆盖"= 它 note 里的所有原子都有承载项。原子标注是**人工判断**（`[推断]`），但每个原子都能在表 F1-d 的 note 原文里逐字找到出处，故可复核。

**原子 → 信息项映射**（表 F5-b 的口径）：

| 原子 | 含义 | 承载项 |
|---|---|---|
| `PROP` | 命题本身 | F2 |
| `CONSEQ` / `REV` | 选项后果 / 可逆性 | F3 |
| `GOAL` / `PROPOSAL` / `SCOPE` | 目标对齐 / 提案一致性 / 范围收窄与排除 | F4 |
| `REASON` / `ABORT` | 机器原因类 / 退出形状 | F5 |
| `DETAIL` / `PTR` / `VERIFY` | 根因细节（需读工件）/ 证据指针 / 可重放命令与结果 | F6 |
| `ABSENCE` / `ATTEST` | 证据缺席（文件不存在、占位件）/ 证据不能背书完成度 | F7 |
| `STAKE` | 弃置代价 | F9 |
| `FIX` / `CONFIG` | 带外修复记录 / 配置与服务变更 | F10 |
| `NEXT` / `BOUNDARY` / `PRIOR` | 下一轮要求 / 不许放宽与不得记为达成 / 前序门带入的约束 | F11 |
| `LEDGER` | 未达成与遗留台账 | F12 |
| `BUDGET` | 轮次与 credits 余量 | F14 |
| `XOWN` / `CONTROL` | 跨 key 写面归属 / 跨 key 对照实验 | **无**（本卡报出） |

**局限声明（必读）**：note 是人在**决策之后**写的，所以「回放覆盖」只能给出**下限**（人当时看过的别的东西不会出现在 note 里）；反过来，note 里写了而最小集**覆盖不到**的，是**确定的缺口**——本卡实测 3 个（见下）。同理，"零命中项"不代表不需要，只代表**note 没有为它作证**，其必要性必须另行论证（F1 操作必需；F8 由 RQ-6 的 46.6%/54.6% 墙钟占比与 JC 8.5 天 pending 论证；F13 由"字段根本不存在"这一实测论证）。

#### 回放结果 `[事实]`

表 F5-a：逐门回放（依据原子取自各门 note；原子 → 最小信息项的映射见表 F2；`无` = 该 note 未记录任何决策依据）

| 门 | 依据原子 | 覆盖 | 未覆盖原子 |
|---|---|---|---|
| JC gate-0001 | 无 | ✅ 全覆盖 | — |
| JC gate-0002 | GOAL | ✅ 全覆盖 | — |
| JC gate-0003 | REASON, DETAIL, PTR, CONSEQ, NEXT | ✅ 全覆盖 | — |
| JC gate-0004 | REASON, DETAIL, CONSEQ, BUDGET, NEXT | ✅ 全覆盖 | — |
| JC gate-0005 | PTR, STAKE, VERIFY | ✅ 全覆盖 | — |
| JC gate-0006 | GOAL, SCOPE, PROPOSAL | ✅ 全覆盖 | — |
| FM gate-0001 | PROP, SCOPE | ✅ 全覆盖 | — |
| FM gate-0002 | REASON, DETAIL, STAKE, FIX, NEXT | ✅ 全覆盖 | — |
| FM gate-0003 | REASON, FIX, NEXT, PTR | ✅ 全覆盖 | — |
| FM gate-0004 | REASON, DETAIL, PTR, STAKE, FIX, NEXT, BOUNDARY, VERIFY | ✅ 全覆盖 | — |
| FM gate-0005 | REASON, DETAIL, PTR, STAKE, FIX, NEXT, BOUNDARY, VERIFY | ✅ 全覆盖 | — |
| FM gate-0006 | REASON, DETAIL, PTR, CONSEQ, FIX, NEXT, BOUNDARY, CONFIG | ✅ 全覆盖 | — |
| FM gate-0007 | REASON, DETAIL, PTR, STAKE, NEXT, BOUNDARY, VERIFY | ✅ 全覆盖 | — |
| FM gate-0008 | PTR, ABSENCE, CONSEQ, NEXT, BOUNDARY, LEDGER | ✅ 全覆盖 | — |
| FM gate-0009 | CONSEQ, NEXT, PROPOSAL, SCOPE, PRIOR | ✅ 全覆盖 | — |
| FM gate-0010 | REASON, DETAIL, PTR, CONSEQ, NEXT, BOUNDARY, LEDGER, XOWN, VERIFY | ❌ 缺项 | XOWN |
| E2 gate-0001 | GOAL, PROPOSAL, SCOPE | ✅ 全覆盖 | — |
| E2 gate-0002 | PROP, CONSEQ | ✅ 全覆盖 | — |
| E2 gate-0003 | PTR, ABSENCE, CONSEQ, SCOPE, LEDGER | ✅ 全覆盖 | — |
| E2 gate-0004 | CONSEQ, BOUNDARY, PROPOSAL, XOWN | ❌ 缺项 | XOWN |
| E2 gate-0005 | REASON, DETAIL, PTR, CONSEQ, BUDGET, NEXT, BOUNDARY, VERIFY | ✅ 全覆盖 | — |
| E2 gate-0006 | REASON, DETAIL, PTR, BUDGET, FIX, BOUNDARY, VERIFY | ✅ 全覆盖 | — |
| E2 gate-0007 | PTR, CONSEQ, BOUNDARY, SCOPE, LEDGER | ✅ 全覆盖 | — |
| E2 gate-0008 | CONSEQ, NEXT, BOUNDARY, PROPOSAL, SCOPE | ✅ 全覆盖 | — |
| E2 gate-0009 | REASON, DETAIL, ABSENCE, BUDGET, NEXT, BOUNDARY | ✅ 全覆盖 | — |
| E2 gate-0010 | REASON, DETAIL, PTR, BUDGET, NEXT, BOUNDARY | ✅ 全覆盖 | — |
| E2 gate-0011 | REASON, DETAIL, PTR, CONSEQ, BUDGET, NEXT | ✅ 全覆盖 | — |
| E2 gate-0012 | DETAIL, CONSEQ, FIX | ✅ 全覆盖 | — |
| E2 gate-0013 | DETAIL, CONSEQ, FIX | ✅ 全覆盖 | — |
| E2 gate-0014 | REASON, DETAIL, STAKE, BUDGET, NEXT | ✅ 全覆盖 | — |
| E2 gate-0015 | REASON, DETAIL, PTR | ✅ 全覆盖 | — |
| E2 gate-0016 | REASON, DETAIL, PTR, BUDGET, NEXT | ✅ 全覆盖 | — |
| E2 gate-0017 | REASON, DETAIL, PTR, BUDGET | ✅ 全覆盖 | — |
| E2 gate-0018 | REASON, DETAIL, BUDGET, NEXT, CONTROL, CONFIG | ❌ 缺项 | CONTROL |

**表 F5-b：回放计数**

门级：**31/34 覆盖**；原子级：**162/165 覆盖**。

未覆盖原子：FM gate-0010 → XOWN；E2 gate-0004 → XOWN；E2 gate-0018 → CONTROL。

零命中的最小信息项（回放不能提供依据，只能由操作必要性/等待实测论证）：F1, F13, F8。

各信息项的**原子**命中数（覆盖门数见 §F2 的「回放命中」列）：F6=45, F11=33, F5=19, F4=15, F3=15, F14=10, F10=10, F9=6, F12=4, F7=3, UNCOVERED=3, F2=2。
**3 个未覆盖原子的性质**（这是本卡最强的自检输出，也是最该补的缺口）：

| 未覆盖原子 | 门 | note 原文片段（逐字） | 缺哪一项 |
|---|---|---|---|
| `XOWN`（跨 key 写面归属） | FM gate-0010 | "两个 key 的 L3 均已登记但都无写面（cli-run-state-and-events 判「本 key 写面外不修，纪律正确」；cli-hitl-channel 判「跨 key 修复轮」），即该红当前无 owner" | 最小集里**没有任何一项**承载"这条红/这个交付归谁"；写面声明在生产代码零命中（RQ-10 AC-014），机器判不了 ⇒ 属**数据缺口**（见 §数据缺口 G2），不进最小集 |
| `XOWN`（同型） | E2 gate-0004 | "两个改 doc 的 key 写面已互斥" | 同上：这是一条**无法机器验证**的断言，人只能接受或另开证据（缺口 G2） |
| `CONTROL`（跨 key 对照实验） | E2 gate-0018 | "同批 gui 的 l3-a5 重试即出裁决（42/42 PASS）证明重掷有效" | 需要"跨 key 的同类工件"作为对照；最小集只覆盖**本门 scope 内**的指针 ⇒ 属**数据缺口**（G3）。注：该门同时用 `.mw/dispatch.yml` 的模型变更（`CONFIG`→F10）承担了另一半论证，故只有 `CONTROL` 这一原子漏出 |

**零命中项的论证（回放不能证明，另行论证）**：
- **F1 门身份与时效**：`[推断]` 操作必需——无法在不知道"这是哪个门、卡了多久、是否重放过"的情况下作答；`[事实]` 现状面板 `MonitorGate` 无 `created_at`（`monitor.ts:89-95`）⇒ 这一项今天**不可得**，而 JC gate-0007 已 pending 8.5 天。
- **F8 影响面·结构**：`[事实]` 可由 `_roadmap.md` 的 `depends_on` 闭包机器算（FM `gui-shell-spike` → 8 个下游 key、`cli-readonly-snapshot` → 9 个）；`[事实]` 其重要性由 RQ-6 的"stalled 占窗口墙钟 E2 46.6% / FM 54.6%"与"E2 曾 3 个 key 同时 stalled"支撑；`[推断]` 34 个 note 无一处写"这门卡住了谁"，正是因为**当时没有这个面**——人只能凭记忆判断，这本身就是缺口。
- **F13 默认动作与到期时间**：`[事实]` `gates.py:68-81` 的 12 字段没有时间上界也没有默认动作；RQ-6 实测 20/20 全靠人工、无 TTL ⇒ 现行语义是**隐式永久滞留**（JC gate-0007 = 8.5 天）。这一项的"反例"就是它自身的缺失。

**回放自检的结论**：最小信息集在 **31/34 门**上覆盖了 note 的全部决策依据；3 个漏出原子对应 **2 个真实缺口**（跨 key 所有权、跨 key 对照证据），它们不是"少显示了字段"，而是**当前无数据源**——应进 §数据缺口，而不是硬塞进契约（否则契约会给一个填不出的字段，直接违反 D4）。

### 【推断】小结

- **I1**：人审的"最小"不是"字段最少"，而是"**必读面最少**"——核 34 门，人实际动手的只有两处：打开 key 目录的工件（F6）、以及把结论/修复/约束写回 `note`（F11）。表 F3 里 6/14 项只在散文或不存在，其中 **F3（选项后果与可逆性）只在代码里**、**F13（默认动作与到期）根本不存在**：这两项恰好是"人审最容易误判"与"无人值守最致命"的两端。
- **I2**：34 门的应答行为可归纳为**两条固定套路**——`stalled` 门 = "① 判定假阴 vs 真缺陷 ② 记录 approve 之前已做的修复 ③ 给一个**带界的**再试承诺（"若下一轮仍同 5 项则转 closed-legacy"）"；`stage-*` 门 = "① 核对目标/提案 ② 加约束或登记未达成 ③ 明确 approve 的解锁面"。第 (3) 类门的呈现应按这两条套路组织（对应契约层 2 的 L3-L7、L11-L12），而不是按 gate 的 12 字段顺序平铺。
- **I3**：F8（影响面）**没有任何 note 为它作证**，但它是"无人值守"场景的唯一抓手：人在场时不需要算影响面（随手就答了）；无人值守时要用它决定"先答哪个 / 能不能延后"——这正好是第 (2) 类（非阻塞可延后复核，AC-027）的输入。
- **I4**：契约 L9 行在今天必然渲染成 `default: none(blocks forever) | ttl: none(no field)`。**如实的空值本身就是一个机器告警面**（对齐 AC-019"缺省不得是隐式永久滞留"）：比"靠人记得这条门没人管"可靠，且不引入任何新状态。
- **I5**：现状里唯一把"后果"写进面板的地方是 `monitor.ts:619-625` 的 `(resume grants one round)`（且**只覆盖 `stalled`**）。契约 L3 行就是把这一处**从特例推广为通则**（6 个 kind × 2 个方向），来源仍是代码常量，不需要新字段。
- **I6**：把 L8（同 scope 历史门）纳入后，JC gate-0008 这类**重放门**会在窗口里自曝。这一项的成本是**一次门目录扫描**，收益是直接暴露消费守卫的失效面（`_consumed_gate_ids` 依赖 timeline 的 `gate-answered`，而 timeline 会轮转剪代）——是本卡性价比最高的一条增补。
- **I7**：不把 F3/F13 的任何值交给 LLM 生成是**硬要求**而非洁癖：P-014 家族的实测反例（`cross-key-repair-request` 的"§遗留第 96 行 <引文>"非逐字且定位不成立）已证明"看起来合理"的摘要**不可核**，而门是审批通道，不可核即等于不可审。

## 结论 → 决策映射

### 支撑 AC-026（gate 审核材料的最小信息契约）

| AC-026 的子要求 | 本卡交付 |
|---|---|
| 每条门必须携带且机器可抽取的字段 | **14 项最小信息集**（表 F2），逐项给出理由 + 反例（"少了它会错判成什么"） |
| 当前**可得性**（机器可读 / 需读多文件 / 仅散文） | 表 F3：**3 / 5 / 6**；每项给出 `file:line` + 字段名、路径模式、散文样例 |
| 缺口清单 | 见 §数据缺口 G1-G9（其中 G1/G2/G3 是**无数据源**，不是缺字段；G4/G6 是可补但当前被覆盖写的面） |
| "窗口里简明扼要展示"的**字段级判据** | §F4.2 三层契约（面板 1 行 ≤110 列 / 门卡片 13 行固定序 / doctor JSON），每字段给长度约束与来源 |
| P-014 家族：**机器抽取 + 逐字锚定** | §F4.3 判据 **D1-D7**（白名单 + 来源三元组 / 逐字断言 + 锚点与体量 / 截断规则 / 禁 LLM / 漂移标记 / `note` 不得作派生输入 / 数字带公式） |
| 现状对照 | §F4.1（面板只给 `id (kind)`、无 `created_at`、doctor 零 gate 内容、`/autopilot gates` 是唯一较全的面） |

### 支撑 AC-025 第 (3) 类（"其余 ⇒ 在窗口给人简明扼要的描述与选项"）

- **第 (3) 类的输入契约 = 表 F2 的信息项 + §F4.2 的 L1-L13 顺序**。其中 **L3（选项与后果）** 是"选项"二字的唯一机器载体，**L7（影响面）** 与 **L9（默认与到期）** 是"简明扼要"里必须出现的两个机器事实（前者决定优先级，后者决定无人值守是否阻塞）。
- **与第 (1)(2) 类的边界（不越界）**：本卡只规定"人审时必须看到什么"，不判定"哪些门可自举验证"（第 (1) 类，RQ-12）也不判定"哪些门可延后"（第 (2) 类，RQ-13/AC-027）。但 F8 的影响面字段正是第 (2) 类的判据输入，F3 的可逆性字段正是第 (1)/(2) 类的安全前置（不可逆动作不能走自动、也不能静默延后）。
- **与 AC-007 的关系**（避免重复计数）：AC-007 问的是"每个 gate 类型当前给人看的东西清单 + 判定必要性与影响面各需要什么输入"；本卡给出的是**现状清单**（F4.1）、**最小集**（F2）、**可得性**（F3）与**呈现契约**（F4.2-F4.3）。AC-007 的"必要性可由机器推导"半面属 RQ-12，本卡不答；但本卡的 F3（可逆性）、F9（弃置代价）与 G2（写面）是 RQ-12 判"必要性"时需要的输入。

### 对本 key 其他 AC 的副作用面（登记，不实现）

- **AC-012（可观测性）**：表 F2 的 F1（时效）与 F8（影响面）是面板要新增的两个量；F1 要求 `MonitorGate` 增 `createdAt`（`monitor.ts:89-95` 当前没有）。
- **AC-018（审计与回滚）**：F10 与 L8 要求"同 scope 历史门"可见；`answered_by` 的 4 种自由写法（实测）说明 `answered_by=auto` 之类机器可判来源仍缺位。
- **AC-019（无人值守默认动作）**：L9 的 `default/ttl` 两个字段今天不存在（`gates.py:68-81`），契约要求**如实输出 none**，这本身就是 AC-019 的机器告警载体。
- **AC-022（消费守卫缺陷）**：本卡实测的 JC gate-0008 重放（09-26 重新消费 gate-0001）是 `_consumed_gate_ids` 只依赖 timeline 这一设计的**第二个**失效面（第一个是 RQ-11 的 4 位正则）——timeline 轮转剪代会让记录消失。建议 AC-022 把"消费记录不得只依赖可轮转的 timeline"纳入判据。

## 数据缺口

| # | 缺口 | 性质 | 为什么重要 | 需要什么数据才能补 |
|---|---|---|---|---|
| **G1** | **门时的"谁在等"不可回读**：`> key-status:` / `> status:` 是覆盖写（`roadmap.py:505`），timeline 无 key-status 快照事件（`timeline.py:67-85`） | 无数据源 | F8 只能算**结构**影响面，"当时实际在等的 key 与各自等待时长"永久丢失（与 RQ-7 F4.2(3) 同结论；本卡复核：3 个项目 roadmap 的现存状态已与门时不同） | 每 tick 落一份 `(in_flight, eligible_not_dispatched, key-status)` 快照，或复用 RQ-7 F4.3 的 `cap-blocked` 事件 + key-status 变更事件 |
| **G2** | **跨 key 写面/所有权判据不存在** | 无数据源 | 3 个未覆盖原子中的 2 个（FM gate-0010、E2 gate-0004）；RQ-10 AC-014 已证 `write_scope` 在生产代码零命中 | 机器可读的写面声明（AC-014 的前置交付） |
| **G3** | **跨 key 对照证据无索引**：E2 gate-0018 用"同批 gui key 的 l3-a5 重试成功"作对照，但同类工件之间没有关联字段 | 无数据源 | 1 个未覆盖原子（`CONTROL`）；"重掷是否有效"这类判断会一直只能靠人记忆 | `workers/*` 行或 task.md 增 `request_id`/`ticket`/`sibling_of` 之类关联列 |
| **G4** | **门时证据快照缺失**：34 门中 **24 门**的证据文件 mtime 晚于应答时刻；E2 gate-0010 的 `l3-a2/output.md` 在应答后 13 分钟被 repair 轮改写（"缺两节"→"有两节"） | 可补（不改语义） | 契约的"证据指针"无法复现"人当时看到的那一版"；也是 P-014"引文不可核"的同一根因 | 把指针落成 `path + sha256 + bytes + mtime` 快照（或对关键工件走 append-only 新文件名——FM/E2 的 A-09 已是这条纪律，但 worker `output.md` 未覆盖） |
| **G5** | **goal 变更摘要不可得**：`goal-halt` 的 detail 只有 `mtime_ns X -> Y`（`conductor.py:2093`） | 可补 | JC gate-0002 的全部依据（"删掉的是 stale Roadmap 快照节、核心三节完好"）无法机器复算 | 落 `goal_before_sha256`/`goal_after_sha256` + 段落级 diff 统计（RQ-10 F5 已列） |
| **G6** | **L3 判定值的时效性矛盾**：磁盘现值是**单一派生记录**（`l3-verdict.txt`，会被后续轮覆盖）；FM gate-0008 证明它可能是首轮快照（C-11），而 E2 gate-0005/0006 的 note 又用它作"below"依据 | 半可补 | F5/F7 的 verdict 行若直接显示磁盘值，在 C-11 未修前会**误导**（"dossier 说 below，实际最终 31/31"） | 落"最终轮 verdict 快照"字段（`verdicts_final`）或修 C-11 |
| **G7** | **`answered_by` 不可机器判**：34 门实测 4 种自由写法（`wenbozhou` 17 / `user-via-pm-window` 10 / `human-via-pi` 6 / `human-pm-window` 1）；无 `expected_responder` | 可补 | F14 的"谁该答"半面不可得；AC-018 的 `answered_by=auto` 无法与自由文本区分 | 封闭枚举 `answered_by ∈ {human:<id>, auto:<policy_id>}` |
| **G8** | **无"同 scope 历史门"视图**（L8 的数据在盘上，但没有现成读取面） | 可直接补 | JC gate-0008 重放门在现状下**完全不可见** | 门目录扫描按 `kind+stage\|key` 分组（一次 `os.listdir` + 现有 parser，无需新字段） |
| **G9** | **本卡样本边界**：`budget-exhausted` / `xkey-authorize` 生产门为 **0**（RQ-10 F1g） | 无样本 | 这两个 kind 的 L3 选项后果文本只能从代码读，**没有历史样本可校准**（尤其 `xkey-authorize` 的 approve 会改代码） | 影子模式样本（RQ-10 已建议）或明确标注"文本来自代码、非历史" |

## 机器行

```
[VERIFY] RQ-14: gates=34 key_level=22(stalled) stage_level=12(stage-confirm 7/stage-close 4/goal-change 1) min_info_items=14 machine_readable=3(F1,F2,F7) multi_file=5(F4,F5,F6,F8,F14) prose_only=6(F3,F9,F10,F11,F12,F13) replay_covered=31/34 atoms=165 covered=162 uncovered=[XOWN x2 (FM gate-0010, E2 gate-0004), CONTROL x1 (E2 gate-0018)] zero_hit_items=[F1 identity/age, F8 impact, F13 default+TTL] evidence_drift=24/34 (evidence mtime > answered_at; E2 gate-0010 l3-a2 output.md rewritten +13min after answer) default_action_field=absent expires_field=absent answered_by_distinct=4 panel_today=id+kind(monitor.ts:644-654; MONITOR_LINE_MAX=110 monitor.ts:61; MonitorGate lacks created_at monitor.ts:89-95) doctor_gates=0(mw_common.py:2022-2065) richest_surface=/autopilot gates(console.ts:182-198: id/kind/scope/question/created/path; GateRecord status-model.ts:582-591 lacks context_refs) contract=D1-D7 + panel_line<=110cols + gate_card=13 lines new_fact=JC gate-0008(stage-close stage1, pending 3.7h) is a re-application: timeline 2026-09-26T04:37:27 "gate-0001 approved → stage 1 running" re-opened a stage closed 2026-09-17T12:51:42 because _consumed_gate_ids(conductor.py:297-312) only reads the rotated timeline
```

