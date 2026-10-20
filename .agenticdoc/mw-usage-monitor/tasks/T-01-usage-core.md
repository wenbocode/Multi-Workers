# T-01: usage.py 口径内核（扫描 + 台账 + 聚合 + 渲染）

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-002, AC-003, AC-004, AC-005, AC-007, AC-008, AC-011, AC-013
依据: `.agenticdoc/mw-usage-monitor/design.md` §2/§3.1/§5/§6/§8；`spec.md` v0.2 §2/§3；
`evidence/research/spec-rq1-pi-session-usage-20261019.md`（§1/§3/§5/§6）、`spec-rq3-cli-worker-logs-20261019.md`（§2b/§4）、`spec-rq4-surface-storage-20261019.md`（§3/§4）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（pi 之上构建 Agent Team 并行开发框架；mw 从"能调度"补到"可回答成本"）。
- 已核实起点（自行复核，勿凭本卡断言）：
  - `packages/multi-workers/mw_common.py:2369-2382`：`acquire_lock(lock_file, retries=20, base_delay=0.05)` /
    `release_lock`，`O_CREAT|O_EXCL` + 指数退避，docstring "Same protocol as the TS side"。
  - `packages/multi-workers/mw_common.py:2481-2503`：`archive_stale_entries`，**锁内 append** 的唯一先例。
  - `packages/multi-workers/mw_common.py:685-703`：`machine_rag_servers_path` 的显式 env 解析序
    （`MW_*_FILE` → `MW_*_HOME` → `HOME` → `USERPROFILE`）——本任务 `usage_dir()` 照此形态。
  - `packages/multi-workers/decision.py:941-970`：JSONL append（`encoding="utf-8"`, `newline="\n"`,
    `ensure_ascii=False`, 每条一行、best-effort 不抛）。
  - `packages/multi-workers/mw.py:6933`：定宽 f-string 列模板 `f"  [{mark}] {c['id']:<18} {c['detail']}"`。
  - `packages/multi-workers/pytest.ini` 存在；测试用 `argparse.Namespace` 直调 `mw._cmd_*` 是既有风格
    （`test_rag_cli.py:207-247`）。
- 已定口径（**不要重新设计**，全部有证据）：token 权威源 = pi 会话 JSONL；一条 assistant message = 一次
  provider 响应（直接相加，不去重，失败尝试是 `EMPTY_USAGE`）；`compaction` entry 的 usage 也计入；
  四分量分列（`input/output/cache_read/cache_write`），`total` 由分项求和；claude 必须按 `message.id` 去重
  （不去重虚增 1.41–1.87×）且 `input_tokens` 本身就是非缓存输入；codex v1 **不读日志**；未知 token 为 `null`
  （渲染 `-`），**绝不写 0**；台账只存运行元数据，token 查询时 join。
- 隐私边界：只读 `type/model/provider/timestamp/usage/message.id/header(cwd,id)`，**不读 message.content 正文**。

## 要求

1. `usage_dir() -> pathlib.Path`：`MW_USAGE_DIR`（可注入测试）→ `USERPROFILE` → `HOME` → `~/.mw/usage`；
   仅在写入时 `mkdir(parents=True, exist_ok=True)`。配套 `ledger_path()`=`<dir>/runs.jsonl`、
   `lock_path()`=`<dir>/runs.jsonl.lock`。
2. `append_event(record: dict) -> bool`：`acquire_lock` → `open("a", encoding="utf-8", newline="\n")` 写一行
   `json.dumps(record, ensure_ascii=False, sort_keys=False)` → `release_lock`；任何异常返回 `False` 且
   **不抛**（launcher 侧不得被台账影响）。
3. `new_session_id(key: str, pid: int, seq: int) -> str`：`mw-<slug(key)>-<pid>-<seq>`，slug 规则
   `re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")`，并与 pi 的 `assertValidSessionId` 同款正则自检
   （`^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$`；不合法则抛 `ValueError`）。
4. `parse_since(text: str, now: datetime|None=None) -> datetime`：支持 `7d` / `24h` / `30m` / `YYYY-MM-DD`；
   非法抛 `ValueError`（调用方转 rc=2）。
5. `load_runs(since, filters: dict) -> tuple[list[dict], dict]`：读台账、按 `run_id` 配对 `start`/`end`
   （`end` 缺失 → `open_run=True`，`wall_s` 保持 `None`）、应用 `key/type/model/project/source` 过滤；
   返回 `(runs, meta)`，`meta={events, bad_lines, open_runs, path}`。坏行跳过并计数。
6. `iter_session_files(root: pathlib.Path, since: datetime) -> Iterator[pathlib.Path]`：先按 mtime 粗筛，
   再读首行 header（`type:"session"`）的 `timestamp` 复核；**不做全量 json 解析**。
7. `scan_pi_session(path) -> dict`：逐行 `"assistant"` 子串预滤 → `json.loads`；累加
   `message.usage{input,output,cacheRead,cacheWrite}` 与 `type=="compaction"` 的 `usage`；
   返回
   `{session_id, cwd, started_at, ended_at, models: {"<provider>/<model>": {input,output,cache_read,cache_write,requests}}, events: [(ts_iso, model_key, tokens_dict)]}`。
   `session_id` 从文件名 `<ts>_<id>.jsonl` 解析，header 的 `id` 优先。
8. `scan_claude_session(session_id: str, roots: list[pathlib.Path]) -> dict|None`：找
   `<root>/<uuid>.jsonl` 与 `<root>/<uuid>/subagents/*.jsonl`（同 uuid 目录），按 `message.id` **去重**
   （取首条），字段 `message.usage{input_tokens, output_tokens, cache_creation_input_tokens,
   cache_read_input_tokens}`；目录不存在返回 `None`（调用方记 `unknown_cli`）。
9. `build_report(now, since, filters) -> dict`：严格产出 `design.md` §5 的 JSON 契约（键名逐字一致，
   **不含任何 cost/usd/amount 键**）；四组 `model/type/key/project`；`coverage` 按 cli 聚合；
   `sources` 统计 worker/pm；`n<5` 时 `wall_p50/wall_p90` 为 `null`；`unknown_cli` 的 run 不计入 token 组。
   归因规则：`session_id` 以 `mw-` 开头 → `source=worker` + 从 id 解析 key；否则 `source=pm`。
10. `format_report_text(report) -> str`：按 `design.md` §6 的行组形态与单位（`1.2M/310k`、`4m12s`、
    尾部 `coverage:` 行）；`None` 渲染 `-`；无数据打印 `no usage in window` + coverage。
11. `_percentile(values, p)`：线性插值，`len<5` 返回 `None`；`n` 为样本数。
12. 不得实现 rollup、不得改 `launcher.py`/`mw.py`/TS、不得新增依赖。

## 写入允许面

- `packages/multi-workers/usage.py`（新建）
- `packages/multi-workers/test_usage.py`（新建）

## 写入禁止面

- 仓库其它任何文件（`launcher.py`、`mw.py`、TS、CHANGELOG、其它 key 目录）
- `~/.pi`、`~/.codex`、`~/.claude`（只读解析；测试一律用 `tmp_path` fixture，**不得读真实 HOME**）

## 验收命令

```powershell
cd H:\git\Multi-Workers\packages\multi-workers
python -m py_compile usage.py
python -m pytest test_usage.py -q
```

`test_usage.py` 必须覆盖（8 类）：
1. `usage_dir()` 的 env 优先级（`MW_USAGE_DIR` 覆盖）；2. `new_session_id` 合法/非法/含大写与空格的 key；
3. `append_event` 并发：4 线程 × 50 条 → 200 行且逐行可 `json.loads`（无交错）；
4. `scan_pi_session`：assistant + compaction + 无 usage 消息 + 半行末尾（torn tail）+ 多模型；
5. `scan_claude_session`：同 `message.id` 写 3 行 → requests=1、tokens 不虚增；subagents 目录并账；
6. `build_report`：四组聚合、`--key/--type/--model/--project/--source` 过滤、`n<5` → `null`、
   codex run 进 `coverage` 但不进 token 组、`null` 而非 0；
7. `format_report_text`：与测试内 fixture 逐字比对（含 `-` 与 `coverage:` 尾行）；
8. `parse_since` 三种形态与非法输入。

## 改动历史

（首次改动，填写：新增文件、每个函数的取舍、被否决的替代方案。）
