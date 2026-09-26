# Research: gate 的证据可自举验证性审计（RQ-12 / key `mw-autopilot-slot-capacity`）

> 角色: spec 期调研（**只读**；本文件是本卡唯一写面：不 commit、不改代码、不答 FM/E2/JC 的任何 gate）。
> 代码基线: `H:/git/Multi-Workers` HEAD `4ef71e0539dfd7c697e552066c4784be8dc092b1`（与 RQ-10 同基线）。本文件所有 `file:line` 为 HEAD 工作树快照。
> 数据快照: **2026-09-26T08:14:32Z**（`python -c "...utcnow()"` 实测；FM/E2 当时仍在跑，gate 目录最后一笔写为 E2 `gate-0018.md` mtime 2026-09-26T06:52:21Z）。
> 边界: 不重复 RQ-10 的**答案分布统计**；不重复 RQ-8 的门清单/阻塞范围/等待时长；不做 RQ-11 的护栏机制。本卡只做"**命题—证据—可独立复算性—防伪绑定—最小附加字段**"这条线。
> 与 RQ-10 的差: RQ-10 的结论是"人写了什么、机器能不能读"；本卡把每类门的**命题**拆成可判子命题，逐条给出**机器复算结果**（含 6 处"机器复算与记录/人工判定不一致"的实测），并给出 `stage-close` 前置集的**充分性反例**。

## TL;DR

1. **6 类门里没有一类是"命题完全可自举"的**；只有 `budget-exhausted` 的**命题面**可完全复算（`used` 对 `limit`、"仍有缺口"来自 L1 dossier），剩下 4 类（`stage-confirm`/`stage-close`/`stalled`/`xkey-authorize`）只**部分**可自举（描述性子命题可复算，审批依据不可），`goal-change` **完全不可自举**。
2. **驱动差异的不是"字段缺失"而是"命题性质"**：`stage-close` 的命题主语"全部 key 已终态"**就是 conductor 建门的触发条件本身**（`conductor.py:629-631` vs `:650-656`）⇒ 机器复算必然为真、零信息量；`stage-confirm` 的命题"该 stage 该不该启动"是**策略判断**；`stalled` 的命题核心是"**假阴 vs 真缺陷**"——≥16/22 条 note 记录的带外修复只存在于散文（RQ-10 F1f）。**"可自举"不等于"能自动答"**：可自举的子命题恰好不是人答的那个。
3. **RQ-10 的 `stage-close` 前置集不充分（实测反例 4 个）**：`verdicts-final==meets ∧ open_items==∅ ∧ 无 closed-legacy` 在磁盘上可满足而命题为假 —— 最硬的两个是：**E2 Stage 2 的 `feature-l3-readcap-injection`**（correction sidecar 明写 `corrected_value: below` + `counted_as_done: false`，而它的 `l3-verdict.txt` 是 `meets`、roadmap 是 `done`、stage 已 `closed`）与 **JC Stage 2**（唯一 key `done`/`meets`/无 closed-legacy，但该 stage goal 明文要求 Rider 实机人工验收，stage-close 已挂 **9.5 天**）。
4. **`l3-verdict.txt` 不能当"最终裁决"用（实测 6/22 key 与现行复算不一致）**：`FM/gui-shell-spike` 文件 `below` 而复算 `meets`（C-11 陈旧，人工 31/31 被机器复算证实）；`FM/gui-contract-mock-tests` 文件 `meets` 而复算 `below`（失败行是 `PASS ... 0 FAIL —` 这种散文行，**机器假阴**）；`E2/feature-l3-readcap-injection`、`E2/feature-sampling-human-channel` 文件 `meets` 而 correction sidecar 说 `below`。⇒ 任何"自举校验"必须先定义**取证源优先级 + 解析器版本**，否则同一命题会得到相反答案。
5. **已有可复用的防伪原语**（别重造）：`l3-verdict-provenance.json`（`conductor.py:1246`，含 `source_mtime_ns`/`anchor_path`/`anchor_mtime_ns`/`suspect`/`verdict`，按 `task_key` append-only 去重，slack 60s，`conductor.py:1410`）；correction sidecar（`*-correction-*.json` + `original_sha256`/`corrected_value`/`counted_as_done`）。**两者的共同缺口是覆盖面**：provenance 只在 FM 2 个 key / E2 2 个 key 存在（2026-09-26 之后），correction 只在 E2 3 个 key 存在（且由**项目 key** 自建、非框架）。
6. **签名式证据不可信**：`answered_at` 与 `answered_by` 都是应答者可写字段（`gate-writer.ts:139` 是"合法路径之一"，手改同等合法 `gates.py:1-20`）；实测两处污染（E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s），且 **`context_refs[1]` 的 reason 文本随 conductor 版本漂移**（实测 3 种格式：E2 `(budget 2)` / FM `(budget 2, credits 0)` / JC 的 `exhausted` 文本按现行为复算应为 `3/3` 而写的是 `2/2`）。⇒ 自举验证必须以 **gate 文件 mtime + 结构性字段 + 产物哈希**为准，不得引用 gate 自身的文本与时间戳。

## 决策问题

用户三分处置模式的第 (1) 类判据是"**硬需求且审批内容可自举验证 ⇒ 机器独立复算证据，不给人答**"。据此本卡要回答 5 个问题，全部只针对**证据链**：

1. **命题**：每类门要人判断的命题的**原文**是什么（gate 字段值 / `gates.py:54-61` schema / conductor 建门处代码注释与 detail 文本）？命题有几层（描述性子命题 / 决策）？
2. **证据**：判这个命题需要哪些事实？这些事实落在磁盘哪里（gate 字段 / roadmap / dossier / `l3-verdict.txt` / timeline 事件 / `_workers.parallel` / task.md / 产物）——逐项 `file:line` + 字段名 + **真实样例值**？
3. **可复算性**：机器能否**独立**推出命题真假？分类为 **可自举 / 部分可自举（指明不可判的部分）/ 不可自举**，并给判据。特别：**RQ-10 的 `stage-close` 前置（verdicts-final + open_items 空 + 无 `closed-legacy`）是否充分？** 给"满足前置但命题为假"的实例。
4. **防伪绑定（风险 20）**：对每个"可自举"的门，需要哪些校验（时间戳阈值 / 与代码或产物的哈希绑定 / 来源字段）才能接受证据？用 RQ-10 实测的两处污染（verdict 陈旧、`answered_at` 回填早 4.1h）作反例说明不校验会怎样误判。
5. **最小附加字段**：要让某门变为"可自举"，必须新增哪些字段（字段名 / 类型 / 写入点 `file:line` / 谁写 / 如何防伪）？

## 调研方法与出处

### 代码（只读；行号 = HEAD `4ef71e053`）

| 面 | 位置 |
|---|---|
| gate 闭集 6 类 / 状态闭集 / 12 字段 schema / 必填集 | `autopilot/gates.py:54-61`、`:63`、`:65`（`CREATED_BY="conductor"`）、`:68-81`、`:86-89`；TS 镜像 `status-model.ts:561-567`、`:572-587` |
| gate 文件渲染（body = 问题原文 + `## Context`） | `gates.py:159-175`（`_gate_file_content`） |
| gate 创建 + 未知字段 fail-closed | `gates.py:262`（`create`）、`:347`（`unknown frontmatter field`）；TS 同规则 `status-model.ts:660-661` |
| 应答写入（只改 4 行；`answered_at` 可被 override） | `gate-writer.ts:139`（`answerGate`）、`:75-84`（`answeredAt?`/`answeredBy` 选项）；CLI 不传 override `console.ts:204-245` |
| 消费（approve/reject 效果） | `conductor.py:316`（`_consume_answered_gates`）、`:297`（`_consumed_gate_ids`，正则 `gate-\d{4}`）、`:2295`（`_apply_stalled_approvals`）、`:2363`（`_apply_stalled_rejections`）、`:2216`（`_budget_bonus`）、`:2228`（`_budget_gate_rejected`）、`:2798`（`_consume_xkey_gate`） |
| `stage-confirm` 建门 | `conductor.py:426-431`（`_ensure_next_stage_gate`）、`:492-497`（`_create_stage_confirm_gate`）、`:454-487`（`_activate_pending_stage`）、`:520-560`（`_dispatch_roadmap_writer`，提案由 LLM 产出）、`:562-577`（`_roadmap_writer_prompt`，模板含 `> goal_mtime: <ms>`） |
| `stage-close` 建门 + 触发条件 + dossier | `conductor.py:616-656`（`_stage_closure`，终态集 `("done","closed-legacy")` 在 `:629-630`）、`:659-671`（`_l3_verdict`）、`:722-750`（`_closure_dossier_md`，`evidence` 列是**字面串** `:744`）、`:675-720`（`_persist_l3_verdict`） |
| `stalled` 建门 + 12 个触发点 | `conductor.py:3944`（`mark_stalled`）、`:3971-3975`（问题与 refs）、调用点 `:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941` |
| `budget-exhausted` 建门 | `conductor.py:995-1000`（问题文本在 `:998`） |
| `goal-change` 建门 + 检测 + 恢复 | `conductor.py:2050`（`tick`）、`:2063-2095`（mtime 比对 + `gates.create` + `goal-halt` detail）、`:2100-2111`（**不判 status，只判是否仍 pending**）、`:174`（`open_goal_change_gate`）、`:4138-4139`（启动 baseline 快照） |
| `xkey-authorize` 建门 + 票据 + 消费 | `conductor.py:2724-2745`（`_xkey_ensure_gate`，问题文本 `:2741-2742`）、`:2641-2700`（ticket JSON 字段）、`:2798-2855`（`_consume_xkey_gate`） |
| 轮次计数（复算 `used`） | `state.py:224-249`（`used_rounds`：`{key}/workers/*/task.md` 的 `loop:`/`attempt:` 标签去重计数） |
| roadmap 语义校验（**未被 conductor 调用**） | `roadmap.py:367-425`（`validate_roadmap`）、`:505-533`（`update_key_status`，docstring 明写 `callers should initialize entries for all stage keys when a stage starts running`）；唯一调用点 `roadmap_check.py:50`（独立 CLI） |
| timeline 事件闭集 | `timeline.py:67-85`（`EVENT_TYPES` 17 类） |
| worker 队列行（8 列，**无 writer/origin 列**） | `worker-store.ts:22-37`（`WorkerEntry`）、`:39-51`（`parseWorkerLine`，容忍 7 列遗留行） |
| 门在窗口/面板上"给人看的东西" | `console.ts:182-198`（`/autopilot gates`：id/kind/scope/`question`/`createdAt`/path）、`monitor.ts:89-95`（`MonitorGate` **只有 id/kind/stage/key**）、`:147-180`（`scanPendingGate` 只读 5 个字段） |
| 已有防伪原语 | `conductor.py:1214`（`_L3_FAIL_RE`）、`:1220`（`_L3_FAIL_ZERO_RE`）、`:1223-1240`（`_l3_fail_marker_line`）、`:1274-1290`（`_l3_resolve_source`）、`:1246-1248`（`_PROVENANCE_FILENAME`/`_L3_TRACE_NAME`/`_PROVENANCE_SLACK_SEC=60.0`）、`:1356`（`_l3_provenance_record`）、`:1451`（`_persist_l3_provenance`） |

### 数据（只读；3 个项目）

| 项目 | 根 | gate 文件 | roadmap | 备注 |
|---|---|---|---|---|
| FM | `E:/CLI_workspace/FeatureMigrator` | 10（全 answered）+ 归档洪泛 6684 | Stage1 `closed` / Stage2 `running`(2/5 key 有 key-status) / Stage3 `pending` | `.agenticdoc/goal.md` **untracked**（`git status --porcelain` → `?? .agenticdoc/goal.md`） |
| E2 | `H:/git/E2Feature` | 18（全 answered） | Stage1/2 `closed`、Stage3 `running`(8/10 key) | `.agenticdoc/goal.md` **tracked**（唯一提交 `7200dfb 2026-09-20 16:57:59 +0800`） |
| JC | `H:/git/JCodingAss` | 8（6 answered + **2 pending stage-close**） | Stage1 `running`、Stage2 `running` | **无 `.git`**；timeline 早期代被轮转剪掉（goal 类事件 0 条） |

### 复算方式（全部可复现，只读）

1. **gate 字段**：`gates.parse()`（`gates.py:405`）/手写 frontmatter 扫描；行号 = gate 文件行号。
2. **轮次复算**：`state.used_rounds(all_workers_dirs)`（`state.py:224`）＝ `{key}/workers/*/task.md` 的 `loop:` 标签分组后 `attempt:` 去重计数；交叉源 = timeline `dispatch` 事件 detail（`ap-<key>-<stem> type=<role> loop=<loop> attempt=<N>`）。
3. **L3 裁决复算**：`conductor._l3_resolve_source(conductor._l3_source_paths(key_dir, "ap-<key>-l3-a<N>"))`，`N` = 该 key 现存 `l3-a*` worker 目录的最大编号；与 `l3-verdict.txt` 对照。
4. **roadmap 复算**：`roadmap.load_roadmap` + `roadmap.validate_roadmap`（同一函数，`roadmap.py:367`）。
5. 最小脚本（本次实际执行过，只读）:

```python
import sys, pathlib, re; sys.path.insert(0, "H:/git/Multi-Workers/packages/multi-workers")
from autopilot import conductor, roadmap
base = pathlib.Path("<root>/.agenticdoc")
for kd in sorted(p for p in base.iterdir() if p.is_dir()):
    w = kd / "workers"
    if not w.is_dir(): continue
    rounds = [(int(m.group(1)), d.name) for d in w.iterdir()
              if (m := re.fullmatch(re.escape(f"ap-{kd.name}-l3-a") + r"(\d+)", d.name))]
    if not rounds: continue
    n, tk = max(rounds)
    srcs = [(p, t) for p in conductor._l3_source_paths(kd, tk)
            if (t := conductor._l3_read_source(p)) is not None]
    print(kd.name, n, conductor._l3_resolve_source(srcs)[0],
          (kd / "l3-verdict.txt").read_text().strip())
```

## 发现

### 【事实】

#### F-1 六类门的命题原文（逐字；含建门代码与 detail 文本）

| kind | 命题原文（gate 文件的 `question` 字段值 = `gates.py` 建门实参） | 建门点 | 门上的其他字段 |
|---|---|---|---|
| `stage-confirm` | `Stage {N}（{K} 个 key，目标：{goal}）提案已写入 _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案`<br>变体（stage 关闭后自动开下一阶段）：`Stage {N}（{K} 个 key，目标：{goal}）已就绪——确认启动该 stage？…` | 代码 `conductor.py:492-495` / `:427-429`；实例 `E2/gates/gate-0001.md:8`、`FM/gates/gate-0009.md:8`、`JC/gates/gate-0006.md:8` | `stage: N`、`key:`（空）、`context_refs: [stage-N]` |
| `stage-close` | `Stage {N} 全部 key 已终态，闭环 dossier 已写入 .agenticdoc/_autopilot/stages/stage-{N}-close.md——确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理` | 代码 `conductor.py:650-654`；实例 `FM/gates/gate-0008.md:8`、`E2/gates/gate-0003.md:8`、`JC/gates/gate-0007.md:8`、`JC/gates/gate-0008.md:8` | `stage: N`、`context_refs: [stage-N]` |
| `stalled` | `key {K} 已 stalled（{reason}）——遗留关闭（closed-legacy），还是人工介入后重试？` | 代码 `conductor.py:3971-3973`；实例 `FM/gates/gate-0002.md:8`、`E2/gates/gate-0014.md:8`、`JC/gates/gate-0003.md:8` | `key: K`、`context_refs: [".agenticdoc/K", "<reason>"]`（`conductor.py:3974`；render 后落在 gate 文件 `:10-11`） |
| `budget-exhausted` | `L2 回路 {loop} 已达 {limit} 轮上限且仍有缺口——追加一轮修复，还是标记 stalled？` | 代码 `conductor.py:996-999`；**生产 0 实例**（FM/E2/JC 均无） | `key: K`、`context_refs: [{loop}]` |
| `goal-change` | `goal.md changed while autopilot is active — review the new goal and approve resuming, or reject to stay halted.` | 代码 `conductor.py:2085-2090`；实例 `JC/gates/gate-0002.md:8` | `key:`/`stage:` 均空、`context_refs: ["H:\\git\\JCodingAss\\.agenticdoc\\goal.md"]`（`JC/gates/gate-0002.md:10`） |
| `xkey-authorize` | `跨 key 红 {file}::{test_id}（owner {owner_key}）请求解冻授权：追认后由框架执行受限修复，拒绝则留账本。` | 代码 `conductor.py:2739-2744`；**生产 0 实例** | `key: owner_key`、`context_refs: [request_id, ticket_rel]` |

**schema 侧原文**（`gates.py:68-81`，12 字段、顺序即契约）:

```
id, kind, stage, key, created_at, created_by, question, context_refs,
status, answered_at, answered_by, note
```

`gates.py:86-89` 必填集 = `{id, kind, created_at, created_by, question, status}`；`gates.py:54-61` 的 `GATE_KINDS` 闭集；`gates.py:1-20` 的模块 docstring 给出角色规范原文：`create: conductor only` / `answer: TS side /autopilot gate rewrites status/answered_at/answered_by/note. Manual file edits are equally legal answers: the file is the source of truth (review B5), and Python only reads.`

**conductor 侧的 detail 文本原文**（不进 gate 文件，只进 timeline）:

- `goal-halt`：`detail=f"goal.md mtime_ns {st.goal_baseline} -> {current}"`（`conductor.py:2093-2094`）
- 启动 baseline：`tl.append("goal-snapshot", detail=f"startup baseline mtime_ns={st.goal_baseline}")`（`conductor.py:4139`）
- `gate-created`：`f"{path.stem} kind={kind}"`（`conductor.py:2183-2185`）——**不含 question、不含 reason**
- `stalled`：`detail=reason`（`conductor.py:4032`）
- `stage-close`：`f"dossier stage-{N}-close.md written"`（`conductor.py:647-648`）

#### F-2 每类门的证据落点与真实样例（逐项 `file:line` + 字段 + 值）

**（a）`stalled`** —— 判定命题需要的 4 组事实：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| key 确实处于 `stalled` | `_roadmap.md` `> key-status:` 行 | `key=stalled` | 判据 `roadmap.py:63-68`、写点 `conductor.py:3955-3962` |
| reason 文本 | gate `context_refs[1]`（`refs=[".agenticdoc/K", reason]`，`conductor.py:3974`） | 散文串（部分被 `_one_line` 截到 300B，如 `conductor.py:908-912`） | `FM/gates/gate-0002.md:11` = `L3 below 2 rounds (budget 2, credits 0)`；`FM/gates/gate-0006.md:11` = `exec task 005-frozen-package-and-thresholds exhausted 2/2 attempts`；`E2/gates/gate-0014.md:11` = `L3 below 3 rounds (budget 2, credits 1)`；`FM/gates/gate-0004.md:11` = `advance verify->done 连续 5 次失败（class=gate-blocked；gate-blockedx5）: GATE BLOCKED: …` |
| 轮次 `used` | `{key}/workers/*/task.md` frontmatter `loop:`/`attempt:` | 整数对 | FM `gui-skeleton-shell/workers/ap-gui-skeleton-shell-005-frozen-package-and-thresholds/task.md` → `loop: exec:gui-skeleton-shell:005-frozen-package-and-thresholds \| attempt: 1`；同 loop 的 `-a2` → `attempt: 2`；`-a3` → `attempt: 3`（⇒ gate-0006 时点 `used=2`） |
| 轮次交叉源 | timeline `dispatch` 事件 detail | `loop=`/`attempt=` | FM `timeline.jsonl.1:574` = `2026-09-23T09:43:08+00:00 dispatch gui-shell-spike 'ap-gui-shell-spike-spec-writer-a1 type=phase-writer loop=gen:gui-shell-spike:spec attempt=1'` |
| `limit` = `round_budget + credits` | `config.json` + `_resume_credits` | int | FM `config.json` = `"round_budget": 2`；`credits` = 该 key 的 **approved** `stalled` gate 计数（`conductor.py:2288-2292`）。E2 `feature-gui-time-mvp-board` 在 gate-0014 时点：gate-0011 `status: approved`（`E2/gates/gate-0011.md:12-13`）⇒ credits=1 ⇒ limit=3，与 `E2/gates/gate-0014.md:8` 的 `3 rounds (budget 2, credits 1)` 一致 |
| 附带产物（机器生成） | `{key}/achieved.md` 的 `## 遗留问题（stalled 草稿）` 段 + `patterns/{key}/stall-lesson.md` | 散文 | 写点 `conductor.py:3977-4030` |

**（b）`stage-close`**：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| 全部 key 终态 | roadmap `> key-status:`（终态集 `done`/`closed-legacy`，`conductor.py:629-630`） | enum | FM Stage1 `> key-status: gui-contract-surface=done, gui-shell-spike=done, cli-readonly-snapshot=done, gui-contract-mock-tests=done, gui-skeleton-shell=done` |
| dossier 存在 + 内容 | `.agenticdoc/_autopilot/stages/stage-{N}-close.md` | 表格 5 列 | `FM/…/stages/stage-1-close.md:9-15`：`\| key \| final phase \| l3 verdict \| l3 report \| evidence \|`；行样例 `\| gui-shell-spike \| DONE \| below \| E:\CLI_workspace\FeatureMigrator\.agenticdoc\gui-shell-spike\l3-report.md \| .agenticdoc/gui-shell-spike/achieved.md \|` |
| key 的最终 L3 裁决 | `{key}/l3-verdict.txt`（写点 `_persist_l3_verdict`） | `meets`/`below` | `FM/gui-shell-spike/l3-verdict.txt` = `below`（mtime 2026-09-23T11:48:31Z）；`FM/gui-contract-surface/l3-verdict.txt` = `below`（mtime 2026-09-23T11:10:29Z）；`E2/feature-tier-a-closeout/l3-verdict.txt` = `meets`（mtime 2026-09-24T16:47:33Z） |
| 该裁决的**刷新记录** | timeline `config` 事件，detail 前缀 `l3-verdict ` | 散文串 | FM `timeline.jsonl` = `2026-09-25T04:14:55+00:00 config gui-skeleton-shell 'l3-verdict none -> meets (report from ap-gui-skeleton-shell-l3-a1)'`；E2 `timeline.jsonl` = `2026-09-26T06:41:55+00:00 config feature-gui-time-mvp-board 'l3-verdict below -> meets (report from ap-feature-gui-time-mvp-board-l3-a5)'` |
| 该 key 的最终轮判定源 | `{key}/workers/ap-{key}-l3-a{N}/output.md` / `report.md` | 两节 + FAIL 行 | `FM/gui-shell-spike/workers/ap-gui-shell-spike-l3-a3/output.md`（`## Quality Gate Report` 有、`## Achieved` 有、FAIL 行 0）；`FM/gui-contract-surface/workers/ap-gui-contract-surface-l3-a3/output.md:59` = `\| **FAIL** \| 被读取的记录与断言矛盾。本轮 **0 条**（不签发无据 FAIL，也不签发无据 PASS） \|` |
| 防伪锚 | `{key}/l3-verdict-provenance.json` | `source_mtime_ns`/`anchor_path`/`anchor_mtime_ns`/`suspect`/`verdict` | `E2/feature-gui-time-mvp-board/l3-verdict-provenance.json`：`{"round":"l3-a3","deciding_source":"workers/ap-feature-gui-time-mvp-board-l3-a3/report.md","source_mtime_ns":1790326518157135800,"anchor_path":"workers/ap-feature-gui-time-mvp-board-l3-a3/trace.log","anchor_mtime_ns":1790326569499869300,"suspect":false,"raw_verdict":"below","verdict":"below",…}` 与 `{"round":"l3-a5",…,"raw_verdict":"meets","verdict":"meets",…}` |
| 项目侧纠正账本 | `{key}/*-correction-*.json`（**非框架产物**，由 E2 的 `feature-false-meets-remediation` 工具链生成） | `original_value`/`original_sha256`/`corrected_value`/`counted_as_done` | `E2/feature-l3-readcap-injection/l3-verdict-correction-fm-136c65a70b2b.json` = `{"original_value":"meets","original_sha256":"1e01e3da…","corrected_value":"below","recorded_path":".agenticdoc/feature-l3-readcap-injection/l3-verdict.txt","corrected_basis":"landed recompute verdict (same run_id)","counted_as_done":false,…}` |

**（c）`stage-confirm`**：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| stage goal 原文 | `_roadmap.md` `## Stage N:` 段 `> goal:` | 散文 | `E2/_autopilot/_roadmap.md` `## Stage 3: Phase A3 …` / `> goal: 把 switch_ready=false 里机器可做的部分全部闭掉…` |
| key 数 / key 表 / 依赖 | `### Keys` 表格 | `key\|role\|depends_on` | `FM/_roadmap.md` Stage2 行 `\| gui-monitor-hitl-e2e \| verify \| gui-live-monitor, gui-run-control-hitl \|` |
| 提案合法性 | `roadmap.validate_roadmap`（`roadmap.py:367-425`） | `list[str]` problems | **实测（本文脚本）**：`E2` → `['stage 3: key-status missing key(s): feature-gui-contract-respec, feature-switch-readiness-closeout']`；`FM` → `['stage 2: key-status missing key(s): gui-live-monitor, gui-monitor-hitl-e2e, gui-run-control-hitl']`；`JC` → `[]` |
| 提案人 | roadmap-writer（LLM，role=phase-writer） | task.md `type: roadmap-writer` | `FM/timeline.jsonl.1:3` = `dispatch - 'ap-_scratch-roadmap-s1-a1 type=roadmap-writer loop=roadmap:stage-1 attempt=1'` |
| goal 版本绑定（**几乎无用**） | `_roadmap.md` 头 `> goal_mtime:` | ms 整数，**由 roadmap-writer LLM 填**（模板 `conductor.py:597`，解析 `roadmap.py:73`） | FM `> goal_mtime: 1790154315560`；实际 `goal.md` mtime_ns = `1790154315559875400`（= 1790154315559.875 ms）⇒ 差 1ms |

**（d）`budget-exhausted`**：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| L2 回路标签 | gate `context_refs[0]` | `l2:{key}:{edge}` | 生产 0 实例。**最近似在盘样本**：`E2/feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l2-tasks-to-execute-a1/task.md` → `loop: l2:feature-gui-time-mvp-board:tasks-to-execute \| attempt: 1`（`used=1 < limit=2` ⇒ 未触发建门） |
| `used` / `limit` | task.md 的 loop/attempt（同 (a)）；`limit = budget + credits` | int | `config.json` `"round_budget": 2`（FM/E2/JC 三项目同值） |
| "仍有缺口" | `audit_evidence.build_dossier` 的 `gaps[]`（`severity == "blocking"`）+ `_missing_plan_tasks`（`conductor.py:1990`） | `[{item, rule, severity}]` | schema `audit_evidence.py:10` = `gaps[{item, rule, severity}], generated_at}`；rules 原文 `audit_evidence.py:226-252`：`spec-missing` / `evidence-ref-missing` / `research-evidence-missing` / 一条 `severity:"non-blocking"` |
| approve 效果 | `_budget_bonus` 返回 True ⇒ 恰好 +1 轮且第二次直接 stall | bool | 代码 `conductor.py:2216-2227`、`:989-994` |

**（e）`goal-change`**：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| "变过" | mtime vs baseline | ns 整数 | FM 现 `goal.md` mtime_ns = `1790154315559875400`（2026-09-23T09:05:15Z）；`FM/timeline.jsonl.1:1` = `2026-09-23T09:06:44+00:00 goal-snapshot - 'startup baseline mtime_ns=1790154315559875400'` |
| 变更事件（含前后 mtime） | timeline `goal-halt` | 散文串 | **JC 的该事件已随早期 timeline 代被剪掉**（JC `timeline.jsonl.2` 最老 seq = 98074；实测 goal 类事件 **0 条**）；E2/FM 无 goal-change 门，故无 `goal-halt` |
| **"改了什么"** | —— | —— | **磁盘上不存在**：无 before-image 快照；FM `.agenticdoc/goal.md` 是 untracked（`git status --porcelain -- .agenticdoc/goal.md` → `?? .agenticdoc/goal.md`）；JC 无 `.git`。E2 的 goal.md 有 git 历史（`git log` → `7200dfb 2026-09-20 16:57:59 +0800 chore: init E2Feature partition skeleton`，仅 1 个提交） |
| reject 的效果 | `tick()` 只判"是否仍 pending" | 无 | `conductor.py:2100-2111`：`if gate_open or st.goal_halted: if gate_open: … return "halted-goal-change"` / `st.goal_baseline = current; st.goal_halted = False` ⇒ **approved 与 rejected 走同一分支**（reject 是 no-op） |
| 人工实际做了什么 | gate `note` | 散文 | `JC/gates/gate-0002.md:14` = `change was the user removing the stale 2026-09-10 Roadmap snapshot section (pending disposition decision, resolved as removal); core Goal/Context/Key Constraints verified intact; approve resume with refreshed baseline` |

**（f）`xkey-authorize`**：

| 事实 | 落点 | 字段 | 真实样例值 |
|---|---|---|---|
| 跨 key 红身份 | ticket JSON | `file`/`test_id`/`owner_key`/`source_key`/`dedup_key`/`request_id` | 代码 `conductor.py:2663-2700`；`request_id` = `"XKEY-" + sha1(dedup_key)[:12]`（`:2656-2658`）。**三项目 0 票据**（`Get-ChildItem -Recurse -Filter "*xkey*"` 仅 FM 命中 1 个 evidence 文本） |
| 冻结块与授权快照 | ticket | `frozen_block`/`authorization_snapshot`（整文件 sha256）/`target_file_sha256` | 代码 `conductor.py:2652-2653`、`:2691-2698` |
| 修复动作与验证命令 | ticket `verification` | `command`/`argv`/`cwd`/`timeout_s` | 代码 `conductor.py:2696-2706`；`cfg["xkey_verify_cmd"]`/`xkey_verify_timeout_s`（`config.py` 默认关） |
| **写面边界** | —— | —— | **不存在**：`write_scope` 在 `packages/multi-workers/autopilot/*.py` 与 `mw.py` **零命中**（仅 2 处测试函数名命中）。三个 `config.json` 均**无** `xkey_repair` 键 ⇒ 默认 `false`（RQ-10 F1g 一致） |
| **生产实际授权路径（绕过该门）** | gate 目录外的散文文件 | 手写 `decision:` 行 | `FM/.agenticdoc/_autopilot/evidence/cross-key-repair-request-20260925-n1.md:57` = `**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**`；`:52` 定义协议原文 `在本文末追加一行：\`decision: <approved\|rejected> by <who> at <ts>（备注）\``；另一份 `cross-key-repair-request-20260926-h1.md:6` = `status     : pending-user-decision` |

#### F-3 可独立复算性：逐门判定 + 实测复算结果

**判定口径**：把门的命题拆成 `P1 描述性（可从磁盘复算的子命题）` / `P2 依据性（审批真正依赖的判断）`；分类按 **P2 是否可复算**，但把 P1 的复算能力一并给出。

| kind | P1（描述性，可复算） | P1 复算实测 | P2（审批依据） | 分类 |
|---|---|---|---|---|
| `stage-confirm` | `stage N 有 K 个 key、goal=G、提案已在 _roadmap.md` | ✅ 逐字可从 `_roadmap.md` 复算（key 数与 goal 与 gate 文本 `E2/gates/gate-0001.md:8` 一致）；⚠ `validate_roadmap` **未被 conductor 调用**（唯一调用点 `roadmap_check.py:50`），且当前 FM/E2 的 roadmap **实测不合法**（F-2c） | `G 是否该现在做 / 范围是否合理 / 要不要加约束` | **部分可自举** |
| `stage-close` | `全部 key 已终态 ∧ dossier 已写入` | ✅ 但**零信息量**：这就是 `_stage_closure` 的触发条件（`conductor.py:629-631` 与 `:650-651` 同一函数体） | `stage 目标是否真的达成 / 是否值得开下一 stage` | **部分可自举**（P1 是自证；P2 不可判） |
| `stalled` | `key=stalled ∧ reason 的计数量（used/limit/class/streak）` | ✅ 计数全部可复算：E2 `gate-0014` 的 `3 rounds (budget 2, credits 1)` ↔ 盘上 `l3-a1..a3` 三目录 + gate-0011 approved；FM `gate-0006` 的 `2/2` ↔ `005…`/`-a2` 两目录；FM `gate-0004` 的 `class=gate-blockedx5` ↔ timeline `advance` 连续失败（`_advance_failure_streak`，`conductor.py:786-800`） | `这是机械假阴还是真缺陷 / 带外修复要不要先做` | **部分可自举**（P2 不可判：需读 `l3-report.md`/reviewer `output.md` 散文） |
| `budget-exhausted` | `used == limit ∧ L1 blocking gaps 非空` | ✅ 完全可复算（`state.used_rounds` + `config.round_budget` + `audit_evidence.build_dossier`），**但 0 生产样本** | `多给一轮值不值` | **可自举（命题面）**；决策仍有界（+1 轮后必 stall，`conductor.py:989-994`） |
| `goal-change` | `goal.md 变过（mtime ≠ baseline）` | ⚠ 部分：baseline 只在**内存** + timeline detail（`:4139`/`:2093-2094`）；roadmap 头的 `goal_mtime` 是 **LLM 填的 ms** 且实测差 1ms；JC 的 goal 事件**已被轮转剪掉**（0 条） | `改了什么、是否推翻现有计划` | **不可自举**（before-image 不存在） |
| `xkey-authorize` | `{(file,test_id)} 是红 ∧ owner_key 已终态` | ✅ 结构上可复算（ticket JSON `:2663-2700` + `_DEP_SATISFIED` 检查 `:2621-2626`），**但 0 票据** | `这次修复是否越出 owner key 写面（blast radius）` | **部分可自举**（P2 不可判：`write_scope` 生产零命中） |

**（★）`l3-verdict.txt` vs 现行 resolver 复算：6/22 key 不一致**

`N` = 现存 `l3-a*` 最大编号；`recomputed` = `_l3_resolve_source`（`conductor.py:1274`）在 `N` 上的结果。

| 项目 | key | 末轮 | recomputed | `l3-verdict.txt` | 判定源 | 差异 |
|---|---|---|---|---|---|---|
| FM | `gui-shell-spike` | a3 | **meets** | **below** | output.md | 文件陈旧（C-11 家族）——人工 note 的 31/31 被机器复算**证实** |
| FM | `gui-contract-surface` | a3 | **below** | below | output.md | 文件与复算一致，但**与人工 23/23 冲突**（失败行是 `\| **FAIL** \| … 本轮 **0 条**` 描述性单元格；`_L3_FAIL_ZERO_RE` 只对 bullet 行生效（`conductor.py:1220` vs `:1230-1240`）） |
| FM | `gui-contract-mock-tests` | a2 | **below** | **meets** | output.md | **机器假阴**：失败行 = `PASS (re-review attempt 2): 18/18 VC-GCM assertions PASS with 0 FAIL — repair round closed all 4 pr…`（`_L3_FAIL_PROSE_RE` 命中 `FAIL —`，`:1218`） |
| E2 | `feature-l3-readcap-injection` | a1 | **below** | **meets** | output.md | 复算与 **correction sidecar** 一致（`corrected_value: below`）；文件是错的 |
| E2 | `feature-sampling-human-channel` | a1 | **below** | **meets** | output.md | 同上（correction sidecar `corrected_value: below`） |
| FM | `gui-contract-surface` | a2 | below | below | report.md | 一致（`l3-report.md` 3789B/4179B = `l3-a2/output.md` 字节数，`_persist_l3_verdict` 复制源） |
| 其余 16 key | — | — | == 文件值 | — | — | `meets`/`meets` 或 `below`/`below` |

⇒ **同一命题（"key K 的最终 L3 裁决"）按不同取证源会得到相反答案**：`l3-verdict.txt` / 末轮 output.md 复算 / correction sidecar / 人工 note 四者两两可冲突。

#### F-4 `stage-close` 前置集的充分性：**不充分**，4 个实测反例

RQ-10 提出的前置集 = `① 每 key 最终 l3-verdict == meets ∧ ② 无 closed-legacy key ∧ ③ open_items 为空`。逐条给"满足前置但命题为假"的实例：

**C1（E2 Stage 2，最硬）——前置满足而"该 key 达标"为假。**
- 事实：`E2/.agenticdoc/_autopilot/_roadmap.md` Stage 2 `> status: closed`、`> key-status: …, feature-l3-readcap-injection=done, …`；`E2/.agenticdoc/feature-l3-readcap-injection/l3-verdict.txt` = `meets`；三项目 **`closed-legacy` 0 个**（三份 roadmap 的 `key-status` 实测无该值）。
- 但：`E2/.agenticdoc/feature-l3-readcap-injection/l3-verdict-correction-fm-136c65a70b2b.json` 明写 `"corrected_value": "below"`、`"corrected_basis": "landed recompute verdict (same run_id)"`、`"counted_as_done": false`；且按现行 resolver 复算其唯一末轮 = `below`（F-3）。
- ⇒ 若"open_items"定义为 `{closed-legacy keys} ∪ {final verdict from l3-verdict.txt != meets}`，则前置**全满足**，而实际存在一项未达成（`ledger_items: ["VC-006"]`，`dispositions: ["pending-authorization"]`）。**命题为假**。

**C2（FM Stage 1）——前置的"merges"定义决定结论，两向都会错。**
- 事实：`FM/…/stages/stage-1-close.md:11-12` 的 dossier 列 `gui-shell-spike | DONE | below |` 与 `gui-contract-surface | DONE | below |`；stage 已于 2026-09-25T06:50:16Z `closed`（`FM/timeline.jsonl` seq 71839-71840）。
- 人工 note（`FM/gates/gate-0008.md:14`）原文：`【人工复核提醒·档案陈旧】dossier Keys 表把 gui-shell-spike 与 gui-contract-surface 标为 l3 verdict=below —— 该列直读 key 级 l3-verdict.txt，而该文件是首轮快照（mtime 09-23 19:48/19:10，早于读上限缺陷修复），两 key 的最终轮结论（31/31、23/23）未回填`，并同时登记 `C-09（wheel 不含 GUI 前端资源，owner=gui-release-hardening）`、`C-10（证据不可变缺失）`、`C-11（档案 verdict 取最终轮）` 与 `NRR-1/NRR-2 两条条件性 needs-rerun（提交/推送门）`。
- ⇒ ① 若前置按 `l3-verdict.txt` 判：**不满足**（2/5 below），与已发生的闭环冲突 → 不能用于自动决策；② 若前置按"末轮复算"判：`gui-shell-spike` 满足（`meets`）、`gui-contract-surface` **仍不满足**（`below`，F-3）；③ 无论哪种，`C-09`（stage goal 里"可发布桌面壳/打包分发"元素未闭）与 `NRR-1/NRR-2` 都**只存在于散文**，机器看到的 `open_items` 为空 ⇒ **前置满足而命题为假/不可判**。

**C3（JC Stage 2）——前置满足而命题不可判。**
- 事实：`JC/.agenticdoc/_autopilot/_roadmap.md` Stage 2 `> status: running`、`> key-status: e2e-validation=done`；`JC/.agenticdoc/e2e-validation/l3-verdict.txt` = `meets`（末轮 a1 复算亦 `meets`）；无 `closed-legacy`；dossier `JC/…/stages/stage-2-close.md:11` 行存在。
- 但 stage goal 原文要求人工在场（`JC/gates/gate-0006.md:14` note：`UI 目视与 Rider 实机段需用户在场时再协作完成`），且 `JC/gates/gate-0007.md:6` `created_at: 2026-09-17T20:04:14+00:00`、`:11` `status: pending` ⇒ 已挂 **9.5 天**未被人工确认（另 `JC/gates/gate-0008.md:6` = `created_at: 2026-09-26T04:37:27+00:00` 也是 pending stage-close）。
- ⇒ 机器前置全满足，但"是否闭环"取决于"是否承认实机段未做"——**磁盘上没有该事实**。

**C4（FM `gui-contract-mock-tests`）——前置的 `verdicts-final` 自身不稳。**
- 事实：`l3-verdict.txt` = `meets`（mtime 2026-09-24T06:21:00Z，与 gate-0005 `created_at` 同秒）；按现行 resolver 复算末轮 a2 = `below`（假阴，F-3）。
- ⇒ 同一前置在"读文件"与"复算"下取反 ⇒ 不能作为自动放行判据（除非先定义取证源优先级与解析器版本）。

**C5（附：前置的文本锚也不可靠）——`reason` 文本随构建版本漂移。**
- 事实：`JC/gates/gate-0004.md:8` 的 reason = `exec task 006-toolwindow-scroll exhausted 2/2 attempts`；但 JC `gate-0003` 已于 `2026-09-11T11:05:00+00:00` approved（`JC/gates/gate-0003.md:12-13`），而 gate-0004 建于 `2026-09-11T13:07:27+00:00` ⇒ 按现行为 `limit = 2 + credits(1) = 3`，应为 `3/3`。E2 `gate-0002.md:8` 的 `(budget 2)` 无 `credits` 段（2026-09-22），FM `gate-0002.md:8` 的 `(budget 2, credits 0)`（2026-09-23）⇒ 同一门的 reason 文本有 3 种格式。【推断】JC 建门时运行的 conductor 尚无 `_resume_credits`（AC-013）。

#### F-5 防伪与绑定（风险 20）：不校验会误判的具体路径

RQ-10 实测的两处污染，逐条落到本卡的分析上：

| 污染（RQ-10 实测） | 真实样例 | 若不校验会怎样误判 |
|---|---|---|
| **verdict 陈旧**（C-11） | `FM/gui-shell-spike/l3-verdict.txt` mtime `2026-09-23T11:48:31Z`（= gate-0003 `created_at`，即"stall 那次"的裁决），而末轮 `l3-a3` 在盘上是 `meets` | 机器按 `l3-verdict.txt` 判"key 未达标" ⇒ 把已闭环的 Stage 1 判为"不该闭环"（与人工 31/31 相反）；反向：把 E2 两个 correction 为 `below` 的 key 判为 `meets` ⇒ 静默把未达成项当达标（`counted_as_done=false` 被忽略） |
| **`answered_at` 人工回填早 4.1h** | `E2/gates/gate-0007.md:12` `answered_at: 2026-09-24T03:32:00+00:00`，文件 mtime = `2026-09-24T07:37:57Z`（本地 15:37:57 +08:00）→ 早 4.1h；另一例 `FM/gates/gate-0002.md:13` `15:26:00` vs mtime `15:24:15` → 晚 104s | 任何"等待时长/TTL 命中"复算被污染（RQ-10 实测 `stage-close` 累计 146.9h vs 6.3h，差 140h）；且若用 `answered_at` 做"该门是人工还是机器答的"判据，回填/提前写会伪造来源 |
| **来源字段不可信** | `answered_by` 是自由文本：实测见过 `user-via-pm-window`（FM `gate-0002.md:14`）、`wenbozhou`（E2 `gate-0001.md:13`）、`human-pm-window`（E2 `gate-0002.md:14`）、`human-via-pi`（JC `gate-0002.md:13`）；`gate-writer.ts:75-84` 允许调用方传 `answeredAt` override，手改同样合法（`gates.py:1-20`） | 机器无法区分"人答/机器答/事后补写" ⇒ 无 `decided_by_system` 之类闭集字段时，自动决策的审计不可信（AC-018 的硬前置） |
| **无"证据快照时刻"** | gate 文件只有 `created_at`（=建门时刻），没有"证据被读取的时刻" | 无法判断"这条证据是建门时读的、还是后来补的" ⇒ 陈旧证据与新鲜证据同权（C-11 正是这个形状） |

**可复用的现成原语（不要重造）**：

- `_l3_provenance_record`（`conductor.py:1356-1449`）：把判定源 mtime 与同轮 `trace.log` mtime 做锚定，`slack=60s`（`:1248`），超前即 `suspect=True`，且 `suspect ∧ raw=meets → verdict=below`（fail-closed）；落盘 `l3-verdict-provenance.json`，append-only 按 `task_key` 去重（`:1451-1502`），损坏文件**不覆盖**（`:1467-1476`）。
- correction sidecar：`original_sha256` 把纠正绑定到纠正前的字节。
- `_consumed_gate_ids`（`:297-313`）+ `gate-answered` timeline：已有的"一次性消费"留痕（但正则 `gate-\d{4}` 在 `gate-10000+` 静默失效，见 RQ-11）。

#### F-6 最小附加字段（逐门清单；不给实现方案）

**通用约束（实测）**：新增 frontmatter 字段**必须两侧同改**，否则 fail-closed 报错并跳过 tick —— Python `gates.py:347` `unknown frontmatter field`、TS `status-model.ts:660-661` 同规则；字段集字面量在 `gates.py:68-81` 与 `status-model.ts:572-587`。

| 目标门 | 需要新增的字段（名 : 类型 → 写入点 : 写者） | 防伪要求 |
|---|---|---|
| `stalled` | ① `reason_code: enum{advance-class, l3-below, l3-no-verdict, l3-suspect, exec-exhausted}` → `conductor.py:3971` : conductor（12 个 `mark_stalled` 调用点各自传码，替换现在的散文 `reason`）② `evidence_refs: list[str]`（形如 `l3-verdict.txt:below` / `advance:class=gate-blocked,count=5` / `exec:task=005,attempts=2/2` / `worker:ap-…:failed`）→ 同点 : conductor ③ `loop: str` / `used_rounds: int` / `round_limit: int` / `credits_used: int` → 同点 : conductor（值取自 `state.used_rounds`、`config.round_budget`、`_resume_credits`）④ `observed_at: iso8601`（证据快照时刻，**非** `created_at`） | 计数必须由 conductor 写、不来自 gate 文本；`evidence_refs` 的每个指针须带目标文件的 mtime/sha 前缀（复用 `_l3_provenance_record` 的锚法） |
| `stage-close` | ① `verdicts_final: list[{key, verdict, source, source_sha256, anchor_mtime_ns, suspect}]` → `conductor.py:650` : conductor（**扩展现有 `l3-verdict-provenance.json` 覆盖面到全部轮次**，再从它取末轮）② `open_items: list[{kind, key, item, disposition}]`（`closed-legacy` / `below` / `unrecovered needs-rerun` / `pending-authorization`）→ 同点 : conductor ③ `subject_sha256: str`（被引 dossier 的 sha256）→ 同点 : conductor | `verdicts_final` 必须绑定 source 的 sha256 + `trace.log` 锚 mtime（否则重演 C-11）；`open_items` 必须由机器生成、人不可写 |
| `stage-confirm` | ① `roadmap_validation: list[str]`（`roadmap.validate_roadmap` 结果；需先决定是否排除"未起跑 key 缺 key-status"这一类，见 F-2c）→ `conductor.py:492` : conductor ② `proposal_sha256: str` + `goal_sha256: str`（把提案绑到 goal 版本；替换 LLM 填的 `goal_mtime`）→ 同点 : conductor ③ `constraints: list[str]`（人填的范围约束，结构可引用而非 `note` 散文）→ `gate-writer.ts:139` : 人/窗口 | `proposal_sha256`/`goal_sha256` 由 conductor 算，人只能读；`constraints` 必须留"谁在何时写"（见通用字段） |
| `goal-change` | ① `goal_sha256_before: str` / `goal_sha256_after: str` ② `goal_diff: {sections_added, sections_removed, sections_changed, bytes_delta}` ③ **非字段**：conductor 在检测到变更时把变更前的 `goal.md` 落一份不可变镜像（现在**完全没有** before-image） → `conductor.py:2085` : conductor | 镜像与两个 sha 必须由 conductor 写；`goal_diff` 从镜像算（不得由 LLM 或人填） |
| `xkey-authorize` | ① `write_scope: list[str]`（机器可读的写面；**前置项不属本 key**：AC-014）② `blast_radius: {files: list[str], sha_before: list[str]}` → `conductor.py:2739` : conductor（数据源同 ticket）③ 把 ticket 的 `authorization_snapshot`（整文件 sha256）提升为 gate 字段 | `write_scope` 必须来自 owner key 的机器可读声明，不得来自散文；`blast_radius` 与 `authorization_snapshot` 必须可独立复算（`git hash-object` 类） |
| **全部 6 类（通用）** | ① `answer_source: enum{human, auto}` + `auto_policy_id: str` → `gate-writer.ts:139` + conductor 自动路径 ② `expires_at: iso8601`（TTL 载体；`gates.py:68-81` 现无任何时间字段）③ `evidence_anchor_mtime_ns: int`（证据快照锚） | `answer_source` 必须由**写者身份**决定而非可填值；`answered_at` 应改为"文件 mtime 口径"或额外写一个不可由应答者填的机器时刻 |

**计数**：上表去重后的新增字段名 = `reason_code, evidence_refs, loop, used_rounds, round_limit, credits_used, observed_at, verdicts_final, open_items, subject_sha256, roadmap_validation, proposal_sha256, goal_sha256, constraints, goal_sha256_before, goal_sha256_after, goal_diff, write_scope, blast_radius, answer_source, auto_policy_id, expires_at, evidence_anchor_mtime_ns` = **23** 个（外加 1 项非字段改动：`goal.md` before-image 落盘）。

### 【推断】

- **I1**：**"可自举"门之所以少，根因不是字段缺失而是命题选错了层**。`stage-close` 的 P1 与触发条件同源（`conductor.py:629-631` 与 `:650-656` 在同一函数体），`stalled` 的 P1 全部是计数量（已可复算）——真正的审批内容 P2 在任何一门上都不是"磁盘可判的事实"，而是"策略/性质判断"。⇒ AC-025 的第 (1) 类若按"命题可复算"划界，落点只有 `budget-exhausted`（0 样本）与 `stalled` 的 **exec-exhausted / L3-below 计数量**子集；其余必须先被人（design 期）**降级为可判命题**（例如把 `stage-close` 的命题从"目标是否达成"改成"是否满足 ①..③ 前置"，并把 ①..③ 的字段补齐）。
- **I2**：**取证源优先级必须先冻结，否则"自举"会自相矛盾**（F-3 的 6/22）。建议顺序按已有实现：`l3-verdict-provenance.json`（有锚）> correction sidecar（有 sha）> 末轮 `output.md`/`report.md` 复算 > `l3-verdict.txt` > gate 散文。当前 `_l3_verdict`（`conductor.py:659-671`，dossier 的唯一数据源）取的是**最末位**那一档。
- **I3**：`stage-confirm` 的 P1 复算现在会**误报**：`validate_roadmap` 的 key-set 相等规则与"runtime 增量写 key-status"冲突（docstring 原文 `callers should initialize entries for all stage keys when a stage starts running`，`roadmap.py:509-512`；conductor 未做），实测 FM Stage 2 / E2 Stage 3 当前不合法。⇒ 若把 `roadmap_validation` 直接搬进门字段，会得到大量假阳，必须先按规则分类（结构性 vs 运行期）。
- **I4**：`goal-change` 的"不可自举"是**结构性**的，不是"字段没加"：`tick()` 的检测输入只有 `os.stat().st_mtime_ns`（`conductor.py:76-83`），且 `reject` 与 `approve` 走同一分支（`:2100-2111`）。⇒ 即便补齐 sha/diff 字段，只要不落 before-image，机器仍只能证"变过"、不能证"变成什么"；同时该门的 reject 语义缺口让"两种答案等价"（与 RQ-10 I5 一致）。
- **I5**：生产上唯一真实发生过的"跨 key 授权"**没有走 `xkey-authorize` 门**，而是走 `_autopilot/evidence/cross-key-repair-request-*.md` 的散文 + 手写 `decision:` 行（F-2f）。⇒ `xkey-authorize` 的 0 样本不是"门没用"，而是"人用了一条门外的路"；这条门外的路**没有任何 schema**，比门本身更难自举。
- **I6**：correction sidecar 这类"项目自建账本"是**双刃**：它把 E2 的两个错误 `l3-verdict.txt` 纠了回来（好事），但它是 **key 级产物**（由 `feature-false-meets-remediation` 工具链生成），换项目就没有 ⇒ 框架若要依赖它做自举校验，等于依赖一个非框架契约（P-021/P-022 家族风险）。

## 结论 → 决策映射

**支撑 AC-025（逐 gate 类型的处置模式三分判定）**：

| AC-025 需要的判定 | 本卡结论（按"命题可独立复算"这一维） |
|---|---|
| **可由机器独立复算（第 (1) 类候选）** | `budget-exhausted`：P1 = `used == limit ∧ L1 blocking gaps 非空` **完全可复算**，approve 后果有界（+1 轮后必 stall）——但 **0 生产样本**（`stalled` 的 exec-exhausted / L3-below 计数子命题也完全可复算，可作第 (1) 类的窄子集） |
| **部分可自举（描述层可复算、审批内容不可）** | `stage-confirm`（P1 逐字可复算 + `validate_roadmap` 需先分类）；`stage-close`（P1 是触发条件的同义反复；P2 不可判）；`stalled`（计数可复算；"假阴 vs 真缺陷"不可）；`xkey-authorize`（身份/目标可复算；写面越界不可） |
| **不可自举** | `goal-change`：before-image 不存在（FM untracked / JC 无 VCS / 无快照），baseline 只在内存与 timeline detail，且 `reject` 为 no-op |
| **反例要求（"证据存在但命题不成立"）** | C1 E2 Stage 2（correction `below` + `counted_as_done=false` 而 stage 已闭环）；C2 FM Stage 1（dossier 2/5 `below` 已闭环 + `C-09`/`NRR-1/2` 只在散文）；C3 JC Stage 2（全绿 + 已挂 9.5 天，命题取决于"实机段算不算没做"）；C4 FM `gui-contract-mock-tests`（文件 `meets` / 复算 `below`） |

**直接回答 RQ-10 的 `stage-close` 前置是否充分**：**不充分**（C1–C4）。要让它充分，至少需要 ① `verdicts_final` 用**带锚的 provenance** 而非 `l3-verdict.txt`（否则 C1/C4 两向都会错）；② `open_items` 必须覆盖"未达成登记"（现在是纯散文，`E2/gates/gate-0003.md:14` 的 `approve 不表示其完成` 就是实例）；③ 承认 C2/C3 型（"目标达成"与"人工在场"）是**策略判断**、机器只能给前置不自足——按 AC-025 应落 (2)/(3) 类而非 (1) 类。

**给 design 期的输入（不含方案，只给判据）**：

1. **先冻结取证源优先级与解析器版本**（I2）。`l3-verdict.txt` **不可**作为"最终裁决"的唯一来源；优先用带 `source_mtime_ns`/`anchor_mtime_ns` 的 `l3-verdict-provenance.json`（`conductor.py:1246-1248`/`:1356`/`:1451`），并把它从"只覆盖 2026-09-26 之后的轮次"扩到全量（当前 FM 2 个 key / E2 2 个 key / JC 0）。
2. **把"命题"降级为可判子命题再谈自动化**（I1）。逐门给"机器可判前置 + 不可判残差"两栏；不可判残差必须落在 (2)/(3) 类，不得用"历史 100% approve"补位（RQ-10 风险 19）。
3. **防伪三件套进任何自举校验**（F-5）：(a) 证据快照时刻 + 目标文件锚 mtime（slack 阈值已有 60s 先例）；(b) 目标文件/判定源 sha256 绑定（correction sidecar 已有 `original_sha256` 先例）；(c) 来源闭集字段（`answer_source`/`auto_policy_id`），因为 `answered_by`/`answered_at` 人可写（E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s）。
4. **最小字段表（F-6，23 字段 + 1 项 before-image 落盘）是 design 的输入清单**，不是实现方案；注意两侧镜像与 fail-closed 解析（`gates.py:347` / `status-model.ts:660-661`）。
5. **`stage-close` 的组合安全性不变**（RQ-10 风险 18 / I4）：本卡的 C1–C4 全部发生在"`stage-confirm` 未自动"的前提下；若同时自动化 `stage-confirm`，`auto-close → auto-confirm → auto-dispatch` 链条会把 C2/C3 的不可判残差直接变成无人派发。
6. **`goal-change` 应优先回答"reject 语义"而不是"能不能自动答"**：`conductor.py:2100-2111` 使两个答案等价，任何自动化都只是在"等于没答"的选项间选择。

**数据缺口**：

1. **`budget-exhausted` / `xkey-authorize` 生产 0 样本**（`xkey_repair` 三项目均未开）⇒ 第 (1) 类的唯一候选无法用真实样本验证；`budget-exhausted` 的"可自举"结论是**纯代码推理**（`used`/`limit`/gaps 三处都可复算）。
2. **`l3-verdict-provenance.json` 覆盖面 < 5/22 key** ⇒ "带锚溯源"这条路径在历史数据上**不可回填**（当时的轮次没有 anchor 记录），只能对 2026-09-26 之后的轮次生效。
3. **correction sidecar 只覆盖 E2 3 个 key**，且是 key 级工具链产物；无法判断 FM/JC 是否还有同类未纠正的陈旧 verdict（本卡只能用"末轮复算"给出 6/22 的不一致清单，无法判定哪一侧为"真值"）。
4. **`goal-change` 的 before-image 全项目不可得**（FM untracked、JC 无 `.git`、无框架快照）⇒ 该类门的自举验证在当前数据上**无法做受控实验**。
5. **`closed-legacy` 生产 0 实例**（三份 roadmap 的 `key-status` 无该值）⇒ "无 closed-legacy"这条前置在真实数据上**从未被触发过**，其判据强度未经检验。
6. **`_workers.parallel` 无 writer/origin 列**（`worker-store.ts:22-37`，与 RQ-10 风险 8b 一致），且文件是 upsert-append 顺序、**不按时间排序**（实测 JC `ap-plugin-ui-006-toolwindow-scroll-a2` 行出现在 base 行之后而 `dispatchedAt` 更早：`2026-09-11T10:44:56+00:00` vs `13:11:20+00:00`）⇒ 用它复算轮次必须按 `dispatchedAt` 显式排序，不能按文件序。
7. **无法区分"项目被弃置"与"人忘了答"**：JC 的 2 条 pending stage-close（`gate-0007` 9.5 天 / `gate-0008` 0.3 天）没有旁证，故 C3 只能给"命题不可判"，不能给"命题为假"。
8. **本会话的工具层对 `goal.md` 字样有拦截**（实测：任何含该字样的 bash 命令被替换为"只读的项目目标锚点…"提示；worker `trace.log` 有记录），该拦截**不在本仓代码内**（`packages/coding-agent/src` 与 `packages/multi-workers` 全量 grep 零命中）⇒ 对 `goal-change` 的"谁能写 goal.md"这一防伪问题，本卡只能记录现象、无法给出实现锚点。
9. **本卡未做**：`stage-confirm` 的人填约束（FM `gate-0009.md:14` 的 7 条 / E2 `gate-0008.md:14` 的 2 条禁令）在**下游是否被消费**没有可判据——这些约束只出现在 gate `note` 散文里，全仓无消费点可得（本卡仅确认其不可机读，未追踪其生命周期）。

[VERIFY] RQ-12: selfverifiable=[budget-exhausted(proposition-face only, 0 samples)] partial=[stage-confirm, stage-close, stalled, xkey-authorize] not_selfverifiable=[goal-change] verdict_source_disagreements=6/22(gui-shell-spike meets-vs-below, gui-contract-mock-tests below-vs-meets, gui-contract-surface-a3 below-vs-human-23/23, feature-l3-readcap-injection meets-vs-correction-below, feature-sampling-human-channel meets-vs-correction-below, gui-contract-surface-a2 below-vs-below=agree) stage_close_precondition_sufficient=false counterexamples=4(C1 E2 stage2 correction counted_as_done=false while l3-verdict.txt=meets and stage closed, C2 FM stage1 dossier 2/5 below closed anyway + C-09/NRR-1/2 prose-only, C3 JC stage2 all-meets/no-closed-legacy but stage goal requires human Rider presence, gate-0007 pending 9.5d, C4 FM gui-contract-mock-tests file=meets vs recompute=below) plus_text_drift=1(JC gate-0004 'exhausted 2/2' vs recompute '3/3' due to credits; 3 reason formats across builds) min_fields=23(+1 non-field: goal.md before-image mirror) reusable_primitives=[l3-verdict-provenance.json conductor.py:1246/1356/1451, correction sidecar original_sha256/corrected_value/counted_as_done, _consumed_gate_ids conductor.py:297, _advance_failure_streak conductor.py:786-800] unforgeable_gaps=[answered_at and answered_by are answerer-writable (E2 gate-0007 -4.1h vs mtime, FM gate-0002/0003 +104s); no evidence-snapshot time on gate (only created_at); reason text drifts with conductor build; no writer/origin column in _workers.parallel] samples_used=gate files FM10+E2 18+JC8, 3 _roadmap.md, 5 stage-*-close.md, 22 l3-verdict.txt, 4 l3-verdict-provenance.json, 4 correction sidecars, 3 _workers.parallel, 3 timeline chains, 34 answered-gate notes (note text reused from RQ-10 scope, not re-statistised)
