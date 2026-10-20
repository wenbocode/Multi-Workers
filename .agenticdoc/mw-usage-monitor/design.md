# Design: mw-usage-monitor（本机 token/耗时监控）

- Key: mw-usage-monitor · 2026-10-19
- 上游：`spec.md` v0.2（§4 AC-001…AC-013）
- 证据：`evidence/research/spec-rq{0,1,2,3,4}-*.md`

## 1. 架构总览

```
┌──────────────────────────── mw serve / launcher (per project) ────────────────────────────┐
│ _spawn (launcher.py:2450)  ──► usage.append_event("start")   ~/.mw/usage/runs.jsonl (+.lock)│
│ _poll_once (launcher.py:2162) ─► usage.append_event("end")        ▲                        │
│ _reconcile_orphans (:1934-1942) ► usage.append_event("end", reconciled=true)               │
└───────────────────────────────────────────────────────────────────┼────────────────────────┘
                                                                    │ join by run_id / session_id
   pi sessions  ~/.pi/agent/sessions/<slug>/<ts>_<id>.jsonl ────────┤
   claude logs  ~/.claude/projects/<slug>/<uuid>.jsonl (+subagents) ┤
   codex logs   ~/.codex/sessions/... (v1 不读)                     ▼
                                                    usage.build_report()  ──►  mw stats (text/json)
                                                                          └─►  /mw stats (notify)
```

**单一真相**：token 只在会话日志里（RQ4：timi 直连不经代理，proxy 无 usage 钩子）；台账只存**运行元数据**
（谁、何时、什么模型、多久、怎么结束）→ 查询时 join（spec D-7）。

## 2. 台账模型：两事件 append-only

`~/.mw/usage/runs.jsonl`，一行一个**事件**，`run_id` 串联：

```json
{"event":"start","run_id":"<ts>-<pid>-<seq>","ts":"2026-10-19T09:45:35.506Z","source":"worker",
 "project":"H:/git/Multi-Workers","key":"mw-usage-monitor","task_key":"um-rq1",
 "type":"research","role":"research","cli":"pi","attribution":"exact",
 "session_id":"mw-mw-usage-monitor-43712-7","model":"timi/glm-5.3-flashx",
 "model_source":"config:research","pid":12345,"cwd":"H:/git/Multi-Workers"}
{"event":"end","run_id":"<same>","ts":"...","exit":0,"wall_s":483.2,"reconciled":false,"status":"done"}
```

- 为什么两事件而不是「更新一行」：launcher 崩溃/被 kill 时单行会永远停在 start；两事件让「未结束」
  可被查询面识别（AC-004），且 append 无需读改写（RQ4 §4 并发）。
- `event` ∈ `start | end | spawn_failed`。`spawn_failed` 记 `_record_spawn_failure` 同点（launcher.py:74-87），
  无 pid、无 wall。
- 孤儿收敛（launcher.py:1934-1942）：写 `end` 且 `reconciled:true`；exit 优先取 trace.log `[END] exit=`，
  取不到写 `null`（**不写 0**，AC-004/AC-013）。
- fail-soft：`append_event` 内部 `except Exception` → 仅 stderr 一行 warning（不静默、不抛、不阻断 spawn）。

## 3. 模块划分

### 3.1 新模块 `packages/multi-workers/usage.py`（唯一新 Python 模块，~450 行）

| 函数 | 职责 |
| --- | --- |
| `usage_dir() -> Path` | `MW_USAGE_DIR` → `USERPROFILE`/`HOME` → `~/.mw/usage`；mkdir(parents=True)（照 `machine_rag_servers_path` 的显式序，RQ4 §3） |
| `ledger_path() / lock_path()` | `<dir>/runs.jsonl`、`<dir>/runs.jsonl.lock` |
| `append_event(record: dict) -> bool` | 锁 → 每条独立 `open("a", encoding="utf-8", newline="\n")` 写一行 → 释放；异常返 False |
| `new_session_id(key, pid, seq) -> str` | `mw-<key>-<pid>-<seq>`，`assertValidSessionId` 同款正则自检（RQ1 §3） |
| `parse_since(text) -> datetime` | `7d/24h/YYYY-MM-DD` |
| `iter_session_files(root, since) -> Iterator[Path]` | 先按文件名/首行 header 粗筛（header-only 全库 0.54 s，RQ1 §5） |
| `scan_pi_session(path) -> dict` | 逐行 `"assistant"` 预滤 → `json.loads` → 累加 4 分量 + compaction entry；返回 `{session_id, cwd, started_at, ended_at, models:{k:{in,out,cache_read,cache_write,requests}}, events:[(ts, model, tokens)]}` |
| `scan_claude_session(uuid, roots) -> dict|None` | 主文件 + `<uuid>/subagents/*.jsonl`，**按 `message.id` 去重**（不去重虚增 1.41–1.87×，RQ3 §2b）；`input_tokens` 直接是非缓存输入（RQ3 §4） |
| `load_runs(since, filters) -> list[Run]` | 读台账、按 run_id 配对 start/end、应用 `--key/--type/--model/--project/--source` 过滤；跳过坏行并计数 `bad_lines` |
| `build_report(now, since, filters) -> dict` | 扫描 + join + 四组聚合 + coverage（§5） |
| `format_report_text(report) -> str` | 定宽 f-string（抄 `_format_update_env_text` mw.py:6933），不自造表格渲染器 |

**指标纯函数**：`_percentile(values, p)`（线性插值，`n<5` 返回 `None` → 渲染 `-`）、`_token_sum(rows)`。

**隐私边界**：只读 `type/model/provider/timestamp/usage/message.id`；**不读、不存** `message.content`、
`custom_message.data` 正文（AC 隐私要求见 spec §5）。

### 3.2 `launcher.py` 改动（4 处，均在既有函数内）

| 位置 | 改动 |
| --- | --- |
| `_build_command`（:1764-1806） | 新增可选参数 `session_id`；`cli=="pi"` → 插 `--session-id <sid>`；`cli=="claude"` → 插 `--session-id <uuid4>`；`cli=="codex"` → 不传（RQ3：无此参数） |
| `_spawn`（:2373-2459） | 分配 `sid = usage.new_session_id(key, os.getpid(), self._seq())`（pi）/`uuid.uuid4()`（claude）；`Popen` 成功后（:2451 后）`append_event(start)` 并 `self._runs[task_key] = run_id` + 记 `session_id`；spawn 失败（:2460-2467）写 `spawn_failed` |
| `_poll_once`（:2162-2186） | `code = proc.returncode ...` 之后立即 `append_event(end)`（含 `wall_s = now - start`、`exit = code`、`status`）；**exit-3 重派分支（:2177-2183）在 `continue` 前写** |
| `_reconcile_orphans`（:1934-1942） | terminal 判定处补 `append_event(end, reconciled=True)`，exit 来自 trace.log `[END]` 解析（`parse_end_exit` 先例 mw_common.py:2772-2795） |

- `_seq()`：launcher 实例内计数器（单调递增），`run_id` = `<iso-ts>-<pid>-<seq>` → 跨重启唯一（pid 变化）。
- 台账调用全部包在 `try/except`（由 `usage.append_event` 内部保证），**不得改变 spawn 控制流**。

### 3.3 `mw.py` 改动

| 位置 | 改动 |
| --- | --- |
| `_parse_args`（:7009-7493） | 在 `("stop","status")` 循环（:7016-7018）之后新增 `stats` 子命令：`--since/--key/--type/--model/--project/--source/--json`（`--project` 可选，TS 恒追加，RQ4 §2） |
| dispatch 表（:7503-7524） | `"stats": cmd_stats` |
| 新函数 `cmd_stats(args) -> int` | `usage.build_report()` → `--json` 打印 `json.dumps(..., indent=2, ensure_ascii=False)`，否则 `format_report_text`；无台账 → 打印 `no usage ledger at <path>` 并 rc=0 |

### 3.4 TS 面

| 文件 | 改动 |
| --- | --- |
| `shared/mw-runner.ts` | `statsMw(projectDir, extra: string[])` → `runMwCliRaw(["stats", ...extra])`（恒追加 `--project`，照已有包装） |
| `pm/ui-bridge.ts` | `runMwStatsCommand(ctx, args)`；`registerMwCommands` 的 if-链（:3687-3688）加 `stats` 分支；`MW_COMMAND_DESCRIPTION`（:3514）与 usage 尾行（:3859）加一行 |

## 4. 归因与 join 算法（`build_report` 主流程）

1. `runs = load_runs(since, filters)`：配对事件，得到 `{run_id, session_id, cli, key, type, model, project, wall_s, exit, source}`。
2. **pi**：`iter_session_files(since)`（header 粗筛）→ `scan_pi_session` → 以文件名解析 `session_id`：
   - `mw-` 前缀 → `source=worker`；join `runs` by `session_id` 补 `key/type/model/wall`（台账缺失也能出数，
     `attribution=exact`，`wall` 退化为 header→末条）；
   - 无前缀 → `source=pm`（`attribution=exact`）。
3. **claude**：仅对 `runs` 里 `cli=claude` 的 `session_id` 精确打开文件（+subagents 并账）→ `attribution=exact`；
   文件缺失 → `unknown_cli`。
4. **codex**：`runs` 行保留，`attribution=unknown_cli`，token 不计入任何组（只计入 coverage）。
5. 分桶：窗口内 assistant message 的 `timestamp` 决定归属（PM 长命会话跨天，RQ1 §6）。
6. 组键：`model` = `provider/model`（`responseModel` 全库为空，RQ1 §6）；`type` = 任务类型；`key` = owner key；
   `project` = control root basename。

## 5. `mw stats --json` 契约（测试固定）

```json
{
  "generated_at": "2026-10-19T10:00:00Z", "since": "2026-10-12T10:00:00Z", "window": "7d",
  "ledger": {"path": "...", "events": 42, "bad_lines": 0, "open_runs": 1},
  "totals": {"calls": 120, "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "runs": 9},
  "groups": {
    "model":   [{"name": "...", "calls": 0, "tokens": {...}, "runs": 0, "wall_p50": null, "wall_p90": null, "n": 0, "wall_kind": "none"}],
    "type":    [...], "key": [...], "project": [...]
  },
  "coverage": [{"cli": "pi", "runs": 8, "attribution": "exact"},
               {"cli": "claude", "runs": 1, "attribution": "exact"},
               {"cli": "codex", "runs": 1, "attribution": "unknown_cli"}],
  "sources": {"worker": 9, "pm": 3}
}
```

- `null` = 未知（渲染 `-`）；**不存在 `cost`/`usd`/`amount` 键**（AC-008）。
- 未知 token 的行 `tokens` 为 `null` 而不是 0（AC-013）。
- `wall_kind` = 该行 `wall_p50/wall_p90/n` 的**样本来源**，取值 `run` / `session` / `none`（T-06）：
  - `run`：台账 `wall_s`（spawn → reap，秒~分钟级）；
  - `session`：会话跨度（header → 末条，小时~天级，`source=pm` 或台账缺失的 worker 会话）；
  - `none`：无可算的分位数（无样本，或样本 < 5），此时 `wall_p50/wall_p90` 均为 `null`、`n` 仍为有效样本数。
  - **绝不混源**：组内只要存在 run 墙钟，会话跨度就不进入分位数（哪怕 PM 样本更多、凑不满 5 也不回填）——
    否则 p90 会被 25 天的 PM 窗口抬成 44 h 量级（T-06 缺陷）。

## 6. 文本简报形态（固定样例进测试）

```
usage since 2026-10-12 (7d) · ledger 42 events · runs 12 (worker 9 / pm 3)

by model
  timi/glm-5.3-flashx      calls 84   in 1.2M  out 310k  cacheR 11.4M  cacheW 42k  wall p50 4m12s p90 11m03s  n 7
  timi/deepseek-v4.1-flash calls 36   in 620k  out 90k   cacheR 2.1M   cacheW 8k   wall p50 2m01s p90  3m40s  n 5

by type
  coding    ...        by key
  mw-usage-monitor ...  by project
  Multi-Workers ...

coverage: pi 8 runs (exact) · claude 1 (exact) · codex 1 (未统计)
```

纯 PM 组（`--source pm` 或无 worker 的同组）：会话跨度不是 worker 墙钟，墙钟单元格末尾加 `*`，
并在 `coverage:` 行之前插脚注：

```
by key
  pm                       calls 200    in 8.0M   out 900k   cacheR 40M    cacheW 300k   wall p50 2h10m  p90 6h41m* n 9

* = PM 会话跨度（header→末条），非 worker 墙钟

coverage: pi 13 runs (exact)
```

数字单位：`1.2M/310k` 三位有效；墙钟 `4m12s`；`n<5` 时 `p50/p90` 显 `-`。

`*` 规则（`wall_kind="session"`，T-06）：该行分位数来自 PM 会话跨度而非 worker 墙钟，`*` 加在墙钟单元格
末尾（p90 之后）；只要输出里出现至少一个 `*`，就在 `coverage:` 行**之前**插入脚注
`* = PM 会话跨度（header→末条），非 worker 墙钟`。`wall_kind="run"` 的行不出现任何新符号，输出形态与
此前一致。

## 7. 错误处理与边界

| 情形 | 行为 |
| --- | --- |
| 台账不存在 | `mw stats` 仍扫描会话（PM 数据可用），打印 `no ledger yet`；rc=0 |
| 台账坏行 | 跳过 + `ledger.bad_lines` 计数，不中断 |
| 会话文件坏行/半行（torn tail） | 该行跳过，其余继续（`timeline.py:398-420` 先例） |
| `--session-id` 非法（key 含大写/非法字符） | `new_session_id` 先把 key slug 化（`[^a-z0-9]+`→`-`）并截断，再自检 |
| `--since` 非法 | `mw stats` 打印可用格式，rc=2 |
| 无任何数据 | 打印 `no usage in window` + coverage，rc=0 |
| Windows 路径 | 一律 `pathlib` + `os.replace` 同卷；不拼 `\` |

## 8. 测试设计

| 文件 | 覆盖 |
| --- | --- |
| `packages/multi-workers/test_usage.py`（新） | `usage_dir()` env 序；`new_session_id` 合法性与唯一性；`append_event` 并发（4 线程 × 50 条，行数=200 且全部可 json 解析）；`scan_pi_session` fixture（assistant + compaction + 无 usage + 坏行）；`scan_claude_session` 按 message.id 去重；`build_report` 四组聚合/过滤/`n<5`→null/unknown_cli 不计入；`format_report_text` 与固定样例逐字比对 |
| `packages/multi-workers/test_stats_cli.py`（新） | `_parse_args(["stats",...])` 接受 `--project`；`cmd_stats` text/json 两路（redirect stdout）；无台账路径 rc=0；非法 `--since` rc=2 |
| `packages/multi-workers/test_launcher_run_ledger.py`（新） | 纯函数级：给 `_spawn`/`_poll_once` 用的 `usage` 调用形态（构造 record → `append_event` → `load_runs` 配对）；exit-3 分支写 end；`reconciled=true` 行 |
| `packages/coding-agent/test/suite/mw-stats-surface.test.ts`（新） | `MW_COMMAND_DESCRIPTION` 含 `stats`；`/mw stats` 转发参数（注入 runner 断言 argv 含 `stats` 且 `--project` 被追加）；错误输出走 notify |
| 既有 | `test_launcher*.py`、`test_task_type_parity.py`、agent-team-loop 相关 vitest 全绿 |

## 9. 落地顺序与风险

1. `usage.py` + `test_usage.py`（无外部依赖，先立口径）
2. launcher 钩子 + `test_launcher_run_ledger.py`
3. `mw.py` `stats` + `test_stats_cli.py`
4. TS `/mw stats` + vitest
5. CHANGELOG/README

**已知风险**

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| 旧 `serve`（2026-10-15 代码）仍跑着 | launcher 钩子不生效 → 台账空 | 落地后需 `/mw restart`；缺数据时 `mw stats` 显式说明 `no ledger yet` |
| launcher 高频 spawn 时每条事件两次文件 open | 微小开销 | 实测基准：单次 append < 2 ms（测试断言上限 50 ms） |
| `--session-id` 影响 `/resume` 列表可读性 | worker 会话以 `mw-<key>-<pid>-<seq>` 出现 | 视为收益（可辨），RQ1 §4 已确认 |
| 会话文件增长（2.68 GB） | 扫描变慢 | header 粗筛 + 窗口过滤；>30 天窗再议 rollup |
