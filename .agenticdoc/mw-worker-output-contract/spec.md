# Spec: mw-worker-output-contract

> Key: mw-worker-output-contract
> 创建时间: 2026-10-14
> 状态: draft（待用户审核 → 锁定 AC）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（无 `status:` 行但三段有真内容 ⇒ 视为已确立）

- 对齐：本 spec 服务于 goal「核心交付」中的两条——「agent-team-loop 扩展（PM 模式编排 + Worker 模式执行）」与「文件驱动的去中心化协调」。Worker 交出的三样东西（`output.md` 契约、`evidence/**` 产物、`trace.log` 变更账本）是 PM 判断的全部输入面；该面失真时，PM 会把已完成的工作判为失败、把没写的当写过、把看不清当看清。本 key 修的就是这条输入面的**可信度与机械可判定性**。
- 继承约束（GC 编号）：
  - GC-1：不引入中心化调度器 —— 本 key 只改文件驱动路径内的契约判定、写面通道与账本记录，不新增任何调度/仲裁组件。
  - GC-2：不修改 pi 核心 —— 全部改动落在 `agent-team-loop` 扩展与 mw 后台服务内。
  - GC-3：Worker 进程级隔离 —— 自动补齐契约段等动作必须在 worker 自己的收尾路径内完成，不引入跨进程协调。
  - GC-4：文件锁并发控制 —— 放宽写面后仍须走既有的原子写/锁语义，不新增可写共享文件。
  - GC-5：工具白名单按任务类型（research/review 无 `write`/`edit`）—— 因此修法**不得**给这两类角色增开 `write` 工具，只能放宽角色自有通道 `worker_file` 的**路径域**。
  - GC-6：Worker 超时看门狗三段式 —— 本 key 会改检查点判据，改后不得削弱 activity idle / 墙钟兜底两段。
  - GC-7：goal.md 目标锚点与 mtime 记录 —— 不变。
- 冲突：无。
- 预期收益：判定「worker 交出了什么」的三条链路从「整篇别名子串 + 人工兜底」变为「结构化可机械判定」。判定方式：6 次历史实例语料重放 + 新增单测矩阵 + 至少 1 例端到端；done 时在 `achieved.md` 对照判定。对项目目标的贡献：消除「实质完成却被判 needs-clarification」与「PM 手工补录」这一类固定开销，使并行 worker 的产出可被无人工干预地吸收——这是「一个 PM 管多个 Worker」能规模化的前提。

## §1 功能概述

### 1.1 目标

把 worker 输出面的三个契约（输出段契约、产物写面、变更账本）修成机械可判定、可自查、可自动补齐；顺带修正依赖它们的检查点判据。目标是让「worker 实质完成」与「框架判定为完成」不再需要人来牵线。

### 1.2 技术栈 / 语言

TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/**`，Node strip-only，禁用非 erasable 语法）+ Python（`packages/multi-workers/**`）。测试：vitest（`packages/coding-agent/test/suite/`，faux provider，禁止真实 provider）+ pytest（`packages/multi-workers/test_*.py`）。

### 1.3 核心用户场景

1. PM 派发一个 review/research worker，worker 实质完成并把报告落到 `evidence/**`；PM 回读时应直接看到「产物 + 契约满足」，不需要手工补录。
2. PM 需要知道 worker 到底写了哪些文件（变更历史 / PR 侧声明缺口判定）；账本必须能区分「没写」与「看不清」。
3. worker 在收尾前应能自查契约并补齐缺失段，而不是 settle 之后才由框架判为缺段。
4. writeless 角色（review/research）在收尾窗口不应被误判为发散而中断或重派。

### 1.4 范围说明（不做什么）

- 不改 pi 核心；不引入中央调度器；不改 AgenticTask 的 phase 门禁语义与 `advance_phase` 行为。
- **不**处理 `_framework-reflect.md` 的 FW-003 / FW-004（→ 已有 key `mw-dispatch-reliability`）、FW-006（→ `mw-review-audit-method`）、FW-008（→ `mw-test-runner-hygiene`）。
- 不重写 change-ledger 的整体设计，只修：壳层写目标抽取、`unjudgeable` 语义、消费者对二者的区分。
- 不改工具白名单（GC-5）；不给 research/review 增开 `write`/`edit`。
- 不改 `_pitfalls.md` / `_framework-reflect.md` 的内容（本 key 只在其上追加新实例）。
- **纳入**（用户 2026-10-14 指定）：终态回读推送范围缺口（`notified` 记账早于 owner 门禁，C1/C2/C3）——证据 `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-gap-20261014.md` + 探针 `readback-push-scope-repro-20261014.mts`（均自 `_scratch/evidence/` 字节纯净并入）。它与 P1~P5 同属「PM 吸收 worker 结果的入口面」：前五条错在**内容判定**，本条约错在**投递**。

### 1.5 背景问题（台账条目 + 已复核的实例）

| 编号 | 问题 | 已复核实例与坐标 |
|---|---|---|
| P1 | **输出段契约判定过粗**（FW-001）：判定 = 对**受判产物文本**做别名子串匹配（`checkRecovery`，`worker/output-sections.ts:87`：整篇 `toLowerCase()` + `includes`，**标题完全不参与**），词汇 fail-open、结论 fail-closed，且在 settle **之后**才判 ⇒ 实质完成的审计被判 `needs-clarification`（`exit=2`）。**RQ-1 更正（PM 已读源码复核）**：受判文本**不是** `output.md`，而是 `agentProductText()`（`worker/output-writer.ts:140-145`：**优先 `report.md`**，其次 `output.md`，再退回 settle summary）；判定只有两个调用点（`worker-mode.ts:2740` settle、`output-writer.ts:257-259` writer 默认），`exitCode` 在 `worker-mode.ts:2746`（先前记的 `:2745` 系一行漂移） | 6 次：`wjg-qg-evidence-closure`、`wjg-w12-negative-space-audit`（五段全缺）、`wjg-w15-delta-adversarial`、另一窗口 `mw-write-face-guard` 的 `wfg-rq2-enforcement` / `wfg-rq3-safety`（各缺 2 段）/ `wfg-rq-d2-runtime-guard`（缺 1 段）——**单批 3/5 命中**，且该窗口 PM 独立重造了 byte-pure 补录这一兜底 |
| P2 | **卡片声明的唯一产物路径对角色不可达**（FW-002）：**三层（RQ-2 逐条定位到 `文件:行号`，PM 已读源码复核）**：(i) 角色工具集的唯一决定处 `worker/worker-mode.ts:73-106 TOOL_ALLOWLISTS`（11 键，其中 **5 键无 `write`/`edit`** = review / research / verifier / reviewer / rag-research），`activeToolsForType:145-148` 只为这些角色追加 `worker_file`（表本身是 Python 侧 `autopilot/dispatch.py` 的 parity 锁，见 R7）；(ii) `worker_file` 只认 `progress.md | report.md | report-<slug>.md`（`worker/worker-file-tool.ts:42`）且强制落任务目录；(iii) **派发期就已经判死了**——`pm/ui-bridge.ts:1707-1722 judgeWriteTarget` 的允许面只有「本任务的 taskDir」与「无目录成分的白名单 basename」，**没有 `evidence/**` 面**，而运行期 `worker-mode.ts:1625-1646` 明确允许 `taskDir + <key>/evidence` ⇒ **同一路径在派发期与运行期判定相反**（RQ-2 用语料重放实测：声明写 `<key>/evidence/*.md` 的 review 卡在派发期被判「不可满足」）。壳层是唯一剩下的通道 | `wfg-rq1/rq2/rq3/rq-d2` 用壳层直接写 `evidence/research/*.md`（32–50 KB）；`wfg-rq-d1` 退回任务目录并被 PM 原样提升（两处同 41,612 B / sha `8E4B5A418D99512B`）。**注意**：`worker-mode.ts:723/1604/1624/2199` 表明 `evidence/**` 本就在允许面内 ⇒ 卡住的是**通道**不是策略 |
| P3 | **两套结构并存**（FW-005）：报告结构归卡片自由、`output.md` 归框架硬判，一个满足另一个不满足 | QG 报告满足卡面要求、`output.md` 不满足契约；W-12 的 914 B `output.md` 只有澄清模板四段，37,149 B 实质内容全在报告文件里 |
| P4 | **变更账本双向失真**（FW-009）：壳层目标抽取器会把命令**正文片段**落成 `[WRITE_FILE]`；而经解释器（python/node heredoc）的真实写入可能 0 行 | 误报：`wfg-rq2` 落 `path=` + 反引号 + `:1175`、`…:1184`，`wfg-rq3` 落 `, .agenticdoc/_aut + opilot)`（各 2 行）；漏报：`wfg-rq1` 写了 50,544 B 却 **0** 条 `[WRITE_FILE]`。**新增影响（RQ-2 运行期实测）**：抽取失真会**误拦合法写入**——heredoc 直写 evidence 被 AC-005b 守卫 block（`pattern=redirect target=.md`），worker 只能改用 `worker_file` + `cp` 两步法落盘。**机制（RQ-3 用 dist 抽取器实测，PM 已复核证据）**：抽取器唯一实现 `worker/worker-mode.ts:1554 extractBashWriteCandidates`（41 个 pattern 标签），失真来源 = PowerShell here-string `@'…'@` 打乱引号配对 + `->` 被当重定向 + **非 `verbatim` 目标仍被 `:2383-2385` 无条件记账**；最小复现只需 **13 字符**输入。**遗漏分支**：`[System.IO.File]::WriteAllText` / `AppendAllText` 这类 .NET API 写入在抽取器里**没有分支**（RQ-1 的 122 条 bash 里有 24 条属此类，这是它 0 行 `[WRITE_FILE]` 的第一原因，第二原因是 3 条真写命令被 here-string 正文里的 `--glob` 伪目标**误拦**：`[WRITE_SCOPE_SUMMARY] allow=0 deny=3`）。**`unjudgeable` 现状**：它只是「零事件」派生的布尔，任何乱码事件都能绕开它 |
| P5 | **writeless 角色的检查点判据失真**（FW-007）：**根因（RQ-4 定位，PM 已读源码复核）**：检查点计数只认 `READ_TOOLS = {read,grep,find,ls,glob}` 与 `WRITE_TOOLS = {write,edit}`（`worker/worker-mode.ts:260-262`）——`worker_file` 与 `bash` **都不计入** ⇒ writeless 角色的 `writes=0` / `uniq_targets=0` **恒真**（**入参缺陷，不是规则缺陷**）。`computeRisk`（`:283-286`）三支：`high` = 已过锚点且零写；`mid` = 已过锚点且 phases 停滞，**或** `repeatTop >= 4`；否则 `low`。⇒ 已落盘的审计被判 `risk=mid`（`repeatTop=16`） | `wjg-w12-negative-space-audit`：`[CHECKPOINT] … writes=0 uniq_targets=0 repeat_top=16 risk=mid`，而其 37,149 B 产物已在 `17:32:12` 落盘 |
| P6 | **终态回读推送的范围缺口**：`notified.add(entry.taskKey)` 发生在 owner 门禁**之前** ⇒ 终态行的所属 key 若不等于当前 watch key，该行被永久记账为「已推送」，之后接管/切回该 key 也**不补推**（丢失不可恢复）；另有开窗基线（开窗即终态 = 历史）与无 watch key 静默两个子因 | 合成探针（真实 `startWorkerPollLoop`，`readback-push-scope-repro-20261014.mts`）决定性复现：`b1` 终态于「watch 别的 key」期间 → 接管后 8 tick 仍 0 推送，而同 key 的对照 `b2` 正常推送；本窗口自然实验 **11/11 吻合**（11 个终态只有 7 条回读，4 条丢失全部落在「终态时 owner key ≠ watch key」窗口）。代码锚点 `pm/pm-orchestrator.ts:1349-1357`（基线）与 `:1434-1440`（**顺序即缺陷**：`:1436` 记账早于 `:1440` 门禁） |

后果汇总：每 key 一次人工补录 + 一次人工搬运 + 一次判据人工覆盖；更危险的是 PM 若照机器判据行事，会**重派已完成的工作或中断正在收尾的 worker**（本仓已两次逼近）。

### 1.6 解决方案（策略层，具体改动点留给 design.md）

- **S1 判定改结构**：契约满足 = 存在 `## <契约段名或别名>` 标题。保留词汇 fail-open（标题可用别名），但把「结构」并入契约；整篇正文的别名不再参与满足判定；结论保持 fail-closed（缺标题即缺段）。**作用对象是 `agentProductText()` 的返回值**（优先 `report.md`）——因此「段标题」要求同时适用于报告文件与 `output.md`，而不是只修 `output.md`。
- **S2 前置 + 收尾前自检**：派发/启动时把本角色契约段清单（含可复制的 `## <段名>`）注入 `task.md` 与 worker 上下文；settle 前把结构化缺口（缺失段名列表，或 `ok`）返回给 agent 一次，使其自行补齐，并落一行可解析 trace。
- **S3 机械段自动补齐**：对**受判文本所在的那个文件**补齐 `## 上下文来源`（以及 review 型可机械产出的部分）由框架用已掌握的事实生成——`task.md` 已记录 `card_path`/`card_sha256`，读取清单可由工具事件汇总，产物路径可从写事件取。目标是消灭「只缺机械段」这一类 needs-clarification。**顺序约束（RQ-4）**：判定发生在 `finishSuccess` 内、且在**唯一一次写出之前**（`readTerminalGaps` `worker-mode.ts:2740` → `exitCode` `:2746` → `writeOutputGuarded` `:2761`，注释明写 before the single write-out）⇒ 自动补齐必须插在判定之前：**I2 = `finishSuccess:2713-2720`**；自检反馈回合用既有模式 **I1 = `agent_settled:2811-2822`**。
- **S4 写面按路径域放宽**：让 `worker_file` 接受 `<key>/evidence/**` 下的相对路径（任务目录内仍限 basename 白名单；越界路径 fail-closed 并留 trace），使卡片声明的唯一产物路径成为角色的**第一等**写目标；同时修 `Tool write not found` 的文案，点出替代通道。
- **S5 账本可信化 + 判据对齐**：壳层写目标只在**写入目标位**取值并做形状校验；解释器写入落 `unjudgeable` 事件（不静默丢弃、不乱猜）；消费者区分「没写 / 看不清」；检查点对 writeless 角色改用「最近落盘事件（含 `unjudgeable`）+ 产物存在性 + progress 完成记录」判定，并把「距上次落盘时长」写进检查点行。**两条修法路径择一或组合（design 定）**：(i) 修**入参**——把 `worker_file` 与壳层写入纳入计数（与 S5 的账本事件同源）；(ii) 改**判据**——改用落盘信号而非 `writes`/`uniq_targets`。**硬约束**：`[CHECKPOINT]` 只有时间触发（锚点 `min(30m, max(1s, budget/2))`，之后每 10m 刷新），且改判据**不得触碰** idle（10m）/墙钟（默认 60m）两段的输入（只有 `lastActivityAt` / `budgetMs`）——RQ-4 已确认两段在 `:2591-2624`、`:2650-2654` 与 `risk` 无耦合。
- **S6 推送记账后置 + 补推语义**：`notified` 只在**真正投递成功**时记账（即把记账移到 owner 门禁之后），使「接管/切回 watch key」时该 key 下未推送的终态行能被补推；同时定义与未 ack 状态的去重键，并把「无 watch key 时静默」改为「静默但给出未回读计数」，避免完全无声。

### 1.7 为什么能解决（机理 + 反向对照）

1. **S1+S2+S3 的分工已被 DR2 量化（原表述「3 次唯一缺项是机械段」是旧 fail-open 口径的产物，已更正）**：按新判定（H2 标题档）**6 个历史实例无一例是「唯一缺机械段」**，全部仍 `exit=2`，差别只在「判错文件」被 AC-015 修掉、缺失集合变准。DR2 对 116 例翻转的量化：**S3 单独只救回 6 例**、84 例含机械段、**32 例与机械段完全无关（S3 无效）** ⇒ **S2（收尾前一次反馈）是承载机制**，S3 只是兜底。这正是 FW-001 自身的结论：修法 2「卡面告知」已被 5 次实例证伪，修法 3「settle 前自检/自动插桩」升为必做。S1 另外消掉当前 fail-open 的反向风险：正文偶然出现「证据」二字即算满足。
2. **S3 之所以可行**：机械段的内容本来就在框架手里，不需要 agent 参与即可生成**非空且可核**的来源清单（`card_path` + sha 已在 `task.md`）。这也是它与「让 agent 自己写」在可靠性上的根本差别。
3. **S4 之所以必要且充分**：不可达来自**通道选择**而非写面策略（`evidence/**` 已在允许面内）。因此只需放宽通道 + 用路径域校验保持隔离（必须 `<key>/evidence/` 前缀），既达成目标又不动 GC-5 的工具白名单。
4. **S5 是 S5 自身与前序修法的前提**：FW-007 的既定修法（改用 `[WRITE_FILE]` 判「是否已落盘」）在账本双向失真的现实下会**把乱码当落地、把真落地当零写入**。先修账本再改判据，才不至于用错证据修判据。
5. **反向对照（防自证）**：每条 AC 都要求一个「当前实现必然失败」的用例——仅正文含别名的 `output.md`、写 `evidence/**` 的 `worker_file` 调用、`wfg-rq2/rq3` 的真实命令文本、`wfg-rq1` 的写入形态、已落盘的 writeless 检查点场景。没有反向对照的「修好了」不算证据。
6. **历史语料的实测现实（RQ-1 + PM 独立复现）**：现存语料里「有受判产物」的 worker = **433** 份（PM 实测；RQ-1 口径 425/423，差异来自对 `manual-*`/`_scratch` 的取舍），当前整篇别名判定通过 **145/433 = 33.5%**（RQ-1：142/423 = 33.6%），而只认标题别名通过 **35/433 = 8.1%**（RQ-1：29/423 = 6.9%），**110 例（RQ-1：113）**属 `alias_ok → heading_fail`。⇒ 两条硬结论：(a) **S1 单独上线会大幅压低历史语料通过率**，所以 S1 必须与 S3（机械段自动补齐）同批交付，且**不得以历史语料通过率当判据**（这批产物生产于「契约不要求标题」的年代，用它评判新契约等于用旧规则的数据否定新规则）；(b) 反过来看，**宽档判据的存在理由本身站不住**——见第 7 条。
7. **一处误引：宽档判据是被跨契约的数字支撑的**：`output-sections.ts:19-20` 的注释写「历史语料是严格标题档会误伤的实测证据（99.4% / 87.2%）」，但 RQ-1 逐条核对（PM 已 `grep` 复核）表明这两个数字属于 **`mw-dispatch-card-gate` 的派发卡信封**：`99.4%` = 派发输入 **341/343 不合规**（`evidence/research/spec-dispatch-input-format-20261012.md:142`），`87.2%` = 卡片 **301/345 不合规**（`spec-card-format-corpus-20261012.md:281`），原出处 `shared/dispatch-card.ts:19-20`；`_framework-reflect.md` FW-001 的修法 5 又转引了一次。**即：本契约的宽档从来不是被本契约的语料实测支撑的**（那批卡片统计测的是「三段标题是否合规」，不是恢复契约的段）。AC-014 要求更正这两处。
8. **S6 的机理与可证伪判据**：缺陷是**两条相邻语句的语义错位**（记账的语义是「已投递」，而门禁 `continue` 表示「不投递」），所以修法是顺序澄清而非新机制；报告已给出可证伪预测——把记账后置后，探针 `P3` 应从 `saw b1=false` 变为 `true`（接管后补推一次），而 `P1/P2/P4/P5/P6` 结果不变；**若 `P3` 不变，则 C1 不是主因**，须转向 C2/C3 或 `triggerTurn` 合并路径。这条反证条件是本 key 验收该条目的闸门（AC-011）。

## §2 业务约束

### 2.1 平台 / 环境

Windows + PowerShell 5.1（`&&` 不可用；git-bash 在 `D:\Program Files\Git\bin\bash.exe`）；TS 只允许 erasable 语法（Node strip-only）；Python 3.14。禁止全量 `./test.sh`（无墙钟超时，实测 7h14m 挂死，见 `_pitfalls.md` P-032）——用包级定向套件对照。

### 2.2 性能指标

settle 契约判定为 `O(契约段数 × 标题行数)`，不新增轮询与后台线程；前置清单注入不新增超过每段 1 行的提示预算；检查点判据改动不得增加 trace 行数。

### 2.3 安全约束

写面放宽**只到** `<key>/evidence/`：其他 key 路径、仓库源码路径、`_index*`、`pm-state.md`、`_workers*` 必须 fail-closed 且留 trace 行；既有原子写/锁语义不变（GC-4）；不引入新的可写共享文件。

### 2.4 集成依赖

`worker/output-sections.ts`（契约段与别名表）、`worker/worker-mode.ts`（settle 判定、检查点、trace 事件、壳层写面）、`worker/worker-file-tool.ts`（角色自有写通道）、`shared/change-ledger.ts`（`[WRITE_FILE]` 事件与消费者）、`worker/output-writer.ts`（`agentProductText` / `readTerminalGaps` / 澄清模板生成 / `write_scope` 记录）、`shared/deliverable-evidence.ts`（`hasDeliverableEvidence`）、`shared/heartbeat.ts`（检查点行字段）、`shared/read-scope.ts`（派发期复用的路径谓词）、`packages/agent/src/agent-loop.ts`（pi 核心，**只读**，`Tool write not found` 文本来源）、`packages/multi-workers/autopilot/dispatch.py`（工具集 parity 锁）。**消费者面（RQ-3 已清点）**：账本消费者共 6 处、**全在 TS**（`parseWriteFileEvents → diffLedger → readTerminalGaps → writeOutput/settle → PM readTerminalDetail`），**Python / `mw doctor` 不消费** ⇒ 本次修复不涉及 Python 侧账本逻辑；相关测试 12 个 vitest 文件，pytest 侧无用例、`pm/ui-bridge.ts`（卡面/派发模板）、`pm/pm-orchestrator.ts`（`startWorkerPollLoop` 的投递/抑制面、`notified` 生命周期）、`shared/ack-store.ts`（`.agenticdoc/_workers.acked`，持久化 `taskKey | ackedAtIso`）、`shared/worker-store.ts`（`WorkerEntry` 无 run 字段 ⇒ 补推去重键受此限制）、`test/extensions/agent-team-loop.test.ts`（既有断言 `:2077` 是 C3 的回归锁）、历史语料与统计入口（由 design 阶段调研定位）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-10-14（**用户已确认锁定**：AC-001..AC-017），编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 worker 提交 `output.md` 时，契约满足判定仅依据 `## <契约段名或别名>` 标题的存在性；在 8 例单测矩阵（全 5 段标题 / 缺 1 / 缺 2 / 缺 5 / 仅正文含别名而无标题 / 标题用别名 / 标题重复 / 标题在引用块内）下判定结果与期望表逐例一致，其中「仅正文含别名而无标题」判为缺失 |
| AC-002 | 在缺任一契约段标题时，settle 的回读文本包含**全部**缺失段的准确名称（不出现与事实不符的段名），且 `exit=2` 的例数等于期望表中的例数 |
| AC-003 | 在 worker 启动前，`task.md` 含本角色契约段清单（每段给出可复制的 `## <段名>`）；在 ≥2 个真实任务（research / review 各 1）的 `task.md` 中可见，命中 2/2 |
| AC-004 | 在 settle 前，worker 收到一次结构化缺口（缺失段名列表或 `ok`）并在 `trace.log` 落一行可解析记录；对「首轮缺 1 段、补齐后再 settle」的模拟用例，最终 `exit=0` |
| AC-005 | 当**受判产物文本**缺 `上下文来源` 且任务事实齐备（`task.md` 含 `card_path`/`card_sha256`）时，框架在**判定之前**（I2 = `finishSuccess:2713-2720`，早于 `readTerminalGaps` `:2740`）自动插入该段，内容含 card 路径与至少 1 条产物或读取来源；对 3 个历史实例的**补录前前缀**重放，判定由 `exit=2` 变为 `exit=0`（3/3）；且自动插入的内容必须出现在最终落盘的受判文件里（判定与产物一致，不允许只对内存文本判定）。**判据校正（2026-10-14，设计阶段，DR2 实测；编号不回收）**：原「3 个历史实例的补录前前缀」有歧义且不可满足——按 R-b（PM 补录前）口径「唯一缺机械段」的实例为 **0**，按 R-a（框架机械补录前）口径**字面**「`card_path`+`card_sha256` 齐备」的只有 **1 例**（`mdc-rq1`）。校正为：**事实前提放宽为「≥1 类事实」（`card_path` / `card_sha256` / 读取清单 / 产物路径任一）**，重放池取 R-a 口径 3 例且仍要求 `exit=2 → 0`（3/3）；**重放池已由 DR6 落到盘上并被 PM 逐例复核**：`evidence/recovery-contract-flip-disposition-20261014.txt` 的 `class=mechanical-only` **8 例**——`mdc-rq1-dispatch-chain`、`mwgf-drq2-target-axis-design`、`mwgf-drq3-role-key-design`、`mwgf-qga3-final-adversarial`、`mw-rag-t11-verify`、`mw-rag-t14-phase-axis`、`mwtp-final-fixes-3`、`mvr-rq5-awareness-surface`；8 例**均无任何标题承载 `上下文来源` 别名**（别名只出现在正文：`读取` / `sources` / `references`），且从未被 PM 补录 ⇒ **盘上现存文本即重放输入**，取其中 3 例即可，无需构造用例 |
| AC-006 | 在 review/research worker 调用 `worker_file` 写 `<key>/evidence/**` 下的路径时成功落盘（含 `evidence/research/*.md` 子目录）；写越界路径（`../..`、其他 key、仓库源码）时 fail-closed 且留 trace；任务目录内 basename 白名单的既有用例 3/3 仍通过。**开放项须由 design 定**（RQ-2 A2/A15）：`<key>` 相对 project-root 还是相对 key 目录；`write_scope:` 是否同时约束 `worker_file` |
| AC-007 | **先钉死「文案」层级**（RQ-2 §6.4 三候选）：可改面 = `worker/worker-file-tool.ts:91-95/:96-100/:105`（工具侧提示）、卡面/派发模板、工具描述；**不可改面** = pi 核心 `packages/agent/src/agent-loop.ts:611` 生成的 `Tool write not found` 文本（扩展的 `tool_result` 钩子不覆盖 `kind:“immediate”` 分支）⇒ 验收改为二者之一：(a) 该错误**不再产生**（worker 直接走 `worker_file`/壳层）；(b) 收到错误后同一回合内能改用正确通道。对 3 例（`wfg-rq-d1/rq2/rq3` 形态）验证 `worker_file` 调用成功 3/3；文案命中 3/3 仅在层级落在扩展可改面时要求 |
| AC-008 | 以 `wfg-rq2-enforcement` / `wfg-rq3-safety` 的真实命令文本作夹具时，壳层写目标抽取产出 **0** 条伪 `[WRITE_FILE]`；以 `wfg-rq1-write-face-sources` 的写入形态（python heredoc 写 `evidence/**`）产 0 条伪路径且**至少 1** 条 `unjudgeable` 记录（不再静默 0 行） |
| AC-009 | 在 writeless 角色「产物已落盘且 `progress.md` 有完成记录」场景下，检查点判 `risk≠mid`（`wjg-w12` 形态：`[WRITE_FILE]`=4、`worker_file` 调用 4 次、37,149 B 产物已落盘）；在「无任何落盘事件且无完成记录」场景下判 `risk=mid` 及以上；两场景各 1 例输出符合。**根因须同时处理**：`worker_file`/`bash` 不进 `writes`（入参缺陷）——修入参或改判据二者至少一处，且必须验证 idle/墙钟两段行为不变（3 例：正常活跃、真挂死、预算尾段） |
| AC-010 | **前提已被 RQ-1 推翻，本 AC 重写**：本仓**不存在** `output.md` 恢复契约的历史语料统计（`99.4%`/`87.2%` 属 `mw-dispatch-card-gate`，出处见 §1.7 第 7 条）。改为三条：(a) 以 RQ-1 口径的语料为对照，改动前后各统计「整篇别名通过率」与「标题别名通过率」，PM 已独立复现为 **145/433 = 33.5%** 与 **35/433 = 8.1%**（110 例 `alias_ok→heading_fail`），两数与命令须落 `evidence/`；(b) **不设 ≤2pp 硬闸**，改为「新产物全通过」：本 key 交付后新跑的 worker（≥6 个，覆盖 research/review/coding）其受判产物在「标题判定 + 机械段自动补齐」组合下**全部** `exit=0`；(c) 上述 110 例的处置**逐条**给出（被自动补齐救回 / 仍失败及原因），不得只报总数 |
| AC-017 | **抽取器失真既不得造假账，也不得误拦**（P4 的可验证判据）：(a) RQ-3 的最小复现输入（13 / 55 / 319 / 336 字符 here-string 形态）经抽取器产出 **0** 行 `[WRITE_FILE]`；(b) `[System.IO.File]::WriteAllText` 与 `::AppendAllText` 各调用一次产出**恰好 1** 行事件（新增分支）；(c) 含 `--glob`/`->`/反引号的 here-string 正文不再把真写命令判 deny —— 对应 `[WRITE_SCOPE_SUMMARY]` 由 `allow=0 deny=3` 变为 `allow=2 deny=0`（**判据校正 2026-10-14（设计阶段，DR3 实测；编号不回收）**：原写 `allow=3`，实测被拦 3 条中第 3 条为 `Write-Output a <term> --glob x`（`trace.log:352`，54 字符、**无写 API**），修后产 0 候选故不计数 ⇒ 正确断言是 `allow=2 deny=0` 且该命令产 0 候选）；(d) `unjudgeable` 改为由「**有效**事件数为零」派生（乱码事件不再能绕开它），并保留现有 12 个 vitest 用例名下的断言不回归 |
| AC-016 | **派发期与运行期的写面必须同源**：`pm/ui-bridge.ts judgeWriteTarget` 的允许面必须与本 key 交付后的运行期写面一致（至少包含 `taskDir + <key>/evidence/**`），不得再出现「运行期允许、派发期判不可满足」；验收：1 例 research + 1 例 review 卡在 `## 唯一证据文件`/写入面声明 `evidence/**` 时派发期判定为可满足（当前 review 形态实测失败），且两处判定共用同一常量/谓词（不得各写一份正则）；越界面仍 fail-closed（`../..`、其他 key、仓库源码 3/3 拒绝） |
| AC-015 | **受判产物候选集合与 `worker_file` 白名单必须对齐**：白名单允许写 `report-<slug>.md`（`worker/worker-file-tool.ts:42`），但 `agentProductText`（`worker/output-writer.ts:140-147`）只依次读 `report.md` → `output.md` → settle 回复，**从不读 `report-<slug>.md`** ⇒ 只写 `report-<slug>.md` 的角色会被按「空/模板 output.md」判定（本仓 `wjg-qg-evidence-closure` 即此形态）。二者取一并有测试：要么把 `report-<slug>.md` 纳入受判候选（按 mtime 最新或明确定义优先级），要么从 `worker_file` 白名单移除该名并给出替代；现有 `report.md`/`output.md` 优先级的 3 个用例不得回归。**设计结论（DR2，2026-10-14）**：取「纳入候选集」，顺序 `report.md` → `report-<slug>.md`（同层多文件按 mtime 降序）→ `output.md`；四条硬证据 `findNonEmptyReport`（`shared/deliverable-evidence.ts:105`）、`judgeWriteTarget`（`pm/ui-bridge.ts:1715`）、`writesLabel`（`worker/worker-mode.ts:2695`）、以及 `WORKER_FILE_NAME_RE` 已把 `report-<slug>.md` 当一等产物名。**必须同批改第二个入口**：`worker/worker-mode.ts:2734-2738` 的 `reportProduct` 谓词只 `statSync(report.md)` ⇒ 不改则「只写 slug 文件」的 write 角色**根本不被判**。语料影响：33 个 target 携带 slug 文件、**13 个受判文件发生变化**（含 QG / W-12 / W-15） |
| AC-014 | 更正「用另一契约的数字证明本契约宽档」这一误引：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:19-20` 的注释与 `_framework-reflect.md` FW-001 的修法 5 必须改为引用真实出处（`mw-dispatch-card-gate` 的派发输入 / 卡片统计，含 `file:line`），或改述为「宽档的真实理由 = 旧契约不要求标题、历史产物不可作为判据」；两处逐字核对 |
| AC-011 | 当一条终态行的 owner key ≠ 当前 watch key 时，该行**不被**记账为已推送。以 `readback-push-scope-repro-20261014.mts` 的场景转为仓库用例后逐条判定：(a) `P3` 由「接管后 0 推送」变为「接管后补推**恰好 1 次**」——若 `P3` 仍为 0，本条不通过（C1 不是主因，需重新定位）；(b) `P1/P2/P5/P6` 断言不变；(c) **`P4` 的断言必须先改写**：其现值 `step4 === 1 && had("b2")`（探针 `:150`）在修复后必然因 `step3` 也投递而变 2 ⇒ 改为「`had("b2")`」或相对式 `step4 === step3 + 1`（这是探针自身的断言债，不是行为回归）；(d) 既有测试 `packages/coding-agent/test/extensions/agent-team-loop.test.ts:2053-2085`（断言 `:2077`「无 watch key 期间终态行不得复活」）必须保持通过 ⇒ 修法必须把 **C3（`!watch.key`：继续记账并静默）与 C1（owner 不匹配：不记账）分开**，禁止把 `notified.add` 朴素后移到整条门禁之后 |
| AC-012 | 对「开窗即终态」的行，二选一必须有机械判据并落测试：要么在对应 key 被 watch 且该行未 ack 时补一次回读，要么保持不回读但在 widget 未处理区给出计数；判定标准写死在用例里，且模块级注释说明 `notified` 与 `ackStore` 的语义分工 |
| AC-013 | 在无 watch key 的窗口里，若存在「终态且未推送且未 ack」的行，则界面或消息中出现未回读条数 N（N>0 时出现、N=0 时不出现）；窗口保持不跨 key 广播这一点不变 |

## §4 风险与未决项

- 风险 R1（RQ-1 已结）：原本担心的「既有语料统计」**不存在**（99.4%/87.2% 属另一契约，见 §1.7 第 7 条），AC-010 已按实测重写。**新暴露的真风险**：历史语料标题通过率只有 8.1%，若把「历史语料不得回退」写成判据，会与 S1 直接冲突 ⇒ 本条风险以「新产物全通过」（AC-010 b）替代，历史数字只作背景记录。此风险与 §1.7 第 6 条同源，design 阶段必须在 tasks 里明确「不拿旧产物当验收对象」。
- 风险 R2：S2/S3 可能把**真实**未决项掩盖成机械段 ⇒ 自动补齐只允许补机械段，`## Questions` 与实质判断段一律不自动生成（在 design 里写成不可越界的白名单）。
- 风险 R3：S4 放宽后 worker 可能把临时文件写进 `evidence/` ⇒ 需保留「`evidence/` 只放产物」的约定（文档 + 可选的 doctor 检查）。
- 风险 R4：S5 的形状校验过严会误判合法路径（含空格、`+`、中文的目录名）⇒ 必须以仓库现有真实路径集合做反向对照，无法判定时退回 `unjudgeable` 而不是拒绝。
- 风险 R5（RQ-5 已核）：记账后置后，长期无人 watch 的跨 key 终态行会**每次轮询重新进入判定**（不投递，Set 不再增长）。I/O 面已确认为安全：门禁 `:1440` 之前只有内存/纯计算，`recordWriteScopeResidualRisks`（读 `trace.log`）在 `:1448`、`heartbeatStatsSuffix` `:1456`、`readOutputBody` `:1457`、`readSpawnFailure` `:1465` **全在门禁之后**，稳态增量仅为每 tick 每行的 Set miss + 一次 `path.relative`。**但**：`notified` 同时承担「`recordWriteScopeResidualRisks` 每任务只记一次」的界（代码注释明写 `notified above bounds it`）⇒ C3 分支（`!watch.key`）必须**继续记账**，切勿整体后移，否则该残留风险记录会被每 tick 重放。
- 风险 R9（RQ-3）：**不能只靠「形状合法」做加固**。全仓磁盘文件名含空格/`+`/中文/`@`/`~` 的 = 0（walk 7,921 项），但 `.agenticdoc` 正文里反斜杠盘符路径出现在 382/1,720 行（`WENBOZ~1` 87 行、`Program Files` 12 行等）——现有 whitelist 会把它们判 `malformed`。⇒ 加固必须是「**正信号**（来自写动词的已解析目标）+ 形状校验」的组合，不能只做形状收窄，否则会把正文里的合法路径引用一起判死（并可能重新引入误拦）。
- 风险 R7（RQ-2）：`TOOL_ALLOWLISTS` 与 Python 侧 `autopilot/dispatch.py` 的 REGISTRY **逐项 parity 锁**（连 entry order 都锁，T-17 L0 测试）⇒ S4 只能「加通道 / 加写面」，**不得改工具集表**；`WORKER_FILE_NAME_RE` 被 `worker-file-tool.ts` 与 `ui-bridge.ts` 两处共用，放宽它必须同批考虑派发期判定。
- 风险 R8（RQ-2 基线）：4 组相关测试在 HEAD 已有既存红 —— `worker-file-tool` 7/9、`mwds-t02` 38/39（各 2/1 例 HEAD 既存，`git diff --quiet HEAD` = 0），`change-ledger` + checkpoint 22/22、`mwds-t03` 63/63 全绿 ⇒ 实现期的「不回归」以这组数字为基线，不得把 HEAD 既存红算作本次引入。**RQ-1 的「0 个既有用例翻转」只在谓词层成立**（DR2 更正）：settle 层**至少 3 处必须改**——`test/suite/dispatch-recovery-terminal.test.ts`（单 settle 后变 `exit=0`）、`test/suite/output-recovery-contract.test.ts`（单次 settle 不再落终态；writer 直调路径视 D5 决议）⇒ 这 3 处要作为「**预期内**改动」显式登记，不能混进「回归失败」。另：测量期间有并行 worker 写入，受判 target 由 433 漂到 **437**（统计口径须固定到某一时刻并记录）。**DR6 实跑基线（24 个 vitest 文件 / 558 用例，2026-10-14）**：既存红 **5 个**（比卡面多 3 类）——`agent-team-loop-worker-file-tool.test.ts:177/:285`、`agent-team-loop.test.ts:6381`（他 key 锚点）、`mwds-t02-write-intent.test.ts:345`（P2 现场）、`mwds-t23-cutover-recheck.test.ts:295`（bundle sha）；全绿基线——change-ledger + checkpoint 22/22、`mwds-t03` 63/63、`t04+t05+t06+t12` 50/50、output-recovery + dispatch-terminal 30/30、`agent-team-loop` 196/197、ledger 家族 105/106、pytest reap 15/15。语料快照 **n=437**（类型分布 coding 278 / research 128 / review 30 / vision 1）：整篇别名 **152/437 = 34.8%**、H2 标题 **37/437 = 8.5%**（H2/H3 41/437 = 9.4%）、**flip 111**，其中 **`mechanical-only` 8 例 / `substantive` 103 例**（这组分类就是 AC-005 的重放池与「S3 vs S2 分工」的实测依据）；标题档缺失频次：`上下文来源` 362/437、`残留与未验证` 311/437、`证据` 124/437、`结论` 86/437。可复跑脚本落在 `evidence/scripts/recovery-contract-corpus-stats.py` 与 `evidence/scripts/new-worker-exit-scan.py`。
- 风险 R6：`notified` 是窗口进程级 Set、`ackStore` 是持久化的已处理标记，二者语义不等价 ⇒ 补推去重键（`taskKey` 还是 `taskKey + run_id`）必须先定，否则会重复推送或漏推；多窗口同时 watch 同一 key 的行为**未实测**（报告 §6 已声明）。
- 待确认：是否把 FW-003 / FW-004 / FW-006 / FW-008 并入本 key（当前按 `_framework-reflect.md` 的派发建议分流到 `mw-dispatch-reliability` / `mw-review-audit-method` / `mw-test-runner-hygiene`）。
- 已决（2026-10-14，用户指定）：回读推送范围缺口（P6）纳入本 key；其证据与探针已从 `_scratch/evidence/` 字节纯净并入 `evidence/`。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产（点名 `_arch_snapshot.md` 清单）

- `advance_phase / audit_phase 门禁脚本`（`.agents/skills/agentic-task/scripts`）：本 key 的相位推进与证据校验走同一套，AC 的机械验收沿用「脚本 + 测试」模式。
- `watchdog / 树杀 / 孤儿 reconcile`（`mw_common` / `worker-mode.ts`）：S5 改检查点判据时必须与三段式超时共存，不另起机制。
- `partition profile v2 + golden parity`（`mw_common` / fixtures）：若改动命中注入块内容（契约段清单进 `task.md`），需照该模式做逐字节 golden 基线。
- `hermetic serve 测试模式`（`test_serve_doctor.py` TestServeSupervision）：假 Popen 兜底思路可复用于 settle 路径的单测。
- `_framework-reflect.md` FW-001…FW-009 本身：问题清单 + 精确坐标 + 修法建议，直接作为本 key 的需求侧证据（无需重新发现）。

### 需规避坑点（点名 `_pitfalls.md`）

- P-001（PowerShell 5.1 UTF-8 管道损坏 / 内联 `python -c` 破坏 CJK）：所有 `.agenticdoc` 编辑用 Python 脚本 + `encoding="utf-8"`。
- P-026（派发卡两道静默门槛：type 专属项须在 `## ` 标题体内、seed 须含字面 `name.ext:NNN`）：本 key 自己派卡时必须遵守。
- P-028（伪 `failed` 风暴）：回读里 ≥2 个 `exited without writing output` 块按噪声处理，一律以 `run.json` 为准，不据此重试。
- P-030（`git grep` 不搜未跟踪文件）：调研负空间时必须带 `--untracked`。
- P-031（`.agenticdoc` 精确匹配失败两次）：改文档优先「EOF 追加」而非 `rindex` 长 CJK 行，且编辑脚本全或无（逐条断言命中数）。
- P-032（全量 `./test.sh` 无超时挂死）：验收一律用包级定向套件。
