# Spec: 守卫形态加固（mw-guard-form-hardening）

- Key: `mw-guard-form-hardening`｜阶段: SPEC｜日期: 2026-10-11｜基线 commit: `ab546bb64`
- 上游：`mw-dispatch-settle-gates`（DONE）遗留账本 R3–R11；独立对抗质量门 QG-B（`evidence/quality-gate-code-adversarial-20261011.md`，30,179 B）
- 本文状态：**初稿**（5 个 spec 阶段 RQ 回收后由 PM 修订；AC 编号一经锁定不回收）

## §0 Goal Alignment

**goal.md 锚点**：本项目要在 pi 之上支撑「一个 PM + 多 Worker 并行开发」，其**安全性不靠进程沙箱，而靠文件驱动协调 + 权限守卫**
（goal.md：*不引入中心化调度器*、*凭证隔离*、*工具白名单按任务类型*、*文件锁并发控制*、*goal.md 目标对齐*）。
因此守卫本身的可判定性 = 框架的地基：守卫**形态假设**一旦可被绕过（漏放）或误触发（误拦），
轻则损坏他人命名空间（跨 key 写坏别人的 `pm-state.md`/`_workers.parallel`），重则让并行开发不可信。

**本 key 与 goal 的对齐点**：
- 「工具白名单按任务类型」⇒ 角色判定必须来自**单一事实源**，且其输入（任务书）不得自我翻转判定（AC-005）。
- 「文件驱动协调 + 文件锁」⇒ 跨 key 写面必须**fail-closed**（AC-003/AC-004/AC-006）。
- 「Worker 进程级隔离、崩溃不影响其他 Worker」⇒ worker 侧的写面守卫必须**fail-open**，否则守卫自己成为新的故障源（AC-001/AC-002）。
- 「Worker 执行过程中追踪 goal 一致性」⇒ 每个「放行/拒绝」决策必须可事后度量（AC-007/AC-011）。

**预期收益**（可量化，作为 done 时的判据）：
1. 写面守卫误拦 = **0**（前值 1：A2 的 `$T` 形态），且形态覆盖率从不完全变为**全枚举并逐条给判定**（AC-001/AC-002）。
2. 跨 key 守卫漏放 = **0**（前值 5/5 已复现样例漏放 + 1 条目录盲判），且真实语料假阳性不恶化（仍为 0）（AC-003/AC-004）。
3. 角色判据从「可被被审文本翻转」变为**不可翻转并单源**（AC-005）。
4. QG-B 的 14 条未覆盖分支 + 2 条空洞断言全部消除，使「守卫有测试」不再只是行覆盖口径（AC-008/AC-009）。
5. 架构冗余消除（无消费端的契约删除或补真消费端），文档计数与实现一致（AC-010）。

## §1 问题陈述

三类守卫已存在但**判定依据建立在「声明的形态」上**，导致两侧都出问题（PM 已在 HEAD `ab546bb64` 上读源码逐条复现，基线坐标见 `pm-state.md` §6；下表坐标已由 T-17/B-1 对最终工作树重锚）：

| # | 缺口 | 性质 | 坐标（最终工作树） |
|---|---|---|---|
| A1 | 包装器集合缺 `bash/sh/zsh/cmd/powershell/perl/ruby`；重定向算子只认 `>`/`>>`；内联脚本只扫 python/node | 漏放 | `worker/worker-mode.ts:834`（wrapper 集）/`worker/worker-mode.ts:1182`（redirect 算子）/`worker/worker-mode.ts:1303`（内联脚本分支） |
| A2 | 变量/命令替换重定向被**误拦**（`$T/report.md`） | **误拦（方向违约）** | `worker/worker-mode.ts:1571`（`checkBashWriteScopeTarget` 的 `verbatim` 门） |
| A3 | 目标发现依赖扩展名白名单 ⇒ `config.toml`/`Makefile`/`.env`/`*.rs`/`*.html` 命中 0 | 漏放（fail-open） | `pm/ui-bridge.ts:1432`（`WRITE_INTENT_TOKEN_RE` 形状发现） |
| A4 | 白名单先判 basename 再判目录 ⇒ `../other-key/workers/x/output.md` 通过 | 漏放（目录盲判） | `pm/ui-bridge.ts:1645`（`judgeWriteTarget` 先目录后 basename） |
| A5 | `_`/`.` 前缀无条件豁免跨 key 守卫 | 漏放 | `pm/ui-bridge.ts:277`（`foreignLiveClaimRefusal` 显式名门） |
| A8 | `parseTaskMd` 全文扫描 + `type:` last-wins ⇒ 正文一行可翻转角色 | **守卫自我失效** | `worker/worker-mode.ts:336`（`parseTaskMd` 改走共享头区） |
| C2 | `WRITE_SURFACE_MARKER` 无消费端（幂等实由正则提供） | 架构冗余 | `pm/ui-bridge.ts:1340-1341`（契约常量）/ `pm/ui-bridge.ts:1745`（`applyWriteSurfaceContract`） |
| C7 | `DELIVERABLE_PLACEHOLDERS` 16 个 vs 头部/plan 说 15 | 文档不一致 | `shared/deliverable-evidence.ts:63` / `shared/deliverable-evidence.ts:85` |

### §1.2 RQ 补充证据（spec 阶段研究结论，均含 `文件:行号`）

| RQ | 结论 | 载荷数值 | 归档 |
|---|---|---|---|
| RQ-1 | 写入形态实测：覆盖 35 / 缺失 33 / 部分 3，另有 **8 条误拦**；**PM 自测另有 5 类形态提取到 0 候选（完全隐形）** | `forms_total=79`、`covered=35`、`missing=33`、`FP=8`；隐形 = `bash -c`/`sh -c`/`powershell -Command`/`perl -e`/`>\|` | `spec-form-inventory-20261011.md` |
| RQ-2 | 方向契约 = `verbatim` 三档；现状 **19 条 must-allow 中误拦 16**、14 条 must-block **零漏放**；契约代价 **F1–F3**（现状拦 → 契约后 `allow-unknown`） | `false_positives=16`、`must_block_currently_allowed=0`、`cost=3`（PM 独立复跑 0 处不符） | `spec-direction-contract-20261011.md` |
| RQ-4 | 正文 `type:` **真实翻转 1 例**（spec 原预期「空集」被证伪）；`type:` 解析器全仓 **6 份且语义分歧**；派发期判据**不复用** worker 解析 | `task_md_total=305`、`body_type=4`、`flip=1`（PM 复现）；唯一文件 `mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md` | `spec-taskmd-corpus-20261011.md` |
| RQ-5 | **A5/A6 成立但潜伏**（路径真实、语料 0 例）；**A7 成立且当前即满足前置**（`_index.md` 回退不经 claim 检查）；A9 只在交付判据层；A11 原版成立/重述版不成立 | `_index.parallel` 54 行、前缀 key 0、大小写重名 0 | `spec-key-identity-20261011.md` |
| RQ-3 | A3/A4 两处漏放实测确认（现实现 5 样例 **0/5** 命中；`.agenticdoc/_index.parallel`、`.git/config` **也 0 命中**）；新目标集轴（允许面 + 路径**形状**判定）在 26 本 writeless 真语料上 `hits 2→13` 而 `violations/FP` 零变化；**裸 token 一律 fail-closed 不可接受**（引入 9/26 = 35% 假阳性） | `hits=0/5`、`hits 2→13`、`FP=0`、`bare_token_fp=9/26`（PM 用**已安装 bundle** 实测 0/5） | `spec-path-resolution-20261011.md` |

**RQ 横向发现（形态误报，与 AC-002 的 FP 族同源）**：here-string 的单引号去同步使 `2 > gapLen` 被当作重定向（`[rule=scope]`，`worker/worker-mode.ts:756` / `worker/worker-mode.ts:1182`），而 `2>$null` 被当作「写入 `$null`」。

**根因（一句话）**：守卫用「能被正则匹配到的形态」代替了「目标的解析结果与拒绝面」，而失败方向没有写成契约
⇒ 漏放与误拦同时出现，且出现方向与各自守卫的代价模型相反。

## §2 范围

**In**：`packages/coding-agent/src/extensions/agent-team-loop/{worker/worker-mode.ts, pm/ui-bridge.ts, shared/deliverable-evidence.ts}` 的守卫判定依据；
配套测试（新增/加固）；`WRITE_SURFACE_MARKER` 契约处置；文档计数一致性；本文与 `design.md`/`plan.md` 的证据标准。

**Out（非范围）**：
- R21 运行期切换（上一 key 的 R21-H 已完成主体：bundle 已装 + Python 驻留进程已换新）。
- P2（OS 级隔离）——前 key 已明确不在范围，本 key 不变。
- `packages/ai`、`packages/tui`、IN-3 事故既有结论（不重开）。
- 新增功能面（本 key 只加固既有守卫的判定依据，不新增守卫种类）。

## §3 验收标准（AC）

> 证据口径见 AC-011：所有数值必须机器可读，每条结论带 `文件:行号`，引用必须对最终工作树重新锚定。

### AC-001 写面守卫的方向契约（fail-open，`verbatim` 三档）
以 `verbatim(word)`（词中无**未引用**的 `$`/反引号/词首 `~`/glob/花括号）为前置：
① verbatim ∧ 允许面内 ⇒ **allow**；② verbatim ∧ deny 面内或面外 ⇒ **deny（域内绝对优先）**；③ ¬verbatim ⇒ **allow-unknown + 审计行**。
- 判据：RQ-2 语料 `corpus_must_allow=19` 上 `false_positives == 0`（前值 **16**，PM 独立复跑确认）；`corpus_must_block=14` 上 `must_block_currently_allowed == 0`（不得回退）。
- **引用信息是必需项**：token 化必须携带「单引号段/反斜杠转义」标记（RQ-2 P-1/P-3）；否则 `'$T/report.md'` 与 `\$T/report.md` 会从 deny 退化为 allow-unknown（**新增漏放 2 条**）。
- **契约代价必须登记**：F1 `$X/pm-state.md`、F2 `.agenticdoc/<other-key>/$X/pm-state.md`、F3 `$T/../../<other-key>/pm-state.md` 现状拦、契约后 `allow-unknown`。理由（witness）：对含变量 token 判 deny 会被**合法展开**证伪（`X=../<own-key>/evidence` 时实际写入自身允许面）。残余风险不由 PM 侧守卫承担（`judgeWriteIntent` 对 shell 角色直接 `ok:true`），只能由**审计 + run.json 归因**承担 ⇒ AC-007 要求这 3 条必留审计行且带 `risk=deny-basename`。
- 「未知档」不是黑箱：必须同时报 `allow_unknown_count` / `deny_count` / `allow_determined_count`。

### AC-002 写入形态覆盖（提取器）
提取器必须覆盖 RQ-1 枚举的写入形态族：包装器（含 `bash/sh/zsh/dash/ksh/cmd/powershell/pwsh/perl/ruby -c/-e/-Command`）、
重定向算子（`>` `>>` `>|` `<>` `>&` `&>` 及 fd 形式）、操作数即目标（`cp/mv/install/tee/dd/truncate/ln/sed -i/perl -i`）、内联脚本语言。
- 判据：`forms_total=79`、`forms_covered`（前值 35）、`forms_missing`（前值 33，逐条裁定：补提取 或 归入 AC-001 的未知档）；`false_positive_forms == 0`（前值 **8**，含 `truncate -s 0 F`、`write_text('x')`、`> $(...)`、`rm *.txt`、`> ~/f.md`、`> {a,b}.txt`、`> $null`）。
- **完全隐形形态优先**：`bash -c`/`sh -c`/`zsh -c`/`dash -c`/`ksh -c`、`powershell -Command`/`pwsh`、`perl -e`/`ruby -e`、`>|`/`>&` 当前提取到 **0 个候选**（比「漏判」更严重：命令完全不可见）⇒ 必须至少让内层命令进入判定或明确归入未知档 + 审计。
- 不允许用「扩大正则」的方式实现：每条新增形态必须同时给 1 条正例与 1 条**不得误拦**的反例。

### AC-003 跨 key 写意图：解析后的目录判据
写意图白名单必须以**解析后的绝对路径**为准：basename 白名单仅在解析后仍落在自身 `taskDir` 或 `<key>/evidence` 内才成立。
- 判据：目录盲判反例集上 `dir_blind_bypass == 0`，至少含 `../other-key/workers/other-task/output.md`、`..\\o\\pm-state.md`、绝对路径跨盘符形式。
- 正例保持：自身 `taskDir` 下的 `report.md`/`progress.md` 仍必须放行（`own_surface_pass == N`，N 为语料中真实条数）。
- 反例补充（R Q-3）：`.agenticdoc/<other-key>/workers/<task>/output.md`（与前者同族的目录盲判）。
- **现状（PM 源码级证实）**：`isWhitelistedWriteTarget` 中 basename 判定（`WORKER_FILE_NAME_RE` 偏移 239、`FRAMEWORK_TASK_BASENAMES` 偏移 289）**先于**目录比较（`path.resolve` 偏移 361）⇒ 目录盲判成立。

### AC-004 跨 key 写意图：目标集轴（fail-closed，但**不允许裸 token 兜底**）
目标发现不得依赖扩展名白名单 ⇒ 未识别扩展名/无扩展名的写目标必须仍被判为外部写。
- 判据：QG-B 的 5 个漏放样例（`config.toml`/`Makefile`/`.env`/`x.html`/`x.rs`）`leak_caught == 5`（**PM 用已安装 bundle 实测前值 0/5**；`.agenticdoc/_index.parallel`、`.git/config` 前值同样 0 命中）。
- **轴的定义（RQ-3 实测裁定）**：目标识别 = 路径**形状**判定（分隔符 / 前导点 / 扩展形状 / `existsSync` / 冒号），叠加 **允许面 realpath + 段边界**（复用 `worker/read-scope.ts` 的归一）与 **deny 前缀优先**（与 AC-005b 同一 deny 表）。
- **禁止「裸 token 一律 fail-closed」**：RQ-3 在 26 本真实 writeless 任务书上实测该做法引入 **9 本（35%）假阳性**（散文词 `your`/`design`/`mcp`/`side`/`surface`/`message_update`/`-pattern`/`/`）⇒ 不可接受；`Makefile` 这类无扩展名目标靠 **deny-name 表 + `existsSync`** 覆盖。
- 假阳性回归：真实语料 `false_positives == 0`（前值 0，不得恶化）；**预期**现实现 `hits=2 / violations=1 / FP=0` → 新轴 `hits=13 / violations=1 / FP=0`（PM 复跑 `mwds-t02-write-intent.test.ts` = 18 passed，其断言为 `false_positives == []` ∧ 唯一真阳 ⊆ 白名单）；**不得**把 `<key>/evidence` 并入白名单（会让唯一真阳消失、断言变红）。
- Windows 边界（RQ-3 的 9 项实测：大小写不归一、尾点/尾空格、ADS 流形式、长路径前缀形式、`C:foo`）全部落在**拒绝**侧 ⇒ 只可能造成假阳性、不产生漏放；设计阶段逐项给处理或显式接受。

### AC-005 角色判定单一事实源
`type:` 必须**只**取自 frontmatter（首个 `type:` 胜出，正文行不得覆盖），且派发期判据与执行期角色判定必须来自**同一解析函数**。
- 判据：① 注入反例（正文追加 `type: coding`）下两侧判定一致且不被翻转（`self_disable == 0`）；② 存量语料 `files_where_body_would_flip_role == 0`（**前值 1**：`mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md` 头 `coding`/正文 `review`，PM 复现；`body_type=4`/`task_md_total=305`）；③ frontmatter 缺失/无 `---`/`type:` 非法值时的 fail-closed 行为有测试。
- **单源要求**：全仓 `type:` 解析器现有 **6 份**且语义分歧（worker last-wins、`task-dispatcher`/`launcher.py`/`mw.py` first-wins、`status-model` fenced-only）；派发期判据（`resolveDispatchType`）当前**不复用** worker 解析 ⇒ 必须收敛到同一解析函数（或明确记录分歧并给一致性测试）。
- 头部区形态两种都要支持：裸头部（现存 305/305）与 `---` fence（Python/conductor 生产者产出）。

### AC-006 key 身份判据

> [REVISED @ 2026-10-12] **口径收窄（PM 裁定，用户确认）**：本 AC 的「共用同一拒绝判据」**仅闭合权威副本** `.agents/skills/agentic-task/scripts/update_index.py`（已达成：14 名保留清单 + `key_name_refusal` + `claim`/`set-phase`/`set-meta`/`release`/`get-claim` 全部过 gate、两侧 84 行 golden 一致性）。**不包含**由 `install.py` 分发的 `.claude/scripts/update_index.py`（T-13 已证实该副本处于 pi 扩展的活动调用链 `pm/ui-bridge.ts:2345 → shared/agentic-scripts.ts:21-30 → .agents/skills/agentic-task/scripts/advance_phase.py:599`，且无 gate）——该项按用户裁定的 (b) 方案**另立后续 key**（提交推送框架改动 → 重同步 mirror → 重装 `.claude` → 加 mirror 一致性检查），并登记为残余 **C-9**。
跨 key 守卫不得对 `_`/`.` 前缀**无条件**豁免：只豁免显式保留清单（含 `_scratch`）与「未在 `_index.parallel` 出现」的新 key 引导路径；
活持有 key 一律拒绝。key 匹配按 Windows 语义**大小写不敏感**归一，并明确 `_index.md` 回退路径的语义。
- 判据：A5 反例（`_tmp` 形式的活 key）`exempt_live_key==0`；A6 大小写反例（`MW-KEY` vs 磁盘 `mw-key`）`case_mismatch_bypass==0`；A7 回退语义有测试且不产生「有活窗口却判未持有」。
- **现状（RQ-5，PM 采纳）**：A5 的显式名门位于 `findByKey` **之前**（`pm/ui-bridge.ts:277` 的 `foreignLiveClaimRefusal` vs `shared/index-store.ts:285` 的 `findByKey`）；A6 为**大小写归一**匹配（`shared/index-store.ts:212` 的 `claim` 与 `shared/index-store.ts:169` 的 `upsert`）；A7 回退到 `_index.md active` **补 claim 检查**（`pm/ui-bridge.ts:97`）。**触发路径真实但语料未覆盖**：`_index.parallel` 54 行中前缀 key 0、大小写重名 0 ⇒ 三项均为**潜伏**缺口，必须由构造用例（而非自然语料）证明已修。
- **豁免必须显式**：保留名单（`_scratch` 等框架名，共 12 个由 RQ-5 列名）+ 「未在 `_index.parallel` 出现」才构成新 key 引导路径；`advance_phase`（`pm/ui-bridge.ts:2256`）与 `claim` 的放行方向必须一致。

### AC-007 决策可观测性
每个「放行/拒绝」决策必须可解释：拒绝带稳定 code + rule + detail（已有）；**放行**在「判定不确定」时必须留审计行，
使 QG-B 提出的静默路径（A9/A11 类）事后可度量。
- 判据：`allow_unknown_audited == allow_unknown_count`（等值，不允许漏记）；审计行含 `rule` 与目标原文。
- **AC-001 的 F1–F3 必须带风险标注**：`verdict=allow-unknown` 且目标 basename 命中 deny 面（如 `pm-state.md`、`_workers*`）时，审计行加 `risk=deny-basename`，并由 PM 侧把它升级为可见告警（`_autopilot/auto-decisions.jsonl`）——因为守卫本身已按契约放行，只剩可观测性这一道。

### AC-008 未覆盖分支测试化

> [REVISED @ 2026-10-12] **口径收窄（PM 裁定，用户确认）**：原判据要求 QG-B 的 14 条未覆盖分支**全部**测试化。最终实测口径为 **13/14**——T-10 新增 16 个用例覆盖 BR-01…BR-10、BR-14，BR-13 由 T-09、BR-12 由 Python 侧既有用例承载；**BR-11（无 timeline 场景的 doctor 配对）未覆盖**（面板侧已由 `test/suite/autopilot-monitor.test.ts:1254` 覆盖，doctor 配对在 T-10 写入面外），登记为残余 **C-11**。`forms`/`allow-unknown` 审计等量化口径见 AC-002 的度量载体（现值见 §4）。
QG-B 列出的 14 条未覆盖分支逐条有测试，测试名与分支坐标一一对应。
- 判据：`branches_total=14`、`branches_covered=14`，每条给 `文件:行号` + 用例名；覆盖口径按**分支**而非行。

### AC-009 断言质量
消除 2 条空洞（自证式）断言，改为独立数据源断言。
- 判据：`hollow_assertions_before=2`、`hollow_assertions_after=0`；具体含 `DELIVERABLE_PLACEHOLDERS.size` 自计数式断言改为外部期望值断言。

### AC-010 契约与文档一致
`WRITE_SURFACE_MARKER` 二选一：① 有真消费端；② 删除契约并改写设计说明（默认：②，因幂等已由 `applyWriteSurfaceContract` 的正则提供）。
`DELIVERABLE_PLACEHOLDERS` 计数与头部注释/plan/design 一致（实测 16）。
- 判据：`marker_consumers_before=0` → 处置后有明确结论（消费端 ≥1 或 `marker_removed==true` 且设计文档同步）；`placeholder_count_documented == placeholder_count_actual == 16`。

### AC-011 证据标准
所有数值机器可读；每条结论给 `文件:行号`；引用他人产物必须对**最终工作树**重新锚定（禁止引用已漂移的行号/哈希/stale 行）；
反例必须给出「输入 → 期望判定 → 现实现判定 → 修复后判定」。
- 判据：`[VERIFY]` 行数与 VC 数一致；`unanchored_refs == 0`；引用哈希与最终工作树一致。

## §4 度量计划（done 时逐格复测）

| 指标 | 前值 | 目标 |
|---|---|---|
| 写面守卫误拦（RQ-2 语料 19 条 must-allow） | **16** | 0 |
| 写面误拦形态（RQ-1 的 8 条 FP） | **8** | 0 |
| 完全隐形形态（0 候选） | **≥5 类** | 0 类（或显式归入未知档 + 审计） |
| 写面形态 `forms_total` / `forms_covered` / `forms_missing` | 79 / 35 / 33 | 79 / **79** / **0**（机器可读 `[FORMS]`，用例 `test/suite/mwds-t03-bash-write-scope.test.ts` → `T-17/B-6 forms coverage metric`；原始输出 `evidence/runs/t17-forms-baseline-20261012.md`） |
| must-block 漏放（RQ-2 语料 14 条） | 0 | 0（不得回退） |
| 契约代价（F1–F3 由拦变放行） | — | 3 条**登记 + 审计告警** |
| 跨 key 守卫漏放（5 样例） | 5 | 0 |
| 跨 key 目录盲判反例 | 1 | 0 |
| 真实语料假阳性（24 本 review 任务书） | 0 | 0（不恶化） |
| 角色可自我翻转（`files_where_body_would_flip_role`） | **1**（实测，非 0） | 0 |
| `type:` 解析器份数（语义分歧） | **6** | 收敛为单源或记录分歧 + 一致性测试 |
| 未覆盖分支 | 14 | 0 |
| 锚点 `unanchored_refs` | 19/24 抽样不符（QG-B） | **0**（机器可读 `[ANCHORS]`，用例 `test/extensions/agent-team-loop.test.ts` → `T-17/B-1 anchor integrity`） |
| 空洞断言 | 2 | 0 |
| 契约/文档不一致 | 2（C2/C7） | 0 |

## §5 待裁项（PM 提案 + 默认值；用户可改）

- **Q1 方向二分**：写面守卫 fail-open、跨 key 守卫 fail-closed（默认采纳，见 `pm-state.md` D-002）。
- **Q2 C2 处置**：默认「删契约 + 设计说明改写」；备选「补真消费端（执行期按 marker 校验契约完整性）」。
- **Q3 frontmatter-only 的兜底**：默认 fail-closed（缺失即视为 `default` 角色（无写权）？还是 `coding`？）——由 RQ-4 给出兼容风险后 PM 定。
- **Q4 形态覆盖边界**：默认「只覆盖能静态判定的形态；不可判定归入未知档」，不引入 shell 解释器。
- **Q5 A9/A11 是否纳入**：默认「先由 RQ-5 裁定真实性；成立则纳入 AC-006/AC-007，不成立则在 spec 记录为已核查不成立」。

## §6 非目标与残留

- 本 key 不追求「守卫完备性」（shell 语言不可静态完全判定），只追求**已复现缺口清零 + 未知档显式化**。
- 已知残留（本 key 之后仍存在）：无进程级沙箱（P2）；shell 解析的非确定项（由未知档 + 审计承担）。

## §7 可复用资产（复用而非重建）

| 资产 | 位置 | 复用方式 |
|---|---|---|
| 路径归一与段边界判定 | `worker/read-scope.ts::normalizeForCompare` / `isSameOrUnder` | AC-003/AC-004 的目标集轴直接复用（RQ-3 §3 推荐），不另写归一 |
| deny 子规则表 | `worker-mode.ts::bashWriteDenyReason`（6 条：`pm-state.md` / `workers/_workers*` / `_index.parallel` / 其他 key 或 `.agenticdoc` 根 / `packages/**` / `.git/**`） | PM 侧 deny 前缀表与之保持同表（单一语义） |
| 真实语料回放机 | `test/suite/mwds-t02-write-intent.test.ts`（扫真实 `.agenticdoc` review 任务书，断言 `FP==0` ∧ 唯一真阳 ⊆ 白名单）、`test/suite/mwds-t03-bash-write-scope.test.ts` | AC-003/AC-004/AC-001 的硬判据载体（改造而非重写） |
| 控制实验框架 | `evidence/scripts/mwds-controls.ps1`（31 组 A/B/C 红→恢复→绿） | 本 key 的每张卡沿用同一「控制组红」纪律 |
| 告警通道 | `pm-orchestrator.ts::recordDispatchAlarm` / `describeDispatchAlarm` → `.agenticdoc/_autopilot/auto-decisions.jsonl` | AC-007 的 F1–F3 风险告警出口 |
| 事故语料与工具 | `test/fixtures/in3-queue-9col-burst.txt`、`scripts/t23-normalize-whole-queue.py` | 队列相关回归；每次派发后归一化 |
| 三套既有语料 | 305 本 `task.md`（AC-005）、26 本 writeless（AC-004）、24 本 review（AC-003） | 报告的**前值**口径一律以这三套语料计量，禁止另起口径 |
| 独立对抗质量门方法 | `evidence/quality-gate-code-adversarial-20261011.md`（攻击面表）+ PM 的「逐条读源码复现」纪律 | 本 key 收口时的 QG 复用同一攻击面分类 |

## §8 需规避坑点（前馈：踩过的坑不得重踩）

| # | 坑 | 证据 | 规避 |
|---|---|---|---|
| P-01 | **简单扩大正则**修漏放 ⇒ 引入新误拦 | RQ-1 实测 8 条 FP：`truncate -s 0 F`（把 `0` 当目标）、`write_text('x')`（把 `x` 当目标）、`> $(...)`（把 `$` 当目标）、`rm *.txt`、`~/f.md`、`{a,b}.txt`、`> $null` | 每条新形态必须带 1 正例 + 1「不得误拦」反例（AC-002 硬判据） |
| P-02 | **裸 token 一律 fail-closed** | RQ-3：26 本真实 writeless 语料引入 **9 本（35%）假阳性**（`your`/`design`/`mcp`/`side`/`surface`/`message_update`/`-pattern`/`/`） | 只认**路径形状**（AC-004） |
| P-03 | 对含展开语法的 token **判 deny** | RQ-2 witness：`.agenticdoc/<other>/$X/pm-state.md` 现状 deny，而 `X=../<own>/evidence` 时实际写入自身允许面；另 `$T/_workers-notes.md` 会被 basename 规则误拦 | `verbatim` 三档；deny 只在 verbatim 域有定义（AC-001） |
| P-04 | 丢掉**引用/转义信息** | RQ-2 B12/B13：`'$T/report.md'`、`\$T/report.md` 现状 deny，若「含 `$` 即未知」则退化为放行 ⇒ 新增 2 条漏放 | token 化必须携带引用标记（AC-001 显式要求） |
| P-05 | 把 `<key>/evidence` 并入白名单 | RQ-3 §6：会让 write-intent 唯一真阳（`mwg-qg-review-20261010`）消失、断言变红 | 白名单保持现状语义（AC-004 明文禁止） |
| P-06 | 只改 TS、忽略 **Python 侧同族解析器** | RQ-4 §3：`type:` 解析器全仓 6 份，`launcher.py`/`mw.py` first-wins 与 worker last-wins 语义分歧，语料中已实测 1 处分歧 | AC-005 要求「同源或同语义 + 一致性测试」 |
| P-07 | **同文件并发编辑**造成 transient 假红 | 前 key D-023：T-09 的 3 次瞬时 `BLOCKED_ON_HUMAN` 失败源自并发改 `mw_common.py` | 串行链（`design.md` §5）+ 单卡瞬时红不作判据 |
| P-08 | 假设**语料是静态的**、用计数上限断言 | 前 key R-T02-1：`hits <= 2` 在增长语料上会因无关新书变红 | 断言判据本身（`FP==0` ∧ 白名单），不用上限（AC-004/AC-011） |
| P-09 | 改 `parseTaskMd` 后**默认行为无变化** | RQ-4：现存 1 例角色会**放宽**（`mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md`） | AC-005 要求具名记录该文件前后角色 + 用例固化 |
| P-10 | 把守卫改动当「已上线」 | 前 key D-026：TS 守卫在 `mw build --install` 前只在源码/测试级生效 | 收口时区分「源码级验证」与「运行期生效」（R21-H 已装 bundle 但 11 个 pi 窗口未重启） |

> [REVISED @ 2026-10-12] **AC-011 子判据口径**：原「`[VERIFY]` 行数与 VC 数一致」**不可测**（QG-B3 实测：78 条 `[VERIFY]`、24 个不同裸 `VC-NNN`、0 条带 `VC-MWGF-`，同文件内 `VC-007` 有三种语义）。改为：**每条 VC 由唯一 `VC-MWGF-0NN` 标签承载，标签计数 == VC 数且每标签恰 1 次**（载体：T-18 挂牌 + `[ANCHORS]`/VC 唯一性测试）。理由：裸 `VC-NNN` 与历史 key 命名空间冲突，不可作为唯一标识；（原 AC-011 行：- 「Worker 执行过程中追踪 goal 一致性」⇒ 每个「放行/拒绝」决策必须可事后度量（AC-007/AC-011）。）
