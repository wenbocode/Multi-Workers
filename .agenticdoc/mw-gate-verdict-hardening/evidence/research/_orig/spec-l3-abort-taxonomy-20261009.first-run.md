# Research: L3 流中止的机器指纹（`l3-aborted`）与有界自动重掷接线

> Key: `mw-gate-verdict-hardening` ｜ 角色: SPEC 只读调研（RQ-1） ｜ 快照: 2026-10-09
> 工作树 HEAD: `10446aefb` ｜ 语料冻结时刻同快照
> 只读声明: 本轮不修改任何代码与其它文件；本文是唯一产物。
> 输入: `H:\git\E2Feature\.agenticdoc\_autopilot\reflect\l3-reviewer-stream-abort.md`（open）、
> `...\reflect\l3-verdict-source-mismatch.md`（open）、`...\reflect\worker-idle-timeout.md`（open），
> 以及两个项目根的真实 `worker.log` / `output.md` / `trace.log` / `_workers.parallel` / `timeline.jsonl`。

## 1 决策问题

1. `stream closed before response.completed` 由谁写、写到哪个文件；worker 为什么会在记录里显示 `exit=0`。
2. conductor 现在如何判一轮 L3 的「裁决 / 无裁决」：`_parse_l3_output`、`_L3_SOURCE_ORDER`、
   `_l3_round_verdict`、`_l3_provenance_record` / `l3-verdict-provenance.json` 的位置与行为；
   `l3-no-verdict` 事件在哪一行发射。
3. 现有轮次重试/预算与 `mark_stalled` 的接线（L3 轮预算计数、loop/attempt），「自动重掷」能挂在哪。
4. 三类无裁决（写错文件 / 流中止 / 真 FAIL）当前各自的可观测信号；哪些重叠、哪些互斥。
5. 真实语料（E2Feature + FeatureMigrator）中该行的命中轮次与对照样本（正负双穷举）。
6. TS 侧（monitor/console/status-model）是否读这些文件，`l3-aborted` 是否需镜像同步。

## 2 调研方法与出处

- 只读 `read` / `Select-String`：`packages/multi-workers/**`（conductor/launcher/gates/timeline/state/dispatch/config/mw_common）、
  `packages/coding-agent/src/**`（agent-team-loop worker/autopilot、core/agent-session、modes/print-mode）、
  `packages/agent/src/**`（agent-loop/proxy/agent）、`packages/ai/src/**`（api/openai-*、utils/retry）、
  `packages/ai/scripts/generate-models.ts`。
- 只读跨项目语料：`H:\git\E2Feature\.agenticdoc`、`E:\CLI_workspace\FeatureMigrator\.agenticdoc`
  （每次 `python` 只读枚举，未写盘；`_workers.parallel` 只解析不修改）。
- `git log -S` 追溯中止字符串的引入历史；`git status` 确认写面归属。
- 计数方法见 F5 与 §6，全部可复算（命令随附）。

## 3 发现

### F1 中止字符串「由谁写、写到哪」：不是框架日志，是 pi print-mode 的 stderr

- **载体**：`worker.log` 是 launcher 打开并重定向的 **子进程 stdout 文件**，stderr 合并进同一文件：
  `packages/multi-workers/launcher.py:53-54`（`_worker_log_path` = task 目录/worker.log）、
  `:952`（`log_file = open(_worker_log_path(entry), "wb")`）、
  `:961-962`（`"stdout": log_file, "stderr": subprocess.STDOUT`）。
  ⇒ 文件里 **stdout 与 stderr 不可区分**。
- **写入者 A（框架的 worker 进程自身）**：`worker-mode.ts:436-443`（`writeWorkerLogLine` 用 `fs.writeSync(1,...)`）；
  起始行 `:778-780`；收尾行 `:1008-1010`（`[worker] done exit=0 ...`，由 `recordEnd` `:1000-1006` 写）。
- **写入者 B（pi print-mode，中止文本的来源）**：`packages/coding-agent/src/modes/print-mode.ts:141-147`
  —— text 模式下取最后一条 assistant 消息，若 `stopReason` 为 `error`/`aborted` 则
  `console.error(assistantMsg.errorMessage)` 并 `exitCode = 1`；正常路径才把 `content.text` 写 stdout
  （同文件 `:151`）。异常抛出路径另在 `:159-160` catch 后写 stderr，同样落进 worker.log。
- **中止文本如何进入 `errorMessage`**：流错误被折成 `stopReason="error"` 的 assistant 消息
  （proxy 路径 `packages/agent/src/proxy.ts:216-226` 设 `partial.errorMessage`；turn 汇入 `agent.ts:569-572`；
  agent-loop 收到 error 事件后 `agent-loop.ts:347-360` 产出 final message，
  `:196-200` 见 stopReason error 即 `agent_end` 返回）。
- **字符串出身：provider/网关，不是本仓常量**。当前树内 byte-相近的抛出点只有两处：
  `packages/ai/src/api/openai-codex-responses.ts:1377`（`"WebSocket stream closed before response.completed"`）与
  SSE 路径 `packages/ai/src/api/openai-responses-shared.ts:737-738`（`"OpenAI Responses stream ended before a terminal response event"`）。
  语料的第 3 行是 `stream closed before response.completed`（**无 `WebSocket ` 前缀**），与两者都不逐字节相等；
  且 `timi/gpt-5.6-sol` 走 `openai-responses`（`packages/ai/scripts/generate-models.ts:491` 附近 `api: "openai-responses"`）。
  `git log -S "stream closed before response.completed"` 只命中引入 `"WebSocket stream closed ..."` 的那次提交
  （`a26a9cfab`，该前缀自引入即存在）⇒ **语料字符串来自 timi llmproxy 网关或旧版 pi 构建**。
  框架侧匹配必须用**子串** `stream closed before response.completed`，不得绑定 `WebSocket ` 前缀。
- **为什么语义上「成功」与「失败」同时出现**（本轮最关键的一条）：
  - `agent_settled` 在**任何** prompt 结束后都发射（`agent-session.ts:1063-1075` `_runAgentPrompt` 的 `finally`
    → `:1073` `_emitAgentSettled()`；定义在 `:596-602`），错误轮也一样。
  - worker-mode 的 `agent_settled` 处理器（`worker-mode.ts:1299+`，无 phases 时 `:1307-1309` 调 `finishSuccess`）
    从不读取 `stopReason`/`errorMessage`（全文件仅 `:983-984` 用 `agent_end` 刷新活动时钟）
    ⇒ `finishSuccess`（`:1270-1297`）写 `output.md`（`exitCode: 0`，`:1274`）、`recordEnd(0)`（`:1295`）
    ⇒ worker.log 出现 `done exit=0`，`trace.log` 出现 `[END] exit=0`。
  - 之后 pi print-mode 才按 `stopReason=error` 把进程退出码设为 **1**（`print-mode.ts:145-147`），
    launcher 按真实退出码回写队列行：`launcher.py:796-801` + `_exit_to_status` `:367-372`（0→done，2→needs-clarification，其余→failed）。
  - **语料实测一致**：6/6 中止轮的 `_workers.parallel` 行 status=**failed**（见 F5），而
    `worker.log`/`trace.log` 都写 **exit=0**。
  ⇒ 实现 `l3-aborted` 时，「done exit=0」只能读 worker.log 的那一行，**不能**读队列行 status（它是 failed）；
  若判据要求 `status != failed` 才修复，则 6/6 真例全部漏判。
- **pi 自带的自动重试对本字符串不生效**：`packages/ai/src/utils/retry.ts:26-80` 的可重试正则表
  （`RETRYABLE_PROVIDER_ERROR_PATTERN`）与 `isRetryableAssistantError`（`:230-238`）不含 `stream closed`，
  故 `retryAssistantCall`（`:162` 起，调用点 `agent-session.ts:1084`）不会自动重掷。
  ⇒ 有界重掷只能挂在框架侧（conductor L3 回路），本 key 的 AC-003 方向正确。

### F2 conductor 现有 L3 裁决判定链（精确位置与行为）

- **`_parse_l3_output`**（`packages/multi-workers/autopilot/conductor.py:1411-1431`）：只读
  `<key>/workers/<l3-aN>/output.md`；缺任一节（`## Quality Gate Report` / `## Achieved`，由 `_md_section` `:1396-1409` 解析）
  或出现 `|\s*FAIL\b` ⇒ `below`。它是**旧的单源判定**，当前主路径已不再唯一依赖它。
- **`_L3_SOURCE_ORDER = ("output.md", "report.md")`**（`:1475`）与 `_l3_source_paths`（`:1515-1517` 附近）：
  `report-<slug>.md` 被**故意排除**在回退源之外（注释 `:1471-1474`）。
- **FAIL 判据**：`_L3_FAIL_RE`（`:1478`）、`_L3_FAIL_BULLET_RE`/`_L3_FAIL_PROSE_RE`/`_L3_FAIL_ZERO_RE`（`:1480-1485`）、
  扫描函数 `_l3_fail_marker_line`（`:1487-1508`）。
- **`_l3_qualifies`**（`:1530-1536`：两节齐备即合格）与 **`_l3_resolve_source`**（`:1538-1554`，
  fail-closed：任一可读源含 FAIL ⇒ below；否则首个合格源 ⇒ meets；否则 below + 无源）。
- **`_l3_round_verdict`**（`:1556-1618`）返回四元组 `(verdict, worker 状态, 判定源, FAIL 行)`：
  - `:1581-1586` **状态门在最前**：队列行 `status ∈ {failed, needs-clarification}` ⇒ 直接
    `("no-verdict", status, None, None)` —— **不读任何源文件**。
  - `:1593-1594` 无任何可读候选源 ⇒ `no-verdict`。
  - `:1616-1618` 否则交 `_l3_resolve_source`。
  ⇒ 现有 6 个真例全部在 `:1585-1586` 就短路成 `no-verdict`，**新指纹必须挂在这个状态门之前/之外**。
- **`l3-no-verdict` 事件发射点**：`_verify_loop` 的 `:1888`（`if verdict == "no-verdict":`）→
  `:1893-1896` `st.timeline.append("l3-no-verdict", key=key, detail=f"l3-a{used} worker status={worker_status} → re-review")`。
  语料实测的 detail 正是 `l3-a3 worker status=failed → re-review`（F5 复算命令）。
- **provenance guard**：`_PROVENANCE_FILENAME = "l3-verdict-provenance.json"`（`:1510`）；
  `_l3_provenance_record`（`:1620-1713`，用同轮 `trace.log` mtime 做锚、slack 60s，`suspect ∧ raw=meets ⇒ below`）；
  `_persist_l3_provenance`（`:1715-1770`，append-only、按 `task_key` 去重、tmp+`os.replace`、坏 sidecar 不覆盖）。
  调用点在 `_verify_loop` `:1916-1920`。注意：**无裁决（`l3_source is None`）时 provenance 记录不写**（`:1915` 条件），
  所以中止轮目前在 provenance 面上**零痕迹**。
- **终态派生物**：`_persist_l3_verdict`（`:928-975`）写 `<key>/l3-verdict.txt`（值域仅 meets|below，`:926`）
  与 `<key>/l3-report.md`，并在 timeline 记 `config` 事件 `l3-verdict <before> -> <after> (report from <round>...)`（`:965`）。

### F3 轮次预算 / loop·attempt / `mark_stalled` 接线 —— 「自动重掷」的挂点

- **轮次计数**：`rounds = state.used_rounds(_all_workers_dirs(project_root))`（conductor `:247`），
  实现 `state.py:224-249` —— 按 task.md 的 `loop:`/`attempt:` 标签对 `loop` 去重计数
  （dispatch 写标签：`dispatch.py:359-360`）。声明性、无私有状态，conductor 重启不丢。
- **L3 预算**：`_verify_loop` `:1857-1859`
  `l3_budget = max(1, cfg["round_budget"])`、`l3_limit = l3_budget + _resume_credits(...)`、`used = rounds.get(f"l3:{key}", 0)`。
  默认 `round_budget = 2`（`config.py:60`，区间 `:82`）；人工批准一个 stalled gate 给**每个**受该 key 约束的回路各 1 轮
  （`_resume_credits` `:2660-2681`，credit 一次性、单调消耗）。
- **现有「自动重掷」其实已存在，只是无分类**：`verdict == "no-verdict"` 分支
  `:1897`（`if used >= l3_limit:` 才 stalled）否则 `:1907-1912` 直接重派 `l3-a{used+1}`。
  ⇒ 「重掷动作」无需新造；缺的是 ①`l3-aborted` 分类 ②不把中止算进共享轮预算的**专用有界计数**。
- **`mark_stalled`**（`:4709-4790`）：写 roadmap key-status=stalled + 建 `stalled` gate（`machine_fields` 带
  `reason_code/loop/used_rounds/round_limit/credits_used`，`:4744-4759`）+ achieved.md 草稿 + pattern 文件。
- **reason_code 是闭集**：`STALL_REASON_CODES`（`:4891-4904`，12 项，含 `l3-no-verdict` `:4898`）、
  `REASON_CODES`（`:4925-4927`）。测试钉死长度：`test_autopilot_auto_decision.py:301`（`len(...) == 12`）。
- **残留闭环**：`_recompute_l3_stall_code`（`:5348-5373`）会从磁盘重算 stall 原因码；
  对中止轮它仍会返回 `l3-no-verdict`（`:5369-5370`，因状态门先给出 no-verdict）。
  ⇒ 若只加新事件而不改重算映射，gate 的 `reason_code` 与 `cause_class` 会判成 `stalled-reason-drift`（`:5036-5041`）。
- **可挂点建议（供 DESIGN）**：指纹计算放在 `_l3_round_verdict` 的状态门（`:1585`）**之前**；重掷决策放在
  `_verify_loop:1888` 的 no-verdict 分支内、用独立 loop 标签（如 `l3abort:{key}`）或独立计数字段承载
  —— 这样 `state.used_rounds` 天然给出独立预算（与 `repair:{key}` 同族，`:2008`、`:2011`）。

### F4 三类无裁决的可观测信号矩阵（重叠 / 互斥）

信号字段逐一定位（`rows` = `_workers.parallel` 解析行；`worker.log` = 合并 stdout+stderr）：

| 信号 | 流中止（B） | 写错文件 / 载体格式不符（A） | 真 FAIL（C） | 其它失败（D：provider 报错/超时） |
|---|---|---|---|---|
| `worker.log` 行 `stream closed before response.completed` | **有**（唯一指纹） | 无 | 无 | 无 |
| 队列行 `status` | failed（`launcher.py:799-800`） | done | done | failed |
| `worker.log` 行 `[worker] done exit=0` | 有（会误导） | 有 | 有 | 视路径（D 实测也有，见 F5） |
| `trace.log` `[END] exit=` | 0（worker-mode 逻辑码） | 0 | 0 | 0（D 也 0） |
| `output.md` 两节 | 缺（占位 260-582 B） | 缺（占位）或散文 | **齐备** | 缺（如 181 B） |
| `output.md`/`report.md` FAIL 标记行 | 无 | 无 | **有**（`_l3_fail_marker_line`） | 无 |
| `report.md` 存在且合格 | 无（6/6 不存在） | **有**（24/27 合格） | 有 | 无 |
| `l3-verdict-provenance.json` 记录 | 无（无源 ⇒ 不写） | 有（源存在时才写） | 有 | 无 |
| timeline 事件 | `l3-no-verdict`（`:1893`） | `l3-no-verdict` 或 below 路径 | 走 below/repair 路径 | `l3-no-verdict` |

- **互斥核心**：`stream closed` 行是 B 的**充分且必要**新增指纹；语料里它与「两节齐备」0 重叠、
  与 FAIL 标记 0 重叠、与 `status=done` 0 重叠。
- **重叠风险（必须靠指纹拆开）**：
  1. A 与 B 在「output.md 缺两节 + exit=0 行」上**完全重叠** —— reflect 里
     `l3-verdict-source-mismatch.md` 与 `l3-reviewer-stream-abort.md` **各自把同一批轮次
     （`feature-inline-marker-patchkit` l3-a1/a2）算作自己的根因**；`stream closed` 行是唯一判别器
     （这两轮实际都有该行 ⇒ 属 B 而非 A）。
  2. B 与 D 在「队列 status=failed + output.md 缺两节」上重叠；判别器同为 `stream closed` 行
     （D 的实测文本是 `OpenAI API error (403): ...`，见 F5）。
  3. 真 FAIL（C）与 A 的差别是「源里是否有 FAIL 标记行」；C 与 B 不重叠（C 两节齐备且有标记）。
- **一类新发现（不是上述三类，但会误判为 below）**：reviewer 把结论写成**无节标题的 report.md**
  （编号章节 `## 0. ...` + 最终消息散文），既无 `## Quality Gate Report`/`## Achieved`，也无 FAIL 行
  ⇒ 现行 `_l3_resolve_source` 判 `below`（源为 None）。实例：`FeatureMigrator/gui-monitor-hitl-e2e l3-a3`
  （2026-10-09，本日）。AC-002 的「三类」在语料里其实至少是 **四类**，建议 DESIGN 明确该类归属
  （既非 aborted，也不该算真 FAIL）。

### F5 真实语料：正负双穷举（E2Feature + FeatureMigrator）

- 扫描范围：`H:\git\E2Feature\.agenticdoc` 与 `E:\CLI_workspace\FeatureMigrator\.agenticdoc`；
  「L3 轮」定义 = 目录名匹配 `-l3-a\d+$`。
- **总 L3 轮 = 54**（E2Feature 31 + FeatureMigrator 23）。全项目 `worker.log` 文件总数 = **844**（快照 2026-10-09T16:51；该目录为活语料，计数随新 spawn 漂移）。
- **正例（含 `stream closed`）= 6**，且 **6/6 同时满足**：队列 status=failed、output.md 缺两节、
  无 FAIL 标记、同轮无合格 `report.md`：

| # | key | 轮次 | output.md | 队列 status | worker.log 末行 |
|---|---|---|---|---|---|
| 1 | `feature-inline-marker-patchkit` | `l3-a1` | 272 B | failed | stream closed… |
| 2 | `feature-inline-marker-patchkit` | `l3-a2` | 582 B | failed | stream closed… |
| 3 | `feature-gui-time-mvp-board` | `l3-a1` | 272 B | failed | stream closed… |
| 4 | `feature-gui-time-mvp-board` | `l3-a4` | 465 B | failed | stream closed… |
| 5 | `feature-false-meets-remediation` | `l3-a3` | 470 B | failed | stream closed… |
| 6 | `feature-false-meets-remediation` | `l3-a4` | 260 B | failed | stream closed… |

  - 6/6 都是 `type=reviewer`（L3），**非 L3 轮 0 命中**（844 个 worker.log 中仅此 6 个含该行）。
  - reflect note 写「累计 7 例」；**实测 6 例**（reflect 表 5 行 + 追加表新增 1 行 = 6；第 7 例无文件依据）。
  - 该字符串只出现在 `worker.log`（6）、`gates/gate-0016.md`、`gate-0017.md`、`gate-0018.md`（人工闸门 note）
    与 reflect note；`trace.log` / `output.md` **零命中**。
- **负例穷举（必须保持 0 假阳性）= 48 轮**，其中：
  - **21 轮两节齐备**（含 FAIL 与 meets）——按「缺两节」或「体积小」的任何粗糙判据都会误伤。
  - **24 轮** output.md 缺两节但同轮 `report.md` 合格（经典 A 类；现行回退后判 meets）。
  - **1 轮** `report.md` 存在但**不合格**（无节标题散文，见 F4）⇒ 判 below。
  - **2 轮** `feature-params-service l3-a1/a2`：output.md 181 B、队列 failed、**无 stream 行**、
    无 report；worker.log 第 4 行是 `OpenAI API error (403): {"message":"...模型不存在..."}`（错误 model id `gpt-5.6.sol`），
    `tools=0`、0 s 结束。这是 D 类（配置/鉴权瞬败），**必须不被 `l3-aborted` 命中**。
- **可复算命令**（PowerShell；只读）：
  - 命中行清单：
    `Get-ChildItem -Recurse -Filter worker.log -Path H:\git\E2Feature\.agenticdoc, E:\CLI_workspace\FeatureMigrator\.agenticdoc | Select-String -SimpleMatch "stream closed before response.completed" | ForEach-Object { "$($_.Path):$($_.LineNumber)" }`
  - 计数与分类交叉表：见 §6 的两段 Python（只读）。
- **timeline 侧**：`l3-no-verdict` 事件在 E2Feature timeline 共 6 条（`timeline.jsonl.2`），
  detail 形如 `l3-a3 worker status=failed → re-review`；FeatureMigrator timeline 0 条。
  **marker 两轮没有该事件**（该事件在 2026-09-25 的 `feature-l3-verdict-source-fallback` 之后才存在），
  说明「分类缺失」在历史上比事件更早。

### F6 TS 侧读取面与镜像同步需求

- TS 侧（`packages/coding-agent/src/extensions/agent-team-loop/autopilot/{status-model,monitor,console}.ts`）
  **不读** `worker.log` / `output.md` / `report.md`：全文件 grep 仅命中 `verdicts_final`（来自 gate frontmatter）
  与 timeline 事件词汇，无 `worker.log`/`output.md` 字面量。
- **timeline 词汇是跨语言闭集且被集合相等测试锁定**：
  `timeline.py:67-96`（`EVENT_TYPES`，`:84` 为 `l3-no-verdict`）与
  `status-model.ts:962-988`（`EVENT_TYPES`，`:978` 为 `l3-no-verdict`）；
  判据 = 集合相等（`packages/coding-agent/test/suite/autopilot-event-parity.test.ts:76-99`，两侧差集都必须为空）。
  ⇒ 若 `l3-aborted` 作为**新 timeline 事件**，必须**两侧同时**加入，否则 parity 测试红 / console 默认视图吞掉。
- **gate `reason_code` 在 TS 侧是透传**：`status-model.ts:894`（`reasonCode: optional("reason_code")`）、
  `monitor.ts:108-109,226,782-783`、`console.ts:409` —— **无闭集校验**。
  ⇒ `l3-aborted` 若作为 gate reason_code，**只需改 Python**（`STALL_REASON_CODES` + `_recompute_l3_stall_code`），
  TS 面板/console 自动显示；但 `test_autopilot_auto_decision.py:301` 的 `== 12` 断言要同步。
- **gate frontmatter**：`_REQUIRED_FIELDS` 冻结为 6（`gates.py:138-144`），`reason_code` 是可选 v2 字段（`:102`）
  ⇒ 新增原因码不触 `_REQUIRED_FIELDS`（满足 spec AC-013 的「一格不加」）。

## 4 结论 → 决策映射

1. **AC-001 判据需修正措辞**：`done exit=0` 只能指 `worker.log` 的 `[worker] done exit=0` 行；
   队列行 status 同轮必为 `failed`（F1）。判据三要素 = `worker.log` 含子串 `stream closed before response.completed`
   + `output.md` 缺两节 + 该行存在（**不**要求 `status=done`）。→ 直接决定 AC-001/AC-002 的判据文本与夹具。
2. **指纹挂点必须是状态门之前**：`_l3_round_verdict` 的 `:1585-1586` 会先短路（F2）。
   实现应在该函数内、状态门之前做 aborted 检测；注意当前 `_l3_round_verdict` 并不读 `worker.log`，
   design 需明示新增读取及其成本（spec §2.2 的「零额外读取」目前对它是**不成立**的前提）。
3. **自动重掷挂点已存在**：`_verify_loop:1888` 的 no-verdict 分支已在重派（F3）。
   需要新增的是 ①`l3-aborted` 专用分类 ②专用有界计数（建议独立 loop 标签，复用 `state.used_rounds`）
   ③`STALL_REASON_CODES`/`_recompute_l3_stall_code` 同步，避免 `stalled-reason-drift`（F3 末）。
4. **互斥性可在语料上机械验收**：B 的指纹与 A/C/D 的判据在 54 轮上 0 重叠（F5）；
   AC-002 的「各命中且仅命中一类」有了可复算的语料基线（正 6 / 负 48）。
5. **镜像面最小化**：timeline 事件需两侧同步（F6）；reason_code 仅 Python。
6. **新发现的第四类（无节标题 report.md）应写进 SPEC 边界**：否则 AC-002 的「三类」与实际语料不符（F4）。

## 5 数据缺口与风险

- 中止字符串的**逐字节出处**无法在本仓定位（F1）：当前树无该字节序的抛出点，语料来自网关/旧构建。
  指纹用子串匹配可覆盖，但 DESIGN 不应断言「该文本由 pi 产生」。
- 未验证「换 review 模型后是否再出现」的持续观察（reflect 的下一步判据），本轮只做只读语料，未重跑。
- 语料计数依赖目录名 `-l3-aN`（项目约定）；若未来 L3 轮命名改变，计数脚本需同步。
- `FeatureMigrator` 的 `gui-monitor-hitl-e2e l3-a3` 是快照当天的活样本，说明第四类问题**未冻结**。
- E2Feature 的 timeline 已轮转（`.1`/`.2`），跨轮转计数需三文件合计；`l3-no-verdict` 6 条全在 `.2`。

## 6 复算脚本（只读）

```python
# 计数：worker.log 命中 'stream closed' 的轮次类型
from pathlib import Path
import re
ROOTS = [Path(r"H:\git\E2Feature"), Path(r"E:\CLI_workspace\FeatureMigrator")]
tot = hits = 0
for root in ROOTS:
    for p in (root / ".agenticdoc").glob("*/workers/*/worker.log"):
        tot += 1
        if "stream closed" in p.read_text(encoding="utf-8", errors="replace"):
            hits += 1
            print(p.parent.name)
print("worker.log total:", tot, "hits:", hits)
```

```python
# 分类交叉表：output.md/report.md 节标题 + FAIL 标记 + _workers.parallel status
from pathlib import Path
import re
ROOTS = [Path(r"H:\git\E2Feature"), Path(r"E:\CLI_workspace\FeatureMigrator")]
ROUND = re.compile(r"-l3-a\d+$")
FAIL = re.compile(r"\|\s*\**\s*FAIL\b")

def secs(t):
    return sum(l.strip() in ("## Quality Gate Report", "## Achieved") for l in t.splitlines()) == 2

status = {}
for r in ROOTS:
    wp = r / ".agenticdoc" / "_workers.parallel"
    if wp.is_file():
        for line in wp.read_text(encoding="utf-8", errors="replace").splitlines():
            p = [x.strip() for x in line.split("|")]
            if len(p) >= 2:
                status.setdefault((r.name, p[0]), p[1])

n = 0
for r in ROOTS:
    ad = r / ".agenticdoc"
    if not ad.is_dir():
        continue
    for wd in ad.glob("*/workers"):
        for td in wd.iterdir():
            if not td.is_dir() or not ROUND.search(td.name):
                continue
            n += 1
            wt = (td / "worker.log").read_text(encoding="utf-8", errors="replace") if (td / "worker.log").is_file() else ""
            ot = (td / "output.md").read_text(encoding="utf-8", errors="replace") if (td / "output.md").is_file() else ""
            rt = (td / "report.md").read_text(encoding="utf-8", errors="replace") if (td / "report.md").is_file() else ""
            print(status.get((r.name, td.name), "?")[:6], "stream" if "stream closed" in wt else "  -   ",
                  "O2" if secs(ot) else "o0", "R2" if secs(rt) else "r0",
                  "FAIL" if FAIL.search(ot) else "    ", td.name)
print("l3 rounds:", n)
```

[VERIFY] RQ-1: corpus_l3_rounds=54(E2Feature=31,FeatureMigrator=23) worker_log_scanned=844(snapshot 2026-10-09T16:51) stream_closed_rounds=6(all L3,all status=failed,all output.md missing both sections,0 with both sections,0 with FAIL marker) non_L3_hits=0 non_stream_missing_sections=27(report_qualifying=24,prose_report=1,provider_403=2) both_sections_controls=21 reroll_branch=conductor.py:1888 fingerprint_must_precede=conductor.py:1585 l3_limit=round_budget(2)+resume_credits stream_string_source=not_in_tree(provider/gateway) retry_classifier_miss=retry.ts:26-80 timeline_event=l3-no-verdict(conductor.py:1894) event_vocab=timeline.py:84+status-model.ts:978 parity=set-equality(tests/suite/autopilot-event-parity.test.ts) reflect_claimed=7 measured=6 e2_events=6 fm_events=0 HEAD=10446aefb