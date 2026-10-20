# RQ1: pi 会话 JSONL usage 全貌与 worker/PM 确定性归因（research）

- Key: mw-usage-monitor / T-RQ1；执行窗口: worker um-rq1-pi-session-usage (type: research)
- 日期: 2026-10-19；只读边界遵守（仓库零修改；临时脚本与探针均在 %TEMP%）
- 数据快照: `~/.pi/agent/sessions/**` 共 4079 个 .jsonl（PM 复核时 4065 → 存量随活窗口增长，本文所有计数为 2026-10-19 快照，两次扫描间存在 ±30 条消息的自然漂移）

## 结论

1. **会话 schema**：entry `type` 实测 7 种（session / model_change / thinking_level_change / message / custom_message / custom / compaction）；schema 另有 branch_summary / label / session_info（本机 0 条）。`usage` 只出现在 4 处：assistant 消息 `message.usage`（必有，287,310/287,310）、compaction entry 顶层 `usage`（1699/1699）、branch_summary.usage 与 toolResult.usage（schema 支持、本机 0 条）。**一条 assistant 消息 = 恰好一次 provider 响应，不聚合重试**：`retryAssistantCall` 只返回最后一次尝试（packages/ai/src/utils/retry.ts:162-213），失败尝试作为独立 message entry 落盘（usage 全 0，EMPTY_USAGE）；实测 (provider,responseId) 重复组 = 0。
2. **版本兼容**：本机 4079 个会话 **全部 version 3**（无一 v1/v2）。`usage` 字段名从未变过；v1→v2 加 id/parentId 树，v2→v3 把 hookMessage 改名 custom，#6671 (2fd386840, 2026-07-20) 给 compaction/branch_summary/toolResult 补了 usage 字段。扫描器可按 version==3 处理、对缺字段防御即可。
3. **session 定位语义（已实测）**：`--session-id` 强校验 `^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$`（非法 id 实测 exit 1）；合法 id + `--session-dir <tmp>` 实测落盘 `%TEMP%\...\2026-10-19T09-53-00-375Z_mw-rq1-probe-1.jsonl`（`<ISO时间戳:.:→-_-_id>.jsonl`，header id 原样保留）。优先级 `--session-dir` > `PI_CODING_AGENT_SESSION_DIR` > settings.sessionDir > 默认按 cwd 编码目录。**同 id 重跑 = 打开续写旧文件（resume 语义）**；自定义目录在 sessions 根之外时其他窗口的 /resume 看不到（listAll 只扫根下子目录）。新会话在首条 assistant 响应前**不落盘**（deferred flush）。
4. **归因方案**：会话文件不含 env/argv/PI_WORKER_TASK（只在消息正文出现）；现有 worker-summary(148 会话)/watch(86 会话) custom 条目是 best-effort 信号。**落地建议**：launcher 在 `_build_command`（launcher.py:1791-1794）给每个 worker 追加 `--session-id mw-<key>-<seq>`（seq 每次派发递增，绝不复用 id），并把 (key,seq,session-id,pid,started_at) 记入任务目录台账；扩展侧在 workerModeActivate 首行 `pi.appendEntry("agent-team-loop:worker-identity", {taskKey,type,pid,startedAt})`（extensions/types.ts:1315）做文件内自描述兜底。孤儿/崩溃：首响应前死 → 无文件（deferred flush，台账记 no-usage，正确）；同 key 重生用新 seq id，避免 resume 合并歧义。PM = 无 `mw-` 前缀（default 目录）。
5. **扫描成本**：4079 文件 / 2,684,435,670 B（p50 588 KB / p99 3.7 MB / max 20 MB）；按 mtime 取近 7 天 1006 文件全量 JSON 解析 **2.911 s**；全库 assistant 行扫描 **11.132 s**；仅 header（4KB/文件）**0.542 s**。结论：`mw stats --since 7d` 按需扫描完全可行（冷启动 <5 s）；rollup 缓存非必需，建议阈值：查询窗 >30d 或全库查询、或扫描墙钟 >10 s（约当前全库 1 倍）时启用增量 rollup（文件 append-only，(file,mtime,size) 粒度增量即可）。
6. **PM 会话可统计**：与 worker 会话同 schema，model/provider/usage 逐消息可聚合（复用 getUsageCostBreakdown 键 `provider/(responseModel??model)`，usage-totals.ts:42-72）。「一次 PM 会话」= 一个 .jsonl 文件；墙钟 = header.timestamp → 末条 entry.timestamp（实测 p50 570 s，最长 25.2 天——常驻窗口一个文件活数周）。确认 tokens-only 决策合理：**timi 全部 286,578 条消息 cost 全 0**（模型表无费率），zai-coding-cn 308/345 条有真实 cost。

## 证据

### 1. 会话 JSONL 完整 schema

**Entry 类型（schema 全集，session-manager.ts:30-175）**：

- `packages/coding-agent/src/core/session-manager.ts:30` `export const CURRENT_SESSION_VERSION = 3;`
- SessionHeader（:32-39）: `{type:"session", version?, id, timestamp, cwd, parentSession?}`
- SessionEntry 联合（:105-115）: `SessionMessageEntry | ThinkingLevelChangeEntry | ModelChangeEntry | CompactionEntry | BranchSummaryEntry | CustomEntry | CustomMessageEntry | LabelEntry | SessionInfoEntry`
- 各类型写入函数：appendMessage(:1049)、appendThinkingLevelChange(:1061)、appendModelChange(:1073)、appendCompaction(:1085-1104)、appendCustomEntry(:1106-1116)、appendSessionInfo(:1118-1129)、appendLabelChange(:1240-1256)、appendCustomMessageEntry(:1146-1172)

**本机 4079 文件实测 type 分布（Python 全量扫描）**：

```
entry type counts: {'session': 4079, 'model_change': 4143, 'thinking_level_change': 4102,
 'custom_message': 1465, 'message': 640306, 'custom': 466, 'compaction': 1699}
# branch_summary / label / session_info: 0 条
message roles: {'user': 7513, 'assistant': 287566, 'toolResult': 345791}   # bashExecution/custom 角色 0 条
```

**usage 出现位置（写点 `文件:行号` + 原文）**：

1. assistant 消息 `message.usage` — 类型 `packages/ai/src/types.ts:365-385`（Usage interface）+ `:410-426`（AssistantMessage.usage 必填）。provider 侧写点：
   - `packages/ai/src/api/anthropic-messages.ts:578-586`（message_start）与 `:718-743`（message_delta）：
     ```ts
     output.usage.input = event.message.usage.input_tokens || 0;
     output.usage.cacheRead = event.message.usage.cache_read_input_tokens || 0;
     output.usage.cacheWrite = event.message.usage.cache_creation_input_tokens || 0;
     output.usage.cacheWrite1h = event.message.usage.cache_creation?.ephemeral_1h_input_tokens || 0;
     output.usage.totalTokens = output.usage.input + output.usage.output + output.usage.cacheRead + output.usage.cacheWrite;
     calculateCost(model, output.usage);
     ```
   - `packages/ai/src/api/openai-completions.ts:1348-1383` `parseChunkUsage`（zai 走此路；`reasoning` 恒写 `|| 0`）
   - `packages/ai/src/api/openai-responses-shared.ts:539-563`（timi openai-responses 走此路；`:570` `output.rawStopReason = incompleteReason ? \`${status}.${incompleteReason}\` : status`）
2. compaction entry 顶层 `usage?` — `session-manager.ts:81-84`（`/** Usage from the LLM call(s) that generated this summary */ usage?: Usage`）；写入 `agent-session.ts:1878` / `:2154` `this.sessionManager.appendCompaction(summary, firstKeptEntryId, tokensBefore, details, fromExtension, usage)`。实测 1699/1699 条 compaction 均带 usage 字段。
3. branch_summary entry 顶层 `usage?` — `session-manager.ts:101-103`（本机 0 条）。
4. toolResult 消息 `message.usage?` — `packages/ai/src/types.ts:431-434` `/** Usage from the tool execution itself, if available. Not part of main LLM context accounting. */`；来源 `agent-session.ts:512,530`（afterToolCall hook 的 `usage: result.usage` / `usage: hookResult?.usage`）。实测本机 0 条。

聚合参考实现（/cost 面板同款）：`packages/coding-agent/src/core/usage-totals.ts:19-27`（addUsageToTotals）与 `:42-72`（getUsageCostBreakdown，键 `${provider}/${responseModel ?? model}`，toolResult/compaction/branch_summary usage 归入 "Tools/summaries" 桶）。

**一条 assistant 消息是否聚合多次重试：否。**

- `packages/ai/src/utils/retry.ts:162-213` `retryAssistantCall`：循环内 `const response = await produce()`，成功（`stopReason !== "error"`）原样返回；重试时丢弃上一次的失败 message，**不合并 usage**。失败尝试只有在其被判定不可重试/预算耗尽时才作为最终消息返回。
- agent 层失败兜底：`packages/agent/src/agent.ts:39-46` `EMPTY_USAGE`（全 0，无 cacheWrite1h/reasoning）+ `:508-518` failureMessage（`stopReason: aborted ? "aborted" : "error"`）。
- 外层 compaction-and-retry（`agent-session.ts:2185-2196`）是**新 turn** → 新 message entry；错误消息保留在会话（`agent-session.ts:2012` "It remains in session history"）。
- 实测闭环：assistant 287,310 条中 `usage.totalTokens==0` 共 1318 条，分布 `{'faux','error'}:33, {'timi','aborted'}:41, {'timi','error'}:1235, {'zai-coding-cn','error'}:8, {'timi','stop'}:1` —— 与 error/aborted 独立落盘一致；`(provider,responseId)` 重复组 = 0，即每条消息唯一对应一次 provider 响应。
- 落盘点：`agent-session.ts:640-657`（message_end → `sessionManager.appendMessage(event.message)`，assistant/user/toolResult 都落）。

**`api` / `responseId` / `rawStopReason` 的作用**（types.ts:412,417-418,425）：

- `api`（types.ts:17-24 Api 枚举 + faux 运行时 id）：产出该消息的 provider API 实现（anthropic-messages / openai-completions / openai-responses / openai-codex-responses / azure-openai-responses / bedrock / google / mistral / `faux:<ts>:<rand>`）；由 `agent.ts:511` `api: this._state.model.api` 写入。
- `responseId`：provider 侧响应 id（anthropic `:575` `output.responseId = event.message.id`；openai-responses-shared `:541-543` `output.responseId = response.id`）。实测全局 0 重复，可作去重键。
- `rawStopReason`：provider 原始状态映射前保留值。实测分布：`tool_use 275560 / end_turn 7304 / completed 2381 / None 1712 / tool_calls 307 / incomplete.max_output_tokens 43 / stop 30`；faux 为 null。

**usage.cost 按 provider 实测**（cost 是**客户端**按模型费率表算的：`packages/ai/src/models.ts:878-897` `calculateCost`；openai-responses 另有 service-tier 乘数 `openai-responses-shared.ts:353-364`）：

```
provider 计数:      timi 286,578 | zai-coding-cn 345 | faux 414   （anthropic/openai-codex 0 样本）
cost.total 非零:    timi 0/286,578（全 0）| zai 308/345（合计 4.90）| faux 22/414（合计 2.71，测试费率）
zai 样例: glm-5.3 input=1803 output=70 → cost.total=0.003
```

- timi：模型注册无费率 → cost 恒 0（token 统计不受影响）。
- anthropic / openai-codex：provider id 存在于代码（`packages/ai/src/types.ts:40-44`、`models.generated.ts:106-110`），本机 0 样本，实际取值**未找到**。
- `cacheWrite1h`：仅 anthropic-messages 路径写（`:582`，`|| 0`，是 cacheWrite 的子集，费率 2x，`models.ts:889-893`）。实测：present 282,915 / **nonzero 0**（本机 timi 代理不回报 ephemeral_1h；真实 anthropic 才可能非 0）。
- `reasoning`：实测 2,766 条（openai-completions 与 openai-responses 路径恒写，anthropic 仅 thinking 时写）；是 output 子集（types.ts:372-377 注释）。

### 2. 多版本兼容

```
session header versions: {'3': 4079}    # v1/v2: 本机 0 个文件
assistant messages total: 287310; missing usage: 0
```

- 代码迁移链（session-manager.ts:232-268）：`migrateV1ToV2`（加 id/parentId、compaction `firstKeptEntryIndex`→`firstKeptEntryId`）、`migrateV2ToV3`（`hookMessage` role → `custom`）。版本历史：v2 = c58d5f20a "Session tree structure with id/parentId linking"；v3 = c6fc08453 "Merge hooks and custom-tools into unified extensions system (#454)"。
- usage 字段名历史上就叫 `usage`（AssistantMessage 接口始终如此）；compaction/branch_summary/toolResult 的 usage 由 2fd386840 (#6671, 2026-07-20) 加入。
- 结论：扫描器只需实现 v3 语义 + migrate 语义兜底（读到 v1/v2 文件时：v2 树结构与 custom 角色改名对 usage 统计无影响）。

### 3. `--session-id` / `--session-dir` / `PI_CODING_AGENT_SESSION_DIR` 语义

- flag 解析：`packages/coding-agent/src/cli/args.ts:107-115`（`--session` :107、`--session-id` :110、`--session-dir` :114）；help 文本 :405 `${ENV_SESSION_DIR} - Session storage directory (overridden by --session-dir)`。
- 优先级：`packages/coding-agent/src/main.ts:632-635`
  ```ts
  const envSessionDir = process.env[ENV_SESSION_DIR];                     // config.ts:512
  const sessionDir =
      (parsed.sessionDir ? normalizePath(parsed.sessionDir) : undefined) ??
      (envSessionDir ? expandTildePath(envSessionDir) : undefined) ??
      startupSettingsManager.getSessionDir();                             // settings-manager.ts:131,675-678
  ```
  未设时 `SessionManager.create` 用默认目录：`session-manager.ts:476-481` `` `--${cwd.replace(/^[/\\]/,"").replace(/[/\\:]/g,"-")}--` `` → `~/.pi/agent/sessions/<slug>/`（getSessionsDir: config.ts:575-577）。
- 落盘文件名：`session-manager.ts:951-953`（newSession）
  ```ts
  const fileTimestamp = timestamp.replace(/[:.]/g, "-");
  this.sessionFile = join(this.getSessionDir(), `${fileTimestamp}_${this.sessionId}.jsonl`);
  ```
  **实测**（`node packages/coding-agent/dist/cli.js --session-id mw-rq1-probe-1 --session-dir %TEMP%\mw-rq1\sess-probe2 --provider no-such-provider -p "hi"`，provider 解析回落默认 timi，产生一次真实调用 ~3.2k token，成本 0，已披露）：
  ```
  文件: 2026-10-19T09-53-00-375Z_mw-rq1-probe-1.jsonl
  首行: {"type": "session", "version": 3, "id": "mw-rq1-probe-1", "timestamp": "2026-10-19T09:53:00.375Z", "cwd": "C:\\Users\\wenbozhou\\AppData\\Local\\Temp"}
  stderr: Warning: No project session found with id 'mw-rq1-probe-1'; creating a new session with that id.
  ```
  同文件还实证 deferred flush：flush 前积压的 header/model_change/thinking_level_change/user 与 assistant 一次性写入（`session-manager.ts:1015-1042`：无 assistant 前 `flushed=false` 不写盘）。反例（代码层面）：新会话若在首条 assistant 前退出 → **无文件**。
- id 强校验：`session-manager.ts:212-218`
  ```ts
  export function assertValidSessionId(id: string): void {
      if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/.test(id)) {
          throw new Error("Session id must be non-empty, contain only alphanumeric characters, '-', '_', and '.', and start and end with an alphanumeric character");
  ```
  CLI 入口 `main.ts:276-299` validateSessionIdFlags（与 --session/--continue/--resume 互斥）。**实测**：`--session-id "bad id!"` → `Error: Session id must be non-empty...`，exit=1，无模型调用。
- `--session <x>` 接受 id 还是路径：`main.ts:218-247` resolveSessionPath —— 含 `/` `\` 或以 `.jsonl` 结尾按路径；否则项目内 exact id → 前缀匹配，再全局 listAll exact → 前缀（跨项目提示 fork）。
- `--session-id` 重跑语义：`main.ts:330-341`（fork 分支查重拒绝）与 `:395-409`：项目内找到同 id → **`SessionManager.open(existing.path)` 续写旧文件**；否则告警 + `SessionManager.create(cwd, sessionDir, { id })`。→ 同 id 复用 = resume，不是新建。
- 目录不在默认 sessions 根时的 /resume 可发现性：同进程内 `/resume` 用 `SessionManager.list(cwd, sessionDir)` / `listAll(sessionDir)`（main.ts:378-388）能看到该目录；**其他**未带该 flag/env 的进程只扫 sessions 根下的子目录（`SessionManager.listAll` → `getSessionsDir()` + readdir 子目录，session-manager.ts:1663-1700）→ 根外的自定义目录对外不可发现，但 `--session <绝对路径>` 始终可打开。`--continue` 用 findMostRecentSession（session-manager.ts:635-670，:1557-1565），仅当目录≠默认时按 header.cwd 过滤。

### 4. worker vs PM 确定性识别

**现有信号盘点（实测）**：

- 会话首行有 `cwd`（304 个不同值），**无 env、无 argv、无 PI_WORKER_TASK 结构化字段**（全库扫描：`"env"` 行 0、`"argv"` 行 0；`PI_WORKER_TASK` 3573 处全部在消息正文/文档文本内）。
- mw 扩展已写两种 best-effort 标记（本机实测）：
  - `custom_message` `customType="agent-team-loop:worker-summary"`：1467 条、148 个会话（worker 侧 phase 汇总）
  - `custom` `customType="agent-team-loop:watch"`：329 条、86 个会话（PM 侧 watch 状态）
  - 缺陷：worker 崩溃在首个 phase 前无标记；PM 未开 autopilot 无 watch；均非 spawn 时刻确定性落盘。
- launcher 现状：`packages/multi-workers/launcher.py:1788,1791-1794` `cmd = ["pi"] (+--model) + ["-p", starter]` —— **未传 --session-id**，worker 会话混入 cwd 默认目录（PM 已实测正文归因误判，不再重复）。

**建议接口（可直接落地，参数形态）**：

1. launcher 显式分配（主方案）：`launcher.py _build_command`（:1791-1794 处）对 `cli=="pi"` 追加
   `cmd += ["--session-id", f"mw-{key}-{seq}"]`
   - `key` = 任务 key（slug，`[a-z0-9-]`），`seq` = 该 key 的派发序号（1,2,3…每次 spawn 递增，**绝不复用**——同 id 会 resume 旧文件，main.ts:395-409）。charset 通过 assertValidSessionId（字母数字开头结尾）。
   - 台账：spawn 时把 `{task_key, seq, session_id, pid, started_at}` 写入任务目录既有 run-state/worker 记录（与 PI_WORKER_TASK 同点写入，launcher.py:380-383）。读取侧 `mw stats` 扫默认目录按 `mw-` 前缀得 source=worker + key；join 台账补 pid/时间；无前缀 → source=pm。
   - 冲突隔离：不改目录，worker 与 PM 同目录但前缀可辨；/resume 列表里 worker 会话以 `mw-<key>-<n>` 可读命名出现（可读性收益而非噪音）。
2. env 隔离（可选叠加）：`_build_env`（launcher.py:376-385，与 PI_WORKER_TASK 同处）加 `env["PI_CODING_AGENT_SESSION_DIR"] = str(control_root/".mw"/"sessions")` —— 零 CLI 改动、worker 会话物理隔离（其它窗口 /resume 不可见，见 §3）；统计侧直接整目录扫 = source=worker。注意 launcher 的 stripped env 已天然防泄漏（探针实测子进程会**继承**当前 shell 的 PI_WORKER_TASK，身份类 env 必须显式覆盖或剥离）。
3. 扩展自描述（兜底，覆盖已运行/存量）：`workerModeActivate`（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`，激活点即 dist `extensions/agent-team-loop.js:31114-31116` 的 `if (process.env.PI_WORKER_TASK)`) 首行调 `pi.appendEntry("agent-team-loop:worker-identity", { taskKey, type, taskPath, pid, startedAt })`（扩展 API：`packages/coding-agent/src/core/extensions/types.ts:1315` `appendEntry<T>(customType, data?)`；会话侧为 `custom` entry）。文件即自证，读取侧不依赖 launcher 台账是否存活。运行时可读 `sessionManager.getSessionId()`（session-manager.ts:1007，ReadonlySessionManager :222-234 已暴露）同步写 trace.log 做 join。
   - 注意 deferred flush：identity entry 也要等首条 assistant 才落盘 —— 与 §4 孤儿语义一致（无响应 = 无 usage，无需记账）。

**孤儿/崩溃处理**：崩溃于首响应前 → 无文件，台账按 crashed/no-usage 收敛（正确，无账可记）；崩溃于会话中途 → 文件保留至最后一条响应，墙钟取 header→末条 timestamp；同 key 重生（新 seq id）→ key 汇总 = 各文件求和。**不做**同 id 复用（resume 会把两次 spawn 混进一个文件，墙钟与归因都歧义）。

### 5. 扫描成本实测

```
# 全库体量（Python os.path.getsize, 4079 files）
total_bytes: 2,684,435,670 (2.5 GiB)  avg: 658,111
min: 178  p50: 588,135  p90: 1,129,090  p99: 3,675,588  max: 20,006,968

# 近 7 天（mtime 过滤 1006 文件）assistant usage 全量 json.loads 汇总:
timed parse seconds: 2.911
assistant-with-usage msgs: 93,507
token totals: input 225,084,298 | output 92,498,238 | cacheRead 11,787,931,297 | cacheWrite 4,156,870 | totalTokens 12,109,670,703

# 全库对照
full corpus assistant scan: 11.132 s (287,391 msgs, totalTokens 34,582,622,571)
full corpus signal scan (customType/env/argv/task.md): 11.338 s
header-only (first 4KB per file, 全 4079): 0.542 s
```

- 命令形态：`glob(~/.pi/agent/sessions/*/*.jsonl)` → mtime/首行 header.timestamp 过滤 → 逐行 `"assistant"` 子串预滤 → json.loads → 累加 usage（+ compaction usage）。机器：Windows 11，Python 3.x 单进程。
- 结论：`mw stats --since 7d` 按需扫描**可行**（冷 <5 s，热缓存更快）。rollup 缓存**非必需**；建议引入阈值：查询窗 >30 天、或全库查询、或预计扫描墙钟 >10 s（≈当前全库再翻倍）时启用增量 rollup（文件 append-only，按 `(file_path, mtime, size)` 缓存该文件累计值并只重扫变化文件即可，无需解析 offset）。
- cacheRead 占 totalTokens 的 97%（12.1G/34.6G 全库）——`/mw stats` 简报应拆示 input/output/cacheRead/cacheWrite，否则数字无解释力。

### 6. PM 窗口会话的可统计性

- **可以**。PM 会话与 worker 会话同 schema（同一 cwd 默认目录、同一 assistant message.usage）。按 model/tokens 聚合直接复用 `usage-totals.ts:42-72` getUsageCostBreakdown 的键法 `${provider}/${responseModel ?? model}`（实测 responseModel 全库非空 0 条，键实际 = provider/model）。
- 「一次 PM 会话」的界定：**一个 .jsonl 文件 = 一次进程会话**（new file per `pi` 启动；/continue 重开同一文件续写）。墙钟 = header.timestamp（首行）→ 末条 entry.timestamp。实测 4078 个可界定会话：span p50 = 569.5 s，max = 2,177,539.9 s（25.2 天，常驻 PM/长命窗口一个文件活数周，跨天统计须按消息 timestamp 而非文件归属切桶）。轮次墙钟 = 相邻 assistant message timestamp 差（`message.timestamp` 为 Unix ms，types.ts:426）。
- 归因叠加 §4：无 `mw-` 前缀（或无 worker-identity entry）→ source=pm；有 watch entry 可进一步标注「autopilot PM」。
- 可见性注意：无任何 assistant 响应的 PM 会话不落盘（deferred flush）→ 统计天然只含有模型调用的会话（合理）。

## 未找到清单

1. anthropic / openai-codex provider 的 usage.cost 实际取值：本机 0 样本。未找到（全库 provider 计数只有 timi/zai-coding-cn/faux；provider id 仅存在于 `packages/ai/src/types.ts:40-44` 与 `models.generated.ts:106-110`）。按代码推知 cost 由模型费率表计算（models.ts:878-897），实际数值待真实凭证环境验证。
2. timi 模型费率注册点：未找到（`~/.pi/agent/models-store.json` providers=[]；`~/.pi/agent` 下无 models.json；`.mw/providers.json` 不存在于本仓库 —— 命令 + 输出：`json.load → providers: []` / `os.path.exists → False`）。timi cost 全 0 的直接原因（无费率）成立，注册链路未追。
3. v1/v2 会话文件本体：未找到（`versions: {'3': 4079}`），字段差异仅能由迁移代码 + git 历史佐证。
4. `{'timi','stop'}` 的 1 条 totalTokens==0 消息：未找到成因（其余 1317 条均为 error/aborted，符合 EMPTY_USAGE 语义）。
5. `pi --session-dir <tmp> -p "say ok"` 的完整干净实测：未以中性环境执行 —— 探针进程继承本 worker env（PI_WORKER_TASK 等），并回落默认 timi provider 产生一次真实调用；文件名/id/校验/flush 语义已由该探针与非法 id 探针覆盖，env 隔离语义未在净环境复测。

## 未覆盖面声明

- 多机/多用户（~/.mw/usage 机器级存储的跨机合并）未验证；本报告全部数据来自单机。
- remote session / RPC 模式（packages/coding-agent/src/modes/rpc、client/）的会话落盘路径未审计（本机未使用）。
- bedrock / google / mistral / azure provider 的 usage 写点仅列出代码位置，未实测样本。
- 扫描耗时为单次冷测量（OS 文件缓存状态未控制），数量级可信、绝对值有 ±20% 波动空间。
- 快照漂移：两次全库扫描间隔内活窗口持续追加，assistant 计数 287,310 → 287,391；所有比例结论不受影响。
- 一次真实 LLM 调用副作用：探针 `pi -p "hi"` 经默认 timi/deepseek-v4.1-flash 产生 ~3,180 token（cost 0）调用与会话文件 %TEMP%\mw-rq1\sess-probe2\（临时目录，非仓库），临时脚本与该目录已在收尾时删除。

## 结论

（本节为交付段契约要求的四段之一；结论要点见文首「## 结论」=「0. 结论先行」1-6 条，不重复。）

## 证据

（本节为交付段契约要求的四段之一；全部判据见上文「## 证据」§1-§6：`文件:行号` + 原文 + 实测命令/输出，均为只读采集。）

## 残留与未验证

（本节为交付段契约要求的四段之一；见「## 未找到清单」1-5 与「## 未覆盖面声明」。核心残留：anthropic/openai-codex cost 实值、timi 费率注册点、净环境 env 隔离实测。）

## 上下文来源

- 任务书：`.agenticdoc/mw-usage-monitor/tasks/T-RQ1-pi-session-usage.md`（PM dispatch card + 要求 1-6 + 只读边界）
- 项目锚点：`.agenticdoc/goal.md`（mw 后台服务 / 文件驱动协调 / 本机 token 监控为可观测性面）
- 代码（只读引用）：packages/coding-agent/src/{core/session-manager.ts, core/agent-session.ts, core/usage-totals.ts, core/config.ts, core/settings-manager.ts, cli/args.ts, main.ts, core/extensions/types.ts}；packages/ai/src/{types.ts, models.ts, utils/retry.ts, api/anthropic-messages.ts, api/openai-completions.ts, api/openai-responses-shared.ts}；packages/agent/src/agent.ts；packages/multi-workers/launcher.py
- 本机数据：`~/.pi/agent/sessions/**`（4079 files, 2.5 GiB, 全 v3）；`~/.pi/agent/{settings.json, models-store.json}`；git 历史（c58d5f20a / c6fc08453 / 2fd386840）
- 实测探针：%TEMP%\mw-rq1\{scan1-7.py, sess-probe2}（已删除；输出均摘录于上文）

[VERIFY] 4079 files, 2,684,435,670 B, v3=4079, assistant=287310, missing-usage=0, zero-usage=1318, timi=286578 cost0=286578, zai nonzero-cost=308, cacheWrite1h nonzero=0, 7d-scan=2.911s, full-scan=11.132s, header-scan=0.542s, probe-file=2026-10-19T09-53-00-375Z_mw-rq1-probe-1.jsonl, bad-id exit=1, worker-summary-sessions=148, watch-sessions=86, session-span-p50=569.5s, session-span-max=2177539.9s
