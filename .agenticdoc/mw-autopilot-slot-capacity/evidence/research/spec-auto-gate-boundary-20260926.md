# Research: 自动 gate 决策的边界与判据（RQ-10 / key `mw-autopilot-slot-capacity`）

> 角色: spec 期调研（**只读**；本文件是本卡唯一写面）。本笔记是 **output**：TL;DR 与 `[VERIFY]` 都在本文件内。
> 代码基线: `H:/git/Multi-Workers` HEAD `4ef71e053`；`autopilot/conductor.py` sha256 `a284dc00478e9c80`、`autopilot/gates.py` sha256 `15e0716065219055`、`autopilot/monitor.ts` sha256 `2cb53cbb9bd7be05`。
> 数据快照: **2026-09-26T07:5xZ**（FM/E2 autopilot 当时仍在跑；所有数字为该时刻的冻结值，冻结后新增的行不属于本文）。
> 边界: 不重复 RQ-6（stalled 生命周期/占槽）、RQ-3（槽位利用率）、RQ-1（并发锚点）、RQ-8（**门清单/阻塞范围/等待时长/无人值守策略**——本文的等待时长只作为"自动化数据依据"的一部分引用并与 RQ-8 交叉核对）；不做 RQ-11 的护栏机制与回放阈值估算。

## TL;DR

1. **答案分布（3 个项目、34 条唯一人工应答）**: **34/34 全部 `approve`，`reject` 0 条**。分门: `stalled` 22/22、`stage-confirm` 7/7、`stage-close` 4/4、`goal-change` 1/1。样本窗: FM 70.8h（2026-09-23T09:06:44Z→09-26T07:54:35Z）、E2 100.3h（2026-09-22T03:35:07Z→09-26T07:54:35Z）、JC 15.1d（gate 文件 09-11T03:33Z→09-26T04:37Z）。另有 6686 条 pending（FM 洪泛 6684 + JC 2）。
2. **但"答案唯一"不等于"可自动"**: 22 条 stalled 里 **≥16 条的 note 记录了 approve 之前的带外修复**（改框架/改配置/改工件/重启），其余 6 条也在 note 里给出成因诊断；**0/22 条是裸的"可以/不可以"决策**。⇒ approve 是"人已修好、放行一轮"的**收据**，不是可独立判断的 y/n。
3. **载体**: gate 文件 12 个 frontmatter 字段里**没有任何机器判据字段**（`question`/`context_refs`/`note` 全是散文）；判断"是框架假阴还是真缺陷"所需的依据散落在 6 处（`l3-verdict.txt` / reviewer `output.md` 两节 / timeline `advance` 的 class+streak / 任务 attempts / `_roadmap.md` key-status / dossier）。现状机器**只能反解析散文**：我实测用一条正则可从 `context_refs[1]` 抽出 5 类原因（F1d），但那是逆推、不是 schema。
4. **三态判定**: 可自动（条件化）= `stage-close`(仅 approve，证据齐备) / `budget-exhausted`(结构最干净但 0 样本→影子模式) / `stalled` 的 approve（仅"机器可证假阴"窄子集 + per-key 上界）；仅给建议 = `stage-confirm`（结构可预检、内容不可判）与 `stalled`（默认）；绝不可自动 = `goal-change`、`xkey-authorize`、**所有 reject 方向**、证据不全的 `stage-close`。
5. **可逆性决定方向**: approve 花 token（可能改代码）；reject 走 `closed-legacy` ⇒ 进入 `_DEP_SATISFIED`（`conductor.py:56`）⇒ **解锁依赖方 + 允许 stage 收口**，且 `_consumed_gate_ids`（`:297`）只是消费记录、**没有任何撤销入口** ⇒ 不可逆。`_resume_credits`（`:2273`）每次 approve 永久 +1 且**无上界** ⇒ 自动 approve 等价于取消所有预算上限。
6. **数据陷阱（必读）**: FM 的 `gate-answered` 事件 6694 条但唯一 gate 只有 10 个（gate-0002 approved **5588** 次、gate-0003 **1098** 次，归档 6684 个 pending stalled gate 文件）。那是**一次人工 approve 被重复消费**（`4e874f5cc` 之前缺一次性消费守卫）的产物；按 timeline 事件统计答案分布会得到"6686/6686 approve"的幻觉。
7. **U-8「C 由数据定」可行吗**: **不能只由答案分布定**。"答案唯一性"有数据（34/34）、"等待成本"有数据（`stalled` 累计 137.3h、`stage-close` 146.9h 里 136.4h 是 JC 一条），但"可自动"还要求 **依据可机器判定 + 答错可逆 + 有上界**，这三项当前（除 `stage-close` 的结构面）**都不满足** ⇒ 数据只能定出"哪些门可以进影子模式"，定不出"哪些门可以自动过"；阈值/范围必须先补齐 F5 的结构化字段再定。

## 决策问题

用户已决策走 **C（机器自动过"部分" gate）**（spec §4 U-6），本卡要用证据回答"**部分**是哪些"。据此把问题拆成 5 个，全部只回答"该不该 / 能不能自动决策"，不回答"门怎么改、阻塞谁"（RQ-8 的题）：

1. **数据面**: 每个 gate 类型的历史创建数 / 被答数 / **答案分布** / 等待时长分布；哪些类型"人工几乎总是同一个答案"（含样本量与时间窗、可复算方式）。
2. **载体面**: 每个 gate 在磁盘上到底留了什么（gate 字段 / roadmap 条目 / timeline `detail` / 面板行），人判断时看的是什么；**哪些字段机器可直接读（`file:line`）**，哪些是散文。
3. **三态判定表（本卡核心产出）**: 逐 gate 类型给出 `可自动 / 仅给建议 / 绝不可自动` + 判据 + **至少 1 个"如果自动过会错"的具体情形**；判据必须覆盖 (a) 依据可否由磁盘判定、(b) 答错的可逆性、(c) 历史一致性与样本量。
4. **不可自动化白名单**: 逐条给证据锚点，不凭感觉；特别评估"任何会写代码/改文件/改 roadmap 的答案""任何 `closed-legacy`（会解锁依赖）""任何'目标是否达成'的判定"。
5. **自动化的最小证据要求**: 若某 gate 要自动化，**必须先补齐哪些字段/事件**，逐条给当前缺口与锚点。

## 调研方法与出处

### 代码（只读；行号 = HEAD `4ef71e053` 工作树快照）

| 面 | 位置 |
|---|---|
| gate 闭集 6 类 + 12 字段 schema + 状态闭集 | `autopilot/gates.py:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:68-81`（`FRONTMATTER_FIELDS`）、`:86-89`（必填集）；TS 镜像 `status-model.ts:561-567`、`:587-598` |
| gate 创建（conductor 唯一创建者） | `gates.py:262` `create()`、`:159-175` `_gate_file_content`（body = 问题原文 + Context 散文）；`conductor.py:2159` `_create_gate` |
| gate 应答（人类路径） | `gate-writer.ts:139` `answerGate`（只改 `status/answered_at/answered_by/note` 四行）；CLI `console.ts:182-198`（`gates` 列表）、`:204-245`（`gate <id> approve\|reject --note`） |
| 消费（approve/reject 的效果） | `conductor.py:316` `_consume_answered_gates`；`stalled` 两向: `:2295` `_apply_stalled_approvals`（→ running + `_resume_credits`）、`:2363` `_apply_stalled_rejections`（→ `closed-legacy`）；`stage-confirm`/`stage-close`: `:348-384`；`budget-exhausted`: `:2216` `_budget_bonus` / `:2228` `_budget_gate_rejected`；`goal-change`: `:2063-2110`；`xkey-authorize`: `:2798` `_consume_xkey_gate` |
| 门创建点（各类型） | `stage-confirm`: `:426`/`:492`；`stage-close`: `:650`；`budget-exhausted`: `:996`；`goal-change`: `:2085`；`xkey-authorize`: `:2739`；`stalled`: `mark_stalled` `:3944` → `_create_gate` `:3971`（12 个触发点见 RQ-6 F1） |
| 阻塞/终态语义 | `_stage_closure` `:616-656`（终态集 `("done","closed-legacy")` `:629-631`）、`_DEP_SATISFIED` `:56`、`_stage_activation` `:434-451`、`_ensure_next_stage_gate` `:410-432` |
| 判据来源（机器可读的那一半） | `l3-verdict.txt` 读点 `conductor.py:659-671`；写点 `_persist_l3_verdict` `:680+`；advance 失败分类 `:786-800`（`interface-drift`/`gate-blocked`/`timeout-env`/`other`）；roadmap 校验 `roadmap.py:367-425` `validate_roadmap`；dossier `:722-750` |
| 观测面 | 面板 `monitor.ts:89-95`（`MonitorGate` 仅 id/kind/stage/key）、`:150-180` `scanPendingGate`、`:596-599`/`:603-627`/`:644-654`；`mw doctor` `mw_common.py:2022-2065`（只有 xkey verify 配置）；roadmap 的 `> status:`/`> key-status:`（`roadmap.py:52-68`） |

### 数据（只读；3 个项目）

| 项目 | 路径 | gate 文件 | timeline | 备注 |
|---|---|---|---|---|
| FM | `E:/CLI_workspace/FeatureMigrator` | live 10 + 归档 `_gates-flood-20260924` 6684（全 `pending`） | `timeline.jsonl*` seq 1..91918，93k 行 | 唯一含洪泛 |
| E2 | `H:/git/E2Feature` | 18 | seq 1..97140 | — |
| JC | `H:/git/JCodingAss` | 8（6 已答 + 2 pending） | 只保留 seq 98074..298516（更早代被轮转剪掉），仅 3 个 `gate-created` | 唯一含 `goal-change` 样本 |
| MW（本仓） | `H:/git/Multi-Workers` | **无** `.agenticdoc/_autopilot/`（`Test-Path` → False） | 无 | 不可用（RQ-3 已记录） |

### 复算方式（全部可复现）

1. **答案分布（唯一口径）**：按 **gate 文件**统计 —— `status` ∈ {pending,approved,rejected}，不是按 timeline 事件（见 F1c 的陷阱）。
2. **等待时长**：`mtime(gate-NNNN.md) − created_at`（秒）。**不用 `answered_at`**，因为它是人工可写字段（实证见 F1e 脚注）。gate 文件在被应答前不会被写，所以 mtime = 应答写入时刻。
3. **原因类抽取（机器可抽的那部分）**：对每个 `stalled` gate 的 `context_refs[1]` 跑
   `re.search(r"L3 无裁决|L3 below|advance \S+ 连续 5 次失败（class=([a-z-]+)|exec task .* exhausted", ref)`。
4. **洪泛口径**：`collections.Counter(re.match(r"(gate-\d{4})", detail).group(1) for gate-answered events)` → 出现次数 >1 的 id 即重放。
5. 最小脚本（可直接跑，只读）:

```python
import os, re, glob, json, datetime, collections
ROOTS = [("JC", "H:/git/JCodingAss"), ("FM", "E:/CLI_workspace/FeatureMigrator"),
         ("E2", "H:/git/E2Feature")]
def front(t):
    d, inr = {}, False
    for ln in t.splitlines()[1:]:
        if ln.strip() == "---": break
        if inr:
            if ln.strip().startswith("- "): continue
            inr = False
        k, _, v = ln.partition(":")
        if k.strip() == "context_refs": inr = (v.strip() != "[]"); continue
        if k: d[k.strip()] = v.strip().strip("'") or None
    return d
ans, pend, waits = collections.Counter(), collections.Counter(), collections.defaultdict(list)
for tag, root in ROOTS:
    gd = os.path.join(root, ".agenticdoc", "_autopilot", "ga" + "tes")
    for f in sorted(os.listdir(gd)):
        if not f.endswith(".md"): continue
        p = os.path.join(gd, f); fm = front(open(p, encoding="utf-8").read())
        ans[(tag, fm["kind"], fm["status"])] += 1
        if fm["status"] == "pending": pend[(tag, fm["kind"])] += 1; continue
        c = datetime.datetime.fromisoformat(fm["created_at"].replace("Z", "+00:00"))
        m = datetime.datetime.fromtimestamp(os.stat(p).st_mtime, datetime.timezone.utc)
        waits[fm["kind"]].append((m - c).total_seconds() / 3600)
for k, v in sorted(ans.items()): print(k, v)
for k, v in sorted(waits.items()):
    v.sort(); print(k, len(v), round(v[0], 2), round(v[len(v)//2], 2), round(v[-1], 2), round(sum(v), 1))
# 洪泛重放（FM）：
evs = [json.loads(l) for f in glob.glob(ROOTS[1][1] + "/.agenticdoc/_autopilot/timeline.jsonl*")
       for l in open(f, encoding="utf-8") if l.strip()]
rep = collections.Counter(re.match(r"(gate-\d{4})", e["detail"] or "").group(1)
                          for e in evs if e["ev"] == "gate-answered")
print("replayed:", {k: v for k, v in rep.items() if v > 1})
```

## 发现

### 【事实】

#### F1 — gate 历史答案分布（问题 1）

##### F1a 样本与时间窗

| 项目 | 唯一已答 gate | 已答 | pending | 观测窗（timeline 冻结值） | 复算 |
|---|---|---|---|---|---|
| FM `E:/CLI_workspace/FeatureMigrator` | 10 | 10 | 6684（全部归档洪泛） | `2026-09-23T09:06:44Z` → `2026-09-26T07:54:35Z` = **70.8h**（seq 1..91918） | 本文脚本 / RQ-8 |
| E2 `H:/git/E2Feature` | 18 | 18 | 0 | `2026-09-22T03:35:07Z` → `2026-09-26T07:54:35Z` = **100.3h**（seq 1..97140） | 本文脚本 / RQ-8 |
| JC `H:/git/JCodingAss` | 8 | 6 | 2 | gate 文件 `2026-09-11T03:33:17Z` → `2026-09-26T04:37:27Z` = **15.1 d**；timeline 只剩 `2026-09-15T20:04:11Z` → `09-26T07:54:34Z`（更早代被轮转剪掉） | 本文脚本 |
| 合计 | 36 | **34** | 6686 | — | — |

JC 的早期 timeline 代被轮转剪掉（只 3 个 `gate-created` 事件），所以 **JC 的答案分布只能从 gate 文件读**（gate 文件才是 source of truth，`gates.py:1-20` 的角色定义）；这与 RQ-6 的"JC 不可用于占槽重叠"不冲突（不同问题）。

##### F1b 答案分布（唯一人工应答；这是"人工几乎总是同一个答案"的数据依据）

| gate kind | 创建 | 已答 | `approve` | `reject` | 其它 | approve 占比 | 等待 p50 | 等待 max | 累计等待 |
|---|---|---|---|---|---|---|---|---|---|
| `stalled` | 22 + 6684(洪泛) | **22** | **22** | 0 | 0 | **100%** | 3.60h | 17.40h | 137.3h |
| `stage-confirm` | 7 | **7** | **7** | 0 | 0 | **100%** | 0.12h | 2.79h | 3.3h |
| `stage-close` | 6（4 已答 + 2 pending） | **4** | **4** | 0 | 0 | **100%** | 6.03h | 136.4h | 146.9h |
| `goal-change` | 1 | **1** | **1** | 0 | 0 | **100%** | 0.24h | 0.24h | 0.2h |
| `budget-exhausted` | 0 | 0 | — | — | — | — | — | — | — |
| `xkey-authorize` | 0 | 0 | — | — | — | — | — | — | — |
| **合计** | 34(+6686 pending) | **34** | **34** | **0** | **0** | **100%** | — | — | 287.7h |

**"人工几乎总是同一个答案"的类型 = 全部 4 个有样本的门都是 100% `approve`**，样本量分别是 `stalled` 22、`stage-confirm` 7、`stage-close` 4、`goal-change` 1。**`reject` 在 3 个项目 15.1 天里从未被走通（0/34）** ⇒ reject 路径（`closed-legacy` / stage `halted`）**没有任何生产样本**。

##### F1c 数据陷阱：FM 洪泛让"事件计数"与"真实决策"差 669 倍

- FM timeline `gate-answered` 事件 **6694** 条，但唯一 gate id 只有 **10** 个：`gate-0002 approved` **5588** 次、`gate-0003 approved` **1098** 次（合计 6686 次重放；其余 8 个 gate 各 1 次）。
- 归档目录 `_gates-flood-20260924/` 有 **6684** 个 `kind=stalled`、`status=pending` 的 gate 文件（id `gate-0004..gate-6687`，`created_at` `2026-09-23T15:37:12Z` → `2026-09-24T03:01:32Z` = **11.4h**；key = `gui-contract-surface` 5587 / `gui-shell-spike` 1097）。
- 根因（框架内已记录）: `_apply_stalled_approvals` 的一次性消费守卫缺位 ⇒ 同一个已批准的 `gate-0002/0003` 每 tick 被重放一次，同时每 tick 新建一个 pending stalled gate；`conductor.py:2320-2331` 的注释原文给出了同一组数字（"6684 pending stalled gates + 6685 stalled/gate-answered/resume events in ~12 h"），修复提交 `4e874f5cc`（2026-09-24，"consume approved stalled gates exactly once"）。
- **口径规则**: 统计答案分布必须按 **唯一 gate id + gate 文件 status**；按 timeline 事件统计会得到 6686/6686 的幻觉。**洪泛本身还是"自动 approve 无上界"的实证**（同一 key 在一夜里被"续跑"5588 次、零推进）。
- **与 RQ-11 的交叉发现（引用，不重复）**: RQ-11 实测 `_consumed_gate_ids` 的正则只认 **4 位** gate id（`conductor.py:310-312`）⇒ `gate-10000` 起持久消费护栏**静默失效**，而洪泛 11.4h 就产出 6684 个文件（已到 `gate-6687`）⇒ 任何「自动过大量 gate」的方案会**先撞这条**，这也是 F5 要求 `auto_decisions` 计数落盘的原因之一。


##### F1d 原因分布（机器可从 gate 文件抽出的类）

对 22 条 `stalled` 的 `context_refs[1]` 跑「复算方式」第 3 条的正则：

| 原因类（机器可抽） | 条数 | 真实成因（需读 note / 工件） | 典型实例 |
|---|---|---|---|
| `L3 below N rounds (budget …, credits …)` | 8 | **5 条有记录的机械假阴**（读域上限 / `output.md` 缺 `## Quality Gate Report`+`## Achieved` 两节 → `_parse_l3_output` 判 below）+ **2 条是真缺陷**（37 PASS/5 FAIL、15 PASS/1 FAIL）+ 1 条成因未记录（E2 gate-0002） | FM gate-0002/0003；E2 gate-0002/0005/0006/0010/0014/0015 |
| `L3 无裁决（worker failed: …）达 N/N 轮` | 4 | reviewer 轮中途断流（`stream closed before response.completed`，exit=0、1 分钟、占位 output.md） | E2 gate-0016/0017/0018/0009 |
| `advance verify->done 连续 5 次失败（class=gate-blocked）` | 5 | 框架 `_done_transaction` 落的 `achieved.md` 词表与工程 done 门禁不匹配（FM 归因 A-02） | FM gate-0004/0005/0007/0010；E2 gate-0012 |
| `advance execute->verify …（class=interface-drift）` | 1 | `pm-state.md` 相位行被写成整句话 | E2 gate-0013 |
| `exec task … exhausted 2/2 attempts` | 4 | harness idle 看门狗误杀长命令（E2 的 613s/612s 无活动；FM 的 pytest 630.51s > 600s 阈值）与网络截断 | FM gate-0006；E2 gate-0011；JC gate-0003/0004 |
| 合计 | **22** | — | — |

⇒ 机器能判 **原因类别**（计数、class 都是结构化的），但**判不了"机器假阴 vs 真缺陷"**——那需要打开 key 目录读散文报告（`l3-report.md` / `reviewer output.md` / `advance` 的 detail 原文）。这是 F5 第一号缺口。

##### F1e 等待时长（mtime 口径）与 RQ-8 交叉核对

| kind | n | min | p50 | p90 | max | 累计 | RQ-8（answered_at 口径） | 差 |
|---|---|---|---|---|---|---|---|---|
| `stalled` | 22 | 0.06h | 3.60h | 15.19h | 17.40h | 137.3h | FM p50 3.62h / 43.49h；E2 p50 4.04h / 90.97h；max 17.40h | ≤ 2 min/项目（口径差，结论一致） |
| `stage-confirm` | 7 | 0.02h | 0.12h | 2.79h | 2.79h | 3.3h | FM/E2 全部 ≤ 0.20h | JC 的 2.79h 是 RQ-8 未含的第三个项目 |
| `stage-close` | 4 | 0.02h | 6.03h | 136.44h | 136.44h | 146.9h | FM 0.02h / E2 3.15h | JC 的 **136.4h** 是新增（项目被搁置 5.7 天） |
| `goal-change` | 1 | 0.24h | 0.24h | 0.24h | 0.24h | 0.24h | 未含 | JC 唯一实例（RQ-8 只说 FM/E2 为 0） |

**口径脚注（为什么用 mtime 而不是 `answered_at`）**: `answered_at` 是**人工可写**字段（`gate-writer.ts:139` 只是"合法路径之一"，手改文件同样合法 `gates.py:1-20`），实测有 3 处不自洽 —— E2 `gate-0007` 的 `answered_at`(03:32:00) 比文件 mtime(07:37:57) **早 4.1h**、FM `gate-0002/0003` 的 `answered_at`(15:26:00) 比 mtime(15:24:15) **晚 104s**。用 mtime 得到 `stage-close` 累计 146.9h（vs answered_at 口径 6.3h——被回填"改小"了 140h）。**这个字段本身也是自动化审计的缺口之一（F5）。**

##### F1f 重复 stall 与"approve 耦合带外修复"

- 22 条 `stalled` 落在 **15 个不同 key** 上；**5 个 key 停过 ≥2 次**（`feature-gui-time-mvp-board` 3、`feature-false-meets-remediation` 3、`gui-skeleton-shell` 2、`feature-cigate-install-kit` 2、`plugin-ui` 2）⇒ **7 条是重复 stall**。
- 关键字匹配（`修复/重启/转写/落章/重写/抬高/还原/派 repair/已收敛/已闭合…`）: **16/22** 条 note 记录了 approve **之前**的带外动作；其余 6 条（JC gate-0003/0004、E2 gate-0002/0009/0014/0016）也在 note 里给出成因诊断（例: E2 gate-0009 "reviewer 把质检长文写进 report.md，output.md 缺两节"；gate-0014 "37 PASS / 5 FAIL 且失败项为真实缺陷"）。
- **⇒ 0/22 条是一次不读散文就能决定的裸 y/n**。approve 的实际语义是"人已经做完修复/诊断，放行一轮"，`_resume_credits`（`:2273`）把它折算成"每个 cap 回路额外一轮"。
- 同 key 同日连停的实例：E2 `feature-false-meets-remediation`/`feature-gui-time-mvp-board` 在 2026-09-26 当天各有两条以上 `L3 无裁决` → 自动续跑（无人修断流根因）会再 stall。

##### F1g 零样本门 / 零样本事件

| 门 / 事件 | 生产创建数 | 为什么是 0 | 影响 |
|---|---|---|---|
| `budget-exhausted` | 0 | 三项目都未命中 L2 多轮预算耗尽路径（创建点 `conductor.py:996-1001`） | 结构上最干净的自动候选，但**没有数据** |
| `xkey-authorize` | 0 | `xkey_repair` 默认 `false`（`config.py:74-77`）且三项目 `config.json` 均未开 | 门本身是"授权改代码"，0 样本 + 结构风险 ⇒ 不可自动 |
| `goal-change` / `goal-halt` | 1 / 0 | 只有 JC 一次（JC 的 `goal-halt` 事件已随更早 timeline 代被剪；gate 文件在） | 唯一语义样本，1 条不足以定自动化 |
| `type-rejected` / `target-config-rejected` | 0 / 0 | dispatch 的 fail-closed 拒绝路径（`dispatch.py:437`/`:479`/`:511`）生产未命中 | 机器已自动处理、无人工参与 ⇒ 不属于"待自动化的门" |
| `l3-no-verdict` | 10（E2）/ 0（FM） | 机器事件：reviewer 轮无裁决 → 自动 re-review（`conductor.py:1630`），累计到 `l3_limit` 才转 `stalled` 门 | 已自动；但它把"自动失败"升级成人工门 |

#### F2 — 每个门在磁盘上到底留了什么（问题 2）

##### F2a 载体字段表（哪些机器可直接读）

| 载体 | 位置（`file:line`） | 字段 | 机器可直接读? | 写者 |
|---|---|---|---|---|
| gate 文件 frontmatter | `gates.py:68-81`（12 字段）；TS 镜像 `status-model.ts:587-598` | `id kind stage key created_at created_by question context_refs status answered_at answered_by note` | **部分是**：`id/kind/stage/key/created_at/status`（枚举）是结构化的；`question`/`note`/`context_refs` 是散文 | 创建=conductor（`gates.py:262`）；应答=人/`gate-writer.ts:139` |
| gate body | `gates.py:159-175` | 问题原文 + `## Context` 列表 | 散文 | conductor |
| **决策依据（成因）** | 12 个 `mark_stalled` 调用点（`conductor.py:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941`）→ `mark_stalled:3944` → `_create_gate:3969` | **无结构字段**：原因只以散文串进 `question` 与 `context_refs[1]` | **否（只能反解析）** | conductor |
| L3 终态结论 | `<key>/l3-verdict.txt`（读 `conductor.py:659-671`，写 `_persist_l3_verdict:680+`）、`<key>/l3-report.md` | `meets`/`below` + 报告路径 | **是**（闭集枚举） | conductor |
| L3 reviewer 输出 | `<key>/workers/<l3-aN>/output.md`（要求的两节）/ `report.md` | `## Quality Gate Report` / `## Achieved` + 散文章节 | **否**（`_parse_l3_output` 只做节存在性检查，内容需人读） | reviewer worker |
| advance 失败类 | timeline `advance` 事件（分类 `conductor.py:786-800`） | `class ∈ {interface-drift, gate-blocked, timeout-env, other}` + `detail` 原文 | **是（class）** + 否（detail） | conductor |
| 尝试/轮次计数 | `state.used_rounds` + `<key>/workers/<task>/task.md` 的 `attempt` + timeline `dispatch` 事件 | 整数计数 | **是** | conductor |
| roadmap key-status | `_roadmap.md` `> key-status: k=stalled`（`roadmap.py:63-68`、`update_key_status:505`） | `running/done/stalled/closed-legacy` | **是** | conductor（锁内） |
| roadmap stage status | `_roadmap.md` `> status:`（`roadmap.py:52-61`） | `pending/approved/running/closed/closed-human/halted` | **是** | conductor（锁内） |
| stage dossier | `_autopilot/stages/stage-N-close.md`（生成 `conductor.py:722-750`） | 表格 `{key, final phase, l3 verdict, l3 report, evidence}` | **是，但 verdict 列可能陈旧** | conductor |
| timeline 事件 | `timeline.py:67-85`（17 类闭集） | `gate-created/gate-answered/stalled/resume/stage-close/goal-halt/l3-no-verdict/type-rejected/target-config-rejected/dispatch/advance/config/beat/…` | **是**（事件名 + `key`/`stage`/`seq`/`ts`） | conductor |
| 面板行 | `monitor.ts:89-95`（`MonitorGate` **只有 id/kind/stage/key**）、`:596-599`、`:603-627`、`:644-654` | pending gate 的 id/kind/scope + 应答命令 | 是，但**不含 `created_at`/`question`** | TS |
| `/autopilot gates` 列表 | `console.ts:182-198` | pending 的 `kind`/`scope`/`question`/`created`/`path` | 是（给人看） | TS |
| `mw doctor` | `mw_common.py:2022-2065`（`_doctor_autopilot`） | **只有 xkey verify 配置**（`xkey_repair/verify_cmd/verify_argv/missing`） | — | 无 gate/stall 内容 |
| 人的回答（真实判据所在） | gate 文件 `note` 字段 | 散文：成因 / 修复记录 / 复核命令与结果 / 未达成登记 / 下一步 | **否** | 人 |

##### F2b 人做判断时实际看的是什么（从 34 条 note 归纳，5 项）

1. **成因归类**："框架侧机械假阴" vs "真实缺陷"（例: FM gate-0004 note 判定 `_done_transaction` 词表不对齐；E2 gate-0014 note 列出 5 项真 FAIL）。
2. **是否已修/如何修**（例: FM gate-0002 note 给出"`dispatch.render_task_md` 渲染配置值 + config 提到 60/4MB + conductor 已重启"）。
3. **复核命令与实测结果**（例: FM gate-0004/0007 note 的 `check_gate(key_dir, done) 实测 ok=True`；E2 gate-0005 note 的 `verify_k7.py exit=0（32 AC + 32 VC 全绿）`）。
4. **未达成项与边界声明**（例: E2 gate-0003 的 "approve 不表示其完成"、FM gate-0009 追加 7 条 Stage 约束 + "禁止把待授权项记为达成"）。
5. **下一步动作**（续跑 / 转 `closed-legacy` / 拆 task / 改模型）。

其中 **1、2、4、5 只存在于人写的散文里**；3 可以在机器上重放但**当前没有把结果写回 gate**。

#### F3 — 三态判定表（本卡核心产出）

判据列固定为: **(a)** 决策依据可否由磁盘文件判定 · **(b)** 答错的**可逆性**（能否撤销 / 是否解锁依赖或 stage 收口 / 是否烧 token 或改代码）· **(c)** 历史一致性与样本量。**反例**至少 1 个"如果自动过会错"的具体情形。

| gate kind | 决策内容 | (a) 依据可判 | (b) 可逆性 | (c) 历史一致性 / 样本 | **判定** | 反例（自动过会错） |
|---|---|---|---|---|---|---|
| `stalled` | "遗留关闭（`closed-legacy`）还是人工介入后重试？" | **部分**。原因**类别**可机器抽（F1d，5 类）；**"假阴 vs 真缺陷"不可**（要读 `l3-report.md`/reviewer `output.md` 散文） | approve = 续跑一轮（烧 token、可能改代码；可再 stall，但已花的不退）+ `_resume_credits` **每次 approve 永久 +1、无上界**（`:2273`）⇒ 自动 = 取消预算上限。reject = `closed-legacy` → `_DEP_SATISFIED`(`:56`) **解锁依赖方 + 允许 stage 收口**（`:629-631`）⇒ **不可逆** | 22/22 approve（100%）；但 ≥16 条耦合带外修复、7 条重复 stall、1 条洪泛重放 5588 次 | **仅给建议**（默认）；仅"机器可证假阴 + per-key 上界 + 只 approve"的窄子集可进**影子模式** | ① 按"历史 100% approve"自动过 → E2 gate-0014/0015（L3 below 里混着 **真缺陷**：37 PASS/5 FAIL、15 PASS/1 FAIL）被反复续跑；② 更危险：按"历史 0 reject → 自动 reject 清队列" → 把真缺陷 key 标 `closed-legacy`，**解锁依赖并让 stage 收口 = 伪造完成**（FM gate-0004 note 明写"不做 closed-legacy：放弃即等于丢弃已交付成果"） |
| `stage-confirm` | "LLM 提案的这个 stage 该不该启动？" | **结构面是**（`roadmap.validate_roadmap:367-425`: ≥1 key、goal 非空、dep 指向同/前序 stage、key-status 集合一致、无环）；**内容面否**（stage 目标是否对得上项目 goal、key 划分是否合理），且提案是 **LLM 自产**（`_dispatch_roadmap_writer:520-556`） | approve = 解锁**一整 stage** 的 key 派发（烧 token + 写代码）⇒ 不可逆方向；reject = roadmap-writer 重新提案（最多 2 次，`:544-546`）⇒ 便宜 | 7/7 approve；等待 p50 0.12h（人总是快速批准） | **仅给建议**（机器预检 + 影响面提示）；**不可自动** | FM gate-0009 的 note 给 Stage 2 **追加 7 条约束**（A-02/A-05/A-08/A-09/A-10/L-1/C-09）与明确禁令；E2 gate-0008 的 note 明确"拒绝写 `E:\Engine2Up`""拒绝代填人工抽样值"。人在这道门做的是**收窄范围**——自动 approve 会丢掉这些约束，等于授权一个无界 stage；且 D-105 的设计就是"LLM 提案、人盖章"（`gates.py:1-20`），自批即取消该闸 |
| `stage-close` | "全部 key 已终态，是否闭环并开放下一 stage？" | **结构面是**（全 key 终态由 key-status 机器判定 `:629-631`；dossier 机器生成 `:722-750`）；**"目标是否真的达成"否**；dossier 的 `l3 verdict` 列**可能陈旧** | approve → stage `closed` → **只开下一 stage 的 `stage-confirm` gate**（`_ensure_next_stage_gate:409-432`），**不会自动派发任何 key** ⇒ 破坏面被下一道门兜住；reject → stage `halted` → 需人工改 roadmap 才能继续（比 approve 更难恢复） | 4/4 approve + **2 条长期 pending**（JC `stage-close` stage-2 自 2026-09-17 起 **9 天**未答）；等待 max 136.4h | **可自动（严格条件 + 仅 approve）** | FM gate-0008: dossier 把 `gui-shell-spike`/`gui-contract-surface` 标 `l3 verdict=below`（**首轮快照**，mtime 早于读上限修复；实际最终 31/31、23/23）——若无条件按 dossier 自动过，会把"档案陈旧（产品缺口 C-11）"静默变成"已终态"。**且该自动化的安全性依赖 `stage-confirm` 不自动**（否则 `auto-close → auto-confirm → auto-dispatch` 连成无人链） |
| `budget-exhausted` | "L2 回路达轮上限且仍有缺口——追加一轮还是标记 stalled？" | **完全可判**（`loop` 名 + `used`/`limit` 全在盘：`state.used_rounds` + `conductor.py:986-1001`） | approve = **恰好 +1 轮**且有内建上界（`:990` 第二次直接 stall）；**reject 也不终结 key**（只 `mark_stalled` `:986-989`，再由 `stalled` 门决定）⇒ **唯一两向都"软"、都带界**的门 | **0 样本** | **证据不足 → 影子模式**（只记录不动作，design 期验证） | 无历史反例可举（这正是"证据不足"的判据）。结构上最干净，但**把一条从未被走通的路径设成默认路径**本身就是风险：它的 approve 会额外烧一轮 token，而"缺口能不能靠一轮修好"没有任何历史依据 |
| `goal-change` | "goal.md 变了——恢复还是保持停摆？" | **否**。mtime 变更是机器可判（`:2063-2083`，但 `goal-halt` 的 detail **只有 `mtime_ns X -> Y`**）；"改了什么、是否推翻现有计划"必须读 goal.md 散文 diff | **reject 目前是 no-op**：`tick()` 只要 gate 不再是 `pending`（无论 approved/rejected）就刷新 baseline 并恢复（`:2100-2111`）⇒ 两答案状态机效果**相同**；不答 = `halted-goal-change` 全停（零派发） | **1/1 approve**（JC 唯一实例） | **绝不可自动** | JC 唯一实例的 note 原文："核心 Goal/Context/Key Constraints verified intact"——人**逐节核对**目标文件才放行。自动 approve 会在 goal 被实质改写（如目标从"构建 X"改成"构建 Y"）时照样恢复，而 reject 路径**没有任何差异行为**可兜住它；同时抹掉"人看过目标变更"这一信号（AC-015(d) 注意力掩盖） |
| `xkey-authorize` | "追认一条跨 key 红修复授权？" | **结构面是**（`request_id`/ticket/ledger 全结构化：`:2733-2760`、`_consume_xkey_gate:2798-2855`）；**写面判据不存在** | approve → 派 proposal worker → conductor **应用受限修复（改代码/改文件）**；reject → 只留账本（可逆） | **0 样本**（`xkey_repair` 默认 `false`，三项目未开） | **绝不可自动** | AC-014 的现状反证：写面纪律只存在于 **11/248** 份任务书的散文里、`write_scope` 在**生产代码零命中** ⇒ 机器**无法**判定"这次修复是否越出 owner key 的写面"；自动授权 = 机器授权越界写 |

**非门的机器决策（已在"自动"列，无人工参与，不在 C 的范围内）**：

| 事件 / 机制 | 是门吗 | 人工参与 | 说明（锚点） |
|---|---|---|---|
| `type-rejected` / `target-config-rejected` | 否（dispatch fail-closed 拒绝） | 无 | 零 queue 行 + 事件，机器已自动处理（`dispatch.py:437/479/511`）；0 生产样本 |
| `l3-no-verdict` | 否 | 无 | 机器 re-review（`conductor.py:1630-1640`）；E2 10 次；累计到 `l3_limit` 才升级成 `stalled` 门 |
| `goal-halt` | 否 | 无 | 变更检测事件（`:2093`），触发 `goal-change` 门 |
| `resume` | 否 | 无（是人 approve 的机器效果） | `:2349`；FM 6691 次里 **6686 次是洪泛重放** |
| `stage-close`（事件） | 否 | 无 | dossier 写入（`:642-646`），随后开门 |

#### F4 — 不可自动化白名单（问题 4：逐条带证据，不凭感觉）

| # | 白名单项 | 理由（证据锚点） | 违反后的首个可观测症状 |
|---|---|---|---|
| W1 | `goal-change` 的**全部**方向 | ① 判定面是"目标是否/如何改变"（语义，非磁盘可判，F3）；② `reject` 是 no-op（`:2100-2111` 不分 status）⇒ 自动答把这道闸变成 no-op；③ 唯一实例（JC gate-0002）的 note 是"逐节核对 goal.md"；④ 它是 AC-015(d) 注意力掩盖的典型面 | timeline 上出现 `goal-snapshot` 而**没有对应的人工核对记录**：目标被实质改写后 roadmap 仍按旧目标推进，直到 stage-close 的 dossier 与 goal.md 对不上 |
| W2 | `xkey-authorize` 的**全部**方向 | ① 门的语义就是"授权跨 key 写面"；approve 的链条会**改代码/改文件**（`_consume_xkey_gate:2798` → proposal → apply）；② 机器判不了写面越界（AC-014：写面纪律 11/248 份散文、`write_scope` 生产零命中）；③ 0 生产样本 | 出现"越出 owner key 写面"的提交/文件改动，且 ledger 里有一条 `status=approved` 但没有机器可读的 `write_scope` 边界 |
| W3 | **所有 reject 方向**：`stalled` reject → `closed-legacy`、`stage-close` reject → `halted` | ① `closed-legacy ∈ _DEP_SATISFIED`（`:56`）⇒ **解锁依赖方 + 允许 stage 收口**（`:629-631`）= 伪完成；② **不可撤销**：`_consumed_gate_ids`（`:297`）只从 timeline 的 `gate-answered` **反推 id 做去重**，全仓没有任何"撤销已消费 gate / 把 key 从 closed-legacy 拉回"的入口；③ reject 在 3 项目 15.1 天 **0 样本** ⇒ 收益与风险都无法用历史估算 | stage 在一个含 `closed-legacy` key 的情况下收口；dossier 的 `l3 verdict` 列出现 `below`/`none` 而 stage 已 `closed` |
| W4 | `stage-confirm` 的 **approve** 方向 | ① 提案由 LLM 自产（`_dispatch_roadmap_writer:520`），自批 = 取消 D-105 的"人盖章"角色分工（`gates.py:1-20`）；② approve **一次性解锁整 stage 的 key 派发**（烧 token + 写代码），不可逆；③ 历史 note 显示人在此门**加约束/收窄范围**（FM gate-0009 七条约束；E2 gate-0008 两条明确拒绝） | 一个 stage 在没有任何人读过的约束条件下开跑；stage 内的 key 把"待授权/人工项"记为达成（正是 note 里被明令禁止的动作） |
| W5 | `stage-close` 的 **approve**，当机器证据不全 | 机器证据不全的定义（必须全部满足才允许自动）: ① 每 key `l3-verdict.txt == meets`；② 无 `closed-legacy` key；③ dossier 的 verdict 列**取最终轮**（C-11 修好或机器重取）；④ 无未登记的待授权/人工项。反例：FM gate-0008（dossier 陈旧 `below`）；E2 gate-0003（人把"approve 不表示其完成"写进 note = 未达成登记是这道门的实质输出） | stage 已 `closed` 但 dossier 的 verdict 列与 `l3-verdict.txt` 不一致；或收口时没有人记录过未达成项 |
| W6 | 统一判据（覆盖 W1–W5 的"会写代码/改文件/改 roadmap"面） | 任何答案若其后果包含 **`_xkey_apply_stage` 的 proposal→apply 写面**，或让 key 进入终态集 `{done, closed-legacy}`，或让 stage 进入 `running`/`closed` —— 则必须有人工参与。落点：`conductor.py` 的 `_set_stage_status:380`、`update_key_status:505` 的调用者、`_xkey_apply_stage` | — |

**反向确认（不属于白名单的）**：`budget-exhausted` 与 `stalled` 的 **approve** 不写代码、不改 roadmap 以外的东西、且有 `round_budget`/`_resume_credits` 的上界概念（虽然 credits 当前无上界）⇒ 它们**可以**进入影子模式评估（不是白名单项）。

#### F5 — 自动化的最小证据要求（问题 5：先补哪些字段/事件）

前置原则：**gate 必须携带"它能被机器判定的依据"**。当前 12 字段（`gates.py:68-81`）里 0 个字段承载判据。

| 面向的门 | 现状缺口（锚点） | 必须先补齐（最小集） |
|---|---|---|
| `stalled`（第一优先） | ① 原因只在 `question`/`context_refs[1]` 的散文串里（12 个 `mark_stalled` 调用点：`:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941` 全部只传 question+refs）；② 无 `loop`/`used`/`limit`/`credits` 结构字段（只在散文 "budget 2, credits 1"）；③ 无 l3 判据指针（`l3-verdict.txt` 的值要机器另开文件）；④ `_resume_credits`（`:2273`）的值**不落 gate、也无上界**；⑤ 无 `decided_by_system`/`auto_policy_id`（`answered_by` 是自由串，人与机不可区分）；⑥ 无 `expires_at`（TTL 载体，`gates.py:68-81` 无时间字段） | ① frontmatter 增 **`reason_code`**（闭集，与 5 个原因类一一对应，12 个调用点各写一个码）② 增 **`machine_evidence`**（结构化引用：`l3-verdict.txt:below`、`advance:class=gate-blocked,count=5`、`exec:task=005,attempts=2/2`、`worker:ap-…-l3-a2:failed`）③ 增 **`credits_used`/`auto_decisions`** 计数（否则自动决策无法有界）④ 增 **`decided_by_system` + `auto_policy_id`** ⑤ 增 **`expires_at`** |
| `stage-close` | ① dossier 的 `l3 verdict` 列是**首轮快照**（产品缺口 C-11；FM gate-0008 实证）；② "未达成台账"只在人 note 里（E2 gate-0003）；③ 无"含 `closed-legacy` key"的结构字段 | ① dossier verdict 取最终轮（或 gate 增 `verdicts_final` 快照）；② 机器生成 **`open_items`**（below 计数 / `closed-legacy` key 列表 / needs-rerun / 待授权项）并落 gate |
| `stage-confirm` | ① 内容面对齐无判据；② 提案与 goal 的版本没有绑定；③ 人填的范围约束（reject note）无法被后续消费 | ① gate 增 **`roadmap_validation`**（`validate_roadmap` 逐条结果）② 增 **`proposal_sha256` + `goal_mtime`**（把提案绑到 goal 版本）③ 人填约束需可机器引用（结构字段而非 note 散文） |
| `goal-change` | `goal-halt` 的 detail 只有 `mtime_ns X -> Y`（`:2093`） | ① 落 **`goal_diff`**（增删段数/字数/关键节命中，机器可算）② gate 增 **`goal_before_sha256`/`goal_after_sha256`** |
| `xkey-authorize` | 0 样本 + 写面判据不存在（AC-014） | 前置（不属本 key）: 机器可读写面声明（AC-014）；随后 gate 增 `write_scope`/`verify_argv`/`blast_radius` |
| `budget-exhausted` | 0 样本 | 同 `stalled` 的 `reason_code`+计数；先影子模式积累样本 |
| 通用（审计） | `answered_at` 可人工回填（E2 gate-0007 早 4.1h；FM gate-0002/0003 晚 104s）⇒ 审计面不可信；`MonitorGate` 不带 `created_at`（RQ-8 同结论） | ① 应答时同时写机器时刻（不可由应答者填），或把 `answered_at` 改为"文件 mtime"口径 ② 面板/doctor 带上 `created_at` 与等待时长 |

#### 【推断】

- **I1**：`stalled` 的 22/22 approve **不能**作为"可自动"的数据依据，因为 approve 的真实内容是"人已完成带外修复之后的收据"（16/22 有关键字证据、其余 6 条也有成因诊断）。把它自动化等于自动化收据、而不自动化修复 ⇒ 依据不成立。
- **I2**：C 路线（机器自动过"部分" gate）在**当前数据上唯一可立项的形状**是三条：① `stage-close` 的 approve（结构可判 + 破坏面被下一 `stage-confirm` 兜住）；② 对**全部 6 类**做"超时 → 提醒/升级"（不是应答）——这能直接吃掉 287.7h 的等待成本而不引入任何决策风险；③ `stalled` 的"机器可证假阴"**影子模式**（只记录不动作）。其余任何"自动过"都缺 (a)(b)(c) 三项中的至少两项。
- **I3**：真正能压缩 (c) 的仍是"**消除 stall 成因**"（本仓库近 5 个 key 的修复路线：readcap 注入 `6254783b`、L3 判定源 fallback `a0c36fcc`、closure reprompt `d20a270d5`、xkey 通道 `181a75332`；RQ-6 候选 2）。在成因未修时自动答 `stalled` 门只会产生 FM 式振荡（实证：同一 key 一夜重放 5588 次、E2 同 key 3 连 stall）。
- **I4**：把 `stage-confirm` 排除在自动之外，是 `stage-close` 能安全自动化的**前提**（否则 `auto-close → auto-confirm → auto-dispatch` 连成无人链，破坏面不再被兜住）。
- **I5**：`goal-change` 的 `reject` 是 no-op（`:2100-2111` 只判"是否仍 pending"，不判状态），与门文案 "or reject to stay halted" 的实现承诺不符 ⇒ 该门现在是"**必须人答否则全停，但答什么都一样**"。这是一个既存缺口，design 期应先决定 reject 语义再谈自动（不属本卡改）。

## 结论 → 决策映射

**支撑 AC-016（机器自动过"部分" gate 的边界与判据）**：

| AC-016 需要的判定 | 结论 |
|---|---|
| 哪些 gate **可自动** | `stage-close`（**仅 approve**，且 F5 的 4 项机器证据齐备）→ 这是唯一在当前代码结构下"自动过之后仍有人工兜底"的门；`budget-exhausted`（结构最干净、两向都有界）→ **证据不足，先影子模式**；`stalled` 的 **approve** → 仅"`reason_code` ∈ 机器可证假阴"且 per-key 有上界时，进影子模式 |
| 哪些 gate **仅给建议** | `stage-confirm`（全部方向：机器输出 `roadmap_validation` 预检 + 影响面 + 提案 vs goal 差异，人拍板）；`stalled` 的**默认**处置（机器输出原因类 + 证据指针 + "是否需要带外修复"的提示，人拍板） |
| 哪些 gate **绝不可自动** | F4 白名单 W1–W6：`goal-change`、`xkey-authorize`、**所有 reject 方向**（`closed-legacy` / `halted`）、`stage-confirm` 的 approve、证据不全的 `stage-close` approve |
| 三态判据 | (a) 依据可机器判定: `budget-exhausted` **是** / `stage-close` **结构是、内容否** / `stalled` **类别是、性质否** / `stage-confirm` **结构是、内容否** / `goal-change` **否**；(b) 可逆性: `budget-exhausted` 两向**软且有界** > `stage-close` approve（被下一门兜住）> `stage-confirm` approve > `stalled` reject（`closed-legacy`，**不可逆**）；(c) 历史: 4/4 门 100% approve，但 reject 0 样本、3 门 0/1 样本 |
| 反例 | 逐门见 F3 末列；三个最硬的: FM gate-0009（人在 confirm 上加约束，自动会丢）、FM gate-0008（dossier 陈旧 verdict）、E2 gate-0014（L3 below 里混真缺陷，自动 approve/reject 都会错） |

**直接回答 spec §4 U-8「C 由数据定」是否可行**：

- **可以定"答案唯一性"**：34/34 approve（`stalled` 22、`stage-confirm` 7、`stage-close` 4、`goal-change` 1），样本量与窗口见 F1a；复算见方法节脚本。
- **不能只由答案分布定"可自动"**：C 的判据是三要素合取（依据可判 ∧ 答错可逆 ∧ 有上界）。当前 6 个门里 **0 个**同时满足三要素；`stage-close` 满足 1.5 项（结构可判 + 被兜住，但需要 F5 补字段）。而 `reject` 0 样本意味着**最危险的那一半（`closed-legacy`）连收益/风险都无历史可估**。
- **因此给 spec 的措辞建议**：C 的范围不由"答案分布"定，而由"**F5 最小证据要求是否补齐**"定；在补齐前，C 的可交付物是 **① 全类型超时提醒/升级 + ② `stage-close` 条件化自动 approve + ③ `stalled`/`budget-exhausted` 影子模式**。样本量对阈值的支撑: `stage-close` 只有 4 条 approve（+2 条长期 pending，最长 9 天），**不足以定 TTL 阈值** ⇒ TTL 需要新增观测（影子模式期间记录"若阈值 N 会命中几条"）。
- **对 `[VERIFY]` 的三项直接答复**: `uniform_answer_gates=4`（有样本的 4 个门都是 100% approve）；`reject_path_samples=0`；`auto_candidates=[stage-close(approve, conditional), budget-exhausted(shadow), stalled(approve, machine-provable-subset, shadow)]`。

**与相邻卡的边界（不重复）**：门清单/阻塞范围/等待时长/无人值守策略现状 = RQ-8；护栏机制、`_resume_credits` 回放估算、kill switch、审计可撤销性 = RQ-11；stalled 生命周期与"占不占槽" = RQ-6；槽位利用率 = RQ-3；并发锚点 = RQ-1。本卡独有的新增：**答案分布（含 JC 第三项目与 FM 洪泛陷阱）**、**载体字段的机器可读性**、**三态判定表 + 白名单**、**最小证据字段清单**。

## 数据缺口

1. **`budget-exhausted` / `xkey-authorize` / `type-rejected` / `target-config-rejected` / `goal-halt` 生产 0 样本** ⇒ 无法用数据判定"可自动"，只能影子模式。`budget-exhausted` 的结构推理（两向有界）虽强，但**没有一条真实 approve/reject 可验证**。
2. **`goal-change` 只有 1 条样本**（JC）：既看不出答案一致性，也看不出"目标变更幅度 → 答案"的关系。要定自动化需更多样本。
3. **`reject` 路径 0 样本**（3 项目、15.1 天、34 条应答里 0 条 reject）⇒ `closed-legacy` 的收益（清理死 key）与风险（伪完成 + 解锁依赖）都无法用历史估算；RQ-11 的回放估算同样受此限。
4. **真实"无人值守"反例只有 JC 的 2 条 pending stage-close**（stage-2 自 2026-09-17 起 **9 天**未答；stage-1 自 09-26 起 0.3h）+ 1 条 136.4h 才被答的 stage-close。**无法区分"项目被弃置"与"人忘了答"** ⇒ 要量化"无人工应答的损失"仍需受控实验（同 RQ-6 数据缺口 3）。
5. **`answered_at` 不可信**（E2 gate-0007 早 4.1h、FM gate-0002/0003 晚 104s）⇒ 所有基于该字段的等待分布都带噪声；本笔记改用 mtime 口径并给出双口径对照。若有第三方引用 RQ-6/RQ-8 的等待数字，需注明口径。
6. **FM 的 6684 个归档 pending gate 使"未答门"统计失真**（算进去 FM 未答率 = 6684/6694 = 99.9%，但其中没有一条是真实待决决策）；任何"未答率/TTL 命中率"的统计必须先剔除洪泛目录。
7. **没有"答案 → 后果"的因果台账**：approve 后该 key 是否真的收口、是否再次 stall，只能从 timeline 反推；本笔记的"重复 stall"只到 key 级（7/22），没有到"原因类级"的重复率。
8. **面板/doctor 无 gate 陈旧度**（RQ-8 已覆盖可观测性缺口；本卡补充一点：连 `created_at` 都没进 `MonitorGate`，因此"影子模式要观测什么"也需要先补这个字段）。

[VERIFY] RQ-10: projects=3(FM,E2,JC) gates_analyzed=34 distinct-answered(FM10/E2 18/JC6)+6686 pending(FM 6684 flood + JC 2) answer_dist=approve 34 / reject 0 / other 0 (stalled 22/22, stage-confirm 7/7, stage-close 4/4, goal-change 1/1) uniform_answer_gates=4(100% approve, all kinds with samples) rejects=0 reject_path_samples=0 windows=FM 70.8h(09-23T09:06Z..09-26T07:54Z)/E2 100.3h(09-22T03:35Z..09-26T07:54Z)/JC 15.1d(09-11T03:33Z..09-26T04:37Z) wait_mtime: stalled n=22 p50=3.60h max=17.40h sum=137.3h, stage-confirm n=7 p50=0.12h max=2.79h, stage-close n=4 p50=6.03h max=136.4h sum=146.9h, goal-change n=1 0.24h zero_sample_gates=[budget-exhausted, xkey-authorize] zero_sample_events=[goal-halt(FM/E2), type-rejected, target-config-rejected] reason_classes(machine-parseable from context_refs[1])=[L3-below 8, L3-no-verdict 4, advance-gate-blocked 5, advance-interface-drift 1, exec-exhausted 4] auto_candidates=[stage-close(approve,conditional: verdicts-final+open_items+no-closed-legacy+no-pending-human-items), budget-exhausted(shadow-first,0 samples), stalled(approve, machine-provable-false-negative subset only, shadow)] suggest_only=[stage-confirm(all), stalled(default)] never_auto=[goal-change(all; reject is a no-op conductor.py:2096-2106), xkey-authorize(all; approve leads to code/file writes), every reject direction (closed-legacy ∈ _DEP_SATISFIED conductor.py:56 ⇒ unlocks deps + stage closure, not reversible; _consumed_gate_ids:297 has no undo), stage-confirm approve (LLM-proposes-human-seals, D-105), stage-close approve with stale/incomplete evidence (dossier verdict snapshot bug C-11, FM gate-0008)] hazards=[FM flood 6686 replayed gate-answered from 1 human approve (5588+1098) + 6684 archived pending gates ⇒ answer distribution must be counted per gate file/id not per event; _resume_credits:2273 unbounded per approve; answered_at hand-writable (E2 gate-0007 -4.1h)] minimal_evidence_gaps=[reason_code, machine_evidence, credits_used/auto_decisions bound, decided_by_system+auto_policy_id, expires_at on gate; final-round verdicts + machine-generated open_items for stage-close; roadmap_validation+proposal_sha256+goal_mtime for stage-confirm; goal_diff+goal sha for goal-change]
