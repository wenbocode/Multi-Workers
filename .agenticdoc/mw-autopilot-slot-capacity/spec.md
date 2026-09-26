# Spec: mw-autopilot-slot-capacity

> Key: mw-autopilot-slot-capacity
> 创建时间: 2026-09-26T07:45:00Z
> 状态: **draft（未锁定：AC 号在 Step 5 用户确认后锁定）**

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，解决单 Agent 长上下文溢出和无法并行的问题」中的**"并行"这一核心承诺**。当前 autopilot 的 key 级并行度上限默认 2（`max_parallel_keys`），本 key 要回答"这个数字从哪来、对不对、够不够、该由谁决定"，并给出可验证的改动或明确的"不改"结论。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1（goal Key Constraints）：**不引入中心化调度器**——并行度只能是文件驱动协调（`_index.parallel` + 文件锁）下的参数与判定，不得引入内存中的全局队列/调度线程来"管理"并发。
  - GC-2：**Worker 进程级隔离**——提高并行度不得以共享进程/共享可变状态为代价。
  - GC-3：**文件锁并发控制**（`_workers.parallel` / `_index.parallel` 的并发写用 `O_CREAT|O_EXCL` 锁）——并行度上升会放大所有共享文件的写入竞争，必须一并评估。
  - GC-4（mw-worker-timeout-convergence 修订）：**活动看门狗 + 墙钟兜底 + 收敛检查点**——并行度提高后 watch/dog 的语义不得退化（例如因机器更忙而误判 idle）。
- 冲突：无。
- 预期收益：本 key 达成后，PM 能在有证据的前提下回答"并发上限该设多少、由谁设、超了会先坏在哪"，并让该数字成为**可配置 + 可观测 + 有失败语义**的机器参数，而不是一个埋在 `DEFAULT_CONFIG` 里的 2。判定方式：`achieved.md` 对照本 spec §3 的 AC 逐条给出实测证据（含"提高后首个失败模式"的实测或明确声明未实测）。

## §1 功能概述

### 1.1 目标

回答并落实一个问题：**autopilot 的并行槽位（slot）为什么是 2，并行度是否不足。**

首先必须把"slot"这个词的含义钉死——代码里它**不是 worker 数**：
- `max_parallel_keys`（默认 **2**，floor 2，`autopilot/config.py:16/52/70`；TS 镜像 `status-model.ts:79/106/136`）= **同时推进的 key 数上限**；
- `conductor.py:289` 用它 gate 派发（`len(in_flight_keys) >= max(1, max_parallel_keys)` ⇒ 本轮不再起新 key）；
- 监控面板的 `slots ${used}/${max}`（`monitor.ts:521-522`）取的是 `busyKeys.size`（有 running worker 的 key 集合）。

因此本需求至少是**两层并行度**的问题：**key 层**（几个 key 同时推进）与 **worker 层**（同一时刻几个 worker 进程在跑，单 key 内与全局）。现状调查显示代码里只见到 key 层的显式上限，worker 层的上限来源待取证（见 §4 待确认 U-4）。

### 1.1.1 用户已确认的现象（U-2 答复 = `c+d`，2026-09-26）——本 key 的主战场

- **(c) 夜跑/无人值守跑不完，槽位被卡死的 key 占着** ⇒ 关键不在上限值，而在「**槽位与 stalled 状态无关**」：若 stalled key 仍计入 in-flight，则 2 个槽位被 2 个卡死 key 占住时，把上限提到 4 只会让 4 个 key 一起卡住。夜跑场景下无人处置 stalled gate ⇒ 这一条决定吞吐上限。
- **(d) `slots 2/2` 时实际在跑的 worker 很少** ⇒ 面板的 `slots` 是 **key 层**计数（`busyKeys.size`，`monitor.ts:521`），2/2 只说明「2 个 key 各至少有 1 个 worker 在跑」。真正偏低的是 **worker 层利用率**，而它不受 `max_parallel_keys` 控制。
- **旁证（已由 RQ-5 复算固化）**：上一 key（`mw-autopilot-verify-cli`）PM 手工派发路径**峰值 6**（`design-rqd1..6` 同批起跑、重叠 306s；PM 记忆的 `mavc-t06/t01b/t02c/t08` 四人组全员重叠 **105.5s**），MW 全项目 PM 通道 166 session / 峰值 6；而 **autopilot/conductor 路径**（E2Feature 431 个 `ap-*` session / 100h）**每 key 峰值恒为 1**，项目峰值 4。⇒ 已证实是 **conductor 的 per-key 硬顺序**（RQ-5 判定 A 类：三重结构性保证 `conductor.py:258-264` + `:287-288` + `_advance_key` 每分支只派 1 张 `:908-1015`），不是机器容量。不是机器容量。

⇒ **本 key 的优先面（2026-09-26 用户确认：先修 (c)）**：

1. **(c1) 无人值守的门阻塞（已确认为 (c) 主因）**——哪些 gate 必须人答、卡住 key 还是 stage/roadmap。**实测（RQ-6）**：**无 gate TTL / 超时 / 自动应答**（20/20 stalled gate 全靠人工，等待 **0.19–17.40h**）；stalled 占窗口墙钟 **E2 46.6%（91.0h / 13 gate）、FM 54.6%（43.5h / 7 gate）** ⇒ 近一半时间 key 停在等人；**反向证据**：E2 曾 **3 个 key 同时 stalled 而 cap=2**（11h）⇒ 再次证明 **stalled 不占槽**，(c) 与槽位无关；
   **用户决策（2026-09-26）：门这条线选 C**——机器自动过**部分** gate；前置硬约束：必须先用调研证据定边界（RQ-10），并**为每条副作用配套防护机制**（RQ-11 / AC-017），不得先上自动决策再补护栏。白名单归属与熔断后动作待定（U-8/U-9）。
   **边界数据（RQ-10，3 项目 34 个唯一人工应答）**：`stalled` 22/22、`stage-confirm` 7/7、`stage-close` 4/4、`goal-change` 1/1 = **34/34 全 approve、reject 0 样本**；`stage-close` 最长等待 **136.4h**，JC 有 2 个 stage-close 长期 pending（最长 **9 天**）。三态结论：**可自动 = `stage-close`（仅 approve 方向）**；仅给建议 = `stage-confirm`、`stalled`；**绝不可自动 = `goal-change`（且实测 reject 是 no-op）、`xkey-authorize`、所有 reject / `closed-legacy` 方向**。
 **［REVISED @ 2026-09-26 by RQ-12］上句"可自动 = `stage-close`"不成立**：其前置（verdicts-final + open_items 空 + 无 `closed-legacy`）**不充分**，4 个实测反例——E2 Stage 2 的 `feature-l3-readcap-injection`（correction sidecar 写 `corrected_value=below` + `counted_as_done=false` + `pending-authorization`，而 `l3-verdict.txt=meets`、roadmap `=done`、stage 已 `closed`；**PM 已亲自抽验复核**）、FM Stage 1（dossier 2/5 `below`）、JC Stage 2（全绿但 goal 要求实机）、FM `gui-contract-mock-tests`（文件 `meets` / 复算 `below`）。深层原因是**命题选层**问题，见 AC-025。
   **用户追加决策（2026-09-26）：先 review gate 设计本身** —— 现状"gate 给我的审批信息没有内容量"。按**三种处置模式**重分类：(1) **硬需求且审批内容可自举验证** ⇒ 机器独立复算证据，不给人答；(2) **非阻塞性** ⇒ 不挡 key/stage，等**阶段目标完成后一次性复核**；(3) 其余 ⇒ 在窗口给人**简明扼要**的描述与选项。三分判定必须先有证据（RQ-12 可自举验证性 / RQ-13 阻塞与延后安全性 / RQ-14 人审最小信息集），**不得凭直觉分类**。
2. **(c2) idle 看门狗误杀**（实测 14 次，并发均值 2.14 即发生）+ `worker_timeout_min` 无消费者的死键（用户确认纳入本 key）；
3. **(c3) 残留非终态行占槽**——残余风险是**孤儿行**；stalled 触发的频率实测 ≈ 0（见 PM 裁定笔记 F6），故不得按"stalled 占槽"设计；
4. **(c3′) E2 型真缺槽**——第 3 个 key 实测排队 4.79h / 5.64h，队列深度 4；
5. **(d) 单 key 内 worker 派发的串行化点**排在 (c) 之后。

「`max_parallel_keys` 默认值 2 改不改」退为**次要**问题：现场 FM/E2 的 `config.json` **显式写了 2**，两条写路径都把 13 键材料化 ⇒ 改默认值对它们**是空操作**。

### 1.2 技术栈 / 语言

- Python（`packages/multi-workers/`：conductor / launcher / serve / mw.py）
- TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/`：monitor / status-model / pm 派发）
- 单机 Windows 开发环境；LLM 走本地 proxy 端口与直连 provider 的混合路由。

### 1.3 核心用户场景

1. **[主场景 c1] 无人值守的门阻塞**：夜跑时 gate 必须人答；一个 stalled key 不占槽但会卡住 key 队列与 stage 收口 ⇒ 无人值守下 stage 可能永不收口。需要：门清单 + 每类门的阻塞范围（key / stage / roadmap）+ 无人值守后果。
2. **[主场景 c2] idle 看门狗误杀**：实测 14 次 idle 判死（602–622s），发生在**并发均值 2.14**（max 3）——不是高并发导致，是阈值贴着 600s；且 `worker_timeout_min`（默认 30）**无任何消费者**。需要：阈值语义 + "真挂死 vs 模型/工具慢"的判据。
3. **[主场景 c3 / c3′] 占槽与排队**：占槽判定 = 存在非终态行（与 key-status 无关）；stalled 触发的频率实测 ≈ 0，残余风险是**孤儿行**（死进程 + 行仍非终态，最长 90 分钟静默窗）；E2 型真缺槽表现为第 3 个及以后的 key 排队。
4. **[主场景 d] 单 key 内 worker 层利用率低**：`slots 2/2` 时面板让人以为已满，实际同时运行的 worker 很少；一个 key 内有 N 张互不冲突的卡却串着跑。需要：worker 层实际并发度可见 + 串行化点被定位（是派发策略、相位门禁、deps 还是文件冲突判定）。
5. **[新增需求 2026-09-26 #3] gate 审核材料不可判定**：当前 gate 给人工审核的东西很模糊 ⇒ 操作者无法判定 (a) 这个 gate **是否必要**（该不该存在 / 能不能自动过）、(b) 答或不答的**影响面**是什么（会卡住谁、多久）。需要：每个 gate 类型的审核材料清单 + "必要性/影响"各自需要什么才能判 + 哪些可由机器从文件推导。
6. **一个项目内多个 key 抢同一批文件**：并行度上升后，同文件写冲突与"跨 key 冻结判据被覆盖"的风险（本仓库已发生过，见 `_pitfalls.md` P-018/P-019）——这是任何提高 worker 层并发方案的**必要安全面**。
7. **[次要] PM 单窗口 vs 多 key 推进**：PM 窗口一次只盯一个 key（watch key），但 autopilot 可同时推进 2 个 key；若将来提高 key 层上限，PM 注意力分配与"无人值守时的自动推进"需要一并回答。

### 1.4 范围说明（不做什么）

- 不包含：重写调度架构、引入内存队列/中央调度器（违反 GC-1）。
- 不包含：LLM proxy / 凭证隔离机制的重新设计（除非调查证明它才是并行度瓶颈，届时作为"依赖项"记录并单独立 key）。
- 不包含：pi 核心的改动。

## §2 业务约束

### 2.1 平台 / 环境

- 单机（当前开发机）+ Windows；worker 是独立 pi 进程；serve 常驻。
- 现有配置分层：项目层 `<root>/.agenticdoc/_autopilot/config.json`（13 键，fail-closed）+ 机器层 `~/.agents/autopilot-defaults.json`（当前仅 `xkey_verify_cmd`/`xkey_verify_cwd`）。

### 2.2 性能指标

- 槽位的价值必须能用**吞吐**衡量：单位时间内推进完成的 key 数 / 阶段数，而不是"同时开了几个进程"。
- 并行度提高后**首个失败模式**必须可观测（错误率、超时率、锁竞争、rate limit）。

### 2.3 安全约束

- 凭证隔离不变：每个 worker 只拿它需要的 API key（goal GC）。
- 不得因并行度提高而让某个 worker 拿到其它 provider 的凭证。
- **gate 目录被工具层封堵**：`xkey-gate-guard.ts` 禁止 agent 写 gate 目录（RQ-8 的只读分析命令都被它拦过）⇒ 这是**有意的安全属性**：门不得由被审对象自己答。任何自动决策机制**必须在 conductor（Python）侧实现**，不得通过放开 agent 写 gate 的权限来实现（见 AC-020）。

### 2.4 集成依赖

- `.agenticdoc/_index.parallel`（key 状态/相位/owner 的去中心化账本）
- `.agenticdoc/_workers.parallel`（worker 队列与状态）
- `mw serve` / launcher / conductor / monitor / doctor

## §3 验收标准（AC）

> 状态：**draft（未锁定）**。Step 5 用户确认后锁号。

| AC 编号 | 描述 |
|--------|------|
| AC-001 | `evidence/research/spec-*.md` 至少一份笔记以 `file:line` 锚点给出「**key 层上限**」「**worker 层上限（单 key 内 / 全局）**」「**serve/launcher 层是否存在并发限制**」三者的完整清单（每项：变量名、默认值、生效位置 file:line、可配置性），且对"worker 层无显式上限"这一类否定结论必须附**反证式范围声明**（读过的代码范围 + 为什么该范围内没有）；另有一份笔记做**独立交叉核对**并报告差异 |
| AC-002 | 给出并行度上限的**现状成因判定**：对每个上限逐一标注"设计约束（附出处 file:line / 文档 / 提交）/ 历史默认 / 无依据"三态之一；不得出现"大概是"这类无出处结论 |
| AC-003 | 给出**槽位利用率与排队实测**（≥2 个真实项目）：key 层打满率（达到上限的时间占比）+ **worker 层同时运行数分布**（平均/峰值）+ **并发 2 vs 1 的吞吐与失败率对比**（中位墙钟、失败率、失败类型分布）+ 样本量与时间窗；每个数字可由文件复算（给出复算命令/脚本片段） |
| AC-004 | 给出**占槽判定规则**的代码锚点（按行状态、与 key-status 无关）+ 三类状态（stalled / done / 在飞）的占槽表 + **频率实测**（stalled 占槽占比、孤儿行占槽占比）；若频率数据不足以实测，必须给出"无法实测"的诚实声明 + 可验证它的方法与所需数据 |
| AC-005 | 给出 **(c2) idle 看门狗误杀**的证据链：14 次（或实测到的全部）idle 判死事件的复算 + 每次死亡时刻的**活动特征**（是否真的无活动、阈值余量多少）+ 阈值 600s 的出处 + `worker_timeout_min` 无消费者的**处置判定**（接线或删除，二选一并给证据） |
| AC-006 | 给出 **(c1) 无人值守门阻塞面**：必须人答的 gate 全清单（每项：谁答、`file:line`、无人值守后果、阻塞范围 key/stage/roadmap）+ stage 收口语义（一个 stalled key 是否让 stage 永久停住，附判定分支原文）+ 每类 gate 的等待时长分布实测 + 现有无人值守策略**有无**（不存在就明确写"不存在"） |
| AC-007 | 给出 **(新增需求) gate 审核材料可判定性**：每个 gate 类型当前"给人看的东西"清单（字段/文件/面板行 + `file:line`）；判定"**必要性**"与"**影响面**"各需要什么输入；哪些必要性可由机器从文件推导（给推导依据与反例），哪些不能；缺口清单与最小补面 |
| AC-008 | 给出 **(d) 的直接证据**：单 key 内 worker 派发的**串行化点清单**（每点：函数 `file:line` + 触发条件 + 硬顺序还是可并行）；并用同项目**两组真实运行**对比（autopilot/conductor 路径 vs PM 手工派发路径）的同时 worker 数，证明瓶颈位于哪一侧 |
| AC-009 | 给出 ≥3 个候选改动方案（覆盖 (c1)(c2)(c3)(c3′) 与 (d) 各路，且必须含"不改"一项），每项：改动位置（`file:line`/键名）、取值域与校验、**首个失败模式**（含判据 + 标注是已有史料还是 `[推断]`）、可逆性（如何退回、是否留残留）、GC-1/GC-3/GC-4 校验 |
| AC-010 | 两侧镜像一致性：任何被选中的参数/语义改动必须 Python 与 TS **逐字段一致**（P-021，verify 期两侧都跑）；若方案依赖**机器层覆盖 int 键**，必须先解决"空值即未决定"无 int 哨兵的语义缺口，否则不得采用该路径（否则是静默空操作） |
| AC-011 | 最终结论必须由 AC-002..AC-010 的证据链支撑，并**逐条回应 (c1)(c2)(c3)(c3′)(d)**：说明如何改善夜跑吞吐与 worker 层利用率，或为何不该动；"不改"也必须给证据化理由 |
| AC-012 | 可观测性：面板/`mw doctor` 能区分「key 层槽位」与「worker 层实际运行数（含 `pending` 行）」两个量（口径差异必须消除或显式标注），能指出谁占着槽、哪些行是孤儿/stalled、哪些 gate 在等谁；不新增误报（无 running worker 的项目显示 0 而非报错） |
| AC-013 | 给出**逃逸口与现存双写源**的证据：三个逃逸口（PM 手工通道无并发判定、**行提前终态化**、`xkey_repair` 提案通道）逐一定位 `file:line`；其中"行提前终态化"必须给出 ≥1 个**实测复算样本**（现状：两例，重试与旧进程重叠 **89.2s / 6.4s**）及对"同文件双写"的影响面；若无法判定置 `failed` 的 writer，必须写"无法判定"+ 可验证它的方法 |
| AC-014 | 给出**并发安全前置清单**：若方案要放开 per-key 并发，必须列出前置项（写面声明→机器可读→重叠拒绝；行终态化时机；锁一致性）并给出每项**现状证据**与缺位时的**首个失败模式**。现状反证（RQ-5）：写面纪律只存在于 **11/248** 个任务书的散文里，`write_scope|写面` 在**生产代码零命中**，`read_scope`/`deny_globs` 只拦读，`implementation-gate` 对 worker 一律放行 ⇒ 机器判定**为零** |
| AC-015 | 给出无人值守 gate 策略的**反作用清单**（若方案含自动 approve/reject/超时）：逐条给判据 —— (a) auto-approve × `_resume_credits` 无上界 ⇒ 夜间无限换 key / 烧 token；(b) `closed-legacy ∈ _DEP_SATISFIED` 会像 done 一样解锁依赖并放行 stage 收口；(c) 自动决策与 `advance_stall_ticks` 的 `stalled↔running` 振荡（FM 洪泛 6684 门 / 12h 已实证"看起来在跑、什么都没干"）；(d) 注意力掩盖（自动过后人看不见）。每条必须说明"如何检测它发生了" |
| AC-016 | 给出**自动决策边界与判据**（支撑 C 的"部分"二字）：逐 gate 类型一张表 —— 它在决定什么、机器能否从磁盘文件判（给可读字段与 `file:line`）、历史答案分布（approve/reject 比例与样本量）、答错的代价（可逆性、是否解锁依赖/stage 收口）；结论落在三态之一：**可自动 / 仅给建议 / 绝不可自动**，每条必须附判据与**反例**；并给出"不可自动化白名单"及其理由（理由必须有证据，不得凭感觉） |
| AC-017 | 给出**副作用防护机制**：对每条已知副作用逐条配套机制 —— (a) `_resume_credits` 无上界 ⇒ 需要什么预算/配额；(b) `closed-legacy ∈ _DEP_SATISFIED` 解锁依赖与 stage 收口 ⇒ 自动决策如何避免静默解锁；(c) `stalled↔running` 振荡 ⇒ 冷却/去重/最大自动轮次；(d) 注意力掩盖 ⇒ 可审计留痕与汇总。每条必须给：机制候选、实现面 `file:line`、**可检测信号**（如何知道它发生了）、以及缺位时的首个失败模式。**新机制必须留痕**（不得重犯"cap 阻塞零痕迹"的错误） |
| AC-018 | 给出**审计与可回滚**方案：每次自动决策必须写 timeline（事件名 + 字段契约，**必须含 `answered_by=auto` 之类机器可判的来源**；现状 `answered_by` 是自由文本、`gate-answered` 的 detail 不含它）+ 在面板/`mw doctor` 可见（现状：面板只渲染 pending、doctor 的 autopilot 段零 gate 内容）+ 早上**一次性汇总**（昨夜自动答了哪些门、依据、影响）+ **kill switch 粒度必须"只停自动决策"**（现状只有全局：`enabled=false` 终止整个 conductor、`paused=true` 软停整个 orchestrate ⇒ 需新键，代价 = 两侧镜像 + parity 语料重冻 + `EFFECTIVE_KEYS` 判定）+ **可回滚**（现状 `_consumed_gate_ids` 不可逆、只能手改 `_roadmap.md` 且不留事件；批量回看/按来源过滤**不存在**）⇒ 必须给出替代方案与判据 |
| AC-019 | 给出**无人值守默认动作的显式声明**：每条 gate 必须有声明式的默认动作（自动过 / 停并报告 / 升级给人 / 拒绝），**缺省不得是隐式永久滞留**；并给出"声明缺失"时的机器判定与告警方式（P-014 家族：机器可判、逐字锚定） |
| AC-020 | 自动决策的**实现面与安全属性**：明确它落在 conductor（Python）侧（`file:line`），并证明**不**放开 agent/worker 对 gate 目录的写权限（`xkey-gate-guard.ts` 的封堵保持有效，含验证方式）；给出"自动决策开关关闭后行为与今天一致"的判据（对齐 xkey 机制的 opt-in 范式） |
| AC-021 | 给出**归属语义缺口**的修法面与判据：(a) PM 手工行复用 `ap-` 前缀会同时（i）占用 conductor 的 key 层配额、（ii）让面板计数错位 ⇒ 给出机器可判的归属方案（writer 列 / 前缀命名空间隔离 / 行携带 origin）及两侧一致性；(b) 面板与 conductor 的归属口径必须收敛到同一判据（现状：面板只看前缀 `monitor.ts:509-513`，conductor 是"前缀 **OR** `task_path`" `conductor.py:2135-2138`）。任何方案必须保证既有行仍可读（给出向后兼容的读取判据） |
| AC-022 | 给出**门消费守卫缺陷**的判据与修法面（自动决策的**硬前置**）：D1 `_consumed_gate_ids` 的 `gate-\d{4}` 正则在 `gate-10000+` **静默失效**（FM 已到 `gate-6687`，洪泛速率 585.8 门/h）；D2 `_apply_stalled_rejections` **无消费守卫**（与 approve 路径不对称）；D3 TS `EVENT_TYPES` 缺 `target-config-rejected`（与 `timeline.py:67-84` 漂移）。每条必须给：可复现判据、修法面 `file:line`、**反证**（还原缺陷 ⇒ 对应测试变红）、以及"必须先于自动决策上线"的顺序约束 |
| AC-023 | 给出**自动化输入统计的口径与陷阱**：任何"历史答案分布"必须按**唯一 gate 文件/id** 去重，并显式处理洪泛与重放（RQ-10 实测陷阱：FM 的 **6694 条 `gate-answered` 事件只来自 10 个门**——gate-0002 重放 5588 次 + gate-0003 1098 次，另有 **6684 个归档 pending 洪泛门**；按事件统计会得出"6686/6686"的幻觉）；同时识别"重复 stall"（7/22 是同一 key 的重复）与"人工回填时间戳"（E2 gate-0007 早 4.1h）两类污染。给出复算口径与判据 |
| AC-024 | 给出**影子模式**的门类清单与判据（承接 AC-016 的 0 样本缺口）：`budget-exhausted` / `xkey-authorize` / `goal-halt` / `type-rejected` / `target-config-rejected` 生产样本为 **0**，**reject 路径样本为 0** ⇒ 必须列出哪些门先进影子模式（只记录"若自动会怎么答"，不动作）、影子期的最小样本量与判据（多少夜 / 多少个门 / 什么分布）、以及影子期如何量化"若不自动要等多久"（收益的可验证来源） |
| AC-025 | 给出**逐 gate 类型的处置模式三分判定**（本 key 核心设计输入），并**先解决"命题选层"**：RQ-12 的三分是 **可自举 = `budget-exhausted`（仅命题面，生产 0 样本）/ 部分可自举 = `stage-confirm` / `stage-close` / `stalled` / `xkey-authorize` / 不可自举 = `goal-change`（before-image 在磁盘上不存在：FM goal.md untracked、JC 无 `.git`、无框架快照）**。核心结论：**根因是命题选得不对，而不是字段缺失** —— `stage-close` 的命题主语"全部 key 已终态"**就是 conductor 建门的触发条件本身**（`conductor.py:629-631` vs `:650-656`）⇒ 机器复算**恒真、零信息量**；真正在审的那几个命题（目标是否达成 / 假阴 vs 真缺陷 / 是否越出写面）**全部不在盘上**。因此必须给：每门**重写后的命题**（机器可判且**有信息量**，即"可以为假"）、该命题的证据字段（`file:line` + 字段名）、机器能否**独立复算**、**反例**（证据存在但命题不成立）、以及"命题恒真"的自检判据。判定不得按历史答案分布（RQ-10 口径有陷阱）。**命题两分**：事实性命题（可机器复算 ⇒ case 1）vs **政策性授权**（必须人给，如 `xkey-authorize` / `goal-change`）——现有 xkey 链路已是原型：`xkey-authorize`（人授权，政策）→ `_xkey_run_verify`（机器自证，事实；`conductor.py:3647` 要求 `red_after==0 and not timed_out and rc==0`）→ 放行闭合（`:3885-3891`）。case 1 **只适用于事实性命题** |
| AC-026 | 给出**gate 审核材料的最小信息契约**（供窗口渲染与人审）：RQ-14 已给出 **14 项最小信息集**（F1 身份与时效〔含同 scope 历史已答门〕/ F2 命题 / F3 选项后果与可逆性 / F4 目标一致性 / F5 触发原因类与计数 / F6 证据指针 / F7 证据存在性与新鲜度 / F8 影响面 / F9 弃置代价 / F10 带外修复记录 / F11 边界与下一轮要求 / F12 未达成台账 / F13 默认动作与到期时间 / F14 谁答与预算余量），且**当前可得性 = 3 项机器可读 / 5 项需多文件 join / 6 项仅散文或不存在**——**最影响决策的两项最不可得**（"选项后果与可逆性"只存在于代码常量；"默认动作与到期时间"**根本不存在**）。必须给：字段级呈现契约（三层：面板每门 1 行 ≤110 列 / `/autopilot gates` 门卡片固定 13 行序 / doctor JSON）、每字段长度约束与来源、判据 D1–D7（白名单+来源三元组、逐字子串断言、头部/尾部保留式截断、**禁 LLM 自由生成**、**漂移标记**、`note` 不得作派生输入、数字必须带公式），并以 34 门**回放自检**（RQ-14 覆盖 **31/34**；3 个漏出原子 = 跨 key 写面归属 ×2 + 跨 key 对照实验 ×1）验证"最小"而非凭感觉列字段 |
| AC-027 | 给出**非阻塞延后复核机制**，并**指明它按字面不可实现的部分**：RQ-13 已证 `stalled` / `budget-exhausted` 让 key 保持非终态，而 `_stage_closure` 终态集只认 `("done","closed-legacy")`（`conductor.py:629-631`）⇒ 它们**在 stage 末必然变成硬阻塞**，"延后到阶段目标完成后再复核"**无法按字面实现**。必须给出可行的替代上界（三选一或组合）：(a) **时间上界**、(b) **触发式上界**（stage 内其它 key 全部终态）、(c) **新增"待复核"状态**（对 stage 收口算终态、但标记待审）。对所选路径必须给：延后期间的**补偿控制**、复核材料的**批量形态**、"延后导致问题被发现太晚"的可检测信号，以及数据依据（实测：已收口 stage 墙钟 n=4 / p50 36.56h / max **150.53h**；门→收口视界 n=11 / p50 24.48h / max 145.99h；仍在跑的 stage ≥211h）。**没有任何门可无条件安全延后**（三分：绝不可延后 = `stage-confirm` / `stage-close` / `goal-change`；需补偿 = `stalled` / `budget-exhausted`（最干净候选）/ `xkey-authorize`） |
| AC-028 | 给出**消费记录持久化与 stage 状态单调性**的修法面（硬前置，已有生产实例）：JC 在 2026-09-26T04:37 把 09-11 已答的 `gate-0001` **重放**，stage 1 由 `closed` **退回** `running` 并生成新 stage-close 门；根因 = 消费记录由 timeline 反推且**只留 2 代**（`timeline.py:93-94`）+ `_set_stage_status:380-407` **无单调性检查**。必须给：可复现判据、修法面 `file:line`、**反证**（还原缺陷 ⇒ 测试变红）、"已回答的门永不重放 / stage 状态不可回退（除显式人工操作）"的判据，以及与 D1（`gate-\d{4}`）的关系说明 |
| AC-029 | 给出**取证源优先级与一致性对账**（自举验证的硬前置）：`l3-verdict.txt` 与现行 resolver 复算**有 6/22 个 key 不一致**（FM `gui-shell-spike` 陈旧、FM `gui-contract-mock-tests` 机器假阴、E2 两个 key 被 correction 反转为 `below`）；可复用原语 `l3-verdict-provenance.json`（带 `source_mtime_ns` / `anchor_mtime_ns` / `suspect`）覆盖面 **<5/22**、correction sidecar（带 `original_sha256`）**3/22**。PM 抽验实例：E2 `feature-l3-readcap-injection` 的 `l3-verdict.txt=meets` 与 correction `corrected_value=below` + `counted_as_done=false` 并存，而 roadmap `=done`、stage 已 `closed`。必须给：**证据源优先级表**、一致性规则、不一致时的 **fail-closed** 行为、以及与 roadmap `done` 的对账判据 | **［RQ-14 补：证据新鲜度是系统性问题］**实测 **24/34 门**的证据文件 mtime **晚于应答时刻**（E2 `gate-0010` 的 `l3-a2/output.md` 在应答后 **13 分钟**被改写）⇒ 自举验证必须绑定"应答时的证据快照"（sha256 + mtime），否则复算的是**现在的文件**而非**当时被审的证据**。
| AC-030 | 给出**不可由被审方伪造的审计字段**设计（护栏的地基）：实测 `answered_at` / `answered_by` **应答者可写**（E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s）；`reason` 文本随 conductor 版本有 **3 种格式**（JC `gate-0004` 写 `2/2` 而按现行为应为 `3/3`）⇒ 审计与护栏**不得依赖应答者可写字段**；必须给"机器可判且被审方无法事后篡改"的来源字段（写入点、写者、防伪方式），并与 AC-018 / AC-026 的字段契约交叉一致 |
| AC-031 | 给出**门有效性审计**（防止"门形同虚设"）：(a) 生产上唯一的跨 key 授权实际走散文 `cross-key-repair-request-*.md` + 手写 `decision:` 行，**绕过了 `xkey-authorize` 门**；(b) `roadmap.validate_roadmap` **未被 conductor 调用**，且 **FM Stage 2 / E2 Stage 3 当前实测不合法**。必须给：判据（如何机器检测"绕门"与"未校验"）、修法面、以及"若门被绕过则视为未授权"的 fail-closed 行为 |

## §4 风险与未决项

- 风险 1：**孤儿行占槽**——占槽判定只看非终态行（与 key-status 无关），而"进程已死 + 行仍非终态"最多要等 **90 分钟**孤儿静默窗才释放；stalled 占槽的频率实测 ≈ 0，故按"stalled 占槽"设计会**做错方向**。
- 风险 2：**同文件写冲突随并行度上升**（P-018/P-019 家族：跨 key 冻结判据被覆盖、同文件多写者）；且**同 key 内两张卡的写面是否重叠目前没有机器判定**（待 RQ-5 确认）——这是放开 (d) 的硬前置。
- 风险 3：**rate limit / 凭证配额**——当前**无数据支持**（726 个任务目录对 429/quota 零命中；27/27 失败均为看门狗超时），保留为待验证项而非已证风险；proxy 启用后硬顶是每端口 8 条并发生成流。
- 风险 4：**watchdog 误杀**已是**实测事实**（14 次，并发均值 2.14），不是"高并发才出"的假设。阈值贴着 600s ⇒ 长思考模型/长工具调用会被误杀，是夜跑的主要杀手之一。
- 风险 5：**提 cap 对现有项目是空操作**（FM/E2 的 `config.json` 已材料化 13 键并显式写 2），且机器层覆盖 int 键有语义缺口 ⇒ "看起来改了其实没改"，是本需求最隐蔽的失败模式。
- 风险 6：本 key 要动的 gate/并发语义可能撞更早 key 的冻结判据（P-018/P-019），派卡前必须逐条检查消费点。
- 风险 7：**行提前终态化 ⇒ 重试与旧进程并发写同一批文件**（RQ-5 实测 2 例：重叠 **89.2s / 6.4s**）。这是**现存**双写源（非本 key 引入），而硬互斥判的是**行状态**而非进程存活 ⇒ 放开 per-key 并发前必须先修。
- 风险 8【已更正（RQ-9）】：原写"孤儿回插用的锁与行写锁不是同一把"——**被证伪**（`conductor.py:4032` 用的就是 `.mw/workers.lock` == `mw_common.lock_path`；`conductor-workers.lock` 全仓与全部 git 历史**零命中**，RQ-5 该条为误报）。真正的语义缺口是两个：(a) **前缀归属**（`conductor.py:2136`）让 PM 手工复用 `ap-` 前缀的行**既造成越界、又消耗 conductor 的 key 层配额**；(b) **`_workers.parallel` 无 writer 列**（`worker-store.ts:22-37`）⇒ 行归属只能靠格式取证（时间戳精度/`origin:`/task.md mtime），机器无法直读。
- 风险 9：**无人值守下 gate 无策略 ⇒ key 永久滞留**（RQ-6：无 TTL/超时/自动应答，20/20 全靠人工，等 0.19–17.40h；stalled 占墙钟 46.6%/54.6%）⇒ 这是 (c) 的**主因**，且**与槽位无关**（反向证据：E2 3 个 key 同时 stalled 而 cap=2）。
- 风险 10：**"看起来在跑、什么都没干"**——FM 洪泛 6684 gate / 12h（RQ-6）⇒ 面板有活动但吞吐为零；任何以"面板有 running"为判据的观测都会被它骗过。
- 风险 11：**自动决策引入不可逆误判**——自动 approve 会让一个本该被拦的 key 继续推进到更远的状态（本仓库已有"L3 误判成 below 白烧 2 轮"的同类史实）；自动 reject 走 `closed-legacy` 会**像 done 一样解锁依赖**并放行 stage 收口。⇒ 必须按 AC-016 的三态划界，并对"不可逆动作"额外加确认/延迟窗。
- 风险 12：**护栏本身成为新面**——预算/冷却/配额这类机制若走内存即违反 GC-1；若落盘则新增共享写面（GC-3）。⇒ 护栏必须在 AC-017/AC-018 里给出"每 tick 由文件重推"的形态，并复用既有原语（`round_budget`、`advance_stall_ticks`、`_XKEY_PROPOSAL_MAX_ATTEMPTS`、`_consumed_gate_ids`）而不是自造状态机。
- 风险 13：**`budget-exhausted` 比 stalled 更隐蔽**（RQ-8：静默冻结——不派发、**也不置 `stalled`**，面板只有 `gates: 1 pending`，`key-status` 上看不出异常）⇒ 自动决策的边界与可观测性必须覆盖它，否则夜跑仍会停在一个"看起来没毛病"的 key 上。
- 风险 14：**多类门叠加**（RQ-8 实测：stalled 连带挡住下游 key 与 stage 收口；`goal-change` 一挂即全 roadmap 停；`closed-legacy` 是唯一能让人工 reject 产生的终态，无人值守下不可得）⇒ 自动化只解一类门可能测不到吞吐收益；方案必须按**端到端链路**验证（如 FM Stage 1 的 17.74h 链条：answer → 9s 派发 → 84s 收口 → 145s 后下一 stage）。
- 风险 15：**自动决策一旦误判不可撤销**（`_consumed_gate_ids` 由 append-only timeline 派生；gate 重新 pending 不会重新应用；回滚只能手改 `_roadmap.md` 且不留事件）⇒ 审计与回滚能力必须**先于**自动决策上线；否则误判无法收敛，且 `closed-legacy` 会连带解锁依赖。
- 风险 16：**"只停自动决策"的 kill switch 需要新配置键** ⇒ 触发两侧镜像（Python + TS）+ 跨语言 parity 语料（53 例冻结 sha）重冻 + `EFFECTIVE_KEYS` 机器层判定；若改走机器层还会撞"int/bool 无空值哨兵"的语义缺口（风险 5 / RQ-4 M2）。
- 风险 17：**自动决策的边界证据存在选择偏差**（RQ-11：历史 28 门 100% approve，但"有 100% 一致答案"本身可能因为人在场时才建门）⇒ 直接按历史分布定白名单有风险；建议先做**影子模式**（只记录"若自动会怎么答"，不动作）积累无偏样本。
- 风险 18：**自动化的安全性耦合**（RQ-10）：`stage-close` 是唯一"可自动"的门，但它**只在 `stage-confirm` 不被自动化的前提下安全**（若 `stage-confirm` 也自动过，未经确认的 stage 会被自动收口）⇒ 白名单必须按**组合**验证，不能逐个门独立判定。
- 风险 19：**"答案唯一" ≠ "可自动"**（RQ-10：≥16/22 条 stalled approve 的 note 记录了 approve **之前的带外修复**，**0/22 是裸 y/n**）⇒ 按"历史 100% approve"直接自动化，会在**缺少那次带外修复**时做出错误决策；白名单必须按"决策依据是否机器可判"决定，而不是按答案分布。
- 风险 20：**自举验证可能被"证据存在但结论不成立"绕过**（RQ-10 已实测：dossier verdict 陈旧 C-11、`answered_at` 可人工回填早 4.1h）⇒ 机器复算必须同时校验证据的**新鲜度与绑定**（时间戳、与代码/产物的关联），并为每条判据给反例测试。
- 风险 21：**延后复核会把"阻塞"变成"隐性欠债"**——延后窗口内若有不可逆动作（改代码/删文件/`closed-legacy` 解锁依赖）通过，事后复核无法回滚 ⇒ 必须给"延后窗口内绝不允许发生的动作"白名单，且该白名单要机器可判。
- 风险 22：**护栏缺陷 D1 与 6684 门洪泛事故同源**（`_apply_stalled_approvals` 注释 `conductor.py:2320-2329` 记录了该事故；守卫本身在 `:310` 用 `re.match(r"(gate-\d{4})\b")`）⇒ 同一个守卫既防洪泛又是 D1 的失效点；FM 最大 id 已 `gate-6687`、洪泛 585.8 门/h ⇒ **D1 必须在任何自动决策上线前修完**（AC-022 的顺序约束是硬要求，不是形式要求）。
- 风险 23：**"延后复核"的现实规模很大**：门→stage 收口视界 p50 24.48h / max 145.99h，仍在跑的 stage ≥211h，JC 有 stage-close 门 pending 203.93h（8.5 天）⇒ "阶段末复核"最坏等于延后一两周；且延后窗口内**实测有真实写动作**（E2 gate-0014 挂起 17.40h 期间其它 key 产生 1139 个 tool 事件 / 239 次 write-edit / 49 个目标，其中 80 次落在 `.agenticdoc` **之外**）⇒ 补偿控制不是可选项。
- 风险 24：**真正不可撤销的动作只有两类**：`closed-legacy`（唯一产生点 `conductor.py:2363-2420` → 写入 `_DEP_SATISFIED:56`，而 `_consumed_gate_ids:297` 无撤销）与**源文件写/删**（写面纪律只存在于散文，**机器判定为零**：`worker-mode.ts:756-780` 仅拦 read）⇒ 延后复核的红线必须锁在这两类动作上；现有唯一自带补偿的写路径是 xkey 快照+恢复（`:3515` / `:3460`），但 opt-in 且**生产 0 样本**。
- 风险 25：**自举验证的双向失真**：`l3-verdict.txt` 有 6/22 与复算不一致，其中 FM `gui-contract-mock-tests` 是**文件写 `meets` 而复算 `below`**（机器假阴/假阳都出现过）⇒ 自举判据必须双向测试（防"文件说达标"被当成真达标），且必须以**复算结果**而非**记录值**为准（或明确优先级与对账规则）。
- 风险 26：**命题恒真陷阱**（RQ-12）：若门的命题主语等于建门条件本身（`stage-close` 的"全部 key 已终态" vs `conductor.py:629-631`），机器复算**恒为真、零信息量** ⇒ 自动化会退化成"自动盖章"。任何 case 1 判定都必须先给出"该命题可以为假"的证明与反例。
- 风险 27：**证据在被审之后被改写**（RQ-14 实测 **24/34 门**，E2 `gate-0010` 应答后 13 分钟）⇒ 不做快照绑定的复算/回放会得出"证据支持当时结论"这类无法追溯的判断，等于**可被事后改写的历史**；这与 D4（JC `gate-0008` 重放：`gate-0001` 的 `gate-answered` 事件随 timeline 轮转被剪掉 ⇒ `_consumed_gate_ids` 读不到 ⇒ 已 closed 的 stage 1 被改回 `running`）同属"证据可被时间改写"这一族。
- 待确认：
  - ~~U-2："并行度不够"的具体现象是什么？~~ **已确认（2026-09-26）：`c+d`**。
  - ~~U-4′：优先修 (c) 还是 (d)？~~ **已确认（2026-09-26）：先修 (c)**；并把 (c2) idle 误杀与 `worker_timeout_min` 死键纳入本 key。
  - ~~U-6：(c1) 的 gate 审核材料要做到什么程度？~~ **已确认（2026-09-26）：C**（机器自动过部分 gate），前置条件：先有调研证据（RQ-10 边界 / RQ-11 护栏）与副作用防护机制，见 AC-016..AC-019。
  - ~~U-8：“不可自动化白名单”由谁定？~~ **已确认（2026-09-26，按 PM 建议）：混合制** —— 白名单判据由**证据**定（命题可机器复算**且可以为假**，即有信息量；**不得**用“历史答案一致”，RQ-10 已证该口径有陷阱），同时保留一份 **PM 提案 + 用户一次性确认的不可自动化黑名单**（`goal-change` / `xkey-authorize` / 所有 reject 方向 / `closed-legacy`）。
  - ~~U-9：熔断/配额触发后的动作？~~ **已确认（2026-09-26，按 PM 建议）：B** —— 停止自动决策并把当前门**升级给人**（门回到人工态）+ 早上汇总报告；不采用“静默继续”。
  - ~~U-7：孤儿静默窗（默认 90 分钟）能否缩短？~~ **已确认（2026-09-26，按 PM 建议）：维持 90 分钟** —— worker 墙钟上限 60 分钟，90 分钟留 50% 余量；缩短需先有“死进程 vs 慢进程”的机器判别依据（本 key 不引入）。
  - ~~U-1：目标形态？~~ **已确认（2026-09-26）：A** —— 主交付 = **gate 命题重设计 + 三分处置 + 护栏**；次级 = (c2) idle 误杀/死键 与 (d) per-key 并发；槽位上限 `max_parallel_keys` 只出“不改”的证据化结论。
  - ~~U-3：能否接受成本与失败率上升？~~ **已确认（2026-09-26）：可接受，且实测无代价**（并发 2 vs 1 吞吐 +2%、失败率差异不显著）。
  - ~~U-5：多项目槽位各自计额还是机器层统一计额？~~ **已确认（2026-09-26，按 PM 建议）：各自计额**（现状即如此：每个 conductor 只读本项目的 `_workers.parallel`；统一计额需新建跨项目协调面，收益与改动面均不成立）。
  - ~~case 2 实现路径~~ **已确认（2026-09-26）：(1)** —— 「待复核」状态 + 触发式复核时机 + 时间兜底；**红线 = 待复核的 key 不得进入 `_DEP_SATISFIED`（不解锁依赖）**。
  - **AC 锁定（2026-09-26）**：`AC-001..AC-031` 编号与内容冻结；后续改动一律走 `[REVISED @ date]` **追加式**修订，**不回收编号**。
  - **提交粒度（2026-09-26）**：本 key 起改为**按波次提交**（波内补丁用 `--amend` 合并），替代上一 key 的“每卡一提交”。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- **两层配置机制（刚落地，可直接承载本需求）**：`autopilot/effective_config.py` 的 `load_effective`（项目层 fail-closed + 机器层 fail-soft + 逐字段 origin + 空值即未决定）；CLI `mw autopilot verify set|show|clear` 是现成的"项目侧写入口"范式；机器层键域现在是 2 个，扩域需要走同一套"越域告警"规则。
- **可观测面**：`monitor.ts::deriveAutopilotPanel`（已有 `slotsUsed/slotsMax`、tick 新鲜度、按 key 的 attention 行）、`mw doctor` 的分节渲染（`_doctor_autopilot`）、`autopilot` 的 timeline（append-only，事件类型 17 个）。
- **并发原语**：`mw_common.acquire_lock`（`O_CREAT|O_EXCL`）、`_workers.parallel`/`_index.parallel` 的锁内 RMW 范式。
- **worker 生命周期**：launcher 的 orphan reconcile（`PI_WORKER_ORPHAN_DEAD_MIN`）、活动看门狗 + 墙钟兜底 + 收敛检查点（GC-4）。

### 需规避坑点

- **P-018/P-019**：改共享函数/共享语义前先查消费点与更早 key 的冻结判据；语义变更的下游卡必须当场认领——"并行度"这类全局参数改动会牵动所有 key。
- **P-015**：serve 的可用参数分"落盘（config.json）"与"仅进程 env"两处；**重启路径不同则 env 丢失**。若并行度参数走 env（如 `PI_WORKER_*`），必须显式声明契约并枚举重启路径。
- **P-017**：`npm run check` 全仓 `--write` 在多会话下是破坏性命令；本 key 很可能同时有多个 worker 在跑。
- **P-021**：跨语言镜像的 key，verify 期必须两侧都跑。
- **P-022**：已知残差要记录、且不要把已知分歧值放进语料。
- **已归档记录里的推算值不得当实测引用**（RQ-6 纠正：`mw-done-closure-repair` / `mw-l3-fail-marker-forms` 的 `achieved.md` 里"FM 9 个卡死 key 自愈"是 Stage 2/3 **推算**，FM 实测为 **6 key / 7 gate**）——引用前必须回到原始 timeline 复算。
