# W-01 — Python 主体：L0 cmd_start 除雷 + console_run.py run-detached

- key: mw-console-storm-hardening · type: coding · 波次 1
- ac_refs: AC-001, AC-003, AC-004, AC-007 · vc_refs: VC-001, VC-003, VC-004, VC-007

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」可靠性维度。机制依据 M1（design.md §1，evidence/research/design-win32-console-semantics-20261015.md）：`CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP` 使子进程获隐藏控制台且被后代继承（判据 = GetConsoleProcessList 计数）。锚点: `packages/multi-workers/mw.py:506`（cmd_start 现 DETACHED 组合，本次唯一 L0 改点）、`packages/multi-workers/mw.py:1118`（ue-toolchain run_dir 惯例：cmd.txt/run.log/exit.txt）、`packages/multi-workers/mw.py:510`（posix 分支 start_new_session 先例）、`packages/multi-workers/autopilot/advance.py:170`（rc=124 timeout 哨兵惯例）。

## 要求（契约 = design.md D-001/D-002，逐条实现）

1. **L0**：`cmd_start` win32 分支 `creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`（去 DETACHED_PROCESS），stdout/stderr 追加重定向到 `.mw/serve-console.log`（父目录不存在则 mkdir）；posix 分支不动。注释引用 design M1。
2. **新模块 `console_run.py`**（两段式）：
   - `cmd_run_detached(args)`：校验 `--` 后 argv 非空 → 建 run_dir（默认 `<cwd>/.mw/runs/run-<YYYYMMDD-HHMMSS>/`，`--run-dir` 可指定，已存在则追加 `-N`）→ 写 `cmd.txt`（argv 每行一条，encoding="utf-8"）→ 以 `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`（win32）/ `start_new_session=True`（posix）spawn 监督进程（`[sys.executable, __file__所在mw.py路径无法用——改为 python -m? 不，用 [sys.executable, str(MW_PY), "_run_supervisor", ...]` 经 mw.py 内部子命令）→ stdout 打印恰 4 行：`[mw run-detached] pid=<n>` / `marker=<path>` / `heartbeat=<path>` / `log=<path>` → return 0。
   - `_run_supervisor`：内部子命令（不出现在 help）；建 `run.log`（子进程 stdout+stderr 合流，wb）→ 给子进程 env 追加 `MW_CONSOLE_GUARD=1` + `PYTHONPATH` 前置 guard 目录（`Path(mw.py).parent/"mw_console_guard"`，os.pathsep 拼接；guard 目录缺失仅 stderr 单行告警；`MW_CONSOLE_GUARD=0` 已设则不注入）→ spawn 用户命令（flags=0，list-args，无 shell）→ 心跳循环（默认 5s，`--heartbeat-s`）：atomic 写 `heartbeat.json` `{"schema":"mw-heartbeat/1","pid":<child_pid>,"ts_ms":...}`（临时文件+os.replace）→ `--timeout-min` 到点 taskkill /T /F <pid>（win32）/ kill(-pgid)（posix），marker rc=124/timed_out=true → 正常退出则 marker = 子进程真实 rc，`{"schema":"mw-run/1","rc":...,"timed_out":false,"started_at_ms":...,"ended_at_ms":...,"wall_sec":...,"pid":...,"argv":[...]}`（同样原子写）→ spawn 失败（OSError）rc=127 + spawn_failed=true。marker 先于 supervisor 退出落盘（flush+close）。
3. **mw.py 挂接**：argparse 子命令 `run-detached`（参数 `--cwd/--run-dir/--timeout-min/--heartbeat-s` + positionals `--` 后命令）；`_parse_args` 注册处与 dispatch 紧邻现有子命令风格。
4. 不改 launcher/serve 现有 spawn 站点；不碰 `test_*` 文件（W-04 领地）。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/console_run.py`（新建）

## 写入禁止面

- 其余一切（含 test_*.py、README、mw_console_guard/、TS 侧、.mw/ 配置）；禁止 git add/commit；禁止 npm run build / 全量 vitest

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_common.py -q -s 2>&1 | Select-Object -Last 5          # 零新增失败
python mw.py run-detached --run-dir %TEMP%\mw-csg-w01 -- cmd /c exit        # 冒烟：4 行输出
type %TEMP%\mw-csg-w01\marker.json                                           # rc=0 且 schema=mw-run/1
python -c "import console_run; print('import-ok')"                          # 模块可导入
```

## 改动历史

- 2026-10-15 W-01 首派（波次 1；mw-worker-output-contract 已提交、树干净后解扣）。

## 交付格式

- 两文件 diff（mw.py 改动段 + console_run.py 全文）+ 验收命令原始输出（≤30 行/命令）+ 简短实现说明（含与契约的逐条对照）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行，长输出落临时文件后只回读 tail/汇总；证据原始行进报告，不进会话（前批研究 worker 双 OOM 教训）。
