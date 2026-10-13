# spec.md — mw-autopilot-gate-alarm-liveness（autopilot 门禁提醒的存活性与可见性）

- Key: `mw-autopilot-gate-alarm-liveness`｜Created: 2026-10-13｜Phase: SPEC（4 个 RQ 已终态，本文件为定稿）
- 上游输入（**已核实存在**）：
  - `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md`（4,217 B，对方给 mw 的 5 条请求 P0×2/P1×2/P2×1）
  - `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\reflect\stale-serve-silent-stall.md`（7,051 B，A-20/分类⑱）
  - `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\reflect\_index.md`（17,788 B，该目录共 21 文件）
- 项目级依据：`.agenticdoc/goal.md`（无人值守并行开发）；`.agenticdoc/mw-dispatch-card-gate/achieved.md`（刚收口：同族反模式）
- SPEC 阶段证据（全部实测，字节准、行数自述虚高约 1.6~1.7 倍）：
  `evidence/research/spec-rq1-reminder-chain-20261013.md`（40,654 B）/ `spec-rq2-stalled-state-machine-20261013.md`（36,422 B）/ `spec-rq3-serve-metadata-drift-20261013.md`（40,704 B）/ `spec-rq4-schema-and-view-surface-20261013.md`（37,560 B）/ `spec-bootstrap-declaration-20261013.md`（2,952 B）

## §0 Goal Alignment

### §0.1 核心问题（用户 2026-10-13 重述，本 key 的第一性目标）

1. **阻塞无感知、派发被卡住**（最核心）：autopilot 下某个 key/门禁被阻塞时，**没人知道**，而**派发也跟着停**——症状是“看上去在运行，实际什么都不发生”。本 key 要回答的第一句话是：**现在卡在什么地方、卡了多久、堵塞了谁**。
2. **窗口并不显式 watch 某个 key**：autopilot 的常态就是无人值守、无人 watch。⇒ **conductor/launcher 的派发与门禁处理不得以“某窗口在 watch”为前置**（否则无人值守时派发天然失效）；无 watch 必须与有 watch **行为等价**（这比 AC-010 的“不得静默丢弃”更根本，单见 AC-014）。
3. **autopilot = 自动驾驶，gate 越少越好**：小 gate（如 stage-close、文书型完成）应当能**自动收集证据并 approved**，只把真正需要人判断的门留给人；目标是**减少必须等人响应的门禁总数**，而不是只把它们变可见（见 AC-015）。

### §0.2 与目标的关系

本项目目标是让一个 PM Agent 编排多个 Worker 并行开发同一项目，前提是**编排链路自身不会静默失效**。`mw-dispatch-card-gate` 已修掉「roadmap 一行坏 ⇒ 整表不可用 ⇒ 连无关能力一起停摆 + 2 天零告警」。本 key 处理**同一族反模式的下一处**：autopilot 的 **pending gate 提醒**。实测（FeatureMigrator，2026-10-13）：key `gui-release-hardening` 卡在 `gate-0022`（`kind: stalled`，`2026-10-12T09:54:03Z` 创建）静置 **12 小时**，而 conductor 一直在跑（beat ≈670 次/小时、最大间隔 15 s、无缺口）；**全历史 212,609 条 timeline 事件中 `gate-reminder` = 0 次** —— 因为运行中的 serve（PID 116368，启动 `2026-09-26 10:30:42`，已 408 小时）**比源码早 15 天**，提醒守护（`ab546bb64`，10-11 18:12 引入）从未存在于该进程（Python 只在启动时 import）；同期 `1cf35637f`（10-10）、`b8bc115ff`（10-09）同样未生效。⇒ 本 key 的验收标准是「**任何时刻都能回答"现在有哪些门禁在等人、等了多久、为什么没提醒我"**」，且该答案不依赖事件推送（事件会停、会衰减、会被 cap）。

**预期收益**：① 门禁等待从「靠推送、可能永久静默」变为「状态面恒可见」，操作者任何时刻可自查，不重演 12 h / 38 h / 12 d 5 h 级静默；② 提醒的失效从「静默」变为「**可见地降级**」（cap 用尽、被抑制、未到期都在状态行标注原因）；③ serve/conductor 能自证代码版本，消除「进程活着但跑旧代码」这一类隐蔽故障（本次事故的直接成因）；④ `stalled` 可分类、可重评，降低一个 key 因误判报废的概率；⑤ 全部改动复用既有通道（stderr + timeline + 既有 view 枚举），不新增日志/通知基础设施、**不新增 config 键**。

## 1 背景与问题（E）

- **E1 静默的提醒通道**：写入面只有 **2 处** —— 台账 `.agenticdoc/_autopilot/auto-decisions.jsonl`（`conductor.py:2708`）+ timeline `gate-reminder`（`:2717`）；`_remind_pending_gates` 函数体内**无 stderr**（对比同文件 roadmap 告警 `:2617` 确有 stderr）。
- **E2 封顶即沉默，且计数持久化**：`gate_reminder_max` 默认 2 且 schema 闭区间 `[1,2]`（`config.py:57/:103/:134`，TS 镜像 `status-model.ts:190-191`）。实测 `gate-0024` 的 n=1/n=2 **相隔 4 秒**（一个 tick 吃完 cap）后静默 158.3 min；`gate-0025` 静默 98.0 min。cap 计数持久化在台账 ⇒ **任何只改事件面的修复都无效**。
- **E3 全项目级整体抑制**：`conductor.py:2558` 判据是整个 `_workers.parallel`，任意 key 有在飞工作 ⇒ **所有** gate 的提醒一律不发（含"该 key 无在飞工作"的 gate）。
- **E4 stage 终止抑制（真实危害已量化）**：`:2562-2566` 使 `gate-0024`（stage 4 的**重复 stage-close**，stage 4 在 `02:48:01Z` 已 `closed`）被压制 **6.78 h** —— 该窗口内条件 1/2/3 全部不成立；其两条提醒**之所以发出**，仅因 `14:11:15–24Z` 三个 tick roadmap 恰好不可读 ⇒ **fail-open**（提醒只在"出错时"才发得出）。
- **E5 `stalled` 不可分类**：`gates.py:44/:76` 的 kind 集合只有 `stalled`，全仓无 `blocker_class`。文书型阻塞可**确定性判定**（`.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern '…'`）并走幂等 `splice_achieved` 拼接钩子（产物已在任务侧就绪），既不消耗判定预算，也不应把人叫起来。
- **E6 `stalled` 的出口/可逆性（已校正）**：入口 2 个（`mark_stalled:5271`，14 个触发点 + `apply_review_decision("escalate"):3601` 声明存在但无生产调用者）；出口 **3 个** —— approve→`running`（`:3289`）、reject→`closed-legacy`（`:3340` 是全仓唯一写入点，全历史仅 1 实例）、**答门前延后→`pending-review`（`:3701`/`:3667`，其 reject = `rework→running`，永不 `closed-legacy`）**。`:3326` 注释的 `closed-legacy → stalled` 回环**代码级成立（`:5294` 只短路 `== "stalled"`）但无 conductor 内部路径**（14 个调用点被 `_DISPATCH_SKIP_STATUSES:70` 挡住）⇒ 只有 out-of-band 的 `_roadmap.md` 写者能触发，真实数据 0 实例。**reject 在状态机内不可逆为真，但"选错就废掉一个 key"是夸大**：恢复 = 人工改 `_roadmap.md` 一行（stage 已 closed 时再改一行），代价是**无审计痕迹** + 已耗轮次不退 + 需重新 stall→approve 才得一轮。⇒ 无"证据变更 ⇒ 重评"入口。
- **E7 部署漂移不可见（本次事故主因）**：conductor 是 serve 的第三子进程（`mw.py:140-198`，D-101），`/mw restart` 才重拉。`serve.meta` 今日只有 `{pid, started_at_ms, code_dir}`（唯一 writer `mw.py:122-131`，**非原子写**；唯一读取值是 `started_at_ms`；`code_dir` **无任何读者**）⇒ **无 commit/版本身份**。实测运行中的 conductor 写出的 stderr/timeline 文本**逐字等于 `b65380d1b^`**（旧代码）。TS 侧已有 stale-serve 检测（`shared/mw-runner.ts:195-330`，判据是**纯 mtime**）与 `console.ts:611/:629` 的交互恢复；Python 侧等价物只在 `mw update-env`（非 tick、非告警）。
- **E8 可见面结构缺陷**：唯一 push 消费面要求**窗口正在 watch 该 key**（`pm-orchestrator.ts:1466-1513`，`:1489`）否则事件被丢弃；面板 `BLOCKED_ON_HUMAN` 与条件 2 **同源同盲区**；timeline 10MB×3 轮转把事件挤出尾窗。RQ-1 穷举 **14 条永久静默路径（P1–P14）**。
- **E9 存量兼容面（RQ-4 下界 → DRQ-1 纠正 → PM 已逐项复现）**：本机共 **56** 个 gate = **v1 51 / v2 5**，分布 **E2Feature 26（`H:\git\E2Feature`）/ JCodingAss 8（`H:\git\JCodingAss`，`gate-0001..0008` 全 v1）/ FeatureMigrator 22（`E:\CLI_workspace\FeatureMigrator`）/ Multi-Workers 0**；`blocker_class` **缺字段率 56/56（100%）**。真实 `pending` 存量 **3 个**：JCodingAss `gate-0007`（`stage-close`，**key 为空**，`2026-09-17T20:04:14Z`，已等 25.6 天）/ `gate-0008`（`stage-close`，key 为空，`2026-09-26T04:37:27Z`，17.0 天）—— 该项目无 `auto-decisions.jsonl` ⇒ 零提醒记录；加 `FeatureMigrator/gate-0022`。⇒ 两条教训写进判据：① **普查必须先把所有项目根枚举齐**（RQ-4 只扫 `H:\git\*` 得 34）；② **项目根未经证实不得写入判据**（RQ-4 与 PM 都把 JCodingAss 猜成了 `E:\CLI_workspace\JCodingAss`，实为 `H:\git\JCodingAss`）③ **key 为空的 gate 不得被“在飞抑制”误杀**（不可解析 ⇒ 不抑制，与 AC-002 一致）。
- **E10 回收契约对 writeless 角色的盲区**（本 key 自曝，C-36）：四份 research worker 的 `trace.log` 里 `evidence/research` 出现 **0 次**，而四份交付物都在（40,654/36,422/40,704/37,560 B）⇒ 交付物写入对账本**不可见**；同时账本把报告里**被读取**的路径名当写入意向（`serve.meta` ×35 触发假 `needs-clarification`），并把**未展开变量**当路径记录（`path=$dir`、`path=$src`、`path=$env:TEMPmwgal-…py`）。

## 2 需求（AC）

| AC | 判据（可机器验证） | 验证方式 |
|---|---|---|
| AC-001 | **monitor 常驻 pending-gate 行**：每个 `pending` gate 恒可见（id/kind/key/stage/已等时长/**被抑制原因**/scope 可解析性），**无 cap、无衰减、无去重**；数据来自磁盘状态 + 派生计算，**不依赖任何事件**；插入点 `monitor.ts:234 scanPendingGate` → `:335 readMonitorState`（age 在 `:427`）→ `:766 renderMonitorLines` 的 gates 段 `:879-908`（宽 110，drop 序 `1reason→2age→3scope→4drift`） | 单测：cap 用尽 + 有在飞 worker + stage 终止条件下，状态行仍列出该 gate 与"已等 N 分钟"及原因 |
| AC-002 | **提醒不再整体抑制**：仅在"该 gate 所属 key 存在在飞工作"时抑制；**key/stage 不可解析的 gate 一律不抑制**（缺记录不得静音，沿 `:2535-2550` 既有 fail-open 原则）；**被抑制也必须留一条可见记录**（上游 P0-② 原文要求） | 单测三分支：他 key 在飞⇒仍发射；本 key 在飞⇒不发射但有可见记录；不可解析⇒发射 |
| AC-003 | **抑制原因封闭枚举**（无现成字段可承载，须在三个读面派生、不落盘）：`key-in-flight / stage-terminal / cap-reached / not-due / unresolved-scope / gate-queue-unreadable`；cap 轴唯一权威输入是 `_reminder_count`（`conductor.py:2512`），TS 侧接入已存在但未使用的 `readGateReminders`（`pm-orchestrator.ts:1289`） | 单测：六种原因各一例，行内文案与枚举值一一对应 |
| AC-004 | **每次发射走 fail-loud 双通道**（stderr + timeline），内容含 gate id/kind/key/已等时长/原因/可执行动作；`gate_reminder_max` 语义**降级为"打断次数"**，cap 用尽后**状态面照旧**且在状态中显式标注"已达打断上限，仍待处理"；限频只防刷屏 | 单测：发射时 stderr 有行 + timeline 有事件；cap=2 后第 3 次不发射但状态行标注 |
| AC-005 | `serve.meta` **记录 commit 与 dirty 标记**（复用 `_git_head_short`/`_git_dirty`，但**必须补 `timeout` + `CREATE_NO_WINDOW` + None 降级**；比对环节用**纯文件读** `.git/HEAD`→loose→`packed-refs` 免 spawn）；启动与每 tick 比对工作区 HEAD，漂移 ⇒ 告警含"期望/实际 + 漂移时长 + 修法 `/mw restart`"；**必须保留至少一个"新鲜进程侧"入口**（serve 自身不可自证）；**重启后复核 pending 门禁未被新自动裁决意外改写** | 单测：commit 不等 ⇒ 告警一次（限频键 `(code_dir, meta_commit, head_commit, serve_pid)`）；相等 ⇒ 无告警；dirty 工作区不误报 |
| AC-006 | 漂移告警与门禁告警**复用同一可见通道**（stderr + timeline `config`），不新造日志文件；与 TS 侧 stale-serve 检测**分工不重复**（Python 拥有持久记录 + serve 生命周期限频；TS 只保留交互恢复，不新增周期通知；Python 不自动重启） | 单测：写入面 = 既有两通道；同漂移在两侧不产生双份周期通知 |
| AC-007 | gates schema 新增 `blocker_class ∈ {paperwork, judgment}`：**parser 保留 `None`，只有判定层折成 `judgment`**（fail-safe）；**必须走 `authorizes` 的"冻结 40 名序之外注册"先例**（不得进冻结名序，4 处测试硬红）；漏注册一处即 fail-closed ⇒ 需专项测试；`contract_guard.py` **零改动**；`paperwork` 判据 = `.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern '…'`，走幂等 `splice_achieved` 钩子且不消耗判定预算；最小写入面 = `mark_stalled` 的 `machine_fields` + `_stamp_gate_defaults` 闭集守卫 | 单测：34 存量 gate（v1 29/v2 5）解析后 `blocker_class is None`；判定层得 `judgment`；冻结名序未变；三读面（Python P1-P9 / TS T1-T9 / monitor）各一例 |
| AC-008 | **gate re-attest 入口**：新建 gate + `context_refs` 放 `reattest-of:<id>`（**schema 零改动**，`_gate_open` 已用 `context_refs` 做去重维度），配一个不依赖 `status=="stalled"` 的独立消费者（照 `_apply_review_decisions:3624` 成例）；不得绕过 AC 锁协议（编号不复用、原判定留痕） | 单测：re-attest 后新判定可区分来源、原 gate 判定留痕 |
| AC-009 | `rejected` **二次确认**（destructive 需显式确认）；文档措辞校正为"状态机内不可逆，但恢复 = 人工改 `_roadmap.md` 一行，代价是无审计痕迹 + 轮次不退"；并记录 `closed-legacy ↔ stalled` 回环只在 out-of-band 可达 | 单测：无确认 ⇒ 拒绝执行；确认 ⇒ 执行并留痕 |
| AC-010 | **消费面不再依赖"窗口正在 watch"**：被丢弃的事件必须留下可见痕迹（状态行或告警），不得静默丢弃 | 单测：无 watch 时事件被丢弃 ⇒ 产生可见记录 |
| AC-011 | **不新增 config 键**（避开 20 键冻结 schema + `status-model.ts` 双镜像 + parity）；`gate_reminder_max` 语义变化须 TS/Python 同步且 `autopilot-config-parity.test.ts` 绿 | 跑 parity 测试 |
| AC-012 | **不回归**：pending gate 的既有约束力、fail-open 原则、T-20 的 roadmap 告警通道与去重语义、`gate-reminder` 对既有消费端（`pm-orchestrator.ts:1472/:1502`）兼容；`GateView` 被 `autopilot-console.test.ts:384-389` 锁死的现状须显式处理（扩展字段而非破坏断言）；**TS 第 3 个解析面不得静默忽略新字段** | 既有两轮 QG 相关测试 + 定向回归全绿 |
| AC-013 | **回收契约对 writeless 角色不再"量错对象"**（C-36，本 key 内修）：① writeless 角色（`research`/`review`）只把"声明写出的唯一交付物"当写入意向，其余路径视为**读取引用**；② 覆盖 taskDir 之外的交付物写入（现存四份 trace 对 `evidence/research` 零可见）；③ 路径卫生：未展开变量（`$dir`/`$src`/`$env:TEMPxxx`）与不可解析路径一律 `malformed`，不得作为写入证据 | 单测：research 报告含被读取路径 ⇒ 零假阳性；真实越界写入 ⇒ 仍红；含 `$var` 路径 ⇒ 不构成证据 |
| AC-014 | **派发不得以“某窗口已接管（`switch_key`）该 key”为前置**（用户裁定 2026-10-13，第一性目标 ②）：autopilot 常态就是**没有任何窗口接管 key**。因此 conductor/launcher 的派发与门禁处理路径**不得**要求存在 live claim/owner；无接管时必须与有人接管**行为等价**（不得退化为“claim-free ⇒ 跳过”，如运行期实证 C-35：`claim-free repair skipped, nothing written (…原因=index 状态 idle)`）。**路线已定（D-013，用户裁定 2026-10-13）：conductor 自动接管**（合成 claim-id，如 `autopilot@<pid>`；**放弃路线② claim-free 派发**）—— 设计须同时定义：合成 claim 的生命周期（何时创建/续期/**失效回收**，即 C-35 的 stale-owner 不得反过来阻塞）、人工 `switch_key` 的**移交与冲突**语义、`_index.parallel` 的呈现、以及“同一 key 单一写入方”如何在合成 claim 下成立。原候选： ① conductor **自动接管**（合成 claim-id，如 `autopilot@<pid>`，使 claim 存在但不依赖人窗口）；② 派发完全 claim-free 但保留“同一 key 单一写入方”保证。验证：在**无任何 `switch_key` 的会话**下制造可派发工作与 pending gate，断言派发仍发生且状态面可见 | 集成/单测（无接管会话） |
| AC-015 | **小 gate 自动收证 + 自动 approve**（用户裁定，第一性目标 ③，autopilot = 自动驾驶）：对**证据可确定性机器收集**的低风险 gate（stage-close / 文书型完成等，具体范围由 DRQ-4 定），由 conductor **自动收集证据并 approved**，人只面对真正的 judgment 门；**安全边界**：仅当证据判据确定性（可复算 + 可留痕）且 gate 非 destructive 时自动；每次自动裁决必须留痕（`answered_by` + 依据）；**收集失败/判据不可用 ⇒ 回落为人工 gate，绝不静默跳过**；不得放宽既有判据（P-03）；目标包含**减少必须等人响应的 gate 总数**并可度量 | 单测（自动/回落两分支）+ 运行期观察（自动批准占比） |
| AC-016 | **状态面必须承载 stage 级主闸**（"派发为什么停"的直接答案，用户批准 2026-10-13）：显示每个 stage 的**状态**（pending/running/closed/halted）+ **卡在哪道门**（stage-confirm / stage-close / stalled 冻结 / 预算 / goal-change）+ **已等时长** + **被冻结的 key 列表**。依据：`_stage_activation:671` 是"是否放行逐 key 派发"的开关（返回 False ⇒ 本 tick 提前 return，`conductor.py:245-247`），未答的 stage-confirm/stage-close、`halted`、`_DISPATCH_SKIP_STATUSES:70` 冻结的 key 都会让派发静默停止（存量 56 gate 中 **24 个是 stage 级主闸**、**31 个是 key 级冻结**） | 单测：构造"stage-close 挂起 + 下一 stage pending"与"key stalled"两种形状，断言状态面直接显示主闸、原因与已等时长 |

## 3 约束（P）

- **P-01 不新造通道**：只用既有 stderr（`.mw/conductor.log` 随 serve）与 timeline 事件；不新建日志文件、不新建通知类型。
- **P-02 状态面优先于事件面**：任何"永久静默"的修复都必须落在**状态读取**上（时间不保险：tick 会停、进程会死、timeline 只有 200/400 条尾窗、10MB×3 轮转、**且 cap 计数持久化**）。
- **P-03 判据不放宽**：不得为让测试变绿而放宽既有断言；旧夹具改**数据**不改**判据**。
- **P-04 生效路径**：Python 侧需**各项目重启 serve/conductor**（`/mw restart`）才生效（构建期/导入期差异），TS 侧需 `build --install` + `/reload`；AC-005 应把这一步自动化并自证。
- **P-05 兼容面**：gates 为 v1/v2 双 schema 存量（34 个，100% 缺新字段）；新增字段必须有缺省语义且不得进入冻结名序。
- **P-06 隔离**：本 key 不写其他 key 的目录；`E:\CLI_workspace\FeatureMigrator`、`H:\git\E2Feature`、JCodingAss 仅只读取证。
- **P-07 证据与复核纪律（经两次自我修正后定稿）**：
  1. **字节数可信**（本阶段 6/6 与自述精确匹配），可作复核尺子。
  2. **行数在本环境有三个互相矛盾的口径**：`Get-Content | Measure-Object -Line` 会少算空行（DRQ-1 298 vs `(Get-Content).Count` 343）；`Select-String` 的 `LineNumber` 也不可信（它把一个实测 105 行的文件的段报成“149/164 行”）；worker 自述的行数又**高于任一口径**（DRQ-1 自述 415 > 343 > 298）。⇒ **复核不得以行号定位，必须用字符串锚（grep 关键符号/关键句）**；行号仅作参考且必须注明测量口径。
  3. **反向教训（写给未来的 PM，包括我）**：我曾据一个自己没校准的工具口径判定“worker 行数普遍虚高”并写进 P-07 —— 证据不足，现已改正；**若一个结论依赖于自己不懂的工具行为，先校准尺子，再指控对方**。
- **P-08 卡面纪律**：卡面必须**逐字写出**证据文件所需的 H2 段名（见 §5 坑点 6），否则回收门禁判"缺段"。

## 4 可复用资产

- **双通道 fail-loud 封装**：`conductor.py:2594-2660`（`_ROADMAP_ALARM_SEEN` 按 `(file,line,kind)` 会话级去重 + `_emit_roadmap_failure`/`_emit_roadmap_warnings`，stderr + timeline `config`，含路径/行号/原因/修法）—— AC-004/AC-006 直接复用（必要时提升为通用 alarm helper，不新造第二条）。
- **台账计数**：`_reminder_count:2512`（`D-006` 已论证时序状态不能靠 timeline 尾窗）。
- **状态面地基**：`status-model.ts:636+` 的 view 侧 gate 枚举 + `monitor.ts:234/:335/:766/:879-908` 的渲染链（**结论：不需要新状态源**，id/kind/stage/key/`created_at`/ageMs 已收齐）；TS 已有 `readGateReminders`（`pm-orchestrator.ts:1289`）未接入。
- **字段注册先例**：`authorizes` 的"冻结名序之外注册"先例（`blocker_class` 必须照抄）；`gates.py:159-174/:507/:537` 的解析面。
- **Python 侧监督前例**：`mw.py:140-198`（conductor 监督，每秒判定 spawn/terminate）+ `:4354 _framework_version()`；TS 侧 `shared/mw-runner.ts:195-330`（staleness 检测 + `restartMw`）。
- **文书型确定性钩子**：`.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern` + 幂等 `splice_achieved`。
- **回归命令**（上游提供）：`Get-Process -Id <pid> | Select StartTime` × `git log -1 -- packages/multi-workers/autopilot/conductor.py`；`gate-reminder` 计数脚本；beat 连续性检查。

## 5 需规避坑点

1. **冻结 40 名序与序外注册**（DRQ-1 已量化）：名序 = `gates.py:95-139`（12 base + 26 v2 + 2 consumed），TS 镜像 `status-model.ts:660-701`；硬红断言 **4 个测试函数 / 5 条**（`test_autopilot_gates.py:224`、`test_autopilot_gate_schema_v2.py:143`、`test_autopilot_contract_guard.py:187` 三处均 `assert len(...) == 40`，PM 已实测）。`blocker_class` 是**标量** ⇒ **必须新开“平行标量集”，不得复用 `_JSON_LIST_FIELDS`(`gates.py:160`)**；照抄 `authorizes` 需覆盖 **7 个代码登记点 + 3 个测试锁 + 1 个 materialize 点**（Python 4 / TS 3）。**漏注册的后果**：Python 解析面漏 ⇒ `GateFormatError` ⇒ `enumerate/pending_gates` 整体抛 ⇒ 提醒（`conductor.py:2692-2694`）/ 阶段跃迁（`:509-512`）/ goal-change 闸门（`:2905-2908`）**一起停摆**；TS 面漏 ⇒ `listGates` 剔除 + errors；**monitor `scanPendingGate` 漏 ⇒ 静默消失（比报错更危险）**。⇒ 必须有 fail-closed 专项测试（T-A 注册/缺省/闭集、T-B Python monkeypatch 清空注册集、T-C TS `Set.delete` 反事实、T-D 跨语言锁、T-E monitor 静默面防回归）。
2. **TS 第 3 个解析面会静默忽略未加分支的新字段** ⇒ 漏改一处 = 字段静默消失（比报错更危险）。
3. **`GateView` 缺 key/stage 且被 `autopilot-console.test.ts:384-389` 精确锁死** ⇒ 只能扩展、不能破坏断言。
4. **cap 计数持久化** ⇒ 只改事件面无效（必须改状态面）。
5. **`_remind_pending_gates` 只在发射时写字段** ⇒ 抑制原因无现成承载，必须派生。
6. **卡面段名必须逐字**：证据文件需 `## 结论 / ## 证据 / ## 残留与未验证 / ## 上下文来源` 四个 H2 段；散文式描述会判"缺段"（本阶段 T-02/T-04 两次假判定即此因）。
7. **`edit`/`write` 对全角半角敏感**、**PowerShell 无 heredoc**、**bash 引用 `.agenticdoc/_autopilot` 时不得出现 `LastWriteTime`/`Replace`**（子串 `Write` 触发 xkey 写守卫；纯读命令去掉即可）。
8. **项目级轴必须同批改**（DRQ-2 连带发现）：`blocked_on_human` 有三处实现（`monitor.ts:442`、`status-model.ts:1354-1356`、`mw_common.py:3279-3291`）且都是**项目级**轴；AC-002 改成 per-key 后必须**同批改三处**，否则面板与发射器互相矛盾。
9. **面板 drop 序与 AC-001 冲突**（DRQ-2 实证）：事故形状（keyed gate + reason）下现行 drop 序先丢 `reason`、再丢 `age`（141→120→109 列）⇒ 与“原因必须恒可见”矛盾，必须在 AC-001 里显式修正 drop 序（`reason` 不得先丢）。
10. **队列不可读在 TS 三面全部静默**（DRQ-2 新发现）：`readdir`/`readFile` 失败都退化为“0 pending”，只有 doctor 记录 ⇒ 面板会把“读不到队列”显示成“没有门禁”，是**新增的静默失败路径**；AC-003 的 `gate-queue-unreadable` 必须在三面都真正可见。
11. **不做**（本 key 排除）：`_workers.parallel` 单写入方 / `run.json` 唯一权威 / EPERM 原子性（另立 key）。

## 6 design 阶段并行调研（3 个，互不重叠，各唯一证据文件）

| RQ | 问题 | 唯一证据文件 |
|---|---|---|
| DRQ-1 | 字段注册与三读面贯通：冻结 40 名序 + `authorizes` 序外注册先例的精确做法、fail-closed 专项测试面、Python P1-P9 / TS T1-T9 / monitor 三处改动清单 | `evidence/research/design-drq1-field-registration-20261013.md` |
| DRQ-2 | 状态面设计：常驻行的派生字段计算（六值枚举）、`GateView` 锁死下的扩展方式、drop 序与宽度、无 watch 丢弃的可见痕迹、"重启后复核 pending 门禁"检查点 | `evidence/research/design-drq2-monitor-state-surface-20261013.md` |
| DRQ-3 | 漂移自检设计：`serve.meta` 加 commit/dirty、比对与告警、限频键、**新鲜进程侧入口**、Windows 无 git/多 worktree/dirty 的边界、与 TS 侧分工 | `evidence/research/design-drq3-drift-selfcheck-20261013.md` |

## §7 design 阶段追加事实（DRQ-1/2/3，PM 已抽查复现）

- **判据换轴（DRQ-3 C1/C4）**：`mtime` 看不见**未提交删除**；`commit` 在"把 dirty 树提交掉"时给出**假漂移**（本仓 `packages/multi-workers` 今日即 dirty 11+9，且正是 FeatureMigrator 的 `code_dir`）⇒ 权威判据 = **`code_digest`**（runtime 文件集 sha256，实测 71 文件 / 1,305,650 B / 7.6 ms）；`mtime` 供漂移起点，`commit` 供命名与 capability。
- **`_git_head_short` 不可直接复用（PM 原种子的错误，已纠正）**：它走 `rev-parse --short HEAD`（`mw.py:5188`）给出**动态长度短 OID**（今日 `cc9a46a1a`），而纯文件读给 40 位 OID ⇒ 字面永不相等 ⇒ 照抄即**永久假漂移**。
- **身份采集必须前置到 `_write_pid` 之前（已复现）**：`_write_pid`(`mw.py:271`) 先于 `_write_serve_meta`(`:273`) ⇒ 一次挂死的 git 会留下"PID 在、服务没起"的假象（"PID 文件存在 ⇒ 服务已起"是被依赖的既有不变量）。
- **skip 集必须加目录名 `test`（已复现）**：`_mw_code_newest_mtime` 的判据是 `f.name.startswith("test_")`（**basename**），只跳 `test_*.py` 文件、**不跳 `test/` 目录**；其 71 个输入文件里 **49 个（69%）是 `test/` 夹具** ⇒ 改夹具会把健康 serve 判 stale。
- **P2 变机器可检**：`meta.schema < EXPECTED_SCHEMA` ⇒ "必须重启 serve"（存量 meta 等价 `schema=0 < 1`）；重启后复核 pending 门禁 = `answered_by=conductor-auto:` + `answered_at > 新 serve.meta.started_at_ms`（**零新字段、零新文件**）。
- **存量现场今天即可判（不需先重启）**：旧 meta 已含 `started_at_ms`+`code_dir` ⇒ 现场复算 PID 116368 漂移 **1,468,520 s ≈ 16 d 23 h 55 m**（uptime 409.7 h）；**保留窗实测 12.8 天 < 漂移 16.98 天**（`conductor.log` 0 B、按会话 truncate）⇒ 当年即使告警也已滚出 —— "状态面必须可随时重算"的硬证据。
- **新鲜进程侧入口 4+1**（DRQ-3）：`mw status` / `mw doctor`（drift ⇒ issue ⇒ exit 1）/ `mw update-env` A3（基线改 `meta.code_dir`）/ TS `serveStaleness`；可选 OS 探针（ctypes `GetProcessTimes`，meta 与 OS 启动时间差 1.0 s）。

## §8 PM 裁定（DRQ-3 上交的两个决策点）

- **D-009（接受收窄）**：AC-005 字面的"commit 不等 ⇒ 告警"在 `code_digest` 存在且**相等**时收窄为 `history-only`（只记录、不告警）—— commit 不等而 digest 相等 = "提交后工作未变"，属正常开发流；否则造成假漂移疲劳，与 AC-012 相悖。
- **D-010（改夹具数据，不放宽判据）**：`test_update_env.py` 的 healthy-world fixture 用 `code_dir: "fake"`，在新判据下为 `undecidable`；按 P-03 **改夹具数据**（给真实 `.git` 或显式 digest 期望），不得把判据放宽成"无法判定即健康"。

- **D-011（用户裁定 2026-10-13：自动 approve 取中档）**：自动放行范围 = ① 证据全在磁盘且判据可复算的**文书型/`stage-close`** 门；② **可自动收集证据的完成型门**（achieved 草稿拼装、verdict 汇总等）。**不含**"超时 N 分钟一律放行"（进取档）；destructive 与显式 `judgment` 永不自动。安全阀：收集失败/判据不可用 ⇒ **回落人工 gate**，不静默跳过。
- **D-012（用户裁定 2026-10-13："watch key" 语义 = `switch_key` 接管）**：第一性目标 ② 的准确提法是：autopilot 下**没有任何窗口 `switch_key` 接管 key** ⇒ 任务阻塞。⇒ 阻塞不只在事件消费面（`pm-orchestrator.ts:1489` 需窗口 watch），更在 **claim/owner 面**：无 live claim 时 conductor **主动跳过**（C-35 运行期实证："claim-free repair skipped, nothing written … 原因=index 状态 idle"）。已立 AC-014 要求派发与门禁处理不得以 live claim 为前置，路线二选一（conductor 自动接管 / claim-free 派发）由 design 定。

- **D-013（用户裁定 2026-10-13：AC-014 取路线① = conductor 自动接管）**：autopilot 下由 conductor 以**合成 claim-id**（如 `autopilot@<pid>`）接管“有工作但无 live claim”的 key，使“无人值守”不再等价于“无 owner 即跳过”（C-35）；“人工 `switch_key` 是常态”从此不再是设计前提。设计必须回答：claim 生命周期（何时创建/续期/回收）、与人工 `switch_key` 的移交与冲突、`_index.parallel` 的呈现、以及“单一写入方”保证如何在合成 claim 下保留。**放弃 claim-free 派发路线**（避免与既有多窗口并发保护冲突）。

- **D-014（用户批准 2026-10-13：stage 级主闸的处置口径）**：① **`stage-close` = AC-015 的第一优先自动放行对象**（唯一"证据可确定性机器收集 + 非 policy"的 kind；复用 `_closure_dossier_md:979` + `_done_credentials_present:1853`；收集失败/判据不可用 ⇒ **回落人工并显示缺失项**）；② **`stage-confirm` 只做可见性升级，不自动放行**（"开始一个 stage"是授权而非文书，D-011 中档不含）；③ **状态面新增 stage 主闸行**（AC-016）；④ **实施前必须先核实 `conductor.py:3542` 的 “48h fallback” 是否是一条既有超时自动闭合路径** —— 若是，必须与 AC-015 **合并**而非并存（避免两条互相打架的自动路径）；核实结果无论正负都记入 design.md。
- **D-015（PM 登记：stage 级主闸的量化危害）**：`_stage_activation:671` 返回 `True` 的**唯一**条件是存在 `running` stage；`halted` 直接 `return False` 且**无自动出口**（只能人工改 `_roadmap.md`）；`_activate_pending_stage` 的 roadmap-writer **最多 2 次提案**，两次被拒即停等人工。⇒ "无人值守 + 门禁等人"的必然表现就是**派发卡死**，而非"少发几条提醒"。