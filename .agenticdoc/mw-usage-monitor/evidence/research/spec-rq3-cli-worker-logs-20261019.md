# Spec-time research (RQ3): codex / claude CLI worker 会话日志的 token 可统计性与归因

- Key: mw-usage-monitor / T-RQ3-cli-worker-logs · Date: 2026-10-19 · Type: research（只读）
- 方法：全部结论来自本机实测（Python 3.14.3 扫描 `~/.codex`、`~/.claude`、`~/.pi`，只读）+ 本机 `--help` 实测（codex-cli 0.147.0、Claude Code 2.1.250）。未发起任何真实 LLM 调用，未修改仓库与 `~/.codex`/`~/.claude`/`~/.pi` 任何文件。
- 机器：Windows，`HOME=C:\Users\wenbozhou`，当前时间 2026-10-19 17:47 (+08:00)。

## 结论

本机 codex/claude 会话日志**存在、含 token 字段、可低成本解析**（全量 275.8 MB + 358.3 MB，实测解析 0.46 s + 1.06 s），但**归因能力不对称**：claude 支持 `--session-id <uuid>` 可精确到文件，codex exec 0.147.0 无 session-id 参数，只能靠「cwd + originator=codex_exec + 首条 user_message 含 task.md 绝对路径 + 文件创建时间窗」组合信号；且本机至今 **0 条** codex/claude mw-worker 运行日志，worker 归因无法端到端实测。口径上 codex `input_tokens` 含 cache、pi/claude 不含，必须换算后才能同表记账。因此推荐：pi + PM 窗口为主口径，codex/claude 走「台账登记 session → 精确读文件」，读不到即显式降级为 `unknown_cli`/「未统计」行。

## 0. 结论先行

1. **日志存在**：`~/.codex/sessions` 124 个 rollout jsonl / 275,770,428 B（2026-04-14 ~ 2026-08-22）；`~/.claude/projects` 294 个 jsonl / 358,323,344 B（2026-07-28 ~ 2026-08-28）。**最近 7 天两者均为 0 文件 0 字节**（最后活动分别为 08-22 / 08-28，今天 10-19）。`~/.codex/history.jsonl`（190,024 B，prompt 历史，无 token）、`~/.codex/config.toml`（4,585 B）存在；`~/.claude/history.jsonl`（899,751 B，prompt 历史）存在；**`~/.claude/todos` 与 `~/.claude/statsig` 不存在**。
2. **token 字段可机器解析**：codex 在 `event_msg/token_count` 的 `info.total_token_usage{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens, total_tokens}`，取每文件**最后一条**累计值即可（事件成对重复：单文件 2,508 事件中 1,252 对完全重复，对 `last_token_usage` 直接求和会 2 倍）；claude 在 assistant 行 `message.usage{input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens, output_tokens_details.thinking_tokens}`，**必须按 `message.id` 去重**（实测同一条消息写 2–4 行，行数/去重后比 1.41–1.87×），无 total 字段需自加。
3. **归因**：claude `--session-id <uuid>`（2.1.250 `--help` 原文 "Use a specific session ID for the conversation (must be a valid UUID)"）→ 可精确到 `~/.claude/projects/<cwd-slug>/<uuid>.jsonl`；codex exec **无** session-id/输出目录参数（0.147.0 `codex exec --help` 全文核过，只有 `resume` 子命令与 `--ephemeral` 反向开关）→ 四信号组合归因（§3）；pi 侧已有 `--session`/`--session-id`/`--session-dir`（RQ0 F-2）。
4. **口径不可直通**：codex `input_tokens` 是含 cache 的总输入（实测 29,522 条 usage 记录 100% 满足 `input ≥ cached+cache_write`；`total_tokens = input+output` 在 99.68% 记录成立），pi/claude 的 input 不含 cache → 同表前必须做 `codex_uncached_input = input_tokens − cached_input_tokens − cache_write_input_tokens` 换算；`totalTokens` 两边定义不同，分项记账。
5. **扫描成本**：全量 usage 行解析实测 codex 0.46 s / claude 1.06 s / pi 12.31–12.66 s（pi 4,079 文件 2.68 GB，比 RQ0 时又长了）；最近 7 天 codex+claude 均为 0。**建议不做每次全量扫**：台账登记的 session 精确读（pi/claude 单文件、codex 单 rollout），全量扫描只作低频兜底。
6. **退路必须显式**：本机 codex/claude 日志中 mw worker 特征（starter "Read your task file at <task.md>"）命中 **0** 条 → worker 归因管线无端到端实测样本；`mw stats` 对未归因的 CLI worker 必须输出 `unknown_cli`/「未统计」行，禁止把「pi+PM 之和」当全量呈现（§6）。

## 证据

### 1. 本机 CLI 日志存在性

命令：Python `os.walk` + `os.stat`（实测，命令全文见 progress 记录；数值为原始输出）。

| 位置 | 文件数 | 总字节 | mtime 跨度 |
| --- | --- | --- | --- |
| `~/.codex/sessions/**/*.jsonl` | 124 | 275,770,428 | 2026-04-14 15:09:20 ~ 2026-08-22 15:58:43 |
| `~/.claude/projects/**/*.jsonl` | 294 | 358,323,344 | 2026-07-28 16:27:24 ~ 2026-08-28 21:05:04 |
| `~/.pi/agent/sessions/**/*.jsonl`（对照） | 4,079 | 2,684,479,887 | —（最近 7 天 1,006 个 / 911,354,298 B） |

- codex sessions 目录树：`sessions/2026/<MM>/<DD>/rollout-<ISO时间戳压缩>-<uuid7>.jsonl`，如 `sessions/2026/08/22/rollout-2026-08-22T15-58-43-01a0287a-ade3-7293-977e-7ff29337a34d.jsonl`（22 行，131,062 B）。单日最多 34 个文件（2026-08-13）。
- codex 根目录相关文件（`os.listdir` 实测）：`history.jsonl`（190,024 B，首行 `{"session_id":"019d89f7-...","ts":1776136247,"text":"hi"}` — 仅 prompt 历史，无 token）、`config.toml`（4,585 B）、`auth.json`、`log/`（空）、`sandbox.*.log`、`logs_2.sqlite` 等。任务书提到的 `history` **目录**不存在，实际是 `history.jsonl` 文件。
- `~/.claude` 根文件（实测）：`history.jsonl` 899,751 B（prompt 历史）、`settings.json`、`daemon.log` 42,451 B、`.last-cleanup`、`mcp.json` 等；`projects/` 14 个项目目录。
- **不存在（实测 `os.path.isdir` → False）**：`~/.claude/todos`、`~/.claude/statsig`。
- claude 项目目录名 = cwd 的 slug（`\` 与 `:` → `-`）：`H--git-Multi-Workers` ↔ `H:\git\Multi-Workers`、`E--CLI-workspace-claude-hook` ↔ `E:\CLI_workspace\claude-hook`，文件名 = `<sessionId>.jsonl`。

### 2. 日志 schema 与 token 字段

#### 2a. codex（rollout jsonl）

行类型直方图（`sessions/2026/08/22/rollout-...-01a0287a-....jsonl`，22 行实测）：
`response_item/message:7 · response_item/reasoning:2 · event_msg/agent_message:2 · event_msg/token_count:2 · session_meta:1 · event_msg/task_started:1 · world_state:1 · turn_context:1 · event_msg/user_message:1 · response_item/custom_tool_call:1 · response_item/custom_tool_call_output:1 · event_msg/agent_reasoning:1 · event_msg/task_complete:1`

- 第 1 行 `session_meta`（截断脱敏样本）：`{"timestamp":"2026-08-22T07:58:44.158Z","type":"session_meta","payload":{"session_id":"01a0287a-ade3-7293-977e-7ff29337a34d","timestamp":"2026-08-22T07:58:43.859Z","cwd":"E:\\UEMigrator","originator":"codex_exec","cli_version":"0.147.0","source":"exec","thread_source":"user","model_provider":"TiMiAIHub",...}}`
- token 样本 1（同文件，真实原始行，截断）：`{"timestamp":"2026-08-22T07:58:52.684Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":15211,"cached_input_tokens":0,"cache_write_input_tokens":15208,"output_tokens":219,"reasoning_output_tokens":124,"total_tokens":15430},"last_token_usage":{"...同结构...},"model_context_window":243200},"rate_limits":{...无金额字段...}}}`
  解析：该次 API 调用 input 15,211（含 cache_write 15,208）、output 219（含 reasoning 124）、total 15,430 = 15,211+219。
- token 样本 2（第二次调用）：`total_token_usage={input_tokens:31956, cached_input_tokens:15208, cache_write_input_tokens:16742, output_tokens:308, reasoning_output_tokens:197, total_tokens:32264}`，`last_token_usage={input_tokens:16745, cached_input_tokens:15208, cache_write_input_tokens:1534, output_tokens:89, ...}`。解析：`16745 = 15208+1534+3` → **input_tokens 含 cache 读+写**；`total = input+output`。
- `turn_context` 行带 `model:"gpt-5.6-sol"`、`cwd`、`turn_id`（每 turn 一条）。

**粒度判定**（全语料实测）：`token_count` 事件 14,877 个 vs `task_started`（turn）1,019 个 → 一次 turn ≈ 14.6 次 API 调用；`token_count.info.last_token_usage` = 单次 API 调用增量，`total_token_usage` = 文件内累计（实测累计值单调不减：最大文件 2,508 事件 0 次回落）。**但事件成对重复**：最大文件 2,508 事件中 1,252 对相邻行完全相同 → 正确读法是「取文件最后一条非空 `total_token_usage`」或「相邻去重后求和 `last_token_usage`」；首个事件可能 `info:null`（实测 line 7），需跳过。

**换算不变量**（全语料 29,522 条 usage 记录实测）：`input ≥ cached_input_tokens + cache_write_input_tokens` 违反 **0** 条；`total_tokens == input+output` 违反 95 条（0.32%，`total` 字段偏大或偏小的 provider 记账差异，样例 `input=1007,cache_write=1004,output=51,total=1058` 形态）→ total 字段可信度略低于分项。

**重试/子 agent/续会话**：重试同文件内多次 `token_count`（已含在累计里）；子 agent **另起文件**——124 文件中 38 个 `session_meta.thread_source:"subagent"`（`thread_source` 直方图：user 56 / subagent 38 / None 32）；`originator`：codex-tui 110 / Codex Desktop 11 / codex_exec 5。`codex resume` 产生**新文件、同 session_id**：124 文件仅 54 个不同 session_id，10 个 id 出现在 >1 个文件（最多 1 个 id 分布在 19 个文件）→ 按 session_id 去重会错，按文件聚合才对；mw 每次 spawn 是新 `codex exec`，天然单文件。

#### 2b. claude（projects jsonl）

行类型直方图（`projects/H--git-Multi-Workers/0fd83ff3-....jsonl` 实测）：`user:139 · assistant:320 · mode:36 · permission-mode:36 · file-history-snapshot:6 · atis-latch:36 · attachment:10 · last-prompt:35 · file-history-delta:7 · system:10`。每行带 `sessionId`、`cwd`（会话中途可变，实测出现 `H:\git\Multi-Workers` 与 `H:\git\Multi-Workers\packages\multi-workers`）、`version:"2.1.238"`、`gitBranch:"dev/AgentTeam"`。

- assistant usage 样本（真实，截断）：`{"type":"assistant",...,"message":{"id":"msg_bdrk_ajawn3asxd35fyhzagcxshkl5h3dgyfjbfqmwuulz2eyrmlm6ysq","model":"claude-opus-4-8","usage":{"input_tokens":2,"cache_creation_input_tokens":54546,"cache_read_input_tokens":0,"output_tokens":608,"output_tokens_details":{"thinking_tokens":357},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":54546},...}}}`。解析：非缓存 input 仅 2，cache 写 54,546（其中 1h 档 0），cache 读 0，output 608（含 thinking 357）；**无 total 字段**；本样本行中**无 cost/美元字段**。
- **同一条消息重复写多行**：上例同一 `message.id`（`msg_bdrk_ajaw...`）在同一文件出现 ≥3 行、usage 数值相同（时间戳 08:14:04.609/.610/.614）。去重实测（两个最大文件）：assistant usage 行 5,251 → 唯一 id 2,804（比 1.87×）；5,316 → 3,760（1.41×）；抽查重复行 usage 数值差 0 → 按 id 去重取首/取末等价。不去重直接求和会虚增 1.4–1.9×。
- 子 agent **另起文件**：`<sessionId>/subagents/agent-<hash>.jsonl` + 同名 `.meta.json`（实测样例 `{"agentType":"fork","isFork":true,"description":"Review relay/proxy changes for proxy-timeout-reconnect","toolUseId":"toolu_bdrk_01R7p9...","spawnDepth":1}`）；全语料 171 个 subagent jsonl，**全部**含 assistant usage 行；其行内 `sessionId` = 父会话 id、`isSidechain:true`。另有旧式内联形态：全语料 8,333 行 `isSidechain:true` 直接写在主会话文件里。**抽样核重叠**（`eeaef714` 主文件 692 唯一 id vs 其 subagents 文件 11 id：交集 0；`fe13b40b` 主文件 0 条内联 sidechain）→ 两种形态目前互斥，但实现时应按 `message.id` 全局去重兜底。
- `~/.claude/history.jsonl` 为 prompt 历史（无 usage 字段），不参与统计。

### 3. 归因方式（能否把会话文件对应到一次 mw worker 运行）

mw 侧发射事实（已复核）：

- `packages/multi-workers/launcher.py:1764` `_build_command`：codex → `["codex","exec","-m",<model>,"<starter>"]`（`:1801`）；claude → `["claude", ("--model",m), "-p","<starter>"]`（`:1803-1807`）；均无 session-id、无输出目录参数。
- `launcher.py:1721,1738` `_starter_prompt`：starter 以 `Read your task file at <task.md 绝对路径> and execute it end-to-end...` 开头（claude/codex 靠读 task 文件获取任务体，`:1731-1734` 注释）。
- `launcher.py:2444,2450`：`Popen` 列表参数，`cwd = _worker_cwd(...)`（项目/分区目录），stdout+stderr 重定向进任务 `worker.log`。

三种 CLI 的 session 固定能力（`--help` 本机实测）：

| CLI | 版本 | 固定 session id | 输出目录 | 证据 |
| --- | --- | --- | --- | --- |
| pi | （RQ0 F-2） | ✅ `--session`/`--session-id`/`--session-dir` | ✅ session-dir | `packages/coding-agent/src/cli/args.ts:108,110,114` + `PI_CODING_AGENT_SESSION_DIR`（config.ts） |
| claude | 2.1.250 | ✅ `--session-id <uuid>`（"must be a valid UUID"） | ❌（落盘位置由 cwd slug 决定，无目录参数） | `claude --help` 原文；另有 `--no-session-persistence`、`-r/--resume`、`--fork-session` |
| codex | 0.147.0 | ❌（`codex exec --help` 全文无 session-id/session 参数；`resume` 子命令是续会话不是指定 id） | ❌（`CODEX_HOME` 环境变量可挪整个 home，但无 per-run 日志目录参数） | `codex exec --help` 全文；反向开关 `--ephemeral`（"Run without persisting session files to disk"）、`--json`（"Print events to stdout as JSONL"）、`-o/--output-last-message <FILE>` |

codex 归因四信号组合（全部字段实测存在）：

1. `session_meta.cwd` == worker cwd（`session_meta` 与 `turn_context.cwd` 双处记录）；
2. `session_meta.originator == "codex_exec"`（本机 124 文件中仅 5 个，区分度极高——TUI/Desktop 是用户交互）；
3. 首条 `event_msg/user_message` 含 mw starter 特征 `Read your task file at <task.md 路径>`，内含 task_key 目录 → 可提 task_key；
4. 文件 mtime/session_meta.timestamp 落在 `[spawn_start, spawn_end]`。

实测限制：本机 5 个 `codex_exec` 文件里 **0 个**是 mw worker（2 个 `Say exactly: ok` 冒烟、2 个 `say hello`、1 个 `type: codex`）；全语料搜 `Read your task file at` 命中 0。claude 侧同理 0 命中（70 个主会话提到 `.agenticdoc` 均为用户手动粘贴的 review 请求）。即：**归因规则无法在本机用真实 worker 样本回测**，只能做到「字段存在性已验证」。

codex 备选硬化手段（列为选项，未实测）：launcher spawn 前后对 `~/.codex/sessions/<Y>/<M>/<D>/` 做文件名快照 diff，新增文件即该次运行；或给 codex 加 `--json` 让事件流（含 token_count）进已捕获的 `worker.log`（`launcher.py:2434-2439` 已重定向 stdout）——两条路都不需要 codex 支持 session-id。claude 侧 launcher 直接生成 uuid 传 `--session-id` 并写入台账，扫描时精确打开 `projects/<slug>/<uuid>.jsonl`（子 agent 用量在 `<uuid>/subagents/`，同 key 可并账）。

保守策略：四信号不满（如 cwd 匹配但 originator 不是 codex_exec、或时间窗重叠多个候选）→ 不猜，计入 `unknown_cli`/`unattributed` 桶，宁可少报不虚报。

### 4. 与 pi 侧的统一口径

pi `Usage` 定义：`packages/ai/src/types.ts:364-385`（`input/output/cacheRead/cacheWrite`、`cacheWrite1h?`、`reasoning?` 为 output 子集、`totalTokens`）；Anthropic 通道 `totalTokens = input+output+cacheRead+cacheWrite`（`packages/ai/src/api/anthropic-messages.ts:584-585`），即 **pi 的 `input` 不含 cache**。

对照表（token 字段级）：

| 语义 | pi usage | claude `message.usage` | codex `total_token_usage` |
| --- | --- | --- | --- |
| 非缓存输入 | `input` | `input_tokens`（1:1，样本 2） | `input_tokens − cached_input_tokens − cache_write_input_tokens`（需减法换算） |
| 输出 | `output` | `output_tokens`（1:1） | `output_tokens`（1:1） |
| 缓存读 | `cacheRead` | `cache_read_input_tokens`（1:1） | `cached_input_tokens`（1:1） |
| 缓存写 | `cacheWrite` | `cache_creation_input_tokens`（1:1） | `cache_write_input_tokens`（1:1） |
| 缓存写(1h 档) | `cacheWrite1h?` | `cache_creation.ephemeral_1h_input_tokens` | ❌ 无（单档） |
| 推理 token | `reasoning?`（output 子集） | `output_tokens_details.thinking_tokens`（output 子集） | `reasoning_output_tokens`（output 子集） |
| 总量 | `totalTokens`=四分量和 | ❌ 无，需四分量自加 | `total_tokens`=input+output（input 已含 cache，99.68% 成立） |
| 每文件去重 | 不需要（逐 assistant 行带 usage，见 RQ1） | **按 `message.id` 去重** | 取最后一条累计值，不求和 |

不可对齐项清单：

1. `total_tokens` 定义不同：codex 的 total 已含 cache；pi/claude 的 total 是「非缓存 input + output + cacheRead + cacheWrite」。直接比 total 会系统性偏大 codex（agent 长会话下 cache 占比 >97%，实测样本 54,546/54,548）。
2. claude 无 total 字段；codex total 有 0.32% 记录不满足 `input+output`。
3. codex 缺 1h 缓存档拆分；pi/claude 有 `cacheWrite1h`/`ephemeral_1h`。
4. reasoning/thinking 在三家都是 output 子集（pi types.ts:375-377 注释、claude `thinking_tokens`、codex `reasoning_output_tokens`），可以单独记列，但**不可加回 output**。
5. claude 抽样中无 cost 字段、codex `rate_limits` 无金额字段 → 与既定决策「只报 tokens 不算钱」一致，无冲突。
6. 结论：**台账按 5 分项（input_uncached / output / cacheRead / cacheWrite / reasoning）+ 每 CLI 原始字段分列存储**，`mw stats` 汇总时先归一到 pi 口径再相加；不要在扫描层强行合并 total。

### 5. 扫描成本（实测）

命令：Python 逐文件逐行扫 + 命中行 `json.loads`，`time.perf_counter` 计时（热缓存二次运行，两轮结果都列）：

| 语料 | 文件数 | 字节 | usage 行 | 解析耗时 |
| --- | --- | --- | --- | --- |
| codex 全量（marker `"token_count"`） | 124 | 275,770,428 | 14,877 | 0.46 s / 0.47 s |
| claude 全量（marker `"usage"`） | 294 | 358,323,344 | 57,789 | 1.06 s / 1.05 s |
| pi 全量（marker `"totalTokens"`） | 4,079 | 2,684,479,887 | 289,090 | 12.66 s / 12.31 s |
| codex 最近 7 天 | 0 | 0 | 0 | — |
| claude 最近 7 天 | 0 | 0 | 0 | — |
| pi 最近 7 天 | 1,006 | 911,354,298 | — | — |

- codex+claude 全量扫描 ≈ 1.5 s（今天），但语料随使用增长且与 worker 无关的用户会话占绝大多数（codex 110/124 是 TUI 会话）——每次 `mw stats` 全量扫既慢又会把用户自己的会话算进来（归因靠过滤，成本随语料涨）。
- **建议**：台账驱动。mw 在 spawn 时登记 (cli, session_id|候选信号, start, end)；`mw stats` 只打开台账登记的文件（单文件 KB~MB 级，毫秒级）；全量目录扫描只做 (a) codex 的时间窗+信号兜底匹配（其文件粒度小、当日目录小），(b) 低频（如每 24h）巡检补漏。pi 侧 12 s 的全量扫同理不进请求路径（与 RQ1 结论对齐）。

### 6. 退路：CLI 日志不可用/不可归因时的呈现（必须项）

规则：**宁可显示「未统计」，禁止把部分和冒充全量。** 具体：

1. `mw stats` 每个 worker 行带 `cli` 与 `attribution` 状态：`exact`（pi/claude 按 session_id 精确文件）、`inferred`（codex 四信号唯一命中）、`unknown_cli`（有 codex/claude worker 运行记录但日志找不到/匹配不唯一）。`unknown_cli` 行 token 列显示 `-`（缺省符），不显示 0，避免被加总。
2. 简报尾部固定一行覆盖声明，例如：`coverage: pi 2 workers (exact) · codex 1 worker (unattributed → 未统计) · claude none`；若没有任何 codex/claude worker 运行过，则写 `codex/claude: no worker runs`，明确「无」与「未统计」的区别。
3. 台账行在 spawn 时就写 `cli` 与归因策略；worker 结束时若扫描侧拿不到日志（文件不存在/解析失败），保留 `unknown_cli` 并在 reason 记录（如 `codex --ephemeral`、日志被清理、版本 schema 漂移），使降级可诊断。
4. 特别防呆：codex/claude 均存在「不落盘」开关（codex `--ephemeral`、claude `--no-session-persistence`，均 `--help` 实测）——mw 不得传这两个参数，且 stats 呈现必须容忍「worker 跑了但永远没有日志」的存在。

## 残留与未验证

### 未找到清单

- `~/.claude/todos`：未找到（`os.path.isdir` → False）。
- `~/.claude/statsig`：未找到（同上）。
- codex `history`（目录形式）：未找到；实际为文件 `~/.codex/history.jsonl`（190,024 B）。
- `codex exec --session-id`/`--session`（固定 session id）：未找到（`codex exec --help` 全文，0.147.0）。
- codex per-run 输出目录参数：未找到（仅 `CODEX_HOME` 全局迁移与 `--ephemeral` 反向开关）。
- claude 会话日志输出目录参数：未找到（`claude --help` 全文；位置由 cwd slug 决定）。
- 本机 codex/claude 日志中的 mw worker 运行（starter `Read your task file at`）：未找到（codex 0/124，claude 0/294）。
- codex token_count 内 cost/金额字段、claude usage 行内 `total_cost_usd`：本机样本中未出现（rate_limits 各字段均 null）。
- `~/.claude/todos`、`statsig` 之外，任务书点名的 `projects/**/*.jsonl` 均在且已解析（294 个）。

### 未覆盖面声明

- **未做真实 worker 端到端回测**（任务书禁止发起 LLM 调用）：`claude --session-id` 与 `-p` 组合的实际落盘文件名、codex 四信号在真实 worker 运行下的唯一性、`codex exec --json` 事件流内容，均只有 schema/`--help` 级证据，实现后需用一次真实 worker 运行验证（或在 PM 允许时用 faux 路径验证）。
- claude 日志由 2.1.238 写成、当前 CLI 已是 2.1.250：schema 可能漂移（本轮所有 claude 字段结论只对 2.1.238 时代文件成立）；codex `cli_version:"0.147.0"` 与当前一致。
- codex 95 条（0.32%）`total ≠ input+output` 记录的根因未查明（影响 total 字段权重，不影响分项）。
- 内联 `isSidechain:true` 行（8,333 行，多为其他项目/旧版格式）与 `subagents/` 文件互斥性只在 2 个会话上抽样验证（交集 0）；全语料按 `message.id` 全局去重未做穷举。
- pi 语料自 RQ0 F-1 的 4,065 文件又增长到 4,079（2.68 GB）；RQ1 若给出不同数值以 RQ1 实测为准。
- `~/.codex/config.toml`、`auth.json` 内容未读取（可能含凭证，统计不需要）。

## 上下文来源

- 任务书：`.agenticdoc/mw-usage-monitor/tasks/T-RQ3-cli-worker-logs.md`；RQ0 计划：`.agenticdoc/mw-usage-monitor/evidence/research/spec-rq0-research-plan-20261019.md`（F-1/F-2/F-3 引用，未重复发现）。
- mw 发射链（只读引用）：`packages/multi-workers/launcher.py:1721,1738`（starter 文本）、`:1764,1801,1803-1807`（三种 CLI 命令行）、`:2444,2450`（Popen cwd/重定向）、`:2434-2439`（worker.log 捕获）。
- pi Usage 口径：`packages/ai/src/types.ts:364-385`、`packages/ai/src/api/anthropic-messages.ts:584-585`、`packages/ai/src/api/openai-completions.ts:1377-1379`。
- 本机数据（只读实测）：`~/.codex/sessions/**/*.jsonl`（124 文件）、`~/.codex/history.jsonl`、`~/.codex/config.toml`（仅大小）、`~/.claude/projects/**/*.jsonl`（294 文件）、`~/.claude/history.jsonl`、`~/.pi/agent/sessions/**/*.jsonl`（对照计数）。
- 本机 CLI（`--help`/`--version` 本地执行，无 LLM 调用）：`codex-cli 0.147.0`（`codex --help`、`codex exec --help`）、`Claude Code 2.1.250`（`claude --help`）。

[VERIFY] codex 124 files / 275,770,428 B（2026-04-14~08-22）；claude 294 files / 358,323,344 B（2026-07-28~08-28）；last-7d 0/0 files both；usage parse 0.46s(codex)+1.06s(claude) vs pi 12.31–12.66s(4,079 files/2.68 GB)；codex token_count 14,877 vs turns 1,019，pair-dup 1,252/2,508；invariants 29,522 checked、0 违反 input≥cached+cache_write、95 违反 total=in+out；claude dedup 1.87×/1.41×；codex subagent 文件 38、claude subagents 文件 171、isSidechain 行 8,333、抽样重叠 0；`Read your task file at` 命中 0；codex exec 0.147.0 无 session-id、claude 2.1.250 有 `--session-id <uuid>`、`--ephemeral`/`--no-session-persistence` 存在。
