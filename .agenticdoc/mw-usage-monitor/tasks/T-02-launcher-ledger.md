# T-02: launcher 台账钩子 + worker session id 分配

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-001, AC-004, AC-011
依据: `.agenticdoc/mw-usage-monitor/design.md` §2/§3.2/§7/§8；`evidence/research/spec-rq2-dispatch-lifecycle-20261019.md`（§1.9/§1.10/§2/§5/§6）、`spec-rq1-pi-session-usage-20261019.md`（§3/§4）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（Worker 进程级隔离；mw 后台服务常驻）。
- 已核实起点（自行复核）：
  - **全系统唯一 worker spawn 点**：`packages/multi-workers/launcher.py:2450 proc = subprocess.Popen(cmd, **spawn_kwargs)`；
    PM `/worker`、`dispatch_worker`、conductor `dispatch.dispatch` 都只写队列行（RQ2 §0.1/§3）。
  - start 钩子：`:2451 running_procs[entry["task_key"]] = proc` 之后（局部变量 `entry/project_dir/config/proc/
    model_value/model_source/effective/env/cmd/spawn_kwargs/fallback_index/target_config`）。
  - end 钩子：`_poll_once` 内 `:2162 code = proc.returncode if proc.returncode is not None else 1` 之后；
    三分支必覆盖：正常终止 `:2185-2186`、**exit-3 重派 `:2177-2183`（`continue` 前必须写 end）**、spawn 失败
    `:2460-2467`（写 `spawn_failed`）；孤儿收敛 `_reconcile_orphans:1934-1942` 写 `end(reconciled=true)`。
  - `_build_command` `:1764-1806`：`codex` → `["codex","exec","-m",<model>,<starter>]`（:1801）；
    `claude` → `["claude",("--model",m),"-p",<starter>]`（:1803-1807）；pi 分支在 :1788-1794 附近。
  - 模型解析链：`mw_common.resolve_dispatch_model`（mw_common.py:300-324）→ `model_value` + `model_source`
    （`task|config:<role>|window|default|fallback`）；`_effective_entry`（launcher.py:243-277）会改写 provider。
  - `_record_spawn_failure`（launcher.py:74-87）现有失败记录点。
- 依赖：T-01 已交付 `packages/multi-workers/usage.py`（`append_event`/`new_session_id`/`ledger_path`）。
  先读该文件确认签名，**不要改它**（如需扩展签名，在 `output.md` 提出问题而不是自行改动 T-01 的写面）。
- 已定口径：pi `--session-id mw-<key>-<pid>-<seq>`；claude `--session-id <uuid4>`；codex 不传（无该参数）；
  同 id 会 resume 旧文件 → **seq 每次 spawn 递增，永不复用**；台账只是元数据，token 由查询面 join。

## 要求

1. `_build_command` 增加可选参数 `session_id: str | None = None`：`cli=="pi"` 时把
   `["--session-id", session_id]` 插入 argv；`cli=="claude"` 时把 `["--session-id", session_id]` 插入 argv；
   `cli=="codex"` 忽略。**不得改变既有参数顺序语义**（`-p` 仍在最后、`--model` 位置不变）。
2. `_spawn`：分配 `session_id`（pi → `usage.new_session_id(key, os.getpid(), seq)`；claude → `str(uuid.uuid4())`；
   codex → `None`），`seq` 为 launcher 实例内单调计数器（`self._usage_seq`），保证跨重启唯一（pid 变化）。
3. `Popen` 成功后立刻写 `start` 事件（含 `event/run_id/ts/source/key/task_key/type/role/cli/attribution/
   session_id/model/model_source/pid/cwd/project`），并在实例上记住 `run_id`（reap 时要配对）；
   `attribution`：pi/claude → `exact`；codex → `unknown_cli`。
4. `_poll_once` reap：`code` 得到后立刻写 `end` 事件（`run_id/ts/exit/wall_s/status/reconciled`），
   **exit-3 重派在 `continue` 前写**；`wall_s` 用 `time.time()` 差。
5. `_record_spawn_failure` 路径写 `event="spawn_failed"`（无 pid、无 wall）。
6. `_reconcile_orphans` terminal 判定处写 `end`，`reconciled=true`，`exit` 取 trace.log `[END]` 解析
   （可复用 `mw_common.parse_end_exit`，:2772-2795）或 `None`（**不写 0**）。
7. 台账调用必须 fail-soft：失败只写一行 stderr warning，绝不改变 spawn/reap 控制流、不新增异常传播路径。
8. 把「构造事件 dict」抽成模块内纯函数（如 `_usage_start_record(...)` / `_usage_end_record(...)`），
   便于测试不启进程地断言字段。

## 写入允许面

- `packages/multi-workers/launcher.py`
- `packages/multi-workers/test_launcher_run_ledger.py`（新建）
- `packages/multi-workers/test_usage.py`（**仅在需要补 launcher 相关纯函数用例时新增测试函数**；不得改动既有断言）

## 写入禁止面

- `packages/multi-workers/usage.py`（T-01 的写面）、`mw.py`、`mw_common.py`、任何 TS、CHANGELOG
- 其它 key 目录、`.mw/**` 运行期文件

## 验收命令

```powershell
cd H:\git\Multi-Workers\packages\multi-workers
python -m py_compile launcher.py
python -m pytest test_launcher_run_ledger.py -q
python -m pytest test_launcher.py -q   # 既有 launcher 用例零回归
```

`test_launcher_run_ledger.py` 必须覆盖：
1. `_build_command` 对三种 cli 的 argv 形态（pi/claude 含 `--session-id`，codex 不含；`-p` 仍在尾部）；
2. start/end 事件字段齐全且 `run_id` 可配对，`load_runs` 能还原 `wall_s`；
3. exit-3 重派分支写 end（模拟一条 `code=3` 的 reap，断言 end 先于下一次 start）；
4. spawn 失败写 `spawn_failed`；
5. fail-soft：台账目录不可写（`MW_USAGE_DIR` 指向只读/非法路径）时 spawn 仍成功、无异常。

## 改动历史

（首次改动，填写：改了 launcher 哪几处、为什么、被否决的替代方案（如"在 _build_env 加
PI_CODING_AGENT_SESSION_DIR 隔离目录"为何不选）。）
