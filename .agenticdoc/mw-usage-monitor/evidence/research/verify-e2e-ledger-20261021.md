# verify-e2e-ledger-20261021 (um-t07-e2e-ledger-smoke)

只读验证：ledger 端到端可用性 + 本次派发自身的台账行。HEAD `744e95b97`。

## 结论

1. **goal 对齐**：本 key 交付的机器级 append-only 台账 + `mw stats` 只读聚合，正是 goal 里「mw 后台服务（常驻运行）」与「文件驱动的去中心化协调」两者的可观测面——每次 spawn/reap 由 launcher 直接追加一行事件到 `~/.mw/usage/runs.jsonl`，不引入任何中心化状态库或 DB（`packages/multi-workers/usage.py:240` `append_event` 的注释即此契约）。
2. **`usage.py` 在 `build_report` 之前共有 45 个模块级函数**（`def ` 行，99–942），`build_report` 定义于 `packages/multi-workers/usage.py:981`。函数名清单见证据 §2。
3. **`--since` 默认窗口 = `7d`**：argparse 侧 `packages/multi-workers/mw.py:9674` `stats_p.add_argument("--since", default="7d", ...)`；`cmd_stats` 内还有兜底 `mw.py:9630` `since_text = str(args.since or "7d").strip()`。**卡片里的 `mw.py:7016` 是失效行号**：该 HEAD 上 7016 行属于 `_gate_downstream_keys`，`def cmd_stats` 实际在 `mw.py:9623`（代码本身存在，只是卡片锚点陈旧）。
4. **我这次运行的那一行就在台账里，端到端链路打通**：`runs.jsonl:335`，`event=start`、`task_key=um-t07-e2e-ledger-smoke`、`run_id=20261021T080045Z-17812-2`、`session_id=mw-mw-usage-monitor-17812-1` 与进程 env `PI_SESSION_ID` 完全一致，且该 id 能在 `~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-21T08-00-49-345Z_mw-mw-usage-monitor-17812-1.jsonl` 的 header `{"type":"session","id":"mw-mw-usage-monitor-17812-1",...}` 中命中 —— launcher 写台账的 session_id 与 pi 实际落盘 session 是同一个 join key。该 run 目前**无 `end` 行**（我是 running 态，`open_run=True` 符合 AC-004 预期，等 reap 后写 `end`）。

## 证据

### §1 goal.md（只取与本 key 对齐的一句）

`H:\git\Multi-Workers\.agenticdoc\goal.md` 核心交付第 1 条“mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行” + Key Constraints “不引入中心化调度器：协调通过文件系统（_workers.parallel + 文件锁）”。→ 台账与之一致：单文件 append-only + `runs.jsonl.lock`（`usage.py:60-61`），无外部服务。

### §2 usage.py 模块级函数（`build_report` 之前，45 个）

```
$ (Select-String -Path usage.py -Pattern '^def ') | Where LineNumber -lt 981 | Count
COUNT: 45
build_report line: 981
```
```
99: _env                    103: _env_value              107: _home_dir
117: usage_dir              126: ledger_path             130: lock_path
134: pi_sessions_dir        147: claude_projects_dir     162: _as_utc
168: _parse_iso             183: _iso                    187: _local_tz
192: _as_int                203: _add_tokens             212: _new_token_map
216: _token_total           222: _percentile             240: append_event
268: new_session_id         290: _key_from_session_id    300: _session_id_from_path
312: parse_since            335: _window_label           349: _read_header
369: iter_session_files     397: _pi_model_key           405: _pi_tokens
414: scan_pi_session        517: _claude_model_key       522: _claude_session_files
557: _jsonl_files           564: _claude_tokens          574: scan_claude_session
669: _norm                  673: _basename               677: _project_matches
693: _project_name          698: _run_matches            717: load_runs
842: _window_events         862: _wall_from_session      870: _unit_matches
886: _new_group_entry       897: _finalize_group         942: _coverage_rows
```
（上表按 grep 输出行的 `行号: 函数名` 重排为 3 列，一名不差；写面函数：`append_event` 240 / `new_session_id` 268，读侧：`load_runs` 717。）

### §3 cmd_stats 默认 `--since`

```
9623: def cmd_stats(args: argparse.Namespace) -> int:
9630:     since_text = str(args.since or "7d").strip()
9674: stats_p.add_argument("--since", default="7d", metavar="WINDOW",
9675:                          help=f"Window to report: {_STATS_SINCE_HINT} (default: %(default)s)")
```
对照卡片锚点：
```
$ Get-Content mw.py | Select -Skip 7005 -First 12
7016:         return [k.key for k in stage.keys]
...
7018: def _gate_downstream_keys(...)   # 7016 在其函数体内
```
→ `mw.py:7016` 与 `cmd_stats` 无关，实际位置 `mw.py:9623`。

### §4 台账（`C:\Users\wenbozhou\.mw\usage\runs.jsonl`，只读）

文件状态：存在，`117497` bytes，`LastWriteTime 2026/10/21 16:00:45`。目录 `C:\Users\wenbozhou\.mw\usage` 存在，仅此 1 个文件（`runs.jsonl`；无残留 `runs.jsonl.lock`）。

定位命令（task_key 匹配 + pid 交叉核对）：
```
$ Select-String -Path runs.jsonl -Pattern 'um-t07-e2e-ledger-smoke' | ForEach { "LINE $($_.LineNumber)" }
LINE 335
$ Select-String -Path runs.jsonl -Pattern '20261021T080045Z-17812-2'
L335: {"event": "start", "run_id": "20261021T080045Z-17812-2", "ts": "2026-10-21T08:00:45+00:00", "source": "worker", "key": ...
$ Select-String -Path runs.jsonl -Pattern '"key": "mw-usage-monitor"' | Measure | % { $_.Count }
mw-usage-monitor rows: 1
```

**我这一行（原样，截断到 400 字符，实际 len=455）**：
```json
{"event": "start", "run_id": "20261021T080045Z-17812-2", "ts": "2026-10-21T08:00:45+00:00", "source": "worker", "project": "H:\\git\\Multi-Workers", "key": "mw-usage-monitor", "task_key": "um-t07-e2e-ledger-smoke", "type": "research", "role": "research", "cli": "pi", "attribution": "exact", "session_id": "mw-mw-usage-monitor-17812-1", "model": "timi/deepseek-v4.1-flash", "model_source": "config:re
```
被截掉的尾部（同一行）：`search", "pid": 17236, "cwd": "H:\\git\\Multi-Workers"}`。

关键字段自检：
- `model=timi/deepseek-v4.1-flash` ↔ env `PI_PROVIDER=timi` / `PI_MODEL=deepseek-v4.1-flash`（一致）。
- `model_source=config:research` ↔ 卡片 `type: research`（一致）。
- `session_id=mw-mw-usage-monitor-17812-1` ↔ env `PI_SESSION_ID`（逐字一致），且 `<usage.py:268>` 的 `mw-<slug>-<pid>-<seq>` 形态成立。
- `pid=17236` **不是** pi 进程 pid：见残留 §1。

台账整体完整性（临时脚本，`%TEMP%`，运行后删除）：
```
lines: 337 bad: 0 []
events: {'start': 172, 'end': 156, 'spawn_failed': 9}
distinct start run_ids: 172 with end: 154
open runs: 18
my rows: 1
line 335 run_id 20261021T080045Z-17812-2 pid 17236 session mw-mw-usage-monitor-17812-1 ended False
```
```
run_ids with >1 end: 0
orphan ends (no start): 2
20261020T131424Z-61436-1 (158, '2026-10-20T13:14:24+00:00', 'done', True)
20261020T131424Z-61436-2 (159, '2026-10-20T13:14:24+00:00', 'done', True)
spawn_failed only: 9
open runs: 19  oldest: ['2026-10-19T10:20:37+00:00', ...]
```
（`open runs` 18 与 19 的差异：前一条口径只统计“有 start 行”的 run；后者把 `spawn_failed` 单行也算进“无 end”集合，`load_runs` 里两者分别走 `running` / `spawn_failed` 分支，见 `usage.py:717` 起。）

### §5 join key 侧的 session 文件

```
$ Get-Item <PI_SESSION_FILE>
Name          : 2026-10-21T08-00-49-345Z_mw-mw-usage-monitor-17812-1.jsonl
Length        : 94675
LastWriteTime : 2026/10/21 16:01:23
$ (Get-Content ... -TotalCount 1)
{"type":"session","version":3,"id":"mw-mw-usage-monitor-17812-1","timestamp":"2026-10-21T08:00:49.345Z","cwd":"H:\\git\\Multi-Workers"}
```
`header.id` == 台账 `session_id` → `usage.build_report` 的 `by_session` 关联（`usage.py:1006` 附近）可用。

## 残留与未验证

1. **`pid` 语义与直觉不同（潜在定位陷阱）**：台账 `pid=17236` 是 launcher spawn 出来的 `cmd.exe` wrapper（`Get-Process -Id 17236` → `ProcessName=cmd`，`StartTime=2026/10/21 16:00:45`，仍存活）；真正跑 pi 的是它的子进程 `node.exe PID=30696 PPID=17236`；`session_id` 里的 `17812` 又是生成 id 时的 python 进程号。三种 pid 混用，`task_key + pid` 定位只在“台账内自洽”这个层面成立，不能拿 pi 进程 pid 反查台账。未验证这是否是有意设计（launcher 记录 spawn 直接子进程 pid 大概率为实现现状而非契约）。
2. **reap 侧未验证**：我这一行只有 `start`，`end`（`exit` / `wall_s` / `status`）要等 launcher reap 后写入，本报告产出时不存在。因此“spawn→reap 完整闭环 + `wall_kind=run` 的 p50/p90 采样”这条路径本次只间接验证（基于台账里 154 个已有 `start+end` 配对与 `wall_s` 字段存在）。
3. **未跑 `mw stats`**（任务硬约束，PM 会跑）：`build_report` 的真实输出、`--json` 契约、文本渲染（含 `SESSION_WALL_FOOTNOTE` 中文与 `*` 标记）均未验证；claude/codex 分支、`--key/--type/--project/--source` 过滤未验证。
4. **2 条无 `start` 的 `end` 行（`reconciled=true`，158/159）在 totals 中不可见**：`load_runs` 里 `spawned = bool(start)`，这类 slot 不计入 `totals.runs` / `coverage`，只在 `ledger.events` 计数里体现。是否为设计意图未确认（可能是启动期 reconcile 补写的孤儿，属预期的“可见但不计 run”）。
5. **9 条 `spawn_failed`、19 条无 `end` 的历史 open run**（最早 2026-10-19T10:20:37Z）未逐条追因；`usage.py:717` 的 open-run 语义（`wall_s` 保持 `None`，不猜 0）从代码与字段看成立，但没有 `mw stats` 输出佐证。
6. 卡片锚点 `mw.py:7016` 已失效（应为 `mw.py:9623`）；建议 PM 在 T-07 收口时更新卡片/派发卡的 `文件:行号` 引用口径。
7. 行数口径差异：PowerShell `Measure-Object -Line` 报 335，python `splitlines()` 报 337（末尾换行/空行计法不同），以 python 的 337 非空行、0 bad lines 为准；未深究差异根因。

## 上下文来源

- `.agenticdoc/goal.md`（全篇读取，仅引用核心交付第 1 条 + 去中心化约束）
- `.agenticdoc/mw-usage-monitor/workers/um-t07-e2e-ledger-smoke/task.md`（本次派发卡）
- `packages/multi-workers/usage.py`（全篇读取，共 1290+ 行）
- `packages/multi-workers/mw.py`（`cmd_stats` 9623–9652、`stats` argparse 9660–9690、卡片锚点 7006–7030）
- `C:\Users\wenbozhou\.mw\usage\runs.jsonl`（只读，337 行全量 JSON 解析）
- 进程 env：`PI_SESSION_ID` / `PI_SESSION_FILE` / `PI_WORKER_TASK` / `PI_MODEL` / `PI_PROVIDER`
- 进程表（`Get-CimInstance Win32_Process` 过滤 `um-t07-e2e-ledger-smoke`）+ pi session header
- `git log -1` = `744e95b97 feat(multi-workers): machine-level usage ledger with mw stats and /mw stats`

[VERIFY] 24 次只读 bash 调用（含 2 次 PowerShell 复合语句语法错误的即时重试）+ 4 次文件 read；未执行 `mw stats`、未跑任何测试、未修改仓库任何文件，临时脚本仅写 `%TEMP%` 并在运行后删除。
