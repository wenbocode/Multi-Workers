# Research: L3 流中止的机器指纹（`l3-aborted`）与有界自动重掷接线

> Key: `mw-gate-verdict-hardening` ｜ 角色: SPEC 只读调研（RQ-1） ｜ 快照: 2026-10-10（本地 ~10:55，`02:55Z`；初稿 2026-10-09 `12:30Z`）
> 工作树 HEAD: `10446aefb` ｜ 项目根: `H:\git\Multi-Workers`
> 只读声明: 本轮不修改任何代码或其它文件；本文是唯一产物。
> 输入: `H:\git\E2Feature\.agenticdoc\_autopilot\reflect\l3-reviewer-stream-abort.md`（open）、
> `...\reflect\l3-verdict-source-mismatch.md`（open）、`...\reflect\worker-idle-timeout.md`（open），
> 以及 `H:\git\E2Feature\.agenticdoc` 与 `E:\CLI_workspace\FeatureMigrator\.agenticdoc`（均存在）的
> 真实 `worker.log` / `output.md` / `report.md` / `trace.log` / `_workers.parallel` / `timeline.jsonl*`。
>
> **修订说明（本稿取代前一稿）**：前一稿（同 key，`16:51` 快照）记 `worker.log=844 / L3 轮=54 / 负例=48（21+24+1+2）`。
> 本稿复核后更正两处：① E2Feature 是**活语料**，两次快照之间新增 3 个 L3 轮（详 F5），故 `878 / 57 / 51`；
> ② 负例不再用合并口径的散文分类，改为**逐轮可复算的四象限交叉表**（`output.md` 两节 × `report.md` 两节）。
> 核心结论不变：`stream closed` 行是唯一判别器，正例 **6/6**、负例 **51 轮 0 命中**。
>
> **2026-10-10 复核刷新（F5 表与 [VERIFY] 行以本次快照为准）**：同一活语料再增 4 个 L3 轮
> （`feature-authorization-intake` l3-a1/a2、`feature-dual-switch-compile` l3-a1、`feature-upgrade-cost-actual` l3-a1，
> 全为 report 回退形态、无 marker），故总量由 `878 / 57 / 51` 更新为 `943 / 61 / 55`；
> 正例仍 **6/6**、负例 **55 轮 0 命中**。结构性发现（F1–F4、F6）与本仓 HEAD 绑定（`10446aefb` 未变），不随语料漂移。

## 1 决策问题（RQ-1）

1. `stream closed before response.completed` 由谁写、写到哪个文件；worker 记录为何同时出现 `done exit=0` 与队列 `failed`。
2. conductor 如何判一轮 L3 的「裁决 / 无裁决」：`_parse_l3_output`、`_L3_SOURCE_ORDER`、`_l3_round_verdict`、
   `_l3_provenance_record` / `l3-verdict-provenance.json` 的位置与行为；`l3-no-verdict` 事件在哪一行发射。
3. 轮次重试/预算与 `mark_stalled` 的接线（L3 轮预算计数、`loop`/`attempt`）——「自动重掷」能挂在哪。
4. 三类无裁决（写错文件 / 流中止 / 真 FAIL）当前各自的可观测信号；哪些重叠、哪些互斥。
5. 真实语料（E2Feature + FeatureMigrator）命中轮次清单与对照样本（正负双穷举）。
6. TS 侧（monitor/console/status-model）是否读这些文件，`l3-aborted` 是否需镜像同步。

## 2 调研方法与出处

- 只读 `read` / `Select-String`：`packages/multi-workers/**`（`autopilot/{conductor,state,dispatch,config,timeline,gates,effective_config}.py`、`launcher.py`、`mw_common.py`）、
  `packages/coding-agent/src/**`（`extensions/agent-team-loop/{worker,autopilot,shared}`、`core/agent-session.ts`、`modes/print-mode.ts`）、`packages/ai/src/**`。
- 只读跨项目语料枚举（Python 只读脚本，见 §6；不写盘）。
- `git log -S "stream closed before response.completed"` 追溯字符串引入史；`git grep` 确认全仓字面量。
- 计数方法见 §6，全部可复算；本文所有数值均为本轮实测。

## 3 发现

### F1 中止字符串「由谁写、写到哪」

- **载体**：`worker.log` = launcher 打开的**子进程 stdout 文件**，stderr 合并进同一文件，两者**不可区分**：
  `packages/multi-workers/launcher.py:53-54`（`_worker_log_path` = `task_path` 的父目录 / `worker.log`）、
  `:952`（`log_file = open(_worker_log_path(entry), "wb")`，每次 spawn 截断）、
  `:962`（`"stderr": subprocess.STDOUT`）。
- **写入者 A（框架 worker 自身）**：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:439`
  （`writeWorkerLogLine` 用 `fs.writeSync(1, ...)`）；起始行 `:779`；收尾行 `:1009`
  （`[worker] done exit=0 ...`，由 `recordEnd` `:1000` 发，成功路径 `finishSuccess` `:1270` 在 `:1295` 调 `recordEnd(0)`）。
- **写入者 B（pi print-mode，中止文本的出口）**：`packages/coding-agent/src/modes/print-mode.ts:143-147`
  —— text 模式取最后一条 assistant 消息，若 `stopReason ∈ {error, aborted}` 则
  `console.error(assistantMsg.errorMessage)` 并 `exitCode = 1`；正常路径才把 `content.text` 写 stdout（同文件 `:148-155`）。
  进程退出码由 `main.ts:918-930`（`process.exitCode = exitCode`）落实。
  ⇒ 语料第 3 行 `stream closed before response.completed` 就是这里的 `errorMessage` 落到 stderr，被 launcher 收进 `worker.log`。
- **字符串出身：provider/网关，不是本仓常量**。本仓唯一的近邻抛出点是
  `packages/ai/src/api/openai-codex-responses.ts:1377`（`"WebSocket stream closed before response.completed"`）与
  SSE 路径 `packages/ai/src/api/openai-responses-shared.ts:738`（`"OpenAI Responses stream ended before a terminal response event"`）；
  `git grep "stream closed"` 全仓只命中前者。语料文本**无 `WebSocket ` 前缀**，与两者都不逐字节相等；
  `git log -S "stream closed before response.completed"` 只命中引入 `WebSocket ...` 前缀的那次提交（`a26a9cfab`，前缀自引入即存在）。
  ⇒ 框架侧匹配必须用**子串** `stream closed before response.completed`，不得绑定 `WebSocket ` 前缀，也不得宣称「该文本由 pi 产生」。
- **「done exit=0」与队列 `failed` 并存是同一进程的两条通道**：
  - `agent_settled` 在**任何** prompt 结束后都发射（`packages/coding-agent/src/core/agent-session.ts:596-602` 定义、
    `:1063-1075` `_runAgentPrompt` 的 `finally` 内 `:1073` 调用）——错误轮也一样。
  - worker-mode 的 `agent_settled` 处理器（`worker-mode.ts:1299+`）**从不读** `stopReason`/`errorMessage`，
    于是无 phases 时直接 `finishSuccess`（`:1270-1297`）⇒ 写 `output.md`（`exitCode: 0`）+ `[worker] done exit=0`。
  - 之后 print-mode 按 `stopReason=error` 把**进程**退出码设为 1（`print-mode.ts:145-147`），
    launcher 按真实退出码回写队列行：`launcher.py:799` + `_exit_to_status` `:367-372`（0→done，2→needs-clarification，其余→failed）。
  - **语料实测一致**：6/6 中止轮 `_workers.parallel` status=**failed**（F5），而 `worker.log` 与 `trace.log`
    都写 `exit=0`（6/6 `trace.log` 有 `[END] ... exit=0`）。
  ⇒ 指纹判据里的 `done exit=0` 只能读 `worker.log:1009` 那一行；**不能**要求队列 `status != failed`（6/6 真例全是 failed）。
- **pi 自带重试对本字符串不生效**：`packages/ai/src/utils/retry.ts:26`（`RETRYABLE_PROVIDER_ERROR_PATTERN`）、
  `:230-238`（`isRetryableAssistantError` 只测该正则）、`:162`（`retryAssistantCall`）不含 `stream closed`
  ⇒ 有界重掷只能挂在 conductor 的 L3 回路。
  - **排除 idle/wall 超时**：idle 阈值默认 600 s（`worker-mode.ts:151`）、wall 默认 3600 s（`:145`），
    而 6 例实测 93–272 s 即结束（F5）⇒ 不是看门狗杀进程。

### F2 conductor 现有 L3 裁决判定链

- **`_parse_l3_output`**（`packages/multi-workers/autopilot/conductor.py:1411-1431`）：只读
  `<key>/workers/<l3-aN>/output.md`；缺任一节（`## Quality Gate Report` / `## Achieved`，解析器 `_md_section` `:1396-1409`）
  或命中 `|\s*FAIL\b` ⇒ `below`。这是**旧单源**判定，当前主路径已不唯一依赖它。
- **`_L3_SOURCE_ORDER = ("output.md", "report.md")`**（`:1475`）；`report-<slug>.md` 被**故意排除**（注释 `:1471-1474`）；
  源路径 helper `_l3_source_paths`（`:1515-1517`）= `key_dir/"workers"/task_key/{output.md,report.md}`。
- **FAIL 判据族**：`_L3_FAIL_RE`（`:1478`）、`_L3_FAIL_BULLET_RE`/`_L3_FAIL_PROSE_RE`/`_L3_FAIL_ZERO_RE`（`:1482-1484`）、
  扫描器 `_l3_fail_marker_line`（`:1487-1505`）。
- **`_l3_read_source`**（`:1520-1527`）、**`_l3_qualifies`**（`:1530-1536`，两节齐备即合格）、
  **`_l3_resolve_source`**（`:1538-1553`，fail-closed：任一可读源含 FAIL ⇒ `below`+该源+FAIL 行；
  否则首个合格源 ⇒ `meets`；否则 `below`+无源+无 FAIL 行）。
- **`_l3_round_verdict`**（`:1556-1608`）返回四元组 `(verdict, worker status, deciding source, fail line)`：
  - `:1581-1584` 从 `rows`（`_workers.parallel` 解析行）取该轮 `status`；
  - **`:1585-1586` 状态门在最前**：`status ∈ {failed, needs-clarification}` ⇒ 直接 `("no-verdict", status, None, None)`，
    **不读任何源文件**；
  - `:1588-1594` 无任何可读候选源 ⇒ `("no-verdict", status or "no-row", None, None)`；
  - `:1607-1608` 否则交 `_l3_resolve_source`。
  ⇒ 现有 6 个真例全部在 `:1585-1586` 短路成 `no-verdict`；**新指纹必须插在该状态门之前**。
  4 元组长度被测试钉死（`test_autopilot_verdict_provenance_guard.py:637-655`），值域未钉死。
- **`l3-no-verdict` 事件发射点**：`_verify_loop`（`:1837`）内 `:1888` `if verdict == "no-verdict":` →
  `:1893-1896` `st.timeline.append("l3-no-verdict", key=key, detail=f"l3-a{used} worker status={worker_status} → re-review")`
  （detail 行在 `:1895`）。语料实测 detail 正是 `l3-a3 worker status=failed → re-review`（F5）。
- **provenance guard**：`_PROVENANCE_FILENAME = "l3-verdict-provenance.json"`（`:1510`）；
  `_l3_provenance_record`（`:1620-1713`，用同轮 `trace.log` mtime 做锚 + slack 60 s，`suspect ∧ raw=meets ⇒ below`）；
  `_persist_l3_provenance`（`:1715-1766`，append-only、按 `task_key` 去重、`tmp`+`os.replace`、坏 sidecar 不覆盖）。
  调用点 `:1915-1920`，被 `if l3_source is not None` 前置 ⇒ **无裁决轮（源为 None）不写 provenance，零痕迹**。
- **终态派生物**：`_persist_l3_verdict`（`:928-975`）写 `<key>/l3-verdict.txt`（值域仅 `meets|below`）与 `<key>/l3-report.md`，
  并在 timeline 记 `config` 事件；done 事务前校验五件套（`_done_credentials_present` `:1768-1815`）。

### F3 轮次预算 / `loop`·`attempt` / `mark_stalled` 接线——「自动重掷」的挂点

- **轮次计数是声明性的**：`rounds = state.used_rounds(_all_workers_dirs(project_root))`（`conductor.py:247`；
  `_all_workers_dirs` `:2415-2421`），实现 `state.py:224-249`——扫 `.agenticdoc/*/workers/*/task.md` 的
  `loop:`/`attempt:` 标签，按 `loop` 去重 `attempt` 计数；标签由 dispatch 渲染（`dispatch.py:359-360`）。
  无私有状态 ⇒ conductor 重启不丢。
- **L3 预算**：`_verify_loop` `:1853-1859`
  （`l3_loop = f"l3:{key}"`、`l3_budget = max(1, cfg["round_budget"])`、`l3_limit = l3_budget + _resume_credits(...)`、
  `used = rounds.get(l3_loop, 0)`）。默认 `round_budget = 2`（`config.py:60`，域 `:82`）；
  人工批准一个 `stalled` gate 给该 key 每个受约束回路各 1 轮（`_resume_credits` `:2660-2681`，一次性、单调消耗）。
- **现有「自动重掷」其实已存在，只是无分类**：`no-verdict` 分支 `:1897`（`used >= l3_limit` 才 stall）
  否则 `:1907-1913` 直接重派 `l3-a{used+1}`（`loop=l3_loop, attempt=used+1`）。
  ⇒ 缺的是 ①`l3-aborted` 分类 ②不占共享轮预算的**专用有界计数**（中止当前会消耗 `l3:` 轮，4 次即耗尽 → stalled）。
- **`mark_stalled`**（`:4709-4802`）：写 roadmap key-status=stalled + 建 `stalled` gate
  （`machine_fields` 带 `reason_code/loop/used_rounds/round_limit/credits_used`，`:4743-4759`）
  + `achieved.md` 遗留草稿 + `patterns/<key>/stall-lesson.md`。
- **reason_code 是闭集且被测试钉死**：`STALL_REASON_CODES`（`:4891-4903`，12 项，含 `l3-no-verdict` `:4898`）、
  `REASON_CODES`（`:4925-4927` 由其推导）；写侧闭集守卫在 `_stamp_gate_defaults`（`:2508-2526`，越界码被丢弃并记 `config` 事件）；
  长度锁 `test_autopilot_auto_decision.py:301`（`len(...) == 12`）与 `:330-339`（12 个 `mark_stalled` 调用点各自映射一个新码，集合相等）。
- **残留闭环（必须同步）**：`_recompute_l3_stall_code`（`:5348-5373`）会从磁盘重算 stall 原因码；
  对中止轮它仍返回 `l3-no-verdict`（`:5369-5370`，因状态门先给出 no-verdict）；`_stall_family`（`:5288-5301`）按 loop 标签分族，
  未知标签落 `advance-class` ⇒ 触发 `stalled-reason-drift`（`:5038-5042`）。
  只加事件/分类而不改重算映射，gate 的 `reason_code` 与 `cause_class` 会判成 drift。
- **可挂点（供 DESIGN，本稿不给实现）**：指纹计算放在 `_l3_round_verdict` 状态门（`:1585`）之前；
  重掷决策放在 `_verify_loop:1888` 的 `no-verdict` 分支之前，用独立 loop 标签承载（`state.used_rounds` 天然给出独立预算，
  与 `repair:{key}` 同族：读 `:2008`、stall 码 `:2017`、`repair_base` `:2005`）。

### F4 三类（实为四类）无裁决的可观测信号矩阵

`rows` = `_workers.parallel` 解析行（`task_key | status | tool | provider | task_path | started | updated | model`，status 是第 2 列）。

| 信号（文件:字段） | B 流中止 | A 写错文件/载体不符 | C 真 FAIL | D 其它瞬败（provider 403 / 错误 model id） |
|---|---|---|---|---|
| `worker.log` 含子串 `stream closed before response.completed` | **有**（唯一指纹） | 无 | 无 | 无 |
| `_workers.parallel` 行 `status` | `failed`（`launcher.py:367-372`） | `done` | `done` | `failed` |
| `worker.log` 行 `[worker] done exit=0`（`:1009`） | 有（会误导） | 有 | 有 | **也有**（D 实测，不可判别） |
| `trace.log` `[END] ... exit=` | 0（worker-mode 逻辑码，非进程码） | 0 | 0 | 0 |
| `output.md` 两节 | 缺（harness 占位 160–582 B） | 缺（占位）或散文 | **齐备** | 缺（181 B 占位） |
| `output.md`/`report.md` FAIL 标记行 | 无 | 无 | **有**（`_l3_fail_marker_line`） | 无 |
| `report.md` 存在且两节齐备 | 无（6/6 不存在） | 常见（A 的主形态） | 常见 | 无 |
| `l3-verdict-provenance.json` 记录 | **无**（无源 ⇒ `:1915` 前置跳过） | 有（有源时） | 有 | 无 |
| timeline 事件 | `l3-no-verdict`（`:1894`） | `l3-no-verdict`（状态门）或 below 路径 | below/repair 路径 | `l3-no-verdict`（与 B 完全重叠） |

- **互斥核心**：`stream closed` 行是 B 的充分必要新增指纹；语料上它与「两节齐备」0 重叠、与 FAIL 标记 0 重叠、
  与 `status=done` 0 重叠（F5）。
- **重叠风险（必须靠指纹拆开）**：
  1. **A 与 B 现象完全重叠**（output.md 缺两节 + `done exit=0`）：reflect 的 `l3-verdict-source-mismatch.md`
     与 `l3-reviewer-stream-abort.md` **各自把同一批轮**（`feature-inline-marker-patchkit` l3-a1/a2）算作自己根因；
     实测这两轮**都有** `stream closed` 行 ⇒ 属 B（`stream closed` 是唯一判别器）。
  2. **B 与 D 重叠**（`status=failed` + output.md 缺两节）：语料上该组合共 8 轮，其中 6 轮有 marker（B）、
     2 轮是 D（`feature-params-service` l3-a1/a2，`worker.log` 第 4 行 `OpenAI API error (403): ...模型不存在...`，
     `tools=0`、0 s）⇒ marker 精确切出 B，**D 必须保持 0 假阳性**。
  3. **C 与 A 的差别**是「源里是否有 FAIL 标记行」；C 与 B 不重叠（C 两节齐备且有标记）。
- **第四类（B 之外的新形态，会误判为 below）**：reviewer 把结论写成**无节标题的 `report.md`**
  （编号章节 `## 0. ...`/`## 4. VC 断言表` + 最终消息散文），既无两节也无 FAIL 行 ⇒ `_l3_resolve_source` 判 `below`（源为 None）。
  实例：`FeatureMigrator/gui-monitor-hitl-e2e` `l3-a3`（2026-10-09，本日活样本，`status=done`、39 min、57 tools，
  `report.md` 22491 B 但无 `## Quality Gate Report`，`output.md` 被 checkpoint steer 文本占位）。
  ⇒ SPEC 的「三类」在语料里至少是**四类**，建议 DESIGN 明确该形态归属（既非 aborted，也不该算 C）。

### F5 真实语料：正负双穷举（E2Feature + FeatureMigrator）

- 「L3 轮」定义 = 目录名匹配 `-l3-a\d+$`；「两节齐备」= 该文件同时含 `## Quality Gate Report` 与 `## Achieved`。
- **总量（本轮快照）**：`worker.log` = **943**（E2Feature 686 + FeatureMigrator 257）；L3 轮 = **61**（E2Feature 38 + FeatureMigrator 23），
  且 61/61 的 `task.md` `type: reviewer`。
- **正例（含 marker）= 6，全部在 E2Feature（FeatureMigrator 0）**，且 **6/6 同时满足**：`type=reviewer`、
  队列 `status=failed`、`output.md` 缺两节、`report.md` 不存在、无 FAIL 标记、`trace.log` 有 `[END] exit=0`：

| # | key | 轮次 | output.md | 队列 status | trace [END] | 判定源 |
|---|---|---|---|---|---|---|
| 1 | `feature-inline-marker-patchkit` | `l3-a1` | 272 B | failed | exit=0 / 272s / 43 tools | 无 |
| 2 | `feature-inline-marker-patchkit` | `l3-a2` | 582 B | failed | exit=0 / 146s / 56 tools | 无 |
| 3 | `feature-gui-time-mvp-board` | `l3-a1` | 272 B | failed | exit=0 / 147s / 46 tools | 无 |
| 4 | `feature-gui-time-mvp-board` | `l3-a4` | 465 B | failed | exit=0 / 93s / 31 tools | 无 |
| 5 | `feature-false-meets-remediation` | `l3-a3` | 470 B | failed | exit=0 / 118s / 47 tools | 无 |
| 6 | `feature-false-meets-remediation` | `l3-a4` | 260 B | failed | exit=0 / 99s / 41 tools | 无 |

  - marker 在 6/6 文件里都是**最后一条内容行**（距 EOF 40 B，即后随一个 `\n`；文件体积 160–179 B）。
  - 全仓（两个目标根）**非 L3 轮 0 命中**：943 个 `worker.log` 中仅此 6 个含该行。
  - reflect note 写「累计 7 例」；**实测 6 例**（其表 5 行 + 追加表新增 `l3-a4` 一行 = 6；第 7 例无文件依据）。
  - 该子串只出现在 6 个 `worker.log`、`gates/gate-0016.md`/`gate-0017.md`/`gate-0018.md`（**人工**闸门 note）与 reflect note；
    `output.md` / `report.md` / `trace.log` **零命中**。
- **负例穷举 = 55 轮，0 命中 marker**（四象限交叉表，逐轮可复算）：

| 类别 | E2Feature | FeatureMigrator | 合计 | 现行判据 |
|---|---|---|---|---|
| `output.md` 两节 + `report.md` 两节 | 13 | 17 | 30 | meets/below（按 FAIL 标记） |
| `output.md` 缺两节 + `report.md` 两节 | 14 | 3 | 17 | report 回退（A 类主形态） |
| `output.md` 两节 + `report.md` 缺两节 | 3 | 2 | 5 | 按 output.md |
| 两者都缺两节 | 2 | 1 | 3 | below（源为 None） |

  - 按 status：非中止轮 `done` 53、`failed` 2；含 FAIL 标记的 17 轮。
  - 两者都缺的 3 轮：E2 的 2 轮 = `feature-params-service l3-a1/a2`（**D 类**：`failed`、181 B 占位、`tools=0`、
    0 s、`worker.log` 第 4 行 `OpenAI API error (403): {"message":"...模型不存在..."}`、错误 model id `gpt-5.6.sol`）；
    FM 的 1 轮 = `gui-monitor-hitl-e2e l3-a3`（**第四类**，`done`、无节标题散文 report，见 F4）。
  - **假阳性边界**（`status=failed` + 两文件都缺两节）共 8 轮：marker 切成 **6 B / 2 D**。
    这是 `l3-aborted` 指纹必须保持 0 假阳性的最小反例集。
- **timeline 侧**：E2Feature timeline（`_autopilot/timeline.jsonl*`，已轮转 `.1/.2`）中 `l3-no-verdict` 共 **6 条**，
  detail 形如 `l3-a3 worker status=failed → re-review`；FeatureMigrator **0 条**。
  marker 两轮（2026-09-24）**没有该事件**（事件在 `feature-l3-verdict-source-fallback` 之后才存在）⇒ 分类缺失在历史上比事件更早。
  另注：同一轮会被**重复发射**（本轮语料里 `gui l3-a4` 与 `false-meets l3-a3` 各出现 2 次，分别在不同 tick/不同 resume 之后），
  该事件无去重（`_timeline_has_event` `:1817-1834` 只有拒绝路径在用）。
- **口径说明**：E2Feature 是活语料，快照间会漂移（本稿口径三跳：`16:51` 版 `844 / 54 / 48` → `2026-10-09 20:30` 版 `878 / 57 / 51` → `2026-10-10 02:55Z` 本版 `943 / 61 / 55`）。
  本版新增的 4 个 L3 轮是 `feature-authorization-intake l3-a1/a2`、`feature-dual-switch-compile l3-a1`、`feature-upgrade-cost-actual l3-a1`（
  均为 report 回退，无 marker）；更早一版新增的 3 个是 `feature-build-baseline l3-a1`、`feature-stage3-residual-repair l3-a1/a2`。
  可复算命令见 §6；语料类结论应按本版快照读，结构性结论（F1–F4、F6）不随漂移。
- **附：本仓（`H:\git\Multi-Workers`）语料另计**（不在任务指定范围内，仅供对照）：`worker.log` 259 个、L3 轮 0、
  marker 命中 2 个且全部 `type=coding`（如 `ga-spec-design-review-2`、`review-mw-target-partition-design`）。
  注：launcher 每次 spawn 以 `"wb"` 截断 `worker.log`，故该计数随重跑漂移（上一版记 4 个）；结论「非 L3 专属」不受影响。
  ⇒ 该字符串**并非 L3 专属**，只是仅 L3 轮会因此丢失两节；这是「指纹必须限定在 L3 判定链」的直接依据。

### F6 TS 侧读取面与镜像同步需求

- TS 侧 `autopilot/{status-model,monitor,console,gate-writer}.ts` **不读** `worker.log` / `output.md` / `report.md` /
  `l3-verdict.txt` / `l3-verdict-provenance.json`（grep 零命中）；它们只消费派生面：
  `status-model.ts:48-53`（`gatesDir`/`timelinePath`）、`:922-955`（`listGates`）、`:1029-1110`（timeline + 轮转链）、
  `shared/index-store.ts`（`_index.parallel`）。
- **timeline 词汇是跨语言闭集且被集合相等测试锁定**：
  Python `timeline.py:67-96`（`EVENT_TYPES`，`l3-no-verdict` 在 `:84`）与 TS `status-model.ts:962-988`（`l3-no-verdict` 在 `:979`）；
  判据 = 集合相等、两侧差集均须空：`packages/coding-agent/test/suite/autopilot-event-parity.test.ts:72-98`。
  ⇒ `l3-aborted` 若作为**新 timeline 事件**，必须**两侧同时**加入（`timeline.py` + `status-model.ts`），否则 parity 红 / console 默认视图吞掉。
- **gate `reason_code` 在 TS 是纯透传**：`status-model.ts:894`（`reasonCode: optional("reason_code")`）、
  `monitor.ts:108-109,226,782-783`、`console.ts:409`——**无闭集校验**。
  ⇒ `l3-aborted` 若作为 gate `reason_code`，只需改 Python（`STALL_REASON_CODES` + `_recompute_l3_stall_code`），
  TS 面板/console 自动显示；但 `test_autopilot_auto_decision.py:301` 的 `== 12` 与调用点集合锁要同步。
- **gate frontmatter 面不膨胀**：`_REQUIRED_FIELDS` 冻结为 6（`gates.py:138-145` 导入期断言），
  `reason_code` 本就是可选 v2 字段（`gates.py:102`）⇒ 新增原因码不触 required 面。

## 4 结论 → 决策映射

1. **AC-001 的 `done exit=0` 只能指 `worker.log:1009` 那一行**，不能指进程退出码、更不能要求队列 `status != failed`
   （6/6 真例 status 全为 `failed`，F1/F5）⇒ 判据三要素 = `worker.log` 含子串 `stream closed before response.completed`
   + `output.md` 缺两节 + 该行存在。
2. **指纹挂点必须在状态门之前**（`_l3_round_verdict:1585-1586` 会短路，F2）⇒ DESIGN 需明示新增一次 `worker.log` 读取；
   本稿不宣称「零额外读取」。
3. **自动重掷动作已存在**（`_verify_loop:1907-1913`），缺的是 ①`l3-aborted` 分类 ②不占共享轮预算的专用有界计数
   （建议独立 loop 标签，复用 `state.used_rounds`，F3）③`STALL_REASON_CODES` 与 `_recompute_l3_stall_code`/`_stall_family` 同步，
   否则 `stalled-reason-drift`。
4. **互斥性可在语料上机械验收**：marker 与 A/C/D 的信号在 61 轮上 0 重叠（F5）；最小假阳性边界 = 8 个
   `failed`+两文件都缺两节的轮，marker 切成 6/2。
5. **镜像面最小化**：timeline 事件需两侧同步（F6）；`reason_code` 只需 Python（TS 透传）。
6. **SPEC 边界应写进第四类**（无节标题 `report.md`），否则「三类」与语料不符（F4/F5）。

## 5 数据缺口与风险

- 中止字符串的**逐字节出处**无法在本仓定位（F1）⇒ 指纹只能按子串匹配，DESIGN 不得声称「该文本由 pi 产生」。
- 语料为**活语料**：本仓 `.agenticdoc` 的 marker 命中数在本次调研期间从 2 漂到 4（全部 `type=coding`）。
  语料类结论应绑定本稿快照；单测必须用合成夹具，不得依赖项目外路径。
- 未做「换 review 模型后是否再复现」的持续观察（reflect 的下一步判据），本轮只做只读普查。
- 计数依赖目录名 `-l3-aN`（项目约定）；若命名变化，§6 脚本需同步。
- E2Feature timeline 已轮转，跨轮转计数需三文件合计；`l3-no-verdict` 6 条全在 `.2`。

## 6 复算脚本（只读）

```python
# A. 总量 + marker 命中（判据：子串匹配）
from pathlib import Path
import re
ROOTS = [Path(r"H:\git\E2Feature\.agenticdoc"), Path(r"E:\CLI_workspace\FeatureMigrator\.agenticdoc")]
ABORT = "stream closed before response.completed"
for base in ROOTS:
    logs = sorted(base.glob("*/workers/*/worker.log"))
    hits = [p for p in logs if ABORT in p.read_text(encoding="utf-8", errors="replace")]
    l3 = [p for p in logs if re.search(r"-l3-a\d+/worker\.log$", p.as_posix())]
    print(base.parent.name, "worker_logs", len(logs), "l3_rounds", len(l3), "hits", len(hits))
```

```python
# B. 正负双穷举：四象限交叉表 + status + FAIL 标记（输出见 F5 两张表）
from pathlib import Path
import re, collections
ROOTS = {"E2": Path(r"H:\git\E2Feature\.agenticdoc"), "FM": Path(r"E:\CLI_workspace\FeatureMigrator\.agenticdoc")}
ABORT = "stream closed before response.completed"
def both(p):
    if not p.is_file(): return False
    t = p.read_text(encoding="utf-8", errors="replace")
    return "## Quality Gate Report" in t and "## Achieved" in t
def failmark(p):
    return p.is_file() and bool(re.search(r"\|\s*\**\s*FAIL\b", p.read_text(encoding="utf-8", errors="replace")))
status = {}
for name, base in ROOTS.items():
    for line in (base / "_workers.parallel").read_text(encoding="utf-8", errors="replace").splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) >= 2: status[(name, p[0])] = p[1]
c = collections.Counter()
for name, base in ROOTS.items():
    for d in sorted(base.glob("*/workers/*")):
        if not re.search(r"-l3-a\d+$", d.name): continue
        a = (d / "worker.log").is_file() and ABORT in (d / "worker.log").read_text(encoding="utf-8", errors="replace")
        c[("abort" if a else "no", status.get((name, d.name), "?"),
           f"O{int(both(d / 'output.md'))}R{int(both(d / 'report.md'))}",
           f"FAIL{int(failmark(d / 'output.md') or failmark(d / 'report.md'))}")] += 1
for k in sorted(c): print(k, c[k])
```

```python
# C. marker 的字节位置（实测 6/6：距 EOF 40 B，为最后一条内容行）
from pathlib import Path
NEEDLE = b"stream closed before response.completed"
for base in (Path(r"H:\git\E2Feature\.agenticdoc"), Path(r"E:\CLI_workspace\FeatureMigrator\.agenticdoc")):
    for p in base.glob("*/workers/*/worker.log"):
        d = p.read_bytes(); i = d.find(NEEDLE)
        if i >= 0: print(p.parent.name, "size", len(d), "from_eof", len(d) - i)
```

```powershell
# D. 等价 PowerShell（任务要求的 grep 形式）
Get-ChildItem -Recurse -Filter worker.log -Path H:\git\E2Feature\.agenticdoc, E:\CLI_workspace\FeatureMigrator\.agenticdoc |
  Select-String -SimpleMatch "stream closed before response.completed" |
  ForEach-Object { "$($_.Path):$($_.LineNumber)" }
```

[VERIFY] RQ-1: snapshot=2026-10-10T02:55Z HEAD=10446aefb worker_logs=943(E2=686,FM=257) l3_rounds=61(E2=38,FM=23) l3_types=reviewer_61/61 stream_closed=6(all_in_E2,FM=0;all_reviewer;all_status=failed;all_output_missing_both;all_report_absent;all_FAIL=0;all_trace_END_exit=0;marker_from_eof=40B;size=160-179B) non_abort=55(status_done=53,status_failed=2;O1R1=30,O0R1=17,O1R0=5,O0R0=3;FAILmark=17) false_positive_boundary=failed_and_both_files_missing=8 marker_split=6B/2D(2=provider_403) reroll_branch=conductor.py:1888-1914 fingerprint_must_precede_status_gate=conductor.py:1585-1586 l3_limit=conductor.py:1858 used_rounds=state.py:224-249 stall_codes=12(test_autopilot_auto_decision.py:301) timeline_event=l3-no-verdict(conductor.py:1894,timeline.py:84,status-model.ts:979) parity=set_equality(autopilot-event-parity.test.ts:72-98) reflect_claimed=7 measured=6 e2_events=6 fm_events=0 worker_log_max=20746B p50=3213 p95=5076 p99=9996 over64KiB=0 mw_root_hits=2(all_type=coding,out_of_declared_corpus;worker_log_truncated_per_spawn) audit_scripted=true
