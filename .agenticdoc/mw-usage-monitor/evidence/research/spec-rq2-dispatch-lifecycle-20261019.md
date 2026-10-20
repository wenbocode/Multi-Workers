# RQ2 派发链路元数据与墙钟时间点调研（spec-rq2-dispatch-lifecycle-20261019）

key: mw-usage-monitor / um-rq2-dispatch-lifecycle · type: research · 2026-10-19
范围：packages/multi-workers（launcher.py / mw.py / mw_common.py / autopilot/*）+ packages/coding-agent/src/extensions/agent-team-loop（pm / worker / shared）+ 运行期样本（.mw/、.agenticdoc/_autopilot/、本 key worker 目录）。只读调研，未改任何仓库文件。

## 0. 结论先行

1. **worker 进程全系统只有一个 spawn 点**：`launcher._spawn` 内 `launcher.py:2450 proc = subprocess.Popen(cmd, **spawn_kwargs)`。PM `/worker`（pm/ui-bridge.ts:2911）、`dispatch_worker` 工具（ui-bridge.ts:2338）、conductor 的 `dispatch.dispatch`（autopilot/dispatch.py:1335）都只写 `_workers.parallel` 队列行、从不 spawn；fallback 同模型重试、fallback 换模型、pending 槽位补发三条重派路径也全部收敛回 `_spawn`（launcher.py:2190、914-940、2210-2270）。**台账只需在 launcher 一处打 spawn/end 钩子即可覆盖全部 worker 运行**。
2. **start 行钩子**插在 `launcher.py:2451 running_procs[entry["task_key"]] = proc` 之后（_spawn 成功分支尾部、`_update_status(..., "running")` 2461 前后皆可），可用局部变量：`entry / project_dir / config / proc(→pid) / model_value / model_source / effective / env / cmd / spawn_kwargs["cwd"] / fallback_index / tried_models / main_model / target_config`。**end 行钩子**插在 `_poll_once` reap 循环 `launcher.py:2162 code = proc.returncode if proc.returncode is not None else 1` 之后，可用局部变量：`key / proc / code / entry / task_dir / reap_entries`；三个分支都要覆盖——正常终止（2185-2186）、exit-3 重派分支（2177-2183，**进程已死必须照写 end 行**，continue 只是行状态保持 running）、spawn 失败路径（2460-2467，从未到达 Popen，无 pid，可选记 spawn_failed 事件）。
3. **模型解析权威链**：`mw_common.resolve_dispatch_model`（mw_common.py:300-324）——task.md `model:` > `.mw/dispatch.yml models.<role>` > `.mw/window-model` > `""`（per-cli 硬编码，`_build_command` launcher.py:1776-1806 补 glm-5.3 / gpt-5.6-sol）。`type:`→role 映射 `TASK_TYPE_TO_ROLE`（mw_common.py:144-158）；provider 前缀重映射 `_effective_entry`（launcher.py:243-277，如 claude/x → provider=anthropic）。**台账应记两级：spawn 时刻「请求模型+来源」（`model_value`/`model_source`，source ∈ task|config:<role>|window|default|fallback）+ worker 运行时「实际生效模型」（trace.log `[MODEL]` 行，output-writer.ts:604-610，D-116）**。依据：请求 "" 时实际模型是 per-cli 硬编码默认（1778/1801），且 `_effective_entry` 会改写 provider——只有 `[MODEL]` 行是 pi 解析后的最终事实。
4. **pid 双写且一致，session_id 全链路无生产者**：launcher 侧 `proc.pid`（launcher.py:2450-2451）；worker 自报 `run.json.pid = process.pid`（worker-mode.ts:2616 附近构造、run-store.ts:53）与 trace.log `[START] pid=<pid>`（worker-mode.ts:769-778）。pi session id 未落任何 mw 文件（全仓检索仅命中 RAG MCP HTTP 会话，rag/mcp-client.ts:69-167，无关）——台账 `session_id` 字段现阶段无来源，需上游扩展新增或以 `run_id`（`<task_key>@<iso>`，run-store.ts:106-108）替代。
5. **没有任何现有日志可直接当台账**：launcher.log / conductor.log 每 serve 会话截断（mw.py:283-289，`"w"` 模式）；worker.log 每 spawn 截断（launcher.py:2436 `open(..., "wb")`）；queue 行 `updated_at` 每次状态变更被改写（mw_common.py:2441）、且队列可被重建（IN-3）；timeline.jsonl 是唯一机器级 JSONL 但不含 worker pid/model/exit。唯一 append-only 的时间锚是 per-task trace.log（[START]/[MODEL]/[END]/[TIMEOUT]/[MODEL_FALLBACK]/[MODEL_RETRY]）与 `_workers.stale.parallel`（append + 锁，mw_common.py:2493-2497）——**新台账必要，钩子见 §2**。
6. **并发/锁先例齐备**：Python `acquire_lock` O_CREAT|O_EXCL + 指数退避（mw_common.py:2369-2382，retries=20×0.05s）、TS `openSync(...,"wx")`（file-lock.ts:9-36）；整文件原子写 tmp+replace（mw_common.py:2391-2402、mw.py:178-183、worker-store.ts:222-225）。Windows JSONL 追加三坑在库内均有现成对策：`newline="\n"` 防 CRLF 翻倍（timeline.py:275-276）、torn tail 修复（timeline.py:398-420）、单写者原则（timeline.py:281-283，D-109）。跨 launcher/跨项目共享台账建议 per-launcher 分片文件（launcher-beat.<pid> 先例，mw_common.py:2797-2812）或每写持锁。

---

## 1. 一次 worker 运行的全部可观测元数据

逐项「字段 → 谁在何时知道 → 文件:行号 + 原文」。行号以当前工作区文件为准。

### 1.1 project（项目根）
- launcher：`run(project_dir=...)` 由 CLI `--project` 传入（launcher.py:2504 `parser.add_argument("--project", required=True...)`；2538-2545 `run(project_dir=project, ...)`）。
- serve：`cmd_serve` mw.py:265 `project_dir = pathlib.Path(args.project).resolve()`。
- worker 侧可从 `entry["task_path"]`（绝对路径）推导项目根；run.json 另存 `owner_key`（见下）。

### 1.2 key（owner key，如 mw-usage-monitor）
- 队列行 task_path → key：mw_common.py:2276-2281
  ```python
  def worker_path_key(task_path: str) -> str:
      match = _WORKER_PATH_KEY_RE.search(str(task_path or "").replace("\\", "/"))
      return match.group(1) if match else ""
  ```
  正则 mw_common.py:2273-2274 `_WORKER_PATH_KEY_RE = re.compile(r"(?:^|/)\.agenticdoc/([^/]+)/workers/")`。
- worker 自报：worker-mode.ts:2617 `owner_key: path.basename(path.dirname(path.dirname(taskDir))),`（写入 run.json，2626 `writeRunState(taskDir, runState)`）。
- 实测样本（本 worker run.json）：`"owner_key": "mw-usage-monitor"`。

### 1.3 task_key
- 队列第 1 列：mw_common.py:2002-2019 `parse_worker_line` → `"task_key": parts[0]`；launcher 在 `_spawn`/reap 全程持有 `entry["task_key"]`（launcher.py:2451/2462）。

### 1.4 type（任务类型）
- 派发时写 task.md 头：conductor 渲染 dispatch.py:987 `f"type: {task_type}"`；PM 侧 writeDispatchTaskMd frontmatter（ui-bridge.ts:2569-2578 `type: typeField`）。
- spawn 前读回：launcher.py:194-212
  ```python
  def _read_task_md_fields(task_path: str) -> tuple[str, str]:
      ...
      task_type = mw_common.read_task_type(content).type or ""
      model_m = re.search(r"^model:[ \t]*(\S+)[ \t\r]*$", content, flags=re.MULTILINE)
      return (task_type, model_m.group(1) if model_m else "")
  ```
  `read_task_type` 单源：mw_common.py:595-610（header 区首个 `type:`，BOM 容忍，body 行不算）。
- worker 侧：worker-mode.ts:2568 `const meta = parseTaskMd(taskPath)`（564 起；`timeoutMin` 在 570-594）。
- 落盘证据：trace.log `[START] ... type=research`（output-writer.ts:595-601）；run.json `"kind": "research"`（run-store.ts:42-44）。

### 1.5 role（语义桶）
- 纯派生、不落盘：mw_common.py:144-158
  ```python
  TASK_TYPE_TO_ROLE: dict[str, str] = {
      "coding": "coding", "phase-writer": "coding", "repair": "coding", "roadmap-writer": "coding",
      "review": "review", "verifier": "review", "reviewer": "review",
      "research": "research", "rag-research": "research", "vision": "vision",
  }
  ```
  在 `resolve_dispatch_model` mw_common.py:319 使用：`role = TASK_TYPE_TO_ROLE.get(task_type, "coding")`。TS 镜像 dispatch-models.ts:58 `DISPATCH_ROLE_BY_TYPE`、:78 `roleForTaskType`。

### 1.6 cli
- 队列第 3 列：mw_common.py:2008 `"cli": parts[2]`；registry 固定 cli：dispatch.py:79-127 `DispatchType(..., "pi", "timi", ...)`（全部 7 个注册类型都是 pi/timi）；PM `/worker` 第一个参数（ui-bridge.ts:2919 `const cli = (parts[0] ?? "").toLowerCase()`，合法值 2979 `["claude","codex","pi"]`）。
- spawn 命令按 cli 分支：`_build_command` launcher.py:1764-1806（pi / codex / claude / 兜底）。

### 1.7 provider（路由）
- 队列第 4 列：mw_common.py:2009 `"provider": parts[3]`；PM pi 硬编码：ui-bridge.ts:2546 `const provider = cli === "pi" ? "timi" : "";`（/worker 分支 2985 同式）。
- 模型前缀可改写 provider：launcher.py:243-277 `_effective_entry`：
  ```python
  prefix, model_id = mw_common.parse_model_value(model_value)
  ...
  if prefix in mw_common.MODEL_PREFIX_TO_PI_PROVIDER:
      ...
      return {**entry, "model": model_id, "provider": mw_common.MODEL_PREFIX_TO_PI_PROVIDER[prefix]}
  ```
- 前缀→provider 表：mw_common.py:127-138
  ```python
  MODEL_PREFIX_TO_PI_PROVIDER: dict[str, str] = {"timi": "timi", "claude": "anthropic", "codex": "openai-codex", "deepseek": "deepseek", "zai": "zai-coding-cn"}
  PROVIDER_ID_TO_PREFIX = {v: k for k, v in MODEL_PREFIX_TO_PI_PROVIDER.items()}
  CLI_PREFIX_TO_CLI: dict[str, str] = {"codex_cli": "codex", "claude_cli": "claude"}
  ```

### 1.8 provider 前缀（模型值前缀）
- 解析：mw_common.py:273-277
  ```python
  def parse_model_value(value: str) -> tuple[str, str]:
      value = value.strip()
      if "/" not in value:
          return "", value
      prefix, _, model_id = value.partition("/")
      return prefix.strip(), model_id.strip()
  ```
- 兼容判定：mw_common.py:285-297 `model_value_compatible`。

### 1.9 model（请求值 + 来源）
- 解析链（权威）：mw_common.py:300-324
  ```python
  def resolve_dispatch_model(*, cli, task_type, entry_model, config_models, window_model) -> tuple[str, str]:
      """...Chain: task.md `model:` (explicit, returned as-is) > dispatch.yml role
      default > current window model > "" (per-cli hardcoded default)."""
      if entry_model.strip():
          return entry_model.strip(), "task"
      role = TASK_TYPE_TO_ROLE.get(task_type, "coding")
      candidate = config_models.get(role, "").strip()
      if candidate and model_value_compatible(cli, candidate):
          return candidate, f"config:{role}"
      if window_model.strip() and model_value_compatible(cli, window_model):
          return window_model.strip(), "window"
      return "", "default"
  ```
- launcher 调用：launcher.py:166-188 `_resolve_entry_model`（读 dispatch.yml + task.md + window-model）；fallback 重派时绕过解析链：launcher.py:2403-2404
  ```python
  if model_override is not None:
      model_value, model_source = model_override, "fallback"
  ```
- 现有日志面（非持久、且 launcher.log 截断）：launcher.py:2423-2426
  ```python
  print(f"[launcher] {entry['task_key']}: model={model_value or '(route default)'} source={model_source}", flush=True)
  ```
  task.md 压过 role 默认时另有一行 evidence：launcher.py:216-238 `_model_override_note`（实测 launcher.log 样本 `[launcher] um-rq2-dispatch-lifecycle: model=timi/glm-5.3-flashx source=config:research`）。

### 1.10 model（最终生效 / 实际运行）
- spawn 命令里的 flag：launcher.py:2422 `cmd = _build_command(effective)`；1776-1806：
  ```python
  if provider == "timi":
      return ["pi", "--provider", "timi", "--model", model or "glm-5.3", "-p", starter]
  ...
  return ["codex", "exec", "-m", model or "gpt-5.6-sol", starter]
  ```
- 运行时最终事实（D-116）：worker session 启动写 trace.log：output-writer.ts:604-610
  ```ts
  export function appendModel(taskKey, agenticdocRoot, modelId): void {
      appendLifecycleLine(taskKey, agenticdocRoot, `[MODEL] ${new Date().toISOString()} model=${modelId}`);
  }
  ```
  （worker-mode.ts:2721 调用；PM watch 读它做模型徽标：ui-bridge.ts:840-882。）实测样本：`[MODEL] 2026-10-19T09:45:35.564Z model=glm-5.3-flashx`。

### 1.11 pid
- launcher：launcher.py:2450-2451 `proc = subprocess.Popen(cmd, **spawn_kwargs)` → `running_procs[entry["task_key"]] = proc`（`proc.pid` 即 worker 进程 pid；cmd[0] 已被 2432 `_resolve_cli` 解析为绝对路径，Windows 下是 .CMD shim 的直接执行，无中间 shell，pid 一致）。
- worker 自报：worker-mode.ts:769-778
  ```ts
  function appendStartPidLine(taskKey: string, agenticdocRoot: string): void {
      ...
      fs.appendFileSync(path.join(dir, "trace.log"), `[START] pid=${process.pid}\n`, "utf8");
  }
  ```
  （2595 `appendStartPidLine(meta.taskKey, meta.agenticdocRoot)`，D-115，先于第一轮 agent turn。）run.json：run-store.ts:53 `pid?: number`，构造于 worker-mode.ts:2611-2626。实测样本：`[START] pid=54460` 与 run.json `"pid": 54460`。
- Python 侧消费先例：autopilot/state.py 按此格式数 spawn（worker-mode.ts:765-767 注释原文 `^\[START\] pid=(\d+)\s*$`）。

### 1.12 cwd（spawn 工作区）
- launcher.py:2357-2371 `_worker_cwd`（dual→game_root / partition→partition_root / single→project_dir），注入 spawn_kwargs：launcher.py:2443-2447
  ```python
  spawn_kwargs: dict = {
      "env": env, "cwd": str(_worker_cwd(project_dir, target_config)),
      "stdout": log_file if log_file is not None else subprocess.DEVNULL,
      "stderr": subprocess.STDOUT if log_file is not None else subprocess.DEVNULL,
  }
  ```
- 派发时刻 cwd 依据落在 task.md profile block：`_task_profile_mode`（launcher.py:1965），tear 检查 `_check_config_tear`（launcher.py:2032-2059），失败即拒绝 spawn（`config torn: ... spawn refused`）。

### 1.13 启动时刻（墙钟）
- launcher 侧**无持久化时间戳**（launcher.log 打印行不带时间且整文件截断）。间接锚：
  - spawn 成功瞬间队列行 `updated_at` 被改写为 running：launcher.py:2459 `_update_status(project_dir, entry["task_key"], "running")` → mw_common.py:2441 `row["updated_at"] = updated_at`（`iso_now()` UTC 秒精度，mw_common.py:171-172）。
  - worker 侧第一事实：run.json `started_at`（worker-mode.ts:2620 `"started_at": new Date().toISOString(),`）；trace.log `[START] <iso> task=... type=...`（output-writer.ts:595-601，2701 调用）。实测样本两行：`[START] pid=54460` / `[START] 2026-10-19T09:45:35.527Z task=um-rq2-dispatch-lifecycle type=research phases=-`。

### 1.14 结束时刻（墙钟）
- reap 瞬间队列行 `updated_at` 终态改写：launcher.py:2185-2186 `status = _reap_status(task_dir, code, key)` → `_update_status(project_dir, key, status)`。
- worker 侧：trace.log `[END] <iso> exit=<c> elapsed=<sec>s tools=<n> phases=<d>/<t>|->`（output-writer.ts:737-750 appendEnd；worker-mode.ts:3211-3231 recordEnd 同步写）；run.json `ended_at`（worker-mode.ts:2693）；launcher 孤儿收敛会补 `mark_run_lost` 写 `ended_at`（mw_common.py:2199）。

### 1.15 exit code
- 进程级：launcher.py:2157 `finished = [k for k, p in running_procs.items() if p.poll() is not None]`；2162 `code = proc.returncode if proc.returncode is not None else 1`。
- 状态映射：launcher.py:588-594 `_exit_to_status`（0→done、2→needs-clarification、其余 failed）；产品优先覆盖：launcher.py:597-633 `_reap_status`（run.json 终态 outrank exit code，冲突打 stderr→launcher.log）。
- worker 侧自证：trace.log `[END] exit=`（解析器 mw_common.py:2772-2795 `parse_end_exit`，64KB 尾读，`_END_LINE_RE` 2775-2776）；run.json `exit`（run-store.ts:47-48）。

### 1.16 是否 fallback 换模型
- 状态全在 trace.log（launcher 重启可续）：写点 launcher.py:896-912
  ```python
  _record_trace_line(entry, f"[MODEL_FALLBACK] {mw_common.iso_now()} from={current} to={candidate} attempt={index + 1}")
  ...
  _record_trace_line(entry, f"[MODEL_RETRY] {mw_common.iso_now()} model={current} attempt={retries + 1}")
  ```
  skip 行 launcher.py:899-904 `[MODEL_FALLBACK-SKIP] ... candidate=... reason=...`。解析正则：launcher.py:466-471 `_MODEL_FALLBACK_RE`、483-486 `_MODEL_RETRY_RE`；历史读取 `_model_fallback_history`（497-512）、`_model_retry_history`（740-757）。
- 重派触发点（reap 内 exit 3 拦截）：launcher.py:2177-2183
  ```python
  redispatched = (
      entry is not None
      and code == 3
      and _try_model_redispatch(entry, project_dir, config, running_procs, log_handles)
  )
  ```
  `_try_model_redispatch`（launcher.py:777-914）两段式：同模型重试（`PI_WORKER_MODEL_ERR_MAX` 默认 2，488-489/730-754）→ fallback 链（`fallback_models:` 配置，`_fallback_chain` 519-537、候选预检 `_fallback_candidate_available` 759-775）。
- worker 侧协同：exit 3 + run.json `model_exhausted: true`（worker-mode.ts:3805；launcher 判定 `_run_model_exhausted` launcher.py:635-648）。

### 1.17 是否超时（idle / wall）
- 判定在 worker：worker-mode.ts:3250-3251
  ```ts
  const budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS);
  const idleMs = resolveIdleMs(process.env.PI_WORKER_IDLE_MS);
  ```
  链：worker-mode.ts:247-253 `resolveBudgetMs`（task.md `timeout:` 分钟 > env > `DEFAULT_BUDGET_MS = 60*60_000`（235））；255-261 `resolveIdleMs`（`DEFAULT_IDLE_MS = 10*60_000`（240），env 可调）；在飞工具上限 30m（267-281）。wall 定时器：3537-3542；kill：3314-3317。
- 落盘证据：`[TIMEOUT] <iso> idle:|wall: <detail>`（output-writer.ts:655-663 appendTimeout；3285 调用）；超时即 exit 1（3317）或转 exit 3 模型耗尽路径（3287-3291）。
- task.md `timeout:` 的派发来源：`_worker_timeout_min`（dispatch.py:821-849，仅项目层显式配置才渲染）→ render_task_md dispatch.py:955-957 `lines.append(f"timeout: {int(worker_timeout_min)}")`。

### 1.18 是否崩溃被重派 / 孤儿收敛
- 孤儿收敛：`_reconcile_orphans`（launcher.py:1857-1942）——`[END]` 尾读、run.json 终态、silence 规则（`PI_WORKER_ORPHAN_DEAD_MIN` 默认 90m，mw_common.py:2860-2873）、beat 让位（mw_common.py:2815-2845）。`lost` 只加不改产品：`mark_run_lost`（mw_common.py:2180-2206，tmp+replace，保留其余字段）。
- 原因落盘：`_record_reconcile`（launcher.py:115-127）写 worker.log；`[LAUNCHER]` 行写 trace.log（`_record_trace_line` launcher.py:2019-2030，tear/rag-tear 拒绝也走这里 2036-2059/2103-2107）。
- ack 收敛：launcher.py:2200-2224（`read_acked` mw_common.py:2134-2156）。

## 2. 台账写入钩子点

### 2.1 start 行（spawn 成功后立刻写）
- 位置：`launcher.py:2451 running_procs[entry["task_key"]] = proc` 之后、`_update_status(..., "running")`（2459）前后皆可（建议紧随 2451，先于 2459，保证台账行先于队列状态）。
- 该处可拿到的局部变量（`_spawn` 作用域，2373-2459）：
  `entry`（task_key/task_path/cli/provider/model 列）、`project_dir`、`config`（providers/credentials）、`proc`（**pid = proc.pid**）、`model_value`（请求模型值）、`model_source`（task|config:<role>|window|default|fallback）、`effective`（provider 改写后的行）、`env`（已剥离凭证+注入 RAG/fallback 链）、`cmd`（最终 argv，含解析后可执行路径与 `--model` flag）、`spawn_kwargs`（含 cwd）、`fallback_index`/`tried_models`/`main_model`（重派上下文）、`target_config`（workspace mode/cwd 依据）、`rag_config`。
- 时间戳：调用点需自取 `mw_common.iso_now()`（UTC 秒精度）或 `time.time()`；_spawn 内现无现成时间变量。

### 2.2 end 行（reap，含异常/超时/被 kill 分支）
- 位置：`_poll_once` reap 循环内，`launcher.py:2162 code = proc.returncode ...` 之后。该处可拿到：`key`、`proc`、`code`、`entry`（2171 `entry = reap_entries.get(key)`，可能为 None——队列行丢失时仍要写 end）、`task_dir`（2184）、`reap_entries`。
- 三分支语义：
  1. 正常终止：2185-2186 `_reap_status` + `_update_status(..., status)`——end 行记 `code` 与 `status`。
  2. exit-3 重派（2177-2183 `if redispatched: continue`）：**进程确实结束了**，end 行必须在 continue 前写（`code=3`，后续 `_spawn` 会写新的 start 行）；否则台账会丢一次进程生命周期。
  3. 超时/被 kill：没有独立分支——idle/wall 超时与被杀都表现为 returncode（worker 自杀式 `process.exit(1)`，worker-mode.ts:3317）；超时判据应回读 trace.log `[TIMEOUT]` 行（mw_common 已有 `[END]` 解析先例 parse_end_exit 2772-2795，可同法加 TIMEOUT 尾读）。
- spawn 失败路径（2460-2467）：从未到达 Popen，无 pid；可选记 `spawn_failed` 事件（reason 已有 `_record_spawn_failure` launcher.py:74-87 落 worker.log + 2462 stderr）。
- 孤儿收敛路径（`_reconcile_orphans`，1857-1942）：进程死亡未被本 launcher reap（前一 launcher 已死），台账无 end 行——建议在 reconcile 判 terminal 处（1934-1942 `_record_reconcile` 附近）补 `end (reconciled, exit=None|<from [END]>)` 行。

### 2.3 全部子进程 spawn 调用点清单（packages/multi-workers 非测试代码，逐一核对）
worker spawn（台账范围）：
- launcher.py:2450 `proc = subprocess.Popen(cmd, **spawn_kwargs)` —— **唯一** worker CLI spawn。

serve 直管子进程（服务自身，非 worker 运行；台账不覆盖，列全备查）：
- mw.py:235 conductor 子进程（`_conductor_supervise_step`，1s 监督环，死亡自愈重生）。
- mw.py:380 proxy 子进程（proxy_multi）。
- mw.py:397 launcher 子进程（serve 的被监督对象，`launcher_proc.poll()` 400-401 判死）。
- mw.py:519 / 531 `mw start` 分离式 serve 自身（CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW / start_new_session）。
- console_run.py:131 / 139 / 294（console 监督树）。

同步子命令/内部计算子进程（非 worker 运行）：
- mw.py:1473（ue-toolchain，shell=True）、4869（git short commit）、4923（`_git`）、5217（node esbuild build）、5242（npm run build）、5459（框架 install.py）、5651（`_run_stream` npm/pip）、5680（`_run_capture`）。
- autopilot/conductor.py:2922（advance.advance 子进程，120s 超时）；autopilot/xkey.py:1301（verify 子进程）；autopilot/advance.py:92 / 181；tree_watch.py:130（git）；worktree_cmd.py:242 / 259；mw_common.py:1852（pi 标题探测）、2568（端口探测）。

**结论**：`mw serve` 没有第二条 worker spawn 入口——conductor 直执不存在（execute_loop 走 `dispatch.dispatch`，conductor.py:2075-2077 → 队列行，dispatch.py:1527-1545），repair/xkey verify 是 conductor 内部计算子进程（xkey.py:1301）不是 agent worker。台账只需覆盖 launcher.py:2450 一点 + 2.2 的 reconcile 补写。

## 3. PM 窗口的派发记录缺失面

- `/worker` 命令：ui-bridge.ts:2911 `pi.registerCommand("worker", {...})`；`dispatch_worker` 工具：ui-bridge.ts:2338 `name: "dispatch_worker"`。两者共用：写 task.md（writeDispatchTaskMd，2569-2578）→ `dispatchTask`（ui-bridge.ts:2580-2586）：
  ```ts
  const outcome = await dispatchTask(
      { taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath },
      workerStore,
  );
  ```
- `dispatchTask`（pm/task-dispatcher.ts:328-352）：write-face 门 + profile 注入 + `store.upsertWithinLock(full)`（351）——**只写队列行，不 spawn**。`WorkerStore.upsertWithinLock`（shared/worker-store.ts:196-225）tmp+rename 原子写；`origin` 未传 → `workerOrigin` 归一为 `manual`（worker-store.ts:41-45、68-72）。
- **会不会经过 launcher 同一入口？会。** 行落 `_workers.parallel` 后由 launcher `_poll_once` 发现并 `_spawn`（launcher.py:2245-2270）。因此 PM 手动派发**不需要独立 spawn 打点**；spawn 侧台账天然覆盖。
- 独立缺失面（若要「谁派发的」）：
  1. PM 派发**不写 timeline 事件**——`dispatch.dispatch` 成功才 append `"dispatch"`（dispatch.py:1657-1663，`detail=f"{task_key} type={task_type} loop={loop} attempt={attempt}"`），`dispatchTask` 无 timeline 参数。
  2. 队列行无窗口身份：claim 概念（host:pid）只在内存 watch state（ui-bridge.ts:96-102 `claimId === this window's host:pid`），不落盘；`origin` 只有 conductor|manual 两值。
  3. 模型覆盖的审计面已存在：task.md frontmatter `model:` / `model-reason:`（ui-bridge.ts:1450、1491-1492）+ 回执 echo（1464-1498）+ 偏离 role 默认需 model_reason 的门（1485-1486）。
  → 结论：spawn 钩子足够回答「何时、何模型、何 pid 跑了什么」；「哪个 PM 窗口派的」现阶段只能到 `origin=manual` 粒度，加窗口身份需改队列 schema 或让 dispatchTask 追加 timeline 事件（新需求面，不属于本调研改动）。

## 4. 任务类型/角色的权威来源

- **type 词表单一源**：TS `DISPATCH_TYPE_VOCABULARY`（shared/dispatch-card.ts，launcher.py:1018-1025 Python 镜像并注明 T-27 parity 锁）：
  ```python
  DISPATCH_TYPE_VOCABULARY: tuple[str, ...] = (
      "coding", "review", "research", "rag-research", "vision",
      "verifier", "reviewer", "repair", "phase-writer", "roadmap-writer", "codex",
  )
  ```
  PM 可声明面：dispatch-models.ts:75 `DISPATCHABLE_TYPES = ["coding","review","research","rag-research","vision"]`；省略时 legacy 映射（ui-bridge.ts:1293-1309：codex→codex、claude→review、否则 coding）。
- **type→(tools, cli, provider)**：dispatch.py:79-127 `REGISTRY`（7 个注册类型，全 pi/timi；rag-research `conductor_dispatchable=False`）。
- **type→role**：mw_common.py:144-158（§1.5）；TS 镜像 dispatch-models.ts:58。
- **task.md 头解析**：
  - Python（launcher）：`_read_task_md_fields` launcher.py:194-212；`read_task_type` mw_common.py:595-610；`model:` 正则 launcher.py:209。
  - worker（TS）：`parseTaskMd` worker-mode.ts:564-701（`timeoutMin` 570-594）。
  - `timeout:` 渲染：dispatch.py:821-849（`_worker_timeout_min`）+ 955-957。
- **模型解析优先级链实现**：`resolve_dispatch_model` mw_common.py:300-324（原文见 §1.9）；launcher 侧装配 `_resolve_entry_model` launcher.py:166-188；fallback 旁路 launcher.py:2403-2404；per-cli 默认兜底 `_build_command` launcher.py:1776-1806。window-model 写入方：TS `recordWindowModel`（dispatch-models.ts:100，非 worker pi 窗口每次选模型写 `.mw/window-model`，last-writer-wins，mw_common.py:263-271）。
- **台账记「最终生效」还是「请求+来源」——结论：两级都记。**
  依据：(a) 请求 `""`（source=default/window）时实际 `--model` 由 `_build_command` 硬编码补默认（1778 glm-5.3 / 1801 gpt-5.6-sol），只记请求值会丢真实模型；(b) `_effective_entry`（launcher.py:243-277）会按前缀改写 provider（claude/x → anthropic），route 归因需要 spawn 时刻的 effective 值；(c) pi 端还可能做最终 id 解析，`[MODEL]` trace 行（output-writer.ts:604-610）是唯一「实际生效」运行时事实（D-116），PM 面板已消费它（ui-bridge.ts:840-854）。(d) 成本侧（只报 tokens）按「实际生效模型」归因才正确。故：start 行记 `model_value + model_source + effective.model/provider`；可选在 end 行回读该 task trace.log 的最后一条 `[MODEL]` 补运行时 id。

## 5. 现有日志/台账的可复用面

### 5.1 .mw/ 运行期文件（本机实测 + 代码出处）
| 文件 | 写者/格式 | 保留策略 | 出处 |
|---|---|---|---|
| launcher.log | launcher 子进程 stdout/stderr（mw.py:397）；行如 `[launcher] <key>: model=<v> source=<s>`（launcher.py:2423-2426）、`[launcher] spawn failed for ...`（2462）、`[ENVELOPE-SKEW]`（2073-2081） | **每 serve 会话截断**（`open(..., "w")` mw.py:286，注释 283-285） | mw.py:286/397 |
| mw.log | serve 自身 stdout/stderr 重定向（mw.py:290-292），`[mw serve] started/stopped/STALE CODE...` | append（mw.py:281） | mw.py:281 |
| proxy.log | proxy 子进程 out（mw.py:380）；实测仅 `[proxy_multi] listening: pi=7001 claude-cli=7003` | append（mw.py:282） | mw.py:282 |
| conductor.log | conductor 子进程 out（mw.py:235） | **每会话截断**（mw.py:289） | mw.py:287-289 |
| serve-console.log | 分离式 serve stdio，`"ab"` append | 一直追加（mw.py:514-519） | mw.py:517 |
| launcher-beat.<pid> | 每 poll 覆写单行 `ts=<iso>`（mw_common.py:2807-2812） | 每 launcher 一文件；过期+死 pid 被 prune（mw_common.py:2826-2836） | mw_common.py:2797-2812 |
| serve.meta | JSON `{pid, started_at_ms, code_dir, schema, commit, dirty_tracked, dirty_untracked, code_mtime_ms, code_digest, version, written_at_ms}`，tmp+os.replace | serve 退出即删（mw.py:184-191） | mw.py:169-191 |
| mw.pid | pid 文本 | stop 时删 | mw_common.py:2492-2494（pid_file） |
| window-model | 单行 `prefix/model`（实测 `timi/deepseek-v4.1-flash`） | last-writer-wins | mw_common.py:263-271；dispatch-models.ts:100 |
| dispatch.yml | `models:{role: prefix/model}` + `fallback_models:{type:[...]}`（实测含 coding/main/research/review + fallback review） | 配置文件 | mw_common.py:224-257、440-470 |
| tree-watch.json | 采样快照 `{version:1, ts, iso, tracked_total, ..., links:[...]}` | 每次采样覆写 | tree_watch.py |
| workers.lock | O_CREAT|O_EXCL 锁文件，无内容 | 用完即删 | mw_common.py:1986-1988 |

### 5.2 队列/归档侧（.agenticdoc/）
- `_workers.parallel`：9 列 `task_key | status | cli | provider | task_path | dispatched_at | updated_at | model | origin`（mw_common.py:2002-2019 parse、2100-2115 serialize；TS 镜像 worker-store.ts:30-50/113-127；`# mw-queue:v2` 头 2053-2055）。**updated_at 每次状态变更被改写**（mw_common.py:2441）→ 不是 append-only 台账。
- `_workers.stale.parallel`：append 归档 `原行 | <iso> | task.md not found`，锁保护（mw_common.py:2468-2507，append 2493-2497）。
- `_workers.acked`：`task_key|ackedAtIso`（mw_common.py:2134-2156）。
- `_autopilot/timeline.jsonl(+.1/.2)`：行 schema 逐字 `{"ts": <iso+00:00>, "seq": <int>, "ev": <str>, "key": <str|"-">, "stage": <int|null>, "detail": <str>[, "data": {...}]}`（timeline.py:322-346 payload 构造）；EVENT_TYPES 27 个逐字（timeline.py:67-104）；**10MB×2 代轮转**（timeline.py:120-121，rotate 364-388，旧代丢弃）；append `open("a", newline="\n")`（273-278）；torn tail 修复（398-420）；**conductor 是唯一写者（D-109）**（281-283）。实测样本：`{"ts": "2026-10-13T15:48:30+00:00", "seq": 1, "ev": "config", "key": "-", "stage": null, "detail": "STALE CODE ..."}`。
- `_autopilot/auto-decisions.jsonl`：`{seq, phase, kind, count, detail, ...}`（实测 11 行；写者 conductor.py:7638+）。

### 5.3 worker 任务目录内（per-task）
- trace.log：append-only，全部行型（output-writer.ts:580-766）：
  `[START] pid=<pid>`、`[START] <iso> task=<key> type=<type> phases=<n|->`、`[MODEL] <iso> model=<id>`、`[PHASE] <iso> start|done <i>/<n>`、`[TOOL] <iso> <tool> [target≤80]`、`[TOOL_ERR] <iso> <tool> <err≤120>`、`[TIMEOUT] <iso> idle|wall: <detail>`、`[CHECKPOINT] <iso> elapsed=..s reads=.. writes=.. phases=.. uniq_targets=.. repeat_top=.. risk=..`、`[FLOW] <iso> <line>`、`[GOAL_CHECK] phase=<n> goal_mtime=<ms>`、`[HEARTBEAT] <iso> task=<key> phase=<d>/<t>`（60s 节流，heartbeat.ts:5）、`[ERROR] <iso> <first line≤160>`、`[END] <iso> exit=<c> elapsed=<s>s tools=<n> phases=<d>/<t>|->`；launcher 侧追加 `[LAUNCHER] <iso> <reason>`（launcher.py:2019-2030）、`[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>`、`[MODEL_FALLBACK-SKIP]`、`[MODEL_RETRY] <iso> model=<m> attempt=<k>`。
- worker.log：**launcher 每 spawn 以 "wb" 截断重建**（launcher.py:2436），内含 worker stdout（pi 输出）+ launcher 前缀行（`[launcher] ...`，_record_* 家族 74-127）。只反映最近一次进程——不是跨 spawn 台账。
- run.json：`{schema, task_key, run_id(<task_key>@<iso>), owner_key, kind, status, started_at, ended_at?, exit?, supersedes?, artifacts[], pid?, last_heartbeat_at?[, model_exhausted]}`（run-store.ts:36-55；worker 唯一写者 + launcher 只加 lost，mw_common.py:2180-2206）。
- output.md / progress.md：产品文件（写通道归属 worker_file）。

### 5.4 判定：谁能直接当台账、谁会丢信息
- **能直接用的：没有。** launcher.log（截断）、worker.log（截断）、queue（updated_at 可变 + 可重建 IN-3）、timeline（无 worker pid/model/exit，且 ev=dispatch 只在 conductor 派发时出现）、serve.meta（单实例）。
- **会丢信息的复用面**：trace.log 有完整进程生命周期但 (a) 无 project 级统一 schema/无汇聚视图，(b) `[MODEL]` 无 source，(c) launcher 侧无 spawn 墙钟（`[START]` ts 是 worker 进程启动，比 Popen 晚几十~几百 ms），(d) 被 kill -9 的进程无 `[END]`/`[TIMEOUT]`，只有 returncode。queue 行有全量静态元数据（cli/provider/task_path/model/origin/dispatched_at）但动态字段会被改写。
- **结论**：新台账（JSONL append）以 §2 钩子写入静态元数据+墙钟；trace.log/run.json 作为 per-task 佐证源，台账行内放 task_dir 相对路径即可溯源。

## 6. 并发与锁

### 6.1 仓库内锁先例
- Python：mw_common.py:2369-2382
  ```python
  def acquire_lock(lock_file: pathlib.Path, retries: int = 20, base_delay: float = 0.05) -> None:
      """Exclusive lock via O_CREAT|O_EXCL. Same protocol as the TS side."""
      ...
      fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
      ...
      time.sleep(base_delay * (2 ** attempt))
  ```
  release_lock 2384-2388（unlink，FileNotFoundError 吞）。锁路径约定 `.mw/workers.lock`（1986-1988）。持锁期间禁止嵌套获取（会退避 14.6h 后 raise，RQ-D3——dispatch.py:1520-1524 注释、task-dispatcher.ts:343-346 注释）。
- TS：file-lock.ts:9-36 `fs.openSync(lockPath, "wx")`（= O_CREAT|O_EXCL），retries=10、baseDelayMs=50 指数退避。
- 原子整文件写（读-改-写场景的替代）：`_write_workers_file` tmp+`replace`（mw_common.py:2391-2402，`write_text(..., newline="\n")`）；serve.meta tmp+os.replace（mw.py:178-183）；`mark_run_lost` tmp+replace（mw_common.py:2201-2204）；`WorkerStore.upsertWithinLock` tmp+renameSync（worker-store.ts:222-225）。
- 追加写先例：
  - `_workers.stale.parallel`：**在 workers.lock 临界区内 append**（mw_common.py:2493-2497）——共享追加文件的既有模式。
  - timeline.jsonl：`open(path, "a", encoding="utf-8", newline="\n")` + 单写者（timeline.py:273-278、281-283）。
  - trace.log / worker.log：每任务目录单写者（一个 task_key 同时最多一个进程，dispatch 门 dispatch.py:1405-1410 `run-running` 拒绝第二进程），无锁 appendFileSync（output-writer.ts:588）。
  - launcher-beat.<pid>：**无锁、每 launcher 一文件**（mw_common.py:2797-2800 注释 "No lock: one small file per launcher, overwritten"）——per-writer 分片先例。

### 6.2 launcher 多 worker 并发写台账的建议形态（基于先例，非新设计）
- launcher 是单线程 poll 循环（run() while True → _poll_once），自身串行；但同机可能多个 launcher（beat 协议明确支持 "another live launcher"，mw_common.py:2815-2845）+ 多项目（机器级 `~/.mw/usage/`）。跨进程共享追加有两案：
  1. 每次追加持专用锁（复用 acquire_lock 模式，如 `~/.mw/usage/usage.lock`）——同 stale-archive 模式；锁竞争窗口极短（单行 write）。
  2. per-launcher 分片 `usage.<project-hash>.<launcher-pid>.jsonl`，读取时归并——同 launcher-beat 模式，零锁但读取复杂。
- 行格式建议 JSONL（与 timeline 一致），行内含 schema/version 字段（serve.meta 有 `"schema": 1` 先例）。

### 6.3 Windows 下追加写 JSONL 的已知坑（库内证据）
1. **换行翻倍**：Python 文本模式默认平台换行，Windows 会写 \r\n；timeline 的对策是 `newline="\n"`（timeline.py:275-276 注释原文 "keeps LF on Windows — no \r\n doubling"）。_write_workers_file 同法（mw_common.py:2399）。TS 侧 fs.appendFileSync 原样写 `\n`（output-writer.ts:588 等）。
2. **编码**：一律显式 `encoding="utf-8"`（timeline.py:277、mw_common.py:2399 等）；本机默认 locale 是 GBK——本次调研中控制台 print 未指定编码即抛 `UnicodeEncodeError: 'gbk' codec can't encode`，同理缺 encoding 的写文件会写出行 mojibake。读回时 errors="replace"（trace 读取先例 launcher.py:503）。
3. **并发交错/半行**：CPython 对 append 模式无跨进程原子性保证；timeline 的既有防线是「单写者 + torn tail 修复」：`_ensure_tail_terminated`（timeline.py:398-420，追加裸 `\n` 让残行成独立行，读者跳过）与 `_tail_seq` 回扫跳过残行（timeline.py:173-207）。若选共享追加，必须带锁（同 6.2 案 1）并实现同款残行容忍读取。
4. **同秒并发 mtime 语义**：`iso_now()` 秒精度（mw_common.py:171-172），同秒多行无法靠 ts 排序——台账行需自带单调字段（timeline 用 `seq`，launcher 单调计数或 `pid+序号`）。

---

## 未找到清单

1. **session_id 生产者**：未找到。命令：`grep -rn "session[_I]d" packages/coding-agent/src/extensions/agent-team-loop packages/multi-workers --include=*.py --include=*.ts`（排除 test）→ 仅 rag/mcp-client.ts:69/90/112/117/158/167（RAG MCP HTTP 会话头 `Mcp-Session-Id`，与 pi 会话无关）。pi 自身 session id 未被 mw 任何一层落盘。
2. **launcher 侧持久化的 spawn/reap 墙钟时间戳**：未找到。命令：`grep -n "iso_now\|time.time\|time()" packages/multi-workers/launcher.py` → 仅 reconcile（age 计算）、beat、archive 路径；`_spawn`/reap 不写任何时间戳。launcher.log 的 spawn 行（2423-2426）无时间前缀且文件截断。
3. **`/mw stats` 命令**：未找到。`registerCommand(` 全量清点（ui-bridge.ts:1039/1178/1237/2911/3684）= pm-key、pm-save、mw-watch、worker、mw；`mw` 子命令 usage 串（ui-bridge.ts:3861）无 stats。该命令是 usage-monitor 的待实现面（PM 需求决策提到），当前不存在。

## 未覆盖面声明

- 未做 Windows 多进程并发追加同一 JSONL 的实测实验（无写权限做运行实验；结论基于库内先例与注释，标注为 6.1/6.3 的引用而非实测）。
- 未读取 `~/.pi/**`（只读边界禁止）——pi 会话文件里是否存在可关联 session id 未验证；§未找到-1 仅覆盖 mw 代码链路。
- serve 子进程（conductor/proxy）的崩溃-重生细节（D-101）未逐行审计：它们不是 worker 运行，不影响台账钩子位置；若未来把服务进程也纳入台账需另行调研。
- providers.json 凭证链（resolve_credential/describe_missing）只确认存在与调用点（_build_env 280-389），未展开 source 语义——台账不记录凭证值。
- TS 侧 `readRoleModel`/`validateModelValue`/`modelImageCapability`（dispatch-models.ts:118-255）只确认与派发前校验有关，其回显逻辑（ui-bridge.ts:1327-1503）未逐行展开——台账以 launcher/worker 侧值为准。
- 本调研不评估 `~/.mw/usage/` 的具体 schema 设计（属 RQ4/后续 spec 面），只给出钩子与约束。

[VERIFY] worker spawn 点=1（launcher.py:2450）；非 worker 子进程调用点=25（Popen 8：mw.py:235/380/397/519/531+console_run.py:131/139/294；subprocess.run/check_output 17：mw.py:1473/4869/4923/5217/5242/5459/5651/5680、conductor.py:2922、xkey.py:1301、advance.py:92/181、tree_watch.py:130、worktree_cmd.py:242/259、mw_common.py:1852/2568）；队列列=9；type 词表=11；REGISTRY=7；TASK_TYPE_TO_ROLE=10；timeline 事件型=27；trace 行型=16；.mw 运行期文件=12；锁实现=2（Py O_CREAT|O_EXCL / TS wx）；未找到=3；四段齐（0/1-6/未找到/未覆盖）+VERIFY=1
